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
  let current=true, fail=null, block=null, rejected=null, mode='suggest', outcomes=options.outcomes||[], consent=[], experiment={experiment_id:'experiment-one',generation:7,phase:'comparing'}, refreshFail=false;
  const ctx={window:{},document:{createElement:tag=>new Element(tag)},crypto:webcrypto,AbortController,setTimeout,clearTimeout,
    t:key=>{assert.ok(key in dict,`Missing ${lang} ${key}`);return dict[key];},
    fetch:async(url,config={})=>{
      const body=config.body?JSON.parse(config.body):null,path=url.split('?')[0];calls.push({path,body,config});
      if(block&&path.endsWith(block.suffix)){const b=block;block=null;b.enter();await b.promise;}
      if(fail&&path.endsWith(fail)){fail=null;throw Error('Lost response');}
      if(rejected&&path.endsWith(rejected.suffix)){
        const value=rejected;rejected=null;
        if(value.admitted)outcomes=[{status:'operation_recorded',operation_status:'pending',operation_id:'operation-one'}];
        return {ok:false,status:value.status,json:async()=>({ok:false})};
      }
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
      else if(path.endsWith('/next')){experiment={...experiment,generation:experiment.generation+1};data={result:{status:'completed',generation:experiment.generation}};if(options.failAfterNext){refreshFail=true;options.failAfterNext=false;}}
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
  return {mounted,calls,find,text,reviews,setMode:x=>mode=x,fail:x=>fail=x,
    reject:(suffix,status,admitted=false)=>rejected={suffix,status,admitted},
    stale:()=>{current=false;mounted.dispose();},block:suffix=>{
      let release,enter;const promise=new Promise(r=>release=r);release.entered=new Promise(r=>enter=r);
      block={suffix,promise,enter};return release;
    }};
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

const recoveryCases=[
  ['T2-R1 older blocked metadata cannot restore revoked consent',async()=>{
    const f=await fixture();
    try {
      await f.find('compose-preview').onclick();await f.find('compose-consent').onclick();
      const release=f.block('/operations'),older=f.find('experiment-refresh').onclick();await release.entered;
      try {
        await f.find('compose-revoke-consent-one').onclick();
        assert.ok(f.text().includes('Revoked'),'Newer revoke and its authoritative reload must finish first');
      } finally {release();await older;}
      assert.ok(f.text().includes('Revoked'),'An older active-consent snapshot must not overwrite revoked state');
      assert.equal(f.calls.filter(x=>x.path.endsWith('/compose-revoke')).length,1);
      assert.equal(f.calls.filter(x=>x.path.endsWith('/compose')).length,0);
    } finally {f.mounted.dispose();}
  }],
  ['T2-R2 authoritative refresh resolves acknowledged next without replay',async()=>{
    const f=await fixture('en',{trial:true,failAfterNext:true});
    try {
      f.find('comparison-ref').value='comparison-real';await f.find('next').onclick();
      assert.equal(f.find('next').disabled,true,'Refresh failure retains the acknowledged guard');
      await f.find('experiment-refresh').onclick();
      assert.equal(f.calls.filter(x=>x.path.endsWith('/next')).length,1,'Manual refresh never replays the recorded action');
      assert.equal(f.find('next').disabled,false,'Successful authoritative refresh must allow a new next action');
      f.find('comparison-ref').value='comparison-real';await f.find('next').onclick();
      const next=f.calls.filter(x=>x.path.endsWith('/next'));assert.equal(next.length,2);
      assert.equal(next[1].body.expected_generation,next[0].body.expected_generation+1);
      assert.notEqual(next[1].body.event_key,next[0].body.event_key);
    } finally {f.mounted.dispose();}
  }],
  ['T2-R3 refused creation accepts corrected prepared refs as a new intent',async()=>{
    const f=await fixture('en',{noExperiment:true,noCandidates:true});
    try {
      f.find('contract-ref').value='contract-unavailable';f.find('case-set-ref').value='case-set-real';f.find('base-bundle-ref').value='bundle-real';
      f.reject('/improvement-experiments',403);await f.find('experiment-create').onclick();
      f.find('contract-ref').value='contract-corrected';await f.find('experiment-create').onclick();
      const creates=f.calls.filter(x=>x.path==='/improvement-experiments');assert.equal(creates.length,2);
      assert.equal(creates[1].body.contract_id,'contract-corrected','Definite pre-creation refusal must not trap old input');
      assert.notEqual(creates[1].body.event_key,creates[0].body.event_key);
    } finally {f.mounted.dispose();}
  }],
  ['Older snapshot cannot resolve an acknowledgment created after it began',async()=>{
    const f=await fixture('en',{trial:true,failAfterNext:true});
    try {
      const release=f.block('/operations'),older=f.find('experiment-refresh').onclick();await release.entered;
      try {
        f.find('comparison-ref').value='comparison-real';await f.find('next').onclick();
        assert.equal(f.find('next').disabled,true,'New acknowledged action awaits authoritative refresh');
      } finally {release();await older;}
      assert.equal(f.find('next').disabled,true,'Superseded snapshot cannot unlock a newer acknowledged action');
      assert.equal(f.calls.filter(x=>x.path.endsWith('/next')).length,1);
      await f.find('experiment-refresh').onclick();assert.equal(f.find('next').disabled,false);
    } finally {f.mounted.dispose();}
  }],
  ['Creation conflict keeps its exact intent without proof of safe reset',async()=>{
    const f=await fixture('en',{noExperiment:true,noCandidates:true});
    try {
      f.find('contract-ref').value='contract-stale';f.find('case-set-ref').value='case-set-real';f.find('base-bundle-ref').value='bundle-real';
      f.reject('/improvement-experiments',409);await f.find('experiment-create').onclick();
      f.find('contract-ref').value='contract-changed';await f.find('experiment-create').onclick();
      const creates=f.calls.filter(x=>x.path==='/improvement-experiments');assert.equal(creates.length,2);
      assert.deepEqual(creates[1].body,creates[0].body);
    } finally {f.mounted.dispose();}
  }],
  ['Uncertain creation stays exact even after a later definite refusal',async()=>{
    const f=await fixture('en',{noExperiment:true,noCandidates:true});
    try {
      f.find('contract-ref').value='contract-uncertain';f.find('case-set-ref').value='case-set-real';f.find('base-bundle-ref').value='bundle-real';
      f.fail('/improvement-experiments');await f.find('experiment-create').onclick();
      f.find('contract-ref').value='contract-changed';f.reject('/improvement-experiments',403);await f.find('experiment-create').onclick();
      await f.find('experiment-create').onclick();
      const creates=f.calls.filter(x=>x.path==='/improvement-experiments');assert.equal(creates.length,3);
      assert.deepEqual(creates[1].body,creates[0].body);assert.deepEqual(creates[2].body,creates[0].body);
    } finally {f.mounted.dispose();}
  }],
];
for(const status of [400,403,409]) recoveryCases.push(['Execution refusal '+status+' cannot reset a compose intent',async()=>{
  const f=await fixture();
  try {
    await f.find('compose-preview').onclick();await f.find('compose-consent').onclick();
    f.reject('/compose',status);await f.find('compose-run').onclick();await f.find('compose-run').onclick();
    const runs=f.calls.filter(x=>x.path.endsWith('/compose'));assert.equal(runs.length,2);assert.deepEqual(runs[0].body,runs[1].body);
  } finally {f.mounted.dispose();}
}]);
recoveryCases.push(['Admitted stale compose consumes the cold scope without resampling',async()=>{
  const f=await fixture();
  try {
    await f.find('compose-preview').onclick();await f.find('compose-consent').onclick();
    f.reject('/compose',409,true);await f.find('compose-run').onclick();await f.find('experiment-refresh').onclick();
    assert.equal(f.find('compose-run').disabled,true);await f.find('compose-run').onclick();
    assert.equal(f.calls.filter(x=>x.path.endsWith('/compose')).length,1);
  } finally {f.mounted.dispose();}
}]);
const failures=[];
for(const [name,run] of recoveryCases){try{await run();console.log('PASS: '+name);}catch(error){failures.push(name+': '+error.stack);}}
assert.equal(failures.length,0,failures.join('\n\n'));
