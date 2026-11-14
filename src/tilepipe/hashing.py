"""SHA-256 helpers and outputs.sha256 (SPEC 7.8). Stub from WP02; WP06 implements it. Signatures are frozen: see contracts.md."""
from pathlib import Path


def sha256_file(path: Path) -> str:
    raise NotImplementedError("hashing.sha256_file: WP06")


def write_outputs_sha256(dist: Path) -> None:
    raise NotImplementedError("hashing.write_outputs_sha256: WP06")
