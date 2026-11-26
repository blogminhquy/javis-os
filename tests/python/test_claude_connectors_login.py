"""claude.ai connectors next to the long-lived Claude token (2026-11-26).

    python tests/run.py claude_connectors_login     (no network, no real CLI)

Owner's report that day, with a screenshot of Javis's own answer: after the switch to the long-lived token
(`claude setup-token`, 2026-11-22) Claude Code no longer loaded the connectors added on claude.ai (Google Calendar,
Gmail, Drive...). Claude Code decides it: a token handed in as CLAUDE_CODE_OAUTH_TOKEN counts as scope
`user:inference` only, and claude.ai connectors need a login with `user:mcp_servers`.

Covered here:
  1. token mode runs on the machine's login when it carries the connector scope; the token waits as the backup;
  2. a login without that scope, without a refresh token, or none at all: the token runs, as before;
  3. a turn that finds the login gone hands over to the token (engine check + router, once), and a new login lifts it;
  4. the router: the card is not marked signed out, the same turn runs again on the token, only once;
  5. the Models card reads which one runs; the ChatGPT browser sign-in asks for the connector scopes too.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-claude-conn-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import claude_auth  # noqa: E402
import config as cfgmod  # noqa: E402

_fails = []
TOK = "sk-ant-oat01-" + "Ab3_x-" * 15 + "Q9zK"
CRED = Path(tempfile.mkdtemp(prefix="javis-claude-cred-")) / ".credentials.json"
claude_auth.login_file = lambda: CRED


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if not cond and extra else ""))
    if not cond:
        _fails.append(name)


def write_login(scopes=("user:inference", "user:profile", "user:mcp_servers"), refresh=True, exp=None):
    oa = {"accessToken": "a", "expiresAt": exp or int(time.time() * 1000) + 3600_000, "scopes": list(scopes)}
    if refresh:
        oa["refreshToken"] = "r"
    CRED.write_text(json.dumps({"claudeAiOauth": oa}), encoding="utf-8")
    t = time.time() + (write_login.n)
    write_login.n += 1
    os.utime(CRED, (t, t))     # a new login always has a new stamp, even inside one second


write_login.n = 0


def reset():
    claude_auth._LOGIN_DEAD.update(sig=None, at=0.0, claimed=False)


def tok_settings():
    return {"model": {"claude_auth": "token", "claude_oauth_token": TOK}}


# ============================================================
# 1-2. which credentials a `claude` gets
# ============================================================
reset()
write_login()
check("CANARY: token mode with a connector-capable login runs on the login (claude.ai connectors load)",
      claude_auth.env_cho_cli(tok_settings()) == {} and claude_auth.runs_on(tok_settings()) == "login")
check("the token stays saved as the backup", claude_auth.oauth_token(tok_settings()) == TOK)
write_login(scopes=("user:inference",))
check("a login without user:mcp_servers: the token runs",
      claude_auth.env_cho_cli(tok_settings()) == {"CLAUDE_CODE_OAUTH_TOKEN": TOK})
write_login(refresh=False)
check("a login with no refresh token: the token runs",
      claude_auth.env_cho_cli(tok_settings()) == {"CLAUDE_CODE_OAUTH_TOKEN": TOK})
CRED.unlink()
check("no login file (a Mac keeps it in the Keychain): the token runs, as before",
      claude_auth.env_cho_cli(tok_settings()) == {"CLAUDE_CODE_OAUTH_TOKEN": TOK}
      and claude_auth.runs_on(tok_settings()) == "token")
CRED.write_text("{broken", encoding="utf-8")
check("a broken login file: the token runs", claude_auth.env_cho_cli(tok_settings()) == {"CLAUDE_CODE_OAUTH_TOKEN": TOK})
write_login()
check("subscription mode is untouched", claude_auth.env_cho_cli({"model": {"claude_auth": "subscription"}}) == {})
check("API key mode is untouched", claude_auth.env_cho_cli(
    {"model": {"claude_auth": "api_key", "anthropic_api_key": "k"}}) == {"ANTHROPIC_API_KEY": "k"})
check("token mode without a token saved: the login, as before",
      claude_auth.env_cho_cli({"model": {"claude_auth": "token"}}) == {})
check("never a token value read out of the login file",
      "accessToken" not in json.dumps(claude_auth._login_sig()))

# ============================================================
# 3. the login dies: the token takes over, a new login lifts it
# ============================================================
cfgmod.write_settings({**cfgmod.read_settings(), "model": tok_settings()["model"]})
reset()
write_login()
check("the engine's own check hands over to the token (no claim yet)", claude_auth.note_login_failed(claim=False))
check("after it, turns run on the token", claude_auth.env_cho_cli() == {"CLAUDE_CODE_OAUTH_TOKEN": TOK})
check("the router claims that same refusal once", claude_auth.note_login_failed())
check("CANARY: a second refusal (now on the token) is not taken over", not claude_auth.note_login_failed())
check("token_took_over says the turn may run again on the token", claude_auth.token_took_over())
check("token_took_over ends after its window", not claude_auth.token_took_over(now=time.time() + 600))
write_login()
check("CANARY: a new sign-in (the file changes) lifts the mark: the login runs again",
      not claude_auth.login_dead() and claude_auth.env_cho_cli() == {})
reset()
write_login(scopes=("user:inference",))
check("a refusal while the token already ran is never taken over",
      not claude_auth.note_login_failed(claim=False) and not claude_auth.note_login_failed())

import connect_health  # noqa: E402
reset()
write_login()
connect_health._engines.pop("claude", None)
connect_health.flag_engine_auth_error("claude", "Failed to authenticate: this login reached its time limit and "
                                                "cannot be renewed. Run claude auth login to sign in again")
check("CANARY: the engine light stays green when the token took over",
      (connect_health._engines.get("claude") or {}).get("ok") is not False
      and claude_auth.env_cho_cli() == {"CLAUDE_CODE_OAUTH_TOKEN": TOK})
reset()
write_login(scopes=("user:inference",))
connect_health.flag_engine_auth_error("claude", "Failed to authenticate: this login reached its time limit and "
                                                "cannot be renewed. Run claude auth login to sign in again")
check("a refused token still turns the light red",
      (connect_health._engines.get("claude") or {}).get("ok") is False)

# ============================================================
# 4. the router
# ============================================================
import main  # noqa: E402

main.inbox.add = lambda *a, **k: None
main._SIGNED_OUT.clear()
reset()
write_login()
main._note_signin_lost("anthropic-cli")
check("CANARY: the card is NOT marked signed out when the token takes over",
      not main._signed_out_until("anthropic-cli"))
mcfg = cfgmod.read_settings().get("model") or {}
nxt = main._chat_next_route(mcfg, "anthropic-cli", tried=[], reason="signin")
check("the same turn runs again at once on Claude Code, now on the token",
      (nxt.get("route") or ("",))[0] == "anthropic-cli" and "token" in nxt.get("status", ""), nxt)
check("the rerun uses the token", claude_auth.env_cho_cli() == {"CLAUDE_CODE_OAUTH_TOKEN": TOK})
main._note_signin_lost("anthropic-cli")
check("CANARY: the token refused too: the card is marked as before",
      main._signed_out_until("anthropic-cli") > time.time())
nxt2 = main._chat_next_route(mcfg, "anthropic-cli", tried=["anthropic-cli"], reason="signin")
check("and the turn is never sent back to the same card",
      (nxt2.get("route") or ("",))[0] != "anthropic-cli", nxt2)
main._SIGNED_OUT.clear()
reset()
write_login()
main._note_signin_lost("anthropic-cli", account="acc-2")
check("an extra account's refusal never touches account 1's login",
      not claude_auth.login_dead() and main._signed_out_until("anthropic-cli") > 0)
main._SIGNED_OUT.clear()

# ============================================================
# 5. what the card reads, and the ChatGPT browser sign-in
# ============================================================
reset()
write_login()
src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("the status the card reads says which one runs",
      'd["auth_runs_on"] = claude_auth.runs_on()' in src and 'd["auth_connectors"]' in src)
js = (Path(ROOT) / "dashboard" / "console.js").read_text(encoding="utf-8")
check("the card has a button that signs in for the connectors, on the existing login flow",
      "data-conn-login" in js and '"/claude/login-start"' in js and '"/claude/login-poll"' in js)
for lang in ("vi", "en"):
    tr = json.loads((Path(ROOT) / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"{lang}: the card's new lines are translated",
          all(tr.get(k) for k in ("models.conn_on", "models.conn_off", "models.conn_btn", "models.conn_s1")))
    check(f"{lang}: no em or en dash in them",
          not any(c in tr.get(k, "") for k in ("models.conn_on", "models.conn_off", "models.conn_btn",
                                               "models.conn_s1") for c in "—–"))

import openai_oauth  # noqa: E402
q = parse_qs(urlparse(openai_oauth.start_browser()["authorize_url"]).query)
sc = (q.get("scope") or [""])[0].split()
check("CANARY: the ChatGPT browser sign-in asks for the scopes Codex asks for (apps and connectors)",
      sc == ["openid", "profile", "email", "offline_access", "api.connectors.read", "api.connectors.invoke"], sc)

print()
if _fails:
    print(f"FAILED {len(_fails)}: {_fails}")
    sys.exit(1)
print("All passed")
