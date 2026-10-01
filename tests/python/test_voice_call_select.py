"""Chọn đường gọi cho nút mic (voice_call.select_call_engine, 0.65.18).

    python tests/run.py voice_call_select

Không mạng. Khoá (docs/dev/2026-10-voice-call-spec.md mục 3.1):
  - auto: ChatGPT Live khi dùng được, rồi Live qua API key, rồi Cơ bản;
  - chọn tay mà đường đó không chạy được thì rơi xuống đường kế tiếp và nói lý do;
  - khoá cũ: mode=live + nhà cung cấp API là người dùng đã CHỌN Live API, giữ nguyên;
  - Cơ bản dùng Làn nhanh khi có bộ não giọng, không thì Chuẩn;
  - /voice/call trả đúng lựa chọn; POST /settings lưu được call_engine;
  - /ws/voice-live dựng nhà cung cấp theo đường đã chọn, không theo khoá live_provider cũ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-call-"))

import codex_realtime  # noqa: E402
import main  # noqa: E402
import voice_call  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


CHAT_OK = {"openai_oauth": {"refresh_token": "r"}}
_avail = {"v": (True, "")}
codex_realtime.realtime_available = lambda cfg: _avail["v"]

# ---- setting() ----
check("thiếu khoá -> auto", voice_call.setting({}) == "auto")
check("khoá cũ mode=fast -> auto", voice_call.setting({"voice": {"mode": "fast"}}) == "auto")
check("khoá cũ mode=live + gemini -> api (đã chọn Live API)",
      voice_call.setting({"voice": {"mode": "live", "live_provider": "gemini"}}) == "api")
check("khoá cũ mode=live + chatgpt -> chatgpt",
      voice_call.setting({"voice": {"mode": "live", "live_provider": "chatgpt"}}) == "chatgpt")
check("khoá mới thắng khoá cũ",
      voice_call.setting({"voice": {"call_engine": "basic", "mode": "live", "live_provider": "gemini"}}) == "basic")

# ---- select_call_engine ----
r = voice_call.select_call_engine({"model": CHAT_OK, "voice": {}})
check("auto + ChatGPT dùng được -> chatgpt, voice_mode live",
      r["engine"] == "chatgpt" and r["live_provider"] == "chatgpt" and r["voice_mode"] == "live")
_avail["v"] = (False, "no_login")
r = voice_call.select_call_engine({"model": {"gemini_api_key": "g"}, "voice": {"live_provider": "chatgpt"}})
check("auto, chưa nối ChatGPT, có key Gemini -> api gemini",
      r["engine"] == "api" and r["live_provider"] == "gemini" and r["voice_mode"] == "live")
r = voice_call.select_call_engine({"model": {}, "voice": {"brain_provider": "antigravity"}})
check("auto, không Live nào -> basic, Làn nhanh khi có bộ não giọng",
      r["engine"] == "basic" and r["voice_mode"] == "fast" and r["live_provider"] == "")
r = voice_call.select_call_engine({"model": {}, "voice": {}})
check("basic không có bộ não giọng -> Chuẩn", r["engine"] == "basic" and r["voice_mode"] == "standard")
check("auto rơi xuống basic nói lý do ChatGPT chưa nối", r["reason"] == "auto_basic" and r["detail"] == "no_login")
r = voice_call.select_call_engine({"model": {"openai_api_key": "k"}, "voice": {"call_engine": "chatgpt"}})
check("chọn tay ChatGPT mà chưa dùng được -> rơi xuống api, lý do chosen_unavailable",
      r["engine"] == "api" and r["live_provider"] == "openai" and r["reason"] == "chosen_unavailable")
_avail["v"] = (True, "")
r = voice_call.select_call_engine({"model": CHAT_OK, "voice": {"call_engine": "basic", "mode": "fast", "brain_provider": "codex"}})
check("chọn tay Cơ bản -> basic dù ChatGPT sẵn", r["engine"] == "basic" and r["reason"] == "chosen" and r["voice_mode"] == "fast")
r = voice_call.select_call_engine({"model": {"gemini_api_key": "g"}, "voice": {"mode": "live", "live_provider": "gemini"}})
check("khoá cũ Live Gemini vẫn là Gemini dù ChatGPT sẵn", r["engine"] == "api" and r["live_provider"] == "gemini")

# ---- routes ----
_goc_cfg = main.cfgmod.read_settings
main.cfgmod.read_settings = lambda: {"model": CHAT_OK, "voice": {}}
d = client.get("/voice/call").json()
check("/voice/call trả engine và voice_mode", d.get("ok") and d["engine"] == "chatgpt" and d["voice_mode"] == "live")

store = {"model": {}, "voice": {}}
main.cfgmod.read_settings = lambda: store
_goc_write = main.cfgmod.write_settings
main.cfgmod.write_settings = lambda cfg: store.update(cfg)
try:
    client.post("/settings", data={"section": "voice", "data": json.dumps({"call_engine": "basic"})})
    check("POST /settings lưu call_engine", store["voice"].get("call_engine") == "basic")
    client.post("/settings", data={"section": "voice", "data": json.dumps({"call_engine": "lạ"})})
    check("call_engine lạ bị bỏ", store["voice"].get("call_engine") == "basic")
finally:
    main.cfgmod.write_settings = _goc_write
main.cfgmod.read_settings = _goc_cfg

# /ws/voice-live dựng nhà cung cấp theo đường đã chọn
src = (SERVER / "main.py").read_text(encoding="utf-8")
seg = src[src.index("async def voice_live_ws"):src.index("async def voice_live_ws") + 4000]
check("/ws/voice-live dùng voice_call.live_settings để chọn nhà cung cấp",
      "voice_call.live_settings(" in seg)
cfg2 = voice_call.live_settings({"model": {"gemini_api_key": "g"}, "voice": {"live_provider": "chatgpt"}})
_avail["v"] = (False, "no_cli")
cfg2 = voice_call.live_settings({"model": {"gemini_api_key": "g"}, "voice": {"live_provider": "chatgpt"}})
check("live_settings ghi đè live_provider theo đường đã chọn", cfg2["voice"]["live_provider"] == "gemini")

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - chọn đường gọi")
