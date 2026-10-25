"""Opt-in ordinary Dashboard API owner; no native/HTTP/activation authority."""
from __future__ import annotations

import asyncio
import contextvars


class TaskSkillTurn:
    def __init__(self):
        self._scope = None
        self._token = None
        self._closed = False
        self._starting = False

    async def start(self, settings, *, provider_kind, tool_provider, hub_enabled,
                    api_key, root, turn_token, runtime, trace, assets_factory):
        runtime_settings = settings.get('context_runtime') if type(settings) is dict else None
        policy = runtime_settings.get('task_skill_snapshot') if type(runtime_settings) is dict else None
        if (type(policy) is not dict or policy.get('enabled') is not True
                or provider_kind != 'api' or tool_provider is not True
                or hub_enabled is not True or not api_key):
            return None
        if self._closed or self._starting or self._scope is not None:
            raise RuntimeError('task_skill_lifecycle_already_used')
        # Default/off/native paths above do not import the core, open M0 or scan.
        from improvement_task_skill_scope import TaskSkillScope, bind
        from resonance_store import Principal
        self._starting = True

        def capture():
            try:
                return TaskSkillScope.open(assets_factory(), Principal('owner', 'owner', str(root)),
                    turn_token=turn_token, runtime=runtime, trace=trace), None
            except BaseException as error:
                return None, error

        # A private executor future has no separately cancellable asyncio Task.
        # Its outcome is data, so a late capture exception cannot replace Stop.
        context = contextvars.copy_context()
        pending = asyncio.get_running_loop().run_in_executor(None, context.run, capture)
        cancelled = None
        try:
            # Retain ownership through repeated cancellation until the actual
            # capture thread settles. It may have created a scope before Stop.
            while True:
                try:
                    scope, error = await asyncio.shield(pending)
                    break
                except asyncio.CancelledError as error:
                    cancelled = error
            if cancelled is not None or self._closed:
                if scope is not None:
                    scope.close()
                if cancelled is not None:
                    raise cancelled
                raise RuntimeError('task_skill_lifecycle_closed')
            if error is not None:
                raise error
            try:
                token = bind(scope)  # bind on the event loop, not in capture's thread
            except BaseException:
                scope.close()
                raise
            self._scope, self._token = scope, token
            return scope
        finally:
            self._starting = False

    def close(self):
        self._closed = True
        if self._scope is not None:
            self._scope.close()  # copied contexts retain a dead owner, never fallback
        if self._token is not None:
            from improvement_task_skill_scope import reset
            token, self._token = self._token, None
            reset(token)
