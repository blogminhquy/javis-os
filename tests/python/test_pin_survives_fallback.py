"""A temporary fallback never replaces a chat's pinned model (issue 1336).

    python tests/run.py pin_survives_fallback     (no network)

While the card a chat is pinned to rests (its plan is out of quota or signed out), the turn runs on the main model.
The stamp that anchors every dashboard chat on its model then wrote that fallback into the chat as its new pin, so
once the quota came back the chat stayed on the fallback model. Stamping is still right for a new chat and for a
broken pin (card gone, key removed, card disconnected); it is never right for a card that only rests.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-pinfb-")

from sessions import SessionStore  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        _fails.append(name)


# Every card counts as signed in, so a fallback can land on the next card of the usage order.
main._routing_connected_ids = lambda cfg: ["anthropic-cli", "openai-oauth", "groq", "openrouter"]

GROQ_MAIN = {"main": {"provider": "groq", "model": "qwen3-32b"}, "groq_api_key": "gsk_test",
             "order": ["groq", "anthropic-cli"]}
CLAUDE_MAIN = {"main": {"provider": "anthropic-cli", "model": "opus"}, "groq_api_key": "gsk_test",
               "order": ["anthropic-cli", "groq"], "profiles": {"groq": {"model": "qwen3-32b"}}}
OPENROUTER_MAIN = {"main": {"provider": "openrouter", "model": "x/y"}, "groq_api_key": "gsk_test",
                   "order": ["openrouter", "groq"], "profiles": {"groq": {"model": "qwen3-32b"}}}
PIN_CLAUDE = {"pinned_provider": "anthropic-cli", "pinned_model": "opus"}
PIN_BROKEN = {"pinned_provider": "openrouter", "pinned_model": "x/y"}     # no OpenRouter key: broken


def reset():
    main._PIN_LIMITED.clear()
    main._SIGNED_OUT.clear()


def stamp(mcfg, row):
    r = main._chat_provider_for_session(mcfg, row)
    return r, main._pin_to_stamp(mcfg, row, r[0], r[3])


# ---- 1. The reported case: a pinned plan out of quota ----
reset()
main._PIN_LIMITED["anthropic-cli"] = time.time() + 3600
route, st = stamp(GROQ_MAIN, PIN_CLAUDE)
check("pinned card out of quota: the turn runs on the main model", route[0] == "groq", route)
check("pinned card out of quota: the pin is NOT replaced by the fallback", st is None, st)

reset()
main._SIGNED_OUT["anthropic-cli"] = time.time() + 3600
route, st = stamp(GROQ_MAIN, PIN_CLAUDE)
check("pinned card signed out: the turn runs on the main model", route[0] == "groq", route)
check("pinned card signed out: the pin stays", st is None, st)

reset()
route, st = stamp(GROQ_MAIN, PIN_CLAUDE)
check("healthy pin: the turn runs on the pin and nothing is written", route[0] == "anthropic-cli" and st is None,
      (route, st))

# ---- 2. Stamping still works where it is meant to ----
reset()
route, st = stamp(GROQ_MAIN, {})
check("new chat: stamped with the model it runs on", st == ("groq", "qwen3-32b"), st)

route, st = stamp(GROQ_MAIN, PIN_BROKEN)
check("broken pin (key removed): replaced by the main model that really runs", st == ("groq", "qwen3-32b"), st)

route, st = stamp(GROQ_MAIN, {"pinned_provider": "no-such-provider", "pinned_model": "m"})
check("broken pin (provider gone): replaced by the main model", st == ("groq", "qwen3-32b"), st)

route, st = stamp(dict(GROQ_MAIN, openrouter_key="sk-or", openrouter_model="a/b"),
                  {"pinned_provider": "openrouter", "pinned_model": ""})
check("pin on the right card, model filled in: stamped as before", st == ("openrouter", "a/b"), (route, st))

route, st = stamp(OPENROUTER_MAIN, {})
check("main card broken too: the card that runs is stamped (nothing else to anchor on)",
      route[0] == "groq" and st == ("groq", "qwen3-32b"), (route, st))

# ---- 3. The main model itself rests: a new chat is not anchored on the fallback ----
reset()
main._PIN_LIMITED["anthropic-cli"] = time.time() + 3600
route, st = stamp(CLAUDE_MAIN, {})
check("main card out of quota: a new chat runs on the next card", route[0] == "groq", route)
check("main card out of quota: a new chat is NOT stamped with the fallback", st is None, st)
route, st = stamp(CLAUDE_MAIN, PIN_BROKEN)
check("broken pin while the main card rests: the fallback is not stamped either", route[0] == "groq" and st is None,
      (route, st))

# ---- 4. End to end in the session store: the chat goes back once the quota resets ----
with tempfile.TemporaryDirectory() as td:
    store = SessionStore(db_path=Path(td) / "conv.db")
    sid = store.create_session(brain="brain-a")
    store.set_pinned_model(sid, "anthropic-cli", "opus")

    def turn(mcfg):
        row = store.get_session(sid) or {}
        route, st = stamp(mcfg, row)
        if st:
            store.set_pinned_model(sid, *st)
        return route

    reset()
    main._PIN_LIMITED["anthropic-cli"] = time.time() + 3600
    r1 = turn(GROQ_MAIN)
    r2 = turn(GROQ_MAIN)
    row = store.get_session(sid)
    check("two turns during the rest run on the fallback", r1[0] == r2[0] == "groq", (r1, r2))
    check("the stored pin is still the owner's choice", (row["pinned_provider"], row["pinned_model"])
          == ("anthropic-cli", "opus"), row)
    reset()   # the quota came back
    r3 = turn(GROQ_MAIN)
    check("after the reset the chat is back on its pinned model", r3[0] == "anthropic-cli" and r3[3] == "opus", r3)

    sid2 = store.create_session(brain="brain-a")
    main._PIN_LIMITED["anthropic-cli"] = time.time() + 3600

    def turn2(mcfg):
        row = store.get_session(sid2) or {}
        route, st = stamp(mcfg, row)
        if st:
            store.set_pinned_model(sid2, *st)
        return route

    turn2(CLAUDE_MAIN)
    check("new chat during the main card's rest stays unpinned", not store.get_session(sid2).get("pinned_provider"))
    reset()
    r = turn2(CLAUDE_MAIN)
    row = store.get_session(sid2)
    check("first turn back on the main card stamps the main model",
          r[0] == "anthropic-cli" and (row["pinned_provider"], row["pinned_model"]) == ("anthropic-cli", "opus"), row)

# ---- 5. Wiring ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
ws = src[src.index("async def websocket_endpoint("):]
check("the dashboard stamp goes through _pin_to_stamp",
      "_stamp = _pin_to_stamp(mcfg, _prow, prov, api_model)" in ws and "store.set_pinned_model(conv_sid, *_stamp)" in ws)
j = ws.index('_set_main_model(_fix, "openai-oauth", actual_model)')
check("Codex self-heal fixes the chat's pin only when that pin is ChatGPT",
      '(_row0.get("pinned_provider") or "").strip() == "openai-oauth"' in ws[j - 1200:j], ws[j - 1200:j])
check("Codex self-heal writes the main model only when ChatGPT IS the main model, else only its own card",
      '_effective_main(_fix)["provider"] == "openai-oauth"' in ws[j - 200:j]
      and 'model_routing.set_profile(_fix.setdefault("model", {}), "openai-oauth", model=actual_model)' in ws[j:j + 400])
for f in (SERVER / "main.py", Path(__file__)):
    txt = f.read_text(encoding="utf-8")
    new = txt[txt.find("def _card_broken("):txt.find("def _route_rest_until(")] if f.name == "main.py" else txt
    check(f"no em or en dash in the new code ({f.name})", chr(0x2014) not in new and chr(0x2013) not in new)

reset()
print()
if _fails:
    print(f"FAIL - test_pin_survives_fallback: {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_pin_survives_fallback: all pass")
