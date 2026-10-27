import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from escalate import server

EV = {"participant_code": "P07", "session_id": "P07-1", "block_order_group": 2, "block_index": 1, "form": "S1",
      "timestamp_utc": "2026-10-27T12:00:00Z", "source_open_duration_s": None, "item_id": "J1a",
      "recommendation_correctness": "correct", "event_type": "send", "event_detail": None, "t_ms": 120, "seq": 1}
SUMMARY = {"participant_code": "P07", "session_id": "P07-1", "block_order_group": 2, "block_index": 1, "form": "S1",
           "item_id": "J1a", "recommendation_correctness": "correct", "final_value": "gpu_short", "accuracy": 1,
           "followed": 1, "verified": 1, "source_pattern": "both", "dwell_a_s": 3.5, "dwell_b_s": 4.0, "opens_a": 1,
           "opens_b": 1, "decision_time_s": 2.1, "total_time_s": 40.2, "source_open_at_fork": "none", "focus_lost_s": 0}
SESSION_START = {"participant_code": "P07", "session_id": "P07-1", "participant_number": 7, "pilot": 0,
                 "order_group": 2, "rotation_id": 1, "block_order": ["S1", "S3", "S2"], "standing": "graduate",
                 "gender": "self-describe", "gender_self_describe": "agender", "course_of_study": "CS MS",
                 "prior_falcon_use": "no", "started_utc": "2026-10-27T12:00:00Z"}
SESSION_END = {"participant_code": "P07", "session_id": "P07-1", "ranking": ["S2", "S1", "S3"],
               "ranking_reason": "fewer interruptions", "finished_utc": "2026-10-27T12:40:00Z"}
INSTRUMENTS ={"participant_code": "P07", "session_id": "P07-1", "block_index": 1, "form": "S1",
               "tlx_mental": 10, "tlx_physical": 2, "tlx_temporal": 8, "tlx_performance": 5, "tlx_effort": 9,
               "tlx_frustration": 4, "intrusion": 3, "manip_response": "S1", "manip_correct": 1,
               "timestamp_utc": "2026-10-27T12:00:00Z"}


class DbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved_db = server.SESSIONS_DB
        server.SESSIONS_DB = Path(self.tmp.name) / "sessions" / "events.sqlite"

    def tearDown(self):
        server.SESSIONS_DB = self.saved_db
        self.tmp.cleanup()

    def query(self, sql, args=()):
        con = sqlite3.connect(server.SESSIONS_DB)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()


class SchemaTest(DbTest):
    def columns(self, table):
        return {r[1] for r in self.query(f"PRAGMA table_info({table})")}

    def test_fresh_db_has_registry_columns(self):
        server._connect().close()
        for table, cols in server.TABLES.items():
            self.assertEqual(self.columns(table), {c for c, _ in cols}, table)

    def test_old_db_is_upgraded(self):
        server.SESSIONS_DB.parent.mkdir(parents=True)
        con = sqlite3.connect(server.SESSIONS_DB)
        con.executescript("""
            CREATE TABLE task_summary (participant_code TEXT, session_id TEXT, item_id TEXT);
            CREATE TABLE session (participant_code TEXT, session_id TEXT, gender TEXT,
                                  PRIMARY KEY (participant_code, session_id));""")
        con.close()
        server._connect().close()
        self.assertTrue({"source_open_at_fork", "focus_lost_s"} <= self.columns("task_summary"))
        self.assertIn("gender_self_describe", self.columns("session"))

    def test_failed_write_rolls_back_and_releases_db(self):
        with self.assertRaises(RuntimeError):
            with server._db() as con:
                con.execute("INSERT INTO session (participant_code, session_id) VALUES ('P07', 'P07-1')")
                raise RuntimeError("boom")
        t = time.monotonic()
        server.log_instruments(INSTRUMENTS)
        self.assertLess(time.monotonic() - t, 1.0)
        self.assertEqual(self.query("SELECT COUNT(*) FROM session"), [(0,)])
        self.assertEqual(self.query("SELECT COUNT(*) FROM block_instruments"), [(1,)])


class PayloadTest(DbTest):
    def test_unknown_event_key_rejected(self):
        with self.assertRaises(server.PayloadError) as cm:
            server.log_events([{**EV, "evnt_type": "x"}])
        self.assertIn("evnt_type", str(cm.exception))

    def test_unknown_summary_key_rejected(self):
        with self.assertRaises(server.PayloadError) as cm:
            server.log_events([], {**SUMMARY, "dwell_c_s": 1})
        self.assertIn("dwell_c_s", str(cm.exception))

    def test_unknown_instrument_key_rejected(self):
        with self.assertRaises(server.PayloadError) as cm:
            server.log_instruments({**INSTRUMENTS, "tlx_mentl": 3})
        self.assertIn("tlx_mentl", str(cm.exception))

    def test_unknown_session_key_rejected(self):
        with self.assertRaises(server.PayloadError) as cm:
            server.upsert_session({**SESSION_START, "gendr": "x"})
        self.assertIn("gendr", str(cm.exception))

    def test_missing_session_id_rejected(self):
        ev = dict(EV)
        del ev["session_id"]
        with self.assertRaises(server.PayloadError):
            server.log_events([ev])

    def test_client_payloads_accepted(self):
        server.upsert_session(SESSION_START)
        server.log_events([EV], SUMMARY)
        server.log_instruments(INSTRUMENTS)
        server.upsert_session(SESSION_END)
        self.assertEqual(self.query("SELECT COUNT(*) FROM events"), [(1,)])
        self.assertEqual(self.query("SELECT COUNT(*) FROM task_summary"), [(1,)])
        self.assertEqual(self.query("SELECT COUNT(*) FROM block_instruments"), [(1,)])
        self.assertEqual(self.query("SELECT gender_self_describe, finished_utc FROM session"),
                         [("agender", "2026-10-27T12:40:00Z")])


class IdempotencyTest(DbTest):
    def test_event_twice_stores_one_row(self):
        self.assertEqual(server.log_events([EV]), 1)
        self.assertEqual(server.log_events([EV]), 0)
        self.assertEqual(self.query("SELECT COUNT(*) FROM events"), [(1,)])

    def test_summary_twice_stores_one_row(self):
        server.log_events([], SUMMARY)
        server.log_events([], SUMMARY)
        self.assertEqual(self.query("SELECT COUNT(*) FROM task_summary"), [(1,)])

    def test_instruments_twice_stores_one_row(self):
        server.log_instruments(INSTRUMENTS)
        server.log_instruments(INSTRUMENTS)
        self.assertEqual(self.query("SELECT COUNT(*) FROM block_instruments"), [(1,)])

    def test_event_without_seq_rejected(self):
        ev = dict(EV)
        del ev["seq"]
        with self.assertRaises(server.PayloadError):
            server.log_events([ev])

    def test_same_seq_other_session_is_kept(self):
        server.log_events([EV, {**EV, "session_id": "P07-2"}])
        self.assertEqual(self.query("SELECT COUNT(*) FROM events"), [(2,)])


class HttpTest(DbTest):
    def setUp(self):
        super().setUp()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def request(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_http_unknown_key_returns_400(self):
        status, body = self.request("/api/events", {"events": [{**EV, "bogus": 1}]})
        self.assertEqual(status, 400)
        self.assertIn("bogus", body["error"])


if __name__ == "__main__":
    unittest.main()
