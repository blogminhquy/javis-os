"""Claude Code on a long-lived token from `claude setup-token` (2026-11-22).

    python tests/run.py claude_long_token     (no network; a fake `claude` plays setup-token in a pseudo-terminal)

Owner's report that day: Claude Code's sign-in "reached its time limit and cannot be renewed" and every bot and job
stopped. A one-year token made by `claude setup-token` and handed to the CLI as CLAUDE_CODE_OAUTH_TOKEN is Anthropic's
own answer for unattended runs. The Models card now has a third "Runs on" choice: the long-lived token, got with one
button (Javis runs the command: link, then the code the page shows) or pasted.

Covered here:
  1. claude_auth: the `token` mode, the env every `claude` gets, the token's check and its year;
  2. the token is a secret: encrypted on disk, never in /settings;
  3. saving, removing, and Disconnect on the card (which also forgets it);
  4. an extra Claude account never runs on account 1's token;
  5. `claude auth status` is asked with the token, and the engine light counts it (red once it expired);
  6. claude_setup_token against a fake `claude`: the link, the code, the token caught even when wrapped, a refused code.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-long-token-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import claude_auth  # noqa: E402
import claude_setup_token  # noqa: E402
import config as cfgmod  # noqa: E402

# 2026-11-26: a connector-capable login on this machine would run first (claude_auth.login_first); these tests are
# about the token alone, so they see no login file.
claude_auth.login_file = lambda: Path(tempfile.mkdtemp(prefix="javis-no-login-")) / ".credentials.json"

_fails = []
TOK = "sk-ant-oat01-" + "Ab3_x-" * 15 + "Q9zK"


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if not cond and extra else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. claude_auth
# ============================================================
def _s(**m):
    return {"model": dict(m)}


check("CANARY: token mode hands the token to `claude` as CLAUDE_CODE_OAUTH_TOKEN",
      claude_auth.env_cho_cli(_s(claude_auth="token", claude_oauth_token=TOK)) == {"CLAUDE_CODE_OAUTH_TOKEN": TOK})
check("token mode with no token falls back to the machine's own sign-in",
      claude_auth.env_cho_cli(_s(claude_auth="token")) == {})
check("the signed-in plan passes nothing, even with a token saved",
      claude_auth.env_cho_cli(_s(claude_auth="subscription", claude_oauth_token=TOK)) == {})
check("API key mode still passes the key", claude_auth.env_cho_cli(
    _s(claude_auth="api_key", anthropic_api_key="sk-ant-api03-x")) == {"ANTHROPIC_API_KEY": "sk-ant-api03-x"})
check("an unknown mode is the signed-in plan", claude_auth.che_do(_s(claude_auth="weird")) == "subscription")
check("a token runs the plan (on_plan), an API key does not",
      claude_auth.on_plan(_s(claude_auth="token", claude_oauth_token=TOK))
      and not claude_auth.on_plan(_s(claude_auth="api_key", anthropic_api_key="k")))
check("a setup-token is recognised, pasted with stray spaces and a line break",
      claude_auth.valid_token("  " + TOK[:40] + "\n" + TOK[40:] + " "))
check("an API key or a login code is not a token",
      not claude_auth.valid_token("sk-ant-api03-" + "a" * 40) and not claude_auth.valid_token("abc#def")
      and not claude_auth.valid_token("sk-ant-oat01-short"))
now = time.time()
info = claude_auth.token_info(_s(claude_oauth_token=TOK, claude_oauth_token_at=now - 10 * 86400), now=now)
check("the token's year counts from the day it was saved",
      info.get("set") and info.get("tail") == "Q9zK" and info.get("days_left") == 355 and not info.get("expired"), info)
check("never the token itself in what the card reads", TOK not in json.dumps(info))
old = claude_auth.token_info(_s(claude_oauth_token=TOK, claude_oauth_token_at=now - 366 * 86400), now=now)
check("a token past its year is expired", old.get("expired") is True, old)

# ============================================================
# 2-3. secret on disk, /settings, save/remove/disconnect
# ============================================================
import main  # noqa: E402

cfg = cfgmod.read_settings()
cfg["model"]["claude_oauth_token"] = TOK
cfgmod.write_settings(cfg)
raw = Path(cfgmod.SETTINGS_PATH if hasattr(cfgmod, "SETTINGS_PATH") else Path(cfgmod.STATE_DIR) / "settings.json")
on_disk = raw.read_text(encoding="utf-8") if raw.exists() else ""
check("CANARY: the token is encrypted on disk", bool(on_disk) and TOK not in on_disk, str(raw))
check("and reads back as is", cfgmod.read_settings()["model"]["claude_oauth_token"] == TOK)
view = main.settings_get()
check("CANARY: /settings never carries the token", TOK not in json.dumps(view, ensure_ascii=False))
claude = next(p for p in view["model"]["providers"] if p["id"] == "anthropic-cli")
check("the Claude card gets its dates and last 4 characters", (claude.get("auth_token") or {}).get("tail") == "Q9zK",
      claude.get("auth_token"))
cfg = cfgmod.read_settings()
cfg["model"]["claude_oauth_token"] = ""
cfgmod.write_settings(cfg)

calls = []
_REAL_PROBE, _REAL_RECONNECTED = main.connect_health.probe_engines, main.connect_health.engine_reconnected
main.warm_pool.POOL.drop_kind = lambda kind: calls.append(("drop", kind))
main.connect_health.engine_reconnected = lambda name: calls.append(("reconnected", name))
main.connect_health.probe_engines = lambda: calls.append(("probe",))
main._SIGNED_OUT["anthropic-cli"] = time.time() + 600

bad = main._claude_token_save("sk-ant-api03-" + "a" * 40)
check("an API key pasted as a token is refused with a sentence", bad.get("ok") is False and "sk-ant-oat01-" in bad["error"])
ok = main._claude_token_save(" " + TOK + "\n")
m = cfgmod.read_settings()["model"]
check("CANARY: saving switches Claude Code to the token", ok.get("ok") and m["claude_auth"] == "token"
      and m["claude_oauth_token"] == TOK and m["claude_oauth_token_at"] > 0, ok)
check("the answer names the token without showing it", TOK not in json.dumps(ok) and ok["token"]["tail"] == "Q9zK")
check("warm `claude` processes are dropped and the light goes green",
      ("drop", "claude") in calls and ("reconnected", "claude") in calls, calls)
check("the signed-out mark of the card is lifted at once", not main._signed_out_until("anthropic-cli"))
check("every `claude` now runs on it", claude_auth.env_cho_cli() == {"CLAUDE_CODE_OAUTH_TOKEN": TOK})

r = main.claude_token_remove()
m = cfgmod.read_settings()["model"]
check("removing forgets it and goes back to the signed-in plan",
      r.get("removed") is True and not m["claude_oauth_token"] and m["claude_auth"] == "subscription", (r, m["claude_auth"]))

main._claude_token_save(TOK)
main.claude_auth_logout = lambda: {"ok": True}
main.claude_logout()
m = cfgmod.read_settings()["model"]
check("CANARY: Disconnect on the card also forgets the token", not m["claude_oauth_token"]
      and m["claude_auth"] == "subscription")

# ============================================================
# 4. an extra account never uses account 1's token
# ============================================================
import plan_accounts  # noqa: E402


class _Eng:
    def _options(self):
        return SimpleNamespace(env={"PATH": "/bin", "CLAUDE_CODE_OAUTH_TOKEN": TOK})


extra = _Eng()
plan_accounts._claude_use(extra, "/tmp/acc2")
env = extra._options().env
check("CANARY: an extra account runs on its own folder, without account 1's token",
      env.get("CLAUDE_CONFIG_DIR") == "/tmp/acc2" and "CLAUDE_CODE_OAUTH_TOKEN" not in env, env)
main_acc = _Eng()
plan_accounts._claude_use(main_acc, None)
check("account 1 keeps it", main_acc._options().env.get("CLAUDE_CODE_OAUTH_TOKEN") == TOK)

# ============================================================
# 5. `claude auth status` and the engine light
# ============================================================
import claude_cli  # noqa: E402
import connect_health  # noqa: E402

connect_health.probe_engines, connect_health.engine_reconnected = _REAL_PROBE, _REAL_RECONNECTED

seen = {}
_real_run = claude_cli.subprocess.run


def _fake_run(args, **kw):
    seen["env"] = kw.get("env")
    return SimpleNamespace(stdout=json.dumps({"loggedIn": True, "authMethod": "oauth_token"}), returncode=0)


claude_cli.find_claude_cli = lambda: "/usr/bin/claude"
claude_cli.subprocess.run = _fake_run
cfg = cfgmod.read_settings()
cfg["model"].update(claude_auth="token", claude_oauth_token=TOK, claude_oauth_token_at=int(time.time()))
cfgmod.write_settings(cfg)
claude_cli.auth_quen_cache()
st = claude_cli.auth_status(bo_qua_cache=True)
claude_cli.subprocess.run = _real_run
check("CANARY: `claude auth status` is asked with the token", (seen.get("env") or {}).get("CLAUDE_CODE_OAUTH_TOKEN") == TOK)
check("and a token is a sign-in method, not a plan name", st.get("connected") and st.get("plan") == ""
      and st.get("auth_method") == "oauth_token", st)

connect_health.engines_in_use = lambda: {"claude"}
connect_health.probe_claude_credentials = lambda path=None: (False, "Chưa đăng nhập Claude Code trên máy này.")
connect_health.on_engine_down = None
connect_health._engines.clear()
connect_health.probe_engines()
check("CANARY: the light is green on a token, whatever the login file says",
      (connect_health._engines.get("claude") or {}).get("ok") is True, connect_health._engines.get("claude"))
cfg = cfgmod.read_settings()
cfg["model"]["claude_oauth_token_at"] = int(time.time()) - 400 * 86400
cfgmod.write_settings(cfg)
connect_health._engines.clear()
connect_health.probe_engines()
rec = connect_health._engines.get("claude") or {}
check("an expired token turns it red with a sentence", rec.get("ok") is False and "hết hạn" in rec.get("message", ""), rec)

# Owner 22/11/2026: no countdown on the card; a week before the year is up the bell says what to do.
told = []
connect_health.on_claude_token_soon = lambda info: told.append(info)
cfg = cfgmod.read_settings()
cfg["model"]["claude_oauth_token_at"] = int(time.time()) - 300 * 86400
cfgmod.write_settings(cfg)
connect_health._engines.clear()
connect_health.probe_engines()
check("months before the end: no reminder", told == [])
cfg["model"]["claude_oauth_token_at"] = int(time.time()) - 360 * 86400
cfgmod.write_settings(cfg)
connect_health.probe_engines()
check("CANARY: a week before the end the owner is reminded, and the light stays green",
      len(told) == 1 and told[0].get("days_left", 99) <= 7
      and (connect_health._engines.get("claude") or {}).get("ok") is True, told)
bell = []
main.inbox.add = lambda text, **kw: bell.append((text, kw))
main._claude_token_soon(told[0] if told else {"expires_at": int(time.time()) + 5 * 86400})
check("the reminder is one bell notice a day naming the step", len(bell) == 1
      and bell[0][1].get("dedup", "").startswith("claude-token-soon:") and "Models" in bell[0][0], bell)

# ============================================================
# 6. claude_setup_token against a fake `claude`
# ============================================================
FAKE = r'''#!/usr/bin/env python3
import os, sys, time
mode = os.environ.get("FAKE_MODE", "ok")
if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
    print("token leaked into setup-token"); sys.exit(3)
url = "https://claude.ai/oauth/authorize?ABCdef123"
sys.stdout.write("\x1b[2J\x1b[HWelcome to Claude Code\r\n Opening browser to sign in...\r\n")
sys.stdout.write("Browser didn't open? Use the url below to sign in\r\n")
sys.stdout.write("\x1b]8;;" + url + "\x07" + url[:30] + "\x1b]8;;\x07\r\n Paste code here if prompted > ")
sys.stdout.flush()
code = sys.stdin.readline().strip()
if mode == "bad" or code != "good#state":
    sys.stdout.write("\r\n\x1b[31m✘ OAuth error: That code wasn't accepted. Press Enter to retry\x1b[0m\r\n")
    sys.stdout.flush(); time.sleep(30); sys.exit(1)
tok = "sk-ant-oat01-" + "Zy9_q-" * 15 + "W1nE"
half = len(tok) // 2
sys.stdout.write("\r\n✓ Long-lived authentication token created successfully!\r\n\r\nYour OAuth token (valid for 1 year):\r\n\r\n")
sys.stdout.write(("\x1b[1m" + tok[:half] + "\r\n" + tok[half:] + "\x1b[0m") if mode == "wrap" else tok)
sys.stdout.write("\r\n\r\nStore this token securely.\r\n")
sys.stdout.flush(); time.sleep(0.3)
'''
FTOK = "sk-ant-oat01-" + "Zy9_q-" * 15 + "W1nE"
fake = Path(tempfile.mkdtemp(prefix="fake-claude-")) / "claude"
fake.write_text(FAKE, encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

if not claude_setup_token.supported():
    print("skip setup-token checks: no pseudo-terminal on this machine")
else:
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-server-wide"   # must never reach the command
    r = claude_setup_token.start(str(fake))
    check("CANARY: the sign-in link comes back, whole, from the terminal hyperlink",
          r.get("ok") and r.get("url") == "https://claude.ai/oauth/authorize?ABCdef123", r)
    check("waiting for the code", claude_setup_token.poll() == {"waiting": True})
    r = claude_setup_token.send_code("  good#state \n")
    check("CANARY: the pasted code is typed in and the printed token is caught", r.get("ok") and r.get("token") == FTOK, r)
    check("take_token hands it over once and forgets it",
          claude_setup_token.take_token() == FTOK and claude_setup_token.poll() == {"waiting": False})

    os.environ["FAKE_MODE"] = "wrap"
    claude_setup_token.start(str(fake))
    r = claude_setup_token.send_code("good#state")
    check("a token wrapped over two lines is still caught whole", r.get("token") == FTOK, r)
    claude_setup_token.stop()

    os.environ["FAKE_MODE"] = "bad"
    claude_setup_token.start(str(fake))
    r = claude_setup_token.send_code("wrong")
    check("a refused code says so, without the terminal's 'Press Enter' and its symbol",
          r.get("ok") is False and "wasn't accepted" in r.get("error", "") and "Press Enter" not in r["error"]
          and "✘" not in r["error"], r)
    claude_setup_token.stop()
    os.environ.pop("FAKE_MODE", None)
    os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)

    check("a code before any start is refused politely", claude_setup_token.send_code("x").get("ok") is False)

    # The endpoint: the code goes in, the token is saved and Claude Code switches to it.
    claude_setup_token.start(str(fake))
    d = main.claude_token_code("good#state")
    m = cfgmod.read_settings()["model"]
    check("CANARY: the card's code saves the token and switches Claude Code to it",
          d.get("ok") and m["claude_oauth_token"] == FTOK and m["claude_auth"] == "token"
          and FTOK not in json.dumps(d), d)

half = FTOK[:40]
check("CANARY: half a token at the end of a piece of output is never taken",
      claude_setup_token.find_token("Your token:\r\n" + half) == ""
      and claude_setup_token.find_token("Your token:\r\n" + FTOK + "\r\n") == ""
      and claude_setup_token.find_token("Your token:\r\n" + FTOK + "\r\n\r\n") == FTOK
      and claude_setup_token.find_token("Your token:\r\r\n" + half + "\r\r\n" + FTOK[40:] + "\r\r\n\r\r\n") == FTOK)
check("a line after the token that is a sentence is not glued on",
      claude_setup_token.find_token(FTOK + "\r\nStore this token securely.\r\n") == FTOK)
check("the last line counts once the command has exited", claude_setup_token.find_token(FTOK, final=True) == FTOK)
check("the terminal helpers strip every escape",
      claude_setup_token.plain("\x1b[1mA\x1b[0m\x1b]8;;http://x\x07B\x1b]8;;\x07") == "AB")

print()
if _fails:
    print(f"FAILED {len(_fails)}: {_fails}")
    sys.exit(1)
print("All passed")
