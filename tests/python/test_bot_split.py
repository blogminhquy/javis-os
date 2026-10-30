"""A bot answer sent as several short messages (0.281.0, bot_split).

    python tests/run.py bot_split      (no network, fake MCP and engine)

Owner request 2026-10-22: the bot itself decides to send a few short messages instead of one long block. The Agent
writes a line `[TACH_TIN]` between messages; personal Zalo sends each part as its own message. Checks:
  1. parts/joined: empty parts dropped, at most MAX_PARTS, the marker never survives `joined`;
  2. the prompt hint reaches the bot only on a channel that splits;
  3. on personal Zalo the answer keeps the marker for the sender, the bot log and the inbox record the joined text;
  4. on any other channel the marker becomes a blank line in the text sent;
  5. the Zalo sender sends one message per part, remembers each as its own echo, still cuts an over-long part,
     and tags only the first part in a group;
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

r = asyncio.run(answer("Mắm 500ml bao nhiêu em?", meta("telegram", chat="u2")))
check("other channel: no split hint in the prompt", CALLS and M not in CALLS[-1]["prompt"])
check("other channel: one message, blank line instead of the marker",
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
