"""Write one fixture .blend per row of SPEC 12.9 from the golden vehicle file, then assert each precondition.

blender --background --factory-startup --offline-mode --python-exit-code 1 \
    --python blender/scripts/make_fixtures.py -- --golden <path> --out-dir <dir>

Also writes `<out-dir>/expected.json`: {fixture: [expected failing FAIL rules]} for the comparison in the core.
"""
import argparse
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_entities import ENTITIES, build_bmesh  # noqa: E402

E = "ent_vehicle_wheeled_a"
_GOLDEN_VERTS: list[int] = []   # vertex count per LOD of the golden file, read in main()


def obj(n: int):
    return bpy.data.objects[f"{E}_LOD{n}"]


def tris(o) -> int:
    o.data.calc_loop_triangles()
    return len(o.data.loop_triangles)


def transform_data(objs, m: Matrix) -> None:
    for o in objs:
        o.data.transform(m)
        o.data.update()


def bmesh_edit(o, fn) -> None:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    fn(bm)
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()


def fx_ent01_name():
    obj(1).data.name = "vehicle_lod1"
    obj(1).name = "vehicle_lod1"


def fx_ent02_units():
    bpy.context.scene.unit_settings.scale_length = 0.001


def fx_ent03_scale():
    obj(0).scale = (100.0, 100.0, 100.0)


def fx_ent04_budget():
    o = obj(1)
    bm = build_bmesh(ENTITIES[E], {"wheels": 128})
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()


def fx_ent06_size():
    transform_data([obj(n) for n in range(3)], Matrix.Diagonal((0.05, 0.05, 0.05, 1.0)))


def fx_ent07_drift():
    transform_data([obj(2)], Matrix.Diagonal((1.1, 1.0, 1.0, 1.0)))


def fx_ent08_origin():
    transform_data([obj(n) for n in range(3)], Matrix.Translation((0.0, 0.0, 0.5)))


def fx_ent09_loose():
    bmesh_edit(obj(1), lambda bm: bm.verts.new((0.0, 0.0, 1.0)))


def fx_ent10_material():
    obj(0).data.materials.append(obj(0).data.materials[0])


def fx_ent12_shapekey():
    obj(0).shape_key_add(name="Basis")
    obj(0).shape_key_add(name="Key 1")


def fx_ent14_extra():
    bpy.data.collections[E].objects.link(bpy.data.objects.new("extra_empty", None))


def fx_ent15_flip():
    def flip(bm):
        bm.faces.ensure_lookup_table()
        bmesh.ops.reverse_faces(bm, faces=[bm.faces[0]])
    bmesh_edit(obj(0), flip)


def _pre_flip() -> bool:
    bm = bmesh.new()
    bm.from_mesh(obj(0).data)
    bm.faces.ensure_lookup_table()
    n0 = bm.faces[0].normal.copy()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    ok = n0.dot(bm.faces[0].normal) < 0 and all(e.is_manifold for e in bm.edges)
    bm.free()
    return ok


def _zmin(o) -> float:
    return min(v.co.z for v in o.data.vertices)


def _xdim(o) -> float:
    xs = [v.co.x for v in o.data.vertices]
    return max(xs) - min(xs)


# (mutation, expected failing set, precondition after reopening the saved file)
FIXTURES = {
    "fx_ent01_name": (fx_ent01_name, ["ENT-01"], lambda: "vehicle_lod1" in bpy.data.objects
                      and bpy.data.objects["vehicle_lod1"].data.name == "vehicle_lod1"),
    "fx_ent02_units": (fx_ent02_units, ["ENT-02"],
                       lambda: abs(bpy.context.scene.unit_settings.scale_length - 0.001) < 1e-9),
    "fx_ent03_scale": (fx_ent03_scale, ["ENT-03"], lambda: tuple(obj(0).scale) == (100.0, 100.0, 100.0)),
    "fx_ent04_budget": (fx_ent04_budget, ["ENT-04", "ENT-05"], lambda: tris(obj(1)) == 2084),
    "fx_ent06_size": (fx_ent06_size, ["ENT-06"], lambda: abs(max(obj(0).dimensions) - 0.25) < 1e-5),
    "fx_ent07_drift": (fx_ent07_drift, ["ENT-07"], lambda: abs(_xdim(obj(2)) - 1.1 * _xdim(obj(0))) < 1e-5),
    "fx_ent08_origin": (fx_ent08_origin, ["ENT-08"], lambda: all(abs(_zmin(obj(n)) - 0.5) < 1e-5 for n in range(3))),
    "fx_ent09_loose": (fx_ent09_loose, ["ENT-09"], lambda: len(obj(1).data.vertices) == _GOLDEN_VERTS[1] + 1),
    "fx_ent10_material": (fx_ent10_material, ["ENT-10"], lambda: len(obj(0).material_slots) == 2),
    "fx_ent12_shapekey": (fx_ent12_shapekey, ["ENT-12"], lambda: len(obj(0).data.shape_keys.key_blocks) == 2),
    "fx_ent14_extra": (fx_ent14_extra, ["ENT-14"], lambda: len(bpy.data.collections[E].objects) == 4),
    "fx_ent15_flip": (fx_ent15_flip, ["ENT-15"], _pre_flip),
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    golden = str(Path(a.golden).resolve())
    out = Path(a.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    ok = True
    bpy.ops.wm.open_mainfile(filepath=golden)
    _GOLDEN_VERTS[:] = [len(obj(n).data.vertices) for n in range(3)]
    for name, (mutate, _, pre) in FIXTURES.items():
        bpy.ops.wm.open_mainfile(filepath=golden)
        mutate()
        path = out / f"{name}.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False, copy=True)
        bpy.ops.wm.open_mainfile(filepath=str(path))
        good = bool(pre())
        print(f"make_fixtures: {name} precondition {'ok' if good else 'FAILED'}")
        ok &= good
    (out / "expected.json").write_text(
        json.dumps({k: v[1] for k, v in FIXTURES.items()}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:]))
