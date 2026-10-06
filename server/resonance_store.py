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
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import STATE_DIR
import resonance as R

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
CREATE TABLE IF NOT EXISTS published(
  goal_id TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, action_id TEXT NOT NULL,
  created_at REAL NOT NULL, PRIMARY KEY(goal_id, path));
"""

# Cột thêm từ M3 vào bảng đã có ở M2. Kho tạo bởi bản M2 không tự có cột mới qua CREATE IF NOT EXISTS,
# nên nâng cấp bằng ALTER TABLE: chỉ thêm, không xoá dữ liệu.
_ADDED_COLUMNS = (
    ("goals", "run_state", "TEXT NOT NULL DEFAULT 'ready'"),
    ("goals", "block_reason", "TEXT NOT NULL DEFAULT ''"),
    ("goals", "lease_owner", "TEXT"),
    ("goals", "lease_until", "REAL"),
    ("outbox", "idem", "TEXT"),
)
_POST_MIGRATION = "CREATE UNIQUE INDEX IF NOT EXISTS outbox_idem ON outbox(goal_id, idem) WHERE idem IS NOT NULL;"


class ScopeError(Exception):
    """Thao tác ngoài phạm vi của principal (brain khác, bản ghi không tồn tại)."""


class ConflictError(Exception):
    """`expected_revision` không còn khớp: có người đã sửa mục tiêu trước."""


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
        with closing(self._conn()) as c:
            c.executescript(_SCHEMA)
            for table, col, decl in _ADDED_COLUMNS:
                have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
                if col not in have:
                    c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            c.executescript(_POST_MIGRATION)

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
            guards=tuple(fr.get("guards") or ()),
            stage=fr.get("stage", "discovery"), mode=fr.get("mode", "achieve"), status=row["status"],
            budget_calls=row["budget_calls"], calls_used=row["calls_used"], paused=bool(row["paused"]))

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
               message_ref: Optional[str] = None) -> tuple:
        """Trả (GoalRecord, đã_tạo_mới). Cùng khoá chống trùng thì trả mục tiêu cũ, không ghi gì thêm."""
        now = time.time()
        msg = message_ref or idempotency_key
        with self._Tx(self) as c:
            old = c.execute("SELECT * FROM goals WHERE brain_id=? AND idempotency_key=?",
                            (p.brain_id, idempotency_key)).fetchone()
            if old is not None:
                return self._record(c, old), False
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
            # M3: mục tiêu mới được làm ngay ở lượt tick kế tiếp; có guard thì có lịch quan sát riêng.
            self._wake(c, gid, p.brain_id, "work", now, "tạo mục tiêu")
            if frame.get("guards"):
                self._wake(c, gid, p.brain_id, "observe", now + R.GUARD_OBSERVE_S, "quan sát guard")
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

    def list_open(self, p: Principal, session_id: Optional[str] = None) -> list:
        with closing(self._conn()) as c:
            q = "SELECT * FROM goals WHERE brain_id=? AND status='active'"
            args = [p.brain_id]
            if session_id is not None:
                q += " AND session_id=?"
                args.append(str(session_id))
            q += " ORDER BY updated_at DESC"
            return [self._record(c, r) for r in c.execute(q, args).fetchall()]

    def revise(self, p: Principal, goal_id: str, expected_revision: int, frame: dict, reason: str,
               intent_id: Optional[str] = None, message_ref: str = "", relation: str = "",
               intent: Optional[dict] = None) -> R.GoalRecord:
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
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
                self._wake(c, goal_id, row["brain_id"], "work", now, "sửa cách hiểu")
                if frame.get("guards"):
                    self._wake(c, goal_id, row["brain_id"], "observe", now + R.GUARD_OBSERVE_S, "quan sát guard",
                               keep_earlier=True)
            return self._record(c, c.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone())

    def set_paused(self, p: Principal, goal_id: str, paused: bool) -> None:
        """Chỉ người dùng (owner) đổi pause. Agent không tự bỏ pause của người dùng."""
        if p.kind != "owner":
            raise PermissionError("chỉ người dùng mới tạm dừng hoặc tiếp tục mục tiêu")
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            c.execute("UPDATE goals SET paused=?, updated_at=? WHERE id=?", (1 if paused else 0, time.time(), goal_id))
            if not paused:
                # Tiếp tục: làm ngay ở nhịp kế; đầu ra đã lưu trước khi dừng được dùng lại, không gọi model lần nữa.
                self._wake(c, goal_id, p.brain_id, "work", time.time(), "người dùng cho tiếp tục")
            c.execute("INSERT INTO goal_events(goal_id,kind,source,payload_json,by,created_at) VALUES(?,?,?,?,?,?)",
                      (goal_id, "paused" if paused else "resumed", "owner", "{}", p.by, time.time()))

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

    def set_wake(self, p: Principal, goal_id: str, kind: str, due_at: float, reason: str = "") -> None:
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            self._wake(c, goal_id, p.brain_id, kind, due_at, reason)

    def clear_wake(self, p: Principal, goal_id: str, kind: Optional[str] = None) -> None:
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                return
            if kind:
                c.execute("DELETE FROM wakeups WHERE goal_id=? AND kind=?", (goal_id, kind))
            else:
                c.execute("DELETE FROM wakeups WHERE goal_id=?", (goal_id,))

    def wakes(self, p: Principal, goal_id: str) -> list:
        with closing(self._conn()) as c:
            if self._goal_row(c, p, goal_id) is None:
                return []
            return [{"kind": r["kind"], "due_at": r["due_at"], "reason": r["reason"]}
                    for r in c.execute("SELECT * FROM wakeups WHERE goal_id=? ORDER BY due_at", (goal_id,)).fetchall()]

    def due_wakeups(self, now: float, limit: int = 20) -> list:
        """Lịch tới hạn của mục tiêu còn active và không bị người dùng tạm dừng. Chỉ host (tick) gọi."""
        with closing(self._conn()) as c:
            rows = c.execute("SELECT w.goal_id, w.brain_id, w.kind, w.due_at FROM wakeups w JOIN goals g "
                             "ON g.id=w.goal_id WHERE w.due_at<=? AND g.status='active' AND g.paused=0 "
                             "ORDER BY w.due_at LIMIT ?", (float(now), int(limit))).fetchall()
            return [dict(r) for r in rows]

    def claim_wake(self, p: Principal, goal_id: str, kind: str, due_at: float, until: float) -> bool:
        """NHẬN một lịch tới hạn bằng CAS trên due_at và DỜI nó tới `until` thay vì xoá: tiến trình chết sau khi nhận
        thì lịch tự tới hạn lại. Hai nhịp cùng thấy một lịch thì chỉ một bên nhận được."""
        with self._Tx(self) as c:
            cur = c.execute("UPDATE wakeups SET due_at=?, reason=?, updated_at=? WHERE goal_id=? AND kind=? AND "
                            "brain_id=? AND due_at=?", (float(until), "đang xử lý (tự tới hạn lại nếu bị ngắt)",
                                                        time.time(), goal_id, kind, p.brain_id, float(due_at)))
            return cur.rowcount == 1

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
                     now: Optional[float] = None, intent: Optional[dict] = None) -> Optional[dict]:
        """Ghi Ý ĐỊNH hành động TRƯỚC khi tác động. Hành động `work` giữ một lượt gọi model trong cùng giao dịch;
        hết hạn mức thì trả None và không ghi gì. Kèm lịch phục hồi lúc hết khoá: tiến trình chết giữa chừng thì
        tick sau đối soát được, không bỏ quên mục tiêu."""
        now = time.time() if now is None else float(now)
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            if kind == "work":
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
            self._wake(c, goal_id, p.brain_id, "work", float(lease_until) + 1, "phục hồi nếu lượt bị ngắt",
                       keep_earlier=True)
            return {"id": aid, "goal_id": goal_id, "revision": int(revision), "kind": kind, "seq": seq}

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
