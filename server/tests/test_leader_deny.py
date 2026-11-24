"""Logic guard của 3 trưởng phòng (fail-closed). Mock: turn dựng bằng turn_context.make, env truyền vào.
Không gọi API, không chạy shell, không ghi file."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import drive_write_guard as g  # noqa: E402
import turn_context as tc  # noqa: E402

LEADERS = "javis-vu,alex-learning-coach,alex-manager-affiliate"
ENF = {"JAVIS_DRIVE_WRITE_GUARD": "enforce", "JAVIS_DRIVE_GUARD_PILOT": LEADERS}
DIRECT = list(g.DIRECT_CONNECTOR_SERVERS)


def _agent(slug):
    return {"key": "k-" + slug, "slug": slug, "config_version": 1}


def _opts(existing=("mcp__keep",)):
    return SimpleNamespace(disallowed_tools=list(existing))


class FailClosedGuardTests(unittest.TestCase):
    def run_add(self, env, turn, existing=("mcp__keep",)):
        return g.add_direct_deny(_opts(existing), env=env, turn=turn).disallowed_tools

    def test_valid_leader_gets_code_tools_and_direct_connectors_union_kept(self):
        got = self.run_add(ENF, tc.make("dashboard", chat_id="c", agent=_agent("javis-vu")))
        for t in g.LEADER_DENY_TOOLS:
            self.assertIn(t, got)
        for s in DIRECT:
            self.assertIn(s, got)
        self.assertIn("mcp__keep", got)
        self.assertEqual(got.count("Bash"), 1)

    def test_all_three_leaders(self):
        for slug in LEADERS.split(","):
            self.assertIn("Bash", self.run_add(ENF, tc.make("dashboard", chat_id="c", agent=_agent(slug))), slug)

    def test_read_is_never_denied(self):
        got = self.run_add(ENF, tc.make("dashboard", chat_id="c", agent=_agent("javis-vu")))
        self.assertNotIn("Read", got)
        self.assertEqual(set(g.LEADER_DENY_TOOLS), {"Bash", "Write", "Edit", "NotebookEdit"})

    def test_unknown_slug_outside_pilot_untouched(self):
        got = self.run_add(ENF, tc.make("dashboard", chat_id="c", agent=_agent("chuyen-vien-x")))
        self.assertFalse(set(g.LEADER_DENY_TOOLS) & set(got))

    def test_owner_chat_no_agent_untouched(self):
        self.assertEqual(self.run_add(ENF, tc.make("dashboard", chat_id="c")), ["mcp__keep"] + DIRECT)

    def test_task_and_team_actor_identity(self):
        self.assertIn("Bash", self.run_add(ENF, tc.make("dashboard", chat_id="c", actor="javis-vu")))
        self.assertIn("Bash", self.run_add(ENF, tc.make("dashboard", chat_id="c", actor="alex-manager-affiliate")))

    def test_off_and_shadow_never_read_turn(self):
        for mode in ("off", "shadow"):
            env = {"JAVIS_DRIVE_WRITE_GUARD": mode, "JAVIS_DRIVE_GUARD_PILOT": LEADERS}
            with mock.patch("turn_context.current", side_effect=RuntimeError("must not be read")):
                got = g.add_direct_deny(_opts(), env=env).disallowed_tools
            self.assertEqual(got, ["mcp__keep"], mode)

    # ---- fail-closed: phải TỪ CHỐI, không được chạy không deny ----
    def assertRefuses(self, fn):
        with self.assertRaises(g.LeaderGuardRefusal):
            fn()

    def test_turn_missing_key_refused(self):
        turn = tc.make("dashboard", chat_id="c", agent={"slug": "javis-vu"})  # thiếu key -> identity_invalid
        self.assertRefuses(lambda: self.run_add(ENF, turn))

    def test_malformed_agent_refused(self):
        turn = tc.make("dashboard", chat_id="c", agent="javis-vu")  # không phải dict
        self.assertRefuses(lambda: self.run_add(ENF, turn))

    def test_agent_without_slug_refused(self):
        turn = tc.make("dashboard", chat_id="c", agent={"key": "k1"})
        self.assertRefuses(lambda: self.run_add(ENF, turn))

    def test_malformed_actor_refused(self):
        turn = tc.make("dashboard", chat_id="c", actor="../etc")
        self.assertRefuses(lambda: self.run_add(ENF, turn))

    def test_actor_agent_mismatch_refused(self):
        turn = tc.make("dashboard", chat_id="c", actor="javis-vu", agent=_agent("chuyen-vien-x"))
        self.assertRefuses(lambda: self.run_add(ENF, turn))

    def test_turn_read_error_refused(self):
        with mock.patch("turn_context.current", side_effect=RuntimeError("boom")):
            self.assertRefuses(lambda: g.add_direct_deny(_opts(), env=ENF))

    def test_broken_pilot_refuses_agent_turn_but_not_owner(self):
        env = {"JAVIS_DRIVE_WRITE_GUARD": "enforce", "JAVIS_DRIVE_GUARD_PILOT": "*"}
        self.assertRefuses(lambda: self.run_add(env, tc.make("dashboard", chat_id="c", agent=_agent("chuyen-vien-x"))))
        self.assertEqual(self.run_add(env, tc.make("dashboard", chat_id="c")), ["mcp__keep"] + DIRECT)

    def test_invalid_mode_refuses_agent_turn(self):
        env = {"JAVIS_DRIVE_WRITE_GUARD": "enfroce", "JAVIS_DRIVE_GUARD_PILOT": LEADERS}
        self.assertRefuses(lambda: self.run_add(env, tc.make("dashboard", chat_id="c", agent=_agent("javis-vu"))))
        self.assertEqual(self.run_add(env, tc.make("dashboard", chat_id="c")), ["mcp__keep"])


class EngineEntryTests(unittest.TestCase):
    """SDK/installer failure: enforce -> chỉ lượt Agent bị từ chối; chat chủ chạy; off/shadow không bao giờ chặn."""

    def test_install_raises_refuses_leader_turn(self):
        with mock.patch.object(g, "install_direct_deny", side_effect=RuntimeError("sdk missing")), \
                mock.patch("turn_context.current", return_value=tc.make("dashboard", chat_id="c", agent=_agent("javis-vu"))), \
                mock.patch.dict(os.environ, ENF, clear=True):
            with self.assertRaises(g.LeaderGuardRefusal):
                g.engine_entry()

    def test_install_returns_false_refuses_agent_turn(self):
        with mock.patch.object(g, "install_direct_deny", return_value=False), \
                mock.patch("turn_context.current", return_value=tc.make("dashboard", chat_id="c", actor="javis-vu")), \
                mock.patch.dict(os.environ, ENF, clear=True):
            with self.assertRaises(g.LeaderGuardRefusal):
                g.engine_entry()

    def test_install_fails_owner_chat_continues(self):
        with mock.patch.object(g, "install_direct_deny", side_effect=RuntimeError("sdk missing")), \
                mock.patch("turn_context.current", return_value=tc.make("dashboard", chat_id="c")), \
                mock.patch.dict(os.environ, ENF, clear=True):
            self.assertFalse(g.engine_entry())

    def test_install_fails_off_mode_only_logs(self):
        with mock.patch.object(g, "install_direct_deny", side_effect=RuntimeError("sdk missing")), \
                mock.patch.dict(os.environ, {"JAVIS_DRIVE_WRITE_GUARD": "off"}, clear=True):
            self.assertFalse(g.engine_entry())

    def test_install_ok_returns_true(self):
        with mock.patch.object(g, "install_direct_deny", return_value=True):
            self.assertTrue(g.engine_entry())


if __name__ == "__main__":
    unittest.main()
