"""Login vault (0.251.0, server/login_vault.py).

The owner pastes the cookies of a site they signed in to; Javis reuses that sign-in to read pages behind it
and to watch them. These tests keep what makes it safe and usable: the four paste formats, cookies only go
to the host they belong to (every redirect hop is checked again), values are encrypted and never come back
out of the API or a tool, routes need a real dashboard session, and an expired sign-in is said plainly.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path
import asyncio
import importlib.util
import json
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import login_vault as lv
import web_watch as ww

FUTURE = time.time() + 30 * 86400
PAST = time.time() - 86400

COOKIE_EDITOR = json.dumps([
    {"domain": ".shopee.vn", "hostOnly": False, "name": "SPC_EC", "value": "abc", "path": "/", "secure": True,
     "httpOnly": True, "sameSite": "no_restriction", "expirationDate": FUTURE, "session": False},
    {"domain": "banhang.shopee.vn", "hostOnly": True, "name": "seller", "value": "s1", "path": "/api",
     "secure": True, "httpOnly": False, "sameSite": "lax", "session": True},
])


# ---------------------------------------------------------------- parsing


def test_reads_cookie_editor_json():
    ck, origins = lv.parse_cookies(COOKIE_EDITOR)
    assert origins == []
    by = {c["name"]: c for c in ck}
    assert by["SPC_EC"]["domain"] == ".shopee.vn" and by["SPC_EC"]["sameSite"] == "None"
    assert by["SPC_EC"]["expires"] == pytest.approx(FUTURE)
    assert by["seller"]["domain"] == "banhang.shopee.vn" and by["seller"]["expires"] == -1
    assert lv.domains_of(ck) == ["banhang.shopee.vn", "shopee.vn"]
    assert lv.last_expiry(ck) == pytest.approx(FUTURE)


def test_reads_playwright_storage_state_with_local_storage():
    state = {"cookies": [{"name": "sid", "value": "v", "domain": "app.example.com", "path": "/",
                          "expires": FUTURE, "httpOnly": True, "secure": True, "sameSite": "Lax"}],
             "origins": [{"origin": "https://app.example.com", "localStorage": [{"name": "tok", "value": "x"}]}]}
    ck, origins = lv.parse_cookies(json.dumps(state))
    assert ck[0]["domain"] == "app.example.com" and ck[0]["httpOnly"] is True
    assert origins == [{"origin": "https://app.example.com", "localStorage": [{"name": "tok", "value": "x"}]}]


def test_reads_netscape_cookies_txt():
    txt = ("# Netscape HTTP Cookie File\n"
           f".example.com\tTRUE\t/\tTRUE\t{int(FUTURE)}\tsid\tAAA\n"
           f"#HttpOnly_shop.example.com\tFALSE\t/\tFALSE\t0\tcart\tBBB\n")
    ck, _ = lv.parse_cookies(txt)
    by = {c["name"]: c for c in ck}
    assert by["sid"]["domain"] == ".example.com" and by["sid"]["secure"] is True
    assert by["cart"]["domain"] == "shop.example.com" and by["cart"]["httpOnly"] is True
    assert by["cart"]["expires"] == -1


def test_reads_a_bare_cookie_header_only_with_a_site():
    with pytest.raises(lv.VaultError):
        lv.parse_cookies("a=1; b=2")
    ck, _ = lv.parse_cookies("Cookie: a=1; b=2=3", "https://www.shop.vn/x")
    assert {(c["name"], c["value"], c["domain"]) for c in ck} == {("a", "1", ".shop.vn"), ("b", "2=3", ".shop.vn")}


@pytest.mark.parametrize("bad", ["", "{broken", "[]", "just words"])
def test_rejects_what_it_cannot_read(bad):
    with pytest.raises(lv.VaultError):
        lv.parse_cookies(bad, "shop.vn" if bad == "just words" else "")


def test_drops_header_injection_and_bad_domains():
    items = [{"name": "ok", "value": "1", "domain": ".a.com"},
             {"name": "evil", "value": "1\r\nX-Hack: 1", "domain": ".a.com"},
             {"name": "nodomain", "value": "1", "domain": "localhost"}]
    ck, _ = lv.parse_cookies(json.dumps(items))
    assert [c["name"] for c in ck] == ["ok"]


# ---------------------------------------------------------------- which cookies go where


def test_cookie_header_follows_domain_path_secure_and_expiry():
    ck = [
        lv._cookie("dom", "1", ".shop.vn", "/", FUTURE),
        lv._cookie("host", "2", "shop.vn", "/", -1, host_only=True),
        lv._cookie("api", "3", ".shop.vn", "/api", -1),
        lv._cookie("sec", "4", ".shop.vn", "/", -1, secure=True),
        lv._cookie("old", "5", ".shop.vn", "/", PAST),
    ]
    h = lv.cookie_header(ck, "https://shop.vn/api/orders")
    assert h.split("; ")[0] == "api=3"                       # longer path first, like a browser
    assert set(h.split("; ")) == {"api=3", "dom=1", "host=2", "sec=4"}
    assert set(lv.cookie_header(ck, "https://banhang.shop.vn/").split("; ")) == {"dom=1", "sec=4"}  # host-only stays
    assert "sec=4" not in lv.cookie_header(ck, "http://shop.vn/")                                   # secure over http
    assert lv.cookie_header(ck, "https://shop.vn.evil.com/") == ""                                  # suffix trick
    assert lv.cookie_header(ck, "https://notshop.vn/") == ""
    assert "api=3" not in lv.cookie_header(ck, "https://shop.vn/apix")


def test_signed_out_guess():
    assert lv.looks_signed_out("", "", 401) and lv.looks_signed_out("", "", 403)
    assert lv.looks_signed_out("https://shopee.vn/buyer/login?next=x")
    assert lv.looks_signed_out("https://www.facebook.com/checkpoint/123")
    assert lv.looks_signed_out("https://site.vn/dang-nhap")
    assert lv.looks_signed_out("https://www.facebook.com/login.php?next=x")
    assert lv.looks_signed_out("https://accounts.google.com/v3/signin/identifier")
    assert lv.looks_signed_out("https://site.vn/", "Đăng nhập")
    assert not lv.looks_signed_out("https://site.vn/orders", "Đơn hàng của tôi")
    assert not lv.looks_signed_out("https://blog.vn/bai-viet-ve-login-page-dep", "10 mẫu trang login đẹp cho shop online năm nay")


# ---------------------------------------------------------------- vault


def _vault(tmp_path, fetch=None, session=True):
    return lv.LoginVault(lv.LoginVaultDeps(state_dir=lambda: tmp_path, has_session=lambda r: session, fetch=fetch))


def test_values_are_encrypted_and_never_in_the_view(tmp_path):
    v = _vault(tmp_path)
    lg = v.create("Shopee", COOKIE_EDITOR)
    row = v.store.get(lg["id"])
    assert row["cookies_enc"].startswith("enc:") and "abc" not in row["cookies_enc"]
    assert "abc" not in json.dumps(lg) and "cookies" not in json.dumps(lg)
    assert lg["domains"] == ["banhang.shopee.vn", "shopee.vn"] and lg["count"] == 2 and lg["allow_ai"]
    assert lg["test_url"] == "https://banhang.shopee.vn/"
    assert {c["name"] for c in v.cookies(lg["id"])} == {"SPC_EC", "seller"}
    with pytest.raises(lv.VaultError):
        v.create("shopee", COOKIE_EDITOR)                 # same name, any case
    v.store.close()


def test_refuses_to_store_without_encryption(tmp_path, monkeypatch):
    import secrets_store

    def nope(_):
        raise RuntimeError("encryption_unavailable")
    monkeypatch.setattr(secrets_store, "encrypt_required", nope)
    v = _vault(tmp_path)
    with pytest.raises(lv.VaultError):
        v.create("Shopee", COOKIE_EDITOR)
    assert v.store.list() == []
    v.store.close()


def test_pick_respects_allow_and_domain(tmp_path):
    v = _vault(tmp_path)
    lg = v.create("Shopee", COOKIE_EDITOR)
    row, ck, err = v.pick("https://shopee.vn/x")
    assert row["id"] == lg["id"] and ck and not err
    assert v.pick("https://lazada.vn/")[2]                                   # nothing for that host
    assert v.pick("https://lazada.vn/", "Shopee")[2]                         # named, but does not cover it
    v.control(lg["id"], "deny")
    assert v.pick("https://shopee.vn/x")[2]
    assert v.pick("https://shopee.vn/x", lg["id"], only_allowed=False)[0]
    v.store.close()


def test_open_marks_ok_signed_out_and_error(tmp_path):
    calls = []

    async def fetch(url, cookies):
        calls.append((url, cookies))
        if url.endswith("/out"):
            return "https://shopee.vn/buyer/login?next=out", "Shopee", "Đăng nhập"
        if url.endswith("/403"):
            raise ww.FetchError("err", status=403)
        if url.endswith("/down"):
            raise ww.FetchError("Không tải được trang: ConnectError")
        return url, "Kênh người bán", "Đơn hàng: 12"

    v = _vault(tmp_path, fetch)
    lg = v.create("Shopee", COOKIE_EDITOR)
    r = asyncio.run(v.open("https://shopee.vn/orders"))
    assert r["ok"] and r["text"] == "Đơn hàng: 12" and r["login"] == "Shopee"
    assert calls[0][1] and v.store.get(lg["id"])["uses"] == 1 and v.store.get(lg["id"])["status"] == "ok"
    r = asyncio.run(v.open("https://shopee.vn/out"))
    assert r["signed_out"] and v.store.get(lg["id"])["status"] == "signed_out"
    assert asyncio.run(v.open("https://shopee.vn/403"))["signed_out"]
    r = asyncio.run(v.open("https://shopee.vn/down"))
    assert not r["ok"] and not r.get("signed_out") and v.store.get(lg["id"])["status"] == "error"
    checked = asyncio.run(v.check(lg["id"]))
    assert checked["status"] == "ok" and v.store.get(lg["id"])["uses"] == 4    # a check is not a use
    v.store.close()


def test_fetch_sends_cookies_only_to_their_host_on_every_hop(monkeypatch):
    """A page that redirects to another site must not carry the sign-in along."""
    seen, ua = [], []

    def handler(req):
        seen.append((str(req.url), req.headers.get("cookie", "")))
        ua.append(req.headers.get("user-agent", ""))
        if req.url.host == "shop.vn":
            return httpx.Response(302, headers={"location": "https://tracker.example/next"})
        return httpx.Response(200, text="<title>T</title><p>ok</p>")

    real = httpx.AsyncClient

    class Client(real):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            super().__init__(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", Client)
    monkeypatch.setattr(ww, "check_url", lambda url: "x")
    ck = [lv._cookie("sid", "SECRET", ".shop.vn", "/", -1)]
    final, title, text = asyncio.run(ww.fetch("https://shop.vn/a", ck))
    assert final == "https://tracker.example/next" and "ok" in text
    assert seen[0] == ("https://shop.vn/a", "sid=SECRET")
    assert seen[1] == ("https://tracker.example/next", "")
    assert "Chrome/" in ua[0] and "JavisWatch" not in ua[0]           # a signed-in fetch looks like a browser
    seen.clear(); ua.clear()
    asyncio.run(ww.fetch("https://shop.vn/a"))
    assert "JavisWatch" in ua[0] and seen[0][1] == ""                 # an anonymous watch still says who it is


# ---------------------------------------------------------------- routes


def _client(tmp_path, session=True):
    v = _vault(tmp_path, session=session)
    app = FastAPI()
    app.include_router(v.router)
    return v, TestClient(app)


def test_routes_need_a_dashboard_session(tmp_path):
    v, c = _client(tmp_path, session=False)
    assert c.get("/logins").status_code == 401
    assert c.post("/logins", json={"name": "x", "text": COOKIE_EDITOR}).status_code == 401
    assert c.post("/logins/action", json={"id": "x", "action": "delete"}).status_code == 401
    assert v.store.list() == []
    v.store.close()


def test_routes_add_list_toggle_rename_replace_delete(tmp_path):
    v, c = _client(tmp_path)
    r = c.post("/logins", json={"name": "Shopee", "text": COOKIE_EDITOR}).json()
    assert r["ok"] and "abc" not in json.dumps(r)
    lid = r["login"]["id"]
    d = c.get("/logins").json()
    assert d["ok"] and d["encryption"] is True and [x["name"] for x in d["logins"]] == ["Shopee"]
    assert "abc" not in json.dumps(d)
    assert c.post("/logins/action", json={"id": lid, "action": "deny"}).json()["login"]["allow_ai"] is False
    assert c.post("/logins/action", json={"id": lid, "action": "rename", "name": "Shop"}).json()["login"]["name"] == "Shop"
    new = c.post("/logins/action", json={"id": lid, "action": "replace", "text": "x=1", "site": "shopee.vn"}).json()
    assert new["login"]["count"] == 1 and new["login"]["status"] == "unknown"
    assert c.post("/logins/action", json={"id": lid, "action": "nope"}).status_code == 400
    assert c.post("/logins", json={"name": "Bad", "text": "{"}).status_code == 400
    assert c.post("/logins/action", json={"id": lid, "action": "delete"}).json()["ok"]
    assert c.get("/logins").json()["logins"] == []
    v.store.close()


# ---------------------------------------------------------------- page watch with a sign-in


def test_watch_uses_the_sign_in_and_pauses_once_when_it_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(ww, "check_url", lambda url: "shopee.vn")
    state = {"out": False}

    async def fetch(url, cookies):
        assert cookies, "the watch must open the page with the stored cookies"
        if state["out"]:
            return "https://shopee.vn/buyer/login", "Đăng nhập", ""
        return url, "Đơn hàng", "Đơn chờ: 3"

    v = _vault(tmp_path, fetch)
    monkeypatch.setattr(lv, "_CURRENT", v)
    lg = v.create("Shopee", COOKIE_EDITOR)
    sent = []

    async def send(chat, text, **kw):
        sent.append(text)
        return True, ""

    f = ww.WebWatchFeature(ww.WebWatchDeps(state_dir=lambda: tmp_path, brain_root=lambda b: str(b), send=send))
    assert f.create("/b", "https://lazada.vn/x", login_id="Shopee")[1]          # sign-in does not cover that host
    w, err = f.create("/b", "https://shopee.vn/orders", "contains", "Đơn chờ", login_id="Shopee")
    assert not err and w["login_id"] == lg["id"]
    asyncio.run(f.check(w["id"]))
    assert sent and "Đơn chờ" in sent[0]
    state["out"] = True
    f.store.update(w["id"], next_at=0)
    asyncio.run(f.check(w["id"]))
    after = f.store.get(w["id"])
    assert after["status"] == "paused"
    assert "Cookies" in sent[-1]
    assert len(sent) == 2
    f.store.close()
    v.store.close()


def test_old_watch_database_gets_the_login_column(tmp_path):
    import sqlite3
    db = sqlite3.connect(str(tmp_path / "web_watch.sqlite3"))
    db.execute("CREATE TABLE watches (id TEXT PRIMARY KEY, brain TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,"
               " cond TEXT NOT NULL, value TEXT NOT NULL DEFAULT '', interval_min INTEGER NOT NULL,"
               " owner_chat TEXT NOT NULL DEFAULT '', summarize INTEGER NOT NULL DEFAULT 0,"
               " status TEXT NOT NULL DEFAULT 'active', next_at REAL NOT NULL DEFAULT 0,"
               " last_at REAL NOT NULL DEFAULT 0, last_hash TEXT NOT NULL DEFAULT '',"
               " timeless_hash TEXT NOT NULL DEFAULT '', lines_json TEXT NOT NULL DEFAULT '[]',"
               " matched INTEGER NOT NULL DEFAULT 0, alert_seq INTEGER NOT NULL DEFAULT 0,"
               " failures INTEGER NOT NULL DEFAULT 0, fail_streak INTEGER NOT NULL DEFAULT 0,"
               " last_error TEXT NOT NULL DEFAULT '', checks INTEGER NOT NULL DEFAULT 0,"
               " created_at REAL NOT NULL, last_alert TEXT NOT NULL DEFAULT '', last_alert_at REAL NOT NULL DEFAULT 0)")
    db.commit()
    db.close()
    s = ww.Store(tmp_path / "web_watch.sqlite3")
    s.add({"id": "w1", "brain": "/b", "title": "t", "url": "https://a.vn", "cond": "change", "interval_min": 60,
           "created_at": 1.0})
    assert s.get("w1")["login_id"] == ""
    s.close()


# ---------------------------------------------------------------- tool


def _plugin():
    p = ROOT / "system" / "plugins" / "javis-login" / "plugin.py"
    spec = importlib.util.spec_from_file_location("javis_login_plugin", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_tool_returns_page_text_never_cookies(tmp_path, monkeypatch):
    async def fetch(url, cookies):
        if "out" in url:
            return "https://shopee.vn/login", "Login", ""
        return url, "Kênh người bán", "Doanh thu hôm nay 1.200.000đ"

    v = _vault(tmp_path, fetch)
    monkeypatch.setattr(lv, "_CURRENT", v)
    m = _plugin()
    assert "trống" in asyncio.run(m._run({"op": "list"}, None))
    v.create("Shopee", COOKIE_EDITOR)
    lst = asyncio.run(m._run({"op": "list"}, None))
    assert "Shopee" in lst and "shopee.vn" in lst and "abc" not in lst
    out = asyncio.run(m._run({"op": "fetch", "url": "https://shopee.vn/x"}, None))
    assert "1.200.000đ" in out and "DỮ LIỆU" in out and "abc" not in out and "SPC_EC" not in out
    assert asyncio.run(m._run({"op": "fetch", "url": "https://shopee.vn/out"}, None)).startswith("ĐĂNG NHẬP HẾT HẠN")
    assert asyncio.run(m._run({"op": "fetch", "url": "https://lazada.vn/"}, None)).startswith("ERROR")
    assert asyncio.run(m._run({"op": "fetch"}, None)).startswith("ERROR")
    v.store.close()


def test_bots_never_get_the_tool():
    import mcp_hub
    assert "javis_login" in mcp_hub.OWNER_ONLY_TOOLS


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
