"""Custom API connector: any REST API with an API key (transport "internal", catalog id `http-api`).

Many tools (POS, CRM, shipping, e-invoices...) publish a REST API and a key but no MCP server. The owner fills in a
base URL and a key on the Connections page; every engine then calls the API through ONE tool, `api_request`, and the
server adds the key on the way out. Several APIs are several connections, each namespaced by the hub.

spec["secrets"] (from `mcp_store.resolved`, all encrypted at rest):
    base_url       required, e.g. https://api.example.com/v1
    api_key        required
    auth_style     optional, how the key travels. Empty = "Authorization: Bearer {key}". Also accepted:
                   "X-API-Key: {key}" (any header, {key} is replaced), "X-Token" (a bare header name, raw key),
                   "?api_key={key}" (query parameter). "Authorization: Basic {key}" with a "user:secret" key is
                   base64-encoded.
    extra_headers  optional, one "Name: value" per line, sent on every call (a shop id, a second secret)
    docs_url       optional, shown to the model so it can read the API docs
    notes          optional, the owner's notes for the model (common endpoints, rules)

Rules kept here (tests/python/test_http_api_connector.py):
- The key never reaches the model: it is not in the tool description and every secret value is scrubbed from results.
- The key only goes to the base URL's host: absolute URLs and redirects to another origin are refused / not followed.
- Plain http only for loopback, private and single-label hosts, so a key never crosses the internet in clear text.
- Permissions come from the catalog's `call_rules` on `method`: GET/HEAD/OPTIONS read, anything else needs Full
  access. So a GET may not carry a body or a method-override header, which would turn a read into a write.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import re
from urllib.parse import urljoin, urlsplit

import httpx

import localefmt

_transport = None          # tests put an httpx.MockTransport here

METHODS = ("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE")
READ_METHODS = ("GET", "HEAD", "OPTIONS")
TIMEOUT = 60.0
MAX_REDIRECTS = 5
MAX_READ = 2_000_000       # bytes read from the wire
MAX_OUT = 24_000           # characters handed to the model
_OVERRIDE_HEADERS = {"x-http-method-override", "x-http-method", "x-method-override"}
_FIXED_HEADERS = {"host", "content-length", "transfer-encoding", "connection"}
_HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$")
_PLACEHOLDER = re.compile(r"\{(?:api_)?key\}")


def _err(vi, en):
    return "ERROR: " + localefmt.chu(vi, en)


def _t(name, description, props, required=None):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": props, "required": required or []}}


# ------------------------------------------------------------------ config

def _private_host(host: str) -> bool:
    h = (host or "").strip("[]").lower()
    if h == "localhost" or h.endswith((".localhost", ".local", ".lan", ".internal", ".home.arpa")):
        return True
    if "." not in h and ":" not in h:
        return True                       # single-label name on the LAN ("nas")
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _base(secrets):
    """(base_url, origin, error)."""
    raw = str(secrets.get("base_url") or "").strip()
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return "", "", _err("Địa chỉ gốc của API phải bắt đầu bằng https:// (ví dụ https://api.ten-dich-vu.com/v1).",
                            "The API base URL must start with https:// (for example https://api.example.com/v1).")
    if parts.scheme == "http" and not _private_host(parts.hostname):
        return "", "", _err("Địa chỉ http:// sẽ gửi API key qua mạng không mã hoá. Dùng https://, hoặc http chỉ cho "
                            "máy trong mạng nội bộ.",
                            "An http:// address would send the API key unencrypted. Use https://, or http only for a "
                            "machine on your local network.")
    base = raw.rstrip("/") + "/"
    return base, _origin(base), ""


def _origin(url):
    p = urlsplit(url)
    port = p.port or (443 if p.scheme == "https" else 80)
    return (p.scheme, (p.hostname or "").lower(), port)


def _auth(secrets):
    """(headers, query, secret_values, error) carrying the key."""
    key = str(secrets.get("api_key") or "").strip()
    if not key:
        return {}, {}, [], _err("Chưa có API key.", "No API key is set.")
    style = str(secrets.get("auth_style") or "").strip() or "Authorization: Bearer {key}"
    values = [key]
    m = re.fullmatch(r"\??\s*([A-Za-z0-9_.\-\[\]]+)\s*=\s*\{(?:api_)?key\}", style)
    if m:
        return {}, {m.group(1): key}, values, ""
    if ":" in style:
        name, tmpl = style.split(":", 1)
        name, tmpl = name.strip(), tmpl.strip()
        if not _HEADER_NAME.match(name) or not _PLACEHOLDER.search(tmpl):
            return {}, {}, [], _err("Cách gửi key phải có dạng 'Tên-header: ... {key}' hoặc '?tham_so={key}'.",
                                    "The key format must look like 'Header-Name: ... {key}' or '?param={key}'.")
        if tmpl.lower().startswith("basic ") and ":" in key:
            encoded = base64.b64encode(key.encode()).decode()
            values.append(encoded)
            return {name: _PLACEHOLDER.sub(encoded, tmpl)}, {}, values, ""
        return {name: _PLACEHOLDER.sub(key, tmpl)}, {}, values, ""
    if _HEADER_NAME.match(style):
        return {style: key}, {}, values, ""
    return {}, {}, [], _err("Cách gửi key phải có dạng 'Tên-header: ... {key}' hoặc '?tham_so={key}'.",
                            "The key format must look like 'Header-Name: ... {key}' or '?param={key}'.")


def _extra_headers(secrets):
    out = {}
    for line in str(secrets.get("extra_headers") or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, value = line.split(":", 1)
        name = name.strip()
        if _HEADER_NAME.match(name):
            out[name] = value.strip()
    return out


# ------------------------------------------------------------------ tools

async def list_tools(spec):
    secrets = (spec or {}).get("secrets") or {}
    base = str(secrets.get("base_url") or "").strip()
    docs = str(secrets.get("docs_url") or "").strip()
    notes = str(secrets.get("notes") or "").strip()[:1500]
    desc = ("Call this connected REST API. Base URL: " + (base or "(not set)") + ". "
            "Authentication is added automatically by the server: never ask the user for the key and never put "
            "it in headers, query or body. `path` is relative to the base URL (an absolute URL must stay on the "
            "same host). GET/HEAD/OPTIONS only read; POST/PUT/PATCH/DELETE change data on the real service and "
            "need Full access on this connection, so use them only when the user asked for that change.")
    if docs:
        desc += " API documentation: " + docs + " (read it with a web fetch tool when unsure of an endpoint)."
    if notes:
        desc += " Owner's notes: " + notes
    return [_t("api_request", desc, {
        "method": {"type": "string", "enum": list(METHODS), "description": "HTTP method, default GET"},
        "path": {"type": "string", "description": "path under the base URL, e.g. /orders?status=new"},
        "query": {"type": "object", "description": "query parameters"},
        "body": {"description": "request body for POST/PUT/PATCH/DELETE: an object/array (JSON) or a string"},
        "body_format": {"type": "string", "enum": ["json", "form", "raw"],
                        "description": "json (default), form (x-www-form-urlencoded) or raw string"},
        "headers": {"type": "object", "description": "extra non-auth headers"},
    }, ["path"])]


def _scrub(text, secrets_values):
    for v in sorted({s for s in secrets_values if s and len(s) >= 4}, key=len, reverse=True):
        text = text.replace(v, "***")
    return text


def _target(base, origin, path):
    path = str(path or "").strip()
    if path.startswith("//"):
        return "", _err("Đường dẫn không được đổi sang máy chủ khác.", "The path may not switch to another host.")
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path):
        if _origin(path) != origin:
            return "", _err("Chỉ gọi được đúng máy chủ của địa chỉ gốc; API key không được gửi tới máy chủ khác.",
                            "Only the base URL's host can be called; the API key is never sent to another host.")
        return path, ""
    return urljoin(base, path.lstrip("/")), ""


def _model_headers(raw, blocked):
    if raw in (None, ""):
        return {}, ""
    if not isinstance(raw, dict):
        return {}, _err("headers phải là object.", "headers must be an object.")
    out = {}
    for k, v in raw.items():
        name, value = str(k).strip(), "" if v is None else str(v)
        if not _HEADER_NAME.match(name) or "\r" in value or "\n" in value:
            return {}, _err("Header không hợp lệ: " + name[:40], "Invalid header: " + name[:40])
        low = name.lower()
        if low in _OVERRIDE_HEADERS:
            return {}, _err("Không được đổi phương thức bằng header; hãy dùng đúng method.",
                            "The method may not be changed through a header; use the right method.")
        if low in blocked or low in _FIXED_HEADERS:
            continue                      # the server's auth and framing headers win
        out[name] = value
    return out, ""


def _body_kwargs(method, args):
    body = args.get("body")
    if body is None or body == "":
        return {}, ""
    if method in READ_METHODS:
        return {}, _err(method + " không được kèm body.", method + " may not carry a body.")
    fmt = str(args.get("body_format") or "").strip().lower() or ("raw" if isinstance(body, str) else "json")
    if fmt == "form":
        if not isinstance(body, dict):
            return {}, _err("body dạng form phải là object.", "A form body must be an object.")
        return {"data": {str(k): "" if v is None else str(v) for k, v in body.items()}}, ""
    if fmt == "raw":
        return {"content": body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)}, ""
    return {"json": body}, ""


def _render(resp, data, truncated_wire):
    ctype = (resp.headers.get("content-type") or "").lower()
    out = {"status": resp.status_code, "host": resp.request.url.host, "url": str(resp.request.url),
           "content_type": ctype.split(";")[0]}
    if resp.is_redirect and resp.headers.get("location"):
        out["location"] = resp.headers["location"]
    textual = (not ctype or "json" in ctype or ctype.startswith("text/") or "xml" in ctype
               or "javascript" in ctype or "x-www-form-urlencoded" in ctype)
    if not data:
        out["body"] = ""
    elif not textual:
        out["body"] = f"[binary content, {len(data):,} bytes, not shown]"
    else:
        text = data.decode(resp.charset_encoding or "utf-8", errors="replace")
        parsed = None
        if "json" in ctype or text[:1] in "[{":
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
        out["body"] = parsed if parsed is not None else text
    if truncated_wire:
        out["note"] = f"Response was longer than {MAX_READ:,} bytes; only the start was read."
    return out


async def _send(client, method, url, headers, query, body_kwargs):
    req = client.build_request(method, url, headers=headers, params=query or None, **body_kwargs)
    resp = await client.send(req, stream=True)
    try:
        chunks, size, cut = [], 0, False
        if method != "HEAD":
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size >= MAX_READ:
                    cut = True
                    break
        return resp, b"".join(chunks)[:MAX_READ], cut
    finally:
        await resp.aclose()


async def call(tool, arguments, spec):
    if tool != "api_request":
        return f"ERROR: tool '{tool}' is not part of the custom API connector"
    args = arguments or {}
    secrets = (spec or {}).get("secrets") or {}
    base, origin, err = _base(secrets)
    if err:
        return err
    auth_headers, auth_query, secret_values, err = _auth(secrets)
    if err:
        return err
    extra = _extra_headers(secrets)
    secret_values += [v for v in extra.values()]

    method = args.get("method", "GET")
    method = method.strip().upper() if isinstance(method, str) else ""
    method = method or "GET"
    if method not in METHODS:
        return _err("Phương thức không hỗ trợ: ", "Unsupported method: ") + str(args.get("method"))[:20]
    url, err = _target(base, origin, args.get("path"))
    if err:
        return err
    blocked = {k.lower() for k in list(auth_headers) + list(extra)}
    model_headers, err = _model_headers(args.get("headers"), blocked)
    if err:
        return err
    body_kwargs, err = _body_kwargs(method, args)
    if err:
        return err
    query = args.get("query") or {}
    if not isinstance(query, dict):
        return _err("query phải là object.", "query must be an object.")
    query = {str(k): ("" if v is None else v) for k, v in query.items()}
    query.update(auth_query)
    headers = {**model_headers, **extra, **auth_headers}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, transport=_transport) as client:
            resp, data, cut = await _send(client, method, url, headers, query, body_kwargs)
            hops = 0
            while resp.is_redirect and hops < MAX_REDIRECTS:
                nxt = urljoin(str(resp.request.url), resp.headers.get("location") or "")
                if _origin(nxt) != origin:
                    break                 # another host: report it, never carry the key there
                hops += 1
                if resp.status_code == 303 or (resp.status_code in (301, 302) and method == "POST"):
                    method, body_kwargs = "GET", {}
                # the key rides again only on the same origin; the query already sits in the new URL or not at all
                resp, data, cut = await _send(client, method, nxt, headers, auth_query, body_kwargs)
    except httpx.TimeoutException:
        return _err("API không trả lời sau 60 giây.", "The API did not answer within 60 seconds.")
    except httpx.HTTPError as e:
        return _scrub(_err("Không gọi được API: ", "Could not reach the API: ") + f"{type(e).__name__}: {e}"[:300],
                      secret_values)

    text = json.dumps(_render(resp, data, cut), ensure_ascii=False)
    text = _scrub(text, secret_values)
    if len(text) > MAX_OUT:
        text = (text[:MAX_OUT] + f"\n... [truncated: {len(text) - MAX_OUT:,} more characters. Narrow the request "
                "with query parameters, paging or a more specific path.]")
    return text
