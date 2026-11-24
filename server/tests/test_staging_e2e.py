"""Harness staging CÁCH LY: không production, không port, không daemon, không Drive thật.
9 WRITE_ROOT giả + stub invoker trả envelope Composio giả. Flag enforce chỉ trong tiến trình unittest này.
Mỗi case: đếm số lần tool THẬT được gọi (execution count); deny phải = 0."""
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
import turn_context as tc  # noqa: E402

AGENTS = [f"agent-{i}" for i in range(1, 10)]
ENF = {"JAVIS_DRIVE_WRITE_GUARD": "enforce", "JAVIS_DRIVE_GUARD_PILOT": "agent-1,agent-2,ghost"}
SHD = {"JAVIS_DRIVE_WRITE_GUARD": "shadow", "JAVIS_DRIVE_GUARD_PILOT": "agent-1,agent-2,ghost"}
COMPOSIO = {"connector_id": "composio"}
MULTI = "COMPOSIO_MULTI_EXECUTE_TOOL"


def _tree():
    t = {"SYN-ROOT": {"id": "SYN-ROOT", "parents": []}}
    for n, a in enumerate(AGENTS, 1):
        w = f"SYN-W{n}"
        t[w] = {"id": w, "parents": ["SYN-ROOT"], "mimeType": "application/vnd.google-apps.folder"}
        t[w + "-sub"] = {"id": w + "-sub", "parents": [w], "mimeType": "application/vnd.google-apps.folder"}
        t[w + "-doc"] = {"id": w + "-doc", "parents": [w + "-sub"]}
    for name, pid in [("SYN-SHARED", "SYN-SHARED"), ("SYN-GOV", "SYN-GOV"), ("SYN-INBOX", "SYN-INBOX"),
                      ("SYN-ARCHIVE", "SYN-ARCHIVE")]:
        t[pid] = {"id": pid, "parents": ["SYN-ROOT"], "mimeType": "application/vnd.google-apps.folder"}
    t["SYN-SHARED-doc"] = {"id": "SYN-SHARED-doc", "parents": ["SYN-SHARED"]}
    t["SYN-GOV-doc"] = {"id": "SYN-GOV-doc", "parents": ["SYN-GOV"]}
    t["SYN-ORPHAN"] = {"id": "SYN-ORPHAN", "parents": []}
    return t


class Fake:
    """Stub invoker: không chạm Drive thật. `fail_ids` mô phỏng lỗi metadata."""

    def __init__(self, tree, fail_ids=()):
        self.tree, self.fail_ids, self.meta_calls = tree, set(fail_ids), 0

    async def __call__(self, args):
        self.meta_calls += 1
        fid = args["tools"][0]["arguments"]["fileId"]
        if fid in self.fail_ids:
            return {"successful": False, "error": "simulated 5xx"}
        if fid not in self.tree:
            return {"successful": True, "data": {"results": [{"response": {"successful": False}}]}}
        return {"successful": True, "data": {"results": [{"response": {"successful": True, "data": dict(
            self.tree[fid], name=fid, trashed=False)}}]}}


def _multi(tool, args):
    return {"tools": [{"tool_slug": tool, "arguments": args}]}


