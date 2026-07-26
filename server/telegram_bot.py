"""
Telegram bot cho Javis - long-polling getUpdates, whitelist theo chat_id (MỘT hoặc NHIỀU ID).
- Trả lời chạy ở BACKGROUND task → vẫn nhận /stop giữa chừng.
- Lệnh /...: command_fn(cmd, arg, chat) -> {"reply": str} | {"ask": str} | None
  (chat = chat_id người gõ → /reset //stop /retry chỉ tác động PHIÊN của họ).
- answer_fn(text, meta) nhận thêm META KÊNH (chat/user/loại chat) để engine biết
  mình đang trả lời qua đâu (port ý tưởng gateway hermes-agent), và có thể trả
  dict {"text":..., "files":[...]} để bot gửi file đính kèm sau câu trả lời.
- Gửi tin: thử MarkdownV2 (đậm/nghiêng/code hiện đẹp) → hỏng thì gửi lại plain
  (mirror vòng (True, False) trong telegram adapter của hermes).
- Nhận file/ảnh từ user: tự tải về download_dir rồi đưa đường dẫn vào tin nhắn.
Decoupled: main.py cấp answer_fn (1 lượt chat) + command_fn (xử lý lệnh).
"""
import asyncio
import re
import sys
import time
from pathlib import Path

import httpx


def parse_chat_ids(raw):
    """Chuẩn hoá whitelist chat_id: nhận chuỗi 'id1, id2 id3' (phẩy/chấm phẩy/khoảng trắng)
    hoặc list → trả list str đã strip, bỏ trùng, giữ thứ tự. RỖNG = cho phép MỌI người
    (giữ hành vi cũ). ID nhóm Telegram là số ÂM nên không ép kiểu/không lọc dấu '-'."""
    if raw is None:
        return []
    items = raw if isinstance(raw, (list, tuple)) else re.split(r"[,;\s]+", str(raw))
    out = []
    for x in items:
        x = str(x).strip()
        if x and x not in out:
            out.append(x)
    return out


TG_API = "https://api.telegram.org/bot{token}/{method}"

# Lệnh hiện trong menu Telegram (gõ "/" hoặc nút Menu). Tên chỉ a-z0-9_ (skill có dấu "-" gõ tay).
BOT_COMMANDS = [
    {"command": "help", "description": "Trợ giúp"},
    {"command": "status", "description": "Engine, model, vault, trạng thái"},
    {"command": "skills", "description": "Liệt kê skill có sẵn"},
    {"command": "notes", "description": "Lưu tin nhắn (kèm ảnh) vào Sources của brain"},
    {"command": "agents", "description": "Liệt kê agent + việc đang chạy"},
    {"command": "workflows", "description": "Liệt kê workflow"},
    {"command": "model", "description": "Xem hoặc đổi model"},
    {"command": "brain", "description": "Xem hoặc đổi brain (vault) của phiên này"},
    {"command": "retry", "description": "Gửi lại câu hỏi gần nhất"},
    {"command": "stop", "description": "Dừng câu đang trả lời"},
    {"command": "reset", "description": "Bắt đầu hội thoại mới"},
    {"command": "cli", "description": "Engine Claude (có MCP/skill)"},
    {"command": "or", "description": "Engine OpenRouter (chat thuần)"},
]

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_DOC_MB = 50     # trần sendDocument của bot API
MAX_PHOTO_MB = 10   # trần sendPhoto
MAX_DOWNLOAD_MB = 20  # bot API chỉ cho TẢI VỀ file ≤ 20MB


