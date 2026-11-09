"""Batched reads: many dashboard GETs in one round trip (2026-11-08, performance stage 2).

Why. The owner reaches Javis through a Cloudflare tunnel (150-400 ms per round trip). Measured over 250 ms: the app
opens with ~32 reads, a chat switch makes 6, and most console pages read in 3 to 5 waves, each wave waiting for the one
before it (a module asks only once the previous answer drew its part of the page). The waiting, not the server, was
the cost: every read answers in under 10 ms.

How. The dashboard learns which reads each moment makes (app start, a page, a chat switch; fetch-gop.js) and at the
next such moment posts them all at once to POST /batch. This route runs each read through the app itself (every
middleware, the auth guard included, with the caller's own cookie), all at the same time, and streams each answer
back as soon as it is ready, as one server-sent event per read: `data: {"p": path, "s": status, "t": type, "b": body}`.
A slow read never holds up the quick ones, and a read missing from the stream is simply asked again by the page.

Only plain reads listed in ALLOWED are run. Nothing with a side effect (web_security.SIDE_EFFECT_GET), no explicit
refresh, no streams, no files, and never /batch itself.
"""
from __future__ import annotations

import asyncio
import json
import re

import httpx
from fastapi.responses import JSONResponse, StreamingResponse

import web_security

BATCH_MAX = 40
PATH_MAX = 600
# 2026-11-08: enforced with asyncio.wait_for in handle(). httpx's own timeout does nothing over ASGITransport (no
# network I/O to time), so before this a read that never finished kept the whole batch open and its page waiting.
SUB_TIMEOUT_S = 10.0

# Keep in step with BATCH_RE in dashboard/fetch-gop.js (tests/python/test_read_batch.py compares the two).
ALLOWED_PATHS = (
    r"settings", r"config", r"brains", r"agents", r"agents/get", r"agents/unread", r"agents/jobs/counts",
    r"agents/[^/?]+/pulse", r"skills", r"workflows", r"plugins", r"tools/optional", r"packs", r"logins",
    r"share/list", r"webhooks", r"webhooks/health", r"connect/catalog", r"connect/health", r"github/status",
    r"github/icons", r"github/session/[^/?]+", r"coding/session/[^/?]+", r"messenger/setup", r"threads/setup",
    r"(telegram|whatsapp|zalo-bot|discord|slack|lark)/status", r"claude/status", r"autostart", r"domain/status",
    r"remote-access/status", r"auth/status", r"auth/tokens", r"ui/order", r"pet/menu", r"voice/ear", r"voice/call",
    r"vault/check", r"files/list", r"files/md-hong", r"graph", r"projects", r"sessions", r"sessions/[0-9a-z]{8,64}",
    r"sessions/[0-9a-z]{8,64}/meta", r"background", r"chat/route", r"inbox", r"notifications", r"notifications/read",
    r"resonance/agents", r"resonance/goals", r"teams", r"learn/config", r"learn/metrics", r"learn/review",
    r"learn/log", r"auto-learning", r"backup/status", r"incidents", r"kanban", r"loops/log", r"my-tasks",
    r"my-tasks/calendar", r"reminders", r"schedules/this-machine", r"tasks/bots", r"viec/all", r"watch",
    r"channels/accounts", r"conversations", r"usage/insights", r"usage/summary", r"usage/theo-gio",
    r"usage/tong-quan", r"runtime/muc", r"cache-keepwarm", r"plan-limits",
)
_ALLOWED = re.compile(r"^/(" + "|".join(ALLOWED_PATHS) + r")(\?[^#]*)?$")
_REFRESH = re.compile(r"(^|[?&])(refresh|nocache)=(1|true)(&|$)", re.I)

# Headers a read needs to be the caller's own read: who (cookie, API token), in which language, and the address the
# person sees. Behind Caddy or another reverse proxy the app itself runs on http: without X-Forwarded-Proto/Host a
# batched /messenger/setup or /threads/setup built http:// addresses, said "not over HTTPS" and locked the Facebook
# sign-in button (#1226). These only shape public URLs (web_security.external_base), never who is calling, and
# X-Forwarded-For still stays out.
_FORWARD = ("cookie", "authorization", "accept-language", "user-agent", "x-forwarded-proto", "x-forwarded-host")


def allowed(path) -> bool:
    """A path the batch may run: an allowed plain read, no explicit refresh, nothing that climbs out of the app."""
    if not isinstance(path, str) or not path or len(path) > PATH_MAX:
        return False
    if ".." in path or "\\" in path or "#" in path or not _ALLOWED.match(path):
        return False
    if path.split("?", 1)[0] in web_security.SIDE_EFFECT_GET:
        return False
    query = path.split("?", 1)[1] if "?" in path else ""
    return not _REFRESH.search(query)


def clean_paths(raw) -> list:
    out = []
    for p in (raw if isinstance(raw, list) else [])[:BATCH_MAX]:
        if allowed(p) and p not in out:
            out.append(p)
    return out


def event(item: dict) -> str:
    return "data: " + json.dumps(item, ensure_ascii=False) + "\n\n"


async def handle(app, request):
    """POST /batch {"paths": [...]} -> text/event-stream, one `data:` event per read, in the order they finish."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - not JSON: nothing to run
        return JSONResponse({"error": "bad request"}, status_code=400)
    paths = clean_paths(body.get("paths") if isinstance(body, dict) else None)
    headers = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD}
    headers["accept-encoding"] = "identity"
    host = request.headers.get("host") or "localhost"
    base = f"{request.url.scheme}://{host}"
    client = (request.client.host, request.client.port) if request.client else ("127.0.0.1", 0)

    async def stream():
        if not paths:
            return
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False, client=client)
        async with httpx.AsyncClient(transport=transport, base_url=base, headers=headers,
                                     timeout=SUB_TIMEOUT_S) as sub:
            async def one(p):
                try:
                    r = await asyncio.wait_for(sub.get(p), SUB_TIMEOUT_S)
                    return {"p": p, "s": r.status_code, "t": r.headers.get("content-type", ""), "b": r.text}
                except Exception:  # noqa: BLE001 - this read (failed or too slow) is left out; the page asks again
                    return None
            jobs = [asyncio.ensure_future(one(p)) for p in paths]
            try:
                for done in asyncio.as_completed(jobs):
                    item = await done
                    if item is not None:
                        yield event(item)
            finally:
                for j in jobs:
                    j.cancel()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
