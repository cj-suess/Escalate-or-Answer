"""Block order and task rotation from the participant number (paper, Design and Procedure).

Design: 3 forms x 3 blocks, one block per form, three tasks per block, one from each
task set. Each set holds three forks (source pairs); a participant meets every fork
exactly once, in one of its two twin versions (recommendation correct or wrong).

Participant n (1, 2, 3, ...):
  order group  g = (n - 1) % 6            block order = ORDERS[g]
  rotation id  w = ((n - 1) // 6) % 2     which twin version pattern the participant gets
  fork of set s in block position b:  forks_s[(b + s) % 3]
  version of that task:               PATTERN[b][s] XOR w   (1 = recommendation correct)
  order of the three tasks inside a block: the set list rotated by (b + g) % 3

Over participants 1..12 (two per order group) this gives, by construction:
  - every fork under every form 4 times, twice in each twin version;
  - every block with at least one correct and one wrong recommendation;
  - every participant with 4 or 5 correct recommendations over the 9 tasks.
`check_balance` verifies those properties; `python -m escalate worksheet` prints them.
"""
import json
from itertools import permutations

ORDERS = list(permutations(("S1", "S2", "S3")))  # order groups 1..6: S1S2S3, S1S3S2, S2S1S3, S2S3S1, S3S1S2, S3S2S1
PATTERN = ((0, 0, 1), (0, 1, 0), (0, 1, 1))      # [block position][set index] -> 1 = correct twin (before XOR with w)
FORM_NAMES = {"S1": "modal stop", "S2": "inline warning", "S3": "provenance-only"}


def participant_number(code):
    """'P07' -> 7, '7' -> 7, 'pilot2' -> 2."""
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    if not digits:
        raise ValueError(f"participant code has no number: {code!r}")
    return int(digits)


def measured_sets(sets):
    """The task sets in a fixed order, each with its sorted list of three forks."""
    keys = sorted(k for k in sets if k != "practice" and not k.startswith("_"))
    out = []
    for k in keys:
        forks = sorted(sets[k].get("forks") or [])
        if len(forks) != 3:
            raise ValueError(f"set {k} has {len(forks)} selected forks; the design needs exactly 3")
        out.append((k, forks))
    if len(out) != 3:
        raise ValueError(f"the design needs 3 task sets, found {len(out)}")
    return out


def plan(n, sets):
    """Blocks for participant n: form, and for each task its set, fork and twin version."""
    g = (n - 1) % 6
    w = ((n - 1) // 6) % 2
    forms = ORDERS[g]
    ms = measured_sets(sets)
    blocks = []
    for b in range(3):
        tasks = []
        for s_i, (sk, forks) in enumerate(ms):
            tasks.append({"set": sk, "pair_id": forks[(b + s_i) % 3], "correct": bool(PATTERN[b][s_i] ^ w)})
        rot = (b + g) % 3
        tasks = tasks[rot:] + tasks[:rot]
        blocks.append({"block_index": b + 1, "form": forms[b], "form_name": FORM_NAMES[forms[b]], "tasks": tasks})
    return {"participant": n, "participant_code": f"P{n:02d}", "order_group": g + 1, "rotation_id": w,
            "block_order": list(forms), "blocks": blocks}


def resolve(p, records):
    """Fill in task ids: the twin of each fork whose recommendation correctness matches the plan."""
    by_pair = {}
    for r in records.values():
        if r.get("pair_id") and r.get("selected"):
            by_pair.setdefault(r["pair_id"], []).append(r)
    for blk in p["blocks"]:
        for t in blk["tasks"]:
            twins = by_pair.get(t["pair_id"], [])
            match = [r for r in twins if bool(r["recommendation_correct"]) == t["correct"]]
            if len(match) != 1:
                raise ValueError(f"fork {t['pair_id']} has no unique twin with recommendation_correct={t['correct']}")
            t["task_id"] = match[0]["task_id"]
            t["recommendation_correctness"] = "correct" if t["correct"] else "wrong"
    p["practice"] = sorted(k for k, r in records.items() if r.get("set") == "practice")
    return p


def check_balance(plans):
    """Verify the design properties over a list of plans (normally participants 1..12)."""
    problems = []
    cell = {}
    for p in plans:
        n_correct = 0
        for blk in p["blocks"]:
            vs = [t["correct"] for t in blk["tasks"]]
            if not (0 < sum(vs) < len(vs)):
                problems.append(f"participant {p['participant']} block {blk['block_index']} has no mix of correct and wrong")
            if len({t["set"] for t in blk["tasks"]}) != len(blk["tasks"]):
                problems.append(f"participant {p['participant']} block {blk['block_index']} repeats a set")
            n_correct += sum(vs)
            for t in blk["tasks"]:
                key = (t["pair_id"], blk["form"], t["correct"])
                cell[key] = cell.get(key, 0) + 1
        forks = [t["pair_id"] for blk in p["blocks"] for t in blk["tasks"]]
        if len(set(forks)) != 9:
            problems.append(f"participant {p['participant']} meets a fork twice")
        if n_correct not in (4, 5):
            problems.append(f"participant {p['participant']} has {n_correct} correct recommendations")
    if len(plans) == 12:
        orders = {}
        for p in plans:
            orders[p["order_group"]] = orders.get(p["order_group"], 0) + 1
        if any(v != 2 for v in orders.values()) or len(orders) != 6:
            problems.append(f"order groups not 2 each: {orders}")
        pairs = {k[0] for k in cell}
        for pid in pairs:
            for form in ("S1", "S2", "S3"):
                for v in (True, False):
                    if cell.get((pid, form, v), 0) != 2:
                        problems.append(f"fork {pid} under {form} {'correct' if v else 'wrong'}: {cell.get((pid, form, v), 0)} (want 2)")
    return problems, cell


def worksheet(sets, records, n_participants=15):
    plans = [resolve(plan(n, sets), records) for n in range(1, n_participants + 1)]
    problems, _ = check_balance(plans[:12])
    return {"participants": plans, "balance_check_over_1_to_12": "ok" if not problems else problems,
            "note": "Three pilot participants run first and are excluded; give them numbers 13 to 15 (or any numbers) and "
                    "start real participants at 1."}


def print_worksheet(ws):
    print(f"{'P':>3} {'grp':>3} {'rot':>3}  blocks (form: tasks)")
    for p in ws["participants"]:
        cells = []
        for blk in p["blocks"]:
            cells.append(f"{blk['form']}: " + " ".join(f"{t['task_id']}({'c' if t['correct'] else 'w'})" for t in blk["tasks"]))
        print(f"{p['participant']:>3} {p['order_group']:>3} {p['rotation_id']:>3}  " + " | ".join(cells))
    print("balance over participants 1 to 12:", ws["balance_check_over_1_to_12"])


def run(n_participants=15):
    from .tasks import TASKS_DIR
    sets = json.loads((TASKS_DIR / "_sets.json").read_text(encoding="utf-8"))
    records = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in TASKS_DIR.glob("*.json") if not p.name.startswith("_")}
    ws = worksheet(sets, records, n_participants)
    from .common import write_json
    write_json(TASKS_DIR / "_worksheet.json", ws)
    print_worksheet(ws)
    print(f"wrote {TASKS_DIR / '_worksheet.json'}")
    return ws
