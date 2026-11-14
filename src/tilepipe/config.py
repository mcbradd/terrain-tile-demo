"""Shared contract helpers: exit-code errors (SPEC 4.3), config loaders with schema checks, canonical JSON (6.7).

Frozen after WP02. Every AOI, profile, LOD, and look value comes from the committed files via these loaders.
"""
import json
import math
import tomllib
from functools import cache
from pathlib import Path

import jsonschema

SCHEMA_DIR = Path(__file__).parent / "schema"
STAGES = ("prep", "lod", "bake", "export", "batch", "scene", "manifest")  # SPEC 7, in run order


class TilepipeError(Exception):
    """Base error. `code` is the process exit code of SPEC 4.3."""
    code = 2


class UsageError(TilepipeError):
    """Usage or configuration error, including schema-invalid config. Exit 2."""
    code = 2


class RuleFailure(TilepipeError):
    """A FAIL-severity check failed (also: scene mismatch 7.7, budget unreachable 7.6). Exit 1."""
    code = 1


class EnvError(TilepipeError):
    """Environment or preflight failure. Exit 3."""
    code = 3


class GuardError(TilepipeError):
    """Data guard failure (5.5). Exit 4. The message carries the measured value and the expected range."""
    code = 4

    def __init__(self, guard: str, measured, expected):
        super().__init__(f"{guard} FAIL: measured {measured}, expected {expected}")
        self.guard, self.measured, self.expected = guard, measured, expected


# ---------------------------------------------------------------- schemas

@cache
def load_schema(name: str) -> dict:
    """`name` is the schema stem: tile, validation, profile, entity, look, aois."""
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def schema_errors(instance, name: str) -> list[str]:
    """All schema violations of `instance` against `<name>.schema.json`, as `path: message` lines. Empty if valid."""
    v = jsonschema.Draft202012Validator(load_schema(name))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
            for e in sorted(v.iter_errors(instance), key=lambda e: list(map(str, e.absolute_path)))]


def check_schema(instance, name: str, what: str) -> None:
    """Raise UsageError (exit 2) listing every violation if `instance` is invalid."""
    errs = schema_errors(instance, name)
    if errs:
        raise UsageError(f"{what} is invalid against {name}.schema.json:\n  " + "\n  ".join(errs))


# ---------------------------------------------------------------- config loaders

def _toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UsageError(f"missing config file: {path.name}") from None
    except tomllib.TOMLDecodeError as e:
        raise UsageError(f"{path.name}: {e}") from None


def load_aois(root: Path) -> dict[str, dict]:
    """`aois.toml` as {aoi_id: aoi}, schema-checked. Order is file order."""
    aois = _toml(root / "aois.toml")
    check_schema(aois, "aois", "aois.toml")
    return aois


def default_aoi(root: Path) -> str:
    """The first AOI of aois.toml (`anza_borrego_01`). Read from the file so no AOI id lives in code (17.14)."""
    return next(iter(load_aois(root)))


def load_aoi(root: Path, aoi: str) -> dict:
    """One AOI record of aois.toml, plus `id`. Unknown AOI is a usage error."""
    aois = load_aois(root)
    if aoi not in aois:
        raise UsageError(f"unknown AOI {aoi!r}; aois.toml defines {', '.join(aois)}")
    return {"id": aoi, **aois[aoi]}


def load_profile(path: Path) -> dict:
    p = _toml(path)
    check_schema(p, "profile", path.name)
    if p["name"] != path.stem:
        raise UsageError(f"{path.name}: name {p['name']!r} does not match the file name")
    return p


def load_profiles(root: Path) -> dict[str, dict]:
    """Every `profiles/*.toml` as {name: profile}, sorted by name, schema-checked."""
    files = sorted((root / "profiles").glob("*.toml"))
    if not files:
        raise UsageError("no profiles/*.toml found")
    return {f.stem: load_profile(f) for f in files}


def load_entity_lods(root: Path) -> dict:
    """`entity_lods.toml`. `lods[n]` is the record for LOD n."""
    d = _toml(root / "entity_lods.toml")
    try:
        ok = d["schema"] == 1 and [l["n"] for l in d["lod"]] == list(range(len(d["lod"])))
        for l in d["lod"]:
            float(l["view_distance_m"]), float(l["ppd"]), int(l["tris_max"])
        float(d["token_table_size_m"]), float(d["min_triangle_area_px"])
    except (KeyError, TypeError, ValueError) as e:
        raise UsageError(f"entity_lods.toml: malformed ({e!r})") from None
    if not ok:
        raise UsageError("entity_lods.toml: schema must be 1 and [[lod]] n must run 0, 1, 2 in order")
    return d


def load_looks(root: Path) -> dict[str, dict]:
    """Every `look/*.json` as {mode: look}, sorted by mode, schema-checked. Colors stay sRGB hex here."""
    out = {}
    for f in sorted((root / "look").glob("*.json")):
        look = json.loads(f.read_text(encoding="utf-8"))
        check_schema(look, "look", f"look/{f.name}")
        if look["mode"] != f.stem:
            raise UsageError(f"look/{f.name}: mode {look['mode']!r} does not match the file name")
        out[f.stem] = look
    if not out:
        raise UsageError("no look/*.json found")
    return out


# ---------------------------------------------------------------- paths

def build_dir(root: Path, aoi: str) -> Path:
    return root / "build" / aoi


def dist_dir(root: Path, aoi: str) -> Path:
    return root / "dist" / aoi


# ---------------------------------------------------------------- canonical JSON (6.7)

def _round(obj):
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError("NaN or Infinity cannot be written (SPEC 6.7)")
        return round(obj, 6)
    if isinstance(obj, dict):
        return {str(k): _round(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v) for v in obj]
    return obj


def dumps_json(obj) -> str:
    """UTF-8 text, keys sorted, two-space indent, floats round(x, 6), no NaN or Infinity, trailing LF."""
    return json.dumps(_round(obj), sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps_json(obj).encode("utf-8"))
