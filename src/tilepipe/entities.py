"""Command `entities` (SPEC 4.2, 11.6). Signatures are frozen: see contracts.md.

Runs the Blender half (blender/source_gate.py: make_entities, export, fixtures, source gate on every entity and
fixture), copies each entity's exported GLBs to `dist/entities/<entity>/`, completes `entity.json` from the GLBs,
then runs the deliverable gate (ENTD-01 to ENTD-06, GLB-01) on them. `--no-blender` skips the Blender half and uses
the committed exports under `assets/entities/<entity>/export/`.
"""
import importlib.util
import json
import shutil
from pathlib import Path

from tilepipe import config, glb
from tilepipe.hashing import sha256_file
from tilepipe.validate import common
from tilepipe.validate.registry import RULES, Context

ENTD = tuple(f"ENTD-{i:02d}" for i in range(1, 7))


def _source_gate(root: Path) -> list[str]:
    """Blender half; returns its error lines. source_gate.py is standard library only (3.3 rule 6)."""
    spec = importlib.util.spec_from_file_location("source_gate", root / "blender" / "source_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    summary = mod.run(root)
    for name, f in summary["fixtures"].items():
        print(f"fixture {name}: expected {f['expected']} actual {f['actual']}")
    return summary["errors"]


def complete(export: Path, dist: Path) -> dict:
    """Copy one entity's GLBs to `dist` and return its entity.json with per-LOD tris, vertices, bytes, sha256."""
    doc = json.loads((export / "entity.json").read_text(encoding="utf-8"))
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    for lod in doc["lods"]:
        f = dist / lod["file"]
        shutil.copyfile(export / lod["file"], f)
        gltf, binary = glb.parse_glb(f.read_bytes())
        prim = gltf["meshes"][0]["primitives"][0]
        lod["vertices"] = gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
        lod["tris"] = (gltf["accessors"][prim["indices"]]["count"] if "indices" in prim else lod["vertices"]) // 3
        lod["bytes"] = f.stat().st_size
        lod["sha256"] = sha256_file(f)
    config.check_schema(doc, "entity", f"{doc['id']}/entity.json")
    config.write_json(dist / "entity.json", doc)
    return doc


def deliverable_gate(root: Path, ids: list[str]) -> list[dict]:
    """ENTD-01 to ENTD-06 per entity and GLB-01 on every entity GLB, as result records."""
    from tilepipe.validate import rules_entd, rules_tex  # noqa: F401  (registers the ENTD checks)
    ctx = Context(root=root, aoi=config.default_aoi(root), profiles=config.load_profiles(root),
                  looks=config.load_looks(root), entity_lods=config.load_entity_lods(root),
                  options={"skip_entities": False, "determinism": False, "no_blender": True}, cache={})
    out = [RULES[r].check(ctx, f"entity:{e}").to_dict() for e in ids for r in ENTD]
    files = sorted((root / "dist" / "entities").rglob("*.glb"))
    counts = rules_tex.run_validator(files, root / "build" / "logs" / "gltf_validator_entities.log")   # 3.3 rule 7
    bad = [f"{f}: {c['errors']} errors, {c['warnings']} warnings" for f, c in counts.items()
           if c["errors"] or c["warnings"]]
    out.append(common.violations("GLB-01", "entities", bad, "files", "Fix the export (11.5).").to_dict())
    return out


def refresh_manifest(root: Path) -> None:
    """Rewrite tile.json and outputs.sha256 now that dist/entities/ exists (D-12). Skipped before a first build."""
    from tilepipe import manifest
    aoi = config.default_aoi(root)
    if (config.build_dir(root, aoi) / "geo.json").exists():
        manifest.run(root, aoi)


def run(root: Path, no_blender: bool = False) -> int:
    root = Path(root).resolve()
    errors = [] if no_blender else _source_gate(root)
    src = root / "assets" / "entities"
    ids = sorted(p.parent.parent.name for p in src.glob("ent_*/export/entity.json"))
    if not ids:
        errors.append("no exported entities under assets/entities/*/export/")
    for e in ids:
        complete(src / e / "export", root / "dist" / "entities" / e)
    records = deliverable_gate(root, ids) if ids else []
    for r in records:
        print(r["message"])
    errors += [f"deliverable gate: {r['message']}" for r in records if r["status"] == "FAIL"]
    if not errors:
        refresh_manifest(root)
    for err in errors:
        print(f"ERROR {err}")
    print(f"entities: {len(ids)} entities, {len(records)} deliverable checks, {len(errors)} errors")
    return 1 if errors else 0
