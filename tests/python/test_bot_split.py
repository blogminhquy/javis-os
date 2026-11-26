"""A bot answer sent as several short messages (0.281.0, bot_split).

    python tests/run.py bot_split      (no network, fake MCP and engine)

Owner request 2026-10-22: the bot itself decides to send a few short messages instead of one long block. The Agent
writes a line `[TACH_TIN]` between messages; the channel sends each part as its own message. Issue #1833: only
personal Zalo did, every other channel got one long block. Now a capability table (`bot_split.CHANNELS`) says which
channels split, and both the prompt hint and the join step of a turn read it. Checks:
  1. parts/joined: empty parts dropped, at most MAX_PARTS, the marker never survives `joined`;
  1b. the table: personal Zalo, Zalo OA, Messenger and Telegram split, a comment thread never does, the transports read
      their message length from it, `outgoing` never lets a marker through;
  2. the prompt hint reaches the bot only on a channel (and chat) that splits;
  3. on a splitting channel the answer keeps the marker for the sender, the bot log and the inbox record the joined text;
  4. on any other channel, and in a Page comment thread, the marker becomes a blank line in the text sent;
  5. the Zalo sender sends one message per part, remembers each as its own echo, still cuts an over-long part,
     and tags only the first part in a group;
  5b. Messenger, Zalo OA and Telegram send one message per part, remember each Messenger/OA part as the bot's own echo,
      quote only on the first Telegram part, and the owner's own Telegram bot never splits;
  6. "Reply for me" and Try bot show the joined text.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-split-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot_split  # noqa: E402
import chatbot_log  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


M = bot_split.SPLIT_MARK

# ---- 1. parts / joined ----------------------------------------------------------------------------
check("no marker: one part", bot_split.parts("Dạ còn ạ") == ["Dạ còn ạ"])
check("marker splits, blanks dropped", bot_split.parts(f"Giá 120k ạ\n{M}\n\n{M}\nChị lấy thêm không?")
      == ["Giá 120k ạ", "Chị lấy thêm không?"])
check("marker is matched loosely (case, spaces)", bot_split.parts("a [ tach_tin ] b") == ["a", "b"])
check("at most MAX_PARTS, overflow joins the last",
      bot_split.parts(M.join("abcdef")) == ["a", "b", "c", "d\n\ne\n\nf"], bot_split.parts(M.join("abcdef")))
check("joined: blank line instead of the marker", bot_split.joined(f"a\n{M}\nb") == "a\n\nb")
check("joined: untouched without marker", bot_split.joined("a\n\nb") == "a\n\nb")
check("joined never keeps a marker", M not in bot_split.joined(M.join("abcdefgh")))

# ---- 1b. the capability table ---------------------------------------------------------------------
import messenger_bot  # noqa: E402
import telegram_bot  # noqa: E402
import zalo_oa_bot  # noqa: E402

check("table: the four chat channels split", all(bot_split.splits(c) for c in
                                                  ("zalo_personal", "zalo_oa", "messenger", "telegram")))
check("table: a channel not in the table does not split", not bot_split.splits("zalo") and not bot_split.splits("api")
      and not bot_split.splits(""))
check("table: a Facebook or Instagram comment thread never splits",
      not bot_split.splits("messenger", "cmt:123_456") and not bot_split.splits("messenger", "igc:789")
      and bot_split.splits("messenger", "ig:42"))
check("table: comment prefixes match the Messenger transport",
      set(bot_split.COMMENT_PREFIXES) == {messenger_bot.COMMENT_PREFIX, messenger_bot.IG_COMMENT_PREFIX})
check("table: transports read their message length from it",
      messenger_bot.MAX_MSG == bot_split.CHANNELS["messenger"].max_len
      and zalo_oa_bot.MAX_MSG == bot_split.CHANNELS["zalo_oa"].max_len
      and telegram_bot.MAX_CHUNK == bot_split.CHANNELS["telegram"].max_len
      and zp.TIN_TOI_DA == bot_split.CHANNELS["zalo_personal"].max_len)
check("table: every entry says how formatting shows",
      all(c.markup in ("zalo", "markdown", "plain") and c.max_len > 0 for c in bot_split.CHANNELS.values()))
check("outgoing: split -> one message per part", bot_split.outgoing(f"a\n{M}\nb", True) == ["a", "b"])
check("outgoing: no split -> one message, marker gone", bot_split.outgoing(f"a\n{M}\nb", False) == ["a\n\nb"])
check("outgoing: no marker -> unchanged", bot_split.outgoing("a\n\nb", True) == ["a\n\nb"])

# ---- 2-4. runtime -------------------------------------------------------------------------------------
BRAIN = Path(tempfile.mkdtemp(prefix="brain-split-"))
CALLS = []
REPLY = {"v": f"Dạ mẫu 500ml giá 120k ạ.\n{M}\nChị lấy thêm chai 1 lít không, đang có ưu đãi ạ?"}


async def _engine(text, meta, progress, *, channel="", bot=None, **kw):
    CALLS.append({"prompt": chatbot_runtime.build_bot_prompt(bot or {}), "channel": channel})
    return {"text": REPLY["v"], "files": []}


chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Bán nước mắm"}, "Trả lời ngắn."),
                     session_probe=lambda key: ("sid", 0), session_undo=lambda key, keep: None)
bid, err = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "muc_quyen": "suggest",
                                     "audience": "all", "xac_nhan_rui_ro": True})
check("(setup) bot created", bool(bid) and not err, err)
answer = chatbot_runtime._make_answer_fn(bid)


def meta(kenh, chat="u1"):
    return {"chat_id": chat, "chat_type": "private", "user_id": chat, "user_name": "Chị Hoa", "message_id": "",
            "account_id": "zl-1" if kenh == "zalo_personal" else "", "platform": kenh, "_kenh": kenh}


r = asyncio.run(answer("Mắm 500ml bao nhiêu em?", meta("zalo_personal")))
check("personal Zalo: prompt carries the split hint", CALLS and M in CALLS[-1]["prompt"])
check("personal Zalo: the answer keeps the marker for the sender", M in str((r or {}).get("text")), r)
rows = chatbot_log.doc(bid)
check("bot log records the joined text", rows and M not in str(rows[-1].get("dap"))
      and "120k ạ.\n\nChị lấy thêm" in str(rows[-1].get("dap")), rows[-1:])

# Issue #1833: Telegram, Messenger and Zalo OA used to join the parts here; they split now (the old check expected the
# bug). A channel outside the table (Zalo Bot) still joins.
for kenh in ("telegram", "messenger", "zalo_oa"):
    r = asyncio.run(answer("Mắm 500ml bao nhiêu em?", meta(kenh, chat="u-" + kenh)))
    check(f"{kenh}: prompt carries the split hint", CALLS and M in CALLS[-1]["prompt"], kenh)
    check(f"{kenh}: the answer keeps the marker for the sender", M in str((r or {}).get("text")), r)

r = asyncio.run(answer("Mắm 500ml bao nhiêu em?", meta("zalo", chat="u2")))
check("other channel: no split hint in the prompt", CALLS and M not in CALLS[-1]["prompt"])
check("other channel: one message, blank line instead of the marker",
      (r or {}).get("text") == "Dạ mẫu 500ml giá 120k ạ.\n\nChị lấy thêm chai 1 lít không, đang có ưu đãi ạ?", r)

r = asyncio.run(answer("Mắm 500ml bao nhiêu em?", meta("messenger", chat="cmt:111_222")))
check("Page comment thread: no split hint in the prompt", CALLS and M not in CALLS[-1]["prompt"])
check("Page comment thread: one reply, blank line instead of the marker",
      (r or {}).get("text") == "Dạ mẫu 500ml giá 120k ạ.\n\nChị lấy thêm chai 1 lít không, đang có ưu đãi ạ?", r)

# ---- 5. the Zalo sender ------------------------------------------------------------------------------
SENT, ECHO = [], []


async def _fake_goi(conn, tool, args):
    SENT.append((tool, dict(args)))
    return {"success": True, "messageId": str(len(SENT))}


zc._goi = _fake_goi
zc.ket_noi_theo_id = lambda cid: {"id": cid, "label": "Zalo"} if cid == "zl-1" else None
_ghi = zc.ghi_da_gui
zc.ghi_da_gui = lambda cid, chat, text: ECHO.append(text)
zp.NGHI_GIUA_DOAN = 0

ok, loi = asyncio.run(zp.gui({"id": "zl-1"}, "u1", REPLY["v"], "private"))
texts = [a["text"] for t, a in SENT if t == "zalo_send_message"]
check("sender: one Zalo message per part", ok and texts == ["Dạ mẫu 500ml giá 120k ạ.",
                                                           "Chị lấy thêm chai 1 lít không, đang có ưu đãi ạ?"], (ok, loi, texts))
check("sender: each part remembered as our own echo", all(t in ECHO for t in texts), ECHO)
check("sender: no marker ever sent", not any(M in t for t in texts))

SENT.clear()
asyncio.run(zp.gui({"id": "zl-1"}, "u1", "Một tin bình thường.\n\nCó dòng trống nhưng không tách.", "private"))
check("sender: a blank line alone does not split", len(SENT) == 1, SENT)

SENT.clear()
dai = "x " * (zp.TIN_TOI_DA)
asyncio.run(zp.gui({"id": "zl-1"}, "u1", f"Ngắn.\n{M}\n{dai}", "private"))
check("sender: an over-long part is still cut", len(SENT) >= 3 and SENT[0][1]["text"] == "Ngắn.", len(SENT))

SENT.clear()
TAGS = []


async def _fake_tagged(conn, chat_id, text, mention, styles=()):
    TAGS.append((text, mention))
    return True, ""


zp._send_tagged = _fake_tagged
asyncio.run(zp.gui({"id": "zl-1"}, "g1", f"Phần một\n{M}\nPhần hai", "group", {"uid": "9", "name": "Hoa"}))
check("group: only the first part tags the person", [m for _, m in TAGS][:1] == [{"uid": "9", "name": "Hoa"}]
      and all(m is None for t, m in TAGS[1:]) and [a["text"] for _, a in SENT] == ["Phần hai"], (TAGS, SENT))

# ---- 5b. Messenger, Zalo OA and Telegram senders -------------------------------------------------------
import chat_files  # noqa: E402

bot_split.PART_PAUSE_S = 0
PARTS = ["Dạ mẫu 500ml giá 120k ạ.", "Chị lấy thêm chai 1 lít không, đang có ưu đãi ạ?"]

MS = []
mb = messenger_bot.MessengerBot({"page_id": "1001", "access_token": "EAA" + "x" * 60, "app_secret": "a" * 32}, "", None,
                                giau_trang_thai=True)


async def _fake_post(client, path, payload):
    MS.append((path, payload))
    return {"ok": True, "message_id": f"m{len(MS)}"}


mb._post_json = _fake_post
asyncio.run(mb._send(None, "psid-7", REPLY["v"]))
texts = [pl["message"]["text"] for path, pl in MS if path.endswith("/messages")]
check("Messenger: one message per part", texts == PARTS, MS)
check("Messenger: each part remembered as the bot's own echo",
      all(chat_files.is_own_echo("messenger", "psid-7", text=t) for t in PARTS))
MS.clear()
asyncio.run(mb._send(None, "cmt:111_222", REPLY["v"]))
check("Messenger: a comment thread gets one reply, no marker",
      len(MS) == 1 and MS[0][0] == "111_222/comments" and M not in MS[0][1]["message"]
      and "120k ạ.\n\nChị lấy" in MS[0][1]["message"], MS)

OS = []
ob = zalo_oa_bot.ZaloOABot("", "", None, giau_trang_thai=True)


async def _fake_call(client, method, path, *, json_body=None, params=None, files=None, retry=True):
    OS.append(json_body)
    return {"ok": True, "data": {"message_id": f"o{len(OS)}"}}


ob._call = _fake_call
asyncio.run(ob._send(None, "oa-user-3", REPLY["v"]))
check("Zalo OA: one message per part", [b["message"]["text"] for b in OS] == PARTS, OS)
check("Zalo OA: each part remembered as the bot's own echo",
      all(chat_files.is_own_echo("zalo_oa", "oa-user-3", text=t) for t in PARTS))

TS = []


class _Resp:
    status_code = 200
    text = "{}"

    def json(self):
        return {"ok": True}


async def _fake_tg_post(client, method, **kw):
    TS.append(kw.get("json") or {})
    return _Resp()


tb = telegram_bot.TelegramBot("1:x", "", None, giau_trang_thai=True)
tb._post = _fake_tg_post
asyncio.run(tb._send(None, "-100", REPLY["v"], reply_to=55))
check("Telegram: one message per part", len(TS) == 2 and M not in str(TS), TS)
check("Telegram: only the first part quotes the question",
      len(TS) == 2 and "reply_parameters" in TS[0] and "reply_parameters" not in TS[1], TS)
TS.clear()
owner = telegram_bot.TelegramBot("1:x", "", None, giau_trang_thai=False)
owner._post = _fake_tg_post
asyncio.run(owner._send(None, "42", f"Cờ {M} là dấu tách tin của bot"))
check("Telegram: the owner's own bot never splits or rewrites", len(TS) == 1 and "TACH" in str(TS[0]), TS)

# ---- 6. try bot shows the joined text -----------------------------------------------------------------
t = asyncio.run(chatbot_runtime.try_message(bid, "Mắm 500ml bao nhiêu em?"))
check("try: joined text, no marker", t.get("would_reply") and M not in str(t.get("text"))
      and "\n\n" in str(t.get("text")), t)

check("no em dash in this file or bot_split.py", chr(0x2014) not in open(__file__, encoding="utf-8").read()
      and chr(0x2014) not in (SERVER / "bot_split.py").read_text(encoding="utf-8"))

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
