import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * Statistique du chi-deux (chi2) pour la sélection de termes caractéristiques (même définition qu'en Python).
 *
 * Tableau de contingence 2x2 (présence du terme = au moins une occurrence dans le document) :
 *                      t présent   t absent
 *      dans C             A           C'
 *      hors C             B           D
 *   chi2 = N (A D - B C')^2 / [ (A+B)(C'+D)(A+C')(B+D) ],  N = |univers|, 1 degré de liberté.
 * Seuils : 3,84 (*, p&lt;0,05) ; 6,63 (**, p&lt;0,01) ; 10,83 (***, p&lt;0,001).
 * Seules les associations positives sont gardées, avec au moins minDf documents de la classe.
 */
public class Statistiques {
    public static class Terme {
        public final String terme;
        public final double chi2;
        public final int dfClasse, dfTotal;
        Terme(String terme, double chi2, int dfClasse, int dfTotal) {
            this.terme = terme; this.chi2 = chi2; this.dfClasse = dfClasse; this.dfTotal = dfTotal;
        }
    }

    public static String niveau(double x) {
        if (x >= 10.83) return "***";
        if (x >= 6.63) return "**";
        if (x >= 3.84) return "*";
        return "";
    }

    public static double chi2(long a, long b, long c, long d) {
        long den = (a + b) * (c + d) * (a + c) * (b + d);
        if (den == 0) return 0.0;
        long n = a + b + c + d;
        return (double) (n * (a * d - b * c) * (a * d - b * c)) / (double) den;
    }

    /** univers == null : tous les documents. */
    public static List<Terme> termesCaracteristiques(Index index, Set<Integer> classe, Set<Integer> univers,
                                                     int n, int minDf) {
        Set<Integer> u = new TreeSet<>();
        if (univers == null) for (int i = 0; i < index.n(); i++) u.add(i); else u.addAll(univers);
        Set<Integer> cl = new TreeSet<>(classe);
        cl.retainAll(u);
        int taille = u.size(), nc = cl.size();
        List<Terme> res = new ArrayList<>();
        for (Map.Entry<String, TreeMap<Integer, Integer>> e : index.postings.entrySet()) {
            int a = 0, tot = 0;
            for (int pos : e.getValue().keySet()) {
                if (u.contains(pos)) { tot++; if (cl.contains(pos)) a++; }
            }
            if (a < minDf) continue;
            int b = tot - a, c = nc - a, d = taille - nc - b;
            if ((long) a * d - (long) b * c <= 0) continue;
            res.add(new Terme(e.getKey(), chi2(a, b, c, d), a, tot));
        }
        res.sort(Comparator.<Terme>comparingDouble(t -> -t.chi2).thenComparing(t -> t.terme));
        return res.size() > n ? new ArrayList<>(res.subList(0, n)) : res;
    }

    /** section -> positions, pour les décisions dont la section est connue. */
    public static TreeMap<String, Set<Integer>> classesParSection(Index index) {
        TreeMap<String, Set<Integer>> cl = new TreeMap<>();
        for (int pos = 0; pos < index.n(); pos++) {
            String s = index.docs.get(pos).section;
            if (!s.isEmpty()) cl.computeIfAbsent(s, k -> new TreeSet<>()).add(pos);
        }
        return cl;
    }

    public static List<String> formater(String titre, int tailleClasse, int tailleUnivers, List<Terme> termes) {
        List<String> L = new ArrayList<>();
        L.add(titre + " : " + tailleClasse + " décision(s) dans la classe / " + tailleUnivers + " dans l'univers");
        if (termes.isEmpty()) L.add("  (aucun terme significatif)");
        int i = 1;
        for (Terme t : termes)
            L.add(String.format(Locale.ROOT, "  %2d. chi2=%9.4f %-3s df_classe=%3d df_total=%3d | %s",
                    i++, t.chi2, niveau(t.chi2), t.dfClasse, t.dfTotal, t.terme));
        return L;
    }

    /** Une analyse par section ; l'univers = décisions dont la section est connue. */
    public static List<String> parSection(Index index, int n, int minDf) {
        TreeMap<String, Set<Integer>> cl = classesParSection(index);
        Set<Integer> univers = new TreeSet<>();
        for (Set<Integer> s : cl.values()) univers.addAll(s);
        List<String> L = new ArrayList<>();
        for (Map.Entry<String, Set<Integer>> e : cl.entrySet())
            L.addAll(formater("Section " + e.getKey(), e.getValue().size(), univers.size(),
                    termesCaracteristiques(index, e.getValue(), univers, n, minDf)));
        return L;
    }
}
