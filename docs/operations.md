# Operations notes

Things that are not obvious from `system/README.md`.

## Running the server from a worktree
- Start it from `system/` (`cd system && python -m escalate serve 8598`). From the repo root, `python -m escalate` fails with "No module named escalate".
- A worktree has no `data/sessions/events.sqlite` until the first write. Test runs there never touch the real database in the main checkout.

## Browser checks without Playwright in the repo
- The study flow can be driven headlessly with `playwright-core` installed in a temp folder (not the repo), launched against the installed Chrome:
  `chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" })`.
- Deep links do most of the work: `#p=7&pace=0.1&pilot=1&autostart=1&autosend=1` runs a whole session; add `start=2` to resume at block 2 and `dupok=1` to start a participant number that already has a session.
- The init script runs once per page load. To apply a new hash, call `page.goto(url#hash)` then `page.reload()`.
- Headless Chrome cannot produce a real tab switch, so the dwell pause on `visibilitychange` must be checked in a real browser.
- The one console error on every run is Chrome's own `/favicon.ico` 404. The server has never served a favicon, and it is harmless.

## Checking the session database
- No duplicate events: `SELECT session_id, seq, COUNT(*) FROM events GROUP BY 1,2 HAVING COUNT(*) > 1` returns no rows.
- No gaps in event numbers for a single unbroken session: `SELECT MAX(seq) = COUNT(*) FROM events WHERE session_id = ?` returns 1.
- A full debug session writes 11 `task_summary` rows (2 practice + 9 measured), 3 `block_instruments` rows and 1 `session` row.

## Caches and reproducibility
- Any change to an LLM prompt string, the option order or the passage formatting changes the cache key. Every cached call then misses, and the frozen task records stop rebuilding byte for byte. Keep prompt text byte-identical when refactoring `agent.py`, `qa.py` or `tasks.py`.
