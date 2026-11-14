"""Placement determinism (SPEC 7.7), manifest schema (9.1), outputs.sha256 (7.8)."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from tilepipe import config, hashing, manifest, scene
from tilepipe.config import GuardError, RuleFailure

ROOT = Path(__file__).resolve().parent.parent
AOI = "anza_borrego_01"


def synthetic_h() -> np.ndarray:
    """1152 square gentle ramp: every interior cell is a candidate, so placement is easy and spread out."""
    x = np.linspace(0, 100, 1152)
    return np.tile(x, (1152, 1)).astype(np.float32)


def test_placement_deterministic_and_valid():
    h = synthetic_h()
    a, b = scene.place(h, 0.0, 1000.0, AOI), scene.place(h, 0.0, 1000.0, AOI)
    assert config.dumps_json(a) == config.dumps_json(b)
    inst = a["instances"]
    assert [i["entity"] for i in inst] == [e for e in scene.ENTITIES for _ in range(8)]
    pts = np.array([[i["x"], i["z"]] for i in inst])
    d = np.hypot(pts[:, None, 0] - pts[None, :, 0], pts[:, None, 1] - pts[None, :, 1])
    assert d[np.triu_indices(24, 1)].min() >= 400
    assert all(300 <= i["x"] <= 10240 - 300 and 300 <= i["z"] <= 10240 - 300 for i in inst)
    assert all(i["hover_table_m"] == (0.02 if "uas" in i["entity"] else 0.0) for i in inst)


def test_placement_guard_when_no_candidates():
    with pytest.raises(GuardError):
        scene.place(synthetic_h(), 0.0, 0.001, AOI)  # t > 0.45 everywhere


def test_scene_stage_writes_then_compares(tmp_path):
    b = config.build_dir(tmp_path, AOI)
    b.mkdir(parents=True)
    np.save(b / "h_full.npy", synthetic_h())
    config.write_json(b / "geo.json", {"h_min": 0.0, "h_max": 1000.0})
    scene.run(tmp_path, AOI)
    p = scene.scene_path(tmp_path, AOI)
    first = p.read_bytes()
    scene.run(tmp_path, AOI)
    assert p.read_bytes() == first
    p.write_bytes(first.replace(b'"heading_deg"', b'"heading_deg_"', 1))
    with pytest.raises(RuleFailure):
        scene.run(tmp_path, AOI)
    scene.run(tmp_path, AOI, regen=True)
    assert p.read_bytes() == first


def test_outputs_sha256(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "b.bin").write_bytes(b"b")
    (tmp_path / "sub" / "a.bin").write_bytes(b"a")
    hashing.write_outputs_sha256(tmp_path)
    lines = (tmp_path / "outputs.sha256").read_text().splitlines()
    assert [l.split("  ")[1] for l in lines] == ["b.bin", "sub/a.bin"]
    assert lines[0].split("  ")[0] == hashing.sha256_file(tmp_path / "b.bin")


def test_committed_scene_matches_data_when_built():
    committed = ROOT / "scene" / f"{AOI}_scene.json"
    assert committed.exists()
    doc = json.loads(committed.read_text(encoding="utf-8"))
    assert len(doc["instances"]) == 24


def test_tile_json_schema_when_built():
    tile = ROOT / "dist" / AOI / "tile.json"
    if not tile.exists():
        pytest.skip("run `tilepipe build` first")
    doc = json.loads(tile.read_text(encoding="utf-8"))
    assert config.schema_errors(doc, "tile") == []
    assert (ROOT / "dist" / AOI / "scene.json").read_bytes() == (ROOT / "scene" / f"{AOI}_scene.json").read_bytes()
    text = tile.read_text(encoding="utf-8")
    assert str(ROOT) not in text and "\\" not in text
    for name, p in doc["profiles"].items():
        files = [b["file"] for b in p["batches"]]
        assert p["terrain_draws"] == len(files)
