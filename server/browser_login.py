"""Signed-in browser (2026-11-21): a sign-in from the Cookies page goes into the browser Javis drives.

`javis_login` op=fetch only downloads a page and reads its text. To click a button or fill a form signed in,
Javis needs a real browser that holds the sign-in. Two pieces were already there and not joined: the login
vault keeps cookies in Playwright's own shape, and the Playwright connection drives Chromium. This module joins
them (owner, 2026-11-21: "anh cần cookies điều khiển và điền được form").

How a sign-in gets in: through the Playwright connection's own code tool (`browser_run_code_unsafe`, once
`browser_run_code`), called from here with three fixed snippets (read cookies, add cookies, clear cookies).
Nothing is written to disk, the connection needs no restart and no extra flag, and the snippet's answer stays
in this process: the model gets the page, never the cookies this module handled.

Rules kept here:

- Only a sign-in whose own "act" switch is on, and only for an address its cookies cover (`LoginVault.pick`).
- The browser's copy wins once it is in. Sites renew session cookies as they are used, so a later open adds
  only what is missing and never writes the stored (older) values over the browser's. The stored copy is put
  in whole when it was never there, when the owner pasted new cookies, or when another account of the same
  site took the browser over.
- After a page load that looks signed in, what the browser holds for those sites is saved back, encrypted, so
  op=fetch and page watches keep working with the renewed session.
- One browser, one cookie jar: opens run one at a time (`_LOCK`).
- A customer bot never reaches a browser that has held a sign-in (`in_use`, read by mcp_hub.discover_all).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from typing import Optional

import localefmt
import login_vault

CALL_TIMEOUT = 120        # one tool call; the first one may have to start the browser
LIST_TIMEOUT = 150        # the first tools/list of a fresh `npx` connection downloads the package
MAX_PAGE = 15000          # characters of the first page handed to the model
_RESULT = re.compile(r"### Result\n(.*?)(?:\n### |\Z)", re.S)
_PAGE_URL = re.compile(r"^- Page URL: (\S+)", re.M)
_PAGE_TITLE = re.compile(r"^- Page Title: (.*)$", re.M)
_LOCK = asyncio.Lock()

_JS_READ = "async (page) => await page.context().cookies()"
_JS_ADD = ("async (page) => {{ const ctx = page.context(); const bad = []; for (const c of {cookies}) {{ "
           "try {{ await ctx.addCookies([c]); }} catch (e) {{ bad.push(c.name); }} }} return {{ bad }}; }}")
_JS_CLEAR = ("async (page) => {{ const ctx = page.context(); for (const c of {cookies}) {{ "
             "await ctx.clearCookies({{ name: c.name, domain: c.domain, path: c.path }}); }} return {{ ok: true }}; }}")


class BrowserError(Exception):
    """Message already worded for the owner. `missing`: no browser connection exists at all."""

    def __init__(self, message: str, missing: bool = False):
        super().__init__(message)
        self.missing = missing


def is_browser_spec(spec) -> bool:
    """A Playwright connection, told by its command line the way mcp_store does: it may come from the
    catalog, from a pack or from the owner typing the command."""
    spec = spec or {}
    line = str(spec.get("command") or "") + " " + " ".join(str(a) for a in (spec.get("args") or []))
    return "playwright" in line.lower()


def in_use() -> bool:
    """True once the browser has ever held one of the owner's sign-ins. mcp_hub drops the browser connection
    from a customer bot's tools from then on: a stranger must not browse as the owner."""
    try:
        vault = login_vault.current()
        return bool(vault and vault.browser_in_use())
    except Exception as e:  # noqa: BLE001 - when unsure, keep the bot away
        print(f"[browser_login] in_use: {type(e).__name__}: {e}", file=sys.stderr)
        return True


def _scrub(text, cookies=()) -> str:
    """An error line safe to show: the snippet (it carries cookie values) and the values themselves are cut."""
    text = str(text or "").split("### Ran Playwright code", 1)[0]
    for c in cookies or ():
        v = str(c.get("value") or "")
        if len(v) >= 4:
            text = text.replace(v, "***")
    return " ".join(text.split())[:240]


