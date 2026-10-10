"""Phiên âm từ tiếng Anh ra âm tiết tiếng Việt: "GitHub Actions" -> "gít hắp ác sừn".

Hai chỗ dùng (0.64.68):
  1. ĐỌC (/tts): câu trả lời tiếng Việt có xen từ tiếng Anh. Giọng Việt đọc "GitHub" theo mặt
     chữ rất khó nghe; giọng đa ngôn ngữ thì đọc tiếng Việt lơ lớ. Chủ dự án chốt 27/09: đọc từ
     tiếng Anh THEO KIỂU NGƯỜI VIỆT NÓI ("Micro" là "mi cờ rô", "Emma" là "em ma", "GitHub
     Action" là "git hắp ác sừn"), cả câu MỘT giọng người dùng đã chọn. Bản 0.64.67 ghép hai
     giọng (đoạn Việt Hoài My, đoạn Anh Emma) đã bị bỏ: nghe lúc Anh lúc Việt thấy sai sai, và
     người chọn giọng khác vẫn nghe ra Hoài My.
  2. NGHE (voice_brain.safe_transcript_rewrite): máy nghe chép "GitHub Actions" thành "huyết
     áp Action", bộ não giọng viết lại đúng nhưng chốt kiểm tra so âm theo MẶT CHỮ tiếng Anh
     nên chặn ("action" viết một đằng đọc một nẻo). So theo cách người Việt đọc từ đó thì khớp.

Cách phiên âm, theo thứ tự ưu tiên:
  - `TU_DIEN`: từ hay gặp, viết sẵn theo đúng cách người Việt quen nói ("email" là "i meo").
  - Chữ viết tắt toàn hoa đọc từng chữ cái kiểu Việt: VPS là "vi pi ét".
  - Từ điển phát âm CMU (dữ liệu giấy phép BSD của Carnegie Mellon, file trong
    data_phien_am/, KHÔNG dùng gói PyPI `cmudict` vì phần code của gói đó là GPL): ra chuỗi âm
    vị ARPAbet rồi đổi sang âm tiết Việt. Từ ghép viết hoa giữa (OpenRouter) tách ra tra từng
    phần.
  - Không có trong từ điển: đoán âm vị theo mặt chữ (luật đơn giản), rồi đổi như trên.

Đổi âm vị sang âm tiết Việt: mỗi nguyên âm là một âm tiết; phụ âm cuối chỉ giữ loại tiếng Việt
có (p t c ch m n ng nh); cụm phụ âm đầu tách thành âm tiết "cờ" như người Việt đọc ("micro" là
"mi cờ rô"); thanh: âm tiết tắc (đuôi p t c ch) mang dấu sắc, âm lướt và âm chêm mang dấu
huyền ("sừn", "cờ"), còn lại thanh ngang.

Module này không gọi mạng và không đọc settings.
"""
from __future__ import annotations

import bisect
import gzip
import re
import threading
import unicodedata
from array import array
from pathlib import Path

# ---------------------------------------------------------------------------------------
# Nhận ra từ tiếng Anh trong câu tiếng Việt
# ---------------------------------------------------------------------------------------
# Âm đầu tiếng Việt viết bằng chữ ASCII (đ đã có dấu nên không cần). Dài trước ngắn sau.
_AM_DAU = ("ngh", "ng", "nh", "ch", "gh", "gi", "kh", "ph", "qu", "th", "tr",
           "b", "c", "d", "g", "h", "k", "l", "m", "n", "p", "r", "s", "t", "v", "x", "")
# Vần tiếng Việt viết thuần ASCII (không mũ, không móc, không thanh).
_VAN = frozenset("""
a ac ach ai am an ang anh ao ap at au ay
e ec em en eng eo ep et
i ia ich im in inh ip it iu
o oa oac oach oai oam oan oang oanh oao oap oat oay oc oe oen oeo oet oi om on ong ooc oong op ot
u ua uc ui um un ung up ut uy uya uych uyn uynh uyp uyt
y
""".split())
# Từ tiếng Anh ngắn trùng khuôn âm tiết Việt mà tiếng Việt thật luôn viết có dấu ("chát",
# "tốp", "ít"). KHÔNG đưa vào đây những từ tiếng Việt không dấu: "to" (chữ to), "in" (in hoá
# đơn), "no" (ăn no), "so" (so sánh), "do" (do đó), "pin" (sạc pin).
_ANH_NGAN = frozenset("chat top tip map cap ping bin hi ok up at it by".split())
_TU = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.U)
_CO_DAU = re.compile(r"[^\x00-\x7f]")


