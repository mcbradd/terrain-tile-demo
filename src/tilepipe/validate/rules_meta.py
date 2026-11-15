"""Repository and meta rules (SPEC 12.3): META-01 to META-04, DET-01, OFF-01, REG-01."""
import contextlib
import io
import json
import math
import os
import re
import shutil
import socket
import tempfile
import tomllib
from fractions import Fraction
from pathlib import Path

from tilepipe import config
from tilepipe.validate import common
from tilepipe.validate.registry import RULES, check_result, implements, result, skip

BUILD_SECONDS_MAX = 120.0
_F = lambda v: Fraction(str(v))  # noqa: E731  exact decimal arithmetic for shares

# Every rule ID of SPEC 12, independent of the registry, so REG-01 notices a missing or extra registration.
SPEC_RULE_IDS = sorted(
    [f"META-{i:02d}" for i in range(1, 5)] + ["DET-01", "OFF-01", "REG-01"]
    + [f"GEO-{i:02d}" for i in range(1, 4)] + [f"TER-{i:02d}" for i in range(1, 12)]
    + [f"TEX-{i:02d}" for i in range(1, 6)] + ["GLB-01", "GLB-02", "PAY-01"]
    + [f"LOOK-{i:02d}" for i in range(1, 6)] + [f"ENT-{i:02d}" for i in range(1, 16)]
    + [f"ENTD-{i:02d}" for i in range(1, 7)] + [f"SCN-{i:02d}" for i in range(1, 6)] + ["PERF-01"])
TEST_NAME = re.compile(r"^def test_rule_([A-Z]+)_(\d{2})_(pass|fail)\b", re.M)


@implements("META-01")
def meta01(ctx, scope):
    p = ctx.profiles[scope.split(":", 1)[1]]
    a, s, b = p["anchor"], p["share"], p["budget"]
    frame = math.floor(_F(a["frame_tris"]) * _F(s["content"]))
    want = {"frame_tris_max": frame,
            "terrain_tris_max": math.floor(frame * _F(s["terrain"])),
            "entity_tris_max": math.floor(frame * _F(s["entities"])),
            "draw_calls_max": math.floor(_F(a["draw_calls"]) * _F(s["content"]))}
    bad = [f"{k} is {b[k]}, expected {v}" for k, v in want.items() if b[k] != v]
    if _F(s["terrain"]) + _F(s["entities"]) + _F(s["reserve"]) != 1:
        bad.append("terrain, entities, reserve shares do not sum to 1.0")
    return common.violations("META-01", scope, bad, "budgets",
                             "Rewrite the [budget] lines as floor(anchor * share), or use `tilepipe profile set-share`.")


@implements("META-02")
def meta02(ctx, scope):
    try:
        secs = float(common.jload(ctx, common.build(ctx) / "build_info.json")["total_seconds"])
    except (FileNotFoundError, KeyError):
        return result("META-02", scope, "WARN", "no build_info.json", BUILD_SECONDS_MAX, "s", "<=",
                      "Run `uv run tilepipe build` so the build time is recorded.")
    return check_result("META-02", scope, secs <= BUILD_SECONDS_MAX, round(secs, 3), BUILD_SECONDS_MAX, "s", "<=",
                        "Find the slowest stage in build_info.json and speed it up.")


