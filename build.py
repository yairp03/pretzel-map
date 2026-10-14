"""Turns an OpenStreetMap extract into the map files Pretzel's routing reads
on the phone: every way a runner may use, cut into small square areas, each
segment carrying what the route's cost needs — its length, its kind of path,
how green it is, how much of it runs through places a runner avoids, and
whether it is lit.

    python3 -I build.py <extract.osm.pbf> <out dir>

Writes <out>/index.json and <out>/t/<row>_<col>.bin.gz (format: FORMAT.md).
Every way is kept as the feasibility test kept it (Pretzel's
scripts/feasibility: loops.mjs and pbf2json.py), so routes come out the same.
"""
import gzip, hashlib, json, math, re, sys, time
from datetime import datetime, timezone
import numpy as np
import osmium
from PIL import Image, ImageDraw, ImageFilter

FORMAT = 1
TILE = 0.05          # degrees: about 5.5 km north–south, 4.7 km east–west here
Q = 1e6              # coordinates kept to a millionth of a degree, about 11 cm
CELL = 20            # metres: the green raster, as the feasibility test had it
R = 6371008.8

# Ways a runner may use: the feasibility test's filter, kept identical.
NOT_RUNNABLE = re.compile(r'^(motorway|motorway_link|trunk|trunk_link|construction|proposed|bus_guideway|raceway|elevator|platform|corridor|bridleway)$')
def runnable(t):
    return 'highway' in t and not NOT_RUNNABLE.match(t['highway']) \
        and t.get('foot') not in ('no', 'private') and t.get('access') not in ('no', 'private')

# Kinds of path, by index in the files. The phone weighs them (its own table),
# so the weights can change without rebuilding the map. Append only: a
# file's numbers must keep their meaning.
CLASSES = ['other', 'footway', 'path', 'pedestrian', 'track', 'cycleway', 'living_street', 'residential', 'service',
           'unclassified', 'tertiary', 'tertiary_link', 'secondary', 'secondary_link', 'primary', 'primary_link', 'steps', 'road',
           # Not an OpenStreetMap way: the waterline along a beach, made here (beach_paths) — runners run on the sand.
           'beach']
CLASS = {c: i for i, c in enumerate(CLASSES)}

# Green: parks, gardens, grass, woods, water, beach — not open fields (meadow, scrub), which a runner doesn't find green.
def green(t, rel):
    if t.get('leisure') in ('park', 'garden', 'nature_reserve'): return True
    if t.get('landuse') in (('grass', 'forest') if rel else ('grass', 'forest', 'recreation_ground', 'village_green')): return True
    return t.get('natural') in (('wood', 'water', 'beach') if rel else ('wood', 'water', 'beach', 'coastline'))
watery = lambda t: t.get('natural') in ('water', 'coastline', 'beach') or 'waterway' in t
AVOID = {'industrial', 'commercial', 'retail', 'farmland', 'orchard', 'construction', 'brownfield', 'railway', 'military', 'quarry', 'landfill'}
avoid = lambda t: t.get('landuse') in AVOID
LIT = {'yes': 1, 'no': 2}  # 0: the map doesn't say


