"""Resonance M3: thực thi, bằng chứng và lịch nhỏ.

    python tests/run.py resonance_mvp_run -v

Đi qua kho SQLite thật và engine GIẢ (hợp đồng sự kiện của aux_engine), bằng chứng qua một cổng giả có cùng
hợp đồng với cổng main.py dựng trên EvidenceStore. Không gọi model thật. Tên test theo Task M3 của
docs/superpowers/plans/2026-10-06-resonance-00-mvp.md.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-resonance-m3-")
os.environ["JAVIS_STATE_DIR"] = _STATE

import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = str(Path(tempfile.mkdtemp(prefix="brain-m3-")).resolve())
(Path(BRAIN) / "Javis").mkdir(parents=True)
SWITCH = Path(BRAIN) / "Javis" / "resonance.json"


def switch(on: bool):
    SWITCH.write_text('{"enabled": %s}' % ("true" if on else "false"), encoding="utf-8")


switch(True)
P = RS.Principal("agent", "javis", BRAIN)
OWNER = RS.Principal("owner", "owner", BRAIN)
store = RS.GoalStore()

USER = ("Từ danh sách việc sau, viết giúp anh một ghi chú tổng hợp trong Inbox: gọi thợ sửa máy lạnh, "
        "nộp báo cáo quý, mua quà sinh nhật mẹ. Việc nào gấp thì đưa lên đầu.")
GOOD = ("# Việc đang dở\n\n1. Nộp báo cáo quý (gấp)\n2. Gọi thợ sửa máy lạnh\n3. Mua quà sinh nhật mẹ\n"
        "\nGhi chú tổng hợp từ danh sách anh đưa — xếp việc gấp lên đầu.\n")


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeEngine:
    def __init__(self, text=GOOD, events=None, on_query=None):
        self.text, self.events, self.on_query = text, events, on_query
        self.queries = 0
        self.max_wall_s = None

    def is_available(self):
        return True

    async def query(self, prompt):
        self.queries += 1
        self.last_prompt = prompt
        if self.on_query:
            self.on_query()
        for ev in (self.events or [{"type": "final", "content": self.text, "tokens_in": 10, "tokens_out": 20}]):
            yield ev


class FakeEvidence:
    """Cùng hợp đồng với cổng EvidenceStore trong main.py: put trả id, valid trả nội dung hoặc None."""

    def __init__(self):
        self.items, self.broken, self.fail_put = {}, set(), False

    def put(self, goal, action_id, text, metadata):
        if self.fail_put:
            raise RuntimeError("evidence_encryption_unavailable")
        eid = f"ev_{len(self.items) + 1}"
        self.items[eid] = {"text": text, "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                           "goal": goal.id, "action": action_id, "meta": dict(metadata or {})}
        return eid

    def valid(self, evidence_id):
        if evidence_id in self.broken:
            return None
        return self.items.get(evidence_id)


class Notes:
    def __init__(self):
        self.sent = []

    async def __call__(self, goal, kind, text):
        self.sent.append((goal.id, kind, text))
        return True


def proposal(**kw):
    p = {"understanding": "Ghi chú tổng hợp việc đang dở trong Inbox, việc gấp lên đầu",
         "criteria": [{"description": "Ghi chú tổng hợp có trong Inbox và có đủ ba việc", "evaluator": "artifact_contract",
                       "params": {"path": "Inbox/viec-dang-do.md", "min_chars": 40,
                                  "must_contain": ["báo cáo quý", "máy lạnh", "sinh nhật"]}}],
         "relevant_quote": "viết giúp anh một ghi chú tổng hợp trong Inbox",
         "horizon": {"kind": "review", "at_iso": "2027-01-20T09:00:00+07:00"},
         "stage": "delivery", "mode": "achieve"}
    p.update(kw)
    return p


_n = {"mid": 0}


def make_goal(budget=4, **kw):
    _n["mid"] += 1
    mid = _n["mid"]
    deps0 = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "không gọi"}), budget=R.CallBudget(0),
                       store=store)
    return asyncio.run(R.form_goal(R.message_ref("s3", mid), {
        "principal": P, "brain_root": BRAIN, "session_id": "s3", "message_id": mid, "user_text": USER,
        "constraints": [], "budget_calls": budget, "proposal": proposal(**kw)}, deps0))


def make_deps(engine=None, clock=None, factory=None, evidence=None, notes=None):
    built = {"n": 0}
    eng = engine or FakeEngine()

    def _factory(system_prompt, tag):
        built["n"] += 1
        return eng, {"provider": "fake", "model": "fake-1", "text_only": True}
    deps = R.GoalDeps(engine_factory=factory or _factory, budget=R.CallBudget(0), clock=clock or Clock(),
                      store=store, principal=P, brain_root=BRAIN, evidence=evidence or FakeEvidence(),
                      notify=notes or Notes())
    return deps, built, eng


def adv(gid, event, deps):
    return asyncio.run(R.advance(gid, event, deps))


def target(g):
    return Path(BRAIN) / "Inbox" / "viec-dang-do.md"


# ═══════════════════════ test_done_is_not_success ═══════════════════════
g = make_goal(criteria=proposal()["criteria"] + [
    {"description": "Anh xác nhận ghi chú dùng được", "evaluator": "human_confirmation"}])
check("tạo mục tiêu thì có lịch làm việc ngay (work wake)", any(w["kind"] == "work" for w in store.wakes(P, g.id)))
deps, built, eng = make_deps()
a = adv(g.id, {"kind": "start"}, deps)
check("done_is_not_success: một lượt engine, receipt thành công", eng.queries == 1
      and any(x["status"] == "succeeded" for x in store.actions(P, g.id)))
check("done_is_not_success: sản phẩm được đặt đúng chỗ tiêu chí khai", target(g).is_file())
check("done_is_not_success: tiêu chí artifact met, tiêu chí người dùng unknown, tổng thể unknown",
      [c["verdict"] for c in a.criterion_results] == ["met", "unknown"] and a.verdict == "unknown")
g_now = store.get(P, g.id)
check("done_is_not_success: lượt chạy xong KHÔNG làm mục tiêu thành công", g_now.status == "active")
check("done_is_not_success: chờ người dùng xác nhận, không hẹn gọi model nữa",
      store.run_state(P, g.id)["run_state"] == "waiting" and not any(w["kind"] == "work" for w in store.wakes(P, g.id)))
check("bằng chứng: đầu ra đi vào kho bằng chứng và gắn với revision",
      len(store.evidence_for(P, g.id, g.revision)) >= 1 and all(e in deps.evidence.items for e in a.evidence_ids))
check("em dash không lọt vào file trong brain", "—" not in target(g).read_text(encoding="utf-8")
      and all("—" not in p.read_text(encoding="utf-8") for p in Path(g.output_root).glob("*.md")))
a2 = adv(g.id, {"kind": "wake"}, deps)
check("đang chờ người dùng: đánh thức lại cũng không gọi model", eng.queries == 1 and a2.verdict == "unknown")

# Chỉ artifact_contract, đầu ra đạt: thành công, báo một lần.
g1 = make_goal()
target(g1).unlink(missing_ok=True)
deps1, _, eng1 = make_deps(notes=Notes())
a1 = adv(g1.id, {"kind": "start"}, deps1)
check("đủ bằng chứng theo mọi tiêu chí: mục tiêu achieve thành công",
      a1.verdict == "met" and store.get(P, g1.id).status == "succeeded")
n_sent = asyncio.run(R.drain_outbox(store, deps1.notify))
n_again = asyncio.run(R.drain_outbox(store, deps1.notify))
check("báo hoàn thành qua outbox đúng một lần", any(k == "goal.succeeded" for (_, k, _) in deps1.notify.sent)
      and n_again == 0 and n_sent >= 1)
# Đầu ra thiếu ý: not_met, giữ active, hẹn làm lại có giới hạn.
g_short = make_goal(criteria=[{"description": "Ghi chú có ba việc", "evaluator": "artifact_contract",
                               "params": {"path": "Inbox/ngan.md", "must_contain": ["máy lạnh", "báo cáo quý"]}}])
deps_s, _, eng_s = make_deps(engine=FakeEngine(text="# Việc\n\nGọi thợ sửa máy lạnh.\n"))
a_s = adv(g_short.id, {"kind": "start"}, deps_s)
check("đầu ra thiếu ý: not_met, mục tiêu vẫn active, có lịch làm lại trong tương lai",
      a_s.verdict == "not_met" and store.get(P, g_short.id).status == "active"
      and any(w["kind"] == "work" and w["due_at"] > deps_s.clock() for w in store.wakes(P, g_short.id)))

# ═══════════════════════ test_missing_evidence_unknown ═══════════════════════
g_m = make_goal(criteria=[{"description": "Có bản tổng hợp", "evaluator": "artifact_contract",
                           "params": {"min_chars": 10}}])
deps_m, _, _ = make_deps()
a_m = R.evaluate_artifact(store.get(P, g_m.id), (), deps_m)
check("missing_evidence_unknown: chưa có bằng chứng nào thì unknown, không phải not_met", a_m.verdict == "unknown")
eid = deps_m.evidence.put(g_m, "act_x0001", "Bản tổng hợp đủ dài", {})
deps_m.evidence.broken.add(eid)
check("missing_evidence_unknown: bằng chứng không đọc lại được (hết hạn, sai hash) thì unknown",
      R.evaluate_artifact(store.get(P, g_m.id), (eid,), deps_m).verdict == "unknown")
g_p = make_goal(criteria=[{"description": "File có mặt", "evaluator": "artifact_contract",
                           "params": {"path": "Inbox/khong-co.md"}}])
check("tài nguyên khai rõ đường dẫn mà không tồn tại: not_met (khách quan)",
      R.evaluate_artifact(store.get(P, g_p.id), (), deps_m).verdict == "not_met")
g_out = make_goal(criteria=[{"description": "File ngoài brain", "evaluator": "artifact_contract",
                             "params": {"path": "../ngoai-brain.md"}}])
check("đường dẫn ra ngoài brain: unknown (lỗi evaluator), không đọc",
      R.evaluate_artifact(store.get(P, g_out.id), (), deps_m).verdict == "unknown")
deps_fail, _, eng_fail = make_deps()
deps_fail.evidence.fail_put = True
g_ev = make_goal(criteria=[{"description": "Có bản tổng hợp", "evaluator": "artifact_contract",
                            "params": {"min_chars": 10}}])
a_ev = adv(g_ev.id, {"kind": "start"}, deps_fail)
check("không lưu được bằng chứng: không xác nhận thành công", a_ev.verdict == "unknown"
      and store.get(P, g_ev.id).status == "active")

# ═══════════════════════ test_restart_does_not_repeat_effect ═══════════════════════
g_r = make_goal()
target(g_r).unlink(missing_ok=True)
clock_r = Clock()
act = store.begin_action(P, g_r.id, g_r.revision, "work", lease_until=clock_r() - 5, now=clock_r() - 600)
Path(g_r.output_root).mkdir(parents=True, exist_ok=True)
(Path(g_r.output_root) / f"{act['id']}.md").write_text(GOOD.replace("—", "-"), encoding="utf-8", newline="\n")
deps_r, built_r, eng_r = make_deps(clock=clock_r)
a_r = adv(g_r.id, {"kind": "wake"}, deps_r)
rec = store.get_action(P, act["id"])
check("restart: lượt dở có đầu ra trên đĩa được đối soát thành succeeded, KHÔNG gọi model lại",
      eng_r.queries == 0 and rec["status"] == "succeeded" and rec["receipt"].get("reconciled") is True)
check("restart: hạn mức của lượt dở không bị tính hai lần", store.get(P, g_r.id).calls_used == 1)
check("restart: đánh giá dùng đầu ra đã đối soát", a_r.verdict == "met")
g_r2 = make_goal()
target(g_r2).unlink(missing_ok=True)
act2 = store.begin_action(P, g_r2.id, g_r2.revision, "work", lease_until=clock_r() - 5, now=clock_r() - 600)
deps_r2, _, eng_r2 = make_deps(clock=clock_r)
adv(g_r2.id, {"kind": "wake"}, deps_r2)
rec2 = store.get_action(P, act2["id"])
check("restart: lượt dở không có đầu ra thì ghi interrupted (không đoán là xong), lượt mới dùng id MỚI",
      rec2["status"] == "failed" and rec2["receipt"].get("error_code") == "interrupted"
      and eng_r2.queries == 1 and len(store.actions(P, g_r2.id)) >= 2)
check("restart: cùng một action_id không bao giờ ghi hai lần",
      len({x["id"] for x in store.actions(P, g_r2.id)}) == len(store.actions(P, g_r2.id)))
# Đăng sản phẩm: chạy lại không ghi đè file người dùng đã sửa.
g_pub = make_goal()
target(g_pub).unlink(missing_ok=True)
deps_pub, _, _ = make_deps()
adv(g_pub.id, {"kind": "start"}, deps_pub)
target(g_pub).write_text("# Bản anh tự sửa\n", encoding="utf-8")
g_pub2 = make_goal()
deps_pub2, _, _ = make_deps()
adv(g_pub2.id, {"kind": "start"}, deps_pub2)
check("không ghi đè file người dùng đã sửa (xung đột thì giữ nguyên, ghi sự kiện)",
      target(g_pub).read_text(encoding="utf-8") == "# Bản anh tự sửa\n"
      and any(e["kind"] == "publish_conflict" for e in store.events(P, g_pub2.id)))
target(g_pub).unlink(missing_ok=True)

# Sản phẩm không được tạo file ở chỗ Javis tự chạy hay tự nạp (loop, agent, skill, plugin, bộ nhớ, CLAUDE.md...).
for bad in ("Javis/loops/tu-chay.md", "agents/moi.md", "Skills/x/SKILL.md", "memory/facts/gia.md",
            ".claude/commands/x.md", "Notes/CLAUDE.md", "plugins/p/README.md", "workflows/w.md", "Inbox/x.py"):
    g_bad = make_goal(criteria=[{"description": "Có file", "evaluator": "artifact_contract", "params": {"path": bad}}])
    deps_bad, _, _ = make_deps()
    adv(g_bad.id, {"kind": "start"}, deps_bad)
    check(f"không đăng sản phẩm vào {bad}: file không được tạo, ghi sự kiện từ chối",
          not (Path(BRAIN) / bad).exists() and any(e["kind"] == "publish_rejected" for e in store.events(P, g_bad.id)))

# ═══════════════════════ test_old_revision_cannot_finish ═══════════════════════
g_o = make_goal()
target(g_o).unlink(missing_ok=True)


def _revise_mid_run():
    R.revise_goal(store, P, g_o.id, 1, {"relevant_quote": "Việc nào gấp thì đưa lên đầu",
                                         "understanding": "Ghi chú tổng hợp, việc gấp lên đầu, có ngày hẹn"},
                  {"message_ref": R.message_ref("s3", 900), "session_id": "s3", "message_id": 900, "user_text": USER})


deps_o, _, eng_o = make_deps(engine=FakeEngine(on_query=_revise_mid_run))
a_o = adv(g_o.id, {"kind": "start"}, deps_o)
check("old_revision: revision đổi giữa lượt thì kết quả của revision cũ KHÔNG kết thúc mục tiêu",
      store.get(P, g_o.id).status == "active" and store.get(P, g_o.id).revision == 2 and a_o.revision == 1)
check("old_revision: có lịch làm việc cho revision mới", any(w["kind"] == "work" for w in store.wakes(P, g_o.id)))
check("old_revision: finish với expected_revision cũ bị từ chối",
      store.finish(P, g_o.id, 1, "succeeded") is False and store.get(P, g_o.id).status == "active")

# ═══════════════════════ test_pause_and_revoke ═══════════════════════
g_pz = make_goal()
store.set_paused(OWNER, g_pz.id, True)
deps_pz, built_pz, eng_pz = make_deps()
adv(g_pz.id, {"kind": "start"}, deps_pz)
check("pause: mục tiêu người dùng tạm dừng thì không dựng engine, không gọi model",
      built_pz["n"] == 0 and store.run_state(P, g_pz.id)["run_state"] == "paused")
store.set_paused(OWNER, g_pz.id, False)
switch(False)
adv(g_pz.id, {"kind": "wake"}, deps_pz)
check("thu hồi (tắt Resonance ở brain): không gọi model, ghi rõ lý do",
      built_pz["n"] == 0 and store.run_state(P, g_pz.id)["block_reason"] == "feature_off")
switch(True)
g_rv = make_goal()
target(g_rv).unlink(missing_ok=True)
deps_rv, _, eng_rv = make_deps(engine=FakeEngine(on_query=lambda: switch(False)))
adv(g_rv.id, {"kind": "start"}, deps_rv)
check("thu hồi giữa lượt: kiểm lại NGAY TRƯỚC tác động, không đăng sản phẩm vào brain",
      not target(g_rv).exists() and store.run_state(P, g_rv.id)["block_reason"] == "feature_off")
switch(True)

# ═══════════════════════ test_audit_failure_before_effect ═══════════════════════
g_au = make_goal()
deps_au, built_au, _ = make_deps()
_orig = store.begin_action
store.begin_action = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sổ hành động hỏng"))
try:
    a_au = adv(g_au.id, {"kind": "start"}, deps_au)
finally:
    store.begin_action = _orig
check("audit_failure_before_effect: không ghi được ý định hành động thì không dựng engine, không gọi model",
      built_au["n"] == 0 and a_au.verdict == "unknown" and store.get(P, g_au.id).calls_used == 0)

# ═══════════════════════ test_budget_reserved_before_call ═══════════════════════
g_b = make_goal(budget=1)
target(g_b).unlink(missing_ok=True)
seen_used = {}
deps_b, built_b, eng_b = make_deps(engine=FakeEngine(
    text="# Việc\n\nGọi thợ máy lạnh.\n", on_query=lambda: seen_used.setdefault("n", store.get(P, g_b.id).calls_used)))
adv(g_b.id, {"kind": "start"}, deps_b)
check("budget_reserved_before_call: lượt gọi đã được trừ vào kho TRƯỚC khi engine chạy", seen_used.get("n") == 1)
adv(g_b.id, {"kind": "wake"}, deps_b)
check("hết hạn mức: không gọi thêm, mục tiêu blocked vì ngân sách",
      eng_b.queries == 1 and store.run_state(P, g_b.id)["block_reason"] == "budget")
rec_b = [x for x in store.actions(P, g_b.id) if x["status"] == "succeeded"][0]
check("usage có thật được ghi; trường không đo được thì vắng, không ghi 0",
      rec_b["receipt"]["usage"] == {"tokens_in": 10, "tokens_out": 20})

# ═══════════════════════ test_limit_keeps_checkpoint ═══════════════════════
g_l = make_goal(budget=4)
target(g_l).unlink(missing_ok=True)
clock_l = Clock()
deps_l, _, eng_l = make_deps(clock=clock_l, engine=FakeEngine(events=[
    {"type": "final", "content": "You've hit your limit · resets 9pm", "is_error": True, "subtype": "error"}]))
adv(g_l.id, {"kind": "start"}, deps_l)
st_l = store.run_state(P, g_l.id)
check("limit: hết lượt gói thì blocked có mã lý do, không retry ngay",
      st_l["run_state"] == "blocked" and st_l["block_reason"] == "engine_result_error"
      and not any(w["goal_id"] == g_l.id for w in store.due_wakeups(clock_l())) and eng_l.queries == 1)
check("limit: lượt đã gọi model vẫn tính vào hạn mức (không giả là miễn phí)", store.get(P, g_l.id).calls_used == 1)
check("limit: có lịch thử lại trong tương lai, có giới hạn",
      any(w["kind"] == "work" and clock_l() + 600 <= w["due_at"] <= clock_l() + 2 * 86400 for w in store.wakes(P, g_l.id)))
check("limit: checkpoint giữ nguyên (ý định, receipt lỗi còn trong sổ)",
      any(x["status"] == "failed" and x["receipt"].get("error_code") == "engine_result_error"
          for x in store.actions(P, g_l.id)))

# ═══════════════════════ test_no_paid_provider_fallback ═══════════════════════
g_np = make_goal()
used_before = store.get(P, g_np.id).calls_used
calls = {"n": 0}


def blocked_factory(system_prompt, tag):
    calls["n"] += 1
    return None, {"blocked": "engine đã chọn không chạy được chỉ chữ; không tự đổi provider", "text_only": False}


deps_np, _, _ = make_deps(factory=blocked_factory)
adv(g_np.id, {"kind": "start"}, deps_np)
check("no_paid_provider_fallback: engine đã chọn bị chặn thì không có lượt gọi nào, hạn mức trả lại",
      calls["n"] == 1 and store.get(P, g_np.id).calls_used == used_before)
check("no_paid_provider_fallback: blocked engine_blocked, báo người dùng lý do",
      store.run_state(P, g_np.id)["block_reason"] == "engine_blocked")

# ═══════════════════════ test_idle_does_not_call_model ═══════════════════════
clock_i = Clock(4_000_000_000.0)
for w in store.due_wakeups(clock_i()):
    store.clear_wake(RS.Principal("agent", "javis", w["brain_id"]), w["goal_id"], w["kind"])
deps_i, built_i, eng_i = make_deps(clock=clock_i)
n_i = asyncio.run(R.tick(store, clock_i(), lambda b: deps_i))
check("idle_does_not_call_model: không có lịch tới hạn thì tick không dựng engine nào", n_i == 0 and built_i["n"] == 0)

# ═══════════════════════ test_guard_wakes_without_worker ═══════════════════════
keep = Path(BRAIN) / "Notes" / "ghi-chu-cu.md"
keep.parent.mkdir(parents=True, exist_ok=True)
keep.write_text("ghi chú cũ\n", encoding="utf-8")
g_g = make_goal(guards=[{"description": "Ghi chú cũ vẫn còn", "evaluator": "artifact_contract",
                         "params": {"path": "Notes/ghi-chu-cu.md"}},
                        {"description": "Doanh số không giảm", "evaluator": "metric_series", "params": {}}])
clock_g = Clock()
deps_g, built_g, eng_g = make_deps(clock=clock_g)
store.set_wake(P, g_g.id, "work", clock_g() + 30 * 86400, "xa")
check("guard có lịch quan sát riêng", any(w["kind"] == "observe" for w in store.wakes(P, g_g.id)))
store.set_wake(P, g_g.id, "observe", clock_g() - 1, "tới hạn")
keep.unlink()
asyncio.run(R.tick(store, clock_g(), lambda b: deps_g))
st_g = store.run_state(P, g_g.id)
check("guard_wakes_without_worker: guard tới hạn được đọc mà KHÔNG gọi model", built_g["n"] == 0)
check("guard bị chạm: dừng phạm vi (blocked guard), bỏ lịch làm việc",
      st_g["block_reason"] == "guard" and not any(w["kind"] == "work" for w in store.wakes(P, g_g.id)))
ga = store.assessments(P, g_g.id)[-1]
check("guard chưa hỗ trợ nguồn: unknown và nói rõ chưa hỗ trợ",
      any(x["verdict"] == "unknown" and "chưa hỗ trợ" in x["reason"] for x in ga["guards"])
      and any(x["verdict"] == "triggered" for x in ga["guards"]))
adv(g_g.id, {"kind": "wake"}, deps_g)
check("guard đã nhảy không tự mở lại khi được đánh thức", built_g["n"] == 0 and store.run_state(P, g_g.id)["block_reason"] == "guard")

# ═══════════════════════ sự kiện tiếp tục: người dùng bổ sung, mục tiêu duy trì làm tiếp ═══════════════════════
g_c = make_goal(mode="maintain", horizon={"kind": "maintain"},
                criteria=[{"description": "Ghi chú có đủ việc", "evaluator": "artifact_contract",
                           "params": {"path": "Inbox/duy-tri.md", "must_contain": ["báo cáo quý", "máy lạnh"]}}])
deps_c, _, eng_c = make_deps()
a_c1 = adv(g_c.id, {"kind": "start"}, deps_c)
check("maintain: đạt thì không đóng mục tiêu, giữ active và hẹn xem lại",
      a_c1.verdict == "met" and store.get(P, g_c.id).status == "active"
      and any(w["kind"] == "work" for w in store.wakes(P, g_c.id)))
_nc = Notes()
asyncio.run(R.drain_outbox(store, _nc))
adv(g_c.id, {"kind": "wake"}, deps_c)
asyncio.run(R.drain_outbox(store, _nc))
check("maintain: lần đầu revision đạt thì báo người dùng MỘT lần, kèm link sản phẩm; xem lại sau không báo lặp",
      [k for (gid, k, _) in _nc.sent if gid == g_c.id] == ["goal.maintained"]
      and any("Inbox/duy-tri.md" in t for (gid, _, t) in _nc.sent if gid == g_c.id) and eng_c.queries == 1)
MSG_ADD = "Thêm việc: gia hạn tên miền trước cuối tháng."
R.revise_goal(store, P, g_c.id, 1, {
    "relevant_quote": "gia hạn tên miền",
    "criteria": [{"description": "Ghi chú có đủ việc", "evaluator": "artifact_contract",
                  "params": {"path": "Inbox/duy-tri.md", "must_contain": ["báo cáo quý", "máy lạnh", "tên miền"]}}]},
    {"message_ref": R.message_ref("s3", 950), "session_id": "s3", "message_id": 950, "user_text": MSG_ADD})
eng_c2 = FakeEngine(text=GOOD + "4. Gia hạn tên miền\n")
deps_c2, _, _ = make_deps(engine=eng_c2)
a_c2 = adv(g_c.id, {"kind": "wake"}, deps_c2)
check("tiếp tục sau bổ sung: lời gửi model có CẢ lời gốc lẫn tin bổ sung",
      "gọi thợ sửa máy lạnh" in eng_c2.last_prompt and "gia hạn tên miền trước cuối tháng" in eng_c2.last_prompt)
check("tiếp tục sau bổ sung: lời gửi model có bản sản phẩm hiện có để sửa tiếp",
      "Bản hiện có" in eng_c2.last_prompt and "Nộp báo cáo quý" in eng_c2.last_prompt)
check("tiếp tục sau bổ sung: revision mới đạt, file trong brain được cập nhật (cùng mục tiêu ghi trước thì ghi đè được)",
      a_c2.verdict == "met" and a_c2.revision == 2
      and "tên miền" in (Path(BRAIN) / "Inbox" / "duy-tri.md").read_text(encoding="utf-8"))

# ═══════════════════════ test_no_source_uses_bounded_review ═══════════════════════
now = 1_800_000_000.0
gm = store.get(P, make_goal(mode="maintain", horizon={"kind": "maintain"}).id)
w = R.next_wake(gm, {"kind": "assessed", "verdict": "met"}, now)
check("no_source_uses_bounded_review: không có nguồn sự kiện thì lần xem lại có giới hạn, không thăm dò dày",
      w and w["kind"] == "work" and now + R.REVIEW_MIN_S <= w["earliest_at"] <= now + R.REVIEW_DEFAULT_S)
w2 = R.next_wake(gm, {"kind": "user_schedule", "at": now + 3 * 86400}, now)
check("chỉ dẫn hẹn lần xem lại sửa lịch trực tiếp", w2 and w2["earliest_at"] == now + 3 * 86400)
check("reaction không sửa tần suất", R.next_wake(gm, {"kind": "reaction", "value": "like"}, now) is None)
ge = store.get(P, make_goal(horizon={"kind": "event", "event": "có ghi chú mới trong Inbox"}).id)
w3 = R.next_wake(ge, {"kind": "assessed", "verdict": "not_met"}, now)
check("có nguồn sự kiện nhưng chưa có adapter: vẫn chỉ xem lại có giới hạn, không thăm dò",
      w3 and w3["earliest_at"] >= now + R.REVIEW_MIN_S and "event" in w3["reason"])

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
