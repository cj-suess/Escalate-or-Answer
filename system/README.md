# Escalate or Answer: local, reproducible pipeline

Everything the study needs before participants arrive, running locally with an
open-weight model through [Ollama](https://ollama.com): a frozen snapshot of the
CSU CS systems documentation, FictionalQA-style question generation with the
blind-vs-informed filter, an embedding index, the drafting agent (plan →
retrieve → fork check → answer or escalate), and a playground that renders an
agent run in the three escalation forms (modal stop, inline flag,
provenance-only).

It runs the same way on Windows (CUDA) and macOS on Apple silicon (Metal).

## Quick start

1. Install Ollama: <https://ollama.com/download>. On macOS you can also run
   `brew install ollama`. Start the Ollama app so it is listening on
   `127.0.0.1:11434`.
2. Install Python 3.11 or newer (built and verified on 3.13.1), then from this `system/` folder:

   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate      macOS: source .venv/bin/activate
   pip install -r requirements.txt
   python -m escalate setup     # pulls the pinned models, checks digests against data/models.lock.json
   python -m escalate serve     # http://127.0.0.1:8567
   ```

The committed `data/` folder already holds the snapshot, chunks, QA results,
index, frozen records and the LLM cache, so the playground works right away.
Any agent question that was already run replays from the cache in under a
second. A new question calls the local model.

## Commands

| Command | What it does |
|---|---|
| `python -m escalate setup` | Pull the models named in `config.json` through Ollama; write or verify `data/models.lock.json` |
| `python -m escalate crawl [--force]` | Freeze a snapshot of sna.cs.colostate.edu (polite BFS, 0.5 s delay): `pages.jsonl`, raw HTML per page, and `SNAPSHOT_MANIFEST.json` (URL, section, retrieval time, SHA-256 of HTML and text). Refuses to overwrite an existing snapshot without `--force` (a re-crawl is a new snapshot version) |
| `python -m escalate verify` | Re-hash every frozen page against `SNAPSHOT_MANIFEST.json` |
| `python -m escalate chunk` | Split pages into heading-scoped chunks (≤180 words) |
| `python -m escalate qa` | Generate span-checked QA pairs, then run the blind-vs-informed filter |
| `python -m escalate index` | Embed all chunks |
| `python -m escalate tasks` | Build the frozen v4 task records from `tasks/catalog.json`: fork check (margin ≤ 0.10 AND judge, grounded options must match the authored fork), blind-vs-informed probe, Source A/B passages, fixed 3–5 s line pacing. Writes `data/tasks/` and `data/fork_check_log.jsonl` |
| `python -m escalate rebuild` | `chunk` + `qa` + `index` + `tasks` from the committed snapshot (no crawl). The index is reused when it matches the chunks and embedding model; `--force` re-embeds |
| `python -m escalate all [--force]` | `crawl` + `rebuild` |
| `python -m escalate ask "question" ["situation"]` | Run the agent once and print the record |
| `python -m escalate serve [port]` | Start the playground |

## The study view (proposal v4)

The **Study task** tab runs a block as a participant sees it:
- the spec sheet and task card are on the left
- the scripted query, a **Send** button and the streamed trace are on the right
- trace lines arrive at the record's fixed 3–5 s pace, with a typing indicator between lines
- **Source A** and **Source B** are separate chips; each opens its own overlay with the cited lines highlighted
- the fork line renders as S1 (blocking modal), S2 (inline warning) or S3 (citation only)
- **Accept** confirms the answer; **Reject** opens the two-option picker, and pressing it again undoes

Every event is written to `data/sessions/events.sqlite`, which is git-ignored because it holds participant data. Logged events include each source's open and close with its duration. A per-task summary row records:
- the final value and whether it is correct
- whether the participant followed the recommendation
- whether they opened any source
- which sources they opened (recommended only, the other only, both, or neither)
- dwell time on Source A and on Source B
- decision time and total time

The experimenter bar sets the participant code, form, task set and pace (study, pilot or debug). Deep links work too, e.g. `#form=S2&set=1&autostart=1`. The task catalog with all candidates and their fate is in `Assets/checkpoint2/task_catalog.md`.

## Rebuilding from scratch, and what to expect

From a fresh clone, `setup` then `rebuild` regenerates every file in `data/` byte for byte from the frozen snapshot and the committed caches. This was tested in a clean folder with a new virtual environment: every file in `data/` plus `MODEL_VERSIONS.md` matched. `setup` also writes `MODEL_VERSIONS.md`, which names each model, its role and digest, and the fork-check settings.

`crawl --force` against the live site reproduced `pages.jsonl` exactly on 2026-10-03. If the site changes, a forced re-crawl produces a new snapshot version, and everything after it changes with it.

## How this maps to the proposal

- **Corpus**: `data/snapshot/pages.jsonl` is the frozen snapshot (title, URL,
  section, "Updated on" date, content as light Markdown).
  `snapshot_meta.json` records the crawl time and a content hash.
- **Contamination filter** (Kirchenbauer et al., FictionalQA): `escalate/qa.py`.
  The model writes up to two questions per chunk, each tied to a verbatim
  evidence span that is checked in code. The same model then answers every
  question blind (it must commit to a best guess) and informed (with the chunk).
  Questions answered correctly blind are discarded. Results are in
  `qa_annotated.jsonl`, and the survivors are in `qa_kept.jsonl`.
- **Drafting agent and fork check**: `escalate/agent.py`. The agent sees only the
  question, never the participant's situation line. For each planned step it
  retrieves the top-k chunks and asks an LLM judge whether the passages give
  different correct answers depending on an unstated fact about the user. If so,
  it escalates with the higher-ranked option as its default. The retrieval
  margin is recorded for every step. Setting `fork_requires_small_margin` in
  `config.json` enforces the proposal's "margin AND judge" rule.
- **Records**: each run returns a JSON record (question, situation, steps with
  citations, retrieval trace, fork-check output, escalation, run card,
  provenance with model digests). **Freeze** in the playground writes it to
  `data/records/`. Authors may edit wording but never an escalation decision or
  a default, and they set `card.key` from the situation line.

## Reproducibility, in three layers

1. **Frozen artifacts (exact).** The snapshot, chunks, QA results, index vectors
   and frozen records are committed. The study replays records, so participants
   on any machine see identical content.
2. **Committed call cache (exact).** Every LLM call is keyed by model name,
   model digest, decoding options, messages and output schema, and stored in
   `data/cache/llm_cache.jsonl`. Query embeddings are stored in
   `data/cache/query_vectors.jsonl`. Re-running any step with the same model
   digest returns byte-identical outputs from the cache.
3. **Regeneration (close, not guaranteed identical).** All calls use temperature
   0, top_k 1 and seed 567. In testing on an RTX 3060 (Windows, Ollama 0.35.1),
   repeated warm calls were identical, but the first call after a cold model
   load produced different wording. GPU kernels, CPU/GPU offload splits and
   Metal vs. CUDA can change low-order bits and so occasionally a token. That is
   why layers 1 and 2, not the seed, are the guarantee. Each step sends a
   warm-up call first.

Model weights are not stored in git (several GB). They are pinned by tag in
`config.json` and by digest in `data/models.lock.json`. `setup` warns if the
digest you pull differs, which can happen if the tag is updated upstream; cached
outputs still replay exactly.

## Models

| Role | Default | Notes |
|---|---|---|
| LLM | `qwen2.5:7b-instruct` (Q4_K_M, 4.7 GB) | `qwen2.5:3b-instruct` also works; change `config.json` and rebuild |
| Embeddings | `nomic-embed-text` (274 MB) | uses the `search_document:` / `search_query:` prefixes |

A 6 GB laptop GPU runs the 7B model with partial CPU offload (about 0.6 s for a
short answer, about 3 s for a question-generation call). An M4 Pro runs it
entirely on the GPU.

## Known limits of this prototype

- The run card shows only the scored field. Decoy fields come from item
  authoring.
- The fork judge is a 7B model. Expect false positives and misses. The
  playground's Agent trace tab shows each judgment, so items can be selected
  and the detector's hit rate reported, as the proposal requires.
- The snapshot is a copy of a public CSU site, kept for research
  reproducibility.
