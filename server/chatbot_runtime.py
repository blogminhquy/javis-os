"""Bộ giám sát Bot chuyên trách: mỗi bot một tiến trình long-polling Telegram riêng.

Ba thứ module này chịu trách nhiệm, và cả ba đều là chỗ dễ hỏng im lặng:

1. **VÒNG ĐỜI.** Bật/tắt phải có tác dụng NGAY, không đòi khởi động lại Javis. Bot chăm sóc
   khách nói bậy một câu thì phải tắt được trong ba giây. Nên bật = tạo task, tắt = huỷ task,
   sửa token = huỷ RỒI mới tạo lại (đảo thứ tự là có lúc hai poller cùng sống trên một token,
   Telegram trả 409 và CẢ HAI cùng chết).

2. **PROMPT.** Bot KHÔNG dùng system prompt của Javis - prompt đó dạy cách điều phối, ghi
   vault, giao việc, toàn thứ bot khách hàng không được làm. Nó dùng prompt của chính Agent nó
   trỏ tới, cộng luật trả lời khách.

3. **RÀO.** Danh sách lệnh TRẮNG (không có lệnh quản trị nào), giới hạn tần suất mỗi người, và
   chuyển người thật khi bí. Mức quyền thì áp ở `main._tg_answer_engine` bằng mã, không phải ở
   đây và càng không phải trong prompt: bản ghi có `muc_quyen` (suggest/auto/full), lượt chạy rẽ
   theo đúng chữ đó sang đường không-tool hay đường có-tool-của-hub. Chữ trong prompt thì lách
   được; nhánh trong mã thì không.

Một rào nữa đứng riêng vì nó từng hỏng theo kiểu tệ nhất: **nhóm phải được chủ cho phép**. Rào
thì đúng, cách từ chối thì sai - bot im hoàn toàn, không log, không dòng nào trên trang Chatbot,
nên "thả bot vào nhóm rồi gọi tên nó" trông y hệt "bot hỏng". Nay từ chối vẫn từ chối, nhưng nó
NÓI: một câu duy nhất cho người đang gọi, và nhóm đó hiện lên thẻ bot để chủ bấm cho phép. Xem
`_ly_do_im`, `_make_precheck_fn`, `nhom_cho`.

Xem docs/dev/2026-08-bot-chuyen-trach-spec.md.
"""
from __future__ import annotations

import asyncio
import sys

import lang_registry
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import channel_accounts
import channels
import chatbot_grounding
import chatbot_log
import chatbot_reply_policy
import chatbot_reply_policy_store
import chatbot_store
import chatbot_tu_dong
import conversations

# Kênh -> lớp vận chuyển: tra SỔ ĐĂNG KÝ KÊNH (server/channels). Trước 0.61.0 là một bảng chép
# tay ở đây; nay thêm kênh là thêm một module ở sổ, bộ giám sát không đổi.
def _lop_kenh(kenh: str):
    m = channels.module(kenh)
    return getattr(m, "Transport", None) if m else None

# Menu lệnh Telegram của bot khách. ĐÚNG bằng danh sách trắng trong `_make_command_fn`, không
# hơn. Menu là một mặt giao diện: liệt kê ở đó những lệnh bot từ chối chạy là dạy khách đi tìm
# một tập lệnh khác, còn liệt kê lệnh quản trị của bot chủ thì khai luôn là có tập lệnh đó.
LENH_KHACH = [
    {"command": "help", "description": "Bot này giúp được gì"},
    {"command": "nhanvien", "description": "Nhờ người thật hỗ trợ"},
    {"command": "id", "description": "Xem ID cuộc trò chuyện này"},
]

# bot_id -> {"pollers": {account_id: transport}, "cfg": dict, "started": float, "answered": int}
# Từ 0.61.0 một bot trực NHIỀU tài khoản kênh (bot Telegram + bot Zalo cùng một vai), nên mỗi
# bot có một poller cho mỗi tài khoản. `_poller_dau(bot_id)` cho chỗ chỉ cần "một cái để gửi".
_RUNNING: Dict[str, dict] = {}


def _poller_dau(bot_id: str):
    run = _RUNNING.get(bot_id) or {}
    for tb in (run.get("pollers") or {}).values():
        return tb
    return None
# (bot_id, chat_id) -> deque[timestamp] cho giới hạn tần suất theo GIỜ
_HITS: Dict[tuple, deque] = {}
# (bot_id, chat_id) -> số lượt BÍ LIÊN TIẾP. Trả lời được một câu là về 0.
_BI_LIEN_TIEP: Dict[tuple, int] = {}
# bot_id đã báo lỗi kỹ thuật cho nhân viên và chưa chạy lại được lượt nào. Chống báo mỗi lượt
# khi engine hỏng - lúc đó MỌI lượt đều gãy.
_DA_BAO_LOI: set = set()

# bot_id -> {chat_id: {"chat_id", "ten", "ts", "lan", "cau"}} - những nhóm CÓ NGƯỜI GỌI BOT mà
# chủ chưa cho phép. Đây là bản vá cho lỗi hỏng-lặng-lẽ nặng nhất của tính năng nhóm: thả bot
# vào nhóm, gọi tên nó, và không có gì xảy ra - không câu trả lời, không log, không dòng nào
# trên trang Chatbot. Chủ chỉ có thể kết luận "bot hỏng".
#
# Giữ trong RAM chứ không ghi đĩa: đây là hàng ĐỢI DUYỆT chứ không phải dữ liệu người dùng, và
# nó tự đầy lại - ai gọi bot lần nữa là nhóm đó lại hiện ra. Ghi đĩa chỉ thêm một kho phải dọn.
_NHOM_CHO: Dict[str, Dict[str, dict]] = {}
MAX_NHOM_CHO = 20       # trần mỗi bot: người lạ thả bot vào 500 nhóm cũng không phình bộ nhớ

# (bot_id, chat_id) đã nói câu "chưa được bật cho nhóm này". Nói ĐÚNG MỘT LẦN mỗi nhóm.
_DA_BAO_NHOM: set = set()

# Câu nói duy nhất bot gửi vào một nhóm chưa được cho phép.
#
# Vì sao nói thay vì im hẳn: im hoàn toàn đúng về mặt an toàn nhưng sai về mặt sự thật. Người
# gọi bot gần như luôn là chủ hoặc người của chủ đang thử, và thứ họ nhận được là một con bot
# "hỏng". Một câu, một lần mỗi nhóm, là đủ để biến một lỗi không thể chẩn đoán thành một việc
# bấm một nút là xong.
CAU_NHOM_CHUA_BAT = ("Em chưa được bật cho nhóm này ạ. Chủ bot mở trang Chatbot của Javis, "
                     "ở thẻ của em sẽ thấy nhóm này đang chờ, bấm **Cho phép** một cái là em "
                     "trả lời được ngay.")

# Bí bao nhiêu lượt liên tiếp thì mới gọi người thật.
#
# Bản 0.20.0 báo ngay từ lượt bí ĐẦU TIÊN, và thực tế nó kêu vì một câu hỏi vu vơ ("lý thuyết
# về kỷ luật của em như nào?"). Nhân viên bị đánh thức vì một câu không ai cần xử lý thì vài
# lần là họ tắt thông báo, và lúc có khách thật cần giúp thì không ai đọc nữa.
#
# Bí một câu là chuyện bình thường. Bí HAI câu liên tiếp mới là dấu hiệu người ta đang mắc kẹt
# thật - đó mới đáng gọi người.
BI_LIEN_TIEP_DE_GOI = 2

# Người gọi bơm vào lúc khởi động (main.py). Tách ra để module này không import ngược main.
_deps: Dict[str, Callable] = {}


def wire(*, answer, brain_root, read_agent):
    """main.py cấp ba thứ: lõi một lượt, đường tới brain, và cách đọc file Agent."""
    _deps["answer"] = answer
    _deps["brain_root"] = brain_root
    _deps["read_agent"] = read_agent


# ============================================================
# Prompt của bot
# ============================================================
# Prompt của bot = prompt của chính Agent nó trỏ tới. Javis KHÔNG chèn luật của mình vào.
#
# Bản 0.19.0 tới 0.20.1 đều chèn một khối "luật bắt buộc" đứng trên mọi hướng dẫn khác. Sai từ
# gốc: người dùng đã viết quy định trong file Agent rồi, khối kia chỉ đè lên và cãi nhau với
# nó. Chủ repo nói thẳng (2026-08-04): "Anh có Agent và quy định của nó rồi, em đừng tự thêm
# vào quy định của nó."
#
# Rào duy nhất còn lại là CÁCH LY BRAIN, và nó nằm ở MÃ chứ không ở chữ: bot chỉ đọc được
# brain của chính nó, không thấy brain khác, không ra được ngoài máy. Xem `start_bot` và
# `main._tg_answer_engine`. Rào bằng mã thì lời lẽ khôn khéo không lách được; rào bằng chữ
# thì vừa lách được, vừa làm hỏng chính Agent người dùng viết.

# Tài liệu tra sẵn từ brain của bot, đưa vào như DỮ LIỆU chứ không kèm mệnh lệnh nào.
_CO_TAI_LIEU = """
## Tài liệu trong brain của bạn (đã tra sẵn theo đúng câu hỏi này)

{khoi}
"""

# Chế độ "chỉ tài liệu" là lựa chọn CỦA NGƯỜI DÙNG trên trang Chatbot, không phải mặc định của
# Javis. Ai bật nó là chủ động muốn bot im khi thiếu căn cứ (bot đọc giá, đọc chính sách), nên
# ở đây mới có một câu chỉ dẫn - và chỉ ở đây.
_KHONG_TAI_LIEU_CHAT = """
## Tài liệu trong brain của bạn

Đã tra và không có phần nào nói về câu hỏi này. Bot này được chủ đặt ở chế độ CHỈ TRẢ LỜI THEO
TÀI LIỆU, nên lượt này hãy nói bạn chưa có thông tin thay vì trả lời bằng kiến thức chung.
"""


