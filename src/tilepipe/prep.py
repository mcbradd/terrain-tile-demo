"""Stage `prep` (SPEC 7.1) and the data guards DG-01 to DG-06 (SPEC 5.5)."""
import math
from pathlib import Path

import mgrs
import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

from tilepipe import config, geo
from tilepipe.config import GuardError
from tilepipe.png import write_png

SIZE, APRON, CELL = 1152, 64, 10.0
SRC_PIXEL_RANGE = (9.0e-5, 9.5e-5)

# Hypsometric ramp: (t in 0..1, RGB). Preview only.
_RAMP = [(0.0, (70, 110, 70)), (0.25, (170, 175, 100)), (0.5, (205, 170, 110)),
         (0.75, (150, 110, 85)), (1.0, (245, 240, 235))]


def _fmt(x) -> str:
    return f"{x:.6g}" if isinstance(x, float) else str(x)


# ---------------------------------------------------------------- guards (5.5); each raises GuardError

def guard_single_zone(geometry: dict) -> None:
    """DG-01: all four apron-box corners lie inside the 6-degree band of `zone`."""
    lons = [p[0] for p in geo.to_lonlat(geometry["epsg"], geo.apron_points(geometry))]
    lo, hi = (geometry["zone"] - 1) * 6 - 180, geometry["zone"] * 6 - 180
    if not (lo <= min(lons) and max(lons) <= hi):
        raise GuardError("DG-01", f"corner longitudes {_fmt(min(lons))} to {_fmt(max(lons))}",
                         f"inside [{lo}, {hi}] (zone {geometry['zone']})")


def guard_single_mgrs_square(geometry: dict) -> None:
    """DG-02: the tile (E0 to E0 + 10240, N0 to N_top) lies in one 100 km square."""
    e0, n0, n_top = geometry["E0"], geometry["N0"], geometry["N_top"]
    e1 = e0 + geo.TILE_M
    if e0 // 100000 != e1 // 100000 or n0 // 100000 != n_top // 100000:
        raise GuardError("DG-02", f"E {e0} to {e1}, N {n0} to {n_top} (100 km indices E {e0 // 100000} to "
                         f"{e1 // 100000}, N {n0 // 100000} to {n_top // 100000})",
                         "one 100 km index in E and one in N")


def guard_origin(geometry: dict, aoi: dict) -> None:
    """DG-05: E0 and N0 fall inside the AOI's expected ranges."""
    for key, rng in (("E0", aoi["expect_e0_range"]), ("N0", aoi["expect_n0_range"])):
        if not rng[0] <= geometry[key] <= rng[1]:
            raise GuardError("DG-05", f"{key} = {geometry[key]}", f"{key} in [{rng[0]}, {rng[1]}]")


def guard_resolution(transform: Affine) -> None:
    """DG-06: source pixel size in degrees is between 9.0e-5 and 9.5e-5."""
    lo, hi = SRC_PIXEL_RANGE
    for name, size in (("x", abs(transform.a)), ("y", abs(transform.e))):
        if not lo <= size <= hi:
            raise GuardError("DG-06", f"{name} pixel size {_fmt(size)} deg", f"between {lo} and {hi} deg")


def guard_no_voids(h_full: np.ndarray) -> None:
    """DG-03: no NaN (reprojection writes NaN for nodata and for cells outside the source) in the raster."""
    bad = int(np.isnan(h_full).sum())
    if bad:
        raise GuardError("DG-03", f"{bad} NaN cells of {h_full.size}", "0 NaN or nodata cells")


def guard_relief(h_full: np.ndarray, min_relief_m: float) -> None:
    """DG-04: max minus min over the central 1024 by 1024 is at least `min_relief_m`."""
    c = h_full[APRON:SIZE - APRON, APRON:SIZE - APRON].astype("float64")
    relief = float(c.max() - c.min())
    if relief < min_relief_m:
        raise GuardError("DG-04", f"relief {_fmt(relief)} m", f">= {_fmt(float(min_relief_m))} m")


# ---------------------------------------------------------------- raster and previews

def reproject_dem(src_path: Path, geometry: dict) -> np.ndarray:
    """7.1 step 2: band 1 of the source crop to the canonical 1152 x 1152 float32 raster."""
    dst = np.full((SIZE, SIZE), np.nan, dtype="float32")
    with rasterio.open(src_path) as ds:
        reproject(source=ds.read(1).astype("float32"), destination=dst,
                  src_transform=ds.transform, src_crs=ds.crs, src_nodata=ds.nodata,
                  dst_transform=Affine(CELL, 0, geometry["E0"] - geo.APRON_M, 0, -CELL, geometry["N_top"] + geo.APRON_M),
                  dst_crs=f"EPSG:{geometry['epsg']}", dst_nodata=np.nan,
                  resampling=Resampling.bilinear, num_threads=1)
    return dst


