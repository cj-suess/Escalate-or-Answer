# Planned changes to the study apparatus (decided 6 October 2026, built 10 October 2026)

These changes were agreed by the authors and are described in the paper's Method section as if complete. Each item says what changes, why, and which files it touches. **Status on 10 October 2026:** all eight changes are built; the regression report is `REGRESSION_2026-10-10.md` (all checks pass).

| Change | Status | Where |
|---|---|---|
| 1 Cross task set with form | Built | `escalate/rotation.py` (plan, worksheet, balance check), `tasks.py` writes `_sets.json` with forks, `_study.json`, `_worksheet.json`; `study.js` builds blocks from `/api/plan`; `FORM_TIE` removed |
| 1a New forks | Built | J6 (Set 1), R9 (Set 2; R8 passes too and is the backup), S5 (Set 3) selected in `tasks/catalog.json`; all fired on the authored fork and survive the blind probe |
| 2 Reword S1 sheet lines | Built | `tasks/catalog.json`, records rebuilt, `task_catalog.md` regenerated |
| 3 Instrument screens and session flow | Built | `playground/index.html`, `study.js`, `style.css`; `server.py` tables `block_instruments` and `session`, endpoints `/api/plan`, `/api/worksheet`, `/api/instruments`, `/api/session` |
| 4 Dwell and verification tooling | Built | focus pause (`focus_lost`/`focus_gained`), `source_scroll`, `source_open_at_fork`, `focus_lost_s`; test database set aside as `events.test-rows-before-2026-10-10.sqlite.bak` |
| 5 Matching statistics | Built | `escalate/matching.py`, `python -m escalate matching`, `data/tasks/_matching.json` |
| 6 Participants fields | Built | entry screen and `session` table: standing, gender, course of study, prior Falcon use, pilot flag |
| 7 Stale descriptions | Built | `catalog_report.py` + `tasks/catalog_preamble.md` (regenerated `task_catalog.md`), `README.md`, `RUNBOOK_CHECK.md`, paper figures |
| 8 Regression test | Built | `REGRESSION_2026-10-10.md`: worksheet balance, byte-identical rebuild, API, full browser session for P07, dwell pausing, screenshots, static checks all pass. Open item: confirm the dwell pause once in a real (non-headless) browser before the pilot |


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

## 1a. Candidate forks for approval (drafted 10 October 2026)

Change 1 needs three more forks, one per set. The candidates below were authored against the frozen snapshot (all passages quoted are verbatim from `data/snapshot/pages.jsonl`; chunk ids are from `data/chunks.jsonl`). None has been run through the pipeline yet. Once approved, each goes into `tasks/catalog.json` as a pair and `python -m escalate tasks` decides whether its fork check fires on the authored fork, which option the assistant recommends (the higher-ranked passage) and whether the deciding fact fails the blind probe. Put every approved candidate in, not only the first choice: the pipeline is cheap and it is the arbiter. Sheet lines are written for the single cover story (a course project that fine-tunes an image model on Falcon, worked on from the labs and from home).

Each candidate was checked against the seven rules in `task_catalog.md`: two documented options, one unstated user fact, an unambiguous key, conditions only on the page, no source pair or deciding fact shared with a selected fork (J1, J2, R3, R6, S1, S2). Whether the fork check fires and whether the fact fails blind can only be known by running the pipeline; the "risk" line gives the expected outcome.

### Set 1 (jobs)

**J6, first choice: where the long preprocessing job runs.** Deciding fact: whether the job runs on a shared CS lab workstation or on Falcon.
- Query: *"How should I run my long preprocessing job on the CS systems?"*
- Options: `nice -n 19 python preprocess.py` (Compute Jobs policy, `p038-c04`: "It is mandatory social etiquette that all long-running and background jobs be run with a nice value of 19") and `sbatch preprocess.sh` (Job Handling, `p009-c01`: "you must ask the cluster's scheduling system to run your program on the compute nodes. To do this, you must submit a unique script").
- Sheet lines: *Your Falcon account is not active yet, so the data preprocessing runs overnight on a CS lab workstation.* / *The data preprocessing runs on Falcon.* Questions: *How do you start the preprocessing run on the lab workstation?* / *How do you start the preprocessing run on Falcon?*
- Exclusivity: hard one way (no Slurm on lab workstations), documented rule the other (programs must not run on the login nodes). Blind probe: *What nice value does the CS department require for long-running jobs on lab machines?* → 19 (the sibling fact, ionice 7, already fails blind in `qa_annotated.jsonl`; 19 is the maximum nice value, so the model may guess it: medium risk).
- Risk: retrieval must put a Compute Jobs chunk and a Falcon chunk in the top four for one query. Medium.

