"""Người gác cổng bản cũ: trang phải biết mình đang chạy code KHÔNG khớp với máy chủ.

    python tests/run.py phat_hien_ban_cu      (KHÔNG mạng)

Lỗi thật, chủ repo báo 03/09/2026: "up file vẫn không chọn được nhiều file" - sau khi bản
vá ĐÃ lên main và máy chủ ĐÃ cập nhật. Hoá ra trình duyệt chạy `sessions-ui.js` CŨ, trong
khi dòng chữ ngay cạnh chính cái ô đó lại là chữ MỚI. Hai thứ đi hai đường khác nhau:

    từ điển i18n   -> fetch kèm `cache: no-cache`          -> LUÔN hỏi lại máy chủ, luôn mới
    file .js/.css  -> `?v=<phiên bản>` + cache 1 năm immutable -> đứng yên nếu có tầng cache
                                                                 nào bỏ qua phần `?v=`

Đây là kiểu hỏng tệ nhất vì nó CÂM: người dùng thấy bản vá "không ăn" rồi kết luận code
sai, còn người sửa thì không tài nào tái hiện. Repo đã vấp đúng chuyện này một lần trước
đó - chú thích trong `root()` kể lại vụ console.js đứng yên suốt hàng chục bản.

Hai điều then chốt mà test này ghim:

1. **So SỐ PHIÊN BẢN là không đủ.** Ở đúng ca trên, số phiên bản KHỚP mà nội dung thì cũ.
   Nên phải so chính NỘI DUNG: server nhúng crc32 từng file vào trang, `freshness.js` tải
   lại đúng URL ấy (lấy từ cache, không tốn mạng) rồi băm và đối chiếu.

2. **Điểm tựa phải luôn mới.** `index.html` trả kèm `no-store` nên nó luôn mới kể cả khi
   mọi file quanh nó đã cũ - khối `<script id="javis-fresh">` vì vậy luôn nói thật. Và
   `freshness.js` nạp KHÔNG kèm `?v=`, được đóng dấu `no-cache`: người gác cổng mà cũ theo
   thì nó gác cái gì.

Bốn nhánh của lớp này đã được chạy thử bằng Chromium thật trước khi commit: mọi file mới ->
im lặng; một file bị giữ bản cũ -> gọi đúng tên file; tải lại rồi vẫn cũ -> đổi sang câu chỉ
thẳng cách làm; máy chủ đổi phiên bản -> mời tải lại.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import re
import zlib

MAIN = (SERVER / "main.py").read_text(encoding="utf-8")
FRESH = (DASHBOARD / "freshness.js").read_text(encoding="utf-8")
INDEX = (DASHBOARD / "index.html").read_text(encoding="utf-8")

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


# ============================================================
# 1. Máy chủ: vân tay nội dung + cổng hỏi lại rẻ tiền
# ============================================================
check("có hàm băm vân tay từng file tĩnh", "def _asset_fp_one" in MAIN)
check("dùng zlib.crc32 (tốc độ C, khớp được với JS)", "zlib.crc32" in MAIN)
check("nhớ theo (mtime, size) nên gọi lại vẫn rẻ",
      "st.st_mtime_ns, st.st_size" in MAIN)
check("có cổng /app-version cho trang hỏi lại", '@app.get("/app-version")' in MAIN)

_av = MAIN.split("async def app_version", 1)[1].split("\n@app.", 1)[0]
# Soi phần MÃ CHẠY, không soi chú thích: docstring của nó có nhắc "/version đi hỏi GitHub"
# để giải thích vì sao hai cổng phải tách nhau, mà bắt cả chữ trong chú thích là bắt oan.
_av_ma = "\n".join(d for d in _av.split("\n")
                   if not d.strip().startswith("#") and '"""' not in d)
check("CANARY: /app-version KHÔNG chạm mạng (khác /version đi hỏi GitHub, timeout 8 giây)",
      "httpx" not in _av_ma and "AsyncClient" not in _av_ma, _av_ma[:120])
check("và trả cả phiên bản lẫn vân tay", '"version"' in _av and '"assets"' in _av)

_root = MAIN.split("async def root()", 1)[1].split("\n@app.", 1)[0]
check("trang nhúng khối javis-fresh", 'id="javis-fresh"' in _root)
# Regex tìm vân tay bám vào `?v=`, nên tính SAU khi đã đổi `?v=` là ra rỗng sạch.
check("CANARY: vân tay tính TRƯỚC khi viết lại ?v= (tính sau là ra rỗng)",
      _root.index("_asset_fps(html)") < _root.index("re.sub("), _root[:200])
check("index.html vẫn trả no-store (điểm tựa phải luôn mới)",
      "no-cache, no-store, must-revalidate" in _root)

