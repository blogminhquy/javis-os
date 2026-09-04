"""Test luồng OAuth ChatGPT - tập trung phần BROWSER (Authorization Code + PKCE). Chạy tay / CI:

    python tests/run.py openai_oauth

Không chạm mạng: phần đổi token (_exchange) được mock. Kiểm PKCE, URL /oauth/authorize,
tách code từ URL callback dán lại, kiểm state, và redirect_uri đúng cho device vs browser.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import base64
import hashlib
import os
import sys
import tempfile
from urllib.parse import urlparse, parse_qs

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-oauthtest-")

import openai_oauth     # noqa: E402

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. PKCE đúng RFC 7636 ----
verifier, challenge = openai_oauth._gen_pkce()
check("verifier độ dài 43-128", 43 <= len(verifier) <= 128)
check("verifier không có padding '='", "=" not in verifier)
_expect = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
check("challenge = base64url(sha256(verifier))", challenge == _expect)
check("verifier ngẫu nhiên mỗi lần", openai_oauth._gen_pkce()[0] != verifier)

# ---- 2. start_browser dựng URL /oauth/authorize đủ tham số ----
d = openai_oauth.start_browser()
check("trả authorize_url", isinstance(d.get("authorize_url"), str) and d["authorize_url"].startswith(openai_oauth.OAUTH_AUTHORIZE_URL))
check("redirect_uri = loopback 1455", d.get("redirect_uri") == "http://localhost:1455/auth/callback")
q = parse_qs(urlparse(d["authorize_url"]).query)
check("response_type=code", q.get("response_type") == ["code"])
check("client_id đúng", q.get("client_id") == [openai_oauth.CLIENT_ID])
check("redirect_uri trong URL khớp", q.get("redirect_uri") == ["http://localhost:1455/auth/callback"])
check("code_challenge_method=S256", q.get("code_challenge_method") == ["S256"])
check("scope offline_access (có refresh)", "offline_access" in (q.get("scope") or [""])[0])
check("có state", bool((q.get("state") or [""])[0]))
# challenge trong URL khớp verifier đã lưu pending
_pv = openai_oauth._browser_pending["verifier"]
_pc = base64.urlsafe_b64encode(hashlib.sha256(_pv.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
check("challenge trong URL khớp verifier pending", q.get("code_challenge") == [_pc])
check("pending giữ state khớp URL", openai_oauth._browser_pending["state"] == q["state"][0])

# ---- 3. finish_browser: các nhánh lỗi (không chạm mạng) ----
openai_oauth._browser_pending.clear()
check("chưa start → lỗi", openai_oauth.finish_browser("http://x/?code=a")["status"] == "error")

openai_oauth.start_browser()
st = openai_oauth._browser_pending["state"]
check("callback rỗng → lỗi", openai_oauth.finish_browser("")["status"] == "error")
check("URL không có code → lỗi", openai_oauth.finish_browser("http://localhost:1455/auth/callback?state=" + st)["status"] == "error")
check("state sai → lỗi", openai_oauth.finish_browser("http://localhost:1455/auth/callback?code=C&state=WRONG")["status"] == "error")
check("OpenAI trả error → lỗi", openai_oauth.finish_browser("http://localhost:1455/auth/callback?error=access_denied")["status"] == "error")

# ---- 4. finish_browser: happy path (mock _exchange, để _save_tokens ghi settings temp) ----
_real_exchange = openai_oauth._exchange   # giữ bản thật để section 5 test lại
captured = {}


def fake_exchange(code, code_verifier, redirect_uri=None):
    captured.update(code=code, verifier=code_verifier, redirect_uri=redirect_uri)
    return {"access_token": "AT", "refresh_token": "RT", "id_token": "", "expires_in": 3600}


openai_oauth._exchange = fake_exchange
d2 = openai_oauth.start_browser()
st2 = openai_oauth._browser_pending["state"]
vf2 = openai_oauth._browser_pending["verifier"]
res = openai_oauth.finish_browser("http://localhost:1455/auth/callback?code=THECODE&state=" + st2)
check("happy path → connected", res.get("status") == "connected")
check("truyền đúng code cho _exchange", captured.get("code") == "THECODE")
check("truyền đúng verifier pending", captured.get("verifier") == vf2)
check("dùng redirect_uri browser (không phải deviceauth)", captured.get("redirect_uri") == "http://localhost:1455/auth/callback")
check("pending được dọn sau khi xong", not openai_oauth._browser_pending)
check("token đã lưu vào settings", openai_oauth.status().get("connected") is True)
# dán thẳng code trần (không phải URL) cũng chạy
openai_oauth.disconnect()
openai_oauth.start_browser()
res2 = openai_oauth.finish_browser("BAREPKCECODE")
check("dán code trần → connected", res2.get("status") == "connected" and captured.get("code") == "BAREPKCECODE")

# ---- 5. _exchange dùng đúng redirect_uri (device mặc định vs browser) ----
grab = {}


class _Resp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"access_token": "x"}


def fake_post(url, data=None, headers=None, timeout=None):
    grab.clear()
    grab.update(url=url, data=data)
    return _Resp()


openai_oauth._exchange = _real_exchange   # khôi phục bản thật (section 4 đã mock)
openai_oauth.httpx.post = fake_post
openai_oauth._exchange("C", "V")
check("device mặc định → redirect deviceauth", grab["data"]["redirect_uri"] == openai_oauth.REDIRECT_URI)
openai_oauth._exchange("C", "V", redirect_uri=openai_oauth.BROWSER_REDIRECT_URI)
check("browser → redirect loopback 1455", grab["data"]["redirect_uri"] == "http://localhost:1455/auth/callback")

# ============================================================
# start_device: đầu này của OpenAI hay chậm, phải THỬ LẠI
# ============================================================
# Người dùng báo 04/09: "login Codex khó ghê, quay vòng vòng đợi rất lâu, hên xui lắm mới hiện
# ra code". Bản cũ gọi ĐÚNG MỘT LẦN với hạn 20 giây, trượt một nhịp là hỏng cả lượt đăng nhập.
# Thử lại ở đây an toàn vì mỗi lần chỉ XIN một mã thiết bị mới, chưa gắn tài khoản nào.
import httpx        # noqa: E402
import time as _t   # noqa: E402


class _Rep:
    def __init__(self, code=200, data=None):
        self.status_code, self._d = code, data or {}
        self.text = "loi"

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("loi", request=None, response=self)


def _thu(chuoi):
    """Chạy start_device với một chuỗi phản hồi giả. Trả (kết quả hoặc lỗi, số lần gọi)."""
    dem = {"n": 0}
    goc_post, goc_sleep = httpx.post, _t.sleep

    def post_gia(*a, **k):
        i = dem["n"]
        dem["n"] += 1
        v = chuoi[i] if i < len(chuoi) else chuoi[-1]
        if isinstance(v, Exception):
            raise v
        return v

    try:
        httpx.post = post_gia
        _t.sleep = lambda s: None      # không ngồi chờ thật trong test
        try:
            return start_ok(), dem["n"]
        except Exception as e:
            return e, dem["n"]
    finally:
        httpx.post, _t.sleep = goc_post, goc_sleep


def start_ok():
    return openai_oauth.start_device()


TOT = _Rep(200, {"device_auth_id": "d1", "user_code": "ABCD-1234", "interval": 5})

ra, n = _thu([TOT])
check("lần đầu đã tốt thì gọi đúng một lần", n == 1 and isinstance(ra, dict))
check("và trả về mã cho người dùng đọc", isinstance(ra, dict) and ra.get("user_code") == "ABCD-1234")

ra, n = _thu([httpx.TimeoutException("qua han"), TOT])
check("hết hạn một nhịp thì THỬ LẠI chứ không bỏ cuộc", n == 2 and isinstance(ra, dict))

ra, n = _thu([_Rep(503), TOT])
check("OpenAI lỗi 5xx cũng thử lại", n == 2 and isinstance(ra, dict))

ra, n = _thu([httpx.TimeoutException("qua han")])
check("hết hạn cả ba lần thì dừng, không thử mãi", n == 3)
# Câu lỗi phải nói ĐÚNG nguyên nhân: "đợi quá lâu" và "OpenAI từ chối" cần hai cách xử lý khác
# nhau, gộp thành một tên ngoại lệ thì người dùng không biết nên thử lại hay đi kiểm tra mạng.
check("và nói rõ là bên kia không trả lời kịp",
      isinstance(ra, Exception) and "không trả lời kịp" in str(ra))

ra, n = _thu([_Rep(400)])
check("lỗi 4xx là lỗi thật, KHÔNG thử lại vô ích", n == 1)
check("và nói rõ OpenAI từ chối", isinstance(ra, Exception) and "từ chối" in str(ra))

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_openai_oauth: tất cả pass")
