"""Duyệt ngoại lệ phạm vi Drive: chủ duyệt ĐÚNG một lệnh ghi ngoài vùng cho ĐÚNG một bước, dùng một lần, có hạn.

Dữ liệu tổng hợp (SYN-*). Test end-to-end chạy qua drive_guard_hub.wrap thật + ApprovalStore SQLite thật.
Metadata Drive thật (tùy chọn) đọc từ file cục bộ ngoài repo qua JAVIS_DRIVE_META_FIXTURE; không có -> bỏ qua.
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import drive_guard_hub as dhub  # noqa: E402
import drive_write_guard as g  # noqa: E402
import team_approval  # noqa: E402
import team_gate  # noqa: E402
import turn_context  # noqa: E402

ACCOUNT = "SYN-ACCOUNT"
OWN = "SYN-OWN-AFF"
OWN_CHILD = "SYN-OWN-AFF-CHILD"
OUT = "SYN-OUTSIDE"
OUT2 = "SYN-OUTSIDE-2"
ACTOR = "alex-manager-affiliate"
OTHER = "alex-learning-coach"
TEAM, TASK = "tm_syn", "t_syn"
ENV_ON = {g.MODE_ENV: "enforce", g.PILOT_ENV: "alex-manager-affiliate"}


class _Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class _Store(team_approval.ApprovalStore):
    """ApprovalStore thật + roster/bước giả đúng dạng của team_store."""

    def __init__(self, path, clock, members, steps):
        super().__init__(path, clock=clock)
        self._members, self._steps = members, steps

    def members(self, team_id, include_removed=False):
        return [m for m in self._members if m["team_id"] == team_id]

    def step(self, step_id):
        return self._steps.get(step_id)


def _member(slug, key):
    return {"team_id": TEAM, "status": "active", "slug_at_join": slug, "agent_key": key}


class _Base(unittest.TestCase):
    def setUp(self):
        self._saved = (dict(g.WRITE_ROOTS), dict(g.PROTECTED_ROOTS), g.COMPOSIO_ACCOUNT)
        g.WRITE_ROOTS.clear()
        g.WRITE_ROOTS[ACTOR] = OWN
        g.WRITE_ROOTS[OTHER] = "SYN-OWN-LEARN"
        g.PROTECTED_ROOTS.clear()
        g.PROTECTED_ROOTS["shared"] = "SYN-SHARED"
        g.COMPOSIO_ACCOUNT = ACCOUNT
        self.clock = _Clock()
        self.tmp = tempfile.TemporaryDirectory()
        self.store = _Store(os.path.join(self.tmp.name, "team.sqlite3"), self.clock,
                            members=[_member(ACTOR, "ag_aff"), _member(OTHER, "ag_learn")],
                            steps={"st_a": {"task_id": TASK, "agent_key": "ag_aff"},
                                   "st_b": {"task_id": TASK, "agent_key": "ag_learn"}})
        self.gate = team_gate.open_gate(self.store, TEAM, TASK, "st_a")
        self.tok = turn_context.bind({"actor": ACTOR, "team_gate": self.gate.gate_id})
        self.parents = {OWN_CHILD: [OWN], OWN: ["SYN-ROOT"], OUT: ["SYN-OTHER"], OUT2: ["SYN-OTHER"],
                        "SYN-OTHER": ["SYN-ROOT"]}

    def tearDown(self):
        turn_context.reset(self.tok)
        team_gate.close_gate(self.gate.gate_id)
        g.WRITE_ROOTS.clear()
        g.WRITE_ROOTS.update(self._saved[0])
        g.PROTECTED_ROOTS.clear()
        g.PROTECTED_ROOTS.update(self._saved[1])
        g.COMPOSIO_ACCOUNT = self._saved[2]
        self.tmp.cleanup()

    def pf(self, fid):
        return list(self.parents.get(fid, []))

    def trash(self, fid):
        return {"tools": [{"tool_slug": "GOOGLEDRIVE_TRASH_FILE", "account": ACCOUNT, "arguments": {"file_id": fid}}]}

    def approve_blocked(self, step="st_a", decision_key="k1", blocked_fp=None):
        """Chủ duyệt ĐÚNG fingerprint đã bị chặn của lệnh vừa thử (như nút trên thẻ duyệt)."""
        fp = blocked_fp or [b["fp"] for b in self.gate.blocked if b["kind"] == team_gate.DRIVE_KIND][-1]
        label = [b["label"] for b in self.gate.blocked if b["fp"] == fp][0]
        ap = self.store.create(team_id=TEAM, task_id=TASK, step_id=step, team_rev=1, requested_by=ACTOR,
                               kind="action", title="Ghi ngoài vùng", action=label,
                               deadline_at=self.clock.t + 600,
                               fingerprints=[{"fp": fp, "label": label, "call": ""}])
        r = self.store.decide(ap["approval_id"], "approve", by="owner", decision_key=decision_key)
        self.assertTrue(r["ok"], r)
        self.store.granted_step(ap["approval_id"], step)
        return ap["approval_id"]


class PolicyTests(_Base):
    def test_outside_write_is_approvable_and_not_allowed(self):
        d = g.decide(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": OUT}, self.pf)
        self.assertFalse(d["allow"])
        self.assertTrue(d.get("approvable"))

    def test_fail_closed_denials_are_not_approvable(self):
        for tool, args in [("COMPOSIO_REMOTE_BASH_TOOL", {}), ("COMPOSIO_PROXY_EXECUTE", {"method": "POST"}),
                           ("GOOGLEDOCS_CREATE_DOCUMENT", {}), ("COMPOSIO_NEW_THING", {}),
                           ("GOOGLEDRIVE_TRASH_FILE", {"file_id": ""})]:
            d = g.decide(ACTOR, tool, args, self.pf)
            self.assertFalse(d["allow"], tool)
            self.assertFalse(d.get("approvable"), tool)

    def test_multi_with_two_subcalls_is_never_approvable(self):
        args = {"tools": [{"tool_slug": "GOOGLEDRIVE_TRASH_FILE", "account": ACCOUNT, "arguments": {"file_id": OUT}},
                          {"tool_slug": "GOOGLEDRIVE_TRASH_FILE", "account": ACCOUNT, "arguments": {"file_id": OUT2}}]}
        d = g.decide(ACTOR, "COMPOSIO_MULTI_EXECUTE_TOOL", args, self.pf)
        self.assertFalse(d["allow"])
        self.assertFalse(d.get("approvable"))

    def test_single_subcall_multi_inherits_approvable(self):
        d = g.decide(ACTOR, "COMPOSIO_MULTI_EXECUTE_TOOL", self.trash(OUT), self.pf)
        self.assertFalse(d["allow"])
        self.assertTrue(d.get("approvable"))

    def test_pilot_filter(self):
        self.assertFalse(g.outside_pilot(ACTOR, {}))                       # chưa đặt: mọi actor được quyết định
        env = {g.PILOT_ENV: ACTOR}
        self.assertFalse(g.outside_pilot(ACTOR, env))
        self.assertTrue(g.outside_pilot(OTHER, env))                       # chuyên viên ngoài đợt: không can thiệp
        self.assertFalse(g.outside_pilot(None, env))                       # không rõ actor: KHÔNG bao giờ bỏ qua


class ApprovalFlowTests(_Base):
    def _block_then_approve(self, args, decision_key="k1"):
        ok, note, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", args, "trash")
        self.assertFalse(ok)
        return self.approve_blocked(decision_key=decision_key)

    def test_exact_call_passes_once_then_replay_is_refused(self):
        args = self.trash(OUT)
        self._block_then_approve(args)
        ok, _, hub_fp = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", args)
        self.assertTrue(ok)
        self.assertEqual(hub_fp, team_approval.fingerprint("hub", "fn1", args))
        ok2, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", args)
        self.assertFalse(ok2, "replay must be refused")

    def test_parameter_swap_is_refused(self):
        self._block_then_approve(self.trash(OUT))
        ok, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", self.trash(OUT2))
        self.assertFalse(ok)

    def test_wrong_step_is_refused(self):
        self._block_then_approve(self.trash(OUT))
        other = team_gate.open_gate(self.store, TEAM, TASK, "st_b")
        tok = turn_context.bind({"actor": OTHER, "team_gate": other.gate_id})
        try:
            ok, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", self.trash(OUT))
            self.assertFalse(ok)
        finally:
            turn_context.reset(tok)
            team_gate.close_gate(other.gate_id)

    def test_wrong_actor_is_refused(self):
        self._block_then_approve(self.trash(OUT))
        tok = turn_context.bind({"actor": OTHER, "team_gate": self.gate.gate_id})
        try:
            ok, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", self.trash(OUT))
            self.assertFalse(ok)
        finally:
            turn_context.reset(tok)

    def test_expired_approval_is_refused(self):
        args = self.trash(OUT)
        ok, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", args)
        self.assertFalse(ok)
        fp = [b["fp"] for b in self.gate.blocked if b["kind"] == team_gate.DRIVE_KIND][-1]
        ap = self.store.create(team_id=TEAM, task_id=TASK, step_id="st_a", team_rev=1, requested_by=ACTOR,
                               kind="action", title="t", action="a", deadline_at=self.clock.t + 60,
                               fingerprints=[{"fp": fp, "label": "x", "call": ""}])
        self.assertTrue(self.store.decide(ap["approval_id"], "approve", by="owner", decision_key="kx")["ok"])
        self.store.granted_step(ap["approval_id"], "st_a")
        self.clock.t += 120                      # quá hạn trước khi lệnh được chạy
        ok, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", args)
        self.assertFalse(ok)

    def test_generic_gated_approval_does_not_authorize_drive_scope(self):
        args = self.trash(OUT)
        team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", args)
        generic_fp = team_approval.fingerprint("hub", "GOOGLEDRIVE_TRASH_FILE", args)
        ap = self.store.create(team_id=TEAM, task_id=TASK, step_id="st_a", team_rev=1, requested_by=ACTOR,
                               kind="action", title="t", action="a",
                               fingerprints=[{"fp": generic_fp, "label": "x", "call": ""}])
        self.store.decide(ap["approval_id"], "approve", by="owner", decision_key="kg")
        self.store.granted_step(ap["approval_id"], "st_a")
        ok, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", args)
        self.assertFalse(ok)

    def test_approved_flag_in_args_never_grants(self):
        self._block_then_approve(self.trash(OUT))
        forged = self.trash(OUT)
        forged["approved"] = True
        ok, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", forged)
        self.assertFalse(ok)

    def test_hub_check_passes_only_with_matching_drive_pass(self):
        args = self.trash(OUT)
        fp = team_approval.fingerprint("hub", "fn1", args)
        tok = team_gate.DRIVE_PASS.set(fp)
        try:
            self.assertEqual(team_gate.hub_check("fn1", args), (True, ""))
            self.assertIsNotNone(team_gate.DRIVE_PASS.get())
            ok, _ = team_gate.hub_check("fn1", self.trash(OUT2))   # khác args: vẫn đi đường gated thường
            self.assertFalse(ok)
        finally:
            team_gate.DRIVE_PASS.reset(tok)


class EndToEndHubTests(_Base):
    """Chạy qua drive_guard_hub.wrap thật: DENY -> thẻ duyệt -> ALLOW một lần -> lặp lại bị chặn."""

    def setUp(self):
        super().setUp()
        self._prefetch = dhub.prefetch_parents
        dhub.prefetch_parents = self._fake_prefetch
        self.calls = []

    def tearDown(self):
        dhub.prefetch_parents = self._prefetch
        super().tearDown()

    async def _fake_prefetch(self, seeds):
        cache = {k: self.pf(k) for k in list(self.parents) + list(seeds)}
        cache["SYN-ROOT"] = []                  # gốc Drive giả: không có cha
        return cache

    def _run(self, args, env=ENV_ON):
        async def call(a):
            self.calls.append(a)
            return "OK"
        wrapped = dhub.wrap(call, {"connector_id": "composio"}, "COMPOSIO_MULTI_EXECUTE_TOOL", "fn1", env=env)
        return asyncio.run(wrapped(args))

    def test_deny_then_owner_exact_approval_then_one_use(self):
        args = self.trash(OUT)
        r1 = self._run(args)
        self.assertTrue(str(r1).startswith("ERROR:"), r1)
        self.assertEqual(self.calls, [])
        self.approve_blocked(decision_key="e2e-1")
        r2 = self._run(args)
        self.assertEqual(r2, "OK")
        self.assertEqual(len(self.calls), 1)
        r3 = self._run(args)
        self.assertTrue(str(r3).startswith("ERROR:"), r3)
        self.assertEqual(len(self.calls), 1, "replay must not reach the tool")

    def _run_with(self, args, call):
        wrapped = dhub.wrap(call, {"connector_id": "composio"}, "COMPOSIO_MULTI_EXECUTE_TOOL", "fn1", env=ENV_ON)
        return asyncio.run(wrapped(args))

    def test_failed_composio_call_burns_approval_and_is_not_retried(self):
        args = self.trash(OUT)
        self._run(args)                                   # lần 1: bị chặn, sinh thẻ duyệt
        self.approve_blocked(decision_key="fail-1")
        attempts = []

        async def boom(a):
            attempts.append(a)
            raise RuntimeError("composio 500")
        with self.assertRaises(RuntimeError):
            self._run_with(args, boom)
        self.assertEqual(len(attempts), 1)
        r = self._run(args)                               # thử lại cùng lệnh: phải bị chặn, không tự gọi lại
        self.assertTrue(str(r).startswith("ERROR:"), r)
        self.assertEqual(self.calls, [], "retry must not reach the tool")
        row = self.store._conn().execute("SELECT status FROM team_approvals").fetchone()
        self.assertEqual(row[0], "consumed")

    def test_error_envelope_from_composio_also_burns_approval(self):
        args = self.trash(OUT)
        self._run(args)
        self.approve_blocked(decision_key="fail-2")

        async def envelope(a):
            return "ERROR: composio 403"
        out = self._run_with(args, envelope)
        self.assertEqual(out, "ERROR: composio 403")
        r = self._run(args)
        self.assertTrue(str(r).startswith("ERROR:"), r)
        self.assertEqual(self.calls, [])

    def test_approval_for_one_file_does_not_open_another(self):
        self._run(self.trash(OUT))
        self.approve_blocked(decision_key="e2e-2")
        r = self._run(self.trash(OUT2))
        self.assertTrue(str(r).startswith("ERROR:"), r)
        self.assertEqual(self.calls, [])

    def test_no_gate_no_approval_path(self):
        turn_context.reset(self.tok)
        team_gate.close_gate(self.gate.gate_id)
        try:
            r = self._run(self.trash(OUT))
            self.assertTrue(str(r).startswith("ERROR:"), r)
            self.assertEqual(self.calls, [])
        finally:
            self.tok = turn_context.bind({"actor": ACTOR, "team_gate": self.gate.gate_id})

    def test_outside_pilot_actor_is_untouched(self):
        env = {g.MODE_ENV: "enforce", g.PILOT_ENV: "someone-else"}
        self.assertEqual(self._run(self.trash(OUT), env=env), "OK")


class SecurityHardeningTests(_Base):
    """Race đồng thời, hạn bắt buộc, metadata thiếu, opaque lồng trong multi."""

    def _approve_with_deadline(self, args, deadline, key):
        ok, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", args)
        self.assertFalse(ok)
        fp = [b["fp"] for b in self.gate.blocked if b["kind"] == team_gate.DRIVE_KIND][-1]
        ap = self.store.create(team_id=TEAM, task_id=TASK, step_id="st_a", team_rev=1, requested_by=ACTOR,
                               kind="action", title="t", action="a", deadline_at=deadline,
                               fingerprints=[{"fp": fp, "label": "x", "call": ""}])
        self.assertTrue(self.store.decide(ap["approval_id"], "approve", by="owner", decision_key=key)["ok"])
        self.store.granted_step(ap["approval_id"], "st_a")

    def test_approval_without_deadline_is_refused_for_drive_scope(self):
        self._approve_with_deadline(self.trash(OUT), None, "nd")
        ok, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", self.trash(OUT))
        self.assertFalse(ok)

    def test_zero_deadline_is_refused(self):
        self._approve_with_deadline(self.trash(OUT), 0, "zd")
        ok, _, _ = team_gate.drive_scope_check("fn1", "GOOGLEDRIVE_TRASH_FILE", self.trash(OUT))
        self.assertFalse(ok)

    def test_concurrent_consumers_one_winner(self):
        import threading
        args = self.trash(OUT)
        self._approve_with_deadline(args, self.clock.t + 600, "race")
        fp = team_approval.fingerprint("drive-scope", "GOOGLEDRIVE_TRASH_FILE", args)
        wins, lock, barrier = [], threading.Lock(), threading.Barrier(12)

        def worker():
            barrier.wait()
            aid = self.store.consume_fingerprint("st_a", fp, need_deadline=True)
            with lock:
                wins.append(aid)

        ts = [threading.Thread(target=worker) for _ in range(12)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(sum(1 for w in wins if w), 1, wins)

    def test_missing_metadata_fails_closed(self):
        def boom(fid):
            raise RuntimeError("metadata down")
        d = g.decide(ACTOR, "GOOGLEDRIVE_TRASH_FILE", {"file_id": OUT}, boom)
        self.assertFalse(d["allow"])
        self.assertFalse(d.get("approvable"))

    def test_opaque_exec_inside_multi_is_not_approvable(self):
        args = {"tools": [{"tool_slug": "COMPOSIO_REMOTE_BASH_TOOL", "account": ACCOUNT, "arguments": {}}]}
        d = g.decide(ACTOR, "COMPOSIO_MULTI_EXECUTE_TOOL", args, self.pf)
        self.assertFalse(d["allow"])
        self.assertFalse(d.get("approvable"))


class RealMetadataFixtureTests(unittest.TestCase):
    """Chỉ chạy khi có fixture metadata Drive thật ở ngoài repo (không commit ID thật)."""

    def test_real_parent_chain_scope(self):
        path = os.environ.get("JAVIS_DRIVE_META_FIXTURE")
        if not path or not os.path.isfile(path):
            self.skipTest("no local Drive metadata fixture")
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)  # {"<id>": {"parentId": "<id>", "title": "..."}}
        def pf(fid):
            p = (meta.get(fid) or {}).get("parentId")
            return [p] if p else []
        own = meta["__own__"]["id"]
        shared = meta["__shared__"]["id"]
        self.assertTrue(g._all_within(own, own, pf))
        self.assertFalse(g._all_within(shared, own, pf))   # Shared không nằm dưới WRITE_ROOT của Agent


if __name__ == "__main__":
    unittest.main()
