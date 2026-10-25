/* Explicit owner controls. Cold history never starts or resumes work. */
(function () {
  'use strict';
  const tr = key => t('improve.' + key);
  const id = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(value);
  function node(tag, text, action) {
    const el = document.createElement(tag);
    if (text != null) el.textContent = String(text);
    if (action) el.setAttribute('data-action', action);
    return el;
  }
  function button(label, action, fn) {
    const el = node('button', label, action); el.type = 'button'; el.onclick = fn; return el;
  }
  function info(parent, key) {
    const toggle = button(tr('explanation'), 'experiment-explanation', null);
    toggle.className = 'info-i with-text'; toggle.setAttribute('aria-expanded', 'false');
    const body = node('div', tr(key)); body.className = 'info-body'; body.hidden = true;
    parent.append(toggle, body);
  }
  function field(parent, key, action, choices) {
    const label = node('label', tr(key)), input = node(choices ? 'select' : 'input', null, action);
    if (choices) {
      for (const [value, key] of choices) { const option = node('option', tr(key)); option.value = value; input.append(option); }
      input.value = choices[0][0];
    } else { input.type = 'text'; input.maxLength = 128; input.autocomplete = 'off'; }
    label.append(input); parent.append(label); return input;
  }
  function mount({parent, brain, context, isCurrent, review, refreshCandidates}) {
    const root = node('section'); root.className = 'improvement-experiment-controls'; parent.append(root);
    const s = {closed:false, version:1, requests:new Set(), intents:new Map(), experiment:null, preview:null,
      consents:[], outcomes:[], rows:[], busy:false, acknowledged:new Set(), loadVersion:0};
    const base = '/improvement-experiments/' + encodeURIComponent(context.experiment_id);
    const alive = (version = s.version) => !s.closed && s.version === version && (!isCurrent || isCurrent());
    function dispose() {
      s.closed = true; s.version++; root.replaceChildren(); root.remove();
      for (const request of s.requests) request.abort(); s.requests.clear();
      s.preview = null; s.rows = []; s.consents = []; s.outcomes = []; s.intents.clear();
    }
    async function request(path, body) {
      const version = s.version;
      if (!alive(version)) throw Error('stale_panel');
      const controller = new AbortController(); s.requests.add(controller);
      const timer = setTimeout(() => controller.abort(), 30000);
      try {
        const response = await fetch(path + (path.includes('?') ? '&' : '?') + 'brain=' + encodeURIComponent(brain), {
          credentials:'same-origin', signal:controller.signal,
          ...(body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)})});
        const data = await response.json();
        if (!alive(version)) throw Error('stale_panel');
        if (!response.ok || data.ok !== true) { const error = Error('unavailable'); error.status = response.status; throw error; }
        return data;
      } finally { clearTimeout(timer); s.requests.delete(controller); }
    }
    function failure(error) {
      if (alive()) status.textContent = tr(error.status === 409 ? 'stale' : error.status === 400 ? 'rejected' : 'unavailable');
    }
    // Retain the entire closed payload on an uncertain retry, even if a later
    // metadata read has moved generation. An acknowledged write cannot be retried.
    async function write(name, path, payload) {
      let intent = s.intents.get(name);
      if (!intent) { intent = {path,body:{...payload,event_key:'experiment-ui-' + crypto.randomUUID()}}; s.intents.set(name,intent); }
      try {
        const data = await request(intent.path,intent.body);
        s.intents.delete(name); return data.result;
      } catch(error) {
        // Create is fixed-identity metadata in one transaction, never Operation
        // admission. Only its first definite validation/scope refusal can be
        // corrected. A prior uncertain response keeps even later refusals exact.
        if(name==='experiment-create' && !intent.uncertain && [400,403].includes(error.status)) s.intents.delete(name);
        else intent.uncertain=true;
        throw error;
      }
    }
    function action(label, name, payload, done, {path=base + '/' + name, enabled=true, refresh=true} = {}) {
      const el = button(tr(label), name, async () => {
        if (!alive() || el.disabled || s.busy || s.acknowledged.has(name)) return;
        s.busy = true; el.disabled = true;
        s.loadVersion++; // Invalidate snapshots started before this explicit write.
        const version = s.version; let acknowledged = false;
        try {
          const result = await write(name,path,payload());
          if (!alive(version)) return;
          acknowledged = true; s.acknowledged.add(name); status.textContent = tr('write_acknowledged');
          if (done) await done(result);
          if (!alive(version)) return;
          if (refresh) { await load(); if (refreshCandidates && alive(version)) await refreshCandidates(); }
          if (alive(version)) { s.acknowledged.delete(name); render(); }
        } catch (error) {
          if (alive(version)) {
            if (acknowledged) status.textContent = tr('write_refresh_required');
            else { failure(error); el.disabled = false; }
          }
        } finally { if (alive(version)) s.busy = false; }
      });
      el.disabled = !enabled || s.acknowledged.has(name); return el;
    }
    root.append(node('h3', tr('experiment_title'))); info(root,'compose_scope_hint');
    const status = node('p',tr('loading'),'experiment-status'); status.setAttribute('role','status'); root.append(status);
    const refresh = button(tr('refresh'), 'experiment-refresh', async () => {
      if (!alive() || refresh.disabled || s.busy) return;
      refresh.disabled = true;
      try { s.preview = null; evidence.replaceChildren(); render(); await load(); }
      catch(error) { failure(error); }
      finally { if(alive()) refresh.disabled = false; }
    }); root.append(refresh);
    const content = node('div'), evidence = node('div'); root.append(content,evidence);
    const generation = () => ({expected_generation:s.experiment.generation});
    const active = () => s.policy?.mode === 'suggest' && s.context?.grant_status === 'active'
      && context.base_generation === context.current_generation
      && s.context.experiment_id === context.experiment_id && s.context.context_id === context.context_id
      && s.context.target_generations?.[context.target_id] === context.base_generation;
    const live = () => active() && ['proposing','probing','comparing'].includes(s.experiment?.phase);
    function facts(parent, label, value) { parent.append(node('p', tr(label) + ': ' + String(value ?? tr('unknown')))); }
    function showEvidence(value) {
      evidence.replaceChildren();
      // Explicit authorized evidence only, bounded and inert. Unknown dependency
      // facts stay unknown; the semantic projection does not supply that verdict.
      for (const key of ['verdict','native_verdict']) facts(evidence,key,value[key]);
      facts(evidence,'dependency_verdict',null);
      const pre = node('pre',JSON.stringify(value,null,2).slice(0,32768),'experiment-evidence'); pre.tabIndex = 0; evidence.append(pre);
    }
    function showReport(value) {
      evidence.replaceChildren();
      const summary=value.summary;
      facts(evidence,'report_complete',summary?.complete);
      facts(evidence,'mechanical_verdict',summary?.mechanical_verdict);
      facts(evidence,'business_eligibility',summary?.business_eligibility);
      for(const [split,label] of [['tuning','tuning_result'],['qualification','final_result'],['regression','regression_result']]) {
        evidence.append(node('h4',tr(label)),node('pre',JSON.stringify(summary?.outcomes?.[split] ?? tr('unknown'))));
      }
      const pre=node('pre',JSON.stringify(value,null,2).slice(0,32768),'experiment-evidence');pre.tabIndex=0;evidence.append(pre);
    }
    function createForm() {
      content.append(node('p',tr('prepared_refs_required')));
      if (!active() || s.context.target_generations?.[context.target_id] !== context.base_generation
          || !Number.isSafeInteger(s.context.generation)) return;
      const contract = field(content,'contract_ref','contract-ref'), cases = field(content,'case_set_ref','case-set-ref');
      const bundle = field(content,'base_bundle_ref','base-bundle-ref');
      const budget = field(content,'budget','candidate-budget',[['2','budget_two'],['3','budget_three']]);
      const repeat = field(content,'repeat_policy','repeat-policy',[['feasibility','repeat_feasibility'],['pilot','repeat_pilot']]);
      const timeout = field(content,'timeout_seconds','experiment-timeout'); timeout.type = 'number'; timeout.min = '1'; timeout.max = '300'; timeout.value = '60';
      content.append(action('create_experiment','experiment-create',() => {
        if (![contract.value,cases.value,bundle.value].every(id) || !['2','3'].includes(budget.value)
            || !Number.isInteger(Number(timeout.value)) || Number(timeout.value)<1 || Number(timeout.value)>300) throw {status:400};
        return {experiment_id:context.experiment_id,contract_id:contract.value,case_set_id:cases.value,base_bundle_id:bundle.value,
          expected_context_generation:s.context.generation,repeat_policy:repeat.value,timeout_seconds:Number(timeout.value),
          ...(budget.value === '3' ? {candidate_policy:'two_proposals_and_one_compose'} : {})};
      },null,{path:'/improvement-experiments'}));
    }
    function render() {
      content.replaceChildren();
      facts(content,'policy_mode',s.policy?.mode);
      content.append(node('p',tr('native_unverified')),node('p',tr('activation_unknown')));
      if (!s.experiment) { createForm(); return; }
      facts(content,'experiment_phase',s.experiment.phase); facts(content,'generation',s.experiment.generation);
      facts(content,'budget',s.immutable.multiple_tests);
      content.append(node('p',tr(s.immutable.multiple_tests === 3 ? 'budget_three_saved' : 'budget_two_saved')));
      for (const outcome of s.outcomes) {
        const labels = {keep_base:'outcome_keep_base',candidate_staged:'outcome_staged',invalid_output:'outcome_invalid',native_incomplete:'outcome_native_incomplete',operation_recorded:'outcome_recorded'};
        content.append(node('p',tr(labels[outcome.status] || 'unknown'),'compose-outcome'));
        facts(content,'operation_status',outcome.operation_status); facts(content,'operation_ref',outcome.operation_id);
      }
      for (const op of s.operations) facts(content,'operation_status',op.kind + ' · ' + op.status);
      const scope = ['probing','comparing'].includes(s.experiment.phase) && active() && !s.outcomes.length;
      content.append(action('compose_preview','compose-preview',generation,result => {
        s.preview = result; s.acknowledged.delete('compose-preview'); render();
      },{enabled:scope,refresh:false}));
      if (s.preview) {
        facts(content,'input_ref',s.preview.input_hash); facts(content,'basis_ref',s.preview.basis_hash);
        for(const ref of [...s.preview.candidate_refs,...s.preview.tuning_refs]) {
          const pre=node('pre',JSON.stringify(ref),'compose-input-ref');pre.tabIndex=0;content.append(pre);
        }
      }
      const consent = s.consents.find(x=>x.status === 'active');
      for (const saved of s.consents) {
        facts(content,'compose_consent_status',tr(saved.status === 'active' ? 'consent_active' : 'consent_revoked'));
        facts(content,'consent_generation',saved.generation); facts(content,'consent_experiment_generation',saved.experiment_generation);
        if(saved.status === 'active') content.append(action('compose_revoke','compose-revoke-' + saved.authorization_id,
          () => ({authorization_id:saved.authorization_id,expected_generation:saved.generation}),null,{path:base+'/compose-revoke'}));
      }
      content.append(action('compose_consent','compose-consent',generation,result=>{
        s.consents = [result]; render();
      },{path:base+'/compose-authorize',enabled:scope && !!s.preview && !consent}));
      content.append(action('compose_run','compose-run',() => ({authorization_id:consent.authorization_id,expected_generation:consent.experiment_generation}),
        result=>{s.outcomes=[result];render();}, {path:base+'/compose',enabled:scope && !!s.preview && !!consent}));
      for (const row of s.rows) {
        const card = node('div');card.className='experiment-candidate';
        card.append(node('h4',tr('proposal')+' '+row.ordinal));
        if(row.ordinal===3 && s.immutable.multiple_tests===2) card.append(node('p',tr('draft_unevaluated')));
        facts(card,'semantic_receipts',row.receipts.length); card.append(node('p',tr('semantic_pending')));
        card.append(button(tr('review'),'experiment-review-'+row.candidate_id,()=>{if(alive() && !s.busy) return review(row.candidate_id);}));
        card.append(action('semantic_review','semantic-review-'+row.candidate_id,
          ()=>({...generation(),candidate_id:row.candidate_id}),null,{path:base+'/semantic-review',enabled:live() && row.receipts.length===0
            && !s.operations.some(op=>op.kind==='semantic' && op.candidate_id===row.candidate_id)}));
        card.append(action('semantic_evidence','semantic-evidence-'+row.candidate_id,
          ()=>({...generation(),candidate_id:row.candidate_id}),showEvidence,{path:base+'/semantic-evidence',enabled:active(),refresh:false}));
        if(row.edit_authority?.status==='active') card.append(action('bind_candidate','bind-'+row.candidate_id,
          ()=>({...generation(),candidate_id:row.candidate_id,authority_id:row.edit_authority.authority_id}),null,
          {path:base+'/bind',enabled:active() && ['proposed','proposing','probing','comparing'].includes(s.experiment.phase)
            && row.ordinal<=s.immutable.multiple_tests}));
        content.append(card);
      }
      comparisonControls();
    }
    function comparisonControls() {
      const controls=node('details');controls.append(node('summary',tr('comparison_controls')));info(controls,'comparison_hint');content.append(controls);
      if(s.capabilities?.trial !== true) controls.append(node('p',tr('trial_unavailable')));
      const ordinals=s.rows.filter(x=>x.ordinal<=s.immutable.multiple_tests).map(x=>[String(x.ordinal),'proposal']);
      if(ordinals.length) {
        const ordinal=field(controls,'proposal','comparison-ordinal',ordinals);
        controls.append(action('select_candidate','select-candidate',()=>({...generation(),choice:'candidate',ordinal:Number(ordinal.value)}),
          null,{path:base+'/select',enabled:live()}));
        for(const kind of ['tuning','final']) controls.append(action('freeze_'+kind,'freeze-'+kind,
          ()=>({...generation(),ordinal:Number(ordinal.value),kind}),result=>{s.comparison=result.comparison_id;}, {path:base+'/freeze',enabled:active()}));
      }
      controls.append(action('select_keep_base','select-keep-base',()=>({...generation(),choice:'keep_base',ordinal:null}),
        null,{path:base+'/select',enabled:active() && !['completed','cancelled','rejected','inconclusive','stale','stopping'].includes(s.experiment.phase)}));
      const comparison=field(controls,'comparison_ref','comparison-ref'); comparison.value=s.comparison || '';
      for(const [name,label] of [['view-freeze','freeze_view'],['view-evidence','view_evidence'],['next','run_trial'],['report','publish_report']]) {
        controls.append(action(label,name,()=>{
          if(!id(comparison.value)) throw {status:400};return {...generation(),comparison_id:comparison.value};
        },result=>{
          if(result.report_id)s.report=result.report_id;
          if(name==='view-evidence') showEvidence(result);
        },{enabled:active() && (name!=='next' || s.capabilities?.trial===true),refresh:name!=='view-evidence'}));
      }
      const report=field(controls,'report_ref','report-ref');report.value=s.report || '';
      const readReport=button(tr('read_report'),'read-report',async()=>{
        if(!alive() || s.busy || readReport.disabled) return;
        readReport.disabled=true;
        try {
          if(!id(report.value))throw {status:400};
          const value=(await request('/improvement-comparison-reports/'+encodeURIComponent(report.value))).report;
          if(value.experiment_id!==context.experiment_id)throw {status:403};
          showReport(value); // Incomplete/unknown/loss stays exact data.
          try {
            const pilot=(await request('/improvement-pilot-reports/'+encodeURIComponent(report.value))).pilot;
            facts(evidence,'pilot_conclusion',tr('conclusion_'+pilot.conclusion));
            if(pilot.win_rate_interval)facts(evidence,'win_rate_interval',pilot.win_rate_interval.join(' - '));
          } catch(_) { /* The plain report above stays the evidence when the conclusion is unavailable. */ }
        } catch(error){failure(error);}
        finally {if(alive())readReport.disabled=false;}
      });controls.append(readReport);
    }
    async function load() {
      const loadVersion=++s.loadVersion, acknowledged=[...s.acknowledged];
      try {
        evidence.replaceChildren();
        const policy = await request('/improvement-policy');
        let currentContext;
        try { currentContext=(await request('/improvement-contexts/'+encodeURIComponent(context.experiment_id))).context; }
        catch(error) { if(error.status!==403)throw error; currentContext=null; }
        let experiment;
        try { experiment=(await request(base)).experiment; }
        catch(error) { if(error.status!==403)throw error; experiment=null; }
        let immutable=null, consents=[], outcomes=[], operations=[], rows=[];
        if(experiment) {
          immutable=(await request(base+'/policy')).policy;
          consents=(await request(base+'/compose-consents')).consents;
          outcomes=(await request(base+'/compose-outcomes')).outcomes;
          operations=(await request(base+'/operations')).operations;
          rows=(await request('/improvement-candidates?experiment_id='+encodeURIComponent(context.experiment_id))).candidates;
          for(const row of rows) row.receipts=(await request('/improvement-candidates/'+encodeURIComponent(row.candidate_id)+'/semantic-history')).receipts;
        }
        if(!alive() || loadVersion!==s.loadVersion)return;
        if(rows.length>3 || consents.length>100 || outcomes.length>1 || operations.length>6)throw Error('bounded_metadata_required');
        if(s.preview && s.preview.generation!==experiment?.generation)s.preview=null;
        s.policy=policy.policy;s.capabilities=policy.capabilities;s.context=currentContext;s.experiment=experiment;s.immutable=immutable;
        s.consents=consents;s.outcomes=outcomes;s.operations=operations;s.rows=rows;
        // Resolve only acknowledgments covered when this latest snapshot began.
        // Uncertain intents are separate and remain exact, never replayed here.
        for(const name of acknowledged)s.acknowledged.delete(name);
        render();status.textContent=tr('metadata_loaded');
      } catch(error) {
        if(!alive() || loadVersion!==s.loadVersion)return;
        throw error;
      }
    }
    const ready=load().catch(failure);
    return {ready,dispose};
  }
  window.JavisImprovementExperiments={mount};
})();
