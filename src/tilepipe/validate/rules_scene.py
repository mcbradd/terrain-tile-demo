"""Scene rules (SPEC 12.8): SCN-01 to SCN-05, PERF-01."""
import json

import numpy as np

from tilepipe import scene
from tilepipe.config import GuardError, RuleFailure
from tilepipe.validate import common
from tilepipe.validate.common import CHUNK_CELLS, TILE_M, lod_counts
from tilepipe.validate.registry import check_result, implements, skip

STEM_TRIS, ENTITY_DRAWS, STEM_DRAWS = 16, 3, 1
MAX_SLOPE_DEG, MAX_T, MIN_SPACING_M, EDGE_CELLS = 8.0, 0.45, 400.0, 30
SCN05_TABLE_M, SCN05_V = 0.002, 1.5
PERF_LONG_FRACTION_MAX = 0.02
PER_ENTITY, UAS_HOVER_M = 8, 0.020   # 7.7
# bench.json (13.8) field names are not fixed by the spec; these are the names this validator reads. See D-07.
BENCH_PROFILE_KEYS = ("profiles",)
BENCH_FRACTION_KEY = "frac_longer_than_1p5_median"


def _name(scope: str) -> str:
    return scope.split(":", 1)[1]


def instance_tris(ctx, entity: str, lod: int, strict: bool) -> int:
    """Triangles of one instance. entity.json when exported; else the entity_lods.toml limit, an upper bound (8.4)."""
    f = common.entity_dir(ctx, entity) / "entity.json"
    if f.exists():
        return int(common.jload(ctx, f)["lods"][lod]["tris"])
    if strict:
        raise FileNotFoundError(common.rel(ctx, f))
    return int(ctx.entity_lods["lod"][lod]["tris_max"])


def static_counts(ctx, name: str, strict: bool = False) -> tuple[int, int, int]:
    """(entity tris, frame tris, draws) for one profile (12.8 SCN-01 and SCN-02)."""
    entry = common.tile(ctx)["profiles"][name]
    ents = sum(instance_tris(ctx, i["entity"], entry["entity_lod"], strict) for i in common.scene_doc(ctx)["instances"])
    return ents, entry["terrain_tris"] + ents + STEM_TRIS, entry["terrain_draws"] + ENTITY_DRAWS + STEM_DRAWS


@implements("SCN-01")
def scn01(ctx, scope):
    name = _name(scope)
    budget = ctx.profiles[name]["budget"]
    ents, frame, _ = static_counts(ctx, name)
    return common.multi("SCN-01", scope, [("entity tris", ents, budget["entity_tris_max"], "<="),
                                          ("frame tris", frame, budget["frame_tris_max"], "<=")],
                        "Lower the entity LOD or the terrain budget in the profile.")


@implements("SCN-02")
def scn02(ctx, scope):
    name = _name(scope)
    draws = static_counts(ctx, name)[2]
    return check_result("SCN-02", scope, draws <= ctx.profiles[name]["budget"]["draw_calls_max"], draws,
                        ctx.profiles[name]["budget"]["draw_calls_max"], "draws", "<=",
                        "Use a coarser terrain_batch in the profile.")


def placement_problems(ctx) -> list[str]:
    g, doc = common.geo_json(ctx), common.scene_doc(ctx)
    h = common.h_full(ctx).astype(np.float64)
    cells = h[64:1088, 64:1088]
    dhdx = (h[64:1088, 65:1089] - h[64:1088, 63:1087]) / 20
    dhdz = (h[65:1089, 64:1088] - h[63:1087, 64:1088]) / 20
    slope = np.degrees(np.arccos(1 / np.sqrt(1 + dhdx ** 2 + dhdz ** 2)))
    bad, xz = [], []
    order = [e for e in common.tile(ctx)["entities"] for _ in range(PER_ENTITY)]
    if [i["entity"] for i in doc["instances"]] != order:
        bad.append("instances are not 8 each of vehicle, mast, UAS in order")
    for n, i in enumerate(doc["instances"]):
        r, c = i["cell"]
        t = (cells[r, c] - g["h_min"]) / (g["h_max"] - g["h_min"])
        tag = f"instance {n} ({i['entity']} at cell {r},{c})"
        if not (EDGE_CELLS <= r < 1024 - EDGE_CELLS and EDGE_CELLS <= c < 1024 - EDGE_CELLS):
            bad.append(f"{tag} is within {EDGE_CELLS} cells of the tile edge")
        if slope[r, c] > MAX_SLOPE_DEG:
            bad.append(f"{tag} sits on a {slope[r, c]:.1f} degree slope")
        if t > MAX_T:
            bad.append(f"{tag} has normalized height {t:.3f}")
        if (i["x"], i["z"]) != (10.0 * c + 5, 10.0 * r + 5):
            bad.append(f"{tag} x and z do not match its cell")
        if not 0 <= i["heading_deg"] < 360:
            bad.append(f"{tag} heading {i['heading_deg']}")
        if i["hover_table_m"] != (UAS_HOVER_M if "_uas_" in i["entity"] else 0.0):
            bad.append(f"{tag} hover_table_m {i['hover_table_m']}")
        if xz and np.hypot(*(np.array(xz) - (i["x"], i["z"])).T).min() < MIN_SPACING_M:
            bad.append(f"{tag} is closer than {MIN_SPACING_M:g} m to another instance")
        xz.append((i["x"], i["z"]))
    return bad


