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

Chưa có: tải media. Tin ảnh/file ghi loại tin kèm mô tả, không tải về, và bot không trả lời chúng.
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
    text = _lay(msg, "text", "content", "msg", "message", mac_dinh="")
    if isinstance(text, dict):
        text = _lay(text, "text", "title", "description", "href", mac_dinh="")
    text = str(text or "")
    if loai != "text" and not text.strip():
        text = f"[{conversations.KENH_NHAN[KENH]}: khách gửi {loai}]"
    vao_nhom = _su_kien_vao_nhom(msg) if nhom else None
    if vao_nhom is not None:
        ten_moi = sender_name or sender_id
        text = localefmt.chu(f"[{ten_moi} vừa vào nhóm]", f"[{ten_moi} joined the group]")
    cua_minh = _la_cua_minh(msg)
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
        "metadata": dict({k: msg.get(k) for k in ("replyTo", "mentions", "mediaUrl", "url", "fileName")
                          if msg.get(k) not in (None, "")},
                         **({"chua_ro_loai": True} if _chua_ro_loai(msg, ten) else {}),
                         **({"member_join": vao_nhom} if vao_nhom is not None else {}),
                         **({"image_url": _link_anh(msg)} if loai == "image" and _link_anh(msg) else {})),
    }


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
    for m in tin:
        ev = chuan_hoa_tin(conn, m, ten)
        if not ev:
            continue
        if ev["sender_type"] == "human":
            _hoc_danh_tinh(conn["id"], m)
            # Tin chủ gửi đi. Tiếng vọng của câu BOT vừa gửi thì bỏ (bot đã tự ghi câu đó vào
            # Hộp thư, ghi thêm lần nữa là hiện hai lần, lần hai mang nhãn "người thật"). Còn
            # lại là chủ tự tay nhắn: nhớ giờ để bot nhường cuộc chat đó.
            if _la_tieng_vong(conn["id"], ev["external_chat_id"], ev["text"]):
                trung += 1
                continue
            _TAY[(conn["id"], ev["external_chat_id"])] = float(ev.get("created_at") or time.time())
        elif _la_tieng_vong(conn["id"], ev["external_chat_id"], ev["text"], TIENG_VONG_TOI_THIEU):
            # Ví dụ trong tài liệu của MCP không có cờ "tin của chính mình", nên câu bot vừa gửi
            # có thể quay về như tin của một KHÁCH. Để lọt thì trong nhóm bot sẽ tự trả lời chính
            # nó, và Hộp thư ghi câu bot nói thành tin khách. Chỉ áp cho tin đủ dài: "Dạ" hay "ok"
            # khách nói trùng câu bot vừa nói là chuyện thường, còn một đoạn dài y hệt thì là vọng.
            trung += 1
            continue
        kq = conversations.ghi_su_kien(ev)
        if kq.get("ok"):
            if kq.get("trung"):
                trung += 1
            else:
                moi += 1
                _giao_cho_bot(conn, ev)
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
    return {"moi": moi, "trung": trung}


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
                    if time.time() < float(tt.get("nghi_toi") or 0):
                        continue
                    try:
                        await doc_mot_lan(conn)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        tt["loi"] = f"{type(e).__name__}: {e}"[:300]
                        tt["nghi_toi"] = time.time() + NHIP_LOI
                        print(f"[zalo-personal {conn.get('label')}] {tt['loi']}", file=sys.stderr)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[zalo-personal vòng] {type(e).__name__}: {e}", file=sys.stderr)
        try:
            await asyncio.sleep(NHIP)
        except asyncio.CancelledError:
            raise
    print("[zalo-personal] vòng đọc dừng", file=sys.stderr)


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


def trang_thai() -> dict:
    return {"dang_chay": bool(_task and not _task.done()), "nhip": NHIP,
            "tai_khoan": tai_khoan()}


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
_TAY: Dict[tuple, float] = {}       # (conn_id, thread) -> giờ tin chủ tự nhắn gần nhất
_VIEC: set = set()                  # giữ tham chiếu task đang chạy, kẻo bị thu gom giữa chừng
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


def dang_ky_bot(conn_id: str, tb: Any) -> None:
    _BOTS[str(conn_id)] = tb
    start()


def huy_dang_ky_bot(conn_id: str, tb: Any = None) -> None:
    cid = str(conn_id)
    if tb is None or _BOTS.get(cid) is tb:
        _BOTS.pop(cid, None)


def co_bot(conn_id: str) -> bool:
    return str(conn_id) in _BOTS


def _chuan(text: str) -> str:
    return " ".join(str(text or "").split())


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


def chu_vua_nhan_tay(conn_id: str, thread: str, now: Optional[float] = None) -> bool:
    """Chủ vừa tự tay nhắn cuộc chat này (trong `TAY_IM` giây) - bot nhường."""
    t = _TAY.get((str(conn_id), str(thread)))
    return bool(t) and ((time.time() if now is None else now) - t) < TAY_IM


def _giao_cho_bot(conn: dict, ev: dict) -> None:
    tb = _BOTS.get(str(conn.get("id") or ""))
    if not tb or ev.get("sender_type") != "customer":
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    t = loop.create_task(tb.xu_ly(ev))
    _VIEC.add(t)
    t.add_done_callback(_VIEC.discard)
