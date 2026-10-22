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


# What a request to https://<domain>/tls-check?domain=<domain> answered, reduced to one code (0.248.0).
#   ok           this very server answered over a valid certificate
#   no_route     the proxy in front (Traefik on Hostinger) has no route for this hostname: its own 404
#   cert_pending the route reaches this server, but the certificate is not issued yet (only works unverified)
#   bad_gateway  the proxy has a route but cannot reach the app (502/503/504)
#   other_javis  another Javis answered (a second stack on the same VPS, or the domain saved differently there)
#   other_site   some other website answered: DNS or the route points somewhere else
#   cert_invalid the certificate is wrong and the page behind it is not ours either
#   unreachable  nothing answers on port 443
# Why /tls-check: it is public, and it answers 200 only when the hostname is the domain saved on THIS server,
# so it tells this Javis apart from any other site or Javis behind the same address.
PROBE_CODES = ("ok", "no_route", "cert_pending", "bad_gateway", "other_javis", "other_site", "cert_invalid",
               "unreachable")


def _classify_answer(status: int, body: str, verified: bool) -> str:
    """Code for an HTTP answer to /tls-check. Pure, so tests can feed it real Traefik and Javis answers."""
    text = (body or "").strip()
    javis_json = text.startswith("{") and '"ok"' in text
    if status == 200 and javis_json and '"ok": true' in text.replace('":true', '": true'):
        return "ok" if verified else "cert_pending"
    if status == 403 and javis_json:
        return "other_javis"
    if status == 404 and text.lower().startswith("404 page not found"):
        return "no_route"   # Traefik's own answer when no router matches the Host
    if status in (502, 503, 504):
        return "bad_gateway"
    return "other_site" if verified else "cert_invalid"


def _probe_reason(code: str, hostinger: bool) -> str:
    if code == "ok":
        return localefmt.chu("HTTPS đang hoạt động", "HTTPS is working")
    if code == "no_route":
        if hostinger:
            return localefmt.chu("DNS đã tới VPS nhưng Traefik của Hostinger chưa nhận tên miền này: dòng "
                                 "traefik...rule=Host(...) của dự án vẫn là tên cũ. Đặt DOMAIN_NAME đúng tên miền "
                                 "này trong Docker Manager (hoặc sửa thẳng dòng Host trong YAML) rồi bấm Redeploy.",
                                 "DNS reaches the VPS but Hostinger's Traefik has no route for this domain: the "
                                 "project's traefik...rule=Host(...) still holds the old name. Set DOMAIN_NAME to this "
                                 "domain in Docker Manager (or edit the Host line in the YAML), then Redeploy.")
        return localefmt.chu("DNS đã tới máy chủ nhưng proxy phía trước chưa có đường cho tên miền này.",
                             "DNS reaches the server but the proxy in front has no route for this domain.")
    if code == "cert_pending":
        return localefmt.chu("Đường đã thông tới Javis nhưng chứng chỉ chưa cấp xong. Đợi vài phút rồi Kiểm tra lại; "
                             "lâu hơn 10 phút thì xem cổng 80 có mở cho Let's Encrypt không.",
                             "The route reaches Javis but the certificate is not issued yet. Wait a few minutes and "
                             "check again; after 10 minutes, check that port 80 is open for Let's Encrypt.")
    if code == "bad_gateway":
        return localefmt.chu("Proxy đã nhận tên miền nhưng không gọi được Javis (502). Kiểm tra container Javis đang "
                             "chạy và nhãn loadbalancer.server.port=7777.",
                             "The proxy knows the domain but cannot reach Javis (502). Check that the Javis "
                             "container is running and loadbalancer.server.port=7777.")
    if code == "other_javis":
        return localefmt.chu("Tên miền này đang mở một bản Javis KHÁC (ví dụ stack thứ hai trên cùng VPS). Kiểm tra "
                             "DOMAIN_NAME của từng stack.",
                             "This domain opens a DIFFERENT Javis (for example a second stack on the same VPS). "
                             "Check each stack's DOMAIN_NAME.")
    if code in ("other_site", "cert_invalid"):
        return localefmt.chu("Tên miền đang mở một trang khác, không phải Javis này. Kiểm tra bản ghi DNS và cấu hình "
                             "proxy.", "The domain opens another site, not this Javis. Check the DNS record and the "
                             "proxy setup.")
    if hostinger:
        return localefmt.chu("Không kết nối được cổng 443 của VPS.", "Cannot connect to the VPS on port 443.")
    return localefmt.chu("Không kết nối được cổng 443 - Caddy/HTTPS chưa chạy, hoặc cổng 80/443 bị proxy khác chiếm",
                         "Cannot connect to port 443 - Caddy/HTTPS is not running, or ports 80/443 are taken by "
                         "another proxy")


