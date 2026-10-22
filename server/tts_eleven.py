"""ElevenLabs voice for Javis (0.255.0): speech for read-aloud, the Basic call path and voice notes.

Owner, 2026-10-20: "đang thiếu mất ElevenLabs để làm giọng của Javis". The provider existed since the
first settings page, but three things kept it out of reach:

- The default model `eleven_multilingual_v2` has no Vietnamese (its 29 languages leave it out;
  Flash v2.5 adds hu, no, vi, and Eleven v3 covers 70+). Vietnamese answers came out in a foreign
  accent. The default is now Flash v2.5, and a saved v2 (written by older versions without anyone
  choosing it) is read as Flash v2.5 when the text is Vietnamese.
- The voice had to be pasted as a raw Voice ID. `list_voices` reads the account's own voices
  (premade, cloned, designed) so the settings page can offer them by name.
- Voice notes (`javis_voice_note`) always used Edge. They now use ElevenLabs when it is the chosen
  voice, falling back to Edge if ElevenLabs fails (quota, key revoked), so a note is never lost.

Sources: https://elevenlabs.io/docs/overview/models (languages per model), API reference for
`POST /v1/text-to-speech/{voice_id}` and `GET /v1/voices`.
"""
from __future__ import annotations

import re

API = "https://api.elevenlabs.io"
DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"   # Rachel, premade, available on every account
DEFAULT_MODEL = "eleven_flash_v2_5"

# Model id -> whether it speaks Vietnamese. Order is the order shown on the settings page.
MODELS = {
    "eleven_flash_v2_5": True,       # fast (~75 ms), 32 languages incl. Vietnamese, half the credits
    "eleven_v3": True,               # most expressive, 70+ languages, slower
    "eleven_turbo_v2_5": True,       # older fast model, same 32 languages
    "eleven_multilingual_v2": False, # 29 languages, no Vietnamese
}

_VI_CHARS = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", re.I)


def effective_model(model: str, text: str) -> str:
    """The model actually sent: an unknown or empty one becomes the default, and one without
    Vietnamese becomes the default when the text is Vietnamese."""
    m = str(model or "").strip()
    if m not in MODELS:
        return DEFAULT_MODEL
    if not MODELS[m] and _VI_CHARS.search(text or ""):
        return DEFAULT_MODEL
    return m


def settings(cfg: dict) -> dict:
    v = (cfg or {}).get("voice") or {}
    return {"key": str(v.get("elevenlabs_key") or "").strip(),
            "voice": str(v.get("elevenlabs_voice") or "").strip() or DEFAULT_VOICE,
            "model": str(v.get("elevenlabs_model") or "").strip()}


def chosen(cfg: dict) -> bool:
    """ElevenLabs is the chosen voice and has a key."""
    v = (cfg or {}).get("voice") or {}
    return str(v.get("tts_provider") or "").lower() == "elevenlabs" and bool(settings(cfg)["key"])


async def synth(text: str, cfg: dict) -> bytes:
    import httpx
    s = settings(cfg)
    if not s["key"]:
        raise RuntimeError("no ElevenLabs API key")
    payload = {"text": text, "model_id": effective_model(s["model"], text)}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{API}/v1/text-to-speech/{s['voice']}",
                              headers={"xi-api-key": s["key"], "accept": "audio/mpeg"},
                              json=payload, params={"output_format": "mp3_44100_128"})
        r.raise_for_status()
        return r.content


def _voice_row(x: dict) -> dict:
    labels = x.get("labels") or {}
    return {"id": str(x.get("voice_id") or ""), "name": str(x.get("name") or ""),
            "category": str(x.get("category") or ""),
            "gender": str(labels.get("gender") or ""), "accent": str(labels.get("accent") or "")}


def sort_voices(voices: list) -> list:
    """The account's own voices (cloned, designed, professional) first, then premade, each by name."""
    rows = [_voice_row(x) for x in voices or [] if isinstance(x, dict) and x.get("voice_id")]
    return sorted(rows, key=lambda r: (r["category"] == "premade", r["name"].lower()))


async def list_voices(key: str) -> dict:
    """{ok, voices} or {ok: False, reason}: reason is "no_key", "bad_key" or "network"."""
    import httpx
    if not key:
        return {"ok": False, "reason": "no_key"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{API}/v1/voices", headers={"xi-api-key": key})
    except httpx.HTTPError:
        return {"ok": False, "reason": "network"}
    if r.status_code in (401, 403):
        return {"ok": False, "reason": "bad_key"}
    if r.status_code >= 400:
        return {"ok": False, "reason": "network"}
    try:
        return {"ok": True, "voices": sort_voices((r.json() or {}).get("voices") or [])}
    except ValueError:
        return {"ok": False, "reason": "network"}
