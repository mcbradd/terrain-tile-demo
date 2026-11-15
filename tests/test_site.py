"""WP10: site assembly, serve, the G4 probe, every control of 13.5, the tour, and bench mode (SPEC 13.5, 13.7 to 13.9)."""
import json
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

import pytest

from tilepipe import config, site

ROOT = Path(__file__).resolve().parents[1]
AOI = config.default_aoi(ROOT)
NEEDS_DIST = pytest.mark.skipif(not (ROOT / "dist" / AOI / "tile.json").exists(), reason="run `tilepipe build` first")
NEEDS_NODE = pytest.mark.skipif(not shutil.which("node"), reason="node not found")


@pytest.fixture(scope="module")
def served():
    site.build(ROOT, AOI)
    server = site.make_server(ROOT, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@NEEDS_DIST
def test_site_tree_matches_13_9(served):
    out = ROOT / "site"
    for f in ("index.html", "app.js", "app.js.map", "styles.css", "config.json", ".nojekyll",
              "look/opaque.json", "look/additive.json"):
        assert (out / f).is_file(), f
    tile = json.loads((out / "data" / AOI / "tile.json").read_text(encoding="utf-8"))
    names = {p.name for p in (out / "data" / AOI).iterdir()}
    assert {"tile.json", "scene.json", "terrain_height.rg8.bin", "terrain_nao.rgba8.bin"} <= names
    for prof in tile["profiles"].values():
        assert {b["file"] for b in prof["batches"]} <= names
    assert not any("_lod" in n for n in names), "the 80 per-chunk LOD files are not hosted"
    assert json.loads((out / "config.json").read_text(encoding="utf-8")).keys() == {"video_url"}
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'" in html
    assert "__TILEPIPE_PROFILES__" not in (out / "app.js").read_text(encoding="utf-8")


@NEEDS_DIST
def test_serve_mime_types(served):
    for path, mime in ((f"data/{AOI}/terrain_workstation_b00.glb", "model/gltf-binary"),
                       (f"data/{AOI}/terrain_height.rg8.bin", "application/octet-stream"),
                       ("app.js", "text/javascript"), ("", "text/html")):
        with urllib.request.urlopen(f"{served}/{path}") as r:
            assert r.headers.get_content_type() == mime, path


@pytest.fixture(scope="module")
def browser_run(served, tmp_path_factory):
    out = tmp_path_factory.mktemp("bench") / "bench.json"
    r = subprocess.run(["node", str(ROOT / "tests" / "wp10_check.mjs"), served, "--bench-out", str(out)], cwd=ROOT,
                       capture_output=True, text=True, timeout=900)
    if r.returncode == 77:
        pytest.skip(r.stdout.strip())
    return r, out


@NEEDS_DIST
@NEEDS_NODE
def test_G4_probe(browser_run):
    r, _ = browser_run
    for line in ("probe line logged", "probe easting is E0 + 5120", "probe northing is N_top - 5120",
                 "probe elevation equals the height texture", "probe MGRS equals tile.mgrs.center"):
        assert f"PASS {line}" in r.stdout, r.stdout
    assert "FAIL" not in r.stdout, r.stdout


@NEEDS_DIST
@NEEDS_NODE
def test_controls_keys_and_tour(browser_run):
    r, _ = browser_run
    assert r.returncode == 0, r.stdout + r.stderr
    for line in ("key W toggles wireframe", "key H hides the HUD", "pointer input cancels the tour",
                 "tour ends with the initial profile and look", "same-origin requests only"):
        assert f"PASS {line}" in r.stdout, r.stdout


@NEEDS_DIST
@NEEDS_NODE
def test_bench_writes_valid_bench_json(browser_run):
    _, out = browser_run
    bench = json.loads(out.read_text(encoding="utf-8"))
    assert {"user_agent", "gpu", "canvas", "pixel_ratio", "profiles"} <= bench.keys()
    tile = json.loads((ROOT / "dist" / AOI / "tile.json").read_text(encoding="utf-8"))
    assert set(bench["profiles"]) == {"workstation", "mobile_ar"}
    for name, p in bench["profiles"].items():
        assert {"live_tris", "live_draws", "frame_ms_p50", "frame_ms_p95", "frac_longer_than_1p5_median"} <= p.keys()
        assert p["frames"] == 600 and p["frame_ms_p95"] >= p["frame_ms_p50"] > 0
        assert 0 <= p["frac_longer_than_1p5_median"] <= 1
        assert p["live_tris"] >= tile["profiles"][name]["terrain_tris"]
        assert p["live_draws"] >= tile["profiles"][name]["terrain_draws"]
