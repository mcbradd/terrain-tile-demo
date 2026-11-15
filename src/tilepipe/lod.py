"""Stages `lod` and `export` (SPEC 7.2, 7.3): mesh nodes, LOD error metric, skirt depths, chunk GLBs.

Signatures of `run` and `export` frozen: see contracts.md.
"""
import json
import math
from pathlib import Path

import numpy as np

from tilepipe import config, glb

CHUNKS = 4            # chunks per side (7.2)
CHUNK_CELLS = 256     # node intervals per chunk side at LOD 0
LODS = 5              # k = 0..4, step s = 2^k
BORDER_DROP_M = 100.0  # tile-border skirt bottom sits at h_min - 100.0 (7.3)


def chunk_ids() -> list[tuple[int, int, str]]:
    """(cx, cz, id) for every chunk in (cz, cx) order."""
    return [(cx, cz, f"c{cx}_{cz}") for cz in range(CHUNKS) for cx in range(CHUNKS)]


def lod_counts(k: int) -> tuple[int, int, int]:
    """(nodes per side, vertices, total tris) of one chunk at LOD k (table of 7.2)."""
    q = CHUNK_CELLS >> k
    n = q + 1
    return n, n * n + 4 * n, 2 * q * q + 8 * q


def h_node(h_full: np.ndarray) -> np.ndarray:
    """float32 [1025, 1025], indexed [j, i]: mean of the four cells around each node (6.3)."""
    h = np.asarray(h_full, dtype=np.float64)
    m = CHUNKS * CHUNK_CELLS + 1
    s = h[63:63 + m, 63:63 + m] + h[63:63 + m, 64:64 + m] + h[64:64 + m, 63:63 + m] + h[64:64 + m, 64:64 + m]
    return (s / 4.0).astype(np.float32)


def chunk_nodes(hn: np.ndarray, cx: int, cz: int) -> np.ndarray:
    """The (257, 257) node block owned by chunk (cx, cz), indexed [j, i]. Neighbors share border nodes."""
    i0, j0 = CHUNK_CELLS * cx, CHUNK_CELLS * cz
    return hn[j0:j0 + CHUNK_CELLS + 1, i0:i0 + CHUNK_CELLS + 1]


