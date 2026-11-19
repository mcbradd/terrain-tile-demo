"""P1.3 overdraw view and report row, P1.5 slope-class overlay, P1.6 rise-in (SPEC 2.2). Browser part: tests/p1_check.mjs."""
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from tilepipe import config, site
from tilepipe.report.render import _overdraw

ROOT = Path(__file__).resolve().parents[1]
AOI = config.default_aoi(ROOT)
NEEDS_DIST = pytest.mark.skipif(not (ROOT / "dist" / AOI / "tile.json").exists(), reason="run `tilepipe build` first")
NEEDS_NODE = pytest.mark.skipif(not shutil.which("node"), reason="node not found")
DOC = {"canvas": {"width": 1920, "height": 1080}, "pixel_ratio": 1,
       "camera": {"view": "default", "target_m": [0, 0.05, 0], "distance_m": 1.9, "elevation_deg": 32,
                  "azimuth_deg": 150, "fov_deg": 40},
       "method": "Fragments per covered pixel.",
       "profiles": {"workstation": {"mean_overdraw": 1.25, "fragments": 125, "covered_px": 100},
                    "mobile_ar": {"mean_overdraw": 1.5, "fragments": 150, "covered_px": 100}}}


def test_overdraw_absent_is_none(tmp_path):
    assert _overdraw(tmp_path) is None


def test_overdraw_rows_and_camera(tmp_path):
    (tmp_path / "overdraw.json").write_text(json.dumps(DOC), encoding="utf-8")
    o = _overdraw(tmp_path)
    assert [(r["name"], r["mean_overdraw"]) for r in o["rows"]] == [("workstation", 1.25), ("mobile_ar", 1.5)]
    assert o["camera"] == ("default view: target (0, 0.05, 0) m, distance 1.9 m, elevation 32 deg, azimuth 150 deg, "
                           "vertical FOV 40 deg")


@NEEDS_DIST
def test_report_shows_overdraw_measured_or_not(tmp_path):
    from tilepipe.report.render import render
    doc = {"schema": 1, "aoi": AOI, "summary": {}, "results": []}
    html = render(ROOT, AOI, doc, out_dir=tmp_path).read_text(encoding="utf-8")
    assert "Mean overdraw [MEASURED]" in html
    if (config.build_dir(ROOT, AOI) / "overdraw.json").exists():
        assert "Measured in the viewer on the build machine at" in html and "No threshold applies." in html
    else:
        assert "Not measured." in html


def test_slope_overlay_is_off_by_default_and_split_at_15_and_30():
    src = (ROOT / "viewer" / "src" / "shaders" / "terrain.frag.glsl").read_text(encoding="utf-8")
    assert re.search(r"deg < 15\.0\).*\n.*deg < 30\.0\)", src)
    assert "mix(lit, tintLit, 0.6 * u_slopeClasses)" in src   # 0 leaves the 10.3 color unchanged
    assert re.search(r"slope: false", (ROOT / "viewer" / "src" / "main.js").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def p1_run(tmp_path_factory):
    site.build(ROOT, AOI)
    server = site.make_server(ROOT, 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    out = tmp_path_factory.mktemp("p1") / "overdraw.json"
    try:
        r = subprocess.run(["node", str(ROOT / "tests" / "p1_check.mjs"), f"http://127.0.0.1:{server.server_address[1]}",
                            "--overdraw-out", str(out)], cwd=ROOT, capture_output=True, text=True, timeout=600)
    finally:
        server.shutdown()
        server.server_close()
    if r.returncode == 77:
        pytest.skip(r.stdout.strip())
    return r, out


@NEEDS_DIST
@NEEDS_NODE
def test_p1_browser_check(p1_run):
    r, _ = p1_run
    assert r.returncode == 0, r.stdout + r.stderr
    for line in ("interactive first frame under 10 s", "rise-in lasts 1.2 s", "rise-in ends on the exact table transform",
                 "rise-in is skipped with ?probe=1", "key O selects the overdraw view", "Debug Overdraw radio",
                 "key S turns on slope classes", "slope legend is on screen and says illustrative",
                 "Slope classes checkbox turns it off", "overdraw.json per profile at the default view"):
        assert f"PASS {line}" in r.stdout, r.stdout


@NEEDS_DIST
@NEEDS_NODE
def test_p1_overdraw_json_feeds_the_report(p1_run):
    _, out = p1_run
    o = _overdraw(out.parent)
    assert {r["name"] for r in o["rows"]} == {"workstation", "mobile_ar"}
    assert all(r["mean_overdraw"] >= 1 and r["covered_px"] > 0 for r in o["rows"])
