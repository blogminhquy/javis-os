import asyncio
import io
import unittest
from contextlib import redirect_stderr

import drive_guard_hub as h
import drive_parents as dp
import drive_write_guard as g

# Dữ liệu tổng hợp: cấu hình thật (ID, account) nằm ở drive_guard.local.json, không nằm trong repo.
g.COMPOSIO_ACCOUNT = "SYN-ACCOUNT"
g.WRITE_ROOTS.clear()
g.WRITE_ROOTS.update({"agent-a": "SYN-WRITE-A", "agent-b": "SYN-WRITE-B"})
g.PROTECTED_ROOTS.clear()
g.PROTECTED_ROOTS.update({"root": "SYN-ROOT", "governance": "SYN-GOV", "shared": "SYN-SHARED",
                          "inbox": "SYN-INBOX", "archive": "SYN-ARCHIVE"})

ENV_OFF = {}
ENV_SHADOW = {"JAVIS_DRIVE_WRITE_GUARD": "shadow"}
ENV_ENFORCE = {"JAVIS_DRIVE_WRITE_GUARD": "enforce"}
COMPOSIO = {"connector_id": "composio"}
WRITE = "COMPOSIO_MULTI_EXECUTE_TOOL"
OWN = g.WRITE_ROOTS["agent-a"]
OTHER = g.WRITE_ROOTS["agent-b"]
GOV = g.PROTECTED_ROOTS["governance"]
TOP = "SYN-TOP"

def _meta(fid, parents, trashed=False, mime="application/vnd.google-apps.folder"):
    return {"id": fid, "name": fid, "mimeType": mime, "parents": parents, "trashed": trashed}


def _envelope(meta):
    return {"successful": True, "data": {"results": [{"response": {"successful": True, "data": meta}}]}}


class FakeDrive:
    """Invoker giả: trả envelope Composio thật cho từng id; đếm số lần gọi."""

    def __init__(self, files, fail=False):
        self.files, self.fail, self.calls = files, fail, 0

    async def __call__(self, args):
        self.calls += 1
        if self.fail:
            return {"successful": False, "error": "auth"}
        fid = args["tools"][0]["arguments"]["fileId"]
        if fid not in self.files:
            return {"successful": True, "data": {"results": [{"response": {"successful": False}}]}}
        return _envelope(self.files[fid])


def _tree():
    files = {TOP: _meta(TOP, [])}
    files[OWN] = _meta(OWN, [TOP])
    files[OTHER] = _meta(OTHER, [TOP])
    files["own-sub"] = _meta("own-sub", [OWN])
    files["OTHER_SUB"] = _meta("OTHER_SUB", [OTHER])
    files["GOV_ITEM"] = _meta("GOV_ITEM", [GOV])
    files["ORPHAN"] = _meta("ORPHAN", ["NOWHERE"])
    return files


def _run(coro):
    return asyncio.run(coro)


def _call_log():
    calls = []

    async def call(args):
        calls.append(args)
        return "REAL"
    return call, calls


def _write(file_id, tool="GOOGLEDRIVE_TRASH_FILE", extra=None):
    arguments = {"file_id": file_id}
    arguments.update(extra or {})
    return {"tools": [{"tool_slug": tool, "arguments": arguments}]}


