"""Năng lực MẶC ĐỊNH của Javis phải gỡ được, và trạng thái "đã gỡ" ghi ở STATE_DIR.

Vì sao cần một module cho một file JSON
---------------------------------------
Đích đến chủ dự án đặt ra (2026-09-03): bao giờ có kho thì xoá bớt, để lại đúng cấu trúc mặc
định của Javis, còn lại người dùng tự chọn cài thêm plugin, skill hay kết nối. Bây giờ chưa xoá
gì, nhưng cấu trúc phải sẵn từ trước, nếu không thì ngày xoá là một lần vá vội giữa đường.

Cấu trúc đó chỉ cần một ý: **"đã gỡ" là DỮ LIỆU NGƯỜI DÙNG, không phải trạng thái của mã
nguồn.** Cây code là read-only trên Docker (`Dockerfile:81,112`) và bị `git pull` ghi đè trên
bản native (`update.sh`), nên STATE_DIR là chỗ DUY NHẤT một lựa chọn sống được qua cập nhật.
Đây cũng đúng khuôn `plugins_host` đã dùng cho plugin bundled: enable-state của plugin đi kèm
app nằm ở `STATE_DIR/plugins.json`, không sửa vào `plugin.yaml` của app.

"Gỡ" khác "xoá file", và khác có chủ ý
--------------------------------------
Với thứ ship kèm app, gỡ nghĩa là biến mất khỏi danh sách chính, khỏi mọi engine, khỏi prompt;
file vẫn nằm trong image. Xoá file thật thì trên Docker `EACCES`, còn trên bản native thì lượt
`git pull` sau đó mọc lại - một thứ "đã xoá" mà tự quay về thì tệ hơn một thứ đang tắt. Đổi lại,
gỡ được thì cài lại được bằng một cú bấm, và chính điều đó làm nó không đáng sợ.

Gỡ một connector lõi KHÔNG xoá kết nối đã đấu theo nó: kết nối là dữ liệu của người dùng,
connector chỉ là cái khuôn. Gỡ khuôn mà kết nối còn thì kết nối thành MỒ CÔI, và `mcp_store`
phải từ chối dựng dial spec cho nó thay vì âm thầm chạy với quyền mặc định.
"""
from __future__ import annotations

import json
import sys
import threading

from config import STATE_DIR

STORE = STATE_DIR / "core-off.json"

# Các loại năng lực mặc định có thể gỡ. Khoá trong file JSON đúng bằng tên loại.
LOAI = ("connectors",)

_lock = threading.RLock()
# Cache theo (mtime_ns, size) chứ không chỉ mtime: mtime trên vài hệ tệp chỉ chính xác tới
# giây, mà gỡ rồi cài lại liền trong cùng một giây đúng là thao tác người dùng hay làm nhất.
# Cùng lý do với `plugins_host.invalidate`.
_cache: dict = {"sig": None, "data": {}}


def _doc() -> dict:
    with _lock:
        try:
            st = STORE.stat()
            sig = (st.st_mtime_ns, st.st_size)
        except OSError:
            _cache.update(sig=None, data={})
            return _cache["data"]
        if _cache["sig"] == sig:
            return _cache["data"]
        try:
            d = json.loads(STORE.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                raise ValueError("gốc phải là object")
        except Exception as e:
            # File hỏng thì coi như CHƯA GỠ GÌ, không phải gỡ hết. Suy biến phải nghiêng về
            # "người dùng thấy đủ năng lực" chứ không phải "Javis đột nhiên trống rỗng".
            print(f"[core_off] lỗi đọc {STORE.name}: {e}", file=sys.stderr)
            _cache.update(sig=sig, data={})
            return _cache["data"]
        sach = {k: sorted({str(x) for x in (d.get(k) or []) if str(x).strip()}) for k in LOAI}
        _cache.update(sig=sig, data=sach)
        return _cache["data"]


def signature():
    """Chữ ký để người khác gộp vào khoá cache của họ.

    `mcp_catalog.load()` cache theo mtime file catalog; nếu không gộp thêm chữ ký này thì gỡ
    một connector sẽ không có hiệu lực cho tới khi ai đó sửa file catalog, tức là không bao giờ.
    """
    with _lock:
        try:
            st = STORE.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None


def da_go(loai: str) -> set:
    """Tập id đã gỡ của một loại năng lực."""
    return set(_doc().get(loai) or ())


def la_da_go(loai: str, cid: str) -> bool:
    return str(cid) in da_go(loai)


def dat(loai: str, cid: str, off: bool) -> bool:
    """Gỡ (off=True) hoặc cài lại (off=False) một năng lực mặc định. Trả về trạng thái mới.

    Ghi bằng tmp + replace như `plugins_host._write_state`: file này quyết định người dùng
    thấy gì, nên một lần ghi bị cắt giữa đường không được phép biến nó thành JSON hỏng.
    """
    if loai not in LOAI:
        raise ValueError(f"loại không hợp lệ: {loai}")
    cid = str(cid or "").strip()
    if not cid:
        raise ValueError("thiếu id")
    with _lock:
        d = {k: list(v) for k, v in _doc().items()}
        for k in LOAI:
            d.setdefault(k, [])
        hien = set(d[loai])
        if off:
            hien.add(cid)
        else:
            hien.discard(cid)
        d[loai] = sorted(hien)
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STORE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(STORE)
        except OSError as e:
            print(f"[core_off] ghi {STORE.name}: {e}", file=sys.stderr)
            raise
        _cache.update(sig=None, data={})   # buộc đọc lại ở lượt sau
        return off
