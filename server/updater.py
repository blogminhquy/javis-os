#!/usr/bin/env python
"""Updater tách rời của Javis cho bản GIT checkout (Windows + Linux systemd + Mac/nohup).
Server spawn DETACHED:

    python updater.py --old-sha <sha> --old-version <v> --target <v> --port <p> --server-pid <pid>

Chuỗi: stop server -> git pull (stash nếu cây bẩn) -> pip install -> start -> chờ /health ~90s.
/health không lên → git reset --hard <old-sha> -> pip -> start (rollback tự động).
3 chế độ restart (service_mode): windows (bat/vbs), systemd (systemctl), nohup (Mac hoặc
Linux không systemd: kill PID server cũ rồi tự chạy lại uvicorn nền như install.sh).
Chỉ dùng stdlib (chạy được cả khi bản mới hỏng dependency)."""
import argparse
import datetime
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
import update_state as us  # noqa: E402


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(us.STATE_DIR / "update.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run(cmd):
    log("$ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        log(f"  (rc={r.returncode}) " + (r.stderr or r.stdout or "").strip()[:500])
    return r


def venv_python():
    p = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(p) if p.exists() else sys.executable


def has_systemd():
    try:
        r = subprocess.run(["systemctl", "list-unit-files"], capture_output=True, text=True)
        return r.returncode == 0 and "javis.service" in (r.stdout or "")
    except Exception:
        return False


def service_mode(osname=None, systemd=None):
    """windows | systemd | nohup - cách stop/start server theo nền tảng. Mac không có
    systemctl (và Linux cài không systemd) chạy kiểu nohup: kill PID + tự chạy lại uvicorn."""
    osname = osname or os.name
    if osname == "nt":
        return "windows"
    if systemd is None:
        systemd = has_systemd()
    return "systemd" if systemd else "nohup"


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill_pid(pid, timeout_s=15):
    import signal
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(0.5)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _pids_on_port(port):
    """PID đang giữ cổng (lsof có sẵn trên Mac lẫn đa số Linux). Fallback khi thiếu --server-pid."""
    try:
        r = subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True)
        return [int(x) for x in (r.stdout or "").split() if x.strip().isdigit()]
    except Exception:
        return []


def stop_server(mode, server_pid=0, port=""):
    if mode == "windows":
        run(["cmd", "/c", str(ROOT / "stop-javis.bat")])
    elif mode == "systemd":
        subprocess.run(["systemctl", "stop", "javis"], capture_output=True, text=True)
    else:  # nohup: kill đúng PID server (mình là session riêng nên không chết theo)
        pids = [server_pid] if server_pid else []
        pids += [p for p in _pids_on_port(port) if p not in pids and p != os.getpid()]
        if not pids:
            log("Không tìm thấy tiến trình server để dừng (có thể đã tắt).")
        for p in pids:
            log(f"Dừng PID {p}…")
            _kill_pid(p)


def start_server(mode, port=""):
    if mode == "windows":
        subprocess.Popen(["wscript.exe", "//nologo", str(ROOT / "start-javis.vbs")],
                         cwd=str(ROOT), creationflags=0x00000008)  # DETACHED_PROCESS
    elif mode == "systemd":
        subprocess.run(["systemctl", "start", "javis"], capture_output=True, text=True)
    else:  # nohup: chạy lại uvicorn nền y như install.sh (fallback không systemd)
        host = os.getenv("JAVIS_HOST", "127.0.0.1")
        logf = open(us.STATE_DIR / "javis.log", "a", encoding="utf-8")
        subprocess.Popen(
            [venv_python(), "-m", "uvicorn", "main:app", "--host", host, "--port", str(port or "7777")],
            cwd=str(ROOT / "server"), stdout=logf, stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "JAVIS_STATE_DIR": os.getenv("JAVIS_STATE_DIR", str(us.STATE_DIR))})


def git_dirty():
    r = run(["git", "status", "--porcelain", "--untracked-files=no"])
    return bool((r.stdout or "").strip())


def chan_doan_pull(pull_out: str) -> str:
    """Vì sao `git pull` trả về THÀNH CÔNG mà VERSION vẫn y nguyên.

    Trước đây chỗ này chỉ nói "(pull chưa áp?)" rồi bảo người dùng đi đọc update.log - tức
    là biết có chuyện bất thường mà không nói ra chuyện gì. Người dùng ở xa file log (bản
    Windows/Docker) thì coi như không có manh mối nào.

    Nguyên nhân hay gặp nhất: máy đang theo dõi một nhánh KHÁC nhánh có bản mới, nên git
    báo "Already up to date" và trả về 0 một cách hoàn toàn hợp lệ."""
    out = (pull_out or "").strip()
    nhanh = (run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout or "").strip()
    up = run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    theo_doi = (up.stdout or "").strip() if up.returncode == 0 else ""

    if "up to date" in out.lower() or "up-to-date" in out.lower():
        if not theo_doi:
            return (f"Nhánh '{nhanh}' không theo dõi nhánh nào trên máy chủ nên git không có "
                    f"gì để tải về. Chạy: git branch --set-upstream-to=origin/main {nhanh}")
        if not theo_doi.endswith("/main"):
            return (f"Máy đang ở nhánh '{nhanh}' theo dõi '{theo_doi}', mà bản mới nằm ở "
                    f"nhánh main. Chạy: git checkout main && git pull")
        return (f"Git báo đã mới nhất trên '{theo_doi}' nhưng phiên bản không đổi. Nhiều khả "
                f"năng bản cài này không phải bản chạy từ mã nguồn (Docker/đóng gói sẵn) - "
                f"hãy cập nhật bằng cách deploy lại image.")
    if "detached" in out.lower() or nhanh == "HEAD":
        return ("Máy đang ở trạng thái detached HEAD (không đứng trên nhánh nào). "
                "Chạy: git checkout main && git pull")
    return (f"Đã tải mã mới nhưng phiên bản không đổi. Nhánh '{nhanh}'"
            + (f", theo dõi '{theo_doi}'" if theo_doi else ", chưa theo dõi nhánh nào")
            + ". Xem update.log để biết chi tiết.")


