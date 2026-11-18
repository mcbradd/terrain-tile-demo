"""Renders site/report/index.html from validation.json, tile.json, lod_stats.json, and build_info.json (SPEC 14.1).

Contract: tilepipe.report.render.render(root, aoi, validation) -> Path (contracts.md section 4).
"""
import base64
import json
import platform
import subprocess
from importlib import metadata
from pathlib import Path

import jinja2

from tilepipe import config
from tilepipe.validate.runner import verdict, verdict_text
from tilepipe.validate.rules_scene import ENTITY_DRAWS, STEM_DRAWS, STEM_TRIS

ACCURACY = (
    "Horizontal: source resampled bilinearly to a 10 m grid in WGS84 / UTM. The NAD83 to WGS84 transformation is "
    "whatever PROJ selects for this CRS pair. The GDAL version is recorded in build_info.json; the PROJ pipeline "
    "string is not captured in `tile.json`. Treat horizontal accuracy as plus or minus one cell (10 m). Vertical: "
    "NAVD88 orthometric heights in meters. No vertical datum conversion is applied. Heights are not ellipsoidal "
    "(HAE) and not EGM96. A consumer that needs HAE must apply a geoid model."
)
EXTRAPOLATION = "Linear extrapolation from one measured tile on one machine. Not a measurement."
STATIC_ONLY = "Static validation only. No headset performance was measured."
TOLERANCE_MET = "Tolerance met."
BUDGET_FORCED = "Budget-forced: the triangle budget, not the pixel tolerance, set this error."
ASSUMED_DESC = {
    "budget.texture_bytes_max": "Texture memory ceiling assumed for the device class.",
    "lod.ppd": "Display pixels per degree assumed for the device class.",
}
ORDER = {"FAIL": 0, "WARN": 1, "PASS": 2, "SKIP": 3}


def _jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _commit(root: Path) -> str:
    log = root / "build" / "logs" / "report.log"   # 3.3 rule 7; no timestamps, so the log is reproducible
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True,
                           timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        log.write_text(f"git rev-parse failed: {e}" + chr(10), encoding="utf-8", newline=chr(10))
        return "unknown"
    log.write_text(f"exit {r.returncode}" + chr(10) + f"{r.stdout}{r.stderr}", encoding="utf-8", newline=chr(10))
    return r.stdout.strip() or "unknown"


def _ver(pkg: str) -> str:
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return "not installed"


def _versions(root: Path, info: dict) -> list[tuple[str, str]]:
    pkg = _jload(root / "package.json")["dependencies"] if (root / "package.json").exists() else {}
    return [("Python", platform.python_version()), ("numpy", _ver("numpy")), ("rasterio", _ver("rasterio")),
            ("GDAL", info.get("gdal_version", "not recorded")),
            ("Blender", info.get("blender_version", "not recorded")),
            ("three", pkg.get("three", "not recorded"))]


def _assumed(root: Path, name: str, prof: dict) -> list[dict]:
    """Fields tagged `# ASSUMED` in profiles/<name>.toml: a whole table or a single key."""
    out, sec = [], ""
    for line in (root / "profiles" / f"{name}.toml").read_text(encoding="utf-8").splitlines():
        s = line.strip()
        flagged = "# ASSUMED" in s
        if s.startswith("["):
            sec = s[1:s.index("]")]
            if flagged:
                for k, v in prof[sec].items():
                    out.append({"field": f"{sec}.{k}", "value": v,
                                "desc": prof[sec]["description"] if k == "description" else f"Class setting: {k}."})
        elif flagged and "=" in s:
            k = s.split("=", 1)[0].strip()
            out.append({"field": f"{sec}.{k}", "value": prof[sec][k],
                        "desc": ASSUMED_DESC.get(f"{sec}.{k}", "Assumed input.")})
    return out


def _entity_docs(root: Path) -> dict:
    return {p.parent.name: _jload(p) for p in sorted((root / "dist" / "entities").glob("ent_*/entity.json"))}


def _gate(rows: list[dict]) -> str:
    st = {r["status"] for r in rows}
    return next((s for s in ("FAIL", "WARN") if s in st), "PASS" if "PASS" in st else "SKIP")


def _budgets(root: Path, entry: dict, prof: dict, scene: dict, ents: dict) -> list[dict]:
    b, lods = prof["budget"], config.load_entity_lods(root)["lod"]
    k = entry["entity_lod"]
    n_tris = sum(ents[i["entity"]]["lods"][k]["tris"] if i["entity"] in ents else lods[k]["tris_max"]
                 for i in scene["instances"])
    rows = [("Terrain triangles", entry["terrain_tris"], b["terrain_tris_max"], ""),
            ("Frame triangles", entry["terrain_tris"] + n_tris + STEM_TRIS, b["frame_tris_max"], ""),
            ("Draw calls", entry["terrain_draws"] + ENTITY_DRAWS + STEM_DRAWS, b["draw_calls_max"], ""),
            ("Texture bytes", entry["texture_bytes"], b["texture_bytes_max"], "ASSUMED"),
            ("Payload bytes", entry["web_payload_bytes"], b["web_payload_bytes_max"], "")]
    return [{"label": a, "used": u, "max": m, "pct": 100.0 * u / m, "tag": t} for a, u, m, t in rows]


