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

import localefmt
import workflow_runs

_LIST_MAX = 20
_TRAN_OUT = 6000       # kết quả cuối (op=show) in ra tool: engine API cắt 8000, chừa chỗ phần còn lại
_TRAN_BUOC = 12        # số bước tối đa in ra ở op=show - quy trình dài hàng chục bước là có thật
_TRAN_TASK = 300       # việc của 1 bước, hiển thị trong danh sách chứ không phải xem đủ
_TRAN_LOI_BUOC = 400   # lỗi của 1 bước
_TRAN_LOI_DONG = 200   # lỗi hiển thị trong 1 dòng op=runs - liệt kê nhiều lần chạy, không phải xem đủ 1 lần
_TRAN_TOAN = 7500      # trần CẢ chuỗi trả về (runs lẫn show) - nhiều lần chạy lỗi dài cộng lại vẫn có thể
                       # vượt 8000 mà engine API cắt, nên phải tự cắt trước và báo rõ đã cắt


def _cat(s, n: int) -> str:
    return str(s or "")[:n]


def _cat_toan(s: str) -> str:
    """Cắt CẢ chuỗi trả về ở trần chung, không để một lần chạy lỗi dài nuốt hết phần còn lại."""
    if len(s) <= _TRAN_TOAN:
        return s
    return s[:_TRAN_TOAN] + "\n... (cắt bớt)"


def _khoa(ctx) -> str:
    return str(Path(ctx.vault_root).resolve())


def _gio(ts: float) -> str:
    # Máy chủ Docker chạy giờ UTC, không phải giờ Việt Nam, nên PHẢI gắn múi giờ người dùng
    # đã chọn (localefmt) chứ không dùng datetime.fromtimestamp trần (mặc định giờ hệ thống) -
    # nếu không giờ in ra lệch đúng offset VN mỗi khi deploy trên VPS.
    try:
        return datetime.fromtimestamp(float(ts), tz=localefmt.now().tzinfo).strftime("%H:%M %d/%m")
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
                    + (f"\n  lỗi: {_cat(r['error'], _TRAN_LOI_DONG)}" if r.get("error") else ""))
    dong.append("Xem đủ một lần: op=show với id ở trên.")
    return _cat_toan("\n".join(dong))


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
    buoc = r.get("steps") or []
    # Quy trình dài hàng chục bước, mỗi bước lại có thể mang lỗi dài - liệt kê hết là tràn trần
    # chung, nên chỉ in _TRAN_BUOC bước đầu rồi báo còn bao nhiêu, giống cách op=runs báo "+N việc".
    for s in buoc[:_TRAN_BUOC]:
        kc = "" if s.get("verified") is None else (" · kiểm chứng đạt" if s.get("verified") else " · kiểm chứng CHƯA đạt")
        ra.append(f"Bước {int(s.get('i', 0)) + 1} · {s.get('agent') or '?'}{kc}: {_cat(s.get('task'), _TRAN_TASK)}")
        if s.get("output"):
            ra.append("  -> " + str(s["output"])[:800])
        if s.get("error"):
            ra.append("  lỗi: " + _cat(s["error"], _TRAN_LOI_BUOC))
    if len(buoc) > _TRAN_BUOC:
        ra.append(f"... (+{len(buoc) - _TRAN_BUOC} bước nữa)")
    if r.get("error"):
        ra.append(f"Lỗi: {r['error']}")
    ra.append("Kết quả cuối:\n" + (str(r.get("output") or "")[:_TRAN_OUT] or "(không có)"))
    return _cat_toan("\n".join(ra))


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
