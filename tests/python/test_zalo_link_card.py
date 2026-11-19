"""A reply holding a link goes out on personal Zalo as a link card (javis-zalo 1.13.0 `zalo_send_link`).

    python tests/run.py zalo_link_card      (no network)

Owner report 19/11/2026: a link Javis sent on Zalo showed as bare text, while the same link typed in the Zalo app
shows the page's title and thumbnail. Zalo's card is built by the SENDER, so the reply has to go out through
`zalo_send_link`. This file guards:
1. The first link is found without the punctuation around it.
2. A reply with a link uses the card tool; one without keeps `zalo_send_message` exactly as before.
3. An older MCP (no tool) or a refused card still delivers the reply as plain text, and the tool is not asked again.
4. A card that timed out is NOT sent a second time as plain text.
5. The card's echo is recognised as the bot's own, even when Zalo fills its text from the page, so the bot does
   not go quiet thinking the owner typed by hand.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-link-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


MEET = "https://meet.google.com/gdp-fthu-kbo"

# ============================================================
# 1. Finding the link
# ============================================================
check("bare link", zp.first_link(f"Link họp: {MEET}") == MEET)
check("full stop after the link is not part of it", zp.first_link(f"Họp ở {MEET}.") == MEET)
check("link in brackets loses the closing bracket", zp.first_link(f"Google Meet ({MEET}).") == MEET)
check("a bracket that belongs to the link stays",
      zp.first_link("Xem https://vi.wikipedia.org/wiki/Python_(ngôn_ngữ) nhé") == "https://vi.wikipedia.org/wiki/Python_(ngôn_ngữ)")
check("the first of two links", zp.first_link(f"{MEET} và https://a.vn/b") == MEET)
check("no link, nothing", zp.first_link("Dạ em chào anh ạ, gặp ở meet.google.com nhé") == "")
check("a scheme alone is not a link", zp.first_link("https:// rồi gì nữa") == "")

# ============================================================
# 2. Card tool or plain send
# ============================================================
CALLS = []
MODE = {"link": "ok"}


async def fake_call(conn, tool, args):
    CALLS.append((tool, dict(args)))
    if tool == "zalo_send_link":
        m = MODE["link"]
        if m == "missing":
            raise RuntimeError("gọi tool lỗi: McpError: Tool zalo_send_link not found")
        if m == "timeout":
            raise RuntimeError("gọi tool lỗi: TimeoutError: timed out after 120s")
        if m == "refused":
            raise RuntimeError("Error: Zalo từ chối")
        if m == "plain":
            return {"success": True, "messageId": "m2", "preview": False}
        return {"success": True, "messageId": "m1", "preview": True}
    if tool == "zalo_send_message":
        return {"success": True, "messageId": "m9"}
    return {}


zc._ket_noi = lambda: [{"id": "zalo-1", "label": "Zalo", "connector_id": "zalo"}]
zc._goi = fake_call
zp.NGHI_GIUA_DOAN = 0


async def no_styled(*a, **k):      # the styled CLI path needs a real home; the MCP path is what is tested here
    return None

zp._send_styled = no_styled


def send(chat, text, chat_type="private"):
    CALLS.clear()
    return asyncio.run(zp.gui({"id": "zalo-1"}, chat, text, chat_type))


ok, err = send("u1", f"Dạ link họp của mình đây ạ: **{MEET}**")
check("a reply with a link is sent once, as a card", ok and [c[0] for c in CALLS] == ["zalo_send_link"], CALLS)
args = CALLS[0][1] if CALLS else {}
check("the card carries the link and the whole reply, without markdown stars",
      args.get("url") == MEET and args.get("text") == f"Dạ link họp của mình đây ạ: {MEET}", args)
check("private chat is threadType 0", args.get("threadType") == 0)

ok, err = send("g1", f"Mọi người vào họp: {MEET}", "group")
check("group chat is threadType 1", ok and CALLS and CALLS[-1][1].get("threadType") == 1, CALLS)

ok, err = send("u1", "Dạ em chào anh ạ")
check("CANARY: a reply without a link goes out exactly as before",
      ok and CALLS == [("zalo_send_message", {"threadId": "u1", "text": "Dạ em chào anh ạ", "threadType": 0, "type": 0})],
      CALLS)

# ============================================================
# 3. Older MCP, refused card, plain fallback inside the tool
# ============================================================
MODE["link"] = "missing"
ok, err = send("u5", f"Link: {MEET}")
check("older MCP: the reply still goes out as plain text",
      ok and [c[0] for c in CALLS] == ["zalo_send_link", "zalo_send_message"], CALLS)
ok, err = send("u5", f"Link lần hai: {MEET}")
check("older MCP: the card tool is not asked again for a while", ok and [c[0] for c in CALLS] == ["zalo_send_message"], CALLS)
check("older MCP: no card echo is left waiting", not zc._LINK_ECHOES.get(("zalo-1", "u5")))
zp._LINK_OFF_UNTIL.clear()

MODE["link"] = "refused"
ok, err = send("u6", f"Link: {MEET}")
check("refused card: the reply still goes out as plain text",
      ok and [c[0] for c in CALLS] == ["zalo_send_link", "zalo_send_message"], CALLS)
check("refused card: the tool stays on for the next reply", not zp._LINK_OFF_UNTIL.get("zalo-1"))

MODE["link"] = "plain"
ok, err = send("u7", f"Link: {MEET}")
check("no preview for the page: one send, no second plain message", ok and [c[0] for c in CALLS] == ["zalo_send_link"], CALLS)
check("no preview for the page: no card echo is left waiting", not zc._LINK_ECHOES.get(("zalo-1", "u7")))

# ============================================================
# 4. Timeout: never twice
# ============================================================
MODE["link"] = "timeout"
ok, err = send("u8", f"Link: {MEET}")
check("CANARY: a card that timed out is not sent again as plain text",
      not ok and [c[0] for c in CALLS] == ["zalo_send_link"], CALLS)
check("timeout reads as uncertain in the inbox", zp.send_uncertain(err), err)
MODE["link"] = "ok"

# ============================================================
# 5. The card's echo
# ============================================================
zc._LINK_ECHOES.clear()
zc._DA_GUI.clear()
ok, err = send("u9", f"Dạ anh vào họp ở đây ạ {MEET}")
own_card = {"type": "other", "message_type": "other", "text": "Real-time meetings by Google."}
raw = {"attachment": {"type": "chat.recommended", "url": MEET, "description": "Google Meet"}}
check("CANARY: the echo is the bot's own even when its text is the page's description",
      zc._is_link_echo("zalo-1", "u9", own_card, raw))
check("the record is used up", not zc._is_link_echo("zalo-1", "u9", own_card, raw))

ok, err = send("u10", f"Link {MEET}")
check("an echo carrying the link in its text matches too",
      zc._is_link_echo("zalo-1", "u10", {"message_type": "other", "text": f"Link {MEET}/"}, {}))

ok, err = send("u11", f"Link {MEET}")
check("an echo with no readable link counts only shortly after the card",
      zc._is_link_echo("zalo-1", "u11", {"message_type": "other", "text": "[chat.recommended]"}, {}))
ok, err = send("u12", f"Link {MEET}")
k = ("zalo-1", "u12")
zc._LINK_ECHOES[k] = [(time.time() - zc.LINK_ECHO_BLIND - 5, u) for _t, u in zc._LINK_ECHOES[k]]
check("...and not minutes later, when it is more likely the owner",
      not zc._is_link_echo("zalo-1", "u12", {"message_type": "other", "text": "[chat.recommended]"}, {}))
check("a plain text message from the owner is never taken for the card blindly",
      not zc._is_link_echo("zalo-1", "u12", {"message_type": "text", "text": "để anh xem"}, {}))
check("another chat's card is not this chat's echo",
      not zc._is_link_echo("zalo-1", "u99", own_card, raw))

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
