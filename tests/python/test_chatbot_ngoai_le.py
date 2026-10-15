"""Per-chat exceptions for a bot (`ngoai_le`), 0.172.0.

    python tests/run.py chatbot_ngoai_le      (no network; TestClient)

The owner of a personal Zalo nick runs ONE bot that answers ~90 parents at "Read only", and wants the same bot to
help his mother edit her Word/Excel files in her own chat. Raising the whole bot would hand those tools to every
stranger who messages the nick. An exception names exactly one private chat and gives it its own level and wait.
What this file guards:

  1. PARSING. Empty = none (old records unchanged); a broken list is REJECTED on save, never half-applied.
  2. THE RISK GATE. An exception that RAISES a chat to "Can write" or "Full power" needs its OWN confirmation
     (`xac_nhan_ngoai_le`), on the store AND on the route (which answers can_force so the form can ask). The
     bot-level flag `xac_nhan_rui_ro` never acknowledges an exception. Saving the same list again, or lowering,
     does not ask.
  3. THE TURN. `ap_ngoai_le` swaps the level only for that private chat ON THE ACCOUNT the exception names, on a
     copy; a group with the same id, the same id on another account, and every other chat keep the bot's level.
     A RAISED chat counts as a chosen person and its prompt says so; a LOWERED one gains nothing.
  4. END TO END (review of #653): the live turn through `_make_answer_fn` and the inbox "Reply for me" /
     "Suggest a reply" (`manual_answer`) both hand `_deps["answer"]` the excepted level for that chat and the
     bot's level for others.
  5. The known-chats list tags each private chat with its account, so the form picks instead of typing.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-ngoaile-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(chatbot_store.STORE_PATH):
    print(f"FAIL store is not in the temp folder: {chatbot_store.STORE_PATH}. STOP.")
    sys.exit(1)

ACC = "zalo-acc-1"
ME = {"account_id": ACC, "chat_id": "u_me", "ten": "Mẹ", "muc_quyen": "full", "cho_giay": 10}

# ============================================================
# 1. Parsing
# ============================================================
for rong in (None, "", []):
    check(f"empty value {rong!r} = no exception", chatbot_store.parse_ngoai_le(rong) == ([], ""))
ok, loi = chatbot_store.parse_ngoai_le(json.dumps([ME]))
check("JSON text from the form", not loi and ok == [ME], (ok, loi))
ok, loi = chatbot_store.parse_ngoai_le([{"account_id": f" {ACC} ", "chat_id": " u_me ", "ten": "  Mẹ   yêu ",
                                         "muc_quyen": "AUTO", "cho_giay": ""}])
check("trimmed ids, collapsed label, level lower-cased, empty wait = channel default",
      ok == [{"account_id": ACC, "chat_id": "u_me", "ten": "Mẹ yêu", "muc_quyen": "auto", "cho_giay": None}], (ok, loi))
ok, loi = chatbot_store.parse_ngoai_le([ME, dict(ME, account_id="tg-acc-1")])
check("the same chat id on two different accounts is two exceptions", ok is not None and len(ok) == 2, (ok, loi))
for xau, ly_do in ((["u_me"], "not an object"),
                   ([{"account_id": ACC, "chat_id": "", "muc_quyen": "auto"}], "no id"),
                   ([{"chat_id": "u_me", "muc_quyen": "auto"}], "no channel account (a raw typed id)"),
                   ([{"account_id": "acc 1", "chat_id": "u_me", "muc_quyen": "auto"}], "account with a space"),
                   ([{"account_id": ACC, "chat_id": "u me", "muc_quyen": "auto"}], "id with a space"),
                   ([{"account_id": ACC, "chat_id": "u_me", "muc_quyen": "admin"}], "unknown level"),
                   ([{"account_id": ACC, "chat_id": "u_me", "muc_quyen": "auto", "cho_giay": 61}], "wait over 60 s"),
                   ([{"account_id": ACC, "chat_id": "u_me", "muc_quyen": "auto", "cho_giay": "abc"}], "wait not a number"),
                   ([ME, dict(ME, ten="Mẹ 2")], "same chat on the same account twice"),
                   ([{"account_id": ACC, "chat_id": f"u{i}", "muc_quyen": "suggest"} for i in range(21)], "more than 20"),
                   ("{không phải json", "broken JSON"), ({"chat_id": "u_me"}, "not a list")):
    ok, loi = chatbot_store.parse_ngoai_le(xau)
    check(f"rejected: {ly_do}", ok is None and loi, (ok, loi))

# ============================================================
# 2. The risk gate (store): the exception's OWN flag
# ============================================================
bid, err = chatbot_store.create_bot({"name": "Trợ lý Zalo", "agent_slug": "tro-ly", "brain": "brain",
                                     "audience": "chon", "people": "u_ph1"})
check("(setup) a read-only bot that answers chosen people", bid and not err, err)
check("old records read as no exception", chatbot_store.get_bot(bid)["ngoai_le"] == [])
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([ME])})
check("raising one chat to Full power WITHOUT confirmation is refused", not ok and loi, loi)
check("and nothing was saved", chatbot_store.get_bot(bid)["ngoai_le"] == [])
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([ME]), "xac_nhan_rui_ro": True})
check("CANARY: the BOT-level confirmation does not acknowledge an exception", not ok and loi
      and chatbot_store.get_bot(bid)["ngoai_le"] == [], loi)
check("the refusal names the exception's own flag", "xac_nhan_ngoai_le" in str(loi), loi)
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([{"chat_id": "u_me", "account_id": ACC}]),
                                         "xac_nhan_ngoai_le": True})
check("a broken list is refused even with the confirmation", not ok and loi, loi)
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([ME]), "xac_nhan_ngoai_le": True})
check("with the exception's confirmation it is saved", ok and chatbot_store.get_bot(bid)["ngoai_le"] == [ME], loi)
check("the bot itself stays Read only", chatbot_store.get_bot(bid)["muc_quyen"] == "suggest")
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([ME]), "name": "Trợ lý Zalo MTM"})
check("saving the edit form again with the same exception does not ask again", ok, loi)
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([ME, dict(ME, account_id="tg-acc-1")])})
check("the same chat id raised on ANOTHER account asks again", not ok, loi)
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([dict(ME, muc_quyen="auto")])})
check("lowering never asks", ok and chatbot_store.get_bot(bid)["ngoai_le"][0]["muc_quyen"] == "auto", loi)
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([ME])})
check("raising it back from Can write to Full power asks again", not ok, loi)
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps(
    [{"account_id": ACC, "chat_id": "u_x", "muc_quyen": "read_docs"}])})
check("an exception to a level without risk needs no confirmation", ok, loi)
nid, err = chatbot_store.create_bot({"name": "Bot hai", "agent_slug": "tro-ly", "brain": "brain",
                                     "ngoai_le": json.dumps([ME]), "xac_nhan_rui_ro": True})
check("create: a raising exception with only the bot-level confirmation is refused", not nid and err, err)

# ============================================================
# 3. The route answers can_force so the form can ask
# ============================================================
c = TestClient(main.app)
r = c.post(f"/chatbots/{bid}/update", data={"ngoai_le": json.dumps([ME])})
j = r.json()
check("route: 400 with can_force, the level, its risk lines and the flag to resend",
      r.status_code == 400 and j.get("can_force") and j.get("muc_quyen") == "full" and j.get("canh_bao")
      and j.get("co") == "xac_nhan_ngoai_le", j)
r = c.post(f"/chatbots/{bid}/update", data={"ngoai_le": json.dumps([ME]), "xac_nhan_rui_ro": "1"})
check("CANARY route: the bot-level flag (what the form sends on every save) does not raise a chat",
      r.status_code == 400 and r.json().get("can_force") and chatbot_store.get_bot(bid)["ngoai_le"][0]["chat_id"] == "u_x",
      r.text)
r = c.post(f"/chatbots/{bid}/update", data={"ngoai_le": json.dumps([ME]), "xac_nhan_ngoai_le": "1"})
check("route: confirmed with its own flag, saved",
      r.status_code == 200 and chatbot_store.get_bot(bid)["ngoai_le"] == [ME], r.text)
r = c.post(f"/chatbots/{bid}/update", data={"ngoai_le": "[1]"})
check("route: a broken list is a plain 400 with the reason", r.status_code == 400 and not r.json().get("can_force"), r.text)
r = c.post("/chatbots", data={"name": "Bot ba", "agent_slug": "tro-ly", "brain": "brain", "ngoai_le": json.dumps([ME]),
                              "xac_nhan_rui_ro": "1"})
check("route create: asks too, even with the bot-level flag", r.status_code == 400 and r.json().get("can_force"), r.text)

# ============================================================
# 4. The turn
# ============================================================
cfg = chatbot_store.get_bot(bid)
rieng = {"chat_id": "u_me", "chat_type": "private", "account_id": ACC}
cfg_me = chatbot_store.ap_ngoai_le(cfg, rieng)
check("her private chat runs at Full power", cfg_me["muc_quyen"] == "full" and cfg_me["_ngoai_le"]["ten"] == "Mẹ")
check("on a COPY: the bot record is untouched", cfg["muc_quyen"] == "suggest" and "_ngoai_le" not in cfg)
check("applying twice keeps the bot's own level", chatbot_store.ap_ngoai_le(cfg_me, rieng) is cfg_me
      and cfg_me["_muc_bot"] == "suggest")
check("another private chat keeps the bot's level",
      chatbot_store.ap_ngoai_le(cfg, dict(rieng, chat_id="u_ph1")) is cfg)
check("a GROUP with the same id is never an exception",
      chatbot_store.ap_ngoai_le(cfg, dict(rieng, chat_type="group")) is cfg)
check("CANARY: the same id on ANOTHER account (e.g. the bot's Telegram) is never an exception",
      chatbot_store.ap_ngoai_le(cfg, dict(rieng, account_id="tg-acc-1")) is cfg)
check("a turn with no account is never an exception",
      chatbot_store.ap_ngoai_le(cfg, {"chat_id": "u_me", "chat_type": "private"}) is cfg)
check("no meta, no exception", chatbot_store.ap_ngoai_le(cfg, None) is cfg)
check("the raised chat counts as a chosen person (audience 'chon')",
      chatbot_runtime._ly_do_im_co_ban(cfg, rieng) == "")
check("a stranger is still not chosen",
      chatbot_runtime._ly_do_im_co_ban(cfg, dict(rieng, chat_id="u_la")) == "nguoi_chua_chon")
chatbot_runtime.wire(answer=lambda *a, **k: None, brain_root=lambda b: _STATE,
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Trợ lý"}, "Trả lời ngắn."))
p_me = chatbot_runtime.build_bot_prompt(cfg_me)
check("her prompt states the level given to this chat", "QUYỀN CỦA CUỘC CHAT NÀY" in p_me and "Toàn quyền" in p_me
      and '"Mẹ"' in p_me, p_me[-300:])
check("other prompts say nothing about it", "QUYỀN CỦA CUỘC CHAT NÀY" not in chatbot_runtime.build_bot_prompt(cfg))

# A LOWERED chat: a Full bot whose owner distrusts one chat and puts it at Read only.
fid, err = chatbot_store.create_bot({"name": "Bot full", "agent_slug": "tro-ly", "brain": "brain", "muc_quyen": "full",
                                     "xac_nhan_rui_ro": True, "audience": "chon", "people": "u_ph1",
                                     "ngoai_le": json.dumps([{"account_id": ACC, "chat_id": "u_nghi", "ten": "Khách lạ",
                                                              "muc_quyen": "suggest"}])})
check("(setup) a Full bot with one chat lowered to Read only, no exception confirmation needed", fid and not err, err)
fcfg = chatbot_store.get_bot(fid)
nghi = {"chat_id": "u_nghi", "chat_type": "private", "account_id": ACC}
fcfg_nghi = chatbot_store.ap_ngoai_le(fcfg, nghi)
check("the lowered chat runs at Read only", fcfg_nghi["muc_quyen"] == "suggest")
check("CANARY: a lowered chat is NOT told 'this is not a stranger'",
      "QUYỀN CỦA CUỘC CHAT NÀY" not in chatbot_runtime.build_bot_prompt(fcfg_nghi))
check("CANARY: lowering a chat never makes it a chosen person",
      chatbot_runtime._ly_do_im_co_ban(fcfg, nghi) == "nguoi_chua_chon")

# ============================================================
# 5. End to end: the live turn and the inbox path hand the engine the right level
# ============================================================
LUOT = []


async def _engine(text, meta, progress, *, channel="", bot=None, **kw):
    LUOT.append({"chat": (meta or {}).get("chat_id"), "acc": (meta or {}).get("account_id"),
                 "muc": (bot or {}).get("muc_quyen"), "prompt": chatbot_runtime.build_bot_prompt(bot)})
    return {"text": "Dạ", "files": []}


chatbot_runtime.wire(answer=_engine, brain_root=lambda b: _STATE,
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Trợ lý"}, "Trả lời ngắn."))
for _b in (bid, fid):
    ok, loi = chatbot_store.update_bot(_b, {"audience": "nhom"})
    check("(setup) the bot answers every private chat, so every test turn reaches the engine", ok, loi)


async def _e2e():
    tra = chatbot_runtime._make_answer_fn(bid)
    for chat, acc in (("u_me", ACC), ("u_ph1", ACC), ("u_me", "tg-acc-1")):
        await tra("Con ơi", {"chat_id": chat, "chat_type": "private", "account_id": acc, "user_id": chat,
                             "user_name": chat, "message_id": f"m-{chat}-{acc}", "platform": "zalo_personal"})
    tra_f = chatbot_runtime._make_answer_fn(fid)
    for chat in ("u_ph1", "u_nghi"):
        await tra_f("Cho hỏi", {"chat_id": chat, "chat_type": "private", "account_id": ACC, "user_id": chat,
                                "user_name": chat, "message_id": f"m-f-{chat}", "platform": "zalo_personal"})


asyncio.run(_e2e())
by = {(x["chat"], x["acc"], x["muc"]) for x in LUOT}
check("live turn: her chat reaches the engine at Full power", ("u_me", ACC, "full") in by, LUOT)
check("live turn: a parent on the same bot reaches it at Read only", ("u_ph1", ACC, "suggest") in by, LUOT)
check("CANARY live turn: her id on another account reaches it at Read only", ("u_me", "tg-acc-1", "suggest") in by, LUOT)
check("live turn: the Full bot answers a parent at Full power", ("u_ph1", ACC, "full") in by, LUOT)
check("CANARY live turn: the chat the owner lowered reaches the engine at Read only", ("u_nghi", ACC, "suggest") in by
      and ("u_nghi", ACC, "full") not in by, LUOT)
check("live turn: five turns, none silenced", len(LUOT) == 5, LUOT)


async def _manual():
    LUOT.clear()
    conv = {"id": 9001, "bot_id": fid, "channel_account_id": f"telegram:{ACC}", "external_chat_id": "u_nghi",
            "chat_type": "private", "channel": "telegram", "title": ""}
    msgs = [{"sender_type": "customer", "text": "Chuyển khoản giúp tôi", "sender_id": "u_nghi",
             "external_message_id": "x1", "created_at": 1}]
    r1 = await chatbot_runtime.manual_answer(conv, msgs)
    r2 = await chatbot_runtime.manual_answer(conv, msgs, draft=True)
    conv_me = dict(conv, id=9002, bot_id=bid, external_chat_id="u_me")
    r3 = await chatbot_runtime.manual_answer(conv_me, msgs)
    conv_ph = dict(conv, id=9003, bot_id=bid, external_chat_id="u_ph1")
    r4 = await chatbot_runtime.manual_answer(conv_ph, msgs)
    return r1, r2, r3, r4


rs = asyncio.run(_manual())
check("(setup) the inbox turns ran", all(r.get("ok") for r in rs), rs)
mucs = [x["muc"] for x in LUOT]
check("CANARY inbox 'Reply for me': the chat the owner lowered runs at Read only, not at the Full bot level",
      mucs[:1] == ["suggest"], LUOT)
check("CANARY inbox 'Suggest a reply': same", mucs[1:2] == ["suggest"], LUOT)
check("inbox: a raised chat keeps its raised level there too", mucs[2:3] == ["full"], LUOT)
check("inbox: every other chat runs at the bot's level", mucs[3:4] == ["suggest"], LUOT)

# ============================================================
# 6. The known-chats list tags each private chat with its account
# ============================================================
import chatbot_cuoc_chat  # noqa: E402
import conversations  # noqa: E402
_goc = conversations.cuoc_chat_cua_tai_khoan
conversations.cuoc_chat_cua_tai_khoan = lambda kenh, aid, q, n: (
    [{"external_chat_id": "u_me", "chat_type": "private", "customer_name": "Mẹ", "last_message_at": 5}]
    if aid == ACC else [])
try:
    dong = chatbot_cuoc_chat.danh_sach([{"id": ACC, "channel": "zalo_personal"}, {"id": "tg-acc-1", "channel": "telegram"}])
finally:
    conversations.cuoc_chat_cua_tai_khoan = _goc
check("a known private chat carries the account it lives on, for the exception picker",
      [(d["id"], d["tk"]) for d in dong] == [("u_me", ACC)], dong)

# ============================================================
# 7. Zalo Bot: a message without its chat type is not taken as private on trust
# ============================================================
import zalo_bot  # noqa: E402
check("Zalo Bot: missing type, chat id = sender id -> private", zalo_bot._chat_type(None, "123", "123") == "private")
check("CANARY Zalo Bot: missing type, chat id != sender id -> group, so a group id never matches an exception",
      zalo_bot._chat_type(None, "g-999", "123") == "group")
check("Zalo Bot: an explicit PRIVATE stays private", zalo_bot._chat_type("PRIVATE", "g-999", "123") == "private")
meta_zb = zalo_bot.ZaloBot._build_meta(type("B", (), {"bot_username": "", "_co_nhac_ten": lambda self, m: False})(),
                                       {"chat": {"id": "g-999"}, "from": {"id": "123"}, "message_id": "z1"})
check("Zalo Bot: the meta of a typeless group message is a group", meta_zb["chat_type"] == "group", meta_zb)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
