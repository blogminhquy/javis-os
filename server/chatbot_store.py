"""Kho Bot chuyên trách - chatbot chuyên một lĩnh vực, trả lời KHÁCH qua Telegram.

Vì sao có kho RIÊNG chứ không nhét vào file Agent (bản thiết kế đầu định làm vậy, và sai):

  - Agent nằm TRONG một brain (`<brain>/Javis/agents/<slug>.md`), còn bot lại đọc **brain
    riêng của nó**. Khai báo bot đặt ở brain chính sẽ mô tả một thứ sống ở brain khác.
  - Token là BÍ MẬT, không được nằm trong file .md mà chủ mở ra sửa trong Obsidian.
  - Bot có VÒNG ĐỜI (đang chạy / đã tắt / lỗi). Vòng đời không thuộc về một file tài liệu.

Nguyên tắc "đừng nhân bản khái niệm" vẫn giữ: bot chỉ **trỏ tới** một Agent bằng cặp
(brain, slug), không chép lại vai trò/prompt/skill. Sửa Agent ở trang Agents là bot đổi theo.

Hình dạng đi theo đúng khuôn `mcp_store`: bản ghi ở JSON, token qua `secrets_store`.

Xem docs/dev/2026-08-bot-chuyen-trach-spec.md.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import secrets_store
from config import STATE_DIR

STORE_PATH = STATE_DIR / "chatbots.json"

_lock = threading.Lock()

# Bot trả lời KHÁCH LẠ nên mọi thứ nhận từ giao diện đều phải kẹp. Trần rộng rãi nhưng hữu hạn.
NAME_MAX = 60
_ICON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")     # tên icon Lucide, như projects.icon
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_CHAT_ID_RE = re.compile(r"^-?\d{1,20}$")               # id nhóm Telegram là số ÂM

REPLY_WHEN = ("mention", "always")
RATE_MIN, RATE_MAX, RATE_DEFAULT = 1, 200, 20

# Bot lấy câu trả lời từ đâu khi tài liệu không phủ được câu hỏi.
#
#   "agent"     - chuyên môn của Agent là nguồn chính, tài liệu là phần bổ sung. Đúng cho bot
#                 tư vấn, coach, đào tạo, giải đáp nghiệp vụ: cái nó giỏi nằm trong hướng dẫn
#                 vai chứ không nằm ở file nào.
#   "tai_lieu"  - CHỈ tài liệu, không có thì im. Đúng cho bot đọc giá và chính sách, nơi một
#                 câu sai là thiệt hại thật.
#
# Mặc định "agent" vì đó là hành vi người dùng MONG ĐỢI sau khi chọn một Agent: bot phải nói
# giống Agent đó. Bản 0.20.0 ép cứng chế độ kia cho mọi bot, và một Agent coach viết rất kỹ
# vẫn trả lời "em chưa có thông tin" cho đúng câu thuộc chuyên môn của nó.
NGUON = ("agent", "tai_lieu")
NGUON_DEFAULT = "agent"


def _now() -> float:
    return time.time()


def _load() -> dict:
    try:
        d = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "bots": []}
    except Exception:
        # File hỏng (sửa tay, đĩa đầy giữa chừng): KHÔNG xoá, đổi tên để còn cứu, rồi bắt đầu lại.
        # Mất danh sách bot đã đau, mất luôn bản gốc để dò thì không cứu được nữa.
        try:
            STORE_PATH.rename(STORE_PATH.with_suffix(".json.hong"))
        except Exception:
            pass
        return {"version": 1, "bots": []}
    if not isinstance(d, dict) or not isinstance(d.get("bots"), list):
        return {"version": 1, "bots": []}
    return d


def _save(d: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, STORE_PATH)   # ghi nguyên tử: mất điện giữa chừng không để lại file cụt


def _slugify(name: str) -> str:
    s = str(name or "").strip().lower()
    for a, b in (("àáảãạăằắẳẵặâầấẩẫậ", "a"), ("èéẻẽẹêềếểễệ", "e"), ("ìíỉĩị", "i"),
                 ("òóỏõọôồốổỗộơờớởỡợ", "o"), ("ùúủũụưừứửữự", "u"), ("ỳýỷỹỵ", "y"), ("đ", "d")):
        for ch in a:
            s = s.replace(ch, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "bot")[:60]


def _clean_name(v: Any) -> str:
    return str(v or "").strip()[:NAME_MAX]


def _clean_icon(v: Any) -> Optional[str]:
    s = str(v or "").strip().lower()
    return s if _ICON_RE.match(s) else None


def _clean_groups(v: Any) -> List[str]:
    """Danh sách id nhóm Telegram. Bỏ thứ không phải số - dán nhầm tên nhóm vào đây thì bot
    im lặng mãi mà không ai hiểu vì sao, thà lọc ngay lúc lưu."""
    if isinstance(v, str):
        items = re.split(r"[,;\s]+", v)
    elif isinstance(v, (list, tuple)):
        items = list(v)
    else:
        items = []
    out = []
    for x in items:
        x = str(x).strip()
        if _CHAT_ID_RE.match(x) and x not in out:
            out.append(x)
    return out[:50]


def _clean_rate(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return RATE_DEFAULT
    return max(RATE_MIN, min(n, RATE_MAX))


def _public(b: dict) -> dict:
    """Bản trả ra giao diện. KHÔNG bao giờ kèm token, kể cả dạng đã mã hoá."""
    out = {k: v for k, v in b.items() if k not in ("token", "token_enc")}
    out["token_set"] = bool(b.get("token_enc"))
    # Bù trường mới cho bản ghi cũ ngay lúc ĐỌC, không viết script di trú. Bot tạo trước 0.20.1
    # không có khoá này; thiếu nó thì prompt rơi vào nhánh mặc định của Python chứ không phải
    # nhánh mình chọn, và bug đó chỉ hiện ra trên máy người đã dùng - đúng chỗ khó dò nhất.
    out.setdefault("nguon_tra_loi", NGUON_DEFAULT)
    return out


# ============================================================
# Đọc
# ============================================================
def list_bots() -> List[Dict[str, Any]]:
    with _lock:
        return [_public(b) for b in _load()["bots"]]


def get_bot(bot_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        for b in _load()["bots"]:
            if b.get("id") == bot_id:
                return _public(b)
    return None


def get_token(bot_id: str) -> str:
    """Token THẬT - chỉ cho mã nội bộ (bộ giám sát). TUYỆT ĐỐI không trả ra giao diện."""
    with _lock:
        for b in _load()["bots"]:
            if b.get("id") == bot_id:
                return secrets_store.decrypt(b.get("token_enc", "")) or ""
    return ""


def enabled_bots() -> List[Dict[str, Any]]:
    return [b for b in list_bots() if b.get("enabled")]


def token_owner(username: str, exclude_id: str = "") -> Optional[Dict[str, Any]]:
    """Bot nào đang giữ đúng con bot Telegram này (so theo @username từ getMe, KHÔNG so chuỗi
    token: cùng một token dán hai lần với khoảng trắng khác nhau vẫn là hai chuỗi khác nhau).

    Vì sao phải chặn: một token chỉ được MỘT tiến trình long-polling. Hai poller cùng token
    thì Telegram trả 409 và CẢ HAI cùng chết - hỏng ở chỗ không ai ngờ, và không ai báo.
    """
    u = str(username or "").strip().lower().lstrip("@")
    if not u:
        return None
    with _lock:
        for b in _load()["bots"]:
            if b.get("id") != exclude_id and str(b.get("bot_username", "")).lower() == u:
                return _public(b)
    return None


# ============================================================
# Ghi
# ============================================================
def create_bot(data: dict) -> tuple[Optional[str], str]:
    """Tạo bot. Trả (id, "") hoặc (None, lý do).

    Bot mới LUÔN tắt, bất kể người gọi gửi gì. Bot chăm sóc khách hàng bật lên là nói chuyện
    với người thật ngay lập tức; đó phải là một cú bấm CÓ Ý THỨC, không phải tác dụng phụ của
    việc tạo.
    """
    name = _clean_name(data.get("name"))
    if not name:
        return None, "Thiếu tên bot"
    agent_slug = str(data.get("agent_slug") or "").strip()
    if not _SLUG_RE.match(agent_slug):
        return None, "Thiếu Agent cho bot (bot không có bộ não thì không trả lời được gì)"
    brain = str(data.get("brain") or "").strip()
    if not brain:
        return None, "Thiếu brain riêng của bot"

    with _lock:
        d = _load()
        bot = {
            "id": "bot_" + uuid.uuid4().hex[:10],
            "slug": _slugify(name),
            "name": name,
            "icon": _clean_icon(data.get("icon")) or "headset",
            "enabled": False,
            "agent": {"brain": str(data.get("agent_brain") or "brain").strip() or "brain",
                      "slug": agent_slug},
            "brain": brain,
            "channel": "telegram",
            "bot_username": str(data.get("bot_username") or "").strip().lstrip("@"),
            "groups": _clean_groups(data.get("groups")),
            "reply_when": (data.get("reply_when") if data.get("reply_when") in REPLY_WHEN else "mention"),
            "nguon_tra_loi": (data.get("nguon_tra_loi") if data.get("nguon_tra_loi") in NGUON
                              else NGUON_DEFAULT),
            "handoff_to": str(data.get("handoff_to") or "").strip(),
            "rate_limit": _clean_rate(data.get("rate_limit")),
            "created_at": _now(),
            "updated_at": _now(),
        }
        tok = str(data.get("token") or "").strip()
        if tok:
            bot["token_enc"] = secrets_store.encrypt(tok)
        d["bots"].append(bot)
        _save(d)
        return bot["id"], ""


# Trường giao diện được phép sửa. Danh sách TRẮNG chứ không phải "nhận hết trừ vài cái":
# thêm trường mới vào bản ghi mà quên loại khỏi danh sách đen là mở một đường ghi không ai ngờ.
_PATCHABLE = ("name", "icon", "groups", "reply_when", "handoff_to", "rate_limit",
              "agent_slug", "agent_brain", "brain", "bot_username", "token", "enabled",
              "nguon_tra_loi")


def update_bot(bot_id: str, patch: dict) -> tuple[bool, str]:
    with _lock:
        d = _load()
        for b in d["bots"]:
            if b.get("id") != bot_id:
                continue
            for k in _PATCHABLE:
                if k not in patch:
                    continue
                v = patch[k]
                if k == "name":
                    nv = _clean_name(v)
                    if nv:
                        b["name"] = nv
                elif k == "icon":
                    b["icon"] = _clean_icon(v) or b.get("icon") or "headset"
                elif k == "groups":
                    b["groups"] = _clean_groups(v)
                elif k == "reply_when":
                    if v in REPLY_WHEN:
                        b["reply_when"] = v
                elif k == "nguon_tra_loi":
                    if v in NGUON:
                        b["nguon_tra_loi"] = v
                elif k == "handoff_to":
                    b["handoff_to"] = str(v or "").strip()
                elif k == "rate_limit":
                    b["rate_limit"] = _clean_rate(v)
                elif k == "agent_slug":
                    if _SLUG_RE.match(str(v or "").strip()):
                        b.setdefault("agent", {})["slug"] = str(v).strip()
                elif k == "agent_brain":
                    b.setdefault("agent", {})["brain"] = str(v or "brain").strip() or "brain"
                elif k == "brain":
                    if str(v or "").strip():
                        b["brain"] = str(v).strip()
                elif k == "bot_username":
                    b["bot_username"] = str(v or "").strip().lstrip("@")
                elif k == "token":
                    tok = str(v or "").strip()
                    if tok:
                        b["token_enc"] = secrets_store.encrypt(tok)
                elif k == "enabled":
                    b["enabled"] = bool(v) and bool(b.get("token_enc"))
            b["updated_at"] = _now()
            _save(d)
            return True, ""
    return False, "Không có bot nào id đó"


def set_enabled(bot_id: str, on: bool) -> tuple[bool, str]:
    """Bật/tắt. Bật mà chưa có token thì TỪ CHỐI kèm lý do, chứ không bật rồi để nó chết lặng
    lẽ trong bộ giám sát - đó đúng là kiểu hỏng mà cả tính năng này đang cố tránh."""
    with _lock:
        d = _load()
        for b in d["bots"]:
            if b.get("id") != bot_id:
                continue
            if on and not b.get("token_enc"):
                return False, "Chưa có token Telegram cho bot này"
            b["enabled"] = bool(on)
            b["updated_at"] = _now()
            _save(d)
            return True, ""
    return False, "Không có bot nào id đó"


def delete_bot(bot_id: str) -> tuple[bool, str]:
    """Xoá bản ghi bot. KHÔNG đụng tới brain và Agent của nó.

    Cùng lý do với xoá Project không xoá hội thoại (0.18.0): người dùng không đoán được hậu
    quả thì đừng bắt họ gánh. Brain có thể chứa cả tháng tri thức chủ tự soạn; Agent có thể
    đang được bot khác hoặc workflow dùng. Muốn xoá thì xoá ở trang của chúng.
    """
    with _lock:
        d = _load()
        n = len(d["bots"])
        d["bots"] = [b for b in d["bots"] if b.get("id") != bot_id]
        if len(d["bots"]) == n:
            return False, "Không có bot nào id đó"
        _save(d)
        return True, ""


def bots_using_agent(brain: str, slug: str) -> List[Dict[str, Any]]:
    """Bot nào đang trỏ vào Agent này. Dùng để CHẶN xoá Agent còn bot dùng, thay vì để bot
    thành mồ côi rồi im lặng trả lời sai."""
    out = []
    for b in list_bots():
        a = b.get("agent") or {}
        if str(a.get("brain")) == str(brain) and str(a.get("slug")) == str(slug):
            out.append(b)
    return out
