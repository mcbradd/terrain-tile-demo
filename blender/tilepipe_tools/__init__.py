"""Tile Pipeline Tools: validate and export tabletop entities against hardware budgets (SPEC 11.4)."""
from pathlib import Path

import bpy
from bpy.props import CollectionProperty, EnumProperty, IntProperty, PointerProperty, StringProperty

from . import pipeline, rules

PROFILES = (("mobile_ar", "mobile_ar", ""), ("workstation", "workstation", ""), ("all", "all", ""))


def _repo_root(context) -> Path | None:
    prefs = context.preferences.addons.get(__package__)
    root = prefs.preferences.repo_root if prefs else ""
    return Path(bpy.path.abspath(root)) if root else None


def _active_collection(context):
    coll = context.view_layer.active_layer_collection.collection
    return None if coll == context.scene.collection else coll


def _select_result(self, context) -> None:
    """Clicking a results row selects and frames its object."""
    items = context.scene.tilepipe.results
    if not 0 <= self.result_index < len(items):
        return
    obj = context.scene.objects.get(items[self.result_index].object)
    if obj is None:
        return
    for o in context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    for area in context.screen.areas if context.screen else ():
        if area.type == "VIEW_3D":
            region = next(r for r in area.regions if r.type == "WINDOW")
            with context.temp_override(area=area, region=region):
                bpy.ops.view3d.view_selected()


class TILEPIPE_Prefs(bpy.types.AddonPreferences):
    bl_idname = __package__
    repo_root: StringProperty(name="Repository root", subtype="DIR_PATH",
                              description="Directory holding entity_lods.toml and profiles/")

    def draw(self, context):
        self.layout.prop(self, "repo_root")


class TILEPIPE_Result(bpy.types.PropertyGroup):
    severity: StringProperty()
    status: StringProperty()
    rule: StringProperty()
    object: StringProperty()
    message: StringProperty()


class TILEPIPE_State(bpy.types.PropertyGroup):
    profile: EnumProperty(name="Profile", items=PROFILES, default="mobile_ar")
    results: CollectionProperty(type=TILEPIPE_Result)
    result_index: IntProperty(default=-1, update=_select_result)


class TILEPIPE_UL_results(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.status, icon="ERROR" if item.status == "FAIL" else
                  "INFO" if item.status == "WARN" else "CHECKMARK")
        row.label(text=item.rule)
        row.label(text=item.object or "-")
        row.label(text=item.message)


def _store(context, records: list[dict]) -> int:
    st = context.scene.tilepipe
    st.results.clear()
    for r in records:
        it = st.results.add()
        it.severity, it.status, it.rule = r["severity"], r["status"], r["rule"]
        it.object, it.message = r.get("object", ""), r["message"]
    st.result_index = -1
    return len(rules.failed(records))


class TILEPIPE_OT_validate_asset(bpy.types.Operator):
    """Run the source gate (ENT-01 to ENT-15) on the active collection"""
    bl_idname = "tilepipe.validate_asset"
    bl_label = "Validate Asset"

    def execute(self, context):
        root, coll = _repo_root(context), _active_collection(context)
        if root is None or coll is None:
            self.report({"ERROR"}, "Set the repo_root preference and make an entity collection active.")
            return {"CANCELLED"}
        fails = _store(context, pipeline.gate(context.scene, coll, root, f"entity:{coll.name}"))
        self.report({"ERROR" if fails else "INFO"}, f"{coll.name}: {fails} FAIL")
        return {"FINISHED"}


class TILEPIPE_OT_export_asset(bpy.types.Operator):
    """Run the source gate, then export three GLBs and a partial entity.json"""
    bl_idname = "tilepipe.export_asset"
    bl_label = "Export Asset"

    def execute(self, context):
        root, coll = _repo_root(context), _active_collection(context)
        if root is None or coll is None or not bpy.data.filepath:
            self.report({"ERROR"}, "Set repo_root, save the file, and make an entity collection active.")
            return {"CANCELLED"}
        fails = _store(context, pipeline.gate(context.scene, coll, root, f"entity:{coll.name}"))
        if fails:
            self.report({"ERROR"}, f"Export aborted: {fails} FAIL. See the results list.")
            return {"CANCELLED"}
        out = root / "assets" / "entities" / coll.name / "export"
        pipeline.export_asset(coll, out, root, Path(bpy.data.filepath))
        self.report({"INFO"}, f"Exported {coll.name} to {out}")
        return {"FINISHED"}


class TILEPIPE_PT_panel(bpy.types.Panel):
    bl_label = "Tile Pipeline"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tile Pipeline"

    def draw(self, context):
        layout, st = self.layout, context.scene.tilepipe
        layout.prop(st, "profile")
        root, coll = _repo_root(context), _active_collection(context)
        if root is None:
            layout.label(text="Set repo_root in the add-on preferences.", icon="ERROR")
        else:
            try:
                limits = rules.tris_limits(rules.load_entity_lods(root))
                profiles = rules.load_profiles(root)
            except OSError:
                limits, profiles = [], {}
            used = {p["entities"]["lod"] for name, p in profiles.items() if st.profile in (name, "all")}
            box = layout.box()
            asset = rules.Asset(coll, context.scene, context.evaluated_depsgraph_get(), limits, "") if coll else None
            for n, lim in enumerate(limits):
                obj = bpy.data.objects.get(f"{coll.name}_LOD{n}") if coll else None
                tris = asset.counts(obj)[0] if obj and obj.type == "MESH" else 0
                row = box.row()
                row.alert = tris > lim
                row.label(text=f"LOD{n}{' *' if n in used else ''}")
                row.label(text=f"{tris:,} / {lim:,} tris")
        layout.operator("tilepipe.validate_asset")
        layout.template_list("TILEPIPE_UL_results", "", st, "results", st, "result_index", rows=5)
        layout.operator("tilepipe.export_asset")


CLASSES = (TILEPIPE_Prefs, TILEPIPE_Result, TILEPIPE_State, TILEPIPE_UL_results,
           TILEPIPE_OT_validate_asset, TILEPIPE_OT_export_asset, TILEPIPE_PT_panel)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.tilepipe = PointerProperty(type=TILEPIPE_State)


def unregister():
    del bpy.types.Scene.tilepipe
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
