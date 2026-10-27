# Session Data Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** No study data is lost or duplicated when a write fails, the browser crashes, a session is resumed, or a participant number is reused.

**Architecture:** The server gets one column registry per table, idempotent inserts (an event `seq` plus unique indexes), strict payload checks that return 400, and a session-history lookup. The client sends every write through a persisted, retrying outbox (`playground/outbox.js`). Events go out as they happen, and a header indicator stays visible while anything is unsaved. A pure decision function (`playground/resume.js`) chooses between new, resume and duplicate on the entry screen. A resume reuses the earlier `session_id` and skips tasks and blocks already stored.

**Tech Stack:** Python 3.11+ standard library (`sqlite3`, `http.server`, `unittest`), plain browser JavaScript with no build step, Node 22 `node:test` for the JS unit tests.

**Spec:** `system/PLANNED_CHANGES.md`, section "11. Session data integrity (database review, 22 October 2026)".

## Global Constraints

- No new Python or JS dependencies; `system/requirements.txt` stays as it is (server is standard library only).
- Plain JavaScript loaded by `<script>` tags; no bundler, no `package.json`. New JS files end with `if (typeof module === "object") module.exports = {...};` so Node tests can `require` them.
- Server keeps listening on `127.0.0.1` only; `data/sessions/` stays git-ignored.
- No new code comments (user preference); keep existing comments where the code they describe is unchanged.
- Commit messages follow the repo's style: one imperative sentence, no `feat:` prefix.
- All commands run from `system/` unless stated. Python tests: `python -m unittest discover -s tests -t . -v`. JS tests: `node --test tests/js/*.test.js`.

## Review Focus

1. **The Python server dies for a few minutes mid-block.** The participant carries on, the header warns, and once the server is back every write lands in order with no duplicates. Pinned by Task 5 `retries in order after the server recovers` and Task 3 idempotency tests.
2. **The browser reloads or crashes mid-task.** Events sent before the crash are in the database, and unsent ones are in `localStorage` and flush on the next page load. Pinned by Task 5 `entries left in the store are sent by a new outbox`.
3. **The server committed a write but the response was lost, so the client retries.** No duplicate row results. Pinned by Task 3 `test_*_twice_stores_one_row`.
4. **The server returns 400 for a payload.** That entry is not retried forever: it is counted as rejected, shown in the header, and the queue moves on. Pinned by Task 5 `a 4xx response moves the entry to rejected and the queue continues`.
5. **`localStorage` throws** (disabled storage or quota). The outbox still works in memory. Pinned by Task 5 `localStore falls back to memory when storage throws`.

---

### Task 1: Column registry and safe connections (`server.py`)

Each column is declared once. The schema and the in-place upgrade are derived from that declaration. Every write runs in a transaction that rolls back and closes on error.

**Files:**
- Modify: `system/escalate/server.py:20-121` (column tuples, `SCHEMA`, `_connect`, `_insert`, `log_events`, `log_instruments`, `upsert_session`)
- Create: `system/tests/__init__.py` (empty), `system/tests/test_server.py`

**Interfaces:**
- Produces:
  - `TABLES: dict[str, tuple[tuple[str, str], ...]]`. It maps table name to `(column, SQL type)` pairs, with keys `"events"`, `"task_summary"`, `"block_instruments"` and `"session"`. Column order and types are copied from the current tuples and `SCHEMA`; in `session`, `gender_self_describe` stays after `gender`.
  - `EVENT_COLS`, `SUMMARY_COLS`, `INSTRUMENT_COLS` and `SESSION_COLS` remain as tuples of names derived from `TABLES`.
  - `_connect() -> sqlite3.Connection` creates any missing tables and runs `ALTER TABLE … ADD COLUMN` for every registry column a table lacks. `session` keeps `PRIMARY KEY (participant_code, session_id)`.
  - `_db()` is a `contextlib.contextmanager` that holds `_db_lock` and yields a connection inside `closing(...)` and `with con:`, so it commits on success, rolls back on error and always closes.
- Tests set `server.SESSIONS_DB` to a temporary path in `setUp`.

