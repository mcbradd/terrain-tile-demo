"""Geodesy rules (SPEC 12.4): GEO-01 to GEO-03."""
import re

import mgrs
import numpy as np
import rasterio
from rasterio.warp import transform

from tilepipe.validate import common
from tilepipe.validate.registry import check_result, implements, skip

SEED, POINTS, INSET_M = 20261113, 1000, 100.0
MEDIAN_MAX_M, P95_MAX_M = 0.5, 5.0
_MGRS = re.compile(r"^(\d{1,2}[C-X])([A-Z]{2})(\d{5})(\d{5})$")


def source_path(ctx):
    return ctx.root / "data" / "source" / f"{ctx.aoi}_src.tif"


@implements("GEO-01")
def geo01(ctx, scope):
    g = common.geo_json(ctx)
    hf = common.h_full(ctx)
    rng = np.random.default_rng(SEED)
    x = rng.uniform(INSET_M, common.TILE_M - INSET_M, POINTS)
    z = rng.uniform(INSET_M, common.TILE_M - INSET_M, POINTS)
    e, n = g["E0"] + x, g["N_top"] - z
    # H_full pixel (row, col) has its center at E = E0 - 640 + 10 col + 5, N = N_top + 640 - 10 row - 5.
    mine = common.bilinear(hf, (e - (g["E0"] - 640)) / 10 - 0.5, (g["N_top"] + 640 - n) / 10 - 0.5)
    with rasterio.open(source_path(ctx)) as ds:
        arr = ds.read(1).astype(np.float64)
        if ds.nodata is not None:
            arr[arr == ds.nodata] = np.nan
        lon, lat = transform(f"EPSG:{g['epsg']}", ds.crs, list(e), list(n))
        inv, lon, lat = ~ds.transform, np.array(lon), np.array(lat)
        col, row = inv.a * lon + inv.b * lat + inv.c, inv.d * lon + inv.e * lat + inv.f
    src = common.bilinear(arr, col - 0.5, row - 0.5)
    d = np.abs(mine - src)
    med, p95 = float(np.nanmedian(d)), float(np.nanpercentile(d, 95))
    return common.multi("GEO-01", scope, [("m median", round(med, 4), MEDIAN_MAX_M, "<="),
                                          ("m p95", round(p95, 4), P95_MAX_M, "<=")],
                        "H_full is misregistered against the source crop; check the reproject transform of 7.1.")


def _digits(lat_lon_m: tuple[float, float], epsg: int) -> str:
    lon, lat = transform(f"EPSG:{epsg}", "EPSG:4326", [lat_lon_m[0]], [lat_lon_m[1]])
    return mgrs.MGRS().toMGRS(lat[0], lon[0], MGRSPrecision=5)


@implements("GEO-02")
def geo02(ctx, scope):
    g = common.geo_json(ctx)
    if not g.get("mgrs_center"):
        return skip("GEO-02", scope, "MGRS is cut (P0.9): geo.json has no mgrs_center")
    e0, n0, nt, t = g["E0"], g["N0"], g["N_top"], common.TILE_M
    pts = [(e0 + t / 2, n0 + t / 2), (e0 + INSET_M, n0 + INSET_M), (e0 + t - INSET_M, n0 + INSET_M),
           (e0 + INSET_M, nt - INSET_M), (e0 + t - INSET_M, nt - INSET_M)]
    bad, grids, worst = [], set(), 0.0
    for i, (e, n) in enumerate(pts):
        s = _digits((e, n), g["epsg"])
        if i == 0 and s != g["mgrs_center"]:
            bad.append(f"geo.json mgrs_center {g['mgrs_center']} differs from {s} at the tile center")
        m = _MGRS.match(s)
        if not m:
            bad.append(f"unparseable MGRS {s!r}")
            continue
        grids.add((m[1], m[2]))
        for got, want, axis in ((int(m[3]), e % 1e5, "E"), (int(m[4]), n % 1e5, "N")):
            worst = max(worst, abs(got - int(want)))
            if abs(got - int(want)) > 1:
                bad.append(f"{axis} digits {got} differ from {int(want)} at ({e:.0f}, {n:.0f})")
    if len(grids) > 1:
        bad.append(f"points fall in {len(grids)} zone and square pairs")
    if g["mgrs_center"][:2] != f"{g['zone']:02d}":
        bad.append("mgrs_center zone differs from geo.json zone")
    tile_mgrs = common.tile(ctx).get("mgrs")
    if tile_mgrs and tile_mgrs["center"] != g["mgrs_center"]:
        bad.append(f"tile.json mgrs.center {tile_mgrs['center']} differs from geo.json {g['mgrs_center']}")
    return check_result("GEO-02", scope, not bad, worst if not bad else len(bad), 1,
                        "m" if not bad else "mismatches", "<=",
                        f"MGRS and UTM disagree. First: {bad[0]}." if bad else "")


@implements("GEO-03")
def geo03(ctx, scope):
    g = common.geo_json(ctx)
    r = max(g["E0"] % 10, g["N0"] % 10)
    return check_result("GEO-03", scope, g["E0"] % 10 == 0 and g["N0"] % 10 == 0, r, 0, "m",
                        "<=", "Round E0 and N0 down to a multiple of 10 (5.3).")
