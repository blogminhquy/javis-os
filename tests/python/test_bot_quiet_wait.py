"""Every customer bot waits for a private chat to go quiet, then answers once (issue #1873).

    python tests/run.py bot_quiet_wait      (no network, a fake transport)

Before, only personal Zalo gathered a customer's quick messages. On Messenger an ad's prefilled question and two
quick-reply taps 12 seconds later got two separate replies. Checks:
  1. the setting: `quiet_wait_s` is cleaned (0-60 whole seconds), saved, cleared; `quiet_wait_of` reads the chat's
     exception first, then the bot, then the default, and 0 for groups and comments;
  2. a customer bot gathers three quick private messages into ONE turn, in order;
  3. a group message, a comment, an owner bot and a bot with 0 seconds answer at once;
  4. the wait never runs past GATHER_CAP_S, however often the customer writes;
  5. personal Zalo reads the same bot setting; the runtime and the form wire it; both dictionaries have its words.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-quiet-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import bot_gateway  # noqa: E402
import chatbot_store  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(detail) + "]") if detail and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. the setting ------------------------------------------------------------------------------------
c = chatbot_store.clean_quiet_wait
check("clean: blank, junk, fractions and out of range are unset",
      c("") is None and c(None) is None and c("x") is None and c(1.5) is None and c(61) is None and c(-1) is None
      and c(True) is None)
check("clean: 0 and a whole number are kept", c("0") == 0 and c(10) == 10 and c("60") == 60)
bid, err = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "muc_quyen": "suggest",
                                     "quiet_wait_s": "9"})
check("(setup) bot created with a wait", bool(bid) and not err and chatbot_store.get_bot(bid)["quiet_wait_s"] == 9, err)
chatbot_store.update_bot(bid, {"quiet_wait_s": "abc"})
check("update: an unreadable value keeps the old one", chatbot_store.get_bot(bid)["quiet_wait_s"] == 9)
chatbot_store.update_bot(bid, {"quiet_wait_s": ""})
check("update: blank clears it", chatbot_store.get_bot(bid)["quiet_wait_s"] is None)

qw = chatbot_store.quiet_wait_of
priv = {"chat_type": "private", "chat_id": "u1", "account_id": "a1"}
check("default: 5 seconds", qw({}, priv) == chatbot_store.DEFAULT_QUIET_WAIT_S == 5)
check("the bot's own wait", qw({"quiet_wait_s": 12}, priv) == 12)
check("the chat's exception wins", qw({"quiet_wait_s": 12, "ngoai_le": [
    {"chat_id": "u1", "account_id": "a1", "muc_quyen": "suggest", "cho_giay": 0}]}, priv) == 0)
check("a group answers at once", qw({"quiet_wait_s": 12}, {"chat_type": "group", "chat_id": "g"}) == 0)
check("a comment under a post answers at once", qw({}, dict(priv, comment=True)) == 0)


# ---- 2-4. the gateway ----------------------------------------------------------------------------------
class FakeBot(bot_gateway.HangLuot):
    def __init__(self, customer=True, wait=0.3):
        self.command_fn = None
        self.precheck_fn = None
        self.giau_trang_thai = customer
        self._current, self._cho, self._stop = {}, {}, False
        self.turns, self.sent = [], []
        if wait is not None:
            self.quiet_wait_fn = lambda chat, meta: wait

    async def _send(self, client, chat, text, *a, **k):
        self.sent.append(text)

    async def _handle_turn(self, client, chat, text, meta=None):
        self.turns.append((chat, text))


PRIV = {"chat_type": "private"}


async def gathered():
    bot = FakeBot()
    await bot._dispatch(None, "u1", "Nhập hàng lần đầu cần vốn bao nhiêu?", PRIV)
    await asyncio.sleep(0.1)
    await bot._dispatch(None, "u1", "Giá sỉ", PRIV)
    await asyncio.sleep(0.1)
    await bot._dispatch(None, "u1", "Ship tỉnh", PRIV)
    early = list(bot.turns)
    await asyncio.sleep(0.6)
    return early, bot.turns


early, turns = asyncio.run(gathered())
check("nothing is answered while the customer keeps writing", early == [], early)
check("three quick messages become ONE turn, in order",
      turns == [("u1", "Nhập hàng lần đầu cần vốn bao nhiêu?\nGiá sỉ\nShip tỉnh")], turns)


async def at_once(bot, chat, meta):
    await bot._dispatch(None, chat, "Chào shop", meta)
    await asyncio.sleep(0.05)
    return list(bot.turns)


check("a group message answers at once (the transport's wait fn says 0)",
      asyncio.run(at_once(FakeBot(wait=0), "g1", {"chat_type": "group"})) == [("g1", "Chào shop")])
check("an owner bot never waits", asyncio.run(at_once(FakeBot(customer=False), "o1", PRIV)) == [("o1", "Chào shop")])
check("a transport without the wait fn answers at once",
      asyncio.run(at_once(FakeBot(wait=None), "u2", PRIV)) == [("u2", "Chào shop")])


async def capped():
    old = bot_gateway.GATHER_CAP_S
    bot_gateway.GATHER_CAP_S = 0.5
    try:
        bot = FakeBot(wait=0.3)
        for i in range(8):
            await bot._dispatch(None, "u3", f"tin {i}", PRIV)
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.4)
        return bot.turns
    finally:
        bot_gateway.GATHER_CAP_S = old


t = asyncio.run(capped())
joined = "\n".join(x[1] for x in t)
check("the wait stops at the cap: the first turn runs before the customer stops writing",
      len(t) >= 2 and t[0][1].startswith("tin 0") and "tin 7" not in t[0][1], t)
check("...and no message is lost", all(f"tin {i}" in joined for i in range(8)), t)

# ---- 5. wiring -----------------------------------------------------------------------------------------
zp = (SERVER / "zalo_personal_channel.py").read_text(encoding="utf-8")
check("personal Zalo reads the same setting", "chatbot_store.quiet_wait_of(cfg" in zp and "default=CHO_KHACH_IM" in zp)
rt = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
check("the runtime gives customer bots the wait", "tb.quiet_wait_fn = " in rt)
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("create route takes the field", 'quiet_wait_s: str = Form("")' in main_src and '"quiet_wait_s": quiet_wait_s' in main_src)
js = (ROOT / "dashboard" / "chatbots.js").read_text(encoding="utf-8")
check("form: the control is drawn and saved", 'id="cbQuietWait"' in js and "quiet_wait_s: quiet" in js)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"i18n {lang}: the control's words exist",
          all(d.get(k) for k in ("cb.quiet_wait", "cb.ph_quiet_wait", "cb.hint_quiet_wait", "cb.quiet_wait_sai")))

check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
