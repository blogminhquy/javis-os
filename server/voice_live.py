"""Nhà cung cấp NGHE NÓI THẲNG (Voice V2 bậc Live, docs/dev/2026-09-voice-v2-spec.md mục 4).

Trình duyệt đẩy PCM16 mono 16 kHz lên `/ws/voice-live` (main.py); route đó cầm một
`LiveProvider` ở đây, chuyển audio sang nhà cung cấp và trả sự kiện chuẩn hoá về:

    {"type":"audio","data":bytes}            PCM16 mono 24 kHz
    {"type":"interrupted"}                    người dùng chen ngang, xả hàng đợi phát
    {"type":"transcript","role":"user"|"assistant","text":str,"final":bool}
    {"type":"tool_call","id":str,"name":str,"args":dict}
    {"type":"turn_done"}
    {"type":"error","message":str}

Hai nhà cung cấp: GeminiLive (BidiGenerateContent v1beta) và OpenAIRealtime (API GA 2025-08:
`session.type = realtime`, khối `audio.input/output`, KHÔNG còn header OpenAI-Beta; phần dịch sự
kiện nhận cả tên cũ `response.audio.*` lẫn tên mới `response.output_audio.*`).
Thêm nhà cung cấp mới = thêm một lớp con, route và trình duyệt không đổi. Tên model để trong
cài đặt vì cả hai hãng đổi tên liên tục; mặc định ở PROVIDERS chỉ là gợi ý lúc viết.

Mọi hàm dựng thông điệp (`setup_message`, `audio_message`, ...) là hàm THUẦN để test không cần
mạng. Chuyển mẫu 16 kHz -> 24 kHz cho OpenAI (chỉ nhận 24 kHz) làm bằng nội suy tuyến tính,
đủ tốt cho giọng nói và không cần numpy.
"""
from __future__ import annotations

import array
import asyncio
import base64
import json
from typing import Any, AsyncIterator, Dict, List, Optional

