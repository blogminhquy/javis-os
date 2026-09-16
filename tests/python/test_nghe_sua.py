"""Sửa chữ nghe nhầm theo ngữ cảnh (nghe_sua.sua) và gợi ý hotwords cho Whisper.

    python tests/run.py nghe_sua

Vì sao file này tồn tại (0.59.24): người dùng nói lẫn Việt - Anh, máy nghe chép "Javis" thành
"David", "Jarvis", "Gia vít"... rồi Javis trả lời bám nghĩa đen. Lớp này sửa theo ÂM và NGỮ
CẢNH trước khi câu đi vào bộ não. Ranh giới quan trọng: không đổi tên người thứ ba ("nhắn cho
David"), không đổi tên riêng hai chữ ("David Beckham"), không đụng câu không liên quan, và
không sửa gì thì trả y nguyên.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401

import nghe_sua  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


TV = ["Javis"]
S = lambda s, tv=TV: nghe_sua.sua(s, tv)   # noqa: E731

# ---- 1. Khoá âm: những cách máy nghe hay chép "Javis" phải về cùng một khoá ----
for w in ("Javis", "David", "Davis", "Jarvis", "Gia vít", "Ja vịt", "Đa vít", "javist"):
    check(f"khoá âm của {w!r} trùng Javis", nghe_sua.khoa_am(w) == nghe_sua.khoa_am("Javis"))
check("Java KHÔNG trùng khoá Javis", nghe_sua.khoa_am("Java") != nghe_sua.khoa_am("Javis"))

# ---- 2. Gọi tên: sửa ở mọi vị trí khi trùng âm hoàn toàn ----
check("đầu câu: David -> Javis", S("David mở trang việc giúp anh") == "Javis mở trang việc giúp anh")
check("hey David", S("hey David, doanh thu hôm nay bao nhiêu") == "hey Javis, doanh thu hôm nay bao nhiêu")
check("cuối câu: cảm ơn David", S("cảm ơn David") == "cảm ơn Javis")
check("Jarvis -> Javis", S("Jarvis ơi mở lịch") == "Javis ơi mở lịch")
check("bị tách hai tiếng: Gia vít ơi", S("Gia vít ơi, tóm tắt email") == "Javis ơi, tóm tắt email")
check("Ja vịt giữa câu (trùng hoàn toàn)", S("hôm nay ja vịt thấy sao") == "hôm nay Javis thấy sao")
check("Đa vít", S("Đa vít cho anh xem lịch") == "Javis cho anh xem lịch")
check("sửa nhiều chỗ trong một câu",
      S("David ơi, David nghe rõ không") == "Javis ơi, Javis nghe rõ không")
check("giữ nguyên xuống dòng và dấu câu quanh chỗ sửa",
      S("Ok David.\nMở trang cài đặt!") == "Ok Javis.\nMở trang cài đặt!")

# ---- 3. Trùng vừa phải: CHỈ sửa ở vị trí gọi tên ----
check("Gia vị ơi (gọi tên) -> Javis", S("Gia vị ơi, mấy giờ rồi") == "Javis ơi, mấy giờ rồi")
check("cho gia vị vào nồi (giữa câu) giữ nguyên",
      S("cho gia vị vào nồi rồi đun") == "cho gia vị vào nồi rồi đun")
check("Cha vít đầu câu -> Javis", S("Cha vít, đọc tin mới") == "Javis, đọc tin mới")

# ---- 4. Không sửa bừa ----
GIU = [
    "nhắn cho David là tôi đến muộn",           # người thứ ba
    "gặp David lúc 3 giờ",
    "David Beckham đá bóng hay",                 # tên riêng hai chữ
    "học Java với anh Nam",                      # Java không phải Javis
    "đọc file README.md và mở https://github.com/x",
    "doanh thu tháng này bao nhiêu",
    "",
]
for s in GIU:
    check(f"giữ nguyên: {s[:40]!r}", S(s) == s)
check("không có gì sửa thì trả CÙNG đối tượng", S("xin chào") == "xin chào")
check("đã đúng Javis thì không đổi gì", S("Javis ơi mở lịch") == "Javis ơi mở lịch")
check("chạy hai lần ra cùng kết quả (idempotent)",
      S(S("David ơi Gia vít nghe không")) == S("David ơi Gia vít nghe không"))
check("bộ từ vựng rỗng: trả y nguyên", nghe_sua.sua("David ơi", []) == "David ơi")

# ---- 5. Từ vựng người dùng khai: nhiều từ, cụm hai tiếng ----
TV2 = ["Javis", "OpenRouter", "Pancake"]
check("Open Router (tách) -> OpenRouter",
      S("đổi bộ não sang open router đi", TV2) == "đổi bộ não sang OpenRouter đi")
check("Pan cake -> Pancake", S("xem đơn trên pan cake", TV2) == "xem đơn trên Pancake")
check("Bánh kếp không thành Pancake", S("ăn bánh kếp", TV2) == "ăn bánh kếp")

# ---- 6. Rút bộ từ vựng từ settings + gợi ý cho Whisper ----
cfg = {"voice": {"hotwords": "OpenRouter, Pancake\n javis ; Zalo,, Pancake"}}
tv = nghe_sua.tu_vung(cfg)
check("Javis luôn đứng đầu, không nhân đôi dù người dùng gõ 'javis'", tv[0] == "Javis" and tv.count("Javis") == 1
      and not any(t.lower() == "javis" for t in tv[1:]))
check("tách bằng phẩy, chấm phẩy, xuống dòng; bỏ trùng", tv == ["Javis", "OpenRouter", "Pancake", "Zalo"])
check("không có cài đặt vẫn có Javis", nghe_sua.tu_vung({}) == ["Javis"])
check("gợi ý Whisper là danh sách ngăn phẩy, khép dấu chấm",
      nghe_sua.goi_y_whisper(tv) == "Javis, OpenRouter, Pancake, Zalo.")
check("gợi ý rỗng khi không có từ", nghe_sua.goi_y_whisper([]) == "")

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - nghe_sua")
