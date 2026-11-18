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
