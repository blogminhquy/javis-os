"""Send a personal-Zalo message on behalf of a background job, the same way the bot sends its replies (0.215.0).

Why this exists. Script jobs (`Javis/scripts/*.py`, reminders in `script` mode) used to send through the Zalo CLI directly
(`zalo_cli.run_cli(["msg", "send"])`). They run in a child process, so they cannot reach the echo memory of the read loop
(`zalo_personal_channel.ghi_da_gui` / `ghi_da_gui_anh`). Every message they sent came back in the live feed as the account's
own message with nothing to match it against, so the read loop took it for the owner typing by hand: the Inbox logged it as
"human" and the bot went quiet in that chat for `TAY_IM` seconds. A parent answering a weekly check-in within ten minutes got
no reply (seen on 18/10/2026).

This module is the server-side path for those jobs, exposed as the localhost-only endpoint `POST /zalo/job-send`:
  - it remembers the echo BEFORE sending, exactly like `channels.zalo_personal.Transport._gui` / `_gui_anh`;
  - it sends with the same functions the bot uses (`channels.zalo_personal.gui` / `gui_anh`);
  - it logs the message in the Inbox as the bot's own (`sender_type="ai"`), so the bot sees it as context on the next turn.

It sends only to a thread id the caller names, on a Zalo account that is connected and enabled; it never picks an account
when several are connected and none was named.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import localefmt

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TEXT = 4000
LOOPBACK = ("127.0.0.1", "::1")


def is_loopback(host: str) -> bool:
    return str(host or "") in LOOPBACK


def _accounts() -> List[dict]:
    import zalo_personal_channel as zc
    try:
        return [c for c in zc._ket_noi() if c.get("id")]
    except Exception as e:  # noqa: BLE001 - a broken store must not crash the request
        print(f"[zalo-job-send] cannot list Zalo accounts: {type(e).__name__}: {e}", file=sys.stderr)
        return []


def pick_account(account: str = "") -> Tuple[Optional[dict], str]:
    """The Zalo account to send from. Named -> that one; none named -> the only one; several -> refuse (sending under the
    wrong identity is worse than asking again)."""
    conns = _accounts()
    want = str(account or "").strip()
    if want:
        hit = [c for c in conns if c.get("id") == want or str(c.get("id")).endswith(":" + want)]
        if hit:
            return hit[0], ""
        return None, localefmt.chu(f"không có tài khoản Zalo đang bật id '{want}'",
                                   f"no enabled Zalo account with id '{want}'")
    if len(conns) == 1:
        return conns[0], ""
    if not conns:
        return None, localefmt.chu("chưa có tài khoản Zalo cá nhân nào đang bật",
                                   "no personal Zalo account is connected and enabled")
    ids = ", ".join(str(c.get("id")) for c in conns)
    return None, localefmt.chu(f"có {len(conns)} tài khoản Zalo, hãy nêu 'account' ({ids})",
                               f"{len(conns)} Zalo accounts are connected, pass 'account' ({ids})")


def bot_for_account(conn_id: str) -> Dict[str, Any]:
    """The dedicated bot on duty for this Zalo account ({} when none), so the Inbox files the message under it."""
    try:
        import chatbot_store
        for b in chatbot_store.list_bots():
            for a in b.get("accounts") or []:
                aid = str((a.get("id") if isinstance(a, dict) else a) or "")
                if aid and (aid == conn_id or aid.endswith(":" + conn_id)):
                    return b
    except Exception as e:  # noqa: BLE001
        print(f"[zalo-job-send] cannot read bots: {type(e).__name__}: {e}", file=sys.stderr)
    return {}


def check_images(paths: Any) -> Tuple[List[str], str]:
    """Absolute paths of existing image files, at most MAX_IMAGES. Returns (paths, error)."""
    if not paths:
        return [], ""
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list):
        return [], localefmt.chu("'images' phải là danh sách đường dẫn", "'images' must be a list of paths")
    out = []
    for raw in paths[:MAX_IMAGES + 1]:
        p = str(raw or "").strip()
        if not p:
            continue
        if not os.path.isabs(p):
            return [], localefmt.chu(f"ảnh phải là đường dẫn tuyệt đối: {p}", f"image path must be absolute: {p}")
        f = Path(p)
        if f.suffix.lower() not in IMAGE_EXTS or not f.is_file():
            return [], localefmt.chu(f"không thấy ảnh hợp lệ: {p}", f"not an existing image file: {p}")
        if f.stat().st_size > MAX_IMAGE_BYTES:
            return [], localefmt.chu(f"ảnh quá 10 MB: {p}", f"image larger than 10 MB: {p}")
        out.append(str(f))
    if len(out) > MAX_IMAGES:
        return [], localefmt.chu(f"tối đa {MAX_IMAGES} ảnh mỗi lần", f"at most {MAX_IMAGES} images per call")
    return out, ""


def log_inbox(conn_id: str, bot: Dict[str, Any], thread: str, chat_type: str, text: str, images: List[str],
              label: str) -> None:
    """Log what the job sent as the bot's own message. Never raises: the message already went out."""
    try:
        import conversations
        md: Dict[str, Any] = {"source": "job", "tu_javis": True}
        if label:
            md["label"] = label[:120]
        if images:
            md["files"] = [p[:300] for p in images]
        body = text or localefmt.chu(f"({len(images)} ảnh)", f"({len(images)} image(s))")
        conversations.ghi_su_kien({
            "channel": "zalo_personal", "account_id": conn_id, "account_name": bot.get("name") or "",
            "bot_id": bot.get("id") or "", "external_chat_id": thread, "chat_type": chat_type,
            "chat_title": "", "sender_type": "ai", "sender_name": bot.get("name") or "Javis",
            "message_type": "text", "text": body, "metadata": md,
        })
    except Exception as e:  # noqa: BLE001
        print(f"[zalo-job-send] inbox log failed: {type(e).__name__}: {e}", file=sys.stderr)


