"""Cổng Zalo Bot - API CHÍNH THỨC của Zalo (bot.zaloplatforms.com).

Đây là kênh thứ tư của Javis, sau dashboard, Telegram và CLI. Nó KHÔNG thay
`zalo-agent-cli` (xem docs/12-zalo.md): hai thứ khác bản chất và cùng tồn tại.

  - `zalo-agent-cli` đăng nhập CHÍNH tài khoản Zalo của bạn qua API không chính thức. Đọc
    được hội thoại thật, nhắn cho bất kỳ ai, và tài khoản CÓ THỂ bị khoá.
  - Zalo Bot là một DANH TÍNH RIÊNG, chính thức, không bị khoá, nhưng chỉ thấy được thứ
    người ta nhắn thẳng cho nó.

Cái đầu để Javis thao tác thay bạn. Cái sau để người khác nói chuyện với Javis. Gộp hai cái
làm một là mất một nửa năng lực.

Về hình dạng, Zalo Bot API gần như một bản sao của Telegram Bot API (cùng vỏ
`{ok, result, description, error_code}`, cùng kiểu `bot<TOKEN>/method`, cùng cặp getUpdates
với webhook), nên lớp này giữ ĐÚNG khế ước của `TelegramBot` và dùng chung `bot_gateway`.

BỐN CHỖ KHÁC TELEGRAM, và cả bốn đều đổi hành vi chứ không chỉ đổi tên hàm:

  1. **Không sửa được tin, không xoá được tin.** Không có `editMessageText` lẫn
     `deleteMessage`. Nên KHÔNG có tin trạng thái nào cả: gửi ra là nằm đó vĩnh viễn.
     Thứ duy nhất báo "đang làm" là `sendChatAction typing`, và nó không mang được chữ.
     Dòng vết công cụ vì vậy đi KÈM câu trả lời (một tin), không phải một tin riêng.
  2. **Không có nút bấm inline, không có callback.** Nên không nhận `callback_fn`.
  3. **Trần 2000 ký tự** một tin, không phải 4096.
  4. **`getUpdates` không có `offset` cũng không có `update_id`** (tham số duy nhất là
     `timeout`). Không có cách xác nhận đã nhận, nên phải TỰ chống trùng theo `message_id`.

Xem docs/dev/2026-08-zalo-bot-spec.md.
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from collections import deque
from pathlib import Path

import httpx

from bot_gateway import HangLuot, dong_vet, parse_chat_ids, ten_tool

ZALO_API = "https://bot-api.zaloplatforms.com/bot{token}/{method}"

# Trần thật của `sendMessage` là 2000. Chừa lại một ít cho phần đuôi dòng vết và cho ký tự
# nhiều byte: cắt sát trần rồi bị từ chối cả tin thì người hỏi không nhận được gì.
MAX_TIN = 1900
TYPING_MOI_GIAY = 4.0     # chưa đo được Zalo tắt chấm sau bao lâu; lấy nhịp an toàn như Telegram
MAX_DEDUPE = 2000         # số message_id nhớ để chống trùng
MAX_TAI_MB = 20           # trần tải file người dùng gửi lên, tự đặt (Zalo chưa công bố)

# Sự kiện Zalo bắn ra. `unsupported` là loại Zalo cố ý không chuyển nội dung.
SK_TEXT = "message.text.received"
SK_ANH = "message.image.received"
SK_STICKER = "message.sticker.received"
SK_VOICE = "message.voice.received"


def _chat_type(raw) -> str:
    """Zalo dùng PRIVATE/GROUP, Javis dùng private/group ở mọi nơi khác (xem
    `chatbot_runtime._ly_do_im`). Quy về MỘT bảng chữ ngay tại cửa vào, chứ đừng bắt mỗi
    chỗ đọc meta phải nhớ kênh nào viết hoa."""
    s = str(raw or "").strip().lower()
    if s.startswith("group"):
        return "group"
    return "private"


class ZaloBot(HangLuot):
    """Giữ ĐÚNG khế ước của `TelegramBot` để `chatbot_runtime` không phải biết mình đang cầm
    kênh nào. Thiếu `callback_fn` vì Zalo không có nút bấm."""

    def __init__(self, token, chat_id, answer_fn, command_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai=False):
        self.token = token
        self.giau_trang_thai = bool(giau_trang_thai)
        self.chat_ids = parse_chat_ids(chat_id)
        # Zalo không có `setMyCommands`. Nhận tham số để chỗ gọi dùng chung một khuôn, nhưng
        # nói rõ ở đây là nó KHÔNG đẩy được menu lên app - người dùng phải tự gõ lệnh.
        self.commands = list(commands or [])
        self.answer_fn = answer_fn
        self.command_fn = command_fn
        self.callback_fn = None       # Zalo không có nút bấm inline
        self.precheck_fn = precheck_fn
        self.event_fn = event_fn
        self.download_dir = download_dir
        self._task = None
        self._current = {}
        self._cho = {}
        self._stop = False
        self.status = "off"           # off | starting | polling | error | stopped
        self.last_error = ""
        # Danh tính của chính bot này (getMe).
        self.bot_id = ""
        self.bot_username = ""        # `account_name` của Zalo, giữ tên trường cho khớp Telegram
        self.account_type = ""
        # Gói BASIC không cho bot vào nhóm. Phải phơi ra: trang Chatbot có cả một khối cấu hình
        # nhóm, và bật nó cho một con bot không bao giờ vào được nhóm là hứa suông.
        self.vao_duoc_nhom = False
        self.doc_moi_tin_nhom = False     # Zalo không có khái niệm này; giữ để khớp khế ước
        self.loi_danh_tinh = ""
        self._lan_hoi_danh_tinh = 0.0
        # Chống trùng: `getUpdates` của Zalo không có offset lẫn update_id, nên không có cách
        # nào nói với máy chủ "tin này nhận rồi". Tự nhớ id đã xử lý.
        self._da_xu_ly = set()
        self._thu_tu = deque()
        self._da_bao_khuon_la = False

    # ---- HTTP -------------------------------------------------------------------------
    def _url(self, method):
        return ZALO_API.format(token=self.token, method=method)

    async def _api(self, client, method, **payload):
        """Gọi một method, luôn trả dict. Lỗi mạng cũng thành dict để chỗ gọi chỉ xử một kiểu."""
        try:
            r = await client.post(self._url(method), json=payload or {})
            try:
                return r.json() or {}
            except Exception:
                return {"ok": False, "description": f"HTTP {r.status_code}", "error_code": r.status_code}
        except Exception as e:
            return {"ok": False, "description": f"{type(e).__name__}: {e}"}

    async def _send(self, client, chat, text, reply_markup=None):
        """Gửi câu trả lời, chia nhỏ theo trần 2000 ký tự.

        `reply_markup` nhận vào rồi BỎ QUA: Zalo không có nút bấm. Giữ tham số để chỗ gọi
        dùng chung `bot_gateway._dispatch` với Telegram mà không phải rẽ nhánh theo kênh.
        """
        if not str(text or "").strip() and self.giau_trang_thai:
            return
        text = text or "(không có nội dung)"
        chunks = [text[i:i + MAX_TIN] for i in range(0, len(text), MAX_TIN)] or [text]
        for chunk in chunks:
            # Markdown trước, hỏng thì gửi lại chữ trơn. Cùng vòng hai bước với Telegram, và
            # cần thật: markdown của Zalo có thẻ màu dạng {red}...{/red}, nên một dấu ngoặc
            # nhọn lạc trong câu trả lời là đủ làm cả tin bị từ chối.
            for co_md in (True, False):
                payload = {"chat_id": chat, "text": chunk}
                if co_md:
                    payload["parse_mode"] = "markdown"
                d = await self._api(client, "sendMessage", **payload)
                if d.get("ok"):
                    break
                if not co_md:
                    print(f"[zalo send] chữ trơn vẫn lỗi: {str(d.get('description'))[:200]}",
                          file=sys.stderr)

    async def _typing(self, client, chat):
        await self._api(client, "sendChatAction", chat_id=chat, action="typing")

    async def _giu_typing(self, client, chat):
        """Giữ chấm "đang nhập" suốt lượt. Trên Zalo đây là THỨ DUY NHẤT báo được là Javis
        đang làm việc: không sửa được tin nên không có tin trạng thái nào để cập nhật."""
        while True:
            await self._typing(client, chat)
            await asyncio.sleep(TYPING_MOI_GIAY)

    # ---- Danh tính --------------------------------------------------------------------
    async def _hoi_danh_tinh(self, client, lan=3):
        self._lan_hoi_danh_tinh = time.monotonic()
        loi = ""
        for i in range(max(1, lan)):
            d = await self._api(client, "getMe")
            me = d.get("result") or {}
            if me.get("id"):
                self.bot_id = str(me.get("id") or "")
                self.bot_username = str(me.get("account_name") or "")
                self.account_type = str(me.get("account_type") or "")
                self.vao_duoc_nhom = bool(me.get("can_join_groups"))
                self.loi_danh_tinh = ""
                return True
            loi = str(d.get("description") or "getMe lỗi")
            if i < lan - 1:
                await asyncio.sleep(2 ** i)
        self.loi_danh_tinh = (
            f"Không hỏi được danh tính bot từ Zalo ({loi}). Bot vẫn trả lời tin nhắn RIÊNG, "
            "nhưng trong nhóm nó không nhận ra được ai đang gọi tên mình nên sẽ im. "
            "Tắt rồi bật lại bot để thử lại.")
        print(f"[zalo getMe] {loi}", file=sys.stderr)
        return False

    # ---- Bóc tin đến ------------------------------------------------------------------
    def _boc_su_kien(self, data):
        """Chuẩn hoá phản hồi `getUpdates` thành list [(event_name, message)].

        Tài liệu Zalo mới chỉ công bố khuôn của WEBHOOK (`result` là MỘT sự kiện), còn phần
        `getUpdates` thì bỏ trống phần phản hồi. Nên nhận cả ba khuôn có thể có thay vì đoán
        một cái rồi im lặng bỏ hết tin khi đoán sai - loại hỏng tệ nhất ở đây, vì bot vẫn
        xanh, vẫn poll, chỉ là không bao giờ trả lời ai.

        Khuôn lạ thì kêu MỘT lần ra stderr kèm mẫu, để lần chạy thật đầu tiên tự nói cho biết
        cần sửa gì.
        """
        res = data.get("result")
        tho = []
        if isinstance(res, dict):
            if res.get("message") or res.get("event_name"):
                tho = [res]
            else:
                for khoa in ("updates", "messages", "events", "data"):
                    if isinstance(res.get(khoa), list):
                        tho = res[khoa]
                        break
        elif isinstance(res, list):
            tho = res

        ra = []
        for item in tho:
            if not isinstance(item, dict):
                continue
            msg = item.get("message")
            if not isinstance(msg, dict):
                # Có thể chính item là message (khuôn phẳng).
                msg = item if item.get("message_id") else None
            if not msg:
                continue
            ra.append((str(item.get("event_name") or SK_TEXT), msg))
        if not ra and tho and not self._da_bao_khuon_la:
            self._da_bao_khuon_la = True
            print(f"[zalo getUpdates] khuôn phản hồi lạ, không bóc được tin nào: "
                  f"{str(data)[:400]}", file=sys.stderr)
        return ra

    def _da_thay(self, mid) -> bool:
        """True nếu message_id này đã xử lý rồi. Ghi nhớ luôn nếu chưa."""
        mid = str(mid or "")
        if not mid:
            return False        # không có id thì không chống trùng được, thà trả lời hai lần
        if mid in self._da_xu_ly:
            return True
        self._da_xu_ly.add(mid)
        self._thu_tu.append(mid)
        while len(self._thu_tu) > MAX_DEDUPE:
            self._da_xu_ly.discard(self._thu_tu.popleft())
        return False

    def _build_meta(self, msg):
        chat_obj = msg.get("chat") or {}
        frm = msg.get("from") or {}
        return {
            "platform": "zalo",
            "chat_id": str(chat_obj.get("id", "") or frm.get("id", "")),
            "chat_type": _chat_type(chat_obj.get("chat_type") or chat_obj.get("type")),
            "chat_title": chat_obj.get("name") or chat_obj.get("title") or "",
            "user_name": frm.get("display_name") or "",
            "username": frm.get("display_name") or "",
            "message_id": msg.get("message_id"),
            "bot_username": self.bot_username,
            "mentioned": self._co_nhac_ten(msg),
            "reply_to_bot": False,   # Zalo không cho biết tin này trả lời vào tin nào
        }

    def _co_nhac_ten(self, msg):
        """Zalo KHÔNG gửi kèm `entities`, nên chỉ còn cách so chuỗi với tên bot.

        Telegram có "@username" - một từ, ranh giới rõ. Zalo chỉ có TÊN HIỂN THỊ, mà tên hiển
        thị có khoảng trắng, nên ranh giới thật sự không tồn tại: trong "Bot Shop VN cho hỏi",
        chuỗi "Bot Shop" vẫn nằm đó dù người ta đang gọi một con bot khác.

        Chọn hướng NHẬN HƠI RỘNG: chặn khi tên bị dính liền vào chữ khác ("BotShopVN" không
        gọi "BotShop"), còn tên nối bằng khoảng trắng thì vẫn tính là được gọi. Vì hai kiểu
        sai không ngang giá nhau - nhận nhầm thì bot trả lời một câu thừa và người ta bỏ qua,
        còn bỏ sót thì bot IM khi được gọi đúng tên, và đó là lỗi im lặng không ai dò ra được.

        Hạn chế đã biết: hai bot cùng tiền tố tên trong một nhóm sẽ cùng lên tiếng. Hiện chưa
        chạm tới ai vì gói bot cơ bản của Zalo không cho bot vào nhóm.
        """
        ten = str(self.bot_username or "").strip()
        if not ten:
            return False
        s = str(msg.get("text") or msg.get("caption") or "")
        return bool(re.search(re.escape(ten) + r"(?![A-Za-zÀ-ỹ0-9_])", s, re.I))

    # ---- File người dùng gửi lên ------------------------------------------------------
    async def _ingest_attachment(self, client, ev, msg):
        """Tải ảnh/voice người dùng gửi về inbox của brain, trả dòng mô tả cho engine."""
        caption = str(msg.get("caption") or "").strip()

        def _with_cap(s):
            return s + ("\n" + caption if caption else "")

        if ev == SK_STICKER:
            return _with_cap("[Người dùng gửi một sticker Zalo. Không có nội dung chữ để đọc.]")
        if ev == SK_VOICE:
            return _with_cap("[Người dùng gửi tin thoại qua Zalo - Javis chưa đọc được loại này. "
                             "Hãy lịch sự nhờ họ gõ chữ.]")
        if ev not in (SK_ANH,):
            return None

        # Tên trường ảnh chưa được tài liệu chốt, nên thử các tên đã thấy thay vì cược vào một cái.
        url = ""
        for khoa in ("photo_url", "photo", "image_url", "url", "file_url"):
            v = msg.get(khoa)
            if isinstance(v, str) and v.startswith("http"):
                url = v
                break
            if isinstance(v, dict) and isinstance(v.get("url"), str):
                url = v["url"]
                break
        if not url:
            return _with_cap("[Người dùng gửi một ảnh qua Zalo nhưng Javis không lấy được "
                             "đường dẫn ảnh.]")
        try:
            rr = await client.get(url, timeout=httpx.Timeout(180.0))
            rr.raise_for_status()
            noi_dung = rr.content
            if len(noi_dung) > MAX_TAI_MB * 1024 * 1024:
                return _with_cap(f"[Người dùng gửi một ảnh lớn hơn {MAX_TAI_MB}MB, Javis không "
                                 "tải về.]")
            chat = str((msg.get("chat") or {}).get("id", ""))
            ddir = self.download_dir(chat) if callable(self.download_dir) else self.download_dir
            d = Path(ddir) if ddir else Path("zalo-inbox")
            d.mkdir(parents=True, exist_ok=True)
            duoi = ".jpg"
            for k in (".png", ".webp", ".gif", ".jpeg", ".jpg"):
                if k in url.lower():
                    duoi = k
                    break
            safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_",
                          f"zalo_{msg.get('message_id') or int(time.time())}{duoi}")
            dest = d / safe
            i = 1
            while dest.exists():
                dest = d / f"{Path(safe).stem}_{i}{Path(safe).suffix}"
                i += 1
            dest.write_bytes(noi_dung)
            return _with_cap(f"[Người dùng gửi một ảnh qua Zalo, đã tải về: {dest}]")
        except Exception as e:
            return _with_cap(f"[Người dùng gửi một ảnh qua Zalo nhưng tải về hỏng: "
                             f"{type(e).__name__}: {e}]")

    async def send_file(self, path, caption="", chat=None):
        """Gửi một file ra Zalo. Trả (ok, error).

        Zalo Bot chỉ có `sendPhoto`, và tài liệu ghi tham số `photo` là "đường dẫn hình ảnh"
        mà không nói rõ có nhận upload trực tiếp hay bắt buộc URL công khai. Nên: THỬ đẩy
        multipart, hỏng thì nói thật lý do. Không có `sendDocument` nào cả, nên PDF, bảng
        tính và tài liệu KHÔNG gửi ra được - phải nói thẳng chứ không im lặng nuốt file.
        """
        chat = chat or (self.chat_ids[0] if self.chat_ids else "")
        if not chat:
            return False, "Chưa cấu hình chat_id"
        p = Path(str(path))
        try:
            if not p.is_file():
                return False, f"File không tồn tại: {path}"
            noi_dung = p.read_bytes()
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            return False, ("Zalo Bot chưa có API gửi tài liệu (chỉ có sendPhoto), nên không gửi "
                           f"được {p.name} qua Zalo")
        data = {"chat_id": chat}
        if caption:
            data["caption"] = str(caption)[:2000]
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as c:
            try:
                r = await c.post(self._url("sendPhoto"), data=data,
                                 files={"photo": (p.name, noi_dung)})
                d = {}
                try:
                    d = r.json() or {}
                except Exception:
                    pass
                if d.get("ok"):
                    return True, ""
                return False, (str(d.get("description") or f"sendPhoto HTTP {r.status_code}") +
                               " (Zalo có thể chỉ nhận ảnh qua URL công khai)")
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"

    # ---- Một lượt ---------------------------------------------------------------------
    async def _handle_turn(self, client, chat, text, meta=None):
        await self._typing(client, chat)
        files = []
        # Zalo không sửa và không xoá được tin, nên KHÔNG có tin trạng thái nào. Thứ duy nhất
        # nói được "đang làm" là chấm "đang nhập", và nó không mang được chữ. Dòng vết công cụ
        # vì vậy đi KÈM câu trả lời: một tin cho cả lượt, không có gì phải dọn.
        giu = asyncio.create_task(self._giu_typing(client, chat))
        t0 = time.monotonic()
        tools = []

        async def progress(txt):
            ten = ten_tool(txt)
            if ten and ten not in tools:
                tools.append(ten)

        try:
            try:
                reply = await self.answer_fn(text, meta, progress)
            except asyncio.CancelledError:
                return   # /stop tự báo, không gửi trùng
            except Exception as e:
                print(f"[zalo lượt hỏng] {type(e).__name__}: {e}", file=sys.stderr)
                from telegram_bot import CAU_LOI_NGUOI_THAT
                reply = (CAU_LOI_NGUOI_THAT if self.giau_trang_thai
                         else f"⚠ Lỗi: {type(e).__name__}: {e}")
            im_lang = False
            if isinstance(reply, dict):
                files = reply.get("files") or []
                im_lang = bool(reply.get("im_lang"))
                reply = reply.get("text") or ""
            if im_lang and not str(reply or "").strip() and not files:
                return
            # Dòng vết chỉ dành cho bot của CHỦ. Bot chuyên trách nói với khách thì tuyệt đối
            # không lộ ra công cụ nào đã chạy.
            if not self.giau_trang_thai:
                vet = dong_vet(tools, time.monotonic() - t0)
                reply = ((str(reply or "").rstrip() + "\n\n") if str(reply or "").strip() else "") + vet
            if str(reply or "").strip() or not files:
                await self._send(client, chat, reply)
            for f in files:
                fpath, fcap = (f.get("path"), f.get("caption", "")) if isinstance(f, dict) else (f, "")
                ok, err = await self.send_file(fpath, fcap, chat=chat)
                if not ok:
                    print(f"[zalo gửi file] {fpath}: {err}", file=sys.stderr)
                    if not self.giau_trang_thai:
                        await self._send(client, chat,
                                         f"⚠ Không gửi được file {Path(str(fpath)).name}: {err}")
        finally:
            giu.cancel()

    # ---- Vòng nhận tin ----------------------------------------------------------------
    async def _loop(self):
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            # Webhook bật thì long-poll không nhận được gì. Xoá trước (no-op nếu chưa đặt).
            await self._api(client, "deleteWebhook")
            await self._hoi_danh_tinh(client)
            # Tin tồn trước lúc bật: nuốt một vòng rồi mới chạy thật, để bật bot lên không bị
            # dội lại mấy câu hỏi từ hôm trước như thể vừa mới hỏi.
            try:
                for _, msg in self._boc_su_kien(await self._api(client, "getUpdates", timeout=1)):
                    self._da_thay(msg.get("message_id"))
            except Exception:
                pass
            print(f"[zalo] bot started (chat_id={','.join(self.chat_ids) or 'mọi người'})",
                  file=sys.stderr)
            self.status = "polling"
            while not self._stop:
                try:
                    d = await self._api(client, "getUpdates", timeout=25)
                    if not d.get("ok"):
                        ma = d.get("error_code")
                        self.status = "error"
                        self.last_error = str(d.get("description") or "getUpdates lỗi")
                        # 429 là hạn mức, không phải hỏng: nghỉ dài hơn hẳn rồi thử lại. Zalo
                        # chưa công bố con số hạn mức nào nên đây là chỗ duy nhất biết được.
                        await asyncio.sleep(60 if ma == 429 else 10)
                        continue
                    self.status = "polling"
                    self.last_error = ""
                    if not self.bot_id and time.monotonic() - self._lan_hoi_danh_tinh > 60:
                        await self._hoi_danh_tinh(client, lan=1)
                    for ev, msg in self._boc_su_kien(d):
                        if (msg.get("from") or {}).get("is_bot"):
                            continue      # tin của chính bot dội lại
                        if self._da_thay(msg.get("message_id")):
                            continue
                        meta = self._build_meta(msg)
                        chat = meta["chat_id"]
                        if not chat:
                            continue
                        if meta["chat_type"] != "private":
                            await self._bao_su_kien(meta)
                        if self.chat_ids and chat not in self.chat_ids:
                            await self._send(client, chat, "Bạn không có quyền dùng bot Javis này.")
                            continue
                        text = str(msg.get("text") or "").strip()
                        if not text:
                            from telegram_bot import _caption_command_text
                            ingested = await self._ingest_attachment(client, ev, msg) or ""
                            text = _caption_command_text(ingested, msg.get("caption"))
                        if not text:
                            continue
                        await self._dispatch(client, chat, text, meta)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"[zalo loop] {type(e).__name__}: {e}", file=sys.stderr)
                    await asyncio.sleep(5)
            print("[zalo] bot stopped", file=sys.stderr)

    async def _bao_su_kien(self, meta):
        """Nhóm: báo lên hàng chờ duyệt của trang Chatbot. Zalo không có tin dịch vụ kiểu
        "bot vừa được thêm vào nhóm", nên đường duy nhất biết một nhóm tồn tại là có tin từ
        đó về."""
        if not self.event_fn:
            return
        try:
            await self.event_fn("thay_nhom", {
                "chat_id": meta.get("chat_id", ""),
                "chat_title": meta.get("chat_title", ""),
                "chat_type": meta.get("chat_type", ""),
                "chat_id_moi": "",
            })
        except Exception as e:
            print(f"[zalo sự kiện nhóm] {type(e).__name__}: {e}", file=sys.stderr)

    def start(self):
        self._stop = False
        self.status = "starting"
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._loop())

    def stop(self):
        self._stop = True
        self.status = "stopped"
        for t in list(self._current.values()):
            if t and not t.done():
                t.cancel()
        self._current.clear()
        self._cho.clear()
        if self._task:
            self._task.cancel()
            self._task = None
