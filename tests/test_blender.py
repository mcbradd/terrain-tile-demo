"""WP11 Blender tests (SPEC 12.9): test_rules.py headless, the fixture matrix, the template, and the entities."""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLENDER = Path(os.environ.get("TILEPIPE_BLENDER", r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"))
pytestmark = pytest.mark.skipif(not BLENDER.exists(), reason="Blender 5.2 not installed")

_spec = importlib.util.spec_from_file_location("source_gate", ROOT / "blender" / "source_gate.py")
source_gate = importlib.util.module_from_spec(_spec)
sys.modules["source_gate"] = source_gate
_spec.loader.exec_module(source_gate)


@pytest.fixture(scope="module")
def gate():
    return source_gate.run(ROOT)


def test_blender_rules_script():
    assert source_gate.blender(ROOT, "test_rules.py") == 0, "see build/logs/entities.log"


def test_blender_fixture_matrix(gate):
    assert len(gate["fixtures"]) == 12
    for name, f in gate["fixtures"].items():
        assert f["actual"] == f["expected"], name
    assert gate["errors"] == []


def test_blender_entities_pass_every_ent_rule(gate):
    for e in source_gate.ENTITIES:
        recs = [r for r in gate["records"] if r["scope"] == f"entity:{e}"]
        assert sorted(r["rule"] for r in recs) == [f"ENT-{i:02d}" for i in range(1, 16)]
        assert all(r["status"] == "PASS" for r in recs), [r["message"] for r in recs if r["status"] != "PASS"]
        for n in range(3):
            assert (ROOT / "assets" / "entities" / e / "export" / f"{e}_LOD{n}.glb").read_bytes()[:4] == b"glTF"


def test_blender_template_passes(tmp_path):
    template = ROOT / "assets" / "entities" / "_template" / "ent_template.blend"
    assert template.exists()
    out = tmp_path / "template.json"
    assert source_gate.blender(ROOT, "validate_blend.py", "--blend", str(template),
                               "--profiles", str(ROOT / "profiles"), "--out", str(out)) == 0
