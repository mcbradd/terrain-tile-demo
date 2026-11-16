"""Build the three placeholder entity files of SPEC 11.1 from primitives and assert their triangle counts.

blender --background --factory-startup --offline-mode --python-exit-code 1 \
    --python blender/scripts/make_entities.py -- --out-dir assets/entities [--regen]
"""
import argparse
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix

BASE_COLOR = "#F2F0EA"

# Parts per SPEC 11.1. Box: ("box", center, size). Cylinder: ("cyl", axis, center, radius, length, segment key).
ENTITIES = {
    "ent_vehicle_wheeled_a": [
        ("box", (0, 0, 0.75), (1.9, 5.0, 0.8)),
        ("box", (0, -1.65, 1.575), (1.8, 1.3, 0.85)),
        ("box", (0, 0.85, 1.45), (1.9, 3.3, 0.6)),
    ] + [("cyl", "X", (sx * 0.85, sy * 1.6, 0.45), 0.45, 0.3, "wheels") for sx in (1, -1) for sy in (1, -1)],
    "ent_mast_comms_a": [
        ("box", (0, 0, 0.2), (3.0, 3.0, 0.4)),
        ("cyl", "Z", (0, 0, 6.2), 0.15, 11.6, "mast"),
        ("box", (0, 0, 10.5), (2.0, 0.1, 0.1)),
    ] + [("cyl", "Y", (sx * 0.6, 0, 11.0), 0.4, 0.15, "dishes") for sx in (1, -1)],
    "ent_uas_quad_a": [
        ("box", (0, 0, 0.175), (0.4, 0.4, 0.15)),
        ("box", (0, 0, 0.2), (1.0, 0.06, 0.04)),
        ("box", (0, 0, 0.2), (0.06, 1.0, 0.04)),
    ] + [("box", (sx * 0.15, 0, 0.05), (0.04, 0.5, 0.1)) for sx in (1, -1)]
      + [("cyl", "Z", c, 0.18, 0.02, "rotors") for c in ((0.5, 0, 0.25), (-0.5, 0, 0.25), (0, 0.5, 0.25), (0, -0.5, 0.25))],
}

# Segment counts per LOD and expected triangles (SPEC 11.1 table).
SEGMENTS = {
    "ent_vehicle_wheeled_a": [{"wheels": 64}, {"wheels": 24}, {"wheels": 8}],
    "ent_mast_comms_a": [{"mast": 32, "dishes": 48}, {"mast": 12, "dishes": 16}, {"mast": 4, "dishes": 4}],
    "ent_uas_quad_a": [{"rotors": 48}, {"rotors": 16}, {"rotors": 4}],
}
TRIS = {
    "ent_vehicle_wheeled_a": [1060, 420, 164],
    "ent_mast_comms_a": [536, 200, 72],
    "ent_uas_quad_a": [828, 316, 124],
}
AXIS_ROT = {"Z": Matrix.Identity(4), "X": Matrix.Rotation(math.pi / 2, 4, "Y"), "Y": Matrix.Rotation(math.pi / 2, 4, "X")}


def srgb_to_linear(hex_color: str) -> tuple[float, float, float, float]:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return (*(lin(c) for c in rgb), 1.0)


def build_bmesh(parts: list, segments: dict) -> bmesh.types.BMesh:
    """All parts of one LOD in one bmesh; each part is a separate closed shell."""
    bm = bmesh.new()
    for p in parts:
        if p[0] == "box":
            _, c, s = p
            m = Matrix.Translation(c) @ Matrix.Diagonal((*s, 1.0))
            bmesh.ops.create_cube(bm, size=1.0, matrix=m)
        else:
            _, axis, c, r, length, key = p
            m = Matrix.Translation(c) @ AXIS_ROT[axis]
            bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=segments[key],
                                  radius1=r, radius2=r, depth=length, matrix=m)
    return bm


def make_material(name: str) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = srgb_to_linear(BASE_COLOR)
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Metallic"].default_value = 0.0
    mat.diffuse_color = srgb_to_linear(BASE_COLOR)
    return mat


def set_lod_mesh(obj: bpy.types.Object, bm: bmesh.types.BMesh) -> None:
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def build_entity(entity: str, segments: list[dict] | None = None) -> bpy.types.Collection:
    """Build the entity into the current (empty) file: one collection, three LOD objects, one material."""
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    coll = bpy.data.collections.new(entity)
    scene.collection.children.link(coll)
    mat = make_material(f"M_{entity}")
    for n, seg in enumerate(segments or SEGMENTS[entity]):
        name = f"{entity}_LOD{n}"
        me = bpy.data.meshes.new(name)
        me.materials.append(mat)
        obj = bpy.data.objects.new(name, me)
        coll.objects.link(obj)
        set_lod_mesh(obj, build_bmesh(ENTITIES[entity], seg))
    return coll


def triangle_counts(entity: str) -> list[int]:
    out = []
    for n in range(3):
        me = bpy.data.objects[f"{entity}_LOD{n}"].data
        me.calc_loop_triangles()
        out.append(len(me.loop_triangles))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--regen", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    paths = {e: out / e / f"{e}.blend" for e in ENTITIES}
    if not a.regen and all(p.exists() for p in paths.values()):
        print("make_entities: all three files exist; nothing to do (use --regen)")
        return 0
    ok = True
    for entity, path in paths.items():
        bpy.ops.wm.read_factory_settings(use_empty=True)
        build_entity(entity)
        path.parent.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(path.resolve()), check_existing=False)
        bpy.ops.wm.open_mainfile(filepath=str(path.resolve()))
        got = triangle_counts(entity)
        status = "ok" if got == TRIS[entity] else "MISMATCH"
        print(f"make_entities: {entity} tris {got} expected {TRIS[entity]} {status}")
        ok &= got == TRIS[entity]
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sys.exit(main(args))
