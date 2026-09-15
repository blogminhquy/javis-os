"""Plugin bundled: tool `javis_workflow` - đọc lịch sử chạy quy trình, từ MỌI engine.

Vì sao tồn tại: kho `workflow_runs` (server/workflow_runs.py) ghi mọi lần chạy quy trình, nhưng
bộ não chính không có đường nào tới nó. Người dùng hỏi "quy trình vừa chạy ra sao" là Javis
trả lời trống, đúng lỗi chủ dự án báo 2026-09-15. Tool này chỉ ĐỌC (min_mode readonly), nên
chạy được cả ở chế độ suggest. Muốn chạy quy trình thì giao việc Kanban (javis_task, route
wf:<slug>) hoặc vào trang Cộng sự.

Khoá brain: kho ghi `_brain_key` = đường dẫn tuyệt đối đã resolve của brain, nên ở đây cũng
resolve `ctx.vault_root` cùng cách. `vault_root` rỗng thì báo lỗi rõ, không rơi về brain khác.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import workflow_runs

_LIST_MAX = 20
_TRAN_OUT = 6000     # kết quả cuối in ra tool: engine API cắt 8000, chừa chỗ cho phần còn lại


def _khoa(ctx) -> str:
    return str(Path(ctx.vault_root).resolve())


def _gio(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M %d/%m")
    except Exception:
        return "?"


def _liet_ke(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa biết đang làm việc trên brain nào nên không xem được lịch sử."
    slug = str((args or {}).get("slug") or "").strip() or None
    try:
        limit = max(1, min(int((args or {}).get("limit") or 10), _LIST_MAX))
    except Exception:
        limit = 10
    ds = workflow_runs.get_store().gan_nhat(_khoa(ctx), slug=slug, limit=limit)
    if not ds:
        return "Chưa có lần chạy quy trình nào" + (f" của '{slug}'" if slug else "") + "."
    dong = []
    for r in ds:
        dong.append(f"- {_gio(r['started_at'])} · {r['name']} ({r['slug']}) · {r['nhan']} · nguồn {r['source']}"
                    f" · id {r['id']}" + (f"\n  {r['output_tom_tat']}" if r.get("output_tom_tat") else "")
                    + (f"\n  lỗi: {r['error']}" if r.get("error") else ""))
    dong.append("Xem đủ một lần: op=show với id ở trên.")
    return "\n".join(dong)


def _xem(args, ctx) -> str:
    rid = str((args or {}).get("id") or "").strip()
    if not rid:
        return "ERROR: op=show cần id của lần chạy (lấy từ op=runs)."
    r = workflow_runs.get_store().lay(rid)
    if not r:
        return f"ERROR: không có lần chạy id {rid}."
    ra = [f"{r['name']} ({r['slug']}) · {r['nhan']} · bắt đầu {_gio(r['started_at'])}"
          + (f" · xong {_gio(r['finished_at'])}" if r.get("finished_at") else ""),
          f"Đầu vào: {r['input'] or '(trống)'}"]
    for s in r.get("steps") or []:
        kc = "" if s.get("verified") is None else (" · kiểm chứng đạt" if s.get("verified") else " · kiểm chứng CHƯA đạt")
        ra.append(f"Bước {int(s.get('i', 0)) + 1} · {s.get('agent') or '?'}{kc}: {s.get('task') or ''}")
        if s.get("output"):
            ra.append("  -> " + str(s["output"])[:800])
        if s.get("error"):
            ra.append("  lỗi: " + str(s["error"]))
    if r.get("error"):
        ra.append(f"Lỗi: {r['error']}")
    ra.append("Kết quả cuối:\n" + (str(r.get("output") or "")[:_TRAN_OUT] or "(không có)"))
    return "\n".join(ra)


async def _chay(args, ctx) -> str:
    op = str((args or {}).get("op") or "").strip().lower()
    if op == "runs":
        return _liet_ke(args, ctx)
    if op == "show":
        return _xem(args, ctx)
    return "ERROR: op phải là 'runs' (liệt kê lần chạy) hoặc 'show' (xem một lần)."


def register(ctx):
    ctx.register_tool(
        "javis_workflow",
        "Lịch sử chạy quy trình (workflow). op=runs: các lần chạy gần nhất, mới trước, lọc theo "
        "slug nếu có, limit mặc định 10. op=show: một lần chạy đầy đủ (đầu vào, từng bước, kết quả) "
        "theo id. Dùng khi người dùng hỏi quy trình vừa chạy ra sao, kết quả lần trước, hay quy "
        "trình nào đang chờ duyệt. Chỉ đọc; muốn chạy quy trình thì dùng javis_task với route "
        "wf:<slug> hoặc trang Cộng sự.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["runs", "show"]},
                "slug": {"type": "string", "description": "Lọc theo quy trình (op=runs)"},
                "limit": {"type": "integer", "description": "Số lần tối đa (op=runs)"},
                "id": {"type": "string", "description": "Id lần chạy (op=show)"},
            },
            "required": ["op"],
        },
        min_mode="readonly",
        emoji="🧾",
    )
