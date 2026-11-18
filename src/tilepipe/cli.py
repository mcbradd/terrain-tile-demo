"""tilepipe command line (SPEC 4.2). `preflight` is SPEC 3.4; every other command dispatches to its module."""
import argparse
import importlib.metadata as md
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

EXIT_OK, EXIT_ENV = 0, 3
_DEFAULT_BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"  # the only place this path lives
PINS = {"rasterio": "1.5.2", "numpy": "2.5.4", "mgrs": "1.7.0", "jinja2": "3.1.6", "jsonschema": "4.26.0"}
THREE_VERSION = "0.187.0"
MIN_FREE_GIB = 2


def blender_exe():
    """Blender lookup (SPEC 3.1): TILEPIPE_BLENDER, then PATH, then the standard install path."""
    return os.environ.get("TILEPIPE_BLENDER") or shutil.which("blender") or _DEFAULT_BLENDER


def _run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _blender_cmd(blender, script, *args):
    return [blender, "--background", "--factory-startup", "--offline-mode",
            "--python-exit-code", "1", "--python", str(script), "--", *args]


def pf01():
    exe = blender_exe()
    if not Path(exe).exists():
        return "FAIL", f"not found: {exe}"
    out = _run([exe, "--version"]).stdout.strip()
    first = out.splitlines()[0] if out else ""
    return ("PASS" if first.startswith("Blender 5.2") else "FAIL"), first


def pf02(root):
    exe = blender_exe()
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


def _stage_fn(stage: str):
    """Stage name (SPEC 7) -> callable(root, aoi). Imported lazily so a stub stage does not break other commands."""
    import importlib
    mod, attr = {"export": ("lod", "export")}.get(stage, (stage, "run"))
    return getattr(importlib.import_module(f"tilepipe.{mod}"), attr)


def build(root: Path, aoi: str, start: str | None = None, stop: str | None = None) -> int:
    """Run stages start..stop of config.STAGES in order and record each wall-clock duration in build_info.json."""
    from tilepipe import config
    stages = list(config.STAGES)
    i = stages.index(start) if start else 0
    j = stages.index(stop) + 1 if stop else len(stages)
    if i >= j:
        raise config.UsageError(f"--from {start} comes after --to {stop}")
    info_path = config.build_dir(root, aoi) / "build_info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    secs = info.setdefault("stage_seconds", {})
    for stage in stages[i:j]:
        t0 = time.perf_counter()
        _stage_fn(stage)(root, aoi)
        secs[stage] = time.perf_counter() - t0
        print(f"{stage}: {secs[stage]:.2f} s")
    info["total_seconds"] = sum(secs[s] for s in stages if s in secs)
    info["host"] = platform.node()
    info["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    config.write_json(info_path, info)
    return EXIT_OK


def _parser(stage_names) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tilepipe", description="Terrain tile pipeline (SPEC 4.2). Exit codes: "
                                 "0 ok, 1 FAIL rule, 2 usage or config, 3 environment, 4 data guard.")
    sub = ap.add_subparsers(dest="command", required=True, metavar="<command>")

    def cmd(name, help_, aoi=False):
        p = sub.add_parser(name, help=help_, description=help_)
        if aoi:
            p.add_argument("--aoi", default=None, help="AOI id from aois.toml (default: its first AOI)")
        return p

    cmd("preflight", "check the toolchain (SPEC 3.4)")
    cmd("fetch", "read the source window; write the committed crop and its provenance (network)", aoi=True)
    p = cmd("build", "run stages prep, lod, bake, export, batch, scene, manifest", aoi=True)
    p.add_argument("--from", dest="start", choices=stage_names, help="first stage to run; reuses build/<aoi>/")
    p.add_argument("--to", dest="stop", choices=stage_names, help="last stage to run")
    p = cmd("entities", "headless Blender source gate and export for every asset, then fixtures")
    p.add_argument("--no-blender", action="store_true",
                   help="skip Blender; copy committed exports into dist/entities/ and run the deliverable gate")
    p = cmd("validate", "run every rule; write validation.json, validation.junit.xml, and the report", aoi=True)
    p.add_argument("--skip-entities", action="store_true",
                   help="run no ENT or ENTD rule; record them and SCN-01, SCN-02, SCN-05 as SKIP")
    p.add_argument("--determinism", action="store_true", help="add rule DET-01")
    cmd("site", "bundle the viewer with esbuild and assemble site/", aoi=True)
    cmd("serve", "serve site/ at http://127.0.0.1:8000")
    p = cmd("all", "build, entities, validate, site, in that order", aoi=True)
    p.add_argument("--no-blender", action="store_true", help="as entities --no-blender")
    p = cmd("scene", "regenerate scene/<aoi>_scene.json", aoi=True)
    p.add_argument("--regen", action="store_true", required=True, help="rewrite the committed placement file")
    p = cmd("profile", "edit a hardware profile")
    psub = p.add_subparsers(dest="profile_command", required=True, metavar="<subcommand>")
    q = psub.add_parser("set-share", help="rewrite a profile's content share and derived budgets so META-01 holds",
                        description="rewrite a profile's content share and derived budgets so META-01 holds")
    q.add_argument("profile", help="profile name, e.g. mobile_ar")
    q.add_argument("share", type=float, help="new content share in (0, 1]")
    p = cmd("presubmit", "source gate on each .blend, deliverable gate on each .glb; exit 1 on any FAIL")
    p.add_argument("files", nargs="+", type=Path, help=".blend and .glb files")
    cmd("licenses", "write the third-party license table of PROVENANCE.md from installed package metadata")
    return ap


