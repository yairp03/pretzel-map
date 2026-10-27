"""Run before a new map is published: every area reads back, and the map is
not smaller than Israel's map has ever been, nor much smaller than the one
phones have now. A broken or half-downloaded
extract would otherwise replace the whole country's map with less of it.

    python3 check.py <out dir> [live index URL]
"""
import gzip, json, sys, urllib.request
from build import decode, decode_extras, decode_heights

out = sys.argv[1]
live_url = sys.argv[2] if len(sys.argv) > 2 else 'https://map.pretzel.yairp.me/index.json'
with open(f'{out}/index.json') as f: new = json.load(f)


def israel(index):
    """The areas of Israel's map: every area but the cities abroad's (ABROAD.md), which come and go with their own build."""
    boxes = [c['box'] for c in index.get('abroad', {}).get('cities', [])]
    def abroad(name):
        row, col = map(int, name.split('_'))
        la, lo = (row + 0.5) * index['tile'], (col + 0.5) * index['tile']
        return any(s - 0.1 <= la <= n + 0.1 and w - 0.1 <= lo <= e + 0.1 for s, w, n, e in boxes)
    return {k: v for k, v in index['tiles'].items() if not abroad(k)}

segments = 0
for name in new['tiles']:
    with open(f'{out}/t/{name}.bin.gz', 'rb') as f: row, col, verts, segs = decode(gzip.decompress(f.read()))
    assert f'{row}_{col}' == name, f'{name} says it is {row}_{col}'
    segments += len(segs)
    # Its heights, when there are any: the same area, the same vertices and segments (the phone pairs them by position).
    if 'heights' in new:
        assert name in new['heights']['tiles'], f'{name} has no heights'
        with open(f'{out}/h/{name}.bin.gz', 'rb') as f: hrow, hcol, z, climbs = decode_heights(gzip.decompress(f.read()))
        assert (hrow, hcol, len(z), len(climbs)) == (row, col, len(verts), len(segs)), f'{name}: heights don’t match the map'
    # Its extras (EXTRAS.md): the same area and segments, paired by position too.
    assert name in new['extras']['tiles'], f'{name} has no extras'
    with open(f'{out}/x/{name}.bin.gz', 'rb') as f: xrow, xcol, stopped, _ = decode_extras(gzip.decompress(f.read()))
    assert (xrow, xcol, len(stopped)) == (row, col, len(segs)), f'{name}: extras don’t match the map'
# The place names (NAMES.md): there, and with about as many towns as Israel has (194 on 2026-10-23).
with open(f'{out}/names.json') as f: towns = len(json.load(f)['towns'])
assert towns >= 150 and new.get('names', {}).get('hash'), f'names.json: {towns} towns'
print(f'{len(new["tiles"])} areas, {segments} segments, {sum(v[0] for v in new["tiles"].values()) / 1e6:.1f} MB: all read back' + (', heights too' if 'heights' in new else '') + ', extras too')
# Each city abroad has its areas (the monthly build checked them), and they are in the map.
for c in new.get('abroad', {}).get('cities', []):
    s_, w_, n_, e_ = c['box']
    mine = [k for k in new['tiles'] if s_ - 0.1 <= (int(k.split('_')[0]) + 0.5) * new['tile'] <= n_ + 0.1 and w_ - 0.1 <= (int(k.split('_')[1]) + 0.5) * new['tile'] <= e_ + 0.1]
    assert len(mine) >= 10, f'{c["en"]}: {len(mine)} areas'
# From here, Israel's map alone: the cities abroad are compared with nothing.
new_il = israel(new)
size = sum(v[0] for v in new_il.values())
print(f'Israel: {len(new_il)} areas, {size / 1e6:.1f} MB; abroad: {len(new.get("abroad", {}).get("cities", []))} cities')

# Always, even when the published map can't be read: the first builds (2026-10-14) had 1,201 areas and 20.0 MB from
# Geofabrik, 1,045 and 16.2 MB from OpenStreetMap France's smaller extract, the fallback.
if len(new_il) < 950 or size < 14e6:
    sys.exit('the new map is smaller than Israel’s has ever been: not publishing it')

try:
    req = urllib.request.Request(live_url, headers={'User-Agent': 'pretzel-map (contact@yairp.me)'})
    live = json.load(urllib.request.urlopen(req, timeout=30))
except Exception as e:
    print(f'no map published yet to compare with ({e})')
    sys.exit(0)
live_il = israel(live)
live_size = sum(v[0] for v in live_il.values())
print(f'published now: Israel {len(live_il)} areas, {live_size / 1e6:.1f} MB, data of {live.get("osm")}')
if live.get('source') != new.get('source'):
    print(f'built from {new.get("source")}, the published one from {live.get("source")}: not compared')
elif len(new_il) < 0.95 * len(live_il) or size < 0.9 * live_size:
    sys.exit('the new map is much smaller than the published one: not publishing it')
