"""Chữa những file .md đã bị vòng lưu WYSIWYG của bản cũ làm hỏng.

Bản <= 0.33.3 mở note .md trong trình sửa trực quan rồi lưu là chạy vòng:

    markdown --mdToHtml--> HTML --turndown--> markdown

Vòng đó rò hai chỗ, và cả hai đều để lại DẤU VẾT RIÊNG mà người viết tay không tạo ra:

1. Frontmatter `---...---` bị hiểu thành đường kẻ ngang, ghi lại thành `* * *`, mấy dòng
   metadata rơi xuống thành một đoạn văn với hai dấu cách cuối mỗi dòng. File mất frontmatter:
   Javis, dataview và Obsidian đều đọc trượt từ đó.

2. Turndown thoát `1.` đầu dòng thành `1\\.`; mdToHtml bản cũ không hiểu dấu thoát nên lần lưu
   sau thoát tiếp chính dấu gạch đó: `1\\\\.`, `1\\\\\\.`... Mỗi lần mở ra sửa là bẩn thêm một lớp.

0.33.4 bịt cả hai đường, nhưng file đã hỏng thì phải chữa lại. Module này làm đúng việc đó.

LUẬT VÀNG: chỉ sửa thứ mà CHỈ CÓ LỖI ĐÓ mới tạo ra được.
- Khối `* * *` ở ĐẦU file, kẹp giữa toàn dòng trông như YAML → chắc chắn là frontmatter bị phá.
  (`---` ở đầu file là frontmatter còn lành - không đụng vào.)
- HAI dấu gạch chéo trở lên trước một ký tự dấu câu → chỉ có vòng lặp dồn mới sinh ra.
  MỘT dấu gạch chéo (`\\.`) thì KHÔNG đụng: người ta có thể cố ý gõ vậy, mà nó cũng hiện
  ra đúng ở mọi trình đọc markdown.

Thuần hàm, không I/O, không phụ thuộc gì - test được thẳng.
Ghi chú: KHÔNG dùng ký tự em dash ở bất kỳ đâu.
"""
import re

# Đường kẻ ngang do turndown ghi ra. KHÔNG nhận kiểu gạch ngang (`---`, `- - -`): ở đầu file
# `---` chính là frontmatter còn lành, nhận nhầm là tự tay phá một file đang tốt.
_HR = re.compile(r"^[ \t]*(?:\*[ \t]*){3,}$|^[ \t]*_{3,}[ \t]*$|^[ \t]*(?:_[ \t]){2,}_[ \t]*$")

# Một dòng trông như YAML: `khoa: gia tri`, hoặc mục danh sách (turndown thoát thành `\- x`).
_YAML_DONG = re.compile(r"^[ \t]*(?:\\?[-*][ \t]+\S.*|[A-Za-z_][\w .\-/]*[ \t]*:.*)$")

# Dấu câu mà turndown thoát. Dồn từ 2 dấu gạch chéo trở lên là dấu vết của lỗi.
_DON_GACH_CHEO = re.compile(r"\\{2,}([.\-+#>*_`\[\]()!~|])")

FRONTMATTER = "frontmatter"       # khối --- ở đầu note bị biến thành * * *
DAU_THOAT = "dau-thoat"           # dấu gạch chéo dồn lên qua nhiều lần lưu

MAX_DONG_FRONTMATTER = 80         # frontmatter dài hơn thế thì gần như chắc chắn không phải


def _go_thoat_dong_yaml(dong: str) -> str:
    """Trả một dòng frontmatter về nguyên trạng: bỏ dấu cách thừa cuối dòng (dấu vết <br> của
    turndown) và bỏ dấu thoát mà turndown thêm vào đầu dòng danh sách."""
    dong = dong.rstrip()
    return re.sub(r"^([ \t]*)\\([-*+])", r"\1\2", dong)


def _tach_frontmatter_hong(text: str):
    """Tìm khối frontmatter bị phá ở ĐẦU file.

    Trả về (cac_dong_yaml, so_dong_da_an) nếu thấy, còn không thì (None, 0).
    """
    dong = text.split("\n")
    i = 0
    while i < len(dong) and not dong[i].strip():      # bỏ qua dòng trống đầu file
        i += 1
    if i >= len(dong) or not _HR.match(dong[i]):
        return None, 0
    mo = i
    # Tìm đường kẻ ngang ĐÓNG khối
    dong_yaml, j, thay_dong = [], mo + 1, False
    while j < len(dong) and j - mo <= MAX_DONG_FRONTMATTER:
        if _HR.match(dong[j]):
            thay_dong = True
            break
        if dong[j].strip():
            if not _YAML_DONG.match(dong[j]):
                return None, 0                        # có dòng không giống YAML -> không phải
            dong_yaml.append(_go_thoat_dong_yaml(dong[j]))
        j += 1
    if not thay_dong or not dong_yaml:
        return None, 0
    return dong_yaml, j + 1


def tim_van_de(text: str):
    """Liệt kê các hỏng hóc thấy được trong nội dung. Rỗng = file lành."""
    van_de = []
    if _tach_frontmatter_hong(text)[0] is not None:
        van_de.append(FRONTMATTER)
    if _DON_GACH_CHEO.search(text):
        van_de.append(DAU_THOAT)
    return van_de


def sua(text: str):
    """Chữa nội dung. Trả về (noi_dung_moi, danh_sach_van_de_da_sua)."""
    van_de = []
    dong_yaml, het = _tach_frontmatter_hong(text)
    if dong_yaml is not None:
        con_lai = "\n".join(text.split("\n")[het:]).lstrip("\n")
        text = "---\n" + "\n".join(dong_yaml) + "\n---\n" + ("\n" + con_lai if con_lai else "")
        van_de.append(FRONTMATTER)
    if _DON_GACH_CHEO.search(text):
        text = _DON_GACH_CHEO.sub(r"\1", text)
        van_de.append(DAU_THOAT)
    return text, van_de


MO_TA = {
    FRONTMATTER: "khối thuộc tính đầu note bị biến thành đường kẻ ngang",
    DAU_THOAT: "dấu gạch chéo dồn lên trong chữ",
}


def mo_ta_van_de(van_de) -> str:
    """Câu chữ cho người đọc, không phải mã lỗi."""
    return " · ".join(MO_TA.get(v, v) for v in van_de)
