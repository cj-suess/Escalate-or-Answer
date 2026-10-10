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
from . import agent, llm, rotation
from .index import Index

STATIC = ROOT / "playground"
TASKS_DIR = ROOT / "data" / "tasks"
SESSIONS_DB = ROOT / "data" / "sessions" / "events.sqlite"
_db_lock = threading.Lock()

EVENT_COLS = ("participant_code", "session_id", "block_order_group", "block_index", "form", "item_id",
              "recommendation_correctness", "event_type", "event_detail", "t_ms", "timestamp_utc", "source_open_duration_s")
SUMMARY_COLS = ("participant_code", "session_id", "block_order_group", "block_index", "form", "item_id",
                "recommendation_correctness", "final_value", "accuracy", "followed", "verified", "source_pattern",
                "dwell_a_s", "dwell_b_s", "opens_a", "opens_b", "decision_time_s", "total_time_s",
                "source_open_at_fork", "focus_lost_s")
INSTRUMENT_COLS = ("participant_code", "session_id", "block_index", "form", "tlx_mental", "tlx_physical", "tlx_temporal",
                   "tlx_performance", "tlx_effort", "tlx_frustration", "intrusion", "manip_response", "manip_correct",
                   "timestamp_utc")
SESSION_COLS = ("participant_code", "session_id", "participant_number", "pilot", "order_group", "rotation_id",
                "block_order", "standing", "gender", "course_of_study", "prior_falcon_use", "ranking", "ranking_reason",
                "started_utc", "finished_utc")

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS events (
    participant_code TEXT, session_id TEXT, block_order_group INTEGER, block_index INTEGER, form TEXT, item_id TEXT,
    recommendation_correctness TEXT, event_type TEXT, event_detail TEXT, t_ms INTEGER,
    timestamp_utc TEXT, source_open_duration_s REAL);
CREATE TABLE IF NOT EXISTS task_summary (
    participant_code TEXT, session_id TEXT, block_order_group INTEGER, block_index INTEGER, form TEXT, item_id TEXT,
    recommendation_correctness TEXT, final_value TEXT, accuracy INTEGER, followed INTEGER,
    verified INTEGER, source_pattern TEXT, dwell_a_s REAL, dwell_b_s REAL, opens_a INTEGER,
    opens_b INTEGER, decision_time_s REAL, total_time_s REAL, source_open_at_fork TEXT, focus_lost_s REAL);
CREATE TABLE IF NOT EXISTS block_instruments (
    participant_code TEXT, session_id TEXT, block_index INTEGER, form TEXT,
    tlx_mental INTEGER, tlx_physical INTEGER, tlx_temporal INTEGER, tlx_performance INTEGER, tlx_effort INTEGER,
    tlx_frustration INTEGER, intrusion INTEGER, manip_response TEXT, manip_correct INTEGER, timestamp_utc TEXT);
CREATE TABLE IF NOT EXISTS session (
    participant_code TEXT, session_id TEXT, participant_number INTEGER, pilot INTEGER, order_group INTEGER,
    rotation_id INTEGER, block_order TEXT, standing TEXT, gender TEXT, course_of_study TEXT, prior_falcon_use TEXT,
    ranking TEXT, ranking_reason TEXT, started_utc TEXT, finished_utc TEXT,
    PRIMARY KEY (participant_code, session_id));
