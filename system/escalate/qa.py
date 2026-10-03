"""Steps 3-4: FictionalQA-style question generation and blind-vs-informed filtering.

Adapted from Kirchenbauer et al. (ICLR 2026). Stage A generates short,
unambiguous question/answer pairs per chunk, each tied to a verbatim evidence
span (span-constrained, checked deterministically). Stage B asks the same model
each question twice: blind (no context) and informed (the chunk in context),
and grades both answers against the gold answer (lexical match first, an LLM
judge only when the lexical check is inconclusive). Items answered correctly
blind are discarded; items failing blind and passing informed are kept. The
filter reduces, but does not remove, the pretraining confound for this model.
"""
import re

from .common import (CHUNKS_FILE, QA_ANNOTATED, QA_CANDIDATES, QA_KEPT, load_config,
                     norm_answer, norm_space, read_jsonl, write_jsonl)
from . import llm

GEN_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["question", "answer", "evidence"],
            },
        }
    },
    "required": ["items"],
}

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"correct": {"type": "boolean"}},
    "required": ["correct"],
}

GEN_SYSTEM = (
    "You write questions that test whether a reader has seen a specific page of a university "
    "computer-science department's internal IT documentation. Rules: each question must be answerable "
    "from the passage alone and have exactly one short answer (a name, command, path, number, limit, "
    "host, flag or short phrase, at most 12 words). The question must make sense without the passage "
    "(name the system or page topic; never say 'the passage' or 'this page'). 'evidence' must be copied "
    "verbatim from the passage and must contain the answer. Prefer department-specific facts "
    "(host names, partition names, paths, limits, procedures) over general computing knowledge."
)

# Blind answers must commit to a best guess; otherwise a model that abstains
# ("unknown") would let generic, guessable questions pass the filter.
BLIND_SYSTEM = (
    "Answer the question with only the short answer (at most 12 words), no explanation. "
    "You must always give your best guess; never say you do not know."
)
INFORMED_SYSTEM = (
    "Answer the question using the passage. Reply with only the short answer (at most 12 words), "
    "no explanation."
)


def _passage(chunk):
    return f"Page: {chunk['title']} ({chunk['path']})\nSection: {chunk['heading'] or '-'}\n\n{chunk['text']}"


def generate(per_chunk, max_chunks=None):
    chunks = read_jsonl(CHUNKS_FILE)
    if max_chunks:
        chunks = chunks[:max_chunks]
    candidates, rejected = [], 0
    for i, ch in enumerate(chunks):
        out = llm.chat(
            [{"role": "system", "content": GEN_SYSTEM},
             {"role": "user", "content": f"Write up to {per_chunk} question(s) for this passage.\n\n{_passage(ch)}"}],
            schema=GEN_SCHEMA, num_predict=400)
        text_norm = norm_space(ch["text"]).lower()
        for j, item in enumerate(out.get("items", [])[:per_chunk]):
            q, a, ev = (norm_space(item.get(k, "")) for k in ("question", "answer", "evidence"))
            reasons = []
            if not q or not a:
                reasons.append("empty")
            if ev.lower() not in text_norm:
                reasons.append("evidence not verbatim")
            if norm_answer(a) and norm_answer(a) not in norm_answer(ev) and norm_answer(a) not in norm_answer(ch["text"]):
                reasons.append("answer not in passage")
            if len(a.split()) > 12:
                reasons.append("answer too long")
            if reasons:
                rejected += 1
                continue
            candidates.append({"qa_id": f"{ch['chunk_id']}-q{j}", "chunk_id": ch["chunk_id"],
                               "page_id": ch["page_id"], "section": ch["section"],
                               "question": q, "answer": a, "evidence": ev})
        if (i + 1) % 20 == 0:
            print(f"  generated from {i + 1}/{len(chunks)} chunks: {len(candidates)} kept, {rejected} rejected")
    write_jsonl(QA_CANDIDATES, candidates)
    print(f"qa candidates: {len(candidates)} (rejected by span checks: {rejected}) -> {QA_CANDIDATES}")
    return candidates


def _lexical(pred, gold):
    """Whole-token comparison. True when every gold token appears in the prediction;
    False when no token overlaps; None (ask the judge) for partial overlap."""
    p, g = norm_answer(pred), norm_answer(gold)
    if not p or p == "unknown":
        return False
    pt, gt = set(p.split()), set(g.split())
    if not pt or not gt:
        return None
    if gt <= pt:
        return True
    # gold as a whole unit inside the prediction, bounded by non-alphanumerics
    # ("authorized_keys" in "~/.ssh/authorized_keys"; but not "2" in "128")
    if len(g) >= 3 and re.search(r"(?<![a-z0-9])" + re.escape(g) + r"(?![a-z0-9])", p):
        return True
    overlap = len(pt & gt)
    f1 = 0 if overlap == 0 else 2 * overlap / (len(pt) + len(gt))
    if f1 >= 0.6:
        return True
    if f1 == 0:
        return False
    return None  # inconclusive: ask the judge


def _grade(question, pred, gold):
    lex = _lexical(pred, gold)
    if lex is not None:
        return lex, "lexical"
    out = llm.chat(
        [{"role": "system", "content": "You grade short answers. Reply in JSON."},
         {"role": "user", "content": f"Question: {question}\nGold answer: {gold}\nCandidate answer: {pred}\n"
                                     "Is the candidate answer correct, i.e. does it state the same fact as the gold answer?"}],
        schema=JUDGE_SCHEMA, num_predict=20)
    return bool(out.get("correct")), "judge"


def annotate():
    chunks = {c["chunk_id"]: c for c in read_jsonl(CHUNKS_FILE)}
    rows = []
    for i, qa in enumerate(read_jsonl(QA_CANDIDATES)):
        blind = llm.chat([{"role": "system", "content": BLIND_SYSTEM},
                          {"role": "user", "content": qa["question"]}], num_predict=40).strip()
        informed = llm.chat([{"role": "system", "content": INFORMED_SYSTEM},
                             {"role": "user", "content": f"{_passage(chunks[qa['chunk_id']])}\n\nQuestion: {qa['question']}"}],
                            num_predict=40).strip()
        b_ok, b_how = _grade(qa["question"], blind, qa["answer"])
        i_ok, i_how = _grade(qa["question"], informed, qa["answer"])
        label = ("kept" if (not b_ok and i_ok) else
                 "answerable_blind" if b_ok else "failed_informed")
        rows.append(dict(qa, blind_answer=blind, blind_correct=b_ok, blind_graded_by=b_how,
                         informed_answer=informed, informed_correct=i_ok, informed_graded_by=i_how,
                         label=label))
        if (i + 1) % 50 == 0:
            print(f"  annotated {i + 1}")
    write_jsonl(QA_ANNOTATED, rows)
    kept = [r for r in rows if r["label"] == "kept"]
    write_jsonl(QA_KEPT, kept)
    counts = {k: sum(r["label"] == k for r in rows) for k in ("kept", "answerable_blind", "failed_informed")}
    print(f"qa annotated: {len(rows)} -> {counts}; kept -> {QA_KEPT}")
    return rows


def run():
    cfg = load_config()["qa"]
    llm.chat([{"role": "user", "content": "warm-up"}], num_predict=1, use_cache=False)
    generate(cfg["per_chunk"], cfg.get("max_chunks"))
    annotate()
