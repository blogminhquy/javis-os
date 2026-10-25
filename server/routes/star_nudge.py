"""Lời mời tặng sao GitHub: hai route cho dashboard (logic ở star_nudge.py).

- `POST /star-nudge/check {reason}`: dashboard báo một khoảnh khắc (heart, work, load, manual);
  server trả có mời không, mời bằng lời chào nào, và số sao thật kèm mốc kế tiếp. Lần mời được
  ghi ngay tại đây (giờ hiện, cột mốc đã ăn mừng) để hai thiết bị mở cùng lúc không cùng mời.
- `POST /star-nudge/action {action}`: opened, later, dismiss, never, done.

Trạng thái nằm trong settings.json (khối `star_nudge`), nên mọi thiết bị của chủ máy dùng chung.
"""
import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import star_nudge as sn


@dataclass
class StarNudgeDeps:
    read_settings: Callable[[], dict]
    update_settings: Callable[[dict], dict]
    read_sql: Callable[..., list]       # SessionStore._read của kho hội thoại
    state_dir: Path
    version: Callable[[], str]


_DEPS: StarNudgeDeps = None


def _st():
    return sn.trang_thai((_DEPS.read_settings() or {}).get("star_nudge"))


def _ghi(st: dict):
    _DEPS.update_settings({"star_nudge": st})


async def _body(request: Request) -> dict:
    try:
        b = await request.json()
    except Exception:             # noqa: BLE001 - thân rỗng hay không phải JSON: coi như không có gì
        return {}
    return b if isinstance(b, dict) else {}


def _make_router() -> APIRouter:
    router = APIRouter()

    @router.post("/star-nudge/check")
    async def star_check(request: Request):
        ly_do = str((await _body(request)).get("reason") or "")
        if ly_do not in sn.LY_DO:
            return JSONResponse({"ok": False, "error": "reason"}, status_code=400)
        now = time.time()
        ver = _DEPS.version() or ""
        st = await asyncio.to_thread(_st)
        dung = await asyncio.to_thread(sn.dem_dung, _DEPS.read_sql, now)
        kk = sn.chon_khoanh_khac(st, ly_do, dung, ver, now)
        if not kk:
            # Lần đầu mở app sau khi có tính năng này: ghi phiên bản hiện tại làm mốc, để lần
            # cập nhật SAU mới tính là "vừa có bản mới" (không coi lần cài đầu là cập nhật).
            if ly_do == "load" and st["seen_version"] != ver:
                await asyncio.to_thread(_ghi, dict(st, seen_version=ver))
            return {"ok": True, "show": False}
        kind, n = kk
        await asyncio.to_thread(_ghi, sn.danh_dau_da_hien(st, kind, n, ver, now))
        sao = await asyncio.to_thread(sn.so_sao, Path(_DEPS.state_dir) / "github_stars.json", now)
        return {"ok": True, "show": True, "kind": kind, "n": n, "url": sn.REPO_URL,
                "count": sn.goi_sao(sao), "state": st["state"]}

    @router.post("/star-nudge/action")
    async def star_action(request: Request):
        hd = str((await _body(request)).get("action") or "")
        if hd not in sn.HANH_DONG:
            return JSONResponse({"ok": False, "error": "action"}, status_code=400)
        st = await asyncio.to_thread(_st)
        moi = sn.ap_hanh_dong(st, hd, time.time())
        await asyncio.to_thread(_ghi, moi)
        return {"ok": True, "state": moi["state"]}

    return router


def register(app, deps: StarNudgeDeps):
    """Mount the router. Call it at the fixed spot in main.py (route_table.json locks order)."""
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    return router
