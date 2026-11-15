"""WP09 viewer shader checks: TEX-05, standalone GLSL, uniform list, profile look mirror, headless compile."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tilepipe import config

ROOT = Path(__file__).resolve().parents[1]
SHADERS = ROOT / "viewer" / "src" / "shaders"
MAIN_JS = ROOT / "viewer" / "src" / "main.js"

# Terrain uniforms of SPEC 10.2. Every uniform the terrain stages declare must be one of these.
TERRAIN_UNIFORMS = {
    "u_viewProj", "u_tableFromTL", "u_height", "u_nao", "u_hMin", "u_hMax", "u_exag", "u_extent",
    "u_gridOffset", "u_ramp", "u_rampT", "u_lightDir", "u_additive", "u_kDim", "u_aoFloor", "u_shadeBase",
    "u_shadeGain", "u_shadeMax", "u_lineColor", "u_plinthColor", "u_alphaMinor", "u_alphaIndex",
    "u_alphaGrid", "u_interval", "u_indexEvery", "u_wMinor", "u_wIndex", "u_wGrid", "u_chunkLod",
    "u_debugLod",
}


def fetch_count(src: str) -> int:
    return len(re.findall(r"\btextureLod\(", src)) + len(re.findall(r"\btexture\(", src))


def test_TEX05_terrain_fetch_count():
    src = (SHADERS / "terrain.frag.glsl").read_text(encoding="utf-8")
    lines = src.splitlines()
    declared = re.fullmatch(r"// TEXTURE_SAMPLES: (\d+)", lines[1])
    assert declared, "line 2 must be the TEXTURE_SAMPLES comment"
    n = fetch_count(src)
    assert n == int(declared.group(1)) == 2
    assert len(re.findall(r"\btextureLod\(", src)) == 1
    for name, prof in config.load_profiles(ROOT).items():
        assert n <= prof["budget"]["terrain_tex_samples_max"], name
    tile = ROOT / "dist" / config.default_aoi(ROOT) / "tile.json"
    if tile.exists():
        for name, prof in json.loads(tile.read_text(encoding="utf-8"))["profiles"].items():
            assert prof["terrain_tex_samples"] == n, name


@pytest.mark.parametrize("path", sorted(SHADERS.glob("*.glsl")), ids=lambda p: p.name)
def test_shaders_are_standalone(path):
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    assert lines[0] == "#version 300 es"
    assert "precision highp float;" in lines[:3]
    assert "#include" not in src
    # three.js chunk and built-in names must not appear: the shaders are engine-free GLSL.
    for word in ("modelViewMatrix", "projectionMatrix", "modelMatrix", "viewMatrix", "cameraPosition",
                 "normalMatrix", "linearToOutputTexel", "sRGBTransferOETF", "<common>"):
        assert word not in src, f"{path.name}: {word}"


def test_terrain_uniforms_listed():
    for name in ("terrain.vert.glsl", "terrain.frag.glsl"):
        src = (SHADERS / name).read_text(encoding="utf-8")
        found = set(re.findall(r"^uniform\s+\w+\s+(\w+)", src, re.M))
        assert found <= TERRAIN_UNIFORMS, f"{name}: {found - TERRAIN_UNIFORMS}"
    frag = (SHADERS / "terrain.frag.glsl").read_text(encoding="utf-8")
    assert set(re.findall(r"^uniform\s+\w+\s+(\w+)", frag, re.M)) == TERRAIN_UNIFORMS - {"u_viewProj",
                                                                                         "u_tableFromTL"}


def test_profile_look_mirror_matches_profiles():
    # main.js mirrors each profile's [look] default because tile.json does not carry it (D-08).
    m = re.search(r"PROFILE_LOOK = \{([^}]*)\}", MAIN_JS.read_text(encoding="utf-8"))
    mirror = dict(re.findall(r"(\w+): '(\w+)'", m.group(1)))
    assert mirror == {name: p["look"]["default"] for name, p in config.load_profiles(ROOT).items()}


def test_glsl_compiles_headless():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found: GLSL compile is a manual check")
    r = subprocess.run([node, str(ROOT / "tests" / "glsl_compile.mjs")], cwd=ROOT, capture_output=True, text=True)
    if r.returncode == 77:
        pytest.skip(f"manual check: {r.stdout.strip()}")
    assert r.returncode == 0, r.stdout + r.stderr