async def _probe_https(domain: str, hostinger: bool = False):
    """Open https://<domain>/tls-check FROM this server and say what answered: (active, reason, code).

    On a Caddy VPS the first request also makes On-Demand TLS issue the certificate. Before 0.248.0 this only said
    "certificate not valid yet - DNS not pointing here or not issued", even when DNS was already right, so an owner
    on Hostinger whose Traefik route still held the old name had nothing to act on (customer report 2026-10-20).
    """
    if not domain:
        return False, localefmt.chu("Chưa đặt tên miền", "No domain set"), ""
    import httpx
    url = f"https://{domain}/tls-check?domain={domain}"
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            r = await client.get(url)
        code = _classify_answer(r.status_code, r.text[:300], True)
    except Exception as e:
        s = (str(e) + " " + type(e).__name__).lower()
        if "ssl" in s or "certificate" in s or "verify" in s:
            # Look behind the bad certificate: Traefik serves its default one both for "no route" and for
            # "route exists, certificate not issued yet", and only the page behind it tells the two apart.
            try:
                async with httpx.AsyncClient(timeout=12, follow_redirects=True, verify=False) as client:
                    r = await client.get(url)
                code = _classify_answer(r.status_code, r.text[:300], False)
            except Exception:
                code = "cert_invalid"
        else:
            code = "unreachable"
    return code == "ok", _probe_reason(code, hostinger), code


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
        target = _domain_deploy_target(request)
        ssl_active, ssl_reason, ssl_code = False, localefmt.chu("Chưa đặt tên miền", "No domain set"), ""
        if custom:
            if on_domain and secure_now:
                ssl_active, ssl_reason, ssl_code = True, localefmt.chu("Bạn đang mở qua HTTPS",
                                                                       "You are browsing over HTTPS"), "ok"
            else:
                ssl_active, ssl_reason, ssl_code = await _probe_https(custom, hostinger=target == "hostinger")
        route_domain = _norm_domain(os.getenv("DOMAIN_NAME", ""))
        return {"domain": custom, "server_ip": server_ip, "dns_ip": dns_ip,
                "dns_ok": dns_ok, "on_domain": on_domain, "secure_now": secure_now,
                "deploy_mode": _DEPS.deploy_mode(), "ssl_enabled": ssl_enabled,
                "ssl_active": ssl_active, "ssl_reason": ssl_reason, "ssl_code": ssl_code,
                "deployment_target": target, "route_domain": route_domain,
                "ui_can_enable_ssl": target != "hostinger",
                # Working HTTPS wins over the env: owners without an Environment box edit the Host(...) line in the
                # YAML directly (as the compose comment says), which leaves DOMAIN_NAME at "localhost" for good.
                "requires_redeploy": (target == "hostinger" and bool(custom) and custom != route_domain
                                      and not ssl_active)}

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
        active, reason, code = await _probe_https(custom)
        resp = {"ok": True, "enabled": True, "ssl_active": active, "ssl_reason": reason, "ssl_code": code}
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
