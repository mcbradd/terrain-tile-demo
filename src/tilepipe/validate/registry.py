"""Rule registry and result record (SPEC 12.1). Frozen after WP02.

`CATALOG` declares every rule ID of SPEC 12 with severity, scope kind, and doc line. Each starts as a stub that
returns SKIP. Rule modules (`rules_*.py`) attach the real check with `@implements("TER-01")`, which replaces the stub.

A check has the signature `check(ctx: Context, scope: str) -> Result` and is called once per scope of its kind.
"""
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

SEVERITIES = ("FAIL", "WARN")
STATUSES = ("PASS", "FAIL", "WARN", "SKIP")
SCOPE_KINDS = ("tile", "profile", "entity", "fixture", "repo")  # scopes: tile, profile:<n>, entity:<id>, ...


@dataclass(frozen=True)
class Result:
    """One result record. Field set and order are those of SPEC 12.1 and validation.schema.json."""
    rule: str
    severity: str
    status: str
    scope: str
    measured: float | int | str | bool | None
    limit: float | int | str | bool | None
    unit: str
    message: str
    fix_hint: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Context:
    """What a check reads. `root` is the repo root; `aoi` the tile id; `profiles` and `looks` the loaded configs.
    `options` carries CLI flags (`skip_entities`, `determinism`, `no_blender`). `cache` is free for the runner and
    rules to memoize loaded artifacts (tile.json, decoded textures, parsed GLBs) by any string key."""
    root: Path
    aoi: str
    profiles: dict = field(default_factory=dict)
    looks: dict = field(default_factory=dict)
    entity_lods: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)


Check = Callable[[Context, str], Result]


@dataclass
class Rule:
    id: str
    severity: str
    scope_kind: str
    doc: str
    check: Check
    stub: bool = True


def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def result(rule_id: str, scope: str, status: str, measured, limit, unit: str = "", op: str = "<=",
           fix_hint: str = "") -> Result:
    """Build a record whose message follows SPEC 12.1:
    `<RULE> <STATUS> <scope>: measured <value> <unit>, limit <op> <limit> <unit>. <fix hint>`"""
    r = RULES[rule_id]
    if status not in STATUSES:
        raise ValueError(f"bad status {status!r}")
    u = f" {unit}" if unit else ""
    msg = f"{rule_id} {status} {scope}: measured {_fmt(measured)}{u}, limit {op} {_fmt(limit)}{u}."
    if fix_hint:
        msg += f" {fix_hint}"
    return Result(rule_id, r.severity, status, scope, measured, limit, unit, msg, fix_hint)


def check_result(rule_id: str, scope: str, ok: bool, measured, limit, unit: str = "", op: str = "<=",
                 fix_hint: str = "") -> Result:
    """PASS if `ok`, else FAIL or WARN per the rule's severity. The fix hint is kept only on non-PASS."""
    status = "PASS" if ok else RULES[rule_id].severity
    return result(rule_id, scope, status, measured, limit, unit, op, "" if ok else fix_hint)


def skip(rule_id: str, scope: str, reason: str) -> Result:
    """SKIP record. SPEC 12.1: a SKIP always carries a reason. Message: `<RULE> SKIP <scope>: <reason>.`"""
    if not reason:
        raise ValueError("SKIP needs a reason")
    r = RULES[rule_id]
    return Result(rule_id, r.severity, "SKIP", scope, None, None, "", f"{rule_id} SKIP {scope}: {reason}.", "")


def _stub(rule_id: str) -> Check:
    return lambda ctx, scope: skip(rule_id, scope, "not implemented")


