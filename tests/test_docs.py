"""WP13 document checks: length per document, forbidden terms, em dashes, required sentences."""
import datetime
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
    n = verification_prose_words(read(rel)) if rel == "docs/VERIFICATION.md" else len(read(rel).split())
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
    assert len(re.findall(r"^- Why: \S", s, re.M)) >= 11
    assert "DRAFT" not in s
    assert "## Deviations" in s and "### D-01 (WP01)" in s


def test_open_questions_rows():
    rows = [r for r in read("docs/OPEN_QUESTIONS.md").splitlines() if re.match(r"\| \d+ \|", r)]
    assert len(rows) >= 13


def verification_prose_words(s: str) -> int:
    """Words in VERIFICATION.md outside its log lines: `- [HUMAN]` entries and the numbered rulings."""
    n, in_rulings = 0, False
    for ln in s.splitlines():
        if ln.startswith("## "):
            in_rulings = ln.strip() == "## Approved threshold changes"
        if ln.startswith("- [HUMAN]") or (in_rulings and re.match(r"\d+\. ", ln)):
            continue
        n += len(ln.split())
    return n


def verification_entry_errors(s: str) -> list[str]:
    """Each `- [HUMAN]` entry is `label:` (empty) or `label: text`; a filled Date holds a valid ISO date."""
    entries = [ln.rstrip() for ln in s.splitlines() if ln.startswith("- [HUMAN]")]
    if not entries:
        return ["no [HUMAN] entries"]
    errors = []
    for ln in entries:
        m = re.fullmatch(r"- \[HUMAN\] ([^:]+):(?: (\S.*))?", ln)
        if not m:
            errors.append(ln)
        elif m.group(1) == "Date" and m.group(2):
            dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", m.group(2))
            try:
                ok = bool(dates) and all(datetime.date.fromisoformat(d) for d in dates)
            except ValueError:
                ok = False
            if not ok:
                errors.append(ln)
    return errors


def test_verification_entries_format():
    assert verification_entry_errors(read("docs/VERIFICATION.md")) == []


@pytest.mark.parametrize("text", [
    "- [HUMAN] Date:\n- [HUMAN] Result:",
    "- [HUMAN] Date: 2026-11-18\n- [HUMAN] Result: PASS, MGRS matches: 11SMS",
])
def test_verification_entries_format_pass(text):
    assert verification_entry_errors(text) == []


@pytest.mark.parametrize("text", [
    "",
    "- [HUMAN] Date: yesterday",
    "- [HUMAN] Date: 2026-13-01",
    "- [HUMAN] Result:PASS",
    "- [HUMAN] no colon here",
])
def test_verification_entries_format_fail(text):
    assert verification_entry_errors(text)


def test_verification_prose_words_skip_log_lines():
    s = "Intro words.\n- [HUMAN] Date: 2026-11-18 a b c\n## Approved threshold changes\n\nRuling text.\n1. x y z\n"
    assert verification_prose_words(s) == 8


def test_provenance_license_placeholder():
    assert "Run `uv run tilepipe licenses`" in read("docs/PROVENANCE.md") or "| Package" in read("docs/PROVENANCE.md")
