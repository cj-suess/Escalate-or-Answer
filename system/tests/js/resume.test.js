const test = require("node:test");
const assert = require("node:assert/strict");
const { decideStart } = require("../../playground/resume.js");

const entry = (id, started, finished = null, pilot = 0) =>
  ({ session_id: id, pilot, started_utc: started, finished_utc: finished, max_seq: 0, tasks_done: [], blocks_done: [] });

test("no history is new", () => {
  assert.deepEqual(decideStart([], { startAt: "practice", pilot: false }), { mode: "new", session: null });
  assert.deepEqual(decideStart([], { startAt: "2", pilot: false }), { mode: "new", session: null });
});

test("practice start with history is duplicate", () => {
  const a = entry("P07-1", "2026-10-27T10:00:00Z");
  assert.deepEqual(decideStart([a], { startAt: "practice", pilot: false }), { mode: "duplicate", session: a });
});

test("block start resumes the latest unfinished session", () => {
  const a = entry("P07-1", "2026-10-27T10:00:00Z");
  const b = entry("P07-2", "2026-10-27T11:00:00Z");
  const c = entry("P07-3", "2026-10-27T12:00:00Z", "2026-10-27T12:30:00Z");
  assert.deepEqual(decideStart([b, a, c], { startAt: "2", pilot: false }), { mode: "resume", session: b });
});

test("block start with only finished sessions is duplicate", () => {
  const a = entry("P07-1", "2026-10-27T10:00:00Z", "2026-10-27T10:40:00Z");
  const b = entry("P07-2", "2026-10-27T11:00:00Z", "2026-10-27T11:40:00Z");
  assert.deepEqual(decideStart([a, b], { startAt: "3", pilot: false }), { mode: "duplicate", session: b });
});

test("pilot sessions do not count for a real participant", () => {
  const p = entry("P07-1", "2026-10-27T10:00:00Z", null, 1);
  assert.deepEqual(decideStart([p], { startAt: "practice", pilot: false }), { mode: "new", session: null });
  assert.deepEqual(decideStart([p], { startAt: "2", pilot: false }), { mode: "new", session: null });
});

test("real sessions do not count for a pilot", () => {
  const r = entry("P07-1", "2026-10-27T10:00:00Z");
  assert.deepEqual(decideStart([r], { startAt: "2", pilot: true }), { mode: "new", session: null });
  const p = entry("P07-2", "2026-10-27T11:00:00Z", null, 1);
  assert.deepEqual(decideStart([r, p], { startAt: "2", pilot: true }), { mode: "resume", session: p });
});