- [ ] **Step 1: Write the failing tests** in `system/tests/test_server.py` (`unittest.TestCase`, temp dir per test):
  - `test_fresh_db_has_registry_columns`: after `server._connect()`, `PRAGMA table_info(t)` names equal `[c for c, _ in server.TABLES[t]]` as a set, for every `t`.
  - `test_old_db_is_upgraded`: create the tables by hand without `source_open_at_fork`, `focus_lost_s` (task_summary) and `gender_self_describe` (session); after `server._connect()` those columns exist.
  - `test_failed_write_rolls_back_and_releases_db`: inside `with self.assertRaises(RuntimeError): with server._db() as con:` insert a `session` row then `raise RuntimeError`; afterwards `server.log_instruments(row)` succeeds without delay and `SELECT COUNT(*) FROM session` is 0.
- [ ] **Step 2: Run, expect FAIL** (`AttributeError: module 'escalate.server' has no attribute 'TABLES'`): `python -m unittest tests.test_server -v`
- [ ] **Step 3: Implement** `TABLES`, the derived `*_COLS`, the schema built from `TABLES`, `_connect()` with the generic upgrade loop, and `_db()`. Then rewrite `log_events`, `log_instruments` and `upsert_session` to use `with _db() as con:` and drop their explicit `commit`/`close`.
- [ ] **Step 4: Run, expect PASS:** `python -m unittest tests.test_server -v`
- [ ] **Step 5: Commit:** `git add system/escalate/server.py system/tests && git commit -m "Declare session columns once and close connections on failed writes"`

### Task 2: Strict payloads (400 on unknown keys)

**Files:**
- Modify: `system/escalate/server.py` (`log_events`, `log_instruments`, `upsert_session`, `do_POST`)
- Test: `system/tests/test_server.py`

**Interfaces:**
- Consumes: `TABLES` and the `*_COLS` tuples (Task 1).
- Produces:
  - `class PayloadError(ValueError)`.
  - `_check(row: dict, cols: tuple[str, ...], what: str) -> dict` raises `PayloadError` when `row` is not a dict, has keys outside `cols` (the message is `f"{what}: unknown keys: {', '.join(sorted(extra))}"`), or lacks a non-empty `participant_code` or `session_id`. Otherwise it returns `row`.
  - `/api/events` body keys must be a subset of `{"events", "summary"}`; anything else raises `PayloadError("events body: unknown keys: …")`.
  - `do_POST` maps `ValueError` (which includes `PayloadError`) to `400 {"error": str(e)}` before the generic 500 handler.

- [ ] **Step 1: Write the failing tests:**
  - `test_unknown_event_key_rejected`: `server.log_events([{**EV, "evnt_type": "x"}])` raises `PayloadError` whose message contains `"evnt_type"`. `EV` is a module-level valid event fixture built from the field list in `study.js` `log()`.
  - `test_unknown_summary_key_rejected`, `test_unknown_instrument_key_rejected`, `test_unknown_session_key_rejected`: same pattern for the other three writers.
  - `test_missing_session_id_rejected`: an event with `session_id` removed raises `PayloadError`.
  - `test_client_payloads_accepted`: fixtures copied key-for-key from `study.js` (event from `log()`, summary from `accept()`, instrument row from `submitInstruments()`, the start and closing session rows) are all stored without error.
  - `test_http_unknown_key_returns_400`: start `ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)` in a daemon thread and POST `{"events": [{**EV, "bogus": 1}]}` to `/api/events`. The response status must be 400 and the JSON `error` must contain `"bogus"`.
- [ ] **Step 2: Run, expect FAIL** (no `PayloadError`).
- [ ] **Step 3: Implement** `PayloadError`, `_check`, the calls to it in the three writers, the body-key check for `/api/events`, and the `except ValueError` branch in `do_POST`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit:** `git commit -am "Reject session payloads with unknown keys instead of storing NULL"` (add the test file if untracked).

### Task 3: Idempotent writes

Retries and resumed sessions must never create a second row.

**Files:**
- Modify: `system/escalate/server.py`
- Test: `system/tests/test_server.py`

