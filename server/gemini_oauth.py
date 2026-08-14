"""Đăng nhập tài khoản Google cho Gemini CLI, NGAY TRÊN DASHBOARD - không phải mở terminal.

Cùng khuôn `openai_oauth.py` đã dựng cho Codex: Javis tự chạy vòng OAuth rồi **bắc cầu** token
sang kho credential của CLI, để chính binary `gemini` dùng. Javis không đọc trộm token của ai;
nó tự xin, bằng đúng client OAuth công khai của Gemini CLI, với sự đồng ý của người dùng.

**Vì sao dán mã chứ không phải chờ localhost.** Gemini CLI có hai đường đăng nhập, và Javis
dùng đúng đường thứ hai của nó (`authWithUserCode`): redirect về trang
`https://codeassist.google.com/authcode` do Google dựng, trang này HIỆN RA một mã cho người
dùng chép lại. Đường thứ nhất (`authWithWeb`) dựng một máy chủ loopback ở cổng ngẫu nhiên trên
MÁY CHẠY CLI - vô dụng khi Javis nằm trên VPS còn trình duyệt ở máy người dùng. Đường mã dán
chạy được ở cả hai chỗ, và giống hệt trải nghiệm đăng nhập Claude Code đang có.

**Bắc cầu token thế nào.** `~/.gemini/oauth_creds.json` là kho credential mà CLI đọc. Bản mới
(0.55+) đọc keychain trước, không thấy thì `migrateFromFileStorage()` nạp file đó vào rồi
**xoá file đi**. Nên Javis không thể ghi một lần rồi thôi: mỗi lượt chạy `gemini` đều gọi
`ghi_creds_cho_cli()` để dựng lại file (và làm mới token nếu sắp hết hạn). Nguồn sự thật nằm ở
settings.json của Javis, không phải ở file kia.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets as _secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

import config as cfgmod

# Client OAuth của Gemini CLI được ĐỌC TỪ CHÍNH BẢN CLI ĐÃ CÀI, không chép cứng vào repo.
#
# Ba lý do, xếp theo thứ tự quan trọng:
#
# 1. Nó là credential của Google, dù thuộc loại "Desktop app" (client_secret không phải bí mật
#    theo đúng chuẩn OAuth cho ứng dụng cài đặt, vì bất kỳ ai cũng giải nén được từ bundle).
#    Chép vào repo là để một chuỗi như vậy nằm trong lịch sử git mãi mãi, và mọi bộ quét bí mật
#    sẽ chặn - GitHub push protection chặn đúng lần đầu thử, và nó chặn đúng.
# 2. Google xoay client thì Javis đi theo ngay, khỏi phải ra bản vá.
# 3. Nói đúng bản chất việc đang làm: Javis MƯỢN client của Gemini CLI để xin token CHO chính
#    Gemini CLI dùng. Đọc từ bản CLI trên máy là cách diễn đạt trung thực nhất của câu đó, và
#    người dùng thấy đúng tên "Gemini CLI" trên màn hình đồng ý của Google.
#
# Cửa thoát cho bản đóng gói lạ: JAVIS_GEMINI_OAUTH_CLIENT_ID / _SECRET.
_CLIENT_CACHE = {}
_RE_ID = re.compile(r'OAUTH_CLIENT_ID\s*=\s*"([^"]+\.apps\.googleusercontent\.com)"')
_RE_SECRET = re.compile(r'OAUTH_CLIENT_SECRET\s*=\s*"([^"]+)"')


def doc_client() -> tuple:
    """(client_id, client_secret) của Gemini CLI đang cài. ("", "") nếu không moi ra được."""
    env_id = (os.environ.get("JAVIS_GEMINI_OAUTH_CLIENT_ID") or "").strip()
    env_sec = (os.environ.get("JAVIS_GEMINI_OAUTH_CLIENT_SECRET") or "").strip()
    if env_id and env_sec:
        return env_id, env_sec
    if _CLIENT_CACHE.get("id"):
        return _CLIENT_CACHE["id"], _CLIENT_CACHE["secret"]
    try:
        from gemini_cli import find_gemini_cli
        cli = find_gemini_cli()
        if not cli:
            return "", ""
        # /usr/bin/gemini -> .../node_modules/@google/gemini-cli/bundle/gemini.js. Đi lên tới
        # gốc gói rồi quét các chunk trong bundle; hằng số nằm ở một chunk không cố định tên.
        goc = Path(os.path.realpath(cli)).parent
        for _ in range(3):
            if (goc / "package.json").exists():
                break
            goc = goc.parent
        cac_file = sorted(goc.rglob("*.js"), key=lambda p: -p.stat().st_size)[:12]
        for f in cac_file:
            try:
                noi_dung = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            mid = _RE_ID.search(noi_dung)
            msec = _RE_SECRET.search(noi_dung)
            if mid and msec:
                _CLIENT_CACHE.update(id=mid.group(1), secret=msec.group(1))
                return mid.group(1), msec.group(1)
    except Exception:
        pass
    return "", ""


SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
# Trang của Google hiện mã ra cho người dùng chép. Phải khớp ĐÚNG chuỗi CLI dùng, vì Google
# kiểm redirect_uri cả lúc xin mã lẫn lúc đổi mã.
REDIRECT_URI = "https://codeassist.google.com/authcode"

_pending = {}      # {"verifier", "state", "ts"} - phiên đăng nhập đang chờ dán mã
_PENDING_TTL = 15 * 60


def _pkce():
    v = base64.urlsafe_b64encode(os.urandom(64)).decode().rstrip("=")
    c = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    return v, c


def _doc() -> dict:
    return (cfgmod.read_settings().get("model", {}) or {}).get("gemini_oauth") or {}


def _ghi(d: dict):
    cfg = cfgmod.read_settings()
    cfg.setdefault("model", {})["gemini_oauth"] = d
    cfgmod.write_settings(cfg)


def start_login() -> dict:
    """Bước 1: dựng link đồng ý của Google + giữ code_verifier. Trả {ok, authorize_url}."""
    cid, _ = doc_client()
    if not cid:
        return {"ok": False,
                "error": "Chưa đọc được thông tin đăng nhập từ Gemini CLI. Cài hoặc cập nhật "
                         "bằng `npm i -g @google/gemini-cli@latest` rồi thử lại."}
    verifier, challenge = _pkce()
    state = _secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": cid,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        # offline + consent: BẮT BUỘC lấy cho được refresh_token. Thiếu nó thì đăng nhập xong
        # chạy được đúng một tiếng rồi im, và triệu chứng đó rất khó lần ra.
        "access_type": "offline",
        "prompt": "consent",
    }
    _pending.clear()
    _pending.update(verifier=verifier, state=state, ts=time.time())
    return {"ok": True, "authorize_url": AUTH_URL + "?" + urlencode(params)}


def finish_login(code: str) -> dict:
    """Bước 2: đổi mã người dùng dán về lấy token, lưu lại, rồi bắc cầu sang CLI."""
    if not _pending:
        return {"ok": False, "error": "Chưa bắt đầu đăng nhập - bấm Đăng nhập Google trước."}
    if time.time() - float(_pending.get("ts") or 0) > _PENDING_TTL:
        _pending.clear()
        return {"ok": False, "error": "Phiên đăng nhập hết hạn (15 phút), bấm lại."}
    ma = (code or "").strip()
    if not ma:
        return {"ok": False, "error": "Chưa dán mã."}
    # Người dùng hay dán cả URL thay vì mã. Nhận luôn cho đỡ phải giải thích.
    if ma.startswith("http"):
        from urllib.parse import parse_qs, urlparse
        ma = (parse_qs(urlparse(ma).query).get("code") or [""])[0].strip()
        if not ma:
            return {"ok": False, "error": "Không tìm thấy mã trong đường dẫn vừa dán."}
    cid, csec = doc_client()
    if not cid:
        return {"ok": False, "error": "Không đọc được thông tin đăng nhập từ Gemini CLI."}
    try:
        r = httpx.post(TOKEN_URL, data={
            "code": ma, "client_id": cid, "client_secret": csec,
            "code_verifier": _pending["verifier"], "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }, timeout=30)
    except Exception as e:
        return {"ok": False, "error": f"Không gọi được Google: {type(e).__name__}"}
    if r.status_code != 200:
        chi_tiet = ""
        try:
            j = r.json()
            chi_tiet = str(j.get("error_description") or j.get("error") or "")
        except Exception:
            chi_tiet = (r.text or "")[:200]
        if "invalid_grant" in chi_tiet:
            chi_tiet = "Mã sai hoặc đã dùng rồi. Bấm Đăng nhập Google để lấy mã mới."
        return {"ok": False, "error": chi_tiet or f"Google từ chối (HTTP {r.status_code})."}
    tok = r.json() or {}
    if not tok.get("refresh_token"):
        return {"ok": False,
                "error": "Google không cấp refresh token. Vào myaccount.google.com/permissions "
                         "gỡ quyền của \"Gemini CLI\" rồi đăng nhập lại."}
    _pending.clear()
    d = {
        "access_token": tok.get("access_token", ""),
        "refresh_token": tok.get("refresh_token", ""),
        "email": _lay_email(tok.get("access_token", "")),
        "expires_at": int(time.time()) + int(tok.get("expires_in") or 3600),
    }
    _ghi(d)
    ghi_creds_cho_cli()
    return {"ok": True, "email": d["email"]}


def _lay_email(access_token: str) -> str:
    if not access_token:
        return ""
    try:
        r = httpx.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
        return str((r.json() or {}).get("email") or "") if r.status_code == 200 else ""
    except Exception:
        return ""


def valid_creds() -> dict:
    """Token còn dùng được, tự làm mới khi sắp hết hạn. {} nếu chưa đăng nhập qua dashboard."""
    d = dict(_doc())
    if not d.get("refresh_token"):
        return {}
    if d.get("access_token") and int(d.get("expires_at") or 0) - 120 > time.time():
        return d
    cid, csec = doc_client()
    if not cid:
        return d if d.get("access_token") else {}
    try:
        r = httpx.post(TOKEN_URL, data={
            "client_id": cid, "client_secret": csec,
            "refresh_token": d["refresh_token"], "grant_type": "refresh_token",
        }, timeout=30)
    except Exception:
        return d if d.get("access_token") else {}
    if r.status_code != 200:
        # Refresh token bị thu hồi (đổi mật khẩu Google, gỡ quyền) → XOÁ hẳn thay vì giữ một
        # trạng thái "đã đăng nhập" nói dối. Người dùng thấy nút đăng nhập lại là đúng việc.
        if r.status_code in (400, 401):
            _ghi({"access_token": "", "refresh_token": "", "email": d.get("email", ""),
                  "expires_at": 0})
            return {}
        return d if d.get("access_token") else {}
    tok = r.json() or {}
    d["access_token"] = tok.get("access_token", "")
    d["expires_at"] = int(time.time()) + int(tok.get("expires_in") or 3600)
    if tok.get("refresh_token"):
        d["refresh_token"] = tok["refresh_token"]
    _ghi(d)
    return d


def connected() -> bool:
    return bool(_doc().get("refresh_token"))


def email() -> str:
    return str(_doc().get("email") or "")


def disconnect():
    _ghi({"access_token": "", "refresh_token": "", "email": "", "expires_at": 0})
    # Gỡ luôn bản sao đã bắc cầu, nếu CLI chưa kịp nuốt nó vào kho của mình.
    try:
        (_home() / ".gemini" / "oauth_creds.json").unlink(missing_ok=True)
    except Exception:
        pass


def _home() -> Path:
    from claude_cli import _home_dir
    return _home_dir()


def ghi_creds_cho_cli() -> bool:
    """Bắc cầu token sang kho của Gemini CLI. Gọi TRƯỚC MỖI LƯỢT chạy `gemini`.

    Hai file, cả hai đều cần:

    - `~/.gemini/oauth_creds.json` - credential. CLI bản mới nạp nó vào keychain rồi XOÁ file,
      nên đây là việc phải làm lại mỗi lượt chứ không phải một lần cho xong.
    - `~/.gemini/settings.json` - khoá `security.auth.selectedType = "oauth-personal"`. Thiếu
      nó thì CLI dừng ngay ở "Please set an Auth method" dù credential nằm sẵn đó.

    Chỉ ĐẶT khoá auth khi người dùng chưa tự chọn cách khác: ai đã tự cấu hình `vertex-ai` hay
    API key trong file của họ thì Javis không giẫm lên.
    """
    d = valid_creds()
    if not d.get("access_token"):
        return False
    try:
        thu_muc = _home() / ".gemini"
        thu_muc.mkdir(parents=True, exist_ok=True)
        p = thu_muc / "oauth_creds.json"
        p.write_text(json.dumps({
            "access_token": d["access_token"],
            "refresh_token": d.get("refresh_token", ""),
            "token_type": "Bearer",
            "scope": " ".join(SCOPES),
            "expiry_date": int(d.get("expires_at") or 0) * 1000,   # CLI tính bằng mili giây
        }, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(p, 0o600)
        except Exception:
            pass

        st_path = thu_muc / "settings.json"
        st = {}
        try:
            st = json.loads(st_path.read_text(encoding="utf-8")) or {}
        except Exception:
            st = {}
        if not isinstance(st, dict):
            st = {}
        cu = (((st.get("security") or {}).get("auth") or {}).get("selectedType")
              or st.get("selectedAuthType") or "")
        if not cu:
            st.setdefault("security", {}).setdefault("auth", {})["selectedType"] = "oauth-personal"
            st_path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

        if d.get("email"):
            try:
                (thu_muc / "google_accounts.json").write_text(
                    json.dumps({"active": d["email"], "old": []}, ensure_ascii=False),
                    encoding="utf-8")
            except Exception:
                pass
        return True
    except Exception:
        return False
