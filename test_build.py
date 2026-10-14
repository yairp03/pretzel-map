"""build.py on a small map drawn by hand (test_map.osm): which ways are kept,
where segments break, how green and avoided they are, and which area holds
each — read back as the phone reads them (decode)."""
import gzip, json, os, tempfile, unittest
from build import CLASS, build, decode

HERE = os.path.dirname(os.path.abspath(__file__))


class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        build(os.path.join(HERE, 'test_map.osm'), cls.dir)
        with open(f'{cls.dir}/index.json') as f: cls.index = json.load(f)
        cls.areas = {}
        for name in cls.index['tiles']:
            with open(f'{cls.dir}/t/{name}.bin.gz', 'rb') as f: cls.areas[name] = decode(gzip.decompress(f.read()))
        # Every segment, named by its ends' node coordinates as test_map.osm writes them.
        cls.seg = {}
        for row, col, verts, segs in cls.areas.values():
            for s in segs:
                a, b = verts[s['a']], verts[s['b']]
                cls.seg[(a[0] / 1e6, a[1] / 1e6, b[0] / 1e6, b[1] / 1e6)] = dict(s, area=f'{row}_{col}')

    def find(self, a, b):
        return self.seg[(*a, *b)]

    def test_index(self):
        self.assertEqual(self.index['format'], 1)
        self.assertEqual(self.index['classes'][CLASS['footway']], 'footway')
        self.assertEqual(sorted(self.index['tiles']), ['645_697', '646_697'])
        for size, digest in self.index['tiles'].values():
            self.assertGreater(size, 20); self.assertEqual(len(digest), 12)

    def test_only_runnable_ways(self):
        # The motorway, a footway marked foot=no and a private service road are left out; so is every area outline.
        self.assertEqual(len(self.seg), 8)

    def test_segments_break_at_junctions(self):
        footway = self.find((32.301, 34.861), (32.301, 34.864))
        self.assertEqual(footway['cls'], CLASS['footway'])
        self.assertEqual(footway['shape'], [(32301000, 34862500)])
        self.assertAlmostEqual(footway['dm'] / 10, 282.4, delta=1)
        self.find((32.301, 34.864), (32.301, 34.867))

    def test_green(self):
        self.assertEqual(self.find((32.301, 34.861), (32.301, 34.864))['green'], 255)       # inside the park
        half = self.find((32.301, 34.864), (32.301, 34.867))['green'] / 255                  # the park ends a third of the way
        self.assertTrue(0.3 < half < 0.55, half)
        self.assertEqual(self.find((32.31, 34.861), (32.31, 34.864))['green'], 255)         # inside the wood (a multipolygon)
        self.assertEqual(self.find((32.304, 34.87), (32.304, 34.873))['green'], 0)

    def test_avoided(self):
        self.assertEqual(self.find((32.304, 34.87), (32.304, 34.873))['avoid'], 255)        # through the industrial zone
        self.assertEqual(self.find((32.301, 34.861), (32.301, 34.864))['avoid'], 0)

    def test_lit(self):
        self.assertEqual(self.find((32.303, 34.864), (32.301, 34.864))['lit'], 1)
        self.assertEqual(self.find((32.301, 34.861), (32.301, 34.864))['lit'], 0)
        self.assertEqual(self.find((32.304, 34.87), (32.304, 34.873))['lit'], 2)

    def test_areas_hold_the_segments_that_start_in_them(self):
        # Starts in 646 and ends in 645: held by 646, its far end listed there too.
        self.assertEqual(self.find((32.301, 34.864), (32.299, 34.864))['area'], '646_697')
        # Starts in 645, ends at the same vertex: the phone joins the two by its coordinates.
        self.assertEqual(self.find((32.298, 34.87), (32.299, 34.864))['area'], '645_697')


if __name__ == '__main__':
    unittest.main()