**Interfaces:**
- Consumes: `TABLES`, `_connect`, `_check` (Tasks 1–2).
- Produces:
  - A new events column, `("seq", "INTEGER")`, appended to `TABLES["events"]`. It is required on every event, and an event without an integer `seq` raises `PayloadError`.
  - Unique indexes created in `_connect()` after the column upgrade:
    - `events_session_seq ON events(session_id, seq)`
    - `task_summary_session_item ON task_summary(session_id, item_id)`
    - `block_instruments_session_block ON block_instruments(session_id, block_index)`
  - Inserts into `events`, `task_summary` and `block_instruments` use `INSERT OR IGNORE`.
  - `log_events(events, summary=None) -> int` returns the number of rows actually inserted (events plus summary), from `con.total_changes`. `/api/events` returns `{"logged": n}` unchanged in shape.

- [ ] **Step 1: Write the failing tests:**
  - `test_event_twice_stores_one_row`: `log_events([EV])` twice gives one row in `events`, and the second call returns 0.
  - `test_summary_twice_stores_one_row`: `log_events([], SUMMARY)` twice gives one `task_summary` row.
  - `test_instruments_twice_stores_one_row`.
  - `test_event_without_seq_rejected`.
  - `test_same_seq_other_session_is_kept`: the same `seq` under two `session_id`s gives two rows.
  - Update the `EV` fixture to carry `"seq": 1`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** the column, the indexes, `INSERT OR IGNORE`, the `seq` check and the inserted-row count.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit:** `git commit -am "Make session writes idempotent with an event seq and unique indexes"`

### Task 4: Session history lookup (`GET /api/session`)

**Files:**
- Modify: `system/escalate/server.py` (new function and a `do_GET` branch)
- Test: `system/tests/test_server.py`

**Interfaces:**
- Produces:
  - `session_history(participant_code: str) -> list[dict]` returns one dict per `session` row for that code, ordered by `started_utc`. Each dict has the keys:
    - `session_id: str`, `pilot: int`, `started_utc: str | None`, `finished_utc: str | None`
    - `max_seq: int`: the highest `events.seq` for the session, or 0 if it has none
    - `tasks_done: list[str]`: `task_summary.item_id`, sorted
    - `blocks_done: list[int]`: `block_instruments.block_index`, sorted
  - `GET /api/session?participant_code=P07` returns `200 {"sessions": session_history(code)}`. A missing or empty parameter returns 400 with `"participant_code is required"`.

- [ ] **Step 1: Write the failing tests:**
  - `test_history_empty_for_unknown_code` returns `[]`.
  - `test_history_reports_progress`: store a session row, events with seq 1..5, summaries for `J1a` and `R6b`, and instruments for block 1. The history entry then has `max_seq == 5`, `tasks_done == ["J1a", "R6b"]`, `blocks_done == [1]` and `finished_utc is None`.
  - `test_history_only_this_participant`: rows for `P08` do not appear under `P07`.
  - `test_http_history_requires_code`: GET `/api/session` returns 400.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement** `session_history` (read under `_db()`) and the `do_GET` branch.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit:** `git commit -am "Add GET /api/session to report a participant's earlier sessions and progress"`

### Task 5: Client outbox (`outbox.js`) and HTTP status on API errors

**Files:**
- Modify: `system/playground/common.js:6-11` (`api`)
- Create: `system/playground/outbox.js`, `system/tests/js/outbox.test.js`

**Interfaces:**
- `api(path, body)`: on a non-OK response it throws an `Error` with `.status = r.status`. A network failure throws without `.status`, as it does now. A non-JSON error body still throws with `.status` and the status text as the message.
- `outbox.js` exports:
  - `memoryStore() -> Store`.
  - `localStore(key: string, storage = globalThis.localStorage) -> Store`. It persists JSON under `key`; if `storage` is missing or any call throws, it falls back to `memoryStore()` behaviour.
  - `Store` is `{ load(): {queue: Entry[], rejected: Entry[]}, save(state): void }`, and `Entry` is `{ id: string, path: string, body: object, error?: string }`.
  - `createOutbox({ send, store, retryDelaysMs = [1000, 2000, 5000, 10000], onChange = () => {} })` returns:
    - `enqueue(path, body) -> Promise<boolean>`: appends to the queue, saves, runs a flush pass, and resolves `true` if this entry was confirmed in that pass and `false` if it is still queued or was rejected.
    - `flush() -> Promise<void>`: sends queued entries strictly in order, one at a time; only one pass runs at a time.
    - `status() -> {pending: number, rejected: number}`.
  - Flush rules:
    - When `send` resolves, the entry is removed.
    - When `send` rejects with `err.status` from 400 to 499, the entry moves to `rejected` with `error: err.message` and the pass continues.
    - Any other rejection stops the pass and schedules `flush()` after `retryDelaysMs[min(failures - 1, last)]`. `failures` resets on a successful send.
    - The store is saved and `onChange(status())` called after every change.

