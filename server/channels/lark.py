"""Lark / Feishu channel (0.102.0): a dedicated bot answers customers through `lark_bot.LarkBot`.

Same transport as the owner's Lark control channel (0.85.0): a long connection (WebSocket) that Javis
opens OUT to Lark, so it works on a laptop or behind NAT with no public URL.

The account secret is the App ID and App Secret of one Lark custom app in one string,
"cli_... SECRET", because the channel-account store keeps exactly one encrypted secret per account
(the same trick as Slack's two tokens). An optional third word "lark" or "feishu" pins the cloud;
without it Javis tries Lark (international) first and then Feishu (mainland China), because an app
made on one platform does not exist on the other and the owner rarely knows which API host it is.
"""
from __future__ import annotations

import httpx

from channels import KenhSpec
import localefmt

SPEC = KenhSpec(
    id="lark", nhan="Lark", kind="bot", logo="lark", mau="#3370FF",
    lay_token=("Tạo một app tự dựng (custom app) ở Lark Developer, bật Bot, chọn nhận sự kiện qua kết nối "
               "dài (persistent connection) và đăng ký im.message.receive_v1, cấp quyền nhắn tin. Rồi dán "
               "App ID và App Secret cách nhau một dấu cách. Mỗi bot một app riêng, không dùng chung app "
               "với kênh admin."),
    tom_tat="Hợp cho khách doanh nghiệp dùng Lark hoặc Feishu. Vào được nhóm, gửi được ảnh và tài liệu.",
    nang_luc={"nhom": True, "gui_chu": True, "gui_file": True},
    en={
        "lay_token": ("Create a custom app in the Lark Developer console, enable Bot, choose to receive events "
                      "through a persistent connection and subscribe to im.message.receive_v1, and grant the "
                      "messaging permissions. Then paste the App ID and App Secret separated by a space. One app "
                      "per bot: do not reuse the app of your admin channel."),
        "tom_tat": "Good for business customers on Lark or Feishu. Joins groups, sends images and documents.",
    },
)

_CLOUDS = ("lark", "feishu")


def parse_token(raw) -> dict:
    """"cli_x SECRET [lark|feishu]" -> {"app_id", "app_secret", "domain"}; domain "" = try both."""
    parts = str(raw or "").split()
    domain = ""
    if parts and parts[-1].lower() in _CLOUDS:
        domain = parts.pop().lower()
    return {"app_id": parts[0] if parts else "", "app_secret": parts[1] if len(parts) > 1 else "",
            "domain": domain}


def _bot_class():
    from lark_bot import LarkBot

    class LarkCustomerBot(LarkBot):
        """LarkBot fed by a channel-account token string. When the cloud is not pinned, a refused
        tenant token on one cloud is retried once on the other, then the working cloud is kept."""

        def __init__(self, token, *a, **kw):
            cred = parse_token(token) if not isinstance(token, dict) else dict(token)
            self._domain_pinned = bool(cred.get("domain"))
            super().__init__({**cred, "domain": cred.get("domain") or "lark"}, *a, **kw)

        async def _tenant_token(self, client) -> str:
            try:
                return await super()._tenant_token(client)
            except RuntimeError:
                if self._domain_pinned:
                    raise
                import lark_bot
                self.domain = "feishu" if self.domain == "lark" else "lark"
                self.base = lark_bot.DOMAINS[self.domain]
                self._domain_pinned = True
                return await super()._tenant_token(client)

    return LarkCustomerBot


class _Lazy:
    def __call__(self, *a, **kw):
        return _bot_class()(*a, **kw)


Transport = _Lazy()


def _admin_app_id() -> str:
    try:
        import config as cfgmod
        return str((cfgmod.read_settings().get("lark") or {}).get("app_id") or "").strip()
    except Exception:      # noqa: BLE001 - no settings means no admin app to clash with
        return ""


