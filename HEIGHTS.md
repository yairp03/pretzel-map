# The heights files, format 1

How much a route climbs. Made by `build.py` from Copernicus GLO-30 (30 m)
through `heights.py`; read by Pretzel's phone beside the map files
(FORMAT.md). A separate file per area, under its own credit:

> Produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus
> Defence and Space GmbH 2014-2018 provided under COPERNICUS by the
> European Union and ESA; all rights reserved.

## In `index.json`

```json
"heights": { "format": 1, "attribution": "Heights: Copernicus WorldDEM-30 …", "tiles": { "646_697": [5120, "9b1c…"], … } }
```

The same areas as `tiles`; each its size and a hash of its content. Absent
when the map was built without heights: a phone then shows no climbs.

## `h/<row>_<col>.bin.gz`

Gzip, then bytes; varints and zigzag numbers as in FORMAT.md. Heights in
decimetres.

| Part | Contents |
|---|---|
| header | `PZH` and the format number as one byte (1); varint row, varint col |
| vertices | varint count; per vertex, its height as a zigzag difference from the previous vertex's (the first from 0) |
| segments | varint count; per segment, varint climb forward (from `a` to `b`), varint climb back |

- The vertices and segments are the area's map file's, **in the same
  order**: the phone pairs them by position. Built together, from one run.
- Heights are smoothed over 3×3 cells (~90 m) of the 30 m grid, then
  sampled every 10 m along each segment: the climb either way is the sum
  of the rises between those samples. Copernicus measures surfaces, not
  bare ground; on streets it matched a bare-ground model within ~10%
  (Netanya; Dizengoff and Ibn Gvirol, Tel Aviv — 2026-10-17).
- The sea, or anywhere without a tile, is 0.