class E2E(unittest.TestCase):
    def setUp(self):
        self._saved = (dict(g.WRITE_ROOTS), dict(g.PROTECTED_ROOTS), g.COMPOSIO_ACCOUNT)
        g.WRITE_ROOTS.clear()
        g.WRITE_ROOTS.update({a: f"SYN-W{n}" for n, a in enumerate(AGENTS, 1)})
        g.PROTECTED_ROOTS.clear()
        g.PROTECTED_ROOTS.update({"root": "SYN-ROOT", "governance": "SYN-GOV", "shared": "SYN-SHARED",
                                  "inbox": "SYN-INBOX", "archive": "SYN-ARCHIVE"})
        g.COMPOSIO_ACCOUNT = "SYN-ACCOUNT"
        self.fake = Fake(_tree())
        h.register_invoker(self.fake)
        self.executed = 0

    def tearDown(self):
        g.WRITE_ROOTS.clear()
        g.WRITE_ROOTS.update(self._saved[0])
        g.PROTECTED_ROOTS.clear()
        g.PROTECTED_ROOTS.update(self._saved[1])
        g.COMPOSIO_ACCOUNT = self._saved[2]
        h.register_invoker(None)

    async def _tool(self, args):
        self.executed += 1
        return "EXECUTED"

    def run_call(self, args, tool=MULTI, env=ENF, actor=None, bind_turn=True):
        """Chạy đúng đường route thật: wrap -> guard -> (tool thật chỉ khi ALLOW). Trả (kết quả, log stderr)."""
        self.executed = 0
        token = tc.bind(tc.make("kanban", actor=actor)) if (bind_turn and actor is not None) else None
        if bind_turn and actor is None:
            token = tc.bind(tc.make("kanban"))  # turn không có actor -> fail-closed
        try:
            wrapped = h.wrap(self._tool, COMPOSIO, tool, "fn", env=env)
            buf = io.StringIO()
            with redirect_stderr(buf):
                out = asyncio.run(wrapped(args))
        finally:
            tc.reset(token)
        return out, buf.getvalue()

    def assertDeny(self, out, log):
        self.assertTrue(str(out).startswith("ERROR:"), out)
        self.assertEqual(self.executed, 0, "tool thật đã chạy dù bị DENY")
        self.assertIn("DENY", log)

    def assertAllow(self, out, log):
        self.assertEqual(out, "EXECUTED", out)
        self.assertEqual(self.executed, 1)
        self.assertIn("ALLOW", log)

    # --- actor ---
    def test_known_actor_own_write_allowed(self):
        out, log = self.run_call(_multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-W1-doc"}), actor="agent-1")
        self.assertAllow(out, log)

    def test_own_subfolder_write_allowed(self):
        out, log = self.run_call(_multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-W1-sub"}), actor="agent-1")
        self.assertAllow(out, log)

    def test_unknown_actor_denied(self):
        out, log = self.run_call(_multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-W1-doc"}), actor="ghost")
        self.assertDeny(out, log)

    def test_no_actor_denied(self):
        out, log = self.run_call(_multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-W1-doc"}), actor=None)
        self.assertDeny(out, log)

    def test_spoofed_actor_in_args_ignored(self):
        # turn là agent-2, args khai "agent-1" và "actor": guard phải dùng agent-2 (không có quyền ghi vùng agent-1)
        args = _multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-W1-doc", "actor": "agent-1"})
        out, log = self.run_call(args, actor="agent-2")
        self.assertDeny(out, log)

    # --- phạm vi ---
    def test_read_shared_allowed(self):
        out, log = self.run_call(_multi("GOOGLEDRIVE_LIST_FILES", {"folderId": "SYN-SHARED"}), actor="agent-1")
        self.assertAllow(out, log)

    def test_cross_agent_write_denied(self):
        out, log = self.run_call(_multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-W2-doc"}), actor="agent-1")
        self.assertDeny(out, log)

    def test_shared_write_denied(self):
        out, log = self.run_call(_multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-SHARED-doc"}), actor="agent-1")
        self.assertDeny(out, log)

    def test_governance_write_denied(self):
        out, log = self.run_call(_multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-GOV-doc"}), actor="agent-1")
        self.assertDeny(out, log)

    def test_orphan_denied(self):
        out, log = self.run_call(_multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-ORPHAN"}), actor="agent-1")
        self.assertDeny(out, log)

    # --- lồng và opaque ---
    def test_nested_multi_cross_write_denied(self):
        args = {"tools": [{"tool_slug": "GOOGLEDRIVE_TRASH_FILE", "arguments": {"file_id": "SYN-W1-doc"}},
                          {"tool_slug": "GOOGLEDRIVE_TRASH_FILE", "arguments": {"file_id": "SYN-W3-doc"}}]}
        out, log = self.run_call(args, actor="agent-1")
        self.assertDeny(out, log)

    def test_remote_bash_denied(self):
        out, log = self.run_call({"command": "rm -rf /"}, tool="COMPOSIO_REMOTE_BASH_TOOL", actor="agent-1")
        self.assertDeny(out, log)

    def test_remote_workbench_denied(self):
        out, log = self.run_call({"code": "print(1)"}, tool="COMPOSIO_REMOTE_WORKBENCH", actor="agent-1")
        self.assertDeny(out, log)

    def test_remote_nested_in_multi_denied(self):
        args = {"tools": [{"tool_slug": "composio_remote_bash_tool", "arguments": {"command": "x"}}]}
        out, log = self.run_call(args, actor="agent-1")
        self.assertDeny(out, log)

    def test_unknown_composio_tool_default_deny(self):
        out, log = self.run_call({}, tool="COMPOSIO_BRAND_NEW_TOOL", actor="agent-1")
        self.assertDeny(out, log)

    # --- fail-closed và logging ---
    def test_metadata_error_fails_closed(self):
        self.fake.fail_ids.add("SYN-W1-doc")
        out, log = self.run_call(_multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-W1-doc"}), actor="agent-1")
        self.assertDeny(out, log)

    def test_shadow_calls_through_and_logs(self):
        out, log = self.run_call(_multi("GOOGLEDRIVE_TRASH_FILE", {"file_id": "SYN-W2-doc"}),
                                 actor="agent-1", env=SHD)
        self.assertEqual(out, "EXECUTED")
        self.assertIn("DENY", log)

    # --- cô lập ngữ cảnh team/Kanban ---
    def test_team_and_kanban_context_isolated(self):
        outer = tc.bind(tc.make("kanban", actor="agent-1"))
        try:
            self.assertEqual(h._actor(), "agent-1")
            inner = tc.bind(tc.make("team", actor="agent-2"))
            try:
                self.assertEqual(h._actor(), "agent-2")
            finally:
                tc.reset(inner)
            self.assertEqual(h._actor(), "agent-1")
        finally:
            tc.reset(outer)
        self.assertIsNone(h._actor())

    # --- phân tích bypass trực tiếp ---
    def test_direct_connector_deny_only_in_enforce(self):
        self.assertEqual(g.direct_deny_rules({}), [])
        self.assertEqual(g.direct_deny_rules(SHD), [])
        rules = g.direct_deny_rules(ENF)
        self.assertIn("mcp__claude_ai_Google_Drive", rules)
        self.assertIn("mcp__claude_ai_Google_Sheets", rules)


if __name__ == "__main__":
    unittest.main()
