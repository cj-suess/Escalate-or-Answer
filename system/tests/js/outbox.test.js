const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createOutbox, localStore, memoryStore } = require("../../playground/outbox.js");

const httpError = (status) => Object.assign(new Error(`HTTP ${status}`), { status });
const netError = () => new Error("Failed to fetch");
const until = async (cond, ms = 2000) => {
  const t = Date.now();
  while (!cond()) {
    if (Date.now() - t > ms) throw new Error("timed out");
    await new Promise((r) => setTimeout(r, 2));
  }
};

function fakeServer(fail = () => null) {
  const sent = [];
  let calls = 0;
  const send = async (p, body) => {
    calls += 1;
    const err = fail(body, calls);
    if (err) throw err;
    sent.push(body);
    return { ok: 1 };
  };
  return { send, sent };
}

test("enqueue resolves true once the server confirms", async () => {
  const srv = fakeServer();
  const ob = createOutbox({ send: srv.send, store: memoryStore(), retryDelaysMs: [5] });
  assert.equal(await ob.enqueue("/api/events", { n: 1 }), true);
  assert.deepEqual(srv.sent, [{ n: 1 }]);
  assert.deepEqual(ob.status(), { pending: 0, rejected: 0 });
});

test("retries in order after the server recovers", async () => {
  const srv = fakeServer((body, calls) => (calls <= 3 ? netError() : null));
  const ob = createOutbox({ send: srv.send, store: memoryStore(), retryDelaysMs: [5] });
  ob.enqueue("/api/events", { n: "a" });
  ob.enqueue("/api/events", { n: "b" });
  ob.enqueue("/api/events", { n: "c" });
  await until(() => ob.status().pending === 0);
  assert.deepEqual(srv.sent, [{ n: "a" }, { n: "b" }, { n: "c" }]);
});

test("enqueue resolves false while the server is down", async () => {
  const srv = fakeServer(() => netError());
  const ob = createOutbox({ send: srv.send, store: memoryStore(), retryDelaysMs: [1000] });
  assert.equal(await ob.enqueue("/api/events", { n: 1 }), false);
  assert.deepEqual(ob.status(), { pending: 1, rejected: 0 });
  ob.stop();
});

test("a 4xx response moves the entry to rejected and the queue continues", async () => {
  const srv = fakeServer((body) => (body.n === "b" ? httpError(400) : null));
  const ob = createOutbox({ send: srv.send, store: memoryStore(), retryDelaysMs: [5] });
  ob.enqueue("/api/events", { n: "a" });
  ob.enqueue("/api/events", { n: "b" });
  await ob.enqueue("/api/events", { n: "c" });
  await until(() => ob.status().pending === 0);
  assert.deepEqual(ob.status(), { pending: 0, rejected: 1 });
  assert.deepEqual(srv.sent, [{ n: "a" }, { n: "c" }]);
});

test("entries left in the store are sent by a new outbox", async () => {
  const store = memoryStore();
  store.save({ queue: [{ id: "1", path: "/api/events", body: { n: 1 } }, { id: "2", path: "/api/session", body: { n: 2 } }], rejected: [] });
  const srv = fakeServer();
  const ob = createOutbox({ send: srv.send, store, retryDelaysMs: [5] });
  assert.deepEqual(ob.status(), { pending: 2, rejected: 0 });
  await ob.flush();
  assert.deepEqual(srv.sent, [{ n: 1 }, { n: 2 }]);
  assert.deepEqual(store.load().queue, []);
});

test("localStore persists across outboxes", async () => {
  const data = new Map();
  const storage = { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)) };
  const down = createOutbox({ send: async () => { throw netError(); }, store: localStore("eoa-outbox", storage), retryDelaysMs: [1000] });
  await down.enqueue("/api/events", { n: 1 });
  down.stop();
  const srv = fakeServer();
  const up = createOutbox({ send: srv.send, store: localStore("eoa-outbox", storage), retryDelaysMs: [5] });
  await up.flush();
  assert.deepEqual(srv.sent, [{ n: 1 }]);
});

test("localStore falls back to memory when storage throws", async () => {
  const storage = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("quota"); } };
  const srv = fakeServer();
  const ob = createOutbox({ send: srv.send, store: localStore("eoa-outbox", storage), retryDelaysMs: [5] });
  assert.equal(await ob.enqueue("/api/events", { n: 1 }), true);
  assert.equal(await createOutbox({ send: srv.send, store: localStore("eoa-outbox", undefined) }).enqueue("/x", {}), true);
});

test("onChange reports pending and rejected counts", async () => {
  const seen = [];
  const srv = fakeServer((body, calls) => (calls === 1 ? netError() : null));
  const ob = createOutbox({ send: srv.send, store: memoryStore(), retryDelaysMs: [5], onChange: (s) => seen.push(s) });
  ob.enqueue("/api/events", { n: 1 });
  await until(() => ob.status().pending === 0);
  assert.ok(seen.some((s) => s.pending === 1));
  assert.deepEqual(seen.at(-1), { pending: 0, rejected: 0 });
});

test("api attaches the HTTP status to errors", async () => {
  const src = fs.readFileSync(path.join(__dirname, "../../playground/common.js"), "utf8");
  const responses = {
    "/bad": { ok: false, status: 400, statusText: "Bad Request", json: async () => ({ error: "unknown keys: x" }) },
    "/html": { ok: false, status: 502, statusText: "Bad Gateway", json: async () => { throw new SyntaxError("not json"); } },
  };
  const ctx = { fetch: async (p) => responses[p], document: {} };
  vm.runInNewContext(`${src}\nthis.api = api;`, ctx);
  await assert.rejects(ctx.api("/bad", { x: 1 }), (e) => e.status === 400 && /unknown keys/.test(e.message));
  await assert.rejects(ctx.api("/html"), (e) => e.status === 502 && e.message === "Bad Gateway");
});
