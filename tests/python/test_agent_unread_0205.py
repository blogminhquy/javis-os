"""0.205.0: private partner chats get an unread count, sort by the newest message, and can be muted.

Covers: the mute lengths (1h, 4h, the next 08:00 in the owner's time zone, until turned back on, off), a partner seen
for the first time starting as read, mark_read, the session-store activity query (partner messages after the read
mark, newest message of either side), the routes behind login, and a muted partner's report filed quietly.

Run:
    python tests/run.py agent_unread
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-agent-unread-")
os.environ["JAVIS_STATE_DIR"] = _TMP

import agent_notify as an  # noqa: E402
import sessions  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


VN = timezone(timedelta(hours=7))
morning = datetime(2026, 10, 17, 6, 30, tzinfo=VN)
evening = datetime(2026, 10, 17, 21, 0, tzinfo=VN)
check("1 hour", an.mute_until("1h", morning) == (morning + timedelta(hours=1)).timestamp())
check("4 hours", an.mute_until("4h", morning) == (morning + timedelta(hours=4)).timestamp())
check("until 8:00 the same morning", an.mute_until("8am", morning) == datetime(2026, 10, 17, 8, 0, tzinfo=VN).timestamp())
check("until 8:00 the next morning after 8", an.mute_until("8am", evening) == datetime(2026, 10, 18, 8, 0, tzinfo=VN).timestamp())
check("until turned back on", an.mute_until("forever", morning) == an.MUTE_FOREVER and an.is_muted(an.MUTE_FOREVER))
check("off", an.mute_until("off", morning) == 0 and not an.is_muted(0))
try:
    an.mute_until("1y", morning)
    check("unknown choice refused", False)
except ValueError:
    check("unknown choice refused", True)
check("a past time is not muted", not an.is_muted(100.0, now_ts=200.0) and an.is_muted(300.0, now_ts=200.0))

clock = {"t": 1000.0}
store = an.AgentNotify(lambda: Path(_TMP), clock=lambda: clock["t"])
recs = store.records("/b", ["viet", "doc"])
check("first sight starts as read now", recs["viet"]["read_at"] == 1000.0 and recs["doc"]["muted_until"] == 0)
clock["t"] = 2000.0
check("a known partner keeps its read mark", store.records("/b", ["viet"])["viet"]["read_at"] == 1000.0)
store.mark_read("/b", "viet")
check("mark_read moves the mark", store.records("/b", ["viet"])["viet"]["read_at"] == 2000.0)
store.set_mute("/b", "doc", 2500.0)
check("muted until a time", store.muted("/b", "doc"))
clock["t"] = 3000.0
check("mute ends by itself", not store.muted("/b", "doc"))
check("brains are kept apart", not store.muted("/other", "doc") and "|" in an.AgentNotify.key("/b", "x"))

st = sessions.SessionStore(Path(_TMP) / "conv.db")
s1 = st.create_session(brain="/b", engine="cli", channel="agent:viet")
s2 = st.create_session(brain="/b", engine="cli", channel="agent:viet")
s3 = st.create_session(brain="/c", engine="cli", channel="agent:viet")
st.append_message(s1, "user", "viết giúp anh")
st.append_message(s1, "assistant", "đây ạ")
st.append_message(s2, "assistant", "bản 2")
st.append_message(s3, "assistant", "brain khác")
act = st.agent_activity(["/b"], {"viet": 0, "none": 0})
check("partner messages across its chats are counted, this brain only", act["viet"]["n"] == 2)
check("newest message time", act["viet"]["last_at"] > 0 and act["none"] == {"n": 0, "last_at": 0.0})
check("read mark hides older messages", st.agent_activity(["/b"], {"viet": act["viet"]["last_at"]})["viet"]["n"] == 0)

import main as app_main  # noqa: E402
from _paths import moi_duong_dan  # noqa: E402

paths = moi_duong_dan(app_main.app)
check("routes registered", {"/agents/unread", "/agents/opened", "/agents/mute"} <= paths)
check("routes behind login", not any(p.startswith(x) for p in ("/agents/unread", "/agents/opened", "/agents/mute")
                                     for x in app_main._AUTH_PUBLIC_PREFIX))
root = app_main._brain_key("brain")
app_main._AGENT_NOTIFY.set_mute(root, "viet", an.MUTE_FOREVER)
check("a muted partner's report is filed quietly", app_main._partner_muted({"channel": "agent:viet", "brain": "brain"}))
check("other chats are never muted here", not app_main._partner_muted({"channel": "web", "brain": "brain"})
      and not app_main._partner_muted({"channel": "agent:doc", "brain": "brain"}))
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("the inbox step turns quiet for a muted partner", "_partner_muted(get_store().get_session(sid) or {}):\n                    quiet = True" in src)
for f in ("agent_notify.py",):
    check(f"no long dashes in {f}", not any(c in (SERVER / f).read_text(encoding="utf-8") for c in "–—"))

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
