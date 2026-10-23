# pretzel-map — working context

The weekly job that makes Pretzel's map files (`build.py` → `site/`,
published to map.pretzel.yairp.me by `.github/workflows/map.yml`). The app,
its rules and its documents are in yairp03/pretzel (private): its
`docs/ARCHITECTURE.md` → "The map data" says why the map is made this way,
and its `lib/core/mapdata.ts` reads these files.

- **This repo is public.** Nothing personal in it beyond the owner's name
  and contact@yairp.me — no home, no test point but public places.
- **The format is a contract with phones already holding areas.** Change
  `FORMAT.md`, `build.py`'s `encode` and the app's reader together; a change
  that old readers can't read raises `FORMAT` (the app refuses other
  formats). `CLASSES` is only ever appended to.
- **What is kept matches Pretzel's feasibility test** (its
  `scripts/feasibility/pbf2json.py` and `loops.mjs`): the runnable-way
  filter, green and avoided areas, the 20 m raster, sampling every 10 m.
  Checked 2026-10-14 within 3 km of Netanya station: path length the same
  to 0.02%; green share 0.183 here against 0.174 there, avoided 0.163
  against 0.157 — the cells fall differently.
- **One class is made here, not read from OpenStreetMap: `beach`**, the
  path along the water on beaches (`beach_paths`; FORMAT.md). Added
  2026-10-15 at the owner's word: routes never went on the sand between
  Netanya's Argaman and Poleg beaches, which had no path there.
  It also takes in OpenStreetMap's own paths over the sand (2026-10-17):
  a path, track or footway 80% or more on a mapped beach or sand and not
  paved, or tagged `surface=sand`, is `beach` — about 22,000 segments,
  dunes included. A path by Wingate along the water wasn't "on the sand".
  **The shore counts only where it lies on mapped sand** (`SHORE_GROW = 0`,
  2026-10-23): OpenStreetMap draws some coasts as long straight strokes
  across a curving shore — 2.3 km across north Netanya — and with 40 m of
  slack the path along that stroke ran 20–50 m out in the sea, in the
  owner's saved route. A coast drawn straight because it *is* straight
  (Ashdod) lies on its beach and keeps its path. `test_no_beach_path_in_the_sea`.
- **Extras: stops and places** (`x/`, EXTRAS.md; the owner, 2026-10-23,
  for Pretzel's "fewer traffic lights" and water and toilets along a run):
  a file per area beside the map, like the heights, so phones that don't
  read it aren't touched; the segments in the map file's order.
- **Street lights from Tel Aviv-Yafo** (`lights.py`; the owner, 2026-10-19,
  under the city's open data terms: share and adapt for any purpose, with
  credit — the layer is on its map server, not in its open data catalogue).
  Poles only ever light an untagged way: in Tel Aviv 45% of untagged paths
  have poles along them against 14% of those tagged unlit, while streets
  tagged lit have them along only 70% (lights on the electricity company's
  poles aren't in the layer) — no pole is not dark. Credited in
  `index.json` and on the app's About. A week the city doesn't answer, the
  job builds with the last copy in its cache.
- **Place names** (`names.py` → `names.json`, NAMES.md; the owner,
  2026-10-23: saved routes and runs should say where they started): town
  boundaries and place points, so the phone names a start with nothing
  sent anywhere. Regional councils are left out (a kibbutz is named for
  itself).
- **Pages for this account redirects to yairp.me** (the account's own Pages
  site carries that domain), so this repo's Pages must keep its custom
  domain, map.pretzel.yairp.me (a CNAME to yairp03.github.io at Vercel's DNS).
- From a cloud session Geofabrik doesn't answer; OpenStreetMap France's copy
  does (the job tries both).
- Commit messages explain the why, and end with the co-author line.
