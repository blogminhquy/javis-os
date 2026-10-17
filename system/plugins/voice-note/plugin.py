"""Plugin bundled: tool javis_voice_note - a short spoken message attached to the answer (0.202.0).

Idea from OpenMausBot's voice notes. The audio is made by server/voice_note.py (Edge TTS) and saved in
the brain's attachments/voice/; the answer embeds it as a markdown link, which the dashboard draws as
an audio player and Telegram sends as an audio file. min_mode=safe: it writes a file.
"""
from __future__ import annotations

import voice_note


def register(ctx):
    async def _note(args, cctx):
        args = args or {}
        text = str(args.get("text") or "").strip()
        if not text:
            return "ERROR: thiếu 'text' (câu cần đọc thành tin thoại)."
        res = await voice_note.make(cctx.vault_root, text, voice=str(args.get("voice") or ""))
        if not res.get("ok"):
            return "ERROR: " + str(res.get("error") or "không tạo được tin thoại")
        rel = res["rel_path"]
        return (f"Đã ghi tin thoại ({res['chars']} ký tự, giọng {res['voice']}), lưu tại {rel}. "
                f"NHÚNG ngay vào câu trả lời bằng đúng dòng này: [🔊 Tin thoại]({rel}) "
                "và viết lại nội dung đó bằng chữ ngay dưới để người không nghe được vẫn đọc được.")

    ctx.register_tool(
        name="javis_voice_note",
        description=("Ghi một TIN THOẠI ngắn (tối đa 1000 ký tự) thành file mp3 rồi nhúng vào câu trả lời. "
                     "Dùng khi user muốn NGHE thay vì đọc (\"đọc cho tôi nghe\", \"gửi tin thoại\", báo cáo "
                     "buổi sáng để nghe lúc lái xe). Tham số: text (câu cần đọc, văn nói, không markdown), "
                     "voice (tuỳ chọn, tên giọng Edge như vi-VN-NamMinhNeural; bỏ trống thì tự chọn theo "
                     "ngôn ngữ). Sau khi gọi, nhúng link trả về vào câu trả lời."),
        handler=_note, min_mode="safe",
        schema={"type": "object", "properties": {
            "text": {"type": "string", "description": "Câu cần đọc thành tiếng (văn nói, tối đa 1000 ký tự)"},
            "voice": {"type": "string", "description": "Tên giọng Edge, bỏ trống để tự chọn"},
        }, "required": ["text"]},
    )
