"""Bộ não GIỌNG NÓI riêng (Voice V2, docs/dev/2026-09-voice-v2-spec.md mục 2).

Khi người dùng NÓI với Javis, lượt đi qua một bộ não nhanh và nhẹ ở đây thay vì bộ não chính
(vốn dựng tiến trình, nạp MCP và prompt dài, mất 5-10 giây mới ra chữ đầu). Bộ não giọng trả
lời ngắn, và khi câu hỏi cần dữ liệu, tool, file, ký ức hay hành động thì nó trả đúng một dòng
`JAVIS_ASK_MAIN: <yêu cầu>`; main.py đọc dòng đó rồi chạy lượt bộ não chính như thường.

Hai loại bộ não:
  - AntigravityVoiceBrain: MỘT tiến trình `agy --input-format stream-json` sống suốt phiên
    nói. Đo 2026-09-14: lượt đầu 4,2 s (khởi động), lượt sau 1,3-2,0 s, stream từng mảnh
    chữ qua `step_update.text_delta`. Chạy trên gói Google đã có, không cần API key.
  - ApiVoiceBrain: Groq / Gemini / OpenAI / OpenRouter qua các hàm stream sẵn có trong
    engine.py, dùng key ở trang Models.

Sổ phiên: mỗi phiên chat web một bộ não, đóng sau IDLE_S giây không nói. Không import main.
"""
from __future__ import annotations

import asyncio
import difflib
import json
import os
import re
import sys
import time
from typing import AsyncIterator, Callable, Dict, List, Optional

import winproc         # lệnh con câm lặng trên Windows (canary test_windows_no_console)
import nghe_sua

MARKER = "JAVIS_ASK_MAIN:"
# Đường TẮT cho việc chỉ đụng tới giao diện: bộ não giọng tự phát, server gọi thẳng dashboard,
# không phải đánh thức bộ não chính (xem parse_ui).
UI_MARKER = "JAVIS_UI:"
UI_ACTIONS = ("open_page", "open_group", "sidebar", "scroll")
# Dòng ĐẦU của mọi câu trả lời: câu người dùng đã DIỄN GIẢI (máy nghe chép sai từ tiếng Anh,
# bộ não giọng viết lại đúng ý). Server bóc dòng này ra: thay tin người dùng trong kho phiên
# và trong khung chat, không bao giờ đọc ra loa (xem parse_nghe, split_speakable).
NGHE_MARKER = "JAVIS_NGHE:"
# CỬA TẠP ÂM: mic bật liên tục nên tiếng TV, người khác trong phòng hay tiếng lẩm bẩm cũng
# được chép thành chữ rồi chốt thành một lượt. Bộ não giọng đã đọc mọi lượt để viết dòng
# JAVIS_NGHE, nên nó xét luôn: cắt phần tạp âm ngay trong dòng ấy, còn cả lượt không có gì
# nói với Javis thì trả đúng một dòng này. Server bỏ lượt, không đọc loa, không để lại bong
# bóng (xem run_voice_turn trong main.py).
BO_QUA_MARKER = "JAVIS_BO_QUA:"
# Mọi dòng lệnh: không bao giờ ra loa (split_speakable), luôn bị bóc khỏi câu trả lời.
MARKERS = (MARKER, UI_MARKER, NGHE_MARKER, BO_QUA_MARKER)
IDLE_S = 300.0
TURN_TIMEOUT_S = 90.0
HISTORY_N = 10
# Danh sách các ô CHỌN của thẻ "Chế độ và bộ não giọng nói". Đây là NGUỒN DUY NHẤT: trang Cài
# đặt (GET /voice/options) vẽ từ đây, và đường lưu (POST /settings) cũng nhận đúng những giá trị
# này. Hai nơi giữ hai danh sách riêng là cách sinh ra lỗi "bấm Lưu thấy xong, F5 là mất".
MODES = ("standard", "fast", "live")

# key_field rỗng = chạy trên gói người dùng đã đăng nhập, không cần API key.
BRAIN_PROVIDERS = {
    "": {"label": "Bộ não chính (như gõ chữ)", "key_field": "", "default_model": ""},
    "antigravity": {"label": "Antigravity CLI (gói Google)", "key_field": "", "default_model": ""},
    # Ba bộ não chạy trên GÓI đã đăng nhập ở trang Models (Voice V3, spec mục 13): lớp giọng chỉ
    # cần một model trả lời ngắn và nhanh, nên bộ não nào cũng cắm được.
    "codex": {"label": "ChatGPT (gói ChatGPT, qua Codex)", "key_field": "", "default_model": ""},
    "claude": {"label": "Claude Code (gói Claude)", "key_field": "", "default_model": "haiku"},
    "grok": {"label": "Grok Build (gói SuperGrok / X Premium+)", "key_field": "", "default_model": ""},
    "groq": {"label": "Groq (API)", "key_field": "groq_api_key", "default_model": "llama-3.3-70b-versatile"},
    "gemini": {"label": "Google Gemini (API)", "key_field": "gemini_api_key", "default_model": "gemini-2.5-flash"},
    "openai": {"label": "OpenAI (API)", "key_field": "openai_api_key", "default_model": "gpt-4o-mini"},
    "openrouter": {"label": "OpenRouter", "key_field": "openrouter_key", "default_model": "google/gemini-2.5-flash"},
}

STT_PROVIDERS = {
    "browser": {"label": "Trình duyệt (Web Speech, miễn phí)", "key_field": ""},
    "groq": {"label": "Groq Whisper (chính xác hơn)", "key_field": "groq_api_key"},
}

# Bộ não chạy bằng API key (antigravity chạy bằng gói nên không nằm trong đây).
PROVIDERS = tuple(k for k, p in BRAIN_PROVIDERS.items() if p["key_field"])