@implements("META-03")
def meta03(ctx, scope):
    """aois.toml, profiles, looks, tile.json, entity.json files. validation.json is checked by the runner on write."""
    bad = []

    def check(name, doc, what):
        bad.extend(f"{what} {e}" for e in config.schema_errors(doc, name))

    check("aois", tomllib.loads((ctx.root / "aois.toml").read_text(encoding="utf-8")), "aois.toml")
    for f in sorted((ctx.root / "profiles").glob("*.toml")):
        doc = tomllib.loads(f.read_text(encoding="utf-8"))
        check("profile", doc, f"profiles/{f.name}")
        if doc.get("name") != f.stem:
            bad.append(f"profiles/{f.name} name does not equal the file name")
    for f in sorted((ctx.root / "look").glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        check("look", doc, f"look/{f.name}")
        if doc.get("mode") != f.stem:
            bad.append(f"look/{f.name} mode does not equal the file name")
    check("tile", common.tile(ctx), f"dist/{ctx.aoi}/tile.json")
    for f in sorted((ctx.root / "dist" / "entities").glob("*/entity.json")):
        check("entity", json.loads(f.read_text(encoding="utf-8")), common.rel(ctx, f))
    return common.violations("META-03", scope, bad, "schema errors", "Fix the file against its schema.")


@implements("META-04")
def meta04(ctx, scope):
    d = ctx.entity_lods
    bad = []
    for lod in d["lod"]:
        deg = math.degrees(2 * math.atan(d["token_table_size_m"] / 2 / lod["view_distance_m"]))
        limit = 2 * (deg * lod["ppd"]) ** 2 / d["min_triangle_area_px"]
        if lod["tris_max"] > limit:
            bad.append(f"LOD {lod['n']} tris_max {lod['tris_max']} exceeds {limit:.0f}")
    for name, p in ctx.profiles.items():
        if not 0 <= p["entities"]["lod"] < len(d["lod"]):
            bad.append(f"profile {name} entity LOD {p['entities']['lod']} does not exist")
    return common.violations("META-04", scope, bad, "limits", "Lower tris_max in entity_lods.toml (8.4).")


# ---------------------------------------------------------------- DET-01 and OFF-01: two builds in scratch roots

_INPUTS = ("aois.toml", "entity_lods.toml", "profiles", "look", "data/source", "scene", "assets/entities",
           "viewer/src/shaders", "dist/entities")


def _stage_root(src: Path, dst: Path) -> None:
    for name in _INPUTS:
        s = src / name
        if s.is_dir():
            shutil.copytree(s, dst / name)
        elif s.is_file():
            (dst / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, dst / name)


@contextlib.contextmanager
def _offline():
    """TILEPIPE_OFFLINE=1 with the socket guard of offline.py, undone on exit."""
    from tilepipe import offline
    names = ("connect", "connect_ex")
    saved = ({n: getattr(socket.socket, n) for n in names},
             {n: getattr(socket, n) for n in ("create_connection", "getaddrinfo", "gethostbyname")})
    prev = os.environ.get("TILEPIPE_OFFLINE")
    os.environ["TILEPIPE_OFFLINE"] = "1"
    offline.install()
    try:
        yield
    finally:
        for n, f in saved[0].items():
            setattr(socket.socket, n, f)
        for n, f in saved[1].items():
            setattr(socket, n, f)
        if prev is None:
            os.environ.pop("TILEPIPE_OFFLINE", None)
        else:
            os.environ["TILEPIPE_OFFLINE"] = prev


def build_into(root: Path, aoi: str) -> None:
    from tilepipe import cli
    with contextlib.redirect_stdout(io.StringIO()):
        cli.build(root, aoi)


def two_builds(ctx) -> dict:
    """Build twice into fresh roots, the second offline. {'hashes': [h1, h2], 'errors': [e1, e2]}."""
    def run():
        out = {"hashes": [], "errors": []}
        with tempfile.TemporaryDirectory() as td:
            for i in (1, 2):
                root = Path(td) / f"b{i}"
                root.mkdir()
                _stage_root(ctx.root, root)
                try:
                    with (_offline() if i == 2 else contextlib.nullcontext()):
                        build_into(root, ctx.aoi)
                    out["hashes"].append((root / "dist" / ctx.aoi / "outputs.sha256").read_text(encoding="utf-8"))
                    out["errors"].append("")
                except Exception as e:  # a failed build is the finding
                    out["hashes"].append("")
                    out["errors"].append(f"{type(e).__name__}: {e}"[:200])
        return out
    return common.memo(ctx, "two_builds", run)


@implements("DET-01")
def det01(ctx, scope):
    if not ctx.options.get("determinism"):
        return skip("DET-01", scope, "runs only with `tilepipe validate --determinism`")
    r = two_builds(ctx)
    if any(r["errors"]):
        return check_result("DET-01", scope, False, "build failed", "two builds", "", "==", next(e for e in r["errors"] if e))
    same = r["hashes"][0] == r["hashes"][1]
    differ = sum(a != b for a, b in zip(r["hashes"][0].splitlines(), r["hashes"][1].splitlines()))
    return check_result("DET-01", scope, same, differ, 0, "differing lines in outputs.sha256", "<=",
                        "Find the stage that writes the differing file and remove its nondeterminism (6.7).")


@implements("OFF-01")
def off01(ctx, scope):
    """Covers the seven build stages under TILEPIPE_OFFLINE=1; entities and site are covered by gate G6."""
    if not ctx.options.get("determinism"):
        return skip("OFF-01", scope, "runs only with `tilepipe validate --determinism`")
    err = two_builds(ctx)["errors"][1]
    return check_result("OFF-01", scope, not err, err or "ok", "ok", "", "==",
                        "Remove the network access the build attempts (3.3 rule 8).")


# ---------------------------------------------------------------- REG-01

def found_cases(root: Path) -> dict[str, set[str]]:
    """{rule id: {'pass', 'fail'}} found as `def test_rule_<FAMILY>_<nn>_pass|fail` in tests/ and blender/scripts/."""
    found: dict[str, set[str]] = {}
    for d in ("tests", "blender/scripts"):
        for f in sorted((root / d).glob("*.py")):
            for fam, num, kind in TEST_NAME.findall(f.read_text(encoding="utf-8")):
                found.setdefault(f"{fam}-{num}", set()).add(kind)
    return found


@implements("REG-01")
def reg01(ctx, scope):
    bad = [f"{rid} is not registered" for rid in SPEC_RULE_IDS if rid not in RULES]
    bad += [f"{rid} is registered but not in SPEC 12" for rid in RULES if rid not in SPEC_RULE_IDS]
    cases = found_cases(ctx.root)
    for rid, rule in RULES.items():
        if not rule.stub:
            for kind in ("pass", "fail"):
                if kind not in cases.get(rid, ()):
                    bad.append(f"{rid} has no {kind} case (def test_rule_{rid.replace('-', '_')}_{kind})")
    return common.violations("REG-01", scope, bad, "gaps",
                             "Register the rule in registry.py or add the missing test case.")
