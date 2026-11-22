"""A lost sign-in printed AS the answer never reaches a customer (2026-11-22).

    python tests/run.py bot_signin_answer     (no network, no real CLI, fake Telegram)

Owner's screenshot, 22/11/2026, a customer Telegram group with four members: the bot "Javis Vũ" quoted a member and
posted, as its reply:

    Failed to authenticate: this login reached its time limit and cannot be renewed. Run claude auth login to sign in
    again, or use claude setup-token and set CLAUDE_CODE_OAUTH_TOKEN for unattended jobs

Owner: "khi logout thì các tin báo hệ thống như thế này không được đi vào bot". Claude Code prints this sentence as the
ANSWER (a `final`), not as an error, so every guard that waits for an error string let it through, and the last gate
before the channel (`chatbot_runtime.engine_notice`) only knew "Not logged in" and "Please run /login".

Covered here:
  1. the strict detector `signin_loss.is_signin_answer`: every CLI's own wording, never a support bot's real advice;
  2. `chatbot_runtime.engine_notice`, the last gate before every channel, catches it;
  3. the bot's own turn (`main._bot_doc_stream`) takes it as the turn's error, and keeps it out of the chat history;
  4. a channel turn (`main._tg_answer`): a Full-access bot's answer is turned into the failed turn it is, the next
     connected model answers the customer, nothing is sent when no model can, and the owner reads a plain sentence;
  5. END TO END, as in the screenshot: a group message to a human-mode Telegram bot sends nothing to the group, and the
     owner's bell names the fix (sign in again on the Models page).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-bot-signin-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import main  # noqa: E402
import model_routing  # noqa: E402
import signin_loss  # noqa: E402
from telegram_bot import TelegramBot  # noqa: E402

_fails = []

# Exactly what the bot posted in the owner's screenshot.
SHOT = ("Failed to authenticate: this login reached its time limit and cannot be renewed. Run claude auth login to "
        "sign in again, or use claude setup-token and set CLAUDE_CODE_OAUTH_TOKEN for unattended jobs")
CLAUDE = "anthropic-cli"


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if not cond and extra else ""))
    if not cond:
        _fails.append(name)


class _Patch:
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, value):
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, old in reversed(self._undo):
            setattr(obj, name, old)


def _reset():
    model_routing.clear_rest(CLAUDE, "main")
    for store in (main._PIN_LIMITED, main._SIGNED_OUT, main._SIGNED_OUT_TOLD):
        store.clear()


# ============================================================
# 1. The strict detector
# ============================================================
def _detector():
    yes = signin_loss.is_signin_answer
    check("CANARY: the sentence in the screenshot is a sign-in failure", yes(SHOT))
    check("Claude Code's older sentences too",
          yes("Not logged in · Please run /login") and yes("Failed to authenticate: OAuth session expired and could "
                                                          "not be refreshed")
          and yes("OAuth token has expired. Please obtain a new token or refresh your existing token."))
    check("Codex's refusal printed as an answer",
          yes("Your access token could not be refreshed because your refresh token was already used. "
              "Please log out and sign in again."))
    check("with a leading warning sign or spaces", yes("  ⚠ " + SHOT))
    check("a support bot's real advice is still sent", not yes("Please log out and sign in again."))
    check("and in Vietnamese too", not yes("Dạ anh chị đăng xuất rồi sign in again giúp em nhé ạ."))
    check("an ordinary answer is left alone", not yes("Dạ bên em còn hàng, anh chị cần mấy cái ạ?"))
    check("a long answer that quotes the sentence is left alone",
          not yes("Dạ khi máy báo \"" + SHOT + "\" thì anh mở terminal gõ lệnh đăng nhập lại ạ. " + "Ngoài ra " * 40))
    check("an MCP server's 401 is not the plan's sign-in", not yes("MCP server zalo: 401 Unauthorized, run /login"))
    check("empty is nothing", not yes("") and not yes(None))


# ============================================================
# 2. The last gate before every channel
# ============================================================
def _gate():
    en = chatbot_runtime.engine_notice
    check("CANARY: engine_notice catches the screenshot's sentence", en(SHOT) == SHOT)
    check("engine_notice still catches the older ones",
          bool(en("Not logged in · Please run /login")) and bool(en("Invalid API key · Please run /login")))
    check("engine_notice catches 'API key not found' and an OAuth line",
          bool(en("API key not found")) and bool(en("OAuth token has expired.")))
    check("engine_notice leaves a real reply alone", not en("Dạ còn hàng ạ, anh chị lấy size nào?"))
    check("engine_notice leaves a support bot's advice alone", not en("Please log out and sign in again."))
    check("engine_notice leaves a tech bot's answer about OAuth alone",
          not en("OAuth token là mã truy cập tạm thời, anh chị không cần lo ạ."))


# ============================================================
# 3. The bot's own turn
# ============================================================
def _bot_stream():
    async def stream(text):
        yield {"type": "meta", "model": "sonnet"}
        yield {"type": "text", "content": text}

    async def progress(_s):
        pass

    async def run(text):
        return await main._bot_doc_stream(stream(text), progress=progress, runtime_trace=None, prov=CLAUDE,
                                          api_model="sonnet")

    out, loi = asyncio.run(run(SHOT))
    check("CANARY: the bot's turn has no answer when the CLI printed a lost sign-in", out == "", out)
    check("the sentence is the turn's error", bool(loi) and loi[0] == SHOT, str(loi))
    out, loi = asyncio.run(run("Dạ còn hàng ạ."))
    check("an ordinary answer stays the answer", out == "Dạ còn hàng ạ." and not loi, str((out, loi)))


# ============================================================
# 4. A channel turn
# ============================================================
def _channel_turns(mp):
    bot = {"id": "b1", "slug": "shop", "brain": "brain", "muc_quyen": "full",
           "agent": {"brain": "brain", "slug": "sales"}}
    f = main._tg_signin_answer
    check("a bot's dict answer that is the sentence becomes the failed turn", f({"text": SHOT, "files": []}, CLAUDE,
                                                                               bot=bot) == "⚠ " + SHOT)
    check("after a tool ran it is left alone", isinstance(f({"text": SHOT, "files": []}, CLAUDE, bot=bot, acted=True),
                                                           dict))
    check("an answer with files is left alone",
          isinstance(f({"text": SHOT, "files": ["/x.png"]}, CLAUDE, bot=bot), dict))
    check("a bot's real advice is left alone",
          isinstance(f({"text": "Please log out and sign in again.", "files": []}, CLAUDE, bot=bot), dict))
    check("the owner's turn is recognised too", f({"text": SHOT, "files": []}, CLAUDE) == "⚠ " + SHOT)
    check("an error string passes through", f("⚠ boom", CLAUDE, bot=bot) == "⚠ boom")

    m = {"order": [CLAUDE, "groq"], "main": {"provider": CLAUDE, "model": "sonnet"},
         "groq_api_key": "gsk_test", "profiles": {"groq": {"model": "llama-4", "reasoning": "off"}}}
    mp.setattr(main.cfgmod, "read_settings", lambda: {"model": m})
    connected = [CLAUDE, "groq"]
    mp.setattr(main, "_routing_connected_ids", lambda _s: list(connected))
    mp.setattr(main.inbox, "add", lambda text, **kw: {})
    mp.setattr(main, "_record_quality_shadow", lambda *a, **k: None)
    mp.setattr(main, "_chat_provider_bot", lambda _m, _b: (CLAUDE, "cli", "", "sonnet"))
    mp.setattr(main, "_chat_provider_kenh", lambda _m, _c, _k="": (CLAUDE, "cli", "", "sonnet"))

    async def quiet(*_a, **_k):
        return ""

    mp.setattr(main, "_canh_bao_hua_suong", quiet)
    calls, lines = [], []

    async def fake_engine(text, meta, progress, *, prov, **_kw):
        calls.append(prov)
        if prov == CLAUDE:
            # What `_tg_answer_engine`'s Claude Code branch returns: the CLI's sentence as the answer.
            return {"text": SHOT, "files": []}
        return {"text": "Dạ, shop còn hàng ạ.", "files": []}

    async def progress(s):
        lines.append(s)

    mp.setattr(main, "_tg_answer_engine", fake_engine)
    _reset()
    out = asyncio.run(main._tg_answer("Shop còn hàng không?", {"chat_id": "c1"}, progress, channel="telegram",
                                      bot=bot, ghi_kho=False))
    check("CANARY: a Full-access bot's turn moves to the next connected model", calls == [CLAUDE, "groq"], str(calls))
    check("the customer gets the real answer", isinstance(out, dict) and out.get("text") == "Dạ, shop còn hàng ạ.",
          str(out))
    check("the customer never sees the sentence or a routing line",
          SHOT not in str(out) and not any("↻" in str(s) for s in lines), str(lines))
    check("Claude Code is marked signed out, so the next turns start elsewhere", main._signed_out_until(CLAUDE) > 0)

    # No other model: the turn fails, and a failed turn is what the bot layer keeps away from the customer.
    _reset()
    calls.clear()
    connected[:] = [CLAUDE]
    out = asyncio.run(main._tg_answer("Shop còn hàng không?", {"chat_id": "c2"}, progress, channel="telegram",
                                      bot=bot, ghi_kho=False))
    check("CANARY: no other model -> the bot's turn is a failed turn, not an answer", isinstance(out, str), str(out))

    # The owner's own channel: a plain sentence naming the fix, not the CLI's advice about a terminal.
    _reset()
    out = asyncio.run(main._tg_answer("Doanh thu hôm nay?", {"chat_id": "owner1"}, progress, channel="telegram",
                                      ghi_kho=False))
    check("owner channel: told the sign-in was lost and where to sign in again",
          isinstance(out, str) and "Models" in out and ("mất đăng nhập" in out or "lost its sign-in" in out), str(out))
    _reset()


# ============================================================
# 5. End to end, as in the screenshot
# ============================================================
class _Resp:
    status_code = 200
    text = ""

    def __init__(self, data=None):
        self._d = data if data is not None else {"ok": True, "result": {"message_id": 7}}

    def json(self):
        return self._d


class _FakeTelegram:
    def __init__(self):
        self.calls = []

    async def post(self, url, json=None, **kw):
        self.calls.append((url.rsplit("/", 1)[-1], json or {}))
        return _Resp()

    def sent(self):
        return [j.get("text", "").replace("\\", "") for m, j in self.calls if m == "sendMessage"]


def _end_to_end():
    bell = []

    async def engine(text, meta, progress, *, channel="", bot=None, **_kw):
        # The Claude Code branch before this fix: the sentence came back as the answer.
        return {"text": SHOT, "files": []}

    brain = tempfile.mkdtemp(prefix="brain-")
    chatbot_runtime.wire(answer=engine, brain_root=lambda b: brain,
                         read_agent=lambda b, slug: ({"name": "Vũ", "role": "Trợ lý"}, "Ngắn gọn."),
                         notify=lambda text: bell.append(text))
    bid, err = chatbot_store.create_bot({"name": "Javis Vũ", "agent_slug": "vu", "brain": "b", "token": "1:x",
                                         "channel": "telegram"})
    check("a test bot is made", bool(bid) and not err, err)
    tg = _FakeTelegram()
    tb = TelegramBot("TOKEN", "", chatbot_runtime._make_answer_fn(bid), giau_trang_thai=True)
    meta = {"chat_id": "-100777", "chat_type": "private", "user_name": "Hà My", "user_id": "55",
            "message_id": 901, "platform": "telegram"}
    asyncio.run(tb._handle_turn(tg, "-100777", "Lãi hôm nay tới 10h15 khoảng 4,71tr", meta))
    check("CANARY: nothing at all is sent to the chat", not tg.sent(), str(tg.sent()))
    check("the owner's bell rings once for the failed turn", len(bell) == 1, str(bell))
    check("the bell names the fix: sign in again on the Models page",
          bool(bell) and "Models" in bell[0] and SHOT[:40] in bell[0], str(bell))


def main_test(mp):
    _detector()
    _gate()
    _bot_stream()
    _channel_turns(mp)
    _end_to_end()


def test_bot_signin_answer(monkeypatch):
    main_test(monkeypatch)
    assert not _fails, _fails


if __name__ == "__main__":
    _mp = _Patch()
    try:
        main_test(_mp)
    finally:
        _mp.undo()
    print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
    sys.exit(1 if _fails else 0)
