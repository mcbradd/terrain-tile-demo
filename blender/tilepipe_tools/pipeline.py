"""Source gate and export (SPEC 11.4, 11.5). Shared by the panel operators and the headless scripts."""
import hashlib
import json
from pathlib import Path

import bpy

from . import rules

TABLE_SIZE_M_KEY = "token_table_size_m"


def entity_collections(scene) -> list:
    return sorted((c for c in scene.collection.children_recursive if c.name.startswith("ent_")), key=lambda c: c.name)


def gate(scene, coll, repo_root: Path, scope: str) -> list[dict]:
    """Run ENT-01 to ENT-15 on one collection. Records keep the `object` key for the panel."""
    limits = rules.tris_limits(rules.load_entity_lods(repo_root))
    asset = rules.Asset(coll, scene, bpy.context.evaluated_depsgraph_get(), limits, scope)
    return rules.run_gate(asset)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _export_glb(obj, path: Path) -> None:
    """SPEC 11.5: deselect all, select the object, make it active, then the exact export call."""
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=str(path), check_existing=False, export_format='GLB',
        use_selection=True, export_apply=True, export_yup=True,
        export_texcoords=False, export_normals=True, export_tangents=False,
        export_materials='EXPORT', export_vertex_color='NONE',
        export_cameras=False, export_lights=False, export_animations=False,
        export_skins=False, export_morph=False, export_extras=False,
        export_draco_mesh_compression_enable=False,
        export_meshopt_compression_enable=False,
        export_use_gltfpack=False, will_save_settings=False)


def _base_color_srgb(mat) -> str:
    bsdf = next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    lin = bsdf.inputs["Base Color"].default_value[:3]
    srgb = [c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in lin]
    return "#" + "".join(f"{round(min(max(c, 0.0), 1.0) * 255):02X}" for c in srgb)


def export_asset(coll, out_dir: Path, repo_root: Path, blend_path: Path) -> Path:
    """Write <entity>_LOD<n>.glb for n = 0..2 and a partial entity.json to out_dir.

    The partial entity.json holds everything the source knows. The core completes each LOD's `tris`,
    `vertices`, `bytes`, and `sha256` from the exported GLBs (SPEC 11.6).
    """
    entity = coll.name
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    lod0 = bpy.data.objects[f"{entity}_LOD0"]
    lo, hi = rules.bounds(lod0.data)
    lods = []
    for n in range(3):
        name = f"{entity}_LOD{n}"
        _export_glb(bpy.data.objects[name], out_dir / f"{name}.glb")
        lods.append({"n": n, "file": f"{name}.glb", "primitives": 1, "materials": 1, "texture_bytes": 0})
    table = rules.load_entity_lods(repo_root)[TABLE_SIZE_M_KEY]
    # Blender Z up (x, y, z) to glTF Y up (x, z, -y), SPEC 6.5.
    doc = {
        "schema": 1,
        "id": entity,
        "class": entity.split("_")[1],
        "display": {"mode": "token", "table_size_m": float(table)},
        "up": "+Y", "front": "+Z", "origin": "ground footprint center",
        "bbox_m": {"min": [round(float(v), 6) + 0.0 for v in (lo[0], lo[2], -hi[1])],
                   "max": [round(float(v), 6) + 0.0 for v in (hi[0], hi[2], -lo[1])]},
        "base_color_srgb": _base_color_srgb(lod0.material_slots[0].material),
        "lods": lods,
        "source_blend_sha256": _sha256(blend_path),
    }
    path = out_dir / "entity.json"
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return path
