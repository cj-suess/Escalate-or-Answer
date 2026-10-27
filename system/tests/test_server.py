import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from escalate import server

INSTRUMENTS = {"participant_code": "P07", "session_id": "P07-1", "block_index": 1, "form": "S1",
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


if __name__ == "__main__":
    unittest.main()
