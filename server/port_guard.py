"""One Javis per port: checked before main.py does any startup work.

2026-11-19 incident: a Javis uvicorn started outside launchd (an old nohup restart of the updater) kept port 7777
for 8 days. launchd's KeepAlive copy failed to bind every ~10 s, 8,000+ times, and each failed copy still ran the
whole startup first (the Zalo read loop, the "previous server stopped without a clean shutdown" recovery) against
state the live copy was using. uvicorn binds the port only AFTER the app is imported and its startup has run, so
nothing stopped that.

`claim_port()` runs at the top of main.py, before anything else is imported:
- port free: nothing to do.
- port held, and this copy is the one launchd manages, and the holder is a Javis server from this same folder: the
  holder is an orphan. Stop it, so launchd's copy takes over.
- port held otherwise: print one line and exit before any startup work.

Only for a real server launch (`uvicorn main:app` or `python main.py`); importing main from tests does nothing.
JAVIS_PORT_GUARD=0 turns it off.
"""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import winproc

SERVER_DIR = Path(__file__).resolve().parent
_DONE_FLAG = "_JAVIS_PORT_GUARD_DONE"


def _arg(argv, name):
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def _is_this_main(path):
    """`python main.py` of THIS server; a test file named test_x_main.py is not."""
    try:
        return Path(path).resolve() == SERVER_DIR / "main.py"
    except (OSError, ValueError):
        return False


def server_launch(argv):
    """(host, port) when argv starts the Javis server, else None."""
    if not argv:
        return None
    if "main:app" not in argv and not _is_this_main(argv[0]):
        return None
    port = _arg(argv, "--port") or os.getenv("JAVIS_PORT") or "7777"
    host = _arg(argv, "--host") or os.getenv("JAVIS_HOST") or "127.0.0.1"
    try:
        return host, int(port)
    except ValueError:
        return None


def port_in_use(host, port, timeout=1.0):
    probe = "127.0.0.1" if host in ("0.0.0.0", "", "::") else host
    try:
        with socket.create_connection((probe, port), timeout=timeout):
            return True
    except OSError:
        return False


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                              creationflags=winproc.no_window()).stdout or ""
    except Exception:
        return ""


def listener_pids(port):
    return [int(x) for x in _run(["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"]).split() if x.isdigit()]


def process_command(pid):
    return _run(["ps", "-o", "command=", "-p", str(pid)]).strip()


def process_cwd(pid):
    for line in _run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]).splitlines():
        if line.startswith("n"):
            return line[1:]
    return ""


def is_javis_server(command, cwd):
    """A uvicorn or `python main.py` running out of this same server folder."""
    if not command or not cwd:
        return False
    if "main:app" not in command and "main.py" not in command:
        return False
    try:
        return Path(cwd).resolve() == SERVER_DIR
    except OSError:
        return False


def managed_by_launchd(environ):
    """launchd sets XPC_SERVICE_NAME to the job label for every process it starts."""
    label = environ.get("JAVIS_LAUNCHD_LABEL", "com.javis.os")
    return environ.get("XPC_SERVICE_NAME") == label


def _stop(pid, timeout=20.0):
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.5)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def decide(holders, managed):
    """'stop' (orphans to stop) or 'exit'. holders: [(pid, command, cwd)] of the processes listening on the port."""
    if managed and holders and all(is_javis_server(cmd, cwd) for _, cmd, cwd in holders):
        return "stop"
    return "exit"


def claim_port(argv=None, environ=None, log=None):
    """Returns 'free', 'took-over' or 'skipped'; exits the process when another server owns the port."""
    argv = sys.argv if argv is None else argv
    environ = os.environ if environ is None else environ
    log = log or (lambda m: print(m, file=sys.stderr, flush=True))
    if os.name == "nt" or environ.get("JAVIS_PORT_GUARD") == "0" or environ.get(_DONE_FLAG):
        return "skipped"
    launch = server_launch(argv)
    if launch is None:
        return "skipped"
    environ[_DONE_FLAG] = "1"   # `python main.py` imports main a second time through uvicorn.run("main:app")
    host, port = launch
    if not port_in_use(host, port):
        return "free"
    me = os.getpid()
    holders = [(p, process_command(p), process_cwd(p)) for p in listener_pids(port) if p != me]
    if decide(holders, managed_by_launchd(environ)) == "stop":
        for pid, cmd, _ in holders:
            log(f"[port-guard] port {port} is held by a Javis server launchd does not manage (PID {pid}: {cmd[:120]}); "
                "stopping it so the launchd copy takes over")
            _stop(pid)
        deadline = time.time() + 10
        while port_in_use(host, port) and time.time() < deadline:
            time.sleep(0.5)
        return "took-over"
    who = ", ".join(f"PID {p}" for p, _, _ in holders) or "another program"
    log(f"[port-guard] port {port} is already served by {who}; this copy exits before any startup work")
    sys.exit(3)
