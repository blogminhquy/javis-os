"""Nghe tin thoại: file âm thanh -> chữ (speech-to-text), qua Whisper của Groq.

Vì sao Groq: Javis đã có sẵn ô nhập `groq_api_key` ở trang Models (Groq là một trong tám bộ
não), và Groq phục vụ Whisper trên CÙNG endpoint OpenAI-compat với model chat. Ai đã đấu Groq
để chat thì không phải đăng ký thêm nhà cung cấp nào nữa mới ra lệnh bằng giọng nói được.

Module này KHÔNG đọc settings và KHÔNG biết Telegram/Zalo là gì: nhận bytes + key, trả chữ.
Chỗ gọi (main.py) lo lấy key, kênh chat lo lời thoại với người dùng. Nhờ vậy kênh Zalo đấu
vào sau này dùng lại nguyên module chứ không phải chép bản thứ hai.

Trả về LUÔN là dict có khoá `ok`. Hỏng thì kèm `ly_do` (mã máy đọc) và `noi_voi_javis` (một
dòng tiếng Việt để đưa thẳng vào lượt chat) - chứ không ném ngoại lệ: một tin thoại nghe hụt
không được phép làm gãy vòng nhận tin của bot.
"""
import re
import sys

import httpx

# ---- Whisper bịa câu kêu gọi đăng ký kênh ----
# Whisper học chủ yếu từ phụ đề YouTube, nên gặp im lặng, tiếng ồn nền hay một đoạn ngắn không
# rõ là nó "nhớ lại" mấy câu outro dày đặc trong dữ liệu học. Tiếng Việt nổi tiếng nhất là
# "Hãy subscribe cho kênh Ghiền Mì Gõ Để không bỏ lỡ những video hấp dẫn". Đây là thứ nguy hiểm
# một cách âm thầm: không phải lỗi mạng nên không có gì báo, nó lặng lẽ thành tin nhắn của
# người dùng và Javis trả lời nó một cách nghiêm túc. Whisper cũng hay dán câu bịa vào TRƯỚC
# lời thật, nên phải cắt theo từng câu chứ không vứt cả lượt.
#
# Ranh giới: mẫu phải ĐỦ HẸP để không đụng lời nói thật. Người dùng bàn chuyện marketing hằng
# ngày ("đăng ký kênh YouTube tốn bao nhiêu", "viết câu kêu gọi đăng ký kênh"), nên chỉ bắt khi
# có dấu hiệu riêng của câu outro: tên kênh, "subscribe cho kênh", hoặc cụm "không bỏ lỡ ...
# video". Thà sót một câu bịa còn hơn nuốt một câu người ta nói thật.
_AO_GIAC = [re.compile(p, re.I) for p in (
    r"ghi[eề]n\s*m[iì]\s*g[oõ]",                 # tên kênh trong câu outro phổ biến nhất
    r"subscribe\s+cho\s+k[eê]nh",
    r"(đăng\s*k[yý]|like)\b[^.!?]{0,60}\bk[eê]nh\b[^.!?]{0,60}kh[oô]ng\s+b[oỏ]\s+l[oỡ]",
    r"kh[oô]ng\s+b[oỏ]\s+l[oỡ]\s+(nh[uữ]ng\s+)?video(\s+(h[aấ]p\s+d[aẫ]n|m[oớ]i\s+nh[aấ]t|hay|m[oớ]i))?",
    # "Các bạn hãy đăng ký kênh để ủng hộ kênh của mình nhé" và họ hàng: dấu hiệu riêng là
    # NGƯỜI NÓI tự kêu gọi ủng hộ kênh CỦA MÌNH, chuyện không bao giờ xảy ra khi ra lệnh cho
    # trợ lý. Phải có cả "đăng ký/ủng hộ" lẫn "kênh ... của mình/tôi/chúng tôi/mình nhé".
    # Đuôi khép câu ("... kênh nha các bạn") nuốt luôn, không thì còn lại một mẩu cụt lủn mà
    # đếm chữ vẫn thấy "đủ dài". Chỉ nuốt đúng mấy tiếng đệm quen thuộc, không nuốt bừa.
    r"(đăng\s*k[yý]|[uủ]ng\s*h[oộ])\b[^.!?]{0,60}\bk[eê]nh\b[^.!?]{0,40}"
    r"([uủ]ng\s*h[oộ]|c[uủ]a\s+(m[iì]nh|t[oô]i|ch[uú]ng\s+(t[oô]i|m[iì]nh)))"
    r"(\s+(k[eê]nh|nh[eé]|nha|nh[aá]|v[oớ]i|đi|m[iì]nh|c[aá]c\s+b[aạ]n)){0,4}",
    r"c[aá]c\s+b[aạ]n\b[^.!?]{0,40}(đăng\s*k[yý]|subscribe)\b[^.!?]{0,30}\bk[eê]nh",
    # "Cảm ơn các bạn đã theo dõi và hẹn gặp lại" - phải có ĐỦ ba mảnh mới bắt, vì riêng
    # "cảm ơn" hay "theo dõi" thì người dùng nói suốt.
    r"c[aả]m\s*[oơ]n\s+c[aá]c\s+b[aạ]n[^.!?]{0,40}theo\s*d[oõ]i[^.!?]{0,40}h[eẹ]n\s+g[aặ]p\s+l[aạ]i",
    # 0.64.74, gặp thật 28/09: hai câu kết video không có "hẹn gặp lại" đi kèm.
    r"c[aả]m\s*[oơ]n\s+c[aá]c\s+b[aạ]n\s+đ[aã]\s+(theo\s*d[oõ]i|xem)(\s+video)?",
    r"(c[aá]c\s+b[aạ]n\s+)?(c[oó]\s+th[eể]\s+)?nh[aậ]n\s+th[eê]m\s+th[oô]ng\s+tin[^.!?]{0,60}"
    r"ph[aầ]n\s+b[iì]nh\s+lu[aậ]n",
    r"subscribe\s+to\s+(my|our|the|this)\s+channel",
    r"thanks?\s+(you\s+)?for\s+watching",
    r"h[eẹ]n\s+g[aặ]p\s+l[aạ]i[^.!?]{0,40}video\s+(ti[eế]p\s+theo|sau)",
)]

