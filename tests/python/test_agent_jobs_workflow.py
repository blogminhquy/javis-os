"""Workflow runs in an assistant's Jobs tab (Partners page).

    python tests/python/test_agent_jobs_workflow.py

Owner, 08/11/2026: the Jobs tab stayed empty while a workflow ran the assistant's step. Each step of a run now records
the assistant's slug and key (workflow_runs.ghi_buoc), and agent_jobs lists the runs the assistant took part in: one
card per run, its bucket from the run's status, the step running now, a failed run marked failed.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import tempfile
import time
from pathlib import Path

import agent_jobs  # noqa: E402
import workflow_runs  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else f"  [{extra}]"))
    if not cond:
        fails.append(name)


tmp = Path(tempfile.mkdtemp())
st = workflow_runs.WorkflowRunStore(tmp / "runs.sqlite3")
B = "/brains/shop"


def run(slug, name, steps, status=None, output="", error=""):
    rid = st.bat_dau(brain=B, slug=slug, name=name, input="x", source="kanban", session_id="s_" + slug)
    for i, (agent_slug, key, state) in enumerate(steps):
        st.ghi_buoc(rid, i, agent=agent_slug.title(), task="t", agent_slug=agent_slug, agent_key=key)
        if state == "done":
            st.ghi_buoc(rid, i, output=f"out {i}", verified=True)
        elif state == "error":
            st.ghi_buoc(rid, i, error="boom")
    if status:
        st.ket_thuc(rid, status, output=output, error=error)
    time.sleep(0.01)
    return rid


r_live = run("bao-cao", "Báo cáo tuần", [("minh", "k_minh", "done"), ("lan", "k_lan", "running")])
r_mine = run("dang-bai", "Đăng bài", [("minh", "k_minh", "running")])
r_wait = run("duyet", "Duyệt giá", [("minh", "k_minh", "done")], status="waiting")
r_done = run("tong-hop", "Tổng hợp", [("minh", "k_minh", "done"), ("lan", "k_lan", "done")], status="done", output="ok")
r_err = run("loi", "Hỏng", [("minh", "k_minh", "error")], status="error", error="engine down")
r_other = run("khac", "Không có Minh", [("lan", "k_lan", "done")], status="done")
r_old_key = run("cu", "Trợ lý cũ cùng slug", [("minh", "k_cu", "done")], status="done")
# A run recorded before steps carried a slug: name only, never listed.
rid = st.bat_dau(brain=B, slug="xua", name="Xưa", input="", source="other")
st.ghi_buoc(rid, 0, agent="Minh", task="t")
st.ket_thuc(rid, "done")
# Same slug in another brain.
rid = st.bat_dau(brain="/brains/other", slug="bao-cao", name="Brain khác", input="", source="other")
st.ghi_buoc(rid, 0, agent="Minh", agent_slug="minh", agent_key="k_minh")

# Store query
rows = st.runs_of_agent(B, "minh")
ids = {r["id"] for r in rows}
check("runs_of_agent: every run Minh stepped in, this brain only",
      ids == {r_live, r_mine, r_wait, r_done, r_err, r_old_key}, sorted(ids))
check("runs_of_agent: open runs first", [r["status"] for r in rows][:3] == ["running", "running", "waiting"]
      or set(r["status"] for r in rows[:3]) == {"running", "waiting"}, [r["status"] for r in rows])
check("runs_of_agent: a slug with LIKE wildcards matches literally", st.runs_of_agent(B, "m_nh") == [])
check("runs_of_agent: empty slug, nothing", st.runs_of_agent(B, "") == [])
check("ghi_buoc: slug and key stored on the step",
      st.lay(r_done)["steps"][0].get("agent_slug") == "minh" and st.lay(r_done)["steps"][0].get("agent_key") == "k_minh")

# Jobs
jobs = {j["id"]: j for j in agent_jobs._workflow_jobs("k_minh", "minh", B, st, steps_of=lambda s: 4 if s == "bao-cao" else None)}
check("jobs: the earlier assistant's run with this slug is not Minh's", f"workflow:{r_old_key}" not in jobs, list(jobs))
check("jobs: runs without Minh are not listed", f"workflow:{r_other}" not in jobs)
j = jobs.get(f"workflow:{r_live}") or {}
check("running run, another assistant's step: In progress, says whose step",
      j.get("bucket") == "running" and j.get("next") == {"code": "wf_other", "n": 2, "agent": "Lan"}, j.get("next"))
check("progress uses the workflow's step count", j.get("progress") == {"done": 1, "total": 4}, j.get("progress"))
check("source, kind, open target", j.get("source") == "workflow" and j.get("kind") == "workflow"
      and j.get("open") == {"kind": "workflow", "slug": "bao-cao", "session_id": "s_bao-cao", "run_id": r_live}, j.get("open"))
j = jobs.get(f"workflow:{r_mine}") or {}
check("running run on Minh's step: 'doing step N'", j.get("next") == {"code": "wf_mine", "n": 1, "agent": ""}, j.get("next"))
j = jobs.get(f"workflow:{r_wait}") or {}
check("waiting for review: Needs you", j.get("bucket") == "needs_you" and j.get("next") == {"code": "wf_review"}, j)
j = jobs.get(f"workflow:{r_done}") or {}
check("done: Done, Minh's own step output as the result", j.get("bucket") == "done" and j.get("result") == "out 0", j)
j = jobs.get(f"workflow:{r_err}") or {}
check("error: Done, marked failed, with the reason", j.get("bucket") == "done" and j.get("failed") is True
      and j.get("reason") == "engine down", j)
later = {x["id"]: x for x in agent_jobs._workflow_jobs("k_minh", "minh", B, st, now=time.time() + agent_jobs.STALE_RUN + 60)}
j = later.get(f"workflow:{r_mine}") or {}
check("a run cut off mid-way (still 'running' hours later) moves to Needs you and says so",
      j.get("bucket") == "needs_you" and j.get("next") == {"code": "wf_stale"}, j)
check("a finished run is not touched by the stale rule", (later.get(f"workflow:{r_done}") or {}).get("bucket") == "done")
check("no fake cancel or priority buttons", all(x["cancel"] is None and x["priority"] is None for x in jobs.values()))
check("an assistant with no key yet still sees its runs (slug match)",
      len(agent_jobs._workflow_jobs("", "minh", B, st)) == len(jobs) + 1)

# collect / active_counts
out = agent_jobs.collect("k_minh", "minh", B, runs=st)
check("collect: workflow is a source with its own count", out["source_counts"].get("workflow") == 5, out["source_counts"])
check("collect: filter by the workflow source", {x["source"] for x in agent_jobs.collect("k_minh", "minh", B, runs=st,
                                                                                         source="workflow")["jobs"]}
      == {"workflow"})
check("collect: without a run store the source is just empty", agent_jobs.collect("k_minh", "minh", B)["source_counts"]
      .get("workflow") == 0)
cn = agent_jobs.active_counts({"minh": "k_minh"}, B, runs=st).get("minh", {})
check("card counts: running and needs-you runs count, the failed one is red",
      cn.get("running") == 2 and cn.get("needs_you") == 1 and cn.get("failed") == 1 and cn.get("done") == 1, cn)
cn_marked = agent_jobs.active_counts({"minh": "k_minh"}, B, runs=st,
                                     marks={f"workflow:{r_done}": {"state": "archived", "at": 1},
                                            f"workflow:{r_err}": {"state": "deleted", "at": 1}}).get("minh", {})
check("card counts: archived and deleted runs drop out like other jobs",
      cn_marked.get("done") == 0 and cn_marked.get("failed") == 0, cn_marked)
old = agent_jobs.active_counts({"minh": "k_minh"}, B, runs=st, now=time.time() + 2 * agent_jobs.DONE_FRESH).get("minh", {})
check("card counts: a run finished over a day ago is not 'just finished'", old.get("done") == 0 and old.get("failed") == 0, old)

# Wiring
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("legacy runner sends the step's agent slug", '"agent_slug": agent_slug, "task": task_f}' in main_src)
check("run history records slug and key", "agent_slug=_aslug, agent_key=_akey" in main_src)
check("graph runner sends the step's agent slug",
      '"agent": node.agent, "agent_slug": node.agent' in (SERVER / "workflow_runtime.py").read_text(encoding="utf-8"))
check("Jobs routes pass the run store", main_src.count("runs=_workflow_runs_store()") == 2)

print("\n" + (f"{len(fails)} FAIL" if fails else "All green"))
raise SystemExit(1 if fails else 0)
