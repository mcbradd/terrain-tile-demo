# Verification log

Dated checks. An entry marked "agent" was run by an AI agent on the build machine and is pending Bradd's review. Bradd fills the rest.

## AOI sign-off (gate G1)

- [HUMAN] Date: 2026-11-18 (agent)
- [HUMAN] Result: PASS (agent). Both previews show Anza-Borrego desert relief, north up, no holes or stripes. Relief 1610.6 m, 0 NoData cells. DG-01 to DG-06 PASS. Pending Bradd's visual sign-off.

## MGRS cross-check

- [HUMAN] Date: 2026-11-18 (agent)
- [HUMAN] Tile-center MGRS from `prep`: 11SNS5307082470 (lat 33.279970, lon -116.430092)
- [HUMAN] MGRS from an independent converter: 11SNS5307082470 (pygeodesy 26.11.11 with pyproj 3.8.0)
- [HUMAN] Result: PASS (agent). 0 m difference. The viewer probe shows the same string.

## Browser matrix

- [HUMAN] Date: 2026-11-18 (agent)
- [HUMAN] Browsers and versions checked: Chrome 157.0.8103.79, Edge 157.0.4341.60, Playwright Firefox 159.0, Playwright WebKit 27.2, all PASS (first frame under 1 s, all controls, tour, probe exact, same-origin only). Pacing fraction 0.005. Safari not tested (no Apple device).

## Entity front-direction check in the viewer

- [HUMAN] Date: 2026-11-18 (agent)
- [HUMAN] Result per entity: vehicle PASS, mast PASS, uas PASS (checked from geometry and top-down views, not close up).

## Art-lock hashes

- [HUMAN] Date: 2026-11-18 (agent)
- [HUMAN] Hashes of `look/*.json`: additive.json sha256 7d6c9beedf1000872ad061b276328ff195c5d1cdec31d215659c03288c0ab044; opaque.json sha256 42d4a4fcb6d98f0ee91779ec6115c7337b6bc3ff74fbf416eeac1b6cc72da26f. LOOK-01 to LOOK-05 PASS.

## Drill rehearsals

- [HUMAN] D1 retarget budget, rehearsal 1 and 2:
- [HUMAN] D2 break and fix an asset, rehearsal 1 and 2:
- [HUMAN] D3 build a new place, rehearsal 1 and 2:
- [HUMAN] D4 defend the decisions, rehearsal 1 and 2:

## Video claims check

- [HUMAN] Date:
- [HUMAN] Result:

## Approved threshold changes

- [HUMAN] None approved, or list each with date and reason: five approved by Bradd on 2026-11-17, listed below.

Approved by Bradd on 2026-11-17 in the orchestrator session, on the WP14 audit findings. Recorded by the orchestrator. No threshold or budget value changes.

1. 17.13 and 9.1: `retrieved_utc` stays in `tile.json`. It is the fixed retrieval time of the source data, not a build time, and it does not change between builds.
2. 17.10 and PF-01: the standard Blender install path is allowed in exactly one place, the preflight lookup. The lookup order is environment variable, then PATH, then that default. Tests import it from there. The username literal in tests is removed.
3. Profile verdict: a profile with 0 FAIL and only WARN results has the verdict PASS. The warning count is shown beside the verdict, and each WARN rule row still shows WARN.
4. Frozen contract change: `build_info.json` gains Blender and GDAL version fields. The Blender version comes from metadata recorded at entity export, so `all` and `all --no-blender` write the same file.
5. OFF-01 is widened to cover all of `tilepipe all`, including the node and Blender subprocesses.
