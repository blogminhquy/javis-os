"""0.267.0: the updater finds its own systemd unit and leaves that unit's cgroup before stopping it.

Two bugs in the old updater on a native Linux install:
- `systemctl stop javis` was hard-coded, so an install named with JAVIS_NAME (install.sh: javis-shop.service) stopped
  the wrong instance, or none, and "javis.service" was looked up as a substring.
- the updater ran inside the service's cgroup (start_new_session does not leave it). With KillMode=mixed, stopping the
  service killed the updater too, halfway through, and Javis stayed down.

    python tests/python/test_updater_systemd.py
"""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-upd-systemd-")
import updater  # noqa: E402
import update_state as us  # noqa: E402

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else f"  {extra}"))
    if not cond:
        fails += 1


CG_V2 = "0::/system.slice/javis-shop.service\n"
CG_V1 = "12:pids:/system.slice/javis.service\n1:name=systemd:/system.slice/javis.service\n"
CG_USER = "0::/user.slice/user-1000.slice/user@1000.service/app.slice/vte-spawn-1.scope\n"
check("unit name: JAVIS_NAME wins", updater.systemd_service_name("javis-shop", CG_V1) == "javis-shop")
check("unit name: a JAVIS_NAME with odd characters is ignored",
      updater.systemd_service_name("bad name;rm", CG_V2) == "javis-shop")
check("unit name: read from the cgroup (v2 and v1)", updater.systemd_service_name("", CG_V2) == "javis-shop"
      and updater.systemd_service_name("", CG_V1) == "javis")
check("unit name: a terminal session falls back to javis", updater.systemd_service_name("", CG_USER) == "javis")


def unit_files(text):
    return lambda *a, **k: SimpleNamespace(returncode=0, stdout=text, stderr="")


with patch.dict(os.environ, {"JAVIS_NAME": "javis"}):
    with patch.object(updater.subprocess, "run", unit_files("javis-shop.service enabled enabled\n")):
        check("has_systemd: javis.service is not found inside javis-shop.service", updater.has_systemd() is False)
    with patch.object(updater.subprocess, "run", unit_files("javis.service enabled enabled\n")):
        check("has_systemd: the exact unit is found", updater.has_systemd() is True)

