# Decisions

## Deviations

### D-01 (WP01) Installing the tilepipe command under `uv sync --no-build`

- Spec section: 3.3 rule 1, 4.2.
- Expected: `uv sync --no-build` succeeds and `uv run tilepipe` resolves.
- Observed: `--no-build` rejects the editable project install ("no binary distribution"), so a normal packaged project cannot sync.
- Change: the project is `package = false`. A tiny prebuilt wheel, `tools/launcher/dist/tilepipe_launcher-0.1.0-py3-none-any.whl` (rebuilt by `tools/launcher/build_wheel.py`), installs a `tilepipe` script that imports `src/tilepipe` from the current directory. pytest uses `pythonpath = ["src"]`. Commands still run from the repo root as 4.2 requires.

### D-02 (WP01) npm dev dependencies

- Spec section: 3.2, 3.3 rule 2.
- Expected: `npm ci` installs esbuild, gltf-validator, playwright.
- Observed: this machine sets `NODE_ENV=production`, so dev dependencies are skipped.
- Change: all four npm packages are listed under `dependencies`, exact versions.

### D-03 (WP01) PF-02 script location

- Spec section: 4.1 lists `blender/scripts/preflight_export.py`, owned by WP11.
- Change: WP01 ships the script as `tools/preflight_export.py` so preflight works now. WP11 may move it.

### D-04 (WP02) Contract modules beyond the 4.1 layout

- Spec section: 4.1 layout, 12.1 (registry location), 19.3 WP02 owned paths.
- Expected: WP02 owns `registry.py` and `cli.py`. The layout lists no shared config module, no `entities.py`, and no home for `profile set-share`.
- Observed: lanes B to F run in parallel after WP02, and they all need the same config loaders, exit-code errors, and canonical JSON writer before any of them merges. The `entities` command has no core module, and `set-share` has no module.
- Change: WP02 adds `src/tilepipe/config.py`, which holds the loaders, the errors of 4.3, and `write_json` per 6.7, and is frozen. It adds `src/tilepipe/entities.py` as a stub owned by WP11. `set_share` is a stub in `presubmit.py`, owned by WP12. The registry lives at `src/tilepipe/validate/registry.py`, where 4.1 and 12.1 place it. All signatures are listed in `src/tilepipe/contracts.md`.

### D-06 (orchestrator) C1 cut deferred to C2

- Spec section: 2.4, checkpoint C1.
- Expected: C1 (day 1, 20:00 PT) has G0 to G3 green. If not, all of P1 is cut.
- Observed: at C1, G0 and G2 were green. G1 passed its machine conditions but awaited the `[HUMAN]` AOI sign-off and MGRS cross-check. G3 was not started, because a usage limit stopped WP07 at setup.
- Change: Bradd chose on 2026-11-14 to defer the P1 cut decision to C2 instead of taking it at C1. P1 work still starts only after WP14 passes (19.3). No threshold, budget, or rule changes.
- Why: DRAFT, for Bradd to write in his own words.

### D-07 (WP07) Validator interfaces the spec leaves open

- Spec section: 12.1, 12.3, 12.8, 13.8, 19.4.
- Expected: the spec fixes every rule's check but not the `bench.json` field names, how REG-01 finds test cases, or how a rule that is implemented later interacts with the WP02 stub test.
- Observed: 13.8 names the per-profile values (`live_tris`, `live_draws`, frame time p50 and p95, fraction of frames longer than 1.5 times the median) but not the document shape. `tests/test_schema.py` asserted that every rule is a stub returning SKIP, which stops being true once a rule module is imported.
- Change: SCN-04 and PERF-01 read `build/<aoi>/bench.json` as `{"profiles": {<profile>: {"live_tris", "live_draws", "frac_longer_than_1p5_median", ...}}}`; WP10 must write that shape. REG-01 finds cases as `def test_rule_<FAMILY>_<nn>_pass` and `_fail` in `tests/*.py` and `blender/scripts/*.py`, and requires them for every rule that is not a stub (ENT rules stay stubs in the core registry and are covered by WP11). SCN-01 and SCN-02 use the `entity_lods.toml` `tris_max` as an upper bound when no `entity.json` exists; SCN-04 requires the exported counts. One line in `tests/test_schema.py` now skips the stub assertion for rules whose `stub` flag is false. No threshold, budget, or rule changed.
- Why: DRAFT, for Bradd to write in his own words.

### D-08 (WP09) Profile default look in the viewer

- Spec section: 13.2 step 2, 9.1.
- Expected: the viewer applies each profile's default look, which `profiles/<name>.toml` holds under `[look] default`.
- Observed: `tile.json` (frozen schema) does not carry the default look, and the site does not ship the profile files.
- Change: `viewer/src/main.js` mirrors the defaults in `PROFILE_LOOK`. `tests/test_viewer.py` fails if the mirror differs from `profiles/*.toml`. No threshold, budget, or rule changes. A later schema revision could add the field to `tile.json` and remove the mirror.
