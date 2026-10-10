"""Build frozen task records from tasks/catalog.json (paper, Tasks and Materials).

For every candidate fork pair:
  1. locate each option's highlighted passage (and the rule/secondary passage) in the
     frozen snapshot; a highlight that is not found verbatim is an error;
  2. retrieve for the scripted query and rank the option passages;
  3. run the fork check: retrieval margin <= fork_margin AND the LLM judge says the
     answer depends on an unstated user fact (judge options are grounded against the
     passages); the full evaluation is appended to data/fork_check_log.jsonl;
  4. the option whose passage ranks higher is the assistant's recommendation;
  5. run the blind-vs-informed probe on the pair's deciding fact;
  6. write two task records, one per sheet line (the twin whose key equals the
     recommendation is a correct-recommendation task, the other a wrong one).

Pacing: each trace line carries a fixed delay drawn deterministically from 3-5 s
(hash of task id and line index), so every participant sees identical timing.
"""
import hashlib
import json

import numpy as np

from .common import CHUNKS_FILE, DATA, PAGES_FILE, ROOT, load_config, norm_answer, norm_space, read_jsonl, write_json, write_jsonl
from . import llm
from .agent import fork_check, grounded_options
from .index import Index
from .qa import BLIND_SYSTEM, INFORMED_SYSTEM, _grade

CATALOG = ROOT / "tasks" / "catalog.json"
TASKS_DIR = DATA / "tasks"
FORK_LOG = DATA / "fork_check_log.jsonl"


def _delay_ms(task_id, line_idx, lo=3000, hi=5000):
    h = int(hashlib.sha256(f"{task_id}:{line_idx}".encode()).hexdigest()[:8], 16)
    return lo + h % (hi - lo + 1)


class Snapshot:
    def __init__(self):
        self.pages = {p["path"]: p for p in read_jsonl(PAGES_FILE)}
        self.chunks = read_jsonl(CHUNKS_FILE)

    def locate(self, path, highlight):
        """Return (chunk, page) whose text contains the highlight (whitespace-normalized)."""
        h = norm_space(highlight)
        for c in self.chunks:
            if c["path"] == path and h in norm_space(c["text"]):
                return c, self.pages[path]
        raise ValueError(f"highlight not found on {path}: {highlight!r}")


def _source_payload(chunk, page, highlight, label):
    return {"label": label, "chunk_id": chunk["chunk_id"], "title": page["title"], "path": page["path"],
            "url": page["url"], "updated": page["updated"], "heading": chunk["heading"],
            "highlight": highlight, "page_text": page["text"]}


def _probe(probe, passages):
    blind = llm.chat([{"role": "system", "content": BLIND_SYSTEM},
                      {"role": "user", "content": probe["question"]}], num_predict=40).strip()
    ctx = "\n\n".join(passages)
    informed = llm.chat([{"role": "system", "content": INFORMED_SYSTEM},
                         {"role": "user", "content": f"{ctx}\n\nQuestion: {probe['question']}"}], num_predict=40).strip()
    b_ok, _ = _grade(probe["question"], blind, probe["answer"])
    i_ok, _ = _grade(probe["question"], informed, probe["answer"])
    return {"question": probe["question"], "gold": probe["answer"], "blind": blind, "blind_correct": b_ok,
            "informed": informed, "informed_correct": i_ok, "survives": (not b_ok) and i_ok}


def _trace(task_id, src_a, src_b, rec, extract_line):
    lines = [
        {"kind": "status", "text": "Reading the question and planning steps…"},
        {"kind": "status", "text": "Searching the CS systems documentation…"},
        {"kind": "source", "source": "A", "text": f"Found Source A: {src_a['title']}" + (f" › {src_a['heading']}" if src_a["heading"] else "")},
        {"kind": "source", "source": "B", "text": f"Found Source B: {src_b['title']}" + (f" › {src_b['heading']}" if src_b["heading"] else "")},
        {"kind": "status", "text": extract_line},
        {"kind": "fork", "text": f"Use {rec} (Source A)", "recommendation_text": f"Source A suggests {rec}."},
        {"kind": "decision", "text": f"Decision: {rec}. Filling the answer field."},
    ]
    for i, ln in enumerate(lines):
        ln["index"] = i + 1
        ln["delay_ms"] = _delay_ms(task_id, i + 1)
    return lines


def _matches(authored, grounded):
    """How many authored options the judge's grounded options correspond to (token overlap)."""
    def toks(s):
        return set(norm_answer(s).split())
    n = 0
    for a in authored:
        ta = toks(a)
        for g in grounded:
            tg = toks(g["value"])
            if ta and tg and (len(ta & tg) / min(len(ta), len(tg)) >= 0.5 or norm_answer(a) in norm_answer(g["value"])):
                n += 1
                break
    return n


