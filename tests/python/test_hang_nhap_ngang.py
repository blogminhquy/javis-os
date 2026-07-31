"""Regression: hàng "ô nhập + nút" trong Cài đặt nhanh không được bóp chết ô nhập.

Lỗi thật 0.9.288: ô nhập tên miền teo còn một sợi, người dùng không thấy chỗ để gõ.

Cơ chế (đáng nhớ vì còn tái diễn ở mọi hàng ngang khác trong quick-set):
  style.css cho MỌI nút trong `.quick-set-body` `width:100%` - đúng khi nút xếp chồng dọc.
  Nhưng trong một flex row, item mang `width:100%` có `flex-basis:auto` nên "cỡ mong muốn"
  của nó bằng TRỌN hàng. Ô nhập bên cạnh lại khai `flex:1` (tức basis 0) nên cỡ mong muốn
  của nó bằng 0. Tổng vượt chỗ chứa -> trình duyệt co lại, mà phần co chia theo basis nên
  dồn hết vào nút; ô nhập ở lại 0 và chỉ còn thấy viền.

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
      re.search(r"\.dom-field \.s-btn\{[^}]*width:auto", DOM_CSS) is not None)
check("hàng SSL khai flex cho CẢ HAI nút (trước đây bỏ sót nút ghost)",
      re.search(r"\.dom-ssl \.s-btn,\.dom-ssl \.s-btn-ghost\{[^}]*flex:1 1 0", DOM_CSS) is not None)

# style.css là nơi sinh ra width:100%, nên phải có ngoại lệ ngay tại đó - và specificity
# phải đủ 3 lớp để thắng bất kể thứ tự nạp (CSS tên miền do JS tiêm lúc chạy).
check("style.css vẫn cho nút xếp dọc full-width (hành vi cũ giữ nguyên)",
      ".quick-set-body .s-btn, .quick-set-body .s-btn-ghost, .quick-set-body .test-btn { width: 100%; }" in STYLE)
_exc = re.search(r"\.quick-set-body \.dom-field \.s-btn,\s*"
                 r"\.quick-set-body \.dom-ssl \.s-btn,\s*"
                 r"\.quick-set-body \.dom-ssl \.s-btn-ghost \{ width: auto; \}", STYLE)
check("style.css có ngoại lệ cho nút trong hàng ngang, đủ 3 lớp class", _exc is not None)
check("ngoại lệ đứng SAU rule width:100% trong style.css",
      _exc is not None and _exc.start() > STYLE.index(".quick-set-body .s-btn, .quick-set-body .s-btn-ghost"))

# Màn hẹp vẫn phải xếp dọc.
check("màn hẹp xếp hai hàng thành cột",
      "@media(max-width:600px){.dom-field,.dom-ssl{flex-direction:column}" in DOM_CSS)

# Markup phải khớp: nếu ai đổi class nút thì test trên thành vô nghĩa.
_field = INDEX.split('<div class="dom-field">', 1)[1].split("</div>", 1)[0]
check("markup: hàng tên miền vẫn là input + nút .s-btn",
      'id="setDomain"' in _field and 'class="s-btn" id="saveDomain"' in _field)


if fails:
    raise SystemExit(f"\nFAIL - test_hang_nhap_ngang: {len(fails)} lỗi")
print("\nOK - test_hang_nhap_ngang: tất cả pass")
