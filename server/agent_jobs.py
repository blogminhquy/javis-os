"""Tab Công việc của một trợ lý ở trang Cộng sự (0.142.0).

Gom việc của MỘT trợ lý (theo `agent_key` bền, trong đúng một brain) từ ba nguồn, đọc thẳng bản ghi gốc, không sao chép:
- **Nhóm** (`kanban.sqlite3` làn `team` + bước trong `team.sqlite3`): việc giao thẳng cho trợ lý, việc trợ lý điều phối,
  và việc trợ lý chỉ làm một bước con, hỗ trợ hay tổng hợp (người làm bước con cũng thấy việc liên quan).
- **Chat riêng** (Kanban thường): việc xếp hàng từ cuộc chat riêng với trợ lý (`chat_id` là phiên `agent:<slug>` đã ghim
  đúng mã), và việc giao bằng nút Giao việc ở chính tab này (khoá idempotency `agent:<mã>:<slug>:...:<nonce>`).
- **Auto** (mục tiêu Cộng hưởng, `resonance.sqlite3`): mục tiêu của trợ lý, cùng mục tiêu cũ trợ lý đang là người review.

Mỗi việc rơi vào đúng một trong bốn ngăn: `running` (Đang làm), `waiting` (Đang chờ), `needs_you` (Cần bạn), `done`
(Đã xong). Không có phần trăm giả: tiến độ là số bước thật của việc nhóm.

Vai của trợ lý trong việc chỉ có bốn: `coordinator` (Điều phối), `worker` (Thực hiện), `helper` (Hỗ trợ), `verifier`
(Kiểm chứng); mục tiêu cũ trợ lý là người review cố định mang `verifier_legacy`.

Mỗi thẻ có `next`: bước kế tiếp tính ở server (mã + tham số, giao diện đọc bằng lời): vị trí trong hàng của nhóm, đang chờ
trợ lý xong việc ở nhóm khác, chờ bạn kèm lý do, bật AI tự vận hành, bấm Tiếp tục.

Danh sách lọc theo nguồn (`source`) và ngăn (`bucket`), phân trang bằng `cursor` (vị trí) và `limit`. Lịch sử đã xong
đọc theo cửa sổ vừa đủ cho trang đang xem, nên không có trần cố định giấu việc: trang sau đọc rộng hơn.

Giao việc (`assign`) tạo MỘT việc Kanban gắn mã trợ lý (hay một việc nhóm giao cho trợ lý, qua đúng máy nhóm). Việc
kiểm chứng mang `v` trong khoá idempotency (bền suốt đời việc) cùng mục được kiểm. Không tạo gì khi chỉ đọc; chat
thường không tự sinh việc.
"""
from __future__ import annotations

import re
import time
from typing import Any, Optional

BUCKETS = ("running", "waiting", "needs_you", "done")
SOURCES = ("team", "chat", "auto")
ROLES = ("coordinator", "worker", "helper", "verifier", "verifier_legacy")
RESULT_CHARS = 280
PAGE = 30
MAX_PAGE = 100
# Lịch sử tối thiểu đọc mỗi nguồn (cửa sổ thật = vị trí trang + cỡ trang + 1, xem `collect`).
TEAM_HISTORY = 30
GOAL_LIMIT = 40
# 0.191.1: the status dot on an assistant's avatar turns green for a job that finished within this window (seconds),
# reading only the few newest finished jobs of each source.
DONE_FRESH = 24 * 3600
FRESH_WINDOW = 3
# Trần của chính kho Kanban (list_tasks). Việc xong quá hạn tự rời bảng (archived), nên tập còn sống vốn nhỏ.
KANBAN_LIMIT = 5000

_TEAM_BUCKET = {"team_running": "running", "team_queued": "waiting", "team_blocked": "needs_you", "done": "done",
                "cancelled": "done"}