SYSTEM_PROMPT = (
    "Bạn là Javis, trợ lý cá nhân, đang NÓI CHUYỆN BẰNG GIỌNG với người dùng. Trả lời như người "
    "đang nói: ngắn (1 đến 3 câu), tự nhiên, không markdown, không gạch đầu dòng, không emoji, "
    "không dấu gạch dài. Mặc định trả lời bằng tiếng Việt. Chỉ đổi ngôn ngữ khi người dùng nói "
    "rõ một câu có nghĩa bằng ngôn ngữ khác hoặc yêu cầu đổi; câu chép âm thanh pha tiếng lạ "
    "vô nghĩa thì xin nhắc lại bằng tiếng Việt. XƯNG HÔ theo đúng cách "
    "người dùng đang xưng hô với bạn (họ xưng thế nào thì đáp lại cho khớp), không tự đổi sang cách "
    "khác.\n"
    "Bạn KHÔNG có tool và KHÔNG biết dữ liệu sống. Khi câu hỏi cần bất kỳ thứ nào sau đây: số liệu "
    "kinh doanh, lịch, email, file hay ghi chú trong brain, ký ức dài hạn, giao việc, nhắc hẹn, mở "
    "trang hay mở app, gửi tin, hay bất cứ hành động nào ra ngoài, thì KHÔNG đoán và KHÔNG bịa. Thay "
    "vào đó trả lời đúng khuôn này: MỘT câu xác nhận ngắn, tự nhiên ở dòng đầu (kiểu 'Ừ, để xem "
    "ngay.', 'Rồi, kiểm tra ngay đây.', xưng hô theo người dùng), rồi một dòng riêng bắt đầu bằng "
    + MARKER + " theo sau là "
    "yêu cầu ĐẦY ĐỦ, tự đứng được (bộ não chính không nghe cuộc nói chuyện này) để bộ não chính của "
    "Javis thực hiện. Không viết gì sau dòng đó. Việc đó chạy NỀN như một việc riêng: kết quả tự "
    "hiện trong khung chat khi xong, còn bạn vẫn trò chuyện tiếp bình thường; có thể giao nhiều việc "
    "nền liên tiếp. Người dùng hỏi tiến độ thì nói việc đang chạy, KHÔNG bịa kết quả.\n"
    "NGOẠI LỆ, làm NGAY không nhờ bộ não chính: khi người dùng chỉ bảo ĐIỀU KHIỂN MÀN HÌNH, hãy "
    "trả lời một câu ngắn xác nhận rồi xuống dòng ghi " + UI_MARKER + " kèm lệnh:\n"
    "  " + UI_MARKER + " open_page <id trang>   (mở một tab. Viết ID tiếng Anh; trong ngoặc là nhãn "
    "người dùng nhìn thấy và hay đọc lên: home (Javis), chat (trò chuyện), files (tệp tin), "
    "learn (tự học), terminal, workspace (cộng sự, trợ lý, quy trình), chatbots (chatbot), "
    "skills (kỹ năng), plugins (công cụ), kanban (việc), selfimprove (việc định kỳ), "
    "mcp (kết nối), packs (Javis Store), channels (kênh), models, usage (mức dùng), "
    "settings (cài đặt), pet (linh vật), logs (cập nhật), account (tài khoản))\n"
    "  " + UI_MARKER + " open_group <id nhóm>   (BUNG một mục đang gập trên thanh bên mà không đổi "
    "trang: bo_nao (Bộ não), code (Code), nang_luc (Năng lực), viec (Việc), "
    "ket_noi (Kết nối), he_thong (Hệ thống))\n"
    "  " + UI_MARKER + " sidebar open | close    (bung hay thu gọn cả thanh bên)\n"
    "  " + UI_MARKER + " scroll top | bottom     (cuộn THỨ NGƯỜI DÙNG ĐANG XEM: có trang nội dung mở thì cuộn trang đó, không thì cuộn khung chat. Chỉ khi họ nói RÕ mới đổi thành "
    "page_top | page_bottom (ép cuộn trang) hay chat_top | chat_bottom (ép cuộn khung chat))\n"
    "Chỉ dùng khuôn này cho việc thuần giao diện. Muốn biết NỘI DUNG bên trong trang thì vẫn phải "
    "nhờ bộ não chính.\n"
    "NGOẠI LỆ THỨ HAI, tuyệt đối: khi người dùng bảo DỪNG hay HUỶ việc nền đang chạy (dừng việc "
    "ngầm, tạm dừng tìm kiếm ngầm, huỷ tác vụ...), TUYỆT ĐỐI KHÔNG giao việc mới. Giao việc để đi "
    "dừng một việc khác là đẻ thêm đúng thứ họ đang muốn bỏ. Chỉ trả lời một câu ngắn xác nhận, "
    "không kèm dòng lệnh nào; hệ thống đã tự huỷ trước khi bạn kịp nói.\n"
    "Chuyện trò thường, hỏi ý kiến, giải thích khái niệm, tính nhẩm, chuyển ngữ: trả lời thẳng.\n"
    "Câu của người dùng đến từ MÁY NGHE GIỌNG NÓI, và họ hay nói lẫn tiếng Việt với tiếng "
    "Anh, nên từ hay bị chép thành từ GẦN ÂM: tên bạn (Javis) thành 'David', 'Jarvis', 'Gia "
    "vít'; từ tiếng Anh, tên công cụ, tên dự án, tên sản phẩm thành một từ nghe na ná. Hãy "
    "HIỂU CÂU THEO NGỮ CẢNH cuộc trò chuyện. DÒNG ĐẦU TIÊN luôn là " + NGHE_MARKER + " rồi "
    "câu người dùng ĐÚNG NHƯ HỌ ĐỊNH NÓI trên một dòng, bỏ khối ngữ cảnh giao diện nếu có: "
    "chép lại nguyên văn, CHỈ thay từ nghe sai bằng từ gần âm đúng với ngữ cảnh (từ tiếng Anh "
    "viết đúng chính tả tiếng Anh); giữ nguyên tiếng Việt, xưng hô, thứ tự, số, từ phủ định; "
    "không dịch, không tóm tắt, không thêm bớt ý; không chắc thì chép y nguyên. Hệ thống tự "
    "kiểm lại dòng này, sửa quá tay thì bị bỏ. Từ dòng thứ hai mới trả lời hoặc dùng "
    + MARKER + " hay " + UI_MARKER + ", và trả lời theo câu đã hiểu đó: không bám nghĩa đen "
    "của từ nghe sai, không nói người dùng đã nói 'David', không bình luận về từ nghe sai. "
    "Câu vẫn không rõ nghĩa thì hỏi lại ngắn bằng tiếng Việt, không tự đoán tên người khác hay đổi "
    "giọng đọc. Người dùng nói dùng 'vâng' thay 'ừ' là yêu cầu cách đáp lễ phép; không suy "
    "thành đổi danh tính sang người tên Vân. Ưu tiên xưng em, gọi người dùng là anh và đáp vâng.\n"
    "Bạn chỉ có bản chép chữ, không có bằng chứng ai nói hay tiếng nào là tạp âm. "
    "Không đoán tiếng TV, không cắt hoặc bỏ lượt vì câu ngắn, đổi chủ đề hay lẫn ngôn ngữ. "
    "Giữ nguyên lời đã nhận; thiếu ý thì hỏi lại ngắn bằng tiếng Việt."
)

