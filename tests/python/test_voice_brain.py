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

    # ---- 5. dây nối main.py ----
    src = (SERVER / "main.py").read_text(encoding="utf-8")
    check("main: nhánh voice trong WS", 'payload.get("voice")' in src and "run_voice_turn(" in src)
    check("main: làn nhanh chỉ đẩy phần đọc được qua split_speakable (marker không ra loa)",
          "voice_brain.split_speakable(text, sent_upto, final)" in src)
    check("main: bộ não giọng hỏng thì rơi về run_turn", "rơi về bộ não chính" in src)
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

asyncio.run(main())
if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - voice_brain")