- [ ] **Step 1: Write the failing tests** (`node:test`, `node:assert/strict`). Each uses `memoryStore()`, `retryDelaysMs: [5]`, and a fake `send` that records `(path, body)`:
  - `enqueue resolves true once the server confirms`.
  - `retries in order after the server recovers`: `send` rejects (no status) for its first 3 calls. After enqueuing `a`, `b` and `c` and waiting until `status().pending === 0`, the recorded successful bodies are `[a, b, c]`.
  - `enqueue resolves false while the server is down`.
  - `a 4xx response moves the entry to rejected and the queue continues`: `send` rejects with `status: 400` for `b` only. The result is `status()` of `{pending: 0, rejected: 1}`, with `a` and `c` sent.
  - `entries left in the store are sent by a new outbox`: seed a store with two queued entries; `createOutbox(...).flush()` sends both in order and empties the store.
  - `localStore falls back to memory when storage throws`: a fake storage whose `getItem` and `setItem` throw; `enqueue` still resolves true.
  - `onChange reports pending and rejected counts`: the last call after a down-then-up sequence is `{pending: 0, rejected: 0}`.
- [ ] **Step 2: Run, expect FAIL:** `node --test tests/js/*.test.js` (`Cannot find module`).
- [ ] **Step 3: Implement** `outbox.js` and the `api` status change.
- [ ] **Step 4: Run, expect PASS;** also `node --check playground/common.js playground/outbox.js`.
- [ ] **Step 5: Commit:** `git add system/playground system/tests/js && git commit -m "Add a persisted, retrying outbox for study writes"`

### Task 6: Route every study write through the outbox (`study.js`)

**Files:**
- Modify: `system/playground/study.js` (`log`, `accept`, `submitInstruments`, `submitClosing`, `startSession`, `init`, `nextTask`), `system/playground/index.html` (header span, script tag), `system/playground/style.css`

**Interfaces:**
- Consumes: `createOutbox` and `localStore` (Task 5), and the event `seq` (Task 3).
- Produces:
  - `session.seq: number`, starting at 0 for a new session (Task 7 sets it for a resume).
  - Every event carries `seq: ++session.seq`.
  - `outbox`, a module-level constant in `Study`: `createOutbox({ send: api, store: localStore("eoa-outbox"), onChange: showSaveState })`.

- [ ] **Step 1: `index.html`.** Add `<span id="saveState" class="save-state"></span>` after `#progress`, and add `<script src="/static/outbox.js"></script>` before `study.js`. In `style.css`, `.save-state.warn` uses the existing warning colours (the ones `.warn-box` uses).
- [ ] **Step 2: Stream events.** `log()` gives every event (block-level and task-level) a `seq` and calls `outbox.enqueue("/api/events", { events: [ev] })` without awaiting. Remove `task.events`. The outbox persists each entry to `localStorage` on enqueue, which covers `pagehide` and crashes; no `sendBeacon`.
- [ ] **Step 3: Accept.** `accept()` does `const saved = await outbox.enqueue("/api/events", { events: [], summary })`. `#taskMsg` reads `"Saved. Next task in a moment…"` when `saved` is true, and otherwise `"Not saved yet: the app keeps retrying. Keep this window open. Next task in a moment…"`.
- [ ] **Step 4: Other writes.** `submitInstruments`, `submitClosing` and `startSession` use `outbox.enqueue` in place of `api` plus `console.warn`, and do not block on the result.
- [ ] **Step 5: Save-state indicator.** `showSaveState({pending, rejected})` sets `#saveState` and toggles `warn`:
  - `rejected > 0`: `"${rejected} write(s) rejected by the server; see the console."`
  - otherwise `pending > 0`: `"${pending} write(s) not saved yet, retrying. Keep this window open."`
  - otherwise empty.

  Rejected entries are logged once with `console.error`. `init()` calls `outbox.flush()` first, so anything left from a crash goes out.
