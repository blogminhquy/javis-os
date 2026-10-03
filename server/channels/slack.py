"""Slack channel (Socket Mode): a dedicated bot answers through `slack_bot.SlackBot`.

The account secret is BOTH tokens of one Slack app in one string, "xoxb-... xapp-...", because
the channel-account store keeps exactly one encrypted secret per account.
"""
from __future__ import annotations

from channels import KenhSpec
import localefmt

SPEC = KenhSpec(
    id="slack", nhan="Slack", kind="bot", logo="slack", mau="#4A154B",
    lay_token=("Tạo một app Slack từ manifest trong docs/en/29-slack-whatsapp.md, cài vào workspace, "
               "rồi dán CẢ HAI token cách nhau một dấu cách: Bot token (xoxb-...) và App token (xapp-...)."),
    tom_tat="Hợp cho đội nhóm và khách doanh nghiệp. Vào được kênh, gửi được ảnh và tài liệu.",
    nang_luc={"nhom": True, "gui_chu": True, "gui_file": True},
    en={
        "lay_token": ("Create a Slack app from the manifest in docs/en/29-slack-whatsapp.md, install it to the "
                      "workspace, then paste BOTH tokens separated by a space: the Bot token (xoxb-...) and "
                      "the App token (xapp-...)."),
        "tom_tat": "Good for teams and business customers. Joins channels, sends images and documents.",
    },
)


def _Transport():
    from slack_bot import SlackBot
    return SlackBot


class _Lazy:
    def __call__(self, *a, **kw):
        return _Transport()(*a, **kw)


Transport = _Lazy()


async def verify_token(token: str) -> dict:
    """Check the bot token with auth.test and that an app token is present."""
    import httpx
    from slack_bot import split_tokens, _explain_error
    bot, app = split_tokens(token)
    if not bot or not app:
        return {"ok": False, "error": localefmt.chu(
            "Cần cả hai token: Bot token (xoxb-...) và App token (xapp-...), cách nhau một dấu cách.",
            "Both tokens are needed: the Bot token (xoxb-...) and the App token (xapp-...), separated by a space.")}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            d = (await c.post("https://slack.com/api/auth.test",
                              headers={"Authorization": f"Bearer {bot}"})).json()
            d2 = (await c.post("https://slack.com/api/apps.connections.open",
                               headers={"Authorization": f"Bearer {app}"})).json()
    except Exception as e:
        return {"ok": False, "error": localefmt.chu(f"Không nối được Slack: {e}", f"Could not reach Slack: {e}")}
    if not d.get("ok"):
        return {"ok": False, "error": localefmt.chu(f"Bot token bị từ chối: {_explain_error(d.get('error'))}",
                                                    f"Bot token refused: {_explain_error(d.get('error'))}")}
    if not d2.get("ok"):
        return {"ok": False, "error": localefmt.chu(
            f"App token bị từ chối: {_explain_error(d2.get('error'))}. Bật Socket Mode và cấp scope connections:write.",
            f"App token refused: {_explain_error(d2.get('error'))}. Turn on Socket Mode and grant connections:write.")}
    return {"ok": True, "username": str(d.get("user") or ""), "bot_name": str(d.get("user") or ""),
            "vao_duoc_nhom": True, "account_type": str(d.get("team") or "")}


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, localefmt.chu("tài khoản Slack này chưa có token", "this Slack account has no token yet")
    bot = _Transport()(token, "", None, giau_trang_thai=True)
    return await bot.send_text(chat_id, text)
