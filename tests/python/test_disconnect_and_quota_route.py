"""Disconnect for every Models card, and a chat that leaves an out-of-quota plan.

    python tests/run.py disconnect_and_quota_route     (no network, no real `agy`)

Owner, 05/11/2026, with a customer's screenshots:
1. "The Antigravity card has no Disconnect button." Its Google session lives in the OS keyring, so Disconnect now runs
   the CLI's own sign-out when the binary lists one, and switches the card off in Javis either way.
2. "Google ran out of quota and Javis keeps using it; switching to ChatGPT does not stick." Two causes:
   - `_LIMIT_ENGINE_PROVIDER` had no Antigravity entry, so an `agy` quota refusal marked nothing;
   - a quota mark on the card the owner had just chosen kept every turn away from it, with no way to lift it.
   And the error said "no other brain is connected" while ChatGPT was signed in.
"""
from _paths import ROOT, SERVER  # noqa: F401
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-disc-")

import config as cfgmod  # noqa: E402
import antigravity_cli  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def fake_agy(help_text: str) -> str:
    d = Path(tempfile.mkdtemp(prefix="javis-fakeagy-"))
    p = d / "agy"
    p.write_text("#!/usr/bin/env python3\nimport sys\n"
                 f"if '--help' in sys.argv:\n    sys.stdout.write({help_text!r}); sys.exit(0)\n"
                 f"open({str(d / 'ran.txt')!r}, 'w').write(' '.join(sys.argv[1:]))\n")
    p.chmod(0o755)
    return str(p)


def use_agy(path: str):
    os.environ["JAVIS_AGY_BIN"] = path
    antigravity_cli._HELP_CACHE.update(path=None, text="", ts=0.0)
    antigravity_cli.forget_status()


# ---- 1. sign-out is measured from --help, never guessed ----
with_logout = fake_agy("Usage: agy [command]\n\nCommands:\n  models    List models\n  logout    Sign out\n")
use_agy(with_logout)
argv = antigravity_cli.logout_argv()
check("a binary that lists `logout` gets it run", argv == [with_logout, "logout"], argv)
r = antigravity_cli.logout()
ran = (Path(with_logout).parent / "ran.txt")
check("the CLI's own sign-out ran", r.get("cli_logout") is True and ran.is_file() and ran.read_text() == "logout", r)

no_logout = fake_agy("Usage: agy [command]\n\nCommands:\n  models    List models\n  chat      Talk\n")
use_agy(no_logout)
check("a binary with no sign-out command gets nothing run", antigravity_cli.logout_argv() is None)
r = antigravity_cli.logout()
check("no sign-out: still ok, Javis switches the card off instead", r == {"ok": True, "cli_logout": False}, r)
check("`logged out` inside a description is not a command",
      (use_agy(fake_agy("Commands:\n  models   List models once you are logged out\n")) or True)
      and antigravity_cli.logout_argv() is None)

# ---- 2. switched off in Javis: every status read says so ----
cfgmod.update_settings({"model": {"antigravity_off": True}})
check("javis_off reads the flag", antigravity_cli.javis_off() is True)
st = antigravity_cli.auth_status(True)
check("auth_status: not connected, marked off, says how to undo",
      st.get("connected") is False and st.get("javis_off") is True and st.get("error"), st)
st2 = antigravity_cli.auth_status_nen()
check("the hot-path status says the same (no CLI run)", st2.get("javis_off") is True and st2.get("connected") is False)
view = next(p for p in main._providers_view(cfgmod.read_settings()) if p["id"] == "antigravity-cli")
check("the Models card is not connected and carries javis_off", view["configured"] is False and view["javis_off"] is True)
mcfg = cfgmod.read_settings()["model"]
route = main._chat_provider_for_session(mcfg, {"pinned_provider": "antigravity-cli", "pinned_model": ""})
check("a chat pinned to the disconnected card runs on the main model", route[0] != "antigravity-cli", route)
check("the chat model bar calls that pin unusable", main._pin_health(mcfg, "antigravity-cli")[0] is False)
cfgmod.update_settings({"model": {"antigravity_off": False}})
check("Connect again clears it", antigravity_cli.javis_off() is False)

# ---- 3. an Antigravity quota refusal marks the card, and the owner's choice lifts a mark ----
main._PIN_LIMITED.clear()
main._note_pin_limit("antigravity-cli", time.time() + 3600)
check("an agy quota refusal marks the card (it marked nothing before)", main._pin_limited_until("antigravity-cli") > 0)
check("marked card: the route skips it", main._route_ready(cfgmod.read_settings()["model"], "antigravity-cli") is False)
main._note_pin_limit("codex", time.time() + 9 * 86400)
check("a stale ChatGPT mark stands until someone lifts it", main._pin_limited_until("openai-oauth") > 0)
check("choosing the card lifts its mark", main._clear_pin_limit("openai-oauth") is True
      and main._pin_limited_until("openai-oauth") == 0)
check("lifting a card with no mark says so", main._clear_pin_limit("openai-oauth") is False)

view = main._routing_view(cfgmod.read_settings()["model"], [
    {"id": "antigravity-cli", "configured": True, "cli_found": True},
    {"id": "openai-oauth", "configured": True, "cli_found": True}])
check("the Models page learns which card rests and until when", "antigravity-cli" in view.get("limited", {})
      and "openai-oauth" not in view["limited"], view.get("limited"))
main._PIN_LIMITED.clear()

# ---- 4. the error names signed-in plan cards as a way out, never the plan that ran out ----
orig = main._routing_connected_ids
main._routing_connected_ids = lambda cfg: ["openai-oauth", "antigravity-cli"]
try:
    labels = main._fallback_brain_labels("antigravity-cli")
finally:
    main._routing_connected_ids = orig
check("ChatGPT is offered as the way out", any("ChatGPT" in x for x in labels), labels)
check("Antigravity is not offered as its own way out", not any("Antigravity" in x for x in labels), labels)

# ---- 5. wiring ----
src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("the disconnect and retry endpoints exist", '@app.post("/antigravity/logout")' in src
      and '@app.post("/antigravity/reconnect")' in src and '@app.post("/routing/retry")' in src)
check("pinning a chat, making a card MAIN and reordering lift the chosen card's mark",
      src.count("_clear_pin_limit(prov)") >= 2 and "_clear_pin_limit(ids[0])" in src)

print()
if fails:
    print(f"ĐỎ {len(fails)} mục")
    raise SystemExit(1)
print("Tất cả xanh.")
