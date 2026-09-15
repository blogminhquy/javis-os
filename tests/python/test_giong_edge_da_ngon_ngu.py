"""Ô chọn giọng Edge: đúng tên Hoài My/Nam Minh và có đủ 5 giọng đa ngôn ngữ (0.58.6).

Vì sao có test này: Edge chỉ có hai giọng tiếng Việt bản địa (HoaiMy, NamMinh), nhưng 5
giọng đa ngôn ngữ thế hệ mới (Ava, Emma, Andrew, Brian, William) tự nhận tiếng Việt và đọc
mượt hơn. Chúng đi cùng đường /tts, không cần gì ở server, nên chỗ duy nhất có thể gãy là
giao diện: mục chọn thiếu value, nhãn i18n thiếu ở một trong hai từ điển (chữ hiện ra là mã
khoá), hay trang voice-test lệch danh sách. Nhãn giọng nữ mặc định phải là tên thật "Hoài My"
(trước ghi "Ngọc Thu", chủ dự án yêu cầu sửa cho đúng).

0.58.8: bảy thẻ radio đổi thành một ô chọn (#voiceSel) vì bảy thẻ xếp dọc cao gần 600px cho
đúng một lựa chọn. Hợp đồng KHÔNG đổi - vẫn đủ bảy value, vẫn phải có nhãn ở cả hai từ điển -
chỉ đổi chỗ đọc: <option value=...> thay cho <input type=radio>.
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
    "en-US-AvaMultilingualNeural": ("Ava", "qs.voice_opt_ava"),
    "en-US-EmmaMultilingualNeural": ("Emma", "qs.voice_opt_emma"),
    "en-US-AndrewMultilingualNeural": ("Andrew", "qs.voice_opt_andrew"),
    "en-US-BrianMultilingualNeural": ("Brian", "qs.voice_opt_brian"),
    "en-AU-WilliamMultilingualNeural": ("William", "qs.voice_opt_william"),
}

# Chỉ lấy các <option> BÊN TRONG ô chọn giọng, không quét cả trang.
_sel = INDEX.split('id="voiceSel"', 1)[1].split("</select>", 1)[0]
giong = re.findall(r'<option value="([^"]+)"', _sel)
check("ô chọn giọng có đúng 7 mục, không trùng", len(giong) == 7 and len(set(giong)) == 7)
check("hai giọng Việt bản địa còn nguyên và đứng đầu", giong[:2] == GIONG_VIET)
check("đủ 5 giọng đa ngôn ngữ", set(giong[2:]) == set(GIONG_DA_NGON_NGU))
# Ô chọn không cần "checked": mục ĐẦU TIÊN là mặc định, và app.js cũng lùi về mục đầu khi
# giọng đã lưu không còn trong danh sách.
check("giọng mặc định vẫn là Hoài My (mục đầu tiên)", giong[0] == "vi-VN-HoaiMyNeural")
check("nhãn giọng nữ là tên thật Hoài My, không còn Ngọc Thu",
      "Hoài My" in VI.get("qs.voice_opt_hoaimy", "") and "Ngọc Thu" not in INDEX)
check("nhãn Nam Minh giữ nguyên", "Nam Minh" in VI.get("qs.voice_opt_namminh", ""))
for khoa in ("qs.voice_opt_hoaimy", "qs.voice_opt_namminh"):
    check(f"{khoa} có ở CẢ vi.json và en.json", bool(VI.get(khoa)) and bool(EN.get(khoa)))

for ma, (ten, khoa) in GIONG_DA_NGON_NGU.items():
    check(f"{ten}: mục chọn gọi khoá {khoa}",
          re.search(rf'value="{re.escape(ma)}" data-i18n="{khoa}"', _sel) is not None)
    check(f"{ten}: khoá {khoa} có ở CẢ vi.json và en.json",
          bool(VI.get(khoa)) and bool(EN.get(khoa)))
    check(f"{ten}: nhãn tiếng Việt có tên giọng và ghi rõ đa ngôn ngữ",
          ten in VI.get(khoa, "") and "đa ngôn ngữ" in VI.get(khoa, ""))
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
