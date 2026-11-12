"""Bundled plugin: tool `javis_browse` - operate a page behind a sign-in from the login vault.

Thin shell over `server/browse_ops.py` (browser, session and approval gate live there so tests run without
Chromium). Owner-only (`mcp_hub.OWNER_ONLY_TOOLS`): a customer talking to a bot must never act as the owner.
`javis_login` stays the read-only tool; this one clicks and types, so min_mode is "safe", not "readonly".
"""
from __future__ import annotations

import browse_ops


async def _run(args, ctx) -> str:
    return await browse_ops.get_manager().run(args or {}, str(getattr(ctx, "vault_root", "") or ""))


def register(ctx):
    ctx.register_tool(
        "javis_browse",
        "THAO TÁC trang web cần đăng nhập bằng phiên đã cất ở trang Cookies (sàn, quảng cáo, trang quản trị). Không "
        "bao giờ trả cookie. op=open (url, login): mở trang. op=read: chữ trên trang + danh sách phần tử đánh số. "
        "op=screenshot: chụp, trả đường dẫn ảnh. op=click (element=số | selector | target_text). op=type (như click, "
        "kèm text). op=press (key, vd Enter). op=close. Luôn read trước, đừng đoán selector. Chỉ đi trong tên miền "
        "của đăng nhập. Với đăng nhập sàn/quảng cáo, click/type/press chờ CHỦ duyệt: nhận 'Chờ chủ duyệt, mã X' thì "
        "dừng, khi được báo đã duyệt gọi lại đúng lệnh kèm approval_id=X. Không thử lại sớm, không tìm đường vòng để "
        "né duyệt. Chỉ đọc thuần thì dùng javis_login.",
        _run,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": list(browse_ops.OPS)},
                "url": {"type": "string"},
                "login": {"type": "string", "description": "Tên đăng nhập trong Kho (bỏ trống nếu chỉ mở một trang)"},
                "element": {"type": "integer", "description": "Số phần tử trong danh sách của op=read"},
                "selector": {"type": "string"},
                "target_text": {"type": "string", "description": "Chữ nhìn thấy của phần tử cần bấm hoặc gõ"},
                "text": {"type": "string", "description": "Chữ cần gõ (op=type)"},
                "key": {"type": "string", "description": "Phím (op=press)"},
                "approval_id": {"type": "string", "description": "Mã chủ đã duyệt, dùng đúng một lần"},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="🖱️",
    )
