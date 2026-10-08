"""Nút Cập nhật ngay chờ đến khi bản mới lên rồi tự tải lại, không báo lỗi sớm (0.85.9).

    python tests/run.py cap_nhat_cho_den_khi_xong      (KHÔNG mạng)

Lỗi thật, chủ repo báo 08/10/2026 kèm ảnh: bấm Cập nhật ngay trên bản Docker, ít lâu sau trang
báo "Bản mới chưa lên sau một lúc - có thể lỗi.", rồi ngay sau đó tự tải lại lên đúng bản mới.
Gốc: trang chỉ chờ 12 lần dò x 3 giây = 36 giây, còn Watchtower phải kéo cả image mới về, máy
yếu hay mạng chậm thì lâu hơn thế. Việc cập nhật không hề lỗi, chỉ có trang bỏ cuộc sớm.

Lỗi THẬT thì server đã tự ghi vào /update/status (Watchtower báo lỗi, không thấy image mới,
rollback), và vòng dò dừng ngay theo đó. Nên chỉ hết hẳn 10 phút mà vẫn im mới coi là kẹt.

Điều được ghim:
  1. Không còn mốc bỏ cuộc theo số lần dò (`tries >= 12`) ở cả hai nút (trang Cài đặt và Tổng quan).
  2. Trần chờ là 10 phút, tính theo đồng hồ chứ không theo số lần dò.
  3. Quá 45 giây thì đổi câu chữ sang "vẫn đang kéo", spinner vẫn quay, không hiện cảnh báo.
  4. Đang chờ cập nhật mà người gác cổng phiên bản (freshness.js) thấy bản mới thì tải lại luôn,
     không hiện thêm thanh "Tải lại / Để sau".
  5. Lỗi thật vẫn dừng ngay: nhánh result error/pull_failed/rolled_back còn nguyên.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CONSOLE = (DASHBOARD / "console.js").read_text(encoding="utf-8")
FRESH = (DASHBOARD / "freshness.js").read_text(encoding="utf-8")
VI = json.loads((DASHBOARD / "i18n" / "vi.json").read_text(encoding="utf-8"))
EN = json.loads((DASHBOARD / "i18n" / "en.json").read_text(encoding="utf-8"))

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


def poller(start_marker):
    """Thân hàm onclick của một nút Cập nhật ngay, từ lúc bắt đầu dò tới hết setInterval."""
    i = CONSOLE.index(start_marker)
    j = CONSOLE.index("}, 3000);", i)
    return CONSOLE[i:j]


SETTINGS = poller('status.innerHTML = ic("loader", { cls: "ic-spin" }) + " " + window.t("cs.upd_running_now");')
OVERVIEW = poller('st.innerHTML = ic("loader", { cls: "ic-spin" }) + " " + esc(window.t("cs.upd_running_now"));')

check("không còn mốc bỏ cuộc theo số lần dò", not re.search(r"tries\s*>=?\s*\d", CONSOLE))
check("không còn câu 'có thể lỗi' báo sớm", "cs.upd_slow" not in CONSOLE and "cs.upd_slow" not in VI)

m = re.search(r"const UPD_WAIT_MS = ([\d\s*]+);", CONSOLE)
check("trần chờ 10 phút", m and eval(m.group(1)) == 10 * 60 * 1000, m and m.group(1))
m = re.search(r"const UPD_LONG_MS = ([\d\s*]+);", CONSOLE)
check("quá 45 giây thì nói rõ là vẫn đang kéo", m and eval(m.group(1)) == 45 * 1000, m and m.group(1))

for ten, body in (("trang Cài đặt", SETTINGS), ("trang Tổng quan", OVERVIEW)):
    check(f"{ten}: tính giờ bằng đồng hồ", "Date.now() - t0" in body and "waited >= UPD_WAIT_MS" in body)
    check(f"{ten}: câu 'vẫn đang kéo' đi kèm spinner, không phải cảnh báo",
          re.search(r'ic\("loader", \{ cls: "ic-spin" \}\) \+ " " \+ (esc\()?window\.t\("cs\.upd_pulling_long"\)', body))
    check(f"{ten}: báo trang đang chờ cập nhật", "window.__javisUpdating = true" in body)
    check(f"{ten}: bản mới lên thì tự tải lại", "location.reload()" in body)
    check(f"{ten}: lỗi thật vẫn dừng ngay",
          "rolled_back" in body and "pull_failed" in body and "\"error\"" in body)
    check(f"{ten}: mọi lối ra thất bại đều nhả cờ đang chờ",
          body.count("window.__javisUpdating = false") >= 3, body.count("window.__javisUpdating = false"))

i = FRESH.index("function kiemPhienBan")
seg = FRESH[i:FRESH.index("setInterval(kiemPhienBan", i)]
check("freshness.js: đang chờ cập nhật thì tải lại luôn, không hỏi",
      "if (window.__javisUpdating) { location.reload(); return; }" in seg
      and seg.index("__javisUpdating") < seg.index("baoCoBanMoi("))

for lang, d in (("vi", VI), ("en", EN)):
    check(f"{lang}: có câu 'vẫn đang kéo'", bool(d.get("cs.upd_pulling_long")))
    check(f"{lang}: câu hết giờ nói đúng 10 phút", "10" in d.get("cs.upd_timeout", ""))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
