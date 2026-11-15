"""Terrain rules (SPEC 12.5): TER-01 to TER-11."""
import numpy as np

from tilepipe import batch
from tilepipe.validate import common
from tilepipe.validate.common import CHUNKS, CHUNK_CELLS, LODS, TILE_M, chunk_ids, lod_counts
from tilepipe.validate.registry import check_result, implements

SKIRT_TOL_M, TER04_TOL_M, AABB_TOL_M = 0.001, 0.10, 0.001
# Outward directions of the skirt edges in the order N, E, S, W (7.3), as (x, z).
OUTWARD = np.array([[0.0, -1.0], [1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])


def chunk_file(ctx, cid: str, k: int):
    return common.dist(ctx) / f"terrain_{cid}_lod{k}.glb"


def _profile(ctx, scope: str) -> tuple[str, dict, dict]:
    name = scope.split(":", 1)[1]
    return name, ctx.profiles[name], common.tile(ctx)["profiles"][name]


def surface_tri_normals_y(pos: np.ndarray, idx: np.ndarray, q: int) -> np.ndarray:
    """y component of the (unnormalized) normal of every surface triangle of a chunk LOD with q quads per side."""
    t = idx[:6 * q * q].reshape(-1, 3).astype(np.int64)
    p = pos.astype(np.float64)
    u, v = p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]]
    return u[:, 2] * v[:, 0] - u[:, 0] * v[:, 2]


def skirt_problems(pos: np.ndarray, idx: np.ndarray, k: int, depth: float, plinth: float,
                   border: list[bool]) -> list[str]:
    """TER-05 on one chunk LOD. `border[e]` says edge e (N, E, S, W) lies on the tile edge."""
    n, nverts, _ = lod_counts(k)
    q = n - 1
    bad = []
    if len(pos) != nverts:
        return [f"{len(pos)} vertices, expected {nverts}"]
    p = pos.astype(np.float64)
    r = np.arange(n)
    tops = [r, r * n + n - 1, (n - 1) * n + r[::-1], r[::-1] * n]
    for e in range(4):
        bot = n * n + e * n + r
        top = tops[e]
        want = plinth if border[e] else p[top, 1] - depth
        dy = np.abs(p[bot, 1] - want)
        if dy.max() > SKIRT_TOL_M:
            bad.append(f"edge {'NESW'[e]} skirt y off by {dy.max():.4f} m")
        if np.abs(p[bot][:, [0, 2]] - p[top][:, [0, 2]]).max() > 0:
            bad.append(f"edge {'NESW'[e]} skirt x or z differs from its surface vertex")
    skirt = idx[6 * q * q:].reshape(-1, 3).astype(np.int64)
    if len(skirt) != 8 * q:
        return bad + [f"{len(skirt)} skirt triangles, expected {8 * q}"]
    u, v = p[skirt[:, 1]] - p[skirt[:, 0]], p[skirt[:, 2]] - p[skirt[:, 0]]
    nrm = np.cross(u, v)
    out = np.repeat(OUTWARD, 2 * q, axis=0)
    dot = nrm[:, 0] * out[:, 0] + nrm[:, 2] * out[:, 1]
    if (dot <= 0).any():
        bad.append(f"{int((dot <= 0).sum())} skirt triangles wind inward")
    return bad


@implements("TER-01")
def ter01(ctx, scope):
    name, prof, entry = _profile(ctx, scope)
    tris = 0
    for b in entry["batches"]:
        _, idx, _ = common.mesh(ctx, common.dist(ctx) / b["file"])
        tris += len(idx) // 3
    return check_result("TER-01", scope, tris <= prof["budget"]["terrain_tris_max"], tris,
                        prof["budget"]["terrain_tris_max"], "tris", "<=",
                        "Raise pixel_error or lower terrain share in the profile, or coarsen the LOD selection.")


