"""Bộ não giọng TỰ CHỌN và thẻ Giọng nói gọn (0.65.19, docs/dev/2026-10-voice-call-spec.md mục 5).

    python tests/run.py voice_brain_auto

Không mạng, không dò binary thật (plan_brain_available bị thay). Khoá:
  - Làn nhanh mà chưa chọn bộ não giọng: dùng bộ não đầu tiên sẵn trên gói, theo thứ tự
    antigravity, codex, claude, grok; không có cái nào thì đi bộ não chính như cũ;
  - bộ não đã chọn từ bản cũ vẫn thắng; chế độ Chuẩn không tự chọn gì;
  - khoá cũ mode=live tính như Làn nhanh (Live nay là đường gọi riêng);
  - đường Cơ bản của nút mic là fast khi có bộ não tự chọn;
  - kết quả dò được nhớ 60 giây (hàm chạy mỗi câu nói);
  - GET /voice/options?brains=0 không chạy `agy models`, trả đường gọi, giọng đọc và bộ não giọng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-brain-auto-"))

import codex_realtime  # noqa: E402
import main  # noqa: E402
import voice_brain as vb  # noqa: E402
import voice_call  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_san = set()
_hoi = []


def _gia(pid, cfg):
    _hoi.append(pid)
    return pid in _san


vb.plan_brain_available = _gia


def moi(*ids):
    """Đặt các bộ não đang sẵn và xoá bộ nhớ 60 giây."""
    _san.clear()
    _san.update(ids)
    vb._AUTO_CACHE.update(at=0.0, key=None, value="")


# ---- auto_brain: thứ tự gói ----
moi("claude", "grok")
check("thứ tự gói: claude đứng trước grok", vb.auto_brain({}) == "claude")
moi("grok", "codex", "antigravity")
check("thứ tự gói: antigravity đứng đầu", vb.auto_brain({}) == "antigravity")
moi()
check("không gói nào sẵn -> rỗng (bộ não chính)", vb.auto_brain({}) == "")

# ---- nhớ 60 giây ----
moi("codex")
vb.auto_brain({})
_hoi.clear()
_san.clear()
check("trong 60 giây không dò lại", vb.auto_brain({}) == "codex" and _hoi == [])
vb.auto_brain({"model": {"openai_oauth": {"access_token": "a"}}})
check("nối hay ngắt ChatGPT thì dò lại ngay", _hoi != [])

# ---- config_from_settings ----
moi("codex")
c = vb.config_from_settings({"voice": {"mode": "fast", "brain_provider": ""}})
check("Làn nhanh chưa chọn bộ não -> tự chọn", c["mode"] == "fast" and c["provider"] == "codex")
c = vb.config_from_settings({"voice": {"mode": "fast", "brain_provider": "grok"}})
check("bộ não đã chọn từ bản cũ vẫn thắng", c["provider"] == "grok")
c = vb.config_from_settings({"voice": {"mode": "standard"}})
check("chế độ Chuẩn không tự chọn gì", c["mode"] == "standard" and c["provider"] == "")
c = vb.config_from_settings({"voice": {"mode": "live", "live_provider": "gemini"}})
check("khoá cũ mode=live tính như Làn nhanh", c["mode"] == "fast" and c["provider"] == "codex")
moi()
c = vb.config_from_settings({"voice": {"mode": "fast"}})
check("không gói nào sẵn -> Làn nhanh bỏ qua, đi bộ não chính", c["provider"] == "" and main._bao_lan_nhanh_bo_qua(c) is True)

# ---- đường Cơ bản của nút mic ----
codex_realtime.realtime_available = lambda cfg: (False, "no_cli")
moi("antigravity")
r = voice_call.select_call_engine({"model": {}, "voice": {"mode": "fast"}})
check("Cơ bản có bộ não tự chọn -> fast", r["engine"] == "basic" and r["voice_mode"] == "fast" and r["basic_mode"] == "fast")
moi()
r = voice_call.select_call_engine({"model": {}, "voice": {"mode": "fast"}})
check("Cơ bản không có bộ não nào -> standard", r["voice_mode"] == "standard")
r = voice_call.select_call_engine({"model": {}, "voice": {"mode": "standard", "brain_provider": "codex"}})
check("chế độ Chuẩn đã lưu vẫn là Chuẩn", r["voice_mode"] == "standard")

# ---- /voice/options?brains=0 ----
moi("claude")
_goc_cfg = main.cfgmod.read_settings
main.cfgmod.read_settings = lambda: {"model": {"openai_api_key": "k"},
                                     "voice": {"mode": "fast", "tts_provider": "openai", "openai_tts_voice": "nova",
                                               "elevenlabs_key": "", "call_engine": "basic"}}
_goc_list = main.antigravity_cli.list_models
_goi_agy = []
main.antigravity_cli.list_models = lambda: _goi_agy.append(1) or []
try:
    d = client.get("/voice/options?brains=0").json()
    check("brains=0: không chạy agy models", _goi_agy == [])
    check("brains=0: không có danh sách bộ não giọng", d.get("brain_providers") == [])
    check("trả đường gọi đang dùng", (d.get("call") or {}).get("engine") == "basic" and d["call"].get("setting") == "basic")
    check("trả giọng đọc của đường Cơ bản",
          d.get("tts") == {"provider": "openai", "openai_voice": "nova", "openai_key_set": True,
                           "elevenlabs_voice": "", "elevenlabs_key_set": False})
    check("trả bộ não giọng tự chọn kèm nhãn", (d.get("voice_brain") or {}).get("id") == "claude"
          and "Claude" in d["voice_brain"].get("label", ""))
    check("vẫn trả giọng ChatGPT Live và nhà cung cấp Live", d.get("chatgpt_voice") and d.get("live_providers"))
    # 0.65.25: ô "Bộ não trả lời nhanh" ở Nâng cao, không cần `agy models`.
    ch = {c["id"]: c["available"] for c in d.get("brain_choices") or []}
    check("brain_choices: đủ bộ não, không có dòng bộ não chính rỗng",
          "" not in ch and set(ch) == {k for k in vb.BRAIN_PROVIDERS if k})
    check("brain_choices: gói soi plan_brain_available, API soi key đã lưu",
          ch.get("claude") is True and ch.get("codex") is False and ch.get("openai") is True and ch.get("groq") is False)
    check("brain_auto: bộ não máy đang tự chọn", d.get("brain_auto") == "claude")
    d = client.get("/voice/options").json()
    check("mặc định vẫn có danh sách bộ não (client cũ)", len(d.get("brain_providers") or []) > 0 and _goi_agy == [1])
finally:
    main.antigravity_cli.list_models = _goc_list
    main.cfgmod.read_settings = _goc_cfg

# ---- brain_available ----
moi("grok")
check("brain_available: gói đang sẵn", vb.brain_available("grok", {}) is True)
check("brain_available: gói chưa sẵn", vb.brain_available("codex", {}) is False)
check("brain_available: API có key", vb.brain_available("gemini", {"model": {"gemini_api_key": "k"}}) is True)
check("brain_available: id rỗng hoặc lạ là không", vb.brain_available("", {}) is False and vb.brain_available("xyz", {}) is False)

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - bộ não giọng tự chọn")
