#!/usr/bin/env python
"""Updater tách rời của Javis cho bản GIT checkout (Windows + systemd + launchd + nohup).
Server spawn DETACHED:

    python updater.py --old-sha <sha> --old-version <v> --target <v> --port <p> --server-pid <pid>

Chuỗi: stop server -> fetch/merge bản phát hành (stash nếu cây bẩn) -> pip -> start -> health.
/health không lên → git reset --hard <old-sha> -> pip -> start (rollback tự động).
4 chế độ restart (service_mode): windows (bat/vbs), systemd (systemctl), launchd (Mac có
job KeepAlive: KHÔNG kill PID mà `launchctl kickstart -k` - xem has_launchd_job), nohup
(Mac không launchd hoặc Linux không systemd: kill PID rồi tự chạy lại uvicorn nền).
Chỉ dùng stdlib (chạy được cả khi bản mới hỏng dependency)."""
import argparse
import datetime
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
import update_state as us  # noqa: E402
import winproc  # noqa: E402

# Updater được server spawn DETACHED, tức nó chạy KHÔNG CÓ console. Trên Windows, một tiến trình
# không console mà gọi chương trình console (git, pip, systemctl...) thì hệ điều hành tự cấp cho
# đứa con một cửa sổ mới - người dùng thấy màn hình nháy đen liên tục suốt lượt cập nhật. Nên
# mọi lời gọi dưới đây đều truyền cờ này. Hai chỗ CỐ Ý không truyền là lúc khởi động lại Javis,
# vì tiến trình đó phải sống lâu hơn updater.
_CAM = winproc.no_window()


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
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       creationflags=_CAM)
    if r.returncode != 0:
        log(f"  (rc={r.returncode}) " + (r.stderr or r.stdout or "").strip()[:500])
    return r


def venv_python():
    p = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(p) if p.exists() else sys.executable


def has_systemd():
    try:
        r = subprocess.run(["systemctl", "list-unit-files"], capture_output=True, text=True,
                           creationflags=_CAM)
        return r.returncode == 0 and "javis.service" in (r.stdout or "")
    except Exception:
        return False


LAUNCHD_LABEL = os.getenv("JAVIS_LAUNCHD_LABEL", "com.javis.os")


def _launchd_target():
    return f"gui/{os.getuid()}/{LAUNCHD_LABEL}"


def has_launchd_job():
    """Mac chạy Javis dưới launchd (job KeepAlive) thì restart PHẢI qua launchd.

    Bài học 14/08/2026: updater kill PID server -> launchd KeepAlive respawn ngay tức thì,
    trong khi updater cũng Popen một bản uvicorn của riêng nó -> hai tiến trình giành cổng
    7777, javis.log đầy "[Errno 48] address already in use". Nhãn job đổi được qua env
    JAVIS_LAUNCHD_LABEL (mặc định com.javis.os)."""
    if sys.platform != "darwin":
        return False
    try:
        r = subprocess.run(["launchctl", "print", _launchd_target()],
                           capture_output=True, text=True, creationflags=_CAM)
        return r.returncode == 0
    except Exception:
        return False


def service_mode(osname=None, systemd=None, launchd=None):
    """windows | systemd | launchd | nohup - cách stop/start server theo nền tảng. Mac không
    có launchd job (và Linux không systemd) chạy kiểu nohup: kill PID + tự chạy lại uvicorn."""
    osname = osname or os.name
    if osname == "nt":
        return "windows"
    if launchd is None:
        launchd = has_launchd_job()
    if launchd:
        return "launchd"
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
        r = subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True,
                           creationflags=_CAM)
        return [int(x) for x in (r.stdout or "").split() if x.strip().isdigit()]
    except Exception:
        return []


