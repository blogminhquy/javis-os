"""Merge cấu hình ĐỆ QUY + endpoint đặt canary an toàn.

    python tests/run.py settings_merge

Vì sao file này tồn tại: `read_settings()` từng gộp cấu hình người dùng lên mặc định bằng
`.update()` MỘT TẦNG, trong khi knob quan trọng nằm sâu HAI tầng
(`context_runtime.canary.allocation_basis_points`). Ghi tay đúng một trường là thay thế trọn
sub-dict, làm `quota_profiles` biến mất; mà fail-closed nói thiếu quota thì rơi về legacy.
Kết quả: bật canary lên rồi ngồi đợi một thứ không bao giờ chạy, im lặng, không lỗi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-merge-")

import config as cfg  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _write(data):
    """Ghi settings.json THÔ, kèm chữ ký "người dùng đã tự chọn mức".

    Chữ ký đó không phải chi tiết vặt. Từ 0.24.7 mức xuất xưởng là Siêu tiết kiệm, nên
    `read_settings` tự NÂNG allocation của máy chưa từng chọn mức lên 10000 (xem
    `config._ap_muc_mac_dinh`). File này đo chuyện khác hẳn - `_deep_merge` có giữ được
    field anh em không - nên nếu để cơ chế nâng mặc định chạy vào thì mọi con số ghi ở đây
    đều bị viết đè, và test đỏ vì một lý do chẳng liên quan gì tới thứ nó kiểm.
    """
    data = json.loads(json.dumps(data))
    rt = data.setdefault("context_runtime", {})
    rt.setdefault("preset_choice", {"level": "off", "source": "user", "at": "2026-01-01T00:00:00+00:00"})
    cfg.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    # Đẩy mốc thời gian lùi lại một chút sau mỗi lần ghi.
    #
    # `read_settings` cache theo (mtime_ns, size). Test này ghi hai nội dung CÙNG ĐỘ DÀI liên
    # tiếp (allocation 100 rồi 250), nên nếu hệ tệp trả cùng một mtime_ns thì lần đọc thứ hai
    # trúng cache cũ và phép kiểm hot reload đỏ oan. Đo được: đỏ ngẫu nhiên khoảng 1 trên 3
    # lượt, trên cả cây sạch từ origin/main.
    #
    # Đây là giới hạn THẬT của cách cache chứ không riêng của test: người dùng sửa tay hai lần
    # trong cùng một nhịp đồng hồ, giữ nguyên độ dài, cũng trượt y hệt. Không siết cache bằng
    # hash nội dung vì `read_settings` nằm trên đường nóng của mọi lượt chat; đổi lại thì ghi
    # rõ giới hạn ra đây.
    import os as _os
    _write.lan = getattr(_write, "lan", 0) + 1
    _t = 1_600_000_000 + _write.lan * 60      # mỗi lần ghi một mốc KHÁC HẲN, không phụ thuộc đồng hồ
    _os.utime(cfg.SETTINGS_PATH, (_t, _t))


# ---- 1. _deep_merge thuần ----
check("_deep_merge: gộp sâu, giữ field anh em",
      cfg._deep_merge({"a": {"b": {"x": 1, "y": 2}}}, {"a": {"b": {"x": 9}}})
      == {"a": {"b": {"x": 9, "y": 2}}})
check("_deep_merge: giữ nhánh anh em cùng cấp",
      cfg._deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 9}}) == {"a": {"b": 9, "c": 2}})
check("_deep_merge: kiểu khác nhau thì THAY, không gộp",
      cfg._deep_merge({"a": {"b": 1}}, {"a": "chuỗi"}) == {"a": "chuỗi"})
check("_deep_merge: list THAY chứ không nối (luật trùng là ý sai)",
      cfg._deep_merge({"a": [1, 2]}, {"a": [3]}) == {"a": [3]})
check("_deep_merge: patch rỗng không đụng gì", cfg._deep_merge({"a": 1}, {}) == {"a": 1})
check("_deep_merge: patch None không nổ", cfg._deep_merge({"a": 1}, None) == {"a": 1})

# ---- 2. Đúng cái bẫy đã tìm ra, kiểm qua read_settings thật ----
_write({"context_runtime": {"canary": {"allocation_basis_points": 100}}})
_rt = cfg.read_settings()["context_runtime"]
_c = _rt["canary"]
check("bẫy đã chết: ghi 1 field không làm mất quota_profiles",
      "quota_profiles" in _c)
check("bẫy đã chết: ghi 1 field không làm mất salt/channels",
      "salt" in _c and "channels" in _c)
check("bẫy đã chết: policy_version của canary còn nguyên", bool(_c.get("policy_version")))
# readonly_canary CÓ capability_profiles (fast path thì không, vì nó không gọi tool)
check("bẫy đã chết: canary có allowlist thì allowlist cũng còn",
      "capability_profiles" in cfg.read_settings()["context_runtime"]["readonly_canary"])
check("giá trị mới vẫn ăn", _c.get("allocation_basis_points") == 100)
check("nhánh anh em cùng cấp (mode) còn nguyên", _rt.get("mode") == "shadow")
check("canary KHÁC không bị đụng tới",
      _rt.get("readonly_canary", {}).get("allocation_basis_points") == 0)

# ---- 3. Hot reload: sửa file là ăn ngay, không cần restart ----
# Đây là tính chất làm cho rollback một canary trở thành tức thì. Nếu nó hỏng thì mọi quy
# trình triển khai dựa trên "đặt về 0 là xong" đều sai.
_write({"context_runtime": {"canary": {"allocation_basis_points": 250}}})
check("sửa settings.json ăn ngay, không cần restart",
      cfg.read_settings()["context_runtime"]["canary"]["allocation_basis_points"] == 250)

# ---- 4. Endpoint đặt canary ----
os.environ.setdefault("JAVIS_SKIP_HEAVY_IMPORT", "1")
import main  # noqa: E402

check("_canary_keys lấy từ _DEFAULT, phủ đủ 10 đường",
      len(main._canary_keys()) == 10 and "write_canary" in main._canary_keys())

# Khoá hai chiều: mọi key _canary_keys trả về phải là dict có allocation trong _DEFAULT.
_default_rt = cfg._DEFAULT["context_runtime"]
for _k in main._canary_keys():
    check(f"_canary_keys '{_k}' trỏ đúng một đường có thật",
          isinstance(_default_rt.get(_k), dict)
          and "allocation_basis_points" in _default_rt[_k])

# Entry CÓ trường quota_profiles nhưng RỖNG = khai thiếu thật → phải cảnh báo.
check("_canary_inert_reason: có trường quota nhưng rỗng → nêu lý do",
      "quota" in main._canary_inert_reason({"quota_profiles": [],
                                            "capability_profiles": ["x"]}))
check("_canary_inert_reason: có quota nhưng allowlist RỖNG → nêu lý do",
      "allowlist" in main._canary_inert_reason({"quota_profiles": [{"a": 1}],
                                                "capability_profiles": []}))
check("_canary_inert_reason: đủ cả hai → không cản",
      main._canary_inert_reason({"quota_profiles": [{"a": 1}],
                                 "capability_profiles": ["x"]}) == "")
# Fast path KHÔNG có capability_profiles vì nó không gọi tool. Đòi trường đó ở đây là từ
# chối oan một cấu hình hợp lệ, nên chỉ soát trường mà đường đó thật sự có.
check("_canary_inert_reason: đường không có allowlist thì không đòi allowlist",
      main._canary_inert_reason({"quota_profiles": [{"a": 1}]}) == "")
# Ba canary Phase 8 không có quota_profiles riêng, chúng đọc ké từ context_sources/canary.
# Rào bản đầu chặn cả ba với lý do SAI ("chưa khai quota") - phát hiện khi bản deploy thật
# vẫn lỗi hạn mức. Lý do sai còn khó hiểu hơn là không chặn.
for _k in ("memory_canary", "lazy_skill_canary", "conversation_state_canary"):
    _entry = dict(cfg._DEFAULT["context_runtime"][_k])
    _st2, _pl2 = main.canary_set_decision(_k, 10000, _entry, False, mode="canary")
    check(f"'{_k}' bật được, không bị đòi quota mà nó không có", _st2 == 0)

# ---- 5. Hàm quyết định (THUẦN) - đây mới là hàng rào thật ----
_EMPTY = {"quota_profiles": [], "capability_profiles": []}
_READY = {"quota_profiles": [{"model": "m", "rolling_tpm": 12000}],
          "capability_profiles": ["x"]}

_st, _pl = main.canary_set_decision("khong_co_that", 100, _READY, False)
check("quyết định: tên đường sai → 400", _st == 400)

_st, _pl = main.canary_set_decision("canary", 99999, _READY, False)
check("quyết định: allocation ngoài 0..10000 → 400", _st == 400)
_st, _pl = main.canary_set_decision("canary", -1, _READY, False)
check("quyết định: allocation âm → 400", _st == 400)
_st, _pl = main.canary_set_decision("canary", "abc", _READY, False)
check("quyết định: allocation không phải số → 400", _st == 400)

# `mode` là điều kiện TRÙM: mọi canary đòi mode canary/on. Bản đầu của rào này soát quota mà
# QUÊN mode, nên nó để lọt đúng kiểu hỏng nó sinh ra để chặn - endpoint trả ok mà không có gì
# chạy. Phát hiện khi bản deploy thật vẫn lỗi hạn mức dù đã bật.
_st, _pl = main.canary_set_decision("canary", 100, _READY, False, mode="shadow")
check("quyết định: mode còn shadow → chặn 409 dù quota đã khai đủ", _st == 409)
check("quyết định: nêu đúng nguyên nhân là mode", "mode" in _pl.get("error", ""))
_st, _pl = main.canary_set_decision("canary", 100, _READY, False, mode="off")
check("quyết định: mode off cũng chặn", _st == 409)
_st, _pl = main.canary_set_decision("canary", 100, _READY, False, mode="on")
check("quyết định: mode on thì cho qua", _st == 0)
_st, _pl = main.canary_set_decision("canary", 0, _READY, False, mode="shadow")
check("quyết định: tắt về 0 không bị mode chặn", _st == 0)

_st, _pl = main.canary_set_decision("canary", 100, _EMPTY, False)
check("quyết định: bật đường sẽ fail-closed → chặn 409", _st == 409)
check("quyết định: chặn kèm can_force để user còn quyết", _pl.get("can_force") is True)
check("quyết định: nêu ĐÚNG lý do (quota) chứ không nói chung chung",
      "quota" in _pl.get("error", ""))

_st, _pl = main.canary_set_decision("canary", 100, _EMPTY, True)
check("quyết định: allow_inert=true thì cho qua", _st == 0 and _pl.get("ok"))

_st, _pl = main.canary_set_decision("canary", 100, _READY, False)
check("quyết định: khai đủ quota rồi thì bật thẳng, không cần ép", _st == 0)

# Đường lui phải RẺ HƠN đường tiến, nếu không người vận hành sẽ ngại thử.
_st, _pl = main.canary_set_decision("canary", 0, _EMPTY, False)
check("quyết định: tắt về 0 luôn được phép, kể cả khi cấu hình còn thiếu", _st == 0)


async def _endpoint_tests():
    """Endpoint chỉ còn là lớp vỏ: đọc settings, hỏi hàm quyết định, ghi. Kiểm phần GHI."""
    r = await main.runtime_canary_set(path="canary", allocation_basis_points=100,
                                      allow_inert=True)
    check("endpoint: ghi được khi quyết định cho phép", isinstance(r, dict) and r.get("ok"))
    check("endpoint: giá trị đã vào settings thật",
          cfg.read_settings()["context_runtime"]["canary"]["allocation_basis_points"] == 100)
    check("endpoint: ghi xong KHÔNG làm mất quota_profiles",
          "quota_profiles" in cfg.read_settings()["context_runtime"]["canary"])
    check("endpoint: ghi xong KHÔNG đụng canary khác",
          cfg.read_settings()["context_runtime"]["readonly_canary"]
          ["allocation_basis_points"] == 0)

    r = await main.runtime_canary_set(path="canary", allocation_basis_points=0)
    check("endpoint: tắt rồi thì settings về 0",
          cfg.read_settings()["context_runtime"]["canary"]["allocation_basis_points"] == 0)

    r = await main.runtime_canary_set(path="khong_co_that", allocation_basis_points=100)
    check("endpoint: quyết định từ chối thì trả đúng status",
          getattr(r, "status_code", 0) == 400)


import asyncio  # noqa: E402

asyncio.run(_endpoint_tests())

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_settings_merge: tất cả pass")
