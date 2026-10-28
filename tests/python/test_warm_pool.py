"""0.382.0: engine processes kept warm between the owner's chat turns (warm_pool.py, claude_warm.py, turn_lane.Lane).

Spec: docs/dev/2026-10-toc-do-luot-chat-spec.md. Covers the pool (budget, LRU, idle, fingerprint, prewarm), the lane
key that lets a warm process carry the running turn to the hub, what makes a Claude turn eligible and what its
fingerprint ignores, and the wiring in main.py and the dashboard. The Codex side is in test_codex_steer_0213.py.

Run:
    python tests/run.py warm_pool
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import sys
import time
import types

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-warm-")

import turn_context  # noqa: E402
import turn_lane  # noqa: E402
import warm_pool  # noqa: E402

fails = []


def check(name, cond, detail=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or detail is None else f"  -> {detail!r}"))
    if not cond:
        fails.append(name)


class FakeHandle(warm_pool.Handle):
    def __init__(self, kind="claude"):
        self.kind = kind
        self.is_alive = True
        self.closed = False

    def alive(self):
        return self.is_alive and not self.closed

    async def close(self):
        self.closed = True


async def settle():
    for _ in range(5):
        await asyncio.sleep(0)


# ---- the pool ----
async def pool_cases():
    os.environ["JAVIS_WARM_BUDGET_MB"] = "400"
    pool = warm_pool.Pool()
    a = FakeHandle("claude")
    s = pool.admit("A", "claude", "fpA", a)
    check("a cold turn's process is admitted when it fits", s is not None and s.busy)
    pool.release(s)
    check("released: idle, kept", not s.busy and not a.closed and pool.status()["used_mb"] == 300)
    hit = pool.take("A", "claude", "fpA")
    check("the next turn with the same fingerprint gets it", hit is s and hit.busy)
    pool.release(hit)
    c = FakeHandle("codex")
    sc = pool.admit("C", "codex", "fpC", c)
    pool.release(sc)
    check("a codex slot fits next to it (300 + 80 <= 400)", pool.status()["used_mb"] == 380 and not a.closed)
    b = FakeHandle("claude")
    sb = pool.admit("B", "claude", "fpB", b)
    await settle()
    check("full: the idle slot used longest ago is evicted", sb is not None and a.closed and not c.closed)
    # B is busy now; another Claude slot does not fit without evicting it
    d = FakeHandle("claude")
    sd = pool.admit("D", "claude", "fpD", d)
    await settle()
    check("a busy slot is never evicted: the new process is refused", sd is None and not b.closed)
    pool.release(sb)
    miss = pool.take("B", "claude", "other")
    await settle()
    check("another fingerprint: no slot, and the stale process is closed", miss is None and b.closed)
    e = FakeHandle("claude")
    se = pool.admit("E", "claude", "fpE", e)
    pool.release(se)
    e.is_alive = False
    check("a dead process is never handed out", pool.take("E", "claude", "fpE") is None)
    # idle expiry leaves a recipe, and prewarm reopens it
    opened = []

    async def recipe():
        h = FakeHandle("claude")
        opened.append(h)
        return h
    f = FakeHandle("claude")
    sf = pool.admit("F", "claude", "fpF", f, recipe=recipe)
    pool.release(sf)
    n = pool.reap(now=time.monotonic() + warm_pool.idle_s() + 1)
    await settle()
    check("idle past its time: closed by the reaper", n >= 1 and f.closed and "F" not in [k for k in pool._slots])
    check("prewarm reopens a conversation whose process was closed", pool.prewarm("F"))
    for _ in range(20):
        await asyncio.sleep(0.01)
    warm = pool.take("F", "claude", "fpF")
    check("the prewarmed process serves the next turn", warm is not None and warm.handle is opened[0]
          and pool.stats["prewarmed"] == 1)
    pool.release(warm)
    check("no second prewarm while it is open", not pool.prewarm("F"))
    check("prewarm without any recipe does nothing", not pool.prewarm("never-seen"))
    pool.forget("F")
    await settle()
    check("forget closes the slot and drops the recipe", opened[0].closed and not pool.prewarm("F"))
    os.environ["JAVIS_WARM_BUDGET_MB"] = "0"
    check("budget 0: nothing taken, nothing prewarmed", pool.take("C", "codex", "fpC") is None
          and not pool.prewarm("C"))
    g = FakeHandle("claude")
    check("budget 0: nothing admitted", pool.admit("G", "claude", "fpG", g) is None)
    os.environ["JAVIS_WARM_BUDGET_MB"] = "400"
    await pool.close_all()
    check("close_all closes every slot", c.closed and pool.status()["slots"] == [])
    del os.environ["JAVIS_WARM_BUDGET_MB"]
    check("default budget is a share of free RAM, at most 1200 MB",
          0 < warm_pool.budget_mb() <= warm_pool.MAX_BUDGET_MB and warm_pool.free_ram_mb() > 0)


asyncio.run(pool_cases())


async def prewarm_race():
    """A prewarm that lands after the owner's turn already ran cold must not replace that turn's newer process,
    and a prewarm never pushes another conversation out."""
    os.environ["JAVIS_WARM_BUDGET_MB"] = "400"
    pool = warm_pool.Pool()
    late = []

    async def slow_recipe():
        await asyncio.sleep(0.2)
        h = FakeHandle("claude")
        late.append(h)
        return h
    pool.remember("R", "claude", "fpR", slow_recipe)
    check("race: prewarm scheduled", pool.prewarm("R"))
    check("race: the turn arrives first and misses", pool.take("R", "claude", "fpR") is None)
    fresh = FakeHandle("claude")
    s = pool.admit("R", "claude", "fpR", fresh)
    pool.release(s)
    await asyncio.sleep(0.4)
    check("race: the turn's own process stays, the late prewarm is closed (or never opened)",
          pool._slots["R"].handle is fresh and all(h.closed for h in late))
    # Same race with room for both: the prewarm does open, and must still give way.
    os.environ["JAVIS_WARM_BUDGET_MB"] = "1000"
    late.clear()
    pool.remember("R2", "claude", "fpR2", slow_recipe)
    pool.prewarm("R2")
    pool.take("R2", "claude", "fpR2")
    fresh2 = FakeHandle("claude")
    pool.release(pool.admit("R2", "claude", "fpR2", fresh2))
    await asyncio.sleep(0.4)
    check("race with room: the prewarmed process opened, then gave way to the newer one",
          len(late) == 1 and late[0].closed and pool._slots["R2"].handle is fresh2)
    pool.forget("R2")
    os.environ["JAVIS_WARM_BUDGET_MB"] = "400"
    other = FakeHandle("claude")
    pool.remember("Q", "claude", "fpQ", slow_recipe)
    pool.prewarm("Q")
    await asyncio.sleep(0.4)
    check("prewarm never evicts: R stays, Q is not opened beyond the budget",
          "R" in pool._slots and not fresh.closed and "Q" not in pool._slots and not other.closed)
    await pool.close_all()
    del os.environ["JAVIS_WARM_BUDGET_MB"]


asyncio.run(prewarm_race())


# ---- a warm Claude client must be quiet before reuse ----
import anyio  # noqa: E402


class _Stream:
    def __init__(self, items):
        self.items = list(items)

    def receive_nowait(self):
        if not self.items:
            raise anyio.WouldBlock
        return self.items.pop(0)


def _handle_with(items):
    h = warm_pool.Handle.__new__(warm_pool.Handle)
    import claude_warm as cw
    ch = cw.ClaudeHandle(types.SimpleNamespace(_query=types.SimpleNamespace(_message_receive=_Stream(items))), None)
    return ch


import claude_warm  # noqa: E402,F811
check("quiet: nothing pending", _handle_with([]).quiet())
check("quiet: an end-of-turn system note is drained", _handle_with([{"type": "system", "subtype": "session_state_changed"}]).quiet())
check("not quiet: a background task's news is pending", not _handle_with([{"type": "system", "subtype": "task_started"}]).quiet())
check("not quiet: an answer the CLI produced on its own is pending", not _handle_with([{"type": "assistant"}]).quiet())
check("not quiet: a result is pending", not _handle_with([{"type": "result"}]).quiet())


# ---- the lane key ----
lane = turn_lane.Lane()
check("outside a turn the lane attaches to nobody", not lane.attach() and turn_context.resolve_key(lane.key) is None)
tok = turn_context.bind(turn_context.make("dashboard", chat_id="s1", la_chu=True))
check("inside a turn it points at that turn", lane.attach()
      and (turn_context.resolve_key(lane.key) or {}).get("chat_id") == "s1")
check("its context sees the running turn (hooks and in-process tools)",
      (lane.context().run(turn_context.current) or {}).get("chat_id") == "s1")
minted = lane.context().run(turn_context.issue_key)
check("a key minted inside the lane resolves while the turn runs", (turn_context.resolve_key(minted) or {}).get("chat_id") == "s1")
turn_context.reset(tok)
check("the turn ends: the lane key and its minted keys resolve to nobody",
      turn_context.resolve_key(lane.key) is None and turn_context.resolve_key(minted) is None
      and lane.context().run(turn_context.current) is None)
tok = turn_context.bind(turn_context.make("dashboard", chat_id="s2", la_chu=True))
lane.attach()
check("the next turn on the same process is the one it carries",
      (turn_context.resolve_key(lane.key) or {}).get("chat_id") == "s2")
lane.detach()
check("detach at the end of the query: nobody at once, before the turn resets",
      turn_context.resolve_key(lane.key) is None and lane.context().run(turn_context.current) is None)
turn_context.reset(tok)
lane.close()
check("a closed lane never resolves again", turn_context.resolve_key(lane.key) is None)
check("turn_context.py is untouched (pinned by the native qualification evidence)",
      "Lane" not in (SERVER / "turn_context.py").read_text(encoding="utf-8"))


# ---- Claude: eligibility and fingerprint ----
import claude_warm  # noqa: E402
from claude_cli import claude_engine  # noqa: E402

eng = claude_engine(system_prompt="x", cwd=tempfile.mkdtemp(), tag="chat:abc:1")
os.environ["JAVIS_WARM_BUDGET_MB"] = "400"
if type(eng).__name__ == "ClaudeSDK":
    check("the owner's chat engine is eligible", claude_warm.eligible(eng))
    eng.tag = "loop:x"
    check("background work is not", not claude_warm.eligible(eng))
    eng.tag = "chat:abc:1"
    eng.allowed_tools = ["Read"]
    check("a gated engine is not", not claude_warm.eligible(eng))
    eng.allowed_tools = None
    os.environ["JAVIS_WARM_BUDGET_MB"] = "0"
    check("budget 0: no engine is", not claude_warm.eligible(eng))
    os.environ["JAVIS_WARM_BUDGET_MB"] = "400"
else:
    print("skip eligibility: claude-agent-sdk not installed")


def opts(**kw):
    base = dict(cli_path="", cwd=eng.cwd, model="sonnet", effort=None, settings='{"fastMode": false}',
                permission_mode="bypassPermissions", setting_sources=["user"], disallowed_tools=[],
                include_partial_messages=True, include_hook_events=True, system_prompt={"type": "preset"},
                env={}, hooks=None, resume="S1",
                mcp_servers={"javis": {"type": "http", "url": "http://h/mcp",
                                       "headers": {"Authorization": "x", turn_context.HEADER: "k1"}}})
    base.update(kw)
    return types.SimpleNamespace(**base)


fp = claude_warm.fingerprint(eng, opts())
other_key = opts(mcp_servers={"javis": {"type": "http", "url": "http://h/mcp",
                                        "headers": {"Authorization": "x", turn_context.HEADER: "k2"}}})
check("the per-turn hub key is not part of the fingerprint", claude_warm.fingerprint(eng, other_key) == fp)
check("another system prompt text is not either (Claude keeps the first one on resume)",
      claude_warm.fingerprint(eng, opts(system_prompt={"type": "preset", "append": "new"})) == fp)
check("another model is", claude_warm.fingerprint(eng, opts(model="opus")) != fp)
check("another session is", claude_warm.fingerprint(eng, opts(resume="S2")) != fp)
check("another effort is", claude_warm.fingerprint(eng, opts(effort="high")) != fp)
check("another hub URL is", claude_warm.fingerprint(eng, opts(mcp_servers={"javis": {"url": "http://other"}})) != fp)
with open(os.path.join(eng.cwd, "CLAUDE.md"), "w") as f:
    f.write("edited")
check("an edited CLAUDE.md is (Claude Code reads it at start-up only)", claude_warm.fingerprint(eng, opts()) != fp)

# 0.387.0: the bug that kept 0.382.0 from ever reusing a process on a real brain. Claude Code rewrites its credentials
# file on every run, and the fingerprint had that file's stat in it, so every turn looked like a new config.
conf = tempfile.mkdtemp(prefix="javis-claude-conf-")
cred = os.path.join(conf, ".credentials.json")
with open(cred, "w") as f:
    f.write('{"claudeAiOauth": {"accessToken": "a1"}}')
fp_c = claude_warm.fingerprint(eng, opts(env={"CLAUDE_CONFIG_DIR": conf}))
time.sleep(0.05)
with open(cred, "w") as f:
    f.write('{"claudeAiOauth": {"accessToken": "a2-refreshed-longer"}}')
check("Claude Code rewriting its credentials file does not change the fingerprint",
      claude_warm.fingerprint(eng, opts(env={"CLAUDE_CONFIG_DIR": conf})) == fp_c)
check("another config folder (another plan account) does",
      claude_warm.fingerprint(eng, opts(env={"CLAUDE_CONFIG_DIR": conf + "-2"})) != fp_c)
parts_a = claude_warm.fingerprint_parts(eng, opts())
parts_b = claude_warm.fingerprint_parts(eng, opts(model="opus"))
check("a miss names what changed", claude_warm.changed_parts(parts_a, parts_b) == ["model"])

import codex_steer  # noqa: E402

chome = tempfile.mkdtemp(prefix="javis-codex-home-")
ccli = types.SimpleNamespace(cli_path=sys.executable, codex_home=chome, cwd=eng.cwd, sandbox=None, model="gpt-5.5",
                             session_id="th1")


def write_auth(account, stamp):
    with open(os.path.join(chome, "auth.json"), "w") as f:
        f.write('{"tokens": {"account_id": "%s", "access_token": "t%s"}, "last_refresh": "%s"}' % (account, stamp, stamp))


write_auth("acct-1", "1")
fp_x = codex_steer._fingerprint(ccli, ["codex", "app-server"])
time.sleep(0.05)
write_auth("acct-1", "2")
check("Javis rewriting auth.json each Codex turn (same account) does not change the fingerprint",
      codex_steer._fingerprint(ccli, ["codex", "app-server"]) == fp_x)
write_auth("acct-2", "3")
check("another ChatGPT account does", codex_steer._fingerprint(ccli, ["codex", "app-server"]) != fp_x)


async def drop_cases():
    os.environ["JAVIS_WARM_BUDGET_MB"] = "1000"
    pool = warm_pool.Pool()
    a, b = FakeHandle("claude"), FakeHandle("codex")
    pool.release(pool.admit("A", "claude", "x", a, recipe=lambda: None))
    pool.release(pool.admit("B", "codex", "y", b))
    n = pool.drop_kind("claude")
    await settle()
    check("a sign-in drops every Claude slot and recipe, and only those",
          n == 1 and a.closed and not b.closed and not pool.prewarm("A") and "B" in pool._slots)
    for i in range(warm_pool.MAX_RECIPES + 5):
        pool.remember(f"k{i}", "claude", "f", lambda: None)
    check("recipes are capped, oldest dropped first",
          len(pool._recipes) == warm_pool.MAX_RECIPES and "k0" not in pool._recipes and f"k{warm_pool.MAX_RECIPES + 4}" in pool._recipes)
    await pool.close_all()
    del os.environ["JAVIS_WARM_BUDGET_MB"]


asyncio.run(drop_cases())
check("a recipe lives long enough for a chat left over lunch", warm_pool.RECIPE_TTL_S >= 6 * 3600)

h = claude_warm.ClaudeHandle(None, turn_lane.Lane())
o = claude_warm._warm_options(eng, opts(), h)
check("warm options carry the lane key in the hub header",
      o.mcp_servers["javis"]["headers"][turn_context.HEADER] == h.lane.key
      and o.mcp_servers["javis"]["headers"]["Authorization"] == "x")
h.lane.close()


# ---- wiring ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("main: the dashboard Claude turn runs through claude_warm", src.count("claude_warm.query(cli, prompt, conv_sid)") == 1)
check("main: only the web chat Codex engine gets a warm key", src.count("ccli.warm_key = conv_sid") == 1)
check("main: the first output of a turn is timed", '"engine.first_output"' in src and "[turn timing]" in src)
check("main: typing asks the pool to prewarm", 'action == "typing"' in src and "warm_pool.POOL.prewarm(" in src)
check("main: warm processes close at shutdown", "await warm_pool.POOL.close_all()" in src)
check("main: Claude sign-in (both ways) and sign-out drop the warm Claude processes",
      src.count('warm_pool.POOL.drop_kind("claude")') == 3)
check("main: ChatGPT disconnect drops the warm Codex processes", src.count('warm_pool.POOL.drop_kind("codex")') == 1)
app = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8", errors="replace")
check("dashboard: the composer sends a throttled typing hint", 'action: "typing"' in app and "20000" in app)
for f in ("warm_pool.py", "claude_warm.py", "codex_steer.py", "turn_context.py"):
    check(f"no long dashes in {f}", not any(c in (SERVER / f).read_text(encoding="utf-8") for c in "–—"))

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
