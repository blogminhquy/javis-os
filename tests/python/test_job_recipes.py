"""Recipes: a recurring job replays its own read chain before the model starts.

    python tests/run.py job_recipes

The dangerous way to do this is to guess. A report job that asked for "2026-11-09 to 2026-11-11"
on a Wednesday might mean "Monday to today", "the 9th to today" or "two days back to today", and
a wrong guess is a report on the wrong period, sent unattended. So this file pins the rule:

  - a recipe needs the same chain on two different days;
  - each date keeps every explanation still consistent with all runs seen;
  - it is replayed on a day only when all remaining explanations give the same date that day,
    otherwise the job runs the normal way and that run narrows the explanations;
  - only reads are recorded and replayed; a failed step, a changed task or a vanished tool falls
    back to the normal run; two failed replays delete the recipe.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from datetime import date

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-recipes-"))

import config  # noqa: E402
import engine  # noqa: E402
import job_recipes as jr  # noqa: E402
import mcp_catalog  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402
import reminders as R  # noqa: E402
import tool_result_shaper as shaper  # noqa: E402
import turn_context  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


# ============================================================
# 1. Dates as explanations
# ============================================================
TUE, WED, THU = date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 12)
MON, NEXT_MON = date(2026, 11, 9), date(2026, 11, 16)
check("the test dates are the weekdays the names say", TUE.weekday() == 1 and MON.weekday() == 0)
ex = jr.explain(date(2026, 11, 9), TUE)
check("a date is explained every way it can be",
      ["literal", "2026-11-09"] in ex and ["day", -1] in ex and ["week_start", 0] in ex, ex)
check("every explanation evaluates back to the date it explains",
      all(jr.evaluate(e, TUE) == date(2026, 11, 9) for e in ex), ex)
for found, day in ((date(2026, 10, 1), TUE), (date(2026, 10, 31), TUE), (date(2026, 1, 1), TUE),
                   (date(2026, 11, 1), TUE), (date(2026, 11, 30), TUE), (date(2025, 12, 31), TUE),
                   (date(2026, 11, 15), TUE), (date(2024, 2, 29), TUE)):
    exs = jr.explain(found, day)
    check(f"explanations of {found} hold on {day}", all(jr.evaluate(e, day) == found for e in exs), exs)
check("month arithmetic crosses a year", jr.evaluate(["month_start", -11], date(2026, 1, 15)) == date(2025, 2, 1)
      and jr.evaluate(["month_end", -1], date(2026, 3, 31)) == date(2026, 2, 28))

steps = [{"tool": "shop__stats", "args": {"from": "2026-11-09", "to": "2026-11-10T23:59:59", "shop": 7}},
         {"tool": "javis_query", "args": {"sql": "SELECT 1 WHERE d >= '2026-11-09'", "ref": "{{ref0}}"}}]
skel, dates = jr.skeleton(steps)
check("dates become slots, everything else is kept",
      dates == [date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 9)] or len(dates) == 3, dates)
check("a skeleton filled with the same dates is the original", jr.fill(skel, dates) == json.loads(json.dumps(steps, sort_keys=True)))
check("an order number that looks nothing like a date is left alone",
      jr.skeleton([{"tool": "t", "args": {"id": "20261109123", "n": 2026}}])[1] == [])

# ============================================================
# 2. Learning from runs: "Monday to today" must not be confused with fixed dates
# ============================================================
BRAIN = tempfile.mkdtemp(prefix="recipes-brain-")
JOB = "reminder:r_week:1731200000"
TASK, MODE = "Báo cáo doanh thu tuần này", "full"


def observe(day, steps_of_day, job=JOB, task=TASK, ok=True, mode=MODE):
    jr.begin(job)
    for s in steps_of_day:
        jr.note_call(job, s["tool"], s["args"], ok=True, ref=s.get("ref", ""))
    return jr.finish(BRAIN, job, ok=ok, task=task, mode=mode, run_day=day)


def week_steps(day):
    monday = day.fromordinal(day.toordinal() - day.weekday())
    return [{"tool": "shop__stats", "args": {"from": monday.isoformat(), "to": day.isoformat(), "shop": 7}}]


check("the first run only learns", observe(TUE, week_steps(TUE)) == "learned")
check("one run is never enough to replay", jr.plan(jr.load(BRAIN, JOB), TASK, MODE, WED) is None)
check("a second run the same day proves nothing", observe(TUE, week_steps(TUE)) == "")
check("the same chain on another day confirms it", observe(WED, week_steps(WED)) == "confirmed")
recipe = jr.load(BRAIN, JOB)
check("'today' is pinned down by two days", recipe["slots"][1] == [["day", 0]], recipe["slots"][1])
check("the start date still has two explanations: fixed date or start of week",
      sorted(e[0] for e in recipe["slots"][0]) == ["literal", "week_start"], recipe["slots"][0])
plan = jr.plan(recipe, TASK, MODE, THU)
check("same week: both explanations agree, so it replays with today's date",
      plan == [{"tool": "shop__stats", "args": {"from": "2026-11-09", "to": "2026-11-12", "shop": 7}}], plan)
check("next Monday they disagree, so it does NOT replay", jr.plan(recipe, TASK, MODE, NEXT_MON) is None)
check("that Monday's normal run settles it", observe(NEXT_MON, week_steps(NEXT_MON)) == "narrowed")
recipe = jr.load(BRAIN, JOB)
check("only 'start of this week' survives", recipe["slots"][0] == [["week_start", 0]], recipe["slots"][0])
plan = jr.plan(recipe, TASK, MODE, date(2026, 11, 25))
check("from then on any day replays with the right week",
      plan[0]["args"] == {"from": "2026-11-23", "to": "2026-11-25", "shop": 7}, plan)

check("a changed task text does not use the old recipe", jr.plan(recipe, TASK + " và tồn kho", MODE, THU) is None)
check("a changed permission level does not either", jr.plan(recipe, TASK, "suggest", THU) is None)
os.environ["JAVIS_RECIPES"] = "0"
check("JAVIS_RECIPES=0 switches recipes off", jr.plan(recipe, TASK, MODE, THU) is None)
os.environ.pop("JAVIS_RECIPES")

# a truly fixed date stays fixed
JOB2 = "reminder:r_fixed:1"
fixed = lambda day: [{"tool": "shop__stats", "args": {"from": "2026-10-01", "to": day.isoformat()}}]  # noqa: E731
observe(TUE, fixed(TUE), job=JOB2)
observe(WED, fixed(WED), job=JOB2)
r2 = jr.load(BRAIN, JOB2)
check("a campaign start date is also explained as 'start of last month'",
      sorted(e[0] for e in r2["slots"][0]) == ["literal", "month_start"], r2["slots"][0])
check("...so it replays in November", jr.plan(r2, TASK, MODE, date(2026, 11, 20))[0]["args"]["from"] == "2026-10-01")
check("...and refuses to guess on the first of December", jr.plan(r2, TASK, MODE, date(2026, 12, 1)) is None)
observe(date(2026, 12, 1), fixed(date(2026, 12, 1)), job=JOB2)
check("the December run proves it was a fixed date",
      jr.load(BRAIN, JOB2)["slots"][0] == [["literal", "2026-10-01"]], jr.load(BRAIN, JOB2)["slots"][0])

# a chain that changes is not a recipe
JOB3 = "reminder:r_changing:1"
observe(TUE, [{"tool": "shop__orders", "args": {"id": 1}}], job=JOB3)
check("a different chain the next day starts over", observe(WED, [{"tool": "shop__orders", "args": {"id": 2}}], job=JOB3) == "reset")
check("...and is not replayable", jr.plan(jr.load(BRAIN, JOB3), TASK, MODE, THU) is None)
JOB4 = "reminder:r_failed:1"
check("a run that produced nothing teaches nothing", observe(TUE, week_steps(TUE), job=JOB4, ok=False) == ""
      and jr.load(BRAIN, JOB4) is None)
check("a one-off or foreign job key is ignored", jr.base_job("kanban:12") == "" and jr.base_job("scout:ab") == ""
      and jr.base_job("reminder:r1:99") == "reminder:r1")
jr.begin("reminder:r_ref:1")
jr.note_call("reminder:r_ref:1", "javis_query", {"ref": "tr_" + "a" * 24, "sql": "SELECT 1"}, ok=True)
check("a reference from outside the run makes the recording unusable",
      jr.finish(BRAIN, "reminder:r_ref:1", ok=True, task=TASK, mode=MODE, run_day=TUE) == "")
jr.begin("reminder:r_desc:1")
jr.note_call("reminder:r_desc:1", "shop__pos_describe", {"action": "list"}, ok=True)
jr.note_call("reminder:r_desc:1", "shop__stats", {"day": "2026-11-10"}, ok=True)
jr.finish(BRAIN, "reminder:r_desc:1", ok=True, task=TASK, mode=MODE, run_day=TUE)
check("calls that only teach how to call a tool are not replayed",
      "describe" not in jr.load(BRAIN, "reminder:r_desc:1")["skeleton"])
check("the recipe is a readable file in the brain",
      os.path.isfile(os.path.join(BRAIN, "Javis", "recipes", "reminder_r_week.json")))

# ============================================================
# 3. Through the hub: record a real run, replay it another day
# ============================================================
_calls = []


def stats_page(args):
    return json.dumps({"data": [{"day": args.get("from"), "revenue": 100, "orders": 3, "empty": None, "note": "n" * 40},
                                {"day": args.get("to"), "revenue": 250, "orders": 5, "empty": None, "note": "n" * 40}] * 200,
                       "summary": {"from": args.get("from"), "to": args.get("to")}}, indent=2)


class _Pool:
    async def call_tool(self, spec, tool, args):
        _calls.append((tool, dict(args or {})))
        if tool == "get_stats":
            return _calls and _fail_next.pop() if _fail_next else stats_page(args or {})
        if tool == "send_message":
            return "sent"
        if tool == "describe_tools":
            return "how to call"
        return "OK"


_fail_next = []
CONN = {"id": "shop1", "connector_id": "recipe-test-shop", "label": "Shop", "slug": "shop", "namespace": "shop",
        "perm": "full", "deny_tools": []}
_real_get = mcp_catalog.get
mcp_catalog.get = lambda cid: ({"id": cid, "name": "Shop", "tool_meta": {"read": ["get_*", "describe_*"], "danger": ["send_*"]}}
                               if cid == "recipe-test-shop" else _real_get(cid))


async def _fake_discover(conns, bo_qua=None):
    spec = {"transport": "http", "url": "https://shop.test/mcp", "headers": {}}
    tools, route = [], {}
    for name in ("get_stats", "send_message", "describe_tools"):
        fn = f"shop__{name}"
        route[fn] = {"spec": spec, "tool": name, "conn": dict(CONN)}
        tools.append({"fn": fn, "server": "shop", "name": name, "description": name,
                      "schema": {"type": "object", "properties": {}}, "conn_id": "shop1",
                      "connector_id": CONN["connector_id"], "namespace": "shop", "label": "Shop"})
    return tools, route

mcp_store.resolved = lambda enabled_only=True: [dict(CONN, transport="http", url="https://shop.test/mcp", headers={}, env={})]
mcp_client.discover_resolved = _fake_discover
mcp_client.pool = _Pool()
mcp_hub._builtin_tools = lambda *a, **k: ([], {})
_settings = {"mcp": {"lazy_tools": "on"}}
config.read_settings = lambda: json.loads(json.dumps(_settings))
shaper.settings(force=True)
mcp_hub._cache.clear()
HUB_BRAIN = tempfile.mkdtemp(prefix="recipes-hub-brain-")
HJOB = "reminder:r_daily:1731300000"
HTASK = "7h sáng báo doanh thu hôm qua rồi gửi vào nhóm"


async def model_run(day):
    """What a model does on `day`: learn the tool, read yesterday's numbers, compute, then act."""
    tools, route = await mcp_hub.discover_all("full", vault_root=HUB_BRAIN, include_plugins=False)
    tok = turn_context.bind(turn_context.make("reminder", job=HJOB))
    try:
        jr.begin(HJOB)
        y = date.fromordinal(day.toordinal() - 1).isoformat()
        await engine._call_tool_for_model(route, mcp_hub._LAZY_RUN, {"name": "shop__describe_tools", "args": {}})
        seen = await engine._call_tool_for_model(route, mcp_hub._LAZY_RUN,
                                                 {"name": "shop__get_stats", "args": {"from": y, "to": y}})
        ref = json.loads(seen)["javis_stored_result"]["ref"]
        await engine._call_tool_for_model(route, "javis_query", {"ref": ref, "sql": "SELECT SUM(revenue) FROM records"})
        await engine._call_tool_for_model(route, mcp_hub._LAZY_RUN, {"name": "shop__send_message", "args": {"text": "hi"}})
    finally:
        turn_context.reset(tok)
    return jr.finish(HUB_BRAIN, HJOB, ok=True, task=HTASK, mode="full", run_day=day)


