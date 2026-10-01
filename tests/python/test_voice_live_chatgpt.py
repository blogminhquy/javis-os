"""Nhà cung cấp ChatGPT Live (voice_live.ChatGPTLive, 0.65.17).

    python tests/run.py voice_live_chatgpt

Không chạy Codex thật: AppServer giả ghi lại request và cho đẩy thông báo vào hàng đợi.
Khoá:
  - thread/start: ephemeral, sandbox read-only, không duyệt quyền, thư mục tạm rỗng;
  - realtime/start: v3, webrtc, includeStartupContext=false (không cho Codex soi máy), giọng
    mặc định juniper, handoff do client lo, lịch sử chat vào initialItems, bộ nhớ vào prompt;
  - answer SDP về qua thông báo thread/realtime/sdp;
  - dịch thông báo: lời người dùng nháp/chốt, lời Javis, turn_done, handoff thành ask_javis
    (yêu cầu quá ngắn ghép câu vừa nói), lượt Codex tự mở bị interrupt;
  - kết quả bộ não đi appendSpeech đã lột markdown, ngắn; chữ gõ đi appendText;
  - make_provider chọn chatgpt không cần key, chưa nối ChatGPT thì báo lỗi dễ hiểu;
  - nhãn hiện ra là "ChatGPT Live", không có chữ "song công".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-chatgptlive-"))

import codex_realtime  # noqa: E402
import voice_live  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


class FakeServer:
    def __init__(self):
        self.calls = []
        self.queue = None
        self.unsubscribed = []

    async def request(self, method, params=None, timeout=30.0):
        self.calls.append((method, params or {}))
        if method == "thread/start":
            return {"thread": {"id": "th-9"}}
        return {}

    def subscribe(self, thread_id):
        self.queue = asyncio.Queue()
        return self.queue

    def unsubscribe(self, thread_id):
        self.unsubscribed.append(thread_id)

    def push(self, method, **params):
        params.setdefault("threadId", "th-9")
        self.queue.put_nowait({"method": method, "params": params})


def call(fake, method):
    return [p for m, p in fake.calls if m == method]


async def collect(prov, n, timeout=2.0):
    out = []
    agen = prov.events()
    try:
        while len(out) < n:
            out.append(await asyncio.wait_for(agen.__anext__(), timeout))
    except (asyncio.TimeoutError, StopAsyncIteration):
        pass
    return out


async def main():
    fake = FakeServer()

    async def getter():
        return fake

    prov = voice_live.ChatGPTLive(memory_index="- Chủ dự án xưng anh, gọi Javis là em.",
                                  app_server_getter=getter)
    check("transport của ChatGPT Live là webrtc", prov.transport == "webrtc")
    check("giọng mặc định juniper", prov.voice == "juniper")
    await prov.connect()
    ts = call(fake, "thread/start")[0]
    check("thread/start: ephemeral, read-only, không duyệt quyền",
          ts.get("ephemeral") is True and ts.get("sandbox") == "read-only" and ts.get("approvalPolicy") == "never")
    check("thread/start: thư mục làm việc tạm và rỗng",
          os.path.isdir(ts.get("cwd", "")) and not os.listdir(ts["cwd"]))
    check("thread/start: lượt Codex lỡ chạy chỉ được trả [FINAL]",
          "[FINAL]" in str(ts.get("developerInstructions")))

    await prov.restore_history([
        {"role": "user", "content": "Doanh thu hôm qua bao nhiêu?"},
        {"role": "assistant", "content": "Hôm qua 11 triệu."},
        {"role": "system", "content": "bỏ qua"},
    ])

    events_task = asyncio.ensure_future(collect(prov, 0, timeout=0.01))
    await events_task

    # start_webrtc chờ answer từ thông báo sdp; events() phải đang chạy để nhận nó
    agen = prov.events()
    reader = asyncio.ensure_future(agen.__anext__())
    starter = asyncio.ensure_future(prov.start_webrtc("v=0 offer"))
    await asyncio.sleep(0.05)
    fake.push("thread/realtime/started", version="v3")
    fake.push("thread/realtime/sdp", sdp="v=0 answer")
    answer = await asyncio.wait_for(starter, 2)
    check("answer SDP lấy từ thông báo thread/realtime/sdp", answer == "v=0 answer")
    rs = call(fake, "thread/realtime/start")[0]
    check("realtime/start: v3, audio, webrtc mang offer",
          rs.get("version") == "v3" and rs.get("outputModality") == "audio"
          and rs.get("transport") == {"type": "webrtc", "sdp": "v=0 offer"})
    check("realtime/start: KHÔNG cho Codex soi máy (includeStartupContext=false)", rs.get("includeStartupContext") is False)
    check("realtime/start: handoff do Javis lo", rs.get("clientManagedHandoffs") is True)
    check("realtime/start: giọng juniper", rs.get("voice") == "juniper")
    check("realtime/start: lịch sử chat vào initialItems (bỏ tin system)",
          rs.get("initialItems") == [{"role": "user", "text": "Doanh thu hôm qua bao nhiêu?"},
                                     {"role": "assistant", "text": "Hôm qua 11 triệu."}])
    check("realtime/start: bộ nhớ vào prompt", "xưng anh" in rs.get("prompt", ""))

    # dịch thông báo
    fake.push("thread/realtime/transcript/delta", role="user", delta="Doanh thu")
    fake.push("thread/realtime/transcript/delta", role="user", delta=" hôm nay")
    fake.push("thread/realtime/transcript/done", role="user", text="Doanh thu hôm nay")
    fake.push("thread/realtime/transcript/delta", role="assistant", delta="Để em xem nhé.")
    fake.push("thread/realtime/transcript/done", role="assistant", text="Để em xem nhé.")
    evs = [await asyncio.wait_for(reader, 2)]
    for _ in range(4):
        evs.append(await asyncio.wait_for(agen.__anext__(), 2))
    check("lời người dùng nháp rồi chốt",
          evs[0] == {"type": "transcript", "role": "user", "text": "Doanh thu", "final": False}
          and evs[1]["text"] == "Doanh thu hôm nay" and evs[1]["final"] is False
          and evs[2] == {"type": "transcript", "role": "user", "text": "Doanh thu hôm nay", "final": True})
    check("lời Javis rồi turn_done",
          evs[3]["role"] == "assistant" and evs[3]["text"] == "Để em xem nhé." and evs[4] == {"type": "turn_done"})

    fake.push("thread/realtime/itemAdded", item={"type": "handoff_request", "handoff_id": "h1",
                                                 "input_transcript": "Doanh thu hôm nay của cửa hàng là bao nhiêu"})
    ev = await asyncio.wait_for(agen.__anext__(), 2)
    check("handoff thành tool_call ask_javis mang yêu cầu",
          ev["type"] == "tool_call" and ev["name"] == "ask_javis" and ev["id"] == "h1"
          and ev["args"]["request"] == "Doanh thu hôm nay của cửa hàng là bao nhiêu")

    fake.push("thread/realtime/transcript/done", role="user", text="Mở dashboard Facebook Ads cho anh")
    await asyncio.wait_for(agen.__anext__(), 2)
    fake.push("thread/realtime/itemAdded", item={"type": "handoff_request", "handoff_id": "h2", "input_transcript": "cho anh"})
    ev = await asyncio.wait_for(agen.__anext__(), 2)
    check("handoff quá ngắn ghép câu người dùng vừa nói",
          "Mở dashboard Facebook Ads" in ev["args"]["request"])

    fake.push("turn/started", turn={"id": "turn-7"})
    fake.push("thread/realtime/transcript/delta", role="assistant", delta="x")
    await asyncio.wait_for(agen.__anext__(), 2)
    await asyncio.sleep(0.05)
    check("lượt Codex tự mở bị turn/interrupt ngay",
          call(fake, "turn/interrupt") == [{"threadId": "th-9", "turnId": "turn-7"}])

    await prov.send_tool_result("h1", "ask_javis",
                                "## Doanh thu\n\n| Ngày | Tiền |\n|---|---|\n| Hôm nay | **12.500.000** |\n\nTăng [8%](http://x) so với hôm qua. " + "Rất dài. " * 200)
    sp = call(fake, "thread/realtime/appendSpeech")[0]
    check("kết quả đi appendSpeech, đã lột markdown",
          "##" not in sp["text"] and "**" not in sp["text"] and "](" not in sp["text"] and "12.500.000" in sp["text"])
    check("kết quả nói ra không quá 600 ký tự", len(sp["text"]) <= 600)

    await prov.send_text("Mở trang kết nối")
    check("chữ gõ đi appendText", call(fake, "thread/realtime/appendText") == [{"threadId": "th-9", "text": "Mở trang kết nối"}])

    fake.push("thread/realtime/closed", reason="server_error")
    ev = await asyncio.wait_for(agen.__anext__(), 2)
    check("phiên bị ngắt ngoài ý muốn thì báo lỗi", ev["type"] == "error")

    await prov.close()
    check("đóng: realtime/stop và huỷ đăng ký", bool(call(fake, "thread/realtime/stop")) and fake.unsubscribed == ["th-9"])

    # lỗi realtime trước khi có answer
    fake2 = FakeServer()

    async def getter2():
        return fake2
    p2 = voice_live.ChatGPTLive(app_server_getter=getter2)
    await p2.connect()
    g2 = p2.events()
    r2 = asyncio.ensure_future(g2.__anext__())
    st2 = asyncio.ensure_future(p2.start_webrtc("offer"))
    await asyncio.sleep(0.05)
    fake2.push("thread/realtime/error", message="thread does not support realtime conversation")
    try:
        await asyncio.wait_for(st2, 2)
        check("lỗi realtime trước answer làm start_webrtc ném lỗi", False)
    except Exception as e:
        check("lỗi realtime trước answer làm start_webrtc ném lỗi", "realtime" in str(e))
    r2.cancel()
    await p2.close()


asyncio.run(main())

# make_provider và nhãn
codex_realtime._find_cli = lambda: "codex-fake"
p = voice_live.make_provider({"voice": {"live_provider": "chatgpt", "chatgpt_voice": "maple"},
                              "model": {"openai_oauth": {"refresh_token": "r"}}}, memory_index="mem")
check("make_provider: chatgpt không cần API key", isinstance(p, voice_live.ChatGPTLive) and p.voice == "maple")
p = voice_live.make_provider({"voice": {"live_provider": "chatgpt", "chatgpt_voice": "marin"},
                              "model": {"openai_oauth": {"refresh_token": "r"}}})
check("make_provider: giọng không hợp lệ cho v3 thì về juniper", p.voice == "juniper")
codex_realtime._codex_logged_in = lambda: False
try:
    voice_live.make_provider({"voice": {"live_provider": "chatgpt"}, "model": {}})
    check("chưa nối ChatGPT thì báo lỗi dễ hiểu", False)
except RuntimeError as e:
    check("chưa nối ChatGPT thì báo lỗi dễ hiểu", "ChatGPT" in str(e) and "Models" in str(e))
cat = voice_live.catalog()
check("catalog có ChatGPT Live, transport webrtc, 9 giọng",
      cat["chatgpt"]["label"].startswith("ChatGPT Live") and cat["chatgpt"]["transport"] == "webrtc"
      and len(cat["chatgpt"]["voices"]) == 9 and cat["gemini"]["transport"] == "pcm")
check("không nhãn nhà cung cấp nào ghi 'song công'",
      not any("song công" in v["label"].lower() for v in cat.values()))

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - ChatGPT Live provider")