def stop_server(mode, server_pid=0, port=""):
    if mode == "windows":
        run(["cmd", "/c", str(ROOT / "stop-javis.bat")])
    elif mode == "systemd":
        subprocess.run(["systemctl", "stop", "javis"], capture_output=True, text=True,
                       creationflags=_CAM)
    elif mode == "launchd":
        # CỐ Ý không dừng gì: kill lúc này thì KeepAlive respawn ngay và bản respawn đó sẽ
        # giành cổng với bản mình bật sau. Server cũ cứ phục vụ tiếp trong lúc pull + pip
        # (git không đụng tiến trình đang chạy); cú đổi ca duy nhất là kickstart -k ở bước start.
        log(f"launchd đang giữ job {_launchd_target()} → bỏ qua bước dừng, "
            "đổi ca bằng launchctl kickstart -k ở bước khởi động.")
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
        subprocess.run(["systemctl", "start", "javis"], capture_output=True, text=True,
                       creationflags=_CAM)
    elif mode == "launchd":
        # kickstart -k: launchd tự hạ bản đang chạy rồi bật bản mới - MỘT người điều phối,
        # không còn cửa cho hai tiến trình cùng bind cổng.
        run(["launchctl", "kickstart", "-k", _launchd_target()])
    else:  # nohup: chạy lại uvicorn nền y như install.sh (fallback không systemd)
        host = os.getenv("JAVIS_HOST", "127.0.0.1")
        logf = open(us.STATE_DIR / "javis.log", "a", encoding="utf-8")
        subprocess.Popen(   # noqa: JAVIS_CONSOLE - server mới phải sống lâu hơn updater
            [venv_python(), "-m", "uvicorn", "main:app", "--host", host, "--port", str(port or "7777")],
            cwd=str(ROOT / "server"), stdout=logf, stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "JAVIS_STATE_DIR": os.getenv("JAVIS_STATE_DIR", str(us.STATE_DIR))})


def git_dirty():
    r = run(["git", "status", "--porcelain", "--untracked-files=no"])
    return bool((r.stdout or "").strip())


def _stash_head():
    r = run(["git", "rev-parse", "--verify", "-q", "refs/stash"])
    return (r.stdout or "").strip() if r.returncode == 0 else ""


def stash_local_changes():
    """Return (stash commit, error), retaining a recoverable backup on failure."""
    status = run(["git", "status", "--porcelain", "--untracked-files=no"])
    if status.returncode != 0:
        return "", "Không kiểm tra được các sửa đổi cục bộ; dừng cập nhật để tránh mất dữ liệu."
    if not (status.stdout or "").strip():
        return "", ""
    previous = _stash_head()
    saved = run(["git", "stash", "push", "-m", "javis-auto-update"])
    current = _stash_head()
    if saved.returncode != 0 or not current or current == previous:
        return "", ("Không cất được sửa đổi cục bộ; dừng cập nhật. Kiểm tra git stash list "
                    "và update.log trước khi thử lại.")
    return current, ""


def restore_local_changes(stash_oid):
    """Apply our exact backup. On conflict, clean the index but keep the backup."""
    restored = run(["git", "stash", "apply", "--index", stash_oid])
    if restored.returncode == 0:
        return True, ""
    cleaned = run(["git", "reset", "--hard", "HEAD"])
    detail = (restored.stderr or restored.stdout or "Xung đột khi khôi phục.").strip()[:500]
    if cleaned.returncode != 0:
        detail += " Không dọn được xung đột; cần kiểm tra cây git bằng tay."
    return False, detail


def drop_update_stash(stash_oid, restored):
    """Delete only a successfully applied backup, if it is still the top stash."""
    if not restored or _stash_head() != stash_oid:
        return False
    return run(["git", "stash", "drop", "stash@{0}"]).returncode == 0


def release_source():
    """The same official release branch that /version checks in main.py."""
    return "https://github.com/blogminhquy/javis-os.git", "main"


def _clean_tracked_tree():
    status = run(["git", "status", "--porcelain", "--untracked-files=no"])
    return status.returncode == 0 and not (status.stdout or "").strip()


def merge_release():
    """Fetch and merge the release while preserving local commits.

    Return (git result, safe worktree). A failed merge is aborted before the caller
    reapplies its stash. If abort fails, leave the backup untouched for manual recovery.
    """
    remote, branch = release_source()
    before = _head_hien_tai()
    if not before or remote.startswith("-") or branch.startswith("-"):
        error = "Không xác định được HEAD hoặc nguồn phát hành hợp lệ."
        return subprocess.CompletedProcess(["git", "fetch"], 1, "", error), True
    current_branch = run(["git", "symbolic-ref", "-q", "--short", "HEAD"])
    if current_branch.returncode != 0:
        error = "detached HEAD: hãy chọn một nhánh trước khi cập nhật."
        return subprocess.CompletedProcess(["git", "merge"], 1, "", error), True
    if not _clean_tracked_tree():
        error = "Cây git chưa sạch sau khi cất sửa đổi; dừng cập nhật để giữ dữ liệu."
        return subprocess.CompletedProcess(["git", "merge"], 1, "", error), False
    fetched = run(["git", "fetch", remote, branch])
    if fetched.returncode != 0:
        return fetched, True
    merged = run(["git", "merge", "--no-edit", "FETCH_HEAD"])
    if merged.returncode == 0:
        if _clean_tracked_tree():
            return merged, True
        error = "Đã hợp nhất nhưng cây git còn sửa đổi ngoài dự kiến; dừng cập nhật."
        return subprocess.CompletedProcess(merged.args, 1, merged.stdout, error), False
    in_merge = run(["git", "rev-parse", "--verify", "-q", "MERGE_HEAD"]).returncode == 0
    if in_merge:
        aborted = run(["git", "merge", "--abort"])
        return merged, (aborted.returncode == 0 and _head_hien_tai() == before
                        and _clean_tracked_tree())
    return merged, _head_hien_tai() == before and _clean_tracked_tree()


