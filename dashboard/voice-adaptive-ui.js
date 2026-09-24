/* Adapter to the app. DOM work lives here; decisions remain in the pure controller. */
(function(root) {
  'use strict';
  root.JavisAdaptiveUI = function(d) {
    const controller = new root.JavisVoiceAdaptive.Controller();
    let mode=localStorage.getItem('javis.adaptive')||'off', prefix='', lastState='', active=false;
    const configured=()=>mode!=='off' && d.browserMode();
    const enabled=()=>configured() && mode==='natural' && d.capable();
    const running=()=>enabled() && d.handsFree();
    const liveDraft=()=>['DRAFT','HOLD','READY'].includes(controller.state);
    function paint() {
      if(!running() && controller.state!=='SAVED_DRAFT') return;
      if(controller.text && controller.state!=='COMMITTED') d.draft(controller.text);
      const el=document.getElementById('adaptiveDraftControls');
      if(!el) return;
      el.hidden=!controller.text || controller.state==='COMMITTED';
      el.querySelector('[data-status]').textContent=root.t('app.adaptive_'+(controller.state==='SAVED_DRAFT'?'saved':controller.state==='READY'?'ready':controller.state==='HOLD'?'hold':'listen'));
      el.querySelector('[data-resume]').hidden=controller.state!=='SAVED_DRAFT';
      el.querySelector('[data-resume]').disabled=controller.text.length>=4000;
      if(lastState!==controller.state) { lastState=controller.state; d.state(liveDraft()); }
    }
    function actions(list, manual=false) {
      list.forEach(a=>{
        if(mode==='observe') return;
        if(a.type==='commit') {
          if(!manual && !d.accept(a.text)) { actions(controller.save('attention_expired',true)); return; }
          const text=a.text; prefix='';
          d.cancelCapture(); d.state(false); d.send(text);
        } else if(a.type==='cancel') {
          d.stop(); d.cancelCapture(); prefix=''; controller.reset(); d.draft('');
        } else if(a.type==='save_draft') {
          d.cancelCapture(); d.expireAttention(); d.state(false);
        }
      });
      paint();
    }
    function input(text) {
      if(!configured()) return false;
      if(!text) return running();
      if(controller.state==='SAVED_DRAFT') return running(); // wake is accepted only on final
      const full=prefix?root.JavisVoice.ghepDuoiTam(prefix,text):text;
      if(running() && full!==controller.text) d.interrupt();
      actions(controller.update(full,{learn:!document.hidden && d.connected() && !d.speaking()}));
      return running();
    }
    function save(reason) { if(running()) actions(controller.save(reason)); }
    function cancel(preserve=true) {
      if(preserve && controller.text && controller.state!=='COMMITTED' && d.preserve) d.preserve(controller.text);
      active=false; prefix=''; controller.reset(); d.managed(false);
      const el=document.getElementById('adaptiveDraftControls'); if(el) el.hidden=true;
    }
    function resume() {
      if(controller.state!=='SAVED_DRAFT') return;
      prefix=controller.text;
      actions(controller.resume());
      if(controller.state!=='SAVED_DRAFT') { d.openAttention(); d.listen(); }
    }
    const box=document.createElement('div'); box.id='adaptiveDraftControls'; box.className='adaptive-draft-controls'; box.hidden=true;
    const status=document.createElement('span'); status.dataset.status=''; status.setAttribute('role','status'); box.appendChild(status);
    [['send',()=>actions(controller.submit(),true)],['resume',resume],['discard',()=>{d.cancelCapture();cancel(false);d.draft('');}]].forEach(([key,fn])=>{
      const b=document.createElement('button'); b.type='button'; b.dataset[key]=''; b.className='js-btn'; b.textContent=root.t('app.adaptive_'+key); b.onclick=fn; box.appendChild(b);
    });
    document.getElementById('chatArea').after(box);
    const select=document.getElementById('adaptiveMode');
    select.value=['off','observe','natural'].includes(mode)?mode:'off'; mode=select.value;
    select.onchange=()=>{d.cancelCapture();cancel();mode=select.value;localStorage.setItem('javis.adaptive',mode);d.draft('');};
    const pace=document.getElementById('adaptivePace'); pace.value=localStorage.getItem('javis.adaptivePace')||'balanced';
    controller.pace=pace.value||'balanced';
    pace.onchange=()=>{controller.pace=pace.value;localStorage.setItem('javis.adaptivePace',pace.value);controller.resetLearning();};
    document.getElementById('adaptiveReset').onclick=()=>controller.resetLearning();
    document.getElementById('adaptiveExport').onclick=()=>{
      const url=URL.createObjectURL(new Blob([JSON.stringify({version:1,mode,events:controller.diagnostics()},null,2)],{type:'application/json'}));
      const a=document.createElement('a');a.href=url;a.download='javis-voice-diagnostics.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
    document.addEventListener('visibilitychange',()=>{if(document.hidden)save('hidden');});
    setInterval(()=>{
      if(mode==='observe' && d.handsFree() && d.browserMode()) { controller.tick(); return; }
      const on=running(); d.managed(on);
      if(!on) {active=false;return;}
      if(document.hidden) {save('hidden');return;}
      if(!active) {active=true;controller.resetLearning();}
      if(liveDraft()) {d.keepAttention(); actions(controller.tick());}
      paint();
    },100);
    return {input,save,cancel,resume,running,enabled,controller,
      blocked:()=>running()&&controller.state==='SAVED_DRAFT',
      holding:()=>running()&&liveDraft(),
      manual:text=>{
        if(mode==='observe'){controller.reset();return false;}
        if(!running())return false;
        if(controller.state==='SAVED_DRAFT') {
          if(/^(?:javis|jarvis)(?:\s|[,!?]|$)/i.test(text.trim())) {
            const addition=text.trim().replace(/^(?:javis|jarvis)(?:\s+ơi)?[\s,!?]*/i,'');
            resume();
            if(addition) input(addition);
          }
          return true;
        }
        input(text);actions(controller.submit(),true);return true;
      },
      start:()=>{d.managed(running());if(running())paint();},
      canListen:()=>!document.hidden};
  };
})(window);
