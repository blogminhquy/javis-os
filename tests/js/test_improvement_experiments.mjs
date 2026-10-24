// Real mounted controller, inert DOM and labelled transport fixtures; no native execution.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
class Element {
  constructor(tag) { this.tagName=tag; this.children=[]; this.attrs={}; this.textContent=''; this.value=''; this.disabled=false; this.hidden=false; }
  set innerHTML(_) { throw Error('Never parse private HTML'); }
  append(...nodes) { for(const n of nodes){n.parentElement=this;this.children.push(n);} }
  replaceChildren(...nodes) { this.children=[];this.append(...nodes); }
  setAttribute(k,v) {this.attrs[k]=String(v);}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(x=>x!==this);}
  querySelectorAll(){return this.children.flatMap(x=>[x,...x.querySelectorAll()]);}
}
const file=new URL('../../dashboard/improvement-experiments.js',import.meta.url);
assert.ok(fs.existsSync(file),'Reachable actual experiment controller is absent');
const source=fs.readFileSync(file,'utf8');
const malicious='<img src=x onerror=attack()> [x](javascript:attack())';
async function fixture(lang='en',options={}) {
  const dict=JSON.parse(fs.readFileSync(new URL(`../../dashboard/i18n/${lang}.json`,import.meta.url)));
  const parent=new Element('section'),calls=[],reviews=[];
  let current=true, fail=null, block=null, mode='suggest', outcomes=options.outcomes||[], consent=[], experiment={experiment_id:'experiment-one',generation:7,phase:'comparing'}, refreshFail=false;
  const ctx={window:{},document:{createElement:tag=>new Element(tag)},crypto:webcrypto,AbortController,setTimeout,clearTimeout,
    t:key=>{assert.ok(key in dict,`Missing ${lang} ${key}`);return dict[key];},
    fetch:async(url,config={})=>{
      const body=config.body?JSON.parse(config.body):null,path=url.split('?')[0];calls.push({path,body,config});
      if(block&&path.endsWith(block.suffix)){const b=block;block=null;await b.promise;}
      if(fail&&path.endsWith(fail)){fail=null;throw Error('Lost response');}
      let data={},status=200;
      if(path==='/improvement-policy')data={policy:{mode},capabilities:{trial:options.trial===true,activation:false}};
      else if(path.startsWith('/improvement-contexts/'))data={context:{context_id:'context-one',experiment_id:'experiment-one',generation:4,grant_status:'active',target_generations:{'target-one':1}}};
      else if(path==='/improvement-experiments'){experiment={experiment_id:'experiment-one',generation:1,phase:'proposed'};data={result:experiment};}
      else if(path.endsWith('/experiment-one')){if(options.noExperiment){status=403;data={ok:false};}else data={experiment};}
      else if(path.endsWith('/policy'))data={policy:{multiple_tests:options.budget||2,candidate_policy:'two_proposals',native_capability:'unknown'}};
      else if(path.endsWith('/compose-outcomes')){if(refreshFail){refreshFail=false;throw Error('Refresh failed');}data={outcomes};}
      else if(path.endsWith('/compose-consents'))data={consents:consent};
      else if(path.endsWith('/operations'))data={operations:[]};
      else if(path==='/improvement-candidates')data={candidates:options.noCandidates?[]:[{candidate_id:'candidate-three',ordinal:3,edit_authority:null}]};
      else if(path.endsWith('/semantic-history'))data={receipts:[]};
      else if(path.endsWith('/compose-preview'))data={result:{generation:7,input_hash:'a'.repeat(64),basis_hash:'b'.repeat(64),candidate_refs:[{id:malicious,content_hash:'c'.repeat(64)}],tuning_refs:[{id:'report-one',report_hash:'d'.repeat(64)}],native_capability:'unknown'}};
      else if(path.endsWith('/compose-authorize')){consent=[{authorization_id:'consent-one',experiment_generation:7,generation:1,status:'active'}];data={result:consent[0]};}
      else if(path.endsWith('/compose-revoke')){consent=[{...consent[0],generation:2,status:'revoked'}];data={result:consent[0]};}
      else if(path.endsWith('/compose')){outcomes=[{status:'keep_base',operation_status:'completed',operation_id:'operation-one'}];data={result:outcomes[0]};if(options.failAfterRun)refreshFail=true;}
      else if(path.endsWith('/semantic-evidence'))data={result:{verdict:'unknown',native_verdict:'fail',dependencies:{verdict:'unknown'},assessment:{verdict:'pass'},reason:malicious}};
      else if(path.endsWith('/next')){experiment={...experiment,generation:experiment.generation+1};data={result:{status:'completed',generation:experiment.generation}};}
      else if(path.endsWith('/freeze'))data={result:{comparison_id:'comparison-real',kind:body.kind}};
      else if(path.endsWith('/view-freeze'))data={result:{comparison_id:body.comparison_id}};
      else if(path.endsWith('/view-evidence'))data={result:{observational_unknowns:[malicious]}};
      else if(path.endsWith('/report'))data={result:{report_id:'report-real'}};
      else if(path.endsWith('/select'))data={result:{generation:experiment.generation+1}};
      else if(path.startsWith('/improvement-comparison-reports/'))data={report:{experiment_id:'experiment-one',summary:{complete:false,mechanical_verdict:'inconclusive',business_eligibility:'unverified',outcomes:{tuning:{win:0,unknown:1},qualification:{loss:1},regression:{unknown:1}}}}};
      else throw Error('Unexpected route '+path);
      return {ok:status===200,status,json:async()=>({ok:status===200,...data})};
    }};
  vm.createContext(ctx);vm.runInContext(source,ctx);
  const mounted=ctx.window.JavisImprovementExperiments.mount({parent,brain:'brain-one',context:{context_id:'context-one',experiment_id:'experiment-one',target_id:'target-one',grant_status:'active',base_generation:1,current_generation:1},isCurrent:()=>current,review:id=>reviews.push(id),refreshCandidates:async()=>{}});
  await mounted.ready;
  const find=action=>{const el=parent.querySelectorAll().find(x=>x.attrs['data-action']===action);assert.ok(el,'Missing '+action);return el;};
  const text=()=>parent.querySelectorAll().map(x=>x.textContent).join('\n');
  return {mounted,calls,find,text,reviews,setMode:x=>mode=x,fail:x=>fail=x,stale:()=>{current=false;mounted.dispose();},block:suffix=>{let release;const promise=new Promise(r=>release=r);block={suffix,promise};return release;}};
}
for(const lang of ['vi','en']) {
  const f=await fixture(lang);
  assert.ok(f.calls.every(x=>!x.body),'Open must only GET');
  assert.equal(f.find('next').disabled,true,'Actual unavailable trial capability stays closed');
  assert.ok(f.text().includes('3'));
  assert.equal(f.find('compose-run').disabled,true);
  await f.find('compose-preview').onclick();
  assert.ok(f.text().includes(malicious),'Malicious refs render as inert text');
  assert.equal(f.calls.filter(x=>x.path.endsWith('/compose-authorize')).length,0);
  await f.find('compose-consent').onclick();
  assert.equal(f.calls.filter(x=>x.path.endsWith('/compose')).length,0,'Consent never runs');
  await f.find('compose-run').onclick();
  const run=f.calls.find(x=>x.path.endsWith('/compose'));
  assert.deepEqual(Object.keys(run.body).sort(),['authorization_id','event_key','expected_generation']);
  assert.equal(run.body.expected_generation,7);
  assert.ok(f.text().includes('KEEP_BASE'));
  await f.find('experiment-review-candidate-three').onclick();assert.deepEqual(f.reviews,['candidate-three']);
  await f.find('semantic-evidence-candidate-three').onclick();assert.ok(f.text().includes(malicious));
  f.setMode('off');await f.find('experiment-refresh').onclick();
  await f.find('compose-revoke-consent-one').onclick();
  assert.equal(f.calls.at(-1).body,null);
  const revoke=f.calls.find(x=>x.path.endsWith('/compose-revoke'));assert.equal(revoke.body.expected_generation,1);
  assert.ok(f.text().includes(lang==='vi'?'Đã thu hồi':'Revoked'));
  f.mounted.dispose();assert.equal(f.text(),'');
}
{
  // Synthetic transport capability only; never native qualification/execution.
  const f=await fixture('en',{trial:true,budget:3});
  f.find('comparison-ref').value='comparison-real';await f.find('next').onclick();
  f.find('comparison-ref').value='comparison-real';await f.find('next').onclick();
  const calls=f.calls.filter(x=>x.path.endsWith('/next'));assert.equal(calls.length,2,'Each next cell requires a fresh explicit intent');
  assert.equal(calls[1].body.expected_generation,calls[0].body.expected_generation+1);assert.notEqual(calls[0].body.event_key,calls[1].body.event_key);
  f.find('comparison-ref').value='comparison-real';await f.find('view-freeze').onclick();
  f.find('comparison-ref').value='comparison-real';await f.find('view-evidence').onclick();assert.ok(f.text().includes(malicious));
  f.find('comparison-ref').value='comparison-real';await f.find('report').onclick();
  await f.find('read-report').onclick();assert.ok(f.text().includes('inconclusive'));assert.ok(f.text().includes('Final qualification result'));assert.ok(f.text().includes('unverified'));
  const keys=f.calls.filter(x=>x.path.endsWith('/view-freeze')||x.path.endsWith('/view-evidence')||x.path.endsWith('/report'));
  for(const call of keys)assert.deepEqual(Object.keys(call.body).sort(),['comparison_id','event_key','expected_generation']);
  await f.find('select-candidate').onclick();
  const selection=f.calls.find(x=>x.path.endsWith('/select'));assert.equal(selection.body.choice,'candidate');assert.equal(selection.body.ordinal,3);
  assert.deepEqual(Object.keys(selection.body).sort(),['choice','event_key','expected_generation','ordinal']);
  f.mounted.dispose();
}
{
  const f=await fixture();const release=f.block('/compose-preview');
  const first=f.find('compose-preview').onclick();await f.find('compose-preview').onclick();
  assert.equal(f.calls.filter(x=>x.path.endsWith('/compose-preview')).length,1,'Duplicate click creates no intent');
  release();await first;
  f.fail('/compose-authorize');await f.find('compose-consent').onclick();await f.find('compose-consent').onclick();
  const writes=f.calls.filter(x=>x.path.endsWith('/compose-authorize'));assert.equal(writes.length,2);assert.deepEqual(writes[0].body,writes[1].body,'Lost response retries exact event and payload');
  f.mounted.dispose();
}
{
  const f=await fixture();const release=f.block('/compose-preview');const pending=f.find('compose-preview').onclick();
  f.stale();assert.equal(f.text(),'','Private content clears synchronously');
  assert.equal(f.calls.at(-1).config.signal.aborted,true,'Switch aborts active request');release();await pending;assert.equal(f.text(),'');
}
{
  const f=await fixture('en',{failAfterRun:true});await f.find('compose-preview').onclick();await f.find('compose-consent').onclick();await f.find('compose-run').onclick();
  assert.equal(f.find('compose-run').disabled,true,'Acknowledged run stays acknowledged after refresh failure');
  await f.find('compose-run').onclick();assert.equal(f.calls.filter(x=>x.path.endsWith('/compose')).length,1);f.mounted.dispose();
}
for(const status of ['operation_recorded','invalid_output','native_incomplete','candidate_staged']){
  const f=await fixture('en',{outcomes:[{status,operation_status:'cancelled'}]});assert.ok(f.calls.every(x=>!x.body));assert.equal(f.find('compose-run').disabled,true);assert.ok(f.text().length);f.mounted.dispose();
}
{
  const f=await fixture('en',{noExperiment:true,noCandidates:true});
  f.find('contract-ref').value='contract-real';f.find('case-set-ref').value='case-set-real';f.find('base-bundle-ref').value='bundle-real';f.find('candidate-budget').value='3';
  await f.find('experiment-create').onclick();const call=f.calls.find(x=>x.path==='/improvement-experiments');
  assert.equal(call.body.expected_context_generation,4,'Use actual context grant generation, not target generation');assert.equal(call.body.candidate_policy,'two_proposals_and_one_compose');f.mounted.dispose();
}
console.log('PASS: real controller vi/en, cold-only open, separate consent/run, immutable budget, exact retry, duplicate guard, abort/clear, acknowledged refresh failure and historical outcomes');
