"""A video a customer sends, turned into something the bot's model can take in (0.433.0).

Field report 2026-11-01 (a phone-repair shop on personal Zalo): a customer sent a video of the faulty machine, the
bot answered "em chưa xem được video" twice and the customer had to call. No model brain Javis runs takes a video as
input, and before this module the video message never even reached the bot's turn.

What the bot gets instead, and what it is TOLD it got:
  - `FRAMES` still frames spread evenly over the clip (ffmpeg), sent as images through the same path as a photo
    (`chatbot_runtime.anh_cho_bot`), so every brain that sees photos sees the video;
  - what is said in the video, when a speech-to-text key is set (`transcribe`, the same Groq Whisper the voice
    messages use), because a customer filming a fault often explains it out loud;
  - one note saying exactly that: frames only, the clip length, and whether the sound was heard. A brain that cannot
    take images still gets the honest "you cannot see this video" label, never a guess.

Safety: the link comes from a chat message, so it is downloaded with the pinned-IP, size-capped downloader of Zalo
files (`zalo_attachments.fetch_file`), the clip is deleted right after the frames are cut, and ffmpeg only ever reads
that local file. Results are cached per link, so a follow-up message about the same video does not download it again.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional

import winproc

FRAMES = 4                       # = vision_input.MAX_IMAGES: one turn never carries more images than that
MAX_VIDEO_BYTES = 60 * 1024 * 1024
FRAME_SIDE = 1024                # long side of a frame; enough to read a label or an error screen
FFMPEG_TIMEOUT = 60
MAX_TRANSCRIBE_SECONDS = 600     # longer clips are not sent to speech-to-text (cost, and Groq's size cap)
CACHE_SECONDS = 3600
_CACHE: Dict[str, dict] = {}     # url -> {"ts", "frames", "duration", "speech", "why"}
_BUSY: Dict[str, asyncio.Lock] = {}

Transcribe = Callable[[bytes, str], Awaitable[dict]]


def available() -> bool:
    """ffmpeg and ffprobe on PATH (installed by install.sh and the Docker image)."""
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


async def _run(*args: str, timeout: float = FFMPEG_TIMEOUT) -> tuple:
    """(return code, stdout bytes, stderr text) of one ffmpeg/ffprobe call, killed on timeout."""
    proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.DEVNULL,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                **winproc.kwargs_no_window())
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, b"", "timeout"
    return proc.returncode, out, err.decode("utf-8", "replace")[-300:]


async def probe(path: Path) -> dict:
    """{"duration": seconds (0 when unknown), "video": has a picture stream, "audio": has a sound stream}."""
    code, out, _err = await _run("ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                                 "-of", "json", str(path))
    if code != 0:
        return {"duration": 0.0, "video": False, "audio": False}
    try:
        data = json.loads(out.decode("utf-8", "replace") or "{}")
    except ValueError:
        data = {}
    kinds = {str(s.get("codec_type") or "") for s in data.get("streams") or [] if isinstance(s, dict)}
    try:
        dur = max(0.0, float((data.get("format") or {}).get("duration") or 0))
    except (TypeError, ValueError):
        dur = 0.0
    return {"duration": dur, "video": "video" in kinds, "audio": "audio" in kinds}


def frame_times(duration: float, n: int = FRAMES) -> List[float]:
    """Moments to cut `n` frames at: spread evenly, never the very first or last instant (often black or blurred)."""
    if duration <= 0:
        return [0.0]
    n = max(1, int(n))
    return [round(duration * (i + 0.5) / n, 2) for i in range(n)]


def clock(seconds: float) -> str:
    s = int(round(max(0.0, float(seconds))))
    return f"{s // 60}:{s % 60:02d}"


async def cut_frames(video: Path, dest: Path, stem: str, duration: float) -> List[tuple]:
    """[(path, second)] of the frames cut from `video` into `dest`, oldest first. Missing frames are skipped."""
    out = []
    scale = f"scale='if(gt(iw,ih),min({FRAME_SIDE},iw),-2)':'if(gt(iw,ih),-2,min({FRAME_SIDE},ih))'"
    for i, t in enumerate(frame_times(duration)):
        p = dest / f"{stem}_f{i + 1}.jpg"
        code, _o, _e = await _run("ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(t), "-i", str(video),
                                  "-frames:v", "1", "-vf", scale, "-q:v", "4", str(p))
        if code == 0 and p.exists() and p.stat().st_size > 0:
            out.append((p, t))
        else:
            p.unlink(missing_ok=True)
    return out


async def sound_of(video: Path, dest: Path, stem: str) -> Optional[bytes]:
    """The clip's sound as a small mono mp3 (what speech-to-text needs), or None."""
    p = dest / f"{stem}_audio.mp3"
    try:
        code, _o, _e = await _run("ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1",
                                  "-ar", "16000", "-b:a", "32k", str(p))
        if code != 0 or not p.exists():
            return None
        return p.read_bytes() or None
    finally:
        p.unlink(missing_ok=True)


