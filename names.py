"""Place names, so the app can say where a run started ("Tel Aviv",
"Old North") on the phone, with no lookup service and nothing sent anywhere
(the owner, 2026-10-23: saved routes and runs said too little).

    python3 -I names.py <extract.osm.pbf> <out dir>

Writes <out>/names.json (NAMES.md), and adds it to <out>/index.json — its
size and a hash, so phones fetch it again only when it changes. Run after
build.py, which writes the index.
"""
import gzip, hashlib, json, math, sys
import osmium

FORMAT = 1
# Settlements, for a start outside every town's boundary; neighbourhoods, inside a town.
SETTLEMENT = {'city', 'town', 'village', 'hamlet'}
AREA = {'suburb', 'neighbourhood', 'quarter'}
# Boundaries simplified to this many metres: a start is named, not surveyed.
TOLERANCE = 25


def names(t):
    """Hebrew and English, each falling back on the other or on the plain name."""
    plain = t.get('name')
    he, en = t.get('name:he') or plain, t.get('name:en') or plain
    return (he, en) if he and en else None


def regional(t):
    # A regional council spans dozens of villages: a start in one is named by the village, not the council.
    return 'Regional Council' in (t.get('name:en') or '') or 'מועצה אזורית' in (t.get('name:he') or t.get('name') or '')


def simplify(ring, tol):
    """Douglas–Peucker in metres on [lon, lat] points; a closed ring split at its farthest point first."""
    if len(ring) < 5: return ring
    k = math.cos(math.radians(ring[0][1]))
    xy = [(lo * 111320 * k, la * 111320) for lo, la in ring]
    far = max(range(len(xy)), key=lambda i: (xy[i][0] - xy[0][0]) ** 2 + (xy[i][1] - xy[0][1]) ** 2)
    keep = {0, far, len(xy) - 1}
    stack = [(0, far), (far, len(xy) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = xy[a], xy[b]
        L = math.hypot(bx - ax, by - ay) or 1
        best, at = tol, -1
        for i in range(a + 1, b):
            d = abs((bx - ax) * (ay - xy[i][1]) - (ax - xy[i][0]) * (by - ay)) / L
            if d > best: best, at = d, i
        if at > 0:
            keep.add(at); stack += [(a, at), (at, b)]
    return [ring[i] for i in sorted(keep)]


class Reader(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.towns, self.places = [], []

    def node(self, n):
        t = n.tags
        kind = t.get('place')
        if kind not in SETTLEMENT and kind not in AREA: return
        nm = names(t)
        if nm: self.places.append([round(n.location.lon, 5), round(n.location.lat, 5), *nm, 's' if kind in SETTLEMENT else 'n'])

    def area(self, a):
        t = a.tags
        if a.from_way() or t.get('boundary') != 'administrative' or t.get('admin_level') != '8' or regional(t): return
        nm = names(t)
        if not nm: return
        rings = []
        for ring in a.outer_rings():
            pts = simplify([(round(p.lon, 5), round(p.lat, 5)) for p in ring], TOLERANCE)
            if len(pts) >= 4: rings.append(pts)
        if rings: self.towns.append({'he': nm[0], 'en': nm[1], 'rings': rings})


def make(pbf, out):
    r = Reader()
    r.apply_file(pbf, locations=True, idx='flex_mem')
    r.towns.sort(key=lambda x: x['en'])
    r.places.sort(key=lambda p: (p[3], p[0]))
    body = json.dumps({'format': FORMAT, 'towns': r.towns, 'places': r.places}, ensure_ascii=False, separators=(',', ':')).encode()
    with open(f'{out}/names.json', 'wb') as f: f.write(body)
    with open(f'{out}/index.json') as f: index = json.load(f)
    index['names'] = {'format': FORMAT, 'bytes': len(body), 'gzip': len(gzip.compress(body)), 'hash': hashlib.sha256(body).hexdigest()[:12]}
    with open(f'{out}/index.json', 'w') as f: json.dump(index, f, separators=(',', ':'))
    print(f'names: {len(r.towns)} towns, {sum(p[4] == "s" for p in r.places)} settlements, {sum(p[4] == "n" for p in r.places)} neighbourhoods; {len(body) / 1e3:.0f} KB, {index["names"]["gzip"] / 1e3:.0f} KB gzipped')


if __name__ == '__main__':
    make(sys.argv[1], sys.argv[2])
