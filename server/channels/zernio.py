"""Zernio channel (multi-channel social messaging via Zernio): a dedicated bot
answers through `zernio_bot.ZernioBot`, fed by the `/webhooks/zernio` route.

Currently supports Instagram messaging, with 5-second message debounce batching,
constant-time HMAC-SHA256 signature verification, and deduplication.
"""
from __future__ import annotations

from channels import KenhSpec
import localefmt

SPEC = KenhSpec(
    id="zernio",
    nhan="Zernio",
    kind="bot",
    logo="zernio",
    mau="#6366F1",
    lay_token=(
        "Nối tài khoản mạng xã hội qua Zernio (hỗ trợ Instagram). "
        "Dán Account ID, Username và Webhook Secret (hoặc chọn từ tài khoản Zernio đã kết nối)."
    ),
    tom_tat=(
        "Nhắn tin đa kênh qua Zernio (hỗ trợ Instagram). "
        "Tự động gom tin 5 giây, bảo vệ chống trùng, xác thực HMAC webhook."
    ),
    nang_luc={"nhom": False, "gui_chu": True, "gui_file": False, "tra_loi_tu_javis": True, "bot": True},
    en={
        "nhan": "Zernio",
        "lay_token": (
            "Connect social channels via Zernio (Instagram supported). "
            "Paste Account ID, Username and Webhook Secret (or choose from connected Zernio accounts)."
        ),
        "tom_tat": (
            "Multi-channel messaging via Zernio (Instagram supported). "
            "Automatic 5s message batching, deduplication, and HMAC webhook authentication."
        ),
    },
)

WEBHOOK_PATH = "/webhooks/zernio"
MAX_ACCOUNTS_PER_BOT = 100


def _Transport():
    from zernio_bot import ZernioBot
    return ZernioBot


class _Lazy:
    def __call__(self, *a, **kw):
        return _Transport()(*a, **kw)


Transport = _Lazy()


async def verify_token(token: str) -> dict:
    from zernio_bot import split_credentials, whoami
    cr = split_credentials(token)
    thieu = []
    if not cr.get("account_id"):
        thieu.append("Account ID")
    if not cr.get("username"):
        thieu.append("Username")
    if not cr.get("secret"):
        thieu.append("Webhook Secret")
    if thieu:
        return {"ok": False, "error": localefmt.chu("Còn thiếu: " + ", ".join(thieu),
                                                    "Missing: " + ", ".join(thieu))}

    info = await whoami(cr)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error", "")}

    return {
        "ok": True,
        "username": cr["username"],
        "bot_name": f"@{cr['username']} (Instagram)",
        "account_type": "instagram",
        "vao_duoc_nhom": False,
        "meta": {
            "platform": "instagram",
            "account_id": cr["account_id"],
            "username": cr["username"],
            "secret": cr["secret"],
            "api_key": cr.get("api_key", ""),
        }
    }


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    token = tk.get("token") or tk
    if not token:
        return False, localefmt.chu("tài khoản Zernio này chưa có thông tin đăng nhập",
                                    "this Zernio account has no credentials yet")
    from zernio_bot import send_text_for_account
    return await send_text_for_account(tk, chat_id, text)
