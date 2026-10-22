"""webhook_actions.py - what a hook DOES with an accepted event (0.274.0, webhook platform M3, spec §8).

A hook may list `actions`, run as independent DELIVERIES of one event:

    [{"id": "crm",   "kind": "http", "url": "https://crm.example.com/hooks/order", "body": "fields",
      "headers": {"X-Api-Key": "..."}, "retry_safety": "manual_on_ambiguous"},
     {"id": "sheet", "kind": "apps_script", "url": "https://script.google.com/macros/s/<id>/exec", "body": "raw",
      "delivery_ref": "query"},
     {"id": "ship",  "kind": "plugin", "plugin": "poscake-zalo", "handler": "order_received",
      "when": {"path": "status", "op": "eq", "value": 1}, "depends_on": ["sheet"]},
     {"id": "crm2",  "kind": "tool", "tool": "pos_create_order", "args": {"phone": "{{payload.bill_phone}}"},
      "approve": true},
     {"id": "ai",    "kind": "ai"}]                    # the hook's task/workflow, the only kind that calls a model

The spec's names are read too: `type` (`http_forward`, with `redirect_profile: google_apps_script` for Apps Script),
`body_mode`, `retry_safety`. Without `actions` a hook has one delivery, `{"id": "main", "kind": "ai"}`.

Each delivery has a DELIVERY ID that never changes for that (event, action, generation): `dlv_<hash>`. It is sent as
`Idempotency-Key` and `X-Javis-Delivery`, with `X-Javis-Event-Id`, and inside the body (or, for an Apps Script web app
that cannot read headers in doPost(e), in the query when the owner chose `delivery_ref: query`). Javis promises no
exactly-once delivery: it records what it knows and never re-sends blindly.

Outcome of one delivery (`run_*` return `Outcome`):
    completed  the receiver confirmed it did the work (2xx; Apps Script receipt ok; plugin "completed")
    accepted   the receiver took it and finishes later on its own (202; plugin "accepted" with its job id): the
               plugin keeps its own scheduling and waiting; Javis does not chase it
    retry      certainly NOT done: the request never left (connect/DNS error) or the receiver said so (429), or the
               owner declared the receiver idempotent (`retry_safety`) and the answer was ambiguous
    unknown    it may have been done (timeout after sending, a 5xx, a dropped connection, a plugin that hung)
    blocked    refused for the configuration, not the event (401/403, a missing credential, a plugin switched off):
               waits until the owner fixes it, never retried in a loop
    failed     certainly refused for this event (4xx, bad receipt, blocked address, wrong schema): `dead` in the spec

Safety:
  - the incoming request's headers (cookies, tokens) are never forwarded: only the action's own headers;
  - the address is checked after DNS AND the connection is made to that checked address (no DNS rebinding);
    loopback, private, link-local, CGNAT, multicast and reserved ranges are refused unless `allow_private`;
    redirects are not followed (Apps Script: one GET to Google's echo host, whose address is checked too);
  - an action's level: http, apps_script and plugin handlers with `min_mode: full` need the hook at `full`;
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
from typing import Any, Callable, Optional
from urllib.parse import urlencode, urlsplit, urlunsplit

ACTIONS_MAX = 10              # spec §8.5
KINDS = ("http", "apps_script", "plugin", "tool", "ai")
TOOL_TIMEOUT_S = 150.0       # above the MCP transport's own 120 s, so its timeout surfaces (as unknown) first
ARGS_MAX = 30
OUTSIDE = ("http", "apps_script")          # kinds that act outside: need the hook at `full`
MAX_BRANCH_TRIES = 4                       # spec §7: 4 calls in all, the first included
TIMEOUT_DEFAULT_S = 15.0
TIMEOUT_MAX_S = 60.0
PLUGIN_TIMEOUT_S = 60.0
RESPONSE_KEEP = 600
HEADERS_MAX = 10
RETRY_SAFETY = ("manual_on_ambiguous", "idempotent", "at_least_once")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_HEADER_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_FORBIDDEN_HEADERS = {"host", "content-length", "cookie", "transfer-encoding", "connection", "idempotency-key",
                      "x-javis-delivery", "x-javis-event-id"}
APPS_SCRIPT_HOSTS = ("script.google.com",)
APPS_SCRIPT_ECHO_HOSTS = ("script.googleusercontent.com",)
STATES = ("completed", "accepted", "retry", "unknown", "failed", "blocked", "waiting")
PLUGIN_RESULTS = {"completed": "completed", "accepted": "accepted", "retryable_error": "retry",
                  "permanent_error": "failed", "unknown": "unknown", "waiting_approval": "waiting"}


class ActionError(ValueError):
    """The action list itself is wrong (shown to the owner when saving)."""


class Outcome:
    """One delivery attempt's result. A plain class, not a dataclass: it is built at every start (keep it light)."""
    __slots__ = ("status", "detail", "receipt", "retry_after", "http_status", "maybe_acted")

    def __init__(self, status: str, detail: str = "", receipt: Optional[dict] = None, retry_after: float = 0.0,
                 http_status: int = 0, maybe_acted: Optional[bool] = None):
        self.status = status                 # one of STATES
        self.detail = detail                 # short, for the owner
        self.receipt = receipt if receipt is not None else {}
        self.retry_after = retry_after
        self.http_status = http_status
        self.maybe_acted = maybe_acted

    def __eq__(self, other):
        return isinstance(other, Outcome) and all(getattr(self, k) == getattr(other, k) for k in self.__slots__)

    def __repr__(self):
        return "Outcome(" + ", ".join(f"{k}={getattr(self, k)!r}" for k in self.__slots__) + ")"


