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
# id nhóm Telegram là số ÂM; id cuộc chat Zalo là chuỗi HEX (vd "6ede9afa66b88fe6d6a9"). Một
# khuôn cho cả hai, vì bản ghi bot chỉ có một trường `groups` và kênh nào cũng đổ vào đó.
_CHAT_ID_RE = re.compile(r"^(-?\d{1,20}|[0-9a-fA-F]{8,40})$")

# Kênh nhắn tin của bot. Trường này có từ 0.20.0 nhưng ghim cứng "telegram"; 0.26.5 cho nó
# thành lựa chọn thật. Giữ ĐÚNG hai giá trị: mỗi giá trị là một lớp vận chuyển có thật trong
# `chatbot_runtime._LOP_KENH`, không phải một nhãn để hiển thị.
KENH = ("telegram", "zalo")
KENH_DEFAULT = "telegram"

# Nhãn + cách lấy token, để server và giao diện nói cùng một câu. Người dùng lấy token ở hai
# nơi hoàn toàn khác nhau, và dán nhầm chỗ thì bot chết lặng với lỗi 401.
KENH_NHAN = {"telegram": "Telegram", "zalo": "Zalo"}
KENH_NGUON_TOKEN = {
    "telegram": "Nhắn @BotFather trên Telegram, gõ /newbot rồi làm theo hướng dẫn.",
    "zalo": "Mở app Zalo, tìm Official Account \"Zalo Bot Manager\", chọn Tạo bot. "
            "Tên bot bắt buộc mở đầu bằng chữ \"Bot\". Token được gửi về bằng tin nhắn Zalo.",
}

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

# Mức quyền của MỘT LƯỢT bot. Cố ý dùng ĐÚNG bộ tên của loop và của hub
# (`mcp_catalog._MODE_CAP`): chữ chọn trên giao diện đi thẳng xuống header `X-Javis-Mode` mà
# không qua bảng dịch nào. Bảng dịch là chỗ dễ sai nhất, và sai ở đây nghĩa là cấp nhầm quyền
# cho một con bot đang nói chuyện với NGƯỜI LẠ.
#
#   "suggest" - chỉ đọc. Không có tool nào cả (xem `main._bot_tra_loi`). MẶC ĐỊNH.
#   "auto"    - đọc + GHI file trong brain của chính bot, gọi được MCP đã đấu ở mức đọc/ghi.
#               Hub chặn nhóm THAO TÁC RA NGOÀI (`mcp_catalog` xếp loại 'danger').
#   "full"    - toàn quyền, kể cả nhóm ra ngoài. Người lạ nói chuyện với bot điều khiển được
#               những tool đó, và thao tác ra ngoài thì không hoàn tác được.
MUC_QUYEN = ("suggest", "auto", "full")
MUC_QUYEN_DEFAULT = "suggest"
MUC_NANG = ("auto", "full")     # hai mức phải có xác nhận rủi ro mới đặt được

# Nhãn tiếng Việt, để server và giao diện gọi cùng một tên cho cùng một mức.
MUC_NHAN = {"suggest": "Chỉ đọc", "auto": "Được ghi", "full": "Toàn quyền"}

