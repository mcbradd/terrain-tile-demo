"""Core validator rules (SPEC 12): one passing and one failing case per rule, plus T-REG and the runner outputs.

Passing cases run on a real build into a scratch root. Failing cases mutate a hard-linked clone of it, or seed the
context cache, so the repository's own build output is never touched. Test names `test_rule_<FAMILY>_<nn>_<pass|fail>`
are what rule REG-01 looks for.
"""
import copy
import json
import os
import re
import shutil
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from tilepipe import config, glb
from tilepipe.validate import common, registry, rules_meta, runner
from tilepipe.validate.registry import RULES, Context
from tilepipe.validate.rules_meta import SPEC_RULE_IDS, _stage_root, build_into
from tilepipe.validate.rules_scene import static_counts

runner._load_rules()
ROOT = Path(__file__).resolve().parent.parent
AOI = "anza_borrego_01"
TILE, REPO = "tile", "repo"
MOBILE, WORK = "profile:mobile_ar", "profile:workstation"
MSG = re.compile(r"^([A-Z]+-\d\d) (PASS|FAIL|WARN) (\S+): measured .+, limit (<=|>=|==|<|>) .+\.( .+)?$")


# ---------------------------------------------------------------- fixtures and helpers

@pytest.fixture(scope="session")
def built(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("built")
    _stage_root(ROOT, root)
    build_into(root, AOI)
    return root


def _link(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


@pytest.fixture
def clone(built, tmp_path) -> Path:
    dst = tmp_path / "clone"
    shutil.copytree(built, dst, copy_function=_link)
    return dst


def make_ctx(root: Path, **options) -> Context:
    return Context(root=root, aoi=AOI, profiles=config.load_profiles(root), looks=config.load_looks(root),
                   entity_lods=config.load_entity_lods(root), options=options)


def rewrite(path: Path, data: bytes) -> None:
    """Replace a file without touching the hard-linked original."""
    path.unlink()
    path.write_bytes(data)


def edit_json(root: Path, rel: str, fn) -> None:
    p = root / rel
    doc = json.loads(p.read_text(encoding="utf-8"))
    fn(doc)
    rewrite(p, config.dumps_json(doc).encode("utf-8"))


def dist(root: Path) -> Path:
    return root / "dist" / AOI


def run_rule(rid: str, ctx: Context, scope: str):
    r = RULES[rid].check(ctx, scope)
    assert r.rule == rid and r.scope == scope
    if r.status != "SKIP":
        m = MSG.match(r.message)
        assert m and m[1] == rid and m[2] == r.status and m[3] == scope, r.message   # 12.1 message format
    return r


def ok(rid: str, ctx: Context, scope: str):
    r = run_rule(rid, ctx, scope)
    assert r.status == "PASS", r.message
    assert r.fix_hint == ""


def bad(rid: str, ctx: Context, scope: str, status: str = "FAIL"):
    r = run_rule(rid, ctx, scope)
    assert r.status == status, r.message
    assert r.fix_hint, "a non-PASS result carries a fix hint"
    return r


def with_profile(ctx: Context, name: str, section: str, key: str, value) -> Context:
    ctx.profiles = copy.deepcopy(ctx.profiles)
    ctx.profiles[name][section][key] = value
    return ctx


def with_look(ctx: Context, mode: str, fn) -> Context:
    ctx.looks = copy.deepcopy(ctx.looks)
    fn(ctx.looks[mode])
    return ctx


def pack_glb(doc: dict, binary: bytes) -> bytes:
    j = json.dumps(doc, separators=(",", ":")).encode()
    j += b" " * (-len(j) % 4)
    binary += b"\0" * (-len(binary) % 4)
    body = struct.pack("<II", len(j), 0x4E4F534A) + j + struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body


def terrain_file(root: Path, cid: str = "c0_0", k: int = 4) -> Path:
    return dist(root) / f"terrain_{cid}_lod{k}.glb"


def swap_winding(idx: np.ndarray, lo: int, hi: int) -> np.ndarray:
    out = idx.copy()
    t = out[lo:hi].reshape(-1, 3)
    t[:, [1, 2]] = t[:, [2, 1]]
    return out


# ---------------------------------------------------------------- META, DET, OFF, REG

def test_rule_META_01_pass(built):
    ok("META-01", make_ctx(built), MOBILE)


def test_rule_META_01_fail(built):
    bad("META-01", with_profile(make_ctx(built), "mobile_ar", "budget", "terrain_tris_max", 112001), MOBILE)


def test_rule_META_02_pass(built):
    ok("META-02", make_ctx(built), TILE)


def test_rule_META_02_fail(clone):
    edit_json(clone, f"build/{AOI}/build_info.json", lambda d: d.update(total_seconds=121.0))
    bad("META-02", make_ctx(clone), TILE, "WARN")


def test_rule_META_03_pass(built):
    ok("META-03", make_ctx(built), REPO)


def test_rule_META_03_fail(clone):
    edit_json(clone, f"dist/{AOI}/tile.json", lambda d: d.pop("textures"))
    bad("META-03", make_ctx(clone), REPO)


def test_rule_META_04_pass(built):
    ok("META-04", make_ctx(built), REPO)


def test_rule_META_04_fail(built):
    ctx = make_ctx(built)
    ctx.entity_lods = copy.deepcopy(ctx.entity_lods)
    ctx.entity_lods["lod"][2]["tris_max"] = 10_000_000
    bad("META-04", ctx, REPO)


@pytest.fixture(scope="module")
def determinism_ctx(built):
    ctx = make_ctx(built, determinism=True)
    rules_meta.two_builds(ctx)   # memoized on ctx.cache; DET-01 and OFF-01 share the two scratch builds
    return ctx


def test_rule_DET_01_pass(built, determinism_ctx):
    ok("DET-01", determinism_ctx, TILE)


def test_rule_DET_01_fail(built):
    ctx = make_ctx(built, determinism=True)
    ctx.cache["two_builds"] = {"hashes": ["a  x\n", "b  x\n"], "errors": ["", ""]}
    bad("DET-01", ctx, TILE)


def test_rule_OFF_01_pass(built, determinism_ctx):
    ok("OFF-01", determinism_ctx, REPO)


def test_rule_OFF_01_fail(built):
    ctx = make_ctx(built, determinism=True)
    ctx.cache["two_builds"] = {"hashes": ["a", ""], "errors": ["", "OfflineError: network attempt"]}
    bad("OFF-01", ctx, REPO)


def test_rule_REG_01_pass():
    ok("REG-01", make_ctx(ROOT), REPO)


def test_rule_REG_01_fail(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_rule_META_01_pass():\n    pass\n", encoding="utf-8")
    ctx = make_ctx(ROOT)
    ctx.root = tmp_path
    r = bad("REG-01", ctx, REPO)
    assert "META-01 has no fail case" in r.fix_hint


def test_reg_catalog_matches_spec_and_only_entity_rules_are_stubs():
    assert sorted(RULES) == SPEC_RULE_IDS
    assert all(s.startswith("ENT-") for s in registry.stubs())   # ENT-01 to ENT-15 belong to the Blender package


# ---------------------------------------------------------------- GEO

def test_rule_GEO_01_pass(built):
    ok("GEO-01", make_ctx(built), TILE)


def test_rule_GEO_01_fail(built):
    ctx = make_ctx(built)
    ctx.cache["h_full"] = np.roll(common.h_full(ctx), 5, axis=1)   # 50 m shift
    bad("GEO-01", ctx, TILE)


def test_rule_GEO_02_pass(built):
    ok("GEO-02", make_ctx(built), TILE)


def test_rule_GEO_02_fail(clone):
    edit_json(clone, f"build/{AOI}/geo.json", lambda d: d.update(mgrs_center=d["mgrs_center"][:-10] + "5307082999"))
    bad("GEO-02", make_ctx(clone), TILE)


def test_rule_GEO_03_pass(built):
    ok("GEO-03", make_ctx(built), TILE)


def test_rule_GEO_03_fail(clone):
    edit_json(clone, f"build/{AOI}/geo.json", lambda d: d.update(E0=d["E0"] + 5))
    bad("GEO-03", make_ctx(clone), TILE)


# ---------------------------------------------------------------- TER

def test_rule_TER_01_pass(built):
    ok("TER-01", make_ctx(built), MOBILE)


def test_rule_TER_01_fail(built):
    bad("TER-01", with_profile(make_ctx(built), "mobile_ar", "budget", "terrain_tris_max", 1000), MOBILE)


def test_rule_TER_02_pass(built):
    ok("TER-02", make_ctx(built), TILE)


def test_rule_TER_02_fail(clone):
    f = terrain_file(clone, "c0_0", 0)
    rewrite(f, terrain_file(clone, "c0_0", 1).read_bytes())
    bad("TER-02", make_ctx(clone), TILE)


def test_rule_TER_03_pass(built):
    ok("TER-03", make_ctx(built), TILE)


def test_rule_TER_03_fail(clone):
    f = terrain_file(clone)
    pos, idx = glb.read_mesh(f)
    f.unlink()
    glb.write_glb(f, pos, idx.astype(np.uint32))   # uint32 below 65,536 vertices
    bad("TER-03", make_ctx(clone), TILE)


def test_rule_TER_04_pass(built):
    ok("TER-04", make_ctx(built), MOBILE)


def test_rule_TER_04_fail(clone):
    f = dist(clone) / "terrain_height.rg8.bin"
    rewrite(f, bytes(f.stat().st_size))
    bad("TER-04", make_ctx(clone), MOBILE)


def test_rule_TER_05_pass(built):
    ok("TER-05", make_ctx(built), TILE)


def test_rule_TER_05_fail(clone):
    f = terrain_file(clone)
    pos, idx = glb.read_mesh(f)
    q = 16
    f.unlink()
    glb.write_glb(f, pos, swap_winding(idx, 6 * q * q, len(idx)))   # T-SKIRT: reversed skirt winding
    bad("TER-05", make_ctx(clone), TILE)


def test_rule_TER_06_pass(built):
    ok("TER-06", make_ctx(built), TILE)


def test_rule_TER_06_fail(clone):
    f = terrain_file(clone)
    pos, idx = glb.read_mesh(f)
    f.unlink()
    glb.write_glb(f, pos, swap_winding(idx, 0, 6 * 16 * 16))
    bad("TER-06", make_ctx(clone), TILE)


def test_rule_TER_07_pass(built):
    ok("TER-07", make_ctx(built), TILE)


def test_rule_TER_07_fail(clone):
    edit_json(clone, f"build/{AOI}/lod_stats.json", lambda d: d["chunks"]["c0_0"].update(e_max_m=[0.0, 2.0, 1.0, 3.0, 4.0]))
    bad("TER-07", make_ctx(clone), TILE)


def test_rule_TER_08_pass(built):
    ok("TER-08", make_ctx(built), MOBILE)


def test_rule_TER_08_fail(clone):
    def f(d):
        sel = d["profiles"]["mobile_ar"]["selection"]
        sel["c0_0"] = (sel["c0_0"] + 1) % 5
    edit_json(clone, f"dist/{AOI}/tile.json", f)
    bad("TER-08", make_ctx(clone), MOBILE)


def test_rule_TER_09_pass(clone):
    edit_json(clone, f"dist/{AOI}/tile.json", lambda d: d["profiles"]["mobile_ar"].update(error_px_nominal=3.0))
    ok("TER-09", make_ctx(clone), MOBILE)


def test_rule_TER_09_fail(clone):
    edit_json(clone, f"dist/{AOI}/tile.json", lambda d: d["profiles"]["mobile_ar"].update(error_px_nominal=4.5))
    bad("TER-09", make_ctx(clone), MOBILE, "WARN")


def test_rule_TER_10_pass(built):
    ok("TER-10", make_ctx(built), TILE)


def test_rule_TER_10_fail(clone):
    edit_json(clone, f"dist/{AOI}/tile.json", lambda d: d["chunks"][0]["aabb"]["max"].__setitem__(1, d["chunks"][0]["aabb"]["max"][1] + 1))
    bad("TER-10", make_ctx(clone), TILE)


def test_rule_TER_11_pass(built):
    ok("TER-11", make_ctx(built), TILE)


def test_rule_TER_11_fail(clone):
    f = terrain_file(clone, "c0_0", 0)
    pos, idx = glb.read_mesh(f)
    pos = pos.copy()
    pos[256, 1] += 0.5   # node (i=256, j=0) of the east edge
    f.unlink()
    glb.write_glb(f, pos, idx)
    bad("TER-11", make_ctx(clone), TILE)


# ---------------------------------------------------------------- TEX, GLB, PAY

def test_rule_TEX_01_pass(built):
    ok("TEX-01", make_ctx(built), MOBILE)


def test_rule_TEX_01_fail(clone):
    f = dist(clone) / "terrain_nao.rgba8.bin"
    rewrite(f, f.read_bytes()[:-1])   # one byte short of 5,592,404
    bad("TEX-01", make_ctx(clone), MOBILE)


def test_rule_TEX_02_pass(built):
    ok("TEX-02", make_ctx(built), TILE)


def test_rule_TEX_02_fail(clone):
    edit_json(clone, f"dist/{AOI}/tile.json", lambda d: d["textures"][1].update(mip_levels=10))
    bad("TEX-02", make_ctx(clone), TILE)


def test_rule_TEX_03_pass(built):
    ok("TEX-03", make_ctx(built), TILE)


def test_rule_TEX_03_fail(clone):
    f = dist(clone) / "terrain_nao.rgba8.bin"
    rewrite(f, bytes([0, 0, 255, 255]) + f.read_bytes()[4:])   # nx = nz = -1, length 1.414
    bad("TEX-03", make_ctx(clone), TILE)


def test_rule_TEX_04_pass(built):
    ok("TEX-04", make_ctx(built), TILE)


def test_rule_TEX_04_fail(clone):
    f = dist(clone) / "terrain_height.rg8.bin"
    rewrite(f, bytes(f.stat().st_size))
    bad("TEX-04", make_ctx(clone), TILE)


SHADER = "#version 300 es\n// TEXTURE_SAMPLES: 2\nprecision highp float;\n// texture( in a comment is not a fetch\n{body}\n"
TWO = "void f(){ textureLod(u_height, uv, 0.0); texture(u_nao, uv); }"


def put_shader(root: Path, body: str, declared: int = 2) -> None:
    d = root / "viewer" / "src" / "shaders"
    d.mkdir(parents=True, exist_ok=True)
    (d / "terrain.frag.glsl").write_text(SHADER.format(body=body), encoding="utf-8")
    edit_json(root, f"dist/{AOI}/tile.json", lambda t: [p.update(terrain_tex_samples=declared) for p in t["profiles"].values()])


def test_rule_TEX_05_pass(clone):
    put_shader(clone, TWO)
    ok("TEX-05", make_ctx(clone), MOBILE)


def test_rule_TEX_05_fail(clone):
    put_shader(clone, TWO.replace("}", "texture(u_nao, uv); }"), declared=2)   # three fetches against a comment of two
    r = bad("TEX-05", make_ctx(clone), MOBILE)
    assert "3" in r.message


def test_rule_GLB_01_pass(built):
    ok("GLB-01", make_ctx(built), TILE)
    assert (common.build(make_ctx(built)) / "gltf_validator.json").exists()   # infos and hints are recorded


def test_rule_GLB_01_fail(clone):
    f = terrain_file(clone)
    rewrite(f, f.read_bytes()[:-8])   # BIN chunk longer than the file
    bad("GLB-01", make_ctx(clone), TILE)


def test_rule_GLB_02_pass(built):
    ok("GLB-02", make_ctx(built), TILE)


def test_rule_GLB_02_fail(clone):
    f = terrain_file(clone)
    doc, binary = glb.parse_glb(f.read_bytes())
    doc["materials"] = [{}]
    doc["meshes"][0]["primitives"][0]["material"] = 0
    rewrite(f, pack_glb(doc, binary))
    bad("GLB-02", make_ctx(clone), TILE)


def test_rule_PAY_01_pass(built):
    ok("PAY-01", make_ctx(built), WORK)


def test_rule_PAY_01_fail(built):
    bad("PAY-01", with_profile(make_ctx(built), "mobile_ar", "budget", "web_payload_bytes_max", 1_000_000), MOBILE)


# ---------------------------------------------------------------- LOOK

def test_rule_LOOK_01_pass(built):
    ok("LOOK-01", make_ctx(built), REPO)


def test_rule_LOOK_01_fail(built):
    bad("LOOK-01", with_look(make_ctx(built), "opaque", lambda l: l["ramp"][0].update(srgb="#B05A3C")), REPO)


def test_rule_LOOK_02_pass(built):
    ok("LOOK-02", make_ctx(built), REPO)


def test_rule_LOOK_02_fail(built):
    bad("LOOK-02", with_look(make_ctx(built), "opaque", lambda l: l.update(line_srgb="#6B6A5E")), REPO)


def test_rule_LOOK_03_pass(built):
    ok("LOOK-03", make_ctx(built), REPO)


def test_rule_LOOK_03_fail(built):
    bad("LOOK-03", with_look(make_ctx(built), "additive", lambda l: l.update(k_dim=0.05)), REPO)


def test_rule_LOOK_04_pass(built):
    ok("LOOK-04", make_ctx(built), REPO)


def test_rule_LOOK_04_fail(built):
    bad("LOOK-04", with_look(make_ctx(built), "additive", lambda l: l.update(line_srgb="#FF3030")), REPO)


def test_rule_LOOK_05_pass(built):
    ok("LOOK-05", make_ctx(built), TILE)


def test_rule_LOOK_05_fail(clone):
    d = clone / "dist" / "entities" / "ent_vehicle_wheeled_a"
    d.mkdir(parents=True)
    (d / "entity.json").write_text(json.dumps({"id": "ent_vehicle_wheeled_a", "base_color_srgb": "#6B6A5E"}), encoding="utf-8")
    bad("LOOK-05", make_ctx(clone), TILE)


# ---------------------------------------------------------------- SCN, PERF

def test_rule_SCN_01_pass(built):
    ok("SCN-01", make_ctx(built), MOBILE)


def test_rule_SCN_01_fail(built):
    bad("SCN-01", with_profile(make_ctx(built), "mobile_ar", "budget", "entity_tris_max", 10), MOBILE)


def test_rule_SCN_02_pass(built):
    r = run_rule("SCN-02", make_ctx(built), MOBILE)
    assert r.status == "PASS" and r.measured == 8 and r.limit == 20   # 12.8: expected 8 of 20
    assert run_rule("SCN-02", make_ctx(built), WORK).measured == 20


def test_rule_SCN_02_fail(built):
    bad("SCN-02", with_profile(make_ctx(built), "mobile_ar", "budget", "draw_calls_max", 7), MOBILE)


def test_rule_SCN_03_pass(built):
    ok("SCN-03", make_ctx(built), TILE)


def test_rule_SCN_03_fail(clone):
    edit_json(clone, f"scene/{AOI}_scene.json", lambda d: d["instances"][0].update(heading_deg=d["instances"][0]["heading_deg"] + 1))
    bad("SCN-03", make_ctx(clone), TILE)


def write_bench(root: Path, ctx: Context, delta: int = 0, frac: float = 0.01) -> None:
    prof = {}
    for n in ctx.profiles:
        tris, draws = static_counts_for(ctx, n)
        prof[n] = {"live_tris": tris + delta, "live_draws": draws, "frac_longer_than_1p5_median": frac}
    b = root / "build" / AOI
    (b / "bench.json").write_text(json.dumps({"profiles": prof}), encoding="utf-8")


def static_counts_for(ctx, name):
    _, tris, draws = static_counts(ctx, name, strict=False)
    return tris, draws


def write_entity_jsons(root: Path) -> None:
    """Minimal entity.json files, so SCN-04 can count strictly from exported data."""
    for e in common.tile(make_ctx(root))["entities"]:
        d = root / "dist" / "entities" / e
        d.mkdir(parents=True)
        (d / "entity.json").write_text(json.dumps({"id": e, "lods": [{"tris": 7000}, {"tris": 1500}, {"tris": 400}]}), encoding="utf-8")


def test_rule_SCN_04_pass(clone):
    write_entity_jsons(clone)
    ctx = make_ctx(clone)
    write_bench(clone, ctx)
    ok("SCN-04", ctx, MOBILE)


def test_rule_SCN_04_fail(clone):
    write_entity_jsons(clone)
    ctx = make_ctx(clone)
    write_bench(clone, ctx, delta=3)
    bad("SCN-04", ctx, MOBILE)


def test_scn_04_and_perf_01_skip_without_bench_json(built):
    for rid, scope in (("SCN-04", MOBILE), ("PERF-01", TILE)):
        r = RULES[rid].check(make_ctx(built), scope)
        assert r.status == "SKIP" and "bench.json" in r.message and r.message.startswith(f"{rid} SKIP {scope}: ")


def test_rule_SCN_05_pass(built):
    ok("SCN-05", make_ctx(built), MOBILE)


def test_rule_SCN_05_fail(built):
    ctx = make_ctx(built)
    ctx.cache["h_full"] = common.h_full(ctx).astype(np.float64) + 50.0   # drawn mesh is 50 m off the "true" ground
    bad("SCN-05", ctx, MOBILE, "WARN")


def test_rule_PERF_01_pass(clone):
    ctx = make_ctx(clone)
    write_bench(clone, ctx, frac=0.01)
    ok("PERF-01", ctx, TILE)


def test_rule_PERF_01_fail(clone):
    ctx = make_ctx(clone)
    write_bench(clone, ctx, frac=0.25)
    bad("PERF-01", ctx, TILE, "WARN")


# ---------------------------------------------------------------- ENTD, on entity GLBs synthesized here

BOX = np.array([[x, y, z] for y in (0.0, 1.0) for z in (-2.0, 2.0) for x in (-1.0, 1.0)], dtype=np.float32)
BOX_IDX = np.array([0, 1, 3, 0, 3, 2, 4, 6, 7, 4, 7, 5, 0, 4, 5, 0, 5, 1, 2, 3, 7, 2, 7, 6, 0, 2, 6, 0, 6, 4, 1, 5, 7, 1, 7, 3],
                   dtype=np.uint16)


def write_entity(root: Path, ent: str = "ent_test_a", pos=None, nrm=None, doc_edit=None, bbox_extra: float = 0.0,
                 n_verts: int | None = None, indices=None) -> None:
    pos = BOX if pos is None else pos
    idx = BOX_IDX if indices is None else indices
    if n_verts:
        pos = np.zeros((n_verts, 3), dtype=np.float32)
        pos[:8] = BOX
    if nrm is None:
        nrm = pos - pos.mean(axis=0)
        nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        nrm[np.linalg.norm(pos - pos.mean(axis=0), axis=1) == 0] = [0, 1, 0]
    nrm = nrm.astype(np.float32)
    binary = pos.tobytes() + nrm.tobytes() + idx.tobytes()
    lo, hi = pos.min(axis=0).tolist(), pos.max(axis=0).tolist()
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": 0}]}],
           "materials": [{}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3", "min": lo, "max": hi},
                         {"bufferView": 1, "componentType": 5126, "count": len(nrm), "type": "VEC3"},
                         {"bufferView": 2, "componentType": 5123, "count": len(idx), "type": "SCALAR"}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": pos.nbytes},
                           {"buffer": 0, "byteOffset": pos.nbytes, "byteLength": nrm.nbytes},
                           {"buffer": 0, "byteOffset": pos.nbytes + nrm.nbytes, "byteLength": idx.nbytes}],
           "buffers": [{"byteLength": len(binary)}]}
    if doc_edit:
        doc_edit(doc)
    d = root / "dist" / "entities" / ent
    d.mkdir(parents=True, exist_ok=True)
    for n in range(3):
        (d / f"{ent}_LOD{n}.glb").write_bytes(pack_glb(doc, binary))
    size = np.array(BOX.max(axis=0) - BOX.min(axis=0)) + bbox_extra
    (d / "entity.json").write_text(json.dumps({"id": ent, "bbox_m": {"min": [0, 0, 0], "max": size.tolist()}}), encoding="utf-8")


ENT = "entity:ent_test_a"


@pytest.fixture
def eroot(tmp_path) -> Path:
    return tmp_path


def entd_ctx(root: Path) -> Context:
    return Context(root=root, aoi=AOI, entity_lods=config.load_entity_lods(ROOT), options={})


def test_rule_ENTD_01_pass(eroot):
    write_entity(eroot)
    ok("ENTD-01", entd_ctx(eroot), ENT)


def test_rule_ENTD_01_fail(eroot):
    write_entity(eroot, doc_edit=lambda d: d.update(images=[{"uri": "x.png"}]))
    bad("ENTD-01", entd_ctx(eroot), ENT)


def test_rule_ENTD_02_pass(eroot):
    write_entity(eroot)
    ok("ENTD-02", entd_ctx(eroot), ENT)


def test_rule_ENTD_02_fail(eroot):
    write_entity(eroot, n_verts=70000)
    bad("ENTD-02", entd_ctx(eroot), ENT)


def test_rule_ENTD_03_pass(eroot):
    write_entity(eroot)
    ok("ENTD-03", entd_ctx(eroot), ENT)


def test_rule_ENTD_03_fail(eroot):
    write_entity(eroot, doc_edit=lambda d: d["nodes"][0].update(translation=[1.0, 0.0, 0.0]))
    bad("ENTD-03", entd_ctx(eroot), ENT)


def test_rule_ENTD_04_pass(eroot):
    write_entity(eroot)
    ok("ENTD-04", entd_ctx(eroot), ENT)


def test_rule_ENTD_04_fail(eroot):
    write_entity(eroot, pos=BOX + np.array([0, 0.1, 0], dtype=np.float32))
    bad("ENTD-04", entd_ctx(eroot), ENT)


def test_rule_ENTD_05_pass(eroot):
    write_entity(eroot)
    ok("ENTD-05", entd_ctx(eroot), ENT)


def test_rule_ENTD_05_fail(eroot):
    write_entity(eroot, bbox_extra=0.5)
    bad("ENTD-05", entd_ctx(eroot), ENT)


def test_rule_ENTD_06_pass(eroot):
    write_entity(eroot)
    ok("ENTD-06", entd_ctx(eroot), ENT)


def test_rule_ENTD_06_fail(eroot):
    nrm = np.tile(np.array([0, 2.0, 0], dtype=np.float32), (8, 1))
    write_entity(eroot, nrm=nrm)
    bad("ENTD-06", entd_ctx(eroot), ENT)


def test_entd_skip_with_flag_and_fail_when_glbs_missing(tmp_path):
    r = RULES["ENTD-01"].check(Context(root=tmp_path, aoi=AOI, entity_lods=config.load_entity_lods(ROOT),
                                       options={"skip_entities": True}), ENT)
    assert r.status == "SKIP" and "--skip-entities" in r.message
    r = RULES["ENTD-01"].check(entd_ctx(tmp_path), ENT)   # no GLBs and no flag: nothing to approve
    assert r.status == "FAIL" and "tilepipe entities" in r.fix_hint


# ---------------------------------------------------------------- runner outputs

def test_runner_writes_json_and_junit_and_exits_1_on_forced_failure(clone):
    edit_json(clone, f"build/{AOI}/geo.json", lambda d: d.update(E0=d["E0"] + 5))   # forces GEO-03 to fail
    code = runner.run(clone, AOI, skip_entities=True)
    assert code == 1
    doc = json.loads((dist(clone) / "validation.json").read_text(encoding="utf-8"))
    assert config.schema_errors(doc, "validation") == []
    by = {(r["rule"], r["scope"]): r for r in doc["results"]}
    assert by["GEO-03", "tile"]["status"] == "FAIL"
    assert {r["status"] for r in doc["results"] if r["rule"].startswith("ENT-")} == {"SKIP"}
    assert all(r["status"] == "SKIP" and r["message"] for r in doc["results"] if r["rule"] in ("SCN-04", "PERF-01"))
    assert set(doc["results"][0]) == {"rule", "severity", "status", "scope", "measured", "limit", "unit", "message", "fix_hint"}
    xml = ET.parse(clone / "build" / AOI / "validation.junit.xml").getroot()
    suites = {s.get("name"): s for s in xml.iter("testsuite")}
    assert set(suites) == set(doc["summary"])
    cases = {c.get("name"): c for c in suites["tile"].iter("testcase")}
    assert cases["GEO-03"].find("failure") is not None
    assert cases["GEO-03"].find("failure").get("message").startswith("GEO-03 FAIL tile: measured ")


def test_runner_turns_a_missing_input_into_a_fail(clone):
    (dist(clone) / "terrain_height.rg8.bin").unlink()
    recs = runner.run_rules(make_ctx(clone, skip_entities=True))
    r = next(x for x in recs if x["rule"] == "TEX-04")
    assert r["status"] == "FAIL" and "terrain_height" in r["message"]
