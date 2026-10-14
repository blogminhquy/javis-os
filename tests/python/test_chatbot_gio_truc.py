"""Chatbot active hours (`gio_truc`), 0.130.0.

    python tests/run.py chatbot_gio_truc      (no network)

The owner wants a customer bot that stays silent at night (e.g. on duty 08:00 to 02:00), with every message the
bot would have answered still landing in the inbox for whoever is on duty in the morning. What this file guards:

  1. PARSING. Empty = all day (old records unchanged); HH:MM pairs; a broken value is REJECTED on save, never
     silently dropped (the form would say "saved" while the bot keeps answering at 3 am).
  2. THE CLOCK. Same-day ranges, ranges past midnight, the end is exclusive.
  3. THE GATE. Outside hours `_ly_do_im` says "ngoai_gio_truc", but only after the audience rules, so an unknown
     group or person still reaches the approval queue with its own code.
  4. THE INBOX. A message turned away at night is still written to the inbox; the try panel reports the code.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from datetime import datetime

_STATE = tempfile.mkdtemp(prefix="javis-giotruc-")
os.environ["JAVIS_STATE_DIR"] = _STATE
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import localefmt  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(chatbot_store.STORE_PATH):
    print(f"FAIL store is not in the temp folder: {chatbot_store.STORE_PATH}. STOP.")
    sys.exit(1)


def luc(h, m=0):
    return datetime(2026, 10, 13, h, m, tzinfo=localefmt.tz())


DEM = {"tu": "08:00", "den": "02:00"}      # the MTM bot: on duty 08:00, off at 02:00

# ============================================================
# 1. Parsing
# ============================================================
for rong in (None, "", "  ", {}, {"tu": "", "den": ""}, "null"):
    check(f"empty value {rong!r} = all day", chatbot_store.parse_gio_truc(rong) == ({}, ""))
check("dict HH:MM kept", chatbot_store.parse_gio_truc({"tu": "08:00", "den": "02:00"}) == (DEM, ""))
check("JSON string from the form", chatbot_store.parse_gio_truc('{"tu":"08:00","den":"02:00"}') == (DEM, ""))
check("range text 8:00-2:00 normalised", chatbot_store.parse_gio_truc("8:00-2:00") == (DEM, ""))
check("range text with 'đến' and 8h30", chatbot_store.parse_gio_truc("8h30 đến 22h")[0] == {"tu": "08:30", "den": "22:00"})
for hong in ({"tu": "25:00", "den": "02:00"}, {"tu": "08:00", "den": ""}, {"tu": "08:60", "den": "09:00"},
             {"tu": "08:00", "den": "08:00"}, "{khong-phai-json", ["08:00", "02:00"], "sang"):
    g, loi = chatbot_store.parse_gio_truc(hong)
    check(f"broken value {hong!r} is an error", g is None and bool(loi), (g, loi))

# ============================================================
# 2. The clock
# ============================================================
TRONG_NGAY = {"tu": "08:00", "den": "22:00"}
for (h, m), mong in {(7, 59): False, (8, 0): True, (12, 0): True, (21, 59): True, (22, 0): False, (23, 0): False}.items():
    check(f"08:00-22:00 at {h:02d}:{m:02d} -> {mong}", chatbot_store.trong_gio_truc(TRONG_NGAY, luc(h, m)) is mong)
for (h, m), mong in {(8, 0): True, (15, 0): True, (23, 30): True, (0, 0): True, (1, 59): True,
                     (2, 0): False, (3, 0): False, (5, 0): False, (7, 59): False}.items():
    check(f"08:00-02:00 (past midnight) at {h:02d}:{m:02d} -> {mong}", chatbot_store.trong_gio_truc(DEM, luc(h, m)) is mong)
for rong in (None, {}, ""):
    check(f"empty {rong!r} = answers at 03:00", chatbot_store.trong_gio_truc(rong, luc(3)) is True)
check("CANARY: a stored value that no longer parses = all day, never a silenced bot",
      chatbot_store.trong_gio_truc({"tu": "99:99", "den": "x"}, luc(3)) is True)

# ============================================================
# 3. Store: create, update, whitelist, old records
# ============================================================
check("gio_truc is in the edit whitelist", "gio_truc" in chatbot_store._PATCHABLE)
check("CANARY: an old record without the key reads as all day",
      chatbot_store._public({"id": "x"}).get("gio_truc") == {})
bid, loi = chatbot_store.create_bot({"name": "Trợ lý Zalo MTM", "agent_slug": "tro-ly", "brain": "b",
                                     "gio_truc": '{"tu":"08:00","den":"02:00"}'})
check("create with active hours", not loi and chatbot_store.get_bot(bid)["gio_truc"] == DEM, loi)
b0, loi = chatbot_store.create_bot({"name": "Ca ngay", "agent_slug": "x", "brain": "b"})
check("create without active hours = all day", not loi and chatbot_store.get_bot(b0)["gio_truc"] == {}, loi)
_, loi = chatbot_store.create_bot({"name": "Hong", "agent_slug": "x", "brain": "b", "gio_truc": "25:00-02:00"})
check("create with broken hours is refused", bool(loi))

ok, err = chatbot_store.update_bot(bid, {"gio_truc": {"tu": "08:00", "den": ""}, "name": "Doi ten"})
check("update with half a range is refused as a whole", not ok and bool(err), (ok, err))
check("... and the old hours and name stay", chatbot_store.get_bot(bid)["gio_truc"] == DEM
      and chatbot_store.get_bot(bid)["name"] == "Trợ lý Zalo MTM")
ok, err = chatbot_store.update_bot(b0, {"gio_truc": "08:00-02:00"})
check("update sets hours", ok and chatbot_store.get_bot(b0)["gio_truc"] == DEM, err)
ok, err = chatbot_store.update_bot(b0, {"gio_truc": ""})
check("update with empty value goes back to all day", ok and chatbot_store.get_bot(b0)["gio_truc"] == {}, err)
ok, err = chatbot_store.update_bot(b0, {"name": "Khong dung gio"})
check("a patch without the key leaves hours alone", ok and chatbot_store.get_bot(b0)["gio_truc"] == {}, err)

# ============================================================
# 4. The gate
# ============================================================
cfg = chatbot_store.get_bot(bid)
rieng = {"chat_type": "private", "chat_id": "p1"}
check("private message at 10:00 -> answered", chatbot_runtime._ly_do_im(cfg, rieng, luc(10)) == "")
check("private message at 03:00 -> ngoai_gio_truc", chatbot_runtime._ly_do_im(cfg, rieng, luc(3)) == "ngoai_gio_truc")
check("private message at 01:30 (past midnight, still on duty) -> answered",
      chatbot_runtime._ly_do_im(cfg, rieng, luc(1, 30)) == "")
check("bot without hours at 03:00 -> answered",
      chatbot_runtime._ly_do_im(chatbot_store.get_bot(b0), rieng, luc(3)) == "")
nhom_la = {"chat_type": "group", "chat_id": "g-la", "mentioned": True}
check("unknown group at night keeps its own code (approval queue still works)",
      chatbot_runtime._ly_do_im(cfg, nhom_la, luc(3)) == "nhom_chua_bat")
cfg_nhom = dict(cfg, groups=["g1"])
check("allowed group, nobody names the bot, at night -> khong_goi_ten (plain silence)",
      chatbot_runtime._ly_do_im(cfg_nhom, {"chat_type": "group", "chat_id": "g1"}, luc(3)) == "khong_goi_ten")
check("allowed group, bot tagged, at night -> ngoai_gio_truc",
      chatbot_runtime._ly_do_im(cfg_nhom, {"chat_type": "group", "chat_id": "g1", "mentioned": True}, luc(3))
      == "ngoai_gio_truc")
check("_nen_tra_loi follows the hours (second layer in the answer path)",
      chatbot_runtime._nen_tra_loi(cfg, rieng) == chatbot_store.trong_gio_truc(DEM))

# The engine must never be reached at night; wiring one that fails loudly proves it.
async def _engine_cam(*a, **k):
    raise AssertionError("engine called outside active hours")


chatbot_runtime.wire(answer=_engine_cam, brain_root=lambda b: _STATE, read_agent=lambda br, slug: ({}, ""))

# ============================================================
# 5. Precheck at night: silent, but the message is in the inbox. Try panel reports the code.
# ============================================================
_now_that = localefmt.now
localefmt.now = lambda: luc(3)
try:
    chan = chatbot_runtime._make_precheck_fn(bid)
    meta = {"chat_type": "private", "chat_id": "khach-dem", "user_id": "khach-dem", "user_name": "Phụ huynh",
            "message_id": "m-dem-1"}
    r = chan("Cô ơi lịch học tuần này thế nào ạ?", dict(meta))
    check("precheck at 03:00 blocks silently ({}: no reply, no fixed sentence)", r == {}, r)
    aid, kenh = chatbot_runtime._tai_khoan_cua(chatbot_store.get_bot(bid), meta)
    tin = conversations.tin_gan_day(kenh, aid, "khach-dem")
    check("the night message is in the inbox for the morning shift",
          any(t.get("sender_type") == "customer" and "lịch học" in (t.get("text") or "") for t in tin), tin)
    chan("Cô ơi lịch học tuần này thế nào ạ?", dict(meta))
    check("the same message seen twice is written once",
          len(conversations.tin_gan_day(kenh, aid, "khach-dem")) == len(tin))

    ok, err = chatbot_store.update_bot(bid, {"groups": "5551234", "reply_when": "auto"})
    assert ok, err
    nhom = {"chat_type": "group", "chat_id": "5551234", "user_id": "u9", "user_name": "Phụ huynh B"}
    akey = chatbot_runtime._tai_khoan_cua(chatbot_store.get_bot(bid), nhom)
    r = chan("cả nhà ngủ ngon", dict(nhom, message_id="g-1"))
    check("night, auto mode, group chatter: silent", r == {}, r)
    check("... and chatter does NOT flood the inbox", not conversations.tin_gan_day(akey[1], akey[0], "5551234"))
    r = chan("@bot cho em hỏi lịch thi", dict(nhom, message_id="g-2", mentioned=True))
    check("night, group, bot tagged: silent", r == {}, r)
    check("... but the tagged question is in the inbox",
          any("lịch thi" in (t.get("text") or "") for t in conversations.tin_gan_day(akey[1], akey[0], "5551234")))

    r = asyncio.run(chatbot_runtime.try_message(bid, "Cô ơi cho em hỏi học phí"))
    check("try panel at 03:00 says the gate code ngoai_gio_truc",
          r.get("ok") and r.get("stage") == "gate" and r.get("code") == "ngoai_gio_truc"
          and not r.get("would_reply") and bool(r.get("reason")), r)
finally:
    localefmt.now = _now_that

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
