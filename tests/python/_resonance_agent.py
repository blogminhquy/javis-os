"""Helper chung cho test Resonance từ A1: bật Cộng hưởng theo AGENT thay cho công tắc brain cũ.

Test M1 đến M5 trước A1 bật bằng `<brain>/Javis/resonance.json`. Từ A1 công tắc đó không cấp quyền gì; mục tiêu phải
thuộc một agent đang bật. Các helper dưới đây làm đúng việc chủ dự án làm qua host (tạo file agent, bật, gán mục
tiêu, tắt) để nội dung kiểm của test cũ giữ nguyên.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

import luot_dang_chay
import resonance_store as RS
import turn_context

SLUG = "tro-ly-thu"


def owner(brain) -> RS.Principal:
    return RS.Principal("owner", "owner", str(Path(brain).resolve()))


def enable(store, brain, slug: str = SLUG) -> dict:
    """Tạo file agent (nếu chưa có) rồi bật Cộng hưởng cho nó như chủ dự án bật. Trả dòng sổ đăng ký."""
    d = Path(brain) / "agents"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{slug}.md"
    if not f.exists():
        f.write_text(f"---\nname: {slug}\n---\nTrợ lý thử {slug}\n", encoding="utf-8", newline="\n")
    return store.agent_set_enabled(owner(brain), slug, True)


def disable(store, brain, slug: str = SLUG):
    return store.agent_set_enabled(owner(brain), slug, False)


def assign(store, brain, goal_id: str, agent_key: str):
    """Gán một mục tiêu chưa gán cho agent (đường của chủ dự án, CAS theo revision hiện tại)."""
    g = store.get(owner(brain), goal_id)
    return store.assign_goal(owner(brain), goal_id, agent_key, g.revision)


def ctx(agent: dict) -> dict:
    """Phần context cho `form_goal`/`revise_goal` gắn mục tiêu vào agent."""
    return {"agent_key": agent["agent_key"], "agent_version": agent["config_version"]}


@contextlib.contextmanager
def turn(agent: dict, session_id: str, message_id: int, user_text: str, brain, slug: str = SLUG, store=None,
         seq=None):
    """Một lượt chat của agent như run_turn dựng: ngữ cảnh lượt có agent và sổ lượt có lời người dùng."""
    # A4: như main.run_turn, lượt có trợ lý chụp thứ tự quyền của kho TRƯỚC khi engine chạy.
    if seq is None:
        seq = (store or RS.GoalStore()).authority_seq()
    tok = turn_context.bind(turn_context.make(
        "dashboard", chat_id=session_id, la_chu=True, session_id=session_id, message_id=message_id,
        agent={"key": agent["agent_key"], "slug": slug, "config_version": agent["config_version"]},
        authority_seq=seq))
    k = luot_dang_chay.bat_dau(f"web:{session_id}", brain, msg_id=message_id, user_text=user_text)
    try:
        yield
    finally:
        luot_dang_chay.ket_thuc(k)
        turn_context.reset(tok)


def pin(store, brain, slug: str = SLUG) -> dict:
    """Mã và version HIỆN TẠI của trợ lý, như host ghim vào ý định hành động hay phép thử (A1, review tích hợp P1-3).
    Mục tiêu thuộc trợ lý thì mọi begin_action/begin_experiment phải mang nó."""
    a = store.agent(str(Path(brain).resolve()), slug) or store.agent(str(brain), slug)
    return {"agent_key": a["agent_key"], "agent_config_version": a["config_version"]}


# ───────────── A4: phạm vi do chủ dự án cho phép (D1, không cấp từ lời chat) ─────────────

def approve(store, brain, goal_id: str) -> dict:
    """Chủ dự án bấm Cho phép trên thẻ cho yêu cầu phạm vi đang chờ của mục tiêu (kèm đúng bản nháp mới nhất nếu có),
    qua đúng lệnh host dùng. Không có yêu cầu đang chờ thì không làm gì."""
    import resonance as R
    o = owner(brain)
    sc = store.scope_state(o, goal_id)
    req = sc.get("request") or {}
    if sc.get("state") != "pending" or not req:
        return {}
    g = store.get(o, goal_id)
    drafts = store.submissions(o, goal_id, limit=1, statuses=("awaiting_scope",), revision=g.revision)
    body = {"request_id": req["id"], "path": R._deliverable_rel(g)}
    if drafts:
        body.update(submission_id=drafts[0]["id"], sha256=drafts[0]["sha256"])
    return R.apply_command(store, o, goal_id, "approve_scope", body, str(Path(brain).resolve()))


def preapprove():
    """Test viết trước A4 giả định mục tiêu có đường sản phẩm được làm ngay. Từ A4 đích mới chờ chủ dự án cho phép
    (D1); helper này đóng vai chủ dự án bấm Cho phép NGAY sau mỗi lần lập, sửa hay gán mục tiêu (mọi kho trong tiến
    trình test, kể cả kho mở lại để mô phỏng khởi động lại), để nội dung kiểm của test cũ giữ nguyên. Lượt chat lập
    mục tiêu vẫn KHÔNG nhận quyền mới (gốc có sau ảnh chụp đầu lượt): đúng luật thứ tự quyền."""
    if getattr(RS.GoalStore, "_preapproved", False):
        return
    for name in ("create", "revise", "assign_goal", "drop_directive"):
        orig = getattr(RS.GoalStore, name)

        def wrapped(self, p, *a, _orig=orig, _name=name, **kw):
            out = _orig(self, p, *a, **kw)
            g = out[0] if _name == "create" else out
            try:
                approve(self, p.brain_id, g.id)
            except Exception:  # noqa: BLE001 - yêu cầu đã cũ hay trợ lý tắt: để test tự thấy trạng thái thật
                pass
            return out
        setattr(RS.GoalStore, name, wrapped)
    RS.GoalStore._preapproved = True