check("day one through the hub: learned", run(model_run(TUE)) == "learned")
check("day two through the hub: confirmed", run(model_run(WED)) == "confirmed")
hr = jr.load(HUB_BRAIN, HJOB)
skel_steps = json.loads(hr["skeleton"])
check("only the reads were recorded: no describe call, no send",
      [s["tool"] for s in skel_steps] == ["shop__get_stats", "javis_query"], [s["tool"] for s in skel_steps])
check("the query step points at the step that produced its data, not at a dead reference",
      skel_steps[1]["args"]["ref"] == "{{ref0}}", skel_steps[1])
plan = jr.plan(hr, HTASK, "full", THU)
check("day three: yesterday is recomputed", plan[0]["args"] == {"from": "2026-11-11", "to": "2026-11-11"}, plan)


async def do_replay(steps):
    tools, route = await mcp_hub.discover_all("full", vault_root=HUB_BRAIN, include_plugins=False)
    tok = turn_context.bind(turn_context.make("reminder", job=HJOB))
    try:
        jr.begin(HJOB)
        jr.pause(HJOB)
        results = await jr.replay(steps, route)
        jr.replay_done(HUB_BRAIN, HJOB, bool(results))
        return results
    finally:
        turn_context.reset(tok)

_calls.clear()
results = run(do_replay(plan))
check("the replay calls the source for the new period, once",
      [c for c in _calls if c[0] == "get_stats"] == [("get_stats", {"from": "2026-11-11", "to": "2026-11-11"})], _calls)
