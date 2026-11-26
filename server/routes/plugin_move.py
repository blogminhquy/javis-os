"""Scope transfer requires a real owner session, as does installing foreign code."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse

import localefmt
import plugin_move


@dataclass
class PluginMoveDeps:
    co_phien: Callable
    brains: Callable
    default_root: Callable
    after_move: Callable


def register(app, deps: PluginMoveDeps):
    def root(value, brains):
        value = str(value or "")
        if value == "brain":
            value = str(deps.default_root())
        value = value.removeprefix("path:")
        for b in brains:
            path = Path(b["path"])
            if value in (b["name"], str(path)) and path.is_dir() and not path.is_symlink():
                return path
        raise plugin_move.MoveError("unknown_brain")

    def denied():
        return JSONResponse({"ok": False, "error": localefmt.chu(
            "Cần đăng nhập vào Javis để chuyển plugin.", "Sign in to Javis to move plugins.")}, status_code=401)

    def error(e):
        reason = str(e) if isinstance(e, plugin_move.MoveError) else "storage_error"
        messages = {
            "destination_conflict": ("Có plugin trùng slug ở phạm vi liên quan. Không ghi đè.", "A plugin with this slug already exists in a related scope. Nothing was overwritten."),
            "source_changed": ("Plugin đã thay đổi. Mở lại hộp chuyển và thử lại.", "The plugin changed. Reopen the move dialog and try again."),
            "different_filesystem": ("Hai nơi ở khác hệ thống tệp; chưa hỗ trợ chuyển tự động.", "Moving between different filesystems is not supported."),
        }
        message = messages.get(reason, ("Không thể chuyển plugin. Tải lại và kiểm tra nơi nguồn/đích.", "Cannot move the plugin. Refresh and check its source and destination."))
        return JSONResponse({"ok": False, "error": localefmt.chu(*message), "reason": reason},
                            status_code=409 if reason in ("destination_conflict", "source_changed", "same_target") else 400)

    @app.get("/plugins/move-options")
    async def options(request: Request, slug: str, scope: str, brain: str = "brain"):
        if not deps.co_phien(request):
            return denied()
        try:
            brains = deps.brains()
            source_root = root(brain, brains)
            return dict(plugin_move.inspect(slug, scope, source_root), brains=brains,
                        source_brain=str(source_root))
        except (ValueError, OSError) as e:
            return error(e)

    @app.post("/plugins/move")
    async def transfer(request: Request):
        if not deps.co_phien(request):
            return denied()
        try:
            d = await request.json()
            if not isinstance(d, dict):
                raise plugin_move.MoveError("invalid_request")
            brains = deps.brains()
            source = root(d.get("brain"), brains)
            scope = d.get("target_scope")
            if scope not in ("global", "selected"):
                raise plugin_move.MoveError("invalid_scope")
            values = d.get("target_brains")
            if scope == "selected" and (not isinstance(values, list) or not values
                                         or len(values) > len(brains) or not all(isinstance(v, str) for v in values)):
                raise plugin_move.MoveError("unknown_brain")
            targets = [root(value, brains) for value in values] if scope == "selected" else None
            r = plugin_move.configure(str(d.get("slug") or ""), d.get("scope"), source,
                                      targets, [Path(b["path"]) for b in brains],
                                      str(d.get("digest") or ""))
        except (ValueError, OSError, TypeError) as e:
            return error(e)
        # The transfer is already committed: refresh failures must never encourage a replay.
        try:
            deps.after_move([b["path"] for b in brains])
        except Exception:
            r["warning"] = localefmt.chu("Đã chuyển; chỉ mục chưa làm mới đủ.", "Moved; some indexes could not refresh.")
        return r
