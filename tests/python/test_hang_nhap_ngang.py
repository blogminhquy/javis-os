"""Regression: hàng "ô nhập + nút" trong Cài đặt nhanh không được bóp chết ô nhập.

Lỗi thật 0.9.288: ô nhập tên miền teo còn một sợi, người dùng không thấy chỗ để gõ.

Cơ chế (đáng nhớ vì còn tái diễn ở mọi hàng ngang khác trong quick-set):
  style.css từng cho MỌI nút trong `.quick-set-body` `width:100%` - đúng khi nút xếp chồng dọc.
  Nhưng trong một flex row, item mang `width:100%` có `flex-basis:auto` nên "cỡ mong muốn"
  của nó bằng TRỌN hàng. Ô nhập bên cạnh lại khai `flex:1` (tức basis 0) nên cỡ mong muốn
  của nó bằng 0. Tổng vượt chỗ chứa -> trình duyệt co lại, mà phần co chia theo basis nên
  dồn hết vào nút; ô nhập ở lại 0 và chỉ còn thấy viền.

0.58.8: luật `width:100%` đó đã BỎ HẲN cùng lúc với việc gom nút của khối này về một họ duy
nhất (.gcard-btn, họ nút của trang Cài đặt - trước đây mỗi thẻ một kiểu nút nên nút Lưu mỗi
chỗ một cỡ). Gốc sinh lỗi không còn, nhưng test này thì GIỮ: hàng ngang vẫn phải tự khai cỡ
cho cả ô nhập lẫn nút, để một luật full-width nào đó thêm vào sau này cũng không giết lại ô
nhập. Và nó canh luôn chiều ngược lại: luật cũ không được lén quay về.

Chạy:
    .venv/Scripts/python.exe tests/python/test_hang_nhap_ngang.py
"""
import re

from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path

STYLE = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")
BRANDING = (ROOT / "dashboard" / "branding.js").read_text(encoding="utf-8")
INDEX = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


# Khối CSS do branding.js tiêm lúc chạy: nối chuỗi + có chú thích xen giữa, nên gom lại
# thành một chuỗi phẳng rồi mới soi.
_inj = BRANDING.split("function _injectDomCss()", 1)[1].split("document.head.appendChild(s);", 1)[0]
DOM_CSS = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', _inj))
check("đọc được khối CSS tên miền do branding.js tiêm", ".dom-field{" in DOM_CSS)


# --- Ô nhập phải giữ được chỗ -------------------------------------------------
check("ô nhập KHÔNG dùng flex:1 (basis 0 = cỡ mong muốn 0, co là mất sạch)",
      re.search(r"\.dom-field input\{[^}]*flex:1[^ ]", DOM_CSS) is None)
check("ô nhập grow từ basis auto", re.search(r"\.dom-field input\{[^}]*flex:1 1 auto", DOM_CSS) is not None)
check("ô nhập vẫn co được ở màn hẹp (min-width:0)",
      re.search(r"\.dom-field input\{[^}]*min-width:0", DOM_CSS) is not None)
check("ô nhập tự khai kiểu (popover không có kiểu input chung nên nếu quên thì trơ mặc định trình duyệt)",
      re.search(r"\.dom-field input\{[^}]*background:var\(--field-bg\)", DOM_CSS) is not None
      and re.search(r"\.dom-field input\{[^}]*border:1px solid var\(--border\)", DOM_CSS) is not None)

# align-items:center biến "giãn hết hàng" thành "co về bề ngang nội dung". Vô hại ở hàng
# ngang, nhưng màn hẹp xoay thành CỘT thì lại đúng cái lỗi ban đầu.
check("KHÔNG đặt align-items:center cho .dom-field (màn hẹp xoay cột là ô nhập bé lại)",
      re.search(r"\.dom-field\{[^}]*align-items:center", DOM_CSS) is None)


# --- Nút không được đòi trọn hàng --------------------------------------------
check("nút Lưu để width:auto ngay tại khối tên miền",
      re.search(r"\.dom-field \.gcard-btn\{[^}]*width:auto", DOM_CSS) is not None)
check("hàng SSL khai flex cho nút (một selector phủ cả nút đặc lẫn nút ghost)",
      re.search(r"\.dom-ssl \.gcard-btn\{[^}]*flex:1 1 0", DOM_CSS) is not None)

# Luật sinh ra lỗi cũ KHÔNG được quay lại: không nút nào trong quick-set bị ép full-width
# một cách mù quáng nữa. (.gcard-btn tự nó đã width:auto - xem console.css.)
check("style.css không còn luật ép mọi nút trong quick-set full-width",
      re.search(r"\.quick-set-body \.s-btn[^{]*\{[^}]*width: 100%", STYLE) is None)

# Màn hẹp vẫn phải xếp dọc.
check("màn hẹp xếp hai hàng thành cột",
      "@media(max-width:600px){.dom-field,.dom-ssl{flex-direction:column}" in DOM_CSS)

# Markup phải khớp: nếu ai đổi class nút thì test trên thành vô nghĩa.
_field = INDEX.split('<div class="dom-field">', 1)[1].split("</div>", 1)[0]
check("markup: hàng tên miền vẫn là input + nút .gcard-btn",
      'id="setDomain"' in _field and 'class="gcard-btn" id="saveDomain"' in _field)

# Một họ nút cho CẢ khối (0.58.8). Chủ repo: "nút lưu thì lung tung hết cả lên" - trước đó
# cùng một trang có nút tím tràn ngang (.s-btn), nút viền tràn ngang (.s-btn-ghost), nút viền
# accent (.test-btn) và nút thường (.gcard-btn), mỗi thẻ một kiểu.
_qs = INDEX.split('<div class="quick-set-body">', 1)[1].split("</details>", 1)[0]
check("trong quick-set không còn nút .s-btn/.test-btn lẫn vào",
      not re.search(r'class="[^"]*\b(s-btn|s-btn-ghost|test-btn)\b', _qs))
check("nút Lưu của mỗi thẻ nằm trong hàng hành động canh phải",
      _qs.count('class="js-actions qs-foot"') >= 2
      and ".quick-set-body .js-actions.qs-foot { justify-content: flex-end;" in STYLE)


if fails:
    raise SystemExit(f"\nFAIL - test_hang_nhap_ngang: {len(fails)} lỗi")
print("\nOK - test_hang_nhap_ngang: tất cả pass")
