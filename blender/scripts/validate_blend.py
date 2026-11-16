"""Open a .blend, run the source gate on every `ent_*` collection, write results, exit 1 on any FAIL (SPEC 11.6).

blender --background --factory-startup --offline-mode --python-exit-code 1 \
    --python blender/scripts/validate_blend.py -- --blend <path> --profiles <dir> --out <json>

The scope is `fixture:<file stem>` for files named `fx_*`, else `entity:<collection>`. The repo root, which holds
`entity_lods.toml`, is the parent of the profiles directory.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tilepipe_tools import pipeline, rules  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    blend = Path(a.blend).resolve()
    repo_root = Path(a.profiles).resolve().parent
    bpy.ops.wm.open_mainfile(filepath=str(blend))
    scene = bpy.context.scene
    colls = pipeline.entity_collections(scene)
    records = []
    for coll in colls:
        scope = f"fixture:{blend.stem}" if blend.stem.startswith("fx_") else f"entity:{coll.name}"
        records += [rules.strip(r) for r in pipeline.gate(scene, coll, repo_root, scope)]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    fails = rules.failed(records)
    print(f"validate_blend: {blend.name}: {len(colls)} collections, FAIL {sorted(set(fails))}")
    return 1 if fails or not colls else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:]))
