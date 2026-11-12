"""Restricted workflows select ChatGPT without inheriting full hub/native permissions."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ['JAVIS_STATE_DIR'] = tempfile.mkdtemp(prefix='javis-workflow-codex-')
import main
import mcp_hub
import workflow_codex
from starlette.requests import Request


def apply_hub(cli, root):
    cli.profile = 'test'
    cli.hub_turn = True
    cli.vault_root = root


with patch.object(main, '_brain_root', return_value=Path(os.environ['JAVIS_STATE_DIR'])), \
        patch.object(main, '_apply_codex_hub', side_effect=apply_hub), \
        patch.object(main, '_codex_user_mcp_servers', return_value=['node_repl']), \
        patch.object(main, '_codex_safe_model', side_effect=lambda model: model), \
        patch.object(main.openai_oauth, 'write_codex_auth'), \
        patch.object(main, 'claude_engine', side_effect=AssertionError('Claude fallback')), \
        patch.object(workflow_codex, 'codex_sandbox_cho_mode', return_value='read-only'), \
        patch.object(workflow_codex.CodexCLI, 'is_available', return_value=True):
    main.codex_models.efforts_for = lambda model: ['high']
    for mode in ['suggest', 'auto']:
        allowed = main.READONLY_TOOLS if mode == 'suggest' else main.SAFE_FILE_TOOLS
        factory, *_ = main._workflow_agent_helpers('brain', allowed, mode)
        cli = factory('test', 'gpt-6-astra', 'openai-oauth', extra_tools=['audio_review'], reasoning='high')
        assert 'model_reasoning_effort=high' in cli.extra_config
        assert cli.sandbox == 'read-only'
        assert f'{mcp_hub.CODEX_MODE_KEY}="{mode}"' in cli.extra_config
        assert 'features.shell_tool=false' in cli.extra_config
        assert 'features.apps=false' in cli.extra_config
        assert 'features.plugins=false' in cli.extra_config
        assert 'features.computer_use=false' in cli.extra_config
        assert 'features.multi_agent=false' in cli.extra_config
        assert 'mcp_servers.node_repl.enabled=false' in cli.extra_config
        assert 'mcp_servers.javis.required=true' in cli.extra_config
        config = next(x for x in cli.extra_config if x.startswith('mcp_servers.javis.http_headers.X-Javis-Tool-Allowlist='))
        names = json.loads(json.loads(config.split('=', 1)[1]))
        expected = {'javis_read_file', 'javis_list_dir', 'javis_search_files', 'audio_review'}
        if mode == 'auto':
            expected |= {'javis_write_file', 'javis_edit_file'}
        assert set(names) == expected
        assert cli.model == 'gpt-6-astra'
        print('PASS factory ChatGPT', mode, 'scoped hub and native restrictions')

# When the restricted Codex environment cannot be built (no Codex CLI, no hub profile...), the step runs on the gated
# Claude Code path, as every such step did before this change, instead of failing a workflow that works today.
class FakeClaude:
    def __init__(self, **kw):
        self.kw = kw
        self.extra_config = []


built = []
with patch.object(main, '_brain_root', return_value=Path(os.environ['JAVIS_STATE_DIR'])), \
        patch.object(main, '_apply_codex_hub', side_effect=apply_hub), \
        patch.object(main, '_codex_user_mcp_servers', return_value=[]), \
        patch.object(main.openai_oauth, 'write_codex_auth', side_effect=AssertionError('Codex auth written')), \
        patch.object(main, 'claude_engine', side_effect=lambda **kw: built.append(FakeClaude(**kw)) or built[-1]), \
        patch.object(workflow_codex.CodexCLI, 'is_available', return_value=False):
    factory, *_ = main._workflow_agent_helpers('brain', main.READONLY_TOOLS, 'suggest')
    engine = factory('test', 'gpt-6-astra', 'openai-oauth')
    assert built and engine is not None, 'the gated Claude Code engine was not built'
    assert list(built[-1].kw['allowed_tools']) == list(main.READONLY_TOOLS), built[-1].kw
    assert built[-1].kw['tag'] == 'workflow'
    assert {'Bash', 'WebFetch', 'WebSearch', 'Task'} <= set(built[-1].disallowed_tools)
    assert built[-1].model != 'gpt-6-astra', 'a ChatGPT model name must not reach Claude Code'
    print('PASS a restricted ChatGPT step without Codex runs on the gated Claude Code path')

SRC = (Path(SERVER) / 'main.py').read_text(encoding='utf-8')
assert 'return _step_engine(cc, "openai-oauth")   # the ChatGPT account with quota' in SRC, \
    'the restricted ChatGPT step lost its account rotation'

for allowed in [['Bash'], ['Task']]:
    try:
        workflow_codex.hub_allowlist(allowed)
    except ValueError:
        pass
    else:
        raise AssertionError('Unsupported native permission was widened')

with patch.object(workflow_codex, 'codex_sandbox_cho_mode', return_value='read-only'):
    try:
        workflow_codex.build(cwd='.',model=None,instructions='',allowed=[],mode='suggest',
                             apply_hub=apply_hub,extra_servers=['server.with.dots'])
    except ValueError:
        pass
    else:
        raise AssertionError('Unsafe CLI configuration key was accepted')


async def verify_hub():
    calls = []
    async def read(args):
        calls.append('read')
        return 'read-ok'
    async def write(args):
        calls.append('write')
        return 'write-ok'
    specs = [{'fn': name, 'description': name, 'schema': {}} for name in ['javis_read_file', 'javis_write_file']]
    routes = {'javis_read_file': {'call': read}, 'javis_write_file': {'call': write}}
    async def no_mcp(*a, **k):
        return [], {}
    with patch.object(mcp_hub.mcp_store, 'resolved', return_value=[]), \
            patch.object(mcp_hub.mcp_client, 'discover_resolved', side_effect=no_mcp), \
            patch.object(mcp_hub, '_builtin_tools', return_value=(specs, routes)), \
            patch.object(main.plugins_host, 'has_tool_hooks', return_value=False):
        mcp_hub._cache.clear()
        root = os.environ['JAVIS_STATE_DIR']
        a, route_a = await mcp_hub.discover_all('auto', root, include_plugins=False,
                                               tool_allowlist=['javis_read_file'])
        b, route_b = await mcp_hub.discover_all('auto', root, include_plugins=False,
                                               tool_allowlist=['javis_write_file'])
        assert {t['fn'] for t in a} == {'javis_read_file'}
        assert set(route_a) == {'javis_read_file'} and set(route_b) == {'javis_write_file'}
        empty, empty_routes = await mcp_hub.discover_all('auto', root, include_plugins=False, tool_allowlist=[])
        assert empty == [] and empty_routes == {}
        forged = await mcp_hub._handle_one({'id': 1, 'method': 'tools/call',
            'params': {'name': 'javis_write_file', 'arguments': {}}}, 'auto',
            include_plugins=False, vault_root=root, tool_allowlist=['javis_read_file'])
        assert forged['result']['isError'] and not calls
        ok = await mcp_hub._handle_one({'id': 2, 'method': 'tools/call',
            'params': {'name': 'javis_read_file', 'arguments': {}}}, 'auto',
            include_plugins=False, vault_root=root, tool_allowlist=['javis_read_file'])
        assert not ok['result']['isError'] and calls == ['read']
        print('PASS hub denies forged calls, isolates scope caches and treats [] as deny-all')


asyncio.run(verify_hub())


async def verify_http_scope():
    async def receive():
        return {'type': 'http.request', 'body': b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'}
    def request(value):
        return Request({'type':'http', 'method':'POST', 'path':'/hub/mcp',
                        'headers':[(b'authorization',b'Bearer TEST'),
                                   (b'x-javis-tool-allowlist',value.encode())]},receive)
    from unittest.mock import AsyncMock
    with patch.object(mcp_hub, 'hub_token', return_value='TEST'):
        for invalid in ['null', '{}', '"read"', '["bad name"]', '[2]', '[' + ','.join(['"a"']*257) + ']']:
            assert (await mcp_hub.handle_http(request(invalid))).status_code == 400
        with patch.object(mcp_hub, 'tra_loi_jsonrpc', new=AsyncMock(return_value='OK')) as dispatch:
            assert await mcp_hub.handle_http(request('[]')) == 'OK'
            assert dispatch.call_args.kwargs['tool_allowlist'] == []
        with patch('chat_bridge.goi_tool',new=AsyncMock(side_effect=AssertionError('bridge escape'))):
            denied=await mcp_hub._handle_one({'id':1,'method':'tools/call',
                'params':{'name':'javis_run_tool','arguments':{}}},'auto',gate={},tool_allowlist=['*'])
            assert denied['result']['isError']
        specs=[{'fn':'read_doc','description':'read','schema':{}}]
        with patch.object(mcp_hub.chatbot_doc_tools,'build',return_value=(specs,{'read_doc':{}})):
            assert await mcp_hub.discover_all(mcp_hub.chatbot_doc_tools.MODE,tool_allowlist=[]) == ([],{})
    print('PASS invalid HTTP scopes, empty transport scope, dispatcher denial and document-mode scope')


asyncio.run(verify_http_scope())
print('ALL PASS')
