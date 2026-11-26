"""Never silently drop an owner bell (issue #1838).

    python tests/run.py escalation_bell      (no network, fake engine and bell)

When the bot leaves a hard message to the owner ([BAO_CHU]), the customer gets no reply and the owner is told in the
Javis bell. Only one bell per chat every 10 minutes used to ring; an escalation inside that gap was dropped, so a
customer nobody answered stayed unseen. Checks:
  1. the setting: `bell_gap_min` (minutes, 0 = every time, blank = default 10) is cleaned, saved, cleared;
  2. the first escalation rings at once;
  3. escalations inside the gap ring ONCE when the gap ends, with how many and the latest message;
  4. no follow-up ring when a person answered the customer meanwhile;
  5. `bell_gap_min = 0` rings every escalation; a bot's own gap is used;
  6. the form has the control and both dictionaries have its words.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bell-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. the setting ---------------------------------------------------------------------------------
check("clean: blank and junk are unset", chatbot_store.clean_bell_gap("") is None
      and chatbot_store.clean_bell_gap(None) is None and chatbot_store.clean_bell_gap("abc") is None
      and chatbot_store.clean_bell_gap(True) is None)
check("clean: 0 and a number are kept", chatbot_store.clean_bell_gap("0") == 0 and chatbot_store.clean_bell_gap(15) == 15)
check("clean: out of range is unset", chatbot_store.clean_bell_gap(-1) is None
      and chatbot_store.clean_bell_gap(chatbot_store.BELL_GAP_MAX + 1) is None)

BELL, CALLS = [], []
REPLY = {"v": "[BAO_CHU] Khách xin giảm giá, cần chủ quyết."}


async def _engine(text, meta, progress, *, channel="", bot=None, **kw):
    CALLS.append(text)
    return {"text": REPLY["v"], "files": []}


BRAIN = Path(tempfile.mkdtemp(prefix="brain-bell-"))
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Bán hàng"}, "Trả lời ngắn."),
                     session_probe=lambda key: ("sid", 0), session_undo=lambda key, keep: None,
                     notify=lambda text: BELL.append(text))
bid, err = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "muc_quyen": "suggest",
                                     "reply_when": "auto", "bell_gap_min": "x"})
check("(setup) bot created", bool(bid) and not err, err)
check("create: an unreadable gap is saved as unset", chatbot_store.get_bot(bid).get("bell_gap_min") is None)
chatbot_store.update_bot(bid, {"bell_gap_min": "25"})
check("update: a gap is saved", chatbot_store.get_bot(bid).get("bell_gap_min") == 25)
cfg = chatbot_store.get_bot(bid)
check("the bot's own gap is used", chatbot_runtime.bell_gap_seconds(cfg) == 25 * 60)
chatbot_store.update_bot(bid, {"bell_gap_min": "999"})
check("update: an invalid gap keeps the old one", chatbot_store.get_bot(bid).get("bell_gap_min") == 25)
chatbot_store.update_bot(bid, {"bell_gap_min": ""})
check("update: blank clears it", chatbot_store.get_bot(bid).get("bell_gap_min") is None)
check("unset: the default gap", chatbot_runtime.bell_gap_seconds(chatbot_store.get_bot(bid))
      == chatbot_runtime.BAO_CHU_BELL_GAP_S)

answer = chatbot_runtime._make_answer_fn(bid)


def meta(chat="u1", name="Chị Hoa"):
    return {"chat_id": chat, "chat_type": "private", "user_id": chat, "user_name": name, "message_id": "",
            "platform": "telegram", "_kenh": "telegram"}


def end_gap_soon(chat, seconds=0.3):
    """Pretend the chat's last bell rang so long ago that its gap ends in `seconds`."""
    key = (bid, chat)
    gap = chatbot_runtime.bell_gap_seconds(chatbot_store.get_bot(bid))
    chatbot_runtime._BAO_CHU_BELL[key] = time.time() - gap + seconds


async def scenario_hold():
    await answer("Lấy 10 thùng giảm 20% được không em?", meta())
    first = len(BELL)
    end_gap_soon("u1")
    await answer("Thế 15 thùng thì sao?", meta())
    await answer("Hay 20 thùng giảm 30%?", meta())
    held = len(BELL)
    await asyncio.sleep(0.8)
    return first, held, len(BELL)


first, held, after = asyncio.run(scenario_hold())
check("first escalation rings at once", first == 1, BELL)
check("escalations inside the gap do not ring at once", held == 1, BELL)
check("...and ring ONCE when the gap ends", after == 2, BELL)
check("the follow-up says how many and shows the latest message",
      len(BELL) == 2 and "2" in BELL[-1] and "20 thùng giảm 30%" in BELL[-1] and "Chị Hoa" in BELL[-1], BELL[-1:])
check("nothing is left held", not chatbot_runtime._BELL_HELD and not chatbot_runtime._BELL_TASKS)


async def scenario_answered():
    await answer("Đổi trả lô hôm qua được không em?", meta("u2", "Anh Nam"))
    n = len(BELL)
    end_gap_soon("u2")
    await answer("Anh cần đổi gấp nhé", meta("u2", "Anh Nam"))
    cfg = chatbot_store.get_bot(bid)
    conversations.ghi_su_kien(chatbot_runtime._bot_event(cfg, meta("u2", "Anh Nam"), sender_type="human",
                                                         sender_name="Chủ shop", message_type="text",
                                                         text="Dạ anh gửi ảnh lô hàng giúp em ạ"))
    await asyncio.sleep(0.8)
    return n, len(BELL)


n, after = asyncio.run(scenario_answered())
check("a person answered the customer meanwhile: no follow-up ring", n == 3 and after == 3, BELL)

chatbot_store.update_bot(bid, {"bell_gap_min": "0"})
n = len(BELL)
asyncio.run(answer("Câu khó một", meta("u3", "Khách 3")))
asyncio.run(answer("Câu khó hai", meta("u3", "Khách 3")))
check("bell_gap_min = 0 rings every escalation", len(BELL) == n + 2, BELL)

# ---- 6. the form ------------------------------------------------------------------------------------
js = (ROOT / "dashboard" / "chatbots.js").read_text(encoding="utf-8")
check("form: the bell gap control is saved", 'id="cbBellGap"' in js and "bell_gap_min: bell" in js)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"i18n {lang}: the control's words exist",
          all(d.get(k) for k in ("cb.bell_gap", "cb.ph_bell_gap", "cb.hint_bell_gap", "cb.bell_gap_sai")))
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("create route accepts the setting", 'bell_gap_min: str = Form("")' in main_src and '"bell_gap_min": bell_gap_min' in main_src)

check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
