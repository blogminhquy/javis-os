"""Actual ordinary task owner lifecycle, local SQL/files only; no inference.

The main lifecycle test executes the real run_turn function extracted from its
AST with an inert _do_turn seam. It proves owner wiring/finally, not main engine
selection, provider dispatch, native/HTTP propagation or account readiness.
"""
from _paths import ROOT, SERVER  # noqa: F401

import ast
import asyncio
import contextvars
import copy
import importlib
import importlib.util
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import context_runtime as CR
from lazy_skill_runtime import LazySkillSource
import mcp_hub
import skill_router
import test_improvement_task_skill_scope as fixture
import turn_context as TC


class TaskSkillTurnTests(unittest.IsolatedAsyncioTestCase):
    new_turn = fixture.TaskSkillScopeTests.new_turn
    reset_turns = fixture.TaskSkillScopeTests.reset_turns
    close_scopes = fixture.TaskSkillScopeTests.close_scopes
    events = fixture.TaskSkillScopeTests.events

    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_task_skill_turn'),
            'actual host task-skill turn lifecycle missing')
        self.turn_module = importlib.import_module('improvement_task_skill_turn')
        fixture.TaskSkillScopeTests.setUp(self)
        self.lifecycle = self.turn_module.TaskSkillTurn()
        self.addCleanup(self.lifecycle.close)

    async def start(self, settings=None, **changes):
        kwargs = {'provider_kind': 'api', 'tool_provider': True, 'hub_enabled': True,
            'api_key': 'inert-unit-key-never-sent', 'root': self.brain, 'turn_token': self.turn,
            'runtime': self.runtime, 'trace': self.trace, 'assets_factory': lambda: self.assets}
        kwargs.update(changes)
        if settings is None: settings = {'context_runtime': {'task_skill_snapshot': {'enabled': True}}}
        return await self.lifecycle.start(settings, **kwargs)

    async def test_disabled_absent_malformed_native_and_nonhub_routes_do_no_factory_import_or_capture(self):
        cases = [({}, {}), ({'context_runtime': {}}, {}), ({'context_runtime': False}, {}),
            ({'context_runtime': {'task_skill_snapshot': None}}, {}),
            ({'context_runtime': {'task_skill_snapshot': {'enabled': False}}}, {}),
            ({'context_runtime': {'task_skill_snapshot': {'enabled': 1}}}, {}),
            ({'context_runtime': {'task_skill_snapshot': {'enabled': 'true'}}}, {})]
        enabled = {'context_runtime': {'task_skill_snapshot': {'enabled': True}}}
        cases += [(enabled, change) for change in ({'provider_kind': 'cli'}, {'provider_kind': 'oauth'},
            {'tool_provider': False}, {'hub_enabled': False}, {'api_key': ''}, {'api_key': None})]
        original_import = __import__
        def no_core(name, *args, **kwargs):
            if name == 'improvement_task_skill_scope': raise AssertionError('disabled path imported scope')
            return original_import(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=no_core), \
                patch.object(self.m, '_inventory', side_effect=AssertionError('disabled path scanned owner files')):
            for settings, changes in cases:
                with self.subTest(settings=settings, changes=changes):
                    scope = await self.start(settings,
                        assets_factory=lambda: self.fail('disabled path constructed M0'), **changes)
                    self.assertIsNone(scope)
        self.assertIsNone(self.m.current(self.brain))
        self.assertEqual(self.events('ordinary_task_skill_scope'), [])

    async def test_actual_selected_api_binds_on_event_loop_and_lazy_hub_metadata_share_pin(self):
        _, routes = mcp_hub._builtin_tools('full', self.brain)
        handler = routes['javis_use_skill']['call']
        scope = await self.start()
        self.assertIs(self.m.current(self.brain), scope, 'thread-local bind would not propagate to event loop')
        with patch.object(self.registry, 'refresh_skills', side_effect=AssertionError('global task projection')):
            selected = await asyncio.to_thread(LazySkillSource(self.registry).resolve, self.brain, 'report')
        self.assertEqual(selected.action, 'load')
        self.path.write_bytes(self.header + b'New mutable ordinary body.')
        with patch('skill_usage.bump') as bump:
            body = await handler({'name': 'report'})
        self.assertEqual(body, self.original.decode().replace('\r\n', '\n'))
        self.assertTrue(selected.context_item.source_ref.endswith(scope.read('report').content_hash))
        self.assertEqual(skill_router.list_enabled_meta(self.brain, 'en')[0]['name'], 'English report')
        self.assertEqual(len(self.events('ordinary_task_skill_asset')), 1)
        bump.assert_called_once_with(self.brain, 'report')

    async def test_close_invalidates_copied_context_before_reset_and_is_idempotent(self):
        scope = await self.start(); copied = contextvars.copy_context()
        self.lifecycle.close(); self.lifecycle.close()
        self.assertIsNone(self.m.current(self.brain))
        with self.assertRaises(self.m.ScopeUnavailable): copied.run(self.m.current, self.brain)
        self.assertTrue(scope._closed)

    async def test_scope_open_failure_propagates_without_binding_or_mutable_fallback(self):
        with patch.object(self.m.TaskSkillScope, 'open', side_effect=self.m.ScopeUnavailable('controlled-open-failure')):
            with self.assertRaises(self.m.ScopeUnavailable): await self.start()
        self.assertIsNone(self.m.current(self.brain))
        self.assertEqual(self.events('ordinary_task_skill_scope'), [])

    async def test_factory_failure_keeps_context_unbound(self):
        def failed_factory(): raise ValueError('controlled-factory-failure')
        with self.assertRaises(ValueError): await self.start(assets_factory=failed_factory)
        self.assertIsNone(self.m.current(self.brain))
        self.lifecycle.close()

    async def test_cancelled_slow_capture_settles_real_thread_and_closes_owner_before_reraising(self):
        entered, release, completed = threading.Event(), threading.Event(), threading.Event()
        captured = []
        original = self.m.TaskSkillScope.open
        def slow(*args, **kwargs):
            scope = original(*args, **kwargs)
            captured.append(scope); entered.set()
            try:
                if not release.wait(5): raise AssertionError('test did not release actual capture thread')
                return scope
            finally: completed.set()
        with patch.object(self.m.TaskSkillScope, 'open', side_effect=slow):
            task = asyncio.create_task(self.start())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                task.cancel(); await asyncio.sleep(.03); task.cancel(); await asyncio.sleep(.03)
                self.assertFalse(task.done(), 'caller cancellation must not abandon capture worker')
                self.assertFalse(completed.is_set())
                release.set()
                with self.assertRaises(asyncio.CancelledError): await asyncio.wait_for(asyncio.shield(task), 3)
                self.assertTrue(completed.is_set())
                self.assertEqual(len(captured), 1)
                self.assertTrue(captured[0]._closed, 'cancelled start must retain and close returned owner')
                with self.assertRaises(self.m.ScopeUnavailable): captured[0].read('report')
                self.assertIsNone(self.m.current(self.brain))
            finally:
                release.set()
                await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 5)

    async def test_actual_main_run_turn_passes_owned_tokens_and_closes_on_success_error_or_stop(self):
        source = ast.parse((ROOT / 'server' / 'main.py').read_text(encoding='utf-8'))
        functions = [node for node in ast.walk(source) if isinstance(node, ast.AsyncFunctionDef) and node.name == 'run_turn']
        self.assertEqual(len(functions), 1)
        function = copy.deepcopy(functions[0]); function.decorator_list = []
        code = compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), '<actual-main-run-turn>', 'exec')
        for outcome in ('success', 'error', 'cancel'):
            with self.subTest(outcome=outcome):
                if outcome != 'success': self.trace, self.turn = self.new_turn()
                owners, frames, order = [], [], []
                async def do_turn(*args, **kwargs):
                    lifecycle, token = kwargs['_task_skills'], kwargs['_turn_token']
                    self.assertIs(token._binding, TC._CURRENT.get())
                    self.assertIs(CR.current_trace(), self.trace)
                    scope = await lifecycle.start({'context_runtime': {'task_skill_snapshot': {'enabled': True}}},
                        provider_kind='api', tool_provider=True, hub_enabled=True, api_key='inert-unit-key-never-sent',
                        root=self.brain, turn_token=token, runtime=self.runtime, trace=self.trace,
                        assets_factory=lambda: self.assets)
                    owners.append(scope)
                    self.assertIs(self.m.current(self.brain), scope)
                    if outcome == 'error': raise ValueError('controlled-turn-error')
                    if outcome == 'cancel': raise asyncio.CancelledError()
                    return 'inert answer'
                async def send(frame): frames.append(frame)
                def close_turn(token):
                    self.assertTrue(owners and owners[0]._closed, 'scope must close before actual host turn reset')
                    order.append('turn_reset'); original_reset(token)
                original_reset = TC.reset
                nothing = lambda *args, **kwargs: None
                env = {'context_runtime': CR, 'turn_context': TC, 'asyncio': asyncio, 'time': time,
                    'TaskSkillTurn': self.turn_module.TaskSkillTurn, 'improvement_task_skill_turn': self.turn_module,
                    '_resonance_turn_agent': lambda *args: None, 'store': SimpleNamespace(get_session=lambda *_: {}),
                    'cfgmod': SimpleNamespace(read_settings=lambda: {'recall': {'enabled': False}}),
                    'WEB_CHAT_PREFIX': 'web:', '_brain_root': lambda *_: str(self.brain),
                    'luot_dang_chay': SimpleNamespace(bat_dau=lambda *a, **kw: 'fixture-job', ket_thuc=nothing),
                    'steer_inbox': SimpleNamespace(INBOX=SimpleNamespace(open=lambda *a: 'fixture-steer', close=lambda *a: [])),
                    '_engine_outcome_reset': nothing, '_do_turn': do_turn, '_resonance_after_turn': nothing,
                    '_record_quality_shadow': nothing, '_CONTEXT_RUNTIME': self.runtime, 'send_raw': send,
                    '_engine_outcome_exception': nothing, '_engine_outcome_turn': nothing,
                    'localefmt': SimpleNamespace(chu=lambda first, *_: first),
                    'tien_trinh_nen': SimpleNamespace(bo_tag=nothing), '_engine_outcome_pop': lambda *_: {},
                    '_CHAT_RUNTIME': SimpleNamespace(finish_job=nothing)}
                exec(code, env)
                with patch.object(TC, 'reset', side_effect=close_turn):
                    await env['run_turn']('session-owner', 'fixture request', str(self.brain), 'fixture-tag',
                        self.trace, user_mid=100, user_text='fixture request')
                self.assertEqual(order, ['turn_reset'])
                self.assertTrue(owners[0]._closed)
                self.assertIsNone(self.m.current(self.brain))
                self.assertEqual(frames[-1]['type'], 'turn_done')

    async def test_cancelled_failing_capture_settles_but_keeps_caller_cancellation(self):
        entered, release, settled = threading.Event(), threading.Event(), threading.Event()
        def failing_factory():
            entered.set()
            try:
                if not release.wait(5): raise AssertionError('capture worker not released')
                raise ValueError('controlled-capture-failure-after-stop')
            finally: settled.set()
        task = asyncio.create_task(self.start(assets_factory=failing_factory))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 3))
            task.cancel(); await asyncio.sleep(.02); task.cancel(); await asyncio.sleep(.02)
            self.assertFalse(task.done()); self.assertFalse(settled.is_set())
            release.set()
            with self.assertRaises(asyncio.CancelledError): await asyncio.wait_for(asyncio.shield(task), 3)
            self.assertTrue(settled.is_set())
            self.assertFalse(self.lifecycle._starting)
            self.assertIsNone(self.m.current(self.brain))
        finally:
            release.set()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 5)


if __name__ == '__main__': unittest.main()
