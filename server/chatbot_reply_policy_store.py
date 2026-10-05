"""Kho của bộ phán xử hội thoại nhóm (0.65.0): SQLite, WAL, nằm trong thư mục state, KHÔNG lên git.

Bốn thứ nằm ở đây, đều tách theo `bot_id` (và nhiều thứ theo cả `chat_id`):

  - `decisions`: MỌI quyết định của bộ phán xử, kể cả lúc bot im. Đây là dấu vết mà lỗi "gọi tên
    trơn mà bot im" từng thiếu: tin bị loại ở tầng lọc đầu không để lại gì nên không ai dò được.
  - `cases`: các tình huống đã có nhãn (hoặc do chủ dạy, hoặc do model viết lúc khởi tạo). Bộ phán
    xử tra những ca giống nhất ngay trước mỗi quyết định.
  - `watches`: cửa theo dõi hậu quả của một quyết định, để gắn nhãn khi người trong nhóm phản ứng.
  - `threshold_offsets`, `role_profiles`, `lessons`: cái bot học được về CUỘC CHAT và về VAI.

Dữ liệu ở đây là NỘI DUNG CHAT KHÁCH, nên: chỉ ghi khi chủ bật bộ phán xử cho bot (xem
`chatbot_reply_policy`), nội dung cắt 400 ký tự, dòng chưa gắn nhãn giữ 14 ngày, ca đã có nhãn giữ
180 ngày, xoá bot thì xoá sạch dòng của bot, và có `forget()` cho nút "quên hết".

Không dùng thư viện ngoài. Mỗi lời gọi mở một kết nối ngắn (SQLite mở rẻ) để khỏi dính chuyện luồng.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import config as cfgmod

TEXT_MAX = 400
UNLABELED_KEEP_S = 14 * 86400
LABELED_KEEP_S = 180 * 86400
MAX_CASES_PER_BOT = 500
MAX_CASES_PER_CHAT = 200
MAX_LESSONS = 15
OFFSET_LIMIT = 0.25
OFFSET_HALF_LIFE_S = 14 * 86400
PURGE_EVERY = 400          # số lần ghi giữa hai lần dọn

_lock = threading.RLock()
_writes = 0
_ready: set = set()        # các file kho đã tạo bảng trong tiến trình này (khỏi chạy lại schema mỗi lần mở)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_id TEXT NOT NULL, chat_id TEXT NOT NULL, msg_id TEXT, ts REAL NOT NULL,
  text TEXT, sender TEXT, sender_id TEXT, sender_role TEXT, address_level TEXT, signals_json TEXT,
  candidate INTEGER NOT NULL DEFAULT 0, verdict TEXT NOT NULL, score REAL, threshold REAL,
  reason TEXT, mode TEXT, silence_code TEXT,
  label TEXT, label_weight REAL, label_ts REAL);
CREATE INDEX IF NOT EXISTS idx_dec_bot_ts ON decisions(bot_id, ts);
CREATE INDEX IF NOT EXISTS idx_dec_chat_ts ON decisions(bot_id, chat_id, ts);
CREATE TABLE IF NOT EXISTS cases(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_id TEXT NOT NULL, chat_id TEXT, ts REAL NOT NULL, text TEXT, tokens TEXT,
  features_json TEXT, correct_verdict TEXT NOT NULL, reason TEXT,
  source TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1.0, origin_case_id INTEGER, decision_id INTEGER);
CREATE INDEX IF NOT EXISTS idx_cases_bot ON cases(bot_id, ts);
CREATE TABLE IF NOT EXISTS watches(
  decision_id INTEGER PRIMARY KEY, bot_id TEXT NOT NULL, chat_id TEXT NOT NULL,
  expires_ts REAL NOT NULL, messages_left INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS idx_watch_chat ON watches(bot_id, chat_id);
CREATE TABLE IF NOT EXISTS role_profiles(
  bot_id TEXT PRIMARY KEY, generated_text TEXT, agent_hash TEXT, updated_ts REAL);
CREATE TABLE IF NOT EXISTS threshold_offsets(
  bot_id TEXT NOT NULL, chat_id TEXT NOT NULL, offset REAL NOT NULL, updated_ts REAL NOT NULL,
  PRIMARY KEY(bot_id, chat_id));
CREATE TABLE IF NOT EXISTS lessons(
  id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT NOT NULL, text TEXT NOT NULL, ts REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_lessons_bot ON lessons(bot_id, ts);
CREATE TABLE IF NOT EXISTS tuning(
  bot_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, updated_ts REAL NOT NULL,
  PRIMARY KEY(bot_id, key));
CREATE TABLE IF NOT EXISTS changes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT NOT NULL, ts REAL NOT NULL, actor TEXT NOT NULL,
  review_id TEXT, op TEXT NOT NULL, target TEXT, before_json TEXT, after_json TEXT, reason TEXT,
  evidence_json TEXT, status TEXT NOT NULL, status_ts REAL);
CREATE INDEX IF NOT EXISTS idx_changes_bot ON changes(bot_id, ts);
CREATE TABLE IF NOT EXISTS review_state(bot_id TEXT PRIMARY KEY, last_ts REAL NOT NULL);
"""

