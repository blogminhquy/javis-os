"""Nối guard 3 trưởng phòng vào ĐƯỜNG THẬT: ClaudeSDK._options (wrap qua install_direct_deny) và argv CLI
(SubprocessCLITransport._build_command của claude_agent_sdk). Mock: không gọi API, không chạy process, không ghi file.
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import drive_write_guard as g  # noqa: E402
import turn_context as tc  # noqa: E402
import claude_sdk_engine as eng  # noqa: E402

LEADERS = "javis-vu,alex-learning-coach,alex-manager-affiliate"
ENF = {"JAVIS_DRIVE_WRITE_GUARD": "enforce", "JAVIS_DRIVE_GUARD_PILOT": LEADERS}
CODE = {"Bash", "Write", "Edit", "NotebookEdit"}


def _agent(slug):
    return {"key": "k-" + slug, "slug": slug, "config_version": 1}


class OptionsWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        g.install_direct_deny()  # đường thật claude_engine() gọi

    def _opts(self, env, turn=None, keep=("mcp__keep",)):
        e = eng.ClaudeSDK(system_prompt="x", cwd="/tmp", tag="t")
        e.disallowed_tools = list(keep)
        token = tc.bind(turn) if turn is not None else None
        try:
            with mock.patch.dict(os.environ, env, clear=True):
                return e._options().disallowed_tools
        finally:
            if token is not None:
                tc.reset(token)

    def test_valid_leader_direct_chat_denied_union_kept(self):
        got = self._opts(ENF, tc.make("dashboard", chat_id="c", agent=_agent("javis-vu")))
        self.assertTrue(CODE <= set(got))
        self.assertIn("mcp__keep", got)
        self.assertEqual(got.count("Bash"), 1)
        self.assertNotIn("Read", got)

    def test_all_three_leaders_denied(self):
        for slug in LEADERS.split(","):
            self.assertTrue(CODE <= set(self._opts(ENF, tc.make("dashboard", chat_id="c", agent=_agent(slug)))), slug)

    def test_leader_team_step_and_task_denied(self):
        self.assertTrue(CODE <= set(self._opts(ENF, tc.make("dashboard", chat_id="c", actor="alex-manager-affiliate"))))
        self.assertTrue(CODE <= set(self._opts(ENF, tc.make("dashboard", chat_id="c", actor="javis-vu", job="t1"))))

    def test_specialist_untouched(self):
        self.assertFalse(CODE & set(self._opts(ENF, tc.make("dashboard", chat_id="c", agent=_agent("chuyen-vien-x")))))

    def test_owner_chat_no_agent_unaffected(self):
        got = self._opts(ENF, tc.make("dashboard", chat_id="c"))
        self.assertFalse(CODE & set(got))
        self.assertIn("mcp__keep", got)

    def test_no_turn_context_unaffected(self):
        self.assertFalse(CODE & set(self._opts(ENF, None)))

    def test_off_and_shadow_noop(self):
        for mode in ("off", "shadow"):
            env = {"JAVIS_DRIVE_WRITE_GUARD": mode, "JAVIS_DRIVE_GUARD_PILOT": LEADERS}
            self.assertFalse(CODE & set(self._opts(env, tc.make("dashboard", chat_id="c", agent=_agent("javis-vu")))), mode)

    def test_leader_turn_with_broken_pilot_refused_at_options(self):
        env = {"JAVIS_DRIVE_WRITE_GUARD": "enforce", "JAVIS_DRIVE_GUARD_PILOT": "*"}
        with self.assertRaises(g.LeaderGuardRefusal):
            self._opts(env, tc.make("dashboard", chat_id="c", agent=_agent("javis-vu")))

    def test_malformed_identity_refused_at_options(self):
        with self.assertRaises(g.LeaderGuardRefusal):
            self._opts(ENF, tc.make("dashboard", chat_id="c", agent={"slug": "javis-vu"}))


class CliArgvWiringTests(unittest.TestCase):
    """Argv thật của claude-agent-sdk (không chạy process)."""

    def _argv(self, disallowed):
        from claude_agent_sdk import ClaudeAgentOptions
        from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
        opts = ClaudeAgentOptions(disallowed_tools=list(disallowed), cli_path="/bin/echo")
        return SubprocessCLITransport(prompt="p", options=opts)._build_command()

    @staticmethod
    def _deny_values(argv):
        return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--disallowedTools"]

    def test_leader_argv_has_code_tools_and_keeps_existing_not_read(self):
        obj = SimpleNamespace(disallowed_tools=["mcp__keep"])
        turn = tc.make("dashboard", chat_id="c", agent=_agent("javis-vu"))
        deny = g.add_direct_deny(obj, env=ENF, turn=turn).disallowed_tools
        argv = self._argv(deny)
        values = " ".join(self._deny_values(argv))
        for t in CODE:
            self.assertIn(t, values)
        self.assertIn("mcp__keep", values)
        self.assertNotIn("Read", self._deny_values(argv))

    def test_owner_argv_has_no_code_deny(self):
        obj = SimpleNamespace(disallowed_tools=[])
        deny = g.add_direct_deny(obj, env=ENF, turn=tc.make("dashboard", chat_id="c")).disallowed_tools
        self.assertFalse(CODE & set(self._deny_values(self._argv(deny))))

    def test_empty_deny_no_flag(self):
        self.assertNotIn("--disallowedTools", self._argv([]))


if __name__ == "__main__":
    unittest.main()
