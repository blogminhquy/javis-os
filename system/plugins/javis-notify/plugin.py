"""Plugin bundled: tool `javis_notify` - người dùng ra lệnh bằng lời cho chỉ huy thông báo (0.403.0).

Chủ repo 29/10/2026: Javis Core là chỉ huy bật tắt thông báo, người dùng nói "tắt thông báo đăng nhập Zalo" là xong.
Luật và dữ liệu nằm ở `server/notify_policy.py`; tool này chỉ đọc và ghi qua đó, với `set_by="owner"` (người dùng tự
nói, không phải bộ phán xử của Core tự chỉnh). Spec: docs/dev/2026-10-javis-core-chi-huy-thong-bao.md mục 4.4.

Năm op:
- status: chế độ từng nhóm, loại tin đang lọc hoặc luôn báo, thay đổi gần đây (kèm mã để hoàn tác).
- set group=... mode=...: đặt chế độ một nhóm (all, important, urgent, off).
- mute text=...: lọc một loại tin, tìm theo chữ trong tiêu đề của các thông báo gần đây.
- unmute text=...: bỏ luật riêng của loại tin đó (về theo chế độ của nhóm).
- undo id=...: hoàn tác một thay đổi.
"""
from __future__ import annotations

try:
    import notify_policy as NP
    import inbox
except Exception:          # chạy ngoài máy chủ
    NP = None
    inbox = None


def _group(text: str) -> str:
    """Khoá nhóm từ khoá hoặc tên hiện (tiếng Việt / tiếng Anh, không phân biệt hoa thường)."""
    t = " ".join(str(text or "").lower().split())
    if t in NP.GROUPS:
        return t
    for g, (vi, en) in NP.GROUP_NAMES.items():
        if t and (t == vi.lower() or t == en.lower() or t in vi.lower() or t in en.lower()):
            return g
    return ""


def _status() -> str:
    st = NP.status(10)
    dong = ["Chế độ từng nhóm (mặc định: " + NP.mode_name(st["default"]) + "):"]
    for g in st["groups"]:
        ai = {"core": " (Javis Core chỉnh)", "owner": " (bạn chọn)"}.get(g["set_by"], "")
        dong.append(f"- {g['name']} [{g['group']}]: {NP.mode_name(g['mode'])}{ai}")
    if st["rules"]:
        dong.append("Loại tin có luật riêng:")
        for r in st["rules"][:20]:
            dong.append(f"- {r.get('label') or r['sig']} ({NP.group_name(r['group'])}): "
                        + ("lọc" if r.get("rule") == "mute" else "luôn báo"))
    if st["changes"]:
        dong.append("Thay đổi gần đây (mã để hoàn tác):")
        for c in st["changes"][:10]:
            dong.append(f"- {c['id']}{' (đã hoàn tác)' if c.get('undone') else ''}: {NP.describe(c)}")
    return "\n".join(dong)


def _find_item(text: str):
    """Thông báo gần đây nhất có tiêu đề khớp `text` (so theo chữ ký, bỏ số và mã)."""
    q = NP.signature(text)
    if not q:
        return None
    for it in inbox.danh_sach(300):
        sig = it.get("sig") or NP.signature(it.get("title") or "")
        if q in sig or q in NP.signature(it.get("body") or ""):
            return it
    return None


