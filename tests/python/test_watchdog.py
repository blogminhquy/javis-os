"""Watchdog /health cho Mac chạy launchd - vụ treo 14/08/2026.

    python tests/run.py watchdog

Server treo kiểu tệ nhất: tiến trình SỐNG, cổng vẫn LISTEN, nhưng event loop đông cứng nên
/health im lặng và SIGTERM bị phớt. KeepAlive của launchd chỉ cứu tiến trình chết, nên phải
có watchdog.sh: N lần /health hỏng liên tiếp -> launchctl kickstart -k. Ở đây chạy chính
`watchdog.sh check` THẬT, chỉ thay lệnh kick bằng `echo` (không ai muốn test đá server thật
trên máy dev) - hành vi đếm/ngưỡng/reset/đứng-ngoài-lúc-cập-nhật đều là đường code thật.
"""
from _paths import ROOT  # noqa: E402,F401
import http.server
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


WD = ROOT / "watchdog.sh"
check("watchdog.sh tồn tại ở gốc repo (cạnh install.sh, update.sh)", WD.exists())
_syntax = subprocess.run(["bash", "-n", str(WD)], capture_output=True, text=True)
check("cú pháp bash hợp lệ", _syntax.returncode == 0, _syntax.stderr)

SRC = WD.read_text(encoding="utf-8")
check("kick bằng launchctl kickstart -k (SIGTERM bị phớt thì launchd tự SIGKILL)",
      "kickstart -k" in SRC)
check("LaunchAgent riêng com.javis.watchdog, không đè lên job chính com.javis.os",
      "com.javis.watchdog" in SRC and "StartInterval" in SRC)
check("nhãn job chính đổi được qua JAVIS_LAUNCHD_LABEL (đồng bộ với updater.py)",
      "JAVIS_LAUNCHD_LABEL" in SRC)


def chay(state_dir: str, port: int):
    """Một nhát `watchdog.sh check` với kick giả + state riêng, trả stdout."""
    r = subprocess.run(
        ["bash", str(WD), "check"], capture_output=True, text=True, cwd=str(ROOT),
        env={**os.environ, "JAVIS_PORT": str(port), "JAVIS_STATE_DIR": state_dir,
             "JAVIS_WATCHDOG_FAILS": "3", "JAVIS_WATCHDOG_KICK_CMD": "echo DA_KICK"},
        timeout=30)
    return (r.stdout or "") + (r.stderr or "")


def _dem(state_dir: str) -> str:
    f = Path(state_dir) / "watchdog-fails"
    return f.read_text(encoding="utf-8").strip() if f.exists() else "(chưa có)"


# --- cổng chết: đếm dần, đúng ngưỡng 3 mới kick, kick xong reset đếm ---
with tempfile.TemporaryDirectory() as td:
    # cổng 1 đóng chắc chắn (quyền bind cổng <1024 cần root, không ai nghe ở đó trên CI/dev)
    o1, o2 = chay(td, 1), chay(td, 1)
    check("2 lần /health hỏng đầu: chỉ đếm, CHƯA kick", "DA_KICK" not in o1 + o2, o1 + o2)
    check("đếm hỏng lưu đúng sau 2 lần", _dem(td) == "2", _dem(td))
    o3 = chay(td, 1)
    check("lần hỏng thứ 3 liên tiếp → kick", "DA_KICK" in o3, o3)
    check("kick xong reset đếm về 0 (không kick dồn dập mỗi phút)", _dem(td) == "0", _dem(td))

    # --- đang có lượt cập nhật (update_state.json nóng) → đứng ngoài, không đếm ---
    (Path(td) / "update_state.json").write_text('{"phase": "restarting"}', encoding="utf-8")
    o4 = chay(td, 1)
    check("updater đang chạy → watchdog đứng ngoài (không đếm /health đỏ hợp lệ)",
          "cập nhật" in o4 and _dem(td) == "0", o4)

# --- server khoẻ: /health 200 → đếm về 0, không kick ---
class _OK(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/health" else 404)
        self.end_headers()

    def log_message(self, *a):
        pass


_srv = http.server.HTTPServer(("127.0.0.1", 0), _OK)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory() as td:
    (Path(td) / "watchdog-fails").write_text("2", encoding="utf-8")  # giả sử vừa hỏng 2 lần
    o = chay(td, _srv.server_address[1])
    check("/health xanh → reset đếm, không kick", "DA_KICK" not in o and _dem(td) == "0", o)
_srv.shutdown()

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test watchdog đã qua.")
