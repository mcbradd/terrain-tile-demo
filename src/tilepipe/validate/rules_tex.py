"""Texture, GLB, and payload rules (SPEC 12.5): TEX-01 to TEX-05, GLB-01, GLB-02, PAY-01."""
import json
import math
import re
import subprocess
from pathlib import Path

import numpy as np

from tilepipe import config
from tilepipe.validate import common
from tilepipe.validate.registry import check_result, implements

HEIGHT_BYTES, NAO_BYTES = 2_097_152, 5_592_404
NORMAL_LEN_MAX = 1 + 1 / 127
GLTF_TOOL = Path(__file__).resolve().parents[3] / "tools" / "validate_gltf.mjs"
SHADER = Path("viewer") / "src" / "shaders" / "terrain.frag.glsl"
_BPP = {"RG8_UNORM": 2, "RGBA8_UNORM": 4}
_FETCH = re.compile(r"\b(textureLod|texture)\s*\(")


def _tex(ctx, tex_id: str) -> dict:
    return next(t for t in common.tile(ctx)["textures"] if t["id"] == tex_id)


def _file(ctx, tex_id: str) -> Path:
    return common.dist(ctx) / _tex(ctx, tex_id)["file"]


@implements("TEX-01")
def tex01(ctx, scope):
    prof = ctx.profiles[scope.split(":", 1)[1]]
    sizes = [(_tex(ctx, i)["file"], _file(ctx, i).stat().st_size, want)
             for i, want in (("height", HEIGHT_BYTES), ("nao", NAO_BYTES))]
    total = sum(s for _, s, _ in sizes)
    checks = [("bytes", total, prof["budget"]["texture_bytes_max"], "<=")]
    checks += [(f"bytes in {f}", s, want, "==") for f, s, want in sizes]
    return common.multi("TEX-01", scope, checks, "Texture files must be exactly 2,097,152 and 5,592,404 bytes; rebake (7.5).")


@implements("TEX-02")
def tex02(ctx, scope):
    bad = []
    dim_max = min(p["budget"]["max_texture_dim"] for p in ctx.profiles.values())
    for t in common.tile(ctx)["textures"]:
        w, h = t["width"], t["height"]
        if (w & (w - 1)) or (h & (h - 1)) or max(w, h) > dim_max:
            bad.append(f"{t['id']}: {w} by {h} is not a power of two within {dim_max}")
        want_mips = 1 if t["id"] == "height" else int(math.log2(w)) + 1
        if t["mip_levels"] != want_mips:
            bad.append(f"{t['id']}: {t['mip_levels']} mip levels, expected {want_mips}")
        want_bytes = _BPP[t["format"]] * sum(max(1, w >> l) * max(1, h >> l) for l in range(t["mip_levels"]))
        actual = (common.dist(ctx) / t["file"]).stat().st_size
        if actual != want_bytes or t["bytes"] != want_bytes:
            bad.append(f"{t['id']}: file has {actual} bytes, declared levels need {want_bytes}")
    return common.violations("TEX-02", scope, bad, "defects", "Rebake the textures and rebuild the manifest (7.5).")


@implements("TEX-03")
def tex03(ctx, scope):
    raw = np.frombuffer(_file(ctx, "nao").read_bytes(), dtype=np.uint8)[:1024 * 1024 * 4].reshape(-1, 4)
    nx, nz = raw[:, 0] / 255.0 * 2 - 1, raw[:, 1] / 255.0 * 2 - 1
    worst = float(np.sqrt(nx * nx + nz * nz).max())
    return check_result("TEX-03", scope, worst <= NORMAL_LEN_MAX, round(worst, 6), round(NORMAL_LEN_MAX, 6), "", "<=",
                        "A decoded (nx, nz) is longer than a unit normal can be; check the 7.5 encoding.")


@implements("TEX-04")
def tex04(ctx, scope):
    h = common.tile(ctx)["height"]
    cells = common.h_full(ctx)[64:1088, 64:1088].astype(np.float64)
    tol = (h["max"] - h["min"]) / 65535
    worst = float(np.abs(common.height_texture(ctx) - cells).max())
    return check_result("TEX-04", scope, worst <= tol, round(worst, 6), round(tol, 6), "m", "<=",
                        "The height texture does not match the tile cells; rebake with the same h_min and h_max (7.5).")


def _strip_comments(src: str) -> str:
    return re.sub(r"//[^\n]*|/\*.*?\*/", "", src, flags=re.S)


