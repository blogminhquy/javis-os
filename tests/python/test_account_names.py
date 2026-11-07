"""Every account gets a name at its first sign-in (owner 07/11/2026).

    python tests/run.py account_names      (no network, no CLI needed)

"When signing in to a provider for the first time, also ask for the account's name, so accounts are never mixed up."
The Models page asks for the name next to the sign-in button and saves it through POST /settings section=model:
- an API card's first key travels with `key_label`, so it is not left as a bare "Key 1";
- a plan card's name is account 1's label in `accounts`, on every plan card, also Antigravity where this machine holds
  no extra account (off Linux), so the card can be named anyway.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-acname-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["HOME"] = str(_TMP / "home")
os.environ["USERPROFILE"] = str(_TMP / "home")
for v in ("CODEX_HOME", "GROK_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(v, None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config as cfgmod  # noqa: E402
import model_routing  # noqa: E402
import plan_accounts  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def post(patch):
    return asyncio.run(main.settings_set(section="model", data=json.dumps(patch)))


def model():
    return cfgmod.read_settings().get("model") or {}


# ---- 1. an API card's first key, connected with a name ----
post({"groq_api_key": "gsk_first_1111", "key_label": "  Groq công việc  "})
acc = model_routing.accounts(model(), "groq", "groq_api_key")
check("the first key is saved under the typed name, trimmed", len(acc) == 1 and acc[0]["label"] == "Groq công việc", acc)
check("the key itself is saved and the card joins the usage order",
      acc and acc[0]["key"] == "gsk_first_1111" and "groq" in model_routing.stored_order(model()), model().get("order"))

# ---- 2. without a name the old default stays ----
post({"deepseek_api_key": "sk-ds-2222"})
acc = model_routing.accounts(model(), "deepseek", "deepseek_api_key")
check("no name typed: the key reads as Key 1, as before", len(acc) == 1 and acc[0]["label"] == "Key 1", acc)

# ---- 3. a very long name is cut, not refused ----
post({"openrouter_key": "sk-or-3333", "key_label": "x" * 200})
acc = model_routing.accounts(model(), "openrouter", "openrouter_key")
check("a name longer than 60 characters is cut to 60", acc and len(acc[0]["label"]) == 60, acc)

# ---- 4. a plan card's account 1 is named through its account list ----
post({"accounts": {"provider": "openai-oauth", "items": [{"id": "main", "label": "ChatGPT Pro cá nhân", "enabled": True}]}})
v = plan_accounts.view(model(), "openai-oauth")
check("ChatGPT: account 1 carries the typed name", v and v[0]["main"] and v[0]["label"] == "ChatGPT Pro cá nhân", v)

# Antigravity holds extra accounts only on Linux, yet its card can always be named.
_goc = plan_accounts.available
try:
    plan_accounts.available = lambda p: p != "antigravity-cli" and p in plan_accounts.KIND
    post({"accounts": {"provider": "antigravity-cli", "items": [{"id": "main", "label": "Gmail công việc", "enabled": True}]}})
finally:
    plan_accounts.available = _goc
v = plan_accounts.view(model(), "antigravity-cli")
check("Antigravity off Linux: account 1 can still be named", v and v[0]["label"] == "Gmail công việc", v)

# Renaming keeps the others and their order.
m = model()
plan_accounts.add(m, "grok-cli", "acc2", "Grok 2")
cfgmod.update_settings({"model": {"accounts": m["accounts"]}})
post({"accounts": {"provider": "grok-cli", "items": [
    {"id": "main", "label": "Grok chính", "enabled": True}, {"id": "acc2", "label": "Grok 2", "enabled": True}]}})
v = plan_accounts.view(model(), "grok-cli")
check("renaming account 1 keeps account 2 and the order",
      [(a["id"], a["label"]) for a in v] == [("main", "Grok chính"), ("acc2", "Grok 2")], v)

# The settings view hands the names to the page.
pa = ((main.settings_get().get("model") or {}).get("accounts") or {}).get("openai-oauth") or []
check("GET /settings hands account 1's name to the Models page", pa and pa[0]["label"] == "ChatGPT Pro cá nhân", pa)

if fails:
    print(f"\n{len(fails)} FAIL")
    sys.exit(1)
print("\nOK - test_account_names: all pass")
