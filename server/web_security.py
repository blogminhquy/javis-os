"""
web_security.py - Chống CSRF + DNS-rebinding cho web API cục bộ của Javis.

Vì sao cần: dashboard nghe ở localhost:7777. Khi CHƯA đặt mật khẩu (chạy cá nhân trên máy),
một trang web độc bất kỳ trong trình duyệt của user có thể:
  1. fetch/POST tới http://localhost:7777/... → server VẪN xử lý (CORS chỉ chặn ĐỌC kết quả,
     không chặn request chạy) → hành động có side-effect vẫn xảy ra (CSRF-to-localhost).
  2. Trỏ một tên miền của kẻ tấn công về 127.0.0.1 (DNS-rebinding) để lách kiểm tra origin.

Lớp phòng thủ (tách khỏi main.py để test được mà không nạp cả app):
  - Request GHI (POST/PUT/DELETE/PATCH) có Origin CHÉO (khác Host, không thuộc allowlist) → chặn 403.
    Cùng-origin (Origin==Host) và client không-trình-duyệt (không gửi Origin, vd Claude CLI, curl)
    KHÔNG bị ảnh hưởng → 0 rủi ro khoá nhầm.
  - Khi CHƯA có cổng đăng nhập (no-auth): Host phải là localhost / IP / tên miền cấu hình - tên
    miền lạ (dấu hiệu DNS-rebinding) bị chặn. Khi ĐÃ bật auth thì bỏ qua bước Host (tránh khoá nhầm
    deploy sau reverse-proxy tên miền chưa khai) - lúc đó cookie + Origin-check đã đủ.

Allowlist: localhost/127.0.0.1/::1 + tên miền custom (settings.domain.custom) + env JAVIS_ALLOWED_HOSTS.
"""
from __future__ import annotations

import ipaddress
import os
import time

import config as cfgmod

_LOCALHOST = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
MUTATING = {"POST", "PUT", "DELETE", "PATCH"}

# GET có TÁC DỤNG PHỤ THẬT: /workflows/run chạy workflow FULL QUYỀN, /workflows/resume duyệt
# một node ghi rồi thực thi (không hoàn tác được). Cả hai là SSE nên buộc phải là GET -
# EventSource không POST được.
#
# Vì sao Origin-check ở csrf_decision KHÔNG cứu được nhóm này: điều hướng top-level bằng GET
# (location.href) KHÔNG gửi Origin, trong khi cookie javis_session đặt SameSite=lax thì VẪN đi
# kèm. Nghĩa là một trang lạ chỉ cần đẩy trình duyệt sang URL này là lệnh chạy trên máy nạn
# nhân, kể cả khi đã bật mật khẩu. Slug workflow lại đoán được (bộ mẫu có sẵn
# 'research-and-write'), nên /workflows/run là đường thật sự hở.
#
# Chốt bằng Sec-Fetch-Site: mọi trình duyệt hiện đại đều gửi header này và trang web KHÔNG đặt
# đè được; client không-trình-duyệt (curl, Claude CLI, Codex) không gửi → không khoá nhầm.
SIDE_EFFECT_GET = frozenset({"/workflows/run", "/workflows/resume"})

_cache = {"hosts": None, "ts": 0.0}
_CACHE_TTL = 5.0


def external_base(url_scheme, host, xf_proto="", xf_host="") -> str:
    """Địa chỉ gốc NHƯ NGƯỜI DÙNG THẤY, dùng để dựng OAuth redirect_uri.

    Chạy sau reverse proxy (Traefik/Caddy trên VPS) thì uvicorn thấy http nội bộ trong khi
    trình duyệt đang https - dựng redirect từ request.base_url ra http://... là Meta/Google
    từ chối ("không dùng kết nối bảo mật", vụ Hostinger 2026-07-27). Ưu tiên header
    X-Forwarded-Proto/Host do proxy đặt; thiếu thì rơi về scheme/host của chính request.

    AN TOÀN: giá trị này CHỈ được nhét vào redirect_uri gửi cho nhà cung cấp OAuth - kẻ tự
    đặt header chỉ phá được luồng đăng nhập của CHÍNH request đó, và provider còn đối chiếu
    whitelist redirect của app. TUYỆT ĐỐI không dùng hàm này cho quyết định quyền/địa chỉ
    client (đường _AUTH_LOCAL_EXACT vẫn phải dựa vào request.client.host thật)."""
    scheme = (xf_proto or "").split(",")[0].strip().lower() or (url_scheme or "http")
    h = (xf_host or "").split(",")[0].strip() or (host or "")
    return f"{scheme}://{h}"


