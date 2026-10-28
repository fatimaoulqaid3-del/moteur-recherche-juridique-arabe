"""Site web du moteur de recherche (Python standard uniquement, aucune installation).

    python3 app.py            puis ouvrir  http://localhost:8000
    python3 app.py 9000       pour choisir un autre port

Les recherches sont exécutées par DEUX moteurs indépendants et affichées côte à côte :
  - le moteur Python (moteur_python/), chargé dans ce processus ;
  - le moteur Java (moteur_java/), lancé en processus persistant (commande `Main serveur`).
Pour activer la colonne Java : JDK 17+ et SAFAR_v2_jar.zip à la racine du projet
(ou variable d'environnement SAFAR_JAR = chemin du jar). Sans Java, le site fonctionne avec Python seul.

Pages : /  recherche  ·  /chi2  statistique du chi-deux  ·  /doc?id=…  texte d'une décision
"""
import glob
import html
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.normpath(os.path.join(ICI, '..'))
sys.path.insert(0, os.path.join(RACINE, 'moteur_python'))

import time                                                    # noqa: E402
from filtres import construire_filtre                          # noqa: E402
from indexation import charger, construire, sauver             # noqa: E402
from moteur import Moteur, MESURES, SCHEMAS_TF                 # noqa: E402
from preprocess import Preprocesseur                           # noqa: E402
from resume import resumer                                     # noqa: E402
from statistiques import niveau, par_section, termes_caracteristiques  # noqa: E402

CORPUS = os.path.join(RACINE, 'corpus')
STOP = os.path.join(RACINE, 'ressources', 'stopwords_ar.txt')
INDEX = os.path.join(RACINE, 'resultats', 'index_py.tsv')
INDEX_JAVA = os.path.join(RACINE, 'resultats', 'index_java.tsv')
REQUETES = os.path.join(RACINE, 'requetes_test.txt')

if os.path.exists(INDEX):
    IDX = charger(INDEX)
else:
    IDX = construire(CORPUS, Preprocesseur(STOP, 'light10'))
    sauver(IDX, INDEX)
MOTEURS = {tf: Moteur(IDX, Preprocesseur(STOP, IDX.stemming), tf) for tf in SCHEMAS_TF}
POS = {d.id: i for i, d in enumerate(IDX.docs)}
e = html.escape


