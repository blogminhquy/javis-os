const assert=require('node:assert/strict'), fs=require('fs'), vm=require('vm');
const {Controller}=require('../../dashboard/voice-adaptive.js');
function setup(mode='natural') {
  let now=0, interval, accept=true, connected=true, sends=[], cancelled=0;
  const els=new Map(), listeners={};
  class El {
    constructor(){this.dataset={};this.children=[];this.hidden=false;this.value='';}
    appendChild(e){this.children.push(e);return e;} after(e){els.set(e.id,e);} setAttribute(){}
    querySelector(sel){const key=sel.slice(6,-1);return this.children.find(e=>key in e.dataset);}
  }
  const document={hidden:false,createElement:()=>new El(),getElementById:id=>{if(!els.has(id))els.set(id,new El());return els.get(id);},addEventListener:(name,fn)=>{listeners[name]=fn;}};
  const window={JavisVoiceAdaptive:{Controller:class extends Controller{constructor(){super({now:()=>now});}}},JavisVoice:{ghepDuoiTam:(a,b)=>a+' '+b},t:k=>k};
  const ctx={window,document,localStorage:{getItem:k=>k==='javis.adaptive'?mode:null,setItem(){}},setInterval:fn=>interval=fn,setTimeout(){}};
  vm.runInNewContext(fs.readFileSync('dashboard/voice-adaptive-ui.js','utf8'),ctx);
  const ui=window.JavisAdaptiveUI({browserMode:()=>true,capable:()=>true,handsFree:()=>true,connected:()=>connected,speaking:()=>false,managed(){},cancelCapture(){cancelled++;},draft(){},state(){},stop(){},interrupt(){},accept:()=>accept,expireAttention:()=>{accept=false;},keepAttention(){},openAttention:()=>{accept=true;},listen(){},send:t=>sends.push(t)});
  return {ui,sends,els,document,listeners,tick:t=>{now=t;interval();},setAccept:a=>accept=a};
}
let s=setup();s.tick(0);s.ui.input('Ý là');s.tick(4000);assert.equal(s.sends.length,0);s.tick(10000);
assert.equal(s.ui.controller.state,'SAVED_DRAFT');
s.els.get('adaptiveDraftControls').querySelector('[data-send]').onclick();
assert.deepEqual(s.sends,['Ý là'],'manual send must retain accepted draft after attention expires');
s=setup();s.tick(0);s.ui.input('Mở khung chat');s.document.hidden=true;s.listeners.visibilitychange();s.tick(90000);
assert.equal(s.sends.length,0);assert.equal(s.ui.controller.text,'Mở khung chat');
s=setup('observe');s.tick(0);s.ui.input('Mở khung chat');s.tick(1400);
assert.equal(s.sends.length,0);assert.equal(s.ui.controller.state,'COMMITTED');
s=setup();s.tick(0);s.ui.input('Ý là');s.tick(10000);
s.ui.manual('Javis, anh muốn mở chat');
assert.equal(s.ui.controller.text,'Ý là anh muốn mở chat','wake continuation retains the accepted words');
s=setup();s.tick(0);s.ui.input('Mở chat');s.document.hidden=true;s.listeners.visibilitychange();s.document.hidden=false;
s.ui.resume();s.tick(2000);assert.equal(s.sends.length,0,'Continue alone must not auto-send a stale saved command');
console.log('adaptive UI lifecycle passed');
