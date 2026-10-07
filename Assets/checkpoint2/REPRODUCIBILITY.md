# Escalate or Answer — Reproducibility Runbook

## 0. Overview

This document is the engineering runbook for building and running the "Escalate or Answer" study apparatus: a frozen documentation snapshot + item records, an offline drafting pipeline that produces those records, and a study web app that replays them. It assumes the reader has already read `new_proposal_v4.tex` (hereafter "the proposal") for the research rationale, hypotheses, and design justification — none of that is repeated here. This document only tells you what to build, in what order, and how to check each step worked.

The three deliverables this runbook walks toward, in build order:

1. A frozen corpus snapshot of the Falcon documentation, hashed and versioned (proposal §3.4 / "Corpus and tasks").
2. The offline drafting pipeline (retrieval index + fork check + contamination filter) that produces 12 measured + 2 practice item JSON records (proposal §3.4, §3.5, Figure 2).
3. The study web app that replays frozen records under one of three escalation-form flags (S1/S2/S3, proposal §3.3, §4).

Everywhere an exact number, threshold, or behavior matters, this document cites the proposal section rather than restating it from memory, so the two documents cannot silently drift apart. If you find a discrepancy between this runbook and `new_proposal_v4.tex`, the proposal governs — fix this file, not your judgment.

---

## 1. Environment setup

The proposal commits to: a Python drafting pipeline (§4, "System Vision and Technology": "The drafting pipeline is Python"); a web app in "React or plain JavaScript" (§4); and a "local SQLite database" for event logging (§4). It does not commit to a specific embedding model, vector index library, or LLM for planning/fork-judging/drafting — §4 says only "The model will be named in the paper; because records are frozen, the human-facing study does not depend on it." Do not silently pick one and treat it as fixed; whatever is chosen must be recorded in the released materials (see §10 checklist item "pipeline version/model recorded").

- [ ] Install Python 3.11+ for the drafting pipeline.
- [ ] Install Node.js 18+ (LTS) if building the web app in React; skip if using plain JavaScript with no build step.
- [ ] Create a Python virtual environment for the pipeline (`python -m venv .venv`) and activate it.
- [ ] Install pipeline dependencies: an HTTP/crawling library (e.g. `requests`, `httpx`), an HTML parser (e.g. `beautifulsoup4`), an embedding client library matching whatever embedding model is chosen, a vector index library (e.g. `faiss`, `chromadb`, or a simple in-memory cosine-similarity index — the proposal does not require any specific one), and an LLM API client (or local-model runtime) matching whatever model is chosen for planning and fork-judging.
- [ ] Create a `MODEL_VERSIONS.md` (or equivalent) file in the pipeline directory that records, verbatim: the embedding model name and version/date, the LLM name and version/date used for sub-step planning, the LLM name and version/date used as the fork judge, and the LLM name and version/date used as the drafting/contamination-filter model (these may be the same model; record it once if so). This file must ship with the released materials (proposal §3.5: "The model will be named in the paper").
- [ ] Install a SQLite driver appropriate to the web app's runtime (e.g. `better-sqlite3` for Node, or the browser-side app writes to a local server that owns the SQLite file — decide and record which, since the app "does not call any live model during a session" but still needs a write path for the event log).
- [ ] Verify installs: run a one-line script in each language/runtime that imports every dependency listed above and exits 0.

---

## 2. Corpus acquisition and freezing

Corpus source and structure per proposal §3.4: "a frozen snapshot of the CSU CS department systems documentation for the Falcon cluster (sna.cs.colostate.edu)... 12 measured tasks in three sets of four, each set from a disjoint section (job submission; access and remote connection; storage and software), plus 2 practice tasks... no source pair recurs across sets." The proposal explicitly flags that exact section/page selection is not finalized ("which sections are used is not yet decided," §3.4 preamble comment) — you must finalize and record it as part of this step, not invent a different structure.

- [ ] Identify the three disjoint documentation sections required by the proposal:
  - Section 1 (job submission) — e.g. "Submitting Jobs," "Partitions and time limits," "GPU Jobs" pages (these are the pages illustrated for the S1-tied task set in Table 1 of the proposal).
  - Section 2 (access and remote connection) — e.g. "Connecting to Falcon," "SSH guide" pages (illustrated for the S2-tied set).
  - Section 3 (storage and software) — e.g. "Home Directories," "Temporary Disk Space" pages (illustrated for the S3-tied set).
