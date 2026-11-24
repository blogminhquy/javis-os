"""drive_parents.py - parents_of cho drive_write_guard, dựa trên metadata Drive THẬT (fail-closed).

Hàm lấy metadata được TIÊM vào (fetch_meta(file_id) -> dict). Ở production, fetch_meta gọi
GOOGLEDRIVE_GET_FILE_METADATA qua cổng Composio với account trong cấu hình local (composio_account).
Không đọc gì từ args của caller: chỉ tin response Drive.

Quy tắc (mọi vi phạm -> raise -> guard DENY):
    - Lỗi gọi API, response không phải dict.
    - response.id khác id đã hỏi (spoof/alias).
    - trashed == true (soft-delete).
    - mimeType là shortcut: đích thật nằm nơi khác, không tin.
    - parents không phải list chuỗi không rỗng (lỗi định dạng). Thiếu parents -> [] (thư mục gốc hoặc mồ côi,
      guard sẽ DENY vì không tới được WRITE_ROOT).
Cache trong một lần quyết định (một instance adapter = một request); không cache qua request.
"""
from __future__ import annotations

from typing import Callable

SHORTCUT_MIME = "application/vnd.google-apps.shortcut"


class DriveMetaError(ValueError):
    pass


def validate_meta(fid: str, meta) -> list[str]:
    """Kiểm metadata Drive của một id; trả danh sách parents. Mọi vi phạm -> DriveMetaError."""
    if not isinstance(meta, dict):
        raise DriveMetaError("metadata không phải object")
    if str(meta.get("id") or "") != fid:
        raise DriveMetaError("id trong response khác id đã hỏi")
    if meta.get("trashed") is True:
        raise DriveMetaError("đối tượng đã vào thùng rác")
    if meta.get("mimeType") == SHORTCUT_MIME:
        raise DriveMetaError("shortcut: không tin đích")
    raw = meta.get("parents")
    if raw is None:
        return []
    if isinstance(raw, list) and all(isinstance(x, str) and x.strip() for x in raw):
        return [x.strip() for x in raw]
    raise DriveMetaError("parents sai định dạng")


def unwrap_composio(envelope, fid: str) -> dict:
    """Lấy data của GOOGLEDRIVE_GET_FILE_METADATA từ envelope COMPOSIO_MULTI_EXECUTE_TOOL. Lỗi -> DriveMetaError."""
    import json
    if isinstance(envelope, str):
        try:
            envelope = json.loads(envelope)
        except ValueError as e:
            raise DriveMetaError("envelope Composio không phải JSON") from e
    if not isinstance(envelope, dict) or envelope.get("successful") is not True:
        raise DriveMetaError("Composio báo lỗi khi đọc metadata")
    results = ((envelope.get("data") or {}).get("results")) or []
    if len(results) != 1 or not isinstance(results[0], dict):
        raise DriveMetaError("Composio trả số kết quả không đúng")
    resp = results[0].get("response") or {}
    if resp.get("successful") is not True:
        raise DriveMetaError("Drive trả lỗi khi đọc metadata (auth/quyền/không tồn tại)")
    data = resp.get("data")
    if not isinstance(data, dict):
        raise DriveMetaError("Drive không trả data")
    return data


def make_parents_of(fetch_meta: Callable[[str], dict]) -> Callable[[str], list[str]]:
    """Adapter đồng bộ: fetch_meta(fid) -> metadata dict (đã unwrap). Cache trong một instance."""
    cache: dict[str, list[str]] = {}

    def parents_of(fid: str) -> list[str]:
        if fid not in cache:
            cache[fid] = validate_meta(fid, fetch_meta(fid))
        return list(cache[fid])

    return parents_of
