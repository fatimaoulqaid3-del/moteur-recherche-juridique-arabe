"""Évaluation indicative du moteur (précision@10 et MAP).

ATTENTION : pas de jugements humains disponibles. Un document est déclaré « pertinent »
si le TITRE de l'arrêt (chapeau éditorial) contient un mot-clé du thème. Le titre faisant
aussi partie du texte indexé, cette évaluation favorise un peu la recherche lexicale :
elle sert à COMPARER les configurations entre elles, pas à mesurer une performance absolue.

  python3 evaluer.py            -> affiche les tableaux et écrit ../resultats/evaluation.md
"""
import os

from indexation import construire
from moteur import Moteur, MESURES
from preprocess import Preprocesseur, normaliser

ICI = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(ICI, '..', 'corpus')
STOP = os.path.join(ICI, '..', 'ressources', 'stopwords_ar.txt')

# (requête, mots-clés du thème cherchés dans le titre)
THEMES = [
    ("نزاع التحفيظ والتعرض", ["تحفيظ"]),
    ("دعوى الإفراغ والطرد من المحل", ["إفراغ", "طرد"]),
    ("الشفعة", ["شفعة"]),
    ("قسمة التركة بين الورثة", ["قسمة", "ورثة", "إرث"]),
    ("الخبرة القضائية وسلطة المحكمة", ["خبرة"]),
    ("التقييد الاحتياطي", ["تقييد"]),
    ("اختصاص المحكمة", ["اختصاص"]),
    ("استحقاق العقار", ["استحقاق"]),
]


def pertinents(index, mots):
    ms = [normaliser(m) for m in mots]
    return {pos for pos, d in enumerate(index.docs) if any(m in normaliser(d.titre) for m in ms)}


def evaluer(moteur, mesure, k=10):
    p10, ap = [], []
    for requete, mots in THEMES:
        rel = pertinents(moteur.index, mots)
        res = moteur.rechercher(requete, 10_000, mesure)
        vus = hits = 0
        somme = 0.0
        for rang, (pos, _) in enumerate(res, 1):
            if pos in rel:
                hits += 1
                somme += hits / rang
            if rang == k:
                vus = hits
        p10.append(vus / k)
        ap.append(somme / len(rel) if rel else 0.0)
    return sum(p10) / len(p10), sum(ap) / len(ap)


def main():
    idx = {s: construire(CORPUS, Preprocesseur(STOP, s)) for s in ('none', 'light10')}
    lignes = ["# Évaluation indicative", "",
              "Pertinence = le titre de l'arrêt contient un mot-clé du thème (voir `evaluer.py`).", "",
              "Thèmes : " + " ; ".join(f"« {q} » ({len(pertinents(idx['light10'], m))} docs pertinents)" for q, m in THEMES), "",
              "## 1. Stemming × mesure de similarité (TF = log)", "",
              "| Stemming | Mesure | P@10 | MAP |", "|---|---|---|---|"]
    for s in ('none', 'light10'):
        for m in MESURES:
            p, a = evaluer(Moteur(idx[s], Preprocesseur(STOP, s), 'log'), m)
            lignes.append(f"| {s} | {m} | {p:.3f} | {a:.3f} |")
    lignes += ["", "## 2. Schéma TF (stemming = light10, mesure = cosinus)", "",
               "| TF | P@10 | MAP |", "|---|---|---|"]
    for tf in ('raw', 'log', 'norm'):
        p, a = evaluer(Moteur(idx['light10'], Preprocesseur(STOP, 'light10'), tf), 'cosinus')
        lignes.append(f"| {tf} | {p:.3f} | {a:.3f} |")
    txt = "\n".join(lignes) + "\n"
    print(txt)
    with open(os.path.join(ICI, '..', 'resultats', 'evaluation.md'), 'w', encoding='utf-8') as f:
        f.write(txt)


if __name__ == '__main__':
    main()