def delivery_id(event_id: str, action_id: str, generation: int = 1) -> str:
    """Stable for one (event, action, generation): every retry of a delivery sends the same id. A replay with a new
    configuration is a new generation, so a new id (spec §7)."""
    base = f"{event_id}:{action_id}" + (f":g{int(generation)}" if int(generation or 1) > 1 else "")
    return "dlv_" + hashlib.sha256(base.encode()).hexdigest()[:24]


def retry_safe(action: dict) -> bool:
    """May an ambiguous outcome (timeout after sending, 5xx, lost lease) be sent again? Only when the owner said the
    receiver drops a second copy of the same delivery id (`idempotent`) or accepts duplicates (`at_least_once`)."""
    return action.get("retry_safety") in ("idempotent", "at_least_once") or action.get("retry") == "safe"


# ── validation ──
def _alias(a: dict) -> dict:
    """The spec's field names (§9) read into ours."""
    a = dict(a)
    t = a.pop("type", None)
    if t and "kind" not in a:
        if t == "http_forward":
            a["kind"] = "apps_script" if (a.get("redirect_profile") == "google_apps_script" or
                                          urlsplit(str(a.get("url") or "")).hostname in APPS_SCRIPT_HOSTS) else "http"
        elif t in KINDS:
            a["kind"] = t
        else:
            a["kind"] = t
    if "body_mode" in a and "body" not in a:
        a["body"] = a.pop("body_mode")
    rp = a.pop("redirect_profile", None)
    if rp not in (None, "", "none", "google_apps_script"):
        raise ActionError(f"action {a.get('id')}: redirect_profile is google_apps_script or none")
    return a


