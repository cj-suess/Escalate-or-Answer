---
name: git-commit
description: Commit convention for this research project - short, imperative, scoped subject lines. Use whenever creating a git commit in this repo.
---

# Commit convention

Short and to the point. Subject line only for most commits.

## Format

```
<type>(<scope>): <subject>
```

- **type** — one of: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `paper`
- **scope** — optional, the area touched: `supervisor`, `miner`, `smelter`,
  `builder`, `logistics`, `defender`, `goals`, `fle`, `papers`, `plan`
- **subject** — imperative mood, lowercase, no trailing period, ≤60 chars

## Rules

- Subject line alone unless the *why* is non-obvious from the diff.
- If a body is needed: one blank line, then wrapped at 72 chars, explaining
  **why** not what.
- No emoji. No "Co-Authored-By". No tool attribution.
- One logical change per commit.

## Types

| type | use for |
|------|---------|
| `feat` | new agent capability, role, or mechanism |
| `fix` | corrected behavior, incl. FLE workarounds |
| `docs` | PLAN.md, handoff, README, paper notes |
| `refactor` | restructure without behavior change |
| `test` | tests and smoke scripts |
| `chore` | deps, config, file moves, venv |
| `paper` | adding or summarizing a reference paper |

## Examples

```
feat(goals): add structured goal schema
fix(fle): patch messageId alias in a2a handler
paper(papers): add hoang2005 htn summary
chore: pin a2a-sdk to 0.3.26
docs(plan): mark milestone 1 complete
```

Body only when warranted:

```
fix(fle): patch messageId alias in a2a handler

Pydantic v2 exposes messageId only as a serialization alias, so the
runtime attribute lookup fails. Monkey-patched rather than editing
site-packages so the fix survives a reinstall.
```
