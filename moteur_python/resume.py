"""Résumé automatique extractif d'une décision.

1. Le corps du texte (après l'en-tête) est découpé en phrases (. ؟ ! ؛).
2. Chaque phrase (≥ 5 termes) reçoit le score  Σ poids TF-IDF des termes distincts / √(nb de termes),
   les poids étant ceux du document dans l'index. Si une requête est donnée, ses termes comptent triple
   (résumé orienté requête).
3. Les n meilleures phrases sont restituées dans l'ordre du texte.
"""
import math
import os
import re

_DOSSIER = re.compile(r'\d{4}/\d+/\d+/\d+')
_FIN_PHRASE = re.compile('[.\u061F!\u061B]+')


def phrases_corps(texte: str):
    L = [l.strip() for l in texte.splitlines() if l.strip()]
    j = next((i for i, l in enumerate(L[:10]) if _DOSSIER.search(l)), 3)
    corps = re.sub(r'\s+', ' ', ' '.join(L[j + 1:]))
    return [p.strip() for p in _FIN_PHRASE.split(corps) if p.strip()]


def resumer(moteur, dossier_corpus: str, pos: int, n: int = 3, requete: str = None):
    d = moteur.index.docs[pos]
    with open(os.path.join(dossier_corpus, d.id + '.txt'), encoding='utf-8') as f:
        texte = f.read()
    vec = moteur.vecteurs_docs()[pos]
    termes_q = set(moteur.vecteur_requete(requete)[0]) if requete else set()
    cands = []
    for i, ph in enumerate(phrases_corps(texte)):
        toks = moteur.prepro.tokens(ph)
        if len(toks) < 5:
            continue
        s = 0.0
        for t in sorted(set(toks)):
            s += (3.0 if t in termes_q else 1.0) * vec.get(t, 0.0)
        cands.append((i, s / math.sqrt(len(toks)), ph))
    top = sorted(cands, key=lambda x: (-x[1], x[0]))[:n]
    top.sort(key=lambda x: x[0])
    return [ph for _, _, ph in top]