# Zalo CÁ NHÂN của chủ (0.64.80). Khác Telegram/Zalo Bot ở chỗ người nhắn tới không chỉ là khách:
# đây là nick chủ dùng hằng ngày nên bạn bè, người nhà, đồng nghiệp đều nhắn vào. Chủ đã chọn
# (29/09) để bot TỰ QUYẾT có trả lời không thay vì bật công tắc từng người, nên quyết định đó phải
# được nói cho model biết - và nó là chỉ dẫn duy nhất Javis thêm vào prompt bot, chỉ ở kênh này.
IM_LANG = "[IM_LANG]"
_CAU_ZALO_CA_NHAN = f"""
## Kênh này là Zalo CÁ NHÂN của chủ

Bạn đang trả lời tin nhắn ở tài khoản Zalo cá nhân của chủ, và câu bạn gửi đi mang TÊN CHỦ.
Người nhắn tới có thể là khách, nhưng cũng có thể là bạn bè, người nhà, đồng nghiệp của chủ.
Hãy tự quyết định có nên trả lời hay không: chỉ trả lời khi tin nhắn đúng là việc mà vai của bạn
phụ trách. Nếu đó là chuyện riêng tư, chuyện gia đình bạn bè, một tin không cần hồi đáp, hoặc
bạn không chắc có nên nhân danh chủ trả lời hay không, thì KHÔNG trả lời: viết đúng một dòng
`{IM_LANG}` và không thêm chữ nào khác.
"""

# Chế độ "Tự đánh giá" (0.64.82): một tin trong NHÓM mà không ai gọi tên bot. Cùng lý do với đoạn
# trên (chủ đã chọn để bot tự quyết, nên phải nói cho model biết), và cũng chỉ hiện ở đúng lượt
# đó: lượt được tag hay chat riêng thì bot trả lời bình thường, không bị dạy im.
_CAU_NHOM_TU_DONG = f"""
## Tin này ở trong NHÓM và không ai gọi tên bạn

Bạn đang đọc một nhóm chat. Tin dưới đây không nhắm tới bạn. Chỉ trả lời khi đó là một câu hỏi
hoặc lời nhờ giúp mà tài liệu ở trên trả lời được. Nếu là các thành viên trò chuyện với nhau,
đùa, hoặc tài liệu không đủ để trả lời chắc chắn thì KHÔNG trả lời: viết đúng một dòng
`{IM_LANG}` và không thêm chữ nào khác.
"""


def build_bot_prompt(bot: dict) -> str:
    """System prompt của một lượt bot = ĐÚNG file Agent, cộng tài liệu đã tra sẵn.

    Không thêm luật nào của Javis. Người dùng viết quy định trong file Agent; việc của hàm này
    là chuyển nguyên nó xuống, không phải bình luận thêm.

    Đọc Agent LÚC CHẠY chứ không chép vào bản ghi bot: sửa Agent ở trang Agents là bot đổi
    theo ngay. Agent biến mất thì bot vẫn phải trả lời được chứ không sập - và trang Chatbot
    có việc báo cho chủ biết.
    """
    a = (bot or {}).get("agent") or {}
    meta, than = {}, ""
    try:
        reader = _deps.get("read_agent")
        if reader:
            meta, than = reader(a.get("brain") or "brain", a.get("slug") or "")
    except Exception as e:
        print(f"[chatbot prompt] đọc agent lỗi: {e}", file=sys.stderr)

    ten = str(meta.get("name") or bot.get("name") or "Trợ lý")
    vai = str(meta.get("role") or "")

    phan = [f"Bạn là **{ten}**." + (f" {vai}" if vai else "")]

    # NGÔN NGỮ của bot, và đây là hòn đảo prompt tách hẳn: nó không nối CLAUDE.md, không đi
    # qua ContextCompiler, không đi qua build_system_prompt. Bỏ sót chỗ này thì đúng ca dùng
    # đáng tiền nhất (chủ shop Việt, bot đối ngoại phục vụ khách Nhật/Hàn) không có một dòng
    # chỉ dẫn ngôn ngữ nào.
    #
    # Một câu ngắn chứ không phải khối đầy đủ như prompt chính: prompt bot vốn chỉ vài chục
    # token, nhét 60 token luật ngôn ngữ vào là làm lệch hẳn tỉ trọng so với file Agent của
    # chủ - mà file đó mới là thứ quyết định bot nói gì.
    _ma = lang_registry.chuan_hoa((bot or {}).get("ngon_ngu") or "")
    if _ma:
        _l = lang_registry.get(_ma)
        phan.append(f"\nNGÔN NGỮ: luôn trả lời khách bằng {_l.lang_directive}, "
                    f"kể cả khi khách nhắn bằng tiếng khác. {_l.nudge}")
    else:
        phan.append("\nNGÔN NGỮ: trả lời bằng ĐÚNG ngôn ngữ khách đang nhắn.")
    if than.strip():
        phan.append("\n" + than.strip())
    if not meta:
        # Agent bị xoá hay đổi slug: bot đang chạy mà KHÔNG có hướng dẫn nào. Một dòng nêu
        # đúng sự thật đó, để nó thận trọng thay vì tự tin bịa. Đây là lấp chỗ trống khi không
        # có quy định, không phải thêm vào quy định đã có.
        phan.append("\nLƯU Ý: chưa nạp được hướng dẫn cho vai này.")

    # Tài liệu đã tra sẵn cho ĐÚNG câu hỏi này, do _make_answer_fn gắn vào. Không có khoá này
    # nghĩa là prompt đang được dựng ngoài luồng một lượt thật (vd để xem trước), lúc đó không
    # bịa ra khối tài liệu nào cả.
    tl = (bot or {}).get("_tai_lieu")
    if isinstance(tl, dict):
        if tl.get("co"):
            phan.append(_CO_TAI_LIEU.format(khoi=tl.get("khoi") or ""))
        elif bot.get("nguon_tra_loi") == "tai_lieu":
            phan.append(_KHONG_TAI_LIEU_CHAT)
    # Kênh của LƯỢT này, do _make_answer_fn gắn vào. Chỉ Zalo cá nhân mới có thêm đoạn này.
    if (bot or {}).get("_kenh_luot") == "zalo_personal":
        phan.append(_CAU_ZALO_CA_NHAN)
    # Lượt Tự đánh giá do _make_answer_fn gắn. Cờ chứ không suy từ meta: prompt được dựng ở đây,
    # nơi không có meta của lượt.
    if (bot or {}).get("_tu_dong"):
        phan.append(_CAU_NHOM_TU_DONG)
    return "\n".join(phan)


# ============================================================
# Rào
# ============================================================
def _qua_han_muc(bot_id: str, chat_id: str, tran: int) -> bool:
    """Giới hạn tần suất theo GIỜ trượt, tính riêng từng người trong từng bot.

    Vì sao cần: một người rảnh trong nhóm đủ đốt hết quota model của chủ trong một buổi chiều,
    và chủ chỉ biết khi nhìn hoá đơn.
    """
    key = (bot_id, str(chat_id))
    now = time.time()
    dq = _HITS.setdefault(key, deque())
    while dq and now - dq[0] > 3600:
        dq.popleft()
    if len(dq) >= max(1, int(tran or 20)):
        return True
    dq.append(now)
    return False


def _dang_khac(chat_id: str) -> str:
    """Dạng CÒN LẠI của cùng một nhóm Telegram, hoặc "" nếu không có dạng nào khác.

    Nhóm thường có id `-123`; nâng lên siêu nhóm thì Telegram đổi thành `-100123`. Việc nâng
    cấp xảy ra ngoài tầm với của Javis (thêm quản trị viên, bật lịch sử cho thành viên mới,
    nhóm đông lên) và không báo ai cả. Chủ khai id lúc còn là nhóm thường, hôm sau bot im -
    đúng kiểu hỏng mà không có manh mối nào để lần.
    """
    s = str(chat_id or "").strip()
    if not s.startswith("-") or not s[1:].isdigit():
        return ""
    if s.startswith("-100") and len(s) > 4:
        return "-" + s[4:]
    return "-100" + s[1:]


def _khop_nhom(danh_sach, chat_id: str) -> bool:
    """Nhóm này có nằm trong danh sách chủ đã khai không - tính cả dạng id trước/sau nâng cấp."""
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    ds = {str(x).strip() for x in (danh_sach or [])}
    khac = _dang_khac(cid)
    return cid in ds or bool(khac and khac in ds)


def _audience_cua(bot_cfg: dict) -> str:
    """"Bot trả lời ai" của một bản ghi. Thiếu khoá = bản ghi cũ = `nhom` (hành vi cũ). Có khoá mà
    giá trị hỏng = `chon` (hẹp nhất): sai về phía im thì chủ thấy bot im và sửa, sai về phía mở thì
    bot nói với người lạ dưới tên người thật. `chatbot_store._public` áp cùng luật này lúc đọc,
    nhưng hàm này còn nhận cả dict trần (test, đường vào khác) nên tự canh lấy."""
    if "audience" not in (bot_cfg or {}):
        return chatbot_store.AUDIENCE_DEFAULT
    a = (bot_cfg or {}).get("audience")
    return a if a in chatbot_store.AUDIENCE else chatbot_store.AUDIENCE_HEP_NHAT


def _nhom_duoc_phep(bot_cfg: dict, chat_id) -> bool:
    """Nhóm này đã được cho phép chưa: `all` = mọi nhóm; còn lại phải nằm trong `groups`."""
    if _audience_cua(bot_cfg) == "all":
        return True
    return _khop_nhom(bot_cfg.get("groups") or [], chat_id)


