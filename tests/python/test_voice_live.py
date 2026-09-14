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

# ---- Gemini: tool bất đồng bộ chỉ trên 2.5, nối lại phiên, goAway ----
g31 = vl.GeminiLive("k", model="gemini-3.1-flash-live-preview")
g25 = vl.GeminiLive("k", model="gemini-2.5-flash-native-audio-preview-12-2025")
check("gemini 3.1: KHÔNG khai NON_BLOCKING (Google chưa hỗ trợ), 2.5: có",
      "behavior" not in g31.setup_message()["setup"]["tools"][0]["functionDeclarations"][0]
      and g25.setup_message()["setup"]["tools"][0]["functionDeclarations"][0]["behavior"] == "NON_BLOCKING")
check("gemini 2.5: kết quả tool có scheduling WHEN_IDLE, 3.1 thì không",
      g25.tool_result_messages("c", "ask_javis", "x")[0]["toolResponse"]["functionResponses"][0]["response"].get("scheduling") == "WHEN_IDLE"
      and "scheduling" not in g31.tool_result_messages("c", "ask_javis", "x")[0]["toolResponse"]["functionResponses"][0]["response"])
s31 = g31.setup_message()["setup"]
check("gemini: setup xin sessionResumption + nén ngữ cảnh", "sessionResumption" in s31 and "slidingWindow" in s31["contextWindowCompression"])
check("gemini: sessionResumptionUpdate lưu handle, không phát sự kiện",
      g31.translate({"sessionResumptionUpdate": {"newHandle": "H1", "resumable": True}}) == [] and g31.resume_handle == "H1")
check("gemini: setup lần sau mang handle cũ", g31.setup_message()["setup"]["sessionResumption"] == {"handle": "H1"})
ev = g31.translate({"goAway": {"timeLeft": "10s"}})
check("gemini: goAway -> goaway + wants_reconnect", ev[0]["type"] == "goaway" and g31.wants_reconnect is True)

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
# ---- OpenAI: response.create xếp hàng khi model đang nói; truncate đúng item ----
o2 = vl.OpenAIRealtime("KEY")
check("openai: response.created -> đang nói", o2.translate({"type": "response.created"}) == [] and o2.response_active is True)
tr2 = o2.tool_result_messages("c1", "ask_javis", "kq")
check("openai: kết quả tool lúc đang nói KHÔNG kèm response.create", [m["type"] for m in tr2] == ["conversation.item.create"])
check("openai: chưa done thì after_translate rỗng", o2.after_translate_messages() == [])
o2.translate({"type": "response.output_audio.delta", "delta": base64.b64encode(b"ab").decode(), "item_id": "item_9"})
check("openai: response.done -> turn_done và response.create xếp hàng được gửi",
      o2.translate({"type": "response.done"}) == [{"type": "turn_done"}]
      and o2.after_translate_messages() == [{"type": "response.create"}] and o2.after_translate_messages() == [])
check("openai: truncate đúng item audio gần nhất và số ms đã phát",
      o2.truncate_messages(1234) == [{"type": "conversation.item.truncate", "item_id": "item_9", "content_index": 0, "audio_end_ms": 1234}])
check("openai: chưa có audio thì không truncate", vl.OpenAIRealtime("KEY").truncate_messages(500) == [])
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
check("catalog: ba nhà cung cấp kèm giọng", set(cat) == {"gemini", "openai", "gpt-live"} and cat["gemini"]["voices"])

# ---- GPT-Live (song công, ủy nhiệm client) ----
gl = vl.GPTLive("KEY", voice="cedar")
check("gpt-live: url /v1/live/sessions, chỉ header Authorization",
      gl.url() == "wss://api.openai.com/v1/live/sessions" and gl.headers() == [("Authorization", "Bearer KEY")])
st = gl.setup_message()
check("gpt-live: session.start với model, pcm 24k, giọng, delegation client",
      st["type"] == "session.start" and st["session"]["model"] == "gpt-live-1"
      and st["session"]["audio"]["format"] == {"type": "audio/pcm", "rate": 24000}
      and st["session"]["audio"]["output"]["voice"] == "cedar" and st["session"]["delegation"] == {"type": "client"})