def validate(actions: Any) -> list:
    """Normalised list, or ActionError. None / [] = no actions (the hook's own task/workflow runs)."""
    import webhook_rules
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
        a = _alias(a)
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
        rs = a.get("retry_safety")
        if rs is not None and rs not in RETRY_SAFETY:
            raise ActionError(f"action {aid}: retry_safety is one of {', '.join(RETRY_SAFETY)}")
        if kind in OUTSIDE:
            url = str(a.get("url") or "").strip()
            u = urlsplit(url)
            if u.scheme != "https" and not (u.scheme == "http" and a.get("allow_private") is True):
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
                    clean[str(k)] = {"$secret": v["$secret"]}
                    continue
                if v == "••••":
                    clean[str(k)] = v
                    continue
                if not isinstance(v, str) or len(v) > 2000 or not all(32 <= ord(c) < 127 for c in v) or v != v.strip():
                    raise ActionError(f"action {aid}: header {k} must be one line of plain ASCII text")
                clean[str(k)] = v
            o["headers"] = clean
            try:
                t = float(a.get("timeout_s") or (30.0 if kind == "apps_script" else TIMEOUT_DEFAULT_S))
            except (TypeError, ValueError):
                raise ActionError(f"action {aid}: timeout_s must be a number")
            o["timeout_s"] = max(1.0, min(t, TIMEOUT_MAX_S))
            r = str(a.get("retry") or "never")
            if r not in ("never", "safe"):
                raise ActionError(f"action {aid}: retry is never or safe")
            o["retry_safety"] = rs or ("idempotent" if r == "safe" else "manual_on_ambiguous")
            o["retry"] = "safe" if o["retry_safety"] != "manual_on_ambiguous" else "never"
            o["allow_private"] = a.get("allow_private") is True
            ref = str(a.get("delivery_ref") or "header")
            if ref not in ("header", "query"):
                raise ActionError(f"action {aid}: delivery_ref is header or query")
            o["delivery_ref"] = ref
        elif kind == "plugin":
            slug, name = str(a.get("plugin") or ""), str(a.get("handler") or "")
            if not re.match(r"^[a-z0-9][a-z0-9._-]{0,63}$", slug) or not re.match(r"^[a-z][a-z0-9_]{0,63}$", name):
                raise ActionError(f"action {aid}: needs `plugin` (slug) and `handler` (name)")
            o.update(plugin=slug, handler=name, allow_ai=a.get("allow_ai") is True)
        elif kind == "tool":
            tool = str(a.get("tool") or "")
            if not re.match(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$", tool):
                raise ActionError(f"action {aid}: needs `tool` (the tool's name as the hub lists it)")
            if tool in ("javis_run_tool", "javis_search_tools"):
                raise ActionError(f"action {aid}: name the tool itself, not {tool}")
            args = a.get("args") or {}
            if not isinstance(args, dict) or len(args) > ARGS_MAX:
                raise ActionError(f"action {aid}: args must be an object of at most {ARGS_MAX}")
            for k, v in args.items():
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", str(k)):
                    raise ActionError(f"action {aid}: argument name {k!r}")
                if isinstance(v, (dict, list)) or (isinstance(v, str) and len(v) > 2000):
                    raise ActionError(f"action {aid}: argument {k} must be plain (a whole {{{{payload.x}}}} keeps "
                                      "its type)")
                try:
                    webhook_rules.validate_template(v, f"action {aid}: argument {k}")
                except webhook_rules.RuleError as e:
                    raise ActionError(str(e))
            o.update(tool=tool, args=dict(args), retry_safety=rs or "manual_on_ambiguous")
        if "approve" in a or kind == "tool":
            o["approve"] = bool(a.get("approve", kind == "tool"))
        if a.get("when") not in (None, {}, ""):
            try:
                o["when"] = webhook_rules.validate_condition(a["when"])
            except webhook_rules.RuleError as e:
                raise ActionError(f"action {aid}: when: {e}")
        deps = a.get("depends_on") or []
        if not isinstance(deps, list) or len(deps) > ACTIONS_MAX:
            raise ActionError(f"action {aid}: depends_on is a list of action ids")
        dd = []
        for d in deps:
            if isinstance(d, str):
                d = {"id": d}
            if not isinstance(d, dict) or not isinstance(d.get("id"), str):
                raise ActionError(f"action {aid}: depends_on items are action ids")
            on = str(d.get("on") or "succeeded")
            if on not in ("succeeded", "accepted"):
                raise ActionError(f"action {aid}: depends_on `on` is succeeded or accepted")
            dd.append({"id": d["id"].strip().lower(), "on": on})
        if dd:
            o["depends_on"] = dd
        out.append(o)
    if sum(1 for o in out if o["kind"] == "ai") > 1:
        raise ActionError("at most one ai action (the hook's own task or workflow)")
    ids = {o["id"] for o in out}
    for o in out:
        for d in o.get("depends_on") or []:
            if d["id"] not in ids or d["id"] == o["id"]:
                raise ActionError(f"action {o['id']}: depends_on names {d['id']!r}, which is not another action")
    _acyclic(out)
    return out


def _acyclic(actions: list) -> None:
    deps = {a["id"]: [d["id"] for d in a.get("depends_on") or []] for a in actions}
    state: dict = {}

    def visit(n, path):
        if state.get(n) == 1:
            raise ActionError("depends_on makes a loop: " + " -> ".join(path + [n]))
        if state.get(n) == 2:
            return
        state[n] = 1
        for m in deps.get(n, []):
            visit(m, path + [n])
        state[n] = 2
    for n in deps:
        visit(n, [])


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
    return [v["$secret"] for a in actions or [] for v in (a.get("headers") or {}).values()
            if isinstance(v, dict) and "$secret" in v]


def same_target(a: Optional[dict], b: Optional[dict]) -> bool:
    """Do two versions of an action send to the same place? A stored secret may only follow the same target."""
    if not a or not b:
        return False
    keys = ("kind", "url", "allow_private", "plugin", "handler", "tool")
    return all(a.get(k) == b.get(k) for k in keys)


def target_key(action: dict) -> str:
    """The breaker's key (spec §11: per target and credential, not per hook): the same receiver behind two hooks
    shares one breaker; another credential to the same URL is another target."""
    cred = sorted(v["$secret"] if isinstance(v, dict) else hashlib.sha256(str(v).encode()).hexdigest()[:8]
                  for v in (action.get("headers") or {}).values())
    t = {"kind": action.get("kind"), "url": action.get("url"), "plugin": action.get("plugin"),
         "handler": action.get("handler"), "tool": action.get("tool"), "cred": cred}
    return "t:" + hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest()[:20]


def merge_secrets(new: list, old: list) -> list:
    """A list sent back from the dashboard carries masked header values: keep the stored value for those, but ONLY
    when the action still sends to the same target."""
    olds = {a["id"]: a for a in old or []}
    for a in new:
        o = olds.get(a["id"])
        for k, v in list((a.get("headers") or {}).items()):
            if isinstance(v, dict) and (not o or (o.get("headers") or {}).get(k) != v):
                raise ActionError(f"action {a['id']}: header {k} cannot be a secret reference; enter its value")
            if v == "••••" or isinstance(v, dict):
                if o and k in (o.get("headers") or {}) and same_target(a, o):
                    a["headers"][k] = o["headers"][k]
                elif o and k in (o.get("headers") or {}):
                    raise ActionError(f"action {a['id']}: its address changed, so enter header {k} again")
                else:
                    raise ActionError(f"action {a['id']}: enter header {k} again")
    return new


def level_ok(action: dict, level: str, plugin_min: str = "readonly") -> str:
    """'' when the hook's level allows this action, else the reason."""
    rank = {"suggest": 0, "auto": 1, "full": 2}
    need = {"readonly": 0, "safe": 1, "full": 2}
    lv = rank.get(level, 0)
    if action["kind"] in OUTSIDE and lv < 2:
        return "needs the webhook at level full (it sends data outside)"
    if action["kind"] == "tool":
        return ""
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


_METADATA = (ipaddress.ip_network("169.254.0.0/16"), ipaddress.ip_network("fe80::/10"),
             ipaddress.ip_network("fd00:ec2::254/128"), ipaddress.ip_network("100.100.100.200/32"))


def _always_blocked(ip: str) -> bool:
    """Link-local and cloud metadata addresses: refused even with allow_private (a LAN receiver is a fair need, the
    machine's metadata service with its credentials never is)."""
    a = ipaddress.ip_address(ip)
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return any(a.version == n.version and a in n for n in _METADATA)


def _default_resolve(host: str) -> list:
    return [i[4][0] for i in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)]


