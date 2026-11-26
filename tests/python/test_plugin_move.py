"""Plugin scope: preserve bytes, isolate discovery and cached calls, refuse unsafe moves."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-scope-")
import plugin_authoring
import plugin_move
import plugin_scope
import plugins_host
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes.plugin_move import PluginMoveDeps, register

base = Path(tempfile.mkdtemp())
a, b, c = [base / name for name in ("a", "b", "c")]
roots = [a, b, c]
for p in roots:
    p.mkdir()
plugins_host.BUNDLED_DIR = base / "bundled"
checks = 0


def check(name, value):
    global checks
    assert value, name
    checks += 1
    print("ok " + name)


def make(slug, root=a, enabled=True, nested=False):
    p = root / ("Javis/plugins" if nested else "plugins") / slug
    p.mkdir(parents=True)
    (p / "plugin.yaml").write_text(f"name: Demo\nslug: {slug}\nenabled: {str(enabled).lower()}\nmin_mode: safe\ntools: [scope_echo]\n")
    (p / "plugin.py").write_text("def register(ctx):\n    ctx.register_tool('scope_echo', 'echo', lambda args, ctx: 'ok', min_mode='safe')\n")
    (p / "asset.bin").write_bytes(b"\x00\xff\x01")
    return p


def configure(slug, scope, root, targets):
    return plugin_move.configure(slug, scope, root, targets, roots, plugin_move.inspect(slug, scope, root)["digest"])


def listed(root, slug):
    return next((x for x in plugins_host.describe(str(root)) if x['slug'] == slug), None)


def tools(root, **kw):
    return plugins_host.plugin_tools('full', str(root), **kw)


def refused(name, reason, fn):
    try:
        fn()
    except plugin_move.MoveError as e:
        check(name, str(e) == reason)
    else:
        raise AssertionError(name)


src = make("demo")
original = plugin_move.fingerprint(src)
plugin_authoring._ledger_set(plugin_authoring._ledger_key('brain', src.parent, 'demo'), {'created': 'test', 'dir': str(src)})
data = plugins_host._PLUGIN_DATA_DIR / 'demo'
data.mkdir(parents=True)
(data / 'state.json').write_text('{"saved":42}')
r = configure('demo', 'brain', a, [a, b])
dest = plugins_host.GLOBAL_DIR / 'demo'
check('private folder becomes one shared copy with byte-identical content', not src.exists() and plugin_move.fingerprint(dest) == original)
check('enabled and permission preserved', r['enabled'] and listed(a, 'demo')['min_mode'] == 'safe')
check('selected brains see plugin, unselected brain does not', listed(a, 'demo') and listed(b, 'demo') and not listed(c, 'demo'))
check('no-brain discovery excludes selected plugins', not any(x['slug'] == 'demo' for x in plugins_host.describe()))
check('data_dir state preserved', (data / 'state.json').read_text() == '{"saved":42}')
check('authoring ownership migrated', plugin_authoring._ledger_key('global', dest.parent, 'demo') in plugin_authoring._read_ledger())
check('selected plugin tools work with scope_vault=False and real brain context', 'scope_echo' in tools(b, scope_vault=False)[1] and 'scope_echo' not in tools(c, scope_vault=False)[1])
stale = tools(b)[1]['scope_echo']['call']
check('cached handler initially works', asyncio.run(stale({})) == 'ok')
configure('demo', 'global', a, [a])
check('cached handler refuses after brain is deselected', asyncio.run(stale({})).startswith('ERROR:'))
# A call can already be waiting for an async condition when availability changes.
ctx = plugins_host.PluginContext('demo', 'user', dest, str(a))
ran = []
async def revoke_during_check():
    configure('demo', 'global', a, [b])
    await asyncio.sleep(0)
    return ''
pending = plugins_host._make_call({'name': 'scope_wait', 'handler': lambda args, context: ran.append(True),
    'min_mode': 'safe', 'check_fn': revoke_during_check}, ctx, 'full')
check('in-flight approval rechecks availability before executing', asyncio.run(pending({})).startswith('ERROR:') and not ran)
configure('demo', 'global', b, [a])

check('fresh tool discovery excludes deselected brain', 'scope_echo' not in tools(b)[1])
configure('demo', 'global', a, None)
check('global available in every brain', all(listed(p, 'demo') for p in roots))
d = base / 'future'; d.mkdir()
check('global includes future brains', listed(d, 'demo') is not None)
configure('demo', 'global', a, [b, c])
check('changing selection removes old brain and adds new ones', not listed(a, 'demo') and listed(b, 'demo') and listed(c, 'demo'))
rev = plugin_move.inspect('demo', 'global', b)['digest']
(dest / 'README.md').write_text('new version')
refused('stale consent refuses changed code', 'source_changed', lambda: plugin_move.configure('demo', 'global', b, None, roots, rev))
rev = plugin_move.inspect('demo', 'global', b)['digest']
configure('demo', 'global', b, [b])
refused('stale consent refuses changed selection', 'source_changed', lambda: plugin_move.configure('demo', 'global', b, None, roots, rev))
refused('empty selection refused', 'unknown_brain', lambda: configure('demo', 'global', b, []))
refused('traversal slug refused', 'invalid_slug', lambda: plugin_move.inspect('../demo', 'brain', a))
conflict = make('conflict', a)
make('conflict', c, nested=True)
refused('duplicate hidden in legacy layout refused', 'destination_conflict', lambda: configure('conflict', 'brain', a, [b]))
check('duplicate refusal keeps source', conflict.is_dir())
link = make('linked', a)
(link / 'secret').symlink_to('/etc/passwd')
refused('symlink payload refused', 'symlink', lambda: plugin_move.inspect('linked', 'brain', a))
plugins_host.BUNDLED_DIR.mkdir()
make('builtin', base / 'bundle-root').rename(plugins_host.BUNDLED_DIR / 'builtin')
refused('bundled slug cannot be moved', 'protected_plugin', lambda: plugin_move.inspect('builtin', 'global', a))
with patch.object(plugin_authoring, '_pack_slugs', return_value={'pack-slug'}):
    refused('pack slug cannot be moved', 'protected_plugin', lambda: plugin_move.inspect('pack-slug', 'global', a))
legacy_root = base / 'legacy'; legacy_root.mkdir(); roots.append(legacy_root)
legacy = make('legacy', legacy_root, enabled=False, nested=True)
configure('legacy', 'brain', legacy_root, [a])
check('legacy layout moves and disabled state stays off', not legacy.exists() and listed(a, 'legacy')['enabled'] is False)
rollback = make('rollback', a)
policy_before = plugin_scope.PATH.read_bytes()
with patch.object(plugin_move.os, 'rename', side_effect=OSError('simulated disk error')):
    try:
        configure('rollback', 'brain', a, [b])
    except OSError:
        pass
    else:
        raise AssertionError('expected simulated error')
check('failed move restores policy and keeps source', rollback.exists() and plugin_scope.PATH.read_bytes() == policy_before)
with patch.object(plugin_move.os, 'replace', side_effect=OSError('simulated atomic write failure')):
    try:
        configure('rollback', 'brain', a, [b])
    except OSError:
        pass
check('failed policy write keeps source and policy', rollback.exists() and plugin_scope.PATH.read_bytes() == policy_before)
# Real owner-only routes, with strictly listed brain identities.
app = FastAPI(); refreshed = []
register(app, PluginMoveDeps(lambda req: req.cookies.get('javis_session') == 'good',
    lambda: [{'name': p.name, 'path': str(p), 'label': p.name} for p in roots], lambda: a, refreshed.append))
client = TestClient(app)
check('options rejects anonymous', client.get('/plugins/move-options', params={'slug':'demo','scope':'global'}).status_code == 401)
check('move rejects anonymous', client.post('/plugins/move', json={}).status_code == 401)
client.cookies.set('javis_session', 'good')
check('unknown brain never falls back to default', client.get('/plugins/move-options', params={'slug':'demo','scope':'global','brain':'missing'}).status_code == 400)
opts = client.get('/plugins/move-options', params={'slug':'demo','scope':'global','brain':str(b)}).json()
check('options supplies registered brains and current selection', opts['ok'] and opts['selected_brains'] == [str(b)] and len(opts['brains']) == len(roots))
body = {'slug':'demo','scope':'global','brain':str(b),'target_scope':'selected','target_brains':[str(a),str(c)],'digest':opts['digest']}
response = client.post('/plugins/move', json=body)
check('owner route updates multiple brains and refreshes all indexes', response.status_code == 200 and response.json()['ok'] and refreshed == [[str(p) for p in roots]])
check('repeated stale request is rejected', client.post('/plugins/move', json=body).status_code == 409)
check('malformed JSON rejected', client.post('/plugins/move', content='{').status_code == 400)
check('unknown scope rejected', client.post('/plugins/move', json=dict(body,target_scope='wrong')).status_code == 400)
check('unregistered target rejected', client.post('/plugins/move', json=dict(body,target_brains=['/tmp'])).status_code == 400)
# Corrupt policy must fail closed, even for a cached callable.
plugin_scope.PATH.write_text('{bad')
plugin_scope.invalidate(); plugins_host.invalidate()
check('corrupt policy hides shared plugin', listed(a, 'demo') is None and not plugin_scope.allowed('demo', str(a)))
for invalid in (None, 'global', [None]):
    plugin_scope.PATH.write_text(json.dumps({'demo': invalid}))
    plugin_scope.invalidate()
    check('invalid policy value cannot grant global access', not plugin_scope.allowed('demo', str(a)))
print(f'PASS {checks} plugin scope checks')
