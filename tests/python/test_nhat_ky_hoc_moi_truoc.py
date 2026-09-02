"""Nhật ký học phải xếp MỚI NHẤT TRƯỚC, kể cả trong cùng một ngày.

    python tests/run.py nhat_ky_hoc_moi_truoc

Người dùng báo 02/09: "cách nó lưu xuống hình như là ko theo thứ tự từ trên xuống theo ngày
giờ", kèm ảnh chụp thấy 08-31 06:13 → 06:58 → 07:02 → ... rồi mới tới 08-30.

Nguyên nhân: `learn_log` sắp FILE giảm dần (mỗi ngày một file) nhưng giữ nguyên thứ tự bên
trong, mà `_log` thì ghi NỐI ĐUÔI - nên trong một ngày lại hoá cũ trước. Docstring của hàm
vẫn ghi "mới nhất trước", tức đúng một nửa.

Vì sao đáng sửa chứ không phải chuyện thẩm mỹ: một ngày học 100-200 mục, dashboard chia 10
mục mỗi trang, nên mục mới nhất nằm lẫn đâu đó giữa hai chục trang. Người dùng mở nhật ký ra
chính là để xem Javis vừa học gì và có lỗi gì khi chạy model nền - thứ họ cần luôn là mục mới
nhất, mà đó lại là thứ khó tìm nhất.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

import learn  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if not cond and them else ""))
    if not cond:
        fails.append(name)


# ---- Đọc mốc thời gian ở đầu mỗi mục -----------------------------------------
check("đọc được mốc thời gian chuẩn",
      learn._moc_log("## [2026-08-31 06:13] learn — auto") == "2026-08-31 06:13")
check("chấp cả dạng có chữ T ngăn ngày với giờ",
      learn._moc_log("## [2026-08-31T06:13] learn") == "2026-08-31 06:13")
# Mục hỏng định dạng mà nhảy lên đầu là chiếm đúng chỗ người dùng đang cần nhìn.
check("CANARY: mục hỏng định dạng trả chuỗi rỗng để rơi xuống ĐÁY",
      learn._moc_log("rác không đúng khuôn") == "")
check("thiếu dấu ngoặc cũng coi là hỏng", learn._moc_log("## 2026-08-31 06:13 learn") == "")

# ---- Sắp xếp: đúng cảnh trong ảnh người dùng gửi -----------------------------
_anh = [
    "## [2026-08-31 06:13] learn — auto\nĐã học.",
    "## [2026-08-31 06:58] learn — auto\nĐã học.",
    "## [2026-08-31 07:02] learn — auto\nĐã học.",
    "## [2026-08-31 07:10] learn — auto\nĐã học.",
    "## [2026-08-30 07:31] learn — không parse được manifest\nĐã học.",
]
_sap = sorted(_anh, key=learn._moc_log, reverse=True)
check("mục mới nhất lên đầu", learn._moc_log(_sap[0]) == "2026-08-31 07:10", _sap[0][:30])
check("và cũ nhất xuống cuối", learn._moc_log(_sap[-1]) == "2026-08-30 07:31")
check("giảm dần suốt danh sách",
      all(learn._moc_log(_sap[i]) >= learn._moc_log(_sap[i + 1]) for i in range(len(_sap) - 1)),
      [learn._moc_log(x) for x in _sap])
# Trong CÙNG một ngày cũng phải mới trước - đây đúng là nửa mà bản cũ làm sai.
_mot_ngay = [x for x in _sap if x.startswith("## [2026-08-31")]
check("CANARY: trong cùng một ngày cũng mới trước",
      learn._moc_log(_mot_ngay[0]) > learn._moc_log(_mot_ngay[-1]),
      [learn._moc_log(x) for x in _mot_ngay])
check("mục hỏng nằm cuối, không chiếm chỗ mới nhất",
      sorted(_anh + ["hỏng"], key=learn._moc_log, reverse=True)[-1] == "hỏng")

# ---- Hàm đọc nhật ký thật sự có gọi sắp xếp ----------------------------------
_src = (ROOT / "server" / "learn.py").read_text(encoding="utf-8")
check("learn_log sắp theo dấu thời gian chứ không tin thứ tự file",
      "entries.sort(key=_moc_log, reverse=True)" in _src)
# Docstring cũ đã hứa "mới nhất trước" trong khi code chỉ làm được một nửa. Giữ lời hứa đó
# nhưng phải có mã đứng sau nó.
check("và docstring vẫn hứa mới nhất trước", "mới nhất trước" in _src)

print("")
if fails:
    print(f"ĐỎ {len(fails)} mục")
    sys.exit(1)
print("Tất cả xanh.")
