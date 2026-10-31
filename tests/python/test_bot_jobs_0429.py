"""Jobs a chatbot made belong to that bot (0.429.0).

Owner, 31/10/2026: the Tasks page listed every job under Javis Core, while most were made by the owner's Zalo assistant
bot. Expected:
  - a dedicated bot's turn carries `bot_id` in turn_context (a string, so a hook cannot edit it for the next reader);
  - javis_schedule stamps the bot on a reminder (bot_id in POST /reminders) and on a loop (bot_id: in frontmatter),
    javis_task stamps a Kanban job created_by "bot:<id>"; the owner's own turns stamp nothing;
  - reminders keep and show bot_id; loops keep it across a save; repeat hints still see bot jobs;
  - older jobs are guessed from the bot's turn log: created during exactly one bot turn (same chat when the job names
    one), a loop by the chat it reports to on the day it was saved; two bots at once or no turn = Javis Core; a guess
    is kept once made; another brain's bots are ignored;
  - the stats count a bot's jobs for the bot's assistant, or for the bot when that assistant is not in the brain.

Run:
    python tests/python/test_bot_jobs_0429.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import bot_jobs  # noqa: E402
import my_tasks  # noqa: E402
import reminders as R  # noqa: E402
import self_improve  # noqa: E402
import task_stats  # noqa: E402
import turn_context  # noqa: E402
import work_log  # noqa: E402
from task_store import TaskStore  # noqa: E402

fails = []


def check(name, cond, info=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not info else f"  [{info}]"))
    if not cond:
        fails.append(name)


def load_plugin(name):
    spec = importlib.util.spec_from_file_location(f"plugin_{name.replace('-', '_')}",
                                                  ROOT / "system" / "plugins" / name / "plugin.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TZ = timezone(timedelta(hours=7))
now = time.time()
BOT = {"id": "bot_vu", "name": "Javis Vũ", "icon": "headset", "agent": "vu"}

# ---- turn context ----
t = turn_context.from_meta("zalo_personal", {"chat_id": "c1", "user_id": "u1"}, la_chu=False)
t["bot_id"] = BOT["id"]
tok = turn_context.bind(t)
cur = turn_context.current()
cur["bot_id"] = "bot_evil"
check("the bot of the turn is readable, and a reader cannot edit it", turn_context.current()["bot_id"] == "bot_vu")

# ---- javis_schedule ----
sched = load_plugin("javis-schedule")
check("javis_schedule reads the bot of the turn", sched._turn_bot() == "bot_vu")
sent = {}


async def fake_post(payload, brain_name=""):
    sent.update(payload)
    return "ok"


sched._post_reminder = fake_post
vault = Path(tempfile.mkdtemp(prefix="javis-botjobs-"))
asyncio.run(sched._do_create(str(vault), {"name": "Báo cáo", "prompt": "Gửi báo cáo", "schedule": "0 7 * * *"}))
check("a reminder made in a bot turn carries bot_id", sent.get("bot_id") == "bot_vu", sent)
asyncio.run(sched._do_create(str(vault), {"name": "Soi đơn", "prompt": "Soi đơn mới", "schedule": "2 tiếng",
                                          "chat_id": "zalo:c1"}))
lp_text = (vault / "Javis" / "loops" / "soi-don.md").read_text(encoding="utf-8")
check("a loop made in a bot turn carries bot_id in its frontmatter", "bot_id: \"bot_vu\"" in lp_text, lp_text)

# ---- javis_task ----
task_pl = load_plugin("javis-task")
got = {}


class FakeTasks:
    deps = SimpleNamespace(workflows_dir=lambda v: str(vault / "workflows"))
    store = SimpleNamespace(get_task=lambda tid: {"created_at": time.time(), "status": "triage"})

    def enqueue(self, *a):
        got["created_by"] = a[7]
        return "t_1"

    def board_view(self, v):
        return {"orchestration": "auto"}


task_pl._feature = lambda: (FakeTasks(), "")
task_pl._them({"title": "Gom đơn", "chat_id": "c1"}, SimpleNamespace(vault_root=str(vault)))
check("a Kanban job made in a bot turn is created by bot:<id>", got.get("created_by") == "bot:bot_vu", got)
turn_context.reset(tok)
sent.clear()
asyncio.run(sched._do_create(str(vault), {"name": "Nhắc chủ", "prompt": "Nhắc", "schedule": "0 8 * * *"}))
task_pl._them({"title": "Việc của chủ", "chat_id": "c9"}, SimpleNamespace(vault_root=str(vault)))
check("the owner's own turn stamps nothing", "bot_id" not in sent and got.get("created_by") == "chat", (sent, got))

# ---- reminders store ----
rf = R.RemindersFeature.__new__(R.RemindersFeature)
rf.deps = SimpleNamespace(brain_root=lambda b: str(vault), atomic_write_text=lambda p, s: Path(p).write_text(s, encoding="utf-8"))
rf._dang_chay = set()
rf._load = lambda brain: {"reminders": []}
saved = {}
rf._save = lambda brain, data: saved.update(data)
rf._register = lambda brain: None
rf.notify_status = lambda: (True, "")
rem = rf._create("b", "Gửi báo cáo", delay_min=5, created_by="javis_schedule", bot_id="bot_vu")
bad = rf._create("b", "x", delay_min=5, bot_id="../../etc")
view = rf._view(rem)
check("a reminder keeps its bot and shows who made it", view["bot_id"] == "bot_vu" and view["created_by"] == "javis_schedule")
check("a malformed bot id is dropped", "bot_id" not in bad)

# ---- loops keep bot_id across a save ----
obj = self_improve.LoopFeature.__new__(self_improve.LoopFeature)
obj.deps = SimpleNamespace(atomic_write_text=lambda p, s: Path(p).write_text(s, encoding="utf-8"))
obj._loops_dir = lambda brain: vault / "Javis" / "loops"
obj._loop_path = lambda brain, slug: vault / "Javis" / "loops" / f"{slug}.md"
lp = obj._norm_loop({"name": "Soi đơn", "bot_id": "bot_vu", "goal": "custom"}, "Soi đơn mới", "soi-don")
check("a loop file is read with its bot", lp["bot_id"] == "bot_vu")
lp["enabled"] = True
obj.save_loop("b", lp)
parsed = "bot_id: bot_vu" in (vault / "Javis" / "loops" / "soi-don.md").read_text(encoding="utf-8")
check("a loop keeps its bot when it is saved again (toggle, edit)", parsed is True)
store_hint = TaskStore(Path(tempfile.mkdtemp()) / "k.sqlite3")
hint_root = str(Path(tempfile.mkdtemp()).resolve())
for i in range(3):
    store_hint.enqueue(hint_root, "Tổng hợp đơn Zalo", "x", created_by="bot:bot_vu", dedupe_title=False)
check("repeat hints still see jobs a bot made", bool(store_hint.repeat_hints(hint_root)), store_hint.repeat_hints(hint_root))

# ---- guessing older jobs from the turn log ----
brain = Path(tempfile.mkdtemp(prefix="javis-botjobs-brain-"))
root = str(brain.resolve())
other = Path(tempfile.mkdtemp(prefix="javis-botjobs-other-"))
roots = {"main": root, "other": str(other.resolve())}
bots = [{"id": "bot_vu", "name": "Javis Vũ", "icon": "headset", "brain": "main", "agent": {"brain": "main", "slug": "vu"}},
        {"id": "bot_shop", "name": "Shop", "brain": "main", "agent": {"brain": "main", "slug": "ghost"}},
        {"id": "bot_far", "name": "Far", "brain": "other", "agent": {}}]
logs = {
    "bot_vu": [{"ts": now - 3000, "chat_id": "zalo:c1", "dap": "ok"}, {"ts": now - 1000, "chat_id": "c1", "dap": "ok"},
               {"ts": now - 500, "chat_id": "c1", "dap": "", "bo_qua": "skip"}],
    "bot_shop": [{"ts": now - 1000, "chat_id": "s7", "dap": "ok"}, {"ts": now - 20000, "chat_id": "s7", "dap": "ok"}],
    "bot_far": [{"ts": now - 7000, "chat_id": "f1", "dap": "ok"}],
}
(brain / "Javis").mkdir(parents=True)
(brain / "Javis" / "reminders.json").write_text(json.dumps({"reminders": [
    {"id": "r_new", "bot_id": "bot_vu", "created_by": "javis_schedule", "created_at": now - 99999},       # stamped
    {"id": "r_old", "created_by": "javis_schedule", "chat_id": "", "created_at": now - 3100},               # vu's turn
    {"id": "r_both", "created_by": "javis_schedule", "chat_id": "", "created_at": now - 1100},              # two bots
    {"id": "r_chat", "created_by": "javis_schedule", "chat_id": "s7", "created_at": now - 1100},            # shop's chat
    {"id": "r_dash", "created_by": "dashboard", "chat_id": "", "created_at": now - 3100},                  # owner typed
    {"id": "r_far", "created_by": "javis_schedule", "chat_id": "", "created_at": now - 7100},              # other brain
]}), encoding="utf-8")
kb = TaskStore(Path(tempfile.mkdtemp()) / "kb.sqlite3")
k_new = kb.enqueue(root, "Gom đơn", "x", created_by="bot:bot_vu")
k_old = kb.enqueue(root, "Đồng bộ kho", "x", created_by="chat", chat_id="zalo:c1")
k_me = kb.enqueue(root, "Việc chủ giao", "x", created_by="user")
with kb._lock:
    kb._db.execute("UPDATE tasks SET created_at=? WHERE id=?", (now - 1050, k_old))
    kb._db.commit()
day = datetime.fromtimestamp(now - 1000, TZ).date().isoformat()
loops = [{"slug": "soi-don", "bot_id": "bot_vu", "owner_chat": "", "updated": day},
         {"slug": "cham-khach", "bot_id": "", "owner_chat": "zalo:s7", "updated": day},
         {"slug": "bao-cao", "bot_id": "", "owner_chat": "", "updated": day}]
deps = bot_jobs.BotJobsDeps(brain_root=lambda b: roots.get(b, b), list_bots=lambda: bots, turns=lambda bid: logs.get(bid, []),
                            task_store=lambda: kb, loops=lambda r: loops)
m = bot_jobs.job_map(deps, "main", TZ)
J = m["jobs"]
check("only this brain's bots", {b["id"] for b in m["bots"]} == {"bot_vu", "bot_shop"}, m["bots"])
check("a stamped reminder keeps its bot", J.get("r:r_new") == "bot_vu")
check("an old reminder made during one bot turn goes to that bot", J.get("r:r_old") == "bot_vu", J)
check("two bots answering at that moment: no guess (Javis Core)", "r:r_both" not in J)
check("a reminder naming a chat goes to the bot of that chat", J.get("r:r_chat") == "bot_shop", J)
check("a reminder the owner made on the dashboard is never guessed", "r:r_dash" not in J)
check("another brain's bot is never matched", "r:r_far" not in J)
check("Kanban: stamped and guessed jobs, the owner's own stays", J.get("k:" + k_new) == "bot_vu"
      and J.get("k:" + k_old) == "bot_vu" and "k:" + k_me not in J, J)
check("loops: stamped, by the chat they report to on that day, none without a chat",
      J.get("l:soi-don") == "bot_vu" and J.get("l:cham-khach") == "bot_shop" and "l:bao-cao" not in J, J)
logs["bot_vu"] = []
check("a guess is kept after the turn log is trimmed", bot_jobs.job_map(deps, "main", TZ)["jobs"].get("r:r_old") == "bot_vu")

# ---- stats ----
work_log.append(root, "reminder", "r_old", "Báo cáo", "ok", mode="task", ts=now - 60)
work_log.append(root, "reminder", "r_chat", "Chăm khách", "ok", mode="task", ts=now - 50)
work_log.append(root, "reminder", "r_dash", "Nhắc chủ", "ok", mode="task", ts=now - 40)
mt = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: root, tz=lambda: TZ,
                                           atomic_write_text=lambda p, s: Path(p).write_text(s, encoding="utf-8")))
feat = task_stats.TaskStats(task_stats.TaskStatsDeps(brain_root=lambda b: root, my_tasks=lambda: mt, task_store=lambda: kb,
                                                     tz=lambda: TZ, agent_names=lambda b: {"vu": "Trợ lý Vũ"},
                                                     bot_jobs=lambda b: bot_jobs.job_map(deps, "main", TZ)))
today = datetime.now(TZ).date().isoformat()
ag = {a["key"]: a for a in feat.compute("main", today, today)["ai"]["agents"]}
check("stats: the bot's job counts for its assistant", ag.get("vu", {}).get("n") == 1 and ag["vu"]["name"] == "Trợ lý Vũ", ag)
check("stats: a bot whose assistant is not here counts as the bot", ag.get("bot:bot_shop", {}).get("name") == "Shop", ag)
check("stats: the owner's reminder stays with Javis Core", ag.get("core", {}).get("n") == 1, ag)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
raise SystemExit(1 if fails else 0)
