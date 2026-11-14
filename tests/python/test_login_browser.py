"""Security checks use synthetic credentials only; no MISA or live vault access."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import base64
import json
import os
import socket
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import login_browser as lb
import login_vault as lv
import turn_context

URL = sorted(lb.PAGES)[0]
COOKIE = {"name": "sid", "value": "synthetic-private-session", "domain": lb.HOST,
          "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax", "expires": -1}
ORIGIN = {"origin": "https://" + lb.HOST,
          "localStorage": [{"name": "token", "value": "synthetic-storage-secret"}]}


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("url,method,kind", [
    ("http://" + lb.HOST + "/warehouse/deskwork", "GET", "document"),
    ("https://" + lb.HOST + ".evil.com/warehouse/deskwork", "GET", "document"),
    ("https://user:password@" + lb.HOST + "/warehouse/deskwork", "GET", "document"),
    ("https://" + lb.HOST + ":444/warehouse/deskwork", "GET", "document"),
    ("https://127.0.0.1/", "GET", "document"),
    ("https://169.254.169.254/", "GET", "document"),
    (URL, "POST", "document"), (URL, "PUT", "document"), (URL, "DELETE", "document"),
    (URL, "PATCH", "fetch"), (URL, "GET", "fetch"),
    ("https://" + lb.HOST + "/api/delete", "GET", "fetch"),
    (URL + "?action=delete", "GET", "document"),
    ("https://" + lb.HOST + "/assets/delete.js", "GET", "script"),
    ("file:///etc/passwd", "GET", "document"),
])
def test_request_scope(url, method, kind):
    with pytest.raises(lb.ReadBlocked):
        lb.check_request(url, method, kind)


def test_allowed_documents_only():
    for url in lb.PAGES:
        lb.check_request(url, "GET", "document")


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.2", "172.16.1.2", "192.168.1.2",
                                      "169.254.169.254", "::1", "fc00::1", "::ffff:8.8.8.8",
                                      "64:ff9b::a00:1", "224.0.0.1", "0.0.0.0"])
def test_dns_blocks_internal_and_transition_addresses(address):
    with patch.object(socket, "getaddrinfo", return_value=[(2, 1, 6, "", (address, 443))]):
        with pytest.raises(lb.ReadBlocked):
            lb.public_addresses(lb.HOST, 443)


def test_dns_mixed_answers_fail_closed():
    answers = [(2, 1, 6, "", (ip, 443)) for ip in ["8.8.8.8", "10.0.0.1"]]
    with patch.object(socket, "getaddrinfo", return_value=answers):
        with pytest.raises(lb.ReadBlocked):
            lb.public_addresses(lb.HOST, 443)


def test_connection_pins_public_address_and_preserves_tls_hostname():
    tls = SimpleNamespace(wrap_socket=lambda raw, server_hostname: (raw, server_hostname))
    with patch.object(lb, "public_addresses", return_value=["8.8.8.8"]) as dns, \
            patch.object(socket, "create_connection", return_value="socket") as connect:
        conn = lb._PinnedHTTPS(lb.HOST, 443)
        conn._context = tls
        conn.connect()
        dns.assert_called_once_with(lb.HOST, 443)
        assert connect.call_args.args[0] == ("8.8.8.8", 443)
        assert conn.sock == ("socket", lb.HOST)


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 500])
def test_redirects_and_upstream_errors_never_follow_or_return_content(status):
    response = SimpleNamespace(status=status)
    conn = SimpleNamespace(request=lambda *a, **k: None, getresponse=lambda: response, close=lambda: None)
    with patch.object(lb, "_PinnedHTTPS", return_value=conn):
        with pytest.raises(lb.ReadBlocked) as error:
            lb.fetch_reviewed(URL, {})
        assert str(error.value) in {"redirect_blocked", "signed_out", "upstream_error"}


@pytest.mark.parametrize("value", [COOKIE["value"], ORIGIN["localStorage"][0]["value"],
                                   base64.b64encode(COOKIE["value"].encode()).decode()])
def test_secret_echo_suppresses_whole_output(value):
    with pytest.raises(lb.ReadBlocked, match="secret_in_output"):
        lb.redact("Inventory " + value, [COOKIE], [ORIGIN])


def vault_stub(**overrides):
    row = {"id": "test", "allow_ai": True, "expires_at": 0,
           "cookies_enc": json.dumps([COOKIE]), "origins_enc": json.dumps([ORIGIN])}
    row.update(overrides)
    return SimpleNamespace(store=SimpleNamespace(get=lambda _: row, find_name=lambda _: row))


def call_open(vault, owner=True):
    token = turn_context.bind(turn_context.make("dashboard", la_chu=owner))
    try:
        return run(lb.open_misa(vault, URL, "Kho Molli"))
    finally:
        turn_context.reset(token)


@pytest.mark.parametrize("owner", [False, None])
def test_untrusted_owner_cannot_decrypt(owner, monkeypatch):
    monkeypatch.setenv("JAVIS_MISA_BROWSER_ENABLED", "1")
    with patch.object(lv, "_decrypt", side_effect=AssertionError("must not decrypt")):
        if owner is None:
            assert run(lb.open_misa(vault_stub(), URL, "Kho Molli"))["code"] == "owner_required"
        else:
            assert call_open(vault_stub(), owner)["code"] == "owner_required"


@pytest.mark.parametrize("row,code", [({"allow_ai": False}, "login_not_allowed"),
                                     ({"expires_at": time.time() - 100}, "signed_out")])
def test_denied_or_expired_before_decryption(row, code, monkeypatch):
    monkeypatch.setenv("JAVIS_MISA_BROWSER_ENABLED", "1")
    with patch.object(lv, "_decrypt", side_effect=AssertionError("must not decrypt")):
        assert call_open(vault_stub(**row))["code"] == code


def test_disabled_adapter_before_decryption(monkeypatch):
    monkeypatch.delenv("JAVIS_MISA_BROWSER_ENABLED", raising=False)
    with patch.object(lv, "_decrypt", side_effect=AssertionError("must not decrypt")):
        assert call_open(vault_stub())["code"] == "adapter_not_enabled"


def test_wrong_cookie_domain_and_expired_cookie(monkeypatch):
    monkeypatch.setenv("JAVIS_MISA_BROWSER_ENABLED", "1")
    for cookie in [{**COOKIE, "domain": "elsewhere.example"}, {**COOKIE, "expires": time.time() - 10}]:
        with patch.object(lv, "_decrypt", side_effect=json.loads), patch.object(lb, "render") as renderer:
            assert call_open(vault_stub(cookies_enc=json.dumps([cookie])))["code"] == "domain_or_expiry"
            renderer.assert_not_called()


def test_server_passes_only_scoped_state_and_returns_no_state(monkeypatch):
    monkeypatch.setenv("JAVIS_MISA_BROWSER_ENABLED", "1")
    origins = [ORIGIN, {"origin": "https://elsewhere.example", "localStorage": []}]
    with patch.object(lv, "_decrypt", side_effect=lambda value: json.loads(value) if value else []), \
            patch.object(lb, "render", new=AsyncMock(return_value={"ok": True, "text": "Stock 7"})) as renderer:
        result = call_open(vault_stub(origins_enc=json.dumps(origins)))
        assert renderer.call_args.args[1:3] == ([COOKIE], [ORIGIN])
        assert result == {"ok": True, "text": "Stock 7"}


def test_renderer_errors_do_not_escape_to_plugin(monkeypatch):
    monkeypatch.setenv("JAVIS_MISA_BROWSER_ENABLED", "1")
    with patch.object(lv, "_decrypt", side_effect=json.loads), \
            patch.object(lb, "render", new=AsyncMock(side_effect=RuntimeError(COOKIE["value"]))):
        assert call_open(vault_stub()) == {"ok": False, "code": "browser_unavailable"}


@pytest.mark.skipif(os.getenv("JAVIS_BROWSER_INTEGRATION") != "1", reason="requires isolated test Chromium")
def test_real_javascript_isolation_cleanup_and_write_blocking():
    from playwright.async_api import async_playwright

    async def exercise():
        browsers, contexts = [], []
        real = async_playwright

        class Tracked:
            async def __aenter__(self):
                self.manager = real()
                pw = await self.manager.__aenter__()
                launch = pw.chromium.launch

                async def tracked_launch(**kwargs):
                    browser = await launch(**kwargs)
                    browsers.append(browser)
                    new_context = browser.new_context

                    async def tracked_context(**kwargs):
                        context = await new_context(**kwargs)
                        contexts.append(context)
                        return context

                    browser.new_context = tracked_context
                    return browser

                pw.chromium.launch = tracked_launch
                return pw

            async def __aexit__(self, *args):
                return await self.manager.__aexit__(*args)

        html = b'''<body>not rendered<script>
        document.body.firstChild.textContent = 'JS rendered stock 7';
        sessionStorage.setItem('isolation', 'first');
        </script></body>'''
        calls = []

        def fetch(url, headers):
            calls.append(url)
            return 200, {"content-type": "text/html"}, html

        with patch("playwright.async_api.async_playwright", Tracked):
            result = await lb.render(URL, [COOKIE], [ORIGIN], fetch=fetch)
            assert result["ok"] and "JS rendered stock 7" in result["text"]
            assert calls == [URL]
            assert all(not b.is_connected() for b in browsers)
            assert all(not c.pages for c in contexts)
            html = b'''<body><script>
            document.body.append(sessionStorage.getItem('isolation') || 'isolated');
            </script></body>'''
            result = await lb.render(URL, [COOKIE], [ORIGIN], fetch=fetch)
            assert result["text"] == "isolated"
            html = b'''<body><script>
            fetch('/api/delete', {method:'POST',body:'x'}).catch(()=>{});
            fetch('/api/delete').catch(()=>{});
            fetch('http://127.0.0.1:1234/').catch(()=>{});
            </script></body>'''
            before = len(calls)
            with pytest.raises(lb.ReadBlocked):
                await lb.render(URL, [COOKIE], [ORIGIN], fetch=fetch)
            assert len(calls) == before + 1  # Only the document ever reaches transport.
            assert all(not b.is_connected() for b in browsers)
            assert all(not c.pages for c in contexts)
            html = b"<body>cancel test</body>"
            def slow_fetch(url, headers):
                time.sleep(0.4)
                return 200, {"content-type": "text/html"}, html
            task = asyncio.create_task(lb.render(URL, [COOKIE], [ORIGIN], fetch=slow_fetch))
            # Wait for a real context, then cancel while the page is still loading.
            previous = len(contexts)
            for _ in range(100):
                if len(contexts) > previous:
                    break
                await asyncio.sleep(0.02)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert all(not b.is_connected() for b in browsers)
            assert all(not c.pages for c in contexts)

    run(exercise())


def test_debug_protocol_logging_is_refused(monkeypatch):
    monkeypatch.setenv("DEBUG", "pw:protocol")
    with pytest.raises(lb.ReadBlocked, match="debugging_not_allowed"):
        run(lb.render(URL, [COOKIE], [ORIGIN]))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
