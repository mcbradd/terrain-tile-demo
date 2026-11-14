"""T-LOD-PLANE, T-LOD-KNOWN, T-SKIRT (SPEC 7.2, 7.3, 16.2) on synthetic height fields that match B/h_full.npy."""
import json
import math

import numpy as np
import pytest

from tilepipe import config, glb, lod

AOI = "synthetic_01"
TABLE_7_2 = {0: (67077, 133120, np.uint32), 1: (17157, 33792, np.uint16), 2: (4485, 8704, np.uint16),
             3: (1221, 2304, np.uint16), 4: (357, 640, np.uint16)}


def hills() -> np.ndarray:
    """Smooth synthetic terrain plus small noise, float32 [1152, 1152], row 0 north."""
    r, c = np.mgrid[0:1152, 0:1152].astype(np.float64)
    h = 400 + 60 * np.sin(c / 90) * np.cos(r / 70) + 25 * np.sin((r + c) / 23)
    return (h + np.random.default_rng(20261113).normal(0, 0.5, h.shape)).astype(np.float32)


def stage_root(tmp_path, h_full):
    b = config.build_dir(tmp_path, AOI)
    b.mkdir(parents=True)
    np.save(b / "h_full.npy", h_full)
    tile = h_full[64:1088, 64:1088].astype(np.float64)
    config.write_json(b / "geo.json", {"zone": 11, "epsg": 32611, "E0": 0.0, "N0": 0.0, "N_top": 0.0,
                                       "h_min": float(tile.min()), "h_max": float(tile.max()), "mgrs_center": None})
    return b


def test_T_LOD_PLANE(tmp_path):
    r, c = np.mgrid[0:1152, 0:1152].astype(np.float64)
    plane = (200 + 0.05 * 10 * c + 0.02 * 10 * r).astype(np.float32)
    hn = lod.h_node(plane)
    assert hn.shape == (1025, 1025) and hn.dtype == np.float32
    for cx, cz, _ in lod.chunk_ids():
        for k in range(1, 5):
            e_max, _ = lod.lod_error(lod.chunk_nodes(hn, cx, cz), 1 << k)
            assert e_max <= 1e-4
    b = stage_root(tmp_path, plane)
    lod.run(tmp_path, AOI)
    stats = json.loads((b / "lod_stats.json").read_text())
    assert len(stats["chunks"]) == 16
    assert all(max(ch["e_max_m"]) <= 1e-4 for ch in stats["chunks"].values())
    # float32 node heights leave e_max at a few ulp, which the ceil of 7.2 step 5 rounds up to 1.1 m.
    assert stats["skirt_depth_m"][0] == 1.0 and max(stats["skirt_depth_m"]) <= 1.1


def test_T_LOD_KNOWN():
    # h[j, i] = i * j. The LOD 1 mesh is exact on the even nodes and along every LOD 1 edge. The four
    # (odd, odd) nodes sit on a quad's b-c diagonal, where the mesh gives (hb + hc) / 2 = i*j - 1: e = 1 each.
    j, i = np.mgrid[0:5, 0:5]
    e_max, e_rms = lod.lod_error((i * j).astype(np.float32), 2)
    assert e_max == 1.0
    assert e_rms == pytest.approx(np.sqrt(4 / 25), abs=1e-12)
    # A 2 m bump on node (i=1, j=0), which LOD 1 drops, is lost entirely: e = 2 there and 0 elsewhere.
    h = np.zeros((5, 5))
    h[0, 1] = 2.0
    assert lod.lod_error(h, 2) == (2.0, pytest.approx(0.4, abs=1e-12))


def test_LOD_node_mean():
    h = hills()
    hn = lod.h_node(h)
    j, i = 300, 517
    want = np.float32(np.mean(h[63 + j:65 + j, 63 + i:65 + i].astype(np.float64)))
    assert hn[j, i] == want


# ---------------------------------------------------------------- T-SKIRT (rule TER-05 semantics)

OUTWARD = [(0, 0, -1), (1, 0, 0), (0, 0, 1), (-1, 0, 0)]  # N, E, S, W in TL (+Z is south)