**J5, second choice: checking on a running job.** Deciding fact: what you need to find out, whether the job has started or how much GPU memory it is using.
- Query: *"How do I check on my GPU job after I submit it?"*
- Options: `squeue --user=<you>` (Monitoring Jobs, `p013-c02`: "The command `squeue` provides an overview of jobs in the scheduling queue") and `sgpu <jobid>` (GPU Jobs, `p020-c03`: "you can monitor the GPU usage to check the memory usage of one or more GPUs in your job").
- Sheet lines: *You submitted the training run ten minutes ago and want to know whether it has started.* / *The training run is running and you want to know whether the batch size fits in GPU memory.* Questions: *Which command tells you whether the run has started?* / *Which command shows the run's GPU memory use?*
- Exclusivity: hard both ways (squeue shows no GPU memory; sgpu shows no queue state). Blind probe: *On Falcon, which command shows the GPU memory usage of your job?* → `sgpu` (a Falcon-local wrapper; the model will say nvidia-smi: low risk).
- Risk: the deciding fact is a goal rather than a situation, so it is the least like the other eight forks; the Monitoring page has six chunks and the judge may fork on squeue vs scontrol vs sstat instead. Medium. `p020-c03` was J4's Source B, but J4 is excluded.

**J7, backup: an interactive shell you can come back to.** Deciding fact: whether you need to disconnect and reconnect to the same allocation.
- Query: *"How do I get an interactive shell on a Falcon compute node?"*
- Options: `srun --nodes=1 --ntasks=1 --mem=4G --time=00:05:00 --pty /bin/bash` (Interactive Jobs, `p026-c01`) and `salloc ... ` then `srun --jobid=<id> --pty /bin/bash` (`p026-c02`: "For situations where you would like to come back to your interactive session (after disconnecting from it), you can use SLURM's `salloc` command").
- Exclusivity: documented condition one way, default the other. Blind risk high: both commands are generic Slurm and the model is likely to answer the probe correctly. Use only if J5 and J6 both fail.

### Set 2 (access and remote connection)

**R8, first choice: leaving a remote desktop session.** Deciding fact: whether you will come back to the same session.
- Query: *"How do I close my remote desktop session on the CS machine?"*
- Options: *close the RDP window* (Remote Desktop, `p044-c03`/`c05`/`c07`: "If you would like to keep the session running and come back to it later, you can pause it by simply closing the RDP window") and *log out from the desktop's logout menu* (`p044-c04`/`c06`/`c08`: "If you would like to terminate the session completely, you need to log out inside of your RDP session, using the logout menu item of the desktop environment"). The Overview chunk (`p044-c00`) adds the hard part: "All sessions, which are not connected for over 48 hours, are automatically terminated" and "To completely end a session you need to log out ... instead of interrupting the connection."
- Sheet lines: *You work on the project over remote desktop from home and will continue in the same session tomorrow.* / *You have finished on the remote desktop machine for the semester and must end the session.* Questions: *How do you leave the remote desktop for today?* / *How do you end the remote desktop session?*
- Exclusivity: hard both ways (closing the window does not end a session; logging out destroys the session you wanted to keep). Blind probe: *How long can a disconnected RDP session on a CS Linux machine be reconnected to?* → 48 hours (already fails blind in `qa_annotated.jsonl`: low risk).
- Risk: low on retrieval, because the pausing and terminating chunks repeat three times (one per OS tab) and are near-identical, so the top four will hold both options with a tiny margin. The page is also R5's Source B, but R5 is excluded.

