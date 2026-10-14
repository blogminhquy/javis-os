"""0.142.0: bỏ người review cố định (A5) và migration của mục tiêu cũ.

    python tests/run.py review_removed_0142

Dựng kho đúng như thời A5 (đội gắn khi tạo), có mục tiêu đang CHỜ REVIEW và mục tiêu đang làm. Bỏ bảng đánh dấu
migration để giả lập kho trước 0.142.0, mở lại bằng mã mới, rồi kiểm:
- không mục tiêu nào bị tự đánh dấu đạt (kể cả khi thức lại), lịch sử review và lượt giữ nguyên;
- đội được gỡ có ghi lý do, mục tiêu đang mở tạm dừng chờ chủ quyết, lý do thức của vai review được chốt;
- có bản sao kho trước khi nâng; mở lại lần hai không đổi gì;
- mục tiêu mới không còn đội; tab Công việc xếp mục tiêu đã gỡ vào Cần bạn với lý do bằng lời.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sqlite3
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-review-removed-")

import resonance as R  # noqa: E402
import resonance_store as RS  # noqa: E402
import agent_jobs  # noqa: E402
import _resonance_team as T  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


STATE = Path(tempfile.mkdtemp(prefix="state-review-removed-"))
t = T.Team(STATE, "rr")                 # kho thời A5: cặp làm/review, đội gắn khi tạo
g_wait = t.create()
t.wake(g_wait)                          # người làm nộp bản, mục tiêu chờ review
g_work = t.create()                     # có đội, chưa chạy
st = t.st(g_wait)
check("dựng đúng: một mục tiêu đang chờ review có đội active",
      st.get("block_reason") == "review_pending" and t.team(g_wait)["status"] == "active"
      and t.team(g_work)["status"] == "active", st)
reviews_before = len(t.reviews(g_wait))
calls_before = t.calls(g_wait)
db = Path(t.store.path)

# Thêm các trạng thái còn lại của một mục tiêu có đội (ghi thẳng trạng thái đã lưu như kho thật để lại lúc nâng cấp):
# đang chờ người làm sửa theo review, đang chạy dở, bị chặn vì lý do KHÔNG thuộc đội, chưa bắt đầu, và đã kết thúc.
g_changes, g_running, g_blocked, g_failed = t.create(), t.create(), t.create(), t.create()
g_new = t.create(approve=False)
with sqlite3.connect(str(db)) as c:
    c.execute("UPDATE goals SET run_state='waiting', block_reason='review_changes' WHERE id=?", (g_changes.id,))
    c.execute("UPDATE goals SET run_state='running', block_reason='' WHERE id=?", (g_running.id,))
    c.execute("UPDATE goals SET run_state='blocked', block_reason='guard_deadline' WHERE id=?", (g_blocked.id,))
    c.execute("UPDATE goals SET status='failed', run_state='done' WHERE id=?", (g_failed.id,))
EXTRA = {"đang chờ sửa theo review": g_changes, "đang chạy dở": g_running, "bị chặn ngoài đội": g_blocked,
         "chưa bắt đầu": g_new, "đã kết thúc (không đạt)": g_failed}
ALL = dict(EXTRA, **{"đang chờ review": g_wait, "có đội chưa chạy": g_work})
check("dựng đúng: mọi mục tiêu thêm vào đều có đội active", all(t.team(g)["status"] == "active" for g in EXTRA.values()),
      {k: t.team(g)["status"] for k, g in EXTRA.items()})
events_before = {g.id: [(e["id"], e["kind"]) for e in t.store.events(t.owner, g.id)] for g in ALL.values()}

# Giả lập kho trước 0.142.0: chưa có bảng đánh dấu migration.
with sqlite3.connect(str(db)) as c:
    c.execute("DROP TABLE review_migrations")
store = RS.GoalStore(db)
owner = t.owner
bak = db.with_name(db.name + RS.REVIEW_REMOVED_BACKUP_SUFFIX)
with sqlite3.connect(str(bak)) as c:
    bak_team = c.execute("SELECT status FROM goal_team WHERE goal_id=?", (g_wait.id,)).fetchone()
    bak_changes = c.execute("SELECT run_state, block_reason, paused FROM goals WHERE id=?", (g_changes.id,)).fetchone()
check("có bản sao kho trước khi nâng, đội trong bản sao vẫn active", bak.is_file() and bak_team == ("active",))
check("bản sao giữ trạng thái gốc của mục tiêu đang chờ sửa theo review", bak_changes == ("waiting", "review_changes", 0),
      bak_changes)

for g, label in ((g_wait, "đang chờ review"), (g_work, "đang làm")):
    cur = store.get(owner, g.id)
    team = store.goal_team(owner, g.id)
    rs = store.run_state(owner, g.id)
    check(f"mục tiêu {label}: vẫn active (không tự đạt), tạm dừng, đội đã gỡ bởi host",
          cur.status == "active" and cur.paused and team["status"] == "detached"
          and team["detached_by"] == "host:review_removed", (cur.status, cur.paused, team))
    check(f"mục tiêu {label}: không còn chặn thuộc đội", rs.get("block_reason") not in RS.TEAM_BLOCKS, rs)

ev = [e for e in store.events(owner, g_wait.id) if e["kind"] == "team_detached"]
check("sự kiện team_detached ghi lý do và trạng thái trước đó",
      len(ev) == 1 and ev[0]["payload"].get("reason") == "review_removed"
      and ev[0]["payload"].get("prev_block") == "review_pending", ev)
check("lịch sử review và lượt giữ nguyên", len(store.reviews(owner, g_wait.id, limit=50)) == reviews_before
      and (store.goal_team(owner, g_wait.id)["calls"].get("maker", {}).get("used"),
           store.goal_team(owner, g_wait.id)["calls"].get("reviewer", {}).get("used")) == calls_before[:2])
pending = [r for r in store.reasons(owner, g_wait.id, state="pending") if r["code"].startswith("review_")]
check("lý do thức của vai review đã chốt", pending == [], pending)
with sqlite3.connect(str(db)) as c:
    pair = c.execute("SELECT enabled, by FROM team_pairs WHERE maker_agent_key=?", (t.maker["agent_key"],)).fetchone()
check("cặp làm/review cũ tắt, dòng vẫn giữ", pair == (0, "host:review_removed"), pair)

# Mọi trạng thái còn lại: không mục tiêu nào bị đánh dấu đạt, lịch sử chỉ được thêm (không mất dòng nào).
for label, g in EXTRA.items():
    cur = store.get(owner, g.id)
    team = store.goal_team(owner, g.id)
    check(f"mục tiêu {label}: không tự đạt, đội đã gỡ bởi host", cur.status != "succeeded"
          and team["status"] == "detached" and team["detached_by"] == "host:review_removed", (cur.status, team))
for label, g in ALL.items():
    after = [(e["id"], e["kind"]) for e in store.events(owner, g.id)]
    check(f"mục tiêu {label}: lịch sử sự kiện giữ nguyên, chỉ thêm",
          set(events_before[g.id]) <= set(after), (len(events_before[g.id]), len(after)))
cur = store.get(owner, g_changes.id)
rs = store.run_state(owner, g_changes.id)
check("đang chờ sửa theo review (review_changes): tạm dừng, gỡ chặn thuộc đội về ready",
      cur.status == "active" and cur.paused and rs.get("block_reason") == "" and rs.get("run_state") == "ready", rs)
cur = store.get(owner, g_running.id)
check("đang chạy dở: vẫn active, tạm dừng, không tự kết thúc", cur.status == "active" and cur.paused)
cur = store.get(owner, g_blocked.id)
rs = store.run_state(owner, g_blocked.id)
check("bị chặn vì lý do ngoài đội: GIỮ NGUYÊN chặn của nó (không bị gỡ), tạm dừng",
      cur.status == "active" and cur.paused and rs.get("block_reason") == "guard_deadline"
      and rs.get("run_state") == "blocked", rs)
cur = store.get(owner, g_new.id)
check("chưa bắt đầu: vẫn active chưa chạy, tạm dừng chờ chủ", cur.status == "active" and cur.paused
      and store.run_state(owner, g_new.id).get("run_state") == "ready")
cur = store.get(owner, g_failed.id)
check("đã kết thúc: giữ trạng thái kết thúc, không tạm dừng, không thành đạt", cur.status == "failed" and not cur.paused)
ev_failed = [e for e in store.events(owner, g_failed.id) if e["by"] == "host:review_removed"]
check("đã kết thúc: chỉ ghi sự kiện gỡ đội, không ghi tạm dừng", [e["kind"] for e in ev_failed] == ["team_detached"],
      ev_failed)

# Thức lại: mục tiêu đang dừng không tự kết thúc, không gọi model.
t.store = store
q0 = t.work.queries + t.rev.queries
t.wake(g_wait)
check("thức lại sau migration: không tự đạt, không gọi model", store.get(owner, g_wait.id).status == "active"
      and t.work.queries + t.rev.queries == q0)

# Mở lại lần hai: không đổi gì.
n_events = len(store.events(owner, g_wait.id))
n_all = {g.id: len(store.events(owner, g.id)) for g in ALL.values()}
store2 = RS.GoalStore(db)
check("mở lại lần hai: migration không chạy lại", len(store2.events(owner, g_wait.id)) == n_events
      and sorted(store2.review_removed_goals()) == sorted(g.id for g in ALL.values()))
check("mở lại lần hai: không mục tiêu nào có thêm sự kiện, trạng thái giữ nguyên",
      {g.id: len(store2.events(owner, g.id)) for g in ALL.values()} == n_all
      and store2.get(owner, g_blocked.id).paused and store2.run_state(owner, g_blocked.id)["block_reason"] == "guard_deadline")
mig = [e["kind"] for e in store2.events(owner, g_wait.id) if e["by"] == "host:review_removed"]
check("migration ghi đúng hai sự kiện: gỡ đội và tạm dừng", sorted(mig) == ["paused", "team_detached"], mig)

# Tab Công việc: mục tiêu đã gỡ nằm ở Cần bạn, lý do bằng lời.
rows = store2.agent_goal_rows(owner, t.maker["agent_key"])
jobs = agent_jobs._auto_jobs(t.maker["agent_key"], store2, owner)
mine = {j["id"]: j for j in jobs}
check("tab Công việc: mục tiêu đã gỡ người review ở ngăn Cần bạn, mã lý do review_removed",
      mine[f"goal:{g_wait.id}"]["bucket"] == "needs_you" and mine[f"goal:{g_wait.id}"]["reason_code"] == "review_removed",
      rows)
bj = mine[f"goal:{g_blocked.id}"]
check("tab Công việc: mục tiêu bị chặn ngoài đội ở Cần bạn, có Tiếp tục kèm revision, Huỷ kèm revision",
      bj["bucket"] == "needs_you" and bj["resume"] == {"goal_id": g_blocked.id, "revision": bj["revision"]}
      and bj["cancel"]["revision"] == bj["revision"] and bj["next"] == {"code": "resume"}
      and bj["roles"] == ["worker"], bj)
check("đọc nhẹ trả revision cho mọi mục tiêu", all(isinstance(r.get("revision"), int) for r in rows), rows)
check("mục tiêu đã kết thúc vẫn hiện ở Đã xong", mine[f"goal:{g_failed.id}"]["bucket"] == "done")
check("trần đọc chỉ áp cho mục tiêu đã kết thúc: mục tiêu đang mở luôn đủ",
      {r["id"] for r in store2.agent_goal_rows(owner, t.maker["agent_key"], 0)} ==
      {g.id for g in ALL.values() if g is not g_failed})
check("người review cũ không còn thấy mục tiêu ở vai review (đội đã gỡ)",
      all(r["role"] != "reviewer" for r in store2.agent_goal_rows(owner, t.reviewer["agent_key"])))

# Mục tiêu mới sau 0.142.0: không có đội (cờ test tắt như máy thật).
t.store = store2
store2.attach_reviewer_teams = False
g_new = t.create()
check("mục tiêu mới không có người review cố định", store2.goal_team(owner, g_new.id) is None)

# Chủ bấm Tiếp tục: mục tiêu chạy lại theo luật thường (quyết định của chủ, không phải của migration).
store2.set_paused(owner, g_wait.id, False)
check("chủ Tiếp tục được", not store2.get(owner, g_wait.id).paused)

print(("FAIL" if fails else "PASS") + f" - test_review_removed_0142: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
