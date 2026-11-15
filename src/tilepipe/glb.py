"""Hand-written GLB writer and reader (SPEC 7.4). No third-party glTF library.

Signatures frozen: see contracts.md.
"""
import json
import struct
from pathlib import Path

import numpy as np

_MAGIC, _JSON, _BIN = 0x46546C67, 0x4E4F534A, 0x004E4942
_COMPONENT = {np.dtype("<u2"): 5123, np.dtype("<u4"): 5125}
_DTYPE = {5123: "<u2", 5125: "<u4", 5126: "<f4"}


def _pad(b: bytes, fill: bytes) -> bytes:
    return b + fill * (-len(b) % 4)


def write_glb(path: Path, positions: np.ndarray, indices: np.ndarray) -> int:
    """Write one terrain GLB with exactly the structure of 7.4. Returns the number of bytes written."""
    pos = np.ascontiguousarray(positions, dtype="<f4")
    if pos.ndim != 2 or pos.shape[1] != 3:
        raise ValueError(f"positions must be (N, 3), got {pos.shape}")
    idx = np.ascontiguousarray(indices)
    idx = idx.astype(idx.dtype.newbyteorder("<"), copy=False)
    if idx.dtype not in _COMPONENT or idx.ndim != 1 or idx.size % 3:
        raise ValueError(f"indices must be uint16 or uint32 of shape (3M,), got {idx.dtype} {idx.shape}")
    pos_b, idx_b = pos.tobytes(), idx.tobytes()
    idx_off = len(pos_b)  # 12 * N, already on a 4-byte boundary
    doc = {
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3",
             # Exact doubles of the float32 bounds: the one exception to the rounding of 6.7.
             "min": [float(v) for v in pos.min(axis=0)], "max": [float(v) for v in pos.max(axis=0)]},
            {"bufferView": 1, "componentType": _COMPONENT[idx.dtype], "count": idx.size, "type": "SCALAR"},
        ],
        "asset": {"generator": "tilepipe 1.0.0", "version": "2.0"},
        "bufferViews": [
            {"buffer": 0, "byteLength": len(pos_b), "byteOffset": 0, "target": 34962},
            {"buffer": 0, "byteLength": len(idx_b), "byteOffset": idx_off, "target": 34963},
        ],
        "buffers": [{"byteLength": idx_off + len(idx_b)}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "nodes": [{"mesh": 0}],
        "scene": 0,
        "scenes": [{"nodes": [0]}],
    }
    j = _pad(json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"), b" ")
    b = _pad(pos_b + idx_b, b"\0")
    total = 12 + 8 + len(j) + 8 + len(b)
    data = (struct.pack("<III", _MAGIC, 2, total) + struct.pack("<II", len(j), _JSON) + j
            + struct.pack("<II", len(b), _BIN) + b)
    Path(path).write_bytes(data)
    return total


def parse_glb(data: bytes) -> tuple[dict, bytes]:
    """(JSON chunk, BIN chunk) of any GLB 2.0. BIN is b"" when absent."""
    if len(data) < 20:
        raise ValueError("not a GLB: too short")
    magic, version, length = struct.unpack_from("<III", data, 0)
    if magic != _MAGIC or version != 2 or length != len(data):
        raise ValueError(f"not a GLB 2.0: magic {magic:#x}, version {version}, length {length} of {len(data)}")
    jlen, jtype = struct.unpack_from("<II", data, 12)
    if jtype != _JSON:
        raise ValueError("first GLB chunk is not JSON")
    doc = json.loads(data[20:20 + jlen].decode("utf-8"))
    off, binary = 20 + jlen, b""
    if off + 8 <= len(data):
        blen, btype = struct.unpack_from("<II", data, off)
        if btype == _BIN:
            binary = data[off + 8:off + 8 + blen]
    return doc, binary


def _accessor(doc: dict, binary: bytes, a: int) -> np.ndarray:
    acc = doc["accessors"][a]
    view = doc["bufferViews"][acc["bufferView"]]
    width = {"SCALAR": 1, "VEC3": 3}[acc["type"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    arr = np.frombuffer(binary, dtype=_DTYPE[acc["componentType"]], count=acc["count"] * width, offset=start)
    return arr.reshape(-1, 3).copy() if width == 3 else arr.copy()


def read_mesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """(positions float32 (N, 3), indices uint16|uint32 (3M,)) of a terrain GLB."""
    doc, binary = parse_glb(Path(path).read_bytes())
    prim = doc["meshes"][0]["primitives"][0]
    return _accessor(doc, binary, prim["attributes"]["POSITION"]), _accessor(doc, binary, prim["indices"])
