"""Schema tests (WP02): every spec example validates, one invalid example per schema is rejected, and the committed
config satisfies META-01, META-03 (config part), and META-04. Registry stubs cover every catalogued rule."""
import copy
import json
import math
from pathlib import Path

import pytest

from tilepipe import config
from tilepipe.validate import registry

ROOT = Path(__file__).resolve().parents[1]
H = "0" * 64

# ---------------------------------------------------------------- spec examples, `...` filled with plausible values

CHUNK_LOD = [(67077, 131072, 2048, "uint32"), (17157, 32768, 1024, "uint16"), (4485, 8192, 512, "uint16"),
             (1221, 2048, 256, "uint16"), (357, 512, 128, "uint16")]
AABB = {"min": [0.0, 400.0, 0.0], "max": [2560.0, 1500.0, 2560.0]}


def tile_example() -> dict:
    chunks = []
    for cz in range(4):
        for cx in range(4):
            cid = f"c{cx}_{cz}"
            chunks.append({"id": cid, "cx": cx, "cz": cz, "aabb": AABB, "lods": [
                {"k": k, "file": f"terrain_{cid}_lod{k}.glb", "vertices": v, "tris_surface": s, "tris_skirt": sk,
                 "tris": s + sk, "index_type": it, "bytes": 1000, "e_max_m": 0.5 * k, "e_rms_m": 0.1 * k,
                 "skirt_depth_m": 1.0 + k, "sha256": H}
                for k, (v, s, sk, it) in enumerate(CHUNK_LOD)]})
    ids = [c["id"] for c in chunks]

    def prof(batches, tau):
        return {"tau_target_m": tau, "e_star_m": 3.9, "budget_forced": False, "error_px_nominal": 1.7,
                "error_px_v3": 3.4, "selection": {c: 2 for c in ids}, "terrain_tris": 16 * 8704,
                "terrain_draws": len(batches), "batches": batches, "texture_bytes": 7689556,
                "terrain_tex_samples": 2, "web_payload_bytes": 9000000, "entity_lod": 1}

    batch = {"file": "terrain_mobile_ar_b00.glb", "chunks": ["c0_0", "c1_0", "c0_1", "c1_1"], "vertices": 17940,
             "tris": 34816, "index_type": "uint16", "bytes": 300000, "aabb": AABB, "sha256": H}
    return {
        "schema": 1, "tile_id": "anza_borrego_01", "name": "Anza-Borrego, Borrego Palm Canyon",
        "generator": "tilepipe 1.0.0",
        "crs": {"epsg": 32611, "zone": 11, "hemisphere": "N", "vertical_datum": "NAVD88", "height_unit": "m"},
        "origin": {"E0": 542830.0, "N0": 3672090.0, "N_top": 3682330.0},
        "extent_m": 10240.0, "cell_m": 10.0, "cells": 1024,
        "height": {"min": 200.0, "max": 1800.0, "plinth_bottom": 100.0},
        "mgrs": {"center": "11SNS4795077210", "gzd": "11S", "square": "NS"},
        "frame": {"handedness": "right", "up": "+Y", "x": "east", "z": "south",
                  "origin": "NW corner, elevation 0", "front_face": "CCW"},
        "table": {"scale": 8000, "exaggeration_default": 1.5, "exaggeration_allowed": [1.0, 1.5, 2.0, 3.0]},
        "source": {"product": "USGS 3DEP 1/3 arc-second DEM", "credit": "Elevation: USGS 3DEP. Public domain.",
                   "crop_sha256": H, "urls": ["https://example.invalid/USGS_13_n34w117.tif"],
                   "retrieved_utc": "2026-11-13T00:00:00Z"},
        "textures": [
            {"id": "height", "file": "terrain_height.rg8.bin", "format": "RG8_UNORM", "colorspace": "linear",
             "width": 1024, "height": 1024, "mip_levels": 1, "bytes": 2097152, "filter": "bilinear",
             "wrap": "clamp", "channels": {"RG": "h = min + (R*65280 + G*255) / 65535 * (max - min)"},
             "sha256": H},
            {"id": "nao", "file": "terrain_nao.rgba8.bin", "format": "RGBA8_UNORM", "colorspace": "linear",
             "width": 1024, "height": 1024, "mip_levels": 11, "bytes": 5592404, "filter": "trilinear",
             "wrap": "clamp", "channels": {"R": "normal.x * 0.5 + 0.5", "G": "normal.z * 0.5 + 0.5",
                                           "B": "ambient occlusion", "A": "reserved, 255"}, "sha256": H}],
        "chunks": chunks,
        "profiles": {"mobile_ar": prof([batch], 4.654),
                     "workstation": prof([dict(batch, file="terrain_workstation_b00.glb")], 2.793)},
        "entities": ["ent_vehicle_wheeled_a", "ent_mast_comms_a", "ent_uas_quad_a"],
        "scene": "scene.json", "looks": ["opaque", "additive"],
    }


