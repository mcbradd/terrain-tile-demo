"""Runs every rule; writes validation.json, validation.junit.xml, and the report (SPEC 12.2). Signatures frozen: see contracts.md."""
import importlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from tilepipe import config
from tilepipe.validate import registry
from tilepipe.validate.registry import RULES, Context, Result, result, skip

RULE_MODULES = ("rules_meta", "rules_geo", "rules_terrain", "rules_tex", "rules_look", "rules_scene", "rules_entd")
FIELDS = ("rule", "severity", "status", "scope", "measured", "limit", "unit", "message", "fix_hint")
ENT_RESULTS = Path("build") / "entities" / "ent_results.json"


def _load_rules() -> None:
    for m in RULE_MODULES:
        importlib.import_module(f"tilepipe.validate.{m}")


def _py(v):
    """numpy scalars to Python scalars, so config.write_json and the schema accept them."""
    return v.item() if hasattr(v, "item") else v


def _record(r: Result) -> dict:
    d = r.to_dict()
    d["measured"], d["limit"] = _py(d["measured"]), _py(d["limit"])
    return d


def entity_scopes(ctx: Context) -> list[str]:
    try:
        ids = json.loads((config.dist_dir(ctx.root, ctx.aoi) / "tile.json").read_text(encoding="utf-8"))["entities"]
    except (OSError, ValueError, KeyError):
        ids = sorted(p.name for p in (ctx.root / "dist" / "entities").glob("ent_*") if p.is_dir())
    return [f"entity:{i}" for i in ids]


def scopes_for(ctx: Context, kind: str) -> list[str]:
    if kind in ("tile", "repo"):
        return [kind]
    if kind == "profile":
        return [f"profile:{n}" for n in ctx.profiles]
    return entity_scopes(ctx) if kind == "entity" else []   # fixture scopes come only from ent_results.json


def _crash(rule, scope: str, e: Exception) -> Result:
    """A check that cannot read its input or raises: the rule's own severity, with the cause as the measurement."""
    if isinstance(e, FileNotFoundError):
        what, hint = f"missing {Path(str(e.filename or e)).name}", "Run `uv run tilepipe build` first."
    else:
        what, hint = f"{type(e).__name__}: {e}"[:160].replace("\n", " "), "Fix the input or the rule; see the message."
    return result(rule.id, scope, rule.severity, what, "check completes", "", "==", hint)


def run_rules(ctx: Context) -> list[dict]:
    out: list[dict] = []
    skip_ent = bool(ctx.options.get("skip_entities"))
    ent_file = ctx.root / ENT_RESULTS
    ent_records = None
    if not skip_ent and ent_file.exists():
        ent_records = json.loads(ent_file.read_text(encoding="utf-8"))
    for rule in RULES.values():
        if rule.id.startswith("ENT-"):   # ENT source rules run in Blender (4, 12.6); their records are merged here
            if ent_records is not None:
                out += [r for r in ent_records if r["rule"] == rule.id]
                continue
            reason = "--skip-entities" if skip_ent else f"{ENT_RESULTS.as_posix()} is absent; run `tilepipe entities`"
            out += [_record(skip(rule.id, s, reason)) for s in scopes_for(ctx, "entity")]
            continue
        for scope in scopes_for(ctx, rule.scope_kind):
            try:
                out.append(_record(rule.check(ctx, scope)))
            except Exception as e:   # a crashing check is a failed check, never a silent pass
                out.append(_record(_crash(rule, scope, e)))
    return out


def summarize(results: list[dict]) -> dict:
    summary: dict[str, dict] = {}
    for r in results:
        c = summary.setdefault(r["scope"], {"pass": 0, "fail": 0, "warn": 0, "skip": 0})
        c[r["status"].lower()] += 1
    return summary


def junit(aoi: str, results: list[dict]) -> bytes:
    """One testsuite per scope, one testcase per rule; FAIL gets a `failure`, SKIP a `skipped`, WARN system-out."""
    root = ET.Element("testsuites", name=f"tilepipe {aoi}")
    for scope, c in summarize(results).items():
        rows = [r for r in results if r["scope"] == scope]
        suite = ET.SubElement(root, "testsuite", name=scope, tests=str(len(rows)), failures=str(c["fail"]),
                              skipped=str(c["skip"]), errors="0")
        for r in rows:
            case = ET.SubElement(suite, "testcase", classname=scope, name=r["rule"])
            if r["status"] == "FAIL":
                ET.SubElement(case, "failure", message=r["message"]).text = r["message"]
            elif r["status"] == "SKIP":
                ET.SubElement(case, "skipped", message=r["message"])
            elif r["status"] == "WARN":
                ET.SubElement(case, "system-out").text = r["message"]
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def run(root: Path, aoi: str, skip_entities: bool = False, determinism: bool = False) -> int:
    _load_rules()
    ctx = Context(root=root, aoi=aoi, profiles=config.load_profiles(root), looks=config.load_looks(root),
                  entity_lods=config.load_entity_lods(root),
                  options={"skip_entities": skip_entities, "determinism": determinism, "no_blender": False})
    results = run_rules(ctx)
    doc = {"schema": 1, "aoi": aoi, "results": results, "summary": summarize(results)}
    errs = config.schema_errors(doc, "validation")   # META-03 also covers the file about to be written
    if errs:
        i = next(i for i, r in enumerate(results) if r["rule"] == "META-03")
        results[i] = _record(result("META-03", "repo", "FAIL", f"validation.json: {errs[0]}"[:160], "valid", "", "==",
                                    "Fix the result record that breaks validation.schema.json."))
        doc["summary"] = summarize(results)
    d, b = config.dist_dir(root, aoi), config.build_dir(root, aoi)
    config.write_json(d / "validation.json", doc)
    b.mkdir(parents=True, exist_ok=True)
    (b / "validation.junit.xml").write_bytes(junit(aoi, results))
    try:
        from tilepipe.report.render import render
        print(f"report: {render(root, aoi, doc)}")
    except (ImportError, NotImplementedError) as e:
        print(f"report: not written ({type(e).__name__}: {e})")
    totals = {s: sum(r["status"] == s for r in results) for s in registry.STATUSES}
    for r in results:
        if r["status"] in ("FAIL", "WARN"):
            print(r["message"])
    print(f"validate: {totals['PASS']} PASS, {totals['WARN']} WARN, {totals['FAIL']} FAIL, {totals['SKIP']} SKIP")
    return 1 if totals["FAIL"] else 0
