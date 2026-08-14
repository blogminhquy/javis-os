"""Đa ngôn ngữ: dò ngôn ngữ, chốt ngôn ngữ, và các cổng chặn phải theo ngôn ngữ.

    python tests/run.py da_ngon_ngu

Bệnh thật đo được trên mã trước khi có tầng này (0.34.1):

    "tóm tắt đơn hàng"    -> bị chặn đúng, đi đường đầy đủ, Javis gọi tool lấy số thật
    "summarize my orders" -> LỌT qua đường tắt tiết kiệm token. Đường tắt cố ý KHÔNG phát
                             tool nào, nên model không có cách nào biết số đơn hàng, và nó
                             làm cái tệ nhất: bịa ra một con số nghe hợp lý.

Cùng một câu hỏi, hai ngôn ngữ, hai kết cục. Nguyên nhân: mẫu DENY của cổng có `don hang`
nhưng không có `orders`. Tiếng Anh được phục vụ một nửa, và **nửa bộ từ vựng nguy hiểm hơn
không có bộ từ vựng nào** - tiếng Thái không khớp gì cả nên rơi về đường đầy đủ, an toàn;
tiếng Anh khớp ALLOW rồi lọt.

File này khoá lại cả hai hướng: tiếng Việt phải giữ NGUYÊN hành vi cũ từng bit, và tiếng Anh
phải được chặn ngang bằng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

import lang as lang_mod
import lang_registry
import lexicon
from fast_path_runtime import FastIntentClassifier
import readonly_path_runtime
import readonly_orchestrator
import chatbot_runtime
import chatbot_store

_loi = []


def check(ten, dieu_kien):
    print(f"       {'ok  ' if dieu_kien else 'FAIL'} {ten}")
    if not dieu_kien:
        _loi.append(ten)


# ============================================================
# 1. Dò ngôn ngữ
# ============================================================
check("dấu tiếng Việt là tín hiệu chắc chắn",
      lang_mod.detect("tóm tắt đơn hàng hôm nay giúp anh")[0] == "vi")
check("tiếng Việt KHÔNG DẤU vẫn dò ra (người Việt gõ kiểu này rất nhiều)",
      lang_mod.detect("toi muon xem doanh thu thang nay the nao")[0] == "vi")
check("tiếng Anh dò ra qua hư từ",
      lang_mod.detect("summarize my orders for this quarter please")[0] == "en")

# Bẫy đã cắn một lần: câu tiếng Nhật mở đầu bằng KANJI, mà kanji nằm trong khoảng Hán. Duyệt
# từng ký tự rồi trả về ngay khi khớp thì câu đó ra "zh".
check("tiếng Nhật mở đầu bằng kanji vẫn ra ja, không ra zh",
      lang_mod.detect("今日の売上をまとめてください")[0] == "ja")
check("tiếng Thái ra th", lang_mod.detect("สรุปยอดขายวันนี้ให้หน่อยครับ")[0] == "th")
check("câu quá ngắn thì KHÔNG đoán bừa", lang_mod.detect("ok")[0] == "")


# ============================================================
# 2. Chốt ngôn ngữ: ưu tiên và quán tính
# ============================================================
lang_mod.quen_phien()
_d = lang_mod.resolve(turn_text="trả lời bằng tiếng Anh từ giờ nhé", session_id="t1")
check("lệnh thẳng trong lượt thắng tất cả", _d.lang == "en" and _d.source == "turn")

check("'dịch bài này sang tiếng Anh' KHÔNG phải lệnh đổi ngôn ngữ",
      lang_mod.resolve(turn_text="dịch bài này sang tiếng Anh giúp anh",
                       session_id="t2").lang == "vi")

check("chatbot ghim thắng cài đặt của chủ",
      lang_mod.resolve(turn_text="anh muốn xem doanh thu tháng này",
                       chatbot_pin="en", reply_pref="vi", session_id="t3").lang == "en")

# Quán tính: một câu tiếng Anh lẻ giữa cuộc tiếng Việt KHÔNG được đổi ngôn ngữ.
lang_mod.quen_phien()
for cau in ("anh muốn xem doanh thu tháng này thế nào",
            "thanks that is very helpful information",
            "cho anh xem thêm phần chi phí quảng cáo"):
    _d = lang_mod.resolve(turn_text=cau, session_id="t4")
check("chèn một câu tiếng Anh lẻ thì KHÔNG đổi ngôn ngữ", _d.lang == "vi")

# Nhưng chuyển HẲN sang tiếng Anh thì phải đổi được, nếu không thì luật quán tính thành cái
# khoá vĩnh viễn. Bản đầu mắc đúng lỗi này: một lượt tin cậy trung bình xoá sạch chuỗi đang
# tích, nên không bao giờ đủ hai lượt liên tiếp.
lang_mod.quen_phien()
for cau in ("anh muốn xem doanh thu tháng này thế nào",
            "please show me the cost breakdown in detail",
            "and also the revenue by channel for this month"):
    _d = lang_mod.resolve(turn_text=cau, session_id="t5")
check("chuyển hẳn sang tiếng Anh thì đổi được sau 2 lượt", _d.lang == "en")


# ============================================================
# 3. Cổng đường tắt: tiếng Việt giữ nguyên, tiếng Anh phải ngang bằng
# ============================================================
_gate = FastIntentClassifier()

# Hành vi tiếng Việt phải giống hệt trước khi rút regex ra lexicon.
for cau in ("Đính kèm file này giúp anh", "Doanh thu hôm nay bao nhiêu",
            "Gửi email cho khách giúp anh", "Đặt lịch họp ngày mai"):
    check(f"VI vẫn bị chặn: {cau[:34]}", not _gate.classify(cau).eligible)
check("VI tự chứa vẫn đi tắt được", _gate.classify("Giải thích entropy là gì").eligible)
check("VI viết lách vẫn đi tắt được",
      _gate.classify("Viết cho anh 5 tiêu đề về học tập").eligible)

# Đây là bệnh chính file này sinh ra để chặn.
_cap = [
    ("tóm tắt đơn hàng", "summarize my orders"),
    ("doanh thu tháng này bao nhiêu", "how much did we make this month"),
    ("nhắc tôi 7h sáng mai", "remind me tomorrow at 7am"),
    ("sửa file ghi chú giúp anh", "edit my notes file"),
    ("kiểm tra hộp thư giúp anh", "check my inbox"),
]
for vi_cau, en_cau in _cap:
    v = _gate.classify(vi_cau).eligible
    e = _gate.classify(en_cau).eligible
    check(f"VI và EN cùng kết cục: {en_cau[:30]}", v == e is False)

check("EN tự chứa vẫn đi tắt được", _gate.classify("explain what entropy is").eligible)
check("EN tính toán vẫn đi tắt được", _gate.classify("calculate 15 percent of 2400").eligible)


# ============================================================
# 4. Luật suy biến: thiếu bộ từ vựng làm Javis TỐN HƠN, không làm Javis LỎNG HƠN
# ============================================================
_th = _gate.classify("สรุปยอดขายวันนี้ให้หน่อยครับ")
check("ngôn ngữ chưa có lexicon thì KHÔNG được đi tắt", not _th.eligible)
check("và lý do phải nói rõ là vì thiếu lexicon, không phải 'uncertain' do may",
      "no_lexicon" in _th.reason)

_ja = _gate.classify("今日の売上をまとめてください")
check("tiếng Nhật cũng vậy", not _ja.eligible and "no_lexicon" in _ja.reason)

check("lexicon chưa có thì get() trả None chứ không im lặng dùng tạm tiếng Việt",
      lexicon.get("th") is None)
check("mọi lexicon phải khai ĐỦ các tập bắt buộc",
      all(all(hasattr(lexicon.get(m), t) for t in lexicon.BAT_BUOC)
          for m in lexicon.ma_list()))


# ============================================================
# 5. Hai cổng chỉ đọc
# ============================================================
for mod, ten in ((readonly_path_runtime, "readonly_path"), (readonly_orchestrator, "orchestrator")):
    for cau in ("Đặt lịch họp ngày mai", "Đăng bài lên trang"):
        check(f"{ten} chặn ý định ghi tiếng Việt: {cau[:26]}",
              mod._cong_chi_doc(mod._norm(cau), cau) == "write_intent")
    for cau in ("Schedule a meeting for tomorrow", "Post this to the page"):
        check(f"{ten} chặn ý định ghi tiếng Anh: {cau[:26]}",
              mod._cong_chi_doc(mod._norm(cau), cau) == "write_intent")


# ============================================================
# 6. Chatbot chuyên trách: ngôn ngữ của bot ĐỘC LẬP với ngôn ngữ của chủ
# ============================================================
check("bot mặc định auto", chatbot_store._clean_ngon_ngu(None) == "auto")
check("mã lạ rơi về auto chứ không lưu nguyên", chatbot_store._clean_ngon_ngu("xx") == "auto")
check("mã hợp lệ giữ nguyên", chatbot_store._clean_ngon_ngu("EN_us") == "en")

_p_auto = chatbot_runtime.build_bot_prompt({"name": "Trợ lý", "ngon_ngu": "auto"})
_p_en = chatbot_runtime.build_bot_prompt({"name": "Trợ lý", "ngon_ngu": "en"})
check("bot auto được dạy bám theo ngôn ngữ khách", "ngôn ngữ khách đang nhắn" in _p_auto)
check("bot ghim en được dạy luôn trả lời tiếng Anh",
      "English" in _p_en and "Answer in English." in _p_en)
check("prompt bot LUÔN có một dòng ngôn ngữ, kể cả khi không khai gì",
      "NGÔN NGỮ" in chatbot_runtime.build_bot_prompt({"name": "Trợ lý"}))


# ============================================================
# 7. Sổ đăng ký
# ============================================================
check("chuẩn hoá được mã dạng đầy đủ", lang_registry.chuan_hoa("vi-VN") == "vi")
check("mã lạ trả rỗng chứ không tự rơi về mặc định", lang_registry.chuan_hoa("xx") == "")
check("get() không bao giờ ném lỗi", lang_registry.get("xx").code == "vi")
check("ElevenLabs cố ý để rỗng (giọng của nó vốn đa ngôn ngữ)",
      lang_registry.giong_tts("en", "elevenlabs") == "")
check("Edge có giọng riêng cho từng ngôn ngữ",
      lang_registry.giong_tts("vi", "edge") != lang_registry.giong_tts("en", "edge"))

print()
if _loi:
    print(f"ĐỎ {len(_loi)} mục: " + "; ".join(_loi[:5]))
    sys.exit(1)
print("Tất cả xanh.")
