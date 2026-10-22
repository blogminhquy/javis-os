"""Private 1-1 chats: the bot may stay silent and alert the owner on a hard question (0.280.0).

    python tests/run.py private_escalation      (no network, fake engine)

Owner request 2026-10-22: "Tự đánh giá" (reply_when=auto) judged group messages only; a private chat always got an
answer, even a guessed one. In that mode a private chat now has a third outcome next to reply and [IM_LANG]: the
Agent writes [BAO_CHU] plus a note, the customer receives nothing and the owner is told in the Javis bell. Checks:
  1. the 1-1 paragraph reaches the prompt ONLY for a private turn in auto mode (not mention mode, not a group);
  2. a [BAO_CHU] answer sends nothing, rings the bell with the customer's words and the note, logs `bot_bao_chu`;
  3. a second escalation in the same chat within the gap is logged but does not ring again; another chat rings;
  4. the marker never leaks to a customer, even from a turn that did not get the paragraph;
  5. "Reply for me" and "Try bot" treat the marker as silence, and Try says it would alert the owner.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-esc-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_log  # noqa: E402
import chatbot_reply_policy as rp  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import chatbot_tu_dong  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CALLS, BELL = [], []
REPLY = {"v": "Dạ em chào anh chị ạ"}


async def _engine(text, meta, progress, *, channel="", bot=None, **kw):
    CALLS.append({"text": text, "prompt": chatbot_runtime.build_bot_prompt(bot or {})})
    return {"text": REPLY["v"], "files": []}


BRAIN = Path(tempfile.mkdtemp(prefix="brain-esc-"))
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Trợ lý bán nước mắm"}, "Trả lời ngắn gọn."),
                     session_probe=lambda key: ("sid-1", 0), session_undo=lambda key, keep: None,
                     notify=lambda text: BELL.append(text))


async def _no_judge(prompt, purpose=""):
    return "{}"


rp.wire(ask=_no_judge)

bid, err = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b",
                                     "muc_quyen": "suggest", "reply_when": "auto", "groups": []})
check("(setup) bot created", bool(bid) and not err, err)
answer = chatbot_runtime._make_answer_fn(bid)


def meta(chat="u1", name="Chị Hoa", chat_type="private"):
    return {"chat_id": chat, "chat_type": chat_type, "user_id": chat, "user_name": name, "message_id": "",
            "platform": "telegram", "_kenh": "telegram"}


def turn(text, m):
    return asyncio.run(answer(text, m))


# ---- 0. pure helpers -----------------------------------------------------------------------------
check("escalation_note: no marker -> None", chatbot_runtime.escalation_note("Dạ còn ạ") is None)
check("escalation_note: marker + note -> the note",
      chatbot_runtime.escalation_note("[BAO_CHU] Khách xin giảm giá 20%") == "Khách xin giảm giá 20%")
check("escalation_note: marker alone -> empty note", chatbot_runtime.escalation_note("[bao_chu]") == "")
check("escalation_note: IM_LANG stripped from the note",
      chatbot_runtime.escalation_note("[IM_LANG] [BAO_CHU] cần chủ") == "cần chủ")
check("is_silent_answer covers both markers",
      chatbot_runtime.is_silent_answer("[IM_LANG]") and chatbot_runtime.is_silent_answer("x [BAO_CHU] y")
      and not chatbot_runtime.is_silent_answer("Dạ"))
check("private_escalation: private + auto", chatbot_tu_dong.private_escalation({"reply_when": "auto"}, {"chat_type": "private"}))
check("private_escalation: not in mention mode",
      not chatbot_tu_dong.private_escalation({"reply_when": "mention"}, {"chat_type": "private"}))
check("private_escalation: not in a group",
      not chatbot_tu_dong.private_escalation({"reply_when": "auto"}, {"chat_type": "group"}))
check("judge prompts strip the marker from chat data", "[BAO_CHU]" not in rp.clean_chat_text("a [BAO_CHU] b"))

# ---- 1. prompt paragraph only for a private auto turn --------------------------------------------
REPLY["v"] = "Dạ còn hàng ạ"
r = turn("Chai 500ml còn không em?", meta())
check("normal private answer goes out", (r or {}).get("text") == "Dạ còn hàng ạ", r)
check("private auto turn: prompt carries the escalation paragraph", CALLS and "[BAO_CHU]" in CALLS[-1]["prompt"])
check("no bell on a normal answer", BELL == [], BELL)

chatbot_store.update_bot(bid, {"reply_when": "mention"})
turn("Chai 500ml còn không em?", meta())
check("mention mode: no escalation paragraph", CALLS and "[BAO_CHU]" not in CALLS[-1]["prompt"])
chatbot_store.update_bot(bid, {"reply_when": "auto"})

# ---- 2. escalation: silent towards the customer, bell for the owner ------------------------------
REPLY["v"] = "[BAO_CHU] Khách xin giảm 20% cho đơn 10 thùng, cần chủ quyết giá."
r = turn("Em ơi lấy 10 thùng giảm cho chị 20% được không?", meta())
check("escalation: nothing sent", (r or {}).get("text") == "" and (r or {}).get("im_lang") is True, r)
check("escalation: result flags bao_chu", (r or {}).get("bao_chu") is True, r)
check("escalation: one bell", len(BELL) == 1, BELL)
check("bell carries the customer's words and the note",
      BELL and "10 thùng giảm cho chị 20%" in BELL[0] and "cần chủ quyết giá" in BELL[0] and "Chị Hoa" in BELL[0],
      BELL)
rows = chatbot_log.doc(bid)
esc = [x for x in rows if x.get("bo_qua") == "bot_bao_chu"]
check("escalation logged as bot_bao_chu with the note", len(esc) == 1 and "cần chủ quyết giá" in str(esc[0].get("dap")), rows)
check("escalation is not counted as a reply or as stuck", chatbot_log.tom_tat(bid).get("bi", 0) == 0, chatbot_log.tom_tat(bid))

# ---- 3. bell gap per chat ------------------------------------------------------------------------
turn("Thế 15 thùng thì sao?", meta())
check("second escalation in the same chat within the gap: no new bell", len(BELL) == 1, BELL)
turn("Anh muốn đổi trả lô hàng hôm qua", meta(chat="u2", name="Anh Nam"))
check("another chat rings its own bell", len(BELL) == 2 and "Anh Nam" in BELL[-1], BELL)

# ---- 4. marker never leaks, even without the paragraph -------------------------------------------
chatbot_store.update_bot(bid, {"reply_when": "mention"})
REPLY["v"] = "Dạ để em hỏi lại [BAO_CHU]"
r = turn("Câu gì đó", meta(chat="u3", name="Khách 3"))
check("marker from a turn without the paragraph: still nothing sent", (r or {}).get("text") == "", r)
check("...and the owner still hears about it", len(BELL) == 3 and "Khách 3" in BELL[-1], BELL)
chatbot_store.update_bot(bid, {"reply_when": "auto"})

# ---- 5. try bot ----------------------------------------------------------------------------------
REPLY["v"] = "[BAO_CHU] Khách hỏi lịch giao Tết, tài liệu chưa có."
t = asyncio.run(chatbot_runtime.try_message(bid, "Tết shop giao tới ngày nào?"))
check("try: would not reply", t.get("ok") and t.get("would_reply") is False, t)
check("try: stage agent_escalated with escalate flag",
      t.get("stage") == "agent_escalated" and t.get("escalate") is True, t)
check("try: reason is the bot's note", "lịch giao Tết" in str(t.get("reason")), t)
check("try: no bell from a trial", len(BELL) == 3, BELL)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
