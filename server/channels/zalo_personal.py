"""Kênh Zalo CÁ NHÂN: tài khoản đã quét QR ở trang Kết nối (MCP `zalo-agent-cli`). Đọc tin bằng
vòng cursor ở `zalo_personal_channel`, gửi tin bằng tool `zalo_send_message` của chính MCP đó.

Gửi từ kênh này là gửi DƯỚI DANH TÍNH CHỦ (không phải bot), nên Hộp thư nói rõ điều đó ở ô
soạn tin; ngoài ra nó là một kênh như mọi kênh khác, không có mục riêng nào trên giao diện.

Từ 0.64.80 kênh này gắn được Bot chuyên trách (lớp `Transport` cuối file). Bot tự trả lời và tự
quyết có nên trả lời không; các rào nằm ở `Transport.xu_ly`. Từ 0.64.82 bot còn đứng được trong
NHÓM đã cho phép: trả lời khi được tag/reply, hoặc (chế độ Tự đánh giá) khi tin là một câu hỏi
mà tài liệu của bot trả lời được, xem `chatbot_tu_dong`.
"""
from __future__ import annotations

import asyncio
import sys
import time

from channels import KenhSpec

SPEC = KenhSpec(
    id="zalo_personal", nhan="Zalo cá nhân", kind="account", logo="zalo", mau="#0068FF",
    tom_tat="Tài khoản Zalo của chính bạn. Bot trực thì tự trả lời chat riêng và nhóm đã cho phép, dưới tên bạn.",
    nang_luc={"nhom": True, "gui_chu": True, "gui_file": False},
)


def tai_khoan():
    import zalo_personal_channel
    return zalo_personal_channel.tai_khoan()


def bat(account_id: str, on: bool) -> dict:
    import zalo_personal_channel
    return zalo_personal_channel.bat(account_id, on)


def trang_thai() -> dict:
    import zalo_personal_channel
    return zalo_personal_channel.trang_thai()


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    """Gửi qua MCP: `threadId`, `text` và kiểu cuộc chat (0 = chat riêng, 1 = nhóm).

    Khoá kiểu cuộc chat mà MCP zalo-agent-cli 1.6.2 THẬT SỰ đọc là `threadType` (mcp-tools.js), không
    phải `type` như tài liệu mcp-guide ghi. MCP bỏ qua khoá lạ mà không báo lỗi, nên gửi `type` một
    mình thì tin nhóm đi như chat riêng và Zalo không giao được (chủ thấy bot trả lời trong Hộp thư
    mà nhóm im, 29/09/2026). Gửi cả hai: `threadType` cho bản 1.6.2 đang ghim, `type` cho bản khác
    đọc theo tài liệu; khoá thừa bị MCP bỏ qua.
    """
    import zalo_personal_channel
    conn = zalo_personal_channel.ket_noi_theo_id(str(tk.get("id") or tk.get("external_id") or ""))
    if not conn:
        return False, "tài khoản Zalo này không còn ở trang Kết nối (hoặc đang tắt)"
    loai = 1 if str(chat_type or "") == "group" else 0
    try:
        d = await zalo_personal_channel._goi(conn, "zalo_send_message", {
            "threadId": str(chat_id), "text": str(text or ""),
            "threadType": loai, "type": loai,
        })
    except Exception as e:
        return False, str(e)[:300]
    if isinstance(d, dict) and d.get("success") is False:
        return False, str(d.get("error") or d.get("message") or "Zalo từ chối")[:300]
    return True, ""


