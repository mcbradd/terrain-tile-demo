# Decisions

## Decision records

Each `Why` is a draft for Bradd to rewrite.

### D1 Core logic lives outside the DCC; Blender is a front end

- Decision: the rules and pipeline are Python with no Blender dependency. The extension calls the same rule shapes.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: all validation inside Blender.
- Revisit when: the receiving team's DCC of record is not Blender.

### D2 Regular-grid chunks with skirts, not adaptive triangulation

- Decision: the tile is 16 chunks on a regular grid, each with skirts.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: adaptive triangulation.
- Revisit when: the engine's mesh format is known.

### D3 Static per-profile LOD selection in the pipeline; runtime LOD policy left to the engine

- Decision: the build picks one LOD per chunk per profile and reports the error.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: a runtime LOD policy in the viewer.
- Revisit when: a team names who owns runtime LOD policy.

### D4 Shading from full-resolution data textures so the look is independent of geometric LOD

- Decision: normals, occlusion, and height come from data textures, not from mesh attributes.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: vertex normals and UVs.
- Revisit when: the engine requires per-vertex shading data.

### D5 Raw binary textures with 16-bit height packed in RG8, not PNG or float

- Decision: textures are raw `.bin` files and height uses two 8-bit channels.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: PNG files, or float textures.
- Revisit when: the engine's texture formats are known.

### D6 Textures ship uncompressed and budgets count actual bytes; compression is a next step

- Decision: no texture compression, and payload budgets use real byte counts.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: KTX2 or Basis compression.
- Revisit when: the target compression format is chosen.

### D7 glTF plus a JSON manifest as an engine-agnostic contract; terrain GLBs carry positions only

- Decision: `tile.json` plus GLB files are the interface. Terrain GLBs hold positions only.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: an engine-specific format.
- Revisit when: the receiving engine and its import path are known.

### D8 The additive look is a first-order preview, not a display model

- Decision: the additive look approximates an optical see-through display and models no real headset.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: a display model for a specific headset.
- Revisit when: a target display is named with its measured response.

### D9 Entities are fixed-size tokens because 1:8000 makes true scale invisible

- Decision: entities have a fixed table size set in `entity_lods.toml`.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: entities drawn at true scale.
- Revisit when: the table scale changes.

### D10 Budgets are public anchors times a content share, all in config

- Decision: each budget is a public anchor times a share, and lives in the profile file.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: hard-coded budgets in code.
- Revisit when: real device budgets are available.

### D11 three.js as scaffolding around standalone GLSL

- Decision: the viewer uses three.js for setup. The terrain shader is standalone GLSL ES 3.00.
- Why: DRAFT, for Bradd to write in his own words.
- Alternative rejected: a three.js material system for the terrain.
- Revisit when: the shader is ported to the engine.

## Known limitations

- Contours come from bilinear height samples, so under magnification they show small kinks at 10 m texel boundaries.
- Normals are stored at 8 bits per component, which quantizes diffuse lighting in steps of about 0.5%.
- Ambient occlusion is baked at true scale and is not recomputed when exaggeration changes.
- Silhouettes show the geometric LOD error. Interior shading does not.
- Index order is row-major with no vertex cache optimization.
- The additive look ignores display brightness limits, color non-uniformity, and field of view.
- Where neighboring chunks differ in LOD, skirt faces can show as thin plinth-colored seams in the opaque look and as thin gaps in the additive look.

## Cuts

None recorded.

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

### D-05 (WP11) Pytest case for the Blender scripts lives in `tests/`

- Spec section: 12.9 (test_rules.py "is run headless by a pytest case"), 19.3 WP11 owned paths (`blender/`), 19.4 WP11 validation `uv run pytest -k blender`.
- Expected: WP11 writes only under `blender/`.
- Observed: `pyproject.toml` sets `testpaths = ["tests"]`, so a pytest case under `blender/` is never collected by `uv run pytest -k blender`.
- Change: WP11 adds one file, `tests/test_blender.py`. It runs `blender/scripts/test_rules.py` headless and the fixture matrix through `blender/source_gate.py`, a standard-library driver that `tilepipe.entities.run` can call for its Blender half. It skips when Blender is absent.

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

