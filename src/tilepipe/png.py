"""PNG writer on zlib and struct only (SPEC 7.1): 8-bit, filter type 0, zlib level 9."""
import struct
import zlib
from pathlib import Path

import numpy as np


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def write_png(path: Path, image: np.ndarray) -> None:
    """`image` is uint8, HxW (gray), HxWx3 (RGB) or HxWx4 (RGBA)."""
    if image.dtype != np.uint8:
        raise ValueError(f"write_png needs uint8, got {image.dtype}")
    if image.ndim == 3 and image.shape[2] in (3, 4):
        color_type = 2 if image.shape[2] == 3 else 6
    elif image.ndim == 2:
        color_type = 0
    else:
        raise ValueError(f"write_png needs HxW, HxWx3 or HxWx4, got shape {image.shape}")
    h, w = image.shape[:2]
    rows = np.ascontiguousarray(image).reshape(h, -1)
    raw = np.concatenate([np.zeros((h, 1), np.uint8), rows], axis=1).tobytes()  # filter type 0 per row
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(raw, 9))
           + _chunk(b"IEND", b""))
    Path(path).write_bytes(png)
