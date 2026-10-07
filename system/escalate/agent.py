"""The drafting agent: plan -> per-step retrieval -> fork check -> answer or escalate.

This is the minimal agentic RAG loop described in the proposal (Figure 2). It
never sees the participant's situation line: only the short question. Each run
produces a JSON record in the proposal's schema, which the playground renders
in the three escalation forms and which can be frozen into data/records/.

Fork check: an LLM judge decides whether the retrieved passages give different
correct answers for this step depending on a fact about the user that the
question does not state. The retrieval-score margin between the top two
chunks is recorded; if `fork_requires_small_margin` is true in config.json the
check fires only when that margin is at most `fork_margin` (the proposal's
"margin AND judge" rule).
"""
import datetime
import hashlib
import re

from .common import RECORDS, load_config, norm_answer, write_json
from . import llm
from .index import Index

PLAN_SCHEMA = {
    "type": "object",
    "properties": {"steps": {"type": "array", "items": {
        "type": "object",
        "properties": {"goal": {"type": "string"}, "query": {"type": "string"}},
        "required": ["goal", "query"]}}},
    "required": ["steps"],
}

FORK_SCHEMA = {
    "type": "object",
    "properties": {
        "depends_on_user": {"type": "boolean"},
        "attribute": {"type": "string"},
        "options": {"type": "array", "items": {
            "type": "object",
            "properties": {"value": {"type": "string"}, "chunk_id": {"type": "string"},
                           "applies_when": {"type": "string"}},
            "required": ["value", "chunk_id", "applies_when"]}},
    },
    "required": ["depends_on_user", "attribute", "options"],
}

STEP_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}, "cites": {"type": "array", "items": {"type": "string"}}},
    "required": ["text", "cites"],
}

SYSTEM = ("You are an assistant for a university computer-science department's IT documentation "
          "(accounts, the Falcon HPC cluster, storage, software, remote access, printing). "
          "Use only the documentation passages you are given.")


def _passages(hits):
    return "\n\n".join(f"[{h['chunk_id']}] {h['title']} > {h['heading'] or h['title']} (updated {h['updated']})\n{h['text']}"
                       for h in hits)


def plan(question, max_steps):
    out = llm.chat([{"role": "system", "content": SYSTEM},
                    {"role": "user", "content":
                        f"User request: \"{question}\"\n\nBreak the request into 2 to {max_steps} concrete steps the "
                        "user must take, in order. For each step give a short goal and a search query for the "
                        "documentation."}],
                   schema=PLAN_SCHEMA, num_predict=300)
    return out.get("steps", [])[:max_steps]


def fork_check(question, goal, hits):
    return llm.chat([{"role": "system", "content": SYSTEM},
                     {"role": "user", "content":
                         f"User request: \"{question}\"\nCurrent step: {goal}\n\nPassages:\n{_passages(hits)}\n\n"
                         "The request does not tell you everything about the user. Do these passages give DIFFERENT "
                         "correct answers for this step depending on a fact about the user that the request does not "
                         "state (for example their role, where they are working, how much GPU memory they need, or "
                         "what kind of data they have)? Answer true only if there are at least two concrete, "
                         "different options for this step and which one is right depends on such an unstated user "
                         "fact. If true: 'attribute' is the fact about the user (e.g. 'GPU memory the model needs'); "
                         "each option's 'value' is the concrete setting or action the user would choose for this step "
                         "(e.g. a partition name, host, path, command or procedure), never a property of the user; "
                         "'chunk_id' is the passage that supports it; 'applies_when' states the user condition. "
                         "If false, return an empty options list."}],
                    schema=FORK_SCHEMA, num_predict=400)


def answer_step(question, goal, hits, use_option=None):
    extra = f"\nUse this option for the step: {use_option}." if use_option else ""
    return llm.chat([{"role": "system", "content": SYSTEM},
                     {"role": "user", "content":
                         f"User request: \"{question}\"\nCurrent step: {goal}\n\nPassages:\n{_passages(hits)}\n\n"
                         "Write ONE short instruction (at most 25 words) telling the user what to do for this step, "
                         f"based only on the passages, and list the passage ids you used.{extra}"}],
                    schema=STEP_SCHEMA, num_predict=200)


