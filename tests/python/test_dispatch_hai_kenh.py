"""Bảy chỗ còn lại mà hai bản dispatch engine trôi lệch nhau (phụ lục spec 2026-07-28).

    python tests/run.py dispatch_hai_kenh        (KHÔNG mạng)

Đánh số theo đúng phụ lục để đối chiếu:

  (3)  Telegram không phục hồi khi Codex resume thất bại - mất sạch ngữ cảnh, không dựng lại.
  (4)  `_codex_safe_model` ép model hợp lệ nhưng KHÔNG ghi lại, và không báo user model đã đổi.
  (5)  Sự kiện `error` đầu tiên huỷ cả lượt Telegram, kể cả khi luồng còn hồi phục được.
       Dashboard coi lỗi là không chí mạng.
  (6)  `compact_mem` chạy trong đường request - phiên dài phải chờ một vòng tóm tắt xong
       mới thấy câu trả lời.
  (8)  Dashboard: khung `response` của nhánh Claude nằm TRONG handler `final`, không có
       `final` thì không có `response` - bong bóng chat treo mãi.
  (9)  Nhánh Codex truyền `written=[]` cho `collect_turn_files`, trong khi nhánh Claude có
       thu đường dẫn Write/NotebookEdit. File Codex ghi ra chỉ được đính kèm nếu đường dẫn
       tình cờ xuất hiện trong câu trả lời.
  (10) Không có bản tương ứng của `store.clear_codex_thread_id`: đổi provider sang Claude rồi
       quay lại là resume một luồng Codex chưa hề thấy các lượt ở giữa.

Lỗi 3, 4, 5, 6, 9, 10 test bằng cách gọi THẲNG `_tg_answer` thật với engine giả (đo hành vi).
Lỗi 8 nằm trong hàm lồng bên trong `@app.websocket("/ws")` nên không gọi thẳng được - test
bằng AST, khẳng định đúng hai điều tạo nên lỗi: khung `response` KHÔNG nằm trong vòng lặp sự
kiện, và vòng lặp có tích luỹ phần text đã stream để còn cái mà trả khi luồng đứt giữa chừng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import ast
import asyncio
import os
import sys
import tempfile
import time

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-dispatch-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_context  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


BRAIN = tempfile.mkdtemp(prefix="javis-dispatch-brain-")
_THAT = channel_context.collect_turn_files      # bản THẬT (lỗi 9 cần chạy bộ lọc thật)


class KhoGia:
    def __init__(self):
        self.sessions, self.messages = {}, []

    def get_or_create(self, session_id, *, brain, engine, model):
        sid = session_id or f"sid-{len(self.sessions) + 1}"
        row = self.sessions.setdefault(sid, {"id": sid, "msg_count": 0})
        row.update({"engine": engine, "updated_at": time.time()})
        return sid

    def create_session(self, *, brain=None, engine=None, model=None, channel="web", **kw):
        # Từ 0.9.246 vỏ Telegram xoay phiên nên nó mở phiên MỚI qua đường này, không còn
        # đi qua get_or_create(None, ...) nữa.
        sid = f"sid-{len(self.sessions) + 1}"
        self.sessions[sid] = {"id": sid, "engine": engine, "channel": channel,
                              "updated_at": time.time(), "msg_count": 0}
        return sid

    def archive_stale(self, channel, before_ts):
        return 0

    def get_session(self, sid):
        return self.sessions.get(sid)

    def get_messages(self, sid):
        return [{"role": r, "content": c} for s, r, c in self.messages if s == sid]

    def append_message(self, sid, role, content, tool_calls=None):
        self.messages.append((sid, role, content))
        row = self.sessions.setdefault(sid, {"id": sid, "msg_count": 0})
        row["msg_count"] = row.get("msg_count", 0) + 1
        row["updated_at"] = time.time()
        return len(self.messages)

    def auto_title(self, sid, first_user_message):
        return None

    def set_cli_session_id(self, sid, v):
        pass

    def set_codex_thread_id(self, sid, v):
        pass

    def clear_codex_thread_id(self, sid):
        pass


def lap_gia(prov, kind, key, model, *, that_collect=False):
    """Thay phụ thuộc ngoài của _tg_answer bằng bản giả. Trả (kho, usage)."""
    kho, usage = KhoGia(), []
    main.get_store = lambda: kho
    main._chat_provider = lambda mcfg: (prov, kind, key, model)
    main._reasoning_level = lambda mcfg: "off"
    main._tg_brain = lambda chat_id: BRAIN
    main._brain_root = lambda b: BRAIN
    main.build_system_prompt = lambda b: "SYS"
    main._apply_mcp = lambda cli, brain=None: None
    main._apply_codex_hub = lambda ccli, root: None
    main.openai_oauth.write_codex_auth = lambda: None
    main.usage_store.record = lambda *a, **k: usage.append(a)
    main.log_conversation = lambda brain, u, j: None
    main.channel_context.collect_turn_files = _THAT if that_collect else (lambda *a, **k: [])

    async def _khong_lich(message, brain):
        return None
    main._schedule_cancel_action = _khong_lich

    async def _enqueue(brain, conv_sid, user, assistant):
        return None
    main.learn_feature.enqueue = _enqueue
    return kho, usage


def chay(text, chat="1"):
    return asyncio.run(main._tg_answer(text, {"chat_id": chat}))


def loi_text(kq):
    return kq.get("text") if isinstance(kq, dict) else str(kq)


# ================================================================
# (3) Codex resume hỏng -> dựng lại ngữ cảnh từ kho phiên
# ================================================================
class CodexResumeHong:
    """Lần query đầu (đang resume) chết vì rollout mất; lần sau phải chạy được."""

    def __init__(self, **kw):
        self.cwd = kw.get("cwd")
        self.model = kw.get("model")
        self.instructions = kw.get("instructions")
        self.session_id = "thread-cu"      # phiên đã có thread -> lượt này là resume
        self.extra_config = []
        self.prompts = []

    def is_available(self):
        return True

    async def query(self, prompt):
        self.prompts.append(prompt)
        if self.session_id:
            yield {"type": "error", "content": "Codex: rollout not found",
                   "resume_failed": True}
            return
        yield {"type": "text", "content": "Đã khôi phục, doanh thu 250k."}
        yield {"type": "final", "content": "Đã khôi phục, doanh thu 250k.",
               "session_id": "thread-moi", "tokens_in": 10, "tokens_out": 5}


kho, usage = lap_gia("openai-oauth", "oauth", "", "gpt-5.5")
main._codex_safe_model = lambda m: "gpt-5.5"
main._TG_SESS.clear()
_cx = CodexResumeHong(cwd=BRAIN, model="gpt-5.5", instructions="SYS")
main._TG_SESS["1"] = {"cli": None, "codex": _cx, "or": None,
                      "last": None, "sent": set(), "brain": None}
kho.messages.append(("sid-1", "user", "câu hỏi cũ"))
kho.messages.append(("sid-1", "assistant", "câu trả lời cũ"))
main._TG_SESS["1"]["sid"] = "sid-1"
kho.sessions["sid-1"] = {"id": "sid-1"}

kq3 = chay("doanh thu hôm nay?")
check("(3) resume hỏng: vẫn ra được câu trả lời, không bỏ cuộc",
      "250k" in (loi_text(kq3) or ""))
check("(3) resume hỏng: có thử lại lần hai", len(_cx.prompts) == 2)
check("(3) resume hỏng: lần hai mang theo ngữ cảnh dựng từ kho phiên",
      len(_cx.prompts) == 2 and "KHÔI PHỤC NGỮ CẢNH" in _cx.prompts[1]
      and "câu trả lời cũ" in _cx.prompts[1])


# ================================================================
# (4) Model bị ép về bản hợp lệ thì phải GHI LẠI và BÁO cho user
# ================================================================
class CodexOk:
    def __init__(self, **kw):
        self.cwd = kw.get("cwd")
        self.model = kw.get("model")
        self.instructions = kw.get("instructions")
        self.session_id = None
        self.extra_config = []
        self.prompts = []
        self.tools = []

    def is_available(self):
        return True

    async def query(self, prompt):
        self.prompts.append(prompt)
        for ev in self.tools:
            yield ev
        yield {"type": "final", "content": "Xong.", "session_id": "thread-1",
               "tokens_in": 1, "tokens_out": 1}


kho, usage = lap_gia("openai-oauth", "oauth", "", "gpt-4o")
main._codex_safe_model = lambda m: "gpt-5.5"
main.CodexCLI = lambda **kw: CodexOk(**kw)
main._TG_SESS.clear()
_ghi = []
main._set_main_model = lambda s, p, m: _ghi.append((p, m))
main.cfgmod.write_settings = lambda s: _ghi.append(("write", None))

kq4 = chay("chào")
t4 = loi_text(kq4) or ""
check("(4) model không hợp lệ: GHI LẠI model đã ép vào Settings",
      any(g[0] == "openai-oauth" and g[1] == "gpt-5.5" for g in _ghi) and ("write", None) in _ghi)
check("(4) model không hợp lệ: BÁO cho user là đã đổi", "gpt-4o" in t4 and "gpt-5.5" in t4)
check("(4) vẫn giữ nguyên câu trả lời thật", "Xong." in t4)


# ================================================================
# (5) Lỗi giữa lượt KHÔNG được huỷ cả lượt nếu luồng còn hồi phục
# ================================================================
class CLIChapChon:
    def __init__(self, **kw):
        self.system_prompt, self.model, self.session_id = "", None, None

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt):
        yield {"type": "error", "content": "một tool lỗi vặt"}
        yield {"type": "text", "content": "Doanh thu 250k."}
        yield {"type": "final", "content": "Doanh thu 250k.",
               "session_id": "s1", "tokens_in": 5, "tokens_out": 5, "cost_usd": 0.001}


kho, usage = lap_gia("anthropic-cli", "cli", "", "opus")
main.claude_engine = lambda **kw: CLIChapChon(**kw)
main._TG_SESS.clear()
kq5 = chay("doanh thu?")
t5 = loi_text(kq5) or ""
check("(5) lỗi giữa lượt: KHÔNG nuốt mất câu trả lời", "250k" in t5)
check("(5) lỗi giữa lượt: vẫn nói cho user biết là có lỗi", "một tool lỗi vặt" in t5)
check("(5) lỗi giữa lượt: vẫn ghi Mức dùng", len(usage) == 1)

# Lỗi mà KHÔNG có chữ nào thì vẫn phải báo lỗi như cũ.


class CLIChetHan:
    def __init__(self, **kw):
        self.system_prompt, self.model, self.session_id = "", None, None

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt):
        yield {"type": "error", "content": "hết hạn đăng nhập"}


kho, usage = lap_gia("anthropic-cli", "cli", "", "opus")
main.claude_engine = lambda **kw: CLIChetHan(**kw)
main._TG_SESS.clear()
kq5b = chay("doanh thu?")
check("(5) lỗi mà không có chữ nào: vẫn báo lỗi",
      "hết hạn đăng nhập" in loi_text(kq5b) and not isinstance(kq5b, dict))


# ================================================================
# (6) compact_mem phải chạy NỀN, không chặn câu trả lời
# ================================================================
kho, usage = lap_gia("openrouter", "api", "sk-x", "x/y")
main._TG_SESS.clear()
_nen = {"xong": False}


async def _api_gia(prov, key, model, messages, reasoning="off", brain=None):
    async def _gen():
        yield {"type": "text", "content": "Trả lời nhanh."}
        yield {"type": "usage", "input": 10, "output": 5}
    return _gen()


async def _compact_cham(msgs, prov, key, model, streamer):
    await asyncio.sleep(0.15)
    _nen["xong"] = True
    return list(msgs) + [{"role": "system", "content": "TÓM TẮT"}]


main._api_stream_mcp = _api_gia
main.compaction.compact_mem = _compact_cham


async def _do_6():
    kq = await main._tg_answer("tổng kết", {"chat_id": "1"})
    som = _nen["xong"]              # lúc user đã có câu trả lời, nén xong chưa?
    await asyncio.sleep(0.4)        # nhường cho task nền chạy nốt
    return kq, som, _nen["xong"]


kq6, som6, sau6 = asyncio.run(_do_6())
check("(6) trả lời user TRƯỚC khi nén xong (không chặn đường request)", som6 is False)
check("(6) nhưng việc nén vẫn chạy tới nơi ở nền", sau6 is True)
check("(6) câu trả lời không bị ảnh hưởng", "Trả lời nhanh." in (loi_text(kq6) or ""))
check("(6) kết quả nén được áp vào lịch sử phiên",
      any((m.get("content") == "TÓM TẮT") for m in (main._TG_SESS["1"]["or"] or [])))


# ================================================================
# (9) File Codex ghi ra phải được đính kèm, không cần nhắc trong câu trả lời
# ================================================================
check("(9) có hàm gom đường dẫn từ payload tool call",
      callable(getattr(channel_context, "candidate_paths_from_tool", None)))

if callable(getattr(channel_context, "candidate_paths_from_tool", None)):
    gom = channel_context.candidate_paths_from_tool
    check("(9) gom: lấy path trong trường 'changes' của bản vá",
          "/a/b/note.md" in gom({"type": "file_change",
                                 "changes": [{"path": "/a/b/note.md", "kind": "add"}]}))
    check("(9) gom: lấy path trong 'arguments' dạng chuỗi JSON",
          "D:\\x\\y.png" in gom({"type": "function_call",
                                 "arguments": '{"file_path": "D:\\\\x\\\\y.png"}'}))
    check("(9) gom: lấy path tương đối trong lệnh shell",
          any(p.endswith("attachments/anh.png")
              for p in gom({"type": "command_execution",
                            "command": "cp tmp.png attachments/anh.png"})))
    check("(9) gom: payload không có path thì trả rỗng",
          gom({"type": "command_execution", "command": "ls -la"}) == [])
    check("(9) gom: payload rác không nổ", gom(None) == [] and gom("abc") == [])

# Đầu-cuối: Codex ghi một file THẬT trong lượt, không nhắc tên nó trong câu trả lời.
kho, usage = lap_gia("openai-oauth", "oauth", "", "gpt-5.5", that_collect=True)
main._codex_safe_model = lambda m: "gpt-5.5"
main._TG_SESS.clear()
_f9 = os.path.join(BRAIN, "bao-cao-thang-6.md")
with open(_f9, "w", encoding="utf-8") as fh:
    fh.write("# Báo cáo\n")
os.utime(_f9, (time.time(), time.time()))
_cx9 = CodexOk(cwd=BRAIN, model="gpt-5.5", instructions="SYS")
_cx9.tools = [{"type": "tool_call", "name": "apply_patch",
               "item": {"type": "file_change",
                        "changes": [{"path": _f9, "kind": "update"}]}}]
main.CodexCLI = lambda **kw: _cx9
kq9 = chay("viết báo cáo giúp anh")
check("(9) file Codex vừa ghi được tự đính kèm dù không nhắc trong câu trả lời",
      isinstance(kq9, dict) and any(os.path.normcase(p) == os.path.normcase(_f9)
                                    for p in (kq9.get("files") or [])))

# Bản vá trên chỉ có tác dụng thật nếu CodexCLI CHỊU đẩy payload thô lên. Nó nằm trong một
# async generator có spawn tiến trình nên không gọi thẳng được; soi bằng AST.
_cc = ast.parse((SERVER / "claude_cli.py").read_text(encoding="utf-8", errors="replace"))
_yields = [n for n in ast.walk(_cc) if isinstance(n, ast.Yield) and isinstance(n.value, ast.Dict)]


def _khoa(d):
    return {k.value for k in d.keys if isinstance(k, ast.Constant)}


def _la(d, ten):
    for k, v in zip(d.keys, d.values):
        if isinstance(k, ast.Constant) and k.value == "type" \
                and isinstance(v, ast.Constant) and v.value == ten:
            return True
    return False


check("(9) CodexCLI đính payload thô vào sự kiện tool_call",
      any(_la(y.value, "tool_call") and "item" in _khoa(y.value) for y in _yields))
check("(9) CodexCLI cũng đẩy item lạ (vd bản vá file) lên cho caller moi đường dẫn",
      any(_la(y.value, "item") and "item" in _khoa(y.value) for y in _yields))


# ================================================================
# (10) Đổi provider sang Claude rồi quay lại: KHÔNG resume luồng Codex cũ
# ================================================================
kho, usage = lap_gia("openai-oauth", "oauth", "", "gpt-5.5")
main._codex_safe_model = lambda m: "gpt-5.5"
_cx10 = CodexOk(cwd=BRAIN, model="gpt-5.5", instructions="SYS")
main.CodexCLI = lambda **kw: _cx10
main._TG_SESS.clear()
chay("lượt codex")
_cx10.session_id = "thread-1"        # Codex đã mở thread cho phiên này

# ... giờ user đổi sang Claude và nói chuyện tiếp
lap_gia("anthropic-cli", "cli", "", "opus")
main.claude_engine = lambda **kw: CLIChapChon(**kw)
chay("lượt claude chen vào")

check("(10) lượt Claude chen vào -> liên kết thread Codex bị xoá",
      not (main._TG_SESS.get("1", {}).get("codex")
           and getattr(main._TG_SESS["1"]["codex"], "session_id", None))
      )


# ================================================================
# (8) Dashboard: khung `response` không được nằm trong vòng lặp sự kiện
# ================================================================
tree = ast.parse((SERVER / "main.py").read_text(encoding="utf-8", errors="replace"))
do_turn = next((n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_do_turn"), None)
check("(8) tìm thấy _do_turn", do_turn is not None)

if do_turn is not None:
    vong = [n for n in ast.walk(do_turn)
            if isinstance(n, ast.AsyncFor) and isinstance(n.iter, ast.Call)
            and isinstance(n.iter.func, ast.Attribute) and n.iter.func.attr == "query"
            and isinstance(n.iter.func.value, ast.Name) and n.iter.func.value.id == "cli"]
    check("(8) tìm thấy vòng lặp sự kiện của nhánh Claude", len(vong) == 1)
    if len(vong) == 1:
        chuoi = [n.value for n in ast.walk(vong[0])
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        check("(8) khung `response` KHÔNG nằm trong vòng lặp (không có `final` vẫn phải có `response`)",
              "response" not in chuoi)
        # Luồng đứt giữa chừng thì `final` không tới - phải còn phần đã stream mà trả.
        cong_don = [n for n in ast.walk(vong[0])
                    if isinstance(n, ast.AugAssign) and isinstance(n.op, ast.Add)]
        check("(8) vòng lặp có tích luỹ phần text đã stream để làm phương án dự phòng",
              len(cong_don) >= 1)
    n_resp = sum(1 for n in ast.walk(do_turn)
                 if isinstance(n, ast.Constant) and n.value == "response")
    check("(8) mỗi nhánh engine vẫn gửi đúng khung response của nó", n_resp >= 4)

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