async def check_address(url: str, allow_private: bool, resolve: Optional[Callable] = None) -> str:
    """'' if the address may be called, else why not. Every resolved address must be public (unless allowed)."""
    host = urlsplit(url).hostname or ""
    try:
        ips = await asyncio.to_thread(resolve or _default_resolve, host)
    except Exception as e:
        return f"name did not resolve: {type(e).__name__}"
    if not ips:
        return "name did not resolve"
    for ip in ips:
        try:
            if _always_blocked(ip):
                return "address is link-local or a cloud metadata service (never called)"
            if not allow_private and _blocked_ip(ip):
                return "address is private or local (set allow_private to call it)"
        except ValueError:
            return "bad address"
    return ""


class AddressRefused(Exception):
    pass


def _refused(why: str) -> "Outcome":
    """A name that did not resolve is a passing fault (DNS outage) and nothing was sent: retry. A private, local or
    malformed address stays refused for good."""
    if why.startswith("name did not resolve"):
        return Outcome("retry", f"not sent: {why}", maybe_acted=False)
    return Outcome("failed", why, maybe_acted=False)


def _pinned_backend(allow_private: bool, resolve: Optional[Callable]):
    """An httpcore network backend that resolves the name itself, refuses a private address, and connects to the
    address it checked (TLS still verifies the certificate for the name: httpcore passes the host as SNI). A name
    that answers a public address to the check and a private one to the connection (DNS rebinding) gets nowhere."""
    import httpcore
    from httpcore._backends.auto import AutoBackend

    class Pinned(httpcore.AsyncNetworkBackend):
        def __init__(self):
            self._inner = AutoBackend()

        async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
            try:
                ips = await asyncio.to_thread(resolve or _default_resolve, host)
            except Exception as e:
                raise httpcore.ConnectError(f"name did not resolve: {type(e).__name__}")
            for ip in ips:
                if not _always_blocked(ip) and (allow_private or not _blocked_ip(ip)):
                    return await self._inner.connect_tcp(ip, port, timeout=timeout, local_address=local_address,
                                                         socket_options=socket_options)
            raise AddressRefused("address is private or local")

        async def connect_unix_socket(self, path, timeout=None, socket_options=None):
            raise httpcore.ConnectError("unix sockets are not used")

        async def sleep(self, seconds):
            await self._inner.sleep(seconds)
    return Pinned()


# ── bodies ──
def _meta(ctx: dict) -> dict:
    m = {"delivery_id": ctx["delivery_id"], "event_id": ctx["event_id"], "hook_id": ctx["hook_id"],
         "action_id": ctx["action_id"], "received_at": ctx["received_at"]}
    if ctx.get("source") == "test":
        m["test"] = True                 # a dashboard test event: a receiver can tell it apart from a real one
    return m


def build_body(action: dict, ctx: dict) -> tuple:
    """(bytes, content_type) of what is sent. `fields`: the mapped fields plus `_javis`; `event`: fields, the parsed
    payload and `_javis`; `raw`: the original body unchanged (and its own content type)."""
    if action.get("body") == "raw":
        return bytes(ctx.get("body") or b""), str(ctx.get("content_type") or "application/octet-stream")
    doc = dict(ctx.get("fields") or {})
    if action.get("body") == "event":
        doc = {"fields": ctx.get("fields") or {}, "payload": ctx.get("payload")}
    doc["_javis"] = _meta(ctx)
    return json.dumps(doc, ensure_ascii=False, default=str).encode("utf-8"), "application/json"


def target_url(action: dict, ctx: dict) -> str:
    """The URL actually called: with `delivery_ref: query`, the delivery and event ids ride in the query (an Apps
    Script doPost(e) reads e.parameter, never request headers). Only when the owner chose it: it changes the URL the
    receiver sees, not the body's schema."""
    test = ctx.get("source") == "test"
    if action.get("delivery_ref") != "query":
        if not (test and action.get("kind") == "apps_script"):
            return action["url"]
        q = {"javis_test": "1"}          # doPost reads no header: a test event must say so in the query
    else:
        q = {"javis_delivery": ctx["delivery_id"], "javis_event": ctx["event_id"]}
        if test:
            q["javis_test"] = "1"
    u = urlsplit(action["url"])
    extra = urlencode(q)
    return urlunsplit((u.scheme, u.netloc, u.path, (u.query + "&" if u.query else "") + extra, u.fragment))


def _headers(action: dict, ctx: dict, content_type: str) -> dict:
    h = {k: v for k, v in (action.get("headers") or {}).items() if isinstance(v, str)}
    low = {k.lower() for k in h}
    if "content-type" not in low:
        h["Content-Type"] = content_type
    if "user-agent" not in low:
        h["User-Agent"] = "Javis-Webhook/1"
    h["Idempotency-Key"] = ctx["delivery_id"]
    h["X-Javis-Delivery"] = ctx["delivery_id"]
    h["X-Javis-Event-Id"] = ctx["event_id"]
    if ctx.get("source") == "test":
        h["X-Javis-Test"] = "1"          # a raw body cannot carry `_javis.test`: the receiver sees it here
    return h