def _dispatch(a, root: Path) -> int:
    from tilepipe import config
    aoi = getattr(a, "aoi", None)
    if aoi is not None or a.command in ("fetch", "build", "validate", "site", "all", "scene"):
        aoi = config.load_aoi(root, aoi or config.default_aoi(root))["id"]
    if a.command == "fetch":
        from tilepipe.fetch import fetch
        fetch(root, aoi)
        return EXIT_OK
    if a.command == "build":
        return build(root, aoi, a.start, a.stop)
    if a.command == "entities":
        from tilepipe.entities import run
        return run(root, no_blender=a.no_blender)
    if a.command == "validate":
        from tilepipe.validate.runner import run
        return run(root, aoi, skip_entities=a.skip_entities, determinism=a.determinism)
    if a.command == "site":
        from tilepipe.site import build as site_build
        site_build(root, aoi)
        return EXIT_OK
    if a.command == "serve":
        from tilepipe.site import serve
        serve(root)
        return EXIT_OK
    if a.command == "all":
        from tilepipe.entities import run as entities
        from tilepipe.site import build as site_build
        from tilepipe.validate.runner import run as validate
        for step in (lambda: build(root, aoi), lambda: entities(root, no_blender=a.no_blender),
                     lambda: validate(root, aoi), lambda: site_build(root, aoi) or EXIT_OK):
            rc = step()
            if rc:
                return rc
        return EXIT_OK
    if a.command == "scene":
        from tilepipe.scene import run
        run(root, aoi, regen=True)
        return EXIT_OK
    if a.command == "profile":
        from tilepipe.presubmit import set_share
        if a.profile not in config.load_profiles(root):
            raise config.UsageError(f"unknown profile {a.profile!r}")
        if not 0 < a.share <= 1:
            raise config.UsageError("share must be in (0, 1]")
        set_share(root, a.profile, a.share)
        return EXIT_OK
    if a.command == "presubmit":
        from tilepipe.presubmit import run
        return run(root, a.files)
    if a.command == "licenses":
        from tilepipe.licenses import run
        run(root)
        return EXIT_OK
    raise AssertionError(a.command)


def main(argv=None) -> int:
    from tilepipe import config
    a = _parser(list(config.STAGES)).parse_args(argv)
    root = Path.cwd()
    if a.command == "preflight":
        return preflight(root)
    try:
        return _dispatch(a, root)
    except config.TilepipeError as e:
        print(f"tilepipe {a.command}: {e}", file=sys.stderr)
        return e.code
    except NotImplementedError as e:
        print(f"tilepipe {a.command}: not implemented yet ({e})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
