"""Test bước ĐỔI CREDENTIAL trên UI (server/cred_exchange.py). Chạy tay / CI:

    python tests/run.py cred_exchange

Không cần pytest, KHÔNG chạm mạng (handler thật được thay bằng handler giả).

Bất biến quan trọng nhất được phủ ở đây: App Password NGƯỜI DÙNG NHẬP KHÔNG BAO GIỜ ĐƯỢC LƯU.
Nó chỉ dùng một lần để đổi lấy master token rồi bị xoá khỏi dữ liệu trước khi ghi xuống đĩa.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-credtest-"))

import cred_exchange  # noqa: E402
import mcp_catalog  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


CON = {
    "id": "thu-nghiem",
    "auth": {
        "fields": [
            {"key": "email", "env": "EMAIL"},
            {"key": "app_password", "optional": True},          # KHÔNG có env - chỉ là đầu vào
            {"key": "token", "env": "TOKEN", "optional": True},
        ],
        "exchange": {
            "handler": "gia_lap",
            "inputs": ["email", "app_password"],
            "output": "token",
            "drop": ["app_password"],
        },
    },
}

_goi = []


def _handler_gia(fields):
    _goi.append(dict(fields))
    # Input optional được run() thả qua -> handler PHẢI tự kiểm, giống handler Google thật.
    if not str(fields.get("app_password") or "").strip():
        return None, "Cần điền App Password."
    if fields.get("app_password") == "sai":
        return None, "Mật khẩu ứng dụng không đúng."
    return "TOKEN-MOI-" + fields.get("email", ""), ""


cred_exchange.HANDLERS["gia_lap"] = _handler_gia

# ---- đổi thành công ----
_goi.clear()
out, err = cred_exchange.run(CON, {"email": "a@gmail.com", "app_password": "dung", "token": ""})
check("đổi thành công -> không lỗi", err == "")
check("đổi thành công -> token được điền", out.get("token") == "TOKEN-MOI-a@gmail.com")
check("BẢO MẬT: app_password bị XOÁ khỏi dữ liệu lưu", "app_password" not in out)
check("email vẫn được giữ", out.get("email") == "a@gmail.com")
check("handler nhận đúng đầu vào", _goi and _goi[0].get("app_password") == "dung")

# ---- đổi thất bại ----
out2, err2 = cred_exchange.run(CON, {"email": "a@gmail.com", "app_password": "sai", "token": ""})
check("đổi thất bại -> có lỗi tiếng Việt", "không đúng" in (err2 or ""))
check("BẢO MẬT: đổi thất bại thì app_password VẪN bị xoá", "app_password" not in (out2 or {}))
check("đổi thất bại -> token vẫn rỗng", not (out2 or {}).get("token"))

# ---- đã có token sẵn thì BỎ QUA đổi (đường lui thủ công) ----
_goi.clear()
out3, err3 = cred_exchange.run(CON, {"email": "a@gmail.com", "app_password": "dung",
                                     "token": "aas_et/co-san"})
check("đã dán sẵn token -> KHÔNG gọi handler", not _goi)
check("đã dán sẵn token -> giữ nguyên token người dùng nhập",
      out3.get("token") == "aas_et/co-san")
check("BẢO MẬT: đã dán sẵn token thì app_password vẫn bị xoá", "app_password" not in out3)
check("đã dán sẵn token -> không lỗi", err3 == "")

# ---- thiếu đầu vào ----
_goi.clear()
out4a, err4a = cred_exchange.run(CON, {"email": "", "app_password": "x", "token": ""})
check("thiếu input BẮT BUỘC (email) -> báo Thiếu, KHÔNG gọi handler",
      "Thiếu" in (err4a or "") and len(_goi) == 0)
_goi.clear()
out4, err4 = cred_exchange.run(CON, {"email": "a@gmail.com", "app_password": "", "token": ""})
check("input TUỲ CHỌN bỏ trống -> VẪN tới handler (nó tự kiểm tổ hợp, vd pw HOẶC oauth_token)",
      len(_goi) == 1)
check("handler tự báo thiếu -> lỗi rõ vẫn tới người dùng", bool(err4))
check("BẢO MẬT: nhánh này app_password vẫn bị xoá", "app_password" not in (out4 or {}))

# ---- handler google_master_token THẬT: đường lui oauth_token (EmbeddedSetup) ----
# gpsoauth được import TRONG handler -> nhét module giả vào sys.modules là chặn được mạng.
import types  # noqa: E402

_calls = {}
_fake_gps = types.ModuleType("gpsoauth")


def _fake_master(email, pw, aid):
    _calls["master"] = (email, pw)
    return {"Error": "BadAuthentication"}


def _fake_exchange(email, tok, aid, **kw):
    _calls["exchange"] = (email, tok)
    return {"Token": "aas_et/tu-oauth-token"}


_fake_gps.perform_master_login = _fake_master
_fake_gps.exchange_token = _fake_exchange
_gps_that = sys.modules.get("gpsoauth")
sys.modules["gpsoauth"] = _fake_gps

_g = cred_exchange._google_master_token
_t1, _e1 = _g({"google_email": "a@x.vn", "app_password": "", "oauth_token": "oauth2_4/abc"})
check("oauth_token -> đổi qua exchange_token, ra master token",
      _t1 == "aas_et/tu-oauth-token" and _calls.get("exchange") == ("a@x.vn", "oauth2_4/abc"))
check("oauth_token -> KHÔNG đi đường App Password", "master" not in _calls)
_t2, _e2 = _g({"google_email": "a@x.vn", "app_password": "abcd efgh ijkl mnop", "oauth_token": ""})
check("App Password bị BadAuthentication -> lỗi chỉ sang đường lui oauth_token",
      _t2 is None and "oauth_token" in (_e2 or "") and "EmbeddedSetup" in (_e2 or ""))
_t3, _e3 = _g({"google_email": "a@x.vn", "app_password": "", "oauth_token": ""})
check("thiếu cả App Password lẫn oauth_token -> lỗi nói rõ cần một trong hai",
      _t3 is None and "App Password" in (_e3 or "") and "oauth_token" in (_e3 or ""))
if _gps_that is not None:
    sys.modules["gpsoauth"] = _gps_that
else:
    sys.modules.pop("gpsoauth", None)

# ---- connector không khai exchange thì đi qua không đổi gì ----
out5, err5 = cred_exchange.run({"id": "khac", "auth": {"fields": []}},
                               {"api_key": "abc"})
check("connector không khai exchange -> giữ nguyên dữ liệu", out5 == {"api_key": "abc"})
check("connector không khai exchange -> không lỗi", err5 == "")

# ---- handler lạ (catalog KHÔNG được chỉ định mã tuỳ ý) ----
CON_LA = {"id": "la", "auth": {"fields": [], "exchange": {
    "handler": "khong_ton_tai", "inputs": ["a"], "output": "b", "drop": []}}}
out6, err6 = cred_exchange.run(CON_LA, {"a": "x"})
check("handler không có trong registry -> báo lỗi, không nổ", bool(err6))

# ---- google-keep trong catalog thật phải khai đúng ----
keep = mcp_catalog.get("google-keep")
ex = ((keep or {}).get("auth") or {}).get("exchange") or {}
check("google-keep khai exchange", ex.get("handler") == "google_master_token")
check("google-keep đổi ra master_token", ex.get("output") == "master_token")
check("BẢO MẬT: google-keep khai drop app_password", "app_password" in (ex.get("drop") or []))

fields = {f["key"]: f for f in ((keep or {}).get("auth") or {}).get("fields") or []}
check("google-keep có ô app_password", "app_password" in fields)
check("BẢO MẬT: ô app_password KHÔNG map ra env (không thể lọt vào tiến trình con)",
      not fields.get("app_password", {}).get("env"))
check("ô app_password là tuỳ chọn (còn đường lui dán token tay)",
      bool(fields.get("app_password", {}).get("optional")))
check("ô master_token thành tuỳ chọn (vì đã có đường app password)",
      bool(fields.get("master_token", {}).get("optional")))

env = mcp_catalog.build_env(keep, {"google_email": "a@gmail.com", "app_password": "SIEU-BI-MAT",
                                   "master_token": "aas_et/x"})
check("BẢO MẬT: app_password KHÔNG xuất hiện trong env dù có bị truyền nhầm vào",
      "SIEU-BI-MAT" not in str(env))

# ---- ô oauth_token (đường lui khi Google từ chối App Password) ----
check("google-keep có ô oauth_token", "oauth_token" in fields)
check("ô oauth_token là tuỳ chọn", bool(fields.get("oauth_token", {}).get("optional")))
check("BẢO MẬT: ô oauth_token KHÔNG map ra env (dùng một lần rồi vứt)",
      not fields.get("oauth_token", {}).get("env"))
check("exchange nhận oauth_token làm input", "oauth_token" in (ex.get("inputs") or []))
check("BẢO MẬT: google-keep khai drop oauth_token", "oauth_token" in (ex.get("drop") or []))

# ---- nút mở trang App Password + trang lấy oauth_token của Google ----
links = (((keep or {}).get("auth") or {}).get("setup") or {}).get("links") or []
check("google-keep có nút mở trang tạo App Password",
      any("apppasswords" in (l.get("url") or "") for l in links))
check("google-keep có nút mở trang EmbeddedSetup lấy oauth_token",
      any("EmbeddedSetup" in (l.get("url") or "") for l in links))

# ---- ĐẦU-CUỐI: app_password có bao giờ chạm tới ĐĨA không? ----
# Đi đúng đường của endpoint /connect/add: cred_exchange.run -> mcp_store.add_connection,
# rồi đọc THẲNG file trên đĩa xem chuỗi bí mật có lọt ra không.
import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

import mcp_store  # noqa: E402

_BI_MAT = "ZZZbimatZZZ1234"          # 16 ký tự, dễ tìm trong file
cred_exchange.HANDLERS["google_master_token"] = lambda f: ("aas_et/gia-lap", "")
_fields, _err = cred_exchange.run(mcp_catalog.get("google-keep"), {
    "google_email": "a@gmail.com", "app_password": _BI_MAT, "master_token": "", "unsafe_mode": ""})
check("đầu-cuối: đổi không lỗi", _err == "")
check("đầu-cuối: master_token được điền từ handler", _fields.get("master_token") == "aas_et/gia-lap")

_cid, _e2 = mcp_store.add_connection("google-keep", {"label": "thử", "fields": _fields})
check("đầu-cuối: lưu được kết nối", bool(_cid) and not _e2)

_store = _Path(os.environ["JAVIS_STATE_DIR"]) / "mcp_servers.json"
_raw = _store.read_text(encoding="utf-8") if _store.exists() else ""
check("BẢO MẬT đầu-cuối: chuỗi App Password KHÔNG có trong file lưu trên đĩa",
      bool(_raw) and _BI_MAT not in _raw)

_conn = mcp_store.get_connection(_cid) or {}
check("BẢO MẬT đầu-cuối: không có khoá 'app_password' trong secrets đã lưu",
      "app_password" not in (_conn.get("secrets") or {}))

_res = next((c for c in mcp_store.resolved(enabled_only=False) if c["id"] == _cid), None)
check("BẢO MẬT đầu-cuối: app_password KHÔNG lọt vào env của tiến trình con",
      _res is not None and _BI_MAT not in str(_res.get("env") or {}))
check("đầu-cuối: master token ĐƯỢC truyền vào env cho keep-mcp",
      (_res or {}).get("env", {}).get("GOOGLE_MASTER_TOKEN") == "aas_et/gia-lap")

# ---- CANARY: chứng minh check 'app_password bị xoá' có quyền lực thật ----
CON_XAU = {"id": "xau", "auth": {"fields": [], "exchange": {
    "handler": "gia_lap", "inputs": ["email", "app_password"], "output": "token",
    "drop": []}}}          # CỐ Ý quên drop
out7, _ = cred_exchange.run(CON_XAU, {"email": "a@gmail.com", "app_password": "dung", "token": ""})
check("CANARY: cấu hình QUÊN drop thì app_password PHẢI còn lại -> tức check ở trên "
      "thật sự đang đo việc xoá, không phải luôn-xanh", "app_password" in out7)

# ---- Apify: gói facebook-monitor cũ chỉ có ô apify_token, chưa khai auth.exchange ----
# Handler vẫn phải kiểm token để một kết nối ảo không được lưu xanh với token sai.
_fake_httpx = types.ModuleType("httpx")
_apify_calls = []


class _ApifyResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def _apify_get(url, headers=None, timeout=None):
    _apify_calls.append((url, dict(headers or {}), timeout))
    return _ApifyResponse(200 if (headers or {}).get("Authorization") == "Bearer apify_api_good"
                          else 401)


_fake_httpx.get = _apify_get
_real_httpx = sys.modules.get("httpx")
sys.modules["httpx"] = _fake_httpx
try:
    valid, error = cred_exchange._apify_verify_token({"apify_token": "apify_api_good"})
    check("Apify: token đúng được trả nguyên vẹn", valid == "apify_api_good" and not error)
    check("Apify: gọi đúng endpoint bằng Bearer header",
          _apify_calls and _apify_calls[0][0] == "https://api.apify.com/v2/users/me"
          and _apify_calls[0][1].get("Authorization") == "Bearer apify_api_good")
    invalid, error = cred_exchange._apify_verify_token({"apify_token": "apify_api_bad"})
    check("Apify: token sai bị từ chối trước khi lưu", invalid is None and bool(error))
finally:
    if _real_httpx is None:
        sys.modules.pop("httpx", None)
    else:
        sys.modules["httpx"] = _real_httpx

facebook = {"id": "facebook-monitor", "auth": {"fields": [{"key": "apify_token"}]}}
_real_apify_handler = cred_exchange.HANDLERS.get("apify_verify_token")
cred_exchange.HANDLERS["apify_verify_token"] = lambda f: (
    (f["apify_token"], "") if f.get("apify_token") == "apify_api_good" else (None, "Token sai"))
try:
    out, error = cred_exchange.run(facebook, {"apify_token": "bad"})
    check("facebook-monitor: gói cũ vẫn chặn token sai", bool(error))
    out, error = cred_exchange.run(facebook, {"apify_token": "apify_api_good"})
    check("facebook-monitor: token đúng qua kiểm và được giữ", not error and out.get("apify_token") == "apify_api_good")
finally:
    if _real_apify_handler is None:
        cred_exchange.HANDLERS.pop("apify_verify_token", None)
    else:
        cred_exchange.HANDLERS["apify_verify_token"] = _real_apify_handler

# Connector có sẵn auth.exchange cũng phải kiểm output khi skip_if_output=False.
strict = {"id": "strict", "auth": {"fields": [{"key": "token"}], "exchange": {
    "handler": "strict_test", "inputs": ["token"], "output": "token", "skip_if_output": False}}}
cred_exchange.HANDLERS["strict_test"] = lambda f: (
    (f["token"], "") if f.get("token") == "good" else (None, "Token sai"))
out, error = cred_exchange.run(strict, {"token": "bad"})
check("skip_if_output=False: token đích sai vẫn bị từ chối", bool(error))
out, error = cred_exchange.run(strict, {"token": "good"})
check("skip_if_output=False: token đích đúng vẫn được giữ", not error and out.get("token") == "good")
cred_exchange.HANDLERS.pop("strict_test", None)

# ---- /connect/add: token sai không được chạm tới kho lưu ----
import asyncio as _asyncio  # noqa: E402
from unittest.mock import patch as _patch  # noqa: E402
import main as _main  # noqa: E402


class _ConnectRequest:
    async def json(self):
        return {"connector_id": "facebook-monitor", "fields": {"apify_token": "bad"}}


_saved = []
with _patch.object(_main.mcp_catalog, "get", lambda cid: facebook), \
     _patch.object(_main.mcp_store, "reuse_client_fields", lambda con, fields, reuse: fields), \
     _patch.object(_main.mcp_store, "add_connection", lambda *a: _saved.append(a)), \
     _patch.dict(cred_exchange.HANDLERS, {"apify_verify_token": lambda f: (None, "Token sai")}):
    _response = _asyncio.run(_main.connect_add(_ConnectRequest()))
check("/connect/add: token Apify sai bị từ chối trước khi ghi đĩa",
      _response.get("ok") is False and not _saved)

if _fails:
    print(f"\nFAIL - test_cred_exchange: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_cred_exchange: tất cả pass")
