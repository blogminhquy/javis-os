"""Owner routes for M2E manual activation: list, apply to one assistant chat, revert."""
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
            data = await _body(request, {"candidate_id", "agent_slug", "event_key"})
            service = await asyncio.to_thread(deps.activations)
            result = await asyncio.to_thread(service.apply, principal, data["candidate_id"], data["agent_slug"],
                                             event_key=data["event_key"])
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

    return deps
