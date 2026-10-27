# Places abroad

Fifty places beside Israel, so a runner abroad gets a route too ("I'm at a
hotel in Rome, give me 8 km"; the owner, 2026-10-27: fifteen cities, then
"up to 50 cities that are popular for Israelis" the same day). Each is in
`abroad.json`:

- **A city**: its centre (a public square, checked with Nominatim) and
  12 km each way — a square about 24 km across. Two reach further, where a
  runner's places are far apart: **Dubai** 18 km (Downtown to the Marina,
  19 km), **Los Angeles** 16 km, centred between Downtown and Santa
  Monica (23 km apart).
- **An island, whole** (`box`): **Cyprus** (in place of Larnaca and
  Limassol: one region from Paphos to Ayia Napa), **Crete**, **Rhodes**
  and **Phuket** — small, spread out, and where a holiday is.

- **Built monthly** by `.github/workflows/abroad.yml`, **one job per
  extract**, downloaded once for all its places (Geofabrik's fair use:
  Greece's 342 MB serves Athens, Thessaloniki, Crete and Rhodes): cut to
  each place (`osmium extract`), built as Israel is (`abroad.py extract` →
  `city` → `build.py` with a `box`, the same rules, extras, names) — **but
  no heights**: Copernicus GLO-30 is the
  surface, roofs included, and in an old city's narrow streets they bleed
  in (flat Whitehall climbed 19 m in 700 m, Tel Aviv's Dizengoff 6 m); a
  route there shows no climb rather than a wrong one. FABDEM, the same
  with buildings taken out, is non-commercial and its server failed
  downloads (heights.py). A place that fails
  keeps last month's build.
- **Kept as the release `abroad`** (`abroad.tar.gz`, a folder per place
  with its own `index.json`, `names.json` and `city.json`), not in the
  repo's history.
- **Published weekly** by `map.yml` as regions (`abroad.py regions`;
  FORMAT.md → "Regions"): the areas' files beside Israel's, and for each
  place its own index and names — a phone fetches only those of where it
  is. Israel's `index.json` and `names.json` stay Israel's alone.
- Each city is built on its own: one build over them all would make the
  20 m grids for green and sand span from New York to Cyprus.
- **West of Greenwich and south of the equator** an area's row or column
  is negative: its file names say so (`t/1030_-3.bin.gz`) and the files'
  headers hold it as 2³² + v (FORMAT.md) — Israel's files are unchanged.
- `check.py` holds Israel's map to its own floors and to the published one;
  each place needs 10 areas or more, and no area may be in two regions
  (`test_places_apart` checks abroad.json before a build).
- Sizes (2026-10-27): Larnaca 24 areas, 0.5 MB; London 50 areas, 6.9 MB.

Map data © OpenStreetMap contributors, ODbL.
