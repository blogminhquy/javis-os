"""Lưu cài đặt giọng nói xong F5 có còn không (POST /settings section=voice).

    python tests/run.py luu_cai_dat_giong

Vì sao file này tồn tại (0.57.3): nhánh `voice` của POST /settings dùng ALLOWLIST TỪNG KEY.
Voice V2 thêm bảy ô mới (mode, brain_provider, brain_model, stt_provider, live_provider,
live_model, live_voice) nhưng allowlist không được nối dài, nên server nhận, trả {"ok": true},
nút hiện "Đã lưu", mà không ghi gì cả - tải lại trang là mất sạch. Không lỗi, không log.
Chính comment ở nhánh `locale` đã cảnh báo đúng cái bẫy này.

Hai lớp canh:
  1. Vòng tròn THẬT qua TestClient: POST rồi đọc lại settings, từng ô một.
  2. Chốt chặn tương lai: mọi key mà console.js gửi đi trong thẻ cài đặt V2 phải có tên trong
     nhánh voice của main.py. Thêm ô mới mà quên server là test đỏ ngay, không đợi người dùng
     phát hiện.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import re
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-voicecfg-")

from fastapi.testclient import TestClient   # noqa: E402
import config as c   # noqa: E402
import main          # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# base_url phải là host được phép: rào chống DNS-rebinding (web_security) trả 403 cho
# "testserver" mặc định của TestClient, và 403 đó sẽ che mất lỗi thật đang cần đo.
cl = TestClient(main.app, base_url="http://127.0.0.1:7777")


def luu(data: dict):
    return cl.post("/settings", data={"section": "voice", "data": json.dumps(data)})


def doc() -> dict:
    return c.read_settings().get("voice") or {}


# ---- 1. Vòng tròn thật: lưu rồi đọc lại ----
V2 = {"mode": "fast", "brain_provider": "antigravity", "brain_model": "gemini-3.8-flash-low",
      "stt_provider": "groq", "live_provider": "openai", "live_model": "gpt-realtime",
      "live_voice": "cedar"}
r = luu(V2)
check("POST /settings section=voice trả ok", r.status_code == 200 and r.json().get("ok") is True)
v = doc()
for k, want in V2.items():
    check(f"lưu rồi đọc lại giữ được '{k}'", v.get(k) == want)

# ---- 2. Giá trị lạ không lọt vào (ô chọn, không phải ô gõ tự do) ----
luu({"mode": "xxx"})
check("mode lạ không ghi đè mode đang dùng", doc().get("mode") == "fast")
luu({"stt_provider": "sai"})
check("stt_provider lạ không ghi đè", doc().get("stt_provider") == "groq")
luu({"live_provider": "sai"})
check("live_provider lạ không ghi đè", doc().get("live_provider") == "openai")
luu({"brain_provider": "khong-co-nha-cung-cap-nay"})
check("brain_provider lạ không ghi đè", doc().get("brain_provider") == "antigravity")

# ---- 3. Về chế độ chuẩn, bỏ bộ não giọng: PHẢI xoá được (chuỗi rỗng là giá trị hợp lệ) ----
luu({"mode": "standard", "brain_provider": "", "brain_model": "", "live_model": "", "live_voice": ""})
v = doc()
check("đổi về chế độ chuẩn được", v.get("mode") == "standard")
check("bỏ bộ não giọng được (rỗng là giá trị thật, không phải 'bỏ qua')",
      v.get("brain_provider") == "" and v.get("brain_model") == "")
check("xoá tên model Live được", v.get("live_model") == "" and v.get("live_voice") == "")

# ---- 4. Thẻ TTS lưu riêng, không đụng cài đặt V2 (hai thẻ cùng ghi section 'voice') ----
luu({"mode": "fast", "brain_provider": "groq", "brain_model": "m1"})
luu({"tts_provider": "openai", "openai_tts_voice": "alloy"})
v = doc()
check("lưu thẻ giọng đọc KHÔNG xoá cài đặt làn nhanh",
      v.get("mode") == "fast" and v.get("brain_provider") == "groq" and v.get("brain_model") == "m1")
check("thẻ giọng đọc vẫn lưu được phần của nó", v.get("tts_provider") == "openai")

# ---- 5. Chốt chặn: key nào console.js gửi thì main.py phải nhận ----
js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8", errors="replace")
m = re.search(r"v2Save\"\)\.onclick[\s\S]{0,900}?const data = \{([\s\S]{0,600}?)\};", js)
keys_js = set(re.findall(r"(\w+):", m.group(1))) if m else set()
check("đọc được khối data của nút Lưu cài đặt giọng nói trong console.js", len(keys_js) >= 7)
src = (SERVER / "main.py").read_text(encoding="utf-8", errors="replace")
nhanh = src[src.index('elif section == "voice":'):src.index('elif section == "password":')]
thieu = sorted(k for k in keys_js if f'"{k}"' not in nhanh)
check("mọi ô trong thẻ cài đặt giọng nói đều được nhánh voice của main.py xử lý: "
      + (", ".join(thieu) if thieu else "đủ"), not thieu)

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - luu_cai_dat_giong")
