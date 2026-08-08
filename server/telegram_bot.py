"""
Telegram bot cho Javis - long-polling getUpdates, whitelist theo chat_id (MỘT hoặc NHIỀU ID).
- Trả lời chạy ở BACKGROUND task → vẫn nhận /stop giữa chừng.
- Lệnh /...: command_fn(cmd, arg, chat, meta) -> {"reply": str} | {"ask": str} | None
  (chat = chat_id người gõ → /reset //stop /retry chỉ tác động PHIÊN của họ).
- answer_fn(text, meta) nhận thêm META KÊNH (chat/user/loại chat) để engine biết
  mình đang trả lời qua đâu (port ý tưởng gateway hermes-agent), và có thể trả
  dict {"text":..., "files":[...]} để bot gửi file đính kèm sau câu trả lời.
- Gửi tin: thử MarkdownV2 (đậm/nghiêng/code hiện đẹp) → hỏng thì gửi lại plain
  (mirror vòng (True, False) trong telegram adapter của hermes).
- Nhận file/ảnh từ user: tự tải về download_dir rồi đưa đường dẫn vào tin nhắn.
- precheck_fn(text, meta) -> None|{"reply":...}: chặn một tin TRƯỚC khi tốn lượt (bot chuyên
  trách dùng để không mở miệng trong nhóm chưa được cho phép).
- event_fn(loai, thong_tin): tin DỊCH VỤ của nhóm (bot vào nhóm / bị đá / nhóm nâng cấp lên
  siêu nhóm và đổi id). Telegram gửi mấy tin này bất kể chế độ riêng tư.
Decoupled: main.py cấp answer_fn (1 lượt chat) + command_fn (xử lý lệnh).
"""
import asyncio
import re
import sys
import time
from pathlib import Path

import httpx

from bot_gateway import HangLuot, dong_vet, ten_tool


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
    {"command": "cli", "description": "Engine Claude Code (MCP Javis + lệnh máy)"},
    {"command": "or", "description": "Engine OpenRouter (MCP Javis, không lệnh máy)"},
]

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_DOC_MB = 50     # trần sendDocument của bot API
MAX_PHOTO_MB = 10   # trần sendPhoto
MAX_DOWNLOAD_MB = 20  # bot API chỉ cho TẢI VỀ file ≤ 20MB

# ---- Chế độ "nói như người thật" (giau_trang_thai=True) ----
# Chủ repo gửi ảnh chụp một nhóm Telegram (2026-08-07): bot chuyên trách đang nói chuyện như
# một người, rồi giữa cuộc nói chuyện hiện ra "⏳ Đang xử lý câu trước. Gửi /stop để dừng rồi
# hỏi lại." trước mặt cả nhóm. Một câu như vậy là khai ngay đây là máy, và còn dạy người lạ
# một lệnh quản trị. Yêu cầu: "các phần trạng thái của Javis anh không muốn để lộ ra như vậy,
# anh muốn ẩn đi để như cảm giác người thật nói chứ ko phải bot."
#
# Ở chế độ này, thứ THAY THẾ tin trạng thái là chấm "đang nhập…" của chính Telegram - đúng thứ
# một người thật để lại khi họ đang gõ. Và tin nhắn tới lúc bot đang bận thì XẾP HÀNG rồi trả
# lời một thể, chứ không bị chặn: im lặng mà đánh rơi câu hỏi của khách còn tệ hơn cả tin
# trạng thái.
TYPING_MOI_GIAY = 4.0   # Telegram tắt chấm "đang nhập" sau ~5 giây, phải nhắc lại trước đó
# Hàng đợi lượt, luật /stop, cổng precheck và dòng vết công cụ nằm ở `bot_gateway`: chúng là
# luật hành vi của Javis, không phải chi tiết của Telegram, nên kênh Zalo dùng chung y hệt.

# Câu duy nhất được nói ra khi một lượt gãy ở chế độ người thật. Không mã lỗi, không tên lớp
# ngoại lệ - người thật không đọc traceback ra miệng. Chi tiết vẫn vào stderr + log bot.
CAU_LOI_NGUOI_THAT = ("Dạ em xin lỗi, chỗ này em đang trục trặc nên chưa trả lời ngay được ạ. "
                      "Anh chị nhắn lại giúp em một chút nữa nhé.")


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