_KANBAN_BUCKET = {"running": "running", "triage": "waiting", "todo": "waiting", "ready": "waiting",
                  "review": "needs_you", "blocked": "needs_you", "done": "done", "cancelled": "done"}
_ORDER = {b: i for i, b in enumerate(("needs_you", "running", "waiting", "done"))}


def _excerpt(text: Any, n: int = RESULT_CHARS) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _uniq(xs: list) -> list:
    return list(dict.fromkeys(x for x in xs if x))


# ───────────── lời giao việc: yêu cầu, tiêu chí xong, kiểm chứng ─────────────
# Đây là chữ đưa cho MODEL (không dịch theo ngôn ngữ giao diện). Kiểu việc bền nằm ở khoá idempotency; các dòng này để
# model đọc, và để đọc ngược được với việc nhóm (việc nhóm không có khoá của mình).
VERIFY_LINE = "Loại việc: Kiểm chứng"
LINK_PREFIX = "Kiểm chứng cho:"
CRITERIA_PREFIX = "Tiêu chí xong:"
_LINK_RE = re.compile(r"^" + re.escape(LINK_PREFIX) + r" .*\(((?:goal|team|kanban):[A-Za-z0-9_-]+)\)\s*$", re.M)
_LINK_TOKEN_RE = re.compile(r"^(goal|team|kanban):([A-Za-z0-9_-]{1,64})$")


def brief(text: str, criteria: str = "", kind: str = "task", link: Optional[dict] = None) -> str:
    """Nội dung việc: yêu cầu trước (việc nhóm lấy đầu tin làm tiêu đề), rồi kiểu việc, mục được kiểm, tiêu chí xong."""
    out = [str(text or "").strip()]
    tail = []
    if kind == "verify":
        tail.append(VERIFY_LINE)
        if link and link.get("id"):
            title = re.sub(r"\s+", " ", str(link.get("title") or "")).strip()[:140] or link["id"]
            tail.append(f"{LINK_PREFIX} {title} ({link['id']})")
    c = str(criteria or "").strip()
    if c:
        tail.append(f"{CRITERIA_PREFIX}\n{c}")
    if tail:
        out.append("\n".join(tail))
    return "\n\n".join(out)


def parse_brief(text: Any) -> dict:
    """{kind, link} đọc ngược từ nội dung việc (việc nhóm)."""
    s = str(text or "")
    kind = "verify" if re.search(r"^" + re.escape(VERIFY_LINE) + r"\s*$", s, re.M) else "task"
    m = _LINK_RE.search(s)
    return {"kind": kind, "link": m.group(1) if m else ""}


def clean_link(token: Any) -> str:
    """Mã mục được kiểm (`goal:<id>`, `team:<id>`, `kanban:<id>`), rỗng nếu không hợp lệ."""
    t = str(token or "").strip()
    return t if _LINK_TOKEN_RE.match(t) else ""


def resolve_link(token: str, root: str, *, tasks=None, goals=None, principal=None) -> Optional[dict]:
    """{id, title, owner_key, open} của mục được kiểm, chỉ trong đúng brain. None khi không còn hay khác brain."""
    m = _LINK_TOKEN_RE.match(str(token or ""))
    if not m:
        return None
    kind, ident = m.group(1), m.group(2)
    try:
        if kind == "goal" and goals is not None:
            g = goals.get(principal, ident)
            if g is None:
                return None
            owner = ""
            try:
                owner = goals.goal_agent_key(principal, ident) or ""
            except Exception:  # noqa: BLE001
                owner = ""
            return {"id": token, "title": _excerpt(getattr(g, "understanding", "") or getattr(g, "request_ref", "")
                                                   or ident, 140),
                    "owner_key": owner,
                    "open": {"kind": "chat", "session_id": getattr(g, "session_id", "") or "", "goal_id": ident}}
        if kind in ("team", "kanban") and tasks is not None:
            t = tasks.get_task(ident)
            if not t or str(t.get("brain_root") or "") != str(root):
                return None
            if (kind == "team") != (t.get("lane") == "team"):
                return None
            if kind == "team":
                return {"id": token, "title": t.get("title") or "", "owner_key": t.get("assignee_key") or "",
                        "open": {"kind": "team", "team_id": t.get("team_id") or "", "task_id": ident}}
            chat = str(t.get("chat_id") or "")
            sid = chat[4:] if chat.startswith("web:") else ""
            return {"id": token, "title": t.get("title") or "", "owner_key": assigned_key(t) or "",
                    "open": {"kind": "chat", "session_id": sid} if sid else {"kind": "work", "task_id": ident}}
    except Exception:  # noqa: BLE001
        return None
    return None


