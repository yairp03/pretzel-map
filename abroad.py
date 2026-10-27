"""Places abroad (ABROAD.md): each place of abroad.json — a city, 12 km
round its centre (or its own `km`), or an island's `box` — cut from its
country's Geofabrik extract and built as Israel is; then published by the
weekly job as regions beside Israel's (FORMAT.md → "Regions").

    python abroad.py city <id> <out dir> [extracts dir]        # one place
    python abroad.py extract <extract> <out root> [extracts dir]  # every place of one extract, as the monthly job builds them
    python abroad.py regions <site> <place dir>…               # Israel and the places, as regions, into the map the weekly job publishes

Each place is built on its own: built together, the map's 20 m grids for
green and sand would span from New York to Cyprus.
"""
import gzip, hashlib, json, math, os, shutil, subprocess, sys, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REGIONS_FORMAT = 1
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


def box_for(c, km):
    """A place's box: its own (an island, whole), or `km` round its centre (its own `km`, else abroad.json's)."""
    return tuple(c['box']) if 'box' in c else box_of(c['at'], c.get('km', km))


def city(cid, out, extracts='extracts'):
    """
    No heights abroad (2026-10-27): Copernicus GLO-30 is the surface, roofs
    included, and in an old city's narrow streets they bleed in — flat
    Whitehall climbed 19 m in 700 m, against 6 m along Tel Aviv's
    Dizengoff; London's flat routes came out "hilly". With no heights files
    the phone shows no climb for a route there, rather than a wrong one.
    """
    from build import build
    from names import make
    conf = cities()
    c = next(x for x in conf['cities'] if x['id'] == cid)
    box = box_for(c, conf['km'])
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
    os.environ['MAP_SOURCE'] = src
    build(cut, out, None, None, box)
    make(cut, out, box)
    with open(f'{out}/index.json') as f: index = json.load(f)
    if len(index['tiles']) < 10: sys.exit(f'{cid}: only {len(index["tiles"])} areas')
    # The data's date from the country's extract: the cut file's header doesn't carry it.
    import osmium
    stamp = index.get('osm') or osmium.io.Reader(pbf, osmium.osm.osm_entity_bits.NOTHING).header().get('osmosis_replication_timestamp', '')
    meta = {k: c[k] for k in ('id', 'he', 'en', 'at')} | {'box': list(box), 'osm': stamp, 'built': index['built']}
    with open(f'{out}/city.json', 'w') as f: json.dump(meta, f, ensure_ascii=False)
    print(f'{cid}: {len(index["tiles"])} areas, {sum(v[0] for v in index["tiles"].values()) / 1e6:.1f} MB')


def extract(name, root, extracts='extracts'):
    """Every place cut from one extract, downloaded once (Geofabrik's fair use; the monthly job runs one of these per
    extract). A place that fails is left out — the job keeps last month's — and the others still built."""
    ids = [c['id'] for c in cities()['cities'] if c['extract'] == name]
    done = 0
    for cid in ids:
        try:
            city(cid, f'{root}/{cid}', extracts)
            done += 1
        except (Exception, SystemExit) as e:
            print(f'{cid}: FAILED ({e})', flush=True)
    print(f'{name}: {done} of {len(ids)} places built')
    if not done: sys.exit(f'{name}: nothing built')


def sha12(body): return hashlib.sha256(body).hexdigest()[:12]


def write(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f: f.write(body)
    return {'hash': sha12(body), 'bytes': len(body), 'gzip': len(gzip.compress(body))}


def cells_box(index):
    """(south, west, north, east) round an index's areas."""
    rc = [tuple(map(int, k.split('_'))) for k in index['tiles']]
    t = index['tile']
    return [round(min(r for r, _ in rc) * t, 5), round(min(c for _, c in rc) * t, 5), round((max(r for r, _ in rc) + 1) * t, 5), round((max(c for _, c in rc) + 1) * t, 5)]


def regions(site, dirs):
    """
    The map as regions (FORMAT.md → "Regions"; the owner, 2026-10-27: a
    phone shouldn't fetch the index of fifty places on every opening): a
    small regions.json, and each region's own index (r/<id>.json) and place
    names (n/<id>.json), fetched only near where the runner is. Israel is
    one region, each place abroad another. Israel's index.json and
    names.json stay as they were, for phones on an app from before.
    """
    with open(f'{site}/index.json') as f: index = json.load(f)
    with open(f'{site}/names.json', 'rb') as f: il_names = f.read()
    part = lambda ix: {'tiles': ix['tiles'], 'heights': ix.get('heights', {}).get('tiles', {}), 'extras': ix.get('extras', {}).get('tiles', {})}
    body = lambda o: json.dumps(o, ensure_ascii=False, separators=(',', ':')).encode()
    box = cells_box(index)
    listed = [{'id': 'israel', 'he': 'ישראל', 'en': 'Israel', 'at': [32.0809, 34.7806], 'box': box, 'osm': index.get('osm', ''), 'built': index['built'],
               'source': index.get('source', ''), 'areas': len(index['tiles']), 'bytes': sum(v[0] for v in index['tiles'].values()),
               'index': write(f'{site}/r/israel.json', body(part(index))), 'names': write(f'{site}/n/israel.json', il_names)}]
    seen = set(index['tiles'])
    for d in sorted(dirs):
        if not os.path.exists(f'{d}/city.json'): continue
        with open(f'{d}/city.json') as f: meta = json.load(f)
        with open(f'{d}/index.json') as f: ci = json.load(f)
        # Two places sharing an area: one would replace the other's. abroad.json's places are apart (test_places_apart).
        shared = seen & set(ci['tiles'])
        assert not shared, f'{meta["id"]}: areas {sorted(shared)[:3]} are already in the map'
        seen |= set(ci['tiles'])
        for kind, key in (('t', 'tiles'), ('h', 'heights'), ('x', 'extras')):
            for name in (ci[key] if key == 'tiles' else ci.get(key, {}).get('tiles', {})):
                os.makedirs(f'{site}/{kind}', exist_ok=True)
                shutil.copy(f'{d}/{kind}/{name}.bin.gz', f'{site}/{kind}/{name}.bin.gz')
        with open(f'{d}/names.json', 'rb') as f: names = f.read()
        listed.append(meta | {'source': ci.get('source', ''), 'areas': len(ci['tiles']), 'bytes': sum(v[0] for v in ci['tiles'].values()),
                              'index': write(f'{site}/r/{meta["id"]}.json', body(part(ci))), 'names': write(f'{site}/n/{meta["id"]}.json', names)})
    out = {'format': REGIONS_FORMAT, 'map': index['format'], 'tile': index['tile'], 'classes': index['classes'], 'attribution': index.get('attribution', ''),
           'heights': {k: v for k, v in index.get('heights', {}).items() if k != 'tiles'}, 'extras': {k: v for k, v in index.get('extras', {}).items() if k != 'tiles'},
           'names': {'format': index.get('names', {}).get('format', 1)}, 'lights': index.get('lights', {}),
           'built': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'regions': listed}
    with open(f'{site}/regions.json', 'wb') as f: f.write(body(out))
    print(f'regions: Israel and {len(listed) - 1} places: {", ".join(c["en"] for c in listed[1:])}')


if __name__ == '__main__':
    if sys.argv[1] == 'city': city(*sys.argv[2:])
    elif sys.argv[1] == 'extract': extract(*sys.argv[2:])
    elif sys.argv[1] == 'regions': regions(sys.argv[2], sys.argv[3:])
    else: sys.exit(__doc__)