**R9, second choice: first login to the course VM.** Deciding fact: the guest OS of your virtual machine.
- Query: *"What password do I use the first time I log in to my course VM as vmuser?"*
- Options: *make up a new password at the first login* (Ubuntu VMs, `p073-c00`: "Login as the 'vmuser', you will have to create your password the first time you login") and *enter the temporary password SNA gave you* (Windows VMs, `p074-c00`: "you will have to provide a temporary password the first time you login. This must have been provided when the VM was created for you by SNA").
- Sheet lines: *Your course virtual machine runs Ubuntu.* / *Your course virtual machine runs Windows.* Questions: *What do you type at the VM's first password prompt (Ubuntu)?* / *(Windows)?*
- Exclusivity: hard both ways. Blind probe: *What username do you log in with on a CS VMware course VM?* → vmuser (low risk).
- Risk: the two chunks are small and almost identical, so retrieval is safe. R6b already uses the VMware portal, so Set 2 would carry two VM tasks; they test different facts and land in different blocks, but it is a narrative repeat. Low to medium.

**R10, backup: desktop environment for a slow connection.** `startxfce4` vs `gnome-session` in `.xsession` (`p044-c09`, `p044-c11`: "Use XFCE desktop environment" under Troubleshooting). Deciding fact: whether the home connection lags. Exclusivity is documented-condition one way only (GNOME also works), and it shares the Remote Desktop page with R8, so take at most one of the two.

**R1 rescue, backup: VPN before SSH.** The 6 October run came within 0.005 of the margin on "Do I need anything before I SSH to Falcon?" (0.1046, judge attribute "user's location", the authored fork). A rephrase may fire, but one passage states both conditions and the fact is generic (universities need VPN off campus), so it will probably pass blind. Lowest priority.

### Set 3 (storage and software)

**S3 as planned has two problems.** Its Source A (`p065-c00`, the quota table) is the same chunk as S1's Source B, so a participant would see the same highlighted passage in two blocks, and S1's key logic depends on the quota that S3 teaches (40 GB exceeds 16000 or 24000 MB), so whichever comes first primes the other. Its Source B (`p065-c02`, du -sh) does not contain either option, so the fork is not two passages giving different answers. It also asks a lookup ("What is your home quota?") where every other task asks for an action. Keep it only as the backup.

**S5, first choice: which TensorFlow to load.** Deciding fact: the TensorFlow major version the starter code needs.
- Query: *"How do I use TensorFlow on the CS machines?"*
- Options: `module load python/anaconda` (Using TensorFlow, `p060-c00` "How do I use TensorFlow version 2.x?": "You may use either Anaconda, or the modules bundle for Python 3.6/3.8/3.9") and `module load deprecated/tensorflow-1.15` (`p060-c01` "How do I use TensorFlow version 1.x?": "We have version 1.15 available, if you need to use the older version of TensorFlow"). The two sections are separate chunks on one page, the same shape as R3.
- Sheet lines: *The starter code for the image model is written for TensorFlow 2.* / *The starter code for the image model is written for TensorFlow 1 and has not been ported.* Questions: *Which module do you load before running the starter code (TF 2)?* / *(TF 1)?*
- Exclusivity: hard both ways (TF 1 code does not run under TF 2 and the page gives a separate module for each). Blind probe: *Which environment module provides TensorFlow 1.15 on CS machines?* → `deprecated/tensorflow-1.15` (low risk).
- Risk: the TF 2 passage names two routes (Anaconda or a bundle), so the option label must say "load python/anaconda" and the key must accept only that string; the picker shows only the two labels, so this is a wording matter, not an ambiguity for the participant. Fits the fine-tuning cover story directly. Low.

**S6, second choice: setting Python paths after a user install.** `p056-c03`: "If you have loaded one of the Python bundles via environment modules, you do not need to set the paths above. The Anaconda environment module does not automatically handle user-installed Python paths, so you will need to set the paths appropriately." Deciding fact: which Python module you loaded. Options: *add ~/.local to PYTHONPATH* vs *nothing, the module handles it*. Both conditions sit in one chunk and the "nothing" option is not a command, so it is weaker than S5.

### Outcome of the pipeline run (10 October 2026)

J6, S5, R8 and R9 fired on the authored fork and survive the blind probe (R8 after its pause option was re-pointed at the Overview sentence that carries the 48-hour fact, so the informed probe could see it). J5 never fired: the squeue chunk ranks 9th to 39th for every phrasing, so the judge never saw both options. **Selected:** J6, R9, S5. R9 was chosen for Set 2 because each of its two pages states only its own condition, whereas R8's re-pointed Source A (the Overview chunk) states both conditions, the weakness S3 had. R8 stays in the catalog as the eligible backup; swapping is one `selected` flag and a rebuild.

