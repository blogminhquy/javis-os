"""Nén gzip các câu trả lời TRỌN MỘT CỤC của API (0.225.0).

Vì sao: Javis hay chạy trên VPS, trình duyệt ở xa. Đo lúc đổi sang một bộ não 2000 note: `/graph` trả 989 KB JSON không
nén, qua đường 8 Mbps mất 1,5 giây chỉ để tải, trong khi gzip xuống còn 62 KB. Mọi danh sách khác (hội thoại, file,
ký ức, việc) cũng đi trần như vậy, vì trước bản này chỉ `/static/` được nén (xem `_NenTinh` trong main.py).

Vì sao KHÔNG dùng GZipMiddleware cho mọi đường: nó gom trọn response streaming rồi mới trả một cục, nên luồng chat
(text/event-stream) hiện ra một lần lúc đã xong. Lớp này chỉ nén khi câu trả lời đến TRONG MỘT tin ASGI duy nhất
(`more_body` false), tức là JSONResponse, HTMLResponse, PlainTextResponse, file nhỏ. Một StreamingResponse luôn gửi
`more_body: true` ở mẩu đầu, nên đi qua nguyên vẹn, từng mẩu một, như cũ; kiểu `text/event-stream` thì thậm chí không
bị giữ tin mở đầu lại một nhịp nào.

Phải gắn ở TRONG CÙNG (add_middleware TRƯỚC mọi middleware khác): các middleware `@app.middleware("http")` bọc response
thành stream, đứng sau chúng thì không còn thấy câu trả lời nào là một cục nữa.
"""
from __future__ import annotations

import gzip

MIN_SIZE = 1400          # dưới một gói TCP thì nén không lợi gì
_NEN_DUOC = ("application/json", "text/html", "text/plain", "text/markdown", "text/css", "text/csv",
             "application/javascript", "text/javascript", "image/svg+xml", "application/xml", "text/xml")


def _header(headers, name: bytes) -> bytes:
    for k, v in headers:
        if k.lower() == name:
            return v
    return b""


def nen_duoc(content_type: bytes) -> bool:
    ct = content_type.split(b";", 1)[0].strip().lower().decode("latin-1")
    return ct in _NEN_DUOC


class NenPhanHoi:
    def __init__(self, app, minimum_size: int = MIN_SIZE, level: int = 5, skip_prefixes=("/static/",)):
        self.app = app
        self.minimum_size = minimum_size
        self.level = level
        self.skip_prefixes = tuple(skip_prefixes)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") == "HEAD" \
                or scope.get("path", "").startswith(self.skip_prefixes) \
                or b"gzip" not in _header(scope.get("headers") or [], b"accept-encoding").lower():
            await self.app(scope, receive, send)
            return

        start = None          # tin mở đầu đang giữ lại, chờ biết thân có trọn một cục không
        xong = False          # đã quyết (nén hoặc thả qua)

        async def gui(message):
            nonlocal start, xong
            if xong:
                await send(message)
                return
            t = message["type"]
            if t == "http.response.start":
                h = message.get("headers") or []
                st = message.get("status", 200)
                if (st < 200 or st >= 300 or st in (204, 206) or _header(h, b"content-encoding")
                        or not nen_duoc(_header(h, b"content-type"))):
                    xong = True
                    await send(message)
                    return
                start = message
                return
            if t == "http.response.body" and start is not None:
                xong = True
                body = message.get("body", b"")
                if message.get("more_body", False) or len(body) < self.minimum_size:
                    await send(start)
                    await send(message)
                    return
                z = gzip.compress(body, self.level)
                h = [(k, v) for k, v in (start.get("headers") or []) if k.lower() not in (b"content-length", b"vary")]
                vary = _header(start.get("headers") or [], b"vary")
                h += [(b"content-encoding", b"gzip"), (b"content-length", str(len(z)).encode()),
                      (b"vary", (vary + b", Accept-Encoding") if vary else b"Accept-Encoding")]
                await send(dict(start, headers=h))
                await send({"type": "http.response.body", "body": z, "more_body": False})
                return
            await send(message)

        await self.app(scope, receive, gui)