# Luôn gửi cả với bộ não đang sống dùng prompt cũ: không cho nó xoá lời đã được nhận.
GHI_CHU_TAT_LOC = (
    "[GHI CHÚ HỆ THỐNG: lượt này đã được nhận vào hội thoại. Chép ĐỦ câu họ nói ở dòng "
    + NGHE_MARKER + " (chỉ được thay từ nghe nhầm gần âm), không cắt bỏ phần nào, không suy "
    "đoán tạp âm từ chữ và không dùng "
    + BO_QUA_MARKER + ".]"
)

_MARK_RE = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"[ \t]*(.+?)[ \t]*$", re.M)
_NGHE_RE = re.compile(r"^[ \t]*" + re.escape(NGHE_MARKER) + r"[ \t]*(.*?)[ \t]*(?:\n|$)", re.M)
_TRANSCRIPT_WORDS = re.compile(r"[+−-]?\d+(?:[.,:/-]\d+)*%?|[^\W\d_]+(?:['’][^\W\d_]+)?", re.U)


# Rào cho câu bộ não giọng diễn giải (0.64.38). Đo trên cặp thật: "mô đồ"/Models 0,6,
# "web kếch"/Webcake 0,77, "com pô si ô"/Composio 1,0 (4 tiếng); còn cặp đổi nghĩa như
# "trả lời"/"trở thành" 0,4, "khách"/"sếp" 0,33, "email"/"Zalo" 0,25. Từ ngắn trùng hẳn âm
# ("vâng"/"Vân") vẫn bị chặn bởi nghe_sua.KHOA_MIN_MO. Không đoán được thì bộ não chính nhận
# nguyên văn và tự hiểu theo ngữ cảnh.
NGUONG_DIEN_GIAI = 0.6
MAX_GHEP_DIEN_GIAI = 4


