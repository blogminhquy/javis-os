"""A rolled-back update says WHY the new version did not start.

    python tests/run.py update_startup_error

No pytest, no network, no real git, pip or server: every command is a fake, as in test_update_lui_hong.

Reported 27/11/2026: 0.646.0 died at startup on Python 3.15 (TypeError in accept_guard). The updater rolled back, the
old version's start rotated (Windows) or appended to (nohup, launchd) the same javis.log, and the screen said only
"the new version failed". The user had to run the new version by hand in another folder to see the error. Now the
updater reads the failed start's output before rolling back, keeps its last lines in update.log and puts the error
line on the screen.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-startup-error-")

import update_state as us   # noqa: E402
import updater              # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


PY315 = """INFO:     Started server process [4242]
Traceback (most recent call last):
  File "C:\\\\Javis\\\\server\\\\main.py", line 30101, in <module>
    uvicorn.run(app, host=host, port=port)
  File "C:\\\\Python315\\\\Lib\\\\asyncio\\\\base_events.py", line 321, in _start_serving
    self._loop._start_serving(
    ~~~~~~~~~~~~~~~~~~~~~~~~~^
TypeError: _start_serving() got an unexpected keyword argument 'context'
"""
OLD_LOG = "".join(f"INFO:     old line {i}\n" for i in range(200)) + (
    "Traceback (most recent call last):\n  File \"x.py\", line 1\nValueError: an old error from last week\n")


class FakeResult:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def update_that_fails(log_file, on_start, *, mode="nohup", journal=""):
    """Replay an update whose new version never answers /health and whose old version comes back.

    `on_start(n)` is called at each server start (1 = the new version, 2 = the old one after the rollback) and does to
    `log_file` what that platform's start does."""
    saved = (updater.run, updater.poll_health, updater.start_server, updater.stop_server, updater.service_mode,
             updater.read_current_version, updater.git_dirty, updater.pip_install, updater._server_log_files,
             updater._read_journal, sys.argv)
    starts, health = {"n": 0}, {"n": 0}

    def fake_run(cmd):
        if cmd[:2] == ["git", "rev-parse"] and cmd[-1] == "HEAD":
            return FakeResult(0, "old1234567890")
        return FakeResult(0, "")

    def fake_start(*_a, **_k):
        starts["n"] += 1
        on_start(starts["n"])

    def fake_health(*_a, **_k):
        health["n"] += 1
        return health["n"] > 1       # the new version never answers, the old one does

    (us.STATE_DIR / "update.log").write_text("", encoding="utf-8")
    try:
        updater.run = fake_run
        updater.poll_health = fake_health
        updater.start_server = fake_start
        updater.stop_server = lambda *a, **k: None
        updater.service_mode = lambda *a, **k: mode
        updater.read_current_version = lambda: "9.9.9"
        updater.git_dirty = lambda: False
        updater.pip_install = lambda: FakeResult(0)
        updater._server_log_files = lambda: [log_file]
        updater._read_journal = lambda since: journal
        sys.argv = ["updater.py", "--old-sha", "old1234567890abcdef", "--old-version", "0.645.4",
                    "--target", "9.9.9", "--port", "7777", "--systemd-worker"]
        code = updater.main()
    finally:
        (updater.run, updater.poll_health, updater.start_server, updater.stop_server, updater.service_mode,
         updater.read_current_version, updater.git_dirty, updater.pip_install, updater._server_log_files,
         updater._read_journal, sys.argv) = saved
    return code, us.read_state(), (us.STATE_DIR / "update.log").read_text(encoding="utf-8")


def fresh_log(text):
    d = Path(tempfile.mkdtemp(prefix="javis-log-"))
    f = d / "javis.log"
    f.write_text(text, encoding="utf-8")
    return f


# ---- 1. Windows: start-javis.vbs moves javis.log aside and starts a new one at every start ----
log1 = fresh_log(OLD_LOG)


def windows_start(n):
    rotated = log1.with_name(f"javis-{n}.log")
    log1.replace(rotated)
    log1.write_text(PY315 if n == 1 else "INFO:     Uvicorn running on http://127.0.0.1:7777\n", encoding="utf-8")


code, st, ulog = update_that_fails(log1, windows_start, mode="windows")
cause = "TypeError: _start_serving() got an unexpected keyword argument 'context'"
check("the rollback still succeeds", code == 0 and st.get("result") == "rolled_back", (code, st.get("result")))
check("the error line of the failed start is kept", st.get("cause") == cause, st.get("cause"))
check("and shown in the result", cause in (st.get("error") or ""), st.get("error"))
check("update.log keeps the failed start's traceback", "Traceback (most recent call last)" in ulog and cause in ulog)
check("not last week's error from the rotated log", "an old error from last week" not in ulog)

# ---- 2. nohup / launchd: both starts append to the same javis.log ----
log2 = fresh_log(OLD_LOG)


def append_start(n):
    with open(log2, "a", encoding="utf-8") as f:
        f.write(PY315 if n == 1 else "INFO:     Uvicorn running on http://127.0.0.1:7777\n")


code, st, ulog = update_that_fails(log2, append_start)
check("an appended log yields the new start's error, not an older one", st.get("cause") == cause, st.get("cause"))

# ---- 3. No traceback: uvicorn's own error line ----
log3 = fresh_log("")


def port_taken(n):
    if n == 1:
        with open(log3, "a", encoding="utf-8") as f:
            f.write("INFO:     Started server process [7]\nERROR:    [Errno 98] error while attempting to bind on address "
                    "('127.0.0.1', 7777): address already in use\nINFO:     Waiting for application shutdown.\n")


code, st, ulog = update_that_fails(log3, port_taken)
check("without a traceback the last error line is used", "[Errno 98]" in (st.get("cause") or ""), st.get("cause"))

# ---- 4. systemd: the server logs to the journal ----
log4 = fresh_log("")
code, st, ulog = update_that_fails(log4, lambda n: None, mode="systemd", journal=PY315)
check("a systemd service's error comes from the journal", st.get("cause") == cause, st.get("cause"))

# ---- 5. Nothing written: the old message, no invented cause ----
log5 = fresh_log(OLD_LOG)
code, st, ulog = update_that_fails(log5, lambda n: None)
check("nothing new in the log means no cause", not st.get("cause"), st.get("cause"))
check("and the plain rolled-back message", (st.get("error") or "") in (
    "Bản mới lỗi, đã tự quay về bản cũ.", "The new version failed, so Javis rolled back to the old one."), st.get("error"))
check("update.log says the new version wrote nothing", "wrote nothing" in ulog or "không ghi gì" in ulog)

# ---- 6. The error line picker on its own ----
check("ANSI colours are stripped", updater.startup_error("\x1b[31mERROR\x1b[0m:    Traceback (most recent call last):\n"
                                                         "  File \"a\", line 1\nKeyError: 'x'\n") == "KeyError: 'x'")
check("a chained traceback reports the last exception",
      updater.startup_error("Traceback (most recent call last):\n  x\nOSError: first\n\nDuring handling of the above "
                            "exception, another exception occurred:\n\nTraceback (most recent call last):\n  y\n"
                            "RuntimeError: second\n") == "RuntimeError: second")
check("plain INFO lines are not an error", updater.startup_error("INFO:     Started\nINFO:     Waiting\n") == "")

# ---- 7. The update screen shows it ----
js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("both update screens append the cause to the rolled-back line",
      js.count("_updCause(state.state)") == 1 and js.count("_updCause(s.state)") == 1)
for lang in ("vi", "en"):
    d = (ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8")
    check(f"{lang}.json has cs.upd_rb_cause", '"cs.upd_rb_cause"' in d)

print()
print(f"RED {len(_fails)}: " + "; ".join(_fails) if _fails else "GREEN: all passed")
sys.exit(1 if _fails else 0)
