import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Index inversé. Format de fichier TSV partagé avec la version Python :
 *   #STEMMING  none|light10
 *   D  position  id  longueur  date  section  titre
 *   T  terme  pos:tf,pos:tf,...
 */
public class Index {
    public static class Doc {
        public final String id, titre, date, section;   // date AAAA-MM-JJ et section : vides si introuvables
        public final int longueur;
        Doc(String id, String titre, int longueur, String date, String section) {
            this.id = id; this.titre = titre; this.longueur = longueur; this.date = date; this.section = section;
        }
    }

    public String stemming;
    public final List<Doc> docs = new ArrayList<>();
    /** terme -> (position du document -> tf brut), trié pour une sortie reproductible */
    public final TreeMap<String, TreeMap<Integer, Integer>> postings = new TreeMap<>();

    public int n() { return docs.size(); }

    // ---------- construction ----------
    private static final Pattern P_NUM = Pattern.compile("\u0631\u0642\u0645\\s*(\\d+\\s*/\\s*\\d+)", Pattern.UNICODE_CHARACTER_CLASS);
    private static final Pattern P_DOSSIER = Pattern.compile("\\d{4}/\\d+/\\d+/\\d+");
    private static final String DEBUT_DECISION = "\u0642\u0631\u0627\u0631 \u0645\u062D\u0643\u0645\u0629 \u0627\u0644\u0646\u0642\u0636"; // "قرار محكمة النقض"
    private static final String MOT_NUM = "\u0631\u0642\u0645 "; // "رقم "

    private static final Pattern P_DATE = Pattern.compile(
            "\u0628\u062A\u0627\u0631\u064A\u062E\\s*(\\d{1,2})\\s+([^\\s\\d]+)\\s+(\\d{4})", Pattern.UNICODE_CHARACTER_CLASS);
    private static final Pattern P_SECTION = Pattern.compile(
            "\u0631\u0642\u0645\\s*(\\d{1,2})\\s*/\\s*\\d+", Pattern.UNICODE_CHARACTER_CLASS);
    private static final Map<String, Integer> MOIS = Map.ofEntries(
            Map.entry("\u064A\u0646\u0627\u064A\u0631", 1),
            Map.entry("\u062C\u0627\u0646\u0641\u064A", 1),
            Map.entry("\u0641\u0628\u0631\u0627\u064A\u0631", 2),
            Map.entry("\u0645\u0627\u0631\u0633", 3),
            Map.entry("\u0627\u0628\u0631\u064A\u0644", 4),
            Map.entry("\u0645\u0627\u064A\u0648", 5),
            Map.entry("\u0645\u0627\u064A", 5),
            Map.entry("\u064A\u0648\u0646\u064A\u0648", 6),
            Map.entry("\u064A\u0648\u0646\u064A\u0647", 6),
            Map.entry("\u064A\u0648\u0644\u064A\u0648\u0632", 7),
            Map.entry("\u064A\u0648\u0644\u064A\u0648", 7),
            Map.entry("\u063A\u0634\u062A", 8),
            Map.entry("\u0627\u063A\u0633\u0637\u0633", 8),
            Map.entry("\u0634\u062A\u0646\u0628\u0631", 9),
            Map.entry("\u0633\u0628\u062A\u0645\u0628\u0631", 9),
            Map.entry("\u0627\u0643\u062A\u0648\u0628\u0631", 10),
            Map.entry("\u0646\u0648\u0646\u0628\u0631", 11),
            Map.entry("\u0646\u0648\u0641\u0645\u0628\u0631", 11),
            Map.entry("\u062F\u062C\u0646\u0628\u0631", 12),
            Map.entry("\u062F\u064A\u0633\u0645\u0628\u0631", 12));

    /** {date ISO, section} lues dans l'en-tête ; chaînes vides si absentes. */
    static String[] metadonnees(String texte) {
        List<String> L = lignes(texte);
        String tete = String.join(" ", L.subList(0, Math.min(10, L.size())));
        String date = "", section = "";
        Matcher m = P_DATE.matcher(tete);
        if (m.find()) {
            Integer mm = MOIS.get(Preprocesseur.normaliser(m.group(2)));
            if (mm != null)
                date = String.format("%s-%02d-%02d", m.group(3), mm, Integer.parseInt(m.group(1)));
        }
        Matcher s = P_SECTION.matcher(tete);
        if (s.find()) section = s.group(1);
        return new String[]{date, section};
    }

    /** Lignes non vides, sans espaces de bord. */
    static List<String> lignes(String texte) {
        List<String> L = new ArrayList<>();
        for (String l : texte.split("\r\n|\r|\n")) { l = strip(l); if (!l.isEmpty()) L.add(l); }
        return L;
    }

    private static String strip(String s) {
        return s.replaceAll("(?U)^\\s+|\\s+$", "");
    }