def _ly_do_im(bot_cfg: dict, meta: dict) -> str:
    """Vì sao bot KHÔNG mở miệng ở lượt này. "" nghĩa là cứ trả lời.

    Tin nhắn riêng: luôn trả lời. Trong NHÓM: chỉ nhóm đã khai, và theo `reply_when`.

    Hai cờ `mentioned`/`reply_to_bot` do `TelegramBot._build_meta` gắn, đọc từ `entities` và
    `reply_to_message` của chính tin nhắn. KHÔNG dựa vào chế độ riêng tư của Telegram để suy
    ra chúng: chế độ đó tắt được ở BotFather, và lúc tắt thì bot nhận MỌI câu khách nói với
    nhau - đúng lúc cần luật này nhất thì nó lại không còn đúng.

    Trả LÝ DO chứ không trả bool vì hai lý do phải xử lý khác nhau hoàn toàn: "nhóm chưa được
    cho phép" là việc của CHỦ và phải nổi lên trang Chatbot, còn "không ai gọi tên" là hành vi
    đúng và phải im tuyệt đối.
    """
    loai = str((meta or {}).get("chat_type") or "private")
    aud = _audience_cua(bot_cfg)
    if loai == "private":
        # "Bot trả lời ai" (0.64.85): chỉ `chon` mới lọc người. `nhom` (mặc định, hành vi cũ) và `all`
        # cho mọi người nhắn riêng. Người chưa chọn có mã RIÊNG: khác "không ai gọi tên" (im đúng),
        # đây là việc của CHỦ và phải nổi lên danh sách chờ duyệt, cùng lý do với nhóm chưa bật.
        if aud != "chon":
            return ""
        if _khop_nhom(bot_cfg.get("people") or [], (meta or {}).get("chat_id")):
            return ""
        return "nguoi_chua_chon"
    # Chưa khai nhóm nào thì bot không tự nhận việc trong nhóm lạ. Cùng một lý do với nhóm đã
    # khai nhưng không phải nhóm này, nên cùng một mã: cả hai đều sửa bằng cách cho phép nhóm.
    # Với `all` mọi nhóm bot có mặt đều đã được phép: chỉ còn `reply_when` quyết khi nào lên tiếng.
    if not _nhom_duoc_phep(bot_cfg, (meta or {}).get("chat_id")):
        return "nhom_chua_bat"
    if bot_cfg.get("reply_when") == "always":
        return ""
    if (meta or {}).get("mentioned") or (meta or {}).get("reply_to_bot"):
        return ""
    # "Tự đánh giá" cho đi tiếp: tin này chưa được gọi tên, nhưng có trả lời hay không do bộ đánh
    # giá quyết ở `_make_answer_fn` (cần tra tài liệu, việc chặn, không làm được ở hàm thuần này).
    # So đúng chữ "auto": giá trị lạ vẫn rơi xuống "khong_goi_ten" bên dưới, tức fail-closed.
    if bot_cfg.get("reply_when") == "auto":
        return ""
    return "khong_goi_ten"


def _nen_tra_loi(bot_cfg: dict, meta: dict) -> bool:
    """Có mở miệng không. Vỏ bool của `_ly_do_im`, giữ cho chỗ gọi chỉ cần biết có/không."""
    return not _ly_do_im(bot_cfg, meta)


# ============================================================
# Nhóm đang chờ chủ cho phép
# ============================================================
def _ghi_nhom_cho(bot_id: str, meta: dict, cau: str = "", dem: bool = True) -> None:
    """Đưa một nhóm chưa được bật lên hàng đợi duyệt của trang Chatbot.

    `dem=False` = chỉ THẤY nhóm (có tin bất kỳ về từ đó), không phải một lần gọi bot. Phân biệt
    vì hai thứ nói hai chuyện khác nhau với chủ: "bot đang nằm trong nhóm này" là thông tin,
    còn "có người gọi bot 5 lần mà nó không trả lời được" là việc cần làm ngay. Đếm gộp thì
    con số mất hết ý nghĩa - mọi câu người ta nói với nhau trong nhóm đều cộng vào.
    """
    cid = str((meta or {}).get("chat_id") or "").strip()
    if not cid:
        return
    # Từ 0.64.85 hàng đợi chứa cả NGƯỜI chưa được chọn (audience `chon`), không chỉ nhóm: `loai` cho
    # giao diện biết bấm Cho phép thì gọi đường nào. Người thì tên lấy từ tên người nhắn.
    loai = "group" if str((meta or {}).get("chat_type") or "group") != "private" else "private"
    m = meta or {}
    ten_moi = str((m.get("chat_title") or m.get("user_name") or "") if loai == "private"
                  else (m.get("chat_title") or ""))[:80]
    ds = _NHOM_CHO.setdefault(bot_id, {})
    cu = ds.get(cid)
    if cu:
        if dem:
            cu["lan"] = cu.get("lan", 0) + 1
            cu["ts"] = time.time()
        if cau:
            cu["cau"] = str(cau)[:200]
        if ten_moi:
            cu["ten"] = ten_moi
        return
    if len(ds) >= MAX_NHOM_CHO:
        # Đầy thì bỏ mục CŨ NHẤT. Nhóm vừa có người gọi đáng nhìn hơn nhóm im từ tuần trước.
        cu_nhat = min(ds, key=lambda k: ds[k].get("ts", 0))
        ds.pop(cu_nhat, None)
    ds[cid] = {"chat_id": cid, "loai": loai, "ten": ten_moi,
               "ts": time.time(), "lan": 1 if dem else 0, "cau": str(cau or "")[:200]}


def nhom_cho(bot_id: str) -> list:
    """Danh sách nhóm đang chờ chủ cho phép, mới gọi nhất lên đầu."""
    ds = list((_NHOM_CHO.get(bot_id) or {}).values())
    ds.sort(key=lambda x: x.get("ts", 0), reverse=True)
    return ds


def bo_nhom_cho(bot_id: str, chat_id: str = "") -> None:
    """Dọn hàng đợi sau khi chủ đã quyết (cho phép hoặc bỏ qua)."""
    if not chat_id:
        _NHOM_CHO.pop(bot_id, None)
        return
    cid = str(chat_id).strip()
    ds = _NHOM_CHO.get(bot_id) or {}
    for k in (cid, _dang_khac(cid)):
        if k:
            ds.pop(k, None)
    if not ds:
        _NHOM_CHO.pop(bot_id, None)


# ============================================================
# Bộ phán xử hội thoại nhóm (0.65.0): phần nối vào bot
# ============================================================
# Đặc tả: docs/superpowers/specs/2026-09-30-bo-phan-xu-nhom-design.md. Bộ máy thuần nằm ở
# `chatbot_reply_policy`; file này chỉ dựng Event/BotProfile từ bản ghi bot và meta của kênh, rồi
# cắm vào ba chỗ: nhận diện gọi tên trơn (mọi bot), móc cho lớp vận chuyển đọc được cả nhóm (Zalo
# cá nhân), và nhánh `on` trong `_answer`.
_RP_RATE = {"het_han_muc": "rate_limited", "het_han_nguoi": "rate_limited_user", "vua_tra_loi": "just_spoke"}
_RP_CHECK_EVERY_S = 300
_RP_CHECKED: Dict[str, float] = {}


def _rp_is_group(meta) -> bool:
    return str((meta or {}).get("chat_type") or "private") != "private"


def _rp_agent_text(cfg: dict) -> str:
    """Nguyên văn file Agent của bot (vai + quy định): nguyên liệu soạn hồ sơ vai, và vai thô dự phòng."""
    try:
        a = cfg.get("agent") or {}
        meta, body = _deps["read_agent"](a.get("brain") or cfg.get("brain"), a.get("slug"))
        head = " ".join(str(v) for k, v in (meta or {}).items() if k in ("name", "role", "description") and v)
        return (head + "\n" + str(body or "")).strip()
    except Exception:      # noqa: BLE001 - không đọc được Agent thì bộ phán xử chạy với vai rỗng
        return ""


def _rp_role_text(cfg: dict) -> str:
    """Vai của CHÍNH bot này: hồ sơ vai máy đã soạn nếu có, không thì vai thô trong file Agent."""
    try:
        p = chatbot_reply_policy_store.get_role_profile(cfg.get("id"))
        if p and p.get("generated_text"):
            return p["generated_text"]
    except Exception:      # noqa: BLE001
        pass
    return _rp_agent_text(cfg)[:1500]


def _rp_profile(cfg: dict, meta: dict = None, with_role: bool = True):
    return chatbot_reply_policy.BotProfile.from_bot(
        cfg, auto_aliases=(meta or {}).get("aliases_auto") or (),
        role_text=_rp_role_text(cfg) if with_role else "")


def _rp_event(cfg: dict, profile, text: str, meta: dict, owner_typing: bool = False):
    now = float((meta or {}).get("ts") or time.time())
    bot_id, chat_id = str(cfg.get("id") or ""), str((meta or {}).get("chat_id") or "")
    last, addressee = chatbot_reply_policy.bot_context(bot_id, chat_id, now)
    uid = str((meta or {}).get("user_id") or "")
    return chatbot_reply_policy.Event(
        channel=str((meta or {}).get("platform") or ""), bot_id=bot_id, chat_id=chat_id,
        chat_type=str((meta or {}).get("chat_type") or "group"), msg_id=str((meta or {}).get("message_id") or ""),
        ts=now, text=str(text or ""), sender_id=uid, sender_name=str((meta or {}).get("user_name") or ""),
        sender_role=chatbot_reply_policy.sender_role(profile, uid), mentioned=bool((meta or {}).get("mentioned")),
        reply_to_bot=bool((meta or {}).get("reply_to_bot")),
        window=chatbot_reply_policy.window_of(bot_id, chat_id, now),
        bot_last_spoke_ts=last, last_bot_addressee=addressee, owner_typing=bool(owner_typing))


def _rp_named_meta(cfg: dict, text: str, meta) -> dict:
    """Bản sao của `meta` với `mentioned` = True nếu tin nhóm GỌI BOT BẰNG TÊN TRƠN ("nhi mai ơi").

    Áp dụng cho MỌI bot, không phụ thuộc bộ phán xử bật hay tắt: đây là sửa lỗi nhận diện. Trả bản sao
    vì `_gan_tai_khoan` đã bọc meta thành bản sao riêng cho từng callback, nên đánh dấu tại chỗ ở một
    callback không truyền sang callback kia; mỗi chỗ dùng tự gọi hàm này.
    """
    m = dict(meta or {})
    if not _rp_is_group(m) or m.get("mentioned") or m.get("reply_to_bot"):
        return m
    try:
        profile = _rp_profile(cfg, m, with_role=False)
        ev = chatbot_reply_policy.Event(channel="", bot_id=profile.bot_id, chat_id="", chat_type="group", msg_id="",
                                        ts=0.0, text=str(text or ""), sender_id="")
        if chatbot_reply_policy.detect_address(ev, profile).level == "certain":
            m["mentioned"] = True
    except Exception as e:      # noqa: BLE001 - nhận diện hỏng thì giữ nguyên như chưa có tính năng này
        print(f"[reply_policy] nhận diện tên trơn lỗi: {type(e).__name__}", file=sys.stderr)
    return m


_RP_RETRACT_CODES = ("rate_limited", "taken_over", "agent_silent")


