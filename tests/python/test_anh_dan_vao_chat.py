"""Ảnh dán vào khung chat phải XEM LẠI ĐƯỢC, và hết hạn thì nói thẳng là hết hạn.

    python tests/run.py anh_dan_vao_chat      (KHÔNG mạng)

Chủ repo báo 01/09: *"gửi ảnh vào javis để javis đọc thì sẽ không lưu lại tấm ảnh đó ở đoạn
chat, và khi dán ảnh vào cũng không zoom lên được"*.

Bong bóng tin của người dùng hiện ảnh bằng `URL.createObjectURL(file)` - một URL chỉ sống
trong tab đang mở, mà `clearAttachments()` lại thu hồi nó NGAY sau khi gửi. Thêm nữa lịch sử
chỉ lưu `{name, kind}`, không lưu chỗ nào để trỏ tới. Nên ảnh vừa gửi đã hỏng, F5 một cái là
mất hẳn, còn trơ cái tên file.

Chữa bằng một đường đọc lại chính file trong thư mục stage tạm. File này canh phần MÁY CHỦ:
`/upload` trả kèm URL đó, `/upload/raw` phục vụ file có thật, chặn mọi kiểu trèo thư mục, và
trả 404 khi file đã bị `media_gc.sweep_staging` dọn - 404 là TÍN HIỆU để dashboard vẽ khung
"không còn xem lại được", nên nó phải là 404 chứ không phải 500 hay một trang lỗi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-anhchat-test-")

import main  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


main.cfgmod.gate_active = lambda: False   # test không đụng auth thật
# base_url phải là IP: chưa bật cổng đăng nhập thì web_security siết Host để chống
# DNS-rebinding, mà "testserver" mặc định của TestClient không nằm trong allowlist.
client = TestClient(main.app, base_url="http://127.0.0.1")

# PNG 1x1 thật (không phải chuỗi bừa): endpoint đoán kiểu MIME theo đuôi file, và ta muốn
# kiểm cả phần "trình duyệt nhận đúng image/png" chứ không chỉ mã 200.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100fdff03fa0000000049454e44ae426082")


# ============================================================
# 1. /upload trả kèm ĐƯỜNG XEM LẠI, không chỉ đường trên đĩa
# ============================================================
r = client.post("/upload", files={"file": ("anh dán.png", _PNG, "image/png")})
up = r.json()
check("/upload nhận ảnh", r.status_code == 200 and up.get("ok"), up)
check("nhận diện là ảnh", up.get("kind") == "image", up.get("kind"))
check("có trường `url` để bong bóng chat trỏ vào (thứ trước đây thiếu hẳn)",
      bool(up.get("url")), up)
check("url đi qua /upload/raw", str(up.get("url", "")).startswith("/upload/raw?name="),
      up.get("url"))
# Tên có dấu và có khoảng trắng phải được mã hoá, không thì URL gãy ngay ở dấu cách.
check("tên file có dấu được mã hoá trong url", " " not in str(up.get("url", "")), up.get("url"))


# ============================================================
# 2. /upload/raw phục vụ lại đúng file đó
# ============================================================
r2 = client.get(up["url"])
check("/upload/raw trả về ảnh", r2.status_code == 200, r2.status_code)
check("đúng byte của file đã tải lên", r2.content == _PNG)
check("kiểu MIME là image/png (trình duyệt mới chịu vẽ trong <img>)",
      "image/png" in (r2.headers.get("content-type") or ""), r2.headers.get("content-type"))
check("hiện INLINE chứ không ép tải về",
      "inline" in (r2.headers.get("content-disposition") or ""),
      r2.headers.get("content-disposition"))
check("có nosniff (file do người dùng tải lên - đừng để trình duyệt tự đoán kiểu)",
      r2.headers.get("x-content-type-options") == "nosniff")

r2b = client.get(up["url"] + "&dl=1")
check("dl=1 thì ép tải về kèm tên file (nút Tải về của lightbox)",
      r2b.status_code == 200 and "attachment" in (r2b.headers.get("content-disposition") or ""),
      r2b.headers.get("content-disposition"))


# ============================================================
# 3. Hết hạn -> 404, và 404 mới là thứ dashboard vẽ được khung "mất ảnh"
# ============================================================
r3 = client.get("/upload/raw?name=khong-he-ton-tai-9f3.png")
check("file đã dọn -> 404 (không phải 500)", r3.status_code == 404, r3.status_code)

# Dọn thật bằng chính hàm media_gc chạy trong đời thật, rồi kiểm lại - để test không chỉ tin
# vào một cái tên bịa ra.
import media_gc  # noqa: E402
import time  # noqa: E402

# Lùi mtime 10 ngày = đúng cảnh đời thật (file nằm đó vài ngày rồi vòng dọn chạy qua), thay vì
# ép max_age_days=0 - hạn 0 ngày là ca không bao giờ xảy ra và nó không chứng minh được gì.
os.utime(up["staged"], (time.time() - 10 * 86400,) * 2)
media_gc.sweep_staging(str(main.STAGING), max_age_days=3)
r4 = client.get(up["url"])
check("sau khi media_gc dọn staging thì cũng 404", r4.status_code == 404, r4.status_code)


# ============================================================
# 4. Không trèo ra khỏi staging
# ============================================================
_ac = ["../config.json", "..%2Fconfig.json", "../../etc/passwd", "a/b.png", "..\\\\x.png",
       ".", "..", ""]
for ten in _ac:
    rr = client.get("/upload/raw", params={"name": ten})
    check(f"chặn tên nguy hiểm: {ten!r} -> {rr.status_code}", rr.status_code in (400, 404, 422),
          rr.status_code)

# Cả ở tầng hàm thuần, để lỗi hiện ra là ValueError chứ không phải một đường dẫn hợp lệ.
for ten in ("../x", "a/b", "..", ".", "", "  "):
    try:
        main._duong_staging(ten)
        check(f"_duong_staging({ten!r}) phải từ chối", False)
    except ValueError:
        check(f"_duong_staging({ten!r}) từ chối đúng", True)

# Tên hợp lệ vẫn phải đi qua được, không thì rào siết quá tay.
_ok = main._duong_staging("paste-123.png")
check("_duong_staging nhận tên thường", _ok.parent == main.STAGING.resolve(), _ok)


# ============================================================
# 5. CANARY: đừng ai gỡ `url` khỏi /upload
# ============================================================
_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: /upload còn trả trường url", '"url": "/upload/raw?name="' in _src)
check("CANARY: /upload/raw còn kiểm lại thư mục cha sau khi resolve",
      "if f.parent != goc:" in _src)

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("TẤT CẢ PASS")