def _la_am_tiet_viet(w: str) -> bool:
    s = w.lower()
    return any(s.startswith(d) and s[len(d):] in _VAN for d in _AM_DAU)


def la_tu_tieng_anh(w: str) -> bool:
    """Một từ (chỉ chữ cái) có phải tiếng Anh không. Có dấu tiếng Việt thì chắc chắn không."""
    if not w or not w.isascii():
        return False
    if len(w) >= 2 and w.isupper():
        return True                          # VPS, API, MCP
    if any(c.isupper() for c in w[1:]):
        return True                          # GitHub, OpenRouter, iPhone
    if w.lower() in _ANH_NGAN:
        return True
    return not _la_am_tiet_viet(w)


def co_tieng_viet(text: str) -> bool:
    """Câu có ít nhất một từ tiếng Việt CÓ DẤU (câu trả lời tiếng Việt luôn có)."""
    return any(_CO_DAU.search(m.group(0)) for m in _TU.finditer(str(text or "")))


# ---------------------------------------------------------------------------------------
# Từ điển viết sẵn và chữ cái
# ---------------------------------------------------------------------------------------
# Cách người Việt quen nói. Khoá chữ thường. Ưu tiên hơn từ điển CMU: CMU cho cách đọc
# ĐÚNG tiếng Anh, còn đây là cách đọc QUEN TAI người Việt ("model" là "mô đồ", không phải
# "ma đồ"). Thêm từ ở đây khi nghe thấy đọc lạ.
TU_DIEN = {
    "github": "ghít hắp", "action": "ác sừn", "actions": "ác sừn", "micro": "mi cờ rô",
    "emma": "em ma", "email": "i meo", "emails": "i meo", "gmail": "gi meo",
    "google": "gu gồ", "facebook": "phây búc", "youtube": "diu túp", "tiktok": "tíc tóc",
    "zalo": "da lô", "telegram": "te lơ gam", "javis": "gia vít", "jarvis": "gia vít",
    "chatgpt": "chát gi pi ti", "openai": "ô pừn ây ai", "claude": "cờ lốt",
    "gemini": "giem mi nai", "groq": "gờ rốc", "deepseek": "đíp xíc", "grok": "gờ rốc", "codex": "cô đéc",
    "antigravity": "en ti gra vi ti", "hostinger": "hốt tinh gơ",
    "composio": "com pô si ô", "anthropic": "en thờ rô pích", "shopify": "sốp pi phai",
    "webflow": "quép phờ lâu", "watchtower": "oát tao ơ", "openrouter": "ô pừn rao tờ", "ollama": "ô la ma",
    "pancake": "pen kếch", "webcake": "quép kếch", "botcake": "bót kếch",
    "model": "mô đồ", "models": "mô đồ", "server": "sơ vờ", "dashboard": "đát bót",
    "workflow": "uốc phờ lâu", "workflows": "uốc phờ lâu", "deploy": "đi pờ lôi",
    "commit": "cơ mít", "push": "pút", "pull": "pun", "request": "ri quét", "merge": "mơ giờ",
    "main": "mên", "branch": "bờ ren", "bug": "bắc", "log": "lóc", "logs": "lóc",
    "token": "tô cừn", "tokens": "tô cừn", "prompt": "pờ rôm", "agent": "ây giần",
    "agents": "ây giần", "skill": "sờ kiu", "skills": "sờ kiu", "test": "tét",
    "file": "phai", "files": "phai", "folder": "phôn đờ", "web": "quép", "website": "quép sai",
    "app": "áp", "apps": "áp", "online": "on lai", "offline": "óp lai", "ok": "ô kê",
    "okay": "ô kê", "video": "vi đi ô", "live": "lai", "livestream": "lai sờ trim",
    "inbox": "in bóc", "content": "con ten", "marketing": "ma két tinh", "ads": "át",
    "landing": "len đinh", "page": "pết", "iphone": "ai phôn", "windows": "uyn đâu",
    "mac": "mác", "linux": "li nút", "docker": "đốc cơ", "chrome": "cờ rôm",
    "plugin": "pờ lấc gin", "plugins": "pờ lấc gin", "hub": "hắp", "setup": "sét ắp",
    "update": "ắp đết", "upload": "ắp lốt", "download": "đao lốt", "link": "linh",
    "ai": "ây ai", "notion": "nâu sừn", "excel": "ếch xeo", "word": "uốt", "pdf": "pi đi ép",
    "kanban": "can ban", "loop": "lúp", "cron": "cờ ron", "webhook": "quép húc",
    "mcp": "em xi pi", "vps": "vi pi ét", "api": "ây pi ai",
}

