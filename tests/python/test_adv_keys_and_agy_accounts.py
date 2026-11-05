"""Advanced API key (several gateways on the Anthropic-compatible route) and extra Antigravity accounts.

    python tests/run.py adv_keys_and_agy_accounts     (no network, no real `agy`)

Owner, 05/11/2026 (approved design docs/design/models-page-redesign.html):
1. "Advanced API key": plug in keys of different sellers, each with its own address, used through the
   Anthropic-compatible route, without naming that route on screen. Every existing code path reads the legacy fields
   `anthropic_compat_base/_key/_models`, so the active gateway is mirrored there; a gateway out of quota rests and
   the next one takes over.
2. "A way to rotate Antigravity": an extra Google account runs `agy` with its own HOME and file storage (Linux only).
"""
from _paths import ROOT, SERVER  # noqa: F401
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-adv-")

import config as cfgmod  # noqa: E402
import model_routing  # noqa: E402
import adv_keys  # noqa: E402
import plan_accounts  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---- 1. an old machine: one gateway in the legacy fields reads as gateway 1 ----
m = {"anthropic_compat_base": "https://api.moonshot.ai/anthropic/v1", "anthropic_compat_key": "sk-old-1111",
     "anthropic_compat_models": ["kimi-k2"]}
g = adv_keys.gateways(m)
check("legacy gateway reads as gateway 1", len(g) == 1 and g[0]["id"] == adv_keys.LEGACY_ID
      and g[0]["base"] == "https://api.moonshot.ai/anthropic" and g[0]["key"] == "sk-old-1111", g)
check("its name is the host people recognise", g[0]["label"] == "api.moonshot.ai")

# ---- 2. add a second gateway: the first stays active, keys go to the encrypted store ----
m = {}
a = adv_keys.add(m, "Kimi", "https://api.moonshot.ai/anthropic", "sk-kimi-4c1e", ["kimi-k2"])
b = adv_keys.add(m, "MiniMax", "https://api.minimax.io/anthropic/v1/messages", "sk-mm-90ab", ["MiniMax-M2"])
check("two gateways, in the order added", [x["label"] for x in adv_keys.gateways(m)] == ["Kimi", "MiniMax"])
check("keys live in account_keys, never in the list", "key" not in m["adv_keys"][0]
      and m["account_keys"][a["id"]] == "sk-kimi-4c1e")
check("the address is normalised (/v1/messages dropped)", adv_keys.gateways(m)[1]["base"] == "https://api.minimax.io/anthropic")
check("the first gateway is mirrored into the legacy fields", m["anthropic_compat_base"] == "https://api.moonshot.ai/anthropic"
      and m["anthropic_compat_key"] == "sk-kimi-4c1e" and m["anthropic_compat_models"] == ["kimi-k2"])
v = adv_keys.view(m)
check("the page sees the last 4 characters only", v[0]["key"] == "••••4c1e" and "sk-kimi" not in str(v), v)

# ---- 3. out of quota: the gateway rests, the next one takes over, its model follows ----
model_routing.set_profile(m, adv_keys.PROVIDER, model="kimi-k2")
switched = adv_keys.rest_and_rotate(m, "sk-kimi-4c1e", 600)
check("quota on Kimi switches to MiniMax", switched and m["anthropic_compat_key"] == "sk-mm-90ab"
      and m["anthropic_compat_base"] == "https://api.minimax.io/anthropic")
check("the card's model moves to a model MiniMax lists", model_routing.profile(m, adv_keys.PROVIDER)["model"] == "MiniMax-M2")
check("the resting gateway shows until when", adv_keys.view(m)[0]["resting_until"] > time.time())
adv_keys.rest_and_rotate(m, "sk-mm-90ab", 600)
check("all gateways resting: no active gateway (the route is not ready)", adv_keys.active(m) is None)
model_routing.clear_rest(adv_keys.PROVIDER, a["id"])
model_routing.clear_rest(adv_keys.PROVIDER, b["id"])

# ---- 4. the page's list: order, on/off, names, removal ----
adv_keys.save_list(m, [{"id": b["id"]}, {"id": a["id"], "enabled": False, "label": "Kimi cũ"}])
gs = adv_keys.gateways(m)
check("reorder and switch off", [x["id"] for x in gs] == [b["id"], a["id"]] and gs[1]["enabled"] is False
      and gs[1]["label"] == "Kimi cũ")
