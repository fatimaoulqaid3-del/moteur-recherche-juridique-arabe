"""Mesure de l'apport de l'index inversé.

  A. Sans index   : à chaque requête on relit et on re-prétraite tout le corpus, on recalcule TF-IDF
  B. Balayage     : vecteurs TF-IDF des documents en mémoire, mais on parcourt TOUS les documents
  C. Index inversé: on ne parcourt que les listes de postings des termes de la requête
"""
import statistics
import time

from indexation import construire
from moteur import Moteur
from preprocess import Preprocesseur


def _mesurer(f, repetitions):
    t = []
    for _ in range(repetitions):
        t0 = time.perf_counter()
        f()
        t.append((time.perf_counter() - t0) * 1000)
    return statistics.mean(t)


def lancer(corpus, stop, fichier_requetes, rep_a=3, rep_bc=300):
    with open(fichier_requetes, encoding='utf-8') as f:
        requetes = [l.strip() for l in f if l.strip()]
    prepro = Preprocesseur(stop, 'light10')
    moteur = Moteur(construire(corpus, prepro), prepro, 'log')
    moteur.vecteurs_docs()

    # les trois méthodes doivent donner exactement les mêmes résultats
    ok = all(moteur.rechercher(q, 10, m, None, 'index') == moteur.rechercher(q, 10, m, None, 'lineaire')
             for q in requetes for m in ('cosinus', 'jaccard', 'euclidienne'))

    def sans_index(q):
        p = Preprocesseur(stop, 'light10')            # cache de stemming vide : tout est recalculé
        Moteur(construire(corpus, p), p, 'log').rechercher(q, 10, 'cosinus')

    ta = statistics.mean(_mesurer(lambda q=q: sans_index(q), 1) for q in requetes[:rep_a])
    tb = statistics.mean(_mesurer(lambda q=q: moteur.rechercher(q, 10, 'cosinus', None, 'lineaire'), rep_bc)
                         for q in requetes)
    tc = statistics.mean(_mesurer(lambda q=q: moteur.rechercher(q, 10, 'cosinus', None, 'index'), rep_bc)
                         for q in requetes)
    print(f"Corpus : {moteur.index.n} documents, {len(moteur.index.postings)} termes, {len(requetes)} requêtes")
    print(f"Résultats identiques entre les méthodes : {'oui' if ok else 'NON'}")
    print(f"A. Sans index (tout recalculer)   : {ta:10.3f} ms / requête")
    print(f"B. Balayage de tous les documents : {tb:10.3f} ms / requête")
    print(f"C. Index inversé                  : {tc:10.3f} ms / requête")
    print(f"Accélération C vs A : x{ta / tc:,.0f}   |   C vs B : x{tb / tc:,.1f}")
