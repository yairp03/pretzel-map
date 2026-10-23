"""Turns an OpenStreetMap extract into the map files Pretzel's routing reads
on the phone: every way a runner may use, cut into small square areas, each
segment carrying what the route's cost needs — its length, its kind of path,
how green it is, how much of it runs through places a runner avoids, and
whether it is lit.

    python3 -I build.py <extract.osm.pbf> <out dir>

    python3 build.py <extract.osm.pbf> <out dir> <heights dir> [<street lights.json>]

Writes <out>/index.json and <out>/t/<row>_<col>.bin.gz (format: FORMAT.md);
with a folder of height tiles (heights.py), also <out>/h/<row>_<col>.bin.gz,
each area's heights and climbs (HEIGHTS.md); and always <out>/x/<row>_<col>.bin.gz,
each area's traffic lights and crossings, water and toilets (EXTRAS.md).
Every way is kept as the feasibility test kept it (Pretzel's
scripts/feasibility: loops.mjs and pbf2json.py), so routes come out the same.
"""
import gzip, hashlib, json, math, re, sys, time
from datetime import datetime, timezone
import numpy as np
import osmium
from PIL import Image, ImageDraw, ImageFilter

FORMAT = 1
EXTRAS_FORMAT = 1    # EXTRAS.md: stops per segment, and places
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
# Stops on the way (EXTRAS.md): a traffic light, at a junction or a crossing, and a crossing without one.
LIGHT, CROSSING = 2, 1
def stop(t):
    if t.get('highway') == 'traffic_signals' or (t.get('highway') == 'crossing' and (t.get('crossing') == 'traffic_signals' or t.get('crossing:signals') == 'yes')): return LIGHT
    if t.get('highway') == 'crossing' and t.get('crossing') != 'no': return CROSSING
    return 0
# Places along a run (EXTRAS.md): drinking water and toilets anyone may use.
WATER, TOILETS = 1, 2
def place(t):
    if t.get('access') in ('private', 'no', 'customers'): return 0
    if t.get('amenity') == 'drinking_water' or (t.get('amenity') == 'fountain' and t.get('drinking_water') == 'yes'): return WATER
    if t.get('amenity') == 'toilets': return TOILETS
    return 0
# A path that lies on a mapped beach is sand to a runner — unless it is paved, a boardwalk and the like.
PAVED = {'paved', 'asphalt', 'concrete', 'concrete:plates', 'concrete:lanes', 'paving_stones', 'sett', 'cobblestone', 'wood', 'metal', 'compacted', 'fine_gravel'}
SANDY = {'path', 'track', 'footway', 'other'}


