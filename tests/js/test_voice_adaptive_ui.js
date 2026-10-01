// Nhịp hội thoại thích nghi đã gỡ khỏi giao diện (0.65.19, docs/dev/2026-10-voice-call-spec.md mục 5).
// Bộ chuyển voice-adaptive-ui.js phải: chạy được khi trang KHÔNG còn các ô #adaptiveMode/#adaptivePace/
// #adaptiveReset/#adaptiveExport, và luôn ở chế độ tắt kể cả máy từng lưu 'natural' trong localStorage
// (không còn ô nào để người dùng tự tắt). Tắt nghĩa là: không giành điểm dừng câu, không tự gửi.
const assert=require('node:assert/strict'), fs=require('fs'), vm=require('vm');
const {Controller}=require('../../dashboard/voice-adaptive.js');
const src=fs.readFileSync('dashboard/voice-adaptive-ui.js','utf8');
for (const id of ['adaptiveMode','adaptivePace','adaptiveReset','adaptiveExport'])
  assert.ok(!src.includes(id), `voice-adaptive-ui.js must not read the removed #${id}`);
let now=0, interval, sends=[], managed=[];
const els=new Map(), listeners={};
class El {
  constructor(){this.dataset={};this.children=[];this.hidden=false;this.value='';}
  appendChild(e){this.children.push(e);return e;} after(e){els.set(e.id,e);} setAttribute(){}
  querySelector(sel){const key=sel.slice(6,-1);return this.children.find(e=>key in e.dataset);}
}
// Chỉ khung chat còn tồn tại: id lạ trả null như trang thật.
const document={hidden:false,createElement:()=>new El(),
  getElementById:id=>id==='chatArea'?new El():(els.get(id)||null),
  addEventListener:(name,fn)=>{listeners[name]=fn;}};
const window={JavisVoiceAdaptive:{Controller:class extends Controller{constructor(){super({now:()=>now});}}},JavisVoice:{ghepDuoiTam:(a,b)=>a+' '+b},t:k=>k};
const ctx={window,document,localStorage:{getItem:k=>k==='javis.adaptive'?'natural':null,setItem(){}},setInterval:fn=>interval=fn,setTimeout(){}};
vm.runInNewContext(src,ctx);
const ui=window.JavisAdaptiveUI({browserMode:()=>true,capable:()=>true,handsFree:()=>true,connected:()=>true,speaking:()=>false,
  managed:on=>managed.push(on),cancelCapture(){},draft(){},state(){},stop(){},interrupt(){},accept:()=>true,
  expireAttention(){},keepAttention(){},openAttention(){},listen(){},send:t=>sends.push(t)});
assert.equal(ui.enabled(),false,'a stored "natural" no longer turns the adaptive timing on');
assert.equal(ui.input('Mở khung chat'),false,'browser endpoint keeps the turn');
now=0;interval();now=10000;interval();
assert.deepEqual(sends,[],'nothing is sent by the adaptive layer');
assert.ok(managed.length && managed.every(on=>on===false),'endpoint is never managed by the adaptive layer');
assert.equal(ui.manual('Javis, mở chat'),false,'typed and spoken text go the normal way');
assert.equal(ui.blocked(),false);assert.equal(ui.holding(),false);
console.log('adaptive UI removed from settings, forced off');