    /** Titre = « رقم X/Y - sujet » (l'en-tête varie d'un document à l'autre). */
    static String titre(String texte) {
        List<String> L = lignes(texte);
        List<String> tete = L.subList(0, Math.min(10, L.size()));
        Matcher m = P_NUM.matcher(String.join(" ", tete));
        String numero = m.find() ? MOT_NUM + m.group(1).replaceAll("(?U)\\s", "") : "";
        int iDec = -1;
        for (int i = 0; i < Math.min(6, L.size()); i++) if (L.get(i).startsWith(DEBUT_DECISION)) { iDec = i; break; }
        List<String> avant = new ArrayList<>();
        for (int i = 0; i < Math.max(iDec, 0); i++) if (L.get(i).length() > 2) avant.add(L.get(i));
        int j = -1;
        for (int i = 0; i < tete.size(); i++) if (P_DOSSIER.matcher(tete.get(i)).find()) { j = i; break; }
        String apres = (j >= 0 && j < L.size() - 1) ? L.get(j + 1) : "";
        String sujet = !avant.isEmpty() ? String.join(" ", avant) : apres;
        if (sujet.length() < 5) {
            sujet = "";
            for (String l : L) if (l.length() > 40) { sujet = l; break; }
        }
        String t = numero.isEmpty() ? sujet : numero + " - " + sujet;
        t = strip(t.replaceAll("(?U)\\s+", " "));
        return t.length() > 140 ? t.substring(0, 140) : t;
    }

    private static int[] cleNum(String nom) {
        String b = nom.substring(0, nom.length() - 4);
        return b.chars().allMatch(Character::isDigit) ? new int[]{0, Integer.parseInt(b)} : new int[]{1, 0};
    }

    public static Index construire(Path dossier, Preprocesseur prepro) throws IOException {
        Index idx = new Index();
        idx.stemming = prepro.getStemming();
        File[] fs = dossier.toFile().listFiles((d, nom) -> nom.endsWith(".txt"));
        Arrays.sort(fs, Comparator.<File>comparingInt(f -> cleNum(f.getName())[0])
                .thenComparingInt(f -> cleNum(f.getName())[1])
                .thenComparing(File::getName));
        for (File fichier : fs) {
            String nom = fichier.getName();
            String texte = Files.readString(fichier.toPath(), StandardCharsets.UTF_8);
            List<String> tokens = prepro.tokens(texte);
            if (tokens.isEmpty()) continue;                 // fichier vide : ignoré (ne compte pas dans N)
            int pos = idx.docs.size();
            String[] meta = metadonnees(texte);
            idx.docs.add(new Doc(nom.substring(0, nom.length() - 4), titre(texte), tokens.size(), meta[0], meta[1]));
            for (String t : tokens)
                idx.postings.computeIfAbsent(t, k -> new TreeMap<>()).merge(pos, 1, Integer::sum);
        }
        return idx;
    }

    // ---------- sauvegarde / chargement ----------
    public void sauver(Path chemin) throws IOException {
        try (BufferedWriter w = Files.newBufferedWriter(chemin, StandardCharsets.UTF_8)) {
            w.write("#STEMMING\t" + stemming + "\n");
            for (int pos = 0; pos < docs.size(); pos++) {
                Doc d = docs.get(pos);
                w.write("D\t" + pos + "\t" + d.id + "\t" + d.longueur + "\t" + d.date + "\t" + d.section + "\t" + d.titre + "\n");
            }
            for (Map.Entry<String, TreeMap<Integer, Integer>> e : postings.entrySet()) {
                StringBuilder sb = new StringBuilder("T\t").append(e.getKey()).append('\t');
                boolean premier = true;
                for (Map.Entry<Integer, Integer> p : e.getValue().entrySet()) {
                    if (!premier) sb.append(',');
                    sb.append(p.getKey()).append(':').append(p.getValue());
                    premier = false;
                }
                w.write(sb.append('\n').toString());
            }
        }
    }

    public static Index charger(Path chemin) throws IOException {
        Index idx = new Index();
        try (BufferedReader r = Files.newBufferedReader(chemin, StandardCharsets.UTF_8)) {
            String ligne;
            while ((ligne = r.readLine()) != null) {
                String[] c = ligne.split("\t", -1);
                switch (c[0]) {
                    case "#STEMMING" -> idx.stemming = c[1];
                    case "D" -> idx.docs.add(new Doc(c[2], c[6], Integer.parseInt(c[3]), c[4], c[5]));
                    case "T" -> {
                        TreeMap<Integer, Integer> p = new TreeMap<>();
                        for (String x : c[2].split(",")) {
                            String[] ab = x.split(":");
                            p.put(Integer.parseInt(ab[0]), Integer.parseInt(ab[1]));
                        }
                        idx.postings.put(c[1], p);
                    }
                    default -> { }
                }
            }
        }
        return idx;
    }
}
