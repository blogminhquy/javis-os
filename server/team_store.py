"""Kho nhóm chat team (`team.sqlite3`): nhóm, thành viên, sự kiện, bước nội bộ của việc nhóm, sổ lượt, khoá bận theo agent.

Thiết kế: docs/superpowers/specs/2026-10-13-team-chat-design.md mục 5.2. Việc cấp nhóm (hàng đợi, thứ tự, Ưu tiên) nằm ở
làn `team` của bảng `tasks` trong `kanban.sqlite3` (task_store.py), KHÔNG ở đây: CAS hàng đợi và bước nhận việc cần
cùng một giao dịch. Kho này giữ phần còn lại.

- Danh tính thành viên là `agent_key` bền do host cấp (sổ danh tính của resonance_store, `agent_register`), không phải
  slug: agent mới cùng tên không là thành viên và không nhận việc cũ.
- Bước (`team_steps`) là bước NỘI BỘ của một việc nhóm (lập kế hoạch, làm, hỗ trợ, tổng hợp, trả lời), không phải việc
  cấp nhóm. Nhận bước bằng CAS `queued -> running`, mỗi bước chạy tối đa một lần.
- Sổ lượt (`team_turns`) có một dòng cho MỖI lời gọi model: giữ chỗ trước khi dựng engine, ghi mốc gọi engine ngay
  trước lời gọi; trước mốc thì hoàn được, sau mốc thì luôn tính (kể cả lỗi, hết giờ, huỷ, restart).
- Khoá bận (`agent_busy`) đảm bảo một agent chạy tối đa một lượt nhóm cùng lúc trên cả máy (D3), có hạn để tự nhả khi
  tiến trình chết.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Optional

import config as cfgmod

# Trần mặc định ở chế độ Quyền giới hạn (spec 12.3, D7). Toàn quyền (T3) đọc và ghi đè theo nhóm.
DEFAULT_CAPS = {
    "task_turns": 12,          # lượt model mỗi việc
    "task_steps": 8,           # bước mỗi việc
    "help_depth": 2,           # độ sâu nhờ hỗ trợ
    "no_progress": 2,          # lượt không tiến triển liên tiếp của một bước
    "mentions": 3,             # @ mỗi tin
    "daily_turns": 100,        # lượt mỗi nhóm mỗi ngày
    "running_jobs": 1,         # việc chạy cùng lúc mỗi nhóm
    "busy_wait_s": 1800,       # chờ khoá bận trước khi báo chặn
}
TEAM_STATUS = ("active", "paused", "archived")
STEP_KINDS = ("plan", "work", "help", "synthesize", "reply")
TURN_ROLES = ("leader_reply", "member_reply", "plan", "work", "help", "synthesize")
# Kết cục của một lượt trả lời trò chuyện (0.142.0), lưu bền để tải lại trang hay khởi động lại máy chủ không mất dấu:
# queued (đang chờ) -> running (đang trả lời) -> done (xong) | error (lỗi, kèm lý do, có Thử lại).
REPLY_STATUS = ("queued", "running", "done", "error")
REPLY_OPEN = ("queued", "running")
STUCK_QUEUED_S = 600.0   # lượt nằm `queued` quá lâu (việc nền không tạo được) thì cho Thử lại

_SCHEMA = """
CREATE TABLE IF NOT EXISTS teams(
  team_id TEXT PRIMARY KEY, brain_id TEXT NOT NULL, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  session_id TEXT NOT NULL, leader_key TEXT, leader_mode TEXT NOT NULL DEFAULT 'limited',
  status TEXT NOT NULL DEFAULT 'active', caps_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS teams_brain ON teams(brain_id, updated_at);
CREATE TABLE IF NOT EXISTS team_members(
  team_id TEXT NOT NULL, agent_key TEXT NOT NULL, slug_at_join TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT 'member', status TEXT NOT NULL DEFAULT 'active',
  managed_by_team INTEGER NOT NULL DEFAULT 0, joined_at REAL NOT NULL, left_at REAL,
  PRIMARY KEY(team_id, agent_key));
CREATE INDEX IF NOT EXISTS team_members_agent ON team_members(agent_key, status);
CREATE TABLE IF NOT EXISTS team_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, team_id TEXT NOT NULL, kind TEXT NOT NULL, by TEXT NOT NULL DEFAULT '',
  before_json TEXT NOT NULL DEFAULT '{}', after_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS team_events_team ON team_events(team_id, id);
CREATE TABLE IF NOT EXISTS team_steps(
  step_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, team_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL,
  agent_key TEXT NOT NULL, job_revision INTEGER NOT NULL, brief TEXT NOT NULL DEFAULT '',
  input_refs_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'queued', parent_step TEXT,
  result_msg_id INTEGER, applied INTEGER NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, updated_at REAL NOT NULL, UNIQUE(task_id, seq));
CREATE TABLE IF NOT EXISTS team_turns(
  turn_id TEXT PRIMARY KEY, team_id TEXT NOT NULL, task_id TEXT, step_id TEXT, agent_key TEXT NOT NULL,
  role TEXT NOT NULL, engine TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'reserved', engine_at REAL, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL,
  created_at REAL NOT NULL, settled_at REAL);
CREATE INDEX IF NOT EXISTS team_turns_team ON team_turns(team_id, created_at);
CREATE INDEX IF NOT EXISTS team_turns_task ON team_turns(task_id);
CREATE TABLE IF NOT EXISTS agent_busy(
  agent_key TEXT PRIMARY KEY, team_id TEXT NOT NULL, turn_id TEXT NOT NULL, lease_until REAL NOT NULL);
CREATE TABLE IF NOT EXISTS team_reactions(
  session_id TEXT NOT NULL, message_id INTEGER NOT NULL, reactor TEXT NOT NULL, team_id TEXT NOT NULL,
  agent_key TEXT NOT NULL, task_id TEXT, value TEXT, reasons_json TEXT NOT NULL DEFAULT '[]',
  comment TEXT NOT NULL DEFAULT '', content_sha TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL,
  updated_at REAL NOT NULL, PRIMARY KEY(session_id, message_id, reactor));
CREATE INDEX IF NOT EXISTS team_reactions_agent ON team_reactions(team_id, agent_key, updated_at);
CREATE TABLE IF NOT EXISTS team_authority(
  id INTEGER PRIMARY KEY AUTOINCREMENT, team_id TEXT NOT NULL, leader_key TEXT NOT NULL,
  grant_json TEXT NOT NULL DEFAULT '{}', granted_by TEXT NOT NULL DEFAULT '', granted_at REAL NOT NULL,
  revoked_at REAL, revoke_reason TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS team_authority_team ON team_authority(team_id, revoked_at);
CREATE TABLE IF NOT EXISTS team_replies(
  team_id TEXT NOT NULL, message_id INTEGER NOT NULL, agent_key TEXT NOT NULL, seq INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued', reason TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '',
  attempt INTEGER NOT NULL DEFAULT 1, turn_id TEXT, result_msg_id INTEGER, engine TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL,
  PRIMARY KEY(team_id, message_id, agent_key));
CREATE INDEX IF NOT EXISTS team_replies_open ON team_replies(status);
CREATE TABLE IF NOT EXISTS team_reaction_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, message_id INTEGER NOT NULL, reactor TEXT NOT NULL,
  team_id TEXT NOT NULL, value TEXT, reasons_json TEXT NOT NULL DEFAULT '[]', comment TEXT NOT NULL DEFAULT '',
  content_sha TEXT NOT NULL DEFAULT '', nonce TEXT NOT NULL UNIQUE, created_at REAL NOT NULL);
"""

# Sáu reaction (spec mục 14.1): lưu NGUYÊN giá trị, không gộp, không suy ra đánh giá. "none" là bỏ emoji.
REACTIONS = ("like", "love", "haha", "wow", "sad", "angry")
REACTION_EMOJI = {"like": "👍", "love": "❤️", "haha": "😂", "wow": "😮", "sad": "😢", "angry": "😡"}
# Lý do chất lượng (chọn được nhiều): tín hiệu ĐÁNH GIÁ, khác emoji.
REACTION_REASONS = ("on_point", "wrong_facts", "missing", "too_long", "unclear", "off_topic")
COMMENT_MAX = 500


class TeamError(Exception):
    """Thao tác không hợp lệ với trạng thái hiện tại của nhóm (route trả 409 hay 400)."""


class TurnCapReached(TeamError):
    """Giữ chỗ lượt bị từ chối vì chạm trần (`cap` là "daily_turns" hay "task_turns"). Không có dòng nào được ghi."""

    def __init__(self, cap: str):
        super().__init__(cap)
        self.cap = cap


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def new_team_id() -> str:
    return "tm_" + secrets.token_hex(8)


class TeamStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else Path(cfgmod.STATE_DIR) / "team.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conn()) as c:
            c.executescript(_SCHEMA)
            cols = {r[1] for r in c.execute("PRAGMA table_info(team_turns)").fetchall()}
            if "committed_at" not in cols:
                # Mốc ghi bài học của lượt vào bộ nhớ agent (chỉ một lần, chỉ khi đầu ra được chấp nhận).
                c.execute("ALTER TABLE team_turns ADD COLUMN committed_at REAL")
            if "identity_json" not in {r[1] for r in c.execute("PRAGMA table_info(team_members)").fetchall()}:
                # Ảnh chụp nhân dạng (tên, ảnh) của thành viên lúc còn xác nhận được theo agent_key, để tin cũ giữ đúng
                # người viết sau khi trợ lý bị xoá và slug được dùng lại cho trợ lý khác (review 4f6268bd #1).
                c.execute("ALTER TABLE team_members ADD COLUMN identity_json TEXT")
            if "pinned_at" not in {r[1] for r in c.execute("PRAGMA table_info(teams)").fetchall()}:
                # Ghim nhóm lên đầu danh sách (T5); NULL là không ghim.
                c.execute("ALTER TABLE teams ADD COLUMN pinned_at REAL")
            tcols = {r[1] for r in c.execute("PRAGMA table_info(teams)").fetchall()}
            if "created_by" not in tcols:
                # Người tạo nhóm (0.142.0): người thật, lấy từ phiên xác thực của server, không từ client. Javis hiện chỉ
                # có một tài khoản chủ máy nên nhóm cũ nhận đúng chủ đó ("owner"), không giả lập đa người dùng.
                c.execute("ALTER TABLE teams ADD COLUMN created_by TEXT NOT NULL DEFAULT 'owner'")
            if "client_req_id" not in tcols:
                # Mã yêu cầu tạo nhóm của client (0.142.0): bấm Tạo hai lần hay mạng chậm gửi lại thì trả lại nhóm đã tạo.
                c.execute("ALTER TABLE teams ADD COLUMN client_req_id TEXT")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS teams_client_req ON teams(brain_id, client_req_id) "
                      "WHERE client_req_id IS NOT NULL")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    class _Tx:
        """BEGIN IMMEDIATE ... COMMIT; lỗi thì ROLLBACK."""

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

    # ───────────── nhóm ─────────────

    @staticmethod
    def _team(r) -> dict:
        caps = dict(DEFAULT_CAPS)
        caps.update(json.loads(r["caps_json"] or "{}"))
        return {"team_id": r["team_id"], "brain_id": r["brain_id"], "name": r["name"], "description": r["description"],
                "session_id": r["session_id"], "leader_key": r["leader_key"], "leader_mode": r["leader_mode"],
                "status": r["status"], "caps": caps, "created_at": r["created_at"], "updated_at": r["updated_at"],
                "pinned_at": r["pinned_at"], "created_by": r["created_by"] if "created_by" in r.keys() else "owner"}

    def _event(self, c, team_id: str, kind: str, by: str, before: Any = None, after: Any = None) -> None:
        c.execute("INSERT INTO team_events(team_id,kind,by,before_json,after_json,created_at) VALUES(?,?,?,?,?,?)",
                  (team_id, kind, by, _j(before or {}), _j(after or {}), time.time()))

    def create_team(self, brain_id: str, name: str, description: str, session_id: str, by: str = "owner",
                    team_id: Optional[str] = None, members: Optional[list] = None, leader_key: Optional[str] = None,
                    client_req_id: Optional[str] = None) -> dict:
        """`team_id` cho trước khi phiên hội thoại đã tạo với kênh `team:<team_id>` (xem `new_team_id`).

        `members` [(agent_key, slug)] và `leader_key` ghi trong CÙNG giao dịch với nhóm (0.142.0): không còn nhóm nửa
        vời khi lỗi giữa chừng. `client_req_id` trùng (bấm hai lần, mạng chậm gửi lại) thì không tạo gì, trả nhóm cũ."""
        name = str(name or "").strip()
        if not name:
            raise TeamError("thiếu tên nhóm")
        tid = team_id or new_team_id()
        req = str(client_req_id or "").strip()[:80] or None
        now = time.time()
        with self._Tx(self) as c:
            dup = None
            if req:
                dup = c.execute("SELECT team_id FROM teams WHERE brain_id=? AND client_req_id=?", (brain_id, req)).fetchone()
                if dup is not None:
                    tid = dup["team_id"]
            if dup is None:
                c.execute("INSERT INTO teams(team_id,brain_id,name,description,session_id,created_at,updated_at,"
                          "created_by,client_req_id) VALUES(?,?,?,?,?,?,?,?,?)",
                          (tid, brain_id, name[:120], str(description or "")[:2000], session_id, now, now,
                           str(by or "owner")[:80], req))
                self._event(c, tid, "created", by, None, {"name": name})
                for key, slug in dict.fromkeys((str(k), str(s)) for k, s in (members or [])):
                    c.execute("INSERT OR IGNORE INTO team_members(team_id,agent_key,slug_at_join,role,status,joined_at) "
                              "VALUES(?,?,?,?,?,?)", (tid, key, slug, "member", "active", now))
                    self._event(c, tid, "member_added", by, None, {"agent_key": key, "slug": slug})
                if leader_key:
                    if c.execute("SELECT 1 FROM team_members WHERE team_id=? AND agent_key=?",
                                 (tid, leader_key)).fetchone() is None:
                        raise TeamError("trưởng nhóm phải là thành viên đang hoạt động của nhóm")
                    c.execute("UPDATE team_members SET role='leader' WHERE team_id=? AND agent_key=?", (tid, leader_key))
                    c.execute("UPDATE teams SET leader_key=? WHERE team_id=?", (leader_key, tid))
                    self._event(c, tid, "leader_set", by, {"leader_key": None}, {"leader_key": leader_key})
        return self.get(tid)

    def find_by_request(self, brain_id: str, client_req_id: str) -> Optional[dict]:
        req = str(client_req_id or "").strip()[:80]
        if not req:
            return None
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM teams WHERE brain_id=? AND client_req_id=?", (brain_id, req)).fetchone()
            return self._team(r) if r else None

    def open_teams(self) -> list:
        """Mọi nhóm chưa lưu trữ, ở mọi brain (đối soát lúc khởi động)."""
        with closing(self._conn()) as c:
            return [self._team(r) for r in c.execute("SELECT * FROM teams WHERE status != 'archived'").fetchall()]

    def get(self, team_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM teams WHERE team_id=?", (str(team_id or ""),)).fetchone()
            return self._team(r) if r else None

    def list_teams(self, brain_id: str, limit: int = 50, before: Optional[float] = None,
                   include_archived: bool = False) -> list:
        """Nhóm của brain, mới cập nhật trước. Trang đầu (`before` trống) mở bằng các nhóm đã ghim (ghim sau đứng trước);
        phần còn lại (và mọi trang sau, theo con trỏ `updated_at`) chỉ gồm nhóm không ghim, nên không nhóm nào lặp."""
        base = "SELECT * FROM teams WHERE brain_id=?" + ("" if include_archived else " AND status != 'archived'")
        q = base + " AND pinned_at IS NULL"
        args: list = [brain_id]
        if before is not None:
            q += " AND updated_at < ?"
            args.append(float(before))
        q += " ORDER BY updated_at DESC LIMIT ?"
        args.append(max(1, min(int(limit), 200)))
        with closing(self._conn()) as c:
            pinned = [] if before is not None else [self._team(r) for r in c.execute(
                base + " AND pinned_at IS NOT NULL ORDER BY pinned_at DESC", (brain_id,)).fetchall()]
            return pinned + [self._team(r) for r in c.execute(q, args).fetchall()]

    def set_pinned(self, team_id: str, on: bool, by: str = "owner") -> Optional[dict]:
        """Ghim (hay bỏ ghim) nhóm lên đầu danh sách. Không đổi `updated_at`."""
        with self._Tx(self) as c:
            r = c.execute("SELECT pinned_at FROM teams WHERE team_id=?", (team_id,)).fetchone()
            if r is None:
                raise TeamError("không có nhóm này")
            after = time.time() if on else None
            c.execute("UPDATE teams SET pinned_at=? WHERE team_id=?", (after, team_id))
            self._event(c, team_id, "pinned" if on else "unpinned", by, {"pinned_at": r["pinned_at"]}, {"pinned_at": after})
        return self.get(team_id)

    def update(self, team_id: str, by: str = "owner", **fields) -> dict:
        allowed = {"name", "description", "status"}
        bad = set(fields) - allowed
        if bad:
            raise TeamError(f"trường không đổi được: {sorted(bad)}")
        if "status" in fields and fields["status"] not in TEAM_STATUS:
            raise TeamError("trạng thái nhóm không hợp lệ")
        if "name" in fields and not str(fields["name"] or "").strip():
            raise TeamError("thiếu tên nhóm")
        with self._Tx(self) as c:
            r = c.execute("SELECT * FROM teams WHERE team_id=?", (team_id,)).fetchone()
            if r is None:
                raise TeamError("không có nhóm này")
            before = {k: r[k] for k in fields}
            sets = ", ".join(f"{k}=?" for k in fields)
            c.execute(f"UPDATE teams SET {sets}, updated_at=? WHERE team_id=?",
                      (*[str(v) for v in fields.values()], time.time(), team_id))
            self._event(c, team_id, "updated", by, before, fields)
        return self.get(team_id)

    def set_caps(self, team_id: str, caps: dict, by: str = "owner") -> dict:
        """Chủ nhóm đổi trần (spec 12.3). Chỉ nhận khoá có trong DEFAULT_CAPS, giá trị số không âm."""
        bad = set(caps or {}) - set(DEFAULT_CAPS)
        if bad:
            raise TeamError(f"trần không có: {sorted(bad)}")
        clean = {}
        for k, v in (caps or {}).items():
            try:
                num = float(v)
            except (TypeError, ValueError):
                raise TeamError(f"trần {k} phải là số")
            if num < 0:
                raise TeamError(f"trần {k} không được âm")
            clean[k] = num if k == "busy_wait_s" else int(num)
        with self._Tx(self) as c:
            r = c.execute("SELECT caps_json FROM teams WHERE team_id=?", (team_id,)).fetchone()
            if r is None:
                raise TeamError("không có nhóm này")
            before = json.loads(r["caps_json"] or "{}")
            after = dict(before, **clean)
            c.execute("UPDATE teams SET caps_json=?, updated_at=? WHERE team_id=?", (_j(after), time.time(), team_id))
            self._event(c, team_id, "caps_set", by, before, after)
        return self.get(team_id)

    def log_event(self, team_id: str, kind: str, by: str, before: Any = None, after: Any = None) -> None:
        with self._Tx(self) as c:
            self._event(c, team_id, kind, by, before, after)

    def touch(self, team_id: str) -> None:
        with self._Tx(self) as c:
            c.execute("UPDATE teams SET updated_at=? WHERE team_id=?", (time.time(), team_id))

    # ───────────── thành viên và trưởng nhóm ─────────────

    @staticmethod
    def _member(r) -> dict:
        return {"team_id": r["team_id"], "agent_key": r["agent_key"], "slug_at_join": r["slug_at_join"],
                "role": r["role"], "status": r["status"], "managed_by_team": bool(r["managed_by_team"]),
                "joined_at": r["joined_at"], "left_at": r["left_at"],
                "identity": json.loads(r["identity_json"]) if r["identity_json"] else None}

    def set_identity(self, team_id: str, agent_key: str, identity: dict) -> None:
        """Ghi ảnh chụp nhân dạng {slug, name, avatar} của thành viên (mọi trạng thái). Chỉ ghi khi đổi."""
        data = _j(identity)
        with self._Tx(self) as c:
            c.execute("UPDATE team_members SET identity_json=? WHERE team_id=? AND agent_key=? "
                      "AND (identity_json IS NULL OR identity_json != ?)", (data, team_id, agent_key, data))

    def add_member(self, team_id: str, agent_key: str, slug: str, by: str = "owner") -> dict:
        now = time.time()
        with self._Tx(self) as c:
            if c.execute("SELECT 1 FROM teams WHERE team_id=?", (team_id,)).fetchone() is None:
                raise TeamError("không có nhóm này")
            r = c.execute("SELECT * FROM team_members WHERE team_id=? AND agent_key=?", (team_id, agent_key)).fetchone()
            if r is not None and r["status"] == "active":
                return self._member(r)
            if r is None:
                c.execute("INSERT INTO team_members(team_id,agent_key,slug_at_join,role,status,joined_at) "
                          "VALUES(?,?,?,?,?,?)", (team_id, agent_key, slug, "member", "active", now))
            else:
                # Vào lại là thành viên thường: cờ "do nhóm quản lý" không tự sống lại (chủ phải giao lại; review T3).
                c.execute("UPDATE team_members SET status='active', role='member', slug_at_join=?, joined_at=?, "
                          "left_at=NULL, managed_by_team=0 WHERE team_id=? AND agent_key=?",
                          (slug, now, team_id, agent_key))
            c.execute("UPDATE teams SET updated_at=? WHERE team_id=?", (now, team_id))
            self._event(c, team_id, "member_added", by, None, {"agent_key": agent_key, "slug": slug})
            return self._member(c.execute("SELECT * FROM team_members WHERE team_id=? AND agent_key=?",
                                          (team_id, agent_key)).fetchone())

    def _drop_member(self, c, team_id: str, agent_key: str, status: str, by: str, now: float) -> bool:
        r = c.execute("SELECT * FROM team_members WHERE team_id=? AND agent_key=? AND status='active'",
                      (team_id, agent_key)).fetchone()
        if r is None:
            return False
        c.execute("UPDATE team_members SET status=?, role='member', left_at=?, managed_by_team=0 "
                  "WHERE team_id=? AND agent_key=?", (status, now, team_id, agent_key))
        t = c.execute("SELECT leader_key FROM teams WHERE team_id=?", (team_id,)).fetchone()
        if t is not None and t["leader_key"] == agent_key:
            # Không âm thầm mất điều phối (spec 6.3): nhóm thành "chưa có trưởng nhóm", ghi sự kiện, giao diện báo.
            self._revoke_in(c, team_id, by, "leader_removed")
            c.execute("UPDATE teams SET leader_key=NULL, leader_mode='limited', updated_at=? WHERE team_id=?",
                      (now, team_id))
            self._event(c, team_id, "leader_removed", by, {"leader_key": agent_key}, {"leader_key": None})
        self._event(c, team_id, "member_" + status, by, {"agent_key": agent_key}, None)
        return True

    def remove_member(self, team_id: str, agent_key: str, by: str = "owner") -> bool:
        with self._Tx(self) as c:
            return self._drop_member(c, team_id, agent_key, "removed", by, time.time())

    def mark_agent_gone(self, brain_id: str, agent_key: str) -> list:
        """Agent bị xoá khỏi Javis (mã nghỉ): mọi nhóm của brain đánh dấu `agent_gone`. Trả danh sách nhóm bị ảnh hưởng."""
        out = []
        now = time.time()
        with self._Tx(self) as c:
            rows = c.execute("SELECT m.team_id FROM team_members m JOIN teams t ON t.team_id=m.team_id "
                             "WHERE t.brain_id=? AND m.agent_key=? AND m.status='active'",
                             (brain_id, agent_key)).fetchall()
            for r in rows:
                if self._drop_member(c, r["team_id"], agent_key, "agent_gone", "host", now):
                    out.append(r["team_id"])
        return out

    def set_leader(self, team_id: str, agent_key: Optional[str], by: str = "owner") -> dict:
        now = time.time()
        with self._Tx(self) as c:
            t = c.execute("SELECT * FROM teams WHERE team_id=?", (team_id,)).fetchone()
            if t is None:
                raise TeamError("không có nhóm này")
            if agent_key is not None and c.execute(
                    "SELECT 1 FROM team_members WHERE team_id=? AND agent_key=? AND status='active'",
                    (team_id, agent_key)).fetchone() is None:
                raise TeamError("trưởng nhóm phải là thành viên đang hoạt động của nhóm")
            c.execute("UPDATE team_members SET role='member' WHERE team_id=? AND role='leader'", (team_id,))
            if agent_key is not None:
                c.execute("UPDATE team_members SET role='leader' WHERE team_id=? AND agent_key=?", (team_id, agent_key))
            # Đổi trưởng nhóm thì chế độ quyền về giới hạn (Toàn quyền gắn người, không gắn chức danh; spec 13.1, M11):
            # thu hồi dòng Toàn quyền trong CÙNG giao dịch.
            if t["leader_key"] != agent_key:
                self._revoke_in(c, team_id, by, "leader_changed")
            c.execute("UPDATE teams SET leader_key=?, leader_mode='limited', updated_at=? WHERE team_id=?",
                      (agent_key, now, team_id))
            self._event(c, team_id, "leader_set", by, {"leader_key": t["leader_key"]}, {"leader_key": agent_key})
        return self.get(team_id)

    def members(self, team_id: str, include_removed: bool = False) -> list:
        q = "SELECT * FROM team_members WHERE team_id=?"
        if not include_removed:
            q += " AND status='active'"
        with closing(self._conn()) as c:
            return [self._member(r) for r in c.execute(q + " ORDER BY joined_at", (team_id,)).fetchall()]

    def member(self, team_id: str, agent_key: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM team_members WHERE team_id=? AND agent_key=?", (team_id, agent_key)).fetchone()
            return self._member(r) if r else None

    def is_active_member(self, team_id: str, agent_key: str) -> bool:
        m = self.member(team_id, agent_key)
        return bool(m and m["status"] == "active")

    def teams_of_agent(self, agent_key: str) -> list:
        with closing(self._conn()) as c:
            return [r["team_id"] for r in c.execute(
                "SELECT team_id FROM team_members WHERE agent_key=? AND status='active'", (agent_key,)).fetchall()]

    def events(self, team_id: str, limit: int = 200) -> list:
        with closing(self._conn()) as c:
            return [{"id": r["id"], "kind": r["kind"], "by": r["by"], "before": json.loads(r["before_json"]),
                     "after": json.loads(r["after_json"]), "created_at": r["created_at"]}
                    for r in c.execute("SELECT * FROM team_events WHERE team_id=? ORDER BY id DESC LIMIT ?",
                                       (team_id, int(limit))).fetchall()]

    def has_reminder(self, team_id: str, task_id: str, blocked_at: float) -> bool:
        """Đã nhắc lần chặn này (`blocked_reminder` cùng việc, cùng mốc chặn) chưa. Tra thẳng trong kho, không trong đuôi sự
        kiện của nhóm (review tích hợp 0.140.0, cùng lỗi với `cap_record`)."""
        with closing(self._conn()) as c:
            return c.execute("SELECT 1 FROM team_events WHERE team_id=? AND kind='blocked_reminder' "
                             "AND json_extract(after_json, '$.task_id')=? AND json_extract(after_json, '$.blocked_at')=? "
                             "LIMIT 1", (team_id, str(task_id), float(blocked_at))).fetchone() is not None

    def cap_record(self, team_id: str, task_id: str) -> Optional[dict]:
        """Bản ghi `cap_blocked` mới nhất của ĐÚNG việc `task_id` (trần đã chạm, các bước bị từ chối), tra thẳng trong kho
        chứ không trong đuôi sự kiện của cả nhóm: nhóm bận có thể sinh hàng trăm sự kiện khác sau lần chặn (review
        b93c46bd #3). Không có thì None."""
        with closing(self._conn()) as c:
            r = c.execute("SELECT after_json FROM team_events WHERE team_id=? AND kind='cap_blocked' "
                          "AND json_extract(after_json, '$.task_id')=? ORDER BY id DESC LIMIT 1",
                          (team_id, str(task_id))).fetchone()
        return json.loads(r["after_json"]) if r else None

    # ───────────── bước nội bộ của việc nhóm ─────────────

    @staticmethod
    def _step(r) -> dict:
        return {"step_id": r["step_id"], "task_id": r["task_id"], "team_id": r["team_id"], "seq": r["seq"],
                "kind": r["kind"], "agent_key": r["agent_key"], "job_revision": r["job_revision"], "brief": r["brief"],
                "input_refs": json.loads(r["input_refs_json"] or "[]"), "status": r["status"],
                "parent_step": r["parent_step"], "result_msg_id": r["result_msg_id"], "applied": bool(r["applied"]),
                "note": r["note"], "created_at": r["created_at"], "updated_at": r["updated_at"]}

    def add_step(self, task_id: str, team_id: str, kind: str, agent_key: str, job_revision: int, brief: str,
                 input_refs: list, parent_step: Optional[str] = None) -> dict:
        if kind not in STEP_KINDS:
            raise TeamError("loại bước không hợp lệ")
        now = time.time()
        with self._Tx(self) as c:
            seq = int(c.execute("SELECT COALESCE(MAX(seq),0)+1 FROM team_steps WHERE task_id=?",
                                (task_id,)).fetchone()[0])
            sid = "st_" + secrets.token_hex(8)
            c.execute("INSERT INTO team_steps(step_id,task_id,team_id,seq,kind,agent_key,job_revision,brief,"
                      "input_refs_json,parent_step,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (sid, task_id, team_id, seq, kind, agent_key, int(job_revision), str(brief or "")[:8000],
                       _j(list(input_refs or [])), parent_step, now, now))
            return self._step(c.execute("SELECT * FROM team_steps WHERE step_id=?", (sid,)).fetchone())

    def steps(self, task_id: str) -> list:
        with closing(self._conn()) as c:
            return [self._step(r) for r in c.execute("SELECT * FROM team_steps WHERE task_id=? ORDER BY seq",
                                                     (task_id,)).fetchall()]

    def step(self, step_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM team_steps WHERE step_id=?", (step_id,)).fetchone()
            return self._step(r) if r else None

    def next_queued_step(self, task_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM team_steps WHERE task_id=? AND status='queued' ORDER BY seq LIMIT 1",
                          (task_id,)).fetchone()
            return self._step(r) if r else None

    def claim_step(self, step_id: str) -> bool:
        with self._Tx(self) as c:
            cur = c.execute("UPDATE team_steps SET status='running', updated_at=? WHERE step_id=? AND status='queued'",
                            (time.time(), step_id))
            return cur.rowcount == 1

    def finish_step(self, step_id: str, status: str, result_msg_id: Optional[int] = None, applied: bool = False,
                    note: str = "") -> None:
        with self._Tx(self) as c:
            c.execute("UPDATE team_steps SET status=?, result_msg_id=?, applied=?, note=?, updated_at=? "
                      "WHERE step_id=?", (status, result_msg_id, 1 if applied else 0, str(note or "")[:500],
                                          time.time(), step_id))

    def requeue_step(self, step_id: str) -> None:
        """Bước chưa tới mốc gọi engine (restart, khoá bận): về hàng chờ, không mất chỗ."""
        with self._Tx(self) as c:
            c.execute("UPDATE team_steps SET status='queued', updated_at=? WHERE step_id=? AND status='running'",
                      (time.time(), step_id))

    def cancel_open_steps(self, task_id: str, note: str) -> int:
        with self._Tx(self) as c:
            return c.execute("UPDATE team_steps SET status='cancelled', note=?, updated_at=? "
                             "WHERE task_id=? AND status IN ('queued','waiting')", (note, time.time(), task_id)).rowcount

    def set_step_status(self, step_id: str, status: str, note: str = "") -> None:
        with self._Tx(self) as c:
            c.execute("UPDATE team_steps SET status=?, note=?, updated_at=? WHERE step_id=?",
                      (status, note, time.time(), step_id))

    # ───────────── sổ lượt ─────────────

    def reserve_turn(self, team_id: str, task_id: Optional[str], step_id: Optional[str], agent_key: str,
                     role: str, *, daily_cap: Optional[int] = None, day_start: float = 0.0,
                     task_cap: Optional[int] = None) -> str:
        """Giữ chỗ một lượt. Có trần thì đếm và ghi trong CÙNG một giao dịch BEGIN IMMEDIATE: hai lượt giữ chỗ đồng thời
        (hai luồng, hai tiến trình) không cùng lọt qua chỗ trống cuối cùng. Chạm trần thì ném `TurnCapReached`."""
        if role not in TURN_ROLES:
            raise TeamError("vai lượt không hợp lệ")
        tid = "tu_" + secrets.token_hex(8)
        with self._Tx(self) as c:
            if daily_cap is not None and int(c.execute(
                    "SELECT COUNT(*) FROM team_turns WHERE team_id=? AND status != 'refunded' AND created_at >= ?",
                    (team_id, float(day_start))).fetchone()[0]) >= int(daily_cap):
                raise TurnCapReached("daily_turns")
            if task_id and task_cap is not None and int(c.execute(
                    "SELECT COUNT(*) FROM team_turns WHERE task_id=? AND status != 'refunded'",
                    (task_id,)).fetchone()[0]) >= int(task_cap):
                raise TurnCapReached("task_turns")
            c.execute("INSERT INTO team_turns(turn_id,team_id,task_id,step_id,agent_key,role,created_at) "
                      "VALUES(?,?,?,?,?,?,?)", (tid, team_id, task_id, step_id, agent_key, role, time.time()))
        return tid

    def mark_engine(self, turn_id: str, engine: str, model: str) -> None:
        with self._Tx(self) as c:
            c.execute("UPDATE team_turns SET status='running', engine=?, model=?, engine_at=? "
                      "WHERE turn_id=? AND status='reserved'", (engine, model, time.time(), turn_id))

    def settle_turn(self, turn_id: str, status: str, tokens_in: Optional[int] = None, tokens_out: Optional[int] = None,
                    cost_usd: Optional[float] = None) -> None:
        if status not in ("ok", "error", "interrupted"):
            raise TeamError("kết cục lượt không hợp lệ")
        with self._Tx(self) as c:
            c.execute("UPDATE team_turns SET status=?, tokens_in=?, tokens_out=?, cost_usd=?, settled_at=? "
                      "WHERE turn_id=? AND status IN ('running','reserved')",
                      (status, tokens_in, tokens_out, cost_usd, time.time(), turn_id))

    def refund_turn(self, turn_id: str) -> None:
        """Lượt chưa tới mốc gọi engine: hoàn, không tính. Đã qua mốc thì không hoàn được."""
        with self._Tx(self) as c:
            r = c.execute("SELECT status, engine_at FROM team_turns WHERE turn_id=?", (turn_id,)).fetchone()
            if r is None:
                raise TeamError("không có lượt này")
            if r["engine_at"] is not None:
                raise TeamError("lượt đã gọi engine, không hoàn được")
            c.execute("UPDATE team_turns SET status='refunded', settled_at=? WHERE turn_id=?", (time.time(), turn_id))

    def claim_commit(self, turn_id: str) -> bool:
        """Giành quyền ghi bài học của lượt `turn_id` vào bộ nhớ agent: True đúng một lần, cho lượt đã chốt `ok`.
        Lượt bị xử lý lặp (gọi lại, phục hồi) không ghi lần hai."""
        with self._Tx(self) as c:
            return c.execute("UPDATE team_turns SET committed_at=? WHERE turn_id=? AND status='ok' "
                             "AND committed_at IS NULL", (time.time(), turn_id)).rowcount == 1

    def turn(self, turn_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM team_turns WHERE turn_id=?", (turn_id,)).fetchone()
            return dict(r) if r else None

    def count_task_turns(self, task_id: str) -> int:
        with closing(self._conn()) as c:
            return int(c.execute("SELECT COUNT(*) FROM team_turns WHERE task_id=? AND status != 'refunded'",
                                 (task_id,)).fetchone()[0])

    def count_team_turns(self, team_id: str, since: float) -> int:
        with closing(self._conn()) as c:
            return int(c.execute("SELECT COUNT(*) FROM team_turns WHERE team_id=? AND status != 'refunded' "
                                 "AND created_at >= ?", (team_id, float(since))).fetchone()[0])

    def turns(self, team_id: str, since: float = 0, limit: int = 500) -> list:
        with closing(self._conn()) as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM team_turns WHERE team_id=? AND created_at >= ? ORDER BY created_at DESC LIMIT ?",
                (team_id, float(since), int(limit))).fetchall()]

    def open_turns(self) -> list:
        """Lượt còn `reserved` hay `running` (dùng khi khởi động lại để chốt `interrupted` hay hoàn)."""
        with closing(self._conn()) as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM team_turns WHERE status IN ('reserved','running')").fetchall()]

    # ───────────── Toàn quyền (T3, spec mục 13) ─────────────

    @staticmethod
    def _authority(r) -> dict:
        return {"id": int(r["id"]), "team_id": r["team_id"], "leader_key": r["leader_key"],
                "grant": json.loads(r["grant_json"] or "{}"), "granted_by": r["granted_by"],
                "granted_at": r["granted_at"], "revoked_at": r["revoked_at"], "revoke_reason": r["revoke_reason"]}

    @staticmethod
    def _active_authority_row(c, team_id: str):
        return c.execute("SELECT * FROM team_authority WHERE team_id=? AND revoked_at IS NULL ORDER BY id DESC LIMIT 1",
                         (team_id,)).fetchone()

    def grant_authority(self, team_id: str, grant: dict, by: str = "owner") -> dict:
        """Chủ bật (hay sửa) Toàn quyền cho trưởng nhóm HIỆN TẠI. Dòng cũ còn hiệu lực bị thu hồi trong cùng giao dịch
        (lý do `regranted`), nên mỗi nhóm có tối đa một dòng hiệu lực. Không có trưởng nhóm thì không bật được."""
        now = time.time()
        with self._Tx(self) as c:
            t = c.execute("SELECT leader_key, status FROM teams WHERE team_id=?", (team_id,)).fetchone()
            if t is None:
                raise TeamError("không có nhóm này")
            if not t["leader_key"]:
                raise TeamError("nhóm chưa có trưởng nhóm, không bật được Toàn quyền")
            old = self._active_authority_row(c, team_id)
            if old is not None:
                c.execute("UPDATE team_authority SET revoked_at=?, revoke_reason='regranted' WHERE id=?", (now, old["id"]))
            cur = c.execute("INSERT INTO team_authority(team_id,leader_key,grant_json,granted_by,granted_at) "
                            "VALUES(?,?,?,?,?)", (team_id, t["leader_key"], _j(grant), by, now))
            c.execute("UPDATE teams SET leader_mode='full', updated_at=? WHERE team_id=?", (now, team_id))
            self._event(c, team_id, "authority_granted", by, None, {"leader_key": t["leader_key"], "grant": grant})
            return self._authority(c.execute("SELECT * FROM team_authority WHERE id=?", (cur.lastrowid,)).fetchone())

    def revoke_authority(self, team_id: str, by: str = "owner", reason: str = "") -> bool:
        """Thu hồi Toàn quyền: ghi `revoked_at`. Trả False nếu không có dòng hiệu lực."""
        with self._Tx(self) as c:
            return self._revoke_in(c, team_id, by, reason or "owner")

    def _revoke_in(self, c, team_id: str, by: str, reason: str) -> bool:
        old = self._active_authority_row(c, team_id)
        if old is None:
            return False
        c.execute("UPDATE team_authority SET revoked_at=?, revoke_reason=? WHERE id=?", (time.time(), reason, old["id"]))
        c.execute("UPDATE teams SET leader_mode='limited' WHERE team_id=?", (team_id,))
        self._event(c, team_id, "authority_revoked", by, {"leader_key": old["leader_key"]}, {"reason": reason})
        return True

    def active_authority(self, team_id: str) -> Optional[dict]:
        """Dòng Toàn quyền còn hiệu lực VÀ còn đúng trưởng nhóm hiện tại; None nếu nhóm ở Quyền giới hạn."""
        with closing(self._conn()) as c:
            r = self._active_authority_row(c, team_id)
            if r is None:
                return None
            t = c.execute("SELECT leader_key FROM teams WHERE team_id=?", (team_id,)).fetchone()
            if t is None or t["leader_key"] != r["leader_key"]:
                return None
            return self._authority(r)

    def update_authority_caps(self, authority_id: int, caps: dict, by: str, ceilings: Optional[dict] = None) -> bool:
        """Trưởng nhóm đổi trần trong trần trần (người gọi đã kiểm). CAS theo dòng còn hiệu lực: dòng đã thu hồi thì
        không đổi gì, trả False. `ceilings` chỉ chủ dùng (nút "Cho thêm lượt" nâng cả trần tối đa khi cần)."""
        with self._Tx(self) as c:
            r = c.execute("SELECT * FROM team_authority WHERE id=? AND revoked_at IS NULL", (int(authority_id),)).fetchone()
            if r is None:
                return False
            g = json.loads(r["grant_json"] or "{}")
            before = dict(g.get("caps") or {})
            g["caps"] = dict(before, **caps)
            if ceilings:
                g["ceilings"] = dict(g.get("ceilings") or {}, **ceilings)
            c.execute("UPDATE team_authority SET grant_json=? WHERE id=?", (_j(g), int(authority_id)))
            self._event(c, r["team_id"], "caps_changed", by, before, g["caps"])
            return True

    def set_managed(self, team_id: str, agent_key: str, on: bool, by: str = "owner") -> None:
        """Đánh dấu agent do nhóm này quản lý (spec 13.3). Mỗi agent tối đa một nhóm quản lý."""
        with self._Tx(self) as c:
            m = c.execute("SELECT * FROM team_members WHERE team_id=? AND agent_key=? AND status='active'",
                          (team_id, agent_key)).fetchone()
            if m is None:
                raise TeamError("không phải thành viên đang hoạt động")
            if on:
                other = c.execute("SELECT team_id FROM team_members WHERE agent_key=? AND managed_by_team=1 "
                                  "AND status='active' AND team_id != ?", (agent_key, team_id)).fetchone()
                if other is not None:
                    raise TeamError("agent này đã do một nhóm khác quản lý")
            c.execute("UPDATE team_members SET managed_by_team=? WHERE team_id=? AND agent_key=?",
                      (1 if on else 0, team_id, agent_key))
            self._event(c, team_id, "managed_set" if on else "managed_unset", by, None, {"agent_key": agent_key})

    def teams_with_member(self, agent_key: str) -> list:
        """Nhóm (id, tên) mà agent đang là thành viên (để báo nhóm bị ảnh hưởng khi sửa cấu hình chung)."""
        with closing(self._conn()) as c:
            return [dict(r) for r in c.execute(
                "SELECT t.team_id, t.name FROM team_members m JOIN teams t ON t.team_id=m.team_id "
                "WHERE m.agent_key=? AND m.status='active'", (agent_key,)).fetchall()]

    # ───────────── reaction (T2, spec mục 14) ─────────────

    @staticmethod
    def _reaction(r) -> dict:
        return {"session_id": r["session_id"], "message_id": int(r["message_id"]), "reactor": r["reactor"],
                "team_id": r["team_id"], "agent_key": r["agent_key"], "task_id": r["task_id"], "value": r["value"],
                "reasons": json.loads(r["reasons_json"] or "[]"), "comment": r["comment"],
                "content_sha": r["content_sha"], "created_at": r["created_at"], "updated_at": r["updated_at"]}

    def set_reaction(self, *, team_id: str, session_id: str, message_id: int, agent_key: str, task_id: Optional[str],
                     content_sha: str, value: Optional[str], reasons: Optional[list] = None, comment: str = "",
                     nonce: str, reactor: str = "owner") -> Optional[dict]:
        """Đặt trọn trạng thái phản hồi của `reactor` trên một tin: emoji (hay "none"), lý do, góp ý. Trả trạng thái
        hiện tại (None khi đã bỏ hết). `nonce` trùng thì không đổi gì (gửi lại sau rớt mạng). Mọi lần đổi ghi nối tiếp
        vào `team_reaction_log`."""
        val = None if value in (None, "", "none") else str(value)
        if val is not None and val not in REACTIONS:
            raise TeamError("reaction không hợp lệ")
        reasons = list(dict.fromkeys(str(x) for x in (reasons or [])))
        if any(x not in REACTION_REASONS for x in reasons):
            raise TeamError("lý do không hợp lệ")
        comment = str(comment or "").strip()
        if len(comment) > COMMENT_MAX:
            raise TeamError(f"góp ý tối đa {COMMENT_MAX} ký tự")
        nonce = str(nonce or "").strip()
        if not nonce or len(nonce) > 100:
            raise TeamError("nonce không hợp lệ")
        now = time.time()
        with self._Tx(self) as c:
            seen = c.execute("SELECT session_id, message_id, reactor FROM team_reaction_log WHERE nonce=?",
                             (nonce,)).fetchone()
            if seen is not None and (seen["session_id"], int(seen["message_id"]), seen["reactor"]) != (
                    session_id, int(message_id), reactor):
                # Nonce của lần gửi khác: không được trả 200 "đã lưu" cho một tin không hề đổi.
                raise TeamError("nonce đã dùng cho một tin khác")
            if seen is None:
                c.execute("INSERT INTO team_reaction_log(session_id,message_id,reactor,team_id,value,reasons_json,"
                          "comment,content_sha,nonce,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                          (session_id, int(message_id), reactor, team_id, val, _j(reasons), comment, content_sha,
                           nonce, now))
                if val is None and not reasons and not comment:
                    c.execute("DELETE FROM team_reactions WHERE session_id=? AND message_id=? AND reactor=?",
                              (session_id, int(message_id), reactor))
                else:
                    c.execute(
                        "INSERT INTO team_reactions(session_id,message_id,reactor,team_id,agent_key,task_id,value,"
                        "reasons_json,comment,content_sha,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(session_id,message_id,reactor) DO UPDATE SET value=excluded.value, "
                        "reasons_json=excluded.reasons_json, comment=excluded.comment, "
                        "content_sha=excluded.content_sha, updated_at=excluded.updated_at",
                        (session_id, int(message_id), reactor, team_id, agent_key, task_id, val, _j(reasons), comment,
                         content_sha, now, now))
            r = c.execute("SELECT * FROM team_reactions WHERE session_id=? AND message_id=? AND reactor=?",
                          (session_id, int(message_id), reactor)).fetchone()
            return self._reaction(r) if r else None

    def reaction_of(self, session_id: str, message_id: int, reactor: str = "owner") -> Optional[dict]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM team_reactions WHERE session_id=? AND message_id=? AND reactor=?",
                          (session_id, int(message_id), reactor)).fetchone()
            return self._reaction(r) if r else None

    def reactions_for(self, session_id: str, message_ids: list, reactor: str = "owner") -> dict:
        """{message_id: trạng thái} cho một trang tin."""
        ids = [int(x) for x in message_ids or []]
        if not ids:
            return {}
        with closing(self._conn()) as c:
            rows = c.execute(f"SELECT * FROM team_reactions WHERE session_id=? AND reactor=? AND message_id IN "
                             f"({','.join('?' * len(ids))})", [session_id, reactor] + ids).fetchall()
            return {int(r["message_id"]): self._reaction(r) for r in rows}

    def reaction_log(self, session_id: str, message_id: int) -> list:
        with closing(self._conn()) as c:
            return [dict(r) for r in c.execute("SELECT * FROM team_reaction_log WHERE session_id=? AND message_id=? "
                                               "ORDER BY id", (session_id, int(message_id))).fetchall()]

    def recent_feedback(self, team_id: str, agent_key: str, since: float, limit: int = 5) -> list:
        """Phản hồi còn hiệu lực trên tin của `agent_key` trong ĐÚNG nhóm `team_id`, mới nhất trước (spec 14.4 mục 3)."""
        with closing(self._conn()) as c:
            return [self._reaction(r) for r in c.execute(
                "SELECT * FROM team_reactions WHERE team_id=? AND agent_key=? AND updated_at >= ? "
                "ORDER BY updated_at DESC, message_id DESC LIMIT ?",
                (team_id, agent_key, float(since), int(limit))).fetchall()]

    def _set_reaction_time(self, session_id: str, message_id: int, ts: float) -> None:
        """Chỉ cho test: đặt lùi mốc cập nhật của một phản hồi."""
        with self._Tx(self) as c:
            c.execute("UPDATE team_reactions SET updated_at=? WHERE session_id=? AND message_id=?",
                      (float(ts), session_id, int(message_id)))

    # ───────────── khoá bận theo agent (D3) ─────────────

    def acquire_busy(self, agent_key: str, team_id: str, turn_id: str, lease_s: float = 300,
                     now: Optional[float] = None) -> bool:
        t = time.time() if now is None else float(now)
        with self._Tx(self) as c:
            r = c.execute("SELECT * FROM agent_busy WHERE agent_key=?", (agent_key,)).fetchone()
            if r is not None and r["turn_id"] != turn_id and float(r["lease_until"]) > t:
                return False
            c.execute("INSERT INTO agent_busy(agent_key,team_id,turn_id,lease_until) VALUES(?,?,?,?) "
                      "ON CONFLICT(agent_key) DO UPDATE SET team_id=excluded.team_id, turn_id=excluded.turn_id, "
                      "lease_until=excluded.lease_until", (agent_key, team_id, turn_id, t + float(lease_s)))
            return True

    def release_busy(self, agent_key: str, turn_id: str) -> None:
        with self._Tx(self) as c:
            c.execute("DELETE FROM agent_busy WHERE agent_key=? AND turn_id=?", (agent_key, turn_id))

    def busy_of(self, agent_key: str, now: Optional[float] = None) -> Optional[dict]:
        t = time.time() if now is None else float(now)
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM agent_busy WHERE agent_key=? AND lease_until > ?", (agent_key, t)).fetchone()
            return dict(r) if r else None

    # ───────────── kết cục lượt trả lời trò chuyện (0.142.0) ─────────────

    def queue_replies(self, team_id: str, message_id: int, agent_keys: list) -> list:
        """Ghi các lượt trả lời của một tin là `queued`, theo thứ tự @. Đã có thì giữ nguyên (gửi lại không nhân đôi)."""
        now = time.time()
        with self._Tx(self) as c:
            for i, key in enumerate(agent_keys):
                c.execute("INSERT OR IGNORE INTO team_replies(team_id,message_id,agent_key,seq,status,created_at,"
                          "updated_at) VALUES(?,?,?,?,'queued',?,?)", (team_id, int(message_id), key, i, now, now))
        return self.replies_of(team_id, message_id)

    def replies_of(self, team_id: str, message_id: int) -> list:
        with closing(self._conn()) as c:
            rows = c.execute("SELECT * FROM team_replies WHERE team_id=? AND message_id=? ORDER BY seq",
                             (team_id, int(message_id))).fetchall()
        return [dict(r) for r in rows]

    def reply(self, team_id: str, message_id: int, agent_key: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM team_replies WHERE team_id=? AND message_id=? AND agent_key=?",
                          (team_id, int(message_id), agent_key)).fetchone()
        return dict(r) if r else None

    def replies_for(self, team_id: str, message_ids: list) -> dict:
        """{message_id: [lượt trả lời theo thứ tự]} cho một trang tin."""
        ids = [int(i) for i in message_ids or []]
        out: dict = {}
        if not ids:
            return out
        with closing(self._conn()) as c:
            q = ",".join("?" * len(ids))
            for r in c.execute(f"SELECT * FROM team_replies WHERE team_id=? AND message_id IN ({q}) ORDER BY seq",
                               [team_id] + ids).fetchall():
                out.setdefault(int(r["message_id"]), []).append(dict(r))
        return out

    def claim_reply(self, team_id: str, message_id: int, agent_key: str) -> Optional[int]:
        """CAS queued -> running: mỗi lượt trả lời chạy tối đa một lần cho mỗi lần thử. Trả số lần thử (`attempt`) đã
        nhận, None khi không nhận được. Người gọi đưa lại số này khi ghi kết cục."""
        with self._Tx(self) as c:
            r = c.execute("SELECT attempt FROM team_replies WHERE team_id=? AND message_id=? AND agent_key=? "
                          "AND status='queued'", (team_id, int(message_id), agent_key)).fetchone()
            if r is None:
                return None
            c.execute("UPDATE team_replies SET status='running', reason='', detail='', updated_at=? "
                      "WHERE team_id=? AND message_id=? AND agent_key=? AND status='queued'",
                      (time.time(), team_id, int(message_id), agent_key))
        return int(r["attempt"])

    def settle_reply(self, team_id: str, message_id: int, agent_key: str, status: str, *, attempt: int,
                     reason: str = "", detail: str = "", turn_id: Optional[str] = None,
                     result_msg_id: Optional[int] = None, engine: str = "", model: str = "") -> bool:
        """Ghi kết cục của ĐÚNG lần thử `attempt` khi lượt còn mở (review 0.142.0, #3): một lượt cũ về muộn (đã bị coi là
        dở lúc khởi động lại, rồi chủ bấm Thử lại) không ghi đè kết cục của lần thử mới. Trả True khi đã ghi."""
        if status not in REPLY_STATUS:
            raise ValueError(status)
        with self._Tx(self) as c:
            n = c.execute("UPDATE team_replies SET status=?, reason=?, detail=?, turn_id=COALESCE(?,turn_id), "
                      "result_msg_id=COALESCE(?,result_msg_id), engine=CASE WHEN ?='' THEN engine ELSE ? END, "
                      "model=CASE WHEN ?='' THEN model ELSE ? END, updated_at=? "
                      "WHERE team_id=? AND message_id=? AND agent_key=? AND attempt=? AND status IN ('queued','running')",
                      (status, str(reason or "")[:60], str(detail or "")[:500], turn_id, result_msg_id, engine,
                       engine, model, model, time.time(), team_id, int(message_id), agent_key, int(attempt))).rowcount
        return n == 1

    def retry_reply(self, team_id: str, message_id: int, agent_key: str, stuck_after_s: float = STUCK_QUEUED_S
                    ) -> Optional[dict]:
        """Thử lại một lượt lỗi: CAS error -> queued, tăng `attempt`. Bấm hai lần, hay bấm khi lượt đang chạy hoặc đã
        xong, thì không làm gì (None): không có lượt thứ hai, không có kết quả trùng. Lượt nằm `queued` quá lâu (việc
        nền không tạo được) cũng thử lại được; lần thử cũ, nếu có lúc chạy, không ghi đè được kết cục mới (attempt)."""
        now = time.time()
        with self._Tx(self) as c:
            n = c.execute("UPDATE team_replies SET status='queued', attempt=attempt+1, reason='', detail='', "
                          "updated_at=? WHERE team_id=? AND message_id=? AND agent_key=? AND (status='error' OR "
                          "(status='queued' AND updated_at<?))",
                          (now, team_id, int(message_id), agent_key, now - float(stuck_after_s))).rowcount
        return self.reply(team_id, message_id, agent_key) if n == 1 else None

    def interrupt_open_replies(self, before: Optional[float] = None) -> list:
        """Sau khi khởi động lại: lượt trả lời còn `queued`/`running` không ai chạy nữa. Đánh `error` lý do `restart`
        (có Thử lại) thay vì để quay mãi hay tự chạy lại ngoài ý chủ. Trả các dòng đã đổi."""
        with self._Tx(self) as c:
            # `before`: chỉ lượt của tiến trình TRƯỚC (ghi trước lúc tiến trình này khởi động). Lượt vừa gửi trong tiến
            # trình này, trước nhịp phục hồi đầu tiên, đang chạy thật, không được đánh lỗi (review 0.142.0, #3).
            cut = float(before) if before is not None else time.time() + 1
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM team_replies WHERE status IN ('queued','running') AND updated_at<?", (cut,)).fetchall()]
            c.execute("UPDATE team_replies SET status='error', reason='restart', updated_at=? "
                      "WHERE status IN ('queued','running') AND updated_at<?", (time.time(), cut))
        return rows

    def teams_of_agent(self, agent_key: str) -> list:
        """Mọi nhóm (chưa lưu trữ) mà `agent_key` từng là thành viên, kể cả đã rời: việc cũ của họ vẫn hiện ở tab Công
        việc (0.142.0)."""
        with closing(self._conn()) as c:
            rows = c.execute("SELECT t.* FROM teams t JOIN team_members m ON m.team_id=t.team_id "
                             "WHERE m.agent_key=? AND t.status != 'archived' ORDER BY t.updated_at DESC",
                             (str(agent_key or ""),)).fetchall()
        return [self._team(r) for r in rows]