check("it never sends anything", all(c[0] != "send_message" for c in _calls))
check("the query step ran on the fresh data", results and json.loads(results[1][2])["rows"] == [[(100 + 250) * 200]], results and results[1][2][:200])
block = jr.prompt_block(results, THU)
check("the model is shown the arguments used, so a wrong period is visible",
      '"from": "2026-11-11"' in block and "KIỂM TRA tham số" in block and "shop__get_stats" in block)
check("the block stays within its budget", len(block) <= jr.PREFETCH_TOTAL_CHARS + 2000, len(block))
check("a replayed run does not re-record itself", jr.finish(HUB_BRAIN, HJOB, ok=True, task=HTASK, mode="full", run_day=THU) == "replayed"
      and jr.load(HUB_BRAIN, HJOB)["replays"] == 1 and jr.load(HUB_BRAIN, HJOB)["observations"] == 2)

# a failing step: fall back, count it, and drop the recipe after two in a row
_fail_next.append("ERROR: upstream 500")
check("a step that errors cancels the replay", run(do_replay(plan)) is None)
check("the failure is counted", jr.load(HUB_BRAIN, HJOB)["fails"] == 1)
jr.finish(HUB_BRAIN, HJOB, ok=True, task=HTASK, mode="full", run_day=THU)
_fail_next.append("ERROR: upstream 500")
run(do_replay(plan))
check("two failed replays in a row delete the recipe", jr.load(HUB_BRAIN, HJOB) is None)
jr.finish(HUB_BRAIN, HJOB, ok=True, task=HTASK, mode="full", run_day=THU)

