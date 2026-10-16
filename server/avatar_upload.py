"""Ảnh đại diện tự tải lên cho trợ lý và nhóm làm việc (0.176.0).

Chủ repo 16/10/2026: "ngoài avatar mặc định của Javis thêm một lựa chọn để tải avatar của họ lên, ở cả agent và nhóm".
Hình Javis (hình dáng, màu, mắt trong agent_avatar.py) vẫn là mặc định; ảnh tải lên chỉ là một lựa chọn thêm, xoá đi là
trở về đúng hình Javis cũ.

Cách lưu:
  - Một kho chung `STATE_DIR/avatars/`, tên file là băm nội dung (20 ký tự hex) + đuôi theo loại ảnh thật. Cùng một ảnh
    tải hai lần là một file; file không bao giờ bị ghi đè nên trình duyệt giữ được lâu (immutable).
  - File trợ lý chỉ ghi TÊN ảnh (`avatar.image` trong frontmatter), nhóm ghi tên ảnh ở cột `avatar_image`. Không ai ghi
    đường dẫn: tên đi qua `hop_le` trước khi chạm ổ đĩa, nên một tên lạ trong frontmatter không mở được file nào khác.
  - Chỉ nhận PNG, JPEG, WEBP, GIF, nhận diện bằng mấy byte đầu chứ không tin đuôi tên file hay Content-Type. Không nhận
    SVG: SVG là tài liệu có thể chạy script.
  - Trình duyệt đã cắt vuông và thu về 256px trước khi gửi (agent-avatar.js), nên trần dung lượng ở đây chỉ là chốt an toàn.
"""
import hashlib
import os
import re
import tempfile
from pathlib import Path

from config import STATE_DIR

DIR = Path(STATE_DIR) / "avatars"
MAX_BYTES = 2 * 1024 * 1024
_TEN = re.compile(r"[0-9a-f]{20}\.(png|jpg|webp|gif)")


def loai_anh(data: bytes) -> str:
    """Đuôi file theo nội dung thật, "" khi không phải ảnh nhận được."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return ""


def hop_le(name) -> bool:
    """Tên ảnh đúng dạng do chính kho này đặt VÀ file còn trên đĩa."""
    return isinstance(name, str) and bool(_TEN.fullmatch(name)) and (DIR / name).is_file()


def duong_dan(name):
    return DIR / name if hop_le(name) else None


def luu(data: bytes) -> str:
    """Lưu ảnh, trả tên. ValueError("avatar_empty" | "avatar_too_big" | "avatar_type") khi không nhận."""
    if not data:
        raise ValueError("avatar_empty")
    if len(data) > MAX_BYTES:
        raise ValueError("avatar_too_big")
    ext = loai_anh(data)
    if not ext:
        raise ValueError("avatar_type")
    name = hashlib.sha256(data).hexdigest()[:20] + "." + ext
    DIR.mkdir(parents=True, exist_ok=True)
    dich = DIR / name
    if not dich.is_file():
        # Ghi ra file tạm rồi đổi tên: hai lần tải cùng lúc hay máy tắt giữa chừng không để lại ảnh cụt.
        fd, tam = tempfile.mkstemp(dir=str(DIR), prefix=".tai-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tam, dich)
        except Exception:
            try:
                os.unlink(tam)
            except OSError:
                pass
            raise
    return name
