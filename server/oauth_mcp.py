"""
OAuth 2.1 cho remote MCP server (chuẩn MCP Authorization) - Javis TỰ giữ token,
mọi engine dùng chung, KHÔNG cần mở terminal gõ /mcp như trước.
Luồng: discovery (RFC 9728 / .well-known) → DCR (RFC 7591, nếu server hỗ trợ)
→ authorize PKCE S256 → callback → token → tự refresh.

Store: STATE_DIR/.oauth_mcp.json - token mã hoá qua secrets_store.
Không import mcp_client/mcp_hub (tránh vòng import).
"""
import base64
import hashlib
import json
import secrets as _secrets
import sys
import time
import urllib.parse

import httpx

import mcp_store
import secrets_store
from config import STATE_DIR

_STORE_PATH = STATE_DIR / ".oauth_mcp.json"
_pending = {}    # state -> {conn_id, verifier, token_endpoint, client_id, redirect_uri, ts}
_PENDING_TTL = 600


def _load():
    try:
        if _STORE_PATH.exists():
            return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(d):
    _STORE_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _conn(conn_id):
    return next((c for c in mcp_store.resolved(enabled_only=False) if c["id"] == conn_id), None)


# ─────────────────────── Scope đã được cấp (chống "xanh mà thiếu quyền") ───────────────────────
# Vì sao tồn tại: Google cấp token theo TỪNG scope, và mỗi tool của server MCP chỉ nhận một
# danh sách scope nhất định. Token thiếu một scope vẫn đăng nhập xanh, tools/list vẫn chạy,
# validate cũng có thể xanh (list_calendars chỉ cần scope danh sách lịch) - nhưng đúng tool cần
# scope đó thì Google trả ACCESS_TOKEN_SCOPE_INSUFFICIENT. Trước đây Javis không lưu scope thật
# nên không phân biệt nổi "chưa đăng nhập" với "đăng nhập rồi mà thiếu quyền", và người dùng xoá
# đi cài lại mãi vẫn dính vì bản thân danh sách scope Javis xin mới là chỗ sai.
_SCOPE_ALIAS = {   # xin bằng tên ngắn, Google trả về dạng URL đầy đủ
    "email": "https://www.googleapis.com/auth/userinfo.email",
    "profile": "https://www.googleapis.com/auth/userinfo.profile",
}
_IDENTITY_SCOPES = {"openid", "https://www.googleapis.com/auth/userinfo.email",
                    "https://www.googleapis.com/auth/userinfo.profile"}


def _norm_scope(s):
    s = (s or "").strip()
    return _SCOPE_ALIAS.get(s, s)


def required_scopes(conn_id):
    """Scope catalog đang xin cho connection này (đã chuẩn hoá tên)."""
    conn = _conn(conn_id) or {}
    auth = (conn.get("connector") or {}).get("auth") or {}
    return [_norm_scope(s) for s in (auth.get("scopes") or []) if str(s).strip()]


def granted_scopes(conn_id):
    """Scope nhà cung cấp THẬT SỰ cấp, đọc từ token response. [] nghĩa là CHƯA BIẾT
    (token lưu trước bản này, hoặc nhà cung cấp không trả trường scope - vd Meta)."""
    ent = _load().get(conn_id) or {}
    return [_norm_scope(s) for s in str(ent.get("scopes") or "").split() if s.strip()]


def scope_report(conn_id):
    """{known, granted, required, missing}. missing = scope catalog xin mà token không có.
    known=False → missing RỖNG: không biết thì không đoán bừa là thiếu (thà bỏ sót còn hơn
    bắt user đăng nhập lại vô cớ). Scope định danh (openid/email) không tính vào missing vì
    chúng chỉ để lấy tên tài khoản, không tool nào chết vì thiếu chúng."""
    granted = granted_scopes(conn_id)
    required = required_scopes(conn_id)
    if not granted:
        return {"known": False, "granted": [], "required": required, "missing": []}
    have = set(granted)
    return {"known": True, "granted": granted, "required": required,
            "missing": [s for s in required if s not in have and s not in _IDENTITY_SCOPES]}


def short_scopes(scopes):
    """Rút gọn scope cho thông báo người đọc: bỏ tiền tố googleapis dài ngoằng."""
    return [str(s).replace("https://www.googleapis.com/auth/", "") for s in (scopes or [])]


