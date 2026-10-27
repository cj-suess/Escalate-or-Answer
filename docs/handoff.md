# Handoff: 27 October 2026

## Current state
- **Planned change 11 is built** (`system/PLANNED_CHANGES.md` §11) on branch `session-data-integrity`, which is pushed to origin and not merged into `main`.
  - Plan: `docs/superpowers/plans/2026-10-27-session-data-integrity.md`.
  - Commits: `b607b80..` on the branch. Python tests pass 20/20 and JS tests 17/17 (commands in `system/README.md`).
  - Worktree: `.claude/worktrees/session-data-integrity`. The main checkout is on `main`, clean.
- **The PR is not opened yet.** The `gh` CLI isn't installed and the GitHub connector failed. Open it by hand: https://github.com/cj-suess/Escalate-or-Answer/pull/new/session-data-integrity (base `main`). The PR text was drafted in the previous session; rebuild it from the plan and the commit messages if needed.
- **An architecture review is published:** https://claude.ai/artifact/LbbnchdVaGgyp4DXp1Nban (private). It has six deepening candidates. The user was asked "Which of these would you like to explore?" and has not answered yet.
- Operational traps and verification recipes: `docs/operations.md`.

## Next step
Wait for the user to pick a candidate from the architecture review. Then run the grilling loop from the improve-codebase-architecture skill: constraints, the shape of the deepened module, what sits behind the seam, which tests survive. Create `CONTEXT.md` lazily when a new domain term is named.
- Recommended first: **candidate 1, the task measurement module.** Today the dwell clock, focus pause, 3 s verified rule, source pattern and decision time live inside `study.js`'s DOM handlers (`openSource`, `closeSource`, `pauseDwell`, `resumeDwell`, `playTrace` fork line, `accept`). The proposal is to move them into one module tested with a fake clock.
- Candidate 2, the fork check module, comes second. `agent.run` and `tasks._evaluate` implement "margin AND judge" differently: the agent ignores the margin because `config.json` has `fork_requires_small_margin: false`. `tasks._evaluate` also reads `Index` private arrays. The judge prompt must stay byte-identical (see `docs/operations.md`).

## Open questions for the user
- Which architecture candidate to explore first.
- Whether to merge the `session-data-integrity` PR before starting the refactor work, which should branch from `main` after the merge.
- Which deferred minor findings from change 11 to fix before the pilot:
  - no fetch timeout, so a paused server freezes Accept;
  - a non-text payload value gets a 500 and is retried forever (latent);
  - Accept says "keeps retrying" for a rejected summary;
  - two tabs share the `eoa-outbox` queue;
  - a `localStorage` quota failure is silent;
  - a legacy database with duplicate rows would fail to build the unique indexes;
  - no test for the start guard or for upgrading `events` rows with a NULL `seq`.

## Loose ends before the pilot
- In the main checkout, move `system/data/sessions/events.sqlite` aside (it holds test rows). The command is in `PLANNED_CHANGES.md` §11.
- Real-browser check that dwell time stops while you are on another tab (`REGRESSION_2026-10-10.md` item 5b).
- Instrument screen: "Please answer every item." can never show because of the `required` radio buttons (regression defect 1).
- `system/RUNBOOK_CHECK.md` still lists matching statistics, the questionnaire screens, the per-block and session tables, and automatic block order as "Not built". All are built.
- Bug: `/api/freeze` writes `data/records/<record_id>.json` from a client-supplied id with no check (`escalate/agent.py:179`), so a path traversal is possible.
- `app.js:61` searches with `k: 5`, but the agent retrieves 4.
- `rotation.plan`, `resolve` and `check_balance` (the counterbalancing guarantees) have no tests.
- After the pilot, fill in the paper's Participants placeholders (`Assets/paper/main.tex:266`).

## Suggested skills
- `improve-codebase-architecture`: continue at step 3 (grilling loop) once the user picks a candidate.
- `grilling` and `codebase-design`: walk the design tree and keep the module/interface/seam vocabulary.
- `domain-modeling`: create or update `CONTEXT.md` as terms crystallize (task measure, fork check, task record, twin, rotation).
- `superpowers:writing-plans`, then `superpowers:executing-plans`: the user prefers native (inline) execution with one final reviewer.
- `superpowers:test-driven-development` (or the project's `tdd` skill): every change so far has been test-first.
- `git-commit`: the project commit convention (short, imperative subject lines, no `feat:` prefix).
- `superpowers:verification-before-completion`: run both test suites and a headless debug session before claiming done.
