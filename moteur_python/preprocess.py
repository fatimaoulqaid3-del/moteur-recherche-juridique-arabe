"""Prétraitement du texte arabe (identique côté Python et côté Java).

Chaîne de traitement :
  1. suppression des diacritiques (tashkîl) et du tatwîl ;
  2. tokenisation : suites de lettres arabes (chiffres, ponctuation, latin ignorés) ;
  3. normalisation : ى -> ي ; ء آ أ ؤ إ ئ -> ا ;
  4. suppression des mots vides et des mots d'une seule lettre ;
  5. (option) racinisation « light stemming » = Light10Stemmer de SAFAR.
"""
import re
from functools import lru_cache

from light10 import stem as _light10

_DIACRITIQUES = re.compile('[\u064B-\u0652\u0670\u0640]')
_TOKEN = re.compile('[\u0621-\u064A]+')
_HAMZA = re.compile('[ءآأؤإئ]')


def normaliser(mot: str) -> str:
    return _HAMZA.sub('ا', mot.replace('ى', 'ي'))


class Preprocesseur:
    def __init__(self, chemin_stopwords: str, stemming: str = 'light10'):
        if stemming not in ('none', 'light10'):
            raise ValueError("stemming doit valoir 'none' ou 'light10'")
        self.stemming = stemming
        with open(chemin_stopwords, encoding='utf-8') as f:
            self.stop = {normaliser(l.strip()) for l in f if l.strip()}
        self._cache = lru_cache(maxsize=None)(self._traiter_mot)

    def _traiter_mot(self, mot: str):
        n = normaliser(mot)
        if len(n) < 2 or n in self.stop:
            return None
        s = _light10(mot) if self.stemming == 'light10' else n
        if len(s) < 2 or s in self.stop:
            return None
        return s

    def tokens(self, texte: str) -> list:
        texte = _DIACRITIQUES.sub('', texte)
        res = []
        for mot in _TOKEN.findall(texte):
            s = self._cache(mot)
            if s is not None:
                res.append(s)
        return res
