"""The owner's control channels on Slack, WhatsApp (0.71.0), Discord and Lark/Feishu (0.85.0).

"Control channel" = the owner talks to Javis itself (full brain, tools, background work), the
way the Telegram and Zalo control bots work. Customer-facing bots live elsewhere
(`chatbot_runtime` + `channels/`).

Why one class instead of a third and fourth copy of the Zalo code in main.py: the pairing queue,
the prefix on chat ids, the restart/status/allow/test endpoints and the "send a result back"
path are the same rules for every channel. Only the transport and the settings shape differ.

Access is FAIL-CLOSED, like Zalo and unlike Telegram: an empty allow-list lets nobody in. A
stranger who writes gets a 4-digit pairing code and lands in a queue the owner approves with
one click on the Admin channels page. Slack allows by USER id (U...), WhatsApp by phone number,
Discord by user id, Lark by open_id (ou_...).

Each channel also DESCRIBES its settings (`plain`, `secrets`), so main.py masks, saves and
restarts every channel with one loop instead of a branch per platform.
"""
from __future__ import annotations

import re
import secrets
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Optional

import localefmt
from bot_gateway import parse_chat_ids

QUEUE_MAX = 20
QUEUE_TTL = 30 * 60
QUEUE_REMIND = 10 * 60


class OwnerChannel:
    def __init__(self, key: str, label: str, prefix: str, transport: Callable,
                 credentials: Callable[[dict], object], required: tuple, id_label: tuple,
                 plain: Optional[Dict[str, Callable]] = None, secret_fields: tuple = (),
                 trust_turn_ids: bool = False):
        self.key = key                  # settings section and channel name: "slack" | "whatsapp"
        self.label = label
        self.prefix = prefix            # owner_chat prefix: "slack:" | "whatsapp:"
        self._transport = transport     # () -> transport class
        self._credentials = credentials  # settings section -> token argument for the transport
        self.required = required        # settings fields that must be non-empty to start
        self.id_label = id_label        # (vi, en): what the allow-list holds, for messages
        # Settings fields: plain ones are shown back to the form (each with a normaliser),
        # secrets are masked on read and only overwritten when a new value is sent.
        self.plain: Dict[str, Callable] = dict(plain or {})
        self.secret_fields = tuple(secret_fields)
        # The allow-list holds PEOPLE, but a turn's chat id may be a channel or DM id (Slack D...,
        # a Discord channel, a Lark oc_...). Ids the turn itself produced are trusted for replies.
        self.trust_turn_ids = bool(trust_turn_ids)
        self.bot = None
        self.queue: Dict[str, dict] = {}
        self.deps: Dict[str, Callable] = {}

    # ---- wiring -----------------------------------------------------------------------
    def wire(self, **deps):
        """answer, command, stt, brain_root_for, read_settings, update_settings."""
        self.deps.update(deps)

    def idl(self) -> str:
        return localefmt.chu(*self.id_label)

    def cfg(self) -> dict:
        rs = self.deps.get("read_settings")
        if rs is None:              # not wired yet (tests, or a call before startup)
            import config
            rs = config.read_settings
        return (rs().get(self.key) or {})

    def allowed(self, c: Optional[dict] = None) -> list:
        return parse_chat_ids((c if c is not None else self.cfg()).get("allow"))

    def configured(self, c: Optional[dict] = None) -> bool:
        c = c if c is not None else self.cfg()
        return all(str(c.get(k) or "").strip() for k in self.required)

    def running(self) -> bool:
        return bool(self.bot and self.bot._task and not self.bot._task.done())

    # ---- pairing ----------------------------------------------------------------------
    def _who(self, meta) -> str:
        """The id the allow-list is checked against: the sender, not the chat."""
        m = meta or {}
        return str(m.get("user_id") or m.get("chat_id") or "").strip()

    def _prune(self):
        now = time.time()
        for k in [k for k, v in self.queue.items() if now - v.get("ts", 0) > QUEUE_TTL]:
            self.queue.pop(k, None)

    def _refusal(self, code: str) -> str:
        return localefmt.chu(
            f"Bạn chưa được cấp quyền dùng Javis này.\nMã ghép nối của bạn: {code}\n"
            "Đưa mã này cho chủ máy để họ cho phép ở trang Kênh Admin.",
            f"You are not allowed to use this Javis yet.\nYour pairing code: {code}\n"
            "Give this code to the owner so they can allow you on the Admin channels page.")

    def _queue(self, meta) -> str:
        """Put a stranger in the pairing queue. Returns what to reply ("" = stay quiet)."""
        self._prune()
        who = self._who(meta)
        if not who:
            return ""
        name = str((meta or {}).get("user_name") or "")[:80]
        old = self.queue.get(who)
        if old:
            old["ts"] = time.time()
            old["lan"] = old.get("lan", 0) + 1
            old["ten"] = name or old.get("ten", "")
            if time.time() - old.get("nhac", 0) < QUEUE_REMIND:
                return ""          # one refusal per 10 minutes, so nobody floods the queue
            old["nhac"] = time.time()
            return self._refusal(old["ma"])
        if len(self.queue) >= QUEUE_MAX:
            self.queue.pop(min(self.queue, key=lambda k: self.queue[k].get("ts", 0)), None)
        code = f"{secrets.randbelow(9000) + 1000}"
        self.queue[who] = {"chat_id": who, "ten": name, "ma": code, "ts": time.time(),
                           "nhac": time.time(), "lan": 1}
        return self._refusal(code)

    def precheck(self, text, meta):
        if self._who(meta) in self.allowed():
            return None
        return {"reply": self._queue(meta)}

    # ---- turns ------------------------------------------------------------------------
    async def answer(self, text, meta=None, progress=None, channel=None, bot=None):
        """Prefix the chat id before the shared core sees it: it is the session key, the brain
        key and the `owner_chat` background results are routed by. The transport keeps the
        raw id it needs to reply."""
        m = dict(meta or {})
        raw = str(m.get("chat_id") or "").strip()
        m["chat_id"] = (self.prefix + raw) if raw else "default"
        return await self.deps["answer"](text, m, progress, channel=self.key, bot=bot)

    def inbox_dir(self, chat=None):
        root = self.deps["brain_root_for"](self.prefix + str(chat or ""))
        return str(Path(root) / "inbox" / self.key)

    def restart(self) -> bool:
        if self.bot:
            try:
                self.bot.stop()
            except Exception as e:
                print(f"[{self.key} stop] {e}", file=sys.stderr)
            self.bot = None
        c = self.cfg()
        if not (c.get("enabled") and self.configured(c)):
            return False
        Lop = self._transport()
        # No allow-list for the transport: `precheck` handles strangers and hands them a code.
        self.bot = Lop(self._credentials(c), "", self.answer, self.deps.get("command"),
                       download_dir=self.inbox_dir, precheck_fn=self.precheck,
                       stt_fn=self.deps.get("stt"))
        self.bot.start()
        return True

    def stop(self):
        if self.bot:
            self.bot.stop()
            self.bot = None

    # ---- API helpers ------------------------------------------------------------------
    def status(self) -> dict:
        c = self.cfg()
        self._prune()
        b = self.bot
        return {
            "enabled": bool(c.get("enabled")), "configured": self.configured(c),
            "allow": c.get("allow", ""), "allow_ids": self.allowed(c),
            "running": self.running(),
            "status": b.status if b else "off",
            "last_error": (b.last_error if b else "") or "",
            "bot_name": (b.bot_username if b else "") or "",
            "loi_danh_tinh": (getattr(b, "loi_danh_tinh", "") if b else "") or "",
            "cho": sorted(self.queue.values(), key=lambda x: x.get("ts", 0), reverse=True),
        }

    def allow(self, who: str, on: bool) -> list:
        who = str(who or "").strip()
        if on and who:
            ids = self.allowed()
            if who not in ids:
                ids.append(who)
            # Cập nhật TỪNG PHẦN. Trước 0.86.2 chỗ này đưa đúng mảnh này cho write_settings, mà hàm
            # đó thay cả file: cho phép một người là mất sạch tên miền, mật khẩu, khoá API.
            up = self.deps.get("update_settings")
            if up is None:
                import config
                up = config.update_settings
            up({self.key: {"allow": ", ".join(ids)}})
        self.queue.pop(who, None)
        return self.allowed()

    def _sender(self):
        """A short-lived transport for one outgoing message (no socket, no registration)."""
        c = self.cfg()
        if not (c.get("enabled") and self.configured(c)):
            return None
        return self._transport()(self._credentials(c), "", None, giau_trang_thai=True)

    async def send_to(self, chat_id, text) -> tuple:
        """Send a background result to `chat_id` (raw id, prefix already stripped). An empty id
        or one outside the allow-list goes to the first allowed id, like Telegram and Zalo."""
        b = self._sender()
        if not b:
            return False, localefmt.chu(f"Kênh {self.label} chưa bật hoặc thiếu thông tin",
                                        f"The {self.label} channel is off or not configured")
        ids = self.allowed()
        cid = str(chat_id or "").strip()
        if self.trust_turn_ids:
            # A Slack DM channel id (D...) is not what the allow-list holds (user ids), so any
            # id the turn itself produced is trusted; empty falls back to the first owner.
            target = cid or (ids[0] if ids else "")
        else:
            target = cid if (cid and cid in ids) else (ids[0] if ids else "")
        if not target:
            return False, localefmt.chu(f"Chưa có {self.idl()} nào được phép",
                                        f"No allowed {self.idl()} yet")
        return await b.send_text(target, text)

    async def test(self) -> dict:
        ids = self.allowed()
        b = self._sender()
        if not b or not ids:
            return {"ok": False, "error": localefmt.chu(
                f"Bật kênh, điền đủ thông tin và cho phép ít nhất một {self.idl()} trước đã.",
                f"Turn the channel on, fill in the credentials and allow at least one {self.idl()} first.")}
        sent, errs = 0, []
        for who in ids:
            ok, err = await b.send_text(who, localefmt.chu(
                f"Javis đã kết nối qua {self.label}. Nhắn câu hỏi bất kỳ nhé.",
                f"Javis is connected through {self.label}. Ask anything."))
            if ok:
                sent += 1
            else:
                errs.append(f"{who}: {str(err)[:120]}")
        return {"ok": sent > 0, "sent": sent, "total": len(ids), "error": "; ".join(errs)[:400]}

    def missing(self) -> str:
        """Why this channel cannot carry background results ("" = it can)."""
        c = self.cfg()
        if not c.get("enabled"):
            return localefmt.chu(f"{self.label} chưa bật", f"{self.label} is not enabled")
        if not self.configured(c):
            return localefmt.chu(f"{self.label} thiếu thông tin đăng nhập", f"{self.label} is missing credentials")
        if not self.allowed(c):
            return localefmt.chu(f"{self.label} chưa có {self.idl()} được phép",
                                 f"{self.label} has no allowed {self.idl()}")
        return ""


