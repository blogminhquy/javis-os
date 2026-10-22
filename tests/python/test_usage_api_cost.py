"""Customer report 0.270, code 12: background DeepSeek turns were written with cost 0.0, the Usage page
"API" filter could stay at 0, and team turns wrote no usage line at all.

    python tests/python/test_usage_api_cost.py

Self-contained: JAVIS_STATE_DIR and the Claude/Codex log folders point at temp dirs. No network, no model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

_TMP = Path(tempfile.mkdtemp(prefix="javis-usage-cost-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["JAVIS_CLAUDE_PROJECTS_DIR"] = str(_TMP / "claude")
os.environ["JAVIS_CODEX_SESSIONS_DIR"] = str(_TMP / "codex")
(_TMP / "state").mkdir(parents=True, exist_ok=True)

import usage_index as ui  # noqa: E402
import usage_parsers as up  # noqa: E402
import usage_store as us  # noqa: E402

fails = []
EVENTS = _TMP / "state" / "usage-events.jsonl"


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:300]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def lines():
    if not EVENTS.exists():
        return []
    return [json.loads(x) for x in EVENTS.read_text(encoding="utf-8").splitlines() if x.strip()]


def reset_events():
    if EVENTS.exists():
        EVENTS.unlink()


# ===== 1. record() prices per-token API turns =====
def section_record():
    reset_events()
    prices = up.load_prices()
    check("price table has the id Javis sends to DeepSeek", up._khoa_gia("deepseek-flash", prices) == "deepseek-flash")
    us.record("deepseek", "deepseek-flash", 1_000_000, 1_000_000)
    ev = lines()[-1]
    want = prices["deepseek-flash"]["in"] + prices["deepseek-flash"]["out"]
    check("DeepSeek background turn: cost from the price table, not 0.0",
          ev["cost"] and abs(ev["cost"] - want) < 1e-6, ev)

    for prov, model in (("openrouter", "deepseek/deepseek-r1"), ("groq", "llama-3.3-70b-versatile"),
                        ("gemini", "gemini-2.5-flash"), ("openai", "gpt-4o-mini"),
                        ("anthropic-api", "claude-sonnet-5"), ("openai-compat", "gpt-4.1"),
                        ("anthropic-compat", "claude-haiku-4-5")):
        us.record(prov, model, 1000, 1000)
        ev = lines()[-1]
        check(f"{prov} turn gets a cost", (ev["cost"] or 0) > 0, ev)

    us.record("deepseek", "mo-hinh-la-hoac", 500, 500)
    check("per-token API model missing from the table: cost null (unknown), never a fake 0.0",
          lines()[-1]["cost"] is None, lines()[-1])
    us.record("openrouter", "deepseek/deepseek-r1:free", 500, 500)
    check("OpenRouter ':free' model is known to cost 0", lines()[-1]["cost"] == 0.0, lines()[-1])
    us.record("cli", "claude-sonnet-5", 500, 500)
    check("plan-based Claude Code without a reported cost stays 0 (not priced as cash)",
          lines()[-1]["cost"] == 0.0, lines()[-1])
    us.record("ollama-local", "llama3", 500, 500)
    check("local Ollama is free: cost 0", lines()[-1]["cost"] == 0.0, lines()[-1])
    us.record("deepseek", "deepseek-flash", 10, 10, 0.5)
    check("a cost the provider reported wins over the table", lines()[-1]["cost"] == 0.5, lines()[-1])

    tot = us.summary()["today"]["items"]
    ds = next((x for x in tot if x["provider"] == "deepseek" and x["model"] == "deepseek-flash"), {})
    check("usage.json (Telegram /usage) also carries the DeepSeek cost", ds.get("cost", 0) > 0.4, ds)


# ===== 2. the index puts these lines under "API" =====
def section_index():
    ui.refresh()
    s = ui.summary(period="today", provider="api")
    k = s["kpi"]
    check("API filter: DeepSeek tokens and turns counted", k["tokens"] > 0 and k["turns"] >= 1, k)
    check("API filter: estimated real cash is not $0", k["cost_est"] > 0, k)
    models = {x["key"] for x in s["by_model"]}
    check("custom gateway lines (openai-compat / anthropic-compat) are counted under API",
          {"gpt-4.1", "claude-haiku-4-5"} <= models, models)
    allp = {x["key"]: x for x in ui.summary(period="today")["by_provider"]}
    check("local Ollama has its own column, not API cash", "local" in allp and "llama3" not in models, list(allp))


# ===== 3. one broken source no longer hides the API branch =====
def section_isolation():
    real = up.parse_claude_line

    def boom(*a, **k):
        raise ValueError("odd transcript line")

    p = _TMP / "claude" / "proj" / "s.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"type": "assistant", "message": {"model": "claude-sonnet-5", "usage": {
        "input_tokens": 5, "output_tokens": 5}}, "timestamp": "2026-10-22T01:00:00Z", "sessionId": "x"}) + "\n",
        encoding="utf-8")
    before = ui.summary(period="today", provider="api")["kpi"]["turns"]
    us.record("deepseek", "deepseek-flash", 2000, 100)
    with patch.object(ui.up, "parse_claude_line", boom):
        res = ui.refresh()
    after = ui.summary(period="today", provider="api")["kpi"]["turns"]
    check("Claude transcript scan crashes, API events are still ingested", after == before + 1, (before, after, res))
    check("CANARY: the real parser is back", ui.up.parse_claude_line is real)


# ===== 4. team turns =====
def section_outcome():
    import team_runner as TR
    o = TR.TextOnlyOutcome()
    o.note({"type": "final", "content": "Xong", "tokens_in": 120, "tokens_out": 30, "cost_usd": 0.01})
    r = o.result()
    check("Claude/Codex team turn: tokens and cost read from the final event",
          (r["tokens_in"], r["tokens_out"], r.get("cost_usd")) == (120, 30, 0.01), r)
    o = TR.TextOnlyOutcome()
    for ev in ({"type": "usage", "input": 100, "output": 10}, {"type": "usage", "input": 50, "output": 5},
               {"type": "final", "content": "Xong"}):
        o.note(ev)
    r = o.result()
    check("API team turn: per-call usage events are added up", (r["tokens_in"], r["tokens_out"]) == (150, 15), r)
    o = TR.TextOnlyOutcome()
    for ev in ({"type": "usage", "input_tokens": 7, "output_tokens": 3}, {"type": "final", "content": "Xong",
                                                                          "tokens_in": 999}):
        o.note(ev)
    r = o.result()
    check("CANARY: a usage event wins over the final's figure (no double count)", r["tokens_in"] == 7, r)


def section_team():
    os.environ.setdefault("JAVIS_NO_REAL_TEAM_ENGINE", "1")
    import main
    import team_engine

    class Engine:
        model = "claude-sonnet-5"

        def is_available(self):
            return True

        async def query(self, prompt):
            yield {"type": "text", "content": "Hi"}
            yield {"type": "final", "content": "Proposal ready", "tokens_in": 4321, "tokens_out": 210,
                   "cost_usd": 0.02}

    def build(spec, base, tag, settings=None, **_kw):
        return Engine()

    info = {"slug": "one", "name": "One", "system": "You are One.", "model": "", "model_provider": ""}
    team = {"brain_id": str(_TMP / "brain"), "team_id": "tm-usage-1", "session_id": ""}
    reset_events()
    with patch.object(main, "_team_agent_info", return_value=info), \
            patch.multiple(main.team_engine, build=build, build_tools=build):
        prov, model, run = main._team_engine_for(team, "agent-one", "member")
        started = []

        async def engine_started(*a):
            started.append(a)

        res = asyncio.run(run({"team_id": team["team_id"], "turn_id": "turn-1", "system": "sys", "prompt": "Write",
                               "tool_turn": False, "engine_started": engine_started}))
    got = lines()
    check("team turn writes one usage line", len(got) == 1, got)
    if got:
        check("team usage line: Claude provider, real tokens",
              got[0]["provider"] == prov and (got[0]["in"], got[0]["out"]) == (4321, 210), got[0])
    check("team turn result carries tokens and cost for the team ledger",
          (res["tokens_in"], res["tokens_out"], res.get("cost_usd")) == (4321, 210, 0.02), res)

    reset_events()
    main._team_record_usage("deepseek", "deepseek-flash", type("O", (), {"tokens_in": 10, "tokens_out": 5,
                                                                           "cost_usd": None})())
    check("CANARY: API team turns are not recorded twice (the API engine records them itself)", lines() == [])
    check("CANARY: team_engine still the real module object", team_engine is main.team_engine)


for _name, _fn in (("record", section_record), ("index", section_index), ("isolation", section_isolation),
                   ("outcome", section_outcome), ("team", section_team)):
    try:
        _fn()
    except Exception as _ex:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        check(f"{_name} section ran to the end", False, f"{type(_ex).__name__}: {_ex}")

print(f"\n{'FAIL' if fails else 'PASS'} - test_usage_api_cost: {len(fails)} failed")
raise SystemExit(1 if fails else 0)
