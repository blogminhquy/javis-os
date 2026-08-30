"""Đổi Main Model xong KHÔNG được làm Claude trông như bị đăng xuất.

    python tests/run.py claude_auth_khong_mat      (KHÔNG mạng, KHÔNG cần cài claude)

Chủ repo báo 2026-08-13 kèm ảnh: chuyển Main Model sang Antigravity xong quay lại thì thẻ
**Anthropic OAuth (Claude Code)** hiện "○ Chưa đăng nhập" kèm nút Đăng nhập, nên phải đi nối
lại Claude - trong khi tài khoản chẳng mất gì cả.

GỐC RỄ là một phép trộn hai thứ khác nhau. `auth_status()` chạy `claude auth status --json`,
tốn một tiến trình Node cỡ một giây; đổi model thì trang Models vẽ lại và CÙNG LÚC còn
`agy models` + /provider/models cũng đẻ tiến trình con. Trên máy nhỏ, lượt hỏi này hết 25 giây
rồi ném TimeoutExpired - và bản cũ trả `connected: False` cho ca đó, y hệt ca CLI nói thật là
"chưa đăng nhập". Thẻ vẽ theo `connected` nên bày nút đăng nhập ra.

Hai thứ phải tách bạch, và đó là toàn bộ nội dung file này:

  - `connected: False`  = CLI NÓI chưa đăng nhập  -> bày nút đăng nhập là đúng.
  - `unknown: True`     = KHÔNG hỏi được          -> không biết gì, cấm nói "chưa đăng nhập".

Cộng thêm hai thứ giảm hẳn số lần rơi vào ca đó: nhớ kết quả 90 giây (khỏi đẻ tiến trình mỗi
lần vẽ trang), và hỏi hỏng thì trả lại bản nhớ kèm `stale` thay vì một câu đoán bừa.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import subprocess
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-cauth-")

import claude_cli   # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


class _R:
    def __init__(self, out):
        self.stdout = out
        self.stderr = ""
        self.returncode = 0


_that_find = claude_cli.find_claude_cli
_that_run = claude_cli.subprocess.run
claude_cli.find_claude_cli = lambda: "/usr/bin/claude"

_lan = {"n": 0}


def _run_ok(*a, **k):
    _lan["n"] += 1
    return _R('{"loggedIn": true, "email": "ai@do.com", "subscriptionType": "max"}')


def _run_timeout(*a, **k):
    _lan["n"] += 1
    raise subprocess.TimeoutExpired(cmd="claude", timeout=25)


def _run_chua_dn(*a, **k):
    _lan["n"] += 1
    return _R('{"loggedIn": false}')


try:
    # ---- 1. Đọc được thì trả đúng, và NHỚ lại ----
    claude_cli.auth_quen_cache()
    claude_cli.subprocess.run = _run_ok
    _lan["n"] = 0
    _d1 = claude_cli.auth_status()
    check("đăng nhập rồi thì báo đã kết nối", _d1.get("connected") is True, _d1)
    claude_cli.auth_status()
    claude_cli.auth_status()
    check("CANARY: hỏi thêm hai lần nữa KHÔNG đẻ thêm tiến trình nào (nhớ 90 giây)",
          _lan["n"] == 1, _lan["n"])
    check("và bản nhớ không tự dán nhãn cũ khi còn hạn", "stale" not in claude_cli.auth_status())

    # ---- 2. Hỏi HỎNG nhưng từng hỏi được -> giữ trạng thái cũ, KHÔNG bịa ra "chưa đăng nhập" ----
    claude_cli.subprocess.run = _run_timeout
    _d2 = claude_cli.auth_status(bo_qua_cache=True)
    check("CANARY: hết giờ mà trước đó đang đăng nhập -> VẪN báo đã kết nối, không đá người "
          "dùng về màn đăng nhập", _d2.get("connected") is True, _d2)
    check("và nói rõ đây là trạng thái lần trước", _d2.get("stale") is True, _d2)
    check("kèm lý do thật để còn tra", "Timeout" in str(_d2.get("error", "")), _d2)

    # ---- 3. Hỏi hỏng mà CHƯA từng hỏi được -> 'unknown', tuyệt đối không nói "chưa đăng nhập" ----
    claude_cli.auth_quen_cache()
    claude_cli.subprocess.run = _run_timeout
    _d3 = claude_cli.auth_status()
    check("CANARY: không hỏi được -> unknown=True, KHÁC hẳn 'chưa đăng nhập'",
          _d3.get("unknown") is True and _d3.get("connected") is False, _d3)

    # ---- 4. CLI nói thật là chưa đăng nhập -> KHÔNG được gắn unknown ----
    claude_cli.auth_quen_cache()
    claude_cli.subprocess.run = _run_chua_dn
    _d4 = claude_cli.auth_status()
    check("CANARY: CLI nói chưa đăng nhập -> connected=False mà KHÔNG unknown (chỗ này phải "
          "bày nút đăng nhập thật)",
          _d4.get("connected") is False and not _d4.get("unknown"), _d4)

    # ---- 5. Đăng nhập / ngắt xong phải quên bản nhớ ngay ----
    claude_cli.subprocess.run = _run_ok
    claude_cli.auth_status()
    claude_cli.auth_quen_cache()
    _lan["n"] = 0
    claude_cli.auth_status()
    check("quên bản nhớ thì lượt sau hỏi lại CLI thật", _lan["n"] == 1, _lan["n"])
finally:
    claude_cli.find_claude_cli = _that_find
    claude_cli.subprocess.run = _that_run
    claude_cli.auth_quen_cache()

# ---- Đã đấu vào server + giao diện chưa ----
_main = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("endpoint có đường ép hỏi lại CLI", "bo_qua_cache=bool(refresh)" in _main)
check("ngắt xong quên bản nhớ ngay",
      "auth_quen_cache()" in (ROOT / "server" / "claude_cli.py").read_text(encoding="utf-8"))

_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
_vi_i18n = (ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8")
check("CANARY: thẻ vẽ RIÊNG trạng thái chưa kiểm được, không gộp vào 'chưa đăng nhập'",
      "d.unknown" in _console and 't("models.st_unknown")' in _console
      and "Chưa kiểm được trạng thái" in _vi_i18n)
check("và nói thẳng là KHÔNG có nghĩa bị đăng xuất",
      't("models.cli_unk2")' in _console and "Không có nghĩa là bạn bị" in _vi_i18n)
check("nút Kiểm tra lại ép hỏi lại CLI chứ không đọc bản nhớ",
      "refreshClaudeCard(el, true)" in _console)
check("đang kết nối mà hỏi lại hỏng thì thẻ nói rõ đang hiện trạng thái cũ",
      "d.stale" in _console)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test claude_auth_khong_mat đã qua.")
