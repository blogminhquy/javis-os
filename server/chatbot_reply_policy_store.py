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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_id TEXT NOT NULL, chat_id TEXT NOT NULL, msg_id TEXT, ts REAL NOT NULL,
  text TEXT, sender TEXT, sender_role TEXT, address_level TEXT, signals_json TEXT,
  candidate INTEGER NOT NULL DEFAULT 0, verdict TEXT NOT NULL, score REAL, threshold REAL,
  reason TEXT, mode TEXT, silence_code TEXT,
  label TEXT, label_weight REAL, label_ts REAL);
CREATE INDEX IF NOT EXISTS idx_dec_bot_ts ON decisions(bot_id, ts);
CREATE INDEX IF NOT EXISTS idx_dec_chat_ts ON decisions(bot_id, chat_id, ts);
CREATE TABLE IF NOT EXISTS cases(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bot_id TEXT NOT NULL, chat_id TEXT, ts REAL NOT NULL, text TEXT, tokens TEXT,
  features_json TEXT, correct_verdict TEXT NOT NULL, reason TEXT,
  source TEXT NOT NULL, weight REAL NOT NULL DEFAULT 1.0, origin_case_id INTEGER);
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
"""

_STOP = frozenset("la va cua thi cho voi nhe a oi da co khong roi ma nay kia the thoi vay nhi nha".split())
_TOK = re.compile(r"[^\W_]+", re.U)


def db_path() -> Path:
    return Path(cfgmod.STATE_DIR) / "chatbot_reply_policy.sqlite3"


@contextmanager
def _conn():
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(_SCHEMA)
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
            "INSERT INTO decisions(bot_id, chat_id, msg_id, ts, text, sender, sender_role, address_level,"
            " signals_json, candidate, verdict, score, threshold, reason, mode, silence_code)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(rec.get("bot_id") or ""), str(rec.get("chat_id") or ""), _cut(rec.get("msg_id"), 80),
             float(rec.get("ts") or now), _cut(rec.get("text")), _cut(rec.get("sender"), 120),
             _cut(rec.get("sender_role"), 12), _cut(rec.get("address_level"), 12),
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
             now: Optional[float] = None) -> int:
    """Thêm một ca và giữ trần: 500 ca mỗi bot, 200 mỗi cuộc chat. Vượt thì bỏ ca có
    `trọng số × độ mới` thấp nhất TRONG PHẠM VI bị vượt (ca do chủ dạy không bao giờ bị bỏ trước)."""
    now = time.time() if now is None else now
    with _lock, _conn() as con:
        cur = con.execute(
            "INSERT INTO cases(bot_id, chat_id, ts, text, tokens, features_json, correct_verdict, reason,"
            " source, weight, origin_case_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (str(bot_id), str(chat_id or ""), now, _cut(text), " ".join(tokens_of(text)),
             json.dumps(features or {}, ensure_ascii=False), str(correct_verdict), _cut(reason, 200),
             str(source), float(weight), origin_case_id))
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


def add_lesson(bot_id: str, text: str, now: Optional[float] = None) -> bool:
    """Thêm một bài học (khử trùng, tối đa 15 dòng, dòng cũ nhất rơi ra). True nếu thật sự thêm."""
    now = time.time() if now is None else now
    line = " ".join(str(text or "").split())[:200]
    if not line:
        return False
    key = " ".join(tokens_of(line))
    with _lock, _conn() as con:
        for r in con.execute("SELECT text FROM lessons WHERE bot_id=?", (str(bot_id),)).fetchall():
            if " ".join(tokens_of(r["text"])) == key:
                return False
        con.execute("INSERT INTO lessons(bot_id, text, ts) VALUES(?,?,?)", (str(bot_id), line, now))
        n = con.execute("SELECT COUNT(*) FROM lessons WHERE bot_id=?", (str(bot_id),)).fetchone()[0]
        if n > MAX_LESSONS:
            con.execute("DELETE FROM lessons WHERE id IN (SELECT id FROM lessons WHERE bot_id=?"
                        " ORDER BY id LIMIT ?)", (str(bot_id), n - MAX_LESSONS))
    return True


def list_lessons(bot_id: str) -> List[dict]:
    with _lock, _conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT id, text, ts FROM lessons WHERE bot_id=? ORDER BY id", (str(bot_id),)).fetchall()]


# ============================================================
# Quên, xoá, dọn, thống kê
# ============================================================
def forget(bot_id: str, chat_id: str = "") -> dict:
    """Nút "quên hết": xoá ca, nhãn, độ lệch, bài học và cửa theo dõi. Có `chat_id` thì chỉ cuộc chat đó.
    Nhật ký quyết định (chưa nhãn) vẫn giữ: đó là dấu vết, không phải thứ đã học."""
    b = str(bot_id)
    with _lock, _conn() as con:
        if chat_id:
            c = str(chat_id)
            n_cases = con.execute("DELETE FROM cases WHERE bot_id=? AND chat_id=? AND source!='bootstrap'",
                                  (b, c)).rowcount
            con.execute("DELETE FROM threshold_offsets WHERE bot_id=? AND chat_id=?", (b, c))
            con.execute("DELETE FROM watches WHERE bot_id=? AND chat_id=?", (b, c))
            con.execute("UPDATE decisions SET label=NULL, label_weight=NULL, label_ts=NULL"
                        " WHERE bot_id=? AND chat_id=?", (b, c))
            return {"cases": n_cases, "lessons": 0}
        n_cases = con.execute("DELETE FROM cases WHERE bot_id=? AND source!='bootstrap'", (b,)).rowcount
        n_les = con.execute("DELETE FROM lessons WHERE bot_id=?", (b,)).rowcount
        con.execute("DELETE FROM threshold_offsets WHERE bot_id=?", (b,))
        con.execute("DELETE FROM watches WHERE bot_id=?", (b,))
        con.execute("UPDATE decisions SET label=NULL, label_weight=NULL, label_ts=NULL WHERE bot_id=?", (b,))
        return {"cases": n_cases, "lessons": n_les}


def delete_bot(bot_id: str) -> None:
    """Xoá sạch mọi thứ của bot. Gọi khi xoá bot."""
    b = str(bot_id)
    with _lock, _conn() as con:
        for t in ("decisions", "cases", "watches", "role_profiles", "threshold_offsets", "lessons"):
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
