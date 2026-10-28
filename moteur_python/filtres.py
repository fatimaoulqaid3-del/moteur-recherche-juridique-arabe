"""Filtres de recherche sur les métadonnées des décisions.

  section : numéro X de « رقم X/Y » (1 à 4)
  du / au : période (dates ISO AAAA-MM-JJ, bornes incluses)
  titre   : mot (ou fragment) qui doit figurer dans le titre de l'arrêt
Les documents sans date sont exclus dès qu'un filtre de date est actif.
"""
from preprocess import normaliser


def construire_filtre(index, section=None, du=None, au=None, titre=None):
    """Ensemble des positions autorisées, ou None si aucun filtre n'est actif."""
    if section is None and not du and not au and not titre:
        return None
    t = normaliser(titre) if titre else None
    autorises = set()
    for pos, d in enumerate(index.docs):
        if section is not None and d.section != str(section):
            continue
        if du and (not d.date or d.date < du):
            continue
        if au and (not d.date or d.date > au):
            continue
        if t and t not in normaliser(d.titre):
            continue
        autorises.add(pos)
    return autorises
