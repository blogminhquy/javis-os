"""Quy ước chữ trong ô nhập: placeholder phải viết hoa chữ đầu và không viết tắt.

Vì sao canh bằng test: placeholder nằm rải khắp index.html, dashboard/*.js và
system/mcp-catalog.json (mỗi connector một bộ trường riêng). Người thêm connector
mới chỉ nhìn quanh vài dòng gần đó, không thấy được cả hệ, nên chỉ vài tuần là
lại lẫn lộn "vd 123456789" với "Ví dụ: 123456789".

Hai luật:
1. Ký tự đầu phải là CHỮ HOA. Chuỗi mẫu kỹ thuật (key, URL, lệnh) thì không viết
   hoa ruột được - viết hoa là sai giá trị - nên thêm tiền tố "Ví dụ: ".
2. Không viết tắt "vd"/"VD", phải viết đủ "Ví dụ".

Chưa canh được: placeholder dựng động trong ternary (`placeholder="${a ? "x" : "y"}"`).
Quét bỏ qua chúng vì phần bắt được chỉ là mảnh biểu thức, không phải chữ hiển thị.
Số này rất ít, phải tự nhớ khi sửa.
"""
import re

from _paths import ROOT  # noqa: E402,F401

DASH = ROOT / "dashboard"
# Tra khoá i18n ra chữ tiếng Việt thật (xem chú thích trong quet()).
import json
VI = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
KHOA_I18N = re.compile(r'(?:window\.)?(?:t|tw|dich)\(\s*"([a-z0-9_.]+)"')

NGUON = ([DASH / "index.html"]
         + sorted(DASH.glob("*.js"))
         + [ROOT / "system" / "mcp-catalog.json"])

RUT = [
    re.compile(r'placeholder\s*=\s*"([^"]*)"'),
    re.compile(r"placeholder\s*=\s*'([^']*)'"),
    re.compile(r'"placeholder"\s*:\s*"((?:[^"\\]|\\.)*)"'),
    re.compile(r'\.placeholder\s*=\s*"([^"]*)"'),
    re.compile(r"\.placeholder\s*=\s*`([^`]*)`"),
]

VIET_TAT = re.compile(r"\bvd\b", re.I)

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


def _dong_cua(text, vi_tri):
    return text.count("\n", 0, vi_tri) + 1


def quet():
    """-> (danh sách chuỗi tĩnh, danh sách vi phạm)."""
    tinh, loi = [], []
    for path in NGUON:
        text = path.read_text(encoding="utf-8")
        for mau in RUT:
            for m in mau.finditer(text):
                s = m.group(1)
                if not s.strip():
                    continue
                # Placeholder đã vào từ điển i18n (0.55.54): chỗ bắt được là biểu thức
                # `' + esc(tw("khoa")) + '` chứ không còn là chữ. Tra ngược khoá ra chữ
                # THẬT rồi soát nó - bỏ qua như nhánh dưới thì luật này lặng lẽ thôi phủ
                # đúng những ô nhập vừa được dịch, tức là hở đúng chỗ vừa đụng vào.
                # Chú ý: bộ bắt ở trên dừng ngay ở dấu nháy MỞ của khoá, nên phần bắt
                # được chỉ là "' + esc(tw(". Phải soi tiếp một đoạn mã sau chỗ khớp mới
                # thấy tên khoá.
                mk = None
                if "tw(" in s or "t(" in s or "esc(" in s:
                    mk = KHOA_I18N.search(text, m.start(), m.start() + 400)
                if mk:
                    s = VI.get(mk.group(1), "")
                    if not s.strip():
                        continue
                # Dựng động: phần bắt được là mảnh biểu thức, không phải chữ hiển thị.
                elif "${" in s or s.lstrip().startswith("' +") or s.lstrip().startswith('" +'):
                    continue
                tinh.append(s)
                dau = s.lstrip()[:1]
                if not dau.isupper():
                    loi.append((path.name, _dong_cua(text, m.start()), "chữ đầu chưa viết hoa", s))
                elif VIET_TAT.search(s):
                    loi.append((path.name, _dong_cua(text, m.start()), "còn viết tắt 'vd'", s))
    return tinh, loi


tinh, loi = quet()

check(f"tìm thấy placeholder để soát (đang có {len(tinh)} chuỗi)", len(tinh) > 40)
check(f"mọi placeholder viết hoa chữ đầu và không viết tắt (thấy {len(loi)} lỗi)", not loi)
for ten, dong, vi_sao, s in loi[:20]:
    print(f"      {ten}:{dong} - {vi_sao} | {s[:70]}")

# Tiền tố dùng cho chuỗi mẫu kỹ thuật phải viết ĐỦ, không rơi lại thành "VD:".
check("tiền tố ví dụ viết đủ chữ", all(not s.startswith(("VD:", "Vd:", "vd:")) for s in tinh))

if fails:
    raise SystemExit(f"\nFAIL - test_placeholder_ui: {len(fails)} lỗi")
print("\nOK - test_placeholder_ui: tất cả pass")