def request_fingerprint(action: dict, ctx: dict) -> str:
    """Hash of what a delivery sends (URL and body), kept with each attempt (spec §4.1 `request hash`)."""
    if action["kind"] in OUTSIDE:
        body, _ = build_body(action, ctx)
        return hashlib.sha256(target_url(action, ctx).encode() + b"\n" + body).hexdigest()[:32]
    return ""


def _short(text: str) -> str:
    t = str(text or "")
    return t if len(t) <= RESPONSE_KEEP else t[:RESPONSE_KEEP] + "…"


def _retry_after(resp) -> float:
    v = str(resp.headers.get("retry-after") or "").strip()
    try:
        return max(0.0, min(float(v or 0), 86400.0))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        import time as _t
        return max(0.0, min(parsedate_to_datetime(v).timestamp() - _t.time(), 86400.0))
    except Exception:
        return 0.0


RESPONSE_READ_MAX = 64 * 1024


async def _send(cl, method: str, url: str, **kw):
    """One request whose answer is read only up to RESPONSE_READ_MAX bytes. Returns (status, headers, text)."""
    async with cl.stream(method, url, **kw) as resp:
        buf = b""
        async for chunk in resp.aiter_bytes():
            buf += chunk
            if len(buf) >= RESPONSE_READ_MAX:
                break
        return resp.status_code, resp.headers, buf[:RESPONSE_READ_MAX].decode("utf-8", "replace")


def _ambiguous(action: dict, detail: str, rc: Optional[dict] = None, code: int = 0) -> Outcome:
    """It may have been done. Sent again only when the owner declared the receiver idempotent or at-least-once."""
    return Outcome("retry" if retry_safe(action) else "unknown", detail, rc or {}, http_status=code, maybe_acted=True)


# ── runners ──
class NoNetwork(Exception):
    pass


PLUGIN_THREADS = 4
PLUGIN_PER_SLUG = 2               # one plugin holds at most this many threads: a hung one never takes them all (§11)
_PLUGIN_SLOTS = __import__("threading").BoundedSemaphore(PLUGIN_THREADS)
_SLUG_LOCK = __import__("threading").Lock()
_SLUG_INFLIGHT: dict = {}         # plugin slug -> sync calls still running (a timed-out thread included)
_POOL = {"ex": None}
_INFLIGHT: set = set()            # delivery ids whose plugin call is still running (a timed-out thread included)


def _plugin_pool():
    if _POOL["ex"] is None:
        from concurrent.futures import ThreadPoolExecutor
        _POOL["ex"] = ThreadPoolExecutor(max_workers=PLUGIN_THREADS, thread_name_prefix="wh-plugin")
    return _POOL["ex"]


def plugin_busy(did: str) -> bool:
    """Is a call of this delivery still running? A retry must not start beside it (spec §8.2: an old callback never
    acts alongside a new attempt)."""
    return did in _INFLIGHT


def plugin_slot_free(slug: str, found: Optional[dict]) -> bool:
    """May a call of this plugin start now? Checked BEFORE the delivery is dispatched, so a full pool costs it no
    attempt (and no breaker failure): it simply waits for its turn."""
    if not found or inspect.iscoroutinefunction(found.get("handler")):
        return True
    with _SLUG_LOCK:
        return _SLUG_INFLIGHT.get(slug, 0) < PLUGIN_PER_SLUG and sum(_SLUG_INFLIGHT.values()) < PLUGIN_THREADS


def plugin_reserve(slug: str, found: Optional[dict]) -> Optional[bool]:
    """Take one of this plugin's call slots right before its delivery is dispatched, so the slot check and the call
    are one step: two deliveries that both saw a free slot can no longer both be dispatched with one of them then
    refused (an attempt spent with nothing sent). None = nothing to reserve (an async handler, no plugin); True =
    reserved (run_plugin(..., reserved=True) uses it, plugin_unreserve gives it back if the call never starts);
    False = busy."""
    if not found or inspect.iscoroutinefunction(found.get("handler")):
        return None
    with _SLUG_LOCK:
        if _SLUG_INFLIGHT.get(slug, 0) >= PLUGIN_PER_SLUG or not _PLUGIN_SLOTS.acquire(blocking=False):
            return False
        _SLUG_INFLIGHT[slug] = _SLUG_INFLIGHT.get(slug, 0) + 1
    return True


def plugin_unreserve(slug: str) -> None:
    with _SLUG_LOCK:
        _SLUG_INFLIGHT[slug] = max(0, _SLUG_INFLIGHT.get(slug, 0) - 1)
    _PLUGIN_SLOTS.release()


def _call_release(h, delivery, ctx, did, slug=""):
    try:
        return h(delivery, ctx)
    finally:
        _INFLIGHT.discard(did)
        with _SLUG_LOCK:
            _SLUG_INFLIGHT[slug] = max(0, _SLUG_INFLIGHT.get(slug, 0) - 1)
        _PLUGIN_SLOTS.release()


