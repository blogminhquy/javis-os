"""Resonance A5: sổ lượt hai vai, bộ đếm thử lại review, lượt dự phòng, hoàn lượt (thiết kế mục 6, 5.6; ma trận 15.5, 15.8).

    python tests/run.py resonance_a5_budget -v

Kho SQLite thật, engine GIẢ hai vai, đồng hồ giả; mục tiêu tạo qua `form_goal` thật và chạy qua `R.advance` thật. Không
gọi model thật. Mỗi vết kiểm: trạng thái và lý do, lượt (maker, reviewer, tổng), số lần engine giả được gọi, trạng thái
hành động và hàng review (seq, charged), lý do đang chờ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

_STATE = Path(tempfile.mkdtemp(prefix="javis-res-a5b-"))
os.environ["JAVIS_STATE_DIR"] = str(_STATE)
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)

import resonance as R  # noqa: E402
import resonance_heartbeat as HB  # noqa: E402
import resonance_store as RS  # noqa: E402
import _resonance_agent as RA  # noqa: E402
import _resonance_team as T  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not detail else f"  [{str(detail)[:400]}]"))
    if not cond:
        _fails.append(name)


GOOD2 = T.GOOD.replace("Xong.", "Xong, bản sửa theo góp ý.")
GOOD3 = T.GOOD.replace("Xong.", "Xong, bản sửa lần hai.")
ERR = {"error": "engine giả báo lỗi"}
BACKOFF1 = HB.POLICY["ERROR_BACKOFF_S"][0]


def rows(t, g):
    return [(x["seq"], x["status"], x["verdict"], x["reason_code"], x["charged"]) for x in t.reviews(g)]


def review_action(t, g):
    """Giữ chỗ một lượt review qua đường thật (chuẩn bị lần thức, rồi pha trước), KHÔNG gọi engine. Trả (ctx, act)."""
    deps = t.deps()
    ctx = R._advance_prepare(g.id, "wake", {}, deps, t.clock())
    assert isinstance(ctx, R._WakeCtx) and ctx.mode == "review", ctx
    pre = R._review_pre(ctx.goal, ctx, deps, t.clock())
    assert isinstance(pre, tuple), pre
    return ctx, pre[0]


def ready_for_review(name):
    t = T.Team(_STATE, name)
    g = t.create()
    t.wake(g)                               # vai làm: H1, đạt; hẹn review
    return t, g


# ═══════════ T5, T6: unknown và thử lại ═══════════
t = T.Team(_STATE, "t5")
t.rev.script = ["không phải JSON", '{"verdict": "pass"}', T.verdict("pass", (False,))]
g = t.create()
t.run(g, n=20, step=1)
check("T5 ba lượt review không đọc được: thử lại hai lần (lần tính 2, 3), rồi blocked/review_unknown; (1, 3, 4)",
      t.st(g) == {"run_state": "blocked", "block_reason": "review_unknown"} and t.calls(g) == (1, 3, 4)
      and [r[3] for r in rows(t, g)] == ["parse_error", "parse_error", "inconsistent"] and t.g(g).status == "active",
      (t.st(g), t.calls(g), rows(t, g)))

t = T.Team(_STATE, "t6")
t.rev.script = [ERR, T.PASS]
g = t.create()
t.run(g, n=20, step=1)
check("T6 lỗi engine ở lượt review (engine CÓ chạy): unknown/engine_error, lượt tính; lần sau pass; (1, 2, 3)",
      t.g(g).status == "succeeded" and t.calls(g) == (1, 2, 3) and rows(t, g)[0][3] == "engine_error"
      and rows(t, g)[0][4] == 1, (t.st(g), rows(t, g)))

# ═══════════ T7: hết phần reviewer khi còn phần maker ═══════════
t = T.Team(_STATE, "t7")
t.work.script = [T.GOOD, GOOD2, GOOD3]
t.rev.script = ["x", "y", T.CHANGES, T.CHANGES]
g = t.create()
t.run(g, n=30, step=1)
check("T7 reviewer dùng hết 4 lượt: blocked/budget_reviewer; không mượn phần maker; (3, 4, 7)",
      t.st(g) == {"run_state": "blocked", "block_reason": "budget_reviewer"} and t.calls(g) == (3, 4, 7)
      and t.rev.queries == 4, (t.st(g), t.calls(g), rows(t, g)))

# ═══════════ T8, T51: hết phần maker trước khi có bản đạt; làn M không đề xuất trên mục tiêu có đội ═══════════
t = T.Team(_STATE, "t8")
t.work.script = [T.BAD]
g = t.create()
t.run(g, n=20, step=1)
st_after3 = (t.st(g), t.calls(g))
t.store.add_reason_event(t.owner, g.id, "feedback", "fb:1")
t.run(g, n=10, step=1)
lessons = sqlite3.connect(str(t.store.path)).execute("SELECT COUNT(*) FROM lessons WHERE goal_id=?", (g.id,)).fetchone()[0]
check("T8 bản đầu và hai lần thử lại chưa đạt: chờ theo luật dự phòng (stalled), (3, 0, 3)",
      st_after3 == ({"run_state": "waiting", "block_reason": "stalled"}, (3, 0, 3)), st_after3)
check("T8 lượt thứ tư chỉ mở bởi tin mới (NEW), vẫn chưa đạt: blocked/budget_maker; (4, 0, 4); không review bản chưa đạt",
      t.st(g) == {"run_state": "blocked", "block_reason": "budget_maker"} and t.calls(g) == (4, 0, 4)
      and t.rev.queries == 0, (t.st(g), t.calls(g)))
check("T51 bế tắc trên mục tiêu có đội không đề xuất phép thử làn M (không có bài học)", lessons == 0, lessons)
eid = t.store.begin_experiment(RS.Principal("agent", "javis", t.brain), g.id, t.g(g).revision, "a", "b", 2, 2, {},
                               agent=RA.pin(t.store, t.brain, T.MAKER))
check("T51 kho từ chối begin_experiment trên mục tiêu có đội: None, calls_used không đổi", eid is None
      and t.g(g).calls_used == 4, eid)

# ═══════════ T9: trần chung chạm khi còn phần vai ═══════════
t = T.Team(_STATE, "t9")
g = t.create()
t.wake(g)
os.environ["JAVIS_RESONANCE_CALL_CEILING"] = "1"
t.run(g, n=4)
st9 = (t.st(g), t.calls(g), t.rev.queries)
os.environ.pop("JAVIS_RESONANCE_CALL_CEILING", None)
check("T9 trần chung thắng phần vai: không giữ chỗ review, không gọi engine; lượt không đổi (1, 0, 1)",
      st9[1] == (1, 0, 1) and st9[2] == 0 and st9[0]["run_state"] == "blocked", st9)

# ═══════════ T47 tới T50: bảng vết V1, V2, V3, V5 ═══════════
t = T.Team(_STATE, "t47")
t.work.script = [T.GOOD, GOOD2, GOOD3]
t.rev.script = [T.CHANGES, T.CHANGES, T.PASS]
g = t.create()
t.run(g, n=30, step=1)
check("T47 V1: hai vòng sửa, không lỗi: succeeded; (3, 3, 6); engine 3 + 3", t.g(g).status == "succeeded"
      and t.calls(g) == (3, 3, 6) and (t.work.queries, t.rev.queries) == (3, 3), (t.st(g), t.calls(g)))

t = T.Team(_STATE, "t48")
t.work.script = [ERR, T.GOOD, GOOD2, GOOD3]
t.rev.script = [T.CHANGES, T.CHANGES, T.PASS]
g = t.create()
t.run(g, n=30, step=1)
check("T48 V2: một lỗi maker; lượt sửa thứ hai dùng lượt CUỐI của maker (FIX): succeeded; (4, 3, 7)",
      t.g(g).status == "succeeded" and t.calls(g) == (4, 3, 7), (t.st(g), t.calls(g), rows(t, g)))

t = T.Team(_STATE, "t49")
t.work.script = [ERR, ERR, T.GOOD, GOOD2]
t.rev.script = [T.CHANGES, T.CHANGES]
g = t.create()
t.run(g, n=30, step=1)
check("T49 V3: hai lỗi maker làm mất một vòng sửa: blocked/budget_maker sau vòng 2; (4, 2, 6)",
      t.st(g) == {"run_state": "blocked", "block_reason": "budget_maker"} and t.calls(g) == (4, 2, 6)
      and t.store.review_rounds(t.owner, g.id, 1) == 2, (t.st(g), t.calls(g)))

t = T.Team(_STATE, "t50")
t.work.script = [T.GOOD, GOOD2, GOOD3]
t.rev.script = [T.CHANGES, T.CHANGES, ERR]
g = t.create()
t.run(g, n=30, step=1)
check("T50 V5: reviewer còn đúng 1 lượt khi unknown: KHÔNG review_retry; blocked/review_unknown; (3, 3, 6)",
      t.st(g) == {"run_state": "blocked", "block_reason": "review_unknown"} and t.calls(g) == (3, 3, 6)
      and not any(c == "review_retry" for c, _r in t.reasons(g)), (t.st(g), t.calls(g), t.reasons(g)))

# ═══════════ T15, T52 (huỷ trước engine) và T62 ═══════════
t, g = ready_for_review("t15")
ctx, act = review_action(t, g)
check("T15 đã giữ chỗ review: (1, 1, 2), hàng running, charged=1", t.calls(g) == (1, 1, 2)
      and rows(t, g) == [(1, "running", None, "", 1)], rows(t, g))
ok = t.store.abort_action(t.owner, act["id"], t.clock())
R._finish_wake(ctx, t.deps())
check("T15 huỷ trước engine: hoàn tổng và vai (1, 0, 1); hàng cancelled/not_run, charged=0; review_due trở lại chờ",
      ok and t.calls(g) == (1, 0, 1) and rows(t, g) == [(1, "cancelled", None, "not_run", 0)]
      and any(c == "review_due" for c, _r in t.reasons(g))
      and t.actions(g, "review")[0]["status"] == "cancelled", (rows(t, g), t.reasons(g)))
t.run(g)
check("T15 lần thức sau: review chạy, pass, succeeded; (1, 1, 2); 1 lượt engine", t.g(g).status == "succeeded"
      and t.calls(g) == (1, 1, 2) and t.rev.queries == 1, (t.st(g), t.calls(g)))

t, g = ready_for_review("t62")
for _ in range(3):
    ctx, act = review_action(t, g)
    t.store.abort_action(t.owner, act["id"], t.clock())
    R._finish_wake(ctx, t.deps())
t.run(g)
check("T62 ba lần huỷ trước engine rồi pass: không bị trần thử chặn; seq 1..4; chỉ một lần tính; (1, 1, 2)",
      t.g(g).status == "succeeded" and [r[0] for r in rows(t, g)] == [1, 2, 3, 4]
      and [r[4] for r in rows(t, g)] == [0, 0, 0, 1] and t.calls(g) == (1, 1, 2) and t.rev.queries == 1, rows(t, g))

# ═══════════ T16, T63: huỷ khi engine có thể đã chạy ═══════════
t, g = ready_for_review("t16")


def _cancel_inside(e):
    raise asyncio.CancelledError()


t.rev.hook = _cancel_inside
try:
    t.wake(g)
    _cx = False
except (asyncio.CancelledError, KeyboardInterrupt):
    _cx = True
t.rev.hook = None
check("T16 huỷ trong lúc engine chạy: failed/cancelled, KHÔNG hoàn, charged=1; (1, 1, 2); hẹn thử lại theo luật",
      _cx and rows(t, g) == [(1, "failed", "unknown", "cancelled", 1)] and t.calls(g) == (1, 1, 2)
      and t.st(g)["block_reason"] == "review_retry", (_cx, rows(t, g), t.st(g)))
t.run(g, n=10, step=1)
check("T63 lượt có thể đã chạy được tính vào trần thử và ngân sách: lần sau là lần tính 2; succeeded; (1, 2, 3)",
      t.g(g).status == "succeeded" and [r[4] for r in rows(t, g)] == [1, 1] and t.calls(g) == (1, 2, 3), rows(t, g))

# ═══════════ T53, T65: engine không dựng được ═══════════
t, g = ready_for_review("t53")
t.factory_raise = True
t.wake(g)
pend = t.store.reasons(t.owner, g.id)
check("T53/T65 engine không dựng được: hoàn đúng vai reviewer (1, 0, 1); hàng cancelled, charged=0, không running",
      t.calls(g) == (1, 0, 1) and rows(t, g) == [(1, "cancelled", None, "engine_not_ready", 0)]
      and t.actions(g, "review")[0]["status"] == "cancelled", (t.calls(g), rows(t, g)))
check("T65 lý do review_due trở lại chờ; hẹn kiểm lại review_recheck sau một khoảng; không hẹn đối soát mồ côi; "
      "blocked/review_engine", t.st(g) == {"run_state": "blocked", "block_reason": "review_engine"}
      and {r["code"] for r in pend} == {"review_due", "review_recheck"}
      and all(float(r["due_at"]) >= t.clock() + R.REVIEW_ENGINE_RECHECK_S - 1 for r in pend
              if r["code"] == "review_recheck"), [(r["code"], r["due_at"]) for r in pend])
t.wake(g)
check("T65 thức trước hạn kiểm lại: không dựng engine lần nữa, không thêm hàng", len(rows(t, g)) == 1)
t.factory_raise = False
t.run(g, n=10, step=1)
check("T53 kiểm lại: review chạy, pass; tổng một lần tính; (1, 1, 2)", t.g(g).status == "succeeded"
      and [r[4] for r in rows(t, g)] == [0, 1] and t.calls(g) == (1, 1, 2), (t.st(g), rows(t, g)))

# ═══════════ T61: vết V8 ═══════════
t, g = ready_for_review("t61")
ctx, act = review_action(t, g)
t.store.abort_action(t.owner, act["id"], t.clock())             # lần 1: huỷ trước engine
R._finish_wake(ctx, t.deps())
t.factory_raise = True
t.wake(g)                                                        # lần 2: engine không dựng được
t.factory_raise = False
t.rev.script = [ERR, T.PASS]
t.clock.t += R.REVIEW_ENGINE_RECHECK_S + 1
t.wake(g)                                                        # lần 3: engine chạy, unknown/engine_error
used_before_retry = t.calls(g)
retry = [r for r in t.store.reasons(t.owner, g.id) if r["code"] == "review_retry"]
check("T61 V8: seq 1..3, charged 0,0,1, n=1; trước lần thử lại reviewer.used = 1; review_retry hẹn đúng "
      "ERROR_BACKOFF_S[0]", [r[0] for r in rows(t, g)] == [1, 2, 3] and [r[4] for r in rows(t, g)] == [0, 0, 1]
      and used_before_retry == (1, 1, 2) and retry and abs(float(retry[0]["due_at"]) - (t.clock() + BACKOFF1)) < 2,
      (rows(t, g), used_before_retry, retry))
t.run(g, n=10, step=1)
check("T61 thử lại hợp lệ sau backoff: pass, succeeded; seq 4; (1, 2, 3); engine 2 lượt thật",
      t.g(g).status == "succeeded" and [r[0] for r in rows(t, g)] == [1, 2, 3, 4] and t.calls(g) == (1, 2, 3)
      and t.rev.queries == 2, (rows(t, g), t.calls(g)))

# ═══════════ T64: hoàn lặp ═══════════
t, g = ready_for_review("t64")
ctx, act = review_action(t, g)
a1 = t.store.abort_action(t.owner, act["id"], t.clock())
a2 = t.store.abort_action(t.owner, act["id"], t.clock())
r1 = t.store.release_call(t.owner, g.id, act["id"])
t.reopen()
a3 = t.store.abort_action(t.owner, act["id"], t.clock())
R._finish_wake(ctx, t.deps())
check("T64 huỷ hai lần, release sau huỷ, mở lại kho rồi huỷ: chỉ lần đầu có tác dụng; (1, 0, 1); một lý do chờ",
      (a1, a2, r1, a3) == (True, False, False, False) and t.calls(g) == (1, 0, 1)
      and rows(t, g) == [(1, "cancelled", None, "not_run", 0)]
      and [c for c, _r in t.reasons(g)].count("review_due") == 1, ((a1, a2, r1, a3), t.calls(g), t.reasons(g)))
t2, g2 = ready_for_review("t64b")
ctx, act = review_action(t2, g2)
r1 = t2.store.release_call(t2.owner, g2.id, act["id"])
a1 = t2.store.abort_action(t2.owner, act["id"], t2.clock())
R._finish_wake(ctx, t2.deps())
check("T64 release rồi huỷ cùng hành động: trừ một lần", (r1, a1) == (True, False) and t2.calls(g2) == (1, 0, 1))
# Lượt việc của mục tiêu có đội: release (engine không dựng được) rồi huỷ: cờ `refunded` chặn trả hai lần.
t3 = T.Team(_STATE, "t64c")
g3 = t3.create()
d3 = t3.deps()
c3 = R._advance_prepare(g3.id, "wake", {}, d3, t3.clock())
pre = R._work_pre(c3.goal, c3.last, d3, t3.clock(), c3)
w1 = t3.store.release_call(t3.owner, g3.id, pre[0]["id"])
w2 = t3.store.release_call(t3.owner, g3.id, pre[0]["id"])
w3 = t3.store.abort_action(t3.owner, pre[0]["id"], t3.clock())
R._finish_wake(c3, d3)
check("T64 lượt việc có đội: release hai lần rồi huỷ: tổng và phần maker chỉ trừ một lần (0, 0, 0)",
      (w1, w2, w3) == (True, False, True) and t3.calls(g3) == (0, 0, 0), ((w1, w2, w3), t3.calls(g3)))

# ═══════════ T66: khởi động lại khi review đang chạy, rồi tới giờ action_recovery ═══════════
t, g = ready_for_review("t66")
ctx, act = review_action(t, g)
t.reopen()
t.clock.t += 700                                                 # giữa chừng: khoá còn, chưa tới hạn đối soát
t.wake(g)
check("T66 trước khi khoá hết: không đối soát, không gọi gì", t.reviews(g)[0]["status"] == "running"
      and t.work.queries == 1 and t.rev.queries == 0)
t.clock.t += 200
t.wake(g)
works = t.actions(g, "work")
check("T66 action_recovery tới: đối soát CHỈ bằng code; không mở lượt work; không gọi review trước backoff",
      t.reviews(g)[0]["status"] == "failed" and len(works) == 1 and t.work.queries == 1 and t.rev.queries == 0
      and t.st(g)["block_reason"] == "review_retry", (t.st(g), len(works)))

# ═══════════ T67: kết luận lỗi thời và lệch không tính vòng ═══════════
t, g = ready_for_review("t67")


def _revise_mid(e):
    if e.queries == 1:
        gg = t.g(g)
        fr = t.store.get_revision(t.owner, g.id, gg.revision)
        t.store.revise(t.owner, g.id, gg.revision, dict(fr, understanding="đổi giữa lúc review"), "sửa")


t.rev.script = [T.CHANGES, T.PASS]
t.rev.hook = _revise_mid
t.run(g, n=12)
check("T67 needs_changes lỗi thời (revision đổi giữa lúc review): không tính vào k, không sinh review_changes; "
      "bản đang dùng có review riêng", t.store.review_rounds(t.owner, g.id, 1) == 0
      and rows(t, g)[0][3] == "stale" and rows(t, g)[0][2] == "needs_changes" and t.g(g).status == "succeeded"
      and t.calls(g) == (1, 2, 3),
      (rows(t, g), t.st(g)))
rc = sqlite3.connect(str(t.store.path)).execute(
    "SELECT COUNT(*) FROM wake_reasons WHERE goal_id=? AND code='review_changes'", (g.id,)).fetchone()[0]
check("T67 không có lý do review_changes nào được tạo", rc == 0, rc)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    raise SystemExit(1)
print("\nOK")
