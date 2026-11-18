"""WP08 report render test (SPEC 14.1): 12 headings in order, required sentences, no script, no off-origin URL."""
import re
from pathlib import Path

import pytest

from tilepipe import cli, config
from tilepipe.report.render import ACCURACY, render

ROOT = Path(__file__).resolve().parent.parent
AOI = "anza_borrego_01"
HEADINGS = ["Header", "Verdict", "Budgets", "LOD selection", "LOD error table", "Rules", "Entities",
            "Fixture matrix", "Registration and accuracy", "Scale estimate", "Provenance", "Assumptions"]
SENTENCES = ["No headset performance was measured.", "Static validation only. No headset performance was measured.",
             "Linear extrapolation from one measured tile on one machine. Not a measurement."]


@pytest.fixture(scope="module")
def html() -> str:
    if not (config.dist_dir(ROOT, AOI) / "tile.json").exists():
        assert cli.build(ROOT, AOI) == 0
    doc = {"schema": 1, "aoi": AOI, "summary": {"tile": {"pass": 1, "warn": 0, "fail": 0, "skip": 0}},
           "results": [{"rule": "GEO-01", "severity": "FAIL", "status": "PASS", "scope": "tile", "measured": 1.0,
                        "limit": 2.0, "unit": "m", "message": "GEO-01 PASS tile: measured 1 m, limit <= 2 m.",
                        "fix_hint": ""},
                       {"rule": "PERF-01", "severity": "WARN", "status": "PASS", "scope": "tile", "measured": 0.0,
                        "limit": 0.02, "unit": "fraction", "message": "PERF-01 PASS tile: smoke.",
                        "fix_hint": ""}]}
    return render(ROOT, AOI, doc).read_text(encoding="utf-8")


def test_twelve_headings_in_order(html):
    found = re.findall(r"<h2>\s*(\d+)\.\s*([^<]+?)\s*</h2>", html)
    assert [int(n) for n, _ in found] == list(range(1, 13))
    assert [t for _, t in found] == HEADINGS


def test_required_sentences_verbatim(html):
    plain = html.replace("&#34;", '"')
    for s in SENTENCES:
        assert s in plain
    assert ACCURACY.replace("`", "") in plain.replace("`", "") or ACCURACY in plain


def test_no_script_no_external_url_no_dash(html):
    assert "<script" not in html.lower()
    assert "—" not in html
    for m in re.finditer(r"""\b(?:src|href)\s*=\s*["']([^"']*)["']""", html, re.I):
        assert not re.match(r"(?:[a-z][a-z0-9+.-]*:)?//", m.group(1), re.I) and not m.group(1).startswith("http"), m.group(1)
    assert "@import" not in html and "url(" not in html


def test_perf01_labeled_build_machine(html):
    assert "Measured on the build machine. Not evidence for either profile." in html


def _verdict_cell(html: str, profile: str) -> tuple[str, str]:
    m = re.search(rf'<tr><td>{profile}</td><td><span class="chip (\w+)">([^<]*)</span></td>', html)
    return m.group(1), m.group(2)


def _render_with(warn: int, fail: int) -> str:
    c = {"pass": 5, "warn": warn, "fail": fail, "skip": 0}
    doc = {"schema": 1, "aoi": AOI, "results": [], "summary": {"profile:mobile_ar": c, "profile:workstation": c}}
    if not (config.dist_dir(ROOT, AOI) / "tile.json").exists():
        assert cli.build(ROOT, AOI) == 0
    return render(ROOT, AOI, doc).read_text(encoding="utf-8")


def test_verdict_pass_with_warning_count():
    """Bradd ruling 3: 0 FAIL and 1 WARN is PASS, with the warning count beside it."""
    from tilepipe.validate.runner import verdict, verdict_text
    c = {"pass": 5, "warn": 1, "fail": 0, "skip": 0}
    assert verdict(c) == "PASS" and verdict_text(c) == "PASS, 1 warning"
    assert verdict_text({**c, "warn": 2}) == "PASS, 2 warnings"
    assert verdict_text({**c, "warn": 0}) == "PASS"
    assert verdict({**c, "fail": 1}) == "FAIL"


def test_report_shows_pass_one_warning():
    assert _verdict_cell(_render_with(1, 0), "mobile_ar") == ("PASS", "PASS, 1 warning")


def test_report_fail_stays_fail():
    assert _verdict_cell(_render_with(0, 1), "workstation")[0] == "FAIL"


def test_report_versions_come_from_build_info(html, tmp_path, monkeypatch):
    """WP08g: GDAL and Blender versions are the ones recorded in build_info.json. Touches only tmp_path."""
    import json
    import shutil
    real = config.build_dir(ROOT, AOI)
    fake = tmp_path / "build"
    shutil.copytree(real, fake)
    info = fake / "build_info.json"
    info.write_text(json.dumps({**json.loads(info.read_text(encoding="utf-8")), "gdal_version": "9.8.7",
                                "blender_version": "6.5.4"}), encoding="utf-8")
    monkeypatch.setattr(config, "build_dir", lambda root, aoi: fake)
    doc = {"schema": 1, "aoi": AOI, "results": [], "summary": {}}
    out = render(ROOT, AOI, doc, out_dir=tmp_path / "report").read_text(encoding="utf-8")
    assert "<th>GDAL</th><td>9.8.7</td>" in out and "<th>Blender</th><td>6.5.4</td>" in out


def test_report_logs_git_call(html):
    """WP08h: the git rev-parse call leaves build/logs/report.log (3.3 rule 7). `html` renders into tmp."""
    log = ROOT / "build" / "logs" / "report.log"
    assert log.is_file() and log.read_text(encoding="utf-8").startswith("exit ")
