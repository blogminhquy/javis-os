# -*- coding: utf-8 -*-
"""Plugin bundled: đọc nội dung video YouTube cho MỌI engine.

Đăng ký tool `javis_youtube_read`, gọi youtube_read.read() (lấy phụ đề qua InnerTube, dự phòng
cào trang watch). Vì sao là plugin bundled chứ không phải để engine tự xoay:
  - Sáu engine API không có WebFetch, tức KHÔNG mở được URL nào. Không có tool này thì chúng
    chỉ còn cách báo "không đọc được" - đúng lời phàn nàn của người dùng.
  - Ba engine CLI có WebFetch nhưng tải trang YouTube về chỉ được khung React rỗng, không có
    một chữ lời thoại nào. Nên WebFetch cũng KHÔNG phải lời giải, chỉ là thất bại chậm hơn.

min_mode=readonly: thuần đọc, không ghi file, không tiêu tiền, không đụng tài khoản. Nhờ vậy
loop/agent ở chế độ chỉ-đọc vẫn tóm tắt được video.

KHÔNG dùng cookie đăng nhập YouTube, có chủ ý: đổi lại là chịu thua video thật sự riêng tư,
nhưng Javis không phải giữ phiên đăng nhập của người dùng trên máy chủ - thứ mà lộ ra là
mất luôn tài khoản. Ca hay gặp trên VPS ("nghi máy chủ là robot") thì đã có sáu kiểu trình
phát và yt-dlp lo, không cần tới cookie.
"""
from __future__ import annotations

import youtube_read


def register(ctx):
    async def _read(args, cctx):
        args = args or {}
        url = str(args.get("url") or args.get("link") or "").strip()
        if not url:
            return "ERROR: thiếu 'url' (link video YouTube cần đọc)."
        lang = str(args.get("lang") or "").strip() or None
        try:
            start_min = float(args.get("start_min") or 0)
        except Exception:
            start_min = 0.0
        try:
            max_chars = int(args.get("max_chars") or youtube_read.MAX_CHARS_DEFAULT)
        except Exception:
            max_chars = youtube_read.MAX_CHARS_DEFAULT
        moc = args.get("timestamps")
        res = await youtube_read.read(
            url, lang=lang, timestamps=(True if moc is None else bool(moc)),
            start_min=start_min, max_chars=max_chars)
        return youtube_read.render(res)

    ctx.register_tool(
        name="javis_youtube_read",
        description=(
            "Đọc LỜI THOẠI (phụ đề) của một video YouTube từ link, để tóm tắt hoặc trích ý. "
            "GỌI TOOL NÀY mỗi khi người dùng gửi link YouTube (youtube.com, youtu.be, shorts) "
            "và muốn tóm tắt/hỏi về nội dung video - ĐỪNG dùng WebFetch cho link YouTube, "
            "trang đó không chứa lời thoại. Tham số: url (bắt buộc), lang (mã ngôn ngữ phụ đề "
            "muốn ưu tiên, vd 'vi'/'en'), start_min (đọc tiếp từ phút thứ mấy, cho video dài bị "
            "cắt bớt), timestamps (mặc định true), max_chars. Video không có phụ đề thì tool "
            "báo rõ - khi đó ĐỪNG bịa nội dung. Tool tự đổi qua nhiều kiểu trình phát rồi tới "
            "yt-dlp khi YouTube chặn máy chủ, nên link hỏng thật mới trả về lỗi."),
        handler=_read, min_mode="readonly", emoji="🎬",
        schema={"type": "object", "properties": {
            "url": {"type": "string",
                    "description": "Link video YouTube (watch, youtu.be, shorts, live, embed) hoặc mã video 11 ký tự"},
            "lang": {"type": "string",
                     "description": "Mã ngôn ngữ phụ đề ưu tiên, vd 'vi' hoặc 'en'. Bỏ trống thì theo ngôn ngữ giao diện, rồi tới tiếng Anh."},
            "start_min": {"type": "number",
                          "description": "Đọc từ phút thứ mấy. Dùng khi lần trước bị cắt bớt vì video quá dài."},
            "timestamps": {"type": "boolean",
                           "description": "Có gắn mốc thời gian [phút:giây] vào lời thoại không. Mặc định true."},
            "max_chars": {"type": "integer",
                          "description": "Trần số ký tự lời thoại trả về (mặc định 40000, tối đa 120000)."}},
            "required": ["url"]},
    )
