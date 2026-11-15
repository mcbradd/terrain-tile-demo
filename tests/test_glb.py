"""T-GLB-ROUNDTRIP (SPEC 7.4): a mesh written by glb.py parses back bitwise identical and passes the Khronos validator."""
import json
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tilepipe import glb, lod

ROOT = Path(__file__).resolve().parents[1]


def khronos(path: Path) -> dict:
    """Run tools/validate_gltf.mjs (WP07) and return {"errors", "warnings"}."""
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is not on PATH; the Khronos validator cannot run")
    p = subprocess.run([node, str(ROOT / "tools" / "validate_gltf.mjs"), str(path)],
                       capture_output=True, text=True, cwd=ROOT)
    return json.loads(p.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("k,dtype", [(0, np.uint32), (4, np.uint16)])
def test_T_GLB_ROUNDTRIP(tmp_path, k, dtype):
    rng = np.random.default_rng(20261113)
    hn = (300 + rng.uniform(0, 50, (1025, 1025))).astype(np.float32)
    pos, idx = lod.chunk_mesh(hn, 1, 2, k, 3.7, 280.25)
    assert idx.dtype == dtype
    path = tmp_path / "m.glb"
    nbytes = glb.write_glb(path, pos, idx)
    data = path.read_bytes()
    assert nbytes == len(data) and len(data) % 4 == 0

    p2, i2 = glb.read_mesh(path)
    assert p2.dtype == np.float32 and i2.dtype == dtype
    assert p2.tobytes() == pos.tobytes() and i2.tobytes() == idx.tobytes()
    assert khronos(path) == {"errors": 0, "warnings": 0}

    doc, binary = glb.parse_glb(data)
    assert doc["asset"] == {"generator": "tilepipe 1.0.0", "version": "2.0"}
    assert doc["meshes"][0]["primitives"] == [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]
    assert doc["nodes"] == [{"mesh": 0}] and doc["scenes"] == [{"nodes": [0]}]
    acc = doc["accessors"]
    assert acc[0]["min"] == [float(v) for v in pos.min(axis=0)]
    assert acc[0]["max"] == [float(v) for v in pos.max(axis=0)]
    assert acc[1]["componentType"] == (5123 if dtype == np.uint16 else 5125)
    views = doc["bufferViews"]
    assert views[0]["byteOffset"] == 0 and views[0]["target"] == 34962
    assert views[1]["byteOffset"] % 4 == 0 and views[1]["target"] == 34963
    jlen = struct.unpack_from("<I", data, 12)[0]
    assert data[20:20 + jlen].rstrip(b" ") == json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    assert len(binary) % 4 == 0


def test_GLB_parse_rejects_garbage():
    with pytest.raises(ValueError):
        glb.parse_glb(b"glTF" + b"\0" * 30)
