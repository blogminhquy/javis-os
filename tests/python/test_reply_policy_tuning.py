"""Reply judge knobs (0.77.0): tuning table, lessons by source, and the `addressed_other` gate that learning can open.

    python tests/run.py reply_policy_tuning      (no network)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-rp-tuning-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_reply_policy as rp  # noqa: E402
import chatbot_reply_policy_store as st  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


NOW = 1_800_000_000.0

# ---- a store that was never created stays uncreated ----
check("get_tuning on a missing store returns {} and creates nothing",
      st.get_tuning("A") == {} and not st.db_path().exists())
check("list_changes on a missing store returns []", st.list_changes("A") == [] and not st.db_path().exists())

# ---- tuning ----
st.set_tuning("A", "eagerness", "high", NOW)
st.set_tuning("A", "consider_tagged", "1", NOW)
check("tuning is per bot", st.get_tuning("A") == {"eagerness": "high", "consider_tagged": "1"} and st.get_tuning("B") == {})
prof = rp.apply_tuning(rp.BotProfile(bot_id="A"), st)
check("apply_tuning overrides eagerness and consider_tagged", prof.eagerness == "high" and prof.consider_tagged)
st.set_tuning("A", "eagerness", "wild", NOW)
check("an unknown knob value is ignored", rp.apply_tuning(rp.BotProfile(bot_id="A"), st).eagerness == rp.EAGERNESS_DEFAULT)
st.set_tuning("A", "eagerness", None, NOW)
check("value None removes the knob", "eagerness" not in st.get_tuning("A"))
check("threshold follows eagerness", rp.threshold_for(rp.BotProfile(bot_id="Z", eagerness="high", learning_enabled=True), st, "g")
      == rp.BASE_THRESHOLD["high"])

# ---- lessons: the review may only displace its own ----
WORDS = ["mot", "hai", "ba", "bon", "nam", "sau", "bay", "tam", "chin", "muoi", "tram", "ngan", "trieu", "ty", "van"]
for i in range(st.MAX_LESSONS):
    st.add_lesson("L", f"luật của chủ về chuyện {WORDS[i]} {WORDS[i]}x", NOW + i)
check("15 owner lessons stored", len(st.list_lessons("L")) == st.MAX_LESSONS)
check("a review lesson cannot push out an owner lesson",
      st.insert_lesson("L", "luật máy viết mới toanh khác biệt", NOW + 100, source="review") is None
      and all(x["source"] == "" for x in st.list_lessons("L")))
st.delete_lesson("L", st.list_lessons("L")[0]["id"])
rid = st.insert_lesson("L", "luật máy viết thứ nhất riêng biệt", NOW + 101, source="review")
check("with room, a review lesson goes in", rid is not None and st.get_lesson("L", rid)["source"] == "review")
st.add_lesson("L", "luật chủ mới nhất hôm nay đặc biệt", NOW + 102)
ls = st.list_lessons("L")
check("over the cap, the review lesson drops first", len(ls) == st.MAX_LESSONS and all(x["source"] == "" for x in ls))
check("insert_lesson skips duplicates", st.insert_lesson("L", ls[-1]["text"], NOW + 103) is None)

# ---- offsets ----
check("set_offset clamps", st.set_offset("A", "g1", 0.9, NOW) == st.OFFSET_LIMIT)
check("get_offset reads it back", abs(st.get_offset("A", "g1", NOW) - st.OFFSET_LIMIT) < 1e-9)

# ---- the addressed_other gate ----
ev = rp.Event(channel="zalo", bot_id="A", chat_id="g1", chat_type="group", msg_id="m", ts=NOW,
              text="@Quý anh ơi lịch học Javis tuần này thế nào", sender_id="u1")
check("tagging someone else is filtered by default", rp.coarse_gate(ev, "none", {}) == (False, "addressed_other"))
check("a positive case opens the gate", rp.coarse_gate(ev, "none", {}, has_positive_case=True)[0])
Q = {"question_score": {"value": 0.8, "evidence": ""}}
check("consider_tagged opens the gate", rp.coarse_gate(ev, "none", Q, consider_tagged=True)[0])
ev_junk = rp.Event(channel="zalo", bot_id="A", chat_id="g1", chat_type="group", msg_id="m", ts=NOW, text="@Quý",
                   sender_id="u1")
check("junk stays junk even with the knob on", rp.coarse_gate(ev_junk, "none", Q, consider_tagged=True) == (False, "junk"))

# pre_screen wires the knob through the profile
p_off = rp.BotProfile(bot_id="T", name="Javis Vũ")
p_on = rp.BotProfile(bot_id="T", name="Javis Vũ", consider_tagged=True)
check("pre_screen: knob off -> addressed_other", rp.pre_screen(ev, p_off, st, NOW)["code"] == "addressed_other")
check("pre_screen: knob on -> candidate", rp.pre_screen(ev, p_on, st, NOW)["candidate"])

# the owner's thumbs-down on a silenced tag creates a case that opens the gate next time
d = st.log_decision({"bot_id": "T", "chat_id": "g1", "ts": NOW, "text": ev.text, "verdict": "silent",
                     "candidate": False, "silence_code": "addressed_other", "address_level": "none",
                     "signals": {"question_score": 0.6}}, NOW)
p_learn = rp.BotProfile(bot_id="T", name="Javis Vũ", learning_enabled=True, mode="on")
check("owner thumbs-down on a silenced tag", rp.owner_label(st, p_learn, d, "down", NOW) == "missed")
ev2 = rp.Event(channel="zalo", bot_id="T", chat_id="g1", chat_type="group", msg_id="m2", ts=NOW + 60,
               text="@Quý anh ơi lịch học Javis tuần sau thế nào", sender_id="u2")
check("a similar tagged message now passes the gate", rp.pre_screen(ev2, p_off, st, NOW + 60)["candidate"])

# prompt mentions the tag signal
prompt = rp.build_prompt(ev, p_on, "none", rp.AddressResult("none", []), {}, [], [])
check("judge prompt states the message tags someone else", "Tin mở đầu bằng tag một người khác: có" in prompt)

# ---- forget and delete_bot clear the new tables ----
st.log_change({"bot_id": "A", "actor": "review", "op": "lesson_add", "status": "applied"}, NOW)
st.set_review_ts("A", NOW)
st.forget("A")
check("forget clears tuning, changes and review state",
      st.get_tuning("A") == {} and st.list_changes("A") == [] and st.get_review_ts("A") == 0.0)
st.set_tuning("B", "eagerness", "low", NOW)
st.delete_bot("B")
check("delete_bot clears tuning", st.get_tuning("B") == {})

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nall ok")
