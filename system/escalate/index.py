"""Step 5: embed every chunk and search the index.

nomic-embed-text expects task prefixes: "search_document: " for passages and
"search_query: " for queries. Vectors are L2-normalized and stored as float32
so cosine similarity is a dot product.
"""
import hashlib
import json

import numpy as np

from .common import CACHE, CHUNKS_FILE, INDEX, load_config, read_jsonl, write_json
from . import llm

VECTORS = INDEX / "vectors.npy"
META = INDEX / "meta.json"
QUERY_CACHE = CACHE / "query_vectors.jsonl"


def _doc_text(c):
    return f"search_document: {c['title']} - {c['heading'] or c['title']}\n{c['text']}"


def build(force=False):
    """Embed every chunk. Reuses the committed vectors when they were built from the same
    chunks (by hash) with the same embedding model digest, so a rebuild on another machine
    does not silently change retrieval scores; pass force=True to re-embed."""
    cfg = load_config()
    chunks = read_jsonl(CHUNKS_FILE)
    chunks_hash = hashlib.sha256(CHUNKS_FILE.read_bytes()).hexdigest()
    model = cfg["models"]["embed"]
    if not force and META.exists() and VECTORS.exists():
        meta = json.loads(META.read_text(encoding="utf-8"))
        if meta.get("chunks_sha256") == chunks_hash and meta.get("model") == model:
            print(f"index: up to date ({len(meta['chunk_ids'])} chunks, {model}); reusing {VECTORS.name}. "
                  "Use --force to re-embed.")
            smoke_test()
            return
    vecs = np.asarray(llm.embed([_doc_text(c) for c in chunks]), dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    INDEX.mkdir(parents=True, exist_ok=True)
    np.save(VECTORS, vecs)
    write_json(META, {"model": model, "digest": llm.digest(model), "dim": int(vecs.shape[1]),
                      "chunks_sha256": chunks_hash, "chunk_ids": [c["chunk_id"] for c in chunks]})
    print(f"index: {vecs.shape[0]} x {vecs.shape[1]} -> {VECTORS}")
    smoke_test()


def smoke_test():
    """Runbook Section 3: query a known fact and record the top-3 chunks as evidence."""
    q = "What is the time limit of the gpu_short QoS?"
    hits = Index().search(q, 3)
    write_json(INDEX / "smoke_test.json", {"query": q, "expected_page": "/hpc/job-handling/partitions/",
                                           "top3": [{"chunk_id": h["chunk_id"], "score": h["score"], "path": h["path"],
                                                     "heading": h["heading"]} for h in hits],
                                           "passed": any(h["path"] == "/hpc/job-handling/partitions/" for h in hits)})
    print(f"index smoke test: top-3 {[h['chunk_id'] for h in hits]} -> "
          f"{'PASS' if any(h['path'] == '/hpc/job-handling/partitions/' for h in hits) else 'FAIL'}")


class Index:
    """Chunk index plus a committed cache of query vectors, so a replayed agent
    run retrieves exactly the same chunks on any machine."""

    def __init__(self):
        self.meta = json.loads(META.read_text(encoding="utf-8"))
        self.vecs = np.load(VECTORS)
        self.chunks = {c["chunk_id"]: c for c in read_jsonl(CHUNKS_FILE)}
        self.ids = self.meta["chunk_ids"]
        self._qcache = {}
        if QUERY_CACHE.exists():
            for line in QUERY_CACHE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if row["model"] == self.meta["model"]:
                        self._qcache[row["query"]] = np.asarray(row["vector"], dtype=np.float32)

    def _query_vec(self, query):
        if query not in self._qcache:
            q = np.asarray(llm.embed([f"search_query: {query}"], model=self.meta["model"])[0], dtype=np.float32)
            q /= np.linalg.norm(q)
            self._qcache[query] = q
            QUERY_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(QUERY_CACHE, "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"model": self.meta["model"], "query": query,
                                    "vector": [round(float(x), 7) for x in q]}) + "\n")
        return self._qcache[query]

    def search(self, query, k=4):
        scores = self.vecs @ self._query_vec(query)
        order = np.argsort(-scores)[:k]
        return [dict(self.chunks[self.ids[i]], score=round(float(scores[i]), 4)) for i in order]


def run(force=False):
    build(force)