async def look(url: str, dest: Path, msg_id: str, transcribe: Optional[Transcribe] = None) -> dict:
    """Frames (and speech) of the video at `url`, saved in `dest`. Cached per link for `CACHE_SECONDS`.

    Returns {"frames": [(path, second)], "duration", "speech": text or "", "heard": sound was transcribed,
    "why": reason nothing could be shown ("" on success)}. Never raises for a bad video or link."""
    url = str(url or "").strip()
    now = time.time()
    for k in [k for k, v in _CACHE.items() if now - v["ts"] > CACHE_SECONDS]:
        _CACHE.pop(k, None)
    hit = _CACHE.get(url)
    if hit and all(Path(p).exists() for p, _t in hit["frames"]):
        return hit
    lock = _BUSY.setdefault(url, asyncio.Lock())
    async with lock:
        hit = _CACHE.get(url)
        if hit and all(Path(p).exists() for p, _t in hit["frames"]):
            return hit
        res = await _look(url, Path(dest), msg_id, transcribe)
        if res["frames"]:
            _CACHE[url] = dict(res, ts=time.time())
        _BUSY.pop(url, None)
        return res


async def _look(url: str, dest: Path, msg_id: str, transcribe: Optional[Transcribe]) -> dict:
    res = {"frames": [], "duration": 0.0, "speech": "", "heard": False, "why": ""}
    if not url:
        res["why"] = "tin video không kèm link tải"
        return res
    if not available():
        res["why"] = "máy chủ Javis chưa cài ffmpeg"
        return res
    import image_vision
    import zalo_attachments
    stem = "video_" + (image_vision.SAFE_PART.sub("_", str(msg_id or ""))[:40] or str(int(time.time())))
    saved, why = await zalo_attachments.fetch_file({"url": url, "name": stem + ".mp4"}, dest, MAX_VIDEO_BYTES)
    if not saved:
        res["why"] = "không tải được video: " + why
        return res
    try:
        info = await probe(saved)
        if not info["video"]:
            res["why"] = "file tải về không phải video đọc được"
            return res
        res["duration"] = info["duration"]
        res["frames"] = await cut_frames(saved, dest, stem, info["duration"])
        if not res["frames"]:
            res["why"] = "không cắt được khung hình nào từ video"
            return res
        if info["audio"] and transcribe and info["duration"] <= MAX_TRANSCRIBE_SECONDS:
            data = await sound_of(saved, dest, stem)
            if data:
                try:
                    heard = await transcribe(data, stem + ".mp3")
                except Exception as e:      # noqa: BLE001 - no speech is fine, the frames still go through
                    heard = {"ok": False}
                    print(f"[video] speech-to-text failed: {type(e).__name__}", file=sys.stderr)
                if (heard or {}).get("ok"):
                    res["heard"] = True
                    res["speech"] = str(heard.get("text") or "").strip()[:4000]
        return res
    except Exception as e:      # noqa: BLE001 - a broken clip must never cost the customer the reply
        res["frames"] = []
        res["why"] = f"xử lý video lỗi: {type(e).__name__}"
        return res
    finally:
        Path(saved).unlink(missing_ok=True)


def note(res: dict, earlier: str = "") -> str:
    """The line in front of the customer's words that says what the model is looking at.

    `earlier`: "HH:MM" when the video was sent in an earlier message of this chat (a follow-up turn)."""
    when = f" lúc {earlier}" if earlier else ""
    if not res.get("frames"):
        return (f"(khách gửi kèm một video{when} nhưng bạn KHÔNG xem được nội dung ({res.get('why') or 'không rõ lý do'}). "
                "Đừng nói như đã xem; nhờ khách tả lại bằng chữ hoặc chụp ảnh chỗ cần xem.) ")
    moc = ", ".join(clock(t) for _p, t in res["frames"])
    dai = f" dài {clock(res['duration'])}" if res.get("duration") else ""
    s = (f"(khách gửi kèm một video{dai}{when}. Bạn không xem được video trực tiếp: các ảnh đi kèm lượt này là "
         f"{len(res['frames'])} khung hình cắt từ video theo thứ tự thời gian ({moc}). Trả lời dựa trên những gì thấy "
         "trong các khung hình; chi tiết nào không thấy rõ thì hỏi lại khách, đừng đoán.")
    if res.get("heard"):
        s += (" Lời nói trong video (máy nghe chép lại, có thể sai vài chữ): \"" + res["speech"].replace('"', "'") + "\"."
              if res.get("speech") else " Video không có lời nói nghe được.")
    else:
        s += " Bạn không nghe được tiếng trong video."
    return s + ") "
