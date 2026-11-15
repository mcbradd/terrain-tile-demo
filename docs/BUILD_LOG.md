# Build log

One row per work package, kept current by the orchestrating session.

| Package | Status | Model | Effort | Attempts | Validation |
| --- | --- | --- | --- | --- | --- |
| WP01 | Accepted, merged | sonnet | medium | 1 | Orchestrator re-run: uv sync --no-build 0; npm ci 0; preflight 0 (PF-01 to PF-07 PASS); pytest -k OFFLINE 0 (1 passed). Deviations D-01 to D-03 logged |
| WP02 | Accepted, merged; contracts frozen | opus | high | 1 | Orchestrator re-run: uv sync 0; pytest -k schema 0 (31 passed); META-01/03/04 tests 0 (8 passed); --help 0 (12 commands, profile set-share); preflight 0. Sweep: 0 section 12 rule IDs missing from registry. Deviation D-04 logged |
| WP03 | Accepted, merged; G1 machine conditions pass, [HUMAN] sign-off pending | sonnet | high | 1 | Orchestrator re-run: fetch 0 (no-op); build --to prep 0 (DG-01 to DG-06 pass); pytest -k "PNG or guard" 0 (11 passed). Scan clean |
| WP04 | Accepted, merged | opus | high | 1 (restarted fresh after usage-limit stop) | Orchestrator re-run: build --to batch 0; pytest -k "LOD or SELECT or SKIRT or GLB" 0 (17 passed); 80 chunk + 20 batch GLBs (4 mobile_ar, 16 workstation); Khronos validator 100 checked, 0 with errors or warnings; lod_stats.json written |
| WP05 | Accepted, merged | sonnet | high | 1 | Orchestrator re-run on real prep output: build --from bake --to bake 0; sizes 2097152 and 5592404 exact; pytest -k "CODEC or normal or AO" 0 (6 passed) |
| WP06 | Accepted, merged; G2 pass | sonnet | medium | 1 | Orchestrator re-run: build 0 twice, outputs.sha256 byte-identical; tile.json schema-valid; textures exact; no abs paths in dist; full pytest 0 (72 passed); scene file committed and unchanged |
| WP07 | Accepted, merged; G3 pass; fix package WP07f in progress | sonnet | high | 1 (continued after usage-limit stops) | Orchestrator re-run after merging main: validate --skip-entities 0 (45 PASS, 2 WARN TER-09, 0 FAIL, 68 SKIP); JSON and JUnit written; pytest -k "REG or rule" 0 (99 passed); full pytest 0 (180 passed); forced failure (nao truncated 1 byte) exit 1, TEX-01/TEX-02 messages per 12.1. DECISIONS merge conflict (D-07 vs D-08) resolved keeping both. Deviation D-07 logged |
| WP08 | Not started | sonnet | medium | 0 | |
| WP09 | Accepted, merged (branch WP09r) | opus | high | 1 (continued after usage-limit stops) | Orchestrator re-run: node tests/viewer_check.mjs 0 (7 checks: 4 profile/look renders, profile switch, same-origin only, fallback page); full pytest 0 (83 passed, incl. TEX-05, no three.js chunks, WebGL2 compile). site/serve are WP10 stubs. Entity render not checkable until WP11 merges: re-check owed at WP10 and WP14. Deviation D-08 logged |
| WP10 | In progress (fresh restart after 3rd usage-limit stop; nothing salvaged) | sonnet | high | 1 | |
| WP11 | Accepted, merged (branch WP11s) | opus | high | 1 (continued across 3 usage-limit stops) | Orchestrator re-run: extension validate 0; tilepipe entities 0 (3 entities, 19 deliverable checks, 0 errors); pytest -k blender 0 (4 passed); 9 entity GLBs committed; validate: ENT/ENTD all PASS for the 3 entities, the only 13 FAILs are the 12 fixtures failing on purpose. Open, sent to WP07 fix: validate exits 1 on fixture FAILs; 3 tests in test_rules_core.py hit FileExistsError once dist/entities exists. Deviation D-05 logged |
| WP12 | Not started | sonnet | low | 0 | |
| WP13 | Not started | sonnet | medium | 0 | |
| WP14 | Not started | opus (verifier) | xhigh | 0 | |
