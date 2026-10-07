# Planned changes to the study apparatus (decided 6 October 2026)

These changes were agreed by the authors and are described in the paper's Method section as if complete. None is implemented yet. Each item says what changes, why, and which files it touches.

## 1. Cross task set with escalation form

**Now.** Each form is tied to one task set (`FORM_TIE` in `escalate/tasks.py`; the study view auto-selects the tied set and warns otherwise). S1 is only ever run on the job-submission tasks, so form and task set cannot be separated in the analysis.

**Change (revised 6 October, afternoon).** Each block holds three tasks, one from each set, and a participant never meets the same fork twice. That needs nine forks, three per set; six are selected now, so three must be added and validated through the pipeline: one new job-submission fork for Set 1 (none of the current candidates fired on its own fork), one access fork for Set 2 (R4 is eligible but weak; prefer a new candidate), and S3 (home quota by status) for Set 3. Each fork keeps its two twin versions; a participant receives one twin, chosen by rotation, so correctness is balanced across participants per fork and within each participant overall.

Rules for the rotation:
- Every block contains at least one correct-recommendation and one wrong-recommendation task, and every participant receives four or five of each over the nine tasks.
- Every fork appears under every form, and in each twin version, equally often across the 12 participants (two per block order).
- Three pilot participants are run first and excluded.

What this touches:
- `escalate/tasks.py`: remove `FORM_TIE` and the `form_tied_to` field; add a function that generates the rotation (block order group 1 to 6, crossed with the set-to-form rotation) from the participant number, and a worksheet export listing every participant's blocks and tasks.
- `data/tasks/_sets.json`: keep the sets, but the block is no longer a set.
- `playground/study.js`: a block is built from the worksheet entry for the participant and block index, not from a set; drop the tie warning; keep `block_order_group`, and log the set of each task (already carried by `item_id`).
- Spec sheets: one cover story for the whole session (a course project on Falcon that involves submitting jobs, connecting from different places, and managing data), and a per-block sheet of three lines, one per task, each labeled with its context.
- Paper, v4 proposal, `task_catalog.md`: Design and Procedure text (the paper is updated; the proposal still describes the tie).

## 2. Reword the Set 3 spec-sheet lines

**Now.** Two Set 3 lines read "Stage 1 writes about 40 GB of intermediate files you can regenerate" and "Stage 5 saves the final 2 GB model, which you must keep". The stage numbers belong to Set 1's assignment and mean nothing under Set 3's heading, and after change 1 the sheets mix sets anyway.

**Change.** Reword to "Your job writes about 40 GB of intermediate files you can regenerate" and "Your final 2 GB model must be kept, and nothing else needs to be stored", then run `python -m escalate tasks` to rebuild the records. The record hashes and `_manifest.json` change; do this before the pilot and re-run `catalog_report` to regenerate `task_catalog.md`.

Files: `tasks/catalog.json` (S1 `sheet_lines`), `data/tasks/`, `Assets/checkpoint2/task_catalog.md`.

## 3. Instrument screens and session flow

**Now.** The study view runs one block at a time from the experimenter bar. There are no questionnaire screens, no per-block or per-session tables, and no automatic block order.

**Change.** Build the screens the Method describes:
- After each block: raw NASA-TLX (six subscales, 21-point scales), one perceived-intrusion item (1 to 7, as in MiPP-Eval), and a manipulation check (which form did you just use: paused and asked, warned but continued, or cited only).
- At the end of the session: a forced ranking of the three forms with a free-text reason.
- Session flow: enter the participant number once; the application assigns the block order group and the set-to-form rotation, runs the two practice tasks, then the three blocks with the instruments between them, then the closing screen.
- Storage: a `block_instruments` table (participant_code, block_index, form, six TLX subscales, intrusion, manipulation-check response and whether it was correct) and a `session` table (participant_code, order group, rotation id, ranking as a JSON array, reason, screening answer).

Files: `playground/index.html`, `playground/study.js`, `playground/style.css`, `escalate/server.py` (two new tables and an `/api/instruments` endpoint).

## 4. Dwell and verification tooling

**Done.** A source counts as viewed when its summed dwell reaches 3 s (`MIN_DWELL_S` in `study.js`); raw opens and dwell per source are logged either way.

**To add.**
- Pause the dwell clock when the browser window loses focus or the tab is hidden, so time away from the screen is not counted as reading (listen for `visibilitychange` and `blur`/`focus`, log `focus_lost` and `focus_gained`).
- Log scroll position inside the source overlay, so a view that never reached the highlighted lines can be identified.
- Close any open overlay when the fork modal appears under S1 is not needed (the chips stay usable), but log whether a source was open at fork onset.
- Clear the test rows from `data/sessions/events.sqlite` before the first real session (delete the file; it is git-ignored and recreated on first write).

## 5. Matching statistics

**Now.** Sets are matched by construction on trace length (seven lines) and fork position (line 6); exclusivity type is recorded per fork.

**To add.** A small script that reports, per task: words in Source A and Source B pages, words in the highlighted passages, and query-to-passage token overlap, so the pilot report can show the sets are comparable. After change 1 this matters less, because set is crossed with form, but it is cheap and the proposal promised it.

Files: new `escalate/matching.py`, output `data/tasks/_matching.json`.

The experiment was a 3 × 2 within-subjects design with factors Escalation Form (S1 modal stop, S2 inline warning, S3
provenance-only) and Recommendation Correctness (correct, wrong). Each form was administered in one block of three
tasks, one from each task set, so that task set was crossed with form rather than tied to it; the rotation was constrained
so that every block contained at least one correct and one wrong recommendation. Block order was counterbalanced
across the six permutations of the three forms, [𝑛] participants per order, and the set-to-form rotation was balanced
within each order. With [𝑁 ] participants this gave [9𝑁 ] measured tasks, about [1.5𝑁 ] per Form × Correctness cell.