def skirt_faults(pos, idx, k, cx, cz, depth, h_min) -> list[str]:
    """TER-05: every skirt face winds outward, and every skirt vertex sits D_k below its surface vertex,
    or at h_min - 100.0 on a tile-border edge."""
    n, _, _ = lod.lod_counts(k)
    tris = idx.reshape(-1, 3).astype(np.int64)[2 * (n - 1) ** 2:]
    border = [cz == 0, cx == 3, cz == 3, cx == 0]
    faults = []
    for e, top in enumerate(lod.edge_vertices(n)):
        t = tris[e * 2 * (n - 1):(e + 1) * 2 * (n - 1)]
        p = pos.astype(np.float64)[t]
        normal = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
        if not (normal @ np.array(OUTWARD[e], dtype=np.float64) > 0).all():
            faults.append(f"edge {e}: skirt face winds inward")
        bot = pos[n * n + e * n:n * n + (e + 1) * n, 1]
        if border[e]:
            ok = (bot == np.float32(h_min - 100.0)).all()
        else:
            ok = np.allclose(bot, pos[top, 1] - depth, atol=1e-3, rtol=0)
        if not ok:
            faults.append(f"edge {e}: skirt bottom at wrong height")
    return faults


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    root = tmp_path_factory.mktemp("root")
    b = stage_root(root, hills())
    lod.run(root, AOI)
    lod.export(root, AOI)
    return root, json.loads((b / "lod_stats.json").read_text()), json.loads((b / "geo.json").read_text())


def test_LOD_export_counts(exported):
    root, stats, _ = exported
    d = config.dist_dir(root, AOI)
    assert len(list(d.glob("terrain_c*_lod*.glb"))) == 80
    for _, _, cid in lod.chunk_ids():
        e = stats["chunks"][cid]["e_max_m"]
        # TER-07 (non-decreasing in k) is not guaranteed by the 7.2 metric; WP07 checks it on real data.
        assert e[0] == 0.0 and min(e[1:]) > 0.0
        for k, (verts, tris, itype) in TABLE_7_2.items():
            pos, idx = glb.read_mesh(d / f"terrain_{cid}_lod{k}.glb")
            assert (len(pos), idx.size // 3, idx.dtype) == (verts, tris, itype)
            assert idx.max() < len(pos)
    assert stats["skirt_depth_m"][0] == 1.0
    worst = [max(stats["chunks"][c]["e_max_m"][k] for _, _, c in lod.chunk_ids()) for k in range(5)]
    assert stats["skirt_depth_m"] == [math.ceil((2 * w + 1.0) * 10) / 10 for w in worst]


def test_LOD_shared_borders_identical(exported):
    root, _, _ = exported
    d = config.dist_dir(root, AOI)
    p00, _ = glb.read_mesh(d / "terrain_c0_0_lod0.glb")
    p10, _ = glb.read_mesh(d / "terrain_c1_0_lod0.glb")
    n = 257
    east = p00[np.arange(n) * n + n - 1]
    west = p10[np.arange(n) * n]
    assert east.tobytes() == west.tobytes()


def test_T_SKIRT(exported):
    root, stats, geo = exported
    d = config.dist_dir(root, AOI)
    for cx, cz, cid in lod.chunk_ids():
        for k in range(5):
            pos, idx = glb.read_mesh(d / f"terrain_{cid}_lod{k}.glb")
            args = (k, cx, cz, stats["skirt_depth_m"][k], geo["h_min"])
            assert skirt_faults(pos, idx, *args) == [], (cid, k)
    # Reversing the skirt winding must fail the rule.
    pos, idx = glb.read_mesh(d / "terrain_c1_1_lod2.glb")
    n = lod.lod_counts(2)[0]
    tris = idx.reshape(-1, 3).copy()
    tris[2 * (n - 1) ** 2:] = tris[2 * (n - 1) ** 2:, ::-1]
    faults = skirt_faults(pos, tris.ravel(), 2, 1, 1, stats["skirt_depth_m"][2], geo["h_min"])
    assert len([f for f in faults if "inward" in f]) == 4
