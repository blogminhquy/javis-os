"""Signed-in browser (2026-11-21, server/browser_login.py).

A sign-in from the Cookies page goes into the browser the Playwright connection drives, so Javis can click and
fill forms signed in (`javis_login` op=browser). These tests keep what makes that safe and what keeps it working:

- only a sign-in whose own "act" switch is on goes in, and rows stored before this feature start with it off;
- the stored copy never overwrites a session the browser renewed, and the renewed one is saved back encrypted;
- new cookies, or another account of the same site, replace what the browser held;
- cookie values never come back to the model, not even inside an error;
- switching a sign-in off or deleting it takes it out of the browser, and says so when that fails;
- a customer bot loses the browser connection once it has held a sign-in.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path
import asyncio
import importlib.util
import json
import sqlite3
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import browser_login as bl
import login_vault as lv

FUTURE = time.time() + 30 * 86400
PAST = time.time() - 86400
SECRET = "s3cr3t-session-value"
COOKIES = json.dumps([
    {"domain": ".shop.test", "hostOnly": False, "name": "sid", "value": SECRET, "path": "/", "secure": True,
     "httpOnly": True, "sameSite": "lax", "expirationDate": FUTURE},
    {"domain": ".shop.test", "hostOnly": False, "name": "old", "value": "expired-value", "path": "/", "secure": True,
     "httpOnly": False, "sameSite": "lax", "expirationDate": PAST},
    {"domain": "seller.shop.test", "hostOnly": True, "name": "csrf", "value": "csrf-token-1", "path": "/",
     "secure": True, "httpOnly": False, "sameSite": "lax", "session": True},
])


class FakeBrowser:
    """A cookie jar that behaves like the Playwright connection as far as browser_login can tell."""
    label, namespace = "Playwright", "playwright"

    def __init__(self, jar=None, landing=None, fail=""):
        self.jar = list(jar or [])
        self.calls = []
        self.landing = landing          # (final_url, title) to answer, default: the url itself
        self.fail = fail                # which call raises

    def _maybe_fail(self, what):
        if self.fail == what:
            raise bl.BrowserError("boom")

    async def cookies(self):
        self._maybe_fail("cookies")
        return [dict(c) for c in self.jar]

    async def add(self, cookies):
        self._maybe_fail("add")
        self.calls.append(("add", sorted(c["name"] for c in cookies)))
        for c in cookies:
            self.jar = [x for x in self.jar if bl._key(x) != bl._key(c)] + [dict(c)]
        return []

    async def clear(self, cookies):
        self._maybe_fail("clear")
        self.calls.append(("clear", sorted(c["name"] for c in cookies)))
        gone = {bl._key(c) for c in cookies}
        self.jar = [x for x in self.jar if bl._key(x) not in gone]

    async def navigate(self, url):
        self.calls.append(("navigate", url))
        final, title = self.landing or (url, "Orders")
        return f"### Ran Playwright code\n```js\nawait page.goto('{url}');\n```\n### Page\n- Page URL: {final}\n- Page Title: {title}\n"

    def value(self, name):
        return next((c["value"] for c in self.jar if c["name"] == name), None)


@pytest.fixture
def vault(tmp_path, monkeypatch):
    v = lv.LoginVault(lv.LoginVaultDeps(state_dir=lambda: tmp_path, has_session=lambda r: True,
                                        forget_browser=bl.forget))
    monkeypatch.setattr(lv, "_CURRENT", v)
    monkeypatch.setattr(bl, "_hide_from_bots", lambda: None)
    yield v
    v.store.close()


def _use(monkeypatch, browser):
    async def find():
        if browser is None:
            raise bl.BrowserError("There is no browser connection (Playwright).", missing=True)
        return browser
    monkeypatch.setattr(bl, "find", find)
    return browser


def _open(url="https://seller.shop.test/orders", login=""):
    return asyncio.run(bl.open_signed_in(url, login))


# ---------------------------------------------------------------- putting a sign-in in


def test_first_open_puts_the_whole_sign_in_in_and_returns_no_cookie(vault, monkeypatch):
    leftover = {"name": "sid", "value": "anonymous", "domain": ".shop.test", "path": "/", "expires": -1,
                "httpOnly": True, "secure": True, "sameSite": "Lax"}
    other = {"name": "x", "value": "keep", "domain": "elsewhere.test", "path": "/", "expires": -1,
             "httpOnly": False, "secure": True, "sameSite": "Lax"}
    b = _use(monkeypatch, FakeBrowser([leftover, other]))
    lg = vault.create("Shop", COOKIES)
    r = _open()
    assert r["ok"] and r["login"] == "Shop" and r["final_url"] == "https://seller.shop.test/orders"
    assert b.calls[0] == ("clear", ["sid"])                       # what the browser held for this site goes first
    assert b.calls[1] == ("add", ["csrf", "sid"])                 # the expired cookie is not put in
    assert b.value("sid") == SECRET and b.value("x") == "keep"    # another site's cookies are not touched
    assert SECRET not in json.dumps(r)
    view = vault.view(vault.store.get(lg["id"]))
    assert view["in_browser"] and view["status"] == "ok" and view["uses"] == 1
    assert vault.browser_in_use()


def test_a_session_the_browser_renewed_is_kept_and_saved_back_encrypted(vault, monkeypatch):
    b = _use(monkeypatch, FakeBrowser())
    lg = vault.create("Shop", COOKIES)
    assert _open()["ok"]
    for c in b.jar:                                               # the site renews the session while it is used
        if c["name"] == "sid":
            c["value"] = "renewed-session-value"
    b.jar = [c for c in b.jar if c["name"] != "csrf"]             # and the browser lost one cookie
    b.jar.append({"name": "seen", "value": "new-from-site", "domain": ".shop.test", "path": "/", "expires": FUTURE,
                  "httpOnly": False, "secure": True, "sameSite": "Lax"})
    b.calls.clear()
    assert _open()["ok"]
    assert b.calls[0] == ("add", ["csrf"])                        # only what is missing; nothing was cleared
    assert b.value("sid") == "renewed-session-value"
    stored = {c["name"]: c["value"] for c in vault.cookies(lg["id"])}
    assert stored["sid"] == "renewed-session-value" and stored["seen"] == "new-from-site"
    assert stored["old"] == "expired-value"                       # what only the vault has is kept
    row = vault.store.get(lg["id"])
    assert row["cookies_enc"].startswith("enc:") and "renewed-session-value" not in row["cookies_enc"]


def test_new_cookies_from_the_owner_replace_the_browsers_copy(vault, monkeypatch):
    b = _use(monkeypatch, FakeBrowser())
    lg = vault.create("Shop", COOKIES)
    assert _open()["ok"]
    vault.replace(lg["id"], json.dumps([{"domain": ".shop.test", "name": "sid", "value": "pasted-again",
                                         "path": "/", "secure": True, "expirationDate": FUTURE}]))
    assert not vault.view(vault.store.get(lg["id"]))["in_browser"]
    b.calls.clear()
    assert _open("https://shop.test/")["ok"]
    assert b.calls[0][0] == "clear" and b.value("sid") == "pasted-again"


def test_another_account_of_the_same_site_takes_the_browser_over(vault, monkeypatch):
    b = _use(monkeypatch, FakeBrowser())
    a = vault.create("Shop A", COOKIES)
    two = vault.create("Shop B", json.dumps([{"domain": ".shop.test", "name": "sid", "value": "account-b-value",
                                              "path": "/", "secure": True, "expirationDate": FUTURE}]))
    assert _open(login="Shop A")["ok"] and b.value("sid") == SECRET
    assert _open("https://shop.test/", "Shop B")["ok"] and b.value("sid") == "account-b-value"
    assert not vault.view(vault.store.get(a["id"]))["in_browser"]
    assert vault.view(vault.store.get(two["id"]))["in_browser"]
    assert _open(login="Shop A")["ok"] and b.value("sid") == SECRET      # and back: A is put in whole again


def test_signed_out_is_said_and_the_next_open_starts_clean(vault, monkeypatch):
    b = _use(monkeypatch, FakeBrowser(landing=("https://shop.test/login?next=/orders", "Log in")))
    lg = vault.create("Shop", COOKIES)
    r = _open()
    assert not r["ok"] and r["signed_out"] and SECRET not in json.dumps(r)
    view = vault.view(vault.store.get(lg["id"]))
    assert view["status"] == "signed_out" and not view["in_browser"]
    assert {c["name"]: c["value"] for c in vault.cookies(lg["id"])}["sid"] == SECRET   # nothing was saved back
    assert b.calls


# ---------------------------------------------------------------- who may


def test_only_a_sign_in_allowed_to_act_goes_in(vault, monkeypatch):
    b = _use(monkeypatch, FakeBrowser())
    lg = vault.create("Shop", COOKIES)
    assert lg["allow_act"] is True                                # a new one: the add form stated the risk
    vault.control(lg["id"], "deny_act")
    for login in ("", "Shop"):
        r = _open(login=login)
        assert not r["ok"] and ("read-only" in r["error"] or "chỉ đọc" in r["error"])
    assert b.calls == [] and b.jar == []
    assert vault.pick("https://shop.test/")[0]                    # reading (op=fetch) still works
    vault.control(lg["id"], "allow_act")
    vault.control(lg["id"], "deny")
    assert not _open()["ok"] and b.calls == []                    # switched off altogether
    assert not _open("https://other.test/")["ok"]
    assert not _open("ftp://shop.test/")["ok"]


def test_sign_ins_stored_before_this_feature_stay_read_only(tmp_path):
    db = sqlite3.connect(str(tmp_path / "login_vault.sqlite3"))
    db.execute("""CREATE TABLE logins (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, domains TEXT NOT NULL DEFAULT '[]',
        cookies_enc TEXT NOT NULL, origins_enc TEXT NOT NULL DEFAULT '',
        count INTEGER NOT NULL DEFAULT 0, allow_ai INTEGER NOT NULL DEFAULT 1,
        test_url TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'unknown',
        status_note TEXT NOT NULL DEFAULT '', checked_at REAL NOT NULL DEFAULT 0,
        used_at REAL NOT NULL DEFAULT 0, uses INTEGER NOT NULL DEFAULT 0,
        expires_at REAL NOT NULL DEFAULT 0, created_at REAL NOT NULL, updated_at REAL NOT NULL)""")
    db.execute("INSERT INTO logins(id, name, domains, cookies_enc, created_at, updated_at) VALUES "
               "('lg_old', 'Old', '[\"shop.test\"]', '', 1, 1)")
    db.commit()
    db.close()
    v = lv.LoginVault(lv.LoginVaultDeps(state_dir=lambda: tmp_path, has_session=lambda r: True))
    view = v.view(v.store.get("lg_old"))
    assert view["allow_ai"] is True and view["allow_act"] is False and view["in_browser"] is False
    assert not v.browser_in_use()
    v.store.close()


def test_no_browser_connection_is_said_plainly(vault, monkeypatch):
    _use(monkeypatch, None)
    lg = vault.create("Shop", COOKIES)
    r = _open()
    assert not r["ok"] and "Playwright" in r["error"]
    assert not vault.view(vault.store.get(lg["id"]))["in_browser"]


def test_a_browser_that_fails_never_leaks_a_cookie(vault, monkeypatch):
    _use(monkeypatch, FakeBrowser(fail="add"))
    vault.create("Shop", COOKIES)
    r = _open()
    assert not r["ok"] and SECRET not in json.dumps(r)


# ---------------------------------------------------------------- taking it out again


def test_switching_off_or_deleting_takes_it_out_of_the_browser(vault, monkeypatch):
    b = _use(monkeypatch, FakeBrowser([{"name": "x", "value": "keep", "domain": "elsewhere.test", "path": "/"}]))
    app = FastAPI()
    app.include_router(vault.router)
    c = TestClient(app)
    lg = vault.create("Shop", COOKIES)
    assert _open()["ok"] and b.value("sid") == SECRET
    r = c.post("/logins/action", json={"id": lg["id"], "action": "deny_act"}).json()
    assert r["ok"] and "warning" not in r and r["login"]["allow_act"] is False and r["login"]["in_browser"] is False
    assert b.value("sid") is None and b.value("csrf") is None and b.value("x") == "keep"
    c.post("/logins/action", json={"id": lg["id"], "action": "allow_act"})
    assert _open()["ok"] and b.value("sid") == SECRET
    assert c.post("/logins/action", json={"id": lg["id"], "action": "delete"}).json()["ok"]
    assert b.value("sid") is None and vault.store.list() == []
    assert vault.browser_in_use()                                 # the profile outlives the row: bots stay away


def test_a_browser_that_cannot_be_cleared_is_reported_to_the_owner(vault, monkeypatch):
    b = _use(monkeypatch, FakeBrowser())
    app = FastAPI()
    app.include_router(vault.router)
    c = TestClient(app)
    lg = vault.create("Shop", COOKIES)
    assert _open()["ok"]
    b.fail = "clear"
    r = c.post("/logins/action", json={"id": lg["id"], "action": "deny"}).json()
    assert r["ok"] and r["login"]["allow_ai"] is False            # the switch itself is saved
    assert "Shop" in r["warning"] and SECRET not in json.dumps(r)
    assert b.value("sid") == SECRET and r["login"]["in_browser"] is True


def test_forget_without_a_browser_connection_is_nothing_to_do(monkeypatch):
    _use(monkeypatch, None)
    assert asyncio.run(bl.forget(["shop.test"])) == ""
    assert asyncio.run(bl.forget([])) == ""


# ---------------------------------------------------------------- the real connection, faked at the pool


class FakePool:
    def __init__(self, answers):
        self.answers, self.sent = answers, []

    async def list_tools(self, spec):
        return [{"name": n} for n in self.answers["tools"]]

    async def call_tool(self, spec, tool, args):
        self.sent.append((tool, args))
        return self.answers[tool]


CONN = {"id": "c1", "label": "Playwright", "namespace": "playwright", "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"], "perm": "full", "deny_tools": [], "connector": None}


def _pool(monkeypatch, answers, conns=(CONN,)):
    import mcp_client
    import mcp_store
    pool = FakePool(answers)
    monkeypatch.setattr(mcp_client, "pool", pool)
    monkeypatch.setattr(mcp_store, "resolved", lambda enabled_only=True: [dict(c) for c in conns])
    return pool


def test_finds_the_playwright_connection_and_reads_its_answers(monkeypatch):
    jar = [{"name": "sid", "value": "v", "domain": ".shop.test", "path": "/"}]
    pool = _pool(monkeypatch, {
        "tools": ["browser_navigate", "browser_run_code_unsafe", "browser_click"],
        "browser_run_code_unsafe": "### Result\n" + json.dumps(jar) + "\n### Ran Playwright code\n```js\nawait x;\n```",
        "browser_navigate": "### Page\n- Page URL: https://shop.test/\n- Page Title: Home\n"})
    b = asyncio.run(bl.find())
    assert b.code_tool == "browser_run_code_unsafe" and b.namespace == "playwright"
    assert asyncio.run(b.cookies()) == jar
    assert pool.sent[-1][0] == "browser_run_code_unsafe" and "cookies()" in pool.sent[-1][1]["code"]
    assert bl._page(asyncio.run(b.navigate("https://shop.test/"))) == ("https://shop.test/", "Home")
    assert bl.is_browser_spec(CONN) and not bl.is_browser_spec({"command": "npx", "args": ["some-other-mcp"]})


def test_an_error_from_the_browser_carries_no_cookie_value(monkeypatch):
    cookies = [{"name": "sid", "value": SECRET, "domain": ".shop.test", "path": "/"}]
    _pool(monkeypatch, {
        "tools": ["browser_navigate", "browser_run_code"],        # the tool's older name
        "browser_run_code": f"ERROR: Protocol error near {SECRET}\n### Ran Playwright code\nawait add({SECRET})"})
    b = asyncio.run(bl.find())
    assert b.code_tool == "browser_run_code"
    with pytest.raises(bl.BrowserError) as e:
        asyncio.run(b.add(cookies))
    assert SECRET not in str(e.value) and "Ran Playwright code" not in str(e.value)


def test_a_connection_that_cannot_take_cookies_or_is_restricted_is_refused(monkeypatch):
    _pool(monkeypatch, {"tools": ["browser_navigate"]})
    with pytest.raises(bl.BrowserError) as e:
        asyncio.run(bl.find())
    assert not e.value.missing
    _pool(monkeypatch, {"tools": ["browser_navigate", "browser_run_code_unsafe"]},
          conns=[dict(CONN, deny_tools=["browser_navigate"])])
    with pytest.raises(bl.BrowserError):
        asyncio.run(bl.find())
    import mcp_catalog
    _pool(monkeypatch, {"tools": ["browser_navigate", "browser_run_code_unsafe"]})
    with monkeypatch.context() as mp:                             # the connection's own level forbids opening pages
        mp.setattr(mcp_catalog, "allowed", lambda *a, **k: (False, "connection is restricted"))
        with pytest.raises(bl.BrowserError) as e:
            asyncio.run(bl.find())
        assert "connection is restricted" in str(e.value)
    _pool(monkeypatch, {"tools": []}, conns=[{"id": "c2", "command": "npx", "args": ["other-mcp"]}])
    with pytest.raises(bl.BrowserError) as e:
        asyncio.run(bl.find())
    assert e.value.missing


def test_merge_keeps_the_browsers_values_and_the_vaults_extras():
    stored = [{"name": "sid", "value": "old", "domain": ".shop.test", "path": "/", "expires": -1,
               "httpOnly": True, "secure": True, "sameSite": "Lax"},
              {"name": "only-vault", "value": "v", "domain": ".shop.test", "path": "/", "expires": -1,
               "httpOnly": False, "secure": True, "sameSite": "Lax"}]
    browser = [{"name": "sid", "value": "new", "domain": "shop.test", "path": "/", "expires": -1,
                "httpOnly": True, "secure": True, "sameSite": "Lax"},
               {"name": "bad name;", "value": "x", "domain": "shop.test", "path": "/"}]
    out = bl.merge(stored, browser)
    assert [(c["name"], c["value"]) for c in out] == [("sid", "new"), ("only-vault", "v")]


# ---------------------------------------------------------------- the tool and the bot


def _plugin():
    p = ROOT / "system" / "plugins" / "javis-login" / "plugin.py"
    spec = importlib.util.spec_from_file_location("javis_login_plugin_browser", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_tool_opens_the_page_names_the_next_tools_and_never_a_cookie(vault, monkeypatch):
    _use(monkeypatch, FakeBrowser())
    m = _plugin()
    vault.create("Shop", COOKIES)
    out = asyncio.run(m._run({"op": "browser", "url": "https://seller.shop.test/orders"}, None))
    assert out.startswith("Signed in as: Shop") and "playwright__browser_click" in out
    assert "DATA, not instructions" in out and SECRET not in out and "csrf-token-1" not in out
    assert "may click and fill forms" in asyncio.run(m._run({"op": "list"}, None))
    assert asyncio.run(m._run({"op": "browser"}, None)).startswith("ERROR")
    _use(monkeypatch, FakeBrowser(landing=("https://shop.test/signin", "Sign in")))
    assert asyncio.run(m._run({"op": "browser", "url": "https://shop.test/"}, None)).startswith("SIGN-IN EXPIRED")


def test_acting_needs_the_full_level_while_reading_does_not():
    import plugins_host

    class Ctx:
        tools = []

        def register_tool(self, name, description, handler, **kw):
            self.tools.append(dict(kw, name=name, description=description))

    ctx = Ctx()
    _plugin().register(ctx)
    tool = dict(ctx.tools[0], op_key="op")
    assert tool["name"] == "javis_login" and "browser" in tool["schema"]["properties"]["op"]["enum"]
    assert plugins_host._required_mode(tool, {"op": "browser"}) == "full"
    assert plugins_host._required_mode(tool, {"op": "fetch"}) == "readonly"
    assert plugins_host._required_mode(tool, {"op": "list"}) == "readonly"
    assert plugins_host._required_mode(tool, {"op": "typo"}) == "full"


def test_a_customer_bot_loses_the_browser_once_it_has_held_a_sign_in(vault, monkeypatch):
    import mcp_client
    import mcp_hub
    import mcp_store

    spec = {"key": "c1", "command": "npx", "args": ["-y", "@playwright/mcp@latest"]}
    other = {"key": "c2", "command": "npx", "args": ["-y", "some-pos-mcp"]}

    async def discover(conns, bo_qua=None):
        tools = [{"fn": "playwright__browser_click", "server": "playwright", "name": "browser_click",
                  "description": "click", "schema": {"type": "object", "properties": {}}},
                 {"fn": "pos__list_orders", "server": "pos", "name": "list_orders", "description": "orders",
                  "schema": {"type": "object", "properties": {}}}]
        route = {"playwright__browser_click": {"spec": spec, "tool": "browser_click",
                                               "conn": {"id": "c1", "namespace": "playwright", "perm": "full",
                                                        "label": "Playwright", "connector_id": "custom"}},
                 "pos__list_orders": {"spec": other, "tool": "list_orders",
                                      "conn": {"id": "c2", "namespace": "pos", "perm": "full", "label": "POS",
                                               "connector_id": "custom"}}}
        return tools, route

    monkeypatch.setattr(mcp_client, "discover_resolved", discover)
    monkeypatch.setattr(mcp_store, "resolved", lambda enabled_only=True: [])

    def names(for_bot):
        tools, route = asyncio.run(mcp_hub.discover_all("full", include_plugins=False, force_refresh=True,
                                                         for_bot=for_bot, tool_allowlist=(
                                                             "playwright__browser_click", "pos__list_orders")))
        return {t["fn"] for t in tools}

    assert names(True) == {"playwright__browser_click", "pos__list_orders"}      # nothing signed in yet
    _use(monkeypatch, FakeBrowser())
    vault.create("Shop", COOKIES)
    assert _open()["ok"]
    assert names(True) == {"pos__list_orders"}                                   # the bot keeps the rest
    assert names(False) == {"playwright__browser_click", "pos__list_orders"}     # the owner keeps the browser


def test_bot_tool_lists_are_dropped_without_closing_any_session(monkeypatch):
    import mcp_hub
    bot_key = ("full", "", True, False, False, "vi", False, "", "", True, (), "")
    owner_key = ("full", "", True, False, False, "vi", False, "", "", False, (), "")
    monkeypatch.setattr(mcp_hub, "_cache", {bot_key: {"ts": 0}, owner_key: {"ts": 0}})
    assert mcp_hub.drop_bot_cache() == 1
    assert list(mcp_hub._cache) == [owner_key]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