check("gpt-live: prompt hội thoại nói rõ khi nào giao việc", "delegate" in st["session"]["instructions"])
am = gl.audio_message(pcm)
check("gpt-live: audio append đã chuyển 24 kHz", am["type"] == "session.input_audio.append" and len(base64.b64decode(am["audio"])) == len(pcm) * 3 // 2)
check("gpt-live: session.started -> ready + giữ session id",
      gl.translate({"type": "session.started", "session": {"id": "ls_1"}}) == [{"type": "ready"}] and gl.session_id == "ls_1")
ev = gl.translate({"type": "session.input_transcript.delta", "delta": "doanh thu ", "start_ms": 0, "end_ms": 500})
ev += gl.translate({"type": "session.input_transcript.delta", "delta": "tháng này", "start_ms": 500, "end_ms": 900})
check("gpt-live: transcript người dùng cộng dồn, chưa final", ev[-1] == {"type": "transcript", "role": "user", "text": "doanh thu tháng này", "final": False})
ev = gl.translate({"type": "session.delegation.created", "delegation": {"id": "item_d1", "target": "client", "type": "delegation"}, "offset_ms": 900})
check("gpt-live: delegation client -> chốt câu user + tool_call ask_javis với câu vừa nói",
      ev[0] == {"type": "transcript", "role": "user", "text": "doanh thu tháng này", "final": True}
      and ev[1]["type"] == "tool_call" and ev[1]["id"] == "item_d1" and ev[1]["args"]["request"] == "doanh thu tháng này")
check("gpt-live: delegation responses bị bỏ qua", gl.translate({"type": "session.delegation.created", "delegation": {"id": "x", "target": "responses"}}) == [])
check("gpt-live: đang chạy -> thinking.append kèm delegation_id",
      gl.tool_running_messages("item_d1", "ask_javis")[0]["type"] == "session.thinking.append"
      and gl.tool_running_messages("item_d1", "ask_javis")[0]["delegation_id"] == "item_d1")
res = gl.tool_result_messages("item_d1", "ask_javis", "Doanh thu 120 triệu")
check("gpt-live: kết quả -> commentary.append (model tự nói), cắt 500 token",
      res == [{"type": "session.commentary.append", "delegation_id": "item_d1", "content": "Doanh thu 120 triệu"}]
      and len(gl.tool_result_messages("d", "ask_javis", "x" * 5000)[0]["content"]) == vl.GPT_LIVE_APPEND_MAX)
check("gpt-live: ngữ cảnh giao diện -> thinking.append không delegation",
      gl.context_messages("[NGỮ CẢNH GIAO DIỆN: trang=work]") == [{"type": "session.thinking.append", "delegation_id": None, "content": "[NGỮ CẢNH GIAO DIỆN: trang=work]"}]
      and gl.context_messages("") == [])
ev = gl.translate({"type": "session.output_transcript.delta", "delta": "Để mình xem", "start_ms": 0, "end_ms": 1})
check("gpt-live: chữ trợ lý", ev[-1] == {"type": "transcript", "role": "assistant", "text": "Để mình xem", "final": False})
check("gpt-live: audio delta", gl.translate({"type": "session.output_audio.delta", "delta": base64.b64encode(b"zz").decode()})[-1] == {"type": "audio", "data": b"zz"})
ev = gl.translate({"type": "session.input_transcript.delta", "delta": "ok"})
check("gpt-live: người dùng nói khi trợ lý đang có chữ dở -> turn_done trước", ev[0] == {"type": "turn_done"})
check("gpt-live: chữ gõ tay -> instructions.append", gl.text_message("xin chào")["type"] == "session.instructions.append")
check("gpt-live: đóng phiên gửi session.close", gl.close_messages() == [{"type": "session.close"}])
check("gpt-live: session.closed vì expired -> error, close_requested thì không",
      any(e["type"] == "error" for e in gl.translate({"type": "session.closed", "reason": "expired"}))
      and not any(e["type"] == "error" for e in gl.translate({"type": "session.closed", "reason": "close_requested"})))
check("gpt-live: sự kiện lạ -> rỗng", gl.translate({"type": "session.usage.updated"}) == [])
check("make_provider: gpt-live dùng key openai",
      isinstance(vl.make_provider({"voice": {"live_provider": "gpt-live"}, "model": {"openai_api_key": "k"}}), vl.GPTLive))

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - voice_live")
