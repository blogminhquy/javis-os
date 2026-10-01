"""Chọn ĐƯỜNG GỌI cho nút mic (docs/dev/2026-10-voice-call-spec.md mục 3.1, 0.65.18).

Bấm mic là gọi Javis. Cuộc gọi chạy bằng một trong ba đường, máy tự chọn theo thứ tự:
  chatgpt - ChatGPT Live qua gói ChatGPT (Codex app-server, không cần key);
  api     - Live qua API key (Gemini Live, OpenAI Realtime, GPT-Live);
  basic   - Cơ bản: Web Speech + tai nghe lại + Làn nhanh hay bộ não chính + giọng Edge.

Khoá `voice.call_engine` = auto | chatgpt | api | basic, thiếu là auto. Chọn tay mà đường đó không
chạy được thì rơi xuống đường kế tiếp và báo lý do, giống voice_ear.select_ear. Khoá cũ
`voice.mode = live` với một nhà cung cấp API là người dùng đã CHỌN Live API: giữ nguyên lựa chọn
đó, auto không được âm thầm đổi giọng và nhà cung cấp họ đã quen.
"""
from __future__ import annotations

import codex_realtime
import voice_brain

ENGINES = ("auto", "chatgpt", "api", "basic")
API_PROVIDERS = ("gemini", "openai", "gpt-live")
_API_KEY = {"gemini": "gemini_api_key", "openai": "openai_api_key", "gpt-live": "openai_api_key"}


def setting(cfg: dict) -> str:
    v = (cfg or {}).get("voice") or {}
    eng = v.get("call_engine")
    if eng in ENGINES:
        return eng
    if v.get("mode") == "live":
        prov = str(v.get("live_provider") or "")
        if prov == "chatgpt":
            return "chatgpt"
        if prov in API_PROVIDERS:
            return "api"
    return "auto"


def _api_provider(cfg: dict) -> str:
    """Nhà cung cấp Live qua API dùng được: cái người dùng đã chọn nếu có key, không thì cái đầu tiên có key."""
    v = (cfg or {}).get("voice") or {}
    m = (cfg or {}).get("model") or {}
    pref = str(v.get("live_provider") or "")
    order = ([pref] if pref in API_PROVIDERS else []) + [p for p in API_PROVIDERS if p != pref]
    for p in order:
        if str(m.get(_API_KEY[p]) or "").strip():
            return p
    return ""


def _basic_mode(cfg: dict) -> str:
    """fast khi đường Cơ bản có bộ não giọng: đã chọn từ bản cũ, hoặc máy tự chọn bộ não đầu tiên
    sẵn trên gói (voice_brain.auto_brain, 0.65.19). Không có thì standard: tin đi bộ não chính."""
    v = (cfg or {}).get("voice") or {}
    if v.get("mode") == "standard":
        return "standard"
    return "fast" if voice_brain.config_from_settings(cfg).get("provider") else "standard"


def select_call_engine(cfg: dict) -> dict:
    """{"engine", "live_provider", "voice_mode", "basic_mode", "setting", "reason", "detail"}.

    voice_mode là thứ trình duyệt dùng: "live" cho chatgpt/api, "fast"/"standard" cho basic.
    reason: auto | auto_api | auto_basic | chosen | chosen_unavailable. detail: vì sao ChatGPT
    Live chưa dùng được (no_cli | no_login | old_cli) khi điều đó làm đường gọi rơi xuống.
    """
    choice = setting(cfg)
    chat_ok, why = codex_realtime.realtime_available(cfg)
    api = _api_provider(cfg)

    def out(engine, reason, provider=""):
        return {"engine": engine, "live_provider": provider,
                "voice_mode": "live" if engine in ("chatgpt", "api") else _basic_mode(cfg),
                # Đường Cơ bản dự phòng khi Live mở không được giữa chừng (trình duyệt tự chuyển).
                "basic_mode": _basic_mode(cfg),
                "setting": choice, "reason": reason, "detail": "" if chat_ok else why}

    if choice == "basic":
        return out("basic", "chosen")
    if choice == "chatgpt":
        if chat_ok:
            return out("chatgpt", "chosen", "chatgpt")
        return out("api", "chosen_unavailable", api) if api else out("basic", "chosen_unavailable")
    if choice == "api":
        return out("api", "chosen", api) if api else out("basic", "chosen_unavailable")
    if chat_ok:
        return out("chatgpt", "auto", "chatgpt")
    if api:
        return out("api", "auto_api", api)
    return out("basic", "auto_basic")


def live_settings(cfg: dict) -> dict:
    """Bản sao cài đặt cho /ws/voice-live, live_provider theo đường đã chọn (khoá cũ không quyết)."""
    sel = select_call_engine(cfg)
    if not sel["live_provider"]:
        return cfg
    out = dict(cfg or {})
    out["voice"] = dict((cfg or {}).get("voice") or {}, live_provider=sel["live_provider"])
    return out
