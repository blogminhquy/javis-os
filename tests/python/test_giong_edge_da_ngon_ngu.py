"""Ô chọn giọng Edge: đúng tên Hoài My/Nam Minh và có đủ 5 giọng đa ngôn ngữ (0.58.6).

Vì sao có test này: Edge chỉ có hai giọng tiếng Việt bản địa (HoaiMy, NamMinh), nhưng 5
giọng đa ngôn ngữ thế hệ mới (Ava, Emma, Andrew, Brian, William) tự nhận tiếng Việt và đọc
mượt hơn. Chúng đi cùng đường /tts, không cần gì ở server, nên chỗ duy nhất có thể gãy là
giao diện: radio thiếu value, nhãn i18n thiếu ở một trong hai từ điển (chữ hiện ra là mã khoá),
hay trang voice-test lệch danh sách. Nhãn giọng nữ mặc định phải là tên thật "Hoài My" (trước
ghi "Ngọc Thu", chủ dự án yêu cầu sửa cho đúng).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
VOICE_TEST = (ROOT / "dashboard" / "voice-test.html").read_text(encoding="utf-8")
VI = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
EN = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))

fails: list[str] = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}")
        fails.append(name)


GIONG_VIET = ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]
GIONG_DA_NGON_NGU = {
    "en-US-AvaMultilingualNeural": ("Ava", "qs.voice_ava_sub"),
    "en-US-EmmaMultilingualNeural": ("Emma", "qs.voice_emma_sub"),
    "en-US-AndrewMultilingualNeural": ("Andrew", "qs.voice_andrew_sub"),
    "en-US-BrianMultilingualNeural": ("Brian", "qs.voice_brian_sub"),
    "en-AU-WilliamMultilingualNeural": ("William", "qs.voice_william_sub"),
}

radios = re.findall(r'<input type="radio" name="voice" value="([^"]+)"', INDEX)
check("ô chọn giọng có đúng 7 radio, không trùng", len(radios) == 7 and len(set(radios)) == 7)
check("hai giọng Việt bản địa còn nguyên và đứng đầu", radios[:2] == GIONG_VIET)
check("đủ 5 giọng đa ngôn ngữ", set(radios[2:]) == set(GIONG_DA_NGON_NGU))
check("giọng mặc định vẫn là Hoài My (checked)",
      'value="vi-VN-HoaiMyNeural" checked' in INDEX)
check("nhãn giọng nữ là tên thật Hoài My, không còn Ngọc Thu",
      "<strong>Hoài My</strong>" in INDEX and "Ngọc Thu" not in INDEX)
check("nhãn Nam Minh giữ nguyên", "<strong>Nam Minh</strong>" in INDEX)

for ma, (ten, khoa) in GIONG_DA_NGON_NGU.items():
    check(f"{ten}: radio kèm nhãn tên và dòng mô tả gọi khoá {khoa}",
          re.search(rf'value="{re.escape(ma)}">\s*<div><strong>{ten}</strong><div class="opt-sub" data-i18n="{khoa}">', INDEX) is not None)
    check(f"{ten}: khoá {khoa} có ở CẢ vi.json và en.json",
          bool(VI.get(khoa)) and bool(EN.get(khoa)))
    check(f"{ten}: mô tả tiếng Việt ghi rõ đa ngôn ngữ", "đa ngôn ngữ" in VI.get(khoa, ""))
    check(f"{ten}: có trong trang voice-test", f'<option value="{ma}">' in VOICE_TEST)

check("dòng ghi chú giọng đa ngôn ngữ có khoá i18n ở cả hai từ điển",
      'data-i18n="qs.voice_ml_note"' in INDEX and bool(VI.get("qs.voice_ml_note")) and bool(EN.get("qs.voice_ml_note")))
check("voice-test cũng ghi Hoài My", "Hoài My" in VOICE_TEST and "Ngọc Thu" not in VOICE_TEST)

# Không có em dash trong chuỗi mới (luật chung của dự án).
moi = [VI[k] for k in VI if k.startswith("qs.voice_")] + [EN[k] for k in EN if k.startswith("qs.voice_")]
check("chuỗi giọng đọc không chứa em dash", all("—" not in s for s in moi))

if fails:
    print(f"\n{len(fails)} FAIL")
    sys.exit(1)
print("\nOK")
