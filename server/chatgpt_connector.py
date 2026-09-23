"""Javis trong ChatGPT: cho ChatGPT gọi công cụ của Javis qua một MCP connector.

Vì sao có file này
------------------
Chủ repo muốn dùng gói ChatGPT không giới hạn cho việc hằng ngày, kèm năng lực của Javis. Đường
đầu tiên (model `chatgpt-web`, Javis lái một trình duyệt vào chatgpt.com) chết trên máy chủ
thuê vì Cloudflare chặn theo IP, và bị gỡ ở 0.64.20.

Đường này ĐẢO CHIỀU: người dùng chat trên chatgpt.com như bình thường, còn ChatGPT (Developer
mode) tự gọi sang Javis qua tính năng MCP connector chính thức. Không có trình duyệt nào ở phía
Javis, nên không có Cloudflare nào để qua: máy chủ OpenAI gọi đến Javis, không phải ngược lại.

Javis vốn đã là một MCP server đầy đủ (`/hub/mcp`, Claude Code và Codex dùng hằng ngày). Thứ
thiếu duy nhất là CỬA: ChatGPT chỉ nhận OAuth hoặc không xác thực, còn hub dùng một bearer cố
định. Không xác thực là không được bàn tới - hub cầm cả công cụ gửi Zalo, tạo đơn.

Cửa này là OAuth 2.1 tối giản, đúng phần ChatGPT dùng (đối chiếu với XiaoDuoYa/codex-with-
chatgpt, đã chạy thật với ChatGPT):

  - khám phá: RFC 9728 (protected resource) + RFC 8414 (authorization server)
  - đăng ký client động: RFC 7591 (ChatGPT tự đăng ký, người dùng không phải dán client id)
  - mã cấp quyền + PKCE S256 (bắt buộc, không nhận `plain`)
  - làm mới token có XOAY vòng, thu hồi: RFC 7009

Chỗ khác bản tham khảo, có chủ ý: bước "Cho phép" dựa vào ĐĂNG NHẬP DASHBOARD sẵn có (mật khẩu
+ 2FA) thay vì mã ghép cặp. Người bấm "Cho phép" phải là người vào được dashboard, không kém
hơn và không có thêm một bí mật nào để lộ.

Ranh giới an toàn
-----------------
- TẮT mặc định. Tắt thì mọi endpoint ở đây trả 404, không quảng bá gì cả.
- Chỉ bật được khi Javis đã có mật khẩu quản trị: cửa đồng ý dựa vào đăng nhập, không có đăng
  nhập thì không có cửa.
- `redirect_uri` chỉ nhận máy của OpenAI. Kẻ tự đăng ký một client trỏ về máy mình rồi dụ chủ
  bấm "Cho phép" sẽ không nhận được mã.
- Token chỉ lưu dạng BĂM SHA-256. File lộ ra không dùng được để gọi.
- Token của cửa này KHÔNG phải `hub_token`, và ngược lại. Thu hồi bên này không đụng Claude
  Code hay Codex.
- Mức quyền (full / auto / suggest) do chủ chọn trên dashboard, hub ép ở lớp cứng như mọi
  engine khác. ChatGPT không tự nâng được.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from typing import Optional
from urllib.parse import urlencode, urlparse

import config as cfgmod
from config import STATE_DIR

# Đường dẫn công khai. Gom một chỗ vì ba nơi phải khớp nhau từng ký tự: metadata khám phá, câu
# `WWW-Authenticate` và danh sách đường không cần cookie trong main.py.
DUONG_MCP = "/chatgpt/mcp"
DUONG_AUTHORIZE = "/chatgpt/oauth/authorize"
DUONG_TOKEN = "/chatgpt/oauth/token"
DUONG_REGISTER = "/chatgpt/oauth/register"
DUONG_REVOKE = "/chatgpt/oauth/revoke"
WK_AS = "/.well-known/oauth-authorization-server"
WK_OIDC = "/.well-known/openid-configuration"
WK_PR = "/.well-known/oauth-protected-resource"
WK_PR_MCP = WK_PR + DUONG_MCP

# Đường không cần cookie đăng nhập: máy chủ OpenAI gọi, hoặc trình duyệt mở trước khi đăng nhập.
# Trang đồng ý (GET authorize) nằm ở đây vì nó phải HIỆN RA để người dùng đăng nhập; nút
# "Cho phép" (POST) thì tự kiểm phiên bên trong.
DUONG_CONG_KHAI = (DUONG_MCP, DUONG_AUTHORIZE, DUONG_TOKEN, DUONG_REGISTER, DUONG_REVOKE,
                   WK_AS, WK_OIDC, WK_PR, WK_PR_MCP)
# Đường KHÔNG dùng cookie, nên hàng rào CSRF (vốn chỉ để bảo vệ thao tác dựa vào cookie) không
# có gì để bảo vệ ở đây, mà chặn nhầm thì ChatGPT không kết nối được. Nút "Cho phép" KHÔNG nằm
# trong danh sách này.
DUONG_KHONG_COOKIE = (DUONG_MCP, DUONG_TOKEN, DUONG_REGISTER, DUONG_REVOKE)

TTL_ACCESS = 3600                   # 1 giờ; ChatGPT tự làm mới
TTL_REFRESH = 30 * 24 * 3600        # 30 ngày không dùng thì phải cho phép lại
TTL_MA = 300                        # mã cấp quyền sống 5 phút, dùng MỘT lần
TTL_YEU_CAU = 600                   # trang đồng ý mở quá 10 phút thì phải bắt đầu lại từ ChatGPT
MAX_CLIENT = 20                     # chặn ai đó đăng ký client tới đầy đĩa
# Trang Cho phép là đường CÔNG KHAI và mỗi lần mở nó cất một yêu cầu vào RAM trong 10 phút.
# Không có trần thì gọi dồn dập là ngốn bộ nhớ tới khi máy chủ chết. Người thật chỉ có vài yêu
# cầu cùng lúc, nên vượt trần thì bỏ cái cũ nhất: người đang bấm dở chỉ phải kết nối lại.
MAX_YEU_CAU = 100
MUC_QUYEN = ("full", "auto", "suggest")
MUC_MAC_DINH = "full"               # theo quyết định 2026-09-10 của chủ repo: Javis tự làm

# Máy của OpenAI. Redirect của connector ChatGPT nằm trên chatgpt.com; để thêm hai họ tên miền
# của OpenAI cho lúc họ dời chỗ, không mở rộng hơn.
_HOST_REDIRECT = ("chatgpt.com", "chat.openai.com")
_DUOI_REDIRECT = (".chatgpt.com", ".openai.com")

_KHO = STATE_DIR / ".chatgpt_connector.json"
_KHOA = threading.Lock()
_yeu_cau: dict = {}                 # id -> yêu cầu đang chờ người bấm Cho phép
_ma: dict = {}                      # băm của mã -> bản ghi, dùng một lần


# ============================================================
# Cấu hình (settings.json) - bật/tắt và mức quyền
# ============================================================

def cau_hinh(cfg: Optional[dict] = None) -> dict:
    d = ((cfg or cfgmod.read_settings()).get("chatgpt_connector") or {})
    muc = d.get("muc_quyen") if d.get("muc_quyen") in MUC_QUYEN else MUC_MAC_DINH
    return {"bat": bool(d.get("bat")), "muc_quyen": muc}


def dat_cau_hinh(bat: Optional[bool] = None, muc_quyen: Optional[str] = None) -> dict:
    """Ghi cấu hình. Không cho BẬT khi chưa có mật khẩu quản trị: cửa đồng ý dựa vào đăng nhập."""
    cfg = cfgmod.read_settings()
    d = dict(cfg.get("chatgpt_connector") or {})
    if bat is not None:
        if bat and not cfgmod.auth_enabled(cfg):
            return {"ok": False, "error": ("Đặt mật khẩu quản trị cho Javis trước. Bước cho phép "
                                           "ChatGPT dựa vào đăng nhập dashboard.")}
        d["bat"] = bool(bat)
    if muc_quyen is not None:
        if muc_quyen not in MUC_QUYEN:
            return {"ok": False, "error": f"Mức quyền không hợp lệ: {muc_quyen!r}"}
        d["muc_quyen"] = muc_quyen
    cfg["chatgpt_connector"] = d
    cfgmod.write_settings(cfg)
    return {"ok": True, **cau_hinh(cfg)}


def dang_bat() -> bool:
    """Bật VÀ còn mật khẩu. Người dùng gỡ mật khẩu sau khi bật thì cửa tự đóng."""
    cfg = cfgmod.read_settings()
    return cau_hinh(cfg)["bat"] and cfgmod.auth_enabled(cfg)


# ============================================================
# Địa chỉ công khai
# ============================================================

def dia_chi_goc(external_base: str) -> str:
    """Gốc công khai của Javis, không có "/" cuối.

    Ưu tiên tên miền riêng đã khai ở trang Thương hiệu: nó ỔN ĐỊNH, còn header proxy thì đổi theo
    đường người ta đi vào. Issuer của OAuth mà đổi giữa chừng là ChatGPT coi như một máy khác.
    """
    try:
        custom = ((cfgmod.read_settings().get("domain") or {}).get("custom") or "").strip().lower()
    except Exception:
        custom = ""
    if custom:
        return f"https://{custom}"
    return (external_base or "").rstrip("/")


def metadata_as(goc: str) -> dict:
    return {
        "issuer": goc,
        "authorization_endpoint": goc + DUONG_AUTHORIZE,
        "token_endpoint": goc + DUONG_TOKEN,
        "registration_endpoint": goc + DUONG_REGISTER,
        "revocation_endpoint": goc + DUONG_REVOKE,
        "response_types_supported": ["code"],
        "response_modes_supported": ["query"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["javis"],
    }


def metadata_pr(goc: str) -> dict:
    return {
        "resource": goc + DUONG_MCP,
        "authorization_servers": [goc],
        "scopes_supported": ["javis"],
        "bearer_methods_supported": ["header"],
        "resource_name": "Javis",
    }


def www_authenticate(goc: str, loi: str = "invalid_token", mo_ta: str = "") -> str:
    """Câu thách thức trả kèm 401. ChatGPT đọc `resource_metadata` để biết đi đâu đăng nhập.

    `mo_ta` PHẢI là ASCII: nó đi vào header HTTP, mà header chỉ nhận Latin-1.
    """
    mo_ta = mo_ta.encode("ascii", "ignore").decode()
    phan = ['Bearer realm="javis"', f'error="{loi}"']
    if mo_ta:
        phan.append(f'error_description="{mo_ta}"')
    phan.append(f'resource_metadata="{goc}{WK_PR_MCP}"')
    return ", ".join(phan)


# ============================================================
# Kho: client + token (chỉ lưu băm)
# ============================================================

def _bam(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _s256(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")


def _doc() -> dict:
    try:
        d = json.loads(_KHO.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            d.setdefault("clients", {})
            d.setdefault("tokens", {})
            return d
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return {"clients": {}, "tokens": {}}


def _ghi(d: dict) -> None:
    # Chỉ dọn bản HẾT HẠN. Bản đã thu hồi giữ tới hạn của nó: refresh đã xoay mà bị dùng lại là
    # dấu hiệu có người cầm bản sao, và phải còn bản ghi thì mới nhận ra được.
    now = time.time()
    d["tokens"] = {h: t for h, t in d["tokens"].items() if t.get("het", 0) > now}
    tam = _KHO.with_suffix(".tmp")
    tam.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(tam, 0o600)
    except OSError:
        pass
    os.replace(tam, _KHO)


def redirect_hop_le(uri: str) -> bool:
    try:
        u = urlparse(uri)
    except Exception:
        return False
    if u.scheme != "https" or not u.hostname:
        return False
    h = u.hostname.lower()
    return h in _HOST_REDIRECT or any(h.endswith(d) for d in _DUOI_REDIRECT)


def dang_ky_client(body: dict) -> tuple:
    """(mã HTTP, JSON). RFC 7591, chỉ phần ChatGPT dùng: client công khai, không bí mật."""
    uris = body.get("redirect_uris") if isinstance(body, dict) else None
    if not isinstance(uris, list) or not uris or not all(isinstance(u, str) and redirect_hop_le(u)
                                                            for u in uris):
        return 400, {"error": "invalid_redirect_uri",
                     "error_description": "redirect_uris phải là địa chỉ https của ChatGPT"}
    ten = str(body.get("client_name") or "ChatGPT")[:120]
    with _KHOA:
        d = _doc()
        if len(d["clients"]) >= MAX_CLIENT:
            # Bỏ client cũ nhất CHƯA từng nhận token: đó là những lần kết nối bỏ dở.
            dang_dung = {t.get("client") for t in d["tokens"].values()}
            cu = sorted((c for c in d["clients"].values() if c["id"] not in dang_dung),
                        key=lambda c: c.get("tao", 0))
            if not cu:
                return 400, {"error": "invalid_client_metadata",
                             "error_description": "Quá nhiều kết nối. Ngắt bớt ở dashboard Javis."}
            d["clients"].pop(cu[0]["id"], None)
        cid = "chatgpt-" + secrets.token_urlsafe(16)
        d["clients"][cid] = {"id": cid, "ten": ten, "redirect_uris": uris, "tao": time.time()}
        _ghi(d)
    return 201, {"client_id": cid, "client_name": ten, "redirect_uris": uris,
                 "token_endpoint_auth_method": "none",
                 "grant_types": ["authorization_code", "refresh_token"],
                 "response_types": ["code"]}


def _don_yeu_cau() -> None:
    now = time.time()
    for k in [k for k, v in _yeu_cau.items() if v["het"] < now]:
        _yeu_cau.pop(k, None)
    for k in [k for k, v in _ma.items() if v["het"] < now]:
        _ma.pop(k, None)


def _chuyen_loi(redirect_uri: str, loi: str, mo_ta: str, state: str = "") -> str:
    q = {"error": loi, "error_description": mo_ta}
    if state:
        q["state"] = state
    return redirect_uri + ("&" if "?" in redirect_uri else "?") + urlencode(q)


def bat_dau_uy_quyen(q: dict) -> tuple:
    """Kiểm yêu cầu từ ChatGPT.

    ("trang_loi", câu)      - không tin được redirect_uri nên KHÔNG được chuyển hướng về đó
    ("chuyen", url)         - lỗi báo ngược về ChatGPT theo đúng OAuth
    ("ok", yeu_cau)         - hiện trang đồng ý
    """
    _don_yeu_cau()
    cid = str(q.get("client_id") or "")
    client = _doc()["clients"].get(cid)
    if not client:
        return "trang_loi", "Không nhận ra kết nối này. Mở lại ChatGPT và bấm kết nối lại."
    ru = str(q.get("redirect_uri") or "")
    if ru not in client["redirect_uris"]:
        return "trang_loi", "Địa chỉ quay về không khớp với lúc đăng ký."
    state = str(q.get("state") or "")
    if q.get("response_type") != "code":
        return "chuyen", _chuyen_loi(ru, "unsupported_response_type", "chỉ hỗ trợ code", state)
    if not q.get("code_challenge") or q.get("code_challenge_method") != "S256":
        return "chuyen", _chuyen_loi(ru, "invalid_request", "bắt buộc PKCE S256", state)
    yc = {"id": secrets.token_urlsafe(24), "client": cid, "ten": client["ten"],
          "redirect_uri": ru, "state": state, "challenge": str(q["code_challenge"])[:128],
          "het": time.time() + TTL_YEU_CAU}
    while len(_yeu_cau) >= MAX_YEU_CAU:
        _yeu_cau.pop(min(_yeu_cau, key=lambda k: _yeu_cau[k]["het"]), None)
    _yeu_cau[yc["id"]] = yc
    return "ok", yc


def lay_yeu_cau(yid: str) -> Optional[dict]:
    _don_yeu_cau()
    return _yeu_cau.get(yid or "")


def dong_y(yid: str) -> Optional[str]:
    """Chủ bấm Cho phép. Trả URL quay về ChatGPT kèm mã, hoặc None nếu yêu cầu đã hết hạn."""
    _don_yeu_cau()
    yc = _yeu_cau.pop(yid or "", None)
    if not yc:
        return None
    ma = secrets.token_urlsafe(32)
    _ma[_bam(ma)] = {"client": yc["client"], "redirect_uri": yc["redirect_uri"],
                     "challenge": yc["challenge"], "het": time.time() + TTL_MA}
    q = {"code": ma}
    if yc["state"]:
        q["state"] = yc["state"]
    return yc["redirect_uri"] + ("&" if "?" in yc["redirect_uri"] else "?") + urlencode(q)


def tu_choi(yid: str) -> Optional[str]:
    yc = _yeu_cau.pop(yid or "", None)
    if not yc:
        return None
    return _chuyen_loi(yc["redirect_uri"], "access_denied", "chủ Javis từ chối", yc["state"])


def _cap_token(d: dict, cid: str, ho: str) -> dict:
    """Một cặp access + refresh. `ho` gom các thế hệ refresh của cùng một lần cho phép."""
    now = time.time()
    at, rt = secrets.token_urlsafe(32), secrets.token_urlsafe(40)
    d["tokens"][_bam(at)] = {"loai": "access", "client": cid, "ho": ho, "het": now + TTL_ACCESS}
    d["tokens"][_bam(rt)] = {"loai": "refresh", "client": cid, "ho": ho, "het": now + TTL_REFRESH}
    return {"access_token": at, "token_type": "Bearer", "expires_in": TTL_ACCESS,
            "refresh_token": rt, "scope": "javis"}


def doi_token(f: dict) -> tuple:
    """(mã HTTP, JSON) cho POST token. Client công khai: không có client_secret, chỉ PKCE."""
    loai = f.get("grant_type")
    cid = str(f.get("client_id") or "")
    if loai == "authorization_code":
        ma, ver = str(f.get("code") or ""), str(f.get("code_verifier") or "")
        if not ma or not ver or not cid:
            return 400, {"error": "invalid_request"}
        _don_yeu_cau()
        rec = _ma.pop(_bam(ma), None)            # MỘT lần, kể cả khi các bước sau hỏng
        if not rec or rec["client"] != cid:
            return 400, {"error": "invalid_grant"}
        ru = f.get("redirect_uri")
        if ru and ru != rec["redirect_uri"]:
            return 400, {"error": "invalid_grant", "error_description": "redirect_uri không khớp"}
        if not secrets.compare_digest(_s256(ver), rec["challenge"]):
            return 400, {"error": "invalid_grant", "error_description": "PKCE không khớp"}
        with _KHOA:
            d = _doc()
            if cid not in d["clients"]:
                return 400, {"error": "invalid_client"}
            out = _cap_token(d, cid, secrets.token_urlsafe(12))
            _ghi(d)
        return 200, out
    if loai == "refresh_token":
        rt = str(f.get("refresh_token") or "")
        if not rt or not cid:
            return 400, {"error": "invalid_request"}
        with _KHOA:
            d = _doc()
            rec = d["tokens"].get(_bam(rt))
            if not rec or rec.get("loai") != "refresh" or rec.get("client") != cid:
                return 400, {"error": "invalid_grant"}
            if rec.get("thu_hoi"):
                # Refresh ĐÃ XOAY mà còn bị dùng lại: có người cầm bản sao. Thu hồi cả họ, bắt
                # cho phép lại, thay vì để hai bên cùng giữ một kết nối.
                for t in d["tokens"].values():
                    if t.get("ho") == rec.get("ho"):
                        t["thu_hoi"] = True
                _ghi(d)
                return 400, {"error": "invalid_grant", "error_description": "refresh đã dùng rồi"}
            if rec["het"] < time.time():
                return 400, {"error": "invalid_grant"}
            rec["thu_hoi"] = True
            out = _cap_token(d, cid, rec["ho"])
            _ghi(d)
        return 200, out
    return 400, {"error": "unsupported_grant_type"}


def kiem_token(raw: str) -> Optional[dict]:
    """Bản ghi của một access token còn hạn, hoặc None."""
    if not raw:
        return None
    rec = _doc()["tokens"].get(_bam(raw))
    if not rec or rec.get("loai") != "access" or rec.get("thu_hoi") or rec["het"] < time.time():
        return None
    return rec


def thu_hoi(raw: str) -> None:
    """RFC 7009: thu hồi một token bất kỳ, và cả họ của nó. Không nói token có tồn tại hay không."""
    if not raw:
        return
    with _KHOA:
        d = _doc()
        rec = d["tokens"].get(_bam(raw))
        if not rec:
            return
        for t in d["tokens"].values():
            if t.get("ho") == rec.get("ho"):
                t["thu_hoi"] = True
        _ghi(d)


def ngat_tat_ca() -> int:
    """Nút "Ngắt mọi kết nối": xoá sạch client và token. Trả số client đã xoá."""
    with _KHOA:
        d = _doc()
        n = len(d["clients"])
        _ghi({"clients": {}, "tokens": {}})
    _yeu_cau.clear()
    _ma.clear()
    return n


def so_ket_noi() -> int:
    """Số lần cho phép còn hiệu lực (mỗi họ refresh còn sống là một)."""
    now = time.time()
    return len({t.get("ho") for t in _doc()["tokens"].values()
                if t.get("loai") == "refresh" and not t.get("thu_hoi") and t.get("het", 0) > now})
