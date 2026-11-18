"""WP12 tests: presubmit exit codes, set-share keeps META-01, licenses table."""
import shutil
from pathlib import Path

import pytest

from tilepipe import config, licenses, presubmit
from tilepipe.cli import blender_exe
from tilepipe.validate.registry import Context

ROOT = Path(__file__).resolve().parents[1]
BLENDER = Path(blender_exe())
needs_blender = pytest.mark.skipif(not BLENDER.exists(), reason="Blender 5.2 not installed")


@needs_blender
def test_presubmit_fixture_fails_and_template_passes():
    assert presubmit.run(ROOT, [ROOT / "assets/fixtures/fx_ent01_name.blend"]) == 1
    assert presubmit.run(ROOT, [ROOT / "assets/entities/_template/ent_template.blend"]) == 0


def test_presubmit_glb_passes():
    assert presubmit.run(ROOT, [ROOT / "assets/entities/ent_mast_comms_a/export/ent_mast_comms_a_LOD0.glb"]) == 0


@pytest.mark.parametrize("share", [0.08, 0.15, 0.25, 0.333])
def test_set_share_keeps_meta01(tmp_path, share):
    from tilepipe.validate import rules_meta  # noqa: F401  (registers META-01)
    shutil.copytree(ROOT / "profiles", tmp_path / "profiles")
    presubmit.set_share(tmp_path, "mobile_ar", share)
    ctx = Context(root=tmp_path, aoi="x", profiles=config.load_profiles(tmp_path), looks={}, entity_lods={},
                  options={}, cache={})
    from tilepipe.validate.registry import RULES
    assert RULES["META-01"].check(ctx, "profile:mobile_ar").status == "PASS"


def test_licenses_table(tmp_path):
    rows = licenses.rows(ROOT)
    assert any(r[0] == "numpy" for r in rows) and all(r[2] != "UNKNOWN" for r in rows)
