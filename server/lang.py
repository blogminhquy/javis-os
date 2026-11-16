"""Ngôn ngữ của một lượt chat: phần con người GHIM, và phần bộ dò phục vụ các cổng chặn.

AI QUYẾT ĐỊNH NGÔN NGỮ TRẢ LỜI. Từ 0.35.0 câu trả lời là: **model**, không phải file này.
Không ai ghim gì thì prompt bảo model "trả lời bằng đúng thứ tiếng người dùng vừa viết", và
thế là xong - nó bám đúng cho MỌI thứ tiếng.

Đây là một bước LÙI có chủ ý của module này, và lý do là số liệu đo được từ chính bản trước:

  - bộ dò tự chốt ngôn ngữ trả lời, và dò tiếng Anh trên câu hỏi thật chỉ đạt 16/18 - tức vẫn
    có câu người ta gõ tiếng Anh mà Javis đáp tiếng Việt;
  - người viết tiếng Thái, Nhật, Pháp, Tây Ban Nha thì LUÔN bị đáp tiếng Việt, kể cả khi bộ
    dò nhận ra đúng, vì các thứ tiếng đó không có trong sổ đăng ký nên rơi hết về mặc định.

Nói cách khác: mình đã tự dựng một bản kém hơn của thứ model vốn làm miễn phí. Nay `resolve()`
chỉ còn lo phần con người ghim (bot chuyên trách, lựa chọn ở Cài đặt, lệnh thẳng trong lượt),
và phần việc chạy nền - nơi không có lượt người dùng nào để mà bám.

BỘ DÒ VẪN CÒN, và vẫn cần, ở những chỗ KHÔNG CÓ MODEL trong vòng lặp:
  - cổng chặn đọc câu HỎI (chọn bộ từ vựng), chạy trước model;
  - cổng bắt khai man đọc câu TRẢ LỜI, chạy sau model;
  - giọng đọc TTS, chọn bằng mã ngôn ngữ trong code.

Ba biến ngôn ngữ tách rời (spec mục 4.1), đừng nhập một:
  ui_lang       chữ trên màn hình      - user chọn, lưu theo thiết bị
  reply_lang    Javis trả lời          - since 2026-11-15 NOT a setting: the model follows whoever writes
                                         (owner: "the language setting only sets the interface"). The
                                         key stays "auto" in settings.json, see main.migrate_reply_lang_to_profile
  content_lang  nội dung trong brain   - của user, Javis không đụng

Dò ngôn ngữ KHÔNG dùng thư viện ngoài. Chỉ cần phân biệt giữa các ngôn ngữ ĐÃ ĐĂNG KÝ, nên
hai tầng là đủ: nhận hệ chữ qua khoảng mã Unicode (xong ngay tiếng Nhật, Thái, Hàn, Ả Rập,
Nga), rồi chấm điểm hư từ cho các thứ tiếng chữ Latin. Cả hai tầng đều đọc dữ liệu từ
`lang_registry`, nên thêm ngôn ngữ vẫn là thêm DỮ LIỆU.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import lang_registry


# Văn bản ngắn hơn ngần này thì không đủ căn cứ để dò ("ok", "cảm ơn", "yes"). Trả về ngôn
# ngữ rỗng - nơi gọi PHẢI hiểu đó là "chưa biết", không phải "tiếng Việt".
DO_DAI_TOI_THIEU = 12


@dataclass(frozen=True)
class LangDecision:
    lang: str            # ngôn ngữ để NÊU TÊN khi cần nêu (đồng hồ, danh sách skill, giọng đọc)
    source: str          # turn | chatbot | setting | brain | channel | detect | ui | default
    confidence: float
    has_lexicon: bool    # có bộ từ vựng cho ngôn ngữ này không (xem server/lexicon/)
    detected: str = ""   # ngôn ngữ dò được từ lượt này, kể cả khi không được dùng
    # True = KHÔNG ai ghim gì, cứ để model bám theo thứ tiếng người dùng vừa viết.
    # False = có lựa chọn rõ ràng của con người (hoặc không có lượt người dùng nào để bám).
    theo_nguoi_dung: bool = False

    @property
    def lang_cau_hoi(self) -> str:
        """Ngôn ngữ của CÂU HỎI, dành cho các CỔNG CHẶN. Có thể là "" (chưa dò ra).

        KHÁC `self.lang`, và phân biệt được hai cái là chuyện sống còn:

      - `lang`        = Javis TRẢ LỜI bằng tiếng gì. Không bao giờ rỗng (rơi về mặc định).
      - `lang_cau_hoi` = người dùng đang VIẾT tiếng gì. Rỗng nghĩa là chưa biết.

        Cổng chặn đọc CÂU HỎI, nên nó phải dùng cái thứ hai. Đưa nhầm `lang` xuống cổng là
        đúng con bệnh đã đo được: user ghim trả lời tiếng Anh rồi hỏi tiếng Việt thì cổng
        chấm câu tiếng Việt bằng bộ từ vựng tiếng Anh, và ngược lại. Tệ hơn nữa, `lang`
        không bao giờ rỗng nên nhánh an toàn "chưa biết ngôn ngữ thì chạy DENY của mọi bộ
        từ vựng" thành mã chết - cổng luôn tưởng mình biết chắc.
        """
        # Chỉ có một câu trả lời đúng: thứ dò được từ CHÍNH lượt này. Không dò được (câu quá
        # ngắn: "ok thanks", "cho anh xem") thì trả rỗng, và cổng chặn phải suy biến an toàn.
        #
        # TUYỆT ĐỐI không mượn `self.lang` khi nó đến từ một cái GHIM: cái ghim nói Javis phải
        # TRẢ LỜI bằng tiếng gì, nó không nói gì về ngôn ngữ người dùng đang VIẾT. Mượn nhầm
        # là đúng con bệnh đã đo được - user ghim trả lời tiếng Anh rồi hỏi tiếng Việt thì
        # cổng đem bộ từ vựng tiếng Anh ra chấm một câu tiếng Việt.
        return self.detected

    @property
    def capsule_lang(self) -> str:
        """Language to NAME in a prompt that carries no full language block (a compiled capsule), "" = follow.

        Only a language a person pinned (Settings, a bot, a command in this message). Owner, 2026-11-15:
        "Claude and ChatGPT already follow the user's language, let the model handle it." The old code
        named a guess here, the interface language when nothing was detected, so a short English message
        ("ok do 2") on a Vietnamese interface was answered in Vietnamese.
        """
        return "" if self.theo_nguoi_dung else self.lang

    def as_trace(self) -> dict:
        return {"lang": self.lang, "lang_source": self.source,
                "lang_confidence": round(float(self.confidence), 3),
                "lang_has_lexicon": self.has_lexicon,
                "lang_detected": self.detected,
                # Đọc trace mà không có cờ này thì `lang` gây hiểu nhầm: nó là ngôn ngữ để
                # NÊU TÊN ở vài chỗ trong prompt, không phải ngôn ngữ Javis đã trả lời.
                "lang_theo_nguoi_dung": self.theo_nguoi_dung}


# ---------------------------------------------------------------- dò ngôn ngữ

# Khoảng mã Unicode -> mã ngôn ngữ, XẾP THEO ĐỘ ƯU TIÊN chứ không theo thứ tự gặp trong câu.
#
# Thứ tự quan trọng và đã cắn một lần: câu tiếng Nhật "今日の売上..." mở đầu bằng KANJI, mà
# kanji nằm trong khoảng Hán. Duyệt từng ký tự rồi trả về ngay khi khớp thì câu đó ra "zh".
# Phải quét HẾT chuỗi, thu tất cả hệ chữ có mặt, rồi mới chọn theo ưu tiên: thấy kana là
# tiếng Nhật, bất kể có bao nhiêu kanji đứng trước.
_KHOANG_CHU = (
    ((0x3040, 0x30FF), "ja"),      # hiragana + katakana - PHẢI đứng trước Hán
    ((0x0E00, 0x0E7F), "th"),      # thai
    ((0xAC00, 0xD7AF), "ko"),      # hangul
    ((0x0600, 0x06FF), "ar"),      # arabic
    ((0x0400, 0x04FF), "ru"),      # cyrillic
    ((0x4E00, 0x9FFF), "zh"),      # han - chỉ kết luận khi KHÔNG có kana nào trong câu
)

_TU = re.compile(r"[^\W_]+", re.UNICODE)

# Ba lớp bằng chứng NGƯỢC, và phải tách bạch vì chúng chắc chắn khác nhau.
#
# `_CHU_NGOAI`: ký tự tiếng Việt KHÔNG BAO GIỜ dùng. Thấy một chữ là chắc chắn không phải
# tiếng Việt. Chú ý â ê ô KHÔNG có ở đây vì tiếng Việt dùng cả ba.
_CHU_NGOAI = re.compile(r"[ñçüäößåæøœîûëï¿¡]", re.I)

# `_TU_NGOAI`: hư từ của các thứ tiếng Latin khác, những chữ tiếng Việt không có.
#
# Vì sao cần lớp này dù đã có `_CHU_NGOAI`. Người ta gõ thiếu dấu, và câu Âu châu gõ thiếu
# dấu thì KHÔNG còn ký tự nào lạ để mà bắt. Đo được: "les ventes du mois de juin sont bonnes"
# bị chấm là tiếng Việt (0.67) chỉ vì đúng một chữ "de", và "je voudrais le rapport de la
# semaine" cũng vậy nhờ "de" với "la". Danh sách hư từ tiếng Việt viết không dấu đầy những
# chữ hai ký tự trùng hư từ tiếng Âu, nên một câu tiếng Pháp bất kỳ gần như luôn trúng vài
# chữ - còn tiếng Pháp thì không có bộ từ vựng, nên nhận nhầm sang tiếng Việt là ĐEM BỘ TỪ
# VỰNG TIẾNG VIỆT ra chấm một câu tiếng Pháp. Đó đúng là kiểu hỏng mà cả tầng này sinh ra
# để chặn: nửa bộ từ vựng nguy hiểm hơn không có bộ nào.
#
# Chỉ nhặt chữ KHÔNG phải tiếng Việt không dấu. Cố ý bỏ qua: que (quê), con, hay, sao, nao
# (não), den (đến), dem (đêm), le (lê), no (nó) - mỗi chữ trong số đó là một chữ tiếng Việt
# có thật, và bắt chúng là làm hỏng đúng nhóm người dùng đông nhất.
_TU_NGOAI = frozenset((
    # Pháp
    "les", "des", "une", "sont", "est", "vous", "nous", "dans", "avec", "pour", "cette",
    "mais", "tous", "leur", "elle", "ils", "sur", "aux", "être", "etre", "voudrais",
    # Tây Ban Nha / Bồ Đào Nha
    "las", "los", "una", "unos", "unas", "por", "para", "del", "esta", "este", "como",
    "pero", "sus", "muy", "quiero", "tambien", "dos", "das", "uma", "foram", "deste",
    # Ý
    "della", "delle", "questo", "questa", "gli", "molto", "sono", "sul",
    # Đức
    "und", "ich", "nicht", "sind", "von", "mit", "auch", "sehr", "eine", "einen",
    # Hà Lan. KHÔNG lấy "het": nó là "hết" tiếng Việt viết không dấu, và bản đầu có nó nên
    # "xoa het don hang cua toi" bị loại khỏi cuộc chấm điểm rồi trả về rỗng.
    "deze", "niet", "een", "wil", "zien",
))
# Bao nhiêu chữ lạ thì kết luận. MỘT là đủ: những chữ trên không xuất hiện trong tiếng Việt,
# kể cả không dấu, nên một chữ đã là bằng chứng chắc. Đòi hai thì "quiero ver las ventas de
# este mes" (trúng quiero, las, este) qua được nhưng câu ngắn hơn thì không.
_TU_NGOAI_TOI_THIEU = 1


def _tu_ngoai_trong(s: str) -> set:
    """Các chữ lạ có trong câu, CHỈ tính khi văn bản gốc viết thường.

    Vì sao phải xét chữ hoa. Hư từ của một thứ tiếng luôn nằm giữa câu và viết thường; còn
    những chỗ chữ lạ tình cờ trùng thì gần như luôn viết hoa vì chúng là MÃ hoặc TÊN RIÊNG.
    Đo được hai ca thật trong ngữ cảnh tiếng Việt: "tim don hang co ma DES-2024" (mã đơn trùng
    `des` tiếng Pháp) và "san pham nay ban o Los Angeles" (địa danh trùng `los` tiếng Tây Ban
    Nha) - cả hai bị loại khỏi cuộc chấm điểm rồi trả về rỗng.

    Câu tiếng Pháp mở đầu bằng "Les" viết hoa vẫn bắt được, vì phần còn lại của câu còn hư từ
    viết thường ("sont", "de", "voudrais").
    """
    return {w for w in _TU.findall(str(s or "")) if w.islower()} & _TU_NGOAI

# `_DAU_CHUNG`: dấu sắc/huyền/hỏi trên nguyên âm trần. Tiếng Việt DÙNG chúng ("cá", "bà"),
# nhưng tiếng Pháp, Tây Ban Nha, Bồ Đào Nha, Ý cũng vậy - nên một mình nó không kết luận
# được gì. Nó chỉ dùng để SIẾT ngưỡng, xem chỗ chấm điểm bên dưới.
_DAU_CHUNG = re.compile(r"[éáíóúàèìòù]", re.I)

# Dấu RIÊNG của tiếng Việt. Cố ý KHÔNG lấy cả bộ dấu: à á è é ì í ò ó ù ú â ê ô dùng chung
# với tiếng Pháp, Tây Ban Nha, Bồ Đào Nha, Ý. Bản đầu vơ hết vào đây, nên
# "Peux-tu me résumer les ventes du mois de juin ?" bị nhận là tiếng Việt với độ tin 0.97
# chỉ vì một chữ "é", rồi Javis được lệnh trả lời người Pháp bằng tiếng Việt.
#
# Còn lại đây là những ký tự gần như chỉ tiếng Việt dùng: ă đ ơ ư, cùng các tổ hợp dấu hỏi,
# ngã, nặng. Một ký tự trong nhóm này là đủ chắc.
_DAU_VIET = re.compile(
    r"[ăđơư"
    r"ảãạằắẳẵặầấẩẫậ"
    r"ẻẽẹềếểễệ"
    r"ỉĩị"
    r"ỏõọồốổỗộờớởỡợ"
    r"ủũụừứửữự"
    r"ỳỷỹỵ]", re.I)


def _he_chu(text: str) -> str:
    """Hệ chữ ngoài Latin -> mã ngôn ngữ. "" nếu là chữ Latin hoặc không nhận ra.

    Quét hết chuỗi rồi mới chọn theo ưu tiên của `_KHOANG_CHU` - lý do ở ngay trên đó.
    """
    thay = set()
    for ch in text:
        ma = ord(ch)
        for (lo, hi), code in _KHOANG_CHU:
            if lo <= ma <= hi:
                thay.add(code)
                break
    for _, code in _KHOANG_CHU:
        if code in thay:
            return code
    return ""


def _bo_dau(text: str) -> str:
    """Bỏ dấu + hạ chữ thường. `đ` KHÔNG phân rã qua NFKD nên phải map tay - cùng cái bẫy đã
    ăn một lần ở `fast_path_runtime._norm`."""
    raw = str(text or "").replace("đ", "d").replace("Đ", "D")
    raw = unicodedata.normalize("NFKD", raw.casefold())
    return "".join(c for c in raw if not unicodedata.combining(c))


def detect(text: str) -> tuple[str, float]:
    """Dò ngôn ngữ của một đoạn văn bản. Trả (mã, độ tin cậy).

    Trả ("", 0.0) khi không đủ căn cứ - nơi gọi PHẢI hiểu đó là "giữ nguyên ngôn ngữ đang
    dùng", không phải "rơi về tiếng Việt".

    Ngôn ngữ dò ra có thể là ngôn ngữ CHƯA ĐĂNG KÝ (vd "ja", "th"). Đó là cố ý và quan trọng:
    các cổng chặn cần biết "người này đang viết tiếng Nhật mà ta không có bộ từ vựng tiếng
    Nhật" để suy biến an toàn, chứ không phải bị nói dối rằng đây là tiếng Việt.
    """
    s = str(text or "").strip()
    if len(s) < DO_DAI_TOI_THIEU:
        return "", 0.0

    ngoai_latin = _he_chu(s)
    if ngoai_latin:
        return ngoai_latin, 0.97

    if _DAU_VIET.search(s):
        return "vi", 0.97

    tu = set(_TU.findall(_bo_dau(s)))
    if not tu:
        return "", 0.0

    # Loại thẳng tiếng Việt khỏi cuộc chấm điểm khi câu mang dấu của thứ tiếng Latin khác.
    # Không có bước này thì một chữ "de" trong "les ventes du mois de juin" đủ để cả câu tiếng
    # Pháp bị chấm thành tiếng Việt, vì danh sách hư từ tiếng Việt viết không dấu chứa nhiều
    # chữ rất ngắn trùng với hư từ của tiếng Pháp, Tây Ban Nha, Bồ Đào Nha, Ý.
    # Hai đường loại tiếng Việt khỏi cuộc chấm điểm: ký tự lạ (câu có dấu), hoặc hư từ lạ
    # (câu gõ thiếu dấu, lúc đó không còn ký tự nào để mà bắt).
    loai = set()
    if _CHU_NGOAI.search(s) or len(_tu_ngoai_trong(s)) >= _TU_NGOAI_TOI_THIEU:
        loai.add("vi")

    diem: dict[str, int] = {}
    for code in lang_registry.ma_list():
        if code in loai:
            continue
        hu_tu = {_bo_dau(w) for w in lang_registry.get(code).stopwords}
        diem[code] = len(tu & hu_tu)

    tot_nhat = max(diem, key=lambda k: diem[k]) if diem else ""
    if not tot_nhat or diem[tot_nhat] == 0:
        return "", 0.0

    nhi = sorted(diem.values(), reverse=True)
    cach_biet = nhi[0] - (nhi[1] if len(nhi) > 1 else 0)
    # Trúng nhiều hư từ VÀ bỏ xa đối thủ thì mới dám chắc. Hai ngôn ngữ hoà nhau nghĩa là
    # câu đó trộn tiếng, và ép nó về một bên là đoán bừa.
    if cach_biet <= 0:
        return "", 0.0
    # Ngưỡng hư từ: bình thường MỘT là đủ, nhưng siết lên HAI khi câu có dấu sắc/huyền trên
    # nguyên âm trần mà KHÔNG có một chữ riêng nào của tiếng Việt.
    #
    # Vì sao phải phân biệt tinh đến vậy. Đòi hai hư từ ở mọi trường hợp thì phá đúng nhóm
    # người dùng đông nhất: tiếng Việt viết KHÔNG DẤU và ngắn ("entropy la gi") chỉ trúng một
    # chữ, mất sạch đường tắt tiết kiệm token. Còn để một hư từ ở mọi trường hợp thì một chữ
    # "de" trong "les ventes du mois de juin" đủ biến câu tiếng Pháp thành tiếng Việt, vì danh
    # sách hư từ tiếng Việt không dấu đầy những chữ hai ký tự trùng với tiếng Âu.
    #
    # Câu tiếng Việt CÓ DẤU thật gần như luôn mang ít nhất một chữ riêng (ă đ ơ ư hoặc dấu
    # hỏi/ngã/nặng), nên nó không rơi vào nhánh siết.
    nguong = 2 if (_DAU_CHUNG.search(s) and not _DAU_VIET.search(s)) else 1
    if nhi[0] < nguong:
        return "", 0.0
    tin = min(0.95, 0.55 + 0.12 * cach_biet)
    return tot_nhat, tin


# Động từ "dịch". Chỉ cần nó có mặt là câu đó không được tính là lệnh đổi ngôn ngữ.
_DONG_TU_DICH = re.compile(r"\b(dich|bien dich|chuyen ngu|translate|translation|localize|"
                           r"localise)\b")


def _yeu_cau_thang(text: str) -> str:
    """Người dùng ra lệnh THẲNG trong lượt này ("trả lời bằng tiếng Anh"). "" nếu không.

    Cố ý đòi một ĐỘNG TỪ ra lệnh đứng gần tên ngôn ngữ, chứ không chỉ thấy chữ "tiếng Anh" là
    đổi. Câu "anh cần dịch bài này sang tiếng Anh" là một YÊU CẦU DỊCH, không phải yêu cầu
    Javis đổi ngôn ngữ trả lời, mà hai câu đó rất giống nhau ở mặt chữ.
    """
    s = _bo_dau(text)
    if not s:
        return ""

    # Câu có ĐỘNG TỪ DỊCH thì KHÔNG bao giờ là lệnh đổi ngôn ngữ, dù mặt chữ giống hệt.
    # "dịch bài này sang tiếng Anh" là một YÊU CẦU LÀM VIỆC; hiểu nó thành "từ giờ nói tiếng
    # Anh với tôi" là đổi ngôn ngữ của cả cuộc trò chuyện vì một câu nhờ dịch. Chính test của
    # file này bắt được lỗi đó.
    if _DONG_TU_DICH.search(s):
        return ""

    # Động từ phải nói về việc TRẢ LỜI. Bản đầu nhận cả "dung", "viet", "write", "use" - quá
    # rộng, nên "anh dùng app học tiếng Anh nào tốt" bị hiểu là lệnh đổi ngôn ngữ, và nó còn
    # đè lên cả lựa chọn user đã ghim ở Cài đặt (mức 1 đứng trên mức 3).
    dong_tu = (r"tra loi|tra loi bang|noi|noi bang|chuyen sang|doi sang|"
               r"answer|reply|respond|speak|switch to")
    for code in lang_registry.ma_list():
        for tu in lang_registry.get(code).request_words:
            t = re.escape(_bo_dau(tu))
            for m in re.finditer(rf"\b({dong_tu})\b[^.!?\n]{{0,24}}?\b{t}\b", s):
                if not _la_cau_than(s, m.start()):
                    return code
    # Dạng đảo ("in English please", "bang tieng Anh nhe") CHỈ tính khi cả tin nhắn là một
    # câu ra lệnh ngắn. Câu dài chỉ NHẮC TỚI một ngôn ngữ thì không phải lệnh: "File hợp đồng
    # bằng tiếng Anh nằm ở đâu trong brain" là một câu hỏi về vị trí file, không phải yêu cầu
    # Javis đổi sang tiếng Anh - mà bản đầu hiểu đúng thành lệnh và đổi cả cuộc trò chuyện.
    if len(s) <= 40:
        for code in lang_registry.ma_list():
            for tu in lang_registry.get(code).request_words:
                t = re.escape(_bo_dau(tu))
                m = re.search(rf"\b(bang|in|sang)\s+{t}\b", s)
                if m and not _la_cau_than(s, m.start()):
                    return code
    return ""


# Từ hỏi lý do. Đứng ngay trước cụm "trả lời bằng tiếng X" thì câu đó là THAN chứ không phải lệnh.
_HOI_LY_DO = re.compile(r"\b(sao|tai sao|vi sao|why|how come)\b")


def _la_cau_than(s: str, vt: int) -> bool:
    """Cụm ở vị trí `vt` nằm trong câu hỏi lý do ("sao em lại trả lời bằng tiếng Anh?").

    0.65.29: chủ dự án hỏi đúng câu đó và bản cũ ghim tiếng Anh cho lượt ấy, tức là trả lời câu
    than bằng chính thứ tiếng đang bị than. Chỉ xét đoạn ngắn ngay trước cụm, trong cùng một câu,
    nên "trả lời bằng tiếng Anh được không" (nhờ lịch sự) vẫn là lệnh."""
    truoc = re.split(r"[.!?\n]", s[max(0, vt - 30):vt])[-1]
    return bool(_HOI_LY_DO.search(truoc))


# ---------------------------------------------------------------- bộ từ vựng

def co_lexicon(code: str) -> bool:
    """Ngôn ngữ này có bộ từ vựng cho các cổng chặn không.

    Import muộn để `lang.py` không kéo theo `lexicon` trên mọi đường nạp, và để một lexicon
    hỏng cú pháp không giết luôn cả việc dò ngôn ngữ.
    """
    try:
        import lexicon
        return lexicon.co(code)
    except Exception:
        return False


# ---------------------------------------------------------------- quyết định

def resolve(*, turn_text: str = "", reply_pref: str = "auto", chatbot_pin: str = "",
            brain_pin: str = "", channel_default: str = "", ui_lang: str = "") -> LangDecision:
    """Chốt xem lượt này Javis trả lời bằng tiếng gì.

    NGUYÊN TẮC (đổi ở 0.35.0, sau khi đo): **model tự bám theo ngôn ngữ người dùng, hàm này
    chỉ lo phần con người đã GHIM.**

    Vì sao đổi. Bản trước tự dò rồi tự chốt ngôn ngữ trả lời, và mình đã đo được nó làm việc
    đó tệ hơn hẳn thứ model làm miễn phí:

      - dò tiếng Anh trên câu hỏi thật: 16/18, tức vẫn có câu người ta gõ tiếng Anh mà bị trả
        lời tiếng Việt;
      - người viết tiếng Thái, Nhật, Pháp, Tây Ban Nha thì LUÔN bị trả lời tiếng Việt, vì các
        thứ tiếng đó không có trong sổ đăng ký nên rơi hết về mặc định.

    Model thì bám đúng ngôn ngữ người dùng cho MỌI thứ tiếng, không cần ai khai gì. Nên việc
    của hàm này rút lại còn: có ai ghim không? Có thì nêu tên ngôn ngữ đó. Không thì bảo model
    tự bám (`theo_nguoi_dung=True`).

    Thứ tự GHIM, cao xuống thấp:
      1. user ra lệnh thẳng trong lượt này ("trả lời bằng tiếng Anh")
      2. ngôn ngữ ghim của chatbot (bot phục vụ khách lạ, không theo ngôn ngữ của chủ)
      3. `reply_pref` khác "auto" - user đã ghim ở Cài đặt
      4. ngôn ngữ ghim của brain
      5. the language a voice call was spoken in (`call_language`); no channel has a fixed language since
         2026-11-15 (Zalo owner chats used to default to Vietnamese)

    Không ghim gì mà CÓ chữ người dùng gõ -> để model bám. Không ghim và cũng KHÔNG có chữ
    nào (việc chạy nền: loop, nhắc hẹn, Kanban, tự học) -> không có gì để bám, phải nêu tên
    một ngôn ngữ, lấy từ `ui_lang` rồi tới mặc định.

    `turn_text` LUÔN được dò, kể cả khi ngôn ngữ trả lời do model tự lo, vì các CỔNG CHẶN cần
    biết người dùng đang thật sự viết tiếng gì để chọn đúng bộ từ vựng. Đó là chỗ không có
    model nào trong vòng lặp, nên vẫn phải tự dò.
    """
    do_duoc, tin = detect(turn_text)

    def _xong(lang: str, source: str, conf: float, theo=False) -> LangDecision:
        ma = lang_registry.reply_code(lang) or lang_registry.MAC_DINH
        return LangDecision(ma, source, conf, co_lexicon(ma), do_duoc, theo)

    thang = _yeu_cau_thang(turn_text)
    if thang:
        return _xong(thang, "turn", 0.99)

    if lang_registry.reply_code(chatbot_pin):
        return _xong(chatbot_pin, "chatbot", 1.0)

    pref = lang_registry.reply_code(reply_pref)
    if pref:
        return _xong(pref, "setting", 1.0)

    if lang_registry.reply_code(brain_pin):
        return _xong(brain_pin, "brain", 1.0)

    if lang_registry.reply_code(channel_default):
        return _xong(channel_default, "channel", 0.9)

    if str(turn_text or "").strip():
        # Có chữ của người dùng: model bám theo. `lang` ở đây KHÔNG phải ngôn ngữ trả lời,
        # nó chỉ là ngôn ngữ để nêu tên ở những chỗ buộc phải nêu (đồng hồ trong prompt, danh
        # sách skill, giọng đọc dự phòng) - lấy ngôn ngữ dò được nếu có, không thì cấu hình.
        # 2026-11-15: a detected language Javis can NAME (Japanese, Thai, Korean...) is named too, not
        # only vi/en: the fast-path capsule then says "answer in Japanese" instead of the interface's.
        neu_ten = lang_registry.reply_code(do_duoc) or ui_lang
        return _xong(neu_ten, "detect" if do_duoc else "ui", max(tin, 0.5), theo=True)

    # Việc chạy nền: không có lượt người dùng nào để mà bám.
    if lang_registry.chuan_hoa(ui_lang):
        return _xong(ui_lang, "ui", 0.7)

    return _xong(lang_registry.MAC_DINH, "default", 0.5)


def resolve_background(*, ui_lang: str = "") -> LangDecision:
    """Language of work that has no chat turn: Kanban tasks, reminders, loops, learning (2026-11-15).

    The model follows the language of the TASK itself, which the owner wrote: a reminder written in
    Japanese reports in Japanese. Before, `build_system_prompt` without a language named Vietnamese
    for every brain, so an English or Japanese owner got every background report in Vietnamese.
    `ui_lang` only names the language of the clock line and the skill list.
    """
    ui = lang_registry.chuan_hoa(ui_lang) or lang_registry.MAC_DINH
    return LangDecision(ui, "ui", 0.7, co_lexicon(ui), "", True)


# ---------------------------------------------------------------- chữ cho prompt

def call_language(said: str, recognition_lang: str = "") -> str:
    """Ngôn ngữ ghim cho bộ não chính khi việc tới từ CUỘC GỌI giọng nói, "" = để model tự bám.

    Lấy theo câu người dùng VỪA NÓI, không theo câu giao việc mà model giọng nói viết lại (có
    lúc là tiếng Anh dù người dùng nói tiếng Việt). Không dò ra thì theo ngôn ngữ nhận dạng của
    mic ("vi-VN"); mic để "auto" thì không ghim gì."""
    code, _ = detect(said)
    # Any nameable language (2026-11-15): a call in Japanese pins Japanese, as one in Vietnamese pins Vietnamese.
    return lang_registry.reply_code(code) or lang_registry.reply_code(recognition_lang)


# Why the pin holds, in the block and in the per-turn line. Background work and an unknown source
# name no reason: there is no person behind it to quote.
_PIN_REASON = {
    "turn": "asked for in this message",
    "setting": "set in Settings",
    "chatbot": "the language of this bot",
    "brain": "the language of this brain",
    "channel": "the language of this channel or call",
}

# The prompt around this block is mostly Vietnamese (the blocks Javis inserts, the channel rules,
# tool results, system skills), and its examples address the reader as mình/bạn. Measured
# 2026-11-15: after the English kernel, the last ~13,000 characters before the model writes are
# about 80% Vietnamese words. A model reads that as a hint; this line says it is none.
_NOT_A_HINT = ("These rules are in English, while tool results, the brain and Javis's own labels may be in "
               "Vietnamese or another language. That is NEVER a hint about the reply language.")
# 2026-11-16 (owner's screenshot): on a long technical turn, Claude Code's notes between tool calls drifted into English
# for a Vietnamese user. The rule said "the WHOLE reply", and a model reads its working notes as scratch, not the reply.
_EVERY_LINE = ("This covers every line the user sees: the notes you write between tool calls while you work, status "
               "lines and the final answer. Code, logs and tool results in another language never change it.")
_KEEP_AS_IS = ("Do not translate: proper nouns, file paths, tool names, brain names, code blocks, and "
               "verbatim excerpts from the brain or a tool result. Content in another language is read "
               "as it is; only the REPLY follows this block.")


def khoi_ngon_ngu(quyet_dinh: LangDecision) -> str:
    """Khối "# === NGÔN NGỮ ===" nối vào system prompt.

    Written in ENGLISH since 2026-11-15. The old reason to keep it Vietnamese ("one CLAUDE.md, the
    rules are not translated N times") lapsed when CLAUDE.md itself moved to English; what was left
    was a Vietnamese rule about the reply language sitting in a Vietnamese tail, read by an English
    speaker's turn. The header stays `# === NGÔN NGỮ ===`: CLAUDE.md points at it by that name and
    `context_runtime` measures blocks by their header. The last line of a pinned block is the
    registry `nudge`, written in the target language itself, for small models that drift with
    the language of the prompt.
    """
    l = lang_registry.reply_info(quyet_dinh.lang)
    # "English (en)", "Japanese (日本語, ja)": the native name helps a model tell close languages apart.
    ten = f"{l.english} ({l.code})" if l.english == l.native else f"{l.english} ({l.native}, {l.code})"

    if quyet_dinh.theo_nguoi_dung:
        # Không ai ghim gì: để model bám. Nó làm việc này tốt hơn bộ dò của mình, và làm được
        # với MỌI thứ tiếng chứ không riêng hai thứ có trong sổ đăng ký. But a reply language the
        # person STATED (profile, memory, earlier in the chat) used to lose to "the language of
        # the last message" here, because this block sits after the profile and said nothing
        # about it: the root of "it keeps forgetting I want English".
        return "\n".join([
            "",
            "",
            "# === NGÔN NGỮ ===",
            "Reply in the language of the user's latest message: Vietnamese gets Vietnamese, "
            "English gets English, any other language gets that language.",
            "A reply language the user has STATED wins over that rule: in the user profile, in "
            "long-term memory, or earlier in this conversation (\"English please\", \"always answer "
            "me in Vietnamese\"). Keep it on every later turn, even when they type in another "
            "language, until they ask for a different one. If they say to ALWAYS use a language, "
            "also save it as a `preference` memory.",
            "Write the WHOLE reply in that one language, headings, labels, units, warnings and "
            "questions back included. Do not mix two languages in one reply.",
            _EVERY_LINE,
            "A message too short to tell (\"ok\", \"do 2\") keeps the language already in use in "
            "this conversation.",
            _NOT_A_HINT,
            _KEEP_AS_IS,
        ])

    why = _PIN_REASON.get(quyet_dinh.source, "")
    dong = [
        "",
        "",
        "# === NGÔN NGỮ ===",
        f"Reply language: {ten}" + (f", {why}." if why else "."),
    ]
    if quyet_dinh.detected and quyet_dinh.detected != l.code:
        dong.append(f"(The user is writing in: {quyet_dinh.detected}. Still reply in "
                    f"{l.english}, as pinned.)")
    dong += [
        f"Write the WHOLE reply in {l.english}, headings, labels, units, warnings and "
        "questions back included.",
        _EVERY_LINE,
        _NOT_A_HINT,
        _KEEP_AS_IS,
    ]
    if quyet_dinh.source in ("turn", "setting"):
        dong.append("If the user now asks for another language, use that one.")
    dong.append(l.nudge)
    return "\n".join(dong)


def nudge_dau_luot(code: str) -> str:
    """Câu nhắc ngắn viết bằng chính ngôn ngữ đích, dán lên đầu tin nhắn user cho engine yếu."""
    return lang_registry.reply_info(code).nudge
