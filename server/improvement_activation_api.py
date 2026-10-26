"""Owner routes for activation (M2E), canaries (M3), routing descriptions (M4), agent procedures (M5), bundles (M6),
Team trials and recipe transfers (M7), governance, export and import (M8)."""
from __future__ import annotations

import asyncio
import re
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
# An agent procedure is prompt text, so every engine gets it on the surfaces the owner chose. Goals and
# customer chatbots never load the assistant prompt.
_AGENT_COVERAGE = {"served": ["dm", "team", "kanban", "workflow"], "not_served": ["goals", "chatbots"]}


@dataclass
class ActivationApiDeps:
    activations: Callable  # () -> improvement_activation.Activations (write store)
    resolve_brain: Callable[[str], str]
    read_store: Callable = lambda: True  # () -> installed read store or None; None means nothing to list
    owner_session: Callable = lambda request: None  # request -> denial Response or None (browser session only)
    canaries: Callable = None  # () -> improvement_canary.Canaries over the same write store
    routing: Callable = None  # () -> improvement_routing.Routing over the same write store (M4)
    agents: Callable = None  # () -> improvement_agent.AgentProcedures over the same write store (M5)
    review_proposals: Callable = lambda agent_key: []  # open agent_review ideas of one assistant (drafts)
    bundles: Callable = None  # () -> improvement_bundle.Bundles over the same write store (M6)
    team_trials: Callable = None  # () -> improvement_team.TeamTrials (M7)
    recipe_transfers: Callable = None  # () -> improvement_team.RecipeTransfers (M7)
    governance: Callable = None  # () -> improvement_library.Governance (M8)
    imports: Callable = None  # () -> improvement_library.Imports (M8)
    export: Callable = None  # (principal, procedure_ids) -> package (M8)
    loop_runs: Callable = None  # () -> improvement_loop_runs.LoopRuns (self-learning runs)
    auto_learning: Callable = None  # () -> auto_learning.AutoLearner (automatic learning from chat)


def _fail(error):
    # A unique pointer race is a version conflict; other SQLite failures are unavailability.
    if isinstance(error, sqlite3.IntegrityError):
        return _error(ConflictError("activation_scope_busy"))
    return _error(OSError("storage_unavailable") if isinstance(error, sqlite3.Error) else error)


