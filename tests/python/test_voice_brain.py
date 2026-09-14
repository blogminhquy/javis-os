"""Bộ não giọng nói riêng (server/voice_brain.py) - Voice V2 làn nhanh.

    python tests/run.py voice_brain

Không chạm mạng, không mở agy thật: tiến trình Antigravity được tiêm giả qua `spawn`, còn
bộ não API nhận `stream_fn` giả. Khoá:
  1. parse_marker: có/không marker, câu chờ đứng trước, marker giữa dòng thừa vẫn bắt được.
  2. build_messages: system trước, cắt HISTORY_N lượt gần nhất, role lạ thành user.
  3. Antigravity: khuôn stdin `{"event":"user","message":{"role","content"}}` đúng từng byte, lượt
     đầu ghép hướng dẫn + lịch sử, lượt sau chỉ câu; stream text_delta; result ERROR ném lỗi;
     tiến trình chết giữa chừng -> lỗi rõ và lần sau tự mở lại.
  4. Sổ phiên: cùng sid dùng lại, đổi model thì dựng lại; thiếu key API -> lỗi câu người hiểu.
  5. main.py có nhánh voice: payload.voice + mode fast -> run_voice_turn; /stt; /ws/voice-live.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-vbrain-"))

import voice_brain as vb  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. marker ----
f, a = vb.parse_marker("Để mình xem.\nJAVIS_ASK_MAIN: doanh thu hôm nay bao nhiêu\n")
check("marker: câu chờ + yêu cầu", f == "Để mình xem." and a == "doanh thu hôm nay bao nhiêu")
f, a = vb.parse_marker("Hai cộng hai bằng bốn.")
check("không marker: yêu cầu None, chữ giữ nguyên", a is None and f == "Hai cộng hai bằng bốn.")
f, a = vb.parse_marker("JAVIS_ASK_MAIN: mở Chrome")
check("marker không câu chờ: filler rỗng", f == "" and a == "mở Chrome")
f, a = vb.parse_marker("  JAVIS_ASK_MAIN:   có khoảng trắng  \nchữ thừa sau")
check("marker có khoảng trắng: vẫn bắt, cắt gọn", a == "có khoảng trắng")

# ---- 2. build_messages ----
hist = [{"role": "user", "content": f"u{i}"} for i in range(30)]
msgs = vb.build_messages(hist, "câu mới")
check("build_messages: system đầu, câu mới cuối", msgs[0]["role"] == "system" and msgs[-1] == {"role": "user", "content": "câu mới"})
check("build_messages: cắt còn HISTORY_N lượt", len(msgs) == vb.HISTORY_N + 2)
msgs = vb.build_messages([{"role": "tool", "content": "x"}, {"role": "assistant", "content": ""}], "q")
check("build_messages: role lạ -> user, nội dung rỗng bị bỏ", len(msgs) == 3 and msgs[1]["role"] == "user")


# ---- 3. Antigravity với tiến trình giả ----
class FakeStdin:
    def __init__(self):
        self.lines = []
        self.closed = False

    def write(self, b):
        self.lines.append(b.decode("utf-8"))

    async def drain(self):
        pass

    def close(self):
        self.closed = True


class FakeStdout:
    def __init__(self, script):
        self.script = list(script)   # list of lists of lines per turn

    async def readline(self):
        if not self.script:
            return b""
        cur = self.script[0]
        if not cur:
            self.script.pop(0)
            return b"" if not self.script else await self.readline()
        return (json.dumps(cur.pop(0), ensure_ascii=False) + "\n").encode("utf-8")


class FakeProc:
    def __init__(self, script):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(script)
        self.returncode = None
        self.killed = False

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


def _turn(deltas, status="SUCCESS", response="", error=""):
    ev = [{"event": "step_update", "step_update": {"step_type": "agent_response", "state": "ACTIVE", "text_delta": d}} for d in deltas]
    ev.append({"event": "result", "result": {"status": status, "response": response, "error": error}})
    return ev


async def main():
    procs = []

    async def spawn(args):
        p = FakeProc([_turn(["Xin ", "chào."]), _turn([], response="Trả nguyên câu."), _turn([], status="ERROR", error="hết hạn mức")])
        p.args = args
        procs.append(p)
        return p

    b = vb.AntigravityVoiceBrain(model="gemini-3.8-flash-low", spawn=spawn)
    out = ""
    async for d in b.stream("Chào Javis", [{"role": "user", "content": "trước đó"}, {"role": "assistant", "content": "ừ"}]):
        out += d
    check("agy: stream ghép text_delta", out == "Xin chào.")
    check("agy: args có --input-format stream-json + model", "--input-format" in procs[0].args and "gemini-3.8-flash-low" in procs[0].args)
    first = json.loads(procs[0].stdin.lines[0])
    check("agy: khuôn stdin event=user, message.role=user", first["event"] == "user" and first["message"]["role"] == "user")
    check("agy: lượt đầu ghép hướng dẫn + lịch sử + câu", "HƯỚNG DẪN" in first["message"]["content"]
          and "trước đó" in first["message"]["content"] and first["message"]["content"].endswith("Chào Javis"))
    out = ""
    async for d in b.stream("Câu hai", []):
        out += d
    second = json.loads(procs[0].stdin.lines[1])
    check("agy: lượt sau chỉ gửi câu", second["message"]["content"] == "Câu hai")
    check("agy: không có text_delta thì lấy result.response", out == "Trả nguyên câu.")
    err = ""
    try:
        async for d in b.stream("Câu ba", []):
            pass
    except RuntimeError as e:
        err = str(e)
    check("agy: result ERROR -> RuntimeError mang lý do", "hết hạn mức" in err)
    # tiến trình chết (stdout hết) -> lỗi rõ, lần sau spawn lại
    err = ""
    try:
        async for d in b.stream("Câu bốn", []):
            pass
    except RuntimeError as e:
        err = str(e)
    check("agy: tiến trình đóng giữa chừng -> lỗi rõ", "đóng tiến trình" in err and procs[0].killed)
    out = ""
    async for d in b.stream("Câu năm", []):
        out += d
    check("agy: sau khi chết tự mở tiến trình mới và mồi lại", len(procs) == 2 and "HƯỚNG DẪN" in json.loads(procs[1].stdin.lines[0])["message"]["content"])
    await b.close()

    # ---- bộ não API với stream giả ----
    async def fake_stream(key, model, messages, reasoning="off"):
        assert key == "k" and model == "m" and messages[0]["role"] == "system"
        yield {"type": "text", "content": "A"}
        yield {"type": "usage", "input": 1, "output": 1}
        yield {"type": "text", "content": "B"}

    api = vb.ApiVoiceBrain("groq", "k", "m", stream_fn=fake_stream)
    out = "".join([d async for d in api.stream("q", [])])
    check("api: chỉ lấy sự kiện text", out == "AB")

    async def err_stream(key, model, messages, reasoning="off"):
        yield {"type": "error", "content": "Groq 429"}

    api2 = vb.ApiVoiceBrain("groq", "k", "m", stream_fn=err_stream)
    err = ""
    try:
        [d async for d in api2.stream("q", [])]
    except RuntimeError as e:
        err = str(e)
    check("api: sự kiện error -> RuntimeError", "429" in err)

    # ---- 4. sổ phiên ----
    conf = vb.config_from_settings({"voice": {"mode": "fast", "brain_provider": "groq", "brain_model": "m1"},
                                    "model": {"groq_api_key": "gk"}})
    check("config_from_settings: lấy đúng key theo provider", conf == {"mode": "fast", "provider": "groq", "model": "m1", "api_key": "gk"})
    b1 = await vb.get_brain("s1", conf)
    b2 = await vb.get_brain("s1", conf)
    check("get_brain: cùng phiên dùng lại", b1 is b2 and vb.active_count() == 1)
    b3 = await vb.get_brain("s1", dict(conf, model="m2"))
    check("get_brain: đổi model thì dựng lại", b3 is not b1 and b3.model == "m2")
    err = ""
    try:
        await vb.get_brain("s2", {"provider": "gemini", "model": "", "api_key": ""})
    except RuntimeError as e:
        err = str(e)
    check("get_brain: thiếu key -> câu lỗi nhắc trang Models", "Models" in err)
    err = ""
    try:
        await vb.get_brain("s3", {"provider": "", "model": "", "api_key": ""})
    except RuntimeError as e:
        err = str(e)
    check("get_brain: chưa chọn provider -> lỗi rõ", "Chưa chọn" in err)
    await vb.close_all()
    check("close_all dọn sạch", vb.active_count() == 0)

    # ---- 4b. Ba bộ não trên gói (Voice V3, spec mục 13) ----
    for k in ("codex", "claude", "grok"):
        check(f"BRAIN_PROVIDERS có {k} chạy trên gói (key_field rỗng)",
              k in vb.BRAIN_PROVIDERS and vb.BRAIN_PROVIDERS[k]["key_field"] == "" and k not in vb.PROVIDERS)

    # Codex: creds giả + stream giả, kiểm đúng token/account/model/messages đi xuống
    seen = {}

    async def fake_codex(token, account, model, messages, reasoning="off"):
        seen.update(token=token, account=account, model=model, system=messages[0]["content"], last=messages[-1]["content"])
        yield {"type": "meta", "model": model}
        yield {"type": "text", "content": "Ừ, "}
        yield {"type": "text", "content": "được."}

    cx = vb.CodexVoiceBrain(model="gpt-x", creds_fn=lambda: {"access_token": "tk", "account_id": "acc"}, stream_fn=fake_codex)
    out = "".join([d async for d in cx.stream("chào", [{"role": "user", "content": "trước đó"}])])
    check("codex: gom text delta", out == "Ừ, được.")
    check("codex: token, account, model, system prompt giọng và câu cuối đi đúng",
          seen["token"] == "tk" and seen["account"] == "acc" and seen["model"] == "gpt-x"
          and seen["system"] == vb.SYSTEM_PROMPT and seen["last"] == "chào")
    cx2 = vb.CodexVoiceBrain(creds_fn=lambda: None, stream_fn=fake_codex)
    err = ""
    try:
        [d async for d in cx2.stream("q", [])]
    except RuntimeError as e:
        err = str(e)
    check("codex: chưa kết nối OAuth -> lỗi nhắc trang Models", "Models" in err)

    async def codex_limit(token, account, model, messages, reasoning="off"):
        yield {"type": "limit_exceeded", "provider": "ChatGPT"}

    err = ""
    try:
        [d async for d in vb.CodexVoiceBrain(creds_fn=lambda: {"access_token": "t"}, stream_fn=codex_limit).stream("q", [])]
    except RuntimeError as e:
        err = str(e)
    check("codex: hết hạn mức -> RuntimeError rõ", "hạn mức" in err)

    # Claude: client giả cùng khuôn ClaudeSDKClient (query/receive_response/disconnect), message giả
    # nhận diện bằng TÊN LỚP như claude_pieces.
    class StreamEvent:
        def __init__(self, text): self.event = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}

    class TextBlock:
        def __init__(self, text): self.text = text

    class AssistantMessage:
        def __init__(self, text): self.content = [TextBlock(text)]

    class ResultMessage:
        def __init__(self, is_error=False, result=""): self.is_error = is_error; self.result = result

    class FakeClient:
        def __init__(self, script):
            self.script = list(script); self.queries = []; self.disconnected = False

        async def query(self, text): self.queries.append(text)

        async def receive_response(self):
            for m in self.script.pop(0):
                yield m

        async def disconnect(self): self.disconnected = True

    made = []

    async def factory():
        c = FakeClient([[StreamEvent("Xin "), StreamEvent("chào."), AssistantMessage("Xin chào."), ResultMessage()],
                        [AssistantMessage("Không stream."), ResultMessage()],
                        [ResultMessage(is_error=True, result="hết hạn mức")]])
        made.append(c)
        return c

    cl = vb.ClaudeVoiceBrain(model="haiku", client_factory=factory)
    out = "".join([d async for d in cl.stream("chào", [{"role": "assistant", "content": "trước đó"}])])
    check("claude: stream delta, KHÔNG lặp lại AssistantMessage", out == "Xin chào.")
    check("claude: lượt đầu mồi lịch sử, không mồi hướng dẫn (đã đi system_prompt)",
          "trước đó" in made[0].queries[0] and "HƯỚNG DẪN" not in made[0].queries[0] and made[0].queries[0].endswith("chào"))
    out = "".join([d async for d in cl.stream("câu hai", [])])
    check("claude: lượt sau chỉ gửi câu, cùng client; không delta thì lấy AssistantMessage",
          made[0].queries[1] == "câu hai" and out == "Không stream." and len(made) == 1)
    err = ""
    try:
        [d async for d in cl.stream("câu ba", [])]
    except RuntimeError as e:
        err = str(e)
    check("claude: ResultMessage lỗi -> RuntimeError mang lý do", "hết hạn mức" in err)
    await cl.close()
    check("claude: close ngắt client", made[0].disconnected and cl.client is None)
    check("claude_pieces: bỏ qua message lạ", vb.claude_pieces(object()) == [])

    # Grok: CLI giả cùng khuôn GrokCLI.query (chỉ final), session_id nhớ sau lượt đầu
    class FakeGrok:
        def __init__(self): self.session_id = None; self.prompts = []

        async def query(self, prompt):
            self.prompts.append(prompt)
            self.session_id = "s-1"
            yield {"type": "usage", "input": 1, "output": 1}
            yield {"type": "final", "content": "Trả một cục."}

    g = vb.GrokVoiceBrain(cli_factory=FakeGrok)
    out = "".join([d async for d in g.stream("chào", [{"role": "user", "content": "trước đó"}])])
    check("grok: lấy final khi không có text", out == "Trả một cục.")
    check("grok: lượt đầu mồi lịch sử (chưa có mạch)", "trước đó" in g.cli.prompts[0])
    out = "".join([d async for d in g.stream("câu hai", [])])
    check("grok: có mạch rồi thì chỉ gửi câu", g.cli.prompts[1] == "câu hai")

    # _make chọn đúng lớp
    check("_make: codex/claude/grok ra đúng lớp",
          isinstance(vb._make({"provider": "codex", "model": ""}), vb.CodexVoiceBrain)
          and isinstance(vb._make({"provider": "claude", "model": ""}), vb.ClaudeVoiceBrain)
          and vb._make({"provider": "claude", "model": ""}).model == "haiku"
          and isinstance(vb._make({"provider": "grok", "model": "grok-4.6"}), vb.GrokVoiceBrain))

    # ---- 4c. Sổ việc nền của phiên nói (V3, spec mục 14) ----
    check("pending: chưa có việc -> ghi chú rỗng", vb.pending_note("p1") == "")
    n = vb.note_task_start("p1", "xem doanh thu hôm nay")
    vb.note_task_start("p1", "gửi mail cho Lan")
    ghi = vb.pending_note("p1", now=vb.pending_tasks("p1")[0]["at"] + 12)
    check("pending: hai việc, ghi chú kể cả hai kèm số giây, dặn đừng bịa", n == 1 and "doanh thu" in ghi and "gửi mail" in ghi
          and "12 giây" in ghi and "đừng bịa" in ghi)
    vb.note_task_done("p1", "xem doanh thu hôm nay")
    check("pending: xong một việc thì còn một", len(vb.pending_tasks("p1")) == 1 and "gửi mail" in vb.pending_note("p1"))
    vb.note_task_done("p1", "gửi mail cho Lan")
    check("pending: xong hết thì sổ rỗng", vb.pending_note("p1") == "" and vb.pending_tasks("p1") == [])
    vb.note_task_done("p1", "không có")   # không nổ
    check("prompt: bắt buộc câu xác nhận + việc chạy nền + yêu cầu tự đứng được",
          "MỘT câu xác nhận" in vb.SYSTEM_PROMPT and "chạy NỀN" in vb.SYSTEM_PROMPT and "tự đứng được" in vb.SYSTEM_PROMPT)

    # ---- 5. dây nối main.py ----
    src5 = (SERVER / "main.py").read_text(encoding="utf-8")
    check("main: gặp JAVIS_ASK_MAIN thì kết thúc lượt giọng ngay và giao việc nền, không await run_turn",
          "asyncio.create_task(_voice_bg_task(ask, conv_sid, brain))" in src5
          and '"background": ask' in src5
          and "await run_turn(conv_sid, user_message, brain, turn_tag, runtime_trace)\n\n        async def _voice_bg_task" not in src5)
    check("main: việc nền có khoá phiên riêng để chạy song song, xong thì push_to_chat",
          'key=f"voice:{conv_sid}:{uuid.uuid4().hex[:8]}"' in src5 and "await push_to_chat(conv_sid, out" in src5
          and 'meta={"chat_id": key}' in src5)
    check("main: câu gửi bộ não giọng ghép pending_note", "voice_brain.pending_note(conv_sid)" in src5)
    check("main: /voice/options báo sẵn/chưa sẵn cho codex, claude, grok",
          'elif pid == "codex":' in src5 and 'elif pid == "claude":' in src5 and 'elif pid == "grok":' in src5)
    src = (SERVER / "main.py").read_text(encoding="utf-8")
    check("main: nhánh voice trong WS", 'payload.get("voice")' in src and "run_voice_turn(" in src)
    check("main: làn nhanh chỉ đẩy phần đọc được qua split_speakable (marker không ra loa)",
          "voice_brain.split_speakable(text, sent_upto, final)" in src)
    check("main: bộ não giọng hỏng thì rơi về run_turn", "rơi về bộ não chính" in src)
    check("main: lệnh giao diện gọi THẲNG dashboard, không qua bộ não chính",
          "voice_brain.parse_ui(text)" in src
          and src.index("voice_brain.parse_ui(text)") < src.index("voice_brain.parse_marker(text)"))
    check("main: có POST /stt và GET /voice/options", '@app.post("/stt")' in src and '@app.get("/voice/options")' in src)
    check("main: có WS /ws/voice-live", '@app.websocket("/ws/voice-live")' in src)
    cfg_src = (SERVER / "config.py").read_text(encoding="utf-8")
    for k in ("brain_provider", "stt_provider", "live_provider", '"mode": "standard"'):
        check(f"config mặc định có {k}", k in cfg_src)


# ---- split_speakable: chỉ phát câu đã khép (0.57.1) ----
def _ss(text, start=0, final=False):
    return vb.split_speakable(text, start, final)

check("split: delta vài từ chưa có dấu -> KHÔNG phát gì", _ss("Xin lỗi David nhé, chắc") == ([], 0))
check("split: câu khép -> phát câu, giữ phần dở",
      _ss("Xin lỗi David nhé. Chắc là do mạng") == (["Xin lỗi David nhé."], len("Xin lỗi David nhé.")))
check("split: hai câu khép trong một lần -> một mẩu gồm cả hai (ít yêu cầu TTS hơn)",
      _ss("Câu một. Câu hai! Câu ba đang") == (["Câu một. Câu hai!"], len("Câu một. Câu hai!")))
check("split: dấu chấm trong số thập phân không phải kết câu", _ss("Doanh thu 1.5 tỷ đang tăng") == ([], 0))
check("split: xuống dòng là khép", _ss("Dòng một\nDòng hai đang") == (["Dòng một\n"], len("Dòng một\n")))
check("split: final đẩy nốt phần đuôi thành MỘT mẩu", _ss("Câu một. đuôi dở", final=True) == (["Câu một. đuôi dở"], len("Câu một. đuôi dở")))
long = "a" * 100 + ", " + "b" * 150
ch, pos = _ss(long)
check("split: đoạn dở dài quá SPEAK_MAX thì cắt sau dấu phẩy", ch == ["a" * 100 + ", "] and pos == 102)
check("split: dòng bắt đầu bằng đầu marker thì giữ lại", _ss("Để mình xem.\nJAVIS_ASK") == (["Để mình xem.\n"], len("Để mình xem.\n")))
check("split: dòng marker bị bỏ cả khi final",
      _ss("Để mình xem.\nJAVIS_ASK_MAIN: doanh thu tháng này", final=True) == (["Để mình xem.\n"], len("Để mình xem.\nJAVIS_ASK_MAIN: doanh thu tháng này")))
check("split: dòng marker giữa chừng bị bỏ, dòng sau vẫn phát",
      _ss("Để mình xem.\nJAVIS_ASK_MAIN: x\nXong rồi.\n") == (["Để mình xem.\n", "Xong rồi.\n"], len("Để mình xem.\nJAVIS_ASK_MAIN: x\nXong rồi.\n")))
check("split: gọi nối tiếp từ vị trí cũ", _ss("Câu một. Câu hai.", start=len("Câu một.")) == ([" Câu hai."], len("Câu một. Câu hai.")))

# ---- parse_ui: đường tắt giao diện, không đánh thức bộ não chính (0.57.5) ----
check("ui: mở trang -> (câu nói, action, target)",
      vb.parse_ui("Mở ngay.\nJAVIS_UI: open_page models") == ("Mở ngay.", ("open_page", "models")))
check("ui: bung nhóm thanh bên",
      vb.parse_ui("Bung mục Năng lực nhé.\nJAVIS_UI: open_group nang_luc") == ("Bung mục Năng lực nhé.", ("open_group", "nang_luc")))
check("ui: không có câu nói kèm thì câu nói rỗng", vb.parse_ui("JAVIS_UI: sidebar close") == ("", ("sidebar", "close")))
check("ui: action model tự bịa thì BỎ QUA, không nuốt câu và không chạy gì",
      vb.parse_ui("JAVIS_UI: rm -rf /") == ("JAVIS_UI: rm -rf /", None))
check("ui: câu thường không dính", vb.parse_ui("Doanh thu hôm nay bao nhiêu?") == ("Doanh thu hôm nay bao nhiêu?", None))
check("ui: dòng JAVIS_UI không bao giờ ra loa",
      _ss("Mở ngay.\nJAVIS_UI: open_page models", final=True)[0] == ["Mở ngay.\n"])
check("ui: đang stream dở chữ đầu trùng marker thì giữ lại, chưa phát",
      _ss("Mở ngay.\nJAVIS_U") == (["Mở ngay.\n"], len("Mở ngay.\n")))
check("prompt bộ não giọng có dạy khuôn JAVIS_UI", vb.UI_MARKER in vb.SYSTEM_PROMPT
      and "open_group" in vb.SYSTEM_PROMPT)
# Model giọng là model NHỎ: nó chỉ viết đúng id khi prompt nói rõ id nào ứng với nhãn tiếng
# Việt người dùng đọc lên ("mở trang công cụ" -> plugins).
check("prompt kèm nhãn tiếng Việt của trang", "plugins (công cụ)" in vb.SYSTEM_PROMPT
      and "skills (kỹ năng)" in vb.SYSTEM_PROMPT and "agents (trợ lý)" in vb.SYSTEM_PROMPT)

asyncio.run(main())
if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - voice_brain")
