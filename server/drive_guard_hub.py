"""drive_guard_hub.py - gắn drive_write_guard vào route Composio của hub, sau cờ JAVIS_DRIVE_WRITE_GUARD.

Chế độ (đọc lúc gắn route):
    off     -> trả nguyên call (mặc định).
    shadow  -> tính quyết định, ghi log, vẫn gọi tool.
    enforce -> DENY thì trả chuỗi "ERROR: ..." và KHÔNG gọi tool.

Metadata parents: prefetch BẤT ĐỒNG BỘ theo BFS qua invoker Composio đã đăng ký (mcp_hub gọi register_invoker),
invoker này gọi thẳng mcp_client.call_route, KHÔNG đi qua guard -> không đệ quy. Giới hạn số nút (MAX_NODES);
vượt giới hạn, lỗi đọc, id lạ -> DENY (fail-closed).
Actor: slug từ turn_context của lượt chat/job. Không có -> None -> DENY ghi.
"""
from __future__ import annotations

import sys
from collections import deque

import asyncio

import drive_parents as dp
import drive_write_guard as g
import team_gate

_GATED_TOOLS = frozenset({"COMPOSIO_MULTI_EXECUTE_TOOL", "COMPOSIO_PROXY_EXECUTE"}) | g._OPAQUE_EXEC
MAX_NODES = 80

_invoker = None  # async def(args) -> envelope; do mcp_hub đăng ký (không bọc guard)


def register_invoker(fn) -> None:
    global _invoker
    _invoker = fn


def _actor() -> str | None:
    """Danh tính agent của lượt: trường `actor` do host gán (Kanban/nhắc việc/nhóm), rồi tới slug trợ lý của chat.
    Không đọc tham số tool, không đọc đầu ra model. Không có -> None -> DENY ghi (fail-closed)."""
    try:
        import turn_context
        t = turn_context.current() or {}
        slug = str(t.get("actor") or "").strip()
        if not slug:
            slug = str((t.get("agent") or {}).get("slug") or "").strip()
        return slug or None
    except Exception:  # noqa: BLE001 - không đọc được -> không actor -> fail-closed
        return None