def default_transport(allow_private: bool = False, resolve: Optional[Callable] = None):
    import httpx
    if os.environ.get("JAVIS_WH_NO_NETWORK") == "1":
        def refuse(request):
            raise NoNetwork(f"network disabled (JAVIS_WH_NO_NETWORK): {request.url.host}")
        return httpx.MockTransport(refuse)
    # Pinned connections (no DNS rebinding), always: an explicit transport makes httpx ignore the *_PROXY variables,
    # so a proxy setting never routed these calls anyway and must not switch the pinning off.
    import httpcore
    t = httpx.AsyncHTTPTransport(retries=0)
    t._pool = httpcore.AsyncConnectionPool(ssl_context=t._pool._ssl_context, retries=0,
                                           network_backend=_pinned_backend(allow_private, resolve))
    return t


def _outcome_of(code: int, text: str, rh, action: dict) -> Outcome:
    rc = {"status": code, "body": _short(text)}

    class _R:
        headers = rh
    if code == 202:
        return Outcome("accepted", "accepted by the receiver", rc, http_status=code)
    if 200 <= code < 300:
        return Outcome("completed", f"HTTP {code}", rc, http_status=code)
    if code == 429:
        # Refused before processing (rate limited): retried after its Retry-After.
        return Outcome("retry", f"HTTP {code}: receiver busy", rc, _retry_after(_R), http_status=code, maybe_acted=False)
    if code in (401, 403):
        return Outcome("blocked", f"HTTP {code}: the receiver refused the credential; fix the action's key, then it "
                       "runs again", rc, http_status=code, maybe_acted=False)
    if 300 <= code < 400:
        # Any redirect after the POST (307/308 included: the receiver may have taken the body before answering it) is
        # not followed and not assumed undone (spec §7): the owner reconciles.
        return Outcome("unknown", f"HTTP {code}: redirected after the POST (not followed): it may have been done", rc,
                       http_status=code, maybe_acted=True)
    if code >= 500:
        o = _ambiguous(action, f"HTTP {code}: the receiver failed, it may have been done", rc, code)
        o.retry_after = _retry_after(_R)
        return o
    return Outcome("failed", f"HTTP {code}", rc, http_status=code, maybe_acted=False)


async def run_http(action: dict, ctx: dict, transport=None, resolve=None) -> Outcome:
    import httpx
    why = await check_address(action["url"], action.get("allow_private", False), resolve)
    if why:
        return _refused(why)
    body, ct = build_body(action, ctx)
    try:
        async with httpx.AsyncClient(transport=transport or default_transport(action.get("allow_private", False),
                                                                               resolve),
                                     follow_redirects=False, timeout=action.get("timeout_s", TIMEOUT_DEFAULT_S)) as cl:
            code, rh, text = await _send(cl, "POST", target_url(action, ctx), content=body,
                                         headers=_headers(action, ctx, ct))
    except AddressRefused as e:
        return Outcome("failed", f"{e} (set allow_private to call it)", maybe_acted=False)
    except (httpx.ConnectError, httpx.ConnectTimeout, NoNetwork) as e:
        return Outcome("retry", f"not sent: {type(e).__name__}", maybe_acted=False)
    except httpx.TimeoutException as e:
        return _ambiguous(action, f"no answer in time ({type(e).__name__}): it may have been done")
    except httpx.HTTPError as e:
        return _ambiguous(action, f"connection dropped ({type(e).__name__}): it may have been done")
    return _outcome_of(code, text, rh, action)


