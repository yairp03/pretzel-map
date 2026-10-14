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
  "osm": "2026-10-13T00:55:40Z",
  "classes": ["other", "footway", "path", …],
  "attribution": "© OpenStreetMap contributors, ODbL — openstreetmap.org/copyright",
  "tiles": { "646_697": [66783, "3f2a9c01b7de"], … }
}
```

- `tile`: an area is a square of this many degrees. The area holding
  latitude `lat`, longitude `lon` is `floor(lat / tile)_floor(lon / tile)`.
- `osm`: when the extract's data was taken.
- `classes`: the kinds of path, by the number a segment carries. Only ever
  appended to, so a number keeps its meaning.
- `tiles`: each area that has any runnable way: its file's size in bytes,
  and a hash of its content. A phone downloads an area again only when the
  hash changes.

## `t/<row>_<col>.bin.gz`

Gzip, then bytes. A *varint* is an unsigned LEB128 number (7 bits a byte,
low first, the top bit set on every byte but the last). A *zigzag* number
is a signed one as a varint: 0, −1, 1, −2 … as 0, 1, 2, 3 …
Coordinates are in millionths of a degree (about 11 cm).

| Part | Contents |
|---|---|
| header | `PZM` and the format number as one byte (1); varint row, varint col |
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
