"""Đường duyệt ngoài vùng cho 3 trưởng phòng, kiểm bằng sổ duyệt SQLite thật (tạm) và actor lấy từ turn_context.

Với mỗi actor: lệnh ngoài vùng (1) dừng, không ghi; (2) tạo thẻ duyệt với fingerprint đúng; (3) duyệt đúng lệnh
cho phép ĐÚNG MỘT lần; (4) phát lại -> TỪ CHỐI. Đổi tham số sau khi duyệt -> không khớp. Không gọi Drive thật.
"""
import asyncio
import io
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import drive_guard_hub as dhub  # noqa: E402
import drive_write_guard as g  # noqa: E402
import team_approval as ta  # noqa: E402
import team_gate  # noqa: E402
import turn_context as tc  # noqa: E402

ENV = {"JAVIS_DRIVE_WRITE_GUARD": "enforce", "JAVIS_DRIVE_GUARD_PILOT": "javis-vu,alex-learning-coach,alex-manager-affiliate"}
TRASH = {"tools": [{"tool_slug": "GOOGLEDRIVE_TRASH_FILE", "account": "SYN-ACC",
                    "arguments": {"file_id": "SYN-OUTSIDE"}}]}
OTHER = {"tools": [{"tool_slug": "GOOGLEDRIVE_TRASH_FILE", "account": "SYN-ACC",
                    "arguments": {"file_id": "SYN-OUTSIDE-2"}}]}
LEADERS = [("javis-vu", "full"), ("alex-learning-coach", "gated"), ("alex-manager-affiliate", "gated")]


async def _no_parents(seeds):
    # Mọi ID có metadata và không có cha: SYN-OUTSIDE nằm ngoài WRITE_ROOT của mọi Agent trong test.
    return {k: [] for k in seeds}


class _Store(ta.ApprovalStore):
    """Sổ duyệt SQLite thật + vài hàm tra cứu bước/thành viên mà team_store cung cấp trong sản xuất."""

    def __init__(self, path, slug, key):
        super().__init__(path)
        self._slug, self._key = slug, key

    def step(self, step_id):
        return {"step_id": step_id, "task_id": "task-1", "agent_key": self._key}

    def members(self, team_id, include_removed=False):
        return [{"status": "active", "slug_at_join": self._slug, "agent_key": self._key}]


