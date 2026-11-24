"""Chặn tool chạy mã tùy ý (REMOTE_BASH/WORKBENCH) và tool COMPOSIO_* chưa xét: trực tiếp, lồng, hoa/thường."""
import asyncio
import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import drive_guard_hub as h  # noqa: E402
import drive_write_guard as g  # noqa: E402

g.WRITE_ROOTS.clear()
g.WRITE_ROOTS.update({"agent-a": "SYN-WRITE-A"})
g.PROTECTED_ROOTS.clear()
g.PROTECTED_ROOTS.update({"root": "SYN-ROOT"})
NOPARENTS = lambda fid: []  # noqa: E731 - không cần metadata cho các lệnh này
OWN = "SYN-WRITE-A"


def multi(*subs):
    return {"tools": [{"tool_slug": s, "arguments": a} for s, a in subs]}


class DecideOpaque(unittest.TestCase):
    def test_direct_remote_bash_denied_even_without_actor(self):
        for actor in ("agent-a", None):
            self.assertFalse(g.decide(actor, "COMPOSIO_REMOTE_BASH_TOOL", {"command": "ls"}, NOPARENTS)["allow"])

    def test_direct_remote_workbench_denied(self):
        self.assertFalse(g.decide("agent-a", "COMPOSIO_REMOTE_WORKBENCH", {"code": "x"}, NOPARENTS)["allow"])

    def test_case_and_whitespace_normalized(self):
        for t in ("composio_remote_bash_tool", " COMPOSIO_Remote_Bash_Tool ", "Composio_Remote_Workbench"):
            self.assertFalse(g.decide("agent-a", t, {}, NOPARENTS)["allow"], t)

    def test_nested_remote_denied_in_multi(self):
        r = g.decide("agent-a", "COMPOSIO_MULTI_EXECUTE_TOOL",
                     multi(("GOOGLEDRIVE_LIST_FILES", {"folderId": OWN}),
                           ("COMPOSIO_REMOTE_BASH_TOOL", {"command": "x"})), NOPARENTS)
        self.assertFalse(r["allow"])

    def test_nested_lowercase_remote_denied(self):
        r = g.decide("agent-a", "COMPOSIO_MULTI_EXECUTE_TOOL",
                     multi(("composio_remote_workbench", {"code": "x"})), NOPARENTS)
        self.assertFalse(r["allow"])

    def test_double_nested_denied(self):
        inner = {"tools": [{"tool_slug": "COMPOSIO_REMOTE_BASH_TOOL", "arguments": {"command": "x"}}]}
        r = g.decide("agent-a", "COMPOSIO_MULTI_EXECUTE_TOOL",
                     multi(("COMPOSIO_MULTI_EXECUTE_TOOL", inner)), NOPARENTS)
        self.assertFalse(r["allow"])

    def test_unknown_composio_tool_denied(self):
        self.assertFalse(g.decide("agent-a", "COMPOSIO_SOMETHING_NEW", {}, NOPARENTS)["allow"])
        r = g.decide("agent-a", "COMPOSIO_MULTI_EXECUTE_TOOL",
                     multi(("COMPOSIO_SOMETHING_NEW", {})), NOPARENTS)
        self.assertFalse(r["allow"])

    def test_safe_catalog_tools_allowed(self):
        self.assertTrue(g.decide("agent-a", "COMPOSIO_SEARCH_TOOLS", {}, NOPARENTS)["allow"])
        self.assertTrue(g.decide("agent-a", "COMPOSIO_GET_TOOL_SCHEMAS", {}, NOPARENTS)["allow"])

    def test_read_drive_still_allowed(self):
        r = g.decide("agent-a", "COMPOSIO_MULTI_EXECUTE_TOOL",
                     multi(("GOOGLEDRIVE_LIST_FILES", {"folderId": "anything"})), NOPARENTS)
        self.assertTrue(r["allow"], r)

    def test_non_composio_outside_scope_unchanged(self):
        self.assertTrue(g.decide("agent-a", "zalo_get_history", {}, NOPARENTS)["allow"])


class HubOpaque(unittest.TestCase):
    def _go(self, tool, args, env):
        calls = []

        async def call(a):
            calls.append(a)
            return "REAL"
        wrapped = h.wrap(call, {"connector_id": "composio"}, tool, "fn", env=env)
        buf = io.StringIO()
        with mock.patch.object(h, "_actor", return_value="agent-a"), redirect_stderr(buf):
            out = asyncio.run(wrapped(args))
        return out, calls, buf.getvalue()

    def test_enforce_blocks_remote_bash(self):
        out, calls, _ = self._go("COMPOSIO_REMOTE_BASH_TOOL", {"command": "x"}, {"JAVIS_DRIVE_WRITE_GUARD": "enforce"})
        self.assertTrue(out.startswith("ERROR:"))
        self.assertEqual(calls, [])

    def test_shadow_logs_but_calls_through(self):
        out, calls, log = self._go("COMPOSIO_REMOTE_BASH_TOOL", {"command": "x"}, {"JAVIS_DRIVE_WRITE_GUARD": "shadow"})
        self.assertEqual(out, "REAL")
        self.assertIn("DENY", log)


if __name__ == "__main__":
    unittest.main()
