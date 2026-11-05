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
        self.assertEqual(self.store._rconns, [])
        self.assertIsNone(self.store._read_conn(), "a closed store hands out no reader")
        # tearDown closes again: must stay harmless.

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


if __name__ == "__main__":
    unittest.main()
