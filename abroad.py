"""Cities abroad (ABROAD.md): each city of abroad.json, 12 km round its
centre, cut from its country's Geofabrik extract and built as Israel is;
then merged into the weekly map.

    python abroad.py city <id> <out dir> [extracts dir] [dem dir]   # one city, as the monthly job builds it
    python abroad.py merge <site> <city dir>…                     # into the map the weekly job publishes

Each city is built on its own: built together, the map's 20 m grids for
green and sand would span from New York to Cyprus.
"""
import gzip, hashlib, json, math, os, shutil, subprocess, sys, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {'User-Agent': 'pretzel-map (contact@yairp.me)'}


def cities():
    with open(os.path.join(HERE, 'abroad.json')) as f: return json.load(f)


def box_of(at, km):
    """(south, west, north, east): `km` each way from the centre."""
    la, lo = at
    dla = km / 111.32
    dlo = km / (111.32 * math.cos(math.radians(la)))
    return (round(la - dla, 5), round(lo - dlo, 5), round(la + dla, 5), round(lo + dlo, 5))


def fetch(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0: return True
    tmp = path + '.part'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r, open(tmp, 'wb') as f:
            shutil.copyfileobj(r, f, 1 << 20)
    except Exception as e:
        print(f'{url}: {e}', flush=True)
        if os.path.exists(tmp): os.remove(tmp)
        return False
    os.replace(tmp, path)
    return True


def dem_tiles(box, dem):
    """Copernicus GLO-30's 1° tiles over the box (as the weekly job fetches Israel's), named N51W001.tif and so on."""
    os.makedirs(dem, exist_ok=True)
    s, w, n, e = box
    for la in range(math.floor(s), math.floor(n) + 1):
        for lo in range(math.floor(w), math.floor(e) + 1):
            ns, ew = f'{"N" if la >= 0 else "S"}{abs(la):02d}', f'{"E" if lo >= 0 else "W"}{abs(lo):03d}'
            name = f'Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM'
            # Over the sea there is no tile: none fetched, heights 0 there.
            fetch(f'https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif', os.path.join(dem, f'{ns}{ew}.tif'))


def city(cid, out, extracts='extracts', dem='dem-abroad'):
    from build import build
    from names import make
    conf = cities()
    c = next(x for x in conf['cities'] if x['id'] == cid)
    box = box_of(c['at'], conf['km'])
    os.makedirs(extracts, exist_ok=True)
    src = f'https://download.geofabrik.de/{c["extract"]}-latest.osm.pbf'
    pbf = os.path.join(extracts, c['extract'].replace('/', '_') + '.osm.pbf')
    if not fetch(src, pbf): sys.exit(f'{cid}: no extract')
    # With osmium-tool there (the job installs it), the city is cut out first: reading a whole country in Python takes
    # minutes. Without it, build.py reads the whole extract and keeps the box.
    cut = pbf
    if shutil.which('osmium'):
        cut = os.path.join(extracts, f'{cid}.osm.pbf')
        s, w, n, e = box
        subprocess.run(['osmium', 'extract', '-b', f'{w},{s},{e},{n}', '-s', 'complete_ways', '--overwrite', '-o', cut, pbf], check=True)
    dem_tiles(box, dem)
    os.environ['MAP_SOURCE'] = src
    build(cut, out, dem, None, box)
    make(cut, out, box)
    with open(f'{out}/index.json') as f: index = json.load(f)
    if len(index['tiles']) < 10: sys.exit(f'{cid}: only {len(index["tiles"])} areas')
    meta = {k: c[k] for k in ('id', 'he', 'en', 'at')} | {'box': list(box), 'osm': index.get('osm', ''), 'built': index['built']}
    with open(f'{out}/city.json', 'w') as f: json.dump(meta, f, ensure_ascii=False)
    print(f'{cid}: {len(index["tiles"])} areas, {sum(v[0] for v in index["tiles"].values()) / 1e6:.1f} MB')


def merge(site, dirs):
    """Each city's areas, heights, extras and names into the site; `abroad` in its index says which cities and where."""
    with open(f'{site}/index.json') as f: index = json.load(f)
    with open(f'{site}/names.json', 'rb') as f: names = json.load(f)
    listed = []
    for d in sorted(dirs):
        if not os.path.exists(f'{d}/city.json'): continue
        with open(f'{d}/city.json') as f: meta = json.load(f)
        with open(f'{d}/index.json') as f: ci = json.load(f)
        for part, key in (('t', 'tiles'), ('h', 'heights'), ('x', 'extras')):
            got = ci[key] if key == 'tiles' else ci.get(key, {}).get('tiles', {})
            mine = index[key] if key == 'tiles' else index.setdefault(key, {}).setdefault('tiles', {})
            for name, v in got.items():
                # Two places sharing an area: the second would replace the first's. None of the cities is that close.
                assert name not in mine, f'{meta["id"]}: area {name} is already in the map'
                os.makedirs(f'{site}/{part}', exist_ok=True)
                shutil.copy(f'{d}/{part}/{name}.bin.gz', f'{site}/{part}/{name}.bin.gz')
                mine[name] = v
        if os.path.exists(f'{d}/names.json'):
            with open(f'{d}/names.json', 'rb') as f: n = json.load(f)
            names['towns'] += n['towns']
            names['places'] += n['places']
        listed.append(meta)
    body = json.dumps(names, ensure_ascii=False, separators=(',', ':')).encode()
    with open(f'{site}/names.json', 'wb') as f: f.write(body)
    index['names'] = {**index.get('names', {}), 'bytes': len(body), 'gzip': len(gzip.compress(body)), 'hash': hashlib.sha256(body).hexdigest()[:12]}
    index['abroad'] = {'merged': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'cities': listed}
    with open(f'{site}/index.json', 'w') as f: json.dump(index, f, separators=(',', ':'), ensure_ascii=False)
    print(f'abroad: {len(listed)} cities merged: {", ".join(c["en"] for c in listed)}')


if __name__ == '__main__':
    if sys.argv[1] == 'city': city(*sys.argv[2:])
    elif sys.argv[1] == 'merge': merge(sys.argv[2], sys.argv[3:])
    else: sys.exit(__doc__)
