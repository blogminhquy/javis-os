"""Adapter kênh Zalo CÁ NHÂN cho Hộp thư hội thoại: đọc tin mới từ MCP `javis-zalo` rồi
đổ vào kho `conversations`.

Ở Việt Nam khách nhắn qua Zalo cá nhân nhiều hơn mọi kênh khác, và không phải ai bán hàng cũng
có Zalo OA. Nên tài khoản Zalo đã quét QR ở trang Kết nối phải là một KÊNH của Hộp thư, không
phải một tool mà chỉ khi chủ hỏi Javis mới đọc.

Cách làm: vòng lặp nền, mỗi `NHIP` giây gọi `zalo_get_messages` với cursor lần trước, chuẩn hoá
từng tin về sự kiện chung rồi `conversations.ghi_su_kien`. Cursor lưu ở `sync_state` của kho,
nên khởi động lại server không đọc trùng (và có trùng thì kho tự chặn theo id tin).

Ba quyết định đáng ghi lại:

  1. **Chỉ ghi khi chủ BẬT cho từng tài khoản** (trang Hộp thư, mục Kênh). Vòng lặp này giữ
     tiến trình MCP sống liên tục (mỗi lần gọi là một lần chạm phiên), tức tài khoản Zalo đăng
     nhập 24/7 qua API không chính thức. Đó là lựa chọn của chủ tài khoản, không phải của Javis.
  2. **Không gọi `zalo_mark_read`.** Cursor của kho là cursor của kho; bộ đệm của MCP để nguyên
     cho chủ hỏi Javis "có tin Zalo mới không" như trước. Tool này là tool ĐỌC, không đụng quyền.
  3. **Không đồng bộ lịch sử cũ.** Lần đầu bật chỉ lấy tin từ lúc bật trở đi (bộ đệm MCP vốn
     chỉ giữ tin từ khi tiến trình chạy), đúng luật của kho: lưu từ lúc kênh được nối.

Gọi MCP đi THẲNG qua `mcp_client.pool` (không qua hub `_guard`): hub bọc quyền và audit cho
model gọi; ở đây là vòng lặp hệ thống, tool đọc, và mỗi 20 giây một dòng audit chỉ là rác.

Bot tự trả lời (0.64.80): tài khoản này gắn được Bot chuyên trách như Telegram hay Zalo Bot.
Chủ quyết định 29/09/2026: bot TỰ TRẢ LỜI và TỰ QUYẾT có nên trả lời không, không cần công tắc
từng người, vì nick này chủ tự quản lý và đã có Hộp thư để giám sát. Đây là chỗ đảo lại quyết
định bỏ tự trả lời Zalo hồi 21/07 (bản khi đó dựa trên listener luật, nay là bot chuyên trách
có Agent, mức quyền, giới hạn tần suất và Hộp thư). Xem "Bot trả lời" ở cuối file: chỉ trả lời
tin dạng chữ, bỏ tin cũ, im khi chủ đang tự nhắn. Từ 0.64.82 bot còn trả lời trong nhóm đã cho
phép (tag/reply, hoặc chế độ Tự đánh giá), xem `channels.zalo_personal.Transport`.

Chờ khách nhắn xong (0.128.0): tin khách ở chat RIÊNG không giao ngay mà gom theo cuộc chat, đợi
khách im `CHO_KHACH_IM` giây rồi mới giao MỘT lượt gộp, xem "Chờ khách nhắn xong" ở cuối file.

Tin file giữ link tải trong `metadata.attachment`; bot chỉ tải về SAU các rào quyền, xem
`channels.zalo_personal.Transport.xu_ly`. Tiếng và sticker vẫn không tải.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from typing import Any, Dict, List, Optional

import config as cfgmod
import localefmt
import conversations

CONNECTOR_ID = "zalo"
KENH = "zalo_personal"
NHIP = 20               # giây giữa hai lần đọc
NHIP_NHANH = 2          # giây giữa hai lần đọc khi tài khoản có chat riêng vừa có tin khách (xem `_nhip_cua`)
NONG_GIAY = 60          # tin khách chat riêng mới hơn chừng này giây thì tài khoản còn đọc theo NHIP_NHANH
NHIP_LOI = 90           # nghỉ dài hơn khi một tài khoản vừa lỗi (MCP chết, chưa đăng nhập)
LIMIT = 100             # tin mỗi lô đọc (MCP cho phép 1..100)
MAX_TRANG = 5           # số lô tối đa đọc liên tiếp trong MỘT lượt khi bộ đệm còn tin (hasMore)
TEN_TTL = 300           # giây giữ bảng tên thread (zalo_list_threads) trước khi hỏi lại
THU_LAI_TEN_GIAY = 15     # giây tối thiểu giữa hai lần làm mới CƯỠNG BỨC bảng (cuộc chat lạ), chống dồn dập
THU_TEN_LAI = 600       # giây nhớ "đã làm mới bảng vì cuộc chat này mà vẫn không thấy tên", khỏi hỏi lại mỗi nhịp
MAX_TEN = 2000

_task: Optional[asyncio.Task] = None
_stop = False
# conn_id -> {"lan_cuoi": ts, "loi": str, "so_tin": int, "ten": {threadId: {...}}, "ten_ts": ts,
#             "nghi_toi": ts}
_TT: Dict[str, dict] = {}


# ============================================================
# Cấu hình: chủ bật/tắt cho TỪNG tài khoản
# ============================================================
def _cau_hinh() -> dict:
    cfg = cfgmod.read_settings()
    ht = cfg.get("conversations") or {}
    zp = ht.get("zalo_personal") or {}
    return zp if isinstance(zp, dict) else {}


def dang_bat(conn_id: str) -> bool:
    return bool(_cau_hinh().get(str(conn_id)))


def bat(conn_id: str, on: bool) -> dict:
    """Bật/tắt ghi hội thoại cho một tài khoản Zalo. Trả về trạng thái sau khi đổi."""
    cid = str(conn_id or "").strip()
    if not cid:
        return {"ok": False, "error": localefmt.chu("thiếu id kết nối", "missing connection id")}
    if not any(c["id"] == cid for c in _ket_noi()):
        return {"ok": False, "error": localefmt.chu("không có kết nối Zalo nào id đó (hoặc đang tắt ở trang Kết nối)",
                                                    "no Zalo connection has that id (or it is turned off on the Connections page)")}
    cfg = cfgmod.read_settings()
    ht = cfg.setdefault("conversations", {})
    if not isinstance(ht, dict):
        ht = cfg["conversations"] = {}
    zp = ht.setdefault("zalo_personal", {})
    if not isinstance(zp, dict):
        zp = ht["zalo_personal"] = {}
    zp[cid] = bool(on)
    cfgmod.write_settings(cfg)
    if on:
        # Bật là bắt đầu từ BÂY GIỜ: bỏ cursor cũ để không kéo lại bộ đệm cũ của một lần bật trước.
        _TT.pop(cid, None)
        start()
    return {"ok": True, "id": cid, "theo_doi": bool(on)}


# ============================================================
# Kết nối Zalo đang có
# ============================================================
def _ket_noi() -> List[dict]:
    """Kết nối Zalo đang BẬT ở trang Kết nối, bản đầy đủ (có env HOME) cho dial spec."""
    try:
        import mcp_store
        return [c for c in mcp_store.resolved(enabled_only=True)
                if c.get("connector_id") == CONNECTOR_ID]
    except Exception as e:
        print(f"[zalo-personal] đọc kết nối lỗi: {type(e).__name__}: {e}", file=sys.stderr)
        return []


def ket_noi_theo_id(conn_id: str) -> Optional[dict]:
    """Bản đầy đủ (có env) của một kết nối Zalo đang bật, để gọi MCP. None nếu không có."""
    for c in _ket_noi():
        if c.get("id") == str(conn_id or ""):
            return c
    return None


def tai_khoan() -> List[dict]:
    """Cho trang Hộp thư: mỗi tài khoản Zalo kèm cờ theo dõi và trạng thái vòng đọc."""
    cfg = _cau_hinh()
    out = []
    for c in _ket_noi():
        tt = _TT.get(c["id"]) or {}
        out.append({
            "id": c["id"], "label": c.get("label") or "Zalo", "channel": KENH,
            "theo_doi": bool(cfg.get(c["id"])),
            "lan_cuoi": tt.get("lan_cuoi") or 0, "loi": tt.get("loi") or "",
            "so_tin": int(tt.get("so_tin") or 0),
        })
    return out


# ============================================================
# Gọi MCP
# ============================================================
async def _goi(conn: dict, tool: str, args: dict) -> Any:
    import mcp_client
    spec = mcp_client._conn_spec(conn)
    raw = await mcp_client.pool.call_tool(spec, tool, args or {})
    if isinstance(raw, str) and raw.startswith("ERROR:"):
        raise RuntimeError(raw[6:].strip()[:300])
    return _json_cua(raw)


# ============================================================
# Chat labels (tags the owner set in the Zalo app), 0.281.0
# ============================================================
# Read with javis-zalo 1.6.0's `zalo_get_labels`. One call returns every label with its chats, so the whole map is
# kept per connection for `LABEL_TTL_S` and each incoming message only looks it up. A connection whose MCP has no such
# tool (older javis-zalo) or that fails is asked again only after `LABEL_RETRY_S`: a bot must never wait on Zalo for
# every message just to learn there are no labels.
LABEL_TTL_S = 60
LABEL_RETRY_S = 600
_LABELS: Dict[str, dict] = {}       # conn_id -> {"at", "names": [...], "by_thread": {thread_id: [names]}, "ok"}


def _label_map(data: Any) -> dict:
    """`zalo_get_labels` result -> {"names": [label names in the owner's order], "by_thread": {thread_id: [names]}}."""
    names, by_thread = [], {}
    labels = data.get("labels") if isinstance(data, dict) else None
    for lb in labels if isinstance(labels, list) else []:
        if not isinstance(lb, dict):
            continue
        name = " ".join(str(lb.get("name") or "").split())[:60]
        if not name:
            continue
        if name not in names:
            names.append(name)
        for t in lb.get("threads") or []:
            tid = str((t or {}).get("threadId") or "").strip() if isinstance(t, dict) else ""
            if tid:
                ds = by_thread.setdefault(tid, [])
                if name not in ds:
                    ds.append(name)
    return {"names": names, "by_thread": by_thread}


async def _labels_of_conn(conn_id: str) -> dict:
    """The cached label map of one connection; `{"names": [], "by_thread": {}}` when unknown. Never raises."""
    now = time.time()
    c = _LABELS.get(conn_id)
    if c and now - c["at"] < (LABEL_TTL_S if c.get("ok") else LABEL_RETRY_S):
        return c
    conn = ket_noi_theo_id(conn_id)
    if not conn:
        return {"names": [], "by_thread": {}}
    try:
        data = await asyncio.wait_for(_goi(conn, "zalo_get_labels", {}), timeout=8)
        m = _label_map(data)
        if not isinstance(data, dict) or "labels" not in data:
            raise RuntimeError("no labels in the reply")
        c = dict(m, at=now, ok=True)
    except Exception as e:      # noqa: BLE001 - labels are a hint for the bot; without them it runs as before
        print(f"[zalo-personal {conn_id}] đọc tag Zalo lỗi: {type(e).__name__}: {str(e)[:160]}", file=sys.stderr)
        c = dict(c or {"names": [], "by_thread": {}}, at=now, ok=False)
    _LABELS[conn_id] = c
    return c


async def labels_of_chat(conn_id: str, thread_id: str) -> List[str]:
    """Names of the Zalo labels on one chat of a connection (e.g. ["Gia đình"]); [] when none or unknown."""
    m = await _labels_of_conn(str(conn_id or ""))
    return list((m.get("by_thread") or {}).get(str(thread_id or ""), []))


async def label_names(conn_id: str) -> List[str]:
    """Every label name of a connection, for the bot form's picker; [] when unknown."""
    return list((await _labels_of_conn(str(conn_id or ""))).get("names") or [])


def _json_cua(raw: Any) -> Any:
    """Kết quả MCP về dạng chữ; bóc JSON nếu có, không thì trả nguyên."""
    if isinstance(raw, (dict, list)):
        return raw
    s = str(raw or "").strip()
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        pass
    # Có server bọc JSON trong text kèm vài dòng chữ: lấy khối {...} hoặc [...] đầu tiên.
    for mo, dong in (("{", "}"), ("[", "]")):
        a, b = s.find(mo), s.rfind(dong)
        if 0 <= a < b:
            try:
                return json.loads(s[a:b + 1])
            except Exception:
                continue
    return {"text": s}


# ============================================================
# Chuẩn hoá một tin Zalo về sự kiện chung
# ============================================================
def _lay(d: dict, *khoa, mac_dinh=None):
    for k in khoa:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return mac_dinh


def _ts(v: Any) -> float:
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        return time.time()
    if f <= 0:
        return time.time()
    return f / 1000.0 if f > 1e12 else f


def _la_nhom(msg: dict, ten: dict) -> bool:
    t = _lay(msg, "threadType", "thread_type", "type_thread", mac_dinh=None)
    if t is not None:
        s = str(t).strip().lower()
        if s in ("1", "group", "true"):
            return True
        if s in ("0", "dm", "user", "private", "false"):
            return False
    if isinstance(msg.get("isGroup"), bool):
        return msg["isGroup"]
    return str((ten or {}).get("type") or "").lower() == "group"


def _la_cua_minh(msg: dict) -> bool:
    for k in ("isSelf", "fromMe", "isOwn", "self", "is_self", "from_me"):
        v = msg.get(k)
        if isinstance(v, bool):
            return v
    return False


def _chua_ro_loai(msg: dict, ten: dict) -> bool:
    """Tin này không nói cuộc chat là nhóm hay chat riêng, và bảng cuộc chat cũng không biết.

    `zalo_get_messages` không có `threadType` (ví dụ của MCP chỉ có id, threadId, text, from, ts),
    nên loại cuộc chat chủ yếu đến từ bảng `zalo_list_threads`. Cuộc chat ngoài bảng mà cứ coi là
    chat riêng thì một nhóm mới sẽ bị bot trả lời từng tin như chat riêng.
    """
    if not isinstance(msg, dict):
        return False
    thread = str(_lay(msg, "threadId", "thread_id", "chatId", mac_dinh="") or "").strip()
    if not thread:
        return False
    if _lay(msg, "threadType", "thread_type", "type_thread", mac_dinh=None) is not None:
        return False
    if isinstance(msg.get("isGroup"), bool):
        return False
    return thread not in (ten or {})


def _loai_tin(msg: dict) -> str:
    t = str(_lay(msg, "type", "msgType", "message_type", mac_dinh="text") or "text").lower()
    if t in conversations.LOAI_TIN:
        return t
    if "image" in t or "photo" in t or t == "chat.photo":
        return "image"
    if "voice" in t or "audio" in t:
        return "audio"
    if "video" in t:
        return "video"
    if "sticker" in t:
        return "sticker"
    if "file" in t or "doc" in t:
        return "file"
    if t in ("text", "chat", "webchat"):
        return "text"
    return "other"


def _link_anh(msg: dict) -> str:
    """Link of the photo in an image message (0.74.1), or "".

    The MCP normalizes a photo as `attachment: {type, url: content.href, description: content.title}` (javis-zalo,
    `normalizeMessage` in src/mcp/message-normalize.js; same shape as zalo-agent-cli 1.6.2). Before 0.74.1 this was dropped here, so the inbox and the customer bot only ever got
    the caption and the bot answered "I can only see the caption". A bare photo also carries the link as its `text`."""
    att = msg.get("attachment") if isinstance(msg.get("attachment"), dict) else {}
    for v in (att.get("url"), msg.get("mediaUrl"), msg.get("url"), msg.get("text")):
        v = str(v or "").strip()
        if v.startswith("https://"):
            return v
    return ""


def _su_kien_vao_nhom(msg: dict) -> Optional[dict]:
    """Someone joined the group (javis-zalo >= 1.1.0): `{time, added_by, added_by_me}` in seconds, else None.

    javis-zalo puts each join in the live feed as a message of type `group.join` sent BY the newcomer, with
    `event: {kind: "join", time (ms), addedBy, addedByMe}`. The type alone is enough; `event` adds detail."""
    ev = msg.get("event") if isinstance(msg.get("event"), dict) else {}
    if str(msg.get("type") or "").lower() != "group.join" and ev.get("kind") != "join":
        return None
    t = _ts(ev.get("time") or _lay(msg, "ts", "timestamp", "time", mac_dinh=0))
    return {"time": t, "added_by": str(ev.get("addedBy") or ""), "added_by_me": bool(ev.get("addedByMe"))}


def _su_kien_xin_vao(msg: dict) -> Optional[dict]:
    """Someone asked to join a group that requires approval (javis-zalo >= 1.2.0): `{time, total_pending}`, else None.

    javis-zalo puts each request in the live feed as a message of type `group.join_request` sent BY the applicant."""
    ev = msg.get("event") if isinstance(msg.get("event"), dict) else {}
    if str(msg.get("type") or "").lower() != "group.join_request" and ev.get("kind") != "join_request":
        return None
    return {"time": _ts(ev.get("time") or _lay(msg, "ts", "timestamp", "time", mac_dinh=0)),
            "total_pending": ev.get("totalPending")}


# Báo chủ khi có người xin vào nhóm (0.84.7). `main` gắn `_notify_owner` vào đây lúc khởi động: hòm thư (chuông) và
# Telegram của chủ. Để trống (test, chạy rời) thì không báo, sự kiện vẫn vào Hộp thư hội thoại như thường.
NOTIFY_OWNER = None
XIN_VAO_TOI_DA_TEN = 10


def cau_bao_xin_vao(conn: dict, chat_title: str, names: List[str]) -> str:
    """Câu báo chủ: ai đang xin vào nhóm nào, và cách xử lý. Một câu cho cả lô của một nhóm."""
    ds = [n for n in names if n][:XIN_VAO_TOI_DA_TEN]
    them = len([n for n in names if n]) - len(ds)
    ai = ", ".join(ds) + (localefmt.chu(f" và {them} người khác", f" and {them} more") if them > 0 else "")
    nhom = chat_title or localefmt.chu("một nhóm", "a group")
    tk = conn.get("label") or "Zalo"
    return localefmt.chu(
        f"Zalo ({tk}): {ai} đang xin vào nhóm \"{nhom}\". Nhắn Javis \"duyệt\" hoặc \"từ chối\" để xử lý "
        f"(tài khoản này phải là trưởng hoặc phó nhóm).",
        f"Zalo ({tk}): {ai} asked to join the group \"{nhom}\". Tell Javis \"approve\" or \"reject\" to handle it "
        f"(this account must be the group's owner or a deputy).")


def _bao_xin_vao(conn: dict, theo_nhom: Dict[str, dict]) -> None:
    """Một thông báo cho mỗi nhóm có người mới xin vào trong lô vừa đọc. Không có vòng lặp sự kiện thì thôi."""
    if not theo_nhom or NOTIFY_OWNER is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    for nhom in theo_nhom.values():
        cau = cau_bao_xin_vao(conn, nhom["ten"], nhom["nguoi"])
        t = loop.create_task(NOTIFY_OWNER("", cau, kind="system", label="Zalo", source="zalo-group"))
        _VIEC.add(t)
        t.add_done_callback(_VIEC.discard)


def _reaction_meta(conn: dict, msg: dict, thread: str, sender_id: str) -> dict:
    """A reaction entry of the feed (javis-zalo >= 1.7.0, `type: "reaction"`) -> `metadata.reaction` (0.334.0).

    Looks up the message it was put on in the inbox, so the line the judge and the Agent read says WHAT was reacted
    to and whose it was: `target_side` "ours" (this account: the bot or the owner), "self" (the reactor's own), or
    the member's name. A message the inbox never stored keeps an empty `target_text`."""
    import bot_reaction
    r = msg.get("reaction") if isinstance(msg.get("reaction"), dict) else {}
    name = str(r.get("name") or "").strip().lower()
    target_id = str(r.get("targetMsgId") or "").strip()
    target = conversations.tin_theo_id(KENH, conn["id"], thread, target_id) if target_id else {}
    kind = str(target.get("message_type") or "")
    text = str(target.get("text") or "")
    if kind == "image":
        text = conversations.chu_thich_anh(text) or localefmt.chu("(ảnh)", "(photo)")
    elif kind == "reaction":
        text = ""
    elif kind and kind != "text" and text.startswith("["):
        text = f"({kind})"
    author = str(target.get("sender_type") or "")
    if author in ("ai", "human"):
        side = "ours"
    elif author == "customer":
        side = ("self" if str(target.get("sender_id") or "") == str(sender_id or "")
                else (str(target.get("sender_name") or "").strip() or "self"))
    else:
        side = ""
    return {
        "name": name, "emoji": str(r.get("emoji") or "") or bot_reaction.emoji_of(name), "code": str(r.get("code") or ""),
        "removed": bool(r.get("removed")), "target_msg_id": target_id,
        "target_cli_msg_id": str(r.get("targetCliMsgId") or ""), "target_text": text, "target_side": side,
    }


def chuan_hoa_tin(conn: dict, msg: dict, ten: Dict[str, dict]) -> Optional[dict]:
    """Một tin của `zalo_get_messages` -> sự kiện chung của kho. None nếu không biết thread."""
    if not isinstance(msg, dict):
        return None
    thread = str(_lay(msg, "threadId", "thread_id", "chatId", mac_dinh="") or "").strip()
    if not thread:
        return None
    th = ten.get(thread) or {}
    nhom = _la_nhom(msg, th)
    sender_id = str(_lay(msg, "from", "senderId", "sender_id", "uidFrom", mac_dinh="") or "").strip()
    sender_name = str(_lay(msg, "senderName", "sender_name", "fromName", "dName", mac_dinh="") or "").strip()
    if not sender_name and not nhom:
        sender_name = str(th.get("name") or "")
    loai = _loai_tin(msg)
    from zalo_attachments import normalize as normalize_attachment
    text = _lay(msg, "text", "content", "msg", "message", mac_dinh="")
    if isinstance(text, dict):
        text = _lay(text, "text", "title", "description", "href", mac_dinh="")
    text = strip_mention_markup(str(text or ""))
    if loai != "text" and not text.strip():
        # The account's own photo (isSelf, from the owner's phone) is not "the customer sent".
        text = (f"[{conversations.KENH_NHAN[KENH]}: gửi {loai}]" if _la_cua_minh(msg)
                else f"[{conversations.KENH_NHAN[KENH]}: khách gửi {loai}]")
    vao_nhom = _su_kien_vao_nhom(msg) if nhom else None
    if vao_nhom is not None:
        ten_moi = sender_name or sender_id
        text = localefmt.chu(f"[{ten_moi} vừa vào nhóm]", f"[{ten_moi} joined the group]")
    xin_vao = _su_kien_xin_vao(msg) if nhom else None
    if xin_vao is not None:
        ten_moi = sender_name or sender_id
        text = localefmt.chu(f"[{ten_moi} xin vào nhóm]", f"[{ten_moi} asked to join the group]")
    cua_minh = _la_cua_minh(msg)
    reaction = _reaction_meta(conn, msg, thread, sender_id) if loai == "reaction" else None
    if reaction is not None:
        import bot_reaction
        text = bot_reaction.describe(localefmt.chu("Bên mình", "We") if cua_minh else (sender_name or sender_id),
                                     reaction)
    return {
        "channel": KENH,
        "account_id": conn["id"],
        "account_name": conn.get("label") or "Zalo",
        "bot_id": "",
        "external_chat_id": thread,
        "chat_type": "group" if nhom else "private",
        "chat_title": str(th.get("name") or "") if nhom else "",
        # Tin do CHÍNH chủ gửi (từ điện thoại) là tin người thật, không phải tin khách.
        "sender_type": "human" if cua_minh else "customer",
        "sender_id": "" if cua_minh else (sender_id or ("" if nhom else thread)),
        "sender_name": sender_name,
        "message_type": loai,
        "text": text,
        "external_message_id": str(_lay(msg, "id", "msgId", "message_id", mac_dinh="") or ""),
        "created_at": _ts(_lay(msg, "ts", "timestamp", "time", mac_dinh=0)),
        "metadata": dict({k: msg.get(k) for k in ("replyTo", "mentions", "mediaUrl", "url", "fileName", "cliMsgId")
                          if msg.get(k) not in (None, "")},
                         **({"reaction": reaction} if reaction is not None else {}),
                         **({"chua_ro_loai": True} if _chua_ro_loai(msg, ten) else {}),
                         **({"member_join": vao_nhom} if vao_nhom is not None else {}),
                         **({"join_request": xin_vao} if xin_vao is not None else {}),
                         **({"attachment": normalize_attachment(msg)} if loai == "file" else {}),
                         **({"image_url": _link_anh(msg)} if loai == "image" and _link_anh(msg) else {}),
                         # 0.433.0: the clip's link (javis-zalo `attachment.url`), so the bot can look at its frames.
                         **({"video_url": _link_anh(msg)} if loai == "video" and _link_anh(msg) else {})),
    }


# ============================================================
# Nhập tin cũ (0.174.0)
# ============================================================
# Chủ repo hỏi 16/10/2026: đăng nhập Zalo vào Javis lần đầu thì Hộp thư trống trơn, dù điện thoại có cả trăm cuộc chat. javis-zalo
# (từ 1.1.0) tự kéo tin cũ về mỗi lần kết nối, khoảng 2 tuần gần nhất theo cửa sổ phát lại của Zalo, rồi giữ trong kho lịch sử của
# nó (`zalo_search_history`). Vòng đọc ở dưới không dùng kho đó: nó chỉ đọc bộ đệm tin MỚI (`zalo_get_messages`), đúng như quyết
# định 3 ở đầu file. Nút "Nhập tin cũ" là lựa chọn riêng của chủ, không chạy tự động.
#
# Ba rào:
#   1. Chỉ nhập vào cuộc chat CHƯA có tin nào trong kho. Khung tin xếp theo id, nên tin cũ nhập sau tin mới sẽ hiện SAU tin mới.
#      Cuộc chat đã có tin thì bỏ qua, nói rõ trong kết quả.
#   2. Không giao cho bot, không cộng số chưa đọc, không đụng đồng hồ "chủ vừa nhắn tay": đây là tin đã qua, ghi để xem lại.
#   3. Có trần (`NHAP_TOI_DA` tin, `NHAP_NGAY` ngày) để một nick nhiều nhóm không làm kho phình. Nhóm vẫn chỉ giữ
#      `conversations.GIU_TIN_NHOM` tin gần nhất như mọi lúc.
NHAP_NGAY = 14
NHAP_TOI_DA = 5000
NHAP_TRANG = 200            # trần `limit` của zalo_search_history
_DANG_NHAP: set = set()     # conn_id đang nhập: bấm hai lần liền không chạy chồng


async def nhap_lich_su(conn_id: str, ngay: int = NHAP_NGAY) -> dict:
    """Nhập tin cũ javis-zalo đã giữ (tối đa `ngay` ngày, `NHAP_TOI_DA` tin) vào Hộp thư, chỉ cho cuộc chat chưa có tin nào.

    Trả {"ok", "so_tin", "so_cuoc_chat", "bo_qua", "het_tran"} hoặc {"ok": False, "loi"}."""
    cid = str(conn_id or "")
    conn = ket_noi_theo_id(cid)
    if not conn:
        return {"ok": False, "loi": localefmt.chu("Tài khoản Zalo này không còn ở trang Kết nối (hoặc đang tắt).",
                                                   "This Zalo account is no longer on the Connections page (or is off).")}
    if cid in _DANG_NHAP:
        return {"ok": False, "loi": localefmt.chu("Đang nhập tin cũ cho tài khoản này, chờ chút rồi xem lại Hộp thư.",
                                                   "Old messages are already being imported for this account.")}
    _DANG_NHAP.add(cid)
    try:
        ngay = max(1, min(int(ngay or NHAP_NGAY), 30))
        tu = int((time.time() - ngay * 86400) * 1000)
        tin: List[dict] = []
        truoc, het_tran = None, False
        while True:
            args: Dict[str, Any] = {"since": tu, "limit": NHAP_TRANG}
            if truoc:
                args["before"] = truoc
            try:
                d = await _goi(conn, "zalo_search_history", args)
            except Exception as e:
                if not tin:
                    return {"ok": False, "loi": localefmt.chu(
                        f"javis-zalo không trả được tin cũ: {str(e)[:200]}. Bản javis-zalo cần từ 1.1.0 trở lên.",
                        f"javis-zalo could not return old messages: {str(e)[:200]}. javis-zalo 1.1.0 or newer is needed.")}
                break
            trang = (d.get("messages") if isinstance(d, dict) else None) or []
            tin.extend(m for m in trang if isinstance(m, dict))
            if len(tin) >= NHAP_TOI_DA:
                het_tran = True
                break
            truoc = d.get("cursor") if isinstance(d, dict) else None
            if not (isinstance(d, dict) and d.get("hasMore") and truoc and trang):
                break
        if not tin:
            return {"ok": True, "so_tin": 0, "so_cuoc_chat": 0, "bo_qua": 0, "het_tran": False}
        ten = await _nap_ten(conn, {})
        theo_chat: Dict[str, List[dict]] = {}
        for m in tin:
            ev = chuan_hoa_tin(conn, m, ten)
            if ev and ev.get("external_message_id"):
                ev["metadata"] = dict(ev.get("metadata") or {}, lich_su=True)
                theo_chat.setdefault(ev["external_chat_id"], []).append(ev)
        so_tin = so_chat = bo_qua = 0
        for chat, evs in theo_chat.items():
            if conversations.co_tin(KENH, cid, chat):
                bo_qua += 1
                continue
            evs.sort(key=lambda e: float(e.get("created_at") or 0))
            ghi = 0
            for ev in evs:
                r = conversations.ghi_su_kien(ev, dem_chua_doc=False)
                if r.get("ok") and not r.get("trung"):
                    ghi += 1
            if ghi:
                so_tin += ghi
                so_chat += 1
        return {"ok": True, "so_tin": so_tin, "so_cuoc_chat": so_chat, "bo_qua": bo_qua, "het_tran": het_tran}
    finally:
        _DANG_NHAP.discard(cid)


# ============================================================
# Vòng đọc
# ============================================================
def _epoch(conn: dict) -> int:
    """Số hiệu PHIÊN MCP đang sống của kết nối này (0 = chưa có phiên). Xem `mcp_client.pool.epoch`."""
    try:
        import mcp_client
        return int(mcp_client.pool.epoch(mcp_client._conn_spec(conn)) or 0)
    except Exception:
        return 0


def _thread_cua(msg: Any) -> str:
    if not isinstance(msg, dict):
        return ""
    return str(_lay(msg, "threadId", "thread_id", "chatId", mac_dinh="") or "").strip()


async def _nap_ten(conn: dict, tt: dict, cuong_buc: bool = False) -> Dict[str, dict]:
    """Bảng threadId -> {name, type}. Hỏi lại sau TEN_TTL giây, hỏng thì giữ bảng cũ.

    `cuong_buc`: hỏi lại NGAY dù chưa hết hạn (nhưng không dồn quá một lần mỗi `THU_LAI_TEN_GIAY`),
    dùng khi có tin từ một cuộc chat chưa có trong bảng: nhóm nick vừa vào, khách mới nhắn.

    Loại cuộc chat đọc từ `threadType` ("group" | "dm" | "unknown", khoá THẬT của MCP 1.6.2), rơi
    về `type` (khuôn trong tài liệu mcp-guide).
    """
    if tt.get("ten") is not None:
        tuoi = time.time() - float(tt.get("ten_ts") or 0)
        if tuoi < TEN_TTL and not (cuong_buc and tuoi >= THU_LAI_TEN_GIAY):
            return tt["ten"]
    tt["ten_lan"] = int(tt.get("ten_lan") or 0) + 1     # số lần HỎI THẬT (đồng hồ Windows có bước ~15ms, không dùng mốc giờ để đếm)
    try:
        d = await _goi(conn, "zalo_list_threads", {"limit": 200})
        ds = d.get("threads") if isinstance(d, dict) else d
        bang: Dict[str, dict] = dict(tt.get("ten") or {})
        for t in (ds or []):
            if not isinstance(t, dict):
                continue
            tid = str(_lay(t, "threadId", "id", mac_dinh="") or "")
            if tid:
                bang[tid] = {"name": str(t.get("name") or "")[:120],
                             "type": str(t.get("threadType") or t.get("type") or "")}
        if len(bang) > MAX_TEN:
            bang = dict(list(bang.items())[-MAX_TEN:])
        tt["ten"], tt["ten_ts"] = bang, time.time()
    except Exception as e:
        tt["ten_ts"] = time.time()      # đừng hỏi dồn dập khi đang hỏng
        if tt.get("ten") is None:
            tt["ten"] = {}
        print(f"[zalo-personal {conn.get('label')}] list_threads: {e}", file=sys.stderr)
    return tt["ten"]


async def _lam_moi_ten_neu_thieu(conn: dict, tt: dict, tin: list, ten: dict) -> dict:
    """Có tin từ cuộc chat CHƯA CÓ trong bảng tên thì làm mới bảng ngay, dù tin đã có threadType.

    Nhóm nick vừa vào chưa có trong bảng (làm mới 5 phút một lần), nên cuộc chat không có tiêu đề
    và Hộp thư lấy tên NGƯỜI NHẮN ĐẦU TIÊN làm tên nhóm. Cuộc chat mà làm mới rồi vẫn không thấy
    thì nhớ `THU_TEN_LAI` giây, khỏi gọi lại `zalo_list_threads` mỗi nhịp 20 giây.
    """
    now = time.time()
    da_thu = tt.setdefault("da_thu_ten", {})
    thieu = [t for t in {_thread_cua(m) for m in tin} if t and t not in ten
             and now - float(da_thu.get(t, 0)) > THU_TEN_LAI]
    if not thieu:
        return ten
    truoc = tt.get("ten_lan")
    ten = await _nap_ten(conn, tt, cuong_buc=True)
    if tt.get("ten_lan") != truoc:      # thật sự đã hỏi (không bị chặn bởi nhịp chờ tối thiểu)
        for t in thieu:
            da_thu[t] = now
        if len(da_thu) > MAX_TEN:
            for k in list(da_thu)[:MAX_TEN // 2]:
                da_thu.pop(k, None)
    return ten


def _ghi_lo(conn: dict, tin: list, ten: dict) -> tuple:
    """Ghi một lô tin vào kho và giao tin khách mới cho bot. Trả (số tin mới, số tin trùng)."""
    moi = trung = 0
    xin_vao: Dict[str, dict] = {}
    for m in tin:
        ev = chuan_hoa_tin(conn, m, ten)
        if not ev:
            continue
        if ev.get("message_type") == "reaction":
            # A reaction (0.334.0) is never the owner typing and never an echo of a sentence: it goes to the inbox as
            # it is. This account's own one is the bot's when the bot just put it (`remember_bot_reaction`), else the owner's.
            # A customer's goes to the bot like a message; whether it deserves anything is the judge's call (or the
            # Agent's), never decided here. Taking a reaction back is only recorded.
            if ev["sender_type"] == "human":
                bot = _bot_reaction_echo(conn["id"], ev["external_chat_id"], (ev.get("metadata") or {}).get("reaction"))
                if bot is not None:
                    ev = dict(ev, sender_type="ai", sender_name=bot)
            kq = conversations.ghi_su_kien(ev)
            if kq.get("ok"):
                if kq.get("trung"):
                    trung += 1
                else:
                    moi += 1
                    if ev["sender_type"] == "customer" and not ((ev.get("metadata") or {}).get("reaction") or {}).get("removed"):
                        _giao_cho_bot(conn, ev)
            continue
        if ev["sender_type"] == "human":
            _hoc_danh_tinh(conn["id"], m)
            # Tin chủ gửi đi. Tiếng vọng của câu BOT vừa gửi thì bỏ (bot đã tự ghi câu đó vào
            # Hộp thư, ghi thêm lần nữa là hiện hai lần, lần hai mang nhãn "người thật"). Còn
            # lại là chủ tự tay nhắn: nhớ giờ để bot nhường cuộc chat đó.
            if _la_tieng_vong(conn["id"], ev["external_chat_id"], ev["text"]) or (
                    ev.get("message_type") == "image"
                    and _la_vong_anh(conn["id"], ev["external_chat_id"])):
                attach_echo_id(conn["id"], ev)
                trung += 1
                continue
            _TAY[(conn["id"], ev["external_chat_id"])] = float(ev.get("created_at") or time.time())
            # Chủ đã vào cuộc: mấy tin khách đang gom chờ là việc của chủ, không phải của bot. This holds even when
            # the bot is set to yield 0 minutes: 0 means "do not go quiet", not "repeat what I just answered".
            _GOM.pop((conn["id"], ev["external_chat_id"]), None)
            bo_cho_chu(conn["id"], ev["external_chat_id"])
        elif _la_tieng_vong(conn["id"], ev["external_chat_id"], ev["text"], TIENG_VONG_TOI_THIEU):
            # Ví dụ trong tài liệu của MCP không có cờ "tin của chính mình", nên câu bot vừa gửi
            # có thể quay về như tin của một KHÁCH. Để lọt thì trong nhóm bot sẽ tự trả lời chính
            # nó, và Hộp thư ghi câu bot nói thành tin khách. Chỉ áp cho tin đủ dài: "Dạ" hay "ok"
            # khách nói trùng câu bot vừa nói là chuyện thường, còn một đoạn dài y hệt thì là vọng.
            attach_echo_id(conn["id"], ev)
            trung += 1
            continue
        kq = conversations.ghi_su_kien(ev)
        if kq.get("ok"):
            if kq.get("trung"):
                trung += 1
            else:
                moi += 1
                if (ev.get("metadata") or {}).get("join_request"):
                    # Xin vào nhóm là việc CHỦ quyết (0.84.7): báo chủ, không giao cho bot.
                    nhom = xin_vao.setdefault(ev["external_chat_id"], {"ten": ev.get("chat_title") or "", "nguoi": []})
                    nhom["nguoi"].append(ev.get("sender_name") or ev.get("sender_id") or "")
                    continue
                _giao_cho_bot(conn, ev)
    _bao_xin_vao(conn, xin_vao)
    return moi, trung


def _so_nguyen(v: Any) -> Optional[int]:
    """Con trỏ đọc của MCP là số nguyên. Chuỗi không phải số (khuôn trong tài liệu ghi
    "cursor_abc") thì None: dùng bừa một con trỏ không hiểu còn tệ hơn đọc lại từ đầu."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)) and v >= 0:
        return int(v)
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


async def doc_mot_lan(conn: dict) -> dict:
    """Một lượt đọc cho một tài khoản. Trả {"moi": n, "trung": n} hoặc ném lỗi.

    `zalo_get_messages` của MCP nhận `since` (số nguyên, số thứ tự toàn cục của bộ đệm) và `limit`,
    trả tin CŨ NHẤT TRƯỚC kèm `cursor` (số) và `hasMore`. Không có khoá `cursor` ở phía nhận: bản
    trước truyền `cursor` (bị bỏ qua) nên mỗi lần đọc lại 100 tin cũ nhất, và khi bộ đệm dày hơn thế
    thì tin mới không bao giờ tới. Số thứ tự đếm lại từ 1 mỗi lần tiến trình MCP khởi động, nên
    `since` chỉ giữ trong RAM và chỉ dùng khi phiên MCP còn là phiên đã cấp nó (`_epoch`).
    """
    tt = _TT.setdefault(conn["id"], {})
    bat_dau = time.time()       # mọi tin tới trước mốc này đã nằm trong lượt đọc này
    moi = trung = 0
    since = 0
    if tt.get("since") and tt.get("ep") and tt["ep"] == _epoch(conn):
        since = int(tt["since"])
    for _ in range(MAX_TRANG):
        ep_truoc = _epoch(conn)
        args: Dict[str, Any] = {"limit": LIMIT}
        if since:
            args["since"] = since
        d = await _goi(conn, "zalo_get_messages", args)
        if since and _epoch(conn) != ep_truoc:
            # Phiên MCP bị dựng lại NGAY trong lúc gọi: since cũ vô nghĩa với bộ đệm mới, đọc lại
            # từ đầu (tin trùng đã có kho chặn theo id).
            since = 0
            d = await _goi(conn, "zalo_get_messages", {"limit": LIMIT})
        if not isinstance(d, dict):
            d = {"messages": d if isinstance(d, list) else []}
        tin = d.get("messages") or []
        ten = await _nap_ten(conn, tt) if tin else (tt.get("ten") or {})
        if tin:
            ten = await _lam_moi_ten_neu_thieu(conn, tt, tin, ten)
        m1, t1 = _ghi_lo(conn, tin, ten)
        moi, trung = moi + m1, trung + t1
        nc = _so_nguyen(d.get("cursor"))
        if nc is None:
            nc = _so_nguyen(d.get("nextCursor"))
        if nc is None:
            tt["since"], tt["ep"] = 0, 0        # không hiểu con trỏ: lần sau đọc lại từ đầu
            break
        tt["since"], tt["ep"] = nc, _epoch(conn)
        if not (d.get("hasMore") and tin and nc > since):
            break
        since = nc
    tt["lan_cuoi"] = time.time()
    tt["loi"] = ""
    tt["so_tin"] = int(tt.get("so_tin") or 0) + moi
    # Chỉ xả sau một lượt đọc THÀNH CÔNG: lượt này vừa xác nhận khách không nhắn thêm gì tới `bat_dau`.
    xa_hang_cho(conn["id"], bat_dau)
    # Cũng vậy với tin chờ chủ trả lời: lượt đọc vừa xác nhận chủ chưa nhắn gì tới `bat_dau`.
    xa_cho_chu(conn["id"], bat_dau)
    return {"moi": moi, "trung": trung}


# Lỗi chết của tiến trình javis-zalo (src/commands/mcp.js) mà người dùng tự xử được, dịch ra lời thường.
_LOI_ZALO = (
    (re.compile(r"duplicate zalo web session", re.I),
     "Zalo đã ngắt phiên của Javis vì tài khoản này vừa được mở ở nơi khác: Zalo Web trên trình duyệt "
     "(chat.zalo.me) hoặc một máy Javis khác cũng đăng nhập tài khoản này. Mỗi tài khoản chỉ giữ được một "
     "phiên như vậy. Đóng nơi kia đi; Javis tự nối lại sau khoảng 2 phút.",
     "Zalo closed Javis's session because this account was just opened somewhere else: Zalo Web in a "
     "browser (chat.zalo.me) or another Javis machine signed in to the same account. An account keeps only "
     "one such session. Close the other one; Javis reconnects by itself in about 2 minutes."),
    (re.compile(r"auto-login failed|re-login retry failed|re-login failed", re.I),
     "Phiên đăng nhập Zalo của tài khoản này đã hết hạn hoặc bị đăng xuất. Vào trang Kết nối, đăng nhập "
     "lại Zalo bằng mã QR.",
     "This account's Zalo sign-in has expired or was signed out. Go to the Connections page and sign in "
     "to Zalo again with the QR code."),
)
_DONG_CAU_HINH = re.compile(r"\[mcp\] Config loaded: \{.*?\}\s*(\|\s*)?")


def mo_ta_loi(raw: str, cap: int = 300) -> str:
    """Câu lỗi cho thẻ bot và trang Kết nối khi đọc tin Zalo hỏng.

    Trước 0.88.6 thẻ chỉ giữ 300 ký tự ĐẦU của lỗi thô, mà dòng "[mcp] Config loaded: {...}" in lúc khởi
    động đã chiếm gần hết chỗ, nên lý do thật nằm SAU nó (Zalo đá phiên, mất đăng nhập) bị cắt mất; chủ
    repo chỉ thấy một dòng cấu hình vô nghĩa (báo 10/10). Lỗi người dùng tự xử được thì nói bằng lời
    thường; còn lại bỏ dòng cấu hình và giữ phần ĐUÔI, nơi tiến trình in lý do nó thoát."""
    s = str(raw or "")
    for mau, vi, en in _LOI_ZALO:
        if mau.search(s):
            return localefmt.chu(vi, en)
    s = _DONG_CAU_HINH.sub("", s).strip()
    return s if len(s) <= cap else "..." + s[-(cap - 3):]


async def _vong() -> None:
    print("[zalo-personal] vòng đọc bắt đầu", file=sys.stderr)
    while not _stop:
        try:
            cfg = _cau_hinh()
            # Có bot trực thì đọc dù công tắc Ghi hội thoại tắt: bot không đọc thì không trả lời được.
            bat_ids = {k for k, v in cfg.items() if v} | set(_BOTS)
            if bat_ids:
                for conn in _ket_noi():
                    if _stop or conn["id"] not in bat_ids:
                        continue
                    tt = _TT.setdefault(conn["id"], {})
                    luc = time.time()
                    if luc < float(tt.get("nghi_toi") or 0):
                        continue
                    # Vòng có thể thức dày hơn NHIP (một tài khoản khác đang nóng): tài khoản chưa tới
                    # hạn thì để yên, khỏi tăng số lần gọi MCP của mọi tài khoản theo một cuộc chat.
                    if luc < float(tt.get("doc_toi") or 0):
                        continue
                    try:
                        await doc_mot_lan(conn)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        tt["loi"] = mo_ta_loi(f"{type(e).__name__}: {e}")
                        tt["nghi_toi"] = time.time() + NHIP_LOI
                        print(f"[zalo-personal {conn.get('label')}] {tt['loi']}", file=sys.stderr)
                    else:
                        _nhan_loi_moi(conn)
                    _soi_tranh_phien(conn)
                    # Hạn sớm hơn một nhịp chút ít: vòng ngủ đúng một nhịp thì lần thức sau chắc chắn đã tới hạn.
                    tt["doc_toi"] = luc + _nhip_cua(conn["id"]) * 0.9
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[zalo-personal vòng] {type(e).__name__}: {e}", file=sys.stderr)
        try:
            await asyncio.sleep(_nhip_vong())
        except asyncio.CancelledError:
            raise
    print("[zalo-personal] vòng đọc dừng", file=sys.stderr)


# ============================================================
# Another session evicting ours (0.283.0)
# ============================================================
# Zalo keeps ONE live socket per account. When a second session of the same account is up (an `mcp start` an earlier
# server lifetime left behind, Zalo Web of this nick in a browser, another Javis or Claude client), ours is evicted
# right after every re-login and javis-zalo backs off up to five minutes. Reading still "works" (the buffer answers),
# so the bot card stayed green while the bot heard only the few seconds after each reconnect (field report
# 22/10/2026, Javis Vũ: three hours of tags in two groups unanswered). javis-zalo prints each close as
# "Connection closed (code: N). Re-login in Ss... (reconnect #R, rapid #K)"; K counts closes that came before the
# connection was stable, so K >= THRASH_RAPID means a rival.
THRASH_RAPID = 3
THRASH_SHOW_S = 900          # the bot card says "evicted" this long after the last rapid close
THRASH_BELL_GAP_S = 6 * 3600
_THRASH_RE = re.compile(r"reconnect #(\d+), rapid #(\d+)")
_THRASH_SEEN: Dict[str, tuple] = {}      # conn_id -> (session pid, last reconnect number handled)


def thrash_of(lines: List[str]) -> Optional[tuple]:
    """(reconnect number, rapid count) of the latest close line in a javis-zalo stderr tail, None when there is none."""
    for line in reversed(lines or []):
        m = _THRASH_RE.search(str(line))
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def _soi_tranh_phien(conn: dict) -> None:
    """After each read: a new rapid close in this connection's MCP log means another session holds the account. Kill
    any other `mcp start` on the same HOME (this machine), mark the bot card, ring the owner (once per 6 hours)."""
    try:
        import mcp_client
        import mcp_orphans
        cid = str(conn.get("id") or "")
        pid = mcp_client.pool.session_pid(cid)
        th = thrash_of(mcp_client.pool.stderr_lines(cid)) if pid else None
        if not th:
            return
        seen_pid, seen_n = _THRASH_SEEN.get(cid, (0, 0))
        if (pid, th[0]) == (seen_pid, seen_n) or (pid == seen_pid and th[0] < seen_n):
            return
        _THRASH_SEEN[cid] = (pid, th[0])
        if th[1] < THRASH_RAPID:
            return
        tt = _TT.setdefault(cid, {})
        tt["tranh_phien"] = time.time()
        home = str(((conn.get("env") or {}).get("HOME")) or "")
        killed = mcp_orphans.reap_same_home(home, keep_pgids=(pid,)) if home else []
        print(f"[zalo-personal {conn.get('label')}] another session keeps evicting this one "
              f"(reconnect #{th[0]}, rapid #{th[1]}); killed {len(killed)} local copy(ies)", file=sys.stderr)
        # 0.402.0: the last notice time is kept in the inbox store too, so a restart does not ring again at once.
        if not tt.get("tranh_phien_bao"):
            try:
                tt["tranh_phien_bao"] = float(conversations.doc_trang_thai(f"zalo_thrash_bell:{cid}", "0") or 0)
            except (TypeError, ValueError):
                tt["tranh_phien_bao"] = 0.0
        if NOTIFY_OWNER is None or time.time() - float(tt.get("tranh_phien_bao") or 0) < THRASH_BELL_GAP_S:
            return
        tt["tranh_phien_bao"] = time.time()
        conversations.ghi_trang_thai(f"zalo_thrash_bell:{cid}", str(tt["tranh_phien_bao"]))
        tk = conn.get("label") or "Zalo"
        don = (localefmt.chu(f" Javis đã tắt {len(killed)} bản Zalo cũ còn chạy trên máy này.",
                             f" Javis stopped {len(killed)} old Zalo copy(ies) still running on this machine.")
               if killed else "")
        cau = localefmt.chu(
            f"Zalo ({tk}) đang bị một phiên khác của cùng nick giành kết nối: bot chỉ nghe được tin vài giây sau mỗi lần "
            f"nối lại, tin tag và tin nhắn riêng ở giữa bị lỡ.{don} Nếu vẫn tiếp diễn: đóng Zalo Web (chat.zalo.me) của "
            "nick này trên mọi trình duyệt, tắt Javis hoặc Claude khác đang dùng cùng nick, rồi bấm Kiểm tra ở trang "
            "Kết nối.",
            f"Zalo ({tk}) is being evicted by another session of the same account: the bot only hears messages for a few "
            f"seconds after each reconnect, and tags and private messages in between are missed.{don} If it goes on: "
            "close Zalo Web (chat.zalo.me) for this account in every browser, stop any other Javis or Claude client "
            "using it, then click Check on the Connections page.")
        loop = asyncio.get_running_loop()
        t = loop.create_task(NOTIFY_OWNER("", cau, kind="system", label="Zalo", source="zalo"))
        _VIEC.add(t)
        t.add_done_callback(_VIEC.discard)
    except Exception as e:      # noqa: BLE001 - the watch must never cost a read
        print(f"[zalo-personal {conn.get('label')}] thrash watch: {type(e).__name__}: {e}", file=sys.stderr)


def evicted_recently(conn_id: str) -> bool:
    """Another session evicted this connection within `THRASH_SHOW_S` (see `_soi_tranh_phien`)."""
    return time.time() - float((_TT.get(str(conn_id or "")) or {}).get("tranh_phien") or 0) < THRASH_SHOW_S


def _nhan_loi_moi(conn: dict) -> None:
    """Friend-request intake (0.172.0, see `zalo_friend_intake`): start a round in its own task when one is due.
    Never awaited here: a slow Zalo must not pause reading, the customer-wait flush or the owner-silence flush."""
    try:
        import zalo_friend_intake as fi
        fi.start_round(conn)
    except Exception as e:      # noqa: BLE001
        print(f"[zalo-personal {conn.get('label')}] friend intake: {type(e).__name__}: {e}", file=sys.stderr)


def start() -> bool:
    """Bật vòng đọc nếu chưa chạy. Không có tài khoản nào được bật thì vòng vẫn chạy nhẹ (chỉ
    đọc cấu hình mỗi nhịp) để bật từ giao diện là có tác dụng ngay, không cần khởi động lại."""
    global _task, _stop
    if _task and not _task.done():
        return True
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    _stop = False
    _task = loop.create_task(_vong())
    return True


def stop() -> None:
    global _task, _stop
    _stop = True
    if _task and not _task.done():
        _task.cancel()
    _task = None
    try:
        import zalo_friend_intake
        zalo_friend_intake.cancel_all()
    except Exception:       # noqa: BLE001
        pass


def trang_thai() -> dict:
    return {"dang_chay": bool(_task and not _task.done()), "nhip": NHIP, "nhip_nhanh": NHIP_NHANH,
            "cho_khach_im": CHO_KHACH_IM, "cho_chu_tra_loi": CHO_CHU_TRA_LOI, "tai_khoan": tai_khoan()}


# ============================================================
# Bot trả lời (0.64.80)
# ============================================================
# Vòng đọc ở trên là NGUỒN tin duy nhất của tài khoản này (một con trỏ cursor, không được có
# hai người đọc). Bot chuyên trách không tự đọc mà đăng ký ở đây; tin khách mới ghi xong thì
# được đưa cho nó. Các rào để bot không nhắn bậy dưới tên chủ nằm ở `channels.zalo_personal.
# Transport.xu_ly` và ở hằng số dưới.
TUOI_TOI_DA = 180       # giây: tin cũ hơn thế thì KHÔNG trả lời. Lần đầu bật, bộ đệm của MCP
                        # còn cả những tin từ trước; trả lời chúng là dội lại câu hỏi của hôm qua.
TAY_IM = 600            # giây bot im sau khi chủ TỰ TAY nhắn cuộc chat đó (chủ đang nói chuyện rồi)
ECHO_TTL = 900          # giây nhớ câu bot vừa gửi để nhận ra tiếng vọng của nó ở vòng đọc
TIENG_VONG_TOI_THIEU = 25   # tin của KHÁCH phải dài ít nhất chừng này chữ mới bị coi là tiếng vọng (xem doc_mot_lan)
NHUONG_GIAY = 20        # giây bot chờ trước khi tự trả lời tin nhóm không ai gọi tên (chế độ Tự
                        # đánh giá): nếu trong lúc đó có người nhắn tay bằng nick này thì nhường

_BOTS: Dict[str, Any] = {}          # conn_id -> Transport đang trực
_DA_GUI: Dict[tuple, list] = {}     # (conn_id, thread) -> [(ts, chữ đã chuẩn hoá)]
_DA_GUI_ANH: Dict[tuple, list] = {}  # (conn_id, thread) -> [ts mỗi ảnh bot vừa gửi] (xem ghi_da_gui_anh)
_TAY: Dict[tuple, float] = {}       # (conn_id, thread) -> giờ tin chủ tự nhắn gần nhất
# Ảnh khách gửi trong CHAT RIÊNG (nhớ cho các lượt chữ ngay sau, xem `Transport.xu_ly`). Ca thật 15/10/2026: giáo viên gửi
# ảnh bài làm rồi nhắn "check xem đúng chưa", bot hỏi danh tính; trả lời xong thì ảnh đã ở tin trước nên bot nói "chưa đọc
# được ảnh", và ảnh gửi lại KHÔNG kèm chữ thì bị bỏ hẳn. Nhóm có cơ chế riêng (`_nho_anh_tron`, bộ phán xử).
ANH_RIENG_GIAY = 600    # giây một ảnh chat riêng còn được kèm vào các lượt chữ sau
_ANH_RIENG: Dict[tuple, tuple] = {}  # (conn_id, thread) -> (giờ, link ảnh) ảnh gần nhất khách gửi


def nho_anh_rieng(conn_id: str, thread: str, url: str, now: Optional[float] = None) -> None:
    if url:
        _ANH_RIENG[(str(conn_id), str(thread))] = (time.time() if now is None else now, url)
        if len(_ANH_RIENG) > 500:
            for k in list(_ANH_RIENG)[:250]:
                _ANH_RIENG.pop(k, None)


_VIDEO_RIENG: Dict[tuple, tuple] = {}  # (conn_id, thread) -> (time, link, message id) of the customer's latest video


def remember_private_video(conn_id: str, thread: str, url: str, msg_id: str = "", now: Optional[float] = None) -> None:
    """A private chat's latest video (0.433.0), shown again with the customer's next messages for `ANH_RIENG_GIAY`,
    like a photo: "anh xem hỗ trợ em với" right after a video is about that video. Frames are cached per link, so
    this costs no second download."""
    if url:
        _VIDEO_RIENG[(str(conn_id), str(thread))] = (time.time() if now is None else now, url, str(msg_id or ""))
        if len(_VIDEO_RIENG) > 500:
            for k in list(_VIDEO_RIENG)[:250]:
                _VIDEO_RIENG.pop(k, None)


def recent_private_video(conn_id: str, thread: str, now: Optional[float] = None) -> tuple:
    """(time, link, message id) of the customer's latest video in this private chat within `ANH_RIENG_GIAY`, else ()."""
    v = _VIDEO_RIENG.get((str(conn_id), str(thread)))
    if not v:
        return ()
    if (time.time() if now is None else now) - v[0] > ANH_RIENG_GIAY:
        _VIDEO_RIENG.pop((str(conn_id), str(thread)), None)
        return ()
    return v


def anh_rieng_gan_day(conn_id: str, thread: str, now: Optional[float] = None) -> tuple:
    """(giờ, link) của ảnh khách gửi gần nhất trong chat riêng này nếu còn trong `ANH_RIENG_GIAY`, không thì ()."""
    v = _ANH_RIENG.get((str(conn_id), str(thread)))
    if not v:
        return ()
    if (time.time() if now is None else now) - v[0] > ANH_RIENG_GIAY:
        _ANH_RIENG.pop((str(conn_id), str(thread)), None)
        return ()
    return v
_VIEC: set = set()                  # giữ tham chiếu task đang chạy, kẻo bị thu gom giữa chừng
_GOM: Dict[tuple, dict] = {}        # (conn_id, thread) -> {"evs": [...], "cuoi": ts}: chat riêng đang chờ khách nhắn xong
_NONG: Dict[str, float] = {}        # conn_id -> giờ thấy tin khách chat riêng gần nhất (đọc dày, xem `_nhip_cua`)
_SEQ: Dict[tuple, int] = {}         # (conn_id, thread) -> số tin khách chat riêng CÓ CHỮ đã thấy (xem "Câu trả lời đã cũ")
_BO_DO: Dict[tuple, dict] = {}      # (conn_id, thread) -> {"texts": [...], "n": số lần bỏ, "luc": giờ}: tin khách của câu trả lời đã bỏ
_ID_MINH: Dict[str, dict] = {}      # conn_id -> {"uid", "ten"} của CHÍNH nick này, học từ tin của nó


def _hoc_danh_tinh(conn_id: str, msg: dict) -> None:
    """Nhớ id + tên Zalo của CHÍNH nick này từ một tin nó gửi. Cần để biết một tin trong nhóm có
    tag mình không (`mentions` chỉ có id, tag trong chữ chỉ có tên hiển thị). Tài liệu của MCP
    không nói id của tài khoản đăng nhập nằm ở đâu, nên học từ tin đã có thay vì đoán.

    Id học sai còn tệ hơn không có id: `Transport.xu_ly` bỏ qua mọi tin mang id đó, nên nếu ở chat
    riêng `from` của tin mình gửi lại là id NGƯỜI KIA thì cả khách đó bị bỏ rơi. Hai lớp phòng:
    id trùng id cuộc chat thì không phải của mình, và chỉ tin id khi MỌI tin của nick đều cho
    đúng một giá trị (đổi qua đổi lại nghĩa là cờ "của mình" đang không đáng tin).
    """
    uid = str(_lay(msg, "from", "senderId", "sender_id", "uidFrom", mac_dinh="") or "").strip()
    thread = str(_lay(msg, "threadId", "thread_id", "chatId", mac_dinh="") or "").strip()
    ten = str(_lay(msg, "senderName", "sender_name", "fromName", "dName", mac_dinh="") or "").strip()
    cu = _ID_MINH.setdefault(str(conn_id), {})
    if uid and uid != thread:
        thay = cu.setdefault("_da_thay", set())
        thay.add(uid)
        cu["uid"] = uid if len(thay) == 1 else ""
    if ten:
        cu["ten"] = ten


def _chuan_ten(s: Any) -> str:
    import chatbot_grounding
    return " ".join(chatbot_grounding._bo_dau(str(s or "")).lower().split())


def _ds(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else ([] if v in (None, "") else [v])


def nhan_dien_goi(conn_id: str, ev: dict, ten_khac=()) -> tuple:
    """(được tag, được reply) của một tin nhóm, theo nick `conn_id`.

    Ba đường, vì khuôn dữ liệu của `zalo_get_messages` chưa được kiểm trên nhóm thật và ví dụ của
    MCP chỉ có `mentions`/`replyTo` ở `zalo_get_history`:
      - "@Tên" trong chữ, với tên là nhãn kết nối và tên hiển thị học được của nick;
      - `mentions` chứa id của nick (chuỗi hoặc object có uid);
      - `replyTo` trỏ về tin của nick (theo id hoặc theo tên người gửi).
    KHÔNG dùng tên Agent/bot: "@Lan" trong nhóm thường là một thành viên tên Lan.
    Không nhận ra thì cùng lắm chế độ Tự đánh giá vẫn bắt được câu hỏi thuộc tài liệu.
    """
    minh = _ID_MINH.get(str(conn_id)) or {}
    uid = str(minh.get("uid") or "").strip()
    ten = {_chuan_ten(x) for x in (list(ten_khac or ()) + [minh.get("ten")]) if x}
    ten.discard("")
    md = ev.get("metadata") or {}
    text_n = _chuan_ten(ev.get("text"))
    tag = any(re.search(r"@" + re.escape(t) + r"(?!\w)", text_n) for t in ten)
    if not tag and uid:
        for m in _ds(md.get("mentions")):
            x = (_lay(m, "uid", "id", "userId", mac_dinh="") if isinstance(m, dict) else m)
            if str(x).strip() == uid:
                tag = True
                break
    rep = False
    rt = md.get("replyTo")
    if isinstance(rt, dict):
        if uid and any(str(rt.get(k) or "").strip() == uid
                       for k in ("uid", "uidFrom", "senderId", "from", "idTo", "userId")):
            rep = True
        else:
            nguoi = _chuan_ten(_lay(rt, "senderName", "dName", "name", "fromName", mac_dinh=""))
            rep = bool(nguoi) and nguoi in ten
    return tag, rep


def _link_trong_quote(rt: dict) -> str:
    """A photo link the quote itself carries, or "". javis-zalo 1.4 gives `replyTo` only {senderId, senderName, text,
    msgId}; for a quoted photo Zalo may put the photo's serialized payload in `text` ({"href": ..., "thumb": ...}).
    Plain text is NOT read as a link: a quoted chat line that happens to hold a URL is not a photo."""
    for k in ("imageUrl", "image_url", "mediaUrl"):
        v = str(rt.get(k) or "").strip()
        if v.startswith("https://"):
            return v
    cands = [rt.get("attachment"), rt.get("attach"), rt.get("text")]
    for c in cands:
        if isinstance(c, str) and c.strip().startswith("{"):
            try:
                c = json.loads(c)
            except ValueError:
                continue
        if isinstance(c, dict):
            for k in ("url", "href", "hdUrl", "normalUrl", "thumb"):
                v = str(c.get(k) or "").strip()
                if v.startswith("https://"):
                    return v
    return ""


def anh_duoc_quote(conn_id: str, thread: str, md: dict) -> str:
    """Link of the photo a message QUOTES (replies to), or "" (0.141.0).

    Field report 2026-10-14: in a group someone quoted a product photo and tagged the bot to look at it; the bot only
    got the text and said it could not see the photo, so the owner's workaround was "send the photo, then tag the bot
    within 3 minutes". The quote carries the photo's message id (`replyTo.msgId`, Zalo's global id, the same id the
    photo was stored under when Javis read it), so the stored photo message gives the link. A link inside the quote
    payload is the fallback, for a photo sent before Javis started reading this account."""
    rt = (md or {}).get("replyTo")
    if not isinstance(rt, dict):
        return ""
    mid = str(_lay(rt, "msgId", "globalMsgId", "id", mac_dinh="") or "").strip()
    if mid:
        goc = conversations.tin_theo_id(KENH, str(conn_id), str(thread), mid)
        url = str((goc.get("metadata") or {}).get("image_url") or "").strip() if goc.get("message_type") == "image" else ""
        if url.startswith("https://"):
            return url
    return _link_trong_quote(rt)


# Files in a group (0.336.0). Owner report 2026-10-26: someone sent a PDF to a group, then tagged the bot to read it, and
# the bot answered it could not read PDFs: a file nobody addressed to the bot is never downloaded, so the tag that came
# next had no file. Same idea as bare photos (`_nho_anh_tron`): the file is remembered (only its Zalo link, nothing is
# downloaded) and handed to the sender's next message that calls the bot; a message that QUOTES a file gets that file.
BARE_FILE_TTL = 600         # seconds a bare group file waits for its sender to call the bot
BARE_FILE_MAX = 3           # files kept per sender (the newest)
_BARE_FILES: Dict[tuple, list] = {}     # (account, chat, sender) -> [(time, attachment)]


def remember_bare_file(conn_id: str, thread: str, sender: str, att, ts: Optional[float] = None) -> None:
    if not sender or not isinstance(att, dict) or not str(att.get("url") or "").startswith("https://"):
        return
    now = time.time()
    key = (str(conn_id), str(thread), str(sender))
    items = [x for x in _BARE_FILES.get(key, []) if now - x[0] < BARE_FILE_TTL]
    items.append((float(ts or now), dict(att)))
    _BARE_FILES[key] = items[-BARE_FILE_MAX:]
    if len(_BARE_FILES) > 500:
        for k in list(_BARE_FILES)[:250]:
            _BARE_FILES.pop(k, None)


def take_bare_files(conn_id: str, thread: str, sender: str, now: Optional[float] = None) -> list:
    """The sender's recent bare files in this group, oldest first, used up (a later call does not get them again)."""
    now = time.time() if now is None else now
    items = _BARE_FILES.pop((str(conn_id), str(thread), str(sender)), [])
    return [att for t, att in items if now - t < BARE_FILE_TTL]


def quoted_file(conn_id: str, thread: str, md: dict) -> list:
    """The file a message QUOTES (replies to), from the inbox row of that message: `[attachment]` or []."""
    rt = (md or {}).get("replyTo")
    if not isinstance(rt, dict):
        return []
    mid = str(_lay(rt, "msgId", "globalMsgId", "id", mac_dinh="") or "").strip()
    if not mid:
        return []
    goc = conversations.tin_theo_id(KENH, str(conn_id), str(thread), mid)
    att = (goc.get("metadata") or {}).get("attachment") if goc.get("message_type") == "file" else None
    return [dict(att)] if isinstance(att, dict) and str(att.get("url") or "").startswith("https://") else []


def dang_ky_bot(conn_id: str, tb: Any) -> None:
    _BOTS[str(conn_id)] = tb
    start()


def huy_dang_ky_bot(conn_id: str, tb: Any = None) -> None:
    cid = str(conn_id)
    if tb is None or _BOTS.get(cid) is tb:
        _BOTS.pop(cid, None)
        # KHÔNG xoá tin đang gom ở đây: lưu cài đặt bot cũng đi qua đây (start_bot -> stop_bot rồi
        # đăng ký lại ngay), xoá là khách vừa nhắn trong mấy giây đó không được trả lời. Bot tắt hẳn
        # thì `xa_hang_cho` tự bỏ hàng chờ khi không còn bot trực, và tin quá `TUOI_TOI_DA` cũng bị
        # bỏ, nên bật lại sau đó không giao tin cũ.
        _NONG.pop(cid, None)


def co_bot(conn_id: str) -> bool:
    return str(conn_id) in _BOTS


def _chuan(text: str) -> str:
    # Compared as Zalo shows it (0.413.0): a reply sent as "**85.000đ**" comes back as "85.000đ" with a bold style,
    # and must still be recognised as the bot's own echo, or the bot takes it for the owner and goes quiet.
    return " ".join(plain_text(str(text or "")).split())


# Zalo's own markup for a tag, e.g. `<a_mention href="zm://Profile/110413987_mention">@Minh</a_mention> Quý`.
# Field report 2026-10-19: a group reply reached Zalo with this markup as plain text, so the group saw code instead
# of a tag. The model copies it from messages that carry it, so it is stripped both ways: incoming (`chuan_hoa_tin`)
# and outgoing (`channels.zalo_personal.gui`), leaving "@Minh Quý" for the real tag (`--mention`) to find.
# Since 0.309.0 the stripping lives in `zalo_markup` (also used by the MCP pool for direct tool calls) and also
# removes broken fragments such as a leftover `href="zm://...">`.
from zalo_markup import plain_text, strip_mention_markup  # noqa: E402,F401


def ghi_da_gui(conn_id: str, thread: str, text: str) -> None:
    """Bot vừa gửi `text`: nhớ lại để vòng đọc nhận ra tiếng vọng của nó."""
    khoa = (str(conn_id), str(thread))
    now = time.time()
    ds = [x for x in _DA_GUI.get(khoa, []) if now - x[0] < ECHO_TTL]
    ds.append((now, _chuan(text)))
    _DA_GUI[khoa] = ds[-20:]
    if len(_DA_GUI) > 500:      # trần thô: thà quên một tiếng vọng còn hơn phình mãi
        for k in list(_DA_GUI)[:250]:
            _DA_GUI.pop(k, None)


def ghi_da_gui_anh(conn_id: str, thread: str, so: int = 1) -> None:
    """Bot is about to send `so` images: remember them so their echoes are not taken for the owner's hand.

    Since javis-zalo keeps the account's own messages in the live feed (flag `isSelf`), an image the bot sends comes
    back as an image "from the owner". It has no text to match, so without this the inbox shows it twice and the bot
    believes the owner just stepped in and goes quiet in that chat for TAY_IM seconds."""
    khoa = (str(conn_id), str(thread))
    now = time.time()
    ds = [x for x in _DA_GUI_ANH.get(khoa, []) if now - x < ECHO_TTL]
    ds.extend([now] * max(0, int(so or 0)))
    _DA_GUI_ANH[khoa] = ds[-20:]
    if len(_DA_GUI_ANH) > 500:
        for k in list(_DA_GUI_ANH)[:250]:
            _DA_GUI_ANH.pop(k, None)


def attach_echo_id(conn_id: str, ev: dict) -> bool:
    """The echo of a message this account sent came back with Zalo's id: give the inbox row of that message the id
    (0.334.0, `conversations.own_messages_without_id`). A customer's reaction names the message by it. Matched like
    the echo itself (same text, or one starts with the other: a long answer goes out in parts). Never raises."""
    msg_id = str((ev or {}).get("external_message_id") or "")
    if not msg_id:
        return False
    echo = _chuan((ev or {}).get("text"))
    try:
        for row in conversations.own_messages_without_id(KENH, str(conn_id), str(ev.get("external_chat_id") or ""),
                                                         time.time() - ECHO_TTL):
            sent = _chuan(row.get("text"))
            if echo and sent and (echo == sent or sent.startswith(echo[:80]) or echo.startswith(sent[:80])):
                return conversations.set_message_id(int(row["id"]), msg_id)
    except Exception as e:      # noqa: BLE001 - worst case a reaction to this message reads "a message"
        print(f"[zalo-personal] attaching a message id failed: {type(e).__name__}", file=sys.stderr)
    return False


_BOT_REACTIONS: Dict[tuple, list] = {}     # (account, chat) -> [(time, target message id, reaction name, bot name)]


def remember_bot_reaction(conn_id: str, thread: str, target_msg_id: str, name: str, bot_name: str) -> None:
    """The bot is about to put a reaction: remember it, so its echo is filed as the bot's, not the owner's."""
    key = (str(conn_id), str(thread))
    now = time.time()
    items = [x for x in _BOT_REACTIONS.get(key, []) if now - x[0] < ECHO_TTL]
    items.append((now, str(target_msg_id), str(name or ""), str(bot_name or "")))
    _BOT_REACTIONS[key] = items[-20:]
    if len(_BOT_REACTIONS) > 500:
        for k in list(_BOT_REACTIONS)[:250]:
            _BOT_REACTIONS.pop(k, None)


def _bot_reaction_echo(conn_id: str, thread: str, reaction) -> Optional[str]:
    """The bot's name when this account's reaction is one the bot just put (used up), else None."""
    r = reaction if isinstance(reaction, dict) else {}
    key = (str(conn_id), str(thread))
    now = time.time()
    items = [x for x in _BOT_REACTIONS.get(key, []) if now - x[0] < ECHO_TTL]
    for i, (_, target, name, bot) in enumerate(items):
        if target == str(r.get("target_msg_id") or "") and name == str(r.get("name") or ""):
            del items[i]
            _BOT_REACTIONS[key] = items
            return bot or "Bot"
    _BOT_REACTIONS[key] = items
    return None


def _la_vong_anh(conn_id: str, thread: str) -> bool:
    """One remembered image echo for this chat, used up. False when the bot sent none lately."""
    khoa = (str(conn_id), str(thread))
    now = time.time()
    ds = [x for x in _DA_GUI_ANH.get(khoa, []) if now - x < ECHO_TTL]
    if not ds:
        _DA_GUI_ANH.pop(khoa, None)
        return False
    _DA_GUI_ANH[khoa] = ds[1:]
    return True


def _la_tieng_vong(conn_id: str, thread: str, text: str, toi_thieu: int = 0) -> bool:
    if len(_chuan(text)) < toi_thieu:
        return False
    khoa = (str(conn_id), str(thread))
    now = time.time()
    ds = [x for x in _DA_GUI.get(khoa, []) if now - x[0] < ECHO_TTL]
    if not ds:
        _DA_GUI.pop(khoa, None)
        return False
    t = _chuan(text)
    for i, (_, gui) in enumerate(ds):
        # So bằng hoặc đầu-câu: Zalo có thể cắt/đổi chút ở đuôi tin dài.
        if t and gui and (t == gui or t.startswith(gui[:80]) or gui.startswith(t[:80])):
            del ds[i]
            _DA_GUI[khoa] = ds
            return True
    _DA_GUI[khoa] = ds
    return False


def tay_im_cua(conn_id: str) -> int:
    """Số giây bot của tài khoản này nhường sau khi chủ nhắn tay: cài đặt "Nhường khi bạn nhắn tay" của bot đang trực
    (0.172.0, 0 = không nhường), không có bot hay bot không khai thì `TAY_IM`."""
    tb = _BOTS.get(str(conn_id))
    fn = getattr(tb, "tay_im", None)
    if callable(fn):
        try:
            return max(0, int(fn()))
        except Exception:      # noqa: BLE001 - cấu hình hỏng thì giữ mặc định an toàn, không làm sập vòng đọc
            pass
    return TAY_IM


def yield_explicit(conn_id: str) -> bool:
    """True when the bot on duty for this account has an explicitly saved `nhuong_tay_phut` (0.172.0).

    Only then do groups get the newer yield logic (a direct tag is answered at once, other messages are held and
    released per person when the window ends). A bot that never set it keeps the pre-0.172.0 group behaviour: silent
    for the whole window, nothing held."""
    fn = getattr(_BOTS.get(str(conn_id)), "yield_explicit", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:      # noqa: BLE001 - a broken setting falls back to the old, quieter behaviour
            pass
    return False


def chu_vua_nhan_tay(conn_id: str, thread: str, now: Optional[float] = None) -> bool:
    """Chủ vừa tự tay nhắn cuộc chat này (trong `tay_im_cua` giây) - bot nhường. Bot đặt nhường 0 phút thì không bao giờ."""
    t = _TAY.get((str(conn_id), str(thread)))
    if not t:
        return False        # cheap path first: most chats never had a hand-typed message, skip reading the bot setting
    im = tay_im_cua(conn_id)
    return im > 0 and ((time.time() if now is None else now) - t) < im


def owner_typed_after(conn_id: str, thread: str, ts: float) -> bool:
    """True when the owner typed into this chat by hand after a customer message sent at `ts`. With a 0-minute yield
    the bot does not go quiet, but a customer message the owner already answered is still not answered again."""
    t = _TAY.get((str(conn_id), str(thread)))
    return bool(t) and float(t) > float(ts or 0)


def _giao_cho_bot(conn: dict, ev: dict) -> None:
    cid = str(conn.get("id") or "")
    tb = _BOTS.get(cid)
    if not tb or ev.get("sender_type") != "customer":
        return
    nhom = ev.get("chat_type") == "group"
    if (CHO_CHU_TRA_LOI > 0 and (not nhom or yield_explicit(cid))
            and chu_vua_nhan_tay(cid, str(ev.get("external_chat_id") or ""))):
        if nhom:
            # Nhóm (0.172.0, only when the bot's yield minutes were set explicitly): tin TAG thẳng nick hoặc trả lời
            # tin của nick thì trả lời ngay, không chờ chủ. A bot without the setting falls through to `_chay`, and
            # `Transport.xu_ly` stays silent for the whole window as before 0.172.0.
            tag, rep = nhan_dien_goi(cid, ev, ((ket_noi_theo_id(cid) or {}).get("label") or "",))
            if tag or rep:
                _chay(tb, ev)
                return
        _giu_cho_chu(cid, ev)       # chủ đang nói chuyện: chờ xem chủ có trả lời không (0.136.0)
        return
    if (cid, str(ev.get("external_chat_id") or "")) in _CHO_CHU:
        # Quãng nhường vừa hết mà cuộc chat còn tin đang giữ (chưa tới lượt xả): gộp tin mới vào đó để `xa_cho_chu`
        # trả lời MỘT lần cho tất cả, thay vì hai câu liền nhau (một cho tin cũ, một cho tin mới).
        _giu_cho_chu(cid, ev)
        return
    if ev.get("chat_type") == "private" and _cho_cua(tb, str(ev.get("external_chat_id") or "")) > 0:
        _xep_cho(cid, ev)
        return
    _chay(tb, ev)


def _cho_cua(tb: Any, thread: str) -> float:
    """Seconds this private chat must be quiet before the bot answers: the chat's own exception (0.172.0,
    `chatbot_store.ngoai_le_cua`) when it sets one, otherwise `CHO_KHACH_IM`. The exception must name this very
    account (`tb.account_id`, set by `chatbot_runtime.start_bot`). Personal Zalo only: no other channel gathers."""
    try:
        import chatbot_store
        cfg = (tb.cfg_fn() if getattr(tb, "cfg_fn", None) else None) or {}
        e = chatbot_store.ngoai_le_cua(cfg, {"chat_type": "private", "chat_id": thread,
                                             "account_id": str(getattr(tb, "account_id", "") or "")})
    except Exception:       # noqa: BLE001 - a broken bot record must not stop the read loop
        e = None
    if e and e.get("cho_giay") is not None:
        return float(e["cho_giay"])
    return CHO_KHACH_IM


def _chay(tb: Any, ev: dict) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    t = loop.create_task(tb.xu_ly(ev))
    _VIEC.add(t)
    t.add_done_callback(_VIEC.discard)


# ============================================================
# Chờ khách nhắn xong (0.128.0)
# ============================================================
# Yêu cầu của chủ nick (14/10/2026): khách hay nhắn một ý thành ba bốn tin liền ("Thầy ơi" / "cho em
# hỏi" / "lớp 9 còn chỗ không ạ"). Giao từng tin ngay thì bot đáp câu chào trước khi câu hỏi tới,
# rồi đáp tiếp từng mẩu: lộ ngay là máy. Người thật đọc hết rồi mới trả lời một lần.
#
# Cách làm: tin khách ở chat RIÊNG vào `_GOM` theo (tài khoản, cuộc chat). Sau mỗi lượt đọc thành
# công, cuộc chat nào có tin khách cuối đã cũ hơn `CHO_KHACH_IM` giây thì được giao MỘT lượt gộp
# (`gop_tin`), nối đúng khuôn hàng đợi của `bot_gateway`. Xả SAU một lượt đọc chứ không hẹn giờ:
# chỉ lượt đọc mới xác nhận được là khách thật sự chưa nhắn thêm gì.
#
# Vòng đọc 20 giây thì khách nhắn cuối nhịp có thể phải chờ tới 30 giây, nên tài khoản có tin khách
# chat riêng trong `NONG_GIAY` giây qua được đọc mỗi `NHIP_NHANH` giây (`_nhip_cua`). `zalo_get_messages`
# đọc bộ đệm của tiến trình MCP trên máy, không hỏi máy chủ Zalo, và chỉ tài khoản đang nóng đọc dày.
#
# NHÓM không gom: ở nhóm mỗi tin còn đi qua nhận diện tag và bộ phán xử (nhớ ngữ cảnh theo từng tin,
# đúng thứ tự giữa nhiều người), gộp tin của một người là đổi những thứ đó. Chế độ Tự đánh giá vẫn
# chờ `NHUONG_GIAY` như cũ.
CHO_KHACH_IM = 5        # giây khách phải im ở chat riêng trước khi bot trả lời; 0 = giao từng tin ngay như trước 0.128.0
MAX_GOM_TIN = 50        # trần số tin giữ cho một cuộc chat đang gom (người lạ dán cả trăm dòng thì không phình theo)
MAX_FILE_GOP = 5        # trần số file một lượt gộp mang theo để tải (gửi cả chục file thì lấy mấy file cuối)


def _xep_cho(conn_id: str, ev: dict, now: Optional[float] = None) -> None:
    """Đưa một tin khách chat riêng vào hàng chờ của cuộc chat đó."""
    now = time.time() if now is None else now
    # Giờ tin theo Zalo, nhưng không cho vượt giờ máy: đồng hồ máy chậm hơn Zalo thì tin "từ tương
    # lai" sẽ giữ cuộc chat chờ mãi.
    ts = min(float(ev.get("created_at") or now), now)
    if now - ts > TUOI_TOI_DA:
        return      # tin cũ của bộ đệm: `xu_ly` cũng bỏ, đừng để nó giữ tài khoản ở nhịp đọc dày
    o = _GOM.setdefault((str(conn_id), str(ev.get("external_chat_id") or "")), {"evs": [], "cuoi": 0.0})
    if len(o["evs"]) >= MAX_GOM_TIN:
        o["evs"][-1] = ev       # giữ mấy tin đầu (câu hỏi thật) và tin CUỐI (mã tin, giờ tin của lượt)
    else:
        o["evs"].append(ev)
    o["cuoi"] = max(float(o["cuoi"]), ts)
    _NONG[str(conn_id)] = now
    if _co_chu(ev):
        khoa = (str(conn_id), str(ev.get("external_chat_id") or ""))
        _SEQ[khoa] = _SEQ.get(khoa, 0) + 1


def _co_chu(ev: dict) -> bool:
    """Tin này sẽ thành CHỮ trong lượt gộp (tin chữ, hay ảnh có chú thích). Sticker, tiếng, file không tính:
    lượt gộp của chúng có thể không có chữ nên không bao giờ có lượt trả lời nối tiếp."""
    loai = ev.get("message_type")
    if loai == "text":
        return bool(str(ev.get("text") or "").strip())
    if loai == "image":
        return bool(conversations.chu_thich_anh(ev.get("text")))
    return False


def gop_tin(evs: List[dict]) -> dict:
    """Nhiều tin khách liền nhau của MỘT cuộc chat riêng -> một sự kiện cho `Transport.xu_ly`.

    Khung là tin CUỐI (mã tin để Hộp thư nhận ra tin đã có, giờ tin cho rào `TUOI_TOI_DA`). Chữ là
    các tin chữ và chú thích ảnh theo đúng thứ tự, nối bằng `bot_gateway.noi_tin` (cùng trần, cùng
    cách nối với tin gom lúc bot bận). Có ảnh thì lượt là tin ảnh, mang link ảnh MỚI NHẤT, nên "gửi
    ảnh rồi nhắn 'xem giúp em'" tới bot thành một câu hỏi kèm ảnh. File đi theo lượt trong
    `metadata.attachments` (tối đa `MAX_FILE_GOP` file mới nhất), nên "gửi file rồi nhắn 'xem giúp
    em'" cũng thành một câu hỏi kèm file; lượt chỉ có file là tin file. Tiếng, sticker chỉ tính là
    khách còn đang nhắn, không góp chữ. Cảm xúc khách thả (0.334.0) góp dòng mô tả của nó; lượt chỉ có cảm
    xúc là tin `reaction`.
    `metadata.gop` = số tin đã gộp: `xu_ly` lấy chữ nguyên như đã gộp, không bóc chú thích lại.
    `metadata.react_to` = mã tin khách cuối có nội dung, tin bot được thả cảm xúc vào ("" khi lượt chỉ có cảm xúc)."""
    import bot_gateway
    cuoi = evs[-1]
    phan: List[str] = []
    co_anh, link = False, ""
    video, video_msg = "", ""
    files: List[dict] = []
    react_to, react_to_cli = "", ""
    for e in evs:
        loai = e.get("message_type")
        if loai in ("text", "image", "file", "video") and e.get("external_message_id"):
            # The bot reacts to a message, never to a reaction.
            react_to = str(e["external_message_id"])
            react_to_cli = str((e.get("metadata") or {}).get("cliMsgId") or "")
        if loai == "file":
            att = (e.get("metadata") or {}).get("attachment")
            if isinstance(att, dict):
                files.append(att)
            continue
        if loai == "video":
            # 0.433.0: the latest clip rides along like a photo; its text is only the link, never the customer's words.
            v = str((e.get("metadata") or {}).get("video_url") or "")
            if v:
                video, video_msg = v, str(e.get("external_message_id") or "")
            continue
        if loai in ("text", "reaction"):
            # A reaction (0.334.0) reads as its describing line, in order with the messages around it.
            t = str(e.get("text") or "").strip()
        elif loai == "image":
            co_anh = True
            link = str((e.get("metadata") or {}).get("image_url") or "") or link
            t = conversations.chu_thich_anh(e.get("text"))
        else:
            continue
        if t:
            phan.append(t)
    md = {k: v for k, v in (cuoi.get("metadata") or {}).items() if k not in ("image_url", "attachment", "video_url")}
    if link:
        md["image_url"] = link
    if video:
        md["video_url"], md["video_msg"] = video, video_msg
    if files:
        md["attachments"] = files[-MAX_FILE_GOP:]
    md["gop"] = len(evs)
    md.pop("reaction", None)
    md["react_to"], md["react_to_cli"] = react_to, react_to_cli
    only_reactions = all(e.get("message_type") == "reaction" for e in evs)
    kieu = ("image" if co_anh else "reaction" if only_reactions else "video" if video and not phan and not files
            else "text" if phan or not files else "file")
    return dict(cuoi, message_type=kieu, text=bot_gateway.noi_tin(phan), metadata=md)


def xa_hang_cho(conn_id: str, luc: Optional[float] = None) -> int:
    """Giao cho bot những cuộc chat của tài khoản này mà khách đã im đủ `CHO_KHACH_IM` giây tính tới
    `luc` (mốc bắt đầu của lượt đọc vừa xong). Trả số lượt đã giao."""
    cid = str(conn_id)
    luc = time.time() if luc is None else luc
    tb = _BOTS.get(cid)
    n = 0
    for khoa in [k for k in _GOM if k[0] == cid]:
        o = _GOM.get(khoa) or {}
        if not tb:
            _GOM.pop(khoa, None)
            continue
        if luc - float(o.get("cuoi") or 0) < _cho_cua(tb, khoa[1]):
            continue
        _GOM.pop(khoa, None)
        evs = [e for e in o.get("evs") or []
               if luc - min(float(e.get("created_at") or luc), luc) <= TUOI_TOI_DA]
        if evs:
            _chay(tb, _dong_dau_seq(gop_tin(evs), khoa))
            n += 1
    return n


# ============================================================
# Câu trả lời đã cũ (0.172.0)
# ============================================================
# Ca thật 15/10/2026: phụ huynh nhắn cách nhau 8 đến 15 giây, bot soạn mất 8 đến 18 giây. Bot đợi đủ
# `CHO_KHACH_IM` giây rồi bắt đầu soạn; tin tiếp theo của khách tới LÚC ĐANG SOẠN, nên câu gửi đi lỗi thời
# ("chị gửi thêm số điện thoại" trong khi số vừa nhắn xong), rồi tin sau lại bị đáp thêm một lượt riêng.
#
# Cách làm: mỗi tin khách có chữ ở chat riêng tăng `_SEQ`; lượt gộp mang `seq_cuoi` lúc nó được giao. Soạn
# xong mà `_SEQ` đã lớn hơn `seq_cuoi` thì câu trả lời là cũ: KHÔNG gửi, KHÔNG vào Hộp thư như lời bot nói,
# chữ của khách trong lượt đó được giữ lại (`bo_do_gui`) để lượt kế tiếp, vốn đang chờ khoá cuộc chat, đọc
# cùng tin mới và trả lời MỘT lần (`lay_bo_do`). Tối đa `MAX_BO_DO` lần liền, để khách nhắn mãi không bao giờ
# nhận được câu nào.
MAX_BO_DO = 3           # số lần liền một cuộc chat được bỏ câu đã cũ; tới đó thì gửi dù khách còn nhắn thêm
BO_DO_TUOI = 300        # giây: chữ giữ lại quá cũ thì bỏ, không trộn vào một cuộc trò chuyện đã nguội


def _dong_dau_seq(ev: dict, khoa: tuple) -> dict:
    """Đóng dấu `seq_cuoi` (số tin khách có chữ đã thấy tới lúc giao lượt) vào lượt gộp chat riêng."""
    md = dict(ev.get("metadata") or {})
    md["seq_cuoi"] = _SEQ.get(khoa, 0)
    return dict(ev, metadata=md)


def co_tin_moi(conn_id: str, thread: str, seq_cuoi: int) -> bool:
    """Từ lúc lượt có dấu `seq_cuoi` được giao, khách có nhắn thêm chữ vào cuộc chat này không."""
    return _SEQ.get((str(conn_id), str(thread)), 0) > int(seq_cuoi)


def bo_do_gui(conn_id: str, thread: str, texts: List[str], n: int) -> None:
    """Giữ chữ của khách trong một lượt có câu trả lời đã bỏ, cho lượt kế tiếp đọc lại."""
    texts = [t for t in texts if str(t or "").strip()]
    if texts:
        _BO_DO[(str(conn_id), str(thread))] = {"texts": texts[-MAX_GOM_TIN:], "n": int(n), "luc": time.time()}


def lay_bo_do(conn_id: str, thread: str, now: Optional[float] = None) -> dict:
    """Lấy (và xoá) chữ khách của các câu trả lời đã bỏ của cuộc chat này; trống nếu không có hay đã nguội."""
    o = _BO_DO.pop((str(conn_id), str(thread)), None) or {}
    now = time.time() if now is None else now
    if not o or now - float(o.get("luc") or 0) > BO_DO_TUOI:
        return {}
    return o


# ============================================================
# Chủ chưa trả lời thì bot trả lời thay (0.136.0)
# ============================================================
# Yêu cầu của chủ nick (14/10/2026): "nếu tôi không rep sau 10 phút thì cứ tự động trả lời sao cho hợp lí nhất".
# Trước bản này, chủ vừa tự tay nhắn một chat thì bot nhường `TAY_IM` giây, và tin khách tới trong quãng đó bị
# bỏ hẳn: hết quãng nhường thì tin đã cũ quá `TUOI_TOI_DA` nên không bao giờ được trả lời. Ca thật: chủ nhắn
# "Mẹ nhắn tin gì vào đây đi" lúc 11:51, khách gửi file và ảnh lúc 11:52, không ai trả lời cả.
#
# Giờ tin khách CHAT RIÊNG tới lúc chủ đang nhường được GIỮ theo cuộc chat. Chủ nhắn tay hoặc gửi từ Hộp thư
# vào chat đó thì bỏ (chủ đã trả lời). Tin khách đầu tiên đã chờ đủ `CHO_CHU_TRA_LOI` giây mà chủ vẫn im thì
# giao cho bot MỘT lượt gộp, kèm một dòng ghi chú cho Agent biết khách đã chờ và khách gửi kèm gì (file,
# ảnh không chữ), để bot đáp hợp cảnh thay vì im vì tin không có chữ. Xả sau một lượt đọc thành công, như
# `xa_hang_cho`: chỉ lượt đọc mới xác nhận được là chủ chưa nhắn gì.
#
# 0.172.0 (chủ nick chốt 14/10/2026: "có nhắn tay thì 3 phút sau tin nhắn tay đó chủ động nhắn tiếp"): mốc chờ là
# TIN NHẮN TAY cuối của chủ cộng `tay_im_cua` (số phút nhường của bot), không phải tin khách đầu tiên. Groups get
# this only when the bot's yield minutes were saved explicitly (`yield_explicit`): a direct tag is answered at once,
# other messages are held until the window ends and then answered one turn per person, through the bot's group
# rules (judge, "reply when"). Without the setting groups stay silent for the whole window, as before 0.172.0.
# Hàng chờ chỉ nằm trong RAM: Javis khởi động lại thì mất, tệ nhất là một tin không được trả lời thay, không bao giờ
# là trả lời hai lần.
CHO_CHU_TRA_LOI = 600   # giây chờ chủ trả lời tin khách tới lúc chủ đang nhắn tay; 0 = tắt (bỏ tin như trước 0.136.0)
_CHO_CHU: Dict[tuple, dict] = {}    # (conn_id, thread) -> {"evs": [...], "dau": giờ tin khách đầu tiên chưa ai trả lời}


def _giu_cho_chu(conn_id: str, ev: dict, now: Optional[float] = None) -> None:
    """Giữ một tin khách chat riêng tới lúc chủ đang nhắn tay, chờ xem chủ có trả lời không."""
    now = time.time() if now is None else now
    ts = min(float(ev.get("created_at") or now), now)
    if now - ts > TUOI_TOI_DA:
        return      # tin cũ của bộ đệm lúc mới bật, như `_xep_cho`
    o = _CHO_CHU.setdefault((str(conn_id), str(ev.get("external_chat_id") or "")), {"evs": [], "dau": ts})
    if len(o["evs"]) >= MAX_GOM_TIN:
        o["evs"][-1] = ev
    else:
        o["evs"].append(ev)
    o["dau"] = min(float(o["dau"]), ts)


def bo_cho_chu(conn_id: str, thread: str) -> None:
    """Chủ (hoặc Hộp thư, kể cả lượt nhờ bot soạn) đã trả lời cuộc chat này: tin đang giữ không còn là việc của bot."""
    _CHO_CHU.pop((str(conn_id), str(thread)), None)


def _ten_kem(e: dict) -> str:
    """Tả ngắn một tin không phải chữ để Agent biết khách gửi gì."""
    loai = str(e.get("message_type") or "")
    md = e.get("metadata") or {}
    if loai == "image":
        return "một ảnh"
    if loai == "file":
        # Tên file nằm ở `metadata.attachment` (0.133.0, `zalo_attachments.normalize`).
        ten = str((md.get("attachment") or {}).get("name") or md.get("fileName") or e.get("text") or "").strip()
        return f"file {ten}" if ten and not ten.startswith("[") else "một file"
    return {"audio": "một tin thoại", "video": "một video", "sticker": "một sticker"}.get(loai, "một tin không phải chữ")


def gop_cho_chu(evs: List[dict], cho: int = 0, tay: float = 0) -> dict:
    """Các tin khách đã chờ chủ trả lời -> một lượt cho `Transport.xu_ly` (dựa trên `gop_tin`), thêm một dòng ghi chú:
    khách nhắn lúc nào, đã chờ bao lâu, gửi kèm gì. `metadata.sau_chu_im` cho `xu_ly` biết lượt này cũ là có chủ ý.

    File đi theo lượt như mọi lượt gộp (`metadata.attachments`): `xu_ly` tải về khi bot có quyền Được ghi và tự ghi
    kết quả (nội dung file, hay lý do không mở được) vào lượt, nên ghi chú ở đây chỉ kể tên, không đoán bot mở được
    hay không. Giờ theo múi giờ trong Cài đặt (`localefmt.tz`), không theo đồng hồ máy chủ (VPS thường chạy UTC).

    `cho` is the configured wait in seconds and `tay` the time of the owner's last hand-typed message: since 0.172.0
    the clock runs from that message, so the note says so instead of "has not answered after N minutes"."""
    ev = gop_tin(evs)
    kem = [_ten_kem(e) for e in evs
           if e.get("message_type") not in ("text", "image")
           or (e.get("message_type") == "image" and not conversations.chu_thich_anh(e.get("text")))]
    dau = min(float(e.get("created_at") or time.time()) for e in evs)
    phut = max(1, round((cho or CHO_CHU_TRA_LOI) / 60))
    from datetime import datetime
    gio = datetime.fromtimestamp(dau, localefmt.tz()).strftime("%H:%M")
    if tay:
        gio_tay = datetime.fromtimestamp(float(tay), localefmt.tz()).strftime("%H:%M")
        cho_chu = f"chủ nick nhắn tay lần cuối lúc {gio_tay} rồi {phut} phút không nhắn thêm gì nên tới lượt bạn"
    else:
        cho_chu = f"chủ nick chưa trả lời sau {phut} phút nên tới lượt bạn"
    ghi = (f"[Ghi chú của Javis, không phải lời khách: khách nhắn lúc {gio}, " + cho_chu
           + (f"; khách gửi kèm {', '.join(kem)}" if kem else "") + ".]")
    md = dict(ev.get("metadata") or {})
    md["sau_chu_im"] = True
    return dict(ev, text=(str(ev.get("text") or "").strip() + "\n" + ghi).strip(), metadata=md)


MAX_NGUOI_NHOM = 5     # nhóm: hết quãng nhường thì trả lời tối đa chừng này người (người nhắn sau cùng), mỗi người một lượt


def xa_cho_chu(conn_id: str, luc: Optional[float] = None) -> int:
    """Giao cho bot các cuộc chat của tài khoản này mà quãng nhường đã hết: đủ `tay_im_cua` giây tính từ TIN NHẮN TAY
    cuối của chủ (0.172.0, chủ nick chốt 14/10/2026: "có nhắn tay thì 3 phút sau tin nhắn tay đó chủ động nhắn tiếp").
    Chat riêng: một lượt gộp. Nhóm: mỗi người một lượt gộp, đi qua đúng luật nhóm của bot. Trả số lượt đã giao."""
    cid = str(conn_id)
    luc = time.time() if luc is None else luc
    khoas = [k for k in _CHO_CHU if k[0] == cid]
    if not khoas:
        return 0        # runs after every read cycle: nothing held means no need to read the bot setting
    tb = _BOTS.get(cid)
    # Chờ chủ đúng bằng quãng bot nhường (0.172.0: chủ đặt nhường 5 phút thì chờ 5 phút); không khai thì `CHO_CHU_TRA_LOI`.
    cho = tay_im_cua(cid) or CHO_CHU_TRA_LOI
    n = 0
    for khoa in khoas:
        o = _CHO_CHU.get(khoa) or {}
        if not tb or CHO_CHU_TRA_LOI <= 0:
            _CHO_CHU.pop(khoa, None)
            continue
        tay = _TAY.get(khoa) or 0
        if luc - float(tay or o.get("dau") or luc) < cho:
            continue
        _CHO_CHU.pop(khoa, None)
        # Chủ nhắn sau tin nào thì tin đó đã có người đáp; tin quá cũ (đồng hồ lệch, hàng chờ kẹt) thì thôi.
        evs = [e for e in o.get("evs") or [] if float(e.get("created_at") or 0) > tay]
        evs = [e for e in evs if luc - float(e.get("created_at") or luc) <= cho + TUOI_TOI_DA]
        if not evs:
            continue
        if evs[-1].get("chat_type") == "group":
            theo_nguoi: Dict[str, list] = {}
            for e in evs:
                theo_nguoi.setdefault(str(e.get("sender_id") or ""), []).append(e)
            # Người nhắn sau cùng đứng sau trong dict (Python giữ thứ tự chèn theo lần đầu): sắp lại theo tin cuối.
            nhom = sorted(theo_nguoi.values(), key=lambda ds: float(ds[-1].get("created_at") or 0))[-MAX_NGUOI_NHOM:]
            for ds in nhom:
                _chay(tb, gop_cho_chu(ds, cho, tay))
                n += 1
        else:
            # Chat riêng: đóng dấu số thứ tự để lượt này nhận ra khách nhắn thêm trong lúc bot soạn (`_dong_dau_seq`).
            _chay(tb, _dong_dau_seq(gop_cho_chu(evs, cho, tay), khoa))
            n += 1
    return n


def _nhip_cua(conn_id: str, now: Optional[float] = None) -> int:
    """Nhịp đọc kế tiếp của một tài khoản: dày khi có cuộc chat đang chờ khách nhắn xong hoặc vừa có
    tin khách chat riêng, thường thì `NHIP`. Chỉ khi có bot trực và đang bật chờ."""
    cid = str(conn_id)
    if cid not in _BOTS:
        return NHIP
    # A chat waiting in `_GOM` reads fast even with CHO_KHACH_IM = 0: it can only be there through its own
    # per-chat wait (0.172.0, `_cho_cua`).
    if any(k[0] == cid for k in _GOM):
        return NHIP_NHANH
    now = time.time() if now is None else now
    if CHO_KHACH_IM > 0 and now - float(_NONG.get(cid) or 0) < NONG_GIAY:
        return NHIP_NHANH
    return NHIP


def _nhip_vong() -> int:
    """Vòng ngủ bao lâu: một nhịp dày nếu có tài khoản nào đang nóng, không thì `NHIP`."""
    return min([NHIP] + [_nhip_cua(cid) for cid in list(_BOTS)])