### D-09 (WP10) Budget limits and class description for the HUD

- Spec section: 13.5 (Budget panel), 9.1, 13.9.
- Expected: the Budget panel shows `used / max` and `ASSUMED class:` plus the profile description from data the site hosts.
- Observed: `tile.json` (frozen schema) carries used values but no budget maxima and no class description, and 13.9 does not list the profile files among the hosted files.
- Change: `site.py` reads `profiles/*.toml` and embeds the description and four budget maxima in `app.js` with an esbuild `define` (`__TILEPIPE_PROFILES__`). No file is added to the 13.9 tree. Without the define, as in `tests/viewer_check.mjs`, the HUD shows `n/a`. A later schema revision could carry these fields in `tile.json`.
- Why: DRAFT, for Bradd to write in his own words.

### D-09a (WP10) Combined debug mode for the tour

- Spec section: 13.7 step 5 to 10 s, 13.5 (debug None / Wireframe / LOD tint), 19.3 (WP09 owns `main.js`).
- Expected: the tour turns LOD tint and wireframe on together. WP09's `setDebug` takes one of `none`, `wireframe`, `lod`.
- Change: two lines in `viewer/src/main.js` `applyUniformsFromLook` also accept `both`. Only the tour sets it. The HUD radio shows LOD tint while it is active.
- Why: DRAFT, for Bradd to write in his own words.

### D-09b (WP10) Entity exports are not built yet

- Spec section: 19.4 (WP10 done: SCN-04 passes from `bench.json`), 12.8 SCN-04.
- Expected: `dist/entities/<entity>/entity.json` exists, so SCN-04 can compare live and static counts.
- Observed: `dist/entities` is absent until WP11 is merged and `tilepipe entities` runs. SCN-04 requires the exported counts (D-07), so it fails with "missing entity.json". With a throwaway set of three synthetic cube entities (not committed, deleted afterwards), the same bench path gave live counts equal to the static counts and SCN-04 passed for both profiles, which shows the viewer and the rule agree.
- Change: none to thresholds or rules. The orchestrator re-runs `?bench=1` and `validate` after WP11.
- Resolved 2026-11-15: after WP11 merged, the orchestrator re-ran `?bench=1` and `validate`. SCN-04 passes for both profiles with the real entities.

### D-09c (WP10f, recorded by the orchestrator) Repository link from `site/config.json`

- Spec section: 13.5 (About panel), 13.9 (`site/config.json`), 16.2 G7, 17.10.
- Expected: `site/config.json` holds the publish-time values of G7. 17.10 forbids usernames in committed or shipped files.
- Observed: the About panel hardcoded the repository URL, and that URL contains a username.
- Change: `viewer/src/hud.js` no longer contains a URL. `site.py` writes `{"repo_url": "", "video_url": ""}` by default. The About panel shows "Repository not yet published" until `repo_url` holds an http(s) URL. `repo_url` is a key the spec does not list, so the G7 step that writes `video_url` must write `repo_url` too. No threshold, budget, or rule changes.
- Why: DRAFT, for Bradd to write in his own words.

### D-11 (WP07f) Fixture verdicts in `validate`

- Spec section: 4.3, 12.1, 12.9, 16.2 G5 and G6.
- Expected: 4.3 says `validate` exits 1 when a FAIL-severity rule fails. 12.9 says each fixture's failing set MUST equal its expected set. G6 needs `tilepipe all` to exit 0. The spec does not say how fixture results count toward the exit code.
- Observed: `validation.json` carries 13 FAIL records under `fixture:` scopes, all of them the expected ones, so `validate` exited 1 and G6 could not pass.
- Change: `validate` still records those results as FAIL. Its exit code ignores a `fixture:` FAIL only when the fixture's failing set equals its set in `assets/fixtures/expected.json`. A fixture whose set differs, or an expected fixture with no results, exits 1. FAILs under every other scope still exit 1. No threshold, budget, or rule changes.
- Why: DRAFT, for Bradd to write in his own words.

### D-12 (WP07f) PAY-01 fails after a clean `tilepipe all` order

