"""Kho mục tiêu của Javis Resonance: SQLite riêng `JAVIS_STATE_DIR/resonance.sqlite3`.

Nguồn chuẩn cho bản ghi ý định, mục tiêu, revision, sự kiện và outbox (spec mục 12). Mọi thao tác
đi qua một `Principal` và kiểm đúng brain: đường dẫn hay id do model đưa ra không đủ làm quyền đọc.

Quy tắc chính:
- Bản ghi ý định giữ NGUYÊN lời người dùng. Sửa ý tạo bản ghi mới, không viết lại bản cũ.
- Một tin nhắn chỉ tạo một mục tiêu: khoá chống trùng (`idempotency_key`) là duy nhất theo brain.
- Sửa cách hiểu tạo revision mới khi và chỉ khi `expected_revision` khớp; revision cũ giữ nguyên.
  Pause, ngân sách và số lượt đã dùng nằm ở mục tiêu, không ở revision, nên đổi cách hiểu không
  reset chúng (spec 4.2 bước 8). Agent không được bỏ ràng buộc người dùng đã nêu.
- Tạo và sửa ghi sự kiện cùng outbox trong CÙNG một giao dịch; M3 đọc outbox để chạy việc.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import STATE_DIR
import resonance as R
import resonance_heartbeat as HB

def call_ceiling() -> Optional[int]:
    """Trần TỔNG lượt engine cấp host của Resonance trên cả kho, đặt bằng biến môi trường
    JAVIS_RESONANCE_CALL_CEILING. Không đặt (mặc định) thì không có trần chung, chỉ có hạn mức từng mục tiêu.

    Tính MỌI đường Resonance gọi engine: lượt việc nền và phép thử (goals.calls_used) cùng bộ lập mục tiêu chưa có
    mục tiêu nào (call_ledger, review e2e P1-1). Đơn vị là lượt engine ở cấp host: một lượt có thể gồm nhiều request
    nội bộ của SDK; đây không phải trần số request gửi nhà cung cấp hay token.

    Dùng cho pilot có hạn mức do người dùng duyệt: kiểm TRƯỚC lượt gọi, trong cùng giao dịch giữ chỗ, nên lượt
    vượt trần không bao giờ được gọi; số đã dùng nằm trong SQLite nên trần giữ qua mọi lần khởi động lại, MIỄN là
    mỗi tiến trình được truyền biến này (tiến trình không có biến thì không có trần chung). Giá trị hỏng thì coi là 0
    (chặn hết), không phải bỏ trần."""
    raw = os.environ.get("JAVIS_RESONANCE_CALL_CEILING", "").strip()
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return 0


def _under_ceiling(c, n: int) -> bool:
    cap = call_ceiling()
    if cap is None:
        return True
    used = int(c.execute("SELECT COALESCE(SUM(calls_used),0) FROM goals").fetchone()[0])
    used += int(c.execute("SELECT COUNT(*) FROM call_ledger WHERE status='used'").fetchone()[0])
    return used + int(n) <= cap


_SCHEMA = """
CREATE TABLE IF NOT EXISTS intents(
  id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, session_id TEXT NOT NULL DEFAULT '',
  message_id INTEGER, text TEXT NOT NULL, constraints_json TEXT NOT NULL DEFAULT '[]',
  prev_intent_id TEXT, relation TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS goals(
  id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, owner TEXT NOT NULL, revision INTEGER NOT NULL,
  status TEXT NOT NULL, session_id TEXT NOT NULL DEFAULT '', request_ref TEXT NOT NULL DEFAULT '',
  idempotency_key TEXT NOT NULL, output_root TEXT NOT NULL,
  user_constraints_json TEXT NOT NULL DEFAULT '[]',
  budget_calls INTEGER NOT NULL DEFAULT 0, calls_used INTEGER NOT NULL DEFAULT 0,
  paused INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL,
  UNIQUE(brain_id, idempotency_key));
CREATE INDEX IF NOT EXISTS goals_open ON goals(brain_id, status, session_id);
CREATE TABLE IF NOT EXISTS goal_revisions(
  goal_id TEXT NOT NULL, revision INTEGER NOT NULL, intent_id TEXT NOT NULL,
  frame_json TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', by TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, PRIMARY KEY(goal_id, revision));
CREATE TABLE IF NOT EXISTS goal_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, revision INTEGER,
  kind TEXT NOT NULL, source TEXT NOT NULL DEFAULT '', message_ref TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}', by TEXT NOT NULL DEFAULT '',
  idempotency_key TEXT, created_at REAL NOT NULL,
  UNIQUE(goal_id, idempotency_key));
CREATE INDEX IF NOT EXISTS goal_events_msg ON goal_events(message_ref);
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, kind TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL, delivered_at REAL);
CREATE TABLE IF NOT EXISTS actions(
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, revision INTEGER NOT NULL, kind TEXT NOT NULL,
  seq INTEGER NOT NULL, status TEXT NOT NULL, lease_until REAL,
  intent_json TEXT NOT NULL DEFAULT '{}', receipt_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL, updated_at REAL NOT NULL,
  UNIQUE(goal_id, revision, kind, seq));
CREATE INDEX IF NOT EXISTS actions_goal ON actions(goal_id, created_at);
CREATE TABLE IF NOT EXISTS assessments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, revision INTEGER NOT NULL,
  verdict TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS evidence_links(
  goal_id TEXT NOT NULL, revision INTEGER NOT NULL, action_id TEXT NOT NULL DEFAULT '',
  evidence_id TEXT NOT NULL, kind TEXT NOT NULL, content_hash TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, PRIMARY KEY(goal_id, evidence_id));
CREATE TABLE IF NOT EXISTS wakeups(
  goal_id TEXT NOT NULL, brain_id TEXT NOT NULL, kind TEXT NOT NULL, due_at REAL NOT NULL,
  reason TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL, PRIMARY KEY(goal_id, kind));
CREATE INDEX IF NOT EXISTS wakeups_due ON wakeups(due_at);
CREATE TABLE IF NOT EXISTS handoffs(
  goal_id TEXT NOT NULL, revision INTEGER NOT NULL, message_ref TEXT NOT NULL, owner TEXT NOT NULL,
  status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(goal_id, revision));
CREATE TABLE IF NOT EXISTS published(
  goal_id TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, action_id TEXT NOT NULL,
  created_at REAL NOT NULL, PRIMARY KEY(goal_id, path));
