"""Phần dùng chung của MỌI cổng bot nhắn tin (Telegram, Zalo, và kênh nào tới sau).

Vì sao có file này thay vì chép sang mỗi kênh một bản: hàng đợi lượt, luật `/stop`, cổng
precheck và dòng vết công cụ đều là **luật hành vi của Javis**, không phải chi tiết của một
nhà cung cấp. Chép sang bản thứ hai là bảo đảm hai bản trôi lệch, và chỗ lệch sẽ là chỗ ít
được nhìn nhất: bot chuyên trách nói chuyện với người lạ.

Ranh giới: file này KHÔNG biết gì về HTTP, endpoint hay khuôn JSON của bất kỳ nhà cung cấp
nào. Mỗi lớp kênh tự lo `_send`, `_handle_turn`, `_loop` và cách bóc tin đến; đổi lại nó
được dùng chung phần trên.
"""
from __future__ import annotations

import asyncio
import re
import sys

import localefmt
import steer_inbox

# ---- Dòng vết công cụ ----------------------------------------------------------------
MAX_VET_TOOL = 6        # số tên công cụ hiện trên dòng vết, dư thì gộp thành "+n"
# Tên công cụ nằm trong các chuỗi tiến trình do main.py bắn ra: "⚙ Đang gọi: X",
# "⚙ Đang gọi công cụ: X", "⚙ Đang dùng công cụ: X". Bắt chung một khuôn để thêm engine mới
# không phải sửa ở đây.
RE_TEN_TOOL = re.compile(r"^⚙[^:]*:\s*(.+)$")


MAX_TEN_TOOL = 40       # một tên trên dòng vết; dài hơn là đã lọt thứ không phải tên

# Loại việc → nhãn người đọc được. Cùng họ tên với LOAI trong dashboard/chat-steps.js.
_NHAN_LOAI = (
    (re.compile(r"^(bash|shell|command_execution|local_shell_call|run_shell_command|"
                r"run_terminal_command|run_command|exec)$"), "Chạy lệnh"),
    (re.compile(r"^(websearch|web_search|web_search_call|google_search|search_web)$"),
     "Tìm trên web"),
    (re.compile(r"^(webfetch|web_fetch|read_url_content|fetch_url)$"), "Đọc web"),
)
# Thứ trông như CÂU LỆNH chứ không phải tên công cụ: có khoảng trắng, hoặc là đường dẫn.
_GIONG_LENH = re.compile(r"\s|^[/\\~.]")


def nhan_ngan(ten) -> str:
    """Tên công cụ → nhãn ngắn cho dòng trạng thái/dòng vết của bot.

    Bug 2026-09-28 (Telegram, engine Codex): dòng vết in nguyên
    `/bin/sh -lc "sed -n '1,260p' skills/..."` vì Codex lấy câu lệnh làm tên. Dòng vết nằm lại
    vĩnh viễn trong chat nên chỉ được chứa TÊN việc; lệnh cụ thể không phải việc của nó.
    Tên thường (pos_statistics, Read) giữ nguyên, tên MCP bỏ tiền tố máy chủ."""
    t = str(ten or "").strip().strip("`").strip()
    if not t:
        return ""
    m = re.match(r"^mcp__.+?__(.+)$", t)
    if m:
        t = m.group(1)
    for mau, nhan in _NHAN_LOAI:
        if mau.match(t.lower()):
            return nhan
    if _GIONG_LENH.search(t):
        return "Chạy lệnh"
    return t if len(t) <= MAX_TEN_TOOL else t[:MAX_TEN_TOOL - 1] + "…"


def ten_tool(txt) -> str:
    """Bóc tên công cụ từ một chuỗi tiến trình, đã rút thành nhãn ngắn (`nhan_ngan`).
    "" nếu chuỗi đó không nói về công cụ nào."""
    m = RE_TEN_TOOL.match(str(txt or "").strip())
    return nhan_ngan(m.group(1)) if m else ""


def dong_vet(tools, giay) -> str:
    """Dòng tổng kết một lượt, thứ sẽ NẰM LẠI trong chat vĩnh viễn.

    Vì nó ở lại nên nó phải nói được một điều thật, chứ không phải một dòng rác. Lượt có gọi
    công cụ thì liệt kê tên: đó đúng là bằng chứng Javis chạm vào dữ liệu thật (POS, quảng
    cáo, file) chứ không trả lời chay. Lượt không gọi gì thì nói thẳng là trả lời trực tiếp -
    cũng là thông tin, và là thông tin người dùng cần để biết có nên tin con số vừa đọc không.
    """
    giay = max(0.0, float(giay))
    s = f"{giay:.0f}s" if giay < 60 else f"{int(giay // 60)}m{int(giay % 60):02d}s"
    if not tools:
        return f"✓ Trả lời trực tiếp · {s}"
    ten = list(tools)[:MAX_VET_TOOL]
    du = f" +{len(tools) - len(ten)}" if len(tools) > len(ten) else ""
    return "⚙ " + " · ".join(ten) + du + f" · {s}"


