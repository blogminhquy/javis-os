"""
media_gc.py - Dọn vùng cache media của brain.

Vì sao tồn tại: ảnh Javis tự tạo (image_gen.py:202) và file user gửi qua Telegram
(main.py:6242) rơi vào `<brain>/attachments/` và `<brain>/inbox/` rồi nằm đó vĩnh viễn.
Không ai dọn, mà trước đây chúng còn được commit vào git của brain nên xoá file cũng
không lấy lại được dung lượng. Quyết định: hai thư mục đó là VÙNG CACHE, không phải tri
thức. Tri thức là file .md. Cái gì trong đó cũng có thể biến mất mà brain vẫn nguyên vẹn.

Tách làm hai tầng để test được:
  - plan_deletions: THUẦN. Nhận sẵn danh sách (path, size, mtime), trả danh sách cần xoá.
    Không chạm đĩa, không đọc đồng hồ -> test không cần fixture.
  - scan / media_dirs / sweep: chạm đĩa. Dùng os.scandir và phải gọi qua asyncio.to_thread.

Stdlib-only.
"""
from __future__ import annotations

import os
import re
import time


def plan_deletions(entries, now, max_age_days, max_mb, keep_md=True):
    """Quyết định file nào phải xoá. HÀM THUẦN.

    entries      : list[(path, size_bytes, mtime)] - mọi file trong vùng cache của MỘT brain.
    now          : mốc thời gian tham chiếu (time.time()).
    max_age_days : file già hơn ngần này ngày thì xoá. <= 0 = tắt luật tuổi.
    max_mb       : trần dung lượng vùng cache. <= 0 = tắt luật trần.
    keep_md      : True (mặc định) = không bao giờ xoá .md, vì vùng cache của brain có thể
                   lạc note vào mà note là tri thức. Đặt False cho thư mục THUẦN trung chuyển
                   (staging), nơi một file .md chỉ là thứ user vừa dán vào chat, không phải note.

    Trả list path theo ĐÚNG thứ tự xoá: nhóm quá hạn trước, rồi nhóm bị trần cắt (cũ tới mới).
    """
    giu = [t for t in entries
           if not (keep_md and str(t[0]).lower().endswith(".md"))]
    xoa, con_lai = [], []
    if max_age_days and max_age_days > 0:
        han = now - max_age_days * 86400.0
        for t in giu:
            (xoa if t[2] < han else con_lai).append(t)
    else:
        con_lai = list(giu)
    if max_mb and max_mb > 0:
        tran = max_mb * 1024 * 1024
        tong = sum(t[1] for t in con_lai)
        # Trần là van an toàn cho trường hợp sinh cả trăm ảnh trong một ngày: lúc đó
        # luật tuổi chưa kịp cứu. Xoá từ CŨ NHẤT và dừng ngay khi xuống dưới trần.
        for t in sorted(con_lai, key=lambda x: x[2]):
            if tong <= tran:
                break
            xoa.append(t)
            tong -= t[1]
    return [t[0] for t in xoa]


# Cùng luật nhận diện thư mục attachments với image_gen.py:40 và main.py:1931: tên có thể là
# "attachments", "Attachments", hay có tiền tố số thứ tự kiểu "05 - attachments".
_ATTACH_RE = r"^(\d+\s*[-_.]\s*)?attachments$"


def media_dirs(brain_root, attachments=True):
    """Các thư mục VÙNG CACHE cấp 1 của brain: attachments (mọi biến thể tên) + inbox.

    attachments=False: CHỈ inbox. Dùng khi bật đồng bộ ảnh lên GitHub (backup.sync_images) -
    lúc đó attachments/ không còn là cache dùng-xong-vứt nữa mà là thứ người dùng muốn GIỮ:
    để máy dọn xoá ảnh quá hạn thì lượt sync sau ghi nhận "đã xoá" rồi lan sang mọi máy,
    ảnh backup tự biến mất đúng hạn. inbox thì vẫn dọn - nó không bao giờ được sync."""
    ra = []
    try:
        with os.scandir(brain_root) as it:
            for d in it:
                try:
                    if not d.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                ten = d.name.strip()
                if ten.lower() == "inbox":
                    ra.append(d.path)
                elif attachments and re.match(_ATTACH_RE, ten, re.IGNORECASE):
                    ra.append(d.path)
    except OSError:
        pass
    return ra


