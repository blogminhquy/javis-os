"""Voice messages in `zalo_get_history` come with what they said (`transcript`).

JumboKiz, 21/11/2026: a recurring job reading the owner's wife on personal Zalo met three voice messages in a row and
could only answer "please type it", because javis-zalo gives a voice note as a bare CDN link (`type: chat.voice`,
`text` = the `.aac` URL) and nothing in a model's turn could hear it. The customer bots already heard voice
(`chatbot_runtime.nghe_cho_bot`); the history tool, which every brain and background job reads, did not.

What this does: when a MODEL reads `zalo_get_history` (never an internal caller, see `mcp_hub._shaped_call`), each voice
message gets `transcript` (the words, heard by the same ears as Telegram and the Zalo bot: `main._stt_nghe`) or
`transcript_error` (why it could not be heard, so the model asks the sender to type instead of guessing).

Cost limits, because a history call is cheap and hearing is not:
- A transcript is kept per URL (`STATE_DIR/zalo_voice_transcripts.json`, newest `CACHE_MAX`), so a job reading the
  same thread every 5 minutes hears each voice message once.
- At most `MAX_NEW` new messages are heard per call, newest first, within `BUDGET_S` seconds in total. The rest get
  `transcript_error` saying so; the next call hears them.
- Only `https://` links on Zalo's own CDN (`*.zdn.vn`) are fetched, through the size-capped downloader.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from config import STATE_DIR

TOOL = "zalo_get_history"
CACHE_FILE = STATE_DIR / "zalo_voice_transcripts.json"
CACHE_MAX = 500
MAX_NEW = 3
BUDGET_S = 240.0
MAX_BYTES = 25 * 1024 * 1024
NOTE = "máy nghe chép lại, có thể sai vài chữ, nhất là tên riêng và con số"

# async (bytes, file name) -> {"ok", "text"} | {"ok": False, "ly_do"}; set by main.py (`_stt_nghe`). None = no ear.
HEAR: Optional[Callable] = None

_lock = threading.Lock()


def _load() -> dict:
    try:
        d = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> None:
    if len(d) > CACHE_MAX:
        keep = sorted(d.items(), key=lambda kv: kv[1].get("ts", 0))[-CACHE_MAX:]
        d = dict(keep)
    tmp = CACHE_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(CACHE_FILE)
    except OSError as e:
        print(f"[zalo voice] cache: {e}", file=sys.stderr)


def voice_url(msg: dict) -> str:
    """The `.aac` link of a voice message, or "" when `msg` is not one (or the link is not Zalo's CDN)."""
    if not isinstance(msg, dict):
        return ""
    att = msg.get("attachment") if isinstance(msg.get("attachment"), dict) else {}
    kind = str(msg.get("type") or att.get("type") or "").lower()
    url = str(att.get("url") or "").strip()
    text = str(msg.get("text") or "").strip()
    if not url and text.startswith("https://") and " " not in text:
        url = text
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower()
    if urlparse(url).scheme != "https" or not host.endswith(".zdn.vn"):
        return ""
    if "voice" in kind or "voice-aac" in host or url.split("?", 1)[0].lower().endswith(".aac"):
        return url
    return ""


def _why(res: dict) -> str:
    ly_do = str((res or {}).get("ly_do") or "")
    if ly_do == "khong_nghe_ro":
        return "không nghe ra lời nào trong tin thoại"
    if ly_do == "thieu_key":
        return ("Javis chưa có bộ nghe: cài Bộ nghe offline ở trang Công cụ, hoặc thêm key Groq/OpenAI/Gemini "
                "hay đăng nhập gói ChatGPT ở trang Models")
    if ly_do == "qua_lon":
        return "tin thoại quá lớn để nghe"
    return "không nghe được tin thoại" + (f" ({ly_do})" if ly_do else "")


async def _hear(url: str) -> dict:
    """{"text"} or {"error"} for one link. Never raises."""
    import zalo_attachments
    if HEAR is None:
        return {"error": _why({"ly_do": "thieu_key"})}
    name = url.split("?", 1)[0].rsplit("/", 1)[-1] or "voice.aac"
    try:
        with tempfile.TemporaryDirectory(prefix="javis-zvoice-") as d:
            saved, why = await zalo_attachments.fetch_file({"url": url, "name": name}, Path(d), MAX_BYTES)
            if not saved:
                return {"error": f"không tải được tin thoại: {why}"}
            res = await HEAR(Path(saved).read_bytes(), Path(saved).name)
    except Exception as e:      # noqa: BLE001 - a broken ear must never cost the history
        return {"error": f"không nghe được tin thoại ({type(e).__name__})"}
    text = str((res or {}).get("text") or "").strip()
    if (res or {}).get("ok") and text:
        return {"text": text}
    return {"error": _why(res)}


async def enrich(result):
    """`zalo_get_history` result (JSON text) -> the same, each voice message carrying `transcript` or
    `transcript_error`. Anything that is not a history JSON comes back untouched."""
    if not isinstance(result, str) or '"messages"' not in result:
        return result
    try:
        data = json.loads(result)
    except ValueError:
        return result
    msgs = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(msgs, list):
        return result
    voices = [(m, u) for m in msgs if (u := voice_url(m))]
    if not voices:
        return result
    with _lock:
        cache = _load()
    heard_new, start = 0, time.monotonic()
    changed = False
    for m, url in reversed(voices):          # newest first: the message a reply is waiting on
        hit = cache.get(url)
        if hit and hit.get("text"):
            m["transcript"] = hit["text"]
            continue
        if heard_new >= MAX_NEW or time.monotonic() - start > BUDGET_S:
            m["transcript_error"] = ("chưa nghe tới tin này (mỗi lần đọc chỉ nghe vài tin mới nhất), "
                                     "gọi lại zalo_get_history là nghe tiếp")
            continue
        heard_new += 1
        left = max(5.0, BUDGET_S - (time.monotonic() - start))
        try:
            got = await asyncio.wait_for(_hear(url), left)
        except asyncio.TimeoutError:
            got = {"error": "nghe tin thoại quá lâu nên bỏ dở, gọi lại để thử tiếp"}
        if got.get("text"):
            m["transcript"] = got["text"]
            cache[url] = {"text": got["text"], "ts": time.time()}
            changed = True
        else:
            m["transcript_error"] = got.get("error") or "không nghe được tin thoại"
    if changed:
        with _lock:
            fresh = _load()
            fresh.update({k: v for k, v in cache.items() if k not in fresh})
            _save(fresh)
    data["transcript_note"] = NOTE
    return json.dumps(data, ensure_ascii=False)
