"""Fail-closed rendered reads from the login vault, never a general browser tool.

Only server-reviewed, exact requests may leave the browser. The initial MISA policy
admits the two requested documents, but deliberately has no guessed API/asset rules.
A deployment must review those rules before this adapter can read real inventory.
"""
from __future__ import annotations

import asyncio
import base64
import http.client
import ipaddress
import os
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

import turn_context

HOST = "amisapp.misa.vn"
PAGES = frozenset({"https://" + HOST + "/warehouse/stock-management/stock-list",
                   "https://" + HOST + "/warehouse/deskwork"})
MAX_BYTES = 8 * 1024 * 1024
MAX_REQUESTS = 200
MAX_TEXT = 15000


class ReadBlocked(Exception):
    """Fixed codes only: never include URLs, headers, page text or exception details."""


@dataclass(frozen=True)
class Rule:
    url: str
    resource_type: str


# No wildcard, extension heuristic, GET-means-read assumption, or model-editable policy.
# Add assets and read APIs only after an authenticated staging review of their semantics.
MISA_RULES: tuple[Rule, ...] = tuple(Rule(url, "document") for url in sorted(PAGES))


def check_request(url: str, method: str, resource_type: str, rules=MISA_RULES) -> None:
    try:
        p = urlsplit(url)
        valid = (p.scheme == "https" and p.hostname == HOST and p.port in (None, 443)
                 and not p.username and not p.password and not p.fragment)
    except ValueError:
        valid = False
    if not valid or method != "GET" or Rule(url, resource_type) not in rules:
        raise ReadBlocked("request_not_reviewed")


def public_addresses(host: str, port: int) -> list[str]:
    if host != HOST or port != 443:
        raise ReadBlocked("invalid_host")
    answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = sorted({a[4][0] for a in answers})
    if not addresses:
        raise ReadBlocked("dns_blocked")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if (not ip.is_global or ip.is_multicast or ip.is_unspecified
                or getattr(ip, "ipv4_mapped", None) is not None
                or ip in ipaddress.ip_network("64:ff9b::/96")
                or ip in ipaddress.ip_network("2002::/16")):
            raise ReadBlocked("dns_blocked")
    return addresses


