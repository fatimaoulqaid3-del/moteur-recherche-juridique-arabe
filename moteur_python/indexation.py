"""Construction, sauvegarde et chargement de l'index inversé.

Format de fichier (TSV, partagé avec la version Java) :
    #STEMMING <none|light10>
    D <position> <id_document> <longueur_en_termes> <date_ISO> <section> <titre>
    T <terme> <pos>:<tf_brut>,<pos>:<tf_brut>,...
"""
import os
import re

from preprocess import normaliser
from dataclasses import dataclass


@dataclass
class Doc:
    id: str
    titre: str
    longueur: int          # nombre de termes (après prétraitement)
    date: str = ''         # AAAA-MM-JJ (vide si introuvable)
    section: str = ''      # X de « رقم X/Y » (vide si introuvable)


class Index:
    def __init__(self, stemming: str):
        self.stemming = stemming
        self.docs = []                 # list[Doc]
        self.postings = {}             # terme -> {position_doc: tf_brut}

    @property
    def n(self) -> int:
        return len(self.docs)


def _titre(texte: str) -> str:
    """Titre = « رقم X/Y - sujet de l'arrêt » (l'en-tête varie d'un document à l'autre)."""
    L = [l.strip() for l in texte.splitlines() if l.strip()]
    tete = L[:10]
    m = re.search(r'رقم\s*(\d+\s*/\s*\d+)', ' '.join(tete))
    numero = 'رقم ' + re.sub(r'\s', '', m.group(1)) if m else ''
    i_dec = next((i for i, l in enumerate(L[:6]) if l.startswith('قرار محكمة النقض')), -1)
    avant = [l for l in L[:max(i_dec, 0)] if len(l) > 2]
    j = next((i for i, l in enumerate(tete) if re.search(r'\d{4}/\d+/\d+/\d+', l)), -1)
    apres = L[j + 1] if 0 <= j < len(L) - 1 else ''
    sujet = ' '.join(avant) if avant else apres
    if len(sujet) < 5:                      # repli : première longue ligne du texte
        sujet = next((l for l in L if len(l) > 40), '')
    t = (numero + ' - ' + sujet) if numero else sujet
    return re.sub(r'\s+', ' ', t).strip()[:140]


_MOIS = {'يناير': 1, 'جانفي': 1, 'فبراير': 2, 'مارس': 3, 'ابريل': 4, 'مايو': 5, 'ماي': 5,
         'يونيو': 6, 'يونيه': 6, 'يوليوز': 7, 'يوليو': 7, 'غشت': 8, 'اغسطس': 8, 'شتنبر': 9,
         'سبتمبر': 9, 'اكتوبر': 10, 'نونبر': 11, 'نوفمبر': 11, 'دجنبر': 12, 'ديسمبر': 12}


def _metadonnees(texte: str):
    """(date ISO, section) lues dans l'en-tête ; chaînes vides si absentes."""
    tete = ' '.join([l.strip() for l in texte.splitlines() if l.strip()][:10])
    date = section = ''
    m = re.search(r'بتاريخ\s*(\d{1,2})\s+([^\s\d]+)\s+(\d{4})', tete)
    if m and normaliser(m.group(2)) in _MOIS:
        date = f"{m.group(3)}-{_MOIS[normaliser(m.group(2))]:02d}-{int(m.group(1)):02d}"
    s = re.search(r'رقم\s*(\d{1,2})\s*/\s*\d+', tete)
    if s:
        section = s.group(1)
    return date, section


def _cle(nom: str):
    base = nom[:-4]
    return (0, int(base)) if base.isdigit() else (1, base)


def construire(dossier: str, prepro) -> Index:
    idx = Index(prepro.stemming)
    fichiers = sorted((f for f in os.listdir(dossier) if f.endswith('.txt')), key=_cle)
    for nom in fichiers:
        with open(os.path.join(dossier, nom), encoding='utf-8') as f:
            texte = f.read()
        tokens = prepro.tokens(texte)
        if not tokens:                       # fichier vide : ignoré (ne compte pas dans N)
            continue
        pos = len(idx.docs)
        date, section = _metadonnees(texte)
        idx.docs.append(Doc(nom[:-4], _titre(texte), len(tokens), date, section))
        for t in tokens:
            p = idx.postings.setdefault(t, {})
            p[pos] = p.get(pos, 0) + 1
    return idx


def sauver(idx: Index, chemin: str) -> None:
    with open(chemin, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f"#STEMMING\t{idx.stemming}\n")
        for pos, d in enumerate(idx.docs):
            f.write(f"D\t{pos}\t{d.id}\t{d.longueur}\t{d.date}\t{d.section}\t{d.titre}\n")
        for t in sorted(idx.postings):
            p = idx.postings[t]
            f.write("T\t" + t + "\t" + ",".join(f"{k}:{p[k]}" for k in sorted(p)) + "\n")


def charger(chemin: str) -> Index:
    idx = None
    with open(chemin, encoding='utf-8') as f:
        for ligne in f:
            ligne = ligne.rstrip('\n')
            c = ligne.split('\t')
            if c[0] == '#STEMMING':
                idx = Index(c[1])
            elif c[0] == 'D':
                idx.docs.append(Doc(c[2], c[6], int(c[3]), c[4], c[5]))
            elif c[0] == 'T':
                idx.postings[c[1]] = {int(a): int(b) for a, b in
                                      (x.split(':') for x in c[2].split(','))}
    return idx
