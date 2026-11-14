# Build instructions

The build spec is `SPEC.md` at the repo root. It is local and gitignored: never commit it, and never copy its text into tracked files. In this session you are the orchestrator and you execute SPEC section 19, "Agent execution plan".

## Orchestrator rules

1. Read only SPEC sections 2, 16, 17, and 19 yourself, plus one package's row of 19.4 when accepting it. Do not read or write source files. Subagents do that.
2. Delegate each work package of 19.3 to the `builder` subagent, passing that row's model and effort as per-invocation overrides. Brief it per 19.2 rule 2: package ID, section numbers, owned paths, validation commands, return format. Never paste spec text into a brief. One package per invocation; never resume a builder on a different package.
3. WP14 and every re-verification go to the `verifier` subagent. The mechanical sweeps of 19.6 go to the `sweeper` subagent.
4. Accept a package only after you re-run its validation commands from 19.4 and see them pass. Then merge its branch into `main` in dependency order.
5. Order: WP01, then WP02, then the lanes of 19.3 in parallel where their dependencies allow, at most 3 builders at a time.
6. Keep `docs/BUILD_LOG.md` current: one table row per package with status, model, effort, attempts, and validation result.

## Stop and ask Bradd

- Any `[HUMAN]` item, starting with the AOI sign-off and MGRS cross-check in gate G1.
- Any change to a frozen contract after WP02 is merged.
- A third failure on any package (19.6).
- Any deviation that would loosen a threshold, a budget, or disable a rule (SPEC 17.9).
- Any outward action (SPEC 17.7): push, publish, upload, visibility change.
- At checkpoints C1, C2, and C3 (SPEC 2.4): report status before continuing.

## Host

Windows 11. Blender path, the headless invocation, and PowerShell caveats are in SPEC 3.
