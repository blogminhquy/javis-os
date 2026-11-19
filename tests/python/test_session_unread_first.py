"""Unread chats come first in the history column (2026-11-19).

Owner: "những tin chấm đỏ mà chưa đọc em sắp xếp kéo lên trên đầu giúp anh nếu không sẽ rất khó tìm những tin chưa
đọc". The history column asks GET /sessions with unread_first=1: pinned chats stay on top, then every unread chat,
then the rest newest first. An unread chat older than the first page still lands on it. Callers that do not ask
(the "latest chat to continue" lookup, limit=1) keep plain newest first.

    python tests/run.py session_unread_first
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-unread-first-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_TMP) / "conv.db")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-unread-first-brains-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"

import sessions  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  " + str(extra)) if extra and not cond else ""))
    if not cond:
        fails.append(name)


st = sessions.SessionStore(Path(_TMP) / "store.db")


def chat(title, reply=True, read=False):
    sid = st.create_session(brain="/b", engine="cli", channel="web", title=title)
    st.append_message(sid, "user", "hỏi")
    if reply:
        st.append_message(sid, "assistant", "đáp")
    if read:
        st.mark_read(sid)
    time.sleep(0.01)
    return sid


old_unread = chat("cũ chưa đọc")                 # the oldest chat, still unread
pinned_read = chat("ghim đã đọc", read=True)
for i in range(5):
    chat("đã đọc %d" % i, read=True)
mid_unread = chat("giữa chưa đọc")
newest_read = chat("mới nhất đã đọc", read=True)
st.set_pinned(pinned_read, True)


def ids(**kw):
    return [s["id"] for s in st.list_sessions(brain="/b", **kw)]


plain = ids()
check("by default the newest chat comes right after the pinned one", plain[:2] == [pinned_read, newest_read], plain[:3])

first = ids(unread_first=True)
check("pinned chats stay on top", first[0] == pinned_read)
check("unread chats come next, newest first", first[1:3] == [mid_unread, old_unread], first[:4])
check("read chats follow, newest first", first[3] == newest_read)
check("the order holds every chat once", sorted(first) == sorted(plain))

page = ids(unread_first=True, limit=3)
check("an old unread chat makes the first page", old_unread in page and mid_unread in page, page)
check("without unread_first it would not", old_unread not in ids(limit=3))

st.mark_read(mid_unread)
again = ids(unread_first=True)
check("a chat read meanwhile drops back to its date place", again[1] == old_unread and again.index(mid_unread) > 2,
      again)

st.set_pinned(old_unread, True)
pin_first = ids(unread_first=True)
check("an unread pinned chat stays in the pinned group", set(pin_first[:2]) == {pinned_read, old_unread}, pin_first)

# The route passes the flag through; the history column always sends it.
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

store = main.get_store()
a = store.create_session(brain="/r", engine="cli", channel="web")
store.append_message(a, "user", "hỏi")
store.append_message(a, "assistant", "đáp")
time.sleep(0.01)
b = store.create_session(brain="/r", engine="cli", channel="web")
store.append_message(b, "user", "hỏi")
store.append_message(b, "assistant", "đáp")
store.mark_read(b)
cl = TestClient(main.app)
r = cl.get("/sessions", params={"brain": "/r", "unread_first": 1}).json()["sessions"]
check("GET /sessions?unread_first=1 puts the unread chat first", [s["id"] for s in r][:2] == [a, b])
r = cl.get("/sessions", params={"brain": "/r", "limit": 1}).json()["sessions"]
check("GET /sessions without it keeps the newest chat first", [s["id"] for s in r] == [b])

js = (Path(ROOT) / "dashboard" / "sessions-ui.js").read_text(encoding="utf-8")
check("the history column asks for unread_first", "&unread_first=1" in js)
check("the history column labels the group with the unread text", 'window.t("sess.unread")' in js and "laChuaDoc" in js)

print("\nFAIL:" if fails else "\nOK - session_unread_first", fails or "")
sys.exit(1 if fails else 0)