@implements("TER-02")
def ter02(ctx, scope):
    tile = common.tile(ctx)
    counts, bad = {}, []
    for _, _, cid in chunk_ids():
        for k in range(LODS):
            pos, idx, _ = common.mesh(ctx, chunk_file(ctx, cid, k))
            counts[cid, k] = (len(pos), len(idx) // 3)
            _, nv, nt = lod_counts(k)
            if counts[cid, k] != (nv, nt):
                bad.append(f"{cid} LOD {k} has {counts[cid, k][0]} vertices and {counts[cid, k][1]} triangles, "
                           f"expected {nv} and {nt}")
    for name, entry in tile["profiles"].items():
        for b in entry["batches"]:
            pos, idx, _ = common.mesh(ctx, common.dist(ctx) / b["file"])
            want = sum(counts[c, entry["selection"][c]][1] for c in b["chunks"])
            if len(idx) // 3 != want:
                bad.append(f"{b['file']} has {len(idx) // 3} triangles, its chunks sum to {want}")
    return common.violations("TER-02", scope, bad, "mismatches", "Rebuild with `uv run tilepipe build`; see 7.2 and 7.6.")


@implements("TER-03")
def ter03(ctx, scope):
    bad = []
    for f in common.terrain_glbs(ctx):
        pos, idx, doc = common.mesh(ctx, f)
        if len(idx) and int(idx.max()) >= len(pos):
            bad.append(f"{f.name}: index {int(idx.max())} not below {len(pos)} vertices")
        want = 5123 if len(pos) <= 65535 else 5125
        if common.index_component(doc) != want:
            bad.append(f"{f.name}: index componentType {common.index_component(doc)}, expected {want}")
    return common.violations("TER-03", scope, bad, "files", "Fix the GLB writer's index type rule (7.4).")


@implements("TER-04")
def ter04(ctx, scope):
    name, _, entry = _profile(ctx, scope)
    ht = common.height_texture(ctx)
    worst, bad = 0.0, []
    for b in entry["batches"]:
        pos, _, _ = common.mesh(ctx, common.dist(ctx) / b["file"])
        off = 0
        for cid in b["chunks"]:
            n, nv, _ = lod_counts(entry["selection"][cid])
            s = pos[off:off + n * n].astype(np.float64)
            off += nv
            keep = (s[:, 0] > 0) & (s[:, 0] < TILE_M) & (s[:, 2] > 0) & (s[:, 2] < TILE_M)
            s = s[keep]
            d = np.abs(s[:, 1] - common.bilinear(ht, s[:, 0] / 10 - 0.5, s[:, 2] / 10 - 0.5))
            worst = max(worst, float(d.max()) if len(d) else 0.0)
        if off != len(pos):
            bad.append(f"{b['file']} holds {len(pos)} vertices, its chunks account for {off}")
    return check_result("TER-04", scope, worst <= TER04_TOL_M and not bad, round(worst, 5), TER04_TOL_M, "m", "<=",
                        "Mesh heights and the height texture disagree; check 6.3 and the 7.5 encoding. " + "; ".join(bad))


@implements("TER-05")
def ter05(ctx, scope):
    tile = common.tile(ctx)
    plinth = tile["height"]["plinth_bottom"]
    bad = []
    for cx, cz, cid in chunk_ids():
        border = [cz == 0, cx == CHUNKS - 1, cz == CHUNKS - 1, cx == 0]
        for k in range(LODS):
            pos, idx, _ = common.mesh(ctx, chunk_file(ctx, cid, k))
            depth = tile["chunks"][cz * CHUNKS + cx]["lods"][k]["skirt_depth_m"]
            bad += [f"{cid} LOD {k}: {m}" for m in skirt_problems(pos, idx, k, depth, plinth, border)]
    return common.violations("TER-05", scope, bad, "defects", "Fix skirt winding or depth in lod.chunk_mesh (7.3).")


@implements("TER-06")
def ter06(ctx, scope):
    bad = []
    for _, _, cid in chunk_ids():
        for k in range(LODS):
            pos, idx, _ = common.mesh(ctx, chunk_file(ctx, cid, k))
            ny = surface_tri_normals_y(pos, idx, CHUNK_CELLS >> k)
            if (ny <= 0).any():
                bad.append(f"{cid} LOD {k}: {int((ny <= 0).sum())} surface triangles face down")
    return common.violations("TER-06", scope, bad, "chunk LODs", "Fix surface winding (6.4): quads emit (a, c, b), (b, c, d).")


@implements("TER-07")
def ter07(ctx, scope):
    bad = []
    for cid, c in common.lod_stats(ctx)["chunks"].items():
        e = c["e_max_m"]
        if e[0] != 0:
            bad.append(f"{cid} e_max at LOD 0 is {e[0]}")
        bad += [f"{cid} e_max falls from LOD {k - 1} to {k}" for k in range(1, len(e)) if e[k] < e[k - 1]]
    return common.violations("TER-07", scope, bad, "chunks", "Recompute the error metric of 7.2 step 4.")


@implements("TER-08")
def ter08(ctx, scope):
    name, prof, entry = _profile(ctx, scope)
    got = batch.select(common.lod_stats(ctx), batch.tau(prof), prof["budget"]["terrain_tris_max"])
    bad = []
    if got["selection"] != entry["selection"]:
        diff = [c for c in got["selection"] if got["selection"][c] != entry["selection"].get(c)]
        bad.append(f"selection differs on {', '.join(diff)}")
    if abs(got["e_star_m"] - entry["e_star_m"]) > 1e-6:
        bad.append(f"e_star {entry['e_star_m']} differs from {got['e_star_m']:.6f}")
    if got["budget_forced"] != entry["budget_forced"]:
        bad.append(f"budget_forced {entry['budget_forced']} differs from {got['budget_forced']}")
    return common.violations("TER-08", scope, bad, "differences", "Rerun `uv run tilepipe build --from batch` (7.6).")


@implements("TER-09")
def ter09(ctx, scope):
    name, _, entry = _profile(ctx, scope)
    return check_result("TER-09", scope, entry["error_px_nominal"] <= 4.0, round(entry["error_px_nominal"], 4), 4.0, "px", "<=",
                        "Accepted trade if the triangle budget set the error; otherwise lower pixel_error or coarsen less.")


@implements("TER-10")
def ter10(ctx, scope):
    tile = common.tile(ctx)
    worst, bad = 0.0, []

    def cmp(label, lo, hi, aabb):
        nonlocal worst
        d = max(np.abs(np.asarray(aabb["min"]) - lo).max(), np.abs(np.asarray(aabb["max"]) - hi).max())
        worst = max(worst, float(d))
        if d > AABB_TOL_M:
            bad.append(label)

    for c in tile["chunks"]:
        pos = np.concatenate([common.mesh(ctx, common.dist(ctx) / l["file"])[0] for l in c["lods"]]).astype(np.float64)
        cmp(c["id"], pos.min(axis=0), pos.max(axis=0), c["aabb"])
    for entry in tile["profiles"].values():
        for b in entry["batches"]:
            pos = common.mesh(ctx, common.dist(ctx) / b["file"])[0].astype(np.float64)
            cmp(b["file"], pos.min(axis=0), pos.max(axis=0), b["aabb"])
    return check_result("TER-10", scope, not bad, round(worst, 5), AABB_TOL_M, "m", "<=",
                        f"Rebuild the manifest. First: {bad[0]}." if bad else "")


@implements("TER-11")
def ter11(ctx, scope):
    n = lod_counts(0)[0]
    r = np.arange(n)
    pos = {cid: common.mesh(ctx, chunk_file(ctx, cid, 0))[0].view(np.uint32).reshape(-1, 3)
           for _, _, cid in chunk_ids()}
    bad = []
    for cx, cz, cid in chunk_ids():
        if cx < CHUNKS - 1:   # east edge of this chunk against the west edge of its neighbor
            if not np.array_equal(pos[cid][r * n + n - 1], pos[f"c{cx + 1}_{cz}"][r * n]):
                bad.append(f"{cid} east edge differs from c{cx + 1}_{cz}")
        if cz < CHUNKS - 1:   # south edge against the north edge below
            if not np.array_equal(pos[cid][(n - 1) * n + r], pos[f"c{cx}_{cz + 1}"][r]):
                bad.append(f"{cid} south edge differs from c{cx}_{cz + 1}")
    return common.violations("TER-11", scope, bad, "seams", "Neighbor chunks must share border node heights exactly (7.2).")
