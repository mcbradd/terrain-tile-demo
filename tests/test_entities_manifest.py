"""D-12: entities.run rewrites the manifest so outputs.sha256 lists the entity GLBs."""
import shutil
from pathlib import Path

from tilepipe import config, entities

ROOT = Path(__file__).resolve().parent.parent


def test_refresh_manifest_calls_manifest_run(monkeypatch):
    calls = []
    monkeypatch.setattr("tilepipe.manifest.run", lambda root, aoi: calls.append((root, aoi)))
    entities.refresh_manifest(ROOT)
    built = [a for a in config.load_aois(ROOT) if (config.dist_dir(ROOT, a) / "tile.json").exists()]
    assert calls == [(ROOT, a) for a in built]


def test_refresh_manifest_covers_every_built_aoi(monkeypatch, tmp_path):
    """Regression: only the default AOI was refreshed, so a fresh `all --aoi st_helens_01` failed PAY-01."""
    shutil.copy2(ROOT / "aois.toml", tmp_path / "aois.toml")
    aois = list(config.load_aois(ROOT))
    assert len(aois) >= 2
    for a in aois:   # every AOI built, the non-default one included
        t = config.dist_dir(tmp_path, a) / "tile.json"
        t.parent.mkdir(parents=True)
        t.write_text("{}", encoding="utf-8")
    calls = []
    monkeypatch.setattr("tilepipe.manifest.run", lambda root, aoi: calls.append(aoi))
    entities.refresh_manifest(tmp_path)
    assert calls == aois


def test_deliverable_gate_logs_validator_output(monkeypatch, tmp_path):
    """3.3 rule 7: the entity GLB-01 run writes its validator output to its own log under build/logs."""
    import subprocess

    from tilepipe.validate import rules_tex
    glb = tmp_path / "dist" / "entities" / "ent_x" / "ent_x_LOD0.glb"
    glb.parent.mkdir(parents=True)
    glb.write_bytes(b"glTF")
    out = '{"ent_x_LOD0.glb": {"errors": 0, "warnings": 0, "infos": 0, "hints": 0}}'
    monkeypatch.setattr(rules_tex.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, out, ""))
    for name in ("default_aoi", "load_profiles", "load_looks", "load_entity_lods"):
        monkeypatch.setattr(config, name, lambda root, f=getattr(config, name): f(ROOT))
    recs = entities.deliverable_gate(tmp_path, [])
    assert recs[-1]["status"] == "PASS"
    log = tmp_path / "build" / "logs" / "gltf_validator_entities.log"
    assert log.stat().st_size > 0 and "ent_x_LOD0.glb" in log.read_text(encoding="utf-8")
