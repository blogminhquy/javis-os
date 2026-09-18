"""
Đăng nhập ChatGPT (OpenAI) bằng OAuth - dùng gói ChatGPT Plus/Pro thay cho API key.
Hỗ trợ HAI cách, cùng client_id + cùng endpoint đổi token của openai/codex:

A) Device-code (mặc định, hợp VPS headless): spec pin từ source chính thức openai/codex
   (device_code_auth.rs, token_data.rs, server.rs) + plugin tumf/opencode-openai-device-auth.
   1. POST /api/accounts/deviceauth/usercode {client_id} -> {device_auth_id, user_code, interval}
      User mở https://auth.openai.com/codex/device, nhập user_code.
   2. Poll POST /api/accounts/deviceauth/token {device_auth_id, user_code}
        403/404 = đang chờ; 200 -> {authorization_code, code_verifier}
   3. Đổi: POST /oauth/token grant_type=authorization_code + redirect_uri deviceauth/callback.

B) Browser OAuth (Authorization Code + PKCE) - CHO WORKSPACE CHẶN device-code. Đúng luồng
   `codex login` mặc định: mở /oauth/authorize trên trình duyệt, đăng nhập, OpenAI redirect
   kèm ?code=...&state=... về http://localhost:1455/auth/callback. Vì Javis có thể chạy trên
   VPS (trình duyệt ở máy user, không tới được server), ta dùng kiểu "dán lại URL callback":
   user copy URL redirect (dù trang localhost không tải được) rồi dán vào, server tách code +
   đổi token. Không cần server tự bind cổng localhost nên chạy được cả local lẫn headless.

  account_id = claim id_token["https://api.openai.com/auth"]["chatgpt_account_id"]

⚠️ Không chính thức cho app ngoài Codex - token chạy backend Codex (model gpt-5-codex),
có thể vỡ khi OpenAI đổi. Token lưu trong settings.json (gitignored).

LUẬT MỘT NGUỒN SỰ THẬT (0.59.34). `~/.codex/auth.json` do CHÍNH Codex CLI giữ, và Codex tự
xoay refresh_token khi cần. OpenAI HUỶ refresh_token cũ ngay khi nó được dùng, nên hai bên
cùng ôm một mã là bên xoay sau cầm mã đã chết. Bản trước để Javis ghi đè file đó vô điều
kiện ở MỖI lượt chat và tự refresh bằng bản sao trong settings.json, nên phân kỳ là chuyện
sớm muộn: Javis refresh hỏng, `valid_creds` trả lại token hết hạn, rồi cặp token chết đó
được ghi đè lên bộ đang tốt của Codex - cả hai bên cùng phải đăng nhập lại. Đúng câu lỗi
"your refresh token was already used" của vụ 30/07 (xem 0.9.x và test_connect_health).

Nay: ĐỌC đĩa trước khi ghi. Mã trên đĩa mới hơn thì KÉO VỀ chứ không đè; đĩa là tài khoản
khác (máy tự `codex login`) thì KHÔNG đụng vào; refresh hỏng thì KHÔNG ghi gì cả. Javis vẫn
tự refresh khi nó là bên duy nhất giữ mã, vì tạo ảnh và giọng nói cũng ăn token này và
không đi qua Codex CLI.
"""
import os
import time
import json
import base64
import hashlib
import secrets
import httpx
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import config as cfgmod
import codex_models

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTH_BASE = "https://auth.openai.com"
DEVICE_USERCODE_URL = AUTH_BASE + "/api/accounts/deviceauth/usercode"
DEVICE_TOKEN_URL = AUTH_BASE + "/api/accounts/deviceauth/token"
OAUTH_TOKEN_URL = AUTH_BASE + "/oauth/token"
OAUTH_AUTHORIZE_URL = AUTH_BASE + "/oauth/authorize"
REDIRECT_URI = AUTH_BASE + "/deviceauth/callback"
# Redirect của luồng browser: PHẢI khớp đúng cái codex CLI đăng ký (loopback cổng 1455) thì
# OpenAI mới chấp nhận. Ta không thật sự bind cổng này - chỉ để user dán lại URL redirect.
BROWSER_REDIRECT_URI = "http://localhost:1455/auth/callback"
BROWSER_SCOPE = "openid profile email offline_access"
VERIFY_URL = AUTH_BASE + "/codex/device"
UA = "javis-os/0.3 (+device-auth)"

