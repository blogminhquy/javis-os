"""Ba mức tiết kiệm token, thay cho việc bắt người dùng hiểu 10 đường canary.

    python tests/run.py runtime_preset

Phản hồi thật của chủ repo về bản trước: "không hiểu trang này và không biết sử dụng như nào,
UX/UI thì quá tệ", "ấn vào đặt thì không có gì diễn ra", "công tắc trùm cũng không hiểu ý
nghĩa". Ba lời đó chỉ vào cùng một sai lầm: phơi nguyên mô hình bên trong (10 canary, đơn vị
basis point, một công tắc mode) ra cho người dùng tự ráp.

Nguyên tắc của file này: mức phải THẬT SỰ đổi được trạng thái, và chỉ gồm những đường chạy
được với cấu hình mặc định - bật một đường sẽ fail-closed chỉ tạo cảm giác đã bật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-preset-")

import config as cfg  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Ba mức, mô tả bằng tiếng người ----
check("có đúng ba mức", set(main.RUNTIME_PRESETS) == {"off", "saving", "max"})
for _k, _p in main.RUNTIME_PRESETS.items():
    check(f"mức '{_k}' có nhãn tiếng Việt", bool(_p.get("nhan")))
    check(f"mức '{_k}' có mô tả nói được đánh đổi", len(_p.get("mo_ta") or "") > 40)

# Mức càng cao càng bật nhiều, không được đảo lộn.
check("Tắt không bật gì", main.RUNTIME_PRESETS["off"]["duong"] == {})
check("Tiết kiệm bật ít hơn Tối đa",
      set(main.RUNTIME_PRESETS["saving"]["duong"])
      < set(main.RUNTIME_PRESETS["max"]["duong"]))

# ---- 2. CHỈ gồm đường chạy được ở cấu hình mặc định ----
# Bật một đường sẽ fail-closed là tạo cảm giác đã bật trong khi mọi lượt vẫn đi đường cũ -
# đúng cái bẫy mà rào _canary_inert_reason sinh ra để chặn.
# Đường nào cần hạn mức thì endpoint phải TỰ KHAI trước khi bật; đường nào cần allowlist mà
# mặc định rỗng thì tuyệt đối không được đưa vào preset (không có cách tự khai an toàn).
_default_rt = cfg._DEFAULT["context_runtime"]
for _k, _p in main.RUNTIME_PRESETS.items():
    for _path in _p["duong"]:
        _entry = dict(_default_rt.get(_path) or {})
        _co_allowlist = "capability_profiles" in _entry or "allowed_slugs" in _entry
        check(f"mức '{_k}': '{_path}' không đòi allowlist (mặc định rỗng = chết câm)",
              not _co_allowlist)

# Mọi tên đường trong preset phải là canary CÓ THẬT.
_keys = main._canary_keys()
for _k, _p in main.RUNTIME_PRESETS.items():
    for _path in _p["duong"]:
        check(f"mức '{_k}': '{_path}' là canary có thật", _path in _keys)

# ---- 3. Nhận ra mức đang dùng ----
check("mặc định là Tắt", main.current_preset(cfg._DEFAULT["context_runtime"]) == "off")

_rt = json.loads(json.dumps(cfg._DEFAULT["context_runtime"]))
_rt["mode"] = "canary"
for _p in main.RUNTIME_PRESETS["saving"]["duong"]:
    _rt[_p]["allocation_basis_points"] = 10000
check("bật đủ 3 đường → nhận ra là Tiết kiệm", main.current_preset(_rt) == "saving")

# Bật đúng các đường nhưng công tắc trùm còn shadow thì KHÔNG được báo là đã bật, vì thực tế
# không có gì chạy. Đây đúng là tình huống chủ repo gặp.
_rt["mode"] = "shadow"
check("đúng đường nhưng mode shadow → KHÔNG báo là Tiết kiệm",
      main.current_preset(_rt) != "saving")

_rt["mode"] = "canary"
_rt["write_canary"]["allocation_basis_points"] = 500
check("chỉnh tay lệch chuẩn → báo custom, không im lặng nhận bừa",
      main.current_preset(_rt) == "custom")


# ---- 4. Endpoint đổi mức THẬT SỰ đổi trạng thái ----
async def _go():
    r = await main.runtime_preset_set(level="khong_co")
    check("mức không tồn tại → 400", getattr(r, "status_code", 0) == 400)

    r = await main.runtime_preset_set(level="saving")
    check("đổi sang Tiết kiệm → ok", isinstance(r, dict) and r.get("ok"))
    check("báo rõ đã bật những gì (không im lặng)", len(r.get("da_bat") or []) == 3)

    _now = cfg.read_settings()["context_runtime"]
    check("công tắc trùm tự sang canary, không bắt user tự hiểu",
          _now.get("mode") == "canary")
    for _p in main.RUNTIME_PRESETS["saving"]["duong"]:
        check(f"'{_p}' đã bật thật trong settings",
              _now[_p]["allocation_basis_points"] == 10000)
    check("đọc lại nhận đúng mức", main.current_preset(_now) == "saving")

    # Đường lui phải rẻ: bấm Tắt là về sạch.
    r = await main.runtime_preset_set(level="off")
    check("đổi sang Tắt → ok", isinstance(r, dict) and r.get("ok"))
    check("báo rõ đã tắt những gì", len(r.get("da_tat") or []) == 3)
    _now = cfg.read_settings()["context_runtime"]
    check("mọi đường đã về 0",
          all(int((v or {}).get("allocation_basis_points") or 0) == 0
              for v in _now.values() if isinstance(v, dict)
              and "allocation_basis_points" in v))

    # Đổi lên Tối đa rồi xuống Tiết kiệm phải TẮT phần dư, không cộng dồn.
    await main.runtime_preset_set(level="max")
    _now = cfg.read_settings()["context_runtime"]
    check("Tối đa bật cả đường tắt nhanh", _now["canary"]["allocation_basis_points"] == 10000)
    r = await main.runtime_preset_set(level="saving")
    _now = cfg.read_settings()["context_runtime"]
    check("hạ mức thì TẮT phần dư, không cộng dồn",
          _now["canary"]["allocation_basis_points"] == 0)

    # Đổi mức không được làm mất cấu hình anh em (bẫy merge một tầng cũ).
    check("đổi mức không làm mất quota_profiles",
          "quota_profiles" in _now["canary"])


asyncio.run(_go())

# ---- 5. Giao diện phải thật sự vẽ ba nút đó ----
# Backend đúng mà giao diện không dùng thì y như không có - đã dính đúng lỗi này với
# tpm_window một lần rồi.
_console = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("giao diện có dùng danh sách mức", "d.presets" in _console)
check("giao diện tô đậm mức đang dùng", "d.preset" in _console)
check("có gắn sự kiện bấm mức", "_bindPresets" in _console)
check("bấm xong có phản hồi nhìn thấy được (không im lặng như bản cũ)",
      "_rtToast" in _console)
check("bảng canary thô đã gập vào phần Nâng cao", "rt-adv" in _console)
check("tên trang không còn chung chung là 'Chẩn đoán'",
      '"Chẩn đoán"' not in _console)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_runtime_preset: tất cả pass")
