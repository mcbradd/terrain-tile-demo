"""Source gate: rules ENT-01 to ENT-15 (SPEC 12.6) as pure functions from Blender objects to result records.

A record holds the fields of SPEC 12.1 in the order of `tilepipe.validate.registry.Result`, plus an `object` key
that names the offending object so the panel can select it. `strip()` drops that key before records are written.
The panel and the headless scripts call the same functions. Imports: standard library, bmesh, numpy (SPEC 3.3).
"""
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import bmesh
import numpy as np

FIELDS = ("rule", "severity", "status", "scope", "measured", "limit", "unit", "message", "fix_hint")
SEVERITY = {f"ENT-{i:02d}": ("WARN" if i == 13 else "FAIL") for i in range(1, 16)}
NAME_RE = re.compile(r"^ent_[a-z0-9]+_[a-z0-9]+_[a-z0-9]+$")   # 6.6
LOD_RE = re.compile(r"lod(\d+)$", re.IGNORECASE)                 # LOD index for geometry rules; ENT-01 checks names
TRANSFORM_TOL = 1e-6        # ENT-03
MAX_VERTS = 65535           # ENT-11
SIZE_MIN_M, SIZE_MAX_M = 0.3, 30.0   # ENT-06
DRIFT_FRAC = 0.02           # ENT-07
GROUND_TOL_M = 0.005        # ENT-08
CENTER_FRAC = 0.01          # ENT-08
MIN_FACE_AREA = 1e-8        # ENT-09
NO_LODS = "No mesh object with an LOD suffix in the collection."


# ------------------------------------------------------------------ records (SPEC 12.1 message format)

def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def record(rule: str, scope: str, status: str, measured, limit, unit: str = "", op: str = "<=",
           fix_hint: str = "", obj: str = "") -> dict:
    u = f" {unit}" if unit else ""
    msg = f"{rule} {status} {scope}: measured {_fmt(measured)}{u}, limit {op} {_fmt(limit)}{u}."
    if fix_hint:
        msg += f" {fix_hint}"
    return {"rule": rule, "severity": SEVERITY[rule], "status": status, "scope": scope, "measured": measured,
            "limit": limit, "unit": unit, "message": msg, "fix_hint": fix_hint, "object": obj}


def check(rule: str, scope: str, ok: bool, measured, limit, unit: str = "", op: str = "<=", fix_hint: str = "",
          obj: str = "") -> dict:
    """PASS if `ok`, else the rule's severity. The fix hint and object are kept only on non-PASS."""
    if ok:
        return record(rule, scope, "PASS", measured, limit, unit, op)
    return record(rule, scope, SEVERITY[rule], measured, limit, unit, op, fix_hint, obj)


def skip(rule: str, scope: str, reason: str, obj: str = "") -> dict:
    return {"rule": rule, "severity": SEVERITY[rule], "status": "SKIP", "scope": scope, "measured": None,
            "limit": None, "unit": "", "message": f"{rule} SKIP {scope}: {reason}.", "fix_hint": "", "object": obj}


def strip(rec: dict) -> dict:
    """The 12.1 record without the panel-only `object` key, floats rounded to 6 places (6.7)."""
    return {k: round(rec[k], 6) if isinstance(rec[k], float) else rec[k] for k in FIELDS}


def failed(records: list[dict]) -> list[str]:
    return [r["rule"] for r in records if r["status"] == "FAIL"]


def _first_failing(rule: str, a: "Asset", items: list[tuple], unit: str = "") -> dict:
    """items: (ok, measured, limit, op, object name, fix hint). Reports the first failing item, else the first."""
    if not items:
        return check(rule, a.scope, False, 0, 3, "", "==", NO_LODS)
    ok, measured, limit, op, obj, hint = next((i for i in items if not i[0]), items[0])
    return check(rule, a.scope, ok, measured, limit, unit, op, hint, obj)


# ------------------------------------------------------------------ configuration (tomllib, SPEC 11.4)

def load_entity_lods(repo_root: Path) -> dict:
    return tomllib.loads((Path(repo_root) / "entity_lods.toml").read_text(encoding="utf-8"))


