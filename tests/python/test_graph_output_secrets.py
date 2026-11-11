"""Graph tool outputs must never expose credentials, including nested paging URLs."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import copy
import importlib.util
import json
from urllib.parse import parse_qs, urlsplit

from graph_output import sanitize_graph_output


def load_plugin(slug):
    spec = importlib.util.spec_from_file_location(slug, ROOT / 'system/plugins' / slug / 'plugin.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


payload = {
    'data': [{'id': 'P1_1', 'message': 'Public post', 'comments': {
        'data': [], 'paging': {'next': 'https://graph.facebook.com/v25.0/c?after=a%2Bb&access_token=FAKE_PAGE'}}}],
    'paging': {'cursors': {'before': 'B', 'after': 'A'},
               'next': 'https://graph.facebook.com/v25.0/feed?%61ccess_token=FAKE_USER&limit=1&after=A',
               'previous': 'https://graph.facebook.com/v25.0/feed?before=B&appsecret_proof=FAKE_PROOF'},
    'nested': [{'access_token': 'FAKE_NESTED', 'refresh_token': 'FAKE_REFRESH', 'count': 4}],
}
original = copy.deepcopy(payload)
for slug in ('meta-pages-graph', 'meta-ads-graph'):
    plugin = load_plugin(slug)
    result = plugin._fmt(payload)
    assert 'FAKE_' not in result, (slug, 'credential leak')
    safe = json.loads(result)
    assert safe['paging']['cursors'] == {'before': 'B', 'after': 'A'}
    assert parse_qs(urlsplit(safe['paging']['next']).query) == {'limit': ['1'], 'after': ['A']}
    assert safe['data'][0]['message'] == 'Public post'
    assert safe['nested'] == [{'count': 4}]
    error = plugin._fmt({'error': {'message': 'Failed https://graph.facebook.com/a?access_token=FAKE_ERROR&limit=2', 'code': 190}})
    assert error.startswith('ERROR:') and 'FAKE_ERROR' not in error and 'limit=2' in error
    print('PASS', slug, 'nested paging, fields, errors, cursor preservation')
assert payload == original, 'Sanitization mutated internal token-bearing API data'
assert 'FAKE_AUTH' not in sanitize_graph_output('Authorization: Bearer FAKE_AUTH')
assert 'FAKE_PARAM' not in sanitize_graph_output('Request access_token=FAKE_PARAM failed')
assert sanitize_graph_output({'id': 1, 'ok': True, 'data': None}) == {'id': 1, 'ok': True, 'data': None}


async def read_handlers():
    plugin = load_plugin('meta-pages-graph')
    async def token():
        return 'FAKE_USER'
    async def resolve(*args):
        return 'P1', 'FAKE_PAGE', 'Page', None
    async def get(*args):
        return payload
    plugin._token, plugin._resolve_page, plugin._get = token, resolve, get
    for handler, args in ((plugin._posts, {'page_id': 'P1'}),
                          (plugin._comments, {'post_id': 'P1_1'})):
        assert 'FAKE_' not in await handler(args, None)
    print('PASS real posts and comments handlers sanitize their responses')


asyncio.run(read_handlers())
print('ALL PASS')
