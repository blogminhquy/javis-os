"""Javis Core's improvement loop: one loop, many knobs (owner, 10/11/2026).

    python tests/run.py core_loop

"Propose improvements together with Javis Core so that it scales by itself, does not cost performance, and the
whole becomes a system that improves with time and with how the person uses it." Pinned here:

1. A part of Javis that wants to tune itself registers a knob; the loop moves it the same way for every knob: one
   step, inside its bounds, not while the owner holds it, at most once a day, logged, announced, undoable.
2. The first knob that is not a model: how many turns worth learning must be queued before a learning batch,
   moved by plain code from how many recent batches learned nothing.
3. A memory Javis learned by itself and the owner then removed counts against the model that learns.
4. Lessons about HOW to learn are Javis Core's lessons: the owner says one in chat (`javis_tune op=teach`), every
   learning batch reads them first, and they are listed and revoked like any assistant's lessons.
5. The owner's side: one status, one undo, for knobs and for the models of background jobs.

No network, no engine.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-core-loop-"))
os.environ["JAVIS_AUTO_BACKGROUND_PAUSED"] = "1"

import core_loop as cl  # noqa: E402
import job_scorecard as sc  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. The loop itself, on a knob made for the test
# ============================================================
sc.reset_for_tests()
cl.reset_for_tests()
box = {"v": 2, "held": False, "want": None}
seen = []
cl.on_change = seen.append
K = cl.register(cl.Knob(id="t.knob", title_vi="Núm thử", title_en="Test knob", lo=1, hi=4, default=2,
                        read=lambda: box["v"], write=lambda v: box.__setitem__("v", v),
                        rule=lambda cur: box["want"], frozen=lambda: box["held"]))
T0 = time.time()

check("a rule with nothing to say moves nothing", cl.tick(now=T0) == [] and box["v"] == 2)
box["want"] = (4, "bốn trong năm mẻ rỗng")
moved = cl.tick(now=T0)
check("a rule moves its knob ONE step, whatever it asked for", box["v"] == 3 and len(moved) == 1
      and (moved[0]["old"], moved[0]["new"], moved[0]["actor"]) == (2, 3, "rule"), moved)
check("the move is announced once, with the reason and a number to undo it",
      len(seen) == 1 and seen[0]["why"] == "bốn trong năm mẻ rỗng" and seen[0]["id"].startswith("k"))
check("the same rule cannot move it again the same day", cl.tick(now=T0 + 3600) == [] and box["v"] == 3)
check("a day later it may", len(cl.tick(now=T0 + cl.COOLDOWN_S + 1)) == 1 and box["v"] == 4)
check("the knob never leaves its bounds", cl.tick(now=T0 + 3 * cl.COOLDOWN_S) == [] and box["v"] == 4)

box["want"] = (1, "xuống")
box["held"] = True
check("a knob the owner holds is left alone by the rule", cl.tick(now=T0 + 5 * cl.COOLDOWN_S) == [] and box["v"] == 4)
box["held"] = False
ch = cl.change("t.knob", 1, "owner", "chủ dặn")
check("the owner may jump more than one step, at any time", ch and box["v"] == 1 and ch["actor"] == "owner")
check("an unknown knob or actor is refused", cl.change("no.such", 2, "rule") is None and cl.change("t.knob", 2, "guest") is None)
check("setting the value it already has is not a change", cl.change("t.knob", 1, "owner") is None)

box["want"] = (2, "lên")
check("what the owner set stands: no rule touches that knob for a month",
      cl.tick(now=T0 + 6 * cl.COOLDOWN_S) == [] and box["v"] == 1)
up = cl.tick(now=time.time() + cl.HOLD_AFTER_OWNER_S + 6 * cl.COOLDOWN_S)
back = cl.undo(up[0]["id"])
check("a move can be undone by its number", back and box["v"] == 1 and back["value"] == 1, back)
check("the same move cannot be undone twice", cl.undo(up[0]["id"]) is None)
check("after an undo the rule leaves that knob alone for two weeks",
      cl.tick(now=T0 + 8 * cl.COOLDOWN_S) == [] and box["v"] == 1)
check("and may move it again once the hold is over",
      len(cl.tick(now=time.time() + cl.HOLD_AFTER_OWNER_S + cl.HOLD_AFTER_UNDO_S + 9 * cl.COOLDOWN_S)) == 1
      and box["v"] == 2)
box["v"], box["want"] = 1, None

st = cl.status()
check("status lists every knob with its value and bounds, and the recent moves",
      st["knobs"][0]["knob"] == "t.knob" and st["knobs"][0]["value"] == 1 and (st["knobs"][0]["min"], st["knobs"][0]["max"]) == (1, 4)
      and st["knob_changes"] and st["knob_changes"][0]["id"].startswith("k"), st)
check("a knob under hold is shown as not tuning itself right now", st["knobs"][0]["self_tuning"] is False)

# a broken rule must not stop the others
cl.register(cl.Knob(id="t.broken", title_vi="Hỏng", title_en="Broken", lo=0, hi=3, default=0, read=lambda: 0,
                    write=lambda v: None, rule=lambda cur: 1 / 0))
ok_box = {"v": 0}
cl.register(cl.Knob(id="t.ok", title_vi="Ổn", title_en="Fine", lo=0, hi=3, default=0, read=lambda: ok_box["v"],
                    write=lambda v: ok_box.__setitem__("v", v), rule=lambda cur: (cur + 1, "thử")))
cl.tick(now=T0)
check("one broken rule does not stop the others", ok_box["v"] == 1)

# the cool-down and the hold survive a restart
ok_before = ok_box["v"]
cl._loaded[0] = False
cl._last_move.clear()
cl._held.clear()
cl._ensure_table()
check("after a restart a rule still cannot redo a move the owner undid, nor move twice in a day",
      cl._held.get("t.knob", 0) > time.time() and "t.ok" in cl._last_move and ok_box["v"] == ok_before)
cl.on_change = None

# ============================================================
# 2. The first real knob: turns needed before a learning batch
# ============================================================
import main  # noqa: E402
import config as cfgmod  # noqa: E402
import job_tune  # noqa: E402
import memory_control  # noqa: E402

lf = main.learn_feature
check("main registers the learning knob with Javis Core's loop",
      any(k.id == "learn.min_turns" and k.rule is not None and (k.lo, k.hi, k.default) == (1, 4, 1) for k in cl.knobs()))


def _p(count, ago_s, urgent=False, first_ago=None):
    p = {"count": count, "dense": False, "urgent": urgent, "last_ts": time.time() - ago_s, "convs": {"s1"}}
    if first_ago is not None:
        p["first_ts"] = time.time() - first_ago
    return p


lf.set_min_turns(3)
cfg = lf.read_config()
check("below the bar a quiet brain does not start a batch, the turns stay queued", not lf._should_fire(cfg, _p(2, 20 * 60)))
check("at the bar it does", lf._should_fire(cfg, _p(3, 20 * 60)))
check("'ghi nhớ giúp' ignores the bar", lf._should_fire(cfg, _p(1, 40, urgent=True)))
check("so does the 2-hour bound", lf._should_fire(cfg, _p(1, 60, first_ago=121 * 60)))
lf.set_min_turns(99)
check("the value is kept inside its bounds", lf.min_turns() == 4)
lf.set_min_turns(1)


def _yield(values):
    c = lf.read_config()
    c.setdefault("_state", {})["yield"] = list(values)
    lf.write_config(c)


_yield([0, 0, 0, 1, 0])
check("fewer than six batches say nothing", lf.min_turns_rule(1) is None)
_yield([0, 0, 0, 1, 0, 0, 0, 0])
r = lf.min_turns_rule(1)
check("three in four batches learned nothing: wait for one more turn", r and r[0] == 2 and "7/8" in r[1], r)
check("at the top of the range it stops", lf.min_turns_rule(4) is None)
_yield([1, 1, 1, 0, 1, 1, 1, 1])
r = lf.min_turns_rule(3)
check("nearly every batch learned something and the bar was raised: lower it again", r and r[0] == 2, r)
check("at the default it does not go lower", lf.min_turns_rule(1) is None)
_yield([1, 0, 1, 0, 1, 0])
check("a mixed record moves nothing", lf.min_turns_rule(2) is None)

# through the loop, end to end
cl._last_move.pop("learn.min_turns", None)
cl._held.pop("learn.min_turns", None)
_yield([0] * 8)
notices = []


async def _fake_notify(owner_chat, text, **kw):
    notices.append(text)
    return (True, "")


real_notify = main._notify_owner
main._notify_owner = _fake_notify


async def _tick_in_loop():
    main._MAIN_LOOP[0] = asyncio.get_running_loop()
    out = await asyncio.to_thread(cl.tick)
    await asyncio.sleep(0.05)
    return out


moved = asyncio.run(_tick_in_loop())
check("the loop moves the learning knob from the batches' record", lf.min_turns() == 2 and len(moved) == 1, moved)
check("the evidence starts over after a move", lf.read_config()["_state"]["yield"] == [])
check("the owner gets one quiet notice with the reason and the way back",
      len(notices) == 1 and "8/8" in notices[0] and moved[0]["id"] in notices[0], notices)

# the batch itself records whether it learned anything
answers = {"out": '{"facts": [], "wiki": [], "notes": "không có gì mới"}'}
prompts = []


async def _fake_spawn(brain, prompt, cfg_, tag="learn"):
    prompts.append(prompt)
    return answers["out"]


class _Store:
    def get_messages(self, sid):
        return [{"role": "user", "content": "anh thích báo cáo ngắn gọn buổi sáng, có so sánh kỳ trước " * 3},
                {"role": "assistant", "content": "Em đã ghi nhận cách anh muốn nhận báo cáo buổi sáng." * 3}]

    def list_sessions(self, **kw):
        return [{"id": "s1"}]


real_spawn, real_store = lf._spawn_readonly, lf.deps.sessions_store
lf._spawn_readonly, lf.deps.sessions_store = _fake_spawn, _Store()


def _auto_batch():
    lf._pending["brain"] = {"count": 3, "dense": False, "urgent": False, "last_ts": 0.0, "convs": {"s1"}}
    return asyncio.run(lf.run_once("brain", reason="auto"))


res = _auto_batch()
check("an automatic batch that learned nothing is counted as empty",
      res.get("ok") and lf.read_config()["_state"]["yield"] == [0], (res, lf.read_config()["_state"].get("yield")))
asyncio.run(lf.run_once("brain", reason="manual"))
check("a batch the owner started by hand is not evidence", lf.read_config()["_state"]["yield"] == [0])

# ============================================================
# 3. Lessons about how to learn live with Javis Core
# ============================================================
ROOT_BRAIN = main._brain_root("brain")


def tune(**kw):
    return json.loads(job_tune.run(kw, ROOT_BRAIN))


check("with no lesson the learner's prompt is untouched", main._learning_lessons_block("brain") == "")
res = tune(op="teach", text="đừng ghi doanh thu từng ngày thành ghi nhớ, đó là số liệu sống")
check("the owner teaches one in chat", res.get("ok") and res["lesson"].startswith("L"), res)
check("an empty lesson is refused", tune(op="teach", text="  ")["ok"] is False)
block = main._learning_lessons_block("brain")
check("Javis Core holds it for this brain", "doanh thu từng ngày" in block and block.startswith("=== BÀI HỌC VỀ CÁCH HỌC"))

# a lesson of Javis Core about something else is not handed to the learner
main.agent_lessons.add(main._resonance_store(), agent_key=main._core_lesson_key("brain", register=True), scope="*",
                       kind="speak", text="trả lời chủ thật ngắn", source="owner", by="owner")
check("only lessons about learning reach the learner", "thật ngắn" not in main._learning_lessons_block("brain"))

prompts.clear()
_auto_batch()
check("every learning batch reads them first", prompts and prompts[-1].startswith("=== BÀI HỌC VỀ CÁCH HỌC")
      and "doanh thu từng ngày" in prompts[-1])

st = tune(op="status")
check("status shows the lessons, the knobs and their moves in one answer",
      st["ok"] and any("doanh thu" in l["text"] for l in st["learning_lessons"])
      and any(k["knob"] == "learn.min_turns" for k in st["knobs"]) and "knob_changes" in st, st.keys())

import memory_chat  # noqa: E402

listed = memory_chat.run({"op": "lessons", "agent": "Javis Core"}, ROOT_BRAIN)
check("they are listed like any assistant's lessons", "doanh thu từng ngày" in listed, listed[:200])
lid = res["lesson"]
out = memory_chat.run({"op": "lesson_revoke", "agent": "javis-core", "id": lid}, ROOT_BRAIN)
check("and revoked the same way", not out.startswith("ERROR") and "doanh thu" not in main._learning_lessons_block("brain"), out)

lf._spawn_readonly, lf.deps.sessions_store = real_spawn, real_store

# ============================================================
# 4. A learned memory the owner removes counts against the learner
# ============================================================
calls = []
real_feedback = sc.feedback
sc.feedback = lambda job, good, note="": calls.append((job, good, note)) or True
mem = main._brain_memory_dir("brain")
(mem / "facts").mkdir(parents=True, exist_ok=True)
(mem / "facts" / "hoc-sai.md").write_text(
    "---\ntype: business\nprovenance: user\norigin: javis-learned\ncreated: 2026-11-01\n---\nDoanh thu 9/11 là 12 triệu.\n",
    encoding="utf-8")
(mem / "facts" / "chu-tu-ghi.md").write_text(
    "---\ntype: preference\ncreated: 2026-11-01\n---\nAnh thích báo cáo ngắn.\n", encoding="utf-8")
out = memory_control.forget_memory(mem, "hoc-sai")
check("forgetting still returns what it always did", set(out) == {"slug", "title", "index_line_removed"})
check("a memory Javis had learned itself counts as a failure of the learner",
      calls == [("learn", False, "chủ xoá ghi nhớ: hoc-sai")], calls)
memory_control.forget_memory(mem, "chu-tu-ghi")
check("a memory the owner or a chat wrote says nothing about the learner", len(calls) == 1)
sc.feedback = real_feedback

# ============================================================
# 5. The owner's side
# ============================================================
res = tune(op="set", knob="learn.min_turns", value=3)
check("the owner sets a knob by talking", res["ok"] and lf.min_turns() == 3, res)
check("outside its bounds it is refused, with the range", tune(op="set", knob="learn.min_turns", value=9)["ok"] is False)
check("an unknown knob is refused, with the list", "learn.min_turns" in tune(op="set", knob="nope", value=1).get("knobs", []))
back = tune(op="undo", id=res["id"])
check("one undo for knobs", back["ok"] and lf.min_turns() == 2, back)
check("and the same undo still takes a model change of the scorecard by its plain number",
      tune(op="undo", id=999999)["ok"] is False and tune(op="undo", id="")["ok"] is False)

_core = (ROOT / "system" / "agents" / "javis-core.md").read_text(encoding="utf-8")
check("Javis Core's role says it keeps background work and learning, through javis_tune",
      "Việc nền và tự học" in _core and "`javis_tune`" in _core)
_plug = (ROOT / "system" / "plugins" / "javis-tune" / "plugin.py").read_text(encoding="utf-8")
check("the tool describes teaching and knobs", "op=teach" in _plug and "op=set" in _plug)
main._notify_owner = real_notify

if _fails:
    print(f"\nFAIL - {len(_fails)} check(s)")
    raise SystemExit(1)
print("\nOK - core_loop: all pass")