def _evaluate(query, opts, ix, cfg):
    """Retrieval + fork check for one phrasing of a pair's query."""
    qv = ix._query_vec(query)
    scores = ix.vecs @ qv
    order = list(np.argsort(-scores))
    rank = {ix.ids[i]: r for r, i in enumerate(order)}
    score = {ix.ids[i]: float(scores[i]) for i in order}
    top = [dict(ix.chunks[ix.ids[i]], score=round(float(scores[i]), 4)) for i in order[:cfg["retrieval"]["k"]]]
    margin = round(top[0]["score"] - top[1]["score"], 4)
    # the judge sees the top-k plus the option passages (deduplicated, in rank order)
    seen, hits = set(), []
    for h in top + [dict(o["chunk"], score=round(score[o["chunk"]["chunk_id"]], 4)) for o in opts]:
        if h["chunk_id"] not in seen:
            seen.add(h["chunk_id"])
            hits.append(h)
    hits.sort(key=lambda h: rank[h["chunk_id"]])
    judge = fork_check(query, "Extract the answer to the question from the documentation.", hits)
    grounded = grounded_options(judge, hits) if judge.get("depends_on_user") else []
    judge_yes = bool(judge.get("depends_on_user")) and len({g["value"].lower() for g in grounded}) >= 2
    margin_small = margin <= cfg["agent"]["fork_margin"]
    # an authored option counts as found if the judge's grounded option matches its value,
    # its documented condition, or its highlighted passage
    matched = sum(1 for o in opts if any(_matches([t], grounded) for t in (o["value"], o["condition"], o["highlight"])))
    return {"query": query, "rank": rank, "hits": hits, "margin": margin, "margin_small": margin_small,
            "judge": judge, "judge_yes": judge_yes, "fired": judge_yes and margin_small,
            "matched_options": matched, "fired_on_authored": judge_yes and margin_small and matched >= 2,
            "grounded_options": [{k: g[k] for k in ("value", "chunk_id")} for g in grounded],
            "top_k": [{"chunk_id": h["chunk_id"], "score": h["score"], "title": h["title"]} for h in top],
            "option_ranks": {o["value"]: rank[o["chunk"]["chunk_id"]] + 1 for o in opts}}


