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
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

import httpx

PROTOCOL = "2025-06-18"
_IDLE_TTL = 600          # đóng session không dùng > 10 phút
_INTERNAL = {"botcake": "botcake_mcp", "substack": "substack_mcp"}   # transport internal → tên module


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
        self._stderr = deque(maxlen=20)
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
        env = dict(os.environ)
        env.update(self.env)
        self.proc = await asyncio.create_subprocess_exec(
            *self._argv(), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=env, limit=self._STREAM_LIMIT, **kwargs)
        asyncio.ensure_future(self._drain_stderr())

    def _err_tail(self):
        return " | ".join(list(self._stderr)[-5:])[:400]

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

    async def close(self):
        try:
            if self.alive():
                self.proc.kill()
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
        for key in [k for k, v in self._sessions.items() if now - v["last"] > _IDLE_TTL]:
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

    async def _retry(self, spec, op, idempotent=True):
        """Chạy op(session); lỗi → dựng session mới, thử lại ĐÚNG 1 lần.
        Tool KHÔNG idempotent (tools/call - có thể là gửi tin/tạo đơn): CHỈ retry khi lỗi
        thuộc pha kết nối (chưa gửi được request) - timeout giữa chừng KHÔNG gọi lại,
        tránh người thật nhận tin 2 lần / tạo đơn trùng."""
        key, sess = self._get(spec)
        try:
            return await op(sess)
        except Exception as e:
            self.invalidate(key)
            if not (idempotent or self._pre_send_error(e)):
                raise
            key, sess = self._get(spec)
            return await op(sess)   # lần 2 lỗi thì raise cho caller xử lý

    async def list_tools(self, spec):
        return await self._retry(spec, lambda s: s.list_tools(), idempotent=True)

    async def call_tool(self, spec, tool, arguments):
        try:
            return await self._retry(spec, lambda s: s.call_tool(tool, arguments), idempotent=False)
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


async def discover_resolved(conns):
    """conns = mcp_store.resolved() → (tools_spec, route) namespaced theo connection.
    Conn nào không kết nối được thì BỎ QUA (không raise) để nguồn khác vẫn chạy."""
    tools_spec, route = [], {}
    for conn in conns:
        deny = set(conn.get("deny_tools") or [])
        spec = _conn_spec(conn)
        # Connection OAuth-only (giữ token, tool đến từ plugin - vd Meta Ads Graph API): không có
        # MCP server để discover → bỏ qua sạch, không thử kết nối (khỏi log lỗi mỗi vòng).
        # Transport `internal` KHÔNG thuộc nhóm này dù cũng không có url/command - xem
        # `co_server_de_dial`, và xem cả cái giá đã trả khi nhầm hai thứ đó với nhau.
        if not co_server_de_dial(spec):
            continue
        spec["headers"].update(await _oauth_headers(conn))
        try:
            tools = await pool.list_tools(spec)
        except Exception as e:
            print(f"[mcp discover] {conn.get('label')}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
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