def _rp_retract(dec, code: str) -> None:
    """Bộ phán xử nói `reply` nhưng bước sau chặn mất (hạn mức, Tiếp quản, Agent chọn im): sửa dòng nhật ký cho
    đúng sự thật và đóng cửa theo dõi, kẻo tin nối tiếp sau đó được gắn nhãn "đúng" cho một câu bot chưa từng nói."""
    if dec is None or not getattr(dec, "decision_id", 0):
        return
    try:
        chatbot_reply_policy_store.amend_decision(dec.decision_id, "silent", code)
        chatbot_reply_policy_store.close_watch(dec.decision_id)
    except Exception:      # noqa: BLE001
        pass


def _rp_rate(bot_id: str, chat_id: str, user_id: str, follow_up: bool = False) -> str:
    code = chatbot_tu_dong.duoc_tra_loi(bot_id, chat_id, user_id, follow_up=follow_up)
    return _RP_RATE.get(code, code)


def _rp_add_alias(bot_id: str, alias: str) -> None:
    cfg = chatbot_store.get_bot(bot_id) or {}
    cur = list((cfg.get("reply_policy") or {}).get("aliases") or [])
    if alias and alias not in cur:
        chatbot_store.update_bot(bot_id, {"reply_policy": {"aliases": cur + [alias]}})


def _rp_schedule_profile(cfg: dict) -> None:
    """Soạn (hoặc soạn lại) hồ sơ vai ở nền khi Agent hay mục lục tài liệu đổi. Kiểm nhiều nhất mỗi 5
    phút mỗi bot; lượt đầu chưa có hồ sơ thì bộ phán xử dùng vai thô của Agent, không phải chờ."""
    bot_id = str(cfg.get("id") or "")
    now = time.time()
    if now - _RP_CHECKED.get(bot_id, 0.0) < _RP_CHECK_EVERY_S:
        return
    _RP_CHECKED[bot_id] = now
    ask = chatbot_reply_policy.ask_fn()
    if ask is None:
        return
    try:
        asyncio.get_running_loop().create_task(_rp_profile_job(cfg, ask))
    except Exception as e:      # noqa: BLE001
        print(f"[reply_policy] lên lịch soạn hồ sơ vai lỗi: {type(e).__name__}", file=sys.stderr)


_RP_BACKOFF_S = 1800


def _rp_collect(cfg: dict) -> tuple:
    """(nguyên văn Agent, mục lục tài liệu) của bot. Đọc đĩa nên chạy trong thread, không trên vòng sự kiện."""
    root = _deps["brain_root"](cfg["brain"])
    return _rp_agent_text(cfg), chatbot_reply_policy.list_doc_titles(root)


async def _rp_profile_job(cfg: dict, ask) -> None:
    """Soạn hồ sơ vai ở nền. Chưa có hồ sơ mà soạn hỏng (engine việc nền chưa sẵn sàng...) thì lùi 30 phút mới
    thử lại, thay vì mỗi 5 phút một lần cho tới khi engine sống dậy."""
    bot_id = str(cfg.get("id") or "")
    try:
        agent_text, titles = await asyncio.to_thread(_rp_collect, cfg)
    except Exception as e:      # noqa: BLE001
        print(f"[reply_policy] đọc Agent/tài liệu lỗi: {type(e).__name__}", file=sys.stderr)
        _RP_CHECKED[bot_id] = time.time() + _RP_BACKOFF_S - _RP_CHECK_EVERY_S
        return
    res = await chatbot_reply_policy.ensure_role_profile(cfg, agent_text, titles, chatbot_reply_policy_store, ask)
    if not res.get("changed") and not res.get("generated_text"):
        _RP_CHECKED[bot_id] = time.time() + _RP_BACKOFF_S - _RP_CHECK_EVERY_S


class PolicyHooks:
    """Móc bộ phán xử cho lớp vận chuyển đọc được TOÀN BỘ tin nhóm (Zalo cá nhân).

    `prepare` chạy cho MỌI tin nhóm đã được phép, trước chốt chặn và trước khi chờ nhường. Nó trả
    `{"mode", "level", "action"}` với `action` là:
      - `legacy`: giữ luật cũ (bộ phán xử tắt, hoặc đang Chạy thử);
      - `answer`: đi tiếp vào `answer_fn` (được gọi chắc chắn, hoặc là ứng viên);
      - `drop`: im, đã ghi vết lý do (chỉ ở chế độ Bật).
    """

    _SHADOW_MAX = 20        # số lượt chạy thử tối đa đang chờ; đầy thì bỏ lượt mới (chạy thử chỉ để so sánh)

    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self._shadow_inflight = 0

    def prepare(self, text: str, meta: dict, owner_typing: bool = False):
        cfg = chatbot_store.get_bot(self.bot_id)
        if not cfg or not _rp_is_group(meta) or not _nhom_duoc_phep(cfg, (meta or {}).get("chat_id")):
            return None
        rpc = chatbot_reply_policy.normalize_config(cfg.get("reply_policy"))
        if cfg.get("reply_when") != "auto":
            rpc = dict(rpc, mode="off")      # chỉ có nghĩa ở chế độ Tự đánh giá
        profile = _rp_profile(cfg, meta, with_role=(rpc["mode"] != "off"))
        ev = _rp_event(cfg, profile, text, meta, owner_typing)
        addr = chatbot_reply_policy.detect_address(ev, profile)
        if addr.level == "certain":
            meta["mentioned"] = True
            ev.mentioned = True
        out = {"mode": rpc["mode"], "level": addr.level, "action": "legacy"}
        if rpc["mode"] == "off":
            return out
        store = chatbot_reply_policy_store
        meta["_rp_observed"] = True
        try:
            chatbot_reply_policy.push_message(self.bot_id, ev.chat_id, chatbot_reply_policy.Message(
                ev.ts, ev.sender_id, ev.sender_name, False, ev.text))
            chatbot_reply_policy.observe(ev, profile, store, ev.ts)
            if profile.learning_enabled and ev.sender_id in profile.trainer_ids:
                asyncio.get_running_loop().create_task(chatbot_reply_policy.maybe_teach(
                    ev, profile, addr.level, store, chatbot_reply_policy.ask_fn(),
                    add_alias=lambda a: _rp_add_alias(self.bot_id, a)))
            _rp_schedule_profile(cfg)
            if addr.level == "certain":
                chatbot_reply_policy.log_called(store, ev, profile, addr, rpc["mode"])
                out["action"] = "answer"
                return out
            pre = chatbot_reply_policy.pre_screen(ev, profile, store, ev.ts)
            out["pre"] = pre
            if rpc["mode"] == "shadow":
                if pre["candidate"] and self._shadow_inflight < self._SHADOW_MAX:
                    self._shadow_inflight += 1
                    asyncio.get_running_loop().create_task(self._shadow(cfg, ev, profile))
                return out
            if not pre["candidate"]:
                chatbot_reply_policy.log_silent(store, ev, profile, pre, "on")
                out["action"] = "drop"
            else:
                out["action"] = "answer"
        except Exception as e:      # noqa: BLE001 - bộ phán xử hỏng thì rơi về luật cũ, không nuốt tin
            print(f"[reply_policy {self.bot_id}] {type(e).__name__}: {e}", file=sys.stderr)
            out["action"] = "legacy"
        return out

    async def _shadow(self, cfg: dict, ev, profile) -> None:
        """Chạy thử: người phán xử quyết song song, chỉ GHI, không ảnh hưởng việc bot làm."""
        try:
            await chatbot_reply_policy.decide(
                ev, profile, store=chatbot_reply_policy_store, ask=chatbot_reply_policy.ask_fn(),
                doc_search=lambda t: _tra_tai_lieu(self.bot_id, cfg, t), commit=False, mode="shadow")
        except Exception as e:      # noqa: BLE001
            print(f"[reply_policy {self.bot_id}] chạy thử lỗi: {type(e).__name__}: {e}", file=sys.stderr)
        finally:
            self._shadow_inflight = max(0, self._shadow_inflight - 1)

    def replied(self, meta: dict, text: str) -> None:
        """Bot vừa nói trong nhóm: nhớ để nhận ra tin nối tiếp của đúng người được trả lời."""
        cfg = chatbot_store.get_bot(self.bot_id)
        if not cfg or chatbot_reply_policy.normalize_config(cfg.get("reply_policy"))["mode"] == "off":
            return
        chatbot_reply_policy.note_bot_reply(self.bot_id, str((meta or {}).get("chat_id") or ""),
                                            str((meta or {}).get("user_id") or ""), text)


def _make_precheck_fn(bot_id: str):
    """Chốt chặn chạy TRƯỚC khi tốn một lượt engine.

    Ba việc, theo đúng thứ tự quan trọng: (1) không để người ngoài thấy "(không có nội dung)",
    (2) đưa nhóm chưa được bật lên trang Chatbot, (3) nói một câu duy nhất cho người đang gọi
    biết phải làm gì - thay vì để họ kết luận bot hỏng.
    """
    def _chan(text, meta=None):
        cfg = chatbot_store.get_bot(bot_id)
        if not cfg:
            return {}
        meta = _rp_named_meta(cfg, text, meta)      # gọi tên trơn ("nhi mai ơi") cũng là gọi bot
        ly_do = _ly_do_im(cfg, meta or {})
        if not ly_do:
            return None
        if ly_do == "nguoi_chua_chon":
            # Người ngoài danh sách (audience `chon`): im TUYỆT ĐỐI, nhưng nổi lên hàng chờ duyệt
            # kèm nút Cho phép. Im mà không để lại dấu thì chủ chỉ thấy "bot hỏng" (cùng bài học
            # với nhóm chưa bật).
            _ghi_nhom_cho(bot_id, meta or {}, text)
            return {}
        if ly_do != "nhom_chua_bat":
            return {}       # không ai gọi tên: im tuyệt đối, và không có gì để chủ duyệt
        # Nhóm chưa bật, nhưng lượt này có phải một lần GỌI BOT thật không? Hỏi lại chính luật
        # trên với giả định nhóm đã được bật: nếu vẫn im thì đây chỉ là hai người nói chuyện
        # với nhau, không có gì để chủ duyệt và tuyệt đối không được chen vào. Hỏi lại luật cũ
        # thay vì chép điều kiện ra đây: chép là có ngày hai chỗ nói khác nhau.
        gia_dinh = dict(cfg)
        gia_dinh["groups"] = [str((meta or {}).get("chat_id") or "")]
        # "Tự đánh giá" cho mọi tin đi tiếp, nhưng một tin chưa gọi tên bot KHÔNG phải một lần
        # gọi: đếm nó là "có người gọi bot" thì hàng chờ duyệt nhóm đầy số lần gọi ma.
        if gia_dinh.get("reply_when") == "auto":
            gia_dinh["reply_when"] = "mention"
        if _ly_do_im(gia_dinh, meta or {}):
            return {}
        _ghi_nhom_cho(bot_id, meta or {}, text)
        khoa = (bot_id, str((meta or {}).get("chat_id") or ""))
        if khoa in _DA_BAO_NHOM:
            return {}
        if len(_DA_BAO_NHOM) > 500:
            _DA_BAO_NHOM.clear()    # trần thô: thà nói lại một câu còn hơn phình mãi
        _DA_BAO_NHOM.add(khoa)
        return {"reply": CAU_NHOM_CHUA_BAT}
    return _chan


