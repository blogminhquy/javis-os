"""WhatsApp channel (official Cloud API by Meta): a dedicated bot answers through
`whatsapp_bot.WhatsAppBot`, fed by the `/whatsapp/webhook` route.

The account secret is the three credentials of one number in one string, "<phone number id>
<access token> <app secret>", because the channel-account store keeps one encrypted secret per
account. `whatsapp_bot.split_credentials` tells the parts apart by shape.
"""
from __future__ import annotations

from channels import KenhSpec
import localefmt

SPEC = KenhSpec(
    id="whatsapp", nhan="WhatsApp", kind="bot", logo="whatsapp", mau="#25D366",
    lay_token=("Cần Javis có tên miền HTTPS. Ở developers.facebook.com tạo app WhatsApp, đặt webhook theo "
               "trang Kênh, rồi dán ba thứ cách nhau dấu cách: Phone number ID, Access token vĩnh viễn, "
               "App secret. Chi tiết: docs/en/29-slack-whatsapp.md."),
    tom_tat="Kênh nhắn tin phổ biến nhất thế giới. Chỉ chat riêng; ngoài 24 giờ kể từ tin cuối của khách thì không nhắn trước được.",
    nang_luc={"nhom": False, "gui_chu": True, "gui_file": True},
    en={
        "lay_token": ("Javis needs an HTTPS domain. On developers.facebook.com create a WhatsApp app, set the "
                      "webhook shown on the Channels page, then paste three things separated by spaces: the "
                      "Phone number ID, a permanent Access token, the App secret. Details: docs/en/29-slack-whatsapp.md."),
        "tom_tat": ("The most used messaging app worldwide. Private chats only; you cannot message a customer "
                    "first once 24 hours have passed since their last message."),
    },
)


def _Transport():
    from whatsapp_bot import WhatsAppBot
    return WhatsAppBot


class _Lazy:
    def __call__(self, *a, **kw):
        return _Transport()(*a, **kw)


Transport = _Lazy()


async def verify_token(token: str) -> dict:
    import httpx
    from whatsapp_bot import split_credentials, whoami
    cr = split_credentials(token)
    thieu = [n for n, k in (("Phone number ID", "phone_number_id"), ("Access token", "access_token"),
                            ("App secret", "app_secret")) if not cr.get(k)]
    if thieu:
        return {"ok": False, "error": localefmt.chu("Còn thiếu: " + ", ".join(thieu),
                                                    "Missing: " + ", ".join(thieu))}
    async with httpx.AsyncClient(timeout=15) as c:
        info = await whoami(c, cr["phone_number_id"], cr["access_token"])
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error", "")}
    return {"ok": True, "username": info.get("username", ""), "bot_name": info.get("bot_name", ""),
            "vao_duoc_nhom": False, "account_type": ""}


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, localefmt.chu("tài khoản WhatsApp này chưa có thông tin đăng nhập",
                                    "this WhatsApp account has no credentials yet")
    bot = _Transport()(token, "", None, giau_trang_thai=True)
    return await bot.send_text(chat_id, text)