# Columns added after a table first shipped. `CREATE TABLE IF NOT EXISTS` never alters an existing table, so an
# older store needs these added by hand. Each one is tried once per process; "duplicate column" is the normal case.
_MIGRATIONS = ("ALTER TABLE lessons ADD COLUMN source TEXT NOT NULL DEFAULT ''",)

_STOP = frozenset("la va cua thi cho voi nhe a oi da co khong roi ma nay kia the thoi vay nhi nha".split())
_TOK = re.compile(r"[^\W_]+", re.U)


def db_path() -> Path:
    return Path(cfgmod.STATE_DIR) / "chatbot_reply_policy.sqlite3"


@contextmanager
def _conn():
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # Nhóm đông thì mỗi tin gọi kho nhiều lần: chỉ tạo bảng lần đầu cho mỗi file. File bị xoá giữa chừng
    # (không còn trên đĩa) thì tạo lại.
    fresh = str(p) not in _ready or not p.exists()
    con = sqlite3.connect(str(p), timeout=10)
    con.row_factory = sqlite3.Row
    try:
        if fresh:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(_SCHEMA)
            for sql in _MIGRATIONS:
                try:
                    con.execute(sql)
                except sqlite3.OperationalError:
                    pass        # column already there
            _ready.add(str(p))
        yield con
        con.commit()
    finally:
        con.close()


def _cut(s: Any, n: int = TEXT_MAX) -> str:
    return str(s or "")[:n]


def _row(r: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(r) if r is not None else None


def tokens_of(text: str) -> List[str]:
    """Token chuẩn hoá (bỏ dấu, chữ thường, bỏ chữ đệm) để so độ giống. Trả list đã khử trùng."""
    import chatbot_grounding
    t = chatbot_grounding._bo_dau(str(text or "")).lower()
    out, seen = [], set()
    for w in _TOK.findall(t):
        if len(w) < 2 or w in _STOP or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def _note_write(now: float) -> None:
    """Cứ mỗi PURGE_EVERY lần ghi thì dọn một lượt, để kho tự giữ hạn mà không cần vòng nền."""
    global _writes
    _writes += 1
    if _writes % PURGE_EVERY == 0:
        try:
            purge(now)
        except Exception:      # noqa: BLE001 - dọn hỏng không được làm hỏng đường ghi
            pass


# ============================================================
# Quyết định
# ============================================================
def log_decision(rec: dict, now: Optional[float] = None) -> int:
    """Ghi một quyết định, trả id. Nội dung cắt 400 ký tự."""
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        cur = con.execute(
            "INSERT INTO decisions(bot_id, chat_id, msg_id, ts, text, sender, sender_id, sender_role, address_level,"
            " signals_json, candidate, verdict, score, threshold, reason, mode, silence_code)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(rec.get("bot_id") or ""), str(rec.get("chat_id") or ""), _cut(rec.get("msg_id"), 80),
             float(rec.get("ts") or now), _cut(rec.get("text")), _cut(rec.get("sender"), 120),
             _cut(rec.get("sender_id"), 80), _cut(rec.get("sender_role"), 12), _cut(rec.get("address_level"), 12),
             json.dumps(rec.get("signals") or {}, ensure_ascii=False)[:2000],
             1 if rec.get("candidate") else 0, str(rec.get("verdict") or "silent"),
             rec.get("score"), rec.get("threshold"), _cut(rec.get("reason"), 200),
             _cut(rec.get("mode"), 10), _cut(rec.get("silence_code"), 40)))
        rid = int(cur.lastrowid)
    _note_write(now)
    return rid


def get_decision(decision_id: int) -> Optional[dict]:
    with _lock, _conn() as con:
        return _row(con.execute("SELECT * FROM decisions WHERE id=?", (int(decision_id),)).fetchone())


def recent_decisions(bot_id: str, limit: int = 100, chat_id: str = "", only_silent: bool = False) -> List[dict]:
    q = "SELECT * FROM decisions WHERE bot_id=?"
    args: list = [str(bot_id)]
    if chat_id:
        q += " AND chat_id=?"
        args.append(str(chat_id))
    if only_silent:
        q += " AND verdict='silent'"
    q += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(int(limit or 100), 500)))
    with _lock, _conn() as con:
        return [dict(r) for r in con.execute(q, args).fetchall()]


def last_decision(bot_id: str, chat_id: str) -> Optional[dict]:
    """Quyết định GẦN NHẤT của bot ở một cuộc chat (hòm thư dùng nó để nói "bot im vì sao" dưới tin khách cuối).
    Kho chưa có thì trả None và KHÔNG tạo file."""
    if not db_path().exists():
        return None
    with _lock, _conn() as con:
        r = con.execute("SELECT * FROM decisions WHERE bot_id=? AND chat_id=? ORDER BY id DESC LIMIT 1",
                        (str(bot_id), str(chat_id))).fetchone()
    return dict(r) if r else None