def _make_event_fn(bot_id: str):
    """Tin dịch vụ của nhóm. Xem `TelegramBot._bao_su_kien` để biết vì sao cần nghe."""
    async def _su_kien(loai, tt):
        cid = str((tt or {}).get("chat_id") or "")
        if loai in ("vao_nhom", "thay_nhom"):
            # `thay_nhom` = có tin bất kỳ về từ nhóm này. Nghe cả loại đó vì khi chế độ riêng
            # tư của Telegram đang bật, tin nhắc tên KHÔNG chắc tới được Javis, còn lệnh `/...`
            # thì luôn tới. Không có nhánh này thì người dùng gõ /id trong nhóm, quay lại
            # dashboard, và vẫn không thấy nhóm nào để bấm cho phép - ngõ cụt hoàn toàn.
            cfg = chatbot_store.get_bot(bot_id)
            if cfg and not _nhom_duoc_phep(cfg, cid):
                _ghi_nhom_cho(bot_id, {"chat_id": cid, "chat_type": "group",
                                       "chat_title": (tt or {}).get("chat_title")}, dem=False)
        elif loai == "roi_nhom":
            bo_nhom_cho(bot_id, cid)
            _DA_BAO_NHOM.discard((bot_id, cid))
        elif loai == "nhom_nang_cap":
            moi = str((tt or {}).get("chat_id_moi") or "")
            cfg = chatbot_store.get_bot(bot_id)
            if not (moi and cfg):
                return
            ds = [str(x) for x in (cfg.get("groups") or [])]
            if moi in ds or not _khop_nhom(ds, cid):
                return
            # Thay id cũ bằng id mới TẠI CHỖ, giữ nguyên thứ tự: chủ đã cho phép đúng nhóm này
            # rồi, việc Telegram đổi số hiệu của nó không phải là một quyết định mới.
            ds = [moi if (x == cid or x == _dang_khac(cid)) else x for x in ds]
            chatbot_store.update_bot(bot_id, {"groups": ds})
            print(f"[chatbot {bot_id}] nhóm {cid} lên siêu nhóm {moi}, đã cập nhật danh sách",
                  file=sys.stderr)
    return _su_kien


# ============================================================
# Lệnh: danh sách TRẮNG, không có lệnh quản trị nào
# ============================================================
def _chan_doan_nhom(bot_id: str, chat: str, meta: dict) -> str:
    """Vì sao bot im trong nhóm này, nói bằng lời người, kèm cách sửa.

    Đây là câu trả lời cho một câu hỏi KHÔNG chẩn đoán được từ bên ngoài. Ba nguyên nhân cho
    ra đúng một triệu chứng - "nhắn riêng thì được, trong nhóm tag tên thì im re":

      1. Nhóm chưa được chủ cho phép.
      2. Chế độ riêng tư của Telegram còn bật, nên tin nhắc tên không tới được Javis.
      3. Bot chưa hỏi được danh tính của chính nó (getMe hỏng), nên không nhận ra tên mình.

    Người đứng trong nhóm không phân biệt được ba thứ đó, và ba thứ đó sửa khác nhau hoàn
    toàn. Lệnh `/...` thì LUÔN về tới bot bất kể chế độ riêng tư, nên `/id` là chỗ duy nhất
    chắc chắn nói được câu này ra.
    """
    tb = _poller_dau(bot_id or "")
    cfg = chatbot_store.get_bot(bot_id) or {}
    dong = [f"ID cuộc trò chuyện này: `{chat}`"]
    if str((meta or {}).get("chat_type") or "private") == "private":
        return dong[0]

    if not _nhom_duoc_phep(cfg, chat):
        dong.append("Nhóm này **chưa được bật** cho em. Chủ bot mở trang Chatbot của Javis, "
                    "thẻ của em sẽ thấy nhóm này đang chờ, bấm **Cho phép** một cái là xong.")
    else:
        dong.append("Nhóm này **đã được bật** cho em rồi ạ.")

    if tb is not None and not getattr(tb, "bot_id", 0):
        dong.append("⚠ Em chưa hỏi được danh tính của chính mình từ Telegram, nên em **không "
                    "nhận ra khi có người gọi tên em**. Chủ bot vào trang Chatbot tắt rồi bật "
                    "lại em giúp ạ.")
    elif tb is not None and not getattr(tb, "doc_moi_tin_nhom", False):
        # Chế độ riêng tư chặn Ở PHÍA TELEGRAM, trước khi Javis nhìn thấy tin nào. Không nói ra
        # thì chủ chỉnh trong dashboard cả buổi mà không đổi được gì.
        dong.append("Chế độ riêng tư của Telegram đang **BẬT** cho em. Trong nhóm, thứ chắc "
                    "chắn tới được em là **lệnh `/...`** và **tin trả lời thẳng vào tin của "
                    "em**. Tag tên mà em im thì gần như luôn là vì cái này.")
        dong.append("Sửa bằng MỘT trong hai cách: mở **@BotFather** gõ `/setprivacy`, chọn em, "
                    "chọn **Disable**; hoặc cho em làm **quản trị viên** nhóm này. Xong thì tắt "
                    "bật lại em ở trang Chatbot.")
    return "\n\n".join(dong)


def _make_command_fn(bot_cfg: dict):
    async def _cmd(cmd, arg, chat, meta=None):
        res = await _cmd_goc(cmd, arg, chat, meta)
        # Lệnh cũng là một lượt khách nhìn thấy: ghi cả câu lệnh lẫn câu bot đáp vào Hộp thư.
        # `bot_cfg` là bản ghi lúc bật bot; đủ dùng vì id, tên, kênh không đổi khi bot đang chạy.
        m = dict(meta or {})
        m.setdefault("chat_id", chat)
        ghi_tin_khach(bot_cfg, m, ("/" + str(cmd or "").lstrip("/") + (" " + arg if arg else "")).strip())
        if res and res.get("reply"):
            ghi_tin_bot(bot_cfg, m, res["reply"])
        return res

    async def _cmd_goc(cmd, arg, chat, meta=None):
        c = (cmd or "").lstrip("/").lower()
        if c in ("start", "help"):
            # KHÔNG gắn "của cửa hàng" vào sau tên bot. Bot tên "Coach kỷ luật" mà Javis tự nối
            # thành "Coach kỷ luật của cửa hàng" là áp nghề bán hàng cho một Agent huấn luyện -
            # đúng lỗi chủ repo đã bác ở 0.20.1, sót lại ở đây vì lệnh không đi qua prompt.
            return {"reply": f"Chào anh chị, em là {bot_cfg.get('name') or 'trợ lý'}. "
                             f"Anh chị cứ hỏi, em trả lời trong phạm vi em biết ạ."}
        if c == "id":
            # Cần để lấy id nhóm khi thả bot vào nhóm. Id nhóm không phải bí mật với người đã
            # ở trong nhóm đó, nên để công khai được. Kèm luôn chẩn đoán: xem `_chan_doan_nhom`.
            return {"reply": _chan_doan_nhom(bot_cfg.get("id") or "", chat, meta or {})}
        if c in ("nhanvien", "nhan_vien", "human"):
            return {"reply": _bao_nhan_vien(bot_cfg, chat, "Người hỏi chủ động xin gặp người thật.")}
        # Mọi lệnh khác (kể cả /brain, /model, /status của bot chủ) im lặng: nói "không có lệnh
        # đó" là tự khai còn tồn tại một tập lệnh khác ở đâu đó.
        return {"reply": "Anh chị cứ nhắn câu hỏi bình thường giúp em ạ."}
    return _cmd


def _bao_nhan_vien(bot_cfg: dict, chat_id: str, ly_do: str) -> str:
    """Chuyển người thật. Trả về câu nói với khách; phần báo nhân viên chạy nền."""
    dich = str(bot_cfg.get("handoff_to") or "").strip()
    if not dich:
        # Chưa đặt người nhận thì nói THẬT là chưa nối được người, và mời hỏi tiếp - đừng dừng
        # hẳn cuộc trò chuyện. Câu cũ ("chưa có thông tin, chờ phản hồi") vừa sai (khách có hỏi
        # thông tin gì đâu, họ xin gặp người), vừa đóng cửa: khách không biết còn hỏi được nữa.
        return ("Hiện em chưa nối máy sang người trực được ạ. Anh chị cứ hỏi tiếp ở đây, "
                "em trả lời được tới đâu em hỗ trợ tới đó.")
    asyncio.ensure_future(_gui_nhan_vien(bot_cfg, dich, chat_id, ly_do))
    return ("Cái này để em chuyển cho người phụ trách hỗ trợ anh chị ạ. "
            "Anh chị chờ một chút nhé.")


async def _gui_nhan_vien(bot_cfg: dict, dich: str, chat_id: str, ly_do: str) -> None:
    tb = _poller_dau(bot_cfg.get("id") or "")
    if not tb:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(tb._url("sendMessage"), json={
                "chat_id": dich,
                "text": (f"🔔 Bot \"{bot_cfg.get('name')}\" cần người thật.\n"
                         f"Người nhắn: {chat_id}\nLý do: {ly_do}"),
            })
    except Exception as e:
        print(f"[chatbot handoff] {e}", file=sys.stderr)