def chan_doan_pull(pull_out: str) -> str:
    """Explain a healthy server whose VERSION did not advance after release merge."""
    out = (pull_out or "").strip()
    remote, branch = release_source()
    if "up to date" in out.lower() or "up-to-date" in out.lower():
        return (f"Nguồn phát hành {remote}/{branch} chưa có phiên bản mới hơn. Nếu chạy bằng "
                "Docker hoặc bản đóng gói, hãy cập nhật image thay vì nút này.")
    return (f"Đã hợp nhất {remote}/{branch} nhưng VERSION không tăng như dự kiến. "
            "Kiểm tra phiên bản trên nhánh phát hành và update.log.")


def chan_doan_pull_hong(loi: str, nhanh: str = "", theo_doi: str = "",
                        merge_aborted: bool = True) -> str:
    """Translate fetch/merge failures without advising users to discard commits."""
    out = (loi or "").strip()
    thap = out.lower()
    remote, branch = release_source()

    if "conflict" in thap or "automatic merge failed" in thap:
        files = list(dict.fromkeys(re.findall(r"Merge conflict in (\S+)", out, re.IGNORECASE)))
        names = (": " + ", ".join(files[:5])
                 + (f" và {len(files) - 5} file khác" if len(files) > 5 else "")) if files else ""
        if not merge_aborted:
            return ("Bản phát hành xung đột với code sửa riêng" + names
                    + ". Chưa hủy được lần hợp nhất; kiểm tra git status và giữ nguyên "
                      "git stash trước khi sửa bằng tay.")
        return ("Bản phát hành xung đột với code sửa riêng" + names
                + f". Updater đã hủy lần hợp nhất; commit riêng giữ nguyên. Cần gộp tay: "
                  f"git fetch {remote} {branch} && git merge FETCH_HEAD, sửa xung đột rồi commit.")
    if "not possible to fast-forward" in thap or "diverging" in thap or "diverged" in thap:
        return ("Lịch sử nhánh phát hành và nhánh hiện tại khác nhau, Git chưa hợp nhất được. "
                "Các commit riêng vẫn ở nhánh hiện tại; xem update.log để xử lý bằng tay.")
    if "you are not currently on a branch" in thap or nhanh == "HEAD":
        return "Máy đang ở trạng thái detached HEAD; hãy chọn một nhánh trước khi cập nhật."
    if "authentication" in thap or "permission denied" in thap or "403" in thap:
        return "GitHub từ chối quyền truy cập. Kiểm tra lại thông tin đăng nhập git của máy."
    if ("could not resolve host" in thap or "unable to access" in thap
            or "connection" in thap or "timed out" in thap):
        return "Không nối được tới GitHub. Kiểm tra mạng rồi bấm cập nhật lại."
    if "local changes" in thap or "would be overwritten" in thap:
        return ("Có file cục bộ chặn bản phát hành. Kiểm tra git status, cất hoặc đổi tên "
                "file đó rồi cập nhật lại; bản sao sửa đổi đã cất vẫn ở git stash.")
    return ""


def pip_install():
    """Cài thư viện. Mã lỗi TRẢ VỀ CHO NƠI GỌI KIỂM - trước đây không ai kiểm.

    pip hỏng (mất mạng giữa chừng, một gói bị gỡ khỏi PyPI, xung đột phiên bản giữa hai bản
    Javis) là một trong hai đường dẫn thẳng tới cảnh "cập nhật xong máy chết hẳn": server mới
    thiếu thư viện nên không lên, rồi đường lùi cũng chạy pip và cũng hỏng y hệt. Nuốt mã lỗi
    thì cả hai lần đều im lặng, và người dùng chỉ nhận được một câu chung chung."""
    r = run([venv_python(), "-m", "pip", "install", "-r", "requirements.txt", "-q"])
    if r.returncode != 0:
        log(f"pip LỖI (rc={r.returncode}). Server sắp tới nhiều khả năng KHÔNG lên được.")
    return r