# ============================================================
# 2. Người gác cổng không được phép cũ theo
# ============================================================
check("CANARY: freshness.js được đóng dấu no-cache",
      'request.url.path == "/static/freshness.js"' in MAIN
      and MAIN.split('request.url.path == "/static/freshness.js"', 1)[1][:200].count("no-cache") >= 1)
check("CANARY: index.html nạp freshness.js KHÔNG kèm ?v=",
      '<script src="/static/freshness.js"></script>' in INDEX)
# Nạp sau các file khác thì một file phía trên hỏng vì chạy bản cũ là nó chết theo, đúng
# lúc cần nó nhất.
check("và nạp SỚM, trước cả i18n",
      INDEX.index("/static/freshness.js") < INDEX.index("/static/i18n/index.js"))

# ============================================================
# 3. crc32 hai bên phải khớp TỪNG BIT, không thì gác cổng báo oan cả ngày
# ============================================================
check("freshness.js tự cài crc32, không GỌI crypto.subtle",
      "0xEDB88320" in FRESH and "crypto.subtle.digest" not in FRESH)
# Vì sao không dùng crypto.subtle: nó chỉ tồn tại trong ngữ cảnh bảo mật, mà Javis rất hay
# chạy trên http:// theo IP của VPS - dùng nó là người gác cổng chết lặng đúng lúc cần nhất.
check("CANARY: có ghi lý do không dùng crypto.subtle (http:// theo IP là ca thật)",
      "ngữ cảnh bảo mật" in FRESH)

# Đối chiếu thuật toán: bảng CRC-32 chuẩn (đa thức 0xEDB88320) phải cho ra ĐÚNG zlib.crc32.
def _crc32_kieu_js(data: bytes) -> str:
    bang = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (0xEDB88320 ^ (c >> 1)) if (c & 1) else (c >> 1)
        bang.append(c & 0xFFFFFFFF)
    c = 0xFFFFFFFF
    for b in data:
        c = bang[(c ^ b) & 0xFF] ^ (c >> 8)
    return format((c ^ 0xFFFFFFFF) & 0xFFFFFFFF, "08x")


for _ten in ("freshness.js", "sessions-ui.js", "style.css"):
    _b = (DASHBOARD / _ten).read_bytes()
    check(f"crc32 kiểu JS khớp zlib.crc32 trên {_ten}",
          _crc32_kieu_js(_b) == format(zlib.crc32(_b) & 0xFFFFFFFF, "08x"))
# Chuỗi có dấu tiếng Việt: hai bên phải cùng băm trên BYTE UTF-8, không phải trên ký tự.
_vn = "Bấm để chọn file từ máy (chọn được nhiều)".encode("utf-8")
check("và khớp cả trên chuỗi UTF-8 có dấu (băm theo byte, không theo ký tự)",
      _crc32_kieu_js(_vn) == format(zlib.crc32(_vn) & 0xFFFFFFFF, "08x"))

# ============================================================
# 4. Hành vi: đo đúng thứ cần đo, và không tự ý cướp trang của người dùng
# ============================================================
# Ép làm mới là đo file trên MÁY CHỦ, tức đo nhầm đầu: cần đo đúng bản trình duyệt đang
# chạy, nghĩa là để nguyên chế độ cache mặc định.
check("CANARY: tải file KHÔNG ép làm mới (phải đo đúng bản đang chạy)",
      'cache: "reload"' not in FRESH and 'cache: "no-cache"' not in FRESH)
check("nhưng /app-version thì hỏi thẳng máy chủ", 'cache: "no-store"' in FRESH)
# Tự tải lại là cướp mất câu người dùng đang gõ dở - tệ hơn hẳn cái nó chữa.
check("CANARY: KHÔNG tự động tải lại trang, chỉ mời",
      "location.reload()" in FRESH and "KHÔNG tự tải lại trang" in FRESH)
check("có chống vòng lặp tải lại vô tận", "javis-fresh-reloaded" in FRESH)
check("tải lại rồi vẫn cũ thì đổi sang câu chỉ thẳng cách làm",
      "Ctrl+Shift+R" in FRESH)
check("gọi ĐÚNG TÊN file đang cũ (để còn lần ra tầng cache nào giữ)",
      "ds.slice(0, 3).join" in FRESH)
check("đo SAU khi trang dựng xong, không làm chậm lúc mở app",
      'addEventListener("load"' in FRESH)
check("server chưa nhúng khối (bản cũ) thì im lặng, không phá gì",
      "if (!m) return;" in FRESH)
check("không dùng em dash trong mã nguồn (luật CLAUDE.md)", "—" not in FRESH)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + "; ".join(_fails[:4]))
    raise SystemExit(1)
print("Tất cả xanh.")
