import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Interface en ligne de commande (version Java).
 *   indexer    [--corpus ../corpus] [--index ...] [--stemming light10|none]
 *   rechercher "عقد البيع" [-k 10] [--mesure cosinus] [--tf log] [--section 2] [--du 2023-02-01] [--au 2023-03-31]
 *              [--titre تحفيظ] [--resume 2] [--methode index|lineaire]
 *   interactif | fichier requetes.txt   (mêmes options)
 *   resumer 954 [-n 3]                   résumé automatique d'une décision
 *   benchmark [requetes.txt]             index inversé vs sans index
 *   chi2 ["requête"] [-n 15] [--min-df 3] [-k 10] [filtres]   termes caractéristiques (chi2) : par section,
 *                                        des décisions filtrées, ou des k premiers résultats de la requête
 *   serveur                              mode persistant (lit des requêtes sur stdin) utilisé par le site web
 * Lancement : java -cp SAFAR_v2_jar.zip:out Main <commande> ...
 */
public class Main {
    static PrintStream out;
    static Path corpus = Paths.get("..", "corpus");
    static String mesure = "cosinus", methode = "index";
    static int k = 10, resume = 0, n = -1, minDf = 3;
    static Set<Integer> filtre;

    static String court(String t, int max) {
        if (t.length() <= max) return t;
        return t.substring(0, max).replaceAll("(?U)\\s+$", "") + "\u2026";
    }

    static void afficher(Moteur m, String requete) throws Exception {
        long t0 = System.nanoTime();
        Moteur.VecteurRequete q = m.vecteurRequete(requete);
        List<Moteur.Resultat> res = m.rechercher(requete, k, mesure, filtre, methode);
        double ms = (System.nanoTime() - t0) / 1e6;
        if (q.poids.isEmpty()) out.println("Aucun terme connu.");
        else {
            StringBuilder sb = new StringBuilder("Termes de la requête (après prétraitement) : ");
            boolean premier = true;
            for (Map.Entry<String, Double> e : q.poids.entrySet()) {
                if (!premier) sb.append(", ");
                sb.append(e.getKey()).append(String.format(Locale.ROOT, " (idf=%.3f)", m.idf.get(e.getKey())));
                premier = false;
            }
            out.println(sb);
        }
        if (filtre != null) out.println("Filtres actifs : " + filtre.size() + " document(s) autorisé(s)");
        out.println(String.format(Locale.ROOT, "Mesure = %s | TF = %s | %d résultat(s) en %.1f ms",
                mesure, m.getSchemaTf(), res.size(), ms));
        int rang = 1;
        for (Moteur.Resultat r : res) {
            Index.Doc d = m.getIndex().docs.get(r.pos);
            out.println(String.format(Locale.ROOT, "%2d. [%.6f] doc %6s | %s", rang++, r.score, d.id, d.titre));
            if (resume > 0)
                for (String ph : Resume.resumer(m, corpus, r.pos, resume, requete)) out.println("      \u2022 " + court(ph, 260));
        }
    }

    public static void main(String[] args) throws Exception {
        out = new PrintStream(System.out, true, StandardCharsets.UTF_8);
        if (args.length == 0) { out.println("Commandes : indexer | rechercher | interactif | fichier | resumer | benchmark | chi2 | serveur"); return; }
        String cmd = args[0], arg = null, du = null, au = null, titre = null;
        if (cmd.equals("serveur")) { Serveur.lancer(args); return; }
        Integer section = null;
        Path index = Paths.get("..", "resultats", "index_java.tsv");
        Path stop = Paths.get("..", "ressources", "stopwords_ar.txt");
        String stemming = "light10", tf = "log";
        for (int i = 1; i < args.length; i++) {
            switch (args[i]) {
                case "--corpus" -> corpus = Paths.get(args[++i]);
                case "--index" -> index = Paths.get(args[++i]);
                case "--stopwords" -> stop = Paths.get(args[++i]);
                case "--stemming" -> stemming = args[++i];
                case "--mesure" -> mesure = args[++i];
                case "--tf" -> tf = args[++i];
                case "--methode" -> methode = args[++i];
                case "--section" -> section = Integer.parseInt(args[++i]);
                case "--du" -> du = args[++i];
                case "--au" -> au = args[++i];
                case "--titre" -> titre = args[++i];
                case "--resume" -> resume = Integer.parseInt(args[++i]);
                case "-k" -> k = Integer.parseInt(args[++i]);
                case "-n" -> n = Integer.parseInt(args[++i]);
                case "--min-df" -> minDf = Integer.parseInt(args[++i]);
                default -> arg = args[i];
            }
        }
        if (cmd.equals("indexer")) {
            long t0 = System.nanoTime();
            Index idx = Index.construire(corpus, new Preprocesseur(stop, stemming));
            idx.sauver(index);
            out.println(String.format(Locale.ROOT, "%d documents, %d termes, stemming=%s -> %s (%.2f s)",
                    idx.n(), idx.postings.size(), stemming, index, (System.nanoTime() - t0) / 1e9));
            return;
        }
        if (cmd.equals("benchmark")) {
            Benchmark.lancer(corpus, stop, arg != null ? Paths.get(arg) : Paths.get("..", "requetes_test.txt"));
            return;
        }
        if (n < 0) n = cmd.equals("chi2") ? 15 : 3;
        Index idx = Index.charger(index);
        Moteur m = new Moteur(idx, new Preprocesseur(stop, idx.stemming), tf);
        filtre = Filtres.construire(idx, section, du, au, titre);
        switch (cmd) {
            case "rechercher" -> {
                if (arg == null) { out.println("Donnez une requête."); return; }
                afficher(m, arg);
            }
            case "chi2" -> {
                List<String> L;
                if (arg != null) {                                   // classe = k premiers résultats
                    Set<Integer> classe = new java.util.TreeSet<>();
                    for (Moteur.Resultat r : m.rechercher(arg, k, mesure, filtre, methode)) classe.add(r.pos);
                    L = Statistiques.formater("Top-" + k + " de \u00AB " + arg + " \u00BB", classe.size(), idx.n(),
                            Statistiques.termesCaracteristiques(idx, classe, null, n, minDf));
                } else if (filtre != null) {                        // classe = décisions filtrées
                    L = Statistiques.formater("D\u00E9cisions filtr\u00E9es", filtre.size(), idx.n(),
                            Statistiques.termesCaracteristiques(idx, filtre, null, n, minDf));
                } else L = Statistiques.parSection(idx, n, minDf);   // une analyse par section
                for (String l : L) out.println(l);
            }
            case "fichier" -> {
                for (String l : Files.readAllLines(Paths.get(arg), StandardCharsets.UTF_8)) {
                    if (l.isBlank()) continue;
                    out.println("=== " + l.strip());
                    afficher(m, l.strip());
                }
            }
            case "resumer" -> {
                int pos = -1;
                for (int i = 0; i < idx.n(); i++) if (idx.docs.get(i).id.equals(arg)) { pos = i; break; }
                if (pos < 0) { out.println("Document inconnu : " + arg); return; }
                Index.Doc d = idx.docs.get(pos);
                out.println("Doc " + d.id + " | " + d.date + " | section " + d.section + " | " + d.titre);
                for (String ph : Resume.resumer(m, corpus, pos, n, null)) out.println("  \u2022 " + court(ph, 400));
            }
            case "interactif" -> {
                out.println("Requête (vide pour quitter) :");
                BufferedReader r = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
                String l;
                while ((l = r.readLine()) != null && !l.isBlank()) afficher(m, l.strip());
            }
            default -> out.println("Commande inconnue : " + cmd);
        }
    }
}
