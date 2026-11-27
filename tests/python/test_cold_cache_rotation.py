"""The cold-cache rule: a long subscription thread whose prompt cache expired during a break is re-seeded from the
saved transcript instead of being re-written whole into the cache (2026-11-27).

    python tests/run.py cold_cache_rotation      (no network, no engine)

Pins:
1. compaction.cold_cache_rotates fires only when the cache is surely cold AND the fresh thread is at most half the
   old one, never on broken input, and respects the anti-churn mark of the size rule;
2. SessionStore.reply_activity reads the newest reply time and the transcript length;
3. KeepWarm.last_warm moves with a warm ping and not with a cold or failed one, so a kept-warm chat is never cut;
4. main._cold_cache_decision ties them together and honours JAVIS_COLD_ROTATE=0;
5. both subscription lanes that resume a native thread (Claude Code, Codex) call it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="javis-cold-cache-"))
for key, relative in {"JAVIS_STATE_DIR": "state", "BRAINS_DIR": "brains", "OBSIDIAN_VAULT_PATH": "vault",
                      "BRAIN_PATH": "brain", "SOURCES_PATH": "sources", "JAVIS_SESSIONS_DB": "sessions.sqlite3"}.items():
    os.environ[key] = str(SCRATCH / relative)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import cache_keepwarm  # noqa: E402
import compaction  # noqa: E402
from sessions import SessionStore  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


HOUR = 3600
rot = compaction.cold_cache_rotates

# ---- 1. the decision ----
check("cold, big thread, short transcript: rotate", rot(400_000, 2 * HOUR, 60_000))
check("warm (inside the hour): keep", not rot(400_000, 50 * 60, 60_000))
check("exactly the TTL is not yet cold", not rot(400_000, HOUR, 60_000))
check("small thread: keep (fresh thread would not be half)", not rot(100_000, 3 * HOUR, 20_000))
check("transcript as big as the thread: keep", not rot(200_000, 3 * HOUR, 300_000))
check("transcript is capped like bootstrap_prompt, so a huge transcript still fits a huge thread",
      rot(1_000_000, 3 * HOUR, 5_000_000))
for name, args in {"no context": (0, 3 * HOUR, 60_000), "no idle": (400_000, 0, 60_000),
                   "no transcript": (400_000, 3 * HOUR, 0), "garbage": ("x", None, "y"),
                   "negative": (-5, -5, -5)}.items():
    check(f"broken input keeps the thread: {name}", not rot(*args))
check("anti-churn: just rotated, keep", not rot(400_000, 3 * HOUR, 60_000, msg_count=21, rotated_at=20))
check("anti-churn: enough progress since the last rotation, rotate",
      rot(400_000, 3 * HOUR, 60_000, msg_count=30, rotated_at=20))
check("anti-churn: unreadable count does not block", rot(400_000, 3 * HOUR, 60_000, msg_count="?", rotated_at=4))
check("a custom TTL is used", rot(400_000, 10 * 60, 60_000, ttl_seconds=5 * 60)
      and not rot(400_000, 4 * 60, 60_000, ttl_seconds=5 * 60))
saving = compaction.cold_cache_saving(400_000, 60_000)
check("saving = thread minus the estimated fresh thread", saving == 400_000 - compaction.COLD_FIXED_TOKENS - 24_000,
      str(saving))
check("saving never negative", compaction.cold_cache_saving(10, 60_000) == 0)

# ---- 2. reply_activity ----
store = SessionStore(db_path=SCRATCH / "reply-activity.db")
sid = store.create_session(brain="brain")
check("empty chat: no reply time, no text", store.reply_activity(sid) == (0.0, 0))
store.append_message(sid, "user", "hello")
store.append_message(sid, "assistant", "hi there")
last, chars = store.reply_activity(sid)
check("reply time is the newest assistant message", abs(last - time.time()) < 60, str(last))
check("transcript chars count user and assistant text", chars == len("hello") + len("hi there"), str(chars))

# ---- 3. keep-warm ----
clock = {"t": 1_000_000.0}


class Eng:
    def __init__(self, res):
        self.res = res

    async def warm_ping(self):
        return dict(self.res)


kw = cache_keepwarm.KeepWarm(enabled=lambda: True, now=lambda: clock["t"])
check("no window: 0", kw.last_warm("nobody") == 0.0)
kw.note_turn("w", Eng({"ok": True, "cache_read": 80_000, "cache_write": 10}), prefix_tokens=80_000)
check("after a real turn: that turn", kw.last_warm("w") == 1_000_000.0)
clock["t"] += cache_keepwarm.PING_AFTER_S + 1
asyncio.run(kw.tick())
check("a warm ping moves it", kw.last_warm("w") == clock["t"], str(kw.last_warm("w")))
kw.note_turn("c", Eng({"ok": True, "cache_read": 0, "cache_write": 80_000}), prefix_tokens=80_000)
start_c = clock["t"]
clock["t"] += cache_keepwarm.PING_AFTER_S + 1
asyncio.run(kw.tick())
check("a cold ping does not", kw.last_warm("c") == start_c)
kw.note_turn("f", Eng({"ok": False, "reason": "boom"}), prefix_tokens=80_000)
start_f = clock["t"]
clock["t"] += cache_keepwarm.PING_AFTER_S + 1
asyncio.run(kw.tick())
check("a failed ping does not", kw.last_warm("f") == start_f)

# ---- 4. main._cold_cache_decision ----
import main  # noqa: E402


class FakeStore:
    def __init__(self, last, chars):
        self.last, self.chars = last, chars

    def reply_activity(self, _sid):
        return self.last, self.chars


now = time.time()
d = main._cold_cache_decision(FakeStore(now - 3 * HOUR, 60_000), "s", 400_000, {"msg_count": 9})
check("decision: cold long thread rotates, with idle minutes and saving",
      d and d["idle_min"] >= 179 and d["saving"] > 0, str(d))
check("decision: recent reply keeps", main._cold_cache_decision(FakeStore(now - 60, 60_000), "s", 400_000, {}) == {})
check("decision: no reply yet keeps", main._cold_cache_decision(FakeStore(0, 60_000), "s", 400_000, {}) == {})


class Broken:
    def reply_activity(self, _sid):
        raise RuntimeError("db gone")


check("decision: a store error keeps", main._cold_cache_decision(Broken(), "s", 400_000, {}) == {})
main._KEEPWARM.windows["kept"] = cache_keepwarm._Window(key="kept", engine=object(), last_real_at=now - 3 * HOUR,
                                                        last_warm_at=now - 10 * 60)
check("decision: keep-warm kept it warm, keep",
      main._cold_cache_decision(FakeStore(now - 3 * HOUR, 60_000), "kept", 400_000, {}, keepwarm=True) == {})
check("decision: keep-warm is only asked when the lane has it",
      bool(main._cold_cache_decision(FakeStore(now - 3 * HOUR, 60_000), "kept", 400_000, {}, keepwarm=False)))
main._KEEPWARM.windows.pop("kept", None)
os.environ["JAVIS_COLD_ROTATE"] = "0"
check("JAVIS_COLD_ROTATE=0 switches the rule off",
      main._cold_cache_decision(FakeStore(now - 3 * HOUR, 60_000), "s", 400_000, {}) == {})
os.environ.pop("JAVIS_COLD_ROTATE", None)
note = main._cold_cache_note({"idle_min": 130, "saving": 250_000}, 400_000)
check("the chat line names the size and the saving", "400,000" in note and "250,000" in note, note)
check("no em or en dash in the chat line", "\u2014" not in note and "\u2013" not in note)

# ---- 5. wired into both lanes ----
src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("Claude Code lane asks the rule, with keep-warm",
      "_cold_cache_decision, store, conv_sid, _claude_context, _row0, True" in src)
check("Claude Code lane only uses a measured thread size",
      '_row0.get("last_context_provider") != "claude-code"' in src)
check("Codex lane asks the rule with a measured thread size only",
      "_codex_ctx if _codex_do else 0, _row0)" in src)
check("both lanes record why the thread rotated", src.count('"reason": "cold_cache"') == 2)

if fails:
    print(f"\nFAIL - {len(fails)} test: {fails}")
    sys.exit(1)
print("\nOK - test_cold_cache_rotation")
