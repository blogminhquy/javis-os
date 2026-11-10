"""Background jobs find their own model from their results (owner, 10/11/2026).

    python tests/run.py job_scorecard

"It has to learn how to learn and adjust the background models itself, to get the job done or to save tokens as
the user intends; it cannot be fixed to a frame I think up." Pinned here:

1. The rules (`job_scorecard.step`): a failure that is the model's fault climbs one rung for the NEXT run; anything
   else leaves the rung alone; a run of successes tries one rung lower, and a failed try goes back up and remembers
   the floor. A job whose only signal is "it did not crash" is not lowered unless the owner asked to save.
2. The owner's intent, said in chat (`javis_tune`): save, balanced, sure, for everything or for one job.
3. The engine layer asks the scorecard for the model of the job that is running, and tells it which link of the
   chain really answered: a pick the provider refused counts against that rung even though the job got done.
4. Each runner reports its verdict: a learning batch, a loop's verify run, a Kanban job's acceptance check.
5. Every change is logged with its reason and can be undone. A background model picked by hand switches it all off.

No network, no engine: engines are fakes.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-scorecard-"))
os.environ["JAVIS_AUTO_BACKGROUND_PAUSED"] = "1"

import aux_engine  # noqa: E402
import job_scorecard as sc  # noqa: E402
import job_tune  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (("  " + str(detail)) if detail and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. The rules
# ============================================================
check("light work starts at the bottom, handed-over work in the middle",
      sc.start_index("light", 4, "balanced") == 0 and sc.start_index("mid", 4, "balanced") == 2)
check("'save' starts handed-over work one rung lower, never below the bottom",
      sc.start_index("mid", 4, "save") == 1 and sc.start_index("light", 4, "save") == 0
      and sc.start_index("mid", 2, "save") == 0)
check("'sure' starts one rung higher, never above MAIN",
      sc.start_index("light", 4, "sure") == 1 and sc.start_index("mid", 4, "sure") == 3
      and sc.start_index("mid", 2, "sure") == 1)
check("the rung the main brain named as the starting point is used", sc.start_index("mid", 5, "balanced", 1) == 1)
check("a ladder of one rung has nowhere to go", sc.start_index("mid", 1, "sure") == 0)

S0 = {"idx": 1, "floor": 0, "floor_at": 0, "streak": 0, "probing": False}
s = sc.step(S0, "fail", "model", 4, "balanced", "strong")
check("a failure of the model climbs one rung", s["idx"] == 2 and s["moved"] == "failed" and s["streak"] == 0)
s = sc.step(S0, "fail", "other", 4, "balanced", "strong")
check("a quota, sign-in or connection failure does not move the rung", s["idx"] == 1 and s["moved"] == "")
s = sc.step(dict(S0, idx=3), "fail", "model", 4, "balanced", "strong")
check("the top rung (MAIN's model) is the ceiling", s["idx"] == 3 and s["moved"] == "")

s = dict(S0)
for _ in range(5):
    s = sc.step(s, "ok", "", 4, "balanced", "strong")
check("five good runs: not yet", s["idx"] == 1 and not s["probing"])
s = sc.step(s, "ok", "", 4, "balanced", "strong")
check("the sixth good run in a row tries one rung lower", s["idx"] == 0 and s["probing"] and s["moved"] == "probe")
ok_try = sc.step(s, "ok", "", 4, "balanced", "strong")
check("the try worked: the lower rung stays", ok_try["idx"] == 0 and not ok_try["probing"] and ok_try["moved"] == "")
bad_try = sc.step(s, "fail", "model", 4, "balanced", "strong")
check("the try failed: back up, and that rung becomes the floor",
      bad_try["idx"] == 1 and bad_try["floor"] == 1 and bad_try["moved"] == "probe_failed")
s2 = dict(bad_try)
for _ in range(20):
    s2 = sc.step(s2, "ok", "", 4, "balanced", "strong")
check("the floor is not tried again", s2["idx"] == 1 and not s2["probing"])
old_floor = dict(bad_try, floor_at=time.time() - (sc.FLOOR_DAYS + 1) * 86400, streak=10)
check("a floor is forgotten after a month: models and jobs change",
      sc.step(old_floor, "ok", "", 4, "balanced", "strong")["moved"] == "probe")

s = dict(S0)
for _ in range(3):
    s = sc.step(s, "ok", "", 4, "save", "weak")
check("'save': three good runs are enough, a weak signal too", s["idx"] == 0 and s["probing"])
s = dict(S0)
for _ in range(30):
    s = sc.step(s, "ok", "", 4, "balanced", "weak")
check("a job whose only signal is 'it did not crash' is not lowered on its own", s["idx"] == 1)
s = dict(S0)
for _ in range(30):
    s = sc.step(s, "ok", "", 4, "sure", "strong")
check("'sure' never tries lower", s["idx"] == 1)

# ============================================================
# 2. A run, the engine layer, and the chain
# ============================================================
LADDER = ["m-light", "m-mid", "m-heavy"]          # MAIN's model "m-main" goes on top
SET = {"model": {"order": ["anthropic-cli"],
                 "profiles": {"anthropic-cli": {"model": "m-main", "reasoning": "off"}},
                 "defaults": {"anthropic-cli": {"model": "m-main", "reasoning": "off"}},
                 "auxiliary": {"auto": True},
                 "auto_background": {"anthropic-cli": {"light": "m-light", "mid": "m-mid", "ladder": LADDER}}}}


def spec(tag):
    return aux_engine.read_spec(SET, tag=tag)["model"]


sc.reset_for_tests()
check("no job running: the tier's starting rung", spec("learn") == "m-light" and spec("reminder") == "m-mid")
sc.set_intent("sure")
check("the owner said 'sure': every tier starts one rung higher", spec("learn") == "m-mid" and spec("reminder") == "m-heavy")
sc.set_intent("save")
check("the owner said 'save': handed-over work starts one rung lower", spec("reminder") == "m-light" and spec("learn") == "m-light")
sc.set_intent("balanced")

with sc.run("reminder:r1", "reminder", "Báo cáo 7 giờ") as r:
    first = spec("reminder")
    again = spec("reminder")
    r.fail(sc.CAUSE_MODEL, "báo cáo rỗng")
check("a new job starts on its tier's rung, and one run keeps one model", first == again == "m-mid")
with sc.run("reminder:r1", "reminder") as r:
    after_fail = spec("reminder")
    r.fail(sc.CAUSE_OTHER, "hết hạn mức")
check("after a failure of the model the NEXT run is one rung up", after_fail == "m-heavy")
with sc.run("reminder:r1", "reminder") as r:
    after_other = spec("reminder")
    r.ok()
check("a failure that was not the model's leaves the job where it was", after_other == "m-heavy")
with sc.run("reminder:r2", "reminder", "Việc khác") as r:
    other_job = spec("reminder")
check("each job has its own rung", other_job == "m-mid")
with sc.run("reminder:r3", "reminder") as r:
    spec("reminder")
check("no verdict leaves no trace", "reminder:r3" not in {j["job"] for j in sc.status(100)["jobs"]})

BY_HAND = json.loads(json.dumps(SET))
BY_HAND["model"]["auxiliary"] = {"provider": "anthropic-cli", "model": "m-main", "auto": False}
with sc.run("reminder:hand", "reminder") as r:
    hand = aux_engine.read_spec(BY_HAND, tag="reminder")["model"]
    r.fail(sc.CAUSE_MODEL)
check("a background model picked by hand: the scorecard is not asked and records nothing",
      hand == "m-main" and "reminder:hand" not in {j["job"] for j in sc.status(100)["jobs"]})

NO_LADDER = json.loads(json.dumps(SET))
NO_LADDER["model"]["auto_background"] = {"anthropic-cli": {"light": "m-light", "mid": "m-mid"}}
check("picks from before the ladder existed still work", aux_engine.read_spec(NO_LADDER, tag="learn")["model"] == "m-light")


class _Link:
    def __init__(self, model, events):
        self.model, self.events, self.provider = model, events, "anthropic-cli"

    def is_available(self):
        return True

    async def query(self, prompt):
        for ev in self.events:
            yield ev


def _chain_run(job, links, verdict="ok"):
    async def go():
        with sc.run(job, "loop", job) as r:
            planned = spec("loop")
            out = [ev async for ev in aux_engine._FallbackChain(links).query("x")]
            (r.ok if verdict == "ok" else r.fail)()
            return planned, out, r
    return asyncio.run(go())


FINAL = {"type": "final", "content": "xong", "tokens_in": 900, "tokens_out": 100}
planned, _, r = _chain_run("loop:a", [_Link("m-mid", [FINAL])])
check("the chain tells the scorecard who answered and what it cost", r.answered == "m-mid" and r.tokens == 1000)
planned, _, r = _chain_run("loop:b", [_Link("m-mid", [{"type": "error", "content": "The model `m-mid` does not exist"}]),
                                      _Link("m-main", [FINAL])])
asyncio.run(asyncio.sleep(0))
with sc.run("loop:b", "loop") as r2:
    nxt = spec("loop")
check("a pick the provider refused counts against that rung, though MAIN got the job done",
      planned == "m-mid" and r.answered == "m-main" and nxt == "m-heavy", (planned, r.answered, nxt))
aux_engine._COOLDOWN.clear()
planned, _, r = _chain_run("loop:c", [_Link("m-mid", [{"type": "error", "content": "429 usage limit reached"}]),
                                      _Link("m-main", [FINAL])])
with sc.run("loop:c", "loop") as r2:
    nxt = spec("loop")
check("a pick that was only out of quota is not held against the model", nxt == "m-mid", nxt)
aux_engine._COOLDOWN.clear()

# ============================================================
# 3. The owner's side: intent, feedback, undo (the javis_tune tool)
# ============================================================
def tune(**kw):
    return json.loads(job_tune.run(kw))


st = tune(op="status")
check("status lists the jobs with their model and record",
      st["ok"] and any(j["job"] == "reminder:r1" and j["model"] == "m-heavy" and j["fails"] == 1 for j in st["jobs"]), st)
check("status shows the change with its reason", any(c["job"] == "reminder:r1" and c["why"] == "failed"
                                                     and c["from_model"] == "m-mid" for c in st["changes"]))
check("an unknown op is refused", tune(op="delete")["ok"] is False)
check("an unknown level is refused", tune(op="intent", level="cheap")["ok"] is False)

res = tune(op="intent", level="save")
check("'tiết kiệm giúp anh' is recorded for every job", res["ok"] and sc.intent() == "save" and res["applies_to"] == "mọi việc nền")
res = tune(op="intent", level="sure", job="báo cáo 7 giờ")
check("'việc này phải thật chắc' is recorded for that job only, found by the owner's own words",
      res["ok"] and sc.intent("reminder:r1") == "sure" and sc.intent("reminder:r2") == "save", res)
with sc.run("reminder:r1", "reminder") as r:
    sure_model = spec("reminder")
check("a job told to be sure starts over from the higher rung", sure_model == "m-heavy")
tune(op="intent", level="balanced")
check("a name that fits no job is said so", tune(op="feedback", job="không có việc này", good=False)["ok"] is False)

with sc.run("reminder:r2", "reminder", "Việc khác") as r:
    spec("reminder")
    r.ok()
res = tune(op="feedback", job="việc khác", good=False, note="số liệu sai")
check("'kết quả việc đó sai rồi' sends the job one rung up for its next run",
      res["ok"] and res["model_next_run"] == "m-heavy", res)
change = next(c for c in tune(op="status")["changes"] if c["job"] == "reminder:r2")
back = tune(op="undo", id=change["id"])
with sc.run("reminder:r2", "reminder") as r:
    undone = spec("reminder")
check("a change can be undone, by its number", back["ok"] and back["model"] == "m-mid" and undone == "m-mid", back)
check("the same change cannot be undone twice", tune(op="undo", id=change["id"])["ok"] is False)

# what the owner is told when a job moves
seen = []
sc.on_change = seen.append
with sc.run("reminder:r9", "reminder", "Gửi tin sáng") as r:
    spec("reminder")
    r.fail(sc.CAUSE_MODEL, "không trả gì")
check("a move is announced once, with the job, both models and the reason",
      len(seen) == 1 and seen[0]["label"] == "Gửi tin sáng" and (seen[0]["from_model"], seen[0]["to_model"]) ==
      ("m-mid", "m-heavy") and seen[0]["why"] == "failed", seen)
sc.on_change = None

# ============================================================
# 4. It survives a restart
# ============================================================
before = {j["job"]: j["model"] for j in sc.status(100)["jobs"]}
sc.reset_for_tests()
after = {j["job"]: j["model"] for j in sc.status(100)["jobs"]}
check("jobs keep their rung across a restart", before and before == after, (before, after))
check("and so does what the owner asked for", sc.intent() == "balanced" and sc.intent("reminder:r1") == "sure")

# ============================================================
# 5. The runners report their verdict
# ============================================================
import inspect  # noqa: E402
import learn  # noqa: E402
import reminders  # noqa: E402
import self_improve  # noqa: E402
import tasks  # noqa: E402

src = inspect.getsource(learn.LearnFeature)
check("a learning batch is scored: unreadable JSON is the model's fault, an engine that will not start is not",
      'job_scorecard.run("learn", "learn"' in src and "_score.fail(job_scorecard.CAUSE_MODEL" in src
      and "_score.fail(job_scorecard.CAUSE_OTHER" in src and "_score.ok()" in src)
src = inspect.getsource(self_improve)
check("a loop is scored by its own verify run",
      'job_scorecard.run(f"loop:{slug}@{brain}", "loop"' in src and "if verify_failed:" in src
      and "_score.fail(job_scorecard.CAUSE_MODEL, verify_line" in src)
src = inspect.getsource(reminders)
check("a reminder is scored: nothing returned is the model's fault, an engine error is not, a stopped run says nothing",
      'job_scorecard.run(f"reminder:' in src and 'if rem.get("id") in self._stopped:' in src
      and "_score.fail(job_scorecard.CAUSE_OTHER" in src)
src = inspect.getsource(tasks)
check("a Kanban job is scored by route, after its acceptance check, which runs outside the job's own rung",
      'job_scorecard.run(f"kanban:' in src and "settle=False" in src and 'if how in ("ai", "heuristic"):' in src
      and "job_scorecard.settle(score)" in src)

# a learning batch end to end, with a fake engine
os.environ["JAVIS_AUTO_BACKGROUND_PAUSED"] = "1"
import main  # noqa: E402
import config as cfgmod  # noqa: E402

cfg = cfgmod.read_settings()
cfg["model"].update(json.loads(json.dumps(SET["model"])))
cfgmod.write_settings(cfg)
sc.reset_for_tests()
lf = main.learn_feature
answers = {"out": "this is not json at all"}
models_used = []


async def _fake_spawn(brain, prompt, cfg_, tag="learn"):
    models_used.append(aux_engine.read_spec(tag=tag)["model"])
    return answers["out"]


class _Store:
    def get_messages(self, sid):
        return [{"role": "user", "content": "anh thích báo cáo ngắn gọn buổi sáng, có so sánh kỳ trước " * 3},
                {"role": "assistant", "content": "Em đã ghi nhận cách anh muốn nhận báo cáo buổi sáng." * 3}]

    def list_sessions(self, **kw):
        return [{"id": "s1"}]


real_spawn, real_store = lf._spawn_readonly, lf.deps.sessions_store
lf._spawn_readonly, lf.deps.sessions_store = _fake_spawn, _Store()
try:
    res = asyncio.run(lf.run_once("brain", reason="manual"))
    answers["out"] = '{"facts": [], "wiki": [], "notes": "không có gì mới"}'
    res2 = asyncio.run(lf.run_once("brain", reason="manual"))
finally:
    lf._spawn_readonly, lf.deps.sessions_store = real_spawn, real_store
check("a batch whose answer is not the JSON asked for fails and counts against the model",
      res.get("ok") is False and models_used[0] == "m-light", (res, models_used))
texts = []


async def _fake_notify(owner_chat, text, **kw):
    texts.append(text)
    return (True, "")


real_notify = main._notify_owner
main._notify_owner = _fake_notify


async def _announce():
    main._scorecard_changed({"id": 7, "job": "reminder:x", "label": "Báo cáo 7 giờ", "from_model": "m-light",
                             "to_model": "m-mid", "why": "failed"})
    await asyncio.sleep(0.01)


asyncio.run(_announce())
main._notify_owner = real_notify
check("the bell notice names the job, both models, the reason and the way back",
      len(texts) == 1 and all(w in texts[0] for w in ("Báo cáo 7 giờ", "m-light", "m-mid", "7"))
      and "không đạt" in texts[0], texts)
check("so the next batch runs one rung up, and its good result is recorded",
      models_used[1] == "m-mid" and res2.get("ok") is True
      and next(j for j in sc.status()["jobs"] if j["job"] == "learn")["runs"] == 2, (models_used, res2))

# ============================================================
# 6. The tool is the owner's, and the bundled plugin exposes it
# ============================================================
import mcp_hub  # noqa: E402

check("a customer-facing bot never sees javis_tune", "javis_tune" in mcp_hub.OWNER_ONLY_TOOLS)
_plug = (ROOT / "system" / "plugins" / "javis-tune" / "plugin.py").read_text(encoding="utf-8")
check("the plugin registers the tool with the four operations",
      'ctx.register_tool(\n        "javis_tune"' in _plug and all(o in job_tune.OPS for o in ("status", "intent", "feedback", "undo")))

if _fails:
    print(f"\nFAIL - {len(_fails)} check(s)")
    raise SystemExit(1)
print("\nOK - job_scorecard: all pass")
