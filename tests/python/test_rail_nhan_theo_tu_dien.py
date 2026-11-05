"""Regression: nhãn mục trên thanh bên phải vẽ lại khi từ điển về.

Lỗi thật 05/11/2026 (khách báo ngay sau khi cập nhật): mục đầu thanh bên hiện khoá thô
`page.chat.label` thay vì "Trò chuyện".

Cơ chế: nhãn mục là getter gọi t(), mà từ điển không phải dữ liệu phản ứng của Alpine. Store
`nav.groups` tính lại theo `i18nTick`, nhưng x-for chỉ DỰNG LẠI một khối khi khoá của nó đổi.
Nhóm thường có khoá là tên nhóm (đổi từ `nav.group.bo_nao` sang "Bộ não" khi từ điển về) nên
được dựng lại; khối "solo:chat" (Trò chuyện đứng riêng trên đầu, 0.480.0) có khoá cố định nên
giữ nguyên chữ vẽ lúc từ điển chưa về. Từ điển về chậm (máy chủ còn khởi động sau cập nhật) là lộ.

Cách chữa: chính biểu thức vẽ nhãn đọc `$store.nav.i18nTick`, nên mọi mục tự vẽ lại khi đổi chữ,
không phụ thuộc khoá của khối chứa nó.

Chạy:
    python tests/run.py rail_nhan_theo_tu_dien
"""
from _paths import ROOT  # noqa: E402

INDEX = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


_rail = INDEX.split('<div class="rail-nav">', 1)[1].split("</nav>", 1)[0]
_muc = _rail.split('<template x-for="it in g.items"', 1)[1].split("</template>", 1)[0]

check("chữ của mục rail đọc i18nTick", 'x-text="($store.nav.i18nTick, it.label)"' in _muc)
check("tooltip của mục rail đọc i18nTick", ':title="($store.nav.i18nTick, it.label)"' in _muc)
check("không còn chỗ vẽ it.label trần trong mục rail",
      'x-text="it.label"' not in _muc and ':title="it.label"' not in _muc)


if fails:
    raise SystemExit(f"\nFAIL - test_rail_nhan_theo_tu_dien: {len(fails)} lỗi")
print("\nOK - test_rail_nhan_theo_tu_dien: tất cả pass")
