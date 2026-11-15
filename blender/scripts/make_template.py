"""Write the entity template of SPEC 11.2: a factory scene with METRIC units at scale 1.0, one correctly named
collection, and three placeholder cubes named for LOD 0 to 2. New assets start from a copy of it.

blender --background --factory-startup --offline-mode --python-exit-code 1 \
    --python blender/scripts/make_template.py -- --out assets/entities/_template/ent_template.blend
"""
import argparse
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_entities import make_material  # noqa: E402

NAME = "ent_template_asset_a"   # 6.6 pattern; rename the collection, objects, meshes, and material on copy


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    coll = bpy.data.collections.new(NAME)
    scene.collection.children.link(coll)
    mat = make_material(f"M_{NAME}")
    # Grid cuts 3, 1, 0 give 192, 48, 12 triangles, so the template passes the whole source gate (ENT-05).
    for n, cuts in enumerate((3, 1, 0)):
        me = bpy.data.meshes.new(f"{NAME}_LOD{n}")
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, 0.5)))
        if cuts:
            bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        coll.objects.link(bpy.data.objects.new(me.name, me))
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), check_existing=False)
    print(f"make_template: wrote {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:]))
