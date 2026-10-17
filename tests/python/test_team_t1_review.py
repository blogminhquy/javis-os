"""Nhóm chat team T1: hồi quy cho review mã vòng 1 (R1 tới R5) và vòng 2 (R7 tới R9), exports/reviews/PR-628-T1-code-r*-review.md.

    python tests/run.py team_t1_review -v

Đi qua factory THẬT `main._team_engine_for` (chỉ thay `team_engine.build` bằng engine giả có `query`) và kho SQLite thật
trong thư mục tạm; không gọi model. R6 (hạ, nâng cả bộ kho) nằm ở test_team_rollback.py vì cần mã 0.139.0 thật.
Mỗi nhóm có đối chứng hợp lệ: đường đúng vẫn ra "done", bài học hợp lệ vẫn được ghi, v.v.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-review-")
TEMP = Path(tempfile.mkdtemp(prefix="javis-team-review-w-"))

import main  # noqa: E402
import sessions  # noqa: E402
import task_store  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.run(coro)


INFO = {"agent-one": {"slug": "one", "name": "One", "system": "You are One.", "model": "", "model_provider": ""},
        "agent-two": {"slug": "two", "name": "Two", "system": "You are Two.", "model": "", "model_provider": ""}}
IDENT = dict(INFO)   # mã bền -> thông tin agent; test sửa để giả lập xoá, tạo lại cùng slug


def ident(root, key):
    return IDENT.get(key)


class Engine:
    """Engine giả có `query` như engine thật; `effect` chạy khi bắt đầu query (lúc lượt đang ở engine)."""

    def __init__(self, events, effect=None, available=True):
        self.events, self.effect, self.available, self.prompts = events, effect, available, []

    def is_available(self):
        return self.available

    async def query(self, prompt):
        self.prompts.append(prompt)
        if self.effect:
            self.effect()
        for ev in self.events:
            yield ev


_n = [0]


def world(label, engine_for=None, agents=("agent-one", "agent-two")):
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}-{label}"
    (d / "agents").mkdir(parents=True)
    for k in agents:
        (d / "agents" / f"{INFO[k]['slug']}.md").write_text(f"---\nname: {INFO[k]['name']}\nrole: Helper\n---\n",
                                                            encoding="utf-8", newline="\n")
    ss = sessions.SessionStore(db_path=d / "chat.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    tid = team_store.new_team_id()
    sid = ss.create_session(brain=str(d), channel=f"team:{tid}")
    tm.create_team(str(d), label, "", sid, team_id=tid)
    for k in agents:
        tm.add_member(tid, k, INFO[k]["slug"])
    tm.set_leader(tid, agents[0])
    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=engine_for or main._team_engine_for,
                      agent_info=ident)
    return r, tm, ts, ss, tm.get(tid), d


def memory_files_text(d):
    return "\n".join(p.read_text(encoding="utf-8") for p in d.glob("memory/agents/**/*") if p.is_file())


def scoped_lessons(prefix="team:"):
    """T3 phần L (0.156.0): bài học của lượt nhóm vào kho bài học phạm vi nhóm (`agent_lessons`), không vào MEMORY.md."""
    import agent_lessons
    from contextlib import closing as _closing
    st = main._resonance_store()
    agent_lessons.ensure(st)
    with _closing(st._conn()) as c:
        return [dict(r) for r in c.execute("SELECT * FROM agent_lessons WHERE scope LIKE ?", (prefix + "%",))]


def memory_text(d):
    """Mọi bộ nhớ bền của agent: file MEMORY.md và kho bài học có phạm vi (mã đánh dấu của từng ca là duy nhất)."""
    return memory_files_text(d) + "\n" + "\n".join(r["text"] for r in scoped_lessons(""))



def patch_build(return_value=None, side_effect=None):
    """Thay `team_engine.build` (0.142.0: lượt nhóm không còn đi qua `_resonance_engine`). Nhận đúng kiểu trả của hàm cũ,
    (engine | None, info), để các ca giữ nguyên: engine None thì `build` ném TeamEngineUnavailable như provider không chạy
    được chỉ chữ."""
    seq = iter(side_effect) if isinstance(side_effect, list) else None

    def src(system, tag):
        if seq is not None:
            return next(seq)
        if side_effect is not None:
            return side_effect(system, tag)
        return return_value

    def build(spec, base, tag, settings=None, **_kw):
        eng, why = src(getattr(base, "system_prompt", ""), tag)
        if eng is None:
            raise main.team_engine.TeamEngineUnavailable(str((why or {}).get("reason") or why), spec.get("provider", ""))
        return eng
    # 0.194.0: Work/Help steps build through `build_tools` (the member's toolkit), every other turn through `build`.
    return patch.multiple(main.team_engine, build=build, build_tools=build)

def agent_msgs(ss, team):
    return [m for m in ss.get_team_messages_page(team["session_id"], limit=200)["messages"] if m["author_kind"] == "agent"]


def job_via_factory(label, events, *, effect=None, available=True, build=None, mention="agent-one", text="Viết tóm tắt"):
    """Một việc @ trực tiếp chạy qua factory thật. `build` thay hẳn bước dựng engine (`team_engine.build`) (vd. trả None hay ném lỗi)."""
    r, tm, ts, ss, t, d = world(label)
    job = r.submit(t["team_id"], text, mentions=[mention], as_job=True, client_msg_id=label)["task_id"]
    holder = {}

    def make_effect():
        return (lambda: effect(r, tm, ts, ss, t, job)) if effect else None

    def fake_resonance(system, tag):
        if build is not None:
            return build()
        eng = Engine(events, make_effect(), available)
        holder["eng"] = eng
        return eng, {"reason": "fake"}

    with patch.object(main, "_team_agent_info", side_effect=ident), \
            patch_build(side_effect=fake_resonance):
        run(r.dispatch_once())
    return {"r": r, "tm": tm, "ts": ts, "ss": ss, "t": t, "d": d, "job": job, "task": ts.get_task(job),
            "turns": tm.turns(t["team_id"]), "msgs": agent_msgs(ss, t), "eng": holder.get("eng")}


class Recorder:
    def __init__(self, answers=None):
        self.reqs, self.answers = [], list(answers or [])

    def engine_for(self, team, key, role):
        async def run_(req):
            self.reqs.append(req)
            return {"text": self.answers.pop(0) if self.answers else "OK"}
        return "fake", "fake", run_



# ═════════════ R1: kết cục engine lỗi hay rỗng không bao giờ thành sản phẩm ═════════════
def section_r1():
    BAD = {
        "final_error": [{"type": "final", "content": "Engine failed", "is_error": True, "subtype": "error_during_execution"}],
        "auth_race": [{"type": "final", "content": "Please run /login", "auth_refresh_race": True}],
        "error_after_final": [{"type": "final", "content": "Câu trả lời"}, {"type": "error", "content": "socket closed"}],
        "error_event": [{"type": "error", "content": "rate limited"}, {"type": "final", "content": "Câu trả lời"}],
        "tool_call": [{"type": "tool_call", "name": "Write", "input": {}}, {"type": "final", "content": "OK"}],
        "tool_result": [{"type": "tool_result", "content": "x"}, {"type": "final", "content": "OK"}],
        "empty_final": [{"type": "final", "content": ""}],
        "blank_final": [{"type": "final", "content": "  \n "}],
        "no_final": [{"type": "text", "content": "đang nghĩ"}],
    }
    # 0.194.0: a Work step runs with the member's tools, so a tool call there is normal work (checked below), not an
    # error. Reply turns stay text only (the reply section checks that a tool call still breaks them).
    TOOL_OK = ("tool_call", "tool_result")
    for name in TOOL_OK:
        w = job_via_factory(f"r1-{name}", BAD[name])
        check(f"R1 {name}: lượt Làm có công cụ, gọi công cụ rồi trả final thì việc xong",
              w["task"]["status"] == "done" and [x["status"] for x in w["turns"]] == ["ok"], (w["task"], w["turns"]))
    for name, events in BAD.items():
        if name in TOOL_OK:
            continue
        w = job_via_factory(f"r1-{name}", events)
        turns = w["turns"]
        check(f"R1 {name}: việc không xong, bị chặn 'failed' để Chạy lại",
              w["task"]["status"] == "team_blocked" and w["task"]["block_kind"] == "failed", w["task"])
        check(f"R1 {name}: lượt đã gọi model nên TÍNH (error, có mốc engine), không hoàn, không 'ok'",
              [x["status"] for x in turns] == ["error"] and turns[0]["engine_at"] is not None, turns)
        check(f"R1 {name}: không có tin kết quả nào của agent", w["msgs"] == [], w["msgs"])

    w = job_via_factory("r1-control", [{"type": "usage", "input_tokens": 5, "output_tokens": 3},
                                       {"type": "final", "content": "Bản tóm tắt hợp lệ"}])
    check("R1 đối chứng: final hợp lệ thì việc xong, lượt ok, có token",
          w["task"]["status"] == "done" and [(x["status"], x["tokens_in"]) for x in w["turns"]] == [("ok", 5)]
          and w["task"]["result"] == "Bản tóm tắt hợp lệ")
    w = job_via_factory("r1-resume", [{"type": "error", "content": "mất mạch", "resume_failed": True},
                                      {"type": "final", "content": "Đã mồi lại, trả lời"}])
    check("R1 đối chứng: lỗi mất mạch đã được engine mồi lại trong lượt không biến lượt tốt thành lỗi",
          w["task"]["status"] == "done")

    # Chạy lại sau khi engine trả lời được: việc xong.
    w = job_via_factory("r1-retry", BAD["final_error"])
    with patch.object(main, "_team_agent_info", side_effect=ident), \
            patch_build(return_value=(Engine([{"type": "final", "content": "Lần này ổn"}]),
                                                                   {})):
        w["r"].unblock(w["job"], "retry")
        run(w["r"].dispatch_once())
    check("R1 Chạy lại sau lỗi engine: việc xong, hai lượt đều tính (error rồi ok)",
          w["ts"].get_task(w["job"])["status"] == "done"
          and sorted(x["status"] for x in w["tm"].turns(w["t"]["team_id"])) == ["error", "ok"])

    # Lượt trò chuyện: final lỗi không thành câu trả lời.
    r, tm, ts, ss, t, d = world("r1-reply")
    with patch.object(main, "_team_agent_info", side_effect=ident), \
            patch_build(return_value=(Engine(BAD["final_error"]), {})):
        outs = run(r.run_replies(r.submit(t["team_id"], "Chào", client_msg_id="r1-reply")))
    check("R1 lượt trò chuyện final lỗi: kết cục error, không đăng câu trả lời, lượt tính",
          [o["status"] for o in outs] == ["error"] and agent_msgs(ss, t) == []
          and [x["status"] for x in tm.turns(t["team_id"])] == ["error"])
    # 0.194.0: chat replies stay text only, so a tool call there still breaks the turn.
    r, tm, ts, ss, t, d = world("r1-reply-tool")
    with patch.object(main, "_team_agent_info", side_effect=ident), \
            patch_build(return_value=(Engine(BAD["tool_call"]), {})):
        outs = run(r.run_replies(r.submit(t["team_id"], "Chào", client_msg_id="r1-reply-tool")))
    check("R1 lượt trò chuyện gọi công cụ: vẫn là lỗi (trò chuyện chỉ chữ), không đăng câu trả lời",
          [o["status"] for o in outs] == ["error"] and agent_msgs(ss, t) == [])

    o = TR.TextOnlyOutcome()
    for ev in ({"type": "text", "content": "a"}, {"type": "usage", "input_tokens": 2, "output_tokens": 1},
               {"type": "final", "content": "Xong"}):
        o.note(ev)
    check("R1 hợp đồng chỉ chữ: final hợp lệ trả chữ và token", o.result() == {"text": "Xong", "tokens_in": 2,
                                                                              "tokens_out": 1})
    o = TR.TextOnlyOutcome()
    o.note({"type": "final", "content": "x", "is_error": True, "subtype": "error_max_turns"})
    try:
        o.result()
        kind = None
    except TR.EngineOutcomeError as ex:
        kind = ex.kind
    check("R1 hợp đồng chỉ chữ: final is_error ném EngineOutcomeError(final_error)", kind == "final_error")


# ═════════════ R2: lượt sau còn lịch sử trước (cửa sổ có giới hạn, chỉ của nhóm này) ═════════════
def section_r2():
    rec = Recorder(["ANSWER_ONE: đã ghi nhận ngân sách."])
    r, tm, ts, ss, t, d = world("r2", rec.engine_for)
    run(r.run_replies(r.submit(t["team_id"], "SOURCE_739: budget 73 million", client_msg_id="a")))
    run(r.run_replies(r.submit(t["team_id"], "Divide that budget into three parts.", client_msg_id="b")))
    p2 = rec.reqs[1]["prompt"]
    check("R2 lượt thứ hai có tin gốc của chủ và câu trả lời trước", "SOURCE_739" in p2 and "ANSWER_ONE" in p2, p2)
    check("R2 câu trả lời trước của chính agent có nhãn (bạn), tin sau lượt trước có nhãn mới",
          "One (bạn)] ANSWER_ONE" in p2 and " mới Chủ nhóm] Divide" in p2, p2)

    # Đối chứng phạm vi: nhóm khác cùng kho không lọt vào.
    tid_b = team_store.new_team_id()
    sid_b = ss.create_session(brain=str(d), channel=f"team:{tid_b}")
    tm.create_team(str(d), "B", "", sid_b, team_id=tid_b)
    tm.add_member(tid_b, "agent-one", "one")
    tm.set_leader(tid_b, "agent-one")
    run(r.run_replies(r.submit(tid_b, "SECRET_B chỉ của nhóm B", client_msg_id="sb")))
    run(r.run_replies(r.submit(t["team_id"], "Tiếp tục nhé", client_msg_id="c")))
    check("R2 không đưa dữ liệu nhóm khác vào prompt", "SECRET_B" not in rec.reqs[-1]["prompt"]
          and "SECRET_B" in rec.reqs[-2]["prompt"])

    # Trần: tối đa 20 tin gần nhất, tối đa 8.000 ký tự.
    rec = Recorder()
    r, tm, ts, ss, t, d = world("r2-cap", rec.engine_for)
    tm.set_caps(t["team_id"], {"daily_turns": 1000})
    for i in range(25):
        ss.append_team_message(t["session_id"], "user", f"MSG_{i:02d}", author_kind="owner", client_msg_id=f"m{i}")
    run(r.run_replies(r.submit(t["team_id"], "Câu hỏi cuối", client_msg_id="last")))
    p = rec.reqs[-1]["prompt"]
    check("R2 trần 20 tin: tin cũ nhất ngoài cửa sổ bị bỏ, tin gần nhất còn",
          "MSG_05" not in p and "MSG_06" in p and "MSG_24" in p, p[-1500:])
    ss.append_team_message(t["session_id"], "user", "BIG_" + "x" * 9000, author_kind="owner", client_msg_id="big")
    run(r.run_replies(r.submit(t["team_id"], "SHORT_AFTER", client_msg_id="short")))
    p = rec.reqs[-1]["prompt"]
    check("R2 trần 8.000 ký tự: tin quá dài không vào cửa sổ, tin mới hơn vẫn có", "BIG_" not in p.split("\n\n")[0]
          and "SHORT_AFTER" in p)


# ═════════════ R3: đầu ra không hợp lệ không ghi bộ nhớ bền ═════════════
def section_r3():
    LESSON = "\nJAVIS_LESSON: {}"


    def lesson_events(mark):
        return [{"type": "final", "content": "Kết quả" + LESSON.format(mark)}]


    w = job_via_factory("r3-control", lesson_events("GOOD_LESSON_101"))
    check("R3 đối chứng: đầu ra hợp lệ ghi bài học vào bộ nhớ agent, tin sạch marker",
          "GOOD_LESSON_101" in memory_text(w["d"]) and w["task"]["status"] == "done"
          and "JAVIS_LESSON" not in w["msgs"][0]["content"])
    good = [x for x in scoped_lessons() if x["text"] == "GOOD_LESSON_101"]
    check("R3 + T3: bài học của lượt nhóm vào phạm vi team:<id> (nguồn self, gắn lượt), không vào MEMORY.md",
          len(good) == 1 and good[0]["scope"] == f"team:{w['t']['team_id']}" and good[0]["source"] == "self"
          and '"turn:' in good[0]["source_refs_json"] and "GOOD_LESSON_101" not in memory_files_text(w["d"]), good)
    w = job_via_factory("r3-rule", [{"type": "final", "content": "Kết quả\nJAVIS_RULE: RULE_202 luôn viết ngắn"}])
    check("R3 JAVIS_RULE trong lượt nhóm hạ thành bài học (không có chủ nói trực tiếp), ghi khi hợp lệ",
          "RULE_202" in memory_text(w["d"]) and "JAVIS_RULE" not in w["msgs"][0]["content"])

    LATE = {
        "member_left": lambda r, tm, ts, ss, t, job: tm.remove_member(t["team_id"], "agent-one"),
        "cancelled": lambda r, tm, ts, ss, t, job: ts.team_cancel(job),
        "revision": lambda r, tm, ts, ss, t, job: ts.team_amend(job, "thêm phần mới"),
    }
    for name, eff in LATE.items():
        mark = f"LATE_{name.upper()}_739"
        w = job_via_factory(f"r3-{name}", lesson_events(mark), effect=eff)
        m = w["msgs"][0] if w["msgs"] else {"meta": {}}
        check(f"R3 {name}: đầu ra muộn KHÔNG ghi bài học vào bộ nhớ agent", mark not in memory_text(w["d"]),
              memory_text(w["d"]))
        check(f"R3 {name}: đầu ra muộn giữ làm bằng chứng trên tin (applied=false, bài học treo)",
              m["meta"].get("applied") is False and mark in " ".join(m["meta"].get("held_lessons") or []), m["meta"])

    # Đổi trưởng nhóm giữa bước lập kế hoạch (việc chung, không @).
    r, tm, ts, ss, t, d = world("r3-leader")
    job = r.submit(t["team_id"], "Việc chung", as_job=True, client_msg_id="lead")["task_id"]
    eng = Engine(lesson_events("LATE_LEADER_739"), lambda: tm.set_leader(t["team_id"], "agent-two"))
    eng2 = Engine([{"type": "final", "content": "Two tự làm xong"}])
    with patch.object(main, "_team_agent_info", side_effect=ident), \
            patch_build(side_effect=[(eng, {}), (eng2, {})]):
        run(r.dispatch_once())
    check("R3 đổi trưởng nhóm giữa lượt điều phối: kế hoạch cũ không ghi bài học, trưởng nhóm mới làm tiếp",
          "LATE_LEADER_739" not in memory_text(d) and ts.get_task(job)["status"] == "done")


    # Xoá agent rồi tạo lại CÙNG slug khi lượt đang ở engine: mã bền cũ không còn trỏ tới slug đó.
    def recreate(r, tm, ts, ss, t, job):
        IDENT.pop("agent-one", None)
        IDENT["agent-one-new"] = dict(INFO["agent-one"])


    w = job_via_factory("r3-recreate", lesson_events("LATE_RECREATE_739"), effect=recreate)
    IDENT.clear()
    IDENT.update(INFO)
    check("R3 xoá rồi tạo lại cùng slug: bài học của mã cũ không vào bộ nhớ của agent mới",
          "LATE_RECREATE_739" not in memory_text(w["d"]), memory_text(w["d"]))

    # Không có khe giữa kiểm và ghi: thao tác bỏ thành viên đang giữ khoá chấp nhận thì pha chấp nhận đợi, rồi thấy đã rời.
    holding = threading.Event()


    def remove_under_lock(r, tm, ts, ss, t, job):
        def hold():
            with r.accept_lock:
                holding.set()
                time.sleep(0.3)
                tm.remove_member(t["team_id"], "agent-one")
        threading.Thread(target=hold, daemon=True).start()
        holding.wait(2)


    w = job_via_factory("r3-race", lesson_events("LATE_RACE_739"), effect=remove_under_lock)
    check("R3 bỏ thành viên trong khoá chấp nhận: pha chấp nhận đợi khoá, thấy đã rời, không ghi bài học",
          "LATE_RACE_739" not in memory_text(w["d"]) and w["msgs"][0]["meta"]["status"] == "member_left", w["msgs"])

    # Một lượt bị xử lý lặp: bài học ghi đúng một lần.
    r, tm, ts, ss, t, d = world("r3-twice", Recorder().engine_for)
    tu = tm.reserve_turn(t["team_id"], None, None, "agent-one", "leader_reply")
    tm.mark_engine(tu, "fake", "fake")
    tm.settle_turn(tu, "ok")
    hits = []
    res = {"text": "Trả lời", "commit": lambda: hits.append(1), "lessons": ["L"]}
    r._accept(t["team_id"], "agent-one", "leader_reply", None, None, tu, res, None, None)
    r._accept(t["team_id"], "agent-one", "leader_reply", None, None, tu, res, None, None)
    check("R3 xử lý lặp cùng lượt: commit đúng một lần", hits == [1], hits)
    tu2 = tm.reserve_turn(t["team_id"], None, None, "agent-one", "leader_reply")
    tm.mark_engine(tu2, "fake", "fake")
    tm.settle_turn(tu2, "error")
    check("R3 lượt không 'ok' không giành được quyền ghi", tm.claim_commit(tu2) is False)


# ═════════════ R4: chưa dựng được engine thì không tính lượt ═════════════
def section_r4():
    def none_engine():
        return None, {"reason": "provider chưa sẵn sàng"}


    def broken_build():
        raise RuntimeError("cấu hình hỏng")


    for name, kw in (("none", {"build": none_engine}), ("unavailable", {"available": False}),
                     ("build_raises", {"build": broken_build})):
        w = job_via_factory(f"r4-{name}", [{"type": "final", "content": "không bao giờ tới"}], **kw)
        turns = w["turns"]
        check(f"R4 {name}: lượt hoàn đúng một lần, không có mốc engine",
              [x["status"] for x in turns] == ["refunded"] and turns[0]["engine_at"] is None, turns)
        check(f"R4 {name}: không lời gọi model nào", (w["eng"] is None) or w["eng"].prompts == [])
        check(f"R4 {name}: việc bị chặn có lý do để Chạy lại, trần ngày không bị trừ",
              w["task"]["status"] == "team_blocked" and "engine" in (w["task"]["block_reason"] or "")
              and w["tm"].count_team_turns(w["t"]["team_id"], 0) == 0, w["task"])

    # Bị huỷ khi engine đang dựng (chưa tới mốc): hoàn, không interrupted.
    gate = threading.Event()


    def slow_build():
        gate.wait(5)
        return Engine([{"type": "final", "content": "x"}]), {}


    r, tm, ts, ss, t, d = world("r4-cancel")
    job = r.submit(t["team_id"], "Việc", mentions=["agent-one"], as_job=True, client_msg_id="c")["task_id"]


    async def cancel_while_building():
        await r.dispatch_once(wait=False)
        for _ in range(300):
            if [x for x in tm.turns(t["team_id"]) if x["status"] == "reserved"] and tm.busy_of("agent-one"):
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        r.cancel_job(job)
        await r.wait_jobs()
        gate.set()


    with patch.object(main, "_team_agent_info", side_effect=ident), \
            patch_build(side_effect=lambda s, tag: slow_build()):
        run(cancel_while_building())
    check("R4 huỷ khi engine đang dựng: lượt hoàn (không interrupted), khoá bận nhả",
          [x["status"] for x in tm.turns(t["team_id"])] == ["refunded"] and tm.busy_of("agent-one") is None,
          tm.turns(t["team_id"]))

    # Restart khi lượt còn giữ chỗ chưa tới mốc: phục hồi hoàn đúng một lần, chạy lại phục hồi không đổi gì.
    r, tm, ts, ss, t, d = world("r4-restart")
    tu = tm.reserve_turn(t["team_id"], None, None, "agent-one", "leader_reply")
    r.recover()
    r.recover()
    check("R4 phục hồi sau restart: lượt chưa tới mốc hoàn đúng một lần",
          [(x["status"], x["engine_at"]) for x in tm.turns(t["team_id"])] == [("refunded", None)])


# ═════════════ R5: I/O chặn không chạy trên event loop ═════════════
def section_r5():
    def slow(fn, s=0.25, log=None, name=""):
        def wrap(*a, **k):
            time.sleep(s)
            out = fn(*a, **k)
            if log is not None:
                log.append((name, time.monotonic()))
            return out
        return wrap


    async def max_gap(coro_factory, beats_n=80):
        beats = []
        stop = asyncio.Event()
        # Dọn rác TRƯỚC khi đo (0.176.0): một lượt gc thế hệ 2 trên tiến trình đã nạp cả `main` dừng mọi luồng ~130 ms và
        # rơi vào cửa sổ đo tuỳ lúc, tức là đổi chỗ nào đó số đối tượng tạo ra là test đỏ dù không có I/O nào chạy trên
        # event loop. Test này canh I/O chặn, không canh lịch dọn rác của Python.
        import gc
        gc.collect()

        async def pulse():
            while not stop.is_set():
                t0 = time.perf_counter()
                await asyncio.sleep(0.005)
                beats.append(time.perf_counter() - t0)
        p = asyncio.create_task(pulse())
        await asyncio.sleep(0.02)
        out = await coro_factory()
        stop.set()
        await p
        return round(max(beats) * 1000, 1), out


    rec = Recorder()
    r, tm, ts, ss, t, d = world("r5-reply", rec.engine_for)
    with patch.object(tm, "reserve_turn", side_effect=slow(tm.reserve_turn)), \
            patch.object(tm, "settle_turn", side_effect=slow(tm.settle_turn)), \
            patch.object(ss, "append_team_message", side_effect=slow(ss.append_team_message)):
        sub = r.submit(t["team_id"], "Hello", client_msg_id="lag")
        gap, _ = run(max_gap(lambda: r.run_replies(sub)))
    check("R5 lượt trả lời với kho chậm 250 ms mỗi ghi: event loop không bị chặn quá 100 ms", gap < 100, gap)

    rec = Recorder()
    r, tm, ts, ss, t, d = world("r5-job", rec.engine_for)
    job = r.submit(t["team_id"], "Việc", mentions=["agent-one"], as_job=True, client_msg_id="j")["task_id"]
    with patch.object(ts, "get_task", side_effect=slow(ts.get_task, 0.1)), \
            patch.object(tm, "claim_step", side_effect=slow(tm.claim_step)), \
            patch.object(tm, "finish_step", side_effect=slow(tm.finish_step)):
        gap, _ = run(max_gap(lambda: r.dispatch_once()))
    check("R5 việc nhóm với kho chậm: event loop không bị chặn, việc vẫn xong", gap < 100
          and ts.get_task(job)["status"] == "done", (gap, ts.get_task(job)["status"]))

    # Đồng thời: trần ngày 1, hai lượt cùng lúc chỉ một lượt được giữ chỗ (đếm và ghi cùng giao dịch).
    rec = Recorder()
    r, tm, ts, ss, t, d = world("r5-cap", rec.engine_for)
    s1 = r.submit(t["team_id"], "A", mentions=["agent-one"], client_msg_id="x1")
    s2 = r.submit(t["team_id"], "B", mentions=["agent-two"], client_msg_id="x2")
    tm.set_caps(t["team_id"], {"daily_turns": 1})


    async def both():
        return await asyncio.gather(r.run_replies(s1), r.run_replies(s2))


    with patch.object(tm, "reserve_turn", side_effect=slow(tm.reserve_turn, 0.1)):
        outs = run(both())
    statuses = sorted(o[0]["status"] for o in outs)
    check("R5 hai lượt đồng thời, trần ngày 1: đúng một lượt chạy, lượt kia chạm trần, không lượt nào tới engine thừa",
          statuses == ["cap", "done"] and len(rec.reqs) == 1
          and len([x for x in tm.turns(t["team_id"]) if x["status"] != "refunded"]) == 1, (statuses, len(rec.reqs)))
    tm2 = team_store.TeamStore(TEMP / "r5-threads.sqlite3")
    got, errs = [], []


    def grab():
        try:
            got.append(tm2.reserve_turn("tmX", None, None, "a", "leader_reply", daily_cap=3, day_start=0))
        except team_store.TurnCapReached:
            errs.append(1)


    ths = [threading.Thread(target=grab) for _ in range(8)]
    for th in ths:
        th.start()
    for th in ths:
        th.join()
    check("R5 tám luồng giữ chỗ cùng lúc, trần 3: đúng 3 lượt, 5 lượt bị từ chối", len(got) == 3 and len(errs) == 5,
          (len(got), len(errs)))

    # Huỷ (lặp) khi luồng phụ đang ghi lượt giữ chỗ: chờ ghi xong rồi hoàn, không lượt mồ côi, không kẹt khoá.
    rec = Recorder()
    r, tm, ts, ss, t, d = world("r5-cancel", rec.engine_for)
    sub = r.submit(t["team_id"], "Hello", client_msg_id="cc")


    async def cancel_twice():
        task = asyncio.ensure_future(r.run_replies(sub))
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
            return "finished"
        except asyncio.CancelledError:
            return "cancelled"


    with patch.object(tm, "reserve_turn", side_effect=slow(tm.reserve_turn, 0.3)):
        how = run(cancel_twice())
    lock = r._locks.get("agent-one")
    check("R5 huỷ lặp khi đang giữ chỗ: lượt vừa ghi được hoàn, không còn 'reserved', không gọi engine, không kẹt khoá",
          how == "cancelled" and [x["status"] for x in tm.turns(t["team_id"])] == ["refunded"] and rec.reqs == []
          and tm.busy_of("agent-one") is None and not (lock and lock.locked()), (how, tm.turns(t["team_id"])))

    # Huỷ khi luồng phụ đang chốt lượt: chốt xong (không bỏ dở 'running'), dòng khoá chỉ nhả SAU khi chốt xong.
    rec = Recorder()
    r, tm, ts, ss, t, d = world("r5-settle", rec.engine_for)
    sub = r.submit(t["team_id"], "Hello", client_msg_id="cs")
    order = []


    async def cancel_during_settle():
        task = asyncio.ensure_future(r.run_replies(sub))
        for _ in range(300):
            if rec.reqs:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        task.cancel()
        await asyncio.sleep(0.02)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


    with patch.object(tm, "settle_turn", side_effect=slow(tm.settle_turn, 0.3, order, "settle")), \
            patch.object(tm, "release_busy", side_effect=slow(tm.release_busy, 0, order, "release")):
        run(cancel_during_settle())
    lock = r._locks.get("agent-one")
    names = [n for n, _ in order]
    check("R5 huỷ khi đang chốt lượt: lượt chốt 'ok' (không treo running), nhả khoá sau khi chốt xong",
          [x["status"] for x in tm.turns(t["team_id"])] == ["ok"] and names[:2] == ["settle", "release"]
          and tm.busy_of("agent-one") is None and not (lock and lock.locked()), (tm.turns(t["team_id"]), names))

    # Huỷ khi luồng phụ đang lấy dòng khoá bận: dòng vừa lấy được nhả (undo), khoá trong tiến trình nhả.
    rec = Recorder()
    r, tm, ts, ss, t, d = world("r5-busy", rec.engine_for)
    sub = r.submit(t["team_id"], "Hello", client_msg_id="cb")


    async def cancel_during_busy():
        task = asyncio.ensure_future(r.run_replies(sub))
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


    with patch.object(tm, "acquire_busy", side_effect=slow(tm.acquire_busy, 0.3)):
        run(cancel_during_busy())
    lock = r._locks.get("agent-one")
    check("R5 huỷ khi đang lấy khoá bận: dòng khoá nhả, khoá trong tiến trình nhả, lượt hoàn",
          tm.busy_of("agent-one") is None and not (lock and lock.locked())
          and [x["status"] for x in tm.turns(t["team_id"])] == ["refunded"], tm.turns(t["team_id"]))

    # Kho lỗi khi giữ chỗ: không có dòng nào, việc bị chặn có lý do, không kẹt khoá.
    rec = Recorder()
    r, tm, ts, ss, t, d = world("r5-error", rec.engine_for)
    job = r.submit(t["team_id"], "Việc", mentions=["agent-one"], as_job=True, client_msg_id="e")["task_id"]
    with patch.object(tm, "reserve_turn", side_effect=sqlite3.OperationalError("database is locked")):
        run(r.dispatch_once())
    lock = r._locks.get("agent-one")
    check("R5 kho lỗi khi giữ chỗ: việc chặn 'failed' có lý do, không có lượt, không kẹt khoá",
          ts.get_task(job)["status"] == "team_blocked" and "database is locked" in ts.get_task(job)["block_reason"]
          and tm.turns(t["team_id"]) == [] and not (lock and lock.locked()), ts.get_task(job))

    # Route ghi thật (POST /teams/{id}/messages) với kho phiên chậm: event loop không bị chặn.
    import httpx  # noqa: E402

    BR = TEMP / "route-brain"
    (BR / "agents").mkdir(parents=True)
    for k in ("agent-one", "agent-two"):
        (BR / "agents" / f"{INFO[k]['slug']}.md").write_text(f"---\nname: {INFO[k]['name']}\nrole: Helper\n---\n",
                                                             encoding="utf-8", newline="\n")
    main._TEAM_API.deps.spawn = lambda coro: coro.close() if asyncio.iscoroutine(coro) else None


    async def route_probe():
        tr = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=tr, base_url="http://127.0.0.1:8080") as c:
            resp = await c.post(f"/teams?brain={BR}", json={"name": "Route", "members": ["one"], "leader_slug": "one"})
            tid = resp.json()["team"]["team_id"]
            store = main.get_store()
            with patch.object(store, "append_team_message", side_effect=slow(store.append_team_message)):
                async def send():
                    return await c.post(f"/teams/{tid}/messages?brain={BR}",
                                        json={"text": "Xin chào", "client_msg_id": "route-1"})
                gap, resp2 = await max_gap(send)
            return gap, resp2.status_code


    gap, code = run(route_probe())
    check("R5 route gửi tin với kho phiên chậm 250 ms: 200 và event loop không bị chặn quá 100 ms",
          code == 200 and gap < 100, (gap, code))


# ═════════════ R7, R8, R9 (review T1 vòng 2): biên áp kết quả, pool chung, khôi phục hỏng sau ghi ═════════════
WAIT = 5  # giây: mọi chờ đồng bộ trong các mục dưới đều có hạn, không dựa vào ngủ cố định


def world_n(label, engine_fn, count=1, members=1):
    """`count` nhóm, mỗi nhóm `members` agent riêng (agent-<nhóm>-<i>), agent đầu là trưởng nhóm. Engine là hàm async
    nhận req (giả), agent_info chấp nhận mọi mã."""
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}-{label}"
    d.mkdir(parents=True)
    ss = sessions.SessionStore(db_path=d / "chat.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    teams = []
    for i in range(count):
        tid = team_store.new_team_id()
        sid = ss.create_session(brain=str(d), channel=f"team:{tid}")
        tm.create_team(str(d), f"{label}{i}", "", sid, team_id=tid)
        for j in range(members):
            tm.add_member(tid, f"agent-{i}-{j}", f"a{i}{j}")
        tm.set_leader(tid, f"agent-{i}-0")
        teams.append(tm.get(tid))
    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=lambda *a: ("fake", "fake", engine_fn),
                      agent_info=lambda root, key: {"slug": key, "name": key, "system": "Fake"})
    return r, tm, ts, ss, teams


def gate_apply(r, kinds):
    """Chặn ở cửa vào `_apply_step` cho bước đầu tiên thuộc `kinds` (sau khi đầu ra đã được chấp nhận và đăng)."""
    entered, release = threading.Event(), threading.Event()
    original = r._apply_step

    def gated(team, task, step, out):
        if step["kind"] in kinds and not entered.is_set():
            entered.set()
            if not release.wait(WAIT):
                raise TimeoutError("test barrier")
        return original(team, task, step, out)
    return gated, entered, release


async def race_at_apply(r, kinds, action):
    """Chạy dispatch thật; khi một bước `kinds` tới cửa áp dụng thì chạy `action` (ở luồng phụ, như route) rồi nhả."""
    gated, entered, release = gate_apply(r, kinds)
    got = {}
    with patch.object(r, "_apply_step", side_effect=gated):
        work = asyncio.ensure_future(r.dispatch_once())
        reached = await asyncio.to_thread(entered.wait, WAIT)
        try:
            if reached:
                got["action"] = await asyncio.to_thread(action)
        finally:
            release.set()
        await asyncio.wait_for(work, 20)
    got["reached"] = reached
    return got


def scripted(answers, hits=None):
    """Engine giả theo thứ tự; mỗi câu trả lời kèm `commit` ghi lại vào `hits` (giả bài học)."""
    calls = []

    async def fn(req):
        calls.append(req)
        text = answers[len(calls) - 1] if len(calls) <= len(answers) else f"EXTRA_{len(calls)}"
        tag = text

        def commit():
            if hits is not None:
                hits.append(tag)
        return {"text": text, "commit": commit, "lessons": [f"L_{tag}"]}
    return fn, calls


def section_r7():
    # 1. Kế hoạch trả lời trực tiếp (không giao ai) + sửa yêu cầu giữa chấp nhận và áp dụng (kịch bản reviewer).
    hits = []
    fn, calls = scripted(["OLD_RESULT", "NEW_RESULT"], hits)
    r, tm, ts, ss, teams = world_n("r7-plan", fn)
    t = teams[0]
    job = r.submit(t["team_id"], "Original brief", as_job=True, client_msg_id="j")["task_id"]

    def amend():
        with r.accept_lock:
            return ts.team_amend(job, "NEW_REQUIREMENT")
    got = run(race_at_apply(r, ("plan",), amend))
    task = ts.get_task(job)
    old = [m for m in agent_msgs(ss, t) if m["content"] == "OLD_RESULT"]
    check("R7 kế hoạch trả lời trực tiếp: tới cửa áp dụng, sửa yêu cầu thành công (bản 2)",
          got.get("reached") and got.get("action") == 2, got)
    check("R7 kế hoạch: yêu cầu mới KHÔNG bị chốt bằng kết quả bản cũ; làm lại và chốt NEW_RESULT ở bản 2",
          task["status"] == "done" and task["team_rev"] == 2 and task["result"] == "NEW_RESULT" and len(calls) == 2,
          (task["status"], task["team_rev"], task["result"], len(calls)))
    check("R7 kế hoạch: bước bản 1 không áp dụng; tin cũ còn làm bằng chứng (applied=false, old_revision)",
          [(s["job_revision"], s["status"], bool(s["applied"])) for s in tm.steps(job)][0] == (1, "cancelled", False)
          and old and old[0]["meta"]["applied"] is False and old[0]["meta"]["status"] == "old_revision"
          and not old[0]["meta"].get("job_result"), (tm.steps(job), old and old[0]["meta"]))
    check("R7 kế hoạch: bài học của kết quả cũ không ghi, của kết quả mới ghi đúng một lần", hits == ["NEW_RESULT"],
          hits)

    # 2. Đối chứng: không sửa yêu cầu thì kết quả bản 1 chốt bình thường, bài học ghi một lần.
    hits = []
    fn, calls = scripted(["OLD_RESULT"], hits)
    r, tm, ts, ss, teams = world_n("r7-plan-control", fn)
    job = r.submit(teams[0]["team_id"], "Original brief", as_job=True, client_msg_id="j")["task_id"]
    got = run(race_at_apply(r, ("plan",), lambda: None))
    task = ts.get_task(job)
    check("R7 đối chứng: không sửa thì bản 1 chốt OLD_RESULT, một lượt, bài học một lần",
          task["status"] == "done" and task["team_rev"] == 1 and task["result"] == "OLD_RESULT" and len(calls) == 1
          and hits == ["OLD_RESULT"], (task, hits))

    # 3. Bước làm (@ trực tiếp) + sửa yêu cầu ở cửa áp dụng: người được giao làm lại theo bản mới.
    fn, calls = scripted(["OLD_WORK", "NEW_WORK"])
    r, tm, ts, ss, teams = world_n("r7-work", fn)
    t = teams[0]
    job = r.submit(t["team_id"], "Viết", mentions=["agent-0-0"], as_job=True, client_msg_id="j")["task_id"]
    def amend_work():
        with r.accept_lock:
            return ts.team_amend(job, "thêm")
    got = run(race_at_apply(r, ("work",), amend_work))
    task = ts.get_task(job)
    check("R7 bước làm: kết quả cũ không chốt bản 2; làm lại, chốt NEW_WORK",
          got.get("action") == 2 and task["status"] == "done" and task["team_rev"] == 2
          and task["result"] == "NEW_WORK", (got, task["status"], task["result"]))

    # 4. Bước tổng hợp + sửa yêu cầu ở cửa áp dụng: tổng hợp cũ không chốt; hai người làm lại, tổng hợp lại.
    fn, calls = scripted(["W1", "W2", "OLD_SYNTH", "W1b", "W2b", "NEW_SYNTH"])
    r, tm, ts, ss, teams = world_n("r7-synth", fn, members=3)
    t = teams[0]
    job = r.submit(t["team_id"], "Hai phần", mentions=["agent-0-1", "agent-0-2"], as_job=True,
                   client_msg_id="j")["task_id"]

    def amend_synth():
        with r.accept_lock:
            return ts.team_amend(job, "đổi hướng")
    got = run(race_at_apply(r, ("synthesize",), amend_synth))
    task = ts.get_task(job)
    check("R7 tổng hợp: tổng hợp bản cũ không chốt bản 2; chốt NEW_SYNTH sau khi làm lại",
          got.get("reached") and got.get("action") == 2 and task["status"] == "done" and task["team_rev"] == 2
          and task["result"] == "NEW_SYNTH", (got, task["status"], task["result"], [c["role"] for c in calls]))

    # 5. Hoàn tất thắng trước: sửa yêu cầu sau khi việc đã xong bị từ chối (route trả 409).
    fn, calls = scripted(["DONE_FIRST"])
    r, tm, ts, ss, teams = world_n("r7-finish-first", fn)
    job = r.submit(teams[0]["team_id"], "Brief", as_job=True, client_msg_id="j")["task_id"]
    run(r.dispatch_once())
    with r.accept_lock:
        rev = ts.team_amend(job, "muộn")
    check("R7 hoàn tất thắng trước: sửa yêu cầu bị từ chối, việc giữ kết quả và bản 1",
          rev is None and ts.get_task(job)["result"] == "DONE_FIRST" and ts.get_task(job)["team_rev"] == 1)

    # 6. Huỷ ở cửa áp dụng: việc huỷ, không có kết quả, tin cũ thành bằng chứng.
    hits = []
    fn, calls = scripted(["LATE_PLAN"], hits)
    r, tm, ts, ss, teams = world_n("r7-cancel", fn)
    t = teams[0]
    job = r.submit(t["team_id"], "Brief", as_job=True, client_msg_id="j")["task_id"]
    run(race_at_apply(r, ("plan",), lambda: r.cancel_job(job)))
    task = ts.get_task(job)
    m = agent_msgs(ss, t)[0]
    check("R7 huỷ ở cửa áp dụng: việc huỷ, không chốt, tin thành bằng chứng late_cancelled, không ghi bài học",
          task["status"] == "cancelled" and task["result"] != "LATE_PLAN" and m["meta"]["applied"] is False
          and m["meta"]["status"] == "late_cancelled" and hits == [], (task["status"], m["meta"], hits))

    # 7. Bỏ thành viên ở cửa áp dụng (@ trực tiếp): không chốt, chặn assignee_removed.
    hits = []
    fn, calls = scripted(["LEFT_WORK"], hits)
    r, tm, ts, ss, teams = world_n("r7-left", fn, members=2)
    t = teams[0]
    job = r.submit(t["team_id"], "Brief", mentions=["agent-0-1"], as_job=True, client_msg_id="j")["task_id"]

    def remove():
        with r.accept_lock:
            return tm.remove_member(t["team_id"], "agent-0-1")
    run(race_at_apply(r, ("work",), remove))
    task = ts.get_task(job)
    check("R7 bỏ thành viên ở cửa áp dụng: không chốt, chặn assignee_removed, không ghi bài học",
          task["status"] == "team_blocked" and task["block_kind"] == "assignee_removed" and hits == [], (task, hits))

    # 8. Đổi trưởng nhóm ở cửa áp dụng (bước lập kế hoạch): kế hoạch cũ không chốt, trưởng nhóm mới điều phối.
    fn, calls = scripted(["OLD_LEADER_PLAN", "NEW_LEADER_PLAN"])
    r, tm, ts, ss, teams = world_n("r7-leader", fn, members=2)
    t = teams[0]
    job = r.submit(t["team_id"], "Brief", as_job=True, client_msg_id="j")["task_id"]

    def swap():
        with r.accept_lock:
            return tm.set_leader(t["team_id"], "agent-0-1")
    run(race_at_apply(r, ("plan",), swap))
    task = ts.get_task(job)
    check("R7 đổi trưởng nhóm ở cửa áp dụng: kế hoạch cũ không chốt, trưởng nhóm mới chốt",
          task["status"] == "done" and task["result"] == "NEW_LEADER_PLAN"
          and calls[-1]["agent_key"] == "agent-0-1", (task["status"], task["result"]))

    # 9. CAS ở kho: chốt bằng bản cũ bị từ chối dù không qua khoá của bộ chạy.
    r, tm, ts, ss, teams = world_n("r7-cas", scripted([])[0])
    job = r.submit(teams[0]["team_id"], "Brief", as_job=True, client_msg_id="j")["task_id"]
    ts.claim_team_next(teams[0]["team_id"], "w")
    ts.team_amend(job, "bản 2")
    try:
        stale = ts.team_finish(job, "OLD", expected_rev=1)
    except TypeError as ex:
        stale = f"thiếu API: {ex}"
    check("R7 CAS kho: team_finish(expected_rev=1) khi đã bản 2 không chốt", stale is None
          and ts.get_task(job)["status"] == "team_running", stale)
    try:
        fresh = ts.team_finish(job, "NEW", expected_rev=2)
    except TypeError as ex:
        fresh = f"thiếu API: {ex}"
    check("R7 CAS kho đối chứng: đúng bản thì chốt", fresh == "team_running" and ts.get_task(job)["result"] == "NEW",
          fresh)


def section_r8():
    async def pool_case(concurrent):
        release = asyncio.Event()
        calls = []

        async def fn(req):
            calls.append(req["team_id"])
            await release.wait()
            return {"text": "OK"}
        r, tm, ts, ss, teams = world_n("r8-race" if concurrent else "r8-seq", fn, count=4)
        r.max_parallel_teams = 2
        for t in teams:
            r.submit(t["team_id"], "Một việc", as_job=True, client_msg_id="j")
        if concurrent:
            barrier = threading.Barrier(2)
            original = r._claim_batch

            def gated(*a):
                barrier.wait(timeout=WAIT)
                return original(*a)
            with patch.object(r, "_claim_batch", side_effect=gated):
                await asyncio.wait_for(asyncio.gather(r.dispatch_once(wait=False), r.dispatch_once(wait=False)), 20)
        else:
            await r.dispatch_once(wait=False)
            await r.dispatch_once(wait=False)
        for _ in range(500):
            if len(calls) >= len([j for j in r._jobs.values() if not j.done()]):
                break
            await asyncio.sleep(0.01)
        # Model đang chạy: khoá pool KHÔNG bị giữ qua engine.
        lock = getattr(r, "_pool_lock", None)
        free = lock.acquire(blocking=False) if lock is not None else None
        if free:
            lock.release()
        res = {"jobs": len(r._jobs), "running": len(ts.team_running_tasks()), "calls": len(calls),
               "pool_lock_free": free}
        release.set()
        await asyncio.wait_for(r.wait_jobs(), 20)
        for _ in range(3):   # chạy hết hai việc còn lại, mỗi lượt tối đa 2
            await asyncio.wait_for(r.dispatch_once(), 20)
        res["done"] = sum(1 for t in teams for x in ts.team_history(t["team_id"]) if x["status"] == "done") \
            if hasattr(ts, "team_history") else None
        res["pool_left"] = len(getattr(r, "_pool", {}) or {})
        return res

    race = run(pool_case(True))
    seq = run(pool_case(False))
    check("R8 hai dispatch đồng thời, bốn nhóm, trần 2: chỉ 2 việc chạy, 2 lời gọi engine",
          race["calls"] == 2 and race["running"] == 2 and race["jobs"] == 2, race)
    check("R8 đối chứng tuần tự: 2 việc chạy", seq["calls"] == 2 and seq["running"] == 2, seq)
    check("R8 khoá pool không bị giữ trong lúc model chạy", race["pool_lock_free"] is True, race)
    check("R8 sau khi xong: pool trả hết chỗ", race["pool_left"] == 0 and seq["pool_left"] == 0, (race, seq))

    # Lỗi giữa chừng khi nhận việc: việc đã nhận trong lượt về lại hàng, không rò chỗ; lượt sau nhận đủ 2.
    async def error_case():
        async def fn(req):
            return {"text": "OK"}
        r, tm, ts, ss, teams = world_n("r8-error", fn, count=3)
        r.max_parallel_teams = 2
        for t in teams:
            r.submit(t["team_id"], "Một việc", as_job=True, client_msg_id="j")
        original = r.start_job_steps
        n = {"c": 0}

        def flaky(task_id):
            n["c"] += 1
            if n["c"] == 2:
                raise sqlite3.OperationalError("database is locked")
            return original(task_id)
        err = None
        with patch.object(r, "start_job_steps", side_effect=flaky):
            try:
                await r.dispatch_once(wait=False)
            except sqlite3.OperationalError as ex:
                err = str(ex)
        state = {"err": err, "running": len(ts.team_running_tasks()), "jobs": len(r._jobs),
                 "pool": len(getattr(r, "_pool", {}) or {})}
        await r.dispatch_once()
        state["after_running_done"] = sum(1 for t in teams for x in ts.team_history(t["team_id"])
                                          if x["status"] == "done")
        return state
    st = run(error_case())
    check("R8 lỗi giữa lúc nhận việc: lỗi nổi lên, không việc nào kẹt team_running, không giữ chỗ",
          st["err"] and st["running"] == 0 and st["jobs"] == 0 and st["pool"] == 0, st)
    check("R8 sau lỗi: lượt điều phối kế tiếp nhận đủ 2 việc và chạy xong", st["after_running_done"] == 2, st)

    # Huỷ (lặp) dispatch khi luồng phụ đang nhận việc: việc vừa nhận về hàng, không rò chỗ, không nhận trùng.
    async def cancel_case():
        async def fn(req):
            return {"text": "OK"}
        r, tm, ts, ss, teams = world_n("r8-cancel", fn, count=2)
        r.max_parallel_teams = 2
        for t in teams:
            r.submit(t["team_id"], "Một việc", as_job=True, client_msg_id="j")
        inside, go = threading.Event(), threading.Event()
        original = ts.claim_team_next

        def slow_claim(*a, **k):
            out = original(*a, **k)
            inside.set()
            go.wait(WAIT)
            return out
        with patch.object(ts, "claim_team_next", side_effect=slow_claim):
            d = asyncio.ensure_future(r.dispatch_once(wait=False))
            await asyncio.to_thread(inside.wait, WAIT)
            d.cancel()
            await asyncio.sleep(0)
            d.cancel()
            go.set()
            try:
                await asyncio.wait_for(d, 20)
                how = "finished"
            except asyncio.CancelledError:
                how = "cancelled"
        state = {"how": how, "running": len(ts.team_running_tasks()), "jobs": len(r._jobs),
                 "pool": len(getattr(r, "_pool", {}) or {}),
                 "queued": sum(len(ts.team_queue(t["team_id"])["waiting"]) for t in teams)}
        await r.dispatch_once()
        state["done"] = sum(1 for t in teams for x in ts.team_history(t["team_id"]) if x["status"] == "done")
        return state
    st = run(cancel_case())
    check("R8 huỷ lặp khi đang nhận việc: việc về hàng chờ, không team_running mồ côi, không giữ chỗ",
          st["how"] == "cancelled" and st["running"] == 0 and st["jobs"] == 0 and st["pool"] == 0
          and st["queued"] == 2, st)
    check("R8 sau huỷ: điều phối kế tiếp chạy xong cả hai, mỗi việc một lần", st["done"] == 2, st)


def section_r9():
    import importlib
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "tools"))
    RT = importlib.import_module("team_chat_restore_pre")

    def fixture(label, *, conversations_absent=False):
        d = TEMP / f"r9-{label}"
        d.mkdir()
        for name, table, marker in RT.STORES:
            for suffix in ("", RT.SNAPSHOT_SUFFIX):
                if suffix == "" and conversations_absent and name == "conversations.db":
                    continue
                db = sqlite3.connect(d / (name + suffix))
                db.execute(f"CREATE TABLE {table}(id INTEGER PRIMARY KEY" + (f", {marker} TEXT" if not suffix else "") + ")")
                db.execute(f"INSERT INTO {table}(id) VALUES (?)", (2 if not suffix else 1,))
                db.commit()
                db.close()
        db = sqlite3.connect(d / RT.TEAM_STORE)
        db.execute("CREATE TABLE evidence(id INTEGER)")
        db.execute("INSERT INTO evidence VALUES(2)")
        db.commit()
        db.close()
        return d

    def live(d):
        out = {}
        for name, table, _ in RT.STORES:
            p = d / name
            if not p.exists():
                out[name] = None
                continue
            db = sqlite3.connect(p)
            out[name] = db.execute(f"SELECT id FROM {table}").fetchone()[0]
            db.close()
        out["team"] = (d / RT.TEAM_STORE).exists()
        return out

    def posts(d):
        return sorted(p.name.split(".post-")[0] for p in d.iterdir() if ".post-0.140.0-" in p.name)

    original = RT._backup

    def after_write(target):
        def fake(src, dst):
            original(src, dst)
            if src.name == target + RT.SNAPSHOT_SUFFIX:
                raise sqlite3.OperationalError("injected disk I/O error after backup")
        return fake

    pre_state = {"kanban.sqlite3": 2, "conversations.db": 2, "team": True}
    for target in ("kanban.sqlite3", "conversations.db"):
        d = fixture(f"after-{target}")
        with patch.object(RT, "_backup", side_effect=after_write(target)):
            res = RT.restore(str(d))
        check(f"R9 lỗi SAU khi ghi {target}: ok=false, cả ba kho về đúng trước khi khôi phục, giữ bản sao",
              res["ok"] is False and live(d) == pre_state
              and posts(d) == ["conversations.db", "kanban.sqlite3", "team.sqlite3"], (res, live(d), posts(d)))
        d = fixture(f"before-{target}")
        res = RT.restore(str(d), _fail_on=target)
        check(f"R9 lỗi TRƯỚC khi ghi {target}: ok=false, cả ba kho về đúng trước khi khôi phục",
              res["ok"] is False and live(d) == pre_state, (res, live(d)))

    # Gỡ kho nhóm hỏng giữa chừng.
    d = fixture("team-remove")
    orig_remove = RT._remove_db
    seen = {"n": 0}

    def flaky_remove(path):
        if path.name == RT.TEAM_STORE and seen["n"] == 0:
            seen["n"] += 1
            raise PermissionError("file đang bị khoá")
        return orig_remove(path)
    with patch.object(RT, "_remove_db", side_effect=flaky_remove):
        res = RT.restore(str(d))
    check("R9 lỗi khi gỡ kho nhóm: ok=false, cả ba kho về đúng trước khi khôi phục",
          res["ok"] is False and live(d) == pre_state, (res, live(d)))

    # Đích vốn không có (kho phiên chưa từng có, chỉ có snapshot): hỏng sau khi ghi thì gỡ lại, không để lẫn.
    d = fixture("absent", conversations_absent=True)
    with patch.object(RT, "_backup", side_effect=after_write("conversations.db")):
        res = RT.restore(str(d))
    check("R9 đích vốn không có, lỗi sau khi ghi: kho đó lại không có, hai kho kia về đúng",
          res["ok"] is False and live(d) == {"kanban.sqlite3": 2, "conversations.db": None, "team": True},
          (res, live(d)))
    d = fixture("absent-control", conversations_absent=True)
    res = RT.restore(str(d))
    check("R9 đối chứng đích vốn không có: khôi phục tạo kho từ snapshot, cả bộ về bản trước nâng",
          res["ok"] and live(d) == {"kanban.sqlite3": 1, "conversations.db": 1, "team": False}, (res, live(d)))

    # Không trả về được: báo rõ kho và bản sao, không nói đã trả về.
    d = fixture("unrecoverable")

    def broken(src, dst):
        if ".post-0.140.0-" in src.name and dst.name == "conversations.db":
            raise OSError("không đọc được bản sao")
        original(src, dst)
        if src.name == "conversations.db" + RT.SNAPSHOT_SUFFIX:
            raise sqlite3.OperationalError("injected disk I/O error after backup")
    with patch.object(RT, "_backup", side_effect=broken):
        res = RT.restore(str(d))
    bad = res.get("unrecoverable") or []
    check("R9 không trả về được: báo rõ kho, lý do và đường dẫn bản sao; bản sao còn nguyên",
          res["ok"] is False and [Path(b["store"]).name for b in bad] == ["conversations.db"]
          and "KHÔNG trả về được" in res["error"] and Path(bad[0]["copy"]).is_file()
          and "conversations.db" not in res["error"].split("đã trả về bản trước khi khôi phục: ")[-1].split(";")[0],
          res)

    d = fixture("control")
    res = RT.restore(str(d))
    check("R9 đối chứng không lỗi: cả bộ về bản trước nâng, gỡ kho nhóm",
          res["ok"] and live(d) == {"kanban.sqlite3": 1, "conversations.db": 1, "team": False}, (res, live(d)))


# Mỗi nhóm chạy riêng: một nhóm văng lỗi (vd. mã cũ thiếu API) thành FAIL của nhóm đó, không che nhóm khác.
for _name, _fn in (("R1", section_r1), ("R2", section_r2), ("R3", section_r3), ("R4", section_r4), ("R5", section_r5),
                   ("R7", section_r7), ("R8", section_r8), ("R9", section_r9)):
    try:
        _fn()
    except Exception as _ex:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        check(f"{_name} chạy hết nhóm kiểm", False, f"{type(_ex).__name__}: {_ex}")

print(f"\n{'FAIL' if fails else 'PASS'} - test_team_t1_review: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
