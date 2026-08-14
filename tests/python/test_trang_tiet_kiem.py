"""Khối chọn mức tiết kiệm phải nói được nó tiết kiệm BAO NHIÊU, và lượt chat đi đường nào.

    python tests/run.py trang_tiet_kiem

Từ 0.24.7 khối này nằm ở ĐẦU trang Mức dùng (`dashboard/usage.js`), không còn là một trang
riêng trong rail. Chủ repo chốt: "gom nút tiết kiệm sang bên Mức dùng... Menu tiết kiệm cũng
không cần nữa". Đúng: "tôi tiêu bao nhiêu" và "làm sao tiêu ít đi" là cùng một câu hỏi, tách
hai trang thì người dùng thấy hoá đơn mà không thấy cái công tắc.

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
_USAGE = (ROOT / "dashboard" / "usage.js").read_text(encoding="utf-8")
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
# 2. Ba mức nằm ở ĐẦU trang Mức dùng
# ============================================================
# Chôn ba nút xuống dưới hoá đơn là mở trang ra thấy số liệu trước khi thấy cái nút cần bấm.
# Đây chính là yêu cầu của chủ repo: "trong mức dùng sẽ để chế độ tiết kiệm ngay trên đầu
# tiên luôn". Soi THỨ TỰ GHÉP CHUỖI thật, không soi định nghĩa hàm - hàm có thể tồn tại mà
# không bao giờ được ghép vào trang.
check("có khối chọn mức trong trang Mức dùng", "function mucHtml(" in _USAGE)
_i_ghep = _USAGE.find("mucHtml(state.muc) + bar1")
check("CANARY: khối chọn mức ghép TRƯỚC thanh lọc kỳ và mọi con số", _i_ghep != -1)
check("và có tiêu đề người đọc hiểu", "Chế độ tiết kiệm token" in _USAGE)

# Trang riêng đã gỡ hẳn: còn sót một mảnh là rail vẫn hiện mục Tiết kiệm, hoặc tệ hơn, hai
# nơi cùng vẽ một khối và chúng lệch nhau.
check("CANARY: trang Tiết kiệm không còn trong rail",
      'label: "Tiết kiệm"' not in _CONSOLE and '{ id: "runtime"' not in _CONSOLE)
check("CANARY: và hàm dựng trang đó đã xoá", "renderRuntime" not in _CONSOLE)
check("id cũ vẫn có chỗ đáp, không rơi vào màn hình trắng",
      "TRANG_GOP" in _CONSOLE and 'runtime: "usage"' in _CONSOLE)

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
check("giao diện có nói ra chữ 'ước lượng'", "ước lượng" in _USAGE)

# Khai hỏng thì trả rỗng chứ không nổ giữa trang.
check("brain không tồn tại vẫn không nổ",
      isinstance(asyncio.run(main._uoc_tinh_tiet_kiem("brain-khong-co-that")), dict))
check("tham số sai kiểu vẫn không nổ (gọi thẳng hàm endpoint)",
      isinstance(asyncio.run(main._uoc_tinh_tiet_kiem(None)), dict))

# Giao diện phải THẬT SỰ vẽ con số đó ra, không chỉ định nghĩa biến rồi bỏ đó.
_nut = _USAGE[_USAGE.find('data-muc="'):][:900]
check("CANARY: nút mức có ghép phần trăm vào", "pct" in _nut and "m.phan_tram" in _USAGE)
check("CANARY: và ghép token mỗi lượt vào", "tok" in _nut and "m.token_moi_request" in _USAGE)
check("có CSS cho hai thứ đó", ".tk-muc-pct{" in _USAGE and ".tk-muc-tok{" in _USAGE)
check("giao diện đọc đúng trường API trả về", "d.uoc_tinh" in _USAGE)

# ============================================================
# 3b. Endpoint gọn: trả ĐÚNG bốn thứ trang cần, không hơn
# ============================================================
# Trang Mức dùng không được gọi `/runtime/diagnostics`: endpoint đó gánh theo bảng canary
# tính bằng phần vạn, cửa sổ token 60 giây, hạn mức tự học, danh sách task kèm
# execution_path, kết quả integrity_check. Không thứ nào trả lời được câu hỏi duy nhất của
# người dùng cuối ("tôi nên bấm mức nào"), mà mỗi thứ đều tốn một lượt đọc runtime.db.
_muc_api = asyncio.run(main.runtime_muc(brain="brain"))
check("endpoint gọn trả về dict", isinstance(_muc_api, dict))
# `engine` thêm ở 0.26.3: cần để nói ĐÚNG về phần quy đổi tiền. Người dùng gói thuê bao không
# trả theo token, nên với họ con số tiền là mức quy đổi nếu tính theo giá API chứ không phải
# tiền mặt tiết kiệm được - không phân biệt là cả trang mất tin cậy. Nó rẻ (chỉ đọc settings),
# khác hẳn nhóm trường chẩn đoán bị cấm ở phép thử ngay dưới.
check("trả đúng những thứ trang cần, không hơn",
      set(_muc_api) == {"muc", "danh_sach", "tu_chon", "uoc_tinh", "do_duoc", "engine"})
check("CANARY: và KHÔNG kèm số liệu chẩn đoán",
      not ({"canaries", "tpm_window", "quota_presets", "registry", "tasks"} & set(_muc_api)))
check("danh sách mức khớp bảng mức thật",
      [x["id"] for x in _muc_api["danh_sach"]] == list(main.RUNTIME_PRESETS))
check("mỗi mức có nhãn và mô tả",
      all(x.get("nhan") and x.get("mo_ta") for x in _muc_api["danh_sach"]))
check("mức đang chạy là một trong số đó (hoặc custom)",
      _muc_api["muc"] in set(main.RUNTIME_PRESETS) | {"custom"})
check("khai rõ người dùng đã tự chọn hay chưa", isinstance(_muc_api["tu_chon"], bool))
# Giao diện đọc đúng những tên đó. Backend đúng mà tên trường lệch một chữ thì trang vẽ ra
# ba cái nút trống, và không có gì báo lỗi cả.
for _f in ("d.muc", "d.danh_sach", "d.tu_chon", "d.uoc_tinh", "d.do_duoc"):
    check(f"giao diện đọc '{_f}'", _f in _USAGE)
check("giao diện gọi đúng endpoint gọn",
      '"/runtime/muc"' in _USAGE and "/runtime/diagnostics" not in _USAGE)


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
check("giao diện có vẽ bảng đo thật", "tk-muc-do" in _USAGE and "d.do_duoc" in _USAGE)


# ============================================================
# 4b. Tiết kiệm được BAO NHIÊU TOKEN, và quy ra tiền
# ============================================================
# Yêu cầu chủ repo (2026-08-08): "lôi cho anh thông tin của việc tiết kiệm được bao nhiêu token
# ra, và quy đổi khoảng thành tiền thì càng tốt". Phần trăm một mình không trả lời được câu
# người ta thật sự hỏi - "cái công tắc này đáng bao nhiêu?".
#
# Ba mức tin cậy phải TÁCH BẠCH, không thì con số to nhất bị đọc như một hoá đơn:
#   token trong cửa sổ vừa đo = ĐO ĐƯỢC · token mỗi tháng = PHÉP CHIẾU · tiền = ƯỚC LƯỢNG.
check("đo được số token đã tiết kiệm, không chỉ phần trăm", _do["token_tiet_kiem"] > 0)
# 2 lượt đường mới, mỗi lượt đáng lẽ tốn 10000 mà chỉ tốn 750 -> (10000-750)*2.
check("cách tính token tiết kiệm đúng", _do["token_tiet_kiem"] == (10000 - 750) * 2)
check("khai rõ đo trong cửa sổ bao nhiêu giờ", _do["gio_do"] > 0)
_thang = main._do_duoc_tiet_kiem(_tasks, 24.0)["token_thang"]
check("chiếu ra một tháng theo đúng nhịp cửa sổ đã đo", _thang == (10000 - 750) * 2 * 30)
check("cửa sổ ngắn hơn thì phép chiếu lớn hơn tương ứng",
      main._do_duoc_tiet_kiem(_tasks, 12.0)["token_thang"] == _thang * 2)

_tien = main._do_duoc_tiet_kiem(_tasks, 24.0, {"model": "claude-opus-5"})["tien"]
# Chủ repo chốt (2026-08-13): mọi con số tiền để nguyên USD, bỏ hẳn lớp quy đổi sang đồng.
# Giá của các nhà cung cấp đều niêm yết bằng USD, còn tỉ giá thì trôi mà hằng số trong code
# thì không ai đi cập nhật - lớp quy đổi đó chỉ tạo thêm một chỗ để sai.
check("có quy đổi ra tiền", _tien.get("usd_thang", 0) > 0)
check("CANARY: không còn quy đổi sang đồng",
      "vnd_thang" not in _tien and "ty_gia" not in _tien)
check("giá lấy theo ĐÚNG model đang dùng, không phải một số cố định",
      _tien["gia_1m_usd"] == main._GIA_INPUT_1M["opus"] and _tien["nguon_gia"] == "bang")
check("model rẻ hơn thì tiền quy đổi nhỏ hơn",
      main._do_duoc_tiet_kiem(_tasks, 24.0, {"model": "claude-haiku-4-5"})["tien"]["usd_thang"]
      < _tien["usd_thang"])
check("model lạ vẫn ra số, rơi về mức phổ biến",
      main._do_duoc_tiet_kiem(_tasks, 24.0, {"model": "mo-hinh-la"})["tien"]["nguon_gia"]
      == "mac_dinh")
check("người dùng đặt được đơn giá của chính mình, đè lên bảng tham khảo",
      main._gia_input_1m("claude-opus-5", {"gia_input_1m": 0.5}) == (0.5, "tay"))
check("đơn giá rác trong settings thì bỏ qua, không nổ",
      main._gia_input_1m("claude-opus-5", {"gia_input_1m": "linh tinh"})[1] == "bang")
check("chưa đủ dữ liệu thì không bịa ra tiền",
      main._do_duoc_tiet_kiem([])["tien"] == {} and main._do_duoc_tiet_kiem([])["token_tiet_kiem"] == 0)

# Giao diện phải VẼ RA, và phải nói đúng mức tin cậy của từng con số.
check("giao diện vẽ khối quy đổi tiền", "tk-tien" in _USAGE and "function tienHtml(" in _USAGE)
check("giao diện đọc đủ ba trường mới",
      "token_tiet_kiem" in _USAGE and "token_thang" in _USAGE and "usd_thang" in _USAGE)
check("giao diện gọi đúng tên: đo được / phép chiếu / ước lượng",
      "đo được" in _USAGE and "phép chiếu" in _USAGE and "ước lượng" in _USAGE)
check("giao diện ghi rõ đơn giá đang dùng", "1 triệu token vào" in _USAGE)
check("CANARY: giao diện không còn vẽ tiền đồng",
      "ty_gia" not in _USAGE and "fVnd" not in _USAGE and "đ/$" not in _USAGE)
# Người dùng gói thuê bao KHÔNG trả theo token: với họ đây là mức quy đổi, không phải tiền
# mặt tiết kiệm được. Nhập nhèm chỗ này là cả trang mất tin cậy.
check("nói đúng với người dùng gói thuê bao",
      "gói thuê bao" in _USAGE and "quy đổi" in _USAGE)
check("endpoint có trả loại engine để giao diện phân biệt được ca đó",
      _muc_api.get("engine", {}).get("loai") in ("Gói thuê bao", "API key", None)
      or isinstance(_muc_api.get("engine"), dict))
check("và nói rõ đây là số THẬT chứ không phải ước lượng", "số thật" in _USAGE)

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

# Và phải NỐI vào các khung trả lời người dùng thật sự đi qua. Đây là chỗ hay sót nhất.
# Đếm CHÍNH XÁC bằng 3 là bản cũ, viết từ hồi chỉ có ba nhánh engine gắn nhãn. Nó vô tình
# thành hàng rào chặn việc SỬA: gắn nhãn cho nhánh thứ tư là test đỏ, dù đó đúng là thứ phải
# làm (chủ repo báo "có chỗ thì không hiện gì"). Bài kiểm đầy đủ - mọi gói `response` đều
# phải mang nhãn - nằm ở test_duong_tat_bi_chan.
check("CANARY: các nhánh engine đều gắn thông tin đường chạy",
      _MAIN.count("**_ctx_frame(runtime_trace, _ctx_in)") >= 3)
check("có cộng dồn token vào của lượt", _MAIN.count("_ctx_in +=") >= 3)
check("giao diện có hàm vẽ dòng đó", "function _renderCtxLine(" in _APP and "msg-ctx" in _APP)
# Định nghĩa hàm cũng chứa "_renderCtxLine(msgEl, data" nên phải soi lời GỌI có dấu chấm phẩy,
# không thì gỡ lời gọi đi mà test vẫn xanh (đã kiểm ngược, mutation này từng lọt).
check("CANARY: và THẬT SỰ gọi khi lượt kết thúc", "_renderCtxLine(msgEl, data);" in _APP)
check("CSS cho dòng đó có thật",
      ".msg-ctx" in (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8"))
check("bấm vào dòng đó thì sang trang Mức dùng", 'usageGoto = "usage"' in _APP)

# ============================================================
# 7. Panel Mức dùng cũng phải nói được chuyện này
# ============================================================
check("panel Mức dùng có dòng tiết kiệm", "_usageSavingRow" in _APP)
check("nó nêu tên mức đang dùng", "Tiết kiệm: <b>" in _APP)
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
# Từ 0.24.7 chỉ còn MỘT bảng dịch, ở khung chat. Bảng thứ hai đi cùng trang Tiết kiệm - và
# đó là cái kết đúng: hai bảng chép tay của cùng một tập tên là hai chỗ để lệch nhau, mà
# lệch thì người dùng không nối được dòng dưới câu trả lời với chỗ chỉnh mức.
_TEN = {"legacy": "Đầy đủ", "sources": "Tối ưu", "fast": "Tức thì"}
check("có bảng dịch tên chế độ ở khung chat", "CTX_PATH_LABEL" in _APP)
check("CANARY: không còn bảng thứ hai để lệch", "DUONG_LABEL" not in _CONSOLE)
_bang_chat = _APP.split("CTX_PATH_LABEL = {")[1].split("};")[0]
for _k, _v in _TEN.items():
    check(f"khung chat gọi '{_k}' là '{_v}'", f'{_k}: "{_v}"' in _bang_chat)
for _k in ("readonly", "orchestrator", "write", "workflow", "bot"):
    check(f"và có tên tiếng Việt cho '{_k}'",
          len(_bang_chat.split(f"{_k}: ")[1].split('"')[1]) > 2)

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
