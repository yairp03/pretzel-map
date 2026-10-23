"""names.py on the hand-drawn map (test_map.osm): a town's boundary kept,
a regional council's left out, a neighbourhood and a village as points, and
the file listed in the index."""
import json, os, tempfile, unittest
from names import make

HERE = os.path.dirname(os.path.abspath(__file__))


class Names(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        with open(f'{cls.dir}/index.json', 'w') as f: json.dump({'tiles': {}}, f)
        make(os.path.join(HERE, 'test_map.osm'), cls.dir)
        with open(f'{cls.dir}/names.json') as f: cls.names = json.load(f)
        with open(f'{cls.dir}/index.json') as f: cls.index = json.load(f)

    def test_towns_without_regional_councils(self):
        self.assertEqual([(t['he'], t['en']) for t in self.names['towns']], [('עיר מבחן', 'Test Town')])
        ring = self.names['towns'][0]['rings'][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(len(ring), 5)

    def test_places(self):
        self.assertIn([34.865, 32.305, 'שכונת מבחן', 'Test Quarter', 'n'], self.names['places'])
        self.assertIn([34.88, 32.32, 'כפר מבחן', 'Test Village', 's'], self.names['places'])

    def test_in_the_index(self):
        n = self.index['names']
        self.assertEqual(n['format'], 1)
        self.assertEqual(len(n['hash']), 12)
        self.assertEqual(n['bytes'], os.path.getsize(f'{self.dir}/names.json'))


if __name__ == '__main__':
    unittest.main()
