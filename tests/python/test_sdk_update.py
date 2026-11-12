"""The Claude Agent SDK package updates itself, inside fences (2026-11-10).

    python tests/run.py sdk_update

server/sdk_update.py moves `claude-agent-sdk` to newer releases of its own series once a day, on the same switch as the
Claude Code update. It installs a package from the Internet into the server's environment, so this test pins the fences:
which release may be picked, that nothing else is allowed to move, that a release failing its check is rolled back and
not tried again, and that the Docker build is left alone.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = Path(tempfile.mkdtemp(prefix="javis-sdkupd-"))
os.environ["JAVIS_STATE_DIR"] = str(_STATE)
os.environ.pop("JAVIS_CLAUDE_AUTO_UPDATE", None)

import sdk_update as su  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


NOW = 1_800_000_000.0
DAY = 86400


def rel(age_days, yanked=False, py=">=3.10"):
    t = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(NOW - age_days * DAY)) + ".000000Z"
    return [{"upload_time_iso_8601": t, "yanked": yanked, "requires_python": py, "filename": "x.whl"}]


RELEASES = {
    "0.2.110": rel(60), "0.2.116": rel(50), "0.2.121": rel(40), "0.2.170": rel(20), "0.2.179": rel(4),
    "0.2.180": rel(1),                 # too fresh
    "0.2.178": rel(6, yanked=True),    # pulled by the publisher
    "0.2.181rc1": rel(30),             # pre-release
    "0.3.0": rel(30),                  # next series
    "1.0.0": rel(30),
    "0.2.177": [],                     # no files
}

# ---- 1. which release may be picked ----
check("newest release of the same series that has cooled down", su.pick("0.2.116", RELEASES, NOW) == "0.2.179")
check("a release younger than the cool-down is not taken", su.pick("0.2.179", RELEASES, NOW) == "")
check("it is taken once it has cooled down", su.pick("0.2.179", RELEASES, NOW + 3 * DAY) == "0.2.180")
check("never the next minor or major series", su.pick("0.2.180", RELEASES, NOW + 30 * DAY) == "")
check("a yanked release is skipped", su.pick("0.2.177", {"0.2.178": rel(6, yanked=True)}, NOW) == "")
check("a pre-release is skipped", su.pick("0.2.180", {"0.2.181rc1": rel(30)}, NOW) == "")
check("never a downgrade", su.pick("0.2.180", {"0.2.116": rel(50)}, NOW) == "")
check("a version remembered as bad is skipped",
      su.pick("0.2.116", RELEASES, NOW, bad=["0.2.179"]) == "0.2.170")
check("a release that needs a newer Python is skipped",
      su.pick("0.2.116", {"0.2.170": rel(20, py=">=3.99")}, NOW) == "")
check("an installed version we cannot read moves nowhere", su.pick("0.2.116.dev1", RELEASES, NOW) == ""
      and su.pick("", RELEASES, NOW) == "")
check("a release with no upload time is not trusted",
      su.pick("0.2.116", {"0.2.170": [{"yanked": False}]}, NOW) == "")
check("the cool-down is at least three days", su.COOLDOWN_S >= 3 * DAY)

# ---- 2. nothing else moves ----
req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
con = su.constraints_text(req)
check("constraints carry the exact pins of requirements.txt", "fastapi==" in con and "starlette==" in con, con)
check("constraints leave the SDK itself free", "claude-agent-sdk" not in con, con)
check("constraints skip comments and ranges", "#" not in con and ">=" not in con, con)
check("constraints_text on its own: extras and trailing comments",
      su.constraints_text("uvicorn[standard]==0.51.0  # x\nfoo>=1\n# bar==2\nclaude-agent-sdk==0.2.116\n") == "uvicorn==0.51.0\n")
_sdk_line = [x for x in req.splitlines() if x.strip().startswith("claude-agent-sdk")]
check("requirements.txt keeps the SDK inside one series (a floor and a ceiling, or an exact pin)",
      len(_sdk_line) == 1 and ("==" in _sdk_line[0] or (">=" in _sdk_line[0] and ",<" in _sdk_line[0].replace(" ", ""))),
      _sdk_line)

# ---- 3. update(): the outside steps are replaced ----
su.installed = lambda: STATE["v"]
STATE = {"v": "0.2.116", "pip": [], "smoke": []}


def fake_pip(version, constraints):
    STATE["pip"].append((version, bool(constraints.strip())))
    if version in STATE.get("pip_fail", ()):
        return False, "no matching distribution"
    STATE["v"] = version
    return True, ""


def fake_smoke(version):
    STATE["smoke"].append(version)
    return (version not in STATE.get("smoke_fail", ())), "ClaudeAgentOptions lost fields: hooks"


def run(**kw):
    return su.update("auto", fetch=lambda: RELEASES, pip_install=fake_pip, smoke=fake_smoke, now=NOW, **kw)


r = run()
check("a newer release is installed and reported", r["ok"] and r["changed"] and r["from"] == "0.2.116"
      and r["to"] == "0.2.179" and STATE["v"] == "0.2.179", r)
check("pip ran under the constraints, and the new version was checked", STATE["pip"] == [("0.2.179", True)]
      and STATE["smoke"] == ["0.2.179"], STATE)
st = json.loads((_STATE / "sdk-update.json").read_text(encoding="utf-8"))
check("the attempt is stored", st.get("to") == "0.2.179" and st.get("ts") == NOW, st)
check("not due again for a day", not su.due(NOW + 3600) and su.due(NOW + su.PERIOD_S + 1))
r = run()
check("already current: ok, nothing installed", r["ok"] and not r["changed"] and len(STATE["pip"]) == 1, r)

# a release that fails its check is rolled back and remembered
STATE.update(v="0.2.116", pip=[], smoke=[], smoke_fail=("0.2.179",))
r = run()
check("a release that fails its check is rolled back", not r["ok"] and r.get("rolled_back") and STATE["v"] == "0.2.116"
      and STATE["pip"] == [("0.2.179", True), ("0.2.116", True)], (r, STATE))
check("the error says the check failed", "check" in r.get("error", "") or "chạy thử" in r.get("error", ""), r)
check("the bad version is remembered", r.get("bad") == ["0.2.179"], r)
STATE.update(pip=[], smoke=[])
r = run()
check("next day it is skipped and the one before is tried", r["ok"] and r["to"] == "0.2.170"
      and STATE["pip"] == [("0.2.170", True)], (r, STATE))

# pip itself fails
(_STATE / "sdk-update.json").unlink()
STATE.update(v="0.2.116", pip=[], smoke=[], smoke_fail=(), pip_fail=("0.2.179",))
r = run()
check("a pip failure reinstalls the old version and runs no check", not r["ok"] and STATE["v"] == "0.2.116"
      and STATE["smoke"] == [] and STATE["pip"][-1][0] == "0.2.116", (r, STATE))

# PyPI unreachable
def _boom():
    raise OSError("network down")

STATE.update(pip=[], pip_fail=())
r = su.update("auto", fetch=_boom, pip_install=fake_pip, smoke=fake_smoke, now=NOW)
check("PyPI unreachable: an error, nothing installed", not r["ok"] and "network down" in r.get("error", "")
      and STATE["pip"] == [], r)

# Docker
import deploy_info  # noqa: E402
_real = deploy_info.deploy_mode
deploy_info.deploy_mode = lambda: "docker"
r = run()
deploy_info.deploy_mode = _real
check("the Docker build is left alone", r.get("docker") and not r["ok"] and STATE["pip"] == [], r)

# the switch
check("on by default", su.enabled({}))
check("off with the Claude Code switch", not su.enabled({"model": {"claude_auto_update": False}}))
os.environ["JAVIS_CLAUDE_AUTO_UPDATE"] = "0"
check("off with the env var", not su.enabled({}))
os.environ.pop("JAVIS_CLAUDE_AUTO_UPDATE")

# status
s = su.status()
check("status says what is on disk and what this process loaded",
      {"installed", "loaded", "restart_needed"} <= set(s), s)

# ---- 4. wiring ----
main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("the daily loop calls it under its switch", "sdk_update.enabled() and sdk_update.due()" in main_src)
check("it runs on a worker thread", "asyncio.to_thread(sdk_update.update" in main_src)
check("the Models card gets its status", 'd["sdk"] = sdk_update.status()' in main_src)
js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
vi = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
en = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))
for k in ("models.cc_sdk_ver", "models.cc_sdk_restart", "models.cc_sdk_done", "models.cc_sdk_fail"):
    check(f"{k}: used by the card, present in both dictionaries", k in js and k in vi and k in en)
check("the PyPI address is fixed, https, and takes no caller input",
      su.PYPI_URL == "https://pypi.org/pypi/claude-agent-sdk/json")

if _fails:
    print(f"\nFAIL - {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_sdk_update")
