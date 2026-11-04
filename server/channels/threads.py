"""Threads channel (Meta), 0.448.0: replies under the owner's Threads posts, answered through
`threads_bot.ThreadsBot`, fed by the `/threads/webhook` route.

Threads has no private messages in its API, so a conversation here is always a public reply thread under a post.
The account secret is "<threads user id> <access token> <app secret>" in one string, like the other Meta channels;
it is normally written by Log in to Threads on the Meta connection card (`threads_oauth`), which also refreshes it.
"""
from __future__ import annotations

from channels import KenhSpec
import localefmt

SPEC = KenhSpec(
    id="threads", nhan="Threads", kind="bot", logo="threads", mau="#000000",
    lay_token=("Nối ở thẻ Kết nối Meta, trang Kết nối: dán Threads App ID và Threads App secret rồi bấm Đăng nhập "
               "Threads. Javis tự lấy và tự gia hạn token."),
    tom_tat=("Bình luận dưới bài Threads của bạn. Threads không có tin nhắn riêng: bot chỉ trả lời công khai, tối đa "
             "500 ký tự mỗi câu."),
    nang_luc={"nhom": False, "gui_chu": True, "gui_file": False},
    en={
        "lay_token": ("Connect it on the Meta connection card, Connections page: paste the Threads App ID and Threads "
                      "App secret and click Log in to Threads. Javis gets and renews the token by itself."),
        "tom_tat": ("Replies under your Threads posts. Threads has no private messages: the bot only answers publicly, "
                    "up to 500 characters each."),
    },
)

WEBHOOK_PATH = "/threads/webhook"
# Connected from the Meta connection card on the Connections page (Log in to Threads), not by pasting a token.
CONNECT_CARD = True


def _Transport():
    from threads_bot import ThreadsBot
    return ThreadsBot


class _Lazy:
    def __call__(self, *a, **kw):
        return _Transport()(*a, **kw)


Transport = _Lazy()


async def verify_token(token: str) -> dict:
    import httpx
    from threads_bot import split_credentials, whoami
    cr = split_credentials(token)
    if not (cr.get("user_id") and cr.get("access_token")):
        return {"ok": False, "error": localefmt.chu("Cần Threads user ID và token, cách nhau dấu cách",
                                                    "The Threads user ID and token are needed, separated by a space")}
    async with httpx.AsyncClient(timeout=15) as c:
        info = await whoami(c, cr["access_token"])
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error", "")}
    return {"ok": True, "username": info.get("username", ""), "bot_name": info.get("name") or info.get("username", ""),
            "vao_duoc_nhom": False, "account_type": ""}


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, localefmt.chu("tài khoản Threads này chưa có thông tin đăng nhập",
                                    "this Threads account has no credentials yet")
    bot = _Transport()(token, "", None, giau_trang_thai=True)
    return await bot.send_text(chat_id, text)
