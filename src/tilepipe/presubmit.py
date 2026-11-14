"""Commands `presubmit` and `profile set-share` (SPEC 4.2, 18 D1). Stub from WP02; WP12 implements it. Signatures are frozen: see contracts.md."""
from pathlib import Path


def run(root: Path, files: list[Path]) -> int:
    raise NotImplementedError("presubmit: WP12")


def set_share(root: Path, profile: str, share: float) -> None:
    raise NotImplementedError("profile set-share: WP12")
