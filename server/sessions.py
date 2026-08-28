"""
Conversation-session persistence cho Javis OS.

Lưu hội thoại web-chat (lượt user/assistant của MỌI engine: cli / codex /
openrouter / openai / anthropic-api) vào 1 file SQLite để dashboard có thể
LIST / RESUME / SEARCH / rename / delete các phiên cũ.

Stdlib-only (sqlite3 + threading). KHÔNG thêm dependency.

Thiết kế port từ Hermes `hermes_state.py` SessionDB:
  - WAL + BEGIN IMMEDIATE + jitter-retry write executor   (hermes_state.py:1055)
  - FTS5 mirror table qua trigger                          (hermes_state.py:738)
  - Probe FTS5 lúc chạy -> fallback LIKE                   (hermes_state.py:955)

Phân biệt 3 loại id:
  - conv id (uuid hex)  : phiên hội thoại dashboard quản lý (engine-agnostic).
  - cli_session_id      : session_id RIÊNG của Claude CLI (để --resume).
  - codex_thread_id     : thread_id RIÊNG của Codex CLI/OpenAI OAuth (để `exec resume`).
"""
from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# DB nằm cùng nơi settings.json/.sessions.json (JAVIS_STATE_DIR, mặc định server/).
_STATE_DIR = Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent)))
_DEFAULT_DB = _STATE_DIR / "conversations.db"
DB_PATH = Path(os.getenv("JAVIS_SESSIONS_DB", str(_DEFAULT_DB)))


def loc_brain(brain, cot: str = "s.brain"):
    """(mệnh_đề_WHERE, params) cho bộ lọc brain. ("", []) nghĩa là không lọc.

    `brain` nhận MỘT chuỗi hoặc DANH SÁCH chuỗi cùng trỏ về một brain, vì cột `brain` giữ
    nguyên văn thứ mà chỗ tạo phiên truyền vào và các kênh không viết giống nhau: dashboard
    gửi tên gọi tắt "brain" cho brain mặc định, còn Telegram (`/brain`) và loop lưu ĐƯỜNG DẪN
    TUYỆT ĐỐI của đúng brain đó. So bằng một chuỗi duy nhất thì hai bên không bao giờ gặp
    nhau - hội thoại Telegram vẫn lưu đủ nhưng biến mất khỏi thanh bên lẫn ô tìm kiếm, và
    người dùng thấy đúng như "Javis không lưu phiên chat từ Telegram" (báo 23/08).
    Bên gọi dựng danh sách bí danh (main.py::_brain_keys); ở đây chỉ lo phần SQL.
    """
    if not brain:
        return "", []
    keys = brain if isinstance(brain, (list, tuple, set)) else [brain]
    keys = list(dict.fromkeys(str(k) for k in keys if k))
    if not keys:
        return "", []
    if len(keys) == 1:
        return f"{cot} = ?", keys
    return f"{cot} IN ({','.join('?' * len(keys))})", keys


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id             TEXT PRIMARY KEY,
    title          TEXT,
    brain          TEXT NOT NULL DEFAULT 'brain',
    engine         TEXT,
    model          TEXT,
    channel        TEXT NOT NULL DEFAULT 'web',
    cli_session_id TEXT,
    codex_thread_id TEXT,
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL,
    msg_count      INTEGER NOT NULL DEFAULT 0,
    parent_session_id TEXT,
    archived       INTEGER NOT NULL DEFAULT 0,
    compact_summary TEXT,
    compact_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT,
    ts              REAL NOT NULL,
    tool_calls_json TEXT
);