def pip_install():
    return run([venv_python(), "-m", "pip", "install", "-r", "requirements.txt", "-q"])


def read_current_version():
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "0.0.0"


def poll_health(port, timeout_s=90):
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=4) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-sha", default="")
    ap.add_argument("--old-version", default="")
    ap.add_argument("--target", default="")
    ap.add_argument("--port", default=os.getenv("JAVIS_PORT", "7777"))
    ap.add_argument("--server-pid", type=int, default=0,
                    help="PID server đang chạy (để chế độ nohup kill đúng tiến trình)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.dry_run:
        print(f"PLAN: stop -> pull(stash nếu bẩn) -> pip -> start -> health({a.port}) "
              f"-> rollback(reset {a.old_sha or '?'}) nếu không lên")
        return 0

    target = a.target or None
    us.write_state({"phase": "preparing", "started_at": _now(), "finished_at": None,
                    "result": None, "error": None, "old_sha": a.old_sha,
                    "old_version": a.old_version, "target_version": target, "stashed": False})

    mode = service_mode()
    log(f"Chế độ restart: {mode}")

    log("Dừng server cũ…")
    stop_server(mode, a.server_pid, a.port)
    time.sleep(2)

    us.write_state({"phase": "pulling"})
    if git_dirty():
        log("Cây git có sửa đổi cục bộ → git stash (giữ lại, không mất).")
        run(["git", "stash"])
        us.write_state({"stashed": True})
    pull = run(["git", "pull", "--ff-only"])
    if pull.returncode != 0:
        log("git pull LỖI:\n" + (pull.stderr or pull.stdout or ""))
        start_server(mode, a.port)
        us.write_state({"phase": "error", "result": "pull_failed",
                        "error": (pull.stderr or "git pull thất bại")[:500], "finished_at": _now()})
        return 1

    us.write_state({"phase": "installing"})
    log("Cài thư viện…")
    pip_install()

    us.write_state({"phase": "restarting"})
    log("Khởi động bản mới…")
    start_server(mode, a.port)

    us.write_state({"phase": "health_check"})
    log("Kiểm tra sức khoẻ…")
    healthy = poll_health(a.port, 90)
    current = read_current_version()
    outcome = us.update_outcome(healthy, current, a.old_version, target)
    log(f"health={healthy} current={current} → {outcome}")

    if outcome == "success":
        us.record_boot_version(current)
        us.write_state({"phase": "done", "result": "success", "finished_at": _now()})
        return 0
    if outcome == "version_mismatch":
        ly_do = chan_doan_pull(pull.stdout or "")
        log("Phiên bản không đổi. Chẩn đoán: " + ly_do)
        us.write_state({"phase": "done", "result": "error",
                        "error": f"Vẫn đang chạy {current}, chưa lên {target}. {ly_do}",
                        "finished_at": _now()})
        return 1

    # need_rollback
    log("Bản mới KHÔNG lên được → tự lùi về bản cũ…")
    us.write_state({"phase": "rolling_back"})
    if not a.old_sha:
        us.write_state({"phase": "error", "result": "rollback_failed",
                        "error": "Không có commit cũ để lùi.", "finished_at": _now()})
        return 1
    run(["git", "reset", "--hard", a.old_sha])
    pip_install()
    # Bản mới có thể đang chạy dở (lên tiến trình nhưng /health đỏ) → dừng hẳn trước khi
    # bật bản cũ, kẻo nohup bind trùng cổng. Windows/systemd dừng lại cũng vô hại.
    stop_server(mode, 0, a.port)
    time.sleep(2)
    start_server(mode, a.port)
    if poll_health(a.port, 90):
        us.write_state({"phase": "done", "result": "rolled_back",
                        "error": "Bản mới lỗi, đã tự quay về bản cũ.", "finished_at": _now()})
        return 0
    us.write_state({"phase": "error", "result": "rollback_failed",
                    "error": "Bản mới lỗi và lùi bản cũng chưa lên. Xem update.log.", "finished_at": _now()})
    return 1


if __name__ == "__main__":
    sys.exit(main())
