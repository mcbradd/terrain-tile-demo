"""WP13 document checks: length per document, forbidden terms, em dashes, required sentences."""
import getpass
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# Word limits are about one page (600 words) per 14.2; DECISIONS gets two pages plus its Deviations log.
LIMITS = {
    "README.md": 600,
    "docs/STANDARDS.md": 700,
    "docs/OPEN_QUESTIONS.md": 600,
    "docs/PROVENANCE.md": 500,
    "docs/DECISIONS.md": 3500,
    "docs/VERIFICATION.md": 400,
}
DOCS = [*LIMITS, "LICENSE", "DATA_LICENSE.md", "blender/LICENSE"]
TEXT = [d for d in DOCS if d != "blender/LICENSE"]  # GPL text is verbatim and exempt from prose rules


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", LIMITS)
def test_doc_length(rel):
    n = len(read(rel).split())
    assert 50 < n <= LIMITS[rel], f"{rel}: {n} words, limit {LIMITS[rel]}"


@pytest.mark.parametrize("rel", DOCS)
def test_doc_forbidden_terms(rel):
    assert not re.search("|".join(["and" + "uril", "lat" + "tice", "eagle" + "eye", "sand" + " table"]), read(rel), re.I)


@pytest.mark.parametrize("rel", TEXT)
def test_doc_no_em_dash_or_banned_phrase(rel):
    s = read(rel)
    assert "—" not in s
    assert not re.search("|".join(["production" + "-ready", "military" + "-grade", "battle" + "-tested", "optimized" + " for"]), s, re.I)


@pytest.mark.parametrize("rel", LIMITS)
def test_doc_no_personal_paths(rel):
    assert not re.search(r"[A-Za-z]:\\|/Users/|@[\w.-]+\.\w+|" + re.escape(getpass.getuser()), read(rel))


def test_readme_required_sentence():
    assert "No headset performance was measured." in read("README.md")


def test_standards_accuracy_statement_verbatim():
    spec = ROOT / "SPEC.md"
    s = read("docs/STANDARDS.md")
    assert "Treat horizontal accuracy as plus or minus one cell (10 m)." in s
    if spec.exists():  # SPEC.md is local and gitignored
        m = re.search(r"### 5\.7.*?\n\n> (.+?)\n", spec.read_text(encoding="utf-8"), re.S)
        assert m and m.group(1) in s


def test_decisions_has_all_records_and_keeps_deviations():
    s = read("docs/DECISIONS.md")
    for i in range(1, 12):
        assert re.search(rf"^### D{i} ", s, re.M), f"D{i}"
    assert len(re.findall(r"^- Why: DRAFT, for Bradd", s, re.M)) >= 11
    assert "## Deviations" in s and "### D-01 (WP01)" in s


def test_open_questions_rows():
    rows = [r for r in read("docs/OPEN_QUESTIONS.md").splitlines() if re.match(r"\| \d+ \|", r)]
    assert len(rows) >= 13


def test_verification_entries_empty():
    s = read("docs/VERIFICATION.md")
    entries = [ln for ln in s.splitlines() if ln.startswith("- [HUMAN]")]
    assert entries and all(ln.rstrip().endswith(":") for ln in entries)


def test_provenance_license_placeholder():
    assert "Run `uv run tilepipe licenses`" in read("docs/PROVENANCE.md") or "| Package" in read("docs/PROVENANCE.md")