# Tên chữ cái kiểu Việt cho chữ viết tắt.
CHU_CAI = {
    "a": "ây", "b": "bi", "c": "xi", "d": "đi", "e": "i", "f": "ép", "g": "gi", "h": "ết",
    "i": "ai", "j": "giây", "k": "cây", "l": "eo", "m": "em", "n": "en", "o": "âu", "p": "pi",
    "q": "kiu", "r": "a", "s": "ét", "t": "ti", "u": "diu", "v": "vi", "w": "đắp bờ liu",
    "x": "ích", "y": "oai", "z": "dét",
}

# ---------------------------------------------------------------------------------------
# Từ điển CMU: tra nhị phân trên khối byte đã giải nén, không dựng dict 124 nghìn khoá
# (dict Python cỡ đó ngốn vài chục MB trên VPS nhỏ).
# ---------------------------------------------------------------------------------------
_CMU_FILE = Path(__file__).parent / "data_phien_am" / "cmudict.txt.gz"
_cmu_lock = threading.Lock()
_cmu = None          # (bytes, array vị trí đầu dòng) | False khi không nạp được


def _nap_cmu():
    global _cmu
    if _cmu is not None:
        return _cmu
    with _cmu_lock:
        if _cmu is None:
            try:
                data = gzip.decompress(_CMU_FILE.read_bytes())
                dau = array("I", [0])
                i = data.find(b"\n")
                while i != -1 and i + 1 < len(data):
                    dau.append(i + 1)
                    i = data.find(b"\n", i + 1)
                _cmu = (data, dau)
            except Exception:
                _cmu = False
    return _cmu


def tra_cmu(tu: str):
    """Chuỗi âm vị ARPAbet (có số trọng âm) của một từ, hoặc None."""
    c = _nap_cmu()
    if not c:
        return None
    data, dau = c
    khoa = tu.lower().encode("ascii", "ignore")
    if not khoa:
        return None

    class _Cot:          # nhìn mảng vị trí như danh sách từ để bisect
        def __len__(self):
            return len(dau)

        def __getitem__(self, i):
            s = dau[i]
            return data[s:data.index(b"\t", s)]

    i = bisect.bisect_left(_Cot(), khoa)
    if i < len(dau):
        s = dau[i]
        tab = data.index(b"\t", s)
        if data[s:tab] == khoa:
            return data[tab + 1:data.index(b"\n", tab)].decode().split()
    return None


