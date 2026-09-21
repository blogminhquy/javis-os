"""Adapter kênh Zalo CÁ NHÂN cho Hộp thư hội thoại: đọc tin mới từ MCP `zalo-agent-cli` rồi
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

Chưa có ở V1: bot tự trả lời qua Zalo cá nhân (gửi tin dưới danh tính CHỦ là chuyện phải cân
nhắc riêng), và tải media. Tin ảnh/file ghi loại tin kèm mô tả, không tải về.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any, Dict, List, Optional

import config as cfgmod
import conversations

CONNECTOR_ID = "zalo"
KENH = "zalo_personal"
NHIP = 20               # giây giữa hai lần đọc
NHIP_LOI = 90           # nghỉ dài hơn khi một tài khoản vừa lỗi (MCP chết, chưa đăng nhập)
LIMIT = 100             # tin mỗi lần đọc
TEN_TTL = 300           # giây giữ bảng tên thread (zalo_list_threads) trước khi hỏi lại
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
        return {"ok": False, "error": "thiếu id kết nối"}
    if not any(c["id"] == cid for c in _ket_noi()):
        return {"ok": False, "error": "không có kết nối Zalo nào id đó (hoặc đang tắt ở trang Kết nối)"}
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
        "metadata": {k: msg.get(k) for k in ("replyTo", "mentions", "mediaUrl", "url", "fileName")
                     if msg.get(k) not in (None, "")},
    }


# ============================================================
# Vòng đọc
# ============================================================
async def _nap_ten(conn: dict, tt: dict) -> Dict[str, dict]:
    """Bảng threadId -> {name, type}. Hỏi lại sau TEN_TTL giây, hỏng thì giữ bảng cũ."""
    if tt.get("ten") is not None and time.time() - float(tt.get("ten_ts") or 0) < TEN_TTL:
        return tt["ten"]
    try:
        d = await _goi(conn, "zalo_list_threads", {"limit": 200})
        ds = d.get("threads") if isinstance(d, dict) else d
        bang: Dict[str, dict] = dict(tt.get("ten") or {})
        for t in (ds or []):
            if not isinstance(t, dict):
                continue
            tid = str(_lay(t, "threadId", "id", mac_dinh="") or "")
            if tid:
                bang[tid] = {"name": str(t.get("name") or "")[:120], "type": str(t.get("type") or "")}
        if len(bang) > MAX_TEN:
            bang = dict(list(bang.items())[-MAX_TEN:])
        tt["ten"], tt["ten_ts"] = bang, time.time()
    except Exception as e:
        tt["ten_ts"] = time.time()      # đừng hỏi dồn dập khi đang hỏng
        if tt.get("ten") is None:
            tt["ten"] = {}
        print(f"[zalo-personal {conn.get('label')}] list_threads: {e}", file=sys.stderr)
    return tt["ten"]


async def doc_mot_lan(conn: dict) -> dict:
    """Một lượt đọc cho một tài khoản. Trả {"moi": n, "trung": n} hoặc ném lỗi."""
    tt = _TT.setdefault(conn["id"], {})
    khoa_cursor = f"{KENH}:{conn['id']}:cursor"
    cursor = conversations.doc_trang_thai(khoa_cursor, "")
    args: Dict[str, Any] = {"limit": LIMIT}
    if cursor:
        args["cursor"] = cursor
    d = await _goi(conn, "zalo_get_messages", args)
    if not isinstance(d, dict):
        d = {"messages": d if isinstance(d, list) else []}
    tin = d.get("messages") or []
    ten = await _nap_ten(conn, tt) if tin else (tt.get("ten") or {})
    moi = trung = 0
    for m in tin:
        ev = chuan_hoa_tin(conn, m, ten)
        if not ev:
            continue
        kq = conversations.ghi_su_kien(ev)
        if kq.get("ok"):
            if kq.get("trung"):
                trung += 1
            else:
                moi += 1
    nc = _lay(d, "nextCursor", "next_cursor", "cursor", mac_dinh="")
    if nc:
        conversations.ghi_trang_thai(khoa_cursor, str(nc))
    tt["lan_cuoi"] = time.time()
    tt["loi"] = ""
    tt["so_tin"] = int(tt.get("so_tin") or 0) + moi
    return {"moi": moi, "trung": trung}


async def _vong() -> None:
    print("[zalo-personal] vòng đọc bắt đầu", file=sys.stderr)
    while not _stop:
        try:
            cfg = _cau_hinh()
            bat_ids = {k for k, v in cfg.items() if v}
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
