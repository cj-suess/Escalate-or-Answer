"""Paths, config and small JSONL helpers shared by every pipeline step."""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOT = DATA / "snapshot"
CACHE = DATA / "cache"
INDEX = DATA / "index"
RECORDS = DATA / "records"

PAGES_FILE = SNAPSHOT / "pages.jsonl"
SNAPSHOT_META = SNAPSHOT / "snapshot_meta.json"
CHUNKS_FILE = DATA / "chunks.jsonl"
QA_CANDIDATES = DATA / "qa_candidates.jsonl"
QA_ANNOTATED = DATA / "qa_annotated.jsonl"
QA_KEPT = DATA / "qa_kept.jsonl"
LOCK_FILE = DATA / "models.lock.json"
LLM_CACHE = CACHE / "llm_cache.jsonl"


def load_config():
    with open(ROOT / "config.json", encoding="utf-8") as f:
        return json.load(f)


def ollama_host():
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def norm_space(text):
    return re.sub(r"\s+", " ", text).strip()


def norm_answer(text):
    """Lowercase, strip punctuation and articles: used for lexical answer matching."""
    text = text.lower()
    text = re.sub(r"[`'\"“”‘’]", "", text)
    text = re.sub(r"[^a-z0-9_./:@\-]+", " ", text)
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    # strip sentence punctuation from token edges ("no." -> "no", "/tmp." -> "/tmp")
    text = " ".join(t.strip(".:,") for t in text.split())
    return norm_space(text)