def _chay(args, ctx) -> str:
    if NP is None:
        return "ERROR: chỉ huy thông báo chưa sẵn sàng trên máy chủ này."
    a = args or {}
    op = str(a.get("op") or "").strip().lower()
    if op == "status":
        return _status()
    if op == "set":
        g = _group(a.get("group"))
        m = str(a.get("mode") or "").strip().lower()
        if not g:
            return "ERROR: không rõ nhóm. Nhóm có: " + ", ".join(f"{k} ({NP.group_name(k)})" for k in NP.GROUPS)
        if m not in NP.MODES:
            return "ERROR: mode phải là all, important, urgent hoặc off."
        c = NP.set_mode(g, m, set_by="owner", reason="Bạn nói trong chat.")
        return (f"Đã đặt nhóm {NP.group_name(g)}: {NP.mode_name(m)}. Mã hoàn tác: {c['id']}." if c
                else f"Nhóm {NP.group_name(g)} đã ở chế độ {NP.mode_name(m)}.")
    if op in ("mute", "unmute"):
        text = str(a.get("text") or "").strip()
        if not text:
            return "ERROR: thiếu text - một đoạn chữ trong tiêu đề của loại thông báo cần đổi."
        if op == "unmute":
            rules = NP.find_rules(text)
            if not rules:
                return f"Không có luật riêng nào khớp \"{text}\"."
            done = [NP.set_rule(r["group"], r["sig"], None, set_by="owner", label=r.get("label") or "",
                                reason="Bạn nói trong chat.") for r in rules]
            return "Đã bỏ luật riêng cho: " + "; ".join(r.get("label") or r["sig"] for r in rules) + \
                   ". Các loại tin này giờ theo chế độ của nhóm." if any(done) else "Không có gì để đổi."
        it = _find_item(text)
        if it is None:
            return (f"Chưa thấy thông báo nào khớp \"{text}\" trong chuông. Có thể tắt cả nhóm bằng op=set "
                    "(xem op=status để biết tên nhóm).")
        g = it.get("group") if it.get("group") in NP.GROUPS else NP.group_of(source=it.get("source") or "",
                                                                                kind=it.get("kind") or "")
        sig = it.get("sig") or NP.signature(it.get("title") or "")
        c = NP.set_rule(g, sig, "mute", set_by="owner", label=it.get("title") or sig, reason="Bạn nói trong chat.")
        return (f"Đã lọc các thông báo kiểu \"{it.get('title')}\" ({NP.group_name(g)}): vẫn giữ trong ngăn Đã lọc "
                f"của chuông, không báo nữa. Mã hoàn tác: {c['id']}." if c else
                f"Các thông báo kiểu \"{it.get('title')}\" đã đang bị lọc.")
    if op == "undo":
        c = NP.undo(str(a.get("id") or "").strip())
        return ("Đã hoàn tác: " + NP.describe(c, hint=False)) if c else \
            "ERROR: không thấy thay đổi nào mang mã này (xem op=status)."
    return "ERROR: op phải là status, set, mute, unmute hoặc undo."


def register(ctx):
    ctx.register_tool(
        "javis_notify",
        "Chỉ huy thông báo của Javis Core: chọn thông báo nào được báo (chấm đỏ trên chuông, đẩy lên điện thoại, "
        "Telegram của chủ). Mỗi thông báo thuộc một nhóm (job, reminder, question, agent, team, incident, "
        "connection, chatbot, cost, update, other) và có mức info, important hoặc urgent. Mỗi nhóm có chế độ: all, "
        "important, urgent (mặc định: chỉ tin khẩn) hoặc off. Tin không đủ mức vẫn nằm trong chuông, ở ngăn Đã lọc. "
        "op=status: xem chế độ, luật riêng, thay đổi gần đây. op=set group=... mode=...: đặt chế độ một nhóm. "
        "op=mute text=...: lọc một loại tin (tìm theo chữ trong tiêu đề thông báo gần đây). op=unmute text=...: bỏ "
        "luật riêng. op=undo id=...: hoàn tác một thay đổi. Dùng khi người dùng nói kiểu 'tắt thông báo đăng nhập "
        "Zalo', 'đừng báo việc chạy xong nữa', 'báo hết cho tôi'.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["status", "set", "mute", "unmute", "undo"]},
                "group": {"type": "string", "description": "Nhóm (op=set): khoá hoặc tên hiện, vd connection, Kết nối"},
                "mode": {"type": "string", "enum": ["all", "important", "urgent", "off"]},
                "text": {"type": "string", "description": "Chữ trong tiêu đề loại thông báo (op=mute/unmute)"},
                "id": {"type": "string", "description": "Mã thay đổi (op=undo)"},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="🔔",
    )
