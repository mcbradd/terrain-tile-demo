"""Commands `site` and `serve` (SPEC 13.9). Signatures are frozen: see contracts.md.

`build` bundles viewer/src with esbuild (the settings tests/viewer_check.mjs uses) and copies the viewer files,
look files, and every complete dist/<aoi>/ into site/. `serve` hosts site/ on 127.0.0.1.
"""
import functools
import json
import shutil
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tilepipe import config
from tilepipe.config import EnvError, UsageError

KEEP = ("report", "config.json")  # written by `validate` and set by [HUMAN] at G7; a rebuild leaves them alone
MIME = {".glb": "model/gltf-binary", ".bin": "application/octet-stream", ".js": "text/javascript",
        ".json": "application/json", ".map": "application/json", ".css": "text/css", ".html": "text/html",
        ".jpg": "image/jpeg"}
BUDGET_KEYS = ("terrain_tris_max", "frame_tris_max", "draw_calls_max", "texture_bytes_max")

# Reads one JSON options object on stdin. A node script is the one way to use esbuild's API from Python, and it
# is the same API tests/viewer_check.mjs calls.
_BUNDLE_JS = "import {build} from 'esbuild';" \
    "let s='';for await(const c of process.stdin)s+=c;" \
    "await build({...JSON.parse(s),bundle:true,format:'iife',target:'es2020',minify:true,sourcemap:true," \
    "loader:{'.glsl':'text'},logLevel:'warning'});"


def _profile_info(root: Path) -> dict:
    """Class descriptions and budget limits for the HUD. tile.json does not carry them (Deviation D-09)."""
    return {name: {"description": p["class"]["description"], "budget": {k: p["budget"][k] for k in BUDGET_KEYS}}
            for name, p in config.load_profiles(root).items()}


def _bundle(root: Path, out: Path) -> None:
    node = shutil.which("node")
    if not node:
        raise EnvError("node was not found on PATH")
    opts = {"entryPoints": [str(root / "viewer" / "src" / "hud.js")], "outfile": str(out / "app.js"),
            "define": {"__TILEPIPE_PROFILES__": json.dumps(_profile_info(root), sort_keys=True)}}
    r = subprocess.run([node, "--input-type=module", "-e", _BUNDLE_JS], cwd=root, input=json.dumps(opts),
                       capture_output=True, text=True)
    if r.returncode:
        raise EnvError(f"esbuild failed:\n{r.stdout}{r.stderr}")


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _complete(dist: Path) -> list[str] | None:
    """Files of one AOI that the site hosts, or None if dist/<aoi>/ is not complete (13.9)."""
    tile_json = dist / "tile.json"
    if not tile_json.exists():
        return None
    tile = json.loads(tile_json.read_text(encoding="utf-8"))
    files = ["tile.json", "scene.json", *(t["file"] for t in tile["textures"]),
             *(b["file"] for p in tile["profiles"].values() for b in p["batches"])]
    return files if all((dist / f).exists() for f in files) else None


def build(root: Path, aoi: str) -> None:
    dist, out = root / "dist", root / "site"
    aois = sorted(d.name for d in dist.iterdir() if d.is_dir() and d.name != "entities") if dist.is_dir() else []
    todo = {a: _complete(dist / a) for a in aois}
    if todo.get(aoi) is None:
        raise UsageError(f"dist/{aoi}/ is not complete; run `uv run tilepipe build` first")
    out.mkdir(exist_ok=True)
    for p in out.iterdir():
        if p.name not in KEEP:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
    _bundle(root, out)
    for name in ("index.html", "styles.css"):
        _copy(root / "viewer" / name, out / name)
    (out / ".nojekyll").write_bytes(b"")
    cfg_path = out / "config.json"  # the viewer reads `aoi` from here when the URL has no ?aoi= (17.14, D-14)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {"video_url": "", "repo_url": ""}
    config.write_json(cfg_path, {**cfg, "aoi": aoi})
    for name in ("room.jpg", "fallback.jpg"):  # [HUMAN] files; copied only when present
        if (root / "assets" / name).exists():
            _copy(root / "assets" / name, out / "assets" / name)
        else:
            print(f"site: assets/{name} is absent and is not created here")
    for look in sorted((root / "look").glob("*.json")):
        _copy(look, out / "look" / look.name)
    for a, files in sorted(todo.items()):
        if files is None:
            print(f"site: skipped dist/{a}/ (incomplete)")
            continue
        for f in [*files, "validation.json"]:
            if (dist / a / f).exists():
                _copy(dist / a / f, out / "data" / a / f)
            else:
                print(f"site: dist/{a}/{f} is absent; run `uv run tilepipe validate`")
    ents = dist / "entities"
    if ents.is_dir():
        for f in sorted(ents.glob("*/entity.json")):
            for g in [f, *sorted(f.parent.glob("*.glb"))]:
                _copy(g, out / "data" / "entities" / f.parent.name / g.name)
    else:
        print("site: dist/entities is absent; run `uv run tilepipe entities`. The viewer draws no entities.")
    print(f"site: wrote {out.name}/")


class _Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, **MIME}

    def log_message(self, *args) -> None:  # one line per request is noise here
        pass


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False  # on Windows reuse lets a second server share a busy port

    def handle_error(self, request, client_address) -> None:  # a browser closing a connection is not an error
        pass


def make_server(root: Path, port: int = 8000) -> ThreadingHTTPServer:
    site = root / "site"
    if not (site / "index.html").exists():
        raise UsageError("site/ is empty; run `uv run tilepipe site` first")
    return _Server(("127.0.0.1", port), functools.partial(_Handler, directory=str(site)))


def serve(root: Path, port: int = 8000) -> None:
    server = make_server(root, port)
    print(f"Serving site/ at http://127.0.0.1:{server.server_address[1]}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