def entity_example() -> dict:
    eid = "ent_vehicle_wheeled_a"
    return {"schema": 1, "id": eid, "class": "vehicle", "display": {"mode": "token", "table_size_m": 0.025},
            "up": "+Y", "front": "+Z", "origin": "ground footprint center",
            "bbox_m": {"min": [-1.1, 0.0, -2.5], "max": [1.1, 2.0, 2.5]}, "base_color_srgb": "#F2F0EA",
            "lods": [{"n": n, "file": f"{eid}_LOD{n}.glb", "tris": t, "vertices": t, "primitives": 1,
                      "materials": 1, "texture_bytes": 0, "bytes": 5000, "sha256": H}
                     for n, t in enumerate([6000, 1400, 380])],
            "source_blend_sha256": H}


def validation_example() -> dict:
    results = [registry.skip(rid, "tile", "not implemented").to_dict() for rid in ("GEO-01", "TER-02")]
    results.append(registry.check_result("TER-01", "profile:mobile_ar", True, 139264, 112500, "tris").to_dict())
    return {"schema": 1, "aoi": "anza_borrego_01", "results": results,
            "summary": {"tile": {"pass": 0, "fail": 0, "warn": 0, "skip": 2},
                        "profile:mobile_ar": {"pass": 1, "fail": 0, "warn": 0, "skip": 0}}}


def committed_configs():
    yield "aois", "aois.toml", config.load_aois(ROOT)
    for name, p in config.load_profiles(ROOT).items():
        yield "profile", f"profiles/{name}.toml", p
    for mode, look in config.load_looks(ROOT).items():
        yield "look", f"look/{mode}.json", look


# ---------------------------------------------------------------- valid examples

@pytest.mark.parametrize("schema,what,doc", list(committed_configs()), ids=lambda x: x if isinstance(x, str) else "")
def test_schema_committed_config_validates(schema, what, doc):
    assert config.schema_errors(doc, schema) == [], what


def test_schema_config_set_is_complete():
    assert set(config.load_profiles(ROOT)) == {"mobile_ar", "workstation"}
    assert set(config.load_looks(ROOT)) == {"opaque", "additive"}
    assert list(config.load_aois(ROOT)) == ["anza_borrego_01", "st_helens_01"]
    assert config.default_aoi(ROOT) == "anza_borrego_01"


@pytest.mark.parametrize("schema,make", [("tile", tile_example), ("entity", entity_example),
                                         ("validation", validation_example)])
def test_schema_spec_example_validates(schema, make):
    assert config.schema_errors(make(), schema) == []


def test_schema_tile_without_mgrs_validates():
    doc = tile_example()
    del doc["mgrs"]  # P0.9 cut
    assert config.schema_errors(doc, "tile") == []


# ---------------------------------------------------------------- invalid examples, one or more per schema

def _mut(doc, fn):
    d = copy.deepcopy(doc)
    fn(d)
    return d


INVALID = [
    ("aois", lambda: _mut(config.load_aois(ROOT), lambda d: d["anza_borrego_01"].pop("min_relief_m"))),
    ("aois", lambda: {"Bad-Id": config.load_aois(ROOT)["anza_borrego_01"]}),
    ("profile", lambda: _mut(config.load_profiles(ROOT)["mobile_ar"],
                             lambda d: d["budget"].__setitem__("draw_calls_max", "20"))),
    ("profile", lambda: _mut(config.load_profiles(ROOT)["mobile_ar"], lambda d: d.__setitem__("extra", 1))),
    ("look", lambda: _mut(config.load_looks(ROOT)["additive"], lambda d: d.pop("bg_gain"))),
    ("look", lambda: _mut(config.load_looks(ROOT)["opaque"], lambda d: d.__setitem__("line_srgb", "#1e1d1"))),
    ("tile", lambda: _mut(tile_example(), lambda d: d["chunks"].pop())),
    ("tile", lambda: _mut(tile_example(), lambda d: d["textures"][0].__setitem__("colorspace", "srgb"))),
    ("tile", lambda: _mut(tile_example(), lambda d: d["profiles"]["mobile_ar"]["selection"].__setitem__("c0_0", 5))),
    ("entity", lambda: _mut(entity_example(), lambda d: d["lods"][0].__setitem__("materials", 2))),
    ("entity", lambda: _mut(entity_example(), lambda d: d.__setitem__("id", "vehicle_a"))),
    ("validation", lambda: _mut(validation_example(), lambda d: d["results"][0].__setitem__("status", "OK"))),
    ("validation", lambda: _mut(validation_example(), lambda d: d["results"][0].pop("fix_hint"))),
]


@pytest.mark.parametrize("schema,make", INVALID, ids=[f"{s}-{i}" for i, (s, _) in enumerate(INVALID)])
def test_schema_invalid_example_rejected(schema, make):
    assert config.schema_errors(make(), schema)


