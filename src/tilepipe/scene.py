"""Stage `scene` (SPEC 7.7): deterministic demo entity placement, committed at scene/<aoi>_scene.json."""
import json
from pathlib import Path

import numpy as np

from tilepipe import bake, config
from tilepipe.config import GuardError, RuleFailure

ENTITIES = ("ent_vehicle_wheeled_a", "ent_mast_comms_a", "ent_uas_quad_a")  # order of 7.7 step 2
PER_ENTITY, MIN_SPACING_M, MAX_DRAWS, EDGE_CELLS = 8, 400.0, 10_000, 30
MAX_SLOPE_DEG, MAX_T, SEED, UAS_HOVER_M = 8.0, 0.45, 20261113, 0.020


def scene_path(root: Path, aoi: str) -> Path:
    return root / "scene" / f"{aoi}_scene.json"


def candidates(h_full: np.ndarray, h_min: float, h_max: float) -> np.ndarray:
    """(N, 2) int array of tile cells (r, c), row-major, that pass the 7.7 step 1 tests."""
    ny = bake.normals(h_full)[..., 1].astype(np.float64)
    h = h_full[bake.PAD:-bake.PAD, bake.PAD:-bake.PAD].astype(np.float64)
    ok = (np.degrees(np.arccos(np.clip(ny, -1, 1))) <= MAX_SLOPE_DEG) & ((h - h_min) / (h_max - h_min) <= MAX_T)
    n = ok.shape[0]
    inner = np.zeros_like(ok)
    inner[EDGE_CELLS:n - EDGE_CELLS, EDGE_CELLS:n - EDGE_CELLS] = True
    return np.argwhere(ok & inner)


def place(h_full: np.ndarray, h_min: float, h_max: float, aoi: str) -> dict:
    cand = candidates(h_full, h_min, h_max)
    if len(cand) == 0:
        raise GuardError("SCN-PLACE candidates", 0, ">= 1")
    rng = np.random.default_rng(SEED)
    xz = np.stack([10.0 * cand[:, 1] + 5, 10.0 * cand[:, 0] + 5], axis=1)
    accepted: list[np.ndarray] = []
    out, draws = [], 0
    for ent in ENTITIES:
        placed = 0
        while placed < PER_ENTITY:
            if draws >= MAX_DRAWS:
                raise GuardError("SCN-PLACE draws", f"{len(out)} placed", f"{PER_ENTITY * len(ENTITIES)} placed")
            draws += 1
            i = int(rng.integers(0, len(cand)))
            if accepted and np.min(np.hypot(*(np.array(accepted) - xz[i]).T)) < MIN_SPACING_M:
                continue
            accepted.append(xz[i])
            out.append({"entity": ent, "cell": [int(cand[i, 0]), int(cand[i, 1])], "x": float(xz[i, 0]),
                        "z": float(xz[i, 1]), "heading_deg": int(rng.integers(0, 360)),
                        "hover_table_m": UAS_HOVER_M if "_uas_" in ent else 0.0})
            placed += 1
    return {"schema": 1, "aoi": aoi, "instances": out}


def run(root: Path, aoi: str, regen: bool = False) -> None:
    b = config.build_dir(root, aoi)
    try:
        h_full = np.load(b / "h_full.npy")
        geo = json.loads((b / "geo.json").read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise config.UsageError(f"scene needs prep output: {e.filename} not found (run prep first)") from e
    data = config.dumps_json(place(h_full, geo["h_min"], geo["h_max"], aoi)).encode("utf-8")
    path = scene_path(root, aoi)
    if regen or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    elif path.read_bytes() != data:
        raise RuleFailure(f"{path.name} differs from the regenerated placement; "
                          "run `tilepipe scene --regen` if the change is intended")