# (id, severity, scope kind, doc). ENT rules run inside Blender (blender/tilepipe_tools/rules.py mirrors this
# shape); they are listed here so the core report carries them. Their scope kind `entity` also covers fixtures.
CATALOG = [
    ("META-01", "FAIL", "profile", "Derived budgets equal floor(anchor * share); terrain, entities, reserve sum to 1.0"),
    ("META-02", "WARN", "tile", "tilepipe build wall-clock is at most 120 s"),
    ("META-03", "FAIL", "repo", "Config files, tile.json, entity.json files, validation.json validate against schemas"),
    ("META-04", "FAIL", "repo", "entity_lods tris_max within 2 * px^2 / min_triangle_area_px; profile LOD indices exist"),
    ("DET-01", "FAIL", "tile", "Two consecutive builds produce identical outputs.sha256"),
    ("OFF-01", "FAIL", "repo", "tilepipe all succeeds with TILEPIPE_OFFLINE=1"),
    ("REG-01", "FAIL", "repo", "Every rule ID is registered and has a passing and a failing test case"),
    ("GEO-01", "FAIL", "tile", "Registration of H_full against the source crop: median <= 0.5 m, p95 <= 5.0 m"),
    ("GEO-02", "FAIL", "tile", "MGRS digits match UTM at center and four inner corners; one zone and square"),
    ("GEO-03", "FAIL", "tile", "E0 and N0 are multiples of 10"),
    ("TER-01", "FAIL", "profile", "terrain_tris <= terrain_tris_max"),
    ("TER-02", "FAIL", "tile", "Chunk LOD vertex and triangle counts match 7.2; batch tris equal sum of chunks"),
    ("TER-03", "FAIL", "tile", "Indices below vertex count; uint16 exactly when vertices <= 65,535"),
    ("TER-04", "FAIL", "profile", "Batch surface vertex y matches decoded height texture within 0.10 m"),
    ("TER-05", "FAIL", "tile", "Skirts wind outward and sit D_k below surface, or at h_min - 100 on tile border"),
    ("TER-06", "FAIL", "tile", "Every surface triangle has normal y > 0"),
    ("TER-07", "FAIL", "tile", "Per chunk, e_max is non-decreasing in k and 0 at LOD 0"),
    ("TER-08", "FAIL", "profile", "Re-running 7.6 on lod_stats.json reproduces selection, e_star, budget_forced"),
    ("TER-09", "WARN", "profile", "error_px_nominal is at most 4.0"),
    ("TER-10", "FAIL", "tile", "Manifest aabb values equal GLB bounds within 0.001 m"),
    ("TER-11", "FAIL", "tile", "Adjacent chunks' shared LOD 0 border vertices are bitwise identical"),
    ("TEX-01", "FAIL", "profile", "texture_bytes <= texture_bytes_max; files are 2,097,152 and 5,592,404 bytes"),
    ("TEX-02", "FAIL", "tile", "Power-of-two dims within max_texture_dim; mip levels and file bytes as declared"),
    ("TEX-03", "FAIL", "tile", "Decoded level 0 (nx, nz) length at most 1 + 1/127"),
    ("TEX-04", "FAIL", "tile", "Decoded level 0 height within (h_max - h_min) / 65535 of the tile cells"),
    ("TEX-05", "FAIL", "profile", "terrain.frag.glsl fetch count matches its comment and terrain_tex_samples_max"),
    ("GLB-01", "FAIL", "tile", "Khronos validator reports 0 errors and 0 warnings for every GLB under dist/"),
    ("GLB-02", "FAIL", "tile", "Terrain GLBs: one mesh, one primitive, POSITION only, no material"),
    ("PAY-01", "FAIL", "profile", "web_payload_bytes <= web_payload_bytes_max"),
    ("LOOK-01", "FAIL", "repo", "Every ramp stop has OKLCH chroma at most 0.040"),
    ("LOOK-02", "FAIL", "repo", "Line contrast ratios at every ramp stop meet the minor, index, grid minimums"),
    ("LOOK-03", "FAIL", "repo", "Additive darkest stop luminance >= 0.020 and brightest <= 0.600"),
    ("LOOK-04", "FAIL", "repo", "Line colors and entity base colors have OKLCH chroma at most 0.020"),
    ("LOOK-05", "FAIL", "tile", "Every placed instance has CR >= 2.00 against terrain in both looks"),
    ("ENT-01", "FAIL", "entity", "Collection, object, mesh, material names follow 6.6; exactly LOD 0, 1, 2"),
    ("ENT-02", "FAIL", "entity", "Scene units METRIC and scale_length == 1.0"),
    ("ENT-03", "FAIL", "entity", "Objects at identity transform within 1e-6 and unparented"),
    ("ENT-04", "FAIL", "entity", "Triangles within entity_lods.toml limits per LOD and at least 1"),
    ("ENT-05", "FAIL", "entity", "Each LOD has at most half the triangles of the LOD above it"),
    ("ENT-06", "FAIL", "entity", "Largest bounding dimension between 0.3 m and 30.0 m"),
    ("ENT-07", "FAIL", "entity", "LOD 1 and 2 bounds within 2% of LOD 0's largest dimension"),
    ("ENT-08", "FAIL", "entity", "Bounds min Z within 0.005 m of 0; X and Y centered within 1%"),
    ("ENT-09", "FAIL", "entity", "No ngons, no loose geometry, no face area below 1e-8 m^2"),
    ("ENT-10", "FAIL", "entity", "One shared Principled BSDF material slot, no image textures"),
    ("ENT-11", "FAIL", "entity", "Mesh vertex count at most 65,535"),
    ("ENT-12", "FAIL", "entity", "No animation data, shape keys, or armature modifiers"),
    ("ENT-13", "WARN", "entity", "Modifiers are present"),
    ("ENT-14", "FAIL", "entity", "Collection contains only the three mesh objects"),
    ("ENT-15", "FAIL", "entity", "recalc_face_normals flips no face; SKIP if not manifold"),
    ("ENTD-01", "FAIL", "entity", "GLB triangles within LOD limit; one primitive, one material; no images"),
    ("ENTD-02", "FAIL", "entity", "GLB vertex count at most 65,535"),
    ("ENTD-03", "FAIL", "entity", "Mesh node transform is identity"),
    ("ENTD-04", "FAIL", "entity", "POSITION min Y within 0.005 m of 0; X and Z centered within 1%"),
    ("ENTD-05", "FAIL", "entity", "Largest bounding dimension equals the source's within 0.001 m"),
    ("ENTD-06", "FAIL", "entity", "NORMAL accessor exists; every normal has length within 0.01 of 1"),
    ("SCN-01", "FAIL", "profile", "Entity tris <= entity_tris_max; terrain + entities + 16 stem tris <= frame_tris_max"),
    ("SCN-02", "FAIL", "profile", "terrain_draws + 3 entity draws + 1 stem draw <= draw_calls_max"),
    ("SCN-03", "FAIL", "tile", "Scene file equals a fresh run of 7.7 and satisfies placement constraints"),
    ("SCN-04", "FAIL", "profile", "Viewer live counts equal static counts (bench.json); SKIP if absent"),
    ("SCN-05", "WARN", "profile", "Instance mesh height within 2 mm on the table of true height at V = 1.5"),
    ("PERF-01", "WARN", "tile", "Smoke: at most 2% of frames longer than 1.5 x median (bench.json); SKIP if absent"),
]

RULES: dict[str, Rule] = {rid: Rule(rid, sev, kind, doc, _stub(rid)) for rid, sev, kind, doc in CATALOG}


def implements(rule_id: str) -> Callable[[Check], Check]:
    """Decorator: attach the real check to a catalogued rule. Unknown IDs are an error (no rule outside SPEC 12)."""
    if rule_id not in RULES:
        raise KeyError(f"{rule_id} is not in the SPEC 12 catalog")

    def deco(fn: Check) -> Check:
        RULES[rule_id].check, RULES[rule_id].stub = fn, False
        return fn
    return deco


def stubs() -> list[str]:
    """IDs still without a real check. WP07 and WP11 drive this to empty for their rules."""
    return [r.id for r in RULES.values() if r.stub]
