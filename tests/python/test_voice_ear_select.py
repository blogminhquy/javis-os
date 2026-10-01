"""Chọn tai nghe lại (voice_ear.select_ear) và các đường nối của nó (0.65.15).

    python tests/run.py voice_ear_select

Không chạm mạng. Khoá:
  - auto chọn tai cùng hãng với bộ não chính, không có thì tai xếp hạng cao nhất đang dùng được,
    không có tai nào thì rỗng (dùng chữ trình duyệt như trước);
  - khoá cũ stt_provider: "groq" vẫn là đã chọn tay, "browser" bị bỏ qua (nút Lưu luôn gửi nó);
  - off thì không tai nào chạy, kể cả khi có key;
  - /voice/ear trả đúng lựa chọn, /stt không gọi tai khi tai tắt, POST /settings lưu được khoá ear;
  - từ mồi gồm tên các kết nối MCP, nhưng lớp sửa mờ nghe_sua.sua KHÔNG nhận chúng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-ear-"))

import main  # noqa: E402
import nghe_sua  # noqa: E402
import stt  # noqa: E402
import voice_ear  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


KEY = {"groq_api_key": "gsk_test"}

# ---- setting(): khoá mới, khoá cũ, mặc định ----
check("thiếu cả hai khoá -> auto", voice_ear.setting({}) == "auto")
check("stt_provider=browser (mặc định lưu kèm) bị bỏ qua -> auto",
      voice_ear.setting({"voice": {"stt_provider": "browser"}}) == "auto")
check("stt_provider=groq người dùng đã lưu -> coi là đã chọn groq",
      voice_ear.setting({"voice": {"stt_provider": "groq"}}) == "groq")
check("khoá ear mới thắng khoá cũ",
      voice_ear.setting({"voice": {"ear": "off", "stt_provider": "groq"}}) == "off")
check("giá trị ear lạ không làm hỏng: về auto", voice_ear.setting({"voice": {"ear": "whisper9"}}) == "auto")

# ---- select_ear() ----
r = voice_ear.select_ear({"model": {}, "voice": {}})
check("auto, không key nào -> không tai, lý do none", r["provider"] == "" and r["reason"] == voice_ear.REASON_NONE)
r = voice_ear.select_ear({"model": KEY, "voice": {}}, "anthropic-cli")
check("auto, bộ não Claude, có key Groq -> tai Groq (tốt nhất đang có)",
      r["provider"] == "groq" and r["kind"] == "upload" and r["reason"] == voice_ear.REASON_BEST)
r = voice_ear.select_ear({"model": KEY, "voice": {}}, "groq")
check("auto, bộ não Groq -> tai cùng hãng", r["provider"] == "groq" and r["reason"] == voice_ear.REASON_SAME_VENDOR)
r = voice_ear.select_ear({"model": KEY, "voice": {"ear": "off"}})
check("off thắng cả khi có key", r["provider"] == "" and r["reason"] == voice_ear.REASON_OFF)
r = voice_ear.select_ear({"model": {}, "voice": {"ear": "groq"}})
check("chọn tay groq mà thiếu key -> không tai, lý do chosen_unavailable",
      r["provider"] == "" and r["reason"] == voice_ear.REASON_CHOSEN_UNAVAILABLE)
r = voice_ear.select_ear({"model": KEY, "voice": {"ear": "groq"}})
check("chọn tay groq có key -> groq, lý do chosen", r["provider"] == "groq" and r["reason"] == voice_ear.REASON_CHOSEN)

# ---- vocab(): MCP vào từ mồi, không vào lớp sửa mờ ----
_goc_mcp = voice_ear._mcp_labels
voice_ear._mcp_labels = lambda: ["Pancake POS", "Gmail", "javis"]
tv = voice_ear.vocab({"voice": {"hotwords": "Webcake"}})
check("từ mồi có tên trợ lý, từ người dùng khai và tên kết nối MCP",
      tv[:2] == ["Javis", "Webcake"] and "Pancake POS" in tv and "Gmail" in tv)
check("từ mồi không lặp tên trợ lý khi kết nối trùng tên", [t.lower() for t in tv].count("javis") == 1)
check("lớp sửa mờ nghe_sua.tu_vung KHÔNG nhận tên MCP",
      "Pancake POS" not in nghe_sua.tu_vung({"voice": {"hotwords": "Webcake"}}))
voice_ear._mcp_labels = _goc_mcp

# ---- routes ----
_goc_cfg, _goc_nghe = main.cfgmod.read_settings, stt.groq_nghe
calls = []


async def fake_nghe(data, ten, key, model="", ngon_ngu=None, hotwords=""):
    calls.append({"key": key, "hotwords": hotwords, "lang": ngon_ngu})
    return {"ok": True, "text": "Mở dashboard Facebook Ads", "model": "whisper-large-v3"}

stt.groq_nghe = fake_nghe

main.cfgmod.read_settings = lambda: {"model": dict(KEY), "voice": {}}
r = client.get("/voice/ear").json()
check("/voice/ear: auto + key Groq -> groq dạng upload", r["ok"] and r["provider"] == "groq" and r["kind"] == "upload")
r = client.post("/stt", files={"file": ("v.webm", b"OggS-fake", "audio/webm")}, data={"lang": "auto"})
check("/stt: auto + key -> chạy tai, ngôn ngữ auto thành '' (Whisper tự dò)",
      r.json()["ok"] is True and calls and calls[-1]["lang"] == "")

calls.clear()
main.cfgmod.read_settings = lambda: {"model": dict(KEY), "voice": {"ear": "off"}}
r = client.get("/voice/ear").json()
check("/voice/ear: off -> không tai", r["provider"] == "" and r["reason"] == "off")
r = client.post("/stt", files={"file": ("v.webm", b"OggS-fake", "audio/webm")}, data={"lang": "vi-VN"})
check("/stt: tai tắt -> không gọi Groq, ok=false ly_do tai_tat",
      not calls and r.json()["ok"] is False and r.json()["ly_do"] == "tai_tat")

# ---- POST /settings lưu được khoá ear (allowlist) ----
store = {"model": {}, "voice": {}}
main.cfgmod.read_settings = lambda: store
_goc_write = main.cfgmod.write_settings
main.cfgmod.write_settings = lambda cfg: store.update(cfg)
try:
    client.post("/settings", data={"section": "voice", "data": json.dumps({"ear": "groq"})})
    check("POST /settings voice.ear=groq được lưu", store.get("voice", {}).get("ear") == "groq")
    client.post("/settings", data={"section": "voice", "data": json.dumps({"ear": "chatgpt-lạ"})})
    check("giá trị ear lạ bị bỏ, giữ giá trị cũ", store.get("voice", {}).get("ear") == "groq")
finally:
    main.cfgmod.write_settings = _goc_write

stt.groq_nghe, main.cfgmod.read_settings = _goc_nghe, _goc_cfg

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - chọn tai nghe lại")
