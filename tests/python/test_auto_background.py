"""Lighter background work on a plan (owner, 10/11/2026).

    python tests/run.py auto_background

Users reported the plan allowance draining while they were not typing. The owner's decisions, pinned here:

1. The background model is on AUTOMATIC unless picked by hand. Javis reads the provider's own model list once, with
   the main brain, and keeps two picks: `light` for the work Javis starts itself, `mid` for handed-over jobs. No
   table of model names: an id the provider did not list is dropped, "not sure" means MAIN's model.
2. It picks again only when that list changed, and never replaces a model picked by hand.
3. Self-learning learns memories and wiki notes only by default. It runs 15 minutes after the brain's LAST event
   (one pass per conversation, every new turn read once), there is no daily cap, and a day with no event learns
   nothing.
4. Text-only side calls send neither the claude_code preset nor a tool schema.
5. Past 80% of the plan's 5-hour window, the work Javis starts itself waits for the reset.

No network, no engine: the model list and the main brain are fakes.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-auto-bg-"))
os.environ["JAVIS_AUTO_BACKGROUND_PAUSED"] = "1"      # the scheduler must not run the tick under the test

import main  # noqa: E402
import config as cfgmod  # noqa: E402
import auto_background as ab  # noqa: E402
import aux_engine  # noqa: E402
import model_routing as mr  # noqa: E402
import plan_limits  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. auto_background: pure helpers
# ============================================================
LIST = [{"id": "gpt-9-terra", "description": "Our most capable model for hard work"},
        {"id": "gpt-9-luna", "description": "Fast, low-cost model for everyday tasks"},
        {"id": "gpt-9-vela", "description": "Balanced model"}]

check("normalize keeps order, drops blanks and repeats",
      [m["id"] for m in ab.normalize(["a", "", "b", "a", {"id": "c"}])] == ["a", "b", "c"])
check("the signature ignores order", ab.signature(LIST) == ab.signature(list(reversed(LIST))))
check("the signature changes when a model appears", ab.signature(LIST) != ab.signature(LIST + ["gpt-10"]))
check("the signature changes when a description changes",
      ab.signature(LIST) != ab.signature([dict(LIST[0], description="x")] + LIST[1:]))

prompt = ab.build_prompt("ChatGPT", LIST, "gpt-9-terra")
check("the prompt carries every id and the provider's own description",
      all(m["id"] in prompt for m in LIST) and "low-cost model" in prompt)
check("the prompt allows 'not sure' and forbids guessing from a name",
      "null" in prompt and "do not guess" in prompt)
check("this module holds no model name of its own",
      not any(w in open(ab.__file__, encoding="utf-8").read().lower() for w in ("haiku", "sonnet", "mini\"", "nano")))

check("a clean answer is read", ab.parse('{"light": "gpt-9-luna", "mid": "gpt-9-vela"}', LIST)
      == {"light": "gpt-9-luna", "mid": "gpt-9-vela", "ladder": ["gpt-9-luna", "gpt-9-vela"]})
check("JSON inside a sentence or a code fence is read",
      ab.parse('Here:\n```json\n{"light": "gpt-9-luna", "mid": null}\n```', LIST)
      == {"light": "gpt-9-luna", "mid": "", "ladder": ["gpt-9-luna"]})
check("an id the provider did not list is dropped, not repaired",
      ab.parse('{"light": "gpt-9-mini", "mid": "gpt-9-vela"}', LIST)
      == {"light": "", "mid": "gpt-9-vela", "ladder": ["gpt-9-vela"]})
_lad = ab.parse('{"ladder": ["gpt-9-luna", "gpt-9-zzz", "gpt-9-vela", "gpt-9-luna", "gpt-9-terra"], "light": null, '
                '"mid": null}', LIST)
check("the ladder keeps the brain's order, without unknown ids or repeats",
      _lad["ladder"] == ["gpt-9-luna", "gpt-9-vela", "gpt-9-terra"])
check("with a ladder and no starting points, they are read off the ladder (bottom, middle)",
      (_lad["light"], _lad["mid"]) == ("gpt-9-luna", "gpt-9-vela"))
check("'light' above 'mid' is a contradiction: the ladder's order wins",
      ab.parse('{"ladder": ["gpt-9-luna", "gpt-9-vela"], "light": "gpt-9-vela", "mid": "gpt-9-luna"}', LIST)["light"]
      == "gpt-9-luna")
check("the prompt asks for the ladder, lightest first, no higher than the main model",
      '"ladder"' in prompt and "lightest to heaviest" in prompt and "stopping at the main chat model" in prompt)
check("no JSON at all is no answer", ab.parse("I think luna is the light one", LIST) is None)
check("JSON about something else is no answer", ab.parse('{"verdict": "ok"}', LIST) is None)

asked = []


async def fake_ask(p):
    asked.append(p)
    return '{"light": "gpt-9-luna", "mid": "gpt-9-vela"}'


_ch = asyncio.run(ab.choose("ChatGPT", LIST, "gpt-9-terra", fake_ask))
check("choose asks the main brain once", (_ch["light"], _ch["mid"]) == ("gpt-9-luna", "gpt-9-vela") and len(asked) == 1)
asked.clear()
check("one model in the list: nothing to pick, nothing asked",
      asyncio.run(ab.choose("X", ["only"], "only", fake_ask)) == {"light": "", "mid": "", "ladder": []} and not asked)
check("a marketplace-sized list is not ranked",
      asyncio.run(ab.choose("X", [f"m{i}" for i in range(ab.MAX_MODELS + 1)], "m0", fake_ask))
      == {"light": "", "mid": "", "ladder": []} and not asked)
check("an empty list gives no answer", asyncio.run(ab.choose("X", [], "", fake_ask)) is None and not asked)

now = time.time()
check("never picked: due at once", ab.due({}, now))
check("picked today: not due", not ab.due({"sig": "a", "checked": now - 3600}, now))
check("picked more than a day ago: due", ab.due({"sig": "a", "checked": now - ab.RECHECK_S - 1}, now))
check("a failed attempt waits for its retry time", not ab.due({"retry_at": now + 600}, now)
      and ab.due({"retry_at": now - 1}, now))

# ============================================================
# 2. model_routing: Automatic, the two tiers, a choice by hand
# ============================================================
M = {"order": ["openai-oauth"], "profiles": {"openai-oauth": {"model": "gpt-9-terra", "reasoning": "off"}},
     "defaults": {"openai-oauth": {"model": "gpt-9-terra", "reasoning": "off"}}}

check("unset background model = Automatic", mr.background_auto(dict(M, auxiliary={"model": ""})))
check("the 0.350.0 starting config of MAIN's provider = never chosen = Automatic",
      mr.background_auto(dict(M, auxiliary={"provider": "openai-oauth", "model": "gpt-9-terra"})))
check("another model of that provider was picked by hand",
      not mr.background_auto(dict(M, auxiliary={"provider": "openai-oauth", "model": "gpt-9-vela"})))
check("another provider was picked by hand",
      not mr.background_auto(dict(M, auxiliary={"provider": "groq", "model": ""})))
check("the explicit flag wins both ways",
      mr.background_auto(dict(M, auxiliary={"provider": "groq", "model": "x", "auto": True}))
      and not mr.background_auto(dict(M, auxiliary={"model": "", "auto": False})))

AUTO = dict(M, auxiliary={"auto": True, "reasoning": "low"},
            auto_background={"openai-oauth": {"light": "gpt-9-luna", "mid": "gpt-9-vela", "sig": "s"}})
check("Automatic, handed-over work: MAIN's provider, the mid pick",
      mr.background_spec(AUTO) == {"provider": "openai-oauth", "model": "gpt-9-vela", "reasoning": "low", "auto": True})
check("Automatic, Javis's own work: the light pick", mr.background_spec(AUTO, "light")["model"] == "gpt-9-luna")
check("no pick yet: MAIN's own model, as before",
      mr.background_spec(dict(AUTO, auto_background={}), "light")["model"] == "gpt-9-terra")
check("an empty slot falls back to MAIN's model, the other slot still applies",
      mr.background_spec(dict(AUTO, auto_background={"openai-oauth": {"light": "", "mid": "gpt-9-vela"}}), "light")["model"]
      == "gpt-9-terra")
check("Automatic follows MAIN to another provider",
      mr.background_spec(dict(AUTO, order=["anthropic-cli", "openai-oauth"]))["provider"] == "anthropic-cli")
BY_HAND = dict(M, auxiliary={"provider": "groq", "model": "llama", "auto": False},
               auto_background={"groq": {"light": "a", "mid": "b"}})
check("a model picked by hand runs for every tier, picks ignored",
      mr.background_spec(BY_HAND, "light")["model"] == "llama" and mr.background_spec(BY_HAND)["provider"] == "groq"
      and mr.background_spec(BY_HAND)["auto"] is False)

check("Javis's own work is the light tier", all(aux_engine.tier_for_tag(t) == "light" for t in
      ("learn", "next-prompt", "reply-policy", "habit-coach", "incident-triage", "agent-judge", "auto-learning", "curator")))
check("handed-over work is the mid tier", all(aux_engine.tier_for_tag(t) == "mid" for t in
      ("reminder", "loop", "workflow", "ingest", "dispatch:abc:run", "", None, "learned-mirror")))
check("read_spec answers by tag", aux_engine.read_spec({"model": AUTO}, tag="learn")["model"] == "gpt-9-luna"
      and aux_engine.read_spec({"model": AUTO}, tag="reminder")["model"] == "gpt-9-vela"
      and aux_engine.read_spec({"model": AUTO})["model"] == "gpt-9-vela")



class _Cli:
    def __init__(self):
        self.model, self.effort, self.tag, self.system_prompt = None, None, "x", "p"

    def is_available(self):
        return True


def _chain(settings, tag):
    e = aux_engine.swap(_Cli(), mode="suggest", tag=tag, settings=settings)
    return [x.model for x in (e._all() if isinstance(e, aux_engine._FallbackChain) else [e])]


PLAN = {"model": {"order": ["anthropic-cli"], "profiles": {"anthropic-cli": {"model": "main-model", "reasoning": "off"}},
                  "defaults": {"anthropic-cli": {"model": "main-model", "reasoning": "off"}},
                  "auxiliary": {"auto": True},
                  "auto_background": {"anthropic-cli": {"light": "light-model", "mid": "mid-model"}}}}
check("on a plan, a refused pick still leaves MAIN's model as the last link",
      _chain(PLAN, "learn") == ["light-model", "main-model"] and _chain(PLAN, "reminder") == ["mid-model", "main-model"],
      (_chain(PLAN, "learn"), _chain(PLAN, "reminder")))
PLAN["model"]["auto_background"] = {}
check("no pick: one link, MAIN's model, no duplicate", _chain(PLAN, "learn") == ["main-model"], _chain(PLAN, "learn"))

# ============================================================
# 3. main: the tick that keeps the picks current
# ============================================================
state = {"list": list(LIST), "asked": 0, "answer": '{"light": "gpt-9-luna", "mid": "gpt-9-vela"}', "notices": []}


async def _fake_models(provider):
    return list(state["list"])


async def _fake_main_ask(prompt):
    state["asked"] += 1
    return state["answer"]


async def _fake_notify(owner_chat, text, **kw):
    state["notices"].append(text)
    return (True, "")


main._auto_background_models = _fake_models
main._auto_background_ask = _fake_main_ask
main._notify_owner = _fake_notify


def _settings(**model):
    cfg = cfgmod.read_settings()
    cfg["model"].pop("auto_background", None)
    cfg["model"]["order"] = ["openai-oauth"]
    cfg["model"]["profiles"] = {"openai-oauth": {"model": "gpt-9-terra", "reasoning": "off"}}
    cfg["model"]["defaults"] = {"openai-oauth": {"model": "gpt-9-terra", "reasoning": "off"}}
    cfg["model"]["auxiliary"] = {"model": ""}
    cfg["model"].update(model)
    cfgmod.write_settings(cfg)


def _picks():
    return mr.background_picks(cfgmod.read_settings()["model"], "openai-oauth")


_settings()
r = asyncio.run(main._auto_background_tick())
check("first tick picks from the provider's list", r.get("reason") == "picked"
      and (_picks().get("light"), _picks().get("mid")) == ("gpt-9-luna", "gpt-9-vela"), r)
check("the flag is written once the tick has decided", cfgmod.read_settings()["model"]["auxiliary"].get("auto") is True)
check("the owner is told once, with both models named",
      len(state["notices"]) == 1 and "gpt-9-luna" in state["notices"][0] and "gpt-9-vela" in state["notices"][0])
check("background work now runs the picks",
      aux_engine.read_spec(tag="learn") == {"provider": "openai-oauth", "model": "gpt-9-luna"}
      and aux_engine.read_spec(tag="reminder")["model"] == "gpt-9-vela")

r = asyncio.run(main._auto_background_tick())
check("picked today: the next tick does nothing", r.get("reason") == "not_due" and state["asked"] == 1, r)
r = asyncio.run(main._auto_background_tick(force=True))
check("same list: the main brain is not asked again", r.get("reason") == "unchanged" and state["asked"] == 1, r)

state["list"].append({"id": "gpt-9-nova", "description": "New: the cheapest small model"})
state["answer"] = '{"light": "gpt-9-nova", "mid": "gpt-9-vela"}'
r = asyncio.run(main._auto_background_tick(force=True))
check("the provider added a model: picked again, once", r.get("reason") == "picked" and state["asked"] == 2
      and _picks().get("light") == "gpt-9-nova", r)
check("and the owner is told about the change", len(state["notices"]) == 2)

state["list"].append({"id": "gpt-9-zeta", "description": ""})
state["answer"] = "sorry, I cannot tell"
r = asyncio.run(main._auto_background_tick(force=True))
check("no usable answer: the earlier picks stay, a retry is set",
      r.get("reason") == "no_answer" and _picks().get("light") == "gpt-9-nova" and _picks().get("retry_at", 0) > time.time(), r)
check("and nobody is notified about a non-change", len(state["notices"]) == 2)

state["answer"] = '{"light": null, "mid": null}'
r = asyncio.run(main._auto_background_tick(force=True))
check("'not sure' is an answer: no picks, MAIN's model runs",
      r.get("reason") == "picked" and aux_engine.read_spec(tag="learn")["model"] == "gpt-9-terra", r)

# a model picked by hand is never replaced
n_before = state["asked"]
rs = client.post("/settings", data={"section": "model",
                                    "data": json.dumps({"auxiliary": {"provider": "openai-oauth", "model": "gpt-9-terra"}})})
check("choosing a model on the Models page turns Automatic off",
      rs.status_code == 200 and cfgmod.read_settings()["model"]["auxiliary"].get("auto") is False)
state["list"].append("gpt-9-omega")
r = asyncio.run(main._auto_background_tick(force=True))
check("a hand-picked background model is never touched, whatever the list does",
      r.get("reason") == "manual" and state["asked"] == n_before
      and aux_engine.read_spec(tag="learn")["model"] == "gpt-9-terra", r)
rs = client.post("/settings", data={"section": "model", "data": json.dumps({"auxiliary": {"auto": True}})})
check("the Automatic row of the picker turns it back on",
      rs.status_code == 200 and cfgmod.read_settings()["model"]["auxiliary"].get("auto") is True)
check("changing only the effort does not count as picking a model",
      client.post("/settings", data={"section": "model", "data": json.dumps({"auxiliary": {"reasoning": "low"}})}).status_code == 200
      and cfgmod.read_settings()["model"]["auxiliary"].get("auto") is True)

view = main._routing_view(cfgmod.read_settings()["model"], [{"id": "openai-oauth", "configured": True}])
check("the Models page is told it is Automatic, with both models",
      view["background"].get("auto") is True and "light" in view["background"])

# ============================================================
# 4. plan_limits.side_pause and the pause of Javis's own work
# ============================================================
plan_limits.ghi("codex", {"five_hour": {"pct": 85, "resets_at": int(time.time()) + 3600}})
check("85% of the 5-hour window: Javis's own work waits", plan_limits.side_pause("openai-oauth")["paused"] is True)
check("main reports the pause with a reason", "85" in main._side_work_paused())
plan_limits.ghi("codex", {"five_hour": {"pct": 79, "resets_at": int(time.time()) + 3600}})
check("79%: it runs", plan_limits.side_pause("openai-oauth")["paused"] is False and main._side_work_paused() == "")
plan_limits.ghi("codex", {"five_hour": {"pct": 95, "resets_at": int(time.time()) - 5}})
check("a window that already reset reads as fresh", plan_limits.side_pause("openai-oauth")["paused"] is False)
check("a provider with no meter is never paused", plan_limits.side_pause("groq")["paused"] is False
      and plan_limits.side_pause("")["paused"] is False)

plan_limits.ghi("codex", {"five_hour": {"pct": 90, "resets_at": int(time.time()) + 3600}})
try:
    asyncio.run(main._next_prompt_ask("x"))
    paused_raised = False
except RuntimeError as e:
    paused_raised = "paused" in str(e)
check("the next-message suggestion does not run on the plan while paused", paused_raised)
plan_limits.ghi("codex", {"five_hour": {"pct": 10, "resets_at": int(time.time()) + 3600}})

# ============================================================
# 5. Self-learning: defaults, one trigger (quiet for 15 minutes), no daily cap
# ============================================================
lf = main.learn_feature
cfg = lf.read_config()
check("out of the box Javis learns memories and wiki notes, not skills",
      cfg["capabilities"]["memory"] and cfg["capabilities"]["wiki"] and cfg["capabilities"]["skill"] is False)
check("the one-time migrations are recorded", cfg["_migrations"].get("skill_learning_off") is True
      and cfg["_migrations"].get("idle_15_minutes") is True)
check("the quiet time before a batch is 15 minutes", cfg["debounce"]["idle_min"] == 15)
check("there is no daily cap in the defaults", "fork_day" not in lf.DEFAULT["rate"] and "token_day" not in lf.DEFAULT["rate"])
cfg["capabilities"]["skill"] = True
lf.write_config(cfg)
check("switching skill learning back on is kept (the migration runs once)",
      lf.read_config()["capabilities"]["skill"] is True)
cfg = lf.read_config()
cfg["capabilities"]["skill"] = False
lf.write_config(cfg)


def _p(count, ago_s, urgent=False):
    return {"count": count, "dense": True, "urgent": urgent, "last_ts": time.time() - ago_s, "convs": {"s1"}}


cfg = lf.read_config()
check("many turns but the chat is still going: no batch", not lf._should_fire(cfg, _p(30, 60)))
check("14 minutes of quiet: not yet", not lf._should_fire(cfg, _p(1, 14 * 60)))
check("15 minutes after the last event: the batch runs", lf._should_fire(cfg, _p(1, 15 * 60 + 1)))
check("nothing queued: a quiet day learns nothing", not lf._should_fire(cfg, _p(0, 24 * 3600)))
check("an explicit 'ghi nhớ giúp' is learned after 30 seconds", lf._should_fire(cfg, _p(1, 31, urgent=True))
      and not lf._should_fire(cfg, _p(1, 10, urgent=True)))

busy = dict(_p(2, 60), first_ts=time.time() - 121 * 60)
check("a brain that is never quiet (a bot with customers all day) still learns after 2 hours", lf._should_fire(cfg, busy))
check("but not before", not lf._should_fire(cfg, dict(_p(2, 60), first_ts=time.time() - 60 * 60)))

lf._pending.clear()
lf._pending["brain"] = _p(2, 16 * 60)
lf.touch("brain")
check("a new event (the owner writes again, a bot answers a customer) starts the quiet time over",
      not lf._should_fire(cfg, lf._pending["brain"]))
lf._pending.clear()
lf.touch("brain")
check("activity alone queues nothing to learn", "brain" not in lf._pending)

st = cfg.setdefault("_state", {})
st.update({"day": main.learn_mod._today(), "fork_count": 999, "token_est": 10 ** 9, "last_fork_ts": 0})
check("a heavy day is not downgraded: the daily caps are gone", lf._rate_check(cfg)["allow_promote"] is True)

# one conversation, one pass: every new turn is read once, however long the chat ran
class _Store:
    def __init__(self, convs):
        self.convs = convs

    def get_messages(self, sid):
        return list(self.convs.get(sid, []))


def _conv(n_turns, size=200, tag="c"):
    out = []
    for i in range(n_turns):
        out.append({"role": "user", "content": f"{tag}-hoi-{i} " + "x" * size})
        out.append({"role": "assistant", "content": f"{tag}-dap-{i} " + "y" * size})
    return out


real_store = lf.deps.sessions_store
lf.deps.sessions_store = _Store({"long": _conv(20), "big": _conv(30, size=2900, tag="b")})
d = lf._build_digest("brain", ["long"], [], {"long": 20})
check("a 20-turn conversation is read whole, not just its last 12 messages",
      "c-hoi-0 " in d and "c-dap-19 " in d and not lf._leftover)
d = lf._build_digest("brain", ["long"], [], {"long": 3})
check("only the turns since the last batch are read", "c-hoi-17 " in d and "c-hoi-16 " not in d)
d = lf._build_digest("brain", ["long"], [])
check("a manual run keeps the old window (last 12 messages)", "c-hoi-14 " in d and "c-hoi-13 " not in d)
d = lf._build_digest("brain", ["big", "long"], [], {"big": 30, "long": 20})
left = dict(lf._leftover)
check("past the budget the rest is left for the next batch, nothing is dropped",
      len(d) <= lf.DIGEST_MAX + 6000 and 0 < left.get("big", 0) < 30 and left.get("long") == 20, left)
first_left = 30 - left["big"]
d2 = lf._build_digest("brain", ["big"], [], {"big": left["big"]})
check("the next batch starts where the last one stopped", f"b-hoi-{first_left} " in d2 or f"b-dap-{first_left - 1} " in d2)
lf.deps.sessions_store = real_store
lf._leftover = {}

# the plan pause is the one thing that makes an automatic batch wait
ran = []


async def _fake_run_once(brain, reason="manual", **kw):
    ran.append((brain, reason))
    return {"ok": True}


real_run_once = lf.run_once
lf.run_once = _fake_run_once
lf._pending.clear()
lf._pending["brain"] = _p(2, 16 * 60)
plan_limits.ghi("codex", {"five_hour": {"pct": 92, "resets_at": int(time.time()) + 3600}})
asyncio.run(lf.tick())
check("while the plan is nearly used up the batch waits, its turns stay queued", ran == [] and "brain" in lf._pending, ran)
check("the reason is noted once", "5" in lf.read_config()["_state"].get("hold_logged", ""))
plan_limits.ghi("codex", {"five_hour": {"pct": 5, "resets_at": int(time.time()) + 3600}})
asyncio.run(lf.tick())
check("after the reset it runs", ran == [("brain", "auto")], ran)
lf.run_once = real_run_once
lf._pending.clear()

# ============================================================
# 6. Text-only side calls carry no preset and no tool schema
# ============================================================
seen = {}


class _FakeCli:
    def __init__(self, **kw):
        seen.update(kw)
        self.disallowed_tools = None
        self.mcp_config = None
        self.mcp_strict = False
        self.system_prompt_raw = False


real_engine = main.claude_engine
main.claude_engine = lambda **kw: _FakeCli(**kw)
try:
    bare = main._reply_policy_sandbox_engine("Answer with JSON.", "next-prompt", cwd_name="t_bare")
    full = main._reply_policy_sandbox_engine("Agent turn.", "team", cwd_name="t_full", bare=False)
finally:
    main.claude_engine = real_engine
check("a text-only call takes every tool schema out of the request", bare.disallowed_tools[0] == "*")
check("and sends its own prompt instead of the claude_code preset", bare.system_prompt_raw is True)
check("the named deny list stays as the second wall", all(t in bare.disallowed_tools for t in ("Bash", "Read", "Skill")))
check("the permission gate still refuses every call", bool(seen.get("allowed_tools")))
check("an agent-style turn keeps the preset", "*" not in full.disallowed_tools and full.system_prompt_raw is False)

# ============================================================
# 7. The Models page shows Automatic and offers the way back to it
# ============================================================
_js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("the background block names Automatic and both models", 'models.bg_auto_sub' in _js and 'bgCfg.light' in _js)
check("the picker has an Automatic row that saves {auto: true}",
      'data-bgauto' in _js and 'save({ auxiliary: { auto: true } })' in _js)
for _lang in ("vi", "en"):
    _t = json.loads((ROOT / "dashboard" / "i18n" / f"{_lang}.json").read_text(encoding="utf-8"))
    check(f"the Automatic labels exist ({_lang}) and the short ones fit on one line",
          all(_t.get(k) for k in ("models.bg_auto", "models.bg_auto_sub", "models.bg_auto_pick"))
          and len(_t["models.bg_auto_sub"]) < 100)

if _fails:
    print(f"\nFAIL - {len(_fails)} check(s)")
    raise SystemExit(1)
print("\nOK - auto_background: all pass")
