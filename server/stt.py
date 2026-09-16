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


GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
STT_MAC_DINH = "vi"   # gợi ý khi chỗ gọi không chốt gì; "" ở chỗ gọi = để Whisper tự dò

# Model rẻ và nhanh nhất trong họ Whisper của Groq, tiếng Việt nghe được. Đổi được qua tham số.
STT_MODEL_MAC_DINH = "whisper-large-v3-turbo"
MAX_STT_MB = 24          # Groq chặn ở 25MB; chừa biên cho phần multipart bọc ngoài
STT_TIMEOUT = 120.0      # tin thoại dài vài phút vẫn phải kịp, mạng VPS có lúc chậm

# Câu Javis nói khi chưa đấu key. Để ở đây (không rải trong từng kênh) vì mọi kênh nói CÙNG
# một chuyện: thiếu đúng một thứ, và thứ đó nằm ở đúng một chỗ trong dashboard.
_HD_THIEU_KEY = (
    "[Người dùng vừa gửi TIN THOẠI. Javis chưa nghe được vì chưa đấu API key của Groq - "
    "đó là thứ chuyển giọng nói thành chữ. Hãy nói với họ: muốn ra lệnh bằng ghi âm thì vào "
    "trang Models trong dashboard, mục nhà cung cấp Groq (API), dán API key lấy ở "
    "console.groq.com rồi lưu lại; xong là gửi tin thoại dùng được ngay, không cần cài gì thêm. "
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
    if not api_key:
        return {"ok": False, "ly_do": "thieu_key", "noi_voi_javis": loi_thanh_dong("thieu_key")}
    if not data:
        return {"ok": False, "ly_do": "rong", "noi_voi_javis": loi_thanh_dong("loi", "file rỗng")}
    if len(data) > MAX_STT_MB * 1024 * 1024:
        ct = f"({_mb(len(data))}MB, trần {MAX_STT_MB}MB)"
        return {"ok": False, "ly_do": "qua_lon", "noi_voi_javis": loi_thanh_dong("qua_lon", ct)}

    mdl = model or STT_MODEL_MAC_DINH
    form = {"model": mdl, "response_format": "json"}
    goi_y = STT_MAC_DINH if ngon_ngu is None else ngon_ngu
    if goi_y:
        form["language"] = goi_y
    if hw := str(hotwords or "").strip():
        form["prompt"] = hw[:600]     # Whisper chỉ giữ ~224 token cuối; dài hơn là vô ích
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(STT_TIMEOUT)) as c:
            r = await c.post(GROQ_STT_URL,
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
                  else d.get("error")) or f"Groq HTTP {r.status_code}"
            print(f"[stt groq] {ly}", file=sys.stderr)
            return {"ok": False, "ly_do": "loi", "noi_voi_javis": loi_thanh_dong("loi", str(ly)[:200])}
        # Lọc câu bịa TRƯỚC khi trả: lọc xong rỗng thì đúng nghĩa là không nghe được gì, đi
        # chung một đường với im lặng thật để chỗ gọi chỉ phải xử một trường hợp.
        text = loc_ao_giac(d.get("text"))
        if not text:
            return {"ok": False, "ly_do": "khong_nghe_ro",
                    "noi_voi_javis": loi_thanh_dong("khong_nghe_ro")}
        return {"ok": True, "text": text, "model": mdl}
    except Exception as e:
        loi = f"{type(e).__name__}: {e}"
        print(f"[stt groq] {loi}", file=sys.stderr)
        return {"ok": False, "ly_do": "loi", "noi_voi_javis": loi_thanh_dong("loi", loi[:200])}
