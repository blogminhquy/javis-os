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
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import chatbot_grounding
import chatbot_log
import chatbot_store
from telegram_bot import TelegramBot
from zalo_bot import ZaloBot

# Kênh -> lớp vận chuyển. Bảng này là NƠI DUY NHẤT biết kênh nào chạy bằng lớp nào; thêm kênh
# thứ ba sau này chỉ phải thêm một dòng ở đây và một giá trị vào `chatbot_store.KENH`.
_LOP_KENH = {"telegram": TelegramBot, "zalo": ZaloBot}

# Menu lệnh Telegram của bot khách. ĐÚNG bằng danh sách trắng trong `_make_command_fn`, không
# hơn. Menu là một mặt giao diện: liệt kê ở đó những lệnh bot từ chối chạy là dạy khách đi tìm
# một tập lệnh khác, còn liệt kê lệnh quản trị của bot chủ thì khai luôn là có tập lệnh đó.
LENH_KHACH = [
    {"command": "help", "description": "Bot này giúp được gì"},
    {"command": "nhanvien", "description": "Nhờ người thật hỗ trợ"},
    {"command": "id", "description": "Xem ID cuộc trò chuyện này"},
]

# bot_id -> {"bot": TelegramBot, "cfg": dict, "started": float, "answered": int, "day": str}
_RUNNING: Dict[str, dict] = {}
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
    if loai == "private":
        return ""
    nhom = [str(x) for x in (bot_cfg.get("groups") or [])]
    # Chưa khai nhóm nào thì bot không tự nhận việc trong nhóm lạ. Cùng một lý do với nhóm đã
    # khai nhưng không phải nhóm này, nên cùng một mã: cả hai đều sửa bằng cách cho phép nhóm.
    if not nhom or not _khop_nhom(nhom, (meta or {}).get("chat_id")):
        return "nhom_chua_bat"
    if bot_cfg.get("reply_when") == "always":
        return ""
    if (meta or {}).get("mentioned") or (meta or {}).get("reply_to_bot"):
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
    ds = _NHOM_CHO.setdefault(bot_id, {})
    cu = ds.get(cid)
    if cu:
        if dem:
            cu["lan"] = cu.get("lan", 0) + 1
            cu["ts"] = time.time()
        if cau:
            cu["cau"] = str(cau)[:200]
        if (meta or {}).get("chat_title"):
            cu["ten"] = str(meta["chat_title"])[:80]
        return
    if len(ds) >= MAX_NHOM_CHO:
        # Đầy thì bỏ mục CŨ NHẤT. Nhóm vừa có người gọi đáng nhìn hơn nhóm im từ tuần trước.
        cu_nhat = min(ds, key=lambda k: ds[k].get("ts", 0))
        ds.pop(cu_nhat, None)
    ds[cid] = {"chat_id": cid, "ten": str((meta or {}).get("chat_title") or "")[:80],
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
        ly_do = _ly_do_im(cfg, meta or {})
        if not ly_do:
            return None
        if ly_do != "nhom_chua_bat":
            return {}       # không ai gọi tên: im tuyệt đối, và không có gì để chủ duyệt
        # Nhóm chưa bật, nhưng lượt này có phải một lần GỌI BOT thật không? Hỏi lại chính luật
        # trên với giả định nhóm đã được bật: nếu vẫn im thì đây chỉ là hai người nói chuyện
        # với nhau, không có gì để chủ duyệt và tuyệt đối không được chen vào. Hỏi lại luật cũ
        # thay vì chép điều kiện ra đây: chép là có ngày hai chỗ nói khác nhau.
        gia_dinh = dict(cfg)
        gia_dinh["groups"] = [str((meta or {}).get("chat_id") or "")]
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
            if cfg and not _khop_nhom(cfg.get("groups") or [], cid):
                _ghi_nhom_cho(bot_id, {"chat_id": cid, "chat_title": (tt or {}).get("chat_title")},
                              dem=False)
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
    run = _RUNNING.get(bot_id or "")
    tb = run and run.get("bot")
    cfg = chatbot_store.get_bot(bot_id) or {}
    dong = [f"ID cuộc trò chuyện này: `{chat}`"]
    if str((meta or {}).get("chat_type") or "private") == "private":
        return dong[0]

    if not _khop_nhom(cfg.get("groups") or [], chat):
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
    run = _RUNNING.get(bot_cfg.get("id") or "")
    tb = run and run.get("bot")
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


def _make_answer_fn(bot_id: str):
    async def _answer(text, meta=None, progress=None):
        cfg = chatbot_store.get_bot(bot_id)
        if not cfg:
            return {"text": "", "files": [], "im_lang": True}
        # Lớp thứ HAI của cùng một luật (`precheck_fn` đã chặn ở tầng kênh). Giữ cả hai vì hai
        # cái canh hai thứ khác nhau: chốt kia để không nhấp nháy tin trạng thái trước mặt
        # người ngoài, chốt này để một kênh tương lai quên nối chốt kia vẫn không lọt.
        if not _nen_tra_loi(cfg, meta or {}):
            return {"text": "", "files": [], "im_lang": True}
        chat_id = str((meta or {}).get("chat_id") or "")
        if _qua_han_muc(bot_id, chat_id, cfg.get("rate_limit")):
            return {"text": "Anh chị nhắn hơi nhanh, em xin phép trả lời lại sau ít phút ạ.",
                    "files": []}

        # Tra tài liệu TRƯỚC rồi nhét vào prompt, thay vì trông vào việc model tự chịu mở file.
        # Quét đĩa + chấm điểm là việc CHẶN, đẩy sang thread để không chẹn event loop (poller
        # của các bot khác và của cả Javis đều chạy chung một loop).
        tl = {"co": False, "khoi": "", "nguon": []}
        try:
            root = _deps["brain_root"](cfg["brain"])
            tl = await asyncio.to_thread(chatbot_grounding.thu_thap, root, text)
        except Exception as e:
            print(f"[chatbot {bot_id}] tra tài liệu lỗi: {e}", file=sys.stderr)
        cfg["_tai_lieu"] = tl

        # Bản ghi truyền xuống lõi phải có brain và slug - lõi dựa vào đó để đổi brain, đổi
        # khoá phiên và đổi nhãn kênh.
        try:
            out = await _deps["answer"](text, meta, progress,
                                        channel=str(cfg.get("channel") or "telegram"), bot=cfg)
        except Exception as e:
            print(f"[chatbot {bot_id}] {type(e).__name__}: {e}", file=sys.stderr)
            return {"text": "Em đang gặp trục trặc, anh chị nhắn lại giúp em sau ít phút ạ.",
                    "files": []}
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

        goi_nguoi = bool(cfg.get("handoff_to")) and (
            bao_lan_dau or (not loi_ky_thuat and lien_tiep >= BI_LIEN_TIEP_DE_GOI))

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
def start_bot(bot_id: str) -> tuple[bool, str]:
    """Bật một bot. Đã chạy thì khởi động LẠI (dùng cho lúc đổi token)."""
    cfg = chatbot_store.get_bot(bot_id)
    if not cfg:
        return False, "Không có bot nào id đó"
    kenh = str(cfg.get("channel") or "telegram")
    nhan_kenh = chatbot_store.KENH_NHAN.get(kenh, kenh)
    token = chatbot_store.get_token(bot_id)
    if not token:
        return False, f"Chưa có token {nhan_kenh} cho bot này"
    if not _deps.get("answer"):
        return False, "Bộ giám sát chưa được nối vào server"
    stop_bot(bot_id)      # huỷ TRƯỚC khi tạo: hai poller cùng token thì máy chủ trả 409 và cả hai chết
    # Hai lớp vận chuyển giữ CHUNG một khế ước (xem đầu zalo_bot.py), nên chỗ này chỉ chọn
    # lớp rồi dựng y hệt. Khác biệt duy nhất: Zalo không có nút bấm nên không nhận callback_fn,
    # và cũng không đẩy được menu lệnh lên app.
    Lop = _LOP_KENH.get(kenh)
    if not Lop:
        return False, f"Kênh '{kenh}' chưa có lớp vận chuyển nào"
    chung = dict(
        download_dir=_inbox_dir(cfg),
        commands=LENH_KHACH,      # menu của khách, KHÔNG phải menu quản trị của chủ
        precheck_fn=_make_precheck_fn(bot_id),   # nhóm chưa được bật: im, nhưng KHÔNG im lặng
        event_fn=_make_event_fn(bot_id),         # vào nhóm / bị đá / nhóm đổi id khi nâng cấp
        # Bot này nói chuyện với KHÁCH, nên không được để lộ một dòng trạng thái nào của Javis.
        # Xem khối chú thích "nói như người thật" ở đầu telegram_bot.py.
        giau_trang_thai=True,
    )
    if kenh == "telegram":
        chung["callback_fn"] = None
    tb = Lop(
        token,
        "",                       # KHÔNG whitelist: bot khách hàng vốn để người lạ nhắn.
        _make_answer_fn(bot_id),  # rào nằm ở mức quyền và ở luật trả lời, không ở whitelist.
        _make_command_fn(cfg),
        **chung,
    )
    tb.start()
    _RUNNING[bot_id] = {"bot": tb, "cfg": cfg, "started": time.time(), "answered": 0}
    return True, ""


def stop_bot(bot_id: str) -> bool:
    run = _RUNNING.pop(bot_id, None)
    if not run:
        return False
    try:
        run["bot"].stop()
    except Exception as e:
        print(f"[chatbot stop {bot_id}] {e}", file=sys.stderr)
    return True


def status(bot_id: str) -> dict:
    """Trạng thái THẬT của một bot, cho thẻ trên trang Chatbot.

    Bốn trạng thái chứ không phải hai: bot chết âm thầm (token bị thu hồi, mạng rớt) là thứ
    chủ chỉ phát hiện khi khách phàn nàn, nên `lỗi` phải là một trạng thái hiện ra được.
    """
    run = _RUNNING.get(bot_id)
    if not run:
        return {"running": False, "state": "off", "last_error": "", "answered": 0}
    tb = run["bot"]
    song = bool(tb._task and not tb._task.done())
    tt = getattr(tb, "status", "off")
    state = ("error" if tt in ("error", "conflict") else
             "running" if (song and tt == "polling") else
             "starting" if song else "error")
    return {
        "running": song,
        "state": state,
        "raw": tt,
        "last_error": getattr(tb, "last_error", "") or "",
        "answered": run.get("answered", 0),
        "started_at": run.get("started"),
        "last_at": run.get("last_at"),
        # Chế độ riêng tư của Telegram, hỏi getMe lúc khởi động. Chỉ có nghĩa khi bot đã biết
        # danh tính của nó; trước đó nó là False vì CHƯA HỎI ĐƯỢC, không phải vì đã tắt riêng tư.
        "doc_moi_tin_nhom": bool(getattr(tb, "doc_moi_tin_nhom", False)),
        "da_hoi_telegram": bool(getattr(tb, "bot_id", 0)),
        # getMe hỏng: bot vẫn trả lời tin nhắn riêng nhưng ĐIẾC trong mọi nhóm. Phải là một
        # dòng riêng chứ không gộp vào `last_error` - vòng lặp xoá `last_error` sau mỗi lượt
        # poll thành công, và lượt nào cũng thành công nên nó không bao giờ hiện ra.
        "loi_danh_tinh": getattr(tb, "loi_danh_tinh", "") or "",
    }


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
        if bid in _RUNNING and _RUNNING[bid]["bot"]._task and not _RUNNING[bid]["bot"]._task.done():
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
