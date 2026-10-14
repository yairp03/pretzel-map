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
python build.py israel.osm.pbf site       # all of Israel: about 2 minutes, 2.3 GB of memory, 16 MB out
python check.py site                      # what the job checks before publishing
```

Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
available under the Open Database License (ODbL); the files here are a
database derived from it, under the same licence.
