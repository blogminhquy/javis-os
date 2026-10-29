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
import re
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
LOAI_TIN = ("text", "image", "file", "audio", "video", "sticker", "reaction", "other")
# "draft" (Chatbot v5, 2026-10-28): the bot writes its reply but does not send it; the reply waits in the conversation's
# `metadata.draft` for the owner to send, rewrite or drop (see `save_draft`).
CHE_DO = ("ai", "human", "waiting", "closed", "draft")
CHE_DO_DEFAULT = "ai"

MAX_CHU = 8_000          # trần độ dài một tin lưu lại
GIU_TIN_NHOM = 1000      # 0.65.12: mỗi NHÓM chỉ giữ chừng này tin gần nhất. Chat riêng với khách vẫn lưu hết (chủ chốt 30/09/2026).
                         # 0.396.0: raised from 100 to 1000 at the owner's request (29/10/2026).
NGAY_GIU_SAO_LUU = 14    # bản sao lưu trước khi cắt nhóm cũ tự xoá sau chừng này ngày: giữ mãi thì lời của người lạ vẫn nằm đó, trái mục đích cắt
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
CREATE TABLE IF NOT EXISTS inbox_tags(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT 'gray',
    position INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_tags(
    conversation_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(conversation_id, tag_id)
);
CREATE INDEX IF NOT EXISTS ix_conv_tag ON conversation_tags(tag_id, conversation_id);
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
        _nang_cap(db)
        db.commit()
        _db, _db_path = db, path
        return db


def _nang_cap(db: sqlite3.Connection) -> None:
    """Thêm cột cho kho cũ. `CREATE TABLE IF NOT EXISTS` không đụng bảng đã có, nên cột mới phải ALTER riêng."""
    cot = {r[1] for r in db.execute("PRAGMA table_info(customers)").fetchall()}
    if "phone" not in cot:
        # 0.216.0: số điện thoại của khách (dạng 0xxxxxxxxx), để ô tìm kiếm của hòm thư tìm theo số.
        db.execute("ALTER TABLE customers ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
    db.execute("CREATE INDEX IF NOT EXISTS ix_khach_sdt ON customers(phone) WHERE phone != ''")
    cot_hoi_thoai = {r[1] for r in db.execute("PRAGMA table_info(conversations)").fetchall()}
    if "pinned" not in cot_hoi_thoai:
        # 0.223.0: chủ ghim một cuộc chat lên đầu hòm thư, như ghim hội thoại ở trang Trò chuyện.
        db.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
    if "contact" not in cot_hoi_thoai:
        # Phone number or email the customer left in their own messages (inbox filter "has phone/email"). Filled on write
        # by `ghi_su_kien`; an old store is scanned once here so conversations from before the column count too.
        db.execute("ALTER TABLE conversations ADD COLUMN contact TEXT NOT NULL DEFAULT ''")
        _backfill_contact(db)
    if "hidden" not in cot_hoi_thoai:
        # Owner, 2026-10-25 (row menu like Zalo's): "Hide conversation" takes a chat out of the normal inbox list; the
        # "Hidden" filter shows it again. A NEW customer message clears it (`ghi_su_kien`), so a customer is never missed.
        db.execute("ALTER TABLE conversations ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")


def close() -> None:
    global _db, _db_path
    with _lock:
        if _db is not None:
            try:
                _db.close()
            except Exception:
                pass
        _db, _db_path = None, None


_ULTIMO_NOW = 0.0


def _now() -> float:
    """Giờ hiện tại, nhưng TĂNG NGHIÊM NGẶT trong tiến trình. Đồng hồ Windows chỉ nhích khoảng 15 ms một lần, nên hai lần ghi liên tiếp
    nhận cùng một `updated_at` và thứ tự "mới hoạt động trước" của danh sách khách/hội thoại phụ thuộc may rủi (test_hoi_thoai_crm đỏ
    ngẫu nhiên trên máy Windows). Nhích thêm một phần triệu giây khi trùng là đủ để thứ tự luôn đúng thứ tự ghi."""
    global _ULTIMO_NOW
    with _lock:
        t = time.time()
        _ULTIMO_NOW = t if t > _ULTIMO_NOW else _ULTIMO_NOW + 1e-6
        return _ULTIMO_NOW


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
        message_type         text | image | file | audio | video | sticker | reaction | other
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
        # A chat logged by the channel itself (Zalo "record chats") comes without a bot; it still belongs to the bot on
        # duty for that nick or Page, or the inbox would offer to "create an A.I." for a channel that has one.
        "bot_id": _s(ev.get("bot_id"), 64).strip() or bot_of_account(account_id),
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


def ghi_su_kien(ev: dict, dem_chua_doc: bool = True) -> dict:
    """Đổ MỘT sự kiện chuẩn vào kho: tìm/tạo tài khoản kênh, khách, hội thoại rồi thêm tin.

    Trả về {"ok": True, "conversation_id", "message_id", "customer_id", "trung": bool}.
    Tin trùng `external_message_id` trong cùng hội thoại thì `trung=True` và không ghi gì.
    Lỗi trả {"ok": False, "loi": ...} và KHÔNG ném: người gọi là lượt trả lời khách.

    `dem_chua_doc=False` (0.174.0): tin NHẬP LẠI từ lịch sử (Zalo cá nhân, `nhap_lich_su`) không cộng vào số chưa đọc. Đó là tin
    cũ đã đọc trên điện thoại; đếm vào là hàng trăm cuộc chat đỏ chót ngay sau một lần bấm.
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
                them_chua_doc = 1 if e["sender_type"] == "customer" and dem_chua_doc else 0
                # A phone number or email in the CUSTOMER's own words marks the conversation for the "has phone/email" filter.
                contact = find_contact(e["text"]) if e["sender_type"] == "customer" else ""
                # A NEW customer message brings a hidden conversation back into the inbox (owner's rule for "Hide
                # conversation": a customer is never missed). Old messages imported from history (dem_chua_doc=False)
                # and messages from the bot or the owner leave it hidden.
                unhide = 1 if e["sender_type"] == "customer" and dem_chua_doc else 0
                db.execute(
                    "UPDATE conversations SET last_message=?, last_message_at=?, last_sender_type=?,"
                    " unread_count=unread_count+?, message_count=message_count+1, updated_at=?,"
                    " contact=CASE WHEN ?!='' THEN ? ELSE contact END,"
                    " hidden=CASE WHEN ?=1 THEN 0 ELSE hidden END"
                    " WHERE id=?",
                    (tom, ts, e["sender_type"], them_chua_doc, now, contact, contact, unhide, conv_id))
                # 6. NHÓM chỉ giữ GIU_TIN_NHOM tin gần nhất (cùng giao dịch: không có lúc nào kho chứa thừa). `message_count` vẫn là số tin
                # từng nhận, không giảm theo.
                if e["chat_type"] == "group":
                    _cat_nhom_mot_cuoc(db, conv_id)
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return {"ok": True, "trung": False, "conversation_id": conv_id, "message_id": msg_id,
                "customer_id": customer_id}
    except Exception as ex:
        print(f"[conversations] ghi lỗi: {type(ex).__name__}: {ex}", file=sys.stderr)
        return {"ok": False, "loi": f"{type(ex).__name__}: {ex}"}


def co_tin(kenh: str, account_id: str, external_chat_id: str) -> bool:
    """Cuộc chat này đã có ít nhất một tin trong kho chưa (0.174.0, cho `zalo_personal_channel.nhap_lich_su`)."""
    with _lock:
        r = _conn().execute(
            "SELECT 1 FROM messages m JOIN conversations c ON c.id = m.conversation_id"
            " WHERE c.channel_account_id=? AND c.external_chat_id=? LIMIT 1",
            (_tai_khoan_id(kenh, account_id), str(external_chat_id))).fetchone()
    return bool(r)


def _cat_nhom_mot_cuoc(db, conv_id: int, giu: int = GIU_TIN_NHOM) -> int:
    """Xoá các tin CŨ của một cuộc chat, chỉ giữ `giu` tin mới nhất. Trả số tin đã xoá. Phải gọi trong giao dịch đang mở.

    Mốc cắt là id của tin thứ `giu` tính từ mới nhất (truy vấn theo chỉ mục `ix_msg_conv`, không quét cả bảng); chưa đủ `giu` tin thì
    không có mốc và không xoá gì."""
    cur = db.execute(
        "DELETE FROM messages WHERE conversation_id=? AND id < COALESCE("
        "(SELECT id FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 1 OFFSET ?), 0)",
        (int(conv_id), int(conv_id), int(giu) - 1))
    return int(cur.rowcount or 0)


_DAU_CAT_NHOM = "cat_nhom_v1"


def _don_sao_luu_cat_nhom() -> int:
    """Xoá bản sao lưu của lần cắt nhóm cũ đã quá `NGAY_GIU_SAO_LUU` ngày. Trả số file đã xoá. Không ném."""
    n = 0
    try:
        goc = Path(DB_PATH)
        for f in goc.parent.glob(goc.name + ".bak-truoc-cat-nhom-*"):
            try:
                if _now() - f.stat().st_mtime > NGAY_GIU_SAO_LUU * 86400:
                    f.unlink()
                    n += 1
            except OSError:
                pass
    except Exception:      # noqa: BLE001
        pass
    return n



def cat_nhom_cu(giu: int = GIU_TIN_NHOM) -> dict:
    """DI TRÚ MỘT LẦN (0.65.12): các nhóm đã có từ trước bản này được cắt xuống còn `giu` tin mới nhất.

    Xoá là không hoàn tác, nên: (1) sao lưu NGUYÊN file kho một lần trước khi cắt (API sao lưu của SQLite, nhất quán cả khi đang ghi WAL),
    (2) chỉ chạy khi thật sự có nhóm vượt mức, (3) ghi dấu vào `sync_state` để lần khởi động sau không chạy lại, và chỉ ghi dấu SAU khi cắt
    xong (cắt dở thì lần sau chạy lại, cắt lại là vô hại). Sau đó gom chỗ trống (VACUUM) để file nhỏ lại thật; hỏng bước này (hết đĩa...) chỉ là
    file chưa nhỏ, không phải lỗi dữ liệu.

    Trả `{"da_chay", "nhom", "da_xoa", "sao_luu", "loi"}`. Không ném: gọi lúc khởi động."""
    out = {"da_chay": False, "nhom": 0, "da_xoa": 0, "sao_luu": "", "loi": ""}
    try:
        with _lock:
            db = _conn()
            if db.execute("SELECT 1 FROM sync_state WHERE key=?", (_DAU_CAT_NHOM,)).fetchone():
                out["da_chay"] = True
                _don_sao_luu_cat_nhom()
                return out
            ds = [int(r[0]) for r in db.execute(
                "SELECT m.conversation_id FROM messages m JOIN conversations c ON c.id=m.conversation_id"
                " WHERE c.chat_type='group' GROUP BY m.conversation_id HAVING COUNT(*) > ?", (int(giu),)).fetchall()]
            if ds:
                ngay = datetime.now().strftime("%Y%m%d-%H%M%S")
                bak = Path(str(DB_PATH) + f".bak-truoc-cat-nhom-{ngay}")
                dst = sqlite3.connect(str(bak))
                try:
                    db.backup(dst)
                finally:
                    dst.close()
                out["sao_luu"] = str(bak)
                db.execute("BEGIN IMMEDIATE")
                try:
                    for cid in ds:
                        out["da_xoa"] += _cat_nhom_mot_cuoc(db, cid, giu)
                    db.execute("COMMIT")
                except Exception:
                    db.execute("ROLLBACK")
                    raise
                out["nhom"] = len(ds)
            db.execute("INSERT OR REPLACE INTO sync_state(key, value, updated_at) VALUES(?,?,?)",
                       (_DAU_CAT_NHOM, _json({"nhom": out["nhom"], "da_xoa": out["da_xoa"], "sao_luu": out["sao_luu"]}), _now()))
            db.commit()
            if out["da_xoa"]:
                try:
                    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    db.execute("VACUUM")
                except Exception as ex:      # noqa: BLE001
                    print(f"[conversations] gom chỗ trống sau khi cắt nhóm lỗi: {type(ex).__name__}: {ex}", file=sys.stderr)
        out["da_chay"] = True
    except Exception as ex:      # noqa: BLE001
        out["loi"] = f"{type(ex).__name__}: {ex}"
        print(f"[conversations] cắt nhóm cũ lỗi: {out['loi']}", file=sys.stderr)
    return out


def tin_gan_day(channel: str, account_id: str, external_chat_id: str, limit: int = 30) -> List[dict]:
    """`limit` tin MỚI NHẤT của một cuộc chat theo khoá kênh, cũ trước mới sau. Chưa có hội thoại thì rỗng.

    Dùng làm NGỮ CẢNH cho bot trả lời trong nhóm (0.65.12). Không ném: lỗi kho thì bot trả lời không có ngữ cảnh, không hỏng lượt."""
    n = max(1, min(int(limit or 30), MAX_TIN_MOT_LAN))
    try:
        with _lock:
            rows = _conn().execute(
                "SELECT m.* FROM messages m JOIN conversations c ON c.id=m.conversation_id"
                " WHERE c.channel_account_id=? AND c.external_chat_id=? ORDER BY m.id DESC LIMIT ?",
                (_tai_khoan_id(channel, account_id), str(external_chat_id), n)).fetchall()
        return [dict(r) for r in reversed(rows)]
    except Exception as ex:      # noqa: BLE001
        print(f"[conversations] đọc tin gần đây lỗi: {type(ex).__name__}: {ex}", file=sys.stderr)
        return []


def tin_theo_id(channel: str, account_id: str, external_chat_id: str, external_message_id: str) -> dict:
    """ONE stored message of a chat by the channel's own message id, `metadata` already parsed; {} if absent.

    Used to find the message a reply quotes (0.141.0, Zalo `replyTo.msgId`). Scoped to the same chat on purpose: a
    quote never points across chats, and an id from another chat must not leak that chat's content. Never raises."""
    mid = str(external_message_id or "").strip()
    if not mid:
        return {}
    try:
        with _lock:
            r = _conn().execute(
                "SELECT m.* FROM messages m JOIN conversations c ON c.id=m.conversation_id"
                " WHERE c.channel_account_id=? AND c.external_chat_id=? AND m.external_message_id=? LIMIT 1",
                (_tai_khoan_id(channel, account_id), str(external_chat_id), mid)).fetchone()
        if r is None:
            return {}
        d = dict(r)
        d["metadata"] = _loads(d.pop("metadata_json", "{}"), {})
        return d
    except Exception as ex:      # noqa: BLE001
        print(f"[conversations] đọc tin theo id lỗi: {type(ex).__name__}: {ex}", file=sys.stderr)
        return {}


def own_messages_without_id(channel: str, account_id: str, external_chat_id: str, since: float, n: int = 10) -> list:
    """Messages this account sent in a chat (the bot, or the owner from the inbox) since `since` that still have no
    channel message id, newest first: `[{id, text}]` (0.334.0). Never raises.

    Javis writes those rows before Zalo gives the message an id; the id comes back with the message's echo in the read
    loop (`zalo_personal_channel.attach_echo_id`). A customer's reaction names the message by that id, so without
    it a heart on the bot's price quote could not be told apart from a heart on anything else."""
    try:
        with _lock:
            rows = _conn().execute(
                "SELECT m.id, m.text FROM messages m JOIN conversations c ON c.id=m.conversation_id"
                " WHERE c.channel_account_id=? AND c.external_chat_id=? AND m.sender_type IN ('ai', 'human')"
                " AND (m.external_message_id IS NULL OR m.external_message_id='') AND m.created_at>=?"
                " ORDER BY m.id DESC LIMIT ?",
                (_tai_khoan_id(channel, account_id), str(external_chat_id), float(since), int(n))).fetchall()
        return [dict(r) for r in rows]
    except Exception as ex:      # noqa: BLE001
        print(f"[conversations] đọc tin chưa có mã lỗi: {type(ex).__name__}: {ex}", file=sys.stderr)
        return []


def set_message_id(row_id: int, external_message_id: str) -> bool:
    """Give a stored message its channel id (see `own_messages_without_id`). False when the id is empty, already used in the
    same conversation, or the row already has one. Never raises."""
    mid = str(external_message_id or "").strip()
    if not mid:
        return False
    try:
        with _lock:
            db = _conn()
            r = db.execute("SELECT conversation_id, external_message_id FROM messages WHERE id=?", (int(row_id),)).fetchone()
            if r is None or str(r["external_message_id"] or ""):
                return False
            if db.execute("SELECT 1 FROM messages WHERE conversation_id=? AND external_message_id=?",
                          (r["conversation_id"], mid)).fetchone():
                return False
            db.execute("UPDATE messages SET external_message_id=? WHERE id=?", (mid, int(row_id)))
            db.commit()
        return True
    except Exception as ex:      # noqa: BLE001
        print(f"[conversations] gắn mã tin lỗi: {type(ex).__name__}: {ex}", file=sys.stderr)
        return False


# ============================================================
# Đọc
# ============================================================
def _conv_public(r: dict) -> dict:
    d = dict(r)
    d["metadata"] = _loads(d.pop("metadata_json", "{}"), {})
    d["channel_label"] = (_channels.nhan_giao_dien(d.get("channel") or "")
                          if _channels.spec(d.get("channel") or "") else (d.get("channel") or ""))
    if not d.get("title"):
        if d.get("chat_type") == "group":
            # KHÔNG mượn tên khách: khách gắn với cuộc chat là NGƯỜI NHẮN ĐẦU TIÊN, nên nhóm
            # chưa biết tên hiện thành tên một người trong nhóm (chủ thấy nhóm "Test Bot Zalo"
            # hiện là "Minh Quý"). Đuôi id đủ để phân biệt các nhóm chưa rõ tên với nhau.
            cid = str(d.get("external_chat_id") or "")
            import localefmt
            d["title"] = (localefmt.chu(f"Nhóm …{cid[-6:]}", f"Group …{cid[-6:]}") if cid
                          else localefmt.chu("Nhóm chưa rõ tên", "Unnamed group"))
        else:
            d["title"] = d.get("customer_name") or d.get("external_chat_id") or ""
    return d


# Tình trạng lọc ở hòm thư (0.65.3). "Đang tiếp quản" = người thật đã nhận cuộc chat, bot im.
# "Cần trả lời" = khách nhắn cuối mà chưa ai đáp, chưa có người tiếp quản (bot trực hoặc chờ người), VÀ
#   - là chat riêng, hoặc
#   - là nhóm mà bot vừa cân nhắc nói rồi im (`hesitant`, từ kho bộ phán xử).
# Nhóm thì phải có điều kiện thứ hai: bot chỉ nói khi được gọi thì khách nhắn cuối trong nhóm là chuyện bình thường,
# đếm hết vào "cần trả lời" thì bộ lọc đầy rác và mất tác dụng.
_LOC_TINH_TRANG = {
    "unread": "c.unread_count>0",
    "human": "c.mode='human'",
}
_KHACH_CHUA_DAP = "c.last_sender_type='customer' AND c.mode IN ('ai','waiting','draft')"


def _sql_can_tra_loi(hesitant) -> tuple:
    """(điều kiện SQL, tham số) của "cần trả lời". `hesitant`: các cặp (bot_id, chat_id) nhóm bot đã cân nhắc rồi im."""
    pairs = [(str(a), str(b)) for a, b in (hesitant or [])][:200]
    if not pairs:
        return f"({_KHACH_CHUA_DAP} AND c.chat_type='private')", []
    vals = ",".join(["(?,?)"] * len(pairs))
    return (f"({_KHACH_CHUA_DAP} AND (c.chat_type='private' OR (c.bot_id, c.external_chat_id) IN (VALUES {vals})))",
            [x for p in pairs for x in p])


def can_tra_loi(item: dict, hesitant=None) -> bool:
    """Bản Python của điều kiện SQL ở trên, cho từng hàng danh sách (thẻ "Cần trả lời")."""
    if item.get("last_sender_type") != "customer" or str(item.get("mode") or "ai") not in ("ai", "waiting", "draft"):
        return False
    if item.get("chat_type") != "group":
        return True
    return (str(item.get("bot_id") or ""), str(item.get("external_chat_id") or "")) in {
        (str(a), str(b)) for a, b in (hesitant or [])}


# Zalo writes "X đã đồng ý kết bạn" / "Bạn vừa kết bạn với X" into the chat as if the other side had typed it. Nobody is
# waiting for an answer to that (owner, 2026-10-28), so it never puts a chat under "Needs you".
_TIN_KET_BAN = re.compile(r"(đã đồng ý kết bạn|vừa kết bạn với|đã trở thành bạn|accepted your friend request|are now friends)",
                          re.IGNORECASE)


def la_tin_ket_ban(text: Any) -> bool:
    """The message only says a friend request was accepted (no question in it)."""
    return bool(_TIN_KET_BAN.search(str(text or "")))


def khach_dang_cho(item: dict, hesitant=None) -> bool:
    """A customer waits for the OWNER right now (Chatbot v5 "Needs you"): the last message is the customer's and nobody
    answered it (`can_tra_loi`), the owner has not opened the chat since (it is still unread: opening it, or a reply, takes
    it off the list until the customer writes again), and it is more than a friend-request notice."""
    if not can_tra_loi(item, hesitant):
        return False
    if int(item.get("unread_count") or 0) <= 0:
        return False
    return not la_tin_ket_ban(item.get("last_message"))


BOT_KHONG_CO = "-"      # giá trị `bot_id` của bộ lọc để chỉ lấy cuộc chat KHÔNG có bot trực


def danh_sach(channel: str = "", bot_id: str = "", account_id: str = "", q: str = "",
              mode: str = "", limit: int = 50, offset: int = 0, status: str = "", chat_type: str = "",
              hesitant=None, tag: int = 0, has_contact: bool = False, sort: str = "",
              hidden: str = "", account_ids=None, ids=None, tags_any=None, tags_none=None,
              since: float = 0, until: float = 0, last_by: str = "", pinned: bool = False,
              _light: bool = False) -> List[dict]:
    """Danh sách hội thoại, ĐÃ GHIM rồi tới MỚI NHẤT TRƯỚC, kèm tên khách và kênh.

    `q` tìm theo tên khách, tiêu đề, id chat, tin cuối (LIKE, không phân biệt hoa thường).
    `status` (unread | need_reply | human) và `chat_type` (group | private): giá trị lạ thì BỎ QUA bộ lọc đó, vì
    một giá trị cũ còn lưu ở trình duyệt không được làm hòm thư trống trơn. `bot_id="-"`: chỉ cuộc chat không có bot.

    `tag` (an inbox tag id): only conversations carrying it. `has_contact`: only conversations where the customer left a
    phone number or email. `sort="waiting"`: conversations whose last message is an unanswered customer message come
    first, the one waiting longest on top (the rest follow, newest first). Each row carries `tags`.

    `hidden` (2026-10-25, row menu "Hide conversation"): "exclude" leaves hidden conversations out (the inbox list),
    "only" returns just them (the "Hidden" filter), "" ignores the flag (other callers, such as the bot form's chat
    picker, still see every chat).

    Chatbot v5 (2026-10-28): `account_ids` (several account keys, "<channel>:<id>") keeps only those accounts, the
    channel picker's ticks; `ids` keeps only these conversation ids, in the usual order (the inbox filters by who is
    handling a chat in Python, then asks for one page of the ids it kept); `tags_any` / `tags_none` (tag ids) keep
    conversations carrying at least one of, or none of, those tags.
    """
    n = max(1, min(int(limit or 50), MAX_STATE_ROWS if _light else MAX_DANH_SACH))
    o = max(0, int(offset or 0))
    where, args = _base_where(account_ids, ids, tags_any, tags_none, since, until, last_by, pinned)
    if channel:
        where.append("a.channel=?"); args.append(str(channel))
    if bot_id == BOT_KHONG_CO:
        where.append("c.bot_id=''")
    elif bot_id:
        where.append("c.bot_id=?"); args.append(str(bot_id))
    if status == "need_reply":
        sql_nr, args_nr = _sql_can_tra_loi(hesitant)
        where.append(sql_nr); args += args_nr
    elif status in _LOC_TINH_TRANG:
        where.append("(" + _LOC_TINH_TRANG[status] + ")")
    if chat_type in ("group", "private"):
        where.append("c.chat_type=?"); args.append(chat_type)
    if account_id:
        where.append("c.channel_account_id=?"); args.append(str(account_id))
    if mode:
        where.append("c.mode=?"); args.append(str(mode))
    if tag and int(tag) > 0:
        where.append("c.id IN (SELECT conversation_id FROM conversation_tags WHERE tag_id=?)"); args.append(int(tag))
    if has_contact:
        where.append("c.contact!=''")
    if hidden == "exclude":
        where.append("c.hidden=0")
    elif hidden == "only":
        where.append("c.hidden=1")
    if q:
        like = f"%{str(q).strip()}%"
        dk = ["k.name LIKE ?", "c.title LIKE ?", "c.external_chat_id LIKE ?", "c.last_message LIKE ?"]
        args += [like, like, like, like]
        # Gõ số điện thoại: khớp số đã lưu của khách theo cả dạng 0912... lẫn 84912..., và id cuộc chat của những kênh lấy
        # chính số làm id (WhatsApp giữ 84912...). Viết cách quãng "0912 345 678" cũng khớp.
        for v in bien_the_sdt(q):
            dk += ["k.phone LIKE ?", "c.external_chat_id LIKE ?"]
            args += [f"%{v}%", f"%{v}%"]
        where.append("(" + " OR ".join(dk) + ")")
    cols = ("c.id, c.bot_id, c.chat_type, c.external_chat_id, c.channel_account_id, c.mode, c.last_sender_type,"
            " c.unread_count, c.last_message, c.metadata_json, a.channel AS channel" if _light else
            "c.*, a.channel AS channel, a.display_name AS account_name,"
            " k.name AS customer_name, k.external_user_id AS customer_external_id, k.phone AS customer_phone")
    sql = (
        "SELECT " + cols +
        " FROM conversations c"
        " JOIN channel_accounts a ON a.id=c.channel_account_id"
        " LEFT JOIN customers k ON k.id=c.customer_id"
        + (" WHERE " + " AND ".join(where) if where else "")
        + (" ORDER BY " + _SORT_WAITING if sort == "waiting" else
           " ORDER BY c.pinned DESC, COALESCE(c.last_message_at, c.updated_at) DESC, c.id DESC")
        + " LIMIT ? OFFSET ?"
    )
    args += [n, o]
    with _lock:
        rows = _conn().execute(sql, args).fetchall()
    if _light:
        out = []
        for r in rows:
            d = _row(r)
            d["metadata"] = _loads(d.pop("metadata_json", "{}"), {})
            out.append(d)
        return out
    out = [_conv_public(_row(r)) for r in rows]
    tags = conversation_tags([c["id"] for c in out])
    for c in out:
        c["tags"] = tags.get(int(c["id"]), [])
    return out


# "Waiting longest" (Pancake's "đợi phản hồi lâu nhất"): an unanswered customer message first, oldest of those on top.
_SORT_WAITING = (f"CASE WHEN {_KHACH_CHUA_DAP} THEN 0 ELSE 1 END,"
                 f" CASE WHEN {_KHACH_CHUA_DAP} THEN COALESCE(c.last_message_at, c.updated_at) END ASC,"
                 " COALESCE(c.last_message_at, c.updated_at) DESC, c.id DESC")


def dem_bo_loc(hesitant=None) -> dict:
    """Số hội thoại cho từng lựa chọn của bộ lọc hòm thư, tính trên TOÀN hòm thư và không phụ thuộc bộ lọc đang
    chọn: con số ở dropdown không nhảy mỗi lần lọc, và biết bot nào còn việc mà không phải mở ra xem.

    `{"tong", "bots": {bot_id: {tong, unread, need_reply, human}}, "status": {...}, "type": {group, private}}`.
    Cuộc chat không có bot trực nằm ở khoá "" của `bots`.

    Hidden conversations (2026-10-25) are left out of every count, the same as they are left out of the list, so
    "All bots (N)" matches what the list shows and drops by one when a chat is hidden. They are counted once, in
    `status.hidden`, for the "Hidden" filter option.
    """
    sql_nr, args_nr = _sql_can_tra_loi(hesitant)
    with _lock:
        rows = _conn().execute(
            "SELECT c.bot_id AS bot_id, COUNT(*) AS tong,"
            " SUM(CASE WHEN c.unread_count>0 THEN 1 ELSE 0 END) AS unread,"
            f" SUM(CASE WHEN {sql_nr} THEN 1 ELSE 0 END) AS need_reply,"
            " SUM(CASE WHEN c.mode='human' THEN 1 ELSE 0 END) AS human,"
            " SUM(CASE WHEN c.chat_type='group' THEN 1 ELSE 0 END) AS grp,"
            " SUM(CASE WHEN c.contact!='' THEN 1 ELSE 0 END) AS contact"
            " FROM conversations c WHERE c.hidden=0 GROUP BY c.bot_id", args_nr).fetchall()
        n_hidden = _conn().execute("SELECT COUNT(*) FROM conversations WHERE hidden=1").fetchone()[0]
    out = {"tong": 0, "bots": {}, "status": {"unread": 0, "need_reply": 0, "human": 0, "hidden": int(n_hidden or 0)},
           "type": {"group": 0, "private": 0}, "has_contact": 0}
    for r in rows:
        tong = int(r["tong"] or 0)
        out["tong"] += tong
        out["bots"][str(r["bot_id"] or "")] = {
            "tong": tong, "unread": int(r["unread"] or 0), "need_reply": int(r["need_reply"] or 0),
            "human": int(r["human"] or 0)}
        for k in ("unread", "need_reply", "human"):
            out["status"][k] += int(r[k] or 0)
        out["type"]["group"] += int(r["grp"] or 0)
        out["type"]["private"] += tong - int(r["grp"] or 0)
        out["has_contact"] += int(r["contact"] or 0)
    return out


LAST_BY = ("customer", "ai", "human")


def _base_where(account_ids=None, ids=None, tags_any=None, tags_none=None, since: float = 0, until: float = 0,
                last_by: str = "", pinned: bool = False) -> tuple:
    """WHERE parts shared by `danh_sach` and `state_rows` for the Chatbot v5 filters: picked accounts, ids, tags
    any/none, the last message between `since` and `until` (timestamps, 0 = open), who sent the last message
    (customer | ai | human, anything else ignored) and pinned chats only."""
    where, args = [], []
    if since:
        where.append("c.last_message_at>=?"); args.append(float(since))
    if until:
        where.append("c.last_message_at<?"); args.append(float(until))
    if last_by in LAST_BY:
        where.append("c.last_sender_type=?"); args.append(last_by)
    if pinned:
        where.append("c.pinned=1")
    accs = [str(a) for a in (account_ids or []) if str(a).strip()][:200]
    if accs:
        where.append("c.channel_account_id IN (" + ",".join("?" * len(accs)) + ")"); args += accs
    if ids is not None:
        keep = [int(i) for i in ids][:MAX_STATE_ROWS]
        if not keep:
            where.append("0")
        else:
            where.append("c.id IN (" + ",".join("?" * len(keep)) + ")"); args += keep
    tany = [int(t) for t in (tags_any or []) if str(t).isdigit()][:50]
    if tany:
        where.append("c.id IN (SELECT conversation_id FROM conversation_tags WHERE tag_id IN ("
                     + ",".join("?" * len(tany)) + "))"); args += tany
    tnone = [int(t) for t in (tags_none or []) if str(t).isdigit()][:50]
    if tnone:
        where.append("c.id NOT IN (SELECT conversation_id FROM conversation_tags WHERE tag_id IN ("
                     + ",".join("?" * len(tnone)) + "))"); args += tnone
    return where, args


MAX_STATE_ROWS = 5000     # most conversations the "who is handling it" filter looks at in one request


def state_rows(channel: str = "", bot_id: str = "", q: str = "", status: str = "", chat_type: str = "",
               hesitant=None, tag: int = 0, has_contact: bool = False, hidden: str = "", account_ids=None,
               tags_any=None, tags_none=None, sort: str = "", since: float = 0, until: float = 0, last_by: str = "",
               pinned: bool = False) -> List[dict]:
    """Every conversation matching the inbox filters (newest first, at most MAX_STATE_ROWS), with only the columns the
    "who is handling it" state needs: id, bot_id, chat_type, external_chat_id, channel_account_id, channel, mode,
    last_sender_type, unread_count, last_message, metadata. Same filters as `danh_sach`, no paging."""
    rows = danh_sach(channel=channel, bot_id=bot_id, q=q, status=status, chat_type=chat_type, hesitant=hesitant,
                     tag=tag, has_contact=has_contact, hidden=hidden, account_ids=account_ids, tags_any=tags_any,
                     tags_none=tags_none, sort=sort, since=since, until=until, last_by=last_by, pinned=pinned,
                     limit=MAX_STATE_ROWS, _light=True)
    return rows


def cuoc_chat_cua_tai_khoan(channel: str, account_id: str, q: str = "", limit: int = 80) -> List[dict]:
    """Các cuộc chat ĐÃ BIẾT của một tài khoản kênh (theo id NGOÀI của tài khoản, như
    `channel_accounts` giữ), mới nhất trước. Cho ô chọn người/nhóm của form bot."""
    return danh_sach(account_id=_tai_khoan_id(channel, account_id), q=q, limit=limit)


def group_speakers(account_key: str, chat_id: str, limit: int = 300) -> List[dict]:
    """Người ĐÃ NHẮN trong một cuộc chat: `[{uid, name, ts}]`, mới nhất trước, tên là tên ở tin gần nhất của người đó.

    Dùng để đổi "@minhquy" thành ID Zalo thật khi tag người trong nhóm (plugin `zalo-group`): kho này có sẵn, tức thì, không
    tốn một lượt gọi mạng. `account_key` là khoá tài khoản kho dùng (`"<kênh>:<id>"`, ví dụ `zalo_personal:zalo-1`). Người
    chưa từng nhắn thì không có ở đây (đã có danh sách thành viên từ Zalo lo phần đó); tin của CHÍNH chủ không mang id nên
    cũng không có."""
    n = max(1, min(int(limit or 300), 1000))
    with _lock:
        rows = _conn().execute(
            "SELECT m.sender_id AS uid, m.sender_name AS name, MAX(m.created_at) AS ts"
            " FROM messages m JOIN conversations c ON c.id=m.conversation_id"
            " WHERE c.channel_account_id=? AND c.external_chat_id=? AND m.sender_type='customer'"
            " AND m.sender_id != '' AND m.sender_name != ''"
            " GROUP BY m.sender_id ORDER BY ts DESC LIMIT ?",
            (str(account_key), str(chat_id), n)).fetchall()
    return [{"uid": str(r["uid"]), "name": str(r["name"]), "ts": float(r["ts"] or 0)} for r in rows]


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
    d["tags"] = conversation_tags([d["id"]]).get(int(d["id"]), [])
    meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
    d["note"] = str(d.get("customer_note") or "") if d.get("customer_id") else str(meta.get("note") or "")
    return d


def tin_nhan(conversation_id: int, limit: int = 100, before_id: int = 0, after_id: int = 0) -> List[dict]:
    """Tin của một hội thoại, CŨ TRƯỚC MỚI SAU trong cửa sổ trả về (cửa sổ lấy từ cuối lên).

    `before_id` > 0: lấy các tin CŨ HƠN id đó (cuộn ngược để xem thêm).
    `after_id` > 0 (0.65.11): lấy các tin MỚI HƠN id đó, cũ trước mới sau. Nhịp làm mới 5 giây của khung tin chỉ hỏi phần này, thay vì
    tải lại cả trăm tin mỗi lần.
    """
    n = max(1, min(int(limit or 100), MAX_TIN_MOT_LAN))
    args: list = [int(conversation_id)]
    sql = "SELECT * FROM messages WHERE conversation_id=?"
    moi = bool(after_id and int(after_id) > 0)
    if moi:
        sql += " AND id>?"; args.append(int(after_id))
        sql += " ORDER BY id ASC LIMIT ?"; args.append(n)
    else:
        if before_id and int(before_id) > 0:
            sql += " AND id<?"; args.append(int(before_id))
        sql += " ORDER BY id DESC LIMIT ?"; args.append(n)
    with _lock:
        rows = _conn().execute(sql, args).fetchall()
    out = []
    for r in (rows if moi else reversed(rows)):
        d = _row(r)
        d["metadata"] = _loads(d.pop("metadata_json", "{}"), {})
        out.append(d)
    return out


def co_tin_cu(conversation_id: int, tin_id: int) -> bool:
    """Còn tin nào CŨ HƠN `tin_id` trong hội thoại này không (để khung tin biết có nên hiện nút/tự tải tin cũ)."""
    with _lock:
        r = _conn().execute("SELECT 1 FROM messages WHERE conversation_id=? AND id<? LIMIT 1",
                            (int(conversation_id), int(tin_id))).fetchone()
    return r is not None


def danh_dau_da_doc(conversation_id: int) -> bool:
    with _lock:
        db = _conn()
        cur = db.execute("UPDATE conversations SET unread_count=0, updated_at=? WHERE id=?",
                         (_now(), int(conversation_id)))
        db.commit()
    return cur.rowcount > 0


def mark_unread(conversation_id: int) -> bool:
    """Mark a conversation unread again (row menu, 2026-10-25): the red badge and the "Unread" filter come back.
    Keeps a real unread count; a read chat gets 1. Opening the chat marks it read as usual (`danh_dau_da_doc`).
    Does not touch `updated_at`: nothing new arrived."""
    with _lock:
        db = _conn()
        cur = db.execute("UPDATE conversations SET unread_count=MAX(unread_count, 1) WHERE id=?", (int(conversation_id),))
        db.commit()
    return cur.rowcount > 0


def set_hidden(conversation_id: int, hidden: bool) -> bool:
    """Hide a conversation from the inbox list, or bring it back (row menu, 2026-10-25). A new customer message
    unhides it on its own (`ghi_su_kien`). Does not touch `updated_at`."""
    with _lock:
        db = _conn()
        cur = db.execute("UPDATE conversations SET hidden=? WHERE id=?", (1 if hidden else 0, int(conversation_id)))
        db.commit()
    return cur.rowcount > 0


def dat_ghim(conversation_id: int, pinned: bool) -> bool:
    """Ghim hoặc bỏ ghim một cuộc chat (0.223.0). Không chạm `updated_at`: ghim không phải là có tin mới."""
    with _lock:
        db = _conn()
        cur = db.execute("UPDATE conversations SET pinned=? WHERE id=?", (1 if pinned else 0, int(conversation_id)))
        db.commit()
    return cur.rowcount > 0


# ============================================================
# Inbox tags (owner, 2026-10-25: "thêm tag khách hàng", like Pancake's coloured chips)
#
# The owner keeps ONE list of tags (name + a colour from a small fixed palette) and puts them on CONVERSATIONS, so a
# customer's private chat and a group they write in are tagged separately. Kept apart from `customers.tags_json`, the
# free-text tags the CRM store pack (javis.khach-hang-crm) writes on a CUSTOMER: neither touches the other.
# ============================================================
TAG_COLORS = ("gray", "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink")
MAX_INBOX_TAGS = 60
MAX_TAG_NAME = 40


def _tag_name(name: Any) -> str:
    return " ".join(str(name or "").split())[:MAX_TAG_NAME]


def _tag_color(color: Any) -> str:
    c = str(color or "").strip().lower()
    return c if c in TAG_COLORS else TAG_COLORS[0]


def list_tags() -> List[dict]:
    """Every inbox tag in the owner's order, with how many conversations carry it: `[{id, name, color, count}]`."""
    with _lock:
        rows = _conn().execute(
            "SELECT t.id, t.name, t.color, (SELECT COUNT(*) FROM conversation_tags ct WHERE ct.tag_id=t.id) AS count"
            " FROM inbox_tags t ORDER BY t.position, t.id").fetchall()
    return [{"id": int(r["id"]), "name": r["name"], "color": _tag_color(r["color"]), "count": int(r["count"] or 0)}
            for r in rows]


def _tag_clash(db, name: str, skip_id: int = 0) -> bool:
    """Another tag already has this name, ignoring case (Python casefold, so "Đã gửi" equals "đã gửi")."""
    key = name.casefold()
    return any(str(r[1]).casefold() == key and int(r[0]) != skip_id
               for r in db.execute("SELECT id, name FROM inbox_tags").fetchall())


def create_tag(name: Any, color: Any = "") -> tuple:
    """Add a tag. Returns `(tag, "")` or `(None, code)` with code `empty`, `duplicate` or `limit`."""
    n = _tag_name(name)
    if not n:
        return None, "empty"
    with _lock:
        db = _conn()
        if _tag_clash(db, n):
            return None, "duplicate"
        if db.execute("SELECT COUNT(*) FROM inbox_tags").fetchone()[0] >= MAX_INBOX_TAGS:
            return None, "limit"
        pos = db.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM inbox_tags").fetchone()[0]
        cur = db.execute("INSERT INTO inbox_tags(name, color, position, created_at) VALUES(?,?,?,?)",
                         (n, _tag_color(color), int(pos), _now()))
        db.commit()
        tid = int(cur.lastrowid)
    return {"id": tid, "name": n, "color": _tag_color(color), "count": 0}, ""


def update_tag(tag_id: int, name: Any = None, color: Any = None) -> tuple:
    """Rename and/or recolour a tag. Returns `(True, "")` or `(False, code)`: `missing`, `empty`, `duplicate`."""
    with _lock:
        db = _conn()
        if not db.execute("SELECT 1 FROM inbox_tags WHERE id=?", (int(tag_id),)).fetchone():
            return False, "missing"
        if name is not None:
            n = _tag_name(name)
            if not n:
                return False, "empty"
            if _tag_clash(db, n, int(tag_id)):
                return False, "duplicate"
            db.execute("UPDATE inbox_tags SET name=? WHERE id=?", (n, int(tag_id)))
        if color is not None:
            db.execute("UPDATE inbox_tags SET color=? WHERE id=?", (_tag_color(color), int(tag_id)))
        db.commit()
    return True, ""


def delete_tag(tag_id: int) -> bool:
    """Remove a tag and take it off every conversation."""
    with _lock:
        db = _conn()
        cur = db.execute("DELETE FROM inbox_tags WHERE id=?", (int(tag_id),))
        db.execute("DELETE FROM conversation_tags WHERE tag_id=?", (int(tag_id),))
        db.commit()
    return cur.rowcount > 0


def set_conversation_tag(conversation_id: int, tag_id: int, on: bool = True) -> Optional[List[dict]]:
    """Put a tag on a conversation (`on`) or take it off. Returns the conversation's tags after the change, or None when
    the conversation or the tag does not exist."""
    cid, tid = int(conversation_id), int(tag_id)
    with _lock:
        db = _conn()
        if not db.execute("SELECT 1 FROM conversations WHERE id=?", (cid,)).fetchone() or \
                not db.execute("SELECT 1 FROM inbox_tags WHERE id=?", (tid,)).fetchone():
            return None
        if on:
            db.execute("INSERT OR IGNORE INTO conversation_tags(conversation_id, tag_id, created_at) VALUES(?,?,?)",
                       (cid, tid, _now()))
        else:
            db.execute("DELETE FROM conversation_tags WHERE conversation_id=? AND tag_id=?", (cid, tid))
        db.commit()
    return conversation_tags([cid]).get(cid, [])


def conversation_tags(conversation_ids) -> Dict[int, List[dict]]:
    """`{conversation_id: [{id, name, color}]}` for the given conversations, tags in the owner's order."""
    ids = [int(x) for x in (conversation_ids or [])][:MAX_DANH_SACH * 5]
    if not ids:
        return {}
    with _lock:
        rows = _conn().execute(
            "SELECT ct.conversation_id AS cid, t.id, t.name, t.color FROM conversation_tags ct"
            " JOIN inbox_tags t ON t.id=ct.tag_id WHERE ct.conversation_id IN (" + ",".join("?" * len(ids)) + ")"
            " ORDER BY t.position, t.id", ids).fetchall()
    out: Dict[int, List[dict]] = {}
    for r in rows:
        out.setdefault(int(r["cid"]), []).append({"id": int(r["id"]), "name": r["name"], "color": _tag_color(r["color"])})
    return out


def dat_che_do(conversation_id: int, mode: str) -> tuple[bool, str]:
    """ai | human | waiting | closed. Chuẩn bị cho bước tiếp quản (V1.1); V1 chỉ đọc."""
    m = str(mode or "").strip().lower()
    if m not in CHE_DO:
        import localefmt
        return False, localefmt.chu(f"chế độ '{m}' không hợp lệ (một trong {', '.join(CHE_DO)})",
                                    f"invalid mode '{m}' (one of {', '.join(CHE_DO)})")
    with _lock:
        db = _conn()
        cur = db.execute("UPDATE conversations SET mode=?, updated_at=? WHERE id=?",
                         (m, _now(), int(conversation_id)))
        db.commit()
    if cur.rowcount > 0 and m == "human":
        _bao_tiep_quan(conversation_id)
    if cur.rowcount > 0:
        return True, ""
    import localefmt
    return False, localefmt.chu("không có hội thoại nào id đó", "no conversation with that id")


def _bao_tiep_quan(conversation_id: int) -> None:
    """Chủ vừa Tiếp quản một cuộc chat của bot: báo bộ phán xử hội thoại nhóm (0.65.0). Những lần bot TỰ nói
    (không ai gọi) ngay trước đó bị coi là chen nhầm. Chỉ chạm kho khi nó đã tồn tại; lỗi gì cũng nuốt vì
    việc Tiếp quản của chủ không được hỏng theo một tính năng học."""
    try:
        c = chi_tiet(conversation_id) or {}
        bot_id, chat = str(c.get("bot_id") or ""), str(c.get("external_chat_id") or "")
        if not (bot_id and chat):
            return
        import chatbot_reply_policy as rp
        import chatbot_reply_policy_store as rps
        import chatbot_store
        cfg = chatbot_store.get_bot(bot_id)
        if cfg and rps.db_path().exists():
            rp.note_takeover(rps, rp.BotProfile.from_bot(cfg), chat)
    except Exception:      # noqa: BLE001
        pass


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
# Drafts the bot wrote in "draft" mode (Chatbot v5)
# ============================================================
MAX_DRAFT = 4000


def _set_meta_key(conversation_id: int, key: str, value) -> bool:
    """Set (or remove, when `value` is None) one key of a conversation's metadata. False when there is no such
    conversation."""
    with _lock:
        db = _conn()
        r = db.execute("SELECT metadata_json FROM conversations WHERE id=?", (int(conversation_id),)).fetchone()
        if r is None:
            return False
        meta = _loads(r["metadata_json"], {})
        if not isinstance(meta, dict):
            meta = {}
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = value
        db.execute("UPDATE conversations SET metadata_json=?, updated_at=? WHERE id=?",
                   (_json(meta), _now(), int(conversation_id)))
        db.commit()
    return True


def conversation_id_of(channel: str, account_id: str, external_chat_id: str) -> int:
    """Id of the conversation for a channel key, 0 when there is none yet."""
    try:
        with _lock:
            r = _conn().execute(
                "SELECT id FROM conversations WHERE channel_account_id=? AND external_chat_id=?",
                (_tai_khoan_id(channel, account_id), str(external_chat_id))).fetchone()
        return int(r["id"]) if r else 0
    except Exception:      # noqa: BLE001
        return 0


def save_draft(conversation_id: int, text: str, for_message_id: int = 0, instruction: str = "") -> bool:
    """Keep the bot's unsent reply on the conversation. A newer draft replaces the older one: the owner only ever reviews
    the reply to the latest customer message."""
    t = str(text or "").strip()[:MAX_DRAFT]
    if not t:
        return False
    return _set_meta_key(conversation_id, "draft", {"text": t, "ts": _now(), "for_message_id": int(for_message_id or 0),
                                                    "instruction": str(instruction or "")[:500]})


def clear_draft(conversation_id: int) -> bool:
    return _set_meta_key(conversation_id, "draft", None)


def set_note(conversation_id: int, note: str) -> bool:
    """The owner's note on a chat (Chatbot v5 Info panel). It belongs to the customer when the chat has one (the same
    note then follows them into every chat), else to the conversation itself (a group). False when there is no such
    conversation."""
    text = _s(str(note or "").strip(), MAX_GHI_CHU)
    with _lock:
        r = _conn().execute("SELECT customer_id FROM conversations WHERE id=?", (int(conversation_id),)).fetchone()
    if r is None:
        return False
    if r["customer_id"]:
        return dat_ghi_chu_khach(int(r["customer_id"]), text)
    return _set_meta_key(conversation_id, "note", text or None)


def draft_of(conv: dict) -> Optional[dict]:
    """The waiting draft of a conversation row (`metadata.draft`), or None."""
    d = ((conv or {}).get("metadata") or {}).get("draft")
    return d if isinstance(d, dict) and str(d.get("text") or "").strip() else None


def last_customer_message_id(conversation_id: int) -> int:
    with _lock:
        r = _conn().execute("SELECT MAX(id) FROM messages WHERE conversation_id=? AND sender_type='customer'",
                            (int(conversation_id),)).fetchone()
    return int(r[0] or 0) if r else 0


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
    """Vài con số cho thẻ bot và đầu trang Hộp thư: tổng, hôm nay, chưa đọc, cần người.

    `chua_doc` (the inbox tab badge) and `theo_kenh` (channel filter counts) leave hidden conversations out, like the
    list does; `tong` still counts every conversation the bot has had."""
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
            f" SUM(CASE WHEN c.unread_count>0 AND c.hidden=0 THEN 1 ELSE 0 END) AS chua_doc,"
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
            f" JOIN channel_accounts a ON a.id=c.channel_account_id WHERE {w} AND c.hidden=0 GROUP BY a.channel",
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


# ---- "No bot needed" (Chatbot v5 Channels tab): the owner says a nick or Page is fine without an A.I., so its chats are
# "logged only" and it stops counting as something to do. Kept per account key ("<channel>:<raw id>") in sync_state,
# which holds every kind of account (a personal Zalo nick has no record in channel_accounts.json).
_NO_BOT = "no_bot:"


def set_no_bot(account_key: str, on: bool) -> None:
    ghi_trang_thai(_NO_BOT + str(account_key), "1" if on else "")


def set_account_bot(account_key: str, bot_id: str) -> int:
    """The bot on duty for a channel account changed (Channels tab): its chats follow, so the inbox, the "who is
    handling it" state and the per-chat A.I. switch all see the new bot (or none). Returns how many chats moved."""
    with _lock:
        db = _conn()
        cur = db.execute("UPDATE conversations SET bot_id=? WHERE channel_account_id=?", (str(bot_id or ""), str(account_key)))
        db.commit()
    return cur.rowcount


def bot_of_account(account_id: str) -> str:
    """The bot on duty for a raw channel account id ("" when none). One bot per account (`chatbot_store.owner_of`)."""
    if not account_id:
        return ""
    try:
        import chatbot_store
        bots = chatbot_store.bots_using_account(str(account_id))
    except Exception:      # noqa: BLE001
        return ""
    return str(bots[0].get("id") or "") if bots else ""


def fill_missing_bots() -> int:
    """Chats logged before the fix above have no bot although their nick or Page has one: give them that bot.
    Returns how many chats changed. Cheap and idempotent (only rows with an empty bot_id)."""
    try:
        import chatbot_store
        pairs = [(aid, b["id"]) for b in chatbot_store.list_bots() for aid in chatbot_store.account_ids_of(b)]
    except Exception:      # noqa: BLE001
        return 0
    n = 0
    with _lock:
        db = _conn()
        for aid, bid in pairs:
            cur = db.execute("UPDATE conversations SET bot_id=? WHERE bot_id=''"
                             " AND substr(channel_account_id, instr(channel_account_id, ':') + 1)=?", (str(bid), str(aid)))
            n += int(cur.rowcount or 0)
        db.commit()
    return n


def no_bot_accounts() -> set:
    try:
        with _lock:
            rows = _conn().execute("SELECT key FROM sync_state WHERE key LIKE ? AND value='1'", (_NO_BOT + "%",)).fetchall()
        return {str(r["key"])[len(_NO_BOT):] for r in rows}
    except Exception:
        return set()


# Hours a customer counts as writing "while you rest" for the Stats tab (owner, 2026-10-29): 21:00 to 07:00 local time.
NGHI_TU, NGHI_DEN = 21, 7


def _trung_vi(xs: list) -> Optional[float]:
    if not xs:
        return None
    v = sorted(xs)
    m = len(v) // 2
    return round(v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2, 1)


def insights(since: float, until: float, account: str = "") -> dict:
    """Numbers for the Stats tab (Chatbot v5) between two timestamps: messages the A.I. sent, messages the owner sent,
    customer messages, the average wait of a customer for the first answer (A.I. or owner), and the same counts per
    channel and per bot. A waiting run starts at the first customer message after an answer; reactions do not count.

    0.399.0 (owner, 2026-10-29: show what the chatbot gives the owner) adds:
      - the typical (median) wait when the A.I. answered first and when the owner did, so the two can be compared;
      - `ai_rest`: A.I. answers sent while the owner rests (21:00 to 07:00 in the brain's time zone);
      - `chats` / `new_chats`: chats where a customer wrote, and private chats whose very first message is in the period;
      - `hours`: customer messages per hour of the day (24 numbers, the brain's time zone).

    0.401.0 (owner, 2026-10-29: "ở nick Javis Vũ anh không trả lời tý nào mà nó tính 45% câu do A.I. lo"): the totals mixed
    every account, so one account's hand replies lowered another one's A.I. share. `account` (the inbox account key,
    `"<channel>:<id>"`) keeps one account only, and `by_account` gives each account its own A.I., hand and customer counts."""
    import localefmt
    tz = localefmt.tz()
    with _lock:
        db = _conn()
        rows = db.execute(
            "SELECT m.conversation_id AS cid, m.sender_type AS who, m.created_at AS ts, a.channel AS channel,"
            " c.bot_id AS bot_id, a.id AS acc FROM messages m JOIN conversations c ON c.id=m.conversation_id"
            " JOIN channel_accounts a ON a.id=c.channel_account_id"
            " WHERE m.created_at>=? AND m.created_at<? AND m.sender_type IN ('customer','ai','human')"
            " AND m.message_type!='reaction'" + (" AND c.channel_account_id=?" if account else "") +
            " ORDER BY m.conversation_id, m.created_at, m.id",
            (float(since), float(until)) + ((str(account),) if account else ())).fetchall()
        moi = db.execute(
            "SELECT COUNT(*) FROM (SELECT m.conversation_id, MIN(m.created_at) AS dau FROM messages m"
            " JOIN conversations c ON c.id=m.conversation_id WHERE c.chat_type='private'" +
            (" AND c.channel_account_id=?" if account else "") +
            " GROUP BY m.conversation_id HAVING dau>=? AND dau<?)",
            ((str(account),) if account else ()) + (float(since), float(until))).fetchone()[0]
    out = {"ai": 0, "human": 0, "customer": 0, "wait_avg": None, "waits": 0, "by_channel": {}, "by_bot": {}, "by_account": {},
           "wait_ai": None, "wait_human": None, "waits_ai": 0, "waits_human": 0, "ai_rest": 0,
           "chats": 0, "new_chats": int(moi or 0), "hours": [0] * 24}
    waits, w_ai, w_human, start, cur, khach = [], [], [], None, None, set()
    for r in rows:
        who, ts = str(r["who"]), float(r["ts"] or 0)
        if r["cid"] != cur:
            cur, start = r["cid"], None
        ch = out["by_channel"].setdefault(str(r["channel"] or ""), {"customer": 0, "ai": 0, "human": 0})
        ch[who] += 1
        acc = out["by_account"].setdefault(str(r["acc"] or ""), {"customer": 0, "ai": 0, "human": 0})
        acc[who] += 1
        out[who] += 1
        gio = datetime.fromtimestamp(ts, tz).hour
        if who == "customer":
            khach.add(r["cid"])
            out["hours"][gio] += 1
            if start is None:
                start = ts
        else:
            if who == "ai":
                if r["bot_id"]:
                    out["by_bot"][str(r["bot_id"])] = out["by_bot"].get(str(r["bot_id"]), 0) + 1
                if gio >= NGHI_TU or gio < NGHI_DEN:
                    out["ai_rest"] += 1
            if start is not None:
                w = max(0.0, ts - start)
                waits.append(w)
                (w_ai if who == "ai" else w_human).append(w)
                start = None
    out["chats"] = len(khach)
    if waits:
        out["wait_avg"] = round(sum(waits) / len(waits), 1)
        out["waits"] = len(waits)
    out["wait_ai"], out["waits_ai"] = _trung_vi(w_ai), len(w_ai)
    out["wait_human"], out["waits_human"] = _trung_vi(w_human), len(w_human)
    return out


def stats_accounts() -> List[dict]:
    """Every channel account the inbox knows, for the Stats tab's account picker: `[{id, channel, name}]` by name."""
    with _lock:
        rows = _conn().execute("SELECT id, channel, display_name FROM channel_accounts ORDER BY display_name, id").fetchall()
    return [{"id": r["id"], "channel": r["channel"], "name": r["display_name"] or r["id"]} for r in rows]


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


_NEN_ANH = re.compile(r"^(?:https?://\S+|\[(?:chat\.)?(?:photo|image)[^\]]*\]|\[[^\]]*khách gửi [a-z]+\])$", re.IGNORECASE)


def chu_thich_anh(text: str) -> str:
    """Chú thích thật của một tin ảnh, hoặc "" nếu tin ảnh trơn.

    MCP của javis-zalo chuẩn hoá tin không phải chữ bằng `extractMessageText` (src/utils/extract-message-text.js; bản 1.6.2 cũ là
    `content.title || content.href || "[<msgType>]"`). Với ảnh hai bản ra cùng kết quả vì ảnh có `description` rỗng: ảnh CÓ chú thích
    thì `text` là chú thích; ảnh trơn thì `text` là đường dẫn ảnh, hoặc "[chat.photo]". Javis
    cũng tự thay chữ trống bằng "[Zalo cá nhân: khách gửi image]". Cả ba loại "nền" đó không phải lời của người gửi nên trả rỗng."""
    t = " ".join(str(text or "").split())
    return "" if (not t or _NEN_ANH.match(t)) else t


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
        dk = ["k.name LIKE ?", "k.external_user_id LIKE ?", "k.note LIKE ?"]
        args += [like, like, like]
        for v in bien_the_sdt(q):
            dk.append("k.phone LIKE ?"); args.append(f"%{v}%")
        where.append("(" + " OR ".join(dk) + ")")
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


# ============================================================
# Số điện thoại của khách (0.216.0)
# ============================================================
_SDT_TACH = re.compile(r"[\s.\-()]")


def chuan_hoa_sdt(s: Any) -> str:
    """Một số di động Việt Nam ĐẦY ĐỦ về dạng `0xxxxxxxxx`, hoặc "" nếu không phải.

    Nhận "0912345678", "84912345678", "+84 912 345 678", "0912.345.678". Chỉ nhận số có đầu 0 hoặc 84: gõ dở
    "849123456" không được coi là số 084..., kẻo ô tìm kiếm đi hỏi Zalo một số người dùng chưa gõ xong."""
    t = _SDT_TACH.sub("", str(s or "").strip())
    if not re.fullmatch(r"\+?\d+", t or "x"):
        return ""
    d = t.lstrip("+")
    if d.startswith("84") and len(d) == 11 and d[2] in "35789":
        return "0" + d[2:]
    if d.startswith("0") and len(d) == 10 and d[1] in "35789":
        return d
    return ""


def sdt_84(phone: str) -> str:
    """`0912345678` -> `84912345678`, dạng Zalo và WhatsApp dùng."""
    p = chuan_hoa_sdt(phone)
    return "84" + p[1:] if p else ""


def bien_the_sdt(q: Any) -> List[str]:
    """Các cách viết của một (phần) số điện thoại để tìm bằng LIKE: chính dãy số, và dạng 0 <-> 84 tương ứng.

    Chỉ khi `q` toàn số (cho phép dấu cách, chấm, gạch, ngoặc, dấu + đầu) và từ 4 chữ số trở lên; còn lại trả [] để chữ
    thường không tìm nhầm vào cột số."""
    t = _SDT_TACH.sub("", str(q or "").strip())
    if not re.fullmatch(r"\+?\d{4,15}", t or "x"):
        return []
    d = t.lstrip("+")
    out = [d]
    if d.startswith("84") and len(d) > 4:
        out.append("0" + d[2:])
    elif d.startswith("0") and len(d) > 4:
        out.append("84" + d[1:])
    return out


# Contact details a customer leaves in a message: a Vietnamese mobile number in any of the usual spellings (0912345678,
# 0912 345 678, 0912.345.678, +84 912345678, 84912345678, (+84) 912...) or an email address. Digits glued to more digits
# (order ids, timestamps, long Zalo ids) are not a phone number.
_PHONE_IN_TEXT = re.compile(r"(?<![\d+])(?:\(?\+?84\)?|0)[ .\-]?[35789](?:[ .\-]?\d){8}(?!\d)")
_EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")


def find_contact(text: Any) -> str:
    """The first phone number (as `0xxxxxxxxx`) or, failing that, the first email (lowercase) in `text`, else ""."""
    t = str(text or "")
    if not t:
        return ""
    for m in _PHONE_IN_TEXT.finditer(t):
        p = chuan_hoa_sdt(m.group(0).replace("(", "").replace(")", ""))
        if p:
            return p
    m = _EMAIL_IN_TEXT.search(t)
    return m.group(0).lower()[:MAX_TEN] if m else ""


def _backfill_contact(db: sqlite3.Connection) -> int:
    """Fill `conversations.contact` from customer messages already stored (once, when the column is added). The newest
    message with a contact wins, the same as on write. Returns how many conversations got one."""
    found: Dict[int, str] = {}
    rows = db.execute("SELECT conversation_id, text FROM messages WHERE sender_type='customer'"
                      " AND (text LIKE '%@%' OR text GLOB '*[0-9][0-9][0-9]*') ORDER BY id").fetchall()
    for r in rows:
        c = find_contact(r[1])
        if c:
            found[int(r[0])] = c
    for cid, c in found.items():
        db.execute("UPDATE conversations SET contact=? WHERE id=?", (c, cid))
    return len(found)


def gan_sdt_khach(channel: str, account_id: str, external_user_id: str, phone: str, name: str = "") -> Optional[int]:
    """Gắn số điện thoại cho khách `external_user_id` của tài khoản kênh (`account_id` là id NGOÀI, như sự kiện mang).

    Có cuộc chat riêng với người đó mà chưa có khách (chỉ chủ nhắn đi, khách chưa nhắn lại) thì tạo khách và nối vào
    cuộc chat, để lần tìm sau khớp ngay. Không có cả khách lẫn cuộc chat thì không tạo gì: hòm thư chỉ hiện cuộc chat.
    Trả id khách, hoặc None."""
    p = chuan_hoa_sdt(phone)
    uid = str(external_user_id or "").strip()
    if not p or not uid:
        return None
    tk = _tai_khoan_id(channel, account_id)
    now = _now()
    with _lock:
        db = _conn()
        r = db.execute("SELECT id FROM customers WHERE channel_account_id=? AND external_user_id=?",
                       (tk, uid)).fetchone()
        conv = db.execute("SELECT id, customer_id FROM conversations WHERE channel_account_id=? AND external_chat_id=?"
                          " AND chat_type='private'", (tk, uid)).fetchone()
        if r:
            kid = int(r[0])
            db.execute("UPDATE customers SET phone=? WHERE id=?", (p, kid))
        elif conv:
            cur = db.execute("INSERT INTO customers(channel_account_id, external_user_id, name, phone, created_at,"
                             " updated_at) VALUES(?,?,?,?,?,?)", (tk, uid, _s(name, MAX_TEN), p, now, now))
            kid = int(cur.lastrowid)
        else:
            return None
        if conv and not conv["customer_id"]:
            db.execute("UPDATE conversations SET customer_id=? WHERE id=?", (kid, int(conv["id"])))
        db.commit()
    return kid


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
