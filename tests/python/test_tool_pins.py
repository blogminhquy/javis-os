"""Pinned tools: the tools a brain really uses skip the search round (tool_pins.py, 10/11/2026).

    python tests/run.py tool_pins

What is locked here:
1. Counting costs nothing during a call (memory only) and survives a restart through one small file.
2. A tool earns its pin with enough recent calls AND a real share of them; it keeps the pin until it falls well
   below that bar, loses weight every day it is not called, and never exceeds the size bounds.
3. A brain's list changes at most once a day and keeps its order, so the front of the prompt stays stable.
4. In the hub a pinned tool is shown directly and is called without a search; the permission layer still wraps it;
   a pin the current level does not hold is simply not shown; an owner's brain and its customer bot keep
   separate lists; the cache key follows the pins.
5. The limit is one knob of Javis Core's loop: the rule gives one more place when a tool waits, the owner switches
   pinning off with 0 and no rule switches it back on.

No network, no engine.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tool-pins-"))
os.environ["JAVIS_AUTO_BACKGROUND_PAUSED"] = "1"

import config  # noqa: E402
import core_loop as cl  # noqa: E402
import job_scorecard as sc  # noqa: E402
import mcp_hub  # noqa: E402
import tool_pins as tp  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        _fails.append(name)


DAY = 86400
T0 = (int(time.time()) // DAY) * DAY + 3600     # one hour into a day, so "the same day" is unambiguous
BRAIN = "/tmp/brains/Minh Quy"
K = tp.key(BRAIN)

# ============================================================
# 1. Keys and counting
# ============================================================
tp.reset_for_tests()
check("no brain, no counter", tp.key("") == "" and tp.key(None) == "")
check("the same brain written two ways is one counter", tp.key(BRAIN + "/") == K)
check("a customer bot of the brain has its own counter", tp.key(BRAIN, bot=True) == K + tp.BOT_SUFFIX != K)
check("the name shown to the owner is the brain's folder", tp.brain_name(K) == "Minh Quy" == tp.brain_name(K + tp.BOT_SUFFIX))
tp.note_run("", "x__a", 100)
tp.note_search("")
check("a call with no brain is not counted", tp.status() == [])
check("a brain nobody counted has no pins", tp.pinned(K) == () and tp.pinned("") == ())

# ============================================================
# 2. The pure pick
# ============================================================
sizes = {f: 400 for f in "abcdefghij"}
runs = {"a": 40, "b": 30, "c": 20, "d": 6, "e": 4, "f": 1}
pins, waiting = tp.pick(runs, sizes, [], 4)
check("the most called tools are pinned, strongest first", pins == ["a", "b", "c", "d"], pins)
check("a tool under the call bar is not pinned, and nothing waits when nothing else earned a place",
      "e" not in pins and waiting == "")
pins, waiting = tp.pick(runs, sizes, [], 2)
check("with no free place the next earned tool waits", pins == ["a", "b"] and waiting == "c", (pins, waiting))
check("limit 0 pins nothing", tp.pick(runs, sizes, ["a"], 0) == ([], ""))
check("no calls, no pins", tp.pick({}, sizes, ["a"], 4) == ([], ""))

many = {"a": 500, "b": 6}
check("enough calls but a share too small to matter is not pinned", tp.pick(many, sizes, [], 4)[0] == ["a"])

faded = {"a": 40, "b": 30, "c": 20, "d": 3}
check("a pinned tool keeps its place under the bar, until half of it", tp.pick(faded, sizes, ["d", "a"], 4)[0][:2] == ["d", "a"])
gone = {"a": 40, "b": 30, "c": 20, "d": 2}
check("under half the bar it leaves", "d" not in tp.pick(gone, sizes, ["d", "a"], 4)[0])
check("pins keep their order and new ones go to the end",
      tp.pick(runs, sizes, ["c", "a"], 4)[0] == ["c", "a", "b", "d"])

check("a tool whose schema is too large is never pinned",
      tp.pick(runs, {**sizes, "a": tp.MAX_TOOL_CHARS + 1}, [], 4)[0] == ["b", "c", "d"])
check("a tool of unknown size is never pinned", "a" not in tp.pick(runs, {k: v for k, v in sizes.items() if k != "a"}, [], 4)[0])
big = {f: 1800 for f in "abcd"}
pins, waiting = tp.pick(runs, big, [], 4)
check("all pins together stay inside the character budget",
      sum(big[f] for f in pins) <= tp.BUDGET_CHARS and pins == ["a", "b"], pins)
check("a tool kept out by the budget is not 'waiting for a place'", waiting == "")

full = {"a": 40, "b": 30, "c": 10, "z": 25}
check("with no free place, a tool called twice as much as the weakest pin takes its place",
      tp.pick(full, {**sizes, "z": 400}, ["a", "b", "c"], 3)[0] == ["a", "b", "z"])
close = {"a": 40, "b": 30, "c": 20, "z": 25}
pins, waiting = tp.pick(close, {**sizes, "z": 400}, ["a", "b", "c"], 3)
check("a tool only a little ahead does not push a pin out, it waits", pins == ["a", "b", "c"] and waiting == "z")
check("a lower limit keeps the strongest pins", tp.pick(runs, sizes, ["d", "c", "b", "a"], 2)[0] == ["b", "a"])

# ============================================================
# 3. tick: lists follow use, once a day, and survive a restart
# ============================================================
tp.reset_for_tests()
seen = []
tp.on_change = seen.append
for fn, n in (("zalo__list_join", 20), ("zalo__history", 14), ("pos__order", 6), ("rare__tool", 1)):
    for _ in range(n):
        tp.note_run(K, fn, 500)
tp.note_search(K)
check("nothing is pinned before the loop looked", tp.pinned(K) == ())
ch = tp.tick(now=T0)
check("the first look pins what the brain calls most",
      tp.pinned(K) == ("zalo__list_join", "zalo__history", "pos__order") and len(ch) == 1, tp.pinned(K))
check("the change says which brain and which tools were added",
      ch[0]["brain"] == "Minh Quy" and ch[0]["added"] == list(tp.pinned(K)) and ch[0]["removed"] == [] and not ch[0]["bot"])
check("the change is announced once", seen == ch)

for _ in range(30):
    tp.note_run(K, "ads__insights", 500, direct=False)
check("a list does not change twice in a day", tp.tick(now=T0 + 3600) == [] and "ads__insights" not in tp.pinned(K))
ch = tp.tick(now=T0 + DAY + 60)
check("a day later the new habit is pinned, after the old pins",
      tp.pinned(K) == ("zalo__list_join", "zalo__history", "pos__order", "ads__insights") and ch[0]["added"] == ["ads__insights"],
      tp.pinned(K))

path = tp._path()
check("the counts are written by the tick, not by the call", path.is_file()
      and json.loads(path.read_text(encoding="utf-8"))["brains"][K]["pins"] == list(tp.pinned(K)))
before = tp.pinned(K)
tp._loaded[0] = False
tp._state.update({"limit": tp.LIMIT_DEFAULT, "brains": {}})
check("a restart reads the pins back", tp.pinned(K) == before)

st = tp.status()
check("status shows the pins and the counters per brain",
      len(st) == 1 and st[0]["brain"] == "Minh Quy" and st[0]["pinned"] == list(before)
      and st[0]["searches"] > 0 and st[0]["calls_after_search"] > 0 and st[0]["audience"] == "owner", st)

# A tool nobody calls any more fades and leaves on its own.
later = T0 + DAY + 60
for d in range(1, 40):
    for _ in range(3):
        tp.note_run(K, "zalo__list_join", 500, direct=True)
    tp.tick(now=later + d * DAY)
check("tools that are no longer called lose their pin with time", tp.pinned(K) == ("zalo__list_join",), tp.pinned(K))
check("calls of a pinned tool are counted as direct", tp.status()[0]["calls_direct"] > 0)

# A broken file only restarts the counting.
path.write_text("{not json", encoding="utf-8")
tp._loaded[0] = False
tp._state.update({"limit": tp.LIMIT_DEFAULT, "brains": {}})
check("a broken state file does not break a call", tp.pinned(K) == () and tp.note_run(K, "a__b", 10) is None)

# ============================================================
# 4. The hub: a pinned tool is shown directly and called without a search
# ============================================================
_calls = []


def _guarded(fn):
    async def _call(args):
        _calls.append((fn, args))
        return f"OK[{fn}]"
    return _call


def _tool(fn, ns, desc):
    spec = {"fn": fn, "server": ns, "name": fn.split("__", 1)[-1], "description": desc,
            "schema": {"type": "object", "properties": {"x": {"type": "string"}}},
            "conn_id": "c1", "connector_id": "pos", "namespace": ns, "label": ns}
    return spec, {"call": _guarded(fn), "conn": {"id": "c1", "namespace": ns}, "tool": spec["name"]}


def _fixture():
    tools, route = [], {}
    for fn, ns, desc in (("javis_read_file", "javis", "đọc file"), ("pos__pos_order", "pos", "Đơn hàng POS"),
                         ("pos__pos_stock", "pos", "Tồn kho"), ("ads__ads_insights", "ads", "Hiệu suất quảng cáo")):
        s, e = _tool(fn, ns, desc)
        if fn == "javis_read_file":
            e = {"call": _guarded(fn)}
        tools.append(s)
        route[fn] = e
    return tools, route


config.read_settings = lambda: {"mcp": {"lazy_tools": True}}   # type: ignore[assignment]
tp.reset_for_tests()
tools, route = _fixture()
lt, lr = mcp_hub._apply_lazy(tools, route, pins_key=K, pins=())
fns = [t["fn"] for t in lt]
check("with no pins the lazy tier is what it was: core tools and the two meta tools",
      fns == ["javis_read_file", mcp_hub._LAZY_SEARCH, mcp_hub._LAZY_RUN], fns)

res = asyncio.run(lr[mcp_hub._LAZY_RUN]["call"]({"name": "pos__pos_order", "args": {"x": "1"}}))
asyncio.run(lr[mcp_hub._LAZY_SEARCH]["call"]({"query": "đơn hàng"}))
st = tp.status()[0]
check("a tool reached through search and run is counted, with its size",
      res == "OK[pos__pos_order]" and st["calls_after_search"] == 1 and st["searches"] == 1
      and tp._state["brains"][K]["sizes"]["pos__pos_order"] == mcp_hub._tool_chars(tools[1]), st)
asyncio.run(lr[mcp_hub._LAZY_RUN]["call"]({"name": "javis_read_file", "args": {}}))
asyncio.run(lr[mcp_hub._LAZY_RUN]["call"]({"name": "no__such", "args": {}}))
check("a core tool or a wrong name called through run is not counted", tp.status()[0]["calls_after_search"] == 1)

lt0, lr0 = mcp_hub._apply_lazy(tools, route)
asyncio.run(lr0[mcp_hub._LAZY_RUN]["call"]({"name": "pos__pos_stock", "args": {}}))
asyncio.run(lr0[mcp_hub._LAZY_SEARCH]["call"]({"query": "tồn kho"}))
check("a caller that names no brain counts nothing", tp.status()[0]["calls_after_search"] == 1 and tp.status()[0]["searches"] == 1)

pins = ("pos__pos_order", "gone__tool")
lt, lr = mcp_hub._apply_lazy(tools, route, pins_key=K, pins=pins)
fns = [t["fn"] for t in lt]
check("a pinned tool is shown directly, after the core tools and before the meta tools",
      fns == ["javis_read_file", "pos__pos_order", mcp_hub._LAZY_SEARCH, mcp_hub._LAZY_RUN], fns)
check("a pin this list does not hold (other permission level, source removed) is simply not shown",
      "gone__tool" not in fns and "gone__tool" not in lr)
_calls.clear()
res = asyncio.run(lr["pos__pos_order"]["call"]({"x": "2"}))
check("calling it directly goes through the same wrapped call, with no search",
      res == "OK[pos__pos_order]" and _calls == [("pos__pos_order", {"x": "2"})])
check("the route entry keeps what the permission layer reads", lr["pos__pos_order"]["conn"]["namespace"] == "pos"
      and lr["pos__pos_order"]["tool"] == "pos_order")
check("the direct call is counted as one search round saved", tp.status()[0]["calls_direct"] == 1)
check("the pinned tool can still be found and run the old way",
      "pos__pos_order" in asyncio.run(lr[mcp_hub._LAZY_SEARCH]["call"]({"query": "đơn hàng POS"}))
      and asyncio.run(lr[mcp_hub._LAZY_RUN]["call"]({"name": "pos__pos_order", "args": {}})) == "OK[pos__pos_order]")
check("the original route is not touched", route["pos__pos_order"]["call"] is not lr["pos__pos_order"]["call"])

fat_tools, fat_route = _fixture()
fat_tools[1] = {**fat_tools[1], "description": "x" * (tp.MAX_TOOL_CHARS + 1)}
lt_fat, lr_fat = mcp_hub._apply_lazy(fat_tools, fat_route, pins_key=K, pins=("pos__pos_order", "pos__pos_stock"))
check("a pinned tool whose description grew past the bound is not shown, the next one still is",
      [t["fn"] for t in lt_fat] == ["javis_read_file", "pos__pos_stock", mcp_hub._LAZY_SEARCH, mcp_hub._LAZY_RUN])
wide_tools, wide_route = _fixture()
for i in (1, 2, 3):
    wide_tools[i] = {**wide_tools[i], "description": "y" * 1900}
lt_wide, _ = mcp_hub._apply_lazy(wide_tools, wide_route, pins_key=K,
                                 pins=("pos__pos_order", "pos__pos_stock", "ads__ads_insights"))
shown = [t for t in lt_wide if t["fn"] in ("pos__pos_order", "pos__pos_stock", "ads__ads_insights")]
check("the pins shown in one request never exceed the character budget",
      len(shown) == 2 and sum(mcp_hub._tool_chars(t) for t in shown) <= tp.BUDGET_CHARS)

config.read_settings = lambda: {"mcp": {"lazy_tools": "off"}}   # type: ignore[assignment]
lt_off, lr_off = mcp_hub._apply_lazy(tools, route, pins_key=K, pins=pins)
check("with the lazy tier off nothing changes: every tool is already shown", lt_off is tools and lr_off is route)

# The whole path once, on a real (empty) brain: count through run, let the loop look, list again.
config.read_settings = lambda: {"mcp": {"lazy_tools": True}}   # type: ignore[assignment]
tp.reset_for_tests()
_vault = tempfile.mkdtemp(prefix="javis-pins-brain-")


async def _whole_path():
    t1, r1 = await mcp_hub.discover_all("full", vault_root=_vault)
    for _ in range(6):
        await r1[mcp_hub._LAZY_RUN]["call"]({"name": "javis_connections", "args": {}})
    tp.tick()
    t2, r2 = await mcp_hub.discover_all("full", vault_root=_vault)
    t3, _r3 = await mcp_hub.discover_all("full", vault_root=_vault, for_bot=True)
    return [t["fn"] for t in t1], [t["fn"] for t in t2], [t["fn"] for t in t3], r2

f1, f2, f3, r2 = asyncio.run(_whole_path())
check("a tool the brain keeps calling is listed directly on the next turn, without waiting for the cache",
      "javis_connections" not in f1 and "javis_connections" in f2 and "javis_connections" in r2, (f1, f2))
check("the core tools still come first and the meta tools last",
      f2[:len(f1) - 2] == f1[:-2] and f2[-2:] == [mcp_hub._LAZY_SEARCH, mcp_hub._LAZY_RUN], f2)
check("the customer bot of that brain keeps its own list", "javis_connections" not in f3, f3)

src = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
disc = src.split("async def discover_all(", 1)[1].split("\ndef _stale_servable(", 1)[0]
check("discover_all keys its cache by the pins, with the session id still last",
      "pins, str(_sid_ctx or \"\"))" in disc and "tool_pins.key(vault_root, bot=for_bot)" in disc)
check("discover_all hands the same pins to the lazy tier", "pins_key=pins_key, pins=pins)" in disc)

# ============================================================
# 5. The limit is a knob of Javis Core's loop
# ============================================================
sc.reset_for_tests()
cl.reset_for_tests()
tp.reset_for_tests()
tp.on_change = None
knob = cl.register(cl.Knob(id="tools.pin_limit", title_vi="Số công cụ ghim sẵn tối đa mỗi brain",
                           title_en="Tools one brain may pin", lo=tp.LIMIT_LO, hi=tp.LIMIT_HI,
                           default=tp.LIMIT_DEFAULT, read=tp.limit, write=tp.set_limit, rule=tp.limit_rule))
check("the limit starts at its default", tp.limit() == tp.LIMIT_DEFAULT == 4)
for i, n in enumerate((40, 30, 20, 15, 12, 10)):
    for _ in range(n):
        tp.note_run(K, f"src__tool{i}", 300)
tp.tick(now=T0)
check("a brain pins up to the limit and the next earned tool waits",
      len(tp.pinned(K)) == 4 and tp._state["brains"][K]["waiting"] == "src__tool4", tp.pinned(K))
check("with a tool waiting the rule asks for one more place", (tp.limit_rule(4) or (0,))[0] == 5)
moved = cl.tick(now=T0)
check("the rule gives one more place, with the reason", tp.limit() == 5 and len(moved) == 1
      and "src__tool4" in moved[0]["why"] and "Minh Quy" in moved[0]["why"], moved)
tp.tick(now=T0 + 600)
check("the new place is filled on the next look, not a day later", tp.pinned(K)[-1] == "src__tool4" and len(tp.pinned(K)) == 5)

ch = cl.change("tools.pin_limit", 0, "owner", "chủ bảo đừng ghim")
check("the owner switches pinning off with 0, at once", ch and tp.limit() == 0 and tp.pinned(K) == ())
check("at 0 the rule proposes nothing", tp.limit_rule(0) is None)
check("no rule touches a knob the owner set, for a month",
      cl.tick(now=time.time() + 5 * cl.COOLDOWN_S) == [] and tp.limit() == 0
      and cl._held["tools.pin_limit"] > time.time() + cl.HOLD_AFTER_OWNER_S - 60)
cl._KNOBS.clear()
cl._held.clear()
cl._last_move.clear()
cl._loaded[0] = False
cl.register(knob)
cl.status()
check("the owner's hold survives a restart", cl._held.get("tools.pin_limit", 0) > time.time() + cl.HOLD_AFTER_OWNER_S - 120)

cl._held.clear()
tp.set_limit(6)
tp.tick(now=T0 + 3 * DAY)
check("every earned tool has a place and the limit is full: the rule proposes nothing",
      len(tp.pinned(K)) == 6 and tp.limit_rule(6) is None, tp.pinned(K))
tp.set_limit(8)
tp.tick(now=T0 + 5 * DAY)
check("above the default with places nobody fills, the rule takes one back",
      len(tp.pinned(K)) == 6 and tp.limit_rule(8) == (7, "không brain nào dùng hết số chỗ ghim"), tp.pinned(K))
tp.set_limit(4)
tp.tick(now=T0 + 7 * DAY)
check("at the default it does not go lower by itself", len(tp.pinned(K)) == 4 and (tp.limit_rule(4) or (0,))[0] == 5)
tp._state["brains"][K]["waiting"] = "src__toolx"
r = tp.limit_rule(tp.LIMIT_HI)
check("with a tool waiting at the top of the range, the rule does not ask for more", r is None or r[0] < tp.LIMIT_HI, r)

# ============================================================
# 6. What the owner sees
# ============================================================
import job_tune  # noqa: E402
import main  # noqa: E402

st = json.loads(job_tune.run({"op": "status"}))
check("javis_tune status lists the pinned tools per brain and how to switch them off",
      st.get("ok") and st["pinned_tools"] and st["pinned_tools"][0]["brain"] == "Minh Quy"
      and "tools.pin_limit" in st["pinned_tools_note"], st.get("pinned_tools"))
check("the knob is registered by the server", any(k.id == "tools.pin_limit" for k in cl.knobs()))
res = json.loads(job_tune.run({"op": "set", "knob": "tools.pin_limit", "value": 0}))
check("the owner turns pinning off in chat", res.get("ok") and tp.limit() == 0, res)

sent = []


async def _fake_notify(owner_chat, text, **kw):
    sent.append((text, kw))


real_notify = main._notify_owner
main._notify_owner = _fake_notify


async def _announce():
    main._pins_changed({"key": K, "brain": "Minh Quy", "bot": False, "added": ["zalo__list_join", "pos__order"],
                        "removed": [], "pins": ["zalo__list_join", "pos__order"]})
    main._pins_changed({"key": K, "brain": "Minh Quy", "bot": False, "added": [], "removed": ["old__tool"], "pins": []})
    await asyncio.sleep(0)


asyncio.run(_announce())
main._notify_owner = real_notify
check("new pins get one quiet notice naming the brain, the tools and the way to stop",
      len(sent) == 1 and "Minh Quy" in sent[0][0] and "zalo__list_join" in sent[0][0]
      and "đừng ghim công cụ nữa" in sent[0][0] and sent[0][1].get("level") == "info", sent)
check("a tool that only left the list is not announced", len(sent) == 1)
check("no long dash in the notice", chr(0x2014) not in sent[0][0] and chr(0x2013) not in sent[0][0])

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    raise SystemExit(1)
print("OK - test_tool_pins: tất cả pass")