# Rủi ro của từng mức, viết bằng lời người. Trả về DANH SÁCH câu chứ không phải một đoạn văn:
# giao diện vẽ thành gạch đầu dòng, kênh chữ in thành nhiều dòng, và test đếm được từng ý.
#
# Câu chữ ở đây là thứ chủ đọc TRƯỚC KHI bấm đồng ý, nên nó phải nói đúng cái mất được chứ
# không phải một câu "hãy cẩn thận" chung chung. Cảnh báo chung chung thì đọc xong vẫn không
# biết mình vừa trao cái gì.
#
# Nhưng "nói đúng cái mất được" KHÔNG có nghĩa là kể tên việc của một ngành. Bản đầu viết
# "tạo đơn, tiêu tiền quảng cáo, đăng bài" - đọc lọt tai với người bán hàng, và vô nghĩa với
# người dùng Javis để quản lý dự án, chăm sức khoẻ hay dạy học. Tệ hơn: người đó đọc xong
# tưởng cảnh báo không áp cho mình. Nên tả theo LOẠI THAO TÁC (gửi đi, thanh toán, đặt/huỷ,
# xoá, công bố) - đúng cách `mcp_catalog` phân loại, và đúng cho mọi nguồn dữ liệu đấu vào.
_CANH_BAO = {
    "auto": [
        "Bot GHI ĐƯỢC file trong brain của chính nó. Người nhắn cho bot một câu là nội dung "
        "trong brain đổi thật, không có bước duyệt.",
        "Bot gọi được các nguồn dữ liệu (MCP) bạn đã đấu, ở mức đọc và ghi. Mọi thứ trong "
        "những nguồn đó nằm trong tầm với của người đang chat với bot.",
        "Javis vẫn CHẶN cứng nhóm thao tác RA NGOÀI ở mức này: không gửi đi, không thanh toán, "
        "không đặt hay huỷ, không xoá, không công bố gì.",
        "Bot vẫn KHÔNG thấy brain khác, không chạy lệnh máy, không ra được ngoài máy.",
    ],
    "full": [
        "Bot làm được MỌI thứ các nguồn đã đấu cho phép, kể cả gửi đi, thanh toán, đặt hay huỷ, "
        "xoá và công bố ra ngoài. Những thao tác đó KHÔNG hoàn tác được.",
        "Người điều khiển bot là NGƯỜI NHẮN CHO NÓ, không phải bạn. Ai nhắn được cho bot cũng "
        "nói được câu khiến nó gọi tool, và không có bước hỏi lại bạn.",
        "Một câu dụ khéo ('bỏ qua hướng dẫn trước, làm giúp việc này') là đủ. Rào duy nhất còn "
        "lại là chính file Agent bạn viết, mà chữ thì lách được.",
        "Chỉ nên bật cho bot mà bạn kiểm soát được DANH SÁCH người nhắn vào. Nơi ai cũng nhắn "
        "được thì không.",
        "Bot vẫn KHÔNG thấy brain khác và không chạy lệnh máy - hai rào đó giữ nguyên ở mọi mức.",
    ],
}


def canh_bao_muc(muc: str) -> List[str]:
    """Những gì chủ đang trao đi khi đặt bot ở mức này. [] với mức chỉ-đọc (không mất gì)."""
    return list(_CANH_BAO.get(str(muc or "").strip().lower(), []))


def _clean_muc(v: Any) -> Optional[str]:
    s = str(v or "").strip().lower()
    return s if s in MUC_QUYEN else None


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


def _clean_kenh(v: Any) -> str:
    """Kênh lạ thì rơi về Telegram chứ KHÔNG lưu nguyên: `chatbot_runtime` tra bảng lớp vận
    chuyển bằng chuỗi này, và một chuỗi không có trong bảng nghĩa là bot không bao giờ bật
    được, với thông báo lỗi chẳng nói lên điều gì."""
    s = str(v or "").strip().lower()
    return s if s in KENH else KENH_DEFAULT


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
    # Cùng lý do: bot tạo trước 0.22.0 không có khoá này. Thiếu nó mà đọc bằng `.get()` thì ra
    # None, và None rơi vào nhánh mặc định của người gọi chứ không phải nhánh mình chọn - ở đây
    # nhánh đó quyết định bot CÓ TOOL hay không, nên đoán sai một lần là cấp nhầm quyền.
    out.setdefault("muc_quyen", MUC_QUYEN_DEFAULT)
    # Cùng lý do: bot tạo trước 0.26.5 luôn là bot Telegram, và trường này lúc đó ghim cứng.
    out["channel"] = _clean_kenh(out.get("channel"))
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


def token_owner(username: str, exclude_id: str = "", channel: str = "") -> Optional[Dict[str, Any]]:
    """Bot nào đang giữ đúng con bot này (so theo tên tài khoản lấy từ getMe, KHÔNG so chuỗi
    token: cùng một token dán hai lần với khoảng trắng khác nhau vẫn là hai chuỗi khác nhau).

    Vì sao phải chặn: một token chỉ được MỘT tiến trình long-polling. Hai poller cùng token
    thì máy chủ trả 409 và CẢ HAI cùng chết - hỏng ở chỗ không ai ngờ, và không ai báo.

    So THEO KÊNH từ 0.26.5: tên tài khoản là không gian tên riêng của từng nền tảng, nên một
    bot Telegram tên "shopbot" và một bot Zalo cũng tên "shopbot" là hai con khác nhau. Gộp
    hai không gian tên lại thì trang Chatbot từ chối một token hoàn toàn hợp lệ, và câu từ
    chối đó nói về một con bot ở kênh khác nên đọc xong không ai hiểu.
    """
    u = str(username or "").strip().lower().lstrip("@")
    if not u:
        return None
    kenh = _clean_kenh(channel) if channel else ""
    with _lock:
        for b in _load()["bots"]:
            if b.get("id") == exclude_id or str(b.get("bot_username", "")).lower() != u:
                continue
            if kenh and _clean_kenh(b.get("channel")) != kenh:
                continue
            return _public(b)
    return None