_CHUNK_RE = re.compile(r"p\d{3}-c\d{2}")


def grounded_options(fork, hits):
    """Keep only options whose value is actually supported by the cited passage.

    The judge's chunk id is normalized (models sometimes echo the passage header),
    and the option's value must appear in that passage, verbatim or with at least
    60% of its tokens. This drops hallucinated options before they can trigger an
    escalation.
    """
    by_id = {h["chunk_id"]: h for h in hits}
    kept = []
    for o in fork.get("options", []):
        m = _CHUNK_RE.search(o.get("chunk_id", ""))
        cid = m.group(0) if m else None
        if cid not in by_id:
            continue
        text, val = norm_answer(by_id[cid]["text"]), norm_answer(o.get("value", ""))
        toks = val.split()
        if not toks:
            continue
        support = val in text or sum(t in text.split() for t in toks) / len(toks) >= 0.6
        if support:
            kept.append(dict(o, chunk_id=cid))
    return kept


def run(question, situation=None):
    cfg = load_config()
    acfg, k = cfg["agent"], cfg["retrieval"]["k"]
    ix = Index()
    steps, escalation_step = [], None
    for i, s in enumerate(plan(question, acfg["max_steps"])):
        hits = ix.search(s["query"], k)
        margin = round(hits[0]["score"] - hits[1]["score"], 4) if len(hits) > 1 else 1.0
        fork = fork_check(question, s["goal"], hits) if escalation_step is None else None
        fired, default, options = False, None, []
        if fork and fork.get("depends_on_user"):
            options = grounded_options(fork, hits)
            values = {o["value"].strip().lower() for o in options}
            margin_ok = margin <= acfg["fork_margin"] or not acfg.get("fork_requires_small_margin", False)
            fired = len(values) >= 2 and margin_ok
        if fired:
            rank = {h["chunk_id"]: r for r, h in enumerate(hits)}
            default = min(options, key=lambda o: rank.get(o["chunk_id"], 99))
            escalation_step = i
        ans = answer_step(question, s["goal"], hits, use_option=default["value"] if default else None)
        valid = {h["chunk_id"] for h in hits}
        steps.append({
            "goal": s["goal"], "query": s["query"],
            "retrieved": [{k2: h[k2] for k2 in ("chunk_id", "score", "title", "heading", "url", "updated")} for h in hits],
            "margin": margin,
            "fork_check": fork,
            "grounded_options": options,
            "escalation": ({"attribute": fork["attribute"], "options": options, "default": default}
                           if fired else None),
            "text": ans.get("text", "").strip(),
            "cites": [c for c in ans.get("cites", []) if c in valid] or [hits[0]["chunk_id"]],
        })
    esc = steps[escalation_step]["escalation"] if escalation_step is not None else None
    rid = hashlib.sha256(f"{question}\n{situation or ''}".encode("utf-8")).hexdigest()[:10]
    return {
        "record_id": rid,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "question": question,
        "situation": situation,
        "flagged": esc is not None,
        "escalation_step": escalation_step,
        "steps": steps,
        "card": ({"scored_field": esc["attribute"],
                  "options": [o["value"] for o in esc["options"]],
                  "prefill": esc["default"]["value"],
                  "key": None} if esc else None),
        "provenance": {"llm": cfg["models"]["llm"], "llm_digest": llm.digest(cfg["models"]["llm"]),
                       "embed": cfg["models"]["embed"], "embed_digest": llm.digest(cfg["models"]["embed"]),
                       "llm_options": cfg["llm_options"], "ollama_version": llm.version()},
    }


def freeze(record):
    path = RECORDS / f"{record['record_id']}.json"
    write_json(path, record)
    return path