# Mã im mà chủ nên xem lại: bot ĐÃ cân nhắc nói (tin qua cổng thô) nhưng im vì chưa chắc, hết hạn mức, hoặc bộ phán xử lỗi.
# Không gồm `agent_silent` (chính Agent chọn im, có chủ ý) và các luật cứng (tin rác, nhắn người khác...).
HESITANT_CODES = ("judge_silent", "below_threshold", "rate_limited", "rate_limited_user", "policy_error")


def hesitant_chats(since_ts: float, limit: int = 200) -> List[tuple]:
    """(bot_id, chat_id) các cuộc chat mà bot vừa cân nhắc nói rồi im, chưa được chủ gắn nhãn Đúng/Sai. Hòm thư dùng
    nó để biết NHÓM nào đáng gọi là "cần trả lời": trong nhóm mà bot chỉ nói khi được gọi thì khách nhắn cuối là chuyện
    bình thường, không phải việc tồn đọng. Kho chưa từng có (bot chưa bật bộ phán xử) thì trả rỗng và KHÔNG tạo file."""
    if not db_path().exists():
        return []
    ph = ",".join("?" * len(HESITANT_CODES))
    with _lock, _conn() as con:
        rows = con.execute(
            f"SELECT DISTINCT bot_id, chat_id FROM decisions WHERE candidate=1 AND verdict='silent' AND label IS NULL"
            f" AND ts>=? AND silence_code IN ({ph}) ORDER BY ts DESC LIMIT ?",
            [float(since_ts), *HESITANT_CODES, max(1, min(int(limit), 500))]).fetchall()
    return [(str(r["bot_id"]), str(r["chat_id"])) for r in rows]


def set_label(decision_id: int, label: str, weight: float, now: Optional[float] = None) -> Optional[dict]:
    """Gắn nhãn cho một quyết định. Chỉ gắn MỘT lần: nhãn đầu tiên thắng, để một cuộc trò chuyện dài
    không lật đi lật lại kết luận của cùng một ca."""
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        cur = con.execute("UPDATE decisions SET label=?, label_weight=?, label_ts=? WHERE id=? AND label IS NULL",
                          (str(label), float(weight), now, int(decision_id)))
        if cur.rowcount == 0:
            return None
        return _row(con.execute("SELECT * FROM decisions WHERE id=?", (int(decision_id),)).fetchone())


def force_label(decision_id: int, label: str, weight: float, now: Optional[float] = None) -> Optional[dict]:
    """Như `set_label` nhưng ghi đè: dành cho nhãn của CHỦ (👍/👎), nặng hơn nhãn tự động."""
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        cur = con.execute("UPDATE decisions SET label=?, label_weight=?, label_ts=? WHERE id=?",
                          (str(label), float(weight), now, int(decision_id)))
        if cur.rowcount == 0:
            return None
        return _row(con.execute("SELECT * FROM decisions WHERE id=?", (int(decision_id),)).fetchone())


def last_decisions_in_chat(bot_id: str, chat_id: str, since_ts: float, limit: int = 5) -> List[dict]:
    with _lock, _conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM decisions WHERE bot_id=? AND chat_id=? AND ts>=? AND candidate=1"
            " ORDER BY id DESC LIMIT ?", (str(bot_id), str(chat_id), float(since_ts), int(limit))).fetchall()]


# ============================================================
# Cửa theo dõi
# ============================================================
def add_watch(decision_id: int, bot_id: str, chat_id: str, expires_ts: float, messages_left: int) -> None:
    with _lock, _conn() as con:
        con.execute("INSERT OR REPLACE INTO watches(decision_id, bot_id, chat_id, expires_ts, messages_left)"
                    " VALUES(?,?,?,?,?)", (int(decision_id), str(bot_id), str(chat_id),
                                            float(expires_ts), int(messages_left)))


def open_watches(bot_id: str, chat_id: str, now: Optional[float] = None) -> List[dict]:
    """Các quyết định còn đang được theo dõi ở cuộc chat này, kèm nội dung quyết định."""
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        con.execute("DELETE FROM watches WHERE expires_ts<? OR messages_left<=0", (now,))
        rs = con.execute(
            "SELECT d.*, w.expires_ts AS w_expires, w.messages_left AS w_left FROM watches w"
            " JOIN decisions d ON d.id=w.decision_id WHERE w.bot_id=? AND w.chat_id=? AND d.label IS NULL"
            " ORDER BY d.id", (str(bot_id), str(chat_id))).fetchall()
        return [dict(r) for r in rs]


def tick_watch(decision_id: int) -> None:
    with _lock, _conn() as con:
        con.execute("UPDATE watches SET messages_left=messages_left-1 WHERE decision_id=?", (int(decision_id),))


