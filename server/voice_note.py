"""Voice notes: Javis records a short spoken message and attaches it to its answer (0.202.0).

Idea borrowed from OpenMausBot's voice notes. Some answers are better heard than read: a morning
summary to play while driving, a reminder read out to someone at home. The tool `javis_voice_note`
(bundled plugin `voice-note`) turns a short text into an mp3 in the brain's `attachments/voice/`,
and the answer embeds it; the dashboard draws an audio player (chat-render.js), Telegram and the
other channels send the file. The same text stays as the visible caption, so the chat is still
readable and searchable without playing anything.

Edge TTS (free, the app's default voice engine), picked by the language of the text unless a
voice is named. At most MAX_CHARS characters, the same limit OpenMausBot uses.

0.255.0: when ElevenLabs is the chosen voice (Settings > Voice) the note is spoken by it, so Javis
sounds the same in a note as in the chat. If ElevenLabs fails (quota, key revoked) the note falls
back to Edge rather than not being made.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

MAX_CHARS = 1000
VI_VOICE = "vi-VN-HoaiMyNeural"
DEFAULT_VOICE = "en-US-EmmaMultilingualNeural"
_VI_CHARS = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", re.I)
_VOICE_RE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+Neural$")


def pick_voice(text: str, voice: str = "") -> str:
    v = str(voice or "").strip()
    if v and _VOICE_RE.match(v):
        return v
    if _VI_CHARS.search(text or ""):
        return VI_VOICE
    return os.getenv("TTS_VOICE", "") or DEFAULT_VOICE


def spoken(text: str) -> str:
    """What the voice reads: markdown syntax and links dropped, the words kept."""
    t = re.sub(r"```.*?```", " ", str(text or ""), flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"[*_`#>|]+", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


async def make(vault_root: str, text: str, voice: str = "", synth=None) -> dict:
    """{ok, rel_path, voice, chars} or {ok: False, error}. `synth(text, voice) -> bytes` is injectable
    for tests; the default is Edge TTS."""
    if not vault_root:
        return {"ok": False, "error": "no brain for this turn"}
    words = spoken(text)
    if not words:
        return {"ok": False, "error": "empty text"}
    if len(words) > MAX_CHARS:
        return {"ok": False, "error": f"text longer than {MAX_CHARS} characters; shorten it"}
    v = pick_voice(words, voice)
    if synth is None:
        synth = _chosen_synth()
    try:
        audio = await synth(words, v)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if not audio:
        return {"ok": False, "error": "the voice engine returned no audio"}
    folder = Path(vault_root) / "attachments" / "voice"
    folder.mkdir(parents=True, exist_ok=True)
    name = time.strftime("voice-%Y%m%d-%H%M%S") + f"-{os.getpid() % 1000:03d}.mp3"
    path = folder / name
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(audio)
    os.replace(tmp, path)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return {"ok": True, "rel_path": f"attachments/voice/{name}", "voice": v, "chars": len(words)}


def _chosen_synth():
    """ElevenLabs when it is the chosen voice and has a key, else Edge."""
    try:
        import config as cfgmod
        import tts_eleven
        cfg = cfgmod.read_settings()
        if not tts_eleven.chosen(cfg):
            return _edge
    except Exception:  # noqa: BLE001
        return _edge

    async def eleven_then_edge(text: str, voice: str) -> bytes:
        try:
            return await tts_eleven.synth(text, cfg)
        except Exception as e:  # noqa: BLE001
            import sys
            print(f"[voice note] ElevenLabs failed ({type(e).__name__}), using Edge", file=sys.stderr)
            return await _edge(text, voice)

    return eleven_then_edge


async def _edge(text: str, voice: str) -> bytes:
    import edge_tts   # lazy: optional feature, kept off the startup path (see test_khoi_dong_nhe)
    try:
        import phien_am
        text = phien_am.doc_viet(text)
    except Exception:
        pass
    out = b""
    async for chunk in edge_tts.Communicate(text, voice, rate="+0%").stream():
        if chunk.get("type") == "audio":
            out += chunk.get("data") or b""
    return out
