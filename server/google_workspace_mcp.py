"""Google's own Workspace MCP servers behind ONE connection (transport "internal", catalog `google-workspace-official`).

Why this exists (2026-11-27). Google made its Workspace MCP servers and its Workspace CLI (`gwscli`) generally available
on 2026-11-24. The CLI is a terminal client for these same servers: every `gwscli <service> <action>` is a `tools/call`
on `https://<service>mcp.googleapis.com/mcp/v1`. Javis is an MCP hub, so it talks to the servers directly instead of
running the CLI in a shell: the hub's permission levels, audit and rate limit stay in front of every call, every brain
gets the tools, and sign-in goes through Javis's own OAuth page, which works on a VPS behind a domain. `gwscli auth
login` needs a browser on the machine that runs it (a local listener on 127.0.0.1), the dead end the community
`workspace-mcp` card had.

Google runs one server per product, so this module fans out: one OAuth token (oauth_mcp, keyed by the connection id)
for nine servers, tool names prefixed with the service (`gmail_search_threads`, `drive_read_file_content`).

Wire protocol: the 2026-07-28 stateless MCP. No initialize handshake; every request carries the headers
`MCP-Protocol-Version`, `Mcp-Method` and, for tools/call, `Mcp-Name` (Google answers -32020 "Header mismatch" without
them), plus `params._meta` naming the client and declaring form elicitation.

Approvals (form elicitation). For a sensitive action (sending mail, sharing, trashing, inviting people outside the
domain) Google pauses the call and returns `resultType: "input_required"` with its own preview of the action and a
choice. The owner must answer: Google's guidance for agents is to prompt the user and relay the choice they made. The
pending call is kept here under a short id and the model is told to show the preview and ask; the owner's answer comes
back through the `confirm_google_action` tool, which repeats the exact call with Google's `requestState`. Only "allow
once" and "don't allow" are relayed: the sticky "always allow" choices belong to a person in Google's own interface.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import sys
import time

import httpx

PROTOCOL = "2026-07-28"
CLIENT_INFO = {"name": "Javis", "version": "1.0"}

# Service prefix, server URL, product name shown in approval prompts. The People API serves MCP on its own API host.
SERVICES = (
    ("gmail", "https://gmailmcp.googleapis.com/mcp/v1", "Gmail"),
    ("calendar", "https://calendarmcp.googleapis.com/mcp/v1", "Google Calendar"),
    ("drive", "https://drivemcp.googleapis.com/mcp/v1", "Google Drive"),
    ("docs", "https://docsmcp.googleapis.com/mcp/v1", "Google Docs"),
    ("sheets", "https://sheetsmcp.googleapis.com/mcp/v1", "Google Sheets"),
    ("slides", "https://slidesmcp.googleapis.com/mcp/v1", "Google Slides"),
    ("tasks", "https://tasksmcp.googleapis.com/mcp/v1", "Google Tasks"),
    ("chat", "https://chatmcp.googleapis.com/mcp/v1", "Google Chat"),
    ("people", "https://people.googleapis.com/mcp/v1", "Google Contacts"),
)
_BY_PREFIX = {s[0]: s for s in SERVICES}

CONFIRM_TOOL = "confirm_google_action"
CHOICES = ("ALLOW_ONCE", "DENY_ONCE")
PENDING_TTL = 15 * 60          # an approval Google asked for is kept this long
PENDING_MAX = 50               # per process; the oldest goes first
MAX_ROUNDS = 3                 # Google may ask again after an answer; past this the call stops
TOOLS_TTL = 600                # tools/list is "cacheScope: public" and the same for everyone
_TIMEOUT = httpx.Timeout(120, connect=15)

_tools_cache: dict = {}        # url -> (time, tools)
_pending: dict = {}            # approval id -> pending call


def _meta() -> dict:
    return {"io.modelcontextprotocol/protocolVersion": PROTOCOL,
            "io.modelcontextprotocol/clientInfo": dict(CLIENT_INFO),
            "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}}}}


def _language() -> str:
    """Accept-Language for Google's approval text: the owner's interface language, English after it."""
    try:
        import localefmt
        lang = (localefmt.ngon_ngu_giao_dien() or "").strip()
    except Exception:
        lang = ""
    return f"{lang}, en;q=0.8" if lang and lang != "en" else "en"


def _headers(method: str, name: str = "", auth: dict | None = None) -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "MCP-Protocol-Version": PROTOCOL, "Mcp-Method": method, "Accept-Language": _language()}
    if name:
        h["Mcp-Name"] = name
    h.update(auth or {})
    return h


def _parse(r: httpx.Response, rpc_id: int) -> dict:
    """One JSON-RPC answer, from a JSON body or from the data: lines of a text/event-stream body."""
    ct = (r.headers.get("content-type") or "").lower()
    if "text/event-stream" in ct:
        for line in (r.text or "").splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            try:
                obj = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("id") == rpc_id:
                return obj
        return {}
    try:
        obj = r.json()
    except Exception:
        return {"error": {"code": r.status_code, "message": (r.text or "").strip()[:300]}}
    return obj if isinstance(obj, dict) else {}


async def _post(client: httpx.AsyncClient, url: str, method: str, params: dict, name: str = "",
                auth: dict | None = None) -> tuple[int, dict]:
    rpc_id = secrets.randbelow(1 << 30) + 1
    r = await client.post(url, headers=_headers(method, name, auth),
                          json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params})
    return r.status_code, _parse(r, rpc_id)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_TIMEOUT)


def _error_text(obj: dict, status: int = 0) -> str:
    err = (obj or {}).get("error")
    if isinstance(err, dict):
        return str(err.get("message") or json.dumps(err, ensure_ascii=False))[:400]
    res = (obj or {}).get("result") or {}
    texts = [c.get("text", "") for c in (res.get("content") or []) if isinstance(c, dict)]
    return (" ".join(t for t in texts if t) or (f"HTTP {status}" if status else "unknown error"))[:400]


# ----------------------------------------------------------------------------------------------------------- tools/list
async def _service_tools(client: httpx.AsyncClient, url: str) -> list:
    hit = _tools_cache.get(url)
    if hit and time.time() - hit[0] < TOOLS_TTL:
        return hit[1]
    tools, cursor = [], None
    for _ in range(20):
        params = {"_meta": _meta()}
        if cursor:
            params["cursor"] = cursor
        status, obj = await _post(client, url, "tools/list", params)
        if status >= 400 or obj.get("error"):
            raise RuntimeError(f"{url}: {_error_text(obj, status)}")
        res = obj.get("result") or {}
        tools.extend(t for t in (res.get("tools") or []) if isinstance(t, dict) and t.get("name"))
        cursor = res.get("nextCursor")
        if not cursor:
            break
    _tools_cache[url] = (time.time(), tools)
    return tools


def _confirm_tool() -> dict:
    return {
        "name": CONFIRM_TOOL,
        "description": (
            "Relay the OWNER's answer to an approval Google asked for (a Google Workspace call that returned "
            "APPROVAL NEEDED). Call it only after the owner answered in this conversation: ALLOW_ONCE when they "
            "agreed, DENY_ONCE when they refused. Never decide for the owner, and never call it in background work "
            "with nobody to ask."),
        "inputSchema": {"type": "object", "properties": {
            "approval_id": {"type": "string", "description": "The id given in the APPROVAL NEEDED result."},
            "choice": {"type": "string", "enum": list(CHOICES),
                       "description": "ALLOW_ONCE = the owner agreed; DENY_ONCE = the owner refused."}},
            "required": ["approval_id", "choice"]},
        "annotations": {"title": "Relay the owner's answer to Google", "readOnlyHint": False},
    }


async def list_tools(spec):
    """Every tool of the nine servers, prefixed with its service, plus the approval relay.

    A server that does not answer is left out of this list (the others still work); all of them failing is an error,
    so the hub shows the connection as down instead of "working, 0 tools"."""
    async with _client() as client:
        got = await asyncio.gather(*(_service_tools(client, url) for _, url, _ in SERVICES), return_exceptions=True)
    out, errors = [], []
    for (prefix, _url, product), tools in zip(SERVICES, got):
        if isinstance(tools, BaseException):
            errors.append(f"{product}: {tools}")
            continue
        for t in tools:
            item = {k: v for k, v in t.items() if k != "outputSchema"}
            item["name"] = f"{prefix}_{t['name']}"
            item["description"] = f"[{product}] " + str(t.get("description") or t["name"])
            out.append(item)
    if errors:
        print("[google-workspace] tools/list: " + "; ".join(errors), file=sys.stderr)
    if not out:
        raise RuntimeError("Google Workspace MCP servers did not answer: " + "; ".join(errors)[:500])
    out.append(_confirm_tool())
    return out


# ----------------------------------------------------------------------------------------------------------- tools/call
def split_name(name: str):
    """`gmail_search_threads` -> the service entry and `search_threads`; (None, "") for any other name."""
    prefix, _, tool = str(name or "").partition("_")
    svc = _BY_PREFIX.get(prefix)
    return (svc, tool) if svc and tool else (None, "")


async def _auth(spec, force: bool = False, rejected: str = "") -> dict:
    conn_id = (spec or {}).get("oauth_conn_id") or ""
    if not conn_id:
        return {}
    try:
        import oauth_mcp   # late import: oauth_mcp imports mcp_store, which imports half the server
        return await oauth_mcp.auth_headers(conn_id, force=force, rejected=rejected) or {}
    except Exception as e:  # noqa: BLE001 - no token reads as "sign in again" below
        print(f"[google-workspace] token: {type(e).__name__}: {e}", file=sys.stderr)
        return {}


def _format(obj: dict) -> str:
    try:
        import mcp_client   # same reading of content blocks (text, images) as every other connection
        return mcp_client._format_result(obj)
    except Exception:
        return json.dumps(obj, ensure_ascii=False)[:4000]


def _prune(now: float) -> None:
    for k in [k for k, v in _pending.items() if now - v["created"] > PENDING_TTL]:
        _pending.pop(k, None)
    while len(_pending) >= PENDING_MAX:
        _pending.pop(min(_pending, key=lambda k: _pending[k]["created"]), None)


def _confirm_name(spec) -> str:
    ns = str((spec or {}).get("namespace") or "").strip()
    return f"{ns}__{CONFIRM_TOOL}" if ns else CONFIRM_TOOL


def _approval_text(pid: str, product: str, tool: str, req: dict, confirm: str = CONFIRM_TOOL) -> str:
    form = ((req or {}).get("params") or {})
    schema = form.get("requestedSchema") or {}
    props = schema.get("properties") or {}
    field = next(iter(props.values()), {}) if props else {}
    question = str(field.get("title") or "Allow this action?")
    preview = str(form.get("message") or "").strip()
    return ("APPROVAL NEEDED: Google asks the owner to approve this action before it runs. Nothing has been done yet.\n"
            f"Service: {product}, tool: {tool}\n"
            + (f"Google's preview:\n{preview}\n" if preview else "")
            + f"Google's question: {question}\n"
            f"Next step: show the owner this preview and ask whether to allow it once (a JAVIS_ASK block with the two "
            f"choices helps). Only after the owner answers, call {confirm} with approval_id=\"{pid}\" and "
            f"choice ALLOW_ONCE (agreed) or DENY_ONCE (refused). Never answer for the owner. In background work with "
            f"no owner to ask, do not call it: report that this action waits for the owner's approval. "
            f"The approval expires in {PENDING_TTL // 60} minutes.")


def _input_request(result: dict):
    """(key, request) of the first form Google asks to fill, or (None, None)."""
    for key, req in ((result or {}).get("inputRequests") or {}).items():
        if isinstance(req, dict):
            return key, req
    return None, None


async def _run(spec, svc, tool: str, arguments: dict, extra: dict | None = None, rounds: int = 0) -> str:
    prefix, url, product = svc
    params = {"name": tool, "arguments": arguments, **(extra or {}), "_meta": _meta()}
    auth = await _auth(spec)
    if not auth:
        return ("ERROR: Google Workspace is not signed in. Ask the owner to press Connect (or Reconnect) on this "
                "connection in Javis's Connections page.")
    async with _client() as client:
        status, obj = await _post(client, url, "tools/call", params, tool, auth)
        if status == 401:
            # The token expired between our check and Google's, or was revoked: refresh once and repeat.
            auth = await _auth(spec, force=True, rejected=auth.get("Authorization", ""))
            if auth:
                status, obj = await _post(client, url, "tools/call", params, tool, auth)
    if status == 401:
        return ("ERROR: Google refused the sign-in (" + _error_text(obj, status) + "). If it says invalid_token, the "
                "OAuth client may lack 'Use this client for an AI-powered agent' in Google Cloud, or the sign-in was "
                "revoked: ask the owner to check the client, then press Reconnect.")
    if obj.get("error"):
        return "ERROR: " + _error_text(obj, status)
    result = obj.get("result") or {}
    if result.get("resultType") == "input_required":
        key, req = _input_request(result)
        if not key or rounds >= MAX_ROUNDS:
            return "ERROR: Google asked for input this connection cannot give, so the action was not done."
        now = time.time()
        _prune(now)
        pid = secrets.token_hex(4)
        props = ((((req.get("params") or {}).get("requestedSchema") or {}).get("properties")) or {})
        field_name = next(iter(props), key)
        offered = list((props.get(field_name) or {}).get("enum") or [])
        _pending[pid] = {"created": now, "conn": spec.get("oauth_conn_id") or "", "svc": prefix, "tool": tool,
                         "arguments": arguments, "state": result.get("requestState"), "key": key,
                         "field": field_name, "offered": offered, "rounds": rounds + 1}
        return _approval_text(pid, product, tool, req, _confirm_name(spec))
    return _format({"result": result})


async def _confirm(spec, args: dict) -> str:
    pid = str((args or {}).get("approval_id") or "").strip()
    choice = str((args or {}).get("choice") or "").strip().upper()
    if choice not in CHOICES:
        return "ERROR: choice must be ALLOW_ONCE (the owner agreed) or DENY_ONCE (the owner refused)."
    _prune(time.time())
    item = _pending.get(pid)
    if not item or item["conn"] != ((spec or {}).get("oauth_conn_id") or ""):
        return ("ERROR: no approval with that id is waiting (it expired after "
                f"{PENDING_TTL // 60} minutes or was already answered). Make the original call again.")
    if item["offered"] and choice not in item["offered"]:
        return "ERROR: Google did not offer that choice here. Offered: " + ", ".join(item["offered"])
    _pending.pop(pid, None)
    extra = {"requestState": item["state"],
             "inputResponses": {item["key"]: {"action": "accept", "content": {item["field"]: choice}}}}
    return await _run(spec, _BY_PREFIX[item["svc"]], item["tool"], item["arguments"], extra, item["rounds"])


async def call(name, arguments, spec):
    args = dict(arguments or {})
    if name != CONFIRM_TOOL and not split_name(name)[0]:
        return f"ERROR: unknown Google Workspace tool '{name}'."
    try:
        if name == CONFIRM_TOOL:
            return await _confirm(spec, args)
        svc, tool = split_name(name)
        return await _run(spec, svc, tool, args)
    except httpx.HTTPError as e:
        return f"ERROR: Google did not answer ({type(e).__name__}). Try again in a moment."