def scan(dirs):
    """Duyệt đệ quy các thư mục -> list[(path, size, mtime)].

    Dùng os.scandir chứ KHÔNG dùng glob: glob đi hết cây rồi mới cắt nên không có trần thật,
    và stat đi kèm entry của scandir thì rẻ hơn hẳn stat riêng từng file. Lỗi từng file
    (đang bị khoá, vừa bị xoá, thiếu quyền) thì bỏ qua chứ không làm hỏng cả lượt quét.
    """
    ra = []
    for d in dirs:
        stack = [d]
        while stack:
            cur = stack.pop()
            try:
                with os.scandir(cur) as it:
                    for x in it:
                        try:
                            if x.is_dir(follow_symlinks=False):
                                stack.append(x.path)
                            elif x.is_file(follow_symlinks=False):
                                st = x.stat()
                                ra.append((x.path, st.st_size, st.st_mtime))
                        except OSError:
                            continue
            except OSError:
                continue
    return ra


def _xoa(can_xoa, kich_thuoc):
    """Xoá thật danh sách path, trả {"files", "bytes"}. Lỗi từng file thì bỏ qua: file vừa bị
    xoá tay hoặc đang bị tiến trình khác giữ -> để lượt sau dọn, không làm hỏng cả lượt."""
    n, b = 0, 0
    for p in can_xoa:
        try:
            os.remove(p)
        except OSError:
            continue
        n += 1
        b += kich_thuoc.get(p, 0)
    return {"files": n, "bytes": b}


def sweep(brain_root, max_age_days=30, max_mb=300, now=None, attachments=True):
    """Dọn vùng cache của MỘT brain. CHẶN vì đụng đĩa - phải gọi qua asyncio.to_thread.

    attachments=False (đang bật đồng bộ ảnh): chỉ dọn inbox, xem media_dirs.
    Trả {"files": số file đã xoá, "bytes": tổng byte đã giải phóng}.
    """
    entries = scan(media_dirs(brain_root, attachments=attachments))
    can_xoa = plan_deletions(entries, float(now if now is not None else time.time()),
                             max_age_days, max_mb)
    return _xoa(can_xoa, {t[0]: t[1] for t in entries})


def sweep_staging(staging_root, max_age_days=3, now=None):
    """Dọn thư mục stage tạm (STATE_DIR/.staging, xem main.py:1779): nơi file user dán hoặc
    tải lên khung chat rơi xuống trước khi engine đọc.

    Đây là đường phình thứ tư, và trên máy phát triển nó còn to hơn attachments (114MB / 62
    tệp, file cũ nhất 27 ngày, lúc đo 2026-07-29). Nó không nằm trong vault nên không dính
    git, nhưng vẫn ăn đĩa VPS y như mọi thứ khác.

    Khác sweep vùng cache brain ở hai điểm, cả hai đều vì staging là chỗ TRUNG CHUYỂN thuần:
      - KHÔNG chừa .md. Không ai cuộn lại lịch sử để mở file staging (chat không nhúng đường
        dẫn staging bao giờ), nên .md ở đây là rác chứ không phải tri thức.
      - Chỉ có luật tuổi, không trần dung lượng: hạn mặc định 3 ngày đã đủ chặt.
    """
    entries = scan([staging_root])
    can_xoa = plan_deletions(entries, float(now if now is not None else time.time()),
                             max_age_days, 0, keep_md=False)
    return _xoa(can_xoa, {t[0]: t[1] for t in entries})