"""


def _connect():
    SESSIONS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(SESSIONS_DB)
    con.executescript(SCHEMA)
    # columns added after the first release (a database created before them is upgraded in place)
    have = {r[1] for r in con.execute("PRAGMA table_info(task_summary)")}
    for col, typ in (("source_open_at_fork", "TEXT"), ("focus_lost_s", "REAL")):
        if col not in have:
            con.execute(f"ALTER TABLE task_summary ADD COLUMN {col} {typ}")
    return con


def _insert(con, table, cols, row):
    con.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                tuple(row.get(c) for c in cols))


def log_events(events, summary=None):
    """Append playground events (and an optional per-task summary row) to SQLite.

    Event columns follow the runbook schema (participant_code, block_index, form,
    item_id, recommendation_correctness, event_type, event_detail, timestamp, and
    source_open_duration_s on source_close)."""
    with _db_lock:
        con = _connect()
        con.executemany(f"INSERT INTO events ({','.join(EVENT_COLS)}) VALUES ({','.join('?' * len(EVENT_COLS))})",
                        [tuple(e.get(c) for c in EVENT_COLS) for e in events])
        if summary:
            _insert(con, "task_summary", SUMMARY_COLS, summary)
        con.commit()
        con.close()
    return len(events)


def log_instruments(row):
    """One row per block: raw NASA-TLX, the intrusion item and the manipulation check (paper, Measures)."""
    with _db_lock:
        con = _connect()
        _insert(con, "block_instruments", INSTRUMENT_COLS, row)
        con.commit()
        con.close()


def upsert_session(row):
    """Session row: written at the start (demographics, assignment) and completed at the end (ranking)."""
    row = dict(row)
    for k in ("ranking", "block_order"):
        if isinstance(row.get(k), (list, dict)):
            row[k] = json.dumps(row[k], ensure_ascii=False)
    with _db_lock:
        con = _connect()
        cur = con.execute("SELECT 1 FROM session WHERE participant_code=? AND session_id=?",
                          (row.get("participant_code"), row.get("session_id")))
        if cur.fetchone():
            cols = [c for c in SESSION_COLS if c in row and c not in ("participant_code", "session_id")]
            con.execute(f"UPDATE session SET {', '.join(c + '=?' for c in cols)} WHERE participant_code=? AND session_id=?",
                        tuple(row[c] for c in cols) + (row["participant_code"], row["session_id"]))
        else:
            _insert(con, "session", SESSION_COLS, row)
        con.commit()
        con.close()


_agent_lock = threading.Lock()  # one model call stream at a time keeps outputs deterministic
_state = {}


def _data():
    if not _state:
        _state["pages"] = {p["page_id"]: p for p in read_jsonl(PAGES_FILE)}
        _state["chunks"] = {c["chunk_id"]: c for c in read_jsonl(CHUNKS_FILE)}
        _state["qa"] = read_jsonl(QA_ANNOTATED)
    return _state


def _tasks():
    """Frozen task records, sets (with their forks) and the study text, read fresh each time."""
    recs = {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in TASKS_DIR.glob("*.json") if not p.name.startswith("_")}
    sets = json.loads((TASKS_DIR / "_sets.json").read_text(encoding="utf-8"))
    sets["practice"] = {"name": "Practice", "assignment": "Practice: get to know the assistant.",
                        "tasks": sorted(k for k, r in recs.items() if r["set"] == "practice"), "forks": []}
    study_file = TASKS_DIR / "_study.json"
    study = json.loads(study_file.read_text(encoding="utf-8")) if study_file.exists() else {}
    return recs, sets, study


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
                recs, sets, study = _tasks()
                return self._send(200, {"sets": sets, "tasks": recs, "study": study})
            if url.path == "/api/plan":
                # the application assigns block order and task rotation from the participant number (paper, Apparatus)
                recs, sets, _ = _tasks()
                n = rotation.participant_number(q.get("participant", ""))
                return self._send(200, rotation.resolve(rotation.plan(n, sets), recs))
            if url.path == "/api/worksheet":
                recs, sets, _ = _tasks()
                return self._send(200, rotation.worksheet(sets, recs, int(q.get("n", 15))))
            if url.path == "/api/records":
                recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RECORDS.glob("*.json"))] if RECORDS.exists() else []
                return self._send(200, recs)
            return self._send(404, {"error": "not found"})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
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
            if url.path == "/api/instruments":
                log_instruments(body)
                return self._send(200, {"logged": 1})
            if url.path == "/api/session":
                upsert_session(body)
                return self._send(200, {"saved": 1})
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