@implements("SCN-03")
def scn03(ctx, scope):
    bad = []
    path = ctx.root / "scene" / f"{ctx.aoi}_scene.json"
    if not path.exists():
        bad.append(f"{common.rel(ctx, path)} is missing")
    else:
        try:   # scene.run regenerates in memory and raises unless the committed file is identical (7.7)
            scene.run(ctx.root, ctx.aoi)
        except (RuleFailure, GuardError) as e:
            bad.append(str(e))
        copy = common.dist(ctx) / "scene.json"
        if not copy.exists() or copy.read_bytes() != path.read_bytes():
            bad.append("dist scene.json is not a byte copy of the scene file")
        bad += placement_problems(ctx)
    return common.violations("SCN-03", scope, bad, "defects", "Run `uv run tilepipe scene --regen` if the change is intended.")


@implements("SCN-04")
def scn04(ctx, scope):
    name = _name(scope)
    f = common.build(ctx) / "bench.json"
    if not f.exists():
        return skip("SCN-04", scope, f"{common.rel(ctx, f)} is absent; the viewer's bench mode writes it (13.8)")
    doc = json.loads(f.read_text(encoding="utf-8"))
    live = next((doc[k][name] for k in BENCH_PROFILE_KEYS if name in doc.get(k, {})), doc.get(name))
    if not isinstance(live, dict) or "live_tris" not in live or "live_draws" not in live:
        return check_result("SCN-04", scope, False, "no live counts", f"live_tris and live_draws for {name}", "", "==",
                            "Rerun the viewer's bench mode and save bench.json (13.8).")
    _, tris, draws = static_counts(ctx, name, strict=True)
    return common.multi("SCN-04", scope, [("tris, viewer", live["live_tris"], tris, "=="),
                                          ("draws, viewer", live["live_draws"], draws, "==")],
                        "The viewer draws something the static counts do not account for (13.8).")


def mesh_height(pos: np.ndarray, k: int, lx: float, lz: float) -> float:
    """Height of the chunk LOD k surface at chunk-local (lx, lz) meters, on its actual triangles (6.4)."""
    n = lod_counts(k)[0]
    step = 10.0 * (1 << k)
    i = min(int(lx // step), n - 2)
    j = min(int(lz // step), n - 2)
    u, v = lx / step - i, lz / step - j
    y = pos[:n * n, 1].reshape(n, n).astype(np.float64)
    ha, hb, hc, hd = y[j, i], y[j, i + 1], y[j + 1, i], y[j + 1, i + 1]
    return ha + u * (hb - ha) + v * (hc - ha) if u + v <= 1 else hd + (1 - u) * (hc - hd) + (1 - v) * (hb - hd)


@implements("SCN-05")
def scn05(ctx, scope):
    name = _name(scope)
    entry = common.tile(ctx)["profiles"][name]
    h = common.h_full(ctx)
    limit = SCN05_TABLE_M * 8000 / SCN05_V
    worst = 0.0
    for inst in common.scene_doc(ctx)["instances"]:
        x, z = inst["x"], inst["z"]
        cx, cz = min(int(x // (CHUNK_CELLS * 10)), 3), min(int(z // (CHUNK_CELLS * 10)), 3)
        cid = f"c{cx}_{cz}"
        k = entry["selection"][cid]
        pos = common.mesh(ctx, common.dist(ctx) / f"terrain_{cid}_lod{k}.glb")[0]
        drawn = mesh_height(pos, k, x - cx * CHUNK_CELLS * 10, z - cz * CHUNK_CELLS * 10)
        true = float(common.bilinear(h.astype(np.float64), np.array([64 + x / 10 - 0.5]), np.array([64 + z / 10 - 0.5]))[0])
        worst = max(worst, abs(drawn - true))
    return check_result("SCN-05", scope, worst <= limit, round(worst, 4), round(limit, 4), "m of ground", "<=",
                        "Tokens sit on the drawn mesh; this reports how far that is from true ground (12.8).")


@implements("PERF-01")
def perf01(ctx, scope):
    f = common.build(ctx) / "bench.json"
    if not f.exists():
        return skip("PERF-01", scope, f"{common.rel(ctx, f)} is absent; the viewer's bench mode writes it (13.8)")
    doc = json.loads(f.read_text(encoding="utf-8"))
    per = {n: p for k in BENCH_PROFILE_KEYS for n, p in doc.get(k, {}).items()} or {n: p for n, p in doc.items() if isinstance(p, dict)}
    fr = {n: p[BENCH_FRACTION_KEY] for n, p in per.items() if isinstance(p, dict) and BENCH_FRACTION_KEY in p}
    if not fr:
        return check_result("PERF-01", scope, False, f"no {BENCH_FRACTION_KEY}", "present", "", "==",
                            "Rerun the viewer's bench mode and save bench.json (13.8).")
    worst = max(fr.items(), key=lambda kv: kv[1])
    return check_result("PERF-01", scope, worst[1] <= PERF_LONG_FRACTION_MAX, round(worst[1], 4), PERF_LONG_FRACTION_MAX,
                        "of frames", "<=", f"Smoke only, measured on the build machine; worst profile {worst[0]}.")
