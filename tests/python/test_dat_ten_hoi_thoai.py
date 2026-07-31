"""Tên hội thoại phải theo NỘI DUNG, không phải khối hướng dẫn đính kèm. Chạy tay / CI:

    python tests/python/test_dat_ten_hoi_thoai.py

Không cần pytest, không chạm mạng, không đụng CSDL (test hàm thuần).

Bệnh (chủ repo báo 2026-07-31): trong danh sách Lịch sử, mọi hội thoại có file đính kèm đều
mang đúng một cái tên "[File đính kèm để ĐỌC (đườn…" nên nhìn không phân biệt nổi cái nào là
cái nào. Nguyên nhân: title = 48 ký tự ĐẦU của tin nhắn thô, mà dashboard chèn sẵn một khối
hướng dẫn dài TRƯỚC câu hỏi khi có file đính kèm (app.js).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import re
import sys

from sessions import TITLE_MAX, title_from_message as tt

loi = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + repr(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


def khoi_doc(files, hoi=""):
    """Dựng đúng chuỗi app.js sinh ra cho nhánh 'đính kèm để ĐỌC'."""
    lines = "\n".join("- " + f for f in files)
    ctx = ("[File đính kèm để ĐỌC (đường dẫn):\n" + lines + "\n"
           "Mặc định: chỉ đọc file rồi trả lời, KHÔNG tự lưu đi đâu.\n"
           'CHỈ khi user yêu cầu rõ (vd "lưu vào source", "ingest", "ghi vào second brain") thì mới: '
           'chuyển thành .md (ảnh thì đọc hiểu + mô tả) lưu vào Sources="/b/06 - Sources" '
           '(ảnh gốc chuyển vào Attachments="/b/attachments"), kèm frontmatter source.]')
    return ctx + "\n\n" + (hoi or "Hãy đọc (các) file trên và phản hồi / tóm tắt nội dung chính.")


# ---- 1. ĐÚNG CA ĐƯỢC BÁO: có file + có câu hỏi -> lấy câu hỏi ----
that = khoi_doc(["/data/state/.staging/javis-tiec-tra-ai-warrior-plus_2.html"],
                "nhóm zalo cho cái này nên để là gì nhỉ, hiện tại anh đang để là bí mật ai, "
                "có nên đổi thành tiệc trà ai không nhỉ?")
t = tt(that)
check("CANARY: hội thoại có file KHÔNG còn tên 'File đính kèm...'",
      not t.startswith("[File đính kèm"), t)
check("lấy đúng câu người dùng gõ", t.startswith("nhóm zalo"), t)
check("không lọt đường dẫn vào tên", "/" not in t and ".html" not in t, t)

# ---- 2. Không đính kèm -> giữ nguyên hành vi cũ ----
check("câu thường giữ nguyên",
      tt("kiểm tra mcp workspace xem có chạy không") == "kiểm tra mcp workspace xem có chạy không")
check("câu dài bị cắt và có dấu …", tt("a " * 60).endswith("…"))
check("cắt xong không dài quá giới hạn", len(tt("a " * 60)) <= TITLE_MAX + 1, tt("a " * 60))

# Cắt phải ở RANH GIỚI TỪ, không cắt giữa chữ.
dai = "Tìm record mới nhất hôm nay lúc mấy giờ và cho anh biết nội dung của nó luôn nhé"
check("cắt ở ranh giới từ, không cụt giữa chữ",
      tt(dai).rstrip("…").split()[-1] in dai.split(), tt(dai))

# ---- 3. Chỉ đính kèm, không gõ chữ nào -> lấy TÊN FILE ----
check("một file -> tên file", tt(khoi_doc(["/x/bao-cao-thang-6.pdf"])) == "bao-cao-thang-6.pdf",
      tt(khoi_doc(["/x/bao-cao-thang-6.pdf"])))
check("nhiều file -> tên file đầu + đếm",
      tt(khoi_doc(["/x/a.png", "/x/b.png", "/x/c.png"])) == "a.png +2 file",
      tt(khoi_doc(["/x/a.png", "/x/b.png", "/x/c.png"])))
check("đường dẫn Windows cũng lấy đúng tên",
      tt(khoi_doc([r"C:\Users\Quy\bao-cao.xlsx"])) == "bao-cao.xlsx",
      tt(khoi_doc([r"C:\Users\Quy\bao-cao.xlsx"])))

# ---- 4. Dạng khối thứ hai (lệnh skill, có Sources=/Attachments=) ----
# Khối này đóng NGAY sau đường dẫn cuối và mang thêm hai thư mục cấu hình. Cả hai chỗ đều
# từng làm hỏng tên: ra "anh-san-pham.png]" và ra "My +4 file" (lặp y hệt ở mọi hội thoại).
slash = ('[File đính kèm (đường dẫn), Sources="/brains/My BJ/06 - Sources", '
         'Attachments="/brains/My BJ/attachments":\n- /tmp/anh-san-pham.png]\n\n')
check("CANARY: thư mục Sources/Attachments KHÔNG lọt vào tên",
      tt(slash) == "anh-san-pham.png", tt(slash))
check("có lệnh skill thì lấy lệnh đó",
      tt(slash.rstrip() + "/notes lưu giúp anh").startswith("/notes"),
      tt(slash.rstrip() + "/notes lưu giúp anh"))

# ---- 5. Không bóc nhầm ngoặc vuông của chính người dùng ----
# Người ta có quyền mở câu bằng "[gấp]". Bóc mọi khối [..] mở đầu là mất phần quan trọng nhất.
check("CANARY: '[gấp] ...' của user KHÔNG bị bóc",
      tt("[gấp] xem giúp anh cái này với") == "[gấp] xem giúp anh cái này với",
      tt("[gấp] xem giúp anh cái này với"))
check("CANARY: '[quan trọng] ...' KHÔNG bị bóc",
      tt("[quan trọng] doanh thu hôm nay bao nhiêu").startswith("[quan trọng]"))

# ---- 6. Đầu vào rỗng / rác ----
for xau in ("", "   ", "\n\n", None):
    check("đầu vào " + repr(xau) + " -> rỗng (không đặt tên bừa)", tt(xau) == "", tt(xau))
check("đính kèm nhưng không đọc được tên file -> vẫn có tên chung",
      tt("[File đính kèm để ĐỌC (đường dẫn):\nkhông có dòng file nào]\n\n") == "File đính kèm",
      tt("[File đính kèm để ĐỌC (đường dẫn):\nkhông có dòng file nào]\n\n"))

# ---- 7. Câu ngắn, nhiều câu ----
check("câu rất ngắn giữ nguyên", tt("Ok?") == "Ok?")
# Không tách theo dấu chấm: tiếng Việt chấm nhiều, tách ra là tên chỉ còn "Chào em".
check("CANARY: không cắt ở dấu chấm giữa câu",
      tt("Chào em. Hôm nay doanh thu bao nhiêu?") == "Chào em. Hôm nay doanh thu bao nhiêu?",
      tt("Chào em. Hôm nay doanh thu bao nhiêu?"))
check("nhiều dòng -> lấy dòng đầu",
      tt("làm giúp anh việc này\nchi tiết ở dưới\nnhiều lắm") == "làm giúp anh việc này",
      tt("làm giúp anh việc này\nchi tiết ở dưới\nnhiều lắm"))

# ---- 8. Mọi tên đều dùng được làm nhãn ----
for msg in (that, khoi_doc(["/x/a.pdf"]), "câu thường", slash, "a " * 60):
    r = tt(msg)
    check("tên không có xuống dòng: " + repr(r[:20]), "\n" not in r, r)
    check("tên không dài quá giới hạn: " + repr(r[:20]), len(r) <= TITLE_MAX + 1, r)

if loi:
    print("\nFAIL - test_dat_ten_hoi_thoai: %d lỗi: %s" % (len(loi), ", ".join(loi)))
    sys.exit(1)
print("\nOK - test_dat_ten_hoi_thoai: tất cả pass")