# Chú thích trong ngoặc do Whisper tự thêm (không ai đọc thành tiếng mấy thứ này).
_CHU_THICH = re.compile(
    r"[\[\(]\s*(music|nhạc|nhạc\s*nền|applause|vỗ\s*tay|laughter|cười|silence|im\s*lặng|"
    r"blank[_\s]*audio|inaudible|sound|tiếng\s*động)[^\]\)]{0,20}[\]\)]", re.I)
_NOT_NHAC = re.compile("[♪♫♬♩]+")
# Tách "câu" để soi từng mảnh. XUỐNG DÒNG cũng là ranh giới: khối điều khiển của Javis
# (`[NGỮ CẢNH GIAO DIỆN: ...]`) đứng riêng một dòng, không tách ra thì nó dính vào câu bịa ngay
# sau và bị cắt oan. Ba nhánh phủ HẾT mọi ký tự nên ghép lại là nguyên văn.
_CAU = re.compile(r"[^.!?…\n]+[.!?…]*|[.!?…]+|\n")
_CO_CHU = re.compile(r"[^\W_]", re.U)   # còn ít nhất một chữ cái hay chữ số thì mới là lời nói
_GIU_TOI_THIEU = 4   # số chữ tối thiểu để một mẩu hai bên câu bịa được coi là lời nói thật


