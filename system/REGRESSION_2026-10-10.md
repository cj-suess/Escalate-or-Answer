# Regression check of the rebuilt study apparatus, 10 October 2026

Scope: planned change 8 in `PLANNED_CHANGES.md`, run against the working tree after changes 1 to 7 were implemented. Tests were run from `system/` with Python 3.13.1 and Node 22.14; the browser checks used Playwright 1.x with Chromium 153 in a scratch virtual environment outside the project. The server under test was `python -X utf8 -m escalate serve 8598`. The database it wrote (`data/sessions/events.sqlite`) was deleted at the end; `data/sessions/` holds only the pre-existing `events.test-rows-before-2026-10-10.sqlite.bak`.

## Summary table

| # | Check | Result | Evidence |
|---|---|---|---|
| 1a | `escalate worksheet 15`: 3 blocks × 3 tasks, one task per set per block, 9 distinct forks, ≥1 correct and ≥1 wrong per block, 4 or 5 correct per participant (P1–P15) | PASS | Recomputed from `data/tasks/_worksheet.json` by an independent script (not the module's own check): "per-participant problems: none"; every task id's record matched its pair, set and twin version |
| 1b | Over P1–P12: every fork × form × twin version exactly 2; each order group twice | PASS | 54 cells, all = 2; order groups {1:2, 2:2, 3:2, 4:2, 5:2, 6:2}; `block_order` equals the blocks' forms |
| 2 | Rebuild reproducibility: `escalate tasks` leaves `_manifest.json` byte-identical | PASS | `cmp` of the manifest before/after: identical; run printed "42 task records", 36 queries, 24 fired, 12 on the authored fork, 18/20 survivors |
| 3a | GET /api/tasks | PASS | 200; 42 records; sets 1/2/3 forks `[J1,J2,J6]`, `[R3,R6,R9]`, `[S1,S2,S5]`, practice `[]`; `study` has `cover_story` (286 chars) and `set_labels` |
| 3b | GET /api/plan?participant=N, N = 1..15, equals the worksheet; practice `[P1,P2]` | PASS | all 15 match |
| 3c | GET /api/plan with a bad code | PASS | `abc` → 400 `participant code has no number: 'abc'`; missing parameter → 400 |
| 3d | GET /api/worksheet?n=12 | PASS | 200, 12 participants, balance "ok" |
| 3e | POST /api/session (start), /api/events with a summary carrying `source_open_at_fork` and `focus_lost_s`, /api/instruments, /api/session (end, upsert) | PASS | all 200; rows read back with every column; `session` row updated in place (one row with both `started_utc` and `finished_utc`, ranking stored as JSON text) |
| 3f | Schemas of the four tables | PASS | `events` 12 cols, `task_summary` 20 cols (incl. `source_open_at_fork TEXT`, `focus_lost_s REAL`), `block_instruments` 14 cols, `session` 15 cols (see listing below) |
| 4a | P07 automatic session reaches the "Thank you" screen | PASS | 38 s at pace 0.1; zero console errors/warnings; zero page errors |
| 4b | P07 rows: 11 `task_summary` (2 practice + 9 measured), 3 `block_instruments` (S1, S2, S3), 1 `session` with ranking and `finished_utc` | PASS | counts 11 / 3 / 1; ranking `["S2","S1","S3"]`, reason "autofilled by debug mode" |
| 4c | Event types present | PASS | accept 11, autofill 11, block_end 4, block_start 4, fork_onset 9, modal_pick 3, send 11, source_open_at_fork 9, task_start 11, trace_line_onset 77 |
| 4d | `decision_time_s` null for practice, positive for measured | PASS | practice: None, None; measured 0.37–0.57 s (pace 0.1, auto-accept) |
| 4e | Nine measured item ids equal the worksheet plan for P7 | PASS | `J1a R6b S5a / R9b S1b J2a / S2b J6a R3a` both sides |
| 4f | `manip_correct` recorded | PASS | values 0, 1, 1 (debug autofill picks the middle option of a shuffled list, so 0 is expected, not a defect) |
| 5a | P08 manual: open Source A ≈ 3.5 s, close, Accept | PASS | `verified=1, dwell_a_s=3.54, opens_a=1, source_pattern="recommended only", source_open_at_fork="A"`; `source_close` logged `3.541` s for that open |
| 5b | Dwell pauses while the window is unfocused / the tab hidden | PASS (handlers) / INCONCLUSIVE (real tab switch) | Dispatching `blur` for 3 s then `focus` + 1 s: `dwell_a_s=1.04` for 4.03 s wall, `focus_lost_s=3.01`, events `focus_lost window_blur` → `focus_gained window_focus`. Faking `document.hidden` + `visibilitychange` for 2 s then 1.5 s visible: `dwell_b_s=1.55`, `focus_lost_s=2.01`, events `tab_hidden` → `tab_visible`. Bringing a second headless tab to the front for 3 s fired neither event in headless Chromium (`dwell_a_s=5.37` for 5.33 s wall, no focus events), so the real-browser path still needs a manual alt-tab check before the pilot |
| 5c | `source_scroll` events after scrolling the overlay | PASS | `A pos=1 highlight_visible=1` then `A pos=0 highlight_visible=1` (plus the open-time `pos=0` event) |
| 5d | Instrument screen validation and submission; break screen; closing validation (duplicate ranks rejected) and submission | PASS with note | closing: "Please give each version a different rank." shown, then accepted with distinct ranks; instrument screen with nothing answered did not submit (see defect 1 for the message) |
| 6 | Screenshots | PASS (see notes) | listed below |
| 7a | `node --check` study.js, common.js, app.js | PASS | |
| 7b | `py_compile` of every module in `escalate/` | PASS | |
| 7c | `FORM_TIE` / `form_tied_to` only in PLANNED_CHANGES.md and RUNBOOK_CHECK.md | PASS | no occurrence in .py/.js/.html/.json |
| 7d | Stale phrases in README.md and task_catalog.md ("3 blocks × 4", "2 / 2", "N = 18", "216", "set is tied", "form_tied_to", "exactly 2 correct", "block of four", "12 measured") | PASS | none (README line 82 "each tied to a verbatim evidence span" is about QA generation, unrelated) |

## Table schemas observed

- `events`: participant_code, session_id, block_order_group, block_index, form, item_id, recommendation_correctness, event_type, event_detail, t_ms, timestamp_utc, source_open_duration_s
- `task_summary`: … final_value, accuracy, followed, verified, source_pattern, dwell_a_s, dwell_b_s, opens_a, opens_b, decision_time_s, total_time_s, source_open_at_fork, focus_lost_s
- `block_instruments`: participant_code, session_id, block_index, form, tlx_mental, tlx_physical, tlx_temporal, tlx_performance, tlx_effort, tlx_frustration, intrusion, manip_response, manip_correct, timestamp_utc
- `session`: participant_code, session_id, participant_number, pilot, order_group, rotation_id, block_order, standing, gender, course_of_study, prior_falcon_use, ranking, ranking_reason, started_utc, finished_utc

## Screenshots (scratch folder `…\scratchpad\reg\shots\`)

- `entry.png`: entry screen with participant 8 typed; assignment preview "order group 2 (S1 → S3 → S2), rotation 1". Nothing wrong.
- `sheet_block1.png` / `task_S1_modal.png`: block 1 under S1. Spec sheet shows the cover story and three labelled lines (JOBS, ACCESS AND REMOTE CONNECTION, STORAGE AND SOFTWARE); line 6 reads "Paused: the sources give different options. Waiting for you." with the modal below; chips remain visible above the modal. Nothing wrong.
- `task_S3_forkline.png`: block 2 under S3; line 6 "Use /s/<hostname>/a/tmp (Source A)" with no warning, answer filled. Nothing wrong.
- `task_S2_warning.png` / `sheet_block3.png`: block 3 under S2; line 6 with the "!" glyph and the warning box "Source A suggests nice -n 19 python preprocess.py." Nothing wrong.
- `instrument.png`: six 21-point TLX rows with anchors (Performance anchored Perfect/Failure), 7-point intrusion item, three manipulation-check options in shuffled order. Nothing cut off.
- `closing.png`: three rank selects and the reason box. Nothing wrong.
- `auto_done.png` / `auto_results.png`: debrief screen and the experimenter results tables. Nothing wrong.

## Defects and notes, by severity

1. Low, `playground/study.js` `submitInstruments` (the "Please answer every item." branch) and `scaleHtml` (`required` on every radio): the custom message can never appear, because the `required` attributes make the browser block submission with its own tooltip first. Submission is still prevented, so data integrity is fine; either drop `required` so the page's own message shows, or delete the dead branch.
2. Note, dwell pausing: the `blur`/`focus` and `visibilitychange` handlers in `study.js` work and log correctly when the events fire, but a genuine tab switch could not be reproduced in headless Chromium. Confirm once in a real browser (alt-tab away for a few seconds with a source open) before the first pilot.
3. Design note, `escalate/rotation.py`: with fork index `(b + s) % 3` and no per-participant rotation, the same three forks always share a block (J1 + R6 + S5, R9 + S1 + J2, S2 + J6 + R3) and the two participants in an order group see identical fork-to-form assignments with opposite twin versions. All stated balance properties hold; this is only worth knowing when describing the rotation in the paper.
4. Note, debug autofill: at the instrument screen the auto-run picks the middle option of the shuffled manipulation check, so `manip_correct` is arbitrary in debug runs (0, 1, 1 for P07). Expected.

No project file other than this report was modified by the regression run. The test database was deleted; the worksheet and task records on disk are the ones the rebuild reproduced byte for byte.
