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
- Biết ĐÚNG lượt nào đang gọi nhờ ngữ cảnh lượt do host gắn (`turn_context`, A1): phiên, id tin và agent của phiên.
  Engine trong tiến trình đọc thẳng; engine CLI mang khoá `X-Javis-Turn` qua hub. Không có ngữ cảnh, lượt không thuộc
  một agent, hay agent chưa bật Cộng hưởng thì từ chối trước mọi lần ghi kho. Không đoán "lượt duy nhất của brain".
- Một tin nhắn chỉ tạo một mục tiêu; cập nhật cần đúng `expected_revision`. Mục tiêu thuộc đúng agent của lượt:
  list và update không thấy mục tiêu của agent khác.

Hiện tool (`visible_fn`) chỉ là gợi ý: trong lượt thì theo agent của lượt, ngoài lượt thì khi brain có ít nhất một
agent bật. Cổng thật nằm trong handler. Công tắc theo brain cũ (`Javis/resonance.json`) không còn cấp quyền.
Từ M3 mục tiêu được làm tiếp ở NỀN (resonance.advance qua scheduler) trong hạn mức lượt gọi riêng; kết quả,
việc chờ xác nhận hay lý do phải dừng tự về đúng khung chat. Kết quả trả về dặn bộ não nói đúng điều đó và
không hứa thời điểm. Bộ thực thi nền CHỈ có lời người dùng và khung mục tiêu, không đọc được file hay dữ liệu.
"""
from __future__ import annotations

from pathlib import Path

_NOTE = ("Lưu ý: mục tiêu sẽ được Javis làm tiếp ở NỀN từng bước, trong hạn mức {budget} lượt gọi model; "
         "kết quả, việc cần người dùng xác nhận hay lý do phải dừng tự hiện trong khung chat này. Nói đúng như vậy, "
         "đừng hứa thời điểm cụ thể. Bộ thực thi nền chỉ có lời người dùng và khung mục tiêu, KHÔNG đọc được file "
         "hay dữ liệu khác: phần cần dữ liệu thì làm ngay trong lượt này.")


def _brain_id(vault_root) -> str:
    return str(Path(vault_root).resolve()) if vault_root else ""


def _store_exists() -> bool:
    from config import STATE_DIR
    return (Path(STATE_DIR) / "resonance.sqlite3").is_file()


def _visible(vault_root) -> bool:
    """Gợi ý hiện tool. Trong lượt: lượt thuộc một agent đang bật. Ngoài lượt (danh sách hub dùng chung): brain có ít
    nhất một agent bật. Không tạo kho chỉ để trả lời câu này."""
    try:
        import resonance as R
        import resonance_store as RS
        import turn_context
        if not vault_root or not _store_exists():
            return False
        store, bid = RS.GoalStore(), _brain_id(vault_root)
        t = turn_context.current()
        if t is not None:
            ag = t.get("agent") or {}
            return bool(ag.get("key")) and not R.agent_gate(store, bid, ag["key"])[1]
        return any(a["enabled"] and a["status"] == "active" for a in store.agents(bid))
    except Exception:  # noqa: BLE001
        return False


def _proposal(args: dict) -> dict:
    # remove_targets đã gỡ khỏi schema (M2 chưa bỏ được chỉ tiêu người dùng) nhưng lời gọi cũ vẫn có thể mang
    # nó: chuyển tiếp để validator báo "chưa hỗ trợ" thay vì lặng lẽ bỏ qua.
    keys = ("understanding", "criteria", "relevant_quote", "horizon", "stage", "mode", "assumptions",
            "constraints", "targets", "open_questions", "guards", "remove_targets")
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
    if g.targets:
        lines.append("Chỉ tiêu người dùng nêu: " + "; ".join(f"{t.get('text')} (\"{t.get('quote')}\")"
                                                         for t in g.targets))
    if g.assumptions:
        lines.append("Giả định: " + "; ".join(g.assumptions))
    if g.constraints:
        lines.append("Ràng buộc của người dùng: " + "; ".join(g.constraints))
    if g.open_questions:
        lines.append("Câu hỏi còn mở (chỉ hỏi nếu thật cần): " + "; ".join(g.open_questions))
    if g.guards:
        lines.append("Guard (host tự kiểm định kỳ, nhảy thì dừng mục tiêu): "
                     + "; ".join(f"{x.get('id')} {x.get('description')}" for x in g.guards))
    lines.append(_NOTE.format(budget=g.budget_calls))
    return "\n".join(lines)


def _hold_until() -> float:
    """Lập hay cập nhật trong lượt chat: lịch việc nền giữ tới khi host bàn giao cuối lượt (review pilot lần 3), để
    việc nền không chen vào khi bộ não còn đang viết. Lượt bị cắt thì lịch tự tới hạn sau HANDOFF_HOLD_S."""
    import time
    import resonance as R
    return time.time() + R.HANDOFF_HOLD_S


_PLAIN = " Không lập mục tiêu; trả lời người dùng bình thường."


def _scope_note(store, p, g, mref: str) -> str:
    """A4: phạm vi ghi của revision này và mã bàn giao (`handoff`) của lượt, để bộ não nộp sản phẩm qua
    javis_submit_deliverable và nói ĐÚNG với người dùng. Javis không cấp quyền ghi từ lời chat: đích mới luôn chờ
    chủ dự án bấm Cho phép trên thẻ."""
    try:
        import resonance as R
        sc = store.scope_state(p, g.id)
        b = store.turn_binding(p, g.id, g.revision, mref)
    except Exception:  # noqa: BLE001
        return ""
    path = R._deliverable_rel(g)
    st = sc.get("state")
    lines = []
    if st == "granted":
        lines.append(f"Phạm vi ghi: đã được cho phép với {path}.")
    elif st == "pending":
        lines.append(f"Phạm vi ghi: CHƯA được cho phép. Thẻ mục tiêu sẽ hỏi chủ dự án có cho ghi vào {path} không. "
                     "Nói đúng như vậy; đừng nói đã ghi hay sẽ tự ghi. Bản bạn nộp bây giờ chỉ được giữ làm nháp; "
                     "chủ dự án bấm Cho phép thì Javis đăng đúng bản đó.")
    elif st in ("revoked", "denied", "missing"):
        lines.append("Phạm vi ghi: không có quyền ghi lúc này (chủ dự án đã thu hồi hay chưa cho phép).")
    if b is not None and b.get("status") == "live" and path:
        lines.append(f"Mã bàn giao của lượt này: handoff={b['id']}. Muốn nộp sản phẩm thì gọi javis_submit_deliverable "
                     f"với path={path}, content là TOÀN VĂN, và handoff này. Không Write thẳng vào file đích.")
    return ("\n" + "\n".join(lines)) if lines else ""


def _turn(vault_root):
    """Danh tính của lời gọi, CHỈ từ ngữ cảnh lượt do host gắn: (store, agent, session_id, msg_id, user_text), hoặc
    chuỗi lỗi. Không nhận agent hay phiên từ tham số của model. Lời người dùng đọc từ sổ lượt theo ĐÚNG khoá
    (web:<phiên>, id tin) của ngữ cảnh, là bản lời host đã dùng cho lượt này."""
    import luot_dang_chay
    import resonance as R
    import resonance_store as RS
    import turn_context
    t = turn_context.current()
    if t is None:
        return ("ERROR: Không xác định được lượt chat đang gọi tool (engine này chưa mang được ngữ cảnh lượt tới "
                "Javis)." + _PLAIN)
    ag = t.get("agent") or {}
    if not ag.get("key"):
        return ("ERROR: Cộng hưởng chỉ dùng trong cuộc trò chuyện với một trợ lý đã bật Cộng hưởng (trang Cộng sự)."
                + _PLAIN)
    sid, mid = str(t.get("session_id") or ""), int(t.get("message_id") or 0)
    if not sid or mid <= 0:
        return "ERROR: Lượt này không có id tin nhắn của người dùng." + _PLAIN
    if not _store_exists():
        return "ERROR: Chưa có trợ lý nào bật Cộng hưởng." + _PLAIN
    store = RS.GoalStore()
    _a, why = R.agent_gate(store, _brain_id(vault_root), ag["key"], ag.get("config_version"))
    if why:
        return (f"ERROR: Cộng hưởng của trợ lý này đang tắt hoặc vừa đổi ({why}). Chủ dự án bật lại ở trang Cộng sự "
                "rồi gửi lại tin." + _PLAIN)
    text = luot_dang_chay.loi_cua_luot(f"web:{sid}", mid, vault_root)
    if text is None:
        return "ERROR: Lượt chat của tin này không còn chạy." + _PLAIN
    return store, ag, sid, mid, text, t.get("authority_seq")


async def javis_goal(args, ctx):
    import resonance as R
    import resonance_store as RS
    args = args or {}
    vault = getattr(ctx, "vault_root", None)
    op = str(args.get("op") or "").strip().lower()
    if op not in ("create", "update", "list"):
        return "ERROR: op phải là create, update hoặc list."
    if not vault:
        return "ERROR: Không xác định được brain." + _PLAIN
    turn = _turn(vault)
    if isinstance(turn, str):
        return turn
    store, ag, sid, mid, user_text, aseq = turn
    p = RS.Principal("agent", ag["key"], _brain_id(vault))
    if op == "list":
        goals = store.list_open(p, agent_key=ag["key"])
        if not goals:
            return "Trợ lý này chưa có mục tiêu nào đang mở."
        return "\n\n".join(_summary(g, "Mục tiêu") for g in goals[:10])
    mref = R.message_ref(sid, mid)
    constraints = [str(x) for x in (args.get("constraints") or []) if str(x).strip()]
    unsure = bool(args.get("user_unsure"))
    if op == "create":
        deps = R.GoalDeps(engine_factory=lambda s, t: (None, {"blocked": "tool không gọi model"}),
                          budget=R.CallBudget(0), store=store)
        try:
            g = await R.form_goal(mref, {"principal": p, "brain_root": vault, "session_id": sid, "message_id": mid,
                                         "user_text": user_text, "constraints": constraints,
                                         "proposal": _proposal(args), "user_unsure": unsure,
                                         "hold_until": _hold_until(), "agent_key": ag["key"],
                                         "agent_version": ag.get("config_version"), "authority_seq": aseq}, deps)
        except R.GoalRejected as e:
            return f"ERROR: Chưa lập được mục tiêu: {e}. Sửa đề xuất rồi gọi lại, hoặc trả lời bình thường nếu việc này không cần theo đuổi sau lượt chat."
        except RS.AgentStateError as e:
            return f"ERROR: Cộng hưởng của trợ lý này vừa tắt hoặc đổi ({e})." + _PLAIN
        if g.agent_key != ag["key"]:
            # Tin này đã có mục tiêu từ trước mà không thuộc trợ lý của lượt: không trả nó ra, không ghi gì thêm.
            return "ERROR: Tin này đã gắn với một mục tiêu không thuộc trợ lý này." + _PLAIN
        return _summary(g, "Đã lập mục tiêu") + _scope_note(store, p, g, mref)
    gid = str(args.get("goal_id") or "")
    try:
        exp = int(args.get("expected_revision"))
    except (TypeError, ValueError):
        return "ERROR: update cần expected_revision (số revision bạn đang thấy)."
    cur = store.get(p, gid)
    if cur is None or cur.agent_key != ag["key"]:
        # Kiểm TRƯỚC khi đọc hay so gì: mục tiêu của agent khác trả lời như không tồn tại, không lộ nội dung.
        return "ERROR: Không có mục tiêu này trong các mục tiêu của trợ lý. Gọi op=list để xem."
    try:
        # Đọc revision hiện tại trước khi kiểm: hạn và chỉ tiêu người dùng nêu ở tin trước được giữ nguyên.
        g, relation, kept = R.revise_goal(store, p, gid, exp, _proposal(args), {
            "message_ref": mref, "session_id": sid, "message_id": mid, "user_text": user_text,
            "constraints": constraints, "user_unsure": unsure, "reason": args.get("reason"),
            "hold_until": _hold_until(), "agent_key": ag["key"], "agent_version": ag.get("config_version"),
            "authority_seq": aseq})
    except RS.ConflictError as e:
        return f"ERROR: Mục tiêu đã đổi trước đó ({e}). Gọi op=list để xem revision hiện tại."
    except RS.ScopeError as e:
        return f"ERROR: {e}."
    except RS.AgentStateError as e:
        return f"ERROR: Cộng hưởng của trợ lý này vừa tắt hoặc đổi ({e})." + _PLAIN
    except R.GoalRejected as e:
        return f"ERROR: Chưa cập nhật được mục tiêu: {e}."
    if relation == "none":
        out = _summary(g, "KHÔNG có thay đổi nào được áp dụng, mục tiêu giữ nguyên")
    else:
        out = _summary(g, "Đã cập nhật mục tiêu")
    out += _scope_note(store, p, g, mref)
    if kept:
        out += ("\nHost giữ nguyên chỉ dẫn cũ, phần sau CHƯA áp dụng (bản này chưa hỗ trợ). Nói rõ với người dùng là chưa đổi được, "
                "đừng báo là đã đổi:\n" + "\n".join("- " + k for k in kept))
    return out


_DESC = (
    "Lập hoặc cập nhật MỤC TIÊU bền (Hệ thống cộng hưởng). op=create CHỈ khi người dùng giao trách nhiệm theo "
    "đuổi kết quả SAU lượt chat này (làm, tự kiểm, sửa theo phản hồi, duy trì, theo dõi, chờ sự kiện, giữ việc "
    "mở tới khi đạt) và nói được cách nhận biết xong (criteria) cùng chân trời (horizon). KHÔNG gọi cho: câu "
    "hỏi, tư vấn, lập kế hoạch, việc làm xong ngay trong lượt, hay kế hoạch do chính bạn đề xuất. Việc nền một "
    "lần, xong là hết trách nhiệm: javis_task. Nhắc giờ cố định: "
    "javis_schedule. relevant_quote phải trích NGUYÊN VĂN lời người dùng. Không bịa hạn chót hay chỉ tiêu: "
    "người dùng không nêu hạn thì horizon.kind=review (mốc xem lại nội bộ). Người dùng nói chưa biết muốn gì "
    "thì user_unsure=true, stage=discovery. Người dùng bổ sung ý cho mục tiêu đang mở: op=update với goal_id "
    "và expected_revision (xem bằng op=list); chỉ gửi trường thay đổi, trường bỏ trống giữ như cũ. Bản này "
    "CHƯA đổi hay bỏ được hạn chót, chỉ tiêu và ràng buộc người dùng đã nêu: host giữ nguyên và báo lại; khi "
    "đó nói rõ với người dùng là bạn không đổi được, người dùng tự bỏ bằng nút Bỏ trên thẻ mục tiêu trong khung chat. "
    "Thêm chỉ tiêu hay ràng buộc mới thì được."
)

_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {"type": "string", "enum": ["create", "update", "list"]},
        "understanding": {"type": "string", "description": "Kết quả cần tạo, một câu. Rỗng nếu chưa rõ."},
        "criteria": {"type": "array", "description": "Cách nhận biết xong. Ít nhất một mục.", "items": {
            "type": "object", "properties": {
                "description": {"type": "string",
                                "description": "Điều cần kiểm, cụ thể. Rỗng thì host từ chối."},
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
        "guards": {"type": "array", "description": "Điều kiện bảo vệ host tự kiểm định kỳ bằng code; nhảy thì "
                   "dừng mục tiêu và báo người dùng. Ví dụ ràng buộc 'không xoá ghi chú cũ': artifact_contract với "
                   "path của ghi chú đó.", "items": {"type": "object", "properties": {
                       "description": {"type": "string"},
                       "evaluator": {"type": "string", "enum": ["artifact_contract"]},
                       "params": {"type": "object"}}, "required": ["description", "evaluator"]}},
        "user_unsure": {"type": "boolean"},
        "goal_id": {"type": "string"},
        "expected_revision": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["op"],
}


_SUBMIT_MSG = {
    "no_turn": "Không xác định được lượt chat đang gọi (engine này chưa mang được ngữ cảnh lượt tới Javis).",
    "not_agent_turn": "Chỉ nộp được trong cuộc trò chuyện với một trợ lý đã bật Cộng hưởng.",
    "invalid_content": "content phải là toàn văn sản phẩm, không rỗng.",
    "path_rejected": "Đường đích không nhận (ngoài brain, có . hay .., đuôi không phải .md/.txt, hay thư mục cấm).",
    "too_large": "Sản phẩm quá 1MB.",
    "no_open_handoff": "Lượt này không có mục tiêu nào đang chờ bàn giao (lập hay cập nhật mục tiêu bằng javis_goal trước).",
    "path_not_in_scope": "Đường này không phải sản phẩm của mục tiêu trong lượt này.",
    "ambiguous_handoff": "Có nhiều mục tiêu cùng đích trong lượt này; gửi kèm handoff do javis_goal trả.",
    "submission_conflict": "Khoá nộp này đã dùng cho một nội dung khác.",
    "turn_closed": "Lượt bàn giao đã đóng; không nhận lời nộp mới.",
    "grant_revoked": "Chủ dự án đã thu hồi quyền của mục tiêu này.",
    "scope_decided": "Chủ dự án đã quyết phạm vi; lượt này không nộp thêm được.",
    "revision_changed": "Mục tiêu đã sang revision khác; nộp theo handoff mới.",
    "agent_changed": "Công tắc trợ lý vừa đổi; không nhận lời nộp.",
    "storage_error": "Javis chưa lưu được bản nộp; thử lại sau.",
}


async def javis_submit_deliverable(args, ctx):
    """A4 (mục 4.3): nộp TOÀN VĂN sản phẩm cho mục tiêu lượt này vừa lập hay cập nhật. Host tự đọc, băm, lưu bản nộp có
    biên nhận và tự đăng vào đích cuối lượt khi có quyền; chưa có quyền thì giữ làm nháp chờ chủ dự án. Model không
    truyền được mục tiêu, trợ lý hay quyền."""
    import resonance as R
    import resonance_store as RS
    import turn_context
    vault = getattr(ctx, "vault_root", None)
    if not vault or not _store_exists():
        return "ERROR: Chưa có trợ lý nào bật Cộng hưởng."
    deps = R.deps_for(_brain_id(vault))
    if deps is None:
        deps = R.GoalDeps(engine_factory=lambda s, t: (None, {}), budget=R.CallBudget(0), store=RS.GoalStore(),
                          principal=RS.Principal("agent", "javis", _brain_id(vault)), brain_root=_brain_id(vault))
    # Ghi file nháp, bằng chứng và SQLite chạy ở luồng phụ (thiết kế A4 mục 11), không giữ event loop. Danh tính lượt
    # đọc NGAY ở đây rồi truyền vào, không dựa vào việc chép ngữ cảnh.
    import asyncio
    res = await asyncio.to_thread(R.submit_deliverable, turn_context.current(), dict(args or {}), deps)
    if not res.get("ok"):
        code = res.get("code") or "storage_error"
        extra = ""
        if res.get("handoffs"):
            extra = " Các handoff: " + ", ".join(f"{h['handoff']} (mục tiêu {h['goal_id']})" for h in res["handoffs"])
        return f"ERROR {code}: {_SUBMIT_MSG.get(code, code)}{extra}"
    st = res["status"]
    what = {"candidate": "chờ host đăng vào file đích cuối lượt",
            "awaiting_scope": "giữ làm NHÁP; file đích chưa được cho phép, chủ dự án bấm Cho phép thì Javis đăng đúng "
                              "bản này",
            "published": "đã đăng"}.get(st, st)
    return (f"Đã nhận bản nộp {res['submission_id']} (sha256 {res['sha256'][:12]}, {res['size']} byte): {what}."
            + (" Đây là biên nhận cũ của cùng nội dung." if res.get("replay") else "")
            + " Không nói với người dùng là file đã được ghi cho tới khi host đăng xong.")


_SUBMIT_DESC = (
    "Nộp TOÀN VĂN sản phẩm của mục tiêu mà lượt này vừa lập hay cập nhật bằng javis_goal. Dùng thay cho ghi thẳng "
    "vào file đích: host tự lưu bản nộp có biên nhận, tự đăng vào file đích khi chủ dự án đã cho phép phạm vi, và "
    "không ghi đè file người dùng. path là đường sản phẩm của mục tiêu (tương đối trong brain), content là toàn bộ "
    "nội dung, handoff là mã javis_goal trả (bắt buộc khi lượt có nhiều mục tiêu cùng đích). Nộp lại cùng nội dung trả "
    "biên nhận cũ.")

_SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Đường sản phẩm của mục tiêu, tương đối trong brain."},
        "content": {"type": "string", "description": "Toàn văn sản phẩm."},
        "handoff": {"type": "string", "description": "Mã bàn giao do javis_goal trả."},
        "submission_key": {"type": "string", "description": "Khoá chống nộp trùng, không bắt buộc."},
    },
    "required": ["path", "content"],
}


def register(ctx):
    ctx.register_tool(name="javis_goal", description=_DESC, handler=javis_goal, min_mode="safe",
                      schema=_SCHEMA, visible_fn=_visible)
    ctx.register_tool(name="javis_submit_deliverable", description=_SUBMIT_DESC, handler=javis_submit_deliverable,
                      min_mode="safe", schema=_SUBMIT_SCHEMA, visible_fn=_visible)