@implements("TEX-05")
def tex05(ctx, scope):
    name = scope.split(":", 1)[1]
    path = ctx.root / SHADER
    if not path.exists():
        return check_result("TEX-05", scope, False, f"missing {SHADER.as_posix()}", "present", "", "==",
                            "The terrain fragment shader is a required file (10.1).")
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    m = re.fullmatch(r"// TEXTURE_SAMPLES: (\d+)", lines[1].strip()) if len(lines) > 1 else None
    if not m:
        return check_result("TEX-05", scope, False, "no line 2 comment", "// TEXTURE_SAMPLES: <n>", "", "==",
                            "Line 2 of terrain.frag.glsl must be `// TEXTURE_SAMPLES: <n>` (10.1).")
    n = len(_FETCH.findall(_strip_comments(src)))
    declared = common.tile(ctx)["profiles"][name]["terrain_tex_samples"]
    return common.multi("TEX-05", scope, [("fetches", n, int(m[1]), "=="), ("fetches in tile.json", declared, n, "=="),
                                          ("fetches", n, ctx.profiles[name]["budget"]["terrain_tex_samples_max"], "<=")],
                        "Make the fetch count, the line 2 comment, tile.json, and the profile budget agree (10.1).")


# ---------------------------------------------------------------- GLB-01, GLB-02

def run_validator(files: list[Path], log: Path | None = None) -> dict:
    """{file name: {errors, warnings, infos, hints}} from the Khronos validator, 40 files per node process.

    `log` receives stdout and stderr of every node call (3.3 rule 7); no timestamps, so the log is reproducible."""
    out = {}
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("", encoding="utf-8")
    for i in range(0, len(files), 40):
        part = files[i:i + 40]
        part = part if len(part) > 1 else part * 2   # one file would print the short single-file form
        r = subprocess.run(["node", str(GLTF_TOOL), *map(str, part)], capture_output=True, text=True,
                           cwd=GLTF_TOOL.parents[1], timeout=600)
        if log is not None:
            with log.open("a", encoding="utf-8", newline="\n") as f:
                f.write(f"exit {r.returncode}\n{r.stdout}{r.stderr}")
        if r.stdout.strip().startswith("{"):
            for f, counts in json.loads(r.stdout).items():
                out[Path(f).name] = counts
        else:
            raise RuntimeError(f"validate_gltf.mjs exit {r.returncode}: {(r.stderr or r.stdout).strip()[-200:]}")
    return out


@implements("GLB-01")
def glb01(ctx, scope):
    files = sorted(common.dist(ctx).rglob("*.glb")) + sorted((ctx.root / "dist" / "entities").rglob("*.glb"))
    files = sorted(set(files))
    counts = common.memo(ctx, "gltf_validator", lambda: run_validator(files, ctx.root / "build" / "logs" / "gltf_validator.log"))
    config.write_json(common.build(ctx) / "gltf_validator.json", counts)   # infos and hints are recorded here
    bad = [f"{f}: {c['errors']} errors, {c['warnings']} warnings" for f, c in counts.items()
           if c["errors"] or c["warnings"]]
    total = sum(c["errors"] + c["warnings"] for c in counts.values())
    if not counts:
        return check_result("GLB-01", scope, False, "no GLBs found", ">= 1 file", "", "==", common.BUILD_HINT)
    return check_result("GLB-01", scope, not bad, total, 0, "errors and warnings", "<=",
                        f"Fix the GLB writer. First: {bad[0]}." if bad else "")


@implements("GLB-02")
def glb02(ctx, scope):
    bad = []
    for f in common.terrain_glbs(ctx):
        doc, _ = common.glb_parts(ctx, f)
        meshes = doc.get("meshes", [])
        prims = meshes[0]["primitives"] if len(meshes) == 1 else []
        ok = (len(meshes) == 1 and len(prims) == 1 and list(prims[0]["attributes"]) == ["POSITION"]
              and "material" not in prims[0] and not doc.get("materials"))
        if not ok:
            bad.append(f.name)
    return common.violations("GLB-02", scope, bad, "files", "Terrain GLBs carry one mesh, one primitive, POSITION only (7.4).")


# ---------------------------------------------------------------- PAY-01

def payload_bytes(ctx, name: str) -> int:
    """Sum of the profile's batch files, both textures, its drawn entity GLBs, tile.json, and scene.json (9.1)."""
    tile = common.tile(ctx)
    d, entry = common.dist(ctx), tile["profiles"][name]
    total = sum((d / b["file"]).stat().st_size for b in entry["batches"])
    total += sum((d / t["file"]).stat().st_size for t in tile["textures"])
    for e in tile["entities"]:
        f = common.entity_dir(ctx, e) / f"{e}_LOD{entry['entity_lod']}.glb"
        total += f.stat().st_size if f.exists() else 0
    return total + (d / "tile.json").stat().st_size + (d / "scene.json").stat().st_size


@implements("PAY-01")
def pay01(ctx, scope):
    name = scope.split(":", 1)[1]
    got = payload_bytes(ctx, name)
    limit = ctx.profiles[name]["budget"]["web_payload_bytes_max"]
    return common.multi("PAY-01", scope, [("bytes", got, limit, "<="),
                                          ("bytes in tile.json", common.tile(ctx)["profiles"][name]["web_payload_bytes"], got, "==")],
                        "Reduce batch or texture size, or raise the demo hosting limit in the profile; rebuild the manifest.")
