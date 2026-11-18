# tilepipe contracts

This file is frozen after WP02. A change needs the orchestrator's approval and a Deviations record in
`docs/DECISIONS.md`. Section numbers refer to the build spec.

## 1. Shared rules

- Every command runs from the repo root. `root` below is that directory as a `Path`. `aoi` is an AOI id from
  `aois.toml`. When `--aoi` is omitted, the CLI uses the first AOI in `aois.toml`.
- Configuration is read only through `tilepipe.config` (section 3). No module hard-codes an AOI, profile, LOD,
  or look value.
- JSON files are written only with `config.write_json`. It sorts keys, indents by two spaces, rounds floats to 6
  places, refuses NaN and Infinity, and writes UTF-8 with LF line endings. Pass Python `int` and `float` values.
  Convert numpy scalars first; `np.float32` is not a `float`.
- Errors map to exit codes by exception class (4.3): `RuleFailure` 1, `UsageError` 2, `EnvError` 3,
  `GuardError` 4. The CLI catches `TilepipeError`, prints the message, and exits with `e.code`. A stub raises
  `NotImplementedError`, which the CLI reports with exit 2.
- Nothing under `dist/` contains a timestamp, hostname, or absolute path. Those go only in
  `build/<aoi>/build_info.json`.
- `B = build/<aoi>/`, `D = dist/<aoi>/`.

## 2. Pipeline stages

`tilepipe build [--from S] [--to S]` runs `config.STAGES` in order: prep, lod, bake, export, batch, scene,
manifest. `cli.build` times each stage and merges `{"stage_seconds": {stage: s}, "total_seconds": s, "host",
"finished_utc", "gdal_version", "blender_version"}` into `B/build_info.json`. A stage reads only committed inputs
and earlier outputs listed here.

`cli.tool_versions(root) -> dict` gives the two version strings. `gdal_version` is `rasterio.__gdal_version__`.
`blender_version` is `bpy.app.version_string` as recorded at entity export: `export_asset` writes it into the
partial `assets/entities/<entity>/export/entity.json`, and `entities.complete` drops it from the `dist/` copy (9.2).
Distinct values are sorted and joined with `", "`; `"not recorded"` if none. Blender is not run for this, so
`all` and `all --no-blender` record the same versions (VERIFICATION.md approved change 4).

| Stage | Function | Reads | Writes |
| --- | --- | --- | --- |
| fetch (not in build) | `tilepipe.fetch.fetch(root: Path, aoi: str) -> None` | `aois.toml`, network | `data/source/<aoi>_src.tif`, `data/source/<aoi>_src.json` |
| prep | `tilepipe.prep.run(root: Path, aoi: str) -> None` | `aois.toml`, `data/source/<aoi>_src.tif` | `B/h_full.npy`, `B/geo.json`, the two preview PNGs of 5.6 in `B/` |
| lod | `tilepipe.lod.run(root: Path, aoi: str) -> None` | `B/h_full.npy` | `B/lod_stats.json` |
| export | `tilepipe.lod.export(root: Path, aoi: str) -> None` | `B/h_full.npy`, `B/geo.json`, `B/lod_stats.json` | `D/terrain_<chunk>_lod<k>.glb`, 80 files |
| bake | `tilepipe.bake.run(root: Path, aoi: str) -> None` | `B/h_full.npy`, `B/geo.json` | `D/terrain_height.rg8.bin`, `D/terrain_nao.rgba8.bin` |
| batch | `tilepipe.batch.run(root: Path, aoi: str) -> None` | `B/lod_stats.json`, `D/terrain_*_lod*.glb`, `profiles/*.toml` | `D/terrain_<profile>_b<nn>.glb`, `B/selection.json` |
| scene | `tilepipe.scene.run(root: Path, aoi: str, regen: bool = False) -> None` | `B/h_full.npy`, `B/geo.json` | `scene/<aoi>_scene.json` (committed) |
| manifest | `tilepipe.manifest.run(root: Path, aoi: str) -> None` | all of the above, `profiles/*.toml`, `entity_lods.toml`, `look/*.json`, `assets/entities/*/export/`, `viewer/src/shaders/terrain.frag.glsl` | `D/tile.json`, `D/scene.json`, `D/outputs.sha256` |

Stage behavior notes:

- `scene.run` with `regen=False` writes the file if it is absent. If the file exists, it recomputes the placement
  in memory and raises `RuleFailure` unless the two are identical. `regen=True` overwrites (`tilepipe scene --regen`).
- `batch.run` raises `RuleFailure` if a profile's budget is unreachable at LOD 4 everywhere (7.6).
- `manifest.run` validates `tile.json` with `config.check_schema(doc, "tile", "tile.json")` before writing it.
- Guards raise `GuardError(guard_id, measured, expected)`.

### 2.1 Intermediate file formats

`B/h_full.npy`: float32, shape `[1152, 1152]`, row 0 north, column 0 west (6.2).

`B/geo.json`:

```json
{"zone": 11, "epsg": 32611, "E0": 0.0, "N0": 0.0, "N_top": 0.0, "h_min": 0.0, "h_max": 0.0, "mgrs_center": "..."}
```

