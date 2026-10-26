// Exercise the public panel using an inert DOM and real WebCrypto, without a server/model.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { webcrypto, createHash } from "node:crypto";

let activeDocument;
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.attrs = {}; this.value = ""; this.textContent = ""; this.disabled = false; this.hidden = false; this.style = {}; }
  set innerHTML(_) { throw Error("Private review must never parse HTML"); }
  append(...nodes) { for (const node of nodes) { node.parentElement = this; this.children.push(node); } }
  prepend(...nodes) { for (const node of nodes.reverse()) { node.parentElement = this; this.children.unshift(node); } }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(x => x !== this); this.isConnected = false; }
  focus() { activeDocument.activeElement = this; }
  querySelectorAll(selector) { const all = this.children.flatMap(x => [x, ...x.querySelectorAll(selector)]); return all.filter(x => selector.includes(',') ? ['button','input','textarea','select'].includes(x.tagName) || x.tabIndex===0 : selector === "button" ? x.tagName === "button" : x.attrs["data-action"] === selector.match(/data-action="(.*?)"/)?.[1]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}
const source = fs.readFileSync(new URL("../../dashboard/improvement-candidates.js", import.meta.url), "utf8");
const raw = '\ufefftitle\r\nViệt 😀\r\n<script>attack()</script>\n[JAVIS_RULE:x] ![x](javascript:attack())';
const hash = s => createHash("sha256").update(s).digest("hex");
const exact = text => ({ text, hash: hash(text), byte_size: Buffer.byteLength(text) });
const candidate = { candidate_id: "candidate-one", experiment_id: "experiment-one", base_revision_id: "revision-one", target_id: "target-one", base_generation: 1,
  base_hash: hash(raw), content_hash: hash(raw + "\nnew"), ordinal: 1, semantic_status: "unreviewed", context_grant: {status: "active"}, edit_authority: null };
async function fixture(lang = "en", withExperiments = false) {
  const dict = JSON.parse(fs.readFileSync(new URL(`../../dashboard/i18n/${lang}.json`, import.meta.url)));
  const body = new Element("body"), head = new Element("head"), calls = [], intervals = [];
  let applied = [], granted = [], routed = [], lastRouting = null, procs = [], overlays = [], packs = [], lastBundle = null, governed = [{kind: "skill", pointer_id: "iac_1", generation: 1}],
    loopState = {examples: {ok: true, tuning: 4, qualification: 12, estimated_calls: 67}, protected: false, exists: true, runs: []},
    autoState = {stats: {pending: 2, mistakes: {"skill:bao-gia": 1}}, history: [{id: "alr_" + "1".repeat(16), kind: "skill",
      slug: "bao-gia", step: -1, state: "done", verdict: "helped", applied: 1, undone_at: null, started_at: 1800000000}]};
  let brain = "brain-one", rows = [candidate], deferred = null, corrupt = false, failStage = false, pages = false, failAfterStage = false, failRows = false;
  const ctx = { document: { body, head, createElement: tag => new Element(tag), getElementById: () => null, addEventListener() {} },
    window: { currentBrainPath: () => brain }, TextEncoder, TextDecoder, crypto: webcrypto, URL, URLSearchParams, Blob,
    setInterval: fn => { intervals.push(fn); return intervals.length; }, clearInterval() {}, setTimeout, clearTimeout, AbortController,
    t: key => { assert.ok(key in dict, `Missing ${lang} translation: ${key}`); return dict[key]; },
    fetch: async (url, options = {}) => {
      calls.push({url: String(url), ...options});
      let value;
      const path = String(url).split("?")[0];
      if (path === "/improvement-candidate-contexts") value = {contexts:{items:[{context_id:"context-one",experiment_id:"experiment-one",target_id:"target-one",grant_status:"active",base_generation:1,current_generation:1,created_at:1,objectives:[{objective:"Review rows"}]}],next_cursor:pages?"cursor-two":null}};
      else if(path === '/improvement-policy') value={policy:{mode:'suggest'},capabilities:{trial:false,activation:false}};
      else if(path === '/improvement-contexts/experiment-one') value={context:{context_id:'context-one',experiment_id:'experiment-one',generation:4,grant_status:'active',target_generations:{'target-one':1}}};
      else if(path === '/improvement-experiments/experiment-one') value={experiment:{experiment_id:'experiment-one',generation:7,phase:'comparing'}};
      else if(path.endsWith('/policy')) value={policy:{multiple_tests:2,native_capability:'unknown'}};
      else if(path.endsWith('/compose-consents')) value={consents:[]};
      else if(path.endsWith('/compose-outcomes')) value={outcomes:[]};
      else if(path.endsWith('/operations')) value={operations:[]};
      else if(path.endsWith('/semantic-history')) value={receipts:[]};
      else if(path.endsWith('/compose-preview')) {if(deferred)await deferred;value={result:{input_hash:hash(raw),basis_hash:hash(raw),candidate_refs:[{id:raw}],tuning_refs:[],native_capability:'unknown'}};}
      else if (path === "/improvement-targets/capture") value = {capture:{target_id:"target-one",revision_id:"revision-one",generation:1}};
      else if (path === "/improvement-candidates" && !options.method) { if(failRows){failRows=false;throw Error("Metadata unavailable after acknowledged write");} value = {candidates: rows}; }
      else if (path.endsWith("/candidate-one/review")) {
        if (deferred) await deferred;
        value = {review:{candidate_id:candidate.candidate_id,before:exact(raw),after:exact(raw + "\nnew"),metadata:candidate, semantic_status:"unreviewed",hypothesis:"Exact instruction",failure_signature:"Missing row",expected_behavior:"All rows",possible_regressions:["Duplicate"]}};
        if (corrupt) value.review.after.hash = "0".repeat(64);
      } else if (path.includes("/improvement-candidate-baselines/")) value = {review:{target_id:"target-one",base_revision_id:"revision-one",base_generation:1,baseline:exact(raw),editable_start:Buffer.byteLength('\ufefftitle\r\n')}};
      else if (path.endsWith("/artifact-review")) value = {review:{artifact:exact(raw),task:"Exact task",contract:{objective:"Count rows"},fixtures:[{source_ref:"sources/rows.csv",source_version:"v1",timezone:"Asia/Saigon",data_period:"2026-10",cutoff:"2026-10-23",schema:{id:"rows-v1"},text:raw,fixture_hash:hash(raw),byte_size:Buffer.byteLength(raw)}]}};
      else if (path.endsWith("/authorize")) { rows = [{...candidate,edit_authority:{authority_id:"authority-one",generation:2,status:"revoked"}}]; value = {authority:{status:"active",generation:1}}; }
      else if (path === "/improvement-candidates") { if (failStage) {failStage=false;throw Error("Unknown transport outcome");} if(failAfterStage) failRows=true; value = {candidate}; }
      else if (path === "/improvement-activations" && !options.method) value = {activations: applied, coverage: {served: ["api_engines"]}};
      else if (path === "/improvement-activations") { const body = JSON.parse(options.body); applied = [{activation_id:"iac_" + "1".repeat(32), state:"active", generation:1, evidence_level:"manual_trial", reason:"owner_apply", selector:{context:"dm", agent_key:"agent-1", agent_slug:body.agent_slug}}]; value = {activation: applied[0]}; }
      else if (path === "/improvement-agent-procedures" && !options.method) value = {procedures: procs, overlays, coverage: {served: ["dm"]}};
      else if (path === "/improvement-agent-procedures") { const b = JSON.parse(options.body); procs = [{procedure_id: "iap_" + "5".repeat(32), agent_key: "agent-1", text: b.text}]; value = {procedure: procs[0]}; }
      else if (path.startsWith("/improvement-agent-procedures/")) { const b = JSON.parse(options.body); overlays = [{overlay_id: "iao_" + "6".repeat(32), procedure_id: procs[0].procedure_id, agent_key: "agent-1", state: "active", generation: 1, reason: "owner_apply", surfaces: b.surfaces, owner_confirmed: b.owner_confirmed}]; value = {overlay: overlays[0]}; }
      else if (path === "/auto-learning" && !options.method) value = autoState;
      else if (path.startsWith("/auto-learning/")) { autoState = {...autoState, history: [{...autoState.history[0], undone_at: 2}]}; value = {undone: true}; }
      else if (path === "/improvement-loops" && !options.method) value = loopState;
      else if (path === "/improvement-loops") { loopState = {...loopState, runs: [{run_id: "ilr_" + "9".repeat(24), state: "done", result: {chosen: "c1", chosen_text: "New skill text", report: {verdict: "helped", outcomes: {win: 5, tie: 1, loss: 0}, base_pass_rate: 0.4, candidate_pass_rate: 0.9}}}]}; value = {run: loopState.runs[0]}; }
      else if (path.startsWith("/improvement-loops/")) { loopState = {...loopState, runs: [{...loopState.runs[0], applied_at: 1}]}; value = {applied: {applied: true}}; }
      else if (path === "/improvement-governance" && !options.method) value = {live: governed};
      else if (path === "/improvement-governance/suspend-all") { governed = []; value = {suspended: [], skipped: [], remaining: []}; }
      else if (path === "/improvement-agent-bundles" && !options.method) value = {bundles: packs};
      else if (path === "/improvement-agent-bundles") { lastBundle = JSON.parse(options.body); packs = [{bundle_id: "iba_" + "7".repeat(32), state: "active", generation: 2, reason: "owner_apply", members: [{kind: "procedure", pointer_id: "iao_" + "8".repeat(32)}]}]; value = {bundle: packs[0]}; }
      else if (path.startsWith("/improvement-agent-bundles/")) { packs = [{...packs[0], state: "reverted", generation: 3}]; value = {bundle: packs[0]}; }
      else if (path.startsWith("/improvement-agent-overlays/")) { overlays = [{...overlays[0], state: "reverted", generation: 2}]; value = {overlay: overlays[0]}; }
      else if (path.endsWith("/revert")) { applied = [{...applied[0], state:"reverted", generation:2}]; value = {activation: applied[0]}; }
      else if (path === "/agents") value = {agents:[{slug:"ke-toan", name:"Accountant", description:"Books"}]};
      else if (path === "/improvement-auto-scopes" && !options.method) value = {grants: granted};
      else if (path === "/improvement-routing" && !options.method) value = {candidates: [], overlays: routed};
      else if (path === "/improvement-routing/evaluate") { lastRouting = JSON.parse(options.body); value = {routing: {candidate_id: "irc_" + "3".repeat(32), verdict: "eligible", report: {outcomes: {win: 5, loss: 0, tie: 2, unknown: 0}}}}; }
      else if (path.startsWith("/improvement-routing/") && path.endsWith("/apply")) { routed = [{overlay_id: "iro_" + "4".repeat(32), state: "active", generation: 1, description: lastRouting.description}]; value = {overlay: routed[0]}; }
      else if (path === "/improvement-auto-scopes") { granted = [{grant_id:"ias_" + "2".repeat(32), status:"active", generation:1, allocation_pct:10, selector:{agent_slug:JSON.parse(options.body).agent_slug}}]; value = {grant: granted[0]}; }
      else throw Error(`Unexpected request ${path}`);
      return {ok:true,status:200,json:async()=>({ok:true,...value})};
    } };
  activeDocument=ctx.document;
  vm.createContext(ctx);
  if(withExperiments)vm.runInContext(fs.readFileSync(new URL('../../dashboard/improvement-experiments.js',import.meta.url),'utf8'),ctx);
  vm.runInContext(source, ctx);
  await ctx.window.JavisImprovementCandidates.open({brain:"brain-one",slug:"test-skill"});
  const find = action => { const nodes = body.querySelectorAll(`[data-action="${action}"]`); assert.ok(nodes.length, `Missing action ${action}`); return nodes.at(-1); };
  return {ctx,body,calls,find,intervals,setBrain:b=>{brain=b;},setRows:r=>{rows=r;},defer:p=>{deferred=p;},corrupt:()=>{corrupt=true;},failStage:()=>{failStage=true;},pages:()=>{pages=true;},failAfterStage:()=>{failAfterStage=true;}};
}
for (const lang of ["vi","en"]) {
  const f = await fixture(lang);
  await f.find("review-candidate-one").onclick();
  assert.equal(f.find("before-text").textContent, raw);
  assert.equal(f.find("after-text").textContent, raw + "\nnew");
  assert.ok(f.find("after-facts").textContent.includes(hash(raw + "\nnew")));
  await f.find("authorize").onclick();
  assert.equal(f.find("authorize").disabled, true, "Historical approval must refresh revoked current metadata");
  f.ctx.window.JavisImprovementCandidates.close();
}
for(const lang of ['vi','en']) {
  const f=await fixture(lang,true);
  assert.ok(f.calls.every(x=>!x.method),'Actual integrated open must only GET');
  assert.ok(f.find('compose-preview'));
  const panel=f.body.children[0], controls=panel.querySelectorAll("button, input, textarea, select, a[href], [tabindex='0']").filter(x=>!x.disabled&&!x.hidden);
  controls.at(-1).focus();let prevented=false;
  panel.onkeydown({key:'Tab',shiftKey:false,preventDefault(){prevented=true;}});
  assert.ok(prevented);assert.equal(f.ctx.document.activeElement,controls[0]);
  controls[0].focus();panel.onkeydown({key:'Tab',shiftKey:true,preventDefault(){}});assert.equal(f.ctx.document.activeElement,controls.at(-1));
  await f.find('review-candidate-one').onclick();const privateReview=f.find('after-text');
  let release;f.defer(new Promise(r=>release=r));const pending=f.find('review-candidate-one').onclick();
  const request=f.calls.at(-1);panel.onkeydown({key:'Escape'});
  assert.equal(request.signal.aborted,true,'Escape aborts private requests');
  assert.equal(f.body.children.length,0);release();await pending;
  assert.equal(f.body.querySelector('[data-action="after-text"]'),null);
  assert.ok(privateReview.textContent.includes('<script>'),'Fixture exercised actual private text before close');
}
{
  const f=await fixture('en',true);let release;f.defer(new Promise(r=>release=r));
  const pending=f.find('compose-preview').onclick();const request=f.calls.at(-1);
  const changed=f.find('context').onchange();
  assert.equal(request.signal.aborted,true,'Changing context aborts experiment requests immediately');
  assert.equal(f.body.querySelector('[data-action="compose-input-ref"]'),null);
  await changed;release();await pending;
  assert.equal(f.body.querySelector('[data-action="compose-input-ref"]'),null,'Old preview cannot enter new context');
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  const f=await fixture(); f.pages();
  await f.ctx.window.JavisImprovementCandidates.open({brain:"brain-one",slug:"test-skill"});
  await f.find("capture").onclick(); await f.find("capture").onclick();
  const captures=f.calls.filter(x=>x.url.startsWith("/improvement-targets/capture"));
  assert.equal(captures.length,2);
  assert.notEqual(JSON.parse(captures[0].body).event_key,JSON.parse(captures[1].body).event_key,"A completed capture must not replay forever for a new explicit intent");
  assert.equal(f.body.querySelectorAll('[data-action="more-contexts"]').length,1,"Reload replaces prior pagination control");
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  const f=await fixture(); await f.find("load-baseline").onclick(); f.failAfterStage();
  f.find("replacement").value="Retain all rows"; f.find("hypothesis").value="Check rows";
  f.find("failure_signature").value="Missing row"; f.find("expected_behavior").value="All rows"; f.find("possible_regressions").value="Double count";
  await f.find("stage").onclick();
  assert.equal(f.find("stage").disabled,true,"Acknowledged staging must stay disabled when only metadata refresh fails");
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  const f = await fixture('en',true); let sameSkill = true;
  await f.ctx.window.JavisImprovementCandidates.open({brain:"brain-one",slug:"test-skill",isCurrent:()=>sameSkill});
  let resolve; f.defer(new Promise(r=>{resolve=r;}));
  const pending = f.find("review-candidate-one").onclick();
  sameSkill=false; f.intervals.forEach(fn=>fn()); resolve(); await pending;
  assert.ok(!f.body.querySelector('[data-action="authorize"]'),"A switched Studio skill cannot retain review actions");
  assert.ok(!f.body.querySelector('[data-action="close"]'),"Close stale skill panel");
}
{
  const f = await fixture(); f.setRows([{...candidate,base_generation:2}]);
  await f.find("review-candidate-one").onclick();
  assert.equal(f.body.querySelector('[data-action="authorize"]'), null, "Changed target generation cannot authorize");
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  const f = await fixture();
  await f.ctx.window.JavisImprovementCandidates.openArtifact({brain:"brain-one",trialId:"trial-one",attempt:1});
  assert.equal(f.find("artifact-text").textContent, raw);
  assert.equal(f.find("fixture-0-text").textContent, raw);
  assert.ok(f.find("fixture-0-metadata").textContent.includes("Asia/Saigon"));
  assert.ok(f.find("fixture-0-metadata").textContent.includes("2026-10-23"));
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  const f = await fixture('en',true);
  let resolve; f.defer(new Promise(r=>{resolve=r;}));
  const pending = f.find("review-candidate-one").onclick();
  f.setBrain("brain-two"); f.intervals.forEach(fn=>fn()); resolve(); await pending;
  assert.ok(!f.body.querySelector('[data-action="authorize"]') || f.find("authorize").disabled, "Stale brain cannot authorize");
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  const f = await fixture(); f.corrupt(); await f.find("review-candidate-one").onclick();
  assert.equal(f.body.querySelector('[data-action="authorize"]'), null, "Hash mismatch must be unavailable");
  assert.ok(f.find("status").textContent.length);
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  const f = await fixture(); await f.find("load-baseline").onclick();
  const select = f.find("baseline-selection");
  select.value = raw.replace(/\r\n/g,"\n");
  select.selectionStart = select.value.indexOf("Việt"); select.selectionEnd = select.selectionStart + "Việt 😀".length;
  await f.find("use-selection").onclick();
  assert.equal(Number(f.find("start").value), Buffer.byteLength('\ufefftitle\r\n'));
  assert.equal(Number(f.find("end").value), Buffer.byteLength('\ufefftitle\r\nViệt 😀'));
  f.find("replacement").value = "Keep rows"; f.find("hypothesis").value = "Check omitted rows";
  f.find("failure_signature").value = "Omitted row"; f.find("expected_behavior").value = "All rows"; f.find("possible_regressions").value = "Double count";
  f.failStage(); await f.find("stage").onclick();
  assert.equal(f.find("stage").disabled,false);
  await f.find("stage").onclick();
  const staged = f.calls.find(x=>x.url.startsWith("/improvement-candidates?") && x.method === "POST");
  assert.equal(JSON.parse(staged.body).patch.start, Buffer.byteLength('\ufefftitle\r\n'));
  const writes = f.calls.filter(x=>x.url.startsWith("/improvement-candidates?") && x.method === "POST");
  assert.equal(writes.length,2); assert.equal(JSON.parse(writes[0].body).event_key,JSON.parse(writes[1].body).event_key,"Unknown write retry must keep its event key");
  f.ctx.window.JavisImprovementCandidates.close();
}
for (const lang of ["vi","en"]) {
  // M2E: an exact-diff authority offers apply to one assistant chat; revert uses the server generation.
  const f = await fixture(lang);
  f.setRows([{...candidate, edit_authority:{authority_id:"authority-two", kind:"exact_diff", generation:1, status:"active"}}]);
  await f.find("review-candidate-one").onclick();
  f.find("apply-agent").value = "ke-toan";
  await f.find("apply-candidate").onclick();
  const apply = f.calls.find(x=>x.url.startsWith("/improvement-activations?") && x.method === "POST");
  const sent = JSON.parse(apply.body);
  assert.equal(sent.candidate_id, "candidate-one"); assert.equal(sent.agent_slug, "ke-toan");
  assert.deepEqual(Object.keys(sent).sort(), ["agent_slug","candidate_id","event_key"]);
  const id = "iac_" + "1".repeat(32);
  assert.ok(f.find("activation-" + id).children.some(x=>x.textContent.includes("ke-toan")));
  await f.find("revert-" + id).onclick();
  const revert = f.calls.find(x=>x.url.startsWith(`/improvement-activations/${id}/revert`));
  assert.equal(JSON.parse(revert.body).expected_generation, 1);
  assert.equal(f.body.querySelector(`[data-action="revert-${id}"]`), null, "A reverted pointer offers no second revert");
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  // M3: a canary share sends allocation_pct; an owner grant posts a 10% auto-scope for the same assistant.
  const f = await fixture();
  f.setRows([{...candidate, edit_authority:{authority_id:"authority-two", kind:"exact_diff", generation:1, status:"active"}}]);
  await f.find("review-candidate-one").onclick();
  f.find("apply-agent").value = "ke-toan";
  f.find("apply-share").value = "10";
  await f.find("apply-candidate").onclick();
  const apply = f.calls.find(x=>x.url.startsWith("/improvement-activations?") && x.method === "POST");
  assert.equal(JSON.parse(apply.body).allocation_pct, 10);
  await f.find("grant-auto").onclick();
  const grant = f.calls.find(x=>x.url.startsWith("/improvement-auto-scopes?") && x.method === "POST");
  assert.deepEqual({...JSON.parse(grant.body), event_key: undefined}, {target_id:"target-one", agent_slug:"ke-toan", allocation_pct:10, event_key: undefined});
  assert.ok(f.find("revoke-grant-ias_" + "2".repeat(32)));
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  // M4: sample lines become closed cases; an eligible description can be applied to the main chat.
  const f = await fixture();
  f.setRows([{...candidate, edit_authority:{authority_id:"authority-two", kind:"exact_diff", generation:1, status:"active"}}]);
  await f.find("review-candidate-one").onclick();
  f.find("routing_description").value = "Reconcile codes and amounts";
  f.find("routing_cases").value = "positive | test-skill | reconcile codes\nnegative | | weather today\nbroken line";
  await f.find("routing-evaluate").onclick();
  const sent = JSON.parse(f.calls.find(x=>x.url.startsWith("/improvement-routing/evaluate?")).body);
  assert.deepEqual(sent.cases, [{kind:"positive", expected:"test-skill", query:"reconcile codes"}, {kind:"negative", expected:"", query:"weather today"}]);
  await f.find("routing-apply").onclick();
  assert.ok(f.find("routing-overlay-iro_" + "4".repeat(32)));
  f.ctx.window.JavisImprovementCandidates.close();
}
for (const lang of ["vi", "en"]) {
  // M5: the exact procedure text needs the owner's confirmation box, then reaches only the ticked surfaces.
  const f = await fixture(lang);
  f.setRows([{...candidate, edit_authority:{authority_id:"authority-two", kind:"exact_diff", generation:1, status:"active"}}]);
  await f.find("review-candidate-one").onclick();
  f.find("procedure-agent").value = "ke-toan";
  f.find("procedure_text").value = "Check sources first, then compare totals with last period.";
  f.find("procedure-surface-team").checked = true;
  await f.find("procedure-apply").onclick();
  assert.ok(!f.calls.some(x => x.url.startsWith("/improvement-agent-procedures?") && x.method === "POST"), "unconfirmed text is never sent");
  f.find("procedure-confirm").checked = true;
  await f.find("procedure-apply").onclick();
  const applyCall = f.calls.find(x => x.url.startsWith("/improvement-agent-procedures/") && x.url.includes("/apply"));
  assert.deepEqual(JSON.parse(applyCall.body).surfaces, ["dm", "team"]);
  assert.equal(JSON.parse(applyCall.body).owner_confirmed, true);
  const overlay = "iao_" + "6".repeat(32);
  assert.equal(f.find("procedure-overlay-text-" + overlay).textContent, "Check sources first, then compare totals with last period.");
  assert.equal(f.find("procedure-confirm").checked, false);
  await f.find("procedure-revert-" + overlay).onclick();
  assert.ok(f.calls.some(x => x.url.startsWith(`/improvement-agent-overlays/${overlay}/revert`)));
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  // M6: the reviewed exact candidate and the new procedure go out as one bundle, private chat only.
  const f = await fixture();
  f.setRows([{...candidate, edit_authority:{authority_id:"authority-two", kind:"exact_diff", generation:1, status:"active"}}]);
  await f.find("review-candidate-one").onclick();
  f.find("procedure-agent").value = "ke-toan";
  f.find("procedure_text").value = "Check sources first, then compare totals with last period.";
  f.find("procedure-confirm").checked = true;
  f.find("procedure-bundle").checked = true;
  f.find("procedure-surface-team").checked = true;
  await f.find("procedure-apply").onclick();
  assert.ok(!f.calls.some(x => x.url.startsWith("/improvement-agent-bundles?") && x.method === "POST"), "team is not covered by a bundle");
  f.find("procedure-surface-team").checked = false;
  await f.find("procedure-apply").onclick();
  const sent = JSON.parse(f.calls.find(x => x.url.startsWith("/improvement-agent-bundles?") && x.method === "POST").body);
  assert.equal(sent.manifest.members[0].candidate_id, "candidate-one");
  assert.deepEqual(sent.manifest.members[1].surfaces, ["dm"]);
  assert.equal(sent.owner_confirmed, true);
  await f.find("bundle-revert-iba_" + "7".repeat(32)).onclick();
  assert.ok(f.calls.some(x => x.url.startsWith("/improvement-agent-bundles/iba_" + "7".repeat(32) + "/revert")));
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  // Automatic learning: the brain-wide list shows what Javis changed on its own, and undo reverts it.
  const f = await fixture();
  assert.ok(f.find("auto-stats").textContent.includes("2"));
  assert.ok(f.find("auto-run-alr_" + "1".repeat(16)).children[0].textContent.includes("bao-gia"));
  await f.find("auto-undo-alr_" + "1".repeat(16)).onclick();
  assert.ok(f.calls.some(x => x.url.startsWith("/auto-learning/alr_" + "1".repeat(16) + "/undo") && x.method === "POST"));
  assert.throws(() => f.find("auto-undo-alr_" + "1".repeat(16)), /Missing action/);  // undone: no second undo
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  // Self-learning: start, read the verdict, apply the chosen text.
  const f = await fixture();
  assert.ok(f.find("loop-examples").textContent.includes("4"));
  await f.find("loop-start").onclick();
  assert.ok(f.calls.some(x => x.url.startsWith("/improvement-loops?") && x.method === "POST"));
  assert.equal(f.find("loop-text").textContent, "New skill text");
  await f.find("loop-apply").onclick();
  assert.ok(f.calls.some(x => x.url.startsWith("/improvement-loops/ilr_" + "9".repeat(24) + "/apply")));
  assert.ok(f.find("loop-applied"));
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  // M8: the pause button shows the live count and empties it in one call.
  const f = await fixture();
  assert.ok(f.find("governance-count").textContent.includes("1"));
  await f.find("governance-pause").onclick();
  assert.ok(f.calls.some(x => x.url.startsWith("/improvement-governance/suspend-all")));
  assert.ok(f.find("governance-count").textContent.includes("0"));
  assert.equal(f.find("governance-pause").disabled, true);
  f.ctx.window.JavisImprovementCandidates.close();
}
{
  // A region authority alone is not an exact approved diff: no apply control.
  const f = await fixture();
  f.setRows([{...candidate, edit_authority:{authority_id:"authority-three", kind:"editable_region", generation:1, status:"active"}}]);
  await f.find("review-candidate-one").onclick();
  assert.equal(f.body.querySelector('[data-action="apply-candidate"]'), null);
  f.ctx.window.JavisImprovementCandidates.close();
}
console.log("OK: exact inert vi/en review, revoked replay, brain race, corrupt hash and UTF-8/CRLF selection");