# ─────────────────────── Facebook / Meta (BYO app → Graph API) ───────────────────────
# Meta KHÁC OAuth chuẩn: (1) đổi code→token bằng GET (không grant_type), client_secret BẮT BUỘC,
# KHÔNG PKCE ở luồng classic; (2) KHÔNG cấp refresh_token - token dài hạn ~60 ngày lấy bằng
# grant_type=fb_exchange_token; (3) miễn HTTP chỉ cho host 'localhost' (không phải 127.0.0.1).
def _meta_localhost(uri):
    """Ép host redirect về 'localhost' (Meta chỉ miễn HTTP cho localhost, chặn 127.0.0.1)."""
    return (uri or "").replace("://127.0.0.1", "://localhost")


def _meta_token_error(tk, redirect_uri=""):
    e = (tk or {}).get("error") or {}
    msg = e.get("message") or (json.dumps(tk, ensure_ascii=False)[:200] if tk else "không rõ")
    rd = redirect_uri or "http://localhost:7777/connect/oauth/callback"
    return (f"Facebook từ chối: {msg}. Kiểm tra: (1) 'Valid OAuth Redirect URIs' trong app khớp CHÍNH XÁC "
            f"{rd} (dùng 'localhost' KHÔNG phải 127.0.0.1); (2) App đang ở Development Mode và bạn là "
            f"Admin/Developer/Tester của app; (3) App ID + App Secret dán đúng.")


async def _meta_longlive(token_endpoint, client_id, client_secret, token):
    """Đổi token ngắn hạn (~1-2h) → dài hạn (~60 ngày) qua fb_exchange_token. Trả dict token hoặc None."""
    if not (token_endpoint and client_id and client_secret and token):
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(token_endpoint, params={
                "grant_type": "fb_exchange_token", "client_id": client_id,
                "client_secret": client_secret, "fb_exchange_token": token})
        d = r.json()
        return d if isinstance(d, dict) and d.get("access_token") else None
    except Exception as e:
        print(f"[oauth meta longlive] {e}", file=sys.stderr)
        return None