# Phiên device đang chờ (1 admin nên giữ in-memory là đủ).
_pending = {}
# Phiên browser-OAuth đang chờ (giữ code_verifier + state giữa lúc start và lúc dán URL về).
_browser_pending = {}


def _empty():
    return {"access_token": "", "refresh_token": "", "id_token": "", "account_id": "", "plan": "", "expires_at": 0}


def _decode_jwt_claims(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")))
    except Exception:
        return {}


def _codex_auth_path():
    """Nơi Codex CLI thật sự giữ phiên. Tôn trọng CODEX_HOME vì chính Codex đọc biến đó."""
    home = os.getenv("CODEX_HOME")
    return (Path(home) if home else Path.home() / ".codex") / "auth.json"


def doc_codex_auth():
    """Bộ token Codex CLI đang giữ trên đĩa. {} nếu chưa có, đọc không được, hoặc file hỏng."""
    try:
        d = json.loads(_codex_auth_path().read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(d, dict):
        return {}
    t = d.get("tokens")
    return t if isinstance(t, dict) else {}


def _han_cua(access_token):
    """Mốc hết hạn của một access token nhặt từ đĩa: đọc claim `exp` của chính JWT đó.

    Không đọc được thì tin DÈ DẶT (5 phút). Đoán dài quá là lượt sau Javis gọi API bằng token
    đã chết rồi tưởng mình bị mất phiên; đoán ngắn chỉ tốn thêm một lần refresh.
    """
    try:
        exp = _decode_jwt_claims(access_token or "").get("exp")
        if exp:
            return float(exp) - 60
    except Exception:
        pass
    return time.time() + 300


def _cung_tai_khoan(dtok, o):
    """Bộ token trên đĩa có cùng tài khoản với bộ Javis đang giữ không?

    Máy có thể đã tự `codex login` bằng tài khoản KHÁC. Bộ đó không phải của Javis: không kéo
    về, và tuyệt đối không ghi đè lên. Bên nào không khai tài khoản thì coi như khớp, giữ
    nguyên hành vi cũ cho đường thường (file do chính Javis ghi luôn có account_id).
    """
    a = (dtok.get("account_id") or "").strip()
    b = (o.get("account_id") or "").strip()
    return not a or not b or a == b


def _la_token_cua_javis(dtok, o):
    """File trên đĩa có đúng là bộ token Javis đã bắc cầu sang không?

    Phải khớp DƯƠNG ít nhất một trường. Chưa từng kết nối (o rỗng) thì không trường nào khớp
    nên trả False - đó là điều ta muốn, vì lúc ấy file kia là phiên người dùng tự tạo.
    """
    for k in ("refresh_token", "access_token", "account_id"):
        a = (dtok.get(k) or "").strip()
        b = (o.get(k) or "").strip()
        if a and b and a == b:
            return True
    return False


def _nhan_token_tu_codex(dtok):
    """Codex CLI vừa tự xoay refresh_token: kéo bộ MỚI của nó về settings.json.

    Đây là nửa còn lại của luật một nguồn sự thật. Không kéo về thì bản sao trong settings
    vĩnh viễn là mã đã chết, và mọi lượt sau đều đi lại đúng vòng hỏng của vụ 30/07.
    """
    cfg = cfgmod.read_settings()
    cur = cfg["model"].get("openai_oauth") or {}
    at = (dtok.get("access_token") or "").strip()
    id_token = (dtok.get("id_token") or "").strip() or cur.get("id_token", "")
    auth = _decode_jwt_claims(id_token).get("https://api.openai.com/auth") or {}
    cfg["model"]["openai_oauth"] = {
        "access_token": at,
        "refresh_token": (dtok.get("refresh_token") or "").strip() or cur.get("refresh_token", ""),
        "id_token": id_token,
        "account_id": ((dtok.get("account_id") or "").strip()
                       or auth.get("chatgpt_account_id", "") or cur.get("account_id", "")),
        "plan": auth.get("chatgpt_plan_type", "") or cur.get("plan", ""),
        "expires_at": _han_cua(at),
    }
    cfgmod.write_settings(cfg)
    return cfg["model"]["openai_oauth"]


def _save_tokens(tok):
    """Ghi token vào settings.json (giữ refresh_token cũ nếu lần refresh không trả cái mới)."""
    cfg = cfgmod.read_settings()
    cur = cfg["model"].get("openai_oauth") or {}
    id_token = tok.get("id_token", "") or cur.get("id_token", "")
    claims = _decode_jwt_claims(id_token)
    auth = claims.get("https://api.openai.com/auth") or {}
    expires_in = int(tok.get("expires_in") or 3600)
    cfg["model"]["openai_oauth"] = {
        "access_token": tok.get("access_token", ""),
        "refresh_token": tok.get("refresh_token", "") or cur.get("refresh_token", ""),
        "id_token": id_token,
        "account_id": auth.get("chatgpt_account_id", "") or cur.get("account_id", ""),
        "plan": auth.get("chatgpt_plan_type", "") or cur.get("plan", ""),
        "expires_at": time.time() + expires_in - 60,
    }
    cfgmod.write_settings(cfg)


def _exchange(code, code_verifier, redirect_uri=REDIRECT_URI):
    r = httpx.post(OAUTH_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": CLIENT_ID,
        "code_verifier": code_verifier,
    }, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json()


def start_device():
    """Bước 1: lấy user_code + verification_uri. Trả cho frontend hiển thị.

    THỬ LẠI vài lần, vì đầu này của OpenAI hay chậm và thỉnh thoảng không trả lời. Bản cũ gọi
    đúng một lần với hạn 20 giây: trượt một nhịp là người dùng nhìn vòng xoay rồi nhận một câu
    lỗi kỹ thuật, đúng cảnh người dùng tả ngày 04/09 - "quay vòng vòng đợi rất lâu, hên xui lắm
    mới hiện ra code".

    Thử lại ở đây an toàn: mỗi lần chỉ XIN một mã thiết bị mới, chưa gắn với tài khoản nào và
    chưa có tác dụng phụ gì. Mã cũ bị bỏ rơi thì tự hết hạn.

    Lỗi cuối cùng nói ĐÚNG nguyên nhân. "Đợi quá lâu" và "OpenAI trả lỗi" là hai chuyện khác
    nhau, và gộp cả hai vào một tên ngoại lệ thì người dùng không biết nên thử lại hay đi kiểm
    tra mạng."""
    cuoi = None
    for lan in range(3):
        try:
            r = httpx.post(DEVICE_USERCODE_URL, json={"client_id": CLIENT_ID},
                           headers={"Content-Type": "application/json",
                                    "Accept": "application/json", "User-Agent": UA},
                           timeout=30)
            if r.status_code >= 500:
                cuoi = RuntimeError(f"OpenAI đang lỗi phía họ ({r.status_code}). Thử lại sau ít phút.")
            else:
                r.raise_for_status()
                break
        except httpx.TimeoutException:
            cuoi = TimeoutError("OpenAI không trả lời kịp. Mạng chậm hoặc phía họ đang quá tải, "
                                "bấm Đăng nhập lần nữa.")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"OpenAI từ chối yêu cầu ({e.response.status_code}): "
                               f"{e.response.text[:200]}") from e
        if lan < 2:
            time.sleep(1.5 * (lan + 1))   # lùi dần, tổng cộng chờ thêm tối đa 4.5 giây
    else:
        raise cuoi or RuntimeError("Không xin được mã đăng nhập từ OpenAI.")
    d = r.json()
    dev = d.get("device_auth_id") or d.get("deviceAuthId")
    uc = d.get("user_code") or d.get("usercode") or d.get("userCode")
    interval = int(d.get("interval") or 5)
    _pending.clear()
    _pending.update({"device_auth_id": dev, "user_code": uc, "interval": interval, "ts": time.time()})
    return {"user_code": uc, "verification_uri": VERIFY_URL, "interval": interval, "expires_in": 900}


def poll():
    """Bước 2-3: poll 1 lần. Trả pending | connected | error."""
    if not _pending:
        return {"status": "error", "error": "Chưa bắt đầu đăng nhập."}
    if time.time() - _pending["ts"] > 15 * 60:
        _pending.clear()
        return {"status": "error", "error": "Mã hết hạn (15 phút), thử lại."}
    try:
        r = httpx.post(DEVICE_TOKEN_URL, json={"device_auth_id": _pending["device_auth_id"], "user_code": _pending["user_code"]},
                       headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA}, timeout=20)
    except Exception as e:
        return {"status": "pending", "note": f"{type(e).__name__}"}
    if r.status_code in (403, 404):
        return {"status": "pending"}
    if r.status_code != 200:
        return {"status": "error", "error": f"{r.status_code}: {r.text[:200]}"}
    d = r.json()
    code = d.get("authorization_code")
    verifier = d.get("code_verifier")
    if not code or not verifier:
        return {"status": "pending"}
    try:
        _save_tokens(_exchange(code, verifier))
    except Exception as e:
        return {"status": "error", "error": f"Đổi token lỗi: {type(e).__name__}: {e}"}
    _pending.clear()
    o = cfgmod.read_settings()["model"].get("openai_oauth") or {}
    return {"status": "connected", "account_id": o.get("account_id", ""), "plan": o.get("plan", "")}


