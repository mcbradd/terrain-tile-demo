"""Hand-written GLB writer and reader (SPEC 7.4). Stub from WP02; WP04 implements it. Signatures are frozen: see contracts.md."""
from pathlib import Path

import numpy as np


def write_glb(path: Path, positions: np.ndarray, indices: np.ndarray) -> int:
    raise NotImplementedError("glb.write_glb: WP04")


def parse_glb(data: bytes) -> tuple[dict, bytes]:
    raise NotImplementedError("glb.parse_glb: WP04")


def read_mesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    raise NotImplementedError("glb.read_mesh: WP04")
