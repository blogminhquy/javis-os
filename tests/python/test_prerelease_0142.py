"""0.142.0, rà soát trước khi phát hành (docs/dev/team-chat-0142.md, mục "Rà soát trước khi phát hành").

- Ghim phiên của tab Công việc và huy hiệu việc đọc MỘT lần cho mọi phiên (trước: một kết nối mỗi phiên, 15 giây với 20
  trợ lý x 150 phiên trên Windows).
- Việc giao bằng nút Giao việc báo về phiên chưa lưu trữ, ưu tiên phiên đã có tin, đúng mã trợ lý.
- Trần 10 phút chỉ cho lượt trả lời chat; bước của việc nhóm có trần riêng rộng hơn.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-prerelease-0142-")
TEMP = Path(tempfile.mkdtemp(prefix="javis-prerelease-0142-w-"))

import agent_jobs  # noqa: E402
import resonance_store as RS  # noqa: E402
import sessions  # noqa: E402
import task_store  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:300]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ───────────── ghim phiên đọc một lần ─────────────
ss = sessions.SessionStore(TEMP / "chat.db")
gs = RS.GoalStore(TEMP / "resonance.sqlite3")
B = str(TEMP / "brain")
P = RS.Principal("owner", "owner", B)
(Path(B) / "agents").mkdir(parents=True)
(Path(B) / "agents" / "lan.md").write_text("---\nname: Lan\n---\nBạn là Lan.\n", encoding="utf-8")
key = gs.agent_register(P, "lan")["agent_key"]
sids = [ss.create_session(brain=B, engine="cli", channel="agent:lan") for _ in range(30)]
other = sids[3]
gs.session_agent(B, sids[0], "lan", 0)          # ghim đúng mã của Lan
import sqlite3  # noqa: E402
with sqlite3.connect(gs.path) as cx:            # phiên của trợ lý cũ cùng slug (mã khác)
    cx.execute("INSERT INTO session_agents(session_id,brain_id,agent_key,by,created_at) VALUES(?,?,?,?,?)",
               (other, B, "ag_khac", "host", 1.0))
pins = gs.session_pins(sids)
check("session_pins: một lần đọc ra đúng ghim của từng phiên", pins.get(sids[0]) == key and pins.get(other) == "ag_khac"
      and len(pins) == 2, pins)
calls = {"n": 0}
orig = gs.session_pin


def counted(sid):
    calls["n"] += 1
    return orig(sid)


gs.session_pin = counted
got = agent_jobs._chat_sessions(key, "lan", [B], ss, gs)
check("tab Công việc: không đọc ghim từng phiên một, vẫn loại phiên của mã khác", calls["n"] == 0 and len(got) == 29
      and other not in got and sids[0] in got, (calls, len(got)))
gs.session_pin = orig

# ───────────── phiên nhận báo cáo ─────────────
ss2 = sessions.SessionStore(TEMP / "chat2.db")
empty = ss2.create_session(brain=B, engine="cli", channel="agent:lan")
old = ss2.create_session(brain=B, engine="cli", channel="agent:lan")
ss2.append_message(old, "user", "chào")
arch = ss2.create_session(brain=B, engine="cli", channel="agent:lan")
ss2.append_message(arch, "user", "cũ")
ss2.archive(arch, True)
pick = agent_jobs.report_session(key, "lan", [B], ss2, gs)
check("báo cáo việc: phiên chưa lưu trữ đã có tin (không phải phiên trống, không phải phiên lưu trữ)", pick == old, pick)
ss3 = sessions.SessionStore(TEMP / "chat3.db")
only_empty = ss3.create_session(brain=B, engine="cli", channel="agent:lan")
check("chỉ có phiên trống: dùng phiên đó", agent_jobs.report_session(key, "lan", [B], ss3, gs) == only_empty)
ss4 = sessions.SessionStore(TEMP / "chat4.db")
check("chưa có phiên nào: None (người gọi mở phiên mới)", agent_jobs.report_session(key, "lan", [B], ss4, gs) is None)

# ───────────── trần thời gian: lượt chat 10 phút, bước việc nhóm rộng hơn ─────────────
check("trần mặc định: trả lời chat 600 giây, bước việc nhóm 3600 giây", TR.TURN_TIMEOUT_S == 600.0 and TR.STEP_TIMEOUT_S == 3600.0)
seen = {}


class Probe(TR.TeamRunner):
    pass


d = TEMP / "team"
d.mkdir()
tm = team_store.TeamStore(d / "team.sqlite3")
ts = task_store.TaskStore(d / "kanban.sqlite3")
sst = sessions.SessionStore(db_path=d / "chat.db")
tid = team_store.new_team_id()
sid = sst.create_session(brain=str(d), channel=f"team:{tid}")
tm.create_team(str(d), "T", "", sid, team_id=tid)
tm.add_member(tid, "ag_a", "a")
tm.set_leader(tid, "ag_a")


def slow(team, key_, role):
    async def run_(req):
        await req["engine_started"]()
        await asyncio.sleep(0.6)
        return {"text": "xong"}
    run_.marks_engine = True
    return "anthropic-cli", "haiku", run_


r = TR.TeamRunner(teams=tm, tasks=ts, sessions=sst, engine_for=slow,
                  agent_info=lambda root, k: {"slug": "a", "name": "A", "system": "S"}, publish=lambda e: None)
r.turn_timeout, r.step_timeout = 0.2, 5
out = asyncio.run(r._turn(tm.get(tid), "ag_a", "leader_reply", "chào"))
check("lượt trả lời chat dùng trần ngắn: quá hạn thành lỗi timeout", out.get("status") == "error" and out.get("reason") == "timeout",
      out)
out = asyncio.run(r._turn(tm.get(tid), "ag_a", "work", "làm việc"))
check("bước việc nhóm dùng trần riêng (rộng hơn): không bị cắt ở trần chat", out.get("status") != "error" or
      out.get("reason") != "timeout", out)

print()
if fails:
    print(f"ĐỎ {len(fails)} mục")
    raise SystemExit(1)
print("XANH")
