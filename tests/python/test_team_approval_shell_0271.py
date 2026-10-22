"""0.271.0: Team approval cards for shell commands (customer report, codes 5 and 22).

    python tests/python/test_team_approval_shell_0271.py

On Windows the Claude Code shell is `PowerShell`, not `Bash`. Reported: the card's "Sẽ làm" line said only "PowerShell";
after approval the member said "the identical command is still blocked" and the card stayed "Approved, waiting for the
assistant to run it"; a second member said it filed a request and no card showed it. Fake engines, real stores.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-shell-")
STATE = Path(os.environ["JAVIS_STATE_DIR"])
os.environ.setdefault("JAVIS_NO_REAL_TEAM_ENGINE", "1")

import sessions  # noqa: E402
import task_store  # noqa: E402
import team_approval  # noqa: E402
import team_gate  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:600]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def directive(**op):
    return f"\n<!-- JAVIS_TEAM: {json.dumps(op, ensure_ascii=False)} -->"


def run(coro):
    return asyncio.run(coro)


AGENTS = {"ag_lan": ("lan", "Lan"), "ag_minh": ("minh", "Minh"), "ag_hoa": ("hoa", "Hoa")}


class Fake:
    def __init__(self):
        self.script, self.calls = {}, []

    def say(self, agent, role, *answers):
        self.script.setdefault((agent, role), []).extend(answers)

    def engine_for(self, team, agent_key, role):
        async def run_(req):
            self.calls.append(dict(req, agent=agent_key))
            q = self.script.get((agent_key, role)) or []
            ans = q.pop(0) if q else f"{agent_key} {role} xong"
            if callable(ans):
                ans = await ans(req)
            return {"text": ans, "tokens_in": 5, "tokens_out": 3}
        return "fake", "fake-model", run_


def world(name):
    d = STATE / name
    d.mkdir()
    ss = sessions.SessionStore(db_path=d / "sessions.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    fake = Fake()

    def agent_info(brain, key):
        if key not in AGENTS:
            return None
        slug, nm = AGENTS[key]
        return {"slug": slug, "name": nm, "system": f"Bạn là {nm}."}

    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=fake.engine_for, agent_info=agent_info,
                      publish=lambda ev: None, notify=lambda tid, text: None)
    tid = team_store.new_team_id()
    sid = ss.create_session(brain="B", channel=f"team:{tid}", title=name)
    tm.create_team("B", name, "", sid, team_id=tid)
    for k in AGENTS:
        tm.add_member(tid, k, AGENTS[k][0])
    tm.set_leader(tid, "ag_lan")
    return r, tm, ts, ss, fake, tm.get(tid)


def cards(ss, team, aid=None):
    out = [m for m in ss.get_team_messages_page(team["session_id"], limit=300)["messages"]
           if (m.get("meta") or {}).get("kind") == "approval_request"]
    return [m for m in out if aid is None or m["meta"]["approval"]["approval_id"] == aid]


def job(r, team, text, mentions=None, key=None):
    return r.submit(team["team_id"], text, mentions=mentions or [], as_job=True,
                    client_msg_id=key or ("k" + str(abs(hash(text)) % 10**8)))["task_id"]


CMD = ('$wb = "C:\\Brain\\attachments\\teams\\t1\\Bang tham dinh.xlsx"; Add-Type -AssemblyName System.IO.Compression.'
       'FileSystem; $z = [IO.Compression.ZipFile]::OpenRead($wb); $e = $z.GetEntry("xl/workbook.xml"); '
       '$r = New-Object IO.StreamReader($e.Open()); $r.ReadToEnd(); $z.Dispose()')
RAN = []


def ps(cmd, who="ag_minh", **extra):
    async def go(req):
        ok, why = team_gate.native_check(req.get("team_gate"), "PowerShell", dict({"command": cmd}, **extra))
        if ok:
            RAN.append((who, cmd))
        return "chạy được" if ok else f"bị chặn: {why[:40]}"
    return go

# ═════ 1. Units: shell tools are one action per command text; the label shows the command ═════
a1 = team_gate._native_args("PowerShell", {"command": "Get-Content a.txt", "timeout": 60000, "description": "x"})
a2 = team_gate._native_args("PowerShell", {"command": "Get-Content a.txt", "timeout": 120000, "run_in_background": False})
check("unit: PowerShell fingerprint ignores timeout, description and background flag",
      team_approval.fingerprint("native", "PowerShell", a1) == team_approval.fingerprint("native", "PowerShell", a2), (a1, a2))
check("unit: Bash keeps its command-only fingerprint", team_gate._native_args("Bash", {"command": "ls", "timeout": 5})
      == {"command": "ls"})
check("unit: PowerShell is never read-only in the gate",
      team_gate.classify_native("PowerShell", {"command": "Get-Content a.txt"}, []) == "outside")
lbl = team_gate.native_label("PowerShell", {"command": CMD})
check("unit: the label carries the command, shortened on one line",
      lbl.startswith("PowerShell: $wb = ") and len(lbl) <= len("PowerShell: ") + team_gate.LABEL_COMMAND_MAX
      and lbl.endswith("…") and "\n" not in lbl, lbl)
check("unit: declared PowerShell, Bash, Write, WebFetch and outside MCP tools are native; javis hub tools are not",
      all(team_gate.is_native(t) for t in ("PowerShell", "Bash", "Write", "WebFetch", "mcp__gmail__send"))
      and not team_gate.is_native("mcp__javis__zalo_send_message") and not team_gate.is_native("zalo_send_message"))

# ═════ 2. A PowerShell call blocked by the gate, approved, rerun with another timeout ═════
r, tm, ts, ss, fake, T = world("ps-gate")
RAN.clear()
fake.say("ag_minh", "work", ps(CMD, timeout=60000), ps(CMD, timeout=120000, description="Đọc workbook"))
j = job(r, T, "Đọc bảng thẩm định", mentions=["ag_minh"])
run(r.dispatch_once())
ap = r.approvals.pending_for_task(j)
check("gate: the PowerShell call did not run and became a request", RAN == [] and ap and ap["kind"] == "action", ap)
check("gate: the card's 'Sẽ làm' line shows the command, not just 'PowerShell'",
      ap and "PowerShell: $wb = " in ap["action"] and ap["fingerprints"][0]["label"].startswith("PowerShell: $wb"), ap)
check("gate: the full command is kept for the card's list of calls",
      ap and json.dumps(CMD, ensure_ascii=False)[1:-1] in ap["fingerprints"][0]["call"], ap and ap["fingerprints"])
r.decide_approval(T["team_id"], ap["approval_id"], "approve", decision_key="ps1")
run(r.dispatch_once())
check("gate: the approved command runs on the rerun even with another timeout", RAN == [("ag_minh", CMD)], RAN)
check("gate: the job finished and the approval is consumed", ts.get_task(j)["status"] == "done"
      and r.approvals.get(ap["approval_id"])["status"] == "consumed", ts.get_task(j)["status"])

# ═════ 3. A declared PowerShell action (ask_approval) matches the real call ═════
r, tm, ts, ss, fake, T = world("ps-declared")
RAN.clear()
fake.say("ag_minh", "work",
         "Em cần đọc file Excel." + directive(op="ask_approval", title="Đọc workbook", action="Chạy lệnh đọc workbook",
                                             actions=[{"tool": "PowerShell", "args": {"command": CMD}}]),
         ps(CMD, timeout=30000))
j = job(r, T, "Đọc bảng thẩm định 2", mentions=["ag_minh"])
run(r.dispatch_once())
ap = r.approvals.pending_for_task(j)
check("declared: the request lists the PowerShell call with its command", ap and ap["fingerprints"]
      and ap["fingerprints"][0]["label"].startswith("PowerShell: $wb"), ap)
r.decide_approval(T["team_id"], ap["approval_id"], "approve", decision_key="psd1")
run(r.dispatch_once())
check("declared: the identical command is NOT blocked again after approval", RAN == [("ag_minh", CMD)]
      and ts.get_task(j)["status"] == "done", (RAN, ts.get_task(j)["status"], ts.get_task(j).get("block_kind")))
check("declared: no second request was filed", len(r.approvals.for_task(j)) == 1, r.approvals.for_task(j))

print()
if fails:
    print(f"FAIL - {len(fails)} check(s)")
    raise SystemExit(1)
print("OK - test_team_approval_shell_0271: all pass")