def loc_ao_giac(text) -> str:
    """Cắt những câu Whisper BỊA ra, giữ nguyên phần người dùng nói thật.

    Trả chuỗi đã cắt (có thể rỗng). Rỗng nghĩa là cả lượt chỉ toàn câu bịa: chỗ gọi nên coi như
    không nghe rõ và giữ lại chữ của Web Speech, đừng đẩy chuỗi rỗng đi tiếp.

    KHÔNG CẮT GÌ THÌ PHẢI TRẢ LẠI Y NGUYÊN. Bản đầu cắt câu rồi nối lại bằng khoảng trắng, thành
    ra `README.md` hoá `README. md` và `https://github.com/x` hoá `https://github. com/x` dù
    chẳng có câu bịa nào - phát hiện khi quét thử kho hội thoại cũ (0.57.5). Nên ở đây ghép lại
    NGUYÊN VĂN từng đoạn giữ lại, kể cả phần regex tách câu bỏ qua.
    """
    s = str(text or "")
    s = _CHU_THICH.sub(" ", s)
    s = _NOT_NHAC.sub(" ", s)
    phan, pos, da_bo = [], 0, False
    for m in _CAU.finditer(s):
        if m.start() > pos:
            phan.append(s[pos:m.start()])          # dấu câu đứng đầu chuỗi, regex không nuốt
        cau = m.group(0)
        pos = m.end()
        # finditer chứ không search: Whisper hay lặp câu bịa vài lần trong một câu, lấy mỗi
        # lần khớp ĐẦU TIÊN thì bản sao thứ hai sống sót nguyên vẹn (thấy ở tin #592).
        hits = [x for r in _AO_GIAC for x in r.finditer(cau)]
        if not cau.strip() or not hits:
            phan.append(cau)
            continue
        # Nhiều mẫu cùng khớp một câu bịa (tên kênh, "subscribe cho kênh", "không bỏ lỡ video"),
        # nên lấy TỪ chỗ khớp sớm nhất ĐẾN chỗ khớp muộn nhất làm vùng bỏ.
        dau, duoi = cau[:min(h.start() for h in hits)], cau[max(h.end() for h in hits):]
        n_dau, n_duoi = len(dau.split()), len(duoi.split())
        # Câu bịa NẰM GIỮA lời thật, hai đầu đều ra hồn: đó là người dùng đang TRÍCH DẪN nó
        # ("anh thấy có cái câu là các bạn đã đăng ký kênh ủng hộ mình, anh không nói câu đấy").
        # Cắt là phá nát ý họ, nên giữ nguyên cả câu. Gặp thật khi quét kho (tin #658).
        if n_dau >= _GIU_TOI_THIEU and n_duoi >= _GIU_TOI_THIEU:
            phan.append(cau)
            continue
        # Còn lại: bỏ vùng bịa, giữ hai đầu nếu còn ra hồn một câu nói. Dưới mức đó thường chỉ
        # là "Hãy", "Nhớ", "nha các bạn" dính liền với chính câu bịa.
        da_bo = True
        if n_dau >= _GIU_TOI_THIEU:
            phan.append(dau)
        if n_duoi >= _GIU_TOI_THIEU:
            phan.append(duoi)
    if pos < len(s):
        phan.append(s[pos:])
    out = "".join(phan)
    if da_bo:
        out = re.sub(r"[ \t]{2,}", " ", out)       # dọn khoảng trống ngay vết cắt, chừa xuống dòng
    out = out.strip()
    return out if _CO_CHU.search(out) else ""


# ---- Đối chiếu chữ Groq với bản nháp của trình duyệt (0.64.74) ----
# Dashboard chạy song song hai bộ nghe: Web Speech cho chữ tạm (bản nháp), MediaRecorder gửi
# Groq. 0.64.73 cho chữ Groq thay bản nháp. Chủ dự án 28/09 gửi ảnh: bản nháp đúng 100%
# ("today How are you I'm fine thank you chào em nhé"), còn tin lưu vào hội thoại là "Cảm ơn
# các bạn đã theo dõi và", "Các bạn có thể nhận thêm thông tin về các bài hát của mình trong
# phần bình luận" - Whisper BỊA vì audio nó nhận thiếu tiếng nói. Groq sửa đúng thì hai bản
# vẫn gần nhau về ÂM ("clash là dịch vụ" / "Cloudflare là dịch vụ"); Groq bịa thì không.
# Đo trên cặp thật: sửa đúng giống âm 0,80 tới 1,0; câu bịa 0,06 tới 0,44.
NGUONG_KHOP_AM = 0.6
NGUONG_KHOP_TU = 0.4


