"""Resonance A3: học có kiểm chứng, chạy trên mã thật.

    python tests/run.py resonance_a3_learning -v

Kho SQLite thật (`GoalStore`), `advance`, `tick`, cổng quyền thật của A1, nhịp tim A2 và phép thử M5 thật; engine GIẢ
(đếm lượt), đồng hồ giả. Không gọi model thật. Ma trận nghiệm thu: thiết kế
`docs/superpowers/specs/2026-10-09-resonance-a3-feedback-learning-design.md` mục 13 (G*, A*, R1 tới R7). Chu trình quay
về mã 0.88.1 thật ở `test_resonance_a3_rollback.py`; đường API (biên nhận tin báo) ở `test_resonance_a3_api.py`.

Mỗi kịch bản dùng một kho riêng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a3-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

import resonance as R  # noqa: E402
import resonance_heartbeat as HB  # noqa: E402
import resonance_learning as L  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402

_fails = []


def check(name, cond, info=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or info is None else f"  ({info})"))
    if not cond:
        _fails.append(name)


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-a3-")).resolve())
(Path(BRAIN) / "Javis").mkdir(parents=True)
(Path(BRAIN) / "Inbox").mkdir(parents=True)
P = RS.Principal("agent", "javis", BRAIN)
OWNER = RS.Principal("owner", "owner", BRAIN)
T0 = 1_800_000_000.0
DELIV = "Inbox/a3-viec.md"
USER = "Viết giúp anh một ghi chú tổng hợp trong Inbox gồm báo cáo quý và máy lạnh, giữ tiêu đề Sample."
USER2 = "Làm lại ghi chú tổng hợp cho tuần sau, vẫn đủ báo cáo quý và máy lạnh, giữ tiêu đề Sample."
GOOD = "# Sample\n\nBáo cáo quý, máy lạnh. Ghi chú tổng hợp đủ hai việc.\n"
HALF = "# Sample\n\nBáo cáo quý thôi.\n"
NONE = "# Sample\n\nChưa có gì.\n"
MARK = R.METHODS["work.checklist.v1"]["addendum"][:40]
PREV = "Bản hiện có, sửa tiếp"
CRIT = [{"description": "Có báo cáo quý", "evaluator": "artifact_contract",
         "params": {"path": DELIV, "must_contain": ["báo cáo quý"]}},
        {"description": "Có máy lạnh", "evaluator": "artifact_contract",
         "params": {"path": DELIV, "must_contain": ["máy lạnh"]}}]


def smart(prompt, n):
    """Cách làm mặc định chỉ ra nửa ý; cách "rà đủ ý" ra đủ. Lượt làm sản phẩm (có bản hiện có) theo cùng luật."""
    return GOOD if MARK in prompt else HALF


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class Engine:
    """Engine giả theo prompt. `fn(prompt, n)` trả văn bản, hay dict sự kiện lỗi. `on_query(n, prompt)` chạy trước."""

    def __init__(self, fn=smart, on_query=None):
        self.fn, self.on_query = fn, on_query
        self.queries, self.prompts, self.max_wall_s = 0, [], None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        self.prompts.append(prompt)
        if self.on_query:
            self.on_query(self.queries, prompt)
        out = self.fn(prompt, self.queries)
        if isinstance(out, dict):
            yield out
            return
        yield {"type": "final", "content": out, "tokens_in": 1, "tokens_out": 1}


class Evidence:
    def __init__(self):
        self.items = {}

    def put(self, goal, action_id, text, metadata):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        return eid

    def valid(self, evidence_id):
        return self.items.get(evidence_id)


class Notes:
    def __init__(self):
        self.sent = []

    async def __call__(self, goal, kind, text, card="", quiet=False):
        self.sent.append({"goal": goal.id, "kind": kind, "text": text, "quiet": bool(quiet)})
        return True


class World:
    _n = 0

    def __init__(self, name, engine=None):
        World._n += 1
        self.path = Path(_STATE) / f"{name}-{World._n}.sqlite3"
        self.store = RS.GoalStore(self.path)
        self.agent = RA.enable(self.store, BRAIN)
        self.clock = Clock()
        self.engine = engine or Engine()
        self.notes = Notes()
        self.deps = self.make_deps()

    def make_deps(self):
        def factory(system_prompt, tag):
            return self.engine, {"provider": "fake", "model": "fake-1", "text_only": True}
        return R.GoalDeps(engine_factory=factory, budget=R.CallBudget(0), clock=self.clock, store=self.store,
                          principal=P, brain_root=BRAIN, evidence=Evidence(), notify=self.notes)

    def reopen(self):
        self.store = RS.GoalStore(self.path)
        self.deps = self.make_deps()

    def goal(self, budget=9, criteria=None, guards=None, user=USER, mode="achieve"):
        prop = {"understanding": "Ghi chú tổng hợp hai việc trong Inbox", "criteria": criteria or CRIT,
                "relevant_quote": "Viết giúp anh một ghi chú tổng hợp trong Inbox",
                "horizon": {"kind": "review", "at_iso": "2027-02-20T09:00:00+07:00"}, "stage": "delivery",
                "mode": mode}
        if guards:
            prop["guards"] = guards
        World._n += 1
        mid = 20_000 + World._n
        deps0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi"}), budget=R.CallBudget(0),
                           store=self.store)
        g = asyncio.run(R.form_goal(R.message_ref("s-a3", mid), {
            "principal": P, "brain_root": BRAIN, "session_id": "s-a3", "message_id": mid, "user_text": user,
            "constraints": [], "budget_calls": budget, "proposal": prop, **RA.ctx(self.agent)}, deps0))
        (Path(BRAIN) / DELIV).unlink(missing_ok=True)
        return g

    def revise(self, gid, understanding=None, text=None, criteria=None, reason="người dùng nói lại"):
        g = self.store.get(P, gid)
        fr = dict(self.store.get_revision(P, gid, g.revision))
        if understanding is not None:
            fr["understanding"] = understanding
        if criteria is not None:
            fr["criteria"] = criteria
        iid = None
        if text is not None:
            World._n += 1
            iid = self.store.add_intent(P, "s-a3", 30_000 + World._n, text, [], relation="replace")["id"]
        return self.store.revise(P, gid, g.revision, fr, reason, intent_id=iid)

    def held_goal(self, budget=9, **kw):
        """Mục tiêu có revision 2 (cách hiểu và lời khác thật, cùng bộ tiêu chí): có tình huống giữ riêng."""
        g = self.goal(budget=budget, **kw)
        self.revise(g.id, understanding="Ghi chú tổng hợp hai việc cho tuần sau", text=USER2)
        return self.store.get(P, g.id)

    def tick(self, limit=5):
        return asyncio.run(R.tick(self.store, self.clock(), lambda b: self.deps, limit=limit))

    def step(self, gid):
        """Một nhịp ở mốc lịch sớm nhất của mục tiêu (không lùi đồng hồ). Trả False khi không còn lịch."""
        dues = [w["due_at"] for w in self.store.wakes(P, gid)]
        if not dues:
            return False
        self.clock.t = max(self.clock.t, min(dues))
        self.tick()
        return True

    def until(self, gid, pred, max_steps=40):
        for _ in range(max_steps):
            if pred():
                return True
            if not self.step(gid):
                return pred()
        return pred()

    def run_days(self, gid, days):
        end = self.clock.t + days * 86400
        for _ in range(400):
            dues = [w["due_at"] for w in self.store.wakes(P, gid)]
            if not dues or min(dues) > end:
                break
            self.clock.t = max(self.clock.t, min(dues))
            self.tick()
        self.clock.t = max(self.clock.t, end)

    def g(self, gid):
        return self.store.get(P, gid)

    def lessons(self, gid):
        return self.store.method_lessons(P, gid)

    def lesson(self, gid):
        rows = self.lessons(gid)
        return rows[-1] if rows else None

    def holds(self, gid):
        return self.store.holds(P, gid)

    def hold(self, gid):
        rows = self.holds(gid)
        return rows[-1] if rows else None

    def pending(self, gid, code=None):
        return [r for r in self.store.reasons(P, gid) if code is None or r["code"] == code]

    def outbox(self, gid, kind):
        with sqlite3.connect(str(self.path)) as c:
            return [json.loads(r[0]) for r in c.execute(
                "SELECT payload_json FROM outbox WHERE goal_id=? AND kind=? ORDER BY id", (gid, kind)).fetchall()]

    def exps(self, gid):
        return self.store.experiments(P, gid)

    def sql(self, q, args=()):
        with sqlite3.connect(str(self.path)) as c:
            c.execute(q, args)

    def stalled(self, gid):
        return lambda: (self.store.run_state(P, gid) or {}).get("block_reason") == "stalled"


def write(rel, text):
    f = Path(BRAIN) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8", newline="\n")


def agent_snapshot(store):
    f = Path(BRAIN) / "agents" / f"{RA.SLUG}.md"
    with sqlite3.connect(str(store.path)) as c:
        rows = c.execute("SELECT agent_key, status, enabled, config_version FROM resonance_agents ORDER BY agent_key"
                         ).fetchall()
    return hashlib.sha256(f.read_bytes()).hexdigest(), rows


def to_trial_pending(w, gid):
    """Chạy tới khi bế tắc có đề xuất phép thử đang chờ (không chạy phép thử)."""
    w.until(gid, w.stalled(gid))
    return w.lesson(gid)


def to_applied(w, gid):
    """Chạy tới khi phép thử thắng và đã áp dụng (lượt giữ còn `held`, lý do làm sản phẩm đang chờ)."""
    to_trial_pending(w, gid)
    w.until(gid, lambda: (w.lesson(gid) or {}).get("status") in ("active", "rejected", "unknown", "dismissed",
                                                                   "skipped"))
    return w.lesson(gid)


# ═══════════════════ Chính sách thuần ═══════════════════

check("tin bắt buộc khoá đúng danh sách thiết kế mục 5.1",
      L.MANDATORY_KINDS == ("goal.guard", "goal.monitoring_lost", "goal.deadline_passed", "goal.publish_conflict",
                            "goal.failed", "goal.blocked", "goal.waiting_human", "goal.stalled",
                            "goal.discovery_done", "goal.method_changed"))
_all_short = {"notice_detail": "brief", "notice_ping": "quiet"}
check("tin bắt buộc luôn đầy đủ và rung chuông dù bài học rút gọn và tắt chuông đang dùng",
      all(L.presentation_for(k, _all_short) == {"detail": "full", "quiet": False} for k in L.MANDATORY_KINDS))
check("rút gọn chỉ cho goal.succeeded và goal.maintained; tắt chuông chỉ cho goal.maintained",
      L.presentation_for("goal.succeeded", _all_short) == {"detail": "brief", "quiet": False}
      and L.presentation_for("goal.maintained", _all_short) == {"detail": "brief", "quiet": True})


def rx(msg, reason="too_long", kind="goal.succeeded", value="down", alive=True, pres="full", at=T0):
    return {"message": msg, "notice_kind": kind, "presentation": pres, "value": value, "reason": reason,
            "alive": alive, "updated_at": at, "ref": f"reaction:{msg}@1"}


check("bộ học: một tin Dài quá chưa đủ", L.propose([rx("a")], {}, [], [], T0) is None)
check("bộ học: hai tin khác nhau Dài quá thì đề xuất rút gọn",
      (L.propose([rx("a"), rx("b")], {}, [], [], T0) or {}).get("to_value") == "brief")
check("bộ học: hai reaction trên CÙNG một tin vẫn là một tin", L.propose([rx("a"), rx("a")], {}, [], [], T0) is None)
check("bộ học: reaction mồ côi không đếm", L.propose([rx("a"), rx("b", alive=False)], {}, [], [], T0) is None)
check("bộ học: 👎 không lý do và 👍 không mở đề xuất",
      L.propose([rx("a", reason=""), rx("b", reason=""), rx("c", value="up", reason="")], {}, [], [], T0) is None)
check("bộ học: đã có đề xuất chờ cùng khoá thì không đề xuất",
      L.propose([rx("a"), rx("b")], {}, ["notice_detail"], [], T0) is None)
check("bộ học: vừa Bỏ qua trong 14 ngày thì không đề xuất lại",
      L.propose([rx("a"), rx("b")], {}, [], [{"key": "notice_detail", "to_value": "brief", "decided_at": T0}],
                T0 + 86400) is None)
check("bộ học: Khó hiểu trên tin rút gọn thì đề xuất quay lại đầy đủ",
      (L.propose([rx("a", reason="unclear", pres="brief")], {"notice_detail": "brief"}, [], [], T0) or {})
      .get("to_value") == "full")
check("bộ học: reaction cũ hơn 30 ngày không mở đề xuất",
      L.propose([rx("a", at=T0), rx("b", at=T0)], {}, [], [], T0 + 31 * 86400) is None)
check("bộ học: Báo nhiều quá chỉ tính tin goal.maintained",
      L.propose([rx("a", "too_often"), rx("b", "too_often")], {}, [], [], T0) is None
      and (L.propose([rx("a", "too_often", "goal.maintained"), rx("b", "too_often", "goal.maintained")], {}, [], [],
                     T0) or {}).get("to_value") == "quiet")
check("ngân sách trọn vòng: 3 lượt đã dùng cần hạn mức 9",
      L.full_cycle(9, 3, 0, 4, 4, 1) == (True, "") and L.full_cycle(8, 3, 0, 4, 4, 1)[0] is False
      and L.full_cycle(6, 3, 0, 4, 3, 1)[0] is False)
check("decide: tin mới thắng lượt làm sản phẩm và phép thử; lượt giữ cho tin mới chạy khi left=0",
      HB.decide([{"code": "method_followup"}, {"code": "feedback"}, {"code": "method_trial"}], attempted=True,
                outcome="not_met", left=0, chain=HB.Chain(), hold_ok=True, trial_ok=True).trigger == "feedback")
check("decide: FOLLOWUP trước TRIAL trước AUTO; không đòi phần dư trên lượt dự phòng",
      HB.decide([{"code": "retry_not_met"}, {"code": "method_trial"}, {"code": "method_followup"}], attempted=True,
                outcome="not_met", left=1, chain=HB.Chain(), hold_ok=True, trial_ok=True).trigger == "method_followup"
      and HB.decide([{"code": "retry_not_met"}, {"code": "method_trial"}], attempted=True, outcome="not_met",
                    left=5, chain=HB.Chain(), trial_ok=True).action == "trial")
check("decide: lượt giữ không hợp lệ thì FOLLOWUP không mở lượt; phép thử không đủ thì không chạy",
      HB.decide([{"code": "method_followup"}, {"code": "method_trial"}], attempted=True, outcome="not_met", left=5,
                chain=HB.Chain()).action == "evaluate")
check("heartbeat.v2", HB.POLICY_VERSION == "heartbeat.v2")

# ═══════════════════ Làn M: trọn vòng (R3a) ═══════════════════

w = World("r3a")
g = w.held_goal(budget=9)
before = agent_snapshot(w.store)
to_trial_pending(w, g.id)
ls = w.lesson(g.id)
check("R3a bế tắc sau 3 lượt việc: đề xuất phép thử đang chờ, có lý do method_trial",
      w.engine.queries == 3 and ls and ls["status"] == "trial_pending" and w.pending(g.id, "method_trial"),
      (w.engine.queries, ls and ls["status"]))
check("R3a đề xuất ghim hash đầu vào hai tình huống khác nhau",
      len({m["prompt_input_hash"] for m in (ls["evidence"].get("cases") or {}).values()}) == 2)
w.until(g.id, lambda: w.g(g.id).status != "active")
gg = w.g(g.id)
acts = [x for x in w.store.actions(P, g.id) if x["kind"] == "work"]
trials = [x for x in w.store.actions(P, g.id) if x["kind"] == "trial"]
check("R3a phép thử 4 lượt, lượt làm sản phẩm 1 lượt: tổng 8 lượt engine, calls_used 8, còn 1 lượt dự phòng",
      w.engine.queries == 8 and gg.calls_used == 8 and gg.budget_calls - gg.calls_used == 1,
      (w.engine.queries, gg.calls_used))
check("R3a lượt làm sản phẩm dùng cách mới (prompt có phần thêm), sửa trên bản hiện có, mục tiêu đạt",
      MARK in w.engine.prompts[-1] and PREV in w.engine.prompts[-1] and gg.status == "succeeded")
check("R3a lượt làm sản phẩm mang lượt giữ; lượt giữ `used`; bài học `active`",
      acts[-1]["intent"].get("hold_id") == w.hold(g.id)["id"] and w.hold(g.id)["status"] == "used"
      and w.lesson(g.id)["status"] == "active")
check("R3a action phép thử mang revision hiện tại (2), kể cả tình huống giữ riêng lấy từ revision 1",
      len(trials) == 4 and all(x["revision"] == 2 for x in trials))
check("R3a prompt tình huống giữ riêng dựng từ lời của revision 1",
      sum(1 for pr in w.engine.prompts[3:7] if USER in pr) == 2 and sum(1 for pr in w.engine.prompts[3:7]
                                                                       if USER2 in pr) == 2)
mc = w.outbox(g.id, "goal.method_changed")
check("R3a tin method_changed một lần, gửi sau lượt sản phẩm, kèm kết quả",
      len(mc) == 1 and mc[0].get("result") == "done" and mc[0].get("verdict") == "met")
check("R3a/A8 học không ghi quyền: file trợ lý và sổ đăng ký không đổi", agent_snapshot(w.store) == before)

# Biến thể: lượt sản phẩm vẫn chưa đạt thì chờ, không tự tiêu thêm (R3e: lịch xem lại là CHECK, 0 lượt).
w = World("r3a-notmet", Engine(fn=lambda pr, n: GOOD if (MARK in pr and PREV not in pr) else HALF))
g = w.held_goal(budget=9)
w.until(g.id, lambda: (w.hold(g.id) or {}).get("status") == "used")
q = w.engine.queries
w.run_days(g.id, 30)
check("R3a/R3e lượt sản phẩm chưa đạt: bế tắc lại, 30 ngày sau không thêm lượt nào, còn đúng lượt dự phòng",
      q == 8 and w.engine.queries == 8 and w.g(g.id).calls_used == 8 and w.g(g.id).status == "active"
      and w.outbox(g.id, "goal.method_changed")[0].get("verdict") != "met", (q, w.engine.queries))

# ═══════════════════ Làn M: điều kiện và bỏ qua ═══════════════════

w = World("r3b")
g = w.held_goal(budget=6)
w.until(g.id, w.stalled(g.id))
w.run_days(g.id, 5)
check("R3b hạn mức mặc định 6: bài học skipped/budget, 0 lượt thêm, không phép thử",
      (w.lesson(g.id) or {}).get("status") == "skipped" and w.lesson(g.id)["status_reason"] == "budget"
      and w.engine.queries == 3 and w.g(g.id).calls_used == 3 and not w.exps(g.id))

w = World("r3c")
g = w.goal(budget=9)
w.until(g.id, w.stalled(g.id))
w.run_days(g.id, 2)
check("R3c không có revision trước: skipped/no_holdout, 0 lượt thêm",
      (w.lesson(g.id) or {}).get("status_reason") == "no_holdout" and w.engine.queries == 3 and not w.exps(g.id))

w = World("g7b", Engine(fn=lambda pr, n: HALF))
g = w.held_goal(budget=2)
w.run_days(g.id, 3)
check("G7b bế tắc vì lượt dự phòng (không phải stalled): không đề xuất, không thêm lượt",
      not w.lessons(g.id) and w.engine.queries == 1)

wg = World("g7c")
gu = wg.goal(budget=9, criteria=[{"description": "Anh duyệt", "evaluator": "human_confirmation"}])
check("G7c revision không có tiêu chí host chấm được: skipped/untestable",
      (R._method_proposal(wg.g(gu.id), HB.Chain(0, 2, 0, ""), wg.deps) or {}).get("status_reason") == "untestable")

# ═══════════════════ R7: chọn tình huống giữ riêng ═══════════════════

w = World("r7a")
g = w.goal()
w.revise(g.id, reason="chỉ đổi lý do sửa")          # cùng khung, cùng ý định: chỉ khác metadata
c7 = R.host_trial_cases(w.g(g.id), w.deps)
check("R7a revision trước chỉ khác metadata: không chọn, no_holdout", c7.get("skip") == "no_holdout")

w = World("r7b")
g = w.held_goal()
c7 = R.host_trial_cases(w.g(g.id), w.deps)
check("R7b revision trước khác thật, cùng tiêu chí: được chọn; ghim hash và bản ghi; prompt từ revision cũ",
      not c7.get("skip") and c7["items"]["cases"][1]["id"] == "rev1"
      and c7["meta"]["rev1"]["prompt_input_hash"] != c7["meta"]["rev2"]["prompt_input_hash"]
      and c7["case_goals"]["rev1"].understanding == "Ghi chú tổng hợp hai việc trong Inbox"
      and c7["case_goals"]["rev1"].revision == 2 and USER in c7["items"]["cases"][1]["input"])

w = World("r7c")
g = w.held_goal()
w.revise(g.id, reason="chỉ đổi lý do")                # rev3 = rev2 về đầu vào
c7 = R.host_trial_cases(w.g(g.id), w.deps)
check("R7c revision gần nhất chỉ khác metadata, revision cũ hơn khác thật: chọn revision cũ hơn",
      not c7.get("skip") and c7["items"]["cases"][1]["id"] == "rev1")

w = World("r7d")
g = w.goal()
w.revise(g.id, understanding="Khác hẳn", text=USER2, criteria=[CRIT[0]])
c7 = R.host_trial_cases(w.g(g.id), w.deps)
check("R7d revision trước khác bộ tiêu chí host chấm: không chọn", c7.get("skip") == "no_holdout")

# ═══════════════════ Kết quả thua, chưa rõ ═══════════════════


def lose(pr, n):
    if MARK in pr:
        return NONE
    return GOOD if USER in pr and USER2 not in pr else HALF


w = World("g4a", Engine(fn=lose))
g = w.held_goal(budget=9)
to_applied(w, g.id)
check("G4a ứng viên tụt ở tình huống giữ riêng: rejected, cách làm giữ, lượt giữ trả (calls 3+4), không tin đổi",
      w.lesson(g.id)["status"] == "rejected" and R.effective_method(w.g(g.id)) == "work.v1"
      and w.hold(g.id)["status"] == "released" and w.g(g.id).calls_used == 7
      and not w.pending(g.id, "method_followup") and not w.outbox(g.id, "goal.method_changed"),
      (w.lesson(g.id)["status"], w.g(g.id).calls_used))
w.run_days(g.id, 3)
check("G4a sau đó không thêm lượt", w.engine.queries == 7)

ERR = {"type": "final", "content": "upstream overloaded", "is_error": True, "subtype": "error"}
w = World("g4b", Engine(fn=lambda pr, n: ERR if MARK in pr else HALF))
g = w.held_goal(budget=9)
to_applied(w, g.id)
check("G4b một bên chưa rõ: unknown, cách làm giữ, lượt giữ trả",
      w.lesson(g.id)["status"] == "unknown" and R.effective_method(w.g(g.id)) == "work.v1"
      and w.hold(g.id)["status"] == "released" and w.exps(g.id)[0]["verdict"] == "inconclusive")

# ═══════════════════ R1: Bỏ qua và Áp dụng trong giao dịch chốt ═══════════════════

w = World("r1a")
g = w.held_goal(budget=9)
lid = to_trial_pending(w, g.id)["id"]
_orig_fin = w.store.finish_experiment


def _dismiss_then_finish(*a, **k):
    # Móc kiểm thử: ĐÚNG sau cổng cuối ngoài giao dịch, ngay trước giao dịch chốt.
    w.store.lesson_decide(OWNER, lid, "dismiss")
    return _orig_fin(*a, **k)


w.store.finish_experiment = _dismiss_then_finish
w.until(g.id, lambda: bool(w.exps(g.id)) and w.exps(g.id)[0]["status"] == "finished")
e = w.exps(g.id)[0]
check("R1a Bỏ qua commit trước giao dịch chốt: cách làm giữ, bài học dismissed, phép thử inconclusive/lesson_dismissed",
      R.effective_method(w.g(g.id)) == "work.v1" and w.lesson(g.id)["status"] == "dismissed"
      and e["verdict"] == "inconclusive" and e["reason"] == "lesson_dismissed" and not e["applied"], e)
check("R1a lượt đã gọi giữ nguyên (3+4), lượt giữ released, không lý do method_followup, không tin đổi",
      w.g(g.id).calls_used == 7 and w.hold(g.id)["status"] == "released" and not w.pending(g.id, "method_followup")
      and not w.outbox(g.id, "goal.method_changed") and w.engine.queries == 7)

w = World("r1b")
g = w.held_goal(budget=9)
ls = to_applied(w, g.id)
res = w.store.lesson_decide(OWNER, ls["id"], "dismiss", expected_status="trialing")
check("R1b áp dụng commit trước: Bỏ qua cũ nhận xung đột, trạng thái active",
      res["ok"] is False and res["lesson"]["status"] == "active")
res = w.store.lesson_decide(OWNER, ls["id"], "revoke")
check("R1b Thu hồi: quay lại cách cũ, bài học revoked, lượt giữ released (7), lý do method_followup chốt",
      res["ok"] and R.effective_method(w.g(g.id)) == "work.v1" and w.lesson(g.id)["status"] == "revoked"
      and w.hold(g.id)["status"] == "released" and w.g(g.id).calls_used == 7 and not w.pending(g.id, "method_followup"))
w.run_days(g.id, 3)
check("R1b sau thu hồi không chạy lượt sản phẩm", w.engine.queries == 7)
check("R1b thu hồi lần hai không lỗi", w.store.lesson_decide(OWNER, ls["id"], "revoke")["ok"] is False)

w = World("r1c")
g = w.held_goal(budget=9)
ls = to_trial_pending(w, g.id)
w.store.lesson_decide(OWNER, ls["id"], "dismiss")
w.run_days(g.id, 3)
check("R1c Bỏ qua lúc trial_pending: không phép thử, không giữ lượt, 0 lượt thêm",
      not w.exps(g.id) and not w.holds(g.id) and w.engine.queries == 3 and not w.pending(g.id, "method_trial"))


def _mark_skipped(n, pr):
    if n == 5:
        w.sql("UPDATE lessons SET status='skipped' WHERE goal_id=? AND lane='method'", (gid_r1d,))


w = World("r1d", Engine(on_query=lambda n, pr: _mark_skipped(n, pr)))
g = w.held_goal(budget=9)
gid_r1d = g.id
to_applied(w, g.id)
check("R1d bài học bị đổi ngoài luồng giữa hai lượt: dừng ở cổng, CAS chốt thất bại, cách làm giữ",
      R.effective_method(w.g(g.id)) == "work.v1" and w.exps(g.id)[0]["applied"] is False
      and w.engine.queries == 5 and w.hold(g.id)["status"] == "released", w.engine.queries)

# ═══════════════════ G6: chốt dừng giữa phép thử ═══════════════════


def mid_trial(name, act):
    holder = {}

    def on_q(n, pr):
        if n == 4:
            act(holder["w"], holder["g"])
    w = World(name, Engine(on_query=on_q))
    g = w.held_goal(budget=9)
    holder.update(w=w, g=g.id)
    to_trial_pending(w, g.id)
    w.until(g.id, lambda: bool(w.exps(g.id)) and w.exps(g.id)[0]["status"] == "finished")
    return w, g


w, g = mid_trial("g6a", lambda w, gid: w.store.set_paused(OWNER, gid, True))
e = w.exps(g.id)[0]
check("G6a pause sau lượt baseline đầu: dừng, inconclusive/stopped, 1 lượt tính, hoàn 3, trả lượt giữ (calls 4)",
      e["verdict"] == "inconclusive" and e["reason"] == "stopped" and w.g(g.id).calls_used == 4
      and w.engine.queries == 4 and w.hold(g.id)["status"] == "released" and w.lesson(g.id)["status"] == "unknown",
      (e["reason"], w.g(g.id).calls_used, w.engine.queries))
w, g = mid_trial("g6b", lambda w, gid: RA.disable(w.store, BRAIN))
check("G6b tắt trợ lý giữa phép thử: dừng, không áp dụng",
      w.exps(g.id)[0]["verdict"] == "inconclusive" and R.effective_method(w.g(g.id)) == "work.v1"
      and w.engine.queries == 4)
RA.enable(World("reenable").store, BRAIN)
w, g = mid_trial("g6e", lambda w, gid: w.store.lesson_decide(OWNER, w.lesson(gid)["id"], "dismiss"))
check("G6e Bỏ qua giữa hai lượt: dừng ở cổng lượt kế, lượt đã bắt đầu vẫn tính",
      w.lesson(g.id)["status"] == "dismissed" and w.engine.queries == 4 and w.g(g.id).calls_used == 4
      and R.effective_method(w.g(g.id)) == "work.v1")

GUARD = [{"description": "Tiêu đề Sample còn giữ", "evaluator": "artifact_contract",
          "params": {"path": DELIV, "must_contain": ["Sample"]}}]


def _break_guard(w, gid):
    write(DELIV, "Mất tiêu đề rồi.\n")


holder = {}
w = World("g6c", Engine(on_query=lambda n, pr: _break_guard(None, None) if n == 4 else None))
g = w.held_goal(budget=9, guards=GUARD)
write(DELIV, "# Sample\n\nBản cũ.\n")
to_trial_pending(w, g.id)
w.until(g.id, lambda: bool(w.exps(g.id)) and w.exps(g.id)[0]["status"] == "finished")
check("G6c guard nhảy giữa phép thử: dừng, chốt guard giữ, không áp dụng",
      w.exps(g.id)[0]["verdict"] == "inconclusive" and (w.store.run_state(P, g.id) or {}).get("block_reason") == "guard"
      and R.effective_method(w.g(g.id)) == "work.v1", w.store.run_state(P, g.id))

w = World("g6d")
g = w.held_goal(budget=9)
to_trial_pending(w, g.id)
w.sql("UPDATE goals SET budget_calls=8 WHERE id=?", (g.id,))
w.run_days(g.id, 2)
check("G6d hạn mức hạ trước khi phép thử chạy: skipped/budget, 0 lượt, calls_used không đổi",
      w.lesson(g.id)["status"] == "skipped" and w.lesson(g.id)["status_reason"] == "budget"
      and w.engine.queries == 3 and w.g(g.id).calls_used == 3 and not w.exps(g.id))

# ═══════════════════ A5, A6: tin mới và "Hiểu chưa đúng" ═══════════════════

w = World("a5")
g = w.held_goal(budget=9)
to_trial_pending(w, g.id)
w.store.record_feedback(OWNER, g.id, w.g(g.id).revision, "goal_fit_confirmed", {}, "fb-a5")
w.tick()
check("A5 tin mới tới trước phép thử: lượt sửa bằng cách cũ, đề xuất skipped/new_feedback, không phép thử",
      w.engine.queries == 4 and MARK not in w.engine.prompts[-1] and w.lesson(g.id)["status"] == "skipped"
      and w.lesson(g.id)["status_reason"] == "new_feedback" and not w.exps(g.id))

w = World("a6")
g = w.held_goal(budget=9)
to_trial_pending(w, g.id)
w.store.record_feedback(OWNER, g.id, w.g(g.id).revision, "goal_fit_rejected", {}, "fb-a6")
w.run_days(g.id, 3)
check("A6 Hiểu chưa đúng sau đề xuất: lý do bị gác, không chạy phép thử", not w.exps(g.id) and w.engine.queries == 3
      and w.lesson(g.id)["status"] == "trial_pending")

# ═══════════════════ R3d, R3f, R3g, R3h, R3i: sau khi áp dụng ═══════════════════

w = World("r3d")
g = w.held_goal(budget=9)
to_applied(w, g.id)
check("R3d trước sửa cách hiểu: lượt giữ held, calls 8", w.hold(g.id)["status"] == "held" and w.g(g.id).calls_used == 8)
w.revise(g.id, understanding="Cách hiểu thứ ba", text="Thêm một ý nữa cho ghi chú, giữ tiêu đề Sample.")
check("R3d sửa cách hiểu: lượt giữ released (calls 7), bài học out_of_scope, cách làm mặc định",
      w.hold(g.id)["status"] == "released" and w.g(g.id).calls_used == 7
      and w.lesson(g.id)["status"] == "out_of_scope" and R.effective_method(w.g(g.id)) == "work.v1")
q = w.engine.queries
w.tick()
check("R3d revision mới làm bằng cách mặc định, không dùng lượt giữ cũ",
      w.engine.queries == q + 1 and MARK not in w.engine.prompts[-1]
      and not [x for x in w.store.actions(P, g.id) if x["kind"] == "work"][-1]["intent"].get("hold_id"))

w = World("r3f")
g = w.held_goal(budget=9)
to_applied(w, g.id)
w.store.record_feedback(OWNER, g.id, w.g(g.id).revision, "goal_fit_confirmed", {}, "fb-r3f")
w.run_days(g.id, 3)
act = [x for x in w.store.actions(P, g.id) if x["kind"] == "work"][-1]
check("R3f tin mới tiếp quản lượt giữ: dùng cách mới, calls 8, FOLLOWUP không chạy thêm, lượt giữ used",
      act["intent"].get("hold_id") == w.hold(g.id)["id"] and MARK in w.engine.prompts[-1]
      and w.g(g.id).calls_used == 8 and w.engine.queries == 8 and w.hold(g.id)["status"] == "used"
      and not w.pending(g.id, "method_followup"), (w.engine.queries, w.g(g.id).calls_used))

w = World("r3g")
g = w.held_goal(budget=9)
to_applied(w, g.id)
w.reopen()
w.until(g.id, lambda: (w.hold(g.id) or {}).get("status") == "used")
q = w.engine.queries
w.reopen()
w.run_days(g.id, 3)
check("R3g khởi động lại giữa áp dụng và lượt sản phẩm: chạy đúng một lần; mở lại không dựng lý do mới",
      q == 8 and w.engine.queries == 8 and not w.pending(g.id, "method_followup"))

w = World("r3h")
g = w.held_goal(budget=9)
to_applied(w, g.id)
w.store.set_paused(OWNER, g.id, True)
w.run_days(g.id, 2)
check("R3h pause trước lượt sản phẩm: 0 lượt, lượt giữ held", w.engine.queries == 7 and w.hold(g.id)["status"] == "held")
w.store.set_paused(OWNER, g.id, False)
w.run_days(g.id, 1)
check("R3h resume: lượt sản phẩm chạy một lần", w.engine.queries == 8 and w.hold(g.id)["status"] == "used")

w = World("r3i1")
g = w.held_goal(budget=9)
to_applied(w, g.id)
write(DELIV, "# Sample\n\nAnh tự sửa tay.\n")
w.run_days(g.id, 2)
check("R3i1 sửa tay đã thấy trước khi mở lượt: gác, 0 lượt, lượt giữ held",
      w.engine.queries == 7 and w.hold(g.id)["status"] == "held"
      and (w.store.run_state(P, g.id) or {}).get("block_reason") == "source_drift", w.store.run_state(P, g.id))

w = World("r3i2", Engine(fn=smart, on_query=lambda n, pr: write(DELIV, "# Sample\n\nSửa tay giữa lượt.\n")
                         if n == 8 else None))
g = w.held_goal(budget=9)
w.until(g.id, lambda: (w.hold(g.id) or {}).get("status") == "used")
check("R3i2 sửa tay trong lúc lượt sản phẩm chạy: không ghi đè, lượt giữ used, tin đổi cách làm vẫn gửi",
      (Path(BRAIN) / DELIV).read_text(encoding="utf-8") == "# Sample\n\nSửa tay giữa lượt.\n"
      and w.engine.queries == 8 and len(w.outbox(g.id, "goal.method_changed")) == 1)

# ═══════════════════ R4: tiếp quản lượt giữ khi chạm trần ═══════════════════

os.environ["JAVIS_RESONANCE_CALL_CEILING"] = "8"
w = World("r4a")
g = w.held_goal(budget=9)
to_applied(w, g.id)
check("R4a trần 8: phép thử và lượt giữ vừa trần (calls 8)", w.g(g.id).calls_used == 8 and w.hold(g.id)["status"] == "held")
w.store.record_feedback(OWNER, g.id, w.g(g.id).revision, "goal_fit_confirmed", {}, "fb-r4a")
w.tick()
check("R4a góp ý cùng revision nhận lượt giữ dù chạm trần: 1 lượt, calls 8, FOLLOWUP không chạy",
      w.engine.queries == 8 and w.g(g.id).calls_used == 8 and w.hold(g.id)["status"] == "used"
      and not w.pending(g.id, "method_followup"), (w.engine.queries, w.g(g.id).calls_used))

w = World("r4b")
g = w.held_goal(budget=9)
to_applied(w, g.id)
w.revise(g.id, understanding="Cách hiểu thứ ba", text="Viết lại theo ý mới, giữ tiêu đề Sample.")
w.tick()
act = [x for x in w.store.actions(P, g.id) if x["kind"] == "work"][-1]
check("R4b revision mới không mượn lượt giữ cũ: lượt giữ released (7), lượt mới giữ như thường (8)",
      w.hold(g.id)["status"] == "released" and not act["intent"].get("hold_id") and w.g(g.id).calls_used == 8
      and w.engine.queries == 8)

w = World("r4c")
g = w.held_goal(budget=10)
to_applied(w, g.id)
w.until(g.id, lambda: (w.hold(g.id) or {}).get("status") == "used")
q, cu = w.engine.queries, w.g(g.id).calls_used
if w.g(g.id).status == "active":
    w.store.record_feedback(OWNER, g.id, w.g(g.id).revision, "goal_fit_confirmed", {}, "fb-r4c")
    w.tick()
check("R4c lượt giữ đã dùng, trần 8 đã chạm: góp ý không mượn lại lượt giữ, bị trần chặn, 0 lượt",
      cu == 8 and w.engine.queries == q, (cu, q, w.engine.queries))
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

# ═══════════════════ R5: huỷ trước và sau engine, đối soát ═══════════════════


def cancel_in_pre(w, gid):
    """Huỷ lần thức ĐÚNG lúc pha chuẩn bị đang chạy (sau khi ghi ý định, trước engine), qua đường huỷ thật."""
    entered, gate = threading.Event(), threading.Event()
    orig = R._work_pre

    def slow(*a):
        res = orig(*a)
        entered.set()
        gate.wait(5)
        return res

    R._work_pre = slow

    async def run():
        t = asyncio.create_task(R.advance(gid, {"kind": "wake"}, w.deps))
        await asyncio.to_thread(entered.wait, 5)
        t.cancel()
        gate.set()
        try:
            await t
        except asyncio.CancelledError:
            pass

    try:
        asyncio.run(run())
    finally:
        R._work_pre = orig


w = World("r5a")
g = w.held_goal(budget=9)
to_applied(w, g.id)
cancel_in_pre(w, g.id)
h = w.hold(g.id)
acts = [x for x in w.store.actions(P, g.id) if x["kind"] == "work"]
check("R5a huỷ FOLLOWUP trước engine: action not_run, lượt giữ held gen+1, calls 8 (không thành 7), lý do lại chờ",
      acts[-1]["status"] == "cancelled" and acts[-1]["receipt"].get("error_code") == "not_run"
      and h["status"] == "held" and h["gen"] == 2 and w.g(g.id).calls_used == 8
      and w.pending(g.id, "method_followup") and w.engine.queries == 7, (h, w.g(g.id).calls_used))
check("R5b huỷ lặp cùng action: False, không đổi gì",
      w.store.abort_action(P, acts[-1]["id"]) is False and w.g(g.id).calls_used == 8 and w.hold(g.id)["gen"] == 2)
w.run_days(g.id, 1)
check("R5a tick sau: lượt sản phẩm chạy đúng một lần", w.engine.queries == 8 and w.hold(g.id)["status"] == "used"
      and w.g(g.id).calls_used == 8)

w = World("r5c")
g = w.held_goal(budget=9)
to_applied(w, g.id)
w.store.record_feedback(OWNER, g.id, w.g(g.id).revision, "goal_fit_confirmed", {}, "fb-r5c")
cancel_in_pre(w, g.id)
check("R5c huỷ trước engine lượt góp ý đã tiếp quản: lượt giữ held, lý do góp ý và method_followup cùng chờ, calls 8",
      w.hold(g.id)["status"] == "held" and w.pending(g.id, "feedback") and w.pending(g.id, "method_followup")
      and w.g(g.id).calls_used == 8 and w.engine.queries == 7)
w.run_days(g.id, 1)
last = [x for x in w.store.actions(P, g.id) if x["kind"] == "work"][-1]
check("R5c tick sau: góp ý thắng và tiếp quản lại; FOLLOWUP không chạy; tổng 1 lượt",
      w.engine.queries == 8 and last["intent"].get("hold_id") and w.hold(g.id)["status"] == "used"
      and not w.pending(g.id, "method_followup"))

w = World("r5d")
g = w.held_goal(budget=9)
to_applied(w, g.id)
fid = [r["id"] for r in w.pending(g.id, "method_followup")]
crashed = w.store.begin_action(P, g.id, w.g(g.id).revision, "work", lease_until=w.clock() + 5, now=w.clock(),
                               intent={"require_hold": True, "wake_reasons": fid, **R._agent_intent(w.g(g.id), w.deps)})
w.clock.t += 3600
w.reopen()
w.run_days(g.id, 1)
check("R5d chết sau khi lượt sản phẩm có thể đã gọi engine: đối soát chốt action, lượt giữ used, không chạy lại",
      w.store.get_action(P, crashed["id"])["status"] == "failed" and w.hold(g.id)["status"] == "used"
      and w.g(g.id).calls_used == 8 and w.engine.queries == 7 and not w.pending(g.id, "method_followup"))


class _Crash(BaseException):
    pass


def _crash_at(n, pr):
    if n == 6:
        raise asyncio.CancelledError()


w = World("r5e", Engine(on_query=_crash_at))
g = w.held_goal(budget=9)
to_trial_pending(w, g.id)
try:
    w.tick()
except BaseException:  # noqa: BLE001
    pass
started = sum(1 for x in w.store.actions(P, g.id) if x["kind"] == "trial")
check("R5e tiến trình chết giữa phép thử: phép thử còn running, lượt giữ held", w.exps(g.id)[0]["status"] == "running"
      and w.hold(g.id)["status"] == "held", (w.exps(g.id)[0]["status"], started))
w.clock.t += 3600
w.reopen()
w.store.reconcile_holds()
check("R5e mở kho: đối soát tôn trọng việc đang chạy, chưa chốt phép thử khi chưa có lần thức giữ khoá",
      w.exps(g.id)[0]["status"] == "running" and w.hold(g.id)["status"] == "held")
w.run_days(g.id, 1)
e = w.exps(g.id)[0]
check("R5e lần thức sau: phép thử inconclusive/interrupted, hoàn lượt chưa ghi ý định, bài học unknown, lượt giữ released",
      e["status"] == "finished" and e["reason"] == "interrupted" and w.lesson(g.id)["status"] == "unknown"
      and w.hold(g.id)["status"] == "released" and w.g(g.id).calls_used == 3 + started
      and not w.pending(g.id, "method_followup"), (e["reason"], w.g(g.id).calls_used, started))
w.reopen()
w.run_days(g.id, 2)
check("R5e không phép thử thứ hai cho cùng cặp và revision; mở lại không trả hai lần",
      len(w.exps(g.id)) == 1 and w.g(g.id).calls_used == 3 + started)

# Đối soát lặp: không tạo hai lý do, không trả hai lần.
w = World("reconcile-repeat")
g = w.held_goal(budget=9)
to_applied(w, g.id)
w.sql("UPDATE wake_reasons SET state='served', settled_by='evaluate' WHERE goal_id=? AND code='method_followup'",
      (g.id,))
n1 = w.store.reconcile_holds()
n2 = w.store.reconcile_holds()
w.reopen()
check("đối soát: lý do bị bản cũ chốt thì dựng lại đúng một lý do; chạy lặp và mở lại không tạo thêm",
      n1 == 1 and n2 == 0 and len(w.pending(g.id, "method_followup")) == 1 and w.hold(g.id)["gen"] == 2)
w.sql("UPDATE goals SET status='cancelled' WHERE id=?", (g.id,))
m1, m2 = w.store.reconcile_holds(), w.store.reconcile_holds()
check("đối soát: mục tiêu đã huỷ bên ngoài thì trả lượt giữ đúng một lần",
      m1 == 1 and m2 == 0 and w.hold(g.id)["status"] == "released" and w.g(g.id).calls_used == 7)

# ═══════════════════ Làn P ở mức kho (A1, A2, A3, A9, A10, A11, G1, G3, G4c, G5a, R2) ═══════════════════

_msg = [0]


def src(w, g, kind="goal.succeeded", pres="full"):
    _msg[0] += 1
    return {"session_id": "s-a3", "message_id": _msg[0], "report_key": f"outbox:{_msg[0]}", "goal_id": g.id,
            "revision": g.revision, "notice_kind": kind, "presentation": pres, "content_sha": f"sha{_msg[0]}"}


DEAD = set()


def alive(sid, mid, sha):
    return mid not in DEAD


def react(w, s, value="down", reason="too_long", nonce=None):
    _msg[0] += 0
    return w.store.record_reaction(OWNER, s, value, reason, nonce or f"n{os.urandom(4).hex()}", alive=alive,
                                   now=w.clock())


w = World("lane-p")
g = w.goal(budget=9)
wake0 = (sorted(map(str, w.store.wakes(P, g.id))), sorted(map(str, w.store.reasons(P, g.id, state=None))))
before = agent_snapshot(w.store)
s1 = src(w, g)
for i in range(10):
    r = react(w, s1)
check("G3a 10 request cùng giá trị, nonce mới: một dòng, seq 10, giá trị cuối down/too_long, không đề xuất",
      r["reaction"]["seq"] == 10 and r["reaction"]["value"] == "down" and r["proposal"] is None)
with sqlite3.connect(str(w.path)) as c:
    nlog = c.execute("SELECT COUNT(*) FROM reaction_log").fetchone()[0]
    nrow = c.execute("SELECT COUNT(*) FROM reactions").fetchone()[0]
check("G3a 10 dòng log, 1 dòng reaction", nlog == 10 and nrow == 1)
r2 = react(w, s1, nonce="fixed")
r3 = react(w, s1, nonce="fixed")
check("G3b gửi lại cùng nonce: duplicate, seq không đổi", r3["duplicate"] and r3["reaction"]["seq"] == r2["reaction"]["seq"])
check("G1/A3/G7a reaction không mở lượt, không đổi lịch hay lý do thức, không làm mục tiêu đạt",
      (sorted(map(str, w.store.wakes(P, g.id))), sorted(map(str, w.store.reasons(P, g.id, state=None)))) == wake0
      and w.engine.queries == 0 and w.g(g.id).status == "active" and not w.store.assessments(P, g.id))
s2 = src(w, g)
r = react(w, s2)
check("A1 hai tin Dài quá: đề xuất rút gọn, nền mặc định",
      r["proposal"] and r["proposal"]["to_value"] == "brief" and r["proposal"]["base_lesson_id"] == "")
pid = r["proposal"]["id"]
w.reopen()
s3 = src(w, g)
r = react(w, s3)
with sqlite3.connect(str(w.path)) as c:
    npend = c.execute("SELECT COUNT(*) FROM lessons WHERE status='proposed'").fetchone()[0]
check("G3c/R2f đề xuất thứ hai cùng khoá không được tạo, kể cả sau khi mở lại kho", npend == 1 and r["proposal"] is None)
res = w.store.lesson_decide(OWNER, pid, "apply", expected_status="proposed",
                            expected_updated_at=w.store.lesson(OWNER, pid)["updated_at"])
check("A1 Áp dụng: đề xuất active, trình bày brief", res["ok"] and w.store.presentation(BRAIN, w.agent["agent_key"])
      == {"notice_detail": "brief"})
w.store.notice(P, g.id, "goal.maintained", {"deliverable": DELIV}, idem="m1")
w.store.notice(P, g.id, "goal.stalled", {"why": "stalled"}, idem="s1")
asyncio.run(R.drain_outbox(w.store, w.notes))
sent = {n["kind"]: n for n in w.notes.sent}
check("A1 tin goal.maintained dựng rút gọn; tin bắt buộc goal.stalled vẫn đầy đủ",
      sent["goal.maintained"]["text"].startswith(("Đã cập nhật", "Updated")) and len(sent["goal.stalled"]["text"]) > 80)
check("A3 áp dụng làn P không đổi lịch", sorted(map(str, w.store.wakes(P, g.id))) == wake0[0])
# R2: cấu hình đang dùng và đề xuất thay thế cùng tồn tại.
s4 = src(w, g, pres="brief")
r = react(w, s4, reason="unclear")
check("R2a brief active và đề xuất full proposed cùng tồn tại",
      r["proposal"] and r["proposal"]["to_value"] == "full" and r["proposal"]["base_lesson_id"] == pid
      and w.store.presentation(BRAIN, w.agent["agent_key"]) == {"notice_detail": "brief"})
fid = r["proposal"]["id"]
res = w.store.lesson_decide(OWNER, fid, "dismiss")
check("R2b Bỏ qua: brief vẫn dùng", res["ok"] and w.store.presentation(BRAIN, w.agent["agent_key"]) ==
      {"notice_detail": "brief"})
# Đề xuất mới (sau cooldown) rồi áp dụng.
w.clock.t += 15 * 86400
s5 = src(w, g, pres="brief")
r = react(w, s5, reason="unclear")
fid = r["proposal"]["id"]
res = w.store.lesson_decide(OWNER, fid, "apply")
with sqlite3.connect(str(w.path)) as c:
    actives = c.execute("SELECT key, to_value FROM lessons WHERE status='active'").fetchall()
check("R2c Áp dụng full: một giao dịch, brief superseded, đúng một active",
      res["ok"] and actives == [("notice_detail", "full")] and w.store.lesson(OWNER, pid)["status"] == "superseded")
# R2d: thu hồi nền rồi Áp dụng đề xuất cũ dựa trên nền đó.
s6, s7 = src(w, g), src(w, g)
w.clock.t += 15 * 86400
for s_ in (s6, s7):
    r = react(w, s_)
prop = r["proposal"] or next(x for x in w.store.agent_lessons(OWNER, w.agent["agent_key"], alive=alive,
                                                             now=w.clock())["lessons"] if x["status"] == "proposed")
check("R2d có đề xuất rút gọn dựa trên nền full đang dùng", prop["to_value"] == "brief" and prop["base_lesson_id"] == fid)
w.store.lesson_decide(OWNER, fid, "revoke")
res = w.store.lesson_decide(OWNER, prop["id"], "apply")
check("R2d nền đã thu hồi: Áp dụng trả xung đột, đề xuất stale, cấu hình về mặc định, không active nào",
      res["ok"] is False and res["conflict"] == "base_changed" and res["lesson"]["status"] == "stale"
      and w.store.presentation(BRAIN, w.agent["agent_key"]) == {})
check("A8 làn P không ghi quyền", agent_snapshot(w.store) == before)

w = World("r2e")
g = w.goal()
sa, sb = src(w, g, "goal.maintained"), src(w, g, "goal.maintained")
react(w, sa, reason="too_often")
p_ping = react(w, sb, reason="too_often")["proposal"]
w.store.lesson_decide(OWNER, p_ping["id"], "apply")
sc, sd = src(w, g, "goal.maintained"), src(w, g, "goal.maintained")
react(w, sc, reason="too_long")
p_br = react(w, sd, reason="too_long")["proposal"]
check("R2e khoá khác nhau độc lập: tắt chuông đang dùng, đề xuất rút gọn vẫn tạo được", p_br and
      p_br["key"] == "notice_detail")
w.store.notice(P, g.id, "goal.maintained", {"deliverable": DELIV}, idem="m2")
w.store.notice(P, g.id, "goal.deadline_passed", {}, idem="d2")
w.store.notice(P, g.id, "goal.monitoring_lost", {"guards": [], "reason": "agent_off"}, idem="ml2")
asyncio.run(R.drain_outbox(w.store, w.notes))
q_by = {n["kind"]: n["quiet"] for n in w.notes.sent}
check("A2 tắt chuông: goal.maintained gửi quiet, deadline_passed và monitoring_lost vẫn rung chuông",
      q_by.get("goal.maintained") is True and q_by.get("goal.deadline_passed") is False
      and q_by.get("goal.monitoring_lost") is False, q_by)
with sqlite3.connect(str(w.path)) as c:
    pays = [json.loads(r[0]) for r in c.execute("SELECT payload_json FROM outbox WHERE kind='goal.maintained'")]
check("A2 payload outbox ghi cách dựng tin đã dùng", pays and pays[-1].get("presentation", {}).get("quiet") is True)

w = World("g4c")
g = w.goal()
react(w, src(w, g))
pr = react(w, src(w, g))["proposal"]
w.clock.t += 15 * 86400
react(w, src(w, g), value="up", reason="")
check("G4c đề xuất quá 14 ngày: expired, tin vẫn đầy đủ",
      w.store.lesson(OWNER, pr["id"])["status"] == "expired" and w.store.presentation(BRAIN, w.agent["agent_key"]) == {})

w = World("g5a")
g = w.goal()
react(w, src(w, g))
pr = react(w, src(w, g))["proposal"]
w.store.lesson_decide(OWNER, pr["id"], "apply")
w.store.lesson_decide(OWNER, pr["id"], "revoke")
w.store.notice(P, g.id, "goal.maintained", {"deliverable": DELIV}, idem="m3")
asyncio.run(R.drain_outbox(w.store, w.notes))
check("G5a thu hồi làn P: tin kế tiếp đầy đủ như mặc định",
      not w.notes.sent[-1]["text"].startswith(("Đã cập nhật:", "Updated:")) and len(w.notes.sent[-1]["text"]) > 60)

w = World("a9")
g = w.goal()
sa, sb = src(w, g), src(w, g)
react(w, sa)
pr = react(w, sb)["proposal"]
w.store.lesson_decide(OWNER, pr["id"], "apply")
DEAD.add(sb["message_id"])
view = w.store.agent_lessons(OWNER, w.agent["agent_key"], alive=alive, now=w.clock())
mine = next(x for x in view["lessons"] if x["id"] == pr["id"])
check("A9 tin bị xoá: reaction mồ côi không đếm; bài học đã áp dụng vẫn áp, danh sách hiện nguồn đã xoá",
      mine["status"] == "active" and mine["evidence_missing"] == 1 and view["stats"]["orphaned"] == 1)
sc = src(w, g)
react(w, sc)
DEAD.add(sc["message_id"])
check("A9 đề xuất mới không tạo từ reaction mồ côi", not [x for x in w.store.agent_lessons(
    OWNER, w.agent["agent_key"], alive=alive, now=w.clock())["lessons"] if x["status"] == "proposed"])

w = World("a10")
g = w.goal()
old = src(w, g)
old["revision"] = 1
w.revise(g.id, understanding="Cách hiểu 2", text=USER2)
w.store.cancel(OWNER, g.id)
r = react(w, old)
check("A10 reaction trên tin của revision cũ và mục tiêu đã huỷ: ghi được, mục tiêu không đổi",
      r["reaction"]["seq"] == 1 and w.g(g.id).status == "cancelled")

w = World("a11")
g = w.goal()
RA.disable(w.store, BRAIN)
react(w, src(w, g))
r = react(w, src(w, g))
check("A11 trợ lý tắt: reaction ghi được, không đề xuất", r["reaction"]["seq"] == 1 and r["proposal"] is None)
RA.enable(w.store, BRAIN)
r = react(w, src(w, g))
check("A11 bật lại rồi bấm thêm: đề xuất xuất hiện", r["proposal"] is not None)

w = World("g2")
g = w.goal()
try:
    w.store.record_reaction(P, src(w, g), "down", "too_long", "n1")
    ok = False
except PermissionError:
    ok = True
try:
    w.store.lesson_decide(P, "ls_x", "dismiss")
    ok2 = False
except PermissionError:
    ok2 = True
check("G2a principal agent không ghi reaction, không quyết bài học", ok and ok2)
other = RS.Principal("owner", "owner", str(Path(tempfile.mkdtemp(prefix="brain-a3x-")).resolve()))
try:
    w.store.record_reaction(other, src(w, g), "down", "too_long", "n2")
    ok = False
except RS.ScopeError:
    ok = True
check("G2b sai brain: ScopeError, không ghi", ok)
try:
    w.store.record_feedback(OWNER, g.id, 7, "goal_fit_confirmed", {}, "fb-wrong")
    ok = False
except RS.ConflictError:
    ok = True
check("G2c phản hồi M4 sai revision: ConflictError (không đổi)", ok)

# ═══════════════════ Hồi quy review mã vòng 1 (5b4f48a6): RV1 tới RV3 ═══════════════════

import time as _time  # noqa: E402

# RV1: dọn phép thử không được xoá hẹn gỡ chặn mà cổng vừa ghi trong lúc thử (P2-1).
_GF = "Inbox/a3-guard-src.txt"
_GUARD_SRC = [{"description": "Nguồn được bảo vệ", "evaluator": "artifact_contract",
               "params": {"path": _GF, "must_contain": ["safe"]}}]


def guard_trial(name, breaker):
    write(_GF, "safe")
    holder = {}
    w = World(name, Engine(on_query=lambda n, pr: breaker() if n == 4 else None))
    g = w.held_goal(budget=9, guards=_GUARD_SRC)
    holder["g"] = g.id
    to_trial_pending(w, g.id)
    w.until(g.id, lambda: bool(w.exps(g.id)) and w.exps(g.id)[0]["status"] == "finished")
    return w, g


w, g = guard_trial("rv1", lambda: (Path(BRAIN) / _GF).write_bytes(b"\xff\xfe"))
pend = [r["code"] for r in w.pending(g.id)]
check("RV1 guard chưa xác định giữa phép thử: phép thử dừng, hẹn guard_recheck CÒN sau khi dọn phép thử",
      w.exps(g.id)[0]["verdict"] == "inconclusive" and "guard_recheck" in pend
      and (w.store.run_state(P, g.id) or {}).get("block_reason") == "guard_unknown", pend)
rec = [r for r in w.store.reasons(P, g.id, state=None) if r["code"] == "trial_recovery"]
check("RV1 hẹn đối soát của phép thử có nghĩa vụ riêng và chỉ nó được chốt theo id (trial_done)",
      len(rec) == 1 and rec[0]["slot"] == "trial" and rec[0]["state"] == "served" and rec[0]["settled_by"] == "trial_done")
write(_GF, "safe")
w.run_days(g.id, 2)
check("RV1 nguồn hồi phục: lần kiểm lại gỡ chặn, mục tiêu không còn kẹt guard_unknown",
      (w.store.run_state(P, g.id) or {}).get("block_reason") not in ("guard_unknown", "guard"),
      w.store.run_state(P, g.id))
w, g = guard_trial("rv1-control", lambda: write(_GF, "đã mất chữ khoá"))
write(_GF, "đã mất chữ khoá")
w.run_days(g.id, 2)
check("RV1 đối chứng: guard thật sự nhảy thì chốt guard giữ, không tự mở lại",
      (w.store.run_state(P, g.id) or {}).get("block_reason") == "guard" and R.effective_method(w.g(g.id)) == "work.v1")

# RV2: Áp dụng kiểm hạn và căn cứ trong giao dịch, không cần đọc lại danh sách (P2-2).
w = World("rv2")
g = w.goal()
react(w, src(w, g))
pr = react(w, src(w, g))["proposal"]
res = w.store.lesson_decide(OWNER, pr["id"], "apply", expected_status="proposed",
                            expected_updated_at=pr["updated_at"], now=pr["expires_at"] + 1, alive=alive)
check("RV2 thẻ cũ bấm Áp dụng sau khi hết hạn (không GET trung gian): xung đột expired, cấu hình cũ giữ",
      res["ok"] is False and res["conflict"] == "expired" and res["lesson"]["status"] == "expired"
      and w.store.presentation(BRAIN, w.agent["agent_key"]) == {})
w = World("rv2-evidence")
g = w.goal()
sa, sb = src(w, g), src(w, g)
react(w, sa)
pr = react(w, sb)["proposal"]
DEAD.add(sb["message_id"])
res = w.store.lesson_decide(OWNER, pr["id"], "apply", expected_status="proposed",
                            expected_updated_at=pr["updated_at"], now=w.clock(), alive=alive)
check("RV2 căn cứ đã mất (tin bị xoá) lúc Áp dụng: xung đột evidence_gone, không áp dụng",
      res["ok"] is False and res["conflict"] == "evidence_gone" and w.store.presentation(BRAIN, w.agent["agent_key"]) == {})
w = World("rv2-control")
g = w.goal()
react(w, src(w, g))
pr = react(w, src(w, g))["proposal"]
res = w.store.lesson_decide(OWNER, pr["id"], "apply", expected_status="proposed",
                            expected_updated_at=pr["updated_at"], now=w.clock() + 86400, alive=alive)
check("RV2 đối chứng: còn hạn, đúng CAS, đủ căn cứ thì áp dụng được", res["ok"] and res["lesson"]["status"] == "active")


# RV3: phần kho và file của phép thử chạy ngoài event loop; khoá chỉ nhả khi worker xong (P2-3).
def slow(store, name, delay, seen, gate=None, fail=None):
    orig = getattr(store, name)

    def wrapped(*a, **k):
        seen.append((name, threading.get_ident()))
        if gate is not None:
            gate.set()
        _time.sleep(delay)
        if fail is not None and fail[0]:
            fail[0] -= 1
            raise RuntimeError("kho chậm rồi hỏng")
        return orig(*a, **k)
    setattr(store, name, wrapped)


async def _watch(coro):
    gaps, run = [], [True]

    async def dog():
        prev = _time.perf_counter()
        while run[0]:
            await asyncio.sleep(0.005)
            cur = _time.perf_counter()
            gaps.append(cur - prev)
            prev = cur
    t = asyncio.create_task(dog())
    await asyncio.sleep(0.01)
    try:
        await coro
    finally:
        run[0] = False
        await t
    return max(gaps) if gaps else 0.0


w = World("rv3")
g = w.held_goal(budget=9)
to_trial_pending(w, g.id)
seen = []
for nm in ("begin_experiment", "finish_experiment", "finish_action"):
    slow(w.store, nm, 0.15, seen)
loop_ids = []


async def _rv3():
    loop_ids.append(threading.get_ident())
    w.clock.t = max(w.clock(), min(x["due_at"] for x in w.store.wakes(P, g.id)))
    await R.tick(w.store, w.clock(), lambda b: w.deps, limit=1)

gap = asyncio.run(_watch(_rv3()))
names = {n for n, _ in seen}
check("RV3 lưu trữ chậm 150 ms ở giữ chỗ, ghi kết quả lượt thử và chốt phép thử: không bước nào chạy trên event loop",
      {"begin_experiment", "finish_experiment", "finish_action"} <= names and all(t != loop_ids[0] for _, t in seen),
      seen[:4])
check(f"RV3 event loop không bị chặn (khoảng lớn nhất {gap:.3f}s < 0.1s)", gap < 0.1)
check("RV3 phép thử vẫn đi hết và áp dụng như trước", w.exps(g.id)[0]["applied"] is True and w.engine.queries == 7)


def cancel_trial_during(name, delay=0.3):
    """Huỷ lần thức phép thử ĐÚNG lúc bước `name` của kho đang chạy ở luồng phụ. Trả (World, g, lease_seen)."""
    w = World(f"rv3-cancel-{name}")
    g = w.held_goal(budget=9)
    to_trial_pending(w, g.id)
    gate, info = threading.Event(), {}
    orig = getattr(w.store, name)

    def wrapped(*a, **k):
        gate.set()
        _time.sleep(delay)
        res = orig(*a, **k)
        with sqlite3.connect(str(w.path)) as c:
            info["lease_after_worker"] = c.execute("SELECT lease_owner FROM goals WHERE id=?", (g.id,)).fetchone()[0]
        return res
    setattr(w.store, name, wrapped)

    async def run():
        w.clock.t = max(w.clock(), min(x["due_at"] for x in w.store.wakes(P, g.id)))
        t = asyncio.create_task(R.advance(g.id, {"kind": "wake"}, w.deps))
        await asyncio.to_thread(gate.wait, 5)
        t.cancel()
        await asyncio.sleep(0)
        t.cancel()          # huỷ lặp
        try:
            await t
        except asyncio.CancelledError:
            pass
    asyncio.run(run())
    setattr(w.store, name, orig)
    return w, g, info


w, g, info = cancel_trial_during("finish_experiment")
with sqlite3.connect(str(w.path)) as c:
    lease_now = c.execute("SELECT lease_owner FROM goals WHERE id=?", (g.id,)).fetchone()[0]
check("RV3 huỷ (cả huỷ lặp) lúc đang chốt phép thử: worker chạy xong khi khoá VẪN giữ, khoá nhả sau đó, phép thử đã chốt",
      info.get("lease_after_worker") is not None and lease_now is None and w.exps(g.id)[0]["status"] == "finished"
      and w.exps(g.id)[0]["applied"] is True, (info, lease_now))
w, g, info = cancel_trial_during("begin_experiment")
check("RV3 huỷ lúc đang giữ chỗ phép thử: khoá giữ tới khi worker xong, phép thử còn running chờ đối soát",
      info.get("lease_after_worker") is not None and w.exps(g.id)[0]["status"] == "running" and w.engine.queries == 3)
w.clock.t += 3600
w.run_days(g.id, 1)
check("RV3 sau khoá hết hạn: hẹn đối soát chốt phép thử interrupted, hoàn hết 4 lượt, trả lượt giữ (calls 3), 0 lượt engine",
      w.exps(g.id)[0]["reason"] == "interrupted" and w.g(g.id).calls_used == 3 and w.hold(g.id)["status"] == "released"
      and w.engine.queries == 3, (w.exps(g.id)[0]["reason"], w.g(g.id).calls_used))
w, g, info = cancel_trial_during("begin_action")
acts = [x for x in w.store.actions(P, g.id) if x["kind"] == "trial"]
check("RV3 huỷ sau khi ghi ý định lượt thử, trước engine: action not_run, engine 0 lượt thêm",
      len(acts) == 1 and acts[0]["status"] == "cancelled" and acts[0]["receipt"].get("error_code") == "not_run"
      and w.engine.queries == 3, [(a["status"], a["receipt"].get("error_code")) for a in acts])
w.clock.t += 3600
w.run_days(g.id, 1)
check("RV3 đối soát hoàn cả lượt not_run: calls 3, lượt giữ released",
      w.exps(g.id)[0]["reason"] == "interrupted" and w.g(g.id).calls_used == 3 and w.hold(g.id)["status"] == "released",
      w.g(g.id).calls_used)

w = World("rv3-storage-error")
g = w.held_goal(budget=9)
to_trial_pending(w, g.id)
seen = []
slow(w.store, "finish_experiment", 0.0, seen, fail=[1])
w.tick()
with sqlite3.connect(str(w.path)) as c:
    lease_now = c.execute("SELECT lease_owner FROM goals WHERE id=?", (g.id,)).fetchone()[0]
check("RV3 lỗi lưu trữ lúc chốt phép thử: lần thức kết thúc có ghi lỗi, khoá được nhả, phép thử còn running",
      lease_now is None and w.exps(g.id)[0]["status"] == "running" and w.engine.queries == 7
      and w.pending(g.id, "trial_recovery"))
w.clock.t += 3600 * 4
w.run_days(g.id, 1)
check("RV3 sau lỗi lưu trữ: đối soát chốt interrupted, 4 lượt đã gọi vẫn tính, lượt giữ released (calls 7)",
      w.exps(g.id)[0]["reason"] == "interrupted" and w.g(g.id).calls_used == 7 and w.hold(g.id)["status"] == "released",
      (w.exps(g.id)[0]["reason"], w.g(g.id).calls_used))

# ═══════════════════ Hồi quy review mã vòng 2 (61d0d8ca): RV4, RV5 ═══════════════════

# RV4: lỗi file hệ thống SAU khi giữ chỗ đã commit (P2-1). Một file thường tên `trials` trong vùng làm việc làm mkdir
# thư mục con của phép thử thất bại thật (không giả lập lỗi kho).
def blocked_trial_root(w, gid):
    root = Path(w.g(gid).output_root)
    root.mkdir(parents=True, exist_ok=True)
    blocker = root / "trials"
    if blocker.is_dir():
        import shutil
        shutil.rmtree(blocker)
    blocker.write_text("cản", encoding="utf-8")
    return blocker


def rv4_state(w, gid):
    return {"exp": [(e["status"], e["reason"]) for e in w.exps(gid)], "calls": w.g(gid).calls_used,
            "hold": (w.hold(gid) or {}).get("status"), "lesson": (w.lesson(gid) or {}).get("status"),
            "pending": [r["code"] for r in w.pending(gid)], "q": w.engine.queries}


w = World("rv4")
g = w.held_goal(budget=9)
to_trial_pending(w, g.id)
blocker = blocked_trial_root(w, g.id)
w.tick()
st = rv4_state(w, g.id)
e = w.exps(g.id)[0]
check("RV4 mkdir lỗi sau khi giữ chỗ: phép thử được chốt (không báo nhầm là chưa tạo), lý do lỗi lưu trữ sau commit",
      st["exp"] == [("finished", "stopped")] and "storage_error_after_commit" in str(e["payload"].get("stop_detail")), st)
check("RV4 hoàn đủ lượt đã giữ (calls 3), trả lượt giữ, bài học unknown, 0 lượt engine thêm, không lý do treo",
      st["calls"] == 3 and st["hold"] == "released" and st["lesson"] == "unknown" and st["q"] == 3
      and "trial_recovery" not in st["pending"] and "method_trial" not in st["pending"], st)
blocker.unlink()
w.run_days(g.id, 2)
w.reopen()
w.run_days(g.id, 2)
check("RV4 khôi phục file hệ thống, khởi động lại, đối soát lặp: không đổi gì, không gọi thêm model",
      rv4_state(w, g.id) == st, rv4_state(w, g.id))

w = World("rv4-finish-fails")
g = w.held_goal(budget=9)
to_trial_pending(w, g.id)
blocker = blocked_trial_root(w, g.id)
seen = []
slow(w.store, "finish_experiment", 0.0, seen, fail=[1])
w.tick()
st = rv4_state(w, g.id)
check("RV4 mkdir lỗi rồi chốt cũng lỗi: phép thử còn running, lượt giữ còn, hẹn trial_recovery CÒN để tự chốt sau",
      st["exp"] == [("running", "")] and st["hold"] == "held" and "trial_recovery" in st["pending"] and st["q"] == 3, st)
blocker.unlink()
w.clock.t += 3600 * 4
w.reopen()
w.run_days(g.id, 1)
st = rv4_state(w, g.id)
check("RV4 lần thức đối soát sau đó: interrupted, hoàn đủ (calls 3), lượt giữ released, 0 lượt engine thêm",
      st["exp"] == [("finished", "interrupted")] and st["calls"] == 3 and st["hold"] == "released" and st["q"] == 3, st)
w.reopen()
w.run_days(g.id, 2)
check("RV4 đối soát lặp và mở lại: không trả hai lần", rv4_state(w, g.id) == st)

w = World("rv4-before-commit")
g = w.held_goal(budget=9)
to_trial_pending(w, g.id)
slow(w.store, "begin_experiment", 0.0, [], fail=[1])
w.tick()
check("RV4 lỗi lưu trữ TRƯỚC commit: không có phép thử, không giữ lượt, ghi đúng lỗi lưu trữ (không phải quyền)",
      not w.exps(g.id) and w.g(g.id).calls_used == 3 and w.lesson(g.id)["status"] == "skipped"
      and w.lesson(g.id)["status_reason"] == "storage_error" and w.engine.queries == 3,
      (w.lesson(g.id)["status"], w.lesson(g.id)["status_reason"]))

# RV5: đọc sổ đăng ký agent (ghim quyền) cũng chạy ngoài event loop (P2-2); đo cả hàm đọc, không chỉ hàm ghi.
w = World("rv5")
g = w.held_goal(budget=9)
to_trial_pending(w, g.id)
loop_tid, reads = [], []
_orig_abk = w.store.agent_by_key


def _abk(*a, **k):
    tid = threading.get_ident()
    reads.append(tid)
    if loop_tid and tid == loop_tid[0]:
        _time.sleep(0.25)
    return _orig_abk(*a, **k)


w.store.agent_by_key = _abk


async def _rv5():
    loop_tid.append(threading.get_ident())
    w.clock.t = max(w.clock(), min(x["due_at"] for x in w.store.wakes(P, g.id)))
    await R.tick(w.store, w.clock(), lambda b: w.deps, limit=1)

gap = asyncio.run(_watch(_rv5()))
check(f"RV5 mọi lần đọc agent khi chạy phép thử nằm ngoài event loop ({len(reads)} lần), loop không khựng ({gap:.3f}s)",
      reads and not [t for t in reads if t == loop_tid[0]] and gap < 0.1, (len(reads), gap))
check("RV5 phép thử vẫn thắng và áp dụng như trước", w.exps(g.id)[0]["applied"] is True and w.engine.queries == 7)

# ═══════════════════ A13: di chuyển ═══════════════════

old_db = Path(_STATE) / "pre-a3.sqlite3"
with sqlite3.connect(str(old_db)) as c:
    c.executescript(RS._SCHEMA.split("CREATE TABLE IF NOT EXISTS reactions")[0])
    for table, col, decl in RS._ADDED_COLUMNS:
        have = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in have:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    c.execute("INSERT INTO goals(id,brain_id,owner,revision,status,session_id,request_ref,idempotency_key,output_root,"
              "budget_calls,calls_used,paused,created_at,updated_at) VALUES('g_old','b','o',1,'active','','','k','/tmp',"
              "4,0,0,1,1)")
cols_before = {t: [r[1] for r in sqlite3.connect(str(old_db)).execute(f"PRAGMA table_info({t})")]
               for t in RS.PRE_A1_TABLES}
RS.GoalStore(old_db)
bak = Path(str(old_db) + ".pre-a3.bak")
m1 = bak.stat().st_mtime if bak.is_file() else None
RS.GoalStore(old_db)
cols_after = {t: [r[1] for r in sqlite3.connect(str(old_db)).execute(f"PRAGMA table_info({t})")]
              for t in RS.PRE_A1_TABLES}
check("A13 nâng lên A3: sao lưu pre-a3 một lần, bảng cũ không đổi cột, có đủ bảng A3",
      m1 is not None and bak.stat().st_mtime == m1 and cols_before == cols_after
      and all(sqlite3.connect(str(old_db)).execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone()
              for t in RS.A3_TABLES))

# ═══════════════════ A16: không ký tự gạch dài ═══════════════════

_dash = "—"
files = [ROOT / "server" / f for f in ("resonance_learning.py", "resonance.py", "resonance_store.py",
                                       "resonance_api.py", "resonance_heartbeat.py")]
files += [ROOT / "dashboard" / f for f in ("chat-resonance.js", "resonance-agent.js")]
files += [ROOT / "dashboard" / "i18n" / f for f in ("vi.json", "en.json")]
files += [ROOT / "docs" / "superpowers" / "specs" / "2026-10-09-resonance-a3-feedback-learning-design.md"]
bad = [str(f.name) for f in files if f.is_file() and _dash in f.read_text(encoding="utf-8")]
check("A16 không ký tự gạch dài trong mã, i18n và thiết kế A3", not bad, bad)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
