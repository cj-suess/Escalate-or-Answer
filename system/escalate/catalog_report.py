"""Generate the task-catalog writeup (Markdown) from the catalog, the frozen task records
and the fork-check log, so every number in the document comes from the data."""
import json
from collections import defaultdict

from .common import DATA, ROOT, read_jsonl
from .tasks import CATALOG, FORK_LOG, TASKS_DIR


def _short(s, n=60):
    return s if len(s) <= n else s[: n - 1] + "…"


def build(out_path):
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    recs = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in TASKS_DIR.glob("*.json") if not p.name.startswith("_")}
    log = read_jsonl(FORK_LOG)
    by_pair = defaultdict(list)
    for e in log:
        by_pair[e["pair_id"]].append(e)
    sel = [p for p in cat["pairs"] if p["selected"]]
    L = []
    w = L.append

    n_q = len(log)
    n_fired = sum(e["fired"] for e in log)
    n_auth = sum(e["fired_on_authored"] for e in log)
    pairs_ok = [p["pair_id"] for p in cat["pairs"] if any(e["fired_on_authored"] for e in by_pair[p["pair_id"]])]
    survivors = [p["pair_id"] for p in cat["pairs"] if any(e.get("probe", {}).get("survives") for e in by_pair[p["pair_id"]])]

    w("## Counts at a glance\n")
    w("| What | Count |\n|---|---|")
    w("| Measured tasks per participant | 12 (3 blocks × 4) |")
    w("| Practice tasks per participant | 2 (no fork, not scored) |")
    w("| Task records seeded for the study | 14 (12 measured + 2 practice) |")
    w("| Source pairs (forks) behind the 12 tasks | 6 (2 per set, each used twice) |")
    w("| Distinct assistant traces | 6 + 2 practice (the two twins of a pair share one trace; only the sheet line and question differ) |")
    w("| Spec sheets | 3 (one per block) + 1 practice sheet |")
    w("| Recommendation correct / wrong | 6 / 6 (2 / 2 in every block) |")
    w(f"| Candidate forks authored | {len(cat['pairs'])} |")
    w(f"| Candidate queries evaluated by the fork check | {n_q} |")
    w(f"| Queries on which the check fired / fired on the authored fork | {n_fired} / {n_auth} |")
    w(f"| Candidate forks with a query that fired on the authored fork | {len(pairs_ok)} of {len(cat['pairs'])} ({', '.join(pairs_ok)}) |")
    w(f"| Candidate forks surviving the blind-vs-informed filter | {len(survivors)} of {len(cat['pairs'])} |")
    w("| Trials at N = 18 | 216 (36 per Form × Correctness cell) |")
    w("")

    w("## The 12 measured tasks\n")
    for sk, s in cat["sets"].items():
        w(f"### Set {sk}: {s['name']}\n")
        w(f"Spec-sheet heading: *{s['assignment']}*\n")
        w("| Task | Sheet line (deciding fact) | Question on the task card | Recommended → key | Rec. |")
        w("|---|---|---|---|---|")
        for p in [p for p in sel if p["set"] == sk]:
            for suffix in "ab":
                r = recs[p["pair_id"] + suffix]
                w(f"| {r['task_id']} | {r['spec_sheet_line']} | {r['question']} | `{_short(r['recommended_option'], 40)}` → `{_short(r['key'], 40)}` | "
                  f"{'correct' if r['recommendation_correct'] else '**wrong**'} |")
        w("")
        for p in [p for p in sel if p["set"] == sk]:
            r = recs[p["pair_id"] + "a"]
            ev = next(e for e in by_pair[p["pair_id"]] if e.get("used_for_task"))
            w(f"**{p['pair_id']}.** Scripted query: *\"{r['scripted_query']}\"* (fork check fired on attempt {r['fork_check']['query_attempts']}, "
              f"margin {ev['margin']}, judge attribute \"{ev['judge'].get('attribute')}\").  ")
            w(f"Source A: **{r['source_a']['title']}**{(' › ' + r['source_a']['heading']) if r['source_a']['heading'] else ''} "
              f"(`{r['source_a']['path']}`), highlighted: \"{_short(r['source_a']['highlight'], 110)}\".  ")
            w(f"Source B: **{r['source_b']['title']}**{(' › ' + r['source_b']['heading']) if r['source_b']['heading'] else ''} "
              f"(`{r['source_b']['path']}`){', highlighted: \"' + _short(r['source_b']['highlight'], 110) + '\"' if r['source_b']['highlight'] else ''}.  ")
            w(f"Options in the picker: {' / '.join('`' + o + '`' for o in r['options'])}.  ")
            w(f"Why the key is unambiguous ({p['exclusivity']}): {p['key_logic']}  ")
            pr = r["contamination_probe"]
            w(f"Blind probe: \"{pr['question']}\" → blind *{pr['blind']}* (wrong), informed *{pr['informed']}* (right).\n")

    w("## Practice tasks\n")
    w("| Task | Sheet line | Question | Answer | Sources (agree) |\n|---|---|---|---|---|")
    for pr in cat["practice"]:
        r = recs[pr["task_id"]]
        w(f"| {r['task_id']} | {r['spec_sheet_line']} | {r['question']} | `{r['key']}` | {r['source_a']['title']}; {r['source_b']['title']} |")
    w("")

    w("## Candidate pool: every fork tried, and its fate\n")
    w("| Fork | Set | Deciding fact | Fork check (authored fork) | Blind filter | Exclusivity | Status |")
    w("|---|---|---|---|---|---|---|")
    for p in cat["pairs"]:
        evs = by_pair[p["pair_id"]]
        ok = any(e["fired_on_authored"] for e in evs)
        fired_any = any(e["fired"] for e in evs)
        surv = any(e.get("probe", {}).get("survives") for e in evs)
        check = (f"fired ({sum(e['fired_on_authored'] for e in evs)}/{len(evs)} queries)" if ok else
                 f"fired on a different fork ({len(evs)} queries)" if fired_any else f"did not fire ({len(evs)} queries)")
        status = "**selected**" if p["selected"] else ("eligible backup" if ok and surv else "excluded")
        w(f"| {p['pair_id']} | {p['set']} | {p['deciding_fact']} | {check} | {'survives' if surv else 'dropped'} | {p['exclusivity']} | {status} |")
    w("")

    w("## Every fork-check evaluation\n")
    w("| Fork | Query | Margin | Judge attribute | Grounded options | Fired | On authored fork |")
    w("|---|---|---|---|---|---|---|")
    for e in log:
        w(f"| {e['pair_id']} | {e['query']} | {e['margin']} | {e['judge'].get('attribute', '')} | "
          f"{'; '.join(_short(g['value'], 28) for g in e['grounded_options']) or '—'} | {'yes' if e['fired'] else 'no'} | {'yes' if e['fired_on_authored'] else 'no'} |")
    w("")
    out_path.write_text("\n".join(L), encoding="utf-8")
    return out_path
