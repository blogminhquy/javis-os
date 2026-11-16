"""A chat turn a restart cut short answers again by itself (owner, 16/11/2026).

    python tests/python/test_chat_resume_after_restart.py      (no network, fake Claude engine over the real WebSocket)

Owner: "Những việc nào đang dang dở kể cả ở cộng sự, ở chat hay team và workflow, khởi động lại server sau khi update
cũng phải khởi động lại tất cả các tiến trình". Before this the question of a turn that was still answering when the
server stopped sat in the chat with no answer and no notice. Now the turn is on disk while it runs (turn_ledger.py) and
the first page back after the restart runs it again. It is not run again when it had already done something outside,
or when restarts cut the same question too many times: the chat then gets one stored line saying why.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-chat-resume-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-chat-resume-brains-")
os.environ.pop("JAVIS_RESUME_AFTER_RESTART", None)

import turn_ledger as TL  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:500] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


def old_boot(session_id=None):
    """Make rows look like they were written by a process that is gone."""
    if session_id:
        TL._conn().execute("UPDATE turns SET boot='gone' WHERE session_id=?", (session_id,))
    else:
        TL._conn().execute("UPDATE turns SET boot='gone'")
    TL._conn().commit()


# ---------- the ledger ----------
TL.configure(Path(tempfile.mkdtemp(prefix="javis-turn-ledger-")) / "turns.sqlite3")
TL.begin("s1", 11, "Câu hỏi 1", "câu 1", "brain")
TL.begin("s2", 21, "Câu hỏi 2", None, "brain")
check("a running turn is on disk with the exact text it was given", [(r["session_id"], r["user_mid"], r["user_message"], r["user_text"])
      for r in TL.rows()] == [("s1", 11, "Câu hỏi 1", "câu 1"), ("s2", 21, "Câu hỏi 2", None)], TL.rows())
check("turns of this process are not cut turns", TL.take_cut() == [])
TL.end("s2")
check("a turn that ended leaves nothing", [r["session_id"] for r in TL.rows()] == ["s1"])
TL.mark_acted("s1")
TL.mark_acted("nobody")
check("a turn that acted outside is marked; a session with no turn is ignored", [r["acted"] for r in TL.rows()] == [1])
old_boot()
cut = TL.take_cut()
check("after a restart the row is a cut turn, handed out with what it needs", len(cut) == 1 and cut[0]["session_id"] == "s1"
      and cut[0]["user_mid"] == 11 and cut[0]["acted"] == 1 and cut[0]["resumes"] == 0 and cut[0]["brain"] == "brain", cut)
check("it is handed out once: a second page gets nothing", TL.take_cut() == [])
TL.begin("s1", 11, "Câu hỏi 1", "câu 1", "brain")
check("the same question running again keeps its count of cuts and starts clean of the outside mark",
      [(r["resumes"], r["acted"]) for r in TL.rows()] == [(1, 0)], TL.rows())
old_boot()
check("a second cut reports one earlier resume", [r["resumes"] for r in TL.take_cut()] == [1])
TL.begin("s1", 12, "Câu khác", None, "brain")
check("a new question of the same chat starts from zero", [(r["user_mid"], r["resumes"]) for r in TL.rows()] == [(12, 0)], TL.rows())
TL.closing = True
TL.end("s1")
check("during shutdown a cancelled turn keeps its row for the next process", [r["session_id"] for r in TL.rows()] == ["s1"])
TL.closing = False
TL._conn().execute("UPDATE turns SET boot='gone', started_at=?", (time.time() - TL.MAX_AGE_S - 60,))
TL._conn().commit()
check("a cut turn too old to answer is dropped, not handed out", TL.take_cut() == [] and TL.rows() == [], TL.rows())
TL.begin("s3", 0, "tiếp tục việc nền", None, "brain")
TL.drop("s3")
check("drop forgets a row", TL.rows() == [])
os.environ["JAVIS_RESUME_AFTER_RESTART"] = "0"
check("the switch reads JAVIS_RESUME_AFTER_RESTART", TL.resume_on() is False)
os.environ.pop("JAVIS_RESUME_AFTER_RESTART", None)
check("and is on by default", TL.resume_on() is True)

# ---------- the runtime tells the host when a job is over ----------
over = []


async def jobs():
    rt = ChatRuntime()
    rt.on_finish = over.append

    async def quick():
        return 1

    async def slow():
        await asyncio.sleep(0.2)

    t1 = asyncio.create_task(quick())
    rt.register_job("a", t1, "tag-a")
    await asyncio.sleep(0.05)
    t2 = asyncio.create_task(slow())
    rt.register_job("b", t2, "tag-b-old")
    t3 = asyncio.create_task(slow())
    rt.register_job("b", t3, "tag-b-new")       # a newer turn of the same chat while the old one still runs
    t2.cancel()
    await asyncio.sleep(0.05)
    seen_while_new_runs = list(over)
    await t3
    await asyncio.sleep(0.05)
    return seen_while_new_runs

seen = asyncio.run(jobs())
check("a finished job reports its session", seen == ["a"], seen)
check("an old job ending under a newer one of the same chat does not close the newer turn's row", over == ["a", "b"], over)

# ---------- over the real WebSocket ----------
import main  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

TL.configure(Path(os.environ["JAVIS_STATE_DIR"]) / "turn_ledger.sqlite3")
main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
store = main.get_store()
CALLS = []
SCRIPT = {"turns": []}
HEAD = {"host": "127.0.0.1:7777", "origin": "http://127.0.0.1:7777"}


class FakeClaude:
    def __init__(self, **kw):
        self.system_prompt, self.model, self.session_id, self.effort = kw.get("system_prompt"), None, None, None
        self.mcp_config = None

    def reset_session(self):
        self.session_id = None

    def __getattr__(self, name):
        return None

    async def query(self, prompt):
        CALLS.append(prompt if isinstance(prompt, str) else str(prompt))
        for ev in (SCRIPT["turns"].pop(0) if SCRIPT["turns"] else []):
            yield dict(ev)


main.claude_engine = lambda **kw: FakeClaude(**kw)
main._apply_mcp = lambda *a, **k: None


def final(text):
    return {"type": "final", "content": text, "session_id": "cs-1", "tokens_in": 5, "tokens_out": 1, "cost_usd": 0}


def connect(wait_done=True, seconds=20):
    got = []
    with client.websocket_connect("/ws", headers=HEAD) as ws:
        ws.send_text(json.dumps({"action": "ping"}))
        t0 = time.time()
        while time.time() - t0 < seconds:
            m = json.loads(ws.receive_text())
            got.append(m)
            if m.get("type") == ("turn_done" if wait_done else "pong"):
                break
    return got


def cut_chat(text, acted=0, resumes=0, answered=False):
    sid = store.create_session(brain="brain", channel="web")
    mid = store.append_message(sid, "user", text)
    if answered:
        store.append_message(sid, "assistant", "Đã trả lời rồi.")
    TL.begin(sid, mid, text, text, "brain")
    TL._conn().execute("UPDATE turns SET boot='gone', acted=?, resumes=? WHERE session_id=?", (acted, resumes, sid))
    TL._conn().commit()
    return sid


def last(sid):
    return (store.get_messages(sid) or [{}])[-1]


# A normal turn leaves no row behind.
sid = store.create_session(brain="brain", channel="web")
SCRIPT["turns"] = [[{"type": "text", "content": "Chào anh."}, final("Chào anh.")]]
with client.websocket_connect("/ws", headers=HEAD) as ws:
    ws.send_text(json.dumps({"message": "chào", "brain": "brain", "session_id": sid}))
    t0 = time.time()
    while time.time() - t0 < 20:
        if json.loads(ws.receive_text()).get("type") == "turn_done":
            break
time.sleep(0.3)
check("a turn that ran to its end is not in the ledger any more", not [r for r in TL.rows() if r["session_id"] == sid], TL.rows())

# A cut turn runs again when a page comes back.
CALLS.clear()
sid = cut_chat("Tóm tắt doanh thu tuần này")
SCRIPT["turns"] = [[{"type": "text", "content": "Tuần này 12 triệu."}, final("Tuần này 12 triệu.")]]
got = connect()
check("the cut question reaches the engine again without anyone typing", any("Tóm tắt doanh thu tuần này" in c for c in CALLS), CALLS)
check("the page is told what is happening", any(m.get("type") == "system" and m.get("session_id") == sid
      and "khởi động lại" in str(m.get("content")) for m in got), [m for m in got if m.get("type") == "system"])
stored = store.get_messages(sid)
check("the answer is stored right under the question, which is not stored twice",
      [(m["role"], m["content"]) for m in stored[:2]] == [("user", "Tóm tắt doanh thu tuần này"), ("assistant", "Tuần này 12 triệu.")]
      and sum(1 for m in stored if m["role"] == "user") == 1, stored)
time.sleep(0.3)
check("and its row is closed", not [r for r in TL.rows() if r["session_id"] == sid], TL.rows())

# A cut turn that had already acted outside is not run again.
CALLS.clear()
sid = cut_chat("Gửi báo giá cho khách A", acted=1)
got = connect(wait_done=False)
check("a turn that already did something outside does NOT run again", CALLS == [], CALLS)
check("the chat keeps one line saying why, and the row is gone", last(sid).get("role") == "assistant" and "ra ngoài" in last(sid).get("content", "")
      and not [r for r in TL.rows() if r["session_id"] == sid], last(sid))

# Too many cuts of the same question.
CALLS.clear()
sid = cut_chat("Câu làm máy chủ chết", resumes=TL.MAX_RESUMES)
connect(wait_done=False)
check("a question restarts keep cutting stops being run again, with the reason stored", CALLS == [] and "nhiều lần" in last(sid).get("content", ""), last(sid))

# The owner already got an answer (or moved on): nothing to do.
CALLS.clear()
sid = cut_chat("Câu đã có trả lời", answered=True)
connect(wait_done=False)
check("a question that is no longer the last message is left alone", CALLS == [] and last(sid).get("content") == "Đã trả lời rồi."
      and not [r for r in TL.rows() if r["session_id"] == sid], last(sid))

# Switched off.
CALLS.clear()
sid = cut_chat("Câu khi tắt tự chạy lại")
os.environ["JAVIS_RESUME_AFTER_RESTART"] = "0"
try:
    connect(wait_done=False)
finally:
    os.environ.pop("JAVIS_RESUME_AFTER_RESTART", None)
check("JAVIS_RESUME_AFTER_RESTART=0: nothing runs again, as before", CALLS == [] and last(sid).get("role") == "user", last(sid))

# ---------- wiring ----------
hub = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("the hub marks a chat turn before any call that is not a read", hub.index("turn_ledger.mark_acted(") < hub.index("result = await once_ledger.run(")
      and 'if cls == "read":' in hub[hub.index("turn_ledger.mark_acted(") - 400:hub.index("turn_ledger.mark_acted(")])
check("every chat turn writes its row first, the runtime closes it, shutdown keeps it",
      "turn_ledger.begin(conv_sid, user_mid, user_message, user_text, brain)" in src
      and "_CHAT_RUNTIME.on_finish = turn_ledger.end" in src and "turn_ledger.closing = True" in src)
check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if fails:
    print(f"\nFAILED {len(fails)}: " + "; ".join(fails))
    raise SystemExit(1)
print("\nALL OK")