def register(app, deps: ActivationApiDeps):
    async def owner(brain: str):
        root = await asyncio.to_thread(deps.resolve_brain, brain)
        return Principal("owner", "owner", root)

    async def not_bundled(principal, kind, pointer_id):
        # M6: a bundle member leaves service only with its bundle, so the state is never half new.
        if deps.bundles is not None and await asyncio.to_thread(deps.read_store) is not None:
            service = await asyncio.to_thread(deps.bundles)
            if await asyncio.to_thread(service.member_of, principal, kind, pointer_id):
                raise ConflictError("bundle_member_revert_with_bundle")

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
            await not_bundled(principal, "skill", activation_id)
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

    @app.get("/improvement-pilot-reports/{report_id}")
    async def pilot_report(report_id: str, brain: str = "brain"):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                raise PermissionError("report_unavailable")
            service = await canaries()
            return {"ok": True, "pilot": await asyncio.to_thread(service.pilot_report, principal, report_id)}
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

    async def routing():
        if deps.routing is None:
            raise PermissionError("routing_unavailable")
        return await asyncio.to_thread(deps.routing)

    @app.get("/improvement-routing")
    async def routing_list(target_id: str, brain: str = "brain"):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                return {"ok": True, "candidates": [], "overlays": []}
            service = await routing()
            await asyncio.to_thread(service.reconcile, principal)
            return {"ok": True, "candidates": await asyncio.to_thread(service.candidates, principal, target_id=target_id),
                    "overlays": await asyncio.to_thread(service.overlays, principal, target_id=target_id),
                    "coverage": {"served": ["main_chat_api_engines"], "not_served": ["assistant_chats", "claude_code", "codex"]}}
        except _ERRORS as error:
            return _fail(error)

    async def routing_write(request, brain, required, call):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            data = await _body(request, required)
            return await asyncio.to_thread(call, await routing(), principal, data)
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-routing/evaluate")
    async def routing_evaluate(request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "routing": service.evaluate(principal, data["target_id"], data["description"], data["cases"],
                                                             event_key=data["event_key"])}
        return await routing_write(request, brain, {"target_id", "description", "cases", "event_key"}, call)

    @app.post("/improvement-routing/{candidate_id}/apply")
    async def routing_apply(candidate_id: str, request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "overlay": service.apply(principal, candidate_id, event_key=data["event_key"])}
        return await routing_write(request, brain, {"event_key"}, call)

    @app.post("/improvement-routing-overlays/{overlay_id}/revert")
    async def routing_revert(overlay_id: str, request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "overlay": service.revert(principal, overlay_id,
                    expected_generation=data["expected_generation"], event_key=data["event_key"])}
        return await routing_write(request, brain, {"expected_generation", "event_key"}, call)

    async def agents():
        if deps.agents is None:
            raise PermissionError("agent_procedures_unavailable")
        return await asyncio.to_thread(deps.agents)

    @app.get("/improvement-agent-procedures")
    async def agent_procedure_list(agent: str, brain: str = "brain"):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                return {"ok": True, "procedures": [], "overlays": [], "review_proposals": [], "coverage": _AGENT_COVERAGE}
            service = await agents()
            await asyncio.to_thread(service.reconcile, principal)
            procedures = await asyncio.to_thread(service.procedures, principal, agent)
            keys = {row["agent_key"] for row in procedures}
            overlays = [row for row in await asyncio.to_thread(service.overlays, principal) if row["agent_key"] in keys]
            key = await asyncio.to_thread(service.key, principal, agent)
            proposals = await asyncio.to_thread(deps.review_proposals, key) if key else []
            return {"ok": True, "procedures": procedures, "overlays": overlays, "review_proposals": proposals,
                    "coverage": _AGENT_COVERAGE}
        except _ERRORS as error:
            return _fail(error)

    async def agent_write(request, brain, required, call):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            data = await _body(request, required)
            return await asyncio.to_thread(call, await agents(), principal, data)
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-agent-procedures")
    async def agent_procedure_stage(request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "procedure": service.stage(principal, data["agent"], data["text"], event_key=data["event_key"])}
        return await agent_write(request, brain, {"agent", "text", "event_key"}, call)

    @app.post("/improvement-agent-procedures/{procedure_id}/apply")
    async def agent_procedure_apply(procedure_id: str, request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "overlay": service.apply(principal, procedure_id, data["surfaces"],
                    owner_confirmed=data["owner_confirmed"], event_key=data["event_key"])}
        return await agent_write(request, brain, {"surfaces", "owner_confirmed", "event_key"}, call)

    @app.post("/improvement-agent-overlays/{overlay_id}/revert")
    async def agent_overlay_revert(overlay_id: str, request: Request, brain: str = "brain"):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            await not_bundled(await owner(brain), "procedure", overlay_id)
        except _ERRORS as error:
            return _fail(error)

        def call(service, principal, data):
            return {"ok": True, "overlay": service.revert(principal, overlay_id,
                    expected_generation=data["expected_generation"], event_key=data["event_key"])}
        return await agent_write(request, brain, {"expected_generation", "event_key"}, call)

    async def bundles():
        if deps.bundles is None:
            raise PermissionError("bundles_unavailable")
        return await asyncio.to_thread(deps.bundles)

    @app.get("/improvement-agent-bundles")
    async def bundle_list(agent: str, brain: str = "brain"):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                return {"ok": True, "bundles": []}
            service = await bundles()
            await asyncio.to_thread(service.reconcile, principal)
            key = await asyncio.to_thread((await agents()).key, principal, agent)
            rows = await asyncio.to_thread(service.list, principal, agent_key=key) if key else []
            return {"ok": True, "bundles": rows}
        except _ERRORS as error:
            return _fail(error)

    async def bundle_write(request, brain, required, call):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            data = await _body(request, required)
            return await asyncio.to_thread(call, await bundles(), principal, data)
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-agent-bundles")
    async def bundle_apply(request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "bundle": service.apply(principal, data["agent"], data["manifest"],
                    owner_confirmed=data["owner_confirmed"], event_key=data["event_key"])}
        return await bundle_write(request, brain, {"agent", "manifest", "owner_confirmed", "event_key"}, call)

    @app.post("/improvement-agent-bundles/{bundle_id}/revert")
    async def bundle_revert(bundle_id: str, request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "bundle": service.revert(principal, bundle_id,
                    expected_generation=data["expected_generation"], event_key=data["event_key"])}
        return await bundle_write(request, brain, {"expected_generation", "event_key"}, call)

    async def m7(factory, name):
        if factory is None:
            raise PermissionError(name + "_unavailable")
        return await asyncio.to_thread(factory)

    async def m7_write(request, brain, required, factory, name, call, optional=None):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            data = await _body(request, required, optional)
            return await asyncio.to_thread(call, await m7(factory, name), principal, data)
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-team-pins")
    async def team_pin(request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "pin": service.pin(principal, data["team_id"], task_id=data.get("task_id", ""),
                                                   event_key=data["event_key"])}
        return await m7_write(request, brain, {"team_id", "event_key"}, deps.team_trials, "team_trials", call,
                              optional={"task_id"})

    @app.get("/improvement-team-trials")
    async def team_trial_list(team_id: str, brain: str = "brain"):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                return {"ok": True, "trials": []}
            service = await m7(deps.team_trials, "team_trials")
            return {"ok": True, "trials": await asyncio.to_thread(service.trials, principal, team_id)}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-team-trials")
    async def team_trial_record(request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "trial": service.record(principal, data["baseline_pin_id"], data["candidate_pin_id"],
                    data["change"], data["arms"], event_key=data["event_key"])}
        return await m7_write(request, brain, {"baseline_pin_id", "candidate_pin_id", "change", "arms", "event_key"},
                              deps.team_trials, "team_trials", call)

    @app.get("/improvement-recipe-transfers")
    async def recipe_transfer_list(kind: str, ref: str, brain: str = "brain"):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                return {"ok": True, "transfers": []}
            service = await m7(deps.recipe_transfers, "recipe_transfers")
            return {"ok": True, "transfers": await asyncio.to_thread(service.for_target, principal, {"kind": kind, "ref": ref})}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-recipe-transfers")
    async def recipe_transfer_propose(request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "transfer": service.propose(principal, data["recipe_id"], data["target"],
                    event_key=data["event_key"])}
        return await m7_write(request, brain, {"recipe_id", "target", "event_key"}, deps.recipe_transfers,
                              "recipe_transfers", call)

    # M8: every live improvement of the brain, and the owner's one-step pause of all of them (spec 18.2).
    @app.get("/improvement-governance")
    async def governance_view(brain: str = "brain"):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                return {"ok": True, "live": []}
            service = await m7(deps.governance, "governance")
            await asyncio.to_thread(service.reconcile, principal)
            return {"ok": True, "live": await asyncio.to_thread(service.live, principal),
                    "grants": await asyncio.to_thread(service.grants, principal)}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-governance/suspend-all")
    async def governance_suspend_all(request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, **service.suspend_all(principal, event_key=data["event_key"])}
        return await m7_write(request, brain, {"event_key"}, deps.governance, "governance", call)

    @app.post("/improvement-export")
    async def improvement_export(request: Request, brain: str = "brain"):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            data = await _body(request, {"procedure_ids", "event_key"})
            if deps.export is None:
                raise PermissionError("export_unavailable")
            return {"ok": True, "package": await asyncio.to_thread(deps.export, principal, data["procedure_ids"])}
        except _ERRORS as error:
            return _fail(error)

    # Self-learning runs: the owner starts one for a user skill with examples; nothing changes until Apply.
    @app.get("/improvement-loops")
    async def loop_status(slug: str, brain: str = "brain"):
        try:
            principal = await owner(brain)
            service = await m7(deps.loop_runs, "loop_runs")
            return {"ok": True, **await asyncio.to_thread(service.status, principal.brain_id, slug)}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-loops")
    async def loop_start(request: Request, brain: str = "brain"):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            data = await _body(request, {"slug", "event_key"})
            service = await m7(deps.loop_runs, "loop_runs")
            return {"ok": True, "run": await asyncio.to_thread(service.start, principal.brain_id, data["slug"],
                                                               event_key=data["event_key"])}
        except _ERRORS as error:
            return _fail(error)

    @app.get("/improvement-loops/{run_id}")
    async def loop_get(run_id: str, brain: str = "brain"):
        try:
            principal = await owner(brain)
            service = await m7(deps.loop_runs, "loop_runs")
            return {"ok": True, "run": await asyncio.to_thread(service.get, principal.brain_id, run_id)}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-loops/{run_id}/cancel")
    async def loop_cancel(run_id: str, request: Request, brain: str = "brain"):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            await _body(request, {"event_key"})
            service = await m7(deps.loop_runs, "loop_runs")
            return {"ok": True, "run": await asyncio.to_thread(service.cancel, principal.brain_id, run_id)}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-loops/{run_id}/apply")
    async def loop_apply(run_id: str, request: Request, brain: str = "brain"):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            await _body(request, {"event_key"})
            service = await m7(deps.loop_runs, "loop_runs")
            return {"ok": True, "applied": await asyncio.to_thread(service.apply, principal.brain_id, run_id)}
        except _ERRORS as error:
            return _fail(error)

    # Automatic learning from chat: what Javis changed on its own, and undo.
    @app.get("/auto-learning")
    async def auto_learning_view(brain: str = "brain"):
        try:
            principal = await owner(brain)
            service = await m7(deps.auto_learning, "auto_learning")
            history = await asyncio.to_thread(service.history, principal.brain_id)
            stats = await asyncio.to_thread(service.stats, principal.brain_id)
            return {"ok": True, "history": history, "stats": stats}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/auto-learning/{run_id}/apply")
    async def auto_learning_apply(run_id: str, request: Request, brain: str = "brain"):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            await _body(request, {"event_key"})
            if not re.fullmatch(r"alr_[0-9a-f]{16}", run_id):
                raise ValueError("invalid_run")
            service = await m7(deps.auto_learning, "auto_learning")
            return {"ok": True, **await asyncio.to_thread(service.apply_proposal, principal.brain_id, run_id)}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/auto-learning/{run_id}/undo")
    async def auto_learning_undo(run_id: str, request: Request, brain: str = "brain"):
        try:
            if (denied := deps.owner_session(request)) is not None:
                return denied
            principal = await owner(brain)
            await _body(request, {"event_key"})
            if not re.fullmatch(r"alr_[0-9a-f]{16}", run_id):
                raise ValueError("invalid_run")
            service = await m7(deps.auto_learning, "auto_learning")
            return {"ok": True, **await asyncio.to_thread(service.undo, principal.brain_id, run_id)}
        except _ERRORS as error:
            return _fail(error)

    @app.get("/improvement-imports")
    async def import_list(brain: str = "brain"):
        try:
            principal = await owner(brain)
            if await asyncio.to_thread(deps.read_store) is None:
                return {"ok": True, "imports": []}
            service = await m7(deps.imports, "imports")
            return {"ok": True, "imports": await asyncio.to_thread(service.list, principal)}
        except _ERRORS as error:
            return _fail(error)

    @app.post("/improvement-imports")
    async def import_stage(request: Request, brain: str = "brain"):
        def call(service, principal, data):
            return {"ok": True, "items": service.stage(principal, data["package"], event_key=data["event_key"])}
        return await m7_write(request, brain, {"package", "event_key"}, deps.imports, "imports", call)

    return deps
