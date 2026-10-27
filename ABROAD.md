# Cities abroad

Fifteen cities beside Israel, so a runner abroad gets a route too ("I'm at a
hotel in Rome, give me 8 km"; the owner, 2026-10-27). Each city is
`abroad.json`'s centre (a public square, checked with Nominatim) and 12 km
each way: a square about 24 km across.

- **Built monthly** by `.github/workflows/abroad.yml`, one job per city:
  its country's Geofabrik extract, cut to the square (`osmium extract`),
  built as Israel is (`abroad.py city` → `build.py` with a `box`, the same
  rules, heights from Copernicus GLO-30, extras, names). A city that fails
  keeps last month's build.
- **Kept as the release `abroad`** (`abroad.tar.gz`, a folder per city
  with its own `index.json` and `city.json`), not in the repo's history.
- **Merged weekly** by `map.yml` into the map it publishes (`abroad.py
  merge`): the areas, heights and extras files beside Israel's, the names
  added to `names.json`, and in `index.json`:

```json
"abroad": { "merged": "…", "cities": [{ "id": "rome", "he": "רומא", "en": "Rome", "at": [41.8962, 12.4824], "box": [s, w, n, e], "osm": "…", "built": "…" }, …] }
```

- Each city is built on its own: one build over them all would make the
  20 m grids for green and sand span from New York to Cyprus.
- **West of Greenwich and south of the equator** an area's row or column
  is negative: its file names say so (`t/1030_-3.bin.gz`) and the files'
  headers hold it as 2³² + v (FORMAT.md) — Israel's files are unchanged.
- `check.py` holds Israel's map to its own floors and to the published one;
  each city needs 10 areas or more.
- Sizes (2026-10-27): Larnaca 24 areas, 0.5 MB; London 50 areas, 6.9 MB.

Map data © OpenStreetMap contributors, ODbL; heights from Copernicus GLO-30,
credited as `heights.py` says.
