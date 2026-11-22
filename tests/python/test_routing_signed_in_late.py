"""A card signed in after the usage order was saved is a real fallback (2026-11-22).

    python tests/run.py routing_signed_in_late     (no network, no real CLI)

Owner, 22/11/2026: Claude Code and ChatGPT were both signed out at the same time, Antigravity was signed in, "nhưng nó
đang không sử dụng dự phòng của Anti-Gravity để có thể trả lời khách hoặc là có thể làm tiếp các cái nhiệm vụ".

Cause: the Models page draws the usage order as the saved order plus every card signed in since, at the end
(`_routing_view`), but routing read the SAVED order only. An API key joins the saved order when it is added; a plan
card signed in later (Antigravity signs in from a terminal with `agy`, outside Javis) never did, so it was shown as
the last fallback and never tried.

Covered here:
  1. `_routing_order`: the saved order, then cards signed in since, as the page draws it;
  2. a chat or bot turn starts on Antigravity when MAIN and fallback 1 are known to be signed out (`_chat_provider`);
  3. a turn refused for a lost sign-in moves on to Antigravity (`_chat_next_route`);
  4. END TO END: a customer bot whose Claude Code prints a lost sign-in and whose ChatGPT refuses is answered by
     Antigravity in the same turn;
  5. background jobs (`aux_engine.swap`) reach Antigravity too;
  6. a team turn falls back to a card that can run, not to a signed-out MAIN.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-route-late-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import aux_engine  # noqa: E402
import main  # noqa: E402
import model_routing  # noqa: E402

_fails = []
CLAUDE, CHATGPT, AGY = "anthropic-cli", "openai-oauth", "antigravity-cli"
SHOT = ("Failed to authenticate: this login reached its time limit and cannot be renewed. Run claude auth login to "
        "sign in again, or use claude setup-token and set CLAUDE_CODE_OAUTH_TOKEN for unattended jobs")
LOST = ("Your access token could not be refreshed because your refresh token was already used. "
        "Please log out and sign in again.")


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
    for store in (main._PIN_LIMITED, main._SIGNED_OUT, main._SIGNED_OUT_TOLD):
        store.clear()


# The owner's machine as reported: the order was saved with Claude Code and ChatGPT; Antigravity signed in later.
M = {"order": [CLAUDE, CHATGPT], "main": {"provider": CLAUDE, "model": "opus"}, "routing_version": 1,
     "profiles": {CLAUDE: {"model": "opus", "reasoning": "off"}, CHATGPT: {"model": "gpt-5.6-luna", "reasoning": "off"}}}
CONNECTED = [CLAUDE, CHATGPT, AGY]


def _setup(mp, connected=None):
    mp.setattr(main.cfgmod, "read_settings", lambda: {"model": M})
    conn = list(connected or CONNECTED)
    mp.setattr(main, "_routing_connected_ids", lambda _s: list(conn))
    mp.setattr(main.inbox, "add", lambda text, **kw: {})
    return conn


def _order(mp):
    _setup(mp)
    check("CANARY: the saved order alone never had Antigravity", AGY not in model_routing.order(M))
    check("the order a turn walks ends with Antigravity, as on the Models page",
          main._routing_order(M, CONNECTED) == [CLAUDE, CHATGPT, AGY], str(main._routing_order(M, CONNECTED)))
    check("an unknown list of signed-in cards keeps the saved order", main._routing_order(M, None) == [CLAUDE, CHATGPT])
    check("an empty list keeps the saved order too", main._routing_order(M, []) == [CLAUDE, CHATGPT])


def _start(mp):
    _setup(mp)
    _reset()
    main._SIGNED_OUT[CLAUDE] = main.time.time() + 600
    main._SIGNED_OUT[CHATGPT] = main.time.time() + 600
    prov = main._chat_provider(M)[0]
    check("CANARY: MAIN and fallback 1 signed out -> the turn starts on Antigravity", prov == AGY, prov)
    main._SIGNED_OUT.pop(CHATGPT)
    check("ChatGPT still signed in -> it takes the turn first", main._chat_provider(M)[0] == CHATGPT)
    _reset()
    check("nothing signed out -> MAIN", main._chat_provider(M)[0] == CLAUDE)


def _next(mp):
    _setup(mp)
    _reset()
    main._SIGNED_OUT[CLAUDE] = main.time.time() + 600
    nxt = main._chat_next_route(M, CLAUDE, tried=[CHATGPT], reason="signin")
    check("CANARY: Claude and ChatGPT tried -> the turn moves to Antigravity",
          (nxt.get("route") or ("",))[0] == AGY, str(nxt))
    check("the status line names why", "Antigravity" in str(nxt.get("status")) or "antigravity" in str(nxt.get("status")).lower(),
          str(nxt.get("status")))
    _setup(mp, [CLAUDE, CHATGPT])
    check("Antigravity not signed in -> nothing is left", main._chat_next_route(M, CLAUDE, tried=[CHATGPT],
                                                                                reason="signin") == {})
    _reset()


def _bot_end_to_end(mp):
    _setup(mp)
    _reset()
    calls, lines = [], []

    async def engine(text, meta, progress, *, prov, **_kw):
        calls.append(prov)
        if prov == CLAUDE:
            return {"text": SHOT, "files": []}       # Claude Code prints its lost sign-in as the answer
        if prov == CHATGPT:
            return "⚠ " + LOST                       # ChatGPT refuses with an error
        return {"text": "Dạ shop còn hàng ạ.", "files": []}

    async def progress(s):
        lines.append(s)

    mp.setattr(main, "_tg_answer_engine", engine)
    mp.setattr(main, "_chat_provider_bot", lambda _m, _b: (CLAUDE, "cli", "", "opus"))
    mp.setattr(main, "_record_quality_shadow", lambda *a, **k: None)
    bot = {"id": "b1", "slug": "shop", "brain": "brain", "muc_quyen": "full", "agent": {"brain": "brain", "slug": "s"}}
    out = asyncio.run(main._tg_answer("Shop còn hàng không?", {"chat_id": "c9"}, progress, channel="telegram",
                                      bot=bot, ghi_kho=False))
    check("CANARY: Claude and ChatGPT both refuse -> Antigravity answers the customer",
          calls == [CLAUDE, CHATGPT, AGY] and isinstance(out, dict) and out.get("text") == "Dạ shop còn hàng ạ.",
          f"{calls} {out}")
    check("both plan cards are marked, so the next turns start on Antigravity",
          main._signed_out_until(CLAUDE) > 0 and main._signed_out_until(CHATGPT) > 0)
    check("the customer never sees a routing line", not any("↻" in str(s) for s in lines), str(lines))
    _reset()


def _background(mp):
    seen = []

    def fake_links(step, *_a, **_k):
        seen.append(step["provider"])
        return []

    mp.setattr(aux_engine, "_links_for_step", fake_links)
    mp.setattr(aux_engine, "CONNECTED_IDS", lambda _s: list(CONNECTED))
    base = object()
    aux_engine.swap(base, tag="kanban", settings={"model": M})
    check("CANARY: a background job's chain reaches Antigravity", AGY in seen, str(seen))
    check("after the saved cards", seen.index(AGY) > max(seen.index(p) for p in (CLAUDE, CHATGPT) if p in seen),
          str(seen))
    seen.clear()
    mp.setattr(aux_engine, "CONNECTED_IDS", None)
    aux_engine.swap(base, tag="kanban", settings={"model": M})
    check("with no signed-in list the chain is the saved order, as before", AGY not in seen, str(seen))


def _team(mp):
    s = {"model": M}
    _setup(mp)
    _reset()
    check("nothing signed out -> a team turn falls back to MAIN", main._team_main(s)["provider"] == CLAUDE)
    main._SIGNED_OUT[CLAUDE] = main.time.time() + 600
    check("CANARY: MAIN signed out -> a text-only team turn takes ChatGPT", main._team_main(s)["provider"] == CHATGPT)
    main._SIGNED_OUT[CHATGPT] = main.time.time() + 600
    check("CANARY: both signed out -> a team turn with tools takes Antigravity",
          main._team_main(s, tools=True)["provider"] == AGY)
    check("a text-only team turn never lands on Antigravity (it cannot run text-only)",
          main._team_main(s)["provider"] != AGY)
    _reset()


def main_test(mp):
    _order(mp)
    _start(mp)
    _next(mp)
    _bot_end_to_end(mp)
    _background(mp)
    _team(mp)


def test_routing_signed_in_late(monkeypatch):
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
