"""Hạn mức lượt tự phát mỗi agent mỗi ngày `agent_daily_calls` (T3 phần L, 0.156.0).

Thiết kế: docs/superpowers/specs/2026-10-15-team-adaptive-design.md mục 9; hợp đồng docs/dev/team-chat-t3-contract.md
mục 3; tài liệu docs/dev/team-chat-t3-learn.md.

- Mặc định 6 lượt/ngày/agent; CHỈ chủ đổi (kể cả "Không giới hạn" = None). Trưởng nhóm, kể cả Toàn quyền, không chỉnh.
- Phép đếm đọc thẳng sổ lượt chung `agent_calls` (không có sổ thứ hai): dòng của agent trong ngày (giờ máy), trừ dòng
  `refunded`, với purpose tự phát (`proactive`, `scan`, `review`, `reaction_review`) cộng lượt phán xử tin chủ động ở CHAT
  RIÊNG (`judge_batch` có `agent_key` và ngữ cảnh `dm:`). Phán xử theo lô của nhóm tính vào `judge_daily` của nhóm, không ở đây.
- Ưu tiên `reaction_review` > `related_review` > `wait_unblocked` > chủ động/quét/tự rà soát. Luôn giữ 2 lượt mỗi ngày cho
  hai loại đầu: loại khác chỉ được dùng tới `trần - (2 - số lượt hai loại đầu đã dùng hôm nay)`.
- `try_spend` chỉ KIỂM (không ghi lượt): lượt thật được tính khi người gọi giữ chỗ sổ lượt ngay sau đó, nên lượt bị hoàn
  (chưa tới model) tự trả lại hạn mức. Hết hạn mức: người gọi giữ lý do `pending` và hiện "Chờ hạn mức".
- Qua ngày, mỗi lý do đã từng chờ hạn mức chỉ được tối đa MỘT lượt mỗi ngày (không bù hàng loạt).
- Hạn mức không bao giờ được nâng bởi học, phản hồi hay lệnh của agent.
"""
from __future__ import annotations

import time
from contextlib import closing
from typing import Any, Callable, Optional

DEFAULT_DAILY = 6
RESERVED = 2
MAX_DAILY = 200
PRIORITY = {"reaction_review": 0, "related_review": 1, "wait_unblocked": 2, "proactive": 3, "proactive_judge": 3,
            "scan": 3, "review": 3}
