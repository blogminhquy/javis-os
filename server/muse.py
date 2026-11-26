"""Muse (Meta's AI app at muse.ai) as a model provider, through Muse Gateway.

Owner 26/11/2026: "connect Muse like ChatGPT and Claude, paste it into the Models page, use it as a fallback, and let
it run background work". Muse has no public API. Muse Gateway (a separate program, `muse serve`, by default on
127.0.0.1:8080) logs in with each Muse account's session cookie and serves an OpenAI-style API on /v1; it already
pools its accounts (every request goes to the least busy enabled account). Javis talks to it over HTTP:

- the admin routes add an account from a pasted cookie, switch one off or on, replace its cookie, remove it;
- /v1/chat/completions runs a chat turn or a background job.

Tools through text. The gateway flattens a chat into one prompt for Muse and has no `tools` field, so on its own Muse
could only answer in words and background work that needs a tool (write a file, read a connection) could not run. The
owner chose to teach it (26/11/2026). `ToolTextTransport` sits under the shared OpenAI tool loop
(`engine._cc_tool_loop`): it writes the request's tools into a short protocol in the system prompt, turns earlier tool
calls and results into plain messages, and reads a <tool_calls> block in Muse's reply back into OpenAI `tool_calls`.
Everything else (permission levels, the round cap, the loop guard) stays the loop's own.

The admin key comes from the Models page (encrypted in settings, `model.muse_key`), else MUSE_ADMIN_KEY, else the
gateway's own config.json on this machine. It is only ever sent to the gateway's address. Cookies are not stored by
Javis at all: they go straight to the gateway, which keeps them.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import httpx

PROVIDER = "muse"
MODEL = "muse-1"
DEFAULT_BASE = "http://127.0.0.1:8080"
# A Muse turn that browses the web runs long; the gateway's own cap is 1200 seconds.
TURN_TIMEOUT_S = 600
_BASE_RE = re.compile(r"^https?://[A-Za-z0-9.\-\[\]:]+$")
_COOKIE_RE = re.compile(r"hatch_sess=[^;\s]+")


class GatewayError(Exception):
    """A sentence the owner can read: what went wrong and what to do."""


def _say(vi: str, en: str) -> str:
    """Words for the screen, in the language of whoever is looking (localefmt.chu)."""
    try:
        import localefmt
        return localefmt.chu(vi, en)
    except Exception:  # noqa: BLE001 - a test without the app around still gets a sentence
        return vi


# ---------------------------------------------------------------- settings
def gateway_config_path() -> Path:
    """The gateway's own config.json (it holds admin_key). Same folder the gateway picks: %APPDATA% on Windows,
    $XDG_CONFIG_HOME or ~/.config elsewhere; MUSE_GATEWAY_CONFIG overrides."""
    root = os.getenv("APPDATA") or os.getenv("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(os.getenv("MUSE_GATEWAY_CONFIG") or Path(root) / "MuseGateway" / "config.json")


def clean_base(url: str) -> str:
    """An address the owner typed: scheme and host[:port] only. No path, no user:password@ (a key there would sit in
    plain text in settings and in every log line that prints the address)."""
    u = str(url or "").strip().rstrip("/")
    if u.endswith("/v1"):
        u = u[:-3].rstrip("/")
    if not _BASE_RE.match(u):
        raise GatewayError(_say("Địa chỉ Muse Gateway phải có dạng http://máy:cổng, ví dụ http://127.0.0.1:8080.",
                                "The Muse Gateway address must look like http://host:port, for example "
                                "http://127.0.0.1:8080."))
    return u


def base(mcfg: dict) -> str:
    """Gateway address: saved on the Models page, else MUSE_GATEWAY_URL, else 127.0.0.1:8080."""
    return (str((mcfg or {}).get("muse_base") or "").strip() or os.getenv("MUSE_GATEWAY_URL", "").strip()
            or DEFAULT_BASE).rstrip("/")


def chat_url(mcfg: dict) -> str:
    return base(mcfg) + "/v1/chat/completions"


def _config_key() -> str:
    try:
        return str(json.loads(gateway_config_path().read_text(encoding="utf-8")).get("admin_key") or "").strip()
    except (OSError, ValueError, AttributeError):
        return ""


def admin_key(mcfg: dict) -> str:
    """The gateway's admin key, "" when none is known."""
    return (str((mcfg or {}).get("muse_key") or "").strip() or os.getenv("MUSE_ADMIN_KEY", "").strip()
            or _config_key())


