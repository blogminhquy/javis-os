const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../../dashboard/model-picker.js'), 'utf8');
const rows = new Map();
const storage = new Map();
const calls = [];
let sid = 'chat-one';
let failSave = false;

function boot() {
  const events = {};
  const nodes = {mbModelTxt: {}, mbEffortTxt: {}};
  const document = {readyState: 'loading', getElementById: k => nodes[k] || null,
    addEventListener: (k, fn) => { events[k] = fn; }};
  const window = {t: k => k, JavisSessions: {current: () => sid, brain: () => 'test-brain'},
    addEventListener: (k, fn) => { events[k] = fn; },
    JavisModelList: {models: async () => ['gpt-6.1-sol'], render: async () => ''},
    matchMedia: () => ({matches: true})};
  const fetch = async (url, opts) => {
    calls.push({url, opts});
    if (url === '/settings') return {json: async () => ({model: {
      main: {provider: 'openai-oauth', model: 'gpt-6.1-sol'}, providers: [{id:'openai-oauth',configured:true,label:'OpenAI'}]}})};
    const match = /\/sessions\/([^/]+)\/(model|meta)/.exec(url);
    if (opts) {
      if (failSave) return {ok:false,json:async()=>({error:'blocked'})};
      const data = Object.fromEntries(opts.body);
      rows.set(match[1], {routing_mode:data.routing_mode, pinned_provider:data.provider, pinned_model:data.model});
      return {ok:true,json:async()=>({ok:true})};
    }
    return {ok:true,json:async()=>rows.get(match[1]) || {}};
  };
  vm.runInNewContext(source, {window, document, fetch, FormData, localStorage: {
    getItem: k => storage.get(k), setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k)},
    alert: () => {}, ic: () => ''});
  return {window,events,nodes};
}
async function choose(h, mode) {
  const button = {dataset:{routing:mode}};
  await h.events.click({target:{closest: selector => selector === '[data-routing]' ? button :
    selector === '#modelBar' ? {} : null}});
}
(async () => {
  let h=boot(); await h.window.initModelBar();
  await choose(h,'auto'); assert.equal(rows.get(sid).routing_mode,'auto');
  h=boot(); await h.window.initModelBar(); assert.equal(h.nodes.mbModelTxt.textContent,'mpick.auto');
  sid='chat-two'; await h.events['javis:sessions-changed']();
  await h.window.JavisModelBar.chon('gpt-6.1-sol');
  assert.equal(rows.get(sid).routing_mode,'pinned');
  assert.equal(rows.get('chat-one').routing_mode,'auto');
  assert(!calls.some(x=>x.url==='/settings' && x.opts), 'selection must not change brain defaults');
  await choose(h,'default'); assert.equal(rows.get(sid).routing_mode,'default');
  sid=null; await h.events['javis:sessions-changed'](); await choose(h,'auto');
  h=boot(); await h.window.initModelBar(); assert.equal(h.nodes.mbModelTxt.textContent,'mpick.auto');
  sid='new-chat'; await h.window.JavisModelBar.claimPending(sid);
  assert.equal(rows.get(sid).routing_mode,'auto');
  assert(!calls.some(x=>x.opts && x.opts.body.get('model') === 'auto'));
  failSave=true; await choose(h,'default');
  assert.equal(rows.get(sid).routing_mode,'auto','failed save must not overwrite selected mode');
  console.log('PASS: per-session Auto, pin, default, reload, pending first-turn save, isolation and failed save');
})().catch(e=>{console.error(e);process.exitCode=1;});
