"""Kho hội thoại KHÁCH HÀNG (Conversation DB) - xương sống của Chatbot V2 / Hộp thư hội thoại.

Mọi tin nhắn khách gửi tới một bot chuyên trách (Telegram, Zalo Bot) hoặc tới tài khoản Zalo
cá nhân đã nối đều được các adapter kênh chuẩn hoá về MỘT sự kiện chung rồi đổ vào đây:

    Channel Account  ->  Customer  ->  Conversation  ->  Message

Vì sao là một kho RIÊNG chứ không đọc từ `sessions` (kho phiên chat):

  - Kho phiên xoay quanh PHIÊN của một engine; ở đó khách chỉ là một chuỗi nằm trong khoá
    phiên (`bot:<id>:<chat>`). Hộp thư cần một thực thể KHÁCH HÀNG xuyên suốt các kênh, biết
    kênh nào, ai gửi, tin nào là tin khách, tin nào là tin bot hay tin người thật - kho phiên
    không có chỗ cho những cột đó, và thêm vào bảng dùng chung chỉ để phục vụ một tính năng là
    cách làm bảng phình ra không kiểm soát.
  - Zalo cá nhân KHÔNG đi qua engine (tin đọc từ MCP rồi lưu thẳng), nên không có phiên nào.
  - Đây là nền cho CRM, tự động hoá và phân tích về sau: schema cố ý để sẵn `tags`, `note`,
    `metadata` để gói nâng cao cắm vào mà không phải đập lại.

Ba luật của kho:

  1. **Chỉ lưu từ lúc kênh được nối**, không đồng bộ lịch sử cũ. Text là dữ liệu chính; file,
     ảnh, tiếng chỉ giữ mô tả và đường dẫn tạm (media dọn theo hạn riêng, xem `media_gc`).
  2. **Ghi không bao giờ làm gãy lượt trả lời khách.** Mọi lỗi ở đây nuốt vào stderr.
  3. **Chống trùng theo id tin của kênh** (`external_message_id`): adapter đọc lại cùng một
     tin (poll trùng, khởi động lại) không sinh hai dòng.

Tên file cố ý KHÔNG phải `conversations.db`: tên đó đã thuộc về kho phiên (`sessions.py`).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import STATE_DIR

DB_PATH = STATE_DIR / "customer_conversations.sqlite3"

# Kênh mà kho hiểu. Adapter mới chỉ cần chuẩn hoá về sự kiện chung và dùng một giá trị ở đây.
# Kênh kho hiểu = SỔ ĐĂNG KÝ KÊNH (server/channels). Trước 0.61.0 danh sách này chép tay ở đây
# (kèm vài kênh "chừa chỗ" chưa có adapter); nay thêm kênh là thêm một module ở sổ, kho tự nhận.
import channels as _channels   # noqa: E402  (nhẹ: sổ không kéo httpx hay MCP lúc import)

KENH = _channels.ids()
KENH_NHAN = _channels.nhan_theo_id()
NGUOI_GUI = ("customer", "ai", "human", "system")
LOAI_TIN = ("text", "image", "file", "audio", "video", "sticker", "other")
CHE_DO = ("ai", "human", "waiting", "closed")
CHE_DO_DEFAULT = "ai"

MAX_CHU = 8_000          # trần độ dài một tin lưu lại
MAX_TEN = 120
MAX_DANH_SACH = 200      # trần một trang danh sách hội thoại
MAX_TIN_MOT_LAN = 500    # trần một trang tin nhắn

_SCHEMA = """
CREATE TABLE IF NOT EXISTS channel_accounts(
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    external_account_id TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    bot_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS customers(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_account_id TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    avatar_url TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    note TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(channel_account_id, external_user_id)
);
CREATE TABLE IF NOT EXISTS conversations(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_account_id TEXT NOT NULL,
    customer_id INTEGER,
    bot_id TEXT NOT NULL DEFAULT '',
    external_chat_id TEXT NOT NULL,
    chat_type TEXT NOT NULL DEFAULT 'private',
    title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    mode TEXT NOT NULL DEFAULT 'ai',
    last_message TEXT NOT NULL DEFAULT '',
    last_message_at REAL,
    last_sender_type TEXT NOT NULL DEFAULT '',
    unread_count INTEGER NOT NULL DEFAULT 0,
    message_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(channel_account_id, external_chat_id)
);
CREATE INDEX IF NOT EXISTS ix_conv_last ON conversations(last_message_at);
CREATE INDEX IF NOT EXISTS ix_conv_bot ON conversations(bot_id, last_message_at);
CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    external_message_id TEXT NOT NULL DEFAULT '',
    sender_type TEXT NOT NULL,
    sender_id TEXT NOT NULL DEFAULT '',
    sender_name TEXT NOT NULL DEFAULT '',
    message_type TEXT NOT NULL DEFAULT 'text',
    text TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_msg_conv ON messages(conversation_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_msg_ext
    ON messages(conversation_id, external_message_id) WHERE external_message_id != '';
CREATE TABLE IF NOT EXISTS sync_state(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at REAL NOT NULL
);
"""

_lock = threading.RLock()
_db: Optional[sqlite3.Connection] = None
_db_path: Optional[Path] = None


# ============================================================
# Kết nối
# ============================================================
def _conn() -> sqlite3.Connection:
    """Mở (một lần) kết nối tới kho. Đường dẫn tính lúc gọi để test đổi STATE_DIR được."""
    global _db, _db_path
    with _lock:
        path = Path(DB_PATH)
        if _db is not None and _db_path == path:
            return _db
        if _db is not None:
            try:
                _db.close()
            except Exception:
                pass
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=5000")
        db.executescript(_SCHEMA)
        db.commit()
        _db, _db_path = db, path
        return db


def close() -> None:
    global _db, _db_path
    with _lock:
        if _db is not None:
            try:
                _db.close()
            except Exception:
                pass
        _db, _db_path = None, None


def _now() -> float:
    return time.time()


def _s(v: Any, tran: int = MAX_CHU) -> str:
    return str(v if v is not None else "")[:tran]


def _json(v: Any) -> str:
    try:
        return json.dumps(v if v is not None else {}, ensure_ascii=False)
    except Exception:
        return "{}"


def _loads(s: Any, mac_dinh):
    try:
        return json.loads(s) if s else mac_dinh
    except Exception:
        return mac_dinh


def _row(r) -> dict:
    return dict(r) if r is not None else {}


# ============================================================
# Sự kiện chuẩn (normalized event) - khế ước chung cho MỌI kênh
# ============================================================
def chuan_hoa(ev: dict) -> dict:
    """Ép một sự kiện adapter gửi vào về đúng khuôn, điền mặc định, cắt trần.

    Khuôn:
        channel              một trong KENH
        account_id           id tài khoản kênh (bot_id với bot chuyên trách, id kết nối với
                             Zalo cá nhân)
        account_name         tên hiển thị tài khoản (tuỳ chọn)
        bot_id               bot chuyên trách xử lý (rỗng nếu không có bot)
        external_chat_id     id cuộc chat phía kênh (chat_id Telegram, threadId Zalo)
        chat_type            private | group
        chat_title           tên nhóm (tuỳ chọn)
        sender_type          customer | ai | human | system
        sender_id            id người gửi phía kênh (khách) - rỗng với ai/human/system
        sender_name          tên người gửi
        message_type         text | image | file | audio | video | sticker | other
        text                 nội dung chữ (hoặc mô tả media)
        external_message_id  id tin phía kênh, dùng chống trùng (tuỳ chọn)
        created_at           epoch giây (mặc định: bây giờ)
        metadata             dict tuỳ ý (đường dẫn file tạm, tên file, ...)

    Không ném lỗi với dữ liệu thiếu: sự kiện thiếu `channel`/`external_chat_id` mới bị từ chối
    (trả về dict có `loi`), vì thiếu hai thứ đó thì không biết xếp tin vào đâu.
    """
    ev = dict(ev or {})
    kenh = _s(ev.get("channel"), 32).strip().lower()
    chat = _s(ev.get("external_chat_id"), 200).strip()
    if kenh not in KENH:
        return {"loi": f"kênh '{kenh}' không nằm trong danh sách kho hiểu"}
    if not chat:
        return {"loi": "thiếu external_chat_id"}
    sender_type = _s(ev.get("sender_type"), 16).strip().lower() or "customer"
    if sender_type not in NGUOI_GUI:
        sender_type = "system"
    loai = _s(ev.get("message_type"), 16).strip().lower() or "text"
    if loai not in LOAI_TIN:
        loai = "other"
    chat_type = _s(ev.get("chat_type"), 16).strip().lower() or "private"
    chat_type = "group" if chat_type.startswith("group") or chat_type == "supergroup" else "private"
    try:
        ts = float(ev.get("created_at") or 0) or _now()
    except (TypeError, ValueError):
        ts = _now()
    account_id = _s(ev.get("account_id"), 120).strip() or "default"
    meta = ev.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    return {
        "channel": kenh,
        "account_id": account_id,
        "account_name": _s(ev.get("account_name"), MAX_TEN).strip(),
        "bot_id": _s(ev.get("bot_id"), 64).strip(),
        "external_chat_id": chat,
        "chat_type": chat_type,
        "chat_title": _s(ev.get("chat_title"), MAX_TEN).strip(),
        "sender_type": sender_type,
        "sender_id": _s(ev.get("sender_id"), 200).strip(),
        "sender_name": _s(ev.get("sender_name"), MAX_TEN).strip(),
        "message_type": loai,
        "text": _s(ev.get("text")),
        "external_message_id": _s(ev.get("external_message_id"), 200).strip(),
        "created_at": ts,
        "metadata": meta,
    }


def _tai_khoan_id(kenh: str, account_id: str) -> str:
    return f"{kenh}:{account_id}"


def ghi_su_kien(ev: dict) -> dict:
    """Đổ MỘT sự kiện chuẩn vào kho: tìm/tạo tài khoản kênh, khách, hội thoại rồi thêm tin.

    Trả về {"ok": True, "conversation_id", "message_id", "customer_id", "trung": bool}.
    Tin trùng `external_message_id` trong cùng hội thoại thì `trung=True` và không ghi gì.
    Lỗi trả {"ok": False, "loi": ...} và KHÔNG ném: người gọi là lượt trả lời khách.
    """
    e = chuan_hoa(ev)
    if e.get("loi"):
        return {"ok": False, "loi": e["loi"]}
    now = _now()
    ts = e["created_at"]
    tk_id = _tai_khoan_id(e["channel"], e["account_id"])
    try:
        with _lock:
            db = _conn()
            db.execute("BEGIN IMMEDIATE")
            try:
                # 1. Tài khoản kênh
                db.execute(
                    "INSERT INTO channel_accounts(id, channel, external_account_id, display_name,"
                    " bot_id, status, created_at, updated_at) VALUES(?,?,?,?,?,'active',?,?)"
                    " ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,"
                    " display_name=CASE WHEN excluded.display_name != '' THEN excluded.display_name"
                    " ELSE channel_accounts.display_name END,"
                    " bot_id=CASE WHEN excluded.bot_id != '' THEN excluded.bot_id"
                    " ELSE channel_accounts.bot_id END",
                    (tk_id, e["channel"], e["account_id"], e["account_name"], e["bot_id"], now, now))

                # 2. Khách: chỉ khi tin do KHÁCH gửi. Chat riêng không có sender_id thì lấy
                # chính id cuộc chat làm id khách (Telegram: chat riêng có chat_id == user id).
                customer_id = None
                if e["sender_type"] == "customer":
                    uid = e["sender_id"] or (e["external_chat_id"] if e["chat_type"] == "private" else "")
                    if uid:
                        db.execute(
                            "INSERT INTO customers(channel_account_id, external_user_id, name,"
                            " created_at, updated_at) VALUES(?,?,?,?,?)"
                            " ON CONFLICT(channel_account_id, external_user_id) DO UPDATE SET"
                            " updated_at=excluded.updated_at,"
                            " name=CASE WHEN excluded.name != '' THEN excluded.name ELSE customers.name END",
                            (tk_id, uid, e["sender_name"], now, now))
                        customer_id = db.execute(
                            "SELECT id FROM customers WHERE channel_account_id=? AND external_user_id=?",
                            (tk_id, uid)).fetchone()[0]

                # 3. Hội thoại
                tieu_de = e["chat_title"] or (e["sender_name"] if e["chat_type"] == "private"
                                                and e["sender_type"] == "customer" else "")
                db.execute(
                    "INSERT INTO conversations(channel_account_id, customer_id, bot_id,"
                    " external_chat_id, chat_type, title, created_at, updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(channel_account_id, external_chat_id) DO UPDATE SET"
                    " updated_at=excluded.updated_at,"
                    " customer_id=COALESCE(conversations.customer_id, excluded.customer_id),"
                    " bot_id=CASE WHEN excluded.bot_id != '' THEN excluded.bot_id ELSE conversations.bot_id END,"
                    " title=CASE WHEN excluded.title != '' THEN excluded.title ELSE conversations.title END",
                    (tk_id, customer_id, e["bot_id"], e["external_chat_id"], e["chat_type"],
                     tieu_de, now, now))
                conv = db.execute(
                    "SELECT id, unread_count, message_count FROM conversations"
                    " WHERE channel_account_id=? AND external_chat_id=?",
                    (tk_id, e["external_chat_id"])).fetchone()
                conv_id = int(conv["id"])

                # 4. Tin - chống trùng theo id tin của kênh
                if e["external_message_id"]:
                    cu = db.execute(
                        "SELECT id FROM messages WHERE conversation_id=? AND external_message_id=?",
                        (conv_id, e["external_message_id"])).fetchone()
                    if cu:
                        db.execute("COMMIT")
                        return {"ok": True, "trung": True, "conversation_id": conv_id,
                                "message_id": int(cu["id"]), "customer_id": customer_id}
                cur = db.execute(
                    "INSERT INTO messages(conversation_id, external_message_id, sender_type,"
                    " sender_id, sender_name, message_type, text, metadata_json, created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (conv_id, e["external_message_id"], e["sender_type"], e["sender_id"],
                     e["sender_name"], e["message_type"], e["text"], _json(e["metadata"]), ts))
                msg_id = int(cur.lastrowid)

                # 5. Cập nhật hội thoại: tin cuối, số tin, chưa đọc (chỉ đếm tin KHÁCH)
                tom = e["text"].strip().replace("\n", " ")[:200] or f"[{e['message_type']}]"
                them_chua_doc = 1 if e["sender_type"] == "customer" else 0
                db.execute(
                    "UPDATE conversations SET last_message=?, last_message_at=?, last_sender_type=?,"
                    " unread_count=unread_count+?, message_count=message_count+1, updated_at=?"
                    " WHERE id=?",
                    (tom, ts, e["sender_type"], them_chua_doc, now, conv_id))
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return {"ok": True, "trung": False, "conversation_id": conv_id, "message_id": msg_id,
                "customer_id": customer_id}
    except Exception as ex:
        print(f"[conversations] ghi lỗi: {type(ex).__name__}: {ex}", file=sys.stderr)
        return {"ok": False, "loi": f"{type(ex).__name__}: {ex}"}


# ============================================================
# Đọc
# ============================================================
def _conv_public(r: dict) -> dict:
    d = dict(r)
    d["metadata"] = _loads(d.pop("metadata_json", "{}"), {})
    d["channel_label"] = KENH_NHAN.get(d.get("channel") or "", d.get("channel") or "")
    if not d.get("title"):
        d["title"] = d.get("customer_name") or d.get("external_chat_id") or ""
    return d


def danh_sach(channel: str = "", bot_id: str = "", account_id: str = "", q: str = "",
              mode: str = "", limit: int = 50, offset: int = 0) -> List[dict]:
    """Danh sách hội thoại, MỚI NHẤT TRƯỚC, kèm tên khách và kênh.

    `q` tìm theo tên khách, tiêu đề, id chat, tin cuối (LIKE, không phân biệt hoa thường).
    """
    n = max(1, min(int(limit or 50), MAX_DANH_SACH))
    o = max(0, int(offset or 0))
    where, args = [], []
    if channel:
        where.append("a.channel=?"); args.append(str(channel))
    if bot_id:
        where.append("c.bot_id=?"); args.append(str(bot_id))
    if account_id:
        where.append("c.channel_account_id=?"); args.append(str(account_id))
    if mode:
        where.append("c.mode=?"); args.append(str(mode))
    if q:
        like = f"%{str(q).strip()}%"
        where.append("(k.name LIKE ? OR c.title LIKE ? OR c.external_chat_id LIKE ? OR c.last_message LIKE ?)")
        args += [like, like, like, like]
    sql = (
        "SELECT c.*, a.channel AS channel, a.display_name AS account_name,"
        " k.name AS customer_name, k.external_user_id AS customer_external_id"
        " FROM conversations c"
        " JOIN channel_accounts a ON a.id=c.channel_account_id"
        " LEFT JOIN customers k ON k.id=c.customer_id"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY COALESCE(c.last_message_at, c.updated_at) DESC, c.id DESC LIMIT ? OFFSET ?"
    )
    args += [n, o]
    with _lock:
        rows = _conn().execute(sql, args).fetchall()
    return [_conv_public(_row(r)) for r in rows]


def chi_tiet(conversation_id: int) -> Optional[dict]:
    with _lock:
        r = _conn().execute(
            "SELECT c.*, a.channel AS channel, a.display_name AS account_name,"
            " k.name AS customer_name, k.external_user_id AS customer_external_id,"
            " k.tags_json AS customer_tags_json, k.note AS customer_note"
            " FROM conversations c JOIN channel_accounts a ON a.id=c.channel_account_id"
            " LEFT JOIN customers k ON k.id=c.customer_id WHERE c.id=?",
            (int(conversation_id),)).fetchone()
    if not r:
        return None
    d = _conv_public(_row(r))
    d["customer_tags"] = _loads(d.pop("customer_tags_json", "[]"), [])
    return d


def tin_nhan(conversation_id: int, limit: int = 100, before_id: int = 0) -> List[dict]:
    """Tin của một hội thoại, CŨ TRƯỚC MỚI SAU trong cửa sổ trả về (cửa sổ lấy từ cuối lên).

    `before_id` > 0: lấy các tin CŨ HƠN id đó (cuộn ngược để xem thêm).
    """
    n = max(1, min(int(limit or 100), MAX_TIN_MOT_LAN))
    args: list = [int(conversation_id)]
    sql = "SELECT * FROM messages WHERE conversation_id=?"
    if before_id and int(before_id) > 0:
        sql += " AND id<?"; args.append(int(before_id))
    sql += " ORDER BY id DESC LIMIT ?"; args.append(n)
    with _lock:
        rows = _conn().execute(sql, args).fetchall()
    out = []
    for r in reversed(rows):
        d = _row(r)
        d["metadata"] = _loads(d.pop("metadata_json", "{}"), {})
        out.append(d)
    return out


def danh_dau_da_doc(conversation_id: int) -> bool:
    with _lock:
        db = _conn()
        cur = db.execute("UPDATE conversations SET unread_count=0, updated_at=? WHERE id=?",
                         (_now(), int(conversation_id)))
        db.commit()
    return cur.rowcount > 0


def dat_che_do(conversation_id: int, mode: str) -> tuple[bool, str]:
    """ai | human | waiting | closed. Chuẩn bị cho bước tiếp quản (V1.1); V1 chỉ đọc."""
    m = str(mode or "").strip().lower()
    if m not in CHE_DO:
        return False, f"chế độ '{m}' không hợp lệ (một trong {', '.join(CHE_DO)})"
    with _lock:
        db = _conn()
        cur = db.execute("UPDATE conversations SET mode=?, updated_at=? WHERE id=?",
                         (m, _now(), int(conversation_id)))
        db.commit()
    return (cur.rowcount > 0), ("" if cur.rowcount > 0 else "không có hội thoại nào id đó")


def che_do(channel: str, account_id: str, external_chat_id: str) -> str:
    """Chế độ hiện tại của một cuộc chat theo khoá kênh. Chưa có hội thoại thì là mặc định (ai).

    Adapter hỏi hàm này TRƯỚC khi gọi AI: `human` nghĩa là người thật đang tiếp quản, bot im.
    """
    try:
        with _lock:
            r = _conn().execute(
                "SELECT mode FROM conversations WHERE channel_account_id=? AND external_chat_id=?",
                (_tai_khoan_id(channel, account_id), str(external_chat_id))).fetchone()
        return str(r["mode"]) if r else CHE_DO_DEFAULT
    except Exception:
        return CHE_DO_DEFAULT


# ============================================================
# Thống kê và tài khoản kênh
# ============================================================
def _dau_ngay() -> float:
    """Epoch của 0 giờ hôm nay theo múi giờ CẤU HÌNH (không phải UTC)."""
    try:
        import localefmt
        now = localefmt.now()
    except Exception:
        now = datetime.now().astimezone()
    return (now - timedelta(hours=now.hour, minutes=now.minute,
                            seconds=now.second, microseconds=now.microsecond)).timestamp()


def thong_ke(bot_id: str = "", channel: str = "", account_id: str = "") -> dict:
    """Vài con số cho thẻ bot và đầu trang Hộp thư: tổng, hôm nay, chưa đọc, cần người."""
    where, args = ["1=1"], []
    if bot_id:
        where.append("c.bot_id=?"); args.append(str(bot_id))
    if channel:
        where.append("a.channel=?"); args.append(str(channel))
    if account_id:
        where.append("c.channel_account_id=?"); args.append(str(account_id))
    w = " AND ".join(where)
    dau = _dau_ngay()
    with _lock:
        db = _conn()
        r = db.execute(
            f"SELECT COUNT(*) AS tong,"
            f" SUM(CASE WHEN COALESCE(c.last_message_at,0)>=? THEN 1 ELSE 0 END) AS hom_nay,"
            f" SUM(CASE WHEN c.unread_count>0 THEN 1 ELSE 0 END) AS chua_doc,"
            f" SUM(CASE WHEN c.mode IN ('human','waiting') THEN 1 ELSE 0 END) AS can_nguoi,"
            f" SUM(c.message_count) AS tin"
            f" FROM conversations c JOIN channel_accounts a ON a.id=c.channel_account_id WHERE {w}",
            [dau] + args).fetchone()
        tin_hom_nay = db.execute(
            f"SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id=m.conversation_id"
            f" JOIN channel_accounts a ON a.id=c.channel_account_id"
            f" WHERE m.created_at>=? AND m.sender_type='customer' AND {w}",
            [dau] + args).fetchone()[0]
        theo_kenh = db.execute(
            f"SELECT a.channel AS channel, COUNT(*) AS n FROM conversations c"
            f" JOIN channel_accounts a ON a.id=c.channel_account_id WHERE {w} GROUP BY a.channel",
            args).fetchall()
    return {
        "tong": int(r["tong"] or 0), "hom_nay": int(r["hom_nay"] or 0),
        "chua_doc": int(r["chua_doc"] or 0), "can_nguoi": int(r["can_nguoi"] or 0),
        "tin": int(r["tin"] or 0), "tin_khach_hom_nay": int(tin_hom_nay or 0),
        "theo_kenh": {str(x["channel"]): int(x["n"]) for x in theo_kenh},
    }


def tai_khoan() -> List[dict]:
    """Các tài khoản kênh đã từng có tin, kèm số hội thoại và số chưa đọc."""
    with _lock:
        rows = _conn().execute(
            "SELECT a.*, COUNT(c.id) AS so_hoi_thoai,"
            " COALESCE(SUM(CASE WHEN c.unread_count>0 THEN 1 ELSE 0 END),0) AS chua_doc,"
            " MAX(c.last_message_at) AS lan_cuoi"
            " FROM channel_accounts a LEFT JOIN conversations c ON c.channel_account_id=a.id"
            " GROUP BY a.id ORDER BY lan_cuoi DESC").fetchall()
    out = []
    for r in rows:
        d = _row(r)
        d["channel_label"] = KENH_NHAN.get(d.get("channel") or "", d.get("channel") or "")
        out.append(d)
    return out


# ============================================================
# Trạng thái đồng bộ của adapter (cursor Zalo...)
# ============================================================
def doc_trang_thai(key: str, mac_dinh: str = "") -> str:
    try:
        with _lock:
            r = _conn().execute("SELECT value FROM sync_state WHERE key=?", (str(key),)).fetchone()
        return str(r["value"]) if r else mac_dinh
    except Exception:
        return mac_dinh


def ghi_trang_thai(key: str, value: str) -> None:
    try:
        with _lock:
            db = _conn()
            db.execute("INSERT INTO sync_state(key, value, updated_at) VALUES(?,?,?)"
                       " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                       " updated_at=excluded.updated_at",
                       (str(key), str(value if value is not None else ""), _now()))
            db.commit()
    except Exception as e:
        print(f"[conversations] ghi trạng thái lỗi: {e}", file=sys.stderr)


def xoa_trang_thai(tien_to: str) -> None:
    try:
        with _lock:
            db = _conn()
            db.execute("DELETE FROM sync_state WHERE key LIKE ?", (str(tien_to) + "%",))
            db.commit()
    except Exception as e:
        print(f"[conversations] xoá trạng thái lỗi: {e}", file=sys.stderr)


# ============================================================
# Tiện ích cho adapter bot chuyên trách
# ============================================================
# Câu gateway Telegram/Zalo Bot ghép vào đầu tin khi khách gửi file/ảnh/tin thoại. Đọc nó ra
# để gắn đúng loại tin; nội dung vẫn giữ nguyên vì phần chữ sau đó là caption hoặc lời nói.
_DAU_MEDIA = (
    ("ảnh", "image"), ("hình", "image"), ("tin thoại", "audio"), ("voice", "audio"),
    ("audio", "audio"), ("video", "video"), ("sticker", "sticker"), ("file", "file"),
    ("tài liệu", "file"), ("document", "file"),
)


def loai_tin_tu_chu(text: str) -> str:
    """Đoán loại tin từ dòng đầu do gateway ghép ("[Người dùng gửi ảnh qua Telegram...]")."""
    t = str(text or "").lstrip()
    if not t.startswith("["):
        return "text"
    dau = t[:160].lower()
    if "gửi" not in dau and "sent" not in dau:
        return "text"
    for tu, loai in _DAU_MEDIA:
        if tu in dau:
            return loai
    return "other"


# ============================================================
# CRM: khách hàng xuyên kênh (0.60.1)
#
# Tầng đọc/ghi mà gói "Quản lý khách hàng" ở Kho cài đặt (javis.khach-hang-crm) cắm vào. Gói
# gọi ĐÚNG các hàm này chứ không tự viết SQL: schema là của kho, kho đổi thì hàm đổi theo, còn
# SQL chép trong gói sẽ gãy im lặng ở bản sau. Hai hàm ghi (tag, ghi chú) chỉ chạm bảng
# customers; không hàm nào gửi tin hay gọi ra ngoài.
# ============================================================
MAX_TAG = 30
MAX_TAG_CHU = 40
MAX_GHI_CHU = 4_000

# Đếm tin KHÁCH của một khách: tin có sender_id trùng id khách trên cùng tài khoản kênh, hoặc
# tin riêng không ghi sender_id nhưng hội thoại đã gán khách đó (Telegram chat riêng).
_SQL_SO_TIN_KHACH = (
    "(SELECT COUNT(*) FROM messages m JOIN conversations c2 ON c2.id=m.conversation_id"
    " WHERE m.sender_type='customer' AND c2.channel_account_id=k.channel_account_id"
    " AND (m.sender_id=k.external_user_id OR (m.sender_id='' AND c2.customer_id=k.id)))"
)
_SQL_KHACH = (
    "SELECT k.*, a.channel AS channel, a.display_name AS account_name,"
    " a.external_account_id AS account_external_id, " + _SQL_SO_TIN_KHACH + " AS so_tin"
    " FROM customers k JOIN channel_accounts a ON a.id=k.channel_account_id"
)


def _khach_public(r: dict) -> dict:
    d = dict(r)
    d["tags"] = _loads(d.pop("tags_json", "[]"), [])
    d["metadata"] = _loads(d.pop("metadata_json", "{}"), {})
    d["channel_label"] = KENH_NHAN.get(d.get("channel") or "", d.get("channel") or "")
    d["first_seen_at"] = d.get("created_at")
    d["last_seen_at"] = d.get("updated_at")
    return d


def danh_sach_khach(channel: str = "", tag: str = "", q: str = "", days: int = 0,
                    limit: int = 100, offset: int = 0) -> List[dict]:
    """Khách đã nhắn, MỚI HOẠT ĐỘNG TRƯỚC. Lọc theo kênh, tag (khớp nguyên từ), chữ (tên, id
    trên kênh, ghi chú) và số ngày gần đây."""
    n = max(1, min(int(limit or 100), 1000))
    o = max(0, int(offset or 0))
    where, args = [], []
    if channel:
        where.append("a.channel=?"); args.append(str(channel))
    if tag:
        # tags_json là mảng JSON: so cả dấu ngoặc kép để "vip" không khớp "vip2".
        where.append("k.tags_json LIKE ?"); args.append('%"' + str(tag).replace('"', "") + '"%')
    if q:
        like = f"%{str(q).strip()}%"
        where.append("(k.name LIKE ? OR k.external_user_id LIKE ? OR k.note LIKE ?)")
        args += [like, like, like]
    if days and int(days) > 0:
        where.append("k.updated_at>=?"); args.append(_now() - int(days) * 86400)
    sql = _SQL_KHACH + (" WHERE " + " AND ".join(where) if where else "") \
        + " ORDER BY k.updated_at DESC, k.id DESC LIMIT ? OFFSET ?"
    with _lock:
        rows = _conn().execute(sql, args + [n, o]).fetchall()
    return [_khach_public(_row(r)) for r in rows]


def khach(customer_id: int) -> Optional[dict]:
    with _lock:
        r = _conn().execute(_SQL_KHACH + " WHERE k.id=?", (int(customer_id),)).fetchone()
    return _khach_public(_row(r)) if r else None


def hoi_thoai_cua_khach(customer_id: int) -> List[dict]:
    """Mọi hội thoại có mặt khách này: chat riêng của họ và các nhóm họ đã nhắn."""
    cid = int(customer_id)
    with _lock:
        rows = _conn().execute(
            "SELECT c.*, a.channel AS channel, a.display_name AS account_name,"
            " k.name AS customer_name, k.external_user_id AS customer_external_id"
            " FROM conversations c JOIN channel_accounts a ON a.id=c.channel_account_id"
            " LEFT JOIN customers k ON k.id=c.customer_id"
            " WHERE c.customer_id=? OR c.id IN ("
            "   SELECT m.conversation_id FROM messages m JOIN conversations c2 ON c2.id=m.conversation_id"
            "   JOIN customers k2 ON k2.id=? WHERE m.sender_type='customer'"
            "   AND c2.channel_account_id=k2.channel_account_id AND m.sender_id=k2.external_user_id)"
            " ORDER BY COALESCE(c.last_message_at, c.updated_at) DESC", (cid, cid)).fetchall()
    return [_conv_public(_row(r)) for r in rows]


def chuan_hoa_tag(tags) -> List[str]:
    """Bỏ trùng, cắt khoảng trắng, giới hạn số lượng và độ dài. Giữ nguyên hoa thường."""
    out: List[str] = []
    for t in (tags or []):
        t = " ".join(str(t or "").split())[:MAX_TAG_CHU]
        if t and t not in out:
            out.append(t)
    return out[:MAX_TAG]


def dat_tag_khach(customer_id: int, tags) -> Optional[List[str]]:
    """Thay cả danh sách tag của khách. Trả danh sách đã chuẩn hoá, None nếu không có khách."""
    sach = chuan_hoa_tag(tags)
    with _lock:
        db = _conn()
        cur = db.execute("UPDATE customers SET tags_json=?, updated_at=updated_at WHERE id=?",
                         (_json(sach), int(customer_id)))
        db.commit()
    return sach if cur.rowcount > 0 else None


def dat_ghi_chu_khach(customer_id: int, note: str) -> bool:
    with _lock:
        db = _conn()
        cur = db.execute("UPDATE customers SET note=?, updated_at=updated_at WHERE id=?",
                         (_s(note, MAX_GHI_CHU), int(customer_id)))
        db.commit()
    return cur.rowcount > 0


def tim_tin(q: str, channel: str = "", limit: int = 50) -> List[dict]:
    """Tìm chữ trong MỌI tin (khách lẫn bot), mới nhất trước, kèm hội thoại chứa tin."""
    q = str(q or "").strip()
    if not q:
        return []
    n = max(1, min(int(limit or 50), MAX_TIN_MOT_LAN))
    args: list = [f"%{q}%"]
    w = ""
    if channel:
        w = " AND a.channel=?"; args.append(str(channel))
    with _lock:
        rows = _conn().execute(
            "SELECT m.id, m.conversation_id, m.sender_type, m.sender_name, m.message_type, m.text,"
            " m.created_at, a.channel AS channel, c.title AS title, c.external_chat_id,"
            " k.name AS customer_name, c.customer_id"
            " FROM messages m JOIN conversations c ON c.id=m.conversation_id"
            " JOIN channel_accounts a ON a.id=c.channel_account_id"
            " LEFT JOIN customers k ON k.id=c.customer_id"
            " WHERE m.text LIKE ?" + w + " ORDER BY m.created_at DESC, m.id DESC LIMIT ?",
            args + [n]).fetchall()
    return [_row(r) for r in rows]


def cho_tra_loi(hours: float = 2.0, limit: int = 100) -> List[dict]:
    """Hội thoại mà câu CUỐI là của khách và đã quá `hours` giờ chưa ai (bot hay người) trả
    lời, cũ nhất trước. Bỏ hội thoại đã đóng."""
    moc = _now() - max(0.0, float(hours or 0)) * 3600
    n = max(1, min(int(limit or 100), MAX_DANH_SACH))
    with _lock:
        rows = _conn().execute(
            "SELECT c.*, a.channel AS channel, a.display_name AS account_name,"
            " k.name AS customer_name, k.external_user_id AS customer_external_id"
            " FROM conversations c JOIN channel_accounts a ON a.id=c.channel_account_id"
            " LEFT JOIN customers k ON k.id=c.customer_id"
            " WHERE c.last_sender_type='customer' AND c.last_message_at<=? AND c.mode!='closed'"
            " ORDER BY c.last_message_at ASC LIMIT ?", (moc, n)).fetchall()
    return [_conv_public(_row(r)) for r in rows]


def thong_ke_khach(days: int = 7, channel: str = "") -> dict:
    """Số khách, khách mới theo ngày trong N ngày (theo múi giờ cấu hình), số khách mỗi tag,
    và số hội thoại đang chờ khách được trả lời."""
    n = max(1, min(int(days or 7), 365))
    args: list = []
    w = ""
    if channel:
        w = " WHERE a.channel=?"; args.append(str(channel))
    with _lock:
        db = _conn()
        rows = db.execute("SELECT k.created_at, k.tags_json FROM customers k"
                          " JOIN channel_accounts a ON a.id=k.channel_account_id" + w, args).fetchall()
    try:
        import localefmt
        tz = localefmt.tz()
    except Exception:
        tz = None
    moc = _now() - n * 86400
    theo_ngay: Dict[str, int] = {}
    theo_tag: Dict[str, int] = {}
    for r in rows:
        ts = float(r["created_at"] or 0)
        if ts >= moc:
            k = datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d")
            theo_ngay[k] = theo_ngay.get(k, 0) + 1
        for t in _loads(r["tags_json"], []):
            theo_tag[str(t)] = theo_tag.get(str(t), 0) + 1
    return {
        "khach": len(rows), "so_ngay": n,
        "khach_moi_theo_ngay": dict(sorted(theo_ngay.items())),
        "theo_tag": dict(sorted(theo_tag.items(), key=lambda x: -x[1])),
        "cho_tra_loi": len(cho_tra_loi(0, MAX_DANH_SACH)),
    }
