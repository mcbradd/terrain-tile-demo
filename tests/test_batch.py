"""T-SELECT (SPEC 7.6) and the tolerance of 8.3, on synthetic lod_stats."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from test_lod import AOI, hills, stage_root
from tilepipe import batch, config, glb, lod
from tilepipe.config import RuleFailure

TRIS = [133120, 33792, 8704, 2304, 640]
CIDS = [cid for _, _, cid in lod.chunk_ids()]


def stats(e_by_chunk: dict) -> dict:
    flat = [0.0, 1.0, 2.0, 3.0, 4.0]
    return {"chunks": {c: {"e_max_m": e_by_chunk.get(c, flat), "e_rms_m": [0.0] * 5} for c in CIDS},
            "skirt_depth_m": [1.0] * 5}


def profile(ppd, px):
    return {"lod": {"ppd": ppd, "pixel_error": px, "view_distance_m": 0.75, "exaggeration": 1.5}}


def test_SELECT_tau_8_3():
    assert batch.tau(profile(30.0, 2.0)) == pytest.approx(4.654, abs=5e-4)
    assert batch.tau(profile(25.0, 1.0)) == pytest.approx(2.793, abs=5e-4)
    p = profile(30.0, 2.0)
    assert batch.error_px(batch.tau(p), p, 1.5) == pytest.approx(2.0, rel=1e-12)
    assert batch.error_px(1.0, p, 3.0) == pytest.approx(2 * batch.error_px(1.0, p, 1.5), rel=1e-6)


def test_T_SELECT_tolerance_only():
    s = batch.select(stats({"c2_1": [0.0, 0.5, 2.5, 3.0, 9.0]}), 2.6, 10**9)
    assert s["selection"]["c2_1"] == 2
    assert all(s["selection"][c] == 2 for c in CIDS)
    assert s["terrain_tris"] == 16 * TRIS[2]
    assert s["e_star_m"] == 2.5 and s["budget_forced"] is False


def test_T_SELECT_budget_forced_with_tie():
    # Everything fits tau at LOD 0 only. LOD 1 errors: c1_0 and c0_1 tie at 0.3, c3_3 is cheapest.
    e = {c: [0.0, 5.0, 6.0, 7.0, 8.0] for c in CIDS}
    e["c3_3"] = [0.0, 0.1, 6.0, 7.0, 8.0]
    e["c1_0"] = [0.0, 0.3, 6.0, 7.0, 8.0]
    e["c0_1"] = [0.0, 0.3, 6.0, 7.0, 8.0]
    # Budget allows exactly three chunks to drop to LOD 1.
    budget = 13 * TRIS[0] + 3 * TRIS[1]
    s = batch.select(stats(e), 0.05, budget)
    lod1 = sorted(c for c, k in s["selection"].items() if k == 1)
    assert lod1 == ["c0_1", "c1_0", "c3_3"]
    assert s["terrain_tris"] == budget and s["e_star_m"] == 0.3 and s["budget_forced"] is True
    # One step less budget room: tie broken by lower cz first, so c1_0 (cz 0) goes before c0_1 (cz 1).
    s = batch.select(stats(e), 0.05, budget + TRIS[0] - TRIS[1])
    assert sorted(c for c, k in s["selection"].items() if k == 1) == ["c1_0", "c3_3"]


def test_SELECT_tie_on_cx():
    e = {c: [0.0, 5.0, 6.0, 7.0, 8.0] for c in CIDS}
    e["c2_0"] = [0.0, 0.3, 6.0, 7.0, 8.0]
    e["c1_0"] = [0.0, 0.3, 6.0, 7.0, 8.0]
    s = batch.select(stats(e), 0.05, 15 * TRIS[0] + TRIS[1])
    assert [c for c, k in s["selection"].items() if k == 1] == ["c1_0"]


def test_SELECT_unreachable():
    with pytest.raises(RuleFailure):
        batch.select(stats({}), 100.0, 16 * TRIS[4] - 1)
    assert batch.select(stats({}), 100.0, 16 * TRIS[4])["terrain_tris"] == 16 * TRIS[4]


def test_SELECT_batch_groups():
    assert [len(g) for g in batch.batch_groups("chunk")] == [1] * 16
    assert batch.batch_groups("chunk")[6] == ["c2_1"]
    q = batch.batch_groups("quadrant")
    assert q[1] == ["c2_0", "c3_0", "c2_1", "c3_1"] and len(q) == 4
    assert batch.batch_groups("tile") == [CIDS]


def test_SELECT_batch_run(tmp_path):
    """batch.run on exported synthetic chunks: one GLB per batch, merged in (cz, cx) order with offset indices."""
    shutil.copytree(Path(__file__).resolve().parents[1] / "profiles", tmp_path / "profiles")
    b = stage_root(tmp_path, hills())
    lod.run(tmp_path, AOI)
    lod.export(tmp_path, AOI)
    batch.run(tmp_path, AOI)
    d = config.dist_dir(tmp_path, AOI)
    sel = json.loads((b / "selection.json").read_text())
    assert sorted(sel) == sorted(config.load_profiles(tmp_path))
    for name, p in sel.items():
        assert len(list(d.glob(f"terrain_{name}_b*.glb"))) == p["terrain_draws"] == len(p["batches"])
        assert sum(x["tris"] for x in p["batches"]) == p["terrain_tris"]
        for x in p["batches"]:
            pos, idx = glb.read_mesh(d / x["file"])
            parts = [glb.read_mesh(d / f"terrain_{c}_lod{p['selection'][c]}.glb") for c in x["chunks"]]
            assert pos.tobytes() == np.concatenate([q for q, _ in parts]).tobytes()
            offs = np.cumsum([0] + [len(q) for q, _ in parts[:-1]])
            want = np.concatenate([i.astype(np.int64) + o for (_, i), o in zip(parts, offs)])
            assert (idx.astype(np.int64) == want).all()
            assert x["index_type"] == ("uint16" if len(pos) <= 65535 else "uint32") == str(idx.dtype)
            assert x["bytes"] == (d / x["file"]).stat().st_size
