"""Kết nối MCP qua OAuth không xin phạm vi nhà cung cấp cấm (0.175.1).

    python tests/run.py oauth_scope_clerk      (KHÔNG mạng)

Chủ repo 16/10/2026: kết nối Higgsfield báo invalid_grant. Lỗi thật nằm ở URL callback: Higgsfield đăng nhập qua Clerk,
Clerk trả invalid_scope "OAuth 2.0 Client is not allowed to request scope 'private_metadata'". Javis đã xin NGUYÊN danh sách
`scopes_supported` của máy chủ đăng nhập, rồi bỏ qua tham số error ở callback và đem code rỗng đi đổi.

File này canh:
  1. Chọn phạm vi theo chuẩn MCP: WWW-Authenticate, rồi protected resource metadata, cuối cùng mới tới máy chủ đăng nhập.
  2. Nhận invalid_scope thì bỏ phạm vi bị từ chối, tự mở lại trang đăng nhập (có trần), không đổi code rỗng.
  3. Lỗi khác ở bước xin quyền báo đúng lỗi đó, trang báo lỗi escape chữ do nhà cung cấp gửi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import urllib.parse
from unittest.mock import AsyncMock, patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-oauth-scope-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import oauth_mcp  # noqa: E402
import mcp_store  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


CLERK = ["openid", "profile", "email", "public_metadata", "private_metadata", "offline_access"]

# ---- 1. Chọn phạm vi
check("CANARY: không có nguồn nào khác thì vẫn dùng danh sách máy chủ đăng nhập",
      oauth_mcp._chon_scopes({"scopes_supported": CLERK}, {}) == CLERK)
check("protected resource metadata thắng danh sách máy chủ đăng nhập",
      oauth_mcp._chon_scopes({"scopes_supported": CLERK, "_prm_scopes": ["openid", "email"]}, {}) == ["openid", "email"])
check("scope trong WWW-Authenticate thắng tất cả",
      oauth_mcp._chon_scopes({"scopes_supported": CLERK, "_prm_scopes": ["openid"], "_www_scope": "mcp:tools email"}, {})
      == ["mcp:tools", "email"])
check("phạm vi đã bị từ chối thì bỏ ở mọi nguồn",
      "private_metadata" not in oauth_mcp._chon_scopes({"scopes_supported": CLERK}, {"blocked_scopes": ["private_metadata"]}))
check("scope_omit: không gửi phạm vi nào", oauth_mcp._chon_scopes({"scopes_supported": CLERK}, {"scope_omit": True}) == [])
check("đọc được tên phạm vi trong lời báo của Clerk",
      oauth_mcp._scope_bi_tu_choi("OAuth 2.0 Client is not allowed to request scope 'private_metadata'.") == ["private_metadata"])

# ---- 2. Luồng thật với máy chủ giả (không mạng): start_auth -> callback invalid_scope -> trang đăng nhập mới
conn_id, err = mcp_store.add_connection("custom", {"label": "Higgsfield", "url": "https://mcp.higgsfield.example/mcp",
                                                   "auth": "oauth"})
assert not err, err
store = oauth_mcp._load()
store[conn_id] = {"client_id": "dcr-client-1"}   # đã tự đăng ký từ trước: không gọi DCR
oauth_mcp._save(store)
MD = {"authorization_endpoint": "https://clerk.example/oauth/authorize", "token_endpoint": "https://clerk.example/oauth/token",
      "scopes_supported": CLERK, "_www_scope": "", "_prm_scopes": []}
REDIR = "http://localhost:7777/connect/oauth/callback"


def q_of(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


async def luong():
    with patch.object(oauth_mcp, "_discover", AsyncMock(return_value=dict(MD))):
        r1 = await oauth_mcp.start_auth(conn_id, REDIR)
        q1 = q_of(r1["url"])
        check("lần đầu: máy chủ không khai gì hơn nên vẫn xin danh sách của máy chủ đăng nhập",
              "private_metadata" in q1.get("scope", "").split(), q1)
        doi = AsyncMock()
        with patch.object(oauth_mcp.httpx, "AsyncClient", doi):
            r2 = await oauth_mcp.handle_callback(q1["state"], "", "invalid_scope",
                                                 "OAuth 2.0 Client is not allowed to request scope 'private_metadata'")
        check("CANARY: invalid_scope thì KHÔNG đem code rỗng đi đổi", not doi.called)
        check("invalid_scope: trả trang đăng nhập mới để chuyển thẳng sang", bool(r2.get("retry_url")), r2)
        q2 = q_of(r2.get("retry_url", "?"))
        check("trang đăng nhập mới không còn private_metadata, vẫn giữ phạm vi khác",
              "private_metadata" not in q2.get("scope", "").split() and "openid" in q2.get("scope", "").split(), q2)
        check("nhớ phạm vi bị từ chối cho lần Kết nối sau",
              oauth_mcp._load()[conn_id].get("blocked_scopes") == ["private_metadata"])
        # Bị từ chối mãi (lời báo không nêu tên): thử không phạm vi, rồi dừng ở trần, không lặp vô hạn.
        r3 = await oauth_mcp.handle_callback(q2["state"], "", "invalid_scope", "nope")
        check("lời báo không nêu tên phạm vi: thử lại không gửi scope", "scope" not in q_of(r3.get("retry_url", "?")), r3)
        q3 = q_of(r3.get("retry_url", "?"))
        r4 = await oauth_mcp.handle_callback(q3.get("state", ""), "", "invalid_scope", "nope")
        check("chạm trần thử lại: báo lỗi rõ, không chuyển tiếp nữa",
              not r4.get("retry_url") and "invalid_scope" in (r4.get("error") or ""), r4)
        r5s = await oauth_mcp.start_auth(conn_id, REDIR)
        r5 = await oauth_mcp.handle_callback(q_of(r5s["url"])["state"], "", "access_denied", "<b>user said no</b>")
        check("từ chối thường: báo đúng lỗi, không thử lại", not r5.get("retry_url") and "access_denied" in r5.get("error", ""), r5)


asyncio.run(luong())

# ---- 3. Route callback: chuyển hướng khi có retry_url, escape lời báo lỗi
import main  # noqa: E402


async def route():
    with patch.object(main.oauth_mcp, "handle_callback", AsyncMock(return_value={"ok": False, "retry_url": "https://x/a"})):
        r = await main.connect_oauth_callback(state="s", code="", error="invalid_scope", error_description="d")
    check("route: có retry_url thì chuyển hướng 302", r.status_code == 302 and r.headers.get("location") == "https://x/a")
    m = AsyncMock(return_value={"ok": False, "error": "<script>alert(1)</script>"})
    with patch.object(main.oauth_mcp, "handle_callback", m):
        r = await main.connect_oauth_callback(state="s", code="", error="access_denied", error_description="x")
    body = r.body.decode()
    check("route: chuyển error và error_description xuống oauth_mcp", m.call_args.args[2:] == ("access_denied", "x"), m.call_args)
    check("route: lời báo lỗi được escape", "<script>" not in body and "&lt;script&gt;" in body, body[-200:])


asyncio.run(route())
check("no em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read())

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
