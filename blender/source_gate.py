"""Core-side driver for the Blender half of `tilepipe entities` (SPEC 11.6). Standard library only, no bpy.

Runs make_entities.py, export_blend.py per entity, make_fixtures.py, and validate_blend.py on every entity and
fixture, then compares each fixture's actual FAIL set with its expected set. Writes
`build/entities/ent_results.json` (contracts.md 4) and logs every Blender call to `build/logs/entities.log`.

    uv run python blender/source_gate.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"   # SPEC 3.1
ENTITIES = ("ent_vehicle_wheeled_a", "ent_mast_comms_a", "ent_uas_quad_a")
GOLDEN = "ent_vehicle_wheeled_a"


def blender(root: Path, script: str, *args: str) -> int:
    """One headless call with the exact shape of SPEC 3.3 rule 4; output appended to build/logs/entities.log."""
    exe = os.environ.get("TILEPIPE_BLENDER", DEFAULT_BLENDER)
    cmd = [exe, "--background", "--factory-startup", "--offline-mode", "--python-exit-code", "1",
           "--python", str(root / "blender" / "scripts" / script), "--", *args]
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = root / "build" / "logs" / "entities.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8", newline="\n") as f:
        f.write(f"$ {script} {' '.join(args)}\n{r.stdout}{r.stderr}exit {r.returncode}\n\n")
    return r.returncode


def run(root: Path) -> dict:
    """Returns {"errors": [...], "fixtures": {fx: {"expected", "actual"}}, "records": [...]}."""
    root = Path(root).resolve()
    ents, profiles = root / "assets" / "entities", str(root / "profiles")
    out = root / "build" / "entities"
    out.mkdir(parents=True, exist_ok=True)
    (root / "build" / "logs" / "entities.log").unlink(missing_ok=True)
    errors, records, fixtures = [], [], {}
    if blender(root, "make_entities.py", "--out-dir", str(ents)):
        errors.append("make_entities.py failed")
    for e in ENTITIES:
        blend = str(ents / e / f"{e}.blend")
        if blender(root, "export_blend.py", "--blend", blend, "--profiles", profiles, "--out-dir", str(ents / e / "export")):
            errors.append(f"export_blend.py failed on {e}")
    fx_dir = root / "assets" / "fixtures"
    if blender(root, "make_fixtures.py", "--golden", str(ents / GOLDEN / f"{GOLDEN}.blend"), "--out-dir", str(fx_dir)):
        errors.append("make_fixtures.py failed")
    expected = json.loads((fx_dir / "expected.json").read_text(encoding="utf-8")) if (fx_dir / "expected.json").exists() else {}
    targets = [(e, ents / e / f"{e}.blend") for e in ENTITIES] + [(f, fx_dir / f"{f}.blend") for f in sorted(expected)]
    for name, blend in targets:
        res = out / f"{name}.json"
        res.unlink(missing_ok=True)
        code = blender(root, "validate_blend.py", "--blend", str(blend), "--profiles", profiles, "--out", str(res))
        recs = json.loads(res.read_text(encoding="utf-8")) if res.exists() else []
        records += recs
        actual = sorted({r["rule"] for r in recs if r["status"] == "FAIL"})
        if name in expected:
            fixtures[name] = {"expected": sorted(expected[name]), "actual": actual}
            if actual != sorted(expected[name]):
                errors.append(f"{name}: failing set {actual} != expected {sorted(expected[name])}")
        elif code or actual:
            errors.append(f"{name}: source gate FAIL {actual}")
        res.unlink(missing_ok=True)
    (out / "ent_results.json").write_text(json.dumps(records, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8", newline="\n")
    return {"errors": errors, "fixtures": fixtures, "records": records}


if __name__ == "__main__":
    summary = run(Path(__file__).resolve().parents[1])
    for name, f in summary["fixtures"].items():
        print(f"{name}: expected {f['expected']} actual {f['actual']}")
    for err in summary["errors"]:
        print(f"ERROR {err}")
    sys.exit(1 if summary["errors"] else 0)
