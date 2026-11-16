"""D-12: entities.run rewrites the manifest so outputs.sha256 lists the entity GLBs."""
from pathlib import Path

from tilepipe import config, entities

ROOT = Path(__file__).resolve().parent.parent


def test_refresh_manifest_calls_manifest_run(monkeypatch):
    calls = []
    monkeypatch.setattr("tilepipe.manifest.run", lambda root, aoi: calls.append((root, aoi)))
    aoi = config.default_aoi(ROOT)
    geo = config.build_dir(ROOT, aoi) / "geo.json"
    entities.refresh_manifest(ROOT)
    assert bool(calls) == geo.exists()
    if calls:
        assert calls == [(ROOT, aoi)]
