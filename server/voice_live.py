"""Nhà cung cấp NGHE NÓI THẲNG (Voice V2 bậc Live, docs/dev/2026-09-voice-v2-spec.md mục 4).

Trình duyệt đẩy PCM16 mono 16 kHz lên `/ws/voice-live` (main.py); route đó cầm một
`LiveProvider` ở đây, chuyển audio sang nhà cung cấp và trả sự kiện chuẩn hoá về:

    {"type":"audio","data":bytes}            PCM16 mono 24 kHz
    {"type":"interrupted"}                    người dùng chen ngang, xả hàng đợi phát
    {"type":"transcript","role":"user"|"assistant","text":str,"final":bool}
    {"type":"tool_call","id":str,"name":str,"args":dict}
    {"type":"turn_done"}
    {"type":"goaway"}                         nhà cung cấp sắp đóng kết nối, route nối lại
    {"type":"error","message":str}

Ba nhà cung cấp:
- GeminiLive (BidiGenerateContent v1beta): theo lượt; tool bất đồng bộ (`behavior NON_BLOCKING` +
  `scheduling WHEN_IDLE`) CHỈ trên dòng 2.5 Flash Live, dòng 3.1 chưa hỗ trợ nên model im chờ tool.
  Có session resumption + GoAway để nối lại trong suốt (kết nối WS của Google sống ~10 phút).
- OpenAIRealtime (API GA 2025-08: `session.type = realtime`, khối `audio.input/output`, KHÔNG
  header OpenAI-Beta; dịch cả tên cũ `response.audio.*` lẫn tên mới `response.output_audio.*`).
  Kết quả tool về khi model đang nói thì `response.create` được XẾP HÀNG tới `response.done`
  (gửi ngay là lỗi "already has active response"). Ngắt lời thì cắt ngữ cảnh đúng chỗ đã nghe
  bằng `conversation.item.truncate` (trình duyệt báo số ms đã phát).
- GPTLive (`wss://api.openai.com/v1/live/sessions`, 09/2026): song công toàn phần, model tự
  quyết ngắt lời, KHÔNG có sự kiện interrupted / turn_done; ủy nhiệm kiểu `client`: model phát
  `session.delegation.created`, Javis chạy bộ não chính rồi trả kết quả bằng
  `session.commentary.append` (model tự thuật lại), tiến độ bằng `session.thinking.append`.
  Khuôn sự kiện lấy từ SDK openai 3.13 (`openai/types/live/*`). CHƯA chạy thật.

Thêm nhà cung cấp mới = thêm một lớp con, route và trình duyệt không đổi. Tên model để trong
cài đặt vì các hãng đổi tên liên tục; mặc định ở PROVIDERS chỉ là gợi ý lúc viết.

Mọi hàm dựng/dịch thông điệp (`setup_message`, `translate`, ...) là hàm THUẦN để test không cần
mạng; trạng thái nhỏ (response đang chạy, handle nối lại) nằm trên instance và cũng test được.
Chuyển mẫu 16 kHz -> 24 kHz cho OpenAI (chỉ nhận 24 kHz) làm bằng nội suy tuyến tính, đủ tốt
cho giọng nói và không cần numpy.
"""
from __future__ import annotations

import array
import asyncio
import base64
import json
import re
from typing import Any, AsyncIterator, Dict, List, Optional

_OPENAI_VOICES = ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]

