"""Matching statistics for the selected tasks (planned change 5).

For every measured task: words on the Source A and Source B pages, words in the
highlighted passages, and the token overlap between the scripted query and the
two highlighted passages. Per-set means follow, so the pilot report can show the
three sets are comparable. Writes data/tasks/_matching.json.
"""
import json

from .common import norm_answer, write_json
from .tasks import TASKS_DIR

OUT = TASKS_DIR / "_matching.json"


def _toks(s):
    return set(norm_answer(s or "").split())


def _words(s):
    return len((s or "").split())


def stats_for(rec):
    a, b = rec["source_a"], rec["source_b"]
    hl = " ".join(x for x in (a.get("highlight"), a.get("highlight_extra"), b.get("highlight")) if x)
    q = _toks(rec["scripted_query"])
    p = _toks(hl)
    overlap = len(q & p) / len(q) if q else 0.0
    return {
        "task_id": rec["task_id"], "set": rec["set"], "pair_id": rec["pair_id"],
        "recommendation_correctness": rec["recommendation_correctness"],
        "trace_lines": len(rec["trace"]), "fork_line": rec["fork_line_index"],
        "source_a_page_words": _words(a.get("page_text")), "source_b_page_words": _words(b.get("page_text")),
        "same_page": a["path"] == b["path"],
        "highlight_words": _words(hl),
        "query_words": _words(rec["scripted_query"]),
        "query_passage_overlap": round(overlap, 3),
        "sheet_line_words": _words(rec["spec_sheet_line"]),
        "question_words": _words(rec["question"]),
        "exclusivity": rec.get("exclusivity"),
    }


def build():
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(TASKS_DIR.glob("*.json")) if not p.name.startswith("_")]
    rows = [stats_for(r) for r in recs if r.get("selected") and r["set"] != "practice"]
    keys = ("source_a_page_words", "source_b_page_words", "highlight_words", "query_words", "query_passage_overlap",
            "sheet_line_words", "question_words")
    per_set = {}
    for s in sorted({r["set"] for r in rows}):
        rs = [r for r in rows if r["set"] == s]
        per_set[s] = {"n_tasks": len(rs), **{k: round(sum(r[k] for r in rs) / len(rs), 3) for k in keys},
                      "exclusivity": sorted({r["exclusivity"] for r in rs})}
    out = {"tasks": rows, "per_set": per_set,
           "note": "overlap = share of normalized query tokens that also occur in the highlighted passages"}
    write_json(OUT, out)
    print(f"{'set':4} {'n':>2} {'pageA':>6} {'pageB':>6} {'hl':>4} {'q':>3} {'overlap':>7} {'sheet':>5} {'quest':>5}")
    for s, v in per_set.items():
        print(f"{s:4} {v['n_tasks']:>2} {v['source_a_page_words']:>6.0f} {v['source_b_page_words']:>6.0f} {v['highlight_words']:>4.0f} "
              f"{v['query_words']:>3.0f} {v['query_passage_overlap']:>7.2f} {v['sheet_line_words']:>5.1f} {v['question_words']:>5.1f}")
    print(f"wrote {OUT}")
    return out


def run():
    build()