# ---------------------------------------------------------------------------------------
# Đoán âm vị theo mặt chữ, cho từ không có trong CMU. Thô nhưng đủ nghe ra từ.
# ---------------------------------------------------------------------------------------
_CHU_AM = [   # (mẫu chữ, âm vị) - dài trước ngắn sau
    ("tion", "SH AH0 N"), ("sion", "ZH AH0 N"), ("igh", "AY1"), ("ph", "F"), ("sh", "SH"),
    ("ch", "CH"), ("th", "TH"), ("ck", "K"), ("ng", "NG"), ("qu", "K W"), ("oo", "UW1"),
    ("ee", "IY1"), ("ea", "IY1"), ("ai", "EY1"), ("ay", "EY1"), ("ou", "AW1"), ("ow", "OW1"),
    ("oa", "OW1"), ("oi", "OY1"), ("oy", "OY1"), ("au", "AO1"), ("aw", "AO1"), ("er", "ER0"),
    ("ar", "AA1"), ("or", "AO1"), ("ir", "ER1"), ("ur", "ER1"),
    ("a", "AE1"), ("e", "EH1"), ("i", "IH1"), ("o", "AA1"), ("u", "AH1"), ("y", "IY0"),
    ("b", "B"), ("c", "K"), ("d", "D"), ("f", "F"), ("g", "G"), ("h", "HH"), ("j", "JH"),
    ("k", "K"), ("l", "L"), ("m", "M"), ("n", "N"), ("p", "P"), ("r", "R"), ("s", "S"),
    ("t", "T"), ("v", "V"), ("w", "W"), ("x", "K S"), ("z", "Z"),
]


def doan_am_vi(tu: str) -> list:
    s = re.sub(r"[^a-z]", "", tu.lower())
    if len(s) > 3 and s.endswith("e") and s[-2] not in "aeiouy":
        s = s[:-1]                           # e câm cuối từ
    ra, i = [], 0
    while i < len(s):
        if s[i] == "c" and i + 1 < len(s) and s[i + 1] in "eiy":
            ra.append("S")
            i += 1
            continue
        for mau, am in _CHU_AM:
            if s.startswith(mau, i):
                ra.extend(am.split())
                i += len(mau)
                break
        else:
            i += 1
    # Chỉ giữ một trọng âm chính: nguyên âm đầu tiên.
    thay, co = [], False
    for p in ra:
        if p[-1:].isdigit() and p[-1] != "0":
            p = p[:-1] + ("0" if co else "1")
            co = True
        thay.append(p)
    return thay


# ---------------------------------------------------------------------------------------
# Âm vị ARPAbet -> âm tiết tiếng Việt
# ---------------------------------------------------------------------------------------
_NGUYEN_AM = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY",
              "UH", "UW"}
_DAU_AM = {"B": "b", "CH": "ch", "D": "đ", "DH": "đ", "F": "ph", "G": "g", "HH": "h",
           "JH": "gi", "K": "c", "L": "l", "M": "m", "N": "n", "NG": "ng", "P": "p", "R": "r",
           "S": "s", "SH": "s", "T": "t", "TH": "th", "V": "v", "W": "", "Y": "d", "Z": "d",
           "ZH": "gi"}
# Phụ âm cuối tiếng Việt có: English -> chữ Việt. Không có trong bảng thì bỏ (cuối từ) hoặc
# đổi thành "t" (giữa từ, loại xát: "dashboard" là "đát bót").
_CUOI_AM = {"P": "p", "B": "p", "T": "t", "D": "t", "K": "c", "G": "c", "M": "m", "N": "n",
            "NG": "ng"}
_XAT = {"S", "Z", "SH", "ZH", "CH", "JH", "TH", "DH"}
_LAX = {"AE", "EH", "IH", "UH"}          # nguyên âm ngắn: có trọng âm thì nhân đôi phụ âm sau
_LUOT = {"AY", "OY", "AW", "EY", "OW"}   # nguyên âm đôi: đã có đuôi lướt, không nhận phụ âm cuối


def _nhan(vowel: str, stress: str, cuoi: str, am_dau: str) -> str:
    """Phần vần (chưa thanh) cho một nguyên âm ARPAbet."""
    lax_schwa = stress == "0" and vowel in ("AH", "ER")
    if vowel == "AH":
        return ("ư" if cuoi else "ơ") if lax_schwa else ("ă" if cuoi else "a")
    if vowel == "ER":
        return "ơ"
    if vowel in ("AA", "AE"):
        return "a"
    if vowel == "AO":
        return "o"
    if vowel == "AW":
        return "ao"
    if vowel == "AY":
        return "ai"
    if vowel == "EH":
        return "e"
    if vowel == "EY":
        return "ây"
    if vowel in ("IH", "IY"):
        return "i"
    if vowel == "OW":
        return "ô"
    if vowel == "OY":
        return "ôi"
    return "u"                                  # UH, UW


