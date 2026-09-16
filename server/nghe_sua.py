"""Sửa chữ NGHE NHẦM theo ngữ cảnh, trước khi câu nói đi vào bộ não.

Vì sao có lớp này (0.59.24): người dùng nói lẫn tiếng Việt và tiếng Anh, và máy nghe (Web
Speech của trình duyệt lẫn Whisper) chép từ tiếng Anh thành từ gần âm: "Javis" thành "David",
"Jarvis", "Gia vít", "Ja vịt"; tên công cụ, tên dự án cũng cùng số phận. Câu đến bộ não mang
từ sai đó, Javis trả lời bám nghĩa đen ("David là ai?") nghe rất buồn cười. Sửa ở tầng máy
nghe thì không được: Web Speech không nhận từ điển riêng, còn Whisper chỉ nhận một gợi ý.

Cách làm, ba lớp bổ trợ nhau:
  1. `goi_y_whisper` - đưa bộ từ vựng vào tham số `prompt` của Whisper để nó ưu tiên viết
     đúng những tên này (hotwords). Chỉ Groq Whisper có, Web Speech không.
  2. `sua` - so khớp MỜ THEO ÂM: mỗi từ (hoặc cặp từ, vì "Javis" hay bị tách thành "Gia vít")
     được rút về một khoá âm (bỏ dấu, gộp những âm máy nghe hay lẫn: j/gi/d/z, v/w, đuôi
     s/t/d) rồi so với khoá âm của từng từ trong bộ từ vựng. Trùng gần như hoàn toàn thì sửa ở
     mọi vị trí; trùng vừa phải thì CHỈ sửa khi từ đứng ở vị trí GỌI TÊN (đầu câu, trước "ơi",
     sau "hey"...), vì đó là chỗ người ta gọi trợ lý chứ không nói về ai khác.
  3. Bộ não giọng được dặn (voice_brain.SYSTEM_PROMPT) rằng câu đến từ máy nghe và phải hiểu
     theo ngữ cảnh. Những ca lớp 2 cố ý bỏ qua (xem `_NGOI_THU_BA`) trông cậy vào lớp này.

Ranh giới của lớp 2, phải giữ để không sửa bừa:
  - KHÔNG SỬA GÌ THÌ TRẢ LẠI Y NGUYÊN (cùng luật với stt.loc_ao_giac): ghép lại nguyên văn
    từng đoạn, không tách rồi nối bằng khoảng trắng.
  - Từ đứng sau "cho", "với", "của"... là đang nói về NGƯỜI THỨ BA ("nhắn cho David là...")
    thì để yên, kể cả khi trùng âm hoàn toàn. Thà sót một lần gọi tên còn hơn đổi tên bạn của
    người dùng thành tên trợ lý.
  - Từ trùng âm mà theo sau là một từ VIẾT HOA khác ("David Beckham") là tên riêng hai chữ,
    để yên.
  - Sửa xong chạy lại phải ra đúng chuỗi đó (idempotent), vì câu có thể đi qua lớp này hai lần
    (endpoint /stt rồi lại WebSocket).

Module này KHÔNG đọc settings: nhận chữ + bộ từ vựng, trả chữ. `tu_vung(cfg)` ở dưới chỉ là
hàm tiện ích rút bộ từ vựng từ settings cho chỗ gọi, để ba cửa nghe (mic dashboard, Telegram,
Zalo) dùng cùng một danh sách.
"""
import difflib
import re
import unicodedata

# Tên trợ lý luôn có mặt, không cần người dùng khai. Bộ từ vựng người dùng thêm nằm ở
# settings `voice.hotwords` (chuỗi, ngăn bằng dấu phẩy hoặc xuống dòng).
TU_VUNG_GOC = ("Javis",)
MAX_TU_VUNG = 60          # Whisper chỉ nhìn ~224 token cuối của prompt; hơn nữa là vô ích
MAX_GHEP = 3              # ghép tối đa 3 tiếng liền nhau làm một ứng viên ("Gia vít", "Open Router")

# Trùng âm từ mức này trở lên: sửa ở mọi vị trí (thực tế là trùng khoá âm hoàn toàn).
NGUONG_MOI_NOI = 0.95
# Trùng âm từ mức này trở lên: chỉ sửa khi đứng ở vị trí gọi tên.
NGUONG_GOI_TEN = 0.8
# Khoá âm ngắn hơn mức này chỉ được sửa khi trùng HOÀN TOÀN: "đặt" (dat) so với "davit" đã
# được 0,75, đủ để một câu lệnh bình thường mất chữ cuối.
KHOA_MIN_MO = 4

