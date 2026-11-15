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

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple


# Ngôn ngữ dùng khi không biết gì cả. Cố ý là tiếng Việt: đây là brain của người Việt, và
# rơi về tiếng Việt thì tệ nhất cũng chỉ là trả lời sai ngôn ngữ cho một người nước ngoài,
# còn rơi về tiếng Anh thì mọi người dùng hiện tại bị đổi ngôn ngữ trong im lặng.
MAC_DINH = "vi"

# Ngôn ngữ CHỮ TRÊN MÀN HÌNH khi thiết bị chọn một thứ tiếng mà chuỗi đó chưa có bản dịch.
# Khác MAC_DINH có chủ ý (0.67.0): người đọc tiếng Nhật gặp một câu chưa dịch thì tiếng Anh còn
# đọc được, tiếng Việt thì không. MAC_DINH vẫn là tiếng Việt cho những chỗ KHÔNG có ai đang
# nhìn màn hình (Telegram, việc nền) - đổi nó là đổi ngôn ngữ của người dùng hiện tại.
DU_PHONG_GIAO_DIEN = "en"


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
    # Chỗ điền: {hm} {weekday} {date} {tz}, ĐÚNG bốn cái này. improvement_trial_dashboard dựng lại câu này với đúng bốn
    # trường và phải khớp từng ký tự với prompt thật, mà file đó bị ghim mã băm trong bằng chứng chạy thật, không sửa được.
    # Nên 0.443.0 nói "hôm qua, ngày mai tính từ {date}" bằng chữ chứ không thêm trường {yesterday}/{tomorrow}.
    clock_template: str = ""
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
            "Bây giờ là {hm} {weekday} ngày {date}, giờ {tz}. Đây là giờ THẬT lúc gửi câu "
            "hỏi: dùng thẳng cho hôm nay/bây giờ, không đoán, không cần gọi tool. Hôm qua, "
            "ngày mai và ngày gửi MCP khi kéo số liệu đều tính từ ngày này."
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
            "It is now {hm} {weekday}, {date}, timezone {tz}. This is the REAL time when "
            "this question was sent: use it directly for today/now, no guessing, no tool call "
            "needed. Yesterday, tomorrow and dates sent to an MCP for report numbers all "
            "count from this date."
        ),
        lang_directive="English",
    ),
}


# ---------------------------------------------------------------- reply languages (2026-11-15)
#
# Owner, 2026-11-15: "Javis must work and talk in ANY language, like Claude or ChatGPT", "let the
# model handle the language", and "the language setting only sets the interface". So nothing in
# Settings or on a bot names a reply language any more: the model answers in whatever language the
# person writes. This catalog serves the few places that still NAME a language for a reason: a voice
# call (the brain only sees the voice model's handoff, so it is told what the caller spoke), a direct
# "answer in Japanese" in the message, and the voice that reads the answer (`/tts/voices`).
#
# `LANGS` above is the heavy registry: a language there has an interface dictionary, safety-gate
# lexicon, clock sentence and weekday names. A REPLY language needs much less: a code, its names
# and one sentence in that language. So it gets its own light catalog, and adding one here costs
# nothing elsewhere. Every language of `LANGS` is a reply language too (`_REPLY` merges them).
#
# `nudge` is written in the language itself, like `Lang.nudge`: small models drift with the
# language of the prompt. Only languages whose sentence is certain are listed; any other language
# still works through "follow the person", it just cannot be pinned by name.


@dataclass(frozen=True)
class ReplyLang:
    code: str                       # "ja", "zh-tw": the key, lowercase
    english: str                    # "Japanese"
    native: str                     # "日本語", shown in pickers
    nudge: str                      # "日本語で答えてください。"
    edge: str = ""                  # Edge TTS locale prefix ("ja-JP"), for the voice list


