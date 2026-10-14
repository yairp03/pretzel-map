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
- **Pages for this account redirects to yairp.me** (the account's own Pages
  site carries that domain), so this repo's Pages must keep its custom
  domain, map.pretzel.yairp.me (a CNAME to yairp03.github.io at Vercel's DNS).
- From a cloud session Geofabrik doesn't answer; OpenStreetMap France's copy
  does (the job tries both).
- Commit messages explain the why, and end with the co-author line.