# ───────────── các nguồn ─────────────

def _team_jobs(agent_key: str, root: str, teams, tasks, window: int = TEAM_HISTORY, flags: Optional[dict] = None) -> list:
    out = []
    if teams is None:
        return out
    busy = None
    try:
        busy = teams.busy_of(agent_key)
    except Exception:  # noqa: BLE001
        busy = None
    busy_name = ""
    if busy:
        bt = teams.get(busy.get("team_id")) or {}
        busy_name = bt.get("name") or ""
    for team in teams.teams_of_agent(agent_key):
        if team.get("brain_id") != root:
            continue
        q = tasks.team_queue(team["team_id"])
        waiting_pos = {t["id"]: i + 1 for i, t in enumerate(q.get("waiting") or [])}
        hist = []
        if window > 0:
            hist = list(tasks.team_history(team["team_id"], window + 1))
            if len(hist) > window or len(hist) >= 500:
                hist = hist[:window]
                if flags is not None:
                    flags["done_more"] = True
        rows = list(q.get("running") or []) + list(q.get("waiting") or []) + list(q.get("blocked") or []) + hist
        for task in rows:
            steps = teams.steps(task["id"])
            mine = [s for s in steps if s.get("agent_key") == agent_key]
            verify = parse_brief(task.get("intent")) if task.get("assignee_key") == agent_key else {"kind": "task"}
            roles = []
            if task.get("coordinator_key") == agent_key or any(s["kind"] in ("plan", "synthesize") for s in mine):
                roles.append("coordinator")
            if task.get("assignee_key") == agent_key or any(s["kind"] == "work" for s in mine):
                roles.append("verifier" if verify["kind"] == "verify" else "worker")
            if any(s["kind"] == "help" for s in mine):
                roles.append("helper")
            roles = _uniq(roles)
            if not roles:
                continue
            live_steps = [s for s in steps if s.get("status") != "cancelled"]
            st = str(task.get("status") or "")
            name = team.get("name") or ""
            reason = _excerpt(task.get("block_reason"), 200) if st == "team_blocked" else ""
            nxt = None
            if st == "team_queued":
                if busy and busy.get("team_id") != team["team_id"]:
                    nxt = {"code": "busy", "team": busy_name}
                else:
                    nxt = {"code": "queue", "n": waiting_pos.get(task["id"]), "team": name}
            elif st == "team_blocked":
                nxt = {"code": "needs_you", "reason": reason}
            live = st in ("team_queued", "team_running", "team_blocked")
            out.append({
                "id": f"team:{task['id']}", "source": "team", "source_id": team["team_id"],
                "source_label": name, "title": task.get("title") or "", "status": st,
                "bucket": _TEAM_BUCKET.get(st, "waiting"), "roles": roles, "kind": verify["kind"],
                "link_token": verify.get("link") or "",
                "progress": {"done": sum(1 for s in live_steps if s.get("status") == "done"), "total": len(live_steps)},
                "my_steps": [{"kind": s["kind"], "status": s["status"]} for s in mine],
                "result": _excerpt(task.get("result")) if st == "done" else "",
                "reason": reason, "next": nxt,
                "queue_pos": waiting_pos.get(task["id"]), "cancelled": st == "cancelled",
                "updated_at": float(task.get("updated_at") or 0),
                "open": {"kind": "team", "team_id": team["team_id"], "task_id": task["id"]},
                "cancel": {"kind": "team", "team_id": team["team_id"], "task_id": task["id"]} if live else None,
                # Ưu tiên trong hàng của nhóm: route gốc của nhóm, CAS theo phiên bản hàng đợi.
                "priority": {"kind": "team", "team_id": team["team_id"], "task_id": task["id"],
                             "on": task.get("team_prio") is None, "version": int(q.get("version") or 0)}
                if st in ("team_queued", "team_blocked") else None,
            })
    return out