def close_watch(decision_id: int) -> None:
    with _lock, _conn() as con:
        con.execute("DELETE FROM watches WHERE decision_id=?", (int(decision_id),))


# ============================================================
# Ca
# ============================================================
def add_case(bot_id: str, chat_id: str, text: str, features: dict, correct_verdict: str, reason: str,
             source: str, weight: float, origin_case_id: Optional[int] = None,
             now: Optional[float] = None, decision_id: Optional[int] = None) -> int:
    """Thêm một ca và giữ trần: 500 ca mỗi bot, 200 mỗi cuộc chat. Vượt thì bỏ ca có
    `trọng số × độ mới` thấp nhất TRONG PHẠM VI bị vượt (ca do chủ dạy không bao giờ bị bỏ trước)."""
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        cur = con.execute(
            "INSERT INTO cases(bot_id, chat_id, ts, text, tokens, features_json, correct_verdict, reason,"
            " source, weight, origin_case_id, decision_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(bot_id), str(chat_id or ""), now, _cut(text), " ".join(tokens_of(text)),
             json.dumps(features or {}, ensure_ascii=False), str(correct_verdict), _cut(reason, 200),
             str(source), float(weight), origin_case_id, decision_id))
        cid = int(cur.lastrowid)
        _trim_cases(con, str(bot_id), str(chat_id or ""), now)
    _note_write(now)
    return cid


def _trim_cases(con: sqlite3.Connection, bot_id: str, chat_id: str, now: float) -> None:
    def worst(where: str, args: tuple, cap: int) -> None:
        n = con.execute(f"SELECT COUNT(*) FROM cases WHERE {where}", args).fetchone()[0]
        if n <= cap:
            return
        rows = con.execute(f"SELECT id, ts, weight, source FROM cases WHERE {where}", args).fetchall()

        def keep(r) -> float:
            age = max(0.0, now - float(r["ts"])) / 86400.0
            return float(r["weight"]) * (0.5 ** (age / 30.0)) * (100.0 if r["source"] == "owner" else 1.0)

        rows = sorted(rows, key=keep)
        for r in rows[: n - cap]:
            con.execute("DELETE FROM cases WHERE id=?", (r["id"],))

    worst("bot_id=?", (bot_id,), MAX_CASES_PER_BOT)
    if chat_id:
        worst("bot_id=? AND chat_id=?", (bot_id, chat_id), MAX_CASES_PER_CHAT)


def candidate_cases(bot_id: str, limit: int = 600) -> List[dict]:
    with _lock, _conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM cases WHERE bot_id=? ORDER BY id DESC LIMIT ?", (str(bot_id), int(limit))).fetchall()]


def list_cases(bot_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
    with _lock, _conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM cases WHERE bot_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (str(bot_id), max(1, min(int(limit), 500)), max(0, int(offset)))).fetchall()]


def count_cases(bot_id: str, source: str = "") -> int:
    with _lock, _conn() as con:
        if source:
            return int(con.execute("SELECT COUNT(*) FROM cases WHERE bot_id=? AND source=?",
                                   (str(bot_id), source)).fetchone()[0])
        return int(con.execute("SELECT COUNT(*) FROM cases WHERE bot_id=?", (str(bot_id),)).fetchone()[0])


def delete_case(bot_id: str, case_id: int) -> bool:
    with _lock, _conn() as con:
        return con.execute("DELETE FROM cases WHERE id=? AND bot_id=?", (int(case_id), str(bot_id))).rowcount > 0


def delete_cases_by_decision(bot_id: str, decision_id: int) -> int:
    """Xoá các ca sinh ra từ MỘT quyết định (khi chủ đổi nhãn hoặc bấm lại): nhãn của chủ ghi đè, không cộng dồn."""
    with _lock, _conn() as con:
        return con.execute("DELETE FROM cases WHERE bot_id=? AND decision_id=?", (str(bot_id), int(decision_id))).rowcount


def amend_decision(decision_id: int, verdict: str, silence_code: str) -> None:
    """Sửa một quyết định cho đúng sự thật: bộ phán xử nói `reply` nhưng bước sau (hạn mức, Tiếp quản, Agent chọn
    im) đã chặn, nên bot chưa từng nói. Nếu không sửa thì tin nối tiếp sau đó sẽ được gắn nhãn "đúng" cho một
    câu bot không hề gửi."""
    with _lock, _conn() as con:
        con.execute("UPDATE decisions SET verdict=?, silence_code=? WHERE id=?",
                    (str(verdict), str(silence_code)[:40], int(decision_id)))


def delete_cases_by_source(bot_id: str, source: str) -> int:
    with _lock, _conn() as con:
        return con.execute("DELETE FROM cases WHERE bot_id=? AND source=?", (str(bot_id), str(source))).rowcount