check("the new first gateway is mirrored", m["anthropic_compat_key"] == "sk-mm-90ab")
adv_keys.save_list(m, [{"id": b["id"]}])
check("a gateway missing from a stale page is kept", len(adv_keys.gateways(m)) == 2)
adv_keys.save_list(m, [{"id": b["id"]}], removed=[a["id"]])
check("a removed gateway goes with its key", len(adv_keys.gateways(m)) == 1 and a["id"] not in m["account_keys"])
check("edit keeps the key when none is typed", adv_keys.update(m, b["id"], label="MM", base=None, key="", models=None)
      and adv_keys.gateways(m)[0]["key"] == "sk-mm-90ab" and adv_keys.gateways(m)[0]["label"] == "MM")

# ---- 5. server wiring: settings view, route readiness, quota rotation on disk ----
with cfgmod._SETTINGS_LOCK:
    cfg = cfgmod.read_settings()
    adv_keys.add(cfg["model"], "Kimi", "https://api.moonshot.ai/anthropic", "sk-kimi-4c1e", ["kimi-k2"])
    adv_keys.add(cfg["model"], "MiniMax", "https://api.minimax.io/anthropic", "sk-mm-90ab", ["MiniMax-M2"])
    cfgmod.write_settings(cfg)
mc = cfgmod.read_settings()["model"]
view = next(p for p in main._providers_view(cfgmod.read_settings()) if p["id"] == adv_keys.PROVIDER)
check("the card is connected and named Advanced API key, not Anthropic Compatible",
      view["configured"] is True and "Anthropic" not in view["label"], view["label"])
check("route ready while a gateway can run", main._route_ready(mc, adv_keys.PROVIDER) is True)
main._note_api_limit(mc, adv_keys.PROVIDER, "sk-kimi-4c1e", "429 rate limit", 600)
mc2 = cfgmod.read_settings()["model"]
check("a quota error in chat moves the saved route to the next gateway", mc2["anthropic_compat_key"] == "sk-mm-90ab")
nxt = main._chat_next_route(mc, adv_keys.PROVIDER, "sk-kimi-4c1e", [])
check("the same turn reruns on the next gateway before the next card",
      nxt.get("route", ("",))[0] == adv_keys.PROVIDER and nxt["route"][2] == "sk-mm-90ab", nxt)
src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("the settings page never receives gateway keys", 'safe["model"].pop(adv_keys.FIELD, None)' in src
      and 'safe["model"].pop("account_keys", None)' in src)
check("Disconnect forgets every gateway", "adv_keys.save_list(m, [], removed=[g[\"id\"] for g in adv_keys.gateways(m)])" in src)

# ---- 6. Antigravity: extra Google accounts, Linux only ----
linux = sys.platform.startswith("linux")
check("Antigravity can hold extra accounts on Linux only", plan_accounts.available("antigravity-cli") == linux)
if linux:
    folder = plan_accounts.home("antigravity-cli", "acc_agy1")
    env = plan_accounts.env_for("antigravity-cli", folder)
    check("an extra account runs agy with its own HOME and file storage",
          env == {"HOME": str(folder), "GEMINI_FORCE_FILE_STORAGE": "true"}, env)
    check("not signed in before agy writes its token", plan_accounts.signed_in("antigravity-cli", "acc_agy1") is False)
    tok = folder / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    tok.parent.mkdir(parents=True, exist_ok=True)
    tok.write_text("x")
    check("signed in once the token file exists", plan_accounts.signed_in("antigravity-cli", "acc_agy1") is True)

    class _E:
        pass
    e = _E()
    plan_accounts.use(e, "antigravity-cli", "acc_agy1")
    check("the engine is pointed at the account's HOME", getattr(e, "agy_home", None) == str(folder))
    plan_accounts.use(e, "antigravity-cli", plan_accounts.MAIN)
    check("account 1 keeps the machine's own login", e.agy_home is None)
agy_src = (Path(SERVER) / "antigravity_cli.py").read_text(encoding="utf-8")
check("the agy process gets HOME and file storage for an extra account",
      'getattr(self, "agy_home", None)' in agy_src and '_env["GEMINI_FORCE_FILE_STORAGE"] = "true"' in agy_src)
check("the chat turn picks the Antigravity account to run",
      '_turn_acc["antigravity-cli"] = _plan_account_apply(acli, "antigravity-cli", mcfg)' in src)

print()
if fails:
    print(f"ĐỎ {len(fails)} mục")
    raise SystemExit(1)
print("Tất cả xanh.")