def _chat_sessions(agent_key: str, slug: str, brain_keys: Any, sessions, goals) -> dict:
    """{session_id: tiêu đề} các phiên chat riêng thuộc ĐÚNG mã này: phiên đã ghim mã khác (trợ lý cũ cùng slug) bị
    loại; phiên chưa ghim thì nhận theo slug (chưa có lượt nào gắn mã)."""
    out = {}
    if sessions is None or not slug:
        return out
    rows = sessions.list_sessions(limit=200, brain=brain_keys, include_archived=True, channel=f"agent:{slug}")
    pins: dict = {}
    if goals is not None and rows:
        # Một lần đọc cho mọi phiên (review trước phát hành 0.142.0): đọc từng phiên mở hàng trăm kết nối.
        try:
            if hasattr(goals, "session_pins"):
                pins = goals.session_pins([s["id"] for s in rows])
            else:
                pins = {s["id"]: (goals.session_pin(s["id"]) or {}).get("agent_key") for s in rows}
        except Exception:  # noqa: BLE001
            pins = {}
    for s in rows:
        pin = pins.get(s["id"])
        if pin and pin != agent_key:
            continue
        out[s["id"]] = s.get("title") or ""
    return out


def report_session(agent_key: str, slug: str, brain_keys: Any, sessions, goals) -> Optional[str]:
    """Phiên chat riêng nhận báo cáo của việc giao bằng nút Giao việc: phiên CHƯA lưu trữ của đúng mã này, ưu tiên phiên đã
    có tin (phiên trống là phiên trang tạo sẵn khi bấm vào trợ lý). Không có thì None, người gọi mở phiên mới."""
    if sessions is None or not slug:
        return None
    rows = sessions.list_sessions(limit=50, brain=brain_keys, channel=f"agent:{slug}")
    pins: dict = {}
    if goals is not None and rows and hasattr(goals, "session_pins"):
        try:
            pins = goals.session_pins([r["id"] for r in rows])
        except Exception:  # noqa: BLE001
            pins = {}
    mine = [r for r in rows if not pins.get(r["id"]) or pins.get(r["id"]) == agent_key]
    with_msgs = [r for r in mine if int(r.get("msg_count") or 0) > 0]
    pick = (with_msgs or mine or [None])[0]
    return pick["id"] if pick else None


