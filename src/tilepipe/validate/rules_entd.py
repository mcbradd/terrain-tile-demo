"""Entity deliverable rules on exported GLBs (SPEC 12.7): ENTD-01 to ENTD-06.

Inputs are `dist/entities/<entity>/<entity>_LOD<n>.glb` and `entity.json`. With `--skip-entities` every ENTD rule is
SKIP with that reason. Without the flag, a missing GLB or entity.json is a FAIL: the deliverable gate has nothing to
approve, and 12.1 allows SKIP only where the spec says so.
"""
import numpy as np

from tilepipe.validate import common
from tilepipe.validate.registry import check_result, implements, skip

VERTS_MAX, MIN_Y_TOL_M, CENTER_FRAC, SIZE_TOL_M, NORMAL_TOL = 65535, 0.005, 0.01, 0.001, 0.01
LODS = 3


class Missing(Exception):
    pass


def _ent(scope: str) -> str:
    return scope.split(":", 1)[1]


def lod_files(ctx, ent: str) -> list:
    files = [common.entity_dir(ctx, ent) / f"{ent}_LOD{n}.glb" for n in range(LODS)]
    gone = [common.rel(ctx, f) for f in files if not f.exists()]
    if gone:
        raise Missing(", ".join(gone))
    return files


def loaded(ctx, ent: str, n: int):
    """(doc, binary, primitive, positions, indices) of one LOD, positions as float64."""
    f = lod_files(ctx, ent)[n]
    doc, binary = common.glb_parts(ctx, f)
    prim = doc["meshes"][0]["primitives"][0]
    pos = common.accessor(doc, binary, prim["attributes"]["POSITION"]).astype(np.float64)
    idx = common.accessor(doc, binary, prim["indices"]) if "indices" in prim else np.arange(len(pos))
    return doc, binary, prim, pos, idx


def _guard(rule_id: str):
    """Wrap a per-entity check: SKIP under --skip-entities, FAIL on missing files."""
    def deco(fn):
        def check(ctx, scope):
            if ctx.options.get("skip_entities"):
                return skip(rule_id, scope, "--skip-entities")
            try:
                return fn(ctx, scope, _ent(scope))
            except Missing as e:
                return check_result(rule_id, scope, False, f"missing {e}", "present", "", "==",
                                    "Run `uv run tilepipe entities` to export the GLBs.")
        check.__doc__ = fn.__doc__
        return implements(rule_id)(check)
    return deco


@_guard("ENTD-01")
def entd01(ctx, scope, ent):
    bad = []
    for n in range(LODS):
        doc, _, prim, pos, idx = loaded(ctx, ent, n)
        tris, limit = len(idx) // 3, ctx.entity_lods["lod"][n]["tris_max"]
        if tris > limit:
            bad.append(f"LOD {n} has {tris} triangles, limit {limit}")
        if len(doc["meshes"]) != 1 or len(doc["meshes"][0]["primitives"]) != 1:
            bad.append(f"LOD {n} does not have exactly one mesh and one primitive")
        if len(doc.get("materials", [])) != 1 or "material" not in prim:
            bad.append(f"LOD {n} does not have exactly one material")
        if doc.get("images") or doc.get("textures"):
            bad.append(f"LOD {n} carries images or textures")
    return common.violations("ENTD-01", scope, bad, "defects", "Fix the asset against entity_lods.toml and re-export (11.5).")


@_guard("ENTD-02")
def entd02(ctx, scope, ent):
    worst = max(len(loaded(ctx, ent, n)[3]) for n in range(LODS))
    return check_result("ENTD-02", scope, worst <= VERTS_MAX, worst, VERTS_MAX, "vertices", "<=",
                        "Reduce the mesh so a uint16 index suffices.")


@_guard("ENTD-03")
def entd03(ctx, scope, ent):
    bad = []
    for n in range(LODS):
        for i, node in enumerate(loaded(ctx, ent, n)[0].get("nodes", [])):
            t, r, s = node.get("translation", [0, 0, 0]), node.get("rotation", [0, 0, 0, 1]), node.get("scale", [1, 1, 1])
            m = node.get("matrix", [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])
            if not (np.allclose(t, 0, atol=1e-6) and np.allclose(r, [0, 0, 0, 1], atol=1e-6)
                    and np.allclose(s, 1, atol=1e-6) and np.allclose(m, np.eye(4).ravel(), atol=1e-6)):
                bad.append(f"LOD {n} node {i} is not identity")
    return common.violations("ENTD-03", scope, bad, "nodes", "Apply transforms before export (6.5, 11.2).")


@_guard("ENTD-04")
def entd04(ctx, scope, ent):
    checks = []
    for n in range(LODS):
        pos = loaded(ctx, ent, n)[3]
        lo, hi = pos.min(axis=0), pos.max(axis=0)
        big = float((hi - lo).max())
        checks += [(f"m, LOD {n} min Y", round(abs(float(lo[1])), 5), MIN_Y_TOL_M, "<="),
                   (f"m, LOD {n} X and Z center", round(float(max(abs(lo[0] + hi[0]), abs(lo[2] + hi[2])) / 2), 5),
                    round(CENTER_FRAC * big, 5), "<=")]
    return common.multi("ENTD-04", scope, checks, "Put the origin at the center of the ground footprint (6.5, 11.2).")


@_guard("ENTD-05")
def entd05(ctx, scope, ent):
    info = common.jload(ctx, common.entity_dir(ctx, ent) / "entity.json")
    src = float((np.asarray(info["bbox_m"]["max"]) - np.asarray(info["bbox_m"]["min"])).max())
    dims = [float((p.max(axis=0) - p.min(axis=0)).max()) for p in (loaded(ctx, ent, n)[3] for n in range(LODS))]
    worst = max(abs(d - src) for d in dims)
    return check_result("ENTD-05", scope, worst <= SIZE_TOL_M, round(worst, 5), SIZE_TOL_M, "m", "<=",
                        f"The exported size differs from the source's {src:.4f} m; export with the exact call of 11.5.")


@_guard("ENTD-06")
def entd06(ctx, scope, ent):
    worst, bad = 0.0, []
    for n in range(LODS):
        doc, binary, prim, _, _ = loaded(ctx, ent, n)
        if "NORMAL" not in prim["attributes"]:
            bad.append(f"LOD {n} has no NORMAL accessor")
            continue
        nrm = common.accessor(doc, binary, prim["attributes"]["NORMAL"]).astype(np.float64)
        worst = max(worst, float(np.abs(np.linalg.norm(nrm, axis=1) - 1).max()))
    return check_result("ENTD-06", scope, not bad and worst <= NORMAL_TOL, "no NORMAL" if bad else round(worst, 5), NORMAL_TOL,
                        "", "<=", "Export with export_normals=True (11.5).")
