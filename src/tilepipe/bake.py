"""Data textures: packed height and normal+AO with mips (SPEC 7.5). Linear data, never sRGB."""
import json
from pathlib import Path

import numpy as np

from tilepipe import config

PAD = 64  # apron cells around the 1024 tile (6.2); AO reach is 64 cells
_SIZES = (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64)
_DIRS = 16


def encode_height(h: np.ndarray, h_min: float, h_max: float) -> np.ndarray:
    """float heights (H, W) -> uint8 (H, W, 2): R = q >> 8, G = q & 255."""
    q = np.clip(np.rint((h.astype(np.float64) - h_min) / (h_max - h_min) * 65535), 0, 65535).astype(np.uint16)
    return np.stack([(q >> 8).astype(np.uint8), (q & 255).astype(np.uint8)], axis=-1)


def decode_height(rg: np.ndarray, h_min: float, h_max: float) -> np.ndarray:
    q = rg[..., 0].astype(np.float64) * 256 + rg[..., 1]
    return h_min + q / 65535 * (h_max - h_min)


def normals(h_full: np.ndarray) -> np.ndarray:
    """Unit normals (true scale) for the tile cells, float32 (n, n, 3) as (x, y, z)."""
    h = h_full.astype(np.float64)
    inner = (slice(PAD, -PAD), slice(PAD, -PAD))

    def at(dr, dc):
        n = h.shape[0] - 2 * PAD
        return h[PAD + dr:PAD + dr + n, PAD + dc:PAD + dc + n]

    dhdx = (at(0, 1) - at(0, -1)) / 20
    dhdz = (at(1, 0) - at(-1, 0)) / 20
    n = np.stack([-dhdx, np.ones_like(dhdx), -dhdz], axis=-1)
    return (n / np.linalg.norm(n, axis=-1, keepdims=True)).astype(np.float32)


def ao(h_full: np.ndarray) -> np.ndarray:
    """Horizon-based ambient occlusion for the tile cells, float32 in [0, 1]."""
    h = h_full.astype(np.float64)
    n = h.shape[0] - 2 * PAD
    center = h[PAD:PAD + n, PAD:PAD + n]
    total = np.zeros((n, n))
    for k in range(_DIRS):
        theta = 2 * np.pi * k / _DIRS
        t = np.zeros((n, n))
        for s in _SIZES:
            dc, dr = int(np.rint(s * np.cos(theta))), int(np.rint(s * np.sin(theta)))
            dist = 10 * np.sqrt(dc * dc + dr * dr)
            t = np.maximum(t, (h[PAD + dr:PAD + dr + n, PAD + dc:PAD + dc + n] - center) / dist)
        total += t / np.sqrt(1 + t * t)
    return (1 - total / _DIRS).astype(np.float32)


def _box(a: np.ndarray) -> np.ndarray:
    return (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2]) / 4


def nao_levels(h_full: np.ndarray) -> list[np.ndarray]:
    """Encoded RGBA8 levels, level 0 first, down to 1 by 1. Each level derives from the float data above it."""
    nrm = normals(h_full).astype(np.float64)
    occ = ao(h_full).astype(np.float64)
    levels = []
    while True:
        out = np.empty(occ.shape + (4,), np.uint8)
        out[..., 0] = np.rint((nrm[..., 0] * 0.5 + 0.5) * 255)
        out[..., 1] = np.rint((nrm[..., 2] * 0.5 + 0.5) * 255)
        out[..., 2] = np.rint(occ * 255)
        out[..., 3] = 255
        levels.append(out)
        if occ.shape[0] == 1:
            return levels
        nrm = np.stack([_box(nrm[..., i]) for i in range(3)], axis=-1)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        occ = _box(occ)


def run(root: Path, aoi: str) -> None:
    b, d = config.build_dir(root, aoi), config.dist_dir(root, aoi)
    try:
        h_full = np.load(b / "h_full.npy")
        geo = json.loads((b / "geo.json").read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise config.UsageError(f"bake needs prep output: {e.filename} not found (run prep first)") from e
    d.mkdir(parents=True, exist_ok=True)
    tile = h_full[PAD:-PAD, PAD:-PAD]
    (d / "terrain_height.rg8.bin").write_bytes(encode_height(tile, geo["h_min"], geo["h_max"]).tobytes())
    (d / "terrain_nao.rgba8.bin").write_bytes(b"".join(lv.tobytes() for lv in nao_levels(h_full)))
