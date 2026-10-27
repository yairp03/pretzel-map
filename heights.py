"""Heights, for how much a route climbs: Copernicus GLO-30 (the owner's
choice, 2026-10-17, of three; FABDEM, bare ground, was his first, but the
University of Bristol's file server reset every download). Copernicus
measures surfaces, not bare ground, but on streets it matched a bare-ground
model within ~10% (Netanya, Dizengoff and Ibn Gvirol in Tel Aviv).

Each 1° tile is smoothed over 3×3 cells (~90 m), so a single noisy cell
isn't a climb; a path is then sampled every 10 m. What the files carry
(HEIGHTS.md): each vertex's height, and each segment's climb either way.

Produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus
Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European
Union and ESA; all rights reserved.
"""
import glob, math, os, re
import numpy as np

ATTRIBUTION = ('Heights: Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 '
               'provided under COPERNICUS by the European Union and ESA; all rights reserved')
R = 6371008.8


def _blur(a):
    """3×3 box average, edges padded with their own values."""
    p = np.pad(a, 1, mode='edge')
    return sum(p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9


class Heights:
    """Height in metres at any point: from tiles (from_dir) or a function (tests). Sea, or no tile: 0."""

    def __init__(self, tiles=None, fn=None):
        self.tiles, self.fn = tiles or {}, fn

    @classmethod
    def from_dir(cls, d):
        import rasterio
        tiles = {}
        for path in sorted(glob.glob(os.path.join(d, '*.tif'))):
            # N32E034, or anywhere: S… is south of the equator, W… west of Greenwich (cities abroad, ABROAD.md).
            m = re.search(r'([NS])(\d+)([EW])(\d+)', os.path.basename(path))
            if not m: continue
            la = int(m.group(2)) * (1 if m.group(1) == 'N' else -1)
            lo = int(m.group(4)) * (1 if m.group(3) == 'E' else -1)
            with rasterio.open(path) as ds:
                a = ds.read(1).astype(np.float32)
                a[~np.isfinite(a) | (a < -100)] = 0
                # Inverse transform: row, col of a point (pixel centres).
                tiles[(la, lo)] = (_blur(a), ~ds.transform)
        return cls(tiles)

    @classmethod
    def from_function(cls, fn):
        return cls(fn=fn)

    def at(self, lat, lon):
        """Heights at arrays of points, bilinear between cell centres."""
        lat, lon = np.asarray(lat, float), np.asarray(lon, float)
        if self.fn: return np.asarray(self.fn(lat, lon), float)
        out = np.zeros(lat.shape)
        # Each point's 1° tile, as (lat, lon) — west and south of zero too, which one number of lat·1000 + lon mixed up.
        tl, tn = np.floor(lat).astype(int), np.floor(lon).astype(int)
        for la, lo in {(int(x), int(y)) for x, y in zip(tl.ravel(), tn.ravel())}:
            t = self.tiles.get((la, lo))
            if t is None: continue
            a, inv = t
            sel = (tl == la) & (tn == lo)
            col, row = inv * (lon[sel], lat[sel])
            col, row = np.asarray(col) - 0.5, np.asarray(row) - 0.5
            r0 = np.clip(np.floor(row).astype(int), 0, a.shape[0] - 2)
            c0 = np.clip(np.floor(col).astype(int), 0, a.shape[1] - 2)
            fr, fc = np.clip(row - r0, 0, 1), np.clip(col - c0, 0, 1)
            out[sel] = (a[r0, c0] * (1 - fr) * (1 - fc) + a[r0, c0 + 1] * (1 - fr) * fc
                        + a[r0 + 1, c0] * fr * (1 - fc) + a[r0 + 1, c0 + 1] * fr * fc)
        return out


def climbs(heights, edges, step=10):
    """
    For each segment (shape points as (lat, lon)): its climb forward and
    backward in metres, from heights every `step` metres along it, and the
    heights at its two ends.
    """
    a_lat, a_lon, b_lat, b_lon, owner = [], [], [], [], []
    for k, (shape, *_) in enumerate(edges):
        for p, q in zip(shape, shape[1:]):
            a_lat.append(p[0]); a_lon.append(p[1]); b_lat.append(q[0]); b_lon.append(q[1]); owner.append(k)
    a_lat, a_lon, b_lat, b_lon, owner = map(np.array, (a_lat, a_lon, b_lat, b_lon, owner))
    r = math.pi / 180
    d = 2 * R * np.arcsin(np.sqrt(np.sin((b_lat - a_lat) * r / 2) ** 2 + np.cos(a_lat * r) * np.cos(b_lat * r) * np.sin((b_lon - a_lon) * r / 2) ** 2))
    m = np.maximum(np.ceil(d / step).astype(np.int64), 1)
    # Sample points: each piece from its start, m points; plus each segment's last point.
    piece = np.repeat(np.arange(len(m)), m)
    s = (np.arange(len(piece)) - np.repeat(np.cumsum(m) - m, m)) / np.repeat(m, m)
    la = a_lat[piece] + (b_lat[piece] - a_lat[piece]) * s
    lo = a_lon[piece] + (b_lon[piece] - a_lon[piece]) * s
    seg = owner[piece]
    z = heights.at(la, lo)
    end_z = heights.at(np.array([e[0][-1][0] for e in edges]), np.array([e[0][-1][1] for e in edges]))
    start_z = heights.at(np.array([e[0][0][0] for e in edges]), np.array([e[0][0][1] for e in edges]))
    # Rises between consecutive samples of the same segment, then the last sample to the segment's end.
    up = np.zeros(len(edges)); down = np.zeros(len(edges))
    same = seg[1:] == seg[:-1]
    dz = np.diff(z)[same]
    np.add.at(up, seg[1:][same], np.maximum(dz, 0))
    np.add.at(down, seg[1:][same], np.maximum(-dz, 0))
    last = np.r_[np.nonzero(~same)[0], len(seg) - 1]
    tail = end_z[seg[last]] - z[last]
    np.add.at(up, seg[last], np.maximum(tail, 0))
    np.add.at(down, seg[last], np.maximum(-tail, 0))
    return up, down, start_z, end_z
