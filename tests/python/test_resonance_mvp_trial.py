"""Resonance M5: một phép thử cải thiện nhỏ (so hai cách làm trên cùng thước đo).

    python tests/run.py resonance_mvp_trial -v

Kho SQLite thật, engine GIẢ (hợp đồng sự kiện của aux_engine), bằng chứng qua cổng giả cùng hợp đồng với
EvidenceStore. Không gọi model thật. Bộ tình huống ở tests/fixtures/resonance/mvp_cases.json. Tên test theo
Task M5 của docs/superpowers/plans/2026-10-06-resonance-00-mvp.md.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m5-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


FIX = json.loads((Path(ROOT) / "tests" / "fixtures" / "resonance" / "mvp_cases.json").read_text(encoding="utf-8"))
CASES = {c["id"]: c for c in FIX["cases"]}
BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-m5-")).resolve())
(Path(BRAIN) / "Javis").mkdir(parents=True)
SWITCH = Path(BRAIN) / "Javis" / "resonance.json"
SWITCH.write_text('{"enabled": true}', encoding="utf-8")
P = RS.Principal("agent", "javis", BRAIN)
OWNER = RS.Principal("owner", "owner", BRAIN)
store = RS.GoalStore()

# Đầu ra mẫu theo tình huống. FULL đạt expect; MISS thiếu một người và một hạn; BRIEF quá ngắn.
FULL = {
    "t1": "# Việc cần làm\n\n- Lan: soạn kế hoạch bài viết tháng 11, hạn thứ Sáu\n- Minh: kiểm lại lịch đăng, hạn 10/10\n"
          "- Hà: gửi bảng số liệu cho cả nhóm, hạn thứ Hai\n",
    "t2": "# Việc cần làm\n\n- Tuấn: liên hệ bên vận chuyển, hạn 12/10\n- Mai: đóng gói hồ sơ giấy, hạn 15/10\n"
          "- Quang: cài lại máy in, hạn 20/10\n",
    "h1": "# Việc cần làm\n\n- Cô Thảo: soạn đề kiểm tra giữa kỳ, hạn 18/10\n- Bình: in tài liệu ôn tập, hạn 14/10\n"
          "- Phương: nhắn lịch thi cho phụ huynh, hạn 16/10\n",
    "h2": "# Việc cần làm\n\n- Chị Ngọc: đặt vé tàu về quê, hạn 01/11\n- Anh Khoa: mua quà cho ông bà, hạn 28/10\n",
}
MISS = {k: "\n".join(v.splitlines()[:-1]) + "\n" for k, v in FULL.items()}
CLAIM = {k: "# Việc cần làm\n\nĐÃ ĐẠT MỌI TIÊU CHÍ. Lan, Minh: xem biên bản.\n" for k in FULL}
MARK = {"t1": "Lan soạn kế hoạch", "t2": "Tuấn liên hệ", "h1": "cô Thảo soạn đề", "h2": "chị Ngọc đặt vé"}


def case_of(prompt):
    hit = [k for k, m in MARK.items() if m in prompt]
    return hit[0] if len(hit) == 1 else None


def method_of(prompt):
    hit = [ref for ref, m in R.METHODS.items() if m["addendum"] and m["addendum"] in prompt]
    return hit[0] if len(hit) == 1 else (R.DEFAULT_METHOD if not hit else None)


class Engine:
    """Trả theo bảng (cách làm, tình huống) -> chữ, hoặc "ERROR" để mô phỏng engine lỗi."""

    def __init__(self, table, on_query=None):
        self.table, self.on_query = table, on_query
        self.prompts, self.max_wall_s = [], None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.prompts.append(prompt)
        if self.on_query:
            self.on_query(prompt)
        out = self.table.get((method_of(prompt), case_of(prompt)), "")
        if out == "ERROR":
            yield {"type": "error", "content": "engine lỗi mô phỏng"}
            return
        yield {"type": "final", "content": out or FULL.get(case_of(prompt) or "t1"), "tokens_in": 100, "tokens_out": 40}


class Evidence:
    def __init__(self):
        self.items = {}

    def put(self, goal, action_id, text, metadata):
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                           "meta": dict(metadata or {})}
        return eid

    def valid(self, eid):
        return self.items.get(eid)


def deps_for(engine):
    return R.GoalDeps(engine_factory=lambda s, t: (engine, {"provider": "fake", "model": "fake-1", "text_only": True}),
                      budget=R.CallBudget(0), store=store, principal=P, brain_root=BRAIN, evidence=Evidence(),
                      clock=lambda: 1_800_000_000.0)


_n = {"mid": 0}


def make_goal(budget=12):
    _n["mid"] += 1
    d0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi"}), budget=R.CallBudget(0), store=store)
    return asyncio.run(R.form_goal(R.message_ref("s5", _n["mid"]), {
        "principal": P, "brain_root": BRAIN, "session_id": "s5", "message_id": _n["mid"],
        "user_text": FIX["goal"]["user_text"], "constraints": [], "budget_calls": budget,
        "proposal": dict(FIX["goal"]["proposal"])}, d0))


def cases(*ids):
    return {"cases": [CASES[i] for i in ids]}


def trial(g, table, base="work.v1", cand="work.checklist.v1", ids=("t1", "t2", "h1"), on_query=None):
    eng = Engine(table, on_query)
    res = asyncio.run(R.compare_methods(g.id, base, cand, cases(*ids), deps_for(eng)))
    return res, eng


def rejected(f):
    try:
        out = f()
        if asyncio.iscoroutine(out):
            asyncio.run(out)
    except R.GoalRejected:
        return True
    return False


class Die(BaseException):
    """Mô phỏng tiến trình chết giữa chừng (không phải Exception nên không bị lớp bắt lỗi nào nuốt)."""


# Bảng chuẩn: cách làm hiện tại sót ý ở t1, ứng viên rà đủ ý đạt mọi tình huống.
WIN = {("work.v1", "t1"): MISS["t1"], ("work.v1", "t2"): FULL["t2"], ("work.v1", "h1"): FULL["h1"],
       ("work.checklist.v1", "t1"): FULL["t1"], ("work.checklist.v1", "t2"): FULL["t2"],
       ("work.checklist.v1", "h1"): FULL["h1"]}

# ═══════════════════════ cấu hình cách làm là khai báo, không phải code ═══════════════════════
check("có cách làm mặc định và hai biến thể khai báo sẵn, mỗi cái chỉ là chữ cố định",
      R.DEFAULT_METHOD == "work.v1" and {"work.v1", "work.checklist.v1", "work.brief.v1"} <= set(R.METHODS)
      and all(set(m) == {"label_vi", "label_en", "addendum"} and all(isinstance(v, str) for v in m.values())
              for m in R.METHODS.values()))
g0 = make_goal()
check("cách làm lạ (không khai báo) bị từ chối, không gọi model",
      rejected(lambda: R.compare_methods(g0.id, "work.v1", "work.tu-viet-code", cases("t1", "h1"),
                                         deps_for(Engine({})))))
check("ứng viên trùng cách làm hiện tại bị từ chối (phải đúng MỘT thay đổi)",
      rejected(lambda: R.compare_methods(g0.id, "work.v1", "work.v1", cases("t1", "h1"), deps_for(Engine({})))))
check("baseline phải là cách làm mục tiêu đang dùng",
      rejected(lambda: R.compare_methods(g0.id, "work.brief.v1", "work.checklist.v1", cases("t1", "h1"),
                                         deps_for(Engine({})))))
check("bộ tình huống thiếu tập giữ riêng bị từ chối",
      rejected(lambda: R.compare_methods(g0.id, "work.v1", "work.checklist.v1", cases("t1", "t2"),
                                         deps_for(Engine({})))))
SWITCH.write_text('{"enabled": false}', encoding="utf-8")
check("Resonance tắt ở brain: không chạy phép thử",
      rejected(lambda: R.compare_methods(g0.id, "work.v1", "work.checklist.v1", cases("t1", "h1"),
                                         deps_for(Engine({})))))
SWITCH.write_text('{"enabled": true}', encoding="utf-8")

# ═══════════════════════ test_same_goal_and_rubric ═══════════════════════
g = make_goal()
before = store.get(P, g.id)
res, eng = trial(g, WIN)
check("test_same_goal_and_rubric: hai cách làm chạy trên CÙNG revision và cùng thước đo đã ghim",
      res["created"] and res["revision"] == before.revision and len(res["rubric_hash"]) == 64
      and all(r["baseline"].get("rubric_hash") == r["candidate"].get("rubric_hash") == res["rubric_hash"]
              for r in res["results"] if r["baseline"].get("verdict") != "skipped"))
by = {}
for pr in eng.prompts:
    by.setdefault(case_of(pr), {})[method_of(pr)] = pr
add = R.METHODS["work.checklist.v1"]["addendum"]
check("test_same_goal_and_rubric: prompt hai bên giống hệt nhau, chỉ khác đúng đoạn chữ của cách làm",
      all(set(v) == {"work.v1", "work.checklist.v1"}
          and v["work.checklist.v1"].replace("\n\n" + add, "") == v["work.v1"] for v in by.values()))
after = store.get(P, g.id)
check("test_same_goal_and_rubric: phép thử không đổi cách hiểu, tiêu chí hay revision của mục tiêu",
      after.revision == before.revision and after.criteria == before.criteria
      and after.understanding == before.understanding)
check("ứng viên hơn ở tập thử, không kém ở tập giữ riêng: eligible và được áp dụng cho mục tiêu này",
      res["verdict"] == "eligible" and res["applied"] is True
      and R.effective_method(store.get(P, g.id)) == "work.checklist.v1")
check("phạm vi áp dụng ghi rõ: đúng mục tiêu, đúng revision đã kiểm",
      res["scope"] == {"goal_id": g.id, "revision": before.revision, "applies_to": "this_goal"})
check("host tự chấm: kết quả từng tình huống có verdict và bằng chứng, không lấy lời tự khai của đầu ra",
      all(r[arm]["verdict"] in ("met", "not_met") and r[arm]["evidence_id"] in res["evidence_refs"]
          for r in res["results"] for arm in ("baseline", "candidate")))
g_claim = make_goal()
res_c, _ = trial(g_claim, {**WIN, ("work.checklist.v1", "t1"): CLAIM["t1"]})
check("đầu ra tự khai 'ĐÃ ĐẠT MỌI TIÊU CHÍ' mà thiếu ý vẫn bị host chấm not_met",
      [r for r in res_c["results"] if r["case_id"] == "t1"][0]["candidate"]["verdict"] == "not_met"
      and res_c["verdict"] != "eligible" and R.effective_method(store.get(P, g_claim.id)) == "work.v1")

# Mục tiêu đổi cách hiểu giữa phép thử: kết quả cũ giữ phạm vi, không áp dụng.
g_rf = make_goal()
_done = {"n": 0}


def _reframe(prompt):
    _done["n"] += 1
    if _done["n"] == 2:
        R.revise_goal(store, P, g_rf.id, 1, {"relevant_quote": "lập giúp mình danh sách việc cần làm",
                                             "understanding": "Danh sách việc, xếp theo hạn gần nhất"},
                      {"message_ref": R.message_ref("s5", 9001), "session_id": "s5", "message_id": 9001,
                       "user_text": FIX["goal"]["user_text"]})


res_rf, eng_rf = trial(g_rf, WIN, on_query=_reframe)
check("đổi cách hiểu giữa chừng có hiệu lực ngay: dừng sau lượt đang chạy, trả lại lượt chưa chạy",
      len(eng_rf.prompts) == 2 and store.get(P, g_rf.id).calls_used == 2)
check("mục tiêu đổi revision giữa phép thử: inconclusive, lý do goal_reframed, không áp dụng",
      res_rf["verdict"] == "inconclusive" and res_rf["reason"] == "goal_reframed" and res_rf["applied"] is False
      and R.effective_method(store.get(P, g_rf.id)) == "work.v1")

# ═══════════════════════ test_holdout_not_visible ═══════════════════════
g_h = make_goal()
res_h, eng_h = trial(g_h, WIN)
leaks = []
for c in (CASES["t1"], CASES["t2"], CASES["h1"]):
    need = c["expect"].get("must_contain") or []
    for pr in eng_h.prompts:
        if ", ".join(need) in pr or json.dumps(need, ensure_ascii=False) in pr or "expect" in pr.lower():
            leaks.append(c["id"])
check("test_holdout_not_visible: không prompt nào chứa danh sách đáp án (expect) của tình huống", not leaks)
check("test_holdout_not_visible: mỗi lượt chỉ thấy đúng một tình huống, không thấy tình huống giữ riêng khác",
      all(sum(1 for m in MARK.values() if m in pr) == 1 for pr in eng_h.prompts))
check("test_holdout_not_visible: không lượt nào thấy đầu ra của lượt trước (bản dựng mới mỗi lượt)",
      not any(FULL["t1"].splitlines()[2] in pr or MISS["t2"].splitlines()[2] in pr for pr in eng_h.prompts))
check("tập giữ riêng được chạy và chấm nhưng tách khỏi tập thử trong kết quả",
      {r["case_id"]: r["split"] for r in res_h["results"]} == {"t1": "tuning", "t2": "tuning", "h1": "holdout"})

# ═══════════════════════ test_unknown_not_win ═══════════════════════
g_u = make_goal()
res_u, eng_u = trial(g_u, {**WIN, ("work.checklist.v1", "h1"): "ERROR"})
check("test_unknown_not_win: ứng viên thắng tập thử nhưng lỗi ở tập giữ riêng: inconclusive, không áp dụng",
      res_u["verdict"] == "inconclusive" and res_u["reason"] == "unknown" and res_u["applied"] is False
      and R.effective_method(store.get(P, g_u.id)) == "work.v1")
check("test_unknown_not_win: lượt lỗi ghi unknown (không phải not_met) kèm mã lỗi",
      [r for r in res_u["results"] if r["case_id"] == "h1"][0]["candidate"]["verdict"] == "unknown")
g_u2 = make_goal()
res_u2, eng_u2 = trial(g_u2, WIN, ids=("t1", "t2", "h1", "h2"))
h2 = [r for r in res_u2["results"] if r["case_id"] == "h2"][0]
check("tình huống chỉ người dùng chấm được: không chạy (không tốn lượt), ghi unknown, kết luận inconclusive",
      h2["baseline"]["verdict"] == h2["candidate"]["verdict"] == "unknown" and h2["baseline"].get("skipped") is True
      and not any(MARK["h2"] in pr for pr in eng_u2.prompts)
      and res_u2["verdict"] == "inconclusive" and res_u2["applied"] is False)

# ═══════════════════════ test_failed_candidate_not_applied ═══════════════════════
g_f = make_goal()
LOSE = {**WIN, ("work.v1", "t1"): FULL["t1"], ("work.brief.v1", "t1"): "Lan, Minh lo.\n",
        ("work.brief.v1", "t2"): FULL["t2"], ("work.brief.v1", "h1"): FULL["h1"]}
res_f, _ = trial(g_f, LOSE, cand="work.brief.v1")
check("test_failed_candidate_not_applied: ứng viên tụt ở một tình huống: rejected, lý do regression",
      res_f["verdict"] == "rejected" and res_f["reason"] == "regression" and res_f["applied"] is False)
check("test_failed_candidate_not_applied: cách làm của mục tiêu giữ nguyên", R.effective_method(store.get(P, g_f.id)) == "work.v1")
exps = store.experiments(P, g_f.id)
check("test_failed_candidate_not_applied: phép thử thua vẫn được lưu đủ kết quả, usage và bằng chứng",
      len(exps) == 1 and exps[0]["verdict"] == "rejected" and exps[0]["status"] == "finished"
      and exps[0]["payload"]["results"] and exps[0]["payload"]["usage"]["candidate"]["calls"] == 3
      and exps[0]["payload"]["evidence_refs"])
check("ngang nhau (không hơn ở tập thử): rejected, lý do no_improvement",
      trial(make_goal(), {**WIN, ("work.v1", "t1"): FULL["t1"]})[0]["reason"] == "no_improvement")


def _lam_mot_luot(goal_id):
    # Các mục tiêu trong test dùng chung một file sản phẩm: xoá bản của mục tiêu trước để lượt này thật sự làm việc.
    (Path(BRAIN) / "Inbox" / "viec-tu-bien-ban.md").unlink(missing_ok=True)
    eng = Engine({})
    d = deps_for(eng)
    asyncio.run(R.advance(goal_id, {"kind": "start"}, d))
    return eng.prompts[-1] if eng.prompts else ""


pr_f = _lam_mot_luot(g_f.id)
check("test_failed_candidate_not_applied: lượt làm việc sau đó vẫn dùng cách làm cũ (không có chữ của ứng viên)",
      pr_f and R.METHODS["work.brief.v1"]["addendum"] not in pr_f)

# ═══════════════════════ test_one_change_within_budget ═══════════════════════
g_b = make_goal(budget=12)
used0 = store.get(P, g_b.id).calls_used
res_b, eng_b = trial(g_b, WIN)
check("test_one_change_within_budget: đúng 2 lượt mỗi tình huống chạy được, tính vào hạn mức của mục tiêu",
      len(eng_b.prompts) == 6 and store.get(P, g_b.id).calls_used == used0 + 6)
check("test_one_change_within_budget: usage ghi theo từng bên, cùng số lượt (cùng nguồn lực)",
      res_b["usage"]["baseline"]["calls"] == res_b["usage"]["candidate"]["calls"] == 3
      and res_b["usage"]["baseline"]["tokens_in"] == 300)
g_nb = make_goal(budget=8)
res_nb, eng_nb = trial(g_nb, WIN)
check("test_one_change_within_budget: phần khám phá (nửa hạn mức) không đủ: KHÔNG tạo phép thử, không gọi model",
      res_nb["created"] is False and res_nb["reason"] == "explore_budget" and not eng_nb.prompts
      and store.experiments(P, g_nb.id) == [] and store.get(P, g_nb.id).calls_used == 0)
g_nb2 = make_goal(budget=12)
res_used, _ = trial(g_nb2, {**WIN, ("work.v1", "t1"): FULL["t1"]}, ids=("t1", "h1"))
res_more, eng_more = trial(g_nb2, WIN, ids=("t1", "t2", "h1"))
check("test_one_change_within_budget: các phép thử cộng dồn vào cùng phần khám phá, hết phần thì dừng",
      res_used["created"] and res_more["created"] is False and res_more["reason"] == "explore_budget"
      and not eng_more.prompts)
g_t = make_goal()
n_tick = asyncio.run(R.tick(store, 1_800_000_000.0 + 10, lambda b: deps_for(Engine({})) if b == BRAIN else None,
                            limit=50))
check("không tự tạo phép thử chỉ vì đến giờ: nhịp lập lịch chạy lượt làm việc nhưng không tạo phép thử nào",
      n_tick >= 1 and store.experiments(P, g_t.id) == []
      and not any(a["kind"] == "trial" for a in store.actions(P, g_t.id)))
check("phép thử đang giữ khoá mục tiêu: lượt khác của cùng mục tiêu không chạy chồng",
      (lambda gg: (store.claim_lease(P, gg.id, "nguoi-khac", 1_800_000_000.0 + 10_000, 1_800_000_000.0),
                   trial(gg, WIN)[0])[1])(make_goal())["reason"] == "busy")
check("engine bị chặn trước khi gọi: trả lại đúng lượt đã giữ",
      (lambda gg: (asyncio.run(R.compare_methods(
          gg.id, "work.v1", "work.checklist.v1", cases("t1", "h1"),
          R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "chặn"}), budget=R.CallBudget(0), store=store,
                     principal=P, brain_root=BRAIN, evidence=Evidence()))), store.get(P, gg.id).calls_used)[1] == 0)(
          make_goal()))

# ═══════════════════════ áp dụng, phạm vi, quay lại ═══════════════════════
g_w = make_goal()
trial(g_w, WIN)
pr_w = _lam_mot_luot(g_w.id)
check("cách làm đã thắng được dùng cho lượt làm việc tiếp theo của đúng revision đó", add in pr_w
      and [a["intent"].get("method") for a in store.actions(P, g_w.id) if a["kind"] == "work"] == ["work.checklist.v1"])
g = make_goal()
trial(g, WIN)
R.revise_goal(store, P, g.id, store.get(P, g.id).revision,
              {"relevant_quote": "lập giúp mình danh sách việc cần làm", "understanding": "Danh sách việc kèm ghi chú"},
              {"message_ref": R.message_ref("s5", 9100), "session_id": "s5", "message_id": 9100,
               "user_text": FIX["goal"]["user_text"]})
check("mục tiêu sang revision mới: cách làm đã kiểm cho revision cũ không tự áp dụng, quay về cách cũ",
      R.effective_method(store.get(P, g.id)) == "work.v1")
check("muốn dùng tiếp phải so lại trên revision mới: lấy cách đã thắng làm baseline bị từ chối",
      rejected(lambda: R.compare_methods(g.id, "work.checklist.v1", "work.brief.v1", cases("t1", "h1"),
                                         deps_for(Engine({})))))
g_r = make_goal()
trial(g_r, WIN)
check("agent không tự đổi cách làm khi không có phép thử eligible",
      rejected(lambda: store.apply_method(P, g_r.id, 1, "work.checklist.v1", "work.brief.v1", "exp_khong_co")))
r_cmd = R.apply_command(store, OWNER, g_r.id, "revert_method", {"expected_revision": 1}, BRAIN)
check("người dùng quay lại cách làm cũ được (giữ ref cũ)",
      r_cmd.get("ok") is True and R.effective_method(store.get(P, g_r.id)) == "work.v1")
try:
    store.revert_method(P, g_r.id)
    _agent_revert = False
except PermissionError:
    _agent_revert = True
check("revert_method chỉ cho owner (PermissionError với agent)", _agent_revert)
v = R.goal_view(store, OWNER, g_r.id, BRAIN)
check("thẻ mục tiêu cho biết cách làm đang dùng và phép thử gần nhất",
      v["method"]["ref"] == "work.v1" and v["experiments"] and v["experiments"][0]["verdict"] == "eligible")

# ═══════════════════════ gián đoạn giữa phép thử ═══════════════════════
g_c = make_goal()
_kill = {"n": 0}


def _die(prompt):
    _kill["n"] += 1
    if _kill["n"] == 3:
        raise Die()


try:
    trial(g_c, WIN, on_query=_die)
except Die:
    pass
ex = store.experiments(P, g_c.id)
check("tiến trình chết giữa phép thử: phép thử còn 'running', lượt dở còn khoá",
      len(ex) == 1 and ex[0]["status"] == "running")
asyncio.run(R.advance(g_c.id, {"kind": "wake"}, R.GoalDeps(
    engine_factory=lambda s, t: (Engine({}), {"provider": "fake", "text_only": True}), budget=R.CallBudget(0),
    store=store, principal=P, brain_root=BRAIN, evidence=Evidence(), clock=lambda: 1_800_000_000.0 + 99_999)))
ex = store.experiments(P, g_c.id)
check("đối soát sau gián đoạn: lượt dở chốt failed, phép thử inconclusive lý do interrupted, không áp dụng",
      ex[0]["status"] == "finished" and ex[0]["verdict"] == "inconclusive" and ex[0]["reason"] == "interrupted"
      and not any(a["kind"] == "trial" and a["status"] == "running" for a in store.actions(P, g_c.id))
      and R.effective_method(store.get(P, g_c.id)) == "work.v1")
check("không chạy lại mù sau gián đoạn: đối soát không gọi lại lượt thử nào",
      sum(1 for a in store.actions(P, g_c.id) if a["kind"] == "trial") == _kill["n"])

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
