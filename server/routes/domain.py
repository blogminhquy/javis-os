"""Tên miền riêng + HTTPS tự động (Caddy On-Demand TLS).

Bóc nguyên văn khỏi main.py ở 0.9.243. Phụ thuộc duy nhất còn lại vào main là `_deploy_mode`,
nhận qua deps.

Lưu ý về `/tls-check`: nó nằm trong danh sách đường dẫn CÔNG KHAI của middleware xác thực
(`_AUTH_PUBLIC_EXACT` trong main.py). Danh sách đó khớp theo CHUỖI đường dẫn và ở lại main,
nên việc bóc file không đụng tới nó. Nhưng đừng bao giờ đổi đường dẫn này: Caddy gọi nó
TRƯỚC khi xin chứng chỉ, mất quyền công khai là nó nhận 401 thay vì 200/403 và việc cấp
chứng chỉ trên production hỏng.
"""
import os
import re
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

import config as cfgmod
import localefmt


@dataclass
class DomainDeps:
    """_deploy_mode ở lại main (khối cập nhật cũng dùng nó) nên tiêm vào đây."""
    deploy_mode: Callable[[], str]


_DEPS: DomainDeps = None

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_PUBLIC_IP_CACHE = {"ip": None, "ts": 0.0}


def _norm_domain(d):
    d = (d or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "")
    d = d.split("/")[0].split(":")[0].strip().strip(".")
    return d


def _domain_deploy_target(request: Request = None):
    """Phân biệt Hostinger (Traefik do hPanel quản lý) với VPS Docker/Caddy.

    Hostinger không cho container sửa label Traefik đang chạy, vì vậy UI chỉ có thể lưu
    tên miền + kiểm tra DNS rồi hướng dẫn đúng bước Environment/Redeploy. Compose mới đặt
    JAVIS_DEPLOY_TARGET rõ ràng; nhận diện hostname .hstgr.cloud giữ tương thích bản cũ.
    """
    explicit = (os.getenv("JAVIS_DEPLOY_TARGET", "") or "").strip().lower()
    if explicit in ("hostinger", "vps", "native", "windows"):
        return explicit
    host = ""
    if request is not None:
        host = (request.headers.get("host", "") or "").split(":")[0].strip().lower()
    if host.endswith(".hstgr.cloud"):
        return "hostinger"
    mode = _DEPS.deploy_mode()
    return "vps" if mode == "docker" else mode


def _detect_public_ip():
    import time as _t
    now = _t.time()
    if _PUBLIC_IP_CACHE["ip"] and now - _PUBLIC_IP_CACHE["ts"] < 600:
        return _PUBLIC_IP_CACHE["ip"]
    ip = None
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"):
        try:
            import urllib.request
            with urllib.request.urlopen(url, timeout=4) as r:
                ip = (r.read().decode() or "").strip()
            if ip:
                break
        except Exception:
            ip = None
    if ip:
        _PUBLIC_IP_CACHE.update(ip=ip, ts=now)
    return ip


def _req_is_secure(request: Request) -> bool:
    """Request hiện tại có phải HTTPS không (tôn trọng proxy qua X-Forwarded-Proto)."""
    xf = (request.headers.get("x-forwarded-proto", "") or "").split(",")[0].strip().lower()
    if xf:
        return xf == "https"
    return request.url.scheme == "https"


async def _probe_https(domain: str):
    """Mở https://<domain>/health TỪ CHÍNH server → buộc Caddy On-Demand cấp chứng chỉ ở lần đầu
    và xác minh HTTPS chạy thật. Trả (active: bool, reason: str) với lý do dễ hiểu để hướng dẫn."""
    if not domain:
        return False, localefmt.chu("Chưa đặt tên miền", "No domain set")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            r = await client.get(f"https://{domain}/health")
        if r.status_code < 500:
            return True, localefmt.chu("HTTPS đang hoạt động", "HTTPS is working")
        return False, localefmt.chu(f"Máy chủ trả HTTP {r.status_code}", f"The server returned HTTP {r.status_code}")
    except Exception as e:
        s = (str(e) + " " + type(e).__name__).lower()
        if "ssl" in s or "certificate" in s or "verify" in s:
            return False, localefmt.chu("Chứng chỉ chưa hợp lệ - DNS chưa trỏ đúng hoặc chứng chỉ chưa cấp xong",
                                        "Certificate not valid yet - DNS does not point here yet or the certificate is still being issued")
        if "connect" in s or "timeout" in s or "timed out" in s or "refused" in s:
            return False, localefmt.chu("Không kết nối được cổng 443 - Caddy/HTTPS chưa chạy, hoặc cổng 80/443 bị proxy khác chiếm",
                                        "Cannot connect to port 443 - Caddy/HTTPS is not running, or ports 80/443 are taken by another proxy")
        return False, type(e).__name__


