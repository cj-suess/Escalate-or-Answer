---
name: git-commit
description: Commit convention for the Escalate-or-Answer study repo - short, imperative, scoped subject lines, with frozen data and participant data kept out of code commits. Use whenever creating a git commit in this repo.
---

# Commit convention

Short and to the point. Subject line only for most commits.

## Format

```
<type>(<scope>): <subject>
```

- **type**: one of the types below
- **scope**: optional; the area touched (see Scopes). Omit it when a commit spans several areas.
- **subject**: imperative mood, lowercase, no trailing period, at most 60 characters

## Types

| type | use for |
|------|---------|
| `feat` | new study behaviour, endpoint, pipeline step or command |
| `fix` | corrected behaviour |
| `refactor` | restructure without behaviour change (frozen outputs must rebuild byte for byte) |
| `test` | tests and regression scripts |
| `data` | regenerated frozen artifacts: snapshot, chunks, QA results, index, task records, manifest, LLM cache |
| `docs` | README, PLANNED_CHANGES, RUNBOOK_CHECK, regression reports, plans, operations notes |
| `paper` | paper, proposal, hypothesis memo, related work, references (`Assets/`) |
| `chore` | dependencies, config, ignores, skills, file moves |

## Scopes

| scope | covers |
|-------|--------|
| `server` | `escalate/server.py`: API, session database |
| `study` | `playground/study.js`, `outbox.js`, `resume.js`, `index.html`: the participant session |
| `playground` | Agent and Corpus tabs (`app.js`), shared `common.js`, styles |
| `agent` | `escalate/agent.py`: planner, fork check, records |
| `tasks` | `escalate/tasks.py`, `tasks/catalog.json`, `data/tasks/` |
| `rotation` | `escalate/rotation.py`: block order, twin assignment, worksheet |
| `pipeline` | crawl, chunk, qa, index, llm, matching, catalog report |
| `plan` | `PLANNED_CHANGES.md`, `docs/superpowers/plans/` |
| `paper` | `Assets/paper/` |

## Rules

- One logical change per commit.
- Subject line alone unless the *why* is not obvious from the diff. A body is one blank line, then text wrapped at 72 characters, explaining why, not what.
- When the commit implements a planned change, end the body with `Planned change <N>.` (number from `system/PLANNED_CHANGES.md`).
- Keep frozen artifacts out of code commits. Regenerated files under `system/data/` (except `data/sessions/`) go in their own `data` commit. Its body must name the command that produced them (for example `python -m escalate tasks`) and say whether `_manifest.json` changed.
- A `refactor` that changes any file under `system/data/` is not a refactor. Find out why the output changed before committing.
- Never commit participant data: `system/data/sessions/` and any `*.sqlite` or `*.bak` file. Never commit `docs/handoff.md` or `.superpowers/`.
- Check `git status` before committing, and stage files by name, not with `git add -A`.
- No emoji. No "Co-Authored-By". No tool attribution.

## Examples

```
feat(study): resume a crashed session under its own id
fix(server): reject payloads with unknown keys
test(rotation): pin the counterbalancing guarantees
refactor(agent): share one fork check with the task builder
docs(plan): mark planned change 11 built
paper: add the regression results to the Apparatus section
chore: add git-commit skill
```

A `data` commit always carries a body:

```
data(tasks): rebuild task records after S1 sheet reword

The Set 3 sheet lines named Set 1's stages, which read wrongly under
a mixed sheet. Rebuilt with `python -m escalate tasks`; record hashes
and _manifest.json changed, the worksheet did not.
Planned change 2.
```