def _collect_ids(obj, out: list[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in g._ID_KEYS:
                vals = v if isinstance(v, list) else [v]
                out.extend(x for x in vals if isinstance(x, str) and x.strip())
            _collect_ids(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _collect_ids(x, out)


async def _fetch_meta(fid: str) -> dict:
    if _invoker is None:
        raise dp.DriveMetaError("chưa đăng ký invoker Composio")
    if not g.COMPOSIO_ACCOUNT:
        raise dp.DriveMetaError("chưa cấu hình composio_account (fail-closed)")
    args = {"tools": [{"tool_slug": "GOOGLEDRIVE_GET_FILE_METADATA", "account": g.COMPOSIO_ACCOUNT, "arguments": {
        "fileId": fid, "fields": "id,name,mimeType,parents,trashed,driveId", "supportsAllDrives": True}}]}
    return dp.unwrap_composio(await _invoker(args), fid)


async def prefetch_parents(seeds: list[str]) -> dict[str, list[str]]:
    """BFS toàn bộ tổ tiên của các id cho trước. Trả cache đã kiểm. Lỗi/vượt giới hạn -> raise."""
    cache: dict[str, list[str]] = {}
    queue = deque(dict.fromkeys(seeds))
    while queue:
        fid = queue.popleft()
        if fid in cache:
            continue
        if len(cache) >= MAX_NODES:
            raise dp.DriveMetaError("vượt giới hạn số thư mục cần kiểm (fail-closed)")
        cache[fid] = dp.validate_meta(fid, await _fetch_meta(fid))
        queue.extend(p for p in cache[fid] if p not in cache)
    return cache


def _probe():
    """parents_of giai đoạn 1: ghi lại id nào cần tổ tiên; trả [] (kết quả giai đoạn 1 chỉ dùng khi không thiếu gì)."""
    missing: list[str] = []

    def parents_of(fid: str) -> list[str]:
        missing.append(fid)
        return []
    return parents_of, missing


def _lookup(cache: dict[str, list[str]]):
    def parents_of(fid: str) -> list[str]:
        if fid not in cache:
            raise dp.DriveMetaError("thiếu metadata cho id (fail-closed)")
        return list(cache[fid])
    return parents_of


def refuse_gated(reason: str):
    """Hàm thay thế cho lệnh ghi Drive khi cấu hình guard lỗi: luôn trả lỗi rõ, không gọi Composio."""
    async def _refused(args):
        print(f"[drive guard] TỪ CHỐI (cấu hình lỗi): {reason}", file=sys.stderr)
        return f"ERROR: Javis chặn ghi Drive/Docs/Sheets: cấu hình guard lỗi ({reason}). Sửa cấu hình rồi khởi động lại."
    return _refused


def wrap(call, conn: dict, tool: str, fn: str = "", env=None):
    """Bọc route call của tool Composio. Trả call gốc khi off hoặc không phải tool cổng."""
    mode = g.current_mode(env)
    if mode == "off" or not call:
        return call
    up = str(tool or "").strip().upper()
    # Mọi tool COMPOSIO_* đều được bọc, trừ danh sách đọc danh mục đã biết. Tool mới bị guard quyết (fail-closed).
    gated = up in _GATED_TOOLS or (up.startswith("COMPOSIO_") and up not in g._COMPOSIO_SAFE)
    if str((conn or {}).get("connector_id") or "") != "composio" or not gated:
        return call
    # FAIL-SECURE: mode lạ, hoặc enforce/shadow mà đợt thiếu/sai -> TỪ CHỐI lệnh gated, không pass-through.
    # Không bao giờ "chỉ ghi log rồi cho qua" khi cấu hình lỗi. Chỉ sửa cấu hình rồi khởi động lại mới mở lại.
    if mode == "invalid":
        return refuse_gated(f"{g.MODE_ENV} không hợp lệ (chỉ off, shadow, enforce)")
    state, _ = g.pilot_status(env)
    if state != "ok":
        print(f"[drive guard {mode}] CẤU HÌNH LỖI: {g.PILOT_ENV} {state}. Từ chối lệnh {tool} cho đến khi sửa.",
              file=sys.stderr)
        return refuse_gated(f"{g.PILOT_ENV} {state}: đặt danh sách slug rõ ràng, không dùng '*'")

    async def _guarded(args):
        a = args if isinstance(args, dict) else {}
        actor = _actor()
        if g.outside_pilot(actor, env):
            # Agent ngoài đợt bật: không đổi hành vi (xem drive_write_guard.PILOT_ENV).
            return await call(args)
        try:
            probe, missing = _probe()
            d = g.decide(actor, str(tool), a, probe)
            if missing:  # chỉ đọc metadata khi quyết định thật sự cần tổ tiên (lệnh chỉ-đọc không gọi Drive)
                cache = await prefetch_parents(list(dict.fromkeys(missing)))
                d = g.decide(actor, str(tool), a, _lookup(cache))
        except Exception as e:  # noqa: BLE001 - fail-closed
            d = {"allow": False, "reason": f"không kiểm được quyền ghi ({type(e).__name__}: {e})"}
        print(f"[drive guard {mode}] {fn or tool}: {'ALLOW' if d['allow'] else 'DENY'} - {d['reason']}",
              file=sys.stderr)
        if g.enforce_decision(mode, d):
            if not d.get("approvable"):
                return f"ERROR: Javis chặn ghi Drive/Docs/Sheets: {d['reason']}"
            # Ngoài vùng: chỉ đi tiếp khi chủ đã duyệt ĐÚNG lệnh này cho bước đang chạy (sổ duyệt, dùng một lần).
            ok, note, hub_fp = await asyncio.to_thread(team_gate.drive_scope_check, str(fn), str(tool), a,
                                                       f"{d['reason']}")
            if not ok:
                return f"ERROR: Javis chặn ghi Drive/Docs/Sheets: {d['reason']}. {note}"
            print(f"[drive guard {mode}] {fn or tool}: owner-approved exact call, one use", file=sys.stderr)
            token = team_gate.DRIVE_PASS.set(hub_fp)
            try:
                return await call(args)
            finally:
                team_gate.DRIVE_PASS.reset(token)
        return await call(args)

    return _guarded
