"""Runs every rule; writes validation.json, validation.junit.xml, and the report (SPEC 12.2). Stub from WP02; WP07 implements it. Signatures are frozen: see contracts.md."""
from pathlib import Path


def run(root: Path, aoi: str, skip_entities: bool = False, determinism: bool = False) -> int:
    raise NotImplementedError("validate: WP07")
