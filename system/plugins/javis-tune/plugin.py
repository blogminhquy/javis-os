"""Bundled plugin: the owner steers background work by talking (10/11/2026).

Background jobs choose their own model from their results (server/job_scorecard.py). There is no settings page for
it: the owner says "tiết kiệm token giúp anh", "việc gửi báo cáo phải thật chắc" or "báo cáo sáng nay sai rồi", and
this tool turns that into an intent or a mark on the job's scorecard. The work is in `server/job_tune.py`.

Owner only: `mcp_hub.OWNER_ONLY_TOOLS` lists it, so a customer-facing bot never sees it.
"""
from __future__ import annotations

import asyncio

import job_tune


def register(ctx):
    ctx.register_tool(
        "javis_tune",
        "Cách việc nền (tự học, nhắc hẹn, loop, Kanban) tự chọn model, làm theo lời NGƯỜI DÙNG trong chat. Dùng khi "
        "họ than tốn token hay hết hạn mức nhanh, bảo tiết kiệm, bảo làm cho kỹ hay cho chắc, hỏi việc nền đang chạy "
        "model gì và vì sao, chê hay khen kết quả một việc nền, hoặc dặn Javis nên tự học thế nào. "
        "op=status: ý định chung, model từng việc đang dùng kèm số lần chạy và hỏng, các thay đổi gần đây. "
        "op=intent {level, job?}: ghi ý định. level=save (ưu tiên tiết kiệm), balanced (để Javis tự cân), sure (ưu "
        "tiên chắc ăn). Không truyền job = mọi việc nền; có job = riêng việc đó. "
        "op=feedback {job, good, note?}: người dùng nói kết quả một việc sai (good=false, lần sau việc đó dùng model "
        "mạnh hơn một bậc) hoặc đúng (good=true). "
        "op=teach {text}: người dùng dặn một điều về CÁCH TỰ HỌC (vd 'đừng ghi doanh thu từng ngày thành ghi nhớ', "
        "'chỉ ghi nhớ quyết định đã chốt'); Javis Core giữ bài học này và mọi mẻ tự học đọc nó trước. "
        "op=set {knob, value}: đặt thẳng một núm Javis Core đang tự chỉnh (tên núm trong op=status). Người dùng "
        "bảo đừng ghim công cụ nữa thì đặt tools.pin_limit về 0; hỏi đang ghim công cụ nào thì xem op=status. "
        "op=undo {id}: hoàn lại một thay đổi (id trong op=status, dạng số hoặc k12). "
        "job là tên việc theo lời người dùng; nhiều việc khớp thì hỏi lại. Chỉ gọi khi người dùng nói về việc nền, "
        "không gọi cho câu trả lời trong chat.",
        _run,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": list(job_tune.OPS)},
                "level": {"type": "string", "enum": ["save", "balanced", "sure"]},
                "job": {"type": "string", "description": "tên việc theo lời người dùng, hoặc mã việc từ op=status"},
                "good": {"type": "boolean"},
                "note": {"type": "string", "description": "người dùng chê hay khen điều gì"},
                "text": {"type": "string", "description": "bài học về cách tự học, một câu ngắn"},
                "knob": {"type": "string", "description": "tên núm, vd learn.min_turns, tools.pin_limit"},
                "value": {"type": "integer"},
                "id": {"type": "string", "description": "mã thay đổi cần hoàn lại, vd 7 hoặc k12"},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="🎚️",
    )


async def _run(args, ctx) -> str:
    return await asyncio.to_thread(job_tune.run, args or {}, getattr(ctx, "vault_root", "") or "")
