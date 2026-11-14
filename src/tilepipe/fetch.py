"""Stage `fetch` (SPEC 5.4). The only command besides `uv sync` and `npm ci` that uses the network."""
import hashlib
import math
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import rasterio
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.transform import array_bounds
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window, from_bounds

from tilepipe import config, geo

CREDIT = "Elevation: U.S. Geological Survey, 3D Elevation Program, 1/3 arc-second DEM. Public domain."
PRIMARY = ("https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/13/TIFF/current/"
           "{tile}/USGS_13_{tile}.tif")
FALLBACK = ("https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/"
            "{tile}/USGS_13_{tile}.tif")
MARGIN_DEG = 0.005
HTTP_TIMEOUT_S = 180
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_TIMEOUT": str(HTTP_TIMEOUT_S),
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif"}


def source_window(geometry: dict, src_crs: str) -> tuple[float, float, float, float]:
    """5.4 step 1: bounding box (west, south, east, north) in source degrees, expanded by 0.005 per side."""
    pts = geo.apron_points(geometry, edge_midpoints=True)
    xs, ys = warp_transform(f"EPSG:{geometry['epsg']}", src_crs, [p[0] for p in pts], [p[1] for p in pts])
    return (min(xs) - MARGIN_DEG, min(ys) - MARGIN_DEG, max(xs) + MARGIN_DEG, max(ys) + MARGIN_DEG)


def source_tiles(bbox: tuple[float, float, float, float]) -> list[str]:
    """5.4 step 2: names `n{NN}w{WWW}` (named for the north and west edges) of the 3DEP tiles the window touches."""
    west, south, east, north = bbox
    if east >= 0 or south < 0:
        raise config.UsageError("3DEP tile naming here covers the northern and western hemispheres only")
    names = [f"n{n:02d}w{w:03d}" for n in range(math.floor(south) + 1, math.ceil(north) + 1)
             for w in range(math.floor(-east) + 1, math.ceil(-west) + 1)]
    if len(names) > 4:
        raise config.UsageError(f"source window touches {len(names)} tiles, more than 4 (SPEC 5.4)")
    return names


def _read_window(src: str, bbox):
    """Read the part of `bbox` that lies in the raster at `src` (URL or path). Returns array, transform, crs, nodata."""
    with rasterio.open(src) as ds:
        win = from_bounds(*bbox, transform=ds.transform)
        c0, r0 = math.floor(win.col_off), math.floor(win.row_off)  # round outward; rasterio 1.5 dropped round(op=)
        c1, r1 = math.ceil(win.col_off + win.width), math.ceil(win.row_off + win.height)
        win = Window(c0, r0, c1 - c0, r1 - r0).intersection(Window(0, 0, ds.width, ds.height))
        return ds.read(1, window=win).astype("float32"), ds.window_transform(win), ds.crs, ds.nodata


def _download(url: str, dest: Path) -> None:
    """Whole-file download with resume (5.4 step 3 last resort)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as r, open(part, "ab" if have and r.status == 206 else "wb") as f:
        while block := r.read(1 << 20):
            f.write(block)
    part.replace(dest)


def _head(url: str) -> dict:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as r:
            return {"last_modified": r.headers.get("Last-Modified"), "etag": r.headers.get("ETag")}
    except OSError:
        return {"last_modified": None, "etag": None}


def _fetch_tile(root: Path, tile: str, bbox):
    """Primary URL, then fallback, then whole-file download. Returns (piece, url used)."""
    urls = [u.format(tile=tile) for u in (PRIMARY, FALLBACK)]
    with rasterio.Env(**GDAL_ENV):
        for url in urls:
            try:
                return _read_window("/vsicurl/" + url, bbox), url
            except Exception as e:  # rasterio raises several error classes for HTTP and GDAL failures
                print(f"fetch: windowed read of {url} failed: {e}")
        dest = root / "data" / "cache" / f"USGS_13_{tile}.tif"
        _download(urls[0], dest)
        return _read_window(str(dest), bbox), urls[0]


def fetch(root: Path, aoi: str, refresh: bool = False) -> None:
    out = root / "data" / "source"
    tif, meta = out / f"{aoi}_src.tif", out / f"{aoi}_src.json"
    if tif.exists() and meta.exists() and not refresh:
        print(f"fetch: {tif.relative_to(root).as_posix()} exists; nothing to do")
        return
    geometry = geo.tile_geometry(config.load_aoi(root, aoi))
    # The source CRS is read from the file (expected EPSG:4269); 3DEP 1/3 arc-second tiles are all NAD83 geographic.
    bbox = source_window(geometry, "EPSG:4269")
    tiles = source_tiles(bbox)
    pieces, used = [], []
    with rasterio.Env(**GDAL_ENV):
        for tile in tiles:
            piece, url = _fetch_tile(root, tile, bbox)
            pieces.append(piece)
            used.append({"tile": tile, "url": url, **_head(url)})
    crs, nodata = pieces[0][2], pieces[0][3]
    if crs.to_epsg() != 4269:
        print(f"fetch: warning: source CRS is {crs}, expected EPSG:4269")
    mems, datasets = [], []
    try:
        for arr, transform, crs_, nd in pieces:
            m = MemoryFile()
            mems.append(m)
            ds = m.open(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype="float32",
                        crs=crs_, transform=transform, nodata=nd)
            ds.write(arr, 1)
            datasets.append(ds)
        data, transform = merge(datasets, method="first", nodata=nodata) if len(datasets) > 1 else (
            pieces[0][0][None], pieces[0][1])
    finally:
        for x in datasets + mems:
            x.close()
    out.mkdir(parents=True, exist_ok=True)
    with rasterio.open(tif, "w", driver="GTiff", height=data.shape[1], width=data.shape[2], count=1, dtype="float32",
                       crs=crs, transform=transform, nodata=nodata, compress="deflate", predictor=3) as dst:
        dst.write(data.astype("float32"))
    w, s, e, n = array_bounds(data.shape[1], data.shape[2], transform)
    config.write_json(meta, {
        "credit": CREDIT,
        "crop_sha256": hashlib.sha256(tif.read_bytes()).hexdigest(),
        "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_crs": str(crs),
        "tiles": used,
        "urls": [u["url"] for u in used],
        "window_bounds": {"west": w, "south": s, "east": e, "north": n},
    })
    print(f"fetch: wrote {tif.relative_to(root).as_posix()} ({data.shape[2]} x {data.shape[1]} px, {len(tiles)} source tile(s))")
