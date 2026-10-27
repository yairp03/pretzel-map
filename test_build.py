"""build.py on a small map drawn by hand (test_map.osm): which ways are kept,
where segments break, how green and avoided they are, and which area holds
each — read back as the phone reads them (decode)."""
import gzip, json, os, tempfile, unittest
from build import CLASS, build, decode, decode_extras, decode_heights
from heights import Heights

HERE = os.path.dirname(os.path.abspath(__file__))


class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        # A made-up slope for the heights: 1 m per 0.0001° east (about 9.4 m), flat north-south.
        build(os.path.join(HERE, 'test_map.osm'), cls.dir, Heights.from_function(lambda la, lo: (lo - 34.85) * 10000))
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
        self.assertEqual(sum(1 for s in self.seg.values() if s['cls'] != CLASS['beach']), 11)

    def beach(self):
        return [(k, s) for k, s in self.seg.items() if s['cls'] == CLASS['beach']]

    def test_beach_path_along_the_water(self):
        # The coastline (land on its left, so east here) along the beach, moved 12 m onto the sand: green, and unlit.
        along = [s for k, s in self.beach() if abs(k[0] - k[2]) > 0.0005 and abs(k[1] - 34.8521) < 0.0002]  # the waterline's, not the path on the sand
        self.assertTrue(along)
        for s in along:
            self.assertEqual(s['lit'], 2); self.assertGreater(s['green'], 200)
            for la, lo in s['shape']: self.assertAlmostEqual(lo / 1e6, 34.8520 + 12 / (111320 * 0.8456), delta=0.00003)
        # Two beaches 200 m apart: one path, the gap bridged.
        length = sum(s['dm'] for k, s in self.beach() if s in along) / 10
        self.assertAlmostEqual(length, 660, delta=40)

    def test_no_beach_path_in_the_sea(self):
        # A coastline stroke beside a beach, not on it: no path along it (the owner's saved route ran 20–50 m out
        # in the sea off north Netanya, 2026-10-23).
        self.assertEqual([k for k, s in self.beach() if 32.289 < k[0] < 32.297 or 32.289 < k[2] < 32.297], [])

    def test_beach_path_joined_to_a_path_down_to_the_sand(self):
        joins = [k for k, s in self.beach() if (32.3065, 34.853) in (k[:2], k[2:])]
        self.assertEqual(len(joins), 1)

    def test_a_path_on_the_sand_is_sand_a_paved_one_is_not(self):
        on_sand = self.find((32.307, 34.8538), (32.3082, 34.8538))
        self.assertEqual((on_sand['cls'], on_sand['lit']), (CLASS['beach'], 2))
        self.assertEqual(self.find((32.307, 34.8539), (32.3082, 34.8539))['cls'], CLASS['footway'])
        # The path down to the sand, mostly off it, stays a footway.
        self.assertEqual(self.find((32.3065, 34.856), (32.3065, 34.853))['cls'], CLASS['footway'])

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


    def test_heights_beside_each_area(self):
        self.assertEqual(sorted(self.index['heights']['tiles']), sorted(self.index['tiles']))
        self.assertIn('Copernicus', self.index['heights']['attribution'])

    def test_climbs_match_the_slope_and_the_map_file(self):
        for name in self.index['tiles']:
            with open(f'{self.dir}/t/{name}.bin.gz', 'rb') as f: row, col, verts, segs = decode(gzip.decompress(f.read()))
            with open(f'{self.dir}/h/{name}.bin.gz', 'rb') as f: hrow, hcol, z, climbs = decode_heights(gzip.decompress(f.read()))
            self.assertEqual((row, col, len(verts), len(segs)), (hrow, hcol, len(z), len(climbs)))
            for v, h in zip(verts, z): self.assertAlmostEqual(h / 10, (v[1] / 1e6 - 34.85) * 10000, delta=0.2)
            for s, (up, down) in zip(segs, climbs):
                rise = z[s['b']] - z[s['a']]   # straight east or west here, so the climb is the rise one way
                self.assertAlmostEqual(up - down, rise, delta=2)


if __name__ == '__main__':
    unittest.main()


    def test_stops(self):
        """Lights and crossings per segment, in halves: whole inside it, half at each end (EXTRAS.md)."""
        stops = {}
        for name, (row, col, verts, segs) in self.areas.items():
            with open(f'{self.dir}/x/{name}.bin.gz', 'rb') as f: xr, xc, stopped, _ = decode_extras(gzip.decompress(f.read()))
            self.assertEqual((xr, xc, len(stopped)), (row, col, len(segs)))
            for s, st in zip(segs, stopped):
                a, b = verts[s['a']], verts[s['b']]
                stops[(a[0] / 1e6, a[1] / 1e6, b[0] / 1e6, b[1] / 1e6)] = st
        # The light at node 2, inside the footway's first segment (1–3); the crossing at node 3, a junction: half to each of its four.
        self.assertEqual(stops[(32.301, 34.861, 32.301, 34.864)], (2, 1))
        self.assertEqual(stops[(32.301, 34.864, 32.301, 34.867)], (0, 1))
        self.assertEqual(stops[(32.303, 34.864, 32.301, 34.864)], (0, 1))
        self.assertEqual(stops[(32.301, 34.864, 32.299, 34.864)], (0, 1))
        self.assertEqual(stops[(32.31, 34.861, 32.31, 34.864)], (0, 0))
        self.assertEqual(self.index['extras']['format'], 1)
        self.assertEqual(set(self.index['extras']['tiles']), set(self.index['tiles']))

    def test_places(self):
        """Water and toilets anyone may use; toilets mapped as a building, at its middle."""
        places = []
        for name in self.index['tiles']:
            with open(f'{self.dir}/x/{name}.bin.gz', 'rb') as f: places += decode_extras(gzip.decompress(f.read()))[3]
        self.assertEqual(sorted(places), [(1, 32302200, 34862100), (2, 32302100, 34865100)])

