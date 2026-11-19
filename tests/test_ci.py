"""P1.2: the CI workflow exists, triggers on main, pins its tools, and runs the core commands without Blender.

PyYAML is not a project dependency, so these checks read the workflow text.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
RUNS = [m.group(1).strip() for m in re.finditer(r"^\s*(?:- )?run: (.+)$", TEXT, re.M)]


def test_ci_workflow_triggers_on_push_and_pull_request_to_main():
    assert re.search(r"^on:\n  push:\n    branches: \[main\]\n  pull_request:\n    branches: \[main\]$", TEXT, re.M)


def test_ci_workflow_runs_core_commands():
    for cmd in ("uv sync --no-build", "npm ci", "uv run tilepipe build", "uv run tilepipe validate", "uv run pytest"):
        assert any(r.startswith(cmd) for r in RUNS), cmd
    assert not any("blender" in r.lower() and "--no-blender" not in r for r in RUNS)  # no Blender in CI


def test_ci_workflow_fetches_nothing_and_runs_offline():
    assert not any("tilepipe fetch" in r for r in RUNS)  # the crop is committed under data/source
    assert TEXT.count('TILEPIPE_OFFLINE: "1"') == 3  # build, entities, validate; pytest runs without the guard


def test_ci_workflow_pins_and_caches():
    assert re.search(r'version: "0\.11\.8"\n\s+enable-cache: true', TEXT)
    assert re.search(r'node-version: "24\.16\.0"\n\s+cache: npm', TEXT)