# ============================================================
# Một lượt của bot
# ============================================================
# Dấu hiệu bot đã bí, đọc từ chính câu nó vừa nói. Cần vì tìm được tài liệu KHÔNG bảo đảm trả
# lời được: tài liệu nói về mục A trong khi người ta hỏi điều kiện của mục B, model đọc xong vẫn
# phải nói chưa có thông tin. Đó là lượt bí, và là loại đáng ghi nhất - nó chỉ đúng chỗ tài liệu
# có mà THIẾU Ý, tinh vi hơn hẳn loại không tìm ra file nào.
#
# Giữ cả cách nói CŨ ("nhân viên") lẫn cách nói trung tính: câu bot thốt ra là do file Agent
# người dùng viết, và Agent đã viết từ trước vẫn đang dùng từ cũ. Bỏ pattern cũ đi là những bot
# đó lặng lẽ ngừng được tính là bí, tab "Bot bí" rỗng dần mà không ai hiểu vì sao.
_DAU_BI = ("chưa có thông tin", "không có thông tin", "chưa nắm được", "chuyển cho nhân viên",
           "chuyển nhân viên", "chuyển cho người phụ trách", "chuyển cho người thật",
           "em chưa rõ", "chưa trả lời được")


def _co_bi(dap: str) -> bool:
    d = str(dap or "").lower()
    return any(x in d for x in _DAU_BI)


# ============================================================
# Kho hội thoại khách (Conversation DB) - adapter của bot chuyên trách
# ============================================================
# Mỗi lượt của bot đẩy HAI sự kiện chuẩn vào `conversations`: tin khách gửi tới và câu bot trả
# lời. Đây là điểm nối duy nhất giữa bot chuyên trách và Hộp thư hội thoại: Telegram hay Zalo Bot
# đều đi qua đây với cùng một `meta` (platform, chat_id, chat_type, user_name, message_id), nên
# kho không cần biết tin đến từ kênh nào.
#
# Vì sao ghi ở ĐÂY chứ không ở lớp vận chuyển: lớp đó chưa biết bot nào đang cầm tin (chỉ có
# token), còn ở đây có đủ bản ghi bot, và lượt bị chặn ở precheck (nhóm chưa cho phép) vốn
# không phải hội thoại của bot. Ghi trước khi gọi engine để tin khách còn đó kể cả khi lượt gãy.
def _tai_khoan_cua(cfg: dict, meta: dict) -> tuple:
    """(id tài khoản kênh, kênh) của lượt này. Poller gắn `account_id` vào meta (xem
    `start_bot`); thiếu thì lấy tài khoản đầu của bot; bot chưa có tài khoản nào (test, bản
    ghi cũ) thì khoá theo chính id bot như trước 0.61.0."""
    aid = str((meta or {}).get("account_id") or "")
    if not aid:
        ds = cfg.get("accounts") or []
        aid = str((ds[0] or {}).get("id") if ds and isinstance(ds[0], dict) else (ds[0] if ds else "")) or ""
    kenh = ""
    if aid:
        a = channel_accounts.get_account(aid)
        if a:
            kenh = a.get("channel") or ""
    if not kenh:
        kenh = str(cfg.get("channel") or "") or chatbot_store.KENH_DEFAULT
    return (aid or cfg.get("id") or ""), kenh


def _kenh_kho(cfg: dict, meta: dict = None) -> str:
    return _tai_khoan_cua(cfg, meta or {})[1]


def _su_kien_bot(cfg: dict, meta: dict, **phan) -> dict:
    meta = meta or {}
    aid, kenh = _tai_khoan_cua(cfg, meta)
    ev = {
        "channel": kenh,
        "account_id": aid,
        "account_name": cfg.get("name") or "",
        "bot_id": cfg.get("id") or "",
        "external_chat_id": str(meta.get("chat_id") or ""),
        "chat_type": meta.get("chat_type") or "private",
        "chat_title": meta.get("chat_title") or "",
    }
    ev.update(phan)
    return ev


def ghi_tin_khach(cfg: dict, meta: dict, text: str) -> None:
    """Tin KHÁCH gửi tới bot. Nuốt mọi lỗi: kho hỏng không được làm gãy câu trả lời."""
    try:
        meta = meta or {}
        conversations.ghi_su_kien(_su_kien_bot(
            cfg, meta, sender_type="customer",
            sender_id=str(meta.get("user_id") or meta.get("username") or ""),
            sender_name=meta.get("user_name") or meta.get("username") or "",
            message_type=conversations.loai_tin_tu_chu(text), text=text,
            external_message_id=str(meta.get("message_id") or ""),
            metadata={"username": meta.get("username") or ""}))
    except Exception as e:
        print(f"[chatbot conversations] {type(e).__name__}: {e}", file=sys.stderr)


def ghi_tin_bot(cfg: dict, meta: dict, text: str, loi: str = "", files=None) -> None:
    """Câu BOT trả lời (hoặc câu xin lỗi khi lượt gãy - vẫn là thứ khách nhìn thấy)."""
    try:
        if not str(text or "").strip() and not files:
            return
        md = {}
        if loi:
            md["loi"] = str(loi)[:300]
        if files:
            md["files"] = [str((f.get("path") if isinstance(f, dict) else f) or "")[:300]
                           for f in list(files)[:10]]
        conversations.ghi_su_kien(_su_kien_bot(
            cfg, meta, sender_type="ai", sender_name=cfg.get("name") or "",
            message_type="text", text=text, metadata=md))
    except Exception as e:
        print(f"[chatbot conversations] {type(e).__name__}: {e}", file=sys.stderr)


async def _tra_tai_lieu(bot_id: str, cfg: dict, text: str) -> dict:
    """Tra brain của bot cho MỘT câu hỏi. Quét đĩa + chấm điểm là việc CHẶN, đẩy sang thread để
    không chẹn event loop (poller của các bot khác và của cả Javis đều chạy chung một loop)."""
    tl = {"co": False, "khoi": "", "nguon": []}
    try:
        root = _deps["brain_root"](cfg["brain"])
        tl = await asyncio.to_thread(chatbot_grounding.thu_thap, root, text)
    except Exception as e:
        print(f"[chatbot {bot_id}] tra tài liệu lỗi: {e}", file=sys.stderr)
    return tl


def _ghi_bo_qua(bot_id: str, cfg: dict, meta: dict, text: str, ma: str, tl: dict = None) -> None:
    """Ghi nhật ký một tin bot CHỌN bỏ qua ở chế độ Tự đánh giá, kèm lý do đọc được.

    Chỉ ghi những tin đã QUA cửa "có giống câu hỏi không" (tin trò chuyện thì không: nhóm đông
    sẽ làm nhật ký tràn). Đây là dữ liệu để chủ chỉnh tài liệu: một dòng "khong_co_tai_lieu" là
    một câu hỏi thật của người trong nhóm mà brain của bot chưa có.
    """
    tl = tl or {}
    chatbot_log.ghi(bot_id, {
        "chat_id": str((meta or {}).get("chat_id") or ""),
        "chat_type": (meta or {}).get("chat_type"),
        "user_name": (meta or {}).get("user_name"), "hoi": text,
        "dap": f"(bot bỏ qua: {chatbot_tu_dong.ly_do_de_doc(ma)})", "loi": "",
        "co_tai_lieu": bool(tl.get("co")), "nguon": tl.get("nguon"),
        "chuyen_nguoi": False, "bi": False, "bo_qua": ma,
        "muc_quyen": cfg.get("muc_quyen") or "suggest",
    })


