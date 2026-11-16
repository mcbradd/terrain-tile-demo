# Standards

## Units and axes

All runtime data is in meters. The tile-local frame is right-handed and Y-up. The origin is the tile's northwest corner at elevation 0. +X is east, +Y is up, +Z is south. Data on disk is always true scale. Exaggeration is applied only at draw time.

Entities use Y up and meters as well.

## Naming

All identifiers are ASCII lower snake case, except the `_LOD<n>` suffix and the `M_` prefix.

| Thing | Pattern | Example |
| --- | --- | --- |
| AOI | `<place>_<nn>` | `anza_borrego_01` |
| Chunk | `c<cx>_<cz>` | `c2_0` |
| Entity | `ent_<class>_<descriptor>_<variant>` | `ent_vehicle_wheeled_a` |
| Entity mesh data | `<entity>_LOD<n>` | `ent_vehicle_wheeled_a_LOD1` |
| Entity material | `M_<entity>` | `M_ent_vehicle_wheeled_a` |
| Entity GLB | `<entity>_LOD<n>.glb` | `ent_vehicle_wheeled_a_LOD1.glb` |

## Entity LOD limits

Read from `entity_lods.toml`.

| LOD | View distance | Triangles at most |
| --- | --- | --- |
| 0 | 0.30 m | 7000 |
| 1 | 0.75 m | 1500 |
| 2 | 1.50 m | 400 |

## Where the gate runs

| Place | Who runs it | How |
| --- | --- | --- |
| Authoring, in the DCC | The artist | `Validate Asset` in the Blender panel runs the source gate. |
| Submit | The artist, or a submit hook | `uv run tilepipe presubmit <files>` runs the source gate on each `.blend` and the deliverable gate on each `.glb`. The exit code is 1 on any FAIL. |
| Build, in CI | The CI system | `uv run tilepipe validate` runs every rule. The deliverable gate needs no Blender. |

## Add a rule

1. Write the check in `src/tilepipe/validate/rules_*.py` with `@implements("<ID>")`. The ID must already be in the registry catalog.
2. Add a passing case and a failing case named `test_rule_<FAMILY>_<nn>_pass` and `test_rule_<FAMILY>_<nn>_fail`. Rule REG-01 fails without them.
3. Run `uv run pytest`, then `uv run tilepipe validate`.

## Add a profile

1. Copy `profiles/workstation.toml` to `profiles/<name>.toml`.
2. Set the anchor, the shares, and the budget. The budget must equal anchor times share (rule META-01). Mark every assumed value `ASSUMED`.
3. Run `uv run tilepipe build`, then `uv run tilepipe validate`.

## Artist quickstart (10 minutes)

1. Build the extension zip from `blender/tilepipe_tools` and install it in Blender through Preferences, Get Extensions, Install from Disk.
2. In the add-on preferences, set `repo_root` to the repository folder.
3. Copy `assets/entities/_template/ent_template.blend` to `assets/entities/<entity>/<entity>.blend` and rename the collection to match.
4. Model within the LOD limits. In the sidebar tab `Tile Pipeline`, press `Validate Asset`. Click a failing row to select the object.
5. Press `Export Asset`. It writes three GLBs and a partial `entity.json` under `assets/entities/<entity>/export/`.

## Accuracy statement

> Horizontal: source resampled bilinearly to a 10 m grid in WGS84 / UTM. The NAD83 to WGS84 transformation is whatever PROJ selects for this CRS pair. The GDAL version is recorded in build\_info.json; the PROJ pipeline string is not captured in `tile.json`. Treat horizontal accuracy as plus or minus one cell (10 m). Vertical: NAVD88 orthometric heights in meters. No vertical datum conversion is applied. Heights are not ellipsoidal (HAE) and not EGM96. A consumer that needs HAE must apply a geoid model.

## Integration note

Binary source art such as `.blend` files belongs under exclusive checkout in a centralized version control system such as Perforce. Not implemented here.
