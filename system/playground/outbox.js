function memoryStore() {
  let state = { queue: [], rejected: [] };
  return {
    load: () => ({ queue: state.queue.slice(), rejected: state.rejected.slice() }),
    save: (s) => { state = { queue: s.queue.slice(), rejected: s.rejected.slice() }; },
  };
}

function localStore(key, storage) {
  if (storage === undefined) {
    try { storage = globalThis.localStorage; } catch { storage = null; }
  }
  const mem = memoryStore();
  return {
    load() {
      try {
        const raw = storage.getItem(key);
        if (raw) return JSON.parse(raw);
      } catch { }
      return mem.load();
    },
    save(s) {
      mem.save(s);
      try { storage.setItem(key, JSON.stringify(s)); } catch { }
    },
  };
}

function createOutbox({ send, store, retryDelaysMs = [1000, 2000, 5000, 10000], onChange = () => {} }) {
  const saved = store.load();
  const queue = saved.queue || [], rejected = saved.rejected || [];
  let failures = 0, timer = null, counter = 0, chain = Promise.resolve();

  const status = () => ({ pending: queue.length, rejected: rejected.length });
  const changed = () => { store.save({ queue, rejected }); onChange(status()); };

  function schedule() {
    if (timer) return;
    const delay = retryDelaysMs[Math.min(failures - 1, retryDelaysMs.length - 1)];
    timer = setTimeout(() => { timer = null; flush(); }, delay);
  }

  async function pass() {
    while (queue.length) {
      const entry = queue[0];
      try {
        await send(entry.path, entry.body);
      } catch (err) {
        if (err && err.status >= 400 && err.status < 500) {
          queue.shift();
          rejected.push({ ...entry, error: err.message });
          changed();
          continue;
        }
        failures += 1;
        schedule();
        return;
      }
      failures = 0;
      queue.shift();
      changed();
    }
  }

  function flush() {
    const p = chain.then(pass);
    chain = p.catch(() => {});
    return p;
  }

  async function enqueue(path, body) {
    const id = `${Date.now()}-${++counter}`;
    queue.push({ id, path, body });
    changed();
    await flush();
    return !queue.some((e) => e.id === id) && !rejected.some((e) => e.id === id);
  }

  function stop() {
    clearTimeout(timer);
    timer = null;
  }

  return { enqueue, flush, status, stop, rejected: () => rejected.slice() };
}

function saveStateText({ pending, rejected }) {
  const parts = [];
  if (pending) parts.push(`${pending} write(s) not saved yet, retrying. Keep this window open.`);
  if (rejected) parts.push(`${rejected} write(s) rejected by the server; see the console.`);
  return parts.join(" ");
}

if (typeof module === "object") module.exports = { createOutbox, localStore, memoryStore, saveStateText };
