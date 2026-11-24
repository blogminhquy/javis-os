"""Ngoại lệ phạm vi của cổng nhóm: chỉ tạo file văn bản trong WRITE_ROOT của CHÍNH actor, chỉ khi guard enforce.

Dữ liệu tổng hợp (SYN-*): không dùng ID Drive thật. Mọi trường hợp khác phải giữ waiting (gate trả False).
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stderr

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import drive_write_guard as g  # noqa: E402
import team_gate  # noqa: E402
import turn_context  # noqa: E402

ACCOUNT = "SYN-ACCOUNT"
OWN_A = "SYN-WRITE-A"
OWN_B = "SYN-WRITE-B"
SHARED = "SYN-SHARED"
GOV = "SYN-GOV"
TEAM = "tm_syn"
TASK = "t_syn"
LEADER_KEY = "ag_leader"
MEMBER_KEY = "ag_member"


def _sub(tool="GOOGLEDRIVE_CREATE_FILE_FROM_TEXT", account=ACCOUNT, parent=OWN_A, mime="text/plain",
         name="JAVIS_TEST_OWN_WRITE_X", text="JAVIS OWN WORKSPACE WRITE TEST", extra=None):
    a = {"file_name": name, "text_content": text, "mime_type": mime, "parent_id": parent}
    a.update(extra or {})
    return {"tool_slug": tool, "account": account, "arguments": a}


def _args(subs=None, tools_as=list):
    subs = [_sub()] if subs is None else subs
    if tools_as is str:
        return {"session_id": "s", "tools": repr(subs)}
    return {"session_id": "s", "tools": subs}


class _Store:
    """Roster và bước giả, đúng dạng trả về của team_store (members/step)."""

    def __init__(self, members, steps):
        self._members = members  # list of dicts
        self._steps = steps      # step_id -> dict

    def members(self, team_id, include_removed=False):
        return [m for m in self._members if m["team_id"] == team_id]

    def step(self, step_id):
        return self._steps.get(step_id)

    def consume_fingerprint(self, step_id, fp):
        return None


class ScopeExemptTests(unittest.TestCase):
    """Hàm thuần scope_exempt: không cần gate."""

    def setUp(self):
        self._saved = (dict(g.WRITE_ROOTS), dict(g.PROTECTED_ROOTS))
        g.WRITE_ROOTS.clear()
        g.WRITE_ROOTS.update({"agent-a": OWN_A, "agent-b": OWN_B})
        g.PROTECTED_ROOTS.clear()
        g.PROTECTED_ROOTS.update({"shared": SHARED, "governance": GOV})

    def tearDown(self):
        g.WRITE_ROOTS.clear()
        g.WRITE_ROOTS.update(self._saved[0])
        g.PROTECTED_ROOTS.clear()
        g.PROTECTED_ROOTS.update(self._saved[1])

    def ok(self, args, actor="agent-a", mode="enforce", account=ACCOUNT, tool="COMPOSIO_MULTI_EXECUTE_TOOL"):
        return g.scope_exempt(actor, tool, args, account, mode)[0]

    def test_own_root_create_allowed_in_enforce(self):
        self.assertTrue(self.ok(_args()))

    def test_string_tools_repr_allowed(self):
        self.assertTrue(self.ok(_args(tools_as=str)))

    def test_guard_off_or_shadow_never_exempt(self):
        self.assertFalse(self.ok(_args(), mode="off"))
        self.assertFalse(self.ok(_args(), mode="shadow"))

    def test_unknown_actor_denied(self):
        self.assertFalse(self.ok(_args(), actor=None))
        self.assertFalse(self.ok(_args(), actor="agent-z"))

    def test_wrong_folder_denied(self):
        self.assertFalse(self.ok(_args([_sub(parent=OWN_B)])))
        self.assertFalse(self.ok(_args([_sub(parent=SHARED)])))
        self.assertFalse(self.ok(_args([_sub(parent=GOV)])))
        self.assertFalse(self.ok(_args([_sub(parent=[OWN_A])])))

    def test_cross_agent_denied(self):
        self.assertFalse(self.ok(_args([_sub(parent=OWN_B)]), actor="agent-a"))

    def test_wrong_account_denied(self):
        self.assertFalse(self.ok(_args([_sub(account="SYN-OTHER")])))

    def test_no_configured_account_denied(self):
        self.assertFalse(self.ok(_args(), account=""))

    def test_non_create_tools_denied(self):
        for tool in ("GOOGLEDRIVE_TRASH_FILE", "GOOGLEDRIVE_UPDATE_FILE", "GOOGLEDRIVE_MOVE_FILE",
                     "GOOGLEDRIVE_CREATE_PERMISSION", "GOOGLEDRIVE_CREATE_FILE", "COMPOSIO_REMOTE_BASH_TOOL"):
            with self.subTest(tool=tool):
                self.assertFalse(self.ok(_args([_sub(tool=tool)])))

    def test_extra_arguments_denied(self):
        for extra in ({"driveId": "SYN-X"}, {"add_parents": OWN_B}, {"permissions": []}):
            with self.subTest(extra=extra):
                self.assertFalse(self.ok(_args([_sub(extra=extra)])))

    def test_non_plain_mime_denied(self):
        self.assertFalse(self.ok(_args([_sub(mime="application/vnd.google-apps.document")])))

    def test_multiple_subcalls_denied(self):
        self.assertFalse(self.ok(_args([_sub(), _sub()])))
        self.assertFalse(self.ok(_args([])))

    def test_unknown_top_level_keys_denied(self):
        a = _args()
        a["sync_response_to_workbench"] = True
        self.assertFalse(self.ok(a))

    def test_bad_filename_denied(self):
        for name in ("", "  ", "a/b", "..", "."):
            with self.subTest(name=name):
                self.assertFalse(self.ok(_args([_sub(name=name)])))

    def test_unparseable_tools_denied(self):
        self.assertFalse(self.ok({"session_id": "s", "tools": "__import__('os')"}))
        self.assertFalse(self.ok({"session_id": "s", "tools": "not a list"}))


class _Gate:
    """Bọc hub_check: bind turn với actor và khóa cổng, gọi đúng như hub."""

    def __init__(self, store, actor, step_id=f"st_{MEMBER_KEY}"):
        self.store = store
        self.actor = actor
        self.step_id = step_id
        self.gate = team_gate.open_gate(store, TEAM, TASK, step_id)

    def check(self, args, tool="COMPOSIO_MULTI_EXECUTE_TOOL"):
        turn = turn_context.make("team", chat_id=TEAM, team_gate=self.gate.gate_id, actor=self.actor or "")
        tok = turn_context.bind(turn)
        try:
            buf = io.StringIO()
            with redirect_stderr(buf):
                ok, why = team_gate.hub_check(tool, args, "syn")
            return ok, why, buf.getvalue()
        finally:
            turn_context.reset(tok)
            team_gate.close_gate(self.gate.gate_id)


class GateExemptionTests(unittest.TestCase):
    def setUp(self):
        self._saved = (dict(g.WRITE_ROOTS), dict(g.PROTECTED_ROOTS), g.COMPOSIO_ACCOUNT)
        g.WRITE_ROOTS.clear()
        g.WRITE_ROOTS.update({"agent-a": OWN_A, "agent-b": OWN_B})
        g.PROTECTED_ROOTS.clear()
        g.PROTECTED_ROOTS.update({"shared": SHARED, "governance": GOV})
        g.COMPOSIO_ACCOUNT = ACCOUNT
        self._env = os.environ.get(g.MODE_ENV)
        os.environ[g.MODE_ENV] = "enforce"
        self.members = [
            {"team_id": TEAM, "agent_key": LEADER_KEY, "slug_at_join": "agent-a", "status": "active"},
            {"team_id": TEAM, "agent_key": MEMBER_KEY, "slug_at_join": "agent-b", "status": "active"},
        ]
        self.steps = {f"st_{MEMBER_KEY}": {"step_id": f"st_{MEMBER_KEY}", "task_id": TASK,
                                           "agent_key": MEMBER_KEY},
                      f"st_{LEADER_KEY}": {"step_id": f"st_{LEADER_KEY}", "task_id": TASK,
                                           "agent_key": LEADER_KEY}}

    def tearDown(self):
        g.WRITE_ROOTS.clear()
        g.WRITE_ROOTS.update(self._saved[0])
        g.PROTECTED_ROOTS.clear()
        g.PROTECTED_ROOTS.update(self._saved[1])
        g.COMPOSIO_ACCOUNT = self._saved[2]
        if self._env is None:
            os.environ.pop(g.MODE_ENV, None)
        else:
            os.environ[g.MODE_ENV] = self._env

    def store(self):
        return _Store(self.members, self.steps)

    def test_allowed_when_roster_actor_own_root_enforce(self):
        ok, why, log = _Gate(self.store(), "agent-b").check(_args([_sub(parent=OWN_B)]))
        self.assertTrue(ok, why)
        self.assertIn("ngoại lệ phạm vi", log)

    def test_guard_off_stays_gated(self):
        os.environ[g.MODE_ENV] = "off"
        ok, why, _ = _Gate(self.store(), "agent-b").check(_args([_sub(parent=OWN_B)]))
        self.assertFalse(ok)

    def test_shadow_stays_gated(self):
        os.environ[g.MODE_ENV] = "shadow"
        ok, _, _ = _Gate(self.store(), "agent-b").check(_args([_sub(parent=OWN_B)]))
        self.assertFalse(ok)

    def test_spoofed_actor_not_in_roster_stays_gated(self):
        ok, _, _ = _Gate(self.store(), "agent-z").check(_args([_sub(parent=OWN_B)]))
        self.assertFalse(ok)

    def test_actor_not_running_this_step_stays_gated(self):
        # Actor là agent-a (leader) nhưng bước đang chạy là của agent-b: spoof qua tên, phải bị chặn.
        ok, _, _ = _Gate(self.store(), "agent-a", step_id=f"st_{MEMBER_KEY}").check(_args([_sub(parent=OWN_A)]))
        self.assertFalse(ok)

    def test_removed_member_stays_gated(self):
        self.members[1]["status"] = "removed"
        ok, _, _ = _Gate(self.store(), "agent-b").check(_args([_sub(parent=OWN_B)]))
        self.assertFalse(ok)

    def test_duplicate_roster_slug_stays_gated(self):
        self.members.append({"team_id": TEAM, "agent_key": "ag_dup", "slug_at_join": "agent-b", "status": "active"})
        ok, _, _ = _Gate(self.store(), "agent-b").check(_args([_sub(parent=OWN_B)]))
        self.assertFalse(ok)

    def test_single_leader_team_allowed(self):
        self.members = [self.members[0]]
        self.steps = {f"st_{LEADER_KEY}": {"step_id": f"st_{LEADER_KEY}", "task_id": TASK, "agent_key": LEADER_KEY}}
        ok, why, _ = _Gate(self.store(), "agent-a", step_id=f"st_{LEADER_KEY}").check(_args([_sub(parent=OWN_A)]))
        self.assertTrue(ok, why)

    def test_wrong_folder_cross_agent_shared_governance_stay_gated(self):
        for parent in (OWN_A, SHARED, GOV):
            with self.subTest(parent=parent):
                ok, _, _ = _Gate(self.store(), "agent-b").check(_args([_sub(parent=parent)]))
                self.assertFalse(ok)

    def test_wrong_account_stays_gated(self):
        ok, _, _ = _Gate(self.store(), "agent-b").check(_args([_sub(parent=OWN_B, account="SYN-OTHER")]))
        self.assertFalse(ok)

    def test_nested_unknown_or_destructive_stays_gated(self):
        for tool in ("GOOGLEDRIVE_TRASH_FILE", "GOOGLEDRIVE_UPDATE_FILE", "COMPOSIO_REMOTE_WORKBENCH"):
            with self.subTest(tool=tool):
                ok, _, _ = _Gate(self.store(), "agent-b").check(_args([_sub(tool=tool, parent=OWN_B)]))
                self.assertFalse(ok)

    def test_non_multi_top_level_tool_stays_gated(self):
        ok, _, _ = _Gate(self.store(), "agent-b").check({"file_id": "x"}, tool="GOOGLEDRIVE_TRASH_FILE")
        self.assertFalse(ok)

    def test_no_gate_bound_stays_denied(self):
        ok, _ = team_gate.hub_check("COMPOSIO_MULTI_EXECUTE_TOOL", _args(), "syn")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
