"""Chat với cộng sự: phần THUẦN (không I/O) của trang Cộng sự.

Hai việc:
1. `persona_cua_phien`: đọc cột `channel` của một phiên ra ("agent"|"workflow", slug). main.py
   dùng nó ở bộ điều phối lượt để rẽ nhánh: phiên trợ lý đổi system prompt, phiên quy trình
   chạy `execute_workflow` thay vì hỏi bộ não chính.
2. Quy trình chạy như một lượt chat: `chay()` tiêu thụ luồng sự kiện của execute_workflow,
   đẩy khung WebSocket cho khung chat (status) và cột phải (wf_event), rồi trả về kết quả
   để main.py dựng tin trả lời bằng `tin_xong` / `tin_loi` / `tin_cho_duyet`. Tách khỏi
   main.py để test được bằng một generator giả, không cần engine.

Luật quan trọng: một lần chạy KHÔNG BAO GIỜ kết thúc mà không có tin trong chat. Luồng đứt
(engine chết không kịp phát `error`) vẫn thành `trang_thai="error"` với câu lỗi rõ.

Ghi chú: KHÔNG dùng ký tự em dash.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

TRAN_KET_QUA_TRUOC = 8000
_LOAI = ("agent", "workflow")


def persona_cua_phien(row: Optional[dict]) -> Optional[Tuple[str, str]]:
    ch = str((row or {}).get("channel") or "")
    for loai in _LOAI:
        tien_to = loai + ":"
        if ch.startswith(tien_to) and len(ch) > len(tien_to):
            return loai, ch[len(tien_to):]
    return None


def ghep_dau_vao(user_message: str, ket_qua_truoc: str) -> str:
    """Tin sau trong cùng hội thoại vẫn hiểu được "sửa đoạn 2": nối kết quả lần trước vào."""
    u = str(user_message or "")
    k = str(ket_qua_truoc or "")
    if not k:
        return u
    return f"{u}\n\n# Kết quả lần trước\n{k[:TRAN_KET_QUA_TRUOC]}"


def tin_xong(so_lan: int, so_buoc: int, giay: int, ket_qua: str) -> str:
    than = str(ket_qua or "").strip() or "(quy trình xong nhưng không có nội dung)"
    return f"Lần chạy #{int(so_lan)} · {int(so_buoc)} bước · {int(giay)} giây\n\n{than}"


def tin_loi(i: Optional[int], agent: str, loi: str) -> str:
    loi = str(loi or "").strip() or "không rõ lý do"
    if i is None:
        return f"Quy trình dừng vì lỗi: {loi}"
    ten = f" ({agent})" if agent else ""
    return f"Quy trình dừng ở bước {int(i) + 1}{ten}: {loi}"


def tin_cho_duyet(node: str, prompt: str) -> str:
    p = str(prompt or "").strip()
    dau = f"Quy trình đang chờ duyệt bước \"{node}\""
    return (dau + (f": {p}" if p else "") + ". Bấm Duyệt ở cột phải để chạy tiếp.")


async def chay(events, emit: Callable[[dict], Awaitable[None]]) -> Dict[str, Any]:
    """Tiêu thụ luồng sự kiện của một lần chạy. `emit(frame)` gửi khung về trình duyệt.

    Khung phát ra:
    - `status` mỗi khi một bước bắt đầu (chip "đang làm" của khung chat);
    - `wf_event` cho MỌI sự kiện trừ `step_text` (cột phải vẽ tiến độ; step_text quá dày và
      cột phải không hiện chữ từng bước).
    Không phát `stream`: main.py gửi cả tin trả lời một lần sau khi có kết quả, để bong bóng
    sống và bản lưu giống hệt nhau.
    """
    kq: Dict[str, Any] = {"trang_thai": "error", "ket_qua": "", "so_buoc": 0, "loi": None,
                          "wait": None, "run_id": ""}
    agent_cua_buoc: Dict[int, str] = {}
    buoc_dang_chay: Optional[int] = None
    da_ket = False
    try:
        async for ev in events:
            t = ev.get("type")
            if t == "start":
                kq["so_buoc"] = int(ev.get("steps") or 0)
                kq["run_id"] = str(ev.get("run_id") or "")
            elif t == "step_start":
                i = int(ev.get("i") or 0)
                buoc_dang_chay = i
                agent_cua_buoc[i] = str(ev.get("agent") or "")
                tong = kq["so_buoc"] or (i + 1)
                await emit({"type": "status", "content": f"Bước {i + 1}/{tong}: {agent_cua_buoc[i]} đang làm..."})
            elif t == "done":
                kq["trang_thai"] = "done"
                kq["ket_qua"] = str(ev.get("result") or "")
                da_ket = True
            elif t == "error":
                # Lỗi của MỘT BƯỚC mang sẵn `i` và `agent` (main.py gắn khi bước hỏng): tin
                # theo nó trước. Chỉ rơi về "bước đang chạy" khi lỗi không thuộc bước nào
                # (không tìm thấy workflow, luồng đứt) - lúc đó `i` vắng mặt.
                i_loi = ev.get("i")
                i_loi = buoc_dang_chay if i_loi is None else int(i_loi)
                kq["trang_thai"] = "error"
                kq["loi"] = {"i": i_loi,
                             "agent": str(ev.get("agent") or agent_cua_buoc.get(
                                 i_loi if i_loi is not None else -1, "")),
                             "content": str(ev.get("content") or "")}
                da_ket = True
            elif t == "wait_user":
                kq["trang_thai"] = "waiting"
                kq["wait"] = dict(ev)
                da_ket = True
            if t != "step_text":
                await emit({"type": "wf_event", "event": dict(ev)})
    finally:
        aclose = getattr(events, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:
                pass
    if not da_ket:
        kq["trang_thai"] = "error"
        kq["loi"] = {"i": buoc_dang_chay, "agent": agent_cua_buoc.get(buoc_dang_chay if buoc_dang_chay is not None else -1, ""),
                     "content": "luồng chạy không kết thúc (engine dừng mà không báo)"}
    return kq
