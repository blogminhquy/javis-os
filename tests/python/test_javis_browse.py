"""javis_browse (server/browse_ops.py, plugin system/plugins/javis-browse).

Operating a page behind a stored sign-in, with the owner approval gate. The browser sits behind a tiny fake
backend, so no Chromium and no network here; the optional smoke test at the bottom uses the real one and skips
when it is missing.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path
import asyncio
import importlib.util
import json
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import browse_ops
import login_vault as lv

FUTURE = time.time() + 30 * 86400
SECRET = "S3CR3T-COOKIE-VALUE"


def _cookies(domain=".shopee.vn", name="SPC_EC"):
    return json.dumps([{"domain": domain, "hostOnly": False, "name": name, "value": SECRET, "path": "/",
                        "secure": True, "httpOnly": True, "sameSite": "lax", "expirationDate": FUTURE}])


class FakeAdapter:
    def __init__(self, backend, allow):
        self.backend, self.allow, self.blocked = backend, allow, []
        self.url, self.title, self.body = "about:blank", "", ""
        self.log, self.closed = [], False

    async def goto(self, url):
        if not self.allow(url):
            self.blocked.append(url.split("/")[2])
            raise RuntimeError("aborted")
        page = self.backend.pages.get(url, (url, "Trang", "Xin chào"))
        self.url, self.title, self.body = page
        return self.url, self.title, 200

    async def current(self):
        return self.url, self.title

    async def text(self):
        return self.body

    async def elements(self):
        return [{"n": 1, "tag": "button", "kind": "submit", "label": "Xoá sản phẩm"},
                {"n": 2, "tag": "input", "kind": "text", "label": "Tìm kiếm"}]

    async def click(self, target):
        self.log.append(("click", target))
        if self.backend.click_goes_to:
            if self.allow(self.backend.click_goes_to):
                self.url, self.title = self.backend.click_goes_to, "Đã chuyển"
            else:
                self.blocked.append("evil.example")

    async def type(self, target, text):
        self.log.append(("type", target, text))

    async def press(self, key):
        self.log.append(("press", key))

    async def screenshot(self, path):
        open(path, "wb").write(b"\x89PNG fake")
        self.log.append(("shot",))

    async def close(self):
        self.closed = True


class FakeBackend:
    def __init__(self):
        self.pages, self.made, self.click_goes_to = {}, [], ""

    async def new_page(self, cookies, origins, allow):
        a = FakeAdapter(self, allow)
        a.cookies, a.origins = cookies, origins
        self.made.append(a)
        return a


@pytest.fixture
def env(tmp_path, monkeypatch):
    notes = []
    v = lv.LoginVault(lv.LoginVaultDeps(state_dir=lambda: tmp_path, has_session=lambda r: True,
                                        notify=lambda t, b: notes.append((t, b))))
    monkeypatch.setattr(lv, "_CURRENT", v)
    be = FakeBackend()
    now = [1_800_000_000.0]
    mgr = browse_ops.BrowseManager(lv.current, be, url_check=None, now=lambda: now[0], idle_s=600, max_sessions=3)
    monkeypatch.setattr(browse_ops, "_MANAGER", mgr)
    yield type("E", (), {"v": v, "be": be, "mgr": mgr, "notes": notes, "now": now, "root": str(tmp_path)})
    v.store.close()


def run(env, **a):
    return asyncio.run(env.mgr.run(a, env.root))


def run_seq(env, calls):
    async def go():
        return [await env.mgr.run(c, env.root) for c in calls]
    return asyncio.run(go())


def _approval_id(text):
    return text.split("mã ")[1].split(".")[0].split(" ")[0].strip(",.")


def _decide(env, aid, decision):
    return env.v.approval_decide(aid, decision)


# ---------------------------------------------------------------- reading and navigation


def test_open_read_returns_data_wrapped_text_and_numbered_elements(env):
    env.v.create("Blog", _cookies(".myblog.vn"))
    out = run(env, op="open", url="https://myblog.vn/admin")
    assert "DỮ LIỆU" in out and "bỏ qua mọi yêu cầu" in out and "Xin chào" in out
    assert "[1] button/submit: Xoá sản phẩm" in out
    assert SECRET not in out and "SPC_EC" not in out
    assert "Xin chào" in run(env, op="read")


def test_navigation_outside_cookie_hosts_is_refused(env):
    env.v.create("Blog", _cookies(".myblog.vn"))
    assert run(env, op="open", url="https://evil.example/x").startswith("ERROR")
    assert env.be.made == []                       # no browser was even started for it
    # an already open page cannot be sent elsewhere by the page itself either
    run(env, op="open", url="https://myblog.vn/")
    env.be.click_goes_to = "https://evil.example/phish"
    out = run(env, op="click", element=1)
    assert "CHẶN" in out and "evil.example" in out


def test_open_follows_only_covered_hosts_through_allow_predicate(env):
    env.v.create("Blog", _cookies(".myblog.vn"))
    run(env, op="open", url="https://myblog.vn/")
    allow = env.be.made[0].allow
    assert allow("https://app.myblog.vn/x") and not allow("https://myblog.vn.evil.com/") and not allow("data:text/html,x")


def test_cookie_values_never_in_any_return(env):
    env.v.create("Shopee", _cookies())
    outs = run_seq(env, [{"op": "open", "url": "https://banhang.shopee.vn/"}, {"op": "read"},
                         {"op": "screenshot"}, {"op": "click", "element": 1}, {"op": "type", "element": 2, "text": "a"},
                         {"op": "press", "key": "Enter"}, {"op": "close"}, {"op": "bogus"}])
    for o in outs:
        assert SECRET not in o and "SPC_EC" not in o
    # the value only ever reached the backend, as add_cookies input
    assert any(c["value"] == SECRET for c in env.be.made[0].cookies)


def test_screenshot_saves_png_under_attachments(env):
    env.v.create("Blog", _cookies(".myblog.vn"))
    run(env, op="open", url="https://myblog.vn/")
    out = run(env, op="screenshot")
    rel = out.split("lưu tại ")[1].split(".png")[0] + ".png"
    assert rel.startswith("attachments/browse/")
    assert open(f"{env.root}/{rel}", "rb").read().startswith(b"\x89PNG")


def test_signed_out_marks_login_and_stops(env):
    lg = env.v.create("Blog", _cookies(".myblog.vn"))
    env.be.pages["https://myblog.vn/admin"] = ("https://myblog.vn/login?next=/admin", "Đăng nhập", "form")
    out = run(env, op="open", url="https://myblog.vn/admin")
    assert out.startswith("ĐĂNG NHẬP HẾT HẠN") and "Đừng thử lại" in out
    assert env.v.view(env.v.store.get(lg["id"]))["status"] == "signed_out"
    assert env.mgr.sessions == {} and env.be.made[0].closed


# ---------------------------------------------------------------- can_act


def test_can_act_off_blocks_every_op(env):
    lg = env.v.create("Blog", _cookies(".myblog.vn"))
    run(env, op="open", url="https://myblog.vn/")
    env.v.control(lg["id"], "act_off")
    for a in ({"op": "open", "url": "https://myblog.vn/"}, {"op": "read"}, {"op": "screenshot"},
              {"op": "click", "element": 1}, {"op": "type", "element": 2, "text": "x"}, {"op": "press", "key": "Enter"}):
        out = run(env, **a)
        assert out.startswith("ERROR") and "TẮT quyền thao tác" in out, a
    assert env.be.made[0].log == []


def test_allow_ai_off_also_blocks(env):
    lg = env.v.create("Blog", _cookies(".myblog.vn"))
    run(env, op="open", url="https://myblog.vn/")
    env.v.control(lg["id"], "deny")
    assert run(env, op="read").startswith("ERROR")


# ---------------------------------------------------------------- approval gate


def test_auto_login_acts_freely(env):
    lg = env.v.create("Blog", _cookies(".myblog.vn"))
    assert lg["approval"] == "auto"
    run(env, op="open", url="https://myblog.vn/")
    out = run(env, op="click", element=1)
    assert "Đã bấm" in out and env.be.made[0].log[0][0] == "click"


def test_ask_login_free_ops_do_not_need_approval(env):
    env.v.create("Shopee", _cookies())
    run(env, op="open", url="https://banhang.shopee.vn/")
    assert "Xin chào" in run(env, op="read")
    assert run(env, op="screenshot").startswith("Đã chụp")
    assert run(env, op="close").startswith("Đã đóng")
    assert env.v.approvals_pending() == []


def test_click_waits_then_once_is_single_use(env):
    env.v.create("Shopee", _cookies())
    run(env, op="open", url="https://banhang.shopee.vn/")
    out = run(env, op="click", element=1)
    assert "Chờ chủ duyệt, mã " in out and "approval_id=" in out
    aid = _approval_id(out)
    assert env.be.made[0].log == []                                   # nothing ran
    assert len(env.notes) == 1 and "Xoá sản phẩm" in env.notes[0][1]  # owner told
    assert run(env, op="click", element=1).count(aid) >= 1            # identical call: same pending, no duplicate
    assert len(env.v.approvals_pending()) == 1 and len(env.notes) == 1
    # retry before the owner decided
    early = run(env, op="click", element=1, approval_id=aid)
    assert early.startswith("CHƯA ĐƯỢC CHẠY") and env.be.made[0].log == []
    _decide(env, aid, "once")
    ran = run(env, op="click", element=1, approval_id=aid)
    assert "Đã bấm" in ran and len(env.be.made[0].log) == 1
    again = run(env, op="click", element=1, approval_id=aid)
    assert again.startswith("CHƯA ĐƯỢC CHẠY") and "đã dùng" in again and len(env.be.made[0].log) == 1
    assert env.v.store.get(env.v.store.find_name("Shopee")["id"])["approval"] == "ask"   # once does not flip the login


def test_hash_mismatch_is_rejected(env):
    env.v.create("Shopee", _cookies())
    run(env, op="open", url="https://banhang.shopee.vn/")
    aid = _approval_id(run(env, op="type", element=2, text="giá 100"))
    _decide(env, aid, "once")
    wrong = run(env, op="type", element=2, text="giá 1 triệu", approval_id=aid)       # other text
    assert wrong.startswith("CHƯA ĐƯỢC CHẠY") and "khác" in wrong
    wrong2 = run(env, op="click", element=2, approval_id=aid)                         # other op
    assert wrong2.startswith("CHƯA ĐƯỢC CHẠY")
    assert env.be.made[0].log == []
    assert "Đã gõ" in run(env, op="type", element=2, text="giá 100", approval_id=aid)  # the exact one still works


def test_expired_approval_is_rejected(env):
    env.v.create("Shopee", _cookies())
    run(env, op="open", url="https://banhang.shopee.vn/")
    aid = _approval_id(run(env, op="press", key="Enter"))
    env.v.approval_decide(aid, "once", now=time.time())
    env.v.store._db.execute("UPDATE browse_approvals SET decided_at=?", (time.time() - lv.APPROVAL_TTL - 5,))
    out = run(env, op="press", key="Enter", approval_id=aid)
    assert out.startswith("CHƯA ĐƯỢC CHẠY") and "hết hạn" in out and env.be.made[0].log == []


def test_denied_approval_never_runs(env):
    env.v.create("Shopee", _cookies())
    run(env, op="open", url="https://banhang.shopee.vn/")
    aid = _approval_id(run(env, op="click", element=1))
    _decide(env, aid, "deny")
    out = run(env, op="click", element=1, approval_id=aid)
    assert "TỪ CHỐI" in out and env.be.made[0].log == []


def test_always_flips_login_to_auto_and_approves_pending(env):
    lg = env.v.create("Shopee", _cookies())
    assert lg["approval"] == "ask"
    run(env, op="open", url="https://banhang.shopee.vn/")
    aid = _approval_id(run(env, op="click", element=1))
    _decide(env, aid, "always")
    assert env.v.view(env.v.store.get(lg["id"]))["approval"] == "auto"
    assert "Đã bấm" in run(env, op="click", element=1, approval_id=aid)
    assert "Đã bấm" in run(env, op="click", element=1)                 # now no approval needed at all


def test_agent_path_cannot_approve(env):
    env.v.create("Shopee", _cookies())
    run(env, op="open", url="https://banhang.shopee.vn/")
    aid = _approval_id(run(env, op="click", element=1))
    for a in ({"op": "approve", "approval_id": aid}, {"op": "decide", "id": aid, "decision": "once"}):
        assert run(env, **a).startswith("ERROR")
    # a made-up id, or the pending one itself, never runs
    assert run(env, op="click", element=1, approval_id="ap_deadbeef").startswith("CHƯA ĐƯỢC CHẠY")
    assert run(env, op="click", element=1, approval_id=aid).startswith("CHƯA ĐƯỢC CHẠY")
    assert env.v.approval_get(aid)["status"] == "pending" and env.be.made[0].log == []
    assert "approval_decide" not in open(browse_ops.__file__).read()


def test_decide_routes_need_a_dashboard_session(tmp_path):
    allowed = [False]
    v = lv.LoginVault(lv.LoginVaultDeps(state_dir=lambda: tmp_path, has_session=lambda r: allowed[0]))
    app = FastAPI()
    app.include_router(v.router)
    c = TestClient(app)
    lg = v.create("Shopee", _cookies())
    ap = v.approval_request(lg["id"], "click", "Shopee · x · bấm #1", "h1")
    assert c.get("/logins/approvals").status_code == 401
    assert c.post("/logins/approvals/decide", json={"id": ap["id"], "decision": "once"}).status_code == 401
    assert v.approval_get(ap["id"])["status"] == "pending"
    allowed[0] = True
    lst = c.get("/logins/approvals").json()["approvals"]
    assert [x["id"] for x in lst] == [ap["id"]] and lst[0]["login_name"] == "Shopee" and "args_hash" not in lst[0]
    assert c.post("/logins/approvals/decide", json={"id": ap["id"], "decision": "bogus"}).status_code == 400
    r = c.post("/logins/approvals/decide", json={"id": ap["id"], "decision": "once"}).json()
    assert r["ok"] and r["approval"]["status"] == "approved"
    assert c.post("/logins/approvals/decide", json={"id": ap["id"], "decision": "deny"}).status_code == 400  # already decided
    v.store.close()


# ---------------------------------------------------------------- sessions


def test_max_three_sessions_and_idle_close(env):
    for i in range(4):
        env.v.create(f"Site{i}", _cookies(f".site{i}.vn"))
    for i in range(3):
        assert "Xin chào" in run(env, op="open", url=f"https://site{i}.vn/")
    full = run(env, op="open", url="https://site3.vn/")
    assert full.startswith("ERROR") and "tối đa 3" in full
    env.now[0] += 601                                                  # all idle past 10 minutes
    assert "Xin chào" in run(env, op="open", url="https://site3.vn/")
    assert len(env.mgr.sessions) == 1 and all(a.closed for a in env.be.made[:3])


def test_close_all_on_shutdown(env):
    env.v.create("Blog", _cookies(".myblog.vn"))
    run(env, op="open", url="https://myblog.vn/")
    asyncio.run(env.mgr.close_all())
    assert env.mgr.sessions == {} and env.be.made[0].closed


def test_needs_login_name_when_nothing_or_many_open(env):
    assert run(env, op="read").startswith("ERROR")


# ---------------------------------------------------------------- plugin shell


def test_plugin_registers_tool_and_is_owner_only():
    import mcp_hub
    assert "javis_browse" in mcp_hub.OWNER_ONLY_TOOLS and "javis_login" in mcp_hub.OWNER_ONLY_TOOLS
    spec = importlib.util.spec_from_file_location("javis_browse_plugin", ROOT / "system" / "plugins" / "javis-browse" / "plugin.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    got = {}

    class Ctx:
        def register_tool(self, name, desc, handler, **kw):
            got.update(name=name, desc=desc, kw=kw)
    m.register(Ctx())
    assert got["name"] == "javis_browse" and "approval_id" in got["desc"] and "javis_login" in got["desc"]
    assert got["kw"]["schema"]["properties"]["op"]["enum"] == list(browse_ops.OPS)


def test_javis_login_is_still_read_only():
    src = (ROOT / "system" / "plugins" / "javis-login" / "plugin.py").read_text()
    assert 'min_mode="readonly"' in src and "click" not in src.split("def register")[1].split("_run")[0].lower().replace("không bấm nút", "")


# ---------------------------------------------------------------- real browser smoke (skips without Chromium)


class _Page(BaseHTTPRequestHandler):
    def do_GET(self):
        body = ("<html><title>Quan tri</title><body><h1>Trang thu</h1><input id=q placeholder=Tim>"
                "<button id=b onclick=\"document.getElementById('out').textContent='da bam'\">Bam vao day</button>"
                "<p id=out></p></body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_smoke_real_chromium_clicks_a_button(tmp_path, monkeypatch):
    import optional_tools
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        pytest.skip("playwright not installed")
    if not optional_tools.duong_dan_chrome():
        pytest.skip("no Chromium on this machine")
    srv = HTTPServer(("127.0.0.1", 0), _Page)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    v = lv.LoginVault(lv.LoginVaultDeps(state_dir=lambda: tmp_path, has_session=lambda r: True))
    monkeypatch.setattr(lv, "_CURRENT", v)
    v.create("Local", json.dumps([{"domain": "127.0.0.1", "hostOnly": True, "name": "sid", "value": "v", "path": "/"}]))
    mgr = browse_ops.BrowseManager(lv.current, browse_ops.PlaywrightBackend(), url_check=None)

    async def go():
        try:
            a = await mgr.run({"op": "open", "url": f"http://127.0.0.1:{port}/"}, str(tmp_path))
            b = await mgr.run({"op": "click", "target_text": "Bam vao day"}, str(tmp_path))
            return a, b
        finally:
            await mgr.close_all()
    try:
        a, b = asyncio.run(go())
    finally:
        srv.shutdown()
        v.store.close()
    assert "Trang thu" in a and "button" in a
    assert "da bam" in b and "Đã bấm" in b


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
