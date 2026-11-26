"""Model and effort stay where the owner set them (25/11/2026).

    python tests/run.py model_effort_isolation      (no network, no model call)

Owner: "khi agent hay chatbot làm việc tự động dù tự làm hay làm việc trong team thì sử dụng đúng model và mức suy nghĩ
theo cài đặt của agent", "khi chat riêng với agent thì phải sử dụng model và mức suy nghĩ theo cửa sổ chat của chat đó",
"model và suy nghĩ của các cửa sổ chat không nhảy chồng chéo sang cửa sổ chat khác", "khi 1 kênh model bị limit thì
suy nghĩ sử dụng theo cài đặt ở model", "cài đặt ưu tiên của các kênh model không được tự ý đảo thứ tự".

Simulated, in order of the owner's five points:

  1. Automatic work: a team turn runs at the member's own level on Claude, ChatGPT (Codex), Grok Build, Antigravity and
     API engines; a workflow step on an API model carries the assistant's level; a dedicated bot thinks at its Agent's
     level; a Codex / Grok / Antigravity link of the background chain gets its effort.
  2. An assistant's chat: the window's own effort wins over the assistant's setting, and setting it never rewrites the
     assistant's file.
  3. Two windows: the model and the effort of one never move the other, nor the Models page.
  4. A resting card: the turn runs on the next card at that card's own setting, whatever the window, the assistant or
     the team member chose.
  5. Picking a model or an effort in a chat never reorders the usage order; the composer no longer rewrites MAIN.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-effort-iso-")
BR = Path(tempfile.mkdtemp(prefix="javis-effort-iso-brain-")).resolve()
(BR / "agents").mkdir()
(BR / "agents" / "lan.md").write_text("---\nname: Lan\nrole: Bán hàng\nreasoning: high\n---\nBạn là Lan.\n",
                                      encoding="utf-8", newline="\n")
(BR / "agents" / "minh.md").write_text("---\nname: Minh\nrole: Kho\nmodel: gpt-5.5\nmodel_provider: openai-oauth\n"
                                       "reasoning: low\n---\nBạn là Minh.\n", encoding="utf-8", newline="\n")

import main  # noqa: E402
import aux_engine  # noqa: E402
import config as cfgmod  # noqa: E402
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


def reset():
    main._PIN_LIMITED.clear()
    main._SIGNED_OUT.clear()


store = main.get_store()
client = TestClient(main.app, base_url="http://127.0.0.1:8080")
H = {"origin": "http://127.0.0.1:8080"}
B = str(BR)


def row(sid):
    return store.get_session(sid) or {}


def turn(sid):
    """(provider, effort) the next dashboard turn of `sid` runs on, as _do_turn decides it."""
    m = cfgmod.read_settings()["model"]
    r = {**row(sid), "brain": row(sid).get("brain") or B}
    prov = main._chat_provider_for_session(m, r)[0]
    return prov, main._session_reasoning(m, r, prov)


# ============================================================
# 3. Two chat windows never move each other
# ============================================================
reset()
a = store.create_session(brain=B, engine="cli", channel="web")
b = store.create_session(brain=B, engine="cli", channel="web")
order_before = list(cfgmod.read_settings()["model"]["order"])
r = client.post(f"/sessions/{a}/model", data={"provider": "openai-oauth", "model": "gpt-5.5", "brain": B}, headers=H)
check("window A pins ChatGPT", r.status_code == 200, r.text)
r = client.post(f"/sessions/{a}/reasoning", data={"level": "ultra", "brain": B}, headers=H)
check("window A sets its own effort", r.status_code == 200 and r.json().get("pinned_reasoning") == "ultra", r.text)
check("window A runs ChatGPT at its own effort", turn(a) == ("openai-oauth", "ultra"), turn(a))
check("window B keeps MAIN and MAIN's effort", turn(b) == ("anthropic-cli", "medium"), turn(b))
r = client.post(f"/sessions/{b}/reasoning", data={"level": "low", "brain": B}, headers=H)
check("window B's effort does not touch window A", turn(a) == ("openai-oauth", "ultra") and turn(b)[1] == "low",
      (turn(a), turn(b)))
s_now = cfgmod.read_settings()["model"]
check("the Models page settings did not move: order, MAIN, MAIN's effort, each card's effort",
      s_now["order"] == order_before and s_now["main"]["provider"] == "anthropic-cli" and s_now.get("reasoning") == "medium"
      and model_routing.profile(s_now, "openai-oauth")["reasoning"] == "xhigh", s_now)
r = client.post(f"/sessions/{a}/reasoning", data={"level": "bogus"}, headers=H)
check("an unknown level is refused", r.status_code == 400, r.text)
r = client.post(f"/sessions/{a}/reasoning", data={"level": ""}, headers=H)
check("an empty level clears the window's effort: ChatGPT's card setting again", turn(a) == ("openai-oauth", "xhigh"),
      turn(a))
r = client.post("/sessions/new-window-x/reasoning", data={"level": "high", "brain": B}, headers=H)
check("an effort picked before the first message creates the chat row (as the model pin does)",
      r.status_code == 200 and row("new-window-x").get("pinned_reasoning") == "high", r.text)
meta = client.get(f"/sessions/{b}/meta").json()
check("the chat meta tells the composer the window's effort", meta.get("pinned_reasoning") == "low"
      and (meta.get("route") or {}).get("reasoning") == "low", meta)

# ============================================================
# 2. An assistant's chat: the window first, then the assistant
# ============================================================
lan = store.create_session(brain=B, engine="cli", channel="agent:lan")
lan2 = store.create_session(brain=B, engine="cli", channel="agent:lan")
check("an assistant's chat starts at the assistant's own level", turn(lan) == ("anthropic-cli", "high"), turn(lan))
client.post(f"/sessions/{lan}/reasoning", data={"level": "low"}, headers=H)
check("its window's effort wins in that window", turn(lan)[1] == "low", turn(lan))
check("another chat with the same assistant keeps the assistant's level", turn(lan2)[1] == "high", turn(lan2))
check("the assistant's file is not rewritten", "reasoning: high" in (BR / "agents" / "lan.md").read_text(encoding="utf-8"))
minh = store.create_session(brain=B, engine="cli", channel="agent:minh")
store.set_pinned_model(minh, "openai-oauth", "gpt-5.5")   # an agent chat pins its agent's model
check("an assistant on its own model runs that model at its own level", turn(minh) == ("openai-oauth", "low"), turn(minh))

# ============================================================
# 4. A resting card: the stand-in card's own setting
# ============================================================
reset()
main._PIN_LIMITED["openai-oauth"] = time.time() + 3600
client.post(f"/sessions/{a}/reasoning", data={"level": "ultra"}, headers=H)
check("window A's ChatGPT rests: the turn runs on MAIN at MAIN's own effort, not the window's ultra",
      turn(a) == ("anthropic-cli", "medium"), turn(a))
check("an assistant whose model rests runs on MAIN at MAIN's setting, not its own low",
      turn(minh) == ("anthropic-cli", "medium"), turn(minh))
reset()
main._PIN_LIMITED["anthropic-cli"] = time.time() + 3600
check("MAIN rests: an unpinned window moves DOWN the order to ChatGPT at ChatGPT's own effort",
      turn(b)[0] == "openai-oauth" and turn(b)[1] == "xhigh", turn(b))
check("an assistant following MAIN moves down too, at the stand-in card's effort", turn(lan2) == ("openai-oauth", "xhigh"),
      turn(lan2))
m_now = cfgmod.read_settings()["model"]
check("a resting card changes nothing saved: the order stays", m_now["order"] == order_before, m_now["order"])
reset()
check("the quota back: window A is on its own ChatGPT pin and effort again", turn(a) == ("openai-oauth", "ultra"), turn(a))

# ============================================================
# 1. Automatic work keeps the assistant's model and level
# ============================================================
m = cfgmod.read_settings()


class _Codex:
    def __init__(self, model="gpt-5.5"):
        self.model, self.extra_config = model, []


class _Grok:
    effort = None
    model = "grok-4"


class _Api:
    reasoning = "off"


class _Claude:
    effort = None


saved_codex_effort, saved_lui = main._codex_effort, main._co_effort_lui
main._codex_effort = lambda model, level: {"low": "low", "medium": "medium", "high": "high", "xhigh": "xhigh",
                                           "ultra": "xhigh"}.get(level, "")
main._co_effort_lui = lambda mod, level: ["--effort", {"ultra": "max"}.get(level, level)]
try:
    cx = _Codex()
    out = main._team_reasoning(cx, "low", "việc", "openai-oauth")
    check("team turn on ChatGPT takes the member's level (was dropped: Codex has no effort attribute)",
          "model_reasoning_effort=low" in cx.extra_config and out == "việc", cx.extra_config)
    gk = _Grok()
    main._team_reasoning(gk, "high", "việc", "grok-cli")
    check("team turn on Grok Build gets Grok's own flag, not Claude Code's mapping", gk.effort == "high", gk.effort)
    ap = _Api()
    main._team_reasoning(ap, "medium", "việc", "groq")
    check("team turn on an API engine takes the member's level", ap.reasoning == "medium")
    cl = _Claude()
    main._team_reasoning(cl, "high", "việc", "anthropic-cli")
    check("team turn on Claude Code still takes the member's level", cl.effort in ("high", None))
    cx2 = _Codex()
    main._link_effort(cx2, "openai-oauth", "off")
    check("'off' sends nothing to Codex", cx2.extra_config == [])
finally:
    main._codex_effort, main._co_effort_lui = saved_codex_effort, saved_lui

# Team turn level: own model, own choice of MAIN, stand-in card.
info = {"reasoning": "low"}
check("team member on its own model: its own level",
      main._team_turn_level(info, {"source": "agent", "provider": "openai-oauth"}, m) == "low")
check("team member following MAIN by choice: its own level",
      main._team_turn_level(info, {"source": "main", "provider": "anthropic-cli", "note": ""}, m) == "low")
check("team member whose model cannot run: the stand-in card's setting",
      main._team_turn_level(info, {"source": "main", "provider": "anthropic-cli", "note": "x"}, m) == "medium")
check("team member following MAIN while MAIN rests: the next card's setting",
      main._team_turn_level(info, {"source": "main", "provider": "groq", "note": ""}, m) == "low"
      and main._team_turn_level({"reasoning": "ultra"}, {"source": "main", "provider": "openai-oauth", "note": ""}, m)
      == "xhigh")

# Background chain: Codex / Grok / Antigravity links get the step's effort.
seen = []
aux_engine.LINK_EFFORT = lambda e, p, lv: seen.append((p, lv))
aux_engine._apply_link_effort([object()], "openai-oauth", "high")
aux_engine._apply_link_effort([object()], "grok-cli", "off")
check("a background Codex link gets its step's effort, 'off' sends nothing", seen == [("openai-oauth", "high")], seen)
aux_engine.LINK_EFFORT = lambda eng, prov, level: main._link_effort(eng, prov, level)
src_aux = (ROOT / "server" / "aux_engine.py").read_text(encoding="utf-8")
check("Codex, Grok and Antigravity links pass their step's level",
      src_aux.count("_apply_link_effort(") >= 4 and "prov, level)" in src_aux)
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("a workflow step on an API model carries the assistant's level (was always 'off')",
      '"reasoning": reasoning if reasoning in engine.REASONING_LEVELS else "off"})' in src)

# Dedicated bot: the Agent's level on the Agent's model, the stand-in card's on a fallback.
mm = m["model"]
bot_lan = {"agent": {"brain": B, "slug": "lan"}}
bot_minh = {"agent": {"brain": B, "slug": "minh"}}
check("a bot whose Agent follows MAIN thinks at the Agent's level", main._bot_turn_reasoning(mm, "anthropic-cli", bot_lan) == "high")
check("a bot on its Agent's own model thinks at the Agent's level", main._bot_turn_reasoning(mm, "openai-oauth", bot_minh) == "low")
check("a bot whose Agent's model rests: the stand-in card's setting", main._bot_turn_reasoning(mm, "anthropic-cli", bot_minh) == "medium")
check("a turn with no Agent keeps the card's effort", main._bot_turn_reasoning(mm, "groq") == "low")

# Kanban job given to an assistant: its model and level, not the background model at "low".
import tasks as tasks_mod  # noqa: E402
main._agent_persona = lambda root, slug, key=None: "persona" if slug in ("lan", "minh") else ""
check("a job for an assistant with its own model runs that model at its level",
      main._agent_job_spec(B, "minh") == {"provider": "openai-oauth", "model": "gpt-5.5", "reasoning": "low"},
      main._agent_job_spec(B, "minh"))
spec_lan = main._agent_job_spec(B, "lan")
check("a job for an assistant on 'Default' model keeps the background model at the assistant's own level",
      spec_lan and spec_lan["reasoning"] == "high" and spec_lan["provider"], spec_lan)
check("an unknown assistant: a plain Kanban job", main._agent_job_spec(B, "nobody") is None)
check("the Kanban job reads its assistant from the owner's pick or the specifier's routing",
      tasks_mod.TasksFeature._assigned_agent({"idempotency_key": "agent:k1:minh:x"}) == ("minh", "k1")
      and tasks_mod.TasksFeature._assigned_agent({"metadata": {"agent": {"slug": "lan", "key": "k2"}}}) == ("lan", "k2")
      and tasks_mod.TasksFeature._assigned_agent({}) == ("", None))
src_t = (ROOT / "server" / "tasks.py").read_text(encoding="utf-8")
check("only the work step takes the assistant's model; a 'light' job keeps the assistant's level",
      'spec = self._agent_spec(task) if tag_suffix == "execute" else None' in src_t
      and 'not getattr(cli, "javis_agent_spec", None)' in src_t)

# An assistant's chat follows the assistant's CURRENT model unless the owner picked one in that window.
old_chat = store.create_session(brain=B, engine="cli", channel="agent:minh")
store.set_pinned_model(old_chat, "anthropic-cli", "sonnet")      # copied at creation / stamped, long ago
check("an old assistant chat runs the assistant's current model, not the model copied when it opened",
      turn(old_chat)[0] == "openai-oauth", turn(old_chat))
own_chat = store.create_session(brain=B, engine="cli", channel="agent:minh")
client.post(f"/sessions/{own_chat}/model", data={"provider": "groq", "model": "qwen3-32b"}, headers=H)
check("a model the owner picked in that window stays", turn(own_chat)[0] == "groq", turn(own_chat))
(BR / "agents" / "minh.md").write_text("---\nname: Minh\nrole: Kho\nmodel: opus\nmodel_provider: anthropic-cli\n"
                                       "reasoning: low\n---\nBạn là Minh.\n", encoding="utf-8", newline="\n")
check("changing the assistant's model moves its chats that had no pick of their own",
      turn(old_chat)[0] == "anthropic-cli" and turn(own_chat)[0] == "groq", (turn(old_chat), turn(own_chat)))
client.post(f"/sessions/{own_chat}/model", data={"provider": ""}, headers=H)
check("'Follow the assistant's model' clears the window's pick", turn(own_chat)[0] == "anthropic-cli", turn(own_chat))
meta = client.get(f"/sessions/{old_chat}/meta").json()
check("the composer shows the assistant's current model for that chat",
      meta.get("pinned_provider") == "anthropic-cli" and meta.get("pinned_model") == "opus", meta)
normal = store.create_session(brain=B, engine="cli", channel="web")
store.set_pinned_model(normal, "groq", "qwen3-32b")
check("a normal chat keeps its stamp as before", turn(normal)[0] == "groq")

# ============================================================
# 5. The usage order is never reordered from a chat
# ============================================================
mp = (ROOT / "dashboard" / "model-picker.js").read_text(encoding="utf-8")
check("the composer's model pick no longer rewrites MAIN (which moved the card to the top of the order)",
      "saveModel({ main:" not in mp)
check("the composer's effort chip saves the window's effort, not MAIN's card",
      "saveModel({ reasoning: v })" not in mp and "pinEffort(sid, v)" in mp)
check("the effort chip no longer rewrites the assistant's file", "/reasoning`, { method: \"POST\"" not in mp.split("pinEffort")[0])
check("a model and an effort picked before the first message are applied when the chat gets its id",
      "if (pendingEff) { sessionEff = pendingEff; pinEffort(sid, pendingEff);" in mp)
check("the usage order after every step of this test is the one the owner saved",
      cfgmod.read_settings()["model"]["order"] == ["anthropic-cli", "openai-oauth", "groq"])

print()
if fails:
    print(f"{len(fails)} FAIL")
    raise SystemExit(1)
print("all ok")
