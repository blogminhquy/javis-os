"""Ảnh chèn vào note: rơi đúng thư mục images/ và máy dọn media KHÔNG được xoá nó.

    python tests/run.py anh_trong_note      (KHÔNG mạng)

Chủ repo yêu cầu chèn ảnh vào note (2026-09-11). Chỗ chết người không nằm ở chuyện tải lên mà
ở chuyện ảnh SỐNG ĐƯỢC BAO LÂU:

`media_gc.media_dirs()` coi `attachments/` và `inbox/` là VÙNG CACHE, mặc định xoá mọi file
quá 30 ngày hoặc khi vùng đó vượt trần 300MB. Tiền đề của nó là "cái gì trong đó cũng có thể
biến mất mà brain vẫn nguyên vẹn" - tiền đề đó SAI với ảnh của một note, vì có người trỏ vào.
Để ảnh note vào attachments/ thì một tháng sau mở note ra chỉ còn ô xám "ảnh không còn", không
một dòng báo nào. Nên ảnh note nằm ở `images/`, ngoài tầm máy dọn.

File này khoá hai thứ đó: thư mục logic `images` có thật và dùng được, và máy dọn không đụng
vào nó dù file đã cũ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-anh-note-"))

import media_gc  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("PASS: " if cond else "FAIL: ") + name + (("  | " + str(extra)) if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


# ── 1. Thư mục logic `images` ────────────────────────────────────────────────────────
import main as _main  # noqa: E402

check("có thư mục logic 'images' cho client gọi tên", "images" in _main._THU_MUC_LOGIC)
check("vẫn còn 'sources' và 'attachments'",
      "sources" in _main._THU_MUC_LOGIC and "attachments" in _main._THU_MUC_LOGIC)

# ── 2. Tải thật một lượt: ảnh rơi đúng chỗ ──────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402

brain = tempfile.mkdtemp(prefix="brain-anh-")
c = TestClient(_main.app, base_url="http://127.0.0.1")
r = c.post("/files/upload", data={"brain": brain, "folder": "images"},
           files={"file": ("2026-09-11-15-04-22.webp", b"RIFFxxxxWEBPVP8 ", "image/webp")}).json()
check("tải lên trả ok kèm đường dẫn đã dùng", r.get("ok") and r.get("path"), r)
check("đường dẫn trả về nằm trong images/", r.get("path", "").startswith("images/"), r)
check("file thật sự nằm trong images/",
      os.path.isfile(os.path.join(brain, "images", "2026-09-11-15-04-22.webp")),
      os.listdir(brain))
check("CANARY: KHÔNG đẻ ra attachments/ (ảnh note không dùng chung vùng cache)",
      not os.path.isdir(os.path.join(brain, "attachments")), os.listdir(brain))

# Dán hai ảnh trong cùng một giây: server phải tự tách tên, không ghi đè tấm trước.
r2 = c.post("/files/upload", data={"brain": brain, "folder": "images"},
            files={"file": ("2026-09-11-15-04-22.webp", b"RIFFyyyyWEBPVP8 ", "image/webp")}).json()
check("CANARY: hai ảnh cùng một giây thì tên thứ hai được tách ra, không ghi đè",
      r2.get("path") != r.get("path") and len(os.listdir(os.path.join(brain, "images"))) == 2,
      r2)

# Brain đặt tên kiểu "06 - Images" thì phải DÙNG LẠI, không đẻ thư mục thứ hai.
brain2 = tempfile.mkdtemp(prefix="brain-anh2-")
os.makedirs(os.path.join(brain2, "06 - Images"))
r3 = c.post("/files/upload", data={"brain": brain2, "folder": "images"},
            files={"file": ("a.webp", b"RIFF", "image/webp")}).json()
check("CANARY: dùng lại thư mục '06 - Images' có sẵn, không đẻ thư mục thứ hai",
      sorted(os.listdir(brain2)) == ["06 - Images"], sorted(os.listdir(brain2)))
check("và đường dẫn trả về trỏ đúng thư mục đó", "06 - Images/a.webp" in r3.get("path", ""), r3)

# ── 3. Máy dọn media KHÔNG được đụng vào images/ ─────────────────────────────────────
brain3 = tempfile.mkdtemp(prefix="brain-gc-")
cu = time.time() - 90 * 86400          # 90 ngày trước, quá hạn 30 ngày rất xa
for thu_muc in ("images", "attachments", "inbox"):
    os.makedirs(os.path.join(brain3, thu_muc), exist_ok=True)
    p = os.path.join(brain3, thu_muc, "anh-cu.webp")
    with open(p, "wb") as f:
        f.write(b"RIFF" * 100)
    os.utime(p, (cu, cu))

vung = media_gc.media_dirs(brain3)
check("CANARY: images/ KHÔNG nằm trong vùng cache của máy dọn",
      not any(os.path.basename(d) == "images" for d in vung), vung)
check("attachments/ và inbox/ thì vẫn là vùng cache", len(vung) == 2, vung)

kq = media_gc.sweep(brain3, max_age_days=30, max_mb=0)
check("máy dọn có xoá ảnh cũ trong vùng cache (luật vẫn chạy)", kq["files"] == 2, kq)
check("CANARY: ảnh note trong images/ VẪN CÒN sau khi dọn",
      os.path.isfile(os.path.join(brain3, "images", "anh-cu.webp")))
check("ảnh cũ trong attachments/ đã bị dọn (đúng thiết kế cũ)",
      not os.path.isfile(os.path.join(brain3, "attachments", "anh-cu.webp")))

print()
if fails:
    print("FAIL - test_anh_trong_note: %d phép thử đỏ" % len(fails))
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("OK - test_anh_trong_note: tất cả pass")
