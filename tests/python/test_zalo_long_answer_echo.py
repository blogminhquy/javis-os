"""A long bot answer sent as several Zalo messages never makes the bot step aside (field reports #1734 and #1699).

    python tests/run.py zalo_long_answer_echo      (no network, no MCP)

#1734 (0.627.0): a personal-Zalo bot sent a long answer, Zalo got it as two messages. About 90 s later the history
catch-up (`zalo_personal_channel.catch_up`) found the second part in javis-zalo's `history.jsonl` and wrote it as the
OWNER's message ("recovered": true), so `_TAY` was set and the bot stayed out of that chat for `nhuong_tay_phut`:
the next two customer messages got no answer. The answer's inbox row is ONE message holding only the first part's id
(`attach_echo_id`), and `_own_already_stored` skipped rows that have an id and only matched equal or same-start text.
#1699 (0.620.0) described the same pattern: after each long AI message one or two "human" duplicates a second or two
later, then silence.

This file guards:
  1. a later part the live feed missed is recognised through what the bot remembered sending (`_DA_GUI`),
  2. a later part the live feed already took for an echo is never written again (the reported pattern),
  3. the same after a restart, when nothing is remembered: the part lies inside the stored answer,
  4. short parts the bot chose to send (`bot_split`), and an image the bot sent,
  5. and the owner typing on the phone still makes the bot step aside, recovered or live, even with words the
     bot or the owner already sent once.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zlongecho-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot_split  # noqa: E402
import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


NOW = time.time()
CONN = {"id": "zalo-1", "label": "Shop", "connector_id": "zalo", "env": {"HOME": tempfile.mkdtemp(prefix="zhome-")}}
SENT = []


async def fake_call(conn, tool, args):
    if tool == "zalo_send_message":
        SENT.append(str(args.get("text") or ""))
        return {"success": True}
    return {}


zc._ket_noi = lambda: [CONN]
zc._goi = fake_call
zp.NGHI_GIUA_DOAN = 0
HANDED = []
zc._giao_cho_bot = lambda conn, ev: HANDED.append(ev)
CHATS = ("c1", "c2", "c3", "c4", "c5", "c6", "c7")
tt = zc._TT.setdefault("zalo-1", {})
tt["first_read"] = NOW - 3600
tt["drained"] = True
tt["ten"] = {c: {"name": "Khach " + c, "type": "dm"} for c in CHATS}


def hist(mid, chat, text, seconds_ago, self_=False, kind="text"):
    """One message as javis-zalo files it (the live feed hands over the same shape)."""
    return {"msgId": str(mid), "threadId": chat, "threadType": "dm", "senderId": "me" if self_ else "u-" + chat,
            "senderName": "Me" if self_ else "Khach " + chat, "isSelf": self_, "text": text,
            "timestamp": int((NOW - seconds_ago) * 1000), "type": kind}


def bot_answers(chat, answer, seconds_ago):
    """What a bot turn does: the inbox row first (no id yet, the joined text), then `Transport._gui` remembers the
    whole answer and `gui` sends it part by part. Returns the parts Zalo received."""
    conversations.ghi_su_kien({
        "channel": "zalo_personal", "account_id": "zalo-1", "account_name": "Shop", "external_chat_id": chat,
        "chat_type": "private", "sender_type": "ai", "sender_id": "", "sender_name": "Bot", "message_type": "text",
        "text": bot_split.joined(answer), "external_message_id": "", "created_at": NOW - seconds_ago})
    zc.ghi_da_gui("zalo-1", chat, answer)
    SENT.clear()
    ok, err = asyncio.run(zp.gui({"id": "zalo-1"}, chat, answer))
    assert ok, err
    return list(SENT)


def live(*msgs):
    zc._ghi_lo(CONN, list(msgs), tt["ten"])


def rows(chat):
    conv = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=100)}.get(chat)
    return conversations.tin_nhan(int(conv["id"]), limit=200) if conv else []


def humans(chat):
    return [m["text"] for m in rows(chat) if m["sender_type"] == "human"]


def stepping_aside(chat):
    return zc.chu_vua_nhan_tay("zalo-1", chat, NOW)


P1 = "\n\n".join("Lop " + str(i) + ". Lich hoc toi thu hai, thu tu va thu sau, moi buoi chin muoi phut, hoc phi "
                 "tron goi da gom tai lieu va bai tap ve nha cho ca khoa." * 3 for i in range(5))
LONG = P1 + "\n\nChi can em giu cho lop nao thi nhan lai cho em nhe, em giu cho trong hai ngay a."

# ---- 1. The report: the live feed got part 1 only; the catch-up finds part 2 ~90 s later
parts = bot_answers("c1", LONG, 120)
check("the long answer went out as two messages", len(parts) == 2, [len(p) for p in parts])
live(hist("c1-1", "c1", parts[0], 118, self_=True))
bot_row = next(m for m in rows("c1") if m["sender_type"] == "ai")
check("the live echo of part 1 gave the answer's row its id", bot_row["external_message_id"] == "c1-1", bot_row)
check("part 1 did not make the bot step aside", not stepping_aside("c1"))
written = zc.catch_up(CONN, [hist("c1-1", "c1", parts[0], 118, self_=True),
                             hist("c1-2", "c1", parts[1], 116, self_=True),
                             hist("c1-k", "c1", "Vay lop toi thu hai con cho khong em?", 60)], NOW)
check("#1734: part 2 is not written as the owner's message", humans("c1") == [], humans("c1"))
check("#1734: part 2 does not make the bot step aside", not stepping_aside("c1"), zc._TAY)
check("the customer's missed message is still recovered", written == 1 and rows("c1")[-1]["sender_type"] == "customer",
      [(m["sender_type"], m["text"][:30]) for m in rows("c1")])
check("what the bot remembered sending was used up", not zc._la_tieng_vong("zalo-1", "c1", parts[1]))

# ---- 2. The live feed saw both parts (the pattern of #1699: after EVERY long answer)
parts = bot_answers("c2", LONG, 120)
live(hist("c2-1", "c2", parts[0], 118, self_=True), hist("c2-2", "c2", parts[1], 116, self_=True))
check("live: both parts are the bot's echo", humans("c2") == [] and not stepping_aside("c2"), humans("c2"))
check("live: the echo of part 2 is remembered for the catch-up", zc._echo_id_seen("zalo-1", "c2", "c2-2"))
zc.catch_up(CONN, [hist("c2-1", "c2", parts[0], 118, self_=True), hist("c2-2", "c2", parts[1], 116, self_=True)], NOW)
check("catch-up: part 2 the live feed already saw is not written again", humans("c2") == [], humans("c2"))
check("catch-up: and the bot does not step aside", not stepping_aside("c2"), zc._TAY)

# ---- 3. Same, after a restart: nothing remembered, only the inbox
parts = bot_answers("c3", LONG, 300)
live(hist("c3-1", "c3", parts[0], 298, self_=True))
zc._DA_GUI.clear()
zc._ECHO_IDS.clear()
zc.catch_up(CONN, [hist("c3-1", "c3", parts[0], 298, self_=True), hist("c3-2", "c3", parts[1], 296, self_=True)], NOW)
check("restart: part 2 lies inside the stored answer, so it is not the owner's", humans("c3") == [], humans("c3"))
check("restart: no stepping aside", not stepping_aside("c3"), zc._TAY)

# ---- 4. Short parts the bot chose to send, and an image the bot sent
SPLIT = "Da chi oi[TACH_TIN]Lop toi thu hai con hai cho a[TACH_TIN]Ok a"
parts = bot_answers("c4", SPLIT, 120)
check("bot_split: three messages", parts == ["Da chi oi", "Lop toi thu hai con hai cho a", "Ok a"], parts)
live(*(hist(f"c4-{i}", "c4", p, 118 - i, self_=True) for i, p in enumerate(parts)))
zc.catch_up(CONN, [hist(f"c4-{i}", "c4", p, 118 - i, self_=True) for i, p in enumerate(parts)], NOW)
check("bot_split: no part is written as the owner's, even a short one", humans("c4") == [], humans("c4"))
check("bot_split: no stepping aside", not stepping_aside("c4"), zc._TAY)
zc.ghi_da_gui_anh("zalo-1", "c4", 1)
live(hist("c4-img", "c4", "", 60, self_=True, kind="chat.photo"))
zc.catch_up(CONN, [hist("c4-img", "c4", "", 60, self_=True, kind="chat.photo")], NOW)
check("an image the bot sent is not the owner's, live or caught up", humans("c4") == [] and not stepping_aside("c4"),
      humans("c4"))

# ---- 5. The owner on the phone still counts
parts = bot_answers("c5", LONG, 200)
live(hist("c5-1", "c5", parts[0], 198, self_=True), hist("c5-2", "c5", parts[1], 196, self_=True))
own = "De anh goi lai cho chi chieu nay nhe"
zc.catch_up(CONN, [hist("c5-o", "c5", own, 30, self_=True)], NOW)
check("a recovered message the owner typed is the owner's", humans("c5") == [own], humans("c5"))
check("a recovered message the owner typed makes the bot step aside", stepping_aside("c5"), zc._TAY)
check("the owner's message is never remembered as an echo", not zc._echo_id_seen("zalo-1", "c5", "c5-o"))

again = "Chi oi lop toi thu hai bat dau tu ngay muoi lam nhe"
live(hist("c6-a", "c6", again, 100, self_=True))
check("live: a message the owner typed makes the bot step aside", humans("c6") == [again] and stepping_aside("c6"),
      humans("c6"))
zc._TAY.pop(("zalo-1", "c6"), None)
zc.catch_up(CONN, [hist("c6-b", "c6", again, 80, self_=True)], NOW)
check("the same words sent again by the owner are a message of their own", humans("c6") == [again, again], humans("c6"))
check("and they make the bot step aside", stepping_aside("c6"), zc._TAY)

parts = bot_answers("c7", LONG, 150)
live(hist("c7-1", "c7", parts[0], 148, self_=True), hist("c7-2", "c7", parts[1], 146, self_=True))
# Both words also appear inside the bot's answer, but a part is only matched from RECONCILE_PART_MIN characters.
zc.catch_up(CONN, [hist("c7-o", "c7", "da", 20, self_=True), hist("c7-p", "c7", "Chi can", 10, self_=True)], NOW)
check("a short recovered message of the owner is never taken for a part of the answer",
      sorted(humans("c7")) == ["Chi can", "da"] and stepping_aside("c7"), humans("c7"))

check("nothing recovered is handed to the bot", not any((e.get("metadata") or {}).get("recovered") for e in HANDED),
      HANDED)

src = open(os.path.join(SERVER, "zalo_personal_channel.py"), encoding="utf-8").read()
check("the live read and the catch-up share one echo check", src.count("_own_echo(") >= 3)
check("no em dash or en dash", not any(c in open(__file__, encoding="utf-8").read() for c in (chr(0x2014), chr(0x2013))))

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
