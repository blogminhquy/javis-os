"""Bundled plugin javis-mine (0.425.0): the owner's tasks and habits from chat, on every engine.

Expected:
  - op=add puts a task (or a habit with a weekday repeat) in the Mine store of the current brain;
  - op=list shows today's tasks and habits with the streak;
  - op=check ticks ONE matching task with by="javis"; several matches return a list to ask back, no tick;
  - no brain -> a clear error, never the default brain.

Run:
    python tests/python/test_javis_mine_plugin.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import tempfile
from datetime import date
from pathlib import Path

import my_tasks  # noqa: E402
import plugins_host  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


VAULT = Path(tempfile.mkdtemp(prefix="javis-mine-"))


def atomic_write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


feat = my_tasks.MyTasks(my_tasks.MyTasksDeps(brain_root=lambda b: str(b), atomic_write_text=atomic_write))
my_tasks._FEATURE = feat

spec = importlib.util.spec_from_file_location("javis_mine_plugin", ROOT / "system/plugins/javis-mine/plugin.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ctx = plugins_host.PluginContext("javis-mine", "bundled", ROOT / "system/plugins/javis-mine", str(VAULT))
m.register(ctx)
tool = ctx._tools[0]
h = tool["handler"]
check("tool javis_mytask registered at level safe", tool["name"] == "javis_mytask" and tool["min_mode"] == "safe")

today = date.today().isoformat()
out = asyncio.run(h({"op": "add", "title": "Gọi chị Lan chốt đơn sỉ", "date": today, "time": "14:00"}, ctx))
check("add a task", out.startswith("OK") and "Gọi chị Lan" in out, out)
out = asyncio.run(h({"op": "add", "title": "Đọc sách 30 phút", "repeat": "day", "habit": True}, ctx))
check("add a daily habit", out.startswith("OK") and "thói quen" in out, out)
out = asyncio.run(h({"op": "add", "title": "Đi bơi", "repeat": "week", "days": "T3, T5, thứ bảy", "habit": True}, ctx))
swim = next(t for t in feat.load(str(VAULT))["tasks"] if t["title"] == "Đi bơi")
check("weekday names become weekdays", swim["repeat"] == {"unit": "week", "n": 1, "days": [2, 4, 6]}, swim["repeat"])
asyncio.run(h({"op": "add", "title": "Đọc báo cáo tuần", "date": today}, ctx))

out = asyncio.run(h({"op": "list"}, ctx))
check("list shows today's task and the daily habit with its streak", "Gọi chị Lan" in out and "Đọc sách" in out and "chuỗi" in out, out)

out = asyncio.run(h({"op": "check", "name": "đọc"}, ctx))
check("an ambiguous name asks back and ticks nothing", "HỎI LẠI" in out
      and not any(t.get("done_dates") for t in feat.load(str(VAULT))["tasks"]), out)
out = asyncio.run(h({"op": "check", "name": "doc sach"}, ctx))
read = next(t for t in feat.load(str(VAULT))["tasks"] if t["title"] == "Đọc sách 30 phút")
check("a unique name (no diacritics) ticks the habit today, by Javis", out.startswith("OK") and read["done_dates"].get(today, {}).get("by") == "javis", out)
check("the answer reports the streak", "Chuỗi giữ lửa: 1" in out, out)
out = asyncio.run(h({"op": "check", "name": "chị Lan"}, ctx))
lan = next(t for t in feat.load(str(VAULT))["tasks"] if t["title"].startswith("Gọi chị Lan"))
check("a one-off task is marked done by Javis", out.startswith("OK") and lan["status"] == "done" and lan.get("done_by") == "javis", out)
check("an unknown name says so", "Không thấy" in asyncio.run(h({"op": "check", "name": "zzzz"}, ctx)))

ctx2 = plugins_host.PluginContext("javis-mine", "bundled", ROOT / "system/plugins/javis-mine", "")
check("no brain -> clear error", asyncio.run(h({"op": "add", "title": "x"}, ctx2)).startswith("ERROR"))
check("unknown op -> clear error", asyncio.run(h({"op": "fly"}, ctx)).startswith("ERROR"))

print(f"\n{len(fails)} failed" if fails else "\nall passed")
raise SystemExit(1 if fails else 0)
