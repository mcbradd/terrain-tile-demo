"""Import Tile operator of the Blender extension (SPEC 11.4): runs blender/scripts/test_tile_import.py headless.
Skips when Blender 5.2 is absent or the tile is not built (dist/ is not tracked)."""
import os
import subprocess
from pathlib import Path

import pytest

from tilepipe.cli import blender_exe

ROOT = Path(__file__).resolve().parents[1]
BLENDER = Path(blender_exe())
# TILEPIPE_DIST_ROOT lets a worktree without its own dist/ point at a built checkout
DIST_ROOT = Path(os.environ.get("TILEPIPE_DIST_ROOT", ROOT))


@pytest.mark.skipif(not BLENDER.exists(), reason="Blender 5.2 not installed")
@pytest.mark.skipif(not list(DIST_ROOT.glob("dist/*/tile.json")), reason="no built tile under dist/")
def test_import_tile_operator():
    cmd = [str(BLENDER), "--background", "--factory-startup", "--offline-mode", "--python-exit-code", "1",
           "--python", str(ROOT / "blender" / "scripts" / "test_tile_import.py"), "--", "--repo-root", str(DIST_ROOT)]
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0 and "\nOK " in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]
