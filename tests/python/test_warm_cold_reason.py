"""A cold chat turn says why it was cold, and a thread about to be rotated gets its new process opened ahead.

Measured 2026-11-23 on two weeks of real turns: 65% of Claude turns were cold and the `engine.first_output` event did
not say why. Reading the history back, 38% of all turns were cold because Javis had just rotated the thread (a new
thread never matched the process kept for the old one), 13% because the process had idled out, 9% were first turns.

Expected:
  - warm_pool.take names the reason of a miss (nothing kept, idle expired, evicted, config changed, process died...);
  - claude_warm tells an ineligible engine apart from a pool miss and names the fingerprint parts that changed;
  - the fingerprint leaves the system prompt text out for a new thread as it does for a resumed one (a warm process
    runs on the prompt it started with), except on the one turn whose context rides in the system prompt;
  - swap_recipe closes the idle resumed process first, then opens the new-thread one in the same slot (no extra RAM);
  - the next-turn rotation forecast is the real rule, one message later;
  - main writes the reason into the event and asks for the new-thread process when the next turn will rotate.

Run:
    python tests/run.py warm_cold_reason
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import time
import types

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-warm-why-")

import compaction  # noqa: E402
import warm_pool  # noqa: E402

fails = []


def check(name, cond, detail=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or detail is None else f"  -> {detail!r}"))
    if not cond:
        fails.append(name)


class FakeHandle(warm_pool.Handle):
    def __init__(self, kind="claude", log=None, name=""):
        self.kind = kind
        self.is_alive = True
        self.closed = False
        self.log = log
        self.name = name

    def alive(self):
        return self.is_alive and not self.closed

    async def close(self):
        self.closed = True
        if self.log is not None:
            self.log.append("close " + self.name)


async def settle(n=5):
    for _ in range(n):
        await asyncio.sleep(0)


def miss(pool, key, kind="claude", fp="fp"):
    why = {}
    slot = pool.take(key, kind, fp, why)
    return slot, why.get("cold")


async def pool_reasons():
    os.environ["JAVIS_WARM_BUDGET_MB"] = "400"
    pool = warm_pool.Pool()
    check("nothing was ever kept for this conversation", miss(pool, "new") == (None, "not_held"))

    a = FakeHandle()
    pool.release(pool.admit("A", "claude", "fpA", a))
    why = {}
    hit = pool.take("A", "claude", "fpA", why)
    check("a hit carries no reason", hit is not None and "cold" not in why)
    check("the conversation is already running on its process", miss(pool, "A", fp="fpA") == (None, "busy"))
    pool.release(hit)
    check("another fingerprint", miss(pool, "A", fp="other") == (None, "config_changed"))
    await settle()

    b = FakeHandle()
    pool.release(pool.admit("B", "claude", "fpB", b))
    check("another engine kind", miss(pool, "B", kind="codex", fp="fpB") == (None, "engine_changed"))
    await settle()

    c = FakeHandle()
    pool.release(pool.admit("C", "claude", "fpC", c))
    c.is_alive = False
    check("the kept process died", miss(pool, "C", fp="fpC") == (None, "process_died"))
    await settle()

    d = FakeHandle()
    pool.release(pool.admit("D", "claude", "fpD", d))
    pool.reap(now=time.monotonic() + warm_pool.idle_s() + 1)
    await settle()
    check("the process idled out", d.closed and miss(pool, "D", fp="fpD") == (None, "idle_expired"))

    e = FakeHandle()
    pool.release(pool.admit("E", "claude", "fpE", e))
    f = FakeHandle()
    sf = pool.admit("F", "claude", "fpF", f)          # 300 + 300 > 400: E is pushed out
    await settle()
    check("pushed out by another conversation", e.closed and miss(pool, "E", fp="fpE") == (None, "evicted"))
    g = FakeHandle()
    check("no room: the busy slot stays", pool.admit("G", "claude", "fpG", g) is None)
    check("the pool had no room when the last turn ended", miss(pool, "G", fp="fpG") == (None, "no_room"))
    pool.release(sf, keep=False)
    await settle()
    check("the last turn ended in a state that cannot be reused", miss(pool, "F", fp="fpF") == (None, "turn_not_clean"))

    h = FakeHandle()
    sh = pool.admit("H", "claude", "fpH", h)
    pool.detach(sh)
    check("kept aside for its background tasks", miss(pool, "H", fp="fpH") == (None, "background_tasks"))

    i = FakeHandle()
    pool.release(pool.admit("I", "claude", "fpI", i))
    pool.drop_kind("claude")
    await settle()
    check("a sign-in closed it", miss(pool, "I", fp="fpI") == (None, "account_changed"))

    async def slow():
        await asyncio.sleep(0.2)
        return FakeHandle()
    pool.remember("P", "claude", "fpP", slow)
    pool.prewarm("P")
    check("the owner sent before the prewarm was ready", miss(pool, "P", fp="fpP") == (None, "prewarm_not_ready"))
    await asyncio.sleep(0.3)

    async def broken():
        raise RuntimeError("no start")
    pool.remember("Q", "claude", "fpQ", broken)
    pool.prewarm("Q")
    await asyncio.sleep(0.05)
    check("the prewarm failed to start", miss(pool, "Q", fp="fpQ") == (None, "prewarm_failed"))

    pool.forget("D")
    check("a forgotten conversation leaves no reason behind", miss(pool, "D", fp="fpD") == (None, "not_held"))
    for n in range(warm_pool.MAX_RECIPES + 20):
        pool._note_gone(f"k{n}", "evicted")
    check("the reasons kept are capped", len(pool._gone) <= warm_pool.MAX_RECIPES)
    os.environ["JAVIS_WARM_BUDGET_MB"] = "0"
    check("pool switched off", miss(pool, "A", fp="fpA") == (None, "pool_off"))
    os.environ["JAVIS_WARM_BUDGET_MB"] = "400"
    await pool.close_all()


asyncio.run(pool_reasons())


async def swap_cases():
    os.environ["JAVIS_WARM_BUDGET_MB"] = "400"      # room for ONE Claude process
    pool = warm_pool.Pool()
    log = []

    async def new_thread():
        log.append("open new")
        return FakeHandle(log=log, name="new")
    old = FakeHandle(log=log, name="old")
    slot = pool.admit("S", "claude", "fp-resume", old, recipe=lambda: None)
    check("a busy slot is never swapped", not pool.swap_recipe("S", "claude", "fp-new", new_thread))
    pool.release(slot)
    check("the idle slot is swapped", pool.swap_recipe("S", "claude", "fp-new", new_thread))
    check("meanwhile a turn would know the process is on its way", miss(pool, "S", fp="fp-new")[1] == "prewarm_not_ready")
    await asyncio.sleep(0.05)
    check("that turn came first, so the new process gave way (same rule as any prewarm)",
          log == ["close old", "open new", "close new"], log)

    log.clear()
    old2 = FakeHandle(log=log, name="old")
    pool.release(pool.admit("S", "claude", "fp-resume", old2, recipe=lambda: None))
    check("swap again, with nobody in the way", pool.swap_recipe("S", "claude", "fp-new", new_thread))
    await asyncio.sleep(0.05)
    check("the old process is closed BEFORE the new one opens (never two at once)",
          log[:2] == ["close old", "open new"], log)
    check("one slot, same RAM as before", pool.status()["used_mb"] == 300)
    check("the old fingerprint no longer matches", miss(pool, "S", fp="fp-resume") == (None, "config_changed"))
    await settle()

    log.clear()
    old3 = FakeHandle(log=log, name="old")
    pool.release(pool.admit("S", "claude", "fp-resume", old3, recipe=lambda: None))
    pool.swap_recipe("S", "claude", "fp-new", new_thread)
    await asyncio.sleep(0.05)
    why = {}
    got = pool.take("S", "claude", "fp-new", why)
    check("the new thread's turn is served by the process opened ahead", got is not None and got.handle.name == "new"
          and "cold" not in why)
    pool.release(got)
    pool.reap(now=time.monotonic() + warm_pool.idle_s() + 1)
    await settle()
    check("idled out: typing reopens the NEW-thread process, not the old one", pool.prewarm("S"))
    await asyncio.sleep(0.05)
    check("reopened from the swapped recipe", pool.take("S", "claude", "fp-new") is not None)
    check("no slot, nothing to swap", not pool.swap_recipe("none", "claude", "fp", new_thread))
    await pool.close_all()
    del os.environ["JAVIS_WARM_BUDGET_MB"]


asyncio.run(swap_cases())


# ---- the rotation forecast is the real rule, one message later ----
LIMIT = compaction.SUBSCRIPTION_THREAD_MAX_TOKENS
check("a light turn: the next one keeps the thread", not compaction.next_turn_rotates(LIMIT - 1, 10, 0))
check("a heavy turn on a thread never rotated: the next one rotates", compaction.next_turn_rotates(LIMIT + 1, 10, 0))
check("heavy, rotated 3 messages ago: the next message makes it 4, so it rotates",
      compaction.next_turn_rotates(LIMIT + 1, 13, 10)
      and compaction.nen_mach_thue_bao(LIMIT + 1, msg_count=14, rotated_at=10))
check("heavy, rotated 2 messages ago: the next turn does not rotate yet",
      not compaction.next_turn_rotates(LIMIT + 1, 12, 10)
      and not compaction.nen_mach_thue_bao(LIMIT + 1, msg_count=13, rotated_at=10))
check("junk values never forecast a rotation", not compaction.next_turn_rotates(None, None, None)
      and not compaction.next_turn_rotates("x", "y", "z"))
agree = all(compaction.next_turn_rotates(t, m, r) == compaction.nen_mach_thue_bao(t, msg_count=m + 1, rotated_at=r)
            for t in (0, LIMIT, LIMIT + 1, 5 * LIMIT) for m in range(0, 12) for r in range(0, 12))
check("the forecast never disagrees with the rule", agree)


# ---- Claude: why an engine is not eligible, and the fingerprint of a new thread ----
import turn_context  # noqa: E402
import claude_warm  # noqa: E402
from claude_cli import claude_engine  # noqa: E402

os.environ["JAVIS_WARM_BUDGET_MB"] = "400"
eng = claude_engine(system_prompt="rules v1", cwd=tempfile.mkdtemp(), tag="chat:abc:1")
if type(eng).__name__ == "ClaudeSDK":
    check("an eligible engine has no reason", claude_warm.ineligible_reason(eng) == "" and claude_warm.eligible(eng))
    eng.tag = "loop:x"
    check("background work", claude_warm.ineligible_reason(eng) == "not_owner_chat" and not claude_warm.eligible(eng))
    eng.tag = "chat:abc:1"
    eng.allowed_tools = ["Read"]
    check("a gated engine", claude_warm.ineligible_reason(eng) == "gated_engine")
    eng.allowed_tools = None
    os.environ["JAVIS_WARM_BUDGET_MB"] = "0"
    check("budget 0", claude_warm.ineligible_reason(eng) == "pool_off")
    os.environ["JAVIS_WARM_BUDGET_MB"] = "400"
else:
    print("skip eligibility: claude-agent-sdk not installed")


def opts(**kw):
    base = dict(cli_path="", cwd=eng.cwd, model="sonnet", effort=None, settings="{}", permission_mode="x",
                setting_sources=["user"], disallowed_tools=[], include_partial_messages=True,
                include_hook_events=True, system_prompt={"type": "preset"}, env={}, hooks=None, resume="S1",
                mcp_servers={"javis": {"type": "http", "url": "http://h/mcp",
                                       "headers": {turn_context.HEADER: "k1"}}})
    base.update(kw)
    return types.SimpleNamespace(**base)


resumed = claude_warm.fingerprint_parts(eng, opts())
eng.system_prompt = "rules v2"
check("a resumed thread ignores the system prompt text, as before",
      claude_warm.fingerprint_parts(eng, opts()) == resumed and resumed.get("new_thread_prompt") == "")
eng.system_prompt = "rules v1"
new1 = claude_warm.fingerprint_parts(eng, opts(resume=None))
eng.system_prompt = "rules v2"
new2 = claude_warm.fingerprint_parts(eng, opts(resume=None))
check("neither does a new thread: same rule as every warm turn, the process runs on the prompt it started with",
      new1 == new2 and claude_warm.changed_parts(resumed, new2) == ["resume"])
ahead = claude_warm.new_thread_parts(resumed)
check("the parts of a process opened ahead equal what the rotated turn computes",
      claude_warm._hash_parts(ahead) == claude_warm._hash_parts(new2), claude_warm.changed_parts(ahead, new2))
own1 = claude_warm.fingerprint_parts(eng, opts(resume=None), own_prompt=True)
check("a turn whose context rides in the system prompt never matches a process opened ahead",
      claude_warm.changed_parts(ahead, own1) == ["new_thread_prompt"])
eng.system_prompt = "rules v3"
check("and its mark follows the prompt text", claude_warm.fingerprint_parts(eng, opts(resume=None), own_prompt=True)
      != own1)
check("on a resumed thread that flag changes nothing",
      claude_warm.fingerprint_parts(eng, opts(), own_prompt=True) == resumed)


async def prepare_cases():
    pool = warm_pool.POOL
    opened = []

    async def recipe():
        h = FakeHandle()
        opened.append(h)
        return h
    check("no slot: nothing prepared", not await claude_warm.prepare_new_thread("conv-none"))
    h = FakeHandle()
    h.new_thread = None
    pool.release(pool.admit("conv-1", "claude", "fp-resume", h))
    check("a slot without a new-thread recipe is left alone", not await claude_warm.prepare_new_thread("conv-1")
          and not h.closed)
    h.new_thread = (ahead, recipe)
    os.environ["JAVIS_WARM_NEW_THREAD"] = "0"
    check("switched off: nothing prepared", not await claude_warm.prepare_new_thread("conv-1") and not h.closed)
    del os.environ["JAVIS_WARM_NEW_THREAD"]
    check("a slot with one is swapped", await claude_warm.prepare_new_thread("conv-1"))
    await asyncio.sleep(0.05)
    got = pool.take("conv-1", "claude", claude_warm._hash_parts(new2))
    check("the rotated turn gets the process opened ahead", h.closed and got is not None and got.handle is opened[0])
    pool.release(got, keep=False)
    await pool.close_all()


asyncio.run(prepare_cases())
del os.environ["JAVIS_WARM_BUDGET_MB"]


# ---- wiring ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
warm_src = (SERVER / "claude_warm.py").read_text(encoding="utf-8")
check("claude_warm: a turn without a thread may use a process opened ahead",
      'warm_pool.POOL.take(key, "claude", fp, why) if allow_warm else None' in warm_src)
check("claude_warm: the warm event carries the reason", '"cold": why.get("cold")' in warm_src
      or "_warm_event(" in warm_src)
check("main: the reason is stored in the first-output event", '"cold"' in src and "_cold_reason(" in src)
check("main: a rotated, a lost and a first thread are told apart",
      all(w in src for w in ('"thread_rotated"', '"thread_lost"', '"new_chat"')))
check("main: the Codex turn passes its reason too", 'ev.get("cold")' in src)
check("main: the new thread's process is asked for when the next turn will rotate",
      "compaction.next_turn_rotates(" in src and "claude_warm.prepare_new_thread(conv_sid)" in src)
# The helper itself, run from the source so the test does not pay for importing main.
import ast  # noqa: E402
node = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_cold_reason")
space = {}
exec(compile(ast.Module(body=[node], type_ignores=[]), "main._cold_reason", "exec"), space)
reason = space["_cold_reason"]
check("no thread, Javis rotated it this turn", reason("new_thread", rotated=True) == "thread_rotated")
check("no thread, a new chat", reason("new_thread") == "new_chat")
check("the old thread was gone and the turn was retried", reason("turn_not_clean", lost=True) == "thread_lost")
check("a pool reason is kept as it is, rotated or not",
      reason("idle_expired", rotated=True) == "idle_expired" and reason("config_changed") == "config_changed")
check("an engine that gave no reason", reason(None) == "unknown")
codex_src = (SERVER / "codex_steer.py").read_text(encoding="utf-8")
check("codex: the session event carries the pool's reason",
      'warm_pool.POOL.take(warm_key, "codex", fp, why)' in codex_src and '"cold": why.get("cold")' in codex_src)
for f in ("warm_pool.py", "claude_warm.py", "compaction.py"):
    check(f"no long dashes in {f}", not any(c in (SERVER / f).read_text(encoding="utf-8") for c in "–—"))

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
