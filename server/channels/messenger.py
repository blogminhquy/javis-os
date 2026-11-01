"""Facebook Messenger channel (official Messenger Platform by Meta), 0.134.0: a dedicated bot
answers a Facebook Page's inbox through `messenger_bot.MessengerBot`, fed by the
`/messenger/webhook` route.

The account secret is the three credentials of one Page in one string, "<page id> <page access
token> <app secret>", because the channel-account store keeps one encrypted secret per account.
`messenger_bot.split_credentials` tells the parts apart by shape.
"""
from __future__ import annotations

from channels import KenhSpec
import localefmt

SPEC = KenhSpec(
    id="messenger", nhan="Messenger", kind="bot", logo="messenger", mau="#0866FF",
    lay_token=("Cần Javis có tên miền HTTPS. Ở developers.facebook.com tạo app, thêm sản phẩm Messenger, gắn "
               "Fanpage, đặt webhook bằng địa chỉ và mã xác minh hiện bên dưới (tick messages và "
               "messaging_postbacks, feed), rồi dán ba thứ cách nhau dấu cách: Page ID, token Trang, App secret."),
    tom_tat=("Hộp thư và bình luận Fanpage Facebook. Chỉ chat riêng; ngoài 24 giờ kể từ tin cuối của khách thì "
             "không nhắn lại được. Trả lời người ngoài cần chuyển app Meta sang chế độ Live."),
    nang_luc={"nhom": False, "gui_chu": True, "gui_file": True},
    en={
        "lay_token": ("Javis needs an HTTPS domain. On developers.facebook.com create an app, add the Messenger "
                      "product, connect your Facebook Page, set the webhook with the address and verify token "
                      "shown below (tick messages, messaging_postbacks and feed), then paste three things separated "
                      "by spaces: the Page ID, the Page token, the App secret."),
        "tom_tat": ("Your Facebook Page inbox and comments. Private chats only; no message once 24 hours have passed "
                    "since the customer's last one. Replying to the public needs the Meta app switched to Live."),
    },
)

# The route Meta calls. The Channels form shows it with the verify token (GET /channels/webhook-info).
WEBHOOK_PATH = "/messenger/webhook"
# Step-by-step guide linked from the add-account form (0.436.1): file names in docs/ and docs/en/.
GUIDE = {"vi": "31-messenger-tung-buoc.md", "en": "31-messenger-step-by-step.md"}


def _Transport():
    from messenger_bot import MessengerBot
    return MessengerBot


class _Lazy:
    def __call__(self, *a, **kw):
        return _Transport()(*a, **kw)


Transport = _Lazy()


async def verify_token(token: str) -> dict:
    import httpx
    from messenger_bot import split_credentials, whoami
    cr = split_credentials(token)
    thieu = [n for n, k in (("Page ID", "page_id"), ("Page access token", "access_token"),
                            ("App secret", "app_secret")) if not cr.get(k)]
    if thieu:
        return {"ok": False, "error": localefmt.chu("Còn thiếu: " + ", ".join(thieu),
                                                    "Missing: " + ", ".join(thieu))}
    async with httpx.AsyncClient(timeout=15) as c:
        info = await whoami(c, cr["page_id"], cr["access_token"], cr["app_secret"])
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error", "")}
    return {"ok": True, "username": info.get("username", ""), "bot_name": info.get("bot_name", ""),
            "vao_duoc_nhom": False, "account_type": ""}


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, localefmt.chu("tài khoản Messenger này chưa có thông tin đăng nhập",
                                    "this Messenger account has no credentials yet")
    bot = _Transport()(token, "", None, giau_trang_thai=True)
    return await bot.send_text(chat_id, text)
