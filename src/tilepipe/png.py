"""PNG writer on zlib and struct only (SPEC 7.1). Stub from WP02; WP03 implements it. Signatures are frozen: see contracts.md."""
from pathlib import Path

import numpy as np


def write_png(path: Path, image: np.ndarray) -> None:
    raise NotImplementedError("png.write_png: WP03")
