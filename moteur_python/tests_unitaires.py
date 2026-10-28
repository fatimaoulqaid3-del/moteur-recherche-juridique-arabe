"""Tests unitaires : TF, IDF, cosinus et autres mesures vérifiés à la main sur un mini-corpus.
   python3 -m unittest tests_unitaires -v
"""
import math
import os
import tempfile
import unittest

from filtres import construire_filtre
from indexation import construire
from moteur import Moteur
from preprocess import Preprocesseur
from statistiques import chi2, niveau, termes_caracteristiques

STOP = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ressources', 'stopwords_ar.txt')
# mini-corpus (stemming désactivé -> les termes restent tels quels)
DOCS = {'1': 'بيع بيع كراء', '2': 'بيع شفعة', '3': 'كراء رهن'}


class TestMoteur(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        for i, t in DOCS.items():
            with open(os.path.join(cls.tmp.name, i + '.txt'), 'w', encoding='utf-8') as f:
                f.write(t)
        p = Preprocesseur(STOP, 'none')
        cls.idx = construire(cls.tmp.name, p)
        cls.m = Moteur(cls.idx, p, 'raw')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_idf(self):                        # بيع: df=2, كراء: df=2, شفعة: df=1, N=3
        self.assertAlmostEqual(self.m.idf['بيع'], math.log10(3 / 2))
        self.assertAlmostEqual(self.m.idf['شفعة'], math.log10(3 / 1))

    def test_tf_et_poids(self):                # tf(بيع, doc1)=2 -> poids = 2*idf
        pos1 = [d.id for d in self.idx.docs].index('1')
        w = dict(self.m.poids['بيع'])[pos1]
        self.assertAlmostEqual(w, 2 * math.log10(1.5))

    def test_cosinus_main(self):               # requête « شفعة » : seul le doc 2 contient le terme
        res = self.m.rechercher('شفعة', 5, 'cosinus')
        self.assertEqual([self.idx.docs[p].id for p, _ in res], ['2'])
        w_doc2 = [math.log10(1.5), math.log10(3)]          # بيع, شفعة
        attendu = math.log10(3) ** 2 / (math.log10(3) * math.sqrt(sum(x * x for x in w_doc2)))
        self.assertAlmostEqual(res[0][1], attendu)

    def test_jaccard_dice(self):               # requête {بيع, كراء} ; doc1 = {بيع, كراء}
        j = dict(self.m.rechercher('بيع كراء', 5, 'jaccard'))
        d = dict(self.m.rechercher('بيع كراء', 5, 'dice'))
        pos1 = [x.id for x in self.idx.docs].index('1')
        self.assertAlmostEqual(j[pos1], 1.0)
        self.assertAlmostEqual(d[pos1], 1.0)

    def test_index_et_balayage_identiques(self):
        for mesure in ('cosinus', 'produit', 'jaccard', 'dice', 'euclidienne'):
            self.assertEqual(self.m.rechercher('بيع كراء', 5, mesure, None, 'index'),
                             self.m.rechercher('بيع كراء', 5, mesure, None, 'lineaire'))

    def test_terme_inconnu(self):
        self.assertEqual(self.m.rechercher('كلمةمجهولة', 5), [])


def _decision(num, date, sujet):
    return (f"قرار محكمة النقض\nرقم {num}\nالصادر بتاريخ {date}\n"
            f"في الملف العقاري رقم 2020/1/1/1234\n{sujet}\nإن المحكمة لما قضت بما قضت تكون قد عللت قرارها")


class TestFiltres(unittest.TestCase):
    def test_section_date_titre(self):
        with tempfile.TemporaryDirectory() as tmp:
            textes = {'1': _decision('1/10', '04 فبراير 2023', 'نزاع تحفيظ - أثره'),
                      '2': _decision('2/20', '15 مارس 2023', 'دعوى الإفراغ - أثره'),
                      '3': _decision('2/30', '20 ابريل 2023', 'شفعة - أثره')}
            for i, t in textes.items():
                with open(os.path.join(tmp, i + '.txt'), 'w', encoding='utf-8') as f:
                    f.write(t)
            idx = construire(tmp, Preprocesseur(STOP, 'none'))
            ids = lambda f: sorted(idx.docs[p].id for p in f)
            self.assertEqual([d.date for d in idx.docs], ['2023-02-04', '2023-03-15', '2023-04-20'])
            self.assertEqual(ids(construire_filtre(idx, section=2)), ['2', '3'])
            self.assertEqual(ids(construire_filtre(idx, du='2023-03-01', au='2023-03-31')), ['2'])
            self.assertEqual(ids(construire_filtre(idx, titre='إفراغ')), ['2'])
            self.assertIsNone(construire_filtre(idx))



class TestChi2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            for i, texte in DOCS.items():
                with open(os.path.join(tmp, i + '.txt'), 'w', encoding='utf-8') as f:
                    f.write(texte)
            cls.idx = construire(tmp, Preprocesseur(STOP, 'none'))

    def test_valeur_calculee_a_la_main(self):
        # A=8 B=2 C'=2 D=8 : N=20 ; chi2 = 20 * (64-4)^2 / (10*10*10*10) = 7.2
        self.assertAlmostEqual(chi2(8, 2, 2, 8), 7.2, places=9)

    def test_independance_et_cas_degenere(self):
        self.assertEqual(chi2(5, 5, 5, 5), 0.0)       # proportions identiques : aucun lien
        self.assertEqual(chi2(0, 0, 3, 4), 0.0)       # terme absent partout : dénominateur nul

    def test_niveaux(self):
        self.assertEqual([niveau(x) for x in (1, 3.84, 6.63, 10.83)], ['', '*', '**', '***'])

    def test_termes_caracteristiques(self):
        # 'بيع' est dans les docs 0 et 1 (classe = {0,1}), 'رهن' seulement dans le doc 2
        classe = {0, 1}
        res = termes_caracteristiques(self.idx, classe, None, n=10, min_df=1)
        termes = [r[0] for r in res]
        self.assertIn('بيع', termes)
        self.assertNotIn('رهن', termes)               # association négative : écartée
        x = dict((r[0], r[1]) for r in res)['بيع']
        self.assertAlmostEqual(x, chi2(2, 0, 0, 1), places=9)   # A=2 B=0 C'=0 D=1


if __name__ == '__main__':
    unittest.main()
