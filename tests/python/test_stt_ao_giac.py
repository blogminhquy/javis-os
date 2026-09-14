"""Whisper bịa câu kêu gọi đăng ký kênh YouTube (stt.loc_ao_giac).

    python tests/run.py stt_ao_giac

Vì sao file này tồn tại (0.57.4): Whisper học chủ yếu từ phụ đề YouTube, nên khi gặp im lặng,
tiếng ồn nền hay một đoạn ngắn không rõ, nó "nhớ lại" mấy câu outro dày đặc trong dữ liệu học.
Tiếng Việt nổi tiếng nhất là "Hãy subscribe cho kênh Ghiền Mì Gõ Để không bỏ lỡ những video
hấp dẫn". Đó không phải lời người dùng, cũng không phải lỗi mạng nên không có gì báo: nó lặng
lẽ thành tin nhắn gửi cho Javis, và Javis trả lời câu đó một cách nghiêm túc.

Ranh giới quan trọng của bộ lọc này: nó CẮT câu bịa nhưng GIỮ phần người dùng nói thật (Whisper
hay dán câu bịa vào đầu rồi mới chép tiếp lời thật). Cắt sạch thành rỗng thì báo không nghe rõ
để chỗ gọi giữ chữ của Web Speech, chứ không đưa chuỗi rỗng đi tiếp.

Và nó phải KHÔNG đụng tới lời nói thật chỉ vì có chữ "kênh" hay "đăng ký" - người dùng bàn
chuyện marketing cả ngày.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401

import stt  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


L = stt.loc_ao_giac

# ---- 1. Câu bịa kinh điển: cắt sạch thành rỗng ----
AO = [
    "Hãy subscribe cho kênh Ghiền Mì Gõ Để không bỏ lỡ những video hấp dẫn",
    "hãy subscribe cho kênh ghiền mì gõ để không bỏ lỡ những video hấp dẫn.",
    "Ghiền Mì Gõ",
    "Hãy đăng ký kênh để không bỏ lỡ những video hấp dẫn!",
    "Hãy like và đăng ký kênh của chúng tôi để không bỏ lỡ những video mới nhất.",
    "Subscribe to my channel for more videos",
    "Thanks for watching!",
    "[Music]",
    "♪♪♪",
]
for s in AO:
    check(f"cắt sạch câu bịa: {s[:42]!r}", L(s) == "")

# ---- 2. Câu bịa DÍNH VÀO lời thật: giữ lời thật ----
lan = L("Hãy subscribe cho kênh Ghiền Mì Gõ Để không bỏ lỡ những video hấp dẫn. "
        "Doanh thu tháng này bao nhiêu?")
check("câu bịa đứng trước, giữ nguyên lời thật phía sau", lan == "Doanh thu tháng này bao nhiêu?")
lan = L("Mở trang Việc giúp mình. Hãy subscribe cho kênh Ghiền Mì Gõ.")
check("câu bịa đứng sau, giữ nguyên lời thật phía trước", lan == "Mở trang Việc giúp mình.")
check("nhiều câu bịa xen giữa", L("[Music] Chào Javis. Thanks for watching!") == "Chào Javis.")

# ---- 3. TUYỆT ĐỐI không đụng lời nói thật (bàn chuyện marketing là chuyện hằng ngày) ----
THAT = [
    "Đăng ký kênh YouTube cho shop mình tốn bao nhiêu tiền?",
    "Viết cho mình một câu kêu gọi đăng ký kênh nhé",
    "Kênh nào đang ra đơn nhiều nhất tháng này?",
    "Mình muốn làm video hấp dẫn hơn thì nên bắt đầu từ đâu?",
    "Subscribe là gì vậy?",
    "Doanh thu hôm nay bao nhiêu?",
    "Ghiền ăn mì quá",
]
for s in THAT:
    check(f"giữ nguyên lời thật: {s[:40]!r}", L(s) == s)

# ---- 4. Biên ----
check("chuỗi rỗng vẫn rỗng", L("") == "" and L(None) == "")
check("chỉ còn dấu câu thì coi như rỗng", L("Ghiền Mì Gõ . !") == "")
check("không làm hỏng khoảng trắng thừa", L("  Chào Javis  ") == "Chào Javis")

# ---- 5. Nối vào đường nghe: groq_nghe lọc trước khi trả ----
src = (SERVER / "stt.py").read_text(encoding="utf-8", errors="replace")
than = src[src.index("async def groq_nghe"):]
check("groq_nghe gọi loc_ao_giac trước khi trả text", "loc_ao_giac(" in than)
check("lọc xong rỗng thì báo khong_nghe_ro (chỗ gọi giữ chữ Web Speech)",
      than.index("loc_ao_giac(") < than.index('"khong_nghe_ro"'))

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - stt_ao_giac")
