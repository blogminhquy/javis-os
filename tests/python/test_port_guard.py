"""One Javis per port, and the updater never starts a copy launchd does not know about (2026-11-19).

The incident: a uvicorn the updater started with nohup held port 7777 for 8 days while launchd's KeepAlive copy
failed to bind every 10 s, each failed copy running the whole startup first.

    python tests/python/test_port_guard.py
"""
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
import _paths  # noqa: E402,F401

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-port-guard-")
import port_guard as pg  # noqa: E402
import updater  # noqa: E402

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else f"  {extra}"))
    if not cond:
        fails += 1


SRV = str(pg.SERVER_DIR)

# --- which launches count ---
check("uvicorn launch is a server launch",
      pg.server_launch(["/x/uvicorn/__main__.py", "main:app", "--host", "127.0.0.1", "--port", "7788"])
      == ("127.0.0.1", 7788))
check("--port=N form", pg.server_launch(["uvicorn", "main:app", "--port=7790"])[1] == 7790)
check("python main.py is a server launch", pg.server_launch([str(pg.SERVER_DIR / "main.py")]) is not None)
check("a test named *_main.py is not (it imports main)",
      pg.server_launch(["tests/python/test_tien_trinh_nen_main.py"]) is None)
check("pytest importing main is not", pg.server_launch(["/x/pytest", "tests/python"]) is None)
check("a test script is not", pg.server_launch(["tests/python/test_x.py"]) is None)

# --- who is an orphan ---
check("uvicorn from this folder is a Javis server",
      pg.is_javis_server("/v/bin/python -m uvicorn main:app --port 7777", SRV))
check("uvicorn from another checkout is not", not pg.is_javis_server("python -m uvicorn main:app", "/elsewhere"))
check("another program is not", not pg.is_javis_server("cloudflared tunnel run", SRV))
check("launchd copy is recognised", pg.managed_by_launchd({"XPC_SERVICE_NAME": "com.javis.os"}))
check("custom label", pg.managed_by_launchd({"XPC_SERVICE_NAME": "x.j", "JAVIS_LAUNCHD_LABEL": "x.j"}))
check("terminal copy is not managed", not pg.managed_by_launchd({}))

orphan = [(68134, "/v/bin/python -m uvicorn main:app --port 7777", SRV)]
check("managed copy stops an orphan Javis", pg.decide(orphan, True) == "stop")
check("unmanaged copy never stops anything", pg.decide(orphan, False) == "exit")
check("managed copy leaves a foreign program alone",
      pg.decide(orphan + [(9, "node other.js", "/tmp")], True) == "exit")
check("holder unknown (lsof found nothing) -> exit", pg.decide([], True) == "exit")

# --- claim_port end to end on a real socket ---
sock = socket.socket()
sock.bind(("127.0.0.1", 0))
sock.listen(64)   # the probes connect without accept; a backlog of 1 can fill and read as "free"
busy = sock.getsockname()[1]
argv = ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(busy)]
lines = []
try:
    pg.claim_port(argv, {}, lines.append)
    check("busy port, not managed: exits", False)
except SystemExit as e:
    check("busy port, not managed: exits before startup", e.code == 3)
check("one clear log line", len(lines) == 1 and "[port-guard]" in lines[0], lines)

with patch.object(pg, "listener_pids", return_value=[68134]), \
        patch.object(pg, "process_command", return_value="python -m uvicorn main:app"), \
        patch.object(pg, "process_cwd", return_value=SRV), \
        patch.object(pg, "_stop", side_effect=lambda pid: sock.close()) as stop:
    r = pg.claim_port(argv, {"XPC_SERVICE_NAME": "com.javis.os"}, lines.append)
check("managed copy takes the port over from an orphan", r == "took-over" and stop.call_args[0][0] == 68134, r)

free = socket.socket()
free.bind(("127.0.0.1", 0))
fport = free.getsockname()[1]
free.close()
check("free port: nothing to do", pg.claim_port(["uvicorn", "main:app", "--port", str(fport)], {}) == "free")
env = {}
pg.claim_port(["uvicorn", "main:app", "--port", str(fport)], env)
check("second import in the same process is skipped",
      pg.claim_port(["uvicorn", "main:app", "--port", str(busy)], env) == "skipped")
