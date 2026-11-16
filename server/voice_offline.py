"""Offline voices (Piper): Vietnamese, English and Chinese read aloud with no internet (2026-11-16).

The engine and the three voice files live in `<state>/tts` (`lib/` = the piper-tts package, `voices/` = the .onnx
models and their .json), outside the app image, so an update does not remove them and a reminder can be spoken at
any hour even when the free online voice refuses the server. Missing files just mean `speak` returns b"" and the
caller falls back to the online voice.

Setup (once per machine, also done by `python server/voice_offline.py install`):
    pip install --target <state>/tts/lib piper-tts
    voices from https://huggingface.co/rhasspy/piper-voices (vi_VN-vais1000, en_US-lessac, zh_CN-huayan, all "medium")
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import subprocess
import sys
import wave
from pathlib import Path
from typing import Dict, Optional

VOICES = {
    "vi": "vi_VN-vais1000-medium",
    "en": "en_US-lessac-medium",
    "zh": "zh_CN-huayan-medium",
}
_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
_PATHS = {
    "vi": "vi/vi_VN/vais1000/medium/",
    "en": "en/en_US/lessac/medium/",
    "zh": "zh/zh_CN/huayan/medium/",
}
_CJK = re.compile(r"[㐀-鿿]")
_VI = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹáàãéèíìĩóòõúùũý]", re.I)
_LOADED: Dict[str, object] = {}


def home() -> Path:
    try:
        import config as cfg
        return Path(cfg.STATE_DIR) / "tts"
    except Exception:       # noqa: BLE001
        return Path(os.getenv("JAVIS_STATE_DIR", ".")) / "tts"


def language(text: str, voice: str = "") -> str:
    """vi, en or zh: Chinese characters win, then Vietnamese letters, then the language of the named voice."""
    t = str(text or "")
    if _CJK.search(t):
        return "zh"
    if _VI.search(t):
        return "vi"
    v = str(voice or "").lower()
    return "zh" if v.startswith("zh") else "vi" if v.startswith("vi") else "en"


def available(lang: str) -> bool:
    h = home()
    return (h / "lib" / "piper").is_dir() and (h / "voices" / f"{VOICES[lang]}.onnx").is_file()


def _load(lang: str):
    if lang not in _LOADED:
        lib = str(home() / "lib")
        if lib not in sys.path:
            sys.path.append(lib)
        from piper import PiperVoice
        _LOADED[lang] = PiperVoice.load(str(home() / "voices" / f"{VOICES[lang]}.onnx"))
    return _LOADED[lang]


def _speak_sync(text: str, lang: str) -> bytes:
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    _load(lang).synthesize_wav(text, w)
    w.close()
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "wav", "-i", "pipe:0", "-codec:a", "libmp3lame",
                        "-q:a", "4", "-f", "mp3", "pipe:1"], input=buf.getvalue(), capture_output=True, timeout=60)
    return r.stdout if r.returncode == 0 else b""


async def speak(text: str, voice: str = "") -> bytes:
    """mp3 bytes, or b"" when the offline voice is not installed or fails (never raises)."""
    lang = language(text, voice)
    if not available(lang):
        return b""
    try:
        return await asyncio.to_thread(_speak_sync, text, lang)
    except Exception as e:      # noqa: BLE001
        print(f"[voice offline] {lang} failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return b""


def offline_first(online):
    """A `synth(text, voice)` for voice_note.make: offline voice first, the given online one when it gives nothing."""
    async def synth(text: str, voice: str) -> bytes:
        return await speak(text, voice) or await online(text, voice)
    return synth


def install(target: Optional[Path] = None) -> None:
    """Download the engine and the three voices into `<state>/tts` (needs internet once)."""
    import urllib.request
    h = Path(target) if target else home()
    (h / "voices").mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--target", str(h / "lib"), "piper-tts"], check=True)
    for lang, name in VOICES.items():
        for ext in (".onnx", ".onnx.json"):
            dst = h / "voices" / (name + ext)
            if not dst.exists():
                urllib.request.urlretrieve(_BASE + _PATHS[lang] + name + ext, dst)
            print(dst, dst.stat().st_size)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "install":
    install()