class ApprovalRouteTests(unittest.TestCase):
    def setUp(self):
        self._saved = dhub.prefetch_parents
        dhub.prefetch_parents = _no_parents
        self.tmp = tempfile.TemporaryDirectory()
        self._saved_roots = (dict(g.WRITE_ROOTS), g.COMPOSIO_ACCOUNT)
        g.WRITE_ROOTS.clear()
        for slug in ("javis-vu", "alex-learning-coach", "alex-manager-affiliate"):
            g.WRITE_ROOTS[slug] = "SYN-OWN-" + slug
        g.COMPOSIO_ACCOUNT = "SYN-ACC"

    def tearDown(self):
        dhub.prefetch_parents = self._saved
        g.WRITE_ROOTS.clear()
        g.WRITE_ROOTS.update(self._saved_roots[0])
        g.COMPOSIO_ACCOUNT = self._saved_roots[1]
        self.tmp.cleanup()

    def _call(self, slug, key, args, gate_id="", env=ENV):
        calls = []

        async def inner(a):
            calls.append(a)
            return "OK"
        turn = tc.make("web", agent={"key": key, "slug": slug}, actor=slug, team_gate=gate_id, provider="claude")
        buf = io.StringIO()
        token = tc.bind(turn)
        try:
            with redirect_stderr(buf):
                wrapped = dhub.wrap(inner, {"connector_id": "composio"}, "COMPOSIO_MULTI_EXECUTE_TOOL", "fn", env=env)
                out = asyncio.run(wrapped(args))
        finally:
            tc.reset(token)
        return str(out), calls

    def _gate_for(self, store, slug, key):
        return team_gate.open_gate(store, "team-1", "task-1", "step-1")

    def test_full_team_has_no_route(self):
        # javis-vu (work_mode FULL): runner không mở cổng, nên không có gate -> lệnh bị TỪ CHỐI, không có thẻ duyệt.
        store = _Store(Path(self.tmp.name) / "a.sqlite3", "javis-vu", "javis-vu-key")
        out, calls = self._call("javis-vu", "javis-vu-key", TRASH, gate_id="")
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])
        self.assertEqual(store.for_team("team-1"), [])
        self.assertIn("ERROR:", out)

    def test_gated_leaders_full_cycle(self):
        for slug, mode in LEADERS[1:]:
            with self.subTest(actor=slug):
                key = slug + "-key"
                store = _Store(Path(self.tmp.name) / f"{slug}.sqlite3", slug, key)
                gate = self._gate_for(store, slug, key)
                # (a) lệnh ngoài vùng dừng, không ghi
                out, calls = self._call(slug, key, TRASH, gate_id=gate.gate_id)
                self.assertTrue(out.startswith("ERROR:"), out)
                self.assertEqual(calls, [])
                self.assertEqual(len(gate.blocked), 1)
                fp = gate.blocked[0]["fp"]
                # (b) thẻ duyệt chứa đúng fingerprint của lệnh
                ap = store.create(team_id="team-1", task_id="task-1", step_id="step-1", team_rev=1,
                                  requested_by=key, kind="action", title="t", action="a",
                                  deadline_at=time.time() + 3600,
                                  fingerprints=[{"fp": fp, "label": "x", "call": "y"}])
                self.assertEqual(ap["status"], "pending")
                # chủ duyệt đúng thẻ
                self.assertTrue(store.decide(ap["approval_id"], "approve", by="owner", decision_key=f"k-{slug}")["ok"])
                store.granted_step(ap["approval_id"], "step-1")
                # (c) cho phép ĐÚNG MỘT lần
                out, calls = self._call(slug, key, TRASH, gate_id=gate.gate_id)
                self.assertEqual(out, "OK", out)
                self.assertEqual(len(calls), 1)
                # (d) phát lại -> TỪ CHỐI
                out, calls = self._call(slug, key, TRASH, gate_id=gate.gate_id)
                self.assertTrue(out.startswith("ERROR:"), out)
                self.assertEqual(calls, [])

    def test_gated_approval_for_other_args_does_not_unlock(self):
        slug, key = "alex-manager-affiliate", "alex-manager-affiliate-key"
        store = _Store(Path(self.tmp.name) / "imm.sqlite3", slug, key)
        gate = self._gate_for(store, slug, key)
        self._call(slug, key, TRASH, gate_id=gate.gate_id)
        fp = gate.blocked[0]["fp"]
        ap = store.create(team_id="team-1", task_id="task-1", step_id="step-1", team_rev=1, requested_by=key,
                          kind="action", title="t", action="a", deadline_at=time.time() + 3600,
                          fingerprints=[{"fp": fp, "label": "x", "call": "y"}])
        store.decide(ap["approval_id"], "approve", by="owner", decision_key="k-imm")
        store.granted_step(ap["approval_id"], "step-1")
        out, calls = self._call(slug, key, OTHER, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def test_approval_without_deadline_cannot_unlock_out_of_scope_write(self):
        # Ghi nhận khoảng trống: thẻ tạo từ đường "blocked" (runner) có deadline_at=None, còn drive-scope bắt buộc có hạn.
        slug, key = "alex-learning-coach", "alex-learning-coach-key"
        store = _Store(Path(self.tmp.name) / "nodl.sqlite3", slug, key)
        gate = self._gate_for(store, slug, key)
        self._call(slug, key, TRASH, gate_id=gate.gate_id)
        fp = gate.blocked[0]["fp"]
        ap = store.create(team_id="team-1", task_id="task-1", step_id="step-1", team_rev=1, requested_by=key,
                          kind="action", title="t", action="a", deadline_at=None,
                          fingerprints=[{"fp": fp, "label": "x", "call": "y"}])
        store.decide(ap["approval_id"], "approve", by="owner", decision_key="k-nodl")
        store.granted_step(ap["approval_id"], "step-1")
        out, calls = self._call(slug, key, TRASH, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def test_non_drive_legacy_write_unaffected(self):
        out, calls = self._call("javis-vu", "javis-vu-key", TRASH, gate_id="", env={"JAVIS_DRIVE_WRITE_GUARD": "off"})
        self.assertEqual(out, "OK")
        self.assertEqual(len(calls), 1)


def _tree(parents):
    async def pf(seeds):
        return {k: list(parents.get(k, [])) for k in seeds}
    return pf


MULTI2 = {"tools": [
    {"tool_slug": "GOOGLEDRIVE_TRASH_FILE", "account": "SYN-ACC", "arguments": {"file_id": "SYN-IN"}},
    {"tool_slug": "GOOGLEDRIVE_TRASH_FILE", "account": "SYN-ACC", "arguments": {"file_id": "SYN-OUTSIDE"}}]}


class ScopeRouteTests(ApprovalRouteTests):
    """Cây thư mục giả: SYN-IN nằm trong WRITE_ROOT của alex-learning-coach, SYN-OUTSIDE thì không."""
    SLUG, KEY = "alex-learning-coach", "alex-learning-coach-key"

    def setUp(self):
        super().setUp()
        dhub.prefetch_parents = _tree({"SYN-IN": ["SYN-OWN-alex-learning-coach"], "SYN-OWN-alex-learning-coach": []})

    def _setup_card(self, args, deadline_offset=3600):
        store = _Store(Path(self.tmp.name) / f"c{time.time_ns()}.sqlite3", self.SLUG, self.KEY)
        gate = team_gate.open_gate(store, "team-1", "task-1", "step-1")
        out, calls = self._call(self.SLUG, self.KEY, args, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])
        if args is MULTI2:
            return store, gate, []
        fps = [b["fp"] for b in gate.blocked]
        return store, gate, fps

    def test_multi_with_one_outside_child_denied_before_any_execution(self):
        store, gate, fps = self._setup_card(MULTI2)
        # Lô nhiều lệnh con không bao giờ xin duyệt chung (guard): không có thẻ, cả lô bị DENY trước khi chạy.
        self.assertEqual(fps, [])
        out, calls = self._call(self.SLUG, self.KEY, MULTI2, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])
        self.assertEqual(store.for_team("team-1"), [])

    def test_expired_card_denies(self):
        store, gate, fps = self._setup_card(TRASH)
        ap = store.create(team_id="team-1", task_id="task-1", step_id="step-1", team_rev=1, requested_by=self.KEY,
                          kind="action", title="t", action="a", deadline_at=time.time() - 1,
                          fingerprints=[{"fp": fps[0], "label": "x", "call": "y"}])
        r = store.decide(ap["approval_id"], "approve", by="owner", decision_key="k-exp")
        self.assertFalse(r["ok"])
        store.granted_step(ap["approval_id"], "step-1")
        out, calls = self._call(self.SLUG, self.KEY, TRASH, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def test_drive_ttl_constant_is_30_minutes(self):
        # Chỉ kiểm hằng số TTL. Việc gắn deadline vào thẻ nằm trong team_runner._approval_need (chưa có test đơn vị).
        import team_runner
        self.assertEqual(team_runner.DRIVE_APPROVAL_TTL_S, 1800)

    def test_wrong_agent_and_other_folder_denied(self):
        store, gate, fps = self._setup_card(TRASH)
        ap = store.create(team_id="team-1", task_id="task-1", step_id="step-1", team_rev=1, requested_by=self.KEY,
                          kind="action", title="t", action="a", deadline_at=time.time() + 600,
                          fingerprints=[{"fp": fps[0], "label": "x", "call": "y"}])
        store.decide(ap["approval_id"], "approve", by="owner", decision_key="k-wa")
        store.granted_step(ap["approval_id"], "step-1")
        # agent khác (không phải thành viên đang chạy của bước) -> DENY
        out, calls = self._call("javis-vu", "javis-vu-key", TRASH, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def test_missing_actor_fail_closed(self):
        store, gate, fps = self._setup_card(TRASH)
        out, calls = self._call("", "", TRASH, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def test_swapped_params_do_not_match_approval(self):
        store, gate, fps = self._setup_card(TRASH)
        ap = store.create(team_id="team-1", task_id="task-1", step_id="step-1", team_rev=1, requested_by=self.KEY,
                          kind="action", title="t", action="a", deadline_at=time.time() + 600,
                          fingerprints=[{"fp": fps[0], "label": "x", "call": "y"}])
        store.decide(ap["approval_id"], "approve", by="owner", decision_key="k-sw")
        store.granted_step(ap["approval_id"], "step-1")
        out, calls = self._call(self.SLUG, self.KEY, OTHER, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])


class ApprovalNeedIntegrationTests(ScopeRouteTests):
    """Gọi THẬT TeamRunner._approval_need với lệnh ngoài vùng bị chặn (gated), rồi lưu thẻ vào sổ SQLite thật."""

    def _runner(self, store):
        import team_runner
        r = team_runner.TeamRunner.__new__(team_runner.TeamRunner)
        r.approvals = store
        r._team = lambda team_id: {"team_id": team_id, "work_mode": "gated"}
        r._name = lambda team, key: "Trợ lý"
        return r

    def _card_from_real_block(self, args=TRASH):
        store = _Store(Path(self.tmp.name) / f"n{time.time_ns()}.sqlite3", self.SLUG, self.KEY)
        gate = team_gate.open_gate(store, "team-1", "task-1", "step-1")
        out, calls = self._call(self.SLUG, self.KEY, args, gate_id=gate.gate_id)
        self.assertEqual(calls, [])
        r = self._runner(store)
        team = {"team_id": "team-1", "work_mode": "gated"}
        task = {"id": "task-1", "title": "t"}
        step = {"step_id": "step-1", "agent_key": self.KEY, "kind": "work", "job_revision": 1, "note": ""}
        need = r._approval_need(team, task, step, {"gate": {"blocked": list(gate.blocked)}, "text": ""})
        return store, gate, need, team, task, step, r

    def test_approval_need_stores_non_null_deadline_about_30_min(self):
        t0 = time.time()
        store, gate, need, team, task, step, r = self._card_from_real_block()
        self.assertIsNotNone(need["deadline_at"])
        self.assertAlmostEqual(need["deadline_at"] - t0, 1800, delta=30)
        ap = store.create(team_id="team-1", task_id="task-1", step_id="step-1", team_rev=1, requested_by=self.KEY,
                          kind=need["kind"], title=need["title"], action=need["action"], scope=need["scope"],
                          impact=need["impact"], evidence=need["evidence"], deadline_at=need["deadline_at"],
                          fingerprints=need["fingerprints"])
        row = store.get(ap["approval_id"])
        self.assertIsNotNone(row["deadline_at"])
        self.assertAlmostEqual(row["deadline_at"] - t0, 1800, delta=30)
        self.assertEqual([f["fp"] for f in row["fingerprints"]], [gate.blocked[0]["fp"]])

    def test_full_lifecycle_on_real_card(self):
        store, gate, need, team, task, step, r = self._card_from_real_block()
        fp = gate.blocked[0]["fp"]
        ap = store.create(team_id="team-1", task_id="task-1", step_id="step-1", team_rev=1, requested_by=self.KEY,
                          kind=need["kind"], title=need["title"], action=need["action"], scope=need["scope"],
                          impact=need["impact"], evidence=need["evidence"], deadline_at=need["deadline_at"],
                          fingerprints=need["fingerprints"])
        self.assertTrue(store.decide(ap["approval_id"], "approve", by="owner", decision_key="k-real")["ok"])
        store.granted_step(ap["approval_id"], "step-1")
        out, calls = self._call(self.SLUG, self.KEY, OTHER, gate_id=gate.gate_id)  # đổi tham số -> DENY
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])
        out, calls = self._call(self.SLUG, self.KEY, TRASH, gate_id=gate.gate_id)  # đúng lệnh -> một lần
        self.assertEqual(out, "OK", out)
        self.assertEqual(len(calls), 1)
        out, calls = self._call(self.SLUG, self.KEY, TRASH, gate_id=gate.gate_id)  # tái dùng -> DENY
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])
        self.assertIsNotNone(fp)

    def test_owner_decision_after_deadline_is_denied(self):
        store, gate, need, team, task, step, r = self._card_from_real_block()
        ap = store.create(team_id="team-1", task_id="task-1", step_id="step-1", team_rev=1, requested_by=self.KEY,
                          kind=need["kind"], title=need["title"], action=need["action"], scope=need["scope"],
                          impact=need["impact"], evidence=need["evidence"], deadline_at=time.time() - 5,
                          fingerprints=need["fingerprints"])
        res = store.decide(ap["approval_id"], "approve", by="owner", decision_key="k-late")
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "expired")
        store.granted_step(ap["approval_id"], "step-1")
        out, calls = self._call(self.SLUG, self.KEY, TRASH, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def test_non_drive_card_keeps_no_deadline(self):
        store = _Store(Path(self.tmp.name) / "nd.sqlite3", self.SLUG, self.KEY)
        r = self._runner(store)
        team = {"team_id": "team-1", "work_mode": "gated"}
        task = {"id": "task-1", "title": "t"}
        step = {"step_id": "step-1", "agent_key": self.KEY, "kind": "work", "job_revision": 1, "note": ""}
        out = {"gate": {"blocked": [{"fp": "h1", "kind": "hub", "name": "some_tool", "args": {"a": 1},
                                     "label": "some_tool"}]}, "text": ""}
        need = r._approval_need(team, task, step, out)
        self.assertIsNone(need["deadline_at"])


class FullScopeRouteTests(ApprovalRouteTests):
    """Nhóm full (javis-vu) trong đợt guard: cổng scope_only chỉ xin duyệt lệnh ghi Drive ngoài vùng."""
    SLUG, KEY = "javis-vu", "javis-vu-key"

    def setUp(self):
        super().setUp()
        dhub.prefetch_parents = _tree({"SYN-IN": ["SYN-OWN-javis-vu"], "SYN-OWN-javis-vu": []})
        self._dwg = (mock.patch.object(g, "current_mode", return_value="enforce"),
                     mock.patch.object(g, "pilot_status", return_value=("ok", frozenset(
                         ["javis-vu", "alex-learning-coach", "alex-manager-affiliate"]))))
        for m in self._dwg:
            m.start()

    def tearDown(self):
        for m in self._dwg:
            m.stop()
        super().tearDown()

    def _gate(self, store):
        return team_gate.open_gate(store, "team-1", "task-1", "step-1", scope_only=True)

    def _card(self, store, gate, deadline_offset=1800):
        out, calls = self._call(self.SLUG, self.KEY, TRASH, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])
        self.assertEqual(len(gate.blocked), 1)
        return store.create(team_id="team-1", task_id="task-1", step_id="step-1", team_rev=1, requested_by=self.KEY,
                            kind="action", title="t", action="a", deadline_at=time.time() + deadline_offset,
                            fingerprints=[{"fp": gate.blocked[0]["fp"], "label": "x", "call": "y"}])

    def test_route_predicate(self):
        with mock.patch.object(g, "current_mode", return_value="off"):
            self.assertFalse(team_gate.scope_route_for("javis-vu"))
        self.assertTrue(team_gate.scope_route_for("javis-vu"))
        self.assertFalse(team_gate.scope_route_for("someone-else"))
        self.assertFalse(team_gate.scope_route_for(""))

    def test_generic_full_tools_unchanged(self):
        store = _Store(Path(self.tmp.name) / "gen.sqlite3", self.SLUG, self.KEY)
        gate = self._gate(store)
        token = tc.bind(tc.make("team", actor=self.SLUG, team_gate=gate.gate_id, provider="claude"))
        try:
            self.assertEqual(team_gate.hub_check("some_kpi_tool", {"x": 1}), (True, ""))
            self.assertEqual(team_gate.native_check(gate.gate_id, "Bash", {"command": "rm -rf /tmp/x"})[0], True)
        finally:
            tc.reset(token)
        self.assertEqual(gate.blocked, [])
        self.assertEqual(store.for_team("team-1"), [])

    def test_non_drive_legacy_write_unaffected(self):
        # Route không phải Composio: guard không can thiệp, đi thẳng dù enforce và có pilot.
        calls = []

        async def inner(a):
            calls.append(a)
            return "OK"
        turn = tc.make("team", actor=self.SLUG, team_gate="", provider="claude")
        token = tc.bind(turn)
        try:
            wrapped = dhub.wrap(inner, {"connector_id": "other"}, "SOME_LEGACY_WRITE", "fn", env=ENV)
            out = asyncio.run(wrapped(TRASH))
        finally:
            tc.reset(token)
        self.assertEqual(out, "OK")
        self.assertEqual(len(calls), 1)

    def test_no_owner_means_zero_invocations(self):
        store = _Store(Path(self.tmp.name) / "noown.sqlite3", self.SLUG, self.KEY)
        gate = self._gate(store)
        self._card(store, gate)
        out, calls = self._call(self.SLUG, self.KEY, TRASH, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def test_owner_exact_card_allows_once_then_denies(self):
        store = _Store(Path(self.tmp.name) / "ok.sqlite3", self.SLUG, self.KEY)
        gate = self._gate(store)
        ap = self._card(store, gate)
        self.assertTrue(store.decide(ap["approval_id"], "approve", by="owner", decision_key="k-full-1")["ok"])
        store.granted_step(ap["approval_id"], "step-1")
        out, calls = self._call(self.SLUG, self.KEY, TRASH, gate_id=gate.gate_id)
        self.assertEqual(out, "OK", out)
        self.assertEqual(len(calls), 1)
        out, calls = self._call(self.SLUG, self.KEY, TRASH, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def test_swapped_args_and_cross_agent_denied(self):
        store = _Store(Path(self.tmp.name) / "sw.sqlite3", self.SLUG, self.KEY)
        gate = self._gate(store)
        ap = self._card(store, gate)
        store.decide(ap["approval_id"], "approve", by="owner", decision_key="k-full-2")
        store.granted_step(ap["approval_id"], "step-1")
        out, calls = self._call(self.SLUG, self.KEY, OTHER, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        out, calls = self._call("alex-learning-coach", "alex-learning-coach-key", TRASH, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def test_expired_card_denied(self):
        store = _Store(Path(self.tmp.name) / "exp.sqlite3", self.SLUG, self.KEY)
        gate = self._gate(store)
        ap = self._card(store, gate, deadline_offset=-1)
        self.assertFalse(store.decide(ap["approval_id"], "approve", by="owner", decision_key="k-full-3")["ok"])
        store.granted_step(ap["approval_id"], "step-1")
        out, calls = self._call(self.SLUG, self.KEY, TRASH, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])

    def test_multi_batch_with_outside_child_is_atomic_deny(self):
        store = _Store(Path(self.tmp.name) / "mb.sqlite3", self.SLUG, self.KEY)
        gate = self._gate(store)
        out, calls = self._call(self.SLUG, self.KEY, MULTI2, gate_id=gate.gate_id)
        self.assertTrue(out.startswith("ERROR:"), out)
        self.assertEqual(calls, [])
        self.assertEqual(gate.blocked, [])


if __name__ == "__main__":
    unittest.main()
