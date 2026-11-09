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

Ghi chép (0.441.0)
------------------
Chủ dự án 02/11: "chat ở bên nào thì cũng copy hội thoại đấy vào Javis để có ngữ cảnh". Javis không
đọc được lịch sử chat của ChatGPT hay Claude (chúng chỉ gửi sang thứ chúng tự truyền vào lúc gọi
tool), nên tool thứ năm `javis_chat_note` để AI bên ngoài tự ghi lại phần đáng giữ: chủ hỏi gì, đã
chốt gì, vì sao. Ghi chép KHÔNG chạy lượt nào của Javis (không tốn hạn mức bộ não), nhưng đi qua đúng
đường lưu lượt chat (`main._persist_turn`): vào Lịch sử, `memory/conversations` và vòng tự học. Mỗi
cuộc chat bên ngoài có một hội thoại riêng "Từ ChatGPT: <tên>", hoặc ghi thẳng vào một hội thoại có
sẵn của Javis khi AI đưa `id`.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional

from config import STATE_DIR
import localefmt

KHOI_GATE = "[GỬI QUA JAVIS GATE:"
MAX_TIN = 7000            # steer_inbox.MAX_CHARS là 8000, chừa chỗ cho khối nguồn
MAX_CHU_MOT_TIN = 4000    # mỗi tin khi đọc hội thoại
MAX_TRA_VE = 14000        # tổng chữ một lần trả về cho AI bên ngoài
CHO_MAC_DINH = 25         # giây; client MCP không chờ một lần gọi quá lâu
CHO_TOI_DA = 50
_NGUON_RE = re.compile(r"^\s*\[GỬI QUA JAVIS GATE: ([^.\]\n]{1,40})")
MAX_GHI_CHEP = 4000       # mỗi trường của một ghi chép
SO_GHI_CHEP = STATE_DIR / "gate-notes.json"   # {"<nguồn>|<tên cuộc chat đã gập>": mã hội thoại}

# main gắn vào lúc nạp (`gan`). Lấy LƯỜI qua hàm vì test thay `main._CHAT_RUNTIME` sau khi nạp.
_HOST: Dict[str, Callable] = {}


def gan(chay_socket: Callable, runtime: Callable, luu_luot: Optional[Callable] = None) -> None:
    """main gọi một lần: `chay_socket(ws)` là vòng nhận tin của khung chat, `runtime()` trả `_CHAT_RUNTIME`,
    `luu_luot(sid, brain, tin_chu, tra_loi)` (async) lưu một lượt đã có sẵn câu trả lời qua đúng đường lưu lượt
    chat (Lịch sử, nhật ký, tự học) và trả mã tin của câu trả lời."""
    _HOST["chay"] = chay_socket
    _HOST["runtime"] = runtime
    if luu_luot is not None:
        _HOST["luu"] = luu_luot


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


def khoi_ghi_chep(nguon: str) -> str:
    """Khối đầu của một ghi chép: cùng tiền tố với `khoi` (giao diện gỡ khối, hiện nhãn nguồn), nhưng nói rõ
    với model đây là ghi chép để nắm ngữ cảnh, không phải yêu cầu làm gì."""
    n = ten_nguon(nguon)
    return (f"{KHOI_GATE} {n}. Ghi chép từ cuộc chat của chủ trên {n}, để Javis nắm ngữ cảnh và nhớ "
            f"quyết định của chủ; không phải yêu cầu làm việc.]\n\n")


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
    """A message time in the owner's timezone (Settings), not the server clock: a VPS runs on UTC."""
    return localefmt.format_ts(ts, "%Y-%m-%d %H:%M")


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


# ─────────────────────────── ghi chép ───────────────────────────

