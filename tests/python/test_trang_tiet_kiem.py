"""Trang Tiết kiệm token phải nói được nó tiết kiệm BAO NHIÊU, và lượt chat đi đường nào.

    python tests/run.py trang_tiet_kiem

Yêu cầu chủ repo: đổi tên ba mức thành Tắt / Tối ưu / Siêu tiết kiệm, đặt lên đầu trang, và
"bộ đếm thì sẽ ghi tiết kiệm được bao nhiêu % khi tối ưu, khi bật mode siêu tiết kiệm".

Vì sao đây không phải chuyện trang trí: ba nút mà không nói được chúng đổi gì thì bấm cũng
như không, và đó đúng là lời chê "không hiểu trang này và không biết sử dụng như nào". Tệ hơn
nữa, trước bản này KHÔNG có cách nào biết một lượt đã đi đường tiết kiệm hay lặng lẽ tụt về
đường cũ - phải đợi tới lúc nhà cung cấp báo vượt hạn mức mới lộ ra, mà lúc đó thì đã muộn.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-tk-")

import config as cfg  # noqa: E402
import context_runtime  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_CONSOLE = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
_APP = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
_MAIN = (ROOT / "server" / "main.py").read_text(encoding="utf-8")

# ============================================================
# 1. Tên ba mức
# ============================================================
_nhan = {k: v["nhan"] for k, v in main.RUNTIME_PRESETS.items()}
check("mức off tên là 'Tắt'", _nhan.get("off") == "Tắt")
check("mức saving tên là 'Tối ưu'", _nhan.get("saving") == "Tối ưu")
check("mức max tên là 'Siêu tiết kiệm'", _nhan.get("max") == "Siêu tiết kiệm")
check("CANARY: không còn tên cũ 'Tiết kiệm' cho mức giữa", "Tiết kiệm" not in _nhan.values())
check("CANARY: không còn tên cũ 'Tối đa'", "Tối đa" not in _nhan.values())

# ============================================================
# 2. Ba mức nằm ở ĐẦU trang
# ============================================================
# Chôn ba nút ở giữa trang, dưới bốn khối biểu đồ, là mở trang ra thấy số liệu trước khi thấy
# cái nút cần bấm.
_i_preset = _CONSOLE.find('<h3>Chọn mức tiết kiệm</h3>')
_i_banner = _CONSOLE.find('class="rt-banner')
_i_grid = _CONSOLE.find('<div class="rt-grid">')
check("có khối chọn mức", _i_preset != -1)
check("CANARY: khối chọn mức đứng TRƯỚC dải trạng thái", 0 < _i_preset < _i_banner)
check("CANARY: và đứng trước các khối số liệu", 0 < _i_preset < _i_grid)
check("khối cũ ở giữa trang đã gỡ", _CONSOLE.count("<h3>Mức tiết kiệm</h3>") == 0)

# ============================================================
# 3. Mỗi mức ghi rõ tiết kiệm bao nhiêu phần trăm
# ============================================================
_uoc = asyncio.run(main._uoc_tinh_tiet_kiem("brain"))
check("API trả về bảng ước tính", isinstance(_uoc, dict) and "muc" in _uoc)
_muc = _uoc.get("muc") or {}
for _k in ("off", "saving", "max"):
    check(f"có số cho mức '{_k}'", _k in _muc and "phan_tram" in _muc[_k])
check("mức Tắt là mốc 0 phần trăm", _muc.get("off", {}).get("phan_tram") == 0)
# Thứ tự phải đúng: càng tiết kiệm càng ít token. Đảo là con số vô nghĩa.
check("CANARY: Tối ưu tốn ít token hơn Tắt",
      _muc["saving"]["token_moi_request"] < _muc["off"]["token_moi_request"])
# "Siêu tiết kiệm" hơn "Tối ưu" ở đúng một thứ: đường tắt cho câu hỏi đơn giản. Đường đó
# nằm trong nhánh engine API của _do_turn và provider_kinds của nó cũng chỉ có "api", nên
# bộ não gói thuê bao KHÔNG ăn phần này - với họ hai mức bằng nhau. Con số phải nói đúng
# chuyện đó thay vì khoe 96% cho một người sẽ không bao giờ chạm tới nó.
# Đường tắt mở cho bộ não nào là do CẤU HÌNH quyết, không phải một danh sách gõ cứng ở
# đây: 0.14.0 mở thêm gói ChatGPT, và một hằng số trong test sẽ lặng lẽ kiểm sai từ đó.
_kinds_tat = ((main.cfgmod.read_settings().get("context_runtime") or {}).get("canary") or {}
              ).get("provider_kinds") or ["api"]
_fast_hop = _uoc.get("kind_bo_nao") in _kinds_tat
check("có khai bộ não đang chạy thuộc loại nào", bool(_uoc.get("kind_bo_nao")))
check("mỗi mức khai rõ bộ não này có ăn được không",
      all("ap_dung" in _muc[k] for k in ("off", "saving", "max")))
if _fast_hop:
    check("CANARY: bộ não API key thì Siêu tiết kiệm tốn ít hơn Tối ưu",
          _muc["max"]["token_moi_request"] < _muc["saving"]["token_moi_request"])
    check("và mức đó được đánh dấu là áp dụng được", _muc["max"]["ap_dung"] is True)
else:
    check("CANARY: bộ não thuê bao thì Siêu tiết kiệm KHÔNG được khoe thấp hơn Tối ưu",
          _muc["max"]["token_moi_request"] == _muc["saving"]["token_moi_request"])
    check("và mức đó bị đánh dấu là không áp dụng", _muc["max"]["ap_dung"] is False)
    check("kèm câu giải thích vì sao", "chưa mở" in (_muc["max"].get("ghi_chu") or ""))
check("phần trăm tăng dần theo mức",
      _muc["off"]["phan_tram"] < _muc["saving"]["phan_tram"] <= _muc["max"]["phan_tram"])
check("phần trăm nằm trong khoảng đọc được",
      all(0 <= _muc[k]["phan_tram"] <= 99 for k in _muc))
check("mỗi mức có một câu nói nó đánh đổi gì",
      all(len(_muc[k].get("ghi_chu") or "") > 20 for k in _muc))

# Con số phải đo trên prompt THẬT, không phải hằng số gõ tay - nếu không thì brain nào cũng
# ra cùng một con số, và con số đó sai với gần hết mọi người.
_that = len(main.build_system_prompt("brain")
            + main.channel_context.build_channel_block(
                "dashboard", {"session_id": "uoc-tinh"}, telegram_running=False,
                port=main._javis_port(), brain_root=main._brain_root("brain")))
_ti_le = _uoc.get("chu_ky_ky_tu_tren_token") or 3.0
check("CANARY: con số đo trên prompt THẬT của brain, không phải hằng số gõ tay",
      abs((_uoc.get("chi_tiet") or {}).get("claude_md_va_bo_nho", 0) - _that / _ti_le) <= 2)
check("và tính bằng ĐÚNG hệ số ký tự-trên-token của runtime",
      "estimate_chars_per_token" in _MAIN.split("async def _uoc_tinh_tiet_kiem(")[1][:2600])
check("có chi tiết để đối chiếu, không chỉ một con số trơ",
      set(_uoc.get("chi_tiet") or {}) >= {"claude_md_va_bo_nho", "capsule", "mo_ta_cong_cu"})
# Nói rõ là ƯỚC LƯỢNG. Trình bày một ước lượng như số đo là hứa thứ không giữ được.
check("CANARY: tự khai đây là ước lượng", _uoc.get("la_uoc_luong") is True)
check("giao diện có nói ra chữ 'ước lượng'", "ước lượng" in _CONSOLE)

# Khai hỏng thì trả rỗng chứ không nổ giữa trang.
check("brain không tồn tại vẫn không nổ",
      isinstance(asyncio.run(main._uoc_tinh_tiet_kiem("brain-khong-co-that")), dict))
check("tham số sai kiểu vẫn không nổ (gọi thẳng hàm endpoint)",
      isinstance(asyncio.run(main._uoc_tinh_tiet_kiem(None)), dict))

# Giao diện phải THẬT SỰ vẽ con số đó ra.
_nut = _CONSOLE[_CONSOLE.find('data-preset="${esc(p.id)}"'):][:520]
check("CANARY: nút mức GỌI hàm dựng phần trăm (không chỉ có định nghĩa)",
      "${presetPct(p.id)}" in _nut)
check("CANARY: và gọi hàm dựng token mỗi lượt", "${presetTok(p.id)}" in _nut)
check("có CSS cho hai thứ đó", "rt-pct" in _CONSOLE and "rt-pertok" in _CONSOLE)
check("giao diện đọc đúng trường API trả về", "d.uoc_tinh" in _CONSOLE)

# ============================================================
# 4. Số ĐO ĐƯỢC từ lượt thật, tách hẳn khỏi ước lượng
# ============================================================
_do = main._do_duoc_tiet_kiem([])
check("chưa có lượt nào → nói rõ chưa đủ dữ liệu", _do["du_du_lieu"] is False)
check("và KHÔNG hiện 0% một cách vô nghĩa", _do["phan_tram"] == 0 and _do["so_luot_cu"] == 0)

_tasks = [
    {"execution_path": "legacy", "actual_input_tokens": 10000},
    {"execution_path": "legacy", "actual_input_tokens": 9000},
    {"execution_path": "unassigned", "actual_input_tokens": 11000},   # gộp vào đường cũ
    {"execution_path": "sources", "actual_input_tokens": 1000},
    {"execution_path": "fast", "actual_input_tokens": 500},
    {"execution_path": "sources", "actual_input_tokens": 0},          # bỏ, không có số
]
_do = main._do_duoc_tiet_kiem(_tasks)
check("đủ hai đường → đo được", _do["du_du_lieu"] is True)
check("đếm đúng số lượt đường cũ (gộp cả unassigned)", _do["so_luot_cu"] == 3)
check("đếm đúng số lượt đường tiết kiệm", _do["so_luot_moi"] == 2)
check("trung bình đường cũ đúng", _do["tb_cu"] == 10000)
check("trung bình đường mới đúng", _do["tb_moi"] == 750)
# 1 - 750/10000 = 92,5%. round() của Python làm tròn về SỐ CHẴN ở đúng mốc .5 nên ra 92.
# Ghi đúng cái nó làm thay vì sửa code cho khớp kỳ vọng: chênh nửa phần trăm ở một con
# số hiển thị không đáng đổi lấy một chỗ làm tròn khác với phần còn lại của Python.
check("phần trăm giảm đúng", _do["phan_tram"] == 92)
# Lượt không có số token thì bỏ, đừng kéo trung bình xuống 0 rồi khoe tiết kiệm 100%.
check("CANARY: lượt thiếu số token bị bỏ, không thổi phồng con số",
      _do["so_luot_moi"] == 2 and _do["tb_moi"] > 0)
check("giao diện có vẽ bảng đo thật", "rt-doduoc" in _CONSOLE and "d.do_duoc" in _CONSOLE)
check("và nói rõ đây là số THẬT chứ không phải ước lượng", "không phải ước lượng" in _CONSOLE)

# ============================================================
# 5. Đường tiết kiệm phải có TÊN RIÊNG trong trace
# ============================================================
# Không có tên riêng thì mọi lượt đi đường tiết kiệm vẫn bị ghi là "legacy", và cả trang này
# lẫn bảng đo ở trên đều mù.
_src_rt = (ROOT / "server" / "context_runtime.py").read_text(encoding="utf-8")
check("CANARY: runtime chấp nhận đường 'sources'",
      '"workflow", "sources"' in _src_rt or '"sources", "workflow"' in _src_rt)
_src_acr = (ROOT / "server" / "adaptive_context_runtime.py").read_text(encoding="utf-8")
check("CANARY: Phase 8 thật sự GHIM tên đường đó",
      'pin_execution_path(\n                    trace, "sources"' in _src_acr)
check("ghim hỏng thì nuốt, không phá lượt chat",
      "except Exception:  # noqa: BLE001 - ghim hỏng không được phá lượt chat" in _src_acr)

# ============================================================
# 6. Mỗi lượt chat tự nói nó đi đường nào
# ============================================================
check("có hàm dựng thông tin đó", "def _ctx_frame(" in _MAIN)
_f = main._ctx_frame(None, 1234)
check("không có trace thì coi là đường cũ", _f["ctx_path"] == "legacy")
check("mang theo số token vào", _f["ctx_in"] == 1234)
check("token âm/None không lọt ra ngoài",
      main._ctx_frame(None, None)["ctx_in"] == 0 and main._ctx_frame(None, -5)["ctx_in"] == 0)


class _Trace:
    execution_path = "sources"


check("có trace thì nói đúng đường", main._ctx_frame(_Trace(), 10)["ctx_path"] == "sources")


class _TraceChua:
    execution_path = "unassigned"


check("đường chưa gán cũng quy về đường cũ, không nói 'chưa rõ'",
      main._ctx_frame(_TraceChua(), 10)["ctx_path"] == "legacy")

# Và phải NỐI vào cả ba khung trả lời người dùng thật sự đi qua. Đây là chỗ hay sót nhất.
check("CANARY: cả ba nhánh engine đều gắn thông tin đường chạy",
      _MAIN.count("**_ctx_frame(runtime_trace, _ctx_in)") == 3)
check("có cộng dồn token vào của lượt", _MAIN.count("_ctx_in +=") >= 3)
check("giao diện có hàm vẽ dòng đó", "function _renderCtxLine(" in _APP and "msg-ctx" in _APP)
# Định nghĩa hàm cũng chứa "_renderCtxLine(msgEl, data" nên phải soi lời GỌI có dấu chấm phẩy,
# không thì gỡ lời gọi đi mà test vẫn xanh (đã kiểm ngược, mutation này từng lọt).
check("CANARY: và THẬT SỰ gọi khi lượt kết thúc", "_renderCtxLine(msgEl, data);" in _APP)
check("CSS cho dòng đó có thật",
      ".msg-ctx" in (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8"))
check("bấm vào dòng đó thì sang trang Tiết kiệm token", 'usageGoto = "runtime"' in _APP)

# ============================================================
# 7. Panel Mức dùng cũng phải nói được chuyện này
# ============================================================
check("panel Mức dùng có dòng tiết kiệm", "_usageSavingRow" in _APP)
check("nó nêu tên mức đang dùng", "Tiết kiệm token: <b>" in _APP)
# Ưu tiên số ĐO ĐƯỢC, chưa có mới dùng ước lượng - và phải nói rõ cái nào là cái nào.
check("CANARY: ưu tiên số đo thật hơn ước lượng",
      _APP.find("dod.du_du_lieu") < _APP.find("uoc.phan_tram"))
check("phân biệt rõ 'đo thật' với 'ước lượng'",
      "(đo thật)" in _APP and "(ước lượng)" in _APP)
# refreshUsage chạy sau MỖI lượt chat; gọi /runtime/diagnostics mỗi lần là tự bắt mình trả giá
# cho chính cái panel đo giá.
check("CANARY: có cache để không gọi lại sau mỗi lượt chat",
      "_savingCache" in _APP and "60000" in _APP)

# ============================================================
# 8. Tên đường phải dịch ra tiếng người
# ============================================================
# Tên phải NÓI ĐÚNG NÓ LÀM GÌ, không phải nó cũ hay mới. "Đường cũ" là góc nhìn của người
# viết code; với người dùng đó là chế độ gửi đủ mọi thứ, an toàn nhất, và đúng là thứ họ chọn
# khi bấm "Tắt". Chủ repo nói thẳng: "đừng đặt tên là đường cũ nghe nó buồn cười".
_TEN = {"legacy": "Đầy đủ", "unassigned": "Đầy đủ", "sources": "Tối ưu", "fast": "Tức thì"}
check("có bảng dịch tên chế độ ở trang", "DUONG_LABEL" in _CONSOLE)
check("có bảng dịch tên chế độ ở khung chat", "CTX_PATH_LABEL" in _APP)
_bang_trang = _CONSOLE.split("DUONG_LABEL = {")[1].split("};")[0]
_bang_chat = _APP.split("CTX_PATH_LABEL = {")[1].split("};")[0]
for _k, _v in _TEN.items():
    check(f"trang gọi '{_k}' là '{_v}'", f'{_k}: "{_v}"' in _bang_trang)
    if _k != "unassigned":   # khung chat quy unassigned về legacy từ phía máy chủ
        check(f"khung chat gọi '{_k}' là '{_v}'", f'{_k}: "{_v}"' in _bang_chat)
# Hai bảng phải khớp nhau: dòng dưới câu trả lời ghi một đằng, bảng trên trang ghi một nẻo
# thì người dùng không nối được hai chỗ với nhau.
for _k in ("readonly", "orchestrator", "write", "workflow"):
    _a = _bang_trang.split(f"{_k}: ")[1].split('"')[1]
    _b = _bang_chat.split(f"{_k}: ")[1].split('"')[1]
    check(f"CANARY: trang và khung chat gọi '{_k}' giống nhau ({_a})", _a == _b)

check("CANARY: bảng chế độ dùng bản đã dịch", "_tenDuong(d.paths)" in _CONSOLE)

# Và không được sót chữ cũ ở BẤT KỲ chỗ nào người dùng đọc. Bỏ comment trước khi soi: cả hai
# file đều nhắc lại cụm cũ trong phần giải thích vì sao bỏ nó, quét cả comment là bắt nhầm
# chính lời giải thích đó.
def _bo_comment(src):
    import re
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    return re.sub(r"(^|[^:])//.*$", r"\1", src, flags=re.M)


for _ten_file, _src in (("console.js", _CONSOLE), ("app.js", _APP)):
    _code = _bo_comment(_src)
    for _xau in ("đường cũ", "Đường cũ", "đường mới", "Đường mới"):
        check(f"CANARY: {_ten_file} không còn chữ '{_xau}' trước mắt người dùng",
              _xau not in _code)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_trang_tiet_kiem: tất cả pass")
