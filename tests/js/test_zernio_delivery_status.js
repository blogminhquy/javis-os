const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('dashboard/conversations.js','utf8');
class Element {
  constructor() { this.nodes = {}; this.disabled = false; this.textContent = ''; }
  set innerHTML(value) { this.html = value; this.nodes = {}; for (const m of value.matchAll(/id="([^"]+)"/g)) this.nodes['#'+m[1]] = new Element(); }
  get innerHTML() { return this.html || ''; }
  querySelector(s) { return this.nodes[s]; }
}
for (const lang of ['vi','en']) test('recovery controls and conflicts in '+lang, async () => {
  const dictionary = JSON.parse(fs.readFileSync('dashboard/i18n/'+lang+'.json','utf8'));
  const calls = [], opened = [];
  let conflict = false, resolved = false;
  const issue = {id:'issue',revision:2,conversation_id:42,reason:'unsupported_media',attempts:3,next_retry_at:null,created_at:123};
  const t = (key,args={}) => { assert.ok(dictionary[key], 'missing translation '+key); return dictionary[key].replace(/\{(\w+)\}/g,(_,k)=>args[k]); };
  const context = {window:{t}, esc: v=>String(v).replace(/</g,'&lt;'), gio: v=>'time '+v, brain:()=> 'Brain A',
    moTu: value=>opened.push(value), infoBtn:()=>'', infoBody:s=>s,
    api:async(url,opts)=>{ calls.push({url,opts}); if(opts){if(conflict){const e=new Error('conflict');e.status=409;throw e;} resolved=true;return {ok:true};} return {issues:resolved?[]:[issue]}; }};
  vm.createContext(context);
  const start=source.indexOf('  async function zernioIssues('), end=source.indexOf('  function openZernioIssues(',start);
  assert.ok(start>=0 && end>start, 'production recovery view exists');
  vm.runInContext(source.slice(start,end),context);
  const host=new Element();
  await context.zernioIssues(host,{id:'acc_a'});
  assert.ok(host.innerHTML.includes(t('ht.zernio.issue_media')));
  assert.ok(host.innerHTML.includes('3'));
  await host.querySelector('#htZIChat0').onclick();
  assert.equal(opened[0].id,42);
  conflict=true;
  await host.querySelector('#htZIResolve0').onclick();
  assert.equal(host.querySelector('#htZIStatus').textContent,t('ht.zernio.issue_conflict'));
  assert.equal(host.querySelector('#htZIResolve0').disabled,true);
  conflict=false;
  await host.querySelector('#htZIReload').onclick();
  await host.querySelector('#htZIResolve0').onclick();
  const post=calls.find(c=>c.opts);
  assert.deepEqual(JSON.parse(post.opts.body),{revision:2,resolution:'handled_by_staff'});
  assert.ok(post.url.includes('brain=Brain%20A'));
  assert.ok(host.innerHTML.includes(t('ht.zernio.issue_empty')));
  assert.ok(calls.every(c=>!c.url.includes('send')&&!c.url.includes('mode')));
  resolved=false;issue.next_retry_at=456;issue.reason='provider_http_429';
  await context.zernioIssues(host,{id:'acc_a'});
  assert.ok(host.innerHTML.includes('time 456'));
  assert.equal(host.querySelector('#htZIResolve0').disabled,true);
});
test('conversation link selects requested inbox conversation in production navigation', () => {
  const context={_msgs:[{id:999}],_conv:{id:7},_draftEdit:{text:'old draft'},dropMic:()=>{},_cho:null,_chon:7,_tab:'kenh',TABS:['inbox','kenh'],_host:{},document:{body:{contains:()=>true}},
    chuanTab:s=>s,veTabs:()=>{},veTab:()=>{context.rendered=context._chon;}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function moTu('),source.indexOf('  window.JavisConversations =')),context);
  context.moTu({tab:'inbox',id:42,account_key:'zernio:acc_a'});
  assert.equal(context.rendered,42);
  assert.equal(context._msgs.length,0);
  assert.equal(context._conv,null);
  assert.equal(context._draftEdit,null);
  assert.equal(context._cho.account_key,'zernio:acc_a');
});
