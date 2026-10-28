import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/**
 * Moteur de recherche : TF, IDF, TF-IDF et mesures de similarité.
 *   idf(t)  = log10(N / df(t))
 *   tf      = raw : c | log : 1 + log10(c) | norm : c / |d|
 *   poids   = tf * idf
 *   cosinus = (q.d)/(|q||d|) ; produit = q.d ; jaccard ; dice ; euclidienne = 1/(1+||q-d||)
 */
public class Moteur {
    public static final String[] MESURES = {"cosinus", "produit", "jaccard", "dice", "euclidienne"};
    public static final String[] SCHEMAS_TF = {"raw", "log", "norm"};
    public static final String[] METHODES = {"index", "lineaire"};

    public static class Resultat {
        public final int pos;
        public final double score;
        Resultat(int pos, double score) { this.pos = pos; this.score = score; }
    }

    public static class VecteurRequete {
        public final TreeMap<String, Double> poids = new TreeMap<>();
        public final List<String> tokens = new ArrayList<>();
    }

    private final Index index;
    private final Preprocesseur prepro;
    private final String schemaTf;
    public final Map<String, Double> idf = new HashMap<>();
    /** terme -> tableau [pos0, w0, pos1, w1, ...] sous forme de deux listes parallèles */
    private final Map<String, int[]> postPos = new HashMap<>();
    private final Map<String, double[]> postW = new HashMap<>();
    private final double[] norme2Doc;
    private final double[] normeDoc;
    private final int[] nbTermes;
    private List<Map<String, Double>> vecteurs;      // « index direct », construit à la demande

    private static double tf(int c, String schema, int longueur) {
        switch (schema) {
            case "raw": return c;
            case "log": return 1.0 + Math.log10(c);
            default:    return (double) c / longueur;     // norm
        }
    }

    public Moteur(Index index, Preprocesseur prepro, String schemaTf) {
        boolean ok = false;
        for (String s : SCHEMAS_TF) ok |= s.equals(schemaTf);
        if (!ok) throw new IllegalArgumentException("schéma TF inconnu : " + schemaTf);
        this.index = index; this.prepro = prepro; this.schemaTf = schemaTf;
        int n = index.n();
        norme2Doc = new double[n]; normeDoc = new double[n]; nbTermes = new int[n];
        for (Map.Entry<String, TreeMap<Integer, Integer>> e : index.postings.entrySet()) {   // ordre trié
            String t = e.getKey();
            double idft = Math.log10((double) n / e.getValue().size());
            idf.put(t, idft);
            int[] ps = new int[e.getValue().size()];
            double[] ws = new double[ps.length];
            int i = 0;
            for (Map.Entry<Integer, Integer> p : e.getValue().entrySet()) {
                double w = tf(p.getValue(), schemaTf, index.docs.get(p.getKey()).longueur) * idft;
                ps[i] = p.getKey(); ws[i] = w; i++;
                norme2Doc[p.getKey()] += w * w;
                nbTermes[p.getKey()]++;
            }
            postPos.put(t, ps); postW.put(t, ws);
        }
        for (int d = 0; d < n; d++) normeDoc[d] = Math.sqrt(norme2Doc[d]);
    }

    public String getSchemaTf() { return schemaTf; }
    public Preprocesseur getPrepro() { return prepro; }

    /** Vecteur TF-IDF de chaque document (pour le balayage linéaire et le résumé). */
    public List<Map<String, Double>> vecteursDocs() {
        if (vecteurs == null) {
            List<Map<String, Double>> v = new ArrayList<>();
            for (int i = 0; i < index.n(); i++) v.add(new HashMap<>());
            for (Map.Entry<String, int[]> e : postPos.entrySet()) {
                double[] ws = postW.get(e.getKey());
                int[] ps = e.getValue();
                for (int i = 0; i < ps.length; i++) v.get(ps[i]).put(e.getKey(), ws[i]);
            }
            vecteurs = v;
        }
        return vecteurs;
    }
    public Index getIndex() { return index; }

    public VecteurRequete vecteurRequete(String requete) {
        VecteurRequete v = new VecteurRequete();
        v.tokens.addAll(prepro.tokens(requete));
        TreeMap<String, Integer> comptes = new TreeMap<>();
        for (String t : v.tokens) if (idf.containsKey(t)) comptes.merge(t, 1, Integer::sum);
        for (Map.Entry<String, Integer> e : comptes.entrySet())
            v.poids.put(e.getKey(), tf(e.getValue(), schemaTf, v.tokens.size()) * idf.get(e.getKey()));
        return v;
    }

    public List<Resultat> rechercher(String requete, int k, String mesure) {
        return rechercher(requete, k, mesure, null, "index");
    }

    public List<Resultat> rechercher(String requete, int k, String mesure, Set<Integer> filtre, String methode) {
        boolean ok = false;
        for (String s : MESURES) ok |= s.equals(mesure);
        if (!ok) throw new IllegalArgumentException("mesure inconnue : " + mesure);
        if (!methode.equals("index") && !methode.equals("lineaire"))
            throw new IllegalArgumentException("méthode inconnue : " + methode);
        VecteurRequete q = vecteurRequete(requete);
        List<Resultat> res = new ArrayList<>();
        if (q.poids.isEmpty()) return res;
        int n = index.n();
        double q2 = 0.0;
        for (double w : q.poids.values()) q2 += w * w;
        int nq = q.poids.size();
        double[] prod = new double[n];
        int[] commun = new int[n];
        if (methode.equals("index")) {
            for (Map.Entry<String, Double> e : q.poids.entrySet()) {          // ordre trié
                int[] ps = postPos.get(e.getKey());
                double[] ws = postW.get(e.getKey());
                for (int i = 0; i < ps.length; i++) { prod[ps[i]] += e.getValue() * ws[i]; commun[ps[i]]++; }
            }
        } else {
            List<Map<String, Double>> vecs = vecteursDocs();
            for (int pos = 0; pos < n; pos++) {
                Map<String, Double> v = vecs.get(pos);
                double pr = 0.0;
                int ov = 0;
                for (Map.Entry<String, Double> e : q.poids.entrySet()) {
                    Double wd = v.get(e.getKey());
                    if (wd != null) { pr += e.getValue() * wd; ov++; }
                }
                prod[pos] = pr; commun[pos] = ov;
            }
        }
        for (int pos = 0; pos < n; pos++) {
            int ov = commun[pos];
            if (ov == 0) continue;
            if (filtre != null && !filtre.contains(pos)) continue;
            double s;
            switch (mesure) {
                case "cosinus": {
                    double den = Math.sqrt(q2) * normeDoc[pos];
                    s = den > 0 ? prod[pos] / den : 0.0;
                    break;
                }
                case "produit": s = prod[pos]; break;
                case "jaccard": s = (double) ov / (nq + nbTermes[pos] - ov); break;
                case "dice":    s = 2.0 * ov / (nq + nbTermes[pos]); break;
                default:        s = 1.0 / (1.0 + Math.sqrt(Math.max(0.0, q2 + norme2Doc[pos] - 2.0 * prod[pos])));
            }
            res.add(new Resultat(pos, s));
        }
        res.sort(Comparator.<Resultat>comparingDouble(r -> -r.score).thenComparingInt(r -> r.pos));
        return res.size() > k ? new ArrayList<>(res.subList(0, k)) : res;
    }
}
