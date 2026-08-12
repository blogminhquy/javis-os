"""Khối ngữ cảnh dashboard tự chèn KHÔNG được lọt ra chỗ người dùng đọc.

    python tests/run.py khoi_ngu_canh      (KHÔNG mạng)

Chủ repo chụp màn hình (2026-08-12): hội thoại dài, mở thanh mốc hội thoại ra thì thấy hai chục
dòng giống hệt nhau, dòng nào cũng bắt đầu bằng "[FILE ĐANG MỞ trong trình sửa của Javis: ..."
- không nhìn ra câu nào với câu nào. Chỉ mỗi dòng cuối (câu vừa gõ) là đọc được.

Đúng cái chi tiết "chỉ dòng cuối đọc được" chỉ thẳng vào nguyên nhân: lúc GÕ, app.js dựng bong
bóng từ chữ sạch rồi mới chèn khối ngữ cảnh vào bản GỬI ĐI. Nhưng mở lại hội thoại cũ (F5, hoặc
bấm vào một cuộc trong Lịch sử) thì bong bóng được dựng từ chữ SERVER LƯU - tức bản đã kèm
khối. Và khối "file đang ghim" được gửi lại MỖI LƯỢT, nên hội thoại càng dài càng nhiều rác.

Hai tầng cùng một lỗi, và tầng thứ hai là lỗi TÁI PHÁT:

1. **Dashboard** - bong bóng, thanh mốc hội thoại, nút gửi lại / sửa câu hỏi (cả ba đọc chung
   `dataset.text`).
2. **Server** - tên hội thoại. `title_from_message` đã được vá đúng lỗi này ngày 2026-07-31 cho
   khối "File đính kèm", nhưng khối "FILE ĐANG MỞ" ra đời SAU nên đi lọt qua cửa khác. Ghim còn
   phổ biến hơn đính kèm nhiều vì nó gửi lại mỗi lượt.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import re
import sys

import sessions   # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# Nguyên văn hai khối mà app.js chèn (chép rút gọn từ dashboard/app.js).
GHIM = ("[FILE ĐANG MỞ trong trình sửa của Javis: /home/user/brain/Wiki/checkout.md\n"
        "Đây là file người dùng ĐANG LÀM VIỆC TRÊN ĐÓ - coi như đầu vào của cuộc trò chuyện "
        "này. Đọc nó trước khi trả lời.]\n\n")
DINH_KEM = ("[File đính kèm để ĐỌC (đường dẫn):\n- /home/user/brain/sources/bao-gia.pdf\n"
            "Mặc định: chỉ đọc file rồi trả lời, KHÔNG tự lưu đi đâu.]\n\n")
CAU_TU_DIEN = "Hãy đọc (các) file trên và phản hồi / tóm tắt nội dung chính."
CAU_THAT = "kiểm tra bên webcake xem liệu có thể là 2 trang checkout không"


# ============================================================
# 1. Server: tên hội thoại
# ============================================================
_t = sessions.title_from_message
check("CANARY: ghim file + câu hỏi -> tên là CÂU HỎI, không phải khối ghim",
      _t(GHIM + CAU_THAT).startswith("kiểm tra bên webcake"), _t(GHIM + CAU_THAT))
check("hai khối lồng nhau vẫn bóc hết",
      _t(GHIM + DINH_KEM + "tóm tắt giúp anh") == "tóm tắt giúp anh",
      _t(GHIM + DINH_KEM + "tóm tắt giúp anh"))
# Ca này từng vỡ ở bản sửa đầu: cả hai mẫu đều neo `^`, nên khối ghim đứng trước là mẫu đính
# kèm trượt, và hội thoại "chỉ gửi file" mất sạch tên thay vì mang tên file.
check("CANARY: ghim + chỉ gửi file (không gõ chữ) -> vẫn lấy được TÊN FILE",
      _t(GHIM + DINH_KEM + CAU_TU_DIEN) == "bao-gia.pdf", _t(GHIM + DINH_KEM + CAU_TU_DIEN))
check("không có khối nào thì giữ nguyên như cũ",
      _t("doanh thu hôm nay bao nhiêu?") == "doanh thu hôm nay bao nhiêu?")
check("chỉ đính kèm (đường cũ) vẫn chạy y như trước",
      _t(DINH_KEM + "đọc giúp em") == "đọc giúp em")
check("tin rỗng -> tên rỗng, không nổ", _t("") == "")
for _x in (GHIM, DINH_KEM, GHIM + DINH_KEM):
    check("CANARY: KHÔNG có tên hội thoại nào bắt đầu bằng dấu ngoặc của khối",
          not _t(_x + CAU_THAT).startswith("["), _t(_x + CAU_THAT))

_src_sessions = (SERVER / "sessions.py").read_text(encoding="utf-8")
check("có mẫu riêng cho khối ghim", "_KHOI_GHIM" in _src_sessions)
check("CANARY: bóc LẶP chứ không phải count=1 một lần (hai khối lồng nhau)",
      "for _ in range(4):" in _src_sessions.split("def title_from_message")[1][:1600])


# ============================================================
# 2. Dashboard: bong bóng + thanh mốc + gửi lại
# ============================================================
APP = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")

check("có hàm gỡ khối ngữ cảnh", "function chuNguoiGo(" in APP)
# Chặn ở CỬA DUY NHẤT dựng bong bóng người dùng. Gỡ ở từng nơi gọi là chỗ thứ tư sinh sau sẽ
# không ai nhớ gỡ - đúng cái bẫy mà chính khối ghim này đã rơi vào ở tầng server.
_ham = APP[APP.index("function appendUserMessage("):]
_ham = _ham[:_ham.index("function appendJavisMessage(")]
check("CANARY: gỡ ngay đầu appendUserMessage - cửa duy nhất dựng bong bóng người dùng",
      _ham.index("chuNguoiGo(text)") < _ham.index("dataset.text"))
check("CANARY: dataset.text cũng sạch - thanh mốc, gửi lại, sửa câu hỏi đều đọc ké nó",
      "div.dataset.text = text" in _ham)
check("lượt nạp hội thoại cũ ghi bản SẠCH vào convo (localStorage), không để lỗi sống qua F5",
      'convo.push({ role: "user", text: _sach' in APP)
check("nhận cả hai loại khối",
      "[FILE ĐANG MỞ trong trình sửa của Javis:" in APP and '"[File đính kèm"' in APP)

# Hành vi THẬT của hàm, chạy bằng node nếu có; không có node thì đọc hợp đồng là đủ.
import shutil          # noqa: E402
import subprocess      # noqa: E402
import json as _json   # noqa: E402

if shutil.which("node"):
    _i, _j = APP.index("const _KHOI_NGU_CANH"), APP.index("window.JavisChuNguoiGo")
    _js = APP[_i:_j] + "\nconst ca = JSON.parse(process.argv[1]);" \
          "\nconsole.log(JSON.stringify(ca.map(chuNguoiGo)));"
    _ca = [GHIM + CAU_THAT, GHIM + DINH_KEM + "tóm tắt giúp anh", DINH_KEM + "đọc giúp em",
           "chào em", "[FILE ĐANG MỞ trong trình sửa của Javis: a.md chưa đóng khối",
           "[ghi chú] nhớ mua sữa", ""]
    _ra = _json.loads(subprocess.run(["node", "-e", _js, _json.dumps(_ca)],
                                     capture_output=True, text=True, timeout=30).stdout)
    check("ghim -> còn đúng câu hỏi", _ra[0] == CAU_THAT, _ra[0])
    check("ghim + đính kèm -> còn đúng câu hỏi", _ra[1] == "tóm tắt giúp anh", _ra[1])
    check("chỉ đính kèm -> còn đúng câu hỏi", _ra[2] == "đọc giúp em", _ra[2])
    check("chữ sạch giữ NGUYÊN, không đụng vào", _ra[3] == "chào em")
    # Fail-open: khối hỏng thì thà hiện thừa còn hơn cắt mất câu hỏi của người ta.
    check("CANARY: khối thiếu chỗ kết -> KHÔNG cắt bừa",
          _ra[4].startswith("[FILE ĐANG MỞ"), _ra[4])
    check("CANARY: câu người dùng tự gõ mở bằng ngoặc vuông KHÔNG bị đụng",
          _ra[5] == "[ghi chú] nhớ mua sữa", _ra[5])
    check("rỗng -> rỗng", _ra[6] == "")
else:
    print("bỏ qua  chạy thật bằng node (máy này không có node)")

# Thanh mốc hội thoại đọc dataset.text, nên nó được sửa lây - khoá lại đường đó.
MARKS = (ROOT / "dashboard" / "chat-marks.js").read_text(encoding="utf-8")
check("CANARY: thanh mốc vẫn lấy nhãn từ dataset.text (đường được sửa lây)",
      "dataset.text" in MARKS)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test khoi_ngu_canh_lo_ra đã qua.")
