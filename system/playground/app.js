// Tabs, status line, the live-agent inspector and the corpus/QA browser.

document.querySelectorAll(".tabs button").forEach((b) => b.onclick = () => {
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.id === "tab-" + b.dataset.tab));
});

async function loadStatus() {
  try {
    const s = await api("/api/status");
    $("status").textContent = `${s.ollama ? "Ollama " + s.ollama_version : "Ollama offline (frozen tasks and cached runs still work)"} · ${s.models.llm} · ${s.chunks} chunks · ${s.qa_kept}/${s.qa} QA kept`;
    $("status").classList.toggle("bad", !s.ollama);
    $("stats").innerHTML = [
      ["pages", s.snapshot?.pages], ["words", s.snapshot?.words], ["chunks", s.chunks],
      ["QA candidates", s.qa], ["QA kept", s.qa_kept], ["snapshot", (s.snapshot?.crawled_at || "").slice(0, 10)],
    ].map(([k, v]) => `<div class="stat"><b>${esc(v ?? "-")}</b>${esc(k)}</div>`).join("");
  } catch (e) { $("status").textContent = "server error: " + e.message; $("status").classList.add("bad"); }
}

// ------------------------------------------------------------------ agent (live)
let lastRecord = null;
$("arun").onclick = async () => {
  $("arun").disabled = true; $("freeze").disabled = true; $("freezeMsg").textContent = "";
  $("atrace").innerHTML = '<p class="muted">Running the agent locally…</p>';
  try {
    lastRecord = await api("/api/agent", { question: $("aq").value });
    renderAgentTrace(lastRecord);
    $("freeze").disabled = false;
  } catch (e) { $("atrace").innerHTML = `<p class="muted">Error: ${esc(e.message)}</p>`; }
  finally { $("arun").disabled = false; }
};
$("freeze").onclick = async () => {
  try { const r = await api("/api/freeze", { record: lastRecord }); $("freezeMsg").textContent = "saved " + r.saved; }
  catch (e) { $("freezeMsg").textContent = "error: " + e.message; }
};
function renderAgentTrace(rec) {
  $("atrace").innerHTML = `<p><b>${esc(rec.question)}</b> · ${rec.flagged ? `<span class="fired">fork at step ${rec.escalation_step + 1}</span>` : '<span class="notfired">no fork</span>'}
    · ${esc(rec.provenance.llm)} @ ${esc((rec.provenance.llm_digest || "").slice(0, 12))}</p>` +
    rec.steps.map((s, i) => `<div class="tstep"><b>${i + 1}. ${esc(s.goal)}</b> <span class="muted">query: ${esc(s.query)} · margin ${s.margin}</span>
      <table><tr><th>chunk</th><th>score</th><th>page › heading</th></tr>${s.retrieved.map((h) =>
        `<tr><td>${esc(h.chunk_id)}</td><td>${h.score}</td><td>${esc(h.title)} › ${esc(h.heading || "")}</td></tr>`).join("")}</table>
      <div>fork check: ${s.fork_check ? (s.escalation ? '<span class="fired">fired</span>' : '<span class="notfired">did not fire</span>') : '<span class="notfired">skipped</span>'}</div>
      ${s.fork_check ? `<pre>${esc(JSON.stringify(s.fork_check, null, 1))}</pre>` : ""}
      <div>step text: ${esc(s.text)}</div></div>`).join("");
}

// ------------------------------------------------------------------ corpus + QA
let QA = [];
async function loadQA() { QA = await api("/api/qa"); renderQA(); }
function renderQA() {
  const f = $("qaFilter").value;
  const rows = QA.filter((r) => f === "all" || r.label === f);
  $("qaCount").textContent = `${rows.length} of ${QA.length}`;
  $("qaBody").innerHTML = rows.map((r) => `<tr><td>${esc(r.question)}</td><td>${esc(r.answer)}</td>
    <td class="${r.blind_correct ? "fired" : ""}">${esc(r.blind_answer)}</td><td>${esc(r.informed_answer)}</td><td>${esc(r.chunk_id)}</td></tr>`).join("");
}
$("qaFilter").onchange = renderQA;
$("searchBtn").onclick = async () => {
  $("hits").innerHTML = '<div class="muted">searching…</div>';
  try {
    const hits = await api("/api/search", { query: $("searchQ").value, k: 5 });
    $("hits").innerHTML = hits.map((h) => `<div class="hit"><span class="score">${h.score}</span><b>${esc(h.title)}</b> › ${esc(h.heading || "")}
      <span class="muted">${esc(h.chunk_id)}</span><div class="muted">${esc(h.text.slice(0, 260))}…</div></div>`).join("");
  } catch (e) { $("hits").innerHTML = `<div class="muted">error: ${esc(e.message)}</div>`; }
};
$("searchQ").addEventListener("keydown", (e) => { if (e.key === "Enter") $("searchBtn").click(); });

loadStatus(); loadQA();
