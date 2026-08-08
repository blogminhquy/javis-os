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

# ---- Dòng vết công cụ ----------------------------------------------------------------
MAX_VET_TOOL = 6        # số tên công cụ hiện trên dòng vết, dư thì gộp thành "+n"
# Tên công cụ nằm trong các chuỗi tiến trình do main.py bắn ra: "⚙ Đang gọi: X",
# "⚙ Đang gọi công cụ: X", "⚙ Đang dùng công cụ: X". Bắt chung một khuôn để thêm engine mới
# không phải sửa ở đây.
RE_TEN_TOOL = re.compile(r"^⚙[^:]*:\s*(.+)$")


def ten_tool(txt) -> str:
    """Bóc tên công cụ từ một chuỗi tiến trình. "" nếu chuỗi đó không nói về công cụ nào."""
    m = RE_TEN_TOOL.match(str(txt or "").strip())
    return m.group(1).strip().strip("`").strip() if m else ""


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


class HangLuot:
    """Mixin: điều phối lượt trả lời theo từng chat.

    Lớp dùng nó phải có sẵn: `_send(client, chat, text)`, `_handle_turn(client, chat, text,
    meta)`, và các thuộc tính `command_fn`, `precheck_fn`, `giau_trang_thai`, `_current`,
    `_cho`, `_stop`.
    """

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
                await self._send(client, chat,
                                 "⏳ Đang xử lý câu trước. Gửi /stop để dừng rồi hỏi lại.")
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

    def _chay_luot(self, client, chat, text, meta=None):
        task = asyncio.create_task(self._handle_turn(client, chat, text, meta))
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
