"""Owner routes for activation (M2E) and canary observation, promotion and grants (M3)."""
from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from typing import Callable

from fastapi import Request

from improvement_api import _body, _error
from improvement_blobs import AssetUnavailable
from improvement_store import ConflictError, SchemaError
from resonance_store import Principal

_ERRORS = (ValueError, PermissionError, AssetUnavailable, SchemaError, OSError, sqlite3.Error)
# Where an applied overlay is served: the in-process javis_use_skill of API engines in the
# assistant's own dashboard chat. CLI engines also read .claude/skills natively.
_COVERAGE = {"served": ["api_engines"], "not_served": ["claude_code", "codex", "grok", "antigravity"]}


@dataclass
class ActivationApiDeps:
    activations: Callable  # () -> improvement_activation.Activations (write store)
    resolve_brain: Callable[[str], str]
    read_store: Callable = lambda: True  # () -> installed read store or None; None means nothing to list
    owner_session: Callable = lambda request: None  # request -> denial Response or None (browser session only)
    canaries: Callable = None  # () -> improvement_canary.Canaries over the same write store


def _fail(error):
    # A unique pointer race is a version conflict; other SQLite failures are unavailability.
    if isinstance(error, sqlite3.IntegrityError):
        return _error(ConflictError("activation_scope_busy"))
    return _error(OSError("storage_unavailable") if isinstance(error, sqlite3.Error) else error)


def register(app, deps: ActivationApiDeps):
    async def owner(brain: str):
        root = await asyncio.to_thread(deps.resolve_brain, brain)
        return Principal("owner", "owner", root)

    @app.get("/improvement-activations")
    async def activation_list(brain: str = "brain", target_id: str | None = None):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                # Fresh install: never create the runtime database just to say "nothing applied".
                return {"ok": True, "activations": [], "coverage": _COVERAGE}
            service = await asyncio.to_thread(deps.activations)
            # Record suspensions first so the owner sees the pointer the next turn will really use.
            await asyncio.to_thread(service.reconcile, principal)
            rows = await asyncio.to_thread(service.list, principal, target_id=target_id)
            return {"ok": True, "activations": rows, "coverage": _COVERAGE}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-activations")
    async def activation_apply(request: Request, brain: str = "brain"):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            data = await _body(request, {"candidate_id", "agent_slug", "event_key"}, {"allocation_pct"})
            service = await asyncio.to_thread(deps.activations)
            result = await asyncio.to_thread(service.apply, principal, data["candidate_id"], data["agent_slug"],
                                             event_key=data["event_key"], allocation_pct=data.get("allocation_pct"))
            return {"ok": True, "activation": result}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-activations/{activation_id}/revert")
    async def activation_revert(activation_id: str, request: Request, brain: str = "brain"):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            data = await _body(request, {"expected_generation", "event_key"})
            service = await asyncio.to_thread(deps.activations)
            result = await asyncio.to_thread(service.revert, principal, activation_id,
                                             expected_generation=data["expected_generation"], event_key=data["event_key"])
            return {"ok": True, "activation": result}
        except _ERRORS as error:
            return _fail(error)

    async def canaries():
        if deps.canaries is None:
            raise PermissionError("canary_unavailable")
        return await asyncio.to_thread(deps.canaries)

    async def write(request, brain, required, optional, call):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            data = await _body(request, required, optional)
            return await asyncio.to_thread(call, await canaries(), principal, data)
        except _ERRORS as error:
            return _fail(error)

    @app.get("/improvement-canaries/{activation_id}")
    async def canary_summary(activation_id: str, brain: str = "brain"):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                raise PermissionError("canary_unavailable")
            service = await canaries()
            return {"ok": True, "canary": await asyncio.to_thread(service.summary, principal, activation_id)}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-canaries/{activation_id}/verdicts")
    async def canary_verdict(activation_id: str, request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "verdict": service.verdict(principal, activation_id, data["session_id"], data["message_id"],
                    data["verdict"], reason=data.get("reason", ""), event_key=data["event_key"])}
        return await write(request, brain, {"session_id", "message_id", "verdict", "event_key"}, {"reason"}, call)

    @app.post("/improvement-canaries/{activation_id}/promote")
    async def canary_promote(activation_id: str, request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "canary": service.promote(principal, activation_id,
                    expected_generation=data["expected_generation"], event_key=data["event_key"])}
        return await write(request, brain, {"expected_generation", "event_key"}, set(), call)

    @app.get("/improvement-auto-scopes")
    async def auto_scopes(brain: str = "brain", target_id: str | None = None):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                return {"ok": True, "grants": []}
            service = await canaries()
            return {"ok": True, "grants": await asyncio.to_thread(service.grants, principal, target_id=target_id)}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-auto-scopes")
    async def auto_scope_grant(request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "grant": service.grant(principal, data["target_id"], data["agent_slug"],
                    data["allocation_pct"], event_key=data["event_key"])}
        return await write(request, brain, {"target_id", "agent_slug", "allocation_pct", "event_key"}, set(), call)

    @app.post("/improvement-auto-scopes/{grant_id}/revoke")
    async def auto_scope_revoke(grant_id: str, request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "grant": service.revoke_grant(principal, grant_id,
                    expected_generation=data["expected_generation"], event_key=data["event_key"])}
        return await write(request, brain, {"expected_generation", "event_key"}, set(), call)

    return deps
