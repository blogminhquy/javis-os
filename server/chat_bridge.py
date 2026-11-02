"""Javis Gate: một AI bên ngoài (ChatGPT, Claude...) đọc và nhắn vào hội thoại của Javis như chủ gõ tay.

Vì sao có module này (0.440.0)
------------------------------
Gói "Javis trong ChatGPT" (nay là Javis Gate) cho ChatGPT gọi tool của Javis qua MCP. Khi ChatGPT
muốn Javis LÀM một việc, đường duy nhất là `javis_task`: việc rơi vào Kanban và chạy ngầm. Người
dùng báo (02/11): không biết việc đó đang chạy, đã dừng hay vẫn sống, và Javis không học được gì
vì trao đổi giữa hai bên không đi qua khung chat, mà vòng tự học chỉ đọc khung chat.

Module này cho cửa Gate bốn tool: tìm hội thoại, đọc hội thoại, GỬI tin vào một hội thoại, và chờ
câu trả lời. Tin gửi vào đi ĐÚNG con đường của khung chat web (`main._chat_socket`) qua một kết
nối ảo, nên lượt đó giống hệt khi chủ gõ: chữ chạy trên mọi tab đang mở, có nút Dừng, lưu vào
kho phiên, ghi `memory/conversations` và vào hàng đợi tự học. Không có bản thứ hai của vòng chat.

Ranh giới
---------
- Bốn tool chỉ hiện ở cửa Gate (`mcp_hub.tra_loi_jsonrpc(gate=...)`), không bao giờ ở danh sách
  tool của chính Javis: Javis tự nhắn vào hội thoại của mình là vòng lặp, không phải tính năng.
- Tool GỬI chỉ có ở mức Toàn quyền: một lượt chat của chủ chạy với quyền của chủ, nên mức Chỉ đọc
  hay Ghi nháp mà gửi được là đi vòng qua chính mức quyền đó.
- Chỉ gửi vào hội thoại của CHỦ (khung Trò chuyện, chat với Cộng sự). Không đọc, không gửi vào
  hội thoại của khách (bot chuyên trách) hay phiên nhóm.
- Tin gửi vào mang khối `[GỬI QUA JAVIS GATE: <nguồn>...]` ở đầu, cùng quy ước với các khối ngữ
  cảnh khác: model biết tin từ đâu tới, giao diện gỡ khối ra và hiện nhãn "từ ChatGPT".
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional

KHOI_GATE = "[GỬI QUA JAVIS GATE:"
MAX_TIN = 7000            # steer_inbox.MAX_CHARS là 8000, chừa chỗ cho khối nguồn
MAX_CHU_MOT_TIN = 4000    # mỗi tin khi đọc hội thoại
MAX_TRA_VE = 14000        # tổng chữ một lần trả về cho AI bên ngoài
CHO_MAC_DINH = 25         # giây; client MCP không chờ một lần gọi quá lâu
CHO_TOI_DA = 50
_NGUON_RE = re.compile(r"^\s*\[GỬI QUA JAVIS GATE: ([^.\]\n]{1,40})")

# main gắn vào lúc nạp (`gan`). Lấy LƯỜI qua hàm vì test thay `main._CHAT_RUNTIME` sau khi nạp.
_HOST: Dict[str, Callable] = {}


def gan(chay_socket: Callable, runtime: Callable) -> None:
    """main gọi một lần: `chay_socket(ws)` là vòng nhận tin của khung chat, `runtime()` trả `_CHAT_RUNTIME`."""
    _HOST["chay"] = chay_socket
    _HOST["runtime"] = runtime


def _store():
    import sessions
    return sessions.get_store()


def _rt():
    return _HOST["runtime"]()


# ─────────────────────────── nguồn và khối ───────────────────────────

def ten_nguon(gia_tri: Any) -> str:
    """Tên AI gửi tin, gọn và an toàn để đặt trong khối: một dòng, không ngoặc vuông, không dấu chấm."""
    s = re.sub(r"[\[\]\r\n.]", " ", str(gia_tri or "")).strip()
    s = re.sub(r"\s+", " ", s)[:40].strip()
    return s or "AI"


def khoi(nguon: str) -> str:
    n = ten_nguon(nguon)
    return (f"{KHOI_GATE} {n}. Chủ trao đổi với {n} rồi nhờ {n} gửi tin này vào hội thoại. "
            f"Làm như chủ vừa gõ và trả lời ngay tại đây.]\n\n")


def nguon_cua(noi_dung: str) -> str:
    """Tên nguồn nếu tin này gửi qua Gate, rỗng nếu chủ tự gõ."""
    m = _NGUON_RE.match(str(noi_dung or ""))
    return m.group(1).strip() if m else ""


# ─────────────────────────── kênh ───────────────────────────

def doc_duoc(kenh: Any) -> bool:
    """Hội thoại của chủ thì đọc được; hội thoại của khách và phiên nhóm thì không."""
    k = str(kenh or "")
    return not k.startswith(("bot:", "team:", "teammate:"))


def gui_duoc(kenh: Any) -> bool:
    """Chỉ khung Trò chuyện và chat với Cộng sự: hai nơi một lượt chủ gõ chạy qua vòng chat web."""
    k = str(kenh or "web")
    return k in ("web", "") or k.startswith("agent:")


# ─────────────────────────── tiện ích ───────────────────────────

def _gap(s: str) -> str:
    """Bỏ dấu, viết thường, gộp khoảng trắng: "Viết Web" khớp "viet web"."""
    s = unicodedata.normalize("NFD", str(s or "").replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.lower()).strip()


def _gio(ts: Any) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return ""


def _sach(m: dict) -> str:
    import share_render
    if m.get("role") == "user":
        return share_render.chu_nguoi_go(m.get("content") or "")
    return share_render.chu_javis_hien(m.get("content") or "")


def _cat(s: str, n: int) -> str:
    s = str(s or "")
    return s if len(s) <= n else s[:n].rstrip() + " …"


def _dang_chay(sid: str) -> bool:
    try:
        return bool(_rt().get_job(sid))
    except Exception:
        return False


def _the(row: dict) -> dict:
    return {"id": row.get("id") or row.get("session_id"), "title": row.get("title") or "",
            "updated": _gio(row.get("updated_at")), "channel": row.get("channel") or "web",
            "messages": int(row.get("msg_count") or 0),
            "running": _dang_chay(str(row.get("id") or row.get("session_id") or ""))}


# ─────────────────────────── bốn việc ───────────────────────────

def tim(q: str = "", limit: int = 10) -> dict:
    """Tìm hội thoại theo TÊN trước (khớp mọi từ, không phân biệt dấu), rồi theo nội dung tin.
    Không có từ khoá thì trả các hội thoại mới nhất của khung Trò chuyện."""
    st = _store()
    limit = max(1, min(int(limit or 10), 30))
    q = str(q or "").strip()
    if not q:
        return {"ok": True, "results": [_the(r) for r in st.list_sessions(limit=limit)]}
    tu = _gap(q).split()
    ra, da = [], set()
    for r in st.list_sessions(limit=400, channel="*"):
        if not doc_duoc(r.get("channel")):
            continue
        ten = _gap(r.get("title") or "")
        if tu and all(t in ten for t in tu):
            ra.append(_the(r))
            da.add(r["id"])
    try:
        tim_noi_dung = st.search(q, limit=40)
    except Exception:
        tim_noi_dung = []
    for r in tim_noi_dung:
        sid = r.get("session_id")
        if not sid or sid in da or len(ra) >= limit:
            continue
        row = st.get_session(sid) or {}
        if not row or not doc_duoc(row.get("channel")):
            continue
        the = _the(row)
        the["match"] = _cat(re.sub(r"\s+", " ", str(r.get("snippet") or "")), 160)
        ra.append(the)
        da.add(sid)
    return {"ok": True, "results": ra[:limit]}


def doc(sid: str, n: int = 20) -> dict:
    """N tin cuối của một hội thoại, đã gỡ khối ngữ cảnh và khối điều khiển."""
    st = _store()
    row = st.get_session(str(sid or ""))
    if not row or not doc_duoc(row.get("channel")):
        return {"ok": False, "error": "conversation not found"}
    n = max(1, min(int(n or 20), 60))
    tin = [m for m in st.get_messages(row["id"]) if m.get("role") in ("user", "assistant")]
    ra: List[dict] = []
    tong = 0
    for m in reversed(tin):
        chu = _sach(m)
        if not chu.strip():
            continue
        chu = _cat(chu, MAX_CHU_MOT_TIN)
        if tong + len(chu) > MAX_TRA_VE and ra:
            break
        tong += len(chu)
        muc = {"id": m.get("id"), "role": m.get("role"), "time": _gio(m.get("ts")), "text": chu}
        nguon = nguon_cua(m.get("content") or "") if m.get("role") == "user" else ""
        if nguon:
            muc["via"] = nguon
        ra.append(muc)
        if len(ra) >= n:
            break
    ra.reverse()
    return {"ok": True, "id": row["id"], "title": row.get("title") or "",
            "running": _dang_chay(row["id"]), "messages": ra,
            "older_messages": max(0, len(tin) - len(ra))}


class _KetNoiAo:
    """WebSocket giả cho `_chat_socket`: trao đúng MỘT gói tin rồi ngắt.

    Ngắt ngay sau khi gửi là đúng ý: vòng chat coi WebSocket chỉ là người xem, job của lượt sống
    trong `_CHAT_RUNTIME` và chạy tiếp tới cuối. `nhan` giữ mọi gói server gửi cho kết nối này
    trong lúc nó còn nối, để bắt lời từ chối (phiên đang bận, lỗi) ngay tại chỗ."""

    def __init__(self, goi: dict):
        self._goi = [json.dumps(goi, ensure_ascii=False)]
        self.nhan: List[dict] = []
        self.cookies: Dict[str, str] = {}

    async def accept(self):
        return None

    async def receive_text(self):
        if self._goi:
            return self._goi.pop(0)
        from starlette.websockets import WebSocketDisconnect
        raise WebSocketDisconnect()

    async def send_text(self, s):
        try:
            self.nhan.append(json.loads(s))
        except Exception:
            pass

    async def close(self, code: int = 1000):
        return None


def _ma_cuoi(st, sid: str) -> int:
    return max((int(m.get("id") or 0) for m in st.get_messages(sid)), default=0)


async def gui(sid: str, text: str, nguon: str) -> dict:
    """Đưa một tin vào hội thoại như chủ gõ. Phiên đang trả lời thì tin thành tin GÕ THÊM (lượt đang
    chạy đọc nó, hoặc nó chạy ngay sau lượt đó), y như chủ gõ thêm trong lúc Javis đang làm."""
    if "chay" not in _HOST:
        return {"ok": False, "error": "chat bridge is not ready"}
    st = _store()
    row = st.get_session(str(sid or ""))
    if not row or not doc_duoc(row.get("channel")):
        return {"ok": False, "error": "conversation not found"}
    if not gui_duoc(row.get("channel")):
        return {"ok": False, "error": "this conversation does not take messages from outside "
                                      "(only the main chat and partner chats do)"}
    text = str(text or "").strip()
    if not text:
        return {"ok": False, "error": "message is empty"}
    if len(text) > MAX_TIN:
        return {"ok": False, "error": f"message is too long ({len(text)} > {MAX_TIN} characters)"}
    noi_dung = khoi(nguon) + text
    truoc = _ma_cuoi(st, row["id"])
    dang_chay = _dang_chay(row["id"])
    if dang_chay:
        goi = {"action": "steer", "session_id": row["id"], "message": noi_dung, "client_id": "gate"}
    else:
        goi = {"message": noi_dung, "brain": row.get("brain") or "brain", "session_id": row["id"]}
    # Báo các tab đang mở TRƯỚC khi lượt chạy: tab nào đang xem hội thoại này vẽ bong bóng tin
    # (kèm nhãn nguồn) ngay, rồi mới tới chữ trả lời chạy dần.
    try:
        await _rt().publish({"type": "external_message", "session_id": row["id"],
                             "content": noi_dung, "source": ten_nguon(nguon)})
    except Exception:
        pass
    ws = _KetNoiAo(goi)
    await _HOST["chay"](ws)
    loi = next((e for e in ws.nhan if e.get("type") == "error" and e.get("session_id") == row["id"]), None)
    if loi:
        return {"ok": False, "error": str(loi.get("content") or "rejected")}
    if not dang_chay and not _dang_chay(row["id"]) and _ma_cuoi(st, row["id"]) <= truoc:
        return {"ok": False, "error": "Javis did not take the message"}
    return {"ok": True, "id": row["id"], "title": row.get("title") or "",
            "mode": "queued" if dang_chay else "started", "after_id": truoc}


async def ket_qua(sid: str, after_id: int = 0, cho: float = CHO_MAC_DINH) -> dict:
    """Chờ tối đa `cho` giây cho lượt xong, rồi trả các câu Javis viết sau tin `after_id`."""
    st = _store()
    row = st.get_session(str(sid or ""))
    if not row or not doc_duoc(row.get("channel")):
        return {"ok": False, "error": "conversation not found"}
    cho = max(0.0, min(float(cho if cho is not None else CHO_MAC_DINH), CHO_TOI_DA))
    het = time.monotonic() + cho
    while True:
        chay = _dang_chay(row["id"])
        if chay and time.monotonic() < het:
            await asyncio.sleep(0.5)
            continue
        if not chay:
            # Tin gõ thêm chạy thành lượt RIÊNG ngay sau lượt đang chạy, cách nhau một nhịp ngắn
            # (`_start_steer_turn` đợi job cũ dứt). Nhìn lại một lần để không báo "xong" giữa hai lượt.
            await asyncio.sleep(1.0)
            chay = _dang_chay(row["id"])
            if chay and time.monotonic() < het:
                continue
        break
    after_id = int(after_id or 0)
    tra_loi = [_sach(m) for m in st.get_messages(row["id"])
               if m.get("role") == "assistant" and int(m.get("id") or 0) > after_id]
    tra_loi = [t for t in tra_loi if t.strip()]
    chu = _cat("\n\n".join(tra_loi), MAX_TRA_VE)
    if chay:
        job = _rt().get_job(row["id"])
        dang_viet = _cat(str(getattr(job, "text", "") or "")[-3000:], 3000)
        return {"ok": True, "status": "running", "answer_so_far": chu, "writing_now": dang_viet,
                "hint": "Javis is still working. Call javis_chat_result again with the same after_id."}
    if not chu:
        return {"ok": True, "status": "no_answer",
                "hint": "The turn ended without a reply (stopped, or an error). Read the conversation."}
    return {"ok": True, "status": "done", "answer": chu}


# ─────────────────────────── tool cho cửa Gate ───────────────────────────

_ID = {"type": "string", "description": "Conversation id from javis_chat_find."}

TOOLS: Dict[str, dict] = {
    "javis_chat_find": {
        "full_only": False,
        "description": (
            "Find the owner's Javis conversations by title (accents ignored) or by words in their messages. "
            "Empty query lists the most recent chats. Use this first when the owner names a chat "
            "(for example 'the Viet Web chat')."),
        "schema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Words from the chat title or content. Empty = latest chats."},
            "limit": {"type": "integer", "description": "Max results, 1-30 (default 10)."}}},
    },
    "javis_chat_read": {
        "full_only": False,
        "description": (
            "Read the last messages of one Javis conversation, oldest first, so you can advise the owner "
            "on what to do next. 'running' tells whether Javis is answering right now."),
        "schema": {"type": "object", "required": ["id"], "properties": {
            "id": _ID, "last": {"type": "integer", "description": "How many recent messages, 1-60 (default 20)."}}},
    },
    "javis_chat_send": {
        "full_only": True,
        "description": (
            "Post a message into a Javis conversation as if the owner typed it there, so Javis does the work "
            "in that chat: the owner watches it live, can press Stop, and Javis learns from it. Only send "
            "after the owner agreed. Start the message with one line on what the owner approved and why, "
            "then the instruction. Waits up to wait_seconds for the reply; if Javis is still working, call "
            "javis_chat_result with the returned after_id. Prefer this over javis_task for work in a chat."),
        "schema": {"type": "object", "required": ["id", "message"], "properties": {
            "id": _ID,
            "message": {"type": "string", "description": "The instruction for Javis, in the owner's language."},
            "wait_seconds": {"type": "integer",
                             "description": f"Seconds to wait for the reply, 0-{CHO_TOI_DA} (default {CHO_MAC_DINH})."}}},
    },
    "javis_chat_result": {
        "full_only": False,
        "description": (
            "Wait for and return Javis's reply after javis_chat_send. status: done (answer), running (call again), "
            "no_answer (stopped or failed). If it keeps running past your patience, tell the owner the result "
            "will appear in the Javis chat and they can ask you to check again later."),
        "schema": {"type": "object", "required": ["id", "after_id"], "properties": {
            "id": _ID,
            "after_id": {"type": "integer", "description": "after_id returned by javis_chat_send."},
            "wait_seconds": {"type": "integer",
                             "description": f"Seconds to wait, 0-{CHO_TOI_DA} (default {CHO_MAC_DINH})."}}},
    },
}


def _du_quyen(mode: str) -> bool:
    return str(mode or "").strip().lower() == "full"


def tool_specs(mode: str) -> List[dict]:
    """Dạng tool của hub (`fn`, `description`, `schema`). Tool GỬI chỉ hiện ở mức Toàn quyền."""
    return [{"fn": ten, "description": t["description"], "schema": t["schema"]}
            for ten, t in TOOLS.items() if _du_quyen(mode) or not t["full_only"]]


def _so(v: Any, mac_dinh: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return mac_dinh


async def goi_tool(ten: str, args: Optional[dict], mode: str, nguon: str) -> str:
    """Chạy một tool Gate, trả chuỗi (JSON) như mọi tool của hub. Lỗi bắt đầu bằng `ERROR:`."""
    a = args if isinstance(args, dict) else {}
    t = TOOLS.get(ten)
    if not t:
        return f"ERROR: unknown tool {ten}"
    if t["full_only"] and not _du_quyen(mode):
        return ("ERROR: sending into Javis chats needs the Full access level. The owner can raise it on the "
                "Javis Gate page in Javis (Plugins, Javis Gate, Open page).")
    try:
        if ten == "javis_chat_find":
            kq = tim(a.get("query") or "", _so(a.get("limit"), 10))
        elif ten == "javis_chat_read":
            kq = doc(str(a.get("id") or ""), _so(a.get("last"), 20))
        elif ten == "javis_chat_send":
            kq = await gui(str(a.get("id") or ""), str(a.get("message") or ""), nguon)
            if kq.get("ok"):
                cho = _so(a.get("wait_seconds"), CHO_MAC_DINH)
                if cho > 0:
                    kq["result"] = await ket_qua(kq["id"], kq["after_id"], cho)
        else:
            kq = await ket_qua(str(a.get("id") or ""), _so(a.get("after_id"), 0),
                               _so(a.get("wait_seconds"), CHO_MAC_DINH))
    except Exception as e:  # noqa: BLE001 - lỗi phải về tới AI bên ngoài, không làm sập hub
        return f"ERROR: {type(e).__name__}: {e}"
    if not kq.get("ok"):
        return "ERROR: " + str(kq.get("error") or "failed")
    return json.dumps(kq, ensure_ascii=False)
