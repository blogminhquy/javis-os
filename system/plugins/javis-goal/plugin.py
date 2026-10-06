"""Plugin bundled: tool `javis_goal` - bộ não tự lập hoặc cập nhật mục tiêu bền (Javis Resonance, M2).

Vì sao là tool của bộ não
=========================
Kế hoạch MVP cấm gọi thêm model để phân loại mọi tin nhắn. Bộ não vốn đang suy nghĩ về tin đó trong
lượt chat, và đã có sẵn cách tự quyết giao việc nền bằng `javis_task`. Nên quyết định "việc này cần
theo đuổi sau lượt chat" cũng thuộc về bộ não, bằng một lời gọi tool, không phải bằng từ khoá.

Host làm phần code làm chắc hơn model
=====================================
- Kiểm đề xuất theo SMART (`resonance.validate_proposal`): câu căn cứ phải trích đúng lời người dùng,
  phải có tiêu chí kiểm được và chân trời; hạn chót hay chỉ tiêu không có căn cứ thì không giữ nguyên.
- Biết đang phục vụ TIN NHẮN nào nhờ sổ `luot_dang_chay`. Không chắc (hai khung chat cùng chạy trên
  một brain, hoặc kênh chưa truyền id tin) thì từ chối, không đoán.
- Một tin nhắn chỉ tạo một mục tiêu; cập nhật cần đúng `expected_revision`.

Chỉ hiện ở brain đã bật Hệ thống cộng hưởng (`<brain>/Javis/resonance.json`), qua `visible_fn`.
Ở M2 tool chỉ LƯU mục tiêu; chưa có gì tự thực hiện, nên kết quả trả về dặn bộ não đừng hứa suông.
"""
from __future__ import annotations

from pathlib import Path

_NOTE = ("Lưu ý: bản hiện tại chỉ LƯU mục tiêu và cách hiểu, chưa tự thực hiện hay tự báo cáo. "
         "Đừng hứa sẽ tự làm tiếp hay tự báo lại. Phần làm được ngay thì làm trong lượt này; "
         "việc nền một lần thì giao javis_task.")


def _enabled(vault_root) -> bool:
    import resonance
    return bool(vault_root) and resonance.enabled_for(vault_root)


def _proposal(args: dict) -> dict:
    keys = ("understanding", "criteria", "relevant_quote", "horizon", "stage", "mode", "assumptions",
            "constraints", "targets", "open_questions")
    return {k: args.get(k) for k in keys if k in args}


def _when(ts) -> str:
    try:
        import time
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))
    except Exception:  # noqa: BLE001
        return "?"


def _summary(g, head: str) -> str:
    h = g.horizon or {}
    if h.get("kind") == "deadline":
        hz = f"hạn {_when(h.get('at'))} (người dùng nêu: \"{h.get('quote')}\")"
    elif h.get("kind") == "review":
        hz = f"mốc xem lại nội bộ {_when(h.get('at'))}, KHÔNG phải hạn của người dùng"
    elif h.get("kind") == "event":
        hz = f"chờ sự kiện: {h.get('event')}"
    else:
        hz = "duy trì cho tới khi người dùng dừng"
    lines = [f"{head} {g.id} (revision {g.revision}, stage {g.stage}, mode {g.mode}).",
             f"Cách hiểu: {g.understanding or '(chưa rõ, đang ở bước khám phá)'}",
             "Tiêu chí: " + "; ".join(f"{c['id']} {c['description']} [{c['evaluator']}]" for c in g.criteria),
             f"Chân trời: {hz}"]
    if g.assumptions:
        lines.append("Giả định: " + "; ".join(g.assumptions))
    if g.constraints:
        lines.append("Ràng buộc của người dùng: " + "; ".join(g.constraints))
    if g.open_questions:
        lines.append("Câu hỏi còn mở (chỉ hỏi nếu thật cần): " + "; ".join(g.open_questions))
    lines.append(_NOTE)
    return "\n".join(lines)


def _turn(vault_root):
    """(session_id, msg_id, user_text) của lượt đang chạy, hoặc chuỗi lỗi."""
    import luot_dang_chay
    lu = luot_dang_chay.doan_luot(vault_root)
    if not lu:
        return ("ERROR: Không xác định được tin nhắn đang xử lý (có thể hai khung chat cùng chạy trên "
                "brain này). Không lập mục tiêu; trả lời người dùng bình thường.")
    chat = str(lu.get("chat_id") or "")
    if not chat.startswith("web:") or int(lu.get("msg_id") or 0) <= 0:
        return ("ERROR: Kênh chat này chưa hỗ trợ lập mục tiêu (cần khung chat web). Không lập mục tiêu; "
                "trả lời người dùng bình thường.")
    return chat[len("web:"):], int(lu["msg_id"]), str(lu.get("user_text") or "")


