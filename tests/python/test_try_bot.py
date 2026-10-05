"""Try bot (0.78.0): test a message against a bot WITHOUT sending anything or leaving any trace.

    python tests/run.py try_bot      (no network)

Owner request (2026-10-05): a Telegram bot added to a group stayed silent and there was no way to
check the bot short of messaging the real group. The Try button runs the same steps a real
message goes through (who-may-speak gate, the group reply judge, the Agent's answer) and shows
the outcome, but:
  1. nothing is sent to any channel and nothing is written to the Inbox or the bot log;
  2. the reply judge does not log a decision (it would skew self-learning and self-review);
  3. rate limits are neither checked nor consumed;
  4. the Agent runs read-only even when the bot is set to a higher level, so a test can never
     place an order or send a message through a tool;
  5. the engine session is left clean (draft mode: no store write, RAM history undone).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-try-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_log  # noqa: E402
import chatbot_reply_policy as rp  # noqa: E402
import chatbot_reply_policy_store as st  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import chatbot_tu_dong  # noqa: E402
import conversations  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CALLS, UNDO = [], []
REPLY = {"v": "Dạ, để em hướng dẫn nhé."}


async def _engine(text, meta, progress, *, channel="", bot=None, **kw):
    CALLS.append({"text": text, "meta": dict(meta or {}), "bot": dict(bot or {}), "kw": kw})
    v = REPLY["v"]
    return v if isinstance(v, str) and v.startswith("ERR:") else {"text": v, "files": []}


BRAIN = Path(tempfile.mkdtemp(prefix="brain-try-"))
(BRAIN / "cai-dat.md").write_text(
    "# Hướng dẫn cài đặt Javis\n\n## Lỗi cổng 7777 đang được dùng\n\nNếu Javis báo lỗi cổng 7777 đang được dùng, "
    "hãy tắt tiến trình Javis cũ rồi khởi động lại bằng file start-javis.bat.\n", encoding="utf-8")
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Trợ lý cài đặt Javis"}, "Trả lời ngắn gọn."),
                     session_probe=lambda key: ("sid-1", 3), session_undo=lambda key, keep: UNDO.append((key, keep)))


class Judge:
    def __init__(self):
        self.verdict = "silent"
        self.calls = 0

    async def __call__(self, prompt, purpose=""):
        if purpose == "profile":
            return "Đảm nhiệm:\n- cài đặt Javis\nKhông đảm nhiệm:\n- chuyện riêng"
        if purpose == "bootstrap":
            return json.dumps([{"text": "javis lỗi cổng thì làm sao", "verdict": "reply", "reason": "đúng ngành"}])
        if purpose == "teach":
            return json.dumps({"is_teaching": False})
        self.calls += 1
        if self.verdict == "reply":
            return json.dumps({"verdict": "reply", "score": 0.92, "reason": "câu hỏi đúng chuyên môn"})
        return json.dumps({"verdict": "silent", "score": 0.2, "reason": "chuyện phiếm, không phải việc của bot"})


J = Judge()
rp.wire(ask=J)


def run(*a, **k):
    return asyncio.run(chatbot_runtime.try_message(*a, **k))


bid, err = chatbot_store.create_bot({"name": "Javis Vũ", "agent_slug": "lan", "brain": "b",
                                     "muc_quyen": "suggest", "reply_when": "mention", "groups": []})
check("(setup) bot created", bool(bid) and not err, err)
chatbot_store.update_bot(bid, {"muc_quyen": "full", "xac_nhan_rui_ro": True})
check("(setup) bot is set to full permission", chatbot_store.get_bot(bid).get("muc_quyen") == "full")

# ---- 1. Private message: answered, read-only, clean session --------------------------------------
r = run(bid, "Javis báo lỗi cổng 7777 thì làm sao?")
check("private: ok and would reply", r.get("ok") and r.get("would_reply") is True and r.get("stage") == "answered", r)
check("private: returns the Agent's answer", r.get("text") == REPLY["v"], r)
check("private: lists the documents it found", any("cai-dat" in str(s) for s in (r.get("sources") or [])), r.get("sources"))
check("engine ran once", len(CALLS) == 1, CALLS)
check("engine ran READ-ONLY although the bot is set to full", CALLS and CALLS[0]["bot"].get("muc_quyen") == "suggest",
      CALLS and CALLS[0]["bot"].get("muc_quyen"))
check("result says tools were limited to read-only", "readonly_tools" in (r.get("notes") or []), r.get("notes"))
check("engine ran in draft mode (no session store write)",
      CALLS and CALLS[0]["kw"].get("ghi_kho") is False and CALLS[0]["kw"].get("phien_kho") == "sid-1", CALLS and CALLS[0]["kw"])
check("RAM history undone after the turn", len(UNDO) == 1 and UNDO[0][1] == 3, UNDO)
check("the real bot record was not changed", chatbot_store.get_bot(bid).get("muc_quyen") == "full")

# ---- 2. Group, mention mode, not called -> gate --------------------------------------------------
CALLS.clear()
r = run(bid, "hôm nay trời đẹp ghê", chat_type="group", mentioned=False)
check("group, not called, mention mode: would stay silent at the gate",
      r.get("ok") and r.get("would_reply") is False and r.get("stage") == "gate" and r.get("code") == "khong_goi_ten", r)
check("gate result has a readable reason", bool(r.get("reason")), r)
check("gate: engine not called", CALLS == [])
check("group with no allowed group: assumed allowed, and the result says so",
      "group_assumed_allowed" in (r.get("notes") or []), r.get("notes"))

# ---- 3. Group, called by @tag -> answered ---------------------------------------------------------
r = run(bid, "@Javis Vũ lỗi cổng 7777 xử lý sao", chat_type="group", mentioned=True)
check("group, tagged: answered", r.get("would_reply") is True and r.get("stage") == "answered" and len(CALLS) == 1, r)
check("group: the engine sees who is speaking like a real group turn",
      CALLS and CALLS[-1]["meta"].get("chat_type") == "group", CALLS and CALLS[-1]["meta"])

# ---- 4. Auto mode: the reply judge decides, nothing is logged -----------------------------------
chatbot_store.update_bot(bid, {"reply_when": "auto"})
CALLS.clear()
J.verdict = "silent"
r = run(bid, "Javis báo lỗi cổng 7777 thì làm sao ạ?", chat_type="group", mentioned=False)
check("auto, judge says silent: would stay silent, stage judge",
      r.get("would_reply") is False and r.get("stage") == "judge" and r.get("code") in ("judge_silent", "below_threshold"), r)
check("judge result carries the judge's reason and score", "chuyện phiếm" in str(r.get("reason")) and r.get("score") == 0.2, r)
check("judge asked once, engine not called", J.calls == 1 and CALLS == [], (J.calls, CALLS))
J.verdict = "reply"
r = run(bid, "Javis báo lỗi cổng 7777 thì làm sao ạ?", chat_type="group", mentioned=False)
check("auto, judge says reply: answered with the Agent's text",
      r.get("would_reply") is True and r.get("stage") == "answered" and r.get("text") == REPLY["v"], r)
check("answered result keeps the judge's score", r.get("score") == 0.92, r)

# ---- 5. Agent chooses silence, engine failure --------------------------------------------------
REPLY["v"] = chatbot_runtime.IM_LANG
r = run(bid, "chào cả nhà", chat_type="private")
check("Agent writes the silence marker: would stay silent, stage agent_silent",
      r.get("ok") and r.get("would_reply") is False and r.get("stage") == "agent_silent", r)
REPLY["v"] = "ERR: engine is down"
r = run(bid, "chào cả nhà", chat_type="private")
check("engine failure: not ok, code engine, reason kept for the owner", not r.get("ok") and r.get("code") == "engine"
      and "engine is down" in str(r.get("error")), r)
REPLY["v"] = "Dạ, để em hướng dẫn nhé."

# ---- 6. Input checks ---------------------------------------------------------------------------
check("unknown bot: no_bot", run("khong-co", "xin chào").get("code") == "no_bot")
check("empty message: no_message", run(bid, "   ").get("code") == "no_message")
r = run(bid, "x" * 5000)
check("very long message is cut, not rejected", r.get("ok"), r)
check("engine got at most 2000 characters", CALLS and len(CALLS[-1]["text"]) <= 2100, CALLS and len(CALLS[-1]["text"]))

# ---- 7. NO TRACE anywhere -----------------------------------------------------------------------
decisions = st.recent_decisions(bid) if st.db_path().exists() else []
check("reply judge logged NO decision for any try", decisions == [], decisions)
check("bot log has no entry", chatbot_log.doc(bid) == [], chatbot_log.doc(bid))
inbox = conversations.danh_sach(bot_id=bid)
inbox = inbox.get("items", inbox) if isinstance(inbox, dict) else inbox
check("Inbox has no conversation for this bot", not inbox, inbox)
check("auto-reply rate counters untouched",
      chatbot_tu_dong.duoc_tra_loi(bid, chatbot_runtime.TRY_CHAT_ID, chatbot_runtime.TRY_USER_ID) == "")

# ---- 8. Telegram privacy note (pure helper) ---------------------------------------------------
tg = {"accounts": [{"id": "a1", "channel": "telegram"}]}
check("Telegram, privacy on, group message not addressed to the bot -> warn",
      "telegram_privacy" in chatbot_runtime.try_notes(tg, {"chat_type": "group"},
                                                      {"da_hoi_telegram": True, "doc_moi_tin_nhom": False}))
check("Telegram, privacy off -> no warning",
      "telegram_privacy" not in chatbot_runtime.try_notes(tg, {"chat_type": "group"},
                                                          {"da_hoi_telegram": True, "doc_moi_tin_nhom": True}))
check("Telegram, a reply to the bot always arrives -> no warning",
      "telegram_privacy" not in chatbot_runtime.try_notes(tg, {"chat_type": "group", "reply_to_bot": True},
                                                          {"da_hoi_telegram": True, "doc_moi_tin_nhom": False}))
check("Zalo bot -> never a Telegram warning",
      "telegram_privacy" not in chatbot_runtime.try_notes({"accounts": [{"id": "z", "channel": "zalo_personal"}]},
                                                          {"chat_type": "group"},
                                                          {"da_hoi_telegram": True, "doc_moi_tin_nhom": False}))

# ---- 9. HTTP route -----------------------------------------------------------------------------
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan"}, "Trả lời ngắn gọn."),
                     session_probe=lambda key: ("", 0), session_undo=lambda key, keep: None)
c = TestClient(main.app)
res = c.post(f"/chatbots/{bid}/try", data={"text": "@Javis Vũ chào em", "chat_type": "group", "mentioned": "1"})
check("POST /chatbots/{id}/try answers", res.status_code == 200 and res.json().get("would_reply") is True, res.text)
check("POST unknown bot -> 404", c.post("/chatbots/khong-co/try", data={"text": "hi"}).status_code == 404)

# ---- 10. UI ------------------------------------------------------------------------------------
js = (ROOT / "dashboard" / "chatbots-try.js").read_text(encoding="utf-8")
html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
cb = (ROOT / "dashboard" / "chatbots.js").read_text(encoding="utf-8")
check("UI file is loaded by the page", "/static/chatbots-try.js" in html)
check("bot card has a Try button wired to the panel", "cb-try" in cb and "JavisTryBot" in cb)
check("UI posts to the try route", "/try" in js and "FormData" in js)
check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

print()
if _fails:
    print(f"{len(_fails)} FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All try_bot tests passed.")
