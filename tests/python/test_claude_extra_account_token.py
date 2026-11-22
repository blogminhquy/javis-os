"""Extra Claude accounts sign in with a long-lived token too (2026-11-22).

    python tests/run.py claude_extra_account_token     (no network; a fake `claude` plays setup-token)

Owner, 22/11/2026, after account 1 moved to a long-lived token from `claude setup-token`: "anh đồng ý phần này" (extra
accounts on the "Add an account" button the same way). Their old sign-in (`claude auth login` into the account's own
folder) could run out midway just like account 1's.

Covered here:
  1. the token is kept in the account's folder, encrypted, readable by this user only, and goes with the folder;
  2. the account counts as signed in, and the card's row gets the token's dates (account 1's from the card's token);
  3. a turn on an extra account runs on that account's token, never account 1's; one without a token runs on its folder;
  4. `claude auth status` for an extra account asks with its own token, never the server's;
  5. END TO END through the API: Add an account -> the link -> the code -> the token is in the folder and the account
     is on the card; a browser that finishes without a code is caught by the poll; cancelling stops the command;
  6. a week before an extra account's token ends, one bell notice a day names that account.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-extra-token-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config as cfgmod  # noqa: E402
import plan_accounts  # noqa: E402

_fails = []
CLAUDE = "anthropic-cli"
TOK1 = "sk-ant-oat01-" + "One1_-" * 15 + "AAAA"
TOK2 = "sk-ant-oat01-" + "Two2_-" * 15 + "BBBB"


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if not cond and extra else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Kept in the folder, encrypted
# ============================================================
folder = plan_accounts.home(CLAUDE, "acc2")
check("an extra account has its own folder", folder is not None and folder.exists(), folder)
check("CANARY: the token is saved in the account's folder", plan_accounts.save_claude_token(folder, TOK2))
f = Path(folder) / plan_accounts._CLAUDE_TOKEN
raw = f.read_text(encoding="utf-8")
check("encrypted on disk", TOK2 not in raw, raw[:80])
check("readable by this user only", os.name != "posix" or stat.S_IMODE(f.stat().st_mode) == 0o600,
      oct(stat.S_IMODE(f.stat().st_mode)))
check("and reads back as is", plan_accounts.claude_token(folder) == TOK2)
check("no folder, no token", plan_accounts.claude_token(None) == "" and not plan_accounts.save_claude_token(None, TOK2))

# ============================================================
# 2. Signed in, and the row's dates
# ============================================================
cfg = cfgmod.read_settings()
m = cfg["model"]
plan_accounts.add(m, CLAUDE, "acc2", "Work")
m.update(claude_auth="token", claude_oauth_token=TOK1, claude_oauth_token_at=int(time.time()) - 10 * 86400)
cfgmod.write_settings(cfg)
check("CANARY: an extra account on a token counts as signed in", plan_accounts.signed_in(CLAUDE, "acc2"))
rows = {r["id"]: r for r in plan_accounts.view(cfgmod.read_settings()["model"], CLAUDE)}
r2, r1 = rows.get("acc2") or {}, rows.get(plan_accounts.MAIN) or {}
check("the extra account's row gets its token's dates", r2.get("token_set") and r2.get("token_days_left") == 365, r2)
check("account 1's row gets the card's token dates", r1.get("token_set") and r1.get("token_days_left") == 355, r1)
check("never a token in the rows", TOK1 not in json.dumps(rows) and TOK2 not in json.dumps(rows))

# ============================================================
# 3. A turn on an extra account runs on its own token
# ============================================================


class _Eng:
    def _options(self):
        return SimpleNamespace(env={"PATH": "/bin", "CLAUDE_CODE_OAUTH_TOKEN": TOK1})


e2 = _Eng()
plan_accounts.use(e2, CLAUDE, "acc2")
env = e2._options().env
check("CANARY: an extra account runs on ITS token, never account 1's",
      env.get("CLAUDE_CODE_OAUTH_TOKEN") == TOK2 and env.get("CLAUDE_CONFIG_DIR") == str(folder), env)
plan_accounts.home(CLAUDE, "acc3")
e3 = _Eng()
plan_accounts.use(e3, CLAUDE, "acc3")
check("an extra account still on its old sign-in runs on its folder, without account 1's token",
      "CLAUDE_CODE_OAUTH_TOKEN" not in e3._options().env)
e1 = _Eng()
plan_accounts.use(e1, CLAUDE, plan_accounts.MAIN)
check("account 1 keeps the card's token", e1._options().env.get("CLAUDE_CODE_OAUTH_TOKEN") == TOK1)

# ============================================================
# 4. `claude auth status` for an extra account
# ============================================================
import claude_cli  # noqa: E402

seen = {}
_real_run = claude_cli.subprocess.run
_real_find = claude_cli.find_claude_cli


def _fake_run(args, **kw):
    seen["env"] = kw.get("env") or {}
    return SimpleNamespace(stdout=json.dumps({"loggedIn": True, "authMethod": "oauth_token"}), returncode=0)


os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-server-wide-token-xxxxxxxxxxxxxxxx"
claude_cli.find_claude_cli = lambda: "/usr/bin/claude"
claude_cli.subprocess.run = _fake_run
st2 = claude_cli.auth_status_folder(folder)
env2 = dict(seen.get("env") or {})
claude_cli.auth_status_folder(plan_accounts.home(CLAUDE, "acc3"))
env3 = dict(seen.get("env") or {})
claude_cli.subprocess.run = _real_run
claude_cli.find_claude_cli = _real_find
os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
check("CANARY: an extra account's status is asked with its own token",
      env2.get("CLAUDE_CODE_OAUTH_TOKEN") == TOK2 and st2.get("connected"), env2.get("CLAUDE_CODE_OAUTH_TOKEN"))
check("never with the server's token", "CLAUDE_CODE_OAUTH_TOKEN" not in env3, env3.get("CLAUDE_CODE_OAUTH_TOKEN"))

# ============================================================
# 5. END TO END through the API
# ============================================================
import claude_setup_token  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FAKE = r'''#!/usr/bin/env python3
import os, sys, time
if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
    print("token leaked into setup-token"); sys.exit(3)
url = "https://claude.ai/oauth/authorize?Extra42"
sys.stdout.write("Welcome\r\n\x1b]8;;" + url + "\x07" + url + "\x1b]8;;\x07\r\n Paste code here if prompted > ")
sys.stdout.flush()
if os.environ.get("FAKE_MODE") == "browser":
    time.sleep(0.5)
else:
    code = sys.stdin.readline().strip()
    if code != "good#state":
        sys.stdout.write("\r\nOAuth error: That code wasn't accepted.\r\n"); sys.stdout.flush(); time.sleep(30); sys.exit(1)
cfg = os.environ.get("CLAUDE_CONFIG_DIR", "")
tok = "sk-ant-oat01-" + ("Acc4_-" if cfg.endswith(os.sep + "claude") else "Main_-") * 15 + "CCCC"
sys.stdout.write("\r\nYour OAuth token (valid for 1 year):\r\n\r\n" + tok + "\r\n\r\nStore this token securely.\r\n")
sys.stdout.flush(); time.sleep(0.3)
'''
TOK4 = "sk-ant-oat01-" + "Acc4_-" * 15 + "CCCC"
fake = Path(tempfile.mkdtemp(prefix="fake-claude-")) / "claude"
fake.write_text(FAKE, encoding="utf-8")
fake.chmod(fake.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

if not claude_setup_token.supported():
    print("skip the end-to-end checks: no pseudo-terminal on this machine")
else:
    main.find_claude_cli = lambda: str(fake)
    main.warm_pool.POOL.drop_kind = lambda kind: None
    c = TestClient(main.app, base_url="http://127.0.0.1:8080")
    r = c.post("/plan-accounts/login-start", json={"provider": CLAUDE, "label": "Shop"}).json()
    aid = r.get("account_id")
    check("CANARY: Add an account gives the sign-in link and asks for a code",
          r.get("ok") and r.get("url") == "https://claude.ai/oauth/authorize?Extra42" and r.get("needs_code"), r)
    bad = c.post("/plan-accounts/login-code", json={"provider": CLAUDE, "account_id": aid, "code": "wrong"}).json()
    check("a refused code says so and adds nothing", bad.get("ok") is False and "accepted" in bad.get("error", ""), bad)
    claude_setup_token.stop()
    r = c.post("/plan-accounts/login-start", json={"provider": CLAUDE, "label": "Shop", "account_id": aid}).json()
    d = c.post("/plan-accounts/login-code", json={"provider": CLAUDE, "account_id": aid, "code": "good#state"}).json()
    f4 = plan_accounts.home(CLAUDE, aid)
    ids = [a["id"] for a in plan_accounts.accounts(cfgmod.read_settings()["model"], CLAUDE)]
    check("CANARY: the code gives the account its own token, kept in its folder",
          d.get("ok") and d.get("connected") and plan_accounts.claude_token(f4) == TOK4, d)
    check("and the account is on the card, named", aid in ids and any(
        a["label"] == "Shop" for a in plan_accounts.accounts(cfgmod.read_settings()["model"], CLAUDE)), ids)
    check("the command was stopped and forgets the token", claude_setup_token.poll() == {"waiting": False})
    check("account 1's token is untouched", cfgmod.read_settings()["model"]["claude_oauth_token"] == TOK1)

    # A browser on the machine running Javis finishes it without a code: the poll keeps the token.
    os.environ["FAKE_MODE"] = "browser"
    r = c.post("/plan-accounts/login-start", json={"provider": CLAUDE, "label": "Home"}).json()
    aid5 = r.get("account_id")
    got = {}
    for _ in range(40):
        got = c.get(f"/plan-accounts/login-poll?provider={CLAUDE}&account_id={aid5}").json()
        if got.get("connected"):
            break
        time.sleep(0.2)
    check("a sign-in finished in the browser is caught by the poll",
          got.get("connected") and plan_accounts.claude_token(plan_accounts.home(CLAUDE, aid5)), got)
    os.environ.pop("FAKE_MODE", None)

    r = c.post("/plan-accounts/login-start", json={"provider": CLAUDE, "label": "Later"}).json()
    c.post("/plan-accounts/login-cancel", json={"provider": CLAUDE, "account_id": r.get("account_id")})
    check("cancelling stops the command and drops the unfinished account's folder",
          claude_setup_token.poll() == {"waiting": False}
          and not (plan_accounts.home(CLAUDE, r.get("account_id"), create=False) or Path("/nonexistent")).exists())

# ============================================================
# 6. The reminder a week before an extra account's token ends
# ============================================================
bell = []
main.inbox.add = lambda text, **kw: bell.append((text, kw))
main._claude_account_tokens_soon()
check("a fresh token: no reminder", bell == [], bell)
tf = Path(folder) / plan_accounts._CLAUDE_TOKEN
d = json.loads(tf.read_text(encoding="utf-8"))
d["at"] = int(time.time()) - 360 * 86400
tf.write_text(json.dumps(d), encoding="utf-8")
main._claude_account_tokens_soon()
check("CANARY: a week before, one bell notice names the account and the step",
      len(bell) == 1 and "Work" in bell[0][0] and bell[0][1].get("dedup", "").startswith("claude-token-soon:acc2:"),
      bell)

print()
if _fails:
    print(f"FAILED {len(_fails)}: {_fails}")
    sys.exit(1)
print("All passed")
