"""Sổ đăng ký ngôn ngữ - MỘT chỗ duy nhất biết mọi thứ về một ngôn ngữ.

Vì sao có file này. Trước nó, "tiếng Việt" nằm rải khắp mã dưới hàng chục hình dạng khác
nhau: `vi-VN` trong giọng đọc, `"vi"` trong Whisper, `_THU_VN` trong đồng hồ, `toLocaleString`
ở dashboard, và hàng chục mẫu regex ASCII trong các cổng chặn. Thêm một ngôn ngữ theo kiểu đó
là đi sửa hai chục chỗ, và quên một chỗ thì nó hỏng TRONG IM LẶNG.

**LUẬT CỦA FILE NÀY: không mã nào ngoài đây được viết `if lang == "vi"`.** Cần biết gì về một
ngôn ngữ thì hỏi sổ đăng ký. Có `tests/python/test_lang_registry_invariant.py` quét mã và báo
đỏ nếu luật này bị vi phạm - không có cái chốt đó thì tính mở rộng mục dần sau vài tháng.

Thêm ngôn ngữ thứ N+1 = thêm MỘT mục vào `LANGS` + một file `lexicon/<mã>.py` (tuỳ chọn) +
`dashboard/i18n/<mã>.json` (khi tới phần giao diện). Không sửa file nào khác.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


# Ngôn ngữ dùng khi không biết gì cả. Cố ý là tiếng Việt: đây là brain của người Việt, và
# rơi về tiếng Việt thì tệ nhất cũng chỉ là trả lời sai ngôn ngữ cho một người nước ngoài,
# còn rơi về tiếng Anh thì mọi người dùng hiện tại bị đổi ngôn ngữ trong im lặng.
MAC_DINH = "vi"


@dataclass(frozen=True)
class Lang:
    # --- định danh ---
    code: str                     # mã gọn, KHÔNG phải BCP-47 đầy đủ ("vi", không phải "vi-VN")
    native: str                   # tên ngôn ngữ viết bằng chính nó ("Tiếng Việt")
    english: str                  # tên tiếng Anh, để log và tài liệu
    script: str                   # "latin" | "hani" | "thai" | ...
    rtl: bool = False

    # --- dò ngôn ngữ ---
    # Hư từ để chấm điểm văn bản chữ Latin. Với tiếng Việt phải có CẢ dạng bỏ dấu, vì người
    # Việt gõ không dấu rất nhiều ("toi muon xem doanh thu").
    stopwords: Tuple[str, ...] = ()
    # Cách người dùng YÊU CẦU ngôn ngữ này, viết bằng bất kỳ tiếng nào. Dùng cho mức ưu tiên
    # cao nhất: câu lệnh thẳng trong lượt ("trả lời bằng tiếng Anh").
    request_words: Tuple[str, ...] = ()

    # --- giọng nói ---
    stt: str = ""                 # mã cho Whisper. "" = để Whisper tự dò.
    tts: Dict[str, str] = field(default_factory=dict)   # nhà cung cấp -> giọng

    # --- locale (tách khỏi ngôn ngữ, xem spec mục 4.6) ---
    tz_default: str = "UTC"
    currency: str = "USD"
    first_day: int = 0            # 0 = Chủ nhật, 1 = Thứ hai
    number_locale: str = "en-US"  # cho toLocaleString phía dashboard

    # --- ngữ pháp ---
    plural: bool = False          # có chia số nhiều không (tiếng Việt: không)

    # --- chữ để dựng prompt ---
    # Một câu viết bằng CHÍNH ngôn ngữ này. Model mạnh không cần, nhưng model nhỏ (Groq,
    # Ollama Cloud) trôi theo ngôn ngữ của prompt, và prompt của Javis là tiếng Việt.
    nudge: str = ""
    weekdays: Tuple[str, ...] = ()          # thứ 2 -> chủ nhật, đúng thứ tự datetime.weekday()
    clock_template: str = ""                # chỗ điền: {hm} {weekday} {date} {tz}
    lang_directive: str = ""                # câu nói rõ phải trả lời bằng ngôn ngữ nào


LANGS: Dict[str, Lang] = {
    "vi": Lang(
        code="vi",
        native="Tiếng Việt",
        english="Vietnamese",
        script="latin",
        stopwords=(
            # có dấu
            "và", "của", "là", "không", "được", "cho", "với", "này", "những", "các",
            "một", "có", "để", "thì", "đã", "sẽ", "anh", "em", "tôi", "mình",
            # không dấu - người Việt gõ kiểu này rất nhiều, thiếu là dò trượt
            "va", "cua", "la", "khong", "duoc", "cho", "voi", "nay", "nhung", "cac",
            "mot", "co", "de", "thi", "da", "se", "anh", "em", "toi", "minh",
            # Bổ sung sau khi ĐO: chỉ 13/17 câu tiếng Việt gõ thật dò ra được, và phần trượt
            # toàn là câu KHÔNG DẤU ngắn ("gui bao cao qua telegram", "kiem tra ton kho con
            # bao nhieu"). Nhóm này đưa lên 16/17, tiếng Anh không đổi, không câu Âu châu nào
            # bị nhận nhầm.
            #
            # CỐ Ý bỏ "sao"/"nào": không dấu thành "nao", trùng "não" tiếng Bồ Đào Nha gõ
            # thiếu dấu, và đo được "eu nao quero o relatorio agora" bị chấm thành tiếng Việt
            # vì đúng chữ đó. Cũng bỏ "cần"/"thế": không dấu thành "can"/"the", trùng đúng
            # hai hư từ tiếng Anh nên cộng điểm cho cả hai bên rồi hoà, mất luôn kết quả.
            "bị", "bi", "hôm", "hom", "qua", "còn", "con", "cũng", "cung", "rất", "rat",
            "đang", "dang", "phải", "phai", "muốn", "muon", "giúp", "giup", "khi",
            "nếu", "neu", "hoặc", "hoac", "mới", "moi", "luôn", "luon", "nữa", "nua",
            "rồi", "roi", "tại", "tai", "bởi", "boi",
        ),
        request_words=("tieng viet", "tiếng việt", "vietnamese", "viet ngu", "việt ngữ"),
        stt="vi",
        tts={
            "edge": "vi-VN-HoaiMyNeural",
            "openai": "alloy",
            "elevenlabs": "",          # rỗng = dùng giọng đa ngôn ngữ user đã chọn
        },
        tz_default="Asia/Ho_Chi_Minh",
        currency="VND",
        first_day=1,
        number_locale="vi-VN",
        plural=False,
        nudge="Trả lời bằng tiếng Việt.",
        # Viết hoa ĐÚNG như hằng `_THU_VN` cũ trong context_compiler: câu đồng hồ của tiếng
        # Việt phải ra y hệt từng ký tự so với trước khi có sổ đăng ký.
        weekdays=("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"),
        clock_template=(
            "Bây giờ là {hm} {weekday} ngày {date}, giờ {tz}. Đây là giờ THẬT tại thời điểm "
            "câu hỏi này được gửi: cứ dùng thẳng khi cần biết hôm nay/bây giờ, không phải đoán "
            "và không cần gọi tool."
        ),
        lang_directive="Tiếng Việt",
    ),
    "en": Lang(
        code="en",
        native="English",
        english="English",
        script="latin",
        # Danh sách này là BẰNG CHỨNG để `lang.detect` chấm điểm, nên nó phải phủ được câu
        # người ta gõ THẬT, không phải câu văn viết. Bản đầu chỉ có 20 chữ và thiếu đúng nhóm
        # hư từ hay gặp nhất trong câu lệnh ngắn (my, from, we, will, show, give...): đo trên
        # 18 câu hỏi kinh doanh tiếng Anh thường gặp thì chỉ nhận ra 5, tức người dùng tiếng
        # Anh gõ "show me my revenue" vẫn bị trả lời bằng tiếng Việt. Với danh sách này là
        # 17/18, và tiếng Việt không mất câu nào.
        #
        # CỐ Ý bỏ qua các chữ tiếng Anh trùng chữ tiếng Việt viết không dấu: to (to), so (số),
        # no (nó), do (đo), it (ít), me (mẹ), an (ăn), in (in), on (ơn), at (át), am (âm),
        # one (ơn). Thêm chúng là cộng điểm tiếng Anh cho câu tiếng Việt không dấu, mà câu
        # tiếng Việt không dấu NGẮN chỉ trúng một hư từ - đủ để hoà rồi mất luôn kết quả.
        #
        # Cũng CỐ Ý chỉ lấy HƯ TỪ, không lấy danh từ hay gặp (week, month, report, total...).
        # Danh từ đi xuyên ngôn ngữ: bản thử có "week" và "report" nên "ik wil het rapport van
        # deze week zien" (tiếng Hà Lan) bị chấm thành tiếng Anh.
        stopwords=(
            "the", "and", "of", "is", "are", "not", "for", "with", "this", "that",
            "you", "your", "have", "can", "please", "what", "how", "why", "when", "i",
            "my", "from", "about", "all", "any", "some", "more", "most", "than", "then",
            "there", "these", "those", "which", "who", "where", "but", "just", "only",
            "also", "get", "give", "show", "make", "need", "want", "was", "were", "been",
            "will", "would", "could", "should", "did", "does", "has", "had", "we", "us",
            "our", "they", "them", "their", "his", "her", "she",
            "each", "every", "other", "into", "over", "under", "between", "before",
            "after", "out", "here", "now",
        ),
        request_words=("english", "tieng anh", "tiếng anh", "in english", "anh ngu", "anh ngữ"),
        stt="en",
        tts={
            "edge": "en-US-AriaNeural",
            "openai": "alloy",
            "elevenlabs": "",
        },
        tz_default="UTC",
        currency="USD",
        first_day=0,
        number_locale="en-US",
        plural=True,
        nudge="Answer in English.",
        weekdays=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
        clock_template=(
            "It is now {hm} {weekday}, {date}, timezone {tz}. This is the REAL time at the "
            "moment this question was sent: use it directly whenever you need to know "
            "today/now, no guessing and no tool call needed."
        ),
        lang_directive="English",
    ),
}


def chuan_hoa(code: str) -> str:
    """"vi-VN" -> "vi", "EN_us" -> "en", rác -> "". KHÔNG tự rơi về mặc định ở đây.

    Cố ý trả "" thay vì `MAC_DINH` khi không nhận ra: nơi gọi cần phân biệt được "user chưa
    chọn gì" với "user chọn tiếng Việt", vì hai cái đó dẫn tới hai nhánh khác nhau ở
    `lang.resolve()`.
    """
    s = str(code or "").strip().lower().replace("_", "-")
    if not s:
        return ""
    goc = s.split("-")[0]
    return goc if goc in LANGS else ""


def get(code: str) -> Lang:
    """Luôn trả về một Lang dùng được, không bao giờ ném lỗi hay trả None.

    Prompt và giọng đọc là đường nóng của mọi lượt chat; một KeyError ở đây giết cả lượt trả
    lời chỉ vì ai đó lưu nhầm mã ngôn ngữ vào settings.
    """
    return LANGS.get(chuan_hoa(code) or MAC_DINH, LANGS[MAC_DINH])


def ma_list() -> Tuple[str, ...]:
    return tuple(LANGS.keys())


def duoc_ho_tro(code: str) -> bool:
    return bool(chuan_hoa(code))


def cho_giao_dien() -> list:
    """Danh sách cho ô chọn ngôn ngữ trên dashboard. Dashboard KHÔNG tự khai danh sách này,
    nếu không thì thêm ngôn ngữ lại phải sửa hai nơi."""
    return [{"ma": l.code, "ten": l.native, "ten_en": l.english} for l in LANGS.values()]


def giong_tts(code: str, provider: str) -> str:
    """Giọng đọc cho cặp (ngôn ngữ, nhà cung cấp). "" = nhà cung cấp tự lo.

    ElevenLabs trả "" có chủ ý: nó đang chạy `eleven_multilingual_v2`, một giọng đọc được
    mọi thứ tiếng, nên ép giọng theo ngôn ngữ ở đó là làm hỏng lựa chọn của user chứ không
    giúp được gì.
    """
    return get(code).tts.get(str(provider or ""), "")
