"""Đăng nhập Google cho Antigravity CLI ngay trên dashboard (không cần terminal).

    python tests/run.py antigravity_login      (KHÔNG mạng, KHÔNG cần cài agy)

Javis không bắc cầu token được như với Gemini CLI (`agy` cất phiên trong keyring của hệ điều
hành, không có file để ghi), nên nó LÁI chính luồng đăng nhập của CLI: mở `agy` trong một
terminal giả, bắt link authorize đưa lên dashboard, rồi bơm ngược mã người dùng dán vào.

Bốn chỗ dễ hỏng, và đây là test cho đúng bốn chỗ đó:

1. **Phải là PTY thật.** `agy` là giao diện bàn phím; đưa ống dẫn thường thì nó đổi hành vi.
   Test dựng một `agy` giả TỰ KIỂM `isatty()` và chỉ in link khi thấy terminal thật.
2. **Link không được gãy.** Bản CLI hiện tại ngắt dòng link theo bề rộng terminal rồi chèn
   xuống dòng vào GIỮA URL (issue #315). Dán một URL gãy sang Google là hỏng, mà lỗi lại trông
   như "mã sai". Javis là bên cấp terminal nên đặt bề rộng rất lớn; test ép `agy` giả ngắt dòng
   để chắc chắn phần dọn dẹp cũng làm việc.
3. **Mã đi xuống được stdin.** Bơm nhầm chỗ thì CLI ngồi chờ mãi.
4. **Thành công phải do KIỂM CHỨNG, không do đọc chữ CLI in ra.** Giao diện nó vẽ đủ thứ và
   câu chữ đổi theo bản; nguồn chân lý là hỏi lại `auth_status()`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import stat
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agylogin-")

import antigravity_cli    # noqa: E402
import antigravity_login  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name
          + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


_LINK = ("https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id="
         "681255809395-oo8abcdefghijklmnop.apps.googleusercontent.com&redirect_uri="
         "urn:ietf:wg:oauth:2.0:oob&scope=openid%20email%20profile&state=abc123xyz")


def _gia_agy(*, doi_tty=True, ngat_dong=0, in_ra=None, nhan_ma=True):
    """Dựng một `agy` giả.

    doi_tty: chỉ in link khi stdout LÀ terminal thật (đúng như CLI thật).
    ngat_dong: chèn xuống dòng vào giữa link mỗi N ký tự, giả lỗi #315.
    """
    d = Path(tempfile.mkdtemp(prefix="javis-fakeagy-login-"))
    p = d / "agy"
    body = f'''#!/usr/bin/env python3
import sys, os
if "--help" in sys.argv[1:]:
    sys.stdout.write("Usage: agy [options]\\n  -p, --print\\n"); sys.exit(0)
link = {_LINK!r}
if {doi_tty!r} and not sys.stdout.isatty():
    sys.stdout.write("cần chạy trong terminal\\n"); sys.stdout.flush(); sys.exit(2)
{"" if in_ra is None else f"sys.stdout.write({in_ra!r}); sys.stdout.flush(); sys.exit(0)"}
n = {ngat_dong}
ra = link if not n else "\\n".join(link[i:i+n] for i in range(0, len(link), n))
sys.stdout.write("Sign in with Google:\\n" + ra + "\\n\\nPaste code here: ")
sys.stdout.flush()
if {nhan_ma!r}:
    ma = sys.stdin.readline().strip()
    open({str(d / "ma.txt")!r}, "w").write(ma)
    sys.stdout.write("\\nSigned in.\\n"); sys.stdout.flush()
'''
    p.write_text(body, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p), d


_that_find = antigravity_cli.find_antigravity_cli

if os.name == "nt":
    check("Windows: nói thẳng là không lái được, không dựng nút chết",
          antigravity_login.kha_dung()[0] is False)
    print("\nBỏ qua phần PTY trên Windows.")
else:
    check("Linux/macOS: lái được luồng đăng nhập", antigravity_login.kha_dung()[0] is True)

    # ---- 1 + 2. PTY thật, và link không gãy dù CLI có ngắt dòng ----
    _cli, _d = _gia_agy(doi_tty=True, ngat_dong=40)
    antigravity_cli.find_antigravity_cli = lambda: _cli
    antigravity_cli._HELP_CACHE.update(path=None, text="", ts=0.0)
    _r = antigravity_login.bat_dau(timeout=25)
    check("CANARY: chạy trong PTY thật nên CLI chịu in link (ống dẫn thường là nó bỏ chạy)",
          _r.get("ok") is True, _r)
    check("CANARY: link lấy về NGUYÊN VẸN dù CLI ngắt dòng giữa URL (lỗi #315)",
          _r.get("url") == _LINK, _r.get("url"))
    check("link không dính khoảng trắng hay xuống dòng nào",
          not any(c.isspace() for c in (_r.get("url") or "x")))

    # ---- 3. Mã đi xuống được stdin của tiến trình ----
    antigravity_cli._AUTH_CACHE.update(ts=0.0, val=None)
    _dem = {"n": 0}

    def _gia_auth(bo_qua_cache=False):
        # Lượt hỏi đầu chưa xong, lượt sau mới xong - giống thực tế CLI cần chút thời gian.
        _dem["n"] += 1
        return {"connected": _dem["n"] >= 2, "method": "google", "email": "", "error": ""}

    _that_auth = antigravity_cli.auth_status
    antigravity_cli.auth_status = _gia_auth
    try:
        _r2 = antigravity_login.gui_ma("MA-GOOGLE-123", timeout=25)
    finally:
        antigravity_cli.auth_status = _that_auth
    check("gửi mã xong báo thành công", _r2.get("ok") is True, _r2)
    _ma_nhan = ""
    try:
        _ma_nhan = (_d / "ma.txt").read_text(encoding="utf-8").strip()
    except Exception:
        pass
    check("CANARY: mã thật sự tới được stdin của `agy` (bơm nhầm chỗ là CLI chờ mãi)",
          _ma_nhan == "MA-GOOGLE-123", _ma_nhan)
    check("xong thì đóng phiên, không để tiến trình con treo lại",
          antigravity_login.trang_thai()["dang_cho"] is False)

    # ---- 4. Thành công là do KIỂM CHỨNG, không do đọc chữ CLI in ra ----
    _cli3, _d3 = _gia_agy(doi_tty=True)
    antigravity_cli.find_antigravity_cli = lambda: _cli3
    antigravity_login.bat_dau(timeout=25)
    antigravity_cli.auth_status = lambda bo_qua_cache=False: {
        "connected": False, "method": "", "email": "", "error": "chưa"}
    try:
        _r3 = antigravity_login.gui_ma("MA-SAI", timeout=6)
    finally:
        antigravity_cli.auth_status = _that_auth
    check("CANARY: CLI in 'Signed in.' nhưng auth_status nói chưa -> KHÔNG báo thành công",
          _r3.get("ok") is False, _r3)
    check("và câu báo chỉ được việc phải làm tiếp",
          "Kiểm tra lại" in (_r3.get("error") or "") or "agy" in (_r3.get("error") or ""))

    # ---- Không có link trong thứ CLI in ra: giữ nguyên văn cho người dùng đọc ----
    _cli4, _ = _gia_agy(doi_tty=True, in_ra="Already signed in as ai@do.com\n")
    antigravity_cli.find_antigravity_cli = lambda: _cli4
    _r4 = antigravity_login.bat_dau(timeout=15)
    check("không thấy link -> báo lỗi chứ không treo", _r4.get("ok") is False, _r4)
    check("CANARY: trả kèm NGUYÊN VĂN thứ CLI in ra (luồng Google đổi thì đây là manh mối duy nhất)",
          "Already signed in" in (_r4.get("log") or ""), _r4)

    antigravity_cli.find_antigravity_cli = lambda: None
    _r5 = antigravity_login.bat_dau(timeout=5)
    check("chưa cài agy -> nói cách cài, không nổ",
          _r5.get("ok") is False and "install" in (_r5.get("error") or ""), _r5)

antigravity_cli.find_antigravity_cli = _that_find

# ---- Đã đấu vào Javis chưa ----
_main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
for _e in ("/antigravity/login-start", "/antigravity/login-code", "/antigravity/login-cancel"):
    check(f"có endpoint {_e}", _e in _main_src)
check("trang Models biết máy này có lái được đăng nhập không", '"login_ui"' in _main_src)

_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("thẻ Models có nút Đăng nhập Google", "data-agylogin" in _console)
check("và ô dán mã", "agyCode" in _console and "/antigravity/login-code" in _console)
check("CANARY: nút chỉ hiện khi máy lái được (Windows không có nút chết)",
      "p.login_ui" in _console)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test antigravity_login đã qua.")
