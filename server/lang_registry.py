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
        stopwords=(
            "the", "and", "of", "is", "are", "not", "for", "with", "this", "that",
            "you", "your", "have", "can", "please", "what", "how", "why", "when", "i",
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