def key_source(mcfg: dict) -> str:
    """Where the key comes from, for the card: "page", "env", "machine", or "" (none)."""
    if str((mcfg or {}).get("muse_key") or "").strip():
        return "page"
    if os.getenv("MUSE_ADMIN_KEY", "").strip():
        return "env"
    return "machine" if _config_key() else ""


def connected(mcfg: dict) -> bool:
    """The card is signed in: the owner connected an account here and did not press Disconnect since. Read from
    settings only, never from the network: `_providers_view` runs inside the request that draws the page."""
    return bool((mcfg or {}).get("muse_on"))


def valid_cookie(text: str) -> bool:
    s = str(text or "").strip()
    return bool(_COOKIE_RE.search(s)) or s.startswith("wss://")


# ---------------------------------------------------------------- admin calls (sync; callers use a thread)
def _request(mcfg: dict, method: str, path: str, body=None, timeout: float = 90) -> dict:
    if not path.startswith("/") or path.startswith("//"):
        raise GatewayError(_say("Đường dẫn Muse Gateway không hợp lệ.", "Invalid Muse Gateway path."))
    key = admin_key(mcfg)
    if not key:
        raise GatewayError(_say("Chưa có khoá quản trị của Muse Gateway. Điền khoá ở mục Muse Gateway của thẻ Muse "
                                "(lấy bằng lệnh muse info trên máy chạy gateway).",
                                "No Muse Gateway admin key yet. Enter it under Muse Gateway on the Muse card (run "
                                "muse info on the machine that runs the gateway)."))
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base(mcfg) + path, data=data, method=method, headers={
        "Authorization": "Bearer " + key, "Accept": "application/json",
        **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as ex:
        text = ex.read().decode("utf-8", "replace")
        try:
            msg = (json.loads(text).get("error") or {}).get("message") or text
        except (ValueError, AttributeError):
            msg = text
        if ex.code in (401, 403):
            raise GatewayError(_say("Muse Gateway từ chối khoá quản trị. Kiểm lại khoá ở mục Muse Gateway của thẻ Muse.",
                                    "Muse Gateway refused the admin key. Check it under Muse Gateway on the Muse card."))
        raise GatewayError(_say(f"Muse Gateway trả lỗi {ex.code}: {str(msg)[:200]}",
                                f"Muse Gateway returned {ex.code}: {str(msg)[:200]}"))
    except Exception as ex:  # noqa: BLE001 - every network failure reads the same to the owner
        raise GatewayError(_say(f"Không nối được Muse Gateway ở {base(mcfg)} ({type(ex).__name__}). Bật gateway "
                                "lên, hoặc sửa địa chỉ ở mục Muse Gateway của thẻ Muse.",
                                f"Could not reach Muse Gateway at {base(mcfg)} ({type(ex).__name__}). Start the "
                                "gateway, or fix the address under Muse Gateway on the Muse card."))
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        raise GatewayError(_say(f"Địa chỉ {base(mcfg)} không phải Muse Gateway.",
                                f"{base(mcfg)} is not a Muse Gateway."))


def _q(aid: str) -> str:
    return urllib.parse.quote(str(aid or ""), safe="")


def accounts(mcfg: dict) -> list:
    """The gateway's accounts, oldest first, with nothing secret: id, label, on/off, online, last error."""
    out = []
    for a in (_request(mcfg, "GET", "/api/admin/accounts").get("data") or []):
        live = a.get("live") or {}
        out.append({"id": str(a.get("id") or ""), "label": str(a.get("name") or ""), "enabled": bool(a.get("enabled")),
                    "online": bool(live.get("connected")), "error": str(a.get("last_error") or "")[:200],
                    "created_at": str(a.get("created_at") or "")})
    out.sort(key=lambda a: (a["created_at"], a["id"]))
    return out


def test_account(mcfg: dict, aid: str) -> tuple:
    r = _request(mcfg, "POST", f"/api/admin/accounts/{_q(aid)}/test", {}, timeout=100)
    return bool(r.get("ok")), str(r.get("error") or "")[:200]


def add_account(mcfg: dict, label: str, cookie: str) -> dict:
    """Add one Muse account from a pasted cookie. {"id", "ok", "error"}: `ok` is the gateway's live test."""
    if not valid_cookie(cookie):
        raise GatewayError(_say("Cookie phải có hatch_sess=... (hoặc là link wss://). Chép cả dòng Cookie của muse.ai.",
                                "The cookie must hold hatch_sess=... (or be a wss:// link). Copy the whole "
                                "Cookie line of muse.ai."))
    r = _request(mcfg, "POST", "/api/admin/accounts",
                 {"name": str(label or "").strip()[:60], "credential": str(cookie).strip(), "proxy": ""}, timeout=120)
    acc = r.get("account") or r.get("data") or r
    aid = str((acc or {}).get("id") or "") if isinstance(acc, dict) else ""
    test = r.get("test") or {}
    if aid and not test:
        ok, err = test_account(mcfg, aid)
        test = {"ok": ok, "error": err}
    _forget_view()
    return {"id": aid, "ok": bool(test.get("ok")), "error": str(test.get("error") or "")[:200]}


def set_enabled(mcfg: dict, aid: str, on: bool) -> None:
    _request(mcfg, "PATCH", f"/api/admin/accounts/{_q(aid)}", {"enabled": bool(on)})
    _forget_view()


def replace_cookie(mcfg: dict, aid: str, cookie: str) -> dict:
    """A fresh cookie for an account whose session ran out. Same answer shape as `add_account`."""
    if not valid_cookie(cookie):
        raise GatewayError(_say("Cookie phải có hatch_sess=... (hoặc là link wss://). Chép cả dòng Cookie của muse.ai.",
                                "The cookie must hold hatch_sess=... (or be a wss:// link). Copy the whole "
                                "Cookie line of muse.ai."))
    _request(mcfg, "PATCH", f"/api/admin/accounts/{_q(aid)}", {"credential": str(cookie).strip(), "enabled": True})
    ok, err = test_account(mcfg, aid)
    _forget_view()
    return {"id": aid, "ok": ok, "error": err}


def remove_account(mcfg: dict, aid: str) -> None:
    _request(mcfg, "DELETE", f"/api/admin/accounts/{_q(aid)}")
    _forget_view()


# ---------------------------------------------------------------- what the card shows
# The page draws from settings without waiting on the network, so the accounts come from this short-lived copy. A
# stale or missing copy is refreshed in a thread and the page asks /provider/muse/status for the fresh one.
_VIEW_TTL_S = 20
_view_lock = threading.Lock()
_view = {"at": 0.0, "data": None, "busy": False}


def _forget_view() -> None:
    with _view_lock:
        _view["at"] = 0.0


def view(mcfg: dict) -> dict:
    """Fresh state of the gateway for the card: {"ok", "error", "base", "key_from", "accounts"}."""
    out = {"ok": True, "error": "", "base": base(mcfg), "key_from": key_source(mcfg), "accounts": []}
    try:
        out["accounts"] = accounts(mcfg)
    except GatewayError as ex:
        out.update(ok=False, error=str(ex))
    with _view_lock:
        _view.update(at=time.time(), data=out, busy=False)
    return out


def cached_view(mcfg: dict) -> dict:
    """Last known state, never blocking. `checking` is True when no state is known yet; a stale state is refreshed
    in a background thread for the next draw."""
    with _view_lock:
        data, fresh = _view["data"], time.time() - _view["at"] < _VIEW_TTL_S
        start = not fresh and not _view["busy"]
        if start:
            _view["busy"] = True
    if start:
        snapshot = dict(mcfg or {})
        threading.Thread(target=view, args=(snapshot,), daemon=True, name="muse-view").start()
    if data is None:
        return {"ok": True, "error": "", "base": base(mcfg), "key_from": key_source(mcfg), "accounts": [],
                "checking": True}
    return {**data, "base": base(mcfg), "key_from": key_source(mcfg)}


# ---------------------------------------------------------------- tools through text
_BLOCK_RE = re.compile(r"<tool_calls?>\s*(.*?)\s*</tool_calls?>", re.S | re.I)
_FENCE_RE = re.compile(r"```(?:json|tool_calls?)?\s*([\[{].*?[\]}])\s*```", re.S | re.I)
_MAX_SCHEMA_CHARS = 1500


def _text(content) -> str:
    """Plain text of a message content (a string, or OpenAI content parts)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(p.get("text") or "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return "" if content is None else str(content)


def _schema(params) -> str:
    s = json.dumps(params or {"type": "object", "properties": {}}, ensure_ascii=False, separators=(",", ":"))
    return s if len(s) <= _MAX_SCHEMA_CHARS else s[:_MAX_SCHEMA_CHARS] + "...(cut)"


def tool_names(tools) -> set:
    out = set()
    for t in tools or []:
        fn = (t or {}).get("function") or {}
        if fn.get("name"):
            out.add(str(fn["name"]))
    return out


def tools_prompt(tools, choice=None) -> str:
    """The protocol and the tool list, as one system message (English, like every prompt Javis sends a model)."""
    lines = [
        "# === TOOLS ===",
        "You work inside Javis and can use the tools listed below. Javis runs them on the owner's machine and "
        "sends back the result. Use them instead of saying you cannot do something, and instead of running the same "
        "work in your own sandbox: only these tools reach the owner's files and connections.",
        "To call tools, reply with ONLY this block, nothing before or after it:",
        "<tool_calls>",
        '[{"name": "tool_name", "arguments": {"param": "value"}}]',
        "</tool_calls>",
        "The list may hold several calls. Javis then sends each result in a message that starts with "
        "[tool result: tool_name]. Read it, then call more tools or write the final answer as plain text without "
        "the block. Never write a tool result yourself, and never use the block for anything but a real call.",
    ]
    if choice == "required":
        lines.append("In this reply you MUST call at least one tool.")
    elif isinstance(choice, dict) and ((choice.get("function") or {}).get("name")):
        lines.append(f"In this reply you MUST call the tool {choice['function']['name']}.")
    lines.append("Tools:")
    for t in tools or []:
        fn = (t or {}).get("function") or {}
        if not fn.get("name"):
            continue
        desc = " ".join(str(fn.get("description") or "").split())
        lines.append(f"- {fn['name']}: {desc}\n  parameters: {_schema(fn.get('parameters'))}")
    return "\n".join(lines)


def _args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


def gateway_messages(messages, tools=None, choice=None) -> list:
    """OpenAI messages (with tool calls and results) as plain messages the gateway takes. The gateway also needs the
    last message to come from the user: trailing notes Javis adds as system messages are folded into one."""
    out = []
    if tools:
        out.append({"role": "system", "content": tools_prompt(tools, choice)})
    call_names = {}
    for m in messages or []:
        role = (m or {}).get("role") or "user"
        if role == "assistant":
            text = _text(m.get("content")).strip()
            calls = m.get("tool_calls") or []
            if calls:
                block = []
                for c in calls:
                    fn = (c or {}).get("function") or {}
                    call_names[c.get("id")] = fn.get("name") or "tool"
                    block.append({"name": fn.get("name"), "arguments": _args(fn.get("arguments"))})
                text = (text + "\n" if text else "") + "<tool_calls>\n" + json.dumps(block, ensure_ascii=False) \
                    + "\n</tool_calls>"
            out.append({"role": "assistant", "content": text})
        elif role == "tool":
            name = call_names.get(m.get("tool_call_id")) or m.get("name") or "tool"
            out.append({"role": "user", "content": f"[tool result: {name}]\n{_text(m.get('content'))}"})
        elif role in ("system", "developer"):
            out.append({"role": "system", "content": _text(m.get("content"))})
        else:
            out.append({"role": "user", "content": m.get("content")})
    tail = []
    while out and out[-1]["role"] == "system" and len(out) > 1 and any(x["role"] != "system" for x in out):
        tail.insert(0, out.pop()["content"])
    if tail:
        out.append({"role": "user", "content": "[Javis]\n" + "\n\n".join(tail)})
    if not out or out[-1]["role"] != "user":
        out.append({"role": "user", "content": "Continue."})
    return out


def parse_tool_calls(text: str, names) -> tuple:
    """(text before the calls, [{"name", "arguments"}]) from a Muse reply. Only calls to tools in `names` count, so a
    JSON sample in an ordinary answer is never taken for a call."""
    text = str(text or "")
    m = _BLOCK_RE.search(text)
    if m:
        raw, before = m.group(1), text[:m.start()]
        inner = _FENCE_RE.search(raw)
        if inner:
            raw = inner.group(1)
    else:
        m = _FENCE_RE.search(text)
        if not m:
            return text, []
        raw, before = m.group(1), text[:m.start()]
    try:
        data = json.loads(raw)
    except ValueError:
        return text, []
    if isinstance(data, dict):
        data = data.get("tool_calls") or data.get("calls") or [data]
    calls = []
    for c in data if isinstance(data, list) else []:
        if not isinstance(c, dict):
            continue
        fn = c.get("function") if isinstance(c.get("function"), dict) else {}
        name = str(c.get("name") or fn.get("name") or "")
        if not name or name not in names:
            continue
        args = c.get("arguments", c.get("args", c.get("parameters", fn.get("arguments"))))
        calls.append({"name": name, "arguments": _args(args)})
    if not calls:
        return text, []
    return before.strip(), calls


def openai_reply(data: dict, names) -> dict:
    """The gateway's chat answer as an OpenAI chat completion, with `tool_calls` when Muse asked for tools."""
    choice = ((data or {}).get("choices") or [{}])[0] or {}
    msg = choice.get("message") or {}
    text = _text(msg.get("content"))
    before, calls = parse_tool_calls(text, names) if names else (text, [])
    out = {"role": "assistant", "content": before if calls else text}
    if calls:
        out["content"] = before or None
        out["tool_calls"] = [{"id": "call_" + uuid.uuid4().hex[:16], "type": "function",
                              "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                             for c in calls]
    return {"id": (data or {}).get("id") or "chatcmpl-muse", "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "message": out,
                         "finish_reason": "tool_calls" if calls else (choice.get("finish_reason") or "stop")}],
            "usage": (data or {}).get("usage") or {}}


class ToolTextTransport(httpx.AsyncBaseTransport):
    """httpx transport for `engine._cc_tool_loop`: the loop posts an OpenAI request with tools, this sends the
    gateway a request without them (see the module docstring) and hands the loop an OpenAI answer back."""

    def __init__(self, timeout: float = TURN_TIMEOUT_S):
        self.timeout = float(timeout)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            body = json.loads((await request.aread()) or b"{}")
        except ValueError:
            body = {}
        tools = body.get("tools") or []
        payload = {"model": MODEL, "stream": False, "store": False, "timeout": int(self.timeout),
                   "messages": gateway_messages(body.get("messages") or [], tools, body.get("tool_choice"))}
        headers = {"Authorization": request.headers.get("Authorization", ""), "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout + 30, connect=15)) as client:
            r = await client.post(str(request.url), headers=headers, json=payload)
        if r.status_code != 200:
            return httpx.Response(r.status_code, content=r.content,
                                  headers={"content-type": r.headers.get("content-type", "application/json")},
                                  request=request)
        try:
            data = r.json()
        except ValueError:
            return httpx.Response(502, json={"error": {"message": _say("Muse Gateway trả về thứ không phải JSON.",
                                                                       "Muse Gateway did not answer in JSON.")}},
                                  request=request)
        return httpx.Response(200, json=openai_reply(data, tool_names(tools)), request=request)
