"""Connect Claude: the full sign-in first, the long-lived token second (owner, 2026-11-28).

    python tests/run.py claude_login_then_token     (no network, no real CLI)

Owner that day: "keep both, but sign in fully first and get the token after". One sign-in cannot give both: a
setup-token carries `user:inference` only, the claude.ai connectors need the full login (`user:mcp_servers`). So the
card chains the two (tests/js/test_claude_login_then_token.js), and the server:
  1. tells the card whether it can (`auth_login_first`): not on a Mac (Keychain login), not without a pseudo-terminal;
  2. knows when a connector-capable login runs with no token behind it (`backup_missing`);
  3. rings the bell once per sign-in about it, a while after the sign-in (the owner may still be on step 2).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-claude-first-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import claude_auth  # noqa: E402
import claude_setup_token  # noqa: E402
import config as cfgmod  # noqa: E402

_fails = []
TOK = "sk-ant-oat01-" + "Ab3_x-" * 15 + "Q9zK"
CRED = Path(tempfile.mkdtemp(prefix="javis-claude-cred-")) / ".credentials.json"
claude_auth.login_file = lambda: CRED


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if not cond and extra else ""))
    if not cond:
        _fails.append(name)


def write_login(scopes=("user:inference", "user:profile", "user:mcp_servers"), age=0.0):
    oa = {"accessToken": "a", "refreshToken": "r", "expiresAt": int(time.time() * 1000) + 3600_000,
          "scopes": list(scopes)}
    CRED.write_text(json.dumps({"claudeAiOauth": oa}), encoding="utf-8")
    t = time.time() - age + write_login.n * 1e-3
    write_login.n += 1
    os.utime(CRED, (t, t))


write_login.n = 0


def settings(model):
    cfgmod.write_settings({**cfgmod.read_settings(), "model": model})


SUB = {"claude_auth": "subscription"}
TOKMODE = {"claude_auth": "token", "claude_oauth_token": TOK}

# ============================================================
# 1. whether the card chains the two
# ============================================================
real = claude_setup_token.supported
claude_setup_token.supported = lambda: True
check("Linux with a pseudo-terminal: the full sign-in first, the token second",
      claude_auth.login_then_token(platform="linux"))
check("CANARY: a Mac keeps the token as the one way in (its login is in the Keychain)",
      not claude_auth.login_then_token(platform="darwin"))
claude_setup_token.supported = lambda: False
check("no pseudo-terminal (Windows): the token is pasted, as before",
      not claude_auth.login_then_token(platform="win32"))
claude_setup_token.supported = real

# ============================================================
# 2. a login with nothing behind it
# ============================================================
write_login()
check("CANARY: signed in fully, no token: the backup is missing", claude_auth.backup_missing({"model": SUB}))
check("a token saved next to it: nothing missing", not claude_auth.backup_missing({"model": TOKMODE}))
check("an API key runs: nothing missing",
      not claude_auth.backup_missing({"model": {"claude_auth": "api_key", "anthropic_api_key": "k"}}))
write_login(scopes=("user:inference",))
check("a login without the connector scope is not this case", not claude_auth.backup_missing({"model": SUB}))
CRED.unlink()
check("no login file at all: not this case", not claude_auth.backup_missing({"model": SUB}))

# ============================================================
# 3. the bell, once per sign-in, not right after it
# ============================================================
claude_auth.login_then_token = lambda platform=None: True
NOW = time.time()
write_login()


def model_with(**kw):
    return {"model": {**SUB, **kw}}


check("no `since` yet: nothing due", claude_auth.backup_remind_key(model_with(), now=NOW) == "")
check("right after the sign-in (step 2 may be on screen): no notice yet",
      claude_auth.backup_remind_key(model_with(claude_backup_since=NOW - 60), now=NOW) == "")
k1 = claude_auth.backup_remind_key(model_with(claude_backup_since=NOW - claude_auth.BACKUP_REMIND_AFTER_S - 60), now=NOW)
check("a while later: due, keyed to that sign-in", k1.startswith("claude-no-backup:"), k1)
write_login()   # what the CLI does on every access-token refresh
check("CANARY: a token refresh (the CLI rewrites its login file) does not change the key",
      claude_auth.backup_remind_key(model_with(claude_backup_since=NOW - claude_auth.BACKUP_REMIND_AFTER_S - 60),
                                    now=NOW) == k1)
check("once sent, never due again for that sign-in", claude_auth.backup_remind_key(
    model_with(claude_backup_since=NOW - 9999, claude_backup_reminded=True), now=NOW) == "")
check("the token saved: never due", claude_auth.backup_remind_key(
    {"model": {**TOKMODE, "claude_backup_since": NOW - 9999}}, now=NOW) == "")
check("API key chosen (even with the key blank): never due", claude_auth.backup_remind_key(
    {"model": {"claude_auth": "api_key", "claude_backup_since": NOW - 9999}}, now=NOW) == "")
claude_auth.login_then_token = lambda platform=None: False
check("CANARY: where the card has no Get the backup token button (Windows), the bell stays quiet",
      claude_auth.backup_remind_key(model_with(claude_backup_since=NOW - 9999), now=NOW) == "")
claude_auth.login_then_token = lambda platform=None: True
m = {"claude_backup_since": 1, "claude_backup_reminded": True}
claude_auth.backup_state_reset(m, since=NOW)
check("a new sign-in on the card restarts the count and allows one notice", m == {"claude_backup_since": int(NOW)})
claude_auth.backup_state_reset(m)
check("a token saved or a disconnect clears the state", m == {})

import main  # noqa: E402

added = []
main.inbox.add = lambda text, **kw: added.append((text, kw))
settings(SUB)
main._claude_backup_soon()
check("the first probe that finds no backup only starts the count",
      added == [] and (cfgmod.read_settings()["model"].get("claude_backup_since") or 0) > 0)
m0 = cfgmod.read_settings()["model"]
settings({**m0, "claude_backup_since": int(NOW) - claude_auth.BACKUP_REMIND_AFTER_S - 60})
main._claude_backup_soon()
check("CANARY: due: the probe rings the bell once, important, and marks it sent",
      len(added) == 1 and added[0][1].get("dedup", "").startswith("claude-no-backup:")
      and added[0][1].get("level") == "important" and cfgmod.read_settings()["model"].get("claude_backup_reminded"),
      added)
check("the notice names the button on the card", "Get the backup token" in added[0][0]
      or "L\u1ea5y token d\u1ef1 ph\u00f2ng" in added[0][0])
check("the notice has no em or en dash", not any(c in added[0][0] for c in "\u2014\u2013"))
write_login()   # a refresh after the notice
for _ in range(3):
    main._claude_backup_soon()
check("CANARY: refreshes and later probes never ring it again", len(added) == 1, len(added))
added.clear()
main._claude_token_save(TOK)
check("saving the token clears the bell's state", not any(
    k in cfgmod.read_settings()["model"] for k in ("claude_backup_since", "claude_backup_reminded")))
main._claude_backup_soon()
check("with the token saved, the probe says nothing", added == [])
main._claude_token_forget()
settings({**cfgmod.read_settings()["model"], "claude_backup_reminded": True, "claude_backup_since": 5})
main.claude_cli._LOGIN["finalized"] = False
for name in ("_plan_main_signed_in",):
    setattr(main, name, lambda *a, **k: None)
main.connect_health.engine_reconnected = lambda *a, **k: None
main._claude_main_signed_in()
mm = cfgmod.read_settings()["model"]
check("a sign-in on the card restarts the count from now and allows one notice",
      not mm.get("claude_backup_reminded") and mm.get("claude_backup_since", 0) >= int(NOW), mm)

calls = []
main._claude_account_tokens_soon = lambda: (calls.append("acc"), 1 / 0)
main._claude_backup_soon = lambda: calls.append("backup")
main._claude_probe_checks()
check("the probe runs both Claude checks, one failing never stops the other", calls == ["acc", "backup"], calls)
src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("the probe hook is the combined one", "connect_health.on_probe = _claude_probe_checks" in src)
check("the card's status says whether it chains the two",
      'd["auth_login_first"] = claude_auth.login_then_token()' in src)

print()
if _fails:
    print(f"FAILED {len(_fails)}: {_fails}")
    sys.exit(1)
print("All passed")
