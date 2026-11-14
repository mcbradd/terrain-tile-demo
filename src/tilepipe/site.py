"""Commands `site` and `serve` (SPEC 13.9). Stub from WP02; WP10 implements it. Signatures are frozen: see contracts.md."""
from pathlib import Path


def build(root: Path, aoi: str) -> None:
    raise NotImplementedError("site: WP10")


def serve(root: Path, port: int = 8000) -> None:
    raise NotImplementedError("serve: WP10")