def khop_ban_nhap(nhap, nghe) -> tuple:
    """(có dùng được chữ Groq không, độ giống theo chữ, độ giống theo âm).

    Bản nháp rỗng thì không có gì để đối chiếu: dùng Groq như cũ.
    """
    import difflib
    a, b = str(nhap or "").strip(), str(nghe or "").strip()
    if not a or not b:
        return True, 1.0, 1.0
    wa = [w.casefold() for w in _CHU_THUONG.findall(a)]
    wb = [w.casefold() for w in _CHU_THUONG.findall(b)]
    tu = difflib.SequenceMatcher(None, wa, wb, autojunk=False).ratio() if wa and wb else 0.0
    am = 0.0
    try:
        import nghe_sua
        import phien_am
        ka = nghe_sua.khoa_am("".join(phien_am.doc_cum(a).split()))
        kb = nghe_sua.khoa_am("".join(phien_am.doc_cum(b).split()))
        am = difflib.SequenceMatcher(None, ka, kb, autojunk=False).ratio() if ka and kb else 0.0
    except Exception:
        pass
    return (tu >= NGUONG_KHOP_TU or am >= NGUONG_KHOP_AM), round(tu, 2), round(am, 2)


_CHU_THUONG = re.compile(r"[^\W_]+", re.U)
_MOI_LAP_MIN = 4   # dưới số chữ này thì trùng lời mồi là chuyện thường ("deploy lên VPS")


def la_lap_loi_moi(text, moi) -> bool:
    """Whisper gặp im lặng hay chép lại chính prompt (danh sách từ mồi, xem nghe_sua.goi_y_whisper).

    Nhận ra bằng cách: chữ nghe được, bỏ dấu câu và hạ thường, là một ĐOẠN LIỀN của lời mồi và
    dài từ `_MOI_LAP_MIN` chữ. Người thật hầu như không đọc bốn từ mồi liền nhau đúng thứ tự.
    """
    a = _CHU_THUONG.findall(str(text or "").lower())
    b = _CHU_THUONG.findall(str(moi or "").lower())
    if len(a) < _MOI_LAP_MIN or len(a) > len(b):
        return False
    return f" {' '.join(a)} " in f" {' '.join(b)} "


GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
STT_MAC_DINH = "vi"   # gợi ý khi chỗ gọi không chốt gì; "" ở chỗ gọi = để Whisper tự dò

# Bản ĐẦY ĐỦ, không phải turbo (0.64.67): đo thật trên câu Việt xen Anh, turbo chép "GitHub
# Actions" thành "Youtube Action", "build agent" thành "bill A-Ren"; bản đầy đủ ra đúng. Độ trễ
# trên Groq gần như bằng nhau (~0,7 giây một câu), giá vẫn rẻ. Đổi được qua `voice.stt_model`.
STT_MODEL_MAC_DINH = "whisper-large-v3"
MAX_STT_MB = 24          # Groq chặn ở 25MB; chừa biên cho phần multipart bọc ngoài
STT_TIMEOUT = 120.0      # tin thoại dài vài phút vẫn phải kịp, mạng VPS có lúc chậm

# Câu Javis nói khi chưa đấu key. Để ở đây (không rải trong từng kênh) vì mọi kênh nói CÙNG
# một chuyện: thiếu đúng một thứ, và thứ đó nằm ở đúng một chỗ trong dashboard.
_HD_THIEU_KEY = (
    "[Người dùng vừa gửi TIN THOẠI. Javis chưa nghe được vì chưa có bộ nghe nào - "
    "thứ chuyển giọng nói thành chữ. Hãy nói với họ: muốn ra lệnh bằng ghi âm thì chọn MỘT trong hai cách: "
    "vào trang Models trong dashboard dán API key của Groq (lấy ở console.groq.com, có gói miễn phí), "
    "hoặc key OpenAI hay Google Gemini nếu đã có; hoặc vào trang Công cụ bấm cài \"Bộ nghe offline\" "
    "để nghe ngay trên máy, không cần key. Xong là gửi tin thoại dùng được ngay. "
    "Trong lúc chờ thì nhờ họ gõ chữ. Nếu đang đóng vai người thật nói với khách thì CHỈ nhờ "
    "họ gõ chữ, đừng nhắc gì tới API key hay dashboard.]")


