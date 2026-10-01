"""Codex app-server sống lâu cho ChatGPT Live (server/codex_realtime.py, 0.65.17).

    python tests/run.py codex_realtime

Không chạy Codex thật: `popen_factory` dựng một tiến trình giả nói JSON-RPC qua stdin/stdout.
Khoá:
  - khởi động gửi `initialize` có capabilities.experimentalApi, rồi `initialized`, kèm cờ
    features.realtime_conversation trên dòng lệnh (Codex trước 0.159 tắt sẵn realtime);
  - request khớp đúng id, lỗi JSON-RPC thành AppServerError mang câu lỗi;
  - yêu cầu từ server (duyệt quyền...) bị từ chối ngay, không treo tiến trình;
  - thông báo đi đúng hàng đợi theo threadId; thread chưa đăng ký thì bỏ;
  - tiến trình chết: request đang chờ ném lỗi, hàng đợi nhận dấu `_exit`, get_app_server dựng lại.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import queue
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-codexrt-"))

import codex_realtime  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


class FakeProc:
    """Tiến trình giả: ghi vào stdin thì `handler` quyết định trả gì qua stdout."""

    def __init__(self, argv, handler):
        self.argv = argv
        self.sent = []
        self._out = queue.Queue()
        self._handler = handler
        self.returncode = None
        proc = self

        class _In:
            def write(self, s):
                for line in s.splitlines():
                    if line.strip():
                        msg = json.loads(line)
                        proc.sent.append(msg)
                        for reply in proc._handler(msg) or []:
                            proc.emit(reply)

            def flush(self):
                pass

        class _Out:
            def readline(self):
                item = proc._out.get()
                return "" if item is None else json.dumps(item) + "\n"

        self.stdin, self.stdout = _In(), _Out()

    def emit(self, msg):
        self._out.put(msg)

    def die(self):
        self.returncode = 1
        self._out.put(None)

    def poll(self):
        return self.returncode

    def kill(self):
        self.die()

    def wait(self, timeout=None):
        return self.returncode


def default_handler(msg):
    if msg.get("method") == "initialize":
        return [{"id": msg["id"], "result": {"userAgent": "fake"}}]
    if msg.get("method") == "thread/start":
        return [{"id": msg["id"], "result": {"thread": {"id": "th-1"}}}]
    if msg.get("method") == "boom":
        return [{"id": msg["id"], "error": {"code": -32600, "message": "thread không hỗ trợ realtime"}}]
    return []


procs = []


def factory(argv, **kw):
    p = FakeProc(argv, default_handler)
    procs.append(p)
    return p


async def main():
    srv = codex_realtime.AppServer("codex-fake", popen_factory=factory)
    await srv.ensure_started()
    p = procs[-1]
    check("dòng lệnh bật cờ realtime và chạy app-server",
          p.argv[1:] == ["-c", "features.realtime_conversation=true", "app-server"])
    init = p.sent[0]
    check("initialize có capabilities.experimentalApi",
          init.get("method") == "initialize" and init["params"].get("capabilities", {}).get("experimentalApi") is True)
    check("gửi thông báo initialized sau initialize",
          any(m.get("method") == "initialized" and "id" not in m for m in p.sent))

    res = await srv.request("thread/start", {"ephemeral": True})
    check("request trả result khớp id", res.get("thread", {}).get("id") == "th-1")

    try:
        await srv.request("boom", {})
        check("lỗi JSON-RPC thành AppServerError", False)
    except codex_realtime.AppServerError as e:
        check("lỗi JSON-RPC thành AppServerError mang câu lỗi", "realtime" in str(e))

    q = srv.subscribe("th-1")
    p.emit({"method": "thread/realtime/transcript/delta", "params": {"threadId": "th-1", "role": "user", "delta": "chào"}})
    p.emit({"method": "thread/realtime/transcript/delta", "params": {"threadId": "khac", "role": "user", "delta": "x"}})
    got = await asyncio.wait_for(q.get(), 2)
    check("thông báo đúng thread vào đúng hàng đợi", got["params"]["delta"] == "chào")
    await asyncio.sleep(0.05)
    check("thông báo thread khác không lọt vào", q.empty())

    p.emit({"id": 99, "method": "item/commandExecution/requestApproval", "params": {"threadId": "th-1"}})
    await asyncio.sleep(0.1)
    denied = [m for m in p.sent if m.get("id") == 99]
    check("yêu cầu duyệt quyền từ server bị từ chối", bool(denied) and "error" in denied[0])

    srv.unsubscribe("th-1")
    p.emit({"method": "thread/realtime/transcript/delta", "params": {"threadId": "th-1", "delta": "y"}})
    await asyncio.sleep(0.05)
    check("huỷ đăng ký thì không nhận nữa", q.empty())

    q2 = srv.subscribe("th-2")
    pending = asyncio.ensure_future(srv.request("im/lang", {}, timeout=5))
    await asyncio.sleep(0.05)
    p.die()
    try:
        await asyncio.wait_for(pending, 2)
        check("tiến trình chết thì request đang chờ ném lỗi", False)
    except codex_realtime.AppServerError:
        check("tiến trình chết thì request đang chờ ném lỗi", True)
    ev = await asyncio.wait_for(q2.get(), 2)
    check("hàng đợi nhận dấu _exit khi tiến trình chết", ev.get("method") == "_exit")
    check("alive = False sau khi chết", srv.alive is False)

    # get_app_server: dựng lại khi bản cũ đã chết
    codex_realtime._SERVER = srv
    codex_realtime._popen_factory = factory
    codex_realtime._find_cli = lambda: "codex-fake"
    fresh = await codex_realtime.get_app_server()
    check("get_app_server dựng lại tiến trình mới khi bản cũ chết", fresh is not srv and fresh.alive)
    again = await codex_realtime.get_app_server()
    check("get_app_server dùng lại bản đang sống", again is fresh)
    codex_realtime._find_cli = lambda: None
    codex_realtime._SERVER = None
    try:
        await codex_realtime.get_app_server()
        check("không có Codex CLI thì báo lỗi dễ hiểu", False)
    except codex_realtime.AppServerError as e:
        check("không có Codex CLI thì báo lỗi dễ hiểu", "Codex" in str(e))


asyncio.run(main())

# realtime_available: cần binary và đăng nhập ChatGPT
codex_realtime._find_cli = lambda: "codex-fake"
ok, why = codex_realtime.realtime_available({"model": {"openai_oauth": {"refresh_token": "r"}}})
check("có Codex và đã nối ChatGPT -> dùng được", ok is True)
codex_realtime._codex_logged_in = lambda: False
ok, why = codex_realtime.realtime_available({"model": {}})
check("chưa nối ChatGPT -> không dùng được, lý do no_login", ok is False and why == "no_login")
codex_realtime._find_cli = lambda: None
ok, why = codex_realtime.realtime_available({"model": {"openai_oauth": {"refresh_token": "r"}}})
check("không có Codex CLI -> lý do no_cli", ok is False and why == "no_cli")

# Chọn bản Codex: bản MỚI NHẤT đủ 0.153; chỉ có bản cũ thì lý do old_cli (0.147 bị OpenAI từ chối
# vì gửi thừa session.model, đo 01/10/2026).
import importlib
cr = importlib.reload(codex_realtime)
cr._candidate_clis = lambda: ["old.exe", "mid.exe", "new.exe"]
cr._version_of = lambda p: {"old.exe": (0, 147, 0), "mid.exe": (0, 153, 4), "new.exe": (0, 158, 0)}[p]
check("chọn bản Codex mới nhất đủ điều kiện", cr._find_cli() == "new.exe")
cr._candidate_clis = lambda: ["old.exe"]
check("chỉ có Codex cũ -> None, lý do old_cli", cr._find_cli() is None and cr._LAST_CLI_REASON == "old_cli")
ok, why = cr.realtime_available({"model": {"openai_oauth": {"refresh_token": "r"}}})
check("realtime_available báo old_cli", ok is False and why == "old_cli")
cr._candidate_clis = lambda: []
check("không có Codex nào -> lý do no_cli", cr._find_cli() is None and cr._LAST_CLI_REASON == "no_cli")

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - codex realtime app-server")
