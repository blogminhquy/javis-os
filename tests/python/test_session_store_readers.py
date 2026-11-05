"""2026-11-05: chat reads no longer queue behind writes in the session store.

Before, every read shared the single write connection and its lock, so opening a chat waited for any write in
flight (a turn saving its answer, a bot logging a message). In WAL mode each thread now reads through its own
connection; only writes take the lock. DELETE journal mode keeps the shared path.
"""
from _paths import ROOT, SERVER  # noqa
import tempfile
import threading
import time
import unittest
from pathlib import Path

import sessions


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = sessions.SessionStore(Path(self._tmp.name) / "s.db")

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_read_does_not_wait_for_the_write_lock(self):
        sid = self.store.get_or_create(None, brain="brain", engine="t", model="t")
        self.store.append_message(sid, "user", "hello")
        self.assertTrue(self.store._wal, "a fresh store on a local disk runs in WAL mode")
        got = {}
        # Hold the write lock in another thread, the way a slow write would.
        held = threading.Event()
        release = threading.Event()

        def hold():
            with self.store._lock:
                held.set()
                release.wait(5)

        t = threading.Thread(target=hold)
        t.start()
        held.wait(5)
        try:
            t0 = time.monotonic()
            got["page"] = self.store.get_messages_page(sid, limit=30)
            got["sess"] = self.store.get_session(sid)
            got["ms"] = (time.monotonic() - t0) * 1000
        finally:
            release.set()
            t.join()
        self.assertEqual([m["content"] for m in got["page"]["messages"]], ["hello"])
        self.assertEqual(got["sess"]["id"], sid)
        self.assertLess(got["ms"], 1000, "the read went through its own connection, not the locked one")

    def test_a_read_sees_the_write_just_made(self):
        sid = self.store.get_or_create(None, brain="brain", engine="t", model="t")
        self.store.get_messages_page(sid, limit=30)          # opens this thread's reader
        self.store.append_message(sid, "assistant", "answer")
        self.assertEqual(self.store.count_messages(sid), 1)
        self.assertEqual(self.store.get_messages_page(sid, limit=30)["messages"][-1]["content"], "answer")

    def test_each_thread_has_its_own_reader_and_close_closes_them(self):
        sid = self.store.get_or_create(None, brain="brain", engine="t", model="t")
        conns = []

        def read():
            self.store.get_session(sid)
            conns.append(self.store._rlocal.conn)

        ts = [threading.Thread(target=read) for _ in range(3)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(len({id(c) for c in conns}), 3)
        self.assertNotIn(self.store._conn, conns)
        self.store.close()
        self.assertEqual(len(self.store._rconns), 0)
        self.assertIsNone(self.store._read_conn(), "a closed store hands out no reader")
        # tearDown closes again: must stay harmless.

    def test_a_finished_thread_leaves_no_open_reader(self):
        import gc
        sid = self.store.get_or_create(None, brain="brain", engine="t", model="t")
        for _ in range(5):
            t = threading.Thread(target=lambda: self.store.get_session(sid))
            t.start()
            t.join()
        gc.collect()
        self.assertLessEqual(len(self.store._rconns), 1, "readers of ended threads are released")

    def test_readers_are_read_only(self):
        sid = self.store.get_or_create(None, brain="brain", engine="t", model="t")
        self.store.get_session(sid)
        import sqlite3
        with self.assertRaises(sqlite3.OperationalError):
            self.store._rlocal.conn.execute("DELETE FROM sessions")

    def test_delete_journal_keeps_the_shared_path(self):
        self.store._wal = False
        sid = self.store.get_or_create(None, brain="brain", engine="t", model="t")
        self.assertIsNone(self.store._read_conn())
        self.assertEqual(self.store.get_session(sid)["id"], sid)

    def test_page_without_tool_calls(self):
        """Performance (2026-11-05): the chat view asks with tools=0. The stored tool calls, often most of the bytes,
        are not read then; everything else, the order and has_more stay the same."""
        sid = self.store.get_or_create(None, brain="brain", engine="t", model="t")
        for i in range(4):
            self.store.append_message(sid, "user", f"q{i}")
            self.store.append_message(sid, "assistant", f"a{i}", tool_calls=[{"name": "read", "output": "x" * 5000}])
        full = self.store.get_messages_page(sid, limit=3)
        light = self.store.get_messages_page(sid, limit=3, with_tools=False)
        self.assertTrue(any(m.get("tool_calls") for m in full["messages"]), "the default still carries tool calls")
        self.assertFalse(any("tool_calls" in m for m in light["messages"]))
        strip = lambda ms: [{k: v for k, v in m.items() if k != "tool_calls"} for m in ms]
        self.assertEqual(strip(full["messages"]), light["messages"])
        self.assertEqual(full["has_more"], light["has_more"])
        older = self.store.get_messages_page(sid, limit=3, with_tools=False,
                                             before=(light["messages"][0]["ts"], light["messages"][0]["id"]))
        self.assertEqual(len(older["messages"]), 3)
        self.assertFalse(any("tool_calls" in m for m in older["messages"]))

    def test_endpoints_pass_tools_through(self):
        src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
        self.assertIn("def sessions_get(session_id: str, limit: int = Query(0), tools: int = Query(1)):", src)
        self.assertIn("store.get_messages_page(session_id, limit=limit, with_tools=bool(tools))", src)
        self.assertIn("with_tools=bool(tools))   # tools=0: see sessions_get", src)


if __name__ == "__main__":
    unittest.main()