def tris_limits(entity_lods: dict) -> list[int]:
    return [int(lod["tris_max"]) for lod in sorted(entity_lods["lod"], key=lambda lod: lod["n"])]


def load_profiles(repo_root: Path) -> dict[str, dict]:
    return {p.stem: tomllib.loads(p.read_text(encoding="utf-8"))
            for p in sorted((Path(repo_root) / "profiles").glob("*.toml"))}


# ------------------------------------------------------------------ the asset under test

@dataclass
class Asset:
    """One entity collection with what the rules read. `tris_max[n]` comes from entity_lods.toml."""
    coll: object
    scene: object
    depsgraph: object
    tris_max: list[int]
    scope: str
    _counts: dict = field(default_factory=dict)

    @property
    def meshes(self) -> list:
        return sorted((o for o in self.coll.all_objects if o.type == "MESH"), key=lambda o: o.name)

    @property
    def lods(self) -> dict[int, object]:
        out = {}
        for o in self.meshes:
            m = LOD_RE.search(o.name)
            if m:
                out.setdefault(int(m.group(1)), o)
        return dict(sorted(out.items()))

    def counts(self, obj) -> tuple[int, int]:
        """(triangles, vertices) of the evaluated mesh, triangles by calc_loop_triangles (SPEC 12.6)."""
        if obj.name not in self._counts:
            ev = obj.evaluated_get(self.depsgraph)
            me = ev.to_mesh()
            try:
                me.calc_loop_triangles()
                self._counts[obj.name] = (len(me.loop_triangles), len(me.vertices))
            finally:
                ev.to_mesh_clear()
        return self._counts[obj.name]


def bounds(me) -> tuple[np.ndarray, np.ndarray] | None:
    """Object-local (min, max) of mesh data vertices, or None for an empty mesh."""
    n = len(me.vertices)
    if n == 0:
        return None
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3).astype(np.float64)
    return co.min(axis=0), co.max(axis=0)


def _dims(obj) -> np.ndarray | None:
    b = bounds(obj.data)
    return None if b is None else b[1] - b[0]


# ------------------------------------------------------------------ rules

def ent01(a: Asset) -> dict:
    c = a.coll.name
    errs = [] if NAME_RE.match(c) else [f"collection {c}"]
    want = {f"{c}_LOD{n}" for n in range(3)}
    have = {o.name for o in a.meshes}
    errs += [f"missing {w}" for w in sorted(want - have)]
    errs += [f"object {n}" for n in sorted(have - want)]
    errs += [f"mesh {o.data.name} on {o.name}" for o in a.meshes if o.data.name != o.name]
    mats = {s.material.name for o in a.meshes for s in o.material_slots if s.material}
    errs += [f"material {m}" for m in sorted(mats - {f"M_{c}"})]
    bad = next((o.name for o in a.meshes if o.name not in want), "")
    return check("ENT-01", a.scope, not errs, len(errs), 0, "", "<=",
                 f"Follow 6.6 names: {'; '.join(errs)}.", bad)


def ent02(a: Asset) -> dict:
    us = a.scene.unit_settings
    ok = us.system == "METRIC" and us.scale_length == 1.0
    return check("ENT-02", a.scope, ok, float(us.scale_length), 1.0, "", "==",
                 f"Set unit system METRIC (is {us.system}) and unit scale 1.0.")


def ent03(a: Asset) -> dict:
    items = []
    for o in a.meshes:
        dev = float(np.abs(np.array(o.matrix_basis) - np.eye(4)).max())   # location, rotation, scale
        hint = f"Clear the parent of {o.name}." if o.parent else f"Apply all transforms on {o.name}."
        items.append((dev <= TRANSFORM_TOL and o.parent is None, dev, TRANSFORM_TOL, "<=", o.name, hint))
    return _first_failing("ENT-03", a, items)


def ent04(a: Asset) -> dict:
    items = []
    for n, o in a.lods.items():
        t = a.counts(o)[0]
        lim = a.tris_max[n] if n < len(a.tris_max) else 0
        if t < 1:
            items.append((False, t, 1, ">=", o.name, f"{o.name} has no triangles."))
        else:
            items.append((t <= lim, t, lim, "<=", o.name, f"Reduce {o.name} to at most {lim} triangles."))
    return _first_failing("ENT-04", a, items, "tris")