check("JAVIS_PORT_GUARD=0 turns it off", pg.claim_port(argv, {"JAVIS_PORT_GUARD": "0"}) == "skipped")
check("main.py calls the guard before its first other import",
      (ROOT / "server" / "main.py").read_text(encoding="utf-8").split("import brain_seed_i18n")[0]
      .rstrip().endswith("port_guard.claim_port()"))

# --- updater: our plist on disk means launchd mode ---
home = Path(tempfile.mkdtemp(prefix="javis-home-"))
agents = home / "Library" / "LaunchAgents"
agents.mkdir(parents=True)
plist = agents / f"{updater.LAUNCHD_LABEL}.plist"
check("no plist -> none", updater.launchd_plist_path(home) is None)
plist.write_text(f"<string>/other/checkout/server</string>", encoding="utf-8")
check("plist of another checkout -> none", updater.launchd_plist_path(home) is None)
plist.write_text(f"<key>WorkingDirectory</key><string>{updater.ROOT / 'server'}</string>", encoding="utf-8")
check("our plist is found", updater.launchd_plist_path(home) == plist)

failed_print = subprocess.CompletedProcess([], 113, "", "Could not find service")
with patch.object(updater.sys, "platform", "darwin"), \
        patch.object(updater.subprocess, "run", return_value=failed_print), \
        patch.object(updater, "launchd_plist_path", return_value=plist):
    check("launchctl print fails but our plist exists -> launchd, not nohup", updater.has_launchd_job())
    check("service_mode picks launchd", updater.service_mode("posix", systemd=False) == "launchd")

calls = []


def fake_run(cmd):
    calls.append(cmd)
    return subprocess.CompletedProcess(cmd, 0 if cmd[1] == "bootstrap" or len(calls) > 2 else 5, "", "")


with patch.object(updater, "run", side_effect=fake_run), \
        patch.object(updater, "launchd_plist_path", return_value=plist), \
        patch.object(updater.subprocess, "Popen") as popen, \
        patch.object(updater, "_kill_pid") as kill:
    updater.start_server("launchd", "7777")
check("kickstart failed -> bootstrap our plist, kickstart again",
      [c[1] for c in calls] == ["kickstart", "bootstrap", "kickstart"], calls)
check("launchd mode never starts its own uvicorn", not popen.called and not kill.called)

with patch.object(updater, "run", return_value=subprocess.CompletedProcess([], 5, "", "")), \
        patch.object(updater, "launchd_plist_path", return_value=plist), \
        patch.object(updater, "_pids_on_port", return_value=[4242]), \
        patch.object(updater.subprocess, "Popen") as popen, \
        patch.object(updater, "_kill_pid") as kill:
    updater.start_server("launchd", "7777")
check("launchctl unusable -> stop the copy, let KeepAlive restart it",
      kill.call_args[0][0] == 4242 and not popen.called)

# Nothing comes back after the copy is stopped (plist left over, agent switched off): start Javis directly rather
# than leave it down until someone opens it by hand.
_ports = iter([[4242], [], []])
with patch.object(updater, "run", return_value=subprocess.CompletedProcess([], 5, "", "")), \
        patch.object(updater, "launchd_plist_path", return_value=plist), \
        patch.object(updater, "_pids_on_port", side_effect=lambda _p: next(_ports, [])), \
        patch.object(updater, "LAUNCHD_RESPAWN_WAIT_S", 0), \
        patch.object(updater, "_start_nohup") as nohup, \
        patch.object(updater, "_kill_pid") as kill:
    updater.start_server("launchd", "7777")
check("launchd never brings it back -> start Javis directly as a last resort",
      kill.call_args[0][0] == 4242 and nohup.called)

with patch.object(updater.subprocess, "run",
                  return_value=subprocess.CompletedProcess([], 0, "123\n", "")) as r:
    updater._pids_on_port("7777")
check("port lookup asks only for the listener (not cloudflared or the browser)",
      "-sTCP:LISTEN" in r.call_args[0][0], r.call_args)

print("\nFAIL" if fails else "\nALL OK")
sys.exit(1 if fails else 0)
