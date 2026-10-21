"""Tests of the reference engine: the selftest (every check and the published vectors)."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gm_engine as E  # noqa: E402


class TestEngine(unittest.TestCase):
    def test_selftest(self):
        E.selftest(E.Zones(), E.Lieux())

    def test_no_context(self):
        z, l = E.Zones(), E.Lieux()
        # The same name in several places: name + number decode to exactly one.
        fam = l.families[E.name_key('Brikama')]
        self.assertGreater(len(fam['lieux']), 1)
        for lieu in fam['lieux']:
            n = lieu['blocks'][0][0] + 1
            self.assertEqual([(a, c['index']) for a, c, _ in E.find(f'Brikama {n}', z, l)], [(lieu['zone'], lieu['index'])])


    def test_border(self):
        """SPEC 2.1: the border decides, not the zones."""
        b, z = E.Border(), E.Zones()
        self.assertLessEqual(b.limit, E.BORDER_M - 1)
        self.assertTrue(b.holds(13.4549, -16.5790))           # Banjul
        self.assertTrue(b.holds(13.31, -14.22))               # Basse Santa Su
        self.assertTrue(b.holds(13.595, -15.1))               # about 120 m outside the line
        across = (13.585, -15.1)                              # about 1.2 km into a neighbouring country
        self.assertEqual(z.lookup(*across), 'CRR')            # the zone rule alone would take it
        self.assertFalse(b.holds(*across))
        self.assertFalse(b.holds(14.15, -16.07))
        self.assertFalse(b.holds(12.57, -16.27))


if __name__ == '__main__':
    unittest.main()
