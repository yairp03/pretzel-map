# The extras files, format 1

What a runner meets along the way: traffic lights and crossings on each
segment, for routes with fewer stops; and drinking water and toilets,
shown along a route. Made by `build.py`; read by Pretzel's phone beside the
map files (FORMAT.md). A separate file per area, so a phone that doesn't
read them is not touched (added 2026-10-23). Everything is OpenStreetMap's
data: © OpenStreetMap contributors, ODbL.

## In `index.json`

```json
"extras": { "format": 1, "tiles": { "646_697": [812, "5d0e…"], … } }
```

The same areas as `tiles`; each its size and a hash of its content.

## `x/<row>_<col>.bin.gz`

Gzip, then bytes; varints and zigzag numbers as in FORMAT.md.

| Part | Contents |
|---|---|
| header | `PZX` and the format number as one byte (1); varint row, varint col |
| segments | varint count; per segment, varint lights, varint crossings — both in halves |
| places | varint count; per place, one byte kind (1 drinking water, 2 toilets), then zigzag latitude and longitude in millionths of a degree, each as the difference from the previous place's (the first from 0) |

- The segments are the area's map file's, **in the same order**: the phone
  pairs them by position. Built together, from one run.
- **A light** is a node tagged `highway=traffic_signals`, or a crossing
  with lights (`highway=crossing` with `crossing=traffic_signals` or
  `crossing:signals=yes`); **a crossing** is any other `highway=crossing`
  but `crossing=no`. A stop inside a segment counts whole (2); one at its
  end, where it meets others, counts half (1) to each, so a route through
  it counts it once.
- **Drinking water**: `amenity=drinking_water`, or `amenity=fountain`
  with `drinking_water=yes`. **Toilets**: `amenity=toilets`. Neither when
  `access` is `private`, `no` or `customers`. A place mapped as a closed
  way (toilets in a building) stands at the middle of its outline.
- Each place is in the area it stands in, sorted by kind, then latitude,
  then longitude. Places in an area with no paths are left out: no route
  reaches them.
