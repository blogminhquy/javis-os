"""Per-chat exceptions for a bot (`ngoai_le`), 0.144.0.

    python tests/run.py chatbot_ngoai_le      (no network; TestClient)

The owner of a personal Zalo nick runs ONE bot that answers ~90 parents at "Read only", and wants the same bot to
help his mother edit her Word/Excel files in her own chat. Raising the whole bot would hand those tools to every
stranger who messages the nick. An exception names exactly one private chat and gives it its own level and wait.
What this file guards:

  1. PARSING. Empty = none (old records unchanged); a broken list is REJECTED on save, never half-applied.
  2. THE RISK GATE. An exception that RAISES a chat to "Can write" or "Full power" needs the same confirmation as
     raising the bot, on the store AND on the route (which answers can_force so the form can ask). Saving the
     same list again, or lowering, does not ask.
  3. THE TURN. `ap_ngoai_le` swaps the level only for that private chat, on a copy; a group with the same id
     and every other chat keep the bot's level. The chat counts as a chosen person; the prompt states the level.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
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

ME = {"chat_id": "u_me", "ten": "Mẹ", "muc_quyen": "full", "cho_giay": 10}

# ============================================================
# 1. Parsing
# ============================================================
for rong in (None, "", []):
    check(f"empty value {rong!r} = no exception", chatbot_store.parse_ngoai_le(rong) == ([], ""))
ok, loi = chatbot_store.parse_ngoai_le(json.dumps([ME]))
check("JSON text from the form", not loi and ok == [ME], (ok, loi))
ok, loi = chatbot_store.parse_ngoai_le([{"chat_id": " u_me ", "ten": "  Mẹ   yêu ", "muc_quyen": "AUTO", "cho_giay": ""}])
check("trimmed id, collapsed label, level lower-cased, empty wait = channel default",
      ok == [{"chat_id": "u_me", "ten": "Mẹ yêu", "muc_quyen": "auto", "cho_giay": None}], (ok, loi))
for xau, ly_do in ((["u_me"], "not an object"), ([{"chat_id": "", "muc_quyen": "auto"}], "no id"),
                   ([{"chat_id": "u me", "muc_quyen": "auto"}], "id with a space"),
                   ([{"chat_id": "u_me", "muc_quyen": "admin"}], "unknown level"),
                   ([{"chat_id": "u_me", "muc_quyen": "auto", "cho_giay": 61}], "wait over 60 s"),
                   ([{"chat_id": "u_me", "muc_quyen": "auto", "cho_giay": "abc"}], "wait not a number"),
                   ([ME, dict(ME, ten="Mẹ 2")], "same chat twice"),
                   ([{"chat_id": f"u{i}", "muc_quyen": "suggest"} for i in range(21)], "more than 20"),
                   ("{không phải json", "broken JSON"), ({"chat_id": "u_me"}, "not a list")):
    ok, loi = chatbot_store.parse_ngoai_le(xau)
    check(f"rejected: {ly_do}", ok is None and loi, (ok, loi))

# ============================================================
# 2. The risk gate (store)
# ============================================================
bid, err = chatbot_store.create_bot({"name": "Trợ lý Zalo", "agent_slug": "tro-ly", "brain": "brain",
                                     "audience": "chon", "people": "u_ph1"})
check("(setup) a read-only bot that answers chosen people", bid and not err, err)
check("old records read as no exception", chatbot_store.get_bot(bid)["ngoai_le"] == [])
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([ME])})
check("raising one chat to Full power WITHOUT confirmation is refused", not ok and loi, loi)
check("and nothing was saved", chatbot_store.get_bot(bid)["ngoai_le"] == [])
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": "[{\"chat_id\": \"u_me\"}]", "xac_nhan_rui_ro": True})
check("a broken list is refused even with the confirmation", not ok and loi, loi)
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([ME]), "xac_nhan_rui_ro": True})
check("with the confirmation it is saved", ok and chatbot_store.get_bot(bid)["ngoai_le"] == [ME], loi)
check("the bot itself stays Read only", chatbot_store.get_bot(bid)["muc_quyen"] == "suggest")
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([ME]), "name": "Trợ lý Zalo MTM"})
check("saving the edit form again with the same exception does not ask again", ok, loi)
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([dict(ME, muc_quyen="auto")])})
check("lowering never asks", ok and chatbot_store.get_bot(bid)["ngoai_le"][0]["muc_quyen"] == "auto", loi)
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([ME])})
check("raising it back from Can write to Full power asks again", not ok, loi)
ok, loi = chatbot_store.update_bot(bid, {"ngoai_le": json.dumps([{"chat_id": "u_x", "muc_quyen": "read_docs"}])})
check("an exception to a level without risk needs no confirmation", ok, loi)
nid, err = chatbot_store.create_bot({"name": "Bot hai", "agent_slug": "tro-ly", "brain": "brain",
                                     "ngoai_le": json.dumps([ME])})
check("create: a raising exception without confirmation is refused", not nid and err, err)

# ============================================================
# 3. The route answers can_force so the form can ask
# ============================================================
c = TestClient(main.app)
r = c.post(f"/chatbots/{bid}/update", data={"ngoai_le": json.dumps([ME])})
j = r.json()
check("route: 400 with can_force, the level and its risk lines",
      r.status_code == 400 and j.get("can_force") and j.get("muc_quyen") == "full" and j.get("canh_bao"), j)
r = c.post(f"/chatbots/{bid}/update", data={"ngoai_le": json.dumps([ME]), "xac_nhan_rui_ro": "1"})
check("route: confirmed, saved", r.status_code == 200 and chatbot_store.get_bot(bid)["ngoai_le"] == [ME], r.text)
r = c.post(f"/chatbots/{bid}/update", data={"ngoai_le": "[1]"})
check("route: a broken list is a plain 400 with the reason", r.status_code == 400 and not r.json().get("can_force"), r.text)
r = c.post("/chatbots", data={"name": "Bot ba", "agent_slug": "tro-ly", "brain": "brain", "ngoai_le": json.dumps([ME])})
check("route create: asks too", r.status_code == 400 and r.json().get("can_force"), r.text)

# ============================================================
# 4. The turn
# ============================================================
cfg = chatbot_store.get_bot(bid)
rieng = {"chat_id": "u_me", "chat_type": "private"}
cfg_me = chatbot_store.ap_ngoai_le(cfg, rieng)
check("her private chat runs at Full power", cfg_me["muc_quyen"] == "full" and cfg_me["_ngoai_le"]["ten"] == "Mẹ")
check("on a COPY: the bot record is untouched", cfg["muc_quyen"] == "suggest" and "_ngoai_le" not in cfg)
check("another private chat keeps the bot's level",
      chatbot_store.ap_ngoai_le(cfg, {"chat_id": "u_ph1", "chat_type": "private"}) is cfg)
check("a GROUP with the same id is never an exception",
      chatbot_store.ap_ngoai_le(cfg, {"chat_id": "u_me", "chat_type": "group"}) is cfg)
check("no meta, no exception", chatbot_store.ap_ngoai_le(cfg, None) is cfg)
check("the exception chat counts as a chosen person (audience 'chon')",
      chatbot_runtime._ly_do_im_co_ban(cfg, rieng) == "")
check("a stranger is still not chosen",
      chatbot_runtime._ly_do_im_co_ban(cfg, {"chat_id": "u_la", "chat_type": "private"}) == "nguoi_chua_chon")
chatbot_runtime.wire(answer=lambda *a, **k: None, brain_root=lambda b: _STATE,
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Trợ lý"}, "Trả lời ngắn."))
p_me = chatbot_runtime.build_bot_prompt(cfg_me)
check("her prompt states the level given to this chat", "QUYỀN CỦA CUỘC CHAT NÀY" in p_me and "Toàn quyền" in p_me
      and '"Mẹ"' in p_me, p_me[-300:])
check("other prompts say nothing about it", "QUYỀN CỦA CUỘC CHAT NÀY" not in chatbot_runtime.build_bot_prompt(cfg))

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