def set_case_weight(case_id: int, weight: float) -> None:
    """Hạ trọng số (ca khởi tạo nhạt dần khi có ca thật). Dưới 0.1 thì xoá hẳn."""
    with _lock, _conn() as con:
        if weight < 0.1:
            con.execute("DELETE FROM cases WHERE id=?", (int(case_id),))
        else:
            con.execute("UPDATE cases SET weight=? WHERE id=?", (float(weight), int(case_id)))


# ============================================================
# Ngưỡng theo cuộc chat
# ============================================================
def get_offset(bot_id: str, chat_id: str, now: Optional[float] = None) -> float:
    """Độ lệch ngưỡng của cuộc chat, đã co dần về 0 theo chu kỳ bán rã 14 ngày kể từ lần cập nhật."""
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        r = con.execute("SELECT offset, updated_ts FROM threshold_offsets WHERE bot_id=? AND chat_id=?",
                        (str(bot_id), str(chat_id))).fetchone()
    if not r:
        return 0.0
    age = max(0.0, now - float(r["updated_ts"]))
    return float(r["offset"]) * (0.5 ** (age / OFFSET_HALF_LIFE_S))


def adjust_offset(bot_id: str, chat_id: str, delta: float, now: Optional[float] = None) -> float:
    """Cộng `delta` vào độ lệch (đã tính phần nhạt dần), kẹp trong [-0.25, +0.25]. Trả giá trị mới."""
    now = time.time() if now is None else now
    cur = get_offset(bot_id, chat_id, now)
    new = max(-OFFSET_LIMIT, min(OFFSET_LIMIT, cur + float(delta)))
    with _lock, _conn() as con:
        con.execute("INSERT OR REPLACE INTO threshold_offsets(bot_id, chat_id, offset, updated_ts) VALUES(?,?,?,?)",
                    (str(bot_id), str(chat_id), new, now))
    return new


def list_offsets(bot_id: str) -> List[dict]:
    with _lock, _conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT chat_id, offset, updated_ts FROM threshold_offsets WHERE bot_id=?", (str(bot_id),)).fetchall()]


# ============================================================
# Hồ sơ vai và bài học
# ============================================================
def get_role_profile(bot_id: str) -> Optional[dict]:
    with _lock, _conn() as con:
        return _row(con.execute("SELECT * FROM role_profiles WHERE bot_id=?", (str(bot_id),)).fetchone())