def ent05(a: Asset) -> dict:
    lods, items = a.lods, []
    for n, o in lods.items():
        if n - 1 in lods:
            t, up = a.counts(o)[0], a.counts(lods[n - 1])[0]
            items.append((t <= up / 2, t, up / 2, "<=", o.name,
                          f"{o.name} needs at most half the triangles of LOD {n - 1}."))
    return _first_failing("ENT-05", a, items, "tris")


def ent06(a: Asset) -> dict:
    items = []
    for o in a.lods.values():
        d = _dims(o)
        size = 0.0 if d is None else float(d.max())
        hint = f"Model {o.name} at real-world scale in meters."
        if size < SIZE_MIN_M:
            items.append((False, size, SIZE_MIN_M, ">=", o.name, hint))
        else:
            items.append((size <= SIZE_MAX_M, size, SIZE_MAX_M, "<=", o.name, hint))
    return _first_failing("ENT-06", a, items, "m")


def ent07(a: Asset) -> dict:
    lods = a.lods
    d0 = _dims(lods[0]) if 0 in lods else None
    if d0 is None:
        return check("ENT-07", a.scope, False, 0, 1, "", ">=", "LOD 0 is missing or empty.")
    lim = DRIFT_FRAC * float(d0.max())
    items = []
    for n in (1, 2):
        if n in lods:
            d = _dims(lods[n])
            diff = float(d0.max()) if d is None else float(np.abs(d - d0).max())
            items.append((diff <= lim, diff, lim, "<=", lods[n].name,
                          f"Keep the bounds of {lods[n].name} equal to LOD 0."))
    return _first_failing("ENT-07", a, items, "m")


def ent08(a: Asset) -> dict:
    lods = a.lods
    d0 = _dims(lods[0]) if 0 in lods else None
    items = []
    for o in lods.values():
        b = bounds(o.data)
        if b is None:
            items.append((False, 0, 1, ">=", o.name, f"{o.name} is empty."))
            continue
        lo, hi = b
        lim = CENTER_FRAC * float((d0 if d0 is not None else hi - lo).max())
        hint = f"Put the origin of {o.name} at the center of the ground footprint, lowest point at Z 0."
        items.append((abs(lo[2]) <= GROUND_TOL_M, abs(float(lo[2])), GROUND_TOL_M, "<=", o.name, hint))
        for axis in (0, 1):
            c = abs(float(lo[axis] + hi[axis]) / 2)
            items.append((c <= lim, c, lim, "<=", o.name, hint))
    return _first_failing("ENT-08", a, items, "m")


def ent09(a: Asset) -> dict:
    total, obj, hint = 0, "", ""
    for o in a.lods.values():
        bm = bmesh.new()
        bm.from_mesh(o.data)
        ngons = sum(len(f.verts) > 4 for f in bm.faces)
        loose_v = sum(not v.link_edges for v in bm.verts)
        loose_e = sum(not e.link_faces for e in bm.edges)
        tiny = sum(f.calc_area() < MIN_FACE_AREA for f in bm.faces)
        bm.free()
        bad = ngons + loose_v + loose_e + tiny
        if bad and not obj:
            obj = o.name
            hint = (f"{o.name}: {ngons} faces over 4 vertices, {loose_v} loose vertices, {loose_e} loose edges, "
                    f"{tiny} faces below 1e-8 m^2.")
        total += bad
    if not a.lods:
        return check("ENT-09", a.scope, False, 0, 3, "", "==", NO_LODS)
    return check("ENT-09", a.scope, total == 0, total, 0, "", "<=", hint, obj)


def _nodes(tree):
    for n in tree.nodes:
        yield n
        if n.bl_idname == "ShaderNodeGroup" and n.node_tree:
            yield from _nodes(n.node_tree)


