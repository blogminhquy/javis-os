"""Kênh Telegram (Bot API): bot chuyên trách long-poll bằng `telegram_bot.TelegramBot`."""
from __future__ import annotations

from channels import KenhSpec

TG_API = "https://api.telegram.org/bot{token}/{method}"

SPEC = KenhSpec(
    id="telegram", nhan="Telegram", kind="bot", logo="telegram", mau="#229ED9",
    lay_token="Nhắn @BotFather trên Telegram, gõ /newbot rồi làm theo hướng dẫn.",
    tom_tat="Vào được nhóm, gửi được ảnh và tài liệu. Người Việt ít dùng.",
    tien_to_ten="@",
    nang_luc={"nhom": True, "gui_chu": True, "gui_file": True},
)


def _Transport():
    from telegram_bot import TelegramBot
    return TelegramBot


class _Lazy:
    """`Transport` tra lười để module kênh nạp được mà không kéo httpx lúc import sổ."""
    def __call__(self, *a, **kw):
        return _Transport()(*a, **kw)


Transport = _Lazy()


async def verify_token(token: str) -> dict:
    """Hỏi Telegram token này là bot nào (getMe)."""
    import httpx
    tok = str(token or "").strip()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(TG_API.format(token=tok, method="getMe"))
        d = r.json()
    except Exception as e:
        return {"ok": False, "error": f"Không nối được Telegram: {e}"}
    if not d.get("ok"):
        return {"ok": False, "error": "Token không hợp lệ (Telegram từ chối). Kiểm lại xem token "
                                      "này có đúng là token Telegram không."}
    info = d.get("result") or {}
    return {"ok": True, "username": info.get("username") or "",
            "bot_name": info.get("first_name") or "",
            "vao_duoc_nhom": True, "account_type": ""}


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    """Gửi một tin chữ từ bot `tk` (có `token`) tới `chat_id`. Trả (ok, lỗi)."""
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, "tài khoản Telegram này chưa có token"
    bot = _Transport()(token, "", None, giau_trang_thai=True)
    return await bot.send_text(chat_id, text)