def set_role_profile(bot_id: str, generated_text: str, agent_hash: str, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        con.execute("INSERT OR REPLACE INTO role_profiles(bot_id, generated_text, agent_hash, updated_ts)"
                    " VALUES(?,?,?,?)", (str(bot_id), str(generated_text or "")[:3000], str(agent_hash), now))


def add_lesson(bot_id: str, text: str, now: Optional[float] = None, source: str = "") -> bool:
    """Thêm một bài học (khử trùng, tối đa 15 dòng, dòng cũ nhất rơi ra). True nếu thật sự thêm."""
    return insert_lesson(bot_id, text, now, source) is not None


def insert_lesson(bot_id: str, text: str, now: Optional[float] = None, source: str = "") -> Optional[int]:
    """Like `add_lesson` but returns the new row id (None when empty or a duplicate).

    `source`: '' for the owner's own lessons (taught in the group, or older rows), 'owner_chat' when the owner asked
    Javis in chat, 'review' when the self-review wrote it. Over the cap, machine-written 'review' lessons drop first,
    so the review can never push out what the owner taught."""
    now = time.time() if now is None else now
    line = " ".join(str(text or "").split())[:200]
    if not line:
        return None
    key = " ".join(tokens_of(line))
    with _lock, _conn() as con:
        for r in con.execute("SELECT text FROM lessons WHERE bot_id=?", (str(bot_id),)).fetchall():
            if " ".join(tokens_of(r["text"])) == key:
                return None
        lid = int(con.execute("INSERT INTO lessons(bot_id, text, ts, source) VALUES(?,?,?,?)",
                              (str(bot_id), line, now, str(source or ""))).lastrowid)
        n = con.execute("SELECT COUNT(*) FROM lessons WHERE bot_id=?", (str(bot_id),)).fetchone()[0]
        over = n - MAX_LESSONS
        if over > 0:
            spare = [r[0] for r in con.execute(
                "SELECT id FROM lessons WHERE bot_id=? AND id!=? AND source='review' ORDER BY id LIMIT ?",
                (str(bot_id), lid, over)).fetchall()]
            if len(spare) < over and source == "review":
                # The review may only displace its own lessons. A full list of the owner's lessons wins.
                con.execute("DELETE FROM lessons WHERE id=?", (lid,))
                return None
            if len(spare) < over:
                spare += [r[0] for r in con.execute(
                    "SELECT id FROM lessons WHERE bot_id=? AND id!=? AND source!='review' ORDER BY id LIMIT ?",
                    (str(bot_id), lid, over - len(spare))).fetchall()]
            con.executemany("DELETE FROM lessons WHERE id=?", [(i,) for i in spare])
    return lid


def get_lesson(bot_id: str, lesson_id: int) -> Optional[dict]:
    with _lock, _conn() as con:
        return _row(con.execute("SELECT id, text, ts, source FROM lessons WHERE bot_id=? AND id=?",
                                (str(bot_id), int(lesson_id))).fetchone())


def delete_lesson(bot_id: str, lesson_id: int) -> bool:
    with _lock, _conn() as con:
        return con.execute("DELETE FROM lessons WHERE bot_id=? AND id=?", (str(bot_id), int(lesson_id))).rowcount > 0


def list_lessons(bot_id: str) -> List[dict]:
    with _lock, _conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT id, text, ts, source FROM lessons WHERE bot_id=? ORDER BY id", (str(bot_id),)).fetchall()]


# ============================================================
# Self-review (0.77.0): knobs, change log, review state, metrics
# ============================================================
def get_case(bot_id: str, case_id: int) -> Optional[dict]:
    with _lock, _conn() as con:
        return _row(con.execute("SELECT * FROM cases WHERE bot_id=? AND id=?", (str(bot_id), int(case_id))).fetchone())


def set_offset(bot_id: str, chat_id: str, value: float, now: Optional[float] = None) -> float:
    """Set a chat's threshold offset outright (clamped). It still fades with the same half-life as learned offsets."""
    now = time.time() if now is None else now
    v = max(-OFFSET_LIMIT, min(OFFSET_LIMIT, float(value)))
    with _lock, _conn() as con:
        con.execute("INSERT OR REPLACE INTO threshold_offsets(bot_id, chat_id, offset, updated_ts) VALUES(?,?,?,?)",
                    (str(bot_id), str(chat_id), v, now))
    return v


def get_tuning(bot_id: str) -> Dict[str, str]:
    """Knobs the self-review (or the owner, through chat) has set for a bot. Missing key = engine default.
    A store that was never created returns {} without creating the file."""
    if not db_path().exists():
        return {}
    with _lock, _conn() as con:
        return {r["key"]: r["value"] for r in con.execute(
            "SELECT key, value FROM tuning WHERE bot_id=?", (str(bot_id),)).fetchall()}


def set_tuning(bot_id: str, key: str, value: Optional[str], now: Optional[float] = None) -> None:
    """`value=None` removes the knob (back to the default)."""
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        if value is None:
            con.execute("DELETE FROM tuning WHERE bot_id=? AND key=?", (str(bot_id), str(key)))
        else:
            con.execute("INSERT OR REPLACE INTO tuning(bot_id, key, value, updated_ts) VALUES(?,?,?,?)",
                        (str(bot_id), str(key), str(value), now))


def log_change(rec: dict, now: Optional[float] = None) -> int:
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        return int(con.execute(
            "INSERT INTO changes(bot_id, ts, actor, review_id, op, target, before_json, after_json, reason,"
            " evidence_json, status, status_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(rec.get("bot_id") or ""), now, str(rec.get("actor") or ""), rec.get("review_id") or None,
             str(rec.get("op") or ""), _cut(rec.get("target"), 200),
             json.dumps(rec.get("before"), ensure_ascii=False)[:4000],
             json.dumps(rec.get("after"), ensure_ascii=False)[:4000], _cut(rec.get("reason"), 400),
             json.dumps(rec.get("evidence") or [], ensure_ascii=False)[:1000],
             str(rec.get("status") or "applied"), now)).lastrowid)


def _change_row(r) -> dict:
    d = dict(r)
    for k in ("before_json", "after_json", "evidence_json"):
        try:
            d[k[:-5]] = json.loads(d.pop(k) or "null")
        except ValueError:
            d[k[:-5]] = None
    return d


def get_change(change_id: int) -> Optional[dict]:
    with _lock, _conn() as con:
        r = con.execute("SELECT * FROM changes WHERE id=?", (int(change_id),)).fetchone()
    return _change_row(r) if r else None


def list_changes(bot_id: str = "", limit: int = 50, status: str = "", review_id: str = "",
                 since_ts: float = 0.0) -> List[dict]:
    q, args = "SELECT * FROM changes WHERE ts>=?", [float(since_ts)]
    if bot_id:
        q += " AND bot_id=?"
        args.append(str(bot_id))
    if status:
        q += " AND status=?"
        args.append(str(status))
    if review_id:
        q += " AND review_id=?"
        args.append(str(review_id))
    q += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(int(limit), 500)))
    if not db_path().exists():
        return []
    with _lock, _conn() as con:
        return [_change_row(r) for r in con.execute(q, args).fetchall()]


