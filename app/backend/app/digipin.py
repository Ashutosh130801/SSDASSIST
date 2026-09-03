"""DIGIPIN — India Post's open, offline geo-code (a 10-character code for a ~4m x 4m square).

Reversible: encode(lat, lon) -> "XXX-XXX-XXXX"  and  decode(code) -> (lat, lon) centre.
No API, no key, no network — pure arithmetic over India's bounding box, subdivided into a
4x4 grid ten times. We store a DIGIPIN on every located case as a clean, shareable location
handle. (Algorithm per the Department of Posts public-domain reference.)
"""

# Symbol grid — row 0 is the TOP (highest latitude), col 0 is the LEFT (lowest longitude).
_GRID = [
    ["F", "C", "9", "8"],
    ["J", "3", "2", "7"],
    ["K", "4", "5", "6"],
    ["L", "M", "P", "T"],
]

# India bounding box used by DIGIPIN.
_MIN_LAT, _MAX_LAT = 2.5, 38.5
_MIN_LON, _MAX_LON = 63.5, 99.5

_CHAR_POS = {ch: (r, c) for r, row in enumerate(_GRID) for c, ch in enumerate(row)}


def encode(lat: float, lon: float) -> str | None:
    """lat/lon -> DIGIPIN string, or None if outside India's bounds."""
    if lat is None or lon is None:
        return None
    if not (_MIN_LAT <= lat <= _MAX_LAT and _MIN_LON <= lon <= _MAX_LON):
        return None
    min_lat, max_lat, min_lon, max_lon = _MIN_LAT, _MAX_LAT, _MIN_LON, _MAX_LON
    out = []
    for level in range(1, 11):
        lat_div = (max_lat - min_lat) / 4.0
        lon_div = (max_lon - min_lon) / 4.0
        # row counted from the TOP (max latitude) downwards
        row = 3 - int((lat - min_lat) / lat_div)
        col = int((lon - min_lon) / lon_div)
        row = 0 if row < 0 else 3 if row > 3 else row
        col = 0 if col < 0 else 3 if col > 3 else col
        out.append(_GRID[row][col])
        if level == 3 or level == 6:
            out.append("-")
        # narrow the box to the chosen cell (compute new edges before overwriting)
        new_max_lat = min_lat + lat_div * (4 - row)
        new_min_lat = min_lat + lat_div * (3 - row)
        new_min_lon = min_lon + lon_div * col
        new_max_lon = min_lon + lon_div * (col + 1)
        min_lat, max_lat, min_lon, max_lon = new_min_lat, new_max_lat, new_min_lon, new_max_lon
    return "".join(out)


def decode(code: str) -> tuple[float, float] | None:
    """DIGIPIN string -> (lat, lon) at the centre of its ~4m cell, or None if malformed."""
    if not code:
        return None
    chars = [c for c in code.upper() if c != "-" and not c.isspace()]
    if len(chars) != 10 or any(c not in _CHAR_POS for c in chars):
        return None
    min_lat, max_lat, min_lon, max_lon = _MIN_LAT, _MAX_LAT, _MIN_LON, _MAX_LON
    for ch in chars:
        row, col = _CHAR_POS[ch]
        lat_div = (max_lat - min_lat) / 4.0
        lon_div = (max_lon - min_lon) / 4.0
        new_max_lat = min_lat + lat_div * (4 - row)
        new_min_lat = min_lat + lat_div * (3 - row)
        new_min_lon = min_lon + lon_div * col
        new_max_lon = min_lon + lon_div * (col + 1)
        min_lat, max_lat, min_lon, max_lon = new_min_lat, new_max_lat, new_min_lon, new_max_lon
    return round((min_lat + max_lat) / 2.0, 6), round((min_lon + max_lon) / 2.0, 6)


if __name__ == "__main__":  # quick round-trip self-test
    for (la, lo) in [(17.7331, 83.2497), (22.2433683, 73.2019148), (28.6139, 77.2090)]:
        code = encode(la, lo)
        back = decode(code)
        err_m = 0.0
        if back:
            import math
            dlat = (back[0] - la) * 111_000
            dlon = (back[1] - lo) * 111_000 * math.cos(math.radians(la))
            err_m = round(math.hypot(dlat, dlon), 1)
        print(f"{la},{lo} -> {code} -> {back}  (~{err_m} m)")