def lod_error(h: np.ndarray, s: int) -> tuple[float, float]:
    """(e_max, e_rms) of the step-s mesh of a square node block `h` [j, i] against every node (7.2 step 4).

    Works on any block whose side minus one is a multiple of s; a chunk block is 257 by 257.
    """
    h = np.asarray(h, dtype=np.float64)
    last = h.shape[0] - 1
    loc = np.arange(last + 1)
    o = np.minimum(loc // s * s, last - s)
    w = (loc - o) / s
    J0, I0 = o[:, None], o[None, :]
    v, u = w[:, None], w[None, :]
    ha, hb = h[J0, I0], h[J0, I0 + s]
    hc, hd = h[J0 + s, I0], h[J0 + s, I0 + s]
    hp = np.where(u + v <= 1, ha + u * (hb - ha) + v * (hc - ha), hd + (1 - u) * (hc - hd) + (1 - v) * (hb - hd))
    e = np.abs(hp - h)
    return float(e.max()), float(np.sqrt(np.mean(e * e)))


def skirt_depths(e_max_by_chunk: list[list[float]]) -> list[float]:
    """D_k = ceil((2 * max over chunks of e_max(chunk, k) + 1.0) * 10) / 10 (7.2 step 5)."""
    return [math.ceil((2 * max(e[k] for e in e_max_by_chunk) + 1.0) * 10) / 10 for k in range(LODS)]


def run(root: Path, aoi: str) -> None:
    """Stage lod: write B/lod_stats.json."""
    b = config.build_dir(root, aoi)
    hn = h_node(np.load(b / "h_full.npy"))
    chunks = {}
    for cx, cz, cid in chunk_ids():
        h = chunk_nodes(hn, cx, cz)
        stats = [(0.0, 0.0)] + [lod_error(h, 1 << k) for k in range(1, LODS)]
        chunks[cid] = {"e_max_m": [e for e, _ in stats], "e_rms_m": [r for _, r in stats]}
    config.write_json(b / "lod_stats.json", {
        "chunks": chunks, "skirt_depth_m": skirt_depths([c["e_max_m"] for c in chunks.values()])})


def edge_vertices(n: int) -> list[np.ndarray]:
    """Surface vertex indices along edges N, E, S, W, traversed clockwise seen from above (7.3)."""
    r = np.arange(n)
    return [r, r * n + n - 1, (n - 1) * n + r[::-1], r[::-1] * n]


def chunk_mesh(hn: np.ndarray, cx: int, cz: int, k: int, depth_m: float, h_min: float
               ) -> tuple[np.ndarray, np.ndarray]:
    """(positions float32 (V, 3), indices uint16|uint32) of chunk (cx, cz) at LOD k, per 7.3 and 6.4."""
    s = 1 << k
    n, nverts, _ = lod_counts(k)
    nodes = np.arange(0, CHUNK_CELLS + 1, s)
    gi = CHUNK_CELLS * cx + nodes                      # global node i, west to east
    gj = CHUNK_CELLS * cz + nodes                      # global node j, north to south
    surf = np.empty((n, n, 3), dtype=np.float32)
    surf[..., 0] = (10 * gi)[None, :]
    surf[..., 1] = hn[np.ix_(gj, gi)]
    surf[..., 2] = (10 * gj)[:, None]
    surf = surf.reshape(-1, 3)

    border = [cz == 0, cx == CHUNKS - 1, cz == CHUNKS - 1, cx == 0]   # N, E, S, W on the tile edge
    edges = edge_vertices(n)
    skirt = []
    for e, top in enumerate(edges):
        p = surf[top].copy()
        p[:, 1] = np.float32(h_min - BORDER_DROP_M) if border[e] else p[:, 1] - np.float32(depth_m)
        skirt.append(p)
    pos = np.concatenate([surf, *skirt])

    # Surface quads row-major, j outer, i inner: (a, c, b) then (b, c, d) (6.4).
    a = (np.arange(n - 1)[:, None] * n + np.arange(n - 1)[None, :]).ravel()
    b_, c, d = a + 1, a + n, a + n + 1
    tris = [np.stack([a, c, b_, b_, c, d], axis=1).reshape(-1, 3)]
    # Skirt strips, edges N, E, S, W: (top_t, top_t+1, bot_t) then (top_t+1, bot_t+1, bot_t).
    t = np.arange(n - 1)
    for e, top in enumerate(edges):
        bot = n * n + e * n + t
        tris.append(np.stack([top[t], top[t + 1], bot, top[t + 1], bot + 1, bot], axis=1).reshape(-1, 3))
    idx = np.concatenate(tris).ravel()
    assert len(pos) == nverts
    return pos, idx.astype(np.uint16 if nverts <= 65535 else np.uint32)


def export(root: Path, aoi: str) -> None:
    """Stage export: write the 80 chunk LOD GLBs `D/terrain_<chunk>_lod<k>.glb`."""
    b, d = config.build_dir(root, aoi), config.dist_dir(root, aoi)
    hn = h_node(np.load(b / "h_full.npy"))
    h_min = float(json.loads((b / "geo.json").read_text(encoding="utf-8"))["h_min"])
    depths = json.loads((b / "lod_stats.json").read_text(encoding="utf-8"))["skirt_depth_m"]
    d.mkdir(parents=True, exist_ok=True)
    for cx, cz, cid in chunk_ids():
        for k in range(LODS):
            pos, idx = chunk_mesh(hn, cx, cz, k, depths[k], h_min)
            glb.write_glb(d / f"terrain_{cid}_lod{k}.glb", pos, idx)