def _kanban_jobs(agent_key: str, slug: str, root: str, brain_keys: Any, tasks, sessions, goals,
                 history: bool = True, rows: Optional[list] = None) -> list:
    out = []
    chats = _chat_sessions(agent_key, slug, brain_keys, sessions, goals)
    board_off = False
    try:
        board_off = tasks.board_mode(root) == "off"
    except Exception:  # noqa: BLE001
        pass
    if rows is None:
        rows = tasks.list_tasks(root, include_archived=False, limit=KANBAN_LIMIT)
    # Mỗi trợ lý chạy MỘT việc giao trực tiếp một lúc (task_store.next_candidate): việc chờ sau một việc đang chạy của
    # cùng trợ lý thì nói rõ là đang chờ việc kia.
    busy = bool(agent_key) and any(assigned_key(t) == agent_key and t.get("status") == "running" for t in rows)
    for task in rows:
        chat = str(task.get("chat_id") or "")
        sid = chat[4:] if chat.startswith("web:") else ""
        info = parse_assign(task.get("idempotency_key"))
        # Việc giao bằng nút Giao việc mang mã trợ lý trong khoá idempotency (metadata bị ghi đè khi việc chạy xong);
        # việc xếp từ chat riêng nhận theo phiên đã ghim đúng mã.
        if info is not None:
            if info["agent_key"] != agent_key:
                continue
        elif not (sid and sid in chats):
            continue
        st = str(task.get("status") or "")
        bucket = _KANBAN_BUCKET.get(st, "waiting")
        if st == "done" and "[[NEEDS_INPUT]]" in str(task.get("result") or ""):
            bucket = "needs_you"
        if not history and bucket == "done":
            continue
        reason = _excerpt(task.get("block_reason") or (task.get("result") if bucket == "needs_you" else ""), 200) \
            if bucket == "needs_you" else ""
        nxt = None
        if bucket == "waiting":
            if board_off:
                nxt = {"code": "board_off"}
            elif info is not None and busy:
                nxt = {"code": "agent_busy"}
            else:
                nxt = {"code": "queued"}
        elif bucket == "needs_you":
            nxt = {"code": "needs_you", "reason": reason}
        kind = info["kind"] if info else "task"
        out.append({
            "id": f"kanban:{task['id']}", "source": "chat", "source_id": sid,
            "source_label": chats.get(sid, ""), "title": task.get("title") or "", "status": st, "bucket": bucket,
            "roles": ["verifier" if kind == "verify" else "worker"], "kind": kind,
            "link_token": (info or {}).get("link") or "", "progress": None, "my_steps": [],
            "result": _excerpt(task.get("result")) if st in ("done", "review") else "",
            "reason": reason, "next": nxt,
            "queue_pos": None, "board_off": bool(board_off and bucket == "waiting"), "cancelled": st == "cancelled",
            "updated_at": float(task.get("updated_at") or 0),
            "open": {"kind": "chat", "session_id": sid} if sid else {"kind": "work", "task_id": task["id"]},
            "cancel": {"kind": "kanban", "task_id": task["id"]} if st not in ("done", "cancelled", "archived") else None,
            # Kanban chưa có route sửa ưu tiên: không bày nút giả.
            "priority": None,
        })
    return out


def _auto_jobs(agent_key: str, goals, principal, window: int = GOAL_LIMIT, flags: Optional[dict] = None) -> list:
    out = []
    if goals is None:
        return out
    rows = goals.agent_goal_rows(principal, agent_key, max(0, window) + 1)
    done_rows = [g for g in rows if str(g.get("status") or "") != "active"]
    if len(done_rows) > window:
        cut = set(g["id"] for g in done_rows[window:])
        rows = [g for g in rows if g["id"] not in cut]
        if flags is not None:
            flags["done_more"] = True
    for g in rows:
        st, rs = str(g.get("status") or ""), str(g.get("run_state") or "")
        legacy = g.get("role") == "reviewer"
        paused = bool(g.get("paused"))
        if st == "active":
            bucket = "needs_you" if (rs == "blocked" or paused) else "running" if rs == "running" else "waiting"
        else:
            bucket = "done"
        reason = str(g.get("block_reason") or "") if bucket == "needs_you" else ""
        nxt = None
        if st == "active" and paused and not legacy:
            nxt = {"code": "resume"}
        elif bucket == "needs_you":
            nxt = {"code": "needs_you", "reason": reason}
        rev = int(g.get("revision") or 0)
        out.append({
            "id": f"goal:{g['id']}", "source": "auto", "source_id": g.get("session_id") or "",
            "source_label": "", "title": _excerpt(g.get("understanding") or g.get("request_ref") or g["id"], 140),
            "status": st, "run_state": rs, "bucket": bucket, "roles": ["verifier_legacy" if legacy else "worker"],
            "kind": "task", "link_token": "", "progress": None,
            "my_steps": [], "result": "", "reason": reason, "next": nxt,
            "reason_code": str(g.get("reason_code") or ""), "revision": rev,
            "queue_pos": None, "cancelled": st == "cancelled", "failed": st == "failed",
            "updated_at": float(g.get("updated_at") or 0),
            "open": {"kind": "chat", "session_id": g.get("session_id") or "", "goal_id": g["id"]},
            "cancel": {"kind": "goal", "goal_id": g["id"], "revision": rev} if st == "active" and not legacy else None,
            # Tiếp tục: lệnh `resume` của mục tiêu (route gốc), gửi kèm revision đang hiện.
            "resume": {"goal_id": g["id"], "revision": rev} if st == "active" and paused and not legacy else None,
            "priority": None,
        })
    return out