### If all first choices pass

The nine forks would be J1, J2, J6 (jobs); R3, R6, R8 (access); S1, S2, S5 (storage and software). Deciding facts: job length, GPU memory and count, where the job runs; at the console or over SSH, which service you log in to, whether you return to the session; output size and whether it is kept, login shell, TensorFlow version. No two share a source chunk or a fact. The "8 of 25 phrasings" figure in the paper's Apparatus section will change once the new queries are run.

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
- Closing an open overlay when the S1 modal appears is not needed (the chips stay usable), but log whether a source was open at fork onset (`source_open_at_fork` on the summary row).
- Clear the test rows from `data/sessions/events.sqlite` before the first real session (delete the file; it is git-ignored and recreated on first write).

## 5. Matching statistics

**Now.** Sets are matched by construction on trace length (seven lines) and fork position (line 6); exclusivity type is recorded per fork.

**To add.** A small script that reports, per task: words in Source A and Source B pages, words in the highlighted passages, and query-to-passage token overlap, so the pilot report can show the sets are comparable. After change 1 this matters less, because set is crossed with form, but it is cheap and the proposal promised it.

Files: new `escalate/matching.py`, output `data/tasks/_matching.json`.

## 6. Record what the Participants section reports

**Now.** The task tables carry only `participant_code`. The paper's Participants section reports undergraduate or graduate standing, gender, course of study and the screening answer (no prior use of Falcon).

**Change.** Add those four fields to the `session` table from change 3 and collect them on the opening screen, after the participant number. Standing and gender as a short pick list with a free-text option; course of study free text; screening as a yes/no item that the experimenter sees before the practice tasks.

Files: `escalate/server.py`, `playground/index.html`, `playground/study.js`.

## 7. Update everything that still describes the old design

The catalog report and the README are generated or written for the tied design (four tasks per block, two forks per set, six traces). After changes 1 and 2 they contradict the paper.

- `escalate/catalog_report.py`: the hard-coded "Counts at a glance" rows (12 measured tasks, 3 blocks × 4, 6 source pairs, 6 + 2 traces, 2 / 2 per block, 216 trials at N = 18) and the sentence "This is how each block gets exactly 2 correct and 2 wrong" must become 9 tasks, 3 × 3, 9 forks, 9 + 2 traces, four or five of each per participant, 108 trials at N = 12. Section "Where v4 was changed", item 7, should say the confound is resolved.
- `README.md`, "The study view" section: the experimenter bar no longer sets form and task set; describe the participant-number entry and the deep link for the experimenter (`#pcode=P07&block=2` to resume a session).
- `RUNBOOK_CHECK.md`, row "Set → form tie preserved": status becomes Deviates, with a pointer to change 1.
- v4 proposal (`Assets/checkpoint2/new_proposal.tex`): the Design paragraph still says Latin square of set and form with N = 18. Leave it as the historical proposal, but the "what changes" note should say the paper supersedes it.

## 8. Regression test before the pilot

Once changes 1 to 7 are in, run a scripted regression pass (a Fable agent driving the local server, or a Playwright script it writes) and file the result as `system/REGRESSION_<date>.md`. It has to show, for every participant number 1 to 15:

- the worksheet gives three blocks of three tasks, one task per set per block, each fork once, at least one correct and one wrong per block, four or five correct in total;
- across participants 1 to 12 every fork appears under every form twice and in each twin version six times, and each block order appears twice;
- a full session (practice, three blocks, instruments, closing screen) runs end to end at debug pace and writes 9 `task_summary` rows, 3 `block_instruments` rows and 1 `session` row, with `decision_time_s` measured from `fork_onset` and `verified` set only when summed dwell reaches 3 s;
- dwell stops accumulating while the tab is hidden;
- `python -m escalate tasks` still reproduces `_manifest.json` from the catalog, and `catalog_report` regenerates `task_catalog.md` without the stale counts.

## Cross-check against the paper (10 October 2026)

Each claim the paper's Method makes about the apparatus, checked against the system as built and against the changes above. Paper text is `Assets/paper/main.tex` at the working-tree version of 10 October.

