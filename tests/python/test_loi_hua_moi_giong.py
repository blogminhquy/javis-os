"""Bộ dò lời hứa phải bắt được MỌI giọng xưng hô (mình / em / tôi).

    python tests/run.py loi_hua_moi_giong

Tách ra từ `test_xung_ho.py` (chủ dự án gỡ test đó ngày 2026-09-14: xưng hô là chuyện của từng
người dùng, không phải luật hệ thống). Phần này vẫn đáng giữ vì không liên quan tới luật xưng
hô: `background_status.detect_promise` dán một dòng đính chính khi Javis hứa suông, và mẫu chỉ
bắt một giọng ("em ... báo lại") thì đổi giọng là cổng im lặng mất tác dụng, không có gì kêu lên.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

import background_status

_loi = []


def check(ten, dieu_kien):
    print(f"       {'ok  ' if dieu_kien else 'FAIL'} {ten}")
    if not dieu_kien:
        _loi.append(ten)


for cau in ("Ok, mình sẽ báo lại sau nhé",
            "Mình đang dò lại code, có kết quả mình báo ngay",
            "Bạn chờ mình chút nhé",
            "Xong mình báo lại",
            "Có kết quả em báo ngay",
            "Anh chờ em chút, em kiểm tra rồi báo lại",
            "Tôi sẽ báo lại sau khi xong"):
    check(f"bắt được lời hứa: {cau[:40]!r}", bool(background_status.detect_promise(cau, "vi")))

check("câu KHÔNG hứa thì không bị dán đính chính oan",
      not background_status.detect_promise("Doanh thu hôm nay 4,2 triệu, tăng 12% so hôm qua.", "vi"))

print()
if _loi:
    print(f"ĐỎ {len(_loi)} mục: " + "; ".join(_loi[:4]))
    sys.exit(1)
print("Tất cả xanh.")