async def _check_cloud(client, domain: str, cred: dict) -> dict:
    import lark_bot
    base = lark_bot.DOMAINS[domain]
    d = (await client.post(base + "/open-apis/auth/v3/tenant_access_token/internal",
                           json={"app_id": cred["app_id"], "app_secret": cred["app_secret"]})).json() or {}
    if d.get("code") != 0 or not d.get("tenant_access_token"):
        return {"ok": False, "why": lark_bot._explain(d)}
    info = (await client.get(base + "/open-apis/bot/v3/info",
                             headers={"Authorization": f"Bearer {d['tenant_access_token']}"})).json() or {}
    bot = info.get("bot") or {}
    if info.get("code") != 0 or not bot.get("open_id"):
        return {"ok": False, "no_bot": True, "why": lark_bot._explain(info)}
    return {"ok": True, "name": str(bot.get("app_name") or "")}


async def verify_token(token: str) -> dict:
    """Check the App ID / App Secret on Lark (or Feishu) and that the app has the Bot ability."""
    cred = parse_token(token)
    if not cred["app_id"] or not cred["app_secret"]:
        return {"ok": False, "error": localefmt.chu(
            "Cần App ID (cli_...) và App Secret, cách nhau một dấu cách.",
            "Both are needed: the App ID (cli_...) and the App Secret, separated by a space.")}
    if cred["app_id"] == _admin_app_id():
        return {"ok": False, "error": localefmt.chu(
            "App này đang chạy kênh admin Lark của bạn. Bot chuyên trách phải dùng một app Lark RIÊNG, "
            "không thì tin nhắn bị chia ngẫu nhiên giữa hai bên.",
            "This app runs your Lark admin channel. A dedicated bot needs a SEPARATE Lark app, otherwise "
            "messages are split at random between the two.")}
    clouds = (cred["domain"],) if cred["domain"] else _CLOUDS
    lan = []
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            for domain in clouds:
                r = await _check_cloud(c, domain, cred)
                if r["ok"]:
                    nhan = "Feishu" if domain == "feishu" else "Lark"
                    return {"ok": True, "username": cred["app_id"], "bot_name": r["name"] or cred["app_id"],
                            "vao_duoc_nhom": True, "account_type": nhan}
                if r.get("no_bot"):
                    return {"ok": False, "error": localefmt.chu(
                        f"App đúng nhưng chưa bật tính năng Bot ({r['why']}). Vào Lark Developer, mục "
                        "Features, bật Bot rồi phát hành lại phiên bản app.",
                        f"The app is right but its Bot feature is off ({r['why']}). In the Lark Developer "
                        "console, Features, turn on Bot and publish a new app version.")}
                lan.append(r["why"])
    except Exception as e:      # noqa: BLE001 - the owner gets a sentence, never a traceback
        return {"ok": False, "error": localefmt.chu(f"Không nối được Lark: {e}", f"Could not reach Lark: {e}")}
    return {"ok": False, "error": localefmt.chu(
        f"Lark từ chối App ID / App Secret ({'; '.join(lan)}). Kiểm tra lại hai giá trị, và app tạo ở "
        "Lark hay Feishu (thêm chữ feishu ở cuối nếu là Feishu).",
        f"Lark refused the App ID / App Secret ({'; '.join(lan)}). Check both values, and whether the app "
        "was made on Lark or Feishu (add the word feishu at the end for Feishu).")}


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, localefmt.chu("tài khoản Lark này chưa có App ID / App Secret",
                                    "this Lark account has no App ID / App Secret yet")
    bot = Transport(token, "", None, giau_trang_thai=True)
    return await bot.send_text(chat_id, text)


async def send_file(tk: dict, chat_id: str, path: str, caption: str = "", chat_type: str = "private"):
    """Send one image or file the owner picked in the inbox (2026-11-24). `(ok, error)`, as `gui`."""
    token = str(tk.get("token") or "").strip()
    if not token:
        return False, localefmt.chu("tài khoản Lark này chưa có App ID / App Secret",
                                    "this Lark account has no App ID / App Secret yet")
    bot = Transport(token, "", None, giau_trang_thai=True)
    return await bot.send_file(path, caption, chat=chat_id)
