"""Độ CHÍNH XÁC của tầng đa ngôn ngữ, đo trên câu người ta gõ thật.

    python tests/run.py do_chinh_xac_ngon_ngu

Khác gì `test_da_ngon_ngu.py`. File kia khoá HÀNH VI: dò ra tiếng Anh thì phải làm gì. File này
khoá ĐỘ PHỦ: có thật sự dò ra không, trên một rổ câu thật. Ba lỗi dưới đây đều lọt qua bộ test
hành vi vì mọi ca mẫu ở đó đều dùng câu văn viết đầy đủ, còn người dùng thì gõ câu lệnh cụt.

Cả ba tìm ra trong lượt rà trước khi merge, và cả ba đều KHÔNG làm test nào đỏ - đó chính là
lý do file này tồn tại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

import lang as L
import fast_path_runtime as FP

_loi = []


def check(ten, dieu_kien, chi_tiet=""):
    print(f"       {'ok  ' if dieu_kien else 'FAIL'} {ten}")
    if not dieu_kien:
        _loi.append(ten)
        if chi_tiet:
            print("              " + chi_tiet)


# ============================================================
# 1. ĐỘ PHỦ khi dò ngôn ngữ, trên câu hỏi kinh doanh THẬT
# ============================================================
# Lỗi 1: hư từ tiếng Anh chỉ có 20 chữ và thiếu đúng nhóm hay gặp nhất trong câu lệnh ngắn
# (my, from, we, will, show, give...). Đo được: 5/18 câu. Nghĩa là người dùng tiếng Anh gõ
# "show me my revenue" vẫn bị Javis trả lời bằng tiếng Việt - đúng tính năng đầu bài của cả
# đợt này, hỏng trên phần lớn câu thật, mà không test nào đỏ.
CAU_EN = (
    "summarize my orders from last week", "show me my revenue",
    "compare my sales to last month", "give me a breakdown by channel",
    "list my pending tasks", "my orders from yesterday",
    "draft an email to my supplier", "check my inbox",
    "create a report about last week sales", "how much did we spend on ads",
    "what is my current revenue", "delete all my draft posts",
    "send the weekly summary to telegram", "which channel performed best",
    "total revenue for june please", "write a thank you note for customers",
    # Hai câu này HIỆN ĐANG TRƯỢT (không chứa hư từ nào), giữ lại trong rổ có chủ ý: bỏ câu
    # khó ra cho đủ điểm là tự đo mình bằng một cái thước đã uốn. Chúng trượt về RỖNG nên
    # phiên giữ nguyên ngôn ngữ đang dùng - sai theo hướng an toàn.
    "remind me tomorrow morning", "find slow moving products",
)
CAU_VI = (
    "Doanh thu hôm nay thế nào so với hôm qua?", "Cho mình xem đơn hàng tuần trước",
    "entropy la gi", "cho minh biet doanh thu thang nay",
    "Tổng hợp bán hàng tuần này giúp mình", "nhắc tôi 8h sáng mai uống thuốc",
    "tao cho toi mot viec moi", "Viết giúp mình một email cảm ơn khách",
    "xoa het don hang cua toi", "hom nay ban duoc bao nhieu",
    "lam cho minh cai bao cao thang 6", "danh sach khach hang moi tuan nay",
    "chi phi quang cao thang truoc la bao nhieu",
    # Cùng lý do như bên tiếng Anh: mấy câu không dấu này không chứa hư từ nào nên đang
    # trượt về rỗng. Giữ trong rổ để con số nói thật.
    "so sanh doanh thu 3 kenh", "bao nhieu don hang bi huy hom qua",
    "gui bao cao qua telegram", "kiem tra ton kho con bao nhieu",
)
_en_dat = [c for c in CAU_EN if L.detect(c)[0] == "en"]
_vi_dat = [c for c in CAU_VI if L.detect(c)[0] == "vi"]
# Ngưỡng đặt DƯỚI mức đo được (14/16 và 11/13) để test không đỏ vì một câu mới thêm vào rổ,
# nhưng vẫn đủ cao để bắt được cú tụt kiểu 5/18.
check(f"dò ra tiếng Anh trên câu thật ({len(_en_dat)}/{len(CAU_EN)})",
      len(_en_dat) >= len(CAU_EN) * 0.75,
      "trượt: " + "; ".join(c for c in CAU_EN if L.detect(c)[0] != "en")[:150])
check(f"dò ra tiếng Việt trên câu thật ({len(_vi_dat)}/{len(CAU_VI)})",
      len(_vi_dat) >= len(CAU_VI) * 0.75,
      "trượt: " + "; ".join(c for c in CAU_VI if L.detect(c)[0] != "vi")[:150])
# Câu trượt phải trượt về RỖNG (giữ ngôn ngữ đang dùng), tuyệt đối không sang ngôn ngữ khác.
_lech = [c for c in CAU_EN if L.detect(c)[0] not in ("en", "")] + \
        [c for c in CAU_VI if L.detect(c)[0] not in ("vi", "")]
check("câu không dò được thì trả RỖNG, không trả sai ngôn ngữ", not _lech, "; ".join(_lech))


# ============================================================
# 2. Tiếng Latin KHÁC không được nhận nhầm thành tiếng Việt
# ============================================================
# Lỗi 2: `_CHU_NGOAI` chỉ bắt được ký tự lạ, mà câu Âu châu GÕ THIẾU DẤU thì không còn ký tự
# nào lạ. Hư từ tiếng Việt không dấu đầy chữ hai ký tự trùng tiếng Âu, nên "les ventes du mois
# de juin sont bonnes" bị chấm là tiếng Việt chỉ vì một chữ "de".
#
# Vì sao đây là lỗi NẶNG chứ không phải chuyện lịch sự: nhận nhầm sang tiếng Việt nghĩa là đem
# BỘ TỪ VỰNG TIẾNG VIỆT ra chấm một câu tiếng Pháp ở các cổng an toàn. Đó đúng là kiểu hỏng mà
# cả tầng này sinh ra để chặn - nửa bộ từ vựng nguy hiểm hơn không có bộ nào.
CHAU_AU = (
    "les ventes du mois de juin sont bonnes",
    "je voudrais le rapport de la semaine",
    "quiero ver las ventas de este mes",
    "as vendas deste mes foram boas",
    "le vendite di questo mese sono buone",
    "die Verkaufszahlen von diesem Monat sind gut",
    "ik wil het rapport van deze week zien",
    # Hai câu Bồ Đào Nha có "nao" (não gõ thiếu dấu). Chúng ở đây vì lượt mở rộng hư từ
    # tiếng Việt suýt thêm "nào" vào danh sách, và thêm là hai câu này thành tiếng Việt.
    "eu nao quero o relatorio agora",
    "por que nao funciona",
)
_nham = [(c, L.detect(c)[0]) for c in CHAU_AU if L.detect(c)[0] in ("vi", "en")]
check("tiếng Âu châu không dấu KHÔNG bị nhận thành vi/en", not _nham,
      "; ".join(f"{c[:34]} -> {m}" for c, m in _nham))

# Và chốt lại chiều ngược: cái làm được điều trên KHÔNG được ăn vào tiếng Việt. "het" là chữ
# Hà Lan, nhưng cũng là "hết" tiếng Việt viết không dấu - bản đầu có nó trong danh sách chữ
# lạ nên "xoa het don hang cua toi" bị loại khỏi cuộc chấm điểm rồi trả về rỗng.
check("CANARY: chữ lạ không được nuốt chữ tiếng Việt không dấu",
      L.detect("xoa het don hang cua toi")[0] == "vi")
check("CANARY: 'het' không nằm trong danh sách chữ lạ", "het" not in L._TU_NGOAI)

# Chiều còn lại của cùng một cái bẫy: hư từ tiếng Việt cũng không được lấn sang tiếng khác.
import lang_registry as LR
_hu_vi = {w.lower() for w in LR.get("vi").stopwords}
_hu_en = {w.lower() for w in LR.get("en").stopwords}
check("CANARY: 'nao' không nằm trong hư từ tiếng Việt (là 'não' tiếng Bồ)",
      "nao" not in _hu_vi)

# Chữ lạ CHỈ tính khi viết thường. Mã đơn và tên riêng trong câu tiếng Việt hay trùng hư từ
# tiếng Âu, mà chúng luôn viết hoa - còn hư từ thật thì luôn nằm giữa câu, viết thường.
for _c in ("tim don hang co ma DES-2024", "san pham nay ban o Los Angeles",
           "đơn hàng từ Zara España tuần này"):
    check(f"chữ lạ VIẾT HOA không nuốt câu tiếng Việt: {_c[:34]}", L.detect(_c)[0] == "vi")
check("nhưng câu tiếng Pháp mở đầu bằng chữ hoa vẫn bắt được",
      L.detect("Les ventes du mois de juin sont bonnes")[0] not in ("vi", "en"))
check("CANARY: hư từ vi và en KHÔNG chồng nhau (chồng là hoà điểm rồi mất kết quả)",
      not (_hu_vi & _hu_en), str(sorted(_hu_vi & _hu_en)))


# ============================================================
# 3. Cổng tiết kiệm: câu KHÁI NIỆM tiếng Anh phải đi tắt được như tiếng Việt
# ============================================================
# Lỗi 3: mẫu `explanation` tiếng Anh đòi mạo từ ("what is a/an/the"), nên "what is entropy in
# information theory" rơi vào `intent_uncertain` và mất đường tắt, trong khi câu tiếng Việt
# cùng nghĩa ("... là gì") thì đi tắt được. Một chênh lệch theo NGÔN NGỮ, không theo nội dung.
_C = FP.FastIntentClassifier()

TU_CHUA = (
    "what is entropy in information theory", "what is machine learning",
    "what is a webhook", "what's the difference between REST and GraphQL",
    "what is the difference between revenue and profit", "what is a sales funnel",
)
for _c in TU_CHUA:
    _k = _C.classify(_c, False, 4000, lang="en")
    check(f"đi tắt được: {_c[:46]}", _k.eligible, f"{_k.intent_class}/{_k.reason}")

# Nới ALLOW ra thì phải chứng minh DENY vẫn giữ. Nới bản đầu làm lọt đúng một câu:
# "what are my pending orders" - `my orders` bị chặn nhưng chèn một tính từ vào giữa là thoát.
CAN_DU_LIEU = (
    "what are my pending orders", "what are my unpaid invoices",
    "what is our monthly revenue", "show me the total sales figure",
    "what are our top customers", "what is my current revenue",
    "what is in my inbox", "summarize my orders",
)
for _c in CAN_DU_LIEU:
    _k = _C.classify(_c, False, 4000, lang="en")
    check(f"vẫn chặn: {_c[:46]}", not _k.eligible, f"{_k.intent_class}/{_k.reason}")

# Cùng câu, hai thứ tiếng, phải ra cùng một quyết định. Đây mới là bất biến thật của cả tầng.
for _vi, _en, _mong in (
    ("entropy trong lý thuyết thông tin là gì", "what is entropy in information theory", True),
    ("tóm tắt đơn hàng tuần trước", "summarize my orders from last week", False),
    ("doanh thu hôm nay bao nhiêu", "what is my revenue today", False),
):
    _a = _C.classify(_vi, False, 4000, lang="vi").eligible
    _b = _C.classify(_en, False, 4000, lang="en").eligible
    check(f"vi và en cùng quyết định ({'đi tắt' if _mong else 'chặn'}): {_en[:38]}",
          _a == _b == _mong, f"vi={_a} en={_b}")

# ============================================================
# 4. Cổng BẮT KHAI MAN phải bắt được cách nói tự nhiên của cả hai thứ tiếng
# ============================================================
# Lỗi 4, và là lỗi nặng nhất trong lượt rà: mẫu FALSE_ACTION tiếng Anh cho ĐÚNG MỘT ô trợ động
# từ (`have` HOẶC `just` HOẶC `already`), nên "I have created" bắt được mà "I have ALREADY
# sent the report" thì lọt - trong khi đó là cách nói tự nhiên nhất.
#
# Cổng này bắt Javis KHAI đã làm một việc mà đường chỉ-đọc không cho phép làm. Bỏ sót ở đây
# nghĩa là rào chắn mất tác dụng trong im lặng. Bản tiếng Việt không dính vì tiếng Việt hiếm
# khi xếp chồng trợ từ - tức lỗi chỉ có ở MỘT ngôn ngữ, đúng kiểu lệch mà tầng đa ngôn ngữ
# phải chủ động đi tìm chứ không đợi nó tự lộ.
import context_compiler as _CC

_gate = _CC.DeterministicQualityGate()


def _khai_man(cau: str) -> bool:
    return "false_action_claim" in _gate.evaluate("x", cau, "dashboard",
                                                  read_only=True, lang="").reasons


for _c in ("I have already sent the report to your email.",
           "I have just created the new order.",
           "I've already deleted those drafts.",
           "We have already scheduled the reminder.",
           "Javis has already posted it to the page.",
           "I have successfully updated the record.",
           "Em đã gửi báo cáo qua email rồi ạ."):
    check(f"bắt được khai man: {_c[:44]}", _khai_man(_c))

# Chiều ngược: nới ra thì không được bắt oan câu chỉ MÔ TẢ việc làm được.
for _c in ("I can send the report if you want.",
           "I will send it once you approve.",
           "You have already sent that report yourself.",
           "To send the report, open the Connections page.",
           "Revenue today is 4.2M, up 12%."):
    check(f"KHÔNG bắt oan: {_c[:44]}", not _khai_man(_c))

# Ngôn ngữ chưa có bộ từ vựng: cổng bắt lỗi phải NÓI RA là chưa kiểm được, không im lặng
# cho qua rồi để người đọc trace tưởng đã kiểm và thấy sạch.
check("CANARY: ngôn ngữ lạ thì đánh dấu lang_unverified, không lặng lẽ pass",
      "lang_unverified" in _gate.evaluate("売上", "今日の売上は420万ドンです。",
                                          "dashboard", lang="ja").reasons)

print()
if _loi:
    print(f"ĐỎ {len(_loi)} mục: " + "; ".join(_loi[:4]))
    sys.exit(1)
print("Tất cả xanh.")
