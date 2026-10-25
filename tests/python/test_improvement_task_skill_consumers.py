"""Actual lazy/hub consumers share an owned baseline, never a mutable fallback."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import ast
import copy
import hashlib
import unittest
from contextlib import contextmanager
from unittest.mock import patch, AsyncMock

import test_improvement_task_skill_scope as fixture
from lazy_skill_runtime import LazySkillSource
import mcp_hub
import skill_router


class TaskSkillConsumerTests(unittest.TestCase):
    setUp = fixture.TaskSkillScopeTests.setUp
    new_turn = fixture.TaskSkillScopeTests.new_turn
    reset_turns = fixture.TaskSkillScopeTests.reset_turns
    close_scopes = fixture.TaskSkillScopeTests.close_scopes
    open = fixture.TaskSkillScopeTests.open
    events = fixture.TaskSkillScopeTests.events

    def bound(self):
        scope = self.open()
        token = self.m.bind(scope)
        self.addCleanup(self.m.reset, token)
        return scope

    def handler(self):
        _, routes = mcp_hub._builtin_tools('full', self.brain)
        return routes['javis_use_skill']['call']

    @contextmanager
    def bound_here(self):
        scope = self.open(); token = self.m.bind(scope)
        try: yield scope
        finally: self.m.reset(token)

    def test_lazy_and_warmed_hub_share_raw_hash_without_global_registry_write(self):
        handler = self.handler()
        before = self.registry.revision(self.brain)
        scope = self.bound()
        source = LazySkillSource(self.registry)
        with patch.object(self.registry, 'refresh_skills', side_effect=AssertionError('private source')):
            selected = source.resolve(self.brain, 'report')
            self.assertEqual(selected.action, 'load')
            self.path.write_bytes(self.header + b'New mutable body.')
            with patch('skill_usage.bump') as bump:
                actual = asyncio.run(handler({'name': 'report'}))
            bump.assert_called_once_with(self.brain, 'report')
        self.assertEqual(actual, self.original.decode().replace('\r\n', '\n'))
        digest = hashlib.sha256(self.original).hexdigest()
        self.assertTrue(selected.context_item.source_ref.endswith(digest))
        self.assertEqual(selected.context_item.metadata['task_scope_hash'], scope.scope_hash)
        self.assertEqual(len(self.events('ordinary_task_skill_asset')), 1)
        self.assertEqual(self.registry.revision(self.brain), before)

    def test_router_metadata_is_frozen_and_header_only_in_bound_task(self):
        self.bound()
        self.path.write_bytes(self.original.replace(b'English report', b'Changed English title'))
        with patch.object(skill_router, 'list_skills', side_effect=AssertionError('mutable full reader')):
            rows = skill_router.list_enabled_meta(self.brain, 'en')
        self.assertEqual(rows[0]['name'], 'English report')
        self.assertTrue(rows[0]['enabled'])
        self.assertNotIn('Private original body', str(rows))
        self.assertEqual(self.events('ordinary_task_skill_asset'), [])

    def test_closed_bound_lazy_scope_never_falls_back_and_hub_never_counts(self):
        handler = self.handler(); scope = self.bound(); scope.close()
        with patch.object(skill_router, 'read_skill_asset', side_effect=AssertionError('mutable read')):
            selected = LazySkillSource(self.registry).resolve(self.brain, 'report')
            with patch('skill_usage.bump') as bump:
                actual = asyncio.run(handler({'name': 'report'}))
        self.assertEqual((selected.action, selected.reason), ('none', 'task_scope_unavailable'))
        self.assertEqual(actual, 'ERROR: task_skill_scope_unavailable'); bump.assert_not_called()

    def test_missing_encrypted_pin_cannot_restore_legacy_loader(self):
        handler = self.handler(); scope = self.bound(); asset = scope.read('report')
        self.assets.blobs._path(self.owner.brain_id, asset.content_hash).unlink()
        with patch('skill_usage.bump') as bump:
            selected = LazySkillSource(self.registry).resolve(self.brain, 'report')
            actual = asyncio.run(handler({'name': 'report'}))
        self.assertEqual((selected.action, selected.reason), ('none', 'task_scope_unavailable'))
        self.assertEqual(actual, 'ERROR: task_skill_scope_unavailable'); bump.assert_not_called()

    def test_bound_empty_body_is_explicit_none_not_legacy_fallback(self):
        self.path.write_bytes(self.header)
        self.bound()
        selected = LazySkillSource(self.registry).resolve(self.brain, 'report')
        self.assertEqual((selected.action, selected.reason), ('none', 'body_empty'))

    def test_ambiguous_bound_selection_keeps_frozen_router_metadata(self):
        self.bound()
        selected = LazySkillSource(self.registry).resolve(self.brain, 'use skill unknown', min_score=1)
        self.assertEqual(selected.action, 'fallback')
        self.path.write_bytes(self.original.replace(b'Bao cao du lieu', b'Changed description'))
        self.assertEqual(skill_router.list_enabled_meta(self.brain)[0]['description'], 'Bao cao du lieu')

    def test_unbound_warmed_hub_still_reads_new_ordinary_bytes(self):
        handler = self.handler()
        self.path.write_bytes(self.header + b'Latest ordinary body.')
        with patch('skill_usage.bump'):
            actual = asyncio.run(handler({'name': 'report'}))
        self.assertIn('Latest ordinary body.', actual)
        self.assertEqual(self.events('ordinary_task_skill_scope'), [])

    def test_hub_rechecks_scope_after_async_usage_before_returning_body(self):
        handler = self.handler(); scope = self.bound()
        def revoke(*args): scope.close()
        with patch('skill_usage.bump', side_effect=revoke):
            actual = asyncio.run(handler({'name': 'report'}))
        self.assertEqual(actual, 'ERROR: task_skill_scope_unavailable')

    def test_actual_discovery_uses_private_task_cache_and_inventory_not_global_warm_metadata(self):
        async def exercise():
            options = {'vault_root': self.brain, 'include_plugins': False}
            await mcp_hub.discover_all(**options)
            global_cache = dict(mcp_hub._cache)
            self.path.write_bytes(self.original.replace(b'Bao cao du lieu', b'Frozen task description'))
            with self.bound_here() as scope:
                tools, routes = await mcp_hub.discover_all(**options)
                description = next(tool['description'] for tool in tools if tool['fn'] == 'javis_use_skill')
                self.assertIn('Frozen task description', description)
                self.assertEqual(mcp_hub._cache, global_cache, 'private descriptor must never update global cache')
                second_tools, second_routes = await mcp_hub.discover_all(**options)
                self.assertIs(second_tools, tools); self.assertIs(second_routes, routes)
                inventory, _ = mcp_hub.registry_inventory(**options)
                self.assertIn('Frozen task description', next(t['description'] for t in inventory if t['fn'] == 'javis_use_skill'))
                scope.close()
                with self.assertRaises(self.m.ScopeUnavailable): await mcp_hub.discover_all(**options)
        with patch.object(mcp_hub, '_cache', {}), \
                patch('mcp_store.resolved', return_value=[]), \
                patch('mcp_client.discover_resolved', new=AsyncMock(return_value=([], {}))), \
                patch('plugins_host.has_tool_hooks', return_value=False), \
                patch.object(mcp_hub, '_apply_lazy', side_effect=lambda tools, route, *a, **kw: (tools, route)):
            asyncio.run(exercise())

    def test_discovery_revoked_during_async_connector_read_cannot_publish_or_return_task_tools(self):
        async def exercise():
            with self.bound_here() as scope:
                async def revoke(*args, **kwargs): scope.close(); return [], {}
                with patch('mcp_client.discover_resolved', new=revoke):
                    with self.assertRaises(self.m.ScopeUnavailable):
                        await mcp_hub.discover_all(vault_root=self.brain, include_plugins=False)
                self.assertEqual(mcp_hub._cache, {})
        with patch.object(mcp_hub, '_cache', {}), patch('mcp_store.resolved', return_value=[]), \
                patch('plugins_host.has_tool_hooks', return_value=False):
            asyncio.run(exercise())

    def test_actual_shadow_scheduler_suppresses_live_and_dead_task_projection_publication(self):
        tree = ast.parse((ROOT / 'server' / 'main.py').read_text(encoding='utf-8'))
        function = next(copy.deepcopy(node) for node in ast.walk(tree)
                        if isinstance(node, ast.FunctionDef) and node.name == '_schedule_registry_shadow')
        scheduled = []
        def track(coroutine): scheduled.append(True); coroutine.close()
        env = {'_track_shadow_task': track}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                     '<actual-shadow-scheduler>', 'exec'), env)
        def invoke(): env['_schedule_registry_shadow'](self.trace, str(self.brain), [], {}, 'query', 'openai', 'inert')
        invoke(); self.assertEqual(scheduled, [True])
        with self.bound_here() as scope:
            invoke(); scope.close(); invoke()
        self.assertEqual(scheduled, [True], 'neither live nor dead task data may enter global derived source')


if __name__ == '__main__': unittest.main()