CREATE TABLE IF NOT EXISTS experiments(
  id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, revision INTEGER NOT NULL,
  baseline_ref TEXT NOT NULL, candidate_ref TEXT NOT NULL, status TEXT NOT NULL,
  verdict TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '', calls_reserved INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL DEFAULT '{}', applied INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS experiments_goal ON experiments(goal_id, created_at);
CREATE TABLE IF NOT EXISTS call_ledger(
  id INTEGER PRIMARY KEY AUTOINCREMENT, brain_id TEXT NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS resonance_agents(
  agent_key TEXT PRIMARY KEY, brain_id TEXT NOT NULL, slug TEXT NOT NULL, status TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0, config_version INTEGER NOT NULL DEFAULT 1,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS resonance_agents_live ON resonance_agents(brain_id, slug)
  WHERE status IN ('active', 'missing');
CREATE TABLE IF NOT EXISTS resonance_agent_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_key TEXT NOT NULL, brain_id TEXT NOT NULL, kind TEXT NOT NULL,
  by TEXT NOT NULL DEFAULT '', version_before INTEGER, version_after INTEGER,
  payload_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS resonance_agent_events_key ON resonance_agent_events(agent_key, id);
CREATE TABLE IF NOT EXISTS session_agents(
  session_id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, agent_key TEXT NOT NULL, by TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS goal_agents(
  goal_id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, agent_key TEXT NOT NULL, by TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS goal_agents_key ON goal_agents(agent_key);
CREATE TABLE IF NOT EXISTS experiment_agents(
  experiment_id TEXT PRIMARY KEY, goal_id TEXT NOT NULL, agent_key TEXT NOT NULL,
  agent_config_version INTEGER NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS handoff_agents(
  goal_id TEXT NOT NULL, revision INTEGER NOT NULL, agent_key TEXT NOT NULL, agent_config_version INTEGER NOT NULL,
  created_at REAL NOT NULL, PRIMARY KEY(goal_id, revision));
CREATE TABLE IF NOT EXISTS wake_reasons(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, brain_id TEXT NOT NULL, wake_kind TEXT NOT NULL,
  code TEXT NOT NULL, origin TEXT NOT NULL, slot TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL,
  source_ref TEXT NOT NULL, due_at REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending', created_at REAL NOT NULL,
  settled_at REAL, settled_by TEXT NOT NULL DEFAULT '');
CREATE UNIQUE INDEX IF NOT EXISTS wake_reasons_event ON wake_reasons(goal_id, code, source_ref) WHERE origin='event';
CREATE INDEX IF NOT EXISTS wake_reasons_pending ON wake_reasons(goal_id, state, due_at);
CREATE TABLE IF NOT EXISTS wake_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id TEXT NOT NULL, brain_id TEXT NOT NULL, revision INTEGER NOT NULL,
  wake_kind TEXT NOT NULL, seen_json TEXT NOT NULL DEFAULT '[]', served_json TEXT NOT NULL DEFAULT '[]',
  codes_json TEXT NOT NULL DEFAULT '[]', policy_version TEXT NOT NULL, decision TEXT NOT NULL,
  why TEXT NOT NULL DEFAULT '', action_id TEXT NOT NULL DEFAULT '', model_calls INTEGER NOT NULL DEFAULT 0,
  met_count INTEGER, error_code TEXT NOT NULL DEFAULT '', chain_start INTEGER NOT NULL DEFAULT 0,
  signature TEXT NOT NULL DEFAULT '', next_due_at REAL, next_code TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS wake_log_goal ON wake_log(goal_id, id);
CREATE TABLE IF NOT EXISTS source_observations(
  goal_id TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, first_seen_at REAL NOT NULL,
  verdict TEXT NOT NULL DEFAULT '', PRIMARY KEY(goal_id, path, sha256));
"""

# Bảng và cột có từ trước A1 (0.86.x), đúng thứ tự. A1 không được đổi (review PR #590, P1-2); test so với đây.
PRE_A1_TABLES = ("intents", "goals", "goal_revisions", "goal_events", "outbox", "actions", "assessments",
                 "evidence_links", "wakeups", "handoffs", "published", "experiments", "call_ledger")

# Cột thêm từ M3 vào bảng đã có ở M2. Kho tạo bởi bản M2 không tự có cột mới qua CREATE IF NOT EXISTS,
# nên nâng cấp bằng ALTER TABLE: chỉ thêm, không xoá dữ liệu.
_ADDED_COLUMNS = (
    ("goals", "run_state", "TEXT NOT NULL DEFAULT 'ready'"),
    ("goals", "block_reason", "TEXT NOT NULL DEFAULT ''"),
    ("goals", "lease_owner", "TEXT"),
    ("goals", "lease_until", "REAL"),
    ("outbox", "idem", "TEXT"),
    # M5: cách làm (method ref) của mục tiêu. method_revision là revision cách làm đã được kiểm chứng; revision
    # khác thì quay về method_prev_ref (R.effective_method). explore_used: lượt đã dùng cho phép thử.
    ("goals", "method_ref", "TEXT NOT NULL DEFAULT 'work.v1'"),
    ("goals", "method_prev_ref", "TEXT NOT NULL DEFAULT ''"),
    ("goals", "method_revision", "INTEGER NOT NULL DEFAULT 0"),
    # Revision mà ref quay-lại thật sự được kiểm (0 với cách làm mặc định). Quay lại KHÔNG gán revision hiện tại cho
    # ref cũ (review M5, P1-3): phạm vi của mỗi ref là phạm vi nó đã được kiểm, không hơn.
    ("goals", "method_prev_revision", "INTEGER NOT NULL DEFAULT 0"),
    ("goals", "explore_used", "INTEGER NOT NULL DEFAULT 0"),
    # A1 KHÔNG thêm cột vào bảng nào có từ trước (review PR #590, P1-2): bản 0.86.x ghi một số bảng theo vị trí cột
    # (`INSERT ... VALUES(?,?,...)`), nên thêm cột là bản cũ hết ghi được khi quay về. Mọi dữ liệu A1 nằm ở bảng
    # riêng (`resonance_agents`, `session_agents`, `goal_agents`, `handoff_agents`...). Test khoá danh sách cột cũ.
)
_POST_MIGRATION = "CREATE UNIQUE INDEX IF NOT EXISTS outbox_idem ON outbox(goal_id, idem) WHERE idem IS NOT NULL;"


class ScopeError(Exception):
    """Thao tác ngoài phạm vi của principal (brain khác, bản ghi không tồn tại)."""


class ConflictError(Exception):
    """`expected_revision` không còn khớp: có người đã sửa mục tiêu trước."""


class AgentStateError(Exception):
    """Thao tác trên sổ đăng ký agent không hợp với trạng thái hiện tại (ví dụ bật agent đang `missing`)."""


AGENT_STATUSES = ("active", "missing", "retired")
_A1_BACKUP_SUFFIX = ".pre-a1.bak"
_A2_BACKUP_SUFFIX = ".pre-a2.bak"
# Bảng có từ A2 (0.88.0). Bản 0.87.x bỏ qua chúng; test rollback chạy mã 0.87 thật trên kho đã nâng.
A2_TABLES = ("wake_reasons", "wake_log", "source_observations")
WAKE_LOG_KEEP = 200
SERVED_TIMER_KEEP_S = 30 * 86400
# Câu ghi vào `wakeups.reason` để bản 0.87 (đọc câu chữ) vẫn hiểu lịch.
_WAKE_TEXT = {
    "created": "tạo mục tiêu", "revised": "sửa cách hiểu", "assigned": "chủ dự án gán trợ lý",
    "feedback": "người dùng phản hồi", "user_schedule": "người dùng hẹn lần xem lại",
    "retry_not_met": "làm lại phần chưa đạt", "error_retry": "thử lại sau lỗi", "recovery": "phục hồi nếu lượt bị ngắt",
    "handoff_wait": "chờ bàn giao lượt chat", "handoff_done": "bàn giao lượt chat", "resumed": "người dùng cho tiếp tục",
    "agent_enabled": "trợ lý được bật", "agent_recheck": "kiểm lại công tắc trợ lý",
    "agent_changed": "xét lại đầu ra theo quyền hiện tại", "guard_recheck": "kiểm lại guard chưa xác định",
    "review": "xem lại định kỳ", "deadline": "kiểm hạn chót", "drift_recheck": "kiểm lại file bị sửa ngoài Javis",
    "guard_observe": "quan sát guard",
}


@dataclass(frozen=True)
class Principal:
    """Ai đang thao tác. `kind`: owner (người dùng qua auth của host) hoặc agent. Host tạo, model không tự khai."""
    kind: str
    id: str
    brain_id: str

    @property
    def by(self) -> str:
        return f"{self.kind}:{self.id}"


def _nid(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _j(v) -> str:
    return json.dumps(v, ensure_ascii=False)


class GoalStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else Path(STATE_DIR) / "resonance.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._backup_before("resonance_agents", _A1_BACKUP_SUFFIX)
        self._backup_before("wake_reasons", _A2_BACKUP_SUFFIX)
        with closing(self._conn()) as c:
            had_goals = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='goals'").fetchone()
            had_a2 = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wake_reasons'").fetchone()
            c.executescript(_SCHEMA)
            for table, col, decl in _ADDED_COLUMNS:
                have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
                if col not in have:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            c.executescript(_POST_MIGRATION)
        if had_goals and not had_a2:
            self._a2_migrate()
        self._a2_reconcile()

    def _backup_before(self, marker_table: str, suffix: str) -> None:
        """Lần đầu mã mới mở một kho có từ trước (chưa có bảng `marker_table`), chép nguyên kho thành
        `resonance.sqlite3<suffix>` cạnh file gốc để khôi phục tay (A1: `.pre-a1.bak`, A2: `.pre-a2.bak`). Dùng API
        backup của SQLite nên lấy được cả phần còn nằm trong WAL. Chỉ chép một lần: bản sao đã có thì không ghi đè.
        Kho mới tinh thì không chép."""
        bak = self.path.with_name(self.path.name + suffix)
        if bak.exists() or not self.path.is_file() or self.path.stat().st_size == 0:
            return
        with closing(sqlite3.connect(str(self.path), timeout=10)) as src:
            names = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "goals" not in names or marker_table in names:
                return
            tmp = bak.with_name(bak.name + ".tmp")
            with closing(sqlite3.connect(str(tmp))) as dst:
                src.backup(dst)
            os.replace(tmp, bak)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        return c

    class _Tx:
        """BEGIN IMMEDIATE ... COMMIT; lỗi thì ROLLBACK. Giữ khoá ghi từ đầu để hai lượt không chen nhau."""

        def __init__(self, store):
            self.c = store._conn()

        def __enter__(self):
            self.c.execute("BEGIN IMMEDIATE")
            return self.c

        def __exit__(self, et, ev, tb):
            try:
                self.c.execute("ROLLBACK" if et else "COMMIT")
            finally:
                self.c.close()
            return False

    # ───────────── sổ đăng ký agent (A1) ─────────────
    # Mã agent do host cấp, độc lập với slug: trùng tên file không đủ để kế thừa quyền hay mục tiêu. Mọi thao tác ĐỔI
    # chỉ dành cho owner (qua API của host); không có tool nào gọi tới đây. Mỗi lần đổi công tắc hay trạng thái tăng
    # `config_version` và ghi một dòng `resonance_agent_events`.

    @staticmethod
    def _agent(r) -> dict:
        return {"agent_key": r["agent_key"], "brain_id": r["brain_id"], "slug": r["slug"], "status": r["status"],
                "enabled": bool(r["enabled"]), "config_version": int(r["config_version"]),
                "created_at": r["created_at"], "updated_at": r["updated_at"]}

    @staticmethod
    def _owner_only(p: Principal) -> None:
        if p.kind != "owner":
            raise PermissionError("chỉ chủ dự án mới đổi được sổ đăng ký agent")

    @staticmethod
    def _agent_event(c, r, kind: str, by: str, after: Optional[int], payload: Optional[dict] = None,
                     now: Optional[float] = None) -> None:
        c.execute("INSERT INTO resonance_agent_events(agent_key,brain_id,kind,by,version_before,version_after,"
                  "payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (r["agent_key"], r["brain_id"], kind, by, int(r["config_version"]), after,
                   _j(payload or {}), now or time.time()))

    @staticmethod
    def _live_agent_row(c, brain_id: str, slug: str):
        return c.execute("SELECT * FROM resonance_agents WHERE brain_id=? AND slug=? AND status IN ('active','missing')",
                         (brain_id, str(slug or ""))).fetchone()

    def _insert_agent(self, c, brain_id: str, slug: str, enabled: bool, by: str, now: float, payload=None):
        key = "ag_" + secrets.token_hex(8)
        c.execute("INSERT INTO resonance_agents(agent_key,brain_id,slug,status,enabled,config_version,created_at,"
                  "updated_at) VALUES(?,?,?,?,?,?,?,?)",
                  (key, brain_id, str(slug), "active", 1 if enabled else 0, 1, now, now))
        r = c.execute("SELECT * FROM resonance_agents WHERE agent_key=?", (key,)).fetchone()
        c.execute("INSERT INTO resonance_agent_events(agent_key,brain_id,kind,by,version_before,version_after,"
                  "payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (key, brain_id, "registered", by, None, 1, _j({"slug": slug, "enabled": bool(enabled),
                                                                  **(payload or {})}), now))
        return r

    def _bump_agent(self, c, r, kind: str, by: str, now: float, payload=None, **cols) -> dict:
        after = int(r["config_version"]) + 1
        sets = "".join(f", {k}=?" for k in cols)
        c.execute(f"UPDATE resonance_agents SET config_version=?, updated_at=?{sets} WHERE agent_key=?",
                  (after, now, *cols.values(), r["agent_key"]))
        self._agent_event(c, r, kind, by, after, payload, now)
        return self._agent(c.execute("SELECT * FROM resonance_agents WHERE agent_key=?", (r["agent_key"],)).fetchone())

    def agent(self, brain_id: str, slug: str) -> Optional[dict]:
        """Dòng còn sống (`active` hay `missing`) của `(brain, slug)`, hoặc None khi chưa đăng ký hay đã nghỉ."""
        with closing(self._conn()) as c:
            r = self._live_agent_row(c, brain_id, slug)
            return self._agent(r) if r else None

    def agent_by_key(self, brain_id: str, agent_key: str) -> Optional[dict]:
        """Đọc theo mã, chỉ trong đúng brain. Mã của brain khác coi như không có."""
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM resonance_agents WHERE agent_key=? AND brain_id=?",
                          (str(agent_key or ""), brain_id)).fetchone()
            return self._agent(r) if r else None

    def agents(self, brain_id: str, include_retired: bool = False) -> list:
        with closing(self._conn()) as c:
            q = "SELECT * FROM resonance_agents WHERE brain_id=?"
            if not include_retired:
                q += " AND status != 'retired'"
            return [self._agent(r) for r in c.execute(q + " ORDER BY slug, created_at", (brain_id,)).fetchall()]

    def agent_events(self, brain_id: str, agent_key: str, limit: int = 200) -> list:
        with closing(self._conn()) as c:
            rows = c.execute("SELECT * FROM resonance_agent_events WHERE agent_key=? AND brain_id=? ORDER BY id LIMIT ?",
                             (str(agent_key or ""), brain_id, int(limit))).fetchall()
            return [{"kind": r["kind"], "by": r["by"], "version_before": r["version_before"],
                     "version_after": r["version_after"], "payload": json.loads(r["payload_json"] or "{}"),
                     "created_at": r["created_at"]} for r in rows]

    def agent_set_enabled(self, p: Principal, slug: str, enabled: bool) -> Optional[dict]:
        """Chủ dự án bật hay tắt Cộng hưởng cho agent `slug` của brain. Lần bật đầu cấp mã mới.
        Tắt một agent chưa đăng ký thì không có gì để làm (trả None). Agent `missing` không bật được tới khi
        chủ dự án xác nhận (`agent_confirm`), nhưng tắt thì luôn được. Đặt lại đúng giá trị đang có không tăng version.
        Kiểm file agent còn tồn tại là việc của người gọi (host biết cấu trúc brain), không phải của kho."""
        self._owner_only(p)
        slug = str(slug or "").strip()
        if not slug:
            raise AgentStateError("thiếu slug agent")
        now = time.time()
        with self._Tx(self) as c:
            r = self._live_agent_row(c, p.brain_id, slug)
            if r is None:
                if not enabled:
                    return None
                return self._agent(self._insert_agent(c, p.brain_id, slug, True, p.by, now))
            # Kiểm trạng thái TRƯỚC nhánh "không đổi" (review PR #590, P2-1): agent missing vẫn giữ cờ bật cũ, nên
            # đặt cờ bật lần nữa không được báo thành công.
            if enabled and r["status"] != "active":
                raise AgentStateError(f"agent đang {r['status']}, cần chủ dự án xác nhận trước khi bật")
            if bool(r["enabled"]) == bool(enabled):
                return self._agent(r)
            return self._bump_agent(c, r, "enabled" if enabled else "disabled", p.by, now, enabled=1 if enabled else 0)

    def agent_mark_missing(self, brain_id: str, agent_key: str, by: str = "host") -> Optional[dict]:
        """Host thấy file agent biến mất: dòng `active` chuyển `missing`, version tăng, mọi cổng của mã này đóng.
        Không đụng tới `enabled`: xác nhận lại thì công tắc như cũ. Gọi lặp lại không tăng version."""
        now = time.time()
        with self._Tx(self) as c:
            r = c.execute("SELECT * FROM resonance_agents WHERE agent_key=? AND brain_id=?",
                          (str(agent_key or ""), brain_id)).fetchone()
            if r is None:
                return None
            if r["status"] != "active":
                return self._agent(r)
            return self._bump_agent(c, r, "missing", by, now, status="missing")

    def agent_retire(self, p: Principal, slug: str, reason: str = "deleted") -> Optional[dict]:
        """Xoá agent qua host (hay chủ dự án cho nghỉ): dòng còn sống chuyển `retired` và tắt. Tạo lại cùng slug sau
        đó là agent MỚI, phải bật lại và nhận mã mới; mục tiêu cũ vẫn giữ mã cũ."""
        self._owner_only(p)
        now = time.time()
        with self._Tx(self) as c:
            r = self._live_agent_row(c, p.brain_id, slug)
            if r is None:
                return None
            return self._bump_agent(c, r, "retired", p.by, now, {"reason": str(reason or "")},
                                    status="retired", enabled=0)

    def agent_confirm(self, p: Principal, agent_key: str, same: bool) -> dict:
        """Chủ dự án xử lý agent `missing` khi file cùng slug xuất hiện lại. `same=True`: đúng trợ lý cũ, giữ mã và
        công tắc. `same=False`: trợ lý mới, mã cũ nghỉ (mục tiêu cũ ở lại với mã cũ), mã mới đăng ký ở trạng thái
        tắt. Người gọi phải kiểm file đang có thật trước khi gọi."""
        self._owner_only(p)
        now = time.time()
        with self._Tx(self) as c:
            r = c.execute("SELECT * FROM resonance_agents WHERE agent_key=? AND brain_id=?",
                          (str(agent_key or ""), p.brain_id)).fetchone()
            if r is None:
                raise ScopeError("agent không tồn tại trong brain này")
            if r["status"] != "missing":
                raise AgentStateError(f"agent đang {r['status']}, không cần xác nhận")
            if same:
                return self._bump_agent(c, r, "confirmed_same", p.by, now, status="active")
            self._bump_agent(c, r, "retired", p.by, now, {"reason": "replaced"}, status="retired", enabled=0)
            new = self._insert_agent(c, p.brain_id, r["slug"], False, p.by, now, {"replaces": r["agent_key"]})
            return self._agent(new)

    def session_agent(self, brain_id: str, session_id: str, slug: str, session_created_at: float,
                      pin: bool = True) -> Optional[dict]:
        """Agent của một phiên trò chuyện `agent:<slug>`, GHIM theo phiên (review PR #590, P1-1).

        Slug chỉ là tên file: xoá rồi tạo lại cùng slug là agent khác với mã khác. Nên phiên đã ghim vào mã A thì
        mãi là của A: A còn `active` thì trả A, A đã `missing` hay `retired` thì trả None, KHÔNG tự chuyển sang mã
        mới của cùng slug. A1 chưa có thao tác chủ dự án nối lại phiên cũ; muốn dùng agent mới thì mở phiên mới.

        Phiên chưa ghim được ghim vào dòng `active` hiện tại của slug khi và chỉ khi chắc nó thuộc dòng đó:
        - đây là mã DUY NHẤT từng có của `(brain, slug)` (gồm phiên mở trước lần bật đầu tiên), hoặc
        - phiên được tạo từ lúc mã đó được cấp trở đi (`session_created_at` >= `created_at` của mã).
        Phiên tạo dưới thời một mã cũ mà chưa ghim (chưa có lượt nào) thì không được nhận mã mới: trả None.
        Ghim một lần, ghi sự kiện `session_pinned`; ghim trùng thì bản đã có thắng."""
        sid = str(session_id or "").strip()
        if not sid:
            return None
        now = time.time()
        with self._Tx(self) as c:
            link = c.execute("SELECT * FROM session_agents WHERE session_id=?", (sid,)).fetchone()
            if link is not None:
                if link["brain_id"] != brain_id:
                    return None
                r = c.execute("SELECT * FROM resonance_agents WHERE agent_key=? AND brain_id=?",
                              (link["agent_key"], brain_id)).fetchone()
                return self._agent(r) if r is not None and r["status"] == "active" and r["slug"] == slug else None
            r = self._live_agent_row(c, brain_id, slug)
            if r is None or r["status"] != "active":
                return None
            n = int(c.execute("SELECT COUNT(*) FROM resonance_agents WHERE brain_id=? AND slug=?",
                              (brain_id, str(slug))).fetchone()[0])
            if n > 1 and float(session_created_at or 0) < float(r["created_at"]):
                return None
            if not pin:
                # Chỉ hỏi (giao diện xem trạng thái phiên): cùng luật, không ghi liên kết.
                return self._agent(r)
            c.execute("INSERT INTO session_agents(session_id,brain_id,agent_key,by,created_at) VALUES(?,?,?,?,?)",
                      (sid, brain_id, r["agent_key"], "host", now))
            c.execute("INSERT INTO resonance_agent_events(agent_key,brain_id,kind,by,version_before,version_after,"
                      "payload_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
                      (r["agent_key"], brain_id, "session_pinned", "host", int(r["config_version"]),
                       int(r["config_version"]), _j({"session_id": sid}), now))
            return self._agent(r)

    def session_pin(self, session_id: str) -> Optional[dict]:
        """Đọc liên kết phiên → mã agent đã ghim (để xem và kiểm), None khi chưa ghim."""
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM session_agents WHERE session_id=?", (str(session_id or ""),)).fetchone()
            return {"session_id": r["session_id"], "brain_id": r["brain_id"], "agent_key": r["agent_key"],
                    "created_at": r["created_at"]} if r else None

    # ───────────── bản ghi ý định ─────────────

    def add_intent(self, p: Principal, session_id: str, message_id, text: str, constraints=(),
                   prev_intent_id: Optional[str] = None, relation: str = "") -> dict:
        """Ghi nguyên văn lời người dùng. `prev_intent_id`: ý định của revision trước khi tin này cập nhật
        một mục tiêu; `relation`: "amend" (bổ sung) hay "replace" (thay chỉ dẫn đã nêu)."""
        rec = self.new_intent(p, session_id, message_id, text, constraints, prev_intent_id, relation)
        with self._Tx(self) as c:
            self._insert_intent(c, p, rec)
        return rec

    def new_intent(self, p: Principal, session_id: str, message_id, text: str, constraints=(),
                   prev_intent_id: Optional[str] = None, relation: str = "") -> dict:
        """Dựng bản ghi ý định CHƯA ghi; `revise(intent=...)` ghi nó cùng transaction với revision."""
        return {"id": _nid("in"), "brain_id": p.brain_id, "session_id": str(session_id or ""),
                "message_id": message_id, "text": str(text or ""),
                "constraints": [str(x).strip() for x in (constraints or ()) if str(x).strip()],
                "prev_intent_id": prev_intent_id, "relation": str(relation or ""), "created_at": time.time()}

    def _insert_intent(self, c, p: Principal, rec: dict) -> None:
        if rec.get("brain_id") != p.brain_id:
            raise ScopeError("bản ghi ý định không thuộc brain này")
        if rec.get("prev_intent_id"):
            self._intent(c, p, rec["prev_intent_id"])
        c.execute("INSERT INTO intents VALUES(?,?,?,?,?,?,?,?,?)",
                  (rec["id"], rec["brain_id"], rec["session_id"], rec["message_id"], rec["text"],
                   _j(rec["constraints"]), rec.get("prev_intent_id"), rec.get("relation") or "", rec["created_at"]))

    def _intent(self, c, p: Principal, intent_id: str) -> dict:
        r = c.execute("SELECT * FROM intents WHERE id=?", (intent_id,)).fetchone()
        if r is None or r["brain_id"] != p.brain_id:
            raise ScopeError("bản ghi ý định không tồn tại trong brain này")
        return {"id": r["id"], "text": r["text"], "constraints": json.loads(r["constraints_json"] or "[]"),
                "prev_intent_id": r["prev_intent_id"], "relation": r["relation"]}

    def get_intent(self, p: Principal, intent_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            try:
                return self._intent(c, p, intent_id)
            except ScopeError:
                return None

    # ───────────── mục tiêu ─────────────

    def _record(self, c, row) -> R.GoalRecord:
        rv = c.execute("SELECT * FROM goal_revisions WHERE goal_id=? AND revision=?",
                       (row["id"], row["revision"])).fetchone()
        fr = json.loads(rv["frame_json"]) if rv else {}
        return R.GoalRecord(
            id=row["id"], brain_id=row["brain_id"], owner=row["owner"], revision=row["revision"],
            output_root=row["output_root"], request_ref=row["request_ref"],
            intent_id=rv["intent_id"] if rv else "", session_id=row["session_id"],
            understanding=fr.get("understanding", ""), criteria=tuple(fr.get("criteria") or ()),
            assumptions=tuple(fr.get("assumptions") or ()), constraints=tuple(fr.get("constraints") or ()),
            targets=tuple(fr.get("targets") or ()), open_questions=tuple(fr.get("open_questions") or ()),
            horizon=dict(fr.get("horizon") or {}), relevant_quote=fr.get("relevant_quote", ""),
            guards=tuple(fr.get("guards") or ()), guard_seq=int(fr.get("guard_seq") or 0),
            stage=fr.get("stage", "discovery"), mode=fr.get("mode", "achieve"), status=row["status"],
            budget_calls=row["budget_calls"], calls_used=row["calls_used"], paused=bool(row["paused"]),
            method_ref=row["method_ref"] or R.DEFAULT_METHOD, method_prev_ref=row["method_prev_ref"] or "",
            method_revision=int(row["method_revision"] or 0), explore_used=int(row["explore_used"] or 0),
            method_prev_revision=int(row["method_prev_revision"] or 0),
            agent_key=self._goal_agent(c, row["id"]))

    @staticmethod
    def _goal_agent(c, goal_id: str) -> str:
        r = c.execute("SELECT agent_key FROM goal_agents WHERE goal_id=?", (goal_id,)).fetchone()
        return r["agent_key"] if r else ""

    @staticmethod
    def _agent_block(c, brain_id: str, agent_key: str, version=None) -> str:
        """Lý do mã agent KHÔNG được tác động lúc này, đọc trong giao dịch của người gọi; rỗng là được. Cùng nghĩa với
        `resonance.agent_gate`, để kiểm lại ngay trong giao dịch ghi (không chỉ ở bước kiểm trước đó)."""
        if not agent_key:
            return "unassigned"
        r = c.execute("SELECT * FROM resonance_agents WHERE agent_key=? AND brain_id=?", (agent_key, brain_id)).fetchone()
        if r is None:
            return "agent_unknown"
        if r["status"] != "active":
            return "agent_" + str(r["status"])
        if not r["enabled"]:
            return "agent_off"
        if version is not None and int(version) != int(r["config_version"]):
            return "agent_changed"
        return ""

    def _goal_row(self, c, p: Principal, goal_id: str):
        r = c.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        if r is None or r["brain_id"] != p.brain_id:
            return None
        return r

    def find_by_key(self, p: Principal, idempotency_key: str) -> Optional[R.GoalRecord]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM goals WHERE brain_id=? AND idempotency_key=?",
                          (p.brain_id, idempotency_key)).fetchone()
            return self._record(c, r) if r else None

    def create(self, p: Principal, intent_id: str, frame: dict, idempotency_key: str, session_id: str = "",
               output_root: Optional[str] = None, output_base: Optional[str] = None, budget_calls: int = 0,
               message_ref: Optional[str] = None, work_due_at: Optional[float] = None,
               handoff_owner: Optional[str] = None, agent_key: Optional[str] = None,
               agent_version: Optional[int] = None) -> tuple:
        """Trả (GoalRecord, đã_tạo_mới). Cùng khoá chống trùng thì trả mục tiêu cũ, không ghi gì thêm.

        A1: `agent_key` gắn mục tiêu vào một agent (bảng goal_agents) trong CÙNG giao dịch, sau khi kiểm lại ngay tại
        đây agent còn `active`, bật và đúng `agent_version`; không đạt thì AgentStateError, không ghi gì."""
        now = time.time()
        msg = message_ref or idempotency_key
        with self._Tx(self) as c:
            old = c.execute("SELECT * FROM goals WHERE brain_id=? AND idempotency_key=?",
                            (p.brain_id, idempotency_key)).fetchone()
            if old is not None:
                return self._record(c, old), False
            if agent_key is not None:
                why = self._agent_block(c, p.brain_id, agent_key, agent_version)
                if why:
                    raise AgentStateError(why)
            intent = self._intent(c, p, intent_id)
            missing = [x for x in intent["constraints"] if x not in (frame.get("constraints") or [])]
            if missing:
                raise R.GoalRejected(f"khung mục tiêu bỏ ràng buộc người dùng đã nêu: {missing}")
            gid = _nid("g")
            root = output_root or str(Path(output_base or (Path(STATE_DIR) / "resonance" / "outputs")) / gid)
            c.execute("INSERT INTO goals(id,brain_id,owner,revision,status,session_id,request_ref,idempotency_key,"
                      "output_root,user_constraints_json,budget_calls,calls_used,paused,created_at,updated_at) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (gid, p.brain_id, p.id, 1, "active", str(session_id or ""), msg, idempotency_key, root,
                       _j(intent["constraints"]), max(0, int(budget_calls)), 0, 0, now, now))
            c.execute("INSERT INTO goal_revisions VALUES(?,?,?,?,?,?,?)",
                      (gid, 1, intent_id, _j(frame), "tạo", p.by, now))
            c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,message_ref,payload_json,by,"
                      "idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (gid, 1, "created", "host", msg, _j({"intent_id": intent_id}), p.by, "created", now))
            c.execute("INSERT INTO outbox(goal_id,kind,payload_json,created_at) VALUES(?,?,?,?)",
                      (gid, "goal.created", _j({"revision": 1}), now))
            # M3: mục tiêu mới được làm ngay ở lượt tick kế tiếp; có guard thì có lịch quan sát riêng. Lập trong một
            # lượt chat thì lịch được GIỮ tới khi bàn giao cuối lượt (work_due_at), để việc nền không chen vào giữa lượt.
            # A2: lý do `created` đủ điều kiện ngay; lập trong lượt chat thì chỉ GIỜ THỨC lùi tới mốc đối soát bàn giao.
            self._reason_event(c, gid, p.brain_id, "created", "rev:1", 1, due_at=now,
                               wake_at=float(work_due_at) if work_due_at else now)
            if agent_key:
                c.execute("INSERT INTO goal_agents(goal_id,brain_id,agent_key,by,created_at) VALUES(?,?,?,?,?)",
                          (gid, p.brain_id, agent_key, p.by, now))
            if handoff_owner:
                self._open_handoff(c, gid, 1, msg, handoff_owner, now, agent_key, agent_version)
            if frame.get("guards"):
                self._reason_timer(c, gid, p.brain_id, "guard_observe", now + R.GUARD_OBSERVE_S, 1, now)
            row = c.execute("SELECT * FROM goals WHERE id=?", (gid,)).fetchone()
            return self._record(c, row), True

    def get(self, p: Principal, goal_id: str) -> Optional[R.GoalRecord]:
        with closing(self._conn()) as c:
            r = self._goal_row(c, p, goal_id)
            return self._record(c, r) if r else None

    def get_revision(self, p: Principal, goal_id: str, revision: int) -> Optional[dict]:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return None
            r = c.execute("SELECT frame_json FROM goal_revisions WHERE goal_id=? AND revision=?",
                          (goal_id, int(revision))).fetchone()
            return json.loads(r["frame_json"]) if r else None

    def list_open(self, p: Principal, session_id: Optional[str] = None, agent_key: Optional[str] = None,
                  unassigned: bool = False) -> list:
        """Mục tiêu đang mở của brain. `agent_key`: chỉ của đúng agent đó. `unassigned`: chỉ mục tiêu chưa gán."""
        with closing(self._conn()) as c:
            q = "SELECT * FROM goals WHERE brain_id=? AND status='active'"
            args = [p.brain_id]
            if session_id is not None:
                q += " AND session_id=?"
                args.append(str(session_id))
            if agent_key is not None:
                q += " AND id IN (SELECT goal_id FROM goal_agents WHERE agent_key=?)"
                args.append(str(agent_key))
            if unassigned:
                q += " AND id NOT IN (SELECT goal_id FROM goal_agents)"
            q += " ORDER BY updated_at DESC"
            return [self._record(c, r) for r in c.execute(q, args).fetchall()]

    def revise(self, p: Principal, goal_id: str, expected_revision: int, frame: dict, reason: str,
               intent_id: Optional[str] = None, message_ref: str = "", relation: str = "",
               intent: Optional[dict] = None, work_due_at: Optional[float] = None,
               handoff_owner: Optional[str] = None, agent_key: Optional[str] = None,
               agent_version: Optional[int] = None) -> R.GoalRecord:
        """A1: có `agent_key` thì mục tiêu phải thuộc đúng agent đó (ScopeError nếu không) và agent còn `active`, bật,
        đúng `agent_version`, kiểm trong cùng giao dịch (AgentStateError)."""
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            if agent_key is not None:
                if self._goal_agent(c, goal_id) != agent_key:
                    raise ScopeError("mục tiêu không thuộc trợ lý này")
                why = self._agent_block(c, p.brain_id, agent_key, agent_version)
                if why:
                    raise AgentStateError(why)
            if int(row["revision"]) != int(expected_revision):
                raise ConflictError(f"mục tiêu đang ở revision {row['revision']}, không phải {expected_revision}")
            user_cons = json.loads(row["user_constraints_json"] or "[]")
            if intent is not None:
                # Ghi ý định trong CÙNG transaction: revision bị từ chối thì ý định cũng không còn.
                self._insert_intent(c, p, intent)
                intent_id = intent["id"]
            if intent_id:
                for x in self._intent(c, p, intent_id)["constraints"]:
                    if x not in user_cons:
                        user_cons.append(x)
            missing = [x for x in user_cons if x not in (frame.get("constraints") or [])]
            if missing:
                raise R.GoalRejected(f"không được bỏ ràng buộc người dùng đã nêu: {missing}")
            prev = c.execute("SELECT * FROM goal_revisions WHERE goal_id=? AND revision=?",
                             (goal_id, row["revision"])).fetchone()
            old_fr = json.loads(prev["frame_json"]) if prev else {}
            diff = {k: {"from": old_fr.get(k), "to": frame.get(k)} for k in frame if old_fr.get(k) != frame.get(k)}
            rev = int(row["revision"]) + 1
            c.execute("INSERT INTO goal_revisions VALUES(?,?,?,?,?,?,?)",
                      (goal_id, rev, intent_id or (prev["intent_id"] if prev else ""), _j(frame), reason[:500], p.by, now))
            c.execute("UPDATE goals SET revision=?, user_constraints_json=?, updated_at=? WHERE id=?",
                      (rev, _j(user_cons), now, goal_id))
            c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,message_ref,payload_json,by,"
                      "idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (goal_id, rev, "reframe", "host", str(message_ref or ""),
                       _j({"reason": reason[:500], "relation": relation, "diff": diff}), p.by,
                       f"reframe:{rev}", now))
            c.execute("INSERT INTO outbox(goal_id,kind,payload_json,created_at) VALUES(?,?,?,?)",
                      (goal_id, "goal.revised", _j({"revision": rev}), now))
            # Cách hiểu mới cần được làm lại; trạng thái chờ người dùng xác nhận revision cũ không còn đúng.
            if row["status"] == "active":
                self._reason_event(c, goal_id, row["brain_id"], "revised", f"rev:{rev}", rev, due_at=now,
                                   wake_at=float(work_due_at) if work_due_at else now)
                if handoff_owner:
                    self._open_handoff(c, goal_id, rev, str(message_ref or ""), handoff_owner, now, agent_key,
                                       agent_version)
                if frame.get("guards") and not c.execute(
                        "SELECT 1 FROM wake_reasons WHERE goal_id=? AND slot='observe' AND state='pending'",
                        (goal_id,)).fetchone():
                    self._reason_timer(c, goal_id, row["brain_id"], "guard_observe", now + R.GUARD_OBSERVE_S, rev, now)
            return self._record(c, c.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone())

    def set_paused(self, p: Principal, goal_id: str, paused: bool) -> None:
        """Chỉ người dùng (owner) đổi pause. Agent không tự bỏ pause của người dùng."""
        if p.kind != "owner":
            raise PermissionError("chỉ người dùng mới tạm dừng hoặc tiếp tục mục tiêu")
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            c.execute("UPDATE goals SET paused=?, updated_at=? WHERE id=?", (1 if paused else 0, time.time(), goal_id))
            cur = c.execute("INSERT INTO goal_events(goal_id,kind,source,payload_json,by,created_at) VALUES(?,?,?,?,?,?)",
                            (goal_id, "paused" if paused else "resumed", "owner", "{}", p.by, time.time()))
            if not paused:
                # Tiếp tục: thức ngay một lần để xét lại (chỉ kiểm); đầu ra đã lưu trước khi dừng được dùng lại, không
                # gọi model lần nữa. Lý do đang chờ (góp ý, thử lại) vẫn còn và được xét theo trần hiện tại (A2).
                self._reason_event(c, goal_id, p.brain_id, "resumed", f"ev:{cur.lastrowid}", int(row["revision"]))
            else:
                self._recompute_wake(c, goal_id)

    def add_calls_used(self, p: Principal, goal_id: str, n: int) -> None:
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            c.execute("UPDATE goals SET calls_used=calls_used+?, updated_at=? WHERE id=?",
                      (max(0, int(n)), time.time(), goal_id))

    # ───────────── sự kiện và outbox ─────────────

    def append_event(self, p: Principal, goal_id: str, kind: str, payload: dict, idempotency_key: Optional[str] = None,
                     revision: Optional[int] = None, source: str = "host", message_ref: str = "") -> int:
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            if idempotency_key:
                old = c.execute("SELECT id FROM goal_events WHERE goal_id=? AND idempotency_key=?",
                                (goal_id, idempotency_key)).fetchone()
                if old is not None:
                    return int(old["id"])
            cur = c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,message_ref,payload_json,by,"
                            "idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                            (goal_id, revision, kind, source, str(message_ref or ""), _j(payload or {}), p.by,
                             idempotency_key, time.time()))
            return int(cur.lastrowid)

    def events(self, p: Principal, goal_id: str, limit: int = 500) -> list:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            rows = c.execute("SELECT * FROM goal_events WHERE goal_id=? ORDER BY id LIMIT ?",
                             (goal_id, int(limit))).fetchall()
            return [{"id": r["id"], "kind": r["kind"], "revision": r["revision"], "source": r["source"],
                     "message_ref": r["message_ref"], "payload": json.loads(r["payload_json"] or "{}"),
                     "by": r["by"], "created_at": r["created_at"]} for r in rows]

    def events_for_message(self, p: Principal, message_ref: str) -> list:
        """Sự kiện tạo/sửa mục tiêu do đúng một tin nhắn gây ra. Đầu vào của route_request."""
        with closing(self._conn()) as c:
            rows = c.execute("SELECT e.goal_id, e.kind, e.message_ref FROM goal_events e JOIN goals g "
                             "ON g.id=e.goal_id WHERE e.message_ref=? AND g.brain_id=? ORDER BY e.id",
                             (str(message_ref), p.brain_id)).fetchall()
            return [{"goal_id": r["goal_id"], "kind": r["kind"], "message_ref": r["message_ref"]} for r in rows]

    def outbox_pending(self, limit: int = 100) -> list:
        with closing(self._conn()) as c:
            rows = c.execute("SELECT * FROM outbox WHERE delivered_at IS NULL ORDER BY id LIMIT ?",
                             (int(limit),)).fetchall()
            return [{"id": r["id"], "goal_id": r["goal_id"], "kind": r["kind"],
                     "payload": json.loads(r["payload_json"] or "{}"), "created_at": r["created_at"]} for r in rows]

    def outbox_mark_delivered(self, outbox_id: int) -> None:
        with self._Tx(self) as c:
            c.execute("UPDATE outbox SET delivered_at=? WHERE id=? AND delivered_at IS NULL", (time.time(), int(outbox_id)))

    # ═══════════════════ M3: lịch, trạng thái chạy, sổ hành động, đánh giá, bằng chứng ═══════════════════

    def get_for_host(self, goal_id: str) -> Optional[R.GoalRecord]:
        """Đọc mục tiêu theo id mà KHÔNG qua principal. Chỉ host dùng (outbox, tick), không đưa cho model."""
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
            return self._record(c, r) if r else None

    # ───────────── lịch đánh thức ─────────────
    # A2 (thiết kế mục 3, 5, 6): `wakeups` là LỊCH VẬT LÝ, một dòng `work` và một dòng `observe` mỗi mục tiêu, để bản
    # 0.87 vẫn đọc được. Nguồn thật là `wake_reasons`: mỗi lý do thức có danh tính, lớp, nghĩa vụ, revision nguồn và
    # giờ đủ điều kiện. Sự kiện (origin=event) chống giao lại bằng `source_ref` của nguồn; hẹn giờ (origin=timer) mỗi
    # lần một id, hẹn mới chỉ thay hẹn cũ cùng nghĩa vụ. Lịch vật lý tính lại từ các lý do còn chờ (_recompute_wake).

    @staticmethod
    def _wake(c, goal_id: str, brain_id: str, kind: str, due_at: float, reason: str, keep_earlier: bool = False):
        if keep_earlier:
            old = c.execute("SELECT due_at FROM wakeups WHERE goal_id=? AND kind=?", (goal_id, kind)).fetchone()
            if old is not None and float(old["due_at"]) <= float(due_at):
                return
        c.execute("INSERT INTO wakeups(goal_id,brain_id,kind,due_at,reason,updated_at) VALUES(?,?,?,?,?,?) "
                  "ON CONFLICT(goal_id,kind) DO UPDATE SET due_at=excluded.due_at, reason=excluded.reason, "
                  "updated_at=excluded.updated_at",
                  (goal_id, brain_id, kind, float(due_at), str(reason or "")[:200], time.time()))

    @classmethod
    def _reason_event(cls, c, goal_id: str, brain_id: str, code: str, ref: str, revision: int,
                      due_at: Optional[float] = None, wake_at: Optional[float] = None) -> bool:
        """Ghi một lý do sự kiện. Giao lại cùng `(code, ref)` thì bỏ qua, dù dòng đầu còn chờ hay đã phục vụ.
        Sự kiện mới đặt lịch vật lý về giờ của nó (sớm nhất), nên mục tiêu thức đúng một lần để xét, kể cả khi đang
        bị gác; lần thức đó tự tính lại lịch. `wake_at`: giờ thức khác giờ đủ điều kiện (giữ lịch tới bàn giao)."""
        now = time.time()
        due = now if due_at is None else float(due_at)
        cur = c.execute("INSERT OR IGNORE INTO wake_reasons(goal_id,brain_id,wake_kind,code,origin,slot,revision,"
                        "source_ref,due_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (goal_id, brain_id, "work", str(code), "event", "", int(revision), str(ref), due, now))
        if cur.rowcount == 1:
            cls._wake(c, goal_id, brain_id, "work", due if wake_at is None else float(wake_at),
                      _WAKE_TEXT.get(code, code), keep_earlier=True)
        return cur.rowcount == 1

    @classmethod
    def _reason_timer(cls, c, goal_id: str, brain_id: str, code: str, due_at: float, revision: int,
                      now: Optional[float] = None) -> int:
        """Ghi một hẹn giờ mới. Hẹn cũ CÙNG nghĩa vụ đang chờ thành `superseded`, trong cùng giao dịch. Lịch vật lý
        chỉ kéo sớm lại (người gọi tính lại lịch đầy đủ ở cuối lần thức)."""
        now = time.time() if now is None else float(now)
        slot = HB.slot_of(code)
        kind = "observe" if slot == "observe" else "work"
        c.execute("UPDATE wake_reasons SET state='superseded', settled_at=? WHERE goal_id=? AND origin='timer' "
                  "AND slot=? AND state='pending'", (now, goal_id, slot))
        cur = c.execute("INSERT INTO wake_reasons(goal_id,brain_id,wake_kind,code,origin,slot,revision,source_ref,"
                        "due_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (goal_id, brain_id, kind, str(code), "timer", slot, int(revision),
                         "tm_" + secrets.token_hex(6), float(due_at), now))
        cls._wake(c, goal_id, brain_id, kind, float(due_at), _WAKE_TEXT.get(code, code), keep_earlier=True)
        c.execute("DELETE FROM wake_reasons WHERE goal_id=? AND origin='timer' AND state!='pending' AND settled_at<?",
                  (goal_id, now - SERVED_TIMER_KEEP_S))
        return int(cur.lastrowid)

    @staticmethod
    def _parked(row) -> bool:
        """Mục tiêu đang bị GÁC: còn nghĩa vụ nhưng không phục vụ được ngay (thiết kế mục 3, "Lịch vật lý"). Đọc từ
        trạng thái đã lưu, nên khởi động lại vẫn đúng."""
        if row is None:
            return True
        if int(row["paused"] or 0) or row["run_state"] == "blocked":
            return True
        return row["run_state"] == "waiting" and row["block_reason"] in ("source_drift", "handoff", "fit_rejected")

    @classmethod
    def _recompute_wake(cls, c, goal_id: str) -> None:
        """Tính lại lịch vật lý từ các lý do còn chờ. Không bị gác: mốc sớm nhất của mọi hẹn giờ và sự kiện. Bị gác:
        CHỈ hẹn gỡ gác (agent_recheck, guard_recheck, drift_recheck, handoff_wait); hẹn thử lại và sự kiện vẫn lưu
        nhưng không kéo lịch, kể cả đã quá giờ. Không còn mốc thì xoá dòng."""
        row = c.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
        if row is None or row["status"] != "active":
            c.execute("DELETE FROM wakeups WHERE goal_id=?", (goal_id,))
            return
        pend = c.execute("SELECT code, origin, slot, due_at FROM wake_reasons WHERE goal_id=? AND state='pending' "
                         "ORDER BY due_at", (goal_id,)).fetchall()
        parked = cls._parked(row)
        work = [r for r in pend if r["slot"] != "observe" and (
            not parked or (r["origin"] == "timer" and r["code"] in HB.UNPARK_CODES))]
        obs = [r for r in pend if r["slot"] == "observe"]
        for kind, rows in (("work", work), ("observe", obs)):
            if rows:
                first = min(rows, key=lambda r: float(r["due_at"]))
                cls._wake(c, goal_id, row["brain_id"], kind, float(first["due_at"]),
                          _WAKE_TEXT.get(first["code"], first["code"]))
            else:
                c.execute("DELETE FROM wakeups WHERE goal_id=? AND kind=?", (goal_id, kind))

    def add_reason_event(self, p: Principal, goal_id: str, code: str, ref: str, due_at: Optional[float] = None,
                         revision: Optional[int] = None) -> bool:
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            if row["status"] != "active":
                return False
            return self._reason_event(c, goal_id, p.brain_id, code, ref,
                                      int(row["revision"] if revision is None else revision), due_at)

    def add_timer(self, p: Principal, goal_id: str, code: str, due_at: float, now: Optional[float] = None) -> int:
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            return self._reason_timer(c, goal_id, p.brain_id, code, due_at, int(row["revision"]), now)

    def supersede_timers(self, p: Principal, goal_id: str, slots: tuple = ("retry", "check", "observe"),
                         now: Optional[float] = None) -> None:
        now = time.time() if now is None else float(now)
        marks = ",".join("?" for _ in slots)
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                return
            c.execute(f"UPDATE wake_reasons SET state='superseded', settled_at=? WHERE goal_id=? AND origin='timer' "
                      f"AND state='pending' AND slot IN ({marks})", (now, goal_id, *slots))

    def reasons(self, p: Principal, goal_id: str, state: Optional[str] = "pending") -> list:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            q, args = "SELECT * FROM wake_reasons WHERE goal_id=?", [goal_id]
            if state:
                q += " AND state=?"
                args.append(state)
            return [dict(r) for r in c.execute(q + " ORDER BY id", args).fetchall()]

    def reason_snapshot(self, p: Principal, goal_id: str, now: float, wake_kind: str = "work") -> list:
        """Ảnh chụp: lý do `pending` đã đủ điều kiện (`due_at <= now`) của một loại lịch, với cả sự kiện lẫn hẹn giờ.
        Chỉ các id trong ảnh chụp được xét và được phục vụ; lý do đến sau vẫn chờ lần sau."""
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            return [dict(r) for r in c.execute(
                "SELECT * FROM wake_reasons WHERE goal_id=? AND wake_kind=? AND state='pending' AND due_at<=? "
                "ORDER BY id", (goal_id, wake_kind, float(now))).fetchall()]

    def serve_reasons(self, p: Principal, goal_id: str, ids, by: str, now: Optional[float] = None) -> list:
        ids = [int(i) for i in (ids or ())]
        if not ids:
            return []
        now = time.time() if now is None else float(now)
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            return self._serve(c, goal_id, ids, by, now)

    @staticmethod
    def _serve(c, goal_id: str, ids, by: str, now: float) -> list:
        done = []
        for i in ids:
            cur = c.execute("UPDATE wake_reasons SET state='served', settled_at=?, settled_by=? WHERE id=? AND "
                            "goal_id=? AND state='pending'", (float(now), str(by)[:80], int(i), goal_id))
            if cur.rowcount == 1:
                done.append(int(i))
        return done

    def recompute_wake(self, p: Principal, goal_id: str) -> None:
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                return
            self._recompute_wake(c, goal_id)

    def log_wake(self, p: Principal, goal_id: str, entry: dict) -> int:
        """Ghi một dòng sổ thức (thiết kế mục 6) và cắt sổ còn WAKE_LOG_KEEP dòng gần nhất mỗi mục tiêu. Sổ để xem
        lại và tính chuỗi thử lại; không dùng để chống trùng."""
        e = dict(entry or {})
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                return 0
            cur = c.execute(
                "INSERT INTO wake_log(goal_id,brain_id,revision,wake_kind,seen_json,served_json,codes_json,"
                "policy_version,decision,why,action_id,model_calls,met_count,error_code,chain_start,signature,"
                "next_due_at,next_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (goal_id, p.brain_id, int(e.get("revision") or row["revision"]), str(e.get("wake_kind") or "work"),
                 _j(list(e.get("seen") or [])), _j(list(e.get("served") or [])), _j(list(e.get("codes") or [])),
                 str(e.get("policy_version") or HB.POLICY_VERSION), str(e.get("decision") or "sleep"),
                 str(e.get("why") or "")[:300], str(e.get("action_id") or ""), int(e.get("model_calls") or 0),
                 e.get("met_count"), str(e.get("error_code") or ""), 1 if e.get("chain_start") else 0,
                 str(e.get("signature") or ""), e.get("next_due_at"), str(e.get("next_code") or ""),
                 float(e.get("at") or time.time())))
            c.execute("DELETE FROM wake_log WHERE goal_id=? AND id NOT IN (SELECT id FROM wake_log WHERE goal_id=? "
                      "ORDER BY id DESC LIMIT ?)", (goal_id, goal_id, WAKE_LOG_KEEP))
            return int(cur.lastrowid)

    def wake_log(self, p: Principal, goal_id: str, limit: int = WAKE_LOG_KEEP, revision: Optional[int] = None) -> list:
        """Sổ thức, cũ trước mới sau."""
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            q, args = "SELECT * FROM wake_log WHERE goal_id=?", [goal_id]
            if revision is not None:
                q += " AND revision=?"
                args.append(int(revision))
            rows = c.execute(q + " ORDER BY id DESC LIMIT ?", (*args, int(limit))).fetchall()
            out = []
            for r in reversed(rows):
                d = dict(r)
                for k in ("seen_json", "served_json", "codes_json"):
                    d[k[:-5]] = json.loads(d.pop(k) or "[]")
                out.append(d)
            return out

    def observe_source(self, p: Principal, goal_id: str, path: str, sha256: str, verdict: str,
                       now: Optional[float] = None) -> bool:
        """Mốc QUAN SÁT file sản phẩm bị sửa ngoài Javis (thiết kế mục 5), tách khỏi mốc được phép thay file
        (`published`, không đụng tới ở đây). Trả True khi đây là hash chưa từng thấy."""
        now = time.time() if now is None else float(now)
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                return False
            cur = c.execute("INSERT OR IGNORE INTO source_observations(goal_id,path,sha256,first_seen_at,verdict) "
                            "VALUES(?,?,?,?,?)", (goal_id, str(path), str(sha256), now, str(verdict or "")))
            return cur.rowcount == 1

    def source_observations(self, p: Principal, goal_id: str) -> list:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            return [dict(r) for r in c.execute("SELECT * FROM source_observations WHERE goal_id=? ORDER BY "
                                               "first_seen_at", (goal_id,)).fetchall()]

    # Đường cũ: ghi thẳng lịch vật lý. Mã A2 hẹn lịch qua lý do; test và công cụ vận hành còn dùng hàm này.
    def set_wake(self, p: Principal, goal_id: str, kind: str, due_at: float, reason: str = "") -> None:
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            self._wake(c, goal_id, p.brain_id, kind, due_at, reason)

    def clear_wake(self, p: Principal, goal_id: str, kind: Optional[str] = None) -> None:
        """Xoá lịch vật lý, và cho mọi hẹn giờ đang chờ của loại đó thành `superseded` để lần tính lại không dựng
        lại lịch. Sự kiện đang chờ GIỮ NGUYÊN: đó là nghĩa vụ, không phải lịch."""
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                return
            now = time.time()
            if kind:
                c.execute("DELETE FROM wakeups WHERE goal_id=? AND kind=?", (goal_id, kind))
                c.execute("UPDATE wake_reasons SET state='superseded', settled_at=? WHERE goal_id=? AND "
                          "origin='timer' AND state='pending' AND wake_kind=?", (now, goal_id, kind))
            else:
                c.execute("DELETE FROM wakeups WHERE goal_id=?", (goal_id,))
                c.execute("UPDATE wake_reasons SET state='superseded', settled_at=? WHERE goal_id=? AND "
                          "origin='timer' AND state='pending'", (now, goal_id))

    def wakes(self, p: Principal, goal_id: str) -> list:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            return [{"kind": r["kind"], "due_at": r["due_at"], "reason": r["reason"]}
                    for r in c.execute("SELECT * FROM wakeups WHERE goal_id=? ORDER BY due_at", (goal_id,)).fetchall()]

    def due_wakeups(self, now: float, limit: int = 20) -> list:
        """Lịch tới hạn của mục tiêu còn active, xếp theo `due_at` (cũ nhất trước, không bỏ đói). Chỉ host (tick) gọi.
        Lịch `work` của mục tiêu tạm dừng bỏ qua; lịch `observe` thì không: tạm dừng vẫn quan sát guard (A2 mục 7)."""
        with closing(self._conn()) as c:
            rows = c.execute("SELECT w.goal_id, w.brain_id, w.kind, w.due_at FROM wakeups w JOIN goals g "
                             "ON g.id=w.goal_id WHERE w.due_at<=? AND g.status='active' AND "
                             "(g.paused=0 OR w.kind='observe') ORDER BY w.due_at LIMIT ?",
                             (float(now), int(limit))).fetchall()
            return [dict(r) for r in rows]

    def claim_wake(self, p: Principal, goal_id: str, kind: str, due_at: float, until: float) -> bool:
        """NHẬN một lịch tới hạn bằng CAS trên due_at và DỜI nó tới `until` thay vì xoá: tiến trình chết sau khi nhận
        thì lịch tự tới hạn lại. Hai nhịp cùng thấy một lịch thì chỉ một bên nhận được."""
        with self._Tx(self) as c:
            cur = c.execute("UPDATE wakeups SET due_at=?, reason=?, updated_at=? WHERE goal_id=? AND kind=? AND "
                            "brain_id=? AND due_at=?", (float(until), "đang xử lý (tự tới hạn lại nếu bị ngắt)",
                                                        time.time(), goal_id, kind, p.brain_id, float(due_at)))
            return cur.rowcount == 1

    # ───────────── nâng lên A2 và đối soát ─────────────

    def _a2_migrate(self) -> None:
        """Lần đầu A2 mở một kho có từ trước: dựng lại lý do từ chính `goal_events` cho mục tiêu active (mục 3).
        Revision chưa có lượt việc: một `created`. Phản hồi ghi sau lượt việc gần nhất của revision: một `feedback`
        mỗi phản hồi, cùng khoá với lúc ghi thường. Lịch cũ không có lý do thì lần thức đó coi như `review`."""
        with self._Tx(self) as c:
            for g in c.execute("SELECT * FROM goals WHERE status='active'").fetchall():
                rev = int(g["revision"])
                last = c.execute("SELECT MAX(created_at) AS t FROM actions WHERE goal_id=? AND revision=? AND "
                                 "kind='work'", (g["id"], rev)).fetchone()["t"]
                if last is None:
                    self._reason_event(c, g["id"], g["brain_id"], "created", f"migrate:rev:{rev}", rev,
                                       due_at=float(g["created_at"]))
                for e in c.execute("SELECT id, created_at FROM goal_events WHERE goal_id=? AND revision=? AND "
                                   "kind LIKE 'feedback.%' AND kind!='feedback.goal_fit_rejected' ORDER BY id",
                                   (g["id"], rev)).fetchall():
                    if last is None or float(e["created_at"]) > float(last):
                        self._reason_event(c, g["id"], g["brain_id"], "feedback", f"fb:{e['id']}", rev,
                                           due_at=float(e["created_at"]))

    def _a2_reconcile(self) -> None:
        """Đối soát sau khi quay về bản cũ rồi nâng lại (mục 3): bản 0.87 có thể đã làm việc mà không ghi id lý do.
        Sự kiện `pending` cùng revision có `created_at` TRƯỚC lúc một lượt việc như vậy BẮT ĐẦU thì chốt `served` theo
        lượt đó: chỉ những sự kiện đó lượt cũ mới có thể đã thấy trong đầu vào."""
        with self._Tx(self) as c:
            rows = c.execute(
                "SELECT r.id AS rid, a.id AS aid FROM wake_reasons r JOIN actions a ON a.goal_id=r.goal_id "
                "AND a.revision=r.revision AND a.kind='work' AND a.created_at>r.created_at "
                "WHERE r.origin='event' AND r.state='pending' AND a.intent_json NOT LIKE '%\"wake_reasons\"%' "
                "ORDER BY a.created_at").fetchall()
            for r in rows:
                c.execute("UPDATE wake_reasons SET state='served', settled_at=?, settled_by=? WHERE id=? AND "
                          "state='pending'", (time.time(), f"reconciled:{r['aid']}", r["rid"]))

    # ───────────── trạng thái chạy và khoá lượt ─────────────

    def run_state(self, p: Principal, goal_id: str) -> dict:
        with closing(self._conn()) as c:
            r = self._goal_row(c, p, goal_id)
            if r is None:
                return {}
            return {"run_state": r["run_state"], "block_reason": r["block_reason"]}

    def set_run_state(self, p: Principal, goal_id: str, run_state: str, reason: str = "",
                      notify: Optional[str] = None, payload: Optional[dict] = None, idem: Optional[str] = None) -> None:
        """Đổi trạng thái chạy; `notify` là loại tin outbox ghi CÙNG giao dịch (idem chống báo lặp)."""
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            changed = (row["run_state"], row["block_reason"]) != (run_state, reason)
            c.execute("UPDATE goals SET run_state=?, block_reason=?, updated_at=? WHERE id=?",
                      (run_state, str(reason or "")[:80], now, goal_id))
            if changed:
                c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,created_at) "
                          "VALUES(?,?,?,?,?,?,?)", (goal_id, row["revision"], f"run.{run_state}", "host",
                                                    _j({"reason": reason, **(payload or {})}), p.by, now))
            if notify:
                c.execute("INSERT OR IGNORE INTO outbox(goal_id,kind,payload_json,created_at,idem) VALUES(?,?,?,?,?)",
                          (goal_id, notify, _j({"revision": row["revision"], "reason": reason, **(payload or {})}),
                           now, idem))

    def claim_lease(self, p: Principal, goal_id: str, owner: str, until: float, now: float) -> bool:
        """Chỉ một lượt advance trên một mục tiêu cùng lúc. Khoá có hạn: tiến trình chết thì khoá tự hết."""
        with self._Tx(self) as c:
            cur = c.execute("UPDATE goals SET lease_owner=?, lease_until=? WHERE id=? AND brain_id=? AND "
                            "(lease_until IS NULL OR lease_until<?)",
                            (owner, float(until), goal_id, p.brain_id, float(now)))
            return cur.rowcount == 1

    def release_lease(self, p: Principal, goal_id: str, owner: str) -> None:
        with self._Tx(self) as c:
            c.execute("UPDATE goals SET lease_owner=NULL, lease_until=NULL WHERE id=? AND brain_id=? AND lease_owner=?",
                      (goal_id, p.brain_id, owner))

    # ───────────── sổ hành động ─────────────

    def begin_action(self, p: Principal, goal_id: str, revision: int, kind: str, lease_until: float,
                     now: Optional[float] = None, intent: Optional[dict] = None, wake: bool = True) -> Optional[dict]:
        """Ghi Ý ĐỊNH hành động TRƯỚC khi tác động. Hành động `work` giữ một lượt gọi model trong cùng giao dịch;
        hết hạn mức thì trả None và không ghi gì. Kèm lịch phục hồi lúc hết khoá: tiến trình chết giữa chừng thì
        tick sau đối soát được, không bỏ quên mục tiêu."""
        now = time.time() if now is None else float(now)
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            it = intent or {}
            if "agent_key" not in it and self._goal_agent(c, goal_id):
                # Mục tiêu đã thuộc một trợ lý thì MỌI hành động phải mang mã và version (review A1 tích hợp, P1-3):
                # thiếu thông tin không được ngầm bỏ kiểm.
                raise AgentStateError("agent_intent_missing")
            if "agent_key" in it:
                # A1: kiểm lại cổng agent NGAY trong giao dịch giữ lượt hay ghi ý định tác động: mục tiêu vẫn thuộc mã đó,
                # mã còn active, bật, đúng version. Không đạt thì không giữ lượt, không ghi gì.
                if self._goal_agent(c, goal_id) != it.get("agent_key"):
                    raise AgentStateError("goal_agent_changed")
                why = self._agent_block(c, p.brain_id, it.get("agent_key"), it.get("agent_config_version"))
                if why:
                    raise AgentStateError(why)
            if kind == "work":
                if not _under_ceiling(c, 1):
                    return None
                cur = c.execute("UPDATE goals SET calls_used=calls_used+1, updated_at=? WHERE id=? "
                                "AND calls_used<budget_calls", (now, goal_id))
                if cur.rowcount != 1:
                    return None
            seq = int(c.execute("SELECT COALESCE(MAX(seq),0) FROM actions WHERE goal_id=? AND revision=? AND kind=?",
                                (goal_id, int(revision), kind)).fetchone()[0]) + 1
            aid = f"act_{secrets.token_hex(8)}"
            c.execute("INSERT INTO actions(id,goal_id,revision,kind,seq,status,lease_until,intent_json,receipt_json,"
                      "created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (aid, goal_id, int(revision), kind, seq, "running", float(lease_until), _j(intent or {}), "{}",
                       now, now))
            if wake:
                self._reason_timer(c, goal_id, p.brain_id, "recovery", float(lease_until) + 1, int(revision), now)
            served = []
            if kind == "work" and it.get("wake_reasons"):
                # A2: lý do trong ảnh chụp được PHỤC VỤ cùng giao dịch ghi ý định hành động (thiết kế mục 3, bước 3).
                served = self._serve(c, goal_id, it["wake_reasons"], aid, now)
            return {"id": aid, "goal_id": goal_id, "revision": int(revision), "kind": kind, "seq": seq,
                    "served": served}

    # ───────────── phép thử cải thiện (M5) ─────────────

    def begin_experiment(self, p: Principal, goal_id: str, revision: int, baseline_ref: str, candidate_ref: str,
                         calls: int, explore_cap: int, payload: dict, now: Optional[float] = None,
                         agent: Optional[dict] = None) -> Optional[str]:
        """Ghi phép thử và giữ chỗ TOÀN BỘ lượt gọi nó cần trong CÙNG giao dịch: trong hạn mức chung của mục tiêu và
        trong phần dành cho khám phá. Không đủ thì trả None, không ghi gì (không tạo phép thử).

        A1: `agent` = {agent_key, agent_config_version} GHIM quyền của cả phép thử (bảng experiment_agents). Kiểm trong
        giao dịch giữ hạn mức: mục tiêu thuộc đúng mã, mã còn active, bật, đúng version; không thì AgentStateError.
        Mục tiêu đã thuộc một trợ lý mà không truyền `agent` thì cũng từ chối."""
        now = time.time() if now is None else float(now)
        calls = int(calls)
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            gkey = self._goal_agent(c, goal_id)
            if gkey or agent:
                ag = agent or {}
                if ag.get("agent_key") != gkey:
                    raise AgentStateError("agent_intent_missing" if not ag else "goal_agent_changed")
                why = self._agent_block(c, p.brain_id, gkey, ag.get("agent_config_version"))
                if why:
                    raise AgentStateError(why)
            if row["status"] != "active" or int(row["revision"]) != int(revision):
                return None
            if not _under_ceiling(c, calls):
                return None
            cur = c.execute("UPDATE goals SET calls_used=calls_used+?, explore_used=explore_used+?, updated_at=? "
                            "WHERE id=? AND calls_used+?<=budget_calls AND explore_used+?<=?",
                            (calls, calls, now, goal_id, calls, calls, int(explore_cap)))
            if cur.rowcount != 1:
                return None
            eid = _nid("exp")
            c.execute("INSERT INTO experiments(id,goal_id,revision,baseline_ref,candidate_ref,status,calls_reserved,"
                      "payload_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (eid, goal_id, int(revision), baseline_ref, candidate_ref, "running", calls, _j(payload or {}),
                       now, now))
            if gkey:
                c.execute("INSERT INTO experiment_agents(experiment_id,goal_id,agent_key,agent_config_version,created_at) "
                          "VALUES(?,?,?,?,?)", (eid, goal_id, gkey, int(agent["agent_config_version"]), now))
            c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,created_at) "
                      "VALUES(?,?,?,?,?,?,?)", (goal_id, int(revision), "experiment_started", "host",
                                                _j({"experiment_id": eid, "baseline_ref": baseline_ref,
                                                    "candidate_ref": candidate_ref, "calls": calls}), p.by, now))
            return eid

    def release_trial_call(self, p: Principal, goal_id: str, n: int = 1) -> None:
        """Trả lại lượt phép thử đã giữ mà model KHÔNG được gọi (engine bị chặn, lượt chưa bắt đầu)."""
        n = max(0, int(n))
        if not n:
            return
        with self._Tx(self) as c:
            c.execute("UPDATE goals SET calls_used=MAX(0,calls_used-?), explore_used=MAX(0,explore_used-?) "
                      "WHERE id=? AND brain_id=?", (n, n, goal_id, p.brain_id))

    def finish_experiment(self, p: Principal, experiment_id: str, verdict: str, reason: str, payload: dict,
                          refund: int = 0, apply: bool = False) -> dict:
        """Chốt kết quả, kể cả khi ứng viên thua. Chỉ chốt phép thử còn đang chạy (chốt một lần). `refund`: lượt đã
        giữ cho các lượt chưa bắt đầu, trả lại hạn mức trong cùng giao dịch.

        `apply` (chỉ với verdict eligible): đổi cách làm TRONG CÙNG giao dịch, sau khi kiểm lại mọi điều kiện chạy
        kiểm được bằng SQLite (_method_change_blocked). Bị chặn thì phép thử chốt `inconclusive` (lý do stopped hoặc
        goal_reframed) chứ không để lại một phép thử eligible chưa áp dụng (review M5, P1-2). Trả {finished, verdict,
        reason, applied, detail}."""
        now = time.time()
        with self._Tx(self) as c:
            r = c.execute("SELECT e.* FROM experiments e JOIN goals g ON g.id=e.goal_id WHERE e.id=? AND g.brain_id=?",
                          (experiment_id, p.brain_id)).fetchone()
            if r is None:
                raise ScopeError("phép thử không tồn tại trong brain này")
            if r["status"] != "running":
                return {"finished": False, "verdict": r["verdict"], "reason": r["reason"], "applied": False}
            applied, detail = False, ""
            if apply and verdict == "eligible":
                row = c.execute("SELECT * FROM goals WHERE id=?", (r["goal_id"],)).fetchone()
                why = self._method_change_blocked(c, row, int(r["revision"]), r["baseline_ref"], experiment_id)
                if why:
                    detail = why[1]
                    verdict, reason = "inconclusive", why[0]
                else:
                    self._set_method(c, p, row, r["baseline_ref"], r["candidate_ref"], int(r["revision"]),
                                     experiment_id, now)
                    applied = True
            old = json.loads(r["payload_json"] or "{}")
            extra = {"stop_detail": detail} if detail else {}
            c.execute("UPDATE experiments SET status='finished', verdict=?, reason=?, payload_json=?, applied=?, "
                      "updated_at=? WHERE id=?",
                      (verdict, reason, _j({**old, **(payload or {}), **extra}), int(applied), now, experiment_id))
            n = max(0, int(refund))
            if n:
                c.execute("UPDATE goals SET calls_used=MAX(0,calls_used-?), explore_used=MAX(0,explore_used-?) "
                          "WHERE id=?", (n, n, r["goal_id"]))
            c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,created_at) "
                      "VALUES(?,?,?,?,?,?,?)", (r["goal_id"], r["revision"], "experiment_finished", "host",
                                                _j({"experiment_id": experiment_id, "verdict": verdict,
                                                    "reason": reason, "applied": applied}), p.by, now))
            return {"finished": True, "verdict": verdict, "reason": reason, "applied": applied, "detail": detail}

    # Chốt THẬT mà một thay đổi cách làm không được vượt: guard đã nhảy, chỉ người dùng mở lại (resume khi guard đã
    # clear, hay bỏ guard). Các cờ còn lại do _gate ghi (feature_off, fit_rejected, guard_unknown) chỉ là KẾT QUẢ QUAN
    # SÁT lần trước, có thể đã hết hiệu lực khi công tắc bật lại hay người dùng đổi sang "Đúng ý" (review M5 vòng 2,
    # P2): điều kiện thật của chúng được kiểm lại tại chỗ, công tắc và guard bằng cổng ngay trước giao dịch, cách hiểu
    # bằng phản hồi mới nhất ngay trong giao dịch.
    _METHOD_LATCHES = ("guard",)
    TRANSIENT_BLOCKS = ("feature_off", "fit_rejected", "guard_unknown", "agent_off", "agent_changed")

    def clear_transient_block(self, p: Principal, goal_id: str, reasons: tuple = TRANSIENT_BLOCKS) -> bool:
        """Đồng bộ trạng thái sau khi cổng vừa kiểm điều kiện hiện tại và cho qua: gỡ cờ quan sát cũ (CAS theo đúng
        cờ đang ghi), không đụng chốt guard, pause, chờ người dùng duyệt hay hết hạn mức."""
        reasons = tuple(r for r in reasons if r in self.TRANSIENT_BLOCKS)
        if not reasons:
            return False
        marks = ",".join("?" for _ in reasons)
        with self._Tx(self) as c:
            cur = c.execute(f"UPDATE goals SET run_state='ready', block_reason='', updated_at=? WHERE id=? AND "
                            f"brain_id=? AND block_reason IN ({marks})", (time.time(), goal_id, p.brain_id, *reasons))
            return cur.rowcount == 1

    def experiment_agent(self, p: Principal, experiment_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT x.* FROM experiment_agents x JOIN goals g ON g.id=x.goal_id WHERE x.experiment_id=? "
                          "AND g.brain_id=?", (experiment_id, p.brain_id)).fetchone()
            return {"agent_key": r["agent_key"], "agent_config_version": int(r["agent_config_version"])} if r else None

    def _method_change_blocked(self, c, row, revision: int, baseline_ref: str,
                               experiment_id: Optional[str] = None) -> Optional[tuple]:
        """Lý do KHÔNG được đổi cách làm lúc này, kiểm trong giao dịch đang mở: (mã, chi tiết) hoặc None. Công tắc
        brain và guard là file, người gọi kiểm bằng cổng ngay trước; ở đây là phần SQLite, đọc TRẠNG THÁI HIỆN TẠI chứ
        không đọc cờ quan sát cũ: còn active, đúng revision, không tạm dừng, không có chốt guard, phản hồi cách hiểu
        MỚI NHẤT của revision không phải "Chưa đúng ý", và cách làm hiện tại vẫn là baseline."""
        if row is None or row["status"] != "active":
            return "stopped", "mục tiêu không còn active"
        if int(row["revision"]) != int(revision):
            return "goal_reframed", "mục tiêu đã sang revision khác"
        if row["paused"]:
            return "stopped", "người dùng đang tạm dừng mục tiêu"
        gkey = self._goal_agent(c, row["id"])
        pin = c.execute("SELECT * FROM experiment_agents WHERE experiment_id=?",
                        (str(experiment_id or ""),)).fetchone() if experiment_id else None
        if gkey and (pin is None or pin["agent_key"] != gkey):
            # Phép thử không ghim quyền (hay ghim mã khác) thì không được áp dụng cho mục tiêu của trợ lý.
            return "stopped", "phép thử không mang quyền của trợ lý sở hữu"
        ablock = self._agent_block(c, row["brain_id"], gkey, pin["agent_config_version"] if pin else None)
        if ablock:
            # A1: agent sở hữu phải còn active, bật và CÙNG version lúc bắt đầu phép thử, NGAY trong giao dịch đổi cách
            # làm. Tắt rồi bật giữa phép thử là version mới: kết quả theo quyền cũ không được áp dụng.
            return "stopped", f"trợ lý của mục tiêu chưa cho phép ({ablock})"
        if row["block_reason"] in self._METHOD_LATCHES:
            return "stopped", f"mục tiêu đang bị chặn: {row['block_reason']}"
        fit = c.execute("SELECT kind FROM goal_events WHERE goal_id=? AND revision=? AND kind IN "
                        "('feedback.goal_fit_confirmed','feedback.goal_fit_rejected') ORDER BY id DESC LIMIT 1",
                        (row["id"], int(revision))).fetchone()
        if fit is not None and fit["kind"] == "feedback.goal_fit_rejected":
            return "stopped", "người dùng nói cách hiểu chưa đúng"
        if R.effective_method(self._record(c, row)) != baseline_ref:
            return "stopped", "cách làm hiện tại không còn là baseline của phép thử"
        return None

    def _set_method(self, c, p: Principal, row, from_ref: str, to_ref: str, revision: int, experiment_id: str,
                    now: float) -> None:
        # Ref quay-lại mang theo đúng phạm vi nó đã được kiểm: mặc định thì 0 (luôn được phép), ref đã học thì
        # revision của nó. Không suy phạm vi của ref cũ từ revision hiện tại (review M5, P1-3).
        prev_rev = 0 if from_ref == R.DEFAULT_METHOD else int(row["method_revision"] or 0)
        c.execute("UPDATE goals SET method_ref=?, method_prev_ref=?, method_revision=?, method_prev_revision=?, "
                  "updated_at=? WHERE id=?", (to_ref, from_ref, int(revision), prev_rev, now, row["id"]))
        c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,created_at) "
                  "VALUES(?,?,?,?,?,?,?)", (row["id"], int(revision), "method_changed", "host",
                                            _j({"from": from_ref, "to": to_ref, "experiment_id": experiment_id}),
                                            p.by, now))

    @staticmethod
    def _experiment(r) -> dict:
        return {"id": r["id"], "goal_id": r["goal_id"], "revision": r["revision"], "baseline_ref": r["baseline_ref"],
                "candidate_ref": r["candidate_ref"], "status": r["status"], "verdict": r["verdict"],
                "reason": r["reason"], "calls_reserved": r["calls_reserved"], "applied": bool(r["applied"]),
                "payload": json.loads(r["payload_json"] or "{}"), "created_at": r["created_at"]}

    def experiments(self, p: Principal, goal_id: str) -> list:
        """Các phép thử của mục tiêu, mới nhất trước."""
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            return [self._experiment(r) for r in c.execute(
                "SELECT * FROM experiments WHERE goal_id=? ORDER BY created_at DESC, rowid DESC", (goal_id,)).fetchall()]

    def apply_method(self, p: Principal, goal_id: str, expected_revision: int, from_ref: str, to_ref: str,
                     experiment_id: str) -> None:
        """Đổi cách làm của mục tiêu. Agent CHỈ đổi được khi có phép thử eligible của đúng revision, đúng cặp cách
        làm, chưa áp dụng; và cách làm hiện tại vẫn là baseline của phép thử đó (CAS). Giữ ref cũ để quay lại."""
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            # A1: áp dụng cách làm là tác động lên mục tiêu: agent sở hữu phải còn active và bật, kiểm trong giao dịch này.
            why = self._agent_block(c, p.brain_id, self._goal_agent(c, goal_id))
            if why:
                raise AgentStateError(why)
            e = c.execute("SELECT * FROM experiments WHERE id=? AND goal_id=?", (experiment_id, goal_id)).fetchone()
            if (e is None or e["verdict"] != "eligible" or e["status"] != "finished" or e["applied"]
                    or int(e["revision"]) != int(expected_revision) or e["baseline_ref"] != from_ref
                    or e["candidate_ref"] != to_ref):
                raise R.GoalRejected("không có phép thử eligible khớp để đổi cách làm")
            why = self._method_change_blocked(c, row, int(expected_revision), from_ref, experiment_id)
            if why:
                raise ConflictError(why[1])
            self._set_method(c, p, row, from_ref, to_ref, int(expected_revision), experiment_id, now)
            c.execute("UPDATE experiments SET applied=1, updated_at=? WHERE id=?", (now, experiment_id))

    def revert_method(self, p: Principal, goal_id: str, seen_revision: Optional[int] = None) -> str:
        """Người dùng quay về cách làm trước đó. CHỈ owner. Ref quay lại giữ ĐÚNG phạm vi nó đã được kiểm (không gán
        revision hiện tại cho nó, review M5, P1-3): nếu phạm vi đó không phải revision hiện tại thì cách làm có hiệu
        lực là mặc định. Trả cách làm có hiệu lực sau khi quay lại."""
        if p.kind != "owner":
            raise PermissionError("chỉ người dùng mới quay lại cách làm cũ")
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            prev = row["method_prev_ref"] or ""
            if not prev:
                raise R.GoalRejected("mục tiêu chưa đổi cách làm nào để quay lại")
            c.execute("UPDATE goals SET method_ref=?, method_prev_ref='', method_revision=?, method_prev_revision=0, "
                      "updated_at=? WHERE id=?", (prev, int(row["method_prev_revision"] or 0), now, goal_id))
            c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,created_at) "
                      "VALUES(?,?,?,?,?,?,?)", (goal_id, row["revision"], "method_reverted", "owner",
                                                _j({"from": row["method_ref"], "to": prev,
                                                    "seen_revision": seen_revision}), p.by, now))
            row2 = c.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
            return R.effective_method(self._record(c, row2))

    # ───────────── sổ lượt gọi chưa gắn mục tiêu (bộ lập mục tiêu) ─────────────

    def reserve_ledger_call(self, p: Principal, kind: str, ref: str = "") -> Optional[int]:
        """Giữ chỗ MỘT lượt engine chưa gắn mục tiêu nào (bộ lập mục tiêu) TRƯỚC khi gọi, trong trần chung. Trả id
        dòng sổ, hoặc None nếu chạm trần (không ghi gì). Dòng giữ chỗ được tính ngay; chỉ hoàn khi engine không được
        gọi (release_ledger_call). Gọi rồi mà lỗi hay không ra mục tiêu vẫn tính."""
        now = time.time()
        with self._Tx(self) as c:
            if not _under_ceiling(c, 1):
                return None
            cur = c.execute("INSERT INTO call_ledger(brain_id,kind,ref,status,created_at,updated_at) "
                            "VALUES(?,?,?,?,?,?)", (p.brain_id, str(kind), str(ref or "")[:200], "used", now, now))
            return int(cur.lastrowid)

    def release_ledger_call(self, p: Principal, ledger_id: int) -> None:
        with self._Tx(self) as c:
            c.execute("UPDATE call_ledger SET status='released', updated_at=? WHERE id=? AND brain_id=? "
                      "AND status='used'", (time.time(), int(ledger_id), p.brain_id))

    def ledger_calls(self, p: Principal) -> list:
        with closing(self._conn()) as c:
            return [dict(r) for r in c.execute("SELECT * FROM call_ledger WHERE brain_id=? ORDER BY id",
                                               (p.brain_id,)).fetchall()]

    def release_call(self, p: Principal, goal_id: str) -> None:
        """Trả lại lượt đã giữ mà model KHÔNG được gọi (engine bị chặn, chưa sẵn sàng)."""
        with self._Tx(self) as c:
            c.execute("UPDATE goals SET calls_used=MAX(0,calls_used-1) WHERE id=? AND brain_id=?", (goal_id, p.brain_id))

    def finish_action(self, p: Principal, action_id: str, status: str, receipt: dict) -> None:
        with self._Tx(self) as c:
            r = c.execute("SELECT a.id FROM actions a JOIN goals g ON g.id=a.goal_id WHERE a.id=? AND g.brain_id=?",
                          (action_id, p.brain_id)).fetchone()
            if r is None:
                raise ScopeError("hành động không tồn tại trong brain này")
            c.execute("UPDATE actions SET status=?, receipt_json=?, lease_until=NULL, updated_at=? WHERE id=?",
                      (status, _j(receipt or {}), time.time(), action_id))

    @staticmethod
    def _action(r) -> dict:
        return {"id": r["id"], "goal_id": r["goal_id"], "revision": r["revision"], "kind": r["kind"], "seq": r["seq"],
                "status": r["status"], "lease_until": r["lease_until"], "intent": json.loads(r["intent_json"] or "{}"),
                "receipt": json.loads(r["receipt_json"] or "{}"), "created_at": r["created_at"]}

    def get_action(self, p: Principal, action_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT a.* FROM actions a JOIN goals g ON g.id=a.goal_id WHERE a.id=? AND g.brain_id=?",
                          (action_id, p.brain_id)).fetchone()
            return self._action(r) if r else None

    def actions(self, p: Principal, goal_id: str) -> list:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            return [self._action(r) for r in
                    c.execute("SELECT * FROM actions WHERE goal_id=? ORDER BY created_at, seq", (goal_id,)).fetchall()]

    def stale_actions(self, p: Principal, goal_id: str, now: float) -> list:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            return [self._action(r) for r in c.execute(
                "SELECT * FROM actions WHERE goal_id=? AND status='running' AND (lease_until IS NULL OR lease_until<?) "
                "ORDER BY created_at", (goal_id, float(now))).fetchall()]

    # ───────────── bằng chứng, đánh giá, sản phẩm đã đăng ─────────────

    def link_evidence(self, p: Principal, goal_id: str, revision: int, action_id: str, evidence_id: str,
                      kind: str, content_hash: str = "") -> None:
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            c.execute("INSERT OR IGNORE INTO evidence_links VALUES(?,?,?,?,?,?,?)",
                      (goal_id, int(revision), str(action_id or ""), evidence_id, kind, str(content_hash or ""),
                       time.time()))

    def evidence_for(self, p: Principal, goal_id: str, revision: int, kind: Optional[str] = None) -> list:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            q, args = "SELECT * FROM evidence_links WHERE goal_id=? AND revision=?", [goal_id, int(revision)]
            if kind:
                q += " AND kind=?"
                args.append(kind)
            return [dict(r) for r in c.execute(q + " ORDER BY created_at", args).fetchall()]

    def add_assessment(self, p: Principal, a: dict) -> int:
        with self._Tx(self) as c:
            if self._goal_row(c, p, a["goal_id"]) is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            cur = c.execute("INSERT INTO assessments(goal_id,revision,verdict,payload_json,created_at) VALUES(?,?,?,?,?)",
                            (a["goal_id"], int(a["revision"]), a["verdict"], _j(a), time.time()))
            return int(cur.lastrowid)

    def assessments(self, p: Principal, goal_id: str) -> list:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            return [json.loads(r["payload_json"]) for r in
                    c.execute("SELECT payload_json FROM assessments WHERE goal_id=? ORDER BY id", (goal_id,)).fetchall()]

    def published(self, p: Principal, goal_id: str, path: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return None
            r = c.execute("SELECT * FROM published WHERE goal_id=? AND path=?", (goal_id, path)).fetchone()
            return dict(r) if r else None

    # ═══════════════════ Bàn giao lượt chat (review mã bàn giao, P1-2) ═══════════════════
    # Một revision lập hay sửa trong lượt chat có MỘT dòng bàn giao: pending tới khi lượt đó bàn giao (done), hay quyền
    # thực thi chuyển cho việc nền (expired: lượt chat không còn chạy, hoặc tiến trình sở hữu đã chết). Chuyển trạng
    # thái trong giao dịch, nên bàn giao đến muộn sau khi việc nền đã nhận quyền thì bị từ chối, và ngược lại.

    @staticmethod
    def _open_handoff(c, goal_id: str, revision: int, message_ref: str, owner: str, now: float,
                      agent_key: Optional[str] = None, agent_version: Optional[int] = None) -> None:
        if agent_key:
            # A1: agent và version lúc mở bàn giao ở bảng riêng; bảng handoffs giữ nguyên cột để 0.86.x còn ghi được.
            c.execute("INSERT OR REPLACE INTO handoff_agents(goal_id,revision,agent_key,agent_config_version,created_at) "
                      "VALUES(?,?,?,?,?)", (goal_id, int(revision), agent_key, int(agent_version or 0), now))
        c.execute("INSERT OR REPLACE INTO handoffs(goal_id,revision,message_ref,owner,status,created_at,updated_at) "
                  "VALUES(?,?,?,?,?,?,?)",
                  (goal_id, int(revision), str(message_ref or ""), str(owner), "pending", now, now))

    def handoff(self, p: Principal, goal_id: str, revision: int) -> Optional[dict]:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return None
            r = c.execute("SELECT * FROM handoffs WHERE goal_id=? AND revision=?", (goal_id, int(revision))).fetchone()
            return dict(r) if r else None

    def handoff_gate(self, p: Principal, goal_id: str, revision: int, owner: str, turn_active: bool) -> str:
        """Cổng của việc nền và bước đăng. "clear": không có bàn giao đang chờ. "pending": lượt chat của CHÍNH tiến
        trình này vẫn đang chạy, chưa được làm. "expired": lượt đó không còn chạy, hoặc tiến trình sở hữu đã chết; quyền
        chuyển cho việc nền, NGAY trong giao dịch này, để bàn giao đến muộn không được nhận nữa."""
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            r = c.execute("SELECT * FROM handoffs WHERE goal_id=? AND revision=?", (goal_id, int(revision))).fetchone()
            if r is None or r["status"] != "pending":
                return "clear"
            if r["owner"] == str(owner) and turn_active:
                return "pending"
            c.execute("UPDATE handoffs SET status='expired', updated_at=? WHERE goal_id=? AND revision=?",
                      (time.time(), goal_id, int(revision)))
            return "expired"

    def finish_handoff(self, p: Principal, goal_id: str, revision: int, message_ref: str,
                       adopt: Optional[dict] = None) -> str:
        """Bàn giao cuối lượt, MỘT giao dịch. Chỉ khi dòng bàn giao của đúng revision và đúng tin nhắn còn pending;
        không thì "handoff_expired" (việc nền đã nhận quyền) hay "no_handoff", và không làm gì.

        `adopt` = {path, sha256, evidence_id}: tiếp nhận bản bộ não viết trong lượt (người gọi đã đối chiếu biên nhận
        ghi thành công với bytes trên đĩa và đã lưu bản chụp): gắn bằng chứng `chat_output`, ghi sự kiện
        `artifact_adopted`, đặt mốc `published` nguồn chat (cho lần sửa sau thay được file). Mục tiêu không còn active,
        đang pause hay đã sang revision khác thì không tiếp nhận. Không tạo receipt việc nền, không tính lượt model.
        Sau đó nhả lịch việc nền về ngay để đánh giá. Trả "adopted", "released" hay lý do."""
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            h = c.execute("SELECT * FROM handoffs WHERE goal_id=? AND revision=?", (goal_id, int(revision))).fetchone()
            if h is None or h["message_ref"] != str(message_ref):
                return "no_handoff"
            if h["status"] != "pending":
                return "handoff_expired" if h["status"] == "expired" else "already_done"
            result = "released"
            active = row["status"] == "active" and not int(row["paused"] or 0) and int(row["revision"]) == int(revision)
            # A1: chỉ tiếp nhận khi agent của mục tiêu là agent mở bàn giao này, còn active, bật và CÙNG version lúc mở.
            # Kiểm ngay trong giao dịch tiếp nhận; tắt hay đổi công tắc giữa lượt thì bản chat không được tiếp nhận.
            ha = c.execute("SELECT * FROM handoff_agents WHERE goal_id=? AND revision=?",
                           (goal_id, int(revision))).fetchone()
            gkey = self._goal_agent(c, goal_id)
            agent_why = ("handoff_agent_mismatch" if ha is None or ha["agent_key"] != gkey
                         else self._agent_block(c, p.brain_id, gkey, ha["agent_config_version"]))
            if adopt and not active:
                result = "not_active"
            elif adopt and agent_why:
                result = agent_why
            elif adopt:
                c.execute("INSERT OR IGNORE INTO evidence_links VALUES(?,?,?,?,?,?,?)",
                          (goal_id, int(revision), f"chat:{message_ref}", adopt["evidence_id"], "chat_output",
                           str(adopt["sha256"]), now))
                c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,message_ref,payload_json,by,"
                          "idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                          (goal_id, int(revision), "artifact_adopted", "host", str(message_ref),
                           _j({"path": adopt["path"], "sha256": adopt["sha256"], "evidence_id": adopt["evidence_id"]}),
                           p.by, f"adopt:{int(revision)}", now))
                c.execute("INSERT INTO published VALUES(?,?,?,?,?) ON CONFLICT(goal_id,path) DO UPDATE SET "
                          "sha256=excluded.sha256, action_id=excluded.action_id, created_at=excluded.created_at",
                          (goal_id, adopt["path"], adopt["sha256"], f"chat:{message_ref}", now))
                result = "adopted"
            c.execute("UPDATE handoffs SET status='done', updated_at=? WHERE goal_id=? AND revision=?",
                      (now, goal_id, int(revision)))
            if active:
                self._reason_event(c, goal_id, row["brain_id"], "handoff_done", f"handoff:{int(revision)}",
                                   int(revision))
            return result

    def handoff_agent(self, p: Principal, goal_id: str, revision: int) -> Optional[dict]:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return None
            r = c.execute("SELECT * FROM handoff_agents WHERE goal_id=? AND revision=?", (goal_id, int(revision))).fetchone()
            return {"agent_key": r["agent_key"], "agent_config_version": int(r["agent_config_version"])} if r else None

    def assign_goal(self, p: Principal, goal_id: str, agent_key: str, expected_revision: int) -> "R.GoalRecord":
        """Chủ dự án gán MỘT LẦN một mục tiêu CHƯA gán (có trước A1, hay tạo lúc chạy bản cũ) cho một agent `active`
        cùng brain. CAS trong một giao dịch: revision đúng `expected_revision` và chưa có dòng goal_agents. Chuyển mục
        tiêu giữa hai agent chưa hỗ trợ trong A1 (thiết kế mục 5).

        Đầu ra và khoá lượt cũ mất hiệu lực tự nhiên: ý định của các hành động trước lúc gán không mang mã này, nên cổng
        đăng không dùng lại chúng. Gán xong hẹn thức ngay (lần đầu là kiểm bằng code) nếu mục tiêu còn chạy được."""
        self._owner_only(p)
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            if int(row["revision"]) != int(expected_revision):
                raise ConflictError(f"mục tiêu đang ở revision {row['revision']}, không phải {expected_revision}")
            if self._goal_agent(c, goal_id):
                raise ConflictError("mục tiêu đã thuộc một trợ lý; A1 chưa hỗ trợ chuyển giữa hai trợ lý")
            a = c.execute("SELECT * FROM resonance_agents WHERE agent_key=? AND brain_id=?",
                          (str(agent_key or ""), p.brain_id)).fetchone()
            if a is None or a["status"] != "active":
                raise AgentStateError("chỉ gán cho trợ lý đang hoạt động trong brain này")
            c.execute("INSERT INTO goal_agents(goal_id,brain_id,agent_key,by,created_at) VALUES(?,?,?,?,?)",
                      (goal_id, p.brain_id, a["agent_key"], p.by, now))
            ev = c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,idempotency_key,"
                           "created_at) VALUES(?,?,?,?,?,?,?,?)",
                           (goal_id, int(row["revision"]), "agent_assigned", "owner",
                            _j({"agent_key": a["agent_key"], "slug": a["slug"]}), p.by, "agent_assigned", now))
            if row["status"] == "active" and row["block_reason"] in ("unassigned", "feature_off", "agent_off",
                                                                      "agent_missing", "agent_retired"):
                c.execute("UPDATE goals SET run_state='ready', block_reason='', updated_at=? WHERE id=?", (now, goal_id))
            if row["status"] == "active":
                # Mục tiêu có trước A1 không có lý do `created`: `assigned` là bước đầu của nó (A2 mục 3).
                self._reason_event(c, goal_id, p.brain_id, "assigned", f"ev:{ev.lastrowid}", int(row["revision"]))
                if json.loads((c.execute("SELECT frame_json FROM goal_revisions WHERE goal_id=? AND revision=?",
                                         (goal_id, row["revision"])).fetchone() or {"frame_json": "{}"})["frame_json"]
                              or "{}").get("guards"):
                    self._reason_timer(c, goal_id, p.brain_id, "guard_observe", now, int(row["revision"]), now)
            return self._record(c, c.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone())

    def wake_agent_goals(self, brain_id: str, agent_key: str, reason: str = "trợ lý được bật") -> int:
        """Bật (lại) một agent: hẹn thức NGAY các mục tiêu active, không tạm dừng, của mã đó, để lần thức đầu kiểm bằng
        code và đăng đầu ra hợp lệ đang giữ. Không mở lại pause, guard, mục tiêu đã huỷ hay kết thúc."""
        now = time.time()
        n = 0
        with self._Tx(self) as c:
            ag = c.execute("SELECT config_version FROM resonance_agents WHERE agent_key=? AND brain_id=?",
                           (str(agent_key or ""), brain_id)).fetchone()
            ver = int(ag["config_version"]) if ag else 0
            rows = c.execute("SELECT g.id, g.block_reason, g.revision FROM goals g JOIN goal_agents a ON a.goal_id=g.id "
                             "WHERE a.agent_key=? AND g.brain_id=? AND g.status='active' AND g.paused=0",
                             (str(agent_key or ""), brain_id)).fetchall()
            for r in rows:
                if r["block_reason"] in ("guard",):
                    continue
                rev = int(r["revision"])
                self._reason_event(c, r["id"], brain_id, "agent_enabled", f"agent:{agent_key}:{ver}", rev)
                fr = c.execute("SELECT frame_json FROM goal_revisions WHERE goal_id=? AND revision=?",
                               (r["id"], rev)).fetchone()
                if fr is not None and (json.loads(fr["frame_json"] or "{}").get("guards")):
                    # Bật lại thì quan sát guard NGAY (A2 mục 7): thẻ hết "không còn theo dõi" khi đã đọc lại guard.
                    self._reason_timer(c, r["id"], brain_id, "guard_observe", now, rev, now)
                n += 1
        return n

    def set_published(self, p: Principal, goal_id: str, path: str, sha256: str, action_id: str) -> None:
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            c.execute("INSERT INTO published VALUES(?,?,?,?,?) ON CONFLICT(goal_id,path) DO UPDATE SET "
                      "sha256=excluded.sha256, action_id=excluded.action_id, created_at=excluded.created_at",
                      (goal_id, path, sha256, action_id, time.time()))

    def finish(self, p: Principal, goal_id: str, expected_revision: int, status: str,
               payload: Optional[dict] = None) -> bool:
        """Kết thúc mục tiêu (succeeded/failed) CHỈ khi revision còn đúng revision đã được đánh giá.
        Revision đã đổi thì trả False: kết quả của revision cũ không đóng được mục tiêu mới."""
        if status not in ("succeeded", "failed"):
            raise ValueError("status kết thúc phải là succeeded hoặc failed")
        now = time.time()
        with self._Tx(self) as c:
            cur = c.execute("UPDATE goals SET status=?, run_state='dormant', block_reason='', updated_at=? "
                            "WHERE id=? AND brain_id=? AND revision=? AND status='active'",
                            (status, now, goal_id, p.brain_id, int(expected_revision)))
            if cur.rowcount != 1:
                return False
            c.execute("DELETE FROM wakeups WHERE goal_id=?", (goal_id,))
            # Mục tiêu kết thúc không nhận sự kiện nữa: bỏ lý do thức (A2 mục 6). Sổ thức giữ để xem lại.
            c.execute("DELETE FROM wake_reasons WHERE goal_id=?", (goal_id,))
            c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,created_at) "
                      "VALUES(?,?,?,?,?,?,?)", (goal_id, int(expected_revision), status, "host", _j(payload or {}),
                                                p.by, now))
            c.execute("INSERT OR IGNORE INTO outbox(goal_id,kind,payload_json,created_at,idem) VALUES(?,?,?,?,?)",
                      (goal_id, f"goal.{status}", _j({"revision": int(expected_revision), **(payload or {})}), now,
                       f"{status}:{int(expected_revision)}"))
            return True

    def notice(self, p: Principal, goal_id: str, kind: str, payload: dict, idem: Optional[str] = None) -> None:
        """Ghi một tin báo vào outbox (idem chống báo lặp). drain_outbox gửi cho người dùng."""
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            c.execute("INSERT OR IGNORE INTO outbox(goal_id,kind,payload_json,created_at,idem) VALUES(?,?,?,?,?)",
                      (goal_id, kind, _j({"revision": row["revision"], **(payload or {})}), time.time(), idem))

    # ═══════════════════ M4: phản hồi của người dùng và lệnh ═══════════════════

    FEEDBACK_KINDS = ("goal_fit_confirmed", "goal_fit_rejected", "outcome_accepted", "outcome_rejected")

    def record_feedback(self, p: Principal, goal_id: str, expected_revision: int, kind: str, data: dict,
                        idempotency_key: Optional[str] = None) -> dict:
        """Ghi một phản hồi có nghĩa rõ (spec 4.7). CHỈ người dùng (owner): agent không tự xác nhận. Gắn đúng
        revision (CAS): thẻ cũ không xác nhận được revision mới. Cùng khoá chống trùng thì không ghi lần hai.
        Hệ quả ghi CÙNG giao dịch: "Chưa đúng ý" dừng tác động tới khi có revision mới; phản hồi khác hẹn đánh giá lại."""
        if p.kind != "owner":
            raise PermissionError("chỉ người dùng mới xác nhận được")
        if kind not in self.FEEDBACK_KINDS:
            raise R.GoalRejected(f"loại phản hồi không hỗ trợ: {kind}")
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            if idempotency_key:
                old = c.execute("SELECT id FROM goal_events WHERE goal_id=? AND idempotency_key=?",
                                (goal_id, f"fb:{idempotency_key}")).fetchone()
                if old is not None:
                    return {"event_id": int(old["id"]), "duplicate": True}
            if row["status"] != "active":
                raise R.GoalRejected(f"mục tiêu đã {row['status']}")
            if int(row["revision"]) != int(expected_revision):
                raise ConflictError(f"mục tiêu đang ở revision {row['revision']}, không phải {expected_revision}")
            cur = c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,idempotency_key,"
                            "created_at) VALUES(?,?,?,?,?,?,?,?)",
                            (goal_id, int(expected_revision), f"feedback.{kind}", "owner", _j(data or {}), p.by,
                             f"fb:{idempotency_key}" if idempotency_key else None, now))
            if kind == "goal_fit_rejected":
                # Gác: lý do đang chờ giữ nguyên nhưng không kéo lịch; quan sát guard vẫn chạy (A2 mục 7).
                c.execute("UPDATE goals SET run_state='waiting', block_reason='fit_rejected', updated_at=? WHERE id=?",
                          (now, goal_id))
                self._recompute_wake(c, goal_id)
            else:
                self._reason_event(c, goal_id, p.brain_id, "feedback", f"fb:{cur.lastrowid}", int(expected_revision))
            return {"event_id": int(cur.lastrowid), "duplicate": False}

    def _latest_feedback(self, p: Principal, goal_id: str, revision: int, kinds: tuple) -> Optional[dict]:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return None
            marks = ",".join("?" for _ in kinds)
            rows = c.execute(f"SELECT * FROM goal_events WHERE goal_id=? AND revision=? AND kind IN ({marks}) "
                             "ORDER BY id DESC", (goal_id, int(revision), *[f"feedback.{k}" for k in kinds])).fetchall()
            return [{"kind": r["kind"][len("feedback."):], "by": r["by"], "created_at": r["created_at"],
                     **json.loads(r["payload_json"] or "{}")} for r in rows]

    def fit_status(self, p: Principal, goal_id: str, revision: int) -> str:
        """Xác nhận cách hiểu của ĐÚNG revision này: confirmed / rejected / unknown (im lặng là unknown)."""
        rows = self._latest_feedback(p, goal_id, revision, ("goal_fit_confirmed", "goal_fit_rejected")) or []
        if not rows:
            return "unknown"
        return "confirmed" if rows[0]["kind"] == "goal_fit_confirmed" else "rejected"

    def confirmation(self, p: Principal, goal_id: str, revision: int, criterion_id: str) -> Optional[dict]:
        """Xác nhận đầu ra mới nhất của một tiêu chí ở đúng revision, hoặc None."""
        for r in self._latest_feedback(p, goal_id, revision, ("outcome_accepted", "outcome_rejected")) or []:
            if r.get("criterion_id") == criterion_id:
                return {"verdict": r.get("verdict"), "artifact_ref": r.get("artifact_ref"), "comment": r.get("comment"),
                        "by": r.get("by"), "created_at": r.get("created_at")}
        return None

    def cancel(self, p: Principal, goal_id: str, seen_revision: Optional[int] = None) -> bool:
        """Người dùng huỷ mục tiêu. Luôn có hiệu lực (can thiệp của người dùng, spec 2.3); ghi revision người dùng
        đang nhìn. Tác động đã xảy ra không được mô tả là đã hoàn tác."""
        if p.kind != "owner":
            raise PermissionError("chỉ người dùng mới huỷ được mục tiêu")
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            if row["status"] != "active":
                return False
            c.execute("UPDATE goals SET status='cancelled', run_state='dormant', block_reason='', updated_at=? "
                      "WHERE id=?", (now, goal_id))
            c.execute("DELETE FROM wakeups WHERE goal_id=?", (goal_id,))
            c.execute("DELETE FROM wake_reasons WHERE goal_id=?", (goal_id,))
            c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,created_at) "
                      "VALUES(?,?,?,?,?,?,?)", (goal_id, row["revision"], "cancelled", "owner",
                                                _j({"seen_revision": seen_revision}), p.by, now))
            return True

    def clear_block(self, p: Principal, goal_id: str, reason: str) -> bool:
        """Người dùng mở lại một chặn cụ thể (ví dụ guard sau khi đã sửa). Chỉ owner; chỉ khi đúng lý do đang chặn."""
        if p.kind != "owner":
            raise PermissionError("chỉ người dùng mới mở lại được")
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None or row["block_reason"] != reason:
                return False
            c.execute("UPDATE goals SET run_state='ready', block_reason='', updated_at=? WHERE id=?", (now, goal_id))
            ev = c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,created_at) "
                           "VALUES(?,?,?,?,?,?,?)", (goal_id, row["revision"], "unblocked", "owner",
                                                     _j({"reason": reason}), p.by, now))
            self._reason_event(c, goal_id, p.brain_id, "resumed", f"ev:{ev.lastrowid}", int(row["revision"]))
            fr = c.execute("SELECT frame_json FROM goal_revisions WHERE goal_id=? AND revision=?",
                           (goal_id, row["revision"])).fetchone()
            if reason == "guard" and fr is not None and json.loads(fr["frame_json"] or "{}").get("guards"):
                # Mở lại sau guard: chốt guard đã xoá mọi hẹn, nên dựng lại lịch quan sát.
                self._reason_timer(c, goal_id, p.brain_id, "guard_observe", now + R.GUARD_OBSERVE_S,
                                   int(row["revision"]), now)
            return True

    DIRECTIVE_FIELDS = ("deadline", "target", "constraint", "guard")

    def drop_directive(self, p: Principal, goal_id: str, expected_revision: int, field: str, key: str) -> "R.GoalRecord":
        """ĐƯỜNG CÓ THẨM QUYỀN để bỏ một chỉ dẫn người dùng đã nêu (hạn chót, chỉ tiêu, ràng buộc) hay một guard:
        CHỈ owner, qua thao tác trên thẻ mục tiêu (M4). Bản cập nhật của bộ não không làm được việc này (M2, M3).
        Gắn revision (CAS), tạo revision mới ghi nguồn là người dùng, rồi hẹn làm tiếp theo cách hiểu mới. Bỏ guard
        đang chặn thì mở chặn đó; các chặn khác giữ nguyên."""
        if p.kind != "owner":
            raise PermissionError("chỉ người dùng mới bỏ được chỉ dẫn của mình")
        if field not in self.DIRECTIVE_FIELDS:
            raise R.GoalRejected(f"không bỏ được loại chỉ dẫn này: {field}")
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            if row["status"] != "active":
                raise R.GoalRejected(f"mục tiêu đã {row['status']}")
            if int(row["revision"]) != int(expected_revision):
                raise ConflictError(f"mục tiêu đang ở revision {row['revision']}, không phải {expected_revision}")
            prev = c.execute("SELECT * FROM goal_revisions WHERE goal_id=? AND revision=?",
                             (goal_id, row["revision"])).fetchone()
            fr = json.loads(prev["frame_json"]) if prev else {}
            user_cons = json.loads(row["user_constraints_json"] or "[]")
            key = str(key or "")
            if field == "deadline":
                h = dict(fr.get("horizon") or {})
                if h.get("kind") != "deadline" or not h.get("from_user"):
                    raise R.GoalRejected("mục tiêu không có hạn chót của người dùng để bỏ")
                fr["horizon"] = {"kind": "review", "from_user": False, "quote": "", "at": h.get("at"),
                                 "reason": "người dùng bỏ hạn chót"}
            elif field == "target":
                left = [t for t in (fr.get("targets") or []) if str(t.get("text")) != key]
                if len(left) == len(fr.get("targets") or []):
                    raise R.GoalRejected("không có chỉ tiêu này")
                fr["targets"] = left
            elif field == "constraint":
                if key not in (fr.get("constraints") or []) and key not in user_cons:
                    raise R.GoalRejected("không có ràng buộc này")
                fr["constraints"] = [x for x in (fr.get("constraints") or []) if x != key]
                user_cons = [x for x in user_cons if x != key]
            else:
                cur_guards = list(fr.get("guards") or [])
                hits = [g for g in cur_guards if str(g.get("id")) == key]
                if not hits:
                    raise R.GoalRejected("không có điều kiện bảo vệ này")
                if len(hits) > 1:
                    # Dữ liệu cũ có id trùng: không đoán người dùng muốn bỏ mục nào, không xoá cả hai (review M4, P1-3).
                    raise R.GoalRejected("có nhiều điều kiện bảo vệ cùng id; không bỏ để tránh xoá nhầm")
                fr["guards"] = [g for g in cur_guards if g is not hits[0]]
                fr["guard_seq"] = max(int(fr.get("guard_seq") or 0), max(R._guard_num(g.get("id")) for g in cur_guards))
            rev = int(row["revision"]) + 1
            c.execute("INSERT INTO goal_revisions VALUES(?,?,?,?,?,?,?)",
                      (goal_id, rev, prev["intent_id"] if prev else "", _j(fr), f"người dùng bỏ {field}", p.by, now))
            unblock = field == "guard" and row["block_reason"] in ("guard", "guard_unknown")
            c.execute("UPDATE goals SET revision=?, user_constraints_json=?, updated_at=?"
                      + (", run_state='ready', block_reason=''" if unblock else "") + " WHERE id=?",
                      (rev, _j(user_cons), now, goal_id))
            c.execute("INSERT INTO goal_events(goal_id,revision,kind,source,payload_json,by,idempotency_key,created_at) "
                      "VALUES(?,?,?,?,?,?,?,?)",
                      (goal_id, rev, "reframe", "owner", _j({"reason": f"người dùng bỏ {field}", "relation": "replace",
                                                            "field": field, "key": key}), p.by, f"reframe:{rev}", now))
            c.execute("INSERT INTO outbox(goal_id,kind,payload_json,created_at) VALUES(?,?,?,?)",
                      (goal_id, "goal.revised", _j({"revision": rev}), now))
            self._reason_event(c, goal_id, p.brain_id, "revised", f"rev:{rev}", rev)
            if not fr.get("guards"):
                c.execute("UPDATE wake_reasons SET state='superseded', settled_at=? WHERE goal_id=? AND "
                          "slot='observe' AND state='pending'", (now, goal_id))
                c.execute("DELETE FROM wakeups WHERE goal_id=? AND kind='observe'", (goal_id,))
            elif unblock:
                self._reason_timer(c, goal_id, p.brain_id, "guard_observe", now + R.GUARD_OBSERVE_S, rev, now)
            return self._record(c, c.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone())