def _slack_transport():
    from slack_bot import SlackBot
    return SlackBot


def _wa_transport():
    from whatsapp_bot import WhatsAppBot
    return WhatsAppBot


def _discord_transport():
    from discord_bot import DiscordBot
    return DiscordBot


def _lark_transport():
    from lark_bot import LarkBot
    return LarkBot


def _digits(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def lark_domain(v) -> str:
    """"lark" (international, open.larksuite.com) unless the owner picked "feishu" (China). Lark is
    the default because it is what businesses outside mainland China sign up for."""
    return "feishu" if str(v or "").strip().lower() == "feishu" else "lark"


SLACK = OwnerChannel(
    "slack", "Slack", "slack:", _slack_transport,
    lambda c: f"{c.get('bot_token', '')} {c.get('app_token', '')}",
    ("bot_token", "app_token"), ("Slack user ID", "Slack user ID"),
    secret_fields=("bot_token", "app_token"), trust_turn_ids=True)

WHATSAPP = OwnerChannel(
    "whatsapp", "WhatsApp", "whatsapp:", _wa_transport,
    lambda c: {"phone_number_id": c.get("phone_number_id", ""),
               "access_token": c.get("access_token", ""), "app_secret": c.get("app_secret", "")},
    ("phone_number_id", "access_token", "app_secret"), ("số điện thoại", "phone number"),
    plain={"phone_number_id": _digits}, secret_fields=("access_token", "app_secret"))

DISCORD = OwnerChannel(
    "discord", "Discord", "discord:", _discord_transport,
    lambda c: str(c.get("bot_token", "") or ""),
    ("bot_token",), ("Discord user ID", "Discord user ID"),
    secret_fields=("bot_token",), trust_turn_ids=True)

LARK = OwnerChannel(
    "lark", "Lark", "lark:", _lark_transport,
    lambda c: {"app_id": str(c.get("app_id", "") or "").strip(),
               "app_secret": c.get("app_secret", ""), "domain": lark_domain(c.get("domain"))},
    ("app_id", "app_secret"), ("Lark open_id", "Lark open_id"),
    plain={"app_id": lambda v: str(v or "").strip(), "domain": lark_domain},
    secret_fields=("app_secret",), trust_turn_ids=True)

ALL = (SLACK, WHATSAPP, DISCORD, LARK)


def get(key: str):
    """The channel whose settings section is `key`, or None."""
    for ch in ALL:
        if ch.key == key:
            return ch
    return None


def by_prefix(owner_chat: str):
    """(channel, raw id) for an owner_chat like "slack:D123", or (None, "")."""
    s = str(owner_chat or "")
    for ch in ALL:
        if s.startswith(ch.prefix):
            return ch, s[len(ch.prefix):]
    return None, ""


def whatsapp_app_secrets(account_secrets=()) -> list:
    """Every app secret a valid WhatsApp webhook may be signed with: the control number's plus
    each customer-bot account's."""
    out = []
    s = str(WHATSAPP.cfg().get("app_secret") or "").strip()
    if s:
        out.append(s)
    out.extend(x for x in account_secrets if x)
    return out