-- Project = nhóm hội thoại do người dùng tự gom (ý "gom hội thoại thành Project").
-- KHÔNG khai REFERENCES ở cột sessions.project_id: cột đó thêm bằng ALTER TABLE cho DB cũ,
-- mà SQLite không cho ALTER kèm khoá ngoại. Ràng buộc được giữ ở tầng code: xoá project là
-- GỠ NHÃN các hội thoại về NULL, không bao giờ xoá hội thoại theo.
CREATE TABLE IF NOT EXISTS projects (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    icon       TEXT,
    brain      TEXT NOT NULL DEFAULT 'brain',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_brain   ON sessions(brain, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_projects_brain   ON projects(brain, updated_at DESC);
"""

# FTS5 mirror giữ đồng bộ qua trigger (shape port từ hermes_state.py:738-761).
_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content);

CREATE TRIGGER IF NOT EXISTS messages_fts_ins AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, COALESCE(new.content, ''));
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_del AFTER DELETE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_upd AFTER UPDATE ON messages BEGIN
    DELETE FROM messages_fts WHERE rowid = old.id;
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, COALESCE(new.content, ''));
END;
"""


# ============================================
# Đặt tên hội thoại
# ============================================
# Khối ngữ cảnh dashboard tự chèn TRƯỚC câu hỏi khi user đính kèm file (app.js). Hai dạng:
#   [File đính kèm để ĐỌC (đường dẫn): ... ]
#   [File đính kèm (đường dẫn), Sources="...", Attachments="...": ... ]
# Neo vào đúng cụm "File đính kèm" chứ KHÔNG bóc mọi khối [..] mở đầu - người dùng có quyền
# mở câu bằng ngoặc vuông ("[gấp] xem giúp anh..."), bóc bừa là mất luôn phần quan trọng nhất.
_KHOI_DINH_KEM = re.compile(r"^\s*\[File đính kèm[^\]]*\]\s*")
# Khối "file đang ghim trong trình sửa" (app.js chèn khi user mở một file .md rồi chat). Cùng
# LOẠI với khối đính kèm ở trên, nhưng là một CỬA KHÁC: nó ra đời sau bản vá 2026-07-31 nên
# lọt qua, và hậu quả giống hệt - mọi hội thoại mở lúc đang ghim file đều mang đúng một cái
# tên "[FILE ĐANG MỞ trong trình sửa của Javis: /home/…". Ghim còn được gửi lại MỖI LƯỢT nên
# nó phổ biến hơn khối đính kèm nhiều.
_KHOI_GHIM = re.compile(r"^\s*\[FILE ĐANG MỞ[^\]]*\]\s*")
# Câu dashboard tự điền khi user đính kèm file mà KHÔNG gõ gì - không mang thông tin gì.
_CAU_TU_DIEN = "Hãy đọc (các) file trên và phản hồi / tóm tắt nội dung chính."
# File đính kèm được app.js liệt kê mỗi dòng một cái, dạng "- <đường dẫn>". Neo vào ĐÚNG dạng
# đó, đừng quét mọi thứ trông giống đường dẫn trong khối: dạng có Sources="..."/Attachments="..."
# sẽ lọt hai thư mục cấu hình vào, ra tên kiểu "My +4 file" (lặp y hệt ở mọi hội thoại).
_DONG_FILE = re.compile(r"^\s*-\s+(\S.*?)\s*$", re.M)
TITLE_MAX = 48


def _cat_gon(s: str, gioi_han: int = TITLE_MAX) -> str:
    """Cắt ở RANH GIỚI TỪ. Cắt giữa chữ ra 'File đính kèm để ĐỌC (đườn…' - vừa xấu vừa khó đoán."""
    s = s.strip()
    if len(s) <= gioi_han:
        return s
    cut = s[:gioi_han + 1]
    khoang = cut.rfind(" ")
    if khoang >= gioi_han // 2:          # có chỗ ngắt tử tế thì dùng, không thì đành cắt cứng
        cut = cut[:khoang]
    else:
        cut = cut[:gioi_han]
    return cut.rstrip(" ,.;:-") + "…"


def title_from_message(msg: str, gioi_han: int = TITLE_MAX) -> str:
    """Câu hỏi đầu của user -> tên hội thoại ngắn, THEO NỘI DUNG.

    Vì sao có hàm này: trước đây title = 48 ký tự đầu của tin nhắn thô. Mà khi user đính kèm
    file, dashboard chèn sẵn một khối hướng dẫn dài trước câu hỏi, nên MỌI hội thoại có file
    đều mang đúng một cái tên "[File đính kèm để ĐỌC (đườn…" - nhìn danh sách Lịch sử không
    phân biệt nổi cái nào là cái nào (đúng lỗi chủ repo báo 2026-07-31).

    Thứ tự ưu tiên: câu user THỰC SỰ gõ > tên file đính kèm > chịu thua trả rỗng.
    """
    raw = msg or ""
    # Bóc LẶP và bóc CẢ HAI loại khối: ghim đi trước đính kèm nên chúng lồng nhau được, mà
    # bóc đúng một lần thì tên hội thoại vẫn là chữ máy của khối còn lại.
    #
    # Giữ lại khối đính kèm vừa bóc ngay TẠI ĐÂY thay vì tìm lại trong `raw` ở dưới: cả hai
    # mẫu đều neo `^`, nên khi khối ghim đứng trước thì tìm lại trong `raw` luôn trượt - và
    # trượt lặng lẽ, hậu quả là hội thoại "chỉ đính kèm file" mất tên thay vì mang tên file.
    con_lai, khoi_dk = raw, ""
    for _ in range(4):
        truoc = con_lai
        con_lai = _KHOI_GHIM.sub("", con_lai, count=1)
        m_dk = _KHOI_DINH_KEM.match(con_lai)
        if m_dk:
            khoi_dk = m_dk.group(0)
            con_lai = con_lai[m_dk.end():]
        if con_lai == truoc:
            break
    co_dinh_kem = bool(khoi_dk)

    tho = con_lai.replace(_CAU_TU_DIEN, " ").strip()
    if tho.strip():
        # Ngắt ý TRƯỚC khi gộp khoảng trắng, nếu không thì xuống dòng biến mất và tin nhiều
        # dòng dính thành một chuỗi dài. Ngắt ở xuống dòng hoặc dấu kết câu; KHÔNG ngắt ở dấu
        # chấm - tiếng Việt chấm nhiều, ngắt ở đó thì "Chào em. Doanh thu?" chỉ còn "Chào em".
        y_dau = " ".join(re.split(r"\n+|(?<=[?!。])\s+", tho, maxsplit=1)[0].split())
        ca_bai = " ".join(tho.split())
        if ca_bai:
            # Ý đầu quá cụt (dưới 8 ký tự) thì nó không nói lên chủ đề - lấy cả bài rồi cắt.
            return _cat_gon(y_dau if 8 <= len(y_dau) else ca_bai, gioi_han)

    # Chỉ đính kèm, không gõ chữ nào -> tên file còn nói được nhiều hơn khối hướng dẫn.
    if co_dinh_kem:
        duong_dan = _DONG_FILE.findall(khoi_dk)
        # rstrip("]"): dạng có Sources= đóng khối NGAY sau đường dẫn cuối ("- /tmp/a.png]"),
        # không bóc thì tên file dính dấu ngoặc.
        ten = [re.split(r"[/\\]", p.rstrip("]").rstrip("/\\"))[-1] for p in duong_dan]
        ten = [t for t in ten if t]
        if ten:
            return _cat_gon(ten[0] if len(ten) == 1 else f"{ten[0]} +{len(ten) - 1} file", gioi_han)
        return "File đính kèm"
    return ""


# Tên icon Lucide: chữ thường, số và gạch nối (vd "message-circle"). Cột `projects.icon` lưu
# TÊN icon chứ không phải ký tự emoji: icon Lucide tự đổi màu theo tông sáng/tối và vẽ giống
# nhau trên mọi máy.
#
# CHỈ project mới có icon. Hội thoại thì không: hàng nào trong danh sách cũng là một cuộc trò
# chuyện nên icon ở đó không phân loại được gì, chỉ thêm một nút phải bấm. Icon để PHÂN LOẠI
# thuộc về Project, nơi mỗi nhóm thật sự là một thứ khác nhau.
_ICON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def _sach_icon(icon: Optional[str]) -> Optional[str]:
    """Chuẩn hoá tên icon; rỗng hoặc sai khuôn -> None (tức là GỠ icon).

    Không cần biết bộ icon hiện có những tên nào: dashboard chỉ đưa ra tên có thật, còn tên
    lạ (bộ icon đổi giữa hai phiên bản, hay ai đó sửa tay DB) thì phía hiển thị đã tự bỏ qua.
    Việc của hàm này là chặn dạng RÁC lọt vào cột - nhất là chuỗi dài hay ký tự lạ.
    """
    v = (icon or "").strip().lower()
    return v if _ICON_RE.match(v) else None


class SessionStore:
    """Kho hội thoại SQLite thread-safe (1 connection + app-lock, WAL)."""

    _WRITE_MAX_RETRIES = 12
    _RETRY_MIN_S = 0.020
    _RETRY_MAX_S = 0.150

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._fts_enabled = False
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,   # truy cập từ threadpool worker của FastAPI
            timeout=1.0,               # ngắn; tự retry với jitter
            isolation_level=None,      # tự quản BEGIN/COMMIT
        )
        self._conn.row_factory = sqlite3.Row
        self._apply_wal()
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # ── connection setup ──

    def _apply_wal(self) -> None:
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            try:
                self._conn.execute("PRAGMA journal_mode=DELETE")
            except sqlite3.OperationalError:
                pass

    def _probe_fts5(self) -> bool:
        try:
            self._conn.execute("CREATE VIRTUAL TABLE temp._fts5_probe USING fts5(x)")
            self._conn.execute("DROP TABLE temp._fts5_probe")
            return True
        except sqlite3.OperationalError:
            return False

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA_SQL)
            # Migration cột mới cho DB cũ (CREATE IF NOT EXISTS không tự thêm cột)
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(sessions)").fetchall()}
            for name, ddl in (("codex_thread_id", "TEXT"),
                              ("compact_summary", "TEXT"),
                              ("compact_count", "INTEGER NOT NULL DEFAULT 0"),
                              ("channel", "TEXT NOT NULL DEFAULT 'web'"),
                              # Token VÀO của lượt gần nhất. Engine gói thuê bao (Claude Code,
                              # Codex) tự quản mạch hội thoại của chúng, nên Javis không nhìn
                              # thấy thread phình tới đâu - trừ chính con số này. Nó là dấu
                              # hiệu DUY NHẤT để biết khi nào phải bắt đầu mạch mới.
                              ("last_input_tokens", "INTEGER NOT NULL DEFAULT 0"),
                              # msg_count tại lần xoay mạch gần nhất. Có để chống XOAY LIÊN
                              # TỤC: token vào của engine thuê bao phần lớn đến từ vòng lặp
                              # agentic bên trong nó, không phải từ độ dài mạch. Nếu một lượt
                              # nặng sinh ra bởi vòng lặp chứ không bởi mạch dài, xoay xong
                              # lượt sau vẫn nặng, và không có mốc này thì Javis xoay mãi -
                              # phá mạch hội thoại mỗi lượt mà chẳng tiết kiệm được gì.
                              ("thread_rotated_msg", "INTEGER NOT NULL DEFAULT 0"),
                              # Ghim hội thoại lên đầu danh sách. Cuộc dùng đi dùng lại không
                              # bị trôi xuống dưới theo thời gian nữa.
                              ("pinned", "INTEGER NOT NULL DEFAULT 0"),
                              # Project (nhóm) đang chứa hội thoại. NULL = chưa xếp vào đâu.
                              ("project_id", "TEXT"),
                              # Mạch native của Gemini CLI (UUID). Cùng vai với codex_thread_id
                              # nhưng phải là cột RIÊNG: đổi bộ não giữa chừng mà dùng chung một
                              # cột là lượt sau đưa UUID của engine này cho engine kia resume.
                              ("gemini_session_id", "TEXT"),
                              # Mạch native của Grok Build CLI. Cột RIÊNG, cùng lý do như
                              # gemini_session_id ngay trên: đổi bộ não giữa chừng mà dùng
                              # chung một cột là lượt sau đưa id của engine này cho engine kia
                              # resume, và nó nối vào một mạch không tồn tại rồi hỏng câm.
                              ("grok_session_id", "TEXT"),
                              # Model GHIM RIÊNG của phiên. Hai nguồn ghi: user đổi model ngay
                              # trong phiên, và từ 0.35.5 server tự ĐÓNG DẤU model đang chạy ở
                              # lượt dashboard đầu tiên - nên đổi mặc định chung không bao giờ
                              # đổi ngược cuộc đang dở. KHÔNG tái dùng cột engine/model sẵn có:
                              # hai cột đó là NHẬT KÝ lượt cuối, bị get_or_create ghi đè mỗi
                              # lượt. NULL/rỗng = phiên chưa có lượt dashboard nào (hoặc phiên
                              # Telegram) → theo mặc định chung ở settings.json.
                              ("pinned_provider", "TEXT"),
                              ("pinned_model", "TEXT")):
                if name not in cols:
                    self._conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {ddl}")
            # Index cho cột vừa thêm phải chạy SAU vòng ALTER: DB cũ chưa có cột thì CREATE
            # INDEX ở _SCHEMA_SQL sẽ ném "no such column" và huỷ cả lượt khởi tạo schema.
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_project "
                "ON sessions(project_id, updated_at DESC)")
            if self._probe_fts5():
                try:
                    self._conn.executescript(_FTS_SQL)
                    self._fts_enabled = True
                except sqlite3.OperationalError:
                    self._fts_enabled = False

    # ── write executor (BEGIN IMMEDIATE + jitter retry, hermes_state.py:1055) ──

    def _write(self, fn):
        last_err: Optional[Exception] = None
        for attempt in range(self._WRITE_MAX_RETRIES):
            try:
                with self._lock:
                    self._conn.execute("BEGIN IMMEDIATE")
                    try:
                        result = fn(self._conn)
                        self._conn.commit()
                        return result
                    except BaseException:
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                        raise
            except sqlite3.OperationalError as exc:
                msg = str(exc).lower()
                if ("locked" in msg or "busy" in msg) and attempt < self._WRITE_MAX_RETRIES - 1:
                    last_err = exc
                    time.sleep(random.uniform(self._RETRY_MIN_S, self._RETRY_MAX_S))
                    continue
                raise
        raise last_err or sqlite3.OperationalError("database is locked after retries")

    def _read(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ── sessions ──

    def create_session(self, brain: str = "brain", engine: Optional[str] = None,
                        model: Optional[str] = None, title: Optional[str] = None,
                        session_id: Optional[str] = None,
                        cli_session_id: Optional[str] = None,
                        codex_thread_id: Optional[str] = None,
                        channel: str = "web") -> str:
        sid = session_id or uuid.uuid4().hex
        now = time.time()

        def _do(conn):
            conn.execute(
                """INSERT INTO sessions
                   (id, title, brain, engine, model, channel, cli_session_id, codex_thread_id,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO NOTHING""",
                (sid, title, brain, engine, model, channel or "web", cli_session_id,
                 codex_thread_id, now, now),
            )
        self._write(_do)
        return sid

    def get_or_create(self, session_id: Optional[str], *, brain: str,
                      engine: str, model: Optional[str]) -> str:
        """Resume phiên cũ hoặc tạo mới. Trả về conv id.
        Backward compatible: session_id None/không tồn tại -> tạo phiên mới."""
        if session_id:
            if self.get_session(session_id):
                self._write(lambda c: c.execute(
                    "UPDATE sessions SET engine=?, model=?, updated_at=? WHERE id=?",
                    (engine, model, time.time(), session_id),
                ))
                return session_id
        return self.create_session(brain=brain, engine=engine, model=model,
                                   session_id=session_id)

    def append_message(self, session_id: str, role: str, content: Optional[str],
                       tool_calls: Any = None) -> int:
        tc_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
        stored = content if (content is None or isinstance(content, str)) \
            else json.dumps(content, ensure_ascii=False)
        now = time.time()

        def _do(conn):
            cur = conn.execute(
                "INSERT INTO messages (session_id, role, content, ts, tool_calls_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, role, stored, now, tc_json),
            )
            conn.execute(
                "UPDATE sessions SET msg_count = msg_count + 1, updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            return cur.lastrowid
        return self._write(_do)

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        rows = self._read("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return dict(rows[0]) if rows else None

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        rows = self._read(
            "SELECT id, role, content, ts, tool_calls_json FROM messages "
            "WHERE session_id = ? ORDER BY ts, id",
            (session_id,),
        )
        out = []
        for r in rows:
            d = dict(r)
            if d.get("tool_calls_json"):
                try:
                    d["tool_calls"] = json.loads(d["tool_calls_json"])
                except Exception:
                    d["tool_calls"] = None
            d.pop("tool_calls_json", None)
            out.append(d)
        return out

    def list_sessions(self, limit: int = 50, brain: Any = None,
                      include_archived: bool = False,
                      project: Optional[str] = None) -> List[Dict[str, Any]]:
        """Danh sách hội thoại, MỤC GHIM luôn nằm trên đầu.

        `project`: bỏ trống = tất cả; "none" = các cuộc chưa xếp vào project nào;
        còn lại = đúng project đó. Giá trị "none" là chuỗi cố định chứ không phải id thật -
        id project là uuid hex nên không bao giờ đụng.

        `brain`: một chuỗi, hoặc DANH SÁCH các cách viết cùng trỏ về một brain (xem
        `loc_brain`).
        """
        where = []
        params: list = []
        cond, bparams = loc_brain(brain)
        if cond:
            where.append(cond)
            params += bparams
        if not include_archived:
            where.append("s.archived = 0")
        if project == "none":
            where.append("(s.project_id IS NULL OR s.project_id = '')")
        elif project:
            where.append("s.project_id = ?")
            params.append(project)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        params.append(limit)
        rows = self._read(
            f"""
            SELECT s.id, s.title, s.brain, s.engine, s.model, s.channel, s.cli_session_id,
                   s.created_at, s.updated_at, s.msg_count,
                   s.pinned, s.project_id, s.pinned_provider, s.pinned_model,
                   (SELECT substr(content, 1, 80) FROM messages
                    WHERE session_id = s.id AND role = 'user'
                    ORDER BY ts, id LIMIT 1) AS preview
            FROM sessions s
            {where_sql}
            ORDER BY s.pinned DESC, s.updated_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        return [dict(r) for r in rows]

    # ── ghim / icon / project của một hội thoại ──

    def set_pinned(self, session_id: str, pinned: bool = True) -> None:
        """Ghim hay bỏ ghim. KHÔNG đụng updated_at: ghim không phải là 'vừa nói chuyện',
        đẩy mốc lên là xáo trộn thứ tự của mọi cuộc còn lại một cách vô cớ."""
        self._write(lambda c: c.execute(
            "UPDATE sessions SET pinned = ? WHERE id = ?",
            (1 if pinned else 0, session_id),
        ))

    def set_project(self, session_id: str, project_id: Optional[str], *,
                    brain: Optional[str] = None) -> bool:
        """Xếp hội thoại vào project. project_id rỗng = gỡ khỏi mọi project.

        `brain` khác None thì TẠO hàng nếu chưa có. Vì sao cần: dashboard tự sinh id hội thoại
        ở phía client ngay lúc bấm gửi (dashboard/app.js), còn hàng trong DB thì tới lượt
        server xử lý mới có. Muốn "đang mở project nào thì chat mới rơi vào project đó" thì
        phải gắn nhãn được ngay lúc đó. create_session dùng ON CONFLICT DO NOTHING nên hai
        đường tạo cùng lúc không giẫm nhau.

        Trả về True nếu có hàng để gắn nhãn.
        """
        pid = (project_id or "").strip() or None
        if brain and not self.get_session(session_id):
            self.create_session(brain=brain, session_id=session_id)
        if not self.get_session(session_id):
            return False
        self._write(lambda c: c.execute(
            "UPDATE sessions SET project_id = ? WHERE id = ?", (pid, session_id)))
        return True

    def set_pinned_model(self, session_id: str, provider: Optional[str],
                         model: Optional[str], *, brain: Optional[str] = None) -> bool:
        """Ghim model riêng cho MỘT phiên (provider rỗng = gỡ ghim, phiên quay về mặc
        định chung). Cùng khuôn set_project: `brain` khác None thì tạo hàng nếu phiên
        chưa kịp tồn tại - dashboard mint id phía client, user có thể đổi model trước
        khi gửi tin đầu tiên."""
        prov = (provider or "").strip() or None
        mdl = (model or "").strip() or None
        if prov is None:
            mdl = None   # gỡ ghim là gỡ cả cặp - model mồ côi không định tuyến được
        if brain and not self.get_session(session_id):
            self.create_session(brain=brain, session_id=session_id)
        if not self.get_session(session_id):
            return False
        self._write(lambda c: c.execute(
            "UPDATE sessions SET pinned_provider = ?, pinned_model = ? WHERE id = ?",
            (prov, mdl, session_id)))
        return True

    # ── projects (nhóm hội thoại) ──

    def create_project(self, name: str, *, icon: str = "", brain: str = "brain") -> str:
        pid = uuid.uuid4().hex
        now = time.time()
        self._write(lambda c: c.execute(
            "INSERT INTO projects (id, name, icon, brain, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (pid, (name or "").strip()[:80] or "Project", _sach_icon(icon),
             brain or "brain", now, now),
        ))
        return pid

    def list_projects(self, brain: Optional[str] = None) -> List[Dict[str, Any]]:
        """Project kèm số hội thoại đang nằm trong đó (đếm cả cuộc đã cất vào kho lưu:
        con số này để người dùng biết xoá project sẽ gỡ nhãn bao nhiêu cuộc)."""
        where_sql, params = ("WHERE p.brain = ?", (brain,)) if brain else ("", ())
        rows = self._read(
            f"""
            SELECT p.id, p.name, p.icon, p.brain, p.created_at, p.updated_at,
                   (SELECT COUNT(*) FROM sessions s WHERE s.project_id = p.id) AS session_count
            FROM projects p
            {where_sql}
            ORDER BY p.updated_at DESC
            """,
            params,
        )
        return [dict(r) for r in rows]

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        rows = self._read("SELECT * FROM projects WHERE id = ?", (project_id,))
        return dict(rows[0]) if rows else None

    def update_project(self, project_id: str, *, name: Optional[str] = None,
                       icon: Optional[str] = None) -> None:
        """Đổi tên và/hoặc icon. Tham số None = không đụng tới; icon = "" là GỠ icon."""
        sets, params = [], []
        if name is not None:
            n = (name or "").strip()[:80]
            if n:
                sets.append("name = ?")
                params.append(n)
        if icon is not None:
            sets.append("icon = ?")
            params.append(_sach_icon(icon))
        if not sets:
            return
        sets.append("updated_at = ?")
        params += [time.time(), project_id]
        self._write(lambda c: c.execute(
            f"UPDATE projects SET {', '.join(sets)} WHERE id = ?", tuple(params)))

    def delete_project(self, project_id: str) -> int:
        """Xoá project và GỠ NHÃN các hội thoại về NULL. Trả số hội thoại được gỡ.

        Xoá project KHÔNG xoá hội thoại. Người dùng gom nhóm để đỡ rối, không phải để một cú
        bấm nhầm mất cả tháng trò chuyện - và không có đường hoàn tác nào cả.
        Cả hai bước trong MỘT transaction: gỡ nhãn xong mà xoá lỗi thì hội thoại mồ côi im lặng.
        """
        def _do(conn):
            cur = conn.execute("UPDATE sessions SET project_id = NULL WHERE project_id = ?",
                               (project_id,))
            n = cur.rowcount or 0
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return n
        return self._write(_do)

    def rename(self, session_id: str, title: str) -> None:
        self._write(lambda c: c.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            ((title or "").strip()[:120], time.time(), session_id),
        ))

    def delete(self, session_id: str) -> None:
        # ON DELETE CASCADE xoá messages; trigger dọn messages_fts.
        self._write(lambda c: c.execute("DELETE FROM sessions WHERE id = ?", (session_id,)))

    def archive(self, session_id: str, archived: bool = True) -> None:
        self._write(lambda c: c.execute(
            "UPDATE sessions SET archived = ?, updated_at = ? WHERE id = ?",
            (1 if archived else 0, time.time(), session_id),
        ))

    def archive_stale(self, channel: str, before_ts: float) -> int:
        """Tự cất các phiên NGUỘI của 1 kênh vào kho lưu (archived=1). Trả số phiên đã cất.

        Kênh nhắn tin (Telegram) xoay phiên liên tục nên danh sách hội thoại phình theo
        thời gian dù mỗi phiên đều nhỏ. Cất phiên cũ đi cho thanh bên còn đọc được; dữ
        liệu KHÔNG mất - vẫn tra được qua search và qua list_sessions(include_archived=True).
        """
        def _do(conn):
            cur = conn.execute(
                "UPDATE sessions SET archived = 1 "
                "WHERE channel = ? AND archived = 0 AND updated_at < ?",
                (channel, float(before_ts)),
            )
            return cur.rowcount or 0
        return self._write(_do)

    def set_compact(self, session_id: str, summary: str, count: int) -> None:
        """Lưu tóm tắt nén hội thoại: summary phủ `count` message user/assistant đầu phiên."""
        self._write(lambda c: c.execute(
            "UPDATE sessions SET compact_summary = ?, compact_count = ? WHERE id = ?",
            (summary, int(count), session_id),
        ))

    def set_last_input_tokens(self, session_id: str, tokens: int) -> None:
        """Ghi token VÀO của lượt vừa xong. Xem cột cùng tên ở phần migration."""
        self._write(lambda c: c.execute(
            "UPDATE sessions SET last_input_tokens = ? WHERE id = ?",
            (max(0, int(tokens or 0)), session_id),
        ))

    def mark_thread_rotated(self, session_id: str) -> None:
        """Ghi mốc msg_count lúc vừa xoay mạch. Xem cột thread_rotated_msg ở migration."""
        self._write(lambda c: c.execute(
            "UPDATE sessions SET thread_rotated_msg = msg_count WHERE id = ?",
            (session_id,),
        ))

    def set_cli_session_id(self, session_id: str, cli_session_id: str) -> None:
        """Gắn mạch native của Claude Code. Truyền rỗng KHÔNG xoá - dùng clear_cli_session_id().

        Cái bẫy này đã cắn thật: `set_cli_session_id(sid, "")` được gọi ở đường tắt với ý
        định XOÁ mạch, và cả một comment dài bên đó giải thích vì sao phải xoá. Nhưng dòng
        `if not ...: return` ngay dưới làm nó thành lệnh rỗng, im lặng. Hệ quả: lượt Claude
        kế tiếp nối lại đúng cái mạch KHÔNG chứa lượt vừa rồi.
        """
        if not cli_session_id:
            return
        self._write(lambda c: c.execute(
            "UPDATE sessions SET cli_session_id = ?, updated_at = ? WHERE id = ?",
            (cli_session_id, time.time(), session_id),
        ))

    def set_codex_thread_id(self, session_id: str, thread_id: str) -> None:
        """Gắn thread native của Codex vào hội thoại dashboard để lượt sau resume đúng mạch."""
        if not thread_id:
            return
        self._write(lambda c: c.execute(
            "UPDATE sessions SET codex_thread_id = ?, updated_at = ? WHERE id = ?",
            (thread_id, time.time(), session_id),
        ))

    def clear_codex_thread_id(self, session_id: str) -> None:
        """Thread Codex thành stale khi provider khác chen lượt vào cùng hội thoại."""
        self._write(lambda c: c.execute(
            "UPDATE sessions SET codex_thread_id = NULL WHERE id = ? AND codex_thread_id IS NOT NULL",
            (session_id,),
        ))

    def clear_cli_session_id(self, session_id: str) -> None:
        """Mạch Claude Code thành stale khi engine khác chen một lượt vào cùng hội thoại."""
        self._write(lambda c: c.execute(
            "UPDATE sessions SET cli_session_id = NULL "
            "WHERE id = ? AND cli_session_id IS NOT NULL",
            (session_id,),
        ))

    def set_gemini_session_id(self, session_id: str, gemini_id: str) -> None:
        """Gắn mạch native của Gemini CLI vào hội thoại để lượt sau `--resume` đúng chỗ."""
        if not gemini_id:
            return
        self._write(lambda c: c.execute(
            "UPDATE sessions SET gemini_session_id = ?, updated_at = ? WHERE id = ?",
            (gemini_id, time.time(), session_id),
        ))

    def clear_gemini_session_id(self, session_id: str) -> None:
        self._write(lambda c: c.execute(
            "UPDATE sessions SET gemini_session_id = NULL "
            "WHERE id = ? AND gemini_session_id IS NOT NULL",
            (session_id,),
        ))

    def set_grok_session_id(self, session_id: str, grok_id: str) -> None:
        """Gắn mạch native của Grok Build CLI vào hội thoại để lượt sau `--resume` đúng chỗ."""
        if not grok_id:
            return
        self._write(lambda c: c.execute(
            "UPDATE sessions SET grok_session_id = ?, updated_at = ? WHERE id = ?",
            (grok_id, time.time(), session_id),
        ))

    def clear_grok_session_id(self, session_id: str) -> None:
        self._write(lambda c: c.execute(
            "UPDATE sessions SET grok_session_id = NULL "
            "WHERE id = ? AND grok_session_id IS NOT NULL",
            (session_id,),
        ))

    # ── mạch native của các engine giữ phiên ──
    #
    # Nhãn engine -> cột giữ mạch. Engine KHÔNG có mặt ở bảng này (Antigravity CLI và mọi
    # engine API) không giữ mạch riêng: chúng dựng lại ngữ cảnh từ transcript ở MỌI lượt nên
    # không bao giờ stale. Thêm engine giữ phiên mới thì thêm một dòng ở đây, đừng rải thêm
    # một lệnh clear nữa vào main.py - đó chính là cách bảng này bị bỏ sót hai engine.
    _MACH_NATIVE = {"cli": "cli_session_id",
                    "codex": "codex_thread_id",
                    "grok-cli": "grok_session_id"}

    def clear_native_threads(self, session_id: str, keep: str = "") -> List[str]:
        """Vô hiệu mạch native của MỌI engine, TRỪ engine `keep` đang chạy lượt này.

        BẤT BIẾN: một mạch native chỉ còn đúng khi nó chứa TOÀN BỘ hội thoại. Ngay khi một
        lượt được engine khác xử lý, mạch của mọi engine còn lại thiếu đúng lượt đó. Nối tiếp
        một mạch như vậy là engine trả lời với bản ghi khuyết - người dùng thấy nó "quên"
        đoạn giữa rồi nói lạc đề.

        Trả về tên các cột vừa dọn, để chỗ gọi ghi vào nhật ký chạy mà lần sau còn soi được.
        """
        da_don: List[str] = []
        cot_giu = self._MACH_NATIVE.get(str(keep or ""), "")
        row = self.get_session(session_id) or {}
        for nhan, cot in self._MACH_NATIVE.items():
            if cot == cot_giu or not (row.get(cot) or ""):
                continue
            self._write(lambda c, _cot=cot: c.execute(
                f"UPDATE sessions SET {_cot} = NULL WHERE id = ? AND {_cot} IS NOT NULL",
                (session_id,),
            ))
            da_don.append(nhan)
        return da_don

    # ── auto-title ──

    def auto_title(self, session_id: str, first_user_message: str) -> Optional[str]:
        """Đặt title từ câu hỏi đầu nếu phiên chưa có title."""
        sess = self.get_session(session_id)
        if not sess or (sess.get("title") or "").strip():
            return None
        title = title_from_message(first_user_message)
        if not title:
            return None
        self.rename(session_id, title)
        return title

    # ── search ──

    @staticmethod
    def _sanitize_fts(query: str) -> str:
        """Bỏ ký tự FTS5-special có thể raise (hermes_state.py:3780)."""
        q = (query or "").strip()
        if not q:
            return ""
        if q.count('"') % 2 != 0:
            q = q.replace('"', "")
        for ch in ("(", ")", ":", "^", "{", "}", "[", "]"):
            q = q.replace(ch, " ")
        return q.strip()

    def search(self, query: str, limit: int = 30,
               brain: Any = None) -> List[Dict[str, Any]]:
        """Full-text search nội dung mọi hội thoại. FTS5 nếu có, fallback LIKE.

        `brain` nhận cả danh sách bí danh, cùng luật với `list_sessions`."""
        q = (query or "").strip()
        if not q:
            return []

        _bcond, _bparams = loc_brain(brain)
        brain_clause = (" AND " + _bcond) if _bcond else ""
        if self._fts_enabled:
            fts_q = self._sanitize_fts(q)
            if fts_q:
                sql = f"""
                    SELECT m.session_id, m.role, m.ts,
                           snippet(messages_fts, 0, '>>>', '<<<', '…', 12) AS snippet,
                           s.title, s.brain, s.engine, s.updated_at
                    FROM messages_fts
                    JOIN messages m ON m.id = messages_fts.rowid
                    JOIN sessions s ON s.id = m.session_id
                    WHERE messages_fts MATCH ?{brain_clause}
                    ORDER BY rank
                    LIMIT ?
                """
                params = [fts_q] + list(_bparams) + [limit]
                try:
                    return [dict(r) for r in self._read(sql, tuple(params))]
                except sqlite3.OperationalError:
                    pass  # MATCH lỗi dù đã sanitize -> rơi xuống LIKE

        esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{esc}%"
        sql = f"""
            SELECT m.session_id, m.role, m.ts,
                   substr(m.content, max(1, instr(m.content, ?) - 30), 120) AS snippet,
                   s.title, s.brain, s.engine, s.updated_at
            FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE m.content LIKE ? ESCAPE '\\'{brain_clause}
            ORDER BY m.ts DESC
            LIMIT ?
        """
        params = [q, like] + list(_bparams) + [limit]
        return [dict(r) for r in self._read(sql, tuple(params))]

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            self._conn.close()


# Singleton toàn process (1 connection + app-lock).
_store: Optional[SessionStore] = None
_store_lock = threading.Lock()


def get_store() -> SessionStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SessionStore()
    return _store
