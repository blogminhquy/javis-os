"""Chế độ "Tự đánh giá" của Bot chuyên trách trong NHÓM (0.64.82).

Bot vốn chỉ mở miệng trong nhóm khi được gọi tên (tag hoặc reply vào nó). Chủ muốn thêm một chế
độ nữa: không cần tag, bot tự xem tin nào đáng trả lời, nghĩa là một CÂU HỎI mà tài liệu của nó
trả lời được, rồi mới lên tiếng. Còn khách trò chuyện với nhau thì bot im.

Đánh giá đi từ rẻ tới đắt, tầng nào loại là dừng và KHÔNG tốn một lượt model:

  1. `nhin_nhu_cau_hoi` (file này, mã thuần): tin có giống một câu hỏi/lời nhờ giúp không.
     Cố ý dễ tính, vì việc nặng đã có tầng sau; ở đây chỉ vứt thứ hiển nhiên không phải.
  2. Tra tài liệu (`chatbot_grounding.thu_thap`, làm ở `chatbot_runtime._answer`): brain của bot
     có phần nào khớp câu hỏi không. Đây là định nghĩa của "chủ đề Agent trả lời được": có căn
     cứ trong tài liệu chủ đã đưa, không phải kiến thức chung của model. Trả lời công khai trước
     cả nhóm bằng trí nhớ chung là cách nhanh nhất để bot bịa một câu về khoá học thay chủ.
  3. Một lượt model, kèm chỉ dẫn "không ai gọi tên bạn": Agent vẫn được quyền viết `[IM_LANG]`
     nếu đọc xong thấy không nên chen vào.

Và hai thứ để bot không thành máy phát thanh: hạn mức tự trả lời (mỗi nhóm, mỗi người, và một
khoảng nghỉ giữa hai lần) ở đây, còn việc NHƯỜNG khi có người đang nhắn tay nằm ở lớp vận
chuyển vì chỉ nó biết ai đang nói trong cuộc chat.

Tag/reply thì KHÔNG qua bộ đánh giá: gọi tên là một lời nhờ rõ ràng, bot trả lời như chat riêng.
"""
from __future__ import annotations

import re
import time
from collections import deque
from typing import Dict, Tuple

import chatbot_grounding

# Hạn mức TỰ trả lời (không tính lượt được gọi tên). Số nhỏ có chủ ý: nick Zalo này là người
# thật, gửi dồn trong nhóm vừa phiền vừa dễ bị Zalo khoá.
TRAN_NHOM_GIO = 8          # số lần tự trả lời tối đa mỗi nhóm mỗi giờ
TRAN_NGUOI_GIO = 3         # số lần tối đa cho MỘT người trong một nhóm mỗi giờ
KHOANG_CACH_GIAY = 20      # nghỉ giữa hai lần tự trả lời trong cùng một nhóm

MIN_CHU = 8
MIN_TU = 3

_URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
# Chữ báo hiệu một lời hỏi/nhờ giúp, đã BỎ DẤU (khách gõ không dấu nhiều). Đây chỉ là cửa thô.
_HOI = re.compile(
    r"\b(?:sao|nao|dau|gi|bao nhieu|bao gio|khi nao|luc nao|the nao|tai sao|vi sao|"
    r"cach|huong dan|giup|hoi|loi|khong duoc|khong chay|khong vao|khong thay|khong mo|"
    r"ai biet|ai co|chi giup|nho)\b"
    r"|\bco\b.*\bkhong\b\s*$")

_LY_DO = {
    "khong_co_tai_lieu": "Có vẻ là câu hỏi nhưng tài liệu của bot không có phần nào khớp, nên bot im.",
    "het_han_muc": "Bot đã tự trả lời đủ số lần cho nhóm này trong giờ vừa qua.",
    "het_han_nguoi": "Người này đã được bot tự trả lời đủ số lần trong giờ vừa qua.",
    "vua_tra_loi": "Bot vừa tự trả lời trong nhóm này, chờ một chút mới trả lời tiếp.",
}
_LY_DO_EN = {
    "khong_co_tai_lieu": "Looks like a question, but nothing in the bot's documents matches, so the bot stayed quiet.",
    "het_han_muc": "The bot has already auto-replied the maximum number of times in this group this past hour.",
    "het_han_nguoi": "The bot has already auto-replied to this person the maximum number of times this past hour.",
    "vua_tra_loi": "The bot just auto-replied in this group; it waits a moment before replying again.",
}


def ly_do_de_doc(ma: str) -> str:
    if ma not in _LY_DO:
        return ma
    import localefmt
    return localefmt.chu(_LY_DO[ma], _LY_DO_EN[ma])


