"""T3 phần L (0.156.0): tự rà soát có tự áp và tự quay lại (thiết kế 2026-10-15 mục 6.4, 8.3; GOAL 8.2, 8.4, 12 ca 17, 26).

    python tests/run.py agent_judge_review -v

Kho thật (resonance.sqlite3 tạm, bảng nhịp và cửa sổ quan sát của P thật), đồng hồ GIẢ, engine GIẢ, bộ phán xử GIẢ (tiêm theo
giao diện `JudgeAdapter`, không model):
- chỉ kích hoạt khi có ≥ 6 nhãn mới hay ≥ 5 tín hiệu mới SAU `resumed_at` (và sau lần trước), cách lần trước ≥ 24 giờ;
  nguồn đã được lượt xem xét reaction tiêu thụ không đếm lại (không hai vòng học);
- danh sách đóng, tối đa 3 thay đổi, mỗi thay đổi dẫn bằng chứng đã cho xem; ngoài phạm vi chỉ thành đề xuất;
- tự áp có trước/sau, mở cửa sổ quan sát; tự quay lại khi lỗi phán xử tăng quá 0,15 (≥ 6 nhãn) hay ước lượng giảm quá 0,3
  (độ tin ≥ 0,5); hết 14 ngày không xấu thì giữ; không lặp thay đổi đã quay lại trong 14 ngày;
- không đè thiết lập chủ đang giữ (lúc áp và lúc quay lại); học không cấp quyền, không nâng trần.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import re
import tempfile
from contextlib import closing
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-selfrev-")
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)
TEMP = Path(tempfile.mkdtemp(prefix="javis-selfrev-w-"))

import agent_budget as AB  # noqa: E402
import agent_ledger as ALG  # noqa: E402
import agent_lessons as ALS  # noqa: E402
import agent_pulse as AP  # noqa: E402
import agent_review as AR  # noqa: E402
import resonance_store as RS  # noqa: E402

fails = []
D = 86400.0
T0 = 2_000_000_000.0


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class FakeJudge:
    """Bộ phán xử GIẢ theo giao diện JudgeAdapter. `record_policy`: giả móc `policy_change` của J (ghi cửa sổ ở P)."""

    def __init__(self, store, clock, record_policy=False):
        self.store, self.clock, self.record_policy = store, clock, record_policy
        self.eagerness, self.eager_src = "medium", ""
        self.offsets, self.owner_offsets = {}, set()
        self.decisions = []
        self.calls = []

    def label(self, ctx, verdict, label, at):
        self.decisions.append({"id": len(self.decisions) + 1, "context_ref": ctx, "verdict": verdict, "label": label,
                               "label_at": float(at), "excerpt": f"tin {len(self.decisions) + 1}", "reason": ""})
        return f"decision:{len(self.decisions)}"

    async def proactive(self, **kw):
        return {"verdict": "silent", "decision_id": None}

    def profile(self, key):
        return {"eagerness": self.eagerness, "eagerness_source": self.eager_src, "offsets": dict(self.offsets)}

    def set_offset(self, key, ctx, value, source):
        before = self.offsets.get(ctx, 0.0)
        self.offsets[ctx] = max(-0.25, min(0.25, float(value)))
        self.calls.append(("offset", ctx, value, source))
        if self.record_policy:
            AP.apply_policy_change(self.store, key, ctx, {"kind": "offset_set", "before": before,
                                                          "after": self.offsets[ctx], "source": source}, at=self.clock())
        return {"before": before, "after": self.offsets[ctx]}

    def set_eagerness(self, key, value, source):
        self.calls.append(("eagerness", value, source))
        self.eagerness = value
        if source == "owner":
            self.eager_src = "owner"
        return {"eagerness": value}

    def labeled(self, key, since):
        return [dict(d) for d in self.decisions if d["label_at"] > float(since)]

    def owner_held(self, key, kind, ctx):
        if kind == "eagerness_set":
            return self.eager_src == "owner"
        return ctx in self.owner_offsets


class Engine:
    def __init__(self, store):
        self.store = store
        self.text = '{"changes": []}'
        self.calls = []

    def engine_for(self, key, ctx, purpose):
        async def run_(req):
            await req["engine_started"]()
            with closing(self.store._conn()) as c:
                req["ledger_seen"] = [dict(r) for r in c.execute(
                    "SELECT purpose, status, obligation FROM agent_calls WHERE reason_ref=?", (req["turn_id"],))]
            self.calls.append(req)
            t = self.text(req) if callable(self.text) else self.text
            return {"text": t, "tokens_in": 1, "tokens_out": 2}
        run_.marks_engine = True
        return "fake", "fake", run_


_n = [0]


def world(record_policy=False, budget=None):
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}"
    d.mkdir()
    gs = RS.GoalStore(d / "resonance.sqlite3")
    owner = RS.Principal("owner", "owner", str(d))
    key = gs.agent_set_enabled(owner, "viet", True)["agent_key"]
    with gs._Tx(gs) as c:   # mốc bật lại theo đồng hồ giả
        c.execute("UPDATE agent_pulse SET resumed_at=? WHERE agent_key=?", (T0, key))
    clock = Clock(T0 + 100)
    judge = FakeJudge(gs, clock, record_policy)
    eng = Engine(gs)
    box = {"busy": set()}
    deps = AR.ReviewDeps(store=lambda: gs, reactions=None, engine_for=eng.engine_for, persona=lambda k: "",
                         try_busy=lambda k, tok: k not in box["busy"], judge=judge,
                         budget=budget or (lambda k, p, at=None, reason_ref=None: (True, "")),
                         contexts=lambda k: ["team:A", "team:B", f"dm:{k}"], clock=clock)
    host = AR.ReviewHost(deps)
    # Một host học mặc định mỗi tiến trình (như main.py): hàm quay lại đăng ký với P dùng host đang nối, nên mỗi thế giới
    # nối host của nó trước khi chạy.
    AR.wire(host)
    AR.register_with_pulse()
    return gs, owner, key, clock, judge, eng, host, box


def run(coro):
    return asyncio.run(coro)


def changes_json(*items, proposals=()):
    return json.dumps({"changes": list(items), "proposals": list(proposals), "reason": "giả"}, ensure_ascii=False)


def sig(gs, key, ctx, value, at, ref):
    AP.record_signal(gs, source_ref=ref, agent_key=key, context_ref=ctx, kind="host_event", value=value, w=1.0, at=at)
    return ref


def review_rows(gs, key):
    with closing(gs._conn()) as c:
        return [dict(r) for r in c.execute("SELECT * FROM agent_review_changes WHERE agent_key=? ORDER BY id", (key,))]


# ═════ kích hoạt: chỉ sau resumed_at, đủ ngưỡng, cách 24 giờ ═════
gs, owner, key, clock, judge, eng, host, box = world()
for i in range(6):
    judge.label("team:A", "speak", "should_silent", T0 - 50 + i)   # trước mốc bật lại
check("6 nhãn TRƯỚC resumed_at: chưa kích hoạt", host.due(gs, key, clock())[:2] == (False, "not_enough"))
ev = [judge.label("team:A", "speak", "should_silent", T0 + 10 + i) for i in range(5)]
check("5 nhãn mới: chưa đủ", host.due(gs, key, clock())[:2] == (False, "not_enough"))
ev.append(judge.label("team:A", "speak", "should_silent", T0 + 20))
check("6 nhãn mới sau resumed_at: đến hạn", host.due(gs, key, clock())[:2] == (True, "due"))
eng.text = changes_json({"kind": "offset_set", "context_ref": "team:A", "value": 0.1, "evidence": ev[:3],
                         "why": "chen ngang nhiều"})
res = run(host.maybe_self_review(key))
check("tự rà soát chạy và áp 1 thay đổi", res["outcome"] == "reviewed" and res["applied"] == 1, res)
check("sổ lượt: purpose review, obligation 0, giữ chỗ trước engine", eng.calls[0]["ledger_seen"] ==
      [{"purpose": "review", "status": "running", "obligation": 0}], eng.calls[0]["ledger_seen"])
prompt = eng.calls[0]["prompt"]
check("lời nhắc chỉ có bằng chứng mới (không nhãn trước mốc)", "decision:7" in prompt and "decision:1]" not in prompt,
      prompt)
check("vừa rà soát xong: chưa đủ 24 giờ", host.due(gs, key, clock())[:2] == (False, "not_due"))
clock.t += D + 1
for i in range(6):
    judge.label("team:A", "silent", "should_speak", clock.t - 10 + i * 0.1)
check("sau 24 giờ có 6 nhãn mới: đến hạn lại; bằng chứng lần trước không đếm lại",
      host.due(gs, key, clock())[:2] == (True, "due") and host.evidence(gs, key, clock())["n_labels"] == 6)

# Tín hiệu: ≥ 5 tín hiệu mới; tín hiệu đã được lượt xem xét reaction tiêu thụ không đếm.
gs2, owner2, key2, clock2, judge2, eng2, host2, box2 = world()
refs = [sig(gs2, key2, f"dm:{key2}", 0.5, T0 + 10 + i, f"rx:dm:{i + 1}") for i in range(5)]
W = ALG.WakeReasons(gs2)
rid = W.add_source(key2, f"dm:{key2}", "reaction_review", refs[0])
cl = W.claim(rid, purpose="reaction_review", obligation=False, now=T0 + 50)
W.settle(rid, "ok", [refs[0]], now=T0 + 51)
check("tín hiệu đã được lượt xem xét reaction tiêu thụ không đếm (không hai vòng học): 4 < 5",
      host2.due(gs2, key2, clock2())[:2] == (False, "not_enough") and host2.evidence(gs2, key2, clock2())["n_signals"]
      == 4)
sig(gs2, key2, f"dm:{key2}", 0.5, T0 + 60, "seen:dm:x:1")
check("thêm 1 tín hiệu mới: 5, đến hạn", host2.due(gs2, key2, clock2())[:2] == (True, "due"))
owner_off = RS.Principal("owner", "owner", str(TEMP / f"{_n[0]:02d}"))
gs2.agent_set_enabled(owner_off, "viet", False)
check("Cộng hưởng tắt: không tự rà soát", host2.due(gs2, key2, clock2())[:2] == (False, "off"))

# ═════ danh sách đóng, tối đa 3, bằng chứng đã cho xem, đề xuất ═════
gs, owner, key, clock, judge, eng, host, box = world(record_policy=True)
evA = [judge.label("team:A", "speak", "should_silent", T0 + 10 + i) for i in range(3)]
evB = [judge.label("team:B", "speak", "should_silent", T0 + 20 + i) for i in range(3)]
lid = ALS.add(gs, agent_key=key, scope="team:A", kind="method", text="Gửi bảng tóm tắt trước.", source="self")
lid2 = ALS.add(gs, agent_key=key, scope="team:B", kind="method", text="Báo tiến độ mỗi chiều.", source="self")
judge.eager_src = "owner"
eng.text = changes_json(
    {"kind": "max_tier", "value": 0, "evidence": evA[:1], "why": "muốn nhịp nhanh hơn"},
    {"kind": "offset_set", "context_ref": "team:A", "value": 0.12, "evidence": ["decision:999"], "why": "bịa"},
    {"kind": "eagerness_set", "value": "low", "evidence": evA[:2], "why": "kín tiếng hơn"},
    {"kind": "lesson_add", "context_ref": f"dm:{key}", "text": "Hỏi lại khi yêu cầu mơ hồ.", "evidence": evB[:1],
     "lesson_kind": "speak"},
    {"kind": "lesson_promote", "lesson_id": lid, "evidence": evA + evB, "why": "đúng ở hai nhóm"},
    proposals=[{"area": "permissions", "text": "Cho em quyền mở việc trong nhóm A", "evidence": evA[:1]}])
res = run(host.maybe_self_review(key))
st = [r["status"] + ":" + str(r.get("reason") or "") for r in res["results"]]
check("tối đa 3 thay đổi; phần thừa bị bỏ (over_limit)", len(res["results"]) == 5 and
      [r["status"] for r in res["results"]][3:] == ["rejected", "rejected"]
      and all(r["reason"] == "over_limit" for r in res["results"][3:]), st)
check("ngoài danh sách đóng (max_tier) chỉ thành đề xuất, không áp", res["results"][0]["status"] == "proposal")
check("bằng chứng không nằm trong danh sách đã cho xem: từ chối", res["results"][1] ==
      {"status": "rejected", "reason": "evidence", "change_id": res["results"][1]["change_id"]}, res["results"][1])
check("độ hăng hái chủ đang giữ: không đè (owner_held)", res["results"][2]["reason"] == "owner_held"
      and judge.eagerness == "medium")
with closing(gs._conn()) as c:
    props = [dict(r) for r in c.execute("SELECT * FROM agent_review_proposals WHERE agent_key=?", (key,))]
check("ý về quyền thành đề xuất cho chủ (cùng ý max_tier)", sorted(p["area"] for p in props) == ["other", "permissions"],
      props)
check("open proposals are readable as procedure drafts (M5)",
      sorted(p["area"] for p in __import__("agent_review").open_proposals(gs, key)) == ["other", "permissions"])
check("học không nâng trần, không cấp quyền: max_tier và hạn mức ngày giữ mặc định",
      (AP.row(gs, key, "*") or {}).get("max_tier", AP.DEFAULT_MAX_TIER) == AP.DEFAULT_MAX_TIER
      and AB.get_cap(gs, key) == AB.DEFAULT_DAILY)

# Áp thật từng loại (trong giới hạn 3 mỗi lần).
clock.t += D + 1
evA2 = [judge.label("team:A", "speak", "should_speak", clock.t - 30 + i) for i in range(3)]   # nhãn đúng: lỗi nền thấp
evB2 = [judge.label("team:B", "speak", "should_silent", clock.t - 20 + i) for i in range(3)]
# Bài học của chat riêng phải có bằng chứng của CHÍNH chat riêng (review T3 L P2-5).
evD2 = [judge.label(f"dm:{key}", "speak", "should_silent", clock.t - 5)]
eng.text = changes_json(
    {"kind": "offset_set", "context_ref": "team:A", "value": 0.12, "evidence": evA2, "why": "chen ngang ở A"},
    {"kind": "lesson_add", "context_ref": f"dm:{key}", "text": "Hỏi lại khi yêu cầu mơ hồ.", "evidence": evD2,
     "lesson_kind": "speak"},
    {"kind": "lesson_promote", "lesson_id": lid, "evidence": evA2[:1], "why": "chỉ một nhóm"})
res = run(host.maybe_self_review(key))
r_off, r_add, r_pro = res["results"]
check("offset_set áp ngay, ghi trước/sau", r_off["status"] == "applied" and r_off["before"] == {"offset": 0.0}
      and r_off["after"] == {"offset": 0.12} and judge.offsets["team:A"] == 0.12, r_off)
pcs = {p["id"]: p for p in AP.policy_changes(gs, key, 50)}
pc = pcs.get(r_off["policy_change_id"])
check("cửa sổ quan sát ở P dùng đúng dòng J đã ghi (nguồn self_review:<mã>) kèm tỷ lệ lỗi nền",
      pc and pc["source"] == f"self_review:{r_off['change_id']}" and pc["kind"] == "offset_set"
      and pc["base_error"] is not None and pc["status"] == "observing"
      and sum(1 for p in pcs.values() if p["source"] == pc["source"]) == 1, pc)
check("lesson_add áp: bài học phạm vi dm, nguồn review, dẫn bằng chứng",
      r_add["status"] == "applied" and ALS.get(gs, r_add["after"]["lesson_id"])["scope"] == f"dm:{key}"
      and evD2[0] in ALS.get(gs, r_add["after"]["lesson_id"])["source_refs"], r_add)
check("lesson_promote với bằng chứng 1 ngữ cảnh: từ chối", r_pro == {"status": "rejected", "reason": "contexts",
                                                                     "change_id": r_pro["change_id"]}, r_pro)
clock.t += D + 1
evA3 = [judge.label("team:A", "silent", "should_speak", clock.t - 30 + i) for i in range(3)]
evB3 = [judge.label("team:B", "silent", "should_speak", clock.t - 20 + i) for i in range(3)]
eng.text = changes_json({"kind": "lesson_promote", "lesson_id": lid, "evidence": evA3[:1] + evB3[:1]},
                        {"kind": "lesson_remove", "lesson_id": lid2, "evidence": evB3[1:2], "why": "lỗi thời"})
res = run(host.maybe_self_review(key))
check("lesson_promote với bằng chứng 2 ngữ cảnh: lên `*`", res["results"][0]["status"] == "applied"
      and ALS.get(gs, res["results"][0]["after"]["lesson_id"])["scope"] == "*", res["results"][0])
check("lesson_remove: thu hồi (giữ lịch sử)", res["results"][1]["status"] == "applied"
      and ALS.get(gs, lid2)["status"] == "revoked")
check("thay đổi nào cũng có mã bằng chứng đã cho xem", all(json.loads(r["evidence_json"]) for r in review_rows(gs, key)
                                                            if r["status"] == "applied"))

# ═════ tự quay lại theo 6.4 ═════
# (1) lỗi phán xử tăng quá 0,15 khi có ≥ 6 nhãn sau thay đổi -> quay lại offset_set
off_change = r_off
for i in range(6):
    judge.label("team:A", "speak", "should_silent", clock.t + 1 + i)   # sáu lỗi sau thay đổi
clock.t += 10
host.refresh_policy_labels(clock.t)
got = AP.observe_policy_changes(gs, at=clock.t)
dec = {g["change_id"]: g for g in got}
check("lỗi phán xử tăng quá 0,15 (≥ 6 nhãn): P tự quay lại, lý do judge_error_up",
      dec.get(off_change["policy_change_id"], {}).get("reason") == "judge_error_up", got)
row = [r for r in review_rows(gs, key) if r["id"] == off_change["change_id"]][0]
# Quay lại bỏ ĐÚNG phần dịch của thay đổi, đã nhạt dần như kho thật (review T3 L P2-4); bộ phán xử giả không nhạt dần
# nên sau một ngày còn dư rất nhỏ.
check("quay lại: độ lệch về trước thay đổi, thay đổi ghi 'reverted'", abs(judge.offsets["team:A"]) < 0.01
      and row["status"] == "reverted" and row["reverted_at"] is not None, [judge.offsets, row])
host.refresh_policy_labels(clock.t)
check("lý do quay lại lấy từ P", [r for r in review_rows(gs, key) if r["id"] == off_change["change_id"]][0]
      ["status"] == "reverted")

# (2) không lặp thay đổi đã quay lại trong 14 ngày
clock.t += D + 1
ev4 = [judge.label("team:A", "speak", "should_silent", clock.t - 30 + i * 0.1) for i in range(6)]
eng.text = changes_json({"kind": "offset_set", "context_ref": "team:A", "value": 0.2, "evidence": ev4[:2]})
res = run(host.maybe_self_review(key))
check("cùng hướng, cùng ngữ cảnh trong 14 ngày: từ chối reverted_recently",
      res["results"][0]["reason"] == "reverted_recently" and abs(judge.offsets["team:A"]) < 0.01, res["results"])
clock.t += 15 * D
ev5 = [judge.label("team:A", "speak", "should_speak", clock.t - 30 + i * 0.1) for i in range(6)]
eng.text = changes_json({"kind": "offset_set", "context_ref": "team:A", "value": 0.2, "evidence": ev5[:2]})
res = run(host.maybe_self_review(key))
check("sau 14 ngày: được áp lại", res["results"][0]["status"] == "applied" and judge.offsets["team:A"] == 0.2,
      res["results"])
again = res["results"][0]

# (3) không đè thiết lập chủ đang giữ lúc quay lại: chủ đặt lại độ lệch rồi cửa sổ thấy xấu
judge.owner_offsets.add("team:A")
judge.offsets["team:A"] = -0.05
for i in range(6):
    judge.label("team:A", "speak", "should_silent", clock.t + 1 + i)
clock.t += 10
host.refresh_policy_labels(clock.t)
AP.observe_policy_changes(gs, at=clock.t)
row = [r for r in review_rows(gs, key) if r["id"] == again["change_id"]][0]
check("quay lại khi chủ đã đặt lại: giữ giá trị của chủ, ghi owner_held", judge.offsets["team:A"] == -0.05
      and row["status"] == "reverted" and row["revert_reason"] == "owner_held", row)
judge.owner_offsets.discard("team:A")

# (4) ước lượng giảm quá 0,3 khi độ tin ≥ 0,5 -> quay lại bài học tự áp
gs3, owner3, key3, clock3, judge3, eng3, host3, box3 = world()
ctx = f"dm:{key3}"
pos = [sig(gs3, key3, ctx, 0.8, T0 + 10 + i * 0.01, f"host:pos{i}") for i in range(6)]
eng3.text = changes_json({"kind": "lesson_add", "context_ref": ctx, "text": "Luôn trả lời bằng bảng.",
                          "evidence": pos[:2]})
res = run(host3.maybe_self_review(key3))
add = res["results"][0]
check("bài học tự áp, mở cửa sổ", add["status"] == "applied" and add["policy_change_id"], add)
for i in range(10):
    sig(gs3, key3, ctx, -0.6, clock3.t + 1 + i * 0.01, f"host:neg{i}")
clock3.t += 5
host3.refresh_policy_labels(clock3.t)
got = AP.observe_policy_changes(gs3, at=clock3.t)
check("ước lượng giảm quá 0,3 (độ tin ≥ 0,5): tự quay lại, lý do estimate_down",
      got and got[0]["reason"] == "estimate_down", got)
check("quay lại bài học tự áp: bài học bị thu hồi (vẫn còn lịch sử)",
      ALS.get(gs3, add["after"]["lesson_id"])["status"] == "revoked"
      and [e["kind"] for e in ALS.events(gs3, add["after"]["lesson_id"])] == ["add", "revoke"])

# (5) hết 14 ngày không có gì xấu: giữ (không tuyên bố gì trước đó)
gs4, owner4, key4, clock4, judge4, eng4, host4, box4 = world()
ev6 = [judge4.label(f"dm:{key4}", "speak", "should_silent", T0 + 10 + i) for i in range(6)]
eng4.text = changes_json({"kind": "lesson_add", "context_ref": f"dm:{key4}", "text": "Ngắn gọn.", "evidence": ev6[:1]})
add = run(host4.maybe_self_review(key4))["results"][0]
clock4.t += 13 * D
check("chưa qua cửa sổ: không kết luận", AP.observe_policy_changes(gs4, at=clock4.t) == [])
clock4.t += 1.5 * D
got = AP.observe_policy_changes(gs4, at=clock4.t)
host4.refresh_policy_labels(clock4.t)
row = [r for r in review_rows(gs4, key4) if r["id"] == add["change_id"]][0]
check("tối đa 14 ngày, không xấu: giữ (kept)", got and got[0]["decision"] == "kept" and row["status"] == "kept",
      [got, row])

# (6) chủ bấm quay lại qua route của P: hàm quay lại đã đăng ký chạy
AR.wire(host4)
AR.register_with_pulse()
clock4.t += D + 1
ev7 = [judge4.label(f"dm:{key4}", "silent", "should_speak", clock4.t - 30 + i * 0.1) for i in range(6)]
eng4.text = changes_json({"kind": "offset_set", "context_ref": f"dm:{key4}", "value": -0.1, "evidence": ev7[:2]})
off = run(host4.maybe_self_review(key4))["results"][0]
AP.revert_policy_change(gs4, off["policy_change_id"], reason="owner", by="owner", at=clock4.t)
row = [r for r in review_rows(gs4, key4) if r["id"] == off["change_id"]][0]
check("chủ quay lại: độ lệch về trước, thay đổi 'reverted'", judge4.offsets[f"dm:{key4}"] == 0.0
      and row["status"] == "reverted", [judge4.offsets, row])

# ═════ hạn mức, bận, sai khuôn ═════
gs5, owner5, key5, clock5, judge5, eng5, host5, box5 = world(budget=lambda k, p, at=None, reason_ref=None:
                                                              (False, "agent_daily_calls"))
for i in range(6):
    judge5.label(f"dm:{key5}", "speak", "should_silent", T0 + 10 + i)
res = run(host5.maybe_self_review(key5))
check("hết hạn mức: không chạy, không sổ lượt", res["outcome"] == "quota" and ALG.CallLedger(gs5).rows() == []
      and eng5.calls == [])
host5.deps.budget = lambda k, p, at=None, reason_ref=None: (True, "")
box5["busy"].add(key5)
check("bận: không chạy", run(host5.maybe_self_review(key5))["outcome"] == "busy")
box5["busy"].clear()
eng5.text = "không phải JSON"
res = run(host5.maybe_self_review(key5))
check("sai khuôn: lượt error, chưa tính là đã rà soát (lùi 1 giờ)", res["outcome"] == "invalid"
      and ALG.CallLedger(gs5).rows()[0]["status"] == "error"
      and host5.due(gs5, key5, clock5())[:2] == (False, "backoff"))
clock5.t += 3601
check("sau 1 giờ thử lại được", host5.due(gs5, key5, clock5())[:2] == (True, "due"))

# ═════ không hai vòng học: learn.py, curator, A3 không đọc bảng reaction hay kho bài học ═════
for name in ("learn.py", "resonance_learning.py"):
    src = (SERVER / name).read_text(encoding="utf-8")
    hit = re.findall(r"dm_reactions|dm_reaction_log|team_reactions|team_reaction_log|agent_lessons|pulse_signals", src)
    check(f"{name} không đọc bảng reaction / bài học có phạm vi (không vòng học thứ hai)", hit == [], hit)

print(f"\n{'ĐỎ' if fails else 'XANH'}: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
