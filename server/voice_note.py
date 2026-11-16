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


def valid_edge_voice(voice) -> bool:
    """An Edge voice name, or "auto" (follow the language of the text)."""
    v = str(voice or "").strip()
    return v == "auto" or bool(_VOICE_RE.match(v))


def _english(text: str) -> bool:
    """An English note that names a Vietnamese page or person is still English (2026-11-08)."""
    try:
        import phien_am
        return phien_am.is_english_text(text)
    except Exception:
        return False


def pick_voice(text: str, voice: str = "", chosen: str = "") -> str:
    """The voice the tool named, else the owner's Edge voice from Settings matched to the language
    of the note (owner, 2026-11-08): Vietnamese is read by a Vietnamese voice, English by a voice
    that speaks English, of the same gender as the one picked (phien_am.speech_plan). Nothing
    picked, or "auto": the language default."""
    v = str(voice or "").strip()
    if v and _VOICE_RE.match(v):
        return v
    c = str(chosen or "").strip()
    if c != "auto" and _VOICE_RE.match(c):
        try:
            import phien_am
            return phien_am.speech_plan(text, c)[1]
        except Exception:
            return c
    vi = bool(_VI_CHARS.search(text or "")) and not _english(text)
    if vi:
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
    v = pick_voice(words, voice, _chosen_edge_voice())
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


def _chosen_edge_voice() -> str:
    """The Edge voice picked in Settings > Voice (0.298.0), "" when none or unreadable."""
    try:
        import config as cfgmod
        return str(((cfgmod.read_settings() or {}).get("voice") or {}).get("edge_voice") or "")
    except Exception:  # noqa: BLE001
        return ""


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
        text, voice = phien_am.speech_plan(text, voice)
    except Exception:
        pass
    out = b""
    try:
        async for chunk in edge_tts.Communicate(text, voice, rate="+0%").stream():
            if chunk.get("type") == "audio":
                out += chunk.get("data") or b""
    except Exception as e:  # noqa: BLE001 - NoAudioReceived: a long-running process can keep a stale token
        import sys
        print(f"[voice note] Edge in-process failed ({type(e).__name__}: {e}); trying a fresh process",
              file=sys.stderr, flush=True)
        out = b""
    return out or await _edge_fresh_process(text, voice) or await _google_tts(text, voice)


async def _google_tts(text: str, voice: str) -> bytes:
    """Last resort when Edge keeps answering NoAudioReceived (the VPS, 2026-11-16): Google Translate's
    public speech endpoint, in chunks of at most 180 characters, joined into one mp3."""
    import sys
    import httpx
    lang = (voice or "vi")[:2].lower() or "vi"
    words, chunks, cur = str(text or "").split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > 180:
            chunks.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        chunks.append(cur)
    out = b""
    try:
        async with httpx.AsyncClient(timeout=20, headers={"User-Agent": "Mozilla/5.0"}) as c:
            for i, part in enumerate(chunks):
                r = await c.get("https://translate.google.com/translate_tts",
                                params={"ie": "UTF-8", "client": "tw-ob", "tl": lang, "q": part,
                                        "total": len(chunks), "idx": i, "textlen": len(part)})
                if r.status_code != 200 or not r.content:
                    print(f"[voice note] Google speech answered {r.status_code}", file=sys.stderr, flush=True)
                    return b""
                out += r.content
    except Exception as e:  # noqa: BLE001
        print(f"[voice note] Google speech failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return b""
    return out


async def _edge_fresh_process(text: str, voice: str) -> bytes:
    """Same voice, asked from a fresh python process. A server that has run for a while sometimes gets
    `NoAudioReceived` from Edge while a new process is answered normally (seen on the VPS, 2026-11-16)."""
    import asyncio
    import sys
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "edge_tts", "--voice", voice, "--text", text, "--write-media", tmp.name,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        try:
            _o, err = await asyncio.wait_for(proc.communicate(), timeout=45)
        except asyncio.TimeoutError:
            proc.kill()
            print("[voice note] fresh Edge process timed out", file=sys.stderr, flush=True)
            return b""
        audio = Path(tmp.name).read_bytes()
        if not audio:
            tail = (err or b"").decode(errors="replace").strip().splitlines()[-1:] or [""]
            print(f"[voice note] fresh Edge process gave no audio (exit {proc.returncode}, voice={voice}, text={text[:80]!r}): {tail[0][:200]}",
                  file=sys.stderr, flush=True)
        return audio
    except Exception as e:  # noqa: BLE001
        print(f"[voice note] fresh Edge process failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return b""
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
