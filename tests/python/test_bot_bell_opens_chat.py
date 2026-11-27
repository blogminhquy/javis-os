"""A bot's "needs a human" bell opens the customer's chat, and every bot can leave a hard private question (issue #1864).

    python tests/run.py bot_bell_opens_chat      (no network, fake engine and bell)

Checks:
  1. the escalation bell carries `chatbot-chat:<conversation id>` of the customer chat;
  2. a notify that takes only the text (older wiring) still rings;
  3. `escalate_private`: None keeps the old rule (on only with reply_when=auto), True/False decide on any bot,
     a group turn never escalates this way;
  4. the store cleans, saves and clears the field; the create route takes it;
  5. the dashboard: the bell opens the chat through JavisOpenConv, the bot form has the tick and sends it, both
     dictionaries have its words; the inbox keeps the channel of a notice with no session.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bell-chat-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import chatbot_tu_dong  # noqa: E402
import conversations  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(detail) + "]") if detail and not cond else ""))
    if not cond:
        _fails.append(name)


BELL = []


async def _engine(text, meta, progress, *, channel="", bot=None, **kw):
    return {"text": "[BAO_CHU] Khách xin giảm giá, cần chủ quyết.", "files": []}


BRAIN = Path(tempfile.mkdtemp(prefix="brain-bell-chat-"))
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Bán hàng"}, "Trả lời ngắn."),
                     session_probe=lambda key: ("sid", 0), session_undo=lambda key, keep: None,
                     notify=lambda text, channel="": BELL.append((text, channel)))

# A Messenger-like bot: no groups, so the form always saved reply_when=mention. The tick alone turns escalation on.
bid, err = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "muc_quyen": "suggest",
                                     "reply_when": "mention", "escalate_private": "1"})
check("(setup) bot created", bool(bid) and not err, err)
check("store: the tick is saved", chatbot_store.get_bot(bid).get("escalate_private") is True)


def meta(chat="psid-1", name="Chị Hoa"):
    return {"chat_id": chat, "chat_type": "private", "user_id": chat, "user_name": name, "message_id": "",
            "platform": "telegram", "_kenh": "telegram"}


answer = chatbot_runtime._make_answer_fn(bid)
asyncio.run(answer("Lấy 10 thùng giảm 20% được không em?", meta()))
cfg = chatbot_store.get_bot(bid)
aid, kenh = chatbot_runtime._tai_khoan_cua(cfg, meta())
cid = conversations.conversation_id_of(kenh, aid, "psid-1")
check("(setup) the customer chat is stored", cid > 0, cid)
check("an escalation with reply_when=mention still rings, because of the tick", len(BELL) == 1, BELL)
check("the bell names the customer chat", BELL and BELL[-1][1] == f"chatbot-chat:{cid}", BELL[-1:])

# ---- 2. older notify wiring ----------------------------------------------------------------------------
OLD = []
chatbot_runtime._deps["notify"] = lambda text: OLD.append(text)
check("a text-only notify still rings", chatbot_runtime._goi_chu(cfg, "Chị Hoa", "lý do", meta()) and len(OLD) == 1)
chatbot_runtime._deps["notify"] = lambda text, channel="": BELL.append((text, channel))
check("no stored chat: no link, still rings",
      chatbot_runtime._goi_chu(cfg, "X", "lý do", meta("never-seen")) and BELL[-1][1] == "", BELL[-1:])

# ---- 3. the rule ---------------------------------------------------------------------------------------
pe = chatbot_tu_dong.private_escalation
priv, grp = {"chat_type": "private"}, {"chat_type": "group"}
check("unset: on with reply_when=auto (old rule)", pe({"reply_when": "auto"}, priv) is True)
check("unset: off otherwise (old rule)", pe({"reply_when": "mention"}, priv) is False)
check("ticked: on whatever reply_when says", pe({"reply_when": "mention", "escalate_private": True}, priv) is True)
check("unticked: off even in Tự đánh giá", pe({"reply_when": "auto", "escalate_private": False}, priv) is False)
check("a group turn never escalates this way", pe({"escalate_private": True}, grp) is False)

# ---- 4. store and route --------------------------------------------------------------------------------
c = chatbot_store.clean_escalate_private
check("clean: blank is unset, on/off read", c("") is None and c(None) is None and c("1") is True and c("0") is False)
chatbot_store.update_bot(bid, {"escalate_private": "0"})
check("update: unticked is saved", chatbot_store.get_bot(bid).get("escalate_private") is False)
chatbot_store.update_bot(bid, {"escalate_private": ""})
check("update: blank goes back to the old rule", chatbot_store.get_bot(bid).get("escalate_private") is None)
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("create route takes the field", 'escalate_private: str = Form("")' in main_src
      and '"escalate_private": escalate_private' in main_src)
check("the bell's channel reaches the inbox", "channel=channel))" in main_src
      and 'kenh = str(channel or "") if not sid else ""' in main_src)

# ---- 5. dashboard --------------------------------------------------------------------------------------
nt = (ROOT / "dashboard" / "notifications.js").read_text(encoding="utf-8")
check("the bell opens the customer chat", "chatbot-chat:" in nt and "window.JavisOpenConv(" in nt)
js = (ROOT / "dashboard" / "chatbots.js").read_text(encoding="utf-8")
check("form: the tick is drawn and saved", 'id="cbEscPrivate"' in js and "escalate_private:" in js)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"i18n {lang}: the tick's words exist", bool(d.get("cb.esc_private")) and bool(d.get("cb.hint_esc_private")))

check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
