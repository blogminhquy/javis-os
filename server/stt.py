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
import sys

import httpx

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
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
           "\"Em nghe: ...\" rồi hỏi xác nhận trước khi làm.]")
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


async def groq_nghe(data, ten_file, api_key, model="", ngon_ngu="vi"):
    """Chuyển bytes âm thanh thành chữ. Trả dict:

        {"ok": True,  "text": "...", "model": "..."}
        {"ok": False, "ly_do": "thieu_key|rong|qua_lon|khong_nghe_ro|loi", "noi_voi_javis": "..."}

    `ngon_ngu` gợi ý cho Whisper (mặc định "vi"): không gợi ý thì câu tiếng Việt ngắn hay bị
    đoán nhầm sang tiếng khác rồi dịch luôn, ra một câu không ai gõ bao giờ.
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
    if ngon_ngu:
        form["language"] = ngon_ngu
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
        text = str(d.get("text") or "").strip()
        if not text:
            return {"ok": False, "ly_do": "khong_nghe_ro",
                    "noi_voi_javis": loi_thanh_dong("khong_nghe_ro")}
        return {"ok": True, "text": text, "model": mdl}
    except Exception as e:
        loi = f"{type(e).__name__}: {e}"
        print(f"[stt groq] {loi}", file=sys.stderr)
        return {"ok": False, "ly_do": "loi", "noi_voi_javis": loi_thanh_dong("loi", loi[:200])}
