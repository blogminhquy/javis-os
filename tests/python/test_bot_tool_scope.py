"""Per-bot tool allowlists: the host decides the scope, the model can only narrow it.

Every identity here is invented; no external call is made.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ['JAVIS_STATE_DIR'] = tempfile.mkdtemp(prefix='scope-test-')
os.environ['BRAINS_DIR'] = tempfile.mkdtemp(prefix='scope-brains-')
import bot_tool_scope as scope  # noqa: E402
import turn_context as turns  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402

BOT = 'bot_example'
ACCOUNT = 'acct_example'
TOOL = 'example_lookup'


def turn(**changes):
    values = dict(kenh='zalo_personal', sender_id='user-a', chat_type='private', chat_id='user-a',
                  account_id=ACCOUNT, bot_id=BOT, tool_allowlist=[TOOL])
    values.update(changes)
    return turns.make(**values)


class ScopeTests(unittest.TestCase):
    def tearDown(self):
        self.assertIsNone(turns.current())

    def test_validation_empty_absent_invalid(self):
        self.assertEqual(scope.validate([]), [])
        self.assertEqual(scope.validate(['b', 'a', 'a']), ['a', 'b'])
        for value in (None, '*', ['*'], ['javis_run_tool'], ['javis_query'], [1], ['x'] * 257):
            with self.subTest(value=str(value)[:30]), self.assertRaises(ValueError):
                scope.validate(value)

    def test_store_persists_scope_and_rejects_invalid_atomically(self):
        import chatbot_store as store
        base = {'name': 'Scoped', 'agent_slug': 'test', 'brain': 'test'}
        legacy, error = store.create_bot(base)
        self.assertFalse(error)
        self.assertNotIn('tool_allowlist', store.get_bot(legacy))
        scoped, error = store.create_bot(dict(base, tool_allowlist=[]))
        self.assertFalse(error)
        self.assertEqual(store.get_bot(scoped)['tool_allowlist'], [])
        ok, error = store.update_bot(scoped, {'tool_allowlist': [TOOL]})
        self.assertTrue(ok, error)
        self.assertEqual(store.get_bot(scoped)['tool_allowlist'], [TOOL])
        for invalid in (None, ['*'], 'all'):
            self.assertIsNone(store.create_bot(dict(base, tool_allowlist=invalid))[0])
            self.assertFalse(store.update_bot(scoped, {'name': 'changed', 'tool_allowlist': invalid})[0])
            self.assertEqual(store.get_bot(scoped)['name'], 'Scoped')
        self.assertNotIn('tool_allowlist', store.get_bot(legacy))

    def test_scope_needs_the_real_account_of_the_bot(self):
        bot = {'id': BOT, 'accounts': [ACCOUNT], 'tool_allowlist': [TOOL]}
        with patch('chatbot_store.account_ids_of', return_value=[ACCOUNT]), \
             patch('channel_accounts.get_account', return_value={'channel': 'zalo_personal'}):
            resolved = scope.from_bot(bot, ACCOUNT, 'zalo_personal')
            self.assertEqual(resolved, {'account_id': ACCOUNT, 'bot_id': BOT, 'tool_allowlist': [TOOL]})
            self.assertEqual(scope.from_bot(bot, 'acct_other', 'zalo_personal')['tool_allowlist'], [])
            self.assertEqual(scope.from_bot(bot, ACCOUNT, 'telegram')['tool_allowlist'], [])

    def test_unscoped_bot_unchanged_and_broken_config_closed(self):
        with patch('channel_accounts.get_account', return_value=None):
            self.assertIsNone(scope.from_bot({'id': 'legacy'}, '', '')['tool_allowlist'])
            self.assertEqual(scope.from_bot({'id': 'broken', 'tool_allowlist': None}, '', '')['tool_allowlist'], [])

    def test_metadata_cannot_set_identity_or_scope(self):
        t = turns.from_meta('zalo_personal', {'user_id': 'user-a', 'account_id': 'forged',
            'bot_id': 'forged', 'tool_allowlist': ['*'], 'la_chu': True}, False)
        self.assertFalse(t['la_chu'])
        self.assertEqual((t['account_id'], t['bot_id']), ('', ''))
        self.assertIsNone(t['tool_allowlist'])

    def test_copy_cannot_widen_and_requested_can_only_narrow(self):
        token = turns.bind(turn())
        try:
            key = turns.issue_key()
            turns.current()['tool_allowlist'].append('shell')
            self.assertEqual(turns.resolve_key(key)['tool_allowlist'], [TOOL])
            self.assertEqual(scope.effective(['shell', TOOL]), [TOOL])
            self.assertEqual(scope.effective(['exa*']), [TOOL])
            self.assertEqual(scope.effective(['shell']), [])
            self.assertTrue(scope.native_engine_blocked())
        finally:
            turns.reset(token)
        self.assertIsNone(turns.resolve_key(key))
        self.assertFalse(scope.native_engine_blocked())
        self.assertTrue(scope.permitted('anything'))


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_is_scoped(self):
        import mcp_store

        async def discovered(*args, **kwargs):
            return [], {}

        def builtins(*args, **kwargs):
            return ([{'fn': TOOL, 'description': 'safe'}, {'fn': 'shell', 'description': 'shell'}],
                    {TOOL: {'call': lambda args: None}, 'shell': {'call': lambda args: None}})
        mcp_hub.invalidate_cache()
        with patch.object(mcp_store, 'resolved', return_value=[]), \
             patch.object(mcp_client, 'discover_resolved', discovered), \
             patch.object(mcp_hub, '_builtin_tools', builtins), \
             patch.object(mcp_hub.scout, 'available', return_value=False):
            broad, broad_routes = await mcp_hub.discover_all('suggest', include_plugins=False, force_lazy=True)
            self.assertIn('javis_run_tool', [x['fn'] for x in broad])
            token = turns.bind(turns.make('zalo_personal', bot_id='legacy'))
            try:
                legacy, legacy_routes = await mcp_hub.discover_all('suggest', include_plugins=False, force_lazy=True)
                self.assertEqual([x['fn'] for x in legacy], [x['fn'] for x in broad])
            finally:
                turns.reset(token)
            token = turns.bind(turn())
            try:
                for requested in (None, [TOOL, 'shell']):
                    tools, routes = await mcp_hub.discover_all('suggest', include_plugins=False,
                                                               force_lazy=True, tool_allowlist=requested)
                    self.assertEqual([x['fn'] for x in tools], [TOOL])
                    self.assertEqual(set(routes), {TOOL})
            finally:
                turns.reset(token)
            token = turns.bind(turn(tool_allowlist=[]))
            try:
                tools, routes = await mcp_hub.discover_all('suggest', include_plugins=False, force_lazy=True)
                self.assertEqual((tools, routes), ([], {}))
            finally:
                turns.reset(token)
        mcp_hub.invalidate_cache()

    async def test_native_engines_deny_before_startup(self):
        from claude_cli import CodexCLI
        from claude_sdk_engine import ClaudeSDK
        from grok_cli import GrokCLI
        from antigravity_cli import AntigravityCLI
        token = turns.bind(turn())
        try:
            for engine_type in (CodexCLI, ClaudeSDK, GrokCLI, AntigravityCLI):
                instance = engine_type.__new__(engine_type)
                events = [event async for event in instance.query('prompt')]
                self.assertEqual([e['type'] for e in events], ['error'])
        finally:
            turns.reset(token)

    async def test_plugin_handler_outside_scope_never_runs(self):
        import plugins_host

        async def forbidden(*args):
            self.fail('plugin handler executed outside scope')
        call = plugins_host._make_call({'handler': forbidden, 'name': 'other_plugin'}, None, 'full')
        token = turns.bind(turn())
        try:
            self.assertEqual(await call({}), 'ERROR: bot_tool_scope_denied')
        finally:
            turns.reset(token)

    async def test_cached_route_denied_at_call_time(self):
        async def forbidden(args):
            self.fail('outside tool executed')
        token = turns.bind(turn())
        try:
            for name in ('shell', 'javis_query', 'javis_run_tool', 'zalo_send_image'):
                result = await mcp_client.call_route({name: {'call': forbidden}}, name, {})
                self.assertIn('scope_denied', result)
        finally:
            turns.reset(token)

    async def test_raw_jsonrpc_cannot_bypass_discovery(self):
        token = turns.bind(turn())
        try:
            result = await mcp_hub._handle_one({'id': 1, 'method': 'tools/call',
                'params': {'name': 'shell', 'arguments': {}}}, 'full', tool_allowlist=['shell'])
            self.assertTrue(result['result']['isError'])
        finally:
            turns.reset(token)

    async def test_concurrent_turns_do_not_share_scope(self):
        async def run(name):
            token = turns.bind(turn(tool_allowlist=[name]))
            try:
                await asyncio.sleep(0.01)
                return scope.current()
            finally:
                turns.reset(token)
        self.assertEqual(await asyncio.gather(run('a'), run('b')), [['a'], ['b']])


if __name__ == '__main__':
    unittest.main(verbosity=2)
