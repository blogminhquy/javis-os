"""Zalo OA channel (official Official Account Open API v3), 0.412.0: a dedicated bot answers the
inbox of a Zalo Official Account through `zalo_oa_bot.ZaloOABot`, fed by the `/zalo-oa/webhook`
route.

The account secret is four credentials in one string, "<App ID> <App secret key> <OA secret key>
<Refresh token>", because the channel-account store keeps one encrypted secret per account. After
the first refresh Javis rewrites it as JSON with the rotated tokens (`zalo_oa_bot.TokenKeeper`).
Different from the `zalo` channel, which is the separate Zalo Bot API (bot accounts made in
"Zalo Bot Manager"): an OA is the business page customers follow.
"""
from __future__ import annotations

from channels import KenhSpec
import localefmt

SPEC = KenhSpec(
    id="zalo_oa", nhan="Zalo OA", kind="bot", logo="zalo", mau="#0068FF",
    lay_token=("Cần Javis có tên miền HTTPS. Ở developers.zalo.me tạo app, liên kết OA, xác thực tên miền "
               "(dán mã vào ô bên dưới), đặt webhook bằng địa chỉ bên dưới và bật các sự kiện user_send_*. "
               "Rồi dán bốn thứ cách nhau dấu cách: App ID, App secret key, OA secret key, Refresh token. "
               "Chi tiết: docs/35-zalo-oa.md."),
    tom_tat=("Hộp thư Zalo Official Account của doanh nghiệp. Chỉ chat riêng; khách lâu không nhắn thì "
             "Zalo không cho OA trả lời tự do nữa."),
    nang_luc={"nhom": False, "gui_chu": True, "gui_file": True},
    en={
        "lay_token": ("Javis needs an HTTPS domain. On developers.zalo.me create an app, link your OA, verify "
                      "the domain (paste the code in the box below), set the webhook to the address below and "
                      "enable the user_send_* events. Then paste four things separated by spaces: App ID, App "
                      "secret key, OA secret key, Refresh token. Details: docs/en/35-zalo-oa.md."),
        "tom_tat": ("Your business Zalo Official Account inbox. Private chats only; once a customer has been "
                    "quiet for a while, Zalo no longer lets the OA reply freely."),
    },
)

# The route Zalo calls. The Channels form shows it (GET /channels/webhook-info).
WEBHOOK_PATH = "/zalo-oa/webhook"


def _Transport():
    from zalo_oa_bot import ZaloOABot
    return ZaloOABot


class _Lazy:
    def __call__(self, *a, **kw):
        return _Transport()(*a, **kw)


Transport = _Lazy()


async def verify_token(token: str) -> dict:
    from zalo_oa_bot import check_credentials
    info = await check_credentials(token)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error", "")}
    return {"ok": True, "username": info.get("username", ""), "bot_name": info.get("bot_name", ""),
            "vao_duoc_nhom": False, "account_type": info.get("account_type", "")}


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    token = str(tk.get("token") or "").strip()
    aid = str(tk.get("id") or "")
    if not token and not aid:
        return False, localefmt.chu("tài khoản Zalo OA này chưa có thông tin đăng nhập",
                                    "this Zalo OA account has no credentials yet")
    bot = _Transport()(token, "", None, giau_trang_thai=True, account_id=aid)
    return await bot.send_text(chat_id, text)