_THANH = {"sac": "́", "huyen": "̀", "ngang": ""}
_NGUYEN_AM_VIET = "aăâeêioôơuưy"


def _dat_thanh(am_tiet: str, thanh: str) -> str:
    """Đặt dấu thanh lên đúng nguyên âm chính (kiểu mới: hoà, thuý)."""
    dau = _THANH[thanh]
    if not dau:
        return am_tiet
    s = am_tiet
    vt = [i for i, ch in enumerate(s) if ch in _NGUYEN_AM_VIET]
    if s.startswith("gi") and len(vt) > 1 and vt[0] == 1:
        vt = vt[1:]                             # "gi" là âm đầu: "giờ" chứ không "gìơ"
    if s.startswith("qu") and len(vt) > 1 and vt[0] == 1:
        vt = vt[1:]
    if not vt:
        return s
    uu = [i for i in vt if s[i] in "ăâêôơư"]
    if uu:
        i = uu[-1] if s[uu[-1]] == "ơ" else uu[0]
    elif len(vt) == 1:
        i = vt[0]
    else:
        co_cuoi = vt[-1] < len(s) - 1
        i = vt[-1] if co_cuoi or s[vt[0]:vt[0] + 2] in ("oa", "oe", "uy") else vt[0]
    return unicodedata.normalize("NFC", s[:i + 1] + dau + s[i + 1:])


def _chinh_ta_dau(am_dau: str, van: str) -> str:
    """Luật chính tả tiếng Việt cho âm đầu: c/k, g/gh, ng/ngh, gi+i."""
    v0 = van[:1]
    if am_dau == "c" and v0 in "eêiy":
        return "k"
    if am_dau == "g" and v0 in "eêi":
        return "gh"
    if am_dau == "ng" and v0 in "eêi":
        return "ngh"
    if am_dau == "gi" and v0 == "i":
        return "g"                              # "gi" + "in" -> "gin"
    return am_dau


def _van_cuoi(nhan: str, cuoi: str) -> str:
    """Ghép nhân + phụ âm cuối theo chính tả Việt (ic -> ich, ing -> inh...)."""
    if not cuoi:
        return nhan
    if nhan[-1:] in ("i", "y", "ê") and cuoi == "ng":
        return nhan + "nh"
    if nhan[-1:] in ("i", "y", "ê") and cuoi == "c":
        return nhan + "ch"
    return nhan + cuoi


def _am_tiet_chem(ph: str) -> str:
    """Phụ âm đứng một mình (cụm đầu): "k" -> "cờ", "p" -> "pờ"."""
    d = _DAU_AM.get(ph, "") or "u"
    if ph == "W":
        return "uờ"
    return _chinh_ta_dau(d, "ơ") + "ờ"


def _onset(cum: list):
    """Cụm phụ âm đầu âm tiết -> (âm chêm đứng trước, chữ âm đầu, lướt "w"/"y"/None).

    Người Việt đọc cụm phụ âm tiếng Anh bằng cách chêm "ờ" vào phụ âm đầu ("micro" là "mi cờ
    rô"); riêng "tr" và "qu" tiếng Việt có sẵn thì giữ nguyên ("street" là "sờ trít", "quick"
    là "quých").
    """
    cum = list(cum)
    luot = None
    if cum and cum[-1] == "Y" and len(cum) > 1:
        cum, luot = cum[:-1], "y"                 # "computer" P Y UW -> "piu"
    if not cum:
        return [], "", luot
    if cum[-2:] == ["K", "W"]:
        return [_am_tiet_chem(p) for p in cum[:-2]], "qu", luot
    if cum[-2:] == ["T", "R"]:
        return [_am_tiet_chem(p) for p in cum[:-2]], "tr", luot
    chem = [_am_tiet_chem(p) for p in cum[:-1]]
    last = cum[-1]
    if last == "W":
        return chem, "", "w"
    if last == "Y":
        return chem, "", "y"
    return chem, _DAU_AM.get(last, ""), luot


