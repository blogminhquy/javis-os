"""Kênh Zalo Bot (Bot API chính thức của Zalo): id kho là `zalo` (giữ từ 0.26.5, dữ liệu cũ
đang mang đúng chuỗi này). Long-poll bằng `zalo_bot.ZaloBot`."""
from __future__ import annotations

from channels import KenhSpec

ZALO_API = "https://bot-api.zaloplatforms.com/bot{token}/{method}"

SPEC = KenhSpec(
    id="zalo", nhan="Zalo Bot", kind="bot", logo="zalo", mau="#0068FF",
    lay_token=("Mở app Zalo, tìm Official Account \"Zalo Bot Manager\", chọn Tạo bot. "
               "Tên bot bắt buộc mở đầu bằng chữ \"Bot\". Token được gửi về bằng tin nhắn Zalo."),
    tom_tat="Khách Việt Nam đã có sẵn trên máy. Chỉ chat riêng, chưa gửi được tài liệu.",
    # Gói cơ bản không vào được nhóm; gói cao hơn thì `verify_token` báo `vao_duoc_nhom`.
    nang_luc={"nhom": False, "gui_chu": True, "gui_file": False},
)


def _Transport():
    from zalo_bot import ZaloBot
    return ZaloBot


class _Lazy:
    def __call__(self, *a, **kw):
        return _Transport()(*a, **kw)


Transport = _Lazy()


async def verify_token(token: str) -> dict:
    import httpx
    tok = str(token or "").strip()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(ZALO_API.format(token=tok, method="getMe"), json={})
        d = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Không nối được Zalo Bot: {e}"}
    if not d.get("ok"):
        return {"ok": False, "error": "Token không hợp lệ (Zalo Bot từ chối). Kiểm lại xem token "
                                      "này có đúng là token Zalo Bot không."}
    info = d.get("result") or {}
    return {"ok": True, "username": info.get("account_name") or "",
            "bot_name": info.get("account_name") or "",
            # Gói BASIC của Zalo không cho bot vào nhóm. Nói NGAY lúc kiểm token.
            "vao_duoc_nhom": bool(info.get("can_join_groups")),
            "account_type": info.get("account_type") or ""}


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, "tài khoản Zalo Bot này chưa có token"
    bot = _Transport()(token, "", None, giau_trang_thai=True)
    return await bot.send_text(chat_id, text)