class Browser:
    """One Playwright connection: its dial spec, the code tool it offers and its name for the model."""

    def __init__(self, spec: dict, conn: dict, code_tool: str):
        self.spec, self.conn, self.code_tool = spec, conn, code_tool
        self.label = conn.get("label") or conn.get("namespace") or "Playwright"
        self.namespace = conn.get("namespace") or conn.get("slug") or conn.get("id") or ""

    async def _call(self, tool: str, args: dict) -> str:
        import mcp_client
        try:
            return str(await asyncio.wait_for(mcp_client.pool.call_tool(self.spec, tool, args), CALL_TIMEOUT))
        except (asyncio.TimeoutError, TimeoutError):
            return "ERROR: " + localefmt.chu("trình duyệt không trả lời kịp", "the browser did not answer in time")

    async def _run(self, code: str, cookies=()):
        out = await self._call(self.code_tool, {"code": code})
        if out.startswith("ERROR:"):
            raise BrowserError(_scrub(out[6:], cookies))
        m = _RESULT.search(out)
        if not m:
            raise BrowserError(localefmt.chu("trình duyệt trả lời không đúng mẫu", "the browser gave an unexpected answer"))
        try:
            return json.loads(m.group(1).strip())
        except ValueError as e:
            raise BrowserError(localefmt.chu("không đọc được câu trả lời của trình duyệt",
                                             "the browser's answer could not be read")) from e

    async def cookies(self) -> list:
        got = await self._run(_JS_READ)
        return [c for c in got if isinstance(c, dict)] if isinstance(got, list) else []

    async def add(self, cookies: list) -> list:
        """Add cookies one at a time, so one the browser refuses does not lose the rest. Returns refused names."""
        got = await self._run(_JS_ADD.format(cookies=json.dumps(cookies, ensure_ascii=False)), cookies)
        return list((got or {}).get("bad") or []) if isinstance(got, dict) else []

    async def clear(self, cookies: list) -> None:
        keys = [{"name": c.get("name"), "domain": c.get("domain"), "path": c.get("path") or "/"} for c in cookies]
        await self._run(_JS_CLEAR.format(cookies=json.dumps(keys, ensure_ascii=False)))

    async def navigate(self, url: str) -> str:
        return await self._call("browser_navigate", {"url": url})


async def find() -> Browser:
    """The Playwright connection to use. Raises BrowserError with words for the owner."""
    import mcp_catalog
    import mcp_client
    import mcp_store
    conns = await asyncio.to_thread(mcp_store.resolved, True)
    seen, why = False, ""
    for conn in conns:
        if not is_browser_spec(conn):
            continue
        seen = True
        if "browser_navigate" in (conn.get("deny_tools") or []):
            why = localefmt.chu(f"kết nối '{conn.get('label')}' đang chặn tool mở trang",
                                f"the connection '{conn.get('label')}' blocks its navigate tool")
            continue
        ok, reason = mcp_catalog.allowed(conn.get("connector"), conn.get("perm"), "full", "browser_navigate", {})
        if not ok:
            why = reason
            continue
        spec = mcp_client._conn_spec(conn)
        try:
            tools = await asyncio.wait_for(mcp_client.pool.list_tools(spec), LIST_TIMEOUT)
        except Exception as e:  # noqa: BLE001 - try the next browser connection, report the last reason
            why = f"{type(e).__name__}: {str(e)[:160]}"
            continue
        names = sorted(str(t.get("name") or "") for t in (tools or []))
        # The owner may have denied the code tool to the MODEL (it runs any script). The three fixed snippets
        # above are not the model's code, so this module still uses it.
        code_tool = next((n for n in names if n.startswith("browser_run_code")), "")
        if "browser_navigate" in names and code_tool:
            return Browser(spec, conn, code_tool)
        why = localefmt.chu(f"kết nối '{conn.get('label')}' không có tool để nạp cookie",
                            f"the connection '{conn.get('label')}' has no tool that can add cookies")
    if not seen:
        raise BrowserError(localefmt.chu(
            "Chưa có kết nối trình duyệt (Playwright). Chủ thêm kết nối Playwright ở trang Kết nối rồi thử lại.",
            "There is no browser connection (Playwright). The owner adds the Playwright connection on the "
            "Connections page, then tries again."), missing=True)
    raise BrowserError(localefmt.chu(f"Chưa dùng được kết nối trình duyệt: {why}",
                                     f"The browser connection is not usable: {why}"))


def _domain(c: dict) -> str:
    return str(c.get("domain") or "").lstrip(".").lower()


def _key(c: dict) -> tuple:
    # A site may set the same cookie host-only after it was imported with a leading dot. One name on one host
    # and path is one cookie here: adding the stored one beside it would send both, the stale one included.
    return (c.get("name"), _domain(c), c.get("path") or "/")


def _clean(c: dict) -> Optional[dict]:
    """A cookie read from the browser, in the vault's shape (and through the vault's own checks)."""
    return login_vault._cookie(c.get("name"), c.get("value"), c.get("domain"), c.get("path") or "/",
                               c.get("expires", -1), c.get("httpOnly"), c.get("secure"), c.get("sameSite"))


