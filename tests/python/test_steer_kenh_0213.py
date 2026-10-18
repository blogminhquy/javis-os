"""0.213.0: send more while Javis is working, on the chat channels (Telegram, Discord, Slack, Lark, Messenger, Zalo).

Before, an owner bot answered "busy, send /stop" and the message was lost. Now bot_gateway hands it to the running
turn (the same steer_inbox as the web dashboard, 0.206.0); what that turn never reads runs right after.

Covers: a turn that reads mid-way (acknowledged as "live", no second turn), a one-shot engine (acknowledged as "after",
runs as the next turn), /stop dropping what was waiting, customer bots unchanged, the history sink, two bots sharing a
chat id, the Claude Code hook on channel turns, and the main.py wiring.

Run:
    python tests/run.py steer_kenh
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-steer-kenh-"))

import steer_inbox as si  # noqa: E402
from telegram_bot import TelegramBot  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


class FakeResp:
    def __init__(self, data=None):
        self._d = data or {"ok": True, "result": {"message_id": 1}}

    def json(self):
        return self._d


class FakeTelegram:
    def __init__(self):
        self.calls = []

    async def post(self, url, json=None, **kw):
        self.calls.append((url.rsplit("/", 1)[-1], json or {}))
        return FakeResp()

    async def get(self, url, params=None, **kw):
        return FakeResp({"ok": True, "result": []})

    def texts(self):
        return [j.get("text", "") for m, j in self.calls if m == "sendMessage"]


async def until_idle(bot, chat, rounds=400):
    for _ in range(rounds):
        await asyncio.sleep(0.005)
        if not bot._busy(chat) and not bot._cho.get(chat):
            return


async def live_turn():
    """The engine reads the inbox at its next step: the message joins the running turn."""
    gate = asyncio.Event()
    seen, notes, sunk = [], [], []

    async def answer(text, meta, progress):
        seen.append(text)
        si.INBOX.set_sink(si.current_sid(), lambda texts: sunk.extend(texts))
        await gate.wait()
        notes.append(si.INBOX.take_note_current())   # what a tool loop / the Claude hook does
        return "xong"

    tg = FakeTelegram()
    b = TelegramBot("TOKEN", "", answer)
    await b._dispatch(tg, "42", "soạn báo cáo tuần", {})
    await asyncio.sleep(0)
    await b._dispatch(tg, "42", "thêm phần so với tuần trước", {})
    acks = [t for t in tg.texts() if t[:1] in ("↪", "📥")]
    check("live: the owner gets one short acknowledgement", len(acks) == 1 and acks[0].startswith("↪"))
    check("live: no more 'busy, send /stop'", not any("/stop" in t for t in tg.texts()))
    gate.set()
    await until_idle(b, "42")
    check("live: the running turn read the message, fenced", notes and "thêm phần so với tuần trước" in notes[0]
          and "<<<" in notes[0])
    check("live: no second turn for a message already read", seen == ["soạn báo cáo tuần"])
    check("live: the read message went to the chat history", sunk == ["thêm phần so với tuần trước"])
    check("live: the inbox is closed after the turn", not si.INBOX.running(b._steer_sid("42")))


async def after_turn():
    """A one-shot engine (Grok, Antigravity, Codex exec) cannot read mid-way: the message runs right after."""
    gate = asyncio.Event()
    seen = []

    async def answer(text, meta, progress):
        seen.append(text)
        if len(seen) == 1:
            si.INBOX.set_live(si.current_sid(), False)
            await gate.wait()
        return "xong"

    tg = FakeTelegram()
    b = TelegramBot("TOKEN", "", answer)
    await b._dispatch(tg, "7", "viết bài đăng", {})
    await asyncio.sleep(0)
    await b._dispatch(tg, "7", "ngắn thôi", {})
    await b._dispatch(tg, "7", "kèm hashtag", {})
    acks = [t for t in tg.texts() if t[:1] in ("↪", "📥")]
    check("after: acknowledged as handled right after", len(acks) == 2 and all(t.startswith("📥") for t in acks))
    gate.set()
    await until_idle(b, "7")
    check("after: both messages run as ONE next turn, in order", seen == ["viết bài đăng", "ngắn thôi\nkèm hashtag"])


async def stop_drops():
    gate = asyncio.Event()
    seen = []

    async def answer(text, meta, progress):
        seen.append(text)
        si.INBOX.set_live(si.current_sid(), False)
        await gate.wait()
        return "xong"

    tg = FakeTelegram()
    b = TelegramBot("TOKEN", "", answer)
    await b._dispatch(tg, "9", "câu 1", {})
    await asyncio.sleep(0)
    await b._dispatch(tg, "9", "câu 2", {})
    await b._dispatch(tg, "9", "/stop", {})
    gate.set()
    await until_idle(b, "9")
    check("/stop: what was waiting does not run afterwards", seen == ["câu 1"])


async def customer_unchanged():
    gate = asyncio.Event()
    seen, sids = [], []

    async def answer(text, meta, progress):
        seen.append(text)
        sids.append(si.current_sid())
        if len(seen) == 1:
            await gate.wait()
        return "Dạ"

    tg = FakeTelegram()
    b = TelegramBot("TOKEN", "", answer, giau_trang_thai=True)
    await b._dispatch(tg, "5", "còn hàng không", {})
    await asyncio.sleep(0)
    await b._dispatch(tg, "5", "size M", {})
    check("customer bot: no acknowledgement, stays human", not any(t[:1] in ("↪", "📥") for t in tg.texts()))
    gate.set()
    await until_idle(b, "5")
    check("customer bot: no inbox, merged into the next turn as before", sids[0] == "" and seen == ["còn hàng không", "size M"])


async def two_bots():
    a = TelegramBot("A", "", None)
    b = TelegramBot("B", "", None)
    check("two bots with the same chat id use different inboxes", a._steer_sid("1") != b._steer_sid("1"))


async def claude_hook():
    import claude_sdk_engine as cse

    eng = cse.ClaudeSDK.__new__(cse.ClaudeSDK)
    eng.tag = "telegram:42"
    check("claude: a channel turn without an open inbox gets no hook", not eng._steer_on())
    sid = "kenh:test:42"
    tok = si.INBOX.open(sid)
    try:
        on = eng._steer_on()
        si.INBOX.put(sid, "dùng số liệu tháng 9")
        out = await eng._steer_hook({"hook_event_name": "PostToolUse"}, "t1", None)
    finally:
        si.INBOX.close(sid, token=tok)
    check("claude: a channel turn with an open inbox gets the hook", on)
    check("claude: the hook reads the channel inbox of this context",
          "số liệu tháng 9" in out.get("hookSpecificOutput", {}).get("additionalContext", ""))
    bg = cse.ClaudeSDK.__new__(cse.ClaudeSDK)
    bg.tag = "loop:bao-cao"
    tok = si.INBOX.open(sid)
    try:
        check("claude: a background fork never steers, even inside a turn context", not bg._steer_on())
    finally:
        si.INBOX.close(sid, token=tok)


async def main():
    await live_turn()
    await after_turn()
    await stop_drops()
    await customer_unchanged()
    await two_bots()
    await claude_hook()


asyncio.run(main())

src = (SERVER / "main.py").read_text(encoding="utf-8")
eng_start = src.index("async def _tg_answer_engine(")
eng_src = src[eng_start:src.index("\nasync def ", eng_start + 10)]
check("main: a channel turn hands read messages to its stored session",
      "steer_inbox.INBOX.set_sink(steer_inbox.current_sid()" in src)
check("main: one-shot engines and the fast path say after on channels (Codex only with its switch off)",
      eng_src.count("steer_inbox.INBOX.set_live(steer_inbox.current_sid(), False)") == 2
      and 'if prov in ("grok-cli", "antigravity-cli") or (prov == "openai-oauth" and not codex_steer.enabled()):'
      in eng_src)
gw = (SERVER / "bot_gateway.py").read_text(encoding="utf-8")
check("gateway: no long dashes", not any(c in gw for c in "–—"))

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
