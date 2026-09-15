/* Hành vi mở phiên/chạy workflow, không gửi nhầm khi phản hồi mạng về sai thứ tự. */
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const root = path.join(__dirname, '../..');
const source = fs.readFileSync(path.join(root, 'dashboard/workspace.js'), 'utf8');
const section = source.slice(source.indexOf('  async function moPhien('), source.indexOf('  function veLoi('));
const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return {promise,resolve}; };

(async () => {
  let selected = {slug:'a'}, current = null, sent = [], errors = [], requests = [];
  const input = {value:'  Viết nội dung mới  '};
  let progress = {trang_thai:'cho'};
  const ctx = {
    opening:0, ready:false, active:true, S:{loai:'workflow',sessionCuaPhien:{}},
    chatReady(v) { ctx.ready=v; }, veGiua(){}, vePhai(){}, veBuoc(){}, toMoiLichSu(){},
    brain:()=> 'test', kenh:x=>'workflow:'+x.slug, fd:x=>x, t:k=>k,
    conDangXem:x=>x.slug===selected.slug, dangChon:()=>selected,
    tienDoHienTai:()=>progress, veLoi:e=>errors.push(e),
    document:{getElementById:()=>input},
    api:()=>{ const d=deferred(); requests.push(d); return d.promise; },
    window:{JavisSessions:{current:()=>current,open:async(id,valid)=>{if(valid())current=id;},new:()=>{current=null;}},JavisSend:text=>sent.push(text)}
  };
  vm.createContext(ctx); vm.runInContext(section,ctx);
  const first=ctx.moPhien(selected,false);
  selected={slug:'b'};
  const second=ctx.moPhien(selected,false);
  assert.equal(ctx.ready,false);
  await ctx.chayQuyTrinh(); assert.equal(sent.length,0);
  requests[1].resolve({sessions:[{id:'session-b'}]}); await second;
  requests[0].resolve({sessions:[{id:'session-a'}]}); await first;
  assert.equal(current,'session-b'); assert.equal(ctx.ready,true);
  await ctx.chayQuyTrinh(); assert.deepEqual(sent,['Viết nội dung mới']);
  input.value=''; await ctx.chayQuyTrinh(); assert.equal(sent[1],'ws.run_default');
  progress={trang_thai:'dang'}; await ctx.chayQuyTrinh(); assert.equal(sent.length,2);
  progress={trang_thai:'cho',cho_duyet:{code:'AB'}}; await ctx.chayQuyTrinh(); assert.equal(sent.length,2);
  const failed=ctx.moPhien(selected,true); requests[2].resolve({error:'Cannot create session'}); await failed;
  assert.equal(current,null); assert.equal(ctx.ready,false); assert.equal(errors.length,1);
  // Câu lỗi THÔ của server không được rơi ra màn hình. Chủ repo đã thấy nguyên câu
  // "channel phải là agent:<slug> hoặc workflow:<slug>" nằm giữa trang Cộng sự: nó nói về
  // khuôn dữ liệu bên trong, không nói người dùng phải làm gì, và không đi qua từ điển nên
  // bản tiếng Anh vẫn ra tiếng Việt. Màn hình dùng khoá i18n, chữ của server để cho nhật ký.
  assert.equal(errors[0],'ws.err_session','màn hình phải dùng khoá i18n');
  assert.ok(!String(errors[0]).includes('Cannot create session'),'không rò chữ của server ra màn hình');
  const nguon = fs.readFileSync(path.join(root, 'dashboard/workspace.js'), 'utf8');
  assert.ok(!/veLoi\(e\.message/.test(nguon),'CANARY: không hiện message của lỗi ném ra');
  assert.ok(!/new Error\(n\.error/.test(nguon),'CANARY: không bọc chữ server thành thông báo');
  await ctx.chayQuyTrinh(); assert.equal(sent.length,2);
  console.log('OK - latest session wins, loading/failure cannot send, workflow draft/default/busy guards');
})().catch(e=>{console.error(e);process.exit(1);});