- [ ] **Step 6: Static check:** `node --check playground/study.js`. Expected: no output.
- [ ] **Step 7: Set aside the old test database before the first run:** `mv data/sessions/events.sqlite data/sessions/events.test-rows-before-2026-10-27.sqlite.bak`.
- [ ] **Step 8: Run a full debug session:** `python -m escalate serve 8598`, then open `http://127.0.0.1:8598/#p=7&pace=0.1&pilot=1&autostart=1&autosend=1` and wait for the debrief screen. Check with `sqlite3 data/sessions/events.sqlite`:
  - `SELECT COUNT(*) FROM task_summary` returns 11.
  - `SELECT COUNT(*) FROM block_instruments` returns 3.
  - `SELECT COUNT(*) FROM session` returns 1, with `finished_utc` set.
  - `SELECT MAX(seq) = COUNT(*) FROM events` returns 1.
  - `#saveState` is empty.
- [ ] **Step 9: Server-down check** (in a real browser: Claude in Chrome, or by hand). Start P08 at pilot pace, stop the server during block 1, and accept a task. `#taskMsg` shows the "Not saved yet" text and `#saveState` shows the pending count. Restart the server: within about 10 s `#saveState` clears. `SELECT session_id, seq, COUNT(*) FROM events GROUP BY 1,2 HAVING COUNT(*) > 1` returns no rows, and P08's task_summary rows are complete for the tasks done.
- [ ] **Step 10: Commit:** `git commit -am "Send study events as they happen and warn while any write is unsaved"`

### Task 7: Resume without duplicates, and a duplicate-participant warning

**Files:**
- Create: `system/playground/resume.js`, `system/tests/js/resume.test.js`
- Modify: `system/playground/study.js` (`previewAssignment`, `onScreening`, `startSession`, `startBlock`, `nextTask`, `endBlock`, `submitInstruments`, `init`), `system/playground/index.html` (dup checkbox, script tag)

**Interfaces:**
- Consumes: `GET /api/session` (Task 4), `session.seq` (Task 6).
- Produces:
  - `decideStart(history: HistoryEntry[], { startAt: "practice" | "1" | "2" | "3", pilot: boolean }) -> { mode: "new" | "resume" | "duplicate", session: HistoryEntry | null }`. It considers only entries whose `pilot` equals `pilot ? 1 : 0`.
    - With no such entries, the result is `new`.
    - With `startAt === "practice"`, the result is `duplicate`, carrying the latest entry.
    - With a block start, the latest entry with `finished_utc == null` gives `resume`; otherwise the result is `duplicate`, carrying the latest entry.
  - On the client session object: `session.done: Set<string>` (task ids already summarised) and `session.blocksDone: Set<number>`. Both are empty for a new session.

- [ ] **Step 1: Write the failing tests** in `tests/js/resume.test.js`:
  - `no history is new`.
  - `practice start with history is duplicate`.
  - `block start resumes the latest unfinished session`: two unfinished entries; the later `started_utc` wins.
  - `block start with only finished sessions is duplicate`.
  - `pilot sessions do not count for a real participant`, and vice versa.
- [ ] **Step 2: Run, expect FAIL:** `node --test tests/js/*.test.js`.
- [ ] **Step 3: Implement** `resume.js`.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Entry screen.**
  - **Recompute the decision.** `previewAssignment` also fetches `/api/session?participant_code=P..` into `entryHistory`. One function, `updateStart()`, recomputes `decideStart` whenever `#pnum`, `#startAt`, `#pilot`, `#priorFalcon` or `#dupOk` changes, and replaces `onScreening`.
  - **Duplicate.** Show `<label id="dupOkWrap" class="check hidden"><input id="dupOk" type="checkbox"> start a new session for this number anyway</label>`. `#entryMsg` reads `"${pcode} already has a session (started ${started_utc}). Tick the box to start a new session anyway."` The prior-Falcon message takes priority over this one.
  - **Resume.** Append `" Resumes session ${session_id}: ${tasks_done.length} tasks done."` to `#assignPreview`.
  - **Start button.** `#startSession` is disabled when `screenedOut() || (mode === "duplicate" && !$("dupOk").checked)`.
  - **Deep link.** `dupok=1` ticks `#dupOk`.
