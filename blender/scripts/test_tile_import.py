"""Headless test of the Import Tile operator (SPEC 11.4): count, bounds, north is +Y, NW corner at the origin,
entity placements face their headings and sit on the terrain, and dist/ is left untouched.

blender --background --factory-startup --offline-mode --python-exit-code 1 --python blender/scripts/test_tile_import.py -- --repo-root <dir>

<dir> holds dist/<aoi>/tile.json; the extension source is this checkout's blender/tilepipe_tools.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # the extension source directory
import tilepipe_tools  # noqa: E402


def snapshot(d: Path) -> dict:
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in d.rglob("*") if p.is_file()}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    root = Path(ap.parse_args(argv).repo_root).resolve()
    tilepipe_tools.register()
    aoi = tilepipe_tools.tile_import.list_aois(root)[0]     # default is the first AOI under dist/
    tile = json.loads((root / "dist" / aoi / "tile.json").read_text(encoding="utf-8"))
    ext = tile["extent_m"]
    profile = bpy.context.scene.tilepipe.profile            # factory default mobile_ar
    before = snapshot(root / "dist")

    assert bpy.ops.tilepipe.import_tile(repo_root=str(root)) == {"FINISHED"}
    assert snapshot(root / "dist") == before, "import modified dist/"

    coll = bpy.data.collections[f"{aoi}_{profile}"]
    terrain = [o for o in coll.objects if o.type == "MESH"]
    batches = tile["profiles"][profile]["batches"]
    assert len(terrain) == len(batches), (len(terrain), len(batches))

    pts = np.concatenate([np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices]) for o in terrain])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    tol = 0.01
    assert abs(lo[0]) < tol and abs(hi[0] - ext) < tol, ("x extent", lo, hi)           # west 0, east 10240
    assert abs(hi[1]) < tol and abs(lo[1] + ext) < tol, ("y extent", lo, hi)           # north 0 (+Y), south -10240
    # each object's bounds match its batch aabb (tile frame x, y up, z south -> Blender x, -z, y); skirts included
    boxes = sorted((tuple(np.round([*b["aabb"]["min"], *b["aabb"]["max"]], 2)) for b in batches))
    for o in terrain:
        p = np.array([tuple(o.matrix_world @ v.co) for v in o.data.vertices])
        a, z = p.min(axis=0), p.max(axis=0)
        key = (a[0], a[2], -z[1], z[0], z[2], -a[1])   # (xmin, ymin, zmin, xmax, ymax, zmax) in the tile frame
        assert any(np.allclose(key, b, atol=0.01) for b in boxes), (o.name, key)
    hmax = hi[2]
    nw = pts[(pts[:, 0] < tol) & (pts[:, 1] > -tol)]
    assert len(nw) > 0, "no vertex at the NW corner (0, 0)"

    # north is +Y: the instances sit on the terrain only if +Y is north, because relief is large and asymmetric
    insts = [o for o in coll.all_objects if o.instance_type == "COLLECTION"]
    scene = json.loads((root / "dist" / aoi / tile["scene"]).read_text(encoding="utf-8"))
    assert len(insts) == len(scene["instances"]) > 0
    slack = max(p["e_star_m"] for p in tile["profiles"].values()) + 1.0   # mesh LOD error bound
    for o, s in zip(insts, scene["instances"]):
        assert o.name.startswith(s["entity"]) and abs(o.location.x - s["x"]) < tol and abs(o.location.y + s["z"]) < tol
        hit_z = None
        for t in terrain:
            inv = t.matrix_world.inverted()
            ok, loc, _n, _i = t.ray_cast(inv @ Vector((o.location.x, o.location.y, hmax + 100)), Vector((0, 0, -1)))
            if ok:
                hit_z = (t.matrix_world @ loc).z
        assert hit_z is not None and abs(hit_z + s["hover_table_m"] * tile["table"]["scale"] - o.location.z) <= slack, (o.name, hit_z, o.location.z)
        front = o.matrix_world.to_3x3() @ Vector((0, -1, 0))           # entity front is Blender -Y (6.5)
        h = math.radians(s["heading_deg"])
        assert (front.xy - Vector((math.sin(h), math.cos(h)))).length < 1e-4, (o.name, front, s["heading_deg"])

    print(f"OK {aoi}/{profile}: {len(terrain)} terrain objects, {len(insts)} entities, "
          f"x [{lo[0]:.1f}, {hi[0]:.1f}] y [{lo[1]:.1f}, {hi[1]:.1f}] z [{lo[2]:.1f}, {hi[2]:.1f}]")
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv[sys.argv.index("--") + 1:])
    except AssertionError as e:
        print("FAIL", e)
        code = 1
    sys.exit(code)
