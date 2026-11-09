"""git before GitHub (owner, 09/11/2026): Connect checks for git and installs it when the machine has none.

    python tests/run.py git_setup      (no network, installs nothing: the install steps are fakes)

Covered:
  - a git that exists but is missing from this process's PATH (installed after the server started) is found, and its
    folder is added to PATH so every later `git ...` works;
  - start() runs the install in a worker thread, reports installing, then ok with the version;
  - a failed step falls through to the next one; when all fail the state says failed with the tool's own last line;
  - a second start() while one runs does not start a second install;
  - no install method here (Linux without root or sudo) = nothing started, can_install false, a command to run by hand;
  - the Git for Windows asset picker takes the installer for the CPU, never the portable or MinGit builds;
  - the routes exist, and GitHub status and brain backup ask git_setup instead of a bare PATH lookup.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-gitsetup-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import git_setup  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        _fails.append(name)


def wait_done(limit=10.0):
    end = time.time() + limit
    while time.time() < end:
        if git_setup.state()["install"] != "installing":
            return
        time.sleep(0.05)


def reset_job():
    with git_setup._LOCK:
        git_setup._JOB.update(install="idle", method="", wait_user=False, error="", version="", started=0.0)


# ---- pure: the Git for Windows asset picker
assets = [{"name": "PortableGit-2.47.0-64-bit.7z.exe"}, {"name": "MinGit-2.47.0-64-bit.zip"},
          {"name": "Git-2.47.0-64-bit.tar.bz2"}, {"name": "Git-2.47.0-arm64.exe"}, {"name": "Git-2.47.0-64-bit.exe"}]
check("x64 takes the 64-bit installer", (git_setup.pick_asset(assets, "AMD64") or {}).get("name") == "Git-2.47.0-64-bit.exe")
check("ARM takes the arm64 installer", (git_setup.pick_asset(assets, "ARM64") or {}).get("name") == "Git-2.47.0-arm64.exe")
check("a patch release name (2.47.0.2) still matches",
      (git_setup.pick_asset([{"name": "Git-2.47.0.2-64-bit.exe"}], "x86_64") or {}).get("name") == "Git-2.47.0.2-64-bit.exe")
check("no installer in the release = None", git_setup.pick_asset(assets[:3], "AMD64") is None)
check("an installer's progress bars do not hide its last real line",
      git_setup._tail("Downloading\r  ██████  30%\r  ██████████ 100%\nInstaller failed with exit code: 1618\n") ==
      "Installer failed with exit code: 1618")

check("the manual command is never empty", bool(git_setup.manual()))
check("the manual page is git-scm", git_setup.MANUAL_URL.startswith("https://git-scm.com/"))

if os.name == "nt":
    print("SKIP: the fake-git part needs a POSIX shell script")
else:
    empty = tempfile.mkdtemp(prefix="nopath-")
    home = Path(tempfile.mkdtemp(prefix="gitdir-"))
    fake_git = home / "git"

    def make_git(ver="9.9.9"):
        fake_git.write_text("#!/bin/sh\necho 'git version " + ver + "'\n", encoding="utf-8")
        fake_git.chmod(fake_git.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # A machine with no git: nothing on PATH, nothing in the folders installers use.
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = empty
    git_setup._candidate_dirs = lambda: [str(home)]
    check("no git anywhere: find() is empty", git_setup.find() == "" and not git_setup.available())

    # Installed after the server started: the file is there, PATH does not list it yet.
    make_git()
    check("a git outside PATH is found in the installers' folders", git_setup.find() == str(fake_git))
    check("its folder is added to PATH for every later git call", str(home) in os.environ["PATH"].split(os.pathsep))
    check("version() reads `git --version`", git_setup.version() == "9.9.9")
    fake_git.unlink()
    os.environ["PATH"] = empty

    # start(): the first method fails, the second installs.
    calls = []

    def bad():
        calls.append("bad")
        raise git_setup._Fail("E: Unable to locate package git")

    def good():
        calls.append("good")
        time.sleep(0.3)
        make_git("2.47.0")

    real_runner = git_setup._runner
    git_setup._runner = lambda m: {"bad": bad, "good": good}[m]
    git_setup.plan = lambda: ["bad", "good"]
    reset_job()
    st = git_setup.start()
    check("start() answers at once with installing", st["install"] == "installing" and not st["has_git"], st)
    again = git_setup.start()
    check("a second start() while installing starts nothing new", again["install"] == "installing")
    wait_done()
    st = git_setup.state()
    check("a failed method falls through to the next one", calls == ["bad", "good"], calls)
    check("after the install: has_git, ok, with the version", st["has_git"] and st["install"] == "ok" and st["version"] == "2.47.0", st)
    check("no error once git is there", st["error"] == "")
    check("start() with git present starts nothing", git_setup.start()["has_git"] and calls == ["bad", "good"], calls)

    # Every method fails: failed, with the tool's own last line.
    fake_git.unlink(missing_ok=True)
    os.environ["PATH"] = empty
    calls.clear()
    git_setup.plan = lambda: ["bad"]
    reset_job()
    git_setup.start()
    wait_done()
    st = git_setup.state()
    check("all methods failed: install=failed, no git", st["install"] == "failed" and not st["has_git"], st)
    check("the error carries the installer's own line", "Unable to locate package git" in st["error"], st["error"])
    calls.clear()
    git_setup.start()
    wait_done()
    check("a failed install can be started again", calls == ["bad"], calls)

    # A step that raises something unexpected must not leave the job installing forever.
    def broken():
        raise RuntimeError("boom")
    git_setup._runner = lambda m: broken
    git_setup.plan = lambda: ["weird"]
    reset_job()
    git_setup.start()
    wait_done()
    check("an unexpected error ends as failed, not stuck installing", git_setup.state()["install"] == "failed")

    # No method on this machine: nothing starts, the dashboard shows the command to run by hand.
    git_setup.plan = lambda: []
    reset_job()
    st = git_setup.start()
    check("no install method: nothing starts", st["install"] == "idle" and not st["has_git"], st)
    check("no install method: can_install false, a manual command", st["can_install"] is False and st["manual"], st)

    # Linux runners: root runs the package manager directly, apt-get retries after `apt-get update`.
    ran = []

    def fake_run(argv, timeout=0, env=None):
        ran.append(list(argv))
        if argv[-1] == "git" and "install" in argv and len([a for a in ran if "update" in a]) == 0:
            return 100, "E: Unable to locate package git"
        if "update" in argv:
            return 0, "ok"
        make_git()
        return 0, "done"

    real_run, real_root = git_setup._run, git_setup._is_root
    git_setup._run = fake_run
    git_setup._is_root = lambda: True
    fake_git.unlink(missing_ok=True)
    git_setup._install_linux("apt-get")
    check("apt-get: install, then update and install again when the lists are missing",
          ran == [["apt-get", "install", "-y", "git"], ["apt-get", "update"], ["apt-get", "install", "-y", "git"]], ran)
    git_setup._is_root = lambda: False
    ran.clear()
    fake_git.unlink()
    git_setup._run = lambda argv, timeout=0, env=None: (ran.append(list(argv)), make_git(), (0, ""))[2]
    git_setup._install_linux("dnf")
    check("not root: password-less sudo, never a prompt", ran and ran[0][:2] == ["sudo", "-n"], ran)
    git_setup._run, git_setup._is_root, git_setup._runner = real_run, real_root, real_runner

    os.environ["PATH"] = old_path

# ---- the routes and the callers
routes = (SERVER / "routes" / "github.py").read_text(encoding="utf-8")
check("GET /github/git reports git_setup.state", '@r.get("/github/git")' in routes and "git_setup.state" in routes)
check("POST /github/git/install runs git_setup.start off the event loop",
      '@r.post("/github/git/install")' in routes and "run_in_threadpool(git_setup.start)" in routes)
repos = (SERVER / "github_repos.py").read_text(encoding="utf-8")
check("GitHub status asks git_setup, which also sees a git installed after start-up",
      '"has_git": git_setup.available()' in repos)
brain = (SERVER / "git_brain.py").read_text(encoding="utf-8")
check("brain backup asks git_setup too", "git_setup.available()" in brain)
check("no em dash in the module", chr(0x2014) not in (SERVER / "git_setup.py").read_text(encoding="utf-8"))

print()
if _fails:
    print(f"{len(_fails)} FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("All git_setup tests passed.")