def set_change_status(change_id: int, status: str, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        con.execute("UPDATE changes SET status=?, status_ts=? WHERE id=?", (str(status), now, int(change_id)))


def get_review_ts(bot_id: str) -> float:
    with _lock, _conn() as con:
        r = con.execute("SELECT last_ts FROM review_state WHERE bot_id=?", (str(bot_id),)).fetchone()
    return float(r["last_ts"]) if r else 0.0


def set_review_ts(bot_id: str, ts: float) -> None:
    with _lock, _conn() as con:
        con.execute("INSERT OR REPLACE INTO review_state(bot_id, last_ts) VALUES(?,?)", (str(bot_id), float(ts)))


def activity_since(since_ts: float) -> List[dict]:
    """Per bot, what happened after `since_ts`: decisions, silent ones, and labels given. Cheap enough for a 30-minute
    tick (one grouped query). A store that was never created returns [] without creating the file."""
    if not db_path().exists():
        return []
    with _lock, _conn() as con:
        rows = con.execute(
            "SELECT bot_id, COUNT(*) AS n, SUM(verdict='silent') AS silent, MIN(ts) AS first_ts FROM decisions"
            " WHERE ts>=? GROUP BY bot_id", (float(since_ts),)).fetchall()
        labels = {r["bot_id"]: int(r["n"]) for r in con.execute(
            "SELECT bot_id, COUNT(*) AS n FROM decisions WHERE label_ts>=? GROUP BY bot_id", (float(since_ts),))}
    return [{"bot_id": r["bot_id"], "decisions": int(r["n"]), "silent": int(r["silent"] or 0),
             "labels": labels.get(r["bot_id"], 0)} for r in rows]


def counts_since(bot_id: str, since_ts: float) -> dict:
    """{'labels': n, 'silent': n} for one bot after `since_ts` (labels counted by when they were given)."""
    with _lock, _conn() as con:
        lab = con.execute("SELECT COUNT(*) FROM decisions WHERE bot_id=? AND label_ts>=?",
                          (str(bot_id), float(since_ts))).fetchone()[0]
        sil = con.execute("SELECT COUNT(*) FROM decisions WHERE bot_id=? AND ts>=? AND verdict='silent'",
                          (str(bot_id), float(since_ts))).fetchone()[0]
    return {"labels": int(lab), "silent": int(sil)}


def label_counts(bot_id: str, since_ts: float, until_ts: float) -> Dict[str, int]:
    """Labels on decisions MADE in [since, until): {'correct': n, 'missed': n, 'intruded': n, 'taught': n}."""
    with _lock, _conn() as con:
        rows = con.execute("SELECT label, COUNT(*) AS n FROM decisions WHERE bot_id=? AND ts>=? AND ts<?"
                           " AND label IS NOT NULL GROUP BY label",
                           (str(bot_id), float(since_ts), float(until_ts))).fetchall()
    return {r["label"]: int(r["n"]) for r in rows}


def decisions_between(bot_id: str, since_ts: float, until_ts: float = 0.0, *, chat_id: str = "", code: str = "",
                      label: str = "", only_silent: bool = False, labeled_wrong: bool = False,
                      limit: int = 50) -> List[dict]:
    """Filtered decision rows, newest first. `labeled_wrong` = labelled missed or intruded."""
    q, args = "SELECT * FROM decisions WHERE bot_id=? AND ts>=?", [str(bot_id), float(since_ts)]
    if until_ts:
        q += " AND ts<?"
        args.append(float(until_ts))
    if chat_id:
        q += " AND chat_id=?"
        args.append(str(chat_id))
    if code:
        q += " AND silence_code=?"
        args.append(str(code))
    if label:
        q += " AND label=?"
        args.append(str(label))
    if only_silent:
        q += " AND verdict='silent'"
    if labeled_wrong:
        q += " AND label IN ('missed','intruded')"
    q += " ORDER BY id DESC LIMIT ?"
    args.append(max(1, min(int(limit), 500)))
    with _lock, _conn() as con:
        return [dict(r) for r in con.execute(q, args).fetchall()]


def summary_between(bot_id: str, since_ts: float, until_ts: float) -> dict:
    """Totals for a report: by verdict, by silence code, by label, and per chat."""
    b, a, z = str(bot_id), float(since_ts), float(until_ts)
    with _lock, _conn() as con:
        verdicts = {r["verdict"]: int(r["n"]) for r in con.execute(
            "SELECT verdict, COUNT(*) AS n FROM decisions WHERE bot_id=? AND ts>=? AND ts<? GROUP BY verdict", (b, a, z))}
        codes = {r["silence_code"] or "": int(r["n"]) for r in con.execute(
            "SELECT silence_code, COUNT(*) AS n FROM decisions WHERE bot_id=? AND ts>=? AND ts<? AND verdict='silent'"
            " GROUP BY silence_code ORDER BY n DESC", (b, a, z))}
        labels = {r["label"]: int(r["n"]) for r in con.execute(
            "SELECT label, COUNT(*) AS n FROM decisions WHERE bot_id=? AND ts>=? AND ts<? AND label IS NOT NULL"
            " GROUP BY label", (b, a, z))}
        chats = [dict(r) for r in con.execute(
            "SELECT chat_id, COUNT(*) AS n, SUM(verdict='silent') AS silent, SUM(label='missed') AS missed,"
            " SUM(label='intruded') AS intruded FROM decisions WHERE bot_id=? AND ts>=? AND ts<?"
            " GROUP BY chat_id ORDER BY n DESC LIMIT 20", (b, a, z))]
    return {"verdicts": verdicts, "codes": codes, "labels": labels, "chats": chats}


# ============================================================
# Quên, xoá, dọn, thống kê
# ============================================================
def forget(bot_id: str, chat_id: str = "", keep_log: bool = False) -> dict:
    """Nút "quên hết": xoá ca, độ lệch, bài học, cửa theo dõi VÀ nhật ký quyết định (đó là chữ chat của khách,
    nên "quên" phải quên thật). Có `chat_id` thì chỉ cuộc chat đó. `keep_log=True` chỉ để giữ dấu vết khi cần."""
    b = str(bot_id)
    with _lock, _conn() as con:
        if chat_id:
            c = str(chat_id)
            n_cases = con.execute("DELETE FROM cases WHERE bot_id=? AND chat_id=? AND source!='bootstrap'",
                                  (b, c)).rowcount
            con.execute("DELETE FROM threshold_offsets WHERE bot_id=? AND chat_id=?", (b, c))
            con.execute("DELETE FROM watches WHERE bot_id=? AND chat_id=?", (b, c))
            if keep_log:
                con.execute("UPDATE decisions SET label=NULL, label_weight=NULL, label_ts=NULL"
                            " WHERE bot_id=? AND chat_id=?", (b, c))
                n_log = 0
            else:
                n_log = con.execute("DELETE FROM decisions WHERE bot_id=? AND chat_id=?", (b, c)).rowcount
            return {"cases": n_cases, "lessons": 0, "decisions": n_log}
        n_cases = con.execute("DELETE FROM cases WHERE bot_id=? AND source!='bootstrap'", (b,)).rowcount
        n_les = con.execute("DELETE FROM lessons WHERE bot_id=?", (b,)).rowcount
        con.execute("DELETE FROM threshold_offsets WHERE bot_id=?", (b,))
        for t in ("tuning", "changes", "review_state"):
            con.execute(f"DELETE FROM {t} WHERE bot_id=?", (b,))
        con.execute("DELETE FROM watches WHERE bot_id=?", (b,))
        if keep_log:
            con.execute("UPDATE decisions SET label=NULL, label_weight=NULL, label_ts=NULL WHERE bot_id=?", (b,))
            n_log = 0
        else:
            n_log = con.execute("DELETE FROM decisions WHERE bot_id=?", (b,)).rowcount
        return {"cases": n_cases, "lessons": n_les, "decisions": n_log}


def delete_bot(bot_id: str) -> None:
    """Xoá sạch mọi thứ của bot. Gọi khi xoá bot."""
    b = str(bot_id)
    with _lock, _conn() as con:
        for t in ("decisions", "cases", "watches", "role_profiles", "threshold_offsets", "lessons", "tuning",
                  "changes", "review_state"):
            con.execute(f"DELETE FROM {t} WHERE bot_id=?", (b,))


def purge(now: Optional[float] = None) -> dict:
    """Giữ hạn: quyết định chưa nhãn 14 ngày, quyết định đã nhãn và ca 180 ngày, cửa theo dõi hết hạn."""
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        a = con.execute("DELETE FROM decisions WHERE label IS NULL AND ts<?", (now - UNLABELED_KEEP_S,)).rowcount
        b = con.execute("DELETE FROM decisions WHERE label IS NOT NULL AND ts<?", (now - LABELED_KEEP_S,)).rowcount
        c = con.execute("DELETE FROM cases WHERE ts<? AND source!='owner'", (now - LABELED_KEEP_S,)).rowcount
        d = con.execute("DELETE FROM watches WHERE expires_ts<?", (now,)).rowcount
    return {"decisions_unlabeled": a, "decisions_labeled": b, "cases": c, "watches": d}


def stats(bot_id: str) -> dict:
    b = str(bot_id)
    with _lock, _conn() as con:
        one = lambda q, *a: int(con.execute(q, a).fetchone()[0])   # noqa: E731
        return {
            "decisions": one("SELECT COUNT(*) FROM decisions WHERE bot_id=?", b),
            "silent": one("SELECT COUNT(*) FROM decisions WHERE bot_id=? AND verdict='silent'", b),
            "labeled": one("SELECT COUNT(*) FROM decisions WHERE bot_id=? AND label IS NOT NULL", b),
            "cases": one("SELECT COUNT(*) FROM cases WHERE bot_id=?", b),
            "cases_bootstrap": one("SELECT COUNT(*) FROM cases WHERE bot_id=? AND source='bootstrap'", b),
            "lessons": one("SELECT COUNT(*) FROM lessons WHERE bot_id=?", b),
        }
