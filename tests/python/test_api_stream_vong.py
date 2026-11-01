"""Bộ não API key hiện chữ lần lượt, kể cả lượt có dùng công cụ (0.438.5).

    python tests/run.py api_stream_vong     (không cần mạng: máy chủ giả chạy ở localhost)

Chủ repo 01/11/2026, sau khi Claude Code đã hiện chữ từng mẩu: "còn các apikey khác cũng phải như vậy",
"rất cần hiện những mẩu nhỏ như vậy". Trước đây mỗi vòng của vòng tool gọi model kiểu non-stream nên
câu trả lời chỉ hiện khi model viết xong. Test giữ:
- Chat Completions (OpenAI, OpenRouter, Gemini, Groq, DeepSeek, Ollama, OpenAI Compatible): chữ ra thành
  `delta` từng mẩu, lệnh gọi tool gom đúng từ các mảnh, `text` cuối mang cờ `streamed`;
- Anthropic Messages: text_delta ra từng mẩu, tool_use gom từ input_json_delta, khối thinking giữ nguyên;
- đường lui: endpoint từ chối stream, endpoint trả JSON thường, lỗi giữa luồng, rớt mạng trước chữ đầu;
- vòng đang ép gọi tool không hiện chữ xem trước; JAVIS_API_STREAM_TOOLS=0 tắt hẳn;
- dashboard hiện `delta` và không in lại câu đã hiện.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-asv-")
os.environ.pop("JAVIS_API_STREAM_TOOLS", None)

import engine  # noqa: E402

fails = []


def check(ten, ok, them=None):
    print(("ok   " if ok else "FAIL ") + ten + ("" if ok or them is None else f"  [{them}]"))
    if not ok:
        fails.append(ten)


SEEN = []          # thân request đã nhận
PLAN = []          # mỗi phần tử: hàm (handler, body) trả lời một request
DROP = {"n": 0}    # số request stream sẽ bị cắt kết nối không trả lời gì


def sse(h, events, anthropic=False):
    h.send_response(200)
    h.send_header("Content-Type", "text/event-stream")
    h.end_headers()
    for ev in events:
        if anthropic:
            h.wfile.write(f"event: {ev.get('type')}\n".encode())
        h.wfile.write(b"data: " + json.dumps(ev, ensure_ascii=False).encode() + b"\n\n")
    if not anthropic:
        h.wfile.write(b"data: [DONE]\n\n")


def js(h, code, obj):
    raw = json.dumps(obj, ensure_ascii=False).encode()
    h.send_response(code)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(raw)))
    h.end_headers()
    h.wfile.write(raw)


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if body.get("stream") and DROP["n"] > 0:
            DROP["n"] -= 1
            SEEN.append({"dropped": True})
            self.close_connection = True
            return   # không gửi gì: httpx thấy máy chủ ngắt kết nối (RemoteProtocolError)
        SEEN.append(body)
        PLAN.pop(0)(self, body)


_srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{_srv.server_address[1]}"
engine.OPENAI_URL = BASE + "/v1/chat/completions"
engine.ANTHROPIC_URL = BASE + "/v1/messages"

TOOLS = [{"fn": "tra_doanh_thu", "server": "javis", "name": "tra_doanh_thu", "description": "tra doanh thu",
          "schema": {"type": "object", "properties": {"ky": {"type": "string"}}}}]
CALLS = []


async def _call(args):
    CALLS.append(args)
    return "Doanh thu tuần: 12 triệu"


ROUTE = {"tra_doanh_thu": {"call": _call}}
ASK = [{"role": "user", "content": "tuần này bán sao rồi"}]


async def collect(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out


def deltas(evs):
    return [e["content"] for e in evs if e["type"] == "delta"]


def texts(evs):
    return [e for e in evs if e["type"] == "text"]


def cc(*chunks):
    return [{"id": "c1", "choices": [{"index": 0, "delta": d}]} for d in chunks]


def openai(evs_turn):
    return collect(engine.openai_chat_with_mcp("k", "gpt-test", ASK, "off", TOOLS, ROUTE))


async def run():
    # ─────────── 1. Chat Completions: chữ ra từng mẩu, tool gom từ mảnh ───────────
    PLAN[:] = [
        lambda h, b: sse(h, cc({"role": "assistant", "content": "Để em "}, {"content": "xem."},
                               {"tool_calls": [{"index": 0, "id": "t1", "type": "function",
                                                "function": {"name": "tra_doanh_thu", "arguments": "{\"ky\":"}}]},
                               {"tool_calls": [{"index": 0, "function": {"arguments": "\"tuan\"}"}}]})
                     + [{"id": "c1", "choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 9}}]),
        lambda h, b: sse(h, cc({"content": "Doanh thu "}, {"content": "tuần này "}, {"content": "12 triệu."})
                     + [{"id": "c2", "choices": [], "usage": {"prompt_tokens": 140, "completion_tokens": 6}}]),
    ]
    SEEN.clear()
    CALLS.clear()
    evs = await openai(None)
    check("chữ xem trước ra từng mẩu, có dòng trống giữa hai vòng",
          deltas(evs) == ["Để em ", "xem.", "\n\n", "Doanh thu ", "tuần này ", "12 triệu."], deltas(evs))
    check("tool chạy với tham số gom từ hai mảnh", CALLS == [{"ky": "tuan"}], CALLS)
    tc = [e for e in evs if e["type"] == "tool_call"]
    check("vẫn báo tool_call như cũ", [e.get("name") for e in tc] == ["tra_doanh_thu"])
    t = texts(evs)
    check("câu trả lời cuối là sự kiện text, mang cờ streamed",
          len(t) == 1 and t[0]["content"] == "Doanh thu tuần này 12 triệu." and t[0].get("streamed") is True, t)
    u = [e for e in evs if e["type"] == "usage"]
    check("token cộng dồn hai vòng", u and u[-1]["input"] == 240 and u[-1]["output"] == 15, u)
    check("mọi vòng xin stream kèm usage",
          len(SEEN) == 2 and all(s.get("stream") is True and s.get("stream_options") == {"include_usage": True}
                                 for s in SEEN))
    asst = [m for m in SEEN[1]["messages"] if m.get("role") == "assistant"][-1]
    check("vòng sau gửi lại đúng lệnh gọi tool (id, tên, tham số)",
          asst["tool_calls"][0]["id"] == "t1" and asst["tool_calls"][0]["function"]["name"] == "tra_doanh_thu"
          and json.loads(asst["tool_calls"][0]["function"]["arguments"]) == {"ky": "tuan"}, asst)
    check("kết quả tool về đúng id", any(m.get("role") == "tool" and m.get("tool_call_id") == "t1"
                                         for m in SEEN[1]["messages"]))

    # ─────────── 2. Kiểu Gemini: không có index, extra_content phải đi nguyên ───────────
    PLAN[:] = [
        lambda h, b: sse(h, cc({"tool_calls": [{"id": "g1", "type": "function",
                                                "function": {"name": "tra_doanh_thu", "arguments": "{}"},
                                                "extra_content": {"google": {"thought_signature": "sig"}}}]})),
        lambda h, b: sse(h, cc({"content": "Xong."})),
    ]
    SEEN.clear()
    evs = await openai(None)
    asst = [m for m in SEEN[1]["messages"] if m.get("role") == "assistant"][-1]
    check("lệnh gọi tool không có index vẫn gom được, extra_content giữ nguyên",
          asst["tool_calls"][0].get("extra_content") == {"google": {"thought_signature": "sig"}}
          and asst["tool_calls"][0]["id"] == "g1", asst)
    check("vòng đầu không có chữ thì không chèn dòng trống thừa", deltas(evs) == ["Xong."], deltas(evs))

    # ─────────── 3. Endpoint trả JSON thường dù đã xin stream ───────────
    PLAN[:] = [lambda h, b: js(h, 200, {"choices": [{"message": {"role": "assistant", "content": "Chào anh"}}],
                                        "usage": {"prompt_tokens": 5, "completion_tokens": 2}})]
    evs = await openai(None)
    t = texts(evs)
    check("trả JSON thường vẫn đọc được, cờ streamed tắt",
          len(t) == 1 and t[0]["content"] == "Chào anh" and not t[0].get("streamed") and not deltas(evs), evs)

    # ─────────── 4. Lỗi giữa luồng ───────────
    PLAN[:] = [lambda h, b: sse(h, [{"error": {"message": "Upstream overloaded", "code": 502}}])]
    evs = await openai(None)
    check("lỗi giữa luồng thành sự kiện error, không treo", [e for e in evs if e["type"] == "error"]
          and not texts(evs), evs)

    # ─────────── 5. Rớt mạng trước chữ đầu tiên thì gửi lại ───────────
    DROP["n"] = 1
    PLAN[:] = [lambda h, b: sse(h, cc({"content": "Ổn rồi."}))]
    SEEN.clear()
    evs = await openai(None)
    check("rớt mạng trước chữ đầu: gửi lại một lần và trả lời được",
          [s.get("dropped") for s in SEEN] == [True, None] and texts(evs) and texts(evs)[0]["content"] == "Ổn rồi.",
          SEEN)

    # ─────────── 6. Endpoint từ chối stream: lui về non-stream và nhớ ───────────
    engine._KHONG_STREAM_VONG.clear()
    PLAN[:] = [lambda h, b: js(h, 400, {"error": {"message": "stream mode is not supported with tools"}}),
               lambda h, b: js(h, 200, {"choices": [{"message": {"role": "assistant", "content": "Không stream"}}]}),
               lambda h, b: js(h, 200, {"choices": [{"message": {"role": "assistant", "content": "Lượt sau"}}]})]
    SEEN.clear()
    evs = await openai(None)
    check("từ chối stream: vẫn trả lời, request sau là non-stream",
          texts(evs) and texts(evs)[0]["content"] == "Không stream"
          and [s.get("stream") for s in SEEN] == [True, False], [s.get("stream") for s in SEEN])
    evs = await openai(None)
    check("lượt sau của cùng provider đi thẳng non-stream",
          [s.get("stream") for s in SEEN] == [True, False, False] and texts(evs)[0]["content"] == "Lượt sau")
    engine._KHONG_STREAM_VONG.clear()

    # ─────────── 7. Tắt bằng biến môi trường ───────────
    os.environ["JAVIS_API_STREAM_TOOLS"] = "0"
    PLAN[:] = [lambda h, b: js(h, 200, {"choices": [{"message": {"role": "assistant", "content": "Tắt"}}]})]
    SEEN.clear()
    evs = await openai(None)
    check("JAVIS_API_STREAM_TOOLS=0 thì gọi non-stream như cũ", SEEN[0].get("stream") is False and not deltas(evs))
    os.environ.pop("JAVIS_API_STREAM_TOOLS")

    # ─────────── 8. Anthropic Messages ───────────
    PLAN[:] = [
        lambda h, b: sse(h, [
            {"type": "message_start", "message": {"id": "m1", "usage": {"input_tokens": 50, "cache_read_input_tokens": 10,
                                                                         "output_tokens": 1}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Để em "}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "tra."}},
            {"type": "content_block_stop", "index": 0},
            {"type": "content_block_start", "index": 1,
             "content_block": {"type": "tool_use", "id": "tu1", "name": "tra_doanh_thu", "input": {}}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{\"ky\""}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": ":\"thang\"}"}},
            {"type": "content_block_stop", "index": 1},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 20}},
            {"type": "message_stop"}], anthropic=True),
        lambda h, b: sse(h, [
            {"type": "message_start", "message": {"id": "m2", "usage": {"input_tokens": 80, "output_tokens": 1}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "nghĩ"}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "SIG"}},
            {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Tháng này "}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "12 triệu."}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 9}},
            {"type": "message_stop"}], anthropic=True),
    ]
    SEEN.clear()
    CALLS.clear()
    evs = await collect(engine.anthropic_chat_with_mcp("sk-ant", "claude-test", ASK, "off", TOOLS, ROUTE))
    check("Anthropic: chữ ra từng mẩu, có dòng trống giữa hai vòng",
          deltas(evs) == ["Để em ", "tra.", "\n\n", "Tháng này ", "12 triệu."], deltas(evs))
    check("Anthropic: tool chạy với tham số gom từ input_json_delta", CALLS == [{"ky": "thang"}], CALLS)
    t = texts(evs)
    check("Anthropic: câu trả lời cuối mang cờ streamed",
          len(t) == 1 and t[0]["content"] == "Tháng này 12 triệu." and t[0].get("streamed") is True, t)
    u = [e for e in evs if e["type"] == "usage"]
    check("Anthropic: token cộng cả cache và hai vòng", u and u[-1]["input"] == 140 and u[-1]["output"] == 29, u)
    check("Anthropic: mọi vòng xin stream", len(SEEN) == 2 and all(s.get("stream") is True for s in SEEN))
    asst = [m for m in SEEN[1]["messages"] if m.get("role") == "assistant"][-1]["content"]
    check("Anthropic: vòng sau gửi lại nguyên khối, tool_use có input là dict, không lọt khoá nội bộ",
          [b["type"] for b in asst] == ["text", "tool_use"] and asst[1]["input"] == {"ky": "thang"}
          and "_json" not in asst[1] and asst[0]["text"] == "Để em tra.", asst)

    # Lỗi Anthropic giữa luồng (overloaded) thành error.
    PLAN[:] = [lambda h, b: sse(h, [{"type": "message_start", "message": {"id": "m3", "usage": {}}},
                                    {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}],
                                anthropic=True)]
    evs = await collect(engine.anthropic_chat_with_mcp("sk-ant", "claude-test", ASK, "off", TOOLS, ROUTE))
    check("Anthropic: lỗi giữa luồng thành error", [e for e in evs if e["type"] == "error"] and not texts(evs), evs)


asyncio.run(run())

# ─────────── 9. Gom chunk: tên lệnh lặp lại nguyên văn không bị nhân đôi ───────────
g = engine._GomCC()
g.them({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "a", "function": {"name": "tra", "arguments": ""}}]}}]})
g.them({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"name": "tra", "arguments": "{}"}}]}}]})
m = g.ket()["choices"][0]["message"]
check("tên lệnh lặp lại không bị nhân đôi", m["tool_calls"][0]["function"]["name"] == "tra", m)
check("không có chữ thì content là None như non-stream", m["content"] is None)

# ─────────── 10. Vòng ép gọi tool không hiện chữ xem trước ───────────
src = (ROOT / "server" / "engine.py").read_text(encoding="utf-8")
loop = src[src.find("async def _cc_tool_loop("):src.find("def _max_tool_rounds()")]
check("vòng đang ép gọi tool không stream", "stream_vong = stream_vong_bat(label) and not requirement_pending" in loop)

# ─────────── 11. Dashboard hiện delta, không in lại câu đã hiện ───────────
main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
i = main_src.find('elif ev["type"] == "delta":')
blk = main_src[i:i + 1400]
check("dashboard gửi delta thành khung stream, không cộng vào final_text",
      i > 0 and '"type": "stream", "content": ev["content"], "tts": False' in blk.split('elif ev["type"] == "text"')[0]
      and "final_text" not in blk.split('elif ev["type"] == "text"')[0].split("\n", 3)[-1])
check("text đã streamed thì không gửi lại", 'if not ev.get("streamed"):' in blk)

_srv.shutdown()
if fails:
    raise SystemExit(f"\nFAIL - test_api_stream_vong: {len(fails)} lỗi")
print("\nOK - test_api_stream_vong: tất cả pass")