def _cursor(cursor: Any) -> int:
    try:
        return max(0, int(str(cursor or "0")))
    except (TypeError, ValueError):
        return 0


def collect(agent_key: str, slug: str, root: str, *, brain_keys: Any = None, teams=None, tasks=None, sessions=None,
            goals=None, principal=None, now: Optional[float] = None, source: str = "all", bucket: str = "",
            cursor: Any = None, limit: int = PAGE, history: bool = True, kanban_rows: Optional[list] = None,
            resolve: bool = True, done_since: float = 0, marks: Optional[dict] = None) -> dict:
    """Một trang việc của một trợ lý.

    Trả {"jobs": trang, "counts": {ngăn: số} theo nguồn đang lọc, "source_counts": {nguồn: số}, "total", "next": cursor
    trang sau hay None, "counts_partial": {"done": bool}, "errors"}. Mỗi nguồn hỏng không làm mất nguồn khác: nguồn lỗi
    được ghi trong `errors` để giao diện nói rõ thiếu phần nào thay vì im lặng.

    `history=False`: bỏ việc đã xong (đếm nhẹ cho huy hiệu trên thẻ trợ lý). Thêm `done_since` thì giữ lại việc xong từ
    mốc đó (chỉ đọc vài việc xong mới nhất mỗi nguồn), cho chấm xanh "vừa xong"."""
    src = source if source in SOURCES else "all"
    want = bucket if bucket in BUCKETS else ""
    offset = _cursor(cursor)
    limit = max(1, min(MAX_PAGE, int(limit or PAGE)))
    # Lịch sử đọc theo cửa sổ vừa đủ cho trang này: việc đã xong luôn xếp cuối, nên mỗi nguồn chỉ cần tối đa
    # offset + limit + 1 việc đã xong mới nhất để trang đúng và biết còn trang sau.
    window = offset + limit + 1 if history else 0
    fresh = FRESH_WINDOW if (done_since and not history) else 0
    flags: dict = {}
    jobs, errors = [], []
    for name, fn in (("team", lambda: _team_jobs(agent_key, root, teams, tasks, max(window, TEAM_HISTORY if history
                                                                                     else fresh), flags)),
                     ("chat", lambda: _kanban_jobs(agent_key, slug, root, brain_keys, tasks, sessions, goals,
                                                   history or bool(fresh), kanban_rows)),
                     ("auto", lambda: _auto_jobs(agent_key, goals, principal, max(window, GOAL_LIMIT if history
                                                                                  else fresh), flags))):
        try:
            jobs += fn()
        except Exception as ex:  # noqa: BLE001
            errors.append({"source": name, "error": f"{type(ex).__name__}: {str(ex)[:200]}"})
    if not history:
        jobs = [j for j in jobs if j["bucket"] != "done" or (done_since and not j.get("cancelled")
                                                              and (j.get("updated_at") or 0) >= done_since)]
    archived: list = []
    if marks is not None:
        # 0.193.0: finished jobs the owner pressed Done on go to the archive list; deleted ones are not shown.
        import job_marks
        jobs, archived = job_marks.split(jobs, marks)
    source_counts = {s: sum(1 for j in jobs if j["source"] == s) for s in SOURCES}
    if src != "all":
        jobs = [j for j in jobs if j["source"] == src]
    counts = {b: sum(1 for j in jobs if j["bucket"] == b) for b in BUCKETS}
    failed = sum(1 for j in jobs if j["bucket"] == "done" and j.get("failed")) if done_since else 0
    if want:
        jobs = [j for j in jobs if j["bucket"] == want]
    jobs.sort(key=lambda j: (_ORDER.get(j["bucket"], 9), -(j.get("updated_at") or 0), j["id"]))
    total = len(jobs)
    page = jobs[offset: offset + limit]
    if resolve:
        for j in page:
            tok = j.get("link_token")
            if tok:
                j["link"] = resolve_link(tok, root, tasks=tasks, goals=goals, principal=principal) or \
                    {"id": tok, "title": "", "open": None, "missing": True}
    nxt = str(offset + limit) if offset + limit < total else None
    out = {"jobs": page, "counts": counts, "source_counts": source_counts, "total": total, "next": nxt,
           "counts_partial": {"done": bool(flags.get("done_more"))}, "errors": errors,
           "at": now if now is not None else time.time()}
    if done_since:
        out["failed_recent"] = failed
    if marks is not None:
        out["archived"] = archived
    return out