# Từ đứng TRƯỚC vị trí gọi tên: "hey Javis", "ok Javis", "này Javis", "cảm ơn Javis".
_MO_DAU = frozenset("""
hey hi hello ok okay alo alô này ê ơi à ừ ờ ừm um rồi thôi nào chào ơn xin cám cảm thanks thank
""".split())
# Từ đứng SAU vị trí gọi tên: "Javis ơi", "Javis à", "Javis này".
_KET_GOI = frozenset("ơi à ạ nhé nha này ei ê hey".split())
# Từ đứng trước cho biết đang nói về NGƯỜI THỨ BA, không phải gọi trợ lý.
_NGOI_THU_BA = frozenset("""
cho với của gặp tên ông bà chú cô bác cậu mợ dì thằng con
to with for from named mr mrs ms miss
""".split())
# Ranh giới câu trong đoạn ngăn cách giữa hai từ.
_RANH_CAU = re.compile(r"[.!?…\n,;:()\[\]\"“”]")
_TU = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.U)   # một "tiếng": chữ cái, không số

# Gộp những âm máy nghe hay lẫn. Chạy THEO THỨ TỰ: cặp chữ trước, chữ đơn sau.
_AM_DOI = (("gi", "d"), ("ph", "f"), ("th", "t"), ("tr", "c"), ("ch", "c"), ("kh", "k"),
           ("ng", "n"), ("nh", "n"), ("qu", "k"), ("gh", "g"), ("ck", "k"), ("sh", "s"),
           ("ee", "i"), ("ea", "i"), ("oo", "u"), ("ay", "e"), ("ai", "e"), ("ey", "e"))
_AM_DON = str.maketrans({"j": "d", "z": "d", "w": "v", "c": "k", "q": "k", "x": "s",
                         "y": "i", "h": ""})
_DUOI_TAC = re.compile(r"[tdskpc]+$")      # đuôi tắc/xát máy nghe hay đổi cho nhau: -s/-t/-d
_R_TRUOC_PHU_AM = re.compile(r"r(?=[^aeiou]|$)")


def bo_dau(s: str) -> str:
    """Bỏ dấu tiếng Việt, hạ chữ thường. `đ` không tách được bằng NFD nên đổi tay."""
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d")


def khoa_am(tu: str) -> str:
    """Rút một từ (hay cụm đã ghép liền) về khoá âm để so mờ.

    Ví dụ: Javis, David, Davis, Jarvis, Gia vít, Ja vịt, Đa vít -> đều là "davit".
    """
    s = re.sub(r"[^a-z]", "", bo_dau(tu))
    if not s:
        return ""
    for a, b in _AM_DOI:
        s = s.replace(a, b)
    s = s.translate(_AM_DON)
    s = _R_TRUOC_PHU_AM.sub("", s)             # "jarvis" -> "javis": r trước phụ âm câm
    s = re.sub(r"(.)\1+", r"\1", s)            # chữ kép -> đơn
    s = _DUOI_TAC.sub("t", s) if _DUOI_TAC.search(s) else s
    return s