def _caption_command_text(ingested, caption):
    """Text cuối cho tin CHỈ có đính kèm (ảnh/file). Nếu caption là LỆNH ('/...', vd '/notes ...')
    thì đưa LỆNH lên ĐẦU + dòng marker '[... đã tải về: path]' để _dispatch nhận đúng lệnh mà
    skill vẫn thấy đường dẫn file; caption thường hoặc rỗng thì giữ NGUYÊN ingested (hành vi cũ).
    Cần vì gửi ảnh + caption '/notes' trước đây bị chôn lệnh giữa text ingest nên không route
    được như lệnh - đúng ca dùng chính của /notes (chộp ảnh lưu vào Sources).
    _ingest_attachment ghép caption vào CUỐI marker, nên ở nhánh lệnh ta lấy lại dòng marker
    (dòng đầu, marker luôn 1 dòng) rồi đặt SAU lệnh."""
    cap = (caption or "").strip()
    ing = ingested or ""
    if cap.startswith("/") and ing:
        return cap + "\n" + ing.split("\n", 1)[0]
    return ing


# ---- Markdown thường → Telegram MarkdownV2 (port rút gọn từ hermes-agent
#      plugins/platforms/telegram/adapter.py:format_message) ----
_MDV2_ESC_RE = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")


def _esc_mdv2(s: str) -> str:
    return _MDV2_ESC_RE.sub(r"\\\1", s)


def md_to_mdv2(text: str) -> str:
    """Bảo toàn code/link bằng placeholder, dịch heading/**bold** → MDV2, escape phần còn lại."""
    ph = {}
    idx = [0]

    def _stash(v):
        k = "\x00%d\x00" % idx[0]
        idx[0] += 1
        ph[k] = v
        return k

    t = text or ""
    # 1) code block ```...``` (escape \ và ` trong thân theo spec MDV2)
    def _fence(m):
        head = m.group(1) or ""
        body = (m.group(2) or "").replace("\\", "\\\\").replace("`", "\\`")
        return _stash("```" + head + "\n" + body + "```")
    t = re.sub(r"```([^\n`]*)\n?([\s\S]*?)```", _fence, t)
    # 2) inline code
    t = re.sub(r"`([^`\n]+)`",
               lambda m: _stash("`" + m.group(1).replace("\\", "\\\\").replace("`", "\\`") + "`"), t)
    # 3) link [text](url) - trong URL chỉ cần escape ')' và '\'; cho phép 1 tầng
    #    ngoặc lồng trong URL (kiểu wikipedia .../Python_(language))
    t = re.sub(r"\[([^\]\n]+)\]\((https?://(?:[^()\s]|\([^()\s]*\))+)\)",
               lambda m: _stash("[" + _esc_mdv2(m.group(1)) + "](" +
                                m.group(2).replace("\\", "\\\\").replace(")", "\\)") + ")"), t)
    # 4) heading → đậm
    t = re.sub(r"^#{1,6}\s+(.+?)\s*$",
               lambda m: _stash("*" + _esc_mdv2(m.group(1)) + "*"), t, flags=re.M)
    # 5) **đậm**
    t = re.sub(r"\*\*([^*\n]+)\*\*", lambda m: _stash("*" + _esc_mdv2(m.group(1)) + "*"), t)
    # 6) escape toàn bộ phần còn lại rồi trả placeholder về chỗ cũ
    t = _esc_mdv2(t)
    for k, v in ph.items():
        t = t.replace(k, v)
    return t


