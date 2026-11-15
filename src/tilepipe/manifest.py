"""Stage `manifest` (SPEC 7.8, 9): tile.json, scene.json copy, outputs.sha256."""
import json
from pathlib import Path

import numpy as np

from tilepipe import config, glb, hashing
from tilepipe.lod import LODS, chunk_ids, lod_counts
from tilepipe.scene import ENTITIES, scene_path

GENERATOR = "tilepipe 1.0.0"
PRODUCT = "USGS 3DEP 1/3 arc-second DEM"
HEIGHT_BYTES, NAO_BYTES = 2_097_152, 5_592_404
HEIGHT_CHANNELS = "h = min + (R*65280 + G*255) / 65535 * (max - min), R and G sampled as 0..1"
PLINTH_DROP_M = 100.0


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise config.UsageError(f"manifest needs {path.name}: not found (run the earlier stages)") from e


def _texture(d: Path, id_: str, file: str, fmt: str, mips: int, filt: str, channels: dict) -> dict:
    return {"id": id_, "file": file, "format": fmt, "colorspace": "linear", "width": 1024, "height": 1024,
            "mip_levels": mips, "bytes": (d / file).stat().st_size, "filter": filt, "wrap": "clamp",
            "channels": channels, "sha256": hashing.sha256_file(d / file)}


def _chunks(d: Path, stats: dict) -> list[dict]:
    out = []
    for cx, cz, cid in chunk_ids():
        lods, lo, hi = [], None, None
        for k in range(LODS):
            f = f"terrain_{cid}_lod{k}.glb"
            pos, _ = glb.read_mesh(d / f)
            lo = pos.min(axis=0) if lo is None else np.minimum(lo, pos.min(axis=0))
            hi = pos.max(axis=0) if hi is None else np.maximum(hi, pos.max(axis=0))
            q = 256 >> k
            _, verts, tris = lod_counts(k)
            c = stats["chunks"][cid]
            lods.append({"k": k, "file": f, "vertices": verts, "tris_surface": 2 * q * q, "tris_skirt": 8 * q,
                         "tris": tris, "index_type": "uint16" if verts <= 65535 else "uint32",
                         "bytes": (d / f).stat().st_size, "e_max_m": c["e_max_m"][k], "e_rms_m": c["e_rms_m"][k],
                         "skirt_depth_m": stats["skirt_depth_m"][k], "sha256": hashing.sha256_file(d / f)})
        out.append({"id": cid, "cx": cx, "cz": cz,
                    "aabb": {"min": [float(v) for v in lo], "max": [float(v) for v in hi]}, "lods": lods})
    return out


def _profiles(root: Path, d: Path, selection: dict, textures_bytes: int) -> tuple[dict, dict]:
    """Profile entries without web_payload_bytes, and each profile's fixed payload part (all but tile.json)."""
    profiles, fixed = {}, {}
    for name, prof in config.load_profiles(root).items():
        sel = dict(selection[name])
        batches = [{**b, "sha256": hashing.sha256_file(d / b["file"])} for b in sel["batches"]]
        n = prof["entities"]["lod"]
        ent_bytes = sum(p.stat().st_size for e in ENTITIES
                        if (p := root / "dist" / "entities" / e / f"{e}_LOD{n}.glb").exists())
        fixed[name] = (sum(b["bytes"] for b in batches) + textures_bytes + ent_bytes
                       + (d / "scene.json").stat().st_size)
        profiles[name] = {**sel, "batches": batches, "texture_bytes": textures_bytes, "terrain_tex_samples": 2,
                          "entity_lod": n}
    return profiles, fixed


def run(root: Path, aoi: str) -> None:
    b, d = config.build_dir(root, aoi), config.dist_dir(root, aoi)
    rec, geo = config.load_aoi(root, aoi), _load(b / "geo.json")
    src, stats, sel = _load(root / "data" / "source" / f"{aoi}_src.json"), _load(b / "lod_stats.json"), \
        _load(b / "selection.json")
    scene = scene_path(root, aoi)
    if not scene.exists():
        raise config.UsageError(f"{scene.name} missing: run `tilepipe scene --regen`")
    (d / "scene.json").write_bytes(scene.read_bytes())

    textures = [
        _texture(d, "height", "terrain_height.rg8.bin", "RG8_UNORM", 1, "bilinear", {"RG": HEIGHT_CHANNELS}),
        _texture(d, "nao", "terrain_nao.rgba8.bin", "RGBA8_UNORM", 11, "trilinear",
                 {"R": "normal.x * 0.5 + 0.5", "G": "normal.z * 0.5 + 0.5", "B": "ambient occlusion",
                  "A": "reserved, 255"})]
    tex_bytes = sum(t["bytes"] for t in textures)
    profiles, fixed = _profiles(root, d, sel, tex_bytes)

    doc = {
        "schema": 1, "tile_id": aoi, "name": rec["name"], "generator": GENERATOR,
        "crs": {"epsg": geo["epsg"], "zone": geo["zone"], "hemisphere": "N", "vertical_datum": "NAVD88",
                "height_unit": "m"},
        "origin": {"E0": geo["E0"], "N0": geo["N0"], "N_top": geo["N_top"]},
        "extent_m": 10240.0, "cell_m": 10.0, "cells": 1024,
        "height": {"min": geo["h_min"], "max": geo["h_max"], "plinth_bottom": geo["h_min"] - PLINTH_DROP_M},
        "frame": {"handedness": "right", "up": "+Y", "x": "east", "z": "south",
                  "origin": "NW corner, elevation 0", "front_face": "CCW"},
        "table": {"scale": 8000, "exaggeration_default": 1.5, "exaggeration_allowed": [1.0, 1.5, 2.0, 3.0]},
        "source": {"product": PRODUCT, "credit": src["credit"], "crop_sha256": src["crop_sha256"],
                   "urls": src["urls"], "retrieved_utc": src["retrieved_utc"]},
        "textures": textures, "chunks": _chunks(d, stats), "profiles": profiles,
        "entities": list(ENTITIES), "scene": "scene.json", "looks": sorted(config.load_looks(root)),
    }
    if geo.get("mgrs_center"):
        m = geo["mgrs_center"]
        doc["mgrs"] = {"center": m, "gzd": m[:3], "square": m[3:5]}

    # web_payload_bytes includes tile.json's own size: iterate until the size is stable.
    size = 0
    for _ in range(8):
        for name, p in profiles.items():
            p["web_payload_bytes"] = fixed[name] + size
        new = len(config.dumps_json(doc).encode("utf-8"))
        if new == size:
            break
        size = new
    else:
        raise config.RuleFailure("tile.json size did not converge")
    config.check_schema(doc, "tile", "tile.json")
    config.write_json(d / "tile.json", doc)
    hashing.write_outputs_sha256(d)