def _make_answer_fn(bot_id: str):
    async def _answer(text, meta=None, progress=None):
        cfg = chatbot_store.get_bot(bot_id)
        if not cfg:
            return {"text": "", "files": [], "im_lang": True}
        meta = _rp_named_meta(cfg, text, meta)
        # Lớp thứ HAI của cùng một luật (`precheck_fn` đã chặn ở tầng kênh). Giữ cả hai vì hai
        # cái canh hai thứ khác nhau: chốt kia để không nhấp nháy tin trạng thái trước mặt
        # người ngoài, chốt này để một kênh tương lai quên nối chốt kia vẫn không lọt.
        if not _nen_tra_loi(cfg, meta or {}):
            return {"text": "", "files": [], "im_lang": True}
        chat_id = str((meta or {}).get("chat_id") or "")
        user_id = str((meta or {}).get("user_id") or "")
        # Chế độ Tự đánh giá: tin nhóm KHÔNG ai gọi bot. Đánh giá TRƯỚC mọi thứ tốn kém hoặc có
        # tác dụng phụ (hạn mức tần suất, ghi Hộp thư, lượt model): tin bị loại không được đụng
        # vào bộ đếm nào, và tin trò chuyện của người ta không được thành một dòng nhật ký.
        tu_dong = chatbot_tu_dong.can_danh_gia(cfg, meta or {})
        tl = None
        rp_on = tu_dong and chatbot_reply_policy.normalize_config(cfg.get("reply_policy"))["mode"] == "on"
        rp_dec = None
        if rp_on:
            # Bộ phán xử (0.65.0) thay cửa từ khoá: nó tự tra tài liệu, kiểm hạn mức và hỏi model. Mọi kết
            # quả, kể cả im, đều đã được ghi vào kho quyết định.
            try:
                profile = _rp_profile(cfg, meta)
                ev = _rp_event(cfg, profile, text, meta or {})
                if not (meta or {}).get("_rp_observed"):
                    chatbot_reply_policy.observe(ev, profile, chatbot_reply_policy_store, ev.ts)
                # Rào cứng chạy TRƯỚC mọi lượt tốn model (đặc tả 5.1): chủ đã Tiếp quản cuộc chat thì bot im, tin khách
                # vẫn vào Hộp thư cho người trực đọc.
                aid_p, kenh_p = _tai_khoan_cua(cfg, meta or {})
                if conversations.che_do(kenh_p, aid_p, chat_id) == "human":
                    ghi_tin_khach(cfg, meta or {}, text)
                    chatbot_reply_policy.log_rail(chatbot_reply_policy_store, ev, profile, "taken_over")
                    return {"text": "", "files": [], "im_lang": True}
                dec = await chatbot_reply_policy.decide(
                    ev, profile, store=chatbot_reply_policy_store, ask=chatbot_reply_policy.ask_fn(),
                    doc_search=lambda t: _tra_tai_lieu(bot_id, cfg, t),
                    rate_check=lambda fu: _rp_rate(bot_id, chat_id, user_id, fu))
            except Exception as e:      # noqa: BLE001 - hỏng thì IM, không tự mở miệng
                print(f"[reply_policy {bot_id}] {type(e).__name__}: {e}", file=sys.stderr)
                return {"text": "", "files": [], "im_lang": True}
            if dec.verdict != "reply":
                return {"text": "", "files": [], "im_lang": True}
            rp_dec = dec
            tl = dec.doc or await _tra_tai_lieu(bot_id, cfg, text)
        elif tu_dong:
            if not chatbot_tu_dong.nhin_nhu_cau_hoi(text)[0]:
                return {"text": "", "files": [], "im_lang": True}
            tl = await _tra_tai_lieu(bot_id, cfg, text)
            ma = "" if tl.get("co") else "khong_co_tai_lieu"
            ma = ma or chatbot_tu_dong.duoc_tra_loi(bot_id, chat_id, user_id)
            if ma:
                _ghi_bo_qua(bot_id, cfg, meta, text, ma, tl)
                return {"text": "", "files": [], "im_lang": True}
        if _qua_han_muc(bot_id, chat_id, cfg.get("rate_limit")):
            if tu_dong:
                # Tin tự trả lời mà quá hạn mức thì im, KHÔNG nói "nhắn hơi nhanh" trước cả nhóm:
                # người ta đâu có gọi bot.
                _ghi_bo_qua(bot_id, cfg, meta, text, "het_han_muc", tl)
                _rp_retract(rp_dec, "rate_limited")
                return {"text": "", "files": [], "im_lang": True}
            return {"text": "Anh chị nhắn hơi nhanh, em xin phép trả lời lại sau ít phút ạ.",
                    "files": []}
        # Hộp thư hội thoại: ghi tin khách TRƯỚC khi gọi engine, để lượt gãy vẫn còn tin khách.
        ghi_tin_khach(cfg, meta or {}, text)
        # Người thật đã TIẾP QUẢN cuộc chat này ở trang Hội thoại thì bot im: tin khách vẫn vào
        # kho (dòng trên), chỉ không gọi engine. Lượt đang chạy dở lúc bấm Tiếp quản vẫn trả
        # lời nốt - chấp nhận ở V1, vì cắt ngang một câu đang gửi còn khó hiểu hơn với khách.
        aid_luot, kenh_luot = _tai_khoan_cua(cfg, meta or {})
        if conversations.che_do(kenh_luot, aid_luot, chat_id) == "human":
            _rp_retract(rp_dec, "taken_over")
            return {"text": "", "files": [], "im_lang": True}

        # Tra tài liệu TRƯỚC rồi nhét vào prompt, thay vì trông vào việc model tự chịu mở file.
        # Lượt Tự đánh giá đã tra ở trên rồi, dùng lại kết quả đó chứ không quét đĩa lần hai.
        if tl is None:
            tl = await _tra_tai_lieu(bot_id, cfg, text)
        cfg["_tai_lieu"] = tl
        cfg["_kenh_luot"] = kenh_luot
        cfg["_tu_dong"] = tu_dong
        # Trong nhóm Zalo cá nhân cả nhóm dùng CHUNG một mạch hội thoại (khoá theo nhóm), nên
        # model phải biết ai đang nói. Telegram giữ nguyên như cũ.
        text_engine = text
        if kenh_luot == "zalo_personal" and (meta or {}).get("chat_type") == "group":
            ten_nguoi = str((meta or {}).get("user_name") or "").strip()
            if ten_nguoi:
                text_engine = f"[{ten_nguoi}] {text}"

        # Bản ghi truyền xuống lõi phải có brain và slug - lõi dựa vào đó để đổi brain, đổi
        # khoá phiên và đổi nhãn kênh.
        try:
            out = await _deps["answer"](text_engine, meta, progress, channel=kenh_luot, bot=cfg)
        except Exception as e:
            print(f"[chatbot {bot_id}] {type(e).__name__}: {e}", file=sys.stderr)
            xin_loi = "Em đang gặp trục trặc, anh chị nhắn lại giúp em sau ít phút ạ."
            ghi_tin_bot(cfg, meta or {}, xin_loi, loi=f"{type(e).__name__}: {e}")
            return {"text": xin_loi, "files": []}
        run = _RUNNING.get(bot_id)
        if run:
            run["answered"] = run.get("answered", 0) + 1
            run["last_at"] = time.time()
        # Lõi trả CHUỖI khi là thông báo lỗi. Không dội câu lỗi kỹ thuật vào mặt người ngoài,
        # nhưng phải GIỮ LẠI cho chủ - bản trước ném thẳng nó đi, nên khi bot hỏng thì cả khách
        # lẫn chủ đều chỉ thấy đúng một câu "em chưa trả lời được câu này" và không ai biết vì
        # sao. Chủ repo dính đúng ca đó: bot im vì một lý do có thật và ghi rõ, mà câu ghi rõ ấy
        # bị nuốt mất trước khi tới nơi nào đọc được.
        loi_ky_thuat = ""
        if isinstance(out, str):
            loi_ky_thuat = out.strip()
            print(f"[chatbot {bot_id}] lượt hỏng: {loi_ky_thuat[:300]}", file=sys.stderr)
            out = {"text": "Em đang gặp trục trặc kỹ thuật, anh chị nhắn lại giúp em sau ít phút ạ.",
                   "files": []}

        dap = (out or {}).get("text") or ""
        # Bot TỰ QUYẾT im lặng (được dạy ở Zalo cá nhân và ở lượt Tự đánh giá, xem _CAU_ZALO_CA_NHAN
        # và _CAU_NHOM_TU_DONG). Đây không phải lượt "bí" và cũng không phải lượt lỗi: bot hiểu
        # tin nhắn và chọn không nhân danh chủ trả lời. Ghi vào nhật ký để chủ soi lại được, nhưng
        # không gửi gì, không vào Hộp thư như một câu bot nói, không tính vào bộ đếm bí/gọi người.
        if not loi_ky_thuat and IM_LANG.lower() in dap.lower():
            _rp_retract(rp_dec, "agent_silent")
            _BI_LIEN_TIEP[(bot_id, chat_id)] = 0
            chatbot_log.ghi(bot_id, {
                "chat_id": chat_id, "chat_type": (meta or {}).get("chat_type"),
                "user_name": (meta or {}).get("user_name"), "hoi": text,
                "dap": "(bot chọn không trả lời)", "loi": "", "bo_qua": "bot_tu_im",
                "co_tai_lieu": bool(tl.get("co")), "nguon": tl.get("nguon"),
                "chuyen_nguoi": False, "bi": False,
                "muc_quyen": cfg.get("muc_quyen") or "suggest",
            })
            return {"text": "", "files": [], "im_lang": True}
        # Chỉ lượt bot THẬT SỰ nói mới tốn hạn mức tự trả lời: lượt viết [IM_LANG] ở trên đã
        # return, và lượt gãy không phải một câu trả lời.
        if tu_dong and not loi_ky_thuat and dap.strip():
            chatbot_tu_dong.ghi_da_tra_loi(bot_id, chat_id, user_id)
        # "Bí" đo bằng chính CÂU BOT VỪA NÓI, không bằng việc có tìm ra tài liệu hay không.
        #
        # Ở chế độ theo Agent thì không có tài liệu là chuyện thường - bot vẫn trả lời tốt bằng
        # chuyên môn của vai. Lấy "không tìm ra tài liệu" làm dấu hiệu bí như bản 0.20.0 thì
        # mọi lượt tư vấn đều bị đếm là bí, và danh sách "Bot bí" đầy rác đúng chỗ nó phải sạch.
        # Lượt gãy cũng là "bot không trả lời được", nên tính là bí để bộ đếm gọi người thấy nó.
        # Nhưng nó KHÔNG phải lỗ hổng tài liệu - `chatbot_log.lo_hong` lọc bỏ lượt có `loi`,
        # nếu không thì tab "Bot bí" đầy dòng lỗi kỹ thuật đúng chỗ chỉ nên có câu khách hỏi.
        bi = bool(loi_ky_thuat) or _co_bi(dap) or (
            cfg.get("nguon_tra_loi") == "tai_lieu" and not tl.get("co"))

        khoa = (bot_id, chat_id)
        lien_tiep = (_BI_LIEN_TIEP.get(khoa, 0) + 1) if bi else 0
        _BI_LIEN_TIEP[khoa] = lien_tiep

        # Lượt GÃY khác hẳn lượt bí: bí là thiếu tài liệu, gãy là bot không chạy được. Gãy thì
        # báo NGAY từ lần đầu, đừng bắt chờ đủ hai câu - mỗi phút im lặng là khách nghĩ cửa
        # hàng bỏ mặc họ. Nhưng chỉ báo MỘT lần cho tới khi có lượt chạy được: engine hỏng thì
        # mọi lượt sau đều gãy, báo hết là biến hộp thư nhân viên thành log lỗi.
        if loi_ky_thuat:
            bao_lan_dau = bot_id not in _DA_BAO_LOI
            _DA_BAO_LOI.add(bot_id)
        else:
            bao_lan_dau = False
            _DA_BAO_LOI.discard(bot_id)

        # Lượt Tự đánh giá thì "bí" KHÔNG gọi người: tin đó đâu ai nhờ bot, đánh thức nhân viên
        # vì một câu người ta hỏi nhau trong nhóm là cách nhanh nhất để họ tắt thông báo.
        goi_nguoi = bool(cfg.get("handoff_to")) and (
            bao_lan_dau or (not loi_ky_thuat and not tu_dong and lien_tiep >= BI_LIEN_TIEP_DE_GOI))

        chatbot_log.ghi(bot_id, {
            "chat_id": chat_id, "chat_type": (meta or {}).get("chat_type"),
            "user_name": (meta or {}).get("user_name"),
            "hoi": text, "dap": dap, "loi": loi_ky_thuat,
            "co_tai_lieu": bool(tl.get("co")), "nguon": tl.get("nguon"),
            "chuyen_nguoi": goi_nguoi, "bi": bi,
            "muc_quyen": cfg.get("muc_quyen") or "suggest",
            # Lượt CHẠY ĐƯỢC nhưng không đúng như chủ đặt (vd mức Được ghi mà engine không gọi
            # nổi công cụ). Cố ý KHÔNG nhét vào `loi`: `loi` kéo theo `bi`, kéo theo gọi người
            # trực, và làm bẩn tab "Bot bí" - trong khi đây là lượt trả lời bình thường. Chủ
            # cần biết, người đang hỏi thì không cần.
            "canh_bao": (out or {}).get("canh_bao") or "",
        })
        # Câu bot nói (kể cả câu xin lỗi khi gãy) vào Hộp thư hội thoại, cạnh tin khách.
        ghi_tin_bot(cfg, meta or {}, dap, loi=loi_ky_thuat, files=(out or {}).get("files"))
        if goi_nguoi:
            _BI_LIEN_TIEP[khoa] = 0     # đã gọi người rồi thì đếm lại, đừng gọi mỗi lượt sau đó
            # Lượt HỎNG thì báo nguyên văn lý do kỹ thuật, không báo "bí N câu": chủ cần biết
            # bot đang gãy chứ không phải đang thiếu tài liệu. Hai chuyện đó sửa khác nhau hoàn toàn.
            asyncio.ensure_future(_gui_nhan_vien(
                cfg, str(cfg["handoff_to"]), chat_id,
                (f"Bot đang LỖI: {loi_ky_thuat[:300]}" if loi_ky_thuat else
                 f"Bí {lien_tiep} câu liên tiếp. Câu gần nhất: {str(text)[:200]}")))
        return out
    return _answer