PROVIDERS = {
    "gemini": {"label": "Google Gemini Live (API)", "key_field": "gemini_api_key",
               "default_model": "gemini-3.1-flash-live-preview",   # 03/2026; bản cũ: gemini-2.5-flash-native-audio-preview-12-2025
               "default_voice": "Aoede", "voices": ["Aoede", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Zephyr"]},
    "openai": {"label": "OpenAI Realtime (API)", "key_field": "openai_api_key",
               "default_model": "gpt-realtime", "default_voice": "marin",
               "voices": ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"]},
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
    "Bạn là Javis, trợ lý cá nhân, đang nói chuyện trực tiếp bằng giọng. Nói ngắn, tự nhiên, đúng "
    "ngôn ngữ người dùng. Không bịa dữ liệu: cần dữ liệu thật hay hành động thì gọi tool ask_javis "
    "rồi thuật lại kết quả. Đang được ngắt lời thì dừng ngay và nghe."
)


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
                 tools: Optional[List[dict]] = None):
        self.api_key = api_key
        self.model = model or PROVIDERS[self.name]["default_model"]
        self.voice = voice or PROVIDERS[self.name]["default_voice"]
        self.system = system
        self.tools = tools if tools is not None else [ASK_JAVIS_TOOL]
        self.ws = None

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

    def interrupt_messages(self) -> List[dict]:
        return []

    def translate(self, msg: dict) -> List[dict]:  # pragma: no cover
        raise NotImplementedError

    # ---- mạng ----
    async def connect(self):
        import websockets
        self.ws = await websockets.connect(self.url(), extra_headers=self.headers(), max_size=16 * 1024 * 1024)
        await self._send(self.setup_message())

    async def _send(self, obj: dict):
        if self.ws is not None:
            await self.ws.send(json.dumps(obj))

    async def send_audio(self, pcm16_16k: bytes):
        await self._send(self.audio_message(pcm16_16k))

    async def send_text(self, text: str):
        await self._send(self.text_message(text))

    async def send_tool_result(self, call_id: str, name: str, result: str):
        for m in self.tool_result_messages(call_id, name, result):
            await self._send(m)

    async def interrupt(self):
        for m in self.interrupt_messages():
            await self._send(m)

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

    async def close(self):
        ws, self.ws = self.ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass


class GeminiLive(LiveProvider):
    name = "gemini"

    def url(self) -> str:
        return ("wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta."
                f"GenerativeService.BidiGenerateContent?key={self.api_key}")

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
        }
        if self.tools:
            setup["tools"] = [{"functionDeclarations": self.tools}]
        return {"setup": setup}

    def audio_message(self, pcm16_16k: bytes) -> dict:
        return {"realtimeInput": {"audio": {"mimeType": "audio/pcm;rate=16000", "data": _b64(pcm16_16k)}}}

    def text_message(self, text: str) -> dict:
        return {"clientContent": {"turns": [{"role": "user", "parts": [{"text": text}]}], "turnComplete": True}}

    def tool_result_messages(self, call_id: str, name: str, result: str) -> List[dict]:
        return [{"toolResponse": {"functionResponses": [
            {"id": call_id, "name": name, "response": {"output": result}}]}}]

    def translate(self, msg: dict) -> List[dict]:
        out: List[dict] = []
        if "setupComplete" in msg:
            return [{"type": "ready"}]
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
            if it.get("text"):
                out.append({"type": "transcript", "role": "user", "text": it["text"], "final": bool(it.get("finished", False))})
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

    def url(self) -> str:
        return f"wss://api.openai.com/v1/realtime?model={self.model}"

    def headers(self) -> List[tuple]:
        # API GA không cần header OpenAI-Beta; gửi kèm là rơi về khuôn beta cũ và session.type bị từ chối.
        return [("Authorization", f"Bearer {self.api_key}")]

    def setup_message(self) -> dict:
        tools = [{"type": "function", "name": t["name"], "description": t.get("description", ""),
                  "parameters": t.get("parameters", {"type": "object", "properties": {}})} for t in self.tools]
        pcm24 = {"type": "audio/pcm", "rate": 24000}
        return {"type": "session.update", "session": {
            "type": "realtime", "output_modalities": ["audio"], "instructions": self.system,
            "audio": {
                "input": {"format": pcm24, "transcription": {"model": "gpt-4o-mini-transcribe"},
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
        return [{"type": "conversation.item.create",
                 "item": {"type": "function_call_output", "call_id": call_id, "output": result}},
                {"type": "response.create"}]

    def interrupt_messages(self) -> List[dict]:
        return [{"type": "response.cancel"}]

    def translate(self, msg: dict) -> List[dict]:
        t = str(msg.get("type") or "")
        if t in ("session.created", "session.updated"):
            return [{"type": "ready"}]
        if t in ("response.output_audio.delta", "response.audio.delta") and msg.get("delta"):
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
            return [{"type": "turn_done"}]
        if t == "error":
            e = msg.get("error") or {}
            return [{"type": "error", "message": str(e.get("message") or e)}]
        return []


def make_provider(cfg: dict, system: str = SYSTEM_PROMPT) -> LiveProvider:
    """Dựng nhà cung cấp Live từ settings. Ném RuntimeError có câu người đọc hiểu được."""
    v = (cfg or {}).get("voice") or {}
    m = (cfg or {}).get("model") or {}
    prov = str(v.get("live_provider") or "gemini").strip().lower()
    if prov not in PROVIDERS:
        raise RuntimeError(f"Nhà cung cấp Live '{prov}' không có. Chọn: {', '.join(PROVIDERS)}.")
    key = str(m.get(PROVIDERS[prov]["key_field"]) or "").strip()
    if not key:
        raise RuntimeError(f"{PROVIDERS[prov]['label']} chưa có API key ở trang Models.")
    cls = GeminiLive if prov == "gemini" else OpenAIRealtime
    return cls(key, model=str(v.get("live_model") or ""), voice=str(v.get("live_voice") or ""), system=system)


def catalog() -> dict:
    """Cho trang Cài đặt: nhà cung cấp, model gợi ý, giọng."""
    return {k: {"label": p["label"], "default_model": p["default_model"], "voices": p["voices"],
                "key_field": p["key_field"]} for k, p in PROVIDERS.items()}