def host_only(v) -> str:
    """Bóc hostname (bỏ scheme + path + port). Giữ IPv6 trong ngoặc: '[::1]:7777' → '::1'."""
    v = (v or "").strip().lower()
    if "://" in v:
        v = v.split("://", 1)[1]
    v = v.split("/", 1)[0]
    if v.startswith("["):            # [::1]:7777 hoặc [::1]
        return v[1:].split("]", 1)[0]
    if v.count(":") == 1:            # host:port
        return v.split(":", 1)[0]
    return v                          # bare host / bare IPv6 (hiếm)


def _is_ip(h: str) -> bool:
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def _compute_hosts() -> set:
    hosts = set(_LOCALHOST)
    try:
        dom = ((cfgmod.read_settings().get("domain") or {}).get("custom") or "").strip().lower()
        dom = host_only(dom)
        if dom:
            hosts.add(dom)
    except Exception:
        pass
    for h in (os.getenv("JAVIS_ALLOWED_HOSTS", "") or "").split(","):
        h = host_only(h)
        if h:
            hosts.add(h)
    return hosts


def allowed_web_hosts(_now=None) -> set:
    """Allowlist hostname (cache ngắn để khỏi đọc settings mỗi request)."""
    now = _now if _now is not None else time.time()
    if _cache["hosts"] is None or (now - _cache["ts"]) > _CACHE_TTL:
        _cache["hosts"] = _compute_hosts()
        _cache["ts"] = now
    return _cache["hosts"]


def invalidate():
    _cache["hosts"] = None


def navigation_decision(path: str, sec_fetch_site):
    """Chặn GET có tác dụng phụ khi bị TRANG KHÁC kích hoạt. Hàm THUẦN - dễ test.

    Cho qua khi Sec-Fetch-Site là:
      - thiếu hẳn  → client không-trình-duyệt (curl, Claude CLI, Codex, plugin in-process)
      - 'none'     → user tự gõ URL / mở bookmark, tức là chính chủ chủ động
      - 'same-origin' → chính dashboard gọi (studio.js dùng URL tương đối)
    Chặn 'cross-site' và 'same-site': cả hai đều nghĩa là một trang khác khởi xướng.

    Đánh đổi đã biết: trình duyệt quá cũ không gửi Sec-Fetch-Site sẽ lọt. Chấp nhận, vì siết
    hơn nữa (bắt buộc phải có header) sẽ khoá luôn curl/CLI - thứ mà cả hệ đang dựa vào.
    """
    if path not in SIDE_EFFECT_GET:
        return None
    site = (sec_fetch_site or "").strip().lower()
    if site in ("", "none", "same-origin"):
        return None
    return 403, "lệnh có tác dụng phụ chỉ chạy được từ chính dashboard"


def csrf_decision(method: str, host_header: str, origin_header, gate_active: bool):
    """Trả None nếu CHO QUA, hoặc (status_code, message) nếu CHẶN. Hàm THUẦN - dễ test."""
    host = host_only(host_header)
    allowed = None
    # 1) CSRF: ghi + có Origin chéo (khác host, ngoài allowlist) → chặn.
    if method.upper() in MUTATING and origin_header:
        oh = host_only(origin_header)
        if oh != host:
            allowed = allowed_web_hosts()
            if oh not in allowed:
                return 403, "cross-origin request bị chặn"
    # 2) DNS-rebinding: chỉ siết Host khi CHƯA có cổng đăng nhập (trường hợp hở thật sự).
    if not gate_active and host:
        if not _is_ip(host):
            if allowed is None:
                allowed = allowed_web_hosts()
            if host not in allowed:
                return 403, "host không được phép"
    return None
