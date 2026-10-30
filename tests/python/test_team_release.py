"""Phát hành nhóm chat team 0.140.0: kho nhóm của bản dựng đời trước (lược đồ lúc T1, chưa có các cột thêm về sau) mở bằng
mã phát hành thì tự nâng, giữ nguyên dữ liệu, và mọi thao tác mới chạy được.

    python tests/run.py team_release -v

Các cột thêm sau T1: `team_turns.committed_at` (bài học ghi một lần), `teams.pinned_at` (ghim), `team_members.identity_json`
(nhân dạng lịch sử theo agent_key). Lược đồ T1 chép nguyên văn dưới đây để test không cần lịch sử git. SQLite tạm.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-release-")

import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# Lược đồ kho nhóm lúc T1 (PR #628, head cee0159d), nguyên văn.
T1_SCHEMA = """
CREATE TABLE IF NOT EXISTS teams(
  team_id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  session_id TEXT NOT NULL, leader_key TEXT, leader_mode TEXT NOT NULL DEFAULT 'limited',
  status TEXT NOT NULL DEFAULT 'active', caps_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS teams_brain ON teams(brain_id, updated_at);
CREATE TABLE IF NOT EXISTS team_members(
  team_id TEXT NOT NULL, agent_key TEXT NOT NULL, slug_at_join TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT 'member', status TEXT NOT NULL DEFAULT 'active',
  managed_by_team INTEGER NOT NULL DEFAULT 0, joined_at REAL NOT NULL, left_at REAL,
  PRIMARY KEY(team_id, agent_key));
CREATE INDEX IF NOT EXISTS team_members_agent ON team_members(agent_key, status);
CREATE TABLE IF NOT EXISTS team_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, team_id TEXT NOT NULL, kind TEXT NOT NULL, by TEXT NOT NULL DEFAULT '',
  before_json TEXT NOT NULL DEFAULT '{}', after_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS team_events_team ON team_events(team_id, id);
CREATE TABLE IF NOT EXISTS team_steps(
  step_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, team_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL,
  agent_key TEXT NOT NULL, job_revision INTEGER NOT NULL, brief TEXT NOT NULL DEFAULT '',
  input_refs_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'queued', parent_step TEXT,
  result_msg_id INTEGER, applied INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(task_id, seq));
CREATE TABLE IF NOT EXISTS team_turns(
  turn_id TEXT PRIMARY KEY, team_id TEXT NOT NULL, task_id TEXT, step_id TEXT, agent_key TEXT NOT NULL,
  role TEXT NOT NULL, engine TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'reserved', engine_at REAL, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL,
  created_at REAL NOT NULL, settled_at REAL);
CREATE INDEX IF NOT EXISTS team_turns_team ON team_turns(team_id, created_at);
CREATE INDEX IF NOT EXISTS team_turns_task ON team_turns(task_id);
CREATE TABLE IF NOT EXISTS agent_busy(
  agent_key TEXT PRIMARY KEY, team_id TEXT NOT NULL, turn_id TEXT NOT NULL, lease_until REAL NOT NULL);
"""

d = Path(tempfile.mkdtemp(prefix="javis-team-release-store-"))
path = d / "team.sqlite3"
now = time.time()
with closing(sqlite3.connect(str(path))) as c:
    c.executescript(T1_SCHEMA)
    c.execute("INSERT INTO teams VALUES('tm_old','B','Nhóm cũ','mô tả','s1','ag_lan','limited','active','{\"daily_turns\": 40}',?,?)",
              (now - 100, now - 100))
    c.execute("INSERT INTO team_members VALUES('tm_old','ag_lan','lan','leader','active',0,?,NULL)", (now - 100,))
    c.execute("INSERT INTO team_members VALUES('tm_old','ag_cu','cu','member','removed',0,?,?)", (now - 100, now - 50))
    c.execute("INSERT INTO team_turns(turn_id,team_id,agent_key,role,status,created_at) VALUES('tu_1','tm_old','ag_lan',"
              "'leader_reply','ok',?)", (now - 90,))
    c.execute("INSERT INTO team_events(team_id,kind,by,created_at) VALUES('tm_old','created','owner',?)", (now - 100,))
    c.commit()

ts = team_store.TeamStore(path)
with closing(sqlite3.connect(str(path))) as c:
    cols = {t: {r[1] for r in c.execute(f"PRAGMA table_info({t})").fetchall()} for t in ("teams", "team_members", "team_turns")}
check("kho đời T1 mở bằng mã phát hành: tự thêm pinned_at, identity_json, committed_at",
      "pinned_at" in cols["teams"] and "identity_json" in cols["team_members"] and "committed_at" in cols["team_turns"], cols)
t = ts.get("tm_old")
check("nhóm cũ giữ nguyên: tên, trưởng nhóm, trần đã đổi, chưa ghim", t and t["name"] == "Nhóm cũ" and t["leader_key"] == "ag_lan"
      and t["caps"]["daily_turns"] == 40 and t["pinned_at"] is None, t)
mem = ts.members("tm_old", include_removed=True)
check("thành viên cũ giữ nguyên (cả người đã rời), chưa có ảnh chụp nhân dạng",
      {m["agent_key"]: m["status"] for m in mem} == {"ag_lan": "active", "ag_cu": "removed"}
      and all(m["identity"] is None for m in mem), mem)
check("lượt cũ vẫn đếm (trần ngày)", ts.count_team_turns("tm_old", now - 1000) == 1)
check("danh sách nhóm đọc được", [x["team_id"] for x in ts.list_teams("B")] == ["tm_old"])
ts.set_pinned("tm_old", True)
ts.set_identity("tm_old", "ag_cu", {"slug": "cu", "name": "Cũ", "avatar": None})
check("thao tác mới chạy được trên kho cũ: ghim, chụp nhân dạng",
      ts.get("tm_old")["pinned_at"] is not None
      and next(m for m in ts.members("tm_old", include_removed=True) if m["agent_key"] == "ag_cu")["identity"]["name"] == "Cũ")
check("bản ghi chặn tra theo việc chạy được trên kho cũ (chưa có bản ghi thì None)", ts.cap_record("tm_old", "t_x") is None)
ts2 = team_store.TeamStore(path)
check("mở lại lần hai: không lỗi, dữ liệu mới còn", ts2.get("tm_old")["pinned_at"] is not None)

# Review tích hợp 0.140.0: snapshot và bản giữ lại của MỌI kho bị nâng (chứa toàn bộ chat, việc) không được lên git khi
# Javis chạy với thư mục state mặc định server/ (bản fork phải sạch).
import subprocess  # noqa: E402
names = [f"server/{base}{tag}" for base in ("conversations.db", "kanban.sqlite3", "team.sqlite3")
         for tag in (".pre-0.140.0", ".post-0.140.0-20261014-120000")]
not_ignored = [n for n in names if subprocess.run(["git", "check-ignore", "-q", n], cwd=str(ROOT)).returncode != 0]
check("snapshot .pre-0.140.0 và bản giữ lại .post-0.140.0-* của ba kho đều bị gitignore", not not_ignored, not_ignored)

# Review tích hợp 0.140.0: bí danh "nhom" trơn của trang Nhóm khớp cụm con nên cướp các câu nói về NHÓM thanh bên ("nhóm
# việc", "nhóm code"...). Kết quả của những câu đó phải giữ như 0.139.0; chỉ câu gọi đúng trang Nhóm mới ra trang Nhóm.
import ui_targets  # noqa: E402
# 0.422.0: Kanban became the Tasks page, so "việc" now lands on "tasks" (same place, new id).
same_as_0137 = {"nhóm việc": "tasks", "nhóm code": "terminal", "mở nhóm trợ lý": "workspace", "nhóm hệ thống": "",
                "nhóm kết nối": "mcp", "nhóm bộ não": "models", "mở cộng sự": "workspace", "trang việc": "tasks"}
got = {s: ui_targets.resolve_page(s) for s in same_as_0137}
check("giọng nói: câu nói về nhóm thanh bên giữ đúng trang như 0.139.0", got == same_as_0137,
      {s: (got[s], same_as_0137[s]) for s in got if got[s] != same_as_0137[s]})
to_teams = ["nhóm", "mở trang nhóm", "trang nhóm", "nhóm chat", "mở nhóm chat", "team", "teams", "mở trang teams"]
got = {s: ui_targets.resolve_page(s) for s in to_teams}
check("giọng nói: gọi đúng trang Nhóm thì ra trang Nhóm", all(v == "teams" for v in got.values()), got)

print(f"\n{'FAIL' if fails else 'PASS'} - test_team_release: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
