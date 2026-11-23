"""The ChatGPT model list comes from the account a Codex run uses now, not always from account 1.

    python tests/run.py chatgpt_model_list_account      (no network, no Codex CLI)

Owner's report 23/11/2026, "the Models page shows only 3 GPT models": account 1 (a Free plan) was switched off on the
ChatGPT card and an extra Plus account was on. Chat turns ran on the Plus account, but `openai_oauth.list_models`
always asked account 1: it wrote account 1's tokens into the shared ~/.codex and asked Codex app-server there, so the
picker showed the Free plan's 3 models instead of the Plus plan's 10, and every refresh wrote the 3 back over a 10.
The Models page picker then kept that old list for good, because it opened on `peek` and asked only when it had none.

This rebuilds that scene with fake Codex answers: one list per login folder.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-gpt-list-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
_FAKE_HOME = _TMP / "home"
(_FAKE_HOME / ".codex").mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(_FAKE_HOME)
os.environ["USERPROFILE"] = str(_FAKE_HOME)
os.environ.pop("CODEX_HOME", None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import codex_models  # noqa: E402
import config as cfgmod  # noqa: E402
import model_routing  # noqa: E402
import openai_oauth  # noqa: E402
import plan_accounts as P  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


GPT = "openai-oauth"
FREE = ["gpt-6-luna", "gpt-5.6-terra", "gpt-5.6-luna"]
PLUS = ["gpt-6.2-sol", "gpt-6.2-astra", "gpt-6.1-terra", "gpt-6.1-sol", "gpt-6-astra",
        "gpt-6-sol", "gpt-6-luna", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]

# ---- the scene: account 1 signed in through Javis (Free), one extra account signed in (Plus) ----
cfg = cfgmod.read_settings()
cfg["model"]["openai_oauth"] = {"access_token": "free-at", "refresh_token": "free-rt", "id_token": "",
                                "account_id": "acct-free", "plan": "free", "expires_at": 9e12}
P.add(cfg["model"], GPT, "acc_plus", "Plus")
cfgmod.write_settings(cfg)
PLUS_HOME = P.home(GPT, "acc_plus")
(PLUS_HOME / "auth.json").write_text(json.dumps({"tokens": {"access_token": "plus-at", "refresh_token": "plus-rt",
                                                            "account_id": "acct-plus"}}), encoding="utf-8")
SHARED_AUTH = _FAKE_HOME / ".codex" / "auth.json"

# Codex app-server, faked: each login folder answers with its own plan's list.
asked_homes = []


def fake_codex_list(timeout=20.0, cli_path=None, popen_factory=None, codex_home=None):
    asked_homes.append(codex_home)
    ids = PLUS if codex_home == str(PLUS_HOME) else FREE
    return {"models": list(ids), "items": [], "default_model": ids[0], "source": "codex-app-server"}


bridged = []
codex_models.list_models = fake_codex_list
openai_oauth.write_codex_auth = lambda: bridged.append(1) or True


def set_accounts(main_on=True, plus_on=True, order=("main", "acc_plus")):
    c = cfgmod.read_settings()
    on = {"main": main_on, "acc_plus": plus_on}
    P.save(c["model"], GPT, [{"id": a, "label": "", "enabled": on[a]} for a in order])
    cfgmod.write_settings(c)
    return c["model"]


class _Engine:
    codex_home = None


def runs_on(m):
    """The account a chat turn is pointed at, through the same path the chat uses."""
    return P.apply(_Engine(), GPT, m)


# ---- 1. the owner's scene: account 1 (Free) off, Plus on ----
m = set_accounts(main_on=False, plus_on=True)
asked_homes.clear()
bridged.clear()
got = openai_oauth.list_models()
check("account 1 switched off: the list is the Plus account's 10 models", got == PLUS, got)
check("...asked in the Plus account's own login folder", asked_homes == [str(PLUS_HOME)], asked_homes)
check("...without writing account 1's tokens into the shared ~/.codex", bridged == [] and not SHARED_AUTH.exists())
check("the list comes from the same account a chat turn runs on",
      P.current(m, GPT) == runs_on(m) == "acc_plus", (P.current(m, GPT), runs_on(m)))

# ---- 2. a refresh asks the same account again; nothing writes the 3 back ----
again = openai_oauth.list_models()
check("asking again still gives 10, never falls back to account 1's 3", again == PLUS and len(asked_homes) == 2)

# ---- 3. one account only, or account 1 first and on: exactly as before ----
m = set_accounts(main_on=True, plus_on=True)
asked_homes.clear()
bridged.clear()
check("account 1 on and first: its own list, as before", openai_oauth.list_models() == FREE)
check("...asked in account 1's folder after bridging its tokens, as before", asked_homes == [None] and bridged == [1])
check("...and the chat runs there too", runs_on(m) == "main")

m = set_accounts(main_on=True, plus_on=True, order=("acc_plus", "main"))
asked_homes.clear()
check("Plus moved first: the list follows the order", openai_oauth.list_models() == PLUS and runs_on(m) == "acc_plus")

# ---- 4. the Plus account rests out of quota: the list follows the account that now answers ----
m = set_accounts(main_on=True, plus_on=True, order=("acc_plus", "main"))
model_routing.mark_rest(GPT, "acc_plus", seconds=3600)
asked_homes.clear()
check("Plus resting, account 1 on: list and chat both on account 1",
      openai_oauth.list_models() == FREE and runs_on(m) == "main" and asked_homes == [None])
model_routing.clear_rest(GPT, "acc_plus")

# ---- 5. every account switched off: same answer as the chat (account 1, which reports its own error) ----
m = set_accounts(main_on=False, plus_on=False)
check("every account off: listing and chat agree", P.current(m, GPT) == runs_on(m) == "main")

# ---- 6. an explicit account is asked as given (image generation asks the account it draws on) ----
set_accounts(main_on=True, plus_on=True)
asked_homes.clear()
check("account_key='acc_plus' asks that account even when account 1 runs chat",
      openai_oauth.list_models("acc_plus") == PLUS and asked_homes == [str(PLUS_HOME)])
check("an extra account that is not signed in gives no list (not account 1's)",
      openai_oauth.list_models("acc_gone") is None)

# ---- 7. old Codex CLI without model/list: the backend is asked with the SAME account's token ----
codex_models.list_models = lambda **kw: None
backend_tokens = []
_orig_backend = openai_oauth._list_models_backend
_orig_for = openai_oauth.valid_creds_for
openai_oauth._list_models_backend = lambda creds: (backend_tokens.append((creds or {}).get("access_token")), ["x"])[1]
openai_oauth.valid_creds_for = lambda key: {"access_token": key + "-at", "account_id": ""}
set_accounts(main_on=False, plus_on=True)
openai_oauth.list_models()
check("fallback path uses the Plus account's token, not account 1's", backend_tokens == ["acc_plus-at"], backend_tokens)
openai_oauth._list_models_backend = _orig_backend
openai_oauth.valid_creds_for = _orig_for
codex_models.list_models = fake_codex_list

# ---- 8. codex_models really points the app-server at the folder it is given ----
import importlib  # noqa: E402
real_cm = importlib.reload(codex_models)
seen = {}


def _capture(argv, **kw):
    seen["home"] = (kw.get("env") or {}).get("CODEX_HOME")
    raise OSError("stop here")


real_cm.list_models(timeout=1, cli_path="codex-fake", popen_factory=_capture, codex_home=str(PLUS_HOME))
check("app-server spawned for an extra account gets that account's CODEX_HOME", seen.get("home") == str(PLUS_HOME), seen)
real_cm.list_models(timeout=1, cli_path="codex-fake", popen_factory=_capture)
check("without codex_home it keeps account 1's folder, as before", seen.get("home") == str(_FAKE_HOME / ".codex"), seen)
codex_models.list_models = fake_codex_list
openai_oauth.codex_models = codex_models

# ---- 9. /provider/models: a list kept for one account is not handed out for another ----
import main  # noqa: E402

main.openai_oauth.list_models = lambda key=None: list(PLUS if key == "acc_plus" else FREE)
main._PROV_MODELS_CACHE.clear()
set_accounts(main_on=True, plus_on=True)
r1 = asyncio.run(main.provider_models_index(GPT))
set_accounts(main_on=False, plus_on=True)
r2 = asyncio.run(main.provider_models_index(GPT))
check("server list on account 1", r1.get("models") == FREE, r1)
check("account 1 switched off: the 10-minute cache does not repeat its 3 models", r2.get("models") == PLUS
      and not r2.get("cached"), r2)
r3 = asyncio.run(main.provider_models_index(GPT))
check("...and the Plus list is kept for the Plus account", r3.get("models") == PLUS and r3.get("cached"), r3)

# ---- 10. the Models page picker asks again on every open ----
console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
picker = console[console.index("const ML = window.JavisModelList;"):console.index("Background model: the composer-style")]
check("the Models page picker asks the server on every open (refresh), not only when nothing is cached",
      "ML.refresh(pid)" in picker and "ids == null && ML" not in picker)
check("...and says it is loading while it asks", "loading ? wait" in picker)

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("All ChatGPT model list account tests passed.")
