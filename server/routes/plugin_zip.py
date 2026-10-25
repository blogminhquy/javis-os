"""Plugins page: install one plugin from a .zip file (owner request 2026-10-25).

Same two rules as `routes/packs.py`, for the same reason: installing a plugin puts foreign Python
code in the server process.

- Every route needs a REAL login session, independent of `gate_active()` (which is False on a
  local install without a password), and there is no API-token path: automation has no
  business installing code.
- Two steps. `POST /plugins/inspect` checks and stages the zip and returns what is about to
  happen plus its `sha256`; `POST /plugins/install` only installs that same sha256.

A full store pack zip dropped here is not turned away: `inspect` reports it with `kind: "pack"`
and the result of the PACK inspector, so the dashboard opens the pack confirmation screen and
installs it through `/packs/install`. One pack installer, one set of rules.
"""
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

import localefmt
import pack_install
import plugin_install

MAX_UPLOAD = pack_install.MAX_ZIP


@dataclass
class PluginZipDeps:
    co_phien: Callable[[Request], bool]
    brain_root: Callable[[str], str]
    # Same refresh as /plugins/toggle: hub route cache + operations index of that brain.
    after_install: Callable[[str], None]


_DEPS: PluginZipDeps = None


def _deny():
    return JSONResponse({"ok": False, "error": localefmt.chu("Cần đăng nhập vào Javis để cài plugin.",
                                                         "Sign in to Javis to install plugins.")},
                        status_code=401)


async def read_capped(file: UploadFile):
    """Read in chunks and stop past the cap, so a huge upload never sits in RAM whole."""
    parts, total = [], 0
    while True:
        b = await file.read(1 << 20)
        if not b:
            break
        total += len(b)
        if total > MAX_UPLOAD:
            return None
        parts.append(b)
    return b"".join(parts)


def _make_router() -> APIRouter:
    router = APIRouter()

    @router.post("/plugins/inspect")
    async def plugins_inspect(request: Request, file: UploadFile = File(...),
                              brain: str = Form("brain")):
        """Check and stage a plugin zip. Nothing lands in the plugins folder yet."""
        if not _DEPS.co_phien(request):
            return _deny()
        data = await read_capped(file)
        if data is None:
            return JSONResponse({"ok": False, "stage": "verify",
                                 "error": localefmt.chu(f"tệp quá lớn, trần {MAX_UPLOAD // 1024 // 1024}MB",
                                                        f"file too large, limit {MAX_UPLOAD // 1024 // 1024}MB")},
                                status_code=413)
        name = (file.filename or "").strip()
        r = plugin_install.inspect(data, name, vault_root=_DEPS.brain_root(brain or "brain"))
        if r.get("ok") and r.get("kind") == "pack":
            r = pack_install.soi(data, name)
            r["kind"] = "pack"
        return r

    @router.post("/plugins/install")
    async def plugins_install(request: Request):
        if not _DEPS.co_phien(request):
            return _deny()
        d = await request.json()
        r = plugin_install.install(str(d.get("staging_id") or ""),
                                   str(d.get("consent_sha256") or ""),
                                   replace=d.get("replace") is True)
        if r.get("ok"):
            _DEPS.after_install(str(d.get("brain") or "brain"))
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    return router


def register(app, deps: PluginZipDeps):
    """Mount the router. Call it at the fixed spot in main.py (route_table.json locks order)."""
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    return router