# Dòng mở đầu khối tin thoại đã nghe thành chữ, DÙNG CHUNG mọi kênh. Là hằng số vì
# `telegram_bot._caption_command_text` phải nhận ra khối này để đừng cắt mất câu vừa nghe
# (khối thoại nhiều dòng, khác marker file đính kèm chỉ có một dòng).
MARK_THOAI = "[Tin THOẠI"


def khoi_thoai(nghe, kenh):
    """Câu đã nghe + một dòng dặn ở trên, dạng đưa thẳng vào lượt chat.

    Vì sao có dòng dặn: Whisper vẫn nghe nhầm, và một câu nghe nhầm đi thẳng ra hành động
    thật (gửi tin, đăng bài, đặt lịch, tiêu tiền) là loại sai không rút lại được. Đọc lại
    câu nghe được TRƯỚC khi làm là chỗ duy nhất người dùng bắt lỗi được.
    """
    dan = (MARK_THOAI + f" qua {kenh}. Javis đã nghe thành chữ (có thể nhầm vài từ) - câu ở "
           "dưới. Cứ làm theo như user gõ tay. Nếu việc sắp làm có tác động RA NGOÀI (gửi "
           "tin, đăng bài, đặt lịch, tiêu tiền, sửa file) thì mở đầu bằng một dòng "
           "\"Mình nghe: ...\" rồi hỏi xác nhận trước khi làm.]")
    return dan + "\n" + str(nghe or "").strip()


def _mb(n):
    return round(n / (1024 * 1024), 1)


def loi_thanh_dong(ly_do, chi_tiet=""):
    """Mã lỗi -> một dòng cho engine. Nội dung là LỜI DẶN Javis nói gì, không phải câu nói sẵn:
    kênh nào cũng đi qua engine nên giọng vẫn hợp ngữ cảnh (chủ hay khách, tiếng Việt hay không).
    """
    if ly_do == "thieu_key":
        return _HD_THIEU_KEY
    if ly_do == "qua_lon":
        return ("[Người dùng gửi một tin thoại quá dài để Javis nghe " + chi_tiet + ". "
                "Nhờ họ thu ngắn lại hoặc gõ chữ.]")
    if ly_do == "khong_nghe_ro":
        return ("[Người dùng gửi tin thoại nhưng Javis nghe không ra chữ nào (có thể im lặng "
                "hoặc quá ồn). Nhờ họ thu lại gần micro hơn, hoặc gõ chữ.]")
    return ("[Người dùng gửi tin thoại nhưng Javis nghe hỏng: " + (chi_tiet or "lỗi không rõ") +
            ". Nhờ họ gõ chữ, và báo là chỗ nghe giọng đang trục trặc.]")


async def groq_nghe(data, ten_file, api_key, model="", ngon_ngu=None, hotwords=""):
    """Chuyển bytes âm thanh thành chữ. Trả dict:

        {"ok": True,  "text": "...", "model": "..."}
        {"ok": False, "ly_do": "thieu_key|rong|qua_lon|khong_nghe_ro|loi", "noi_voi_javis": "..."}

    `hotwords` là tham số `prompt` của Whisper: một danh sách tên riêng (hotwords) để nó ưu tiên
    chép đúng chính tả "Javis", tên công cụ, tên dự án thay vì từ gần âm ("David"). Chỗ gọi
    lấy từ `nghe_sua.goi_y_whisper(nghe_sua.tu_vung(cfg))`; rỗng thì không gửi.

    `ngon_ngu` gợi ý cho Whisper. Ba giá trị có ý nghĩa KHÁC NHAU, đừng gộp:
      None  -> chưa ai chốt, lấy `STT_MAC_DINH` ("vi"). Giữ hành vi cũ cho mọi chỗ gọi chưa
               truyền gì: câu tiếng Việt ngắn không có gợi ý hay bị Whisper đoán nhầm sang
               tiếng khác rồi DỊCH luôn, ra một câu không ai gõ bao giờ.
      ""    -> cố ý KHÔNG gợi ý, để Whisper tự dò. Dùng khi ngôn ngữ trả lời đang là "auto"
               và chưa có căn cứ nào - ép "vi" lúc đó là chủ động làm hỏng tiếng nước ngoài.
      "en"  -> gợi ý đích danh.
    """
    return await _api_nghe(GROQ_STT_URL, "groq", data, ten_file, api_key, model or STT_MODEL_MAC_DINH,
                           ngon_ngu, hotwords)


