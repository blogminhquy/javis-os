"""Resonance A2: nhịp tim thích nghi, chạy trên mã thật.

    python tests/run.py resonance_a2 -v

Đi qua kho SQLite thật (`GoalStore`), `advance`, `tick`, cổng quyền thật của A1 và engine GIẢ (đếm số lần dựng
engine = số lượt model). Đồng hồ giả, không gọi model thật. Ma trận nghiệm thu: thiết kế
`docs/superpowers/specs/2026-10-08-resonance-a2-heartbeat-design.md` mục 13; các phản ví dụ của bốn vòng review
thiết kế (7504bf6a, e95a3260, fe92e753, cb11fc23) được chuyển thành ca ở đây.

Mỗi kịch bản dùng một kho riêng để lịch của kịch bản này không lẫn vào nhịp của kịch bản khác.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import datetime as _dt
import hashlib
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-a2-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import resonance as R  # noqa: E402
import resonance_heartbeat as HB  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402
RA.preapprove()  # A4: chủ dự án cho phép phạm vi ngay sau khi lập (D1); xem _resonance_agent.preapprove

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-a2-")).resolve())
(Path(BRAIN) / "Javis").mkdir(parents=True)
(Path(BRAIN) / "Inbox").mkdir(parents=True)
P = RS.Principal("agent", "javis", BRAIN)
OWNER = RS.Principal("owner", "owner", BRAIN)
T0 = 1_800_000_000.0
POL = HB.POLICY
DELIV = "Inbox/a2-viec.md"
USER = ("Viết giúp anh một ghi chú tổng hợp trong Inbox gồm báo cáo quý và máy lạnh, xong trước 8 giờ 20 sáng nay "
        "nhé, giữ tiêu đề Sample.")
GOOD = "# Sample\n\nBáo cáo quý, máy lạnh. Ghi chú tổng hợp đủ hai việc anh nhờ.\n"
HALF = "# Sample\n\nBáo cáo quý thôi.\n"
NONE = "# Sample\n\nChưa có gì.\n"


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class Engine:
    """Engine giả. `texts`: danh sách trả lần lượt (hết thì lặp cái cuối); `events`: thay cho văn bản."""

    def __init__(self, texts=(GOOD,), events=None, on_query=None):
        self.texts, self.events, self.on_query = list(texts), events, on_query
        self.queries = 0
        self.max_wall_s = None

    def is_available(self):
        return True

    async def query(self, prompt):
        i = min(self.queries, len(self.texts) - 1)
        self.queries += 1
        if self.on_query:
            self.on_query()
        evs = self.events(self.queries) if callable(self.events) else self.events
        for ev in (evs or [{"type": "final", "content": self.texts[i], "tokens_in": 1, "tokens_out": 1}]):
            yield ev


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

    async def __call__(self, goal, kind, text, card=""):
        self.sent.append((goal.id, kind, text))
        return True


class World:
    """Một kịch bản: kho riêng, trợ lý đã bật, đồng hồ giả, engine giả đếm lượt."""
    _n = 0

    def __init__(self, name, engine=None):
        World._n += 1
        self.path = Path(_STATE) / f"{name}-{World._n}.sqlite3"
        self.store = RS.GoalStore(self.path)
        self.agent = RA.enable(self.store, BRAIN)
        self.clock = Clock()
        self.engine = engine or Engine()
        self.built = 0
        self.notes = Notes()
        self.deps = self.make_deps()

    def make_deps(self):
        def factory(system_prompt, tag):
            self.built += 1
            return self.engine, {"provider": "fake", "model": "fake-1", "text_only": True}
        return R.GoalDeps(engine_factory=factory, budget=R.CallBudget(0), clock=self.clock, store=self.store,
                          principal=P, brain_root=BRAIN, evidence=Evidence(), notify=self.notes)

    def reopen(self):
        """Khởi động lại thật: kho mở lại từ file, deps mới; trạng thái chỉ còn những gì đã lưu."""
        self.store = RS.GoalStore(self.path)
        self.deps = self.make_deps()

    def goal(self, budget=6, criteria=None, guards=None, horizon=None, mode="achieve", path=DELIV):
        crit = criteria or [
            {"description": "Có báo cáo quý", "evaluator": "artifact_contract",
             "params": {"path": path, "must_contain": ["báo cáo quý"]}},
            {"description": "Có máy lạnh", "evaluator": "artifact_contract",
             "params": {"path": path, "must_contain": ["máy lạnh"]}}]
        prop = {"understanding": "Ghi chú tổng hợp hai việc trong Inbox", "criteria": crit,
                "relevant_quote": "Viết giúp anh một ghi chú tổng hợp trong Inbox",
                "horizon": horizon or {"kind": "review", "at_iso": "2027-02-20T09:00:00+07:00"},
                "stage": "delivery", "mode": mode}
        if guards:
            prop["guards"] = guards
        World._n += 1
        mid = 10_000 + World._n
        deps0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi"}), budget=R.CallBudget(0),
                           store=self.store)
        g = asyncio.run(R.form_goal(R.message_ref("s-a2", mid), {
            "principal": P, "brain_root": BRAIN, "session_id": "s-a2", "message_id": mid, "user_text": USER,
            "constraints": [], "budget_calls": budget, "proposal": prop, **RA.ctx(self.agent)}, deps0))
        (Path(BRAIN) / path).unlink(missing_ok=True)
        return g

    def tick(self, limit=3):
        return asyncio.run(R.tick(self.store, self.clock(), lambda b: self.deps, limit=limit))

    def adv(self, gid, kind="wake"):
        return asyncio.run(R.advance(gid, {"kind": kind}, self.deps))

    def due(self, gid, kind="work"):
        return next((w["due_at"] for w in self.store.wakes(P, gid) if w["kind"] == kind), None)

    def run_until(self, gid, end, max_wakes=500):
        """Chạy nhịp tới `end`: mỗi lần nhảy đồng hồ tới lịch vật lý sớm nhất của mục tiêu. Trả số lần thức."""
        n = 0
        while n < max_wakes:
            dues = [w["due_at"] for w in self.store.wakes(P, gid)]
            if not dues or min(dues) > end:
                break
            self.clock.t = max(self.clock.t, min(dues))
            self.tick(limit=10)
            n += 1
        self.clock.t = max(self.clock.t, end)
        return n

    def state(self, gid):
        return self.store.run_state(P, gid) or {}

    def log(self, gid):
        return self.store.wake_log(P, gid)

    def reasons(self, gid, state="pending"):
        return self.store.reasons(P, gid, state=state)

    def outbox(self, gid, kind):
        with sqlite3.connect(str(self.path)) as c:
            return c.execute("SELECT COUNT(*) FROM outbox WHERE goal_id=? AND kind=?", (gid, kind)).fetchone()[0]

    def feedback(self, gid, kind="outcome_rejected", key=None, data=None):
        g = self.store.get(OWNER, gid)
        return self.store.record_feedback(OWNER, gid, g.revision, kind, data or {}, key)


def write(rel, text):
    f = Path(BRAIN) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8", newline="\n")


def iso(t):
    return _dt.datetime.fromtimestamp(t, _dt.timezone.utc).isoformat()


# ═══════════════════ Chính sách thuần ═══════════════════

check("chuỗi: tụt rồi hồi về mốc cũ không phải tiến bộ",
      HB.chain_from([{"met_count": 1}, {"met_count": 0}, {"met_count": 1}]).stall == 2)
check("chuỗi: vượt mốc tốt nhất là tiến bộ", HB.chain_from([{"met_count": 0}, {"met_count": 1}]).stall == 0)
check("chuỗi: đầu ra giữ lại (held) không phải lỗi, không phải tiến bộ",
      HB.chain_from([{"met_count": 1}, {"met_count": None, "error": "held"}]) == HB.Chain(1, 0, 0, ""))
check("trần chung: còn đúng lượt dự phòng thì không thử lại tự động, cả hai nhánh",
      not HB.auto_allowed("retry_not_met", HB.Chain(), 1)[0] and not HB.auto_allowed("error_retry", HB.Chain(), 1)[0])
check("ba lượt lỗi tổng cộng thì dừng", HB.auto_allowed("error_retry", HB.Chain(fails=2), 5)[0]
      and not HB.auto_allowed("error_retry", HB.Chain(fails=3), 5)[0])
check("lỗi cố định không thử lại", not HB.auto_allowed("error_retry", HB.Chain(fails=1, last_error="engine_build"), 5)[0])
check("mã lạ và các mã kiểm không mở lượt model kể cả revision chưa có đầu ra",
      HB.decide([{"code": "review"}, {"code": "deadline"}, {"code": "mystery"}], attempted=False, outcome="not_met",
                left=5, chain=HB.Chain()).action == "evaluate")
check("gần hạn: còn 20 phút thì kiểm đúng hạn", HB.check_due(T0, 6 * 3600, {"kind": "deadline", "at": T0 + 1200})
      == (T0 + 1200, "deadline"))
check("gần hạn: còn 2 giờ thì kiểm ở nửa thời gian còn lại", HB.check_due(T0, 6 * 3600, {"kind": "deadline",
                                                                                     "at": T0 + 7200})
      == (T0 + 3600, "deadline"))

# ═══════════════════ Nhịp và lượt model ═══════════════════

# Duy trì đạt, sản phẩm không đổi, 30 ngày: 0 lượt sau lượt đầu, xem lại giãn dần.
w = World("maintain", Engine([GOOD]))
g = w.goal(mode="maintain", horizon={"kind": "maintain"})
w.tick()
first = w.built
n = w.run_until(g.id, T0 + 30 * 86400)
gaps = [round((r["next_due_at"] - r["created_at"]) / 3600) for r in w.log(g.id)
        if r.get("next_code") == "review" and r.get("next_due_at")]
check("duy trì đạt 30 ngày: chỉ một lượt model (lượt đầu)", first == 1 and w.built == 1)
check(f"duy trì đạt 30 ngày: xem lại giãn dần 6, 12, 24... tới 7 ngày ({gaps[:6]})",
      gaps[:4] == [6, 12, 24, 48] and max(gaps) == 168 and n <= 12)
check("mọi lần thức có dòng sổ", len(w.log(g.id)) >= n)
revs = [r for r in w.reasons(g.id, state=None) if r["code"] == "review"]
check("hai lần xem lại định kỳ liên tiếp là hai lý do khác nhau, đều được phục vụ",
      len(revs) >= 2 and len({r["source_ref"] for r in revs}) == len(revs)
      and sum(1 for r in revs if r["state"] == "served") >= 2)

# Đạt và chờ người dùng xác nhận: 30 ngày 0 lượt.
w = World("human", Engine([GOOD]))
g = w.goal(criteria=[{"description": "Có báo cáo quý", "evaluator": "artifact_contract",
                      "params": {"path": DELIV, "must_contain": ["báo cáo quý"]}},
                     {"description": "Anh duyệt bản này", "evaluator": "human_confirmation"}])
w.tick()
b0 = w.built
w.run_until(g.id, T0 + 30 * 86400)
check("chờ người dùng xác nhận 30 ngày: không lượt model nào thêm, không lịch work",
      b0 == 1 and w.built == 1 and w.state(g.id).get("block_reason") == "human_confirmation" and w.due(g.id) is None)

# Ảnh chụp chỉ có review / mã lạ, revision chưa có đầu ra: 0 lượt.
w = World("checkonly")
g = w.goal()
w.store.serve_reasons(P, g.id, [r["id"] for r in w.reasons(g.id)], "test")
w.store.add_timer(P, g.id, "review", T0, T0)
w.store.add_timer(P, g.id, "mystery_code", T0, T0)
w.store.recompute_wake(P, g.id)
w.tick()
check("chỉ review và mã lạ, chưa có đầu ra: không gọi model", w.built == 0 and w.log(g.id))

# Mọi lối ra không gác phục vụ hết lý do đã tới hạn: bước đầu khi revision đã có lượt (ví dụ `assigned` của mục tiêu
# cũ đã làm) không nằm chờ rồi kéo lịch về quá khứ mỗi nhịp.
w = World("start-attempted", Engine([HALF]))
g = w.goal(budget=8)
w.tick()
w.store.supersede_timers(P, g.id, ("retry",))
with sqlite3.connect(str(w.path)) as _c:
    _c.execute("INSERT INTO wake_reasons(goal_id,brain_id,wake_kind,code,origin,slot,revision,source_ref,due_at,created_at) "
               "VALUES(?,?,'work','assigned','event','',1,'ev:test',?,?)", (g.id, BRAIN, T0, T0))
w.store.recompute_wake(P, g.id)
claimed = sum(w.tick() for _ in range(5))
check("bước đầu khi đã có lượt: phục vụ một lần, không thức lại mỗi nhịp, không gọi model",
      claimed == 1 and w.built == 1 and not any(r["code"] == "assigned" for r in w.reasons(g.id)))

# Bế tắc: hai lượt không vượt mốc thì dừng thử, chờ, không thất bại.
w = World("stall", Engine([HALF, HALF, HALF, HALF]))
g = w.goal(budget=8)
w.run_until(g.id, T0 + 6 * 3600)
check("bế tắc: lượt đầu + 2 lần thử không tiến bộ = 3 lượt, rồi dừng", w.built == 3)
check("bế tắc: chờ (stalled), mục tiêu vẫn active, báo một lần",
      w.state(g.id).get("block_reason") == "stalled" and w.store.get(P, g.id).status == "active"
      and w.outbox(g.id, "goal.stalled") == 1)
w.run_until(g.id, T0 + 10 * 86400)
check("bế tắc: không gọi thêm về sau", w.built == 3)
w.feedback(g.id, "goal_fit_confirmed", key="fb-stall")
w.engine.texts = [GOOD]
w.engine.queries = 0
w.tick()
check("góp ý sau bế tắc: đúng một lượt, đạt", w.built == 4 and w.store.get(P, g.id).status == "succeeded")

# Tiến bộ thì được thử tiếp.
w = World("progress", Engine([NONE, HALF, GOOD]))
g = w.goal(budget=8)
w.run_until(g.id, T0 + 3 * 3600)
check("lượt sau vượt mốc tốt nhất thì được thử tiếp tới khi đạt",
      w.built == 3 and w.store.get(P, g.id).status == "succeeded")

# Lượt dự phòng: còn đúng một lượt thì thử lại tự động không dùng; góp ý thì dùng được.
w = World("reserve", Engine([HALF, GOOD]))
g = w.goal(budget=2)
w.run_until(g.id, T0 + 86400)
check("còn một lượt: không tự thử lại, chờ", w.built == 1 and w.state(g.id).get("block_reason") == "stalled")
w.feedback(g.id, "goal_fit_confirmed", key="fb-res")
w.tick()
check("còn một lượt: góp ý dùng được lượt cuối", w.built == 2 and w.store.get(P, g.id).status == "succeeded")

# Lỗi tạm thời: ba lượt lỗi tổng cộng rồi dừng, báo một lần ngừng.
ERR = [{"type": "final", "content": "upstream overloaded", "is_error": True, "subtype": "error"}]
w = World("transient", Engine(events=ERR))
g = w.goal(budget=8)
w.run_until(g.id, T0 + 3 * 86400)
check("lỗi tạm thời: tối đa 3 lượt lỗi tổng cộng", w.built == 3)
check("lỗi tạm thời: hết trần thì gác, không hẹn work", w.state(g.id).get("run_state") == "blocked"
      and w.due(g.id) is None)
with sqlite3.connect(str(w.path)) as _c:
    finals = [r for r in _c.execute("SELECT payload_json FROM outbox WHERE goal_id=? AND kind='goal.blocked'",
                                    (g.id,)).fetchall()]
check("lỗi tạm thời: báo một lần (cùng khoá revision)", len(finals) == 1)

# Lỗi cố định: không thử lại.
w = World("fixed")
w.deps = R.GoalDeps(**{**w.deps.__dict__, "engine_factory": lambda s, t: (None, {"blocked": "engine_build"})})
g = w.goal(budget=8)
w.run_until(g.id, T0 + 3 * 86400)
acts = [x for x in w.store.actions(P, g.id) if x["kind"] == "work"]
check("lỗi cố định: không tự thử lại", len(acts) == 1 and w.due(g.id) is None
      and w.state(g.id).get("run_state") == "blocked")

# Chết giữa lượt model: đối soát, tính một lượt lỗi, thử lại theo trần.
w = World("crash", Engine([GOOD]))
g = w.goal(budget=6)
snap = [r["id"] for r in w.reasons(g.id)]
held = R._agent_intent(w.store.get(P, g.id), w.deps)
act = w.store.begin_action(P, g.id, 1, "work", lease_until=T0 + 10, now=T0,
                           intent={"prompt_kind": "work", "wake_reasons": snap, **held})
check("chết giữa lượt: lý do đã phục vụ cùng ý định", set(act["served"]) == set(snap) and not w.reasons(g.id, "pending")
      or all(r["code"] == "recovery" for r in w.reasons(g.id)))
w.reopen()
w.clock.t = T0 + 11
w.tick()
log_rows = [r for r in w.log(g.id) if r["error_code"] == "interrupted"]
check("chết giữa lượt: đối soát ghi một lượt lỗi interrupted, rồi thử lại trong trần đúng một lượt",
      len(log_rows) == 1 and w.built == 1 and w.store.get(P, g.id).status == "succeeded")

# Hạn chót còn 20 phút; qua hạn chưa đạt.
w = World("deadline", Engine([HALF, HALF, HALF]))
dl = {"kind": "deadline", "from_user": True, "quote": "xong trước 8 giờ 20 sáng nay", "at_iso": iso(T0 + 1200)}
g = w.goal(budget=8, horizon=dl)
w.tick()
pend = {r["code"]: r["due_at"] for r in w.reasons(g.id)}
check("thử lại phút 15 và kiểm hạn phút 20 cùng chờ",
      pend.get("retry_not_met") == T0 + 900 and pend.get("deadline") == T0 + 1200)
w.clock.t = T0 + 300
w.store.add_timer(P, g.id, "deadline", T0 + 300, T0)     # một lần kiểm hạn sớm (phút 5)
w.store.recompute_wake(P, g.id)
w.tick()
pend = {r["code"]: r["due_at"] for r in w.reasons(g.id)}
check("kiểm hạn ở phút 5 không gọi model, không xoá hay chạy sớm thử lại",
      w.built == 1 and pend.get("retry_not_met") == T0 + 900 and w.due(g.id) <= T0 + 900)
w.reopen()
pend2 = {r["code"]: r["due_at"] for r in w.reasons(g.id)}
check("khởi động lại khi có hai nghĩa vụ: cả hai còn, đúng mốc", pend2.get("retry_not_met") == T0 + 900)
w.clock.t = T0 + 900
w.tick()
check("phút 15: thử lại đúng một lượt", w.built == 2)
w.run_until(g.id, T0 + 1300)
check("qua hạn chưa đạt: báo một lần, không gia hạn, không kết luận",
      w.outbox(g.id, "goal.deadline_passed") == 1 and w.store.get(P, g.id).status == "active"
      and w.store.get(P, g.id).horizon.get("at") == T0 + 1200)

# Backoff một giờ và hạn chót sau 20 phút: kiểm hạn không kéo backoff thành lượt sớm.
w = World("backoff", Engine(events=lambda n: ERR if n == 1 else None, texts=[GOOD]))
g = w.goal(budget=8, horizon={"kind": "deadline", "from_user": True, "quote": "xong trước 8 giờ 20 sáng nay",
                              "at_iso": iso(T0 + 1200)})
w.tick()
pend = {r["code"]: r["due_at"] for r in w.reasons(g.id)}
w.run_until(g.id, T0 + 3000)
check("backoff 1 giờ, hạn chót phút 20: kiểm hạn không gọi model",
      pend.get("error_retry") == T0 + 3600 and w.built == 1)
w.run_until(g.id, T0 + 3700)
check("tới mốc backoff mới thử lại", w.built == 2)

# Cùng thời điểm: thử lại và kiểm hạn cùng tới hạn.
w = World("sametime", Engine([HALF, GOOD]))
g = w.goal(budget=8)
w.tick()
w.store.add_timer(P, g.id, "deadline", T0 + 900, T0)
w.clock.t = T0 + 900
w.tick()
row = w.log(g.id)[-1]
check("thử lại và kiểm hạn cùng lúc: một lần thức, một quyết định, cả hai được phục vụ",
      w.built == 2 and row["decision"] == "work" and set(row["codes"]) >= {"retry_not_met", "deadline"})

# Hết hạn mức: gác, giữ lý do, 0 lượt.
w = World("budget", Engine([HALF]))
g = w.goal(budget=1)
w.tick()
w.feedback(g.id, "goal_fit_confirmed", key="fb-b")
w.tick()
check("hết hạn mức: gác budget, góp ý vẫn chờ, không gọi thêm",
      w.built == 1 and w.state(g.id).get("block_reason") == "budget"
      and any(r["code"] == "feedback" for r in w.reasons(g.id)) and w.due(g.id) is None)

# ═══════════════════ Vòng đời lý do ═══════════════════

# Góp ý rồi tạm dừng trước lần thức, rồi tiếp tục.
w = World("pause-fb", Engine([HALF, GOOD]))
g = w.goal(budget=8)
w.tick()
w.store.supersede_timers(P, g.id, ("retry",))
w.feedback(g.id, key="fb-p")
w.store.set_paused(OWNER, g.id, True)
w.tick()
check("tạm dừng: không gọi model, góp ý vẫn chờ", w.built == 1 and any(r["code"] == "feedback" for r in w.reasons(g.id)))
w.store.set_paused(OWNER, g.id, False)
w.tick()
w.tick()
check("tiếp tục: góp ý xử lý đúng một lần", w.built == 2 and not any(r["code"] == "feedback" for r in w.reasons(g.id)))

# Góp ý rồi tắt trợ lý, bật lại.
w = World("off-fb", Engine([HALF, GOOD]))
g = w.goal(budget=8)
w.tick()
w.store.supersede_timers(P, g.id, ("retry",))
w.feedback(g.id, key="fb-o")
RA.disable(w.store, BRAIN)
w.tick()
check("trợ lý tắt: không gọi model, góp ý vẫn chờ", w.built == 1 and any(r["code"] == "feedback" for r in w.reasons(g.id)))
w.agent = RA.enable(w.store, BRAIN)
w.store.wake_agent_goals(BRAIN, w.agent["agent_key"])
w.tick()
w.tick()
check("bật lại: góp ý xử lý đúng một lần", w.built == 2)

# Góp ý trong lúc guard chưa đọc được, rồi đọc lại được.
_real_obs = R.observe_guards
_flag = {"v": "unknown"}


def _fake_obs(goal, deps):
    return tuple({"id": x.get("id"), "description": x.get("description", ""), "verdict": _flag["v"], "reason": "giả"}
                 for x in goal.guards)


GUARD = [{"description": "Tiêu đề Sample còn giữ", "evaluator": "artifact_contract",
          "params": {"path": DELIV, "must_contain": ["Sample"]}}]
R.observe_guards = _fake_obs
try:
    _flag["v"] = "clear"
    w = World("gu-fb", Engine([HALF, GOOD]))
    g = w.goal(budget=8, guards=GUARD)
    w.tick()
    w.store.supersede_timers(P, g.id, ("retry",))
    w.feedback(g.id, key="fb-g")
    _flag["v"] = "unknown"
    w.tick()
    check("guard chưa đọc được: 0 lượt, góp ý vẫn chờ", w.built == 1 and w.state(g.id).get("block_reason") == "guard_unknown"
          and any(r["code"] == "feedback" for r in w.reasons(g.id)))
    check("guard chưa đọc được: lịch là mốc guard_recheck", abs(w.due(g.id) - (w.clock() + POL["REVIEW_MIN_S"])) < 1)
    _flag["v"] = "clear"
    w.clock.t = w.due(g.id)
    w.tick()
    check("guard đọc lại được: góp ý xử lý đúng một lần", w.built == 2)

    # Quan sát trong lúc tạm dừng không đụng góp ý.
    w = World("obs-pause", Engine([HALF]))
    g = w.goal(budget=8, guards=GUARD)
    w.tick()
    w.feedback(g.id, key="fb-op")
    w.store.set_paused(OWNER, g.id, True)
    w.clock.t = w.due(g.id, "observe")
    w.tick()
    check("quan sát khi tạm dừng: có chạy, góp ý vẫn chờ",
          w.log(g.id)[-1]["wake_kind"] == "observe" and any(r["code"] == "feedback" for r in w.reasons(g.id)))
    _flag["v"] = "triggered"
    w.clock.t = w.due(g.id, "observe")
    w.tick()
    check("tạm dừng mà guard chạm: vẫn phát hiện, chốt guard, báo",
          w.state(g.id).get("block_reason") == "guard" and w.outbox(g.id, "goal.guard") == 1)
    _flag["v"] = "clear"

    # Chờ xác nhận, cách hiểu bị bác: guard chạm vẫn phát hiện.
    for label, setup in (("chờ xác nhận", "human"), ("cách hiểu bị bác", "fit")):
        w = World(f"obs-{setup}", Engine([GOOD]))
        crit = None
        if setup == "human":
            crit = [{"description": "Có báo cáo quý", "evaluator": "artifact_contract",
                     "params": {"path": DELIV, "must_contain": ["báo cáo quý"]}},
                    {"description": "Anh duyệt", "evaluator": "human_confirmation"}]
        g = w.goal(budget=8, guards=GUARD, criteria=crit, **({} if crit else {"mode": "maintain",
                                                                     "horizon": {"kind": "maintain"}}))
        w.tick()
        if setup == "fit":
            w.feedback(g.id, "goal_fit_rejected", key="fb-fit")
        _flag["v"] = "triggered"
        w.clock.t = w.due(g.id, "observe")
        w.tick()
        check(f"{label}, guard chạm: vẫn phát hiện", w.state(g.id).get("block_reason") == "guard")
        _flag["v"] = "clear"

    # Tắt trợ lý có guard: báo mất theo dõi một lần mỗi đợt; thẻ hiện đã ngừng; bật lại quan sát ngay.
    w = World("lost", Engine([GOOD]))
    g = w.goal(budget=8, guards=GUARD, mode="maintain", horizon={"kind": "maintain"})
    w.tick()
    RA.disable(w.store, BRAIN)
    w.clock.t = w.due(g.id, "observe")
    w.tick()
    v = R.goal_view(w.store, P, g.id, BRAIN)
    check("tắt trợ lý: báo monitoring_lost một lần, thẻ hiện không còn theo dõi, 0 lượt thêm",
          w.outbox(g.id, "goal.monitoring_lost") == 1 and v["observe"]["state"] == "lost" and w.built == 1
          and w.due(g.id, "observe") is None)
    w.agent = RA.enable(w.store, BRAIN)
    w.store.wake_agent_goals(BRAIN, w.agent["agent_key"])
    check("bật lại: hẹn quan sát ngay", w.due(g.id, "observe") is not None and w.due(g.id, "observe") <= time.time() + 1)
    w.tick()
    check("bật lại: thẻ hiện đang theo dõi", R.goal_view(w.store, P, g.id, BRAIN)["observe"]["state"] == "on")
    RA.disable(w.store, BRAIN)
    w.clock.t = max(w.clock.t, w.due(g.id, "observe") or w.clock.t)
    w.store.set_wake(P, g.id, "observe", w.clock.t, "test")
    w.tick()
    check("tắt lần hai sau khi bật lại: báo thêm một lần", w.outbox(g.id, "goal.monitoring_lost") == 2)
    w.agent = RA.enable(w.store, BRAIN)

    # ═══ Vòng 3: thử lại tới hạn khi bị gác ═══
    for gate, recheck in (("guard_unknown", "guard_recheck"), ("agent_off", "agent_recheck")):
        w = World(f"park-{gate}", Engine([HALF, GOOD]))
        g = w.goal(budget=8, guards=GUARD if gate == "guard_unknown" else None)
        w.tick()
        retry_at = next(r["due_at"] for r in w.reasons(g.id) if r["code"] == "retry_not_met")
        if gate == "guard_unknown":
            _flag["v"] = "unknown"
        else:
            RA.disable(w.store, BRAIN)
        w.clock.t = retry_at
        w.tick()
        due = w.due(g.id)
        check(f"thử lại tới hạn khi {gate}: 0 lượt model, thử lại còn chờ",
              w.built == 1 and any(r["code"] == "retry_not_met" for r in w.reasons(g.id)))
        check(f"thử lại tới hạn khi {gate}: lịch là mốc {recheck}",
              due is not None and abs(due - (retry_at + POL["REVIEW_MIN_S"])) < 1)
        claimed = 0
        for k in range(1, 50):
            w.clock.t = retry_at + 30 * k
            claimed += w.tick()
        check(f"thử lại tới hạn khi {gate}: các nhịp ở giữa không nhận mục tiêu", claimed == 0)
        w.reopen()
        check(f"khởi động lại khi bị gác ({gate}): lịch giữ mốc gỡ gác", w.due(g.id) == due)
        claimed = 0
        for k in range(50, 80):
            w.clock.t = retry_at + 30 * k
            claimed += w.tick()
        check(f"khởi động lại khi bị gác ({gate}): không thức dày", claimed == 0)
        if gate == "guard_unknown":
            _flag["v"] = "clear"
            w.clock.t = due
            w.tick()
        else:
            w.agent = RA.enable(w.store, BRAIN)
            w.store.wake_agent_goals(BRAIN, w.agent["agent_key"])
            w.tick()
        check(f"gỡ gác ({gate}): thử lại quá giờ chạy đúng một lần", w.built == 2)
        w.tick()
        check(f"gỡ gác ({gate}): không chạy lần hai", w.built == 2)
        RA.enable(w.store, BRAIN)

    # Gỡ gác trước mốc backoff: không chạy sớm, không đặt lại chuỗi lỗi.
    w = World("park-backoff", Engine(events=lambda n: ERR if n == 1 else None, texts=[GOOD]))
    g = w.goal(budget=8)
    w.tick()
    RA.disable(w.store, BRAIN)
    w.clock.t = T0 + 600
    w.store.add_timer(P, g.id, "agent_recheck", T0 + 600, T0)
    w.store.recompute_wake(P, g.id)
    w.tick()
    w.agent = RA.enable(w.store, BRAIN)
    w.store.wake_agent_goals(BRAIN, w.agent["agent_key"])
    w.tick()
    check("gỡ gác trước mốc backoff: không chạy sớm, lịch về mốc backoff",
          w.built == 1 and w.due(g.id) == T0 + 3600)
    check("gỡ gác không đặt lại chuỗi lỗi", R._chain(w.store, P, w.store.get(P, g.id)).fails == 1)

    # Tạm dừng có thử lại tới hạn: không có lịch work.
    w = World("park-pause", Engine([HALF]))
    g = w.goal(budget=8)
    w.tick()
    w.store.set_paused(OWNER, g.id, True)
    check("tạm dừng: không có lịch work; thử lại còn chờ, giữ giờ",
          w.due(g.id) is None and any(r["code"] == "retry_not_met" and r["due_at"] == T0 + 900 for r in w.reasons(g.id)))
    w.clock.t = T0 + 900
    check("tạm dừng: nhịp không nhận mục tiêu", w.tick() == 0)

    # Chờ bàn giao và source_drift: thử lại cũ không thắng hẹn chờ.
    w = World("park-drift", Engine([HALF, GOOD]))
    g = w.goal(budget=8)
    w.tick()
    write(DELIV, "# Sample\n\nAnh sửa tay.\n")
    w.store.add_timer(P, g.id, "review", T0 + 60, T0)
    w.store.recompute_wake(P, g.id)
    w.clock.t = T0 + 60
    w.tick()
    due = w.due(g.id)
    check("source_drift: lịch là hẹn drift_recheck, thử lại cũ không thắng",
          w.state(g.id).get("block_reason") == "source_drift" and due == T0 + 60 + POL["DRIFT_RECHECK_MIN_S"]
          and any(r["code"] == "retry_not_met" for r in w.reasons(g.id)))

    # Hàng đợi: 5 mục tiêu bị gác có thử lại cũ, 3 mục tiêu sẵn sàng.
    w = World("queue", Engine([HALF]))
    parked = []
    _flag["v"] = "clear"
    for i in range(5):
        gp = w.goal(budget=8, guards=GUARD)
        parked.append(gp)
    w.tick(limit=10)
    w.tick(limit=10)
    _flag["v"] = "unknown"
    w.clock.t = T0 + 900
    w.tick(limit=10)
    w.tick(limit=10)
    _flag["v"] = "clear"
    ready = [w.goal(budget=8) for _ in range(3)]
    q0 = w.built
    w.clock.t = T0 + 930
    n = w.tick(limit=3)
    check("hàng đợi: nhịp kế tiếp nhận cả 3 mục tiêu sẵn sàng, mục tiêu bị gác không chiếm suất",
          n == 3 and w.built == q0 + 3 and all(w.state(gp.id).get("block_reason") == "guard_unknown" for gp in parked))
finally:
    R.observe_guards = _real_obs

# Góp ý đến trong lúc lượt model đang chạy.
w = World("during", Engine([HALF, GOOD]))
g = w.goal(budget=8)
w.engine.on_query = lambda: w.feedback(g.id, key="fb-during") if w.engine.queries == 1 else None
w.tick()
check("góp ý giữa lượt: còn chờ, lịch về now sau lượt",
      any(r["code"] == "feedback" for r in w.reasons(g.id)) and w.due(g.id) <= time.time() + 1)
w.engine.on_query = None
w.tick()
check("góp ý giữa lượt: xử lý ở lần sau, đúng một lượt", w.built == 2)

# Giao lại cùng góp ý trước và sau khi phục vụ.
w = World("redeliver", Engine([HALF, HALF, GOOD]))
g = w.goal(budget=8)
w.tick()
w.store.supersede_timers(P, g.id, ("retry",))
w.feedback(g.id, key="same")
w.feedback(g.id, key="same")
check("giao lại khi còn chờ: một dòng", sum(1 for r in w.reasons(g.id, None) if r["code"] == "feedback") == 1)
w.tick()
w.feedback(g.id, key="same")
w.tick()
check("giao lại sau khi phục vụ: không xử lý lần hai", w.built == 2
      and sum(1 for r in w.reasons(g.id, None) if r["code"] == "feedback") == 1)

# Chết sau khi nhận lịch, trước khi ghi sổ: lý do còn, xử lý đúng một lần.
w = World("claimcrash", Engine([GOOD]))
g = w.goal()
row = w.store.due_wakeups(w.clock(), 5)[0]
w.store.claim_wake(P, row["goal_id"], row["kind"], row["due_at"], w.clock() + 900)
w.reopen()
check("chết sau khi nhận lịch: lý do created còn chờ", any(r["code"] == "created" for r in w.reasons(g.id)))
w.clock.t += 901
w.tick()
w.tick()
check("chết sau khi nhận lịch: xử lý đúng một lần", w.built == 1)

# Quay về 0.87 làm việc (lượt không gắn lý do), rồi nâng lại: đối soát theo lúc lượt BẮT ĐẦU.
w = World("reconcile", Engine([GOOD]))
g = w.goal()
fb_before = w.feedback(g.id, key="fb-before")
time.sleep(0.01)
start = time.time()
with sqlite3.connect(str(w.path)) as c:
    c.execute("INSERT INTO actions(id,goal_id,revision,kind,seq,status,lease_until,intent_json,receipt_json,created_at,"
              "updated_at) VALUES('act_old087',?,1,'work',1,'succeeded',NULL,'{}','{}',?,?)", (g.id, start, start))
time.sleep(0.01)
fb_after = w.feedback(g.id, key="fb-after")
w.reopen()
st = {r["source_ref"]: r for r in w.reasons(g.id, None)}
check("nâng lại: sự kiện trước lúc lượt cũ bắt đầu được chốt theo lượt đó",
      st[f"fb:{fb_before['event_id']}"]["state"] == "served"
      and st[f"fb:{fb_before['event_id']}"]["settled_by"] == "reconciled:act_old087")
check("nâng lại: sự kiện đến sau lúc lượt cũ bắt đầu vẫn chờ", st[f"fb:{fb_after['event_id']}"]["state"] == "pending")

# Tin báo của trợ lý vào chat không sinh lý do.
w = World("notify", Engine([GOOD]))
g = w.goal()
w.tick()
before = len(w.reasons(g.id, None))
asyncio.run(R.drain_outbox(w.store, w.notes))
check("tin báo của trợ lý: không sinh lý do, không lần thức", len(w.reasons(g.id, None)) == before and w.notes.sent)

# Hai tick song song trên cùng kho.
w = World("twotick", Engine([GOOD]))
g = w.goal()


async def _two():
    return await asyncio.gather(R.tick(w.store, w.clock(), lambda b: w.deps),
                                R.tick(RS.GoalStore(w.path), w.clock(), lambda b: w.make_deps()))


asyncio.run(_two())
check("hai tick song song: tối đa một lượt model", w.built == 1)

# Lý do của revision cũ.
w = World("stale", Engine([HALF, HALF]))
g = w.goal(budget=8)
w.tick()
w.feedback(g.id, key="fb-old")
g2, _, _ = R.revise_goal(w.store, P, g.id, 1, {"understanding": "Ghi chú tổng hợp hai việc, bản sửa",
                                                    "relevant_quote": "Viết giúp anh một ghi chú tổng hợp trong Inbox"},
                         {"message_ref": R.message_ref("s-a2", 99_001), "session_id": "s-a2", "message_id": 99_001,
                          "user_text": USER, **RA.ctx(w.agent)})
w.tick()
stale = [r for r in w.reasons(g.id, None) if r["settled_by"] == "stale_revision"]
check("lý do revision cũ: chốt stale_revision, không đặt lại trần của revision mới",
      {r["code"] for r in stale} >= {"feedback"} and w.built == 2
      and R._chain(w.store, P, w.store.get(P, g.id)).fails == 0)

# ═══════════════════ Sửa ngoài luồng ═══════════════════

w = World("drift", Engine([GOOD]))
g = w.goal(budget=8, mode="maintain", horizon={"kind": "maintain"})
w.tick()
pub0 = dict(w.store.published(P, g.id, DELIV))
write(DELIV, "# Sample\n\nAnh sửa tay, bỏ hết.\n")
w.feedback(g.id, "goal_fit_confirmed", key="fb-drift")
w.run_until(g.id, T0 + 30 * 86400)
rows = [r for r in w.log(g.id)]
check("sửa tay làm hỏng tiêu chí, 30 ngày: 0 lượt model", w.built == 1)
check("sửa tay: một dòng quan sát, báo một lần, source_drift",
      len(w.store.source_observations(P, g.id)) == 1 and w.state(g.id).get("block_reason") == "source_drift"
      and w.outbox(g.id, "goal.publish_conflict") == 1)
check("sửa tay: lần thức chỉ theo drift_recheck, không thức mỗi 30 giây", len(rows) < 45)
check("sửa tay: góp ý vẫn chờ", any(r["code"] == "feedback" for r in w.reasons(g.id)))
check("mốc được phép thay file không đổi do quan sát", w.store.published(P, g.id, DELIV) == pub0)
write(DELIV, "# Sample\n\nAnh sửa lần hai.\n")
w.clock.t = w.due(g.id)
w.tick()
check("sửa tiếp thành H2: thêm một dòng quan sát, báo thêm một lần",
      len(w.store.source_observations(P, g.id)) == 2 and w.outbox(g.id, "goal.publish_conflict") == 2)
write(DELIV, GOOD)
w.clock.t = w.due(g.id)
w.tick()
w.tick()
check("đưa file về mốc đã đăng: hết source_drift, góp ý xử lý đúng một lần, 0 lượt (đã đạt)",
      w.state(g.id).get("block_reason") != "source_drift" and not any(r["code"] == "feedback" for r in w.reasons(g.id))
      and w.built == 1)

# Sửa tay mà vẫn đạt: ghi nhận, healthy.
w = World("drift-ok", Engine([GOOD]))
g = w.goal(budget=8, mode="maintain", horizon={"kind": "maintain"})
w.tick()
write(DELIV, GOOD + "\nThêm một dòng anh tự viết.\n")
w.clock.t = w.due(g.id)
w.tick()
check("sửa tay vẫn đạt: ghi nhận, healthy, 0 lượt",
      w.state(g.id).get("block_reason") == "healthy" and w.built == 1 and len(w.store.source_observations(P, g.id)) == 1)

# Xoá file, bản hiệu lực từ việc nền: đăng lại, 0 lượt.
w = World("drift-del", Engine([GOOD]))
g = w.goal(budget=8, mode="maintain", horizon={"kind": "maintain"})
w.tick()
(Path(BRAIN) / DELIV).unlink()
w.clock.t = w.due(g.id)
w.tick()
check("xoá file, bản việc nền: đăng lại đầu ra đã lưu, 0 lượt",
      (Path(BRAIN) / DELIV).read_text(encoding="utf-8") == GOOD and w.built == 1)

# Cùng path, size, mtime nhưng bytes khác: nhận ra ở lần kiểm kế tiếp.
w = World("drift-mtime", Engine([GOOD]))
g = w.goal(budget=8, mode="maintain", horizon={"kind": "maintain"})
w.tick()
f = Path(BRAIN) / DELIV
st0 = f.stat()
data = bytearray(f.read_bytes())
i = data.index("máy lạnh".encode("utf-8"))
data[i:i + 3] = b"XYZ"
f.write_bytes(bytes(data))
os.utime(f, ns=(st0.st_atime_ns, st0.st_mtime_ns))
check("tiền đề: size và mtime giữ nguyên", (f.stat().st_size, f.stat().st_mtime_ns) == (st0.st_size, st0.st_mtime_ns))
w.clock.t = w.due(g.id)
w.tick()
check("cùng metadata mà bytes khác: nhận ra sửa ngoài luồng, không gọi model",
      w.state(g.id).get("block_reason") == "source_drift" and w.built == 1)
ref_now = R._artifact_ref_of(w.store, P, w.store.get(P, g.id), BRAIN)
check("nhận diện sản phẩm dùng hash bytes hiện tại", ref_now and ref_now != w.store.published(P, g.id, DELIV)["sha256"])

# Góp ý mới trong lúc chờ file sửa tay: kiểm ngay một lần, còn sửa ngoài luồng thì lại gác.
w = World("drift-fb", Engine([GOOD]))
g = w.goal(budget=8, mode="maintain", horizon={"kind": "maintain"})
w.tick()
write(DELIV, "# Sample\n\nSửa tay.\n")
w.clock.t = w.due(g.id)
w.tick()
recheck = w.due(g.id)
w.feedback(g.id, "goal_fit_confirmed", key="fb-dr")
first = w.due(g.id)
n_before = len(w.log(g.id))
w.tick()
check("góp ý khi đang chờ file: thức đúng một lần để kiểm, rồi lịch về drift_recheck, 0 lượt",
      first <= time.time() + 1 and len(w.log(g.id)) == n_before + 1 and w.due(g.id) == recheck and w.built == 1)
w.reopen()
check("khởi động lại khi chờ file: góp ý không mất", any(r["code"] == "feedback" for r in w.reasons(g.id)))

# ═══════════════════ Lịch người dùng hẹn ═══════════════════

w = World("user-sched", Engine([HALF, HALF]))
g = w.goal(budget=8)
w.tick()
w.store.supersede_timers(P, g.id, ("retry",))
asyncio.run(R.advance(g.id, {"kind": "user_schedule", "at": T0 + 3600, "ref": "us-1"}, w.deps))
asyncio.run(R.advance(g.id, {"kind": "user_schedule", "at": T0 + 3600, "ref": "us-1"}, w.deps))
check("gửi lại cùng lịch hẹn: không nhân đôi", sum(1 for r in w.reasons(g.id) if r["code"] == "user_schedule") == 1)
w.store.add_timer(P, g.id, "review", T0 + 30, T0)
w.store.recompute_wake(P, g.id)
w.clock.t = T0 + 30
w.tick()
check("hẹn sau 1 giờ, lần thức chỉ kiểm ở giây 30: không gọi model, không phục vụ lịch hẹn",
      w.built == 1 and any(r["code"] == "user_schedule" and r["state"] == "pending" for r in w.reasons(g.id))
      and "user_schedule" not in w.log(g.id)[-1]["codes"])
check("lịch vật lý vẫn ở mốc hẹn, không kéo về sớm", w.due(g.id) == T0 + 3600)
w.reopen()
check("khởi động lại: giờ hẹn giữ nguyên", w.due(g.id) == T0 + 3600)
w.clock.t = T0 + 3600
w.tick()
check("tới giờ hẹn: mở lượt (còn hạn mức, trạng thái cho phép)", w.built == 2)

# Chờ bàn giao có thử lại cũ đã quá giờ: lịch là hẹn chờ bàn giao, thử lại không thắng.
w = World("handoff", Engine([HALF]))
g = w.goal(budget=8)
w.tick()
_real_hg = R._handoff_gate
R._handoff_gate = lambda goal, deps: "pending"
try:
    w.clock.t = T0 + 900
    w.tick()
    due = w.due(g.id)
    check("chờ bàn giao: lịch là hẹn handoff_wait 30 giây, thử lại cũ không thắng",
          due == T0 + 900 + POL["HANDOFF_POLL_S"] and any(r["code"] == "retry_not_met" for r in w.reasons(g.id))
          and w.built == 1)
finally:
    R._handoff_gate = _real_hg
w.clock.t = due
w.tick()
check("bàn giao xong: thử lại quá giờ được xét đúng một lần", w.built == 2)

# ═══════════════════ Hiệu năng ═══════════════════

w = World("perf", Engine([GOOD]))
many = [w.goal(budget=2, path=f"Inbox/perf-{i}.md") for i in range(40)]
for gx in many:
    w.store.serve_reasons(P, gx.id, [r["id"] for r in w.reasons(gx.id)], "test")
    w.store.add_timer(P, gx.id, "review", T0 + 86400, T0)
    w.store.recompute_wake(P, gx.id)
due_goals = many[:3]
for gx in due_goals:
    w.store.add_timer(P, gx.id, "review", T0, T0)
    w.store.recompute_wake(P, gx.id)
reads = []
_orig_rb, _orig_rt = Path.read_bytes, Path.read_text


def _rb(self):
    reads.append(str(self))
    return _orig_rb(self)


def _rt(self, *a, **k):
    reads.append(str(self))
    return _orig_rt(self, *a, **k)


Path.read_bytes, Path.read_text = _rb, _rt
try:
    n = w.tick(limit=3)
finally:
    Path.read_bytes, Path.read_text = _orig_rb, _orig_rt
others = [r for r in reads if any(f"perf-{i}.md" in r for i in range(3, 40))]
check("200 lịch chưa tới hạn (40 ở đây): một nhịp không đọc file nào của mục tiêu chưa tới hạn", n == 3 and not others)

w = World("perf-limit", Engine([GOOD]))
q = [w.goal(budget=2, path=f"Inbox/q-{i}.md") for i in range(10)]
for gx in q:
    w.store.serve_reasons(P, gx.id, [r["id"] for r in w.reasons(gx.id)], "test")
    w.store.add_timer(P, gx.id, "review", T0 + q.index(gx), T0)
    w.store.recompute_wake(P, gx.id)
w.clock.t = T0 + 20
counts = [w.tick(limit=3)]
first3 = [gx.id for gx in q if w.log(gx.id)]
counts += [w.tick(limit=3) for _ in range(3)]
check(f"10 lịch cùng tới hạn: mỗi nhịp đúng 3, hết trong 4 nhịp ({counts})", counts == [3, 3, 3, 1])
check("nhận theo thứ tự due_at (cũ nhất trước), không bỏ đói",
      first3 == [gx.id for gx in q[:3]] and all(w.log(gx.id) for gx in q))

# Trễ event loop: nhịp xử lý 3 mục tiêu có file 1 MB.
w = World("perf-loop", Engine([GOOD]))
big = "# Sample\n\nBáo cáo quý, máy lạnh.\n" + ("x" * 1_000_000)
heavy = []
for i in range(3):
    gx = w.goal(budget=2, path=f"Inbox/big-{i}.md", mode="maintain", horizon={"kind": "maintain"})
    write(f"Inbox/big-{i}.md", big)
    w.store.serve_reasons(P, gx.id, [r["id"] for r in w.reasons(gx.id)], "test")
    w.store.add_timer(P, gx.id, "review", T0, T0)
    w.store.recompute_wake(P, gx.id)
    heavy.append(gx)


async def _lag():
    worst = [0.0]
    stop = asyncio.Event()

    async def ticker():
        while not stop.is_set():
            t = time.perf_counter()
            await asyncio.sleep(0.005)
            worst[0] = max(worst[0], time.perf_counter() - t - 0.005)

    tk = asyncio.create_task(ticker())
    await asyncio.sleep(0.02)
    await R.tick(w.store, w.clock(), lambda b: w.deps, limit=3)
    stop.set()
    await tk
    return worst[0]


lag = asyncio.run(_lag())
check(f"trễ event loop khi nhịp đọc 3 file 1 MB: {lag * 1000:.1f} ms < 50 ms (đo trong môi trường test)", lag < 0.05)

# Số câu SQLite mỗi lần thức không tăng theo số mục tiêu.


def _sql_count(n_goals):
    ww = World(f"perf-sql-{n_goals}", Engine([GOOD]))
    gs = [ww.goal(budget=2, path=f"Inbox/s-{n_goals}-{i}.md") for i in range(n_goals)]
    for gx in gs:
        ww.store.serve_reasons(P, gx.id, [r["id"] for r in ww.reasons(gx.id)], "test")
        ww.store.add_timer(P, gx.id, "review", T0 + 86400, T0)
        ww.store.recompute_wake(P, gx.id)
    ww.store.add_timer(P, gs[0].id, "review", T0, T0)
    ww.store.recompute_wake(P, gs[0].id)
    count = [0]
    orig = ww.store._conn

    def traced():
        c = orig()
        c.set_trace_callback(lambda s: count.__setitem__(0, count[0] + 1))
        return c
    ww.store._conn = traced
    ww.tick()
    return count[0]


c5, c30 = _sql_count(5), _sql_count(30)
check(f"số câu SQLite mỗi lần thức không tăng theo số mục tiêu ({c5} so với {c30})", c30 <= c5 + 2)

# ═══════════════════ Review mã vòng 1 (50c355f1) ═══════════════════
# Ca tái hiện của reviewer (`PR-593-A2-code-50c355f1-checks.py`) chuyển thành kỳ vọng đúng.

# P1-1: trần thử lại không phụ thuộc sổ thức.
w = World("rv-logfail", Engine(events=ERR))
g = w.goal(budget=10)
_orig_log, _inj = w.store.log_wake, {"n": 0}


def _fail_once(*a, **k):
    if _inj["n"] == 0:
        _inj["n"] += 1
        raise sqlite3.OperationalError("lỗi ghi sổ thức chèn một lần")
    return _orig_log(*a, **k)


w.store.log_wake = _fail_once
w.run_until(g.id, T0 + 3 * 86400)
check("ghi sổ thức lỗi một lần: vẫn đúng 3 lượt lỗi", _inj["n"] == 1 and w.built == 3
      and len([x for x in w.store.actions(P, g.id) if x["kind"] == "work" and x["status"] == "failed"]) == 3)

w = World("rv-gap", Engine(events=ERR))
g = w.goal(budget=10)
w.tick()
held = R._agent_intent(w.store.get(P, g.id), w.deps)
a2 = w.store.begin_action(P, g.id, 1, "work", lease_until=T0 + 5, now=T0, intent={"prompt_kind": "work", **held})
w.store.finish_action(P, a2["id"], "failed", {"error_code": "upstream", "status": "failed"})
check("chết giữa receipt và kết sổ: lượt lỗi vẫn được tính (gấp bảo thủ)",
      R._chain(w.store, P, w.store.get(P, g.id)).fails == 2)
w.reopen()
w.clock.t = T0 + 10
w.run_until(g.id, T0 + 3 * 86400)
check("chết giữa receipt và kết sổ, khởi động lại: tổng không quá 3 lượt lỗi",
      len([x for x in w.store.actions(P, g.id) if x["kind"] == "work" and x["status"] == "failed"]) == 3)

w = World("rv-trim", Engine(events=ERR))
g = w.goal(budget=10)
w.tick()
f0 = R._chain(w.store, P, w.store.get(P, g.id)).fails
for i in range(250):
    w.store.log_wake(P, g.id, {"revision": 1, "wake_kind": "observe", "decision": "observe", "at": T0 + i + 1})
w.reopen()
check("hơn 200 lần quan sát và mở lại kho: số lỗi giữ nguyên",
      f0 == 1 and R._chain(w.store, P, w.store.get(P, g.id)).fails == 1 and len(w.log(g.id)) == 200)

w = World("rv-progress", Engine([HALF, HALF, GOOD]))
g = w.goal(budget=10)
w.tick()
w.clock.t = T0 + 900
w.tick()
c1 = R._chain(w.store, P, w.store.get(P, g.id))
RA.disable(w.store, BRAIN)
w.agent = RA.enable(w.store, BRAIN)
w.store.wake_agent_goals(BRAIN, w.agent["agent_key"])
w.tick()
w.reopen()
c2 = R._chain(w.store, P, w.store.get(P, g.id))
check("bật lại trợ lý và mở lại kho: mốc tiến bộ và chuỗi bế tắc không đặt lại",
      c1.best == 1 and c1.stall == 1 and (c2.best, c2.stall) == (c1.best, c1.stall))

# P1-2: tạm dừng, tắt, mất theo dõi, bật lại: quan sát được dựng lại, kể cả qua khởi động lại.
for restart in (False, True):
    w = World(f"rv-pause-observe-{restart}")
    write("Inbox/protect.md", "Sample")
    gd = [{"description": "Giữ Sample", "evaluator": "artifact_contract",
           "params": {"path": "Inbox/protect.md", "must_contain": ["Sample"]}}]
    g = w.goal(mode="maintain", horizon={"kind": "maintain"}, guards=gd)
    w.tick()
    b0 = w.built
    w.store.set_paused(OWNER, g.id, True)
    RA.disable(w.store, BRAIN)
    w.clock.t = w.due(g.id, "observe")
    w.tick()
    lost_ok = w.due(g.id, "observe") is None and R.goal_view(w.store, P, g.id, BRAIN)["observe"]["state"] == "lost"
    if restart:
        w.reopen()
    w.agent = RA.enable(w.store, BRAIN)
    n_woke = w.store.wake_agent_goals(BRAIN, w.agent["agent_key"])
    if restart:
        w.reopen()
    write("Inbox/protect.md", "BROKEN")
    w.run_until(g.id, w.clock.t + 2 * 86400)
    check(f"tạm dừng rồi tắt, bật lại{' (có khởi động lại)' if restart else ''}: dựng lại quan sát, báo guard, "
          "không gọi model, vẫn tạm dừng",
          lost_ok and n_woke == 1 and w.outbox(g.id, "goal.guard") == 1 and w.built == b0
          and w.store.get(P, g.id).paused and w.state(g.id).get("block_reason") == "guard")

w = World("rv-latched")
write("Inbox/protect2.md", "Sample")
gd = [{"description": "Giữ Sample", "evaluator": "artifact_contract",
       "params": {"path": "Inbox/protect2.md", "must_contain": ["Sample"]}}]
g = w.goal(mode="maintain", horizon={"kind": "maintain"}, guards=gd)
w.tick()
write("Inbox/protect2.md", "BROKEN")
w.clock.t = w.due(g.id, "observe")
w.tick()
RA.disable(w.store, BRAIN)
w.agent = RA.enable(w.store, BRAIN)
w.store.wake_agent_goals(BRAIN, w.agent["agent_key"])
check("đối chứng: guard đã chốt không tự mở khi bật lại trợ lý",
      w.state(g.id).get("block_reason") == "guard" and w.due(g.id, "observe") is None
      and R.goal_view(w.store, P, g.id, BRAIN)["observe"]["state"] == "stopped")
v = R.goal_view(w.store, P, g.id, BRAIN)
w2 = World("rv-view-sched")
g2 = w2.goal(mode="maintain", horizon={"kind": "maintain"}, guards=gd)
w2.store.supersede_timers(P, g2.id, ("observe",))
w2.store.recompute_wake(P, g2.id)
check("thẻ: bật mà không có lịch quan sát thì không hiện như đang theo dõi",
      R.goal_view(w2.store, P, g2.id, BRAIN)["observe"] == {"state": "lost", "next_at": None,
                                                           "lost_reason": "not_scheduled"})

# P2-1: lỗi của revision cũ không chặn revision mới.
FIXED = [{"type": "final", "content": "x", "is_error": True, "subtype": "error"}]
for label, events, at_query in (("lỗi cuối của trần", ERR, 3), ("lỗi đầu", ERR, 1)):
    w = World(f"rv-rev-{at_query}-{label}", Engine(events=events))
    g = w.goal(budget=10)

    def _rev(w=w, g=g, at_query=at_query):
        if w.engine.queries != at_query:
            return
        R.revise_goal(w.store, P, g.id, 1, {"understanding": "Ghi chú tổng hợp hai việc, bản sửa",
                                            "relevant_quote": "Viết giúp anh một ghi chú tổng hợp trong Inbox"},
                      {"message_ref": R.message_ref("s-a2", 99_100 + at_query), "session_id": "s-a2",
                       "message_id": 99_100 + at_query, "user_text": USER, **RA.ctx(w.agent)})
    w.engine.on_query = _rev
    w.run_until(g.id, T0 + 600 if at_query == 1 else T0 + 3 * 86400, max_wakes=at_query + 2)
    cur = w.store.get(P, g.id)
    acts2 = [x for x in w.store.actions(P, g.id) if x["kind"] == "work" and x["revision"] == 2]
    check(f"đổi revision trong {label}: revision mới vẫn được làm, không bị chặn bởi lỗi cũ",
          cur.revision == 2 and len(acts2) >= 1 and not any(r["code"] == "revised" for r in w.reasons(g.id))
          and R._chain(w.store, P, cur).fails <= len([a for a in acts2 if a["status"] == "failed"]))

# Lỗi cố định (engine không dựng được) đúng lúc revision đổi: dựng engine là lúc lượt đang chạy.
w = World("rv-rev-fixed", Engine([GOOD]))
g = w.goal(budget=10)
_fx = {"n": 0}


def _fixed_factory(system_prompt, tag, w=w, g=g):
    _fx["n"] += 1
    if _fx["n"] == 1:
        R.revise_goal(w.store, P, g.id, 1, {"understanding": "Ghi chú tổng hợp hai việc, bản sửa",
                                            "relevant_quote": "Viết giúp anh một ghi chú tổng hợp trong Inbox"},
                      {"message_ref": R.message_ref("s-a2", 99_150), "session_id": "s-a2", "message_id": 99_150,
                       "user_text": USER, **RA.ctx(w.agent)})
        return None, {"blocked": "engine_build"}
    w.built += 1
    return w.engine, {"provider": "fake", "model": "fake-1", "text_only": True}


w.deps = R.GoalDeps(**{**w.deps.__dict__, "engine_factory": _fixed_factory})
w.tick()
st_fx = w.state(g.id)
w.tick()
check("đổi revision trong lượt lỗi cố định: revision mới không bị gác bởi lỗi cũ, được làm và đạt",
      st_fx.get("run_state") != "blocked" and w.built == 1 and w.store.get(P, g.id).revision == 2
      and w.store.get(P, g.id).status == "succeeded")

w = World("rv-rev-cleanup", Engine([HALF, HALF, GOOD]))
g = w.goal(budget=10)
w.tick()


def _rev_cleanup():
    if w.engine.queries == 2:
        R.revise_goal(w.store, P, g.id, 1, {"understanding": "Ghi chú tổng hợp hai việc, bản sửa",
                                            "relevant_quote": "Viết giúp anh một ghi chú tổng hợp trong Inbox"},
                      {"message_ref": R.message_ref("s-a2", 99_200), "session_id": "s-a2", "message_id": 99_200,
                       "user_text": USER, **RA.ctx(w.agent)})
        w.store.add_timer(P, g.id, "retry_not_met", w.clock() + 50, w.clock())   # nghĩa vụ của revision mới


w.engine.on_query = _rev_cleanup
w.clock.t = T0 + 900
w.tick()
check("dọn hẹn thử lại của lượt cũ không đụng nghĩa vụ của revision mới; không đăng đầu ra cũ",
      any(r["code"] == "retry_not_met" and r["revision"] == 2 for r in w.reasons(g.id))
      and any(r["code"] == "revised" for r in w.reasons(g.id))
      and w.store.published(P, g.id, DELIV)["sha256"] == hashlib.sha256(HALF.encode()).hexdigest())

# P2-2: pha trước và sau lời gọi engine chạy ngoài event loop.
import threading  # noqa: E402

for slow in ("finish_action", "evidence"):
    w = World(f"rv-loop-{slow}", Engine([GOOD]))
    g = w.goal()
    threads = []
    if slow == "finish_action":
        _orig_fa = w.store.finish_action

        def _slow_fa(*a, _o=_orig_fa, **k):
            threads.append(threading.current_thread().name)
            time.sleep(0.16)
            return _o(*a, **k)
        w.store.finish_action = _slow_fa
    else:
        _ev = w.deps.evidence
        _orig_put = _ev.put

        def _slow_put(*a, _o=_orig_put, **k):
            threads.append(threading.current_thread().name)
            time.sleep(0.16)
            return _o(*a, **k)
        _ev.put = _slow_put

    async def _gap(w=w, g=g):
        gaps, done = [], [False]

        async def timer():
            last = time.perf_counter()
            while not done[0]:
                await asyncio.sleep(0.005)
                t = time.perf_counter()
                gaps.append(t - last)
                last = t
        tk = asyncio.create_task(timer())
        await R.advance(g.id, {"kind": "wake"}, w.deps)
        done[0] = True
        await tk
        return max(gaps)
    gap = asyncio.run(_gap())
    check(f"ghi {slow} chậm 160 ms: không chạy trên luồng chính, timer giãn dưới 60 ms ({gap * 1000:.0f} ms)",
          threads and "MainThread" not in threads and gap < 0.06 and w.store.get(P, g.id).status == "succeeded")

# Huỷ lần thức trong pha sau: khoá lượt chỉ nhả khi pha sau đã ghi xong, không ghi trùng.
w = World("rv-cancel", Engine([GOOD]))
g = w.goal()
_orig_fa = w.store.finish_action
_events = []


def _slow_fa2(*a, **k):
    _events.append("post_start")
    time.sleep(0.3)
    r = _orig_fa(*a, **k)
    _events.append("post_end")
    return r


w.store.finish_action = _slow_fa2
_orig_rel = w.store.release_lease


def _rel(*a, **k):
    _events.append("release")
    return _orig_rel(*a, **k)


w.store.release_lease = _rel


async def _cancel_mid():
    t = asyncio.create_task(R.advance(g.id, {"kind": "wake"}, w.deps))
    while "post_start" not in _events:
        await asyncio.sleep(0.01)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        pass


asyncio.run(_cancel_mid())
acts = [x for x in w.store.actions(P, g.id) if x["kind"] == "work"]
check("huỷ giữa pha sau: nhả khoá sau khi pha sau ghi xong, không ghi trùng, không mất lượt",
      _events.index("post_end") < _events.index("release") and len(acts) == 1 and acts[0]["status"] == "succeeded"
      and w.built == 1)

# ═══════════════════ Review mã vòng 2 (d1f64b46): huỷ lần thức ═══════════════════
# Ca tái hiện của reviewer (`PR-593-A2-d1f64b46-checks.py`) chuyển thành kỳ vọng đúng. Đồng bộ giữa event loop và
# luồng phụ bằng threading.Event, không dựa vào thời gian may rủi.
from unittest.mock import patch  # noqa: E402


async def _settles_early(task, order, window=0.5):
    """Trong lúc luồng phụ còn bị giữ, tác vụ có kết thúc hay nhả khoá không. Mã đúng thì KHÔNG (cả cửa sổ trôi qua);
    mã sai thì xảy ra ngay khi lời huỷ tới, nên cửa sổ có giới hạn đủ bắt."""
    until = time.monotonic() + window
    while time.monotonic() < until:
        if task.done() or "lease_released" in order:
            return True
        await asyncio.sleep(0.01)
    return False


async def _wait_ev(ev, timeout=10.0):
    until = time.monotonic() + timeout
    while not ev.is_set():
        assert time.monotonic() < until, "hết giờ chờ luồng phụ"
        await asyncio.sleep(0.005)


def _trace_release(w, order):
    real = w.store.release_lease

    def rel(*a, **k):
        order.append("lease_released")
        return real(*a, **k)
    w.store.release_lease = rel


# Huỷ trong lúc ghi đầu ra sau model: chờ ghi xong, lưu receipt, rồi mới nhả khoá.
w = World("rv2-cancel-write", Engine([GOOD]))
g = w.goal()
entered, allow, finished = threading.Event(), threading.Event(), threading.Event()
order = []
_real_replace = R.os.replace


def _slow_replace(src, dst):
    if Path(dst).parent == Path(g.output_root) and str(dst).endswith(".md"):
        order.append("write_started")
        entered.set()
        assert allow.wait(10)
        r = _real_replace(src, dst)
        order.append("write_finished")
        finished.set()
        return r
    return _real_replace(src, dst)


_trace_release(w, order)


async def _run_cancel_write():
    task = asyncio.create_task(R.advance(g.id, {"kind": "wake"}, w.deps))
    await _wait_ev(entered)
    task.cancel()
    early = await _settles_early(task, order)
    allow.set()
    try:
        await task
        got = "returned"
    except asyncio.CancelledError:
        got = "cancelled"
    return early, got


with patch.object(R.os, "replace", _slow_replace):
    early, got = asyncio.run(_run_cancel_write())
acts = [x for x in w.store.actions(P, g.id) if x["kind"] == "work"]
check("huỷ khi đang ghi đầu ra: chưa nhả khoá trước khi ghi xong; báo huỷ cho người gọi",
      not early and got == "cancelled" and order.index("write_finished") < order.index("lease_released"))
check("huỷ khi đang ghi đầu ra: receipt đã lưu (action succeeded, không còn running), một lượt model, không trả lượt",
      len(acts) == 1 and acts[0]["status"] == "succeeded" and w.built == 1 and w.store.get(P, g.id).calls_used == 1
      and w.store.get(P, g.id).status == "succeeded")

# Huỷ trong lúc chuẩn bị (pha chỉ-code đã giữ khoá): nhận lại kết quả, nhả khoá, không gọi model.
w = World("rv2-cancel-prepare", Engine([GOOD]))
g = w.goal()
entered, allow, finished = threading.Event(), threading.Event(), threading.Event()
order = []
_orig_ww = R._wake_work


def _slow_wake(*a):
    entered.set()
    assert allow.wait(10)
    try:
        return _orig_ww(*a)
    finally:
        finished.set()


_trace_release(w, order)


async def _run_cancel_prepare():
    task = asyncio.create_task(R.advance(g.id, {"kind": "wake"}, w.deps))
    await _wait_ev(entered)
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()                      # huỷ lặp trong lúc pha chuẩn bị còn chạy
    allow.set()
    try:
        await task
        got = "returned"
    except asyncio.CancelledError:
        got = "cancelled"
    return got


with patch.object(R, "_wake_work", _slow_wake):
    got = asyncio.run(_run_cancel_prepare())
can_claim = w.store.claim_lease(P, g.id, "lan-sau", w.clock() + 30, w.clock())
check("huỷ khi đang chuẩn bị (kể cả huỷ lặp): nhả khoá đúng một lần, lần sau nhận được, không gọi model",
      got == "cancelled" and order.count("lease_released") == 1 and can_claim and w.built == 0)
w.store.release_lease(P, g.id, "lan-sau")
check("huỷ khi đang chuẩn bị: lý do created vẫn chờ, không mất việc",
      any(r["code"] == "created" for r in w.reasons(g.id)) and w.store.get(P, g.id).calls_used == 0)
w.tick()
check("huỷ khi đang chuẩn bị: lần thức sau làm đúng một lượt", w.built == 1 and w.store.get(P, g.id).status == "succeeded")

# Huỷ ngay sau pha trước (đã ghi ý định, chưa gọi model): huỷ lượt, trả lượt, trả lý do.
w = World("rv2-cancel-pre", Engine([GOOD]))
g = w.goal()
entered, allow = threading.Event(), threading.Event()
_orig_pre = R._work_pre


def _slow_pre(*a):
    r = _orig_pre(*a)
    entered.set()
    assert allow.wait(10)
    return r


async def _run_cancel_pre():
    task = asyncio.create_task(R.advance(g.id, {"kind": "wake"}, w.deps))
    await _wait_ev(entered)
    task.cancel()
    allow.set()
    try:
        await task
    except asyncio.CancelledError:
        return "cancelled"
    return "returned"


with patch.object(R, "_work_pre", _slow_pre):
    got = asyncio.run(_run_cancel_pre())
acts = [x for x in w.store.actions(P, g.id) if x["kind"] == "work"]
check("huỷ sau pha trước, trước lời gọi engine: action not_run, trả lượt, lý do về chờ, không gọi model",
      got == "cancelled" and w.built == 0 and len(acts) == 1 and acts[0]["status"] == "cancelled"
      and acts[0]["receipt"].get("error_code") == "not_run" and w.store.get(P, g.id).calls_used == 0
      and any(r["code"] == "created" for r in w.reasons(g.id))
      and R._chain(w.store, P, w.store.get(P, g.id)).fails == 0)
w.tick()
check("huỷ sau pha trước: lần thức sau làm đúng một lượt", w.built == 1 and w.store.get(P, g.id).status == "succeeded")

# Huỷ trong lúc gọi engine: model có thể đã chạy, không trả lượt; kết sổ như một lượt lỗi, còn đường thử lại.
w = World("rv2-cancel-engine", Engine([GOOD]))
g = w.goal(budget=6)
started = asyncio.Event


class _SlowEngine(Engine):
    async def query(self, prompt):
        self.queries += 1
        await asyncio.sleep(30)
        yield {"type": "final", "content": GOOD}


w.engine = _SlowEngine()
order = []
_trace_release(w, order)


async def _run_cancel_engine():
    task = asyncio.create_task(R.advance(g.id, {"kind": "wake"}, w.deps))
    while w.engine.queries == 0:
        await asyncio.sleep(0.005)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return "cancelled"
    return "returned"


got = asyncio.run(_run_cancel_engine())
acts = [x for x in w.store.actions(P, g.id) if x["kind"] == "work"]
check("huỷ trong lúc gọi engine: receipt lỗi `cancelled`, không trả lượt, tính một lượt lỗi, có hẹn thử lại, nhả khoá",
      got == "cancelled" and len(acts) == 1 and acts[0]["status"] == "failed"
      and acts[0]["receipt"].get("error_code") == "cancelled" and w.store.get(P, g.id).calls_used == 1
      and R._chain(w.store, P, w.store.get(P, g.id)).fails == 1
      and any(r["code"] == "error_retry" for r in w.reasons(g.id)) and order.count("lease_released") == 1)

# Huỷ lặp trong lúc đang dọn (nhả khoá chạy ở luồng phụ): việc dọn vẫn chạy xong, khoá nhả đúng một lần.
w = World("rv2-cancel-cleanup", Engine([GOOD]))
g = w.goal()
entered, allow = threading.Event(), threading.Event()
order = []
_orig_fw = R._finish_wake


def _slow_finish(*a):
    entered.set()
    assert allow.wait(10)
    r = _orig_fw(*a)
    order.append("cleanup_done")
    return r


_trace_release(w, order)


async def _run_cancel_cleanup():
    task = asyncio.create_task(R.advance(g.id, {"kind": "wake"}, w.deps))
    await _wait_ev(entered)
    for _ in range(3):
        task.cancel()
        await asyncio.sleep(0)
    early = await _settles_early(task, [])
    allow.set()
    try:
        await task
    except asyncio.CancelledError:
        return "cancelled", early
    return "returned", early


with patch.object(R, "_finish_wake", _slow_finish):
    got, early = asyncio.run(_run_cancel_cleanup())
check("huỷ lặp trong lúc dọn: không kết thúc trước khi dọn xong, khoá nhả đúng một lần, kết quả lượt giữ nguyên",
      got == "cancelled" and not early and order == ["lease_released", "cleanup_done"]
      and w.store.get(P, g.id).status == "succeeded" and w.store.claim_lease(P, g.id, "x", w.clock() + 5, w.clock()))

# ═══════════════════ Review mã vòng 3 (f7cbab4c): lỗi của pha không che lời huỷ ═══════════════════

# Bộ chạy luồng phụ: thành công hay lỗi, không huỷ, huỷ một lần, huỷ lặp.
async def _helper_case(fail: bool, cancels: int):
    entered, allow = threading.Event(), threading.Event()

    def work():
        entered.set()
        assert allow.wait(10)
        if fail:
            raise OSError("ghi hỏng")
        return "xong"

    task = asyncio.create_task(R._thread_done(work))
    await _wait_ev(entered)
    for _ in range(cancels):
        task.cancel()
        await asyncio.sleep(0)
    early = await _settles_early(task, [], window=0.2)
    allow.set()
    try:
        return early, ("ok", await task)
    except R._CancelledWith as c:
        return early, ("cancelled_with", c.value, type(c.error).__name__ if c.error else None)
    except asyncio.CancelledError:
        return early, ("cancelled",)
    except OSError as e:
        return early, ("error", str(e))


for fail in (False, True):
    for cancels in (0, 1, 3):
        early, got = asyncio.run(_helper_case(fail, cancels))
        want = (("error", "ghi hỏng") if fail else ("ok", ("xong", False))) if cancels == 0 else \
            (("cancelled_with", None, "OSError") if fail else ("ok", ("xong", True)))
        check(f"bộ chạy luồng phụ: {'lỗi' if fail else 'thành công'}, huỷ {cancels} lần: chờ pha xong, "
              f"{'giữ cả lời huỷ lẫn lỗi' if fail and cancels else 'đúng kết quả'}", not early and got == want)

# Tái hiện: huỷ tick khi mục tiêu đầu đang ghi đầu ra, và việc ghi đó lỗi.
for cancel in (True, False):
    w = World(f"rv3-tick-{cancel}", Engine([GOOD]))
    g1 = w.goal(path="Inbox/rv3-a.md")
    g2 = w.goal(path="Inbox/rv3-b.md")
    entered, allow = threading.Event(), threading.Event()
    order = []
    _real_replace = R.os.replace

    def _broken_replace(src, dst, g1=g1):
        if Path(dst).parent == Path(g1.output_root) and str(dst).endswith(".md"):
            entered.set()
            assert allow.wait(10)
            raise OSError("ổ đĩa lỗi khi ghi đầu ra")
        return _real_replace(src, dst)

    _trace_release(w, order)

    async def _run_tick(cancel=cancel, w=w):
        task = asyncio.create_task(R.tick(w.store, w.clock(), lambda b: w.deps, limit=5))
        await _wait_ev(entered)
        if cancel:
            task.cancel()
        allow.set()
        try:
            return ("returned", await task)
        except asyncio.CancelledError:
            return ("cancelled",)

    with patch.object(R.os, "replace", _broken_replace):
        got = asyncio.run(_run_tick())
    a1 = [x for x in w.store.actions(P, g1.id) if x["kind"] == "work"]
    a2x = [x for x in w.store.actions(P, g2.id) if x["kind"] == "work"]
    if cancel:
        check("huỷ tick khi ghi đầu ra lỗi: tick báo huỷ, không xử lý mục tiêu thứ hai, một lượt engine tổng cộng",
              got == ("cancelled",) and w.built == 1 and not a2x
              and any(r["code"] == "created" for r in w.reasons(g2.id)))
        check("huỷ tick khi ghi đầu ra lỗi: lỗi write_failed được lưu, lượt đã dùng vẫn là 1, khoá mục tiêu đầu đã nhả",
              len(a1) == 1 and a1[0]["status"] == "failed" and a1[0]["receipt"].get("error_code") == "write_failed"
              and w.store.get(P, g1.id).calls_used == 1 and order.count("lease_released") == 1
              and w.store.claim_lease(P, g1.id, "sau", w.clock() + 5, w.clock()))
    else:
        check("đối chứng, cùng lỗi ghi mà không huỷ: lỗi ghi thông thường, tick làm tiếp mục tiêu thứ hai",
              got[0] == "returned" and got[1] == 2 and w.built == 2 and len(a1) == 1
              and a1[0]["receipt"].get("error_code") == "write_failed"
              and any(r["code"] == "error_retry" for r in w.reasons(g1.id))
              and len(a2x) == 1 and a2x[0]["status"] == "succeeded")

# ═══════════════════ Kiểm tích hợp (sau review đạt ở b5975b7e) ═══════════════════
# Soi dữ liệu thẻ trên sandbox thấy hẹn `recovery` của hành động ĐĂNG còn chờ ở nghĩa vụ thử lại. Hẹn phục hồi của hành
# động không phải lượt việc chỉ được đối soát bằng code, không bao giờ là một lần thử lại tự động.
w = World("int-publish-recovery", Engine([GOOD]))
g = w.goal(mode="maintain", horizon={"kind": "maintain"})
w.tick()
check("sau khi đăng: không còn lý do thử lại tự động nào đang chờ (hẹn phục hồi của hành động đăng là chỉ kiểm)",
      not any(HB.classify(r["code"]) == HB.AUTO for r in w.reasons(g.id))
      and any(r["code"] == "action_recovery" and r["state"] != "pending" for r in w.reasons(g.id, None)))
w = World("int-publish-blocked", Engine(["Báo cáo quý, máy lạnh, mất tiêu đề.\n", GOOD]))
_flag_g = [{"description": "Tiêu đề Sample còn giữ", "evaluator": "artifact_contract",
            "params": {"path": DELIV, "must_contain": ["Sample"]}}]
g = w.goal(budget=8, guards=_flag_g)
write(DELIV, "# Sample\n\nBản cũ.\n")
w.tick()
q1 = w.built
for k in range(1, 25):
    w.clock.t = T0 + 30 * k
    w.tick()
check("bản mới làm guard sai (không đăng): không gọi model lại trước mốc thử lại 15 phút", q1 == 1 and w.built == 1)

# ═══════════════════ Sao lưu và nâng cấp ═══════════════════
old = Path(_STATE) / "pre-a2.sqlite3"
with sqlite3.connect(str(old)) as c:
    c.executescript(RS._SCHEMA.split("CREATE TABLE IF NOT EXISTS wake_reasons")[0])
    for table, col, decl in RS._ADDED_COLUMNS:
        have = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in have:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    c.execute("INSERT INTO goals(id,brain_id,owner,revision,status,session_id,request_ref,idempotency_key,output_root,"
              "budget_calls,calls_used,paused,created_at,updated_at) VALUES('g_old','b','o',1,'active','','','k','/tmp',"
              "4,0,0,1,1)")
    c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,created_at) VALUES('g_old',1,"
              "'feedback.outcome_rejected','owner','{}','owner:o',2)")
RS.GoalStore(old)
check("nâng lên A2: chép bản sao pre-a2 một lần", (Path(str(old) + ".pre-a2.bak")).is_file())
with sqlite3.connect(str(old)) as c:
    codes = sorted(r[0] for r in c.execute("SELECT code FROM wake_reasons WHERE goal_id='g_old'"))
check("nâng lên A2: dựng lại lý do created và feedback từ goal_events", codes == ["created", "feedback"])

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