def active_counts(agents: dict, root: str, *, brain_keys: Any = None, teams=None, tasks=None, sessions=None, goals=None,
                  principal=None, now: Optional[float] = None) -> dict:
    """{slug: {"running", "needs_you", "waiting", "done", "failed"}} cho huy hiệu và chấm trạng thái trên thẻ trợ lý;
    "done" và "failed" chỉ đếm việc xong (hay hỏng) trong DONE_FRESH giây gần nhất. Nhẹ: đọc Kanban một lần cho cả brain, mỗi nguồn chỉ vài việc xong mới nhất.
    Trợ lý không có việc nào thì không có mặt. `agents`: {slug: agent_key hay ""}."""
    since = (now if now is not None else time.time()) - DONE_FRESH
    rows = tasks.list_tasks(root, include_archived=False, limit=KANBAN_LIMIT) if tasks is not None else []
    live = [t for t in rows if t.get("status") not in ("done", "cancelled", "archived")
            or "[[NEEDS_INPUT]]" in str(t.get("result") or "")
            or (t.get("status") == "done" and float(t.get("updated_at") or 0) >= since)]
    out = {}
    for slug, key in agents.items():
        got = collect(key or "", slug, root, brain_keys=brain_keys, teams=teams if key else None, tasks=tasks,
                      sessions=sessions, goals=goals if key else None, principal=principal, history=False,
                      kanban_rows=live, limit=1, resolve=False, done_since=since)
        c, failed = got["counts"], int(got.get("failed_recent") or 0)
        if c["running"] or c["needs_you"] or c["waiting"] or c["done"]:
            out[slug] = {"running": c["running"], "needs_you": c["needs_you"], "waiting": c["waiting"],
                         "done": c["done"] - failed, "failed": failed}
    return out


