"""Resonance A5: một agent làm, một agent review cho mỗi mục tiêu (thiết kế chốt tại 56f7ab50).

    python tests/run.py resonance_a5_team -v

Kho SQLite thật, engine GIẢ hai vai (lượt review nhận `R.REVIEW_SYSTEM`), đồng hồ giả. Mục tiêu tạo qua `form_goal` thật
(đường của tool javis_goal và /goal-requests; T31, T32 đi qua chính plugin và chính route), chạy qua `R.advance` thật
(cổng, scheduler, kho). Không gọi model thật. Tên ca theo ma trận nghiệm thu mục 15 của
docs/superpowers/specs/2026-10-11-resonance-a5-maker-reviewer-design.md. Mỗi ca kiểm: trạng thái và lý do, lượt (maker,
reviewer, tổng), số lần engine giả được gọi, và kết quả nào được phép dùng.

Ngân sách và bộ đếm thử lại (T5 đến T9, T47 đến T54, T61 đến T67) ở test_resonance_a5_budget.py.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import os
import sqlite3
import tempfile
from pathlib import Path

_STATE = Path(tempfile.mkdtemp(prefix="javis-res-a5-"))
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
GOOD4 = T.GOOD.replace("Xong.", "Xong, bản sửa lần ba.")

# ═══════════ parse_review: hàm thuần, đóng khi lỗi (mục 5.2; T5, T26) ═══════════
check("parse: pass hợp lệ", R.parse_review(T.PASS, 1)["verdict"] == "pass")
check("parse: needs_changes hợp lệ", R.parse_review(T.CHANGES, 1)["verdict"] == "needs_changes")
check("parse: bỏ được một lớp rào ```json", R.parse_review("```json\n" + T.PASS + "\n```", 1)["verdict"] == "pass")
for label, txt in (("không phải JSON", "Đạt, bản tốt."), ("JSON lẫn chữ", "Kết luận: " + T.PASS),
                   ("thiếu criteria", json.dumps({"verdict": "pass", "fixes": ""})),
                   ("verdict lạ", json.dumps({"verdict": "ok", "criteria": [{"index": 0, "ok": True}]})),
                   ("ok không phải bool", json.dumps({"verdict": "pass", "criteria": [{"index": 0, "ok": "true"}]})),
                   ("index trùng", json.dumps({"verdict": "pass", "criteria": [{"index": 0, "ok": True},
                                                                              {"index": 0, "ok": True}]})),
                   ("thiếu một chỉ số", T.verdict("pass", (True,))), ("index ngoài tầm", json.dumps(
                       {"verdict": "pass", "criteria": [{"index": 5, "ok": True}]})),
                   ("mảng thay vì đối tượng", "[" + T.PASS + "]")):
    n = 2 if label == "thiếu một chỉ số" else 1
    r = R.parse_review(txt, n)
    check(f"T5 parse đóng khi lỗi: {label} -> unknown/parse_error", r["verdict"] == "unknown"
          and r["reason_code"] == "parse_error", r)
r = R.parse_review(T.verdict("pass", (False,)), 1)
check("T5 parse: pass mà có tiêu chí ok=false -> unknown/inconsistent", r == {**r, "verdict": "unknown",
                                                                             "reason_code": "inconsistent"}, r)
r = R.parse_review(T.verdict("needs_changes", (True,), ""), 1)
check("T5 parse: needs_changes mà mọi tiêu chí đạt và không có fixes -> inconsistent",
      r["verdict"] == "unknown" and r["reason_code"] == "inconsistent", r)
r = R.parse_review(json.dumps({"verdict": "pass", "criteria": [{"index": 0, "ok": True}], "fixes": "",
                               "budget_calls": 99, "criteria_override": ["x"], "role": "maker"}), 1)
check("T26 parse: trường lạ bị bỏ qua, chỉ báo tên; kết luận chỉ từ ba trường",
      r["verdict"] == "pass" and r["extra_keys"] == ["budget_calls", "criteria_override", "role"]
      and set(r) == {"verdict", "reason_code", "criteria", "fixes", "extra_keys"}, r)

# ═══════════ T1: làm, đạt khách quan, review pass ═══════════
t = T.Team(_STATE, "t1")
g = t.create()
t.run(g)
rv = t.reviews(g)
check("T1 succeeded; lượt (1, 1, 2); engine giả: 1 lượt làm, 1 lượt review", t.g(g).status == "succeeded"
      and t.calls(g) == (1, 1, 2) and t.work.queries == 1 and t.rev.queries == 1, (t.g(g).status, t.calls(g)))
check("T1 kết luận dùng để chốt là review pass của H1; sự kiện kết thúc mang review_id",
      len(rv) == 1 and rv[0]["verdict"] == "pass" and rv[0]["status"] == "done" and rv[0]["charged"] == 1
      and any(e["payload"].get("review_id") == rv[0]["id"] for e in t.events(g, "succeeded")), rv)
check("T1 review không ghi gì vào brain: file đích là đúng bản của vai làm",
      t.target().read_text(encoding="utf-8") == T.GOOD)
check("T1 lượt review đọc ảnh chụp bản đã tiếp nhận (hash bytes gửi bằng hash đã ghim)",
      T.GOOD in t.rev.prompts[0] and rv[0]["artifact_sha"] == R._sha(T.GOOD.encode("utf-8")))
check("T1 lời dặn review đúng hợp đồng: mô tả vai của reviewer là dữ liệu",
      "Mô tả vai của bạn (dữ liệu)" in t.rev.prompts[0] and "Trợ lý thử nguoi-duyet" in t.rev.prompts[0])
check("T1 đội gắn lúc tạo: budget 8, maker 4, reviewer 4, tối đa 2 vòng",
      t.g(g).budget_calls == 8 and t.team(g)["calls"] == {"maker": {"cap": 4, "used": 1}, "reviewer": {"cap": 4, "used": 1}}
      and t.team(g)["max_rounds"] == 2)

# ═══════════ T2: có human_confirmation ═══════════
t = T.Team(_STATE, "t2")
g = t.create(human=True)
t.run(g)
check("T2 review pass rồi mới chờ người xác nhận: waiting/human_confirmation, (1, 1, 2)",
      t.st(g) == {"run_state": "waiting", "block_reason": "human_confirmation"} and t.calls(g) == (1, 1, 2)
      and t.rev.queries == 1, (t.st(g), t.calls(g)))
gg = t.g(g)
crit = next(c for c in gg.criteria if c.get("evaluator") == "human_confirmation")
R.apply_feedback(t.store, t.owner, g.id, "outcome_accepted",
                 {"expected_revision": gg.revision, "criterion_id": crit["id"],
                  "artifact_ref": R.current_artifact_ref(gg, t.deps())}, t.brain)
t.run(g)
check("T2 chủ xác nhận đúng sha: succeeded, không thêm lượt", t.g(g).status == "succeeded" and t.calls(g) == (1, 1, 2),
      (t.g(g).status, t.st(g), t.calls(g)))

# ═══════════ T3: needs_changes, làm sửa, review bản mới pass ═══════════
t = T.Team(_STATE, "t3")
t.work.script = [T.GOOD, GOOD2]
t.rev.script = [T.CHANGES, T.PASS]
g = t.create()
t.run(g)
rv = t.reviews(g)
check("T3 succeeded; (2, 2, 4); hai hàng review gắn hai bộ ghim khác nhau", t.g(g).status == "succeeded"
      and t.calls(g) == (2, 2, 4) and len(rv) == 2 and rv[0]["bundle_ref"] != rv[1]["bundle_ref"]
      and [x["verdict"] for x in rv] == ["needs_changes", "pass"], [(x["verdict"], x["bundle_ref"][:30]) for x in rv])
check("T3 góp ý vào lời nhắc lượt sửa (dữ liệu), vòng 1/2", "Người review góp ý" in t.work.prompts[1]
      and "Thêm mục Kết luận rõ hơn" in t.work.prompts[1]
      and t.store.review_rounds(t.owner, g.id, 1) == 1, t.work.prompts[1][-400:])
check("T3 file đích là bản sửa đã được review pass", t.target().read_text(encoding="utf-8") == GOOD2)

# ═══════════ T4: needs_changes ba lần: k=1,2 cho sửa, k=3 chặn ═══════════
t = T.Team(_STATE, "t4")
t.work.script = [T.GOOD, GOOD2, GOOD3, GOOD4]
t.rev.script = [T.CHANGES]
g = t.create()
t.run(g, n=20)
ob = [r for r in sqlite3.connect(str(t.store.path)).execute("SELECT kind FROM outbox WHERE goal_id=?", (g.id,))]
check("T4 blocked/review_rounds sau kết luận needs_changes thứ 3; (3, 3, 6); không có lượt sửa thứ ba",
      t.st(g) == {"run_state": "blocked", "block_reason": "review_rounds"} and t.calls(g) == (3, 3, 6)
      and t.work.queries == 3 and t.rev.queries == 3 and t.store.review_rounds(t.owner, g.id, 1) == 3,
      (t.st(g), t.calls(g), t.work.queries))
check("T4 tin goal.review_exhausted (loại phải gửi)", ("goal.review_exhausted",) in ob, ob)
check("T4 không tự nới: chạy thêm không gọi model", (t.run(g), t.work.queries, t.rev.queries)[1:] == (3, 3))

# ═══════════ T31 tới T36: gắn đội trong giao dịch tạo (R1) ═══════════
# T31: tạo qua CHÍNH tool javis_goal (plugin), trong lượt chat của agent làm, kho mặc định của host.
_spec = importlib.util.spec_from_file_location("javis_goal_plugin", str(Path(ROOT) / "system" / "plugins" / "javis-goal"
                                                                          / "plugin.py"))
PLUG = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PLUG)


class _Ctx:
    def __init__(self, vault):
        self.vault_root = vault


t = T.Team(_STATE, "resonance")          # kho mặc định của host: STATE_DIR/resonance.sqlite3 (plugin mở kho này)
check("T31 kho của test là kho mặc định mà plugin mở", Path(t.store.path) == Path(RS.GoalStore().path))
orig_assign = RS.GoalStore.assign_goal


def _no_assign(*a, **k):
    raise AssertionError("create không được gọi assign_goal")


RS.GoalStore.assign_goal = _no_assign
mid, ref = t.next()
with RA.turn(t.ag(), t.sid, mid, T.USER, t.brain, slug=T.MAKER, store=t.store):
    out = asyncio.run(PLUG.javis_goal({"op": "create", **t.proposal()}, _Ctx(t.brain)))
RS.GoalStore.assign_goal = orig_assign
g = t.store.find_by_key(t.owner, ref)
tm = t.team(g)
created = [e for e in t.store.events(t.owner, g.id) if e["kind"] in ("created", "team_attached")]
# 0.142.0: bỏ người review cố định. Đường thật (tool javis_goal mở kho mặc định của host, không bật cờ của test) KHÔNG
# gắn đội nữa, kể cả khi trợ lý còn một cặp làm/review cũ trong kho.
check("T31 (0.142.0) tool javis_goal: mục tiêu mới KHÔNG có đội dù có cặp cũ, không lấy ngân sách đội 8, chỉ một sự kiện tạo",
      "Đã lập mục tiêu" in out and tm is None and t.g(g).budget_calls != 8
      and [e["kind"] for e in created] == ["created"], (out[:200], tm, created))
try:
    t.store.assign_goal(t.owner, g.id, t.maker["agent_key"], g.revision)
    _conf = False
except RS.ConflictError:
    _conf = True
check("T31 gọi assign_goal sau đó bị từ chối (đã gán), không có giao dịch thứ hai", _conf)

# T32: tạo qua CHÍNH route POST /goal-requests (bộ lập mục tiêu chạy bằng engine giả, không phải model thật).
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import resonance_api as RAPI  # noqa: E402

t32 = T.Team(_STATE, "t32")
_framer = T.Engine(json.dumps(t32.proposal(), ensure_ascii=False))
_msgs = {}


class _Sessions:
    def get_session(self, sid):
        return {"brain": t32.brain, "channel": f"agent:{T.MAKER}", "created_at": 1.0} if sid in _msgs else None

    def get_messages(self, sid):
        return [{"id": i, "role": "user", "content": txt} for i, txt in _msgs.get(sid, {}).items()]


_app = FastAPI()
RAPI.register(_app, RAPI.ResonanceApiDeps(
    store=lambda: t32.store, brain_key=lambda b: t32.brain,
    engine_factory=lambda s, tag: (_framer, {"provider": "fake", "model": "fake-1", "text_only": True}),
    session_store=lambda: _Sessions()))
_msgs["s32"] = {7: T.USER}
r = TestClient(_app).post("/goal-requests", params={"brain": "x"}, json={"message_ref": R.message_ref("s32", 7)})
g32 = t32.store.find_by_key(t32.owner, R.message_ref("s32", 7))
check("T32 /goal-requests: đội active trong giao dịch tạo, budget 8; bộ lập là engine giả (1 lượt, sổ riêng)",
      r.status_code == 200 and g32 is not None and (t32.team(g32) or {}).get("status") == "active"
      and t32.g(g32).budget_calls == 8 and _framer.queries == 1 and t32.calls(g32) == (0, 0, 0),
      (r.status_code, r.text[:300]))

# T33: tạo lặp cùng tin, giữa hai lần đổi cặp sang reviewer khác: không đổi gì.
t = T.Team(_STATE, "t33")
mid, ref = t.next()
g = t.create(mid, ref)
third = RA.enable(t.store, t.brain, "nguoi-thu-ba")
t.store.team_pair_set(t.owner, t.maker["agent_key"], third["agent_key"])
g2 = t.create(mid, ref)
check("T33 tạo lặp cùng khoá: trả mục tiêu cũ; reviewer, budget, team_calls không đổi; không thêm sự kiện gắn đội",
      g2.id == g.id and t.team(g)["reviewer_agent_key"] == t.reviewer["agent_key"] and t.g(g).budget_calls == 8
      and len(t.events(g, "team_attached")) == 1, t.team(g))
g3 = t.create()
check("T33 đổi cặp chỉ áp cho mục tiêu MỚI", t.team(g3)["reviewer_agent_key"] == third["agent_key"]
      and t.team(g)["reviewer_agent_key"] == t.reviewer["agent_key"])

# T34 / T25: cặp tắt, hay không có cặp: không có đội, chạy như A4.
t = T.Team(_STATE, "t34")
t.store.team_pair_set(t.owner, t.maker["agent_key"], None)
g = t.create()
t.run(g)
check("T34 cặp tắt lúc tạo: không có goal_team; như A4 (succeeded, 1 lượt, budget 4 như người gọi đưa, 0 review)",
      t.team(g) is None and t.g(g).status == "succeeded" and t.g(g).calls_used == 1 and t.g(g).budget_calls == 4
      and t.rev.queries == 0, (t.team(g), t.g(g).status))
t = T.Team(_STATE, "t25", pair=False)
g = t.create()
t.run(g)
check("T25 không có cặp: như A4", t.team(g) is None and t.g(g).status == "succeeded" and t.rev.queries == 0)

# T35: reviewer bị tắt đúng lúc tạo (cặp vẫn bật): vẫn có đội, cổng chặn, không bỏ review.
t = T.Team(_STATE, "t35")
RA.disable(t.store, t.brain, T.REVIEWER)
g = t.create()
t.run(g)
check("T35 reviewer tắt lúc tạo: đội active, blocked/reviewer_off, không gọi model nào, không chốt",
      (t.team(g) or {}).get("status") == "active" and t.st(g) == {"run_state": "blocked", "block_reason": "reviewer_off"}
      and t.work.queries == 0 and t.rev.queries == 0 and t.g(g).status == "active", (t.st(g), t.work.queries))

# T36: mục tiêu cũ đã tiêu lượt, gán qua assign_goal cho agent có cặp: không có đội.
t = T.Team(_STATE, "t36")
d0 = R.GoalDeps(engine_factory=lambda s, x: (None, {}), budget=R.CallBudget(0), store=t.store)
it = t.store.add_intent(t.owner, t.sid, 99, T.USER)
gl, _ = t.store.create(t.owner, it["id"], R.validate_proposal(t.proposal(), T.USER, source_ref="legacy"), "legacy:1",
                       budget_calls=6)
with sqlite3.connect(str(t.store.path)) as c:
    c.execute("UPDATE goals SET calls_used=3 WHERE id=?", (gl.id,))
RA.assign(t.store, t.brain, gl.id, t.maker["agent_key"])
ev = t.events(gl, "agent_assigned")
check("T36 assign_goal: không gắn đội, calls_used giữ 3, sự kiện ghi not_attached_legacy, thẻ nói không có người review",
      t.team(gl) is None and t.g(gl).calls_used == 3 and ev and ev[-1]["payload"].get("team") == "not_attached_legacy"
      and (R.goal_view(t.store, t.owner, gl.id, t.brain) or {}).get("team") == {"legacy": True},
      (t.team(gl), ev))

# ═══════════ R2: bộ ghim, lịch review, đồng thời (T11 tới T14, T22, T37 tới T41, T59) ═══════════


def revise_same(t, g, understanding):
    """Chủ dự án sửa cách hiểu, GIỮ NGUYÊN tiêu chí (cùng id, cùng nội dung): revision mới, cùng hash tiêu chí."""
    gg = t.g(g)
    fr = t.store.get_revision(t.owner, g.id, gg.revision)
    return t.store.revise(t.owner, g.id, gg.revision, dict(fr, understanding=understanding), "sửa cách hiểu")


# T11: revision đổi TRONG LÚC review chạy.
t = T.Team(_STATE, "t11")
g = t.create()
t.wake(g)                                   # vai làm: H1, đạt khách quan, hẹn review
t.rev.hook = lambda e: (revise_same(t, g, "Bản tóm tắt, đổi cách hiểu giữa lúc review") if e.queries == 1 else None)
t.run(g, n=12)
rv = t.reviews(g)
check("T11 kết luận của revision cũ ghi nhưng 'stale', không dùng, không tính vòng; review mới cho revision 2 "
      "(bản trên đĩa đã đạt kiểm nên vai làm không chạy lại, đúng luật A2): (1, 2, 3)",
      [(x["revision"], x["verdict"], x["reason_code"]) for x in rv] == [(1, "pass", "stale"), (2, "pass", "")]
      and t.g(g).status == "succeeded" and t.g(g).revision == 2 and t.calls(g) == (1, 2, 3)
      and t.store.review_rounds(t.owner, g.id, 1) == 0,
      ([(x["revision"], x["verdict"], x["reason_code"]) for x in rv], t.calls(g), t.st(g)))

# T12: kết luận lệch hành động (bộ ghim của hàng review bị đổi): `review_mismatch`, không dùng.
t = T.Team(_STATE, "t12")
g = t.create()
t.wake(g)


def _tamper(e):
    if e.queries == 1:
        with sqlite3.connect(str(t.store.path)) as c:
            c.execute("UPDATE reviews SET bundle_ref=bundle_ref||':x' WHERE status='running'")


t.rev.hook = _tamper
t.run(g, n=12)
rv = t.reviews(g)
check("T12 review_mismatch: lưu, không dùng để chốt; review lại đúng bộ ghim (rearm vì bộ ghim chưa có hàng nào)",
      [x["reason_code"] for x in rv] == ["review_mismatch", ""] and t.g(g).status == "succeeded"
      and t.calls(g) == (1, 2, 3), ([(x["verdict"], x["reason_code"]) for x in rv], t.calls(g), t.st(g)))

# T13: kết quả review gửi lại hai lần cùng hành động.
t = T.Team(_STATE, "t13")
g = t.create()
t.run(g)
act = t.actions(g, "review")[0]
again = t.store.record_review(t.owner, act["id"], {"verdict": "needs_changes", "criteria": [], "fixes": "x"}, "x")
check("T13 ghi lần hai cùng hành động bị bỏ qua: một hàng done, không đổi lượt hay trạng thái",
      again.get("recorded") is False and len(t.reviews(g)) == 1 and t.reviews(g)[0]["verdict"] == "pass"
      and t.calls(g) == (1, 1, 2) and t.g(g).status == "succeeded", again)

# T14 (a, b): tiến trình chết sau khi giữ chỗ review (trước hay trong lúc gọi engine; kho thấy như nhau).
t = T.Team(_STATE, "t14")
g = t.create()
t.wake(g)
deps = t.deps()
ctx = R._advance_prepare(g.id, "wake", {}, deps, t.clock())
check("T14 chuẩn bị: nhánh đội quyết một lượt review", isinstance(ctx, R._WakeCtx) and ctx.mode == "review", ctx)
pre = R._review_pre(ctx.goal, ctx, deps, t.clock())
check("T14 đã giữ chỗ: hành động review running, hàng review running, charged=1, (1, 1, 2)",
      isinstance(pre, tuple) and t.actions(g, "review")[0]["status"] == "running"
      and t.reviews(g)[0]["status"] == "running" and t.reviews(g)[0]["charged"] == 1 and t.calls(g) == (1, 1, 2))
t.reopen()                                  # "khởi động lại": khoá lượt và khoá hành động hết hạn theo đồng hồ
t.clock.t += deps.max_wall_s + deps.wall_grace_s + R.LEASE_EXTRA_S + 5
t.wake(g)
rv = t.reviews(g)
pend = t.store.reasons(t.owner, g.id)
check("T14 đối soát bằng code: failed/interrupted, charged giữ 1, KHÔNG gọi model, không mở lượt vai làm",
      rv[0]["status"] == "failed" and rv[0]["reason_code"] == "interrupted" and rv[0]["charged"] == 1
      and t.rev.queries == 0 and t.work.queries == 1 and t.calls(g) == (1, 1, 2), (rv[0], t.work.queries))
check("T14 review_retry hẹn đúng backoff lần tính 1 (ERROR_BACKOFF_S[0]), không gọi sớm",
      [(r["code"], r["source_ref"]) for r in pend if r["code"].startswith("review")] == [("review_retry",
                                                                                          f"rr:{rv[0]['id']}")]
      and min(float(r["due_at"]) for r in pend if r["code"] == "review_retry") >= t.clock() + HB.POLICY[
          "ERROR_BACKOFF_S"][0] - 1, pend)
t.wake(g)
check("T14 thức trước hạn backoff: không gọi review", t.rev.queries == 0)
t.run(g, n=12, step=1)
check("T14 tới hạn: thử lại đúng một lần, pass, succeeded; (1, 2, 3); seq 1, 2", t.g(g).status == "succeeded"
      and t.rev.queries == 1 and t.calls(g) == (1, 2, 3) and [x["seq"] for x in t.reviews(g)] == [1, 2],
      (t.st(g), t.calls(g)))

# T14 (c): đã ghi kết luận, chưa chốt: khởi động lại thì chốt mà không gọi thêm model.
t = T.Team(_STATE, "t14c")
g = t.create()
t.wake(g)
t.wake(g)                                   # review pass được ghi; lý do review_done chờ
check("T14c sau ghi kết luận: chưa chốt, lý do review_done chờ", t.g(g).status == "active"
      and ("review_done", f"rd:{t.reviews(g)[0]['id']}") in t.reasons(g), t.reasons(g))
t.reopen()
t.run(g)
check("T14c khởi động lại: chốt succeeded, không gọi thêm model", t.g(g).status == "succeeded"
      and (t.work.queries, t.rev.queries) == (1, 1))

# T22: hai lần thức đồng thời khi lý do review đến hạn: một hành động chạy.
t = T.Team(_STATE, "t22")
g = t.create()
t.wake(g)


async def _two():
    return await asyncio.gather(R.advance(g.id, {"kind": "wake"}, t.deps()), R.advance(g.id, {"kind": "wake"}, t.deps()))


asyncio.run(_two())
check("T22 hai lần thức cùng lúc: đúng một lượt review", t.rev.queries == 1 and len(t.actions(g, "review")) == 1
      and t.calls(g) == (1, 1, 2))

# T37: revision 2 giữ nguyên bytes và tiêu chí của revision 1 đã review.
t = T.Team(_STATE, "t37")
g = t.create()
t.wake(g)
t.wake(g)                                   # pass cho revision 1, chưa chốt
revise_same(t, g, "Cùng bản, chỉ đổi cách hiểu")
t.run(g, n=12)
rv = t.reviews(g)
check("T37 revision mới cùng bytes và tiêu chí: review_due mới (ref có revision) được phục vụ, không chờ mãi",
      t.g(g).status == "succeeded" and [x["revision"] for x in rv] == [1, 2] and rv[1]["verdict"] == "pass"
      and rv[0]["artifact_sha"] == rv[1]["artifact_sha"] and rv[0]["criteria_hash"] == rv[1]["criteria_hash"],
      ([(x["revision"], x["verdict"]) for x in rv], t.st(g)))

# T38: một sự kiện review_due gửi hai lần.
t = T.Team(_STATE, "t38")
g = t.create()
t.wake(g)
ref = next(r for c, r in t.reasons(g) if c == "review_due")
dup = t.store.add_reason_event(t.owner, g.id, "review_due", ref)
t.run(g)
check("T38 gửi lặp cùng (mã, ref): một lý do, một lượt review", dup is False and t.rev.queries == 1
      and t.calls(g) == (1, 1, 2) and t.g(g).status == "succeeded")

# T39 + T41: unknown, khởi động lại giữa hai lần, thử lại đúng một lần; lịch vật lý đúng.
t = T.Team(_STATE, "t39")
t.rev.script = ["không phải JSON", T.PASS]
g = t.create()
t.wake(g)
t.wake(g)
rv = t.reviews(g)
wk = [w for w in t.store.wakes(t.owner, g.id) if w["kind"] == "work"]
check("T39 unknown/parse_error: hàng failed, charged=1; review_retry hẹn sau backoff; lịch vật lý đúng giờ đó",
      rv[0]["status"] == "failed" and rv[0]["reason_code"] == "parse_error" and rv[0]["charged"] == 1
      and t.st(g)["block_reason"] == "review_retry" and wk and float(wk[0]["due_at"]) >= t.clock() + 3599,
      (rv[0], t.st(g), wk))
check("T41 không có lý do treo khác: chỉ review_retry và hẹn đối soát chỉ-code đang chờ",
      {c for c, _r in t.reasons(g)} <= {"review_retry", "action_recovery"}, t.reasons(g))
t.reopen()
t.run(g, n=12, step=1)
rv = t.reviews(g)
check("T39 sau khởi động lại: thử lại đúng một lần, pass; seq liên tục 1, 2; n = 2; (1, 2, 3)",
      t.g(g).status == "succeeded" and t.rev.queries == 2 and [x["seq"] for x in rv] == [1, 2]
      and sum(x["charged"] for x in rv) == 2 and t.calls(g) == (1, 2, 3), (t.calls(g), t.st(g)))

# T40: chủ dự án tắt rồi bật reviewer sau khi đã có pass (version mới): review lại một lượt.
t = T.Team(_STATE, "t40")
g = t.create()
t.wake(g)
t.wake(g)
v_before = t.ag(T.REVIEWER)["config_version"]
RA.disable(t.store, t.brain, T.REVIEWER)
a = RA.enable(t.store, t.brain, T.REVIEWER)
t.store.wake_agent_goals(t.brain, a["agent_key"])
t.run(g, n=12)
rv = t.reviews(g)
check("T40 bật lại cùng mã (version mới): kết luận v cũ không dùng; review lại; succeeded; (1, 2, 3)",
      a["config_version"] == v_before + 2 and t.g(g).status == "succeeded" and t.calls(g) == (1, 2, 3)
      and [x["reviewer_config_version"] for x in rv] == [v_before, v_before + 2], ([x["reviewer_config_version"]
                                                                                    for x in rv], t.calls(g)))

# T59: chat của vai làm sửa mục tiêu và nộp bản mới (A4) TRONG LÚC review nền chạy: lease không khoá chat.
t = T.Team(_STATE, "t59")
g = t.create()
t.wake(g)
H3 = T.GOOD.replace("Xong.", "Xong, bản nộp từ chat.")
_out = {}


def _chat_during_review(e):
    if e.queries == 1:
        _out["r"] = t.chat_update(g, H3)


t.rev.hook = _chat_during_review
t.run(g, n=15)
rv = t.reviews(g)
check("T59 bản nộp từ chat giữa lúc review: kết luận cũ 'stale'; review bản mới; file là bản chat; succeeded",
      (_out.get("r") or (None, {}, ""))[2] == "submission_published"
      and [x["reason_code"] for x in rv] == ["stale", ""] and rv[1]["artifact_sha"] == R._sha(H3.encode("utf-8"))
      and t.target().read_text(encoding="utf-8") == H3 and t.g(g).status == "succeeded",
      (_out.get("r"), [(x["verdict"], x["reason_code"]) for x in rv], t.st(g)))

# ═══════════ R3: reviewer tắt, bật, mất, nghỉ (T18, T19, T42 tới T46) ═══════════
t = T.Team(_STATE, "t18")
g = t.create()
t.wake(g)                                   # có review_due chờ
RA.disable(t.store, t.brain, T.REVIEWER)
t.wake(g)
check("T18 tắt reviewer khi chờ review: blocked/reviewer_off, hẹn agent_recheck, không gọi model",
      t.st(g) == {"run_state": "blocked", "block_reason": "reviewer_off"} and t.rev.queries == 0
      and any(c == "agent_recheck" for c, _r in t.reasons(g)), (t.st(g), t.reasons(g)))
ob = [r[0] for r in sqlite3.connect(str(t.store.path)).execute("SELECT kind FROM outbox WHERE goal_id=?", (g.id,))]
check("T18 tin goal.review_blocked một lần", ob.count("goal.review_blocked") == 1, ob)
a = RA.enable(t.store, t.brain, T.REVIEWER)
t.store.wake_agent_goals(t.brain, a["agent_key"])
t.run(g)
check("T18 bật lại cùng mã: chạy tiếp, review, succeeded; (1, 1, 2)", t.g(g).status == "succeeded"
      and t.calls(g) == (1, 1, 2), (t.st(g), t.calls(g)))

# T42: on v1 có pass, off v2, on v3 (cùng T40 nhưng kiểm thêm lượt, vòng và chuỗi lỗi không reset).
t = T.Team(_STATE, "t42")
t.work.script = [T.GOOD, GOOD2]
t.rev.script = [T.CHANGES, T.PASS, T.PASS]
g = t.create()
for _ in range(4):
    t.wake(g)                               # H1 -> needs_changes -> H2 -> pass (chưa chốt)
rounds_before = t.store.review_rounds(t.owner, g.id, 1)
RA.disable(t.store, t.brain, T.REVIEWER)
a = RA.enable(t.store, t.brain, T.REVIEWER)
t.store.wake_agent_goals(t.brain, a["agent_key"])
t.run(g, n=12)
check("T42 bật lại: không reset team_calls, vòng (1) hay lượt; review lại một lượt; succeeded; (2, 3, 5)",
      rounds_before == 1 and t.store.review_rounds(t.owner, g.id, 1) == 1 and t.g(g).status == "succeeded"
      and t.calls(g) == (2, 3, 5), (rounds_before, t.calls(g), t.st(g)))

# T43: review đang chạy lúc tắt rồi bật.
t = T.Team(_STATE, "t43")
g = t.create()
t.wake(g)


def _flip(e):
    if e.queries == 1:
        RA.disable(t.store, t.brain, T.REVIEWER)
        RA.enable(t.store, t.brain, T.REVIEWER)


t.rev.hook = _flip
t.run(g, n=12)
rv = t.reviews(g)
check("T43 kết quả ghi với version cũ là 'stale', không dùng; review version mới; succeeded; (1, 2, 3)",
      [x["reason_code"] for x in rv] == ["stale", ""] and t.g(g).status == "succeeded" and t.calls(g) == (1, 2, 3),
      ([(x["verdict"], x["reason_code"]) for x in rv], t.calls(g)))

# T44: khởi động lại khi reviewer đang tắt.
t = T.Team(_STATE, "t44")
g = t.create()
t.wake(g)
RA.disable(t.store, t.brain, T.REVIEWER)
t.wake(g)
t.reopen()
t.clock.t += R.REVIEW_MIN_S + 1
t.run(g, n=6)
check("T44 sau khởi động lại vẫn blocked/reviewer_off, không gọi model; chỉ hẹn gỡ gác kéo lịch",
      t.st(g)["block_reason"] == "reviewer_off" and t.rev.queries == 0, (t.st(g), t.reasons(g)))

# T45: file reviewer mất, chủ dự án xác nhận cùng trợ lý (confirmed_same): cùng mã, version mới, review lại.
t = T.Team(_STATE, "t45")
g = t.create()
t.wake(g)
t.wake(g)                                   # pass v1, chưa chốt
f = Path(t.brain) / "agents" / f"{T.REVIEWER}.md"
body = f.read_text(encoding="utf-8")
f.unlink()
t.wake(g)
check("T45 file reviewer mất: blocked/reviewer_missing", t.st(g)["block_reason"] == "reviewer_missing", t.st(g))
f.write_text(body, encoding="utf-8")
key = t.reviewer["agent_key"]
t.store.agent_confirm(t.owner, key, True)
t.store.wake_agent_goals(t.brain, key)
t.run(g, n=12)
check("T45 xác nhận cùng trợ lý: cùng mã, version mới; review lại; succeeded; (1, 2, 3)",
      t.store.agent_by_key(t.brain, key)["status"] == "active" and t.g(g).status == "succeeded"
      and t.calls(g) == (1, 2, 3), (t.st(g), t.calls(g)))

# T46: reviewer bị xoá (nghỉ mã), tạo agent mới cùng slug và cùng tag: không thay.
t = T.Team(_STATE, "t46")
g = t.create()
t.wake(g)
t.store.agent_retire(t.owner, T.REVIEWER)
newrv = RA.enable(t.store, t.brain, T.REVIEWER)
f = Path(t.brain) / "agents" / f"{T.REVIEWER}.md"
f.write_text("---\nname: nguoi-duyet\ntags:\n- Review\n---\nTrợ lý mới cùng tên\n", encoding="utf-8")
t.store.wake_agent_goals(t.brain, newrv["agent_key"])
t.run(g, n=8)
check("T46 mã cũ nghỉ: blocked/reviewer_retired; agent mới cùng slug/tag là mã khác, không được nhận; 0 lượt review",
      newrv["agent_key"] != t.reviewer["agent_key"] and t.team(g)["reviewer_agent_key"] == t.reviewer["agent_key"]
      and t.st(g)["block_reason"] == "reviewer_retired" and t.rev.queries == 0, (t.st(g), t.rev.queries))
R.apply_command(t.store, t.owner, g.id, "team_detach", {}, t.brain)
t.run(g, n=8)
check("T46 chỉ chủ dự án tách đội mới hết kẹt: chốt theo luật A4", t.team(g)["status"] == "detached"
      and t.g(g).status == "succeeded" and t.rev.queries == 0, (t.st(g), t.g(g).status))

# T19: đổi trạng thái reviewer trong lúc review chạy (tắt và để tắt).
t = T.Team(_STATE, "t19")
g = t.create()
t.wake(g)
t.rev.hook = lambda e: RA.disable(t.store, t.brain, T.REVIEWER) if e.queries == 1 else None
t.run(g, n=8)
rv = t.reviews(g)
check("T19 kết luận của lượt đang chạy là review cũ ('stale'), không dùng; mục tiêu chặn reviewer_off",
      [x["reason_code"] for x in rv] == ["stale"] and t.st(g)["block_reason"] == "reviewer_off"
      and t.g(g).status == "active" and t.calls(g) == (1, 1, 2), ([x["reason_code"] for x in rv], t.st(g)))

# ═══════════ R5: file sửa tay và ảnh chụp (T10, T28, T55 tới T58) ═══════════
H2 = T.GOOD.replace("Xong.", "Xong, chủ dự án tự sửa tay.")
t = T.Team(_STATE, "t10")
g = t.create()
t.wake(g)
t.wake(g)                                   # pass cho H1, chưa chốt
t.target().write_text(H2, encoding="utf-8", newline="\n")
t.run(g, n=6)
check("T10 sửa tay thành H2 (vẫn đạt khách quan) sau pass của H1: waiting/source_drift; không review, không chốt, "
      "không đăng đè; 0 lượt thêm", t.st(g) == {"run_state": "waiting", "block_reason": "source_drift"}
      and t.g(g).status == "active" and t.target().read_text(encoding="utf-8") == H2
      and (t.work.queries, t.rev.queries) == (1, 1), (t.st(g), t.g(g).status))

# T56: khôi phục đúng bytes H1: dùng lại review H1, không gọi model.
t.target().write_text(T.GOOD, encoding="utf-8", newline="\n")
t.wake(g)
check("T56 khôi phục đúng H1: succeeded bằng review H1 cũ, không gọi model", t.g(g).status == "succeeded"
      and (t.work.queries, t.rev.queries) == (1, 1) and len(t.reviews(g)) == 1, (t.st(g), t.g(g).status))

# T57: sau sửa tay, vai làm nộp H2 qua A4 hợp lệ (chat): mốc đăng mới, review H2 đọc từ bằng chứng H2.
t = T.Team(_STATE, "t57")
g = t.create()
t.wake(g)
t.wake(g)
t.target().write_text(H2, encoding="utf-8", newline="\n")
t.run(g, n=4)
g2, sub, ho = t.chat_update(g, H2)
t.run(g, n=12)
rv = t.reviews(g)
check("T57 bản H2 qua A4 hợp lệ: review mới đọc bằng chứng H2 (hash khớp); succeeded; vai làm 0 lượt nền thêm",
      sub.get("ok") and ho == "submission_published" and len(rv) == 2 and rv[1]["artifact_sha"] == R._sha(
          H2.encode("utf-8")) and H2 in t.rev.prompts[-1] and t.g(g).status == "succeeded" and t.work.queries == 1,
      (sub, ho, [(x["revision"], x["verdict"]) for x in rv], t.st(g)))

# T55: sửa tay TRONG LÚC review H1 đang chạy.
t = T.Team(_STATE, "t55")
g = t.create()
t.wake(g)
t.rev.hook = lambda e: t.target().write_text(H2, encoding="utf-8", newline="\n") if e.queries == 1 else None
t.run(g, n=8)
check("T55 kết luận ghi cho H1; lúc chốt thấy lệch: waiting/source_drift, không chốt", t.reviews(g)[0]["verdict"] == "pass"
      and t.st(g)["block_reason"] == "source_drift" and t.g(g).status == "active", (t.st(g), t.reviews(g)[0]["verdict"]))

# T58: ảnh chụp có hash khác artifact_sha (bằng chứng bị thay): snapshot_mismatch, không giữ chỗ.
t = T.Team(_STATE, "t58")
g = t.create()
t.wake(g)
for k in list(t.ev.items):
    t.ev.items[k] = {"text": "nội dung khác", "content_hash": "x"}
t.run(g, n=6)
check("T58 snapshot_mismatch: blocked/review_input, không giữ chỗ, không gọi engine; (1, 0, 1)",
      t.st(g) == {"run_state": "blocked", "block_reason": "review_input"} and t.rev.queries == 0
      and t.calls(g) == (1, 0, 1), (t.st(g), t.calls(g)))

# T28: bản quá REVIEW_INPUT_MAX_CHARS: too_large, không giữ chỗ, không tự thử lại.
t = T.Team(_STATE, "t28")
BIG = T.GOOD + ("x" * (R.REVIEW_INPUT_MAX_CHARS + 10)) + "\n"
t.work.script = [BIG]
g = t.create()
t.run(g, n=8)
w0 = t.store.wakes(t.owner, g.id)
check("T28 too_large: blocked/review_input, không giữ chỗ, không gọi engine, không nhịp thức sát nhau",
      t.st(g) == {"run_state": "blocked", "block_reason": "review_input"} and t.rev.queries == 0
      and t.calls(g) == (1, 0, 1) and all(float(w["due_at"]) > t.clock() for w in w0 if w["kind"] == "work"),
      (t.st(g), t.calls(g), w0))

# ═══════════ Quyền, dừng, phạm vi (T17, T20, T21, T23, T24, T26, T27, T29, T60) ═══════════
# T17: thu hồi quyền ghi khi đang chờ review; cấp lại.
t = T.Team(_STATE, "t17")
g = t.create()
t.wake(g)
t.wake(g)                                   # pass, chưa chốt
R.apply_command(t.store, t.owner, g.id, "revoke_grant", {"expected_revision": t.g(g).revision}, t.brain)
t.run(g, n=4)
st17 = {"paused": t.g(g).paused, "status": t.g(g).status}
R.apply_command(t.store, t.owner, g.id, "resume", {}, t.brain)
RA.approve(t.store, t.brain, g.id)
t.run(g, n=8)
check("T17 thu hồi: tạm dừng, không chốt; cấp lại: review cũ còn khớp bộ ghim nên dùng được; không gọi thêm model",
      st17 == {"paused": True, "status": "active"} and t.g(g).status == "succeeded"
      and (t.work.queries, t.rev.queries) == (1, 1), (st17, t.st(g), t.g(g).status))

# T20: tắt agent làm: blocked/agent_off như A1, không review.
t = T.Team(_STATE, "t20")
g = t.create()
RA.disable(t.store, t.brain, T.MAKER)
t.run(g, n=4)
check("T20 tắt agent làm: blocked/agent_off, không gọi model", t.st(g)["block_reason"] == "agent_off"
      and (t.work.queries, t.rev.queries) == (0, 0), t.st(g))

# T21: guard chặn bản đã review pass.
t = T.Team(_STATE, "t21")
gp = t.proposal()
gp["guards"] = [{"description": "File Inbox/khoa.md còn chữ MO", "evaluator": "artifact_contract",
                 "params": {"path": "Inbox/khoa.md", "must_contain": ["MO"]}}]
(Path(t.brain) / "Inbox").mkdir(parents=True, exist_ok=True)
(Path(t.brain) / "Inbox" / "khoa.md").write_text("MO\n", encoding="utf-8")
t.proposal = lambda human=False, path=T.DELIV, _p=gp: _p
g = t.create()
t.wake(g)
t.wake(g)
(Path(t.brain) / "Inbox" / "khoa.md").write_text("DONG\n", encoding="utf-8")
t.run(g, n=6)
check("T21 guard chạm sau review pass: blocked/guard; review không xoá guard; không chốt",
      t.st(g)["block_reason"] == "guard" and t.g(g).status == "active" and t.reviews(g)[0]["verdict"] == "pass",
      (t.st(g), t.g(g).status))

# T23: lỗi lưu bằng chứng của đầu ra review.
t = T.Team(_STATE, "t23")
g = t.create()
t.wake(g)
t.rev.hook = lambda e: setattr(t.ev, "fail", True) if e.queries == 1 else None
t.wake(g)
rv = t.reviews(g)
check("T23 lưu bằng chứng hỏng: unknown/storage_error, lượt tính, hẹn review_retry theo luật AUTO",
      rv[0]["reason_code"] == "storage_error" and rv[0]["charged"] == 1 and t.calls(g) == (1, 1, 2)
      and t.st(g)["block_reason"] == "review_retry", (rv[0], t.st(g)))
t.ev.fail = False
t.run(g, n=8, step=1)
check("T23 sau backoff: thử lại, pass, succeeded; (1, 2, 3)", t.g(g).status == "succeeded" and t.calls(g) == (1, 2, 3))

# T24: tách đội khi đang chờ review.
t = T.Team(_STATE, "t24")
g = t.create()
t.wake(g)
res = R.apply_command(t.store, t.owner, g.id, "team_detach", {}, t.brain)
t.run(g, n=6)
check("T24 tách đội khi chờ review: chốt theo luật A4, không gọi review; lượt đã dùng giữ nguyên",
      res["status"] == "team_detached" and t.g(g).status == "succeeded" and t.rev.queries == 0
      and t.calls(g) == (1, 0, 1) and t.team(g)["status"] == "detached", (res, t.st(g)))
try:
    t.store.team_detach(RS.Principal("agent", t.maker["agent_key"], t.brain), g.id)
    _ag = False
except Exception:  # noqa: BLE001
    _ag = True
check("T24 agent không tự tách đội được (chỉ chủ dự án)", _ag)

# T26: reviewer trả trường đổi tiêu chí hay hạn mức: bỏ qua, ghi sự kiện, kết luận chỉ từ ba trường.
t = T.Team(_STATE, "t26")
t.rev.script = [json.dumps({"verdict": "pass", "criteria": [{"index": 0, "ok": True}], "fixes": "",
                            "budget_calls": 99, "criteria": [{"index": 0, "ok": True}], "role": "maker"})]
g = t.create()
t.run(g)
check("T26 trường lạ không đổi hạn mức hay tiêu chí; ghi sự kiện review_extra_fields; succeeded như T1",
      t.g(g).budget_calls == 8 and t.events(g, "review_extra_fields") and t.g(g).status == "succeeded"
      and t.calls(g) == (1, 1, 2), (t.g(g).budget_calls, t.events(g, "review_extra_fields")))

# T27: bản nộp trong chat (A4) trên mục tiêu có đội: review ở việc nền, tính phần reviewer.
t = T.Team(_STATE, "t27")
g = t.create()
g2, sub, ho = t.chat_update(g, T.GOOD)
t.run(g, n=10)
check("T27 bản chat: đăng theo A4; review ở việc nền, tính phần reviewer; vai làm 0 lượt nền; succeeded",
      ho == "submission_published" and t.g(g).status == "succeeded" and t.calls(g) == (0, 1, 1)
      and t.work.queries == 0 and t.rev.queries == 1, (ho, t.calls(g), t.st(g)))

# T29: chat thường không có mục tiêu: không tạo mục tiêu, không review.
t = T.Team(_STATE, "t29")
check("T29 không có mục tiêu thì không có review hay lượt nào", t.store.list_open(t.owner) == []
      and (t.work.queries, t.rev.queries) == (0, 0))

# T60: đổi tên hay xoá một tag mà hai trợ lý mang: cặp và đội không đổi.
t = T.Team(_STATE, "t60")
for slug in (T.MAKER, T.REVIEWER):
    (Path(t.brain) / "agents" / f"{slug}.md").write_text(f"---\nname: {slug}\ntags:\n- Viết\n---\nTrợ lý thử {slug}\n",
                                                          encoding="utf-8")
g = t.create()
pair0 = t.store.team_pair(t.brain, t.maker["agent_key"])
for slug in (T.MAKER, T.REVIEWER):
    (Path(t.brain) / "agents" / f"{slug}.md").write_text(f"---\nname: {slug}\ntags:\n- Nội dung\n---\nTrợ lý thử {slug}\n",
                                                          encoding="utf-8")
t.run(g)
check("T60 tag đổi: team_pairs, goal_team không đổi (lưu theo agent_key); mục tiêu chạy như thường",
      t.store.team_pair(t.brain, t.maker["agent_key"]) == pair0 and t.team(g)["reviewer_agent_key"]
      == t.reviewer["agent_key"] and t.g(g).status == "succeeded")

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    raise SystemExit(1)
print("\nOK")
