"""Kho Bot chuyên trách - chatbot chuyên một lĩnh vực, trả lời KHÁCH qua Telegram.

Vì sao có kho RIÊNG chứ không nhét vào file Agent (bản thiết kế đầu định làm vậy, và sai):

  - Agent nằm TRONG một brain (`<brain>/agents/<slug>.md`), còn bot lại đọc **brain
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

import channel_accounts   # tài khoản kênh dạng token (0.61.0): bot chỉ TRỎ tới, không giữ token
import channels          # sổ đăng ký kênh: nơi duy nhất biết kênh nào gắn được bot
import lang_registry   # sổ đăng ký ngôn ngữ: hợp lệ hoá trường ngon_ngu của bot

from config import STATE_DIR
import localefmt

STORE_PATH = STATE_DIR / "chatbots.json"

_lock = threading.Lock()

# Bot trả lời KHÁCH LẠ nên mọi thứ nhận từ giao diện đều phải kẹp. Trần rộng rãi nhưng hữu hạn.
NAME_MAX = 60
_ICON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")     # tên icon Lucide, như projects.icon
# Slug Agent = TÊN FILE `<brain>/agents/<slug>.md`, và tên file đó do người dùng đặt.
# `main._slugify` giữ nguyên chữ có dấu (nó lọc theo `\w` Unicode), nên Agent tên "Tư vấn sản
# phẩm" ra slug "tư-vấn-sản-phẩm" - một slug HOÀN TOÀN hợp lệ, đang nằm sẵn trong ô chọn ở trang
# Chatbot. Khuôn cũ `^[a-z0-9][a-z0-9-]{0,63}$` chỉ nhận ASCII nên nó đá bay đúng những Agent
# đặt tên tiếng Việt, mà lại đá bằng câu "Thiếu Agent" - chủ đang nhìn thấy Agent mình vừa chọn
# trong ô, và không có cách nào đoán ra chuyện dấu tiếng Việt.
#
# Nên ở đây KHÔNG canh hình dạng nữa, chỉ canh đúng thứ thật sự nguy hiểm: slug đi thẳng vào
# đường dẫn file, nên phải chặn tách đường dẫn và '..' (cùng lối với `skill_router._slug_ok`).
SLUG_MAX = 64
_SLUG_CAM = re.compile(r"[/\\\x00-\x1f\x7f]")           # tách đường dẫn + ký tự điều khiển
# id nhóm Telegram là số ÂM; id cuộc chat Zalo là chuỗi HEX (vd "6ede9afa66b88fe6d6a9"). Một
# khuôn cho cả hai, vì bản ghi bot chỉ có một trường `groups` và kênh nào cũng đổ vào đó.
# Từ 0.71.0 thêm id kênh/người Slack (C0ABC123, G..., D..., U...: chữ HOA và số). Số WhatsApp
# là chữ số nên đã khớp nhánh đầu.
_CHAT_ID_RE = re.compile(r"^(-?\d{1,20}|[0-9a-fA-F]{8,40}|[CGDUW][A-Z0-9]{6,20})$")

# Kênh nhắn tin của bot. Trường này có từ 0.20.0 nhưng ghim cứng "telegram"; 0.26.5 cho nó
# thành lựa chọn thật; 0.61.0 đọc từ SỔ ĐĂNG KÝ KÊNH (`channels`) thay vì chép ở đây: kênh nào
# có lớp vận chuyển (kind "bot") thì gắn được bot. Thêm kênh = thêm một module ở server/channels.
#
# Ba tên dưới giữ nguyên cho chỗ gọi cũ (main.py, test). Chúng là ẢNH của sổ lúc nạp module.
KENH = channels.bot_ids()
# Mặc định vẫn là Telegram: bản ghi bot trước 0.26.5 không có trường `channel` và đều là bot
# Telegram, nên rơi về Telegram là đọc đúng dữ liệu cũ, không phải ưu ái kênh nào.
KENH_DEFAULT = "telegram" if "telegram" in KENH else (KENH[0] if KENH else "telegram")
KENH_NHAN = {k: channels.nhan(k) for k in KENH}
KENH_NGUON_TOKEN = {k: (channels.spec(k).lay_token if channels.spec(k) else "") for k in KENH}

# mention = chỉ khi được gọi tên/reply; always = mọi tin trong nhóm đã cho phép; auto = "Tự đánh
# giá" (0.64.82): tag/reply vẫn trả lời, còn tin khác thì bot tự xem có phải câu hỏi tài liệu của
# nó trả lời được không, xem `chatbot_tu_dong`.
REPLY_WHEN = ("mention", "always", "auto")

# "Bot trả lời AI" (0.64.85), khác `reply_when` (khi nào lên tiếng TRONG nhóm):
#   "all"  - mọi cuộc chat trên kênh: chat riêng ai cũng được, mọi nhóm bot có mặt (không cần khai).
#   "nhom" - chat riêng ai cũng được, nhóm chỉ những nhóm trong `groups`. MẶC ĐỊNH, và chính là hành
#            vi từ trước tới nay, nên bản ghi cũ không có khoá này đọc ra là "nhom" và không đổi gì.
#   "chon" - chỉ người trong `people` và nhóm trong `groups`; mọi cuộc chat khác bot im.
# Sai về phía IM LẶNG: khoá có mà giá trị hỏng đọc là "chon" (hẹp nhất). Sai về phía mở thì bot nói
# với người lạ dưới tên người thật (nick Zalo cá nhân), còn sai về phía im thì chủ thấy bot im và sửa.
AUDIENCE = ("all", "nhom", "chon")
AUDIENCE_DEFAULT = "nhom"
AUDIENCE_HEP_NHAT = "chon"
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
        "Một câu dụ khéo ('bỏ qua hướng dẫn trước, làm giúp việc này') là đủ để bot làm theo. "
        "Rào cứng còn lại là mức quyền của TỪNG kết nối ở trang Kết nối (hạ một kết nối về Chỉ "
        "đọc thì bot cũng bị chặn ghi ở đó), nhưng rào đó chặn theo loại thao tác nên với nguồn "
        "Javis chưa có khuôn phân loại sẵn thì không kín tuyệt đối. Ngoài ra chỉ còn file Agent "
        "bạn viết, mà chữ thì lách được.",
        "Chỉ nên bật cho bot mà bạn kiểm soát được DANH SÁCH người nhắn vào. Nơi ai cũng nhắn "
        "được thì không.",
        "Bot vẫn KHÔNG thấy brain khác và không chạy lệnh máy - hai rào đó giữ nguyên ở mọi mức.",
    ],
}


_CANH_BAO_EN = {
    "auto": [
        "The bot CAN WRITE files in its own brain. One message to the bot and the content "
        "in the brain really changes, with no review step.",
        "The bot can call the data sources (MCP) you connected, for reading and writing. Everything in "
        "those sources is within reach of whoever is chatting with the bot.",
        "Javis still hard-BLOCKS OUTSIDE actions at this level: nothing is sent, paid, "
        "booked or cancelled, deleted or published.",
        "The bot still CANNOT see other brains, run machine commands or reach outside the machine.",
    ],
    "full": [
        "The bot can do EVERYTHING the connected sources allow, including sending, paying, booking or "
        "cancelling, deleting and publishing. Those actions CANNOT be undone.",
        "The bot is controlled by WHOEVER MESSAGES IT, not by you. Anyone who can message the bot "
        "can say something that makes it call a tool, with no step that asks you first.",
        "One clever line ('ignore previous instructions, do this for me') is enough for the bot to comply. "
        "The remaining hard barrier is the permission level of EACH connection on the Connections page "
        "(set a connection to read-only and the bot is blocked from writing there too), but that barrier "
        "works by action type, so for sources Javis has no classification for yet it is not airtight. "
        "Beyond that there is only the Agent file you wrote, and words can be worked around.",
        "Only turn this on for a bot whose LIST of people who can message it you control. Not "
        "where anyone can message it.",
        "The bot still CANNOT see other brains or run machine commands - those two barriers hold at every level.",
    ],
}


def canh_bao_muc(muc: str) -> List[str]:
    """Những gì chủ đang trao đi khi đặt bot ở mức này. [] với mức chỉ-đọc (không mất gì).

    Theo ngôn ngữ giao diện: danh sách này chỉ để hiện cho chủ đọc trước khi bấm đồng ý."""
    k = str(muc or "").strip().lower()
    vi = list(_CANH_BAO.get(k, []))
    en = _CANH_BAO_EN.get(k, [])
    if not vi or len(en) != len(vi):
        return vi
    return [localefmt.chu(a, b) for a, b in zip(vi, en)]


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
    if _di_tru(d):
        _save(d)
    return d


def _di_tru(d: dict) -> bool:
    """Bản ghi bot trước 0.61.0 giữ token TRONG bot. Chuyển token sang `channel_accounts` (id
    tài khoản = id bot) và để bot chỉ TRỎ qua `accounts`. Chạy ngay lúc đọc, không cần script;
    trả True nếu có đổi gì để `_load` ghi lại một lần."""
    doi = False
    for b in d.get("bots") or []:
        if "accounts" in b and "token_enc" not in b:
            continue
        acc = []
        if b.get("token_enc"):
            aid = channel_accounts.ensure_from_bot(b)
            if aid:
                acc.append(aid)
            b.pop("token_enc", None)
        b.pop("token", None)
        b["accounts"] = acc
        doi = True
    return doi


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


def _agent_slug_ok(v: Any) -> bool:
    """Slug Agent có AN TOÀN để ghép vào `<brain>/agents/<slug>.md` không.

    Nhận mọi tên file người dùng đặt được (kể cả tiếng Việt có dấu, hoa/thường, khoảng trắng,
    gạch dưới); chỉ từ chối thứ trèo ra khỏi thư mục agents hoặc phá đường dẫn.
    """
    s = str(v or "").strip()
    if not s or len(s) > SLUG_MAX:
        return False
    return not (_SLUG_CAM.search(s) or ".." in s or s.startswith("."))


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


def _clean_ngon_ngu(v: Any) -> str:
    """Ngôn ngữ bot trả lời khách: "auto" hoặc một mã trong sổ đăng ký.

    Mặc định "auto" (bám theo ngôn ngữ khách nhắn) chứ KHÔNG bám ngôn ngữ của chủ shop. Đây
    là cả lý do trường này tồn tại: bot phục vụ NGƯỜI LẠ, và chủ người Việt bán hàng cho khách
    Nhật thì ngôn ngữ của chủ là thông tin sai để suy ra ngôn ngữ của bot.

    Mã lạ rơi về "auto" chứ không lưu nguyên, cùng lý do với `_clean_kenh`: một mã không có
    trong sổ đăng ký làm bot nói sai ngôn ngữ với khách thật mà không báo lỗi gì.
    """
    s_ = str(v or "").strip().lower()
    if s_ in ("", "auto"):
        return "auto"
    return lang_registry.chuan_hoa(s_) or "auto"


def _clean_rate(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return RATE_DEFAULT
    return max(RATE_MIN, min(n, RATE_MAX))


def _co_token(b: dict) -> bool:
    """Bot có ít nhất một tài khoản kênh còn token không (bản ghi thô)."""
    return any((channel_accounts.get_account(a) or {}).get("token_set")
               for a in (b.get("accounts") or []))


def _public(b: dict) -> dict:
    """Bản trả ra giao diện. KHÔNG bao giờ kèm token, kể cả dạng đã mã hoá."""
    out = {k: v for k, v in b.items() if k not in ("token", "token_enc")}
    # Tài khoản kênh của bot (0.61.0): bản công khai, KHÔNG token. Bot trỏ tới tài khoản; tài
    # khoản mất (xoá ở tab Tài khoản bot) thì bot còn nguyên nhưng không có gì để chạy - nói ra bằng
    # `token_set` = False, cùng cách thẻ bot vẫn báo "chưa có token".
    ds_tk = [channel_accounts.get_account(a) for a in (b.get("accounts") or [])]
    ds_tk = [a for a in ds_tk if a]
    out["accounts"] = ds_tk
    out["token_set"] = any(a.get("token_set") for a in ds_tk)
    # `channel` và `bot_username` là ẢNH của tài khoản đầu tiên - giữ cho giao diện, log và
    # test cũ đọc một chỗ; nguồn thật là `accounts`.
    if ds_tk:
        out["channel"] = ds_tk[0].get("channel") or out.get("channel")
        out["bot_username"] = ds_tk[0].get("external_id") or out.get("bot_username") or ""
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
    # Cùng lý do: bot tạo trước bản đa ngôn ngữ không có khoá này.
    out["ngon_ngu"] = _clean_ngon_ngu(out.get("ngon_ngu"))
    # "Bot trả lời ai" (0.64.85). THIẾU khoá = bản ghi cũ = hành vi cũ ("nhom"). CÓ khoá mà hỏng thì
    # về mức HẸP NHẤT, không phải mặc định: xem chú thích ở AUDIENCE.
    if "audience" not in out:
        out["audience"] = AUDIENCE_DEFAULT
    elif out["audience"] not in AUDIENCE:
        out["audience"] = AUDIENCE_HEP_NHAT
    out["people"] = _clean_groups(out.get("people"))
    # Bộ phán xử hội thoại nhóm (0.65.0). Thiếu khoá = bản ghi cũ = tắt; có khoá mà hỏng = phía hẹp nhất.
    import chatbot_reply_policy
    out["reply_policy"] = chatbot_reply_policy.normalize_config(out.get("reply_policy"))
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
    for a, tok in tokens(bot_id):
        if tok:
            return tok
    return ""


def tokens(bot_id: str) -> List[tuple]:
    """[(tài khoản công khai, token thật)] của mọi tài khoản bot đang trực. Chỉ cho mã nội bộ."""
    with _lock:
        for b in _load()["bots"]:
            if b.get("id") == bot_id:
                out = []
                for aid in b.get("accounts") or []:
                    a = channel_accounts.get_account(aid)
                    if a:
                        out.append((a, channel_accounts.get_token(aid)))
                return out
    return []


def enabled_bots() -> List[Dict[str, Any]]:
    return [b for b in list_bots() if b.get("enabled")]


def token_owner(username: str, exclude_id: str = "", channel: str = "") -> Optional[Dict[str, Any]]:
    """Bot nào đang giữ đúng con bot này (so theo tên tài khoản lấy từ getMe, THEO KÊNH).

    Từ 0.61.0 tên tài khoản nằm ở `channel_accounts`; hàm này tra kho đó rồi tìm bot đang trỏ
    tới tài khoản ấy. Không bot nào trỏ tới thì trả chính TÀI KHOẢN (có `la_tai_khoan=True`)
    để chỗ gọi nói đúng: "token này đã là tài khoản X, chọn nó thay vì dán lại".
    """
    kenh = _clean_kenh(channel) if channel else ""
    tk = channel_accounts.owner_of(username, kenh)
    if not tk:
        return None
    for b in list_bots():
        if b.get("id") == exclude_id:
            continue
        if tk["id"] in account_ids_of(b):
            return b
    if exclude_id and tk["id"] in account_ids_of(get_bot(exclude_id) or {}):
        return None
    out = dict(tk)
    out["la_tai_khoan"] = True
    return out


def account_ids_of(b: dict) -> List[str]:
    """Id tài khoản của một bản ghi bot, dù bản ghi là thô (list id) hay công khai (list dict)."""
    out = []
    for a in (b or {}).get("accounts") or []:
        aid = a.get("id") if isinstance(a, dict) else a
        if aid:
            out.append(str(aid))
    return out


def bots_using_account(account_id: str) -> List[Dict[str, Any]]:
    """Bot nào đang trực tài khoản kênh này. Một tài khoản token chỉ MỘT bot (xem owner_of)."""
    return [b for b in list_bots() if account_id in account_ids_of(b)]


def _clean_account_ids(v: Any, exclude_bot: str = "") -> tuple[List[str], str]:
    """Danh sách id tài khoản kênh cho một bot: phải tồn tại, phải là kênh gắn được bot, và
    chưa bot nào khác trực. Trả (ids, lỗi)."""
    if isinstance(v, str):
        items = re.split(r"[,;\s]+", v)
    elif isinstance(v, (list, tuple)):
        items = list(v)
    else:
        items = []
    out: List[str] = []
    for x in items:
        x = str((x.get("id") if isinstance(x, dict) else x) or "").strip()
        if not x or x in out:
            continue
        a = channel_accounts.get_account(x)
        if not a:
            return [], localefmt.chu(f"Tài khoản kênh '{x}' không tồn tại",
                                     f"Channel account '{x}' does not exist")
        for b in bots_using_account(x):
            if b.get("id") != exclude_bot:
                return [], localefmt.chu(f"Tài khoản \"{a.get('label')}\" đang do bot \"{b.get('name')}\" trực. "
                                         "Mỗi tài khoản một bot.",
                                         f"Account \"{a.get('label')}\" is served by bot \"{b.get('name')}\". "
                                         "One bot per account.")
        out.append(x)
    return out[:20], ""


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
# Cùng cổng xác nhận nhưng nói đúng chuyện đang xảy ra: chọn "mọi cuộc chat" mở bot ra cho MỌI người
# nhắn tới nick, kể cả bạn bè và người nhà khi đó là Zalo cá nhân.
LOI_CHUA_XAC_NHAN_DOI_TUONG = ("Chọn 'mọi cuộc chat trên kênh' nghĩa là ai nhắn tới tài khoản này, kể cả nhóm "
                               "và người quen, cũng được bot trả lời. Phải xác nhận đã đọc cảnh báo rủi ro "
                               "(xac_nhan_rui_ro) mới đặt được.")
# Hai câu RIÊNG cho hai chuyện khác nhau. Gộp làm một là cách cũ, và nó nói sai với chủ: người
# đã chọn Agent trong ô mà đọc "Thiếu Agent" thì không có đường nào lần ra lỗi thật.
LOI_KHONG_CO_BOT = "Không có bot nào id đó"
LOI_THIEU_AGENT = "Thiếu Agent cho bot (bot không có bộ não thì không trả lời được gì)"
LOI_SLUG_AGENT = ("Tên Agent không dùng được: phải là tên file trong thư mục agents của brain, dài tối đa "
                  f"{SLUG_MAX} ký tự, không chứa '/', '\\' hay '..'.")

# Bản tiếng Anh của các câu lỗi trên. Hằng số GIỮ tiếng Việt vì nơi khác so sánh `==` với
# chúng; chỉ chỗ trả về mới đi qua `_loi`. LOI_KHONG_CO_BOT cố ý KHÔNG dịch: main.py so
# `err == LOI_KHONG_CO_BOT` để chọn mã 404.
_LOI_EN = {
    LOI_CHUA_XAC_NHAN: "This permission level lets the bot take REAL outside actions, controlled by strangers. "
                       "You must confirm you have read the risk warning (xac_nhan_rui_ro) to set it.",
    LOI_CHUA_XAC_NHAN_DOI_TUONG: "Choosing 'every chat on the channel' means anyone who messages this account, including "
                                 "groups and people you know, gets bot replies. You must confirm you have read the "
                                 "risk warning (xac_nhan_rui_ro) to set it.",
    LOI_THIEU_AGENT: "The bot needs an Agent (without a brain the bot cannot answer anything)",
    LOI_SLUG_AGENT: ("Agent name not usable: it must be a file name in the brain's agents folder, at most "
                     f"{SLUG_MAX} characters, without '/', '\\' or '..'."),
}


def _loi(vi: str) -> str:
    return localefmt.chu(vi, _LOI_EN.get(vi) or vi)


def can_xac_nhan(muc: Any, xac_nhan: Any) -> bool:
    """Mức này có đòi chủ xác nhận rủi ro mà chưa có xác nhận không."""
    return _clean_muc(muc) in MUC_NANG and not bool(xac_nhan)


def can_xac_nhan_doi_tuong(audience: Any, xac_nhan: Any, hien_tai: Any = None) -> bool:
    """Chọn "mọi cuộc chat" (`all`) mà chưa xác nhận. Đang ở `all` rồi mà lưu lại `all` thì không hỏi
    lại (form Sửa luôn gửi lại mọi trường); hạ xuống thì không bao giờ đòi gì."""
    return str(audience or "") == "all" and str(hien_tai or "") != "all" and not bool(xac_nhan)


def create_bot(data: dict) -> tuple[Optional[str], str]:
    """Tạo bot. Trả (id, "") hoặc (None, lý do).

    Bot mới LUÔN tắt, bất kể người gọi gửi gì. Bot chăm sóc khách hàng bật lên là nói chuyện
    với người thật ngay lập tức; đó phải là một cú bấm CÓ Ý THỨC, không phải tác dụng phụ của
    việc tạo.
    """
    name = _clean_name(data.get("name"))
    if not name:
        return None, localefmt.chu("Thiếu tên bot", "Missing bot name")
    agent_slug = str(data.get("agent_slug") or "").strip()
    if not agent_slug:
        return None, _loi(LOI_THIEU_AGENT)
    if not _agent_slug_ok(agent_slug):
        return None, _loi(LOI_SLUG_AGENT)
    brain = str(data.get("brain") or "").strip()
    if not brain:
        return None, localefmt.chu("Thiếu brain riêng của bot", "Missing the bot's own brain")
    if can_xac_nhan(data.get("muc_quyen"), data.get("xac_nhan_rui_ro")):
        return None, _loi(LOI_CHUA_XAC_NHAN)
    if can_xac_nhan_doi_tuong(data.get("audience"), data.get("xac_nhan_rui_ro")):
        return None, _loi(LOI_CHUA_XAC_NHAN_DOI_TUONG)
    # Tài khoản kênh: hoặc CHỌN tài khoản có sẵn (account_ids), hoặc dán token mới (token +
    # channel) thì tạo tài khoản ngay tại đây. Cả hai cùng lúc cũng được.
    acc, loi = _clean_account_ids(data.get("account_ids"))
    if loi:
        return None, loi
    tok = str(data.get("token") or "").strip()
    if tok:
        aid, loi = channel_accounts.create_account({
            "channel": _clean_kenh(data.get("channel")), "token": tok,
            "label": data.get("account_label") or name,
            "external_id": data.get("bot_username"),
            "brain": brain,
        })
        if loi:
            return None, loi
        acc.append(aid)

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
            "accounts": acc,
            "bot_username": str(data.get("bot_username") or "").strip().lstrip("@"),
            "groups": _clean_groups(data.get("groups")),
            "reply_when": (data.get("reply_when") if data.get("reply_when") in REPLY_WHEN else "mention"),
            "audience": (data.get("audience") if data.get("audience") in AUDIENCE else AUDIENCE_DEFAULT),
            "people": _clean_groups(data.get("people")),
            "reply_policy": __import__("chatbot_reply_policy").merge_config(None, data.get("reply_policy")),
            "nguon_tra_loi": (data.get("nguon_tra_loi") if data.get("nguon_tra_loi") in NGUON
                              else NGUON_DEFAULT),
            "muc_quyen": _clean_muc(data.get("muc_quyen")) or MUC_QUYEN_DEFAULT,
            "ngon_ngu": _clean_ngon_ngu(data.get("ngon_ngu")),
            "handoff_to": str(data.get("handoff_to") or "").strip(),
            "rate_limit": _clean_rate(data.get("rate_limit")),
            "created_at": _now(),
            "updated_at": _now(),
        }
        d["bots"].append(bot)
        _save(d)
    _nhan_brain_cho_tk(bot)
    return bot["id"], ""


def _nhan_brain_cho_tk(bot: dict) -> None:
    """Tài khoản bot này giữ mà CHƯA có brain chủ thì nhận brain của bot (0.62.4).

    Tab Tài khoản bot lọc theo brain, nên một tài khoản không chủ là một thẻ lơ lửng hiện ở
    mọi brain. Gắn bot vào chính là lúc biết được nó thuộc về đâu. `nhan_brain` không ghi đè
    chủ cũ, nên gọi ở đây an toàn kể cả khi tài khoản đã có brain.
    """
    br = str((bot or {}).get("brain") or "").strip()
    if not br:
        return
    for aid in account_ids_of(bot or {}):
        try:
            channel_accounts.nhan_brain(aid, br)
        except Exception:      # noqa: BLE001 - kho tài khoản hỏng không được làm hỏng lưu bot
            pass


# Trường giao diện được phép sửa. Danh sách TRẮNG chứ không phải "nhận hết trừ vài cái":
# thêm trường mới vào bản ghi mà quên loại khỏi danh sách đen là mở một đường ghi không ai ngờ.
_PATCHABLE = ("name", "icon", "groups", "people", "audience", "reply_when", "handoff_to", "rate_limit",
              "agent_slug", "agent_brain", "brain", "bot_username", "token", "enabled",
              "nguon_tra_loi", "muc_quyen", "ngon_ngu", "account_ids", "reply_policy")
# `channel` CỐ Ý đứng ngoài danh sách trắng. Đổi kênh của một bot đã tạo là đổi sang một CON
# BOT KHÁC: token khác, danh tính khác, khách khác, và cả đống id nhóm đang lưu lập tức vô
# nghĩa. Cho sửa tại chỗ thì bản ghi còn nguyên tên và lịch sử của con cũ trong khi nó đã là
# con khác. Muốn kênh khác thì tạo bot mới - giao diện cũng khoá đúng như vậy.


def update_bot(bot_id: str, patch: dict) -> tuple[bool, str]:
    # Cùng rào với lúc tạo, và đây mới là đường hay đi hơn: bot sống nhiều tháng ở mức chỉ đọc
    # rồi một hôm được nâng lên. Thiếu rào ở đây thì cả cái gate lúc tạo thành trang trí.
    if "muc_quyen" in patch and can_xac_nhan(patch.get("muc_quyen"), patch.get("xac_nhan_rui_ro")):
        return False, _loi(LOI_CHUA_XAC_NHAN)
    if "audience" in patch and can_xac_nhan_doi_tuong(
            patch.get("audience"), patch.get("xac_nhan_rui_ro"),
            (get_bot(bot_id) or {}).get("audience")):
        return False, _loi(LOI_CHUA_XAC_NHAN_DOI_TUONG)
    # Slug Agent hỏng thì TỪ CHỐI cả bản vá, đừng lặng lẽ bỏ qua một trường. Bỏ qua nghĩa là
    # form Sửa báo "đã lưu" trong khi bot vẫn trỏ về Agent cũ, và chủ chỉ biết khi khách nhận
    # được câu trả lời của một vai mà mình tưởng đã đổi.
    if "agent_slug" in patch:
        s = str(patch.get("agent_slug") or "").strip()
        if not s:
            return False, _loi(LOI_THIEU_AGENT)
        if not _agent_slug_ok(s):
            return False, _loi(LOI_SLUG_AGENT)
    acc_moi = None
    if "account_ids" in patch:
        acc_moi, loi = _clean_account_ids(patch.get("account_ids"), exclude_bot=bot_id)
        if loi:
            return False, loi
    with _lock:
        d = _load()
        for b in d["bots"]:
            if b.get("id") != bot_id:
                continue
            if acc_moi is not None:
                b["accounts"] = acc_moi
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
                elif k == "people":
                    b["people"] = _clean_groups(v)
                elif k == "audience":
                    # Giá trị lạ thì GIỮ giá trị cũ (cùng luật với muc_quyen): rơi về mặc định là mở
                    # rộng hay thu hẹp im lặng, và chủ không biết bot đang nói chuyện với ai.
                    if v in AUDIENCE:
                        b["audience"] = v
                elif k == "reply_when":
                    if v in REPLY_WHEN:
                        b["reply_when"] = v
                elif k == "reply_policy":
                    # Gộp từng khoá, giá trị lạ giữ nguyên giá trị cũ (xem `merge_config`).
                    b["reply_policy"] = __import__("chatbot_reply_policy").merge_config(b.get("reply_policy"), v)
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
                elif k == "ngon_ngu":
                    b["ngon_ngu"] = _clean_ngon_ngu(v)
                elif k == "handoff_to":
                    b["handoff_to"] = str(v or "").strip()
                elif k == "rate_limit":
                    b["rate_limit"] = _clean_rate(v)
                elif k == "agent_slug":
                    # Đã kiểm ở đầu hàm, tới đây chắc chắn hợp lệ.
                    b.setdefault("agent", {})["slug"] = str(v).strip()
                elif k == "agent_brain":
                    b.setdefault("agent", {})["brain"] = str(v or "brain").strip() or "brain"
                elif k == "brain":
                    if str(v or "").strip():
                        b["brain"] = str(v).strip()
                elif k == "bot_username":
                    b["bot_username"] = str(v or "").strip().lstrip("@")
                    # Tên tài khoản là của TÀI KHOẢN; bot chỉ giữ một bản chép để hiện.
                    if b.get("accounts") and b["bot_username"]:
                        channel_accounts.update_account(b["accounts"][0],
                                                        {"external_id": b["bot_username"]})
                elif k == "token":
                    # Dán token mới: thay token của tài khoản đầu tiên cùng kênh; bot chưa có
                    # tài khoản nào thì tạo mới. Kênh lấy từ bản ghi (không đổi kênh tại chỗ).
                    tok = str(v or "").strip()
                    if tok:
                        kenh = _clean_kenh(b.get("channel"))
                        dich = None
                        for aid in b.get("accounts") or []:
                            a = channel_accounts.get_account(aid)
                            if a and a.get("channel") == kenh:
                                dich = aid
                                break
                        if dich:
                            channel_accounts.update_account(dich, {
                                "token": tok, "external_id": patch.get("bot_username") or ""})
                        else:
                            aid, loi = channel_accounts.create_account({
                                "channel": kenh, "token": tok, "label": b.get("name"),
                                "external_id": patch.get("bot_username") or b.get("bot_username")})
                            if loi:
                                return False, loi
                            b.setdefault("accounts", []).append(aid)
                elif k == "enabled":
                    b["enabled"] = bool(v) and _co_token(b)
            b["updated_at"] = _now()
            _save(d)
            _da_luu = dict(b)
            break
        else:
            return False, LOI_KHONG_CO_BOT
    # Ngoài khoá: `nhan_brain` tự lấy khoá của kho tài khoản, gọi trong `with _lock` ở đây là
    # giữ hai khoá lồng nhau không cần thiết.
    _nhan_brain_cho_tk(_da_luu)
    return True, ""


def set_enabled(bot_id: str, on: bool) -> tuple[bool, str]:
    """Bật/tắt. Bật mà chưa có token thì TỪ CHỐI kèm lý do, chứ không bật rồi để nó chết lặng
    lẽ trong bộ giám sát - đó đúng là kiểu hỏng mà cả tính năng này đang cố tránh."""
    with _lock:
        d = _load()
        for b in d["bots"]:
            if b.get("id") != bot_id:
                continue
            if on and not _co_token(b):
                kn = KENH_NHAN.get(_clean_kenh(b.get('channel')), '')
                return False, localefmt.chu(f"Chưa có token {kn} cho bot này", f"This bot has no {kn} token yet")
            b["enabled"] = bool(on)
            b["updated_at"] = _now()
            _save(d)
            return True, ""
    return False, LOI_KHONG_CO_BOT


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
            return False, LOI_KHONG_CO_BOT
        _save(d)
    _xoa_du_lieu_phan_xu(bot_id)
    return True, ""


def _xoa_du_lieu_phan_xu(bot_id: str) -> None:
    """Xoá bot thì xoá sạch mọi thứ bộ phán xử đã học về bot đó (nội dung chat khách). Chỉ đụng kho khi nó
    đã tồn tại: bot chưa từng bật bộ phán xử không được làm sinh ra một file rỗng."""
    try:
        import chatbot_reply_policy_store as _rps
        if _rps.db_path().exists():
            _rps.delete_bot(bot_id)
    except Exception:      # noqa: BLE001 - dọn hỏng không được làm hỏng việc xoá bot
        pass


def bots_using_agent(brain: str, slug: str) -> List[Dict[str, Any]]:
    """Bot nào đang trỏ vào Agent này. Dùng để CHẶN xoá Agent còn bot dùng, thay vì để bot
    thành mồ côi rồi im lặng trả lời sai."""
    out = []
    for b in list_bots():
        a = b.get("agent") or {}
        if str(a.get("brain")) == str(brain) and str(a.get("slug")) == str(slug):
            out.append(b)
    return out