if hasattr(os, "getuid"):
    a = SimpleNamespace(old_sha="abc123", old_version="0.1.0", target="0.2.0", port="7778", server_pid=42)
    cmd = updater._systemd_worker_command(a, "javis-shop")
    check("worker: started as its own transient unit, outside the service's cgroup",
          cmd[0] == "systemd-run" and any(x.startswith("--unit=javis-update-") for x in cmd))
    check("worker: keeps the unit name, port and state folder, runs as the same user",
          "--setenv=JAVIS_NAME=javis-shop" in cmd and "--setenv=JAVIS_PORT=7778" in cmd
          and f"--setenv=JAVIS_STATE_DIR={us.STATE_DIR}" in cmd and f"--property=User={os.getuid()}" in cmd)
    check("worker: same arguments plus --systemd-worker, so it does not split again",
          cmd[-1] == "--systemd-worker" and cmd[cmd.index("--old-sha") + 1] == "abc123"
          and cmd[cmd.index("--target") + 1] == "0.2.0" and cmd[cmd.index("--server-pid") + 1] == "42")

    ran = []
    with patch.object(updater, "service_mode", lambda *x, **k: "systemd"), \
            patch.object(updater, "stop_server", lambda *x, **k: ran.append("stop")), \
            patch.object(updater.subprocess, "run",
                         lambda c, **k: ran.append(c[0]) or SimpleNamespace(returncode=0, stdout="", stderr="")), \
            patch.object(sys, "argv", ["updater.py", "--old-sha", "abc", "--port", "7777"]):
        rc = updater.main()
    check("systemd: the first updater only hands over to the worker, it never stops the service itself",
          rc == 0 and ran == ["systemd-run"], ran)

    us.write_state({"phase": "preparing", "result": None, "error": None})
    with patch.object(updater, "service_mode", lambda *x, **k: "systemd"), \
            patch.object(updater, "stop_server", lambda *x, **k: ran.append("stop")), \
            patch.object(updater.subprocess, "run",
                         lambda c, **k: SimpleNamespace(returncode=1, stdout="", stderr="Access denied")), \
            patch.object(sys, "argv", ["updater.py", "--old-sha", "abc", "--port", "7777"]):
        rc = updater.main()
    st = us.read_state()
    check("systemd-run refused: Javis is left running and the screen says why",
          rc == 1 and "stop" not in ran and st.get("phase") == "error" and "Access denied" in (st.get("error") or ""), st)

    # ---- 0.269.0: a service running as a normal user (User= in the unit) ----
    # Real case (2026-10-21): every click on Update failed with "Failed to start transient service unit: Interactive
    # authentication required", because a normal user may not create system units. The worker now falls back to the
    # user's own systemd manager and restarts Javis by signal, which needs no privileges.
    def fake_run(answers, seen):
        def _run(c, **k):
            seen.append((c, k.get("env")))
            if c[:2] == ["systemctl", "show"]:
                return SimpleNamespace(returncode=0, stdout=answers.get(c[3], "") + "\n", stderr="")
            if c[:2] == ["systemd-run", "--user"]:
                return answers["user"]
            if c[0] == "systemd-run":
                return SimpleNamespace(returncode=1, stdout="",
                                       stderr="Failed to start transient service unit: Interactive authentication required.")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return _run

    OK = SimpleNamespace(returncode=0, stdout="", stderr="")
    NO_BUS = SimpleNamespace(returncode=1, stdout="", stderr="Failed to connect to bus: No medium found")
    a = SimpleNamespace(old_sha="abc123", old_version="0.1.0", target="0.2.0", port="7777", server_pid=42)

    seen = []
    with patch.object(updater.os, "geteuid", lambda: 1000), \
            patch.object(updater.subprocess, "run", fake_run({"Restart": "always", "user": OK}, seen)):
        ok = updater._launch_systemd_worker(a)
    user_cmd = next((c for c, _ in seen if c[:2] == ["systemd-run", "--user"]), None)
    check("normal user: the system unit is refused, the user's own manager takes the worker", ok and user_cmd, seen)
    check("normal user: the worker restarts Javis by signal and asks for no User=/Group=",
          user_cmd and user_cmd[-2:] == ["--systemd-worker", "--restart-by-signal"]
          and not any(x.startswith("--property=User=") for x in user_cmd))
    check("normal user: the worker gets the user bus even from inside a system service",
          all((env or {}).get("XDG_RUNTIME_DIR") is not None or not Path(f"/run/user/{os.getuid()}").is_dir()
              for c, env in seen if c[:2] == ["systemd-run", "--user"]))

    us.write_state({"phase": "preparing", "result": None, "error": None})
    seen = []
    with patch.object(updater.os, "geteuid", lambda: 1000), \
            patch.object(updater.subprocess, "run", fake_run({"Restart": "always", "user": NO_BUS}, seen)):
        ok = updater._launch_systemd_worker(a)
    err = us.read_state().get("error") or ""
    check("no user manager either: Javis is left running and the screen says how to update and how to fix the button",
          not ok and "Interactive authentication required" in err and "git pull --ff-only" in err
          and "systemctl restart" in err and "enable-linger" in err, err)

    us.write_state({"phase": "preparing", "result": None, "error": None})
    seen = []
    with patch.object(updater.os, "geteuid", lambda: 1000), \
            patch.object(updater.subprocess, "run", fake_run({"Restart": "on-failure", "user": OK}, seen)):
        ok = updater._launch_systemd_worker(a)
    check("only Restart=always is restarted by signal (on-failure treats SIGTERM as clean and stays down)",
          not ok and not any(c[:2] == ["systemd-run", "--user"] for c, _ in seen), seen)

    # The worker in signal mode: the old server keeps running while the release is merged, then one signal swaps it.
    killed, logs = [], []
    with patch.object(updater, "_unit_main_pid", lambda name: 4242), \
            patch.object(updater, "_kill_pid", lambda pid, timeout_s=15: killed.append(pid)), \
            patch.object(updater, "log", logs.append):
        updater.stop_server("systemd-signal", 4242, "7777")
        check("signal mode: stopping does not touch the running server", killed == [])
        updater.start_server("systemd-signal", "7777")
        check("signal mode: starting signals the unit's main process so systemd brings up the new code",
              killed == [4242])

    modes = []
    with patch.object(updater, "service_mode", lambda *x, **k: "systemd"), \
            patch.object(updater, "stop_server", lambda m, *x, **k: modes.append(m) or (_ for _ in ()).throw(SystemExit(7))), \
            patch.object(sys, "argv", ["updater.py", "--old-sha", "abc", "--port", "7777",
                                       "--systemd-worker", "--restart-by-signal"]):
        try:
            updater.main()
        except SystemExit:
            pass
    check("--restart-by-signal puts the worker in signal mode", modes == ["systemd-signal"], modes)

sys.exit(1 if fails else 0)
