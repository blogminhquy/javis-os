"""The chat's pre-push gate uses the saved "Check commands" whichever way the brain is spelled (#1109).

    python tests/run.py github_checks_brain_alias      (no network, no git)

The bug: the dashboard saved a repo record with the brain's folder ("/brains/Brain Default") while a chat turn passed
the alias "brain" to `github_work.after_turn`. `github_repos.find` compared the strings, missed the record, and the
gate fell back to the commands read from CI. The GitHub card on the Connections page (`local_view` -> `list_local`)
listed nothing for the same reason. CI commands also ignored `working-directory`, so a repo with its app in a
subfolder ran `npm ci` at the root and failed every time: the saved commands were the way around that.

Pinned here:
  1. find / list_local / local_view match a record saved under the folder when asked with the alias, and the reverse
  2. another brain's folder never matches the alias (no folding into the default brain)
  3. gate_repo, called with the alias, runs the SAVED commands
  4. CI commands start in the step's working-directory, else the job's defaults.run, else the workflow's
  5. a working-directory holding an expression is left to CI; the Windows form uses `cd /d`
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-gh-alias-")
os.environ["JAVIS_STATE_DIR"] = _STATE
_BRAINS = Path(tempfile.mkdtemp(prefix="javis-gh-alias-brains-"))
os.environ["BRAINS_DIR"] = str(_BRAINS)

import brain_ident  # noqa: E402
import github_gate  # noqa: E402
import github_repos  # noqa: E402
import github_work  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


default_dir = _BRAINS / "Brain Default"
other_dir = _BRAINS / "Shop"
default_dir.mkdir(parents=True)
other_dir.mkdir(parents=True)
brain_ident.set_default_dir(lambda: default_dir)

SAVED = [{"name": "install web", "run": "cd web && npm ci"}, {"name": "test web", "run": "cd web && npm test"}]
github_repos._put({"id": "r1", "brain": str(default_dir), "full_name": "owner/app", "path": str(_BRAINS / "clone"),
                   "folder_id": "f1", "default_branch": "main", "checks": SAVED})
github_repos._put({"id": "r2", "brain": str(other_dir), "full_name": "owner/shop", "path": str(_BRAINS / "clone2"),
                   "folder_id": "f2", "default_branch": "main"})

# 1. one brain, two spellings
check("1. find with the alias sees the record saved under the folder",
      (github_repos.find("brain", "owner/app") or {}).get("id") == "r1")
check("1. find with the folder still works", (github_repos.find(str(default_dir), "owner/app") or {}).get("id") == "r1")
check("1. list_local with the alias lists it", [r["id"] for r in github_repos.list_local("brain")] == ["r1"],
      github_repos.list_local("brain"))
check("1. the GitHub card (local_view) lists it", [r["full_name"] for r in github_repos.local_view("brain")] == ["owner/app"])
github_repos._put({"id": "r3", "brain": "brain", "full_name": "owner/lib", "path": str(_BRAINS / "clone3"),
                   "folder_id": "f3", "default_branch": "main"})
check("1. and the reverse: a record saved under the alias is found with the folder",
      (github_repos.find(str(default_dir), "owner/lib") or {}).get("id") == "r3")

# 2. no folding
check("2. another brain's repo is not found with the alias", github_repos.find("brain", "owner/shop") is None)
check("2. nor listed under it", "r2" not in [r["id"] for r in github_repos.list_local("brain")])
check("2. an unknown folder matches nothing", github_repos.find(str(_BRAINS / "gone"), "owner/app") is None)

# 3. the gate runs the saved commands
seen = {}
real = (github_work.fingerprint, github_work._has_work, github_gate.run_gate)
github_work.fingerprint = lambda wt: "fp-1"
github_work._has_work = lambda repo: True


def fake_run_gate(wt, base, checks=None, **kw):
    seen["checks"] = checks
    return {"ok": True}


github_gate.run_gate = fake_run_gate
try:
    wt = tempfile.mkdtemp(prefix="javis-gh-alias-wt-")
    github_work.gate_repo("sid-1", "brain", {"full_name": "owner/app", "worktree": wt, "repo_id": "r1"}, force=True)
finally:
    github_work.fingerprint, github_work._has_work, github_gate.run_gate = real
check("3. the gate ran the saved commands", seen.get("checks") == SAVED, seen.get("checks"))

# 4. working-directory
WF = """
on: [push, pull_request]
defaults:
  run:
    working-directory: app
jobs:
  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - run: npm ci
      - name: lint docs
        working-directory: docs site
        run: npm run lint
      - name: multi
        run: |
          npm test
          npm run build
  api:
    runs-on: ubuntu-latest
    steps:
      - run: pytest
      - name: root
        working-directory: .
        run: make check
      - name: from CI only
        working-directory: ${{ github.workspace }}/x
        run: echo x
"""
cmds = {c["name"]: c["run"] for c in github_gate.commands_from_workflow(WF, host="linux")}
check("4. job defaults.run.working-directory", cmds.get("npm ci") == "cd web && npm ci", cmds)
check("4. a step's own working-directory wins, quoted", cmds.get("lint docs") == "cd 'docs site' && npm run lint", cmds)
check("4. a multi-line step starts with its own cd line", cmds.get("multi") == "cd web\nnpm test\nnpm run build", cmds)
check("4. workflow defaults.run when the job has none", cmds.get("pytest") == "cd app && pytest", cmds)
check("4. working-directory '.' runs at the root", cmds.get("root") == "make check", cmds)

# 5. expressions and Windows
check("5. an expression in working-directory is left to CI", "from CI only" not in cmds, cmds)
WIN_WF = WF.replace("runs-on: ubuntu-latest", "runs-on: windows-latest")
win = {c["name"]: c["run"] for c in github_gate.commands_from_workflow(WIN_WF, host="windows")}
check("5. Windows uses cd /d", win.get("npm ci") == 'cd /d "web" && npm ci', win)
plain = github_gate.commands_from_workflow("on: [push]\njobs:\n  t:\n    runs-on: ubuntu-latest\n    steps:\n      - run: make\n",
                                           host="linux")
check("5. no working-directory: the command is unchanged", [c["run"] for c in plain] == ["make"], plain)

for name in ("server/github_gate.py", "server/github_repos.py", "tests/python/test_github_checks_brain_alias.py"):
    s = (ROOT / name).read_text(encoding="utf-8")
    check(f"{name} has no long dash", chr(0x2014) not in s and chr(0x2013) not in s)

if fails:
    raise SystemExit(f"{len(fails)} check(s) failed: {fails}")
print("all ok")
