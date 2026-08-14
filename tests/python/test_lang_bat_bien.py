"""Chốt chặn thoái lui: ngôn ngữ chỉ được biết ở SỔ ĐĂNG KÝ, không rải ra khắp mã.

    python tests/run.py lang_bat_bien

Vì sao cần một test quét mã. Lời hứa của cả tầng đa ngôn ngữ là "thêm ngôn ngữ thứ N+1 là
thêm DỮ LIỆU, không phải sửa mã". Lời hứa đó không tự giữ được: chỉ cần vài tháng và dăm lượt
sửa tính năng vội là lại có người viết `if lang == "vi"` ở một chỗ tiện tay, rồi ngôn ngữ thứ
ba lặng lẽ hỏng đúng ở đó.

Đây chính là cái bẫy tầng này sinh ra để thoát: trước khi có sổ đăng ký, "tiếng Việt" nằm rải
dưới hàng chục hình dạng (`vi-VN` ở giọng đọc, `"vi"` ở Whisper, `_THU_VN` ở đồng hồ,
`toLocaleString("vi-VN")` ở dashboard). Không ai cố ý làm thế; nó tích tụ từng dòng một.

Test này KHÔNG cấm chữ "vi" xuất hiện. Nó cấm đúng một thứ: **rẽ nhánh hành vi theo một mã
ngôn ngữ viết cứng**. Cần biết gì về một ngôn ngữ thì hỏi `lang_registry`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import pathlib
import re
import sys

GOC = pathlib.Path(__file__).resolve().parents[2]

# Những file ĐƯỢC PHÉP biết mã ngôn ngữ, vì đó là việc của chúng.
MIEN_TRU = {
    "server/lang_registry.py",   # sổ đăng ký - nơi duy nhất khai mã ngôn ngữ
    "server/lang.py",            # bộ dò/chốt - phải so mã để làm việc của nó
    "server/lexicon/__init__.py",
    "server/lexicon/vi.py",
    "server/lexicon/en.py",
}

# Rẽ nhánh hành vi theo mã ngôn ngữ viết cứng. Cố ý bắt HẸP: so sánh và startswith, chứ không
# bắt mọi chuỗi chứa "vi" (nếu không thì "service", "view", "vi phạm" đều dính).
_XAU = re.compile(
    r"""(?x)
    (?:lang|ngon_ngu|language|locale|ma_ngon_ngu)\s*(?:==|!=)\s*["'](?:vi|en)[-_a-zA-Z]*["']
    | ["'](?:vi|en)[-_a-zA-Z]*["']\s*(?:==|!=)\s*(?:lang|ngon_ngu|language|locale)
    | \.startswith\(\s*["'](?:vi|en)["']\s*\)
    """
)

_loi = []


def check(ten, dieu_kien, chi_tiet=""):
    print(f"       {'ok  ' if dieu_kien else 'FAIL'} {ten}" + (f"  {chi_tiet}" if not dieu_kien else ""))
    if not dieu_kien:
        _loi.append(ten)


def _quet(thu_muc: str, duoi: tuple) -> list:
    ra = []
    for p in sorted((GOC / thu_muc).rglob("*")):
        if p.suffix not in duoi or "__pycache__" in p.parts or "node_modules" in p.parts:
            continue
        rel = p.relative_to(GOC).as_posix()
        if rel in MIEN_TRU:
            continue
        try:
            noi_dung = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, dong in enumerate(noi_dung.split("\n"), 1):
            # Bỏ qua lời GIẢI THÍCH, chỉ soi mã CHẠY. Nói về một mã ngôn ngữ trong chú thích
            # hay docstring là chuyện tốt và nên khuyến khích - chính vì có người ghi lại
            # "trước đây chỗ này lọc cứng `startswith("vi")`" mà người sau hiểu được vì sao
            # nó đổi.
            s = dong.strip()
            if s.startswith("#") or s.startswith("//") or s.startswith("*"):
                continue
            # Đoạn trong backtick là TRÍCH MÃ trong văn xuôi (quy ước của repo này, xem
            # docs/dev/README.md). Gỡ nó ra trước khi soi, nếu không thì mọi docstring tử tế
            # giải thích bẫy cũ đều bị báo là vi phạm.
            sach = re.sub(r"`[^`]*`", "", dong)
            if _XAU.search(sach):
                ra.append(f"{rel}:{i}  {s[:76]}")
    return ra


vi_pham_py = _quet("server", (".py",))
check("server/ không rẽ nhánh theo mã ngôn ngữ viết cứng",
      not vi_pham_py, "\n              ".join(vi_pham_py[:6]))

vi_pham_js = _quet("dashboard", (".js", ".mjs"))
check("dashboard/ không rẽ nhánh theo mã ngôn ngữ viết cứng",
      not vi_pham_js, "\n              ".join(vi_pham_js[:6]))


# --- Sổ đăng ký và bộ từ vựng phải khớp nhau ---
sys.path.insert(0, str(GOC / "server"))
import lang_registry  # noqa: E402
import lexicon        # noqa: E402

check("mọi ngôn ngữ trong sổ đăng ký đều có đủ trường để dựng prompt",
      all(lang_registry.get(m).nudge and lang_registry.get(m).weekdays
          and lang_registry.get(m).clock_template and lang_registry.get(m).lang_directive
          for m in lang_registry.ma_list()))

check("mọi ngôn ngữ đều khai đủ 7 tên thứ trong tuần",
      all(len(lang_registry.get(m).weekdays) == 7 for m in lang_registry.ma_list()))

check("clock_template khai đủ 4 chỗ điền",
      all(all(k in lang_registry.get(m).clock_template
              for k in ("{hm}", "{weekday}", "{date}", "{tz}"))
          for m in lang_registry.ma_list()))

# Lexicon là TUỲ CHỌN theo thiết kế (thiếu thì cổng suy biến an toàn), nhưng đã có thì phải
# đủ tập - thiếu một tập là cổng dùng tập đó hỏng trong im lặng.
check("lexicon nào đã có thì phải khai đủ tập bắt buộc",
      all(all(hasattr(lexicon.get(m), t) for t in lexicon.BAT_BUOC)
          for m in lexicon.ma_list()))

check("mỗi lexicon phải khai được cho một ngôn ngữ CÓ trong sổ đăng ký",
      all(lang_registry.duoc_ho_tro(m) for m in lexicon.ma_list()))

print()
if _loi:
    print(f"ĐỎ {len(_loi)} mục: " + "; ".join(_loi))
    sys.exit(1)
print("Tất cả xanh.")