class HubGuardTests(unittest.TestCase):
    def setUp(self):
        self.drive = FakeDrive(_tree())
        h.register_invoker(self.drive)
        self.actor = "agent-a"
        from unittest import mock
        self._p = mock.patch.object(h, "_actor", side_effect=lambda: self.actor)
        self._p.start()

    def tearDown(self):
        self._p.stop()
        h.register_invoker(None)

    def _go(self, args, env=ENV_ENFORCE, actor="agent-a", tool=WRITE):
        self.actor = actor
        call, calls = _call_log()
        wrapped = h.wrap(call, COMPOSIO, tool, "fn", env=env)
        buf = io.StringIO()
        with redirect_stderr(buf):
            out = _run(wrapped(args))
        return out, calls, buf.getvalue()

    def test_missing_account_config_fails_closed(self):
        saved = g.COMPOSIO_ACCOUNT
        g.COMPOSIO_ACCOUNT = ""
        try:
            out, calls, _ = self._go(_write("own-sub"))
        finally:
            g.COMPOSIO_ACCOUNT = saved
        self.assertTrue(out.startswith("ERROR:"))
        self.assertEqual(calls, [])

    def test_off_returns_original_call(self):
        call, _ = _call_log()
        self.assertIs(h.wrap(call, COMPOSIO, WRITE, "fn", env=ENV_OFF), call)

    def test_own_nested_file_allowed_in_enforce(self):
        out, calls, log = self._go(_write("own-sub"))
        self.assertEqual(out, "REAL")
        self.assertEqual(len(calls), 1)
        self.assertIn("ALLOW", log)

    def test_cross_root_denied_and_tool_not_called(self):
        out, calls, log = self._go(_write("OTHER_SUB"))
        self.assertTrue(out.startswith("ERROR: Javis chặn"))
        self.assertEqual(calls, [])
        self.assertIn("DENY", log)

    def test_governance_denied(self):
        out, calls, _ = self._go(_write("GOV_ITEM"))
        self.assertTrue(out.startswith("ERROR:"))
        self.assertEqual(calls, [])

    def test_orphan_ancestry_denied(self):
        out, calls, _ = self._go(_write("ORPHAN"))
        self.assertTrue(out.startswith("ERROR:"))
        self.assertEqual(calls, [])

    def test_shadow_calls_through_but_logs_deny(self):
        out, calls, log = self._go(_write("OTHER_SUB"), env=ENV_SHADOW)
        self.assertEqual(out, "REAL")
        self.assertIn("DENY", log)

    def test_invoker_failure_fails_closed(self):
        self.drive.fail = True
        out, calls, _ = self._go(_write("own-sub"))
        self.assertTrue(out.startswith("ERROR:"))
        self.assertEqual(calls, [])

    def test_unknown_id_fails_closed(self):
        out, calls, _ = self._go(_write("NOT_IN_DRIVE"))
        self.assertTrue(out.startswith("ERROR:"))
        self.assertEqual(calls, [])

    def test_missing_invoker_fails_closed(self):
        h.register_invoker(None)
        out, calls, _ = self._go(_write("own-sub"))
        self.assertTrue(out.startswith("ERROR:"))
        self.assertEqual(calls, [])

    def test_unknown_actor_denied(self):
        out, calls, _ = self._go(_write("own-sub"), actor=None)
        self.assertTrue(out.startswith("ERROR:"))
        self.assertEqual(calls, [])

    def test_trashed_ancestor_denied(self):
        self.drive.files["own-sub"] = _meta("own-sub", [OWN], trashed=True)
        out, calls, _ = self._go(_write("own-sub"))
        self.assertTrue(out.startswith("ERROR:"))
        self.assertEqual(calls, [])

    def test_read_tool_does_not_fetch_metadata(self):
        before = self.drive.calls
        out, calls, _ = self._go({"tools": [{"tool_slug": "GOOGLEDRIVE_LIST_FILES",
                                             "arguments": {"folderId": "anything"}}]})
        self.assertEqual(out, "REAL")
        self.assertEqual(self.drive.calls, before)

    def test_fetch_count_is_bounded(self):
        # chuỗi cha vô hạn -> phải dừng ở MAX_NODES và DENY, không đệ quy mãi
        for i in range(200):
            self.drive.files[f"loop{i}"] = _meta(f"loop{i}", [f"loop{i + 1}"])
        out, calls, _ = self._go(_write("loop0"))
        self.assertTrue(out.startswith("ERROR:"))
        self.assertLessEqual(self.drive.calls, h.MAX_NODES + 1)


if __name__ == "__main__":
    unittest.main()