def _scale(info: dict, dist: Path) -> dict:
    stages = info.get("stage_seconds", {})
    nbytes = sum(f.stat().st_size for f in dist.iterdir()
                 if f.is_file() and f.name not in ("validation.json", "outputs.sha256"))
    total = sum(stages.values())
    return {"stages": sorted(stages.items()), "total": total, "bytes": nbytes,
            "rows": [{"n": n, "seconds": total * n, "bytes": nbytes * n} for n in (1, 100, 1000)]}


def build_context(root: Path, aoi: str, validation: dict) -> dict:
    d, b = config.dist_dir(root, aoi), config.build_dir(root, aoi)
    tile, stats = _jload(d / "tile.json"), _jload(b / "lod_stats.json")
    info = _jload(b / "build_info.json") if (b / "build_info.json").exists() else {}
    profiles, scene, ents = config.load_profiles(root), _jload(d / "scene.json"), _entity_docs(root)
    results, summary = validation["results"], validation["summary"]
    empty = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
    prof_ctx = []
    for name, prof in profiles.items():
        e = tile["profiles"][name]
        sel, ch = e["selection"], stats["chunks"]
        cells = [[{"k": sel[f"c{cx}_{cz}"], "e": ch[f"c{cx}_{cz}"]["e_max_m"][sel[f"c{cx}_{cz}"]]}
                  for cx in range(4)] for cz in range(4)]
        c = summary.get(f"profile:{name}", empty)
        prof_ctx.append({"name": name, "chip": verdict(c), "verdict": verdict_text(c), "counts": c, "cells": cells, "e": e,
                         "budgets": _budgets(root, e, prof, scene, ents),
                         "sentence": BUDGET_FORCED if e["budget_forced"] else TOLERANCE_MET,
                         "assumed": _assumed(root, name, prof), "anchor": prof["anchor"]["source"]})
    scopes = sorted({r["scope"] for r in results}, key=lambda s: (s.split(":")[0] not in ("tile", "repo"), s))
    groups = [{"scope": s, "rows": sorted((r for r in results if r["scope"] == s),
                                          key=lambda r: (ORDER[r["status"]], r["rule"]))} for s in scopes]
    elods = config.load_entity_lods(root)["lod"]
    ent_ctx = []
    for i, doc in ents.items():
        rows = [r for r in results if r["scope"] == f"entity:{i}"]
        ent_ctx.append({"id": i, "lods": [{"n": x["n"], "tris": x["tris"], "max": elods[x["n"]]["tris_max"]}
                                          for x in doc["lods"]],
                        "source": _gate([r for r in rows if r["rule"].startswith("ENT-")]),
                        "export": _gate([r for r in rows if not r["rule"].startswith("ENT-")])})
    exp_f = root / "assets" / "fixtures" / "expected.json"
    expected = _jload(exp_f) if exp_f.exists() else {}
    fixtures = []
    for n in sorted(expected):
        rows = [r for r in results if r["scope"] == f"fixture:{n}"]
        fixtures.append({"id": n, "expected": sorted(expected[n]),
                         "actual": sorted({r["rule"] for r in rows if r["status"] == "FAIL"}),
                         "ran": any(r["status"] != "SKIP" for r in rows)})
    img = root / "docs" / "img"
    h5 = next(iter(sorted(img.glob("H5*"))), None) if img.is_dir() else None
    src = tile["source"]
    return {
        "tile": tile, "commit": _commit(root), "build_date": (info.get("finished_utc") or "not recorded")[:10],
        "profiles": prof_ctx, "chunk_ids": [f"c{cx}_{cz}" for cz in range(4) for cx in range(4)],
        "lod_err": {c["id"]: [x["e_max_m"] for x in c["lods"]] for c in tile["chunks"]}, "lods": list(range(5)),
        "groups": groups, "entities": ent_ctx, "fixtures": fixtures,
        "geo": [r for r in results if r["rule"] == "GEO-01"], "accuracy": ACCURACY,
        "scale": _scale(info, d), "extrapolation": EXTRAPOLATION, "static_only": STATIC_ONLY,
        "source": src, "retrieved_date": src["retrieved_utc"][:10], "versions": _versions(root, info),
        "validator": tile["generator"], "h5": h5,
    }


def render(root: Path, aoi: str, validation: dict, out_dir: Path | None = None) -> Path:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(Path(__file__).parent), autoescape=True,
                             trim_blocks=True, lstrip_blocks=True, undefined=jinja2.StrictUndefined)
    env.filters["n"] = lambda v: f"{int(v):,}"
    env.filters["f"] = lambda v, p=1: f"{float(v):.{p}f}"
    ctx = build_context(root, aoi, validation)
    if ctx["h5"] is not None:   # inline data URI: the report makes no requests (14.1)
        mime = "jpeg" if ctx["h5"].suffix.lower() in (".jpg", ".jpeg") else "png"
        ctx["h5"] = f"data:image/{mime};base64," + base64.b64encode(ctx["h5"].read_bytes()).decode("ascii")
    html = env.get_template("report.html.j2").render(**ctx).replace("—", "-")
    out = (out_dir or root / "site" / "report") / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    return out