# =====================================================================================
#  Pont vers le moteur Java (processus persistant : l'index n'est chargé qu'une fois)
# =====================================================================================
class PontJava:
    def __init__(self):
        self.proc, self.erreur, self.verrou = None, None, threading.Lock()
        self.dossier = os.path.join(RACINE, 'moteur_java')
        try:
            self._demarrer()
        except Exception as ex:                                # Java absent, jar manquant, erreur de compilation…
            self.erreur = str(ex)

    def _classpath(self):
        jar = os.environ.get('SAFAR_JAR')
        if not jar:
            trouves = sorted(glob.glob(os.path.join(RACINE, 'SAFAR*.zip')) + glob.glob(os.path.join(RACINE, 'SAFAR*.jar')))
            jar = trouves[0] if trouves else None
        if not jar:
            raise RuntimeError("SAFAR_v2_jar.zip introuvable (placez-le à la racine du projet ou définissez SAFAR_JAR)")
        return jar

    def _demarrer(self):
        jar = self._classpath()
        sortie = os.path.join(self.dossier, 'out')
        sources = glob.glob(os.path.join(self.dossier, 'src', '*.java'))
        classe = os.path.join(sortie, 'Serveur.class')
        if not os.path.exists(classe) or max(os.path.getmtime(s) for s in sources) > os.path.getmtime(classe):
            os.makedirs(sortie, exist_ok=True)
            r = subprocess.run(['javac', '-encoding', 'UTF-8', '-cp', jar, '-d', sortie] + sources,
                               capture_output=True, text=True, encoding='utf-8')
            if r.returncode != 0:
                raise RuntimeError("compilation Java impossible : " + (r.stderr or r.stdout)[:300])
        if not os.path.exists(INDEX_JAVA):
            raise RuntimeError("index Java absent : lancez  java -cp … Main indexer")
        self.proc = subprocess.Popen(
            ['java', '-Dfile.encoding=UTF-8', '-cp', jar + os.pathsep + sortie, 'Main', 'serveur',
             '--index', INDEX_JAVA, '--stopwords', STOP, '--corpus', CORPUS],
            cwd=self.dossier, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', bufsize=1)
        pret = self.proc.stdout.readline()
        if not pret.startswith('READY'):
            raise RuntimeError("le moteur Java ne démarre pas")

    @property
    def dispo(self):
        return self.proc is not None and self.proc.poll() is None

    def _appel(self, champs):
        if not self.dispo:
            raise RuntimeError(self.erreur or "moteur Java arrêté")
        ligne = '\t'.join(str(c).replace('\t', ' ').replace('\n', ' ').replace('\r', ' ') for c in champs)
        with self.verrou:
            self.proc.stdin.write(ligne + '\n')
            self.proc.stdin.flush()
            lignes = []
            while True:
                l = self.proc.stdout.readline()
                if l == '':
                    raise RuntimeError("le moteur Java s'est arrêté")
                l = l.rstrip('\n')
                if l == 'END':
                    return lignes
                lignes.append(l.split('\t'))

    def rechercher(self, q, k, mesure, tf, section, du, au, titre, nres):
        res = {'termes': [], 'nfiltre': None, 'ms': 0.0, 'res': []}
        for c in self._appel(['R', q, k, mesure, tf, section or '', du or '', au or '', titre or '', nres]):
            if c[0] == 'ERR':
                raise RuntimeError(c[1])
            elif c[0] == 'Q':
                res['termes'].append((c[1], float(c[2])))
            elif c[0] == 'F':
                res['nfiltre'] = int(c[1])
            elif c[0] == 'M':
                res['ms'] = float(c[1])
            elif c[0] == 'R':
                res['res'].append({'id': c[2], 'score': float(c[3]), 'date': c[4], 'section': c[5],
                                   'longueur': int(c[6]), 'titre': c[7], 'resume': []})
            elif c[0] == 'S':
                res['res'][-1]['resume'].append(c[1])
        return res

    def chi2(self, q, k, mesure, tf, n, min_df, section, du, au, titre):
        blocs = []
        for c in self._appel(['C', q, k, mesure, tf, n, min_df, section or '', du or '', au or '', titre or '']):
            if c[0] == 'ERR':
                raise RuntimeError(c[1])
            elif c[0] == 'H':
                blocs.append({'titre': c[1], 'nc': int(c[2]), 'nu': int(c[3]), 'termes': []})
            elif c[0] == 'T':
                blocs[-1]['termes'].append((c[1], float(c[2]), int(c[3]), int(c[4])))
        return blocs


JAVA = PontJava()


# =====================================================================================
#  Calculs côté Python (même interface de sortie que le pont Java)
# =====================================================================================
def entier(valeur, defaut, mini=0, maxi=1000):
    """Entier tiré d'un paramètre d'URL ; valeur invalide -> défaut ; borné pour éviter les abus."""
    try:
        return max(mini, min(maxi, int(valeur)))
    except (TypeError, ValueError):
        return defaut


def section_valide(v):
    """'' si la section n'est pas un entier (évite une erreur côté Java)."""
    n = entier(v, None) if v else None
    return '' if n is None else str(n)


def rechercher_py(q, k, mesure, tf, section, du, au, titre, nres):
    m = MOTEURS[tf]
    filtre = construire_filtre(IDX, entier(section, None) if section else None, du or None, au or None, titre or None)
    vec, _ = m.vecteur_requete(q)
    t0 = time.perf_counter()
    res = m.rechercher(q, k, mesure, filtre)
    ms = (time.perf_counter() - t0) * 1000
    sortie = {'termes': [(t, m.idf[t]) for t in vec], 'nfiltre': None if filtre is None else len(filtre),
              'ms': ms, 'res': []}
    for pos, s in res:
        d = IDX.docs[pos]
        sortie['res'].append({'id': d.id, 'score': s, 'date': d.date, 'section': d.section, 'longueur': d.longueur,
                              'titre': d.titre, 'resume': resumer(m, CORPUS, pos, nres, q) if nres else []})
    return sortie


def chi2_py(q, k, mesure, tf, n, min_df, section, du, au, titre):
    filtre = construire_filtre(IDX, entier(section, None) if section else None, du or None, au or None, titre or None)
    if q:
        classe = {pos for pos, _ in MOTEURS[tf].rechercher(q, k, mesure, filtre)}
        return [{'titre': f"Top-{k} de « {q} »", 'nc': len(classe), 'nu': IDX.n,
                 'termes': termes_caracteristiques(IDX, classe, None, n, min_df)}]
    if filtre is not None:
        return [{'titre': "Décisions filtrées", 'nc': len(filtre), 'nu': IDX.n,
                 'termes': termes_caracteristiques(IDX, filtre, None, n, min_df)}]
    return [{'titre': f"Section {s}", 'nc': nc, 'nu': nu, 'termes': t} for s, nc, nu, t in par_section(IDX, n, min_df)]


# =====================================================================================
#  Présentation
# =====================================================================================
CSS = """
:root{--bg:#f3f1ec;--carte:#fff;--texte:#1c2433;--doux:#5d6779;--bord:#e1ddd3;--marine:#0f2a43;--marine2:#17406a;
--or:#c49a3a;--py:#2f6fb3;--pyfond:#e6f0fb;--jv:#c8641a;--jvfond:#fcece0;--ok:#1d7a4b;--okfond:#e2f4ea;--ko:#b3261e;--kofond:#fbe9e7;
--ombre:0 1px 2px rgba(15,42,67,.06),0 6px 18px rgba(15,42,67,.06)}
@media(prefers-color-scheme:dark){:root{--bg:#0e141c;--carte:#16202c;--texte:#e6ebf2;--doux:#9aa7b8;--bord:#27364a;--marine:#0a1a2b;
--marine2:#12304f;--pyfond:#14283f;--jvfond:#33200f;--okfond:#112b1e;--kofond:#35171a;--ombre:0 1px 2px rgba(0,0,0,.4)}}
*{box-sizing:border-box}
body{margin:0;font-family:'Segoe UI',system-ui,Roboto,Arial,sans-serif;background:var(--bg);color:var(--texte);line-height:1.5}
a{color:var(--marine2);text-decoration:none} a:hover{text-decoration:underline}
@media(prefers-color-scheme:dark){a{color:#7fb2e8}}
.ar{font-family:'Noto Naskh Arabic','Amiri','Traditional Arabic','Segoe UI',Tahoma,serif;direction:rtl;text-align:right}
header{background:linear-gradient(135deg,var(--marine),var(--marine2));color:#fff;border-bottom:4px solid var(--or)}
.bandeau{max-width:1320px;margin:0 auto;padding:18px 20px 0}
.bandeau h1{margin:0;font-size:24px;font-weight:650;letter-spacing:.2px} .bandeau h1 a{color:#fff}
.bandeau p{margin:2px 0 12px;color:#c9d6e6;font-size:14px}
nav{display:flex;gap:4px} nav a{color:#c9d6e6;padding:9px 18px;border-radius:9px 9px 0 0;font-size:14.5px;font-weight:600}
nav a:hover{text-decoration:none;background:rgba(255,255,255,.1)} nav a.on{background:var(--bg);color:var(--marine)}
@media(prefers-color-scheme:dark){nav a.on{color:#fff}}
main{max-width:1320px;margin:0 auto;padding:20px}
.carte{background:var(--carte);border:1px solid var(--bord);border-radius:14px;box-shadow:var(--ombre)}
form.carte{padding:18px 20px;margin-bottom:18px}
.q{display:flex;gap:10px} .q input{flex:1;font-size:20px;padding:11px 16px;border-radius:10px}
input,select{padding:8px 10px;border:1px solid var(--bord);border-radius:8px;font-size:14.5px;background:var(--carte);color:var(--texte);font-family:inherit}
input:focus,select:focus{outline:2px solid var(--or);outline-offset:0}
button.go{background:var(--marine2);color:#fff;border:0;border-radius:10px;padding:0 28px;font-size:16px;font-weight:600;cursor:pointer}
button.go:hover{background:var(--marine)}
.grille{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px;margin-top:14px}
label{display:flex;flex-direction:column;gap:4px;font-size:12.5px;color:var(--doux);font-weight:600;text-transform:uppercase;letter-spacing:.4px}
label input,label select{text-transform:none;letter-spacing:0;font-weight:400;font-size:14.5px;color:var(--texte)}
.puces{margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;font-size:13px;color:var(--doux)}
.puce{background:var(--bg);border:1px solid var(--bord);border-radius:20px;padding:3px 12px;color:var(--texte)}
.puce:hover{border-color:var(--or);text-decoration:none}
.verdict{padding:11px 16px;border-radius:10px;margin-bottom:14px;font-size:14.5px;font-weight:600}
.verdict.ok{background:var(--okfond);color:var(--ok)} .verdict.ko{background:var(--kofond);color:var(--ko)}
.cols{display:grid;gap:16px;align-items:start} .cols.deux{grid-template-columns:1fr 1fr}
@media(max-width:980px){.cols.deux{grid-template-columns:1fr}}
.col>h2{margin:0 0 10px;font-size:16px;display:flex;align-items:center;gap:10px}
.badge{display:inline-block;border-radius:6px;padding:2px 10px;font-size:13px;font-weight:700;color:#fff}
.badge.py{background:var(--py)} .badge.jv{background:var(--jv)}
.temps{margin-left:auto;font-size:12.5px;font-weight:600;color:var(--doux)}
.info{font-size:13px;color:var(--doux);margin:0 0 10px}
.info b{color:var(--texte);background:var(--bg);border:1px solid var(--bord);border-radius:5px;padding:0 6px}
.res{padding:13px 16px;margin-bottom:10px;border-left:5px solid var(--bord)}
.col.py .res{border-left-color:var(--py)} .col.jv .res{border-left-color:var(--jv)}
.res h3{margin:0 0 6px;font-size:17px;font-weight:600;line-height:1.7} .res h3 .n{float:left;margin-right:10px;color:var(--doux);font-family:'Segoe UI',sans-serif;font-size:14px}
.meta{font-size:12.5px;color:var(--doux);display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.score{font-weight:700;color:var(--texte);font-variant-numeric:tabular-nums}
.barre{height:5px;background:var(--bg);border-radius:4px;margin:8px 0 2px;overflow:hidden}
.barre i{display:block;height:100%;border-radius:4px} .py .barre i{background:var(--py)} .jv .barre i{background:var(--jv)}
.res ul{margin:8px 0 0;padding:0;list-style:none} .res li{font-size:14.5px;line-height:1.9;margin:6px 0;padding-right:12px;border-right:3px solid var(--or);color:var(--texte)}
.alerte{padding:14px 16px;border-radius:10px;background:var(--jvfond);border:1px solid var(--jv);color:var(--texte);font-size:14px}
.alerte code{background:var(--bg);padding:1px 6px;border-radius:4px}
table.chi{width:100%;border-collapse:collapse;font-size:14px} .chi th{text-align:left;font-size:11.5px;text-transform:uppercase;letter-spacing:.4px;color:var(--doux);padding:6px 8px;border-bottom:1px solid var(--bord)}
.chi td{padding:5px 8px;border-bottom:1px solid var(--bord);vertical-align:middle} .chi td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.chi td.terme{font-size:17px;font-weight:600}
.chi .jauge{width:34%} .chi .jauge span{display:block;height:9px;border-radius:5px}
.py .jauge span{background:var(--py)} .jv .jauge span{background:var(--jv)}
.etoiles{color:var(--or);font-weight:700;letter-spacing:1px}
.bloc{padding:14px 16px;margin-bottom:14px} .bloc h3{margin:0 0 8px;font-size:15px}
.aide{padding:14px 18px;font-size:14px;color:var(--doux);margin-bottom:16px} .aide b{color:var(--texte)}
.aide code{background:var(--bg);padding:1px 6px;border-radius:4px;color:var(--texte)}
pre.texte{white-space:pre-wrap;line-height:2.1;padding:20px;font-size:18px;margin:0}
.vide{padding:28px;text-align:center;color:var(--doux)}
footer{max-width:1320px;margin:0 auto;padding:6px 20px 26px;font-size:12.5px;color:var(--doux)}
"""

TITRE = "Moteur de recherche – décisions de la Cour de cassation"


def page(corps, actif='/', titre=TITRE):
    nav = ''.join(f"<a href='{h}'{' class=on' if h == actif else ''}>{t}</a>"
                  for h, t in (('/', '🔎 Recherche'), ('/chi2', 'χ² Statistiques')))
    return (f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{e(titre)}</title><style>{CSS}</style></head><body>"
            f"<header><div class='bandeau'><h1><a href='/'>⚖️ {e(titre)}</a></h1>"
            f"<p>{IDX.n} arrêts de la chambre foncière · TF-IDF, index inversé, chi² · double implémentation Python / Java</p>"
            f"<nav>{nav}</nav></div></header><main>{corps}</main>"
            f"<footer>Projet de text mining – moteur de recherche pour textes juridiques arabes</footer></body></html>")


def options(valeurs, choisi, etiquettes=None):
    return ''.join(f"<option value='{e(str(v))}'{' selected' if str(v) == str(choisi) else ''}>"
                   f"{e(str((etiquettes or {}).get(v, v)))}</option>" for v in valeurs)


def champs_communs(g, avec_resume=True):
    """Champs partagés par la recherche et la page chi2."""
    h = (f"<label>Mesure<select name='mesure'>{options(MESURES, g('mesure', 'cosinus'))}</select></label>"
         f"<label>TF<select name='tf'>{options(SCHEMAS_TF, g('tf', 'log'))}</select></label>"
         f"<label>Résultats (k)<select name='k'>{options([5, 10, 20, 50], g('k', '10'))}</select></label>"
         f"<label>Section<select name='section'>{options(['', 1, 2, 3, 4], g('section'), {'': 'toutes'})}</select></label>"
         f"<label>Du<input type='date' name='du' value='{e(g('du'))}'></label>"
         f"<label>Au<input type='date' name='au' value='{e(g('au'))}'></label>"
         f"<label>Mot du titre<input class='ar' name='titre' value='{e(g('titre'))}' placeholder='ex. تحفيظ'></label>")
    if avec_resume:
        h += (f"<label>Résumé<select name='resume'>{options([0, 1, 2, 3], g('resume', '2'), {0: 'aucun', 1: '1 phrase', 2: '2 phrases', 3: '3 phrases'})}</select></label>")
    return h


MOTEURS_CHOIX = {'both': 'Python + Java', 'py': 'Python seul', 'jv': 'Java seul'}


def exemples():
    try:
        with open(REQUETES, encoding='utf-8') as f:
            qs = [l.strip() for l in f if l.strip()][:8]
    except OSError:
        qs = []
    return ''.join(f"<a class='puce ar' href='/?q={quote(q)}'>{e(q)}</a>" for q in qs)


def formulaire(p):
    g = lambda k, d='': p.get(k, [d])[0]
    return f"""<form class='carte' method='get' action='/'>
<div class='q'><input class='ar' name='q' value='{e(g('q'))}' placeholder='اكتب سؤالك هنا… مثال: الشفعة' autofocus>
<button class='go'>Rechercher</button></div>
<div class='grille'>{champs_communs(g)}
<label>Moteur<select name='moteur'>{options(MOTEURS_CHOIX, g('moteur', 'both'), MOTEURS_CHOIX)}</select></label></div>
<div class='puces'>Exemples : {exemples()}</div></form>"""


def alerte_java():
    return (f"<div class='alerte'><b>Moteur Java indisponible.</b> {e(JAVA.erreur or 'arrêté')}<br>"
            f"Pour l'activer : JDK 17+, <code>SAFAR_v2_jar.zip</code> à la racine du projet (ou variable "
            f"<code>SAFAR_JAR</code>), puis relancer <code>python3 app.py</code>.</div>")


def entete_colonne(cle, nom, r):
    t = '' if r is None else f"<span class='temps'>⏱ {r['ms']:.2f} ms</span>"
    return f"<h2><span class='badge {cle}'>{nom}</span>{t}</h2>"


def bloc_resultats(cle, nom, r, erreur=None):
    h = [f"<div class='col {cle}'>{entete_colonne(cle, nom, r)}"]
    if erreur:
        h.append(f"<div class='alerte'>{e(erreur)}</div></div>")
        return ''.join(h)
    h.append("<div class='info'>Termes retenus : " +
             (' '.join(f"<b class='ar'>{e(t)}</b> idf {w:.2f}" for t, w in r['termes']) or 'aucun terme connu') +
             (f" · {r['nfiltre']} décision(s) après filtres" if r['nfiltre'] is not None else '') +
             f" · {len(r['res'])} résultat(s)</div>")
    top = max((x['score'] for x in r['res']), default=1) or 1
    for rang, x in enumerate(r['res'], 1):
        h.append(f"<div class='res carte'><h3 class='ar'><span class='n'>#{rang}</span>"
                 f"<a href='/doc?id={e(x['id'])}'>{e(x['titre']) or 'décision ' + e(x['id'])}</a></h3>"
                 f"<div class='meta'><span class='score'>{x['score']:.4f}</span><span>décision n° {e(x['id'])}</span>"
                 f"<span>{e(x['date']) or 'date ?'}</span><span>section {e(x['section']) or '?'}</span>"
                 f"<span>{x['longueur']} termes</span></div>"
                 f"<div class='barre'><i style='width:{100 * x['score'] / top:.1f}%'></i></div>")
        if x['resume']:
            h.append("<ul class='ar'>" + ''.join(
                f"<li>{e(ph[:320] + ('…' if len(ph) > 320 else ''))}</li>" for ph in x['resume']) + "</ul>")
        h.append("</div>")
    if not r['res']:
        h.append("<div class='carte vide'>Aucun résultat.</div>")
    h.append("</div>")
    return ''.join(h)


def lien_chi2(p, q):
    cles = ('mesure', 'tf', 'k', 'section', 'du', 'au', 'titre')
    qs = '&'.join(f"{c}={quote(p[c][0])}" for c in cles if c in p and p[c][0]) + f"&q={quote(q)}"
    return f"/chi2?{qs}"


def recherche(p):
    g = lambda k, d='': p.get(k, [d])[0].strip()
    q = g('q')
    if not q:
        return ''
    tf = g('tf', 'log') if g('tf', 'log') in SCHEMAS_TF else 'log'
    mesure = g('mesure', 'cosinus') if g('mesure', 'cosinus') in MESURES else 'cosinus'
    k = entier(g('k', '10'), 10, 1, 100)
    nres = entier(g('resume', '2'), 2, 0, 5)
    moteur = g('moteur', 'both') if g('moteur', 'both') in MOTEURS_CHOIX else 'both'
    arg = (q, k, mesure, tf, section_valide(g('section')), g('du'), g('au'), g('titre'), nres)
    rp = rj = err_j = None
    if moteur in ('both', 'py'):
        rp = rechercher_py(*arg)
    if moteur in ('both', 'jv'):
        try:
            rj = JAVA.rechercher(*arg)
        except Exception as ex:
            err_j = str(ex)
    h = []
    if rp and rj:
        a = [(x['id'], f"{x['score']:.6f}") for x in rp['res']]
        b = [(x['id'], f"{x['score']:.6f}") for x in rj['res']]
        if a == b:
            h.append(f"<div class='verdict ok'>✔ Python et Java retournent exactement les mêmes résultats "
                     f"({len(a)} décisions, mêmes scores à 6 décimales). Python : {rp['ms']:.2f} ms · Java : {rj['ms']:.2f} ms.</div>")
        else:
            h.append("<div class='verdict ko'>✘ Les deux moteurs diffèrent (voir les listes ci-dessous).</div>")
    colonnes = []
    if rp is not None:
        colonnes.append(bloc_resultats('py', '🐍 Python', rp))
    if moteur in ('both', 'jv'):
        colonnes.append(bloc_resultats('jv', '☕ Java', rj, err_j) if err_j is None else
                        f"<div class='col jv'>{entete_colonne('jv', '☕ Java', None)}{alerte_java()}</div>")
    h.append(f"<div class='cols {'deux' if len(colonnes) == 2 else ''}'>{''.join(colonnes)}</div>")
    h.append(f"<p class='info'>🔬 <a href='{e(lien_chi2(p, q))}'>Voir les termes caractéristiques de ces résultats (χ²)</a></p>")
    return ''.join(h)


# ---------------------------------------------------------------- page chi2
def tableau_chi2(cle, bloc):
    termes = bloc['termes']
    h = [f"<div class='bloc carte {cle}'><h3 class='ar' style='direction:ltr;text-align:left'>{e(bloc['titre'])} "
         f"<span class='info'>— {bloc['nc']} décision(s) / {bloc['nu']}</span></h3>"]
    if not termes:
        return ''.join(h) + "<div class='vide'>Aucun terme significatif.</div></div>"
    top = max(t[1] for t in termes) or 1
    h.append("<table class='chi'><tr><th>#</th><th>Terme</th><th>χ²</th><th></th><th>Niveau</th><th>df classe / total</th></tr>")
    for i, (t, x, a, tot) in enumerate(termes, 1):
        h.append(f"<tr><td class='num'>{i}</td><td class='terme ar'>{e(t)}</td><td class='num'>{x:.2f}</td>"
                 f"<td class='jauge'><span style='width:{100 * x / top:.1f}%'></span></td>"
                 f"<td class='etoiles'>{niveau(x)}</td><td class='num'>{a} / {tot}</td></tr>")
    h.append("</table></div>")
    return ''.join(h)


def page_chi2(p):
    g = lambda k, d='': p.get(k, [d])[0].strip()
    q = g('q')
    tf = g('tf', 'log') if g('tf', 'log') in SCHEMAS_TF else 'log'
    mesure = g('mesure', 'cosinus') if g('mesure', 'cosinus') in MESURES else 'cosinus'
    k = entier(g('k', '10'), 10, 1, 100)
    n = entier(g('n', '15'), 15, 1, 100)
    min_df = entier(g('min_df', '3'), 3, 1, 1000)
    moteur = g('moteur', 'both') if g('moteur', 'both') in MOTEURS_CHOIX else 'both'
    form = f"""<form class='carte' method='get' action='/chi2'>
<div class='q'><input class='ar' name='q' value='{e(q)}' placeholder='Requête (facultatif) : analyser les k premiers résultats'>
<button class='go'>Analyser</button></div>
<div class='grille'>{champs_communs(g, False)}
<label>Termes affichés<select name='n'>{options([10, 15, 20, 30], n)}</select></label>
<label>df min (classe)<select name='min_df'>{options([1, 2, 3, 5, 10], min_df)}</select></label>
<label>Moteur<select name='moteur'>{options(MOTEURS_CHOIX, moteur, MOTEURS_CHOIX)}</select></label></div></form>"""
    aide = """<div class='carte aide'><b>Statistique du χ² (chi-deux).</b> Pour chaque terme <i>t</i> et une classe de décisions <i>C</i>,
on compte les décisions qui contiennent <i>t</i> ou non, dans et hors de <i>C</i> (tableau 2×2) :
<code>χ² = N·(A·D − B·C′)² / [(A+B)(C′+D)(A+C′)(B+D)]</code>, 1 degré de liberté. Plus χ² est grand, plus le terme est
<b>caractéristique</b> de la classe (seules les sur-représentations sont gardées). Niveaux : <b>*</b> p&lt;0,05 (χ²≥3,84) ·
<b>**</b> p&lt;0,01 (≥6,63) · <b>***</b> p&lt;0,001 (≥10,83). <b>La classe</b> est : les <i>k</i> premiers résultats si une requête est saisie ;
sinon les décisions retenues par les filtres (ex. mot du titre تحفيظ) ; sinon chaque section tour à tour. Les termes sont affichés après racinisation Light10.</div>"""
    sortie = [form, aide]
    arg = (q, k, mesure, tf, n, min_df, section_valide(g('section')), g('du'), g('au'), g('titre'))
    cp = cj = err_j = None
    if moteur in ('both', 'py'):
        cp = chi2_py(*arg)
    if moteur in ('both', 'jv'):
        try:
            cj = JAVA.chi2(*arg)
        except Exception as ex:
            err_j = str(ex)
    if cp is not None and cj is not None:
        ok = len(cp) == len(cj) and all(
            x['titre'] == y['titre'] and x['nc'] == y['nc'] and len(x['termes']) == len(y['termes']) and
            all(t[0] == u[0] and t[2:] == u[2:] and abs(t[1] - u[1]) < 1e-5 for t, u in zip(x['termes'], y['termes']))
            for x, y in zip(cp, cj))       # Java transmet 6 décimales : comparaison à 1e-5 près
        sortie.append("<div class='verdict ok'>✔ Python et Java calculent exactement les mêmes χ².</div>" if ok else
                      "<div class='verdict ko'>✘ Les deux moteurs diffèrent.</div>")
    cols = []
    if cp is not None:
        cols.append("<div class='col py'><h2><span class='badge py'>🐍 Python</span></h2>" +
                    ''.join(tableau_chi2('py', b) for b in cp) + "</div>")
    if moteur in ('both', 'jv'):
        if err_j is not None or cj is None:
            cols.append(f"<div class='col jv'>{entete_colonne('jv', '☕ Java', None)}{alerte_java()}</div>")
        else:
            cols.append("<div class='col jv'><h2><span class='badge jv'>☕ Java</span></h2>" +
                        ''.join(tableau_chi2('jv', b) for b in cj) + "</div>")
    sortie.append(f"<div class='cols {'deux' if len(cols) == 2 else ''}'>{''.join(cols)}</div>")
    return ''.join(sortie)


# ---------------------------------------------------------------- serveur HTTP
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        p = parse_qs(u.query)
        try:
            if u.path == '/':
                body = page(formulaire(p) + recherche(p))
            elif u.path == '/chi2':
                body = page(page_chi2(p), '/chi2', "Statistique du χ² – termes caractéristiques")
            elif u.path == '/doc':
                did = p.get('id', [''])[0]
                if did not in POS:
                    return self.repondre(404, page("<div class='carte vide'>Décision introuvable.</div>"))
                d = IDX.docs[POS[did]]
                with open(os.path.join(CORPUS, did + '.txt'), encoding='utf-8') as f:
                    texte = f.read()
                body = page(f"<p class='info'><a href='javascript:history.back()'>← retour aux résultats</a> · "
                            f"décision n° {e(did)} · {e(d.date) or 'date ?'} · section {e(d.section) or '?'}</p>"
                            f"<div class='carte'><pre class='texte ar'>{e(texte)}</pre></div>")
            else:
                return self.repondre(404, page("<div class='carte vide'>Page introuvable.</div>"))
        except Exception as ex:                      # affichage lisible d'une erreur de saisie
            body = page(formulaire(p) + f"<div class='verdict ko'>Erreur : {e(str(ex))}</div>")
        self.repondre(200, body)

    def repondre(self, code, body):
        b = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Site prêt : http://localhost:{port}   ({IDX.n} décisions indexées)")
    print("Moteur Java : " + ("actif" if JAVA.dispo else f"INDISPONIBLE – {JAVA.erreur}"))
    print("Ctrl+C pour arrêter")
    try:
        ThreadingHTTPServer(('127.0.0.1', port), H).serve_forever()
    finally:
        if JAVA.proc:
            JAVA.proc.terminate()
