"""Import a built tile into Blender at real scale so artists can author entities against the terrain (SPEC 11.4).

Reads `dist/<aoi>/tile.json`, the batch GLBs of one profile, and `scene.json`; writes nothing under `dist/`.
Frame: the tile is glTF Y up with +Z south and the origin at the NW corner. Blender's glTF importer converts
that to Z up, so east is +X, north is +Y, and the tile covers x in [0, extent], y in [-extent, 0].
"""
import json
import math
from pathlib import Path

import bpy
import numpy as np


def list_aois(repo_root: Path) -> list[str]:
    """AOI ids that have a built tile under <repo_root>/dist, sorted."""
    return sorted(p.parent.name for p in (repo_root / "dist").glob("*/tile.json"))


def _import_glb(path: Path, coll) -> list:
    """Import one GLB into `coll`; return the new objects. Does not touch the source file."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    return new


def _heights(dist: Path, tile: dict):
    """Height function over cell (row, col) from the RG8 height texture (9.1)."""
    t = next(t for t in tile["textures"] if t["id"] == "height")
    raw = np.fromfile(dist / t["file"], dtype=np.uint8).reshape(t["height"], t["width"], 2).astype(np.float64)
    lo, hi = tile["height"]["min"], tile["height"]["max"]
    return lambda r, c: lo + (raw[r, c, 0] * 256 + raw[r, c, 1]) / 65535 * (hi - lo)


def _layer(coll):
    def find(lc):
        if lc.collection == coll:
            return lc
        return next((f for f in map(find, lc.children) if f), None)
    return find(bpy.context.view_layer.layer_collection)


def _place_entities(entities_dir: Path, dist: Path, tile: dict, parent) -> int:
    """One collection instance per scene.json placement, entity LOD0 GLB, heading clockwise from north."""
    scene = json.loads((dist / tile["scene"]).read_text(encoding="utf-8"))
    height, scale = _heights(dist, tile), tile["table"]["scale"]
    sources = {}
    for name in sorted({i["entity"] for i in scene["instances"]}):
        glb = entities_dir / name / f"{name}_LOD0.glb"
        if glb.exists():
            sources[name] = bpy.data.collections.new(f"{name}_LOD0")
            parent.children.link(sources[name])
            _import_glb(glb, sources[name])
    placed = 0
    for i in scene["instances"]:
        if i["entity"] not in sources:
            continue
        inst = bpy.data.objects.new(i["entity"], None)
        inst.instance_type, inst.instance_collection = "COLLECTION", sources[i["entity"]]
        r, c = i["cell"]
        # tile (x, z south) -> Blender (x, -z); the model front is -Y, so yaw pi - heading faces the heading
        inst.location = (i["x"], -i["z"], height(r, c) + i["hover_table_m"] * scale)
        inst.rotation_euler = (0.0, 0.0, math.pi - math.radians(i["heading_deg"]))
        parent.objects.link(inst)
        placed += 1
    for src in sources.values():  # sources stay in the file but out of the view layer
        _layer(src).exclude = True
    return placed


def import_tile(repo_root: Path, aoi: str | None = None, profile: str | None = None, entities: bool = True) -> dict:
    """Returns {"collection", "aoi", "profile", "terrain_objects", "instances"}. Raises FileNotFoundError."""
    repo_root = Path(repo_root)
    aois = list_aois(repo_root)
    aoi = aoi or (aois[0] if aois else None)
    if aoi not in aois:
        raise FileNotFoundError(f"no built tile for {aoi!r} under {repo_root / 'dist'}")
    dist = repo_root / "dist" / aoi
    tile = json.loads((dist / "tile.json").read_text(encoding="utf-8"))
    profile = profile if profile in tile["profiles"] else next(iter(tile["profiles"]))  # "all" -> first profile
    coll = bpy.data.collections.new(f"{aoi}_{profile}")
    bpy.context.scene.collection.children.link(coll)
    n = sum(len(_import_glb(dist / b["file"], coll)) for b in tile["profiles"][profile]["batches"])
    inst = _place_entities(repo_root / "dist" / "entities", dist, tile, coll) if entities else 0
    return {"collection": coll.name, "aoi": aoi, "profile": profile, "terrain_objects": n, "instances": inst}
