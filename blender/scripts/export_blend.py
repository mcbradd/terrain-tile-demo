"""Run the source gate; on pass, export per SPEC 11.5 and write the partial entity.json (SPEC 11.6).

blender --background --factory-startup --offline-mode --python-exit-code 1 \
    --python blender/scripts/export_blend.py -- --blend <path> --profiles <dir> --out-dir <dir>
"""
import argparse
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tilepipe_tools import pipeline, rules  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    blend = Path(a.blend).resolve()
    repo_root = Path(a.profiles).resolve().parent
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene = bpy.context.scene
    colls = pipeline.entity_collections(scene)
    if len(colls) != 1:
        print(f"export_blend: {blend.name} has {len(colls)} ent_* collections, expected 1")
        return 1
    coll = colls[0]
    records = pipeline.gate(scene, coll, repo_root, f"entity:{coll.name}")
    for r in records:
        if r["status"] != "PASS":
            print(r["message"])
    if rules.failed(records):
        print(f"export_blend: {coll.name}: source gate failed; nothing exported")
        return 1
    path = pipeline.export_asset(coll, Path(a.out_dir), repo_root, blend)
    print(f"export_blend: {coll.name}: wrote {path.parent.name}/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:]))