# Âm đầu được phép đứng giữa từ làm âm đầu âm tiết sau (tách từ cụm phụ âm giữa hai nguyên
# âm). Cụm có S thì không: "customer" là "cát tờ mờ", S làm đuôi âm tiết trước.
_DAU_GIUA = {("P", "L"), ("P", "R"), ("B", "L"), ("B", "R"), ("K", "L"), ("K", "R"),
             ("G", "L"), ("G", "R"), ("F", "L"), ("F", "R"), ("T", "R"), ("D", "R"),
             ("TH", "R"), ("K", "W")}


def _cuoi_tu(c: str):
    """Một phụ âm làm đuôi âm tiết (không ở cuối từ). None = không có đuôi tương ứng."""
    if c == "L":
        return "L"
    if c in _CUOI_AM:
        return _CUOI_AM[c]
    if c in _XAT:
        return "t"
    if c in ("F", "V"):
        return "p"
    return None


def am_vi_sang_viet(am_vi: list, chu: str = "") -> str:
    """Danh sách âm vị ARPAbet -> chuỗi âm tiết tiếng Việt cách nhau khoảng trắng.

    `chu` là mặt chữ gốc (không bắt buộc): chỉ dùng để chọn "o" cho AA khi từ viết bằng chữ o
    ("python" là "pai thon", "product" là "pờ ro đức"), vì người Việt đọc theo mặt chữ.
    """
    ph = [p for p in am_vi if p]
    vt_na = [i for i, p in enumerate(ph) if p.rstrip("012") in _NGUYEN_AM]
    if not vt_na:
        return " ".join(_am_tiet_chem(p.rstrip("012")) for p in ph)
    aa_o = "o" in chu.lower() and "a" not in chu.lower()
    ra = []
    chem, am_dau, luot = _onset(ph[:vt_na[0]])
    ra.extend(chem)
    for n, i in enumerate(vt_na):
        vowel, stress = ph[i].rstrip("012"), (ph[i][-1] if ph[i][-1].isdigit() else "1")
        cuoi_tu = n + 1 == len(vt_na)
        sau = ph[i + 1:vt_na[n + 1]] if not cuoi_tu else ph[i + 1:]
        cuoi, cum_sau = "", []
        if cuoi_tu:
            if sau:
                c0 = sau[0]
                if c0 == "L":
                    cuoi = "L"
                elif c0 in _CUOI_AM:
                    cuoi = _CUOI_AM[c0]
                elif c0 in _XAT and len(sau) > 1 and sau[1] in _CUOI_AM:
                    cuoi = _CUOI_AM[sau[1]]           # "test" S T -> t
                elif c0 == "R" and len(sau) > 1 and sau[1] in _CUOI_AM:
                    cuoi = _CUOI_AM[sau[1]]           # "art" R T -> t
                elif c0 in _XAT and stress != "0" and vowel in _LAX | {"AH", "AA", "AO"}:
                    cuoi = "t"                        # "pass" -> "pát", "dash" -> "đát"
        elif sau:
            # Tách cụm giữa hai nguyên âm: phần đuôi dài nhất làm được âm đầu thì cho âm tiết
            # sau, phần còn lại làm đuôi âm tiết này (lấy phụ âm đầu tiên có đuôi tương ứng).
            k = len(sau) - 1
            if len(sau) >= 2 and sau[-1] == "Y":
                k = len(sau) - 2
                if k >= 1 and (sau[k - 1], sau[k]) in _DAU_GIUA:
                    k -= 1
            elif len(sau) >= 2 and (sau[-2], sau[-1]) in _DAU_GIUA:
                k = len(sau) - 2
            truoc_cum, cum_sau = sau[:k], sau[k:]
            for c in truoc_cum:
                cc = _cuoi_tu(c)
                if cc:
                    cuoi = cc
                    break
            if (not truoc_cum and len(cum_sau) == 1 and stress == "1" and vowel in _LAX
                    and cum_sau[0] in _CUOI_AM and cum_sau[0] != "NG"):
                cuoi = _CUOI_AM[cum_sau[0]]           # "Emma" -> "em ma"
        if vowel in _LUOT and cuoi not in ("", "L"):
            cuoi = ""
        nhan = _nhan(vowel, stress, cuoi, "")
        if vowel == "AA" and aa_o:
            nhan = "o"
        if cuoi == "L":
            if vowel in ("EH", "EY"):
                nhan, cuoi = "eo", ""
            elif vowel in _LUOT:
                cuoi = ""
            elif stress == "0" and vowel in ("AH", "ER"):
                nhan, cuoi = "ô", ""                # "model" -> "mô đồ"
            else:
                cuoi = "n"
        if luot == "w":
            nhan = {"a": "oa", "ă": "oă", "e": "oe", "i": "uy", "ơ": "uơ", "ư": "uơ"}.get(
                nhan, nhan if nhan[:1] in "uôo" else "u" + nhan)
        elif luot == "y":
            nhan = {"u": "iu", "ô": "iô", "ơ": "iơ"}.get(nhan, nhan)
        if am_dau == "qu" and nhan.startswith("i"):
            nhan = "y" + nhan[1:]                   # "qui" -> "quy"
        van = _van_cuoi(nhan, cuoi)
        dau = _chinh_ta_dau(am_dau, van)
        if cuoi in ("p", "t", "c") or van.endswith("ch"):
            thanh = "sac"
        elif stress == "0" and vowel in ("AH", "ER"):
            thanh = "huyen"
        else:
            thanh = "ngang"
        ra.append(_dat_thanh(dau + van, thanh))
        if not cuoi_tu:
            chem, am_dau, luot = _onset(cum_sau)
            ra.extend(chem)
    return " ".join(ra)