class Reader(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways = []                 # (node ids, (lat, lon) of each, class, lit)
        self.paved = []                # beside each way: its surface is paved (or wood…), or it is a path tagged sand: 'sand'
        self.green_areas, self.green_lines, self.avoid_areas = [], [], []
        self.coast, self.beaches, self.cliffs = [], [], []   # for the path along the water (beach_paths)
        self.stops = {}                # node id: LIGHT or CROSSING
        self.places = []               # (kind, lat, lon)

    def node(self, n):
        if not n.tags: return
        t = dict(n.tags)
        k = stop(t)
        if k: self.stops[n.id] = k
        k = place(t)
        if k: self.places.append((k, n.location.lat, n.location.lon))

    def way(self, w):
        t = dict(w.tags)
        if not t: return
        # Toilets mapped as a building or an area: at its middle.
        k = place(t)
        if k and len(w.nodes) > 3 and w.nodes[0].ref == w.nodes[-1].ref:
            try:
                ring = [(n.lat, n.lon) for n in w.nodes][:-1]
                self.places.append((k, sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)))
            except osmium.InvalidLocationError:
                pass
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
            self.paved.append('sand' if t.get('surface') == 'sand' else t.get('surface') in PAVED)
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
# Cells (20 m each) a beach is grown by when asking whether the shore is on the sand: none. Grown by 40 m, a
# coastline OpenStreetMap draws as one straight 2.3 km stroke across north Netanya's curving shore counted as
# sand, and the path drawn along it ran 20–50 m out in the sea (the owner's saved route, 2026-10-23). With none:
# that stretch 2.24 km → 0.26 km; Argaman–Poleg 3.90 → 3.84, Tel Aviv 5.00 → 4.67, all of Israel 170 → 149 km.
SHORE_GROW = 0
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
    sand, moved 12 m onto the sand, gaps of up to 300 m between
    beaches bridged, cut into stretches of 200 m or more, and joined to the runnable ways that reach the sand: each way's
    node on the beach to the nearest point of the path within 120 m, one join
    every 150 m, never across a mapped cliff. Returned as ways for graph():
    (node ids, points, class, lit) — ids below zero, made here; lit = no.
    """
    if not coast or not beaches: return []
    mask = ras.image(beaches, (), SHORE_GROW, 0)
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


def graph(ways, src=None, stops=None, stopped=None):
    """
    Segments between junctions and way ends; the points between them stay as
    the segment's shape. src: a list filled, beside each segment, with the
    index of the way it came from. stopped: a list filled, beside each, with
    its (lights, crossings) in halves — whole inside it, half at each end,
    where it meets the next — from stops (node id: LIGHT or CROSSING).
    """
    uses = {}
    for ids, _, _, _ in ways:
        last = len(ids) - 1
        for i, n in enumerate(ids): uses[n] = uses.get(n, 0) + (2 if i in (0, last) else 1)
    edges = []  # (shape points, class, lit)
    for w, (ids, pts, cls, lit) in enumerate(ways):
        start = 0
        for i in range(1, len(ids)):
            if uses[ids[i]] > 1 or i == len(ids) - 1:
                shape = pts[start:i + 1]
                if any(p != shape[0] for p in shape):
                    edges.append((shape, cls, lit))
                    if src is not None: src.append(w)
                    if stopped is not None:
                        got = [0, 0]
                        for j in range(start, i + 1):
                            k = (stops or {}).get(ids[j])
                            if k: got[0 if k == LIGHT else 1] += 1 if start < j < i else 0.5
                        stopped.append((round(got[0] * 2), round(got[1] * 2)))
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


HEIGHTS_FORMAT = 1
EXTRAS_FORMAT = 1    # EXTRAS.md: stops per segment, and places

def encode_heights(row, col, edges, heights):
    """
    One area's heights (HEIGHTS.md), its vertices and segments in the same
    order as its map file (encode): each vertex's height, each segment's
    climb forward and back. heights: (start, end, up, down) per edge, in dm.
    """
    vid, verts = {}, []
    for (shape, *_), (z0, z1, _, _) in zip(edges, heights):
        for p, z in ((shape[0], z0), (shape[-1], z1)):
            if p not in vid: vid[p] = len(verts); verts.append(z)
    out = bytearray(b'PZH' + bytes([HEIGHTS_FORMAT]))
    varint(out, row); varint(out, col); varint(out, len(verts))
    prev = 0
    for z in verts:
        varint(out, zigzag(z - prev)); prev = z
    varint(out, len(edges))
    for _, _, up, down in heights:
        varint(out, up); varint(out, down)
    return bytes(out)


def encode_extras(row, col, stopped, places):
    """
    One area's extras (EXTRAS.md): each segment's lights and crossings in
    halves, in the order of its map file (encode); then its places, sorted
    so the file is the same for the same map.
    """
    out = bytearray(b'PZX' + bytes([EXTRAS_FORMAT]))
    varint(out, row); varint(out, col); varint(out, len(stopped))
    for lights, crossings in stopped:
        varint(out, lights); varint(out, crossings)
    varint(out, len(places))
    pla = plo = 0
    for kind, la, lo in sorted(places):
        out.append(kind)
        varint(out, zigzag(la - pla)); varint(out, zigzag(lo - plo)); pla, plo = la, lo
    return bytes(out)


def decode_extras(raw):
    """An extras file back: (row, col, [(lights, crossings)…], [(kind, lat, lon)…]), in millionths."""
    assert raw[:3] == b'PZX' and raw[3] == EXTRAS_FORMAT
    i = 4
    def uv():
        nonlocal i
        v = s = 0
        while True:
            b = raw[i]; i += 1
            v |= (b & 0x7f) << s; s += 7
            if b < 0x80: return v
    zz = lambda v: (v >> 1) ^ -(v & 1)
    row, col, n = uv(), uv(), uv()
    stopped = [(uv(), uv()) for _ in range(n)]
    places, la, lo = [], 0, 0
    for _ in range(uv()):
        kind = raw[i]; i += 1
        la += zz(uv()); lo += zz(uv())
        places.append((kind, la, lo))
    assert i == len(raw), 'extras: bytes left over'
    return row, col, stopped, places


def decode_heights(raw):
    """One area's heights back: (row, col, vertex heights, [(up, down)]) in dm — for the tests and the check."""
    assert raw[:3] == b'PZH' and raw[3] == HEIGHTS_FORMAT, 'not a heights file of this format'
    i = 4
    def uv():
        nonlocal i
        v, sh = 0, 0
        while True:
            b = raw[i]; i += 1; v |= (b & 0x7F) << sh; sh += 7
            if b < 0x80: return v
    zz = lambda: (lambda v: -(v + 1) // 2 if v & 1 else v // 2)(uv())
    row, col = uv(), uv()
    z, verts = 0, []
    for _ in range(uv()):
        z += zz(); verts.append(z)
    segs = [(uv(), uv()) for _ in range(uv())]
    assert i == len(raw), 'bytes left over'
    return row, col, verts, segs


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


def build(pbf, out, dem=None, lights=None):
    """
    dem: a folder of height tiles, or a Heights (tests); none, no heights
    files. lights: street-light poles (lights.py), a file of them or a list
    of (lat, lon); none, the map's own lit tags only.
    """
    import os
    import lights as street_lights
    from heights import ATTRIBUTION, Heights, climbs
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
    src, stopped = [], []
    edges = graph(r.ways + shore, src, r.stops, stopped)
    print(f'stops: {sum(1 for v in r.stops.values() if v == LIGHT)} lights, {sum(1 for v in r.stops.values() if v == CROSSING)} crossings; places: {len(r.places)}', flush=True)
    paved = r.paved + [False] * len(shore)
    del r.ways
    print(f'graph: {len(edges)} segments; raster {ras.W}×{ras.H}, {time.time() - t0:.0f}s', flush=True)

    # Paths over the sand (the owner, 2026-10-17: a path along the beach by Wingate wasn't "on the sand"): a path, track or
    # footway 80% or more on a mapped beach or sand, not paved, is the class 'beach' — slower, unlit unless tagged, said and dashed.
    if r.beaches:
        on_sand = ras.share(ras.image(r.beaches), edges)
        moved = 0
        for k, (shape, cls, lit) in enumerate(edges):
            p = paved[src[k]]
            if cls != CLASS['beach'] and (p == 'sand' or (CLASSES[cls] in SANDY and not p and on_sand[k] >= 0.8)):
                edges[k] = (shape, CLASS['beach'], lit if lit else LIT['no'])
                moved += 1
        print(f'paths on the sand: {moved}, {time.time() - t0:.0f}s', flush=True)
    # Lit where the map doesn't say and street-light poles stand along the way (lights.py).
    if lights is not None:
        poles = json.load(open(lights)) if isinstance(lights, str) else lights
        edges, lit_now = street_lights.lit_by_poles(edges, poles, 0, LIT['yes'])
        print(f'lit by poles: {lit_now} segments, of {len(poles)} poles, {time.time() - t0:.0f}s', flush=True)
    g = ras.share(ras.image(r.green_areas, r.green_lines, 1, 2), edges)
    a = ras.share(ras.image(r.avoid_areas), edges)
    print(f'green and avoided shares, {time.time() - t0:.0f}s', flush=True)
    if dem is not None:
        H = Heights.from_dir(dem) if isinstance(dem, str) else dem
        up, down, z0, z1 = climbs(H, edges)
        print(f'heights: {len(H.tiles) or "a function"}; climbs, {time.time() - t0:.0f}s', flush=True)

    tiles = {}
    tiles_h = {}
    tiles_x = {}
    for k, ((shape, cls, lit), gs, av) in enumerate(zip(edges, g, a)):
        pts = [(round(la * Q), round(lo * Q)) for la, lo in shape]
        la, lo = np.array([p[0] for p in shape]), np.array([p[1] for p in shape])
        dm = max(1, round(float(dist(la[:-1], lo[:-1], la[1:], lo[1:]).sum()) * 10))
        # An area holds the segments that start in it; the phone joins areas by the vertices' coordinates.
        key = (math.floor(shape[0][0] / TILE), math.floor(shape[0][1] / TILE))
        tiles.setdefault(key, []).append((pts, cls, lit, round(gs * 255), round(av * 255), dm))
        if dem is not None:
            # In decimetres, beside the edge in its area's list, so both files keep one order.
            tiles_h.setdefault(key, []).append((round(z0[k] * 10), round(z1[k] * 10), round(up[k] * 10), round(down[k] * 10)))
        tiles_x.setdefault(key, []).append(stopped[k])
    # Each place in the area it stands in; an area with no paths has no file, and its places no runner reaches.
    places_in = {}
    for kind, la, lo in r.places:
        places_in.setdefault((math.floor(la / TILE), math.floor(lo / TILE)), []).append((kind, round(la * Q), round(lo * Q)))

    os.makedirs(f'{out}/t', exist_ok=True)
    index = {}
    total = 0
    for (row, col), es in sorted(tiles.items()):
        raw = encode(row, col, es)
        gz = gzip.compress(raw, 9, mtime=0)
        with open(f'{out}/t/{row}_{col}.bin.gz', 'wb') as f: f.write(gz)
        index[f'{row}_{col}'] = [len(gz), hashlib.sha256(raw).hexdigest()[:12]]
        total += len(gz)
    index_h = {}
    if dem is not None:
        os.makedirs(f'{out}/h', exist_ok=True)
        for (row, col), es in sorted(tiles.items()):
            raw = encode_heights(row, col, es, tiles_h[(row, col)])
            gz = gzip.compress(raw, 9, mtime=0)
            with open(f'{out}/h/{row}_{col}.bin.gz', 'wb') as f: f.write(gz)
            index_h[f'{row}_{col}'] = [len(gz), hashlib.sha256(raw).hexdigest()[:12]]
    index_x = {}
    os.makedirs(f'{out}/x', exist_ok=True)
    for (row, col), es in sorted(tiles.items()):
        raw = encode_extras(row, col, tiles_x[(row, col)], places_in.get((row, col), []))
        gz = gzip.compress(raw, 9, mtime=0)
        with open(f'{out}/x/{row}_{col}.bin.gz', 'wb') as f: f.write(gz)
        index_x[f'{row}_{col}'] = [len(gz), hashlib.sha256(raw).hexdigest()[:12]]
    meta = {
        'format': FORMAT, 'tile': TILE, 'built': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'osm': stamp,
        # Where the extract came from (MAP_SOURCE, set by the job): Geofabrik's covers more than its fallback's, so check.py compares like with like.
        'source': os.environ.get('MAP_SOURCE', os.path.basename(pbf)),
        'classes': CLASSES, 'attribution': '© OpenStreetMap contributors, ODbL — openstreetmap.org/copyright',
        'tiles': index,
    }
    if index_h:
        # A separate file per area under its own credit: the map is OpenStreetMap's; the heights are Copernicus's.
        meta['heights'] = {'format': HEIGHTS_FORMAT, 'attribution': ATTRIBUTION, 'tiles': index_h}
    if lights is not None:
        meta['lights'] = {'attribution': street_lights.ATTRIBUTION}
    # Stops and places (EXTRAS.md): a file of their own, so phones that don't read them aren't touched.
    meta['extras'] = {'format': EXTRAS_FORMAT, 'tiles': index_x}
    with open(f'{out}/index.json', 'w') as f: json.dump(meta, f, separators=(',', ':'))
    big = sorted(index.items(), key=lambda kv: -kv[1][0])[:3]
    print(f'wrote {len(index)} areas, {total / 1e6:.1f} MB in all; largest {[(k, round(v[0] / 1e3)) for k, v in big]} KB; {time.time() - t0:.0f}s')


if __name__ == '__main__':
    build(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None, sys.argv[4] if len(sys.argv) > 4 else None)
