# Built system vs. `REPRODUCIBILITY.md` (runbook), checked 2026-10-02

Every runbook item is compared against `system/` as built.

**Status values:**
- **Matches**: matches the runbook
- **Fixed**: was a gap, fixed in this check
- **Deviates**: deviates on purpose; the reason is given
- **Not built**: not built yet

## Rebuild test

`system/` was copied to a clean folder with a fresh virtual environment, and the README steps were followed: `pip install -r requirements.txt`, `setup`, `verify`, `rebuild`. **Every file** in `data/` plus `MODEL_VERSIONS.md` came out byte-identical. A live `crawl --force` reproduced `pages.jsonl` exactly.

The first run of this test exposed three problems, all fixed:
- `qa_annotated.jsonl` and `qa_kept.jsonl` were stale. The grader had changed after they were written. The correct counts are 84 kept, 25 answerable blind, 2 failed informed.
- Dependency versions weren't pinned. The clean venv installed different numpy and requests versions.
- `rebuild` re-embedded every chunk, which could shift retrieval scores on another machine.

## 1. Environment

| Runbook item | Status | Notes |
|---|---|---|
| Python 3.11+ | Fixed | README said 3.10+; now 3.11+ (built on 3.13.1) |
| Node 18+ only if React | Matches | Plain JavaScript, no build step |
| venv and pipeline dependencies | Fixed | `requirements.txt` now pins exact versions |
| `MODEL_VERSIONS.md` naming the embedding, planner, judge and filter models | Fixed | Written by `setup` from `models.lock.json` and `config.json`, including the fork-check settings |
| SQLite write path decided and recorded | Matches | The local Python server writes `data/sessions/events.sqlite` (git-ignored) |
| Import-check script | Not built | Not built; `setup` fails loudly if Ollama or a model is missing |

## 2. Corpus

| Runbook item | Status | Notes |
|---|---|---|
| Identify three disjoint sections | Deviates | The whole site (77 pages) is frozen; sections are assigned per task set. A superset of what the runbook asks for |
| Raw HTML, plain text, URL and UTC timestamp per page | Fixed | `data/snapshot/html/*.html` and `pages.jsonl` |
| SHA-256 per page | Fixed | Of both the HTML and the text, in the manifest |
| `SNAPSHOT_MANIFEST.json` | Fixed | `data/snapshot/SNAPSHOT_MANIFEST.json` |
| Freeze policy: no silent re-crawl | Fixed | `crawl` refuses to overwrite an existing snapshot; `--force` creates a new version |
| Re-hash and verify before continuing | Fixed | `python -m escalate verify` |
| Old snapshot versions kept | Not built | `--force` replaces the files; git history is the archive |

## 3. Index

| Runbook item | Status | Notes |
|---|---|---|
| Chunk by heading, with a stable `chunk_id` | Matches | `chunks.jsonl` |
| Chunk tagged with its page's content hash | Deviates | Linked through `page_id` to the manifest rather than copied into every chunk |
| Embeddings and persisted index | Matches | `vectors.npy` (cosine index; the runbook allows any index type) |
| Smoke-test evidence | Fixed | `data/index/smoke_test.json` (the gpu_short query; top-3 includes the Partitions page; passes) |
| No re-embedding after authoring | Fixed | The index is reused when the chunks hash and model match; `--force` re-embeds |

## 4. Fork check

| Runbook item | Status | Notes |
|---|---|---|
| Sub-step planner | Deviates | Exists in `agent.py`. The task builder runs the check at a fixed "extract the answer" step instead of planning first. The playground's Agent tab uses the planner |
| Fixed k | Matches | k = 4 |
| Margin threshold recorded | Matches | 0.10, in `config.json` and `MODEL_VERSIONS.md` |
| Judge asked the literal question | Deviates | The prompt contains the question plus instructions to return grounded options |
| Fires only on margin AND judge | Matches | Both conditions required |
| Log every evaluation | Matches | `data/fork_check_log.jsonl`: query, top-k, margin, judge output, fired |
| Report the hit rate | Matches | 24 of 36 phrasings fired; 12 of 36 fired on the authored fork (`task_catalog.md`, 10 October 2026) |
| Extra rule: the fork found must match the authored fork | Deviates | Added because 9 firings were on a *different* fork. The proposal should state this rule |

