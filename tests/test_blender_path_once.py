"""PF-01 ruling (VERIFICATION.md): the standard Blender install path appears in exactly one tracked file."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_install_path_in_one_tracked_file():
    needle = "Blender " + "Foundation"   # split so this file does not match itself
    out = subprocess.run(["git", "grep", "-l", "-F", needle, "--", "*.py", "*.toml", "*.json"],
                         cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert out == ["src/tilepipe/cli.py"], out
