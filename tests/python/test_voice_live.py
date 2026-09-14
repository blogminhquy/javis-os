"""Nhà cung cấp nghe nói thẳng (server/voice_live.py) - Voice V2 bậc Live.

    python tests/run.py voice_live

Không chạm mạng: chỉ test hàm THUẦN dựng và dịch thông điệp của hai nhà cung cấp, chuyển mẫu
16k -> 24k, và make_provider đọc cài đặt. Thêm nhà cung cấp thứ ba thì thêm một khối ở đây.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import array
import base64
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-vlive-"))

import voice_live as vl  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- resample ----
src = array.array("h", [0, 1000, 2000, 3000])
out = array.array("h")
out.frombytes(vl.resample_16k_to_24k(src.tobytes()))
check("resample: 4 mẫu -> 6 mẫu", len(out) == 6)
check("resample: nội suy tuyến tính đúng", list(out) == [0, 666, 1333, 2000, 2666, 3000] or list(out)[:2] == [0, 666])
check("resample: rỗng -> rỗng", vl.resample_16k_to_24k(b"") == b"")
check("resample: byte lẻ bị bỏ, không nổ, ra số byte chẵn", len(vl.resample_16k_to_24k(b"\x00\x01\x02")) % 2 == 0)

pcm = array.array("h", [100] * 160).tobytes()

# ---- Gemini ----
g = vl.GeminiLive("KEY", model="gemini-x", voice="Kore")
check("gemini: url mang key", "BidiGenerateContent?key=KEY" in g.url())
s = g.setup_message()["setup"]
check("gemini: setup model có tiền tố models/", s["model"] == "models/gemini-x")
check("gemini: setup AUDIO + giọng + tool ask_javis + transcription hai chiều",
      s["generationConfig"]["responseModalities"] == ["AUDIO"]
      and s["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"
      and s["tools"][0]["functionDeclarations"][0]["name"] == "ask_javis"
      and "inputAudioTranscription" in s and "outputAudioTranscription" in s)
a = g.audio_message(pcm)["realtimeInput"]["audio"]
check("gemini: audio 16 kHz base64", a["mimeType"] == "audio/pcm;rate=16000" and base64.b64decode(a["data"]) == pcm)
check("gemini: text turnComplete", g.text_message("hi")["clientContent"]["turnComplete"] is True)
tr = g.tool_result_messages("c1", "ask_javis", "kết quả")[0]["toolResponse"]["functionResponses"][0]
check("gemini: tool result đúng id/name/output", tr == {"id": "c1", "name": "ask_javis", "response": {"output": "kết quả"}})
evs = g.translate({"serverContent": {"modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": base64.b64encode(b"\x01\x02").decode()}}]},
                                     "inputTranscription": {"text": "xin chào", "finished": True}, "turnComplete": True}})
check("gemini: dịch audio + transcript user final + turn_done",
      [e["type"] for e in evs] == ["audio", "transcript", "turn_done"] and evs[0]["data"] == b"\x01\x02"
      and evs[1]["role"] == "user" and evs[1]["final"] is True)
evs = g.translate({"serverContent": {"interrupted": True}})
check("gemini: interrupted", evs == [{"type": "interrupted"}])
evs = g.translate({"serverContent": {"modelTurn": {"parts": [{"text": "xin chào"}]}, "outputTranscription": {"text": "xin chào"}}})
check("gemini: chữ trợ lý chỉ phát MỘT lần (từ outputTranscription, bỏ modelTurn.text)",
      [e for e in evs if e["type"] == "transcript"] == [{"type": "transcript", "role": "assistant", "text": "xin chào", "final": False}])
evs = g.translate({"toolCall": {"functionCalls": [{"id": "f1", "name": "ask_javis", "args": {"request": "doanh thu"}}]}})
check("gemini: tool_call", evs[0]["type"] == "tool_call" and evs[0]["args"]["request"] == "doanh thu")
check("gemini: setupComplete -> ready", g.translate({"setupComplete": {}}) == [{"type": "ready"}])
check("gemini: mặc định model/voice từ PROVIDERS", vl.GeminiLive("k").model == vl.PROVIDERS["gemini"]["default_model"])

# ---- OpenAI ----
o = vl.OpenAIRealtime("KEY", model="gpt-realtime", voice="marin")
check("openai: url model + KHÔNG còn header beta (API GA)", "model=gpt-realtime" in o.url()
      and all(h[0] != "OpenAI-Beta" for h in o.headers()) and ("Authorization", "Bearer KEY") in o.headers())
s = o.setup_message()
au = s["session"]["audio"]
check("openai: session.update khuôn GA: type realtime, audio.input/output pcm 24k, server_vad, tool, voice",
      s["type"] == "session.update" and s["session"]["type"] == "realtime" and s["session"]["output_modalities"] == ["audio"]
      and au["input"]["format"] == {"type": "audio/pcm", "rate": 24000} and au["output"]["format"]["rate"] == 24000
      and au["input"]["turn_detection"]["type"] == "server_vad"
      and s["session"]["tools"][0]["name"] == "ask_javis" and au["output"]["voice"] == "marin")
am = o.audio_message(pcm)
check("openai: audio append đã chuyển sang 24 kHz (dài gấp 1,5)", am["type"] == "input_audio_buffer.append"
      and len(base64.b64decode(am["audio"])) == len(pcm) * 3 // 2)
tr = o.tool_result_messages("c9", "ask_javis", "kq")
check("openai: tool result = function_call_output + response.create",
      tr[0]["item"]["type"] == "function_call_output" and tr[0]["item"]["call_id"] == "c9" and tr[1]["type"] == "response.create")
check("openai: interrupt = response.cancel", o.interrupt_messages() == [{"type": "response.cancel"}])
check("openai: audio delta (tên GA lẫn tên cũ)",
      o.translate({"type": "response.output_audio.delta", "delta": base64.b64encode(b"ab").decode()}) == [{"type": "audio", "data": b"ab"}]
      and o.translate({"type": "response.audio.delta", "delta": base64.b64encode(b"ab").decode()}) == [{"type": "audio", "data": b"ab"}])
check("openai: transcript trợ lý delta (tên GA)",
      o.translate({"type": "response.output_audio_transcript.delta", "delta": "hi"}) == [{"type": "transcript", "role": "assistant", "text": "hi", "final": False}])
check("openai: speech_started -> interrupted", o.translate({"type": "input_audio_buffer.speech_started"}) == [{"type": "interrupted"}])
ev = o.translate({"type": "response.function_call_arguments.done", "call_id": "c2", "name": "ask_javis", "arguments": json.dumps({"request": "x"})})
check("openai: function call args parse JSON", ev[0]["type"] == "tool_call" and ev[0]["args"] == {"request": "x"} and ev[0]["id"] == "c2")
check("openai: transcript user completed final", o.translate({"type": "conversation.item.input_audio_transcription.completed", "transcript": "hi"})[0]["final"] is True)
check("openai: response.done -> turn_done", o.translate({"type": "response.done"}) == [{"type": "turn_done"}])
check("openai: error có message", o.translate({"type": "error", "error": {"message": "bad"}}) == [{"type": "error", "message": "bad"}])
check("openai: sự kiện lạ -> rỗng", o.translate({"type": "rate_limits.updated"}) == [])

# ---- make_provider ----
err = ""
try:
    vl.make_provider({"voice": {"live_provider": "gemini"}, "model": {}})
except RuntimeError as e:
    err = str(e)
check("make_provider: thiếu key -> nhắc trang Models", "Models" in err)
p = vl.make_provider({"voice": {"live_provider": "openai", "live_model": "gpt-realtime-mini", "live_voice": "cedar"},
                      "model": {"openai_api_key": "sk"}})
check("make_provider: openai đúng model/giọng", isinstance(p, vl.OpenAIRealtime) and p.model == "gpt-realtime-mini" and p.voice == "cedar")
err = ""
try:
    vl.make_provider({"voice": {"live_provider": "xai"}, "model": {}})
except RuntimeError as e:
    err = str(e)
check("make_provider: provider lạ -> liệt kê provider có", "gemini" in err and "openai" in err)
cat = vl.catalog()
check("catalog: hai nhà cung cấp kèm giọng", set(cat) == {"gemini", "openai"} and cat["gemini"]["voices"])

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - voice_live")
