"""Commands `presubmit` and `profile set-share` (SPEC 4.2, 18 D1). Signatures are frozen: see contracts.md."""
import importlib.util
import json
import math
import re
import tempfile
from fractions import Fraction
from pathlib import Path
from unittest import mock

from tilepipe import config
from tilepipe.validate import common
from tilepipe.validate.registry import RULES, Context

ENTD = tuple(f"ENTD-{i:02d}" for i in range(1, 7))


def _blend(root: Path, f: Path) -> list[str]:
    """Source gate (blender/source_gate.py) on one .blend; returns failure lines."""
    spec = importlib.util.spec_from_file_location("source_gate", root / "blender" / "source_gate.py")
    sg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sg)
    with tempfile.TemporaryDirectory() as t:
        out = Path(t) / "r.json"
        code = sg.blender(root, "validate_blend.py", "--blend", str(f), "--profiles", str(root / "profiles"),
                          "--out", str(out))
        recs = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    bad = [f"{f}: {r['rule']} FAIL {r.get('message', '')}" for r in recs if r["status"] == "FAIL"]
    if code and not bad:
        bad = [f"{f}: source gate failed to run (exit {code}), see build/logs/entities.log"]
    return bad


def _glb(root: Path, f: Path) -> list[str]:
    """Deliverable gate (ENTD-01..06) on the entity that owns this GLB; the rules read the GLB's own folder."""
    from tilepipe.validate import rules_entd  # noqa: F401  (registers the ENTD checks)
    ent = re.sub(r"_LOD\d+$", "", f.stem)
    ctx = Context(root=root, aoi=config.default_aoi(root), profiles=config.load_profiles(root),
                  looks=config.load_looks(root), entity_lods=config.load_entity_lods(root),
                  options={"skip_entities": False, "determinism": False, "no_blender": True}, cache={})
    with mock.patch.object(common, "entity_dir", lambda c, e: f.parent):
        recs = [RULES[r].check(ctx, f"entity:{ent}").to_dict() for r in ENTD]
    return [f"{f}: {r['rule']} FAIL {r['message']}" for r in recs if r["status"] == "FAIL"]


def run(root: Path, files: list[Path]) -> int:
    root = Path(root).resolve()
    bad = []
    for f in map(Path, files):
        f = f.resolve()
        if f.suffix == ".blend":
            bad += _blend(root, f)
        elif f.suffix == ".glb":
            bad += _glb(root, f)
    print("\n".join(bad) if bad else f"presubmit: {len(files)} files OK")
    return 1 if bad else 0


def set_share(root: Path, profile: str, share: float) -> None:
    """Rewrite [share] content and the four derived [budget] lines as floor(anchor * share) (META-01), text-preserving."""
    f = Path(root) / "profiles" / f"{profile}.toml"
    text = f.read_text(encoding="utf-8")
    p = config.load_profiles(root)[profile]
    a, s, c = p["anchor"], p["share"], Fraction(str(share))
    frame = math.floor(a["frame_tris"] * c)
    new = {"frame_tris_max": frame, "terrain_tris_max": math.floor(frame * Fraction(str(s["terrain"]))),
           "entity_tris_max": math.floor(frame * Fraction(str(s["entities"]))),
           "draw_calls_max": math.floor(a["draw_calls"] * c)}
    sec = {"content": repr(float(share)), **{k: str(v) for k, v in new.items()}}
    out, cur = [], None
    for line in text.splitlines(keepends=True):
        h = re.match(r"\[(\w+)\]", line)
        cur = h.group(1) if h else cur
        m = re.match(r"(\w+)(\s*=\s*)\S+(.*)", line, re.S)
        if m and m.group(1) in sec and cur == ("share" if m.group(1) == "content" else "budget"):
            line = f"{m.group(1)}{m.group(2)}{sec[m.group(1)]}{m.group(3)}"
        out.append(line)
    f.write_text("".join(out), encoding="utf-8", newline="")
