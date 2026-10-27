# The map files, format 1

What `build.py` writes and Pretzel's phone reads (`lib/core/mapdata.ts`
in the app). Everything is OpenStreetMap's data: © OpenStreetMap
contributors, ODbL.

## `index.json`

```json
{
  "format": 1,
  "tile": 0.05,
  "built": "2026-10-14T21:05:51Z",
  "osm": "2026-10-13T20:21:31Z",
  "source": "https://download.geofabrik.de/asia/israel-and-palestine-latest.osm.pbf",
  "classes": ["other", "footway", "path", …],
  "attribution": "© OpenStreetMap contributors, ODbL — openstreetmap.org/copyright",
  "tiles": { "646_697": [66783, "3f2a9c01b7de"], … }
}
```

- `tile`: an area is a square of this many degrees. The area holding
  latitude `lat`, longitude `lon` is `floor(lat / tile)_floor(lon / tile)`.
- `osm`: when the extract's data was taken; `source`: where it came from.
- `classes`: the kinds of path, by the number a segment carries. Only ever
  appended to, so a number keeps its meaning.
- `tiles`: each area that has any runnable way: its file's size in bytes,
  and a hash of its content. A phone downloads an area again only when the
  hash changes.
- `lights` (when street lights were used): `{"attribution": …}`, their
  source's credit. A segment's lit is then also 1 where OpenStreetMap
  doesn't say and Tel Aviv-Yafo's light poles stand within 20 m of 60% of
  it, every 10 m (`lights.py`); a tag of OpenStreetMap's is never
  overruled, and no segment is made unlit by them.

Since the regions (below), `index.json` is Israel's alone, as phones on
an app from before them read it.

## Regions: `regions.json`, `r/<id>.json`, `n/<id>.json`

The map is Israel and fifty places abroad (ABROAD.md). One index of them
all, fetched on every opening, would grow with each place for a runner who
never leaves Tel Aviv (the owner, 2026-10-27). So the phone fetches a small
list of regions, and only the regions it is near (`abroad.py regions`):

```json
{
  "format": 1, "map": 1, "tile": 0.05, "classes": [...], "attribution": "...",
  "heights": { "format": 1, "attribution": "..." }, "extras": { "format": 1 }, "names": { "format": 1 },
  "lights": { "attribution": "..." }, "built": "...",
  "regions": [
    { "id": "israel", "he": "ישראל", "en": "Israel", "at": [lat, lon], "box": [s, w, n, e],
      "osm": "...", "built": "...", "source": "...", "areas": 1249, "bytes": 20112345,
      "index": { "hash": "…", "bytes": …, "gzip": … }, "names": { "hash": "…", "bytes": …, "gzip": … } },
    …
  ]
}
```

- `map`: the area files' format (`index.json`'s `format`); `format` is
  this file's own.
- A region's `box` holds all its areas; `at` is where it is named for (a
  city's centre, an island's main town).
- `r/<id>.json`: the region's areas as `index.json` lists them, its
  heights' and extras' too: `{"tiles": {…}, "heights": {…}, "extras":
  {…}}`. `n/<id>.json`: its place names (NAMES.md). Each is fetched again
  only when its `hash` changes (SHA-256 of the file, 12 hex digits).
- No area is in two regions (`regions` refuses it; `check.py` checks it).
- Israel is the first region, and its `r/` file lists exactly
  `index.json`'s areas; its `n/` file is `names.json`.

## `t/<row>_<col>.bin.gz`

Gzip, then bytes. A *varint* is an unsigned LEB128 number (7 bits a byte,
low first, the top bit set on every byte but the last). A *zigzag* number
is a signed one as a varint: 0, −1, 1, −2 … as 0, 1, 2, 3 …
Coordinates are in millionths of a degree (about 11 cm).

| Part | Contents |
|---|---|
| header | `PZM` and the format number as one byte (1); varint row, varint col — a negative one (west of Greenwich, south of the equator: ABROAD.md) as 2³² + v, so every area of Israel's is the same bytes as ever |
| vertices | varint count; per vertex, zigzag latitude and zigzag longitude, each as the difference from the previous vertex (the first from 0) |
| segments | varint count; per segment: varint `a`, varint `b` (vertex numbers in this file), then four bytes — class, lit (0 unknown, 1 yes, 2 no), green (0–255), avoided (0–255) — then varint length in decimetres, varint count of shape points, and per shape point a zigzag latitude and longitude difference from the point before (the first from vertex `a`) |

- A **vertex** is where ways meet or a way ends; a **segment** runs between
  two of them, along its shape points, in the way's own direction.
- An area holds the segments that **start** in it. A segment's `b` may lie
  in another area: it is still listed in this file's vertices, and the
  phone joins areas by matching vertices' coordinates.
- **Green** is the share of the segment, sampled every 10 m, within 20 m
  of a park, garden, grass, wood or beach, or 40 m of water, as 0–255.
  **Avoided** is its share inside industrial, commercial or retail land,
  farmland, orchards, construction, railway land, military land, quarries
  or landfill.
- Car one-way streets are not marked: a runner may run either way.
- **The class `beach` is not an OpenStreetMap way.** OpenStreetMap has
  no path along the water on most beaches, so the job makes one: the
  coastline where it lies on a mapped beach or sand (no slack: a coast
  drawn as a long straight stroke across a curving shore lies in the sea
  there, and gets no path), 12 m onto
  the sand, gaps of up to 300 m between beaches bridged, in stretches of
  200 m or more; and short `beach` segments joining it to the runnable
  ways that reach the sand (each such way's node to the nearest point
  within 120 m, one join every 150 m, never across a mapped cliff). Its
  vertices are made by the job too. Lit is "no".
  Also `beach`: an OpenStreetMap path, track or footway lying 80% or more
  on a mapped beach or sand and not paved (`surface` asphalt, paving
  stones, wood and the like), or any path tagged `surface=sand` — it is on
  the sand, whatever its kind. Its lit stays as tagged, else "no".