def verify_targets(agents: dict, exclude_slug: str, root: str, *, names: Optional[dict] = None, brain_keys: Any = None,
                   teams=None, tasks=None, sessions=None, goals=None, principal=None, per_agent: int = 10,
                   limit: int = 30) -> list:
    """Việc gần đây của các trợ lý KHÁC trong brain (để chọn mục cần kiểm chứng). Việc người kiểm đang tham gia thì bỏ."""
    rows = tasks.list_tasks(root, include_archived=False, limit=KANBAN_LIMIT) if tasks is not None else []
    mine = set()
    ex_key = agents.get(exclude_slug) or ""
    if exclude_slug in agents:
        got = collect(ex_key, exclude_slug, root, brain_keys=brain_keys, teams=teams if ex_key else None, tasks=tasks,
                      sessions=sessions, goals=goals if ex_key else None, principal=principal, kanban_rows=rows,
                      limit=MAX_PAGE, resolve=False)
        mine = {j["id"] for j in got["jobs"]}
    seen, out = set(), []
    for slug, key in agents.items():
        if slug == exclude_slug:
            continue
        got = collect(key or "", slug, root, brain_keys=brain_keys, teams=teams if key else None, tasks=tasks,
                      sessions=sessions, goals=goals if key else None, principal=principal, kanban_rows=rows,
                      limit=per_agent, resolve=False)
        for j in got["jobs"]:
            if j["id"] in seen or j["id"] in mine or j.get("kind") == "verify":
                continue
            seen.add(j["id"])
            out.append({"id": j["id"], "title": j["title"], "slug": slug, "name": (names or {}).get(slug) or slug,
                        "bucket": j["bucket"], "source": j["source"], "updated_at": j.get("updated_at") or 0})
    out.sort(key=lambda x: -(x["updated_at"] or 0))
    return out[:max(1, int(limit))]


# ───────────── khoá của việc giao trực tiếp ─────────────
ASSIGN_PREFIX = "agent:"


def assign_key(agent_key: str, slug: str, nonce: str, kind: str = "task", link: str = "") -> str:
    """Khoá idempotency của việc giao cho trợ lý: `agent:<mã>:<slug>:<nonce>`, việc kiểm chứng
    `agent:<mã>:<slug>:v:<nonce>` hay `agent:<mã>:<slug>:v:<loại>.<id>:<nonce>` khi có mục được kiểm. Bền suốt đời việc
    (metadata và cả nội dung việc có thể bị viết lại khi chạy), nên vừa là dấu "việc của ai, kiểu gì, kiểm cái gì" vừa
    chống gửi trùng khi bấm hai lần hay gửi lại sau rớt mạng."""
    n = clean_nonce(nonce)
    if not n:
        raise ValueError("nonce rỗng sau khi lọc")
    if kind == "verify":
        lk = clean_link(link)
        mid = "v:" + (lk.replace(":", ".", 1) + ":" if lk else "")
        return f"{ASSIGN_PREFIX}{agent_key}:{slug}:{mid}{n}"
    return f"{ASSIGN_PREFIX}{agent_key}:{slug}:{n}"


def clean_nonce(nonce: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(nonce or ""))[:64]


def parse_assign(key: Any) -> Optional[dict]:
    """{agent_key, slug, kind, link, nonce} từ khoá của việc giao cho trợ lý, None nếu không phải."""
    k = str(key or "")
    if not k.startswith(ASSIGN_PREFIX):
        return None
    parts = k[len(ASSIGN_PREFIX):].split(":")
    if len(parts) < 3 or not parts[0] or not parts[1]:
        return None
    kind, link = "task", ""
    if len(parts) >= 4 and parts[2] == "v":
        kind = "verify"
        if len(parts) >= 5 and "." in parts[3]:
            link = clean_link(parts[3].replace(".", ":", 1))
    return {"agent_key": parts[0], "slug": parts[1], "kind": kind, "link": link, "nonce": parts[-1]}


def parse_assign_key(key: Any) -> Optional[tuple]:
    """(agent_key, slug) từ khoá của việc giao cho trợ lý, None nếu không phải."""
    got = parse_assign(key)
    return (got["agent_key"], got["slug"]) if got else None


def assigned_key(task: dict) -> Optional[str]:
    got = parse_assign(task.get("idempotency_key"))
    return got["agent_key"] if got else None


def assign_title(agent_name: str, text: str) -> str:
    """Tiêu đề việc giao cho trợ lý. Kanban gộp việc đang mở CÙNG tiêu đề trong một brain, nên tên trợ lý đi kèm để
    "Viết bài" giao cho hai trợ lý khác nhau vẫn là hai việc (trên bảng Việc cũng đọc ra ngay ai làm)."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return f"{t[:120]} · {str(agent_name or '').strip()[:40]}".strip(" ·")
