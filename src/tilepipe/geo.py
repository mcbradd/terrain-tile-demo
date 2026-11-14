"""Tile geometry and geodesy helpers (SPEC 5.3, 6.1)."""
import math

from rasterio.warp import transform

from tilepipe.config import UsageError

TILE_M = 10240
APRON_M = 640


def tile_geometry(aoi: dict) -> dict:
    """5.3 steps 1 to 3. Reads only `center_lat` and `center_lon` from the AOI record."""
    if aoi["center_lat"] < 0:
        raise UsageError("southern-hemisphere AOI centers are not supported (SPEC 5.3)")
    zone = math.floor((aoi["center_lon"] + 180) / 6) + 1
    epsg = 32600 + zone
    xs, ys = transform("EPSG:4326", f"EPSG:{epsg}", [aoi["center_lon"]], [aoi["center_lat"]])
    e0 = math.floor((xs[0] - TILE_M / 2) / 10) * 10
    n0 = math.floor((ys[0] - TILE_M / 2) / 10) * 10
    return {"zone": zone, "epsg": epsg, "E0": e0, "N0": n0, "N_top": n0 + TILE_M}


def apron_box(geo: dict) -> tuple[float, float, float, float]:
    """5.3 step 4: (west, south, east, north) in the projected CRS."""
    return (geo["E0"] - APRON_M, geo["N0"] - APRON_M, geo["E0"] + TILE_M + APRON_M, geo["N_top"] + APRON_M)


def apron_points(geo: dict, edge_midpoints: bool = False) -> list[tuple[float, float]]:
    w, s, e, n = apron_box(geo)
    pts = [(w, s), (e, s), (e, n), (w, n)]
    if edge_midpoints:
        pts += [((w + e) / 2, s), (e, (s + n) / 2), ((w + e) / 2, n), (w, (s + n) / 2)]
    return pts


def to_lonlat(epsg: int, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Projected (E, N) points to (lon, lat)."""
    lons, lats = transform(f"EPSG:{epsg}", "EPSG:4326", [p[0] for p in points], [p[1] for p in points])
    return list(zip(lons, lats))
