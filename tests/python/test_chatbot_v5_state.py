"""Chatbot v5 groundwork (owner, 2026-10-28; docs/dev/2026-10-chatbot-v5-spec.md sections 3 to 5).

    python tests/run.py chatbot_v5_state      (no network)

Pins the server side of the new Chatbot page:
  1. `chatbot_store.chat_allowed` / `allow_patch`: switching the bot on or off in ONE chat keeps the audience as it is
     (lists for chats the audience does not cover, `blocked` for chats it does).
  2. The live turn stays silent with code `chat_tat` in a blocked chat.
  3. `inbox_state.state`: every who / who_code case.
  4. The inbox store: "draft" is a mode, drafts are saved, replaced and cleared, "need reply" counts a draft-mode chat,
     and the list filters by several accounts, by ids and by tags any / none.
  5. Draft mode in the live turn: the reply is kept on the conversation, nothing is sent or recorded as the bot's words.
  6. Routes: the list carries who fields and who_counts and filters by `who` and `account_ids`; POST /ai switches one
     chat; /mode leaving draft drops the draft; /draft discard and send; /ai-reply passes the owner's instruction.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-cbv5-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import inbox_state  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)

# ---- 1. allow / block one chat -------------------------------------------------------------------------------------
nhom = {"audience": "nhom", "groups": ["-100"], "people": [], "blocked": []}
check("nhom: private chat allowed by default", chatbot_store.chat_allowed(nhom, "private", "111"))
check("nhom: listed group allowed", chatbot_store.chat_allowed(nhom, "group", "-100"))
check("nhom: other group not allowed", not chatbot_store.chat_allowed(nhom, "group", "-200"))
p = chatbot_store.allow_patch(nhom, "private", "111", False)
check("nhom: switching a private chat off blocks it", p == {"blocked": ["111"], "people": []}, p)
check("nhom: blocked private chat no longer allowed", not chatbot_store.chat_allowed(dict(nhom, **p), "private", "111"))
p2 = chatbot_store.allow_patch(dict(nhom, **p), "private", "111", True)
check("nhom: switching it back on unblocks without listing", p2 == {"blocked": [], "people": []}, p2)
p = chatbot_store.allow_patch(nhom, "group", "-200", True)
check("nhom: switching a group on lists it", p == {"blocked": [], "groups": ["-100", "-200"]}, p)
p = chatbot_store.allow_patch(nhom, "group", "-100", False)
check("nhom: switching a listed group off unlists it, no block needed", p == {"blocked": [], "groups": []}, p)
chon = {"audience": "chon", "groups": [], "people": ["5"]}
check("chon: unlisted person not allowed", not chatbot_store.chat_allowed(chon, "private", "6"))
check("chon: switching a person on lists them", chatbot_store.allow_patch(chon, "private", "6", True)["people"] == ["5", "6"])
moi = {"audience": "all", "groups": []}
check("all: any group allowed", chatbot_store.chat_allowed(moi, "group", "-9"))
p = chatbot_store.allow_patch(moi, "group", "-9", False)
check("all: switching a group off blocks it", p["blocked"] == ["-9"], p)
check("no bot: nothing allowed", not chatbot_store.chat_allowed(None, "private", "1"))

# ---- 2. the live turn in a blocked chat ------------------------------------------------------------------------------
cfg = {"audience": "nhom", "blocked": ["777"], "reply_when": "mention"}
check("blocked private chat: silent with chat_tat",
      chatbot_runtime._ly_do_im_co_ban(cfg, {"chat_type": "private", "chat_id": "777"}) == "chat_tat")
check("other private chat still answered", chatbot_runtime._ly_do_im_co_ban(cfg, {"chat_type": "private", "chat_id": "8"}) == "")

# ---- 3. who is handling it -----------------------------------------------------------------------------------------
bot = {"audience": "nhom", "groups": [], "people": [], "blocked": []}
row = {"external_chat_id": "1", "chat_type": "private", "mode": "ai", "metadata": {}}
grp = {"external_chat_id": "-5", "chat_type": "group", "mode": "ai", "metadata": {}}


def who(r, b=bot, running=True, pending=None, waiting=False, **kw):
    s = inbox_state.state(r, b, running, pending, waiting, **kw)
    return s["who"], s["who_code"]


check("ai: allowed, running", who(row) == ("ai", "ai"))
check("ai: customer waiting still ai (the bot is on it)", who(row, waiting=True) == ("ai", "ai"))
check("bot off: log", who(row, running=False) == ("log", "bot_off"))
check("bot off and waiting: needs you", who(row, running=False, waiting=True) == ("you", "bot_off_waiting"))
check("human: you are handling it", who(dict(row, mode="human")) == ("owner", "you"))
check("human and waiting: needs you", who(dict(row, mode="human"), waiting=True) == ("you", "waiting_you"))
check("draft mode, nothing written yet: ai", who(dict(row, mode="draft")) == ("ai", "draft_mode"))
check("draft waiting: needs you", who(dict(row, mode="draft", metadata={"draft": {"text": "Dạ"}})) == ("you", "draft_ready"))
check("draft waiting in a not-allowed chat (owner's order): needs you",
      who(dict(grp, metadata={"draft": {"text": "Dạ"}})) == ("you", "draft_ready"))
check("group not allowed: log", who(grp) == ("log", "not_allowed"))
check("group not allowed, someone called the bot: needs you", who(grp, pending={"-5": 2}) == ("you", "pending"))
s = inbox_state.state(grp, bot, True, {"-5": 2})
check("pending count travels", s["pending"] == 2 and s["ai_allowed"] is False, s)
check("no bot: log no_bot", who(row, b=None) == ("log", "no_bot"))
check("no bot, owner said none needed", who(row, b=None, no_bot_wanted=True) == ("log", "no_bot_wanted"))
check("no bot and waiting: needs you", who(row, b=None, waiting=True) == ("you", "waiting"))
check("count", inbox_state.count([{"who": "ai"}, {"who": "you"}, {"who": "ai"}]) == {"you": 1, "ai": 2, "owner": 0, "log": 0})

# ---- 4. the inbox store ----------------------------------------------------------------------------------------------
check("draft is a conversation mode", "draft" in conversations.CHE_DO)


def ev(acc, chat, text, kind="customer", ctype="private", bot_id=""):
    return conversations.ghi_su_kien({"channel": "telegram", "account_id": acc, "external_chat_id": chat, "chat_type": ctype,
                                      "chat_title": "Nhóm " + chat if ctype == "group" else "", "sender_type": kind,
                                      "sender_id": "u" + chat, "sender_name": "Khách " + chat, "text": text, "bot_id": bot_id})


r1 = ev("acc1", "1", "Còn hàng không?")
r2 = ev("acc2", "2", "Giá sao shop?")
r3 = ev("acc3", "3", "Ship không?")
c1 = r1["conversation_id"]
check("save_draft", conversations.save_draft(c1, "Dạ còn ạ", 5, "báo còn hàng"))
d = conversations.draft_of(conversations.chi_tiet(c1))
check("draft read back", d and d["text"] == "Dạ còn ạ" and d["for_message_id"] == 5 and d["instruction"] == "báo còn hàng", d)
conversations.save_draft(c1, "Dạ còn 3 chai ạ")
check("newer draft replaces older", conversations.draft_of(conversations.chi_tiet(c1))["text"] == "Dạ còn 3 chai ạ")
check("empty draft refused", not conversations.save_draft(c1, "   "))
conversations.clear_draft(c1)
check("clear_draft", conversations.draft_of(conversations.chi_tiet(c1)) is None)
conversations.dat_che_do(c1, "draft")
check("need reply counts a draft-mode chat", conversations.can_tra_loi(conversations.chi_tiet(c1)))
ids = {c["id"] for c in conversations.danh_sach(account_ids=["telegram:acc1", "telegram:acc3"])}
check("account_ids keeps only those accounts", ids == {c1, r3["conversation_id"]}, ids)
ids = [c["id"] for c in conversations.danh_sach(ids=[r2["conversation_id"]])]
check("ids keeps only those conversations", ids == [r2["conversation_id"]], ids)
check("ids=[] keeps nothing", conversations.danh_sach(ids=[]) == [])
tag, _ = conversations.create_tag("VIP", "green")
conversations.set_conversation_tag(r2["conversation_id"], tag["id"], True)
ids = {c["id"] for c in conversations.danh_sach(tags_any=[str(tag["id"])])}
check("tags_any", ids == {r2["conversation_id"]}, ids)
ids = {c["id"] for c in conversations.danh_sach(tags_none=[str(tag["id"])])}
check("tags_none", r2["conversation_id"] not in ids and c1 in ids, ids)
light = conversations.state_rows(account_ids=["telegram:acc1"])
check("state_rows: light columns with metadata", light and set(light[0]) >= {"id", "mode", "metadata", "channel_account_id"}
      and "customer_name" not in light[0], light[:1])

# ---- 5. draft mode in the live turn -------------------------------------------------------------------------------
BRAIN = Path(tempfile.mkdtemp(prefix="brain-cbv5-"))


async def _engine(text, meta, progress, *, channel="", bot=None, **kw):
    return {"text": "Dạ shop còn hàng ạ.", "files": []}


chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Bán hàng"}, "Trả lời ngắn."),
                     session_probe=lambda key: ("sid", 0), session_undo=lambda key, keep: None)
bid, err = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "muc_quyen": "suggest",
                                     "audience": "nhom"})
check("(setup) bot created", bool(bid) and not err, err)
answer = chatbot_runtime._make_answer_fn(bid)
M = {"chat_id": "900", "chat_type": "private", "user_id": "900", "user_name": "Chị Hoa", "message_id": "",
     "account_id": "", "platform": "telegram", "_kenh": "telegram"}
out = asyncio.run(answer("Còn hàng không em?", dict(M)))
check("ai mode: the reply goes out", (out or {}).get("text") == "Dạ shop còn hàng ạ.", out)
conv = [c for c in conversations.danh_sach(limit=50) if c.get("external_chat_id") == "900"]
check("(setup) the turn made a conversation", len(conv) == 1, conv)
cid = conv[0]["id"] if conv else 0
n_ai = sum(1 for m in conversations.tin_nhan(cid) if m["sender_type"] == "ai")
conversations.dat_che_do(cid, "draft")
out = asyncio.run(answer("Giá bao nhiêu em?", dict(M, message_id="m2")))
check("draft mode: nothing is sent", (out or {}).get("im_lang") and (out or {}).get("draft") and not (out or {}).get("text"), out)
d = conversations.draft_of(conversations.chi_tiet(cid))
check("draft mode: the reply waits on the conversation", d and d["text"] == "Dạ shop còn hàng ạ." and d["for_message_id"] > 0, d)
check("draft mode: not recorded as the bot's words",
      sum(1 for m in conversations.tin_nhan(cid) if m["sender_type"] == "ai") == n_ai)
check("draft mode: the customer message is in the inbox",
      any(m["text"] == "Giá bao nhiêu em?" for m in conversations.tin_nhan(cid)))

# ---- 6. routes -----------------------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import routes.conversations as conv_routes  # noqa: E402

cl = TestClient(main.app)
r = cl.get("/conversations?limit=50").json()
check("list: ok", r.get("ok"), r)
row = next((x for x in r["items"] if x["id"] == cid), None)
check("list: rows carry who fields", row and row["who"] == "you" and row["who_code"] == "draft_ready"
      and row["ai_allowed"] is True and row["draft"]["text"], row)
check("list: who_counts on the first page", isinstance(r.get("who_counts"), dict) and r["who_counts"]["you"] >= 1, r.get("who_counts"))
check("list: needs-you per account", sum((r["who_counts"].get("you_by_account") or {}).values()) == r["who_counts"]["you"],
      r.get("who_counts"))
check("list: needs-you in all, for the tab", r["who_counts"].get("you_total") == r["who_counts"]["you"], r.get("who_counts"))
whole = r["who_counts"]
r = cl.get("/conversations?account_ids=nobody:x&q=zzz").json()
check("list: picker and tab counts stay whole-inbox under filters (other Pages' numbers do not vanish)",
      r["who_counts"]["you"] == 0 and r["who_counts"]["you_by_account"] == whole["you_by_account"]
      and r["who_counts"]["you_total"] == whole["you_total"], r.get("who_counts"))
r = cl.get("/conversations?who=you&limit=50").json()
check("list: who=you keeps only needs-you rows", r["items"] and all(x["who"] == "you" for x in r["items"]), r["items"][:2])
r = cl.get("/conversations?who=owner").json()
check("list: who=owner empty", r["items"] == [], r["items"][:1])
r = cl.get("/conversations?account_ids=telegram:acc2").json()
check("list: account_ids", [x["external_chat_id"] for x in r["items"]] == ["2"], [x["external_chat_id"] for x in r["items"]])

r = cl.post(f"/conversations/{cid}/ai", data={"on": "0"}).json()
b = chatbot_store.get_bot(bid)
check("POST /ai on=0 blocks the chat on the bot", r.get("ok") and "900" in b["blocked"], (r, b.get("blocked")))
check("POST /ai returns the new state", r["conversation"]["ai_allowed"] is False and r["conversation"]["who"] in ("you", "log"),
      r.get("conversation"))
r = cl.post(f"/conversations/{cid}/ai", data={"on": "1"}).json()
check("POST /ai on=1 unblocks", r.get("ok") and "900" not in chatbot_store.get_bot(bid)["blocked"], r)
check("POST /ai without a bot: no_bot", cl.post(f"/conversations/{c1}/ai", data={"on": "1"}).json().get("code") == "no_bot")
odd = conversations.ghi_su_kien({"channel": "telegram", "account_id": "acc9", "external_chat_id": "khach-la", "chat_type": "private",
                                 "sender_type": "customer", "sender_id": "x", "sender_name": "X", "text": "hi", "bot_id": bid})
r = cl.post(f"/conversations/{odd['conversation_id']}/ai", data={"on": "0"})
check("POST /ai on a chat id the bot's lists cannot keep: an error, never a silent 'done'",
      r.status_code == 400 and r.json().get("code") == "chat_id", r.text)

r = cl.post(f"/conversations/{cid}/mode", data={"mode": "human"}).json()
check("changing the mode keeps the waiting draft (Undo brings it back)",
      r.get("ok") and conversations.draft_of(conversations.chi_tiet(cid)) is not None, r)
check("a waiting draft needs you in any mode", r["conversation"]["who"] == "you" and r["conversation"]["who_code"] == "draft_ready",
      r.get("conversation"))
conversations.dat_che_do(cid, "draft")
conversations.save_draft(cid, "Dạ 120k ạ")
r = cl.post(f"/conversations/{cid}/draft", data={"action": "discard"}).json()
check("draft discard", r.get("ok") and conversations.draft_of(conversations.chi_tiet(cid)) is None, r)
check("draft bad action", cl.post(f"/conversations/{cid}/draft", data={"action": "x"}).status_code == 400)

SENT = []


async def _fake_gui(kenh, tk, chat, text, ctype, **kw):
    SENT.append((kenh, chat, text))
    return True, ""


conv_routes.channels.gui = _fake_gui
conversations.save_draft(cid, "Dạ 120k ạ")
r = cl.post(f"/conversations/{cid}/draft", data={"action": "send", "text": "Dạ 120k một chai ạ"}).json()
check("draft send: sent the edited text", r.get("ok") and SENT and SENT[-1][2] == "Dạ 120k một chai ạ", (r, SENT))
check("draft send: recorded as the bot's words",
      any(m["sender_type"] == "ai" and m["text"] == "Dạ 120k một chai ạ" for m in conversations.tin_nhan(cid)))
check("draft send: draft cleared", conversations.draft_of(conversations.chi_tiet(cid)) is None)
check("draft send: empty refused", cl.post(f"/conversations/{cid}/draft", data={"action": "send", "text": " "}).status_code == 400)
conversations.save_draft(cid, "Dạ để em xem ạ")
r = cl.post(f"/conversations/{cid}/reply", data={"text": "Dạ còn hàng ạ"}).json()
check("owner's own reply drops the A.I. draft", r.get("ok") and conversations.draft_of(conversations.chi_tiet(cid)) is None, r)

ASKED = []


async def _fake_manual(conv, msgs, draft=False, instruction=""):
    ASKED.append((draft, instruction))
    return {"ok": True, "silent": False, "text": "Dạ em báo giá ạ", "meta": {}}


conv_routes._DEPS.manual_answer = _fake_manual
r = cl.post(f"/conversations/{cid}/ai-reply", data={"mode": "send", "instruction": "báo giá sỉ 20 thùng"}).json()
check("ai-reply with an instruction: always a draft, instruction passed",
      r.get("ok") and r.get("draft") and ASKED[-1] == (True, "báo giá sỉ 20 thùng") and not SENT[-1][2] == "Dạ em báo giá ạ",
      (r, ASKED))
d = conversations.draft_of(conversations.chi_tiet(cid))
check("ai-reply draft is kept as the chat's draft, with the instruction",
      d and d["text"] == "Dạ em báo giá ạ" and d["instruction"] == "báo giá sỉ 20 thùng"
      and (r.get("conversation") or {}).get("draft", {}).get("text") == "Dạ em báo giá ạ", (d, r.get("conversation")))
r = cl.post(f"/conversations/{cid}/ai-reply", data={"mode": "draft"}).json()
check("ai-reply without an instruction keeps the old call", r.get("ok") and ASKED[-1] == (True, ""), (r, ASKED))
r = cl.get(f"/conversations/{cid}/messages").json()
check("messages: the conversation carries who fields", "who" in (r.get("conversation") or {}), r.get("conversation"))
check("messages: the conversation carries the bot's reply_when", "reply_when" in (r.get("conversation") or {}), r.get("conversation"))

# The owner's note (Info panel): on the customer when the chat has one, else on the chat itself.
r = cl.post(f"/conversations/{cid}/note", data={"note": "  Khách sỉ, hay hỏi giá  "}).json()
check("note: saved and read back trimmed", r.get("ok") and r["conversation"]["note"] == "Khách sỉ, hay hỏi giá", r)
check("note: unknown chat is 404", cl.post("/conversations/999999/note", data={"note": "x"}).status_code == 404)
r = cl.post(f"/conversations/{cid}/note", data={"note": ""}).json()
check("note: cleared", r.get("ok") and r["conversation"]["note"] == "", r)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("all ok")
