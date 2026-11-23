"""A chat read on one device rings no other device (owner, 2026-11-23).

"Every answer buzzes the phone while I am reading it on the computer." sw.js only sees the tabs of its own device, so
each tab now tells the server which chat it shows (push.js -> POST /push/presence), and a push about that chat is
skipped everywhere while a fresh report says the owner is in front of it.

    python tests/run.py push_presence
"""
import asyncio
import os
import tempfile

from _paths import ROOT, SERVER  # noqa: E402,F401

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-presence-")

import push_presence as P  # noqa: E402
import webpush  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# --- the table ---
P.reset()
check("nobody reads anything at start", not P.watching("s1"))
check("an empty tab id is refused", not P.report("", "s1", True))
P.report("pc", "s1", True, now=1000)
check("the computer reads s1", P.watching("s1", now=1010))
check("another chat is not being read", not P.watching("s2", now=1010))
check("an empty chat id is never read", not P.watching("", now=1010))
check("a stale report no longer counts", not P.watching("s1", now=1000 + P.FRESH_S + 1))
P.report("pc", "s1", False, now=1020)
check("hiding the tab ends it at once", not P.watching("s1", now=1021))
P.report("pc", "s1", True, now=1030)
P.report("phone", "s1", False, now=1031)
check("one active tab is enough", P.watching("s1", now=1032))
P.report("pc", "s2", True, now=1040)
check("switching chats moves the reading", P.watching("s2", now=1041) and not P.watching("s1", now=1041))
P.reset()
for i in range(P.MAX_TABS + 50):
    P.report(f"t{i}", "s", True, now=2000 + i * 0.001)
check("the table stays bounded", len(P._TABS) <= P.MAX_TABS, len(P._TABS))

# --- webpush skips every device while the chat is read ---
sent = []
webpush.danh_sach_sub = lambda: [{"endpoint": "https://fcm.googleapis.com/x", "p256dh": "k", "auth": "a"}]


def fake_encrypt(payload, *_a):
    sent.append(payload.decode("utf-8"))
    raise RuntimeError("stop before the network")


webpush.ma_hoa = fake_encrypt
P.reset()
P.report("pc", "s1", True)
r = asyncio.run(webpush.gui_het("Javis", "hi", "/?mo_phien=s1", tag="t", quiet_if_visible=True, session_id="s1"))
check("an answer in the chat being read pushes nowhere", not sent and r == (0, 0, []), (sent, r))
asyncio.run(webpush.gui_het("Javis", "hi", "/?mo_phien=s2", tag="t", quiet_if_visible=True, session_id="s2"))
check("an answer in another chat still pushes", len(sent) == 1, sent)
sent.clear()
asyncio.run(webpush.gui_het("Javis", "job done", "/?mo_thu=1", tag="t"))
check("an ordinary notice (job, reminder) still pushes", len(sent) == 1, sent)
sent.clear()
P.report("pc", "s1", False)
asyncio.run(webpush.gui_het("Javis", "hi", "/?mo_phien=s1", tag="t", quiet_if_visible=True, session_id="s1"))
check("once the owner leaves, the answer rings again", len(sent) == 1, sent)

# --- wiring ---
push_js = (ROOT / "dashboard" / "push.js").read_text(encoding="utf-8")
main = (SERVER / "main.py").read_text(encoding="utf-8")
check("the tab reports presence", "/push/presence" in push_js and "TAB_ID" in push_js)
check("the tab says inactive when hidden", "visibilitychange" in push_js and "sendBeacon" in push_js)
check("server has the endpoint", '@app.post("/push/presence")' in main)
check("a long turn files no bell copy while read", "if push_presence.watching(conv_sid):" in main)

if fails:
    print(f"\nFAIL - test_push_presence: {len(fails)}: {', '.join(fails)}")
    raise SystemExit(1)
print("\nOK - test_push_presence: all pass")
