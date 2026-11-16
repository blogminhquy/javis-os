"""Background jobs and workflow runs a restart cut short (owner, 16/11/2026).

    python tests/python/test_jobs_resume_after_restart.py

Owner: "Những việc nào đang dang dở kể cả ở cộng sự, ở chat hay team và workflow, khởi động lại server sau khi update
cũng phải khởi động lại tất cả các tiến trình".

- A Kanban job (also an assistant's assigned job) that was running goes back to the queue at once when the process
  starts, with the attempt of the dead run given back. Before, it waited out its 90 s lease and the cut cost one of its
  three attempts, and on Windows every update is a hard kill.
- A workflow run that was running no longer says "running" for ever: it is closed with the reason, and a run the owner
  started in the workflow's chat leaves one line there.
Real stores on temp SQLite, no model call.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-jobs-resume-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-jobs-resume-brains-")
TMP = Path(tempfile.mkdtemp(prefix="javis-jobs-resume-w-"))

from task_store import TaskStore  # noqa: E402
import workflow_runs  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---------- Kanban: back to the queue at boot, the attempt given back ----------
store = TaskStore(TMP / "kanban.sqlite3")
root = str(TMP / "brain")
Path(root).mkdir()
other = str(TMP / "brain2")
Path(other).mkdir()
tid = store.enqueue(root, "Viết báo cáo", "làm", capability="files", status="ready")
waiting = store.enqueue(root, "Việc chờ", "làm", capability="files", status="ready")
far = store.enqueue(other, "Việc brain khác", "làm", capability="files", status="ready")
check("setup: the job is claimed and running, one attempt used", store.claim(tid, "old-worker") and store.claim(far, "old-worker")
      and store.get_task(tid)["status"] == "running" and store.get_task(tid)["attempts"] == 1, store.get_task(tid))
lease = store.get_task(tid)["claim_expires_at"]
check("its lease has not run out: the old sweep would still leave it alone", lease > time.time() and store.reclaim_stale(root, set()) == 0)
n = store.reclaim_boot(root)
t = store.get_task(tid)
check("at boot the cut job goes back to the queue at once", n == 1 and t["status"] == "ready" and t["claimed_by"] == ""
      and t["claim_expires_at"] == 0, t)
check("the attempt the dead run took is given back", t["attempts"] == 0, t["attempts"])
runs = store.list_runs(tid)
check("the dead run is closed as stale with the reason", runs and runs[0]["status"] == "stale" and runs[0]["error"] == "server restarted", runs)
check("a job that was only waiting, and a job of another brain, are not touched", store.get_task(waiting)["status"] == "ready"
      and store.get_task(waiting)["attempts"] == 0 and store.get_task(far)["status"] == "running")
check("the job can be taken again right away", store.claim(tid, "new-worker") is not None and store.get_task(tid)["attempts"] == 1)
store.reclaim_boot(root)
check("a second cut is forgiven too", store.get_task(tid)["attempts"] == 0)
store.claim(tid, "w3")
store.reclaim_boot(root)
check("a third cut costs the attempt: a job that keeps bringing the server down cannot run for ever",
      store.get_task(tid)["status"] == "ready" and store.get_task(tid)["attempts"] == 1, store.get_task(tid))
check("nothing running: nothing reclaimed", store.reclaim_boot(root) == 0)

# ---------- workflow runs ----------
wr = workflow_runs.WorkflowRunStore(TMP / "runs.sqlite3")
cut = wr.bat_dau(brain="b", slug="bao-cao", name="Báo cáo tuần", input="chạy", source="web", session_id="s-web")
wr.ghi_buoc(cut, 0, agent="Lan", task="Thu số liệu")
wr.ghi_buoc(cut, 0, output="xong số liệu")
wr.ghi_buoc(cut, 1, agent="Minh", task="Viết báo cáo")
bg = wr.bat_dau(brain="b", slug="bao-cao", name="Báo cáo tuần", input="chạy", source="kanban")
waiting_run = wr.bat_dau(brain="b", slug="duyet", name="Duyệt", input="x", source="web", session_id="s-wait")
wr.ket_thuc(waiting_run, "waiting", task_id="t1")
done_run = wr.bat_dau(brain="b", slug="xong", name="Xong", input="x", source="web")
wr.ket_thuc(done_run, "done", output="ok")
boot = time.time() + 1
rows = wr.close_cut(boot, "Máy chủ khởi động lại giữa chừng")
check("the two runs that were running are closed with the reason", sorted(r["id"] for r in rows) == sorted([cut, bg])
      and wr.lay(cut)["status"] == "error" and wr.lay(cut)["error"] == "Máy chủ khởi động lại giữa chừng"
      and wr.lay(bg)["status"] == "error", [(r["id"], r["status"]) for r in rows])
check("the closed rows say who started them and how far they got", {r["id"]: (r["source"], r["session_id"], len(r["steps"])) for r in rows}
      == {cut: ("web", "s-web", 2), bg: ("kanban", "", 0)}, rows)
check("a run awaiting approval and a finished run are left as they are", wr.lay(waiting_run)["status"] == "waiting"
      and wr.lay(done_run)["status"] == "done")
time.sleep(0.01)
fresh = wr.bat_dau(brain="b", slug="moi", name="Mới", input="x", source="web")
check("a run started by THIS process is never closed", wr.close_cut(boot - 2, "x") == [] and wr.lay(fresh)["status"] == "running")

# ---------- the host: the workflow chat gets one line, the scheduler-owned run does not ----------
import main  # noqa: E402

sessions = main.get_store()
sid = sessions.create_session(brain="brain", channel="workflow:bao-cao")
mst = workflow_runs.get_store()
web = mst.bat_dau(brain="brain", slug="bao-cao", name="Báo cáo tuần", input="chạy", source="web", session_id=sid)
mst.ghi_buoc(web, 0, agent="Lan", task="Thu số liệu")
mst.ghi_buoc(web, 0, output="xong")
kb = mst.bat_dau(brain="brain", slug="bao-cao", name="Báo cáo tuần", input="chạy", source="kanban")
main._PROCESS_STARTED = time.time() + 1
closed = main.close_cut_workflow_runs()
msgs = sessions.get_messages(sid)
check("the host closes both runs", sorted(r["id"] for r in closed) == sorted([web, kb]) and mst.lay(web)["status"] == "error")
check("the workflow's chat keeps one line: where it stopped, why it was not run again, what to press",
      len(msgs) == 1 and msgs[0]["role"] == "assistant" and "Báo cáo tuần" in msgs[0]["content"] and "1 bước" in msgs[0]["content"]
      and "Chạy" in msgs[0]["content"], msgs)
check("running it twice says nothing twice", main.close_cut_workflow_runs() == [] and len(sessions.get_messages(sid)) == 1)
src = (SERVER / "tasks.py").read_text(encoding="utf-8")
check("the Kanban feature reclaims once per process, before it dispatches", "self.store.reclaim_boot(root)" in src
      and src.index("self.store.reclaim_boot(root)") < src.index("self._dispatcher_task = asyncio.create_task("))
check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())

if fails:
    print(f"\nFAILED {len(fails)}: " + "; ".join(fails))
    raise SystemExit(1)
print("\nALL OK")
