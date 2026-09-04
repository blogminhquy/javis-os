"""Test connector Meta Ads (Graph API) BYO app (v0.9.40). Chạy tay / CI:

    python tests/run.py meta_graph

KHÔNG mạng (monkeypatch httpx). Phủ: catalog connector hợp lệ, oauth_mcp nhánh Meta
(authorize không PKCE + redirect localhost + scope, đổi code bằng GET + nâng long-lived,
_refresh qua fb_exchange_token), plugin nạp + tool readonly + gate chưa-kết-nối + format.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import urllib.parse
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-metagraph-"))

_fails = []
def check(n, c):
    print(("ok  " if c else "FAIL ") + n)
    if not c: _fails.append(n)


# ---- 1. Connector: đã dọn sang kho ----
# Khuôn connector `meta-ads-graph` rời `system/mcp-catalog.json` ở 0.55.36 và giờ sống trong gói
# `javis.meta-ads-graph` của repo kho (blogminhquy/javis-store). Những assert về HÌNH DẠNG của nó
# (provider, scope, fields, default_perm, phân loại tool, chữ cảnh báo) đi theo dữ liệu sang đó:
# `tools/kiem-tra.py` của repo kho chạy đúng các phép kiểm ấy trên mọi Pull Request.
#
# Giữ lại ở đây là giả vờ: dữ liệu đổi được trong kho mà KHÔNG cần bản Javis mới, nên một test
# ở repo này chỉ canh được bản chụp lúc dọn nhà chứ không canh được thứ người dùng thật sự cài.
# Phần bên dưới - plugin đi kèm - vẫn là mã của app nên vẫn kiểm ở đây.


# ---- 2. oauth_mcp nhánh Meta ----
import oauth_mcp  # noqa: E402
import secrets_store  # noqa: E402

META_AUTH = {"provider": "meta", "authorize_url": "https://www.facebook.com/v25.0/dialog/oauth",
             "token_url": "https://graph.facebook.com/v25.0/oauth/access_token",
             "scopes": ["ads_read", "business_management"]}


class _Resp:
    def __init__(self, data): self._d = data
    def json(self): return self._d


class _FakeClient:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def get(self, url, params=None):
        params = params or {}
        if params.get("grant_type") == "fb_exchange_token":
            return _Resp({"access_token": "LONGLIVED60D", "token_type": "bearer", "expires_in": 5184000})
        return _Resp({"access_token": "SHORTLIVED", "token_type": "bearer", "expires_in": 3600})
    async def post(self, url, data=None, headers=None):
        return _Resp({"access_token": "should-not-be-used"})


class _FakeHttpx:
    AsyncClient = _FakeClient


async def oauth_tests():
    orig_conn, orig_secrets, orig_httpx = oauth_mcp._conn, oauth_mcp.mcp_store.connection_secrets, oauth_mcp.httpx
    oauth_mcp._conn = lambda cid: {"id": cid, "url": "", "connector": {"auth": META_AUTH}}
    oauth_mcp.mcp_store.connection_secrets = lambda cid: {"client_id": "APPID", "client_secret": "SECRET"}
    oauth_mcp.httpx = _FakeHttpx
    try:
        res = await oauth_mcp.start_auth("cmeta", "http://127.0.0.1:7777/connect/oauth/callback")
        check("start_auth: ok + có url", res.get("ok") and res.get("url"))
        u = urllib.parse.urlparse(res["url"])
        q = urllib.parse.parse_qs(u.query)
        check("authorize: redirect ĐỔI 127.0.0.1 → localhost",
              q["redirect_uri"][0] == "http://localhost:7777/connect/oauth/callback")
        check("authorize: KHÔNG có PKCE (code_challenge)", "code_challenge" not in q)
        check("authorize: scope dấu cách đúng", q["scope"][0] == "ads_read business_management")
        check("authorize: client_id từ secrets BYO", q["client_id"][0] == "APPID")
        # Kết nối lại mà thiếu auth_type=rerequest thì Facebook đi đường tắt "Tiếp tục với tên X"
        # và KHÔNG hiện lại màn chọn Trang / tài khoản quảng cáo - user không thêm được Trang mới.
        check("authorize: có auth_type=rerequest (bắt Facebook hiện lại màn chọn Trang)",
              q.get("auth_type", [""])[0] == "rerequest")
        state = q["state"][0]

        cb = await oauth_mcp.handle_callback(state, "THE_CODE")
        check("callback: ok", cb.get("ok"))
        ent = oauth_mcp._load().get("cmeta") or {}
        check("callback: LƯU token LONG-LIVED (đã nâng qua fb_exchange_token)",
              secrets_store.decrypt(ent.get("access_token", "")) == "LONGLIVED60D")
        check("callback: provider=meta + refresh_token rỗng + expires ~60 ngày",
              ent.get("provider") == "meta" and not secrets_store.decrypt(ent.get("refresh_token", ""))
              and ent.get("expires_at", 0) > __import__("time").time() + 5000000)

        # _refresh dùng fb_exchange_token (không refresh_token)
        ent2 = await oauth_mcp._refresh("cmeta", oauth_mcp._load()["cmeta"])
        check("_refresh: nhánh meta trả token mới qua fb_exchange_token",
              ent2 and secrets_store.decrypt(ent2.get("access_token", "")) == "LONGLIVED60D")

        # callback báo lỗi thân thiện khi Facebook từ chối
        oauth_mcp.httpx = type("H", (), {"AsyncClient": type("C", (), {
            "__init__": lambda s, *a, **k: None,
            "__aenter__": lambda s: asyncio.sleep(0, s),
            "__aexit__": lambda s, *a: asyncio.sleep(0, False),
            "get": lambda s, url, params=None: asyncio.sleep(0, _Resp({"error": {"message": "redirect_uri isn't valid"}})),
        })})
        r2 = await oauth_mcp.start_auth("cmeta2", "http://127.0.0.1:7777/connect/oauth/callback")
        st2 = urllib.parse.parse_qs(urllib.parse.urlparse(r2["url"]).query)["state"][0]
        cb2 = await oauth_mcp.handle_callback(st2, "BADCODE")
        check("callback lỗi: surface message Meta + mẹo localhost",
              cb2.get("ok") is False and "redirect_uri isn't valid" in cb2["error"] and "localhost" in cb2["error"])
    finally:
        oauth_mcp._conn, oauth_mcp.mcp_store.connection_secrets, oauth_mcp.httpx = orig_conn, orig_secrets, orig_httpx

asyncio.run(oauth_tests())


# ---- 3. Plugin ----
spec = importlib.util.spec_from_file_location(
    "meta_ads_graph_test", str(ROOT / "system" / "plugins" / "meta-ads-graph" / "plugin.py"))
plug = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plug)


class _Ctx:
    def __init__(self): self.tools = []
    def register_tool(self, name, description, handler, schema=None, min_mode="readonly", check_fn=None, **k):
        self.tools.append({"name": name, "handler": handler, "min_mode": min_mode, "check_fn": check_fn})


ctx = _Ctx()
plug.register(ctx)
names = {t["name"] for t in ctx.tools}
check("plugin: đủ 4 tool", names == {"meta_ads_accounts", "meta_ads_insights", "meta_ads_campaigns", "meta_ads_get"})
check("plugin: mọi tool readonly", all(t["min_mode"] == "readonly" for t in ctx.tools))

# chưa kết nối → _check chặn + handler trả ERROR
plug._connected_id = lambda: None
check("plugin: _check chặn khi chưa kết nối", "Chưa kết nối" in (plug._check() or ""))


async def plugin_tests():
    # giả token + giả _get để test handler không cần mạng
    plug._connected_id = lambda: "cmeta"
    async def _fake_token(): return "TOK"
    calls = {}
    async def _fake_get(path, params, token):
        calls["last"] = (path, params, token)
        if path == "me/adaccounts" and (params or {}).get("limit") == 1:
            return {"data": [{"account_id": "123"}]}
        if path == "me/adaccounts":
            return {"data": [{"account_id": "123", "name": "Shop A", "currency": "VND"}]}
        if path.endswith("/insights"):
            return {"data": [{"spend": "50000", "impressions": "1000"}]}
        if path.endswith("/campaigns"):
            return {"data": [{"name": "CD1", "status": "ACTIVE"}]}
        return {"data": []}
    plug._token = _fake_token
    plug._get = _fake_get

    r_acc = await plug._accounts({}, None)
    check("tool accounts: trả JSON list", "Shop A" in r_acc)
    r_ins = await plug._insights({}, None)
    check("tool insights: tự lấy account đầu (act_123) + kỳ mặc định last_7d",
          "50000" in r_ins and calls["last"][0] == "act_123/insights" and calls["last"][1]["date_preset"] == "last_7d")
    r_ins2 = await plug._insights({"account_id": "act_999", "since": "2026-07-01", "until": "2026-07-10"}, None)
    check("tool insights: time_range khi có since+until", "time_range" in calls["last"][1] and calls["last"][0] == "act_999/insights")
    r_camp = await plug._campaigns({"account_id": "123"}, None)
    check("tool campaigns: normalize act_ + trả JSON", "CD1" in r_camp and calls["last"][0] == "act_123/campaigns")
    r_raw = await plug._raw_get({"path": "me/businesses"}, None)
    check("tool get: gọi path tuỳ ý", calls["last"][0] == "me/businesses")
    r_raw2 = await plug._raw_get({}, None)
    check("tool get: thiếu path → ERROR", r_raw2.startswith("ERROR"))

    # format lỗi Graph
    check("_fmt: lỗi Graph → ERROR message", plug._fmt({"error": {"message": "boom"}}).startswith("ERROR: Facebook API: boom"))

asyncio.run(plugin_tests())

if _fails:
    print(f"\nFAIL - {len(_fails)} test: {_fails}")
    sys.exit(1)
print("\nOK - test_meta_graph: tất cả pass")
