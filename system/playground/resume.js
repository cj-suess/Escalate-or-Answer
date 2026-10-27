function decideStart(history, { startAt, pilot }) {
  const mine = history.filter((h) => h.pilot === (pilot ? 1 : 0))
    .sort((x, y) => String(x.started_utc).localeCompare(String(y.started_utc)));
  if (!mine.length) return { mode: "new", session: null };
  const latest = mine[mine.length - 1];
  if (startAt === "practice") return { mode: "duplicate", session: latest };
  const open = mine.filter((h) => h.finished_utc == null);
  return open.length ? { mode: "resume", session: open[open.length - 1] } : { mode: "duplicate", session: latest };
}

if (typeof module === "object") module.exports = { decideStart };
