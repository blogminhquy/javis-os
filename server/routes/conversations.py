"""Hộp thư hội thoại khách (Chatbot V2): đọc kho `conversations` cho trang Hội thoại.

Danh sách hội thoại, lịch sử tin, đánh dấu đã đọc, `mode` để người thật TIẾP QUẢN một cuộc
chat (bot im) và trả lại cho AI (phần chạy thật nằm ở `chatbot_runtime`, xem `che_do`), và từ
0.61.0 `reply`: chủ trả lời khách NGAY TỪ JAVIS qua năng lực gửi của kênh (sổ `channels`).

Kênh và tài khoản kênh có API riêng ở `routes/channels.py`; hai đường cũ
`/conversations/channels` và `/conversations/zalo/{id}/watch` giữ làm bí danh cho bookmark cũ.

Xác thực: như mọi route khác, đi qua `_auth_guard` của main.py (cookie phiên hoặc API token).
Không nhận `import main` - mọi thứ cần từ main đi qua `deps`.
"""
from __future__ import annotations

import mimetypes
import time
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from fastapi import APIRouter, Form, Query
from fastapi.responses import FileResponse, JSONResponse

import channel_accounts
import channels
import chatbot_store
import conversations
import inbox_state
import localefmt
import routes.channels as channels_routes

router = APIRouter()


@dataclass
class ConversationsDeps:
    # Trạng thái sống của một bot (chatbot_runtime.status) - để mục Kênh nói bot đang chạy hay không.
    bot_status: Callable[[str], dict]
    # Chủ nhờ bot trả lời từ Hộp thư (0.65.5): `manual_answer(conv, msgs, draft)` chạy Agent, `manual_done(conv, msgs, text, meta)`
    # ghi và dạy sau khi đã gửi. Không import chatbot_runtime ở đây: route đi qua deps như mọi route khác.
    manual_answer: Callable = None
    manual_done: Callable = None
    # `brain_root(brain) -> str`: thư mục gốc của một brain. Cần cho `/conversations/{id}/media` (0.171.0), nơi phát ảnh và file khách
    # gửi mà kênh đã tải về brain của bot. Thiếu thì đường đó trả 404.
    brain_root: Callable = None
    # Chatbot v5: the bot's approval queue (`pending(bot_id) -> [{chat_id, ...}]`) and taking one chat off it
    # (`drop_pending(bot_id, chat_id)`), so the inbox can show and settle "someone called the A.I. here".
    pending: Callable = None
    drop_pending: Callable = None
    # `manual_meta(conv, last) -> meta`: the turn meta for a stored conversation, to record a sent draft as the bot's words.
    manual_meta: Callable = None


# Ảnh và file khách gửi chỉ được phát từ hai thư mục mà các kênh tự tải về: `inbox/` (Telegram, Zalo Bot, Slack, WhatsApp,
# Messenger, Discord, Lark ghi vào `inbox/khach`) và `attachments/` (ảnh Zalo cá nhân bot đã tải để xem). Không ghi chú nào khác của brain.
_THU_MUC_MEDIA = ("inbox", "attachments")
_DUOI_XEM_THANG = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".mp4", ".webm", ".mp3", ".ogg", ".m4a",
                   ".wav", ".opus", ".pdf")


_DEPS: "ConversationsDeps" = None   # type: ignore


def _404(msg: str = ""):
    msg = msg or localefmt.chu("không có hội thoại nào id đó", "no conversation with that id")
    return JSONResponse({"ok": False, "error": msg}, status_code=404)