class TelegramBot:
    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None):
        self.token = token
        # chat_id nhận chuỗi "id1,id2" hoặc list → whitelist NHIỀU người dùng chung 1 bot.
        self.chat_ids = parse_chat_ids(chat_id)
        self.answer_fn = answer_fn          # async (text, meta, progress) -> str | {"text":..., "files":[...]}; progress(txt) = báo trạng thái trung gian
        self.command_fn = command_fn        # async (cmd, arg, chat) -> dict|None
        self.callback_fn = callback_fn      # async (data, chat) -> dict|None (bấm nút inline; chat = ai bấm)
        self.download_dir = download_dir    # str | callable(chat) -> str: nơi lưu file user gửi lên
        self._task = None
        # ĐA PHIÊN: mỗi chat_id có lượt trả lời RIÊNG → các tài khoản chạy song song,
        # cùng 1 tài khoản vẫn tuần tự (1 lượt/lúc). Map chat_id(str) -> asyncio.Task.
        self._current = {}
        self._stop = False
        self.offset = 0
        self.status = "off"      # off | starting | polling | conflict | error | stopped
        self.last_error = ""

    def _url(self, method):
        return TG_API.format(token=self.token, method=method)

    async def _send(self, client, chat, text, reply_markup=None):
        text = text or "(không có nội dung)"
        # 3500 (không phải 4096) để chừa chỗ cho ký tự escape MarkdownV2
        chunks = [text[i:i + 3500] for i in range(0, len(text), 3500)] or [text]
        for idx, chunk in enumerate(chunks):
            base = {"chat_id": chat, "text": chunk}
            if reply_markup is not None and idx == len(chunks) - 1:
                base["reply_markup"] = reply_markup   # nút chỉ gắn vào tin cuối
            # MDV2 trước, hỏng escape (400 can't parse entities) → gửi lại plain
            for use_md in (True, False):
                payload = dict(base)
                if use_md:
                    payload["text"] = md_to_mdv2(chunk)
                    payload["parse_mode"] = "MarkdownV2"
                try:
                    r = await client.post(self._url("sendMessage"), json=payload)
                    try:
                        ok = bool(r.json().get("ok"))
                    except Exception:
                        ok = r.status_code == 200
                    if ok:
                        break
                    if not use_md:
                        print(f"[telegram send] plain vẫn lỗi: {r.text[:200]}", file=sys.stderr)
                except Exception as e:
                    print(f"[telegram send] {e}", file=sys.stderr)
                    break   # lỗi mạng: thử lại plain cũng sẽ lỗi

    async def send_file(self, path, caption="", chat=None):
        """Gửi 1 file tới chat (mặc định ID ĐẦU TIÊN trong whitelist - chủ bot).
        Ảnh nhỏ → sendPhoto (có preview), còn lại / ảnh bị từ chối → sendDocument.
        Trả (ok, error)."""
        chat = chat or (self.chat_ids[0] if self.chat_ids else "")
        if not chat:
            return False, "Chưa cấu hình chat_id"
        try:
            p = Path(str(path))
            if not p.is_file():
                return False, f"File không tồn tại: {path}"
            size = p.stat().st_size
            if size == 0:
                return False, "File rỗng"
            if size > MAX_DOC_MB * 1024 * 1024:
                return False, f"File {size // (1024 * 1024)}MB vượt trần {MAX_DOC_MB}MB của Telegram bot"
            content = p.read_bytes()
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        caption = (caption or "")[:1000]
        data = {"chat_id": chat}
        if caption:
            data["caption"] = caption
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            try:
                if p.suffix.lower() in IMG_EXTS and size <= MAX_PHOTO_MB * 1024 * 1024:
                    r = await client.post(self._url("sendPhoto"), data=data,
                                          files={"photo": (p.name, content)})
                    try:
                        if r.json().get("ok"):
                            return True, ""
                    except Exception:
                        pass
                    # ảnh bị từ chối (kích thước/định dạng lạ) → rơi xuống gửi dạng document
                r = await client.post(self._url("sendDocument"), data=data,
                                      files={"document": (p.name, content)})
                d = {}
                try:
                    d = r.json()
                except Exception:
                    pass
                if d.get("ok"):
                    return True, ""
                return False, str(d.get("description") or f"sendDocument HTTP {r.status_code}")
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"

    async def _typing(self, client, chat):
        try:
            await client.post(self._url("sendChatAction"), json={"chat_id": chat, "action": "typing"})
        except Exception:
            pass

    # ---- Tin TRẠNG THÁI tạm: cho user đỡ lo khi chờ (gửi → cập nhật theo tiến trình → xoá) ----
    async def _send_status(self, client, chat, text):
        """Gửi 1 tin trạng thái (plain, không markdown) → trả message_id để sửa/xoá sau."""
        try:
            r = await client.post(self._url("sendMessage"), json={"chat_id": chat, "text": text})
            d = r.json()
            if d.get("ok"):
                return d["result"]["message_id"]
        except Exception as e:
            print(f"[telegram status send] {e}", file=sys.stderr)
        return None

    async def _edit_status(self, client, chat, mid, text):
        if not mid:
            return
        try:
            await client.post(self._url("editMessageText"),
                              json={"chat_id": chat, "message_id": mid, "text": text})
        except Exception as e:
            print(f"[telegram status edit] {e}", file=sys.stderr)

    async def _del_msg(self, client, chat, mid):
        if not mid:
            return
        try:
            await client.post(self._url("deleteMessage"),
                              json={"chat_id": chat, "message_id": mid})
        except Exception:
            pass

    # ---- Meta kênh: engine cần biết tin đến từ đâu (DM/nhóm, ai gửi) ----
    @staticmethod
    def _build_meta(msg):
        chat_obj = msg.get("chat") or {}
        frm = msg.get("from") or {}
        name = " ".join(x for x in (frm.get("first_name", ""), frm.get("last_name", "")) if x).strip()
        return {
            "platform": "telegram",
            "chat_id": str(chat_obj.get("id", "")),
            "chat_type": chat_obj.get("type", ""),
            "chat_title": chat_obj.get("title", ""),
            "user_name": name,
            "username": frm.get("username", ""),
            "message_id": msg.get("message_id"),
        }

    # ---- User gửi file/ảnh lên bot → tải về, trả dòng mô tả (đường dẫn) cho engine ----
    async def _ingest_attachment(self, client, msg):
        doc = msg.get("document")
        photos = msg.get("photo") or []
        media_khac = msg.get("voice") or msg.get("audio") or msg.get("video") or msg.get("video_note")
        caption = (msg.get("caption") or "").strip()

        def _with_cap(s):
            return s + ("\n" + caption if caption else "")

        if doc:
            kind = "file"
            file_id = doc.get("file_id")
            name = doc.get("file_name") or f"file_{msg.get('message_id')}"
            fsize = doc.get("file_size") or 0
        elif photos:
            big = photos[-1]   # Telegram xếp size tăng dần → phần tử cuối nét nhất
            kind = "ảnh"
            file_id = big.get("file_id")
            name = f"photo_{msg.get('message_id')}.jpg"
            fsize = big.get("file_size") or 0
        elif media_khac:
            return _with_cap("[Người dùng gửi voice/audio/video qua Telegram - Javis chưa đọc được "
                             "loại này. Hãy lịch sự nhờ user gõ chữ hoặc gửi dạng file tài liệu.]")
        else:
            return None

        if fsize and fsize > MAX_DOWNLOAD_MB * 1024 * 1024:
            return _with_cap(f"[Người dùng gửi {kind} '{name}' ({fsize // (1024 * 1024)}MB) nhưng "
                             f"Telegram bot chỉ cho tải file dưới {MAX_DOWNLOAD_MB}MB - không tải về được. "
                             "Hãy báo user và gợi ý cách gửi khác.]")
        try:
            r = await client.get(self._url("getFile"), params={"file_id": file_id})
            fp = ((r.json() or {}).get("result") or {}).get("file_path")
            if not fp:
                return _with_cap(f"[Người dùng gửi {kind} '{name}' nhưng không lấy được từ Telegram.]")
            rr = await client.get(f"https://api.telegram.org/file/bot{self.token}/{fp}",
                                  timeout=httpx.Timeout(180.0))
            rr.raise_for_status()
            # download_dir nhận chat_id → file rơi vào inbox của ĐÚNG brain phiên người gửi
            chat = str((msg.get("chat") or {}).get("id", ""))
            ddir = self.download_dir(chat) if callable(self.download_dir) else self.download_dir
            d = Path(ddir) if ddir else Path("telegram-inbox")
            d.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name)).strip() or "file"
            dest = d / safe
            i = 1
            while dest.exists():
                dest = d / f"{Path(safe).stem}_{i}{Path(safe).suffix}"
                i += 1
            dest.write_bytes(rr.content)
            return _with_cap(f"[Người dùng gửi {kind} qua Telegram, gateway đã tải về: {dest}]")
        except Exception as e:
            return _with_cap(f"[Người dùng gửi {kind} qua Telegram nhưng tải về lỗi: "
                             f"{type(e).__name__}: {e}]")

    async def _handle_turn(self, client, chat, text, meta=None):
        await self._typing(client, chat)
        files = []
        # Tin trạng thái tạm để user Telegram thấy Javis đang chạy (đang gọi công cụ / nhận data /
        # soạn trả lời) thay vì im lặng chờ dài. Xong thì xoá tin này và gửi câu trả lời thật.
        status_mid = await self._send_status(client, chat, "🤔 Javis đang xử lý…")
        _last = [0.0]

        async def progress(txt):
            now = time.monotonic()
            if now - _last[0] < 2.5:      # throttle ~2.5s → không spam / dính rate-limit Telegram
                return
            _last[0] = now
            await self._typing(client, chat)
            await self._edit_status(client, chat, status_mid, "⏳ " + (txt or "Đang xử lý…"))

        try:
            reply = await self.answer_fn(text, meta, progress)
        except asyncio.CancelledError:
            await self._del_msg(client, chat, status_mid)
            return   # /stop sẽ tự báo, không gửi trùng
        except Exception as e:
            reply = f"⚠ Lỗi: {type(e).__name__}: {e}"
        if isinstance(reply, dict):
            files = reply.get("files") or []
            reply = reply.get("text") or ""
        await self._del_msg(client, chat, status_mid)   # bỏ tin trạng thái, thay bằng câu trả lời
        # Nếu câu trả lời chỉ là ![](local-path) và file đã được tách để gửi riêng, không gửi
        # thêm tin "(không có nội dung)" trước ảnh.
        if str(reply or "").strip() or not files:
            await self._send(client, chat, reply)
        # Gửi file SAU câu trả lời để thứ tự đọc tự nhiên (text trước, đính kèm sau)
        for f in files:
            fpath, fcap = (f.get("path"), f.get("caption", "")) if isinstance(f, dict) else (f, "")
            ok, err = await self.send_file(fpath, fcap, chat=chat)
            if not ok:
                await self._send(client, chat, f"⚠ Không gửi được file {Path(str(fpath)).name}: {err}")

    async def _loop(self):
        async with httpx.AsyncClient(timeout=httpx.Timeout(40.0)) as client:
            try:
                r = await client.get(self._url("getUpdates"), params={"offset": -1, "timeout": 0})
                res = r.json().get("result", [])
                if res:
                    self.offset = res[-1]["update_id"] + 1
            except Exception:
                pass
            try:
                # Webhook bật thì getUpdates trả 409 → xoá webhook trước khi long-poll (no-op nếu không có).
                await client.post(self._url("deleteWebhook"))
            except Exception as e:
                print(f"[telegram deleteWebhook] {e}", file=sys.stderr)
            try:
                await client.post(self._url("setMyCommands"), json={"commands": BOT_COMMANDS})
            except Exception as e:
                print(f"[telegram setMyCommands] {e}", file=sys.stderr)
            print(f"[telegram] bot started (chat_id={','.join(self.chat_ids) or 'mọi người'})", file=sys.stderr)
            self.status = "polling"
            while not self._stop:
                try:
                    r = await client.get(self._url("getUpdates"), params={"offset": self.offset, "timeout": 25})
                    data = r.json()
                    if not data.get("ok"):
                        if data.get("error_code") == 409:
                            self.status = "conflict"
                            self.last_error = data.get("description") or "409 - token bị poll nơi khác hoặc còn webhook."
                            print("[telegram] 409 CONFLICT - cùng token đang poll ở nơi khác. Chỉ chạy 1 nơi.", file=sys.stderr)
                            await asyncio.sleep(20)
                        else:
                            self.status = "error"
                            self.last_error = data.get("description") or "getUpdates lỗi"
                            print(f"[telegram] getUpdates lỗi: {data.get('description')}", file=sys.stderr)
                            await asyncio.sleep(10)
                        continue
                    self.status = "polling"; self.last_error = ""
                    for upd in data.get("result", []):
                        self.offset = upd["update_id"] + 1
                        cq = upd.get("callback_query")
                        if cq:
                            await self._handle_callback(client, cq)
                            continue
                        msg = upd.get("message") or upd.get("edited_message") or {}
                        chat = str((msg.get("chat") or {}).get("id", ""))
                        if not chat:
                            continue
                        if self.chat_ids and chat not in self.chat_ids:
                            await self._send(client, chat, "Bạn không có quyền dùng bot Javis này.")
                            continue
                        text = (msg.get("text") or "").strip()
                        if not text:
                            # tin không có chữ → ảnh/file đính kèm. Caption có thể là LỆNH
                            # (vd "/notes ..."): đưa lệnh lên đầu để _dispatch nhận đúng, kèm
                            # dòng "[đã tải về: path]" cho skill dùng file.
                            ingested = await self._ingest_attachment(client, msg) or ""
                            text = _caption_command_text(ingested, msg.get("caption"))
                        if not text:
                            continue
                        await self._dispatch(client, chat, text, self._build_meta(msg))
                except Exception as e:
                    print(f"[telegram loop] {type(e).__name__}: {e}", file=sys.stderr)
                    await asyncio.sleep(5)
            print("[telegram] bot stopped", file=sys.stderr)

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
                res = await self.command_fn("stop", "", chat) if self.command_fn else None
                await self._send(client, chat, (res or {}).get("reply", "⏹ Đã dừng."))
                return
            if self.command_fn:
                res = await self.command_fn(cmd, arg, chat)
                if res and "reply" in res:
                    await self._send(client, chat, res["reply"], res.get("reply_markup"))
                    return
                if res and "ask" in res:
                    text = res["ask"]   # chuyển thành câu hỏi cho Javis
                # res None → coi như tin thường (gửi nguyên text)
        # Tin thường → chạy nền. Tuần tự THEO CHAT: chỉ chặn nếu chính chat này đang bận.
        if self._busy(chat):
            await self._send(client, chat, "⏳ Đang xử lý câu trước. Gửi /stop để dừng rồi hỏi lại.")
            return
        task = asyncio.create_task(self._handle_turn(client, chat, text, meta))
        self._current[chat] = task
        # Dọn task đã xong khỏi map (tránh phình theo thời gian); chỉ xoá nếu vẫn là task này.
        task.add_done_callback(
            lambda _t, c=chat: self._current.pop(c, None) if self._current.get(c) is _t else None)

    async def _handle_callback(self, client, cq):
        """Xử lý bấm nút inline: trả lời callback (tắt spinner) + sửa tin để hiện bước kế."""
        cq_id = cq.get("id")
        data = cq.get("data") or ""
        msg = cq.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        mid = msg.get("message_id")
        if self.chat_ids and chat not in self.chat_ids:
            try:
                await client.post(self._url("answerCallbackQuery"),
                                  json={"callback_query_id": cq_id, "text": "Không có quyền"})
            except Exception:
                pass
            return
        res = await self.callback_fn(data, chat) if self.callback_fn else None
        # luôn answer để Telegram tắt vòng xoay; alert hiện toast nếu có
        try:
            await client.post(self._url("answerCallbackQuery"),
                              json={"callback_query_id": cq_id, "text": (res or {}).get("alert", "")})
        except Exception as e:
            print(f"[telegram answerCallback] {e}", file=sys.stderr)
        if not res or "text" not in res:
            return
        payload = {"chat_id": chat, "message_id": mid, "text": res["text"]}
        rm = res.get("reply_markup")
        if rm is not None:
            payload["reply_markup"] = rm   # bỏ trống → gỡ bàn phím nút (khi chọn xong/đóng)
        try:
            await client.post(self._url("editMessageText"), json=payload)
        except Exception as e:
            print(f"[telegram editMessage] {e}", file=sys.stderr)

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
        if self._task:
            self._task.cancel()
            self._task = None
