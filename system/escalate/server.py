"""Playground server (standard library only): JSON API + static front end."""
import json
import mimetypes
import sqlite3
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .common import (CHUNKS_FILE, LOCK_FILE, PAGES_FILE, QA_ANNOTATED, RECORDS, ROOT,
                     SNAPSHOT_META, load_config, read_jsonl)
from . import agent, llm
from .index import Index

STATIC = ROOT / "playground"
SESSIONS_DB = ROOT / "data" / "sessions" / "events.sqlite"


def log_events(events, summary=None):
    """Append playground events (and an optional per-task summary row) to SQLite.

    Event columns follow the runbook schema (participant_code, block_index, form,
    item_id, recommendation_correctness, event_type, event_detail, timestamp, and
    source_open_duration_s on source_close)."""
    SESSIONS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(SESSIONS_DB)
    con.execute("""CREATE TABLE IF NOT EXISTS events (
        participant_code TEXT, session_id TEXT, block_order_group INTEGER, block_index INTEGER, form TEXT, item_id TEXT,
        recommendation_correctness TEXT, event_type TEXT, event_detail TEXT, t_ms INTEGER,
        timestamp_utc TEXT, source_open_duration_s REAL)""")
    con.execute("""CREATE TABLE IF NOT EXISTS task_summary (
        participant_code TEXT, session_id TEXT, block_order_group INTEGER, block_index INTEGER, form TEXT, item_id TEXT,
        recommendation_correctness TEXT, final_value TEXT, accuracy INTEGER, followed INTEGER,
        verified INTEGER, source_pattern TEXT, dwell_a_s REAL, dwell_b_s REAL, opens_a INTEGER,
        opens_b INTEGER, decision_time_s REAL, total_time_s REAL)""")
    cols = ("participant_code", "session_id", "block_order_group", "block_index", "form", "item_id", "recommendation_correctness",
            "event_type", "event_detail", "t_ms", "timestamp_utc", "source_open_duration_s")
    con.executemany(f"INSERT INTO events ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                    [tuple(e.get(c) for c in cols) for e in events])
    if summary:
        scols = ("participant_code", "session_id", "block_order_group", "block_index", "form", "item_id", "recommendation_correctness",
                 "final_value", "accuracy", "followed", "verified", "source_pattern", "dwell_a_s", "dwell_b_s",
                 "opens_a", "opens_b", "decision_time_s", "total_time_s")
        con.execute(f"INSERT INTO task_summary ({','.join(scols)}) VALUES ({','.join('?' * len(scols))})",
                    tuple(summary.get(c) for c in scols))
    con.commit()
    con.close()
    return len(events)
_agent_lock = threading.Lock()  # one model call stream at a time keeps outputs deterministic
_state = {}


def _data():
    if not _state:
        _state["pages"] = {p["page_id"]: p for p in read_jsonl(PAGES_FILE)}
        _state["chunks"] = {c["chunk_id"]: c for c in read_jsonl(CHUNKS_FILE)}
        _state["qa"] = read_jsonl(QA_ANNOTATED)
    return _state


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        q = dict(urllib.parse.parse_qsl(url.query))
        try:
            if url.path in ("/", "/index.html"):
                return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            if url.path.startswith("/static/"):
                f = (STATIC / url.path[len("/static/"):]).resolve()
                if STATIC.resolve() in f.parents and f.exists():
                    ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                    return self._send(200, f.read_bytes(), ctype)
                return self._send(404, {"error": "not found"})
            if url.path == "/api/status":
                cfg = load_config()
                try:
                    llm.tags()
                    up = True
                except llm.OllamaError:
                    up = False
                d = _data()
                return self._send(200, {
                    "ollama": up, "ollama_version": llm.version(), "models": cfg["models"],
                    "lock": json.loads(LOCK_FILE.read_text(encoding="utf-8")) if LOCK_FILE.exists() else None,
                    "snapshot": json.loads(SNAPSHOT_META.read_text(encoding="utf-8")) if SNAPSHOT_META.exists() else None,
                    "chunks": len(d["chunks"]), "qa": len(d["qa"]),
                    "qa_kept": sum(r["label"] == "kept" for r in d["qa"]),
                    "records": len(list(RECORDS.glob("*.json"))) if RECORDS.exists() else 0})
            if url.path == "/api/chunk":
                c = _data()["chunks"].get(q.get("id", ""))
                if not c:
                    return self._send(404, {"error": "no such chunk"})
                page = _data()["pages"][c["page_id"]]
                return self._send(200, {"chunk": c, "page": page})
            if url.path == "/api/qa":
                return self._send(200, _data()["qa"])
            if url.path == "/api/tasks":
                tdir = ROOT / "data" / "tasks"
                recs = {p.stem: json.loads(p.read_text(encoding="utf-8"))
                        for p in tdir.glob("*.json") if not p.name.startswith("_")}
                sets = json.loads((tdir / "_sets.json").read_text(encoding="utf-8"))
                sets["practice"] = {"name": "Practice", "assignment": "Practice: get to know the assistant.",
                                    "tasks": sorted(k for k, r in recs.items() if r["set"] == "practice")}
                return self._send(200, {"sets": sets, "tasks": recs})
            if url.path == "/api/records":
                recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RECORDS.glob("*.json"))] if RECORDS.exists() else []
                return self._send(200, recs)
            return self._send(404, {"error": "not found"})
        except Exception as e:  # surface errors to the UI
            traceback.print_exc()
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        try:
            body = self._body()
            if url.path == "/api/search":
                with _agent_lock:
                    hits = Index().search(body["query"], int(body.get("k", 5)))
                return self._send(200, hits)
            if url.path == "/api/agent":
                with _agent_lock:
                    rec = agent.run(body["question"].strip(), (body.get("situation") or "").strip() or None)
                return self._send(200, rec)
            if url.path == "/api/events":
                n = log_events(body.get("events", []), body.get("summary"))
                return self._send(200, {"logged": n})
            if url.path == "/api/freeze":
                rec = body["record"]
                path = agent.freeze(rec)
                return self._send(200, {"saved": str(path.relative_to(ROOT))})
            return self._send(404, {"error": "not found"})
        except llm.OllamaError as e:
            return self._send(503, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": str(e)})


def serve(port=8567):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"playground: http://127.0.0.1:{port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