# ---- Luồng B: Browser OAuth (Authorization Code + PKCE) ----

def _gen_pkce():
    """(code_verifier, code_challenge) theo RFC 7636 - challenge = base64url(sha256(verifier))."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


def start_browser():
    """Bước 1 luồng browser: dựng URL /oauth/authorize (khớp đúng codex CLI) + giữ verifier/state.
    Trả {authorize_url, redirect_uri} cho frontend mở trình duyệt."""
    verifier, challenge = _gen_pkce()
    state = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": BROWSER_REDIRECT_URI,
        "scope": BROWSER_SCOPE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "state": state,
        "originator": "codex_cli_rs",
    }
    _browser_pending.clear()
    _browser_pending.update({"verifier": verifier, "state": state, "ts": time.time()})
    return {"authorize_url": OAUTH_AUTHORIZE_URL + "?" + urlencode(params), "redirect_uri": BROWSER_REDIRECT_URI}


def finish_browser(callback):
    """Bước 2-3 luồng browser: nhận URL callback user dán về (hoặc chính chuỗi code), tách code,
    kiểm state, đổi lấy token. Trả pending-free: connected | error."""
    if not _browser_pending:
        return {"status": "error", "error": "Chưa bắt đầu đăng nhập bằng trình duyệt."}
    if time.time() - _browser_pending["ts"] > 15 * 60:
        _browser_pending.clear()
        return {"status": "error", "error": "Phiên hết hạn (15 phút), thử lại."}
    raw = (callback or "").strip()
    if not raw:
        return {"status": "error", "error": "Chưa dán đường dẫn callback."}
    code = None
    state = None
    if raw.startswith("http://") or raw.startswith("https://"):
        q = parse_qs(urlparse(raw).query)
        code = (q.get("code") or [None])[0]
        state = (q.get("state") or [None])[0]
        err = (q.get("error") or [None])[0]
        if err:
            return {"status": "error", "error": f"OpenAI trả lỗi: {err}"}
    else:
        code = raw   # user dán thẳng mã code
    if not code:
        return {"status": "error", "error": "Không tìm thấy 'code' trong đường dẫn dán vào."}
    if state and state != _browser_pending.get("state"):
        return {"status": "error", "error": "State không khớp - đăng nhập lại cho chắc."}
    try:
        _save_tokens(_exchange(code, _browser_pending["verifier"], redirect_uri=BROWSER_REDIRECT_URI))
    except Exception as e:
        return {"status": "error", "error": f"Đổi token lỗi: {type(e).__name__}: {e}"}
    _browser_pending.clear()
    o = cfgmod.read_settings()["model"].get("openai_oauth") or {}
    return {"status": "connected", "account_id": o.get("account_id", ""), "plan": o.get("plan", "")}


def valid_creds():
    """(access_token, account_id) hợp lệ - tự refresh nếu hết hạn. None nếu chưa kết nối.

    Kèm cờ ``stale=True`` khi refresh HỎNG và ta đành trả lại token cũ. Nơi gọi dùng cờ đó để
    KHÔNG ghi bộ token đã chết đè lên ~/.codex/auth.json. Thiếu cờ này thì một lần refresh
    trượt là Javis tự tay bẻ luôn phiên Codex CLI đang tốt trên máy.
    """
    o = cfgmod.read_settings()["model"].get("openai_oauth") or {}
    if not o.get("access_token") and not o.get("refresh_token"):
        return None
    if o.get("access_token") and time.time() < (o.get("expires_at") or 0):
        return {"access_token": o["access_token"], "account_id": o.get("account_id", "")}
    # Hết hạn. TRƯỚC khi tự refresh, xem Codex CLI đã xoay giúp chưa: mã trên đĩa khác mã
    # trong tay ta nghĩa là nó xoay rồi, và OpenAI đã huỷ mã của ta ngay lúc đó. Refresh bằng
    # mã chết vừa chắc chắn hỏng, vừa đẩy ta vào nhánh `stale` một cách vô cớ.
    dtok = doc_codex_auth()
    drt = (dtok.get("refresh_token") or "").strip()
    if drt and drt != (o.get("refresh_token") or "").strip() and _cung_tai_khoan(dtok, o):
        o = _nhan_token_tu_codex(dtok)
        if o.get("access_token") and time.time() < (o.get("expires_at") or 0):
            return {"access_token": o["access_token"], "account_id": o.get("account_id", "")}
    rt = o.get("refresh_token")
    if rt:
        try:
            r = httpx.post(OAUTH_TOKEN_URL, data={
                "grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": rt,
            }, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA}, timeout=30)
            r.raise_for_status()
            _save_tokens(r.json())
            o = cfgmod.read_settings()["model"]["openai_oauth"]
            return {"access_token": o["access_token"], "account_id": o.get("account_id", "")}
        except Exception:
            pass
    if o.get("access_token"):
        return {"access_token": o["access_token"], "account_id": o.get("account_id", ""), "stale": True}
    return None


def write_codex_auth():
    """Đồng bộ token ChatGPT giữa settings.json và ~/.codex/auth.json. Gọi mỗi lượt chat.

    Device-code dùng CÙNG client_id với codex → token tương thích → KHỎI phải chạy `codex login`
    riêng (login đó khó trên VPS headless). Nhưng bắc cầu KHÔNG còn nghĩa là ghi đè: bản trước
    ghi đè vô điều kiện và chưa bao giờ đọc file đang có, nên nó giẫm lên cả phiên `codex login`
    người dùng tự tạo lẫn bộ token Codex vừa xoay. Xem luật một nguồn sự thật ở đầu file.

    Bốn nhánh, theo thứ tự:
      - đĩa là tài khoản KHÁC          → không đụng, trả False
      - đĩa có mã MỚI HƠN              → kéo về settings, không ghi, trả True
      - token trong tay đã chết (stale)→ không ghi, trả False
      - còn lại                        → ghi như cũ
    """
    o = cfgmod.read_settings()["model"].get("openai_oauth") or {}
    if not (o.get("access_token") or o.get("refresh_token")):
        return False          # Javis chưa kết nối: phiên trên đĩa là của máy, không đụng vào
    dtok = doc_codex_auth()
    drt = (dtok.get("refresh_token") or "").strip()
    if drt:
        if not _cung_tai_khoan(dtok, o):
            return False
        if drt != (o.get("refresh_token") or "").strip():
            _nhan_token_tu_codex(dtok)
            return True
    creds = valid_creds()
    if not creds or not creds.get("access_token") or creds.get("stale"):
        return False
    o = cfgmod.read_settings()["model"].get("openai_oauth") or {}
    try:
        path = _codex_auth_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "OPENAI_API_KEY": None,
            "tokens": {
                "id_token": o.get("id_token", ""),
                "access_token": creds["access_token"],
                "refresh_token": o.get("refresh_token", ""),
                "account_id": creds.get("account_id", ""),
            },
            "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }), encoding="utf-8")
        return True
    except Exception:
        return False


def _list_models_backend(creds):
    """Nguồn dự phòng cho Codex CLI cũ chưa có app-server ``model/list``."""
    if not creds or not creds.get("access_token"):
        return None
    headers = {
        "Authorization": f"Bearer {creds['access_token']}",
        "chatgpt-account-id": creds.get("account_id", ""),
        "originator": "codex_cli_rs",
        "User-Agent": UA,
        "Accept": "application/json",
    }
    if not creds.get("account_id"):
        headers.pop("chatgpt-account-id", None)
    # CHỈ endpoint codex: trả đúng model chạy được qua Codex. KHÔNG fallback /backend-api/models
    # (nó trả cả model ChatGPT chung như gpt-5-mini/gpt-4o - Codex account từ chối → picker chào sai).
    # Endpoint codex hỏng → return None → caller dùng catalog curated (đã đúng).
    for url in ("https://chatgpt.com/backend-api/codex/models",):
        try:
            r = httpx.get(url, headers=headers, timeout=20)
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception:
            continue
        items = data.get("models") if isinstance(data, dict) else None
        if items is None and isinstance(data, dict):
            items = data.get("data")
        if items is None and isinstance(data, list):
            items = data
        if not items:
            continue
        ids = []
        for it in items:
            if isinstance(it, str):
                mid = it
            elif isinstance(it, dict):
                mid = it.get("id") or it.get("slug") or it.get("model") or it.get("name")
            else:
                mid = None
            if mid and not str(mid).endswith("-pro"):
                ids.append(str(mid))
        if ids:
            return ids
    return None


def list_models(creds):
    """Lấy model LIVE từ chính Codex, không ghim version model trong Javis.

    Nguồn chính là ``codex app-server`` / ``model/list``: cùng catalog và cùng
    quyền account mà model picker chính thức của Codex dùng. Endpoint backend
    trực tiếp chỉ còn là đường tương thích cho Codex CLI cũ.
    """
    if not creds or not creds.get("access_token"):
        return None
    # Javis có luồng OAuth riêng; bắc cầu token sang kho Codex trước để
    # app-server nhìn đúng account ngay cả khi user chưa từng chạy `codex login`.
    write_codex_auth()
    live = codex_models.list_models()
    if live and live.get("models"):
        return live["models"]
    return _list_models_backend(creds)


def disconnect():
    cfg = cfgmod.read_settings()
    o = cfg["model"].get("openai_oauth") or {}
    # Dọn luôn bộ token đã bắc cầu sang Codex, không thì "Ngắt kết nối" chỉ xoá nửa trong
    # settings còn file trên đĩa vẫn đăng nhập - `codex exec` chạy tiếp bằng tài khoản người
    # dùng tưởng đã ngắt. CHỈ xoá khi file đúng là của phiên này: máy có thể đã `codex login`
    # riêng, và xoá nhầm là người dùng mất phiên họ tự tạo mà Javis không dựng lại được.
    dtok = doc_codex_auth()
    if dtok and _la_token_cua_javis(dtok, o):
        try:
            _codex_auth_path().unlink()
        except Exception:
            pass
    cfg["model"]["openai_oauth"] = _empty()
    cfgmod.write_settings(cfg)
    _pending.clear()
    _browser_pending.clear()


def status():
    o = cfgmod.read_settings()["model"].get("openai_oauth") or {}
    return {"connected": bool(o.get("access_token") or o.get("refresh_token")),
            "account_id": o.get("account_id", ""), "plan": o.get("plan", "")}
