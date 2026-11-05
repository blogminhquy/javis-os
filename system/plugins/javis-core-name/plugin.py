"""Bundled plugin: tool `javis_core_name`, the name and style of Javis Core in one brain (owner, 04/11/2026).

The owner wants people to make Javis Core their own: on the first chat it asks what to call it, then keeps that name
and the way of talking the person likes. The data lives in `<brain>/Javis/core.json` through `server/javis_core.py`
(`identity`, `set_identity`), the same agent file the Javis Core editor on the Partners page saves (name), plus `Javis/core.json` (style).

Owner only: `mcp_hub.OWNER_ONLY_TOOLS` lists it, so a customer-facing bot can never rename the owner's assistant.

Four ops:
- get: the current name (or none), style and whether the name was already asked.
- set name=... style=...: save a new name and/or style (name "" = back to "Javis Core").
- asked: note that Javis Core asked for a name, so it does not ask again in later chats.
- reset: drop the own name and style.
"""
from __future__ import annotations

try:
    import javis_core
except Exception:          # outside the server
    javis_core = None


def _root(ctx) -> str:
    return str(getattr(ctx, "vault_root", "") or "")


def _chay(args, ctx) -> str:
    if javis_core is None:
        return "ERROR: Javis Core chưa sẵn sàng trên máy chủ này."
    root = _root(ctx)
    if not root:
        return "ERROR: lượt này không gắn với brain nào, không lưu được tên."
    a = args or {}
    op = str(a.get("op") or "").strip().lower()
    if op == "get":
        me = javis_core.identity(root)
        return (f"Tên: {me['name'] or 'chưa đặt (đang là Javis Core)'}. "
                f"Phong cách: {me['style'] or 'chưa thống nhất'}. "
                f"Đã hỏi tên: {'rồi' if me['asked'] else 'chưa'}.")
    if op == "set":
        if "name" not in a and "style" not in a:
            return "ERROR: op=set cần name hoặc style."
        name = a.get("name") if "name" in a else None
        if name is not None and str(name).strip() and not javis_core.clean_name(name):
            return "ERROR: tên không hợp lệ."
        me = javis_core.set_identity(root, name=name, style=a.get("style") if "style" in a else None)
        out = []
        if name is not None:
            out.append(f"Đã đổi tên thành {me['name']}." if me["name"] else "Đã trả lại tên Javis Core.")
        if "style" in a:
            out.append(f"Đã lưu phong cách: {me['style']}." if me["style"] else "Đã bỏ phong cách riêng.")
        return " ".join(out)
    if op == "asked":
        javis_core.set_identity(root, asked=True)
        return "Đã ghi nhận là đã hỏi tên. Các chat sau không hỏi lại."
    if op == "reset":
        javis_core.set_identity(root, name="", style="")
        return "Đã trả lại tên Javis Core và bỏ phong cách riêng."
    return "ERROR: op phải là get, set, asked hoặc reset."


def register(ctx):
    ctx.register_tool(
        "javis_core_name",
        "Tên riêng và phong cách nói chuyện của Javis Core trong brain này, do NGƯỜI DÙNG chọn. Tên hiện trên trang "
        "Cộng sự và Javis Core tự xưng bằng tên đó. op=get: xem. op=set name=... (và/hoặc style=..., một câu ngắn "
        "mô tả giọng điệu người dùng thích): lưu; name rỗng = về lại Javis Core. op=asked: ghi nhận đã hỏi tên để "
        "không hỏi lại. op=reset: bỏ tên và phong cách riêng. Chỉ đổi khi người dùng chọn hoặc đồng ý, không tự đặt.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["get", "set", "asked", "reset"]},
                "name": {"type": "string", "description": "Tên mới (op=set), tối đa 40 ký tự"},
                "style": {"type": "string", "description": "Phong cách nói chuyện (op=set), một câu ngắn"},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="🪪",
    )