async def send(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Body: {"thread": "<thread id>", "chat_type": "private"|"group", "text": "...", "images": ["/abs/x.png"],
    "account": "<zalo account id, optional>", "label": "<job name, optional>"}. Images go first, then the text.
    Returns {"ok", "error", "sent": {"images": n, "text": bool}}."""
    p = payload or {}
    thread = str(p.get("thread") or p.get("threadId") or "").strip()
    chat_type = "group" if str(p.get("chat_type") or "").lower() in ("group", "1") else "private"
    text = str(p.get("text") or "").strip()
    label = str(p.get("label") or "").strip()
    sent = {"images": 0, "text": False}
    if not thread:
        return {"ok": False, "error": localefmt.chu("thiếu 'thread'", "missing 'thread'"), "sent": sent}
    if len(text) > MAX_TEXT:
        return {"ok": False, "error": localefmt.chu(f"tin dài quá {MAX_TEXT} ký tự", f"text longer than {MAX_TEXT}"),
                "sent": sent}
    images, err = check_images(p.get("images"))
    if err:
        return {"ok": False, "error": err, "sent": sent}
    if not text and not images:
        return {"ok": False, "error": localefmt.chu("không có chữ hay ảnh để gửi", "nothing to send"), "sent": sent}
    conn, err = pick_account(str(p.get("account") or ""))
    if not conn:
        return {"ok": False, "error": err, "sent": sent}

    import zalo_personal_channel as zc
    from channels import zalo_personal as zp
    cid = str(conn.get("id"))
    bot = bot_for_account(cid)
    if images:
        zc.ghi_da_gui_anh(cid, thread, len(images))      # remember BEFORE sending, like Transport._gui_anh
        ok, err = await zp.gui_anh({"id": cid}, thread, images, chat_type)
        if not ok:
            return {"ok": False, "error": localefmt.chu(f"gửi ảnh lỗi: {err}", f"image send failed: {err}"),
                    "sent": sent}
        sent["images"] = len(images)
    if text:
        zc.ghi_da_gui(cid, thread, text)                  # remember BEFORE sending, like Transport._gui
        ok, err = await zp.gui({"id": cid}, thread, text, chat_type)
        if not ok:
            if images:   # the images did go out: keep them in the Inbox
                log_inbox(cid, bot, thread, chat_type, "", images, label)
            return {"ok": False, "error": localefmt.chu(f"gửi chữ lỗi: {err}", f"text send failed: {err}"),
                    "sent": sent}
        sent["text"] = True
    log_inbox(cid, bot, thread, chat_type, text, images, label)
    return {"ok": True, "error": "", "sent": sent}
