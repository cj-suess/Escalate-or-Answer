// Shared helpers for the playground pages.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(path, body) {
  const opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const r = await fetch(path, opt);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

// Render the snapshot's light Markdown (headings, pipe tables, code fences, lists) as HTML,
// highlighting the cited passage: a line that contains a highlight gets the substring
// marked; a line that is wholly part of a highlight (e.g. a table row) is shaded.
function renderPage(text, highlights) {
  const norm = (s) => s.replace(/[`*]/g, "").replace(/\s+/g, " ").trim().toLowerCase();
  const hs = highlights.filter(Boolean).map((h) => ({ raw: h, n: norm(h) }));
  const lineHl = (line) => {
    const n = norm(line);
    if (!n) return { cls: "", html: esc(line) };
    let html = esc(line), hit = false;
    for (const h of hs) {
      if (n.includes(h.n)) { html = markAll(html, h.raw); hit = true; }
      else if (n.length > 8 && h.n.includes(n)) return { cls: "hl", html: esc(line) };
    }
    return { cls: hit ? "has-mark" : "", html };
  };
  const out = [], lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const L = lines[i];
    if (L.startsWith("```")) {                       // code block
      const buf = [];
      while (++i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i]);
      out.push(`<pre class="md-code">${buf.map((b) => { const r = lineHl(b); return r.cls === "hl" ? `<span class="hl">${r.html}</span>` : r.html; }).join("\n")}</pre>`);
    } else if (/^\|/.test(L.trim())) {               // pipe table
      const rows = [];
      while (i < lines.length && /^\|/.test(lines[i].trim())) rows.push(lines[i++]);
      i--;
      out.push(`<table class="md-table">${rows.map((r) => {
        const hl = lineHl(r);
        const cells = r.trim().replace(/^\||\|$/g, "").split("|").map((c) => `<td>${markAll(esc(c.trim()), "") }</td>`).join("");
        const marked = hl.cls === "has-mark" ? " hl" : hl.cls ? " " + hl.cls : "";
        return `<tr class="${marked.trim()}">${cells}</tr>`;
      }).join("")}</table>`);
    } else if (/^#{2,6}\s/.test(L)) {                // heading
      out.push(`<div class="md-h">${esc(L.replace(/^#+\s*/, ""))}</div>`);
    } else if (L.trim()) {
      const r = lineHl(L.replace(/^\s*-\s+/, "• "));
      out.push(`<p class="${r.cls}">${r.html}</p>`);
    }
  }
  return out.join("");
}

// Mark every occurrence of `needle` in escaped `hay`, tolerating whitespace differences.
function markAll(hayEscaped, needle) {
  if (!needle) return hayEscaped;
  const pat = esc(needle).replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
  return hayEscaped.replace(new RegExp(pat, "g"), (m) => `<mark>${m}</mark>`);
}