def _inbox_dir(bot_cfg: dict):
    def _fn(chat):
        root = _deps["brain_root"](bot_cfg["brain"])
        return str(Path(root) / "inbox" / "khach")
    return _fn


# ============================================================
# Vòng đời
# ============================================================
def _gan_tai_khoan(fn, account_id: str, vi_tri_meta: int):
    """Bọc một callback của poller để MỌI meta mang `account_id`: kho hội thoại khoá tài
    khoản theo đó, và một bot trực hai tài khoản phải ghi tin về đúng tài khoản nhận."""
    if fn is None:
        return None
    import inspect

    def _them(args, kwargs):
        args = list(args)
        if "meta" in kwargs:
            kwargs["meta"] = dict(kwargs.get("meta") or {}, account_id=account_id)
        elif len(args) > vi_tri_meta:
            args[vi_tri_meta] = dict(args[vi_tri_meta] or {}, account_id=account_id)
        else:
            kwargs["meta"] = {"account_id": account_id}
        return args, kwargs

    if inspect.iscoroutinefunction(fn):
        async def _boc(*args, **kwargs):
            args, kwargs = _them(args, kwargs)
            return await fn(*args, **kwargs)
    else:
        def _boc(*args, **kwargs):
            args, kwargs = _them(args, kwargs)
            return fn(*args, **kwargs)
    return _boc


def start_bot(bot_id: str) -> tuple[bool, str]:
    """Bật một bot: MỖI tài khoản kênh của nó một poller. Đã chạy thì khởi động LẠI."""
    cfg = chatbot_store.get_bot(bot_id)
    if not cfg:
        return False, "Không có bot nào id đó"
    if not _deps.get("answer"):
        return False, "Bộ giám sát chưa được nối vào server"
    ds = chatbot_store.tokens(bot_id)
    nhan_kenh = chatbot_store.KENH_NHAN.get(str(cfg.get("channel") or ""), str(cfg.get("channel") or ""))
    if not any(tok for _, tok in ds):
        return False, f"Chưa có token {nhan_kenh} cho bot này"
    stop_bot(bot_id)      # huỷ TRƯỚC khi tạo: hai poller cùng token thì máy chủ trả 409 và cả hai chết
    pollers = {}
    loi = []
    for tk, token in ds:
        if not token:
            continue
        kenh = str(tk.get("channel") or "")
        Lop = _lop_kenh(kenh)
        if not Lop:
            loi.append(f"Kênh '{kenh}' chưa có lớp vận chuyển nào")
            continue
        aid = tk["id"]
        chung = dict(
            download_dir=_inbox_dir(cfg),
            commands=LENH_KHACH,      # menu của khách, KHÔNG phải menu quản trị của chủ
            precheck_fn=_gan_tai_khoan(_make_precheck_fn(bot_id), aid, 1),
            event_fn=_make_event_fn(bot_id),         # vào nhóm / bị đá / nhóm đổi id khi nâng cấp
            # Bot này nói chuyện với KHÁCH, nên không được để lộ một dòng trạng thái nào của Javis.
            giau_trang_thai=True,
        )
        if kenh == "telegram":
            chung["callback_fn"] = None
        if kenh == "zalo_personal":
            # Lớp vận chuyển Zalo cần đọc cấu hình bot SỐNG (chế độ trả lời trong nhóm) để biết có
            # nên chờ nhường trước khi trả lời tin không ai gọi tên. Đọc lại mỗi lần chứ không giữ
            # bản chụp: chủ đổi chế độ ở trang Chatbot là có tác dụng ngay.
            chung["cfg_fn"] = (lambda _b=bot_id: chatbot_store.get_bot(_b) or {})
            chung["policy"] = PolicyHooks(bot_id)      # bộ phán xử hội thoại nhóm (0.65.0)
        tb = Lop(
            token,
            "",                       # KHÔNG whitelist: bot khách hàng vốn để người lạ nhắn.
            _gan_tai_khoan(_make_answer_fn(bot_id), aid, 1),
            _gan_tai_khoan(_make_command_fn(cfg), aid, 3),
            **chung,
        )
        tb.account_id = aid
        tb.start()
        pollers[aid] = tb
    if not pollers:
        return False, "; ".join(loi) or f"Chưa có token {nhan_kenh} cho bot này"
    _RUNNING[bot_id] = {"pollers": pollers, "cfg": cfg, "started": time.time(), "answered": 0}
    return True, ("; ".join(loi) if loi else "")


def stop_bot(bot_id: str) -> bool:
    run = _RUNNING.pop(bot_id, None)
    if not run:
        return False
    for tb in (run.get("pollers") or {}).values():
        try:
            tb.stop()
        except Exception as e:
            print(f"[chatbot stop {bot_id}] {e}", file=sys.stderr)
    return True


def _trang_thai_poller(tb) -> dict:
    song = bool(tb._task and not tb._task.done())
    tt = getattr(tb, "status", "off")
    state = ("error" if tt in ("error", "conflict") else
             "running" if (song and tt == "polling") else
             "starting" if song else "error")
    return {
        "account_id": getattr(tb, "account_id", ""),
        "running": song, "state": state, "raw": tt,
        "last_error": getattr(tb, "last_error", "") or "",
        # Chế độ riêng tư của Telegram, hỏi getMe lúc khởi động. Chỉ có nghĩa khi bot đã biết
        # danh tính của nó; trước đó nó là False vì CHƯA HỎI ĐƯỢC, không phải vì đã tắt riêng tư.
        "doc_moi_tin_nhom": bool(getattr(tb, "doc_moi_tin_nhom", False)),
        "da_hoi_telegram": bool(getattr(tb, "bot_id", 0)),
        # getMe hỏng: bot vẫn trả lời tin nhắn riêng nhưng ĐIẾC trong mọi nhóm. Dòng riêng vì
        # vòng lặp xoá `last_error` sau mỗi lượt poll thành công.
        "loi_danh_tinh": getattr(tb, "loi_danh_tinh", "") or "",
        "loi_menu_lenh": getattr(tb, "loi_menu_lenh", "") or "",
    }


_THU_TU_XAU = {"error": 3, "starting": 2, "running": 1, "off": 0}


def status(bot_id: str) -> dict:
    """Trạng thái THẬT của một bot, cho thẻ trên trang Chatbot.

    Bốn trạng thái chứ không phải hai: bot chết âm thầm (token bị thu hồi, mạng rớt) là thứ
    chủ chỉ phát hiện khi khách phàn nàn, nên `lỗi` phải là một trạng thái hiện ra được.
    Nhiều tài khoản thì trạng thái chung là trạng thái XẤU NHẤT (một tài khoản lỗi = thẻ đỏ),
    và từng tài khoản nằm trong `accounts` để thẻ chỉ đúng cái nào hỏng.
    """
    run = _RUNNING.get(bot_id)
    if not run:
        return {"running": False, "state": "off", "last_error": "", "answered": 0, "accounts": []}
    ds = [_trang_thai_poller(tb) for tb in (run.get("pollers") or {}).values()]
    if not ds:
        return {"running": False, "state": "off", "last_error": "", "answered": 0, "accounts": []}
    xau = max(ds, key=lambda x: _THU_TU_XAU.get(x["state"], 0))
    out = dict(ds[0])
    out.update({
        "running": any(x["running"] for x in ds),
        "state": xau["state"], "raw": xau["raw"],
        "last_error": xau["last_error"] or next((x["last_error"] for x in ds if x["last_error"]), ""),
        "loi_danh_tinh": next((x["loi_danh_tinh"] for x in ds if x["loi_danh_tinh"]), ""),
        "loi_menu_lenh": next((x["loi_menu_lenh"] for x in ds if x["loi_menu_lenh"]), ""),
        "answered": run.get("answered", 0),
        "started_at": run.get("started"),
        "last_at": run.get("last_at"),
        "accounts": ds,
    })
    out.pop("account_id", None)
    return out


def sync_all() -> dict:
    """Khớp thực tế với cấu hình: bật cái nào đang bật, tắt cái nào không còn.

    Gọi lúc khởi động server và sau mỗi lần sửa cấu hình. Ý tưởng giống `restart_telegram`
    nhưng cho nhiều bot.
    """
    muon = {b["id"]: b for b in chatbot_store.enabled_bots()}
    for bid in list(_RUNNING):
        if bid not in muon:
            stop_bot(bid)
    ok, loi = 0, {}
    for bid in muon:
        if bid in _RUNNING and any(tb._task and not tb._task.done()
                                   for tb in _RUNNING[bid].get("pollers", {}).values()):
            ok += 1
            continue
        thanh, err = start_bot(bid)
        if thanh:
            ok += 1
        else:
            loi[bid] = err
    return {"running": ok, "errors": loi}


def quen_bot(bot_id: str) -> None:
    """Dọn mọi vết trong RAM của một bot vừa bị XOÁ.

    Cố ý tách khỏi `stop_bot`: tắt rồi bật lại (đổi token, sửa cấu hình) không được làm mất
    hàng đợi nhóm chờ duyệt - chủ vừa nhìn thấy một nhóm ở đó thì nó phải còn ở đó.
    """
    stop_bot(bot_id)
    _NHOM_CHO.pop(bot_id, None)
    _DA_BAO_LOI.discard(bot_id)
    for k in [x for x in _DA_BAO_NHOM if x and x[0] == bot_id]:
        _DA_BAO_NHOM.discard(k)
    for kho in (_HITS, _BI_LIEN_TIEP):
        for k in [x for x in kho if x and x[0] == bot_id]:
            kho.pop(k, None)


def stop_all() -> None:
    for bid in list(_RUNNING):
        stop_bot(bid)