`mgrs_center` is `null` if P0.9 is cut.

`data/source/<aoi>_src.json` (provenance): at least `{"urls": [...], "retrieved_utc": "YYYY-MM-DDTHH:MM:SSZ",
"crop_sha256": "<hex>"}`. The manifest's `source` block reads it.

`B/lod_stats.json`: `e_max_m[k]` and `e_rms_m[k]` for `k = 0..4`. `skirt_depth_m[k]` is `D_k`.

```json
{"chunks": {"c0_0": {"e_max_m": [0.0, 0.0, 0.0, 0.0, 0.0], "e_rms_m": [0.0, 0.0, 0.0, 0.0, 0.0]}},
 "skirt_depth_m": [1.0, 0.0, 0.0, 0.0, 0.0]}
```

All 16 chunk ids are present.

`B/selection.json`: one entry per profile. The keys are a subset of the `tile.json` profile entry (9.1):
`tau_target_m`, `e_star_m`, `budget_forced`, `error_px_nominal`, `error_px_v3`, `selection`, `terrain_tris`,
`terrain_draws`, and `batches`. Each batch entry has `file`, `chunks`, `vertices`, `tris`, `index_type`, `bytes`,
and `aabb`. The manifest adds the batch `sha256` plus `texture_bytes`, `terrain_tex_samples`,
`web_payload_bytes`, and `entity_lod`.

`scene/<aoi>_scene.json`, with `D/scene.json` a byte copy. `x` and `z` are TL meters at the cell center, `cell`
is `[r, c]` of the tile cell, and `entity` is an id from `assets/entities/`. Instances are listed in placement order.

```json
{"schema": 1, "aoi": "<aoi>", "instances": [
  {"entity": "ent_vehicle_wheeled_a", "cell": [0, 0], "x": 5.0, "z": 5.0, "heading_deg": 0, "hover_table_m": 0.0}]}
```

`D/outputs.sha256`: one line per file in `D/` except itself, sorted by POSIX relative path, written as
`<sha256 hex><two spaces><path>\n`.

## 3. Shared modules

`tilepipe.config` is implemented by WP02 and frozen.

```python
STAGES: tuple[str, ...]
class TilepipeError(Exception): code: int        # UsageError 2, RuleFailure 1, EnvError 3, GuardError 4
class GuardError(TilepipeError): def __init__(self, guard: str, measured, expected)
def load_schema(name: str) -> dict                # name: tile|validation|profile|entity|look|aois
def schema_errors(instance, name: str) -> list[str]
def check_schema(instance, name: str, what: str) -> None   # raises UsageError
def load_aois(root: Path) -> dict[str, dict]
def default_aoi(root: Path) -> str
def load_aoi(root: Path, aoi: str) -> dict        # record plus "id"
def load_profile(path: Path) -> dict
def load_profiles(root: Path) -> dict[str, dict]  # sorted by name
def load_entity_lods(root: Path) -> dict          # d["lod"][n]
def load_looks(root: Path) -> dict[str, dict]     # {"additive": ..., "opaque": ...}
def build_dir(root: Path, aoi: str) -> Path
def dist_dir(root: Path, aoi: str) -> Path
def dumps_json(obj) -> str
def write_json(path: Path, obj) -> None
```

The following are stubs from WP02, implemented by the named package:

```python
# geo.py (WP03)
def tile_geometry(aoi: dict) -> dict   # {"zone","epsg","E0","N0","N_top"} per 5.3
# png.py (WP03)
def write_png(path: Path, image: np.ndarray) -> None   # uint8, HxW (gray), HxWx3 or HxWx4
# glb.py (WP04)
def write_glb(path: Path, positions: np.ndarray, indices: np.ndarray) -> int   # float32 (N,3); uint16|uint32 (3M,); returns bytes written
def parse_glb(data: bytes) -> tuple[dict, bytes]                # (JSON chunk, BIN chunk), any GLB
def read_mesh(path: Path) -> tuple[np.ndarray, np.ndarray]      # (positions, indices) of a terrain GLB
# batch.py (WP04)
def tau(profile: dict) -> float                                 # 8.3, meters
def error_px(e_m: float, profile: dict, exaggeration: float) -> float   # 8.3 inverse
def select(lod_stats: dict, tau_m: float, terrain_tris_max: int) -> dict
    # {"selection": {chunk: k}, "e_star_m", "budget_forced", "terrain_tris"}; used by batch.run and TER-08
# hashing.py (WP06)
def sha256_file(path: Path) -> str
def write_outputs_sha256(dist: Path) -> None
```

## 4. Commands

