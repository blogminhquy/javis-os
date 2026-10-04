"""Nhà cung cấp NGHE NÓI THẲNG (Voice V2 bậc Live, docs/dev/2026-10-voice-call-spec.md phụ lục A5).

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
import os
import re
import shutil
import sys
import tempfile
import time
import unicodedata
from typing import Any, AsyncIterator, Dict, List, Optional

import localefmt

_OPENAI_VOICES = ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]
# Giọng của realtime v3 trên gói ChatGPT (Codex app-server). marin/alloy... của API bị v3 từ chối.
CHATGPT_VOICES = ["juniper", "maple", "spruce", "ember", "vale", "breeze", "arbor", "sol", "cove"]

# `transport`: "pcm" = trình duyệt đẩy PCM qua /ws/voice-live; "webrtc" = trình duyệt nối THẲNG
# nhà cung cấp, /ws/voice-live chỉ chuyển gói bắt tay SDP và chữ (ChatGPT Live).
PROVIDERS = {
    "chatgpt": {"label": "ChatGPT Live (gói ChatGPT)", "key_field": None,
                "default_model": "", "default_voice": "juniper", "voices": CHATGPT_VOICES, "transport": "webrtc"},
    "gemini": {"label": "Google Gemini Live (API)", "key_field": "gemini_api_key",
               "default_model": "gemini-3.1-flash-live-preview",   # 03/2026; bản cũ: gemini-2.5-flash-native-audio-preview-12-2025
               "default_voice": "Aoede", "voices": ["Aoede", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Zephyr"],
               "transport": "pcm"},
    "openai": {"label": "OpenAI Realtime (API)", "key_field": "openai_api_key",
               "default_model": "gpt-realtime", "default_voice": "marin", "voices": _OPENAI_VOICES, "transport": "pcm"},
    "gpt-live": {"label": "OpenAI GPT-Live (API)", "key_field": "openai_api_key",
                 "default_model": "gpt-live-1", "default_voice": "marin", "voices": _OPENAI_VOICES, "transport": "pcm"},
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

    async def say_status(self, text: str) -> bool:
        """Cho model đọc to một câu tiến độ (việc đang chạy tới đâu), không phải câu trả lời của việc nào.
        Trả False khi nhà cung cấp không có kênh đó: bên gọi tự tìm đường khác hoặc im."""
        return False

    def is_quiet(self) -> bool:
        """Không ai đang nói (người dùng lẫn model) nên chen một câu tiến độ vào được không."""
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

    async def restore_history(self, messages: List[dict]):
        """Bounded transcript context after focus sleep; never a request to generate speech."""
        history, budget = [], 8000
        for message in reversed(messages[-12:]):
            role = message.get("role")
            if role not in ("user", "assistant"):
                continue
            text = str(message.get("content") or "")[:min(2000, budget)].strip()
            if text:
                history.insert(0, {"role": role, "content": text})
                budget -= len(text)
            if budget <= 0:
                break
        if history:
            await self._send_all(self.history_messages(history))

    def history_messages(self, history: List[dict]) -> List[dict]:
        return []

    async def send_tool_running(self, call_id: str, name: str):
        await self._send_all(self.tool_running_messages(call_id, name))

    async def send_tool_result(self, call_id: str, name: str, result: str):
        await self._send_all(self.tool_result_messages(call_id, name, result))

    async def send_tool_ack(self, call_id: str, name: str, text: str):
        """Đóng một lần giao việc KHÔNG có kết quả mới (lời nói thêm lúc đang chờ, 0.65.21). Live qua
        API cần đúng một kết quả cho mỗi lời gọi tool, không thì model chờ mãi."""
        await self.send_tool_result(call_id, name, text)

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

    def history_messages(self, history: List[dict]) -> List[dict]:
        # https://ai.google.dev/gemini-api/docs/live-api/capabilities#incremental-updates
        return [{"clientContent": {"turns": [
            {"role": "model" if m["role"] == "assistant" else "user",
             "parts": [{"text": m["content"]}]} for m in history], "turnComplete": False}}]

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
    def history_messages(self, history: List[dict]) -> List[dict]:
        return [{"type": "conversation.item.create", "item": {
            "type": "message", "role": m["role"], "content": [{
                "type": "output_text" if m["role"] == "assistant" else "input_text",
                "text": m["content"]}]}} for m in history]

    async def send_text(self, text: str):
        await super().send_text(text)
        # Text input does not trigger server VAD. Request a response once it is safe.
        if self.response_active:
            self._pending_create = True
        else:
            self.response_active = True
            await self._send({"type": "response.create"})

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

    async def send_text(self, text: str):
        # A browser wake handoff has no provider input_transcript event. Preserve it for
        # delegation, whose payload carries only metadata, and do not emit a duplicate user.
        self._user_buf = ""
        self._user_last = text
        await super().send_text(text)

    def history_messages(self, history: List[dict]) -> List[dict]:
        prefix = ("Lịch sử trước lúc chờ, chỉ làm ngữ cảnh, không thực hiện lại yêu cầu cũ. "
                  "Đợi lượt mới của người dùng.\n")
        frames = []
        for message in history:
            item = dict(message)
            encoded = json.dumps(item, ensure_ascii=False)
            # Bound each append, not the whole oldest-first history: truncating that blob
            # would discard the most recent turns and leave malformed JSON.
            while len(prefix) + len(encoded) > GPT_LIVE_APPEND_MAX and item["content"]:
                excess = len(prefix) + len(encoded) - GPT_LIVE_APPEND_MAX
                item["content"] = item["content"][:max(0, len(item["content"]) - excess)]
                encoded = json.dumps(item, ensure_ascii=False)
            frames.extend(self.context_messages(prefix + encoded))
        return frames

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
                out.append({"type": "error", "message": localefmt.chu(f"Phiên GPT-Live kết thúc: {reason}",
                                                                       f"GPT-Live session ended: {reason}")})
            return out
        if t == "error":
            e = msg.get("error") or {}
            return [{"type": "error", "message": str(e.get("message") or e)}]
        return []


# ChatGPT Live (docs/dev/2026-10-voice-call-spec.md mục 3.3): model nói chuyện của OpenAI lo chuyện
# trò, việc cần dữ liệu thì GIAO cho bộ não Javis. Xưng hô theo người dùng, không ép cố định.
CHATGPT_LIVE_PROMPT = (
    "Bạn là Javis, trợ lý cá nhân, đang nói chuyện với người dùng qua cuộc gọi bằng giọng nói. "
    "Nói tự nhiên như người qua điện thoại, ngắn 1 đến 2 câu. Xưng hô đúng theo cách người dùng đang "
    "xưng với bạn (phần bộ nhớ bên dưới cho biết nếu có), không tự đổi. Chuyện trò, hỏi thăm, giải "
    "thích kiến thức chung thì trả lời thẳng. Mọi câu cần dữ liệu thật hay hành động (doanh thu, đơn "
    "hàng, lịch, email, file, ghi chú, ký ức, mở trang trên màn hình, gửi tin, nhắc hẹn, tạo việc) thì "
    "KHÔNG đoán: nói một câu đệm rất ngắn kiểu 'Để em xem nhé' rồi giao việc cho hệ thống. Trong lúc "
    "đang chờ kết quả mà người dùng chỉ nói kiểu 'ok', 'xong thì báo anh nhé', 'cảm ơn' thì KHÔNG giao "
    "việc lần nữa, chỉ đáp một câu ngắn là đang làm. Khi hệ thống trả kết quả, đọc lại tự nhiên, ngắn "
    "gọn, không thêm số liệu (bản đầy đủ đã hiện trên màn hình). Bị chen ngang thì dừng ngay và nghe."
)
SPEAK_MAX = 600          # kết quả bộ não đọc ra loa: phần đầu, đủ ý; bản đầy đủ hiện thành bong bóng
HANDOFF_SHORT_WORDS = 3  # yêu cầu giao việc ngắn hơn thì ghép câu người dùng vừa nói
HANDOFF_MERGE_S = 10.0
HISTORY_ITEMS = 12
HISTORY_CHARS = 8000
MEMORY_CHARS = 4000

# Lời nói thêm trong lúc bộ não chính còn đang làm (0.65.21, lỗi chủ dự án báo 01/10): model nói
# chuyện hay giao việc LẦN NỮA với câu kiểu "Ok, xem xong kiểm tra xong thì báo anh nhé" (Codex coi
# handoff tới giữa chừng là lời chỉnh hướng việc đang chạy). Route /ws/voice-live lọc các lần giao
# việc: câu chỉ gồm từ xác nhận thì bỏ, câu hỏi tiến độ thì trả lời ngay từ trạng thái thật, câu có yêu
# cầu thật chạy SONG SONG với việc đang chạy kèm ngữ cảnh, và bộ não được phép trả FOLLOWUP_NOOP khi
# chẳng có gì mới. Từ 0.71.2 không còn xếp hàng: trước đó mọi câu nói thêm chờ cả việc dài xong, nên
# hỏi "xong chưa" giữa chừng im re mấy phút rồi các câu trả lời cũ bị đọc dồn một lượt.
FOLLOWUP_NOOP = "JAVIS_NOOP"
# Việc chạy lâu thì Javis tự lên tiếng cho người dùng (đang không nhìn màn hình) biết còn sống.
STATUS_FIRST_S = 60.0    # việc chạy quá chừng này thì bắt đầu nói
STATUS_EVERY_S = 90.0    # rồi cách chừng này mới nói lại
STATUS_TICK_S = 5.0      # nhịp kiểm tra của vòng nền
FOLLOWUP_ACK = "Đã ghi nhận. Việc đang làm sẽ báo kết quả ngay khi xong, không có việc mới."
_ACK_WORDS = frozenset("""
ok oke okie okay ừ ừm ờ ừa vâng dạ được rồi nhé nha nhá nhỉ nghen thế vậy thì là xong xem kiểm tra
báo lại cho anh em chị mình tôi tớ bạn biết đi cảm ơn cám chờ đợi tí chút xíu nhanh lên cứ làm khi nào
có kết quả đó đấy nghe hiểu ạ à nhớ giúp hộ với luôn sau javis jarvis
sure yes yeah yep thanks thank you let me know when done fine great cool alright got it please
""".split())
_ACK_MAX_WORDS = 16


def is_followup_ack(text: str) -> bool:
    """Câu nói thêm CHỈ gồm từ xác nhận, nhắc báo kết quả, bảo chờ. Một từ lạ là coi như có yêu cầu thật
    (thà chạy thêm một lượt còn hơn nuốt mất yêu cầu)."""
    words = re.findall(r"[^\W\d_]+", str(text or "").lower())
    return 0 < len(words) <= _ACK_MAX_WORDS and all(w in _ACK_WORDS for w in words)


def _norm_words(text: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", str(text or "").lower()))


def is_same_request(previous: str, followup: str) -> bool:
    """Lần giao việc lặp lại (một phần) chính yêu cầu đang chạy: model hay bắn handoff đôi cho cùng
    một câu. Câu dài hơn yêu cầu cũ (thêm ý mới) KHÔNG tính là lặp."""
    new, old = _norm_words(followup), _norm_words(previous)
    return bool(new) and bool(old) and f" {new} " in f" {old} "


def parallel_request(running: List[str], followup: str) -> str:
    """Yêu cầu gửi bộ não chính cho câu nói thêm, chạy SONG SONG với các việc đang chạy.

    Báo rõ các việc kia CHƯA xong: bộ não không được coi kết quả của chúng là đã có, cũng không được
    ghi đè thứ chúng đang làm dở (tệp, tin đang soạn) trừ khi người dùng bảo rõ."""
    work = "; ".join('"' + str(r).strip()[:200] + '"' for r in running)
    return (f"Em đang làm các việc sau cho người dùng và chúng CHƯA xong: {work}. Trong lúc đó người dùng "
            f"nói thêm qua cuộc gọi: \"{str(followup).strip()}\". Việc này chạy SONG SONG với các việc trên, "
            f"không chờ chúng và kết quả của chúng chưa có. Nếu câu nói thêm chỉ là đồng ý, nhắc báo kết quả "
            f"hay bảo chờ thì trả lời đúng một dòng {FOLLOWUP_NOOP} và không làm gì thêm. Nếu có yêu cầu "
            f"mới thì làm phần đó rồi trả lời như thường; đừng sửa hay ghi đè thứ mà các việc đang chạy "
            f"đang làm dở (tệp, tin nhắn đang soạn), trừ khi người dùng bảo rõ.")


def is_noop_result(text: str) -> bool:
    t = str(text or "").strip()
    return FOLLOWUP_NOOP in t and len(t) <= 80


# Câu HỎI TIẾN ĐỘ trong lúc một việc đang chạy ("xong chưa", "đang làm gì", "có nghe thấy không").
# Model nói chuyện giao từng câu đó cho bộ não như một việc mới, mà bộ não chỉ biết trả lời sau khi việc
# dài xong. Nhận ra câu này để trả lời ngay từ trạng thái thật. Cố ý HẸP: nhận hụt thì câu đó vẫn chạy
# song song và được trả lời (chậm hơn một chút), còn nhận nhầm thì nuốt mất một yêu cầu thật.
_PROGRESS_MAX_WORDS = 12
_PROGRESS_RE = re.compile("|".join((
    r"\bxong\b.{0,20}\bchưa\b",                      # "xong chưa", "em xong chỗ đấy chưa"
    r"^(?:vẫn |còn )?chưa xong\b",                   # "vẫn chưa xong à" (câu đầu: "anh chưa xong" là lời của người dùng)
    r"\bxong rồi (?:hả|à|chưa|sao)\b",
    r"\btiến độ\b",
    r"\b(?:đến|tới) đâu rồi\b",
    r"\b(?:bao lâu|bao nhiêu lâu|bao nhiêu phút|mấy phút)\b.{0,20}\b(?:xong|hoàn thiện|hoàn thành|có kết quả|nữa)\b",
    r"\bcòn bao lâu\b",
    r"\bkhi nào (?:thì )?(?:xong|có kết quả|hoàn thiện)\b",
    r"\b(?:đang|vẫn đang|còn đang) làm (?:gì|việc gì|cái gì|nhiệm vụ nào|đến đâu|tới đâu)\b",
    r"\bmình đang làm (?:nhiệm vụ|việc|gì)\b",
    r"^(?:vẫn|còn) (?:đang )?(?:làm|chạy)\b.{0,25}\b(?:đúng không|không|hả|à)\b",
    r"\b(?:em|bạn|javis) (?:vẫn |còn )?(?:đang )?(?:làm|chạy)\b.{0,12}\b(?:đúng không|không|chưa|hả)\b",
    r"\bcó nghe (?:thấy|rõ|được)\b.{0,30}\bkhông\b",
    r"\bnghe (?:thấy|rõ) (?:không|chứ)\b",
    r"^(?:alo|a lô)\b",
    r"\b(?:are you|is it) (?:done|finished)\b", r"\bdone yet\b", r"\bhow(?:'s| is) it going\b",
    r"\bany (?:progress|update)\b", r"\bwhat are you (?:doing|working on)\b",
    r"\bhow long (?:until|till|will|is)\b", r"\bcan you hear me\b", r"\bare you (?:still )?(?:there|working)\b",
)))


def is_progress_question(text: str) -> bool:
    # NFC trước: chữ có dấu tách rời (NFD) làm `\b` của Python đứt giữa từ.
    s = unicodedata.normalize("NFC", str(text or "")).lower()
    s = " ".join(re.findall(r"[\w']+", s))
    words = s.split()
    return 0 < len(words) <= _PROGRESS_MAX_WORDS and bool(_PROGRESS_RE.search(s))


def _spoken_elapsed(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 90:
        return localefmt.chu(f"{s} giây", f"{s} seconds")
    m = round(s / 60)
    return localefmt.chu(f"{m} phút", f"{m} minutes")


def _short_request(text: str, limit: int = 80) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0].strip()


def _spoken_step(step: str) -> str:
    """Bước hiện tại để đọc to: bỏ biểu tượng đầu dòng và dấu chấm lửng ("⚙ Đang dùng công cụ: Write")."""
    return re.sub(r"\s+", " ", re.sub(r"^[^\w]+", "", str(step or ""))).strip().rstrip(".… ")[:80]


def status_line(jobs: List[dict], now: float) -> str:
    """Câu đọc to cho biết các việc đang chạy: làm gì, bao lâu rồi, tới bước nào.

    `jobs`: {"request", "started", "step"}; `now` cùng đồng hồ với `started`. Chỉ dùng số liệu thật
    (không đoán bao giờ xong): người nghe đang không nhìn màn hình, nói sai còn tệ hơn im."""
    jobs = sorted(jobs, key=lambda j: j.get("started", 0.0))
    if not jobs:
        return localefmt.chu("Em không có việc nào đang chạy ạ.", "Nothing is running right now.")
    longest = _spoken_elapsed(now - jobs[0].get("started", now))
    if len(jobs) == 1:
        what = _short_request(jobs[0].get("request", ""))
        step = _spoken_step(jobs[0].get("step", ""))
        step_vi = (", hiện " + step[:1].lower() + step[1:]) if step else ""
        step_en = (", now: " + step) if step else ""
        return localefmt.chu(f'Em vẫn đang làm việc "{what}", được {longest}{step_vi}.',
                             f'Still working on "{what}", {longest} so far{step_en}.')
    names = "; ".join('"' + _short_request(j.get("request", ""), 50) + '"' for j in jobs[:3])
    return localefmt.chu(f"Em đang làm {len(jobs)} việc: {names}. Việc lâu nhất đã được {longest}.",
                         f"Working on {len(jobs)} jobs: {names}. The longest has run {longest}.")


def speakable(text: str, limit: int = SPEAK_MAX) -> str:
    """Chữ đọc được từ câu trả lời markdown của bộ não: bỏ khối mã, ký hiệu, link; giữ số liệu.

    Bảng giữ lại thành các ô ngăn bằng phẩy (số liệu nằm ở đó). Cắt ở dấu kết câu gần nhất
    trước `limit` để câu nói ra không cụt giữa chừng.
    """
    s = str(text or "")
    s = re.sub(r"```.*?```", " ", s, flags=re.S)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    lines = []
    for line in s.splitlines():
        t = line.strip()
        if re.fullmatch(r"\|?[\s:\-|]+\|?", t) and "-" in t:
            continue   # dòng kẻ của bảng
        if t.startswith("|"):
            t = ", ".join(c.strip() for c in t.strip("|").split("|") if c.strip())
        t = re.sub(r"^#{1,6}\s*", "", t)
        t = re.sub(r"^[>\-*+]\s+", "", t)
        lines.append(t)
    s = " ".join(x for x in lines if x)
    s = re.sub(r"[*_`#>]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= limit:
        return s
    cut = s[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > limit // 3 else cut.rsplit(" ", 1)[0]).strip()


class _Status(str):
    """Câu tiến độ trong hàng lời đọc: phân biệt với lời đọc kết quả để bỏ được khi kết quả về."""


class ChatGPTLive(LiveProvider):
    """ChatGPT Live: realtime v3 của Codex app-server trên gói ChatGPT, KHÔNG cần API key.

    Âm thanh đi WebRTC thẳng trình duyệt tới OpenAI; lớp này chỉ dựng thread, chuyển SDP, dịch
    thông báo chữ và trả kết quả giao việc. Đo 01/10/2026: tiếng đầu 0,44 đến 0,85 giây khi ấm,
    handoff 0,5 giây sau câu hỏi, phiên 15 phút không rớt (spec mục 2).
    """
    name = "chatgpt"
    transport = "webrtc"
    # Hàng chờ lời đọc kết quả (0.65.23): đẩy appendSpeech giữa lúc model đang nói thì nó TRỘN hai
    # nội dung vào cùng một lượt (đo trên Codex 0.153.4 và 0.158), người nghe thấy hai câu trả lời lẫn
    # vào nhau. Nên chỉ đẩy khi model im; vừa đẩy mà model chưa mở lời thì chờ một khoảng ân hạn.
    SPEECH_START_GRACE = 8.0   # giây: chờ model mở lời cho kết quả vừa đẩy
    SPEECH_GAP = 0.4           # giây im sau lượt nói trước, cho nghe ra hai câu tách nhau
    SPEECH_WAIT_MAX = 90.0     # giây: trần chờ, mất khung transcript cũng không kẹt
    SPEECH_STALL = 4.0         # giây không có chữ mới thì coi lượt nói đã dừng (bị chen ngang, mất done)

    def __init__(self, api_key: str = "", model: str = "", voice: str = "", system: str = CHATGPT_LIVE_PROMPT,
                 tools: Optional[List[dict]] = None, recognition_lang: str = "vi-VN", memory_index: str = "",
                 app_server_getter=None):
        super().__init__(api_key, model=model, voice=voice, system=system, tools=tools, recognition_lang=recognition_lang)
        if self.voice not in CHATGPT_VOICES:
            self.voice = PROVIDERS["chatgpt"]["default_voice"]
        self.memory_index = str(memory_index or "")[:MEMORY_CHARS]
        if app_server_getter is None:
            import codex_realtime
            app_server_getter = codex_realtime.get_app_server
        self._get_server = app_server_getter
        self.srv = None
        self.thread_id = ""
        self.queue: Optional[asyncio.Queue] = None
        self.initial_items: List[dict] = []
        self._cwd = ""
        self._sdp: Optional[asyncio.Future] = None
        self._closing = False
        self._user_buf = ""
        self._user_last = ""
        self._user_last_at = 0.0
        self._interrupt_turns: List[str] = []
        self._held: List[dict] = []   # lời Javis tới lúc người dùng còn đang nói, chờ câu người dùng chốt
        self._bg: set = set()
        self._speaking = False        # model đang có một lượt nói chưa xong (theo transcript)
        self._last_delta_at = 0.0
        self._quiet_since = 0.0       # lúc lượt nói gần nhất xong
        self._pushed_at = 0.0         # lúc vừa đẩy appendSpeech mà model chưa mở lời
        self._speech_q: List[str] = []
        self._speech_task: Optional[asyncio.Task] = None

    async def connect(self):
        self._closing = False
        self.srv = await self._get_server()
        # Thư mục tạm rỗng: lượt Codex nào lỡ chạy cũng không thấy file thật của người dùng.
        self._cwd = tempfile.mkdtemp(prefix="javis-live-")
        res = await self.srv.request("thread/start", {
            "ephemeral": True, "cwd": self._cwd, "sandbox": "read-only", "approvalPolicy": "never",
            "developerInstructions": "Reply only: [FINAL]",
        }, timeout=40)
        self.thread_id = str(((res or {}).get("thread") or {}).get("id") or "")
        if not self.thread_id:
            raise RuntimeError(localefmt.chu("Codex app-server không mở được thread cho ChatGPT Live.",
                                              "Codex app-server could not open a thread for ChatGPT Live."))
        self.queue = self.srv.subscribe(self.thread_id)

    async def reconnect(self):
        # Không nối lại trong suốt được: trình duyệt phải bắt tay WebRTC lại từ đầu.
        await self.close()
        raise RuntimeError(localefmt.chu("ChatGPT Live đã ngắt, hãy bấm gọi lại.",
                                          "ChatGPT Live disconnected, press call again."))

    async def restore_history(self, messages: List[dict]):
        items, budget = [], HISTORY_CHARS
        for message in reversed((messages or [])[-HISTORY_ITEMS:]):
            role = message.get("role")
            if role not in ("user", "assistant"):
                continue
            text = str(message.get("content") or "")[:min(2000, budget)].strip()
            if text:
                items.insert(0, {"role": role, "text": text})
                budget -= len(text)
            if budget <= 0:
                break
        self.initial_items = items

    def start_params(self, sdp: str) -> dict:
        prompt = self.system
        if self.memory_index.strip():
            prompt += "\n\nBộ nhớ về người dùng (mục lục, chỉ làm ngữ cảnh):\n" + self.memory_index.strip()
        params = {
            "threadId": self.thread_id, "version": "v3", "outputModality": "audio",
            "transport": {"type": "webrtc", "sdp": sdp},
            "prompt": prompt, "voice": self.voice,
            # BẮT BUỘC tắt: mặc định Codex nhét ~5.300 token quét máy và thư mục làm việc vào prompt.
            "includeStartupContext": False,
            "clientManagedHandoffs": True, "delegationAckFiller": True,
            "flushTranscriptTailOnSessionEnd": False,
            "realtimeStartInstructions": "Do no work. Reply only: [FINAL]",
        }
        if self.initial_items:
            params["initialItems"] = self.initial_items
        return params

    async def start_webrtc(self, sdp: str) -> str:
        """Gửi offer của trình duyệt, trả answer. events() phải đang chạy (nó nhận thông báo sdp)."""
        loop = asyncio.get_running_loop()
        self._sdp = loop.create_future()
        await self.srv.request("thread/realtime/start", self.start_params(sdp), timeout=30)
        try:
            return await asyncio.wait_for(self._sdp, 25)
        except asyncio.TimeoutError:
            raise RuntimeError(localefmt.chu("ChatGPT Live không trả lời bắt tay sau 25 giây.",
                                              "ChatGPT Live did not answer the handshake after 25 seconds."))

    def _flush_user(self) -> List[dict]:
        if not self._user_buf.strip():
            return []
        text = self._user_buf.strip()
        self._user_buf = ""
        self._user_last, self._user_last_at = text, time.monotonic()
        return [{"type": "transcript", "role": "user", "text": text, "final": True}]

    def _handoff_request(self, req: str) -> str:
        req = str(req or "").strip()
        # Câu đang nghe dở (handoff hay tới trước done) đầy đủ hơn câu đã chốt lần trước.
        recent = self._user_buf.strip() or (
            self._user_last if time.monotonic() - self._user_last_at <= HANDOFF_MERGE_S else "")
        # Yêu cầu là MẢNH của câu người dùng đang nói ("là bao nhiêu em" trong "Doanh thu hôm nay ...
        # là bao nhiêu em", đo 01/10) thì dùng cả câu cho đủ ý.
        if recent and req and req.lower() in recent.lower():
            return recent
        if len(req.split()) < HANDOFF_SHORT_WORDS and recent:
            # Phiên ngồi im lâu có lúc tách đôi câu ("Doanh" / "là bao nhiêu em"): ghép câu vừa nói.
            return (recent + " " + req).strip()
        return req or recent or "(không rõ yêu cầu, hãy hỏi lại người dùng)"

    def translate(self, msg: dict) -> List[dict]:
        method = str(msg.get("method") or "")
        p = msg.get("params") or {}
        if method == "thread/realtime/sdp":
            if self._sdp is not None and not self._sdp.done():
                self._sdp.set_result(str(p.get("sdp") or ""))
            return []
        if method == "thread/realtime/error":
            text = str(p.get("message") or "lỗi không rõ")
            if self._sdp is not None and not self._sdp.done():
                self._sdp.set_exception(RuntimeError(f"ChatGPT Live không mở được: {text}"))
            return [{"type": "error", "message": localefmt.chu(f"ChatGPT Live lỗi: {text}", f"ChatGPT Live error: {text}")}]
        # Chỉ thông báo `transcript/done` của người dùng mới tạo bong bóng chốt. Đo trên dashboard thật
        # (01/10): model hay BẮT ĐẦU trả lời trước khi chữ cuối của người dùng về ("... có khỏe" rồi
        # mới tới " không"), và handoff tới trước cả done. Chốt sớm theo những mốc đó sinh bong bóng
        # cụt, bong bóng lặp và đảo thứ tự. Nên lời Javis tới lúc người dùng còn đang nói thì GIỮ
        # lại, phát ra ngay sau câu người dùng đã chốt.
        if method == "thread/realtime/transcript/delta":
            delta = str(p.get("delta") or "")
            if p.get("role") == "user":
                self._user_buf += delta
                return [{"type": "transcript", "role": "user", "text": self._user_buf.strip(), "final": False}] \
                    if self._user_buf.strip() else []
            if not delta:
                return []
            self._speaking, self._pushed_at, self._last_delta_at = True, 0.0, time.monotonic()
            ev = {"type": "transcript", "role": "assistant", "text": delta, "final": False}
            if self._user_buf.strip():
                self._held.append(ev)
                return []
            return [ev]
        if method == "thread/realtime/transcript/done":
            if p.get("role") == "user":
                text = str(p.get("text") or "").strip() or self._user_buf.strip()
                self._user_buf = ""
                out: List[dict] = []
                if text:
                    self._user_last, self._user_last_at = text, time.monotonic()
                    out.append({"type": "transcript", "role": "user", "text": text, "final": True})
                out += self._held
                self._held = []
                return out
            self._speaking, self._pushed_at, self._quiet_since = False, 0.0, time.monotonic()
            # Javis nói xong mà câu người dùng vẫn chưa có done (hiếm): chốt phần đã nghe rồi mới nhả.
            out = self._flush_user() + self._held + [{"type": "turn_done"}]
            self._held = []
            return out
        if method == "thread/realtime/itemAdded":
            item = p.get("item") or {}
            if item.get("type") != "handoff_request":
                return []
            return [{"type": "tool_call", "id": str(item.get("handoff_id") or ""), "name": "ask_javis",
                     "args": {"request": self._handoff_request(item.get("input_transcript"))}}]
        if method == "turn/started":
            # Mỗi lần giao việc Codex TỰ mở một lượt agent: chặn ngay, việc thật do bộ não Javis làm.
            tid = str(((p.get("turn") or {}).get("id")) or p.get("turnId") or "")
            if tid:
                self._interrupt_turns.append(tid)
            return []
        if method == "thread/realtime/closed":
            if self._closing:
                return []
            return [{"type": "error", "message": localefmt.chu(
                f"ChatGPT Live đã ngắt ({p.get('reason') or 'không rõ lý do'}).",
                f"ChatGPT Live disconnected ({p.get('reason') or 'reason unknown'}).")}]
        if method == "_exit":
            return [] if self._closing else [{"type": "error", "message": localefmt.chu(
                "Codex app-server đã dừng, cuộc gọi ChatGPT Live kết thúc.",
                "Codex app-server stopped, the ChatGPT Live call has ended.")}]
        return []

    async def _interrupt(self, turn_id: str):
        try:
            await self.srv.request("turn/interrupt", {"threadId": self.thread_id, "turnId": turn_id}, timeout=10)
        except Exception:
            pass

    async def events(self) -> AsyncIterator[dict]:
        if self.queue is None:
            return
        debug = bool(os.environ.get("JAVIS_LIVE_DEBUG"))
        while True:
            msg = await self.queue.get()
            if debug:
                p = msg.get("params") or {}
                item = p.get("item") or {}
                print(f"[chatgpt live] {time.monotonic():.1f} {msg.get('method')} role={p.get('role')} "
                      f"delta={p.get('delta')!r} text={p.get('text')!r} item={item.get('type')}"
                      + (f" request={item.get('input_transcript')!r}" if item.get("type") == "handoff_request" else ""),
                      file=sys.stderr)
            for ev in self.translate(msg):
                yield ev
            while self._interrupt_turns:
                task = asyncio.ensure_future(self._interrupt(self._interrupt_turns.pop(0)))
                self._bg.add(task)
                task.add_done_callback(self._bg.discard)
            if msg.get("method") == "_exit" or (msg.get("method") == "thread/realtime/closed" and self._closing):
                return

    async def send_audio(self, pcm16_16k: bytes):
        return   # âm thanh đi WebRTC, không qua máy chủ

    async def send_text(self, text: str):
        self._user_last, self._user_last_at = str(text), time.monotonic()
        await self.srv.request("thread/realtime/appendText", {"threadId": self.thread_id, "text": str(text)})

    def _enqueue_speech(self, text: str):
        self._speech_q.append(text)
        if self._speech_task is None or self._speech_task.done():
            self._speech_task = asyncio.ensure_future(self._drain_speech())
            self._bg.add(self._speech_task)
            self._speech_task.add_done_callback(self._bg.discard)

    async def send_tool_result(self, call_id: str, name: str, result: str):
        """Xếp lời đọc kết quả vào hàng, trả về ngay (route không phải đứng chờ model đọc xong)."""
        # Câu tiến độ còn kẹt trong hàng là câu cũ ngay khi kết quả thật về: đọc nó SAU câu trả lời
        # ("em vẫn đang làm" rồi mới "xong rồi") nghe như Javis lú.
        self._speech_q[:] = [t for t in self._speech_q if not isinstance(t, _Status)]
        self._enqueue_speech(speakable(result) or "Em chưa có kết quả.")

    async def say_status(self, text: str) -> bool:
        """Câu tiến độ cho người đang không nhìn màn hình. Đi chung hàng với lời đọc kết quả nên không
        bao giờ chen vào giữa câu model đang nói, và bị bỏ nếu kết quả thật về trước."""
        if self._closing:
            return False
        self._enqueue_speech(_Status(text))
        return True

    def is_quiet(self) -> bool:
        return not self._user_buf.strip() and not self._speech_q and not self._model_busy()

    def _model_busy(self) -> bool:
        now = time.monotonic()
        if self._speaking and now - self._last_delta_at < self.SPEECH_STALL:
            return True
        if self._pushed_at and now - self._pushed_at < self.SPEECH_START_GRACE:
            return True
        return bool(self._quiet_since) and now - self._quiet_since < self.SPEECH_GAP

    async def _drain_speech(self):
        while self._speech_q and not self._closing:
            deadline = time.monotonic() + self.SPEECH_WAIT_MAX
            while self._model_busy() and time.monotonic() < deadline and not self._closing:
                await asyncio.sleep(0.05)
            if self._closing or not self._speech_q:
                return
            text = self._speech_q.pop(0)
            self._pushed_at = time.monotonic()
            if os.environ.get("JAVIS_LIVE_DEBUG"):
                print(f"[chatgpt live] {time.monotonic():.1f} appendSpeech ({len(text)} ký tự)", file=sys.stderr)
            try:
                await self.srv.request("thread/realtime/appendSpeech", {"threadId": self.thread_id, "text": text})
            except Exception as e:
                print(f"[chatgpt live] appendSpeech lỗi: {type(e).__name__}: {e}", file=sys.stderr)

    async def send_tool_ack(self, call_id: str, name: str, text: str):
        return   # handoff do client tự quản không cần kết quả; nói gì ở đây là đọc thừa ra loa

    async def send_tool_running(self, call_id: str, name: str):
        return

    async def send_context(self, text: str):
        return   # ngữ cảnh giao diện đi kèm yêu cầu giao việc (route ghép vào), không nói ra

    async def truncate_played(self, played_ms: int):
        return

    async def interrupt(self):
        return   # model tự xử lý chen ngang (VAD phía OpenAI)

    async def close(self):
        self._closing = True
        self._speech_q.clear()   # cúp máy thì không đọc nốt
        srv, tid = self.srv, self.thread_id
        if srv is not None and tid:
            try:
                await srv.request("thread/realtime/stop", {"threadId": tid}, timeout=5)
            except Exception:
                pass
            try:
                srv.unsubscribe(tid)
            except Exception:
                pass
        for task in list(self._bg):
            task.cancel()
        if self._cwd:
            shutil.rmtree(self._cwd, ignore_errors=True)
            self._cwd = ""


_CLASSES = {"chatgpt": ChatGPTLive, "gemini": GeminiLive, "openai": OpenAIRealtime, "gpt-live": GPTLive}

CHATGPT_UNAVAILABLE = {
    "no_cli": "Chưa cài Codex CLI nên chưa dùng được ChatGPT Live. Cài Codex rồi nối ChatGPT ở trang Models.",
    "no_login": "Chưa nối ChatGPT ở trang Models nên chưa dùng được ChatGPT Live.",
    "old_cli": "Codex CLI trên máy đã cũ (cần bản 0.153 trở lên) nên chưa dùng được ChatGPT Live. Cập nhật Codex rồi thử lại.",
}


def make_provider(cfg: dict, system: str = "", recognition_lang: str = "vi-VN", memory_index: str = "") -> LiveProvider:
    """Dựng nhà cung cấp Live từ settings. Ném RuntimeError có câu người đọc hiểu được."""
    v = (cfg or {}).get("voice") or {}
    m = (cfg or {}).get("model") or {}
    prov = str(v.get("live_provider") or "gemini").strip().lower()
    if prov not in PROVIDERS:
        raise RuntimeError(localefmt.chu(f"Nhà cung cấp Live '{prov}' không có. Chọn: {', '.join(PROVIDERS)}.",
                                         f"Live provider '{prov}' does not exist. Choose: {', '.join(PROVIDERS)}."))
    if prov == "chatgpt":
        import codex_realtime
        ok, why = codex_realtime.realtime_available(cfg)
        if not ok:
            raise RuntimeError(CHATGPT_UNAVAILABLE.get(why, localefmt.chu("ChatGPT Live chưa dùng được.",
                                                                           "ChatGPT Live is not available yet.")))
        kw = {"voice": str(v.get("chatgpt_voice") or ""), "recognition_lang": recognition_lang,
              "memory_index": memory_index}
        if system:
            kw["system"] = system
        return ChatGPTLive(**kw)
    key = str(m.get(PROVIDERS[prov]["key_field"]) or "").strip()
    if not key:
        raise RuntimeError(localefmt.chu(f"{PROVIDERS[prov]['label']} chưa có API key ở trang Models.",
                                         f"{PROVIDERS[prov]['label']} has no API key on the Models page."))
    cls = _CLASSES[prov]
    kw = {"model": str(v.get("live_model") or ""), "voice": str(v.get("live_voice") or ""),
          "recognition_lang": recognition_lang}
    if system:
        kw["system"] = system
    return cls(key, **kw)


def catalog() -> dict:
    """Cho trang Cài đặt: nhà cung cấp, model gợi ý, giọng, kiểu truyền âm thanh."""
    return {k: {"label": p["label"], "default_model": p["default_model"], "voices": p["voices"],
                "key_field": p["key_field"], "transport": p["transport"],
                "default_voice": p["default_voice"]} for k, p in PROVIDERS.items()}