- Spec section: 4.2 (`all`), 9.1, 12.5 (PAY-01).
- Expected: `build, entities, validate, site` leaves PAY-01 passing.
- Observed: the manifest counts the drawn entity GLBs in `dist/entities/` when `build` runs, before `entities` has created them. After `rm -rf dist/entities`, `build`, `entities`, `validate` gives PAY-01 FAIL on both profiles (measured 9117813 vs 9162285, and 12101709 vs 12208697). A second run passes only because `dist/entities/` survives.
- Change: none in WP07f paths. The manifest must be rewritten after `entities` in `all`: the fix belongs in `tilepipe.entities.run` (WP11) or the `all` step of `cli.py` (WP02), not in `validate/`.
- Why: DRAFT, for Bradd to write in his own words.

### D-13 (WP08) Report header date

- Spec section: 14.1 item 1, 6.7.
- Expected: the header shows the build date.
- Observed: the only build date is `finished_utc` in `build_info.json`, which differs on every build, so the report would not be reproducible. The WP08 brief also bars timestamps.
- Change: the header and provenance show the source retrieval date (a date, from `tile.json`), and the header says the build records no date in this file. No threshold, budget, or rule changes.
- Why: DRAFT, for Bradd to write in his own words.

### D-12 update (WP11f) Fix applied

- Change: `tilepipe.entities.run` calls `manifest.run(root, default_aoi)` after a successful gate, when `build/<aoi>/geo.json` exists, so `tile.json` and `outputs.sha256` count `dist/entities/`. No signature, threshold, or rule changed.
- Result: `build`, `entities`, `validate` on a clean tree passes PAY-01 on both profiles (9162285 and 12208697 bytes). `entities --no-blender` copies the committed exports and yields a byte-identical `outputs.sha256`.
- Open: `tilepipe all` still exits 2 at `site` (WP10 not merged, stub).

### D-14 (WP06f) validation.json is not listed in outputs.sha256

- Spec section: 7.8, 6.7, 12.2 (DET-01).
- Expected: `outputs.sha256` lists every file in `dist/<aoi>/` except itself (7.8) and is identical on a clean re-run (6.7).
- Observed: after a clean `tilepipe all`, `outputs.sha256` had 104 lines because `validate` runs after the manifest. On the next run `validation.json` existed, so the list had 105 lines and its hash changed with each run.
- Change: `hashing.write_outputs_sha256` also skips `validation.json`. It is written after the manifest and carries the DET-01 comparison of the list, so listing it is circular, and fixing it the other way would need a change in `validate/`. The list is now the same on a clean and a repeated run. No threshold, budget, or rule changes.
- Why: DRAFT, for Bradd to write in his own words.

### D-15 (WP07g) Khronos validator output was not logged

- Spec section: 3.3 rule 7, 12.5 (GLB-01).
- Expected: stdout and stderr of every orchestrated subprocess are captured to `build/logs/<stage>.log`.
- Observed: `rules_tex.run_validator` captured the node output in memory and wrote nothing to `build/logs/`.
- Change: `run_validator` takes an optional log path. GLB-01 passes `build/logs/gltf_validator.log`, which holds the exit code and output of each node call and carries no timestamp. The log is under `build/`, not `dist/`, so absolute paths in it are allowed. No threshold, budget, or rule changes.
- Resolved by WP11g: `tilepipe.entities.deliverable_gate` writes `build/logs/gltf_validator_entities.log`.

### D-16 (WP09f) Viewer default AOI

- Spec section: 13.2 step 1, 17.14.
- Expected: 13.2 reads `?aoi=` with a literal default AOI id.
- Observed: a literal AOI id in viewer code breaks 17.14, and 17 wins a conflict.
- Change: the viewer reads `?aoi=`, else the `aoi` key of `site/config.json`, else it shows a load error. `tests/viewer_check.mjs` writes `aoi` (the first `aois.toml` AOI with a built tile) into its config.json and fails if any `aois.toml` id appears under `viewer/src`. No threshold, budget, or rule changes.
- Resolved by WP10g: `tilepipe site` writes `aoi` into `config.json`, merged into a kept file, and `tests/test_site.py` accepts the key.
- Why: DRAFT, for Bradd to write in his own words.