def _receipt(text: str, did: str, ran: bool = False) -> Outcome:
    """An Apps Script web app answers with ContentService JSON. `{"ok": true}` (echoing `delivery_id` when it keeps
    one) is a receipt; `{"ok": false, "error": ...}` is a refusal (a 200 is not a business success); anything else
    (often Google's sign-in page) is not a receipt. `ran`: the answer came through the echo hop, so Google already ran
    doPost: a receipt that cannot be read then says nothing about whether it acted (unknown, never a certain failure
    the owner would retry into a second order)."""
    def unreadable(why: str, rc: dict) -> Outcome:
        if ran:
            return Outcome("unknown", why + ": the script ran, check the sheet before retrying", rc, maybe_acted=True)
        return Outcome("failed", why, rc, maybe_acted=None)
    try:
        doc = json.loads(text)
    except ValueError:
        low = text.lower()
        hint = " (the web app must be deployed with access: Anyone)" if "accounts.google.com" in low or "<html" in low else ""
        return unreadable("Apps Script answered without a JSON receipt" + ("" if ran else hint), {"body": _short(text)})
    if not isinstance(doc, dict):
        return unreadable("Apps Script receipt is not an object", {"body": _short(text)})
    rc = {"receipt": doc if len(json.dumps(doc, default=str)) <= RESPONSE_KEEP else {"ok": doc.get("ok")}}
    if doc.get("delivery_id") not in (None, "", did):
        return unreadable("Apps Script receipt names another delivery", rc)
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
    action, the echo host's address checked too) and treat it as the receipt. The POST is never repeated."""
    import httpx
    why = await check_address(action["url"], False, resolve)
    if why:
        return _refused(why)
    body, ct = build_body(action, ctx)
    try:
        async with httpx.AsyncClient(transport=transport or default_transport(False, resolve), follow_redirects=False,
                                     timeout=action.get("timeout_s", 30.0)) as cl:
            resp = await cl.post(target_url(action, ctx), content=body, headers=_headers(action, ctx, ct))
            if resp.status_code in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location") or ""
                host = urlsplit(loc).hostname or ""
                if host == "accounts.google.com" or host.endswith(".accounts.google.com"):
                    return Outcome("blocked", "Apps Script asked to sign in: the script did not run (deploy the web "
                                   "app with access: Anyone)", {"location": _short(loc)}, maybe_acted=False)
                if urlsplit(loc).scheme != "https" or host not in APPS_SCRIPT_ECHO_HOSTS:
                    return Outcome("unknown", "Apps Script redirected somewhere unexpected: the script may have run",
                                   {"location": _short(loc)}, maybe_acted=True)
                hop = await check_address(loc, False, resolve)
                if hop:
                    return Outcome("unknown", f"the receipt address was refused ({hop}): the script may have run",
                                   {"location": _short(loc)}, maybe_acted=True)
                try:
                    ecode, _, etext = await _send(cl, "GET", loc, headers={"User-Agent": "Javis-Webhook/1"})
                except (httpx.HTTPError, AddressRefused) as e:
                    return Outcome("unknown", f"the script ran but its receipt could not be read ({type(e).__name__})",
                                   maybe_acted=True)
                if ecode != 200:
                    return Outcome("unknown", f"receipt page answered HTTP {ecode}: the script may have run",
                                   maybe_acted=True)
                out = _receipt(etext, ctx["delivery_id"], ran=True)
                out.http_status = resp.status_code
                return out
    except AddressRefused as e:
        return Outcome("failed", str(e), maybe_acted=False)
    except (httpx.ConnectError, httpx.ConnectTimeout, NoNetwork) as e:
        return Outcome("retry", f"not sent: {type(e).__name__}", maybe_acted=False)
    except httpx.TimeoutException as e:
        return _ambiguous(action, f"no answer in time ({type(e).__name__}): the script may have run")
    except httpx.HTTPError as e:
        return _ambiguous(action, f"connection dropped ({type(e).__name__}): the script may have run")
    if resp.status_code == 200:
        out = _receipt(resp.text, ctx["delivery_id"])
        out.http_status = 200
        return out
    return _outcome_of(resp.status_code, resp.text, resp.headers, action)


def envelope(ctx: dict, level: str) -> dict:
    """What a plugin handler receives (spec §8.2): ids, attempt, source, brain, configuration revision, the verified
    metadata, the parsed payload, the raw body's hash and the business key. Never the owner's cookie or the sender's
    signing secret."""
    return {**_meta(ctx), "attempt": int(ctx.get("attempt") or 1), "generation": int(ctx.get("generation") or 1),
            "source": ctx.get("source") or "http", "brain": ctx.get("brain", ""), "revision": ctx.get("revision"),
            "verified": ctx.get("verified") or {}, "fields": ctx.get("fields") or {}, "payload": ctx.get("payload"),
            "raw_sha256": hashlib.sha256(bytes(ctx.get("body") or b"")).hexdigest(),
            "business_key": ctx.get("business_key") or "", "level": level}


def plugin_precheck(action: dict, found: Optional[dict], level: str, ctx: dict) -> Optional[Outcome]:
    """Before dispatch: an Outcome that closes the delivery without calling the plugin, or None to call it."""
    if not found:
        return Outcome("blocked", f"plugin handler {action['plugin']}/{action['handler']} is not installed or is off",
                       maybe_acted=False)
    why = level_ok(action, level, found.get("min_mode", "full"))
    if why:
        return Outcome("blocked", why, maybe_acted=False)
    if found.get("ai") and not action.get("allow_ai"):
        return Outcome("blocked", "this plugin handler uses AI: allow it in the action (allow_ai) to run it",
                       maybe_acted=False)
    schema = found.get("schema")
    if schema:
        import webhook_rules
        env = envelope(ctx, level)
        bad = []
        for path, spec in (schema.get("fields") or {}).items():
            v = webhook_rules.get_path(env, path)
            if v is webhook_rules._MISSING:
                if spec.get("required"):
                    bad.append(f"{path}: missing")
            elif not webhook_rules._matches_type(v, spec.get("type", "any")):
                bad.append(f"{path}: expected {spec.get('type')}, got {webhook_rules.type_of(v)}")
        if bad:
            return Outcome("failed", "the event does not fit the handler's schema: " + "; ".join(bad[:4]),
                           maybe_acted=False)
    return None