| Paper says (section) | System now | Covered by |
|---|---|---|
| Nine forks, three per set, each in two twin versions; a participant meets each fork exactly once, in one version (Tasks) | Six forks selected (J1, J2, R3, R6, S1, S2); each participant would meet both twins of a fork | Change 1. Three forks to add: one Set 1, one Set 2 (R4 eligible but weak; prefer new), S3 for Set 3. **The paper keeps twins.** "No duplicate queries" means no participant sees the same fork or query twice, not that twins are dropped: the twin is how correctness is varied without editing the agent, and the paper's Tasks and Design text both depend on it. |
| One block of three tasks per form, one task from each set (Design, Procedure) | A block is a set of four tasks, tied to one form | Change 1 |
| Every block has at least one correct and one wrong; every participant gets four or five of each (Design) | 2 / 2 per block by construction of the tie | Change 1, rotation rules |
| Six block orders, two participants each, fork-to-form rotation balanced within order; 12 participants, 108 tasks, 18 per cell (Design) | `block_order_group` is logged but nothing assigns it | Change 1 (generator), change 3 (assignment from participant number) |
| The application assigns block order and task rotation from the participant number (Apparatus, Interface) | Experimenter picks form and set in the bar | Change 3, session flow. This is the "experiment mode": participant number in, everything else assigned. Keep the current bar as a debug mode behind a flag. |
| Instrument screens between blocks and at the end (Interface, Procedure, Measures) | None | Change 3 |
| Raw NASA-TLX, intrusion item (1 to 7, MiPP-Eval wording), manipulation check with three options (Measures) | None | Change 3, `block_instruments` table. Store the manipulation-check response and whether it matched the block's form. |
| Closing screen: ranking of the three forms with a free-text reason (Measures) | None | Change 3, `session` table |
| Two practice tasks with experimenter-guided open, Reject and Accept (Procedure) | P1, P2 exist; run from the bar | Change 3, session flow runs them first |
| One cover story, a three-line spec sheet per block, one line per task (Tasks, Procedure) | One sheet per set with a set-specific heading, four lines | Change 1 (sheets), change 2 (reword S1 lines so they read under a mixed sheet) |
| Verification = a source viewed for 3 s of summed dwell before Accept; source pattern under the same threshold; raw dwell per source (Measures) | Implemented (`MIN_DWELL_S`, `dwell_a_s`, `dwell_b_s`, `source_pattern`) | Done. Change 4 adds focus pausing and scroll logging; the 3 s rule itself is unchanged. |
| Decision time = fork-line onset to Accept (Measures) | `decision_time_s` from `forkT`, set at `fork_onset` | Done |
| Logged: Send, each line onset, fork onset, modal pick, source open and close with duration, Reject, picker choice, Accept (Logging) | All present: `send`, `trace_line_onset`, `fork_onset`, `modal_pick`, `source_open`, `source_close`, `reject`, `picker_choice`, `accept`, plus `task_start`, `block_start`, `block_end` | Done |
| Per-task summary: final value, accuracy, following, verification, source pattern, dwell per source, decision time (Logging) | `task_summary` has all of these | Done |
| Participants: standing, gender, course of study, screening for prior Falcon use (Participants) | Not collected | Change 6 (new) |
| Trace lines at a fixed 3 to 5 s delay stored in the record; only line 6 differs by form (Apparatus) | Implemented | Done |
| Recommendation is the higher-ranked option; fork check margin ≤ 0.10 and judge, options must match the authored fork; 8 of 25 phrasings (Apparatus) | Implemented and logged | Done. The three new forks in change 1 must pass the same check, and the "8 of 25" figure in the paper changes when they are run. |
| Pipeline: 77 pages, 23,965 words, 226 chunks, nomic-embed-text, qwen2.5:7b-instruct, Ollama 0.35.1, seed 567, crawl 3 October (Apparatus) | Matches `MODEL_VERSIONS.md` and the snapshot | Done |

Not in the paper, kept anyway: change 5 (matching statistics) was promised in the v4 proposal and costs little; change 4's focus pausing and scroll logging make the dwell measure defensible but are implementation detail, so the paper need not mention them.

Mapping to the short list agreed on 10 October: (1) no duplicate queries → change 1; (2) one task per set per form and (3) three tasks per block → change 1; (4) experiment mode → change 3; (5) questionnaire between systems → change 3; (6) dwell testing → change 4 and change 8; (7) new questions for the forks not yet twinned → change 1, three new forks; (8) regression agent → change 8.
