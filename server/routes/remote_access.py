"""Remote access from Settings: turn the built-in Cloudflare Tunnel (0.242.0) or Tailscale serve (0.244.0) on or off.

The tunnel itself lives in remote_tunnel.py. This file only reads the form, enforces the two preconditions (a real
browser session, an admin password) and saves the settings the supervisor reads.
"""
import asyncio
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

import config as cfgmod
import localefmt
import remote_tunnel


@dataclass
class RemoteAccessDeps:
    """`browser_session_error(request)` returns a 403 response when the caller is not a signed-in browser (an API
    token must not be able to put the machine on the Internet), else None. It lives in main as _doi_phien_that."""
    browser_session_error: Callable


_DEPS: RemoteAccessDeps = None


def _err(vi: str, en: str, status: int, **extra):
    return JSONResponse({"ok": False, "error": localefmt.chu(vi, en), **extra}, status_code=status)


def _make_router() -> APIRouter:
    router = APIRouter()

    @router.get("/remote-access/status")
    def remote_access_status():
        return {"ok": True, **remote_tunnel.MANAGER.status()}

    @router.post("/remote-access/enable")
    async def remote_access_enable(request: Request, mode: str = Form("quick"), token: str = Form("")):
        if (loi := _DEPS.browser_session_error(request)) is not None:
            return loi
        if not cfgmod.auth_enabled():
            return _err("Đặt mật khẩu đăng nhập trước (Cài đặt, mục Tài khoản), rồi mới mở Javis ra Internet.",
                        "Set a login password first (Settings, Account), then open Javis to the Internet.",
                        409, need_password=True)
        mode = (mode or "").strip().lower()
        if mode not in remote_tunnel.MODES:
            return _err("Chế độ không hợp lệ.", "Unknown mode.", 400)
        patch = {"enabled": True, "mode": mode}
        if mode == "tailscale":
            # Checked here so the button answers at once; the supervisor still copes if this changes later.
            if not remote_tunnel.MANAGER.tailscale_binary():
                return _err("Máy này chưa cài Tailscale. Cài Tailscale, đăng nhập, rồi bấm Bật lại.",
                            "Tailscale is not installed on this computer. Install it, sign in, then turn this on again.",
                            409, need_tailscale=True)
            info = await asyncio.to_thread(remote_tunnel.MANAGER.tailscale_status, True)
            if info.get("backend") != "Running":
                return _err("Tailscale trên máy này chưa đăng nhập hoặc đang tắt. Mở app Tailscale để đăng nhập trước.",
                            "Tailscale on this computer is signed out or off. Open the Tailscale app and sign in first.",
                            409, need_tailscale_login=True)
        if mode == "token":
            pasted = (token or "").strip()
            tok = remote_tunnel.extract_token(pasted) if pasted else ""
            if pasted and not tok:
                return _err("Không tìm thấy token trong nội dung vừa dán. Hãy dán cả dòng lệnh Cloudflare đưa, "
                            "hoặc chuỗi bắt đầu bằng eyJ.",
                            "No tunnel token found in what you pasted. Paste the whole command Cloudflare shows, "
                            "or the string starting with eyJ.", 400)
            saved = str(remote_tunnel.section().get("token") or "")
            if not tok and not remote_tunnel.token_info(saved):
                return _err("Dán token của tunnel Cloudflare trước.", "Paste your Cloudflare tunnel token first.", 400)
            if tok:
                patch["token"] = tok
        cfgmod.update_settings({remote_tunnel.SETTINGS_KEY: patch})
        # start() stops the running tunnel first and waits for it, so keep it off the event loop.
        await asyncio.to_thread(remote_tunnel.MANAGER.start)
        # status() may ask the tailscale CLI (a subprocess), so not on the event loop either.
        return {"ok": True, **(await asyncio.to_thread(remote_tunnel.MANAGER.status))}

    @router.post("/remote-access/disable")
    async def remote_access_disable():
        cfgmod.update_settings({remote_tunnel.SETTINGS_KEY: {"enabled": False}})
        await asyncio.to_thread(remote_tunnel.MANAGER.stop)
        return {"ok": True, **(await asyncio.to_thread(remote_tunnel.MANAGER.status))}

    return router


async def _autostart():
    # kill_stray may shell out (tasklist, ps), so keep it off the event loop.
    await asyncio.to_thread(remote_tunnel.MANAGER.autostart)


async def _shutdown():
    await asyncio.to_thread(remote_tunnel.MANAGER.stop, 3, True)


def register(app, deps: RemoteAccessDeps):
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    # Starts the tunnel after a reboot or an update when the owner left it on; stops it with the server.
    app.on_event("startup")(_autostart)
    app.on_event("shutdown")(_shutdown)
    return router
