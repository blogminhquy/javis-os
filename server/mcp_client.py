"""
MCP client của Javis - để MỌI bộ não (API/OAuth lẫn hub) dùng được MCP.
v2: SESSION POOL sống lâu giữa các tin nhắn (hết cảnh mỗi tool call mở session mới),
thêm transport stdio (MCP local như zalo-agent-cli, webcake-landing-mcp) và
"internal" (cầu nối Python nội bộ như botcake_mcp).

3 transport:
- http/sse : Streamable HTTP JSON-RPC 2.0, giữ Mcp-Session-Id, httpx client sống lâu.
- stdio    : spawn subprocess, NDJSON JSON-RPC qua stdin/stdout (Windows: .cmd chạy qua cmd.exe /c).
- internal : gọi thẳng module Python trong repo (registry _INTERNAL).

Lỗi 1 lần → đóng session, dựng lại, retry ĐÚNG 1 lần rồi mới trả "ERROR: ...".
"""
import asyncio
import hashlib
import importlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

import httpx

PROTOCOL = "2025-06-18"
# _IDLE_TTL PHẢI LỚN HƠN connect_health.HEALTH_INTERVAL (600). Khi hai số bằng nhau,
# session vừa bị dọn xong ngay trước mỗi vòng quét sức khoẻ → vòng nào cũng spawn server
# stdio mới (uvx còn đi hỏi PyPI mỗi lần). Đặt TTL > interval thì chính vòng quét giữ
# session ấm: một tiến trình sống lâu thay vì đẻ mới mỗi 10 phút. Vụ VPS Hostinger
# 15/08: 100 tiến trình mcp-google-sheets, ăn 6,9 GB RAM.
_IDLE_TTL = 900          # đóng session không dùng > 15 phút
_INTERNAL = {"botcake": "botcake_mcp", "substack": "substack_mcp"}   # transport internal → tên module

_DIAL_SONG_SONG = 8      # số connection dò tool CÙNG LÚC (đừng để npx nổ ra 30 tiến trình)
_DIAL_TRAN = "20"        # giây - trần dò tool CHO MỖI connection (0 = không giới hạn)
_WARM_TRAN = "180"       # giây - trần cho vòng LÀM NÓNG lúc khởi động (xem tran_warm)


