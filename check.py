"""Run before a new map is published: every area reads back, and the map is
not smaller than Israel's map has ever been, nor much smaller than the one
phones have now. A broken or half-downloaded
extract would otherwise replace the whole country's map with less of it.

    python3 check.py <out dir> [live index URL]
"""
import gzip, json, sys, urllib.request
from build import decode, decode_heights

out = sys.argv[1]
live_url = sys.argv[2] if len(sys.argv) > 2 else 'https://map.pretzel.yairp.me/index.json'
with open(f'{out}/index.json') as f: new = json.load(f)

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
size = sum(v[0] for v in new['tiles'].values())
print(f'{len(new["tiles"])} areas, {segments} segments, {size / 1e6:.1f} MB: all read back' + (', heights too' if 'heights' in new else ''))

# Always, even when the published map can't be read: the first builds (2026-10-14) had 1,201 areas and 20.0 MB from
# Geofabrik, 1,045 and 16.2 MB from OpenStreetMap France's smaller extract, the fallback.
if len(new['tiles']) < 950 or size < 14e6:
    sys.exit('the new map is smaller than Israel’s has ever been: not publishing it')

try:
    req = urllib.request.Request(live_url, headers={'User-Agent': 'pretzel-map (contact@yairp.me)'})
    live = json.load(urllib.request.urlopen(req, timeout=30))
except Exception as e:
    print(f'no map published yet to compare with ({e})')
    sys.exit(0)
live_size = sum(v[0] for v in live['tiles'].values())
print(f'published now: {len(live["tiles"])} areas, {live_size / 1e6:.1f} MB, data of {live.get("osm")}')
if live.get('source') != new.get('source'):
    print(f'built from {new.get("source")}, the published one from {live.get("source")}: not compared')
elif len(new['tiles']) < 0.95 * len(live['tiles']) or size < 0.9 * live_size:
    sys.exit('the new map is much smaller than the published one: not publishing it')
