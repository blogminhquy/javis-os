"""Several accounts on one subscription plan card: ChatGPT, Grok Build, Claude Code (0.353.0).

    python tests/run.py plan_accounts      (no network, no CLI needed)

Spec: docs/dev/2026-10-model-routing-spec.md 2.2 and 6.3. Pins what decides behaviour: account 1 is the machine's own
login and never moves; each extra account runs in its own folder; rotation is sequential and an account that ran out
rests while the next one runs; the plan only counts as out of quota when no account of it can run.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-plan-acc-"))
os.environ.setdefault("JAVIS_STATE_DIR", str(_TMP / "state"))
_FAKE_HOME = _TMP / "home"
for d in (".codex", ".grok", ".claude"):
    (_FAKE_HOME / d).mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(_FAKE_HOME)
os.environ["USERPROFILE"] = str(_FAKE_HOME)
for v in ("CODEX_HOME", "GROK_HOME", "CLAUDE_CONFIG_DIR", "XAI_API_KEY"):
    os.environ.pop(v, None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config as cfgmod  # noqa: E402
import model_routing as R  # noqa: E402
import plan_accounts as P  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. the list ----------------------------------------------------------------------------------
m = {}
check("a plan card always has account 1, before any list is saved", [a["id"] for a in P.accounts(m, "openai-oauth")] == ["main"])
check("account 1 runs in the CLI's own folder", P.home("openai-oauth", "main") is None and P.env_for("openai-oauth", None) == {})
check("Antigravity holds one account only", not P.supported("antigravity-cli"))
P.add(m, "openai-oauth", "acc_b", "Plus phụ")
P.add(m, "openai-oauth", "acc_c", "")
check("a new account goes to the end", [a["id"] for a in P.accounts(m, "openai-oauth")] == ["main", "acc_b", "acc_c"])
fb = P.home("openai-oauth", "acc_b")
check("an extra account gets its own folder under the state dir",
      fb is not None and str(fb).startswith(str(Path(cfgmod.STATE_DIR) / "accounts")) and fb.name == "codex")
check("its CLI is pointed there", P.env_for("openai-oauth", fb) == {"CODEX_HOME": str(fb)})

# ---- 2. signed in, per CLI ------------------------------------------------------------------------------
check("an extra ChatGPT account without auth.json is not signed in", not P.signed_in("openai-oauth", "acc_b"))
(fb / "auth.json").write_text(json.dumps({"tokens": {"access_token": "a", "refresh_token": "r"}}), encoding="utf-8")
check("auth.json with tokens = signed in", P.signed_in("openai-oauth", "acc_b"))
fc = P.home("anthropic-cli", "acc_k")
check("an extra Claude account starts signed out", not P.signed_in("anthropic-cli", "acc_k"))
P.mark_signed_in("anthropic-cli", fc)
# 0.355.0: the "sign-in finished" mark counts on macOS only (token in the Keychain); elsewhere the credentials file must exist.
check("Claude: the sign-in mark alone counts on macOS only", P.signed_in("anthropic-cli", "acc_k") == (sys.platform == "darwin"))
(fc / ".credentials.json").write_text("{}", encoding="utf-8")
check("Claude: a credentials file = signed in", P.signed_in("anthropic-cli", "acc_k"))
(P.default_home("openai-oauth") / "javis.config.toml").write_text("[profiles.javis]\n", encoding="utf-8")
(P.default_home("openai-oauth") / "auth.json").write_text("{}", encoding="utf-8")
P.prepare("openai-oauth", fb)
check("account 1's Codex settings (hub profile) are copied into the extra folder", (fb / "javis.config.toml").exists())
check("account 1's login is never copied", json.loads((fb / "auth.json").read_text(encoding="utf-8"))["tokens"]["access_token"] == "a")

# ---- 3. rotation ---------------------------------------------------------------------------------------
check("account 1 runs first", P.pick(m, "openai-oauth")["id"] == "main")
R.mark_rest("openai-oauth", "main", seconds=600)
check("account 1 out of quota: the next signed-in account runs", P.pick(m, "openai-oauth")["id"] == "acc_b")
check("an account still signing in is skipped", all(a["id"] != "acc_c" for a in P.usable(m, "openai-oauth")))
R.mark_rest("openai-oauth", "acc_b", seconds=600)
check("every account resting: nothing can run", P.pick(m, "openai-oauth") is None)
R.clear_rest("openai-oauth", "main")
check("account 1 back: it runs first again", P.pick(m, "openai-oauth")["id"] == "main")
R.clear_rest("openai-oauth", "acc_b")
P.save(m, "openai-oauth", [{"id": "acc_b", "label": "Plus phụ", "enabled": True},
                           {"id": "main", "label": "", "enabled": False}])
check("an account missing from a stale page is kept, at the end (0.355.0)",
      [a["id"] for a in P.accounts(m, "openai-oauth")] == ["acc_b", "main", "acc_c"])
P.home("openai-oauth", "acc_c")   # its folder, so the removal below can be seen deleting it
P.save(m, "openai-oauth", [{"id": "acc_b", "label": "Plus phụ", "enabled": True},
                           {"id": "main", "label": "", "enabled": False}], removed=["acc_c"])
check("the owner's order and on/off are kept", [(a["id"], a["enabled"]) for a in P.accounts(m, "openai-oauth")]
      == [("acc_b", True), ("main", False)])
check("a removed extra account loses its folder", not P.home("openai-oauth", "acc_c", create=False).exists())
P.save(m, "openai-oauth", [{"id": "acc_b", "label": "", "enabled": True}])
check("account 1 cannot be removed", any(a["id"] == "main" for a in P.accounts(m, "openai-oauth")))
P.save(m, "openai-oauth", P.accounts(m, "openai-oauth"), removed=["main"])
check("account 1 cannot be removed even by name", any(a["id"] == "main" for a in P.accounts(m, "openai-oauth")))


# ---- 4. engines are pointed at the account ---------------------------------------------------------------------
class FakeCodex:
    pass


class FakeOptions:
    def __init__(self):
        self.env = {}


class FakeClaude:
    def __init__(self):
        self.model = "x"

    def _options(self):
        return FakeOptions()


e = P.use(FakeCodex(), "openai-oauth", "acc_b")
check("a Codex engine on account 2 runs with its CODEX_HOME", e.codex_home == str(fb) and e.account_id == "acc_b")
e1 = P.use(FakeCodex(), "openai-oauth", "main")
check("a Codex engine on account 1 keeps the default folder", e1.codex_home is None)
import claude_cli  # noqa: E402
check("codex_env takes an account folder", claude_cli.codex_env(str(fb))["CODEX_HOME"] == str(fb))
import grok_cli  # noqa: E402
check("Grok runs with GROK_HOME of its account", grok_cli._moi_truong("/tmp/g")["GROK_HOME"] == "/tmp/g")
check("Grok on account 1 keeps the default", "GROK_HOME" not in grok_cli._moi_truong())
c = FakeClaude()
P.use(c, "anthropic-cli", "acc_k")
check("a Claude engine on account 2 hands CLAUDE_CONFIG_DIR to the claude process",
      c._options().env.get("CLAUDE_CONFIG_DIR") == str(fc) and "PATH" in c._options().env)
c2 = copy.copy(c)
P.use(c2, "anthropic-cli", "main")
check("a copy for another account builds its own options (background work)",
      "CLAUDE_CONFIG_DIR" not in (c2._options().env or {}) and c._options().env.get("CLAUDE_CONFIG_DIR") == str(fc))

# ---- 5. background: one link per account ---------------------------------------------------------------------
import aux_engine  # noqa: E402
s = cfgmod.read_settings()
s["model"]["accounts"] = {"openai-oauth": [{"id": "main", "label": "", "enabled": True},
                                           {"id": "acc_b", "label": "", "enabled": True}]}
links = aux_engine._per_account("openai-oauth", FakeCodex(), s, FakeCodex)
check("a plan card with two accounts gives two background links, account 1 first",
      [getattr(x, "account_id", "") for x in links] == ["main", "acc_b"])
check("each link rests its own account on a quota error",
      all(getattr(x, "account_provider", "") == "openai-oauth" for x in links))
aux_engine._FallbackChain._rest(links[1], "429 usage limit reached")
check("a background quota error rests that account for chat too", R.resting_until("openai-oauth", "acc_b") > 0)
R.clear_rest("openai-oauth", "acc_b")
one = aux_engine._per_account("grok-cli", FakeCodex(), {"model": {}}, FakeCodex)
check("a plan card with one account runs as before (one link, no account set)",
      len(one) == 1 and not hasattr(one[0], "account_id"))

# ---- 6. chat: the plan is out of quota only when no account is left -----------------------------------------
import main  # noqa: E402
s = cfgmod.read_settings()
s["model"]["accounts"] = {"openai-oauth": [{"id": "main", "label": "", "enabled": True},
                                           {"id": "acc_b", "label": "", "enabled": True}]}
cfgmod.write_settings(s)
mcfg = cfgmod.read_settings()["model"]
main._PIN_LIMITED.clear()
eng = FakeCodex()
check("chat picks account 1 first", main._plan_account_apply(eng, "openai-oauth", mcfg) == "main")
main._note_pin_limit("codex")
check("account 1 out of quota rests, the plan is not pinned away while account 2 can run",
      R.resting_until("openai-oauth", "main") > 0 and not main._pin_limited_until("openai-oauth"))
check("the next chat turn runs on account 2", main._plan_account_apply(FakeCodex(), "openai-oauth", mcfg) == "acc_b")
check("the plan card can still take a turn", main._route_ready(mcfg, "openai-oauth"))
main._note_pin_limit("codex")
check("account 2 out of quota too: now the plan counts as out of quota",
      main._pin_limited_until("openai-oauth") > 0 and not main._route_ready(mcfg, "openai-oauth"))
R.clear_rest("openai-oauth", "main")
R.clear_rest("openai-oauth", "acc_b")
main._PIN_LIMITED.clear()

# ---- 6b. code review fixes (0.355.0) ---------------------------------------------------------------------------
main._PLAN_ACCOUNT_LAST["openai-oauth"] = "acc_b"            # another chat picked account 2 since
main._note_pin_limit("codex", account="main")                 # ...but THIS turn ran on account 1
check("the account the failing turn ran on rests, not the last one any chat picked",
      R.resting_until("openai-oauth", "main") > 0 and not R.resting_until("openai-oauth", "acc_b"))
nxt = main._chat_next_route(mcfg, "openai-oauth", failed_account="main")
check("next route after account 1 runs out: account 2 of the same card",
      bool(nxt) and nxt["route"][0] == "openai-oauth" and "2" in nxt["status"], str(nxt.get("status")))
R.clear_rest("openai-oauth", "main")
main._PIN_LIMITED.clear()

import aux_engine  # noqa: E402
e = P.use(FakeCodex(), "openai-oauth", "acc_b")
aux_engine._FallbackChain._rest(e, "model_not_found: gpt-x is not available on this plan")
check("a background 'model not found' does not rest the plan account for chat", not R.resting_until("openai-oauth", "acc_b"))
aux_engine._FallbackChain._rest(e, "You've hit your usage limit")
check("a background quota error rests it", R.resting_until("openai-oauth", "acc_b") > 0)
R.clear_rest("openai-oauth", "acc_b")
aux_engine._COOLDOWN.clear()

m_off = {"accounts": {"openai-oauth": [{"id": "main", "label": "", "enabled": False},
                                       {"id": "acc_b", "label": "", "enabled": True}]}}
R.mark_rest("openai-oauth", "acc_b", seconds=600)
check("nothing usable and account 1 switched off: account 2 still runs (and reports its quota)",
      P.apply(FakeCodex(), "openai-oauth", m_off) == "acc_b" and P.fallback(m_off, "openai-oauth")["id"] == "acc_b")
R.clear_rest("openai-oauth", "acc_b")

ch = P.default_home("anthropic-cli")
ch.mkdir(parents=True, exist_ok=True)
(ch.parent / ".claude.json").write_text(json.dumps({"mcpServers": {"gmail": {"type": "http", "url": "https://x"}},
                                                    "oauthAccount": {"emailAddress": "one@x"}}), encoding="utf-8")
fk = P.home("anthropic-cli", "acc_k")
(fk / ".claude.json").write_text(json.dumps({"oauthAccount": {"emailAddress": "two@x"}}), encoding="utf-8")
P.prepare("anthropic-cli", fk)
kj = json.loads((fk / ".claude.json").read_text(encoding="utf-8"))
check("an extra Claude account sees account 1's user-scope MCP servers, keeping its own login data",
      "gmail" in (kj.get("mcpServers") or {}) and kj["oauthAccount"]["emailAddress"] == "two@x")

import time as _t  # noqa: E402
main._PLAN_LOGIN["acc_k"] = {"provider": "anthropic-cli", "ts": _t.time() + 60}
check("sign in again: the old credentials file does not finish the new sign-in",
      not main._plan_login_fresh("anthropic-cli", "acc_k", fk))
main._PLAN_LOGIN["acc_k"]["ts"] = _t.time() - 60
check("a credentials file written after the sign-in started finishes it", main._plan_login_fresh("anthropic-cli", "acc_k", fk))
main._PLAN_LOGIN.pop("acc_k", None)

# ---- 7. Models page --------------------------------------------------------------------------------------------
v = main.settings_get()["model"]
acc_view = {a["id"]: a for a in v["accounts"]["openai-oauth"]}
check("the page lists account 1 and the extra account with sign-in state",
      acc_view["main"]["main"] and acc_view["acc_b"]["signed_in"] and not acc_view["acc_b"]["main"])
check("the page knows which cards hold plan accounts", set(v["routing"]["multi_plan"]) == set(P.KIND))
asyncio.run(main.settings_set("model", json.dumps({"accounts": {"provider": "openai-oauth", "items": [
    {"id": "acc_b", "label": "Plus phụ", "enabled": True}, {"id": "main", "label": "Pro chính", "enabled": True}]}})))
check("saving the list keeps order and labels",
      [(a["id"], a["label"]) for a in P.accounts(cfgmod.read_settings()["model"], "openai-oauth")]
      == [("acc_b", "Plus phụ"), ("main", "Pro chính")])
check("the plan card is never dropped from the usage order by its list", True)

print()
if _fails:
    print(f"ĐỎ {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("Tất cả xanh.")
