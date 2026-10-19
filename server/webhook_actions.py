"""webhook_actions.py - what a hook DOES with an accepted event (0.229.0, webhook platform M3).

A hook may list `actions`, run as independent BRANCHES of one event:

    [{"id": "crm",   "kind": "http", "url": "https://crm.example.com/hooks/order", "body": "fields",
      "headers": {"X-Api-Key": "..."}, "retry": "never"},
     {"id": "sheet", "kind": "apps_script", "url": "https://script.google.com/macros/s/<id>/exec"},
     {"id": "ship",  "kind": "plugin", "plugin": "giao-hang", "handler": "new_order"},
     {"id": "ai",    "kind": "ai"}]                    # the hook's task/workflow, the only kind that calls a model

     {"id": "crm2",  "kind": "tool", "tool": "pos_create_order", "args": {"phone": "{phone}", "ref": "{_delivery_id}"},
      "approve": true}                                 # M4: a tool through the hub dispatcher, after the owner approves

Without `actions` a hook has one branch, `{"id": "main", "kind": "ai"}`: the behaviour before M3.
M4: header values are kept as `{"$secret": name}` references (webhook_secrets.py); `approve: true` (the default for
`tool`) makes the branch wait for the owner's approval of that event before it runs.

Each branch gets a DELIVERY ID that never changes for that (event, action): `dlv_<hash>`. It is sent as the
`Idempotency-Key` and `X-Javis-Delivery` headers and inside the body, so a receiver that keeps it can drop a second
copy. Javis promises no exactly-once delivery: it records what it knows and never re-sends blindly.

Outcome of one branch (`run_*` return `Outcome`):
    completed  the receiver confirmed it did the work (2xx; Apps Script receipt ok; plugin "completed")
    accepted   the receiver took it and finishes later on its own (202; plugin "accepted": the plugin keeps its
               own scheduling and waiting); Javis does not chase it
    retry      certainly NOT done: the request never left (connect/DNS error) or the receiver said so (429, 503).
               Sent again with the SAME delivery ID after a backoff, at most MAX_BRANCH_TRIES times
    unknown    it may have been done (timeout after sending, a 5xx, a dropped connection, a plugin that hung): only
               the owner decides, unless the action says `"retry": "safe"` (the receiver dedups on the delivery ID)
    failed     certainly refused (4xx, bad receipt, blocked address, permission): retried only by the owner

Safety:
  - the incoming request's headers (cookies, tokens) are never forwarded: only the action's own headers;
  - addresses resolving to loopback, private, link-local, multicast or reserved ranges are refused unless the action
    says `"allow_private": true`; redirects are not followed (Apps Script: one GET to Google's own echo host);
  - an action's level: http, apps_script and plugin handlers with `min_mode: full` need the hook at `full`; a
    plugin handler's `min_mode` is checked against the hook's CURRENT level at run time;
  - nothing here calls a model. `JAVIS_WH_NO_NETWORK=1` makes the default HTTP transport refuse every request (tests).
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import ipaddress
import json
import os
import re
import socket
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

ACTIONS_MAX = 8
KINDS = ("http", "apps_script", "plugin", "tool", "ai")
TOOL_TIMEOUT_S = 120.0
ARGS_MAX = 30
OUTSIDE = ("http", "apps_script")          # kinds that act outside: need the hook at `full`
MAX_BRANCH_TRIES = 3
BRANCH_BACKOFF_S = (10.0, 60.0, 300.0)
TIMEOUT_DEFAULT_S = 15.0
TIMEOUT_MAX_S = 60.0
PLUGIN_TIMEOUT_S = 60.0
RESPONSE_KEEP = 600                        # characters of a receiver's answer kept as the receipt
HEADERS_MAX = 10
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_HEADER_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_FORBIDDEN_HEADERS = {"host", "content-length", "cookie", "transfer-encoding", "connection", "idempotency-key",
                      "x-javis-delivery"}
APPS_SCRIPT_HOSTS = ("script.google.com",)
APPS_SCRIPT_ECHO_HOSTS = ("script.googleusercontent.com",)
STATES = ("completed", "accepted", "retry", "unknown", "failed")


class ActionError(ValueError):
    """The action list itself is wrong (shown to the owner when saving)."""


@dataclass
class Outcome:
    status: str                      # one of STATES
    detail: str = ""                 # short, for the owner
    receipt: dict = field(default_factory=dict)
    retry_after: float = 0.0


def delivery_id(event_id: str, action_id: str) -> str:
    return "dlv_" + hashlib.sha256(f"{event_id}:{action_id}".encode()).hexdigest()[:24]


# ── validation ──
def validate(actions: Any) -> list:
    """Normalised list, or ActionError. None / [] = no actions (the hook's own task/workflow runs)."""
    if actions in (None, "", []):
        return []
    if isinstance(actions, str):
        try:
            actions = json.loads(actions)
        except ValueError as e:
            raise ActionError(f"actions are not valid JSON: {e}")
    if not isinstance(actions, list):
        raise ActionError("actions must be a list")
    if len(actions) > ACTIONS_MAX:
        raise ActionError(f"at most {ACTIONS_MAX} actions")
    out, seen = [], set()
    for a in actions:
        if not isinstance(a, dict):
            raise ActionError("each action must be an object")
        aid = str(a.get("id") or "").strip().lower()
        if not _ID_RE.match(aid):
            raise ActionError(f"action id {aid!r}: lowercase letters, digits, - and _ (max 32)")
        if aid in seen:
            raise ActionError(f"action id {aid} used twice")
        seen.add(aid)
        kind = str(a.get("kind") or "")
        if kind not in KINDS:
            raise ActionError(f"action {aid}: kind is one of {', '.join(KINDS)}")
        o: dict = {"id": aid, "kind": kind}
        if kind in OUTSIDE:
            url = str(a.get("url") or "").strip()
            u = urlsplit(url)
            if u.scheme != "https" and not (u.scheme == "http" and a.get("allow_private")):
                raise ActionError(f"action {aid}: the address must start with https://")
            if not u.hostname or u.username or u.password:
                raise ActionError(f"action {aid}: bad address")
            if kind == "apps_script" and (u.hostname not in APPS_SCRIPT_HOSTS
                                          or not re.match(r"^/macros/(?:u/\d+/)?s/[A-Za-z0-9_-]{10,}/exec$", u.path)):
                raise ActionError(f"action {aid}: an Apps Script web app address ends in /exec "
                                  "(https://script.google.com/macros/s/.../exec)")
            o["url"] = url
            body = a.get("body", "fields")
            if body not in ("fields", "raw", "event"):
                raise ActionError(f"action {aid}: body is fields, raw or event")
            o["body"] = body
            hdrs = a.get("headers") or {}
            if not isinstance(hdrs, dict) or len(hdrs) > HEADERS_MAX:
                raise ActionError(f"action {aid}: headers must be an object of at most {HEADERS_MAX}")
            clean = {}
            for k, v in hdrs.items():
                if not _HEADER_RE.match(str(k)) or str(k).lower() in _FORBIDDEN_HEADERS:
                    raise ActionError(f"action {aid}: header {k!r} is not allowed")
                if isinstance(v, dict) and set(v) == {"$secret"} and isinstance(v["$secret"], str):
                    clean[str(k)] = {"$secret": v["$secret"]}       # already sealed (webhook_secrets)
                    continue
                if not isinstance(v, str) or len(v) > 2000 or "\n" in v or "\r" in v:
                    raise ActionError(f"action {aid}: header {k} must be one line of text")
                clean[str(k)] = v
            o["headers"] = clean
            try:
                t = float(a.get("timeout_s") or TIMEOUT_DEFAULT_S)
            except (TypeError, ValueError):
                raise ActionError(f"action {aid}: timeout_s must be a number")
            o["timeout_s"] = max(1.0, min(t, TIMEOUT_MAX_S))
            r = str(a.get("retry") or "never")
            if r not in ("never", "safe"):
                raise ActionError(f"action {aid}: retry is never or safe")
            o["retry"] = r
            o["allow_private"] = bool(a.get("allow_private", False))
        elif kind == "plugin":
            slug, name = str(a.get("plugin") or ""), str(a.get("handler") or "")
            if not re.match(r"^[a-z0-9][a-z0-9._-]{0,63}$", slug) or not re.match(r"^[a-z][a-z0-9_]{0,63}$", name):
                raise ActionError(f"action {aid}: needs `plugin` (slug) and `handler` (name)")
            o.update(plugin=slug, handler=name)
        elif kind == "tool":
            tool = str(a.get("tool") or "")
            if not re.match(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$", tool):
                raise ActionError(f"action {aid}: needs `tool` (the tool's name as the hub lists it)")
            args = a.get("args") or {}
            if not isinstance(args, dict) or len(args) > ARGS_MAX:
                raise ActionError(f"action {aid}: args must be an object of at most {ARGS_MAX}")
            for k, v in args.items():
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", str(k)):
                    raise ActionError(f"action {aid}: argument name {k!r}")
                if isinstance(v, (dict, list)) or (isinstance(v, str) and len(v) > 2000):
                    raise ActionError(f"action {aid}: argument {k} must be plain (text may use {{field}})")
            o.update(tool=tool, args=dict(args))
        if "approve" in a or kind == "tool":
            o["approve"] = bool(a.get("approve", kind == "tool"))
        out.append(o)
    if sum(1 for o in out if o["kind"] == "ai") > 1:
        raise ActionError("at most one ai action (the hook's own task or workflow)")
    return out


def effective(actions: Optional[list]) -> list:
    return list(actions) if actions else [{"id": "main", "kind": "ai"}]


def view(actions: Optional[list]) -> list:
    """For the dashboard: header VALUES are never shown (they are often API keys)."""
    out = []
    for a in actions or []:
        b = dict(a)
        if b.get("headers"):
            b["headers"] = {k: "••••" for k in b["headers"]}
        out.append(b)
    return out


def sealed_names(actions: Optional[list]) -> list:
    """Secret names referenced by the headers of these actions."""
    return [v["$secret"] for a in actions or [] for v in (a.get("headers") or {}).values()
            if isinstance(v, dict) and "$secret" in v]


def merge_secrets(new: list, old: list) -> list:
    """A list sent back from the dashboard carries masked header values: keep the stored value for those."""
    olds = {a["id"]: a for a in old or []}
    for a in new:
        o = olds.get(a["id"])
        for k, v in list((a.get("headers") or {}).items()):
            if v == "••••":
                if o and k in (o.get("headers") or {}):
                    a["headers"][k] = o["headers"][k]
                else:
                    del a["headers"][k]
    return new


def level_ok(action: dict, level: str, plugin_min: str = "readonly") -> str:
    """'' when the hook's level allows this action, else the reason."""
    rank = {"suggest": 0, "auto": 1, "full": 2}
    need = {"readonly": 0, "safe": 1, "full": 2}
    lv = rank.get(level, 0)
    if action["kind"] in OUTSIDE and lv < 2:
        return "needs the webhook at level full (it sends data outside)"
    if action["kind"] == "tool":
        return ""      # the hub dispatcher checks every tool against this level (and the connection's own limit)
    if action["kind"] == "plugin" and lv < need.get(plugin_min, 2):
        return f"needs the webhook at a higher level (plugin handler min_mode {plugin_min})"
    return ""


# ── addresses ──
def _blocked_ip(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved
            or a.is_unspecified or (isinstance(a, ipaddress.IPv4Address) and a in ipaddress.ip_network("100.64.0.0/10")))


def _default_resolve(host: str) -> list:
    return [i[4][0] for i in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)]


async def check_address(url: str, allow_private: bool, resolve: Optional[Callable] = None) -> str:
    """'' if the address may be called, else why not. Every resolved address must be public (unless allowed)."""
    host = urlsplit(url).hostname or ""
    if allow_private:
        return ""
    try:
        ips = await asyncio.to_thread(resolve or _default_resolve, host)
    except Exception as e:
        return f"name did not resolve: {type(e).__name__}"
    if not ips:
        return "name did not resolve"
    for ip in ips:
        try:
            if _blocked_ip(ip):
                return "address is private or local (set allow_private to call it)"
        except ValueError:
            return "bad address"
    return ""


# ── bodies ──
def _meta(ctx: dict) -> dict:
    return {"delivery_id": ctx["delivery_id"], "event_id": ctx["event_id"], "hook_id": ctx["hook_id"],
            "action_id": ctx["action_id"], "received_at": ctx["received_at"]}


def build_body(action: dict, ctx: dict) -> tuple:
    """(bytes, content_type) of what is sent. `fields`: the mapped fields plus `_javis`; `event`: fields, the parsed
    payload and `_javis`; `raw`: the original body unchanged."""
    if action.get("body") == "raw":
        return bytes(ctx.get("body") or b""), str(ctx.get("content_type") or "application/octet-stream")
    doc = dict(ctx.get("fields") or {})
    if action.get("body") == "event":
        doc = {"fields": ctx.get("fields") or {}, "payload": ctx.get("payload")}
    doc["_javis"] = _meta(ctx)
    return json.dumps(doc, ensure_ascii=False, default=str).encode("utf-8"), "application/json"


def _headers(action: dict, ctx: dict, content_type: str) -> dict:
    h = {k: v for k, v in (action.get("headers") or {}).items() if isinstance(v, str)}
    h["Content-Type"] = content_type
    h["Idempotency-Key"] = ctx["delivery_id"]
    h["X-Javis-Delivery"] = ctx["delivery_id"]
    h["User-Agent"] = "Javis-Webhook/1"
    return h


def _short(text: str) -> str:
    t = str(text or "")
    return t if len(t) <= RESPONSE_KEEP else t[:RESPONSE_KEEP] + "…"


def _retry_after(resp) -> float:
    try:
        return max(0.0, min(float(resp.headers.get("retry-after") or 0), 3600.0))
    except ValueError:
        return 0.0


def _ambiguous(action: dict, detail: str) -> Outcome:
    """It may have been done. Re-sent only when the owner said the receiver dedups on the delivery ID."""
    return Outcome("retry" if action.get("retry") == "safe" else "unknown", detail)


# ── runners ──
class NoNetwork(Exception):
    pass


def default_transport():
    import httpx
    if os.environ.get("JAVIS_WH_NO_NETWORK") == "1":
        def refuse(request):
            raise NoNetwork(f"network disabled (JAVIS_WH_NO_NETWORK): {request.url.host}")
        return httpx.MockTransport(refuse)
    return httpx.AsyncHTTPTransport(retries=0)


async def run_http(action: dict, ctx: dict, transport=None, resolve=None) -> Outcome:
    import httpx
    why = await check_address(action["url"], action.get("allow_private", False), resolve)
    if why:
        return Outcome("failed", why)
    body, ct = build_body(action, ctx)
    try:
        async with httpx.AsyncClient(transport=transport or default_transport(), follow_redirects=False,
                                     timeout=action.get("timeout_s", TIMEOUT_DEFAULT_S)) as cl:
            resp = await cl.request(action.get("method", "POST"), action["url"], content=body,
                                    headers=_headers(action, ctx, ct))
    except (httpx.ConnectError, httpx.ConnectTimeout, NoNetwork) as e:
        return Outcome("retry", f"not sent: {type(e).__name__}")       # the request never reached the receiver
    except httpx.TimeoutException as e:
        return _ambiguous(action, f"no answer in time ({type(e).__name__}): it may have been done")
    except httpx.HTTPError as e:
        return _ambiguous(action, f"connection dropped ({type(e).__name__}): it may have been done")
    rc = {"status": resp.status_code, "body": _short(resp.text)}
    if resp.status_code == 202:
        return Outcome("accepted", "accepted by the receiver", rc)
    if 200 <= resp.status_code < 300:
        return Outcome("completed", f"HTTP {resp.status_code}", rc)
    if resp.status_code in (429, 503):
        return Outcome("retry", f"HTTP {resp.status_code}: receiver busy", rc, _retry_after(resp))
    if 300 <= resp.status_code < 400:
        return Outcome("failed", f"HTTP {resp.status_code}: redirects are not followed", rc)
    if resp.status_code >= 500:
        return _ambiguous(action, f"HTTP {resp.status_code}: the receiver failed, it may have been done")
    return Outcome("failed", f"HTTP {resp.status_code}", rc)


def _receipt(text: str, did: str) -> Outcome:
    """An Apps Script web app answers with ContentService JSON. `{"ok": true}` (echoing `delivery_id` when it keeps
    one) is a receipt; `{"ok": false, "error": ...}` is a refusal; anything else (often Google's sign-in page, when
    the deployment is not open to "Anyone") is not a receipt."""
    try:
        doc = json.loads(text)
    except ValueError:
        low = text.lower()
        hint = " (the web app must be deployed with access: Anyone)" if "accounts.google.com" in low or "<html" in low else ""
        return Outcome("failed", "Apps Script answered without a JSON receipt" + hint, {"body": _short(text)})
    if not isinstance(doc, dict):
        return Outcome("failed", "Apps Script receipt is not an object", {"body": _short(text)})
    rc = {"receipt": doc if len(json.dumps(doc, default=str)) <= RESPONSE_KEEP else {"ok": doc.get("ok")}}
    if doc.get("delivery_id") not in (None, "", did):
        return Outcome("failed", "Apps Script receipt names another delivery", rc)
    if doc.get("ok") is True:
        if doc.get("duplicate"):
            return Outcome("completed", "Apps Script had it already (same delivery)", rc)
        return Outcome("completed", "Apps Script receipt ok", rc)
    if doc.get("accepted") is True:
        return Outcome("accepted", "Apps Script accepted it for later", rc)
    return Outcome("failed", "Apps Script refused: " + str(doc.get("error") or "no reason")[:200], rc)


async def run_apps_script(action: dict, ctx: dict, transport=None, resolve=None) -> Outcome:
    """POST to the /exec address. Google runs the script, then answers 302 to a one-time echo address on
    script.googleusercontent.com that holds the script's output: read it with a plain GET (no body, no headers of the
    action) and treat it as the receipt. A POST is never repeated on the redirect."""
    import httpx
    why = await check_address(action["url"], False, resolve)
    if why:
        return Outcome("failed", why)
    body, ct = build_body(action, ctx)
    try:
        async with httpx.AsyncClient(transport=transport or default_transport(), follow_redirects=False,
                                     timeout=action.get("timeout_s", 30.0)) as cl:
            resp = await cl.post(action["url"], content=body, headers=_headers(action, ctx, ct))
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location") or ""
                host = urlsplit(loc).hostname or ""
                if urlsplit(loc).scheme != "https" or host not in APPS_SCRIPT_ECHO_HOSTS:
                    return Outcome("unknown", "Apps Script redirected somewhere unexpected: the script may have run",
                                   {"location": _short(loc)})
                try:
                    echo = await cl.get(loc, headers={"User-Agent": "Javis-Webhook/1"})
                except httpx.HTTPError as e:
                    return Outcome("unknown", f"the script ran but its receipt could not be read ({type(e).__name__})")
                if echo.status_code != 200:
                    return Outcome("unknown", f"receipt page answered HTTP {echo.status_code}: the script may have run")
                return _receipt(echo.text, ctx["delivery_id"])
    except (httpx.ConnectError, httpx.ConnectTimeout, NoNetwork) as e:
        return Outcome("retry", f"not sent: {type(e).__name__}")
    except httpx.TimeoutException as e:
        return _ambiguous(action, f"no answer in time ({type(e).__name__}): the script may have run")
    except httpx.HTTPError as e:
        return _ambiguous(action, f"connection dropped ({type(e).__name__}): the script may have run")
    if resp.status_code == 200:
        return _receipt(resp.text, ctx["delivery_id"])
    if resp.status_code in (429, 503):
        return Outcome("retry", f"HTTP {resp.status_code}: Google is busy", {"status": resp.status_code},
                       _retry_after(resp))
    if resp.status_code >= 500:
        return _ambiguous(action, f"HTTP {resp.status_code}: the script may have run")
    return Outcome("failed", f"HTTP {resp.status_code} from Apps Script", {"status": resp.status_code,
                                                                           "body": _short(resp.text)})


async def run_plugin(action: dict, ctx: dict, found: Optional[dict], level: str) -> Outcome:
    """`found` = {"handler", "ctx", "min_mode"} of an ENABLED plugin visible to the hook's brain, or None.
    handler(delivery, plugin_ctx) -> {"status": "completed"|"accepted", "ref"?: str, "detail"?: str}."""
    if not found:
        return Outcome("failed", f"plugin handler {action['plugin']}/{action['handler']} is not installed or is off")
    why = level_ok(action, level, found.get("min_mode", "full"))
    if why:
        return Outcome("failed", why)
    delivery = {**_meta(ctx), "brain": ctx.get("brain", ""), "fields": ctx.get("fields") or {},
                "payload": ctx.get("payload"), "level": level}
    h = found["handler"]
    try:
        if inspect.iscoroutinefunction(h):
            res = await asyncio.wait_for(h(delivery, found.get("ctx")), PLUGIN_TIMEOUT_S)
        else:
            # A plain function runs in a thread so a slow plugin cannot stall the server's event loop.
            res = await asyncio.wait_for(asyncio.to_thread(h, delivery, found.get("ctx")), PLUGIN_TIMEOUT_S)
            if inspect.isawaitable(res):
                res = await asyncio.wait_for(res, PLUGIN_TIMEOUT_S)
    except asyncio.TimeoutError:
        return Outcome("unknown", f"plugin did not answer in {int(PLUGIN_TIMEOUT_S)} s: it may have acted")
    except Exception as e:
        return Outcome("failed", f"plugin error: {type(e).__name__}: {e}"[:300])
    if not isinstance(res, dict) or res.get("status") not in ("completed", "accepted"):
        return Outcome("failed", "plugin answered without status completed or accepted")
    rc = {"ref": str(res.get("ref") or "")[:200]}
    return Outcome(res["status"], str(res.get("detail") or f"plugin {res['status']}")[:300], rc)


def tool_args(action: dict, ctx: dict) -> dict:
    """The tool's arguments: text values may use `{field}` of the mapped fields and `{_delivery_id}`, `{_event_id}`,
    `{_hook_id}`. Substitution only (webhook_rules.render_template): nothing in the payload is evaluated."""
    import webhook_rules
    vals = dict(ctx.get("fields") or {})
    vals.update(_delivery_id=ctx["delivery_id"], _event_id=ctx["event_id"], _hook_id=ctx["hook_id"])
    out = {}
    for k, v in (action.get("args") or {}).items():
        out[k] = webhook_rules.render_template(v, vals) if isinstance(v, str) else v
    return out


async def run_tool(action: dict, ctx: dict, call_tool: Optional[Callable], level: str) -> Outcome:
    """A tool through the hub dispatcher, at the hook's CURRENT level: the hub applies the same permission rules as
    for any background run (a `danger` tool needs full, the connection's own limit applies too)."""
    if not call_tool:
        return Outcome("failed", "tools are not available to webhooks on this server")
    args = tool_args(action, ctx)
    try:
        res = await asyncio.wait_for(call_tool(ctx.get("brain", ""), level, action["tool"], args), TOOL_TIMEOUT_S)
    except asyncio.TimeoutError:
        return Outcome("unknown", f"tool did not answer in {int(TOOL_TIMEOUT_S)} s: it may have acted")
    except Exception as e:
        return Outcome("unknown", f"tool call broke ({type(e).__name__}): it may have acted")
    text = str(res or "")
    if text.startswith("ERROR:"):
        return Outcome("failed", text[6:].strip()[:300], {"result": _short(text)})
    return Outcome("completed", f"tool {action['tool']} ran", {"result": _short(text)})