def _doc_so() -> Dict[str, str]:
    try:
        d = json.loads(SO_GHI_CHEP.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _ghi_so(d: Dict[str, str]) -> None:
    SO_GHI_CHEP.parent.mkdir(parents=True, exist_ok=True)
    tam = SO_GHI_CHEP.with_suffix(".json.tmp")
    tam.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tam.replace(SO_GHI_CHEP)


def _phien_ghi_chep(st, nguon: str, ten: str) -> str:
    """Hội thoại "Từ <nguồn>: <tên>" của một cuộc chat bên ngoài: dùng lại nếu đã có (sổ `SO_GHI_CHEP`), mở mới
    nếu chưa có hoặc chủ đã xoá. Mở trong brain của hội thoại gần nhất, như mọi công cụ Gate khác."""
    nguon = ten_nguon(nguon)
    khoa = f"{nguon}|{_gap(ten)}"
    so = _doc_so()
    sid = so.get(khoa, "")
    if sid and st.get_session(sid):
        return sid
    gan_nhat = (st.list_sessions(limit=1) or [{}])[0]
    import localefmt
    tieu_de = localefmt.chu(f"Từ {nguon}: {ten}", f"From {nguon}: {ten}")
    sid = st.create_session(brain=gan_nhat.get("brain") or "brain", engine="gate", model=nguon,
                            title=_cat(tieu_de, 80), channel="web")
    so[khoa] = sid
    _ghi_so(so)
    return sid


def noi_dung_ghi_chep(nguon: str, hoi: str, tra_loi: str, chot: str) -> str:
    n = ten_nguon(nguon)
    phan = [khoi_ghi_chep(n).rstrip("\n")]
    if hoi:
        phan.append(f"**Chủ nói:** {hoi}")
    if tra_loi:
        phan.append(f"**{n} trả lời:** {tra_loi}")
    if chot:
        phan.append(f"**Chủ đã chốt:** {chot}")
    return "\n\n".join(phan)


async def ghi_chep(nguon: str, ten: str = "", hoi: str = "", tra_loi: str = "", chot: str = "",
                   sid: str = "") -> dict:
    """Lưu một ghi chép của AI bên ngoài vào Javis. KHÔNG chạy lượt nào của Javis."""
    if "luu" not in _HOST:
        return {"ok": False, "error": "chat notes are not ready"}
    hoi, tra_loi, chot = (str(x or "").strip() for x in (hoi, tra_loi, chot))
    if not (hoi or chot):
        return {"ok": False, "error": "a note needs what the owner said (asked) or decided (decided)"}
    for ten_truong, gia_tri in (("asked", hoi), ("answered", tra_loi), ("decided", chot)):
        if len(gia_tri) > MAX_GHI_CHEP:
            return {"ok": False, "error": f"{ten_truong} is too long ({len(gia_tri)} > {MAX_GHI_CHEP} characters)"}
    st = _store()
    if sid:
        row = st.get_session(str(sid)) or {}
        if not row or not gui_duoc(row.get("channel")):
            return {"ok": False, "error": "conversation not found, or it does not take notes from outside"}
        if _dang_chay(row["id"]):
            return {"ok": False, "error": "that conversation is answering right now; note again in a moment, "
                                          "or leave id out to keep the note in your own log"}
    else:
        ten = re.sub(r"\s+", " ", str(ten or "")).strip()
        if not ten:
            return {"ok": False, "error": "title is required (the name of this chat on your side) when id is not given"}
        row = st.get_session(_phien_ghi_chep(st, nguon, ten)) or {}
    import localefmt
    tin = noi_dung_ghi_chep(nguon, hoi, tra_loi, chot)
    da_ghi = localefmt.chu(f"Đã ghi lại ghi chép từ {ten_nguon(nguon)}.", f"Saved the note from {ten_nguon(nguon)}.")
    try:
        await _rt().publish({"type": "external_message", "session_id": row["id"], "content": tin,
                             "source": ten_nguon(nguon)})
    except Exception:
        pass
    mid = await _HOST["luu"](row["id"], row.get("brain") or "brain", tin, da_ghi)
    if not mid:
        return {"ok": False, "error": "the note was not saved"}
    try:
        import sessions
        await _rt().publish({"type": "push", "content": da_ghi, "session_id": row["id"], "message_id": int(mid),
                             "content_sha": sessions.content_sha(da_ghi)})
    except Exception:
        pass
    return {"ok": True, "id": row["id"], "title": row.get("title") or ""}


# ─────────────────────────── tool cho cửa Gate ───────────────────────────

_ID = {"type": "string", "description": "Conversation id from javis_chat_find."}

TOOLS: Dict[str, dict] = {
    "javis_chat_find": {
        "muc": "doc",
        "description": (
            "Find the owner's Javis conversations by title (accents ignored) or by words in their messages. "
            "Empty query lists the most recent chats. Use this first when the owner names a chat "
            "(for example 'the Viet Web chat')."),
        "schema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Words from the chat title or content. Empty = latest chats."},
            "limit": {"type": "integer", "description": "Max results, 1-30 (default 10)."}}},
    },
    "javis_chat_read": {
        "muc": "doc",
        "description": (
            "Read the last messages of one Javis conversation, oldest first, so you can advise the owner "
            "on what to do next. 'running' tells whether Javis is answering right now."),
        "schema": {"type": "object", "required": ["id"], "properties": {
            "id": _ID, "last": {"type": "integer", "description": "How many recent messages, 1-60 (default 20)."}}},
    },
    "javis_chat_send": {
        "muc": "full",
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
    "javis_chat_note": {
        "muc": "ghi",
        "description": (
            "Save a note of THIS chat into Javis so Javis keeps the context and remembers the owner's decisions. "
            "It does not run Javis and costs Javis nothing. Call it whenever the owner settles something (a "
            "decision, a choice, a plan, a fact about their business), and when a useful chat ends; not after "
            "every message. asked: what the owner said, in their own words where it matters. answered: your "
            "answer in 1-5 sentences. decided: what the owner agreed or chose, and why. title: a short name for "
            "this chat, the SAME every time in this chat so notes land together. To note into one existing "
            "Javis chat instead (for example the chat this work belongs to), pass its id."),
        "schema": {"type": "object", "required": ["asked"], "properties": {
            "title": {"type": "string", "description": "Short name of this chat on your side, stable across calls."},
            "asked": {"type": "string", "description": "What the owner said or asked."},
            "answered": {"type": "string", "description": "Your answer, short."},
            "decided": {"type": "string", "description": "What the owner decided, and why. Empty if nothing yet."},
            "id": {"type": "string", "description": "Optional: a Javis conversation id to note into instead."}}},
    },
    "javis_chat_result": {
        "muc": "doc",
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


def _du_quyen(mode: str, muc: str = "full") -> bool:
    """Mức của cửa Gate có đủ cho mức tool không. `doc`: mọi mức. `ghi` (lưu ghi chép, không làm việc ra ngoài):
    Ghi nháp và Toàn quyền. `full` (để Javis LÀM việc): chỉ Toàn quyền."""
    m = str(mode or "").strip().lower()
    if muc == "doc":
        return True
    if muc == "ghi":
        return m in ("full", "auto")
    return m == "full"


def tool_specs(mode: str) -> List[dict]:
    """Dạng tool của hub (`fn`, `description`, `schema`). Tool ghi và tool gửi chỉ hiện ở mức đủ quyền."""
    return [{"fn": ten, "description": t["description"], "schema": t["schema"]}
            for ten, t in TOOLS.items() if _du_quyen(mode, t["muc"])]


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
    if not _du_quyen(mode, t["muc"]):
        can = "Full access" if t["muc"] == "full" else "the Draft or Full access level"
        return (f"ERROR: {ten} needs {can}. The owner can raise it on the Javis Gate page in Javis "
                "(Plugins, Javis Gate, Open page).")
    try:
        if ten == "javis_chat_find":
            kq = tim(a.get("query") or "", _so(a.get("limit"), 10))
        elif ten == "javis_chat_read":
            kq = doc(str(a.get("id") or ""), _so(a.get("last"), 20))
        elif ten == "javis_chat_note":
            kq = await ghi_chep(nguon, str(a.get("title") or ""), str(a.get("asked") or ""),
                                str(a.get("answered") or ""), str(a.get("decided") or ""), str(a.get("id") or ""))
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