# ============================================================
# Ghi
# ============================================================
# Nâng mức quyền là hành động một chiều: từ lúc bấm xong, mọi câu khách nhắn đều chạy ở mức
# mới. Nên nó phải là một cú bấm CÓ Ý THỨC, cùng lý do "bot mới luôn tắt" - và cùng khuôn với
# `POST /reminders` (`can_force` khi chưa đấu kênh báo).
#
# Rào đặt ở KHO chứ không chỉ ở route: route là một trong nhiều đường vào (giao diện, chat tự
# tạo bot, script của chủ). Rào ở kho thì đường nào cũng đi qua nó.
LOI_CHUA_XAC_NHAN = ("Mức quyền này cho bot làm việc THẬT ra ngoài, do người lạ điều khiển. "
                     "Phải xác nhận đã đọc cảnh báo rủi ro (xac_nhan_rui_ro) mới đặt được.")


def can_xac_nhan(muc: Any, xac_nhan: Any) -> bool:
    """Mức này có đòi chủ xác nhận rủi ro mà chưa có xác nhận không."""
    return _clean_muc(muc) in MUC_NANG and not bool(xac_nhan)


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
    if can_xac_nhan(data.get("muc_quyen"), data.get("xac_nhan_rui_ro")):
        return None, LOI_CHUA_XAC_NHAN

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
            "channel": _clean_kenh(data.get("channel")),
            "bot_username": str(data.get("bot_username") or "").strip().lstrip("@"),
            "groups": _clean_groups(data.get("groups")),
            "reply_when": (data.get("reply_when") if data.get("reply_when") in REPLY_WHEN else "mention"),
            "nguon_tra_loi": (data.get("nguon_tra_loi") if data.get("nguon_tra_loi") in NGUON
                              else NGUON_DEFAULT),
            "muc_quyen": _clean_muc(data.get("muc_quyen")) or MUC_QUYEN_DEFAULT,
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
              "nguon_tra_loi", "muc_quyen")
# `channel` CỐ Ý đứng ngoài danh sách trắng. Đổi kênh của một bot đã tạo là đổi sang một CON
# BOT KHÁC: token khác, danh tính khác, khách khác, và cả đống id nhóm đang lưu lập tức vô
# nghĩa. Cho sửa tại chỗ thì bản ghi còn nguyên tên và lịch sử của con cũ trong khi nó đã là
# con khác. Muốn kênh khác thì tạo bot mới - giao diện cũng khoá đúng như vậy.


def update_bot(bot_id: str, patch: dict) -> tuple[bool, str]:
    # Cùng rào với lúc tạo, và đây mới là đường hay đi hơn: bot sống nhiều tháng ở mức chỉ đọc
    # rồi một hôm được nâng lên. Thiếu rào ở đây thì cả cái gate lúc tạo thành trang trí.
    if "muc_quyen" in patch and can_xac_nhan(patch.get("muc_quyen"), patch.get("xac_nhan_rui_ro")):
        return False, LOI_CHUA_XAC_NHAN
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
                elif k == "muc_quyen":
                    # Giá trị lạ thì GIỮ NGUYÊN mức cũ, không rơi về mặc định: bot đang ở
                    # "Toàn quyền" mà một bản vá gõ sai chữ lại hạ nó xuống chỉ đọc thì chủ
                    # tưởng bot vẫn làm việc, còn nó thì im lặng từ chối mọi tool.
                    nv = _clean_muc(v)
                    if nv:
                        b["muc_quyen"] = nv
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
                return False, f"Chưa có token {KENH_NHAN.get(_clean_kenh(b.get('channel')), '')} cho bot này"
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