class TelegramBot(HangLuot):
    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai=False):
        self.token = token
        # Giấu MỌI tin trạng thái/kỹ thuật của Javis, để cuộc trò chuyện đọc như người thật.
        # Bot của CHỦ để False (chủ cần thấy "đang gọi công cụ…", cần lệnh /stop); bot chuyên
        # trách nói với khách thì True. Xem khối chú thích ở đầu file.
        self.giau_trang_thai = bool(giau_trang_thai)
        # chat_id nhận chuỗi "id1,id2" hoặc list → whitelist NHIỀU người dùng chung 1 bot.
        self.chat_ids = parse_chat_ids(chat_id)
        # Menu lệnh đẩy lên Telegram. Mặc định là menu của CHỦ; bot chuyên trách truyền menu
        # riêng vào đây. Trước đây ghim cứng BOT_COMMANDS nên bot chăm sóc khách hiện cho
        # khách thấy "/brain - Xem hoặc đổi brain (vault) của phiên này" - khai ra cả một tập
        # lệnh quản trị mà chính nó từ chối chạy.
        self.commands = BOT_COMMANDS if commands is None else list(commands)
        self.answer_fn = answer_fn          # async (text, meta, progress) -> str | {"text":..., "files":[...]}; progress(txt) = báo trạng thái trung gian
        self.command_fn = command_fn        # async (cmd, arg, chat, meta) -> dict|None
        self.callback_fn = callback_fn      # async (data, chat) -> dict|None (bấm nút inline; chat = ai bấm)
        # Chốt chặn TRƯỚC khi tốn một lượt: sync (text, meta) -> None|dict. CHỈ `None` là chạy
        # tiếp; MỌI dict đều bỏ lượt, kể cả `{}` (chặn mà không nói gì). Đừng đổi thành kiểm
        # tra truthy: `{}` falsy nên lượt sẽ chạy tiếp, và đó đúng là con bọ đã sống ở đây.
        # `reply` trong dict (nếu có) được gửi thẳng như một câu nói thường.
        #
        # Vì sao chặn ở ĐÂY chứ không để answer_fn trả chuỗi rỗng: `_handle_turn` gửi tin
        # "🤔 đang xử lý…" NGAY trước khi gọi answer_fn, nên bot từ chối một tin trong nhóm lạ
        # vẫn kịp nhấp nháy một tin rồi xoá, và cuối cùng gửi "(không có nội dung)" vào mặt
        # người ngoài. Im lặng phải là im lặng thật, quyết ngay từ lúc chưa gửi gì.
        self.precheck_fn = precheck_fn
        # Tin DỊCH VỤ của nhóm: async (loai, thong_tin) -> None. Xem `_bao_su_kien`.
        self.event_fn = event_fn
        self.download_dir = download_dir    # str | callable(chat) -> str: nơi lưu file user gửi lên
        self._task = None
        # ĐA PHIÊN: mỗi chat_id có lượt trả lời RIÊNG → các tài khoản chạy song song,
        # cùng 1 tài khoản vẫn tuần tự (1 lượt/lúc). Map chat_id(str) -> asyncio.Task.
        self._current = {}
        # Tin đến trong lúc chat đó đang bận, chờ trả lời xong lượt trước rồi gộp làm một lượt.
        # Chỉ dùng ở chế độ người thật; chế độ chủ vẫn báo "đang xử lý câu trước" như cũ.
        # chat_id(str) -> {"texts": [str], "meta": dict}
        self._cho = {}
        self._stop = False
        self.offset = 0
        self.status = "off"      # off | starting | polling | conflict | error | stopped
        self.last_error = ""
        # Danh tính của CHÍNH con bot này, lấy bằng getMe lúc khởi động. Cần để biết một tin
        # trong nhóm có nhắc tên nó hay reply vào nó không - xem _build_meta.
        self.bot_id = 0
        self.bot_username = ""
        # Chế độ riêng tư của Telegram, đọc từ getMe (`can_read_all_group_messages`). True =
        # ĐÃ TẮT riêng tư ở BotFather, bot nhận mọi tin trong nhóm. False = còn bật (mặc định),
        # trong nhóm bot chỉ nhận tin nhắc tên nó, tin trả lời vào nó, và lệnh.
        #
        # Cần phơi ra vì nó im lặng vô hiệu hoá một tuỳ chọn của Javis: đặt bot "trả lời mọi
        # tin trong nhóm" mà riêng tư còn bật thì Telegram chặn từ trước khi Javis nhìn thấy,
        # và trang Chatbot cứ hiện xanh trong khi bot điếc một nửa.
        self.doc_moi_tin_nhom = False
        # getMe hỏng thì bot KHÔNG biết @username của chính nó, và lúc đó `_co_nhac_ten` trả
        # False cho MỌI tin - bot điếc trong mọi nhóm trong khi tin nhắn riêng vẫn chạy ngon
        # lành. Bản trước nuốt lỗi này bằng một dòng stderr rồi đặt trạng thái "polling", nên
        # thẻ vẫn xanh và không có chỗ nào nói ra. Giữ riêng khỏi `last_error` vì vòng lặp xoá
        # `last_error` sau mỗi lượt poll thành công, còn lỗi này thì vẫn còn nguyên đó.
        self.loi_danh_tinh = ""
        self._lan_hoi_danh_tinh = 0.0

    def _url(self, method):
        return TG_API.format(token=self.token, method=method)

    async def _send(self, client, chat, text, reply_markup=None):
        # "(không có nội dung)" là một dòng gỡ lỗi. Ở chế độ người thật thì thà không nói gì
        # còn hơn nói ra một câu chỉ có nghĩa với người viết code.
        if not str(text or "").strip() and self.giau_trang_thai:
            return
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

    async def _giu_typing(self, client, chat):
        """Giữ chấm "đang nhập…" sáng suốt cả lượt trả lời (chế độ người thật).

        Đây là thứ THAY THẾ tin "🤔 Javis đang xử lý…": người đang chờ vẫn thấy đầu kia có
        động tĩnh, nhưng thấy đúng cái một người thật để lại chứ không phải một tin nhắn máy.
        Telegram tự tắt chấm sau ~5 giây nên phải nhắc lại đều.
        """
        while True:
            await self._typing(client, chat)
            await asyncio.sleep(TYPING_MOI_GIAY)

    # ---- Tin TRẠNG THÁI: gửi IM LẶNG → cập nhật theo tiến trình → ở lại làm dòng vết ----
    async def _send_status(self, client, chat, text):
        """Gửi 1 tin trạng thái (plain, không markdown) → trả message_id để sửa sau.

        `disable_notification` là phần quan trọng chứ không phải chi tiết làm đẹp. Trước đây
        mỗi lượt hỏi nổ HAI thông báo lên điện thoại: một cái "🤔 Javis đang xử lý…" hoàn toàn
        vô nghĩa, rồi mới tới câu trả lời. Tin này chỉ để NHÌN trong lúc chờ, không phải để
        gọi người ta ra xem, nên nó đi im. Sửa tin (`editMessageText`) vốn không nổ thông báo,
        nên cả lượt chỉ còn đúng một tiếng chuông: lúc câu trả lời thật được gửi.
        """
        try:
            r = await client.post(self._url("sendMessage"),
                                  json={"chat_id": chat, "text": text,
                                        "disable_notification": True})
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

    def _dong_vet(self, tools, giay):
        """Chữ CUỐI CÙNG của tin trạng thái. Luật nằm ở `bot_gateway.dong_vet` (dùng chung
        với kênh Zalo); giữ phương thức này làm cửa cho test và cho chỗ gọi đọc dễ."""
        return dong_vet(tools, giay)

    # ---- Meta kênh: engine cần biết tin đến từ đâu (DM/nhóm, ai gửi) ----
    def _build_meta(self, msg):
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
            "bot_username": self.bot_username,
            "mentioned": self._co_nhac_ten(msg),
            "reply_to_bot": self._la_reply_bot(msg),
        }

    def _co_nhac_ten(self, msg):
        """Tin này có nhắc tên CHÍNH con bot này không.

        Cần cho bot chuyên trách trong nhóm: mặc định nó chỉ mở miệng khi được gọi tên. Trước
        0.19.1 hai cờ này không ai gắn, nên luật "chỉ trả lời khi được gọi tên" đọc phải None
        và bot IM trong mọi nhóm - hỏng đúng kiểu im lặng, không log, không báo.

        Hai đường nhắc của Telegram, phải nhận cả hai:
          - `mention`: khách gõ "@ten_bot", entity chỉ cho offset/length nên phải cắt chuỗi ra so.
          - `text_mention`: khách bấm chọn từ danh sách thành viên, không có "@" trong chữ,
            danh tính nằm ở `entity.user.id`.
        """
        if not (self.bot_username or self.bot_id):
            return False
        u = "@" + str(self.bot_username or "").lower()
        for khoa_text, khoa_ent in (("text", "entities"), ("caption", "caption_entities")):
            s = msg.get(khoa_text) or ""
            for e in (msg.get(khoa_ent) or []):
                loai = e.get("type")
                if loai == "mention" and self.bot_username:
                    off, ln = e.get("offset") or 0, e.get("length") or 0
                    if s[off:off + ln].lower() == u:
                        return True
                elif loai == "text_mention" and self.bot_id:
                    if (e.get("user") or {}).get("id") == self.bot_id:
                        return True
        # Không có entity nào khớp: rơi xuống so chuỗi thô. Cần vì `entities` là thứ Telegram
        # gắn thêm chứ không phải một bảo đảm - tin chuyển tiếp, tin do bot khác dựng lại, và
        # vài client đã thấy về tới nơi mà không kèm entity nào. Bỏ nhánh này thì đúng cái ca
        # "gọi tên mà bot im" quay lại, và nó im lặng không log gì.
        #
        # Chặn hậu tố ở cuối: "@shopbot" và "@shopbotvn" là hai username hợp lệ khác nhau, và
        # so chuỗi trần trụi thì con thứ nhất nhận vơ mọi câu gọi con thứ hai.
        if self.bot_username:
            re_ten = re.compile(re.escape(u) + r"(?![A-Za-z0-9_])", re.I)
            for khoa_text in ("text", "caption"):
                if re_ten.search(str(msg.get(khoa_text) or "")):
                    return True
        return False

    def _la_reply_bot(self, msg):
        """Tin này có phải reply vào một tin của CHÍNH con bot này không.

        So theo id chứ không theo cờ `is_bot`: trong nhóm có thể có nhiều bot, reply vào bot
        khác mà tính là gọi mình thì bot chen ngang vào việc của người ta.
        """
        rep = msg.get("reply_to_message") or {}
        return bool(self.bot_id) and (rep.get("from") or {}).get("id") == self.bot_id

    async def _hoi_danh_tinh(self, client, lan=3):
        """getMe: bot phải biết @username và id của CHÍNH NÓ. Hỏng cái này là điếc trong nhóm.

        Vì sao đáng một hàm riêng có thử lại, trong khi mấy lời gọi khởi động khác thì không:
        `deleteWebhook` hay `setMyCommands` hỏng thì hậu quả nhìn thấy được ngay. Còn getMe
        hỏng thì bot vẫn poll, vẫn trả lời tin nhắn riêng hoàn hảo, chỉ **im trong mọi nhóm** -
        vì `_co_nhac_ten` không có gì để so nên trả False cho mọi tin. Triệu chứng đó (riêng
        thì được, nhóm im re) trùng khít với chế độ riêng tư của Telegram, nên đứng ngoài nhìn
        không thể phân biệt được hai nguyên nhân, và cả hai đều không để lại dấu vết nào.

        Một cú mạng hỏng đúng giây khởi động là đủ. Nên: thử lại, và thất bại thì GIỮ LẠI lý do
        cho trang Chatbot nói ra, chứ không nuốt bằng một dòng stderr.
        """
        self._lan_hoi_danh_tinh = time.monotonic()
        loi = ""
        for i in range(max(1, lan)):
            try:
                r = await client.get(self._url("getMe"))
                d = r.json() or {}
                me = d.get("result") or {}
                if me.get("id"):
                    self.bot_id = me["id"]
                    self.bot_username = me.get("username") or ""
                    self.doc_moi_tin_nhom = bool(me.get("can_read_all_group_messages"))
                    self.loi_danh_tinh = ""
                    return True
                loi = str(d.get("description") or f"getMe HTTP {r.status_code}")
            except Exception as e:
                loi = f"{type(e).__name__}: {e}"
            if i < lan - 1:
                await asyncio.sleep(2 ** i)
        self.loi_danh_tinh = (
            f"Không hỏi được danh tính bot từ Telegram ({loi}). Bot vẫn trả lời tin nhắn RIÊNG, "
            "nhưng trong nhóm nó không nhận ra được ai đang gọi tên mình nên sẽ im. "
            "Tắt rồi bật lại bot để thử lại.")
        print(f"[telegram getMe] {loi}", file=sys.stderr)
        return False

    async def _bao_su_kien(self, msg):
        """Tin DỊCH VỤ của nhóm - thứ Javis nghe được BẤT KỂ chế độ riêng tư của Telegram.

        Ba loại đáng quan tâm, cả ba đều là lúc "im lặng" nghĩa là hỏng:

          - **vao_nhom**: có người vừa thả bot vào một nhóm. Đây là lúc DUY NHẤT biết được id
            nhóm mà không bắt chủ đi gõ /id rồi chép tay sang dashboard.
          - **roi_nhom**: bot bị đá ra. Không dọn thì trang Chatbot còn nhắc mãi một nhóm
            không còn nữa.
          - **nhom_nang_cap**: nhóm thường lên siêu nhóm thì Telegram ĐỔI id (thêm tiền tố
            -100). Danh sách nhóm chủ khai lúc trước lập tức trỏ vào một id không còn tồn tại,
            và bot im trong đúng cái nhóm nó vừa trả lời được hôm qua.
        """
        if not self.event_fn:
            return
        chat_obj = msg.get("chat") or {}
        loai = ""
        if self.bot_id and any((u or {}).get("id") == self.bot_id
                               for u in (msg.get("new_chat_members") or [])):
            loai = "vao_nhom"
        elif self.bot_id and (msg.get("left_chat_member") or {}).get("id") == self.bot_id:
            loai = "roi_nhom"
        elif msg.get("migrate_to_chat_id"):
            loai = "nhom_nang_cap"
        elif str(chat_obj.get("type") or "private") != "private":
            # Bất kỳ tin nào về từ một nhóm. Nghe cả loại này vì nó là đường DUY NHẤT còn chắc
            # chắn khi chế độ riêng tư của Telegram đang bật: lệnh `/...` luôn về tới nơi, còn
            # tin nhắc tên thì chưa chắc. Không nghe thì gõ /id trong nhóm xong quay lại
            # dashboard vẫn không thấy nhóm nào - đúng ngõ cụt cần tránh.
            loai = "thay_nhom"
        if not loai:
            return
        try:
            await self.event_fn(loai, {
                "chat_id": str(chat_obj.get("id", "")),
                "chat_title": chat_obj.get("title", ""),
                "chat_type": chat_obj.get("type", ""),
                "chat_id_moi": str(msg.get("migrate_to_chat_id") or ""),
            })
        except Exception as e:
            print(f"[telegram sự kiện nhóm] {type(e).__name__}: {e}", file=sys.stderr)

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
        # Chờ dài mà đầu kia im hẳn thì người ta tưởng hỏng. Hai cách nói điều đó:
        #   - bot của CHỦ: một tin trạng thái gửi IM LẶNG, cập nhật theo tiến trình (đang gọi
        #     công cụ / nhận data / soạn trả lời), xong thì Ở LẠI thành một dòng vết gọn;
        #   - chế độ NGƯỜI THẬT: không tin nào cả, chỉ giữ chấm "đang nhập…" của Telegram.
        #
        # Trước 0.26.4 tin trạng thái bị XOÁ rồi mới gửi câu trả lời. Hai chỗ sai: người dùng
        # thấy một tin nhấp nháy rồi biến mất (đọc như lỗi, và ai đang đọc dở thì mất chữ), và
        # mỗi lượt nổ hai thông báo mà cái đầu chỉ nói "đang xử lý". Nay không xoá gì nữa.
        # Telegram KHÔNG có bề mặt nào hiện chữ tuỳ ý ngoài tin nhắn (`sendChatAction` chỉ nhận
        # một bộ hành động cố định, không nhận chữ), nên "hiện trạng thái mà không gửi tin" là
        # bất khả; thứ sửa được là đừng để tin nào biến mất và đừng nổ thông báo thừa.
        status_mid = None
        giu = None
        if self.giau_trang_thai:
            giu = asyncio.create_task(self._giu_typing(client, chat))
        else:
            status_mid = await self._send_status(client, chat, "🤔 Javis đang xử lý…")
        _last = [0.0]
        t0 = time.monotonic()
        tools = []          # tên công cụ đã gọi trong lượt, giữ thứ tự, không trùng

        async def progress(txt):
            if self.giau_trang_thai:
                return              # đã có chấm "đang nhập…" chạy đều, không cần tin nào
            # Gom tên công cụ TRƯỚC cửa throttle. Throttle sinh ra để đỡ spam Telegram, không
            # phải để quên bớt việc đã làm: gom sau cửa thì mấy tool chạy nhanh (2 tool trong
            # cùng một giây) rụng khỏi dòng vết, và dòng vết là thứ nằm lại vĩnh viễn.
            ten = ten_tool(txt)
            if ten and ten not in tools:
                tools.append(ten)
            now = time.monotonic()
            if now - _last[0] < 2.5:      # throttle ~2.5s → không spam / dính rate-limit Telegram
                return
            _last[0] = now
            await self._typing(client, chat)
            await self._edit_status(client, chat, status_mid, "⏳ " + (txt or "Đang xử lý…"))

        try:
            try:
                reply = await self.answer_fn(text, meta, progress)
            except asyncio.CancelledError:
                # /stop: tin trạng thái ở lại nói rõ lượt này đã bị cắt, thay vì biến mất không
                # dấu vết rồi để người ta tự đoán câu hỏi của mình đã đi đâu.
                await self._edit_status(client, chat, status_mid, "⏹ Đã dừng.")
                return   # /stop sẽ tự báo, không gửi trùng
            except Exception as e:
                print(f"[telegram lượt hỏng] {type(e).__name__}: {e}", file=sys.stderr)
                # Người thật không đọc tên lớp ngoại lệ ra miệng.
                reply = (CAU_LOI_NGUOI_THAT if self.giau_trang_thai
                         else f"⚠ Lỗi: {type(e).__name__}: {e}")
            im_lang = False
            if isinstance(reply, dict):
                files = reply.get("files") or []
                # Im lặng CÓ CHỦ Ý (bot không được phép mở miệng ở nhóm này) khác hẳn câu trả lời
                # rỗng vì hỏng. Không phân biệt thì cả hai cùng ra "(không có nội dung)" - vừa lộ
                # với người ngoài, vừa che mất lượt hỏng thật.
                im_lang = bool(reply.get("im_lang"))
                reply = reply.get("text") or ""
            # Chốt tin trạng thái thành dòng vết rồi ĐỂ NGUYÊN ĐÓ. Câu trả lời đi sau, là một
            # tin MỚI có chuông - nên thông báo trên điện thoại hiện đúng nội dung trả lời.
            await self._edit_status(client, chat, status_mid,
                                    self._dong_vet(tools, time.monotonic() - t0))
            if im_lang and not str(reply or "").strip() and not files:
                return
            # Nếu câu trả lời chỉ là ![](local-path) và file đã được tách để gửi riêng, không gửi
            # thêm tin "(không có nội dung)" trước ảnh.
            if str(reply or "").strip() or not files:
                await self._send(client, chat, reply)
            # Gửi file SAU câu trả lời để thứ tự đọc tự nhiên (text trước, đính kèm sau)
            for f in files:
                fpath, fcap = (f.get("path"), f.get("caption", "")) if isinstance(f, dict) else (f, "")
                ok, err = await self.send_file(fpath, fcap, chat=chat)
                if not ok:
                    print(f"[telegram gửi file] {fpath}: {err}", file=sys.stderr)
                    if not self.giau_trang_thai:
                        await self._send(client, chat,
                                         f"⚠ Không gửi được file {Path(str(fpath)).name}: {err}")
        finally:
            if giu:
                giu.cancel()

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
            await self._hoi_danh_tinh(client)
            try:
                await client.post(self._url("setMyCommands"), json={"commands": self.commands})
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
                    # Danh tính hỏng lúc khởi động thì hỏi lại mỗi phút. Mạng rớt đúng giây
                    # khởi động là chuyện thường, và không có nhánh này thì bot điếc trong nhóm
                    # cho tới khi có người nghĩ ra việc tắt bật lại nó.
                    if not self.bot_id and time.monotonic() - self._lan_hoi_danh_tinh > 60:
                        await self._hoi_danh_tinh(client, lan=1)
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
                        # Tin dịch vụ đi TRƯỚC whitelist: "bot vừa bị thả vào nhóm nào" là
                        # chuyện phải biết kể cả (nhất là) khi nhóm đó chưa được cho phép.
                        await self._bao_su_kien(msg)
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
        self._cho.clear()
        if self._task:
            self._task.cancel()
            self._task = None
