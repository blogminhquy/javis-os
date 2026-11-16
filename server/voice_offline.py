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


VIENEU_VOICE = "Trúc Ly"      # female, northern, natural (preset of VieNeu-TTS v3 Turbo, Apache-2.0)
_VIENEU_SCRIPT = ("import sys\nfrom vieneu import Vieneu\nv = Vieneu(precision='int8')\n"
                  "v.save(v.infer(sys.argv[1], voice=sys.argv[2]), sys.argv[3])\n")


def vieneu_available() -> bool:
    h = home()
    return (h / "vieneu-lib" / "vieneu").is_dir() and (h / "hf").is_dir()


def _to_mp3(wav: bytes) -> bytes:
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "wav", "-i", "pipe:0", "-codec:a", "libmp3lame",
                        "-q:a", "4", "-f", "mp3", "pipe:1"], input=wav, capture_output=True, timeout=60)
    return r.stdout if r.returncode == 0 else b""


def _vieneu_sync(text: str) -> bytes:
    """Vietnamese (and Vietnamese-English mixed) text read by VieNeu in its own process: its numpy and onnxruntime
    stay in `<state>/tts/vieneu-lib` and never meet the server's. Weights are in `<state>/tts/hf`, read offline."""
    import tempfile
    h = home()
    env = dict(os.environ, PYTHONPATH=str(h / "vieneu-lib"), HF_HOME=str(h / "hf"), HF_HUB_OFFLINE="1")
    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    out.close()
    try:
        r = subprocess.run([sys.executable, "-c", _VIENEU_SCRIPT, text, VIENEU_VOICE, out.name], env=env,
                           capture_output=True, text=True, timeout=180)
        wav = Path(out.name).read_bytes()
        if r.returncode != 0 or not wav:
            print(f"[voice offline] VieNeu gave no audio (exit {r.returncode}): {(r.stderr or '').strip()[-200:]}",
                  file=sys.stderr, flush=True)
            return b""
        return _to_mp3(wav)
    finally:
        try:
            os.unlink(out.name)
        except OSError:
            pass


_RUN = re.compile(r"[㐀-鿿，、。！？；]+|[^㐀-鿿，、。！？；]+")
_CLAUSE = re.compile(r"(?<=[.!?;\n])\s+")


def segments(text: str, voice: str = "") -> list:
    """[(lang, text)] in reading order: a sentence that mixes Vietnamese, English and Chinese is cut at sentence
    ends and at every change between Chinese characters and other letters; neighbours in the same language are
    joined, so each engine is started as few times as possible."""
    out: list = []
    for clause in _CLAUSE.split(str(text or "")):
        for run in _RUN.findall(clause):
            if not re.search(r"\w", run):
                continue
            lang = "zh" if _CJK.search(run) else "vi" if _VI.search(run) else ("vi" if str(voice).lower().startswith("vi") and not out else "en")
            if out and out[-1][0] == lang:
                out[-1] = (lang, out[-1][1] + " " + run.strip())
            else:
                out.append((lang, run.strip()))
    return out


def _concat(parts: list) -> bytes:
    """One mp3 from several (the engines run at different sample rates, so they are decoded and joined)."""
    import tempfile
    tmp = tempfile.mkdtemp()
    try:
        cmd = ["ffmpeg", "-loglevel", "error", "-y"]
        for i, b in enumerate(parts):
            p = Path(tmp) / f"{i}.mp3"
            p.write_bytes(b)
            cmd += ["-i", str(p)]
        cmd += ["-filter_complex", "".join(f"[{i}:a]aresample=24000[a{i}];" for i in range(len(parts)))
                + "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[o]",
                "-map", "[o]", "-codec:a", "libmp3lame", "-q:a", "4", "-f", "mp3", "pipe:1"]
        r = subprocess.run(cmd, capture_output=True, timeout=90)
        return r.stdout if r.returncode == 0 else b""
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


async def speak(text: str, voice: str = "") -> bytes:
    """mp3 bytes, or b"" when an offline voice is missing or fails (never raises). Mixed-language text is read
    piece by piece, each in its own language."""
    segs = segments(text, voice)
    if len(segs) <= 1:
        return await _speak_one(text, language(text, voice))
    parts = []
    for lang, seg in segs:
        b = await _speak_one(seg, lang)
        if not b:
            return b""
        parts.append(b)
    try:
        return await asyncio.to_thread(_concat, parts)
    except Exception as e:      # noqa: BLE001
        print(f"[voice offline] joining failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return b""


async def _speak_one(text: str, lang: str) -> bytes:
    if lang == "vi" and vieneu_available():
        try:
            mp3 = await asyncio.to_thread(_vieneu_sync, text)
            if mp3:
                return mp3
        except Exception as e:      # noqa: BLE001
            print(f"[voice offline] VieNeu failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
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