class _PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        # Resolve ONCE and connect to that numeric address. TLS still verifies the real hostname.
        address = public_addresses(self.host, self.port)[0]
        raw = socket.create_connection((address, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def fetch_reviewed(url: str, headers: dict) -> tuple[int, dict, bytes]:
    """No proxy env, redirect following, cookie jar, request logging or exception text."""
    p = urlsplit(url)
    conn = _PinnedHTTPS(HOST, 443, timeout=12, context=ssl.create_default_context())
    # Never forward page-controlled proxy, host or connection headers.
    safe = {k: v for k, v in headers.items()
            if k.lower() in {"accept", "accept-language", "user-agent", "cookie", "authorization"}}
    try:
        conn.request("GET", p.path + (("?" + p.query) if p.query else ""), headers=safe)
        response = conn.getresponse()
        if response.status in (401, 403):
            raise ReadBlocked("signed_out")
        if 300 <= response.status < 400:
            raise ReadBlocked("redirect_blocked")
        if response.status != 200:
            raise ReadBlocked("upstream_error")
        if "attachment" in (response.getheader("Content-Disposition") or "").lower():
            raise ReadBlocked("download_blocked")
        body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ReadBlocked("response_too_large")
        # Drop Set-Cookie and all response headers except the MIME type. No generated secrets exported.
        return response.status, {"content-type": response.getheader("Content-Type") or "text/plain"}, body
    except ReadBlocked:
        raise
    except Exception:
        raise ReadBlocked("upstream_error") from None
    finally:
        conn.close()


def redact(text: str, cookies: list, origins: list) -> str:
    values = [str(c.get("value") or "") for c in cookies]
    values += [str(i.get("value") or "") for o in origins for i in o.get("localStorage", [])]
    # Suppress the entire output on a known-secret echo, including common encodings.
    for value in values:
        if value and any(v in text for v in (value, quote(value, safe=""),
                                              base64.b64encode(value.encode()).decode())):
            raise ReadBlocked("secret_in_output")
    return text[:MAX_TEXT]


async def render(url: str, cookies: list, origins: list, *, rules=MISA_RULES,
                 fetch=fetch_reviewed, executable="") -> dict:
    # The Playwright driver inherits the parent env before chromium.launch(env=...).
    # Refuse protocol/debug dumps before creating it, rather than mutating global process env.
    if any(os.environ.get(k) for k in ("DEBUG", "PWDEBUG", "DEBUG_FILE", "SSLKEYLOGFILE")):
        raise ReadBlocked("debugging_not_allowed")
    from playwright.async_api import async_playwright

    blocked: set[str] = set()
    requests = 0
    browser = context = None
    # No debug output, protocol dump, tracing, video, HAR, persistent profile, or storage-state file.
    env = {k: v for k, v in os.environ.items()
           if k not in {"DEBUG", "PWDEBUG", "DEBUG_FILE", "SSLKEYLOGFILE", "NODE_OPTIONS"}}
    async with async_playwright() as pw:
        try:
            kwargs = {"headless": True, "env": env,
                      "proxy": {"server": "http://127.0.0.1:9", "bypass": "<-loopback>"},
                      "args": ["--disable-background-networking", "--disable-component-update",
                               "--disable-quic", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]}
            if executable:
                kwargs["executable_path"] = executable
            browser = await pw.chromium.launch(**kwargs)
            context = await browser.new_context(service_workers="block", accept_downloads=False,
                                                 storage_state={"cookies": cookies, "origins": origins})

            async def route_request(route):
                nonlocal requests
                requests += 1
                try:
                    if requests > MAX_REQUESTS:
                        raise ReadBlocked("request_limit")
                    request = route.request
                    check_request(request.url, request.method, request.resource_type, rules)
                    status, headers, body = await asyncio.to_thread(fetch, request.url, await request.all_headers())
                    await route.fulfill(status=status, headers=headers, body=body)
                except Exception as exc:
                    blocked.add(str(exc) if isinstance(exc, ReadBlocked) else "render_error")
                    await route.abort()

            await context.route("**/*", route_request)
            async def close_socket(ws):
                blocked.add("websocket_blocked")
                await ws.close()

            await context.route_web_socket("**/*", close_socket)
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=25000)
            # No model-provided JavaScript, selectors, clicks, form submission or page interaction.
            title = await page.title()
            text = await page.locator("body").inner_text(timeout=5000)
            import login_vault
            if login_vault.looks_signed_out(page.url, title):
                raise ReadBlocked("signed_out")
            if page.url != url:
                raise ReadBlocked("redirect_blocked")
            if blocked:
                raise ReadBlocked("signed_out" if "signed_out" in blocked else "request_not_reviewed")
            # Never return a URL/title controlled by the page or any raw DOM/storage/headers.
            return {"ok": True, "text": redact(text, cookies, origins), "url": url}
        except ReadBlocked:
            raise
        except Exception:
            raise ReadBlocked("signed_out" if "signed_out" in blocked else "render_error") from None
        finally:
            try:
                if context:
                    await context.close()
            finally:
                if browser:
                    await browser.close()


async def open_misa(vault, url: str, login: str) -> dict:
    """Owner identity comes from host context, never a model argument. Secrets stay in-process."""
    turn = turn_context.current()
    if not turn or turn.get("la_chu") is not True:
        return {"ok": False, "code": "owner_required"}
    if os.environ.get("JAVIS_MISA_BROWSER_ENABLED") != "1":
        return {"ok": False, "code": "adapter_not_enabled"}
    if url not in PAGES:
        return {"ok": False, "code": "page_not_allowed"}
    row = vault.store.get(login) or vault.store.find_name(login)
    if not row or not row.get("allow_ai"):
        return {"ok": False, "code": "login_not_allowed"}
    if row.get("expires_at") and row["expires_at"] <= time.time():
        return {"ok": False, "code": "signed_out"}
    import login_vault
    # Do not use cookies() or any API returning secrets to the caller/model.
    cookies = login_vault._decrypt(row["cookies_enc"])
    cookies = [c for c in cookies if login_vault.matches([c], url)]
    if not cookies:
        return {"ok": False, "code": "domain_or_expiry"}
    origins = login_vault._decrypt(row.get("origins_enc") or "")
    origins = [o for o in origins if o.get("origin") == "https://" + HOST]
    try:
        import optional_tools
        result = await asyncio.wait_for(render(url, cookies, origins,
                                              executable=optional_tools.duong_dan_chrome()), 40)
        return result
    except ReadBlocked as exc:
        return {"ok": False, "code": str(exc)}
    except (Exception, asyncio.TimeoutError):
        return {"ok": False, "code": "browser_unavailable"}
