/* Exercise the actual availability dialog without network or browser dependencies. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../../dashboard/console.js'), 'utf8');
const start = code.indexOf('    async function openScope(p) {');
const end = code.indexOf('\n    function openAdd()', start);
assert(start > 0 && end > start);
const factory = new Function('env', `with (env) { ${code.slice(start, end)}; return openScope; }`);
let checks = 0;
function check(name, ok) { assert(ok, name); checks++; console.log('ok ' + name); }
function harness(selection = ['/brain/a'], behavior = 'ok') {
  const calls = [], messages = [], status = {textContent: ''}, submit = {disabled: false};
  const boxes = {hidden: selection === null};
  const form = {dataset: {}, elements: {scope: {value: selection === null ? 'global' : 'selected'}},
    checked: [], isConnected: true,
    querySelector: s => s === '[data-scope-status]' ? status : s === '.pl-scope-brains' ? boxes : submit,
    querySelectorAll: () => form.checked.map(value => ({value: String(value)}))};
  let html = '', loads = 0, closed = 0;
  const env = {fbrain: () => '/brain/a', myGen: 1, _renderGen: 1,
    esc: s => String(s).replaceAll('<', '&lt;').replaceAll('"', '&quot;'), tt: k => k, ic: () => '',
    layer: {querySelector: () => form}, openLayer: s => {html = s;},
    closeLayer: () => {closed++;}, toast: s => messages.push(s), load: async () => {loads++;},
    URLSearchParams,
    fetch: async (url, request) => {
      calls.push({url, request});
      if (!request) return {json: async () => ({ok: true, digest: 'revision-1', selected_brains: selection,
        brains: [{name: 'a', path: '/brain/a', label: '<A>'}, {name: 'b', path: '/brain/b'}]})};
      if (behavior === 'lost') throw new Error('connection lost');
      return {json: async () => behavior === 'conflict' ? {ok: false, error: 'changed'} : {ok: true}};
    }};
  return {open: factory(env), env, form, status, submit, boxes, calls, messages,
    html: () => html, loads: () => loads, closed: () => closed};
}
const plugin = {slug: 'demo', name: 'Demo', source: 'vault'};
const event = {preventDefault() {}};
(async () => {
  let h = harness(); await h.open(plugin);
  check('renders registered brains and escapes labels', h.html().includes('&lt;A>') && !h.html().includes('<A>'));
  await h.form.onsubmit(event);
  check('empty selection does not send a mutation', h.calls.length === 1 && h.status.textContent === 'cs.pl_scope_empty');
  h.form.checked = [0, 1]; await h.form.onsubmit(event);
  const body = JSON.parse(h.calls[1].request.body);
  check('selected brains use exact registered paths and observed revision', body.digest === 'revision-1' && body.scope === 'brain' && JSON.stringify(body.target_brains) === '["/brain/a","/brain/b"]');
  check('successful save closes dialog and refreshes once', h.closed() === 1 && h.loads() === 1);
  h = harness(null); await h.open({...plugin, source: 'user'});
  check('global policy renders global selection', h.html().includes('value="global" checked') && h.boxes.hidden);
  await h.form.onsubmit(event);
  check('global save permits no selected brains', JSON.parse(h.calls[1].request.body).target_scope === 'global' && h.loads() === 1);
  h = harness(['/brain/a'], 'lost'); await h.open(plugin); h.form.checked = [1];
  await h.form.onsubmit(event); await h.form.onsubmit(event);
  check('lost save response requires readback and prevents duplicate submission', h.calls.length === 2 && h.submit.disabled && h.loads() === 1 && h.status.textContent === 'cs.pl_scope_unknown');
  h = harness(['/brain/a'], 'conflict'); await h.open(plugin); h.form.checked = [1]; await h.form.onsubmit(event);
  check('definitive rejection shows error without claiming success', h.status.textContent === 'changed' && !h.submit.disabled && h.closed() === 0);
  h = harness(); h.env._renderGen = 2; await h.open(plugin);
  check('stale page response cannot open a dialog', h.html() === '');
  for (const language of ['vi', 'en']) {
    const dict = JSON.parse(fs.readFileSync(path.join(__dirname, '../../dashboard/i18n', language + '.json')));
    const keys = [...code.slice(start, end).matchAll(/tt\("([^"]+)"/g)].map(m => m[1]);
    check(language + ' provides every dialog string', keys.every(k => dict[k]));
  }
  console.log(`PASS ${checks} plugin scope UI checks`);
})().catch(e => {console.error(e); process.exit(1);});
