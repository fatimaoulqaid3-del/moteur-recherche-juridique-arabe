"""Moteur de recherche : TF, IDF, TF-IDF, mesures de similarité, filtres.

  idf(t)      = log10(N / df(t))
  tf(t,d)     = 'raw'  : c                (nombre d'occurrences)
                'log'  : 1 + log10(c)     (sublinéaire, défaut)
                'norm' : c / |d|          (fréquence relative)
  poids(t,d)  = tf(t,d) * idf(t)
  cosinus     = (q.d) / (|q| |d|)
  produit     = q.d
  jaccard     = |Q ∩ D| / |Q ∪ D|          (ensembles de termes)
  dice        = 2 |Q ∩ D| / (|Q| + |D|)
  euclidienne = 1 / (1 + ||q - d||)         (similarité dérivée de la distance)

Deux stratégies de recherche (mêmes résultats) :
  'index'    : parcours des listes de postings des termes de la requête (index inversé)
  'lineaire' : balayage du vecteur de chaque document (sans index inversé)
"""
import math

MESURES = ('cosinus', 'produit', 'jaccard', 'dice', 'euclidienne')
SCHEMAS_TF = ('raw', 'log', 'norm')
METHODES = ('index', 'lineaire')


def _tf(c: int, schema: str, longueur: int) -> float:
    if schema == 'raw':
        return float(c)
    if schema == 'log':
        return 1.0 + math.log10(c)
    return c / longueur            # 'norm'


class Moteur:
    def __init__(self, index, prepro, schema_tf: str = 'log'):
        if schema_tf not in SCHEMAS_TF:
            raise ValueError(f"schéma TF inconnu : {schema_tf}")
        self.index, self.prepro, self.schema_tf = index, prepro, schema_tf
        n = index.n
        self.idf = {t: math.log10(n / len(p)) for t, p in index.postings.items()}
        self.poids = {}                       # terme -> [(pos_doc, poids)]
        norme2 = [0.0] * n
        nb_termes = [0] * n
        for t in sorted(index.postings):
            liste = []
            for pos in sorted(index.postings[t]):
                w = _tf(index.postings[t][pos], schema_tf, index.docs[pos].longueur) * self.idf[t]
                liste.append((pos, w))
                norme2[pos] += w * w
                nb_termes[pos] += 1
            self.poids[t] = liste
        self.norme_doc = [math.sqrt(x) for x in norme2]
        self.norme2_doc = norme2
        self.nb_termes = nb_termes
        self._vecteurs = None

    # -- vecteurs des documents (index « direct », construit à la demande) --------
    def vecteurs_docs(self):
        if self._vecteurs is None:
            v = [dict() for _ in range(self.index.n)]
            for t, liste in self.poids.items():
                for pos, w in liste:
                    v[pos][t] = w
            self._vecteurs = v
        return self._vecteurs

    # -- vecteur de la requête ------------------------------------------------
    def vecteur_requete(self, requete: str):
        tokens = self.prepro.tokens(requete)
        comptes = {}
        for t in tokens:
            if t in self.idf:               # termes inconnus du corpus ignorés
                comptes[t] = comptes.get(t, 0) + 1
        vec = {t: _tf(c, self.schema_tf, len(tokens)) * self.idf[t]
               for t, c in sorted(comptes.items())}
        return vec, tokens

    # -- recherche ---------------------------------------------------------------
    def rechercher(self, requete: str, k: int = 10, mesure: str = 'cosinus',
                   filtre=None, methode: str = 'index'):
        if mesure not in MESURES:
            raise ValueError(f"mesure inconnue : {mesure}")
        if methode not in METHODES:
            raise ValueError(f"méthode inconnue : {methode}")
        q, _ = self.vecteur_requete(requete)
        if not q:
            return []
        n = self.index.n
        q2 = sum(w * w for w in q.values())
        nq = len(q)
        candidats = []                      # (pos, produit scalaire, termes communs)
        if methode == 'index':
            prod = [0.0] * n
            commun = [0] * n
            for t, wq in q.items():         # ordre trié = résultats reproductibles
                for pos, wd in self.poids[t]:
                    prod[pos] += wq * wd
                    commun[pos] += 1
            candidats = [(p, prod[p], commun[p]) for p in range(n) if commun[p] > 0]
        else:
            vecs = self.vecteurs_docs()
            for pos in range(n):
                v = vecs[pos]
                pr, ov = 0.0, 0
                for t, wq in q.items():
                    wd = v.get(t)
                    if wd is not None:
                        pr += wq * wd
                        ov += 1
                if ov > 0:
                    candidats.append((pos, pr, ov))
        scores = []
        for pos, pr, ov in candidats:
            if filtre is not None and pos not in filtre:
                continue
            if mesure == 'cosinus':
                den = math.sqrt(q2) * self.norme_doc[pos]
                s = pr / den if den > 0 else 0.0
            elif mesure == 'produit':
                s = pr
            elif mesure == 'jaccard':
                s = ov / (nq + self.nb_termes[pos] - ov)
            elif mesure == 'dice':
                s = 2.0 * ov / (nq + self.nb_termes[pos])
            else:
                s = 1.0 / (1.0 + math.sqrt(max(0.0, q2 + self.norme2_doc[pos] - 2.0 * pr)))
            scores.append((pos, s))
        scores.sort(key=lambda x: (-x[1], x[0]))
        return scores[:k]