async def run_plugin(action: dict, ctx: dict, found: Optional[dict], level: str, reserved: bool = False) -> Outcome:
    """`found` = {"handler", "ctx", "min_mode", "schema", "ai", "idempotent"} of an ENABLED plugin visible to the hook's
    brain, or None. handler(envelope, plugin_ctx) -> {"status": completed | accepted | retryable_error |
    permanent_error | unknown | waiting_approval, "ref"?: job id, "detail"?: str}. `reserved` = the caller holds a
    slot from plugin_reserve: the call uses it (or gives it back when it never starts)."""
    slug = str(action.get("plugin") or "")
    pre = plugin_precheck(action, found, level, ctx)
    if pre:
        if reserved:
            plugin_unreserve(slug)
        return pre
    try:
        delivery = envelope(ctx, level)
    except BaseException:
        if reserved:
            plugin_unreserve(slug)
        raise
    did = ctx["delivery_id"]
    h = found["handler"]
    try:
        if inspect.iscoroutinefunction(h):
            _INFLIGHT.add(did)
            try:
                res = await asyncio.wait_for(h(delivery, found.get("ctx")), PLUGIN_TIMEOUT_S)
            finally:
                _INFLIGHT.discard(did)
        else:
            if not reserved:
                with _SLUG_LOCK:
                    if _SLUG_INFLIGHT.get(slug, 0) >= PLUGIN_PER_SLUG or not _PLUGIN_SLOTS.acquire(blocking=False):
                        return Outcome("retry", "not sent: plugin handlers are busy (earlier calls still running)",
                                       maybe_acted=False)
                    _SLUG_INFLIGHT[slug] = _SLUG_INFLIGHT.get(slug, 0) + 1
            _INFLIGHT.add(did)
            fut = asyncio.get_running_loop().run_in_executor(_plugin_pool(), _call_release, h, delivery,
                                                              found.get("ctx"), did, slug)
            res = await asyncio.wait_for(asyncio.shield(fut), PLUGIN_TIMEOUT_S)
            if inspect.isawaitable(res):
                res = await asyncio.wait_for(res, PLUGIN_TIMEOUT_S)
    except asyncio.TimeoutError:
        return Outcome("unknown", f"plugin did not answer in {int(PLUGIN_TIMEOUT_S)} s: it may have acted",
                       maybe_acted=True)
    except Exception as e:
        # The handler broke its contract mid-way: it may have acted. One that keeps the delivery id (idempotent)
        # can take it again.
        st = "retry" if found.get("idempotent") else "unknown"
        return Outcome(st, f"plugin error: {type(e).__name__}: {e}"[:300], maybe_acted=True)
    if not isinstance(res, dict) or res.get("status") not in PLUGIN_RESULTS:
        return Outcome("unknown", "plugin answered without a known status (completed, accepted, retryable_error, "
                       "permanent_error, unknown, waiting_approval)", maybe_acted=True)
    st = PLUGIN_RESULTS[res["status"]]
    rc = {"ref": str(res.get("ref") or "")[:200], "result": res["status"]}
    return Outcome(st, str(res.get("detail") or f"plugin {res['status']}")[:300], rc,
                   maybe_acted=st not in ("retry", "failed") or None)


def tool_args(action: dict, ctx: dict) -> dict:
    """The tool's arguments (spec §8.3): `{{payload.x}}`, `{{fields.x}}`, `{{event.id}}`, `{{delivery.id}}` are data
    paths (a whole-value expression keeps its type); the older `{field}` reads a mapped field. A missing field raises
    webhook_rules.TemplateError: the tool is not called with an empty recipient, amount or id."""
    import webhook_rules
    tctx = {"payload": ctx.get("payload"), "fields": ctx.get("fields") or {},
            "event": {"id": ctx["event_id"], "hook_id": ctx["hook_id"], "received_at": ctx["received_at"]},
            "delivery": {"id": ctx["delivery_id"], "action_id": ctx["action_id"]}}
    return {k: webhook_rules.render_value(v, tctx) for k, v in (action.get("args") or {}).items()}


async def run_tool(action: dict, ctx: dict, call_tool: Optional[Callable], level: str,
                   args: Optional[dict] = None) -> Outcome:
    """A tool through the hub dispatcher, at the hook's CURRENT level: the hub applies the same permission rules as
    for any background run (a `danger` tool needs full, the connection's own limit applies too)."""
    if not call_tool:
        return Outcome("blocked", "tools are not available to webhooks on this server", maybe_acted=False)
    if args is None:
        args = tool_args(action, ctx)
    try:
        res = await asyncio.wait_for(call_tool(ctx.get("brain", ""), level, action["tool"], args), TOOL_TIMEOUT_S)
    except asyncio.TimeoutError:
        return _ambiguous(action, f"tool did not answer in {int(TOOL_TIMEOUT_S)} s: it may have acted")
    except Exception as e:
        return _ambiguous(action, f"tool call broke ({type(e).__name__}): it may have acted")
    text = str(res or "")
    if text.startswith("ERROR: gọi tool lỗi"):
        return _ambiguous(action, "the tool call broke after it was sent: it may have acted", {"result": _short(text)})
    if text.startswith("ERROR:"):
        # The hub's own refusals happen BEFORE the tool runs (certainly not done). Its permission guard says "bị chặn"
        # and a missing tool "không tồn tại" / "không có tool": the configuration, so blocked. Its rate limit and a
        # source that did not start: not sent, try later. Anything else is the tool's own refusal of this event.
        low = text.lower()
        if "vượt giới hạn tần suất" in low or "không khởi động được" in low:
            return Outcome("retry", "not sent: " + text[6:].strip()[:280], {"result": _short(text)}, maybe_acted=False)
        st = "blocked" if any(w in low for w in ("bị chặn", "không tồn tại", "không có tool", "route entry")) else "failed"
        return Outcome(st, text[6:].strip()[:300], {"result": _short(text)}, maybe_acted=False)
    return Outcome("completed", f"tool {action['tool']} ran", {"result": _short(text)})