# ---- Whitelist -----------------------------------------------------------------------
def parse_chat_ids(raw):
    """"111, 222" hoặc [111, 222] -> ["111", "222"]. Rỗng = KHÔNG giới hạn ai."""
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        items = raw
    else:
        items = str(raw).replace(";", ",").split(",")
    return [str(x).strip() for x in items if str(x).strip()]


# ---- Hàng đợi lượt trả lời -----------------------------------------------------------
MAX_CHO_TIN = 5         # trần số tin gom lại khi bot đang bận (chống spam làm phình bộ nhớ)
MAX_CHO_KY_TU = 4000


def noi_tin(texts):
    """Gộp nhiều tin của một người thành MỘT lượt, giữ thứ tự, nối bằng xuống dòng, trong trần
    MAX_CHO_KY_TU ký tự. Dùng cho kênh tự gom ngoài hàng đợi này (Zalo cá nhân chờ khách nhắn xong).

    Khác hàng đợi lúc bot bận (giữ MAX_CHO_TIN tin ĐẦU để chống spam làm phình bộ nhớ): ở đây khách
    hay mở bằng vài câu chào rồi mới hỏi, nên giữ các tin MỚI NHẤT vừa trần ký tự. Giữ tin đầu thì
    7 tin "Thầy ơi / cho em hỏi / ..." tới bot chỉ còn 5 câu chào, mất đúng câu hỏi."""
    giu, tong = [], 0
    for t in reversed([str(x or "") for x in (texts or [])]):
        if tong + len(t) > MAX_CHO_KY_TU:
            continue
        giu.append(t)
        tong += len(t)
    return "\n".join(reversed(giu))


