"""SHA-256 helpers and outputs.sha256 (SPEC 7.8)."""
import hashlib
from pathlib import Path

NAME = "outputs.sha256"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_outputs_sha256(dist: Path) -> None:
    """One line `<hex>  <posix path>` per file under `dist`, except the list itself, sorted by path."""
    files = sorted((p for p in dist.rglob("*") if p.is_file() and p.relative_to(dist).as_posix() != NAME),
                   key=lambda p: p.relative_to(dist).as_posix())
    text = "".join(f"{sha256_file(p)}  {p.relative_to(dist).as_posix()}\n" for p in files)
    (dist / NAME).write_bytes(text.encode("utf-8"))