- [ ] **Step 6: Resume flow.**
  - **Flush first.** Before resuming, `startSession` awaits `outbox.flush()` and re-fetches the history, so `max_seq` includes events queued before the crash. If `outbox.status().pending > 0` afterwards, it does not start and `#entryMsg` reads `"Writes from the last session are not saved yet. Check that the server is running, then try again."` Without this guard, reused `seq` values would be dropped silently by `INSERT OR IGNORE`. Add `test_resume_guard`-style coverage by asserting this message in the Step 8 browser check with the server stopped.
  - **Reuse the session.** On `resume`, `startSession` sets `session.id = prior.session_id`, `session.seq = prior.max_seq`, `session.done = new Set(prior.tasks_done)` and `session.blocksDone = new Set(prior.blocks_done)`. It writes no new session row and logs a `session_resume` event (detail: `block ${startAt}`) right after the first `block_start`.
  - **Skip finished tasks.** `nextTask` skips ids in `session.done` but keeps the "task i of n" numbering of the full block. The spec sheet still lists all three lines.
  - **Skip stored instruments.** `endBlock` skips the instrument screen when `session.blocksDone.has(block.index)`. The code after a successful instrument submit moves into `afterInstruments()` so both paths share it.
- [ ] **Step 7: Static check:** `node --check playground/study.js playground/resume.js`.
- [ ] **Step 8: Resume check** (real browser). Start P05 as pilot at debug pace and reload the page after the first task of block 2 is accepted. Enter 5, tick pilot and choose "block 2 (resume)". The preview shows "Resumes session …", and the session finishes.
  - SQL for P05: one `session` row with `finished_utc` set, 11 `task_summary` rows, no `(session_id, item_id)` duplicates, 3 `block_instruments` rows, and one `session_resume` event.
  - Then enter 5 again with "practice": the duplicate message shows and Start stays disabled until the box is ticked.
- [ ] **Step 9: Commit:** `git add system/playground system/tests/js && git commit -m "Resume a crashed session under its own id and warn when a participant number is reused"`

### Task 8: Documentation, regression and cleanup

**Files:**
- Modify: `system/README.md` ("The study view" section, commands table), `system/PLANNED_CHANGES.md` (status row 11, section 11)

- [ ] **Step 1: README.** In "The study view":
  - **New behaviour.** Writes go through a retrying outbox kept in the browser's `localStorage`, and the header warns while anything is unsaved. Events are sent as they happen, each with a per-session `seq`.
  - **Resume and duplicates.** "Start at block N" resumes the latest unfinished session for that number and pilot flag, reusing its `session_id` and skipping stored tasks and instruments. Reusing a participant number otherwise needs an explicit tick.
  - **Analysis dedupe rule.** `task_summary` has at most one row per `(session_id, item_id)` and `block_instruments` one per `(session_id, block_index)`. A task interrupted by a crash leaves partial events. For each `(session_id, item_id)`, analyse only events with `seq` greater than that item's last `task_start`.
  - **Test commands.** Add both test commands from Global Constraints to the commands table.
- [ ] **Step 2: PLANNED_CHANGES.md.** Row 11 status becomes `Built`, with the file list plus `playground/outbox.js`, `playground/resume.js` and `tests/`. Section 11 gets a `**Done.** Built as described below.` line, as items 9 and 10 have.
- [ ] **Step 3: Full test run:** `python -m unittest discover -s tests -t . -v` and `node --test tests/js/*.test.js`, both all PASS. Then `node --check playground/*.js` and `python -m py_compile escalate/*.py`.
- [ ] **Step 4: Worksheet unaffected:** `python -m escalate worksheet 15` still reports a balanced design, and `git status` shows no change under `data/tasks/`.
- [ ] **Step 5: Remove verification data:** delete `data/sessions/events.sqlite` written by Tasks 6–7 (git-ignored test rows). Keep the `.bak` from Task 6 Step 7.
- [ ] **Step 6: Commit:** `git commit -am "Document session data integrity and mark planned change 11 built"`
