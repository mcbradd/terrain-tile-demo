"""Shared loaders and math for the core rule modules (SPEC 12). Everything is cached on `ctx.cache`.

A missing input raises FileNotFoundError; the runner turns that into a FAIL record with a build hint.
"""
import json
from pathlib import Path

import numpy as np

from tilepipe import config, glb
from tilepipe.validate.registry import Context, check_result

TILE_M = 10240.0
CHUNKS, CHUNK_CELLS, LODS = 4, 256, 5          # SPEC 7.2
BUILD_HINT = "Run `uv run tilepipe build`."
_COMP = {5120: "i1", 5121: "u1", 5122: "i2", 5123: "u2", 5125: "u4", 5126: "f4"}
_WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def lod_counts(k: int) -> tuple[int, int, int]:
    """(nodes per side, vertices, total triangles) of one chunk at LOD k, from the table of 7.2."""
    q = CHUNK_CELLS >> k
    n = q + 1
    return n, n * n + 4 * n, 2 * q * q + 8 * q


def chunk_ids() -> list[tuple[int, int, str]]:
    return [(cx, cz, f"c{cx}_{cz}") for cz in range(CHUNKS) for cx in range(CHUNKS)]


def memo(ctx: Context, key: str, fn):
    if key not in ctx.cache:
        ctx.cache[key] = fn()
    return ctx.cache[key]


def rel(ctx: Context, path: Path) -> str:
    try:
        return Path(path).relative_to(ctx.root).as_posix()
    except ValueError:
        return Path(path).name


def jload(ctx: Context, path: Path):
    return memo(ctx, f"json:{path}", lambda: json.loads(Path(path).read_text(encoding="utf-8")))


def dist(ctx: Context) -> Path:
    return config.dist_dir(ctx.root, ctx.aoi)


def build(ctx: Context) -> Path:
    return config.build_dir(ctx.root, ctx.aoi)


def tile(ctx: Context) -> dict:
    return jload(ctx, dist(ctx) / "tile.json")


def geo_json(ctx: Context) -> dict:
    return jload(ctx, build(ctx) / "geo.json")


def lod_stats(ctx: Context) -> dict:
    return jload(ctx, build(ctx) / "lod_stats.json")


def h_full(ctx: Context) -> np.ndarray:
    return memo(ctx, "h_full", lambda: np.load(build(ctx) / "h_full.npy"))


def scene_doc(ctx: Context) -> dict:
    return jload(ctx, ctx.root / "scene" / f"{ctx.aoi}_scene.json")


# ---------------------------------------------------------------- GLB reading (own accessor reader, honors byteStride)

def glb_parts(ctx: Context, path: Path) -> tuple[dict, bytes]:
    return memo(ctx, f"glb:{path}", lambda: glb.parse_glb(Path(path).read_bytes()))


def accessor(doc: dict, binary: bytes, i: int) -> np.ndarray:
    a = doc["accessors"][i]
    w = _WIDTH[a["type"]]
    dt = np.dtype("<" + _COMP[a["componentType"]])
    view = doc["bufferViews"][a["bufferView"]]
    start = view.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = view.get("byteStride", 0) or w * dt.itemsize
    if stride == w * dt.itemsize:
        arr = np.frombuffer(binary, dtype=dt, count=a["count"] * w, offset=start)
    else:
        raw = np.frombuffer(binary, dtype=np.uint8, count=stride * (a["count"] - 1) + w * dt.itemsize, offset=start)
        arr = np.ndarray((a["count"], w), dtype=dt, buffer=raw, strides=(stride, dt.itemsize)).ravel()
    return arr.reshape(-1, w) if w > 1 else arr.copy()


def mesh(ctx: Context, path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """(positions (N, 3) float32, indices (3M,) as stored, glTF JSON) of the first primitive of a GLB."""
    def load():
        doc, binary = glb_parts(ctx, path)
        prim = doc["meshes"][0]["primitives"][0]
        pos = accessor(doc, binary, prim["attributes"]["POSITION"]).astype(np.float32)
        idx = accessor(doc, binary, prim["indices"]) if "indices" in prim else np.arange(len(pos))
        return pos, idx, doc
    return memo(ctx, f"mesh:{path}", load)


def index_component(doc: dict) -> int:
    return doc["accessors"][doc["meshes"][0]["primitives"][0]["indices"]]["componentType"]


def terrain_glbs(ctx: Context) -> list[Path]:
    return sorted(dist(ctx).glob("terrain_*.glb"))


# ---------------------------------------------------------------- textures and sampling

def height_texture(ctx: Context) -> np.ndarray:
    """Decoded level 0 of terrain_height.rg8.bin as float64 (1024, 1024), per the channel formula of 9.1."""
    def load():
        raw = np.frombuffer((dist(ctx) / "terrain_height.rg8.bin").read_bytes(), dtype=np.uint8)[:1024 * 1024 * 2]
        rg = raw.reshape(1024, 1024, 2).astype(np.float64)
        h = tile(ctx)["height"]
        return h["min"] + (rg[..., 0] * 256 + rg[..., 1]) / 65535 * (h["max"] - h["min"])
    return memo(ctx, "height_tex", load)


def bilinear(grid: np.ndarray, fx: np.ndarray, fy: np.ndarray) -> np.ndarray:
    """Bilinear sample of grid[row, col] at fractional (col, row) = (fx, fy), clamped to the grid."""
    h, w = grid.shape
    fx, fy = np.clip(fx, 0, w - 1), np.clip(fy, 0, h - 1)
    x0, y0 = np.minimum(fx.astype(int), w - 2), np.minimum(fy.astype(int), h - 2)
    u, v = fx - x0, fy - y0
    g = grid.astype(np.float64)
    return (g[y0, x0] * (1 - u) * (1 - v) + g[y0, x0 + 1] * u * (1 - v)
            + g[y0 + 1, x0] * (1 - u) * v + g[y0 + 1, x0 + 1] * u * v)


def violations(rule_id: str, scope: str, bad: list[str], unit: str, fix: str):
    """A count-of-violations result: PASS when `bad` is empty, otherwise the first offender goes in the hint."""
    return check_result(rule_id, scope, not bad, len(bad), 0, unit, "<=", f"{fix} First: {bad[0]}." if bad else "")


def entity_ids(ctx: Context) -> list[str]:
    return list(tile(ctx)["entities"])


def entity_dir(ctx: Context, ent: str) -> Path:
    return ctx.root / "dist" / "entities" / ent


def multi(rule_id: str, scope: str, checks: list[tuple], fix: str):
    """One result from several limits, each `(unit, measured, limit, op)` with op `<=`, `>=` or `==`.

    The first failing check is reported; if all pass, the tightest one is."""
    def ok(m, lim, op):
        return {"<=": m <= lim, ">=": m >= lim, "==": m == lim}[op]

    def tight(c):
        _, m, lim, op = c
        if op == "==":
            return 0.0
        return (m / lim if lim else 0.0) if op == "<=" else (lim / m if m else float("inf"))
    failed = [c for c in checks if not ok(c[1], c[2], c[3])]
    unit, m, lim, op = failed[0] if failed else max(checks, key=tight)
    return check_result(rule_id, scope, not failed, m, lim, unit, op, fix)