| Command | Function | Reads | Writes |
| --- | --- | --- | --- |
| `preflight` | `cli.preflight(root) -> int` (WP01) | toolchain | `build/preflight.json` |
| `entities [--no-blender]` | `tilepipe.entities.run(root, no_blender: bool = False) -> int` (WP11) | `assets/entities/`, `entity_lods.toml` | `dist/entities/<entity>/entity.json` and `<entity>_LOD<n>.glb`, `build/entities/ent_results.json` |
| `validate [--skip-entities] [--determinism]` | `tilepipe.validate.runner.run(root, aoi, skip_entities=False, determinism=False) -> int` (WP07) | everything | `D/validation.json`, `B/validation.junit.xml`, `site/report/index.html` |
| `site` | `tilepipe.site.build(root, aoi) -> None` (WP10) | `dist/`, `viewer/` | `site/` |
| `serve` | `tilepipe.site.serve(root, port=8000) -> None` (WP10) | `site/` | none |
| `all [--no-blender]` | `cli._dispatch`: build, entities, validate, site; stops at the first nonzero code | | |
| `scene --regen` | `tilepipe.scene.run(root, aoi, regen=True)` (WP06) | | `scene/<aoi>_scene.json` |
| `profile set-share <profile> <share>` | `tilepipe.presubmit.set_share(root, profile, share) -> None` (WP12). The CLI checks that the profile exists and the share is in (0, 1] | `profiles/<profile>.toml` | same file, with the content share and every derived budget line rewritten |
| `presubmit <files...>` | `tilepipe.presubmit.run(root, files: list[Path]) -> int` (WP12) | `.blend`, `.glb` | stdout |
| `licenses` | `tilepipe.licenses.run(root) -> None` (WP12) | package metadata | `docs/PROVENANCE.md` table |

The report renderer (WP08) is called by the validate runner as
`tilepipe.report.render.render(root: Path, aoi: str, validation: dict) -> Path`. `validation` is the
`validation.json` document, and the function returns the path written.

`build/entities/ent_results.json` holds a JSON list of result records (section 5) for every ENT rule on every
entity and fixture, written by the Blender source gate. The validate runner merges it into `validation.json`. If
the file is absent, the runner records the ENT rules as SKIP with a reason.

`build/<aoi>/bench.json` is written by the viewer's bench mode (13.8). SCN-04 and PERF-01 read it.

## 5. Validator

`tilepipe.validate.registry` is implemented by WP02 and frozen.

- `CATALOG` lists every rule ID of section 12 as `(id, severity, scope_kind, doc)`. `RULES: dict[str, Rule]` is
  built from it. Each rule starts as a stub returning SKIP with reason `not implemented`.
- A check has the signature `check(ctx: Context, scope: str) -> Result`. The runner calls it once per scope of
  the rule's kind: `tile`; `profile:<name>` for each profile; `entity:<id>` for each entity; `fixture:<id>` for
  each fixture (ENT rules only); `repo`.
- Rule modules attach checks with `@registry.implements("TER-01")`. That sets `RULES["TER-01"].stub = False`.
  `registry.stubs()` lists the IDs still unimplemented. The runner imports every `rules_*.py` before it runs.
- `Context(root, aoi, profiles, looks, entity_lods, options, cache)`. `options` holds `skip_entities`,
  `determinism`, and `no_blender`. `cache` is a free dict for memoized artifacts.
- `Result` fields in order: `rule, severity, status, scope, measured, limit, unit, message, fix_hint`.
  `Result.to_dict()` gives the record of `validation.json`.
- Build results only with these helpers. They make the message follow 12.1:
  - `result(rule_id, scope, status, measured, limit, unit="", op="<=", fix_hint="")`
  - `check_result(rule_id, scope, ok, measured, limit, unit="", op="<=", fix_hint="")`. It returns PASS, or the
    rule's severity on failure.
  - `skip(rule_id, scope, reason)`. The message is `<RULE> SKIP <scope>: <reason>.`, and `measured` and `limit`
    are null.
- `validation.json` is `{"schema": 1, "aoi", "results": [record...], "summary": {scope: {"pass", "fail", "warn",
  "skip"}}}` and validates against `validation.schema.json`.
- `validation.junit.xml`: one `testsuite` per scope, one `testcase` per rule, and a `failure` element carrying the
  message for FAIL status.

## 6. Schemas

`src/tilepipe/schema/` contains six schemas, all JSON Schema draft 2020-12 with `additionalProperties: false` on
every object. Maps such as `profiles`, `selection`, and `summary` use `patternProperties`.

| Schema | Instance |
| --- | --- |
| `aois.schema.json` | `aois.toml` parsed with `tomllib` |
| `profile.schema.json` | each `profiles/*.toml`. The `name` must equal the file stem |
| `look.schema.json` | each `look/*.json`. `mode` must equal the file stem. `bg_gain` and `display_gain` are required for additive and absent for opaque |
| `tile.schema.json` | `dist/<aoi>/tile.json`, with exactly 2 textures, 16 chunks, 5 LODs per chunk, and 16 selection entries. `mgrs` is optional |
| `entity.schema.json` | `dist/entities/<entity>/entity.json`, with exactly 3 LODs |
| `validation.schema.json` | `dist/<aoi>/validation.json` |

`entity_lods.toml` has no JSON schema. `config.load_entity_lods` checks its shape, and META-04 checks its values.

Look files store the ramp as `[{"t": 0.0, "srgb": "#6B6A5E"}, ...]` in ascending `t`, with uppercase hex colors.
