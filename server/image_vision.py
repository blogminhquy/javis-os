"""image_vision.py - let ChatGPT LOOK at images in the brain and describe them, on the signed-in plan.

Why this exists. The six API engines (OpenRouter, OpenAI API, Gemini...) only ever receive tool results as text: the hub drops every
non-text MCP content block, and none of those engines sends image input. So when a brain on one of them needs to know what is in a
picture (a photo someone posted in a Zalo group, a screenshot in attachments/), it has no eyes. The CLI engines (Claude Code, Codex)
can open the file themselves; everyone else gets eyes through this module.

How: the same Codex Responses endpoint `image_gen.py` already uses on the ChatGPT OAuth plan (no API key), with the images sent as
`input_image` and no tools, streamed, collecting `response.output_text.delta`. Reading the files goes through
`image_gen.read_reference_image`, so the "must stay inside the brain" fence and the size cap are the exact same code.

The prompt is in Vietnamese on purpose (prompts sent to a model are not translated, see docs/dev/them-mot-ngon-ngu.md); the model is
told to answer in the user's language anyway.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

import image_gen
import localefmt
import openai_oauth

_VISION_ENV = os.getenv("JAVIS_VISION_MODEL", "").strip()
VISION_MODEL = _VISION_ENV or image_gen.HOST_MODEL
MAX_IMAGES = image_gen.MAX_REF_IMAGES
MAX_OUTPUT_CHARS = 12_000
INSTRUCTIONS = (
    "Bạn là đôi mắt của một trợ lý AI không tự xem được ảnh. Mô tả ĐÚNG những gì thấy trong ảnh để trợ lý đó dùng: "
    "chép lại NGUYÊN VĂN mọi chữ, số, giá, mã đơn, số điện thoại, ngày giờ đọc được; nêu đồ vật, người, bối cảnh, biểu đồ, "
    "bảng. Không đoán điều không thấy, chỗ mờ thì nói là mờ. Trả lời bằng ngôn ngữ của phần yêu cầu."
)


def build_prompt(question: str = "", labels: Optional[List[str]] = None) -> str:
    """The text part of the request: what to look for, plus one label per image so the answer can be matched back."""
    q = str(question or "").strip()
    lines = [f"Yêu cầu: {q}" if q else "Yêu cầu: mô tả chi tiết từng ảnh."]
    labels = [str(x or "").strip() for x in (labels or [])]
    if len(labels) > 1 or any(labels):
        lines.append("Các ảnh gửi kèm theo đúng thứ tự:")
        for i, lab in enumerate(labels, 1):
            lines.append(f"- Ảnh {i}" + (f": {lab}" if lab else ""))
        lines.append("Trả lời theo từng ảnh, mở đầu mỗi phần bằng \"Ảnh N:\".")
    return "\n".join(lines)


def build_payload(prompt: str, data_urls: Iterable[str], model: str = "") -> dict:
    """Responses body for one look at N images. No tools: the answer is plain text."""
    content: list = [{"type": "input_text", "text": prompt}]
    for u in data_urls:
        content.append({"type": "input_image", "image_url": u})
    return {
        "model": model or VISION_MODEL,
        "store": False,
        "instructions": INSTRUCTIONS,
        "input": [{"type": "message", "role": "user", "content": content}],
        "stream": True,
    }


def text_from_completed(obj: Any) -> str:
    """Fallback when no delta arrived: dig the output_text out of a `response.completed` event."""
    out = []
    resp = (obj or {}).get("response") if isinstance(obj, dict) else None
    for item in (resp or {}).get("output") or []:
        if not isinstance(item, dict):
            continue
        for c in item.get("content") or []:
            if isinstance(c, dict) and c.get("type") in ("output_text", "text") and c.get("text"):
                out.append(str(c["text"]))
    return "".join(out)


# ---------------------------------------------------------------------------
# Fetching an image someone posted in a chat (0.74.1: the Zalo customer bot)
# ---------------------------------------------------------------------------
FETCH_TIMEOUT = 60
MAX_REDIRECTS = 3
_EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
_EXT_RE = re.compile(r"\.(jpe?g|png|webp|gif)$", re.IGNORECASE)
SAFE_PART = re.compile(r"[^0-9A-Za-z_-]")


def url_allowed(url: str) -> bool:
    """Only https on a hostname, never localhost or a literal IP: the link comes from a chat message, so it is untrusted input."""
    try:
        u = urlparse(str(url or ""))
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        return True


# Labels a CDN puts on a file when it does not say what the file is. Zalo's photo servers answer `application/octet-stream` for some
# photos (seen 2026-10-11: every photo from one customer was dropped as "not an image" before the bot could see it). A file with one
# of these labels is downloaded and judged by its first bytes instead.
_GENERIC_TYPES = ("", "application/octet-stream", "binary/octet-stream", "application/binary", "application/x-binary",
                  "application/unknown", "application/download", "application/force-download")


def header_may_be_image(content_type: str) -> bool:
    """True when the Content-Type is an image type, or a generic binary label that the bytes must settle."""
    ct = str(content_type or "").split(";")[0].strip().lower()
    return ct.startswith("image/") or ct in _GENERIC_TYPES


def sniff_image_type(head: bytes) -> str:
    """The image MIME type read from a file's first bytes (JPEG, PNG, GIF, WebP), or "" when they are not one of those."""
    b = bytes(head or b"")
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return ""


