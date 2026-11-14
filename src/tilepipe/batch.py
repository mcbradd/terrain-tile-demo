"""Stage `batch` (SPEC 7.6, 8.3). Stub from WP02; WP04 implements it. Signatures are frozen: see contracts.md."""
from pathlib import Path


def tau(profile: dict) -> float:
    raise NotImplementedError("batch.tau: WP04")


def error_px(e_m: float, profile: dict, exaggeration: float) -> float:
    raise NotImplementedError("batch.error_px: WP04")


def select(lod_stats: dict, tau_m: float, terrain_tris_max: int) -> dict:
    raise NotImplementedError("batch.select: WP04")


def run(root: Path, aoi: str) -> None:
    raise NotImplementedError("batch: WP04")
