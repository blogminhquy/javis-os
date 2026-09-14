"""Bộ não GIỌNG NÓI riêng (Voice V2, docs/dev/2026-09-voice-v2-spec.md mục 2).

Khi người dùng NÓI với Javis, lượt đi qua một bộ não nhanh và nhẹ ở đây thay vì bộ não chính
(vốn dựng tiến trình, nạp MCP và prompt dài, mất 5-10 giây mới ra chữ đầu). Bộ não giọng trả
lời ngắn, và khi câu hỏi cần dữ liệu, tool, file, ký ức hay hành động thì nó trả đúng một dòng
`JAVIS_ASK_MAIN: <yêu cầu>`; main.py đọc dòng đó rồi chạy lượt bộ não chính như thường.

Hai loại bộ não:
  - AntigravityVoiceBrain: MỘT tiến trình `agy --input-format stream-json` sống suốt phiên
    nói. Đo 2026-09-14: lượt đầu 4,2 s (khởi động), lượt sau 1,3-2,0 s, stream từng mảnh
    chữ qua `step_update.text_delta`. Chạy trên gói Google đã có, không cần API key.
  - ApiVoiceBrain: Groq / Gemini / OpenAI / OpenRouter qua các hàm stream sẵn có trong
    engine.py, dùng key ở trang Models.

Sổ phiên: mỗi phiên chat web một bộ não, đóng sau IDLE_S giây không nói. Không import main.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from typing import AsyncIterator, Callable, Dict, List, Optional

import winproc         # lệnh con câm lặng trên Windows (canary test_windows_no_console)

MARKER = "JAVIS_ASK_MAIN:"
# Đường TẮT cho việc chỉ đụng tới giao diện: bộ não giọng tự phát, server gọi thẳng dashboard,
# không phải đánh thức bộ não chính (xem parse_ui).
UI_MARKER = "JAVIS_UI:"
UI_ACTIONS = ("open_page", "open_group", "sidebar", "scroll")
IDLE_S = 300.0
TURN_TIMEOUT_S = 90.0
HISTORY_N = 10
# Danh sách các ô CHỌN của thẻ "Chế độ và bộ não giọng nói". Đây là NGUỒN DUY NHẤT: trang Cài
# đặt (GET /voice/options) vẽ từ đây, và đường lưu (POST /settings) cũng nhận đúng những giá trị
# này. Hai nơi giữ hai danh sách riêng là cách sinh ra lỗi "bấm Lưu thấy xong, F5 là mất".
MODES = ("standard", "fast", "live")

# key_field rỗng = chạy trên gói người dùng đã đăng nhập, không cần API key.
BRAIN_PROVIDERS = {
    "": {"label": "Bộ não chính (như gõ chữ)", "key_field": "", "default_model": ""},
    "antigravity": {"label": "Antigravity CLI (gói Google)", "key_field": "", "default_model": ""},
    # Ba bộ não chạy trên GÓI đã đăng nhập ở trang Models (Voice V3, spec mục 13): lớp giọng chỉ
    # cần một model trả lời ngắn và nhanh, nên bộ não nào cũng cắm được.
    "codex": {"label": "ChatGPT (gói ChatGPT, qua Codex)", "key_field": "", "default_model": ""},
    "claude": {"label": "Claude Code (gói Claude)", "key_field": "", "default_model": "haiku"},
    "grok": {"label": "Grok Build (gói SuperGrok / X Premium+)", "key_field": "", "default_model": ""},
    "groq": {"label": "Groq (API)", "key_field": "groq_api_key", "default_model": "llama-3.3-70b-versatile"},
    "gemini": {"label": "Google Gemini (API)", "key_field": "gemini_api_key", "default_model": "gemini-2.5-flash"},
    "openai": {"label": "OpenAI (API)", "key_field": "openai_api_key", "default_model": "gpt-4o-mini"},
    "openrouter": {"label": "OpenRouter", "key_field": "openrouter_key", "default_model": "google/gemini-2.5-flash"},
}

STT_PROVIDERS = {
    "browser": {"label": "Trình duyệt (Web Speech, miễn phí)", "key_field": ""},
    "groq": {"label": "Groq Whisper (chính xác hơn)", "key_field": "groq_api_key"},
}

# Bộ não chạy bằng API key (antigravity chạy bằng gói nên không nằm trong đây).
PROVIDERS = tuple(k for k, p in BRAIN_PROVIDERS.items() if p["key_field"])

SYSTEM_PROMPT = (
    "Bạn là Javis, trợ lý cá nhân, đang NÓI CHUYỆN BẰNG GIỌNG với người dùng. Trả lời như người "
    "đang nói: ngắn (1 đến 3 câu), tự nhiên, không markdown, không gạch đầu dòng, không emoji, "
    "không dấu gạch dài. Trả lời bằng đúng ngôn ngữ người dùng vừa dùng.\n"
    "Bạn KHÔNG có tool và KHÔNG biết dữ liệu sống. Khi câu hỏi cần bất kỳ thứ nào sau đây: số liệu "
    "kinh doanh, lịch, email, file hay ghi chú trong brain, ký ức dài hạn, giao việc, nhắc hẹn, mở "
    "trang hay mở app, gửi tin, hay bất cứ hành động nào ra ngoài, thì KHÔNG đoán và KHÔNG bịa. Thay "
    "vào đó trả lời đúng khuôn này: MỘT câu xác nhận ngắn, tự nhiên ở dòng đầu (kiểu 'Ừ, để mình "
    "xem.', 'Rồi, để mình kiểm tra ngay.'), rồi một dòng riêng bắt đầu bằng " + MARKER + " theo sau là "
    "yêu cầu ĐẦY ĐỦ, tự đứng được (bộ não chính không nghe cuộc nói chuyện này) để bộ não chính của "
    "Javis thực hiện. Không viết gì sau dòng đó. Việc đó chạy NỀN như một việc riêng: kết quả tự "
    "hiện trong khung chat khi xong, còn bạn vẫn trò chuyện tiếp bình thường; có thể giao nhiều việc "
    "nền liên tiếp. Người dùng hỏi tiến độ thì nói việc đang chạy, KHÔNG bịa kết quả.\n"
    "NGOẠI LỆ, làm NGAY không nhờ bộ não chính: khi người dùng chỉ bảo ĐIỀU KHIỂN MÀN HÌNH, hãy "
    "trả lời một câu ngắn xác nhận rồi xuống dòng ghi " + UI_MARKER + " kèm lệnh:\n"
    "  " + UI_MARKER + " open_page <id trang>   (mở một tab. Viết ID tiếng Anh; trong ngoặc là nhãn "
    "người dùng nhìn thấy và hay đọc lên: home (Javis), chat (trò chuyện), files (tệp tin), "
    "learn (tự học), terminal, agents (trợ lý), chatbots (chatbot), skills (kỹ năng), "
    "workflows (quy trình), plugins (công cụ), kanban (việc), selfimprove (việc định kỳ), "
    "mcp (kết nối), packs (Javis Store), channels (kênh), models, usage (mức dùng), "
    "settings (cài đặt), logs (cập nhật), account (tài khoản))\n"
    "  " + UI_MARKER + " open_group <id nhóm>   (BUNG một mục đang gập trên thanh bên mà không đổi "
    "trang: tro_ly (Trợ lý), bo_nao (Bộ não), code (Code), nang_luc (Năng lực), viec (Việc), "
    "ket_noi (Kết nối), he_thong (Hệ thống))\n"
    "  " + UI_MARKER + " sidebar open | close    (bung hay thu gọn cả thanh bên)\n"
    "  " + UI_MARKER + " scroll top | bottom     (cuộn khung chat)\n"
    "Chỉ dùng khuôn này cho việc thuần giao diện. Muốn biết NỘI DUNG bên trong trang thì vẫn phải "
    "nhờ bộ não chính.\n"
    "Chuyện trò thường, hỏi ý kiến, giải thích khái niệm, tính nhẩm, chuyển ngữ: trả lời thẳng."
)

_MARK_RE = re.compile(r"^[ \t]*" + re.escape(MARKER) + r"[ \t]*(.+?)[ \t]*$", re.M)
_UI_RE = re.compile(r"^[ \t]*" + re.escape(UI_MARKER) + r"[ \t]*(.+?)[ \t]*$", re.M)


def parse_marker(text: str):
    """(câu chờ, yêu cầu cho bộ não chính | None). Bỏ dòng marker khỏi câu chờ."""
    t = str(text or "")
    m = _MARK_RE.search(t)
    if not m:
        return t.strip(), None
    filler = t[:m.start()].strip()
    return filler, m.group(1).strip()


def parse_ui(text: str):
    """(câu nói, (action, target) | None) cho dòng `JAVIS_UI:`.

    Vì sao có đường tắt này: mở một tab là việc KHÔNG cần dữ liệu gì. Trước đây nó vẫn phải đi
    `JAVIS_ASK_MAIN` sang bộ não chính, mà bộ não chính mang cả ngữ cảnh hội thoại (có lúc hơn
    200 nghìn token) nên một câu "mở trang Models" mất hàng chục giây. Bộ não giọng tự phát
    dòng này thì server gọi thẳng dashboard, còn đúng độ trễ của chính bộ não giọng.
    """
    t = str(text or "")
    m = _UI_RE.search(t)
    if not m:
        return t.strip(), None
    noi = (t[:m.start()] + t[m.end():]).strip()
    phan = m.group(1).strip().split(None, 1)
    action = phan[0].strip().lower()
    target = (phan[1].strip() if len(phan) > 1 else "")
    if action not in UI_ACTIONS:
        return t.strip(), None          # model bịa action lạ: coi như không có, đừng nuốt câu
    return noi, (action, target)


# Đoạn stream chưa có dấu kết câu mà dài quá mức này thì cắt ở dấu phẩy/khoảng trắng cuối,
# để một câu dài lê thê không giữ loa im mãi.
SPEAK_MAX = 220
_SENT_END = re.compile(r"[.!?…]+[\"'”’)\]]*(?=\s|$)")


def split_speakable(text: str, start: int, final: bool = False):
    """Cắt phần chữ từ `start` thành các mẩu ĐỌC ĐƯỢC cho loa; trả (mẩu, vị trí mới).

    Vì sao phải có hàm này (bài học 0.57.1): trước đây làn nhanh đẩy MỖI delta stream (vài từ)
    thành một khung cho trình duyệt, mà trình duyệt đọc mỗi khung là một yêu cầu TTS riêng ->
    hàng chục yêu cầu Edge, mỗi cái một độ trễ mạng, nghe giật và cà nhắc như cắt từng mẩu.
    Nay chỉ phát khi CÂU đã khép (dấu . ! ? … hoặc xuống dòng), hoặc khi đoạn dở dài quá
    SPEAK_MAX thì cắt ở dấu phẩy/khoảng trắng cuối; `final` thì đẩy nốt phần đuôi.

    Dòng marker `JAVIS_ASK_MAIN:` không bao giờ ra loa: dòng mới mà chữ đầu trùng đầu marker
    thì giữ lại tới khi biết chắc; đã là marker thì bỏ cả dòng.
    """
    out: List[str] = []
    while start < len(text):
        nl = text.find("\n", start)
        line_start = text.rfind("\n", 0, start) + 1
        if nl < 0:
            line = text[line_start:]
            if not final and any(mk.startswith(line.lstrip()) or line.lstrip().startswith(mk)
                                 for mk in (MARKER, UI_MARKER)):
                break                          # chưa biết có phải marker: đợi thêm
            if line.lstrip().startswith((MARKER, UI_MARKER)):
                start = len(text)              # final: dòng marker, bỏ
                break
            partial = text[start:]
            if final:
                if partial.strip():
                    out.append(partial)
                start = len(text)
                break
            # Chưa xuống dòng: chỉ lấy tới dấu kết câu cuối cùng.
            last_end = -1
            for m in _SENT_END.finditer(partial):
                last_end = m.end()
            if last_end > 0:
                out.append(partial[:last_end])
                start += last_end
                continue
            if len(partial) >= SPEAK_MAX:
                cut = max(partial.rfind(",", 0, SPEAK_MAX), partial.rfind(" ", 0, SPEAK_MAX))
                if cut > 20:
                    out.append(partial[:cut + 1])
                    start += cut + 1
                    continue
            break                              # câu còn dở: đợi thêm chữ
        chunk = text[start:nl + 1]
        line = text[line_start:nl + 1]
        start = nl + 1
        if line.lstrip().startswith((MARKER, UI_MARKER)):
            continue
        if chunk.strip():
            out.append(chunk)
    return out, start


def seed_text(history: List[dict], text: str, with_prompt: bool = True) -> str:
    """Lượt ĐẦU của một tiến trình/mạch mới: hướng dẫn (nếu engine không nhận system prompt
    riêng) + mấy lượt gần nhất từ kho phiên + câu vừa nói. Dùng chung cho agy, Claude, Grok."""
    parts = []
    if with_prompt:
        parts.append("[HƯỚNG DẪN CHO LƯỢT NÓI CHUYỆN NÀY]\n" + SYSTEM_PROMPT)
    h = [x for x in (history or [])[-HISTORY_N:] if str(x.get("content") or "").strip()]
    if h:
        parts.append("[MẤY LƯỢT GẦN NHẤT TRONG PHIÊN NÀY]")
        for x in h:
            ai = "Javis" if x.get("role") == "assistant" else "Người dùng"
            parts.append(f"{ai}: {str(x.get('content'))[:1500]}")
    parts.append("[NGƯỜI DÙNG VỪA NÓI]\n" + str(text or ""))
    return "\n\n".join(parts)


def build_messages(history: List[dict], text: str, system: str = SYSTEM_PROMPT) -> List[dict]:
    msgs = [{"role": "system", "content": system}]
    for h in (history or [])[-HISTORY_N:]:
        role = "assistant" if h.get("role") == "assistant" else "user"
        c = str(h.get("content") or "").strip()
        if c:
            msgs.append({"role": role, "content": c[:2000]})
    msgs.append({"role": "user", "content": str(text or "")})
    return msgs


class VoiceBrain:
    provider = ""
    model = ""

    def __init__(self):
        self.last_used = time.time()
        self._lock = asyncio.Lock()

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:  # pragma: no cover
        raise NotImplementedError
        yield ""

    async def close(self) -> None:
        return None


class ApiVoiceBrain(VoiceBrain):
    """Groq / Gemini / OpenAI / OpenRouter qua engine.<prov>_stream."""

    def __init__(self, provider: str, api_key: str, model: str, stream_fn: Optional[Callable] = None):
        super().__init__()
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self._stream_fn = stream_fn

    def _fn(self):
        if self._stream_fn:
            return self._stream_fn
        import engine
        return {
            "groq": engine.groq_stream, "gemini": engine.gemini_stream,
            "openai": engine.openai_stream, "openrouter": engine.openrouter_stream,
        }[self.provider]

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        msgs = build_messages(history, text)
        async with self._lock:
            async for ev in self._fn()(self.api_key, self.model, msgs, "off"):
                t = ev.get("type")
                if t == "text" and ev.get("content"):
                    yield ev["content"]
                elif t == "error":
                    raise RuntimeError(str(ev.get("content") or "lỗi provider"))


class AntigravityVoiceBrain(VoiceBrain):
    """Một tiến trình `agy` sống lâu, nhận từng lượt qua stdin NDJSON.

    Khuôn stdin dò ra 2026-09-14 (không có trong help): `{"event":"user","message":{"role":
    "user","content":"..."}}`. Tên sự kiện khác bị bỏ qua, `message` là chuỗi thì tiến trình
    THOÁT. Sự kiện ra: `init`, `step_update` (text_delta khi step_type=agent_response),
    `result` (status SUCCESS|ERROR, response, error).

    `agy` không có cờ system prompt, nên hướng dẫn được ghép vào ĐẦU lượt đầu tiên của mỗi
    tiến trình, kèm mấy lượt gần nhất từ kho phiên để mạch không đứt khi tiến trình mở lại.
    """
    provider = "antigravity"

    def __init__(self, model: str = "", cli_path: str = "", spawn: Optional[Callable] = None):
        super().__init__()
        self.model = model
        self.cli_path = cli_path
        self._spawn = spawn          # test tiêm tiến trình giả
        self.proc = None
        self._seeded = False
        self.turns = 0

    def _args(self) -> List[str]:
        args = [self.cli_path]
        if self.model:
            args += ["--model", self.model]
        args += ["--input-format", "stream-json", "--output-format", "stream-json"]
        return args

    async def _ensure(self):
        if self.proc is not None and self.proc.returncode is None:
            return
        if not self.cli_path and not self._spawn:
            raise RuntimeError("Chưa cài Antigravity CLI (agy).")
        if self._spawn:
            self.proc = await self._spawn(self._args())
        else:
            self.proc = await asyncio.create_subprocess_exec(
                *self._args(), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, **winproc.kwargs_no_window())
        self._seeded = False
        self.turns = 0

    def _seed_text(self, history: List[dict], text: str) -> str:
        return seed_text(history, text, with_prompt=True)

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        async with self._lock:
            await self._ensure()
            content = text if self._seeded else self._seed_text(history, text)
            self._seeded = True
            self.turns += 1
            line = json.dumps({"event": "user", "message": {"role": "user", "content": content}},
                              ensure_ascii=False) + "\n"
            self.proc.stdin.write(line.encode("utf-8"))
            await self.proc.stdin.drain()
            got_delta = False
            deadline = time.time() + TURN_TIMEOUT_S
            while True:
                left = deadline - time.time()
                if left <= 0:
                    await self.close()
                    raise RuntimeError("Antigravity không trả lời trong 90 giây.")
                try:
                    raw = await asyncio.wait_for(self.proc.stdout.readline(), timeout=left)
                except asyncio.TimeoutError:
                    await self.close()
                    raise RuntimeError("Antigravity không trả lời trong 90 giây.")
                if not raw:
                    await self.close()
                    raise RuntimeError("Antigravity đóng tiến trình giữa chừng.")
                try:
                    ev = json.loads(raw.decode("utf-8", "ignore"))
                except Exception:
                    continue
                kind = ev.get("event")
                if kind == "step_update":
                    su = ev.get("step_update") or {}
                    if su.get("step_type") == "agent_response" and su.get("text_delta"):
                        got_delta = True
                        yield str(su["text_delta"])
                elif kind == "result":
                    r = ev.get("result") or {}
                    if r.get("status") != "SUCCESS":
                        raise RuntimeError(str(r.get("error") or "Antigravity báo lỗi."))
                    if not got_delta and r.get("response"):
                        yield str(r["response"])
                    return

    async def close(self) -> None:
        p, self.proc = self.proc, None
        self._seeded = False
        if p is None:
            return
        try:
            if p.stdin:
                p.stdin.close()
        except Exception:
            pass
        try:
            if p.returncode is None:
                p.kill()
        except Exception:
            pass
        # Đợi tiến trình khép hẳn để transport asyncio đóng pipe ngay bây giờ, không phải lúc
        # event loop đã đóng (khi đó Windows ném "I/O operation on closed pipe" ra stderr).
        try:
            await asyncio.wait_for(p.wait(), timeout=3.0)
        except Exception:
            pass


# ============================================================
# Ba bộ não trên GÓI đã đăng nhập (Voice V3, spec mục 13)
# ============================================================
def _codex_creds():
    import openai_oauth
    return openai_oauth.valid_creds()


def codex_default_model() -> str:
    """Model Codex mặc định = đầu catalog 'openai-oauth' đã lấy live (main._codex_safe_model
    cũng làm vậy). Rỗng thì engine tự chọn mặc định của nó."""
    try:
        import config as cfgmod
        cat = (cfgmod.read_settings().get("model", {}).get("catalog", {}).get("openai-oauth")) or []
        return str(cat[0]) if cat else ""
    except Exception:
        return ""


class CodexVoiceBrain(VoiceBrain):
    """ChatGPT trên gói đã đăng nhập (OAuth), qua backend Codex Responses API: một HTTP stream
    mỗi lượt, không dựng tiến trình nào, nên đây là đường gói nhanh nhất. Cùng hàm
    `engine.openai_responses_stream` mà bộ não chính dùng; ở đây chỉ khác system prompt ngắn."""
    provider = "codex"

    def __init__(self, model: str = "", creds_fn: Optional[Callable] = None, stream_fn: Optional[Callable] = None):
        super().__init__()
        self.model = model
        self._creds_fn = creds_fn
        self._stream_fn = stream_fn

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        creds = (self._creds_fn or _codex_creds)() or {}
        if not creds.get("access_token"):
            raise RuntimeError("Chưa kết nối ChatGPT (OAuth) ở trang Models.")
        if self._stream_fn:
            fn = self._stream_fn
        else:
            import engine
            fn = engine.openai_responses_stream
        msgs = build_messages(history, text)
        async with self._lock:
            async for ev in fn(creds.get("access_token", ""), creds.get("account_id", ""),
                               self.model or codex_default_model(), msgs, "off"):
                t = ev.get("type")
                if t == "text" and ev.get("content"):
                    yield ev["content"]
                elif t == "limit_exceeded":
                    raise RuntimeError("ChatGPT hết hạn mức gói cho lượt này.")
                elif t == "error":
                    raise RuntimeError(str(ev.get("content") or "lỗi ChatGPT"))


def claude_pieces(msg):
    """Đổi một message của claude-agent-sdk thành [(loại, dữ liệu)]: ('delta', chữ) từ StreamEvent
    (include_partial_messages), ('text', chữ) từ AssistantMessage, ('result', msg) từ ResultMessage.
    Nhận diện bằng TÊN LỚP để test tiêm message giả không cần SDK."""
    name = type(msg).__name__
    out = []
    if name == "StreamEvent":
        ev = getattr(msg, "event", None) or {}
        if isinstance(ev, dict) and ev.get("type") == "content_block_delta":
            d = ev.get("delta") or {}
            if d.get("type") == "text_delta" and d.get("text"):
                out.append(("delta", str(d["text"])))
    elif name == "AssistantMessage":
        for b in (getattr(msg, "content", None) or []):
            if type(b).__name__ == "TextBlock" and (getattr(b, "text", "") or "").strip():
                out.append(("text", str(b.text)))
    elif name == "ResultMessage":
        out.append(("result", msg))
    return out


class ClaudeVoiceBrain(VoiceBrain):
    """Claude Code trên gói Claude: MỘT ClaudeSDKClient sống suốt phiên nói (như tiến trình agy),
    không tool, không MCP, không nạp settings hay CLAUDE.md, system prompt trần vài trăm token,
    nên lượt sau chỉ còn độ trễ của model. Mạch giữ trong client nên có ký ức giữa các lượt."""
    provider = "claude"

    def __init__(self, model: str = "", client_factory: Optional[Callable] = None):
        super().__init__()
        self.model = model
        self._factory = client_factory      # test tiêm client giả (async () -> client)
        self.client = None
        self._seeded = False
        self.turns = 0

    def _options(self):
        import tempfile
        from claude_agent_sdk import ClaudeAgentOptions
        fields = getattr(ClaudeAgentOptions, "__dataclass_fields__", {})
        kw = {"system_prompt": SYSTEM_PROMPT, "cwd": tempfile.gettempdir(),
              "permission_mode": "bypassPermissions"}
        if "tools" in fields:
            kw["tools"] = []                        # không tool builtin: bộ não giọng chỉ nói
        if "max_turns" in fields:
            kw["max_turns"] = 1
        if "setting_sources" in fields:
            kw["setting_sources"] = []              # không CLAUDE.md, không MCP máy: khởi động nhanh
        if "include_partial_messages" in fields:
            kw["include_partial_messages"] = True   # stream từng mảnh chữ cho loa
        if self.model and "model" in fields:
            kw["model"] = self.model
        try:
            import claude_cli
            _cli = (os.environ.get("JAVIS_CLAUDE_CLI") or "").strip() or (claude_cli.tim_binary("claude") or "")
            if _cli and "_bundled" not in _cli.replace("\\", "/") and "cli_path" in fields:
                kw["cli_path"] = _cli
        except Exception:
            pass
        try:
            import claude_auth
            _env = claude_auth.env_cho_cli()
            if _env and "env" in fields:
                kw["env"] = {**os.environ, **_env}
        except Exception:
            pass
        return ClaudeAgentOptions(**kw)

    async def _ensure(self):
        if self.client is not None:
            return
        if self._factory:
            self.client = await self._factory()
        else:
            import claude_cli
            import claude_sdk_engine
            if not claude_sdk_engine.sdk_available() or not claude_cli.find_claude_cli():
                raise RuntimeError("Chưa cài hoặc chưa đăng nhập Claude Code (claude).")
            from claude_agent_sdk import ClaudeSDKClient
            try:
                import claude_token_gate
                await claude_token_gate.xep_hang()
            except Exception:
                pass
            self.client = ClaudeSDKClient(options=self._options())
            await self.client.connect()
        self._seeded = False
        self.turns = 0

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        async with self._lock:
            await self._ensure()
            # System prompt đã đi bằng tuỳ chọn SDK nên lượt đầu chỉ mồi lịch sử.
            content = text if self._seeded else seed_text(history, text, with_prompt=False)
            self._seeded = True
            self.turns += 1
            got_delta = False
            deadline = time.time() + TURN_TIMEOUT_S
            try:
                await self.client.query(content)
                agen = self.client.receive_response().__aiter__()
                while True:
                    left = deadline - time.time()
                    if left <= 0:
                        raise asyncio.TimeoutError()
                    try:
                        msg = await asyncio.wait_for(agen.__anext__(), timeout=left)
                    except StopAsyncIteration:
                        return
                    for kind, data in claude_pieces(msg):
                        if kind == "delta":
                            got_delta = True
                            yield data
                        elif kind == "text":
                            if not got_delta:
                                yield data
                        elif kind == "result":
                            if getattr(data, "is_error", False):
                                raise RuntimeError(str(getattr(data, "result", "") or "Claude báo lỗi."))
                            return
            except asyncio.TimeoutError:
                await self.close()
                raise RuntimeError("Claude không trả lời trong 90 giây.")
            except RuntimeError:
                raise
            except Exception as e:
                await self.close()          # client hỏng: lần sau mở lại và mồi lại
                raise RuntimeError(f"Claude: {type(e).__name__}: {e}")

    async def close(self) -> None:
        c, self.client = self.client, None
        self._seeded = False
        if c is None:
            return
        try:
            await asyncio.wait_for(c.disconnect(), timeout=5.0)
        except Exception:
            pass


class GrokVoiceBrain(VoiceBrain):
    """Grok Build trên gói SuperGrok / X Premium+: một lượt `grok` headless mỗi câu, giữ cùng một
    GrokCLI để `--resume` mạch cũ (có ký ức). CLI gom chữ rồi trả `final` một cục nên không stream
    từng mảnh, nhưng câu trả lời giọng ngắn nên chấp nhận được."""
    provider = "grok"

    def __init__(self, model: str = "", cli_factory: Optional[Callable] = None):
        super().__init__()
        self.model = model
        self._factory = cli_factory
        self.cli = None

    def _ensure(self):
        if self.cli is not None:
            return
        if self._factory:
            self.cli = self._factory()
        else:
            import grok_cli
            if not grok_cli.find_grok_cli():
                raise RuntimeError("Chưa cài Grok Build (grok). Cài rồi đăng nhập ở trang Models.")
            import tempfile
            self.cli = grok_cli.GrokCLI(cwd=tempfile.gettempdir(), tag="voice", model=self.model or None,
                                        instructions=SYSTEM_PROMPT)
            self.cli.mode = "suggest"
            self.cli.max_turns = 1
            self.cli.timeout = TURN_TIMEOUT_S

    async def stream(self, text: str, history: List[dict]) -> AsyncIterator[str]:
        self.last_used = time.time()
        async with self._lock:
            self._ensure()
            content = text if getattr(self.cli, "session_id", None) else seed_text(history, text, with_prompt=False)
            got = False
            async for ev in self.cli.query(content):
                t = ev.get("type")
                if t == "text" and ev.get("content"):
                    got = True
                    yield ev["content"]
                elif t == "final":
                    if not got and ev.get("content"):
                        yield str(ev["content"])
                elif t == "error":
                    raise RuntimeError(str(ev.get("content") or "Grok báo lỗi."))

    async def close(self) -> None:
        self.cli = None


# ============================================================
# Việc nền đang chạy của mỗi phiên nói (Voice V3, spec mục 14: tách NÓI khỏi LÀM)
# ============================================================
# Khi bộ não giọng phát JAVIS_ASK_MAIN, main.py giao yêu cầu đó cho bộ não chính chạy NỀN rồi
# kết thúc lượt giọng ngay, để người dùng nói tiếp được. Sổ này cho bộ não giọng biết còn việc
# gì đang chạy, để nó trả lời "đang chạy" thay vì bịa kết quả hay giao lại việc cũ.
_PENDING: Dict[str, List[dict]] = {}
PENDING_MAX_NOTE = 6


def note_task_start(session_id: str, request: str) -> int:
    lst = _PENDING.setdefault(str(session_id or "default"), [])
    lst.append({"request": str(request or "")[:300], "at": time.time()})
    return len(lst)


def note_task_done(session_id: str, request: str) -> None:
    lst = _PENDING.get(str(session_id or "default")) or []
    for i, it in enumerate(lst):
        if it["request"] == str(request or "")[:300]:
            lst.pop(i)
            break
    if not lst:
        _PENDING.pop(str(session_id or "default"), None)


def pending_tasks(session_id: str) -> List[dict]:
    return list(_PENDING.get(str(session_id or "default")) or [])


def pending_note(session_id: str, now: Optional[float] = None) -> str:
    """Dòng ghi chú ghép vào cuối câu người dùng gửi bộ não giọng; rỗng khi không có việc nền."""
    lst = pending_tasks(session_id)
    if not lst:
        return ""
    now = now or time.time()
    dong = []
    for it in lst[-PENDING_MAX_NOTE:]:
        giay = int(max(0, now - it["at"]))
        dong.append(f"- {it['request']} (giao {giay} giây trước)")
    return ("[GHI CHÚ HỆ THỐNG: đang có việc chạy nền, kết quả sẽ TỰ hiện trong khung chat khi xong; "
            "đừng bịa kết quả, đừng giao lại việc trùng:\n" + "\n".join(dong) + "]")


# ============================================================
# Sổ phiên
# ============================================================
_BRAINS: Dict[str, VoiceBrain] = {}
_REAPER: Optional[asyncio.Task] = None


def config_from_settings(cfg: dict) -> dict:
    v = (cfg or {}).get("voice") or {}
    m = (cfg or {}).get("model") or {}
    prov = str(v.get("brain_provider") or "").strip().lower()
    kf = (BRAIN_PROVIDERS.get(prov) or {}).get("key_field") or ""
    return {"mode": str(v.get("mode") or "standard"), "provider": prov,
            "model": str(v.get("brain_model") or "").strip(),
            "api_key": str(m.get(kf, "")) if kf else ""}


def _make(conf: dict) -> VoiceBrain:
    prov = conf.get("provider") or ""
    if prov == "antigravity":
        try:
            import antigravity_cli
            cli = antigravity_cli.find_antigravity_cli() or ""
        except Exception:
            cli = ""
        return AntigravityVoiceBrain(model=conf.get("model") or "", cli_path=cli)
    if prov == "codex":
        return CodexVoiceBrain(model=conf.get("model") or "")
    if prov == "claude":
        return ClaudeVoiceBrain(model=conf.get("model") or BRAIN_PROVIDERS["claude"]["default_model"])
    if prov == "grok":
        return GrokVoiceBrain(model=conf.get("model") or "")
    if prov in PROVIDERS:
        if not conf.get("api_key"):
            raise RuntimeError(f"Bộ não giọng nói {prov} chưa có API key ở trang Models.")
        return ApiVoiceBrain(prov, conf["api_key"], conf.get("model") or BRAIN_PROVIDERS[prov]["default_model"])
    raise RuntimeError("Chưa chọn bộ não giọng nói.")


async def get_brain(session_id: str, conf: dict) -> VoiceBrain:
    """Bộ não cho phiên này; đổi provider/model trong cài đặt thì dựng lại."""
    key = str(session_id or "default")
    b = _BRAINS.get(key)
    want = (conf.get("provider") or "", conf.get("model") or "")
    if b is not None and (b.provider, b.model) != want:
        await b.close()
        b = None
    if b is None:
        b = _make(conf)
        _BRAINS[key] = b
    _start_reaper()
    return b


def _start_reaper():
    global _REAPER
    if _REAPER is not None and not _REAPER.done():
        return
    try:
        _REAPER = asyncio.get_running_loop().create_task(_reap())
    except RuntimeError:
        pass


async def _reap():
    while True:
        await asyncio.sleep(30)
        now = time.time()
        for k, b in list(_BRAINS.items()):
            if now - b.last_used > IDLE_S:
                _BRAINS.pop(k, None)
                try:
                    await b.close()
                except Exception:
                    pass
        if not _BRAINS:
            return


async def close_all():
    for k, b in list(_BRAINS.items()):
        _BRAINS.pop(k, None)
        try:
            await b.close()
        except Exception:
            pass


def active_count() -> int:
    return len(_BRAINS)