check("a recipe step that is not a read is refused at replay time",
      run(do_replay([{"tool": "shop__send_message", "args": {"text": "x"}}])) is None and all(c[0] != "send_message" for c in _calls))
check("a recipe step whose tool is gone is refused", run(do_replay([{"tool": "shop__gone", "args": {}}])) is None)
check("a step that needs an earlier step's data cannot run alone",
      run(do_replay([{"tool": "javis_query", "args": {"ref": "{{ref0}}", "sql": "SELECT 1"}}])) is None)
jr.finish(HUB_BRAIN, HJOB, ok=False, task=HTASK, mode="full", run_day=THU)

# ============================================================
# 4. The reminder runner hands the prefetched data to the model
# ============================================================
run(model_run(TUE))
run(model_run(WED))
_GOT = {}


class _CLI:
    max_wall_s = None
    mcp_config = None
    mcp_strict = False
    disallowed_tools = None

    def is_available(self):
        return True

    async def query(self, prompt):
        _GOT["prompt"] = prompt
        yield {"type": "final", "content": "xong"}


class _Deps:
    safe_tools = ["Read", "Write"]
    readonly_tools = ["Read"]
    mcp_allow_patterns = staticmethod(lambda: [])
    aux_swap = None
    aux_model = staticmethod(lambda: None)
    apply_mcp = None
    build_agent_prompt = None
    finish_agent_run = None

    @staticmethod
    def brain_root(brain):
        return HUB_BRAIN

    @staticmethod
    def build_system_prompt(brain):
        return "sysprompt"


