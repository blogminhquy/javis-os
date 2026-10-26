"""Emoji reactions on personal Zalo (0.334.0, javis-zalo 1.7.0), END TO END: fake MCP, fake models, real bot.

    python tests/run.py zalo_reactions      (no network)

Owner 2026-10-26: "khách hàng đọc được emoji reaction trên zalo và javis thả được reaction vào", then "Khách chỉ thả
reaction thì bot có trả lời không? phần này tự học trong bộ phán xử, đừng fix cứng" and "bot được tự thả dựa theo bộ
phán xử luôn". This file guards:
  1. A reaction lands in the inbox as one line saying who reacted, with what, and to which message (the bot's own
     reply included: its id is attached when its echo comes back).
  2. The account's own reactions never count as the owner typing; the bot's own one is filed as the bot's.
  3. A customer's reaction reaches the decider (the Agent, or the judge in a group) as an event; nothing in Javis
     answers or ignores it on its own. Taking a reaction back is only recorded.
  4. The bot reacts only when the Agent (`[CAM_XUC:<name>]`) or the judge (`"reaction"`) says so, on the customer's
     message, never on a reaction; the marker never reaches the customer.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-reactions-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot_reaction  # noqa: E402
import chatbot_reply_policy as rp  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal  # noqa: E402,F401

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CONN = {"id": "zalo-1", "label": "Shop Hoa", "connector_id": "zalo"}
CUSTOMER = "8001"          # a private chat: the thread id is the customer's id
GROUP = "6661001"
UID_A = "7001"
THREADS = [{"threadId": GROUP, "name": "Nhóm khách quen", "type": "group"}]
SENT, REACTED, FEED, TURNS = [], [], [], []
ANSWER = {"v": "Dạ có ạ"}


def _ms(secs_ago=0):
    return int((time.time() - secs_ago) * 1000)


async def _fake_call(conn, tool, args):
    if tool == "zalo_send_message":
        SENT.append(dict(args))
        return {"success": True, "messageId": "s" + str(len(SENT))}
    if tool == "zalo_add_reaction":
        REACTED.append(dict(args))
        return {"success": True, "msgId": args.get("msgId"), "reaction": args.get("reaction")}
    if tool == "zalo_list_threads":
        return {"threads": [dict(t) for t in THREADS]}
    if tool == "zalo_get_messages":
        tin = list(FEED)
        FEED.clear()
        return {"messages": tin, "nextCursor": "c" + str(time.time())}
    return {}


zc._ket_noi = lambda: [dict(CONN)]
zc._goi = _fake_call
zc.NHUONG_GIAY = 0.02
zc.THU_LAI_TEN_GIAY = 0
zc.CHO_KHACH_IM = 0         # private messages go to the bot at once (gathering is tested on `gop_tin` directly)


async def _engine(text, meta, progress, *, channel="", bot=None):
    TURNS.append({"text": text, "meta": dict(meta or {}), "channel": channel})
    return {"text": ANSWER["v"], "files": []}


BRAIN = Path(tempfile.mkdtemp(prefix="brain-reactions-"))
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Hoa", "role": "Tư vấn hoa"}, "Trả lời ngắn gọn."))


class Judge:
    """Fake judge: answers `self.out` and records each prompt."""

    def __init__(self):
        self.out = {"verdict": "silent", "score": 0.3, "reason": "chưa chắc"}
        self.prompts = []

    async def __call__(self, prompt, purpose=""):
        if purpose == "profile":
            return "Đảm nhiệm:\n- tư vấn hoa\nKhông đảm nhiệm:\n- chuyện riêng"
        if purpose == "bootstrap":
            return "[]"
        if purpose == "teach":
            return json.dumps({"is_teaching": False})
        self.prompts.append(prompt)
        return json.dumps(self.out)


J = Judge()
rp.wire(ask=J)


def message(text, mid, thread=CUSTOMER, uid=CUSTOMER, who="Lan", secs_ago=2, group=False, **extra):
    m = {"id": mid, "threadId": thread, "threadType": "group" if group else "dm", "senderId": uid, "senderName": who,
         "isSelf": False, "text": text, "timestamp": _ms(secs_ago), "type": "text", "cliMsgId": "c" + mid}
    m.update(extra)
    return m


def reaction_msg(rid, target, name="heart", thread=CUSTOMER, uid=CUSTOMER, who="Lan", group=False, removed=False,
                 own=False, secs_ago=1):
    """Exactly javis-zalo 1.7.0 `normalizeReaction`."""
    emoji = bot_reaction.emoji_of(name)
    return {"id": rid, "threadId": thread, "threadType": "group" if group else "dm", "senderId": uid,
            "senderName": who, "isSelf": own, "text": None, "timestamp": _ms(secs_ago), "type": "reaction",
            "attachment": None, "replyTo": None,
            "reaction": {"name": None if removed else name, "code": "" if removed else "/-" + name,
                         "emoji": None if removed else emoji, "removed": removed, "targetMsgId": target,
                         "targetCliMsgId": "c" + target}}


def stored(thread, mid):
    return conversations.tin_theo_id(zc.KENH, CONN["id"], thread, mid)


THREAD_NAMES = {}

# ============================================================
# 1. bot_reaction: the marker and the describing line
# ============================================================
check("the marker leaves the answer and names the reaction",
      bot_reaction.pick("Dạ có ạ\n[CAM_XUC:heart]") == ("Dạ có ạ", "heart"))
check("only the marker: no words left, the reaction stays", bot_reaction.pick("[cam_xuc: Like]") == ("", "like"))
check("an unknown name is removed too, so it never reaches a customer, and no reaction is put",
      bot_reaction.pick("ok [CAM_XUC:banana]") == ("ok", None))
check("several markers: the first usable one wins, all are removed",
      bot_reaction.pick("[CAM_XUC:banana] [CAM_XUC:wow] chào [CAM_XUC:haha]") == ("chào", "wow"))
check("no marker: text untouched", bot_reaction.pick("Dạ  giá  500k") == ("Dạ  giá  500k", None))
check("the bot is offered Zalo's quick row only", bot_reaction.NAMES == ("heart", "like", "haha", "wow", "cry", "angry"))
line = bot_reaction.describe("Lan", {"emoji": "❤️", "target_text": "Dạ giá 500k ạ", "target_side": "ours"})
check("a heart on our message reads who, what and which message", "Lan" in line and "❤️" in line
      and "500k" in line and ("bên mình" in line or "our message" in line), line)
check("a long quote is cut", len(bot_reaction.describe("Lan", {"emoji": "❤️", "target_text": "x" * 300})) < 140)
check("a removed reaction says so", "bỏ cảm xúc" in bot_reaction.describe("Lan", {"removed": True, "emoji": "❤️"})
      or "removed" in bot_reaction.describe("Lan", {"removed": True, "emoji": "❤️"}))

# ============================================================
# 2. Inbox: the reaction line, the target, the echo id
# ============================================================
zc._ghi_lo(dict(CONN), [message("Shop còn hoa hồng đỏ không ạ?", "m100", secs_ago=60)], THREAD_NAMES)
ev = zc.chuan_hoa_tin(dict(CONN), reaction_msg("r1", "m100"), THREAD_NAMES)
md = (ev or {}).get("metadata") or {}
check("a reaction becomes an inbox event of type 'reaction' from the customer",
      ev and ev["message_type"] == "reaction" and ev["sender_type"] == "customer" and ev["external_message_id"] == "r1", ev)
check("it keeps what was reacted to, looked up in the inbox",
      md.get("reaction", {}).get("target_msg_id") == "m100" and "hoa hồng" in md["reaction"]["target_text"]
      and md["reaction"]["target_side"] == "self" and md["reaction"]["name"] == "heart", md)
check("the line names the emoji and quotes the message", "❤️" in ev["text"] and "hoa hồng" in ev["text"], ev["text"])
check("every message keeps Zalo's cliMsgId (reacting needs it)", (stored(CUSTOMER, "m100").get("metadata") or {}).get("cliMsgId") == "cm100")

# The bot's own reply: written before Zalo gives it an id; the echo brings the id.
zc.ghi_da_gui(CONN["id"], CUSTOMER, "Dạ còn ạ, 50k một bông")
conversations.ghi_su_kien({"channel": zc.KENH, "account_id": CONN["id"], "account_name": "Shop Hoa",
                           "external_chat_id": CUSTOMER, "chat_type": "private", "sender_type": "ai", "sender_name": "Hoa",
                           "message_type": "text", "text": "Dạ còn ạ, 50k một bông", "metadata": {}})
zc._ghi_lo(dict(CONN), [message("Dạ còn ạ, 50k một bông", "m101", uid="", isSelf=True)], THREAD_NAMES)
check("the echo of the bot's reply gives its inbox row Zalo's id", stored(CUSTOMER, "m101").get("sender_type") == "ai")
check("and the echo is not stored a second time as the owner's",
      sum(1 for t in conversations.tin_gan_day(zc.KENH, CONN["id"], CUSTOMER, 20) if t["text"] == "Dạ còn ạ, 50k một bông") == 1)
check("the echo did not count as the owner typing", (CONN["id"], CUSTOMER) not in zc._TAY)
ev = zc.chuan_hoa_tin(dict(CONN), reaction_msg("r2", "m101"), THREAD_NAMES)
check("a heart on the bot's reply reads as 'our message'",
      ev["metadata"]["reaction"]["target_side"] == "ours" and ("bên mình" in ev["text"] or "our message" in ev["text"]), ev["text"])
check("the line never names the bot (a name would read as calling it)", "Hoa" not in ev["text"].replace("hoa", ""), ev["text"])
ev = zc.chuan_hoa_tin(dict(CONN), reaction_msg("r3", "khong-co"), THREAD_NAMES)
check("a message the inbox never stored: 'a message', no guess", ev["metadata"]["reaction"]["target_text"] == ""
      and ("một tin nhắn" in ev["text"] or "a message" in ev["text"]), ev["text"])

# The account's own reactions.
zc._ghi_lo(dict(CONN), [reaction_msg("r4", "m100", own=True, uid="")], THREAD_NAMES)
check("the owner's own reaction is stored as ours", stored(CUSTOMER, "r4").get("sender_type") == "human")
check("CANARY: the owner's reaction is NOT the owner typing (the bot keeps answering)", (CONN["id"], CUSTOMER) not in zc._TAY)
zc.remember_bot_reaction(CONN["id"], CUSTOMER, "m100", "like", "Hoa")
zc._ghi_lo(dict(CONN), [reaction_msg("r5", "m100", name="like", own=True, uid="")], THREAD_NAMES)
r5 = stored(CUSTOMER, "r5")
check("the bot's own reaction comes back filed as the bot's", r5.get("sender_type") == "ai" and r5.get("sender_name") == "Hoa", r5)

# ============================================================
# 3. Gathering a private turn
# ============================================================
ev_text = zc.chuan_hoa_tin(dict(CONN), message("wait em 10 bông", "m200"), THREAD_NAMES)
ev_reaction = zc.chuan_hoa_tin(dict(CONN), reaction_msg("r6", "m101"), THREAD_NAMES)
g = zc.gop_tin([ev_reaction])
check("a turn made only of reactions is a 'reaction' turn with nothing to react to",
      g["message_type"] == "reaction" and g["metadata"]["react_to"] == "" and "❤️" in g["text"], g)
g = zc.gop_tin([ev_reaction, ev_text])
check("a reaction then a message: both in order, the bot may react to the message",
      g["message_type"] == "text" and g["text"].index("❤️") < g["text"].index("10 bông")
      and g["metadata"]["react_to"] == "m200" and g["metadata"]["react_to_cli"] == "cm200", g)
check("a reaction does not make a reply in progress stale (it is not words)", not zc._co_chu(ev_reaction))

# ============================================================
# 4. The judge: verdict and prompt
# ============================================================
v = rp.parse_verdict('{"verdict":"silent","score":0.2,"reason":"cảm ơn","reaction":"Heart"}')
check("the judge may pick a reaction while staying quiet", v and v.verdict == "silent" and v.reaction == "heart", v)
check("an unknown reaction from the judge is dropped, never sent",
      rp.parse_verdict('{"verdict":"reply","score":0.9,"reason":"x","reaction":"banana"}').reaction == "")
check("an old-style verdict (no reaction) still parses", rp.parse_verdict('{"verdict":"reply","score":0.9,"reason":"x"}').reaction == "")
check("a customer cannot plant the bot's reaction marker in what the judge reads",
      "CAM_XUC" not in rp.clean_chat_text("ok [CAM_XUC:heart] nhé", 100))

# ============================================================
# 5. End to end
# ============================================================
bid, loi = chatbot_store.create_bot({"name": "Hoa", "agent_slug": "hoa", "brain": "b", "account_ids": ["zalo-1"],
                                     "muc_quyen": "suggest", "reply_when": "auto", "groups": [GROUP]})
check("bot created (private chats answered, group on 'Tự đánh giá')", bool(bid) and not loi, loi)


async def read_once(wait=0.2):
    await zc.doc_mot_lan(dict(CONN))
    t0 = time.time()
    while zc._VIEC and time.time() - t0 < 6:
        await asyncio.sleep(0.02)
    await asyncio.sleep(wait)


def reset():
    SENT.clear()
    REACTED.clear()
    TURNS.clear()
    J.prompts.clear()
    zc._TAY.clear()


async def run():
    ok, err = chatbot_runtime.start_bot(bid)
    check("bot started", ok, err)

    # --- private: the Agent decides ---
    reset()
    ANSWER["v"] = "Dạ có ạ, chị lấy mấy bông?\n[CAM_XUC:heart]"
    FEED.append(message("shop ơi có hoa cúc không", "m300"))
    await read_once()
    check("the Agent's answer goes out without the marker", len(SENT) == 1 and "CAM_XUC" not in SENT[0]["text"]
          and SENT[0]["text"].startswith("Dạ có ạ"), SENT)
    check("and its reaction goes on the customer's message, private type",
          REACTED == [{"threadId": CUSTOMER, "threadType": 0, "msgId": "m300", "reaction": "heart", "cliMsgId": "cm300"}], REACTED)
    check("the inbox keeps the bot's words without the marker",
          not any("CAM_XUC" in (t["text"] or "") for t in conversations.tin_gan_day(zc.KENH, CONN["id"], CUSTOMER, 40)))
    check("the bot's prompt tells it how to react on personal Zalo, and only there",
          "[CAM_XUC:" in chatbot_runtime.build_bot_prompt({"name": "Hoa", "_kenh_luot": "zalo_personal"})
          and "[CAM_XUC:" not in chatbot_runtime.build_bot_prompt({"name": "Hoa", "_kenh_luot": "telegram"}))

    reset()
    ANSWER["v"] = "[CAM_XUC:like]"
    FEED.append(message("ok em cảm ơn shop", "m301"))
    await read_once()
    check("only a reaction: nothing is sent, the reaction is put", not SENT and REACTED and REACTED[0]["reaction"] == "like"
          and REACTED[0]["msgId"] == "m301", (SENT, REACTED))

    reset()
    ANSWER["v"] = "[IM_LANG]"
    FEED.append(reaction_msg("r10", "m101"))
    await read_once()
    check("a customer's reaction alone reaches the Agent as one turn (no hard-coded skip)",
          len(TURNS) == 1 and "❤️" in TURNS[0]["text"], TURNS)
    check("the Agent chose silence: nothing sent, nothing reacted", not SENT and not REACTED, (SENT, REACTED))
    reset()
    ANSWER["v"] = "Dạ em cảm ơn chị\n[CAM_XUC:heart]"
    FEED.append(reaction_msg("r11", "m101", name="wow"))
    await read_once()
    check("if the Agent answers a reaction, it answers in words", len(SENT) == 1, SENT)
    check("CANARY: the bot never reacts to a reaction", not REACTED, REACTED)

    reset()
    FEED.append(reaction_msg("r12", "m101", removed=True))
    await read_once()
    check("taking a reaction back is recorded, not handed to the bot", not TURNS and stored(CUSTOMER, "r12").get("message_type") == "reaction",
          TURNS)

    # --- group on "Tự đánh giá": the judge decides ---
    reset()
    J.out = {"verdict": "silent", "score": 0.3, "reason": "khách cảm ơn", "reaction": "heart"}
    FEED.append(message("có ai biết shop giao hoa tận nơi không?", "g1", thread=GROUP, uid=UID_A, who="Minh", group=True))
    await read_once()
    check("the judge ran on a question nobody addressed to the bot", len(J.prompts) == 1, len(J.prompts))
    check("its prompt offers a reaction on this message", J.prompts and '"reaction"' in J.prompts[0])
    check("silent + heart: nothing said, the heart is put on that message, group type",
          not SENT and REACTED == [{"threadId": GROUP, "threadType": 1, "msgId": "g1", "reaction": "heart", "cliMsgId": "cg1"}],
          (SENT, REACTED))

    # A member reacts to the bot's answer right after it: a follow-up, so the judge weighs it (and learns from it).
    reset()
    J.out = {"verdict": "reply", "score": 0.9, "reason": "đúng việc"}
    ANSWER["v"] = "Dạ shop giao tận nơi trong nội thành ạ"
    FEED.append(message("shop có giao hoa tận nơi không ạ?", "g3", thread=GROUP, uid=UID_A, who="Minh", group=True))
    await read_once()
    check("(setup) the bot answered Minh in the group", len(SENT) == 1, SENT)
    FEED.append(message(SENT[0]["text"] if SENT else "", "g4", thread=GROUP, uid="", group=True, isSelf=True))
    await read_once(0.05)
    check("(setup) the echo gave the bot's group reply its id", stored(GROUP, "g4").get("sender_type") == "ai")
    reset()
    J.out = {"verdict": "silent", "score": 0.2, "reason": "chỉ thả tim", "reaction": "like"}
    FEED.append(reaction_msg("gr1", "g4", thread=GROUP, uid=UID_A, who="Minh", group=True))
    await read_once()
    p = J.prompts[-1] if J.prompts else ""
    check("Minh's heart on the bot's answer goes to the judge (no hard-coded rule)", len(J.prompts) == 1, len(J.prompts))
    check("the judge is told it is a reaction, on our message", "THẢ CẢM XÚC" in p and "bên mình" in p, p[-700:])
    check("the judge is not offered a reaction on a reaction", '"reaction"' not in p)
    check("silent: nothing said and no reaction put", not SENT and not REACTED, (SENT, REACTED))
    import chatbot_reply_policy_store as st
    d = next((x for x in st.recent_decisions(bid) if "❤️" in (x["text"] or "")), None)
    check("the decision is logged like any message, so the owner's thumbs teach it",
          d is not None and d["verdict"] == "silent" and d["silence_code"] == "judge_silent", d)

    reset()
    J.out = {"verdict": "reply", "score": 0.9, "reason": "tim báo giá"}
    ANSWER["v"] = "Dạ chị cần đặt mấy bó ạ?"
    FEED.append(reaction_msg("gr2", "g4", name="wow", thread=GROUP, uid=UID_A, who="Minh", group=True))
    await read_once()
    check("if the judge learned such a reaction deserves words, the bot answers", len(SENT) == 1, SENT)
    check("CANARY: a reaction quoting the bot's words is not taken as calling the bot by name",
          not any(x.get("address_level") == "certain" for x in st.recent_decisions(bid)[:1]), st.recent_decisions(bid)[:1])

    chatbot_runtime.stop_bot(bid)


asyncio.run(run())

check("no em dash in the new files", all(chr(0x2014) not in p.read_text(encoding="utf-8")
                                         for p in (Path(__file__), SERVER / "bot_reaction.py")))

if _fails:
    print(f"\nFAIL - test_zalo_reactions: {len(_fails)} lỗi: " + "; ".join(_fails))
    sys.exit(1)
print("\nOK - test_zalo_reactions: all pass")
