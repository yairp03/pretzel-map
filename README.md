# pretzel-map

The map [Pretzel](https://yairp.me) routes on: every way a runner may use in
Israel, from OpenStreetMap, cut into small areas a phone downloads once and
keeps — so a route can be made with no reception.

Rebuilt every Monday by GitHub Actions (`.github/workflows/map.yml`) from
Geofabrik's extract, and published at **https://map.pretzel.yairp.me**:
`index.json`, and `t/<row>_<col>.bin.gz` for each area. The format is
`FORMAT.md`.

```
pip install -r requirements.txt
python -m unittest -v                     # on test_map.osm, a small map drawn by hand
python lights.py lights.json              # Tel Aviv-Yafo's street-light poles (lights.py)
python build.py israel.osm.pbf site dem lights.json   # all of Israel, with heights (HEIGHTS.md) and lights: 20 MB out
python names.py israel.osm.pbf site      # place names for where a run starts (NAMES.md): after build.py
python check.py site                      # what the job checks before publishing
```

Fifteen cities abroad are built monthly beside it (`abroad.py`, `.github/workflows/abroad.yml`; ABROAD.md):

```
python abroad.py city london out/london   # one city: its country's extract, cut and built
python abroad.py merge site out/*          # into the weekly map
```

Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
available under the Open Database License (ODbL); the files here are a
database derived from it, under the same licence.

Street lights in Tel Aviv-Yafo: Tel Aviv-Yafo Municipality, open data
(`lights.py`), used only to mark ways lit where OpenStreetMap doesn't say.
