"""Street lights, for night routes: Tel Aviv-Yafo's light poles, from the
municipality's map server (layer "עמודי מאור", ~52,000 poles, refreshed
daily), used under its open data terms — share and adapt for any purpose,
with credit (opendatasource.tel-aviv.gov.il; the owner's choice,
2026-10-19).

OpenStreetMap rarely says whether a way is lit (about 6% of streets round
Netanya). Measured in Tel Aviv: 45% of its untagged paths have poles along
them, against 14% of those tagged unlit — poles mean lit. No pole doesn't
mean dark: even streets tagged lit have poles along only 70% of them (many
lights hang on the electricity company's poles, not in this layer). So a
way the map doesn't light-tag becomes lit when poles stand along it; a tag
is never overruled, and nothing is made dark.

    python lights.py <out.json>     # the poles, as [[lat, lon], …]
"""
import json, math, sys, time, urllib.parse, urllib.request
import numpy as np

URL = 'https://gisn.tel-aviv.gov.il/arcgis/rest/services/IView2/MapServer/543/query'
ATTRIBUTION = 'Street lights in Tel Aviv-Yafo: Tel Aviv-Yafo Municipality, open data'
PAGE = 2000          # the server's most per request
REACH = 20           # metres: a pole this near lights the way
SHARE = 0.6          # of the way's points every 10 m
STEP = 10


def fetch(out):
    """Every pole, page by page, with retries; refuses a result far smaller than expected."""
    pts, off = [], 0
    while True:
        q = urllib.parse.urlencode({'where': '1=1', 'outFields': 'oid_amud', 'outSR': 4326, 'orderByFields': 'oid_amud',
                                    'resultOffset': off, 'resultRecordCount': PAGE, 'f': 'json'})
        for attempt in range(4):
            try:
                req = urllib.request.Request(f'{URL}?{q}', headers={'User-Agent': 'pretzel-map (contact@yairp.me)'})
                with urllib.request.urlopen(req, timeout=60) as r:
                    page = json.load(r)['features']
                break
            except Exception as e:
                if attempt == 3: raise
                print(f'retrying page {off}: {e}', flush=True)
                time.sleep(5 * (attempt + 1))
        pts += [[round(f['geometry']['y'], 7), round(f['geometry']['x'], 7)] for f in page if f.get('geometry')]
        if len(page) < PAGE: break
        off += PAGE
    # 52,134 on 2026-10-19: far fewer is a broken answer, not the city taking its lights down.
    if len(pts) < 30000: raise SystemExit(f'only {len(pts)} poles: not used')
    with open(out, 'w') as f: json.dump(pts, f, separators=(',', ':'))
    print(f'{len(pts)} poles')


def lit_by_poles(edges, poles, unknown=0, lit=1):
    """
    edges: [(shape [(lat, lon)…], cls, lit), …]. Those whose lit is
    `unknown` and with a pole within REACH of SHARE of their points (every
    STEP metres) become `lit`. Returns the edges and how many changed.
    """
    if not poles: return edges, 0
    P = np.asarray(poles, float)
    lat0 = float(P[:, 0].mean())
    ky, kx = 111320.0, 111320.0 * math.cos(math.radians(lat0))
    cell = {}
    for la, lo in P:
        cell.setdefault((math.floor(la * ky / REACH), math.floor(lo * kx / REACH)), []).append((la * ky, lo * kx))
    lo_la, hi_la = P[:, 0].min() - .001, P[:, 0].max() + .001
    lo_lo, hi_lo = P[:, 1].min() - .001, P[:, 1].max() + .001

    def near(y, x):
        cy, cx = math.floor(y / REACH), math.floor(x / REACH)
        for a in (-1, 0, 1):
            for b in (-1, 0, 1):
                for py, px in cell.get((cy + a, cx + b), ()):
                    if (py - y) ** 2 + (px - x) ** 2 <= REACH * REACH: return True
        return False

    out, changed = [], 0
    for shape, cls, l in edges:
        if l != unknown or not any(lo_la <= la <= hi_la and lo_lo <= lo <= hi_lo for la, lo in shape):
            out.append((shape, cls, l))
            continue
        n = hit = 0
        for (a_la, a_lo), (b_la, b_lo) in zip(shape, shape[1:]):
            ay, ax, by, bx = a_la * ky, a_lo * kx, b_la * ky, b_lo * kx
            steps = max(1, round(math.hypot(by - ay, bx - ax) / STEP))
            for s in range(steps):
                t = s / steps
                n += 1
                hit += near(ay + t * (by - ay), ax + t * (bx - ax))
        n += 1
        hit += near(shape[-1][0] * ky, shape[-1][1] * kx)
        if hit >= SHARE * n:
            out.append((shape, cls, lit))
            changed += 1
        else:
            out.append((shape, cls, l))
    return out, changed


if __name__ == '__main__':
    fetch(sys.argv[1])
