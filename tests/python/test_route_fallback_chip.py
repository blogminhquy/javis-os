"""The chat shows which model REALLY answers when Javis falls back (owner, 05/11/2026).

    python tests/run.py route_fallback_chip      (no network, no real CLI)

A customer's report: Antigravity ran out of quota, Javis moved to ChatGPT, then to Claude Code, and the model chip under
the chat still said "Gemini 3.8 Flash" with a green dot. The server now says, for a chat, what the owner chose and
where the turn really runs (`_route_view`): in `/sessions/{id}/meta`, in `/chat/route` for an empty chat, and in a
"route" frame at the start of every turn. Nothing saved changes, so the chosen model comes back once its quota does.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-routechip-")

import config as cfgmod  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def mcfg_three():
    """Usage order Antigravity (MAIN) -> ChatGPT -> Claude Code, all three plans signed in."""
    return {"order": ["antigravity-cli", "openai-oauth", "anthropic-cli"],
            "main": {"provider": "antigravity-cli", "model": "gemini-3.8-flash"},
            "profiles": {"antigravity-cli": {"model": "gemini-3.8-flash", "reasoning": "off"},
                         "openai-oauth": {"model": "gpt-5.5", "reasoning": "off"},
                         "anthropic-cli": {"model": "opus", "reasoning": "off"}}}


orig_connected = main._routing_connected_ids
main._routing_connected_ids = lambda _s: ["antigravity-cli", "openai-oauth", "anthropic-cli"]
main._PIN_LIMITED.clear()
try:
    m = mcfg_three()
    # ---- 1. nothing out of quota: the chosen model runs, no fallback ----
    v = main._route_view(m, {})
    check("all fine: runs on the chosen card", v["provider"] == "antigravity-cli" and v["fallback"] is False, v)
    check("all fine: the chosen model is MAIN", v["selected_provider"] == "antigravity-cli"
          and v["selected_model"] == "gemini-3.8-flash")
    check("all fine: no card resting, no notice", v["limited"] == {} and "content" not in v, v)

    # ---- 2. the customer's case: Antigravity, then ChatGPT out of quota -> Claude Code answers ----
    now = time.time()
    main._PIN_LIMITED["antigravity-cli"] = now + 3600
    main._PIN_LIMITED["openai-oauth"] = now + 600
    v = main._route_view(m, {})
    check("both out: Claude Code runs", v["provider"] == "anthropic-cli" and v["model"] == "opus", v)
    check("both out: marked as a fallback for quota, with the reset time",
          v["fallback"] is True and v["reason"] == "quota" and abs(v["until"] - (now + 3600)) < 2, v)
    check("both out: the chosen model is still Antigravity's", v["selected_provider"] == "antigravity-cli"
          and v["selected_model"] == "gemini-3.8-flash")
    check("both out: every resting card is listed", set(v["limited"]) == {"antigravity-cli", "openai-oauth"}, v["limited"])
    c = v.get("content") or ""
    check("the notice says who ran out and who answers", "Antigravity" in c and "Claude Code" in c, c)
    check("the notice has no long dash", "—" not in c and "–" not in c, c)
    check("names for the chip", v["name"] == "Claude Code" and v["selected_name"] == "Antigravity", v)

    # ---- 3. a chat pinned to ChatGPT: its own pin is the choice ----
    row = {"pinned_provider": "openai-oauth", "pinned_model": "gpt-5.5"}
    v = main._route_view(m, row)
    check("pinned chat: the pin is what was chosen", v["selected_provider"] == "openai-oauth"
          and v["selected_model"] == "gpt-5.5", v)
    check("pinned chat out of quota: a fallback card runs, flagged", v["fallback"] is True
          and v["provider"] == "anthropic-cli" and v["reason"] == "quota", v)

    # ---- 4. a turn already routed (run_turn rerouted it): the view follows that route ----
    v = main._route_view(m, {}, ("openai-oauth", "oauth", "", "gpt-5.5"))
    check("given route: reported as is", v["provider"] == "openai-oauth" and v["model"] == "gpt-5.5" and v["fallback"])

    # ---- 5. quota back: the chosen model runs again by itself, nothing saved changed ----
    main._PIN_LIMITED.clear()
    v = main._route_view(m, {})
    check("quota back: on the chosen card again, no fallback", v["provider"] == "antigravity-cli"
          and v["fallback"] is False and v["limited"] == {}, v)
    check("nothing saved changed", m == mcfg_three())

    # ---- 6. a chosen card that cannot run for another reason ----
    main._PIN_LIMITED.clear()
    v = main._route_view(m, {"pinned_provider": "groq", "pinned_model": "llama-4"})
    check("pin on a card with no key: fallback flagged as unavailable, not quota",
          v["fallback"] is True and v["reason"] == "unavailable" and v["until"] == 0, v)

    # ---- 7. the endpoints ----
    cfgmod.update_settings({"model": mcfg_three()})
    main._PIN_LIMITED["antigravity-cli"] = time.time() + 3600
    main._PIN_LIMITED["openai-oauth"] = time.time() + 3600
    d = asyncio.run(main.chat_route())
    check("/chat/route: an empty chat learns where its first turn runs",
          d.get("provider") == "anthropic-cli" and d.get("fallback") is True, d)
    main.get_store().get_or_create("phien-route", brain="brain", engine="cli", model=None)
    meta = main._sessions_meta_sync("phien-route")
    r = meta.get("route") if isinstance(meta, dict) else None
    check("/sessions/{id}/meta carries the route", bool(r) and r.get("provider") == "anthropic-cli"
          and r.get("fallback") is True, meta if not isinstance(meta, dict) else r)
    main._PIN_LIMITED.clear()
finally:
    main._routing_connected_ids = orig_connected
    main._PIN_LIMITED.clear()

# ---- 8. wiring ----
src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
dt = src[src.index("        async def _do_turn("):src.index("        async def run_turn(")]
i_route = dt.find('"type": "route"')
check("every turn sends a route frame", i_route > 0 and "_route_view(mcfg, _row0, (prov, kind, api_key, api_model))" in dt)
check("the route frame goes before the first status line", 0 < i_route < dt.find('"type": "status"'))
check("a rerouted turn says so in its frame", '"rerouted": bool(_route)' in dt)
check("the endpoint for an empty chat exists", '@app.get("/chat/route")' in src)

print()
if fails:
    print(f"ĐỎ {len(fails)} mục")
    raise SystemExit(1)
print("Tất cả xanh.")
