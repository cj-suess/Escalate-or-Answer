"""Deterministic Ollama client with a committed, content-addressed cache.

Every chat call is sent with temperature 0, top_k 1 and a fixed seed. The
request (model name + digest + options + messages + format) is hashed; the
response is stored in data/cache/llm_cache.jsonl. Re-running the pipeline on
any machine with the same model digest returns byte-identical outputs from the
cache, even where GPU floating-point differences would otherwise change a token.
"""
import hashlib
import json
import threading

import requests

from .common import LLM_CACHE, LOCK_FILE, load_config, ollama_host

_lock = threading.Lock()
_cache = None
_digests = {}


class OllamaError(RuntimeError):
    pass


def _load_cache():
    global _cache
    if _cache is None:
        _cache = {}
        if LLM_CACHE.exists():
            with open(LLM_CACHE, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        _cache[row["key"]] = row["response"]
    return _cache


def _append_cache(key, request, response):
    LLM_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(LLM_CACHE, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"key": key, "request": request, "response": response},
                           ensure_ascii=False, sort_keys=True) + "\n")


def tags():
    try:
        r = requests.get(f"{ollama_host()}/api/tags", timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(f"Ollama is not reachable at {ollama_host()} ({e}). Start the Ollama app.") from e
    return r.json().get("models", [])


def version():
    try:
        return requests.get(f"{ollama_host()}/api/version", timeout=5).json().get("version")
    except requests.RequestException:
        return None


def digest(model):
    """Digest of a local model; falls back to the lock file when Ollama is not running."""
    if model in _digests:
        return _digests[model]
    d = None
    names = {model} if ":" in model else {model, model + ":latest"}
    try:
        for m in tags():
            if m.get("name") in names or m.get("model") in names:
                d = m.get("digest")
                break
    except OllamaError:
        pass
    if d is None and LOCK_FILE.exists():
        d = json.loads(LOCK_FILE.read_text(encoding="utf-8")).get("models", {}).get(model, {}).get("digest")
    _digests[model] = d
    return d


def _key(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def chat(messages, schema=None, model=None, num_predict=512, use_cache=True):
    """One deterministic chat call. Returns the message content (str), or parsed JSON when schema is given."""
    cfg = load_config()
    model = model or cfg["models"]["llm"]
    options = dict(cfg["llm_options"], num_predict=num_predict)
    request = {"model": model, "digest": digest(model), "options": options,
               "messages": messages, "format": schema}
    key = _key(request)
    with _lock:
        cache = _load_cache()
        if use_cache and key in cache:
            content = cache[key]
            return json.loads(content) if schema else content
    body = {"model": model, "messages": messages, "stream": False, "options": options}
    if schema:
        body["format"] = schema
    try:
        r = requests.post(f"{ollama_host()}/api/chat", json=body, timeout=600)
        r.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(f"chat call failed: {e}") from e
    content = r.json()["message"]["content"]
    if use_cache:
        with _lock:
            _cache[key] = content
            _append_cache(key, request, content)
    if schema:
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise OllamaError(f"model returned invalid JSON: {content[:200]}") from e
    return content


def embed(texts, model=None):
    """Embeddings for a list of strings (not cached: the index itself is the committed artifact)."""
    model = model or load_config()["models"]["embed"]
    out = []
    for i in range(0, len(texts), 32):
        batch = texts[i:i + 32]
        try:
            r = requests.post(f"{ollama_host()}/api/embed", json={"model": model, "input": batch}, timeout=600)
            r.raise_for_status()
        except requests.RequestException as e:
            raise OllamaError(f"embed call failed: {e}") from e
        out.extend(r.json()["embeddings"])
    return out


def pull(model):
    r = requests.post(f"{ollama_host()}/api/pull", json={"model": model, "stream": False}, timeout=None)
    r.raise_for_status()
    return r.json()