def image_extension(url: str, content_type: str = "") -> str:
    ct = str(content_type or "").split(";")[0].strip().lower()
    if ct in _EXT_BY_TYPE:
        return _EXT_BY_TYPE[ct]
    m = _EXT_RE.search(urlparse(str(url or "")).path or "")
    if m:
        e = m.group(1).lower()
        return ".jpg" if e == "jpeg" else "." + e
    return ".jpg"


async def fetch_image(url: str, dest_dir: Path, stem: str, max_bytes: int = image_gen.MAX_REF_BYTES) -> Tuple[Optional[Path], str]:
    """Save one posted image as `<dest_dir>/<stem>.<ext>` and return `(path, "")` or `(None, reason)`.

    Reuses a copy saved earlier under the same stem. Redirects are followed by hand so every hop is checked BEFORE it is requested;
    letting httpx follow them would already have sent a request to whatever internal address a hop pointed at."""
    dest_dir = Path(dest_dir)
    if dest_dir.is_dir():
        for old in dest_dir.glob(stem + ".*"):
            if old.is_file() and old.stat().st_size > 0:
                return old, ""
    if not url_allowed(url):
        return None, "link ảnh không phải https hợp lệ nên không tải"
    buf = bytearray()
    ctype = ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(FETCH_TIMEOUT, connect=15), follow_redirects=False) as client:
            for _hop in range(MAX_REDIRECTS + 1):
                async with client.stream("GET", url) as r:
                    if r.status_code in (301, 302, 303, 307, 308):
                        nxt = str(r.url.join(r.headers.get("location") or ""))
                        if not url_allowed(nxt):
                            return None, "link ảnh chuyển hướng ra địa chỉ không an toàn nên không tải"
                        url = nxt
                        continue
                    if r.status_code != 200:
                        return None, f"máy chủ ảnh trả HTTP {r.status_code} (link có thể đã hết hạn)"
                    ctype = r.headers.get("content-type") or ""
                    if not header_may_be_image(ctype):
                        return None, f"link không phải ảnh ({ctype.split(';')[0]})"
                    async for chunk in r.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) > max_bytes:
                            return None, f"ảnh lớn hơn {max_bytes // (1024 * 1024)}MB nên không tải"
                    break
            else:
                return None, "link ảnh chuyển hướng quá nhiều lần"
    except Exception as e:      # noqa: BLE001 - a caller answers with a sentence, never a traceback
        return None, f"tải ảnh lỗi: {type(e).__name__}: {e}"
    if not buf:
        return None, "ảnh rỗng"
    sniffed = sniff_image_type(bytes(buf[:16]))
    if not sniffed and not str(ctype or "").lower().startswith("image/"):
        # A generic binary label is only trusted once the bytes prove it: an HTML error page served as octet-stream stays out.
        return None, f"link không phải ảnh ({(ctype or 'không rõ loại').split(';')[0]})"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (stem + image_extension(url, sniffed or ctype))
    dest.write_bytes(bytes(buf))
    return dest, ""


def connected() -> bool:
    try:
        return bool(openai_oauth.status().get("connected"))
    except Exception:      # noqa: BLE001 - an unreadable status is "not connected", never a crash in a tool
        return False