- [ ] Confirm each section maps to disjoint URLs/pages with no overlap in source pairs used across sections (proposal §3.4: "no source pair recurs across sets").
- [ ] Crawl each identified page exactly once. For each page, save: the raw HTML, a plain-text extraction, the source URL, and a UTC retrieval timestamp.
- [ ] Compute and record a content hash (SHA-256) of the raw HTML for every saved page.
- [ ] Store the snapshot (raw HTML + text + timestamps + hashes) in version control or an equivalent immutable archive location (a tagged git commit, or a write-once storage bucket). Record the exact commit hash / archive identifier as "the frozen snapshot."
- [ ] Write a `SNAPSHOT_MANIFEST.json` listing, per page: URL, section assignment, retrieval timestamp, SHA-256 hash, local file path.
- [ ] Freeze policy: once item authoring (Section 6 below) begins, do not re-crawl any page. If a page must be re-fetched for any reason, that is a new snapshot version — bump a version number, keep the old snapshot, and re-derive all item records from the new version if you switch to it. Never mix pages from two snapshot versions in one released item set.
- [ ] Verify: re-hash every saved page locally and confirm it matches `SNAPSHOT_MANIFEST.json` before proceeding to Section 3.

---

## 3. Building the retrieval index

Chunking is "by heading" (proposal §4: "the snapshot is chunked by heading, embedded into a vector index, and queried per sub-step").

- [ ] Write a chunker that splits each saved page's text at heading boundaries (H1/H2/H3 or the site's equivalent structural markers), producing one chunk per section under a heading, each tagged with: source page URL, section/heading title, chunk text, and the page's content hash from Section 2.
- [ ] Run the chunker over the full frozen snapshot and save the chunk set (e.g. `chunks.jsonl`), one JSON object per chunk with a stable `chunk_id`.
- [ ] Embed every chunk with the embedding model recorded in `MODEL_VERSIONS.md` (Section 1). Save embeddings keyed by `chunk_id`.
- [ ] Build the vector index (e.g. FAISS flat index, or equivalent) over the chunk embeddings. Persist the index to disk alongside the chunk set so it can be rebuilt deterministically from the frozen snapshot.
- [ ] Smoke test: query the index with a known fact from the corpus (e.g. "What is the wall-time limit for the `-short` QoS?") and confirm the top-ranked retrieved chunk is the correct page/heading (Submitting Jobs / QoS flags, per Table 1 of the proposal). Record the query, the top-3 retrieved chunk IDs, and their scores as evidence this step passed.
- [ ] Do not rebuild or re-embed the index once item authoring (Section 6) begins, for the same freeze reason as Section 2.

---

## 4. Implementing the fork check

Definition, verbatim from proposal §3.5 / Figure 2: the fork check "fires when the retrieval-score margin between the top candidates is small **and** an LLM judge answers yes to 'do these chunks give different answers depending on a user attribute the query does not state?'" It runs at the extraction sub-step of the per-query planning loop (plan sub-steps → retrieve top-k per sub-step → fork check → answer or escalate → next sub-step → freeze as JSON record when done).