class Lights(unittest.TestCase):
    """Street-light poles (lights.py): a way the map doesn't light-tag, with poles along it, is lit; a tag is never overruled."""

    # Poles every ~28 m along the untagged way 32.301, 34.861–34.864, and along the way tagged unlit.
    POLES = [(32.30101, 34.861 + i * 0.0003) for i in range(11)] + [(32.30401, 34.87 + i * 0.0003) for i in range(11)]

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        build(os.path.join(HERE, 'test_map.osm'), cls.dir, None, cls.POLES)
        with open(f'{cls.dir}/index.json') as f: cls.index = json.load(f)
        cls.seg = {}
        for name in cls.index['tiles']:
            with open(f'{cls.dir}/t/{name}.bin.gz', 'rb') as f: row, col, verts, segs = decode(gzip.decompress(f.read()))
            for s in segs:
                a, b = verts[s['a']], verts[s['b']]
                cls.seg[(a[0] / 1e6, a[1] / 1e6, b[0] / 1e6, b[1] / 1e6)] = s

    def test_untagged_with_poles_is_lit(self):
        self.assertEqual(self.seg[(32.301, 34.861, 32.301, 34.864)]['lit'], 1)

    def test_a_tag_stays(self):
        self.assertEqual(self.seg[(32.304, 34.87, 32.304, 34.873)]['lit'], 2)
        self.assertEqual(self.seg[(32.303, 34.864, 32.301, 34.864)]['lit'], 1)

    def test_credited(self):
        self.assertIn('Tel Aviv-Yafo', self.index['lights']['attribution'])

    def test_a_pole_at_one_end_is_not_enough(self):
        from lights import lit_by_poles
        way = [((32.3, 34.86), (32.3, 34.863), (32.3, 34.866)), 1, 0]
        out, changed = lit_by_poles([tuple(way)], [(32.3, 34.86)])
        self.assertEqual((out[0][2], changed), (0, 0))
        out, changed = lit_by_poles([tuple(way)], [(32.30005, 34.86 + i * 0.0002) for i in range(31)])
        self.assertEqual((out[0][2], changed), (1, 1))


class Abroad(unittest.TestCase):
    """Cities abroad (ABROAD.md): areas west of Greenwich or south of the equator, a city cut from its country's extract, heights there."""

    def test_a_negative_area_reads_back_and_israel_is_unchanged(self):
        from build import encode, encode_extras, encode_heights, varint
        edge = [([(51507400, -128400), (51507500, -127400)], CLASS['footway'], 0, 0, 0, 70)]
        row, col, verts, segs = decode(encode(1030, -3, edge))
        self.assertEqual((row, col, len(segs)), (1030, -3, 1))
        self.assertEqual(decode_heights(encode_heights(-7, -3, edge, [(0, 0, 0, 0)]))[:2], (-7, -3))
        self.assertEqual(decode_extras(encode_extras(1030, -3, [(0, 0)], []))[:2], (1030, -3))
        # An area of Israel: the same bytes as before the change (varint row, varint col straight after the magic).
        head = []; varint(head, 646); varint(head, 697)
        self.assertEqual(encode(646, 697, edge)[4:4 + len(head)], bytes(head))

    def test_a_box_keeps_only_what_reaches_into_it(self):
        d = tempfile.mkdtemp()
        build(os.path.join(HERE, 'test_map.osm'), d, box=(32.30, 34.80, 32.40, 34.90))
        with open(f'{d}/index.json') as f: tiles = json.load(f)['tiles']
        self.assertEqual(sorted(tiles), ['646_697'])

    def test_heights_west_of_greenwich(self):
        import numpy as np, rasterio
        from rasterio.transform import from_origin
        d = tempfile.mkdtemp()
        # A 1° tile over London, 100 m everywhere.
        with rasterio.open(f'{d}/N51W001.tif', 'w', driver='GTiff', height=10, width=10, count=1, dtype='float32', transform=from_origin(-1, 52, 0.1, 0.1)) as ds:
            ds.write(np.full((1, 10, 10), 100, np.float32))
        h = Heights.from_dir(d)
        self.assertAlmostEqual(float(h.at([51.5], [-0.5])[0]), 100, 3)
        self.assertEqual(float(h.at([51.5], [0.5])[0]), 0)
