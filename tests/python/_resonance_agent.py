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
def turn(agent: dict, session_id: str, message_id: int, user_text: str, brain, slug: str = SLUG):
    """Một lượt chat của agent như run_turn dựng: ngữ cảnh lượt có agent và sổ lượt có lời người dùng."""
    tok = turn_context.bind(turn_context.make(
        "dashboard", chat_id=session_id, la_chu=True, session_id=session_id, message_id=message_id,
        agent={"key": agent["agent_key"], "slug": slug, "config_version": agent["config_version"]}))
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