R.claude_engine = lambda **kw: _CLI()
feature = R.RemindersFeature(_Deps())
_real_today = jr.today
jr.today = lambda tz=None: THU


async def fire(recipe_job):
    tok = turn_context.bind(turn_context.make("reminder", job=HJOB))
    rtok = R._RECIPE_JOB.set(recipe_job)
    try:
        return await feature._run_task("brain", HTASK, "full")
    finally:
        R._RECIPE_JOB.reset(rtok)
        turn_context.reset(tok)

_calls.clear()
body, err = run(fire(HJOB))
check("the job still runs and answers", body == "xong" and not err, (body, err))
check("the model's prompt carries the prefetched data for the right day",
      "DỮ LIỆU JAVIS ĐÃ LẤY SẴN" in _GOT["prompt"] and '"from": "2026-11-11"' in _GOT["prompt"], _GOT["prompt"][-400:])
check("the task itself is still in the prompt", HTASK in _GOT["prompt"])
check("the run is closed as a replay", jr.finish(HUB_BRAIN, HJOB, ok=True, task=HTASK, mode="full", run_day=THU) == "replayed")
_GOT.clear()
body, err = run(fire(""))
check("a one-off reminder gets no prefetch", "DỮ LIỆU JAVIS ĐÃ LẤY SẴN" not in _GOT["prompt"])
_GOT.clear()
_fail_next.append("ERROR: upstream 500")
body, err = run(fire(HJOB))
check("a failed prefetch: the job runs the normal way, nothing half-injected",
      body == "xong" and "DỮ LIỆU JAVIS ĐÃ LẤY SẴN" not in _GOT["prompt"])
jr.finish(HUB_BRAIN, HJOB, ok=True, task=HTASK, mode="full", run_day=THU)
jr.today = _real_today

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL: " + "; ".join(_fails))
print("All green")
