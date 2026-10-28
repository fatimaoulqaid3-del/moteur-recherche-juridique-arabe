import java.util.HashSet;
import java.util.Set;

/**
 * Filtres de recherche sur les métadonnées des décisions.
 *   section : numéro X de « رقم X/Y » (1 à 4) ; du / au : période ISO AAAA-MM-JJ (bornes incluses) ;
 *   titre : mot (ou fragment) qui doit figurer dans le titre.
 * Les documents sans date sont exclus dès qu'un filtre de date est actif.
 */
public class Filtres {
    /** Positions autorisées, ou null si aucun filtre n'est actif. */
    public static Set<Integer> construire(Index index, Integer section, String du, String au, String titre) {
        if (section == null && du == null && au == null && titre == null) return null;
        String t = titre == null ? null : Preprocesseur.normaliser(titre);
        Set<Integer> ok = new HashSet<>();
        for (int pos = 0; pos < index.n(); pos++) {
            Index.Doc d = index.docs.get(pos);
            if (section != null && !d.section.equals(String.valueOf(section))) continue;
            if (du != null && (d.date.isEmpty() || d.date.compareTo(du) < 0)) continue;
            if (au != null && (d.date.isEmpty() || d.date.compareTo(au) > 0)) continue;
            if (t != null && !Preprocesseur.normaliser(d.titre).contains(t)) continue;
            ok.add(pos);
        }
        return ok;
    }
}
