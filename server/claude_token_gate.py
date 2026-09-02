"""Xếp hàng đúng LÚC LÀM MỚI token Claude - chống hai lượt chat đá nhau văng đăng nhập.

Bệnh (chủ repo báo 02/09, hai vợ chồng dùng chung một javis)
------------------------------------------------------------
Javis chạy NHIỀU tiến trình `claude` song song (xem `_ACTIVE_PROCS` ở claude_cli, và
`_ACTIVE` ở claude_sdk_engine) mà không có gì xếp hàng chúng lại. Cả đám dùng chung ĐÚNG MỘT
file `~/.claude/.credentials.json`.

Refresh token OAuth là loại DÙNG MỘT LẦN: máy chủ tiêu nó rồi trả về một cặp mới. Nên khi
access token hết hạn đúng lúc hai người đang cùng chat:

  - lượt A làm mới trước  -> tiêu mất refresh token cũ, ghi cặp mới xuống file, chạy tiếp;
  - lượt B vẫn cầm refresh token CŨ (đọc từ trước) -> máy chủ trả
    "refresh token was already used. Please log out and sign in again".

Ai thua thì lượt đó hỏng, còn FILE VẪN LÀNH nên người kia không thấy gì. Đúng cái hình
"vợ bị văng, chồng dùng bình thường".

Vì sao vệ sĩ credentials (claude_cli.giu_credentials) không cứu được: nó lo file HỎNG hoặc
MẤT. Ở đây file lành tuyệt đối - chỉ có một cái token bị tiêu trước. Và nó quét 5 phút một
lần, quá chậm so với một cuộc đua tính bằng mili giây.

Cách chặn
---------
Chỉ xếp hàng trong ĐÚNG cửa sổ hẹp lúc token sắp/đã hết hạn (đọc `expiresAt` ngay trong file,
không đụng tới chính token - cùng cách connect_health đang làm). Ngoài cửa sổ đó thì hàm này
trả về ngay, không tốn gì. Trong cửa sổ: người đầu tiên đi luôn, người tới sau chờ tới khi
`expiresAt` nhích lên rồi mới chạy, tức là đã cầm token mới.

KHÔNG dùng khoá giữ suốt lượt: một lượt chat có thể chạy vài phút, giữ khoá cả lượt là biến
hai người thành xếp hàng nối đuôi. Ở đây chỉ giữ một MỐC THỜI GIAN tự hết hạn, nên không có
đường nào kẹt vĩnh viễn: kẹt xấu nhất là mọi lượt chờ thêm vài giây rồi vẫn chạy.

macOS cất token trong Keychain, không có file -> `han_token()` trả 0 -> không xếp hàng, lui
về đúng hành vi cũ.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path

# Coi là "sắp hết hạn" khi hạn còn dưới ngần này. Rộng hơn thời gian một lượt khởi động
# `claude` để cuộc đua bị bắt TRƯỚC khi nó xảy ra, chứ không phải sau.
CHUAN_BI_S = 120.0
# Người tới sau chờ tối đa ngần này rồi vẫn chạy. Thà chịu rủi ro đua còn hơn treo lượt chat.
CHO_TOI_DA_S = 30.0
# Mốc "đang có người đi trước" tự hết hạn sau ngần này, kể cả khi lượt đó chết giữa chừng.
GIU_TOI_DA_S = 25.0
NHIP_S = 0.4

_KHOA_BIEN = threading.Lock()
_MOC_DI_TRUOC = 0.0


def duong_cred() -> Path:
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".claude" / ".credentials.json"


def han_token() -> float:
    """Hạn của access token, tính bằng epoch GIÂY. 0.0 = không đọc được / không có file.

    Chỉ đọc MỖI trường `expiresAt`, không đụng tới accessToken/refreshToken và không gửi
    chúng đi đâu - đúng ranh giới mà connect_health đã đặt sẵn.
    """
    try:
        oa = (json.loads(duong_cred().read_text(encoding="utf-8")) or {}).get("claudeAiOauth") or {}
        exp = float(oa.get("expiresAt") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0.0
    # File ghi mili giây (13 chữ số). Chia cho 1000 để về giây.
    return exp / 1000.0 if exp > 0 else 0.0


def la_loi_tranh_lam_moi(text: str) -> bool:
    """Câu lỗi này có phải DẤU VẾT CUỘC ĐUA không - phân biệt với mất đăng nhập THẬT.

    Mốc nhận dạng là "already used": nó nói refresh token bị TIÊU TRƯỚC bởi một lượt khác,
    tức phiên đăng nhập vẫn còn nguyên. Cố ý KHÔNG nhận theo "could not be refreshed" trơn:
    câu đó cũng là câu của phiên hết hạn THẬT (vụ Claude 27/07), mà bắt nhầm ca đó thành
    "chạy lại là được" là giấu mất một lỗi người dùng buộc phải xử lý.
    """
    return "already used" in (text or "").lower()


def con_dang_nhap() -> bool:
    """File credentials còn token không - để phân biệt "đua nhau" với "mất đăng nhập thật"."""
    try:
        oa = (json.loads(duong_cred().read_text(encoding="utf-8")) or {}).get("claudeAiOauth") or {}
        return bool(oa.get("accessToken") or oa.get("refreshToken"))
    except (OSError, ValueError, TypeError, AttributeError):
        return False


async def xep_hang() -> str:
    """Gọi ngay trước khi khởi chạy một tiến trình `claude`.

    Trả nhãn để test và log đọc được: "" (ngoài cửa sổ, không làm gì) | "di-truoc" |
    "cho" (đã có token mới, hoặc người đi trước hết lượt giữ) | "het-gio".
    """
    global _MOC_DI_TRUOC
    han = han_token()
    if han <= 0:
        return ""                                   # không đọc được hạn -> giữ nguyên hành vi cũ
    if han - time.time() > CHUAN_BI_S:
        return ""                                   # đường nhanh: token còn tốt, không tốn gì
    with _KHOA_BIEN:
        di_truoc = (time.time() - _MOC_DI_TRUOC) >= GIU_TOI_DA_S
        if di_truoc:
            _MOC_DI_TRUOC = time.time()
    if di_truoc:
        return "di-truoc"
    het = time.time() + CHO_TOI_DA_S
    while time.time() < het:
        await asyncio.sleep(NHIP_S)
        if han_token() > han:
            return "cho"                            # người đi trước đã ghi cặp mới -> đi thôi
        with _KHOA_BIEN:
            if (time.time() - _MOC_DI_TRUOC) >= GIU_TOI_DA_S:
                return "cho"                        # lượt đi trước chết giữa chừng, không chờ nữa
    return "het-gio"