def safe_transcript_rewrite(original: str, proposed: str) -> str:
    """Accept local spelling repairs, retaining the source on semantic or lossy edits.

    This is deliberately conservative: a model cannot establish which audio was noise
    from text alone. Whole-turn noise handling is separate. The UI prefix is context,
    not speech, and always belongs to the original message.
    """
    original = str(original or "")
    prefix, speech = nghe_sua.split_ui_context(original)
    candidate_prefix, candidate = nghe_sua.split_ui_context(str(proposed or "").strip())
    if candidate_prefix and candidate_prefix.strip() != prefix.strip():
        return original
    if not candidate or any(marker in candidate for marker in MARKERS):
        return original
    # Literal paths, email addresses, numeric separators and identifiers are not names
    # inferred from audio. Keep them exact, including punctuation.
    if nghe_sua.VERBATIM.findall(speech) != nghe_sua.VERBATIM.findall(candidate):
        return original
    before_raw = _TRANSCRIPT_WORDS.findall(speech)
    after_raw = _TRANSCRIPT_WORDS.findall(candidate)
    before = [w.casefold() for w in before_raw]
    after = [w.casefold() for w in after_raw]
    if not before or not after:
        return original
    changed = 0
    for kind, i, j, k, l in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if kind == "equal":
            continue
        # No dropped/added words, even when the remaining transcript is still long.
        if kind != "replace" or max(j - i, l - k) > MAX_GHEP_DIEN_GIAI:
            return original
        old, new = before[i:j], after[k:l]
        if "".join(old) == "".join(new):
            # Allow compound proper names (Open Router -> OpenRouter), not merged
            # command/negation words. Lowercase brand repairs still use explicit hotwords.
            proper_name = (all(re.fullmatch(r"[A-Z][a-zA-Z]*", w) for w in before_raw[i:j])
                           and all(re.fullmatch(r"[A-Z][a-z]+[A-Z][a-zA-Z]*", w) for w in after_raw[k:l]))
            if proper_name or not any(w in nghe_sua.PROTECTED_WORDS for w in old + new):
                continue
        if any(w in nghe_sua.PROTECTED_WORDS or any(c.isdigit() for c in w) for w in old + new):
            return original
        a, b = nghe_sua.khoa_am("".join(old)), nghe_sua.khoa_am("".join(new))
        if min(len(a), len(b)) < nghe_sua.KHOA_MIN_MO or nghe_sua.do_giong(a, b) < NGUONG_DIEN_GIAI:
            return original
        changed += max(len(old), len(new))
    if changed > max(2, len(before) // 3):
        return original
    return prefix + candidate


def parse_nghe(text: str):
    """(phần còn lại, câu đã diễn giải | None) cho dòng `JAVIS_NGHE:` (dòng ĐẦU TIÊN chỉ được
    tìm ở bất kỳ đâu vì model nhỏ có khi đặt nó sau câu xác nhận). Bóc cả dòng khỏi phần còn
    lại, kể cả dấu xuống dòng của nó. Câu diễn giải rỗng thì coi như không có."""
    t = str(text or "")
    m = _NGHE_RE.search(t)
    if not m:
        return t, None
    rest = t[:m.start()] + t[m.end():]
    nghe = m.group(1).strip()
    return rest, (nghe or None)


_BO_QUA_RE = re.compile(r"^[ \t]*" + re.escape(BO_QUA_MARKER) + r"[ \t]*(.*?)[ \t]*$", re.M)


def parse_bo_qua(text: str):
    """Lý do bỏ lượt (chuỗi, có thể rỗng) nếu bộ não giọng ra dòng `JAVIS_BO_QUA:`, không thì None.

    Tìm ở BẤT KỲ đâu chứ không chỉ dòng đầu: model nhỏ có khi viết dòng JAVIS_NGHE trước rồi mới
    chốt bỏ. Lý do rỗng vẫn là bỏ - dòng lệnh có mặt đã là quyết định, lý do chỉ để ghi log.

    Không trả phần còn lại như parse_nghe/parse_marker: lượt bị bỏ thì cả câu trả lời bị vứt,
    không có gì để đọc ra loa hay lưu vào phiên.
    """
    m = _BO_QUA_RE.search(str(text or ""))
    return None if not m else m.group(1).strip()


def tach_nghe_dau(text: str):
    """Như parse_nghe nhưng CHỈ xét dòng đầu tiên đã khép (có xuống dòng), dùng giữa lúc stream:
    gọi khi text vừa có dấu xuống dòng đầu tiên. Dòng đầu không phải marker thì trả y nguyên."""
    t = str(text or "")
    nl = t.find("\n")
    if nl < 0:
        return t, None
    dau = t[:nl]
    if not dau.lstrip().startswith(NGHE_MARKER):
        return t, None
    nghe = dau.lstrip()[len(NGHE_MARKER):].strip()
    return t[nl + 1:], (nghe or None)
_UI_RE = re.compile(r"^[ \t]*" + re.escape(UI_MARKER) + r"[ \t]*(.+?)[ \t]*$", re.M)


def parse_marker(text: str):
    """(câu chờ, yêu cầu cho bộ não chính | None). Bỏ dòng marker khỏi câu chờ."""
    t = str(text or "")
    m = _MARK_RE.search(t)
    if not m:
        return t.strip(), None
    filler = t[:m.start()].strip()
    return filler, m.group(1).strip()


def parse_ui(text: str):
    """(câu nói, (action, target) | None) cho dòng `JAVIS_UI:`.

    Vì sao có đường tắt này: mở một tab là việc KHÔNG cần dữ liệu gì. Trước đây nó vẫn phải đi
    `JAVIS_ASK_MAIN` sang bộ não chính, mà bộ não chính mang cả ngữ cảnh hội thoại (có lúc hơn
    200 nghìn token) nên một câu "mở trang Models" mất hàng chục giây. Bộ não giọng tự phát
    dòng này thì server gọi thẳng dashboard, còn đúng độ trễ của chính bộ não giọng.
    """
    t = str(text or "")
    m = _UI_RE.search(t)
    if not m:
        return t.strip(), None
    noi = (t[:m.start()] + t[m.end():]).strip()
    phan = m.group(1).strip().split(None, 1)
    action = phan[0].strip().lower()
    target = (phan[1].strip() if len(phan) > 1 else "")
    if action not in UI_ACTIONS:
        return t.strip(), None          # model bịa action lạ: coi như không có, đừng nuốt câu
    return noi, (action, target)


# Đoạn stream chưa có dấu kết câu mà dài quá mức này thì cắt ở dấu phẩy/khoảng trắng cuối,
# để một câu dài lê thê không giữ loa im mãi.
SPEAK_MAX = 220
_SENT_END = re.compile(r"[.!?…]+[\"'”’)\]]*(?=\s|$)")


def split_speakable(text: str, start: int, final: bool = False):
    """Cắt phần chữ từ `start` thành các mẩu ĐỌC ĐƯỢC cho loa; trả (mẩu, vị trí mới).

    Vì sao phải có hàm này (bài học 0.57.1): trước đây làn nhanh đẩy MỖI delta stream (vài từ)
    thành một khung cho trình duyệt, mà trình duyệt đọc mỗi khung là một yêu cầu TTS riêng ->
    hàng chục yêu cầu Edge, mỗi cái một độ trễ mạng, nghe giật và cà nhắc như cắt từng mẩu.
    Nay chỉ phát khi CÂU đã khép (dấu . ! ? … hoặc xuống dòng), hoặc khi đoạn dở dài quá
    SPEAK_MAX thì cắt ở dấu phẩy/khoảng trắng cuối; `final` thì đẩy nốt phần đuôi.

    Dòng marker `JAVIS_ASK_MAIN:` không bao giờ ra loa: dòng mới mà chữ đầu trùng đầu marker
    thì giữ lại tới khi biết chắc; đã là marker thì bỏ cả dòng.
    """
    out: List[str] = []
    while start < len(text):
        nl = text.find("\n", start)
        line_start = text.rfind("\n", 0, start) + 1
        if nl < 0:
            line = text[line_start:]
            if not final and any(mk.startswith(line.lstrip()) or line.lstrip().startswith(mk)
                                 for mk in MARKERS):
                break                          # chưa biết có phải marker: đợi thêm
            if line.lstrip().startswith(MARKERS):
                start = len(text)              # final: dòng marker, bỏ
                break
            partial = text[start:]
            if final:
                if partial.strip():
                    out.append(partial)
                start = len(text)
                break
            # Chưa xuống dòng: chỉ lấy tới dấu kết câu cuối cùng.
            last_end = -1
            for m in _SENT_END.finditer(partial):
                last_end = m.end()
            if last_end > 0:
                out.append(partial[:last_end])
                start += last_end
                continue
            if len(partial) >= SPEAK_MAX:
                cut = max(partial.rfind(",", 0, SPEAK_MAX), partial.rfind(" ", 0, SPEAK_MAX))
                if cut > 20:
                    out.append(partial[:cut + 1])
                    start += cut + 1
                    continue
            break                              # câu còn dở: đợi thêm chữ
        chunk = text[start:nl + 1]
        line = text[line_start:nl + 1]
        start = nl + 1
        if line.lstrip().startswith(MARKERS):
            continue
        if chunk.strip():
            out.append(chunk)
    return out, start


def seed_text(history: List[dict], text: str, with_prompt: bool = True) -> str:
    """Lượt ĐẦU của một tiến trình/mạch mới: hướng dẫn (nếu engine không nhận system prompt
    riêng) + mấy lượt gần nhất từ kho phiên + câu vừa nói. Dùng chung cho agy, Claude, Grok."""
    parts = []
    if with_prompt:
        parts.append("[HƯỚNG DẪN CHO LƯỢT NÓI CHUYỆN NÀY]\n" + SYSTEM_PROMPT)
    h = [x for x in (history or [])[-HISTORY_N:] if str(x.get("content") or "").strip()]
    if h:
        parts.append("[MẤY LƯỢT GẦN NHẤT TRONG PHIÊN NÀY]")
        for x in h:
            ai = "Javis" if x.get("role") == "assistant" else "Người dùng"
            parts.append(f"{ai}: {str(x.get('content'))[:1500]}")
    parts.append("[NGƯỜI DÙNG VỪA NÓI]\n" + str(text or ""))
    return "\n\n".join(parts)


def build_messages(history: List[dict], text: str, system: str = SYSTEM_PROMPT) -> List[dict]:
    msgs = [{"role": "system", "content": system}]
    for h in (history or [])[-HISTORY_N:]:
        role = "assistant" if h.get("role") == "assistant" else "user"
        c = str(h.get("content") or "").strip()
        if c:
            msgs.append({"role": role, "content": c[:2000]})
    msgs.append({"role": "user", "content": str(text or "")})
    return msgs


class VoiceBrain:
    provider = ""
    model = ""

    def __init__(self):
        self.last_used = time.time()
        self._lock = asyncio.Lock()

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:  # pragma: no cover
        raise NotImplementedError
        yield ""

    async def close(self) -> None:
        return None


class ApiVoiceBrain(VoiceBrain):
    """Groq / Gemini / OpenAI / OpenRouter qua engine.<prov>_stream."""

    def __init__(self, provider: str, api_key: str, model: str, stream_fn: Optional[Callable] = None):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self._stream_fn = stream_fn

    def _fn(self):
        if self._stream_fn:
            return self._stream_fn
        import engine
        return {
            "groq": engine.groq_stream, "gemini": engine.gemini_stream,
            "openai": engine.openai_stream, "openrouter": engine.openrouter_stream,
        }[self.provider]

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        msgs = build_messages(history, text)
        async with self._lock:
            async for ev in self._fn()(self.api_key, self.model, msgs, "off"):
                t = ev.get("type")
                if t == "text" and ev.get("content"):
                    yield ev["content"]
                elif t == "error":
                    raise RuntimeError(str(ev.get("content") or "lỗi provider"))


class AntigravityVoiceBrain(VoiceBrain):
    """Một tiến trình `agy` sống lâu, nhận từng lượt qua stdin NDJSON.

    Khuôn stdin dò ra 2026-09-14 (không có trong help): `{"event":"user","message":{"role":
    "user","content":"..."}}`. Tên sự kiện khác bị bỏ qua, `message` là chuỗi thì tiến trình
    THOÁT. Sự kiện ra: `init`, `step_update` (text_delta khi step_type=agent_response),
    `result` (status SUCCESS|ERROR, response, error).

    `agy` không có cờ system prompt, nên hướng dẫn được ghép vào ĐẦU lượt đầu tiên của mỗi
    tiến trình, kèm mấy lượt gần nhất từ kho phiên để mạch không đứt khi tiến trình mở lại.
    """
    provider = "antigravity"

    def __init__(self, model: str = "", cli_path: str = "", spawn: Optional[Callable] = None):
        super().__init__()
        self.model = model
        self.cli_path = cli_path
        self._spawn = spawn          # test tiêm tiến trình giả
        self.proc = None
        self._seeded = False
        self.turns = 0

    def _args(self) -> List[str]:
        args = [self.cli_path]
        if self.model:
            args += ["--model", self.model]
        args += ["--input-format", "stream-json", "--output-format", "stream-json"]
        return args

    async def _ensure(self):
        if self.proc is not None and self.proc.returncode is None:
            return
        if not self.cli_path and not self._spawn:
            raise RuntimeError("Chưa cài Antigravity CLI (agy).")
        if self._spawn:
            self.proc = await self._spawn(self._args())
        else:
            self.proc = await asyncio.create_subprocess_exec(
                *self._args(), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, **winproc.kwargs_no_window())
        self._seeded = False
        self.turns = 0

    def _seed_text(self, history: List[dict], text: str) -> str:
        return seed_text(history, text, with_prompt=True)

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        async with self._lock:
            await self._ensure()
            content = text if self._seeded else self._seed_text(history, text)
            self._seeded = True
            self.turns += 1
            line = json.dumps({"event": "user", "message": {"role": "user", "content": content}},
                              ensure_ascii=False) + "\n"
            self.proc.stdin.write(line.encode("utf-8"))
            await self.proc.stdin.drain()
            got_delta = False
            deadline = time.time() + TURN_TIMEOUT_S
            while True:
                left = deadline - time.time()
                if left <= 0:
                    await self.close()
                    raise RuntimeError("Antigravity không trả lời trong 90 giây.")
                try:
                    raw = await asyncio.wait_for(self.proc.stdout.readline(), timeout=left)
                except asyncio.TimeoutError:
                    await self.close()
                    raise RuntimeError("Antigravity không trả lời trong 90 giây.")
                if not raw:
                    await self.close()
                    raise RuntimeError("Antigravity đóng tiến trình giữa chừng.")
                try:
                    ev = json.loads(raw.decode("utf-8", "ignore"))
                except Exception:
                    continue
                kind = ev.get("event")
                if kind == "step_update":
                    su = ev.get("step_update") or {}
                    if su.get("step_type") == "agent_response" and su.get("text_delta"):
                        got_delta = True
                        yield str(su["text_delta"])
                elif kind == "result":
                    r = ev.get("result") or {}
                    if r.get("status") != "SUCCESS":
                        raise RuntimeError(str(r.get("error") or "Antigravity báo lỗi."))
                    if not got_delta and r.get("response"):
                        yield str(r["response"])
                    return

    async def close(self) -> None:
        p, self.proc = self.proc, None
        self._seeded = False
        if p is None:
            return
        try:
            if p.stdin:
                p.stdin.close()
        except Exception:
            pass
        try:
            if p.returncode is None:
                p.kill()
        except Exception:
            pass
        # Đợi tiến trình khép hẳn để transport asyncio đóng pipe ngay bây giờ, không phải lúc
        # event loop đã đóng (khi đó Windows ném "I/O operation on closed pipe" ra stderr).
        try:
            await asyncio.wait_for(p.wait(), timeout=3.0)
        except Exception:
            pass


# ============================================================
# Ba bộ não trên GÓI đã đăng nhập (Voice V3, spec mục 13)
# ============================================================
def _codex_creds():
    import openai_oauth
    return openai_oauth.valid_creds()


def codex_default_model() -> str:
    """Model Codex mặc định = đầu catalog 'openai-oauth' đã lấy live (main._codex_safe_model
    cũng làm vậy). Rỗng thì engine tự chọn mặc định của nó."""
    try:
        import config as cfgmod
        cat = (cfgmod.read_settings().get("model", {}).get("catalog", {}).get("openai-oauth")) or []
        return str(cat[0]) if cat else ""
    except Exception:
        return ""


class CodexVoiceBrain(VoiceBrain):
    """ChatGPT trên gói đã đăng nhập (OAuth), qua backend Codex Responses API: một HTTP stream
    mỗi lượt, không dựng tiến trình nào, nên đây là đường gói nhanh nhất. Cùng hàm
    `engine.openai_responses_stream` mà bộ não chính dùng; ở đây chỉ khác system prompt ngắn."""
    provider = "codex"

    def __init__(self, model: str = "", creds_fn: Optional[Callable] = None, stream_fn: Optional[Callable] = None):
        super().__init__()
        self.model = model
        self._creds_fn = creds_fn
        self._stream_fn = stream_fn

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        creds = (self._creds_fn or _codex_creds)() or {}
        if not creds.get("access_token"):
            raise RuntimeError("Chưa kết nối ChatGPT (OAuth) ở trang Models.")
        if self._stream_fn:
            fn = self._stream_fn
        else:
            import engine
            fn = engine.openai_responses_stream
        msgs = build_messages(history, text)
        async with self._lock:
            async for ev in fn(creds.get("access_token", ""), creds.get("account_id", ""),
                               self.model or codex_default_model(), msgs, "off"):
                t = ev.get("type")
                if t == "text" and ev.get("content"):
                    yield ev["content"]
                elif t == "limit_exceeded":
                    raise RuntimeError("ChatGPT hết hạn mức gói cho lượt này.")
                elif t == "error":
                    raise RuntimeError(str(ev.get("content") or "lỗi ChatGPT"))


def claude_pieces(msg):
    """Đổi một message của claude-agent-sdk thành [(loại, dữ liệu)]: ('delta', chữ) từ StreamEvent
    (include_partial_messages), ('text', chữ) từ AssistantMessage, ('result', msg) từ ResultMessage.
    Nhận diện bằng TÊN LỚP để test tiêm message giả không cần SDK."""
    name = type(msg).__name__
    out = []
    if name == "StreamEvent":
        ev = getattr(msg, "event", None) or {}
        if isinstance(ev, dict) and ev.get("type") == "content_block_delta":
            d = ev.get("delta") or {}
            if d.get("type") == "text_delta" and d.get("text"):
                out.append(("delta", str(d["text"])))
    elif name == "AssistantMessage":
        for b in (getattr(msg, "content", None) or []):
            if type(b).__name__ == "TextBlock" and (getattr(b, "text", "") or "").strip():
                out.append(("text", str(b.text)))
    elif name == "ResultMessage":
        out.append(("result", msg))
    return out


class ClaudeVoiceBrain(VoiceBrain):
    """Claude Code trên gói Claude: MỘT ClaudeSDKClient sống suốt phiên nói (như tiến trình agy),
    không tool, không MCP, không nạp settings hay CLAUDE.md, system prompt trần vài trăm token,
    nên lượt sau chỉ còn độ trễ của model. Mạch giữ trong client nên có ký ức giữa các lượt."""
    provider = "claude"

    def __init__(self, model: str = "", client_factory: Optional[Callable] = None):
        super().__init__()
        self.model = model
        self._factory = client_factory      # test tiêm client giả (async () -> client)
        self.client = None
        self._seeded = False
        self.turns = 0

    def _options(self):
        import tempfile
        from claude_agent_sdk import ClaudeAgentOptions
        fields = getattr(ClaudeAgentOptions, "__dataclass_fields__", {})
        kw = {"system_prompt": SYSTEM_PROMPT, "cwd": tempfile.gettempdir(),
              "permission_mode": "bypassPermissions"}
        if "tools" in fields:
            kw["tools"] = []                        # không tool builtin: bộ não giọng chỉ nói
        if "max_turns" in fields:
            kw["max_turns"] = 1
        if "setting_sources" in fields:
            kw["setting_sources"] = []              # không CLAUDE.md, không MCP máy: khởi động nhanh
        if "include_partial_messages" in fields:
            kw["include_partial_messages"] = True   # stream từng mảnh chữ cho loa
        if self.model and "model" in fields:
            kw["model"] = self.model
        try:
            import claude_cli
            _cli = (os.environ.get("JAVIS_CLAUDE_CLI") or "").strip() or (claude_cli.tim_binary("claude") or "")
            if _cli and "_bundled" not in _cli.replace("\\", "/") and "cli_path" in fields:
                kw["cli_path"] = _cli
        except Exception:
            pass
        try:
            import claude_auth
            _env = claude_auth.env_cho_cli()
            if _env and "env" in fields:
                kw["env"] = {**os.environ, **_env}
        except Exception:
            pass
        return ClaudeAgentOptions(**kw)

    async def _ensure(self):
        if self.client is not None:
            return
        if self._factory:
            self.client = await self._factory()
        else:
            import claude_cli
            import claude_sdk_engine
            if not claude_sdk_engine.sdk_available() or not claude_cli.find_claude_cli():
                raise RuntimeError("Chưa cài hoặc chưa đăng nhập Claude Code (claude).")
            from claude_agent_sdk import ClaudeSDKClient
            try:
                import claude_token_gate
                await claude_token_gate.xep_hang()
            except Exception:
                pass
            self.client = ClaudeSDKClient(options=self._options())
            await self.client.connect()
        self._seeded = False
        self.turns = 0

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        async with self._lock:
            await self._ensure()
            # System prompt đã đi bằng tuỳ chọn SDK nên lượt đầu chỉ mồi lịch sử.
            content = text if self._seeded else seed_text(history, text, with_prompt=False)
            self._seeded = True
            self.turns += 1
            got_delta = False
            deadline = time.time() + TURN_TIMEOUT_S
            try:
                await self.client.query(content)
                agen = self.client.receive_response().__aiter__()
                while True:
                    left = deadline - time.time()
                    if left <= 0:
                        raise asyncio.TimeoutError()
                    try:
                        msg = await asyncio.wait_for(agen.__anext__(), timeout=left)
                    except StopAsyncIteration:
                        return
                    for kind, data in claude_pieces(msg):
                        if kind == "delta":
                            got_delta = True
                            yield data
                        elif kind == "text":
                            if not got_delta:
                                yield data
                        elif kind == "result":
                            if getattr(data, "is_error", False):
                                raise RuntimeError(str(getattr(data, "result", "") or "Claude báo lỗi."))
                            return
            except asyncio.TimeoutError:
                await self.close()
                raise RuntimeError("Claude không trả lời trong 90 giây.")
            except RuntimeError:
                raise
            except Exception as e:
                await self.close()          # client hỏng: lần sau mở lại và mồi lại
                raise RuntimeError(f"Claude: {type(e).__name__}: {e}")

    async def close(self) -> None:
        c, self.client = self.client, None
        self._seeded = False
        if c is None:
            return
        try:
            await asyncio.wait_for(c.disconnect(), timeout=5.0)
        except Exception:
            pass


class GrokVoiceBrain(VoiceBrain):
    """Grok Build trên gói SuperGrok / X Premium+: một lượt `grok` headless mỗi câu, giữ cùng một
    GrokCLI để `--resume` mạch cũ (có ký ức). CLI gom chữ rồi trả `final` một cục nên không stream
    từng mảnh, nhưng câu trả lời giọng ngắn nên chấp nhận được."""
    provider = "grok"

    def __init__(self, model: str = "", cli_factory: Optional[Callable] = None):
        super().__init__()
        self.model = model
        self._factory = cli_factory
        self.cli = None

    def _ensure(self):
        if self.cli is not None:
            return
        if self._factory:
            self.cli = self._factory()
        else:
            import grok_cli
            if not grok_cli.find_grok_cli():
                raise RuntimeError("Chưa cài Grok Build (grok). Cài rồi đăng nhập ở trang Models.")
            import tempfile
            self.cli = grok_cli.GrokCLI(cwd=tempfile.gettempdir(), tag="voice", model=self.model or None,
                                        instructions=SYSTEM_PROMPT)
            self.cli.mode = "suggest"
            self.cli.max_turns = 1
            self.cli.timeout = TURN_TIMEOUT_S

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        async with self._lock:
            self._ensure()
            content = text if getattr(self.cli, "session_id", None) else seed_text(history, text, with_prompt=False)
            got = False
            async for ev in self.cli.query(content):
                t = ev.get("type")
                if t == "text" and ev.get("content"):
                    got = True
                    yield ev["content"]
                elif t == "final":
                    if not got and ev.get("content"):
                        yield str(ev["content"])
                elif t == "error":
                    raise RuntimeError(str(ev.get("content") or "Grok báo lỗi."))

    async def close(self) -> None:
        self.cli = None


# ============================================================
# Việc nền đang chạy của mỗi phiên nói (Voice V3, spec mục 14: tách NÓI khỏi LÀM)
# ============================================================
# Khi bộ não giọng phát JAVIS_ASK_MAIN, main.py giao yêu cầu đó cho bộ não chính chạy NỀN rồi
# kết thúc lượt giọng ngay, để người dùng nói tiếp được. Sổ này cho bộ não giọng biết còn việc
# gì đang chạy, để nó trả lời "đang chạy" thay vì bịa kết quả hay giao lại việc cũ.
_PENDING: Dict[str, List[dict]] = {}
PENDING_MAX_NOTE = 6


def note_task_start(session_id: str, request: str) -> int:
    lst = _PENDING.setdefault(str(session_id or "default"), [])
    lst.append({"request": str(request or "")[:300], "at": time.time()})
    return len(lst)


def note_task_done(session_id: str, request: str) -> None:
    lst = _PENDING.get(str(session_id or "default")) or []
    for i, it in enumerate(lst):
        if it["request"] == str(request or "")[:300]:
            lst.pop(i)
            break
    if not lst:
        _PENDING.pop(str(session_id or "default"), None)


def pending_tasks(session_id: str) -> List[dict]:
    return list(_PENDING.get(str(session_id or "default")) or [])


# ---- "Dừng việc nền đi" là LỆNH, không phải một việc mới ----
# Chủ dự án 15/09 gặp vòng lặp cười ra nước mắt: bảo "tạm dừng cái việc tìm kiếm ngầm đi nhé"
# thì Javis dạ vâng rồi GIAO THÊM một việc nền mới với nội dung "dừng việc nền đang chạy". Nói
# lần nữa lại đẻ thêm một việc nữa. Gốc ở chỗ luật của bộ não giọng bảo mọi thứ cần HÀNH ĐỘNG
# thì đẩy sang bộ não chính, mà "dừng việc" nghe đúng là một hành động.
#
# Chữa bằng luật CỨNG chứ không chỉ dặn model: nhận ra câu này thì huỷ ngay tại chỗ, không hỏi
# model, không giao việc. Vừa đúng, vừa trả lời tức thì.
#
# Ranh giới: phải có ĐỦ CẶP một từ DỪNG và một từ chỉ VIỆC ĐANG CHẠY NGẦM. Chỉ "dừng việc" thì
# không tính, vì "dừng việc nhập liệu lại" là chuyện khác hẳn.
_DUNG_TU = (
    "dừng", "tạm dừng", "ngừng", "huỷ", "hủy", "bỏ", "tắt", "thôi", "dẹp", "khoan làm",
    "stop", "cancel", "abort", "kill", "halt",
)
_VIEC_TU = (
    "việc nền", "viec nen", "việc ngầm", "viec ngam", "chạy nền", "chay nen", "chạy ngầm",
    "ngầm", "ngam", "nền", "nen", "tác vụ", "tac vu", "đang chạy", "dang chay",
    "background", "task", "job",
)


def la_lenh_dung_viec(text: str) -> bool:
    """Câu này có phải là LỆNH dừng việc nền đang chạy không (thuần, test được)."""
    s = " " + re.sub(r"\s+", " ", str(text or "").lower().strip()) + " "
    if not s.strip():
        return False
    co_dung = any((" " + t + " ") in s or s.startswith(" " + t + " ") for t in _DUNG_TU)
    if not co_dung:
        return False
    return any(v in s for v in _VIEC_TU)


def pending_note(session_id: str, now: Optional[float] = None) -> str:
    """Dòng ghi chú ghép vào cuối câu người dùng gửi bộ não giọng; rỗng khi không có việc nền."""
    lst = pending_tasks(session_id)
    if not lst:
        return ""
    now = now or time.time()
    dong = []
    for it in lst[-PENDING_MAX_NOTE:]:
        giay = int(max(0, now - it["at"]))
        dong.append(f"- {it['request']} (giao {giay} giây trước)")
    return ("[GHI CHÚ HỆ THỐNG: đang có việc chạy nền, kết quả sẽ TỰ hiện trong khung chat khi xong; "
            "đừng bịa kết quả, đừng giao lại việc trùng:\n" + "\n".join(dong) + "]")


# ============================================================
# Lỗi gần nhất của làn nhanh - để NÓI RA, không chỉ in stderr
# ============================================================
# Vì sao có (0.59.23): khi bộ não giọng hỏng (chưa cài CLI, hết key, hết hạn mức, mất mạng),
# run_voice_turn rơi về bộ não chính để lượt không câm. Đúng, nhưng trước đây cú rơi đó chỉ để
# lại một dòng stderr và một status bị dòng "Javis đang suy nghĩ..." của bộ não chính đè lên
# trong vài mili giây. Người dùng chỉ thấy: bật mic, nói, rồi chờ hàng chục giây như chưa từng
# có làn nhanh - và không có cách nào biết vì sao (chủ dự án gặp 16/09 sau vài bản cập nhật).
# Nên giữ lại lỗi gần nhất ở đây: khung chat nói ra ngay lượt đó, và thẻ Giọng nói ở trang
# Cài đặt hiện lại cho tới khi một lượt làn nhanh chạy trót lọt.
LOI_GAN_NHAT: Dict[str, object] = {}
_LOI_MAX_CHU = 300


def ten_bo_nao(provider: str) -> str:
    """Nhãn người dùng nhìn thấy ở thẻ cài đặt, để câu báo lỗi gọi đúng tên họ đã chọn."""
    p = BRAIN_PROVIDERS.get(str(provider or "").strip().lower())
    return (p or {}).get("label") or str(provider or "bộ não giọng")


def ghi_loi_lan_nhanh(provider: str, err, now: Optional[float] = None) -> dict:
    """Nhớ cú rơi về bộ não chính vừa xảy ra. Trả về bản ghi (để test và để gửi đi)."""
    LOI_GAN_NHAT.clear()
    LOI_GAN_NHAT.update({
        "provider": str(provider or ""),
        "label": ten_bo_nao(provider),
        "error": re.sub(r"\s+", " ", str(err or "").strip())[:_LOI_MAX_CHU],
        "at": float(now or time.time()),
    })
    return dict(LOI_GAN_NHAT)


def xoa_loi_lan_nhanh() -> None:
    """Một lượt làn nhanh vừa chạy trót lọt: lỗi cũ không còn đúng nữa, thôi khoe."""
    LOI_GAN_NHAT.clear()


def loi_lan_nhanh_gan_nhat() -> dict:
    return dict(LOI_GAN_NHAT)


def cau_roi_ve_bo_nao_chinh(provider: str, err) -> str:
    """Câu hiện TRONG KHUNG CHAT khi làn nhanh rơi về bộ não chính.

    Nói đủ ba ý, không dài hơn: rơi vì cái gì (tên bộ não giọng và lời báo lỗi thật), hệ quả là
    gì (lượt này chậm hơn vì đi bộ não chính), và sửa ở đâu (Cài đặt → Giọng nói). Không dùng
    gạch dài (luật của chủ dự án) và không đổ lỗi cho người dùng.
    """
    loi = re.sub(r"\s+", " ", str(err or "").strip())[:_LOI_MAX_CHU] or "không rõ lỗi"
    return (f"Làn nhanh không chạy được: bộ não giọng {ten_bo_nao(provider)} báo \"{loi}\". "
            f"Lượt này đi bộ não chính nên chậm hơn bình thường. "
            f"Kiểm tra bộ não giọng ở Cài đặt, mục Giọng nói, hoặc chọn bộ não khác ở đó.")


# ============================================================
# Sổ phiên
# ============================================================
_BRAINS: Dict[str, VoiceBrain] = {}
_REAPER: Optional[asyncio.Task] = None


def config_from_settings(cfg: dict) -> dict:
    v = (cfg or {}).get("voice") or {}
    m = (cfg or {}).get("model") or {}
    prov = str(v.get("brain_provider") or "").strip().lower()
    kf = (BRAIN_PROVIDERS.get(prov) or {}).get("key_field") or ""
    return {"mode": str(v.get("mode") or "standard"), "provider": prov,
            "model": str(v.get("brain_model") or "").strip(),
            "api_key": str(m.get(kf, "")) if kf else "",
            # Lọc tạp âm MẶC ĐỊNH BẬT: brain cũ chưa có khoá này trong settings.json vẫn được lọc,
            # nên phải hỏi `is False` chứ không phải `or True` (giá trị False hợp lệ).
            "loc_tap_am": False}


def _make(conf: dict) -> VoiceBrain:
    prov = conf.get("provider") or ""
    if prov == "antigravity":
        try:
            import antigravity_cli
            cli = antigravity_cli.find_antigravity_cli() or ""
        except Exception:
            cli = ""
        return AntigravityVoiceBrain(model=conf.get("model") or "", cli_path=cli)
    if prov == "codex":
        return CodexVoiceBrain(model=conf.get("model") or "")
    if prov == "claude":
        return ClaudeVoiceBrain(model=conf.get("model") or BRAIN_PROVIDERS["claude"]["default_model"])
    if prov == "grok":
        return GrokVoiceBrain(model=conf.get("model") or "")
    if prov in PROVIDERS:
        if not conf.get("api_key"):
            raise RuntimeError(f"Bộ não giọng nói {prov} chưa có API key ở trang Models.")
        return ApiVoiceBrain(prov, conf["api_key"], conf.get("model") or BRAIN_PROVIDERS[prov]["default_model"])
    raise RuntimeError("Chưa chọn bộ não giọng nói.")


async def get_brain(session_id: str, conf: dict) -> VoiceBrain:
    """Bộ não cho phiên này; đổi provider/model trong cài đặt thì dựng lại."""
    key = str(session_id or "default")
    b = _BRAINS.get(key)
    want = (conf.get("provider") or "", conf.get("model") or "")
    if b is not None and (b.provider, b.model) != want:
        await b.close()
        b = None
    if b is None:
        b = _make(conf)
        _BRAINS[key] = b
    _start_reaper()
    return b


def _start_reaper():
    global _REAPER
    if _REAPER is not None and not _REAPER.done():
        return
    try:
        _REAPER = asyncio.get_running_loop().create_task(_reap())
    except RuntimeError:
        pass


async def _reap():
    while True:
        await asyncio.sleep(30)
        now = time.time()
        for k, b in list(_BRAINS.items()):
            if now - b.last_used > IDLE_S:
                _BRAINS.pop(k, None)
                try:
                    await b.close()
                except Exception:
                    pass
        if not _BRAINS:
            return


async def close_all():
    for k, b in list(_BRAINS.items()):
        _BRAINS.pop(k, None)
        try:
            await b.close()
        except Exception:
            pass


def active_count() -> int:
    return len(_BRAINS)
