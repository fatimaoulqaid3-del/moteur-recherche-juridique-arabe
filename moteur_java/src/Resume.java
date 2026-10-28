import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;

/**
 * Résumé automatique extractif (même algorithme que la version Python) :
 * phrases du corps (. ؟ ! ؛) de ≥ 5 termes, score = somme des poids TF-IDF des termes distincts / racine(nb de termes),
 * termes de la requête comptés triple ; restitution des n meilleures phrases dans l'ordre du texte.
 */
public class Resume {
    private static final Pattern DOSSIER = Pattern.compile("\\d{4}/\\d+/\\d+/\\d+", Pattern.UNICODE_CHARACTER_CLASS);
    private static final String FIN_PHRASE = "[.\u061F!\u061B]+";

    static List<String> phrasesCorps(String texte) {
        List<String> L = Index.lignes(texte);
        int j = 3;
        for (int i = 0; i < Math.min(10, L.size()); i++) if (DOSSIER.matcher(L.get(i)).find()) { j = i; break; }
        String corps = String.join(" ", L.subList(Math.min(j + 1, L.size()), L.size())).replaceAll("(?U)\\s+", " ");
        List<String> res = new ArrayList<>();
        for (String p : corps.split(FIN_PHRASE)) {
            p = p.replaceAll("(?U)^\\s+|\\s+$", "");
            if (!p.isEmpty()) res.add(p);
        }
        return res;
    }

    private record Cand(int i, double score, String phrase) { }

    public static List<String> resumer(Moteur m, Path corpus, int pos, int n, String requete) throws IOException {
        Index.Doc d = m.getIndex().docs.get(pos);
        String texte = Files.readString(corpus.resolve(d.id + ".txt"), StandardCharsets.UTF_8);
        Map<String, Double> vec = m.vecteursDocs().get(pos);
        Set<String> termesQ = requete == null ? Set.of() : m.vecteurRequete(requete).poids.keySet();
        List<Cand> cands = new ArrayList<>();
        int i = 0;
        for (String ph : phrasesCorps(texte)) {
            List<String> toks = m.getPrepro().tokens(ph);
            if (toks.size() >= 5) {
                double s = 0.0;
                for (String t : new TreeSet<>(toks))
                    s += (termesQ.contains(t) ? 3.0 : 1.0) * vec.getOrDefault(t, 0.0);
                cands.add(new Cand(i, s / Math.sqrt(toks.size()), ph));
            }
            i++;
        }
        cands.sort(Comparator.<Cand>comparingDouble(c -> -c.score()).thenComparingInt(Cand::i));
        List<Cand> top = new ArrayList<>(cands.subList(0, Math.min(n, cands.size())));
        top.sort(Comparator.comparingInt(Cand::i));
        List<String> res = new ArrayList<>();
        for (Cand c : top) res.add(c.phrase());
        return res;
    }
}
