// Study task view (proposal v4, Section 3.2): spec sheet + task card on the left,
// scripted query, timed retrieval trace and per-source overlays on the right.
// Logs every event (runbook schema) and per-task metrics, including dwell per source.

const Study = (() => {
  let DATA = null;          // {sets, tasks}
  let block = null;         // current block state
  let task = null;          // current task state
  let token = 0;            // cancels an in-flight trace when a new block starts

  // ---------------------------------------------------------------- utilities
  function seeded(str) {    // deterministic PRNG (mulberry32) seeded from a string
    let h = 1779033703 ^ str.length;
    for (let i = 0; i < str.length; i++) { h = Math.imul(h ^ str.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
    return () => { h += 0x6D2B79F5; let t = h; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  }
  function shuffle(arr, seed) {
    const a = arr.slice(), rnd = seeded(seed);
    for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
    return a;
  }
  const now = () => performance.now();

  function log(type, detail = null, extra = {}) {
    if (!block) return;
    if (!task) {   // block-level event (block_start, block_end)
      const ev = { participant_code: block.pcode, session_id: block.session_id, block_order_group: block.orderGroup,
        block_index: block.index, form: block.form, item_id: null, recommendation_correctness: null, event_type: type,
        event_detail: detail == null ? null : String(detail), t_ms: null, timestamp_utc: new Date().toISOString(),
        source_open_duration_s: null, ...extra };
      api("/api/events", { events: [ev] }).catch(() => {});
      return ev;
    }
    const ev = {
      participant_code: block.pcode, session_id: block.session_id, block_order_group: block.orderGroup,
      block_index: block.index, form: block.form, item_id: task.rec.task_id,
      recommendation_correctness: task.rec.fork_line_index ? (task.rec.recommendation_correct ? "correct" : "wrong") : "practice",
      event_type: type, event_detail: detail == null ? null : String(detail),
      t_ms: Math.round(now() - task.t0), timestamp_utc: new Date().toISOString(), source_open_duration_s: null, ...extra,
    };
    task.events.push(ev);
    return ev;
  }

  // ---------------------------------------------------------------- source overlay + dwell
  function openSource(label) {
    if (!task) return;
    if (task.open) closeSource();
    const s = label === "A" ? task.rec.source_a : task.rec.source_b;
    const body = renderPage(s.page_text, [s.highlight, s.highlight_extra]);
    $("srcOverlay").innerHTML = `
      <div class="src-head">
        <div><span class="src-tag">Source ${label}</span> <b>${esc(s.title)}</b>${s.heading ? ` › ${esc(s.heading)}` : ""}
          <div class="muted small">Updated ${esc(s.updated || "unknown")} · ${esc(s.path)}</div></div>
        <button id="srcClose">Close</button>
      </div>
      <div class="src-body">${body}</div>`;
    $("srcOverlay").classList.remove("hidden");
    $("srcClose").onclick = closeSource;
    const m = $("srcOverlay").querySelector("mark, .hl"); if (m) m.scrollIntoView({ block: "center" });
    task.open = { label, since: now() };
    task.opens[label] += 1;
    log("source_open", label);
  }
  function closeSource() {
    if (!task || !task.open) return;
    const dur = (now() - task.open.since) / 1000;
    task.dwell[task.open.label] += dur;
    log("source_close", task.open.label, { source_open_duration_s: Math.round(dur * 1000) / 1000 });
    task.open = null;
    $("srcOverlay").classList.add("hidden");
  }

  // ---------------------------------------------------------------- trace rendering
  function chipFor(label) {
    return `<button class="src-chip" data-src="${label}">Source ${label}</button>`;
  }
  function addLine(html, cls = "") {
    const d = document.createElement("div");
    d.className = "tline " + cls;
    d.innerHTML = html;
    $("traceBox").appendChild(d);
    $("traceBox").scrollTop = $("traceBox").scrollHeight;
    return d;
  }
  async function wait(ms, my) {
    const typing = addLine('<span class="typing"><i></i><i></i><i></i></span>', "typing-line");
    await sleep(ms * block.pace);
    typing.remove();
    return my === token;
  }

  async function playTrace(my) {
    const rec = task.rec, form = block.form;
    for (const ln of rec.trace) {
      if (!(await wait(ln.delay_ms, my))) return;
      log("trace_line_onset", ln.index);
      if (ln.kind === "status" || ln.kind === "answer") {
        addLine(`<span class="n">${ln.index}.</span> ${esc(ln.text)}`);
      } else if (ln.kind === "source") {
        const rest = esc(ln.text).replace(`Found Source ${ln.source}:`, "").trim();
        addLine(`<span class="n">${ln.index}.</span> Found ${chipFor(ln.source)} ${rest}`);
      } else if (ln.kind === "fork") {
        task.forkT = now();
        log("fork_onset", form);
        if (form === "S1") {
          addLine(`<span class="n">${ln.index}.</span> <i class="muted">Paused: the sources give different options. Waiting for you.</i>`);
          task.value = await modalPick(ln);
          if (my !== token) return;
        } else if (form === "S2") {
          const d = addLine(`<span class="n">${ln.index}.</span> ${esc(ln.text)} <span class="warn-glyph" title="warning">!</span>`);
          d.insertAdjacentHTML("beforeend", `<div class="warn-box">${esc(ln.recommendation_text)}</div>`);
          task.value = rec.recommended_option;
        } else {
          addLine(`<span class="n">${ln.index}.</span> ${esc(ln.text)}`);
          task.value = rec.recommended_option;
        }
      } else if (ln.kind === "decision") {
        const v = task.value ?? rec.recommended_option;
        addLine(`<span class="n">${ln.index}.</span> Decision: <code>${esc(v)}</code>. Filling the answer field.`);
        setAnswer(v, "autofill");
        addLine('<i class="muted">Done. Accept or Reject the answer.</i>');
        $("accept").disabled = false; $("reject").disabled = false;
      }
    }
  }

  function modalPick(ln) {
    return new Promise((resolve) => {
      const opts = task.rec.options;
      $("forkModal").innerHTML = `<div class="fm-box">
        <div class="fm-title">Which option should this task use?</div>
        <p>${esc(ln.recommendation_text)}</p>
        ${opts.map((o, i) => `<button class="fm-opt" data-i="${i}"><code>${esc(o)}</code></button>`).join("")}
        <div class="muted small">Your pick fills the answer field; Reject undoes it. The sources above stay clickable.</div></div>`;
      // anchor the blocking layer just below the last trace line so lines 1-6 (and the chips) stay visible
      const last = $("traceBox").lastElementChild;
      const top = last ? last.getBoundingClientRect().bottom - $("traceBox").parentElement.getBoundingClientRect().top + 8 : 200;
      $("forkModal").style.top = `${Math.round(top)}px`;
      $("forkModal").classList.remove("hidden");
      $("forkModal").onclick = (e) => {
        const b = e.target.closest(".fm-opt"); if (!b) return;
        const v = opts[+b.dataset.i];
        log("modal_pick", v);
        $("forkModal").classList.add("hidden");
        resolve(v);
      };
    });
  }

  // ---------------------------------------------------------------- answer field, accept/reject
  function setAnswer(v, how) {
    task.value = v;
    $("answer").textContent = v;
    $("answer").classList.remove("empty");
    log(how, v);
  }
  function showPicker() {
    const opts = task.rec.options;
    $("picker").innerHTML = `<div class="muted small">Choose the answer:</div>` +
      opts.map((o, i) => `<button class="pick-opt" data-i="${i}"><code>${esc(o)}</code></button>`).join("");
    $("picker").classList.remove("hidden");
    $("picker").onclick = (e) => {
      const b = e.target.closest(".pick-opt"); if (!b) return;
      const v = opts[+b.dataset.i];
      log("picker_choice", v);
      setAnswer(v, "refill");
      $("picker").classList.add("hidden");
    };
  }

  async function accept() {
    closeSource();
    $("accept").disabled = true; $("reject").disabled = true; $("picker").classList.add("hidden");
    log("accept", task.value);
    const t = now();
    const rec = task.rec;
    const opened = task.opens.A + task.opens.B;
    const pattern = task.opens.A && task.opens.B ? "both" : task.opens.A ? "recommended only" : task.opens.B ? "non-recommended only" : "neither";
    const summary = {
      participant_code: block.pcode, session_id: block.session_id, block_order_group: block.orderGroup,
      block_index: block.index, form: block.form, item_id: rec.task_id, recommendation_correctness: rec.fork_line_index ? (rec.recommendation_correct ? "correct" : "wrong") : "practice",
      final_value: task.value, accuracy: task.value === rec.key ? 1 : 0, followed: task.value === rec.recommended_option ? 1 : 0,
      verified: opened > 0 ? 1 : 0, source_pattern: pattern,
      dwell_a_s: +task.dwell.A.toFixed(2), dwell_b_s: +task.dwell.B.toFixed(2), opens_a: task.opens.A, opens_b: task.opens.B,
      decision_time_s: task.forkT ? +((t - task.forkT) / 1000).toFixed(2) : null,
      total_time_s: +((t - task.t0) / 1000).toFixed(2),
    };
    block.results.push(summary);
    try { await api("/api/events", { events: task.events, summary }); } catch (e) { console.warn("log failed", e); }
    $("taskMsg").textContent = "Saved. Next task in a moment…";
    await sleep(1500);
    nextTask();
  }

  // ---------------------------------------------------------------- block + task flow
  function startBlock() {
    token++;
    const setKey = $("setPick").value, set = DATA.sets[setKey];
    block = {
      pcode: $("pcode").value.trim() || "P00", form: $("form").value, setKey, pace: +$("pace").value,
      index: (block && block.pcode === $("pcode").value.trim() ? block.index + 1 : 1),
      session_id: (block && block.session_id) || `${$("pcode").value.trim()}-${Date.now()}`,
      order: shuffle(set.tasks, `${$("pcode").value.trim()}:${setKey}`), results: [], i: -1,
      orderGroup: +$("orderGroup").value,
    };
    task = null;
    log("block_start", `set ${setKey}`);
    $("sheetTitle").textContent = set.assignment;
    const lines = set.tasks.map((id) => DATA.tasks[id].spec_sheet_line).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
    $("sheetLines").innerHTML = lines.map((l) => `<li>${esc(l)}</li>`).join("");
    $("blockSummary").innerHTML = "";
    nextTask();
  }

  function nextTask() {
    block.i += 1;
    if (block.i >= block.order.length) return showSummary();
    const rec = DATA.tasks[block.order[block.i]];
    task = { rec, t0: now(), events: [], opens: { A: 0, B: 0 }, dwell: { A: 0, B: 0 }, open: null, value: null, forkT: null };
    $("progress").textContent = `${block.form} · set ${block.setKey} · task ${block.i + 1} of ${block.order.length} · block ${block.index}`;
    $("taskNo").textContent = `Task ${block.i + 1} of ${block.order.length}`;
    $("taskQ").textContent = rec.question; $("taskQ").classList.remove("muted");
    $("answer").innerHTML = "&nbsp;"; $("answer").classList.add("empty");
    $("accept").disabled = true; $("reject").disabled = true;
    $("picker").classList.add("hidden"); $("taskMsg").textContent = "";
    $("qtext").textContent = rec.scripted_query;
    $("traceBox").innerHTML = ""; $("forkModal").classList.add("hidden"); $("srcOverlay").classList.add("hidden");
    $("send").disabled = false;
    log("task_start");
  }

  function showSummary() {
    task = null;
    log("block_end", `set ${block.setKey}`);
    $("progress").textContent = `block ${block.index} done`;
    // No correctness feedback on the participant's screen (runbook Section 6); results sit behind an experimenter button.
    $("blockSummary").innerHTML = `<div class="card done-card"><b>Block complete.</b> Please tell the experimenter.
      <button id="showResults" class="exp-btn">Experimenter: show block results</button><div id="resultsBox"></div></div>`;
    $("showResults").onclick = () => { $("resultsBox").innerHTML = resultsHtml(); $("showResults").remove(); };
  }

  function resultsHtml() {
    const R = block.results, scored = R.filter((r) => r.recommendation_correctness !== "practice");
    const rate = (xs) => xs.length ? Math.round(100 * xs.reduce((x, y) => x + y, 0) / xs.length) + "%" : "–";
    const wrong = scored.filter((r) => r.recommendation_correctness === "wrong"), right = scored.filter((r) => r.recommendation_correctness === "correct");
    return `<h3>Block ${block.index} · ${block.form} · set ${block.setKey} · order group ${block.orderGroup}</h3>
      <div class="stats">
        <div class="stat"><b>${rate(scored.map((r) => r.verified))}</b>verified</div>
        <div class="stat"><b>${rate(wrong.map((r) => 1 - r.followed))}</b>override when wrong</div>
        <div class="stat"><b>${rate(right.map((r) => r.followed))}</b>follow when right</div>
        <div class="stat"><b>${rate(scored.map((r) => r.accuracy))}</b>accuracy</div>
      </div>
      <table class="qa"><thead><tr><th>task</th><th>rec.</th><th>final</th><th>acc</th><th>followed</th><th>verified</th><th>pattern</th>
        <th>dwell A (s)</th><th>dwell B (s)</th><th>opens A/B</th><th>decision (s)</th><th>total (s)</th></tr></thead><tbody>
      ${R.map((r) => `<tr><td>${esc(r.item_id)}</td><td>${esc(r.recommendation_correctness)}</td><td><code>${esc(r.final_value)}</code></td>
        <td>${r.accuracy}</td><td>${r.followed}</td><td>${r.verified}</td><td>${esc(r.source_pattern)}</td><td>${r.dwell_a_s}</td><td>${r.dwell_b_s}</td>
        <td>${r.opens_a}/${r.opens_b}</td><td>${r.decision_time_s ?? "–"}</td><td>${r.total_time_s}</td></tr>`).join("")}
      </tbody></table><p class="muted small">Written to data/sessions/events.sqlite.</p>`;
  }

  // ---------------------------------------------------------------- wiring
  async function init() {
    DATA = await api("/api/tasks");
    $("setPick").innerHTML = Object.entries(DATA.sets).map(([k, s]) => `<option value="${k}">${k === "practice" ? "Practice" : "Set " + k}: ${esc(s.name)} (${s.tasks.length})</option>`).join("");
    $("startBlock").onclick = startBlock;
    const TIE = { S1: "1", S2: "2", S3: "3" };   // proposal v4: each form has its own fixed task set
    const tieNote = () => {
      const v = $("setPick").value, tied = TIE[$("form").value];
      $("progress").textContent = v !== "practice" && v !== tied ? `⚠ set ${v} is not tied to ${$("form").value} (testing only)` : "";
    };
    $("form").onchange = () => { $("setPick").value = TIE[$("form").value]; tieNote(); };
    $("setPick").onchange = tieNote;
    $("send").onclick = () => { $("send").disabled = true; task.sendT = now(); log("send"); playTrace(token); };
    $("accept").onclick = accept;
    $("reject").onclick = () => { log("reject"); showPicker(); };
    $("traceBox").addEventListener("click", (e) => { const c = e.target.closest(".src-chip"); if (c) openSource(c.dataset.src); });
    const h = new URLSearchParams(location.hash.slice(1));   // deep link: #form=S2&set=1&pace=0.1&autostart=1
    if (h.get("form")) $("form").value = h.get("form");
    if (h.get("set")) $("setPick").value = h.get("set");
    if (h.get("pace")) $("pace").value = h.get("pace");
    if (h.get("autostart")) { startBlock(); if (h.get("autosend")) $("send").click(); }
    if (h.get("opensrc")) {   // debugging aid: open a source as soon as its chip exists
      const t = setInterval(() => { if (document.querySelector(`.src-chip[data-src="${h.get("opensrc")}"]`)) { clearInterval(t); openSource(h.get("opensrc")); } }, 100);
    }
  }
  return { init, openSource, closeSource };
})();

Study.init();
