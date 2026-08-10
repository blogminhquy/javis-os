"""Ghi âm gửi qua Telegram / Zalo thì Javis NGHE được (Whisper qua Groq), chưa đấu key thì nói rõ.

    python tests/run.py tin_thoai

Vì sao có file này. Tin thoại là loại tin duy nhất mà "hỏng" và "chạy" nhìn giống hệt nhau ở
phía người gửi: bấm giữ, thả ra, thấy đã gửi. Mọi ngả hỏng (chưa đấu key, file to, nghe không
ra chữ, Groq trả lỗi) đều phải quay lại thành MỘT CÂU NÓI, không được im.

Bốn chỗ dễ vỡ khi sửa code sau này, test khoá cả bốn:
  1. Chưa đấu key Groq -> phải nói ra là cần dán key ở trang Models, chứ không phải "chưa đọc
     được loại này" như thời chưa có STT.
  2. Khối tin thoại là NHIỀU dòng. `_caption_command_text` cắt lấy dòng đầu (đúng cho ảnh/file)
     sẽ vứt luôn câu vừa nói - im lặng, không lỗi nào. Và marker phải nhận ra khối của CẢ HAI
     kênh: Zalo mượn thẳng hàm này của Telegram.
  3. Key đọc TẠI THỜI ĐIỂM NGHE. Đọc lúc dựng bot thì key mới dán nằm im tới lần khởi động sau.
  4. Zalo KHÔNG có `getFile`: file thoại chỉ tới được qua URL nằm trong payload, mà khuôn
     payload đó Zalo chưa công bố. Trượt hết tên trường thì phải kêu ra kèm mẫu, không im.

Không chạm mạng: httpx của stt.py bị thay bằng client giả, phần tải file của hai kênh bị thay
bằng hàm trả bytes sẵn.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-thoai-"))

import stt  # noqa: E402
import telegram_bot as tb  # noqa: E402
import zalo_bot as zb  # noqa: E402

MAIN = (ROOT / "server" / "main.py").read_text(encoding="utf-8")

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def chay(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ============================================================
# stt.py - lớp nghe, không biết gì về Telegram
# ============================================================
kq = chay(stt.groq_nghe(b"xxx", "voice.ogg", ""))
check("chưa có key -> không ok", not kq["ok"] and kq["ly_do"] == "thieu_key")
_cau = kq["noi_voi_javis"]
check("câu thiếu key gọi đúng tên Groq", "Groq" in _cau)
check("câu thiếu key chỉ đúng chỗ dán key", "Models" in _cau)
check("câu thiếu key nói được cả ca đóng vai người thật với khách",
      "người thật" in _cau and "đừng nhắc" in _cau)

kq = chay(stt.groq_nghe(b"x" * (stt.MAX_STT_MB * 1024 * 1024 + 10), "v.ogg", "k"))
check("file vượt trần -> không gọi API, báo quá lớn", not kq["ok"] and kq["ly_do"] == "qua_lon")

kq = chay(stt.groq_nghe(b"", "v.ogg", "k"))
check("file rỗng -> không ok", not kq["ok"])


class _Resp:
    def __init__(self, code, data):
        self.status_code = code
        self._d = data

    def json(self):
        return self._d


class _FakeClient:
    """Thay httpx.AsyncClient trong stt.py. Ghi lại lời gọi để soi tham số gửi đi."""

    goi = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, data=None, files=None):
        _FakeClient.goi.append({"url": url, "headers": headers, "data": data, "files": files})
        return _Resp(*_FakeClient.tra)


_that = stt.httpx.AsyncClient
stt.httpx.AsyncClient = _FakeClient
try:
    _FakeClient.tra = (200, {"text": "  báo cáo doanh thu hôm nay  "})
    kq = chay(stt.groq_nghe(b"audio", "voice.ogg", "gsk_test"))
    check("nghe được -> trả chữ đã trim", kq["ok"] and kq["text"] == "báo cáo doanh thu hôm nay")
    g = _FakeClient.goi[-1]
    check("gọi đúng endpoint Whisper của Groq", g["url"] == stt.GROQ_STT_URL)
    check("gửi key dạng Bearer", g["headers"]["Authorization"] == "Bearer gsk_test")
    check("gợi ý tiếng Việt cho Whisper", g["data"].get("language") == "vi")
    check("model mặc định là bản turbo", g["data"]["model"] == stt.STT_MODEL_MAC_DINH)

    _FakeClient.tra = (200, {"text": "   "})
    kq = chay(stt.groq_nghe(b"audio", "voice.ogg", "k"))
    check("nghe ra chữ rỗng -> báo không nghe rõ", not kq["ok"] and kq["ly_do"] == "khong_nghe_ro")

    _FakeClient.tra = (401, {"error": {"message": "Invalid API Key"}})
    kq = chay(stt.groq_nghe(b"audio", "voice.ogg", "sai"))
    check("Groq từ chối -> nhắc lại LÝ DO THẬT chứ không phải mã HTTP trơn",
          not kq["ok"] and "Invalid API Key" in kq["noi_voi_javis"])
finally:
    stt.httpx.AsyncClient = _that


# ============================================================
# telegram_bot.py - tin thoại đi đường riêng, không rơi vào nhánh file đính kèm
# ============================================================
def _bot(stt_fn=None):
    return tb.TelegramBot("tok", "", answer_fn=None, stt_fn=stt_fn)


def _voice_msg(caption=""):
    m = {"message_id": 7, "chat": {"id": "9"}, "voice": {"file_id": "F1", "file_size": 1234}}
    if caption:
        m["caption"] = caption
    return m


async def _tai_gia(self, client, file_id):
    return b"AUDIO", ""


tb.TelegramBot._tai_ve_ram = _tai_gia   # không chạm mạng Telegram

# --- chưa đấu STT (stt_fn=None): phải nói cần key Groq ---
out = chay(_bot(None)._ingest_attachment(None, _voice_msg()))
check("chưa đấu STT -> vẫn trả một câu (không im lặng)", bool(out))
check("chưa đấu STT -> câu nói về key Groq", "Groq" in out and "Models" in out)
check("chưa đấu STT -> KHÔNG còn câu cũ 'chưa đọc được loại này'",
      "chưa đọc được" not in out)


# --- nghe được: khối gồm dòng dặn + câu đã nghe ---
async def _stt_ok(data, ten):
    return {"ok": True, "text": "doanh thu hôm nay bao nhiêu"}


out = chay(_bot(_stt_ok)._ingest_attachment(None, _voice_msg()))
check("nghe được -> khối mở đầu bằng marker thoại", out.startswith(tb.MARK_THOAI))
check("nghe được -> có câu vừa nói", "doanh thu hôm nay bao nhiêu" in out)
check("nghe được -> KHÔNG báo 'đã tải về path' như file thường", "đã tải về" not in out)
check("nghe được -> dặn xác nhận trước khi làm việc có tác động ra ngoài",
      "Em nghe:" in out and "xác nhận" in out)

# --- caption thường thì ghép vào cuối; caption LỆNH thì để _caption_command_text lo ---
out_cap = chay(_bot(_stt_ok)._ingest_attachment(None, _voice_msg("gấp nhé")))
check("caption thường -> ghép vào cuối khối", out_cap.rstrip().endswith("gấp nhé"))

out_cmd = chay(_bot(_stt_ok)._ingest_attachment(None, _voice_msg("/notes")))
check("caption LỆNH -> không ghép vào khối (tránh lệnh xuất hiện hai lần)",
      out_cmd.count("/notes") == 0)

# Đây là chỗ đã suýt mất câu vừa nói: cắt dòng đầu như ảnh/file thì transcript bay mất.
ghep = tb._caption_command_text(out_cmd, "/notes")
check("thoại + caption lệnh -> lệnh lên đầu", ghep.startswith("/notes"))
check("thoại + caption lệnh -> GIỮ NGUYÊN câu đã nghe",
      "doanh thu hôm nay bao nhiêu" in ghep)
# Ảnh/file vẫn giữ hành vi cũ (cắt lấy dòng marker) - không được sửa lây.
MARK_ANH = "[Người dùng gửi ảnh qua Telegram, gateway đã tải về: /inbox/p.jpg]"
check("ảnh + caption lệnh -> vẫn chỉ lấy dòng marker như trước",
      tb._caption_command_text(MARK_ANH + "\n/notes x", "/notes x") == "/notes x\n" + MARK_ANH)


# --- nghe hỏng: vẫn phải ra một câu ---
async def _stt_loi(data, ten):
    return {"ok": False, "ly_do": "loi", "noi_voi_javis": stt.loi_thanh_dong("loi", "mạng chết")}


out = chay(_bot(_stt_loi)._ingest_attachment(None, _voice_msg()))
check("nghe hỏng -> vẫn nói ra lý do", "mạng chết" in out)


async def _stt_no(data, ten):
    raise RuntimeError("bùm")


out = chay(_bot(_stt_no)._ingest_attachment(None, _voice_msg()))
check("stt_fn ném ngoại lệ -> nuốt lại thành câu nói, không gãy vòng nhận tin",
      bool(out) and "bùm" in out)

# --- video vẫn chưa xem được, nhưng câu từ chối không được nói lây sang voice ---
out = chay(_bot(_stt_ok)._ingest_attachment(None, {"message_id": 8, "chat": {"id": "9"},
                                                   "video": {"file_id": "V"}}))
check("video -> vẫn báo chưa xem được", "video" in out.lower() and "chưa xem được" in out)
check("câu từ chối video KHÔNG nhắc voice nữa", "voice" not in out.lower())

# --- audio (file nhạc/ghi âm gửi dạng audio) đi chung đường thoại ---
out = chay(_bot(_stt_ok)._ingest_attachment(None, {"message_id": 9, "chat": {"id": "9"},
                                                   "audio": {"file_id": "A", "file_size": 10}}))
check("audio cũng được nghe", out.startswith(tb.MARK_THOAI))

# --- file quá to so với trần TẢI VỀ của Telegram: chặn trước khi tải ---
out = chay(_bot(_stt_ok)._ingest_attachment(
    None, {"message_id": 10, "chat": {"id": "9"},
           "voice": {"file_id": "B", "file_size": (tb.MAX_DOWNLOAD_MB + 5) * 1024 * 1024}}))
check("thoại quá dài -> báo quá lớn thay vì tải về rồi hỏng", "quá dài" in out)


# ============================================================
# zalo_bot.py - cùng luật, khác đúng khâu LẤY FILE
# ============================================================
# Zalo không có getFile: đường duy nhất là URL trong payload, mà khuôn payload chưa công bố.
check("moi được URL dạng chuỗi",
      zb._lay_url({"voice_url": "https://a/v.ogg"}, ("voice_url", "voice")) == "https://a/v.ogg")
check("moi được URL lồng trong dict",
      zb._lay_url({"voice": {"url": "https://b/v.ogg"}}, ("voice_url", "voice")) == "https://b/v.ogg")
check("moi được URL ở khoá download_url",
      zb._lay_url({"voice": {"download_url": "https://c/v.ogg"}}, ("voice",)) == "https://c/v.ogg")
check("không có URL -> trả rỗng chứ không nổ", zb._lay_url({"voice": 123}, ("voice",)) == "")
check("bỏ qua giá trị không phải http", zb._lay_url({"voice": "abc"}, ("voice",)) == "")


class _ZClient:
    """Client giả cho phần TẢI FILE của Zalo (bot tự gọi client.get vào URL trong payload)."""

    def __init__(self, noi_dung=b"AUDIO"):
        self.noi_dung = noi_dung

    async def get(self, url, timeout=None):
        return _ZResp(self.noi_dung)


class _ZResp:
    def __init__(self, noi_dung):
        self.content = noi_dung

    def raise_for_status(self):
        return None


def _zbot(stt_fn=None):
    return zb.ZaloBot("tok", "", answer_fn=None, stt_fn=stt_fn)


def _zvoice(caption=""):
    m = {"message_id": "abc", "chat": {"id": "z1"}, "voice": {"url": "https://x/v.ogg"}}
    if caption:
        m["caption"] = caption
    return m


out = chay(_zbot(None)._ingest_attachment(_ZClient(), zb.SK_VOICE, _zvoice()))
check("Zalo chưa đấu STT -> nói về key Groq", "Groq" in out and "Models" in out)

out = chay(_zbot(_stt_ok)._ingest_attachment(_ZClient(), zb.SK_VOICE, _zvoice()))
check("Zalo nghe được -> khối mở đầu bằng marker thoại", out.startswith(stt.MARK_THOAI))
check("Zalo nghe được -> ghi đúng tên kênh trong khối", "qua Zalo" in out)
check("Zalo nghe được -> có câu vừa nói", "doanh thu hôm nay bao nhiêu" in out)
check("Zalo nghe được -> KHÔNG lưu file .ogg vào inbox", "đã tải về" not in out)

# Marker dùng chung: hàm cắt caption-lệnh của Telegram phải nhận ra cả khối của Zalo.
ghep = tb._caption_command_text(out, "/notes")
check("Zalo + caption lệnh -> lệnh lên đầu mà vẫn giữ câu đã nghe",
      ghep.startswith("/notes") and "doanh thu hôm nay bao nhiêu" in ghep)

# Không tìm ra URL: phải nói thẳng + kêu MỘT lần ra stderr (đây là ca dễ xảy ra nhất vì
# Zalo chưa công bố khuôn payload của tin thoại).
b = _zbot(_stt_ok)
out = chay(b._ingest_attachment(_ZClient(), zb.SK_VOICE, {"message_id": "m", "chat": {"id": "z"}}))
check("Zalo thiếu đường dẫn file -> nói thẳng chứ không im", "không tải về nghe được" in out
      or "không kèm đường dẫn" in out)
check("kêu khuôn lạ đúng MỘT lần (không spam log mỗi tin)", b._da_bao_khuon_thoai is True)

# Ảnh Zalo vẫn đi đường cũ (tải về đĩa, báo path) - không được sửa lây.
check("ảnh Zalo vẫn dùng _lay_url với bộ khoá của ảnh",
      '_lay_url(msg, ("photo_url", "photo", "image_url", "url", "file_url"))'
      in (ROOT / "server" / "zalo_bot.py").read_text(encoding="utf-8"))

# Sticker giữ nguyên hành vi cũ.
out = chay(_zbot(_stt_ok)._ingest_attachment(_ZClient(), zb.SK_STICKER,
                                             {"message_id": "s", "chat": {"id": "z"}}))
check("sticker Zalo vẫn báo không có chữ để đọc", "sticker" in out.lower())


# ============================================================
# main.py - đấu dây
# ============================================================
check("bot Telegram được cấp hàm nghe", "stt_fn=_stt_nghe" in MAIN)
check("bot Zalo cũng được cấp hàm nghe (cùng một key Groq)",
      MAIN.count("stt_fn=_stt_nghe") >= 2)
_fn = MAIN.split("async def _stt_nghe(", 1)[1].split("\n\n\n", 1)[0]
check("hàm nghe đọc key Groq", 'get("groq_api_key")' in _fn)
check("đọc key TẠI THỜI ĐIỂM GỌI (dán key xong không phải tắt bật lại bot)",
      "cfgmod.read_settings()" in _fn)
check("hàm nghe gọi đúng module stt", "stt.groq_nghe(" in _fn)


if _fails:
    raise SystemExit(f"\nFAIL - test_tin_thoai: {len(_fails)} lỗi")
print("\nOK - test_tin_thoai: tất cả pass")