# ---------------------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------------------
def _tach_ghep(tu: str) -> list:
    """"OpenRouter" -> ["Open", "Router"]; "GitHub" -> ["Git", "Hub"]; "iPhone" giữ nguyên."""
    phan = re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+", tu)
    return phan if len(phan) > 1 else [tu]


def doc_tu(tu: str) -> str:
    """Một từ tiếng Anh -> cách đọc kiểu Việt."""
    k = tu.lower().replace("’", "'")
    if k in TU_DIEN:
        return TU_DIEN[k]
    if len(tu) >= 2 and tu.isupper() and tu.isalpha():
        return " ".join(CHU_CAI.get(c, c) for c in tu.lower())
    if len(tu) == 1:
        return CHU_CAI.get(k, k)
    am = tra_cmu(k)
    if am:
        return am_vi_sang_viet(am, tu)
    phan = _tach_ghep(tu)
    if len(phan) > 1:
        return " ".join(doc_tu(p) for p in phan)
    if k.endswith("'s") and tra_cmu(k[:-2]):
        return am_vi_sang_viet(tra_cmu(k[:-2]), tu)
    return am_vi_sang_viet(doan_am_vi(k), tu)


def doc_viet(text: str) -> str:
    """Câu tiếng Việt xen tiếng Anh -> câu để giọng Việt đọc: từ tiếng Anh thay bằng cách đọc
    kiểu Việt, mọi thứ khác GIỮ NGUYÊN (dấu câu, số, khoảng trắng).

    Câu không có chữ tiếng Việt có dấu (câu thuần tiếng Anh) thì trả nguyên: để giọng đọc nó
    như tiếng Anh.
    """
    s = str(text or "")
    if not co_tieng_viet(s):
        return s
    ra, pos = [], 0
    for m in _TU.finditer(s):
        w = m.group(0)
        if la_tu_tieng_anh(w):
            ra.append(s[pos:m.start()])
            try:
                ra.append(doc_tu(w) or w)
            except Exception:
                ra.append(w)
            pos = m.end()
    ra.append(s[pos:])
    return "".join(ra)


def doc_cum(text: str) -> str:
    """Như doc_viet nhưng không đòi câu có tiếng Việt: dùng để so ÂM một cụm từ tiếng Anh
    (chốt kiểm tra câu diễn giải ở voice_brain)."""
    s = str(text or "")
    ra, pos = [], 0
    for m in _TU.finditer(s):
        w = m.group(0)
        if la_tu_tieng_anh(w):
            ra.append(s[pos:m.start()])
            try:
                ra.append(doc_tu(w) or w)
            except Exception:
                ra.append(w)
            pos = m.end()
    ra.append(s[pos:])
    return "".join(ra)
