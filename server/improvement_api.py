"""Lazy owner-only M0 metadata routes. Trials and conditional activation stay disconnected."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse

import localefmt
from improvement_assets import capture_source
from improvement_blobs import AssetUnavailable
from improvement_store import ConflictError, SchemaError
from resonance_store import Principal

# `manual_apply`: the owner can apply an authorized candidate to one assistant chat (M2E).
# `activation` stays False: no conditional or automatic activation exists.
CAPABILITIES = {"capture": True, "trial": False, "activation": False, "manual_apply": True}


@dataclass
class ImprovementApiDeps:
    read_store: Callable
    write_store: Callable
    resolve_brain: Callable[[str], str]
    agent_key: Callable[[str, str], str] = lambda root, slug: ""


def strict_brain(value: str, *, default_root: Path, brains_root: Path) -> str:
    """Resolve an explicitly selected existing brain without the chat fallback."""
    value = str(value or "").strip()
    if value == "brain":
        path = Path(default_root)
    else:
        value = value.removeprefix("path:")
        path = Path(value)
        if not path.is_absolute():
            if not value or value in (".", "..") or any(char in value for char in "/\\:"):
                raise ValueError("unknown_brain")
            path = Path(brains_root) / value
    if not path.is_dir():
        raise ValueError("unknown_brain")
    return str(path.resolve(strict=True))


async def _body(request: Request, required: set[str], optional: set[str] | None = None) -> dict:
    try:
        data = await request.json()
    except Exception as error:
        raise ValueError("invalid_json") from error
    if not isinstance(data, dict) or not required.issubset(data) or set(data) - required - (optional or set()):
        raise ValueError("invalid_fields")
    key = data.get("event_key")
    if not isinstance(key, str) or not 8 <= len(key) <= 160:
        raise ValueError("invalid_event_key")
    return data


def _error(error: Exception):
    if isinstance(error, ConflictError):
        code = 409
        message = localefmt.chu("Phiên bản đã đổi. Hãy tải lại trước khi quyết định.",
                               "The version changed. Refresh before deciding.")
    elif isinstance(error, PermissionError):
        code = 404 if str(error).endswith("unavailable") else 403
        message = localefmt.chu("Không thể thực hiện trong phạm vi hiện tại.", "Unavailable in the current scope.")
    elif isinstance(error, (AssetUnavailable, SchemaError, OSError)):
        code = 503
        message = localefmt.chu("Chưa đọc được dữ liệu cải tiến. Hãy thử lại.",
                               "Improvement data is unavailable. Try again.")
    else:
        code = 404 if str(error) == "unknown_brain" else 422
        message = localefmt.chu("Thông tin cải tiến hoặc bộ não chưa hợp lệ.",
                               "Invalid improvement data or brain selection.")
    # Errors have host-defined codes only; never expose source bytes or storage paths.
    reason = str(error) if isinstance(error, (ValueError, PermissionError, AssetUnavailable, SchemaError)) else "storage_unavailable"
    return JSONResponse({"ok": False, "error": message, "reason": reason}, status_code=code)


def register(app, deps: ImprovementApiDeps):
    async def owner(brain: str):
        root = await asyncio.to_thread(deps.resolve_brain, brain)
        return Principal("owner", "owner", root)

    async def read_policy(principal):
        wrapper = await asyncio.to_thread(deps.read_store)
        policy = await asyncio.to_thread(wrapper.get_policy, principal) if wrapper else {"mode": "suggest", "version": 0}
        return policy, wrapper

    @app.get("/improvement-policy")
    async def improvement_policy(brain: str = "brain"):
        try:
            principal = await owner(brain)
            policy, _ = await read_policy(principal)
            return {"ok": True, "policy": policy, "capabilities": dict(CAPABILITIES)}
        except (ValueError, PermissionError, AssetUnavailable, SchemaError, OSError) as error:
            return _error(error)

    @app.put("/improvement-policy")
    async def improvement_set_policy(request: Request, brain: str = "brain"):
        try:
            principal = await owner(brain)
            data = await _body(request, {"mode", "expected_version", "event_key"})
            if data["mode"] not in ("off", "suggest") or type(data["expected_version"]) is not int:
                raise ValueError("unsupported_improvement_policy")
            wrapper = await asyncio.to_thread(deps.write_store)
            policy = await asyncio.to_thread(wrapper.set_policy, principal, data["mode"],
                expected_version=data["expected_version"], event_key=data["event_key"])
            return {"ok": True, "policy": policy, "capabilities": dict(CAPABILITIES)}
        except (ValueError, PermissionError, AssetUnavailable, SchemaError, OSError) as error:
            return _error(error)

    @app.get("/improvement-targets")
    async def improvement_targets(brain: str = "brain"):
        try:
            principal = await owner(brain)
            _, wrapper = await read_policy(principal)
            targets = await asyncio.to_thread(wrapper.targets, principal) if wrapper else []
            return {"ok": True, "targets": targets}
        except (ValueError, PermissionError, AssetUnavailable, SchemaError, OSError) as error:
            return _error(error)

    @app.post("/improvement-targets/capture")
    async def improvement_capture(request: Request, brain: str = "brain"):
        try:
            principal = await owner(brain)
            data = await _body(request, {"kind", "slug", "event_key"}, {"expected_generation"})
            policy, _ = await read_policy(principal)
            if policy["mode"] == "off":
                raise PermissionError("improvement_disabled")
            source, content = await asyncio.to_thread(capture_source, Path(principal.brain_id), data["kind"], data["slug"],
                agent_identity=lambda: deps.agent_key(principal.brain_id, data["slug"]))
            wrapper = await asyncio.to_thread(deps.write_store)
            result = await asyncio.to_thread(wrapper.capture, principal, source, content, event_key=data["event_key"],
                                              expected_generation=data.get("expected_generation"))
            return {"ok": True, "capture": result}
        except (ValueError, PermissionError, AssetUnavailable, SchemaError, OSError) as error:
            return _error(error)

    @app.get("/improvement-targets/{target_id}/revisions")
    async def improvement_revisions(target_id: str, brain: str = "brain"):
        try:
            principal = await owner(brain)
            _, wrapper = await read_policy(principal)
            if wrapper is None:
                raise PermissionError("target_unavailable")
            rows = await asyncio.to_thread(wrapper.revisions, principal, target_id)
            return {"ok": True, "revisions": rows}
        except (ValueError, PermissionError, AssetUnavailable, SchemaError, OSError) as error:
            return _error(error)

    @app.post("/improvement-targets/{target_id}/retire")
    async def improvement_retire(target_id: str, request: Request, brain: str = "brain"):
        try:
            principal = await owner(brain)
            data = await _body(request, {"expected_generation", "event_key"})
            wrapper = await asyncio.to_thread(deps.read_store)
            if wrapper is None:
                raise PermissionError("target_unavailable")
            await asyncio.to_thread(wrapper.revisions, principal, target_id)
            wrapper = await asyncio.to_thread(deps.write_store)
            result = await asyncio.to_thread(wrapper.retire, principal, target_id,
                expected_generation=data["expected_generation"], event_key=data["event_key"])
            return {"ok": True, "target": result}
        except (ValueError, PermissionError, AssetUnavailable, SchemaError, OSError) as error:
            return _error(error)

    return deps
