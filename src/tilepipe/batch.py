"""Stage `batch` (SPEC 7.6, 8.3): per-profile LOD selection under the triangle budget, then draw batches.

Signatures frozen: see contracts.md.
"""
import json
import math
from pathlib import Path

import numpy as np

from tilepipe import config, glb
from tilepipe.config import RuleFailure
from tilepipe.lod import CHUNKS, LODS, chunk_ids, lod_counts

REPORT_EXAGGERATION = 3.0  # 8.3: the report also states the error in pixels at V = 3.0


def tau(profile: dict) -> float:
    """Vertical ground tolerance in meters that projects to `pixel_error` pixels at the nominal view (8.3)."""
    lod = profile["lod"]
    return (lod["view_distance_m"] * math.tan(lod["pixel_error"] / lod["ppd"] * math.pi / 180)
            * 8000 / lod["exaggeration"])


def error_px(e_m: float, profile: dict, exaggeration: float) -> float:
    """Inverse of `tau`: pixels subtended by a vertical error of e_m meters at exaggeration V (8.3)."""
    lod = profile["lod"]
    return math.degrees(math.atan(e_m * exaggeration / 8000 / lod["view_distance_m"])) * lod["ppd"]


def select(lod_stats: dict, tau_m: float, terrain_tris_max: int) -> dict:
    """LOD per chunk (7.6). Raises RuleFailure when even LOD 4 everywhere exceeds the budget."""
    tris = [lod_counts(k)[2] for k in range(LODS)]
    e = {cid: lod_stats["chunks"][cid]["e_max_m"] for _, _, cid in chunk_ids()}
    order = {cid: (cz, cx) for cx, cz, cid in chunk_ids()}
    sel = {cid: max(k for k in range(LODS) if em[k] <= tau_m) for cid, em in e.items()}
    total = sum(tris[k] for k in sel.values())
    while total > terrain_tris_max:
        open_ = [cid for cid, k in sel.items() if k < LODS - 1]
        if not open_:
            raise RuleFailure(f"terrain budget unreachable: {total} tris at LOD 4 everywhere "
                              f"> terrain_tris_max {terrain_tris_max}")
        cid = min(open_, key=lambda c: (e[c][sel[c] + 1], *order[c]))
        total += tris[sel[cid] + 1] - tris[sel[cid]]
        sel[cid] += 1
    e_star = max(e[cid][k] for cid, k in sel.items())
    return {"selection": sel, "e_star_m": e_star, "budget_forced": e_star > tau_m, "terrain_tris": total}


def batch_groups(mode: str) -> list[list[str]]:
    """Chunk ids per batch in (cz, cx) order, indexed by batch number b (7.6)."""
    groups: dict[int, list[str]] = {}
    for cx, cz, cid in chunk_ids():
        b = {"chunk": cz * CHUNKS + cx, "quadrant": cz // 2 * 2 + cx // 2, "tile": 0}[mode]
        groups.setdefault(b, []).append(cid)
    return [groups[b] for b in sorted(groups)]


def run(root: Path, aoi: str) -> None:
    """Stage batch: write `D/terrain_<profile>_b<nn>.glb` for every profile and `B/selection.json`."""
    b, d = config.build_dir(root, aoi), config.dist_dir(root, aoi)
    stats = json.loads((b / "lod_stats.json").read_text(encoding="utf-8"))
    out = {}
    for name, prof in config.load_profiles(root).items():
        t = tau(prof)
        s = select(stats, t, prof["budget"]["terrain_tris_max"])
        batches = []
        for nb, group in enumerate(batch_groups(prof["terrain"]["batch"])):
            pos, idx, base = [], [], 0
            for cid in group:
                p, i = glb.read_mesh(d / f"terrain_{cid}_lod{s['selection'][cid]}.glb")
                pos.append(p)
                idx.append(i.astype(np.uint32) + base)
                base += len(p)
            pos = np.concatenate(pos)
            itype = "uint16" if base <= 65535 else "uint32"
            idx = np.concatenate(idx).astype(itype)
            fname = f"terrain_{name}_b{nb:02d}.glb"
            nbytes = glb.write_glb(d / fname, pos, idx)
            batches.append({
                "file": fname, "chunks": group, "vertices": int(base), "tris": int(idx.size // 3),
                "index_type": itype, "bytes": nbytes,
                "aabb": {"min": [float(v) for v in pos.min(axis=0)], "max": [float(v) for v in pos.max(axis=0)]}})
        out[name] = {
            "tau_target_m": t, "e_star_m": s["e_star_m"], "budget_forced": s["budget_forced"],
            "error_px_nominal": error_px(s["e_star_m"], prof, prof["lod"]["exaggeration"]),
            "error_px_v3": error_px(s["e_star_m"], prof, REPORT_EXAGGERATION),
            "selection": s["selection"], "terrain_tris": s["terrain_tris"], "terrain_draws": len(batches),
            "batches": batches}
    config.write_json(b / "selection.json", out)
