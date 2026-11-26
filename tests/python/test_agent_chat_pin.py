"""Each assistant keeps its own chat model pin (owner, 26/11/2026).

    python tests/run.py agent_chat_pin      (no network, no model call)

Owner: "mỗi cái agent sẽ có ghim cài đặt riêng nếu mà người dùng chủ động thay đổi khi chat", "đổi ở khung chat với
agent thì cũng không đổi ở chạy nền", "nếu mà không chủ động ... thì nó sẽ mặc định ghim chat của agent khi mà vào".

Simulated:

  1. An assistant's chat with no pick runs the model in the assistant's settings.
  2. A model picked on the chip of one chat with it becomes that assistant's chat pin: a new chat with it, and an old
     one never picked in, open on that model. The window picked in keeps its own pick (windows never move each other).
  3. Background work keeps the model in the assistant's settings: a Kanban job, a dedicated bot, the bot's effort.
     The assistant's file is never rewritten.
  4. Changing the assistant's settings moves background work, not the chats on its chat pin.
  5. "Follow the model set on the assistant" clears the window's pick and the chat pin.
  6. The pin is per assistant and per brain; a normal chat, a Javis Core chat and Javis Gate do not touch it; deleting
     the assistant drops it.
  7. The chat's meta tells the chip where the model comes from; the chip and its words follow.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agent-chat-pin-")
BR = Path(tempfile.mkdtemp(prefix="javis-agent-chat-pin-brain-")).resolve()
BR2 = Path(tempfile.mkdtemp(prefix="javis-agent-chat-pin-brain2-")).resolve()
LAN = "---\nname: Lan\nrole: Bán hàng\nmodel: gpt-5.5\nmodel_provider: openai-oauth\nreasoning: high\n---\nBạn là Lan.\n"
for root in (BR, BR2):
    (root / "agents").mkdir()
    (root / "agents" / "lan.md").write_text(LAN, encoding="utf-8", newline="\n")
(BR / "agents" / "minh.md").write_text("---\nname: Minh\nrole: Kho\nreasoning: low\n---\nBạn là Minh.\n",
                                       encoding="utf-8", newline="\n")

import main  # noqa: E402
import config as cfgmod  # noqa: E402
import javis_core  # noqa: E402
import model_routing  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:400]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


main._routing_connected_ids = lambda cfg: ["anthropic-cli", "openai-oauth", "groq"]
MCFG = {"main": {"provider": "anthropic-cli", "model": "opus"}, "reasoning": "medium",
        "order": ["anthropic-cli", "openai-oauth", "groq"], "groq_api_key": "gsk_test",
        "profiles": {"anthropic-cli": {"model": "opus", "reasoning": "medium"},
                     "openai-oauth": {"model": "gpt-5.5", "reasoning": "xhigh"},
                     "groq": {"model": "qwen3-32b", "reasoning": "low"}}}
cfgmod.update_settings({"model": json.loads(json.dumps(MCFG))})
main._PIN_LIMITED.clear()
main._SIGNED_OUT.clear()

store = main.get_store()
client = TestClient(main.app, base_url="http://127.0.0.1:8080")
H = {"origin": "http://127.0.0.1:8080"}
B, B2 = str(BR), str(BR2)


def m():
    return cfgmod.read_settings()["model"]


def turn(sid, brain=B):
    """(provider, model) the next dashboard turn of `sid` runs on, as the chat turn decides it."""
    r = store.get_session(sid) or {}
    r = {**r, "brain": r.get("brain") or brain}
    run = main._chat_provider_for_session(m(), r)
    return run[0], run[3]


def pick(sid, prov, model=""):
    return client.post(f"/sessions/{sid}/model", data={"provider": prov, "model": model}, headers=H)


def meta(sid):
    return client.get(f"/sessions/{sid}/meta").json()


def new_chat(slug="lan", brain=B):
    r = client.post("/sessions/new", data={"brain": brain, "channel": f"agent:{slug}"}, headers=H)
    return r.json()["id"]


def chat_pin(slug="lan", brain=B):
    return model_routing.agent_chat_pin(m(), main._agent_chat_key(brain, slug))


# ============================================================
# 1. No pick: the model in the assistant's settings
# ============================================================
old = new_chat()
check("an assistant's chat with no pick runs the model in its settings", turn(old) == ("openai-oauth", "gpt-5.5"),
      turn(old))
check("the chip is told it is the assistant's settings", meta(old).get("pin_source") == "agent", meta(old))
minh = new_chat("minh")
check("an assistant on 'Default' follows the main model", turn(minh)[0] == "anthropic-cli", turn(minh))
check("...and the chip says so", meta(minh).get("pin_source") == "" and not meta(minh).get("pinned_provider"),
      meta(minh))

# ============================================================
# 2. A pick in one chat becomes the assistant's chat pin
# ============================================================
a = new_chat()
r = pick(a, "groq", "qwen3-32b")
check("picking a model in an assistant's chat is accepted with the assistant's scope",
      r.status_code == 200 and r.json().get("scope") == "agent", r.text)
check("that window runs the pick", turn(a) == ("groq", "qwen3-32b"), turn(a))
check("the pick is kept as the assistant's chat pin", chat_pin() == {"provider": "groq", "model": "qwen3-32b"},
      chat_pin())
check("the chip of that window shows its own pick", meta(a).get("pin_source") == "window", meta(a))
fresh = new_chat()
check("a NEW chat with the assistant opens on its chat pin", turn(fresh) == ("groq", "qwen3-32b"), turn(fresh))
check("...and the chip names the chat pin", meta(fresh).get("pin_source") == "agent_chat"
      and meta(fresh).get("pinned_provider") == "groq", meta(fresh))
check("an OLD chat never picked in follows the chat pin too", turn(old) == ("groq", "qwen3-32b"), turn(old))
b = new_chat()
pick(b, "anthropic-cli", "sonnet")
check("a later pick in another window moves the chat pin", chat_pin() == {"provider": "anthropic-cli",
                                                                          "model": "sonnet"}, chat_pin())
check("the first window keeps its own pick (windows never move each other)", turn(a) == ("groq", "qwen3-32b"),
      turn(a))
check("chats with no pick of their own follow the latest chat pin",
      turn(fresh) == ("anthropic-cli", "sonnet") and turn(old) == ("anthropic-cli", "sonnet"), (turn(fresh), turn(old)))
check("another assistant's chats are not touched", turn(minh)[0] == "anthropic-cli" and not chat_pin("minh"),
      (turn(minh), chat_pin("minh")))
other_brain = new_chat("lan", B2)
check("the same assistant name in another brain keeps its own setting",
      turn(other_brain, B2) == ("openai-oauth", "gpt-5.5") and not chat_pin("lan", B2), turn(other_brain, B2))

# ============================================================
# 3. Background work keeps the model in the assistant's settings
# ============================================================
check("the assistant's file is not rewritten by a pick in its chat",
      (BR / "agents" / "lan.md").read_text(encoding="utf-8") == LAN)
saved_persona = main._agent_persona
main._agent_persona = lambda root, slug, key=None: "persona" if slug in ("lan", "minh") else ""
try:
    check("a Kanban job, reminder or loop of the assistant runs the model in its settings",
          main._agent_job_spec(B, "lan") == {"provider": "openai-oauth", "model": "gpt-5.5", "reasoning": "high"},
          main._agent_job_spec(B, "lan"))
finally:
    main._agent_persona = saved_persona
bot = {"agent": {"brain": B, "slug": "lan"}}
check("a dedicated bot of the assistant runs the model in its settings",
      main._chat_provider_bot(m(), bot)[:1] == ("openai-oauth",) and main._chat_provider_bot(m(), bot)[3] == "gpt-5.5",
      main._chat_provider_bot(m(), bot))
check("the bot thinks at the assistant's own level on that model",
      main._bot_turn_reasoning(m(), "openai-oauth", bot) == "high")
check("the Models page is not touched: main model and usage order",
      m()["main"]["provider"] == "anthropic-cli" and m()["order"] == ["anthropic-cli", "openai-oauth", "groq"], m())

# ============================================================
# 4. The assistant's settings move background work, not chats on the chat pin
# ============================================================
(BR / "agents" / "lan.md").write_text(LAN.replace("model: gpt-5.5\nmodel_provider: openai-oauth",
                                                  "model: qwen3-32b\nmodel_provider: groq"),
                                      encoding="utf-8", newline="\n")
check("background work follows the new setting", main._chat_provider_bot(m(), bot)[0] == "groq",
      main._chat_provider_bot(m(), bot))
check("chats on the chat pin stay on it", turn(fresh) == ("anthropic-cli", "sonnet"), turn(fresh))

# ============================================================
# 5. "Follow the model set on the assistant" clears both
# ============================================================
r = pick(fresh, "")
check("following the assistant's settings is accepted", r.status_code == 200 and r.json().get("scope") == "agent",
      r.text)
check("...clears the assistant's chat pin", not chat_pin(), chat_pin())
check("...and that chat runs the model in the assistant's settings again", turn(fresh) == ("groq", "qwen3-32b")
      and meta(fresh).get("pin_source") == "agent", (turn(fresh), meta(fresh)))
check("chats with no pick of their own go back to the settings too", turn(old)[0] == "groq", turn(old))
check("a window with its own pick keeps it", turn(b) == ("anthropic-cli", "sonnet"), turn(b))
(BR / "agents" / "lan.md").write_text(LAN, encoding="utf-8", newline="\n")

# ============================================================
# 6. Who does not touch the chat pin
# ============================================================
web = store.create_session(brain=B, engine="cli", channel="web")
pick(web, "groq", "qwen3-32b")
check("a pick in a normal chat pins that chat only", turn(web)[0] == "groq" and not m().get("agent_chats"),
      m().get("agent_chats"))
core = store.create_session(brain=B, engine="cli", channel=javis_core.CHANNEL)
r = pick(core, "openai-oauth", "gpt-5.5")
check("a pick in a Javis Core chat still pins Javis Core", r.json().get("scope") == "core"
      and main._core_pin(m()) == {"provider": "openai-oauth", "model": "gpt-5.5"} and not m().get("agent_chats"),
      (r.text, m().get("agent_chats")))
pick(core, "")
gate = new_chat()
out = asyncio.run(main._pin_chat_model(gate, "groq", "qwen3-32b"))
check("Javis Gate picking a model pins that conversation only, not the assistant",
      out.get("ok") and turn(gate)[0] == "groq" and not chat_pin(), (out, chat_pin()))
pick(a, "openai-oauth", "gpt-old")
healed = new_chat()
main._heal_agent_chat_pin(store.get_session(healed), m(), B, "gpt-5.5")
check("Codex self-heal fixes a ChatGPT model that left the catalog in the assistant's chat pin",
      chat_pin() == {"provider": "openai-oauth", "model": "gpt-5.5"}, chat_pin())
pick(a, "groq", "qwen3-32b")
main._heal_agent_chat_pin(store.get_session(a), m(), B, "gpt-5.5")
check("...but not from a window running its own pick", chat_pin() == {"provider": "groq", "model": "qwen3-32b"},
      chat_pin())
check("the chat pin is back after a pick", bool(chat_pin()))
r = client.post("/agents/delete", data={"slug": "lan", "brain": B}, headers=H)
check("deleting the assistant drops its chat pin", r.status_code == 200 and not chat_pin(), (r.text, chat_pin()))
(BR / "agents" / "lan.md").write_text(LAN, encoding="utf-8", newline="\n")
check("an assistant made again with the same name starts on its own settings", turn(new_chat())[0] == "openai-oauth")

# ============================================================
# 7. The chip
# ============================================================
mp = (ROOT / "dashboard" / "model-picker.js").read_text(encoding="utf-8")
check("the chip reads where the model of an assistant's chat comes from", 'pinSource = (d && d.pin_source) || "";' in mp)
check("the chip explains the assistant's chat pin and the assistant's settings apart",
      '"mpick.agent_chat_pin_title"' in mp and '"mpick.agent_model_title"' in mp)
check("'Follow the model set on the assistant' shows only when the chat runs on something else",
      'sessionPin && (pinSource === "window" || pinSource === "agent_chat")' in mp)
check("after following, the chip reads the chat again (it shows the assistant's model, not the main one)",
      "await loadState(); await loadSessionPin(); renderBar(); close();" in mp)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    check(f"{lang}: both new chip lines exist and use no long dash",
          all(d.get(k) and "\u2014" not in d[k] and "\u2013" not in d[k]
              for k in ("mpick.agent_chat_pin_title", "mpick.agent_model_title")))

print()
if fails:
    print(f"{len(fails)} FAIL")
    raise SystemExit(1)
print("all ok")
