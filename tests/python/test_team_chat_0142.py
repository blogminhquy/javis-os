"""0.142.0: chat nhóm không còn im lặng.

Hai lỗi gốc (biên bản docs/dev/team-chat-0142.md):
1. Lượt nhóm dựng engine bằng hợp đồng Cộng hưởng (`_resonance_engine`: model VIỆC NỀN, chỉ nhận Claude và engine API).
   Máy để Codex làm model việc nền thì mọi lượt bị chặn trước khi gọi model.
2. `run_replies` bỏ kết cục lỗi đi: không một dòng nào hiện trong khung chat.

Ở đây kiểm: hợp đồng chat tương tác (`team_engine`) chọn model của trợ lý rồi tới model chính, Codex chạy chỉ chữ với rào
`read-only` kể cả khi máy tắt sandbox, kết cục từng lượt trả lời lưu bền (chờ, đang trả lời, xong, lỗi kèm lý do), Thử
lại không nhân đôi tin, lượt hay kết quả, và khởi động lại không để lượt nào quay mãi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-0142-")
TEMP = Path(tempfile.mkdtemp(prefix="javis-team-0142-w-"))

import aux_engine  # noqa: E402
import main  # noqa: E402
import sessions  # noqa: E402
import task_store  # noqa: E402
import team_engine  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.run(coro)


# ───────────── 1. chọn model: trợ lý trước, rồi model chính; KHÔNG model việc nền ─────────────

OK = lambda sp: (True, "")  # noqa: E731
resolve = main._agent_model_provider
MAIN = {"provider": "anthropic-cli", "model": "opus"}

sp = team_engine.choose_spec("gpt-5.5", "openai-oauth", MAIN, resolve, OK)
check("model riêng của trợ lý (Codex) được dùng", sp["provider"] == "openai-oauth" and sp["model"] == "gpt-5.5"
      and sp["source"] == "agent" and not sp["note"], sp)
sp = team_engine.choose_spec("", "", MAIN, resolve, OK)
check("trợ lý không đặt model: theo model chính", sp["provider"] == "anthropic-cli" and sp["source"] == "main", sp)
sp = team_engine.choose_spec("deepseek-chat", "deepseek", MAIN, resolve,
                             lambda s: (False, "Chưa có API key") if s["provider"] == "deepseek" else (True, ""))
check("model riêng chưa cấu hình được: theo model chính, kèm ghi chú vì sao",
      sp["provider"] == "anthropic-cli" and sp["source"] == "main" and "Chưa có API key" in sp["note"], sp)

# Máy để Codex làm model VIỆC NỀN, model chính Claude: lượt nhóm theo model chính, không bị chặn bởi hợp đồng Cộng hưởng.
SETTINGS = {"model": {"main": {"provider": "anthropic-cli", "model": "sonnet"},
                      "auxiliary": {"provider": "openai-oauth", "model": "gpt-5.5"}}}
INFO = {"agent-one": {"slug": "one", "name": "One", "system": "You are One.", "model": "", "model_provider": ""},
        "agent-two": {"slug": "two", "name": "Two", "system": "You are Two.", "model": "", "model_provider": ""},
        "agent-dup": {"slug": "one-2", "name": "One", "system": "You are One too.", "model": "gpt-5.5",
                      "model_provider": "openai-oauth"}}


def ident(root, key):
    return INFO.get(key)


with patch.object(main.cfgmod, "read_settings", return_value=SETTINGS), \
        patch.object(main, "_team_agent_info", side_effect=ident), \
        patch.object(main, "_resonance_engine", side_effect=AssertionError("không được đi qua hợp đồng Cộng hưởng")), \
        patch.object(aux_engine, "availability", return_value=(True, "")):
    prov, model, fn = main._team_engine_for({"brain_id": "b", "team_id": "tm_x"}, "agent-one", "leader_reply")
    check("model việc nền là Codex: lượt nhóm KHÔNG dùng model việc nền, chạy model chính",
          prov == "anthropic-cli" and model == "sonnet", (prov, model))
    prov, model, fn = main._team_engine_for({"brain_id": "b", "team_id": "tm_x"}, "agent-dup", "leader_reply")
    check("trợ lý có model Codex riêng: lượt nhóm chạy Codex của trợ lý", prov == "openai-oauth" and model == "gpt-5.5",
          (prov, model))

# ───────────── 2. dựng engine chỉ chữ theo provider ─────────────


class Base:
    def __init__(self):
        self.allowed_tools = ["javis_reply_policy_khong_cong_cu"]
        self.system_prompt = "SYS"
        self.cwd = str(TEMP / "team_cwd")
        self.model = None


eng = team_engine.build({"provider": "anthropic-cli", "model": "haiku"}, Base(), "team-x", {})
check("Claude: dùng engine hộp cát có cổng chặn công cụ, đúng model", eng.allowed_tools and eng.model == "haiku")
b = Base()
b.allowed_tools = []
try:
    team_engine.build({"provider": "anthropic-cli", "model": ""}, b, "team-x", {})
    check("Claude không có cổng chặn công cụ: từ chối", False)
except team_engine.TeamEngineUnavailable:
    check("Claude không có cổng chặn công cụ: từ chối", True)

old = os.environ.get("JAVIS_CODEX_SANDBOX")
os.environ["JAVIS_CODEX_SANDBOX"] = "off"
try:
    with patch.object(aux_engine, "availability", return_value=(True, "")):
        cc = team_engine.build({"provider": "openai-oauth", "model": "gpt-5.5"}, Base(), "team-x", {})
    args = cc._build_args()
finally:
    if old is None:
        os.environ.pop("JAVIS_CODEX_SANDBOX", None)
    else:
        os.environ["JAVIS_CODEX_SANDBOX"] = old
check("Codex: luôn --sandbox read-only, kể cả khi máy đặt JAVIS_CODEX_SANDBOX=off",
      "--sandbox" in args and args[args.index("--sandbox") + 1] == "read-only"
      and "--dangerously-bypass-approvals-and-sandbox" not in args, args)
check("Codex: không profile (hub), MCP rỗng, tắt web search và công cụ native",
      "-p" not in args and "mcp_servers={}" in args and 'web_search="disabled"' in args
      and all(f"features.{f}=false" in args for f in ("shell_tool", "unified_exec", "view_image", "multi_agent",
                                                       "image_generation", "computer_use", "browser_use")), args)
check("Codex: lời nhắc của trợ lý đi kèm, model của trợ lý", cc.instructions == "SYS" and cc.model == "gpt-5.5")

with patch.object(aux_engine, "availability", return_value=(True, "")):
    api = team_engine.build({"provider": "openrouter", "model": "x/y"}, Base(), "team-x", {})
check("engine API: no_tools, mức suggest, không vault", api.no_tools is True and api.javis_mode == "suggest"
      and api.vault_root is None)
for prov in ("grok-cli", "antigravity-cli"):
    try:
        with patch.object(aux_engine, "availability", return_value=(True, "")):
            team_engine.build({"provider": prov, "model": ""}, Base(), "team-x", {})
        check(f"{prov}: chưa có cơ chế chỉ chữ, báo rõ thay vì chạy", False)
    except team_engine.TeamEngineUnavailable as ex:
        check(f"{prov}: chưa có cơ chế chỉ chữ, báo rõ thay vì chạy", prov in ex.reason and "Cộng sự" in ex.reason)
try:
    with patch.object(aux_engine, "availability", return_value=(False, "Chưa cài Codex CLI")):
        team_engine.build({"provider": "openai-oauth", "model": ""}, Base(), "team-x", {})
    check("provider chưa sẵn sàng: lý do đi ra ngoài", False)
except team_engine.TeamEngineUnavailable as ex:
    check("provider chưa sẵn sàng: lý do đi ra ngoài", "Chưa cài Codex CLI" in ex.reason)

# ───────────── 3. kết cục lượt trả lời: hiện trong chat, lưu bền, Thử lại không nhân đôi ─────────────

_n = [0]


def world(label, engine_for, agents=("agent-one", "agent-two", "agent-dup")):
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}-{label}"
    (d / "agents").mkdir(parents=True)
    ss = sessions.SessionStore(db_path=d / "chat.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    tid = team_store.new_team_id()
    sid = ss.create_session(brain=str(d), channel=f"team:{tid}")
    tm.create_team(str(d), label, "", sid, team_id=tid)
    for k in agents:
        tm.add_member(tid, k, INFO[k]["slug"])
    tm.set_leader(tid, agents[0])
    events = []
    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=engine_for, agent_info=ident,
                      publish=events.append)
    return r, tm, ts, ss, tm.get(tid), events


class Script:
    """engine_for giả: mỗi lượt lấy một hành vi trong `plan` theo agent ("ok", "unavailable", "error")."""

    def __init__(self, plan):
        self.plan = {k: list(v) for k, v in plan.items()}
        self.calls = []

    def __call__(self, team, key, role):
        async def run_(req):
            act = (self.plan.get(key) or ["ok"]).pop(0) if self.plan.get(key) else "ok"
            if act == "unavailable":
                raise TR.EngineUnavailable("engine openai-oauth chưa sẵn sàng (kiểm tra trang Models)")
            await req["engine_started"]()
            self.calls.append((key, role))
            if act == "error":
                raise TR.EngineOutcomeError("final_error", "rate limit")
            return {"text": f"{key} trả lời"}
        run_.marks_engine = True
        return "openai-oauth", "gpt-5.5", run_


def replies(tm, t, mid):
    return {x["agent_key"]: x for x in tm.replies_of(t["team_id"], mid)}


def agent_msgs(ss, t):
    return [m for m in ss.get_team_messages_page(t["session_id"], limit=200)["messages"] if m["author_kind"] == "agent"]


# Tin thường: đúng MỘT lượt, của người điều phối.
eng = Script({})
r, tm, ts, ss, t, ev = world("plain", eng)
sub = r.submit(t["team_id"], "Chào cả nhóm", client_msg_id="p1")
check("tin thường gọi đúng một người điều phối", sub["replies"] == ["agent-one"], sub)
check("lượt trả lời ghi 'queued' ngay khi gửi (tải lại vẫn thấy đang chờ)",
      replies(tm, t, sub["message_id"])["agent-one"]["status"] == "queued")
run(r.run_replies(sub))
rp = replies(tm, t, sub["message_id"])["agent-one"]
check("xong: status done, trỏ đúng tin trả lời, ghi engine thật", rp["status"] == "done" and rp["result_msg_id"]
      and rp["engine"] == "openai-oauth" and rp["model"] == "gpt-5.5", rp)
seen = [e for e in ev if e.get("type") == "team_replies"]
check("đẩy trạng thái qua WS: chờ, đang trả lời, xong",
      [x["replies"][0]["status"] for x in seen][:1] == ["queued"]
      and any(x["replies"][0]["status"] == "running" and x["replies"][0]["reason"] == "answering" for x in seen)
      and seen[-1]["replies"][0]["status"] == "done", [x["replies"][0]["status"] for x in seen])

# @ hai người trùng tên: gọi đúng người theo agent_key.
eng = Script({})
r, tm, ts, ss, t, ev = world("dup", eng)
sub = r.submit(t["team_id"], "@One ơi", mentions=["agent-dup"], client_msg_id="d1")
run(r.run_replies(sub))
check("@ trùng tên: chỉ đúng agent_key được @ trả lời", sub["replies"] == ["agent-dup"]
      and [m["author_ref"] for m in agent_msgs(ss, t)] == ["agent-dup"] and eng.calls == [("agent-dup", "member_reply")])

# Lỗi dựng engine (ca Codex cũ) và lỗi engine: hiện trong chat với lý do; lượt sau vẫn chạy.
eng = Script({"agent-one": ["unavailable"], "agent-two": ["error"]})
r, tm, ts, ss, t, ev = world("errors", eng)
sub = r.submit(t["team_id"], "Hai bạn ơi", mentions=["agent-one", "agent-two", "agent-dup"], client_msg_id="e1")
outs = run(r.run_replies(sub))
rp = replies(tm, t, sub["message_id"])
check("lỗi dựng engine: error, lý do engine_unavailable, chi tiết đi kèm",
      rp["agent-one"]["status"] == "error" and rp["agent-one"]["reason"] == "engine_unavailable"
      and "chưa sẵn sàng" in rp["agent-one"]["detail"], rp["agent-one"])
check("lỗi engine sau khi gọi model: error, lý do engine", rp["agent-two"]["status"] == "error"
      and rp["agent-two"]["reason"] == "engine" and "rate limit" in rp["agent-two"]["detail"], rp["agent-two"])
check("một lượt lỗi không làm mất lượt sau", rp["agent-dup"]["status"] == "done" and len(outs) == 3)
turns_before = len(tm.turns(t["team_id"]))
owner_before = [m for m in ss.get_team_messages_page(t["session_id"], limit=200)["messages"]
                if m["author_kind"] == "owner"]

# Thử lại: một lượt mới, không thêm tin của chủ nhóm; bấm lặp không làm gì.
s1 = r.retry_reply(t["team_id"], sub["message_id"], "agent-one")
s2 = r.retry_reply(t["team_id"], sub["message_id"], "agent-one")
check("Thử lại: lần bấm thứ hai khi lượt đang chờ không tạo lượt nào", s1 is not None and s2 is None)
run(r.run_replies(s1))
rp = replies(tm, t, sub["message_id"])
owner_after = [m for m in ss.get_team_messages_page(t["session_id"], limit=200)["messages"]
               if m["author_kind"] == "owner"]
check("Thử lại xong: done, attempt=2, đúng một tin trả lời mới, không thêm tin của chủ",
      rp["agent-one"]["status"] == "done" and rp["agent-one"]["attempt"] == 2
      and [m["author_ref"] for m in agent_msgs(ss, t)].count("agent-one") == 1
      and len(owner_after) == len(owner_before) == 1, rp["agent-one"])
check("Thử lại chỉ thêm đúng một lượt model", len(tm.turns(t["team_id"])) == turns_before + 1)
check("lượt đã xong không Thử lại được", r.retry_reply(t["team_id"], sub["message_id"], "agent-one") is None
      and r.retry_reply(t["team_id"], sub["message_id"], "agent-dup") is None)
run(r.run_replies(dict(sub)))
check("chạy lại cùng tin (gửi lại sau rớt mạng) không thêm lượt hay kết quả",
      len(tm.turns(t["team_id"])) == turns_before + 1 and len(agent_msgs(ss, t)) == 2)
# Gửi lại đúng client_msg_id: không ghi tin mới, không lượt mới.
again = r.submit(t["team_id"], "Hai bạn ơi", mentions=["agent-one"], client_msg_id="e1")
check("gửi lại cùng client_msg_id: trả tin cũ, không có lượt", again["created"] is False and again["replies"] == [])

# Nhóm tạm dừng: không im lặng, ghi lỗi có lý do.
eng = Script({})
r, tm, ts, ss, t, ev = world("paused", eng)
tm.update(t["team_id"], status="paused")
sub = r.submit(t["team_id"], "Có ai không", client_msg_id="z1")
rp = replies(tm, t, sub["message_id"])
check("nhóm tạm dừng: lượt ghi lỗi team_paused, không chạy model",
      rp["agent-one"]["status"] == "error" and rp["agent-one"]["reason"] == "team_paused" and eng.calls == [], rp)

# Khởi động lại giữa chừng: lượt queued/running thành lỗi `restart`, có Thử lại, không quay mãi.
eng = Script({})
r, tm, ts, ss, t, ev = world("restart", eng)
sub = r.submit(t["team_id"], "Chào", mentions=["agent-one", "agent-two"], client_msg_id="r1")
tm.claim_reply(t["team_id"], sub["message_id"], "agent-one")
r2 = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=eng, agent_info=ident)
r2.recover()
rp = replies(tm, t, sub["message_id"])
check("restart: đang chờ và đang trả lời đều thành lỗi 'restart'",
      all(rp[k]["status"] == "error" and rp[k]["reason"] == "restart" for k in ("agent-one", "agent-two")), rp)
s = r2.retry_reply(t["team_id"], sub["message_id"], "agent-two")
run(r2.run_replies(s))
check("restart rồi Thử lại: chạy đúng một lượt", replies(tm, t, sub["message_id"])["agent-two"]["status"] == "done"
      and eng.calls == [("agent-two", "member_reply")])

# Trang tin trả kèm kết cục (tải lại trang không mất dấu): đọc thẳng kho như route.
got = tm.replies_for(t["team_id"], [sub["message_id"]])
check("replies_for trả kết cục theo tin", [x["agent_key"] for x in got[sub["message_id"]]] == ["agent-one", "agent-two"])

# Việc nền bị chặn: lỗi hiện trong khung chat (tin hệ thống), không chỉ ở hộp thư.
eng = Script({"agent-one": ["error"]})
r, tm, ts, ss, t, ev = world("job", eng)
job = r.submit(t["team_id"], "Viết tóm tắt", mentions=["agent-one"], as_job=True, client_msg_id="j1")["task_id"]
run(r.dispatch_once())
sysm = [m for m in ss.get_team_messages_page(t["session_id"], limit=200)["messages"]
        if m["author_kind"] == "system" and (m.get("meta") or {}).get("kind") == "job_blocked"]
check("việc bị chặn: có tin hệ thống trong chat kèm lý do", ts.get_task(job)["status"] == "team_blocked"
      and len(sysm) == 1 and "rate limit" in sysm[0]["content"] and sysm[0]["task_id"] == job, sysm)

# ───────────── review 0.142.0 ─────────────
# #3: lượt cũ về muộn không ghi đè kết cục của lần thử mới.
eng = Script({})
r, tm, ts, ss, t, ev = world("stale", eng)
sub = r.submit(t["team_id"], "Chào", client_msg_id="s1")
att1 = tm.claim_reply(t["team_id"], sub["message_id"], "agent-one")
tm.interrupt_open_replies()                          # tiến trình mới coi lượt đang chạy là dở
again = r.retry_reply(t["team_id"], sub["message_id"], "agent-one")
late = tm.settle_reply(t["team_id"], sub["message_id"], "agent-one", "done", attempt=att1, result_msg_id=999)
rp = replies(tm, t, sub["message_id"])["agent-one"]
check("review #3: lượt cũ (attempt 1) về muộn không ghi đè lần thử 2", att1 == 1 and again is not None and late is False
      and rp["status"] == "queued" and rp["attempt"] == 2 and rp["result_msg_id"] is None, rp)
# #3: phục hồi chỉ đụng lượt của tiến trình trước, không đụng lượt vừa gửi trong tiến trình này.
eng = Script({})
r, tm, ts, ss, t, ev = world("scoped", eng)
sub = r.submit(t["team_id"], "Chào", client_msg_id="s2")
r3 = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=eng, agent_info=ident)
r3.started_at = 0.0                                  # mốc khởi động cũ hơn mọi lượt: không có lượt "của tiến trình trước"
r3.recover()
check("review #3: lượt gửi sau mốc khởi động không bị đánh 'restart'",
      replies(tm, t, sub["message_id"])["agent-one"]["status"] == "queued")
# #4: bị huỷ giữa chừng: lượt chưa chạy phía sau cũng thành lỗi có Thử lại.


class Hang:
    def __call__(self, team, key, role):
        async def run_(req):
            await req["engine_started"]()
            await asyncio.sleep(30)
            return {"text": "x"}
        run_.marks_engine = True
        return "fake", "m", run_


r, tm, ts, ss, t, ev = world("cancel", Hang())
sub = r.submit(t["team_id"], "Hai bạn", mentions=["agent-one", "agent-two"], client_msg_id="c1")


async def cancel_mid():
    task = asyncio.ensure_future(r.run_replies(sub))
    for _ in range(100):
        await asyncio.sleep(0.02)
        if replies(tm, t, sub["message_id"])["agent-one"]["reason"] == "answering":
            break
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
run(cancel_mid())
rp = replies(tm, t, sub["message_id"])
check("review #4: huỷ giữa chừng: lượt đang chạy và lượt chưa chạy đều thành lỗi có Thử lại",
      rp["agent-one"]["status"] == "error" and rp["agent-two"]["status"] == "error"
      and rp["agent-two"]["reason"] == "interrupted", rp)
# #4: lượt kẹt ở "đang chờ" quá lâu thì Thử lại được; chưa quá lâu thì không.
eng = Script({})
r, tm, ts, ss, t, ev = world("stuck", eng)
sub = r.submit(t["team_id"], "Chào", client_msg_id="k1")
check("lượt mới chờ: chưa cho Thử lại", tm.retry_reply(t["team_id"], sub["message_id"], "agent-one") is None)
check("lượt chờ quá lâu: Thử lại được", tm.retry_reply(t["team_id"], sub["message_id"], "agent-one", stuck_after_s=-1)
      is not None)
# #2: quyền "Không giới hạn" cấp trước 0.142.0 không nới sang lượt chạy model chính.
r, tm, ts, ss, t, ev = world("grant", Script({}))
r.grant_authority(t["team_id"], {"caps": {"daily_turns": {"unlimited": True}}, "providers_unlimited": ["anthropic-cli"]})
check("quyền mới (providers_v=2) vẫn cho Không giới hạn với provider đã tích",
      r.effective_caps(t["team_id"], "anthropic-cli")["daily_turns"] is None)
import sqlite3 as _sq  # noqa: E402
with _sq.connect(str(tm.path)) as c:
    g = json.loads(c.execute("SELECT grant_json FROM team_authority WHERE team_id=?", (t["team_id"],)).fetchone()[0])
    g.pop("providers_v", None)
    c.execute("UPDATE team_authority SET grant_json=? WHERE team_id=?", (json.dumps(g), t["team_id"]))
check("review #2: quyền cũ (không providers_v) không cho provider nào Không giới hạn",
      r.effective_caps(t["team_id"], "anthropic-cli")["daily_turns"] == t["caps"]["daily_turns"])

print(("FAIL" if fails else "PASS") + f" - test_team_chat_0142: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