# OpenAI ear (0.231.0). gpt-4o-transcribe is a language model that listens, so a Vietnamese sentence with English
# product names in it ("mở Claude Code", "hỏi ChatGPT") keeps both languages instead of spelling the English part out
# in Vietnamese sounds the way Whisper does. Same endpoint shape as Groq (OpenAI-compatible), same `prompt` hint.
OPENAI_STT_URL = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_STT_MODEL = "gpt-4o-transcribe"


async def openai_nghe(data, ten_file, api_key, model="", ngon_ngu=None, hotwords=""):
    """Same contract as `groq_nghe`, on OpenAI's transcription endpoint."""
    return await _api_nghe(OPENAI_STT_URL, "openai", data, ten_file, api_key, model or OPENAI_STT_MODEL,
                           ngon_ngu, hotwords)


async def _api_nghe(url, ten, data, ten_file, api_key, mdl, ngon_ngu, hotwords):
    if not api_key:
        return {"ok": False, "ly_do": "thieu_key", "noi_voi_javis": loi_thanh_dong("thieu_key")}
    if not data:
        return {"ok": False, "ly_do": "rong", "noi_voi_javis": loi_thanh_dong("loi", "file rỗng")}
    if len(data) > MAX_STT_MB * 1024 * 1024:
        ct = f"({_mb(len(data))}MB, trần {MAX_STT_MB}MB)"
        return {"ok": False, "ly_do": "qua_lon", "noi_voi_javis": loi_thanh_dong("qua_lon", ct)}

    form = {"model": mdl, "response_format": "json"}
    goi_y = STT_MAC_DINH if ngon_ngu is None else ngon_ngu
    if goi_y:
        form["language"] = goi_y
    if hw := str(hotwords or "").strip():
        form["prompt"] = hw[:600]     # Whisper chỉ giữ ~224 token cuối; dài hơn là vô ích
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(STT_TIMEOUT)) as c:
            r = await c.post(url,
                             headers={"Authorization": f"Bearer {api_key}"},
                             data=form,
                             files={"file": (ten_file or "voice.ogg", data)})
        d = {}
        try:
            d = r.json()
        except Exception:
            pass
        if r.status_code != 200:
            # Groq trả lý do thật trong body; đó là thứ đáng đọc chứ không phải mã HTTP trơn.
            ly = ((d.get("error") or {}).get("message") if isinstance(d.get("error"), dict)
                  else d.get("error")) or f"{ten} HTTP {r.status_code}"
            print(f"[stt {ten}] {ly}", file=sys.stderr)
            return {"ok": False, "ly_do": "loi", "noi_voi_javis": loi_thanh_dong("loi", str(ly)[:200])}
        # Lọc câu bịa TRƯỚC khi trả: lọc xong rỗng thì đúng nghĩa là không nghe được gì, đi
        # chung một đường với im lặng thật để chỗ gọi chỉ phải xử một trường hợp.
        text = loc_ao_giac(d.get("text"))
        if text and la_lap_loi_moi(text, form.get("prompt")):
            text = ""
        if not text:
            return {"ok": False, "ly_do": "khong_nghe_ro",
                    "noi_voi_javis": loi_thanh_dong("khong_nghe_ro")}
        return {"ok": True, "text": text, "model": mdl}
    except Exception as e:
        loi = f"{type(e).__name__}: {e}"
        print(f"[stt {ten}] {loi}", file=sys.stderr)
        return {"ok": False, "ly_do": "loi", "noi_voi_javis": loi_thanh_dong("loi", loi[:200])}