PROVIDERS = {
    "gemini": {"label": "Google Gemini Live (API)", "key_field": "gemini_api_key",
               "default_model": "gemini-3.1-flash-live-preview",   # 03/2026; bản cũ: gemini-2.5-flash-native-audio-preview-12-2025
               "default_voice": "Aoede", "voices": ["Aoede", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Zephyr"]},
    "openai": {"label": "OpenAI Realtime (API)", "key_field": "openai_api_key",
               "default_model": "gpt-realtime", "default_voice": "marin", "voices": _OPENAI_VOICES},
    "gpt-live": {"label": "OpenAI GPT-Live (API, song công)", "key_field": "openai_api_key",
                 "default_model": "gpt-live-1", "default_voice": "marin", "voices": _OPENAI_VOICES},
}

ASK_JAVIS_TOOL = {
    "name": "ask_javis",
    "description": ("Hỏi bộ não chính của Javis khi cần dữ liệu thật (số liệu kinh doanh, lịch, email, file, "
                    "ghi chú, ký ức), giao việc, nhắc hẹn, mở trang hay app, hoặc bất cứ hành động nào ra "
                    "ngoài. Truyền yêu cầu đầy đủ bằng ngôn ngữ người dùng. Trong lúc chờ hãy nói một câu "
                    "ngắn như 'để mình xem'. Kết quả trả về là chữ, hãy thuật lại ngắn gọn."),
    "parameters": {"type": "object", "properties": {"request": {"type": "string"}}, "required": ["request"]},
}

SYSTEM_PROMPT = (
    "Bạn là Javis, trợ lý cá nhân, đang nói chuyện trực tiếp bằng giọng. "
    "Nói ngắn, tự nhiên. Không bịa dữ liệu: cần dữ liệu "
    "thật hay hành động thì gọi tool ask_javis "
    "rồi thuật lại kết quả. Đang được ngắt lời thì dừng ngay và nghe."
)

# GPT-Live không có tool: nó ỦY NHIỆM. Prompt hội thoại ngắn, nói rõ khi nào giao việc.
GPT_LIVE_PROMPT = (
    "Bạn là Javis, trợ lý cá nhân, đang nói chuyện bằng giọng. Nói ngắn và "
    "tự nhiên. Chuyện phiếm, hỏi đáp thường thì trả lời ngay. Câu nào cần dữ liệu thật (số liệu "
    "kinh doanh, lịch, email, file, ghi chú, ký ức), cần làm việc, nhắc hẹn, mở trang hay app, hay "
    "bất cứ hành động nào ra ngoài thì GIAO cho bộ não chính (delegate), nói một câu ngắn như 'để "
    "mình xem' và tiếp tục trò chuyện; kết quả về thì thuật lại ngắn gọn. Không bịa dữ liệu."
)

# GPT-Live giới hạn mỗi lần append 500 token; giữ kết quả bộ não chính trong khoảng đó.
GPT_LIVE_APPEND_MAX = 1400


def _recognition_language(value: str) -> str:
    value = str(value or "vi-VN").strip()
    if value.lower() == "auto":
        return "auto"
    # Only a locale token may enter the system prompt and provider payload.
    return value if re.fullmatch(r"[A-Za-z]{2}(?:-[A-Za-z0-9]{2,8})*", value) else "vi-VN"


def _language_instruction(language: str) -> str:
    # Native Gemini audio uses system instructions for language, not speechConfig.languageCode:
    # https://ai.google.dev/gemini-api/docs/live-api/best-practices#specify-language
    if language == "auto":
        policy = "Detect the user's spoken language and reply in that language."
    else:
        policy = (f"The user selected recognition language {language}. Listen and reply in {language}; "
                  "switch only when the user clearly speaks another language or explicitly requests it.")
    return policy + " If audio is unclear, ask for repetition in the current language; do not infer a language switch from noise."


def resample_16k_to_24k(pcm16: bytes) -> bytes:
    """PCM16 mono 16 kHz -> 24 kHz (tỉ lệ 2:3) bằng nội suy tuyến tính."""
    src = array.array("h")
    src.frombytes(pcm16[: len(pcm16) - (len(pcm16) % 2)])
    n = len(src)
    if n == 0:
        return b""
    out = array.array("h")
    m = (n * 3) // 2
    for i in range(m):
        pos = i * 2 / 3
        j = int(pos)
        frac = pos - j
        a = src[j]
        b = src[j + 1] if j + 1 < n else a
        out.append(int(a + (b - a) * frac))
    return out.tobytes()


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


class LiveProvider:
    name = ""

    def __init__(self, api_key: str, model: str = "", voice: str = "", system: str = SYSTEM_PROMPT,
                 tools: Optional[List[dict]] = None, recognition_lang: str = "vi-VN"):
        self.api_key = api_key
        self.model = model or PROVIDERS[self.name]["default_model"]
        self.voice = voice or PROVIDERS[self.name]["default_voice"]
        self.recognition_lang = _recognition_language(recognition_lang)
        self.system = system + "\n\n" + _language_instruction(self.recognition_lang)
        self.tools = tools if tools is not None else [ASK_JAVIS_TOOL]
        self.ws = None
        self.wants_reconnect = False   # nhà cung cấp báo sắp đóng: route gọi reconnect()

    # ---- hàm thuần dựng thông điệp (test được) ----
    def url(self) -> str:  # pragma: no cover
        raise NotImplementedError

    def headers(self) -> List[tuple]:
        return []

    def setup_message(self) -> dict:  # pragma: no cover
        raise NotImplementedError

    def audio_message(self, pcm16_16k: bytes) -> dict:  # pragma: no cover
        raise NotImplementedError

    def text_message(self, text: str) -> dict:  # pragma: no cover
        raise NotImplementedError

    def tool_result_messages(self, call_id: str, name: str, result: str) -> List[dict]:  # pragma: no cover
        raise NotImplementedError

    def tool_running_messages(self, call_id: str, name: str) -> List[dict]:
        """Báo cho model biết việc đang chạy (chỉ nhà cung cấp nào có kênh cho việc đó)."""
        return []

    def context_messages(self, text: str) -> List[dict]:
        """Ngữ cảnh giao diện (trang đang mở, đoạn bôi đen) vào phiên, nếu nhà cung cấp có kênh im lặng."""
        return []

    def truncate_messages(self, played_ms: int) -> List[dict]:
        """Bị ngắt lời sau khi đã phát `played_ms`: cắt ngữ cảnh đúng chỗ đã nghe (nếu hãng cần)."""
        return []

    def after_translate_messages(self) -> List[dict]:
        """Thông điệp phải gửi ngay sau khi dịch xong một khung server (vd response.create đã xếp hàng)."""
        return []

    def interrupt_messages(self) -> List[dict]:
        return []

    def close_messages(self) -> List[dict]:
        return []

    def supports_async_tools(self) -> bool:
        """Model có tiếp tục nói trong lúc chờ kết quả tool không."""
        return False

    def translate(self, msg: dict) -> List[dict]:  # pragma: no cover
        raise NotImplementedError

    # ---- mạng ----
    async def connect(self):
        import websockets
        self.wants_reconnect = False
        self.ws = await websockets.connect(self.url(), extra_headers=self.headers(), max_size=16 * 1024 * 1024)
        await self._send(self.setup_message())

    async def reconnect(self):
        await self.close()
        await self.connect()

    async def _send(self, obj: dict):
        if self.ws is not None:
            await self.ws.send(json.dumps(obj))

    async def _send_all(self, msgs: List[dict]):
        for m in msgs:
            await self._send(m)

    async def send_audio(self, pcm16_16k: bytes):
        await self._send(self.audio_message(pcm16_16k))

    async def send_text(self, text: str):
        await self._send(self.text_message(text))

    async def send_tool_running(self, call_id: str, name: str):
        await self._send_all(self.tool_running_messages(call_id, name))

    async def send_tool_result(self, call_id: str, name: str, result: str):
        await self._send_all(self.tool_result_messages(call_id, name, result))

    async def send_context(self, text: str):
        await self._send_all(self.context_messages(text))

    async def truncate_played(self, played_ms: int):
        await self._send_all(self.truncate_messages(int(played_ms)))

    async def interrupt(self):
        await self._send_all(self.interrupt_messages())

    async def events(self) -> AsyncIterator[dict]:
        if self.ws is None:
            return
        async for raw in self.ws:
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8")
                except Exception:
                    continue
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            for ev in self.translate(msg):
                yield ev
            after = self.after_translate_messages()
            if after:
                await self._send_all(after)

    async def close(self):
        ws, self.ws = self.ws, None
        if ws is not None:
            try:
                for m in self.close_messages():
                    await asyncio.wait_for(ws.send(json.dumps(m)), 2)
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass


class GeminiLive(LiveProvider):
    name = "gemini"
    SETUP_TIMEOUT = 10

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.resume_handle = ""   # từ sessionResumptionUpdate, dùng khi nối lại
        self._setup_ready = asyncio.Event()
        self._initial_events: List[dict] = []

    async def connect(self):
        # BidiGenerateContentSetup requires setupComplete before any further client input.
        # https://ai.google.dev/api/live#bidigeneratecontentsetup
        self._setup_ready.clear()
        self._initial_events = []
        try:
            await super().connect()
            await asyncio.wait_for(self._wait_for_setup(), self.SETUP_TIMEOUT)
            self._setup_ready.set()
        except BaseException:
            await self.close()
            raise

    async def _wait_for_setup(self):
        while self.ws is not None:
            raw = await self.ws.recv()
            try:
                msg = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                continue
            if not isinstance(msg, dict):
                continue
            if "error" in msg:
                raise RuntimeError("Gemini Live rejected session setup.")
            self._initial_events.extend(self.translate(msg))
            if "setupComplete" in msg:
                return
        raise RuntimeError("Gemini Live closed before session setup completed.")

    async def _send(self, obj: dict):
        socket = self.ws
        if socket is None:
            return
        if "setup" not in obj:
            await self._setup_ready.wait()
            if self.ws is not socket:
                return
        await super()._send(obj)

    async def events(self) -> AsyncIterator[dict]:
        initial, self._initial_events = self._initial_events, []
        for event in initial:
            yield event
        async for event in super().events():
            yield event

    async def close(self):
        try:
            await super().close()
        finally:
            self._initial_events = []
            self._setup_ready.set()  # Release senders when setup fails or the connection closes.

    def url(self) -> str:
        return ("wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta."
                f"GenerativeService.BidiGenerateContent?key={self.api_key}")

    def supports_async_tools(self) -> bool:
        # Tài liệu Google (09/2026): "Asynchronous function calling is not yet supported in
        # Gemini 3.1 Flash Live", chỉ 2.5 Flash Live nhận behavior NON_BLOCKING.
        return "2.5" in self.model

    def setup_message(self) -> dict:
        model = self.model if self.model.startswith("models/") else f"models/{self.model}"
        setup: Dict[str, Any] = {
            "model": model,
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": self.voice}}},
            },
            "systemInstruction": {"parts": [{"text": self.system}]},
            "inputAudioTranscription": {},
            "outputAudioTranscription": {},
            # Nối lại trong suốt khi Google đóng WS (~10 phút) và nén ngữ cảnh để nói lâu hơn 15 phút.
            "sessionResumption": ({"handle": self.resume_handle} if self.resume_handle else {}),
            "contextWindowCompression": {"slidingWindow": {}},
        }
        if self.tools:
            decls = []
            for t in self.tools:
                d = dict(t)
                if self.supports_async_tools():
                    d["behavior"] = "NON_BLOCKING"
                decls.append(d)
            setup["tools"] = [{"functionDeclarations": decls}]
        return {"setup": setup}

    def audio_message(self, pcm16_16k: bytes) -> dict:
        return {"realtimeInput": {"audio": {"mimeType": "audio/pcm;rate=16000", "data": _b64(pcm16_16k)}}}

    def text_message(self, text: str) -> dict:
        return {"clientContent": {"turns": [{"role": "user", "parts": [{"text": text}]}], "turnComplete": True}}

    def tool_result_messages(self, call_id: str, name: str, result: str) -> List[dict]:
        resp: Dict[str, Any] = {"output": result}
        if self.supports_async_tools():
            # WHEN_IDLE: nói xong câu đang nói rồi mới thuật kết quả, không cắt ngang chính mình.
            resp["scheduling"] = "WHEN_IDLE"
        return [{"toolResponse": {"functionResponses": [{"id": call_id, "name": name, "response": resp}]}}]

    def translate(self, msg: dict) -> List[dict]:
        out: List[dict] = []
        if "setupComplete" in msg:
            return [{"type": "ready"}]
        sru = msg.get("sessionResumptionUpdate")
        if isinstance(sru, dict):
            if sru.get("resumable") and sru.get("newHandle"):
                self.resume_handle = str(sru["newHandle"])
            return out
        if "goAway" in msg:
            self.wants_reconnect = True
            tl = (msg.get("goAway") or {}).get("timeLeft")
            return [{"type": "goaway", "time_left": str(tl or "")}]
        sc = msg.get("serverContent")
        if isinstance(sc, dict):
            if sc.get("interrupted"):
                out.append({"type": "interrupted"})
            mt = sc.get("modelTurn") or {}
            for part in mt.get("parts") or []:
                inl = part.get("inlineData") or {}
                if inl.get("data"):
                    try:
                        out.append({"type": "audio", "data": base64.b64decode(inl["data"])})
                    except Exception:
                        pass
                # Chữ trong modelTurn KHÔNG phát: setup đã bật outputAudioTranscription nên chữ
                # trợ lý đi qua outputTranscription; phát cả hai là khung chat hiện đúp.
            it = sc.get("inputTranscription") or {}
            interim = sc.get("interimInputTranscription") or {}
            if interim.get("text") and not it.get("text"):
                out.append({"type": "transcript", "role": "user", "text": str(interim["text"]), "final": False})
            if it.get("text"):
                # Input transcripts have no documented finished flag or ordering relative to
                # model turnComplete. Commit each received segment independently so a late
                # transcript cannot be stranded or joined to the next user turn. `final` is
                # our persistence marker, not a claim that this is a complete utterance.
                # Legacy models streaming short segments may therefore create short bubbles.
                out.append({"type": "transcript", "role": "user", "text": str(it["text"]), "final": True})
            ot = sc.get("outputTranscription") or {}
            if ot.get("text"):
                out.append({"type": "transcript", "role": "assistant", "text": ot["text"], "final": False})
            if sc.get("turnComplete"):
                out.append({"type": "turn_done"})
        tc = msg.get("toolCall")
        if isinstance(tc, dict):
            for fc in tc.get("functionCalls") or []:
                out.append({"type": "tool_call", "id": str(fc.get("id") or ""), "name": str(fc.get("name") or ""),
                            "args": fc.get("args") or {}})
        if "error" in msg:
            out.append({"type": "error", "message": str(msg.get("error"))})
        return out


class OpenAIRealtime(LiveProvider):
    name = "openai"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.response_active = False   # giữa response.created và response.done
        self._pending_create = False   # kết quả tool về lúc đang nói: đợi response.done rồi mới response.create
        self.last_audio_item = ""      # item_id của audio trợ lý gần nhất, để truncate khi bị ngắt

    def url(self) -> str:
        return f"wss://api.openai.com/v1/realtime?model={self.model}"

    def headers(self) -> List[tuple]:
        # API GA không cần header OpenAI-Beta; gửi kèm là rơi về khuôn beta cũ và session.type bị từ chối.
        return [("Authorization", f"Bearer {self.api_key}")]

    def supports_async_tools(self) -> bool:
        return True

    def setup_message(self) -> dict:
        tools = [{"type": "function", "name": t["name"], "description": t.get("description", ""),
                  "parameters": t.get("parameters", {"type": "object", "properties": {}})} for t in self.tools]
        pcm24 = {"type": "audio/pcm", "rate": 24000}
        transcription = {"model": "gpt-4o-mini-transcribe"}
        # Realtime audio.input.transcription.language accepts ISO-639-1, not BCP-47 locales.
        if self.recognition_lang != "auto":
            transcription["language"] = self.recognition_lang.split("-")[0].lower()
        return {"type": "session.update", "session": {
            "type": "realtime", "output_modalities": ["audio"], "instructions": self.system,
            "audio": {
                "input": {"format": pcm24, "transcription": transcription,
                          "turn_detection": {"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300,
                                             "silence_duration_ms": 500}},
                "output": {"format": pcm24, "voice": self.voice},
            },
            "tools": tools, "tool_choice": "auto",
        }}

    def audio_message(self, pcm16_16k: bytes) -> dict:
        return {"type": "input_audio_buffer.append", "audio": _b64(resample_16k_to_24k(pcm16_16k))}

    def text_message(self, text: str) -> dict:
        return {"type": "conversation.item.create", "item": {"type": "message", "role": "user",
                                                             "content": [{"type": "input_text", "text": text}]}}

    def tool_result_messages(self, call_id: str, name: str, result: str) -> List[dict]:
        msgs = [{"type": "conversation.item.create",
                 "item": {"type": "function_call_output", "call_id": call_id, "output": result}}]
        if self.response_active:
            self._pending_create = True   # gửi response.create lúc này là lỗi; đợi response.done
        else:
            msgs.append({"type": "response.create"})
        return msgs

    def after_translate_messages(self) -> List[dict]:
        if self._pending_create and not self.response_active:
            self._pending_create = False
            return [{"type": "response.create"}]
        return []

    def truncate_messages(self, played_ms: int) -> List[dict]:
        if not self.last_audio_item or played_ms < 0:
            return []
        return [{"type": "conversation.item.truncate", "item_id": self.last_audio_item,
                 "content_index": 0, "audio_end_ms": int(played_ms)}]

    def interrupt_messages(self) -> List[dict]:
        return [{"type": "response.cancel"}]

    def translate(self, msg: dict) -> List[dict]:
        t = str(msg.get("type") or "")
        if t in ("session.created", "session.updated"):
            return [{"type": "ready"}]
        if t == "response.created":
            self.response_active = True
            return []
        if t in ("response.output_audio.delta", "response.audio.delta") and msg.get("delta"):
            if msg.get("item_id"):
                self.last_audio_item = str(msg["item_id"])
            try:
                return [{"type": "audio", "data": base64.b64decode(msg["delta"])}]
            except Exception:
                return []
        if t == "input_audio_buffer.speech_started":
            return [{"type": "interrupted"}]
        if t == "conversation.item.input_audio_transcription.completed":
            return [{"type": "transcript", "role": "user", "text": str(msg.get("transcript") or ""), "final": True}]
        if t in ("response.output_audio_transcript.delta", "response.audio_transcript.delta") and msg.get("delta"):
            return [{"type": "transcript", "role": "assistant", "text": str(msg["delta"]), "final": False}]
        if t == "response.function_call_arguments.done":
            try:
                args = json.loads(msg.get("arguments") or "{}")
            except Exception:
                args = {}
            return [{"type": "tool_call", "id": str(msg.get("call_id") or ""), "name": str(msg.get("name") or ""),
                     "args": args}]
        if t == "response.done":
            self.response_active = False
            return [{"type": "turn_done"}]
        if t == "error":
            e = msg.get("error") or {}
            return [{"type": "error", "message": str(e.get("message") or e)}]
        return []


class GPTLive(LiveProvider):
    """OpenAI GPT-Live, ủy nhiệm kiểu client: Javis là backend.

    Không có tool theo nghĩa cũ: model tự quyết giao việc và phát `session.delegation.created`
    (chỉ có metadata, KHÔNG có nội dung việc), nên Javis dựng yêu cầu từ chữ người dùng vừa nói.
    Trả kết quả bằng `session.commentary.append` (model tự thuật lại), tiến độ bằng
    `session.thinking.append`. Không có sự kiện interrupted (model tự quyết ngắt lời) lẫn
    turn_done; turn_done được suy ra khi người dùng bắt đầu nói mà trợ lý đang có chữ dở.
    """
    name = "gpt-live"

    def __init__(self, api_key: str, model: str = "", voice: str = "", system: str = GPT_LIVE_PROMPT,
                 tools: Optional[List[dict]] = None, recognition_lang: str = "vi-VN"):
        super().__init__(api_key, model=model, voice=voice, system=system, tools=tools, recognition_lang=recognition_lang)
        self._user_buf = ""       # chữ người dùng đang nói (chưa chốt)
        self._user_last = ""      # câu người dùng gần nhất đã chốt
        self._asst_open = False   # trợ lý đang có chữ dở (để suy ra turn_done)
        self.session_id = ""

    def url(self) -> str:
        return "wss://api.openai.com/v1/live/sessions"

    def headers(self) -> List[tuple]:
        return [("Authorization", f"Bearer {self.api_key}")]

    def supports_async_tools(self) -> bool:
        return True

    def setup_message(self) -> dict:
        return {"type": "session.start", "session": {
            "model": self.model, "instructions": self.system,
            "audio": {"format": {"type": "audio/pcm", "rate": 24000}, "output": {"voice": self.voice}},
            "delegation": {"type": "client"},
        }}

    def audio_message(self, pcm16_16k: bytes) -> dict:
        return {"type": "session.input_audio.append", "audio": _b64(resample_16k_to_24k(pcm16_16k))}

    def text_message(self, text: str) -> dict:
        # Chữ gõ tay: lái model trả lời câu đó bằng lời (GPT-Live không có ô nhập text cho model giọng).
        return {"type": "session.instructions.append", "delegation_id": None,
                "content": "Người dùng vừa GÕ chữ (không nói): \"" + text[:GPT_LIVE_APPEND_MAX]
                           + "\". Trả lời câu đó bằng lời."}

    def tool_running_messages(self, call_id: str, name: str) -> List[dict]:
        return [{"type": "session.thinking.append", "delegation_id": call_id or None,
                 "content": "Bộ não chính đang xử lý, chưa có kết quả. Chưa được nói là đã làm xong."}]

    def tool_result_messages(self, call_id: str, name: str, result: str) -> List[dict]:
        return [{"type": "session.commentary.append", "delegation_id": call_id or None,
                 "content": (result or "(không có nội dung)")[:GPT_LIVE_APPEND_MAX]}]

    def context_messages(self, text: str) -> List[dict]:
        if not text:
            return []
        return [{"type": "session.thinking.append", "delegation_id": None, "content": text[:GPT_LIVE_APPEND_MAX]}]

    def close_messages(self) -> List[dict]:
        return [{"type": "session.close"}]

    def _flush_user(self) -> List[dict]:
        if not self._user_buf.strip():
            return []
        self._user_last = self._user_buf.strip()
        self._user_buf = ""
        return [{"type": "transcript", "role": "user", "text": self._user_last, "final": True}]

    def translate(self, msg: dict) -> List[dict]:
        t = str(msg.get("type") or "")
        if t == "session.started":
            self.session_id = str(((msg.get("session") or {}).get("id")) or "")
            return [{"type": "ready"}]
        if t == "session.output_audio.delta" and msg.get("delta"):
            out = self._flush_user()
            try:
                out.append({"type": "audio", "data": base64.b64decode(msg["delta"])})
            except Exception:
                pass
            return out
        if t == "session.input_transcript.delta":
            out: List[dict] = []
            if self._asst_open:
                self._asst_open = False
                out.append({"type": "turn_done"})
            self._user_buf += str(msg.get("delta") or "")
            out.append({"type": "transcript", "role": "user", "text": self._user_buf, "final": False})
            return out
        if t == "session.output_transcript.delta" and msg.get("delta"):
            out = self._flush_user()
            self._asst_open = True
            out.append({"type": "transcript", "role": "assistant", "text": str(msg["delta"]), "final": False})
            return out
        if t == "session.delegation.created":
            d = msg.get("delegation") or {}
            if str(d.get("target") or "") != "client":
                return []
            out = self._flush_user()
            req = self._user_last or "(không rõ yêu cầu, hãy hỏi lại người dùng)"
            out.append({"type": "tool_call", "id": str(d.get("id") or ""), "name": "ask_javis", "args": {"request": req}})
            return out
        if t == "session.closed":
            reason = str(msg.get("reason") or "")
            out = self._flush_user()
            if self._asst_open:
                self._asst_open = False
                out.append({"type": "turn_done"})
            if reason and reason != "close_requested":
                out.append({"type": "error", "message": f"Phiên GPT-Live kết thúc: {reason}"})
            return out
        if t == "error":
            e = msg.get("error") or {}
            return [{"type": "error", "message": str(e.get("message") or e)}]
        return []


_CLASSES = {"gemini": GeminiLive, "openai": OpenAIRealtime, "gpt-live": GPTLive}


def make_provider(cfg: dict, system: str = "", recognition_lang: str = "vi-VN") -> LiveProvider:
    """Dựng nhà cung cấp Live từ settings. Ném RuntimeError có câu người đọc hiểu được."""
    v = (cfg or {}).get("voice") or {}
    m = (cfg or {}).get("model") or {}
    prov = str(v.get("live_provider") or "gemini").strip().lower()
    if prov not in PROVIDERS:
        raise RuntimeError(f"Nhà cung cấp Live '{prov}' không có. Chọn: {', '.join(PROVIDERS)}.")
    key = str(m.get(PROVIDERS[prov]["key_field"]) or "").strip()
    if not key:
        raise RuntimeError(f"{PROVIDERS[prov]['label']} chưa có API key ở trang Models.")
    cls = _CLASSES[prov]
    kw = {"model": str(v.get("live_model") or ""), "voice": str(v.get("live_voice") or ""),
          "recognition_lang": recognition_lang}
    if system:
        kw["system"] = system
    return cls(key, **kw)


def catalog() -> dict:
    """Cho trang Cài đặt: nhà cung cấp, model gợi ý, giọng."""
    return {k: {"label": p["label"], "default_model": p["default_model"], "voices": p["voices"],
                "key_field": p["key_field"]} for k, p in PROVIDERS.items()}
