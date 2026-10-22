// Study session (paper, Apparatus / Procedure / Measures).
//
// Flow: participant number in -> the application assigns block order and task rotation
// (GET /api/plan) -> two practice tasks -> three blocks of three tasks, one per form, with
// an instrument screen (raw NASA-TLX, intrusion item, manipulation check) after each block
// -> closing ranking screen -> debrief.
//
// Every interaction is logged with the runbook schema (POST /api/events), one summary row
// per task, one block_instruments row per block and one session row per session.

const Study = (() => {
  let DATA = null;          // {sets, tasks, study}
  let session = null;       // participant, plan, pace, results
  let block = null;         // current block state
  let task = null;          // current task state
  let token = 0;            // cancels an in-flight trace when a block is restarted
  const MIN_DWELL_S = 3;    // a source counts as viewed only after 3 s of summed dwell (paper, Measures)
  const FORM_TEXT = {       // the manipulation-check wording for each form
    S1: "It paused and asked me to choose before it answered.",
    S2: "It warned me that the sources disagreed, but continued with its own choice.",
    S3: "It only cited its sources and gave an answer.",
  };
  const TLX = [
    ["mental", "Mental demand", "How mentally demanding were the tasks?", "Very low", "Very high"],
    ["physical", "Physical demand", "How physically demanding were the tasks?", "Very low", "Very high"],
    ["temporal", "Temporal demand", "How hurried or rushed was the pace of the tasks?", "Very low", "Very high"],
    ["performance", "Performance", "How successful were you in accomplishing what you were asked to do?", "Perfect", "Failure"],
    ["effort", "Effort", "How hard did you have to work to accomplish your level of performance?", "Very low", "Very high"],
    ["frustration", "Frustration", "How insecure, discouraged, irritated, stressed, and annoyed were you?", "Very low", "Very high"],
  ];

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
  const utc = () => new Date().toISOString();
  function show(id) {
    document.querySelectorAll("#tab-study .screen").forEach((s) => s.classList.toggle("hidden", s.id !== id));
  }
  function setProgress(text) { $("progress").textContent = text; }

  function log(type, detail = null, extra = {}) {
    if (!block) return;
    const base = { participant_code: session.pcode, session_id: session.id, block_order_group: session.plan.order_group,
      block_index: block.index, form: block.form, timestamp_utc: utc(), source_open_duration_s: null };
    if (!task) {   // block-level event (block_start, block_end)
      const ev = { ...base, item_id: null, recommendation_correctness: null, event_type: type,
        event_detail: detail == null ? null : String(detail), t_ms: null, ...extra };
      api("/api/events", { events: [ev] }).catch(() => {});
      return ev;
    }
    const ev = { ...base, item_id: task.rec.task_id, recommendation_correctness: task.rec.recommendation_correctness,
      event_type: type, event_detail: detail == null ? null : String(detail), t_ms: Math.round(now() - task.t0), ...extra };
    task.events.push(ev);
    return ev;
  }

  // ---------------------------------------------------------------- source overlay, dwell, focus, scroll
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
      <div class="src-body" id="srcBody">${body}</div>`;
    $("srcOverlay").classList.remove("hidden");
    $("srcClose").onclick = closeSource;
    const m = $("srcOverlay").querySelector("mark, .hl"); if (m) m.scrollIntoView({ block: "center" });
    // the dwell clock runs only while the overlay is open AND the page has focus (planned change 4)
    task.open = { label, since: document.hidden || !document.hasFocus() ? null : now(), scrollT: 0 };
    task.dwellAtOpen = task.dwell[label];   // so source_close can report this open's own duration
    task.opens[label] += 1;
    log("source_open", label);
    $("srcBody").addEventListener("scroll", onScroll, { passive: true });
    onScroll(true);
  }
  function hlInView(body) {
    const m = body.querySelector("mark, .hl");
    if (!m) return null;
    const r = m.getBoundingClientRect(), b = body.getBoundingClientRect();
    return r.bottom > b.top && r.top < b.bottom ? 1 : 0;
  }
  function onScroll(force) {
    if (!task || !task.open) return;
    const body = $("srcBody");
    const t = now();
    if (!force && t - task.open.scrollT < 400) return;   // throttle to one event per 400 ms
    task.open.scrollT = t;
    const max = body.scrollHeight - body.clientHeight;
    const frac = max > 0 ? Math.round(100 * body.scrollTop / max) / 100 : 0;
    log("source_scroll", `${task.open.label} pos=${frac} highlight_visible=${hlInView(body)}`);
  }
  function pauseDwell(reason) {
    if (!task) return;
    if (task.open && task.open.since != null) {
      task.dwell[task.open.label] += (now() - task.open.since) / 1000;
      task.open.since = null;
    }
    if (task.focusLostAt == null) { task.focusLostAt = now(); log("focus_lost", reason); }
  }
  function resumeDwell(reason) {
    if (!task) return;
    if (task.focusLostAt != null) {
      task.focusLost += (now() - task.focusLostAt) / 1000; task.focusLostAt = null;
      log("focus_gained", reason);
    }
    if (task.open && task.open.since == null) task.open.since = now();
  }
  function closeSource() {
    if (!task || !task.open) return;
    if (task.open.since != null) task.dwell[task.open.label] += (now() - task.open.since) / 1000;
    const dur = task.dwell[task.open.label] - (task.dwellAtOpen ?? 0);
    log("source_close", task.open.label, { source_open_duration_s: Math.round(dur * 1000) / 1000 });
    task.open = null;
    $("srcOverlay").classList.add("hidden");
  }
  document.addEventListener("visibilitychange", () => document.hidden ? pauseDwell("tab_hidden") : resumeDwell("tab_visible"));
  window.addEventListener("blur", () => pauseDwell("window_blur"));
  window.addEventListener("focus", () => resumeDwell("window_focus"));

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
    await sleep(ms * session.pace);
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
        task.sourceOpenAtFork = task.open ? task.open.label : "none";
        log("fork_onset", form);
        log("source_open_at_fork", task.sourceOpenAtFork);
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
        if (session.autosend) setTimeout(() => $("accept").click(), 50);   // debug/regression: accept as filled
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
      if (session.autosend) setTimeout(() => $("forkModal").querySelector(".fm-opt").click(), 50);
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
    if (task.focusLostAt != null) resumeDwell("accept");
    $("accept").disabled = true; $("reject").disabled = true; $("picker").classList.add("hidden");
    log("accept", task.value);
    const t = now();
    const rec = task.rec;
    // A source counts as viewed only when its summed dwell reaches MIN_DWELL_S;
    // raw opens and dwell are still logged so the threshold can be re-analyzed.
    const viewedA = task.dwell.A >= MIN_DWELL_S, viewedB = task.dwell.B >= MIN_DWELL_S;
    const opened = (viewedA ? 1 : 0) + (viewedB ? 1 : 0);
    const pattern = viewedA && viewedB ? "both" : viewedA ? "recommended only" : viewedB ? "non-recommended only" : "neither";
    const summary = {
      participant_code: session.pcode, session_id: session.id, block_order_group: session.plan.order_group,
      block_index: block.index, form: block.form, item_id: rec.task_id, recommendation_correctness: rec.recommendation_correctness,
      final_value: task.value, accuracy: task.value === rec.key ? 1 : 0, followed: task.value === rec.recommended_option ? 1 : 0,
      verified: opened > 0 ? 1 : 0, source_pattern: pattern,
      dwell_a_s: +task.dwell.A.toFixed(2), dwell_b_s: +task.dwell.B.toFixed(2), opens_a: task.opens.A, opens_b: task.opens.B,
      decision_time_s: task.forkT ? +((t - task.forkT) / 1000).toFixed(2) : null,
      total_time_s: +((t - task.t0) / 1000).toFixed(2),
      source_open_at_fork: task.sourceOpenAtFork, focus_lost_s: +task.focusLost.toFixed(2),
    };
    session.results.push(summary);
    try { await api("/api/events", { events: task.events, summary }); } catch (e) { console.warn("log failed", e); }
    $("taskMsg").textContent = "Saved. Next task in a moment…";
    await sleep(1500 * Math.max(session.pace, 0.2));
    nextTask();
  }

  // ---------------------------------------------------------------- blocks and tasks
  function sheetLabel(rec) {
    if (rec.set === "practice") return "";
    const name = (DATA.study.set_labels || {})[rec.set] || DATA.sets[rec.set]?.name || `Set ${rec.set}`;
    return `<span class="sheet-tag">${esc(name)}</span> `;
  }
  function startBlock(b) {
    // b: {block_index, form, tasks:[{task_id,...}]} or the practice pseudo-block
    token++;
    block = { index: b.block_index, form: b.form, order: b.tasks.map((t) => t.task_id), i: -1, practice: b.form === "practice" };
    task = null;
    log("block_start", block.practice ? "practice" : `${block.form} tasks ${block.order.join(",")}`);
    const recs = block.order.map((id) => DATA.tasks[id]);
    $("sheetTitle").textContent = block.practice ? "Practice: two warm-up tasks." : DATA.study.cover_story || "";
    // one line per task, labelled with its context, in set order (not task order)
    const lines = recs.slice().sort((x, y) => String(x.set).localeCompare(String(y.set)))
      .map((r) => `<li>${sheetLabel(r)}${esc(r.spec_sheet_line)}</li>`);
    $("sheetLines").innerHTML = lines.join("");
    show("screen-task");
    nextTask();
  }

  function nextTask() {
    block.i += 1;
    if (block.i >= block.order.length) return endBlock();
    const rec = DATA.tasks[block.order[block.i]];
    task = { rec, t0: now(), events: [], opens: { A: 0, B: 0 }, dwell: { A: 0, B: 0 }, open: null, value: null, forkT: null,
      sourceOpenAtFork: null, focusLost: 0, focusLostAt: null };
    const label = block.practice ? "Practice" : `Block ${block.index} of 3`;
    setProgress(`${session.pcode} · ${label} · task ${block.i + 1} of ${block.order.length}`);
    $("taskNo").textContent = `${block.practice ? "Practice task" : "Task"} ${block.i + 1} of ${block.order.length}`;
    $("taskQ").textContent = rec.question; $("taskQ").classList.remove("muted");
    $("answer").innerHTML = "&nbsp;"; $("answer").classList.add("empty");
    $("accept").disabled = true; $("reject").disabled = true;
    $("picker").classList.add("hidden"); $("taskMsg").textContent = "";
    $("qtext").textContent = rec.scripted_query;
    $("traceBox").innerHTML = ""; $("forkModal").classList.add("hidden"); $("srcOverlay").classList.add("hidden");
    $("send").disabled = false;
    log("task_start");
    if (session.autosend) $("send").click();
  }

  function endBlock() {
    task = null;
    log("block_end", block.practice ? "practice" : block.form);
    if (block.practice) {
      $("breakTitle").textContent = "Practice complete";
      $("breakText").textContent = "The three blocks start now. Each block has its own spec sheet; read it before the first task.";
      $("breakNext").onclick = () => runBlock(1);
      show("screen-break");
      if (session.autosend) $("breakNext").click();
      return;
    }
    showInstruments();
  }

  function runBlock(i) {
    if (i > 3) return showClosing();
    session.blockNo = i;
    startBlock(session.plan.blocks[i - 1]);
  }

  // ---------------------------------------------------------------- instruments after each block
  function scaleHtml(name, n, lo, hi, from = 0) {
    const boxes = [];
    for (let v = from; v < from + n; v++) boxes.push(`<label class="tick"><input type="radio" name="${name}" value="${v}"><span>${v}</span></label>`);
    return `<div class="scale"><span class="anchor">${esc(lo)}</span><div class="ticks">${boxes.join("")}</div><span class="anchor">${esc(hi)}</span></div>`;
  }
  function showInstruments() {
    setProgress(`${session.pcode} · Block ${block.index} of 3 · questionnaire`);
    $("tlxBox").innerHTML = TLX.map(([k, title, q, lo, hi]) =>
      `<div class="item"><div class="item-q"><b>${title}.</b> ${esc(q)}</div>${scaleHtml("tlx_" + k, 21, lo, hi)}</div>`).join("");
    $("intrusionBox").innerHTML = scaleHtml("intrusion", 7, "Not at all intrusive", "Extremely intrusive", 1);
    const order = shuffle(["S1", "S2", "S3"], `${session.pcode}:manip:${block.index}`);
    $("manipBox").innerHTML = order.map((f) => `<label class="manip-opt"><input type="radio" name="manip" value="${f}"> ${esc(FORM_TEXT[f])}</label>`).join("");
    $("instrumentMsg").textContent = "";
    $("instrumentForm").reset();
    show("screen-instrument");
    if (session.autosend) autoFill($("instrumentForm"));
  }
  function autoFill(form) {   // debug/regression aid: pick the first option of every scale
    for (const name of new Set([...form.querySelectorAll("input[type=radio]")].map((r) => r.name))) {
      const rs = form.querySelectorAll(`input[name="${name}"]`); rs[Math.floor(rs.length / 2)].checked = true;
    }
    form.requestSubmit();
  }
  async function submitInstruments(e) {
    e.preventDefault();
    const f = new FormData($("instrumentForm"));
    const val = (k) => f.get(k) == null ? null : +f.get(k);
    if (TLX.some(([k]) => val("tlx_" + k) == null) || val("intrusion") == null || !f.get("manip")) {
      $("instrumentMsg").textContent = "Please answer every item."; return;
    }
    const row = { participant_code: session.pcode, session_id: session.id, block_index: block.index, form: block.form,
      tlx_mental: val("tlx_mental"), tlx_physical: val("tlx_physical"), tlx_temporal: val("tlx_temporal"),
      tlx_performance: val("tlx_performance"), tlx_effort: val("tlx_effort"), tlx_frustration: val("tlx_frustration"),
      intrusion: val("intrusion"), manip_response: f.get("manip"), manip_correct: f.get("manip") === block.form ? 1 : 0,
      timestamp_utc: utc() };
    session.instruments.push(row);
    $("instrumentSubmit").disabled = true;
    try { await api("/api/instruments", row); } catch (err) { console.warn("instrument log failed", err); }
    $("instrumentSubmit").disabled = false;
    const next = block.index + 1;
    if (next <= 3) {
      $("breakTitle").textContent = `Block ${block.index} complete`;
      $("breakText").textContent = `Block ${next} has a new spec sheet. Read it, then start the first task when you are ready.`;
      $("breakNext").onclick = () => runBlock(next);
      show("screen-break");
      if (session.autosend) $("breakNext").click();
    } else {
      showClosing();
    }
  }

  // ---------------------------------------------------------------- closing screen
  function showClosing() {
    setProgress(`${session.pcode} · closing questions`);
    const order = shuffle(["S1", "S2", "S3"], `${session.pcode}:rank`);
    const opts = order.map((f) => `<option value="${f}">${esc(FORM_TEXT[f])}</option>`).join("");
    $("rankBox").innerHTML = [1, 2, 3].map((r) => `<label>${r}${r === 1 ? "st" : r === 2 ? "nd" : "rd"}
      <select class="rank" data-r="${r}"><option value="">—</option>${opts}</select></label>`).join("");
    $("rankReason").value = ""; $("closingMsg").textContent = "";
    show("screen-closing");
    if (session.autosend) {
      document.querySelectorAll("select.rank").forEach((s, i) => s.value = order[i]);
      $("rankReason").value = "autofilled by debug mode"; $("closingSubmit").click();
    }
  }
  async function submitClosing() {
    const ranking = [...document.querySelectorAll("select.rank")].map((s) => s.value);
    if (ranking.some((v) => !v) || new Set(ranking).size !== 3) { $("closingMsg").textContent = "Please give each version a different rank."; return; }
    const reason = $("rankReason").value.trim();
    if (!reason) { $("closingMsg").textContent = "Please write a short reason."; return; }
    session.ranking = ranking; session.reason = reason;
    $("closingSubmit").disabled = true;
    try {
      await api("/api/session", { participant_code: session.pcode, session_id: session.id, ranking, ranking_reason: reason, finished_utc: utc() });
    } catch (err) { console.warn("session log failed", err); }
    $("closingSubmit").disabled = false;
    block = null; task = null;
    setProgress(`${session.pcode} · done`);
    $("resultsBox").innerHTML = "";
    $("showResults").classList.remove("hidden");
    show("screen-done");
  }

  // ---------------------------------------------------------------- experimenter results
  function resultsHtml() {
    const R = session.results, scored = R.filter((r) => r.recommendation_correctness !== "practice");
    const rate = (xs) => xs.length ? Math.round(100 * xs.reduce((x, y) => x + y, 0) / xs.length) + "%" : "–";
    const wrong = scored.filter((r) => r.recommendation_correctness === "wrong"), right = scored.filter((r) => r.recommendation_correctness === "correct");
    const forms = ["S1", "S2", "S3"];
    return `<h3>${esc(session.pcode)} · order group ${session.plan.order_group} (${session.plan.block_order.join(" ")}) · rotation ${session.plan.rotation_id}${session.pilot ? " · PILOT" : ""}</h3>
      <div class="stats">
        <div class="stat"><b>${rate(scored.map((r) => r.verified))}</b>verified</div>
        <div class="stat"><b>${rate(wrong.map((r) => 1 - r.followed))}</b>override when wrong</div>
        <div class="stat"><b>${rate(right.map((r) => r.followed))}</b>follow when right</div>
        <div class="stat"><b>${rate(scored.map((r) => r.accuracy))}</b>accuracy</div>
        ${forms.map((f) => `<div class="stat"><b>${rate(scored.filter((r) => r.form === f).map((r) => r.verified))}</b>verified ${f}</div>`).join("")}
      </div>
      <table class="qa"><thead><tr><th>block</th><th>form</th><th>task</th><th>rec.</th><th>final</th><th>acc</th><th>followed</th><th>verified</th><th>pattern</th>
        <th>dwell A (s)</th><th>dwell B (s)</th><th>opens A/B</th><th>open at fork</th><th>decision (s)</th><th>total (s)</th><th>focus lost (s)</th></tr></thead><tbody>
      ${R.map((r) => `<tr><td>${r.block_index}</td><td>${esc(r.form)}</td><td>${esc(r.item_id)}</td><td>${esc(r.recommendation_correctness)}</td><td><code>${esc(r.final_value)}</code></td>
        <td>${r.accuracy}</td><td>${r.followed}</td><td>${r.verified}</td><td>${esc(r.source_pattern)}</td><td>${r.dwell_a_s}</td><td>${r.dwell_b_s}</td>
        <td>${r.opens_a}/${r.opens_b}</td><td>${esc(r.source_open_at_fork ?? "")}</td><td>${r.decision_time_s ?? "–"}</td><td>${r.total_time_s}</td><td>${r.focus_lost_s ?? ""}</td></tr>`).join("")}
      </tbody></table>
      <h4>Instruments</h4>
      <table class="qa"><thead><tr><th>block</th><th>form</th><th>mental</th><th>physical</th><th>temporal</th><th>performance</th><th>effort</th><th>frustration</th><th>intrusion</th><th>manipulation check</th></tr></thead><tbody>
      ${session.instruments.map((r) => `<tr><td>${r.block_index}</td><td>${r.form}</td><td>${r.tlx_mental}</td><td>${r.tlx_physical}</td><td>${r.tlx_temporal}</td><td>${r.tlx_performance}</td><td>${r.tlx_effort}</td><td>${r.tlx_frustration}</td><td>${r.intrusion}</td><td>${r.manip_response} (${r.manip_correct ? "correct" : "wrong"})</td></tr>`).join("")}
      </tbody></table>
      <p>Ranking: ${(session.ranking || []).map((f) => esc(f)).join(" > ")} · “${esc(session.reason || "")}”</p>
      <p class="muted small">Written to data/sessions/events.sqlite (tables events, task_summary, block_instruments, session).</p>`;
  }

  // ---------------------------------------------------------------- session start
  async function previewAssignment() {
    const n = +$("pnum").value;
    if (!n) { $("assignPreview").textContent = ""; return; }
    try {
      const p = await api(`/api/plan?participant=${n}`);
      $("assignPreview").textContent = `Assigned: order group ${p.order_group} (${p.block_order.join(" → ")}), rotation ${p.rotation_id}.`;
    } catch (e) { $("assignPreview").textContent = `Cannot assign: ${e.message}`; }
  }
  async function startSession() {
    const n = +$("pnum").value;
    if (!n || n < 1) { $("entryMsg").textContent = "Enter the participant number."; return; }
    $("startSession").disabled = true; $("entryMsg").textContent = "";
    let plan;
    try { plan = await api(`/api/plan?participant=${n}`); }
    catch (e) { $("entryMsg").textContent = `Cannot build the plan: ${e.message}`; $("startSession").disabled = false; return; }
    const pcode = `P${String(n).padStart(2, "0")}`;
    session = { n, pcode, pilot: $("pilot").checked, id: `${pcode}-${Date.now()}`, plan, pace: +$("pace").value,
      results: [], instruments: [], autosend: session?.autosend || false };
    const startAt = $("startAt").value;
    try {
      await api("/api/session", { participant_code: pcode, session_id: session.id, participant_number: n, pilot: session.pilot ? 1 : 0,
        order_group: plan.order_group, rotation_id: plan.rotation_id, block_order: plan.block_order,
        standing: $("standing").value || null, gender: $("gender").value || null, course_of_study: $("course").value.trim() || null,
        prior_falcon_use: $("priorFalcon").value || null, started_utc: utc() });
    } catch (e) { console.warn("session row failed", e); }
    $("startSession").disabled = false;
    if (startAt === "practice") startBlock({ block_index: 0, form: "practice", tasks: plan.practice.map((id) => ({ task_id: id })) });
    else runBlock(+startAt);
  }

  // ---------------------------------------------------------------- wiring
  async function init() {
    DATA = await api("/api/tasks");
    DATA.study = DATA.study || {};
    $("pnum").oninput = previewAssignment;
    $("startSession").onclick = startSession;
    $("send").onclick = () => { $("send").disabled = true; log("send"); playTrace(token); };
    $("accept").onclick = accept;
    $("reject").onclick = () => { log("reject"); showPicker(); };
    $("traceBox").addEventListener("click", (e) => { const c = e.target.closest(".src-chip"); if (c) openSource(c.dataset.src); });
    $("instrumentForm").onsubmit = submitInstruments;
    $("closingSubmit").onclick = submitClosing;
    $("showResults").onclick = () => { $("resultsBox").innerHTML = resultsHtml(); $("showResults").classList.add("hidden"); };
    $("newSession").onclick = () => { session = null; block = null; task = null; setProgress(""); $("pnum").value = ""; $("assignPreview").textContent = ""; show("screen-entry"); };
    // deep link for testing: #p=7&pace=0.1&start=2&autostart=1&autosend=1&pilot=1
    const h = new URLSearchParams(location.hash.slice(1));
    if (h.get("p")) { $("pnum").value = h.get("p"); previewAssignment(); }
    if (h.get("pace")) $("pace").value = h.get("pace");
    if (h.get("start")) $("startAt").value = h.get("start");
    if (h.get("pilot")) $("pilot").checked = true;
    if (h.get("autostart")) { session = { autosend: !!h.get("autosend") }; startSession(); }
    if (h.get("opensrc")) {   // debugging aid: open a source as soon as its chip exists
      const t = setInterval(() => { if (document.querySelector(`.src-chip[data-src="${h.get("opensrc")}"]`)) { clearInterval(t); openSource(h.get("opensrc")); } }, 100);
    }
  }
  return { init, openSource, closeSource, state: () => ({ session, block, task }) };
})();

Study.init();
