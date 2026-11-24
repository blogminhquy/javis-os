"""A customer bot never sends the files its turn happened to write (issue #1785).

    python tests/run.py bot_no_turn_files      (NO network, fake MCP and CLI)

A bot turn at "full" (the whole bot, or one private chat raised by a per-chat exception, as the owner's own chat with
the bot usually is) runs the owner's engine path, which lists every file the turn wrote or named
(`channel_context.collect_turn_files`) so the owner's Telegram receives them. Up to 0.632.1 that list reached the Zalo
channel: three Zalo bots kept logging "Gửi Zalo lỗi ... (N ảnh)" in the owner's full-level chat because Zalo refused the
work log, the agent file and the /tmp script the turn had written. Had the turn written only images (a draft in /tmp, a
contract preview), they would have gone out, and on a bot at "full" for everyone, to customers too.

This file guards:
  1. `chatbot_runtime.drop_engine_files` empties the engine's list and leaves everything else alone.
  2. The engine core never gathers files for a full-access bot, and `_tg_ket(khach=True)` carries none, so the
     reply keeps its `![](...)` for `bot_images.pick`. The owner's channel is unchanged.
  3. End to end on personal Zalo, in the owner's chat raised to "full" by an exception and in a customer chat: junk
     files from the engine are never sent; an image the Agent embeds still is, alone.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-noturnfiles-")
os.environ["JAVIS_REPLY_POLICY_SHADOW"] = "1"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot_images  # noqa: E402
import channel_context  # noqa: E402
import chatbot_log  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{str(detail)[:300]}]"))
    if not cond:
        _fails.append(name)


BRAIN = Path(tempfile.mkdtemp(prefix="brain-noturnfiles-")).resolve()
(BRAIN / "attachments").mkdir()
(BRAIN / "agents").mkdir()
(BRAIN / "attachments" / "a.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 100)
(BRAIN / "attachments" / "draft.png").write_bytes(b"\x89PNG" + b"0" * 100)
(BRAIN / "nhat-ky-thao-tac.md").write_text("work log", encoding="utf-8")
(BRAIN / "agents" / "sales.md").write_text("---\nname: sales\n---\n", encoding="utf-8")
(BRAIN / "contract.doc").write_bytes(b"doc")
OUTSIDE = Path(tempfile.mkdtemp(prefix="tmp-noturnfiles-")).resolve()
(OUTSIDE / "script.py").write_text("print(1)", encoding="utf-8")
(OUTSIDE / "preview.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 100)
B = str(BRAIN)


def at(rel):
    return str((BRAIN / rel).resolve())


# What the owner's engine path gathers in the reported turn: brain files, a /tmp script, and draft images.
TURN_FILES = [at("nhat-ky-thao-tac.md"), at("agents/sales.md"), str(OUTSIDE / "script.py"), at("contract.doc"),
              at("attachments/draft.png"), str(OUTSIDE / "preview.jpg")]

# ============================================================
# 1. drop_engine_files
# ============================================================
out = {"text": "Dạ", "files": list(TURN_FILES), "canh_bao": "x"}
dropped = chatbot_runtime.drop_engine_files(out)
check("engine files are dropped", dropped["files"] == [], dropped)
check("the rest of the answer is kept", dropped["text"] == "Dạ" and dropped["canh_bao"] == "x", dropped)
check("the engine's dict itself is not mutated", out["files"] == TURN_FILES, out)
check("a failed turn (a string) passes unchanged", chatbot_runtime.drop_engine_files("⚠ boom") == "⚠ boom")
plain = {"text": "Dạ", "files": []}
check("an answer without files passes unchanged", chatbot_runtime.drop_engine_files(plain) is plain)

# ============================================================
# 2. Engine core of main.py (source and `_tg_ket`)
# ============================================================
src = (SERVER / "main.py").read_text(encoding="utf-8")
core = src[src.index("async def _tg_answer_engine("):src.index("async def _tg_help_text(")]
check("the engine core gathers turn files in three branches", core.count("collect_turn_files(") == 3,
      core.count("collect_turn_files("))
check("CANARY: none of them runs for a full-access bot",
      core.count("files = [] if _bot_full else channel_context.collect_turn_files(") == 3)

import main  # noqa: E402

owner = main._tg_ket("Dạ", ["a.jpg"])
check("owner channel: the files still ride along", owner["files"] == ["a.jpg"], owner)
customer = main._tg_ket("Dạ", ["a.jpg"], khach=True)
check("customer bot: `_tg_ket` carries no file at all", customer["files"] == [], customer)

# With no gathered file, the embedded image stays in the text, so `bot_images.pick` can still send it.
reply = "Dạ mẫu đây ạ ![Mẫu A](attachments/a.jpg)"
kept = channel_context.strip_attached_media(channel_context.strip_control_blocks(reply), [], B)
check("a full-access bot's reply keeps its embedded image", "![Mẫu A](attachments/a.jpg)" in kept, kept)
text, picked = bot_images.pick(kept, B)
check("and bot_images.pick sends exactly that image", [f["path"] for f in picked] == [at("attachments/a.jpg")], picked)

# ============================================================
# 3. End to end on personal Zalo (fake MCP and CLI)
# ============================================================
CONN = {"id": "zalo-1", "label": "Shop", "connector_id": "zalo", "env": {"HOME": "/state/zalo-1"}}
CUSTOMER = "8880001"
OWNER = "u_owner"       # the owner's private chat with the bot, raised to "full" by a per-chat exception
SENT, INBOX, CLI, LEVELS = [], [], [], []
REPLY = {"text": "", "files": []}


async def _fake_call(conn, tool, args):
    if tool == "zalo_send_message":
        SENT.append(dict(args))
        return {"success": True}
    if tool == "zalo_list_threads":
        return {"threads": [{"threadId": CUSTOMER, "name": "Khách A", "type": "user"},
                            {"threadId": OWNER, "name": "Chủ shop", "type": "user"}]}
    if tool == "zalo_get_messages":
        msgs = list(INBOX)
        INBOX.clear()
        return {"messages": msgs, "nextCursor": "c" + str(time.time())}
    return {}


async def _fake_cli(conn, command, positionals=None, options=None, timeout=120):
    CLI.append({"command": list(command), "pos": list(positionals or [])})
    return True, {"msgId": "m1"}, ""


async def _engine(text, meta, progress, *, channel="", bot=None):
    # As `main._tg_answer_engine` behaved up to 0.632.1: only a turn at "full" takes the owner's engine path, which
    # returned the reply plus every file the turn wrote. Lower levels already returned no file.
    level = str((bot or {}).get("muc_quyen") or "")
    LEVELS.append(level)
    return {"text": REPLY["text"], "files": list(REPLY["files"]) if level == "full" else []}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _fake_call
zc.CHO_KHACH_IM = 0
zc.THU_LAI_TEN_GIAY = 0
zalo_cli.run_cli = _fake_cli
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: B,
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Bán hàng"}, "Trả lời khách."))

bot_id, err = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "account_ids": ["zalo-1"],
                                        "muc_quyen": "suggest"})
ok, why = chatbot_store.update_bot(bot_id, {"xac_nhan_ngoai_le": True, "ngoai_le": json.dumps(
    [{"account_id": "zalo-1", "chat_id": OWNER, "ten": "Chủ shop", "muc_quyen": "full", "cho_giay": None}])})
check("bot created, read-only, with the owner's chat raised to full", bool(bot_id) and not err and ok, (err, why))


def message(text, mid, who=CUSTOMER):
    return {"threadId": who, "from": who, "senderName": "Khách A" if who == CUSTOMER else "Chủ shop", "type": "text",
            "text": text, "id": mid, "ts": int((time.time() - 2) * 1000), "threadType": 0}


def clear():
    SENT.clear()
    CLI.clear()
    LEVELS.clear()


async def read_once():
    await zc.doc_mot_lan(dict(CONN))
    t0 = time.time()
    while zc._VIEC and time.time() - t0 < 6:
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.1)


def send_errors():
    return [r for r in chatbot_log.doc(bot_id, 50) if "Gửi Zalo lỗi" in str(r.get("loi") or "")]


async def run():
    ok, why = chatbot_runtime.start_bot(bot_id)
    check("bot started", ok, why)

    # The reported turn: the owner's full-level chat, a plain text reply, the engine's list full of working files.
    REPLY.update(text="Dạ em ghi xong nhật ký rồi ạ", files=TURN_FILES)
    INBOX.append(message("ghi nhật ký giúp em", "o1", OWNER))
    await read_once()
    check("(setup) the owner's chat ran at full, through the per-chat exception", LEVELS == ["full"], LEVELS)
    check("the text reply goes out", [s["text"] for s in SENT] == ["Dạ em ghi xong nhật ký rồi ạ"], SENT)
    check("CANARY: no working file is sent (no send-image at all)", CLI == [], CLI)
    check("no 'Gửi Zalo lỗi' line in the bot log", send_errors() == [], send_errors())

    # Only images in the list (a draft in the brain, a preview in /tmp): still nothing leaves.
    clear()
    REPLY.update(text="Dạ vâng ạ", files=[at("attachments/draft.png"), str(OUTSIDE / "preview.jpg")])
    INBOX.append(message("ok em", "o2", OWNER))
    await read_once()
    check("CANARY: draft images the turn wrote are never sent", CLI == [], CLI)
    check("and the text still goes out", [s["text"] for s in SENT] == ["Dạ vâng ạ"], SENT)

    # The Agent embeds one image: that image, and only that one, is sent.
    clear()
    REPLY.update(text="Dạ mẫu đây ạ ![Mẫu A](attachments/a.jpg)", files=TURN_FILES)
    INBOX.append(message("gửi anh mẫu A", "o3", OWNER))
    await read_once()
    check("full level: the embedded image is sent, alone",
          len(CLI) == 1 and CLI[0]["pos"] == [OWNER, at("attachments/a.jpg")], CLI)
    check("full level: the text goes out without the image syntax", [s["text"] for s in SENT] == ["Dạ mẫu đây ạ"], SENT)

    # A customer chat (the bot's own read-only level) behaves exactly as before.
    clear()
    REPLY.update(text="Dạ mẫu đây ạ ![Mẫu A](attachments/a.jpg)", files=TURN_FILES)
    INBOX.append(message("cho xem mẫu", "k1"))
    await read_once()
    check("(setup) the customer chat ran at the bot's own level", LEVELS == ["suggest"], LEVELS)
    check("customer chat: the embedded image is sent, alone",
          len(CLI) == 1 and CLI[0]["pos"] == [CUSTOMER, at("attachments/a.jpg")], CLI)
    check("customer chat: the text goes out without the image syntax", [s["text"] for s in SENT] == ["Dạ mẫu đây ạ"],
          SENT)
    chatbot_runtime.stop_bot(bot_id)


asyncio.run(run())

for f in (SERVER / "chatbot_runtime.py", Path(__file__)):
    body = f.read_text(encoding="utf-8")
    check(f"no em or en dash in {f.name}", chr(0x2014) not in body and chr(0x2013) not in body)

print()
if _fails:
    print(f"FAIL - test_bot_no_turn_files: {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("OK - test_bot_no_turn_files: all pass")