# ============================================================
# More ears (0.435.0): Gemini, and a chain that tries every ear the owner has
# ============================================================
# Owner, 2026-11-01: "anh muốn không cần groq mà vẫn nghe được", then "làm cả đường 1 và 2 luôn nhé, để không dùng
# được cái này thì dùng cái khác". Until this release a voice message or a video's sound was heard by Groq only.
# Now `listen_any` tries, in order: Groq, OpenAI, Gemini (keys from the Models page), then the offline Whisper the
# owner installed from the Tools page (`local_stt`). An ear that is missing or fails hands over to the next one.
GEMINI_STT_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_STT_MODEL = "gemini-2.5-flash"     # takes audio input; fast and cheap
GEMINI_MAX_MB = 18                        # inline audio rides in a request capped at 20MB
_GEMINI_MIME = {".mp3": "audio/mp3", ".wav": "audio/wav", ".ogg": "audio/ogg", ".oga": "audio/ogg",
                ".opus": "audio/ogg", ".flac": "audio/flac", ".aac": "audio/aac", ".aiff": "audio/aiff"}
_GEMINI_PROMPT = ("Chép lại NGUYÊN VĂN lời nói trong đoạn âm thanh này thành chữ, đúng ngôn ngữ người nói dùng. "
                  "Chỉ trả về phần chữ chép lại: không chào, không giải thích, không tóm tắt, không dịch. "
                  "Không có lời nói nào nghe được thì trả về đúng một chuỗi rỗng.")

# A failure that another ear may well fix (no key, the vendor down, quota, a file one ear cannot take).
# "khong_nghe_ro" is not one: silence stays silence whoever listens.
_TRY_NEXT = ("thieu_key", "loi", "qua_lon")


async def _as_mp3(data: bytes, ten_file: str) -> bytes:
    """`data` re-encoded as a small mono mp3 by ffmpeg, or b"" when that is not possible.

    For an audio format Gemini does not take (Zalo's .m4a, a browser's .webm). Uses files, not pipes: an .m4a often
    keeps its index at the end, which ffmpeg cannot read from a pipe."""
    import asyncio
    import os
    import shutil
    import tempfile
    import winproc
    if not shutil.which("ffmpeg"):
        return b""
    ext = os.path.splitext(str(ten_file or ""))[1][:8] or ".bin"
    with tempfile.TemporaryDirectory(prefix="javis-stt-") as d:
        src, dst = os.path.join(d, "in" + ext), os.path.join(d, "out.mp3")
        with open(src, "wb") as f:
            f.write(data)
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", dst,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            **winproc.kwargs_no_window())
        try:
            await asyncio.wait_for(proc.wait(), 120)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return b""
        if proc.returncode != 0 or not os.path.exists(dst):
            return b""
        with open(dst, "rb") as f:
            return f.read()