## 5. Curating items

| Runbook item | Status | Notes |
|---|---|---|
| About 30 candidate queries | Matches | 25 phrasings across 15 forks |
| Keep only forks where the check fired | Matches | Also requires a match to the authored fork |
| Blind-vs-informed filter and survivor count | Matches | 13 of 15 forks survive; logged per fork |
| Five-line pre-fork template | Matches | Reading, searching, Source A, Source B, extracting |
| Recommendation is the higher-ranked option; key from the passage plus the sheet line | Matches | |
| Set → form tie (1→S1, 2→S2, 3→S3) preserved | Deviates | Dropped on 10 October 2026: task set is crossed with form (one task per set in every block, nine forks), as the paper's Design section states; see `PLANNED_CHANGES.md`, change 1 |
| Sets match the runbook's examples (2.1 VPN, and so on) | Deviates | The VPN fork never fired on itself. Set 1 is J1, J2, J6; Set 2 is R3, R6, R9; Set 3 is S1, S2, S5 (see `task_catalog.md`) |
| 2 correct + 2 wrong per set; no source pair shared across sets | Deviates | Now 3 forks per set; each participant gets 4 or 5 correct recommendations over 9 tasks with at least one of each per block (`escalate/rotation.py`); no source pair is shared across forks |
| Two practice items | Matches | P1, P2 |
| Required record fields | Fixed | Added `item_id`, `is_correct`, `recommendation_correctness` (`form_tied_to` was removed with the tie). `trace` holds the runbook's `trace_lines` |
| SHA-256 per record and a manifest hash | Matches | `data/tasks/_manifest.json` |
| Matching statistics (trace length, fork line, overlap band, fork type) | Not built | Not computed |

## 6. Renderings

| Runbook item | Status | Notes |
|---|---|---|
| S1: trace freezes, modal, field empty until a pick, chips stay clickable | Matches | |
| S2: warning glyph and recommendation, auto-fill | Matches | |
| S3: citation only, auto-fill | Matches | |
| Recommendation wording "Default configuration suggests…" | Deviates | "Source A suggests…", because the page's actual default QoS is `gpu_debug` |
| All lines except the fork line identical across forms | Matches (by construction) | One record and one renderer; the formal text-diff check was not run |
| Reject opens the picker; pressing it again undoes | Matches | |
| No correctness feedback | Fixed | The block summary is now behind an experimenter button |

## 7. Web app

| Runbook item | Status | Notes |
|---|---|---|
| Two-pane layout; spec sheet stays for the block | Matches | |
| 3–5 s pacing; separate source overlays | Matches | Pacing is fixed per line in each record |
| No live LLM during a session | Matches | The Study tab reads frozen records only (the Agent tab is a separate development tool) |
| NASA-TLX, intrusion item and manipulation-check screens | Not built | Not built |
| Closing questionnaire (ranking and reason) | Not built | Not built |
| Event-table columns | Fixed | Added `block_order_group`. `t_ms` is included. `final_value` and `verified` are stored in the per-task summary table rather than on each event |
| Event types | Fixed | Added `trace_line_onset`, `block_start`, `block_end`. Also logs `task_start` and `refill` (a refill after a picker choice) |
| Per-block table (TLX and others) and per-session table | Not built | Not built (depend on the instrument screens) |
| End-to-end smoke test with every event type written | Deviates | SQLite writes tested through the API; the forms were checked in screenshots; no scripted click-through |

## 8. Session protocol

| Runbook item | Status | Notes |
|---|---|---|
| Order group assigned in rotation | Deviates | Selector for groups 1–6, logged; the experimenter picks it; no automatic rotation |
| Blocks run in group order | Not built | The experimenter starts each block by hand |
| Practice block | Matches | Set "Practice" |
| Screening, consent, debrief | Not built | Outside the app |

## Still to build before a pilot

The agreed changes, including crossing task set with form and the instrument screens, are specified in `PLANNED_CHANGES.md`.

1. The instrument screens (NASA-TLX, intrusion, manipulation check, closing ranking) and their tables.
2. Automatic session flow: assign an order group, then run practice and the three blocks in order with instruments between them.
3. Task-set matching statistics.
4. A scripted end-to-end test that writes every event type.
