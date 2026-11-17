"""Every dashboard answer can ring the phone, but not when the owner is looking at that chat (owner 2026-11-17).

"After you answer, notify me, but only when I left for another app; still notify when I opened another chat in the
dashboard." The bell switch `push.turn_done` = "all" makes every turn push; the service worker asks the tab in front
which chat it shows and stays quiet only for that chat.

    python tests/run.py turn_done_every
"""
import asyncio
import os
import tempfile

from _paths import ROOT, SERVER  # noqa: E402,F401

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tde-")

import turn_done_notice as N  # noqa: E402
import webpush  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# --- the switch ---
check("off by default", not N.every_turn({}))
check("'long' keeps the old rule", not N.every_turn({"push": {"turn_done": "long"}}))
check("'all' turns it on", N.every_turn({"push": {"turn_done": "all"}}))

# --- push body: one plain line ---
raw = "### Kết luận\n**Kiwi** là [trái cây](x.md) có [[Wiki|vitamin C]] cao.\n- ý 1\n```py\nprint(1)\n```"
got = N.push_text(raw)
check("markdown stripped to one line", got == "Kết luận Kiwi là trái cây có vitamin C cao. ý 1", got)
long = N.push_text("a " * 500)
check("a long answer is cut", len(long) <= N.PUSH_BODY and long.endswith("..."), len(long))
check("an empty answer gives nothing", N.push_text("  \n ") == "")

# --- the push names the chat so the service worker can tell chats apart ---
sent = []
webpush.danh_sach_sub = lambda: [{"endpoint": "https://fcm.googleapis.com/x", "p256dh": "k", "auth": "a"}]


def fake_encrypt(payload, *_a):
    sent.append(payload.decode("utf-8"))
    raise RuntimeError("stop before the network")


webpush.ma_hoa = fake_encrypt
asyncio.run(webpush.gui_het("Javis", "hi", "/?mo_phien=s1", tag="t", quiet_if_visible=True, session_id="s1"))
check("payload carries the chat id", sent and '"session_id": "s1"' in sent[0] and '"quiet_if_visible": true' in sent[0],
      sent[:1])
sent.clear()
asyncio.run(webpush.gui_het("Javis", "hi", "/", tag="t"))
check("an ordinary push carries no chat id", sent and "session_id" not in sent[0], sent[:1])

# --- wiring in the files the browser runs ---
sw = (ROOT / "dashboard" / "sw.js").read_text(encoding="utf-8")
push_js = (ROOT / "dashboard" / "push.js").read_text(encoding="utf-8")
noti = (ROOT / "dashboard" / "notifications.js").read_text(encoding="utf-8")
main = (SERVER / "main.py").read_text(encoding="utf-8")
check("sw asks the tab which chat it shows", "javis-which-session" in sw and "d.session_id" in sw)
check("sw keeps the old rule for a tab that does not answer", "sid === null" in sw)
check("the tab answers with its chat", "javis-which-session" in push_js and "JavisSessions.current()" in push_js)
check("a tap opens the chat", "mo_phien" in noti and "JavisSessions.open(sid)" in noti)
check("the bell has the switch", "notificationPushEvery" in noti and "turn_done" in noti)
check("server saves the switch", '["turn_done"] = "all" if' in main)
check("a short turn pushes when the switch is on", "return _bao_luot_xong_ngan(conv_sid, text)" in main)

if fails:
    print(f"\nFAIL - test_turn_done_every: {len(fails)}: {', '.join(fails)}")
    raise SystemExit(1)
print("\nOK - test_turn_done_every: all pass")
