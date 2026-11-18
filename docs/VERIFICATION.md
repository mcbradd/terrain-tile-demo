# Verification log

Dated human checks. Bradd fills every entry. Agents leave them empty.

## AOI sign-off (gate G1)

- [HUMAN] Date:
- [HUMAN] Result:

## MGRS cross-check

- [HUMAN] Date:
- [HUMAN] Tile-center MGRS from `prep`:
- [HUMAN] MGRS from an independent converter:
- [HUMAN] Result:

## Browser matrix

- [HUMAN] Date:
- [HUMAN] Browsers and versions checked:

## Entity front-direction check in the viewer

- [HUMAN] Date:
- [HUMAN] Result per entity:

## Art-lock hashes

- [HUMAN] Date:
- [HUMAN] Hashes of `look/*.json`:

## Drill rehearsals

- [HUMAN] D1 retarget budget, rehearsal 1 and 2:
- [HUMAN] D2 break and fix an asset, rehearsal 1 and 2:
- [HUMAN] D3 build a new place, rehearsal 1 and 2:
- [HUMAN] D4 defend the decisions, rehearsal 1 and 2:

## Video claims check

- [HUMAN] Date:
- [HUMAN] Result:

## Approved threshold changes

- [HUMAN] None approved, or list each with date and reason:

Approved by Bradd on 2026-11-17 in the orchestrator session, on the WP14 audit findings. Recorded by the orchestrator. No threshold or budget value changes.

1. 17.13 and 9.1: `retrieved_utc` stays in `tile.json`. It is the fixed retrieval time of the source data, not a build time, and it does not change between builds.
2. 17.10 and PF-01: the standard Blender install path is allowed in exactly one place, the preflight lookup. The lookup order is environment variable, then PATH, then that default. Tests import it from there. The username literal in tests is removed.
3. Profile verdict: a profile with 0 FAIL and only WARN results has the verdict PASS. The warning count is shown beside the verdict, and each WARN rule row still shows WARN.
4. Frozen contract change: `build_info.json` gains Blender and GDAL version fields. The Blender version comes from metadata recorded at entity export, so `all` and `all --no-blender` write the same file.
5. OFF-01 is widened to cover all of `tilepipe all`, including the node and Blender subprocesses.