- [ ] Implement the sub-step planner: given a query, produce an ordered list of sub-steps (proposal's running example: read the question, search, extract the flag, decide).
- [ ] Implement per-sub-step retrieval: for each sub-step, retrieve top-k chunks from the index built in Section 3, with their similarity scores. Choose and record a fixed k.
- [ ] Implement the margin check: compute the score gap between the top-1 and top-2 retrieved chunks per sub-step; choose and record a fixed threshold below which the margin counts as "small." This threshold is not specified numerically in the proposal — pick a value, justify it against the pilot data once available, and record it in `MODEL_VERSIONS.md` or a dedicated `FORK_CHECK_CONFIG.json`.
- [ ] Implement the LLM-judge call: when the margin check passes, send the top candidate chunks plus the original query to the judge model with the literal question "do these chunks give different answers depending on a user attribute the query does not state?" and parse a yes/no.
- [ ] The fork check fires only when both the margin condition and the judge's "yes" are true (proposal: margin small **and** judge says yes — both required, not either).
- [ ] Logging requirement (proposal §3.5: "Only queries on which the check fired become tasks; we report its hit rate" and §6/Deliverables: "a log of where it fired over about 30 candidate queries"): log every fork-check evaluation, positive or negative, with: query text, sub-step, top-2 chunk IDs and scores, computed margin, judge's raw yes/no output, and final fired/not-fired decision. Persist this log as `fork_check_log.jsonl`.
- [ ] Compute and report the hit rate: fired / total evaluated, over the full candidate query pool (Section 6). This number must appear in the released materials per the proposal's deliverables list.
- [ ] On a "no" (not fired), the loop answers the sub-step directly with citations and continues (proposal Figure 2, left branch); on "yes," it escalates — produces the fork's recommendation, both source citations, and marks the fork line index (right branch). Implement both branches even though only the escalate branch produces study items, since the branching itself is part of "the loop is fully described here" (proposal §3.6, agentic-ness property list).

---

## 5. Curating the 12 (+2 practice) items

Target structure, per proposal §3.4 and Table 1: 12 measured items = 3 systems/sections × 4 items each; within each 4-item set, 2 source pairs, each source pair used twice — once with the recommended option correct, once wrong — so each 4-item set is exactly 2 correct + 2 wrong. Plus 2 practice items (unforked, per proposal §"Procedure" step 2 — "two tasks on a practice sheet with no fork; the trace cites two agreeing sources"). No source pair recurs across the three sets.

**Known, accepted limitation — do not "fix" it here.** Each 4-item task set is permanently tied to one escalation form (S1's set is job submission, S2's set is access/connection, S3's set is storage/software per Table 1), not crossed in a Latin square of set × form. The proposal's own TODO comment (line ~599) flags that this confound could be removed by crossing set with form as in an earlier draft, and explicitly says the team is keeping the tie and relying on matching + the task random effect as the defense (proposal §"Threats": "Task set and form are confounded by the fixed tie between each form and its four tasks; the matching procedure, the disjoint sections and the task random effect are the defenses, and the confound is stated as a limitation"). Whoever authors item sets must preserve this tie — do not rebalance sets across forms to "improve" the design.

- [ ] Draft approximately 30 candidate questions spread across the three sections (proposal deliverables: "a log of where it fired over about 30 candidate queries" — this is the stated candidate pool size). Write each candidate as a plain scripted query, omitting the deciding user fact, matching the style of the proposal's running example ("Which QoS flag should I use to submit this job?").
- [ ] Run all ~30 candidates through the drafting pipeline (Sections 3-4). Keep only candidates where the fork check actually fired.
- [ ] For each fired candidate, run the FictionalQA-style contamination filter (`kirchenbauer2026`, proposal §3.4 and §2 Related Work): query the drafting model blind (question only, no source text) and informed (question + the two cited source passages). Discard any candidate fact the model answers correctly blind. Keep only facts the model gets wrong blind and right informed — the proposal notes "department-local hostnames, QoS names and paths are the kind that fail blind," i.e., generic/guessable facts should not survive this filter.
- [ ] Log and report the contamination-filter survivor count (candidates in → survivors out) as part of the released materials (proposal deliverables list).
- [ ] From the surviving candidates, hand-edit drafts to a fixed length/format matching Table 1's style: a sheet line that decides the answer, the scripted query, the trace lines (5 pre-fork lines per the proposal's fixed template: reading the question, searching, Source A found, Source B found, extracting), the fork line, the two named options, the recommended option (= the higher-ranked retrieval result, proposal §3.2), and the key (derived only from the frozen source passage + the sheet line — "no dates, no authority rule, no verification against the live system," proposal §3.2).
- [ ] Assign items to the three sets per the proposal's fixed section-to-form tie:
  - Set tied to S1 (job submission): items 1.1-1.4, two source pairs (QoS flag pair; GPU partition pair), each used once correct / once wrong.
  - Set tied to S2 (access and connection): items 2.1-2.4, two source pairs, same correct/wrong split. (Table 1 shows only 2.1 illustratively — item 2.2 is its stated twin using the same sources with a different sheet line; 2.3/2.4 must be produced from the pipeline per the proposal's own TODO note, not hand-seeded.)
  - Set tied to S3 (storage and software): items 3.1-3.4, same structure. (Table 1 shows only 3.1; 3.2 is its twin; 3.3/3.4 must come from the pipeline, not hand-seeded — same TODO note.)
- [ ] Confirm within each set: exactly 2 items have recommended = key (correct) and exactly 2 have recommended ≠ key (wrong), and the two items sharing a source pair differ only in their sheet line / recommendation-correctness (proposal §3.2: "used twice in a block, once ... correct and once ... wrong").
- [ ] Confirm no source pair is reused across the three sets (proposal §3.4).
- [ ] Author the 2 practice items separately: no fork, two agreeing sources, same trace template, not scored (proposal Procedure step 2).
- [ ] Freeze each of the 14 items (12 measured + 2 practice) as a JSON record with at least these fields: `item_id`, `set` (1/2/3 or practice), `form_tied_to` (S1/S2/S3/none), `spec_sheet_line`, `question` (participant-facing), `scripted_query` (assistant-facing), `trace_lines` (ordered list, each with line index and text, source chips marked), `source_a` (id, title, url, highlighted-passage text), `source_b` (same), `fork_line_index`, `options` (list of the two option strings), `recommended_option`, `key`, `is_correct` (recommended == key), `recommendation_correctness` label used for the Correctness IV.
- [ ] Version and hash the final 14-record set the same way as the corpus snapshot (Section 2): compute a SHA-256 per record and an overall manifest hash, store in version control alongside `SNAPSHOT_MANIFEST.json`.
- [ ] Matching check (proposal §3.4: "Task sets are matched on trace length, fork line index, query–source lexical overlap band and fork type, checked in the pilot"): compute these four quantities per item and confirm they are comparable across the three sets before finalizing. Record the comparison table.

---

## 6. Implementing the three escalation-form renderings

Behavioral spec, verbatim from proposal §3.3: all three forms share one skeleton — "the same trace lines, the same two source chips printed before the fork, the same recommended option with the same parenthetical citation, and the same Accept/Reject controls with one-step undo." Only the fork line's rendering and post-fork flow differ.

**Must stay byte-identical across all three forms, per item:** trace lines 1-5 (reading, searching, Source A found, Source B found, extracting), the two source chips and their click-to-open overlay behavior, the pacing (3-5s between lines, proposal §3.2), the recommended option and its citation text, the Accept/Reject controls, and the one-step undo (pressing Reject again before Accept reopens the picker).

- [ ] **S1, modal stop (announced, blocking).** At the fork line, freeze the trace. Show a modal naming both options and the one-line recommendation ("Default configuration suggests `-short` for all jobs"), with one button per option. Leave the answer field empty until the participant clicks a button; fill the field with whichever option was clicked. Source chips above the modal overlay remain clickable while the modal is up (proposal §3.3 and Figure 1 caption).
- [ ] **S2, inline warning (announced, not blocking).** Keep the trace streaming. The fork line itself carries a small warning glyph plus the same recommendation sentence beneath it. Do not wait for input — automatically take the recommended option and fill the field with it, then continue the trace to the "Decision: ... Filling the answer field" line.
- [ ] **S3, provenance-only (not announced).** Keep the trace streaming. The fork line states the decision with a citation only ("Use `-short` (Source A)") — no glyph, no stated alternative option. Automatically take the recommended option and fill the field, same as S2.
- [ ] Implement the replay engine so that switching the condition flag changes only the rendering/behavior of the single fork line (and, for S1, whether the flow blocks) — verify this by diffing the rendered trace text of the same item under all three flags and confirming every line except the fork line is character-identical.
- [ ] Verify Reject always opens a two-option picker listing both fork options, regardless of form; choosing one refills the field; Accept confirms; pressing Reject again before Accept reopens the picker (one-step undo, all three forms).
- [ ] Verify no feedback is given on Accept/Reject correctness (proposal §3.2: "No feedback is given").

---

## 7. Building the study web app

Layout: two panes per proposal §3.2 and Figure 1 — left pane: spec sheet (persistent for the block), the task question, one answer field, Accept/Reject buttons; right pane: the assistant panel with the scripted query + Send button, then the streamed trace.

- [ ] Build the left pane: spec-sheet display (persists across all 4 tasks in a block, replaced only at block boundaries), per-task question text, single answer field (read-only / autofilled, not participant-typed — proposal: "participants never type"), Accept and Reject buttons.
- [ ] Build the right pane: pre-scripted query text + Send button; on Send, start the replay engine (Section 6) which prints trace lines one at a time with a 3-5s pause between lines; source chips are clickable at any time after they appear and open an overlay showing the cited passage with relevant lines highlighted; closing the overlay returns to the trace in its current state.
- [ ] Build the replay engine: reads one frozen JSON item record (Section 5) plus a condition flag (S1/S2/S3), renders the trace and fork line per Section 6, and autofills the answer field per the form's rule. The engine must never call a live LLM or retrieval index during a session — it only reads the frozen record (proposal §3.6: "the web app reads only the record" and §4: "the human-facing study does not depend on it" referring to the drafting model).
- [ ] Build the instrument screens: full-screen steps between blocks for raw NASA-TLX, the one-item (1-7) perceived-intrusion measure, and the manipulation check (identify the form just used) — per proposal §"Dependent variables" (f) and §"Procedure" step 3.
- [ ] Build the closing-questionnaire screen: ranking of the three forms + free-text reason (proposal §"Dependent variables" (g) and Procedure step 4).
- [ ] Implement the event log, writing to local SQLite under a participant code (proposal §4: "logged as a timestamped event ... to a local SQLite database under a participant code"). Use this schema (one row per event unless noted):

| Column | Type | Notes |
|---|---|---|
| `participant_code` | TEXT | assigned at session start |
| `session_id` | TEXT | one per participant session |
| `block_order_group` | INTEGER | 1-6, which of the six S1/S2/S3 permutations (proposal §"Design," Block Order nuisance variable) |
| `block_index` | INTEGER | 1-3, position of this block within the session |
| `form` | TEXT | S1 / S2 / S3, form active for this block |
| `item_id` | TEXT | matches the frozen record's `item_id` |
| `recommendation_correctness` | TEXT | correct / wrong, from the item record |
| `event_type` | TEXT | one of: send, trace_line_onset, fork_onset, modal_pick, source_open, source_close, autofill, accept, reject, picker_choice, block_start, block_end |
| `event_detail` | TEXT | e.g. trace line index, source id (A/B), option string chosen |
| `timestamp_utc` | TEXT/DATETIME | ISO-8601, millisecond precision |
| `source_open_duration_s` | REAL | nullable; filled on `source_close`, computed from matching `source_open` |
| `final_value` | TEXT | nullable; filled once, at task completion (final Accept) |
| `verified` | INTEGER (bool) | derived: at least one source opened between Send and final Accept (proposal DV (a)) |

Additional per-block table (one row per participant per block):

| Column | Type | Notes |
|---|---|---|
| `participant_code` | TEXT | |
| `block_index` | INTEGER | |
| `form` | TEXT | |
| `nasa_tlx_mental` / `_physical` / `_temporal` / `_performance` / `_effort` / `_frustration` | INTEGER | raw NASA-TLX subscales, 1-21 or per your instrument's scale — record which scale you used |
| `intrusion_item` | INTEGER | 1-7, "as in MiPP-Eval" (proposal DV (f)) |
| `manipulation_check_response` | TEXT | participant's identification of the form used |
| `manipulation_check_correct` | INTEGER (bool) | |

And a per-session table:

| Column | Type | Notes |
|---|---|---|
| `participant_code` | TEXT | |
| `form_ranking` | TEXT | ordered list, e.g. JSON array `["S2","S1","S3"]` |
| `ranking_reason_freetext` | TEXT | |
| `screening_used_falcon_before` | INTEGER (bool) | screening item result |

- [ ] Smoke test the app end to end on one practice item and one measured item under each of the three forms before Section 8's rehearsal: confirm trace pacing, chip-click overlay, autofill behavior, Accept/Reject/undo, and that every event type in the schema above actually gets written.

---

## 8. Session script / protocol

Literal sequence per proposal §"Procedure" (total ~45 minutes):

- [ ] **Consent and instructions (5 min).** Obtain consent. Read the participant the cover story verbatim, quoted from the proposal: *"You are a student using the Falcon cluster for an assigned project. You are given the assignment details and an agentic AI assistant for the cluster documentation that retrieves from those documents. You will complete a series of tasks derived from the assignment."* State explicitly: the assistant is usually right but can be wrong; the spec sheet describes their assignment; they may open any source the assistant cites; every task has a fork (100% base rate, disclosed up front per proposal §3.4 "No control tasks" and §"Threats"). Log: `screening_used_falcon_before` (screening item — must be "no" to qualify, proposal §"Participants").
- [ ] Assign `participant_code` and `block_order_group` (1 of 6 permutations of S1/S2/S3, assigned in rotation across participants — proposal §"Design," Block Order).
- [ ] **Practice (3 min).** Show the practice spec sheet. Run 2 unforked practice items: trace cites two agreeing sources and fills the field automatically; experimenter has the participant open and close a source once and use Reject then Accept once each. Do not score or log these as measured trials (proposal Procedure step 2 — "not scored"), though logging the interaction events for debugging purposes is fine as long as they are excluded from analysis.
- [ ] **Three measured blocks (~9 min each), in the order given by `block_order_group`.** For each block:
  - [ ] Replace the visible spec sheet with that block's assignment sheet; it stays on screen for the whole block. Log `block_start`.
  - [ ] Run the block's 4 items in random order, each following the trial loop of proposal §3.2 (Query → Trace → Fork → Fill → Accept/Reject), under the block's assigned form. Every event listed in the Section 7 schema is written live as it occurs (Send timestamp on `send`; each trace line's appearance on `trace_line_onset`; the fork line's appearance on `fork_onset`; an S1 button click on `modal_pick`; chip clicks/closes on `source_open`/`source_close` with computed `source_open_duration_s`; the field filling on `autofill`; button presses on `accept`/`reject`/`picker_choice`; the task's final value on `final_value` at the terminal `accept` event).
  - [ ] At block end, present NASA-TLX, the intrusion item, and the manipulation check as full-screen steps; write one row to the per-block table (Section 7). Log `block_end`.
- [ ] **Closing questionnaire (5 min).** Present the ranking task and free-text reason prompt; write one row to the per-session table.
- [ ] Block position is later used as a covariate in analysis (proposal §"Procedure": "Block position enters the models as a covariate and the first block is reported alone as a descriptive between-subjects check") — no special logging needed beyond `block_index`, which is already recorded.
- [ ] Debrief and end session.

---

## 9. Reproducibility checklist

A third party should be able to check every box below against the released materials and confirm the study as actually run matches `new_proposal_v4.tex`.

- [ ] Frozen corpus snapshot exists, with retrieval timestamps and a SHA-256 hash recorded per page (`SNAPSHOT_MANIFEST.json`, Section 2), and no page was re-crawled after item authoring began.
- [ ] `MODEL_VERSIONS.md` records the exact embedding model, planning LLM, fork-judge LLM, and drafting/contamination-filter LLM (names + versions/dates), per proposal §4's promise that "the model will be named in the paper" (Section 1).
- [ ] Fork-check hit rate is computed and reported over the full ~30-candidate pool, with `fork_check_log.jsonl` retained showing every firing and non-firing evaluation (Section 4; proposal deliverables list).
- [ ] Contamination-filter survivor count (candidates in vs. items surviving blind-vs-informed filtering) is reported (Section 5; proposal deliverables list).
- [ ] All 12 measured + 2 practice item records are frozen, hashed, and versioned, with the required fields present per record (Section 5).
- [ ] Each 4-item set has exactly 2 correct-recommendation and 2 wrong-recommendation items, no source pair recurs across sets, and the set-to-form tie matches Table 1 of the proposal (job submission → S1, access/connection → S2, storage/software → S3) — and this tie was preserved, not rebalanced (Section 5, "Known, accepted limitation").
- [ ] Task-set matching statistics (trace length, fork line index, query-source lexical overlap band, fork type) are computed and comparable across the three sets, checked in the pilot (Section 5; proposal §3.4).
- [ ] All three form renderings (S1/S2/S3) were verified byte-identical on every line except the fork line, for at least one sample item (Section 6).
- [ ] The event log schema in the running SQLite database matches the tables specified in Section 7 (event-level, per-block, per-session).
- [ ] The web app's replay engine makes no live LLM/retrieval calls during a session — confirmed by code inspection or network-call logging during a session (Section 7; proposal §3.6, §4).
- [ ] A pilot of 3-4 participants has been completed and logged, with resulting revisions to task timing/wording noted (proposal §"Deliverables": "a completed pilot of 3-4 people with tasks and timing revised").
- [ ] IRB decision status is recorded, if applicable (proposal §"Participants": required before recruitment if publication is intended).
