"""Kênh Telegram (Bot API): bot chuyên trách long-poll bằng `telegram_bot.TelegramBot`."""
from __future__ import annotations

from channels import KenhSpec
import localefmt

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
        return {"ok": False, "error": localefmt.chu(f"Không nối được Telegram: {e}", f"Could not reach Telegram: {e}")}
    if not d.get("ok"):
        return {"ok": False, "error": localefmt.chu(
            "Token không hợp lệ (Telegram từ chối). Kiểm lại xem token "
            "này có đúng là token Telegram không.",
            "Invalid token (Telegram refused it). Check that this really is a Telegram bot token.")}
    info = d.get("result") or {}
    return {"ok": True, "username": info.get("username") or "",
            "bot_name": info.get("first_name") or "",
            "vao_duoc_nhom": True, "account_type": ""}


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    """Gửi một tin chữ từ bot `tk` (có `token`) tới `chat_id`. Trả (ok, lỗi)."""
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, localefmt.chu("tài khoản Telegram này chưa có token", "this Telegram account has no token yet")
    bot = _Transport()(token, "", None, giau_trang_thai=True)
    return await bot.send_text(chat_id, text)


async def send_file(tk: dict, chat_id: str, path: str, caption: str = "", chat_type: str = "private"):
    """Send one image or file the owner picked in the inbox (2026-11-24). `(ok, error)`, as `gui`."""
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, localefmt.chu("tài khoản Telegram này chưa có token", "this Telegram account has no token yet")
    bot = _Transport()(token, "", None, giau_trang_thai=True)
    return await bot.send_file(path, caption, chat=chat_id)


# Rename from the inbox (2026-11-27): a bot that is an admin with "Change group info" can retitle a group
# (setChatTitle). A person's name is theirs on Telegram, so a private chat is renamed in Javis only.
RENAMES = {"group": "title"}


async def rename(tk: dict, chat_id: str, name: str, chat_type: str = "private"):
    """Retitle a Telegram group. `(ok, error)`, the error in Telegram's words when it refuses (bot not an admin)."""
    import httpx
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, localefmt.chu("tài khoản Telegram này chưa có token", "this Telegram account has no token yet")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(TG_API.format(token=token, method="setChatTitle"),
                                  json={"chat_id": chat_id, "title": str(name)[:128]})
        d = r.json() if r.content else {}
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    if d.get("ok"):
        return True, ""
    why = str(d.get("description") or f"HTTP {r.status_code}")
    if "not enough rights" in why.lower() or "admin" in why.lower():
        return False, localefmt.chu("Bot cần là quản trị viên nhóm, có quyền đổi thông tin nhóm. (" + why + ")",
                                    "The bot must be a group admin allowed to change group info. (" + why + ")")
    return False, why