_CATALOG: Tuple[ReplyLang, ...] = (
    ReplyLang("zh", "Chinese (Simplified)", "简体中文", "请用简体中文回答。", "zh-CN"),
    ReplyLang("zh-tw", "Chinese (Traditional)", "繁體中文", "請用繁體中文回答。", "zh-TW"),
    ReplyLang("ja", "Japanese", "日本語", "日本語で答えてください。", "ja-JP"),
    ReplyLang("ko", "Korean", "한국어", "한국어로 답해 주세요.", "ko-KR"),
    ReplyLang("th", "Thai", "ภาษาไทย", "กรุณาตอบเป็นภาษาไทย", "th-TH"),
    ReplyLang("id", "Indonesian", "Bahasa Indonesia", "Jawab dalam bahasa Indonesia.", "id-ID"),
    ReplyLang("ms", "Malay", "Bahasa Melayu", "Jawab dalam bahasa Melayu.", "ms-MY"),
    ReplyLang("tl", "Filipino", "Filipino", "Sumagot sa Filipino.", "fil-PH"),
    ReplyLang("km", "Khmer", "ភាសាខ្មែរ", "សូមឆ្លើយជាភាសាខ្មែរ។", "km-KH"),
    ReplyLang("lo", "Lao", "ພາສາລາວ", "ກະລຸນາຕອບເປັນພາສາລາວ", "lo-LA"),
    ReplyLang("hi", "Hindi", "हिन्दी", "कृपया हिन्दी में उत्तर दें।", "hi-IN"),
    ReplyLang("bn", "Bengali", "বাংলা", "বাংলায় উত্তর দিন।", "bn-BD"),
    ReplyLang("ar", "Arabic", "العربية", "يرجى الرد باللغة العربية.", "ar-SA"),
    ReplyLang("he", "Hebrew", "עברית", "ענה בעברית.", "he-IL"),
    ReplyLang("fa", "Persian", "فارسی", "لطفاً به فارسی پاسخ دهید.", "fa-IR"),
    ReplyLang("tr", "Turkish", "Türkçe", "Lütfen Türkçe cevap ver.", "tr-TR"),
    ReplyLang("ru", "Russian", "Русский", "Отвечай на русском языке.", "ru-RU"),
    ReplyLang("uk", "Ukrainian", "Українська", "Відповідай українською мовою.", "uk-UA"),
    ReplyLang("pl", "Polish", "Polski", "Odpowiadaj po polsku.", "pl-PL"),
    ReplyLang("cs", "Czech", "Čeština", "Odpovídej česky.", "cs-CZ"),
    ReplyLang("de", "German", "Deutsch", "Antworte auf Deutsch.", "de-DE"),
    ReplyLang("nl", "Dutch", "Nederlands", "Antwoord in het Nederlands.", "nl-NL"),
    ReplyLang("fr", "French", "Français", "Réponds en français.", "fr-FR"),
    ReplyLang("es", "Spanish", "Español", "Responde en español.", "es-ES"),
    ReplyLang("pt", "Portuguese", "Português", "Responda em português.", "pt-BR"),
    ReplyLang("it", "Italian", "Italiano", "Rispondi in italiano.", "it-IT"),
    ReplyLang("sv", "Swedish", "Svenska", "Svara på svenska.", "sv-SE"),
    ReplyLang("da", "Danish", "Dansk", "Svar på dansk.", "da-DK"),
    ReplyLang("no", "Norwegian", "Norsk", "Svar på norsk.", "nb-NO"),
    ReplyLang("fi", "Finnish", "Suomi", "Vastaa suomeksi.", "fi-FI"),
    ReplyLang("el", "Greek", "Ελληνικά", "Απάντησε στα ελληνικά.", "el-GR"),
    ReplyLang("hu", "Hungarian", "Magyar", "Válaszolj magyarul.", "hu-HU"),
    ReplyLang("ro", "Romanian", "Română", "Răspunde în limba română.", "ro-RO"),
)

# Codes people and browsers write for the same language.
_REPLY_ALIASES = {"zh-cn": "zh", "zh-hans": "zh", "zh-sg": "zh", "zh-hant": "zh-tw", "zh-hk": "zh-tw",
                  "zh-mo": "zh-tw", "fil": "tl", "nb": "no", "nn": "no", "iw": "he"}


def _reply_table() -> Dict[str, ReplyLang]:
    out: Dict[str, ReplyLang] = {}
    for l in LANGS.values():
        voice = l.tts.get("edge") or ""
        out[l.code] = ReplyLang(l.code, l.english, l.native, l.nudge,
                                "-".join(voice.split("-")[:2]) if voice else "")
    for r in _CATALOG:
        out.setdefault(r.code, r)
    return out


_REPLY: Dict[str, ReplyLang] = _reply_table()


def reply_code(code: str) -> str:
    """A reply-language code ("ja", "zh-tw") for any spelling ("ja-JP", "zh_Hant", "FIL"), "" when unknown.

    Wider than `chuan_hoa`, which only knows the languages with a full registry entry. Use this
    where a person NAMES the language Javis answers in; use `chuan_hoa` for the interface.
    """
    s = str(code or "").strip().lower().replace("_", "-")
    if not s:
        return ""
    if s in _REPLY:
        return s
    for k in (s, "-".join(s.split("-")[:2]), s.split("-")[0]):
        if k in _REPLY_ALIASES:
            return _REPLY_ALIASES[k]
        if k in _REPLY:
            return k
    return ""