def do_giong(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def tach_tu_vung(chuoi) -> list:
    """Chuỗi người dùng gõ ở ô cài đặt -> danh sách từ, giữ thứ tự, bỏ trùng (không phân biệt hoa thường)."""
    ra, da = [], set()
    for phan in re.split(r"[,\n;]+", str(chuoi or "")):
        t = " ".join(phan.split())
        if not t or len(t) > 40:
            continue
        k = t.lower()
        if k in da:
            continue
        da.add(k)
        ra.append(t)
    return ra


def tu_vung(cfg: dict) -> list:
    """Bộ từ vựng hiệu lực: tên trợ lý + từ người dùng khai ở `voice.hotwords`."""
    v = (cfg or {}).get("voice") or {}
    ra = list(TU_VUNG_GOC)
    da = {t.lower() for t in ra}
    for t in tach_tu_vung(v.get("hotwords")):
        if t.lower() not in da:
            da.add(t.lower())
            ra.append(t)
    return ra[:MAX_TU_VUNG]


def goi_y_whisper(tv) -> str:
    """Tham số `prompt` cho Whisper: một danh sách tên, ngăn bằng phẩy, khép bằng dấu chấm.

    Whisper coi prompt là "đoạn trước" của bản ghi và bắt chước cách viết trong đó, nên chỉ cần
    tên xuất hiện là nó ưu tiên chép đúng chính tả ấy. Cố ý KHÔNG viết thành câu ("Nói chuyện
    với Javis") vì gặp im lặng Whisper hay chép lại chính câu mồi.
    """
    ds = [t for t in (tv or []) if t]
    return (", ".join(ds) + ".") if ds else ""


def _ung_vien(toks, i, n, s):
    """Ghép n tiếng liền nhau từ vị trí i, chỉ khi giữa chúng thuần khoảng trắng."""
    if i + n > len(toks):
        return None
    for k in range(i, i + n - 1):
        if not s[toks[k].end():toks[k + 1].start()].isspace():
            return None
    return s[toks[i].start():toks[i + n - 1].end()]


def _o_vi_tri_goi_ten(toks, i, n, s) -> bool:
    truoc = toks[i - 1] if i > 0 else None
    sau = toks[i + n] if i + n < len(toks) else None
    if truoc is None:
        return True
    khoang_truoc = s[truoc.end():toks[i].start()]
    if _RANH_CAU.search(khoang_truoc) or bo_dau(truoc.group(0)) in {bo_dau(x) for x in _MO_DAU}:
        return True
    if sau is None:
        return True
    khoang_sau = s[toks[i + n - 1].end():sau.start()]
    if _RANH_CAU.search(khoang_sau):
        return True
    return sau.group(0).lower() in _KET_GOI


def _ngoi_thu_ba(toks, i, s) -> bool:
    if i == 0:
        return False
    truoc = toks[i - 1]
    if _RANH_CAU.search(s[truoc.end():toks[i].start()]):
        return False
    return truoc.group(0).lower() in _NGOI_THU_BA


def _ten_rieng_hai_chu(toks, i, n, s, term) -> bool:
    """"David Beckham": từ sau viết hoa, dính liền bằng khoảng trắng, mà từ vựng chỉ một tiếng."""
    if " " in term or i + n >= len(toks):
        return False
    sau = toks[i + n]
    if not s[toks[i + n - 1].end():sau.start()].isspace():
        return False
    w = sau.group(0)
    return w[:1].isupper() and w.lower() not in _KET_GOI


def sua(text, tv) -> str:
    """Sửa những từ nghe nhầm thành từ trong bộ từ vựng `tv`. Không có gì để sửa thì trả y nguyên."""
    s = str(text or "")
    ds = [(t, khoa_am(t), len(t.split())) for t in (tv or []) if t and khoa_am(t)]
    if not s or not ds:
        return s
    toks = list(_TU.finditer(s))
    if not toks:
        return s
    dem = frozenset(bo_dau(x) for x in (_MO_DAU | _KET_GOI | _NGOI_THU_BA))

    def _diem_don(j):
        """Điểm cao nhất của RIÊNG tiếng thứ j so với cả bộ từ vựng."""
        k = khoa_am(toks[j].group(0))
        return max((do_giong(k, kt) for _, kt, _ in ds), default=0.0) if len(k) >= 3 else 0.0

    ra, pos, i, doi = [], 0, 0, False
    while i < len(toks):
        # Xét mọi cách ghép n tiếng từ vị trí i, lấy cách TRÙNG NHẤT (hoà thì cụm ngắn hơn).
        # Duyệt theo thứ tự "n dài trước" rồi lấy khớp đầu tiên là sai: "hey David" ghép hai
        # tiếng trùng 0,91 thắng "David" một tiếng trùng 1,0, và cả "hey" bị nuốt vào tên.
        best = None      # (d, n, term)
        for n in range(1, min(MAX_GHEP, len(toks) - i) + 1):
            uv = _ung_vien(toks, i, n, s)
            if uv is None:
                break
            k = khoa_am(uv)
            if len(k) < 3:
                continue
            if n >= 2:
                # Cụm ghép không được chứa tiếng đệm ("hey", "ơi", "cho"), và không tiếng nào
                # trong cụm tự nó trùng tốt hơn cả cụm: "ơn David" 0,83 thua "David" 1,0.
                if any(bo_dau(toks[j].group(0)) in dem for j in range(i, i + n)):
                    continue
            for term, kt, so_tieng in ds:
                if n > so_tieng + 1:
                    continue           # không ghép quá số tiếng của từ vựng (+1 cho ca bị tách)
                d = 1.0 if uv.lower() == term.lower() else do_giong(k, kt)
                if d < 1.0 and len(k) < KHOA_MIN_MO:
                    continue
                if n >= 2 and any(_diem_don(j) >= d for j in range(i, i + n)):
                    continue
                if best is None or d > best[0]:
                    best = (d, n, term, uv)
        if best is None or best[0] < NGUONG_GOI_TEN:
            i += 1
            continue
        d, n, term, uv = best
        if uv.lower() == term.lower():
            i += n                     # đã đúng sẵn: khoá cả cụm, khỏi sửa từng tiếng bên trong
            continue
        if (_ngoi_thu_ba(toks, i, s) or _ten_rieng_hai_chu(toks, i, n, s, term)
                or (d < NGUONG_MOI_NOI and not _o_vi_tri_goi_ten(toks, i, n, s))):
            i += 1
            continue
        dau, cuoi = toks[i].start(), toks[i + n - 1].end()
        ra.append(s[pos:dau])
        ra.append(term)
        pos = cuoi
        doi = True
        i += n
    if not doi:
        return s
    ra.append(s[pos:])
    return "".join(ra)
