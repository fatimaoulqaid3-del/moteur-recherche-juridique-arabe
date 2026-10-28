"""Interface en ligne de commande du moteur de recherche (version Python).

  python3 main.py indexer    [--corpus ../corpus] [--index ...] [--stemming light10|none]
  python3 main.py rechercher "عقد البيع" [-k 10] [--mesure cosinus] [--tf log]
                             [--section 2] [--du 2023-02-01] [--au 2023-03-31] [--titre تحفيظ]
                             [--resume 2] [--methode index|lineaire]
  python3 main.py interactif [mêmes options]
  python3 main.py fichier requetes.txt [mêmes options]      (une requête par ligne, UTF-8)
  python3 main.py resumer 954 [-n 3] [--requete "الشفعة"]   (résumé automatique d'une décision)
  python3 main.py benchmark                                 (index inversé vs sans index)
  python3 main.py chi2 [\"requête\"] [-n 15] [--min-df 3] [-k 10] [filtres]
        sans requête ni filtre : termes caractéristiques de chaque section (chi2) ;
        avec filtres (--titre, --section, --du, --au) : termes caractéristiques des décisions filtrées ;
        avec une requête : termes caractéristiques des k premiers résultats.
"""
import argparse
import os
import sys
import time

from filtres import construire_filtre
from indexation import construire, sauver, charger
from moteur import Moteur, MESURES, SCHEMAS_TF, METHODES
from preprocess import Preprocesseur
from resume import resumer
from statistiques import formater, par_section, termes_caracteristiques

ICI = os.path.dirname(os.path.abspath(__file__))
STOP = os.path.join(ICI, '..', 'ressources', 'stopwords_ar.txt')


def court(txt, n=260):
    return txt if len(txt) <= n else txt[:n].rstrip() + '…'


def afficher(moteur, requete, a, filtre):
    t0 = time.perf_counter()
    q, _ = moteur.vecteur_requete(requete)
    res = moteur.rechercher(requete, a.k, a.mesure, filtre, a.methode)
    dt = (time.perf_counter() - t0) * 1000
    print("Termes de la requête (après prétraitement) : " +
          ", ".join(f"{t} (idf={moteur.idf[t]:.3f})" for t in q) if q else "Aucun terme connu.")
    if filtre is not None:
        print(f"Filtres actifs : {len(filtre)} document(s) autorisé(s)")
    print(f"Mesure = {a.mesure} | TF = {moteur.schema_tf} | {len(res)} résultat(s) en {dt:.1f} ms")
    for rang, (pos, s) in enumerate(res, 1):
        d = moteur.index.docs[pos]
        print(f"{rang:>2}. [{s:.6f}] doc {d.id:>6} | {d.titre}")
        if a.resume:
            for ph in resumer(moteur, a.corpus, pos, a.resume, requete):
                print("      • " + court(ph))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('commande', choices=['indexer', 'rechercher', 'interactif', 'fichier', 'resumer', 'benchmark', 'chi2'])
    ap.add_argument('requete', nargs='?')
    ap.add_argument('--corpus', default=os.path.join(ICI, '..', 'corpus'))
    ap.add_argument('--index', default=os.path.join(ICI, '..', 'resultats', 'index_py.tsv'))
    ap.add_argument('--stemming', default='light10', choices=['none', 'light10'])
    ap.add_argument('-k', type=int, default=10)
    ap.add_argument('-n', type=int, default=None, help="resumer : nb de phrases (défaut 3) ; chi2 : nb de termes (défaut 15)")
    ap.add_argument('--mesure', default='cosinus', choices=MESURES)
    ap.add_argument('--tf', default='log', choices=SCHEMAS_TF)
    ap.add_argument('--methode', default='index', choices=METHODES)
    ap.add_argument('--min-df', type=int, default=3, help="chi2 : nb minimal de documents de la classe contenant le terme")
    ap.add_argument('--section', type=int)
    ap.add_argument('--du')
    ap.add_argument('--au')
    ap.add_argument('--titre')
    ap.add_argument('--resume', type=int, default=0, help="affiche un résumé de N phrases sous chaque résultat")
    a = ap.parse_args()
    if a.n is None:
        a.n = 15 if a.commande == 'chi2' else 3
    if a.commande == 'resumer':
        a.requete_resume = None

    if a.commande == 'indexer':
        t0 = time.perf_counter()
        idx = construire(a.corpus, Preprocesseur(STOP, a.stemming))
        sauver(idx, a.index)
        print(f"{idx.n} documents, {len(idx.postings)} termes, stemming={a.stemming} "
              f"-> {a.index} ({time.perf_counter() - t0:.2f} s)")
        return

    if a.commande == 'benchmark':
        import benchmark
        benchmark.lancer(a.corpus, STOP, a.requete or os.path.join(ICI, '..', 'requetes_test.txt'))
        return

    idx = charger(a.index)
    moteur = Moteur(idx, Preprocesseur(STOP, idx.stemming), a.tf)
    filtre = construire_filtre(idx, a.section, a.du, a.au, a.titre)

    if a.commande == 'resumer':
        pos = next((i for i, d in enumerate(idx.docs) if d.id == a.requete), None)
        if pos is None:
            sys.exit(f"Document inconnu : {a.requete}")
        d = idx.docs[pos]
        print(f"Doc {d.id} | {d.date} | section {d.section} | {d.titre}")
        for ph in resumer(moteur, a.corpus, pos, a.n, None):
            print("  • " + court(ph, 400))
    elif a.commande == 'chi2':
        if a.requete:                                   # classe = k premiers résultats de la requête
            res = moteur.rechercher(a.requete, a.k, a.mesure, filtre, a.methode)
            classe = {pos for pos, _ in res}
            titre = f"Top-{a.k} de « {a.requete} »"
            L = formater(titre, len(classe), idx.n, termes_caracteristiques(idx, classe, None, a.n, a.min_df))
        elif filtre is not None:                        # classe = décisions retenues par les filtres
            L = formater("Décisions filtrées", len(filtre), idx.n,
                         termes_caracteristiques(idx, filtre, None, a.n, a.min_df))
        else:                                           # une analyse par section
            L = []
            for s, nc, nu, termes in par_section(idx, a.n, a.min_df):
                L += formater(f"Section {s}", nc, nu, termes)
        print("\n".join(L))
    elif a.commande == 'rechercher':
        if not a.requete:
            sys.exit("Donnez une requête.")
        afficher(moteur, a.requete, a, filtre)
    elif a.commande == 'fichier':
        with open(a.requete, encoding='utf-8') as f:
            for l in f:
                if l.strip():
                    print("===", l.strip())
                    afficher(moteur, l.strip(), a, filtre)
    else:
        print("Requête (vide pour quitter) :")
        while True:
            try:
                r = input("> ").strip()
            except EOFError:
                break
            if not r:
                break
            afficher(moteur, r, a, filtre)


if __name__ == '__main__':
    main()
