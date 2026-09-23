"""Javis trong ChatGPT: đi TRỌN luồng kết nối đúng như ChatGPT đi, trên app thật.

    python tests/run.py javis_trong_chatgpt

ChatGPT (Developer mode) nối một MCP connector theo đúng thứ tự dưới đây, và file này đóng vai
nó từng bước (thứ tự đối chiếu với XiaoDuoYa/codex-with-chatgpt, đã chạy thật với ChatGPT):

  1. gọi /chatgpt/mcp không token -> 401 kèm `resource_metadata`
  2. đọc protected resource metadata -> biết authorization server ở đâu
  3. đọc authorization server metadata -> biết các endpoint
  4. tự đăng ký client (RFC 7591)
  5. mở trang Cho phép trong trình duyệt của người dùng -> người dùng đăng nhập, bấm Cho phép
  6. đổi mã lấy token, có PKCE S256
  7. gọi MCP bằng token; hết hạn thì làm mới

Ngoài đường vui, file này khoá những chỗ một cửa OAuth hay hở: redirect về máy lạ, mã dùng hai
lần, PKCE sai, refresh bị đánh cắp rồi dùng lại, token của cửa này lọt sang hub nội bộ và ngược
lại, và mức quyền chủ chọn phải tới được lớp ép cứng của hub.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import base64
import hashlib
import os
import secrets
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-gptconn-")

from fastapi.testclient import TestClient  # noqa: E402

import chatgpt_connector as cc  # noqa: E402
import config as cfg  # noqa: E402
import main  # noqa: E402
import mcp_hub  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + ((f"  [{them}]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


GOC = "http://testserver"
REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"


def _pkce():
    ver = secrets.token_urlsafe(48)
    ch = base64.urlsafe_b64encode(hashlib.sha256(ver.encode()).digest()).decode().rstrip("=")
    return ver, ch


# Bắt mức quyền hub nhận được, và trả một danh sách tool giả: file này thử CỬA, không thử MCP.
_nhan = {}


async def _discover_gia(mode, **kw):
    _nhan["mode"] = mode
    _nhan["vault_root"] = kw.get("vault_root")
    return ([{"fn": "javis_thu", "description": "tool thử", "schema": {"type": "object"}}],
            {"javis_thu": {"call": _goi_gia}})


async def _goi_gia(args):
    return "đã gọi javis_thu"


mcp_hub.discover_all = _discover_gia

cl = TestClient(main.app)          # KHÔNG cookie: đóng vai máy chủ OpenAI
trinh_duyet = TestClient(main.app)  # có cookie: đóng vai trình duyệt của chủ Javis


def mcp(token, method, params=None, client=None, mid=1):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    return (client or cl).post(cc.DUONG_MCP, json={"jsonrpc": "2.0", "id": mid, "method": method,
                                                   "params": params or {}}, headers=h)


# ============================================================
# 0) TẮT mặc định: cửa không tồn tại
# ============================================================

check("mặc định tắt", cc.cau_hinh()["bat"] is False)
for duong in (cc.WK_PR, cc.WK_PR_MCP, cc.WK_AS, cc.WK_OIDC):
    # 404 từ chính cửa này, hoặc 403 từ hàng rào DNS-rebinding có sẵn (máy chưa đặt mật khẩu
    # thì hàng rào đó chặn host lạ trước). Điều phải giữ là: KHÔNG lộ metadata.
    _r = cl.get(duong)
    check(f"tắt -> {duong} không lộ gì", _r.status_code in (403, 404) and "issuer" not in _r.text
          and "authorization_servers" not in _r.text, _r.status_code)
check("tắt -> /chatgpt/mcp trả 404, không phải 401 (không quảng bá gì)",
      mcp("", "initialize").status_code == 404)
check("tắt -> không đăng ký client được", cl.post(cc.DUONG_REGISTER, json={
    "redirect_uris": [REDIRECT]}).status_code == 404)

check("chưa có mật khẩu quản trị -> KHÔNG cho bật",
      cc.dat_cau_hinh(bat=True).get("ok") is False and cc.cau_hinh()["bat"] is False)

_s = cfg.read_settings()
_s["auth"] = {"username": "admin", **dict(zip(("password_hash", "salt"),
                                              cfg.hash_password("matkhau123")))}
cfg.write_settings(_s)

# Dashboard: bật phải đi bằng PHIÊN trình duyệt, không qua được khi chưa đăng nhập.
check("bật khi chưa đăng nhập dashboard -> bị chặn",
      cl.post("/chatgpt/connector/settings", json={"bat": True}).status_code in (401, 403))
r = trinh_duyet.post("/auth/login", data={"username": "admin", "password": "matkhau123"})
check("chủ đăng nhập dashboard được", r.status_code == 200 and r.json().get("ok"))
r = trinh_duyet.post("/chatgpt/connector/settings", json={"bat": True})
check("chủ bật được từ dashboard", r.status_code == 200 and r.json().get("bat") is True)
st = trinh_duyet.get("/chatgpt/connector/status").json()
check("thẻ dashboard đưa ra đúng địa chỉ MCP để dán vào ChatGPT",
      st.get("url_mcp") == GOC + cc.DUONG_MCP, st.get("url_mcp"))
check("mức quyền mặc định là full (quyết định 2026-09-10)", st.get("muc_quyen") == "full")


# ============================================================
# 1-3) Khám phá, đúng như ChatGPT dò
# ============================================================

r = mcp("", "initialize")
check("1. gọi MCP không token -> 401", r.status_code == 401)
wa = r.headers.get("www-authenticate", "")
check("1. kèm WWW-Authenticate chỉ tới protected resource metadata",
      f'resource_metadata="{GOC}{cc.WK_PR_MCP}"' in wa, wa)

pr = cl.get(cc.WK_PR_MCP).json()
check("2. resource đúng là địa chỉ MCP", pr.get("resource") == GOC + cc.DUONG_MCP, pr)
check("2. chỉ về authorization server là chính Javis", pr.get("authorization_servers") == [GOC])
check("2. bản không đuôi cũng có (client dò kiểu cũ)", cl.get(cc.WK_PR).json() == pr)

asm = cl.get(cc.WK_AS).json()
check("3. issuer khớp", asm.get("issuer") == GOC)
check("3. chỉ nhận PKCE S256", asm.get("code_challenge_methods_supported") == ["S256"])
check("3. client công khai, không bí mật", asm.get("token_endpoint_auth_methods_supported") == ["none"])
check("3. có đăng ký client động", asm.get("registration_endpoint") == GOC + cc.DUONG_REGISTER)
check("3. openid-configuration trả cùng nội dung (vài client dò đường này)",
      cl.get(cc.WK_OIDC).json() == asm)


# ============================================================
# 4) Đăng ký client
# ============================================================

for ten, uri in (("máy lạ", "https://ke-gian.example/cb"),
                 ("http thường", "http://chatgpt.com/cb"),
                 ("tên miền giả dạng", "https://chatgpt.com.ke-gian.example/cb")):
    check(f"4. redirect về {ten} -> từ chối",
          cl.post(cc.DUONG_REGISTER, json={"redirect_uris": [uri]}).status_code == 400)
r = cl.post(cc.DUONG_REGISTER, json={"client_name": "ChatGPT", "redirect_uris": [REDIRECT]})
check("4. redirect về chatgpt.com -> nhận", r.status_code == 201, r.text)
CID = r.json().get("client_id", "")
check("4. có client_id, không có client_secret", CID and "client_secret" not in r.json())


# ============================================================
# 5) Trang Cho phép
# ============================================================

def uy_quyen(client, challenge, redirect=REDIRECT, state="st-123", **them):
    q = {"response_type": "code", "client_id": CID, "redirect_uri": redirect, "state": state,
         "code_challenge": challenge, "code_challenge_method": "S256", **them}
    return client.get(cc.DUONG_AUTHORIZE, params=q, follow_redirects=False)


VER, CH = _pkce()

r = uy_quyen(cl, CH)
check("5. chưa đăng nhập -> hiện ô đăng nhập ngay tại chỗ", r.status_code == 200
      and "Đăng nhập Javis" in r.text and "/auth/login" in r.text)
check("5. trang đó không cho nhúng khung (chống clickjacking)",
      r.headers.get("x-frame-options") == "DENY")

r = uy_quyen(trinh_duyet, CH, redirect="https://chatgpt.com/khac")
check("5. redirect_uri khác lúc đăng ký -> trang lỗi, KHÔNG chuyển hướng",
      r.status_code == 400 and "location" not in r.headers)

r = uy_quyen(trinh_duyet, "")
loc = r.headers.get("location", "")
check("5. thiếu PKCE -> báo lỗi ngược về ChatGPT theo OAuth",
      r.status_code == 302 and "error=invalid_request" in loc and "state=st-123" in loc, loc)

r = uy_quyen(trinh_duyet, CH)
check("5. đã đăng nhập -> trang Cho phép", r.status_code == 200 and "Cho phép ChatGPT" in r.text)
check("5. trang nói rõ mức quyền đang dùng", "Toàn quyền" in r.text)
YID = r.text.split('name="yeu_cau" value="')[1].split('"')[0]

r = cl.post(cc.DUONG_AUTHORIZE, data={"yeu_cau": YID, "hanh_dong": "cho_phep"},
            follow_redirects=False)
check("5. bấm Cho phép mà KHÔNG có phiên -> chặn", r.status_code == 401)

r = trinh_duyet.post(cc.DUONG_AUTHORIZE, data={"yeu_cau": YID, "hanh_dong": "cho_phep"},
                     headers={"Origin": "https://ke-gian.example"}, follow_redirects=False)
check("5. bấm Cho phép từ trang lạ (CSRF) -> hàng rào chặn", r.status_code == 403)

check("5. CANARY: trang KHÔNG dùng no-referrer (trình duyệt sẽ gửi Origin: null khi nộp form)",
      'content="no-referrer"' not in uy_quyen(trinh_duyet, CH).text)
# Trình duyệt thật GỬI Origin khi nộp form cùng nguồn. TestClient thì không, nên phải tự gửi:
# thiếu dòng này là phép thử đi vòng qua đúng hàng rào đã chặn nút Cho phép trên Chromium thật.
r = trinh_duyet.post(cc.DUONG_AUTHORIZE, data={"yeu_cau": YID, "hanh_dong": "cho_phep"},
                     headers={"Origin": GOC}, follow_redirects=False)
loc = r.headers.get("location", "")
q = parse_qs(urlparse(loc).query)
check("5. Cho phép -> quay về đúng ChatGPT kèm mã và state",
      r.status_code == 302 and loc.startswith(REDIRECT) and q.get("state") == ["st-123"]
      and q.get("code"), loc)
MA = (q.get("code") or [""])[0]
r = trinh_duyet.post(cc.DUONG_AUTHORIZE, data={"yeu_cau": YID, "hanh_dong": "cho_phep"},
                     follow_redirects=False)
check("5. cùng một yêu cầu không bấm được lần hai", r.status_code == 400)


# ============================================================
# 6) Đổi mã lấy token
# ============================================================

def doi(code, ver, cid=None):
    # cid=None rồi đọc CID lúc GỌI: để `cid=CID` thì Python đóng băng giá trị lúc định nghĩa
    # hàm, và client đăng ký lại ở mục 9 sẽ bị đổi mã bằng id của client đã xoá.
    return cl.post(cc.DUONG_TOKEN, data={"grant_type": "authorization_code", "code": code,
                                         "code_verifier": ver, "client_id": cid or CID,
                                         "redirect_uri": REDIRECT})


r = doi(MA, "sai-" + VER)
check("6. PKCE sai -> invalid_grant", r.status_code == 400 and r.json().get("error") == "invalid_grant")
check("6. CANARY: mã đã bị thử sai thì CHẾT luôn, đúng verifier cũng không cứu (chống dò)",
      doi(MA, VER).status_code == 400)

# Lượt mới cho đường vui.
VER, CH = _pkce()
r = uy_quyen(trinh_duyet, CH)
YID = r.text.split('name="yeu_cau" value="')[1].split('"')[0]
loc = trinh_duyet.post(cc.DUONG_AUTHORIZE, data={"yeu_cau": YID, "hanh_dong": "cho_phep"},
                       follow_redirects=False).headers["location"]
MA = parse_qs(urlparse(loc).query)["code"][0]
check("6. mã của client KHÁC -> từ chối", doi(MA, VER, cid="chatgpt-khac").status_code == 400)

VER, CH = _pkce()
r = uy_quyen(trinh_duyet, CH)
YID = r.text.split('name="yeu_cau" value="')[1].split('"')[0]
loc = trinh_duyet.post(cc.DUONG_AUTHORIZE, data={"yeu_cau": YID, "hanh_dong": "cho_phep"},
                       follow_redirects=False).headers["location"]
MA = parse_qs(urlparse(loc).query)["code"][0]
r = doi(MA, VER)
tk = r.json()
check("6. đúng mã + đúng PKCE -> có access và refresh",
      r.status_code == 200 and tk.get("access_token") and tk.get("refresh_token"), r.text)
check("6. không cho cache token", r.headers.get("cache-control") == "no-store")
check("6. mã dùng một lần", doi(MA, VER).status_code == 400)
AT, RT = tk.get("access_token", ""), tk.get("refresh_token", "")

_kho = (cfg.STATE_DIR / ".chatgpt_connector.json").read_text(encoding="utf-8")
check("6. kho KHÔNG chứa token thô, chỉ chứa băm", AT not in _kho and RT not in _kho)


# ============================================================
# 7) Gọi MCP bằng token
# ============================================================

r = mcp(AT, "initialize", {"protocolVersion": "2025-06-18"})
check("7. initialize qua được", r.status_code == 200
      and r.json().get("result", {}).get("serverInfo", {}).get("name") == "javis-hub", r.text)
r = mcp(AT, "tools/list")
check("7. tools/list ra đúng danh sách của hub",
      [t["name"] for t in r.json()["result"]["tools"]] == ["javis_thu"])
check("7. hub nhận mức quyền chủ chọn (full)", _nhan.get("mode") == "full")
r = mcp(AT, "tools/call", {"name": "javis_thu", "arguments": {}})
check("7. tools/call chạy thật", "đã gọi javis_thu" in r.text)

trinh_duyet.post("/chatgpt/connector/settings", json={"muc_quyen": "suggest"})
mcp(AT, "tools/list")
check("7. chủ hạ quyền trên dashboard -> có hiệu lực NGAY lượt sau, không chờ token mới",
      _nhan.get("mode") == "suggest")
check("7. mức quyền lạ bị từ chối",
      trinh_duyet.post("/chatgpt/connector/settings", json={"muc_quyen": "root"}).status_code == 400)

check("7. GET vào MCP -> 405 (không mở luồng từ máy chủ)", cl.get(
    cc.DUONG_MCP, headers={"Authorization": f"Bearer {AT}"}).status_code == 405)

# Hai cửa KHÔNG dùng chung chìa.
check("7. hub_token nội bộ KHÔNG mở được cửa ChatGPT",
      mcp(mcp_hub.hub_token(), "initialize").status_code == 401)
check("7. token ChatGPT KHÔNG mở được hub nội bộ", cl.post(
    "/hub/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    headers={"Authorization": f"Bearer {AT}"}).status_code == 401)
check("7. token ChatGPT không phải token API của dashboard",
      cl.get("/chatgpt/connector/status", headers={"Authorization": f"Bearer {AT}"}).status_code
      in (401, 403))


# ============================================================
# 8) Làm mới, và refresh bị đánh cắp
# ============================================================

def lam_moi(rt):
    return cl.post(cc.DUONG_TOKEN, data={"grant_type": "refresh_token", "refresh_token": rt,
                                         "client_id": CID})


r = lam_moi(RT)
tk2 = r.json()
check("8. làm mới -> cặp token mới", r.status_code == 200 and tk2.get("refresh_token") not in ("", RT))
AT2, RT2 = tk2.get("access_token", ""), tk2.get("refresh_token", "")
check("8. token mới dùng được", mcp(AT2, "initialize").status_code == 200)
check("8. có đúng MỘT kết nối đang sống", cc.so_ket_noi() == 1, cc.so_ket_noi())

r = lam_moi(RT)
check("8. dùng lại refresh CŨ -> từ chối", r.status_code == 400)
check("8. CANARY: và thu hồi CẢ HỌ, token mới nhất cũng chết (ai đó cầm bản sao)",
      mcp(AT2, "initialize").status_code == 401 and lam_moi(RT2).status_code == 400)


# ============================================================
# 9) Thu hồi, ngắt, tắt
# ============================================================

def ket_noi_moi():
    ver, ch = _pkce()
    r = uy_quyen(trinh_duyet, ch)
    yid = r.text.split('name="yeu_cau" value="')[1].split('"')[0]
    loc = trinh_duyet.post(cc.DUONG_AUTHORIZE, data={"yeu_cau": yid, "hanh_dong": "cho_phep"},
                           follow_redirects=False).headers["location"]
    return doi(parse_qs(urlparse(loc).query)["code"][0], ver).json()


tk = ket_noi_moi()
cl.post(cc.DUONG_REVOKE, data={"token": tk["refresh_token"]})
check("9. thu hồi refresh -> access cùng họ cũng chết", mcp(tk["access_token"], "initialize").status_code == 401)

tk = ket_noi_moi()
r = trinh_duyet.post("/chatgpt/connector/disconnect")
check("9. nút Ngắt mọi kết nối chạy", r.status_code == 200 and r.json().get("da_ngat", 0) >= 1)
check("9. ngắt xong token chết", mcp(tk["access_token"], "initialize").status_code == 401)
check("9. ngắt xong client cũ phải đăng ký lại",
      uy_quyen(trinh_duyet, _pkce()[1]).status_code == 400)

r = cl.post(cc.DUONG_REGISTER, json={"redirect_uris": [REDIRECT]})
CID = r.json()["client_id"]
tk = ket_noi_moi()
trinh_duyet.post("/chatgpt/connector/settings", json={"bat": False})
check("9. TẮT tính năng -> token còn hạn cũng không vào được",
      mcp(tk["access_token"], "initialize").status_code == 404)
trinh_duyet.post("/chatgpt/connector/settings", json={"bat": True})
check("9. bật lại -> token cũ còn hạn dùng tiếp (tắt là đóng cửa, không phải thu hồi)",
      mcp(tk["access_token"], "initialize").status_code == 200)

_s = cfg.read_settings()
_s.pop("auth", None)
cfg.write_settings(_s)
check("9. chủ gỡ mật khẩu -> cửa tự đóng dù cờ vẫn bật",
      cc.cau_hinh()["bat"] is True and mcp(tk["access_token"], "initialize").status_code == 404)


# ============================================================
# 10) Đường công khai không được ngốn bộ nhớ
# ============================================================

_s = cfg.read_settings()
_s["auth"] = {"username": "admin", **dict(zip(("password_hash", "salt"),
                                              cfg.hash_password("matkhau123")))}
cfg.write_settings(_s)
_cid = cc.dang_ky_client({"redirect_uris": [REDIRECT]})[1]["client_id"]
for _i in range(cc.MAX_YEU_CAU * 3):
    cc.bat_dau_uy_quyen({"response_type": "code", "client_id": _cid, "redirect_uri": REDIRECT,
                         "code_challenge": "x" * 43, "code_challenge_method": "S256"})
check("10. mở trang Cho phép dồn dập -> số yêu cầu trong RAM có trần",
      len(cc._yeu_cau) <= cc.MAX_YEU_CAU, len(cc._yeu_cau))
_, _yc = cc.bat_dau_uy_quyen({"response_type": "code", "client_id": _cid, "redirect_uri": REDIRECT,
                              "code_challenge": "y" * 5000, "code_challenge_method": "S256"})
check("10. code_challenge dài bất thường bị cắt, không cất nguyên", len(_yc["challenge"]) <= 128)


# ============================================================
# 11) Chữ viết
# ============================================================

for _f in ("server/chatgpt_connector.py", "server/routes/chatgpt_connector.py",
           "tests/python/test_javis_trong_chatgpt.py"):
    _t = (ROOT / _f).read_text(encoding="utf-8")
    check(f"{_f} không dùng gạch dài (luật CLAUDE.md)", "\u2014" not in _t and "\u2013" not in _t)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_javis_trong_chatgpt: tất cả pass")