def ent10(a: Asset) -> dict:
    probs, mats = [], []
    for o in a.lods.values():
        if len(o.material_slots) != 1:
            probs.append((o.name, f"{o.name} has {len(o.material_slots)} material slots"))
        for s in o.material_slots:
            if s.material not in mats:
                mats.append(s.material)
    if len(mats) != 1:
        probs.append(("", f"the LODs use {len(mats)} materials"))
    for m in mats:
        if m is None:
            probs.append(("", "an empty material slot"))
            continue
        nodes = list(_nodes(m.node_tree)) if m.node_tree else []
        if not any(n.bl_idname == "ShaderNodeBsdfPrincipled" for n in nodes):
            probs.append(("", f"{m.name} has no Principled BSDF"))
        if any(n.bl_idname == "ShaderNodeTexImage" for n in nodes):
            probs.append(("", f"{m.name} has an image texture node"))
    if not a.lods:
        return check("ENT-10", a.scope, False, 0, 3, "", "==", NO_LODS)
    obj = next((p[0] for p in probs if p[0]), "")
    return check("ENT-10", a.scope, not probs, len(probs), 0, "", "<=",
                 f"Use one shared Principled BSDF material: {'; '.join(p[1] for p in probs)}.", obj)


def ent11(a: Asset) -> dict:
    items = [(a.counts(o)[1] <= MAX_VERTS, a.counts(o)[1], MAX_VERTS, "<=", o.name,
              f"Reduce the vertex count of {o.name}.") for o in a.lods.values()]
    return _first_failing("ENT-11", a, items, "vertices")


def ent12(a: Asset) -> dict:
    probs = []
    for o in a.lods.values():
        if o.animation_data or o.data.animation_data:
            probs.append((o.name, f"{o.name} has animation data"))
        if o.data.shape_keys:
            probs.append((o.name, f"{o.name} has shape keys"))
        if any(m.type == "ARMATURE" for m in o.modifiers):
            probs.append((o.name, f"{o.name} has an armature modifier"))
    if not a.lods:
        return check("ENT-12", a.scope, False, 0, 3, "", "==", NO_LODS)
    return check("ENT-12", a.scope, not probs, len(probs), 0, "", "<=",
                 f"Remove: {'; '.join(p[1] for p in probs)}.", probs[0][0] if probs else "")


def ent13(a: Asset) -> dict:
    with_mods = [o for o in a.lods.values() if o.modifiers]
    n = sum(len(o.modifiers) for o in a.lods.values())
    return check("ENT-13", a.scope, n == 0, n, 0, "", "<=",
                 "Modifiers are applied on export and counted on the evaluated mesh.",
                 with_mods[0].name if with_mods else "")


def ent14(a: Asset) -> dict:
    objs = list(a.coll.all_objects)
    extra = [o.name for o in objs if o.type != "MESH"] + [f"collection {c.name}" for c in a.coll.children]
    ok = len(objs) == 3 and not extra
    return check("ENT-14", a.scope, ok, len(objs), 3, "", "==",
                 f"Keep only the three LOD meshes in {a.coll.name}; remove {', '.join(extra) or 'extra meshes'}.",
                 next((o.name for o in objs if o.type != "MESH"), ""))


def ent15(a: Asset) -> dict:
    flipped, nonmanifold, obj = 0, [], ""
    for o in a.lods.values():
        bm = bmesh.new()
        bm.from_mesh(o.data)
        if not all(e.is_manifold for e in bm.edges):
            nonmanifold.append(o.name)
            bm.free()
            continue
        bm.normal_update()
        before = [f.normal.copy() for f in bm.faces]
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        bm.normal_update()
        k = sum(b.dot(f.normal) < 0 for b, f in zip(before, bm.faces))
        bm.free()
        if k and not obj:
            obj = o.name
        flipped += k
    if not a.lods:
        return check("ENT-15", a.scope, False, 0, 3, "", "==", NO_LODS)
    if flipped == 0 and nonmanifold:
        return skip("ENT-15", a.scope, f"not manifold: {', '.join(nonmanifold)}", nonmanifold[0])
    return check("ENT-15", a.scope, flipped == 0, flipped, 0, "faces", "<=",
                 f"Recalculate normals outside on {obj}.", obj)


RULES = (ent01, ent02, ent03, ent04, ent05, ent06, ent07, ent08, ent09, ent10, ent11, ent12, ent13, ent14, ent15)


def run_gate(a: Asset) -> list[dict]:
    """Every ENT rule on one asset, in ID order."""
    return [rule(a) for rule in RULES]
