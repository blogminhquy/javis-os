"""Quyết định Javis trả lời bằng ngôn ngữ nào, và dò ngôn ngữ người dùng đang viết.

Đây là hàm DUY NHẤT trả lời câu hỏi "lượt này nói tiếng gì". Mọi chỗ cần biết ngôn ngữ đều
gọi vào đây thay vì tự đoán, để câu trả lời, giọng đọc, cổng chặn và prompt không bao giờ
lệch nhau trong cùng một lượt.

Ba biến ngôn ngữ tách rời (spec mục 4.1), đừng nhập một:
  ui_lang       chữ trên màn hình      - user chọn, lưu theo thiết bị
  reply_lang    Javis trả lời          - mặc định "auto" = bám theo người dùng
  content_lang  nội dung trong brain   - của user, Javis không đụng

Dò ngôn ngữ KHÔNG dùng thư viện ngoài. Chỉ cần phân biệt giữa các ngôn ngữ ĐÃ ĐĂNG KÝ, nên
hai tầng là đủ: nhận hệ chữ qua khoảng mã Unicode (xong ngay tiếng Nhật, Thái, Hàn, Ả Rập,
Nga), rồi chấm điểm hư từ cho các thứ tiếng chữ Latin. Cả hai tầng đều đọc dữ liệu từ
`lang_registry`, nên thêm ngôn ngữ vẫn là thêm DỮ LIỆU.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass

import lang_registry


# Ngưỡng tin cậy để ĐỔI ngôn ngữ của một phiên đang chạy. Cố ý cao: người Việt chèn một câu
# tiếng Anh giữa cuộc trò chuyện là chuyện thường ngày, và Javis đổi hẳn sang tiếng Anh vì
# một câu như thế thì khó chịu hơn hẳn so với việc trả lời chậm đổi một lượt.
NGUONG_DOI = 0.80

# Số lượt LIÊN TIẾP phải cùng dò ra ngôn ngữ mới thì mới đổi. Một lượt là chưa đủ: xem trên.
SO_LUOT_DE_DOI = 2

# Văn bản ngắn hơn ngần này thì không đủ căn cứ để dò ("ok", "cảm ơn", "yes"). Trả về ngôn
# ngữ rỗng để nơi gọi giữ nguyên ngôn ngữ đang dùng.
DO_DAI_TOI_THIEU = 12

# Trần số phiên nhớ trong RAM. Ngôn ngữ phiên là thứ rẻ tiền, mất thì dò lại, nên không đáng
# đẩy xuống đĩa; nhưng để dict lớn vô hạn trên tiến trình chạy nhiều tháng thì là rò rỉ.
TRAN_PHIEN = 2000


@dataclass(frozen=True)
class LangDecision:
    lang: str            # ngôn ngữ CHỐT cho lượt này
    source: str          # turn | chatbot | brain | channel | session | detect | ui | default
    confidence: float
    has_lexicon: bool    # có bộ từ vựng cho ngôn ngữ này không (xem server/lexicon/)
    detected: str = ""   # ngôn ngữ dò được từ lượt này, kể cả khi không được dùng

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
        # Dò được từ chính lượt này thì lấy luôn, chắc nhất.
        if self.detected:
            return self.detected
        # Không dò được (câu quá ngắn: "ok thanks", "cho anh xem") thì mượn ngôn ngữ của
        # PHIÊN - nhưng CHỈ khi ngôn ngữ đó đến từ việc QUAN SÁT người dùng viết, tức là
        # `detect` hoặc `session`. Nếu nó đến từ một cái GHIM (`setting`, `chatbot`, `brain`,
        # `channel`, `ui`, `default`) thì nó nói về ngôn ngữ Javis phải TRẢ LỜI, không nói gì
        # về ngôn ngữ người dùng đang VIẾT - và mượn nhầm nó là quay lại đúng con bệnh cũ.
        if self.source in ("detect", "session"):
            return self.lang
        return ""

    def as_trace(self) -> dict:
        return {"lang": self.lang, "lang_source": self.source,
                "lang_confidence": round(float(self.confidence), 3),
                "lang_has_lexicon": self.has_lexicon,
                "lang_detected": self.detected}


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

# Hai lớp bằng chứng NGƯỢC, và phải tách bạch vì chúng chắc chắn khác nhau.
#
# `_CHU_NGOAI`: ký tự tiếng Việt KHÔNG BAO GIỜ dùng. Thấy một chữ là chắc chắn không phải
# tiếng Việt. Chú ý â ê ô KHÔNG có ở đây vì tiếng Việt dùng cả ba.
_CHU_NGOAI = re.compile(r"[ñçüäößåæøœîûëï¿¡]", re.I)

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
    loai = {"vi"} if _CHU_NGOAI.search(s) else set()

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
            if re.search(rf"\b({dong_tu})\b[^.!?\n]{{0,24}}?\b{t}\b", s):
                return code
    # Dạng đảo ("in English please", "bang tieng Anh nhe") CHỈ tính khi cả tin nhắn là một
    # câu ra lệnh ngắn. Câu dài chỉ NHẮC TỚI một ngôn ngữ thì không phải lệnh: "File hợp đồng
    # bằng tiếng Anh nằm ở đâu trong brain" là một câu hỏi về vị trí file, không phải yêu cầu
    # Javis đổi sang tiếng Anh - mà bản đầu hiểu đúng thành lệnh và đổi cả cuộc trò chuyện.
    if len(s) <= 40:
        for code in lang_registry.ma_list():
            for tu in lang_registry.get(code).request_words:
                t = re.escape(_bo_dau(tu))
                if re.search(rf"\b(bang|in|sang)\s+{t}\b", s):
                    return code
    return ""


# ---------------------------------------------------------------- ngôn ngữ dính theo phiên

_PHIEN: dict[str, dict] = {}
_KHOA = threading.RLock()


def _phien_doc(session_id: str) -> dict:
    with _KHOA:
        return dict(_PHIEN.get(str(session_id or ""), {}))


def _phien_ghi(session_id: str, lang: str, streak_lang: str = "", streak: int = 0,
               streak_best: float = 0.0) -> None:
    sid = str(session_id or "")
    if not sid:
        return
    with _KHOA:
        if len(_PHIEN) >= TRAN_PHIEN and sid not in _PHIEN:
            # Bỏ mục cũ nhất. dict của Python giữ thứ tự chèn nên đây là FIFO, đủ tốt cho
            # một bộ nhớ tạm mất cũng không sao.
            try:
                _PHIEN.pop(next(iter(_PHIEN)))
            except StopIteration:
                pass
        _PHIEN[sid] = {"lang": lang, "streak_lang": streak_lang, "streak": streak,
                       "streak_best": streak_best}


def quen_phien(session_id: str = "") -> None:
    """Xoá ngôn ngữ đã nhớ. Không truyền gì = xoá sạch (dùng trong test)."""
    with _KHOA:
        if session_id:
            _PHIEN.pop(str(session_id), None)
        else:
            _PHIEN.clear()


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

def resolve(*, turn_text: str = "", session_id: str = "", reply_pref: str = "auto",
            chatbot_pin: str = "", brain_pin: str = "", channel_default: str = "",
            ui_lang: str = "") -> LangDecision:
    """Chốt ngôn ngữ trả lời cho một lượt, theo thứ tự ưu tiên ở spec mục 4.1.

    Thứ tự, cao xuống thấp:
      1. user ra lệnh thẳng trong lượt này
      2. ngôn ngữ ghim của chatbot (bot phục vụ khách lạ, không theo ngôn ngữ của chủ)
      3. `reply_pref` khác "auto" - user đã ghim ở Cài đặt
      4. ngôn ngữ ghim của brain
      5. mặc định của kênh (Zalo là nền tảng Việt Nam)
      6. dò từ tin nhắn, có luật dính theo phiên
      7. ui_lang
      8. mặc định

    `turn_text` LUÔN được dò, kể cả khi kết quả không được dùng, vì các cổng chặn cần biết
    người dùng đang THẬT SỰ viết tiếng gì để suy biến cho đúng - khác với ngôn ngữ Javis
    được lệnh phải trả lời.
    """
    do_duoc, tin = detect(turn_text)

    def _xong(lang: str, source: str, conf: float) -> LangDecision:
        ma = lang_registry.chuan_hoa(lang) or lang_registry.MAC_DINH
        return LangDecision(ma, source, conf, co_lexicon(ma), do_duoc)

    thang = _yeu_cau_thang(turn_text)
    if thang:
        if session_id:
            _phien_ghi(session_id, thang)
        return _xong(thang, "turn", 0.99)

    if lang_registry.chuan_hoa(chatbot_pin):
        return _xong(chatbot_pin, "chatbot", 1.0)

    pref = lang_registry.chuan_hoa(reply_pref)
    if pref:
        return _xong(pref, "setting", 1.0)

    if lang_registry.chuan_hoa(brain_pin):
        return _xong(brain_pin, "brain", 1.0)

    if lang_registry.chuan_hoa(channel_default):
        return _xong(channel_default, "channel", 0.9)

    # --- dò, có quán tính ---
    truoc = _phien_doc(session_id)
    dang_dung = truoc.get("lang") or ""

    if do_duoc and lang_registry.duoc_ho_tro(do_duoc):
        if not dang_dung:
            _phien_ghi(session_id, do_duoc)
            return _xong(do_duoc, "detect", tin)
        if do_duoc == dang_dung:
            # Quay lại ngôn ngữ đang dùng thì xoá luôn chuỗi lượt đang tích cho ngôn ngữ kia:
            # đó không còn là một chuỗi LIÊN TIẾP nữa.
            _phien_ghi(session_id, dang_dung)
            return _xong(dang_dung, "session", max(tin, 0.9))

        # Dò ra ngôn ngữ KHÁC. Tích luỹ bằng chứng qua nhiều lượt thay vì đòi mỗi lượt phải
        # tự mình đủ tin.
        #
        # Bản đầu đòi `tin >= NGUONG_DOI` mới được cộng chuỗi, và nó KHÔNG BAO GIỜ đổi được
        # ngôn ngữ trong thực tế: một người chuyển hẳn sang tiếng Anh vẫn có những lượt chỉ
        # trúng hai hư từ (tin 0.79), và mỗi lượt như thế lại xoá sạch chuỗi vừa tích. Nay
        # chuỗi cộng theo mọi lượt cùng trỏ về một ngôn ngữ, còn ngưỡng tin áp lên ĐỘ TIN
        # CAO NHẤT từng thấy trong chuỗi đó.
        streak = (truoc.get("streak", 0) + 1) if truoc.get("streak_lang") == do_duoc else 1
        best = max(float(truoc.get("streak_best", 0.0)) if truoc.get("streak_lang") == do_duoc
                   else 0.0, tin)
        if streak >= SO_LUOT_DE_DOI and best >= NGUONG_DOI:
            _phien_ghi(session_id, do_duoc)
            return _xong(do_duoc, "detect", best)
        _phien_ghi(session_id, dang_dung, streak_lang=do_duoc, streak=streak, streak_best=best)
        return _xong(dang_dung, "session", 0.85)

    if dang_dung:
        return _xong(dang_dung, "session", 0.75)

    if lang_registry.chuan_hoa(ui_lang):
        return _xong(ui_lang, "ui", 0.7)

    return _xong(lang_registry.MAC_DINH, "default", 0.5)


# ---------------------------------------------------------------- chữ cho prompt

def khoi_ngon_ngu(quyet_dinh: LangDecision) -> str:
    """Khối "# === NGÔN NGỮ ===" nối vào system prompt.

    Bản thân khối viết bằng TIẾNG VIỆT có chủ ý (spec quyết định số hai: một bản CLAUDE.md,
    không dịch luật hành xử ra N bản - model không cần đọc luật bằng tiếng Anh để trả lời
    bằng tiếng Anh). Chỉ câu `nudge` cuối là viết bằng chính ngôn ngữ đích, dành cho model
    nhỏ vốn trôi theo ngôn ngữ của prompt.
    """
    l = lang_registry.get(quyet_dinh.lang)
    dong = [
        "",
        "",
        "# === NGÔN NGỮ ===",
        f"Ngôn ngữ trả lời: {l.lang_directive} ({l.code}).",
    ]
    if quyet_dinh.detected and quyet_dinh.detected != l.code:
        dong.append(f"(Người dùng đang viết bằng: {quyet_dinh.detected}. Vẫn trả lời bằng "
                    f"{l.lang_directive} theo lựa chọn đã ghim.)")
    dong += [
        "Viết TOÀN BỘ câu trả lời bằng ngôn ngữ này, kể cả tiêu đề, nhãn, đơn vị và câu cảnh báo.",
        "Giữ nguyên KHÔNG dịch: tên riêng, đường dẫn file, tên tool, tên brain, khối mã, và "
        "đoạn trích nguyên văn từ brain hoặc từ kết quả tool.",
        "Nội dung trong brain viết bằng ngôn ngữ khác thì cứ đọc bình thường, chỉ TRẢ LỜI "
        "bằng ngôn ngữ trên.",
        l.nudge,
    ]
    return "\n".join(dong)


def nudge_dau_luot(code: str) -> str:
    """Câu nhắc ngắn viết bằng chính ngôn ngữ đích, dán lên đầu tin nhắn user cho engine yếu."""
    return lang_registry.get(code).nudge