def merge(stored: list, browser: list) -> list:
    """The copy to keep after a signed-in page load: what the browser holds, then what only the vault has."""
    out = [k for k in (_clean(c) for c in browser) if k]
    have = {_key(c) for c in out}
    out += [c for c in stored if _key(c) not in have]
    return out[:login_vault.MAX_COOKIES]


def _page(text: str) -> tuple[str, str]:
    url, title = _PAGE_URL.search(text or ""), _PAGE_TITLE.search(text or "")
    return (url.group(1) if url else ""), (title.group(1).strip() if title else "")


async def open_signed_in(url: str, login: str = "") -> dict:
    """Put the sign-in for `url` into the browser and open the page there.

    {ok, login, browser, namespace, final_url, title, page, refused} or {ok: False, error, signed_out?, login?}."""
    vault = login_vault.current()
    if vault is None:
        return {"ok": False, "error": localefmt.chu("Trang Cookies chưa sẵn sàng", "The Cookies page is not ready")}
    url = str(url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return {"ok": False, "error": localefmt.chu("url phải bắt đầu bằng http:// hoặc https://",
                                                    "url must start with http:// or https://")}
    row, stored, err = vault.pick(url, login, act=True)
    if err:
        return {"ok": False, "error": err}
    try:
        browser = await find()
    except BrowserError as e:
        return {"ok": False, "error": str(e), "login": row["name"]}
    now = time.time()
    live = [c for c in stored if not (c.get("expires", -1) > 0 and c["expires"] <= now)]
    sites = {_domain(c) for c in stored}
    async with _LOCK:
        try:
            held = [c for c in await browser.cookies() if _domain(c) in sites]
            if row.get("browser_at"):
                have = {_key(c) for c in held}
                todo = [c for c in live if _key(c) not in have]
            else:
                if held:
                    await browser.clear(held)
                todo = live
            refused = await browser.add(todo) if todo else []
            if vault.claim_browser(row["id"]):
                _hide_from_bots()
            text = await browser.navigate(url)
            if text.startswith("ERROR:"):
                note = _scrub(text[6:], stored)
                vault.mark(row["id"], "error", note, used=True)
                return {"ok": False, "login": row["name"], "error": note}
            final_url, title = _page(text)
            if login_vault.looks_signed_out(final_url, title):
                note = localefmt.chu("Trang chuyển về màn đăng nhập", "The site sent us to its sign-in page")
                vault.mark(row["id"], "signed_out", note, used=True)
                vault.release_browser(row["id"])      # the next open puts the stored copy in whole again
                return {"ok": False, "signed_out": True, "login": row["name"], "final_url": final_url,
                        "title": title, "error": note}
            vault.mark(row["id"], "ok", title[:120], used=True)
            if final_url:                              # only a page we could read counts as "signed in"
                kept = merge(stored, [c for c in await browser.cookies() if _domain(c) in sites])
                if kept != stored:
                    vault.save_browser_cookies(row["id"], kept)
        except BrowserError as e:
            return {"ok": False, "login": row["name"], "error": localefmt.chu(
                f"Trình duyệt chưa nhận được đăng nhập: {e}", f"The browser did not take the sign-in: {e}")}
        except login_vault.VaultError as e:
            return {"ok": False, "login": row["name"], "error": str(e)}
    return {"ok": True, "login": row["name"], "login_id": row["id"], "browser": browser.label,
            "namespace": browser.namespace, "final_url": final_url, "title": title,
            "page": _scrub_page(text, stored), "refused": refused}


def _scrub_page(text: str, cookies) -> str:
    """The page as Playwright reported it. A page can print its own cookies; the values this module put in are
    still cut, so they never reach the model through this tool."""
    for c in cookies or ():
        v = str(c.get("value") or "")
        if len(v) >= 8:
            text = text.replace(v, "***")
    return text[:MAX_PAGE]


def _hide_from_bots() -> None:
    try:
        import mcp_hub
        mcp_hub.drop_bot_cache()
    except Exception as e:  # noqa: BLE001 - the list still refreshes by itself within its TTL
        print(f"[browser_login] bot cache: {type(e).__name__}: {e}", file=sys.stderr)


async def forget(domains) -> str:
    """Take every cookie of these sites out of the browser. "" when none is left there, else why not."""
    sites = {str(d or "").lstrip(".").lower() for d in (domains or [])}
    if not sites:
        return ""
    try:
        browser = await find()
    except BrowserError as e:
        return "" if e.missing else str(e)     # no browser connection: no model can drive that profile either
    async with _LOCK:
        try:
            held = [c for c in await browser.cookies() if _domain(c) in sites]
            if held:
                await browser.clear(held)
        except BrowserError as e:
            return str(e)
    return ""
