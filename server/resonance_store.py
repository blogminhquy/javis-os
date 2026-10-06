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
  supersedes TEXT, created_at REAL NOT NULL);
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
"""


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
                   supersedes: Optional[str] = None) -> dict:
        rec = {"id": _nid("in"), "brain_id": p.brain_id, "session_id": str(session_id or ""),
               "message_id": message_id, "text": str(text or ""),
               "constraints": [str(x).strip() for x in (constraints or ()) if str(x).strip()],
               "supersedes": supersedes, "created_at": time.time()}
        with self._Tx(self) as c:
            c.execute("INSERT INTO intents VALUES(?,?,?,?,?,?,?,?)",
                      (rec["id"], rec["brain_id"], rec["session_id"], rec["message_id"], rec["text"],
                       _j(rec["constraints"]), supersedes, rec["created_at"]))
        return rec

    def _intent(self, c, p: Principal, intent_id: str) -> dict:
        r = c.execute("SELECT * FROM intents WHERE id=?", (intent_id,)).fetchone()
        if r is None or r["brain_id"] != p.brain_id:
            raise ScopeError("bản ghi ý định không tồn tại trong brain này")
        return {"id": r["id"], "text": r["text"], "constraints": json.loads(r["constraints_json"] or "[]")}

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
               intent_id: Optional[str] = None, message_ref: str = "") -> R.GoalRecord:
        now = time.time()
        with self._Tx(self) as c:
            row = self._goal_row(c, p, goal_id)
            if row is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            if int(row["revision"]) != int(expected_revision):
                raise ConflictError(f"mục tiêu đang ở revision {row['revision']}, không phải {expected_revision}")
            user_cons = json.loads(row["user_constraints_json"] or "[]")
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
                       _j({"reason": reason[:500], "diff": diff}), p.by, f"reframe:{rev}", now))
            c.execute("INSERT INTO outbox(goal_id,kind,payload_json,created_at) VALUES(?,?,?,?)",
                      (goal_id, "goal.revised", _j({"revision": rev}), now))
            return self._record(c, c.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone())

    def set_paused(self, p: Principal, goal_id: str, paused: bool) -> None:
        """Chỉ người dùng (owner) đổi pause. Agent không tự bỏ pause của người dùng."""
        if p.kind != "owner":
            raise PermissionError("chỉ người dùng mới tạm dừng hoặc tiếp tục mục tiêu")
        with self._Tx(self) as c:
            if self._goal_row(c, p, goal_id) is None:
                raise ScopeError("mục tiêu không tồn tại trong brain này")
            c.execute("UPDATE goals SET paused=?, updated_at=? WHERE id=?", (1 if paused else 0, time.time(), goal_id))
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