RESERVED_FOR = ("reaction_review", "related_review")
LEDGER_PURPOSES = ("proactive", "scan", "review", "reaction_review")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_budget(
  agent_key TEXT PRIMARY KEY, daily_calls INTEGER, unlimited INTEGER NOT NULL DEFAULT 0, by TEXT NOT NULL DEFAULT '',
  updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS agent_budget_waits(
  agent_key TEXT NOT NULL, reason_ref TEXT NOT NULL, day TEXT NOT NULL, at REAL NOT NULL,
  PRIMARY KEY(agent_key, reason_ref, day));
"""
_READY: set = set()
_STORE: list = [None]


def wire(store_fn: Optional[Callable[[], Any]]) -> None:
    """`main.py` nối kho resonance mặc định (hàm trả kho hay None) cho lời gọi `try_spend(agent_key, purpose)` của P và J."""
    _STORE[0] = store_fn


def _default_store():
    fn = _STORE[0]
    if fn is None:
        return None
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return None


def ensure(store, force: bool = False) -> None:
    key = str(getattr(store, "path", id(store)))
    if key in _READY and not force:
        return
    with closing(store._conn()) as c:
        c.executescript(_SCHEMA)
    _READY.add(key)


def day_start(at: float) -> float:
    lt = time.localtime(at)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def day_tag(at: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(at))


def get_cap(store, agent_key: str) -> Optional[int]:
    """Trần ngày của agent: số, hay None khi chủ chọn "Không giới hạn". Chưa đặt: mặc định 6."""
    ensure(store)
    with closing(store._conn()) as c:
        r = c.execute("SELECT daily_calls, unlimited FROM agent_budget WHERE agent_key=?", (str(agent_key),)).fetchone()
    if r is None:
        return DEFAULT_DAILY
    if r["unlimited"]:
        return None
    return int(r["daily_calls"]) if r["daily_calls"] is not None else DEFAULT_DAILY


def set_cap(store, agent_key: str, value: Any, by: str = "owner", at: Optional[float] = None) -> Optional[int]:
    """Chủ đặt trần ngày: số 0..200, hay "unlimited"/None là Không giới hạn. Người gọi khác chủ bị từ chối
    (PermissionError): học, phản hồi, trưởng nhóm hay Toàn quyền không nâng được trần này."""
    if str(by) != "owner":
        raise PermissionError("chỉ chủ mới đổi được hạn mức lượt mỗi ngày của trợ lý")
    # Chuỗi rỗng KHÔNG phải "Không giới hạn" (review T3 L P3): ô trống gửi lên là lỗi nhập (400), không âm thầm bỏ trần.
    unlimited = value is None or str(value).strip().lower() in ("unlimited", "none")
    n = None
    if not unlimited:
        try:
            n = int(value)
        except (TypeError, ValueError):
            raise ValueError("hạn mức phải là số hay Không giới hạn")
        if not 0 <= n <= MAX_DAILY:
            raise ValueError(f"hạn mức phải trong 0 tới {MAX_DAILY}")
    ensure(store)
    t = time.time() if at is None else float(at)
    with store._Tx(store) as c:
        c.execute("INSERT INTO agent_budget(agent_key,daily_calls,unlimited,by,updated_at) VALUES(?,?,?,?,?) "
                  "ON CONFLICT(agent_key) DO UPDATE SET daily_calls=excluded.daily_calls, unlimited=excluded.unlimited, "
                  "by=excluded.by, updated_at=excluded.updated_at", (str(agent_key), n, 1 if unlimited else 0, "owner", t))
    return None if unlimited else n


def _counted_where() -> str:
    marks = ",".join(f"'{p}'" for p in LEDGER_PURPOSES)
    return (f"agent_key=? AND created_at>=? AND status<>'refunded' AND (purpose IN ({marks}) OR "
            f"(purpose='judge_batch' AND context_ref LIKE 'dm:%'))")


def usage(store, agent_key: str, at: Optional[float] = None) -> dict:
    """Hạn mức hôm nay: {cap, used, reserved_used, left, by_purpose, day_start}. `cap` None là Không giới hạn."""
    t = time.time() if at is None else float(at)
    ensure(store)
    d0 = day_start(t)
    key = str(agent_key)
    with closing(store._conn()) as c:
        rows = c.execute(f"SELECT purpose, reason_ref FROM agent_calls WHERE {_counted_where()}", (key, d0)).fetchall()
        related = {f"wr:{r['id']}" for r in c.execute(
            "SELECT id FROM agent_wake_reasons WHERE agent_key=? AND code='related_review'", (key,)).fetchall()}
    by: dict = {}
    reserved_used = 0
    for r in rows:
        p = r["purpose"]
        if p == "judge_batch":
            p = "related_review" if r["reason_ref"] in related else "proactive_judge"
        by[p] = by.get(p, 0) + 1
        if p in RESERVED_FOR:
            reserved_used += 1
    cap = get_cap(store, key)
    used = len(rows)
    return {"agent_key": key, "cap": cap, "used": used, "reserved_used": reserved_used,
            "left": None if cap is None else max(0, cap - used), "reserved": RESERVED, "by_purpose": by,
            "day_start": d0}


def runs(store, agent_key: str, finished_limit: int = 40) -> list:
    """Các lượt tự phát của agent, đúng những dòng `usage` đếm (cùng điều kiện, không giới hạn theo ngày): mọi lượt còn
    đang chạy, rồi `finished_limit` lượt đã chốt mới nhất (theo giờ bắt đầu, là thứ tự tab xếp thẻ). Tab Công việc của
    trợ lý đọc ở đây để con số "hôm nay đã tự làm N lần" và danh sách việc không bao giờ lệch nhau."""
    ensure(store)
    key = str(agent_key or "")
    if not key:
        return []
    q = (f"SELECT id, purpose, context_ref, reason_ref, status, created_at, settled_at FROM agent_calls "
         f"WHERE {_counted_where()} AND status ")
    order = " ORDER BY created_at DESC, id DESC"
    with closing(store._conn()) as c:
        live = c.execute(q + "IN ('reserved','running')" + order, (key, 0)).fetchall()
        done = c.execute(q + "NOT IN ('reserved','running')" + order + " LIMIT ?",
                         (key, 0, max(0, int(finished_limit)))).fetchall()
    return [dict(r) for r in live] + [dict(r) for r in done]


def _purpose_of(purpose: str) -> str:
    p = str(purpose or "")
    return p if p in PRIORITY else "proactive"


def try_spend(agent_key: str, purpose: str, at: Optional[float] = None, *, store: Any = None,
              reason_ref: Optional[str] = None, units: int = 1) -> tuple:
    """Có được chạy thêm MỘT lượt tự phát `purpose` hôm nay không: (True, "") hay (False, lý do). Gọi TRƯỚC khi giữ chỗ sổ
    lượt. `reason_ref` (`wr:<id>`): lý do đã từng chờ hạn mức thì qua ngày chỉ được một lượt mỗi ngày. `units`: số lượt
    cần còn trống (lượt xem xét reaction ở chat riêng cần 2: lượt xem xét và lượt phán xử tin mới, review T3 L P2-1). Chưa nối kho hay
    chưa có kho: cho qua (khi đó không có lượt tự phát nào chạy được; trần chung của máy chủ vẫn áp ở sổ lượt)."""
    st = store if store is not None else _default_store()
    if st is None:
        return True, ""
    t = time.time() if at is None else float(at)
    p = _purpose_of(purpose)
    key = str(agent_key or "")
    if not key:
        return True, ""
    u = usage(st, key, t)
    if reason_ref:
        with closing(st._conn()) as c:
            waited = c.execute("SELECT 1 FROM agent_budget_waits WHERE agent_key=? AND reason_ref=? AND day<?",
                               (key, str(reason_ref), day_tag(t))).fetchone()
            ran_today = c.execute("SELECT 1 FROM agent_calls WHERE reason_ref=? AND created_at>=? AND "
                                  "status<>'refunded'", (str(reason_ref), u["day_start"])).fetchone()
        if waited and ran_today:
            return False, "backlog_once"
    cap = u["cap"]
    if cap is None:
        return True, ""
    extra = max(0, int(units or 1) - 1)
    if p in RESERVED_FOR:
        ok = u["used"] + extra < cap
    else:
        hold = max(0, RESERVED - u["reserved_used"])
        ok = u["used"] + extra < cap - hold
    if ok:
        return True, ""
    if reason_ref:
        note_wait(st, key, str(reason_ref), t)
    return False, "agent_daily_calls"


def note_wait(store, agent_key: str, reason_ref: str, at: Optional[float] = None) -> None:
    """Ghi lý do đã phải chờ hạn mức hôm nay (để qua ngày không bù hàng loạt). Dọn mốc cũ hơn 7 ngày."""
    t = time.time() if at is None else float(at)
    ensure(store)
    with store._Tx(store) as c:
        c.execute("INSERT OR IGNORE INTO agent_budget_waits(agent_key,reason_ref,day,at) VALUES(?,?,?,?)",
                  (str(agent_key), str(reason_ref), day_tag(t), t))
        c.execute("DELETE FROM agent_budget_waits WHERE at<?", (t - 7 * 86400,))


def sort_by_priority(reasons: list) -> list:
    """Sắp lý do lớp 3 theo thứ tự ưu tiên tiêu hạn mức (`code`), cũ trước trong cùng loại."""
    return sorted(reasons or [], key=lambda r: (PRIORITY.get(str(r.get("code") or ""), 9), int(r.get("id") or 0)))


def limits_row(store: Any = None, agent_key: Optional[str] = None) -> dict:
    """Dòng của bảng giới hạn T1 (nhóm "owner"): mặc định 6, có lựa chọn Không giới hạn; chủ chỉnh từng trợ lý ở bảng
    Bài học và hạn mức."""
    value: Optional[int] = DEFAULT_DAILY
    if store is not None and agent_key:
        try:
            value = get_cap(store, agent_key)
        except Exception:  # noqa: BLE001
            value = DEFAULT_DAILY
    return {"key": "agent_daily_calls", "category": "owner", "value": value, "unit": "count", "unlimited_ok": True,
            "reserved": RESERVED}
