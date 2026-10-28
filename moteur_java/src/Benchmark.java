import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;

/**
 * Apport de l'index inversé :
 *  A. sans index : à chaque requête on relit et on re-prétraite tout le corpus, on recalcule TF-IDF ;
 *  B. balayage : vecteurs TF-IDF en mémoire, mais on parcourt TOUS les documents ;
 *  C. index inversé : on ne parcourt que les listes de postings des termes de la requête.
 */
public class Benchmark {
    private static double moyenneMs(Consumer<String> f, List<String> requetes, int rep) {
        long t0 = System.nanoTime();
        for (int r = 0; r < rep; r++) for (String q : requetes) f.accept(q);
        return (System.nanoTime() - t0) / 1e6 / (rep * requetes.size());
    }

    public static void lancer(Path corpus, Path stop, Path fichierRequetes) throws Exception {
        List<String> requetes = Files.readAllLines(fichierRequetes, StandardCharsets.UTF_8).stream()
                .map(String::strip).filter(l -> !l.isEmpty()).toList();
        Preprocesseur p = new Preprocesseur(stop, "light10");
        Moteur m = new Moteur(Index.construire(corpus, p), p, "log");
        m.vecteursDocs();

        boolean ok = true;
        for (String q : requetes) for (String mes : new String[]{"cosinus", "jaccard", "euclidienne"})
            ok &= m.rechercher(q, 10, mes, null, "index").stream().map(r -> r.pos + ":" + r.score).toList()
                    .equals(m.rechercher(q, 10, mes, null, "lineaire").stream().map(r -> r.pos + ":" + r.score).toList());

        Consumer<String> sansIndex = q -> {
            try {
                Preprocesseur p2 = new Preprocesseur(stop, "light10");     // cache de stemming vide
                new Moteur(Index.construire(corpus, p2), p2, "log").rechercher(q, 10, "cosinus");
            } catch (Exception e) { throw new RuntimeException(e); }
        };
        Consumer<String> balayage = q -> m.rechercher(q, 10, "cosinus", null, "lineaire");
        Consumer<String> inverse = q -> m.rechercher(q, 10, "cosinus", null, "index");
        sansIndex.accept(requetes.get(0));                                  // échauffement (JIT, chargement SAFAR)
        moyenneMs(balayage, requetes, 100); moyenneMs(inverse, requetes, 100);
        double ta = moyenneMs(sansIndex, requetes.subList(0, 3), 1);
        double tb = moyenneMs(balayage, requetes, 300);
        double tc = moyenneMs(inverse, requetes, 300);
        Main.out.println(String.format(Locale.ROOT, "Corpus : %d documents, %d termes, %d requêtes",
                m.getIndex().n(), m.getIndex().postings.size(), requetes.size()));
        Main.out.println("Résultats identiques entre les méthodes : " + (ok ? "oui" : "NON"));
        Main.out.println(String.format(Locale.ROOT, "A. Sans index (tout recalculer)   : %10.3f ms / requête", ta));
        Main.out.println(String.format(Locale.ROOT, "B. Balayage de tous les documents : %10.3f ms / requête", tb));
        Main.out.println(String.format(Locale.ROOT, "C. Index inversé                  : %10.3f ms / requête", tc));
        Main.out.println(String.format(Locale.ROOT, "Accélération C vs A : x%,.0f   |   C vs B : x%.1f", ta / tc, tb / tc));
    }
}
