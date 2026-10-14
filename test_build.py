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
        self.assertEqual(self.index['classes'][-1], 'beach')   # appended: older numbers keep their meaning
        self.assertEqual(sorted(self.index['tiles']), ['645_697', '646_697'])
        for size, digest in self.index['tiles'].values():
            self.assertGreater(size, 20); self.assertEqual(len(digest), 12)

    def test_only_runnable_ways(self):
        # The motorway, a footway marked foot=no and a private service road are left out; so is every area outline.
        self.assertEqual(sum(1 for s in self.seg.values() if s['cls'] != CLASS['beach']), 10)

    def beach(self):
        return [(k, s) for k, s in self.seg.items() if s['cls'] == CLASS['beach']]

    def test_beach_path_along_the_water(self):
        # The coastline (land on its left, so east here) along the beach, moved 12 m onto the sand: green, and unlit.
        along = [s for k, s in self.beach() if abs(k[0] - k[2]) > 0.0005]
        self.assertTrue(along)
        for s in along:
            self.assertEqual(s['lit'], 2); self.assertGreater(s['green'], 200)
            for la, lo in s['shape']: self.assertAlmostEqual(lo / 1e6, 34.8520 + 12 / (111320 * 0.8456), delta=0.00003)
        # Two beaches 200 m apart: one path, the gap bridged.
        length = sum(s['dm'] for k, s in self.beach() if s in along) / 10
        self.assertAlmostEqual(length, 660, delta=40)

    def test_beach_path_joined_to_a_path_down_to_the_sand(self):
        joins = [k for k, s in self.beach() if (32.3065, 34.853) in (k[:2], k[2:])]
        self.assertEqual(len(joins), 1)

    def test_no_join_across_a_cliff(self):
        self.assertFalse([k for k, s in self.beach() if (32.3038, 34.853) in (k[:2], k[2:])])

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
