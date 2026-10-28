import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

/**
 * Mode persistant utilisé par le site web (app.py) : l'index est chargé une seule fois, puis chaque
 * ligne lue sur l'entrée standard est une requête (champs séparés par des tabulations) ; la réponse
 * est écrite ligne par ligne et se termine par « END ».
 *
 *   R  requête  k  mesure  tf  section  du  au  titre  nb_phrases_resume
 *   C  requête  k  mesure  tf  n  min_df  section  du  au  titre         (chi2)
 *
 * Réponse à R : Q terme idf | F nb_filtre | M ms | R rang id score date section longueur titre | S phrase
 * Réponse à C : (H titre taille_classe taille_univers, puis T terme chi2 df_classe df_total)*
 * Erreur      : ERR message
 */
public class Serveur {
    static String c(String s) { return s.replace('\t', ' ').replace('\n', ' ').replace('\r', ' '); }

    static String vide(String[] f, int i) { return i < f.length && !f[i].isBlank() ? f[i].strip() : null; }

    public static void lancer(String[] args) throws Exception {
        PrintStream out = new PrintStream(System.out, false, StandardCharsets.UTF_8);
        Path index = Paths.get("..", "resultats", "index_java.tsv");
        Path stop = Paths.get("..", "ressources", "stopwords_ar.txt");
        Path corpus = Paths.get("..", "corpus");
        for (int i = 1; i < args.length; i++) {
            switch (args[i]) {
                case "--index" -> index = Paths.get(args[++i]);
                case "--stopwords" -> stop = Paths.get(args[++i]);
                case "--corpus" -> corpus = Paths.get(args[++i]);
                default -> { }
            }
        }
        Index idx = Index.charger(index);
        Map<String, Moteur> moteurs = new HashMap<>();
        for (String tf : Moteur.SCHEMAS_TF) moteurs.put(tf, new Moteur(idx, new Preprocesseur(stop, idx.stemming), tf));
        out.println("READY\t" + idx.n());
        out.flush();

        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String ligne;
        while ((ligne = in.readLine()) != null) {
            String[] f = ligne.split("\t", -1);
            try {
                if (f[0].equals("R")) recherche(out, idx, moteurs, corpus, f);
                else if (f[0].equals("C")) chi2(out, idx, moteurs, f);
                else out.println("ERR\tcommande inconnue");
            } catch (Exception e) {
                out.println("ERR\t" + c(String.valueOf(e.getMessage())));
            }
            out.println("END");
            out.flush();
        }
    }

    static Set<Integer> filtre(Index idx, String[] f, int i) {
        String s = vide(f, i);
        return Filtres.construire(idx, s == null ? null : Integer.valueOf(s), vide(f, i + 1), vide(f, i + 2), vide(f, i + 3));
    }

    static void recherche(PrintStream out, Index idx, Map<String, Moteur> moteurs, Path corpus, String[] f) throws Exception {
        String q = f[1];
        int k = Integer.parseInt(f[2]);
        String mesure = f[3];
        Moteur m = moteurs.get(f[4]);
        if (m == null) throw new IllegalArgumentException("schéma TF inconnu : " + f[4]);
        Set<Integer> filtre = filtre(idx, f, 5);
        int nres = Integer.parseInt(f[9]);
        long t0 = System.nanoTime();
        List<Moteur.Resultat> res = m.rechercher(q, k, mesure, filtre, "index");
        double ms = (System.nanoTime() - t0) / 1e6;
        for (Map.Entry<String, Double> e : m.vecteurRequete(q).poids.entrySet())
            out.println("Q\t" + e.getKey() + "\t" + String.format(Locale.ROOT, "%.6f", m.idf.get(e.getKey())));
        if (filtre != null) out.println("F\t" + filtre.size());
        out.println(String.format(Locale.ROOT, "M\t%.3f", ms));
        int rang = 1;
        for (Moteur.Resultat r : res) {
            Index.Doc d = idx.docs.get(r.pos);
            out.println(String.format(Locale.ROOT, "R\t%d\t%s\t%.6f\t%s\t%s\t%d\t%s",
                    rang++, d.id, r.score, d.date, d.section, d.longueur, c(d.titre)));
            if (nres > 0)
                for (String ph : Resume.resumer(m, corpus, r.pos, nres, q)) out.println("S\t" + c(ph));
        }
    }

    static void bloc(PrintStream out, String titre, int nc, int nu, List<Statistiques.Terme> termes) {
        out.println("H\t" + c(titre) + "\t" + nc + "\t" + nu);
        for (Statistiques.Terme t : termes)
            out.println(String.format(Locale.ROOT, "T\t%s\t%.6f\t%d\t%d", t.terme, t.chi2, t.dfClasse, t.dfTotal));
    }

    static void chi2(PrintStream out, Index idx, Map<String, Moteur> moteurs, String[] f) {
        String q = f[1].strip();
        int k = Integer.parseInt(f[2]), n = Integer.parseInt(f[5]), minDf = Integer.parseInt(f[6]);
        Moteur m = moteurs.get(f[4]);
        Set<Integer> filtre = filtre(idx, f, 7);
        if (!q.isEmpty()) {                                         // classe = k premiers résultats
            Set<Integer> classe = new TreeSet<>();
            for (Moteur.Resultat r : m.rechercher(q, k, f[3], filtre, "index")) classe.add(r.pos);
            bloc(out, "Top-" + k + " de \u00AB " + q + " \u00BB", classe.size(), idx.n(),
                    Statistiques.termesCaracteristiques(idx, classe, null, n, minDf));
        } else if (filtre != null) {                                // classe = décisions filtrées
            bloc(out, "D\u00E9cisions filtr\u00E9es", filtre.size(), idx.n(),
                    Statistiques.termesCaracteristiques(idx, filtre, null, n, minDf));
        } else {                                                    // une analyse par section
            Map<String, Set<Integer>> cl = Statistiques.classesParSection(idx);
            Set<Integer> univers = new TreeSet<>();
            for (Set<Integer> s : cl.values()) univers.addAll(s);
            for (Map.Entry<String, Set<Integer>> e : cl.entrySet())
                bloc(out, "Section " + e.getKey(), e.getValue().size(), univers.size(),
                        Statistiques.termesCaracteristiques(idx, e.getValue(), univers, n, minDf));
        }
    }
}
