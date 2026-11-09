"""Personal Zalo: "đang soạn tin" in groups once the bot decided to answer, and a sturdier private indicator.

    python tests/run.py zalo_group_typing      (no network, fake MCP, fake engine)

Request 09/11/2026 (a bot used as an advisor in a company Zalo group): the indicator only showed in private chats, so a
group sat in silence for 20 to 30 seconds and people thought the bot had not heard. Locked here:
  1. Groups: the indicator starts only when `chatbot_runtime` calls the channel's `_on_compose` hook, i.e. after the
     reply-policy judge said reply and the chat is not taken over. A turn that ends in silence never shows it.
  2. It lasts until the reply has been SENT, not just until the model finished writing.
  3. Each bot can switch it off (`group_typing`, on when never set); private chats are not affected by that switch.
  4. The hook never reaches the engine (a callable in meta), and a raising hook never costs the turn.
  5. send_typing: only an MCP WITHOUT the tool mutes the account for an hour. One chat that refuses, or a transient
     MCP error, ends the indicator for that turn only (before, one refusal switched typing off in every chat).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-gtyping-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_reply_policy  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{str(detail)[:400]}]"))
    if not cond:
        fails.append(name)


CID = "zalo-gt"
GROUP = "2000000001"
PERSON = "1000000001"
TYPING, SENT = [], []
NEXT = {"typing": "ok"}


async def fake_goi(conn, tool, args):
    if tool == "zalo_send_typing":
        TYPING.append((time.monotonic(), dict(args)))
        mode = NEXT["typing"]
        if mode == "missing":
            raise RuntimeError("Tool zalo_send_typing not found")
        if mode == "timeout":
            raise RuntimeError("timeout after 30s")
        if mode == "refused":
            return {"success": False, "error": "blocked"}
        return {"success": True}
    return {}


zc.ket_noi_theo_id = lambda cid: {"id": CID, "label": "Nick thử"} if cid == CID else None
zc._goi = fake_goi
zp.TYPING_DELAY = 0
zp.TYPING_EVERY = 0.01


def reset(mode="ok"):
    TYPING.clear()
    SENT.clear()
    zp._TYPING_OFF_UNTIL.clear()
    NEXT["typing"] = mode


# ============================================================
# 1. send_typing: what mutes the account and what does not
# ============================================================
reset("refused")
check("a chat that refuses: False for this call", asyncio.run(zp.send_typing(CID, GROUP, "group")) is False)
check("CANARY: one refusing chat does not mute the account", CID not in zp._TYPING_OFF_UNTIL, zp._TYPING_OFF_UNTIL)
NEXT["typing"] = "ok"
check("the next chat still gets its indicator", asyncio.run(zp.send_typing(CID, PERSON, "private")) is True)
reset("timeout")
check("a transient MCP error: False, account not muted",
      asyncio.run(zp.send_typing(CID, PERSON)) is False and CID not in zp._TYPING_OFF_UNTIL)
reset("missing")
check("an MCP without the tool mutes the account for TYPING_OFF",
      asyncio.run(zp.send_typing(CID, PERSON)) is False and zp._TYPING_OFF_UNTIL.get(CID, 0) > time.time() + 60)
TYPING.clear()
check("and is not asked again meanwhile", asyncio.run(zp.send_typing(CID, PERSON)) is False and not TYPING)
reset()
asyncio.run(zp.send_typing(CID, GROUP, "group"))
check("a group goes out with threadType 1", TYPING and TYPING[0][1] == {"threadId": GROUP, "threadType": 1}, TYPING)


async def _handle_twice():
    h = zp.TypingHandle(CID, GROUP, "group")
    h.start(0)
    first = h.task
    h.start(0)
    same = h.task is first
    await asyncio.sleep(0.03)
    h.stop()
    await asyncio.sleep(0)
    return same, first.cancelled() or first.done()

reset()
same, stopped = asyncio.run(_handle_twice())
check("TypingHandle.start twice runs one loop, stop ends it", same and stopped)

# ============================================================
# 2. Transport: group turns only after the hook, kept until the reply is sent
# ============================================================
CFG = {"id": "bot-gt", "reply_when": "always"}
ANSWER = {"call_hook": True, "out": {"text": "Dạ em trả lời ạ", "files": []}}
METAS = []


async def answer(text, meta, _p):
    METAS.append(dict(meta))
    await asyncio.sleep(0.03)
    n_before = len(TYPING)
    if ANSWER["call_hook"] and callable(meta.get("_on_compose")):
        meta["_on_compose"]()
    ANSWER["before_hook"] = n_before
    await asyncio.sleep(0.05)
    return ANSWER["out"]


def make_bot(cfg):
    t = zp.Transport(CID, [], answer, cfg_fn=lambda: cfg)
    zc._BOTS[CID] = t

    async def fake_send(thread, cau, chat_type="private", meta=None, receipt_row=0):
        n = len(TYPING)
        await asyncio.sleep(0.05)       # a slow send: the indicator must keep going meanwhile
        SENT.append((thread, cau, chat_type, n, len(TYPING)))
    t._gui = fake_send
    return t


def group_msg(text="cho em hỏi quy trình nghỉ phép", **kw):
    ev = {"chat_type": "group", "message_type": "text", "text": text, "external_chat_id": GROUP,
          "external_message_id": f"m{time.time_ns()}", "sender_id": PERSON, "sender_name": "Lan",
          "sender_type": "customer", "account_id": CID, "created_at": time.time(), "metadata": {}}
    ev.update(kw)
    return ev


def private_msg(text="cho em hỏi giá"):
    return group_msg(text, chat_type="private", external_chat_id=PERSON)


reset()
METAS.clear()
t = make_bot(dict(CFG))
asyncio.run(t.xu_ly(group_msg()))
group_calls = [a for _, a in TYPING if a["threadType"] == 1]
check("(setup) the group turn was answered and sent", len(SENT) == 1 and SENT[0][0] == GROUP, (SENT, t.last_error))
check("group: no indicator before the bot decided to answer", ANSWER.get("before_hook") == 0, TYPING)
check("group: indicator once the hook fired", group_calls and group_calls[0]["threadId"] == GROUP, TYPING)
check("group: still repeated while the reply was being sent", SENT and SENT[0][4] > SENT[0][3], SENT)
n_after = len(TYPING)
asyncio.run(asyncio.sleep(0.05))
check("group: stopped once the reply was out", len(TYPING) == n_after, (n_after, len(TYPING)))

reset()
ANSWER.update(call_hook=False, out={"text": "", "files": [], "im_lang": True})
asyncio.run(make_bot(dict(CFG)).xu_ly(group_msg()))
check("CANARY group: a turn that ends in silence never shows the indicator", not TYPING and not SENT, (TYPING, SENT))

reset()
ANSWER.update(call_hook=True, out={"text": "Dạ em trả lời ạ", "files": []})
METAS.clear()
asyncio.run(make_bot(dict(CFG, group_typing=False)).xu_ly(group_msg()))
check("group_typing off: no hook handed to the turn", METAS and "_on_compose" not in METAS[-1], METAS[-1:])
check("group_typing off: no indicator in the group", not TYPING and len(SENT) == 1, TYPING)

reset()
ANSWER.update(call_hook=False, out={"text": "Dạ giá 85.000đ ạ", "files": []})
METAS.clear()
asyncio.run(make_bot(dict(CFG, group_typing=False)).xu_ly(private_msg()))
priv = [a for _, a in TYPING if a == {"threadId": PERSON, "threadType": 0}]
check("private: indicator from the start of the turn, whatever the group switch", priv, TYPING)
check("private: no hook handed to the turn", METAS and "_on_compose" not in METAS[-1])
check("private: still going while the reply was sent", SENT and SENT[0][4] > SENT[0][3], SENT)

# The live setting, read from the bot record.
check("unset group_typing is on", chatbot_store.group_typing_on({}) and chatbot_store.group_typing_on({"group_typing": None}))
check("False / '0' is off", not chatbot_store.group_typing_on({"group_typing": False})
      and not chatbot_store.group_typing_on({"group_typing": "0"}))
bid, err = chatbot_store.create_bot({"name": "Bot nhóm", "agent_slug": "tro-ly", "brain": "b", "channel": "zalo_personal"})
check("a new bot without the field: on", not err and chatbot_store.get_bot(bid).get("group_typing") is True, err)
chatbot_store.update_bot(bid, {"group_typing": "0"})
check("switched off from the form", chatbot_store.get_bot(bid)["group_typing"] is False)
chatbot_store.update_bot(bid, {"name": "Bot nhóm 2"})
check("another field saved: switch untouched", chatbot_store.get_bot(bid)["group_typing"] is False)
chatbot_store.update_bot(bid, {"group_typing": "1"})
check("switched on again", chatbot_store.get_bot(bid)["group_typing"] is True)
bid2, _ = chatbot_store.create_bot({"name": "Bot tắt", "agent_slug": "tro-ly", "brain": "b", "channel": "zalo_personal",
                                    "group_typing": "0"})
check("created with the switch off", chatbot_store.get_bot(bid2)["group_typing"] is False)

# ============================================================
# 3. chatbot_runtime: the hook fires after the gates, never reaches the engine
# ============================================================
BRAIN = Path(tempfile.mkdtemp(prefix="brain-gtyping-"))
ENGINE = []


async def engine(text, meta=None, progress=None, channel="", bot=None, **kw):
    ENGINE.append(dict(meta or {}))
    return {"text": "Dạ em trả lời ạ.", "files": []}


chatbot_runtime.wire(answer=engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Cố vấn", "role": "Trực nhóm"}, "Luật riêng."))
rbid, err = chatbot_store.create_bot({"name": "Cố vấn", "agent_slug": "co-van", "brain": "b", "token": "1:x",
                                      "channel": "zalo", "muc_quyen": "suggest", "audience": "all",
                                      "xac_nhan_rui_ro": True})
check("(setup) runtime bot created", bool(rbid) and not err, err)
fn = chatbot_runtime._make_answer_fn(rbid)
HOOK = []


def run_turn(chat_type="group", **extra):
    meta = {"chat_type": chat_type, "chat_id": GROUP if chat_type == "group" else PERSON, "user_id": PERSON,
            "user_name": "Lan", "platform": "zalo_personal", "_kenh": "zalo_personal", "account_id": "acc-1",
            "message_id": f"m{time.time_ns()}", "mentioned": True, "_on_compose": lambda: HOOK.append(len(ENGINE))}
    meta.update(extra)
    return asyncio.run(fn("cho em hỏi quy trình", meta))


HOOK.clear()
ENGINE.clear()
out = run_turn()
check("called turn: hook fired once, before the engine ran", HOOK == [0] and len(ENGINE) == 1, (HOOK, len(ENGINE)))
check("CANARY: the hook callable never reaches the engine", ENGINE and "_on_compose" not in ENGINE[-1], ENGINE[-1:])

HOOK.clear()
ENGINE.clear()
run_turn(_on_compose=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
check("a raising hook never costs the turn", len(ENGINE) == 1)

# Taken over by a person on the inbox page: silent, no indicator.
orig_mode = conversations.che_do
conversations.che_do = lambda *a, **k: "human"
HOOK.clear()
ENGINE.clear()
run_turn()
conversations.che_do = orig_mode
check("taken-over chat: no hook, no engine", not HOOK and not ENGINE, (HOOK, ENGINE))

# Judge mode on, a message nobody addressed: the judge decides.
chatbot_store.update_bot(rbid, {"reply_when": "auto", "groups": GROUP,
                                "reply_policy": '{"mode": "on"}'})
orig_decide = chatbot_reply_policy.decide
VERDICT = {"v": "silent"}


class _Dec:
    def __init__(self, v):
        self.verdict, self.reaction, self.doc = v, None, None


async def fake_decide(*a, **k):
    return _Dec(VERDICT["v"])

chatbot_reply_policy.decide = fake_decide
HOOK.clear()
ENGINE.clear()
run_turn(mentioned=False)
check("judge says silent: no hook, no engine", not HOOK and not ENGINE, (HOOK, ENGINE))
VERDICT["v"] = "reply"
HOOK.clear()
ENGINE.clear()
run_turn(mentioned=False)
check("judge says reply: hook fired before the engine", HOOK == [0] and len(ENGINE) == 1, (HOOK, len(ENGINE)))
chatbot_reply_policy.decide = orig_decide

print()
if fails:
    print(f"{len(fails)} FAIL: " + ", ".join(fails))
    sys.exit(1)
print("ALL PASS")