def not_connected_reason() -> str:
    return localefmt.chu(
        "Chưa kết nối ChatGPT (OAuth) nên không có ai xem ảnh hộ. Vào trang Model đăng nhập ChatGPT rồi thử lại - "
        "dùng chính gói ChatGPT, không cần API key.",
        "ChatGPT (OAuth) is not connected, so nothing can look at the image. Sign in to ChatGPT on the Models page and "
        "try again - it uses your ChatGPT plan, no API key needed.")


async def describe_images(paths: List[str], question: str = "", vault_root: Optional[str] = None,
                          labels: Optional[List[str]] = None, timeout_s: float = 180.0) -> dict:
    """Send up to MAX_IMAGES brain images to ChatGPT and return `{ok, text, count}` or `{ok: False, error}`."""
    paths = [str(p).strip() for p in (paths or []) if str(p or "").strip()]
    if not paths:
        return {"ok": False, "error": localefmt.chu("Thiếu đường dẫn ảnh.", "Missing image path.")}
    if len(paths) > MAX_IMAGES:
        return {"ok": False, "error": localefmt.chu(f"Xem tối đa {MAX_IMAGES} ảnh một lượt (đang gửi {len(paths)}).",
                                                f"At most {MAX_IMAGES} images per look (sending {len(paths)}).")}
    creds = openai_oauth.valid_creds()
    if not creds or not creds.get("access_token"):
        return {"ok": False, "error": not_connected_reason()}
    # Read every file BEFORE spending a network call: a wrong path is reported by name, not as a vague model answer.
    data_urls = []
    for p in paths:
        r = image_gen.read_reference_image(p, vault_root)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error") or localefmt.chu(f"Không đọc được ảnh '{p}'.", f"Could not read image '{p}'.")}
        data_urls.append(r["data_url"])
    prompt = build_prompt(question, labels if labels else ["" for _ in paths])
    headers = image_gen._headers(creds["access_token"], creds.get("account_id") or "")
    # Same model order as image generation: a plan without HOST_MODEL moves on to another model of that very account instead
    # of handing the user "model is not supported" (seen 2026-10-15 with gpt-5.5 on a plan that lacks it).
    candidates = [_VISION_ENV] if _VISION_ENV else image_gen.host_model_candidates()
    parts, final, err, status = [], "", "", 0
    payload = build_payload(prompt, data_urls, model=candidates[0] if candidates else "")
    for model in candidates:
        payload = build_payload(prompt, data_urls, model=model)
        parts, final, err, status = await _look_once(payload, headers, timeout_s)
        if status == -1:
            return {"ok": False, "error": err}
        if (parts or final) or not image_gen.model_rejected(status, err):
            break
    if status not in (0, -1) and not (parts or final):
        return {"ok": False, "error": err}
    text = ("".join(parts) or final).strip()
    if err and not text:
        return {"ok": False, "error": f"ChatGPT: {err}"}
    if not text:
        return {"ok": False, "error": localefmt.chu("ChatGPT không trả lời gì về ảnh này.", "ChatGPT said nothing about this image.")}
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + " ..."
    return {"ok": True, "text": text, "count": len(data_urls), "model": payload["model"]}


async def _look_once(payload: dict, headers: dict, timeout_s: float):
    """One streamed look. Returns (deltas, completed text, error, status): status is the HTTP code of a refused request,
    0 when the stream ran (an error inside it is in `error`), -1 when the call itself blew up."""
    parts: List[str] = []
    final = ""
    err = ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=20)) as client:
            async with client.stream("POST", image_gen.CODEX_RESPONSES_URL, headers=headers, json=payload) as r:
                if r.status_code != 200:
                    body = await r.aread()
                    return [], "", f"ChatGPT {r.status_code}: {body.decode('utf-8', 'replace')[:300]}", r.status_code
                async for line in r.aiter_lines():
                    line = (line or "").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    kind = obj.get("type")
                    if kind == "response.output_text.delta":
                        parts.append(str(obj.get("delta") or ""))
                    elif kind in ("response.failed", "error", "response.error", "response.incomplete"):
                        e = (obj.get("response") or {}).get("error") or obj.get("error") or {}
                        err = (e.get("message") if isinstance(e, dict) else str(e)) or kind
                        break
                    elif kind == "response.completed":
                        final = text_from_completed(obj)
                        break
    except Exception as e:      # noqa: BLE001 - a tool answers with a sentence, never a traceback
        return [], "", localefmt.chu(f"Gọi ChatGPT lỗi: {type(e).__name__}: {e}",
                                     f"Calling ChatGPT failed: {type(e).__name__}: {e}"), -1
    return parts, final, err, 0