async def gemini_nghe(data, ten_file, api_key, model="", ngon_ngu=None, hotwords=""):
    """Same contract as `groq_nghe`, with a Gemini API key: the model is asked to write down what is said."""
    import base64
    import os
    if not api_key:
        return {"ok": False, "ly_do": "thieu_key", "noi_voi_javis": loi_thanh_dong("thieu_key")}
    if not data:
        return {"ok": False, "ly_do": "rong", "noi_voi_javis": loi_thanh_dong("loi", "file rỗng")}
    mime = _GEMINI_MIME.get(os.path.splitext(str(ten_file or "").lower())[1], "")
    if not mime:
        data = await _as_mp3(data, ten_file)
        mime = "audio/mp3"
        if not data:
            return {"ok": False, "ly_do": "loi",
                    "noi_voi_javis": loi_thanh_dong("loi", "Gemini không nhận định dạng âm thanh này")}
    if len(data) > GEMINI_MAX_MB * 1024 * 1024:
        ct = f"({_mb(len(data))}MB, trần {GEMINI_MAX_MB}MB)"
        return {"ok": False, "ly_do": "qua_lon", "noi_voi_javis": loi_thanh_dong("qua_lon", ct)}
    mdl = model or GEMINI_STT_MODEL
    goi_y = STT_MAC_DINH if ngon_ngu is None else ngon_ngu
    prompt = _GEMINI_PROMPT
    if goi_y:
        prompt += f" Ngôn ngữ nhiều khả năng là: {goi_y}."
    if hw := str(hotwords or "").strip():
        prompt += " Các tên riêng có thể xuất hiện, hãy viết đúng chính tả: " + hw[:600]
    body = {"contents": [{"role": "user", "parts": [
                {"text": prompt}, {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}]}],
            "generationConfig": {"temperature": 0, "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(STT_TIMEOUT)) as c:
            r = await c.post(GEMINI_STT_URL.format(model=mdl), headers={"x-goog-api-key": api_key}, json=body)
        d = {}
        try:
            d = r.json()
        except Exception:
            pass
        if r.status_code != 200:
            ly = ((d.get("error") or {}).get("message") if isinstance(d.get("error"), dict) else "") \
                or f"gemini HTTP {r.status_code}"
            print(f"[stt gemini] {ly}", file=sys.stderr)
            return {"ok": False, "ly_do": "loi", "noi_voi_javis": loi_thanh_dong("loi", str(ly)[:200])}
        parts = (((d.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        text = loc_ao_giac(" ".join(str(p.get("text") or "") for p in parts if isinstance(p, dict)).strip())
        if text.strip() in ('""', "''"):
            text = ""
        if not text:
            return {"ok": False, "ly_do": "khong_nghe_ro", "noi_voi_javis": loi_thanh_dong("khong_nghe_ro")}
        return {"ok": True, "text": text, "model": mdl}
    except Exception as e:
        loi = f"{type(e).__name__}: {e}"
        print(f"[stt gemini] {loi}", file=sys.stderr)
        return {"ok": False, "ly_do": "loi", "noi_voi_javis": loi_thanh_dong("loi", loi[:200])}


async def listen_any(data, ten_file, keys: dict, ngon_ngu=None, hotwords="", groq_model="", local=None):
    """Try every ear the owner has until one hears something. Same contract as `groq_nghe`, plus `ear` on success.

    `keys`: {"groq": ..., "openai": ..., "gemini": ...} (empty = that ear is skipped). `local`: an async
    (bytes, file name, language) -> dict like `groq_nghe`, or None when the offline Whisper is not installed.
    When no ear exists at all the answer is the "thieu_key" line, which names every way to get one."""
    keys = keys or {}
    ears = []
    if keys.get("groq"):
        ears.append(("groq", lambda: groq_nghe(data, ten_file, keys["groq"], groq_model, ngon_ngu, hotwords)))
    if keys.get("openai"):
        ears.append(("openai", lambda: openai_nghe(data, ten_file, keys["openai"], "", ngon_ngu, hotwords)))
    if keys.get("gemini"):
        ears.append(("gemini", lambda: gemini_nghe(data, ten_file, keys["gemini"], "", ngon_ngu, hotwords)))
    if local is not None:
        ears.append(("local", lambda: local(data, ten_file, STT_MAC_DINH if ngon_ngu is None else ngon_ngu)))
    if not ears:
        return {"ok": False, "ly_do": "thieu_key", "noi_voi_javis": loi_thanh_dong("thieu_key")}
    res = {}
    for name, run in ears:
        res = await run()
        if res.get("ok"):
            return dict(res, ear=name)
        if res.get("ly_do") not in _TRY_NEXT:
            return dict(res, ear=name)
        print(f"[stt] tai {name} hỏng ({res.get('ly_do')}), thử tai kế tiếp", file=sys.stderr)
    return res
