"""0.199.0: the read-only health scan groups failures from every store into issues.

Run:
    python tests/run.py sentinel
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import sentinel  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


now = time.time()
state = Path(tempfile.mkdtemp(prefix="javis-sentinel-state-"))
brains_dir = Path(tempfile.mkdtemp(prefix="javis-sentinel-brains-"))
shop = brains_dir / "shop"
(shop / "Javis").mkdir(parents=True)

con = sqlite3.connect(state / "kanban.sqlite3")
con.execute("CREATE TABLE tasks (id TEXT, brain_root TEXT, title TEXT, status TEXT, block_kind TEXT, "
            "block_reason TEXT, updated_at REAL)")
con.executemany("INSERT INTO tasks VALUES (?,?,?,?,?,?,?)", [
    ("t_a1b2c3d4", str(shop), "Đăng bài 1", "blocked", "transient", "Zalo token expired (code 401)", now - 60),
    ("t_e5f6a7b8", str(shop), "Đăng bài 2", "blocked", "transient", "Zalo token expired (code 401)", now - 120),
    ("t_old", str(shop), "Cũ", "blocked", "transient", "Zalo token expired (code 401)", now - 3 * 86400),
    ("t_ask", str(shop), "Hỏi", "blocked", "needs_input", "Cần anh chọn ảnh", now - 60),
    ("t_ok", str(shop), "Xong", "done", "", "", now - 60),
])
con.commit()
con.close()
(shop / "Javis" / "reminders.json").write_text(json.dumps({"reminders": [
    {"id": "r_1", "label": "Báo doanh thu", "error": "Zalo token expired (code 403)", "fired_at": now - 300},
    {"id": "r_2", "label": "OK", "error": "", "fired_at": now - 300}]}), encoding="utf-8")
(shop / "Javis" / "loop-state.json").write_text(json.dumps({
    "quet-don": {"fail_streak": 3, "auto_paused_reason": "Tự tạm dừng 17/10 09:00: 3 lần lỗi", "last_run": now - 600},
    "ok-loop": {"fail_streak": 0}}), encoding="utf-8")
(state / "webhooks.json").write_text(json.dumps({"hooks": [{"id": "wh_1", "name": "Lead", "brain": str(shop),
    "history": [{"at": now - 30, "status": "failed", "result": "engine timeout after 3600s"},
                {"at": now - 20, "status": "done", "result": "ok"}]}]}), encoding="utf-8")
(state / "incidents.json").write_text(json.dumps({"incidents": [{"id": "i1", "status": "needs_you"},
                                                               {"id": "i2", "status": "resolved"}]}), encoding="utf-8")

before = {p: p.stat().st_mtime for p in [state / "kanban.sqlite3", shop / "Javis" / "reminders.json"]}
rep = sentinel.scan(state, [shop], now=now)
top = rep["issues"][0]
check("same cause across stores groups into one issue", top["count"] == 3
      and top["sources"] == ["kanban", "reminder"])
check("old and needs_input jobs are left out", rep["counts"].get("kanban") == 2)
check("paused loop reported", rep["counts"].get("loop") == 1)
check("failed webhook run reported, done run not", rep["counts"].get("webhook") == 1)
check("open incidents counted", rep["incidents"] == 1)
check("examples capped", len(top["examples"]) <= sentinel.EXAMPLES_PER_ISSUE)
check("signature masks numbers and ids", sentinel.signature("Job t_a1b2c3d4 failed 3 times") ==
      sentinel.signature("Job t_99ffee00 failed 7 times"))
check("nothing was written", all(p.stat().st_mtime == m for p, m in before.items()))
check("markdown lists the issue", "3x" in sentinel.to_markdown(rep))
check("empty state is an empty report", sentinel.scan(Path(tempfile.mkdtemp()), [])["issues"] == [])

out = Path(tempfile.mkdtemp(prefix="javis-sentinel-out-"))
r = subprocess.run([sys.executable, str(ROOT / "tools" / "sentinel.py"), "--state-dir", str(state),
                    "--brains-dir", str(brains_dir), "--json", "--out", str(out)],
                   capture_output=True, text=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
check("CLI runs and prints JSON", r.returncode == 0 and json.loads(r.stdout)["issues"])
check("CLI writes report files outside the state dir", (out / "report.json").exists() and (out / "report.md").exists())
r = subprocess.run([sys.executable, str(ROOT / "tools" / "sentinel.py"), "--state-dir", str(state),
                    "--brains-dir", str(brains_dir), "--out", str(state / "x")],
                   capture_output=True, text=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
check("CLI refuses to write inside the state dir", not (state / "x").exists() and "outside" in r.stderr)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
