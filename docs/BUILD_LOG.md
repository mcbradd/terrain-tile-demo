# Build log

One row per work package, kept current by the orchestrating session.

| Package | Status | Model | Effort | Attempts | Validation |
| --- | --- | --- | --- | --- | --- |
| WP01 | Accepted, merged | sonnet | medium | 1 | Orchestrator re-run: uv sync --no-build 0; npm ci 0; preflight 0 (PF-01 to PF-07 PASS); pytest -k OFFLINE 0 (1 passed). Deviations D-01 to D-03 logged |
| WP02 | Accepted, merged; contracts frozen | opus | high | 1 | Orchestrator re-run: uv sync 0; pytest -k schema 0 (31 passed); META-01/03/04 tests 0 (8 passed); --help 0 (12 commands, profile set-share); preflight 0. Sweep: 0 section 12 rule IDs missing from registry. Deviation D-04 logged |
| WP03 | In progress | sonnet | high | 1 | |
| WP04 | In progress | opus | high | 1 | |
| WP05 | In progress | sonnet | high | 1 | |
| WP06 | Not started | sonnet | medium | 0 | |
| WP07 | Not started | sonnet | high | 0 | |
| WP08 | Not started | sonnet | medium | 0 | |
| WP09 | Not started | opus | high | 0 | |
| WP10 | Not started | sonnet | high | 0 | |
| WP11 | Not started | opus | high | 0 | |
| WP12 | Not started | sonnet | low | 0 | |
| WP13 | Not started | sonnet | medium | 0 | |
| WP14 | Not started | opus (verifier) | xhigh | 0 | |
