# -*- coding: utf-8 -*-
"""Đăng nhập `agy` trong tab Code phải CÓ CHỖ DÁN MÃ.

    python tests/run.py agy_dan_ma     (KHÔNG mạng)

Sự cố 05/09 (chủ repo, Javis chạy Docker, trình duyệt trên máy Mac): gõ `agy` trong tab Code,
màn hình in ra link Google rồi đứng im - không có ô nào để điền mã, đăng nhập tắc ở đó.

Bàn phím của terminal KHÔNG hỏng (pty thật, gõ được). Bệnh nằm ở chỗ `agy` chọn đường đăng
nhập theo môi trường: thấy `SSH_CONNECTION` thì in link rồi CHỜ dán ngược URL callback vào;
không thấy thì coi trình duyệt nằm cùng máy, mở một cổng loopback rồi nằm chờ im lặng. Terminal
của Javis là pty ngay trên máy chủ nên không có biến SSH nào, luôn rơi vào đường thứ hai - mà
trình duyệt lại ở máy khác, nên mã không bao giờ về tới nơi.

Test này giữ hai điều: `_env` khai phiên từ xa khi máy chủ không có màn hình, và hướng dẫn trên
thẻ Models nói đúng bước dán tay.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
from unittest import mock

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


import terminal  # noqa: E402
import antigravity_cli  # noqa: E402

_GIU = {k: os.environ.get(k) for k in
        ("JAVIS_TERMINAL_REMOTE", "SSH_CONNECTION", "SSH_CLIENT", "DISPLAY", "WAYLAND_DISPLAY")}


def _dat(**kv):
    """Đặt/xoá env cho một tình huống, không để rác lại cho test sau."""
    for k in _GIU:
        os.environ.pop(k, None)
    for k, v in kv.items():
        if v is not None:
            os.environ[k] = v


def _tra_lai():
    for k, v in _GIU.items():
        os.environ.pop(k, None)
        if v is not None:
            os.environ[k] = v


try:
    # ---- 1. Máy chủ không màn hình (VPS, Docker - kể cả Docker trên máy Mac) ----
    with mock.patch.object(terminal, "IS_WINDOWS", False), mock.patch.object(sys, "platform", "linux"):
        _dat()
        check("CANARY: máy chủ không có màn hình -> coi là phiên từ xa",
              terminal._khong_co_trinh_duyet() is True)
        env = terminal._env()
        check("CANARY: _env đặt SSH_CONNECTION (agy mới hỏi chỗ dán mã)",
              bool(env.get("SSH_CONNECTION")))
        check("SSH_CONNECTION đúng dạng 4 phần <ip> <cổng> <ip> <cổng>",
              len(env.get("SSH_CONNECTION", "").split()) == 4)
        check("có kèm SSH_CLIENT cho CLI nào đọc biến đó", bool(env.get("SSH_CLIENT")))

        # ---- 2. Linux có màn hình: trình duyệt mở ngay trước mặt, giữ luồng cũ ----
        _dat(DISPLAY=":0")
        check("Linux có DISPLAY -> KHÔNG khai từ xa (trình duyệt cùng máy)",
              terminal._khong_co_trinh_duyet() is False)
        check("và _env không chèn SSH_CONNECTION", not terminal._env().get("SSH_CONNECTION"))
        _dat(WAYLAND_DISPLAY="wayland-0")
        check("Wayland cũng tính là có màn hình", terminal._khong_co_trinh_duyet() is False)

        # ---- 3. Phiên SSH THẬT: không đè lên giá trị của hệ thống ----
        _dat(SSH_CONNECTION="10.0.0.9 51234 10.0.0.1 22")
        check("SSH thật thì giữ nguyên giá trị gốc",
              terminal._env().get("SSH_CONNECTION") == "10.0.0.9 51234 10.0.0.1 22")

        # ---- 4. Công tắc tay ----
        _dat(JAVIS_TERMINAL_REMOTE="0")
        check("JAVIS_TERMINAL_REMOTE=0 tắt được (bố trí lạ: X11 forwarding...)",
              terminal._khong_co_trinh_duyet() is False)
        _dat(JAVIS_TERMINAL_REMOTE="1", DISPLAY=":0")
        check("JAVIS_TERMINAL_REMOTE=1 bật được kể cả khi có DISPLAY",
              terminal._khong_co_trinh_duyet() is True)

    # ---- 5. Máy để bàn chạy THẲNG (macOS/Windows): trình duyệt ở ngay trước mặt ----
    _dat()
    with mock.patch.object(terminal, "IS_WINDOWS", False), mock.patch.object(sys, "platform", "darwin"):
        check("macOS chạy thẳng -> giữ luồng tự mở trình duyệt",
              terminal._khong_co_trinh_duyet() is False)
    with mock.patch.object(terminal, "IS_WINDOWS", True):
        check("Windows chạy thẳng -> giữ luồng tự mở trình duyệt",
              terminal._khong_co_trinh_duyet() is False)
finally:
    _tra_lai()

# ---- 6. Hướng dẫn trên thẻ Models nói đúng bước dán tay ----
hd = antigravity_cli.login_huong_dan()
check("hướng dẫn nói phải DÁN địa chỉ ngược vào terminal", "dán" in hd["ghi_chu"].lower())
check("nói trước rằng localhost báo lỗi là bước ĐÚNG", "localhost" in hd["ghi_chu"].lower())
check("vẫn giữ lời cảnh báo đăng nhập đúng user (trang Code trong Javis)",
      "NGAY TRONG Javis" in hd["ghi_chu"] and "root" in hd["ghi_chu"])
check("có đường cứu hộ bằng curl cho bản agy cũ",
      "curl" in (hd.get("cuu_ho") or ""))

js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("thẻ Antigravity có vẽ dòng cứu hộ ra màn hình", "dn.cuu_ho" in js)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_agy_dan_ma_tu_terminal: tat ca pass")
