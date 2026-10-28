"""Statistique du chi-deux (chi2) pour la sélection de termes caractéristiques.

Pour un terme t et une classe de documents C (dans un ensemble de référence U), on construit le
tableau de contingence 2x2 (présence du terme = au moins une occurrence dans le document) :

                      t présent   t absent
      dans C             A           C'          A + C' = |C|
      hors C (U \\ C)     B           D           B + D = |U| - |C|

      chi2(t, C) = N (A D - B C')^2 / [ (A+B) (C'+D) (A+C') (B+D) ]        N = |U|, 1 degré de liberté

Plus chi2 est grand, plus le terme et la classe sont liés. Seuils (1 ddl) : 3,84 -> p < 0,05 (*) ;
6,63 -> p < 0,01 (**) ; 10,83 -> p < 0,001 (***).
On ne garde que les associations POSITIVES (terme sur-représenté dans la classe, A D > B C') et
les termes présents dans au moins `min_df` documents de la classe (chi2 peu fiable sinon).

Deux usages :
  - classe = une section (1 à 4)         -> vocabulaire caractéristique de chaque section ;
  - classe = les k premiers résultats    -> termes qui distinguent les résultats d'une requête
                                            du reste du corpus (aide à reformuler la requête).
"""

SEUILS = ((10.83, '***'), (6.63, '**'), (3.84, '*'))


def niveau(x: float) -> str:
    for s, etoiles in SEUILS:
        if x >= s:
            return etoiles
    return ''


def chi2(a: int, b: int, c: int, d: int) -> float:
    """chi2 du tableau [[a, c], [b, d]] (a = classe & terme, b = hors classe & terme, c = classe sans terme)."""
    den = (a + b) * (c + d) * (a + c) * (b + d)
    if den == 0:
        return 0.0
    n = a + b + c + d
    return n * (a * d - b * c) ** 2 / den


def termes_caracteristiques(index, classe, univers=None, n: int = 15, min_df: int = 3):
    """[(terme, chi2, df_classe, df_univers)] trié par chi2 décroissant puis terme ; n meilleurs."""
    univers = set(range(index.n)) if univers is None else set(univers)
    classe = set(classe) & univers
    taille, nc = len(univers), len(classe)
    res = []
    for terme, p in index.postings.items():
        a = sum(1 for pos in p if pos in classe)
        if a < min_df:
            continue
        tot = sum(1 for pos in p if pos in univers)
        b, c = tot - a, nc - a
        d = taille - nc - b
        if a * d - b * c <= 0:               # association négative ou nulle : ignorée
            continue
        res.append((terme, chi2(a, b, c, d), a, tot))
    res.sort(key=lambda x: (-x[1], x[0]))
    return res[:n]


def classes_par_section(index):
    """{section: ensemble de positions} pour les décisions dont la section est connue."""
    cl = {}
    for pos, d in enumerate(index.docs):
        if d.section:
            cl.setdefault(d.section, set()).add(pos)
    return dict(sorted(cl.items()))


def par_section(index, n: int = 15, min_df: int = 3):
    """[(section, taille_classe, taille_univers, [termes...])] ; l'univers = décisions avec section connue."""
    cl = classes_par_section(index)
    univers = set().union(*cl.values()) if cl else set()
    return [(s, len(c), len(univers), termes_caracteristiques(index, c, univers, n, min_df))
            for s, c in cl.items()]


def formater(titre: str, taille_classe: int, taille_univers: int, termes) -> list:
    """Lignes de texte identiques en Python et en Java (utilisées pour la comparaison)."""
    L = [f"{titre} : {taille_classe} décision(s) dans la classe / {taille_univers} dans l'univers"]
    if not termes:
        L.append("  (aucun terme significatif)")
    for i, (t, x, a, tot) in enumerate(termes, 1):
        L.append(f"  {i:>2}. chi2={x:>9.4f} {niveau(x):<3} df_classe={a:>3} df_total={tot:>3} | {t}")
    return L