def sanitize_fn(name):
    """Tên function gửi cho model phải khớp ^[a-zA-Z0-9_-]{1,64}$."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:64]


def _mk_fn(ns, tool, route):
    """fn <=64 ký tự nhưng KHÔNG để namespace dài nuốt mất tên tool (cắt thô 64 làm mọi tool
    của 1 connection trùng nhau): giữ nguyên tên tool, cắt namespace + hash 4 ký tự; vẫn trùng
    (đã có trong route) thì thêm hậu tố số."""
    t = re.sub(r"[^a-zA-Z0-9_-]", "_", str(tool))
    n = re.sub(r"[^a-zA-Z0-9_-]", "_", str(ns))
    fn = f"{n}__{t}"
    if len(fn) > 64:
        h = hashlib.md5(n.encode("utf-8")).hexdigest()[:4]
        keep = max(4, 64 - len(t) - 2 - 4)
        fn = f"{n[:keep]}{h}__{t}"[:64]
    base, i = fn, 2
    while fn in route:
        suf = f"_{i}"
        fn = base[:64 - len(suf)] + suf
        i += 1
    return fn


def _format_result(res):
    """Bóc JSON-RPC response thành text kết quả (giữ đúng hành vi bản cũ)."""
    if "error" in (res or {}):
        return "ERROR: " + json.dumps(res["error"], ensure_ascii=False)[:500]
    result = (res or {}).get("result") or {}
    texts = []
    for c in (result.get("content") or []):
        if isinstance(c, dict):
            texts.append(c.get("text", "") if c.get("type") == "text" else json.dumps(c, ensure_ascii=False))
    out = "\n".join(t for t in texts if t)
    if result.get("isError"):
        return "ERROR: " + (out or "tool error")
    return out or json.dumps(result, ensure_ascii=False)[:2000]


# ============================================================
# HTTP (Streamable HTTP) - client sống lâu, giữ Mcp-Session-Id
# ============================================================
class McpHttpSession:
    def __init__(self, url, headers=None):
        self.url = url
        self.base_headers = dict(headers or {})
        self.session_id = None
        self._id = 0
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10))
        self._init_done = False
        self._lock = asyncio.Lock()

    def _hdr(self):
        h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        h.update(self.base_headers)
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
            h["MCP-Protocol-Version"] = PROTOCOL
        return h

    async def _rpc(self, method, params=None, notify=False):
        self._id += 1
        msg = {"jsonrpc": "2.0", "method": method}
        if not notify:
            msg["id"] = self._id
        if params is not None:
            msg["params"] = params
        r = await self._client.post(self.url, headers=self._hdr(), json=msg)
        sid = r.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if notify:
            return None
        ct = (r.headers.get("content-type") or "").lower()
        if "text/event-stream" in ct:
            for line in (r.text or "").splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    try:
                        obj = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if obj.get("id") == msg.get("id"):
                        return obj
            return {}
        try:
            return r.json()
        except Exception:
            return {"error": {"code": r.status_code, "message": (r.text or "")[:300]}}

    async def ensure_init(self):
        async with self._lock:
            if self._init_done:
                return
            await self._rpc("initialize", {
                "protocolVersion": PROTOCOL, "capabilities": {},
                "clientInfo": {"name": "javis-os", "version": "1.0"},
            })
            await self._rpc("notifications/initialized", notify=True)
            self._init_done = True

    async def list_tools(self):
        await self.ensure_init()
        res = await self._rpc("tools/list")
        return ((res or {}).get("result") or {}).get("tools", []) or []

    async def call_tool(self, name, arguments):
        await self.ensure_init()
        res = await self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return _format_result(res)

    async def close(self):
        try:
            await self._client.aclose()
        except Exception:
            pass


# ============================================================
# stdio - subprocess NDJSON (Windows-first)
# ============================================================
class McpStdioSession:
    def __init__(self, command, args=None, env=None, label=""):
        self.command = command
        self.args = list(args or [])
        self.env = {k: str(v) for k, v in (env or {}).items() if v is not None}
        self.label = label or command
        self.proc = None
        self._id = 0
        self._lock = asyncio.Lock()   # NDJSON tuần tự - serialize request/response
        # 50 dòng: traceback Python lồng nhau (uvx crash lúc import) dễ vượt 20 dòng,
        # mà dòng NGUYÊN NHÂN nằm cuối cùng - thiếu chỗ chứa là mất đúng dòng đó.
        self._stderr = deque(maxlen=50)
        self._stderr_task = None
        self._init_done = False

    def _argv(self):
        # Tìm cả trong Scripts/bin của venv Javis: uvx/uv cài theo requirements nằm ở đó
        # (PATH hệ thống thường không có) → connector PyPI (uvx ...) chạy được out-of-the-box.
        venv_bin = str(Path(sys.executable).parent)
        search = venv_bin + os.pathsep + os.environ.get("PATH", "")
        resolved = shutil.which(self.command, path=search) or self.command
        # CreateProcess không chạy .cmd/.bat trực tiếp (npx trên Windows là npx.cmd)
        if str(resolved).lower().endswith((".cmd", ".bat")):
            return ["cmd.exe", "/c", resolved] + self.args
        return [resolved] + self.args

    async def _drain_stderr(self):
        try:
            while self.proc and self.proc.stderr:
                line = await self.proc.stderr.readline()
                if not line:
                    return
                self._stderr.append(line.decode("utf-8", "replace").rstrip())
        except Exception:
            pass

    def alive(self):
        return self.proc is not None and self.proc.returncode is None

    # asyncio mặc định trần StreamReader 64KB MỖI DÒNG - tools/list của workspace-mcp là MỘT
    # dòng NDJSON vài trăm KB nên readline() nổ LimitOverrun (đội lốt ValueError). Nới hẳn 16MB.
    _STREAM_LIMIT = 16 * 1024 * 1024

    async def start(self):
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        else:
            # Nhóm tiến trình RIÊNG cho cả cây con - xem docstring _kill_tree (vụ 15/08:
            # uvx bị kill nhưng server thật thành mồ côi, 96 tiến trình ăn hết RAM VPS).
            kwargs["start_new_session"] = True
        env = dict(os.environ)
        env.update(self.env)
        self.proc = await asyncio.create_subprocess_exec(
            *self._argv(), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=env, limit=self._STREAM_LIMIT, **kwargs)
        self._stderr_task = asyncio.ensure_future(self._drain_stderr())

    def _err_tail(self, n=8, cap=900):
        lines = [l for l in self._stderr if l.strip()]
        if not lines:
            return ""
        tail = " | ".join(lines[-n:])
        # Traceback Python để NGUYÊN NHÂN ở dòng CUỐI (vd "ModuleNotFoundError: ...").
        # Cắt từ đầu như trước là giữ đúng phần vô dụng (đường dẫn cache dài của uv)
        # và vứt đúng dòng người ta cần → phải giữ ĐUÔI.
        return tail if len(tail) <= cap else "..." + tail[-cap:]

    async def _doi_stderr_xong(self):
        # Process vừa chết: _drain_stderr chạy bất đồng bộ nên tại thời điểm này có thể
        # CHƯA đọc hết traceback. Đợi nó tới EOF (process chết thì EOF tới ngay) rồi hãy
        # dựng thông báo lỗi, không thì chụp được log dở dang.
        try:
            await asyncio.wait_for(self.proc.wait(), timeout=1.0)
        except Exception:
            pass
        if self._stderr_task:
            try:
                await asyncio.wait_for(asyncio.shield(self._stderr_task), timeout=0.5)
            except Exception:
                pass

    async def _rpc(self, method, params=None, notify=False, timeout=120):
        if not self.alive():
            # ConnectionError = lỗi TRƯỚC khi gửi request → pool được phép retry cả tool ghi
            raise ConnectionError(f"process chết ({self._err_tail() or 'không rõ lý do'})")
        self._id += 1
        msg = {"jsonrpc": "2.0", "method": method}
        if not notify:
            msg["id"] = self._id
        if params is not None:
            msg["params"] = params
        line = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        self.proc.stdin.write(line)
        await self.proc.stdin.drain()
        if notify:
            return None
        deadline = time.time() + timeout
        while True:
            remain = deadline - time.time()
            if remain <= 0:
                raise TimeoutError(f"tool không phản hồi sau {timeout}s")
            raw = await asyncio.wait_for(self.proc.stdout.readline(), timeout=remain)
            if not raw:
                await self._doi_stderr_xong()
                raise RuntimeError(f"process đóng stdout ({self._err_tail() or 'exit?'})")
            raw = raw.decode("utf-8", "replace").strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue   # noise (log npx...) → bỏ qua
            if obj.get("id") == msg["id"]:
                return obj
            # notification/request từ server → bỏ qua (Javis không hỗ trợ sampling)

    async def ensure_init(self):
        async with self._lock:
            if self._init_done:
                return
            if not self.alive():
                await self.start()
            # npx lần đầu phải TẢI package → init cho timeout dài
            await self._rpc("initialize", {
                "protocolVersion": PROTOCOL, "capabilities": {},
                "clientInfo": {"name": "javis-os", "version": "1.0"},
            }, timeout=90)
            await self._rpc("notifications/initialized", notify=True)
            self._init_done = True

    async def list_tools(self):
        await self.ensure_init()
        async with self._lock:
            res = await self._rpc("tools/list", timeout=60)
        return ((res or {}).get("result") or {}).get("tools", []) or []

    async def call_tool(self, name, arguments):
        await self.ensure_init()
        async with self._lock:
            res = await self._rpc("tools/call", {"name": name, "arguments": arguments or {}}, timeout=120)
        return _format_result(res)

    def _kill_tree(self):
        """Giết CẢ CÂY tiến trình, không riêng launcher.

        start() đặt start_new_session=True nên trên POSIX pgid của nhóm == pid của child;
        killpg theo số đó quét được cả cháu, KỂ CẢ khi launcher đã chết trước (nhóm còn
        tồn tại chừng nào còn thành viên). Chốt an toàn hai lớp: không bao giờ đụng nhóm
        của chính server, và nếu child không phải leader (bản cũ chưa có session riêng)
        thì nhóm mang id đó không tồn tại → ProcessLookupError → rơi về kill() như cũ."""
        pid = self.proc.pid
        if os.name == "nt":
            # Windows không có process group kiểu POSIX → taskkill /T giết cả cây.
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                return
            except Exception:
                pass
        else:
            try:
                if pid != os.getpgid(0):
                    os.killpg(pid, signal.SIGKILL)
                    return
            except ProcessLookupError:
                pass   # cả nhóm đã chết sạch, hoặc child không phải leader → kill thường
            except Exception:
                pass
        try:
            self.proc.kill()   # fallback: ít nhất giết launcher như cũ
        except Exception:
            pass

    async def close(self):
        # KHÔNG canh alive() ở đây: launcher chết trước (crash lúc import...) thì cháu
        # của nó vẫn sống mồ côi - vẫn phải quét nhóm.
        try:
            if self.proc:
                self._kill_tree()
                await self.proc.wait()
        except Exception:
            pass


# ============================================================
# internal - module Python trong repo (vd botcake_mcp)
# ============================================================
class McpInternalSession:
    def __init__(self, name, spec):
        self.mod = importlib.import_module(_INTERNAL[name])
        self.spec = spec

    async def list_tools(self):
        return await self.mod.list_tools(self.spec)

    async def call_tool(self, name, arguments):
        return await self.mod.call(name, arguments or {}, self.spec)

    async def close(self):
        pass


# ============================================================
# Session pool
# ============================================================
def _spec_hash(spec):
    t = spec.get("transport") or "http"
    if t == "stdio":
        core = (spec.get("command"), tuple(spec.get("args") or []),
                tuple(sorted((spec.get("env") or {}).items())))
    elif t == "internal":
        core = (spec.get("internal"), tuple(sorted((spec.get("secrets") or {}).items())))
    else:
        core = (spec.get("url"), tuple(sorted((spec.get("headers") or {}).items())))
    return hash(core)


class SessionPool:
    """Giữ session MCP sống giữa các tin nhắn. key = định danh connection."""

    def __init__(self):
        self._sessions = {}   # key -> {"obj", "hash", "last"}

    def _close_later(self, obj):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(obj.close())
        except RuntimeError:
            pass   # không có event loop (test sync) → GC tự dọn

    def _sweep(self):
        now = time.time()
        # `not v.get("ban")`: phiên đang chạy dở một tool call thì TUYỆT ĐỐI không đóng. Đóng
        # phiên stdio là SIGKILL cả cây tiến trình (xem `McpStdioSession.close`), tức là giết
        # luôn cái đơn/tin đang gửi dở. Một tool call dài hơn _IDLE_TTL là hiếm nhưng có thật.
        for key in [k for k, v in self._sessions.items()
                    if now - v["last"] > _IDLE_TTL and not v.get("ban")]:
            ent = self._sessions.pop(key, None)
            if ent:
                self._close_later(ent["obj"])

    def _make(self, spec):
        t = spec.get("transport") or "http"
        if t == "stdio":
            return McpStdioSession(spec.get("command", ""), spec.get("args"), spec.get("env"),
                                   label=spec.get("label", ""))
        if t == "internal":
            return McpInternalSession(spec.get("internal", ""), spec)
        return McpHttpSession(spec.get("url", ""), spec.get("headers"))

    def _get(self, spec):
        self._sweep()
        key = spec.get("key") or _spec_hash(spec)
        h = _spec_hash(spec)
        ent = self._sessions.get(key)
        if ent and ent["hash"] != h:   # đổi key/URL/env → session cũ vô hiệu
            self._close_later(ent["obj"])
            ent = None
            self._sessions.pop(key, None)
        if not ent:
            ent = {"obj": self._make(spec), "hash": h, "last": time.time()}
            self._sessions[key] = ent
        ent["last"] = time.time()
        return key, ent["obj"]

    def _danh_dau_ban(self, key, delta):
        ent = self._sessions.get(key)
        if ent is not None:
            ent["ban"] = max(0, int(ent.get("ban", 0)) + delta)
            ent["last"] = time.time()

    def dang_goi_tool(self, spec) -> bool:
        """Phiên của spec này có đang chạy dở một tool call không.

        Dùng ở chỗ DÒ TOOL: `tools/list` quá hạn trong lúc phiên đang bận nghĩa là nó mới chỉ
        XẾP HÀNG chờ khoá chứ chưa gửi đi byte nào - khác hẳn "server treo giữa request"."""
        ent = self._sessions.get(spec.get("key") or _spec_hash(spec))
        return bool(ent and ent.get("ban"))

    def tool_da_biet(self, spec):
        """Danh sách tool của lần dò gần nhất trên phiên này (None nếu chưa dò được lần nào)."""
        ent = self._sessions.get(spec.get("key") or _spec_hash(spec))
        return (ent or {}).get("tools")

    def invalidate(self, key):
        ent = self._sessions.pop(key, None)
        if ent:
            self._close_later(ent["obj"])

    async def close_all(self):
        for key in list(self._sessions):
            ent = self._sessions.pop(key, None)
            if ent:
                try:
                    await ent["obj"].close()
                except Exception:
                    pass

    @staticmethod
    def _pre_send_error(e):
        """Lỗi CHẮC CHẮN xảy ra trước khi request chạm server → retry không gây side-effect đôi."""
        return isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout, ConnectionError))

    async def _retry(self, spec, op, idempotent=True, ban=False):
        """Chạy op(session); lỗi → dựng session mới, thử lại ĐÚNG 1 lần.
        Tool KHÔNG idempotent (tools/call - có thể là gửi tin/tạo đơn): CHỈ retry khi lỗi
        thuộc pha kết nối (chưa gửi được request) - timeout giữa chừng KHÔNG gọi lại,
        tránh người thật nhận tin 2 lần / tạo đơn trùng.

        `ban=True` bật cờ "phiên đang chạy tool" suốt lúc op chạy, để vòng dò tool và vòng
        quét phiên rảnh biết mà TRÁNH giết phiên này."""
        key, sess = self._get(spec)
        try:
            return await self._chay(key, sess, op, ban)
        except Exception as e:
            self.invalidate(key)
            if not (idempotent or self._pre_send_error(e)):
                raise
            key, sess = self._get(spec)
            return await self._chay(key, sess, op, ban)   # lần 2 lỗi thì raise cho caller

    async def _chay(self, key, sess, op, ban):
        if not ban:
            return await op(sess)
        self._danh_dau_ban(key, 1)
        try:
            return await op(sess)
        finally:
            self._danh_dau_ban(key, -1)

    async def list_tools(self, spec):
        tools = await self._retry(spec, lambda s: s.list_tools(), idempotent=True)
        # Nhớ lại để vòng dò sau còn thứ mà dùng khi phiên đang bận (xem `tool_da_biet`).
        ent = self._sessions.get(spec.get("key") or _spec_hash(spec))
        if ent is not None and tools:
            ent["tools"] = tools
        return tools

    async def call_tool(self, spec, tool, arguments):
        # Chèn tham số kỹ thuật BẮT BUỘC của connector (catalog `inject_args`) vào đây - đây là
        # chốt DUY NHẤT mọi đường gọi đi qua: hub `_guard`, nút Test ở `validate_connection`,
        # meta-tool `run` của lớp lazy, và cả route legacy. Đặt ở `_guard` thôi là nút Test đi
        # đường vòng rồi báo đỏ trong khi kết nối vẫn tốt. Model đưa gì thì giữ nguyên cái đó.
        args = arguments or {}
        inject = spec.get("inject_args") or {}
        if inject:
            try:
                import mcp_catalog
                args = mcp_catalog.merge_inject_args(args, inject)
            except Exception as e:
                print(f"[mcp] inject_args {spec.get('label')}: {type(e).__name__}: {e}",
                      file=sys.stderr)
        try:
            return await self._retry(spec, lambda s: s.call_tool(tool, args), idempotent=False,
                                     ban=True)
        except Exception as e:
            return f"ERROR: gọi tool lỗi: {type(e).__name__}: {e}"


pool = SessionPool()


# ============================================================
# Discover + route
# ============================================================
def _legacy_spec(s):
    return {"key": f"legacy:{s.get('name')}:{s.get('url')}", "transport": s.get("transport") or "http",
            "url": s.get("url"), "headers": s.get("headers") or {}, "label": s.get("name", "")}


def _conn_spec(conn):
    return {"key": conn["id"], "transport": conn.get("transport") or "http",
            "url": conn.get("url"), "headers": dict(conn.get("headers") or {}),
            "command": conn.get("command"), "args": conn.get("args") or [],
            "env": conn.get("env") or {}, "internal": conn.get("internal") or "",
            "secrets": conn.get("secrets") or {}, "config": conn.get("config") or {},
            "inject_args": conn.get("inject_args") or {},
            "label": conn.get("label", "")}


def co_server_de_dial(conn) -> bool:
    """Connection này có thứ gì để MỞ PHIÊN không. Nhận cả bản `resolved()` lẫn `_conn_spec()`.

    Ba dạng CÓ: http (`url`), stdio (`command`), và **internal** (module Python trong repo,
    xem `_INTERNAL`). Dạng KHÔNG có là connection chỉ giữ token OAuth cho một plugin dùng
    (vd Meta Ads Graph API): trang Kết nối vẫn hiện nó, nhưng không có MCP server nào để dial.

    Vì sao phải là một hàm dùng chung chứ không viết tay ở từng chỗ: câu hỏi này được hỏi ở
    BA nơi (dò tool ở `discover_resolved`, nút Test ở `mcp_hub.validate_connection`, vòng kiểm
    sức khoẻ ở `connect_health`) và cả ba từng viết tay `not (url or command)`. Transport
    internal không có url cũng không có command, nên **Substack và Botcake rơi hết vào nhánh
    "không có server"**: vòng dò quét sạch chúng nên không bộ não nào gọi được tool, trong khi
    hai chỗ kia lại trả về "ổn" mà chưa hề gọi thử. Kết quả là trang Kết nối báo xanh, hộp
    công cụ thì trống, và không có một dòng lỗi nào ở đâu cả.
    """
    if (conn.get("url") or "").strip() or (conn.get("command") or "").strip():
        return True
    # Có tên module thì mới tính. Transport internal mà tên rỗng là bản ghi hỏng: cho đi tiếp
    # chỉ đổi một lỗi im lặng thành một KeyError mỗi vòng dò.
    return ((conn.get("transport") or "") == "internal"
            and (conn.get("internal") or "").strip() in _INTERNAL)


async def _oauth_headers(conn):
    """Connection auth=oauth → hub/oauth_mcp giữ token, merge vào headers (lazy import tránh vòng)."""
    if conn.get("auth") != "oauth":
        return {}
    try:
        import oauth_mcp
        return await oauth_mcp.auth_headers(conn["id"])
    except ImportError:
        return {}
    except Exception as e:
        print(f"[mcp oauth] {e}", file=sys.stderr)
        return {}


async def discover(servers):
    """LEGACY: servers [{name,url,headers,transport,deny_tools}] → (tools_spec, route).
    Giữ nguyên shape cũ; chạy qua pool nên nhanh hơn (session tái dùng)."""
    tools_spec, route = [], {}
    for s in servers:
        deny = set(s.get("deny_tools") or [])
        spec = _legacy_spec(s)
        try:
            tools = await pool.list_tools(spec)
        except Exception:
            continue
        for t in tools:
            tname = t.get("name")
            if not tname or tname in deny:
                continue
            fn = _mk_fn(s["name"], tname, route)
            route[fn] = {"server": s, "tool": tname}
            tools_spec.append({
                "fn": fn, "server": s["name"], "name": tname,
                "description": (t.get("description") or tname),
                "schema": t.get("inputSchema") or {"type": "object", "properties": {}},
            })
    return tools_spec, route


def tran_dial():
    """Trần dò tool cho MỘT connection (giây). Trả None = không giới hạn.

    Vì sao phải có trần: danh sách tool của hub nằm trên ĐƯỜNG GĂNG của mọi lượt chat qua
    Claude Code. Lúc khởi động, `claude` đấu xong MCP rồi mới nhận việc, mà SDK chỉ chờ
    `initialize` 60 giây. Một connection chết mà cứ để nó chạy hết trần riêng của transport
    (http 60s, stdio 90s lúc init) là một mình nó thổi bay cả lượt chat - lỗi người dùng thật
    gặp ngày 2026-08-11: "chạy rất lâu rồi báo Control request timeout: initialize".

    Bỏ nguồn chậm ở vòng này KHÔNG mất gì lâu dài: cache hub hết hạn sau 60s là dò lại, và
    nguồn khoẻ vẫn lên tool đầy đủ ngay lượt đó.
    """
    raw = os.getenv("JAVIS_MCP_DISCOVER_TIMEOUT", _DIAL_TRAN)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = float(_DIAL_TRAN)
    return v if v > 0 else None


def tran_warm():
    """Trần MỘT connection ở vòng LÀM NÓNG lúc khởi động (giây). None = không giới hạn.

    Phải RỘNG HƠN HẲN `tran_dial()` vì hai vòng trả lời hai câu hỏi khác nhau. Vòng dò của
    một lượt chat có người đang ngồi chờ, nên 20 giây là đúng: thà thiếu một nguồn còn hơn
    treo cả lượt. Vòng làm nóng thì KHÔNG AI CHỜ - nó chạy vài giây sau khi server lên, chỉ
    để mở sẵn phiên. Cắt nó ở 20 giây là cắt đúng thứ nó sinh ra để làm, vì mọi việc nặng
    của một phiên nguội đều nằm quá mốc đó: `npx -y` / `uvx` phải TẢI package lần đầu (bản
    Docker mất sạch cache npm/uv sau mỗi lần đổi ảnh), và máy chủ HTTP phía dịch vụ cũng
    phải dựng lại phiên từ đầu.
    """
    raw = os.getenv("JAVIS_MCP_WARM_TIMEOUT", _WARM_TRAN)
    try:
        v = float(raw)
    except (TypeError, ValueError):
        v = float(_WARM_TRAN)
    return v if v > 0 else None


async def warm_pool(conns):
    """Mở sẵn phiên MCP cho từng connection. Trả (id đã nóng, id còn nguội). Không bao giờ raise.

    Đây là vòng chạy NỀN lúc khởi động, không phải đường găng của lượt chat, nên nó khác
    `discover_resolved` ở đúng hai chỗ: chờ theo `tran_warm()` (rộng gấp nhiều lần) và không
    quan tâm tool là gì - chỉ cần phiên nằm sẵn trong pool để vòng dò kế tiếp trả lời tức thì.

    Vì sao cần (báo cáo 31/08: "khi update rất hay bị mất kết nối với các MCP"): sau mỗi lần
    cập nhật, pool rỗng và cache npm/uv trong ảnh Docker cũng mất theo. Nguồn nào nguội quá 20
    giây là rơi khỏi vòng dò đầu tiên, mà danh sách tool của vòng đó lại được cache và được
    CLI engine đọc đúng một lần lúc mở phiên - nên nguồn đó biến mất khỏi hộp công cụ suốt cả
    phiên chat, dù kết nối chẳng hỏng gì.
    """
    tran = tran_warm()
    sem = asyncio.Semaphore(_DIAL_SONG_SONG)
    nong, con_lanh = [], []

    async def _mo(conn):
        spec = _conn_spec(conn)
        if not co_server_de_dial(spec):
            return                      # connector ảo: không có phiên nào để mở

        async def _lay():
            spec["headers"].update(await _oauth_headers(conn))
            return await pool.list_tools(spec)

        async with sem:
            try:
                if tran is None:
                    await _lay()
                else:
                    await asyncio.wait_for(_lay(), timeout=tran)
                nong.append(conn["id"])
                return
            except (asyncio.TimeoutError, TimeoutError):
                # Cùng lý do như `discover_resolved`: huỷ từ ngoài giữa một request NDJSON là
                # ống stdio lệch pha vĩnh viễn - vứt phiên chứ đừng tái dùng. TRỪ khi phiên
                # đang chạy dở một tool call: lúc đó `tools/list` mới chỉ chờ khoá, chưa gửi
                # gì, mà giết phiên là giết luôn việc đang chạy.
                if pool.dang_goi_tool(spec):
                    print(f"[mcp warm] {conn.get('label')}: đang chạy tool - để nguyên phiên",
                          file=sys.stderr)
                else:
                    pool.invalidate(spec.get("key") or _spec_hash(spec))
                    print(f"[mcp warm] {conn.get('label')}: quá hạn làm nóng", file=sys.stderr)
            except Exception as e:
                print(f"[mcp warm] {conn.get('label')}: {type(e).__name__}: {e}", file=sys.stderr)
        con_lanh.append(conn["id"])

    if conns:
        await asyncio.gather(*(_mo(c) for c in conns))
    return nong, con_lanh


async def discover_resolved(conns, bo_qua=None):
    """conns = mcp_store.resolved() → (tools_spec, route) namespaced theo connection.
    Conn nào không kết nối được thì BỎ QUA (không raise) để nguồn khác vẫn chạy.

    `bo_qua`: truyền vào một set để NHẬN LẠI id những connection đã bị bỏ ở vòng này. Caller
    cần nó để biết danh sách tool vừa dựng là bản THIẾU chứ không phải bản đủ - `mcp_hub` dùng
    đúng chỗ đó để cache ngắn hạn thay vì đóng băng một danh sách thiếu nguồn trong 60 giây.

    Dò SONG SONG (trước 0.26.18 là tuần tự): tổng thời gian nay xấp xỉ nguồn CHẬM NHẤT chứ
    không còn là tổng của mọi nguồn. Máy đấu chục connector thì đây là khác biệt giữa vài giây
    và vài phút. Thứ tự kết quả vẫn theo đúng thứ tự `conns` để tên tool (`_mk_fn` chống trùng
    bằng hậu tố) không đổi giữa hai lần dò.
    """
    tran = tran_dial()
    sem = asyncio.Semaphore(_DIAL_SONG_SONG)

    async def _dial(conn):
        """(spec, tools|None) cho 1 connection. Không bao giờ raise."""
        spec = _conn_spec(conn)
        # Connection OAuth-only (giữ token, tool đến từ plugin - vd Meta Ads Graph API): không có
        # MCP server để discover → bỏ qua sạch, không thử kết nối (khỏi log lỗi mỗi vòng).
        # Transport `internal` KHÔNG thuộc nhóm này dù cũng không có url/command - xem
        # `co_server_de_dial`, và xem cả cái giá đã trả khi nhầm hai thứ đó với nhau.
        if not co_server_de_dial(spec):
            return spec, None

        async def _lay():
            spec["headers"].update(await _oauth_headers(conn))
            return await pool.list_tools(spec)

        async with sem:
            try:
                if tran is None:
                    return spec, await _lay()
                return spec, await asyncio.wait_for(_lay(), timeout=tran)
            except (asyncio.TimeoutError, TimeoutError):
                # Quá hạn ở đây có HAI nghĩa khác hẳn nhau, và trước 0.52.8 cả hai bị xử như một.
                #
                # (a) Phiên ĐANG CHẠY DỞ một tool call thật (tạo đơn POS, gửi tin...). Khoá
                #     phiên đang bị cái đó giữ, nên `tools/list` mới chỉ XẾP HÀNG chứ chưa gửi
                #     đi byte nào: ống stdio không hề lệch pha. Giết phiên lúc này là SIGKILL cả
                #     cây tiến trình, tức là giết luôn cái đơn đang lên dở - đúng lỗi "lên đơn
                #     thứ 2 là rớt kết nối" khách của chủ repo báo 01/09/2026. Giữ phiên, và trả
                #     lại danh sách tool lần dò trước để nguồn KHÔNG biến mất khỏi hộp công cụ
                #     chỉ vì nó đang bận (biến mất là Javis nói "chưa đấu POS", cũng sai nốt).
                # (b) Server thật sự treo giữa một request: huỷ từ ngoài để lại nửa câu trả lời
                #     trong ống, lần sau đọc là lệch pha vĩnh viễn - vứt phiên, đừng tái dùng.
                if pool.dang_goi_tool(spec):
                    cu = pool.tool_da_biet(spec)
                    print(f"[mcp discover] {conn.get('label')}: đang chạy tool - giữ phiên, "
                          f"dùng lại danh sách tool lần trước ({len(cu or [])} tool)",
                          file=sys.stderr)
                    if cu:
                        return spec, cu
                else:
                    pool.invalidate(spec.get("key") or _spec_hash(spec))
                    print(f"[mcp discover] {conn.get('label')}: quá hạn dò tool - bỏ qua vòng này",
                          file=sys.stderr)
            except Exception as e:
                print(f"[mcp discover] {conn.get('label')}: {type(e).__name__}: {e}", file=sys.stderr)
        if bo_qua is not None:
            bo_qua.add(conn["id"])
        return spec, None

    ket = await asyncio.gather(*(_dial(c) for c in conns)) if conns else []

    tools_spec, route = [], {}
    for conn, (spec, tools) in zip(conns, ket):
        if not tools:
            continue
        deny = set(conn.get("deny_tools") or [])
        ns = conn.get("namespace") or conn.get("slug") or conn["id"]
        for t in tools:
            tname = t.get("name")
            if not tname or tname in deny:
                continue
            fn = _mk_fn(ns, tname, route)
            route[fn] = {"spec": spec, "tool": tname,
                         "conn": {"id": conn["id"], "namespace": ns, "perm": conn.get("perm") or "full",
                                  "deny_tools": conn.get("deny_tools") or [], "label": conn.get("label", ""),
                                  "connector_id": conn.get("connector_id", "custom")}}
            tools_spec.append({
                "fn": fn, "server": ns, "name": tname,
                "description": (t.get("description") or tname),
                "schema": t.get("inputSchema") or {"type": "object", "properties": {}},
                "conn_id": conn["id"], "connector_id": conn.get("connector_id", "custom"),
                "namespace": ns, "label": conn.get("label", ""),
            })
    return tools_spec, route


async def call_route(route, fn, arguments):
    """Gọi 1 tool theo fn. Entry: {"call"} (hub bọc sẵn) | {"spec","tool"} (pool) | {"server","tool"} (legacy)."""
    ent = route.get(fn)
    if not ent:
        return f"ERROR: tool '{fn}' không tồn tại"
    try:
        if ent.get("call"):
            return await ent["call"](arguments or {})
        if ent.get("spec") is not None:
            return await pool.call_tool(ent["spec"], ent["tool"], arguments or {})
        if ent.get("server") is not None:
            return await pool.call_tool(_legacy_spec(ent["server"]), ent["tool"], arguments or {})
    except Exception as e:
        return f"ERROR: gọi tool lỗi: {type(e).__name__}: {e}"
    return f"ERROR: route entry hỏng cho '{fn}'"