def can_danh_gia(cfg: dict, meta: dict) -> bool:
    """Lượt này có phải tin nhóm KHÔNG ai gọi bot, khi bot đang ở chế độ Tự đánh giá.

    So đúng chữ "auto": giá trị lạ (bản ghi cũ, chỉnh tay sai) thì KHÔNG bật, để rơi về luật
    "chỉ khi được gọi tên". Mở nhầm là bot chen vào mọi câu trong nhóm dưới tên người thật.
    """
    meta = meta or {}
    return (str(meta.get("chat_type") or "private") != "private"
            and (cfg or {}).get("reply_when") == "auto"
            and not meta.get("mentioned") and not meta.get("reply_to_bot"))


def nhin_nhu_cau_hoi(text: str) -> Tuple[bool, str]:
    """Tầng 1: tin có giống câu hỏi/lời nhờ giúp không. Trả (đạt, lý do khi loại)."""
    t = str(text or "").strip()
    if not t:
        return False, "trong"
    if t.lstrip().startswith("@"):
        # Mở đầu bằng tag mà tag đó không phải bot (tag bot đã được xử lý như lượt gọi tên):
        # đây là người này đang nói chuyện với người kia.
        return False, "goi_nguoi_khac"
    khong_link = _URL.sub(" ", t).strip()
    if len(khong_link) < MIN_CHU and _URL.search(t):
        return False, "chi_co_link"
    if len(khong_link) < MIN_CHU or len(khong_link.split()) < MIN_TU:
        return False, "qua_ngan"
    chuan = chatbot_grounding._bo_dau(khong_link).lower()
    if "?" in khong_link or "？" in khong_link or _HOI.search(chuan):
        return True, ""
    return False, "khong_phai_cau_hoi"


# ============================================================
# Hạn mức tự trả lời
# ============================================================
_NHOM: Dict[tuple, deque] = {}       # (bot, nhóm) -> giờ các lần tự trả lời
_NGUOI: Dict[tuple, deque] = {}      # (bot, nhóm, người) -> giờ các lần
_CUOI: Dict[tuple, float] = {}       # (bot, nhóm) -> giờ lần cuối
_TRAN_BO_NHO = 5000                  # trần thô: quên hạn mức còn hơn phình mãi


def _don(dq: deque, now: float) -> None:
    while dq and now - dq[0] > 3600:
        dq.popleft()


def duoc_tra_loi(bot_id: str, chat_id: str, user_id: str = "", now: float = None, follow_up: bool = False) -> str:
    """"" nếu bot được tự trả lời lúc này, không thì mã lý do (xem `ly_do_de_doc`).

    `follow_up` (0.65.0): tin này là người bot VỪA trả lời hỏi tiếp. Đó là một cuộc trò chuyện đang diễn ra
    chứ không phải bot chen vào, nên KHÔNG bị chặn bởi khoảng nghỉ giữa hai lần nói và trần theo người;
    trần theo nhóm mỗi giờ vẫn áp (nick này là người thật, không được thành máy phát thanh)."""
    now = time.time() if now is None else now
    kn = (str(bot_id), str(chat_id))
    dq = _NHOM.get(kn)
    if dq is not None:
        _don(dq, now)
        if len(dq) >= max(1, int(TRAN_NHOM_GIO)):
            return "het_han_muc"
    if not follow_up and KHOANG_CACH_GIAY and now - _CUOI.get(kn, 0.0) < KHOANG_CACH_GIAY:
        return "vua_tra_loi"
    if user_id and not follow_up:
        dq = _NGUOI.get(kn + (str(user_id),))
        if dq is not None:
            _don(dq, now)
            if len(dq) >= max(1, int(TRAN_NGUOI_GIO)):
                return "het_han_nguoi"
    return ""


def ghi_da_tra_loi(bot_id: str, chat_id: str, user_id: str = "", now: float = None) -> None:
    """Bot VỪA tự trả lời thật (không tính lượt bot chọn im). Chỉ gọi sau khi đã có câu trả lời."""
    now = time.time() if now is None else now
    if len(_NGUOI) > _TRAN_BO_NHO:
        _NGUOI.clear()
    kn = (str(bot_id), str(chat_id))
    _NHOM.setdefault(kn, deque()).append(now)
    _CUOI[kn] = now
    if user_id:
        _NGUOI.setdefault(kn + (str(user_id),), deque()).append(now)


def reset_cho_test() -> None:
    _NHOM.clear()
    _NGUOI.clear()
    _CUOI.clear()