def register(app, deps: ConversationsDeps):
    global _DEPS
    _DEPS = deps

    def _tk_goc(c: dict) -> str:
        key = str(c.get("channel_account_id") or "")
        return key.split(":", 1)[1] if ":" in key else key

    async def _gui_tin(c: dict, txt: str, tieng_vong: bool = False, reply_to: Optional[dict] = None):
        """Gửi một tin chữ vào cuộc chat qua năng lực `gui` của kênh. Trả (ok, lỗi). Dùng chung cho chủ gõ tay và cho lượt
        nhờ bot trả lời (0.65.5), để hai đường không lệch nhau ở cách dựng tài khoản gửi.

        `tieng_vong=True`: trên Zalo cá nhân phải nhớ câu vừa gửi TRƯỚC khi gửi, y như `Transport._gui`, không thì vòng đọc thấy nó
        quay về như tin của chính chủ (bot tưởng chủ vừa nhắn tay nên im cả quãng) hoặc như tin của một khách (bot tự trả lời chính
        mình trong nhóm). Câu CHỦ gõ ở Hộp thư cũng bật cờ này (0.108.0): Javis đã tự ghi câu đó, và từ javis-zalo 1.3.0 tin của
        chính tài khoản quay về vòng đọc kèm `isSelf`, nên không nhớ thì Hộp thư hiện câu chủ gõ HAI lần.

        `reply_to` (tin khách bot đang trả lời): trong nhóm Zalo cá nhân, câu của bot tag đúng người gửi tin đó, y như bot tự trả lời."""
        kenh = str(c.get("channel") or "")
        raw = _tk_goc(c)
        if tieng_vong and kenh == "zalo_personal":
            try:
                import zalo_personal_channel as zc
                zc.ghi_da_gui(raw, str(c.get("external_chat_id") or ""), txt)
            except Exception:      # noqa: BLE001 - không nhớ được tiếng vọng thì vẫn gửi, tệ nhất là một dòng trùng trong Hộp thư
                pass
        s = channels.spec(kenh)
        if not s:
            return False, localefmt.chu(f"kênh '{kenh}' không có trong sổ đăng ký",
                                        f"channel '{kenh}' is not in the registry")
        tk = {"id": raw, "channel": kenh}
        if s.kind == "bot":
            a = channel_accounts.get_account(raw) or {}
            tk.update({k: a.get(k) for k in ("label", "external_id")})
            tk["token"] = channel_accounts.get_token(raw)
        extra = {}
        if tieng_vong and kenh == "zalo_personal" and reply_to and str(c.get("chat_type") or "") == "group":
            extra["mention"] = {"uid": reply_to.get("sender_id"), "name": reply_to.get("sender_name")}
        kq = await channels.gui(kenh, tk, str(c.get("external_chat_id") or ""), txt, str(c.get("chat_type") or "private"), **extra)
        if tieng_vong and kenh == "zalo_personal" and kq and kq[0]:
            # Hộp thư vừa trả lời chat này: tiếng vọng của câu này bị lọc ở vòng đọc nên không tính là chủ nhắn tay,
            # phải tự báo kẻo 10 phút sau bot trả lời lại tin khách đã có người đáp (0.136.0).
            try:
                import zalo_personal_channel as zc
                zc.bo_cho_chu(raw, str(c.get("external_chat_id") or ""))
            except Exception:      # noqa: BLE001
                pass
        return kq

    def _hesitant() -> list:
        """Nhóm bot vừa cân nhắc nói rồi im trong 24 giờ qua (kho bộ phán xử). Kho hỏng hay chưa có thì rỗng: bộ lọc
        chỉ mất phần nhóm chứ không sập hòm thư."""
        try:
            import chatbot_reply_policy_store as rps
            return rps.hesitant_chats(time.time() - 86400)
        except Exception:      # noqa: BLE001
            return []

    def _bot_silence(conv: dict, msgs: list):
        """Vì sao bot im ở tin khách CUỐI của cuộc chat này, nếu bộ phán xử có ghi. Chỉ khi cuộc chat đang ở chế độ AI, tin
        cuối là của khách, và quyết định gần nhất là `silent` cho đúng tin đó (mốc giờ lệch không quá 60 giây, vì quyết định ghi
        theo giờ tin). Người thật đang tiếp quản thì bot im là hiển nhiên, không cần nói."""
        try:
            bot_id = str(conv.get("bot_id") or "")
            if not bot_id or str(conv.get("mode") or "ai") != "ai" or not msgs or msgs[-1].get("sender_type") != "customer":
                return None
            import chatbot_reply_policy_store as rps
            d = rps.last_decision(bot_id, str(conv.get("external_chat_id") or ""))
            if not d or d.get("verdict") != "silent":
                return None
            if float(d.get("ts") or 0) < float(msgs[-1].get("created_at") or 0) - 60:
                return None
            return {"decision_id": d.get("id"), "code": d.get("silence_code") or "", "reason": d.get("reason") or "",
                    "score": d.get("score"), "threshold": d.get("threshold")}
        except Exception:      # noqa: BLE001 - dòng phụ này hỏng không được làm hỏng việc đọc hội thoại
            return None

    def _ten_bot(bot_id: str) -> str:
        """Tên bot để hiện trên hàng hội thoại và ở dropdown lọc. Bot đã xoá thì báo thẳng, không lòi id thô."""
        if not bot_id:
            return ""
        b = chatbot_store.get_bot(bot_id)
        return str((b or {}).get("name") or "") or localefmt.chu("Bot đã xoá", "Deleted bot")

    # Chats logged before 0.380.0 by a channel that records without a bot (Zalo "record chats") get the bot on duty for
    # their nick once, at start (owner, 2026-10-28: "a chat in the inbox already has an A.I.").
    try:
        conversations.fill_missing_bots()
    except Exception as e:      # noqa: BLE001
        print(f"[conversations] fill_missing_bots: {e}", file=sys.stderr)

    class _StateCtx:
        """Per-request cache for the "who is handling it" state (Chatbot v5): bot records, running flags and approval
        queues are read once per bot, not once per row."""

        def __init__(self, hesitant):
            self.hesitant = hesitant
            self.bots, self.running, self.pending = {}, {}, {}
            self.no_bot = conversations.no_bot_accounts()

        def of(self, row: dict) -> dict:
            bid = str(row.get("bot_id") or "")
            if bid and bid not in self.bots:
                self.bots[bid] = chatbot_store.get_bot(bid)
                try:
                    self.running[bid] = bool((_DEPS.bot_status(bid) or {}).get("running"))
                except Exception:      # noqa: BLE001
                    self.running[bid] = False
                try:
                    self.pending[bid] = {str(x.get("chat_id")): int(x.get("lan") or 0)
                                         for x in (_DEPS.pending(bid) if _DEPS.pending else []) if int(x.get("lan") or 0) > 0}
                except Exception:      # noqa: BLE001
                    self.pending[bid] = {}
            bot = self.bots.get(bid) if bid else None
            return inbox_state.state(row, bot, self.running.get(bid, False), self.pending.get(bid, {}),
                                     conversations.khach_dang_cho(row, self.hesitant),
                                     no_bot_wanted=str(row.get("channel_account_id") or "") in self.no_bot)

    def _attach_state(items: list, ctx: "_StateCtx") -> None:
        for it in items:
            st = ctx.of(it)
            bot = ctx.bots.get(str(it.get("bot_id") or "")) or {}
            yield_min = bot.get("nhuong_tay_phut")
            it.update(who=st["who"], who_code=st["who_code"], ai_allowed=st["ai_allowed"], ai_pending=st["pending"],
                      draft=st["draft"], reply_when=str(bot.get("reply_when") or ""),
                      yield_min=yield_min if isinstance(yield_min, int) else None)

    def _day_range(date_from: str, date_to: str) -> tuple:
        """("YYYY-MM-DD", "YYYY-MM-DD"), both days included, in the server's time zone -> (since, until) timestamps.
        A missing or unreadable end stays open (0); the two ends swap when given backwards."""
        def midnight(v: str) -> float:
            try:
                return time.mktime(time.strptime(str(v or "").strip()[:10], "%Y-%m-%d"))
            except (ValueError, OverflowError):
                return 0.0
        a, b = midnight(date_from), midnight(date_to)
        if a and b and b < a:
            a, b = b, a
        return a, (midnight(time.strftime("%Y-%m-%d", time.localtime(b + 36 * 3600))) if b else 0.0)

    def _ids_param(raw: str) -> list:
        return [x.strip() for x in str(raw or "").split(",") if x.strip()]

    @router.get("/conversations")
    async def conversations_list(channel: str = "", bot_id: str = "", account_id: str = "",
                                 q: str = "", mode: str = "", limit: int = 50, offset: int = 0,
                                 status: str = "", chat_type: str = "", tag: int = 0, has_contact: int = 0,
                                 sort: str = "", account_ids: str = "", who: str = "", tags_any: str = "",
                                 tags_none: str = "", date_from: str = Query("", alias="from"),
                                 date_to: str = Query("", alias="to"), last_by: str = "", pinned: int = 0):
        """Danh sách hội thoại mới nhất trước, kèm vài con số đầu trang (cùng bộ lọc).

        0.65.3: thêm `status` (unread | need_reply | human) và `chat_type` (group | private); mỗi hàng có `bot_name`;
        `facets` là số hội thoại cho từng lựa chọn dropdown (toàn hòm thư, không theo bộ lọc) và `bots` là danh sách bot
        có hội thoại kèm tên, cho dropdown Bot.

        2026-10-25: `tag` (inbox tag id), `has_contact=1` (the customer left a phone number or email) and `sort=waiting`
        (unanswered customer message waiting longest first). Each row has `tags`; the first page also returns `tags`, the
        owner's tag list with counts, and `facets.has_contact`.

        Chatbot v5 (2026-10-28): `account_ids` (comma-separated account keys, the channel picker), `tags_any` /
        `tags_none` (comma-separated tag ids), and `who` (you | ai | owner | log, see `inbox_state`). Every row carries
        `who`, `who_code`, `ai_allowed`, `ai_pending` and `draft`; the first page also returns `who_counts` for the
        same filters without `who`, plus `you_by_account` ("Needs you" per account key) and `you_total`, both over the
        whole inbox whatever the filters.

        2026-10-25 (row menu): hidden conversations stay out of the list unless `status=hidden` asks for exactly them;
        a search (`q`) finds them too, so a customer the owner hid can always be looked up. `facets.status.hidden`
        counts them."""
        hesitant = _hesitant()
        hidden = "only" if status == "hidden" else ("" if q.strip() else "exclude")
        since, until = _day_range(date_from, date_to)
        extra = dict(tag=tag, has_contact=bool(has_contact), sort=sort, hidden=hidden,
                     account_ids=_ids_param(account_ids), tags_any=_ids_param(tags_any), tags_none=_ids_param(tags_none),
                     since=since, until=until, last_by=last_by, pinned=bool(pinned))
        ctx = _StateCtx(hesitant)
        who = who if who in inbox_state.WHO else ""
        who_counts, total = None, None
        if who or offset == 0:
            # The state needs the bot record, so it is worked out here rather than in SQL: every matching row once,
            # then one page of the ids that kept the wanted `who`.
            base = dict(extra)
            if account_id:
                base["account_ids"] = (base["account_ids"] or []) + [account_id]
            light = conversations.state_rows(channel=channel, bot_id=bot_id, q=q, status=status, chat_type=chat_type,
                                             hesitant=hesitant, **base)
            states = [(r["id"], ctx.of(r)["who"]) for r in light]
            who_counts = inbox_state.count({"who": w} for _, w in states)
            # Every row the filters match (the Channels tab pages through an account's chats with it).
            total = len(states)
            # "Needs you" per channel account (the channel picker's badges) and in all (the tab's badge) count the whole
            # inbox: ticking one Page or searching must not make the other Pages' numbers vanish.
            narrowed = bool(channel or bot_id or account_id or q or status or chat_type or tag or has_contact
                            or base["account_ids"] or base["tags_any"] or base["tags_none"] or since or until
                            or base["last_by"] or pinned)
            every = conversations.state_rows(hesitant=hesitant, hidden="exclude") if narrowed else light
            by_acc, you_total = {}, 0
            for r in every:
                if ctx.of(r)["who"] == "you":
                    k = str(r.get("channel_account_id") or "")
                    by_acc[k] = by_acc.get(k, 0) + 1
                    you_total += 1
            who_counts["you_by_account"] = by_acc
            who_counts["you_total"] = you_total
        if who:
            keep = [i for i, w in states if w == who]
            page = keep[max(0, offset):max(0, offset) + max(1, min(int(limit or 50), conversations.MAX_DANH_SACH))]
            items = conversations.danh_sach(channel=channel, bot_id=bot_id, account_id=account_id, q=q, mode=mode,
                                            limit=len(page) or 1, offset=0, status=status, chat_type=chat_type,
                                            hesitant=hesitant, ids=page, **extra)
        else:
            items = conversations.danh_sach(channel=channel, bot_id=bot_id, account_id=account_id,
                                            q=q, mode=mode, limit=limit, offset=offset,
                                            status=status, chat_type=chat_type, hesitant=hesitant, **extra)
        _attach_state(items, ctx)
        if offset > 0:
            # Trang thứ hai trở đi (0.65.11, cuộn xuống thì tải thêm) chỉ cần các dòng: số đếm, bộ lọc và danh sách bot đã có từ trang
            # đầu, tính lại cho mỗi trang là tốn công vô ích.
            for it in items:
                it["bot_name"] = _ten_bot(str(it.get("bot_id") or ""))
                it["need_reply"] = conversations.can_tra_loi(it, hesitant)
            return {"ok": True, "items": items}
        phone_lookup = None
        if q and conversations.chuan_hoa_sdt(q) and channel in ("", "zalo_personal") \
                and (not account_id or account_id.startswith("zalo_personal:")):
            items, phone_lookup = await _tim_sdt_tren_zalo(items, q, dict(
                channel=channel, bot_id=bot_id, account_id=account_id, q=q, mode=mode, limit=limit,
                status=status, chat_type=chat_type, hesitant=hesitant, **extra))
            _attach_state(items, ctx)
        facets = conversations.dem_bo_loc(hesitant)
        ten = {bid: _ten_bot(bid) for bid in facets["bots"] if bid}
        for it in items:
            it["bot_name"] = ten.get(str(it.get("bot_id") or "")) or _ten_bot(str(it.get("bot_id") or ""))
            it["need_reply"] = conversations.can_tra_loi(it, hesitant)
        return {"ok": True, "items": items, "who_counts": who_counts, "total": total,
                "stats": conversations.thong_ke(bot_id=bot_id, channel=channel, account_id=account_id),
                "facets": facets,
                "bots": [{"id": bid, "name": ten[bid], **facets["bots"][bid]} for bid in ten],
                "tags": conversations.list_tags(),
                "channels": channels.cho_giao_dien(), "phone_lookup": phone_lookup}

    async def _tim_sdt_tren_zalo(items: list, q: str, loc: dict) -> tuple:
        """0.216.0: ô tìm kiếm là một số điện thoại đầy đủ mà chưa khách nào trong hòm thư mang số đó: hỏi Zalo của các
        tài khoản Zalo cá nhân số này là ai, gắn số vào khách đó rồi tìm lại. Trả `(items, phone_lookup)`; `phone_lookup`
        là None khi không cần hỏi (đã có khách mang số này) và cho giao diện biết người mang số chưa có cuộc chat nào."""
        import zalo_phone_lookup
        sdt = conversations.chuan_hoa_sdt(q)
        if any(it.get("customer_phone") == sdt for it in items):
            return items, None
        r = await zalo_phone_lookup.lookup(sdt, account_id=loc.get("account_id") or "")
        if not r["results"]:
            return items, None
        if any(x["uid"] for x in r["results"]):
            items = conversations.danh_sach(**loc)
        for x in r["results"]:
            kenh, _, tk = x["account_id"].partition(":")
            # `has_chat`: có cuộc chat riêng trong kho; `shown`: nó nằm trong danh sách đang hiện (bộ lọc có thể ẩn nó).
            x["has_chat"] = bool(x["uid"]) and conversations.co_tin(kenh, tk, x["uid"])
            x["shown"] = bool(x["uid"]) and any(
                it.get("channel_account_id") == x["account_id"]
                and x["uid"] in (it.get("customer_external_id"), it.get("external_chat_id")) for it in items)
        return items, r

    @router.get("/conversations/insights")
    async def conversations_insights(days: int = 7, date_from: str = Query("", alias="from"),
                                     date_to: str = Query("", alias="to"), account: str = ""):
        """The Stats tab (Chatbot v5): this period against the one of the same length right before it, plus "needs you"
        right now and the bot names. The period is `from`..`to` (days included, the date range picker), or else the
        last `days` (1, 7 or 30) counted from midnight of the server's day. `account` (0.401.0): one inbox account only."""
        now = time.time()
        since, until = _day_range(date_from, date_to)
        if since and until:
            n = max(1, round((until - since) / 86400))
            until = min(until, now)
        else:
            n = days if days in (1, 7, 30) else 7
            lt = time.localtime()
            midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
            since, until = midnight - (n - 1) * 86400, now
        accounts = conversations.stats_accounts()
        account = account if any(a["id"] == account for a in accounts) else ""
        cur = conversations.insights(since, until, account)
        prev = conversations.insights(since - n * 86400, since, account)
        ctx = _StateCtx(_hesitant())
        you = sum(1 for r in conversations.state_rows(hesitant=ctx.hesitant, hidden="exclude", account_ids=[account] if account else None)
                  if ctx.of(r)["who"] == "you")
        names = {bid: _ten_bot(bid) for bid in set(cur["by_bot"]) | set(prev["by_bot"])}
        return {"ok": True, "days": n, "since": since, "until": until, "now": cur, "before": prev, "needs_you": you, "bot_names": names,
                "channels": channels.cho_giao_dien(), "accounts": accounts, "account": account}

    @router.get("/conversations/stats")
    async def conversations_stats(bot_id: str = "", channel: str = "", account_id: str = ""):
        return {"ok": True, "stats": conversations.thong_ke(bot_id=bot_id, channel=channel,
                                                              account_id=account_id)}

    # ---- inbox tags (2026-10-25). Declared before /conversations/{conv_id}, which would otherwise catch "tags".
    _TAG_ERR = {
        "empty": (400, "Tên tag đang trống", "The tag name is empty"),
        "duplicate": (409, "Đã có tag tên này", "A tag with this name already exists"),
        "limit": (400, f"Tối đa {conversations.MAX_INBOX_TAGS} tag", f"At most {conversations.MAX_INBOX_TAGS} tags"),
        "missing": (404, "Không có tag này", "No such tag"),
    }

    def _tag_err(code: str):
        st, vi, en = _TAG_ERR.get(code, _TAG_ERR["missing"])
        return JSONResponse({"ok": False, "code": code, "error": localefmt.chu(vi, en)}, status_code=st)

    @router.get("/conversations/tags")
    async def conversations_tags():
        """The owner's inbox tags with how many conversations carry each, and the colour palette."""
        return {"ok": True, "tags": conversations.list_tags(), "colors": list(conversations.TAG_COLORS)}

    @router.post("/conversations/tags")
    async def conversations_tag_create(name: str = Form(...), color: str = Form("")):
        tag, err = conversations.create_tag(name, color)
        return {"ok": True, "tag": tag, "tags": conversations.list_tags()} if tag else _tag_err(err)

    @router.post("/conversations/tags/{tag_id}")
    async def conversations_tag_update(tag_id: int, name: Optional[str] = Form(None), color: Optional[str] = Form(None)):
        """Rename and/or recolour a tag (fields left out stay as they are)."""
        ok, err = conversations.update_tag(tag_id, name=name, color=color)
        return {"ok": True, "tags": conversations.list_tags()} if ok else _tag_err(err)

    @router.delete("/conversations/tags/{tag_id}")
    async def conversations_tag_delete(tag_id: int):
        """Delete a tag; it comes off every conversation."""
        return {"ok": True, "tags": conversations.list_tags()} if conversations.delete_tag(tag_id) else _tag_err("missing")

    @router.get("/conversations/channels")
    async def conversations_channels():
        """Bí danh của GET /channels/accounts (0.61.0): mọi tài khoản kênh, một khuôn."""
        return {"ok": True, "accounts": channels_routes._tai_khoan_thong_nhat(),
                "channels": channels.cho_giao_dien()}

    @router.post("/conversations/zalo/{conn_id}/watch")
    async def conversations_zalo_watch(conn_id: str, on: str = Form("1")):
        """Bí danh cũ của POST /channels/accounts/{id}/watch cho Zalo cá nhân."""
        m = channels.module("zalo_personal")
        if not m:
            return JSONResponse({"ok": False, "error": localefmt.chu("kênh Zalo cá nhân chưa có trong sổ",
                                                                      "the personal Zalo channel is not in the registry")}, status_code=400)
        r = m.bat(conn_id, str(on).strip().lower() in ("1", "true", "on", "yes"))
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    @router.get("/conversations/{conv_id}")
    async def conversations_detail(conv_id: int):
        d = conversations.chi_tiet(conv_id)
        return {"ok": True, "conversation": d} if d else _404()

    @router.get("/conversations/{conv_id}/messages")
    async def conversations_messages(conv_id: int, limit: int = 100, before: int = 0, after: int = 0):
        """Tin của một hội thoại, cũ trước mới sau.

        Mặc định lấy `limit` tin MỚI NHẤT; `before=<id>` lấy các tin cũ hơn id đó (kéo lên để xem thêm); `after=<id>` (0.65.11) chỉ lấy tin MỚI
        hơn id đó, dành cho nhịp làm mới 5 giây. `has_more` cho biết còn tin cũ hơn tin đầu của phần trả về hay không."""
        d = conversations.chi_tiet(conv_id)
        if not d:
            return _404()
        _attach_state([d], _StateCtx(_hesitant()))
        moi = after > 0
        msgs = conversations.tin_nhan(conv_id, limit=limit, before_id=before, after_id=after)
        d["bot_name"] = _ten_bot(str(d.get("bot_id") or ""))
        bot_id = str(d.get("bot_id") or "")
        # Lý do bot im gắn với tin khách CUỐI của cuộc chat, không phải cuối phần trả về: nhịp chỉ hỏi tin mới có thể trả rỗng, và
        # kéo lên xem tin cũ thì phần trả về không chứa tin cuối.
        cuoi = msgs if (not moi and not before) else conversations.tin_nhan(conv_id, limit=1)
        # `bot_running`: giao diện cần biết bot có đang chạy để bật hay nói lý do tắt nút "Trả lời giúp tin này".
        return {"ok": True, "conversation": d, "messages": msgs, "bot_silence": _bot_silence(d, cuoi),
                "has_more": (False if moi else (bool(msgs) and conversations.co_tin_cu(conv_id, msgs[0]["id"]))),
                "bot_running": bool(bot_id and (_DEPS.bot_status(bot_id) or {}).get("running"))}

    @router.post("/conversations/{conv_id}/read")
    async def conversations_read(conv_id: int):
        return {"ok": True} if conversations.danh_dau_da_doc(conv_id) else _404()

    @router.post("/conversations/{conv_id}/unread")
    async def conversations_unread(conv_id: int):
        """Mark a conversation unread again (row menu). Opening it marks it read, as `/read` always did."""
        return {"ok": True, "conversation": conversations.chi_tiet(conv_id)} if conversations.mark_unread(conv_id) else _404()

    @router.post("/conversations/{conv_id}/hide")
    async def conversations_hide(conv_id: int, hidden: str = Form("1")):
        """Hide (hidden=1) a conversation from the inbox list or bring it back (hidden=0). A new customer message
        unhides it on its own."""
        ok = conversations.set_hidden(conv_id, str(hidden).strip().lower() not in ("0", "false", ""))
        return {"ok": True, "conversation": conversations.chi_tiet(conv_id)} if ok else _404()

    @router.post("/conversations/{conv_id}/pin")
    async def conversations_pin(conv_id: int, pinned: str = Form("1")):
        """Ghim (pinned=1) hoặc bỏ ghim (pinned=0) một cuộc chat lên đầu hòm thư."""
        ok = conversations.dat_ghim(conv_id, str(pinned).strip().lower() not in ("0", "false", ""))
        return {"ok": True, "conversation": conversations.chi_tiet(conv_id)} if ok else _404()

    @router.post("/conversations/{conv_id}/tags")
    async def conversations_set_tag(conv_id: int, tag_id: int = Form(...), on: str = Form("1")):
        """Put a tag on this conversation (on=1) or take it off (on=0). Returns the conversation's tags."""
        tags = conversations.set_conversation_tag(conv_id, tag_id, str(on).strip().lower() not in ("0", "false", ""))
        return {"ok": True, "tags": tags} if tags is not None else _404()

    @router.post("/conversations/{conv_id}/reply")
    async def conversations_reply(conv_id: int, text: str = Form(...)):
        """Chủ trả lời khách ngay từ Hộp thư (Chatbot V2 bản V1.2).

        Gửi qua năng lực `gui` của kênh trong sổ đăng ký: bot Telegram/Zalo gửi bằng token của
        tài khoản, Zalo cá nhân gửi bằng MCP dưới danh tính chủ. Gửi được thì ghi vào kho như
        tin `human`, và nếu cuộc này có bot đang trực ở chế độ AI thì TIẾP QUẢN luôn (chuyển
        `human`): người vừa nhắn tay mà bot chen vào câu sau là khách đọc hai giọng một lúc.
        Trả `tiep_quan: true` để giao diện nói ra điều đó.
        """
        c = conversations.chi_tiet(conv_id)
        if not c:
            return _404()
        txt = str(text or "").strip()
        if not txt:
            return JSONResponse({"ok": False, "error": localefmt.chu("tin rỗng", "empty message")}, status_code=400)
        if len(txt) > conversations.MAX_CHU:
            return JSONResponse({"ok": False, "error": localefmt.chu(f"tin dài quá {conversations.MAX_CHU} ký tự",
                                                                   f"message longer than {conversations.MAX_CHU} characters")}, status_code=400)
        kenh = str(c.get("channel") or "")
        ok, loi = await _gui_tin(c, txt, tieng_vong=True)
        if not ok:
            return JSONResponse({"ok": False, "error": loi or localefmt.chu("không gửi được", "could not send")},
                                status_code=400)
        raw = _tk_goc(c)
        r = conversations.ghi_su_kien({
            "channel": kenh, "account_id": raw, "account_name": c.get("account_name") or "",
            "bot_id": c.get("bot_id") or "",
            "external_chat_id": c.get("external_chat_id"), "chat_type": c.get("chat_type"),
            "chat_title": c.get("title") if c.get("chat_type") == "group" else "",
            "sender_type": "human", "sender_name": "Bạn", "message_type": "text", "text": txt,
            "metadata": {"tu_javis": True},
        })
        tiep_quan = False
        if c.get("bot_id") and str(c.get("mode") or "ai") == "ai":
            conversations.dat_che_do(conv_id, "human")
            tiep_quan = True
        # The owner answered by hand: an A.I. draft still waiting is no longer needed (Chatbot v5).
        conversations.clear_draft(conv_id)
        return {"ok": True, "message_id": r.get("message_id"), "tiep_quan": tiep_quan,
                "conversation": conversations.chi_tiet(conv_id)}

    @router.post("/conversations/{conv_id}/ai-reply")
    async def conversations_ai_reply(conv_id: int, mode: str = Form("send"), instruction: str = Form("")):
        """Chủ nhờ BOT trả lời ngay từ Hộp thư (0.65.5). `mode=send`: bot trả lời tin khách cuối và câu đó được gửi luôn; cuộc chat
        vẫn ở chế độ Tự động. `mode=draft`: bot chỉ soạn, trả chữ về để đổ vào ô nhập, không gửi và không để lại dấu vết.

        Chỉ đúng chế độ mới chạy, và trả `code` để giao diện nói được lý do: `human` (đang tiếp quản), `bot_off` (bot đang tắt),
        `no_bot`, `already_answered` (tin cuối không phải của khách), `busy`, `no_message`, `send_failed`, `engine`.

        `instruction` (Chatbot v5, "A.I. reply"): what the owner typed as an order for the reply. It always means a draft:
        the owner reviews the result before anything is sent."""
        if str(instruction or "").strip():
            mode = "draft"
        if mode not in ("send", "draft"):
            return JSONResponse({"ok": False, "code": "bad_mode", "error": localefmt.chu("mode phải là send hoặc draft",
                                                                                         "mode must be send or draft")}, status_code=400)
        if _DEPS.manual_answer is None:
            return JSONResponse({"ok": False, "code": "unavailable", "error": localefmt.chu("Chưa nối bot vào Hộp thư",
                                                                                            "Bots are not wired to the Inbox yet")}, status_code=503)
        c = conversations.chi_tiet(conv_id)
        if not c:
            return _404()
        bot_id = str(c.get("bot_id") or "")
        if not bot_id:
            return JSONResponse({"ok": False, "code": "no_bot", "error": localefmt.chu("Cuộc chat này không có bot trực",
                                                                                           "No bot is on duty in this chat")}, status_code=400)
        msgs = conversations.tin_nhan(conv_id, limit=30)
        send = mode == "send"
        if send:
            # Tin cuối phải là của khách: bot đã đáp (hay bạn đã đáp) rồi thì "trả lời giúp" là nói lần hai.
            if not msgs or msgs[-1].get("sender_type") != "customer":
                return JSONResponse({"ok": False, "code": "already_answered", "error": localefmt.chu("Tin cuối không phải của khách",
                                                                                                         "The last message is not from the customer")}, status_code=409)
            if str(c.get("mode") or "ai") != "ai":
                return JSONResponse({"ok": False, "code": "human", "error": localefmt.chu("Bạn đang tiếp quản cuộc chat này",
                                                                                              "You have taken over this chat")}, status_code=409)
            if not (_DEPS.bot_status(bot_id) or {}).get("running"):
                return JSONResponse({"ok": False, "code": "bot_off", "error": localefmt.chu("Bot đang tắt", "The bot is off")}, status_code=409)
        lenh = str(instruction or "").strip()
        r = await (_DEPS.manual_answer(c, msgs, not send, lenh) if lenh else _DEPS.manual_answer(c, msgs, not send))
        if not r.get("ok"):
            status = 409 if r.get("code") == "busy" else 400 if r.get("code") in ("no_bot", "no_message") else 502
            return JSONResponse({"ok": False, "code": r.get("code") or "engine", "error": r.get("error") or localefmt.chu("Bot không soạn được", "The bot could not draft a reply")},
                                status_code=status)
        if r.get("silent"):
            return {"ok": True, "silent": True, "text": ""}
        if not send:
            # Kept as the chat's waiting draft (Chatbot v5), so it survives a reload and is sent or dropped through
            # /draft like a draft the bot wrote in "drafts" mode.
            conversations.save_draft(conv_id, r["text"], conversations.last_customer_message_id(conv_id), lenh)
            return {"ok": True, "silent": False, "text": r["text"], "draft": True,
                    "conversation": _detail_with_state(conv_id)}
        ok, loi = await _gui_tin(c, r["text"], tieng_vong=True, reply_to=msgs[-1])
        if not ok:
            # Không gửi được thì trả chữ đã soạn để chủ dán vào ô nhập gửi tay, khỏi mất công soạn lại.
            return JSONResponse({"ok": False, "code": "send_failed", "error": loi or localefmt.chu("không gửi được", "could not send"), "text": r["text"]},
                                status_code=400)
        done = _DEPS.manual_done(c, msgs, r["text"], r["meta"]) if _DEPS.manual_done else {}
        return {"ok": True, "silent": False, "text": r["text"], "taught": bool((done or {}).get("taught")),
                "conversation": conversations.chi_tiet(conv_id)}

    def _detail_with_state(conv_id: int) -> Optional[dict]:
        """`chi_tiet` plus the "who is handling it" fields (Chatbot v5)."""
        d = conversations.chi_tiet(conv_id)
        if d:
            _attach_state([d], _StateCtx(_hesitant()))
        return d

    @router.post("/conversations/{conv_id}/mode")
    async def conversations_mode(conv_id: int, mode: str = Form(...)):
        """ai | human | waiting | closed | draft. `human` = người thật tiếp quản, bot im ở cuộc chat đó. `draft` (Chatbot v5)
        = the bot writes its reply and waits for the owner. A draft still waiting stays when the mode changes (the owner
        may still send it, and Undo puts the old mode back with its draft); /reply and /draft clear it."""
        ok, err = conversations.dat_che_do(conv_id, mode)
        if not ok:
            # Chế độ hợp lệ mà vẫn hỏng thì chỉ có thể là không có hội thoại đó. Không dò chữ
            # của câu lỗi: câu đó theo ngôn ngữ giao diện.
            hop_le = str(mode or "").strip().lower() in conversations.CHE_DO
            return JSONResponse({"ok": False, "error": err},
                                status_code=404 if hop_le else 400)
        return {"ok": True, "conversation": _detail_with_state(conv_id)}

    @router.post("/conversations/{conv_id}/ai")
    async def conversations_ai(conv_id: int, on: str = Form("1")):
        """Let the bot on duty answer in this chat (on=1) or switch it off here (on=0), Chatbot v5. The bot's audience
        stays as it is: see `chatbot_store.allow_patch`. Allowing also settles the approval queue entry."""
        c = conversations.chi_tiet(conv_id)
        if not c:
            return _404()
        bot_id = str(c.get("bot_id") or "")
        bot = chatbot_store.get_bot(bot_id) if bot_id else None
        if not bot:
            return JSONResponse({"ok": False, "code": "no_bot", "error": localefmt.chu(
                "Cuộc chat này chưa có bot nào trực", "No bot is on duty in this chat")}, status_code=400)
        bat = str(on).strip().lower() not in ("0", "false", "")
        chat_id = str(c.get("external_chat_id") or "")
        ctype = str(c.get("chat_type") or "private")
        patch = chatbot_store.allow_patch(bot, ctype, chat_id, bat)
        ok, err = chatbot_store.update_bot(bot_id, patch)
        if not ok:
            return JSONResponse({"ok": False, "error": err}, status_code=400)
        # The bot's lists only keep ids that look like a real platform chat id; one they drop would leave the switch
        # where it was while the screen says "done". Say it instead.
        if chatbot_store.chat_allowed(chatbot_store.get_bot(bot_id), ctype, chat_id, inbox_state.raw_account(c)) != bat:
            return JSONResponse({"ok": False, "code": "chat_id", "error": localefmt.chu(
                "Không đổi được A.I. riêng cho cuộc chat này (mã cuộc chat không hợp lệ). Đổi ở cài đặt bot.",
                "Could not change the A.I. for this chat alone (its chat id is not valid). Change it in the bot settings.")},
                status_code=400)
        if _DEPS.drop_pending:
            try:
                _DEPS.drop_pending(bot_id, chat_id)
            except Exception:      # noqa: BLE001
                pass
        return {"ok": True, "conversation": _detail_with_state(conv_id)}

    @router.post("/conversations/{conv_id}/note")
    async def conversations_note(conv_id: int, note: str = Form("")):
        """The owner's note about the customer of this chat (Chatbot v5 Info panel; only the owner sees it)."""
        if not conversations.set_note(conv_id, note):
            return _404()
        return {"ok": True, "conversation": _detail_with_state(conv_id)}

    @router.post("/conversations/{conv_id}/draft")
    async def conversations_draft(conv_id: int, action: str = Form(...), text: str = Form("")):
        """The A.I.'s waiting draft (Chatbot v5): `action=send` sends `text` (the owner may have edited it) as the bot's
        reply and records it in the inbox as the bot's words; `action=discard` drops it. Both clear the stored draft."""
        c = conversations.chi_tiet(conv_id)
        if not c:
            return _404()
        if action == "discard":
            conversations.clear_draft(conv_id)
            return {"ok": True, "conversation": _detail_with_state(conv_id)}
        if action != "send":
            return JSONResponse({"ok": False, "error": localefmt.chu("action phải là send hoặc discard",
                                                                     "action must be send or discard")}, status_code=400)
        txt = str(text or "").strip()
        if not txt:
            return JSONResponse({"ok": False, "error": localefmt.chu("tin rỗng", "empty message")}, status_code=400)
        if len(txt) > conversations.MAX_CHU:
            return JSONResponse({"ok": False, "error": localefmt.chu(f"tin dài quá {conversations.MAX_CHU} ký tự",
                                                                   f"message longer than {conversations.MAX_CHU} characters")}, status_code=400)
        msgs = conversations.tin_nhan(conv_id, limit=30)
        last = next((m for m in reversed(msgs) if m.get("sender_type") == "customer"), None)
        ok, loi = await _gui_tin(c, txt, tieng_vong=True, reply_to=last)
        if not ok:
            return JSONResponse({"ok": False, "code": "send_failed", "error": loi or localefmt.chu("không gửi được", "could not send")},
                                status_code=400)
        recorded = False
        if c.get("bot_id") and _DEPS.manual_done and _DEPS.manual_meta:
            try:
                _DEPS.manual_done(c, msgs, txt, _DEPS.manual_meta(c, last or {}))
                recorded = True
            except Exception:      # noqa: BLE001 - the message went out; a failed record must not report a failed send
                recorded = False
        if not recorded:
            conversations.ghi_su_kien({
                "channel": str(c.get("channel") or ""), "account_id": _tk_goc(c), "account_name": c.get("account_name") or "",
                "bot_id": c.get("bot_id") or "", "external_chat_id": c.get("external_chat_id"), "chat_type": c.get("chat_type"),
                "chat_title": c.get("title") if c.get("chat_type") == "group" else "",
                "sender_type": "ai", "sender_name": "Bot", "message_type": "text", "text": txt,
                "metadata": {"tu_javis": True, "draft": True},
            })
        conversations.clear_draft(conv_id)
        return {"ok": True, "conversation": _detail_with_state(conv_id)}

    def _goc_media(c: dict) -> list:
        """Các thư mục được phép phát media của hội thoại này: inbox/ và attachments/ trong brain của bot trực nó, và
        brain gắn với tài khoản kênh."""
        if not _DEPS or not _DEPS.brain_root:
            return []
        brains = []
        bot = chatbot_store.get_bot(str(c.get("bot_id") or "")) if c.get("bot_id") else None
        if bot and bot.get("brain"):
            brains.append(str(bot["brain"]))
        for key in (str(c.get("channel_account_id") or ""), _tk_goc(c)):
            try:
                a = channel_accounts.get_account(key) if key else None
            except Exception:      # noqa: BLE001 - a broken account record must not break the inbox
                a = None
            if a and a.get("brain"):
                brains.append(str(a["brain"]))
        goc = []
        for b in dict.fromkeys(brains):
            try:
                root = Path(_DEPS.brain_root(b)).resolve()
            except Exception:      # noqa: BLE001
                continue
            goc += [root / d for d in _THU_MUC_MEDIA]
        return goc

    @router.get("/conversations/{conv_id}/media")
    async def conversations_media(conv_id: int, p: str = Query(...), dl: int = Query(0)):
        """Ảnh hay file KHÁCH gửi mà kênh đã tải về máy (0.171.0): Hộp thư hiện ảnh ngay trong cuộc chat, file thì tải về.

        Đường dẫn nằm sẵn trong tin ("[... đã tải về: <path>]"). Chỉ phát file nằm thật trong inbox/ hoặc attachments/ của brain
        của chính hội thoại này (resolve trước khi so, nên `..` hay symlink không leo ra được). Cần đăng nhập như mọi route khác."""
        c = conversations.chi_tiet(conv_id)
        if not c:
            return _404()
        try:
            f = Path(str(p or "")).expanduser().resolve()
        except (OSError, ValueError):
            return _404(localefmt.chu("không có file đó", "no such file"))
        if not f.is_file() or not any(g == f.parent or g in f.parents for g in _goc_media(c)):
            return _404(localefmt.chu("không có file đó", "no such file"))
        if dl or f.suffix.lower() not in _DUOI_XEM_THANG:
            return FileResponse(str(f), filename=f.name)
        resp = FileResponse(str(f), media_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        resp.headers["Content-Disposition"] = "inline"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    app.include_router(router)
