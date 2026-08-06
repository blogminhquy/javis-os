"""Đổi mặc định mức tiết kiệm phải TỚI ĐƯỢC máy đã cài, và không giẫm lên ai đã tự chọn.

    python tests/run.py muc_mac_dinh

Cái bẫy file này canh. `write_settings` ghi lại TOÀN BỘ config đã trộn, nên ngay lần đầu
người dùng bấm bất cứ nút nào, giá trị mặc định của NGÀY HÔM ĐÓ bị đóng băng vào
settings.json; `read_settings` lại trộn file ĐÈ LÊN mặc định. Hệ quả: sau này nâng mặc định
lên mức Tối ưu hay Siêu tiết kiệm thì máy đã cài rồi không bao giờ thấy - mặc định mới chỉ
tới được máy cài mới tinh. Đúng con bệnh đã cắn `provider_kinds` hồi 0.12.4, lần này rơi vào
thứ quyết định mỗi lượt chat tốn bao nhiêu token.

Vì sao cần chữ ký chứ không nâng đại: số 0 trong file có HAI nghĩa - "cố ý chọn Tắt" và
"chưa ai chọn gì". Nên mọi endpoint đổi mức đều đóng dấu `preset_choice.source = "user"`, và
có dấu thì bản cập nhật không đụng vào.

Test ở đây GIẢ LẬP việc nâng mặc định (đổi `cfg.PRESET_MAC_DINH` rồi đọc lại) thay vì chờ
tới ngày thật sự nâng. Một cơ chế di trú chỉ chạy đúng một lần trong đời mà không có test thì
tới hôm dùng mới biết nó hỏng, và lúc đó thì đã phát ra cho người dùng rồi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-macdinh-")

import config as cfg  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _ghi(raw: dict):
    """Ghi settings.json THÔ (không qua write_settings) rồi xoá cache đọc.

    Phải xoá cache bằng tay: `read_settings` nhớ theo (mtime, size) của file, mà test đổi
    `PRESET_MAC_DINH` trong bộ nhớ chứ không đụng file - cache hit sẽ trả về bản đã tính
    bằng mặc định CŨ và test thành ra đo cái bóng của chính nó.
    """
    cfg.SETTINGS_PATH.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    cfg._SETTINGS_CACHE["sig"] = None
    cfg._SETTINGS_CACHE["cfg"] = None


def _doc_voi_mac_dinh(muc: str) -> dict:
    """Đọc settings như thể bản đang chạy có mức xuất xưởng là `muc`."""
    cu = cfg.PRESET_MAC_DINH
    cfg.PRESET_MAC_DINH = muc
    cfg._SETTINGS_CACHE["sig"] = None
    try:
        return cfg.read_settings().get("context_runtime") or {}
    finally:
        cfg.PRESET_MAC_DINH = cu
        cfg._SETTINGS_CACHE["sig"] = None


def _bp(rt: dict, ten: str) -> int:
    return int(((rt.get(ten) or {}).get("allocation_basis_points")) or 0)


# Máy cài từ lâu: settings.json đã đóng băng mặc định của ngày hôm đó (mọi đường 0, mode
# shadow) và KHÔNG có chữ ký nào, vì hồi đó chưa có khái niệm chữ ký.
MAY_CU = {
    "context_runtime": {
        "mode": "shadow",
        "canary": {"allocation_basis_points": 0, "provider_kinds": ["api"]},
        "conversation_state_canary": {"allocation_basis_points": 0},
        "memory_canary": {"allocation_basis_points": 0},
        "lazy_skill_canary": {"allocation_basis_points": 0},
    }
}

# ---- 1. Một nguồn sự thật cho bảng mức ----
check("bảng mức nằm ở config, main không chép lại",
      set(cfg.PRESET_DUONG) == set(main.RUNTIME_PRESETS))
for _k in cfg.PRESET_DUONG:
    check(f"mức '{_k}': main dùng đúng bảng của config",
          main.RUNTIME_PRESETS[_k]["duong"] == cfg.PRESET_DUONG[_k]["duong"]
          and main.RUNTIME_PRESETS[_k]["mode"] == cfg.PRESET_DUONG[_k]["mode"])
_keys = main._canary_keys()
for _k, _p in cfg.PRESET_DUONG.items():
    for _d in _p["duong"]:
        check(f"mức '{_k}' trỏ vào đường có thật: {_d}", _d in _keys)
check("mức xuất xưởng phải là một mức có thật", cfg.PRESET_MAC_DINH in cfg.PRESET_DUONG)

# ---- 2. Máy CÀI MỚI ăn đúng mức xuất xưởng ----
try:
    cfg.SETTINGS_PATH.unlink()
except OSError:
    pass
cfg._SETTINGS_CACHE["sig"] = None
check("máy mới tinh chạy đúng mức xuất xưởng của bản này",
      main.current_preset(cfg.read_settings().get("context_runtime") or {})
      == cfg.PRESET_MAC_DINH)

# ---- 3. Máy CŨ cũng phải ăn được mặc định mới. Đây là cái bẫy chính ----
_ghi(MAY_CU)
_rt = _doc_voi_mac_dinh("max")
check("máy cũ đóng băng mặc định vẫn được nâng lên mức mới",
      main.current_preset(_rt) == "max")
check("công tắc trùm được nâng theo, không để knob xoay mà đèn không sáng",
      _rt.get("mode") == "canary")
for _d in cfg.PRESET_DUONG["max"]["duong"]:
    check(f"máy cũ: '{_d}' đã bật thật", _bp(_rt, _d) == 10000)

_ghi(MAY_CU)
_rt = _doc_voi_mac_dinh("saving")
check("nâng mặc định lên Tối ưu thì máy cũ được đúng ba đường của Tối ưu",
      main.current_preset(_rt) == "saving")
check("Tối ưu KHÔNG kéo theo đường tắt", _bp(_rt, "canary") == 0)

# Mức xuất xưởng THẬT của bản đang build, đo qua đường đọc bình thường chứ không giả lập.
# Từ 0.24.7 là "max": máy đã cài từ lâu, chưa từng tự chọn mức, mở lên là đã ở Siêu tiết
# kiệm. Đây là điểm khác biệt lớn nhất của bản này với mọi bản trước, nên nó phải có một
# phép thử đọc thẳng `PRESET_MAC_DINH` - đổi lại "off" mà quên chỗ khác thì đỏ ngay.
_ghi(MAY_CU)
check(f"mức xuất xưởng của bản NÀY là '{cfg.PRESET_MAC_DINH}', và máy cũ ăn được nó",
      main.current_preset(cfg.read_settings().get("context_runtime") or {})
      == cfg.PRESET_MAC_DINH)
check("CANARY: bản này xuất xưởng ở mức Siêu tiết kiệm", cfg.PRESET_MAC_DINH == "max")

# Mức không bật đường nào thì không có lý do gì đụng tới công tắc trùm - công tắc đó dùng
# chung với các phase khác (readonly, orchestrator, write).
_may_tat_han = json.loads(json.dumps(MAY_CU))
_may_tat_han["context_runtime"]["mode"] = "off"
_ghi(_may_tat_han)
_rt = _doc_voi_mac_dinh("off")
check("mức Tắt không tự kéo công tắc trùm của ai lên", _rt.get("mode") == "off")

# ---- 4. Có chữ ký thì không ai được đụng vào ----
_da_chon_tat = json.loads(json.dumps(MAY_CU))
_da_chon_tat["context_runtime"]["preset_choice"] = {
    "level": "off", "source": "user", "at": "2026-08-03T00:00:00+00:00"}
_ghi(_da_chon_tat)
_rt = _doc_voi_mac_dinh("max")
check("người đã cố ý chọn Tắt thì bản cập nhật KHÔNG bật lại",
      main.current_preset(_rt) == "off")
check("mode cũng giữ nguyên khi đã có chữ ký", _rt.get("mode") == "shadow")

_da_chon_saving = json.loads(json.dumps(MAY_CU))
_da_chon_saving["context_runtime"]["mode"] = "canary"
for _d in cfg.PRESET_DUONG["saving"]["duong"]:
    _da_chon_saving["context_runtime"][_d] = {"allocation_basis_points": 10000}
_da_chon_saving["context_runtime"]["preset_choice"] = {
    "level": "saving", "source": "user", "at": "2026-08-03T00:00:00+00:00"}
_ghi(_da_chon_saving)
_rt = _doc_voi_mac_dinh("max")
check("người đã chọn Tối ưu thì không bị đẩy lên Siêu tiết kiệm",
      main.current_preset(_rt) == "saving")

# ---- 5. CHỈ NÂNG, KHÔNG BAO GIỜ HẠ ----
_may_cao = json.loads(json.dumps(MAY_CU))
_may_cao["context_runtime"]["mode"] = "canary"
for _d in cfg.PRESET_DUONG["max"]["duong"]:
    _may_cao["context_runtime"][_d] = {"allocation_basis_points": 10000}
_ghi(_may_cao)          # sửa tay settings.json: không có chữ ký nào cả
_rt = _doc_voi_mac_dinh("saving")
check("máy đang cao hơn mặc định thì không bị hạ xuống",
      main.current_preset(_rt) == "max")
check("đường tắt sửa tay vẫn còn nguyên", _bp(_rt, "canary") == 10000)
_rt = _doc_voi_mac_dinh("off")
check("mặc định Tắt cũng không tắt đồ của người ta", main.current_preset(_rt) == "max")

# Ba mức hiện tại đều bật 100% (10000 basis point) nên không mức nào HẠ được ai - tức là
# luật "chỉ nâng" chưa có cơ hội chứng minh mình đúng qua đường settings. Gọi thẳng hàm với
# một mức giả bật một phần: ngày nào đó có mức rollout 30% thì luật này mới lộ ra, mà lúc đó
# thì test phải sẵn sàng từ trước rồi.
_gia = {"mode": "shadow", "duong": {"memory_canary": 3000}}
cfg.PRESET_DUONG["_thu_nghiem"] = _gia
_cu_md = cfg.PRESET_MAC_DINH
cfg.PRESET_MAC_DINH = "_thu_nghiem"
try:
    _cf = {"context_runtime": {"mode": "on",
                               "memory_canary": {"allocation_basis_points": 10000}}}
    cfg._ap_muc_mac_dinh(_cf)
    check("mức mặc định bật một phần KHÔNG kéo tụt máy đang bật đủ",
          _bp(_cf["context_runtime"], "memory_canary") == 10000)
    check("mode mạnh hơn mặc định cũng không bị hạ",
          _cf["context_runtime"]["mode"] == "on")
    _cf = {"context_runtime": {"mode": "shadow",
                               "memory_canary": {"allocation_basis_points": 0}}}
    cfg._ap_muc_mac_dinh(_cf)
    check("còn máy đang thấp hơn thì vẫn được nâng lên đúng phần đó",
          _bp(_cf["context_runtime"], "memory_canary") == 3000)
finally:
    cfg.PRESET_MAC_DINH = _cu_md
    cfg.PRESET_DUONG.pop("_thu_nghiem", None)

# ---- 6. Endpoint nào đổi mức cũng phải ký tên ----
def _lam_moi():
    """Về máy chưa ai chọn gì. Mỗi endpoint phải được đo trên nền sạch: đo nối đuôi nhau thì
    chữ ký của endpoint TRƯỚC còn nằm đó và endpoint sau quên ký vẫn qua bài."""
    try:
        cfg.SETTINGS_PATH.unlink()
    except OSError:
        pass
    cfg._SETTINGS_CACHE["sig"] = None


def _chu_ky() -> dict:
    return (cfg.read_settings().get("context_runtime") or {}).get("preset_choice") or {}


async def _go():
    _lam_moi()
    check("nền sạch thì chưa có chữ ký nào", _chu_ky().get("source") != "user")

    r = await main.runtime_preset_set(level="saving")
    check("bấm mức → ok", isinstance(r, dict) and r.get("ok"))
    _c = _chu_ky()
    check("bấm mức để lại chữ ký", _c.get("source") == "user")
    check("chữ ký nhớ đúng mức đã bấm", _c.get("level") == "saving")
    check("chữ ký có mốc thời gian", bool(_c.get("at")))

    # Bấm rồi thì bản cập nhật sau không được nâng nữa, kể cả nâng lên mức cao hơn.
    _rt = _doc_voi_mac_dinh("max")
    check("sau khi bấm, mặc định mới không đụng vào nữa",
          main.current_preset(_rt) == "saving")

    # Công tắc trùm: hạ về shadow là cố ý tắt hết, phải được tôn trọng y như bấm Tắt.
    #
    # Đo bằng "KHÔNG ĐỔI so với ngay sau khi ký", không phải bằng số 0 gõ cứng. Nền sạch
    # không còn là toàn số 0 từ khi mức xuất xưởng là một mức thật (0.24.7), và một fixture
    # ghim số 0 thì hoá đỏ ngay lúc đổi mặc định - trong khi thứ nó định kiểm (cập nhật
    # không giẫm lên người đã ký) vẫn đúng nguyên. Đúng cái bẫy đã cắn
    # test_cauhinh_cu_khong_ket một lần rồi.
    _lam_moi()
    await main.runtime_mode_set(mode="shadow")
    check("đổi công tắc trùm cũng ký tên", _chu_ky().get("source") == "user")
    _truoc = _bp(cfg.read_settings().get("context_runtime") or {}, "memory_canary")
    _rt = _doc_voi_mac_dinh("max")
    check("hạ mode về shadow rồi thì cập nhật không kéo lên lại",
          _rt.get("mode") == "shadow" and _bp(_rt, "memory_canary") == _truoc)

    # Chỉnh tay một đường ở phần Nâng cao cũng là có ý kiến riêng.
    _lam_moi()
    r = await main.runtime_canary_set(path="memory_canary",
                                      allocation_basis_points=5000, allow_inert=True)
    check("chỉnh tay một đường → ok", isinstance(r, dict) and r.get("ok"))
    check("chỉnh tay một đường cũng ký tên", _chu_ky().get("source") == "user")
    _canary_truoc = _bp(cfg.read_settings().get("context_runtime") or {}, "canary")
    _rt = _doc_voi_mac_dinh("max")
    check("cấu hình chỉnh tay không bị cập nhật ghi đè",
          _bp(_rt, "memory_canary") == 5000 and _bp(_rt, "canary") == _canary_truoc)

asyncio.run(_go())

# ---- 7. Người dùng phải THẤY mình đang ở mặc định hay ở lựa chọn của mình ----
# Khối chọn mức nằm ở đầu trang Mức dùng từ 0.24.7 (trước đó là một trang riêng trong rail).
_usage = (ROOT / "dashboard" / "usage.js").read_text(encoding="utf-8")
check("giao diện đọc nguồn của mức đang chạy", "d.tu_chon" in _usage)
check("giao diện nói rõ khi mức chỉ là mặc định",
      "mặc định của bản này" in _usage and "chưa tự chọn bao giờ" in _usage)
_src_main = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("máy chủ trả nguồn của mức cho giao diện",
      '"tu_chon"' in _src_main and '"preset_nguon"' in _src_main)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_muc_mac_dinh: tất cả pass")