class Transport:
    """Lớp vận chuyển cho bot trên Zalo cá nhân, đúng khế ước của `chatbot_runtime.start_bot`.

    KHÔNG tự đọc tin: vòng đọc của `zalo_personal_channel` là nguồn duy nhất (một cursor, hai
    người đọc là mất tin của nhau). Lớp này đăng ký ở đó, được đưa từng tin khách mới, và gửi
    câu trả lời bằng `gui`. `token` ở đây là id kết nối Zalo (xem `channel_accounts.get_token`).
    """

    def __init__(self, token, whitelist, answer_fn, command_fn=None, download_dir=None,
                 commands=None, precheck_fn=None, event_fn=None, giau_trang_thai=True,
                 cfg_fn=None, policy=None, **_):
        self.conn_id = str(token or "")
        self.answer_fn = answer_fn
        self.precheck_fn = precheck_fn
        self.event_fn = event_fn        # tin dịch vụ của nhóm: ở đây chỉ dùng "thay_nhom"
        self.cfg_fn = cfg_fn            # đọc cấu hình bot SỐNG (chế độ trả lời trong nhóm)
        self.policy = policy            # móc bộ phán xử hội thoại nhóm (0.65.0), xem chatbot_runtime.PolicyHooks
        self.account_id = self.conn_id
        self.status = "off"
        self.last_error = ""
        self._task = None
        self._khoa = {}         # thread -> Lock: một cuộc chat một lượt, khỏi trả lời chồng nhau

    # ---- vòng đời ------------------------------------------------------------------
    def start(self):
        import zalo_personal_channel as zc
        zc.dang_ky_bot(self.conn_id, self)
        self.status = "starting"
        self._task = asyncio.get_running_loop().create_task(self._giam_sat())

    def stop(self):
        import zalo_personal_channel as zc
        zc.huy_dang_ky_bot(self.conn_id, self)
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self.status = "off"

    async def _giam_sat(self):
        """Đo sức khoẻ để thẻ bot nói thật: chấm xanh chỉ khi vòng đọc đang đọc được."""
        import zalo_personal_channel as zc
        while True:
            try:
                tt = zc._TT.get(self.conn_id) or {}
                if not zc.ket_noi_theo_id(self.conn_id):
                    self.status = "error"
                    self.last_error = ("Kết nối Zalo này không còn (hoặc đang tắt) ở trang Kết nối, "
                                       "bot không nhận được tin.")
                elif tt.get("loi"):
                    self.status = "error"
                    self.last_error = str(tt["loi"])
                elif tt.get("lan_cuoi"):
                    self.status = "polling"
                    self.last_error = ""
                else:
                    self.status = "starting"
            except Exception:
                pass
            await asyncio.sleep(10)

    # ---- một tin khách ---------------------------------------------------------------
    def _che_do_nhom(self) -> str:
        try:
            return str((self.cfg_fn() if self.cfg_fn else {}).get("reply_when") or "")
        except Exception:
            return ""

    async def _bao_nhom(self, thread: str, ev: dict):
        """Báo cho bộ giám sát THẤY một nhóm (có tin bất kỳ về từ đó) để nhóm chưa cho phép hiện
        lên hàng chờ của thẻ bot, kèm nút Cho phép. Không thì chủ phải tự đi tìm id nhóm Zalo."""
        if not self.event_fn:
            return
        try:
            r = self.event_fn("thay_nhom", {"chat_id": thread,
                                            "chat_title": str(ev.get("chat_title") or "")})
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:
            print(f"[zalo-personal bot {self.conn_id}] báo nhóm lỗi: {e}", file=sys.stderr)

    async def xu_ly(self, ev: dict):
        """Quyết định có trả lời một tin khách không, và trả lời nếu có.

        Các rào, theo thứ tự rẻ tới đắt (cái nào chặn thì KHÔNG tốn một lượt model):
          - chỉ tin dạng CHỮ, ở chat riêng hoặc nhóm (ảnh/tiếng/file bỏ qua: chủ chưa giao việc đó);
          - tin cũ quá `TUOI_TOI_DA` bỏ qua (bộ đệm MCP lúc mới bật);
          - chủ vừa TỰ TAY nhắn cuộc chat này thì nhường;
          - nhóm: phải được chủ cho phép (chưa thì im TUYỆT ĐỐI và hiện lên hàng chờ duyệt);
          - chế độ Tự đánh giá, tin không ai gọi tên: giống câu hỏi không, rồi chờ `NHUONG_GIAY`
            để nhường nếu có người nhắn tay trong lúc đó;
          - rồi tới các luật chung của bot (Tiếp quản, hạn mức, tra tài liệu) trong `answer_fn`;
          - cuối cùng chính bot tự quyết: Agent viết `[IM_LANG]` nghĩa là không gửi gì.

        Trong NHÓM bot KHÔNG bao giờ nói một câu cố định nào (như "em chưa được bật cho nhóm
        này" của Telegram): nick này là người thật, câu đó khai với cả nhóm rằng đây là máy.
        """
        import chatbot_tu_dong
        import zalo_personal_channel as zc
        loai = ev.get("chat_type")
        if loai not in ("private", "group") or ev.get("message_type") != "text":
            return
        nhom = loai == "group"
        text = str(ev.get("text") or "").strip()
        thread = str(ev.get("external_chat_id") or "")
        if not text or not thread:
            return
        # Không biết cuộc chat là nhóm hay chat riêng (đã hỏi lại bảng mà vẫn không thấy): KHÔNG trả
        # lời. Đoán là chat riêng nghĩa là trả lời từng tin của một nhóm, dưới tên người thật.
        if (ev.get("metadata") or {}).get("chua_ro_loai"):
            return
        # Tin do CHÍNH nick này gửi (id đã học từ tin của nó) không bao giờ là khách, kể cả khi MCP
        # không gắn cờ "của mình": không thì bot tự trả lời chính nó.
        minh = (zc._ID_MINH.get(self.conn_id) or {}).get("uid")
        if minh and str(ev.get("sender_id") or "") == minh:
            return
        if nhom:
            await self._bao_nhom(thread, ev)
        if time.time() - float(ev.get("created_at") or 0) > zc.TUOI_TOI_DA:
            return
        if zc.chu_vua_nhan_tay(self.conn_id, thread):
            return
        meta = {
            "chat_id": thread, "chat_type": "group" if nhom else "private",
            "chat_title": str(ev.get("chat_title") or "") if nhom else "",
            # Trong nhóm id NGƯỜI gửi khác id nhóm: hạn mức và Hộp thư khoá theo người.
            "user_id": str(ev.get("sender_id") or ("" if nhom else thread)),
            "user_name": str(ev.get("sender_name") or ""), "username": "",
            "message_id": str(ev.get("external_message_id") or ""),
            "account_id": self.conn_id,
        }
        duoc_goi = False
        pol = None
        if nhom:
            conn = zc.ket_noi_theo_id(self.conn_id) or {}
            tag, rep = zc.nhan_dien_goi(self.conn_id, ev, (conn.get("label") or "",))
            meta["mentioned"], meta["reply_to_bot"] = tag, rep
            duoc_goi = tag or rep
            if self.policy is not None:
                # Tên gọi tự suy của nick (nhãn kết nối, tên hiển thị học được) để nhận ra gọi tên trơn
                # ("nhi mai ơi"); tin nào gọi chắc chắn thì `prepare` đặt `meta["mentioned"]`.
                meta["aliases_auto"] = [conn.get("label") or "", (zc._ID_MINH.get(self.conn_id) or {}).get("ten") or ""]
                meta["ts"] = float(ev.get("created_at") or time.time())
                try:
                    pol = self.policy.prepare(text, meta)
                except Exception as e:      # noqa: BLE001 - bộ phán xử hỏng thì giữ luật cũ, không được nuốt tin
                    pol = None
                    print(f"[zalo-personal bot {self.conn_id}] bộ phán xử lỗi: {type(e).__name__}: {e}", file=sys.stderr)
                duoc_goi = duoc_goi or bool(meta.get("mentioned"))
        try:
            if self.precheck_fn:
                r = self.precheck_fn(text, meta)
                if asyncio.iscoroutine(r):
                    r = await r
                if r is not None:           # {} = im, {"reply": ...} = một câu cố định
                    cau = str((r or {}).get("reply") or "").strip()
                    if cau and not nhom:
                        await self._gui(thread, cau, "private")
                    return
            if nhom and not duoc_goi and self._che_do_nhom() == "auto":
                if pol and pol.get("mode") == "on":
                    # Bộ phán xử thay cửa từ khoá: tin hiển nhiên không đáng đã được ghi vết và bỏ ở `prepare`.
                    if pol.get("action") == "drop":
                        return
                elif not chatbot_tu_dong.nhin_nhu_cau_hoi(text)[0]:
                    return
                # Chờ TRƯỚC khi cầm khoá cuộc chat: khoá là của các lượt được tag, đừng bắt chúng
                # xếp hàng sau một lượt đang ngủ.
                await asyncio.sleep(zc.NHUONG_GIAY)
                if zc.chu_vua_nhan_tay(self.conn_id, thread):
                    return
                if zc._BOTS.get(self.conn_id) is not self:
                    return      # bot bị tắt lúc đang chờ: nút Tắt phải có tác dụng ngay
            khoa = self._khoa.setdefault(thread, asyncio.Lock())
            async with khoa:
                out = await self.answer_fn(text, meta, None)
                if isinstance(out, dict):
                    if out.get("im_lang"):
                        return
                    cau = str(out.get("text") or "").strip()
                else:
                    cau = str(out or "").strip()
                if cau and zc._BOTS.get(self.conn_id) is self:
                    await self._gui(thread, cau, loai)
                    if nhom and self.policy is not None:
                        self.policy.replied(meta, cau)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"[:300]
            print(f"[zalo-personal bot {self.conn_id}] lượt hỏng: {self.last_error}",
                  file=sys.stderr)

    async def _gui(self, thread: str, cau: str, chat_type: str = "private"):
        import zalo_personal_channel as zc
        # Nhớ TRƯỚC khi gửi: tiếng vọng có thể về vòng đọc ngay trong nhịp kế tiếp.
        zc.ghi_da_gui(self.conn_id, thread, cau)
        ok, loi = await gui({"id": self.conn_id}, thread, cau, chat_type)
        if not ok:
            self.last_error = f"Gửi Zalo lỗi: {loi}"[:300]
            print(f"[zalo-personal bot {self.conn_id}] {self.last_error}", file=sys.stderr)
            self._ghi_loi_gui(thread, cau, loi, chat_type)

    def _ghi_loi_gui(self, thread: str, cau: str, loi: str, chat_type: str):
        """Để lại dấu ở nhật ký bot khi gửi lỗi.

        Câu trả lời đã vào Hộp thư TRƯỚC khi gửi (xem `chatbot_runtime._answer`), còn `last_error`
        bị vòng giám sát xoá sau vài giây. Không có dòng này thì "bot đã trả lời" trong Hộp thư và
        "khách không nhận được gì" nhìn giống hệt nhau, và không chỗ nào cho biết vì sao.
        """
        try:
            import chatbot_log
            cfg = self.cfg_fn() if self.cfg_fn else {}
            bid = str((cfg or {}).get("id") or "")
            if not bid:
                return
            chatbot_log.ghi(bid, {
                "chat_id": thread, "chat_type": chat_type, "user_name": "",
                "hoi": "(bot gửi tin vào " + ("nhóm" if chat_type == "group" else "chat riêng") + ")",
                "dap": cau,
                "loi": f"Gửi Zalo lỗi: {loi}. Câu định gửi: {cau[:200]}",
                "muc_quyen": (cfg or {}).get("muc_quyen") or "suggest",
            })
        except Exception as e:
            print(f"[zalo-personal bot {self.conn_id}] ghi nhật ký lỗi gửi: {e}", file=sys.stderr)
