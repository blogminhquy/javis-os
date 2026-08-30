"""Một CLI hỏng KHÔNG được kéo cả dashboard chết theo.

    python tests/run.py settings_khong_treo_theo_cli     (KHÔNG mạng, không cần cài agy)

Khách báo 2026-08-30, đúng nguyên văn cảnh này: chọn model Antigravity xong là "disable tất
cả cổng" - mọi nút xám, không đổi được model, trang Cập nhật báo không kiểm tra được phiên
bản, cài đè source mới cũng không hết. Nguyên nhân không nằm ở model đã chọn mà ở chỗ này:

    GET /settings (handler async, chạy TRÊN event loop)
      -> _providers_view
        -> antigravity_cli.auth_status()
          -> `agy --help` (20s) + `agy models` JSON (30s) + `agy models` thường (30s)

`agy` chưa đăng nhập thì mở menu "Select login method" rồi ngồi chờ bàn phím, nên một binary
hỏng là mỗi lượt /settings chặn event loop tới ~80 giây - MỌI endpoint khác chết theo, và cache
lỗi chỉ sống 60 giây nên cảnh đó lặp mãi. Cài lại source không cứu được vì binary hỏng vẫn nằm
trên PATH.

Bản vá có ba tầng, test khoá cả ba:
  1. auth_status_nen(): hot path chỉ đọc cache, làm mới ở thread nền (single-flight).
  2. _help_text nhớ CẢ kết quả rỗng - trước đây binary hỏng là `--help` chạy lại mỗi lượt.
  3. Mọi probe subprocess.run của hai driver CLI cắt stdin (DEVNULL) - CLI rơi vào màn hỏi
     tương tác thì thoát ngay thay vì ngồi chờ bàn phím vô hình ăn trọn timeout.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import io
import os
import re
import tempfile
import threading
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-treo-"))

import antigravity_cli  # noqa: E402
import grok_cli         # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + ((" [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. auth_status_nen: KHÔNG chặn luồng gọi, kể cả khi CLI treo
# ============================================================
_that_auth = antigravity_cli.auth_status
_that_find = antigravity_cli.find_antigravity_cli
_dem = {"auth": 0}


def _auth_cham(bo_qua_cache=False):
    """Giả một auth_status mất 1.2s - mô phỏng `agy` chậm/treo (bản thật tới ~80s)."""
    _dem["auth"] += 1
    time.sleep(1.2)
    d = {"connected": True, "method": "gia-lap", "email": "", "error": ""}
    antigravity_cli._AUTH_CACHE.update(ts=time.time(), val=dict(d))
    return d


try:
    antigravity_cli.find_antigravity_cli = lambda: "/fake/agy"
    antigravity_cli.auth_status = _auth_cham
    antigravity_cli._AUTH_CACHE.update(ts=0.0, val=None)   # chưa từng probe
    antigravity_cli._AUTH_LAM_MOI["dang_chay"] = False

    t0 = time.time()
    d1 = antigravity_cli.auth_status_nen()
    mat = time.time() - t0
    check(f"lần đầu (cache trống) trả lời NGAY, không chờ CLI ({mat*1000:.0f}ms)", mat < 0.3, mat)
    check("và nói thật là đang kiểm chứ không bịa 'đã kết nối'",
          d1.get("connected") is False and d1.get("dang_kiem") is True, d1)

    # Gọi dồn dập trong lúc thread nền đang chạy: single-flight, không đẻ thêm probe.
    for _ in range(5):
        antigravity_cli.auth_status_nen()
    time.sleep(1.5)   # chờ thread nền xong
    check(f"5 lượt gọi dồn chỉ đẻ ĐÚNG 1 probe nền (đếm được {_dem['auth']})", _dem["auth"] == 1)

    d2 = antigravity_cli.auth_status_nen()
    check("lượt sau đọc được kết quả thread nền đã điền", d2.get("connected") is True, d2)

    # Cache còn hạn thì không probe lại.
    antigravity_cli.auth_status_nen()
    check("cache còn hạn thì thôi, không probe thêm", _dem["auth"] == 1)
finally:
    antigravity_cli.auth_status = _that_auth
    antigravity_cli.find_antigravity_cli = _that_find
    antigravity_cli._AUTH_CACHE.update(ts=0.0, val=None)
    antigravity_cli._AUTH_LAM_MOI["dang_chay"] = False

# Thread nền nổ lỗi thì cờ single-flight phải được nhả, không thì kẹt vĩnh viễn.
try:
    antigravity_cli.find_antigravity_cli = lambda: "/fake/agy"

    def _auth_no(bo_qua_cache=False):
        raise RuntimeError("giả lập probe nổ")

    antigravity_cli.auth_status = _auth_no
    antigravity_cli._AUTH_CACHE.update(ts=0.0, val=None)
    antigravity_cli.auth_status_nen()
    time.sleep(0.3)
    check("probe nền nổ lỗi thì cờ single-flight được nhả (lần sau còn probe lại được)",
          antigravity_cli._AUTH_LAM_MOI["dang_chay"] is False)
finally:
    antigravity_cli.auth_status = _that_auth
    antigravity_cli.find_antigravity_cli = _that_find
    antigravity_cli._AUTH_CACHE.update(ts=0.0, val=None)
    antigravity_cli._AUTH_LAM_MOI["dang_chay"] = False


# ============================================================
# 2. _providers_view không còn đường nào tới auth_status CHẶN
# ============================================================
# Soi nguồn thay vì dựng cả app: main.py nạp nặng, mà điều cần khoá là "đừng ai vô tình đổi
# auth_status_nen về auth_status trong _providers_view" - một literal check bắt được đúng nó.
_src = io.open(os.path.join(ROOT, "server", "main.py"), encoding="utf-8").read()
_pv = _src.split("def _providers_view", 1)[1].split("\ndef ", 1)[0]
check("CANARY: _providers_view chỉ dùng auth_status_nen cho agy, không gọi bản chặn",
      "antigravity_cli.auth_status_nen()" in _pv
      and "antigravity_cli.auth_status()" not in _pv)
check("grok trong _providers_view vẫn là bản đọc-file (rẻ, không phải sửa)",
      "grok_cli.auth_status()" in _pv)


# ============================================================
# 3. _help_text nhớ CẢ kết quả rỗng
# ============================================================
for _mod, _ten in ((antigravity_cli, "agy"), (grok_cli, "grok")):
    _dem_run = {"n": 0}
    _that_run = _mod.subprocess.run

    def _run_no(*a, **k):
        _dem_run["n"] += 1
        raise OSError("giả lập binary hỏng")

    try:
        if _mod is antigravity_cli:
            _mod.find_antigravity_cli = lambda: "/fake/bin"
        else:
            _that_find_g = _mod.find_grok_cli
            _mod.find_grok_cli = lambda: "/fake/bin"
        _mod._HELP_CACHE.update(path=None, text="", ts=0.0)
        _mod.subprocess.run = _run_no
        _mod._help_text()
        _mod._help_text()
        _mod.co_co("--gi-do")
        check(f"{_ten}: `--help` hỏng chỉ chạy 1 lần rồi nhớ, không chạy lại mỗi lượt "
              f"(đếm được {_dem_run['n']})", _dem_run["n"] == 1)
    finally:
        _mod.subprocess.run = _that_run
        _mod._HELP_CACHE.update(path=None, text="", ts=0.0)
        if _mod is antigravity_cli:
            _mod.find_antigravity_cli = _that_find
        else:
            _mod.find_grok_cli = _that_find_g


# ============================================================
# 4. Mọi probe subprocess.run của 2 driver phải cắt stdin
# ============================================================
# CLI rơi vào màn hỏi tương tác (menu đăng nhập của agy, hộp thoại lần-đầu-chạy) mà còn stdin
# là nó ngồi chờ bàn phím vô hình cho tới hết timeout. Trừ duy nhất chỗ CỐ Ý bơm stdin
# (input=...), mọi subprocess.run còn lại phải khai stdin=subprocess.DEVNULL.
for _f in ("antigravity_cli.py", "grok_cli.py"):
    _s = io.open(os.path.join(ROOT, "server", _f), encoding="utf-8").read()
    _thieu = []
    for m in re.finditer(r"subprocess\.run\((?:[^()]|\([^()]*\))*\)", _s):
        goi = m.group(0)
        if "input=" in goi or "stdin=" in goi:
            continue
        dong = _s[:m.start()].count("\n") + 1
        _thieu.append(f"dòng {dong}")
    check(f"{_f}: mọi subprocess.run đều cắt stdin (hoặc cố ý bơm input)", not _thieu,
          "; ".join(_thieu))

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("TẤT CẢ PASS")