async def _discover(url):
    """Tìm authorization server metadata cho 1 MCP url. Trả dict metadata hoặc None."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        issuer = None
        try:
            r = await client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                                        "clientInfo": {"name": "javis-os", "version": "1.0"}}},
                                  headers={"Accept": "application/json, text/event-stream"})
            www = r.headers.get("www-authenticate") or ""
            m = None
            for part in www.split(","):
                if "resource_metadata" in part:
                    m = part.split("=", 1)[-1].strip().strip('"')
            # Chống SSRF: metadata URL do server trả về CHỈ được fetch khi cùng host với
            # chính MCP url user đã khai (chuẩn RFC 9728 đặt metadata cùng origin).
            if m:
                mp = urllib.parse.urlparse(m)
                up = urllib.parse.urlparse(url)
                if mp.scheme in ("http", "https") and mp.netloc == up.netloc:
                    rm = (await client.get(m)).json()
                    servers = rm.get("authorization_servers") or []
                    if servers:
                        issuer = servers[0]
        except Exception:
            pass
        def _wk(base):
            """Ứng viên .well-known cho 1 issuer/URL. Issuer CÓ PATH (vd Meta
            https://mcp.facebook.com/ads) thì RFC 8414 đặt metadata dạng CHÈN GIỮA
            host và path (/.well-known/oauth-authorization-server/ads) - thử trước;
            giữ dạng NỐI ĐUÔI làm fallback vì một số server đặt kiểu đó."""
            b = urllib.parse.urlparse(base)
            o = f"{b.scheme}://{b.netloc}"
            path = b.path.rstrip("/")
            if not path:
                return [o + "/.well-known/oauth-authorization-server",
                        o + "/.well-known/openid-configuration"]
            return [o + "/.well-known/oauth-authorization-server" + path,
                    o + "/.well-known/openid-configuration" + path,
                    o + path + "/.well-known/oauth-authorization-server",
                    o + path + "/.well-known/openid-configuration"]

        candidates = []
        if issuer:
            candidates += _wk(issuer)
        p = urllib.parse.urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        candidates += _wk(url)          # metadata treo theo path của chính MCP url (không issuer)
        candidates += [origin + "/.well-known/oauth-authorization-server",
                       origin + "/.well-known/openid-configuration"]
        seen = set()
        candidates = [c for c in candidates if not (c in seen or seen.add(c))]
        for c in candidates:
            try:
                r = await client.get(c)
                if r.status_code == 200:
                    md = r.json()
                    if md.get("authorization_endpoint") and md.get("token_endpoint"):
                        return md
            except Exception:
                continue
    return None


async def start_auth(conn_id, redirect_uri):
    """Bắt đầu OAuth cho 1 connection. Trả {ok, url?} hoặc {ok:False, error}.

    2 nhánh:
    - EXPLICIT (connector.auth khai authorize_url + token_url, vd Google): dùng cấu hình khai
      sẵn + client_id/secret user tự tạo (BYO). Dành cho provider KHÔNG hỗ trợ DCR như Google.
    - DISCOVERY (còn lại, vd Meta): tự tìm metadata + tự đăng ký client (DCR) như chuẩn MCP."""
    conn = _conn(conn_id)
    if not conn:
        return {"ok": False, "error": "Kết nối không tồn tại"}
    auth = (conn.get("connector") or {}).get("auth") or {}
    store = _load()
    ent = store.get(conn_id) or {}
    explicit = bool(auth.get("authorize_url") and auth.get("token_url"))

    if explicit:
        creds = mcp_store.connection_secrets(conn_id)
        client_id = (creds.get("client_id") or "").strip()
        client_secret = creds.get("client_secret") or ""
        if not client_id:
            return {"ok": False, "error": "Chưa có Client ID. Dán Client ID + Client Secret bạn tạo "
                                          "ở nhà cung cấp (Google Cloud / Slack app) rồi bấm Kết nối lại."}
        authorize_endpoint = auth["authorize_url"]
        token_endpoint = auth["token_url"]
        scopes = auth.get("scopes") or []
        # Tên param mang scope + dấu ngăn khác nhau theo hãng: Google dùng scope + dấu cách (mặc định),
        # Slack dùng user_scope + dấu phẩy (token người dùng).
        scope_param = auth.get("scope_param") or "scope"
        scope_sep = auth.get("scope_sep") or " "
        extra_params = dict(auth.get("authorize_params") or {})
        add_resource = False
        provider = (auth.get("provider") or "").strip().lower()
    else:
        if not conn.get("url"):
            return {"ok": False, "error": "Kết nối không có URL"}
        md = await _discover(conn["url"])
        if not md:
            return {"ok": False, "error": "Server này không khai OAuth chuẩn MCP (không tìm thấy "
                                          ".well-known metadata). Dùng API key nếu nhà cung cấp có."}
        authorize_endpoint = md["authorization_endpoint"]
        token_endpoint = md["token_endpoint"]
        client_id = ent.get("client_id", "")
        client_secret = ""
        dcr_detail = ""      # error_description máy chủ trả về khi DCR bị từ chối (để báo minh bạch)
        if not client_id and md.get("registration_endpoint"):
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.post(md["registration_endpoint"], json={
                        "client_name": "Javis OS", "redirect_uris": [redirect_uri],
                        "grant_types": ["authorization_code", "refresh_token"],
                        "response_types": ["code"], "token_endpoint_auth_method": "none",
                    })
                    if r.status_code in (200, 201):
                        client_id = r.json().get("client_id", "")
                    else:
                        try:
                            dcr_detail = (r.json() or {}).get("error_description", "") or ""
                        except Exception:
                            dcr_detail = ""
            except Exception as e:
                print(f"[oauth dcr] {e}", file=sys.stderr)
        if not client_id:
            # Máy chủ MCP chỉ nhận ứng dụng được cấp phép sẵn + tắt tự đăng ký (DCR). Với Meta Ads
            # đây là beta giới hạn (allowlist client như ChatGPT/Claude/Perplexity) - không phải lỗi
            # máy user, và dán client_id thủ công cũng không qua được resource server. Báo trung thực.
            msg = ("Máy chủ này chưa cho phép kết nối tự phục vụ: nó chỉ chấp nhận các ứng dụng "
                   "được nhà cung cấp cấp phép sẵn và đã TẮT tự đăng ký ứng dụng (DCR). Đây là giới "
                   "hạn phía nhà cung cấp (Meta Ads đang mở beta dần theo tài khoản), không phải lỗi "
                   "máy bạn - thử lại sau khi tài khoản được mở.")
            if dcr_detail:
                msg += f" (máy chủ báo: {dcr_detail})"
            return {"ok": False, "error": msg}
        scopes = md.get("scopes_supported") or []
        scope_param, scope_sep = "scope", " "
        extra_params = {}
        add_resource = True
        provider = ""

    is_meta = provider == "meta"
    if is_meta:
        redirect_uri = _meta_localhost(redirect_uri)   # Meta chỉ miễn HTTP cho 'localhost'
    verifier = _secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = _secrets.token_urlsafe(24)
    now = time.time()
    for k in [k for k, v in _pending.items() if now - v["ts"] > _PENDING_TTL]:
        _pending.pop(k, None)
    _pending[state] = {"conn_id": conn_id, "verifier": verifier, "token_endpoint": token_endpoint,
                       "client_id": client_id, "client_secret": client_secret,
                       "redirect_uri": redirect_uri, "provider": provider, "ts": now}
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state}
    if not is_meta:                   # Meta classic flow KHÔNG dùng PKCE (client_secret đủ)
        q["code_challenge"] = challenge
        q["code_challenge_method"] = "S256"
    if is_meta:
        # Đã cấp quyền một lần rồi thì Facebook đi đường tắt "Tiếp tục với tên X" và KHÔNG hiện
        # lại màn "Chọn nội dung bạn cho phép" - tức là không tick thêm được Trang/tài khoản mới.
        # auth_type=rerequest là cách Meta khai để ép hiện lại đầy đủ hộp thoại quyền.
        # https://developers.facebook.com/docs/facebook-login/guides/advanced/manual-flow/
        q["auth_type"] = "rerequest"
    if scopes:
        q[scope_param] = scope_sep.join(scopes)
    if add_resource:
        q["resource"] = conn["url"]   # RFC 8707 - server bỏ qua nếu không dùng
    q.update(extra_params)            # vd Google: access_type=offline, prompt=consent (để có refresh_token)
    ent.update(client_id=client_id, token_endpoint=token_endpoint, provider=provider)
    store[conn_id] = ent
    _save(store)
    return {"ok": True, "url": authorize_endpoint + "?" + urllib.parse.urlencode(q)}


def _email_from_id_token(idt):
    """Bóc email từ id_token (JWT) Google trả về khi scope có openid+email - để tự đặt tên
    tài khoản. Chỉ đọc payload hiển thị, không cần verify chữ ký (token lấy trực tiếp qua TLS)."""
    try:
        payload = (idt or "").split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
        return data.get("email") or ""
    except Exception:
        return ""


async def handle_callback(state, code):
    p = _pending.pop(state or "", None)
    if not p:
        return {"ok": False, "error": "Phiên OAuth không hợp lệ hoặc đã hết hạn - thử lại từ đầu"}
    is_meta = (p.get("provider") == "meta")
    try:
        if is_meta:
            # Facebook: đổi code→token bằng GET, KHÔNG grant_type/PKCE, client_secret bắt buộc.
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get(p["token_endpoint"], params={
                    "client_id": p["client_id"], "client_secret": p.get("client_secret", ""),
                    "redirect_uri": p["redirect_uri"], "code": code})
            tk = r.json()
            if not (isinstance(tk, dict) and tk.get("access_token")):
                return {"ok": False, "error": _meta_token_error(tk, p["redirect_uri"])}
            # Nâng ngay lên token dài hạn ~60 ngày (short-lived chỉ 1-2h).
            ll = await _meta_longlive(p["token_endpoint"], p["client_id"], p.get("client_secret", ""),
                                      tk["access_token"])
            tk = ll or tk
        else:
            data = {"grant_type": "authorization_code", "code": code, "redirect_uri": p["redirect_uri"],
                    "client_id": p["client_id"], "code_verifier": p["verifier"]}
            if p.get("client_secret"):   # client bảo mật (vd Google Web app) cần secret khi đổi token
                data["client_secret"] = p["client_secret"]
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(p["token_endpoint"], data=data, headers={"Accept": "application/json"})
            tk = r.json()
            if "access_token" not in tk:
                return {"ok": False, "error": f"Đổi code thất bại: {json.dumps(tk, ensure_ascii=False)[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"Đổi code thất bại: {type(e).__name__}: {e}"}
    store = _load()
    ent = store.get(p["conn_id"]) or {}
    first_auth = not ent.get("access_token")   # lần đăng nhập ĐẦU (chưa từng có token) mới tự đặt tên
    # Facebook không cấp refresh_token; long-lived ~60 ngày, gia hạn bằng fb_exchange_token (xem _refresh).
    ent.update(access_token=secrets_store.encrypt(tk["access_token"]),
               refresh_token=secrets_store.encrypt(tk.get("refresh_token", "")),
               provider=p.get("provider", ""),
               # scope THẬT được cấp (không phải scope đã xin): dùng để phát hiện "đăng nhập
               # xanh nhưng thiếu quyền" mà không phải chờ một tool cụ thể chết. Không phải bí
               # mật (chỉ là danh sách phạm vi) nên lưu thẳng, khỏi mã hoá.
               scopes=str(tk.get("scope") or ""),
               expires_at=time.time() + float(tk.get("expires_in") or (5184000 if is_meta else 3600)))
    store[p["conn_id"]] = ent
    _save(store)
    return {"ok": True, "conn_id": p["conn_id"], "first_auth": first_auth,
            "email": _email_from_id_token(tk.get("id_token", ""))}


async def _refresh(conn_id, ent):
    # Facebook: KHÔNG có refresh_token - gia hạn bằng cách re-exchange chính access_token hiện tại
    # qua fb_exchange_token. Hết hạn (~60 ngày) hoặc bị thu hồi thì phải đăng nhập lại.
    if ent.get("provider") == "meta":
        cur = secrets_store.decrypt(ent.get("access_token", ""))
        cs = mcp_store.connection_secrets(conn_id).get("client_secret")
        ll = await _meta_longlive(ent.get("token_endpoint"), ent.get("client_id"), cs, cur)
        if not ll:
            return None
        ent.update(access_token=secrets_store.encrypt(ll["access_token"]),
                   expires_at=time.time() + float(ll.get("expires_in") or 5184000))
        store = _load()
        store[conn_id] = ent
        _save(store)
        return ent
    rt = secrets_store.decrypt(ent.get("refresh_token", ""))
    if not (rt and ent.get("token_endpoint") and ent.get("client_id")):
        return None
    try:
        data = {"grant_type": "refresh_token", "refresh_token": rt, "client_id": ent["client_id"]}
        cs = mcp_store.connection_secrets(conn_id).get("client_secret")
        if cs:   # BYO client bảo mật (Google) - refresh cũng cần client_secret
            data["client_secret"] = cs
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(ent["token_endpoint"], data=data, headers={"Accept": "application/json"})
        tk = r.json()
        if "access_token" not in tk:
            return None
    except Exception as e:
        print(f"[oauth refresh] {e}", file=sys.stderr)
        return None
    ent.update(access_token=secrets_store.encrypt(tk["access_token"]),
               expires_at=time.time() + float(tk.get("expires_in") or 3600))
    if tk.get("scope"):   # Google trả lại scope mỗi lần refresh - giữ bản mới nhất
        ent["scopes"] = str(tk["scope"])
    if tk.get("refresh_token"):
        ent["refresh_token"] = secrets_store.encrypt(tk["refresh_token"])
    store = _load()
    store[conn_id] = ent
    _save(store)
    return ent


async def auth_headers(conn_id):
    """{"Authorization": "Bearer ..."} cho connection oauth; tự refresh khi sắp hết hạn."""
    store = _load()
    ent = store.get(conn_id)
    if not ent or not ent.get("access_token"):
        return {}
    if time.time() > float(ent.get("expires_at") or 0) - 60:
        ent = await _refresh(conn_id, ent) or ent
    tok = secrets_store.decrypt(ent.get("access_token", ""))
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def credentials_file(conn_id, fmt):
    """Nội dung file credential cho connector STDIO dùng OAuth. Trả chuỗi JSON, hoặc "" nếu chưa
    đăng nhập / thiếu dữ kiện / format không biết.

    Vì sao cần: auth_headers() ở trên phục vụ connector transport=http (nhét Bearer vào header).
    Connector stdio (vd google-ads) chạy tiến trình con và chỉ nhận credential qua FILE + biến môi
    trường. Hàm này bắc cầu giữa hai kiểu đó.

    ĐỒNG BỘ, không gọi mạng: file ADC chứa refresh_token, chính tiến trình con sẽ tự đổi lấy
    access token khi cần. Nên KHÔNG refresh ở đây."""
    if fmt != "google_adc":
        return ""
    ent = _load().get(conn_id) or {}
    rt = secrets_store.decrypt(ent.get("refresh_token", ""))
    if not rt:
        return ""
    sec = mcp_store.connection_secrets(conn_id) or {}
    cid = sec.get("client_id") or ent.get("client_id") or ""
    cs = sec.get("client_secret") or ""
    if not (cid and cs):
        return ""
    # Đúng khuôn file gcloud sinh ra ở ~/.config/gcloud/application_default_credentials.json
    return json.dumps({"type": "authorized_user", "client_id": cid,
                       "client_secret": cs, "refresh_token": rt}, ensure_ascii=False, indent=2)


def status(conn_id):
    ent = _load().get(conn_id) or {}
    rep = scope_report(conn_id)
    return {"connected": bool(ent.get("access_token")), "expires_at": float(ent.get("expires_at") or 0),
            "scopes_known": rep["known"], "scopes_missing": short_scopes(rep["missing"])}


def forget(conn_id):
    store = _load()
    if conn_id in store:
        store.pop(conn_id)
        _save(store)
    return {"ok": True}