def _head_hien_tai() -> str:
    return (run(["git", "rev-parse", "HEAD"]).stdout or "").strip()


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
        remote, branch = release_source()
        print(f"PLAN: stop -> fetch({remote}/{branch}) + merge(stash nếu bẩn) "
              f"-> pip -> start -> health({a.port}) "
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
    stash_oid, stash_error = stash_local_changes()
    if stash_error:
        log(stash_error)
        start_server(mode, a.port)
        them = "" if poll_health(a.port, 60) else " Server cũ chưa lên lại."
        us.write_state({"phase": "error", "result": "error", "error": stash_error + them,
                        "finished_at": _now()})
        return 1
    if stash_oid:
        us.write_state({"stashed": True})
    pull, tree_safe = merge_release()
    if pull.returncode != 0:
        git_error = "\n".join(x for x in (pull.stdout, pull.stderr) if x)
        log("Hợp nhất bản phát hành LỖI:\n" + git_error)
        if not tree_safe:
            note = (f"Không xác nhận được cây Git an toàn. Kiểm tra git status và update.log "
                    f"trước khi khởi động lại; "
                    f"bản sao sửa đổi {stash_oid[:12]} vẫn trong git stash."
                    if stash_oid else
                    "Không xác nhận được cây Git an toàn. Kiểm tra git status và update.log "
                    "trước khi khởi động lại.")
            us.write_state({"phase": "error", "result": "pull_failed", "error": note,
                            "finished_at": _now()})
            return 1
        stash_note = ""
        if stash_oid:
            restored, restore_error = restore_local_changes(stash_oid)
            if restored and drop_update_stash(stash_oid, restored):
                us.write_state({"stashed": False})
            elif restored:
                stash_note = f" Đã áp lại sửa đổi, nhưng bản sao {stash_oid[:12]} vẫn trong git stash."
            else:
                stash_note = (f" Chưa khôi phục được sửa đổi; bản sao {stash_oid[:12]} vẫn "
                              f"trong git stash: {restore_error}")
        # Merge đã hủy hoặc fetch thất bại; xác nhận server cũ thật sự lên lại.
        start_server(mode, a.port)
        them = "" if poll_health(a.port, 60) else (
            " Server cũ CŨNG chưa lên lại - mở Javis bằng tay để chạy tiếp.")
        ly_do = chan_doan_pull_hong(git_error, merge_aborted=tree_safe)
        log("Chẩn đoán: " + (ly_do or "(không nhận ra nguyên nhân quen thuộc)"))
        tho = (git_error or "Không hợp nhất được bản phát hành").strip()
        us.write_state({"phase": "error", "result": "pull_failed",
                        "error": ((ly_do + " (chi tiết trong update.log)") if ly_do else tho[:400])
                                 + stash_note + them,
                        "finished_at": _now()})
        return 1

    stash_restored = False
    stash_note = ""
    if stash_oid:
        stash_restored, restore_error = restore_local_changes(stash_oid)
        if stash_restored:
            log("Đã áp lại sửa đổi cục bộ; giữ bản sao tới khi bản mới chạy ổn.")
        else:
            stash_note = (f"Sửa đổi cục bộ chưa khôi phục được trên bản mới; bản sao "
                          f"{stash_oid[:12]} vẫn trong git stash: {restore_error}")
            log(stash_note)

    us.write_state({"phase": "installing"})
    log("Cài thư viện…")
    pip_moi = pip_install()

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
        if stash_oid and stash_restored:
            if drop_update_stash(stash_oid, stash_restored):
                us.write_state({"stashed": False})
            else:
                stash_note = f"Bản sao sửa đổi {stash_oid[:12]} vẫn trong git stash."
        if stash_note:
            us.write_state({"phase": "done", "result": "error", "error": stash_note,
                            "finished_at": _now()})
            return 1
        us.write_state({"phase": "done", "result": "success", "finished_at": _now()})
        return 0
    if outcome == "version_mismatch":
        if stash_oid and stash_restored:
            if drop_update_stash(stash_oid, stash_restored):
                us.write_state({"stashed": False})
            else:
                stash_note = f"Bản sao sửa đổi {stash_oid[:12]} vẫn trong git stash."
        ly_do = chan_doan_pull(pull.stdout or "")
        log("Phiên bản không đổi. Chẩn đoán: " + ly_do)
        us.write_state({"phase": "done", "result": "error",
                        "error": f"Vẫn đang chạy {current}, chưa lên {target}. {ly_do} {stash_note}",
                        "finished_at": _now()})
        return 1

    # need_rollback
    log("Bản mới KHÔNG lên được → tự lùi về bản cũ…")
    us.write_state({"phase": "rolling_back"})
    if not a.old_sha:
        us.write_state({"phase": "error", "result": "rollback_failed",
                        "error": "Không có commit cũ để lùi. "
                                 + (f"Bản sao sửa đổi {stash_oid[:12]} vẫn trong git stash."
                                    if stash_oid else ""), "finished_at": _now()})
        return 1
    # Từ đây trở xuống mọi bước đều KIỂM MÃ LỖI. Trước đây không bước nào kiểm, nên khi đường
    # lùi hỏng người dùng nhận đúng một câu "Xem update.log" - vô dụng trên bản Windows và
    # Docker, nơi họ không biết log nằm ở đâu. Tệ hơn: không ai biết mã nguồn lúc đó đang là
    # bản CŨ hay vẫn là bản MỚI đang hỏng, mà hai tình huống ấy cần hai cách chữa khác hẳn.
    hong = []

    rs = run(["git", "reset", "--hard", a.old_sha])
    head = _head_hien_tai()
    if rs.returncode != 0 or not head.startswith(a.old_sha[:7]):
        # Reset trượt là chuyện NẶNG NHẤT ở đây: mã nguồn vẫn là bản mới đang hỏng, nên bật
        # lại bao nhiêu lần cũng hỏng y như vậy. Phải nói thẳng, kèm lệnh chữa.
        hong.append(f"lùi mã nguồn KHÔNG thành (git reset rc={rs.returncode}, "
                    f"HEAD={head[:7] or '?'}). Mã nguồn vẫn là bản mới đang lỗi. "
                    f"Chạy tay: git reset --hard {a.old_sha[:12]}")

    # Reset xóa cả sửa đổi đã áp trên bản mới; áp lại từ bản sao nếu đã về commit cũ.
    if stash_oid:
        stash_restored = False
        if rs.returncode == 0 and head.startswith(a.old_sha[:7]):
            stash_restored, restore_error = restore_local_changes(stash_oid)
            if stash_restored:
                stash_note = ""
            else:
                stash_note = (f"Chưa khôi phục được sửa đổi sau rollback; bản sao "
                              f"{stash_oid[:12]} vẫn trong git stash: {restore_error}")
        else:
            stash_note = f"Bản sao sửa đổi {stash_oid[:12]} vẫn trong git stash."

    if pip_install().returncode != 0:
        hong.append("cài lại thư viện cho bản cũ thất bại - kiểm tra mạng rồi chạy lại: "
                    "pip install -r requirements.txt")

    # Bản mới có thể đang chạy dở (lên tiến trình nhưng /health đỏ) → dừng hẳn trước khi
    # bật bản cũ, kẻo nohup bind trùng cổng. Windows/systemd dừng lại cũng vô hại.
    stop_server(mode, 0, a.port)
    time.sleep(2)
    start_server(mode, a.port)
    if poll_health(a.port, 90):
        if stash_oid and stash_restored:
            if drop_update_stash(stash_oid, stash_restored):
                us.write_state({"stashed": False})
            else:
                stash_note = f"Bản sao sửa đổi {stash_oid[:12]} vẫn trong git stash."
        if stash_note:
            us.write_state({"phase": "error", "result": "rollback_failed",
                            "error": "Bản cũ đã chạy lại nhưng " + stash_note,
                            "finished_at": _now()})
            return 1
        us.write_state({"phase": "done", "result": "rolled_back",
                        "error": "Bản mới lỗi, đã tự quay về bản cũ.", "finished_at": _now()})
        return 0

    if pip_moi.returncode != 0:
        hong.append("bản mới cũng không cài nổi thư viện, nên nhiều khả năng lỗi nằm ở môi "
                    "trường chứ không ở mã nguồn")
    if stash_note:
        hong.append(stash_note)
    us.write_state({"phase": "error", "result": "rollback_failed",
                    "error": ("Bản mới lỗi và bản cũ cũng chưa lên. "
                              + ("; ".join(hong) if hong else
                                 "Mã nguồn đã lùi đúng và thư viện cài xong, nhưng server vẫn "
                                 "không lên - nhiều khả năng cổng đang bị tiến trình khác giữ.")),
                    "finished_at": _now()})
    return 1


if __name__ == "__main__":
    sys.exit(main())