def reply_info(code: str) -> ReplyLang:
    """Names and nudge of a reply language; unknown codes get the default language, never an error."""
    return _REPLY.get(reply_code(code)) or _REPLY[MAC_DINH]


def reply_codes() -> Tuple[str, ...]:
    return tuple(_REPLY.keys())


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
    ma = chuan_hoa(code)
    if not ma and reply_code(code):
        # A reply language without a full entry ("ja", "fr", 2026-11-15): its clock line, weekday names
        # and skill descriptions fall back to English, which its reader is far likelier to read than
        # Vietnamese. Before, a Japanese pin got a Vietnamese clock and a Vietnamese voice.
        ma = DU_PHONG_GIAO_DIEN
    return LANGS.get(ma or MAC_DINH, LANGS[MAC_DINH])


def chon_ban_dich(code: str, ban: dict) -> str:
    """Chọn bản chữ cho ngôn ngữ `code` từ `{"vi": ..., "en": ...}`.

    Thứ tự: đúng ngôn ngữ đó -> DU_PHONG_GIAO_DIEN -> MAC_DINH -> bản nào có chữ. Không bao giờ
    trả rỗng khi còn một bản có chữ: chữ sai ngôn ngữ vẫn hơn một ô trống trên màn hình.
    """
    for k in (chuan_hoa(code), DU_PHONG_GIAO_DIEN, MAC_DINH):
        v = ban.get(k) if k else None
        if v:
            return v
    return next((v for v in ban.values() if v), "")


def ma_list() -> Tuple[str, ...]:
    return tuple(LANGS.keys())


def duoc_ho_tro(code: str) -> bool:
    return bool(chuan_hoa(code))


def cho_giao_dien() -> list:
    """Danh sách cho ô chọn ngôn ngữ trên dashboard. Dashboard KHÔNG tự khai danh sách này,
    nếu không thì thêm ngôn ngữ lại phải sửa hai nơi."""
    return [{"ma": l.code, "ten": l.native, "ten_en": l.english} for l in LANGS.values()]


_DICT_NAME = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})?$")
_DICT_CACHE: dict = {}


def dashboard_only_languages(i18n_dir) -> list:
    """Dashboard dictionaries for languages this registry does NOT know (0.99.0).

    A community translation can be just `dashboard/i18n/<code>.json` (CONTRIBUTING.md,
    Translations item 2): the dashboard picks it up for that browser language, but the server,
    the voice and the prompts stay in vi/en. The language pickers still need to offer it, or a
    reader who switched to English could never switch back. Same shape as `cho_giao_dien`, plus
    `chi_giao_dien: True` so the dashboard stores English on the server for it. The name comes
    from the file's own `_meta.name`. Cached per file mtime: GET /settings calls this often.
    """
    out = []
    try:
        files = sorted(Path(i18n_dir).glob("*.json"))
    except OSError:
        return out
    for f in files:
        code = f.stem.lower()
        if code in LANGS or not _DICT_NAME.match(code):
            continue
        try:
            mtime = f.stat().st_mtime_ns
            hit = _DICT_CACHE.get(code)
            if not hit or hit[0] != mtime:
                data = json.loads(f.read_text(encoding="utf-8"))
                name = str((data or {}).get("_meta.name") or code) if isinstance(data, dict) else code
                _DICT_CACHE[code] = hit = (mtime, name[:40])
        except (OSError, ValueError):
            continue      # a broken file is not offered; the dashboard loader skips it too
        out.append({"ma": code, "ten": hit[1], "ten_en": hit[1], "chi_giao_dien": True})
    return out


def giong_tts(code: str, provider: str) -> str:
    """Giọng đọc cho cặp (ngôn ngữ, nhà cung cấp). "" = nhà cung cấp tự lo.

    ElevenLabs trả "" có chủ ý: giọng ElevenLabs là giọng user tự chọn, đọc được mọi thứ tiếng
    của model (Flash v2.5 từ 0.255.0, có tiếng Việt; xem tts_eleven.py), nên ép giọng theo ngôn
    ngữ ở đó là làm hỏng lựa chọn của user chứ không giúp được gì.
    """
    return get(code).tts.get(str(provider or ""), "")