def _make_router() -> APIRouter:
    router = APIRouter()

    @router.get("/tls-check")
    async def tls_check(domain: str = ""):
        """Cổng gác cho Caddy On-Demand TLS: chỉ 200 khi hostname == tên miền admin đã đặt,
        chống kẻ trỏ DNS bừa vào IP ép server xin cert vô hạn (cạn rate-limit Let's Encrypt)."""
        want = _norm_domain((cfgmod.read_settings().get("domain", {}) or {}).get("custom", ""))
        got = _norm_domain(domain)
        if want and got and got == want:
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False}, status_code=403)

    @router.post("/domain")
    async def domain_set(domain: str = Form("")):
        d = _norm_domain(domain)
        if d and not _DOMAIN_RE.match(d):
            return JSONResponse({"ok": False, "error": localefmt.chu("Tên miền không hợp lệ (vd: javis.tencuaban.com)",
                                                                   "Invalid domain (e.g. javis.yourdomain.com)")}, status_code=400)
        cfg = cfgmod.read_settings()
        cfg.setdefault("domain", {})
        cfg["domain"]["custom"] = d
        cfgmod.write_settings(cfg)
        return {"ok": True, "domain": d}

    @router.get("/domain/status")
    async def domain_status(request: Request):
        cfg = cfgmod.read_settings()
        dom = cfg.get("domain", {}) or {}
        custom = _norm_domain(dom.get("custom", ""))
        ssl_enabled = bool(dom.get("ssl_enabled", False))
        server_ip = _detect_public_ip()
        dns_ip = None
        dns_ok = False
        if custom:
            try:
                import socket as _sock
                dns_ip = _sock.gethostbyname(custom)
                dns_ok = bool(server_ip) and dns_ip == server_ip
            except Exception:
                dns_ip = None
        host = (request.headers.get("host", "") or "").split(":")[0].strip().lower()
        on_domain = bool(custom) and host == custom
        secure_now = _req_is_secure(request)
        # SSL: nếu đang mở chính tên miền qua HTTPS thì chắc chắn đang chạy; nếu không, chủ động probe.
        ssl_active, ssl_reason = False, localefmt.chu("Chưa đặt tên miền", "No domain set")
        if custom:
            if on_domain and secure_now:
                ssl_active, ssl_reason = True, localefmt.chu("Bạn đang mở qua HTTPS", "You are browsing over HTTPS")
            else:
                ssl_active, ssl_reason = await _probe_https(custom)
        target = _domain_deploy_target(request)
        route_domain = _norm_domain(os.getenv("DOMAIN_NAME", ""))
        return {"domain": custom, "server_ip": server_ip, "dns_ip": dns_ip,
                "dns_ok": dns_ok, "on_domain": on_domain, "secure_now": secure_now,
                "deploy_mode": _DEPS.deploy_mode(), "ssl_enabled": ssl_enabled,
                "ssl_active": ssl_active, "ssl_reason": ssl_reason,
                "deployment_target": target, "route_domain": route_domain,
                "ui_can_enable_ssl": target != "hostinger",
                "requires_redeploy": target == "hostinger" and bool(custom) and custom != route_domain}

    @router.post("/domain/ssl")
    async def domain_ssl(request: Request, enabled: str = Form("1")):
        """Bật/tắt SSL cho tên miền. Bật → lưu ý định + chủ động probe HTTPS (buộc Caddy cấp chứng chỉ),
        trả trạng thái thật + gợi ý lệnh nếu chưa bật được (bản Docker cần compose HTTPS)."""
        on = str(enabled).strip().lower() in ("1", "true", "yes", "on")
        cfg = cfgmod.read_settings()
        cfg.setdefault("domain", {})
        custom = _norm_domain(cfg["domain"].get("custom", ""))
        if on and not custom:
            return JSONResponse({"ok": False, "error": localefmt.chu("Hãy nhập và lưu tên miền trước khi bật SSL.",
                                                                   "Enter and save a domain before turning on SSL.")}, status_code=400)
        if on and _domain_deploy_target(request) == "hostinger":
            return JSONResponse({
                "ok": False,
                "error": localefmt.chu(
                    "Hostinger quản lý HTTPS bằng Traefik. Hãy đặt DOMAIN_NAME trong Docker Manager rồi Redeploy; Javis không thể sửa route của hPanel từ bên trong container.",
                    "Hostinger manages HTTPS with Traefik. Set DOMAIN_NAME in Docker Manager and Redeploy; Javis cannot change hPanel routes from inside the container."),
                "hostinger": True,
                "domain": custom,
                "docs": "https://github.com/blogminhquy/javis-os/blob/main/docs/15-thuong-hieu-ten-mien.md",
            }, status_code=409)
        cfg["domain"]["ssl_enabled"] = on
        cfgmod.write_settings(cfg)
        if not on:
            return {"ok": True, "enabled": False, "ssl_active": False, "ssl_reason": localefmt.chu("Đã tắt SSL", "SSL turned off")}
        active, reason = await _probe_https(custom)
        resp = {"ok": True, "enabled": True, "ssl_active": active, "ssl_reason": reason}
        if not active and _DEPS.deploy_mode() == "docker":
            resp["hint_cmd"] = "docker compose -f docker-compose.yml -f docker-compose.https.yml up -d"
        return resp

    return router


def register(app, deps: DomainDeps):
    """Gắn router vào app. Gọi ĐÚNG vị trí dòng cũ trong main.py - xem routes/__init__.py."""
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    return router
