# Place names, format 1

`names.json`, made by `names.py` beside the map, so Pretzel can say where a
run started ("Tel Aviv", "Old North") on the phone, with no lookup service
and nothing sent anywhere. Listed in `index.json` as
`"names": {"format": 1, "bytes": …, "gzip": …, "hash": "…"}` — a phone
fetches it again only when the hash changes. © OpenStreetMap contributors,
ODbL.

```json
{
  "format": 1,
  "towns": [{ "he": "תל־אביב–יפו", "en": "Tel-Aviv", "rings": [[[34.74, 32.04], …]] }, …],
  "places": [[34.865, 32.305, "הצפון הישן", "Old North", "n"], …]
}
```

- **towns**: municipalities' boundaries (`boundary=administrative`,
  `admin_level=8`), their outer rings, simplified to 25 m, as [longitude,
  latitude]. Regional councils are left out: they span dozens of villages,
  and a start in one is named by the village.
- **places**: points, [longitude, latitude, Hebrew, English, kind] — `s` a
  settlement (`place=city|town|village|hamlet`), for a start outside every
  town's boundary; `n` a neighbourhood (`place=suburb|neighbourhood|quarter`).
- Each name in Hebrew and English, each falling back on the other or on the
  plain `name` when OpenStreetMap lacks it.
