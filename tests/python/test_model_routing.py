"""Usage order, per-card model/effort, several keys per provider, background order (0.350.0).

    python tests/run.py model_routing      (no network)

Spec: docs/dev/2026-10-model-routing-spec.md. The owner settled every rule on the Models page mockup; this file pins
the ones the server owns: migration from older settings, MAIN = top card, key rotation, the background order with each
provider's starting config and MAIN last, and the nearest effort level.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-routing-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config as cfgmod  # noqa: E402
import model_routing as R  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


# ---- 1. nearest effort (spec 2.3) -----------------------------------------------------------
check("level the model has runs as is", R.nearest_effort("high", ["low", "medium", "high"]) == "high")
check("missing top level runs at the nearest one", R.nearest_effort("xhigh", ["off", "low", "medium", "high"]) == "high")
check("ultra on a low/high model runs high", R.nearest_effort("ultra", ["low", "high"]) == "high")
check("a tie goes to the lower level", R.nearest_effort("medium", ["low", "high"]) == "low")
check("low on a high-only model runs high", R.nearest_effort("low", ["high"]) == "high")
check("off sends nothing even when the model always reasons", R.nearest_effort("off", ["low", "high"]) == "off")
check("a model without reasoning runs off", R.nearest_effort("high", []) == "off")
check("an unknown level counts as off", R.nearest_effort("max", ["high"]) == "off")

# ---- 2. migration (spec 4) -------------------------------------------------------------------
old = {"main": {"provider": "openai-oauth", "model": "gpt-5.5"}, "reasoning": "high",
       "groq_api_key": "gsk-1", "auxiliary": {"model": ""},
       "telegram": {"provider": "anthropic-cli", "model": "sonnet"}}
defaults = {"anthropic-cli": {"model": "", "reasoning": "off"}, "openai-oauth": {"model": "", "reasoning": "off"},
            "groq": {"model": "llama-3.3-70b-versatile", "reasoning": "off"}}
changed = R.migrate(old, connected_ids=["anthropic-cli", "openai-oauth", "groq"], defaults=defaults,
                    key_fields={"groq": "groq_api_key", "openai": "openai_api_key"}, telegram_chat_keys=["111", "222"])
check("migration reports a change", changed)
check("MAIN stays first, other connected cards follow", old["order"] == ["openai-oauth", "anthropic-cli", "groq"], old["order"])
check("MAIN keeps its model and effort", old["profiles"]["openai-oauth"] == {"model": "gpt-5.5", "reasoning": "high"})
check("other cards start on their provider's config", old["profiles"]["groq"]["model"] == "llama-3.3-70b-versatile")
check("an API key becomes account 1 of its card",
      len(old["accounts"]["groq"]) == 1 and old["account_keys"][old["accounts"]["groq"][0]["id"]] == "gsk-1")
check("an unset background model takes MAIN's starting config, not MAIN's chat model",
      old["auxiliary"]["provider"] == "openai-oauth" and old["auxiliary"]["model"] == "")
check("the shared Telegram pin becomes a pin of each known chat",
      old["telegram_chats"] == {"111": {"provider": "anthropic-cli", "model": "sonnet"},
                                "222": {"provider": "anthropic-cli", "model": "sonnet"}})
check("and the shared pin is cleared", not old["telegram"].get("provider"))
check("legacy main and reasoning mirror the top card", old["main"] == {"provider": "openai-oauth", "model": "gpt-5.5"}
      and old["reasoning"] == "high")
snap = json.dumps(old, sort_keys=True)
check("a second run changes nothing", not R.migrate(old, connected_ids=["groq", "openai"], defaults={}, key_fields={})
      and json.dumps(old, sort_keys=True) == snap)
kept = {"auxiliary": {"provider": "groq", "model": "qwen3-32b"}}
R.migrate(kept, connected_ids=["groq"], defaults={}, key_fields={})
check("an explicit background model is kept", kept["auxiliary"]["provider"] == "groq" and kept["auxiliary"]["model"] == "qwen3-32b")
legacy_alias = {"auxiliary": {"model": "haiku"}}
R.migrate(legacy_alias, connected_ids=[], defaults={}, key_fields={})
check("an old Claude alias as background model is kept (provider empty = Claude)",
      legacy_alias["auxiliary"].get("model") == "haiku" and not legacy_alias["auxiliary"].get("provider"))

# ---- 3. order and profiles ------------------------------------------------------------------
m = json.loads(snap)
R.set_profile(m, "groq", model="qwen3-32b", reasoning="xhigh")
check("a card's model and effort are saved together", R.profile(m, "groq") == {"model": "qwen3-32b", "reasoning": "xhigh"})
R.set_order(m, ["groq", "openai-oauth", "anthropic-cli"])
check("the top card becomes MAIN with its own model and effort",
      m["main"] == {"provider": "groq", "model": "qwen3-32b"} and m["reasoning"] == "xhigh")
check("the old MAIN keeps its model as a fallback", R.profile(m, "openai-oauth")["model"] == "gpt-5.5")
R.promote(m, "anthropic-cli", "opus")
check("composer choice moves that card to the top, others keep their order",
      m["order"] == ["anthropic-cli", "groq", "openai-oauth"] and m["main"]["model"] == "opus", m["order"])
R.set_profile(m, "anthropic-cli", reasoning="medium")
check("MAIN's effort mirrors legacy reasoning", m["reasoning"] == "medium")
R.add_to_order(m, "deepseek")
check("a new connection joins the END", m["order"][-1] == "deepseek")
R.drop_from_order(m, "anthropic-cli")
check("dropping MAIN makes the next card MAIN", m["order"][0] == "groq" and m["main"]["provider"] == "groq")
check("order() with connected ids hides cards that lost their login and appends new ones",
      R.order({"order": ["a", "b", "c"]}, ["c", "a", "d"]) == ["a", "c", "d"])

# ---- 4. accounts and rest -------------------------------------------------------------------
m = {"groq_api_key": "gsk-1"}
check("an old single key shows as account 1", [a["key"] for a in R.accounts(m, "groq", "groq_api_key")] == ["gsk-1"])
R.save_accounts(m, "groq", [{"id": "acc_a", "label": "Key 1", "enabled": True, "key": "gsk-1"},
                            {"id": "acc_b", "label": "Key 2", "enabled": True, "key": "gsk-2"}], "groq_api_key")
check("the old key field holds the first enabled key", m["groq_api_key"] == "gsk-1")
check("the first account is active", R.active_account(m, "groq", "groq_api_key")["id"] == "acc_a")
R.mark_rest("groq", "acc_a", seconds=600)
check("a resting account is skipped: key 2 runs", R.active_account(m, "groq", "groq_api_key")["id"] == "acc_b")
R.mark_rest("groq", "acc_b", seconds=600)
check("all resting: no usable account", R.usable_accounts(m, "groq", "groq_api_key") == [])
check("all resting: active falls back to the first enabled one (the provider then reports itself)",
      R.active_account(m, "groq", "groq_api_key")["id"] == "acc_a")
R.clear_rest("groq", "acc_a")
check("account 1 back from rest is used first again", R.active_account(m, "groq", "groq_api_key")["id"] == "acc_a")
R.mark_rest("groq", "acc_b", until=9e12, persist=True)
check("a stated reset time is written to disk", "groq:acc_b" in (cfgmod.STATE_DIR / "account_rest.json").read_text())
R.save_accounts(m, "groq", [{"id": "acc_b", "label": "Key 2", "enabled": True, "key": ""},
                            {"id": "acc_a", "label": "Key 1", "enabled": False, "key": ""}], "groq_api_key")
check("reordering keeps keys, the old field follows the first ENABLED account",
      m["groq_api_key"] == "gsk-2" and R.accounts(m, "groq", "groq_api_key")[1]["key"] == "gsk-1")
R.save_accounts(m, "groq", [{"id": "acc_b", "label": "Key 2", "enabled": True}], "groq_api_key")
check("a removed account's key is deleted", "acc_a" not in m["account_keys"])

# ---- 5. background order (spec 2.4.3) -------------------------------------------------------
m = {"order": ["anthropic-cli", "openai-oauth", "groq"],
     "profiles": {"anthropic-cli": {"model": "opus", "reasoning": "xhigh"},
                  "openai-oauth": {"model": "gpt-5.5", "reasoning": "high"},
                  "groq": {"model": "qwen3-32b", "reasoning": "off"}},
     "defaults": {"anthropic-cli": {"model": "", "reasoning": "off"}, "openai-oauth": {"model": "", "reasoning": "off"},
                  "groq": {"model": "llama-3.3-70b-versatile", "reasoning": "off"}},
     "auxiliary": {"provider": "anthropic-cli", "model": "haiku", "reasoning": "off"}}
check("a plan provider appears once when asked (quota belongs to the account)",
      [s["provider"] for s in R.background_chain(m, once=("anthropic-cli",))] == ["anthropic-cli", "openai-oauth", "groq"])
steps = R.background_chain(m)
check("background model first, fallbacks next, MAIN last",
      [s["provider"] for s in steps] == ["anthropic-cli", "openai-oauth", "groq", "anthropic-cli"], steps)
check("fallback steps run the provider's starting config, not the chat model",
      steps[1]["model"] == "" and steps[2]["model"] == "llama-3.3-70b-versatile")
check("MAIN last runs its starting config, not Opus", steps[3]["model"] == "" and steps[3]["step"] == "main")
m["auxiliary"] = {"provider": "groq", "model": "llama-3.3-70b-versatile"}
check("the same provider and model is tried once",
      [s["provider"] for s in R.background_chain(m)] == ["groq", "openai-oauth", "anthropic-cli"])
check("an assistant's own model can lead the chain",
      R.background_chain(m, first={"provider": "openai-oauth", "model": "gpt-5-codex"})[0]["model"] == "gpt-5-codex")

# ---- 6. Telegram pins ------------------------------------------------------------------------
m = {}
R.set_telegram_pin(m, "111", "groq", "qwen3-32b")
check("a pin belongs to one chat", R.telegram_pin(m, "111") == {"provider": "groq", "model": "qwen3-32b"}
      and R.telegram_pin(m, "222") == {})
R.set_telegram_pin(m, "111", "", "")
check("an empty provider removes the pin", R.telegram_pin(m, "111") == {})

# ---- 7. main.py: settings endpoint, chat route, key lookup ------------------------------------
import main  # noqa: E402

s = cfgmod.read_settings()
s["model"].update({"main": {"provider": "anthropic-cli", "model": "opus"}, "reasoning": "high",
                   "groq_api_key": "gsk-1", "routing_version": 0})
s["model"].pop("order", None)
cfgmod.write_settings(s)
s = cfgmod.read_settings()
main._routing_migrate(s)
cfgmod.write_settings(s)
mm = cfgmod.read_settings()["model"]
check("startup migration stores an order with MAIN first and the Groq card", mm["order"][0] == "anthropic-cli" and "groq" in mm["order"], mm.get("order"))
check("account keys are encrypted at rest", all(str(v).startswith("enc:") for v in json.loads(
    cfgmod.SETTINGS_PATH.read_text(encoding="utf-8"))["model"]["account_keys"].values()))

asyncio.run(main.settings_set("model", json.dumps({"accounts": {"provider": "groq", "items": [
    {"id": mm["accounts"]["groq"][0]["id"], "label": "Key 1", "enabled": True},
    {"label": "Key 2", "enabled": True, "key": "gsk-2"}]}})))
mm = cfgmod.read_settings()["model"]
check("Models page adds a second key", [a["key"] for a in R.accounts(mm, "groq", "groq_api_key")] == ["gsk-1", "gsk-2"])
asyncio.run(main.settings_set("model", json.dumps({"accounts": {"provider": "groq", "items": [
    {"label": "No key", "enabled": True}]}})))
check("a new account without a key is refused (nothing else changes)", [a["key"] for a in R.accounts(
    cfgmod.read_settings()["model"], "groq", "groq_api_key")] == ["gsk-1", "gsk-2"])
asyncio.run(main.settings_set("model", json.dumps({"accounts": {"provider": "groq", "items": []}})))
check("an empty list removes every key of the card", R.accounts(cfgmod.read_settings()["model"], "groq", "groq_api_key") == [])
asyncio.run(main.settings_set("model", json.dumps({"groq_api_key": "gsk-new"})))
mm = cfgmod.read_settings()["model"]
check("the old single key box creates account 1 again and re-adds the card",
      [a["key"] for a in R.accounts(mm, "groq", "groq_api_key")] == ["gsk-new"] and "groq" in mm["order"])

asyncio.run(main.settings_set("model", json.dumps({"profile": {"provider": "groq", "model": "qwen3-32b", "reasoning": "medium"}})))
asyncio.run(main.settings_set("model", json.dumps({"order": ["groq", "anthropic-cli"]})))
mm = cfgmod.read_settings()["model"]
check("saving an order makes the top card MAIN, legacy engine follows",
      mm["main"] == {"provider": "groq", "model": "qwen3-32b"} and mm.get("engine") == "groq" and mm["reasoning"] == "medium")
asyncio.run(main.settings_set("model", json.dumps({"reasoning": "low"})))
check("composer effort chip edits MAIN's card", R.profile(cfgmod.read_settings()["model"], "groq")["reasoning"] == "low")
asyncio.run(main.settings_set("model", json.dumps({"main": {"provider": "anthropic-cli", "model": "sonnet"}})))
mm = cfgmod.read_settings()["model"]
check("composer model chip moves Claude to the top", mm["order"][:2] == ["anthropic-cli", "groq"] and mm["main"]["model"] == "sonnet")

mcfg = cfgmod.read_settings()["model"]
acc = R.accounts(mcfg, "groq", "groq_api_key")[0]
d = main._provider_def("groq")
check("key lookup uses the card's active account", main._provider_key(mcfg, d) == "gsk-new")
asyncio.run(main.settings_set("model", json.dumps({"order": ["groq", "anthropic-cli"]})))
mcfg = cfgmod.read_settings()["model"]
check("chat runs MAIN when it can", main._chat_provider(mcfg)[0] == "groq")
# Which cards count as signed in depends on the machine (a `claude` binary); pin it so CI and laptops agree.
main._routing_connected_ids = lambda cfg: ["groq", "anthropic-cli"]
R.mark_rest("groq", acc["id"], seconds=600)
check("chat starts on the next card when every key of MAIN rests", main._chat_provider(mcfg)[0] == "anthropic-cli")
check("and that turn uses the next card's own effort", main._chat_reasoning(mcfg, "anthropic-cli")
      == R.profile(mcfg, "anthropic-cli")["reasoning"])
main._routing_connected_ids = lambda cfg: ["groq"]
check("a card that lost its login never takes over", main._chat_provider(mcfg)[0] == "groq")
R.clear_rest("groq", acc["id"])
check("the next turn goes back to MAIN", main._chat_provider(mcfg)[0] == "groq")

asyncio.run(main.settings_set("model", json.dumps({"auxiliary": {"reasoning": "high"}})))
mm = cfgmod.read_settings()["model"]
check("background effort saves without touching its model",
      mm["auxiliary"].get("reasoning") == "high" and "provider" in mm["auxiliary"])
asyncio.run(main.settings_set("model", json.dumps({"clear_key": "groq"})))
mm = cfgmod.read_settings()["model"]
check("disconnecting a card removes its keys and its place in the order",
      "groq" not in mm["order"] and not R.accounts(mm, "groq", "groq_api_key") and mm["main"]["provider"] == "anthropic-cli")

# ---- 8. keys never reach the browser ---------------------------------------------------------------
asyncio.run(main.settings_set("model", json.dumps({"groq_api_key": "gsk-secret-1234"})))
view = json.dumps(main.settings_get())
check("GET /settings has no account key in clear", "gsk-secret-1234" not in view and "account_keys" not in view)
check("GET /settings shows each account with its last 4 characters",
      main.settings_get()["model"]["accounts"]["groq"][0]["key"] == "••••1234")

# ---- 9. what the Models page draws -------------------------------------------------------------------
asyncio.run(main.settings_set("model", json.dumps({"order": ["groq", "anthropic-cli"]})))
asyncio.run(main.settings_set("model", json.dumps({"auxiliary": {"provider": "anthropic-cli", "model": "haiku"}})))
mcfg = cfgmod.read_settings()["model"]
provs = [{"id": "anthropic-cli", "configured": True, "cli_found": True}, {"id": "groq", "configured": True},
         {"id": "gemini", "configured": False}, {"id": "openai-oauth", "configured": True, "cli_found": False}]
v = main._routing_view(mcfg, provs)
check("the page's order lists signed-in cards only, MAIN first", v["order"] == ["groq", "anthropic-cli"], v["order"])
check("each card in the order carries its model and effort", set(v["profiles"]) == {"groq", "anthropic-cli"})
check("chat in use is MAIN when it can run", v["chat_in_use"] == "groq")
check("background in use is the background model", v["bg_in_use"]["step"] == "background"
      and v["bg_in_use"]["model"] == "haiku", v["bg_in_use"])
check("API cards with a key list are named for the page", "groq" in v["multi_key"] and "openai-compat" not in v["multi_key"])
acc = R.accounts(mcfg, "groq", "groq_api_key")[0]
R.mark_rest("groq", acc["id"], seconds=600)
check("a resting MAIN shows chat on the next card", main._routing_view(mcfg, provs)["chat_in_use"] == "anthropic-cli")
R.clear_rest("groq", acc["id"])

print()
if _fails:
    print(f"ĐỎ {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("Tất cả xanh.")