async def javis_goal(args, ctx):
    import resonance as R
    import resonance_store as RS
    args = args or {}
    vault = getattr(ctx, "vault_root", None)
    if not _enabled(vault):
        return "ERROR: Hệ thống cộng hưởng chưa bật cho brain này. Không lập mục tiêu."
    p = RS.Principal("agent", "javis", str(Path(vault).resolve()))
    store = RS.GoalStore()
    op = str(args.get("op") or "").strip().lower()
    if op == "list":
        goals = store.list_open(p)
        if not goals:
            return "Chưa có mục tiêu nào đang mở trong brain này."
        return "\n\n".join(_summary(g, "Mục tiêu") for g in goals[:10])
    if op not in ("create", "update"):
        return "ERROR: op phải là create, update hoặc list."
    turn = _turn(vault)
    if isinstance(turn, str):
        return turn
    sid, mid, user_text = turn
    mref = R.message_ref(sid, mid)
    constraints = [str(x) for x in (args.get("constraints") or []) if str(x).strip()]
    unsure = bool(args.get("user_unsure"))
    if op == "create":
        deps = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "tool không gọi model"}),
                          budget=R.CallBudget(0), store=store)
        try:
            g = await R.form_goal(mref, {"principal": p, "brain_root": vault, "session_id": sid, "message_id": mid,
                                         "user_text": user_text, "constraints": constraints,
                                         "proposal": _proposal(args), "user_unsure": unsure}, deps)
        except R.GoalRejected as e:
            return f"ERROR: Chưa lập được mục tiêu: {e}. Sửa đề xuất rồi gọi lại, hoặc trả lời bình thường nếu việc này không cần theo đuổi sau lượt chat."
        return _summary(g, "Đã lập mục tiêu")
    gid = str(args.get("goal_id") or "")
    try:
        exp = int(args.get("expected_revision"))
    except (TypeError, ValueError):
        return "ERROR: update cần expected_revision (số revision bạn đang thấy)."
    try:
        frame = R.validate_proposal(_proposal(args), user_text, user_unsure=unsure, user_constraints=constraints)
        if store.get(p, gid) is None:
            return "ERROR: Không có mục tiêu này trong brain."
        intent = store.add_intent(p, sid, mid, user_text, constraints=constraints)
        g = store.revise(p, gid, exp, frame, reason=str(args.get("reason") or "người dùng bổ sung")[:500],
                         intent_id=intent["id"], message_ref=mref)
    except RS.ConflictError as e:
        return f"ERROR: Mục tiêu đã đổi trước đó ({e}). Gọi op=list để xem revision hiện tại."
    except RS.ScopeError as e:
        return f"ERROR: {e}."
    except R.GoalRejected as e:
        return f"ERROR: Chưa cập nhật được mục tiêu: {e}."
    return _summary(g, "Đã cập nhật mục tiêu")


_DESC = (
    "Lập hoặc cập nhật MỤC TIÊU bền (Hệ thống cộng hưởng). op=create CHỈ khi người dùng giao một việc cần "
    "theo đuổi SAU lượt chat này (duy trì, theo dõi, chờ sự kiện, làm tới khi đạt) và nói được cách nhận biết "
    "xong (criteria) cùng chân trời (horizon). KHÔNG gọi cho: câu hỏi, tư vấn, lập kế hoạch, việc làm xong ngay "
    "trong lượt, hay kế hoạch do chính bạn đề xuất. Việc nền một lần: javis_task. Nhắc giờ cố định: "
    "javis_schedule. relevant_quote phải trích NGUYÊN VĂN lời người dùng. Không bịa hạn chót hay chỉ tiêu: "
    "người dùng không nêu hạn thì horizon.kind=review (mốc xem lại nội bộ). Người dùng nói chưa biết muốn gì "
    "thì user_unsure=true, stage=discovery. Người dùng bổ sung ý cho mục tiêu đang mở: op=update với goal_id "
    "và expected_revision (xem bằng op=list)."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {"type": "string", "enum": ["create", "update", "list"]},
        "understanding": {"type": "string", "description": "Kết quả cần tạo, một câu. Rỗng nếu chưa rõ."},
        "criteria": {"type": "array", "description": "Cách nhận biết xong. Ít nhất một mục.", "items": {
            "type": "object", "properties": {
                "description": {"type": "string"},
                "evaluator": {"type": "string", "enum": ["artifact_contract", "human_confirmation"]},
                "params": {"type": "object", "description": "artifact_contract: path (tương đối trong brain), "
                                                            "min_chars, must_contain"}},
            "required": ["description", "evaluator"]}},
        "relevant_quote": {"type": "string", "description": "Trích nguyên văn một đoạn lời người dùng làm căn cứ."},
        "horizon": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["deadline", "review", "event", "maintain"]},
            "at_iso": {"type": "string", "description": "Thời điểm ISO 8601 cho deadline/review."},
            "from_user": {"type": "boolean"},
            "quote": {"type": "string", "description": "Trích đoạn người dùng nêu hạn (bắt buộc với deadline)."},
            "event": {"type": "string"},
            "reason": {"type": "string"}}},
        "stage": {"type": "string", "enum": ["discovery", "delivery"]},
        "mode": {"type": "string", "enum": ["achieve", "maintain"]},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "string"},
                        "description": "Ràng buộc người dùng đã nêu (ví dụ: không xoá gì)."},
        "targets": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "quote": {"type": "string"}}}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "user_unsure": {"type": "boolean"},
        "goal_id": {"type": "string"},
        "expected_revision": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["op"],
}


def register(ctx):
    ctx.register_tool(name="javis_goal", description=_DESC, handler=javis_goal, min_mode="safe",
                      schema=_SCHEMA, visible_fn=_enabled)
