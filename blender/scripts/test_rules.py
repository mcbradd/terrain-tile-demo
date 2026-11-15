"""Procedural cases for the ENT rules the fixtures do not cover: ENT-05, ENT-11, ENT-13, plus the ENT-15 SKIP
(SPEC 12.9). Each rule gets one passing and one failing case. Run headless; exits 1 on any failed assertion.

blender --background --factory-startup --offline-mode --python-exit-code 1 --python blender/scripts/test_rules.py
"""
import sys
import traceback
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tilepipe_tools import rules  # noqa: E402

LIMITS = [7000, 1500, 400]
NAME = "ent_test_shape_a"


def cyl(segments: int):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=segments, radius1=0.5, radius2=0.5,
                          depth=1.0, matrix=Matrix.Translation((0, 0, 0.5)))
    return bm


def grid(segments: int):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=segments, y_segments=segments, size=0.5)
    return bm


def asset(bms: list) -> rules.Asset:
    """A fresh file holding one entity collection whose LOD n mesh is bms[n]."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    coll = bpy.data.collections.new(NAME)
    scene.collection.children.link(coll)
    mat = bpy.data.materials.new(f"M_{NAME}")
    for n, bm in enumerate(bms):
        me = bpy.data.meshes.new(f"{NAME}_LOD{n}")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        coll.objects.link(bpy.data.objects.new(me.name, me))
    return rules.Asset(coll, scene, bpy.context.evaluated_depsgraph_get(), LIMITS, f"entity:{NAME}")


def status(rule, a: rules.Asset) -> str:
    rec = rule(a)
    assert rec["message"].startswith(f"{rec['rule']} {rec['status']} {a.scope}: "), rec["message"]
    return rec["status"]


def test_ent05():
    assert status(rules.ent05, asset([cyl(64), cyl(32), cyl(16)])) == "PASS"      # 256, 128, 64 tris
    assert status(rules.ent05, asset([cyl(64), cyl(33), cyl(16)])) == "FAIL"      # 132 > 128


def test_ent11():
    assert status(rules.ent11, asset([grid(250), cyl(8), cyl(4)])) == "PASS"      # 251^2 = 63,001 vertices
    assert status(rules.ent11, asset([grid(256), cyl(8), cyl(4)])) == "FAIL"      # 257^2 = 66,049 vertices


def test_ent13():
    a = asset([cyl(16), cyl(8), cyl(4)])
    assert status(rules.ent13, a) == "PASS"
    bpy.data.objects[f"{NAME}_LOD0"].modifiers.new("tri", "TRIANGULATE")
    assert status(rules.ent13, a) == "WARN"
    assert "ENT-13" not in rules.failed(rules.run_gate(a))                         # WARN never fails the gate


def test_ent15_skip():
    assert status(rules.ent15, asset([cyl(16), cyl(8), cyl(4)])) == "PASS"
    rec = rules.ent15(asset([grid(4), grid(2), grid(1)]))                          # open sheets: not manifold
    assert rec["status"] == "SKIP" and "not manifold" in rec["message"], rec


def test_panel_operators_registered():
    import tilepipe_tools
    tilepipe_tools.register()
    try:
        for op in ("validate_asset", "export_asset"):
            assert getattr(bpy.ops.tilepipe, op).idname() == f"TILEPIPE_OT_{op}"
        assert bpy.types.TILEPIPE_PT_panel.bl_category == "Tile Pipeline"
        assert [i.identifier for i in bpy.types.Scene.bl_rna.properties["tilepipe"].fixed_type
                .bl_rna.properties["profile"].enum_items] == ["mobile_ar", "workstation", "all"]
    finally:
        tilepipe_tools.unregister()


def main() -> int:
    bad = 0
    for name, fn in sorted((k, v) for k, v in globals().items() if k.startswith("test_")):
        try:
            fn()
            print(f"test_rules: {name} ok")
        except Exception:
            bad += 1
            print(f"test_rules: {name} FAILED\n{traceback.format_exc()}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
