"""tilepipe command line. Only `preflight` exists so far (SPEC 3.4); WP02 adds the other commands."""
import argparse
import importlib.metadata as md
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

EXIT_OK, EXIT_ENV = 0, 3
DEFAULT_BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
PINS = {"rasterio": "1.5.2", "numpy": "2.5.4", "mgrs": "1.7.0", "jinja2": "3.1.6", "jsonschema": "4.26.0"}
THREE_VERSION = "0.187.0"
MIN_FREE_GIB = 2


def _run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _blender_cmd(blender, script, *args):
    return [blender, "--background", "--factory-startup", "--offline-mode",
            "--python-exit-code", "1", "--python", str(script), "--", *args]


def pf01():
    exe = os.environ.get("TILEPIPE_BLENDER", DEFAULT_BLENDER)
    if not Path(exe).exists():
        return "FAIL", f"not found: {exe}"
    out = _run([exe, "--version"]).stdout.strip()
    first = out.splitlines()[0] if out else ""
    return ("PASS" if first.startswith("Blender 5.2") else "FAIL"), first


def pf02(root):
    exe = os.environ.get("TILEPIPE_BLENDER", DEFAULT_BLENDER)
    if not Path(exe).exists():
        return "FAIL", "Blender missing"
    out = root / "build" / "preflight" / "cube.glb"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    r = _run(_blender_cmd(exe, root / "tools" / "preflight_export.py", str(out)), timeout=300)
    if r.returncode != 0 or not out.exists():
        return "FAIL", f"export failed, exit {r.returncode}: {r.stderr.strip()[-200:]}"
    magic = out.read_bytes()[:4]
    return ("PASS" if magic == b"glTF" else "FAIL"), f"{out.stat().st_size} bytes, magic {magic!r}"


def pf03():
    r = _run(["node", "--version"])
    v = r.stdout.strip()
    return ("PASS" if v.startswith("v24.") else "FAIL"), v


def pf04(root):
    pkg = root / "node_modules" / "three" / "package.json"
    if not pkg.exists():
        return "FAIL", "node_modules/three missing"
    v = json.loads(pkg.read_text(encoding="utf-8"))["version"]
    if v != THREE_VERSION:
        return "FAIL", f"three {v}, expected {THREE_VERSION}"
    glb = root / "build" / "preflight" / "cube.glb"
    if not glb.exists():
        return "FAIL", "PF-02 file missing"
    r = _run(["node", str(root / "tools" / "validate_gltf.mjs"), str(glb)])
    return ("PASS" if r.returncode == 0 else "FAIL"), (r.stdout.strip() or r.stderr.strip()[-200:])


def pf05():
    py = platform.python_version()
    bad = [f"python {py}"] if not py.startswith("3.12.") else []
    for name, want in PINS.items():
        try:
            got = md.version(name)
        except md.PackageNotFoundError:
            got = "missing"
        if got != want:
            bad.append(f"{name} {got} != {want}")
    return ("FAIL", "; ".join(bad)) if bad else ("PASS", f"python {py}")


def pf06(root):
    free = shutil.disk_usage(root).free / 2**30
    return ("PASS" if free >= MIN_FREE_GIB else "FAIL"), f"{free:.1f} GiB free"


def pf07():
    p = shutil.which("ffmpeg")
    return ("PASS", p) if p else ("WARN", "ffmpeg not on PATH")


def preflight(root: Path) -> int:
    results = []
    for id_, name, fn in [
        ("PF-01", "Blender binary", pf01), ("PF-02", "Headless export", lambda: pf02(root)),
        ("PF-03", "Node", pf03), ("PF-04", "npm packages", lambda: pf04(root)),
        ("PF-05", "Python", pf05), ("PF-06", "Disk", lambda: pf06(root)), ("PF-07", "ffmpeg", pf07),
    ]:
        try:
            status, detail = fn()
        except Exception as e:  # a crashing check is a failed check
            status, detail = "FAIL", f"{type(e).__name__}: {e}"
        results.append({"id": id_, "name": name, "status": status, "detail": detail})
        print(f"{id_}  {status:<4}  {name}: {detail}")
    (root / "build").mkdir(exist_ok=True)
    (root / "build" / "preflight.json").write_text(
        json.dumps({"checks": results}, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return EXIT_ENV if any(r["status"] == "FAIL" for r in results) else EXIT_OK


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tilepipe")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight", help="check the toolchain (SPEC 3.4)")
    ap.parse_args(argv)
    return preflight(Path.cwd())


if __name__ == "__main__":
    sys.exit(main())
