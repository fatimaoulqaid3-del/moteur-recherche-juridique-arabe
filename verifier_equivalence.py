"""Vérifie que les versions Python et Java donnent exactement les mêmes résultats.

  python3 verifier_equivalence.py [chemin/vers/SAFAR_v2_jar.zip]
Compare, pour chaque requête de requetes_test.txt, chaque mesure et chaque schéma TF,
le classement (documents) et les scores (6 décimales) du top 10 ; puis les filtres, la méthode
« balayage » (sans index inversé) et le résumé automatique.
"""
import itertools
import os
import re
import subprocess
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
SAFAR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ICI, 'SAFAR_v2_jar.zip')
REQ = os.path.join(ICI, 'requetes_test.txt')
MESURES = ['cosinus', 'produit', 'jaccard', 'dice', 'euclidienne']
TFS = ['raw', 'log', 'norm']


def nettoyer(sortie):
    return [re.sub(r' en [\d.,]+ ms$', '', l) for l in sortie.splitlines()]


def lancer(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding='utf-8', check=True).stdout


total = ok = 0


def comparer(titre, args_communs, commande='fichier', cible=REQ):
    """Lance Python et Java avec les mêmes arguments et compare les sorties (hors temps d'exécution)."""
    global total, ok
    cible_l = [cible] if cible is not None else []          # chi2 sans requête : pas d'argument
    py = lancer(['python3', 'main.py', commande] + cible_l + ['--index', '../resultats/index_py.tsv'] + args_communs,
                os.path.join(ICI, 'moteur_python'))
    jv = lancer(['java', '-Dfile.encoding=UTF-8', '-Dsun.jnu.encoding=UTF-8', '-cp', f'{SAFAR}{os.pathsep}out', 'Main',
                 commande] + cible_l + ['--index', '../resultats/index_java.tsv'] + args_communs,
                os.path.join(ICI, 'moteur_java'))
    a, b = nettoyer(py), nettoyer(jv)
    total += 1
    if a == b:
        ok += 1
        print(f"OK   {titre} ({len(a)} lignes identiques)")
    else:
        print(f"DIFF {titre}")
        for x, y in zip(a, b):
            if x != y:
                print('  PY  :', x); print('  JAVA:', y); break


for mesure, tf in itertools.product(MESURES, TFS):
    comparer(f"mesure={mesure:<11} tf={tf:<4}", ['--mesure', mesure, '--tf', tf, '-k', '10'])
comparer("filtre section=2", ['--section', '2', '-k', '10'])
comparer("filtre période 2023-02-01 → 2023-03-15", ['--du', '2023-02-01', '--au', '2023-03-15', '-k', '10'])
comparer("filtre titre=تحفيظ + section=1", ['--titre', 'تحفيظ', '--section', '1', '-k', '10'])
comparer("méthode balayage (sans index inversé)", ['--methode', 'lineaire', '-k', '10', '--mesure', 'jaccard'])
comparer("résumé automatique sous les résultats", ['--resume', '2', '-k', '3'])
for doc in ('954', '8', '241', '1298', '36'):
    comparer(f"commande resumer {doc}", ['-n', '3'], 'resumer', doc)
# --- statistique du chi-deux (chi2)
comparer("chi2 par section (4 sections)", ['-n', '15'], 'chi2', None)
comparer("chi2 par section, min-df 1, 40 termes", ['-n', '40', '--min-df', '1'], 'chi2', None)
comparer("chi2 décisions filtrées (titre=تحفيظ)", ['--titre', 'تحفيظ', '-n', '20'], 'chi2', None)
comparer("chi2 décisions filtrées (section 2 + période)", ['--section', '2', '--du', '2023-02-01', '--au', '2023-03-31'], 'chi2', None)
for requete in ('الشفعة', 'عقد البيع', 'القسمة بين الورثة'):
    comparer(f"chi2 top-10 de « {requete} »", ['-k', '10', '-n', '15'], 'chi2', requete)
comparer("chi2 top-20, produit scalaire, tf=raw", ['-k', '20', '--mesure', 'produit', '--tf', 'raw'], 'chi2', 'الرهن الرسمي')
print(f"\n{ok}/{total} comparaisons strictement identiques entre Python et Java")