class Reader(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways = []                 # (node ids, (lat, lon) of each, class, lit)
        self.green_areas, self.green_lines, self.avoid_areas = [], [], []
        self.coast, self.beaches, self.cliffs = [], [], []   # for the path along the water (beach_paths)

    def way(self, w):
        t = dict(w.tags)
        if not t: return
        run, g, a = runnable(t), green(t, False), avoid(t)
        nat = t.get('natural')
        shore = nat in ('coastline', 'beach', 'sand', 'cliff')
        if not (run or g or a or shore): return
        try:
            pts = [(n.lat, n.lon) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if nat == 'coastline': self.coast.append(pts)
        elif nat == 'cliff': self.cliffs.append(pts)
        elif nat in ('beach', 'sand') and len(pts) > 3 and pts[0] == pts[-1]: self.beaches.append(pts)
        if run:
            self.ways.append(([n.ref for n in w.nodes], pts, CLASS.get(t['highway'], 0), LIT.get(t.get('lit'), 0)))
        closed = len(pts) > 3 and pts[0] == pts[-1]
        if g:
            if closed: self.green_areas.append(pts)
            if not closed or watery(t): self.green_lines.append(pts)
        if a and closed: self.avoid_areas.append(pts)

    def area(self, a):
        # Closed ways came through way(); here only multipolygon relations, their outer rings.
        if a.from_way(): return
        t = dict(a.tags)
        g, v = green(t, True), avoid(t)
        sand = t.get('natural') in ('beach', 'sand')
        if not (g or v or sand): return
        for ring in a.outer_rings():
            pts = [(n.lat, n.lon) for n in ring]
            if len(pts) > 3:
                if g or v: (self.green_areas if g else self.avoid_areas).append(pts)
                if sand: self.beaches.append(pts)


def dist(lat1, lon1, lat2, lon2):
    """Haversine, in metres, as the feasibility test measured (numpy arrays or numbers)."""
    r = math.pi / 180
    x = np.sin((lat2 - lat1) * r / 2) ** 2 + np.cos(lat1 * r) * np.cos(lat2 * r) * np.sin((lon2 - lon1) * r / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(x))


SHORE_STEP = 20     # metres between the beach path's points
SHORE_IN = 12       # metres onto the sand from the waterline (OpenStreetMap draws the coastline with the land on its left)
MIN_RUN = 200       # metres: shorter stretches of beach are not worth a path
SHORE_GAP = 300     # metres of unmapped shore bridged between two beaches
ACCESS = 120        # metres: how far a path ending on the sand may be joined to the beach path
ACCESS_EVERY = 150  # metres along the beach path between two joins


def _cross(p, q, a, b):
    """Do segments p–q and a–b cross (as plane coordinates)?"""
    d = lambda u, v, w: (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
    return d(p, q, a) * d(p, q, b) < 0 and d(a, b, p) * d(a, b, q) < 0


def beach_paths(coast, beaches, cliffs, ways, ras, next_id):
    """
    The path along the water on beaches, which OpenStreetMap doesn't have: on
    Netanya's coast, from Argaman to Poleg beach, about 1.9 km of broken bits
    in 3 km, so routes never went on the sand (the owner, 2026-10-15, chose to
    add it, in normal routes). The coastline where it runs along a beach or
    sand (within 40 m), moved 12 m onto the sand, gaps of up to 300 m between
    beaches bridged, cut into stretches of 200 m or more, and joined to the runnable ways that reach the sand: each way's
    node on the beach to the nearest point of the path within 120 m, one join
    every 150 m, never across a mapped cliff. Returned as ways for graph():
    (node ids, points, class, lit) — ids below zero, made here; lit = no.
    """
    if not coast or not beaches: return []
    mask = ras.image(beaches, (), 2, 0)
    on_sand = lambda la, lo: 0 <= (y := int((la - ras.la0) / ras.dy)) < ras.H and 0 <= (x := int((lo - ras.lo0) / ras.dx)) < ras.W and mask[y, x]
    kx = 111320 * math.cos(math.radians(ras.la0))
    plane = lambda la, lo: (lo * kx, la * 111320)
    runs = []
    for line in coast:
        # Every SHORE_STEP metres along the coastline, each point moved SHORE_IN metres to its left.
        pts, last = [], None
        for (la1, lo1), (la2, lo2) in zip(line, line[1:]):
            d = float(dist(la1, lo1, la2, lo2))
            if d == 0: continue
            ux, uy = (lo2 - lo1) * kx / d, (la2 - la1) * 111320 / d
            for i in range(max(1, int(d // SHORE_STEP))):
                f = i * SHORE_STEP / d
                la, lo = la1 + (la2 - la1) * f, lo1 + (lo2 - lo1) * f
                pts.append((la + ux * SHORE_IN / 111320, lo - uy * SHORE_IN / kx))
            last = (la2 + ux * SHORE_IN / 111320, lo2 - uy * SHORE_IN / kx)
        if last: pts.append(last)
        # On the sand, with gaps of up to SHORE_GAP between two mapped beaches bridged: the beaches round
        # Netanya's Poleg don't quite touch (200 m apart), and the path stopped there; a runner carries on.
        sand = [on_sand(*p) for p in pts]
        gap = SHORE_GAP // SHORE_STEP
        i = 0
        while i < len(sand):
            if sand[i]: i += 1; continue
            j = i
            while j < len(sand) and not sand[j]: j += 1
            if 0 < i and j < len(sand) and j - i <= gap: sand[i:j] = [True] * (j - i)
            i = j
        run = []
        for p, ok in zip(pts + [None], sand + [False]):
            if ok: run.append(p); continue
            if len(run) * SHORE_STEP >= MIN_RUN: runs.append(run)
            run = []

    # The beach path's points by 100 m cell, to find the nearest; cliffs by cell too, to refuse a join across one.
    cell = lambda x, y: (int(x // 100), int(y // 100))
    near, cliff_cells = {}, {}
    for r, run in enumerate(runs):
        for i, p in enumerate(run): near.setdefault(cell(*plane(*p)), []).append((r, i))
    for c in cliffs:
        for a, b in zip(c, c[1:]):
            pa, pb = plane(*a), plane(*b)
            # Every cell the cliff passes through, sampled every 50 m.
            n = max(1, int(math.hypot(pb[0] - pa[0], pb[1] - pa[1]) // 50))
            for k in {cell(pa[0] + (pb[0] - pa[0]) * j / n, pa[1] + (pb[1] - pa[1]) * j / n) for j in range(n + 1)}:
                cliff_cells.setdefault(k, []).append((pa, pb))
    # Each node on the sand to its nearest point of the path (not across a cliff); then the nearest node in each stretch.
    best = {}  # (run, stretch of ACCESS_EVERY) -> (distance, node id, node point, point index)
    seen = set()
    for ids, pts, _, _ in ways:
        for nid, p in zip(ids, pts):
            if nid in seen or not on_sand(*p): continue
            seen.add(nid)
            px, py = plane(*p); cx, cy = cell(px, py)
            hits = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for r, i in near.get((cx + dx, cy + dy), ()):
                        qx, qy = plane(*runs[r][i]); d = math.hypot(qx - px, qy - py)
                        if d > ACCESS: continue
                        cells = {cell(px + (qx - px) * j / 4, py + (qy - py) * j / 4) for j in range(5)}
                        if any(_cross((px, py), (qx, qy), a, b) for k in cells for a, b in cliff_cells.get(k, ())): continue
                        hits.append((d, r, i))
            if not hits: continue
            d, r, i = min(hits)
            key = (r, i * SHORE_STEP // ACCESS_EVERY)
            if key not in best or d < best[key][0]: best[key] = (d, nid, p, i)
    out, ids_of = [], []
    for run in runs:
        ids_of.append(list(range(next_id, next_id - len(run), -1))); next_id -= len(run)
        out.append((ids_of[-1], run, CLASS['beach'], LIT['no']))
    for (r, _), (_, nid, p, i) in best.items():
        out.append(([nid, ids_of[r][i]], [p, runs[r][i]], CLASS['beach'], LIT['no']))
    return out


def graph(ways):
    """Segments between junctions and way ends; the points between them stay as the segment's shape."""
    uses = {}
    for ids, _, _, _ in ways:
        last = len(ids) - 1
        for i, n in enumerate(ids): uses[n] = uses.get(n, 0) + (2 if i in (0, last) else 1)
    edges = []  # (shape points, class, lit)
    for ids, pts, cls, lit in ways:
        start = 0
        for i in range(1, len(ids)):
            if uses[ids[i]] > 1 or i == len(ids) - 1:
                shape = pts[start:i + 1]
                if any(p != shape[0] for p in shape): edges.append((shape, cls, lit))
                start = i
    return edges


class Raster:
    """A 20 m grid over the whole map, one byte a cell, drawn by Pillow."""
    def __init__(self, la0, lo0, la1, lo1):
        self.la0, self.lo0 = la0, lo0
        self.dy = CELL / 111320
        self.dx = CELL / (111320 * math.cos(math.radians((la0 + la1) / 2)))
        self.W, self.H = int((lo1 - lo0) / self.dx) + 2, int((la1 - la0) / self.dy) + 2

    def xy(self, pts):
        return [((lo - self.lo0) / self.dx, (la - self.la0) / self.dy) for la, lo in pts]

    def image(self, areas=(), lines=(), area_grow=0, line_grow=0):
        """Areas filled and lines drawn, each grown by n cells (the feasibility test: areas 1, lines 2)."""
        out = None
        for shapes, grow, fill in ((areas, area_grow, True), (lines, line_grow, False)):
            if not shapes: continue
            im = Image.new('L', (self.W, self.H), 0)
            d = ImageDraw.Draw(im)
            for pts in shapes:
                if fill: d.polygon(self.xy(pts), fill=1)
                else: d.line(self.xy(pts), fill=1, width=1)
            if grow: im = im.filter(ImageFilter.MaxFilter(2 * grow + 1))
            a = np.asarray(im, dtype=np.uint8)
            out = a if out is None else np.maximum(out, a)
        return out if out is not None else np.zeros((self.H, self.W), np.uint8)

    def share(self, grid, edges):
        """For each segment, the share of points every 10 m along it that fall in a marked cell — as the feasibility test sampled."""
        a_lat, a_lon, b_lat, b_lon, owner = [], [], [], [], []
        for k, (shape, _, _) in enumerate(edges):
            for p, q in zip(shape, shape[1:]):
                a_lat.append(p[0]); a_lon.append(p[1]); b_lat.append(q[0]); b_lon.append(q[1]); owner.append(k)
        a_lat, a_lon, b_lat, b_lon, owner = map(np.array, (a_lat, a_lon, b_lat, b_lon, owner))
        m = np.maximum(np.ceil(dist(a_lat, a_lon, b_lat, b_lon) / 10).astype(np.int64), 0)
        seg = np.repeat(np.arange(len(m)), m)
        s = (np.arange(len(seg)) - np.repeat(np.cumsum(m) - m, m)) / np.repeat(np.maximum(m, 1), m)
        la = a_lat[seg] + (b_lat[seg] - a_lat[seg]) * s
        lo = a_lon[seg] + (b_lon[seg] - a_lon[seg]) * s
        y = np.floor((la - self.la0) / self.dy).astype(np.int64)
        x = np.floor((lo - self.lo0) / self.dx).astype(np.int64)
        ok = (x >= 0) & (y >= 0) & (x < self.W) & (y < self.H)
        hit = np.zeros(len(seg), np.int64)
        hit[ok] = grid[y[ok], x[ok]]
        n = np.bincount(owner[seg], minlength=len(edges))
        inside = np.bincount(owner[seg], weights=hit, minlength=len(edges))
        return np.where(n > 0, inside / np.maximum(n, 1), 0.0)


def varint(out, v):
    while v >= 0x80:
        out.append((v & 0x7F) | 0x80); v >>= 7
    out.append(v)

def zigzag(v):
    return v * 2 if v >= 0 else -v * 2 - 1

def encode(row, col, edges):
    """One area's file (FORMAT.md): its vertices, then its segments. edges: (shape as ints, class, lit, green, avoid, length in dm)."""
    vid, verts = {}, []
    for shape, *_ in edges:
        for p in (shape[0], shape[-1]):
            if p not in vid: vid[p] = len(verts); verts.append(p)
    out = bytearray(b'PZM' + bytes([FORMAT]))
    varint(out, row); varint(out, col); varint(out, len(verts))
    px = (0, 0)
    for p in verts:
        varint(out, zigzag(p[0] - px[0])); varint(out, zigzag(p[1] - px[1])); px = p
    varint(out, len(edges))
    for shape, cls, lit, g, a, dm in edges:
        varint(out, vid[shape[0]]); varint(out, vid[shape[-1]])
        out += bytes([cls, lit, g, a])
        varint(out, dm)
        varint(out, len(shape) - 2)
        px = shape[0]
        for p in shape[1:-1]:
            varint(out, zigzag(p[0] - px[0])); varint(out, zigzag(p[1] - px[1])); px = p
    return bytes(out)


def decode(raw):
    """One area's file back into (row, col, vertices, segments): what the phone reads, for the tests and the check."""
    assert raw[:3] == b'PZM' and raw[3] == FORMAT, 'not a map file of this format'
    i = 4
    def uv():
        nonlocal i
        v, sh = 0, 0
        while True:
            b = raw[i]; i += 1; v |= (b & 0x7F) << sh; sh += 7
            if b < 0x80: return v
    zz = lambda: (lambda v: -(v + 1) // 2 if v & 1 else v // 2)(uv())
    row, col = uv(), uv()
    verts, la, lo = [], 0, 0
    for _ in range(uv()):
        la += zz(); lo += zz(); verts.append((la, lo))
    segs = []
    for _ in range(uv()):
        a, b = uv(), uv()
        cls, lit, g, av = raw[i:i + 4]; i += 4
        dm, shape, (la, lo) = uv(), [], verts[a]
        for _ in range(uv()):
            la += zz(); lo += zz(); shape.append((la, lo))
        segs.append(dict(a=a, b=b, cls=cls, lit=lit, green=g, avoid=av, dm=dm, shape=shape))
    assert i == len(raw), 'bytes left over'
    return row, col, verts, segs


def build(pbf, out):
    import os
    t0 = time.time()
    r = Reader()
    r.apply_file(pbf, locations=True, idx='flex_mem')
    stamp = osmium.io.Reader(pbf, osmium.osm.osm_entity_bits.NOTHING).header().get('osmosis_replication_timestamp', '')
    print(f'read: {len(r.ways)} ways, {len(r.green_areas)} green areas, {len(r.green_lines)} green lines, {len(r.avoid_areas)} avoided areas, {len(r.beaches)} beaches, {time.time() - t0:.0f}s', flush=True)

    lats = np.array([p[0] for w in r.ways for p in (w[1][0], w[1][-1])])
    lons = np.array([p[1] for w in r.ways for p in (w[1][0], w[1][-1])])
    ras = Raster(lats.min() - .01, lons.min() - .01, lats.max() + .01, lons.max() + .01)
    shore = beach_paths(r.coast, r.beaches, r.cliffs, r.ways, ras, -1)
    print(f'beach paths: {sum(1 for w in shore if len(w[0]) > 2)} stretches, {sum(1 for w in shore if len(w[0]) == 2)} joins, {time.time() - t0:.0f}s', flush=True)
    edges = graph(r.ways + shore)
    del r.ways
    print(f'graph: {len(edges)} segments; raster {ras.W}×{ras.H}, {time.time() - t0:.0f}s', flush=True)

    g = ras.share(ras.image(r.green_areas, r.green_lines, 1, 2), edges)
    a = ras.share(ras.image(r.avoid_areas), edges)
    print(f'green and avoided shares, {time.time() - t0:.0f}s', flush=True)

    tiles = {}
    for (shape, cls, lit), gs, av in zip(edges, g, a):
        pts = [(round(la * Q), round(lo * Q)) for la, lo in shape]
        la, lo = np.array([p[0] for p in shape]), np.array([p[1] for p in shape])
        dm = max(1, round(float(dist(la[:-1], lo[:-1], la[1:], lo[1:]).sum()) * 10))
        # An area holds the segments that start in it; the phone joins areas by the vertices' coordinates.
        key = (math.floor(shape[0][0] / TILE), math.floor(shape[0][1] / TILE))
        tiles.setdefault(key, []).append((pts, cls, lit, round(gs * 255), round(av * 255), dm))

    os.makedirs(f'{out}/t', exist_ok=True)
    index = {}
    total = 0
    for (row, col), es in sorted(tiles.items()):
        raw = encode(row, col, es)
        gz = gzip.compress(raw, 9, mtime=0)
        with open(f'{out}/t/{row}_{col}.bin.gz', 'wb') as f: f.write(gz)
        index[f'{row}_{col}'] = [len(gz), hashlib.sha256(raw).hexdigest()[:12]]
        total += len(gz)
    meta = {
        'format': FORMAT, 'tile': TILE, 'built': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'osm': stamp,
        # Where the extract came from (MAP_SOURCE, set by the job): Geofabrik's covers more than its fallback's, so check.py compares like with like.
        'source': os.environ.get('MAP_SOURCE', os.path.basename(pbf)),
        'classes': CLASSES, 'attribution': '© OpenStreetMap contributors, ODbL — openstreetmap.org/copyright',
        'tiles': index,
    }
    with open(f'{out}/index.json', 'w') as f: json.dump(meta, f, separators=(',', ':'))
    big = sorted(index.items(), key=lambda kv: -kv[1][0])[:3]
    print(f'wrote {len(index)} areas, {total / 1e6:.1f} MB in all; largest {[(k, round(v[0] / 1e3)) for k, v in big]} KB; {time.time() - t0:.0f}s')


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2])