def hillshade(h_full: np.ndarray, azimuth_deg: float = 315.0, altitude_deg: float = 45.0) -> np.ndarray:
    """uint8 1024 x 1024 shading of the tile cells. Gradients come from the full raster so tile edges are exact."""
    dz_drow, dz_dcol = np.gradient(h_full.astype("float64"), CELL)
    dz_east, dz_north = dz_dcol, -dz_drow  # row 0 is north
    az, alt = math.radians(azimuth_deg), math.radians(altitude_deg)
    light = (math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt))
    shade = (-dz_east * light[0] - dz_north * light[1] + light[2]) / np.sqrt(dz_east ** 2 + dz_north ** 2 + 1.0)
    return np.round(np.clip(shade, 0, 1)[APRON:SIZE - APRON, APRON:SIZE - APRON] * 255).astype("uint8")


def hypso(h_full: np.ndarray, h_min: float, h_max: float) -> np.ndarray:
    """uint8 1024 x 1024 x 3 hypsometric tint of the tile cells, blended with the hillshade."""
    t = (h_full[APRON:SIZE - APRON, APRON:SIZE - APRON].astype("float64") - h_min) / (h_max - h_min)
    ts, cols = [r[0] for r in _RAMP], np.array([r[1] for r in _RAMP], dtype="float64")
    rgb = np.stack([np.interp(t, ts, cols[:, i]) for i in range(3)], axis=-1)
    light = hillshade(h_full).astype("float64") / 255.0
    return np.round(np.clip(rgb * (0.45 + 0.55 * light[..., None]), 0, 255)).astype("uint8")


def mgrs_string(geometry: dict) -> tuple[str, float, float]:
    """MGRS string at 1 m precision of the tile center, with the latitude and longitude it came from."""
    (lon, lat), = geo.to_lonlat(geometry["epsg"], [(geometry["E0"] + geo.TILE_M / 2, geometry["N0"] + geo.TILE_M / 2)])
    return mgrs.MGRS().toMGRS(lat, lon, MGRSPrecision=5), lat, lon


def run(root: Path, aoi: str) -> None:
    rec = config.load_aoi(root, aoi)
    geometry = geo.tile_geometry(rec)
    guard_origin(geometry, rec)
    guard_single_zone(geometry)
    guard_single_mgrs_square(geometry)
    src = root / "data" / "source" / f"{aoi}_src.tif"
    if not src.exists():
        raise config.UsageError(f"{src.relative_to(root).as_posix()} not found; run `tilepipe fetch --aoi {aoi}`")
    with rasterio.open(src) as ds:
        guard_resolution(ds.transform)
    h_full = reproject_dem(src, geometry)
    guard_no_voids(h_full)
    guard_relief(h_full, rec["min_relief_m"])
    tile = h_full[APRON:SIZE - APRON, APRON:SIZE - APRON].astype("float64")
    h_min, h_max = float(tile.min()), float(tile.max())
    if h_max - h_min < 1.0:
        raise GuardError("H-RANGE", f"h_max - h_min = {_fmt(h_max - h_min)} m", ">= 1.0 m")
    mgrs_center, lat, lon = mgrs_string(geometry)
    out = config.build_dir(root, aoi)
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "h_full.npy", h_full)
    config.write_json(out / "geo.json", {**{k: geometry[k] for k in ("zone", "epsg", "E0", "N0", "N_top")},
                                         "h_min": h_min, "h_max": h_max, "mgrs_center": mgrs_center})
    write_png(out / "preview_hillshade.png", hillshade(h_full))
    write_png(out / "preview_hypso.png", hypso(h_full, h_min, h_max))
    print(f"prep: guards DG-01 to DG-06 pass; zone {geometry['zone']} (EPSG:{geometry['epsg']}), "
          f"E0 {geometry['E0']}, N0 {geometry['N0']}, N_top {geometry['N_top']}, h {h_min:.1f} to {h_max:.1f} m")
    print(f"prep: tile center lat {lat:.6f}, lon {lon:.6f}, "
          f"UTM E {geometry['E0'] + geo.TILE_M // 2}, N {geometry['N0'] + geo.TILE_M // 2}, MGRS {mgrs_center}")