def build(selected_only=False):
    cfg = load_config()
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    snap, ix = Snapshot(), Index()
    llm.chat([{"role": "user", "content": "warm-up"}], num_predict=1, use_cache=False)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    log, records, summary = [], [], []
    for pair in cat["pairs"]:
        if selected_only and not pair["selected"]:
            continue
        opts = []
        for o in pair["options"]:
            chunk, page = snap.locate(o["source"], o["highlight"])
            opts.append(dict(o, chunk=chunk, page=page))
        # Evaluate the scripted query, then any alternative neutral phrasings, in order.
        # Every evaluation is logged (it counts toward the reported hit rate); the first
        # phrasing on which the check fires becomes the task's scripted query.
        evals = []
        for query in [pair["query"]] + pair.get("alt_queries", []):
            ev = _evaluate(query, opts, ix, cfg)
            evals.append(ev)
            log.append({"pair_id": pair["pair_id"], "query": query, "selected": pair["selected"],
                        **{k: ev[k] for k in ("top_k", "margin", "margin_small", "judge", "grounded_options",
                                              "judge_yes", "fired", "matched_options", "fired_on_authored",
                                              "option_ranks")}})
            if ev["fired_on_authored"]:
                break
        ev = next((e for e in evals if e["fired_on_authored"]), evals[0])
        query, rank, hits = ev["query"], ev["rank"], ev["hits"]
        margin, margin_small, judge_yes, fired = ev["margin"], ev["margin_small"], ev["judge_yes"], ev["fired_on_authored"]
        # recommendation: option whose passage ranks higher; same passage -> earlier in the text
        def key_fn(o):
            pos = norm_space(o["chunk"]["text"]).find(norm_space(o["highlight"]))
            return (rank[o["chunk"]["chunk_id"]], pos)
        rec_opt, other_opt = sorted(opts, key=key_fn)
        src_a = _source_payload(rec_opt["chunk"], rec_opt["page"], rec_opt["highlight"], "A")
        if other_opt["chunk"]["chunk_id"] != rec_opt["chunk"]["chunk_id"]:
            src_b = _source_payload(other_opt["chunk"], other_opt["page"], other_opt["highlight"], "B")
        else:
            extra = pair.get("rule_source") or pair.get("secondary_source")
            if extra:
                c, p = snap.locate(extra["source"], extra["highlight"])
                src_b = _source_payload(c, p, extra["highlight"], "B")
            else:
                alt = next(h for h in hits if h["chunk_id"] != rec_opt["chunk"]["chunk_id"])
                src_b = _source_payload(alt, snap.pages[alt["path"]], "", "B")
            src_a["highlight_extra"] = other_opt["highlight"]  # both options live in Source A
        probe = _probe(pair["blind_probe"], [f"{s['title']}\n{snap.locate(s['path'], s['highlight'])[0]['text'] if s['highlight'] else ''}"
                                              for s in (src_a, src_b)])
        log[-1].update(recommended=rec_opt["value"], probe=probe, used_for_task=True)
        values = [o["value"] for o in pair["options"]]
        for twin, key in enumerate(values):
            tid = f"{pair['pair_id']}{'ab'[twin]}"
            records.append({
                "task_id": tid, "item_id": tid, "pair_id": pair["pair_id"], "set": pair["set"], "selected": pair["selected"],
                "is_correct": key == rec_opt["value"],
                "recommendation_correctness": "correct" if key == rec_opt["value"] else "wrong",
                "spec_sheet_line": pair["sheet_lines"][key], "question": pair["questions"][key],
                "scripted_query": query, "deciding_fact": pair["deciding_fact"],
                "options": values, "recommended_option": rec_opt["value"], "key": key,
                "recommendation_correct": key == rec_opt["value"],
                "source_a": src_a, "source_b": src_b,
                "trace": _trace(tid, src_a, src_b, rec_opt["value"], "Extracting the answer from the sources…"),
                "fork_line_index": 6,
                "fork_check": {"margin": margin, "margin_small": margin_small, "judge_yes": judge_yes, "fired_on_authored_fork": fired,
                               "matched_options": ev["matched_options"], "query_attempts": len(evals)},
                "contamination_probe": probe,
                "key_logic": pair["key_logic"], "exclusivity": pair["exclusivity"],
            })
        summary.append((pair["pair_id"], pair["selected"], fired, judge_yes, margin, rec_opt["value"], probe["survives"],
                        len(evals), query))
    # practice tasks: no fork, two agreeing sources
    for pr in cat["practice"]:
        srcs = []
        for lab, s in zip("AB", pr["sources"]):
            c, p = snap.locate(s["source"], s["highlight"])
            srcs.append(_source_payload(c, p, s["highlight"], lab))
        trace = _trace(pr["task_id"], srcs[0], srcs[1], pr["answer"], "Extracting the answer from the sources…")
        trace[5] = {"index": 6, "kind": "answer", "text": f"Both sources agree: {pr['answer']}", "delay_ms": trace[5]["delay_ms"]}
        records.append({"task_id": pr["task_id"], "item_id": pr["task_id"], "pair_id": None, "set": "practice",
                        "selected": True, "is_correct": True, "recommendation_correctness": "practice",
                        "spec_sheet_line": pr["sheet_line"], "question": pr["question"],
                        "scripted_query": pr["query"], "options": [pr["answer"]], "recommended_option": pr["answer"],
                        "key": pr["answer"], "recommendation_correct": True, "source_a": srcs[0], "source_b": srcs[1],
                        "trace": trace, "fork_line_index": None})
    for f in TASKS_DIR.glob("*.json"):   # records only; the _-prefixed files are rewritten below
        if not f.name.startswith("_"):
            f.unlink()
    manifest = {}
    for r in records:
        write_json(TASKS_DIR / f"{r['task_id']}.json", r)
        manifest[r["task_id"]] = hashlib.sha256((TASKS_DIR / f"{r['task_id']}.json").read_bytes()).hexdigest()
    # a set is no longer a block: every block takes one task from each set (paper, Design), so a set
    # lists its selected forks (three are needed) and the twin records behind them
    sets = {k: dict(v, tasks=[r["task_id"] for r in records if r["set"] == k and r["selected"]],
                    forks=sorted({r["pair_id"] for r in records if r["set"] == k and r["selected"]}))
            for k, v in cat["sets"].items()}
    write_json(TASKS_DIR / "_sets.json", sets)
    write_json(TASKS_DIR / "_study.json", {"cover_story": cat.get("cover_story", ""),
                                           "set_labels": {k: v["name"] for k, v in cat["sets"].items()}})
    write_json(TASKS_DIR / "_manifest.json", {"records": manifest,
                                              "all_sha256": hashlib.sha256("".join(sorted(manifest.values())).encode()).hexdigest()})
    write_jsonl(FORK_LOG, log)
    try:
        from . import rotation
        ws = rotation.worksheet(sets, {r["task_id"]: r for r in records}, 15)
        write_json(TASKS_DIR / "_worksheet.json", ws)
        print("worksheet: participants 1-15 written; balance over 1-12:", ws["balance_check_over_1_to_12"])
    except ValueError as e:
        print(f"worksheet not written: {e}")
    from . import matching
    matching.build()
    n = len(summary)
    print(f"{'pair':5} {'sel':4} {'fired':6} {'judge':6} {'margin':7} {'blind-filter':12} {'tries':5} recommended | query")
    for pid, sel, fired, jy, m, rec, surv, tries, q in summary:
        print(f"{pid:5} {'yes' if sel else '':4} {str(fired):6} {str(jy):6} {m:<7} {'survives' if surv else 'DROPPED':12} {tries:<5} {rec} | {q}")
    print(f"queries evaluated: {len(log)}; fired on {sum(e['fired'] for e in log)}/{len(log)} queries "
          f"({sum(e['fired_on_authored'] for e in log)} on the authored fork); "
          f"pairs with a firing query: {sum(s[2] for s in summary)}/{n}; blind-filter survivors {sum(s[6] for s in summary)}/{n}; "
          f"{len(records)} task records -> {TASKS_DIR}")


def run():
    build()
