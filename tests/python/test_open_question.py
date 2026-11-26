"""The bot remembers it is waiting for an answer (issue #1852).

    python tests/run.py open_question      (no network, fake engine and judge)

A group bot in "Tự đánh giá" mode asked a customer "Chị cần mấy kg ạ?" and the customer answered two hours later
with "7kg e ơi": no "?", no question word, past the 3-minute follow-up window. The judge's gate said `no_signal` and
the bot stayed silent. Now the last message the bot (or a staff member) sent to one person in a chat opens a question
when it asks something; while it is open (hours), that person's next message in that chat is a follow-up. Checks:
  1. `asks_question`: conservative detector, end of the message only, diacritics respected;
  2. the store: open, claim once (same message again = same answer), closed after, other person / chat, expiry,
     forgotten with the bot, kept in sqlite (survives a restart of the RAM state);
  3. the signal: an open question makes "7kg e ơi" a follow-up candidate; without it, `no_signal`;
  4. end to end on a Telegram group: same person late answer -> judged and answered; another person -> silent;
     another group -> silent; expired -> silent; a second message after the answer -> silent; a reply without a
     question closes it; taken over by a person -> silent;
  5. a staff member's hand-typed question to one tagged person opens one too (personal Zalo hook), an untargeted one
     does not.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-openq-")
os.environ.pop("JAVIS_REPLY_POLICY_SHADOW", None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_reply_policy as rp  # noqa: E402
import chatbot_reply_policy_store as st  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. asks_question ---------------------------------------------------------------------------------
ASKS = {
    "Chị cần mấy kg ạ?": True,
    "Chị cần mấy kg ạ": True,
    "Anh lấy thêm không ạ": True,
    "anh lay them khong a": True,
    "Chị nhận được hàng chưa": True,
    "Chị ship về đâu ạ 😊": True,
    "Chị đặt bao nhiêu cái ạ": True,
    "Shop gửi chị ảnh mẫu nhé. Chị ưng mẫu nào ạ": True,
    "Giá 120k ạ.\n\nChị lấy mấy chai ạ?": True,
    "chị lấy màu gì chị": True,
    "Dạ không ạ": False,
    "Chưa ạ": False,
    "Không có gì ạ": False,
    "Không sao đâu chị": False,
    "Dạ size nào cũng được ạ": False,
    "Cảm ơn chị nhé 😊": False,
    "Dạ vâng, em ghi nhận ạ.": False,
    "Chị ưng mẫu nào ạ? Em gửi thêm ảnh nhé.": False,
    "Chị cần gì cứ nhắn em nhé": False,
    "Xem tại https://shop.vn/sp?id=3": False,
    "Hàng về rồi chị ơi!": False,
    "": False,
}
wrong = {k: v for k, v in ASKS.items() if rp.asks_question(k) != v}
check("asks_question: every case as expected", not wrong, wrong)

# ---- 2. the store ---------------------------------------------------------------------------------------
H = rp.OPEN_QUESTION_S
now = time.time()
st.set_open_question("b1", "g1", "u1", "bot", now - 7200)
check("store: the addressee's late message claims the question",
      st.claim_open_question("b1", "g1", "u1", "m1", now, H, now) == "bot")
check("store: the same message again gets the same answer (judged twice)",
      st.claim_open_question("b1", "g1", "u1", "m1", now, H, now) == "bot")
check("store: the next message of that person is no longer an answer",
      st.claim_open_question("b1", "g1", "u1", "m2", now + 5, H, now) == "")
st.set_open_question("b1", "g1", "u1", "staff", now - 60)
check("store: another person in the chat claims nothing", st.claim_open_question("b1", "g1", "u2", "m3", now, H, now) == "")
check("store: the same person in another chat claims nothing",
      st.claim_open_question("b1", "g2", "u1", "m4", now, H, now) == "")
check("store: another bot claims nothing", st.claim_open_question("b2", "g1", "u1", "m5", now, H, now) == "")
check("store: a message from before the question is not its answer",
      st.claim_open_question("b1", "g1", "u1", "m6", now - 120, H, now) == "")
check("store: who asked is kept", st.claim_open_question("b1", "g1", "u1", "m7", now, H, now) == "staff")
st.set_open_question("b1", "g1", "u3", "bot", now - H - 10)
check("store: an expired question claims nothing", st.claim_open_question("b1", "g1", "u3", "m8", now, H, now) == "")
st.set_open_question("b1", "g1", "u4", "bot", now - 30)
st.clear_open_question("b1", "g1", "u4")
check("store: a cleared question claims nothing", st.claim_open_question("b1", "g1", "u4", "m9", now, H, now) == "")
st.set_open_question("b1", "g1", "u5", "bot", now - 30)
rp.reset_runtime_state()
check("store: survives a restart of the RAM state",
      st.claim_open_question("b1", "g1", "u5", "m10", now, H, now) == "bot")
st.set_open_question("b9", "g1", "u1", "bot", now - 30)
st.delete_bot("b9")
check("store: deleting the bot forgets its questions", st.claim_open_question("b9", "g1", "u1", "m11", now, H, now) == "")
st.set_open_question("b8", "g1", "u1", "bot", now - 30)
st.forget("b8", "g1")
check("store: forgetting a chat forgets its questions", st.claim_open_question("b8", "g1", "u1", "m12", now, H, now) == "")
con = sqlite3.connect(str(st.db_path()))
cols = [r[1] for r in con.execute("PRAGMA table_info(open_questions)")]
con.close()
check("store: ids and times only, never the words", "text" not in cols and "addressee" in cols, cols)

# ---- 3. the signal --------------------------------------------------------------------------------------
prof = rp.BotProfile(bot_id="b1", name="Lan")


def _ev(**kw):
    base = dict(channel="telegram", bot_id="b1", chat_id="g1", chat_type="group", msg_id="x", ts=time.time(),
                text="7kg e ơi", sender_id="u1")
    base.update(kw)
    return rp.Event(**base)


sig = rp.compute_signals(_ev(open_question="bot"), prof, rp.AddressResult())
check("signal: an open question makes the message a follow-up", sig["follow_up"]["value"] == 1.0, sig["follow_up"])
check("gate: '7kg e ơi' answering an open question is a candidate",
      rp.coarse_gate(_ev(open_question="bot"), "none", sig) == (True, ""))
sig0 = rp.compute_signals(_ev(), prof, rp.AddressResult())
check("gate: the same words without an open question stay no_signal", rp.coarse_gate(_ev(), "none", sig0)
      == (False, "no_signal"), rp.coarse_gate(_ev(), "none", sig0))
check("judge prompt says who asked",
      "question the staff asked them" in rp.build_prompt(_ev(open_question="staff"), prof, "possible",
                                                          rp.AddressResult(), sig, [], []))

# ---- 4. end to end on a Telegram group ------------------------------------------------------------------
CALLS, JUDGED = [], []
REPLY = {"v": "Dạ chị cần mấy kg ạ?"}


async def _engine(text, meta, progress, *, channel="", bot=None, **kw):
    CALLS.append(text)
    return {"text": REPLY["v"], "files": []}


async def _judge(prompt, purpose=""):
    if purpose != "judge":
        return ""
    JUDGED.append(prompt)
    return '{"verdict":"reply","score":0.9,"reason":"answers the bot"}'


BRAIN = Path(tempfile.mkdtemp(prefix="brain-openq-"))
chatbot_runtime.wire(answer=_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Bán gạo"}, "Trả lời ngắn."),
                     session_probe=lambda key: ("sid", 0), session_undo=lambda key, keep: None)
rp.wire(ask=_judge)
bid, err = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "muc_quyen": "suggest",
                                     "reply_when": "auto", "groups": ["-1001", "-1002"]})
check("(setup) bot created", bool(bid) and not err, err)
answer = chatbot_runtime._make_answer_fn(bid)
MID = [0]


def meta(chat="-1001", uid="u1", name="Chị Hoa", mentioned=False):
    MID[0] += 1
    return {"chat_id": chat, "chat_type": "group", "user_id": uid, "user_name": name, "message_id": f"tg{MID[0]}",
            "platform": "telegram", "_kenh": "telegram", "mentioned": mentioned}


def turn(text, m):
    return asyncio.run(answer(text, m)) or {}


def age_questions(seconds):
    con = sqlite3.connect(str(st.db_path()))
    con.execute("UPDATE open_questions SET asked_ts=asked_ts-? WHERE bot_id=?", (seconds, bid))
    con.commit()
    con.close()


def ask_again(uid="u1", chat="-1001"):
    """The customer tags the bot, the bot answers with a question: a question is open for that customer. What the
    judge learned from the previous scenario (a "7kg e ơi" it answered becomes a positive case) is forgotten first,
    so each scenario shows the open question alone."""
    st.forget(bid)
    REPLY["v"] = "Dạ chị cần mấy kg ạ?"
    r = turn("Lan ơi gạo ST25 còn không em", meta(chat=chat, uid=uid, mentioned=True))
    return r.get("text") == "Dạ chị cần mấy kg ạ?"


check("(setup) the bot asks the customer in the group", ask_again())
age_questions(2 * 3600)
REPLY["v"] = "Dạ em lên đơn 7kg cho chị ạ."
n = len(JUDGED)
r = turn("7kg e ơi", meta())
check("late answer of the same person: judged", len(JUDGED) == n + 1, len(JUDGED))
check("late answer of the same person: the bot answers", r.get("text") == "Dạ em lên đơn 7kg cho chị ạ.", r)

n = len(JUDGED)
r = turn("Ok e, tối chị qua lấy", meta())
check("the answer closed it: the person's next message is not a follow-up",
      len(JUDGED) == n and not r.get("text"), (len(JUDGED), r))

check("(setup) the bot asks again", ask_again())
n = len(JUDGED)
r = turn("7kg e ơi", meta(uid="u2", name="Anh Nam"))
check("another person in the group: silent, not judged", len(JUDGED) == n and not r.get("text"), r)
r = turn("7kg e ơi", meta(chat="-1002"))
check("the same person in another group: silent, not judged", len(JUDGED) == n and not r.get("text"), r)

age_questions(rp.OPEN_QUESTION_S + 60)
r = turn("7kg e ơi", meta())
check("expired question: silent, not judged", len(JUDGED) == n and not r.get("text"), r)

check("(setup) the bot asks again", ask_again())
REPLY["v"] = "Dạ vâng, em ghi nhận ạ."
turn("Lan ơi chị đổi ý rồi nhé", meta(mentioned=True))
n = len(JUDGED)
r = turn("7kg e ơi", meta())
check("a later bot reply without a question closes it", len(JUDGED) == n and not r.get("text"), r)

check("(setup) the bot asks again", ask_again())
aid, kenh = chatbot_runtime._tai_khoan_cua(chatbot_store.get_bot(bid), meta())
cid = conversations.conversation_id_of(kenh, aid, "-1001")
conversations.dat_che_do(cid, "human")
n, c = len(JUDGED), len(CALLS)
r = turn("7kg e ơi", meta())
check("taken over by a person: the bot stays silent", not r.get("text") and len(CALLS) == c and len(JUDGED) == n, r)
conversations.dat_che_do(cid, "ai")

# Personal Zalo judges a group message twice: the transport's `prepare`, then the turn. Both must see the answer.
check("(setup) the bot asks again", ask_again())
hooks = chatbot_runtime.PolicyHooks(bid)
REPLY["v"] = "Dạ em lên đơn 7kg cho chị ạ."


async def _prepare_then_turn(m):
    pol = hooks.prepare("7kg e ơi", m)
    return pol, await answer("7kg e ơi", m)


n = len(JUDGED)
pol, r = asyncio.run(_prepare_then_turn(meta()))
check("judged twice (transport, then turn): both see the answer",
      (pol or {}).get("action") == "answer" and len(JUDGED) == n + 1
      and (r or {}).get("text") == "Dạ em lên đơn 7kg cho chị ạ.", (pol, r))

# ---- 5. a staff member's question -----------------------------------------------------------------------
staff_ev = {"external_chat_id": "-1001", "chat_type": "group", "message_type": "text", "created_at": time.time(),
            "text": "@Anh Nam anh lấy mấy bao ạ", "metadata": {"mentions": [{"uid": "u2"}]}}
check("staff: a question tagging one person opens one", hooks.staff_wrote(staff_ev) is True)
check("staff: one quoting a person's message opens one",
      hooks.staff_wrote(dict(staff_ev, text="Chị lấy loại nào ạ", metadata={"replyTo": {"senderId": "u3"}})) is True)
check("staff: a question to the whole group opens none",
      hooks.staff_wrote(dict(staff_ev, text="Cả nhà ai cần gạo không ạ", metadata={})) is False)
check("staff: a question tagging two people opens none",
      hooks.staff_wrote(dict(staff_ev, metadata={"mentions": [{"uid": "u2"}, {"uid": "u4"}]})) is False)
age_questions(3600)
REPLY["v"] = "Dạ em ghi 3 bao cho anh ạ."
n = len(JUDGED)
r = turn("3 bao nhé", meta(uid="u2", name="Anh Nam"))
check("staff question: the tagged person's late answer is judged and answered",
      len(JUDGED) == n + 1 and r.get("text") == "Dạ em ghi 3 bao cho anh ạ." and "question the staff" in JUDGED[-1], r)

import types  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

zc._BOTS["zl-9"] = types.SimpleNamespace(policy=hooks)
zc._note_staff_question("zl-9", dict(staff_ev, text="Chị Hoa lấy mấy kg ạ", created_at=time.time(),
                                     metadata={"mentions": ["u1"]}))
check("personal Zalo: the owner's hand-typed question reaches the bot on duty",
      st.claim_open_question(bid, "-1001", "u1", "zk1", time.time() + 1, rp.OPEN_QUESTION_S) == "staff")
zc._note_staff_question("zl-unknown", staff_ev)      # no bot on duty: nothing happens, nothing raises
zc._BOTS.pop("zl-9", None)

chatbot_store.update_bot(bid, {"reply_when": "mention"})
check("mention mode: nothing is tracked", hooks.staff_wrote(dict(staff_ev, created_at=time.time())) is False)

check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