class HangLuot:
    """Mixin: điều phối lượt trả lời theo từng chat.

    Lớp dùng nó phải có sẵn: `_send(client, chat, text)`, `_handle_turn(client, chat, text,
    meta)`, và các thuộc tính `command_fn`, `precheck_fn`, `giau_trang_thai`, `_current`,
    `_cho`, `_stop`.
    """

    @property
    def _steer_meta(self):
        """chat -> meta of the latest message held for its running turn (created on first use: the channel classes
        build their own __init__)."""
        d = self.__dict__.get("_steer_meta_d")
        if d is None:
            d = self.__dict__["_steer_meta_d"] = {}
        return d

    def _busy(self, chat):
        t = self._current.get(chat)
        return bool(t and not t.done())

    async def _dispatch(self, client, chat, text, meta=None):
        # Lệnh bắt đầu bằng /
        if text.startswith("/"):
            head = text.split(maxsplit=1)
            cmd = head[0][1:].lower()
            arg = head[1].strip() if len(head) > 1 else ""
            # /stop xử lý NGAY - CHỈ dừng lượt của CHÍNH chat này (không đụng phiên người khác)
            if cmd == "stop":
                t = self._current.get(chat)
                if t and not t.done():
                    t.cancel()
                # Bảo dừng là dừng hẳn: bỏ luôn phần đang xếp hàng. Không xoá ở đây thì lượt
                # bị huỷ vẫn chạy tiếp mấy câu chờ - `_handle_turn` NUỐT CancelledError (nó
                # cần nuốt để khỏi gửi trùng câu báo dừng) nên task kết thúc "bình thường" và
                # `task.cancelled()` ở `_xong_luot` không bao giờ True.
                self._cho.pop(chat, None)
                steer_inbox.INBOX.drop(self._steer_sid(chat))   # 0.213.0: and what was sent for the turn mid-way
                res = await self.command_fn("stop", "", chat, meta) if self.command_fn else None
                # Chế độ người thật không có câu mặc định: "⏹ Đã dừng." là tiếng của máy. Bot
                # chuyên trách vẫn nói được, nhưng bằng câu do command_fn của nó soạn.
                mac_dinh = "" if self.giau_trang_thai else "⏹ Đã dừng."
                await self._send(client, chat, (res or {}).get("reply", mac_dinh))
                return
            if self.command_fn:
                res = await self.command_fn(cmd, arg, chat, meta)
                if res and "reply" in res:
                    await self._send(client, chat, res["reply"], res.get("reply_markup"))
                    return
                if res and "ask" in res:
                    text = res["ask"]   # chuyển thành câu hỏi cho Javis
                # res None → coi như tin thường (gửi nguyên text)
        # Chốt chặn trước khi tốn một lượt. Đặt SAU khối lệnh có chủ ý: /id là đường chính
        # thức để lấy id nhóm, chặn nó thì chủ không còn cách nào khai nhóm cho bot.
        if self.precheck_fn and not text.startswith("/"):
            try:
                chan = self.precheck_fn(text, meta or {})
            except Exception as e:
                print(f"[bot precheck] {type(e).__name__}: {e}", file=sys.stderr)
                chan = None
            # `is not None` chứ KHÔNG phải `if chan:` - đây là lỗi đã sống lặng lẽ suốt từ khi
            # có precheck. Cách chặn IM LẶNG của bot chuyên trách là trả về `{}` (chặn, không
            # nói gì), mà dict rỗng thì falsy, nên nhánh này bỏ qua và lượt vẫn chạy tiếp. Hệ
            # quả thấy được: thả bot vào nhóm rồi hai người nói chuyện với nhau, tin nào bot
            # cũng hiện "đang nhập…" (chủ repo báo 2026-08-07 kèm ảnh). Hệ quả KHÔNG thấy
            # được, và đắt hơn nhiều: mỗi tin trong nhóm đều tốn một lượt engine thật, chỉ để
            # lớp thứ hai trong answer_fn trả về im_lang rồi vứt đi.
            if chan is not None:
                loi_nhan = str((chan or {}).get("reply") or "")
                if loi_nhan:
                    await self._send(client, chat, loi_nhan)
                return
        # Tin thường → chạy nền. Tuần tự THEO CHAT: chỉ chặn nếu chính chat này đang bận.
        if self._busy(chat):
            if self.giau_trang_thai:
                # Người thật đang gõ dở mà nghe thêm một câu thì đọc nốt rồi trả lời một thể,
                # chứ không quay ra nói "đang xử lý câu trước". Gộp vào lượt kế tiếp.
                self._xep_hang(chat, text, meta)
            else:
                await self._steer(client, chat, text, meta)
            return
        self._chay_luot(client, chat, text, meta)

    def _xep_hang(self, chat, text, meta=None):
        """Gom tin đến trong lúc bận, trả lời một thể khi lượt hiện tại xong.

        Có trần vì đây là hộp thư mở cho người lạ: ai đó dán 200 dòng lúc bot đang bận thì
        hàng chờ không được phình theo. Quá trần thì giữ mấy câu ĐẦU - câu hỏi thật gần như
        luôn nằm ở đó, phần đuôi thường là sốt ruột nhắn thêm.
        """
        o = self._cho.setdefault(chat, {"texts": [], "meta": meta})
        o["meta"] = meta or o.get("meta")
        if len(o["texts"]) >= MAX_CHO_TIN:
            return
        if sum(len(x) for x in o["texts"]) + len(text or "") > MAX_CHO_KY_TU:
            return
        o["texts"].append(str(text or ""))

    # ---- Send more while Javis is working (0.213.0, the chat-channel side of 0.206.0) ----
    def _steer_sid(self, chat):
        """The steer_inbox key of one chat on THIS bot: two bots (or two channels) can share a chat id."""
        return f"kenh:{id(self)}:{chat}"

    async def _steer(self, client, chat, text, meta=None):
        """The owner wrote again while their turn runs. Before 0.213.0 the bot answered "busy, send /stop" and the
        message was lost. Now the running turn reads it at its next step (Claude Code after a tool call, the API
        engines before the next model round); a one-shot engine, or a turn already writing its answer, leaves it for
        the turn that runs right after this one (`_turn` puts the unread rest back in the queue)."""
        sid = self._steer_sid(chat)
        if steer_inbox.INBOX.put(sid, text) is not None:
            self._steer_meta[chat] = meta
            live = steer_inbox.INBOX.live(sid)
        else:
            self._xep_hang(chat, text, meta)   # the turn has not opened its inbox yet, or too many are waiting
            live = False
        await self._send(client, chat, localefmt.chu(
            "↪ Đã nhận, Javis đọc tin này ngay ở bước kế tiếp của việc đang làm.",
            "↪ Got it, Javis reads this at the next step of the current work.") if live else localefmt.chu(
            "📥 Đã nhận, Javis làm tin này ngay sau câu đang trả lời.",
            "📥 Got it, Javis handles this right after the current answer."))

    async def _turn(self, client, chat, text, meta=None):
        if self.giau_trang_thai:
            # Customer-facing bots keep their own rule: messages sent meanwhile are merged into the next turn.
            return await self._handle_turn(client, chat, text, meta)
        sid = self._steer_sid(chat)
        token = steer_inbox.INBOX.open(sid)
        try:
            return await self._handle_turn(client, chat, text, meta)
        finally:
            left = steer_inbox.INBOX.close(sid, token=token)
            meta_moi = self._steer_meta.pop(chat, None)
            if left:
                o = self._cho.setdefault(chat, {"texts": [], "meta": meta_moi or meta})
                o["texts"][:0] = [i["text"] for i in left]

    def _chay_luot(self, client, chat, text, meta=None):
        task = asyncio.create_task(self._turn(client, chat, text, meta))
        self._current[chat] = task
        task.add_done_callback(lambda t, c=chat: self._xong_luot(client, c, t))

    def _xong_luot(self, client, chat, task):
        """Dọn task đã xong (tránh phình theo thời gian) rồi chạy nốt phần đang xếp hàng."""
        if self._current.get(chat) is task:
            self._current.pop(chat, None)
        cho = self._cho.pop(chat, None)
        # Bị /stop cắt ngang thì bỏ luôn hàng chờ: người ta bảo dừng chứ không bảo trả lời tiếp.
        if not cho or not cho.get("texts") or task.cancelled() or self._stop:
            return
        self._chay_luot(client, chat, "\n".join(cho["texts"]), cho.get("meta"))
