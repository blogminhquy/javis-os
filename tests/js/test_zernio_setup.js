// Execute the production form and save handlers with a small DOM harness, no network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('dashboard/conversations.js', 'utf8');
const dictionaries = ['vi', 'en'].map(lang => JSON.parse(fs.readFileSync(`dashboard/i18n/${lang}.json`, 'utf8')));
const escape = s => String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
class Node {
  constructor() { this.value = ''; this.disabled = false; this.nodes = {}; this.events = {}; }
  set innerHTML(html) {
    this.html = html;
    for (const match of html.matchAll(/<(input|select|div|button)[^>]*\bid="([^"]+)"[^>]*>/g)) {
      const child = new Node();
      child.value = (match[0].match(/value="([^"]*)"/) || [,''])[1];
      this.nodes['#' + match[2]] = child;
    }
  }
  get innerHTML() { return this.html || ''; }
  querySelector(id) { return this.nodes[id] || null; }
  addEventListener(name, fn) { this.events[name] = fn; }
}
const flush = () => new Promise(resolve => setImmediate(resolve));
async function testForm(dictionary) {
  const calls = [];
  let failAccounts = false;
  let resolveSlow;
  const context = { window: {t: key => { assert.ok(dictionary[key], key); return dictionary[key]; }},
    esc: escape, infoBtn: () => '<button class="info-i">i</button>', infoBody: html => '<div class="info-body">'+html+'</div>',
    fd: data => data, api: async (url, options) => {
      calls.push({url, options});
      if (url.endsWith('/connections')) return {connections:[{id:'conn-a',label:'First'},{id:'conn-b',label:'Second'}]};
      if (url.includes('webhook-info')) return {webhook_url:'https://example.com/webhooks/zernio', events:['message.received'],signature_header:'X-Zernio-Signature',signature_algorithm:'HMAC-SHA256',https:true};
      if (failAccounts) throw new Error('provider_unavailable');
      if (url.includes('conn-a')) return new Promise(resolve => { resolveSlow = resolve; });
      return {accounts:[{id:'provider-b',username:'alice',platform:'instagram'}]};
    }};
  const formCode = source.slice(source.indexOf('  function zernioForm('), source.indexOf('  async function moThemTK('));
  vm.createContext(context); vm.runInContext(formCode, context);
  const host = new Node(); const form = context.zernioForm(host); await flush();
  const node = id => host.querySelector('#' + id);
  assert.match(node('htZConnection').innerHTML, /Second/);
  assert.match(node('htZWebhook').innerHTML, /https:\/\/example.com\/webhooks\/zernio/);
  assert.match(node('htZWebhook').innerHTML, /message.received/);
  assert.match(node('htZWebhook').innerHTML, /info-body/);
  assert.match(host.innerHTML, /id="htZSecret" type="password"/);
  assert.match(host.innerHTML, /id="htZKey" type="password"/);
  assert.throws(() => form.token(), /./);
  node('htZConnection').value = 'conn-b'; node('htZConnection').onchange(); await flush();
  assert.equal(node('htZKey').disabled, true);
  assert.match(node('htZAccount').innerHTML, /provider-b/);
  node('htZAccount').value = 'provider-b'; node('htZAccount').selectedIndex = 1;
  node('htZAccount').options = [{}, {dataset:{username:'alice'}}]; node('htZAccount').onchange();
  node('htZSecret').value = 'private-signing';
  const token = JSON.parse(form.token());
  assert.deepEqual(token, {account_id:'provider-b',username:'alice',secret:'private-signing',connection_id:'conn-b'});
  assert.equal(node('htZUser').value, 'alice');
  // A late response from the old connection cannot replace the new account list.
  node('htZConnection').value = 'conn-a'; node('htZConnection').onchange(); await flush();
  node('htZConnection').value = 'conn-b'; node('htZConnection').onchange(); await flush();
  resolveSlow({accounts:[{id:'stale',username:'stale',platform:'instagram'}]}); await flush();
  assert.doesNotMatch(node('htZAccount').innerHTML, /stale/);
  failAccounts = true; await node('htZLoad').onclick();
  assert.equal(node('htZStatus').textContent, 'provider_unavailable');
  failAccounts = false;
  node('htZConnection').value = ''; node('htZConnection').onchange();
  node('htZKey').value = 'private-key'; await node('htZLoad').onclick();
  assert.equal(calls.at(-1).url, '/channels/zernio/connected-accounts');
  assert.equal(calls.at(-1).options.method, 'POST');
  assert.equal(calls.at(-1).options.body.api_key, 'private-key');
  assert.equal(JSON.parse(form.token()).api_key, 'private-key');
  assert.ok(calls.every(call => !call.url.includes('private-key')));
  const editorHost = new Node();
  const editor = context.zernioForm(editorHost, {meta:{account_id:'provider-b'},external_id:'alice'}); await flush();
  assert.equal(editor.token(), '');
  editorHost.oninput();
  assert.throws(() => editor.token(), /./);
}
async function testSaveFailure(edit) {
  let closed = false, calledBack = false, notified = '';
  const button = {disabled:false};
  const box = {querySelector: id => ({'.ht-save':button,'#htLabel':{value:'Example'},'#htToken':{value:''}}[id] || null), querySelectorAll: () => []};
  const start = source.indexOf('    box.querySelector(".ht-save").onclick = async function () {', edit ? source.indexOf('  function moSuaTK(') : source.indexOf('  async function moThemTK('));
  const end = source.indexOf('\n    };', start);
  const handler = source.slice(start, end + 7);
  const apiCode = source.slice(source.indexOf('  async function api('), source.indexOf('  function fd('));
  const context = {box, chon:'zernio', a:{id:'acc_a'}, uname:'', zernio:{token:()=>'{"example":"credentials"}'},
    kenhCua:()=>({}), brain:()=>'', fd:d=>d, dong:()=>{closed=true;}, opts:{onXong:()=>{calledBack=true;}},
    alert:message=>{notified=message;}, window:{t:key=>key}, _tab:'kenh', taiTK:()=>{}, veTab:()=>{},
    fetch:async()=>({ok:true,status:200,json:async()=>({ok:false,error:'account_username_mismatch'})})};
  vm.createContext(context); vm.runInContext(apiCode + handler, context);
  await button.onclick();
  assert.equal(button.disabled,false);
  assert.equal(closed,false); assert.equal(calledBack,false);
  assert.match(notified,/account_username_mismatch/);
  // A successful create exposes the public Javis account to the existing bot picker callback.
  if (!edit) {
    context.fetch = async()=>({ok:true,json:async()=>({ok:true,id:'acc_created',account:{id:'acc_created',channel:'zernio'}})});
    await button.onclick();
    assert.equal(closed,true); assert.equal(calledBack,true);
  }
}
(async()=>{
  for (const dictionary of dictionaries) await testForm(dictionary);
  await testSaveFailure(false); await testSaveFailure(true);
  console.log('PASS Zernio setup: vi/en, connections, accounts, JSON credentials, stale loads, help, secret inputs, create/edit ok=false and create callback');
})().catch(error=>{console.error(error);process.exitCode=1;});
