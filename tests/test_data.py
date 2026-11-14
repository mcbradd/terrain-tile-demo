"""WP03 tests: T-PNG, geometry, fetch no-op, and one synthetic failing input per data guard DG-01 to DG-06."""
import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from tilepipe import cli, config, fetch, geo, png

ROOT = Path(__file__).resolve().parents[1]
AOI = "test_zone_01"
WIDE = "[0, 100000000]"


# ---------------------------------------------------------------- T-PNG

def _decode(path: Path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, []
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        assert struct.unpack(">I", data[pos + 8 + n:pos + 12 + n])[0] == zlib.crc32(tag + body), "bad CRC"
        chunks.append((tag, body))
        pos += 12 + n
    assert [t for t, _ in chunks] == [b"IHDR", b"IDAT", b"IEND"]
    w, h, depth, ctype, comp, filt, inter = struct.unpack(">IIBBBBB", chunks[0][1])
    assert (depth, comp, filt, inter) == (8, 0, 0, 0)
    raw = zlib.decompress(chunks[1][1])
    ch = {0: 1, 2: 3, 6: 4}[ctype]
    stride = 1 + w * ch
    assert len(raw) == h * stride
    rows = np.frombuffer(raw, np.uint8).reshape(h, stride)
    assert (rows[:, 0] == 0).all(), "filter type 0 on every row"
    img = rows[:, 1:].reshape(h, w, ch)
    return img[..., 0] if ch == 1 else img


@pytest.mark.parametrize("shape", [(7, 5), (7, 5, 3), (7, 5, 4)])
def test_PNG_roundtrip(tmp_path, shape):
    img = np.random.default_rng(1).integers(0, 256, shape, dtype=np.uint8)
    png.write_png(tmp_path / "a.png", img)
    assert np.array_equal(_decode(tmp_path / "a.png"), img)


def test_PNG_deterministic_and_rejects_bad_input(tmp_path):
    img = np.arange(64, dtype=np.uint8).reshape(8, 8)
    png.write_png(tmp_path / "a.png", img)
    png.write_png(tmp_path / "b.png", img)
    assert (tmp_path / "a.png").read_bytes() == (tmp_path / "b.png").read_bytes()
    with pytest.raises(ValueError):
        png.write_png(tmp_path / "c.png", img.astype("float32"))
    with pytest.raises(ValueError):
        png.write_png(tmp_path / "c.png", np.zeros((2, 2, 2), np.uint8))


# ---------------------------------------------------------------- geometry and fetch

def test_geo_tile_geometry_anza_borrego():
    g = geo.tile_geometry(config.load_aoi(ROOT, "anza_borrego_01"))
    assert (g["zone"], g["epsg"]) == (11, 32611)
    assert g["E0"] % 10 == 0 and g["N0"] % 10 == 0 and g["N_top"] == g["N0"] + 10240
    assert 545000 <= g["E0"] <= 551000 and 3674000 <= g["N0"] <= 3681000


def test_geo_southern_hemisphere_is_usage_error():
    with pytest.raises(config.UsageError):
        geo.tile_geometry({"center_lat": -10.0, "center_lon": 20.0})


def test_fetch_source_window_and_tiles():
    g = geo.tile_geometry(config.load_aoi(ROOT, "anza_borrego_01"))
    bbox = fetch.source_window(g, "EPSG:4269")
    assert fetch.source_tiles(bbox) == ["n34w117"]
    assert fetch.source_tiles((-117.01, 33.9, -116.99, 34.1)) == [
        "n34w117", "n34w118", "n35w117", "n35w118"]
    with pytest.raises(config.UsageError):
        fetch.source_tiles((-118.5, 33.5, -116.5, 35.5))


def test_fetch_is_noop_when_crop_exists(tmp_path, monkeypatch):
    (tmp_path / "data" / "source").mkdir(parents=True)
    (tmp_path / "data" / "source" / f"{AOI}_src.tif").write_bytes(b"x")
    (tmp_path / "data" / "source" / f"{AOI}_src.json").write_text("{}")
    monkeypatch.setattr(rasterio, "open", lambda *a, **k: pytest.fail("fetch touched the source"))
    fetch.fetch(tmp_path, AOI)  # would raise on any network or file access beyond the existence check


# ---------------------------------------------------------------- guards, end to end through the CLI (exit 4)

def _project(tmp_path, lat, lon, *, pixel=9.2593e-5, e_range=WIDE, n_range=WIDE, min_relief=500,
             hole=False) -> Path:
    """A tmp repo root with one synthetic AOI and a synthetic source crop of a 1000 m east-west ramp."""
    (tmp_path / "aois.toml").write_text(
        f'[{AOI}]\nname = "synthetic"\ncenter_lat = {lat}\ncenter_lon = {lon}\nmin_relief_m = {min_relief}\n'
        f"expect_e0_range = {e_range}\nexpect_n0_range = {n_range}\n")
    half = 0.08
    n = int(2 * half / pixel)
    ramp = np.tile(np.linspace(0, 1000, n, dtype="float32"), (n, 1))
    if hole:
        ramp[n // 2 - 20:n // 2 + 20, n // 2 - 20:n // 2 + 20] = -9999.0
    src = tmp_path / "data" / "source"
    src.mkdir(parents=True)
    with rasterio.open(src / f"{AOI}_src.tif", "w", driver="GTiff", height=n, width=n, count=1, dtype="float32",
                       crs="EPSG:4269", transform=from_origin(lon - half, lat + half, pixel, pixel),
                       nodata=-9999.0) as ds:
        ds.write(ramp, 1)
    return tmp_path


def _prep(root, monkeypatch, capsys):
    monkeypatch.chdir(root)
    code = cli.main(["build", "--to", "prep", "--aoi", AOI])
    return code, capsys.readouterr().err


def test_guard_pass_baseline_writes_outputs(tmp_path, monkeypatch, capsys):
    root = _project(tmp_path, 33.28, -116.43)
    code, err = _prep(root, monkeypatch, capsys)
    assert code == 0, err
    b = root / "build" / AOI
    h = np.load(b / "h_full.npy")
    assert h.shape == (1152, 1152) and h.dtype == np.float32 and not np.isnan(h).any()
    geo_json = json.loads((b / "geo.json").read_text())
    for name in ("preview_hillshade.png", "preview_hypso.png"):
        shape = _decode(b / name).shape
        assert shape[:2] == (1024, 1024), name
    assert geo_json["zone"] == 11 and geo_json["mgrs_center"]


@pytest.mark.parametrize("guard,kwargs,lat,lon", [
    ("DG-01", {}, 33.28, -119.99),                                          # apron box crosses the zone 10/11 edge
    ("DG-02", {}, 33.28, -117.00),                                          # E0 = 494880 crosses the 500 km line
    ("DG-03", {"hole": True}, 33.28, -116.43),                              # nodata block inside the raster
    ("DG-04", {"min_relief": 5000}, 33.28, -116.43),                        # ramp relief is about 640 m
    ("DG-05", {"e_range": "[1, 2]"}, 33.28, -116.43),                       # E0 outside the expected range
    ("DG-06", {"pixel": 1.0e-4}, 33.28, -116.43),                           # 1.0e-4 deg is above 9.5e-5
])
def test_guard_failure_exits_4_with_measured_and_expected(tmp_path, monkeypatch, capsys, guard, kwargs, lat, lon):
    root = _project(tmp_path, lat, lon, **kwargs)
    code, err = _prep(root, monkeypatch, capsys)
    assert code == 4, err
    assert f"{guard} FAIL: measured " in err and ", expected " in err, err
    assert not (root / "build" / AOI / "geo.json").exists()
