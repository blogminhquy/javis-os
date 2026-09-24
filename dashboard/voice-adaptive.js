/* One deadline owner, monotonic clock, session-only learning and metadata diagnostics. */
(function(root) {
  'use strict';
  const policy=typeof module==='object'&&module.exports?require('./voice-turn-policy.js'):root.JavisVoiceTurnPolicy;
  class Controller {
    constructor({now=()=>performance.now(),pace='balanced'}={}) {
      this.now=now; this.pace=pace; this.samples=[]; this.targets={}; this.events=[]; this.epoch=0; this.reset();
    }
    record(reason) {
      this.events.push({at:this.now(),epoch:this.epoch,revision:this.revision,state:this.state,reason,deadline:this.deadline,activity:'unknown'});
      if(this.events.length>200) this.events.shift();
    }
    reset() { this.epoch++; this.text=''; this.state='EMPTY'; this.revision=0; this.started=null; this.last=null; this.deadline=0; this.record('reset'); }
    resetLearning() { this.samples=[]; this.targets={}; this.record('reset_learning'); }
    update(text, {learn=true}={}) {
      text=String(text||'').trim();
      if(this.state==='COMMITTED') this.reset();
      if(!text || text===this.text || this.state==='SAVED_DRAFT') return [];
      const now=this.now();
      if(this.started===null) this.started=now;
      const gap=this.last===null?0:now-this.last;
      if(learn && this.state!=='HOLD' && gap>=300 && gap<=4000 && text.startsWith(this.text) && this.text) {
        this.samples.push(gap); if(this.samples.length>20) this.samples.shift();
      }
      this.text=text; this.last=now; this.revision++; this.group=policy.classify(text);
      if(text.length>=4000 || now-this.started>=120000) return this.save('draft_limit');
      if(this.group==='wait') { this.state='HOLD'; this.deadline=now+90000; this.record('explicit_wait'); return [{type:'hold'}]; }
      if(this.group==='stop') { this.state='COMMITTED'; this.record('stop'); return [{type:'cancel'}]; }
      const target=policy.target(this.group,this.samples,this.pace);
      const old=this.targets[this.group]??policy.target(this.group,[],this.pace);
      this.delay=this.targets[this.group]=old+Math.max(-150,Math.min(150,target-old));
      this.deadline=now+this.delay; this.state='DRAFT'; this.record(this.group); return [];
    }
    tick() {
      if(!['DRAFT','READY','HOLD'].includes(this.state)) return [];
      const now=this.now();
      if(now-this.started>=120000) return this.save('draft_limit');
      if(this.group==='unfinished') {
        if(now-this.last>=10000) return this.save('unfinished_expired');
        if(now-this.last>=4000 && this.state!=='HOLD') { this.state='HOLD'; this.record('unfinished_clause'); return [{type:'hold'}]; }
        return [];
      }
      if(this.group==='wait') return now>=this.deadline?this.save('hold_expired'):[];
      if(now>=this.deadline) return this.submit();
      if(now>=this.deadline-200 && this.state!=='READY') { this.state='READY'; this.record('ready'); return [{type:'ready'}]; }
      return [];
    }
    submit() {
      if(!this.text || this.state==='COMMITTED') return [];
      this.state='COMMITTED'; this.record('commit');
      return [{type:'commit',text:this.text,revision:this.revision,epoch:this.epoch}];
    }
    save(reason='capture_unknown', force=false) {
      if(!this.text || (this.state==='COMMITTED' && !force)) return [];
      this.state='SAVED_DRAFT'; this.record(reason); return [{type:'save_draft',text:this.text,reason}];
    }
    resume() {
      if(this.state!=='SAVED_DRAFT' || this.text.length>=4000) return [];
      this.started=this.now(); this.last=this.now(); this.state='HOLD';
      this.group='wait'; this.deadline=this.now()+90000; this.record('resume');
      return [{type:'hold'}];
    }
    diagnostics() { return this.events.map(e=>({...e})); }
  }
  const api={Controller};
  if(typeof module==='object'&&module.exports) module.exports=api; else root.JavisVoiceAdaptive=api;
})(typeof window!=='undefined'?window:globalThis);
