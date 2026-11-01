"""Javis Core giao việc cho một nhóm có sẵn rồi báo kết quả về đúng chỗ đã giao (0.357.0, issue #826).

Chủ nói với Javis Core (web chat, Telegram, Zalo...) một mục tiêu; Core chọn nhóm và gọi `javis_team` op=dispatch. Việc đi
đúng đường của trang Nhóm: một tin giao việc trong khung chat nhóm (`TeamRunner.submit`, `as_job`), nên hàng đợi, trưởng
nhóm điều phối, nghiệm thu và lịch sử là của nhóm như khi chủ tự gõ. Không có bộ điều phối hay kho thứ hai.

Luật
====
- Chỉ chủ (lượt có `la_chu`) hay việc nền chủ đã lên lịch (nhắc hẹn, việc Kanban) được giao. Một bước việc nhóm không được
  mở việc ở nhóm (tránh vòng nhóm tự giao cho nhau). Nhóm phải thuộc đúng brain của lượt (`_find_team` của plugin).
- Không đụng cổng duyệt: việc đòi chủ xác nhận nghiệm thu hay duyệt thao tác vẫn dừng ở thẻ của chủ; Core chỉ BÁO.
- Chống giao trùng: mã đối chiếu (`correlation_id`) thành `client_msg_id` của tin giao việc. Gửi lại cùng mã trả đúng việc
  cũ, không tạo việc thứ hai.
- Nơi báo lấy từ lượt đang chạy, không nhận từ model: một mã phiên gõ sai không làm kết quả của nhóm lọt sang khung chat
  hay brain khác.
- Báo về khi việc xong, bị huỷ, hay dừng chờ chủ (một lần cho mỗi trạng thái), qua `_notify_owner` nên luôn có một bản
  trong hòm thư. XONG và ĐẠT là hai chuyện: tin báo nói rõ việc đã qua nghiệm thu hay chưa.
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Optional

import localefmt

TEXT_MAX = 8000          # mục tiêu giao cho nhóm, ký tự
RESULT_SHOWN = 1500      # phần kết quả kèm trong tin báo
WATCH_LIMIT = 200
SCHEDULED = ("reminder", "kanban")   # việc nền chủ đã lên lịch: được giao việc cho nhóm như chủ
NO_TURN_BUCKET_S = 1800  # kênh không có mã tin: gửi lại cùng mục tiêu trong 30 phút coi là cùng một lần giao


class DispatchError(Exception):
    pass


def _s(v) -> str:
    return str(v or "").strip()


def check_caller(turn: Optional[dict]) -> dict:
    """Người giao việc phải là chủ (hay việc nền chủ đã lên lịch). Trả lượt đó, sai thì `DispatchError`."""
    if not turn:
        raise DispatchError("không rõ ai đang giao việc (lượt không có danh tính), nên không giao việc cho nhóm. "
                            "Chủ giao ở trang Nhóm trên dashboard.")
    if turn.get("kenh") == "team" or turn.get("team_gate"):
        raise DispatchError("một bước việc của nhóm không được mở việc ở nhóm. Chỉ chủ hay Javis Core giao việc cho nhóm.")
    if not turn.get("la_chu") and turn.get("kenh") not in SCHEDULED:
        raise DispatchError("chỉ chủ mới giao việc cho nhóm được.")
    return turn


def report_to(turn: dict) -> str:
    """Nơi báo kết quả, theo đúng định dạng `owner_chat` của việc nền: web:<phiên> cho dashboard, còn lại là chat_id của
    lượt (kênh nhắn đã gắn tiền tố zalo:, slack:...; việc nền mang sẵn nơi báo của nó). Rỗng: Javis Core và hòm thư."""
    if turn.get("kenh") == "dashboard":
        sid = _s(turn.get("session_id") or turn.get("chat_id"))
        return f"web:{sid}" if sid else ""
    chat = _s(turn.get("chat_id"))
    return "" if chat in ("", "default") else chat


def correlation(turn: dict, team_id: str, objective: str, given: str = "", now: Optional[float] = None) -> str:
    """Mã đối chiếu xuyên Core -> nhóm -> Core. Model đưa thì dùng đúng mã đó; không thì suy từ lượt, nên cùng một lượt
    gọi lại (thử lại sau lỗi mạng) ra cùng mã."""
    given = re.sub(r"[^A-Za-z0-9_.:-]", "", _s(given))[:80]
    if given:
        return given
    h = hashlib.sha1(f"{team_id}\n{_s(objective)}".encode("utf-8")).hexdigest()[:10]
    if turn.get("session_id") and turn.get("message_id"):
        return f"c-{_s(turn['session_id'])[-16:]}-{int(turn['message_id'])}-{h}"
    if turn.get("job"):
        return f"c-{re.sub(r'[^A-Za-z0-9_.:-]', '', _s(turn['job']))[-48:]}-{h}"
    bucket = int((time.time() if now is None else now) // NO_TURN_BUCKET_S)
    chat = hashlib.sha1(_s(turn.get("chat_id")).encode("utf-8")).hexdigest()[:8]
    return f"c-{chat}-{bucket}-{h}"


def dispatch(ops, root: str, team: dict, objective: str, turn: dict, assignee: str = "", request_id: str = "") -> dict:
    """Giao MỘT việc cho nhóm `team`. Kiểm hết TRƯỚC khi tạo việc. Trả {task_id, correlation_id, created, task, report_to,
    quality, paused}."""
    objective = _s(objective)
    if not objective:
        raise DispatchError("thiếu objective (việc cần nhóm làm).")
    if len(objective) > TEXT_MAX:
        raise DispatchError(f"objective dài quá {TEXT_MAX} ký tự; tóm lại, phần chi tiết để trong file của brain.")
    if team["status"] == "archived":
        raise DispatchError(f"nhóm '{team['name']}' đã lưu trữ. Chỉ khi chủ muốn thì mở lại (op=unarchive) rồi giao.")
    mentions = []
    if _s(assignee):
        key = ops.member_key(team, assignee)
        if not ops.api.teams().is_active_member(team["team_id"], key):
            raise DispatchError(f"'{assignee}' không còn trong nhóm '{team['name']}'. Dùng op=get để xem thành viên.")
        mentions = [key]
    elif not team.get("leader_key"):
        raise DispatchError(f"nhóm '{team['name']}' chưa có trưởng nhóm để nhận việc. Truyền assignee (slug một thành "
                            "viên), hoặc đặt trưởng nhóm trước (op=set_leader).")
    cid = correlation(turn, team["team_id"], objective, request_id)
    dest = report_to(turn)
    runner = ops.api.runner()
    sub = runner.submit(team["team_id"], objective, mentions=mentions, as_job=True, client_msg_id=f"core:{cid}",
                        via={"correlation_id": cid, "kenh": turn.get("kenh")})
    task_id = sub.get("task_id")
    if not task_id:
        raise DispatchError("nhóm không nhận việc (không tạo được việc).")
    store = ops.deps.task_store()
    store.team_core_mark(task_id, {"correlation_id": cid, "report_to": dest, "kenh": _s(turn.get("kenh")),
                                   "brain": root, "at": time.time()})
    if sub.get("created"):
        ops.api.kick()
    task = store.get_task(task_id) or {}
    return {"task_id": task_id, "correlation_id": cid, "created": bool(sub.get("created")), "task": task,
            "report_to": ((task.get("metadata") or {}).get("core") or {}).get("report_to", dest),
            "quality": bool(runner.quality.policy(team["team_id"]).get("enabled")) if runner.quality else False,
            "paused": team["status"] != "active"}


def find(ops, team: dict, ref: str) -> dict:
    """Việc của nhóm theo mã việc (t_...) hay mã đối chiếu."""
    ref = _s(ref)
    if not ref:
        raise DispatchError("thiếu task (mã việc t_... hay mã đối chiếu).")
    store = ops.deps.task_store()
    task = store.get_task(ref)
    if not task:
        task = store.team_core_find(team["team_id"], ref)
    if not task or task.get("lane") != "team" or task.get("team_id") != team["team_id"]:
        raise DispatchError(f"không có việc '{ref}' trong nhóm '{team['name']}'.")
    return task


# ───────────── trạng thái và tin báo ─────────────

_OWNER_BLOCKS = ("waiting_user", "acceptance_review", "approval_expired", "rejected")


def verdict(acc: Optional[dict]) -> str:
    """'pass' (qua nghiệm thu thật), 'pending' (có hợp đồng nhưng chưa đạt), 'none' (nhóm không bật nghiệm thu)."""
    if not acc:
        return "none"
    return "pass" if acc.get("completion_valid") else "pending"


def phase(task: dict, acc: Optional[dict], team: Optional[dict] = None) -> tuple:
    """(mã trạng thái, câu cho người đọc, có báo về không, đã kết thúc chưa)."""
    st, kind = _s(task.get("status")), _s(task.get("block_kind"))
    reason = _s(task.get("block_reason"))[:300]
    if st == "done":
        v = verdict(acc)
        if v == "pass":
            return "done_pass", localefmt.chu("XONG và ĐẠT nghiệm thu.", "DONE and PASSED acceptance."), True, True
        if v == "pending":
            return "done_unverified", localefmt.chu(
                "Nhóm báo xong, nhưng nghiệm thu CHƯA xác nhận đạt.",
                "The team reports done, but acceptance has NOT confirmed a pass."), True, True
        return "done", localefmt.chu(
            "Nhóm báo xong (nhóm này không bật nghiệm thu, nên chưa có ai xác nhận đạt).",
            "The team reports done (this team has no acceptance check, so nobody confirmed a pass)."), True, True
    if st == "cancelled":
        return "cancelled", localefmt.chu("Đã huỷ: {r}", "Cancelled: {r}", r=reason or "-"), True, True
    if st == "team_blocked":
        if kind == "auto_retry":
            # 0.436.0: a temporary error; the team runs the step again on its own. Not worth a report to Core.
            return "retrying", localefmt.chu("Gặp lỗi tạm thời, nhóm sẽ tự chạy lại: {r}",
                                             "Hit a temporary error, the team will retry on its own: {r}",
                                             r=reason or "-"), False, False
        if kind == "acceptance_checking":
            return "checking", localefmt.chu("Đang kiểm nghiệm thu.", "Acceptance check running."), False, False
        if kind == "acceptance_failed":
            return "acceptance_failed", localefmt.chu(
                "Nghiệm thu KHÔNG đạt, việc dừng: {r}", "Acceptance FAILED, the job stopped: {r}", r=reason or "-"), True, False
        if kind in _OWNER_BLOCKS or "approval" in kind:
            return "needs_owner", localefmt.chu(
                "Đang chờ chủ quyết trên thẻ việc ở trang Nhóm (Javis không tự duyệt thay): {r}",
                "Waiting for the owner on the job card in Teams (Javis never approves for you): {r}", r=reason or kind), True, False
        return "blocked", localefmt.chu("Việc bị chặn ({k}): {r}", "The job is blocked ({k}): {r}", k=kind or "-",
                                        r=reason or "-"), True, False
    if st == "team_running":
        return "running", localefmt.chu("Nhóm đang làm.", "The team is working on it."), False, False
    if team and team.get("status") == "paused":
        return "queued", localefmt.chu("Đang nằm chờ: nhóm đang tạm dừng.", "Waiting: the team is paused."), False, False
    return "queued", localefmt.chu("Đang chờ tới lượt.", "Waiting for its turn."), False, False


def view(ops, team: dict, task: dict) -> dict:
    acc = ops.api.runner().acceptance_view(team, task["id"])
    code, line, _, _ = phase(task, acc, team)
    core = (task.get("metadata") or {}).get("core") or {}
    steps = []
    try:
        steps = [{"agent_key": x.get("agent_key") or "", "kind": x.get("kind") or "", "status": x.get("status") or ""}
                 for x in ops.api.teams().steps(task["id"])][:20]
    except Exception:  # noqa: BLE001 - một danh sách bước hỏng không che việc
        steps = []
    return {"task_id": task["id"], "title": task.get("title") or "", "status": task.get("status") or "",
            "block_kind": task.get("block_kind") or "", "phase": code, "line": line,
            "verdict": verdict(acc), "acceptance_status": (acc or {}).get("status") or "",
            "correlation_id": core.get("correlation_id") or "", "result": _s(task.get("result")),
            "steps": steps, "team": team["name"]}


def report_text(team: dict, task: dict, line: str) -> tuple:
    """(bản đủ cho khung chat web và hòm thư, bản gọn cho Telegram/Zalo)."""
    cid = ((task.get("metadata") or {}).get("core") or {}).get("correlation_id") or ""
    head = localefmt.chu('Nhóm {n} báo về việc "{t}" (mã {i}):', 'Team {n} on the job "{t}" ({i}):',
                         n=team["name"], t=task.get("title") or "", i=task["id"])
    result = _s(task.get("result"))
    tail = localefmt.chu("Xem đủ ở trang Nhóm, nhóm {n}, tab Việc. Mã đối chiếu: {c}.",
                         "Full detail on the Teams page, team {n}, Jobs tab. Correlation id: {c}.", n=team["name"], c=cid)
    full = "\n".join([head, line] + ([""] + [result[:RESULT_SHOWN] + ("…" if len(result) > RESULT_SHOWN else "")]
                                     if result and task.get("status") == "done" else []) + ["", tail])
    short = "\n".join([head, line] + ([result[:400] + ("…" if len(result) > 400 else "")]
                                      if result and task.get("status") == "done" else []))
    return full, short


def due_reports(api) -> list:
    """Những tin cần báo về Core lúc này: mỗi việc do Core mở, một tin cho mỗi trạng thái đáng báo chưa báo. Chạy ở luồng
    phụ (vòng nhóm)."""
    store = api.deps.task_store()
    out = []
    for task in store.team_core_watch(WATCH_LIMIT):
        team = api.teams().get(task.get("team_id") or "")
        if not team:
            store.team_core_said(task["id"], "team_gone", closed=True)
            continue
        acc = api.runner().acceptance_view(team, task["id"])
        code, line, worth, final = phase(task, acc, team)
        key = f"{code}:{task.get('block_kind') or ''}:{task.get('team_rev') or 0}"
        meta = task.get("metadata") or {}
        if not worth or meta.get("core_said") == key:
            continue
        core = meta.get("core") or {}
        full, short = report_text(team, task, line)
        out.append({"task_id": task["id"], "key": key, "closed": final, "report_to": core.get("report_to") or "",
                    "brain": core.get("brain") or team.get("brain_id") or "", "text": full, "short": short,
                    "dedup": f"teamcore:{task['id']}:{key}"})
    return out
