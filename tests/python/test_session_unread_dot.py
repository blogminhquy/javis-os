"""Red unread dot in every chat history list (2026-11-06).

A chat is unread when Javis answered after the owner last had it on screen. Only chats read on the dashboard count
(web, partner chats); Telegram and bot chats were read where they happened.

    python tests/run.py session_unread_dot
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-unread-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_TMP) / "conv.db")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-unread-brains-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"

import sessions  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def unread_map(st, **kw):
    return {s["id"]: s["unread"] for s in st.list_sessions(brain="/b", **kw)}


db = Path(_TMP) / "old.db"
st = sessions.SessionStore(db)
web = st.create_session(brain="/b", engine="cli", channel="web")
tg = st.create_session(brain="/b", engine="cli", channel="telegram")
ag = st.create_session(brain="/b", engine="cli", channel="agent:nguoi-viet")
asked = st.create_session(brain="/b", engine="cli", channel="web")
for sid in (web, tg, ag, asked):
    st.append_message(sid, "user", "xin chào")
st.append_message(asked, "user", "còn câu nữa")
for sid in (web, tg, ag):
    st.append_message(sid, "assistant", "chào anh")

u = unread_map(st)
check("a reply nobody looked at is unread", u[web] is True)
check("a telegram chat is never unread on the dashboard", u[tg] is False)
check("a chat with no reply yet is not unread", u[asked] is False)
check("partner chat counts too", unread_map(st, channel="agent:nguoi-viet")[ag] is True)
check("unread is a real bool in the list", isinstance(u[web], bool))

# Every partner kind lights the dot; bot and team chats never do (Teams keep their own unread count, customer bot
# chats are read in the bot inbox).
kinds = {ch: st.create_session(brain="/b", engine="cli", channel=ch)
         for ch in ("workflow:viet-blog", "coding:javis-os", "bot:shop", "team:marketing", "teammate:an")}
for sid in kinds.values():
    st.append_message(sid, "user", "giao việc")
    st.append_message(sid, "assistant", "xong rồi")
check("workflow and coding chats count as partner chats",
      st.is_unread(kinds["workflow:viet-blog"]) is True and st.is_unread(kinds["coding:javis-os"]) is True)
check("bot and team chats never get the history dot",
      not any(st.is_unread(kinds[ch]) for ch in ("bot:shop", "team:marketing", "teammate:an")))
for sid in kinds.values():
    st.mark_read(sid)

check("mark_read on an existing chat", st.mark_read(web) is True)
check("read chat loses the dot", unread_map(st)[web] is False and st.is_unread(web) is False)
check("mark_read never moves the mark back", st.mark_read(web, at=1.0) is False)
check("mark_read on an unknown chat is harmless", st.mark_read("khong-co") is False and st.is_unread("khong-co") is False)

time.sleep(0.01)
st.append_message(web, "assistant", "kết quả việc nền")
check("a new reply after reading lights the dot again", st.is_unread(web) is True)
st.append_message(asked, "user", "câu thứ ba")
check("the owner's own message never lights the dot", st.is_unread(asked) is False)

# Upgrade: a store from before the column existed. Old chats must not all light up at once.
st.mark_read(ag)
st.append_message(ag, "assistant", "câu trả lời cũ")
st._conn.execute("DROP TABLE session_read")
st._conn.commit()
st2 = sessions.SessionStore(db)
tables = {r[0] for r in st2._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
check("migration adds the session_read table", "session_read" in tables)
check("chats from before the upgrade count as read",
      not any(unread_map(st2).values()) and not any(unread_map(st2, channel="agent:nguoi-viet").values()))
time.sleep(0.01)
st2.append_message(web, "assistant", "tin sau khi nâng cấp")
check("a reply after the upgrade still lights the dot", st2.is_unread(web) is True)
st2.delete(web)
check("deleting a chat drops its read mark",
      st2._conn.execute("SELECT COUNT(*) FROM session_read WHERE session_id = ?", (web,)).fetchone()[0] == 0)

# The read mark lives outside `sessions`: its columns are an exact list the qualified native trial context reads, and
# a new column there makes every trial on a web chat fail with unsupported_sql_context_schema.
import improvement_trial_sql_context as SQLCTX  # noqa: E402
_c = sqlite3.connect(str(db))
_c.row_factory = sqlite3.Row
try:
    SQLCTX._schema(_c, "sessions", SQLCTX._SESSION_FIELDS, SQLCTX._SESSION_COLUMNS)
    check("sessions keeps the column list the trial context accepts", True)
except ValueError as e:
    check("sessions keeps the column list the trial context accepts (%s)" % e, False)
finally:
    _c.close()

# Route: POST /sessions/{id}/read clears the dot and tells the other tabs only when something changed.
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
store = main.get_store()
sid = store.create_session(brain="/b", engine="cli", channel="web")
store.append_message(sid, "user", "hỏi")
store.append_message(sid, "assistant", "đáp")
sent = []
_orig = main._CHAT_RUNTIME.publish


async def _spy(ev):
    sent.append(ev)
main._CHAT_RUNTIME.publish = _spy
try:
    cl = TestClient(main.app)
    r = cl.post("/sessions/" + sid + "/read")
    check("route answers was_unread", r.status_code == 200 and r.json() == {"ok": True, "was_unread": True})
    check("route marks it read", store.is_unread(sid) is False)
    check("route broadcasts session_read once", sent == [{"type": "session_read", "session_id": sid}])
    r = cl.post("/sessions/" + sid + "/read")
    check("second call is quiet", r.json()["was_unread"] is False and len(sent) == 1)
    r = cl.get("/sessions", params={"brain": "/b"}).json()
    row = [s for s in r["sessions"] if s["id"] == sid]
    check("GET /sessions carries the unread field", row and row[0]["unread"] is False)
finally:
    main._CHAT_RUNTIME.publish = _orig

print("\nFAIL:" if fails else "\nOK - session_unread_dot", fails or "")
sys.exit(1 if fails else 0)
