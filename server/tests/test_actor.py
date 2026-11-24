"""Actor đáng tin: chỉ lấy từ turn (host gán), không từ args; không có -> DENY ghi."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import turn_context as tc  # noqa: E402
import drive_guard_hub as h  # noqa: E402
import drive_write_guard as g  # noqa: E402


class ActorTests(unittest.TestCase):
    def test_make_sanitizes_actor(self):
        self.assertEqual(tc.make("kanban", actor="agent-a")["actor"], "agent-a")
        self.assertEqual(tc.make("kanban", actor="../x")["actor"], "")
        self.assertEqual(tc.make("kanban", actor="a b")["actor"], "")
        self.assertEqual(tc.make("kanban")["actor"], "")

    def test_actor_from_turn_only(self):
        tok = tc.bind(tc.make("kanban", actor="agent-a"))
        try:
            self.assertEqual(h._actor(), "agent-a")
        finally:
            tc.reset(tok)

    def test_no_turn_means_no_actor(self):
        self.assertIsNone(h._actor())

    def test_unknown_actor_denied_by_decide(self):
        d = g.decide(None, "GOOGLEDRIVE_TRASH_FILE", {"file_id": "x"}, lambda f: [])
        self.assertFalse(d["allow"])


if __name__ == "__main__":
    unittest.main()