def test_schema_invalid_config_raises_usage_error(tmp_path):
    (tmp_path / "aois.toml").write_text('[x_01]\nname = "x"\n', encoding="utf-8")
    with pytest.raises(config.UsageError) as e:
        config.load_aois(tmp_path)
    assert e.value.code == 2


def test_schema_every_schema_file_is_strict():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, node
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    names = sorted(p.name.split(".")[0] for p in config.SCHEMA_DIR.glob("*.schema.json"))
    assert names == ["aois", "entity", "look", "profile", "tile", "validation"]
    for n in names:
        walk(config.load_schema(n))


# ---------------------------------------------------------------- META-01, META-04 on the committed config

@pytest.mark.parametrize("name", ["mobile_ar", "workstation"])
def test_schema_meta01_budgets_derive_from_anchor(name):
    p = config.load_profiles(ROOT)[name]
    a, s, b = p["anchor"], p["share"], p["budget"]
    frame = math.floor(a["frame_tris"] * s["content"] + 1e-9)
    assert b["frame_tris_max"] == frame
    assert b["terrain_tris_max"] == math.floor(frame * s["terrain"] + 1e-9)
    assert b["entity_tris_max"] == math.floor(frame * s["entities"] + 1e-9)
    assert b["draw_calls_max"] == math.floor(a["draw_calls"] * s["content"] + 1e-9)
    assert math.isclose(s["terrain"] + s["entities"] + s["reserve"], 1.0, abs_tol=1e-9)


def test_schema_meta04_entity_lod_limits():
    d = config.load_entity_lods(ROOT)
    for lod in d["lod"]:
        deg = math.degrees(2 * math.atan(d["token_table_size_m"] / 2 / lod["view_distance_m"]))
        px = deg * lod["ppd"]
        assert lod["tris_max"] <= 2 * px * px / d["min_triangle_area_px"], lod
    for p in config.load_profiles(ROOT).values():
        assert 0 <= p["entities"]["lod"] < len(d["lod"])


# ---------------------------------------------------------------- registry and result record

def test_schema_registry_catalog_is_complete_and_stubbed():
    ids = [r[0] for r in registry.CATALOG]
    assert len(ids) == len(set(ids)) == 61
    want = (["META-01", "META-02", "META-03", "META-04", "DET-01", "OFF-01", "REG-01"]
            + [f"GEO-{i:02d}" for i in range(1, 4)] + [f"TER-{i:02d}" for i in range(1, 12)]
            + [f"TEX-{i:02d}" for i in range(1, 6)] + ["GLB-01", "GLB-02", "PAY-01"]
            + [f"LOOK-{i:02d}" for i in range(1, 6)] + [f"ENT-{i:02d}" for i in range(1, 16)]
            + [f"ENTD-{i:02d}" for i in range(1, 7)] + [f"SCN-{i:02d}" for i in range(1, 6)] + ["PERF-01"])
    assert sorted(ids) == sorted(want)
    warn = {"META-02", "TER-09", "ENT-13", "SCN-05", "PERF-01"}
    for r in registry.RULES.values():
        assert r.severity == ("WARN" if r.id in warn else "FAIL")
        assert r.scope_kind in registry.SCOPE_KINDS and r.doc
    ctx = registry.Context(root=ROOT, aoi="anza_borrego_01")
    for rid, r in registry.RULES.items():
        res = r.check(ctx, "repo")
        assert res.status == "SKIP" and res.rule == rid and res.message.startswith(f"{rid} SKIP repo: ")
        assert config.schema_errors({"schema": 1, "aoi": "anza_borrego_01", "results": [res.to_dict()],
                                     "summary": {}}, "validation") == []


def test_schema_result_message_format():
    r = registry.check_result("TER-01", "profile:mobile_ar", False, 139264, 112500, "tris",
                              fix_hint="Raise pixel_error or coarsen LODs.")
    assert r.status == "FAIL"
    assert r.message == ("TER-01 FAIL profile:mobile_ar: measured 139264 tris, limit <= 112500 tris. "
                         "Raise pixel_error or coarsen LODs.")
    w = registry.check_result("TER-09", "profile:mobile_ar", False, 4.5, 4.0, "px")
    assert w.status == "WARN" and w.message == "TER-09 WARN profile:mobile_ar: measured 4.5 px, limit <= 4 px."
    with pytest.raises(ValueError):
        registry.skip("GEO-02", "tile", "")
    with pytest.raises(KeyError):
        registry.implements("XYZ-01")


def test_schema_canonical_json(tmp_path):
    p = tmp_path / "a.json"
    config.write_json(p, {"b": 1.23456789, "a": [0.1 + 0.2]})
    assert p.read_bytes() == b'{\n  "a": [\n    0.3\n  ],\n  "b": 1.234568\n}\n'
    with pytest.raises(ValueError):
        config.dumps_json({"x": float("nan")})
    assert json.loads(p.read_text(encoding="utf-8"))["b"] == 1.234568
