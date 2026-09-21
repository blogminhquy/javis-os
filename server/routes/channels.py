"""Kênh và tài khoản kênh của Hộp thư hội thoại - một API cho MỌI kênh (0.61.0).

Trước đây trang Hội thoại hỏi `/conversations/channels` và nhận hai danh sách khác khuôn (bot
một kiểu, Zalo cá nhân một kiểu); trang Chatbot hỏi `/chatbots` để biết kênh nào có. Nay:

    GET  /channels                      các LOẠI kênh Javis hỗ trợ (từ sổ đăng ký) + năng lực
    GET  /channels/accounts             MỌI tài khoản kênh, MỘT khuôn, bất kể kênh
    POST /channels/verify-token         hỏi nền tảng token này là bot nào, chặn trùng
    POST /channels/accounts             thêm tài khoản token (kênh kind=bot)
    POST /channels/accounts/{id}/update đổi nhãn / token
    POST /channels/accounts/{id}/watch  bật/tắt ghi vào hộp thư (kênh kind=account)
    POST /channels/accounts/{id}/delete xoá tài khoản token (từ chối khi còn bot trực)

Id tài khoản trong API này là id THÔ (`acc_...`, `bot_...` di trú, hoặc id kết nối Zalo). Kho
hội thoại khoá theo `f"{kenh}:{id thô}"`; mỗi bản ghi trả về mang cả hai (`id` và `account_key`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

import channel_accounts
import channels
import chatbot_store
import conversations

router = APIRouter()


@dataclass
class ChannelsDeps:
    bot_status: Callable[[str], dict]      # chatbot_runtime.status
    # Token bot CHỦ (Telegram ở trang Kênh) - để từ chối dán nhầm nó làm bot chuyên trách.
    main_bot_token: Callable[[], str]


_DEPS: "ChannelsDeps" = None   # type: ignore


def _400(msg: str, **them):
    return JSONResponse({"ok": False, "error": msg, **them}, status_code=400)


def _404(msg: str = channel_accounts.LOI_KHONG_CO):
    return JSONResponse({"ok": False, "error": msg}, status_code=404)


def _bat(v) -> bool:
    return str(v or "").strip().lower() not in ("", "0", "false", "off", "no")


def _tai_khoan_thong_nhat() -> list:
    """Mọi tài khoản kênh về MỘT khuôn. Không nhánh theo tên kênh: mỗi loại kênh (kind) cho một
    cách LIỆT KÊ, còn hình dạng bản ghi thì như nhau."""
    da_co = {a["id"]: a for a in conversations.tai_khoan()}
    bots = chatbot_store.list_bots()
    bot_cua = {}
    for b in bots:
        for aid in chatbot_store.account_ids_of(b):
            bot_cua[aid] = b
    out = []
    for s in channels.danh_sach():
        m = channels.module(s.id)
        nl = dict(s.nang_luc)
        if s.kind == "bot":
            for a in channel_accounts.list_accounts(s.id):
                b = bot_cua.get(a["id"])
                st = {}
                if b:
                    try:
                        st = _DEPS.bot_status(b["id"]) if _DEPS else {}
                    except Exception:
                        st = {}
                    st = next((x for x in (st.get("accounts") or []) if x.get("account_id") == a["id"]), st)
                key = f"{s.id}:{a['id']}"
                tk = da_co.get(key) or {}
                out.append({
                    "id": a["id"], "account_key": key, "kind": "bot",
                    "channel": s.id, "channel_label": s.nhan, "logo": s.logo, "mau": s.mau,
                    "label": a.get("label") or a.get("external_id") or s.nhan,
                    "external_id": a.get("external_id") or "",
                    "tien_to_ten": s.tien_to_ten,
                    "token_set": bool(a.get("token_set")),
                    "meta": a.get("meta") or {},
                    # Bot trực + trạng thái sống của poller trên ĐÚNG tài khoản này.
                    "bot_id": (b or {}).get("id") or "", "bot_name": (b or {}).get("name") or "",
                    "bot_icon": (b or {}).get("icon") or "", "bot_enabled": bool((b or {}).get("enabled")),
                    "state": (st or {}).get("state") or ("off" if b else "chua_gan"),
                    "loi": (st or {}).get("last_error") or "",
                    "lan_cuoi": (st or {}).get("last_at") or 0,
                    # Bot ghi vào hộp thư khi đang bật: không có công tắc riêng.
                    "watch": None, "ghi": bool((b or {}).get("enabled")),
                    "so_hoi_thoai": int(tk.get("so_hoi_thoai") or 0),
                    "chua_doc": int(tk.get("chua_doc") or 0),
                    "nang_luc": nl, "xoa_duoc": not b, "sua_duoc": True,
                })
        elif s.kind == "account" and m and callable(getattr(m, "tai_khoan", None)):
            for a in m.tai_khoan():
                key = f"{s.id}:{a['id']}"
                tk = da_co.get(key) or {}
                theo_doi = bool(a.get("theo_doi"))
                out.append({
                    "id": a["id"], "account_key": key, "kind": "account",
                    "channel": s.id, "channel_label": s.nhan, "logo": s.logo, "mau": s.mau,
                    "label": a.get("label") or s.nhan, "external_id": "", "tien_to_ten": "",
                    "token_set": True, "meta": {},
                    "bot_id": "", "bot_name": "", "bot_icon": "", "bot_enabled": False,
                    "state": ("error" if a.get("loi") else "running" if theo_doi else "off"),
                    "loi": a.get("loi") or "", "lan_cuoi": a.get("lan_cuoi") or 0,
                    "watch": theo_doi, "ghi": theo_doi,
                    "so_hoi_thoai": int(tk.get("so_hoi_thoai") or 0),
                    "chua_doc": int(tk.get("chua_doc") or 0),
                    "nang_luc": nl, "xoa_duoc": False, "sua_duoc": False,
                })
        # kind == "webhook": chưa có kênh nào; khi có, module tự liệt kê qua `tai_khoan()`.
    return out


def register(app, deps: ChannelsDeps):
    global _DEPS
    _DEPS = deps

    @router.get("/channels")
    async def channels_list():
        """Các loại kênh Javis hỗ trợ, kèm năng lực và cách nối. Giao diện vẽ từ đây."""
        return {"ok": True, "channels": channels.cho_giao_dien()}

    @router.get("/channels/accounts")
    async def channels_accounts(channel: str = ""):
        ds = _tai_khoan_thong_nhat()
        k = str(channel or "").strip().lower()
        if k:
            ds = [a for a in ds if a["channel"] == k]
        return {"ok": True, "accounts": ds, "channels": channels.cho_giao_dien()}

    @router.post("/channels/verify-token")
    async def channels_verify_token(channel: str = Form(...), token: str = Form(...),
                                    account_id: str = Form(""), bot_id: str = Form("")):
        """Hỏi nền tảng token này là bot nào (getMe) và chặn trùng, theo module của kênh."""
        return await verify_token(channel, token, account_id=account_id, bot_id=bot_id)

    @router.post("/channels/accounts")
    async def channels_account_create(channel: str = Form(...), token: str = Form(...),
                                      label: str = Form(""), bot_username: str = Form("")):
        """Thêm tài khoản token. Chưa kiểm (không có bot_username) thì kiểm luôn ở đây."""
        ext = str(bot_username or "").strip()
        meta = {}
        if not ext:
            r = await verify_token(channel, token)
            if isinstance(r, JSONResponse) or not r.get("ok"):
                return r if isinstance(r, JSONResponse) else _400(r.get("error") or "Token không hợp lệ")
            ext = r.get("username") or ""
            meta = {k: r[k] for k in ("vao_duoc_nhom", "account_type", "bot_name") if k in r}
        aid, loi = channel_accounts.create_account({
            "channel": channel, "token": token, "label": label, "external_id": ext, "meta": meta})
        if loi:
            return _400(loi)
        return {"ok": True, "id": aid, "account": channel_accounts.get_account(aid)}

    @router.post("/channels/accounts/{account_id}/update")
    async def channels_account_update(account_id: str, label: str = Form(""), token: str = Form(""),
                                      bot_username: str = Form("")):
        patch = {}
        if label.strip():
            patch["label"] = label
        if token.strip():
            patch["token"] = token
            if bot_username.strip():
                patch["external_id"] = bot_username
        ok, loi = channel_accounts.update_account(account_id, patch)
        if not ok:
            return _404(loi) if loi == channel_accounts.LOI_KHONG_CO else _400(loi)
        # Token đổi thì poller đang chạy phải khởi động lại mới ăn.
        if token.strip():
            for b in chatbot_store.bots_using_account(account_id):
                if b.get("enabled") and _DEPS and getattr(_DEPS, "restart_bot", None):
                    _DEPS.restart_bot(b["id"])
        return {"ok": True, "account": channel_accounts.get_account(account_id)}

    @router.post("/channels/accounts/{account_id}/watch")
    async def channels_account_watch(account_id: str, on: str = Form("1"), channel: str = Form("")):
        """Bật/tắt ghi vào hộp thư cho tài khoản kênh kind=account. Kênh bot không có công tắc
        này (bot ghi khi đang bật) và trả 400 nói rõ."""
        k = str(channel or "").strip().lower()
        ung = []
        for s in channels.danh_sach():
            if k and s.id != k:
                continue
            m = channels.module(s.id)
            if s.kind == "account" and m and callable(getattr(m, "bat", None)):
                ung.append((s, m))
        for s, m in ung:
            r = m.bat(account_id, _bat(on))
            if r.get("ok"):
                return r
        if channel_accounts.get_account(account_id):
            return _400("Tài khoản bot ghi vào hộp thư khi bot đang bật; không có công tắc riêng.")
        return _404("không có tài khoản kênh nào id đó (hoặc đang tắt ở trang Kết nối)")

    @router.post("/channels/accounts/{account_id}/delete")
    async def channels_account_delete(account_id: str):
        dang = chatbot_store.bots_using_account(account_id)
        if dang:
            return _400(f"Tài khoản đang do bot \"{dang[0].get('name')}\" trực. Gỡ khỏi bot trước "
                        "(sửa bot, bỏ chọn tài khoản này) rồi mới xoá được.")
        ok, loi = channel_accounts.delete_account(account_id)
        return {"ok": True} if ok else _404(loi)

    app.include_router(router)


async def verify_token(channel: str, token: str, account_id: str = "", bot_id: str = ""):
    """Dùng chung cho /channels/verify-token và /chatbots/verify-token (đường cũ)."""
    tok = (token or "").strip()
    if not tok:
        return _400("Thiếu token")
    kenh = str(channel or "").strip().lower() or chatbot_store.KENH_DEFAULT
    s = channels.spec(kenh)
    m = channels.module(kenh)
    if not s or s.kind != "bot" or not m or not callable(getattr(m, "verify_token", None)):
        return _400(f"Kênh '{kenh}' không nhận token bot. Kênh có: " + ", ".join(channels.bot_ids()))
    if kenh == "telegram" and _DEPS and _DEPS.main_bot_token() and _DEPS.main_bot_token() == tok:
        return {"ok": False, "error": "Đây là token bot chính của bạn. Bot chuyên trách phải "
                                      "dùng một bot Telegram RIÊNG (tạo thêm ở BotFather)."}
    r = await m.verify_token(tok)
    if not r.get("ok"):
        return {"ok": False, "error": r.get("error") or f"Token không hợp lệ ({s.nhan} từ chối)."}
    username = r.get("username") or ""
    # Trùng: tài khoản nào đã giữ đúng con bot này (theo kênh). Sửa chính nó thì bỏ qua.
    loai_tru = account_id
    if not loai_tru and bot_id:
        ids = chatbot_store.account_ids_of(chatbot_store.get_bot(bot_id) or {})
        loai_tru = next((a for a in ids if (channel_accounts.get_account(a) or {}).get("channel") == kenh), "")
    trung = channel_accounts.owner_of(username, kenh, exclude_id=loai_tru)
    if trung:
        bots = chatbot_store.bots_using_account(trung["id"])
        if bots:
            return {"ok": False, "error": f"Bot {s.nhan} \"{username}\" đã được bot "
                                          f"\"{bots[0]['name']}\" dùng rồi. Mỗi bot phải một token riêng."}
        return {"ok": False, "error": f"Bot {s.nhan} \"{username}\" đã là tài khoản "
                                      f"\"{trung.get('label')}\" ở tab Kênh. Chọn tài khoản đó thay vì dán lại token.",
                "account_id": trung["id"]}
    ra = {"ok": True, "username": username, "bot_name": r.get("bot_name") or "", "channel": kenh}
    for k in ("vao_duoc_nhom", "account_type"):
        if k in r:
            ra[k] = r[k]
    return ra
