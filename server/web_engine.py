"""Engine ChatGPT Web: vòng lặp tool quanh một model chỉ biết nhận chữ và trả chữ.

Vị trí trong Javis
------------------
    chatgpt-web  ->  web_engine (VÒNG LẶP TOOL của Javis)  ->  mcp_hub  ->  tool
    codex        ->  codex exec (vòng lặp NATIVE của Codex) ->  tool native

Hai engine SONG SONG. Web không chạy qua Codex, và không được phép chạy qua: `codex exec` tự
nó là một agent runtime gọi model Codex, nên đặt nó ở dưới engine Web là tiêu quota Codex đúng
cái mà người dùng chọn engine Web để tránh.

Hợp đồng sự kiện
----------------
`query()` sinh ra đúng những khoá mà `CodexCLI.query` và `claude_sdk_engine` đã dùng, nên
dashboard không phải sửa gì:

    {"type": "session", "session_id": ...}   mở luồng web mới
    {"type": "text", "content": ...}         chữ trả lời
    {"type": "tool_call", "name": ...}       đang gọi tool
    {"type": "progress", "content": ...}     dòng trạng thái ("đang hỏi vòng 3…")
    {"type": "final", "content": ...}        xong lượt
    {"type": "error", "content": ...}        hỏng

KHÔNG có `usage`: web không trả số token (spec mục 3.2), và bịa một con số là tệ hơn không có.

Vì sao vòng lặp nằm ở đây chứ không dùng lại `engine.openai_chat_with_mcp`
-------------------------------------------------------------------------
Hàm đó dựng payload theo khuôn OpenAI (`tools=[...]`, `tool_calls`) rồi gọi HTTP. Web không có
function calling và không có endpoint; hai thứ duy nhất dùng chung được là `_LapGuard` và ý
tưởng vòng lặp, và cả hai đã được mượn lại ở đây. Nhét Web vào hàm kia là bẻ một hàm đang phục
vụ sáu engine để chiều một engine khác hẳn.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator, Optional

import web_state
import web_tool_protocol as wtp

# Trần vòng tool. Số tin nhắn không phải ràng buộc (gói chat lớn), nhưng THỜI GIAN thì có:
# mỗi vòng web mất hàng chục giây. Ngân sách giờ ở dưới mới là cái phanh thật.
MAX_VONG_MAC_DINH = 30

# Ngân sách thời gian một lượt, giây. Đây là phanh chính (spec mục 5): không phải để tiết kiệm
# tin nhắn, mà để người dùng không ngồi trước màn hình im lặng mười lăm phút rồi tưởng treo.
TURN_BUDGET_MAC_DINH = 600

# Số lượt sửa khuôn cho mỗi vòng. Đúng MỘT (spec mục 19): sửa mãi là đốt thời gian vào việc
# dạy model một khuôn mà nó đang không giữ nổi.
SUA_MOI_VONG = 1

# Trần ký tự kết quả tool nhét lại vào một tin nhắn web. Engine API gửi kết quả qua trường
# `tool` riêng nên dài mấy cũng được; ở đây kết quả đi CHUNG một tin nhắn chat, nên một lệnh
# `grep` quét cả repo là đủ làm hỏng cả lượt. Cắt giữa, giữ đầu và đuôi, vì đầu là thứ model
# cần và đuôi thường là dòng tổng kết.
KET_QUA_MOT_TOOL = 6_000
KET_QUA_CA_LO = 24_000


def _tran_vong() -> int:
    import os
    try:
        n = int(os.getenv("JAVIS_WEB_MAX_TOOL_ROUNDS", str(MAX_VONG_MAC_DINH)))
    except (TypeError, ValueError):
        return MAX_VONG_MAC_DINH
    return max(1, min(n, 120))


def _ngan_sach() -> float:
    import os
    try:
        return max(30.0, float(os.getenv("JAVIS_WEB_TURN_BUDGET_S", str(TURN_BUDGET_MAC_DINH))))
    except (TypeError, ValueError):
        return float(TURN_BUDGET_MAC_DINH)


class WebEngine:
    """Engine ChatGPT Web. Cùng bề mặt ngoài với `CodexCLI`: `is_available()` và `query()`.

    `transport` tiêm từ ngoài vào để test được bằng một transport giả, không cần trình duyệt.
    """

    def __init__(self, transport=None, tools: Optional[list] = None, route: Optional[dict] = None,
                 instructions: str = "", tag: str = "chat", session_id: str = ""):
        self.transport = transport
        self.tools = list(tools or [])
        self.route = dict(route or {})
        self.instructions = instructions or ""
        self.tag = tag
        self.session_id = session_id or ""
        self.model = "chatgpt-web"
        self.provider = "chatgpt-web"
        self._huy = False

    # ---- bề mặt chung của engine ----

    def is_available(self) -> bool:
        if self.transport is None:
            return False
        try:
            import web_transport
            ok, _ = web_transport.kha_dung()
            return ok
        except Exception:
            return False

    def reset_session(self) -> None:
        self.session_id = ""
        try:
            self.transport.luong_moi()
        except Exception:
            pass

    def cancel(self) -> None:
        self._huy = True
        try:
            self.transport.dung()
        except Exception:
            pass

    # ---- prompt ----

    def _tin_dau(self, prompt: str) -> str:
        """Tin nhắn đầu của một luồng web.

        Web KHÔNG có system role (spec mục 3.2), nên mọi thứ vốn là system prompt phải nằm
        ngay trong tin nhắn này và cạnh tranh chỗ với câu hỏi. Vì thế thứ tự là: vai trò, luật
        tool, rồi mới tới câu hỏi - và KHÔNG nhét cả vũ trụ Javis vào mỗi vòng.
        """
        khuc = []
        if self.instructions.strip():
            khuc.append(self.instructions.strip())
        if self.tools:
            khuc.append(wtp.loi_dan([t.get("fn") or t.get("name") or "" for t in self.tools]))
        khuc.append(str(prompt or ""))
        return "\n\n".join(k for k in khuc if k)

    # ---- chạy tool ----

    async def _chay_mot_tool(self, call: wtp.ToolCall) -> str:
        """Chạy một tool qua `mcp_client.call_route`.

        Dùng lại hàm đó chứ không tự đọc entry của route: route của hub có BA khuôn entry
        (`call` do hub bọc sẵn, `spec`+`tool` của pool MCP, `server`+`tool` kiểu cũ), và tự
        đọc một khuôn là im lặng bỏ rơi mọi tool MCP thật.
        """
        if call.name not in self.route:
            co = ", ".join(sorted(self.route)[:20]) or "(không có tool nào)"
            return f"ERROR: không có tool '{call.name}'. Tool đang có: {co}"
        try:
            import mcp_client
            kq = await mcp_client.call_route(self.route, call.name, call.arguments)
        except Exception as e:
            # KHÔNG để exception bay ra: một tool hỏng không được giết cả lượt. Model đọc câu
            # này rồi tự đổi hướng ở vòng sau.
            return f"ERROR: tool '{call.name}' lỗi: {type(e).__name__}: {e}"
        return _cat_giua(str(kq), KET_QUA_MOT_TOOL)

    # ---- vòng lặp chính ----

    async def query(self, prompt: str) -> AsyncIterator[dict]:
        """Chạy một lượt. Sinh sự kiện theo hợp đồng chung (xem docstring đầu file)."""
        self._huy = False
        t0 = time.time()

        chan = web_state.co_chay_duoc()
        if not chan.ok:
            yield {"type": "error", "content": chan.message}
            return
        if not self.is_available():
            yield {"type": "error", "content": (
                "Engine ChatGPT Web chưa dùng được trên máy này. Kiểm tra biến môi trường "
                "JAVIS_ENABLE_WEB_CHAT và thư viện playwright.")}
            return

        tin = self._tin_dau(prompt)
        tran, ngan_sach = _tran_vong(), _ngan_sach()
        guard = _nap_lap_guard()
        final_text = ""

        for vong in range(tran):
            if self._huy:
                yield {"type": "error", "content": "Đã dừng theo yêu cầu."}
                return
            con = ngan_sach - (time.time() - t0)
            if con <= 0:
                yield {"type": "final", "content": (final_text + _het_gio(ngan_sach)).strip(),
                       "session_id": self.session_id}
                return

            yield {"type": "progress", "content": f"Đang hỏi ChatGPT Web (vòng {vong + 1})…"}
            # `self.session_id` là id cuộc chat của HỘI THOẠI NÀY. Transport dùng nó để về
            # đúng cuộc trước khi gõ - thiếu nó thì hai hội thoại Javis cùng gõ vào cuộc chat
            # đang hiện trên màn hình và hai mạch trộn làm một.
            kq = await asyncio.to_thread(
                self.transport.gui, tin, min(con, 300), None, self.session_id)

            if not kq.ok:
                web_state.ghi_hong(kq.error, kind=(kq.kind or ""))
                yield {"type": "error", "content": kq.error}
                return

            if kq.thread_id and kq.thread_id != self.session_id:
                self.session_id = kq.thread_id
                yield {"type": "session", "session_id": kq.thread_id}
            web_state.ghi_thanh_cong(self.session_id)

            kq_bóc = wtp.parse(kq.text)

            # Khuôn hỏng: đúng MỘT lượt sửa, rồi thôi.
            if kq_bóc.is_error:
                yield {"type": "progress", "content": "Khuôn gọi tool sai, đang nhờ sửa lại…"}
                tin = wtp.loi_nhac_sua(kq_bóc.error)
                sua = await asyncio.to_thread(
                    self.transport.gui, tin,
                    max(30.0, min(ngan_sach - (time.time() - t0), 300)), None, self.session_id)
                if not sua.ok:
                    web_state.ghi_hong(sua.error, kind=(sua.kind or ""))
                    yield {"type": "error", "content": sua.error}
                    return
                kq_bóc = wtp.parse(sua.text)
                if kq_bóc.is_error:
                    yield {"type": "error", "content": (
                        f"ChatGPT Web không trả đúng khuôn gọi tool sau một lượt nhắc "
                        f"({kq_bóc.error}). Thử hỏi lại bằng câu ngắn hơn, hoặc đổi sang model "
                        f"khác ở ô chọn model.")}
                    return

            if kq_bóc.is_final:
                final_text = kq_bóc.final_text
                yield {"type": "text", "content": final_text}
                yield {"type": "final", "content": final_text, "session_id": self.session_id}
                return

            # Có tool. Phanh chống kẹt vòng lặp, mượn nguyên của engine API.
            if guard is not None:
                guard.ghi([(c.name, repr(sorted((c.arguments or {}).items()))) for c in kq_bóc.calls])
                if guard.ket():
                    yield {"type": "final", "content": (final_text + _kẹt()).strip(),
                           "session_id": self.session_id}
                    return

            ten = ", ".join(c.name for c in kq_bóc.calls)
            yield {"type": "progress", "content": f"Đang chạy {len(kq_bóc.calls)} tool: {ten}"}
            cap = []
            for c in kq_bóc.calls:
                yield {"type": "tool_call", "name": c.name[:80], "item": {"arguments": c.arguments}}
                cap.append((c, await self._chay_mot_tool(c)))

            tin = _cat_giua(wtp.tin_ket_qua(cap), KET_QUA_CA_LO)
            if guard is not None:
                nhac = guard.loi_nhac()
                if nhac:
                    tin += nhac

        yield {"type": "final", "content": (final_text + _het_vong(tran)).strip(),
               "session_id": self.session_id}


def _cat_giua(s: str, tran: int) -> str:
    """Cắt giữa, giữ đầu và đuôi, và NÓI RÕ đã cắt bao nhiêu.

    Nói rõ là phần quan trọng: model đọc một đoạn bị cắt lặng lẽ sẽ tưởng đó là toàn bộ kết
    quả rồi kết luận sai trên dữ liệu thiếu.
    """
    s = str(s or "")
    if len(s) <= tran:
        return s
    dau = int(tran * 0.7)
    duoi = tran - dau
    return (s[:dau] + f"\n\n… [Javis cắt bớt {len(s) - tran} ký tự ở giữa vì quá dài cho một "
            f"tin nhắn web. Lọc hẹp hơn rồi gọi lại nếu cần phần bị cắt.] …\n\n" + s[-duoi:])


def _nap_lap_guard():
    """`_LapGuard` của engine API. Không nạp được thì chạy không có phanh, không chết."""
    try:
        import engine
        return engine._LapGuard()
    except Exception:
        return None


def _het_gio(ngan_sach: float) -> str:
    return (f"\n\n⚠ Lượt này đã chạy quá {int(ngan_sach)} giây nên phải dừng. ChatGPT Web mất "
            f"hàng chục giây mỗi vòng, nên việc nhiều bước chạy ở đây sẽ lâu. Chia nhỏ yêu "
            f"cầu, hoặc đổi sang Codex ở ô chọn model cho việc coding nhiều vòng.")


def _het_vong(tran: int) -> str:
    return (f"\n\n⚠ Đã chạy hết {tran} vòng gọi tool nên phải dừng, câu trả lời ở trên có thể "
            f"còn dở. Chia nhỏ yêu cầu, hoặc nâng JAVIS_WEB_MAX_TOOL_ROUNDS rồi khởi động lại.")


def _kẹt() -> str:
    return ("\n\n⚠ ChatGPT Web gọi lại cùng tool với cùng tham số nhiều vòng liên tiếp (kẹt "
            "vòng lặp) nên Javis dừng lượt này. Thử hỏi lại và nói rõ hơn yêu cầu.")
