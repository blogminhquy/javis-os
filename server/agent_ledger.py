"""Sổ lượt chung theo agent và vòng đời lý do thức theo agent (T2, 0.154.0).

Thiết kế: docs/superpowers/specs/2026-10-15-team-adaptive-design.md mục 3.1-3.4 và 9.1. Bảng nằm trong
`resonance.sqlite3` (tạo ở `resonance_store.GoalStore`), module này chỉ có thao tác:

- `CallLedger`: giữ chỗ (kiểm trần và ghi trong CÙNG một giao dịch BEGIN IMMEDIATE), mốc gọi engine, chốt, hoàn, đối
  soát. Chỉ mục duy nhất từng phần `UNIQUE(reason_ref) WHERE status IN ('reserved','running','ok')`: một lý do có tối đa
  một lượt đang hay đã chạy thành công; lượt `refunded`/`interrupted`/`error` không giữ khoá nên thử lại được (attempt + 1).
- `TeamCeiling`: phần phụ thuộc `ceiling` của `TeamRunner`. Mỗi lượt nhóm giữ chỗ một dòng `counted = 1`,
  `mirror_ref = team_turn:<id>` ngay sau khi giữ chỗ `team_turns`, TRƯỚC khoá bận và engine; mọi lần hoàn hay chốt của
  lượt nhóm phản chiếu sang đây. Đối soát lúc khởi động và theo nhịp.
- `WakeReasons`: lý do thức theo agent x ngữ cảnh (pending/claimed/served/superseded/failed), nguồn ở
  `agent_wake_sources`. T2 chỉ TẠO lý do (bộ chiếu phản hồi); T3 mới phục vụ chúng. API đã đủ vòng đời và có test.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from typing import Any, Callable, Iterable, Optional

import resonance_store as RS

CALL_STATUSES = ("reserved", "running", "ok", "error", "refunded", "interrupted")
LIVE_STATUSES = ("reserved", "running", "ok")
OPEN_STATUSES = ("reserved", "running")
PURPOSES = ("reply", "step", "judge_batch", "review", "proactive", "scan", "reaction_review", "goal", "improve_probe",
            "improve_propose", "improve_evaluate", "improve_compose")
STALE_RESERVED_S = 600.0          # một lượt tối đa 10 phút (thiết kế 3.4, 9.1), chỉ cho dòng `mirror_ref = ''`
# Cửa sổ ân hạn của đối soát (thiết kế 9.1, sửa sau review T1 vòng 2): dòng sổ và lượt nhóm mới hơn mốc này bị bỏ qua, để
# một nhịp đối soát không bắt gặp lượt nhóm đang ở giữa hai bước giữ chỗ của hai kho.
RECONCILE_GRACE_S = 120.0
REASON_CODES = ("reaction_review", "related_review", "proactive_due", "scan_due", "wait_unblocked")
REASON_STATUSES = ("pending", "claimed", "served", "superseded", "failed")
MAX_ATTEMPTS = 3                  # quá 3 lần thử thì `failed` (hiển thị, chủ bấm thử lại)
# Mục đích của lượt nhóm theo vai (sổ chung). Lượt nhóm là nghĩa vụ (trả lời tin nhóm, bước việc nhóm).
TEAM_PURPOSE = {"leader_reply": "reply", "member_reply": "reply", "plan": "step", "work": "step", "help": "step",
                "synthesize": "step", "member_volunteer": "reply"}
# T3 phần J (0.156.0): lượt tự lên tiếng (`member_volunteer`, không ai gọi) là lượt TỰ PHÁT, chỉ dùng tới 80% trần chung.
SPONTANEOUS_ROLES = ("member_volunteer",)


class ReasonBusy(Exception):
    """Lý do đã có một lượt đang chạy hay đã chạy thành công (chỉ mục duy nhất từng phần chặn lượt thứ hai)."""


def _now(now: Optional[float]) -> float:
    return time.time() if now is None else float(now)


class CallLedger:
    """Sổ `agent_calls` trên kho của một `GoalStore`. Mọi thao tác ghi đi qua `GoalStore._Tx` (BEGIN IMMEDIATE)."""

    def __init__(self, store: "RS.GoalStore"):
        self.store = store

    def _tx(self):
        return self.store._Tx(self.store)

    # ───────────── giữ chỗ, mốc engine, chốt, hoàn ─────────────

    def reserve(self, *, purpose: str, reason_ref: str, agent_key: str = "", brain_id: str = "", context_ref: str = "",
                obligation: bool = False, counted: bool = True, mirror_ref: str = "", attempt: Optional[int] = None,
                now: Optional[float] = None, c=None) -> Optional[int]:
        """Giữ chỗ MỘT lượt TRƯỚC khi gọi engine. Trả id dòng, hoặc None khi trần chung đầy (không ghi gì).

        Kiểm trần và ghi nằm trong CÙNG giao dịch BEGIN IMMEDIATE (SQLite tuần tự hoá mọi giao dịch ghi, kể cả từ tiến
        trình khác), nên nhiều lượt đồng thời không cùng lọt qua chỗ trống cuối. `obligation=False` chỉ dùng tới
        floor(trần * 0.8). Lý do đang có lượt sống thì ném `ReasonBusy`. `c`: giao dịch có sẵn của người gọi."""
        if purpose not in PURPOSES:
            raise ValueError(f"purpose không hợp lệ: {purpose}")
        ref = str(reason_ref or "").strip()
        if not ref:
            raise ValueError("thiếu reason_ref")
        if c is None:
            with self._tx() as cc:
                return self.reserve(purpose=purpose, reason_ref=ref, agent_key=agent_key, brain_id=brain_id,
                                    context_ref=context_ref, obligation=obligation, counted=counted,
                                    mirror_ref=mirror_ref, attempt=attempt, now=now, c=cc)
        if counted and not RS._under_ceiling(c, 1, obligation=bool(obligation)):
            return None
        if c.execute("SELECT 1 FROM agent_calls WHERE reason_ref=? AND status IN ('reserved','running','ok')",
                     (ref,)).fetchone():
            raise ReasonBusy(ref)
        if attempt is None:
            attempt = 1 + int(c.execute("SELECT COALESCE(MAX(attempt),0) FROM agent_calls WHERE reason_ref=?",
                                        (ref,)).fetchone()[0])
        try:
            cur = c.execute("INSERT INTO agent_calls(agent_key,brain_id,context_ref,purpose,reason_ref,attempt,status,"
                            "counted,obligation,mirror_ref,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (str(agent_key or ""), str(brain_id or ""), str(context_ref or ""), purpose, ref,
                             int(attempt), "reserved", 1 if counted else 0, 1 if obligation else 0,
                             str(mirror_ref or ""), _now(now)))
        except sqlite3.IntegrityError as ex:
            raise ReasonBusy(ref) from ex
        return int(cur.lastrowid)

    def mark_engine(self, call_id: int, engine: str = "", model: str = "", now: Optional[float] = None) -> bool:
        """Mốc gọi engine: từ đây lượt luôn tính (không hoàn được). Chỉ dòng `reserved` chuyển `running`."""
        with self._tx() as c:
            return self._mark_engine_in(c, call_id, engine, model, _now(now))

    @staticmethod
    def _mark_engine_in(c, call_id, engine, model, now):
        return c.execute("UPDATE agent_calls SET status='running', engine=?, model=?, engine_at=? "
                         "WHERE id=? AND status='reserved' AND engine_at IS NULL",
                         (str(engine or ""), str(model or ""), now, int(call_id))).rowcount == 1

    def settle(self, call_id: int, status: str, tokens_in: Optional[int] = None, tokens_out: Optional[int] = None,
               cost_usd: Optional[float] = None, now: Optional[float] = None) -> bool:
        """Chốt `ok`, `error` hay `interrupted` (đều tính). Dòng đã chốt hay đã hoàn thì không đổi."""
        if status not in ("ok", "error", "interrupted"):
            raise ValueError("kết cục lượt không hợp lệ")
        with self._tx() as c:
            return self._settle_in(c, call_id, status, tokens_in, tokens_out, cost_usd, _now(now))

    @staticmethod
    def _settle_in(c, call_id, status, tokens_in, tokens_out, cost_usd, now):
        return c.execute("UPDATE agent_calls SET status=?, tokens_in=?, tokens_out=?, cost_usd=?, settled_at=? "
                         "WHERE id=? AND status IN ('reserved','running')",
                         (status, tokens_in, tokens_out, cost_usd, now, int(call_id))).rowcount == 1

    def refund(self, call_id: int, now: Optional[float] = None) -> bool:
        """Hoàn lượt CHẮC CHẮN chưa gọi model (mốc engine chưa ghi). Dòng đã qua mốc thì không hoàn được: trả False."""
        with self._tx() as c:
            return self._refund_in(c, int(call_id), _now(now))

    @staticmethod
    def _refund_in(c, call_id: int, now: float) -> bool:
        return c.execute("UPDATE agent_calls SET status='refunded', settled_at=? WHERE id=? AND status='reserved' "
                         "AND engine_at IS NULL", (now, int(call_id))).rowcount == 1

    def get(self, call_id: int) -> Optional[dict]:
        with closing(self.store._conn()) as c:
            r = c.execute("SELECT * FROM agent_calls WHERE id=?", (int(call_id),)).fetchone()
            return dict(r) if r else None

    def rows(self, reason_ref: Optional[str] = None, mirror_ref: Optional[str] = None) -> list:
        q, args = "SELECT * FROM agent_calls WHERE 1=1", []
        if reason_ref is not None:
            q += " AND reason_ref=?"
            args.append(str(reason_ref))
        if mirror_ref is not None:
            q += " AND mirror_ref=?"
            args.append(str(mirror_ref))
        with closing(self.store._conn()) as c:
            return [dict(r) for r in c.execute(q + " ORDER BY id", args).fetchall()]

    def used(self) -> int:
        """Số lượt đang tính vào trần chung (cùng phép đếm với mọi đường giữ chỗ)."""
        with closing(self.store._conn()) as c:
            return RS._ceiling_used(c)

    # ───────────── đối soát lượt không gắn lượt nhóm ─────────────

    def reconcile_stale(self, now: Optional[float] = None, stale_s: float = STALE_RESERVED_S) -> dict:
        """Dòng KHÔNG phản chiếu gì (`mirror_ref = ''`: phán xử theo lô, xem xét, chủ động, quét) còn mở quá một lượt (10
        phút): chưa có mốc engine thì `refunded` (chắc chắn chưa gọi model), có mốc thì `interrupted` (vẫn tính).
        Idempotent. Dòng `team_turn:*` KHÔNG BAO GIỜ xử lý theo tuổi (lượt nhóm có thể chờ khoá bận tới busy_wait_s và
        một bước chạy tới STEP_TIMEOUT_S): `TeamCeiling.reconcile` lo theo trạng thái thật của `team_turns`."""
        t = _now(now)
        out = {"refunded": 0, "interrupted": 0}
        with self._tx() as c:
            rows = c.execute("SELECT id, engine_at FROM agent_calls WHERE status IN ('reserved','running') "
                             "AND created_at < ? AND mirror_ref = ''", (t - stale_s,)).fetchall()
            for r in rows:
                if r["engine_at"] is None:
                    out["refunded"] += self._refund_in(c, r["id"], t)
                else:
                    out["interrupted"] += c.execute(
                        "UPDATE agent_calls SET status='interrupted', settled_at=? WHERE id=? "
                        "AND status IN ('reserved','running')", (t, r["id"])).rowcount
        return out


class TeamCeiling:
    """Phụ thuộc `ceiling` của `TeamRunner` (thiết kế 3.1, 9.1). Mọi thao tác khoá theo mã lượt nhóm.

    Thứ tự hai kho: giữ chỗ `team_turns` (kho nhóm) rồi mới giữ chỗ sổ chung; sổ chung từ chối thì người gọi hoàn
    `team_turns` ngay. Lỗi kho chung lúc chốt không được làm hỏng lượt nhóm (bộ chạy nuốt lỗi), đối soát sửa sau."""

    def __init__(self, store: "RS.GoalStore"):
        self.store = store
        self.ledger = CallLedger(store)

    @staticmethod
    def mirror(turn_id: str) -> str:
        return f"team_turn:{turn_id}"

    def enabled(self) -> bool:
        return RS.call_ceiling() is not None

    def _live(self, c, turn_id: str):
        return c.execute("SELECT * FROM agent_calls WHERE mirror_ref=? ORDER BY id DESC LIMIT 1",
                         (self.mirror(turn_id),)).fetchone()

    def reserve(self, turn: dict, now: Optional[float] = None) -> bool:
        """Giữ chỗ dòng phản chiếu cho lượt nhóm `turn` ({turn_id, team_id, agent_key, role, brain_id?}). False khi
        trần chung đầy (không ghi gì). Lượt nhóm là nghĩa vụ (dùng được cả trần), trừ lượt tự lên tiếng (T3 J)."""
        tid = str(turn["turn_id"])
        cid = self.ledger.reserve(purpose=TEAM_PURPOSE.get(str(turn.get("role") or ""), "reply"),
                                  reason_ref=self.mirror(tid), agent_key=str(turn.get("agent_key") or ""),
                                  brain_id=str(turn.get("brain_id") or ""),
                                  context_ref=f"team:{turn.get('team_id') or ''}",
                                  obligation=str(turn.get("role") or "") not in SPONTANEOUS_ROLES, counted=True,
                                  mirror_ref=self.mirror(tid), now=now)
        return cid is not None

    def mark(self, turn_id: str, engine: str = "", model: str = "", now: Optional[float] = None) -> None:
        """Mốc gọi engine của lượt nhóm. Dòng phản chiếu đã bị hoàn (đối soát) hay chưa có thì DỰNG LẠI một dòng
        `counted = 1` đang chạy (có thể tạm vượt trần: không làm mất lượt đã tới model)."""
        t = _now(now)
        with self.ledger._tx() as c:
            r = self._live(c, turn_id)
            if r is not None and r["status"] == "reserved":
                c.execute("UPDATE agent_calls SET status='running', engine=?, model=?, engine_at=? WHERE id=?",
                          (str(engine or ""), str(model or ""), t, r["id"]))
                return
            if r is not None and r["status"] in ("running", "ok", "error", "interrupted"):
                return
            att = 1 + int(c.execute("SELECT COALESCE(MAX(attempt),0) FROM agent_calls WHERE reason_ref=?",
                                    (self.mirror(turn_id),)).fetchone()[0])
            c.execute("INSERT INTO agent_calls(purpose,reason_ref,attempt,engine,model,status,counted,obligation,"
                      "mirror_ref,engine_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      ("reply", self.mirror(turn_id), att, str(engine or ""), str(model or ""), "running", 1, 1,
                       self.mirror(turn_id), t, t))

    def settle(self, turn_id: str, status: str, tokens_in: Optional[int] = None, tokens_out: Optional[int] = None,
               cost_usd: Optional[float] = None, now: Optional[float] = None) -> None:
        t = _now(now)
        with self.ledger._tx() as c:
            r = self._live(c, turn_id)
            if r is None or r["status"] not in OPEN_STATUSES:
                if r is None or r["status"] == "refunded":
                    # Lượt nhóm đã chốt sau mốc engine mà thiếu dòng (hay dòng bị hoàn nhầm): dựng lại, tính.
                    att = 1 + int(c.execute("SELECT COALESCE(MAX(attempt),0) FROM agent_calls WHERE reason_ref=?",
                                            (self.mirror(turn_id),)).fetchone()[0])
                    c.execute("INSERT INTO agent_calls(purpose,reason_ref,attempt,status,counted,obligation,mirror_ref,"
                              "tokens_in,tokens_out,cost_usd,created_at,settled_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                              ("reply", self.mirror(turn_id), att, status, 1, 1, self.mirror(turn_id), tokens_in,
                               tokens_out, cost_usd, t, t))
                return
            c.execute("UPDATE agent_calls SET status=?, tokens_in=?, tokens_out=?, cost_usd=?, settled_at=? WHERE id=?",
                      (status, tokens_in, tokens_out, cost_usd, t, r["id"]))

    def refund(self, turn_id: str, now: Optional[float] = None) -> None:
        """Lượt nhóm được hoàn (chưa tới mốc engine): dòng phản chiếu cũng `refunded`."""
        with self.ledger._tx() as c:
            r = self._live(c, turn_id)
            if r is not None:
                self.ledger._refund_in(c, r["id"], _now(now))

    def reconcile(self, teams: Any, startup: bool = False, now: Optional[float] = None,
                  stale_s: float = STALE_RESERVED_S, grace_s: float = RECONCILE_GRACE_S, batch: int = 2000) -> dict:
        """Đối soát hai kho (thiết kế 9.1, bản sửa sau review T1 vòng 2), idempotent. Dòng `team_turn:*` chỉ theo trạng
        thái của CHÍNH lượt nhóm đó, KHÔNG BAO GIỜ theo tuổi (lượt nhóm có thể nằm `reserved` không mốc engine trong lúc
        chờ khoá bận tới busy_wait_s, mặc định 1800 giây, và một bước chạy tới STEP_TIMEOUT_S):
        - lượt nhóm đã hoàn hay không còn: dòng `refunded` (đã có mốc engine thì `interrupted`, vẫn tính);
        - lượt nhóm đã chốt: dòng chốt theo; lượt nhóm đã tới mốc engine: dòng `running`;
        - lượt nhóm còn `reserved`/`running`: để nguyên;
        - lượt nhóm đã tới mốc engine mà THIẾU dòng sổ: dựng lại dòng `counted = 1` theo kết cục (có thể tạm vượt trần),
          CHỈ với lượt tạo sau mốc nâng lên T2 (`t2_migrated_at`) hay còn mở lúc nâng; lịch sử đã chốt trước khi nâng
          không bao giờ tính vào trần (quyết định của chủ, review T2 P1).
        Dòng sổ và lượt nhóm mới hơn `grace_s` (120 giây) bị bỏ qua: không bắt gặp lượt đang ở giữa hai bước giữ chỗ.
        Lúc khởi động (`startup`) mọi lượt của tiến trình cũ đã được `TeamRunner.recover` hoàn hay chốt `interrupted`,
        nên dòng sổ của chúng đi đúng đường đó. Dòng `mirror_ref = ''` theo quy tắc 10 phút (`reconcile_stale`)."""
        t = _now(now)
        cutoff = t - float(grace_s)
        out = {"refunded": 0, "settled": 0, "marked": 0, "rebuilt": 0, "stale": {}}
        with closing(self.store._conn()) as c:
            open_rows = [dict(r) for r in c.execute(
                "SELECT * FROM agent_calls WHERE status IN ('reserved','running') AND mirror_ref LIKE 'team_turn:%' "
                "AND created_at <= ?", (cutoff,)).fetchall()]
            mark = c.execute("SELECT value FROM ceiling_state WHERE name='team_scan_at'").fetchone()
            mig = c.execute("SELECT value FROM ceiling_state WHERE name='t2_migrated_at'").fetchone()
            cur_row = c.execute("SELECT at, turn_id FROM ceiling_cursor WHERE name='team_turns'").fetchone()
        # Mốc nâng lên T2 (GoalStore ghi lúc tạo bảng). Kho thiếu mốc (không nên có) thì lấy lúc này: không tính lịch sử.
        migrated = float(mig["value"]) if mig else t
        floor = migrated - float(grace_s)
        # Con trỏ bền `(created_at, turn_id)`: lần đầu bắt đầu từ mốc nâng; lần sau quét tiếp đúng chỗ dừng.
        cur_at, cur_id = (float(cur_row["at"]), str(cur_row["turn_id"])) if cur_row else (floor, "")
        settled_since = (float(mark["value"]) if mark else migrated) - 2 * float(grace_s) - 60.0
        for r in open_rows:
            tid = r["mirror_ref"][len("team_turn:"):]
            turn = teams.turn(tid)
            with self.ledger._tx() as c:
                cur = c.execute("SELECT status, engine_at FROM agent_calls WHERE id=?", (r["id"],)).fetchone()
                if cur is None or cur["status"] not in OPEN_STATUSES:
                    continue
                if turn is None or turn.get("status") == "refunded":
                    if cur["engine_at"] is None:
                        out["refunded"] += self.ledger._refund_in(c, r["id"], t)
                    else:
                        out["settled"] += c.execute("UPDATE agent_calls SET status='interrupted', settled_at=? "
                                                    "WHERE id=?", (t, r["id"])).rowcount
                elif turn.get("status") in ("ok", "error", "interrupted"):
                    out["settled"] += c.execute(
                        "UPDATE agent_calls SET status=?, tokens_in=?, tokens_out=?, cost_usd=?, "
                        "engine_at=COALESCE(engine_at, ?), settled_at=? WHERE id=?",
                        (turn["status"], turn.get("tokens_in"), turn.get("tokens_out"), turn.get("cost_usd"),
                         turn.get("engine_at") or t, t, r["id"])).rowcount
                elif turn.get("engine_at") is not None and cur["status"] == "reserved":
                    out["marked"] += c.execute(
                        "UPDATE agent_calls SET status='running', engine=?, model=?, engine_at=? WHERE id=?",
                        (turn.get("engine") or "", turn.get("model") or "", turn["engine_at"], r["id"])).rowcount
                # Lượt nhóm còn reserved/running (đang chờ khoá bận hay đang chạy): để nguyên, dù lâu bao nhiêu.
        # Lượt nhóm thiếu dòng sổ (review T2 P1, quyết định của chủ): KHÔNG tính lịch sử trước khi nâng lên T2. Chỉ xét
        # lượt tạo sau mốc `t2_migrated_at` (trừ ân hạn) và lượt còn mở lúc nâng (chốt hay còn chạy sau mốc). Cửa sổ quét
        # bắt đầu từ lần quét trước (không quét lại cả bảng), có trần số dòng mỗi lần.
        window, special = teams.turns_for_reconcile(cur_at, cur_id, cutoff, floor, settled_since, limit=batch)
        seen_ids = {x["turn_id"] for x in window}
        turns = window + [x for x in special if x["turn_id"] not in seen_ids]
        refs = [self.mirror(x["turn_id"]) for x in turns]
        have = set()
        with closing(self.store._conn()) as c:
            for k in range(0, len(refs), 500):
                part = refs[k:k + 500]
                have |= {row[0] for row in c.execute(
                    f"SELECT DISTINCT mirror_ref FROM agent_calls WHERE mirror_ref IN ({','.join('?' * len(part))})",
                    part).fetchall()}
        for turn in turns:
            ref = self.mirror(turn["turn_id"])
            if ref in have or turn.get("engine_at") is None or float(turn.get("created_at") or 0) > cutoff:
                continue
            settled = turn.get("settled_at")
            open_at_upgrade = turn.get("status") in ("reserved", "running") or (
                settled is not None and float(settled) >= migrated - float(grace_s))
            if float(turn.get("created_at") or 0) < migrated - float(grace_s) and not open_at_upgrade:
                continue   # lượt đã chốt trước khi nâng: lịch sử, không bao giờ tính
            status = turn["status"] if turn["status"] in ("running", "ok", "error", "interrupted") else "running"
            with self.ledger._tx() as c:
                if c.execute("SELECT 1 FROM agent_calls WHERE mirror_ref=?", (ref,)).fetchone():
                    continue
                c.execute("INSERT INTO agent_calls(agent_key,context_ref,purpose,reason_ref,attempt,engine,model,"
                          "status,counted,obligation,mirror_ref,tokens_in,tokens_out,cost_usd,engine_at,created_at,"
                          "settled_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (turn.get("agent_key") or "", f"team:{turn.get('team_id') or ''}",
                           TEAM_PURPOSE.get(turn.get("role") or "", "reply"), ref, 1, turn.get("engine") or "",
                           turn.get("model") or "", status, 1, 1, ref, turn.get("tokens_in"),
                           turn.get("tokens_out"), turn.get("cost_usd"), turn["engine_at"],
                           float(turn.get("created_at") or t),
                           None if status == "running" else (turn.get("settled_at") or t)))
                out["rebuilt"] += 1
        # Con trỏ tiến tới dòng cuối của cửa sổ; cửa sổ đầy thì lần sau quét tiếp (không nạp lại cả bảng).
        out["truncated"] = len(window) >= int(batch)
        with self.ledger._tx() as c:
            if window:
                last = window[-1]
                c.execute("INSERT INTO ceiling_cursor(name, at, turn_id) VALUES('team_turns', ?, ?) "
                          "ON CONFLICT(name) DO UPDATE SET at=excluded.at, turn_id=excluded.turn_id",
                          (float(last.get("created_at") or 0), str(last["turn_id"])))
            c.execute("INSERT INTO ceiling_state(name, value) VALUES('team_scan_at', ?) "
                      "ON CONFLICT(name) DO UPDATE SET value=excluded.value", (t,))
        out["stale"] = self.ledger.reconcile_stale(now=t, stale_s=stale_s)
        return out


class WakeReasons:
    """Lý do thức theo agent x ngữ cảnh (thiết kế 3.2). Một lý do `pending` mỗi (agent, ngữ cảnh, loại): nguồn mới gom
    vào đó; một lý do `pending` mới được cùng tồn tại với một lý do đang `claimed` (nguồn đến trong lúc lượt xem xét
    đang chạy vào lý do chờ mới, không vào lý do đang chạy)."""

    def __init__(self, store: "RS.GoalStore", ledger: Optional[CallLedger] = None):
        self.store = store
        self.ledger = ledger or CallLedger(store)

    def _tx(self):
        return self.store._Tx(self.store)

    @staticmethod
    def _reason(r) -> dict:
        return dict(r) if r is not None else None

    @staticmethod
    def _pending_in(c, agent_key: str, context_ref: str, code: str, now: float, create: bool = True):
        r = c.execute("SELECT * FROM agent_wake_reasons WHERE agent_key=? AND context_ref=? AND code=? "
                      "AND status='pending'", (agent_key, context_ref, code)).fetchone()
        if r is None and create:
            cur = c.execute("INSERT INTO agent_wake_reasons(agent_key,context_ref,code,status,attempt,created_at,"
                            "updated_at) VALUES(?,?,?,'pending',0,?,?)", (agent_key, context_ref, code, now, now))
            r = c.execute("SELECT * FROM agent_wake_reasons WHERE id=?", (cur.lastrowid,)).fetchone()
        return r

    # ───────────── nguồn ─────────────

    def add_source(self, agent_key: str, context_ref: str, code: str, source_ref: str, group_ref: str = "",
                   now: Optional[float] = None) -> int:
        """Gom một nguồn vào lý do `pending` (tạo nếu chưa có). Idempotent theo `source_ref`: gọi lại trả đúng lý do cũ,
        không thêm dòng (bộ chiếu chạy lại an toàn). Trả mã lý do."""
        if code not in REASON_CODES:
            raise ValueError(f"loại lý do không hợp lệ: {code}")
        t = _now(now)
        with self._tx() as c:
            old = c.execute("SELECT reason_id FROM agent_wake_sources WHERE source_ref=?", (str(source_ref),)).fetchone()
            if old is not None:
                return int(old["reason_id"])
            r = self._pending_in(c, str(agent_key), str(context_ref), code, t)
            c.execute("INSERT INTO agent_wake_sources(reason_id,source_ref,group_ref,added_at) VALUES(?,?,?,?)",
                      (r["id"], str(source_ref), str(group_ref or ""), t))
            c.execute("UPDATE agent_wake_reasons SET updated_at=? WHERE id=?", (t, r["id"]))
            return int(r["id"])

    def _remove_in(self, c, rows, t: float) -> list:
        touched = []
        for s in rows:
            rr = c.execute("SELECT status FROM agent_wake_reasons WHERE id=?", (s["reason_id"],)).fetchone()
            # Lý do đang chạy (`claimed`) cũng đánh `removed_at` (review T2 P2-1): danh sách nguồn của lượt đã chốt lúc
            # nhận, nhưng `settle(ok)` chỉ chuyển nguồn còn sống, nên nguồn đã gỡ không bị mang sang lý do chờ kế tiếp.
            if rr is None or rr["status"] not in ("pending", "claimed") or s["removed_at"] is not None \
                    or s["consumed_at"] is not None:
                continue
            c.execute("UPDATE agent_wake_sources SET removed_at=? WHERE source_ref=?", (t, s["source_ref"]))
            touched.append(int(s["reason_id"]))
        for rid in set(touched):
            live = c.execute("SELECT COUNT(*) FROM agent_wake_sources WHERE reason_id=? AND removed_at IS NULL",
                             (rid,)).fetchone()[0]
            if not live:
                c.execute("UPDATE agent_wake_reasons SET status='superseded', updated_at=? WHERE id=? "
                          "AND status='pending'", (t, rid))
            else:
                c.execute("UPDATE agent_wake_reasons SET updated_at=? WHERE id=?", (t, rid))
        return [s["source_ref"] for s in rows if int(s["reason_id"]) in touched]

    def remove_source(self, source_ref: str, now: Optional[float] = None) -> bool:
        """Nguồn bị bỏ (reaction gỡ hay đổi): đánh `removed_at` khi lý do còn `pending` hay đang `claimed`; lý do chờ không
        còn nguồn nào thì `superseded` (lý do đang chạy giữ nguyên, lượt đó tự chốt). Lý do đã chốt thì không đụng (bằng
        chứng). Trả có gỡ không."""
        t = _now(now)
        with self._tx() as c:
            rows = c.execute("SELECT * FROM agent_wake_sources WHERE source_ref=?", (str(source_ref),)).fetchall()
            return bool(self._remove_in(c, rows, t))

    def remove_group(self, group_ref: str, keep: Iterable[str] = (), now: Optional[float] = None) -> list:
        """Gỡ mọi nguồn còn chờ của cùng một cặp (tin, người phản hồi) trừ `keep`. Trả các `source_ref` đã gỡ."""
        if not group_ref:
            return []
        keep = {str(x) for x in keep}
        t = _now(now)
        with self._tx() as c:
            rows = [r for r in c.execute("SELECT * FROM agent_wake_sources WHERE group_ref=?", (str(group_ref),))
                    .fetchall() if r["source_ref"] not in keep]
            return self._remove_in(c, rows, t)

    # ───────────── nhận (CAS), chốt ─────────────

    def claim(self, reason_id: int, *, try_busy: Optional[Callable[[], bool]] = None,
              release_busy: Optional[Callable[[], Any]] = None, purpose: Optional[str] = None,
              brain_id: str = "", obligation: bool = False, now: Optional[float] = None) -> dict:
        """Nhận một lý do để phục vụ (thiết kế 3.2, 3.4): THỬ KHOÁ BẬN TRƯỚC (không chờ), bận thì không nhận, lý do giữ
        `pending` và `attempt` không tăng. Rồi trong MỘT giao dịch: CAS `pending -> claimed`, `attempt + 1`, chốt danh
        sách nguồn còn sống, giữ chỗ một dòng `agent_calls` (`reason_ref = wr:<id>`, kiểm trần). Trần đầy thì không nhận
        (lý do giữ nguyên, kể cả `attempt`) và nhả khoá bận.

        Trả {"outcome": "claimed"|"busy"|"quota"|"gone"|"conflict", "reason", "sources", "call_id"}."""
        t = _now(now)
        if try_busy is not None and not try_busy():
            return {"outcome": "busy", "reason": self.get(reason_id), "sources": [], "call_id": None}
        done = False
        try:
            with self._tx() as c:
                r = c.execute("SELECT * FROM agent_wake_reasons WHERE id=?", (int(reason_id),)).fetchone()
                if r is None or r["status"] != "pending":
                    raise _Abort("gone")
                srcs = [s["source_ref"] for s in c.execute(
                    "SELECT source_ref FROM agent_wake_sources WHERE reason_id=? AND removed_at IS NULL "
                    "AND consumed_at IS NULL ORDER BY added_at, source_ref", (r["id"],)).fetchall()]
                if not srcs:
                    raise _Abort("empty")
                att = int(r["attempt"]) + 1
                try:
                    cid = self.ledger.reserve(purpose=purpose or (r["code"] if r["code"] in PURPOSES else "review"),
                                              reason_ref=f"wr:{r['id']}", agent_key=r["agent_key"], brain_id=brain_id,
                                              context_ref=r["context_ref"], obligation=obligation, counted=True,
                                              attempt=att, now=t, c=c)
                except ReasonBusy:
                    raise _Abort("conflict")
                if cid is None:
                    raise _Abort("quota")
                n = c.execute("UPDATE agent_wake_reasons SET status='claimed', attempt=?, ledger_ref=?, updated_at=? "
                              "WHERE id=? AND status='pending'", (att, f"call:{cid}", t, r["id"])).rowcount
                if n != 1:
                    raise _Abort("gone")
                out = {"outcome": "claimed", "sources": srcs, "call_id": cid}
            done = True
        except _Abort as ab:
            outcome = ab.outcome
            if outcome == "empty":
                # Lý do không còn nguồn: chốt `superseded` trong giao dịch RIÊNG (review T2 P3: ném trong cùng giao dịch
                # làm lệnh chốt bị rollback).
                with self._tx() as c:
                    if not c.execute("SELECT 1 FROM agent_wake_sources WHERE reason_id=? AND removed_at IS NULL "
                                     "AND consumed_at IS NULL", (int(reason_id),)).fetchone():
                        c.execute("UPDATE agent_wake_reasons SET status='superseded', updated_at=? WHERE id=? "
                                  "AND status='pending'", (t, int(reason_id)))
                outcome = "gone"
            return {"outcome": outcome, "reason": self.get(reason_id), "sources": [], "call_id": None}
        finally:
            # Không nhận được (kể cả lỗi kho bất ngờ, không chỉ _Abort): nhả khoá bận vừa lấy, không để rò tới hết hạn.
            if not done and release_busy is not None:
                try:
                    release_busy()
                except Exception:  # noqa: BLE001
                    pass
        out["reason"] = self.get(reason_id)
        return out

    def settle(self, reason_id: int, call_status: str, consumed: Iterable[str] = (), *, tokens_in=None,
               tokens_out=None, cost_usd=None, now: Optional[float] = None) -> dict:
        """Chốt lượt phục vụ lý do đang `claimed`.

        - `ok`: lý do `served`; nguồn trong `consumed` đánh `consumed_at`; nguồn KHÔNG được tiêu thụ chuyển sang lý do
          `pending` cùng loại (tạo mới nếu chưa có), nên được xem đúng một lần ở lượt sau.
        - `error`/`interrupted`/`refunded`: đã có lý do `pending` cùng loại (tạo trong lúc chạy) thì chuyển nguồn sang đó,
          giữ `attempt` lớn hơn, lý do đang chạy `superseded`; chưa có thì quay về `pending`, hay `failed` khi đã thử đủ
          MAX_ATTEMPTS lần. Dòng sổ lượt chốt theo (`refunded` chỉ khi chưa qua mốc engine)."""
        if call_status not in ("ok", "error", "interrupted", "refunded"):
            raise ValueError("kết cục không hợp lệ")
        t = _now(now)
        consumed = {str(x) for x in consumed}
        with self._tx() as c:
            r = c.execute("SELECT * FROM agent_wake_reasons WHERE id=?", (int(reason_id),)).fetchone()
            if r is None or r["status"] != "claimed":
                return {"status": r["status"] if r else None, "moved_to": None}
            cid = int(r["ledger_ref"].split(":", 1)[1]) if str(r["ledger_ref"]).startswith("call:") else None
            if cid is not None:
                if call_status == "refunded":
                    if not CallLedger._refund_in(c, cid, t):
                        call_status = "interrupted"
                        c.execute("UPDATE agent_calls SET status='interrupted', settled_at=? WHERE id=? "
                                  "AND status IN ('reserved','running')", (t, cid))
                else:
                    c.execute("UPDATE agent_calls SET status=?, tokens_in=?, tokens_out=?, cost_usd=?, settled_at=? "
                              "WHERE id=? AND status IN ('reserved','running')",
                              (call_status, tokens_in, tokens_out, cost_usd, t, cid))
            live = c.execute("SELECT source_ref FROM agent_wake_sources WHERE reason_id=? AND removed_at IS NULL "
                             "AND consumed_at IS NULL", (r["id"],)).fetchall()
            live = [x["source_ref"] for x in live]
            moved_to = None
            if call_status == "ok":
                for ref in live:
                    if ref in consumed:
                        c.execute("UPDATE agent_wake_sources SET consumed_at=? WHERE source_ref=?", (t, ref))
                rest = [ref for ref in live if ref not in consumed]
                if rest:
                    p = self._pending_in(c, r["agent_key"], r["context_ref"], r["code"], t)
                    moved_to = int(p["id"])
                    c.executemany("UPDATE agent_wake_sources SET reason_id=? WHERE source_ref=?",
                                  [(moved_to, ref) for ref in rest])
                c.execute("UPDATE agent_wake_reasons SET status='served', updated_at=? WHERE id=?", (t, r["id"]))
                return {"status": "served", "moved_to": moved_to}
            p = self._pending_in(c, r["agent_key"], r["context_ref"], r["code"], t, create=False)
            if p is not None:
                c.executemany("UPDATE agent_wake_sources SET reason_id=? WHERE source_ref=?",
                              [(p["id"], ref) for ref in live])
                c.execute("UPDATE agent_wake_reasons SET attempt=MAX(attempt, ?), updated_at=? WHERE id=?",
                          (int(r["attempt"]), t, p["id"]))
                c.execute("UPDATE agent_wake_reasons SET status='superseded', updated_at=? WHERE id=?", (t, r["id"]))
                return {"status": "superseded", "moved_to": int(p["id"])}
            if not live:
                c.execute("UPDATE agent_wake_reasons SET status='superseded', updated_at=? WHERE id=?", (t, r["id"]))
                return {"status": "superseded", "moved_to": None}
            # Lượt hoàn (chắc chắn chưa gọi model) không tính là một lần thử thất bại.
            att = int(r["attempt"]) - (1 if call_status == "refunded" else 0)
            st = "failed" if att >= MAX_ATTEMPTS else "pending"
            c.execute("UPDATE agent_wake_reasons SET status=?, attempt=?, ledger_ref='', updated_at=? WHERE id=?",
                      (st, max(0, att), t, r["id"]))
            return {"status": st, "moved_to": None}

    def requeue(self, reason_id: int, source_refs: Iterable[str], now: Optional[float] = None) -> Optional[int]:
        """Trả các nguồn ĐÃ tiêu thụ của một lý do `served` về lý do `pending` cùng loại (tạo nếu chưa có), bỏ mốc tiêu thụ.
        Dùng khi lượt đã chạy nhưng tác động bị chặn vì hết hạn mức trước khi phán xử (review T3 L P2-1: hết trần không làm
        mất phản hồi). Lý do cũ giữ `served` (lượt đã thật sự gọi model). Trả mã lý do chờ, None khi không có gì để trả."""
        refs = [str(x) for x in source_refs or [] if x]
        if not refs:
            return None
        t = _now(now)
        with self._tx() as c:
            r = c.execute("SELECT * FROM agent_wake_reasons WHERE id=?", (int(reason_id),)).fetchone()
            if r is None or r["status"] != "served":
                return None
            rows = [x["source_ref"] for x in c.execute(
                f"SELECT source_ref FROM agent_wake_sources WHERE reason_id=? AND removed_at IS NULL AND consumed_at "
                f"IS NOT NULL AND source_ref IN ({','.join('?' * len(refs))})", [r["id"]] + refs).fetchall()]
            if not rows:
                return None
            p = self._pending_in(c, r["agent_key"], r["context_ref"], r["code"], t)
            c.executemany("UPDATE agent_wake_sources SET reason_id=?, consumed_at=NULL WHERE source_ref=?",
                          [(p["id"], ref) for ref in rows])
            c.execute("UPDATE agent_wake_reasons SET updated_at=? WHERE id=?", (t, p["id"]))
            return int(p["id"])

    def retry_failed(self, reason_id: int, now: Optional[float] = None) -> Optional[int]:
        """Chủ bấm thử lại một lý do `failed`: về `pending` (attempt về 0). Đã có lý do chờ cùng loại thì gộp nguồn vào
        đó. Trả mã lý do đang chờ, None khi lý do không ở `failed`."""
        t = _now(now)
        with self._tx() as c:
            r = c.execute("SELECT * FROM agent_wake_reasons WHERE id=?", (int(reason_id),)).fetchone()
            if r is None or r["status"] != "failed":
                return None
            p = self._pending_in(c, r["agent_key"], r["context_ref"], r["code"], t, create=False)
            if p is None:
                c.execute("UPDATE agent_wake_reasons SET status='pending', attempt=0, updated_at=? WHERE id=?",
                          (t, r["id"]))
                return int(r["id"])
            c.execute("UPDATE agent_wake_sources SET reason_id=? WHERE reason_id=? AND removed_at IS NULL "
                      "AND consumed_at IS NULL", (p["id"], r["id"]))
            c.execute("UPDATE agent_wake_reasons SET status='superseded', updated_at=? WHERE id=?", (t, r["id"]))
            return int(p["id"])

    # ───────────── đọc ─────────────

    def get(self, reason_id: int) -> Optional[dict]:
        with closing(self.store._conn()) as c:
            r = c.execute("SELECT * FROM agent_wake_reasons WHERE id=?", (int(reason_id),)).fetchone()
            return dict(r) if r else None

    def reasons(self, agent_key: Optional[str] = None, context_ref: Optional[str] = None,
                status: Optional[str] = None, code: Optional[str] = None) -> list:
        q, args = "SELECT * FROM agent_wake_reasons WHERE 1=1", []
        for col, v in (("agent_key", agent_key), ("context_ref", context_ref), ("status", status), ("code", code)):
            if v is not None:
                q += f" AND {col}=?"
                args.append(str(v))
        with closing(self.store._conn()) as c:
            return [dict(r) for r in c.execute(q + " ORDER BY id", args).fetchall()]

    def sources(self, reason_id: int, live_only: bool = False) -> list:
        q = "SELECT * FROM agent_wake_sources WHERE reason_id=?"
        if live_only:
            q += " AND removed_at IS NULL AND consumed_at IS NULL"
        with closing(self.store._conn()) as c:
            return [dict(r) for r in c.execute(q + " ORDER BY added_at, source_ref", (int(reason_id),)).fetchall()]

    def source(self, source_ref: str) -> Optional[dict]:
        """Nguồn kèm trạng thái lý do đang chứa nó ({..., reason_status, reason_attempt, code, context_ref})."""
        with closing(self.store._conn()) as c:
            r = c.execute("SELECT s.*, r.status AS reason_status, r.attempt AS reason_attempt, r.code AS code, "
                          "r.context_ref AS context_ref, r.agent_key AS agent_key FROM agent_wake_sources s "
                          "JOIN agent_wake_reasons r ON r.id = s.reason_id WHERE s.source_ref=?",
                          (str(source_ref),)).fetchone()
            return dict(r) if r else None

    def sources_by_ref(self, source_refs: Iterable[str]) -> dict:
        """{source_ref: nguồn kèm trạng thái lý do} cho nhiều nguồn trong một câu đọc (bộ chiếu đối soát theo lô)."""
        refs = sorted({str(x) for x in source_refs or [] if x})
        out: dict = {}
        if not refs:
            return out
        with closing(self.store._conn()) as c:
            for i in range(0, len(refs), 500):
                part = refs[i:i + 500]
                for r in c.execute("SELECT s.*, r.status AS reason_status, r.attempt AS reason_attempt, r.code AS code, "
                                   "r.context_ref AS context_ref, r.agent_key AS agent_key FROM agent_wake_sources s "
                                   "JOIN agent_wake_reasons r ON r.id = s.reason_id WHERE s.source_ref IN "
                                   f"({','.join('?' * len(part))})", part).fetchall():
                    out[str(r["source_ref"])] = dict(r)
        return out


class _Abort(Exception):
    def __init__(self, outcome: str):
        super().__init__(outcome)
        self.outcome = outcome


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)
