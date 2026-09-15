/* Đường LƯU của trang Cộng sự: mở lại phiên sau khi lưu, danh sách rỗng thì khoá chat,
   và lưu hỏng phải nói ra chứ không giả vờ xong.

       node tests/js/test_workspace_save.js */
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const root = path.join(__dirname, '../..');
const src = fs.readFileSync(path.join(root, 'dashboard/workspace.js'), 'utf8');
const code = src.slice(src.indexOf('  function thuGonCaiDat('), src.indexOf('  // ---------- cột phải'));
(async () => {
 for (const narrow of [true, false]) {
  let collapsed, focused = 0, opens = 0, success = true;
  const ctx = {active:true,ready:false,S:{loai:'agent',chon:{agent:'a'},el:{querySelector:()=>({classList:{toggle:(name,value)=>{collapsed=value;}}})}},
   taiDanhSach:async()=>{}, veTrai(){}, veGiua(){}, dangChon:()=>({slug:'a'}),
   moPhien:async()=>{opens++;return success;},
   window:{matchMedia:()=>({matches:narrow})}, document:{getElementById:()=>({focus:()=>focused++})}};
  vm.createContext(ctx); vm.runInContext(code,ctx);
  await ctx.sauLuu({slug:'a'},'agent');
  assert.equal(opens,1); assert.equal(focused,1); assert.equal(collapsed,!narrow);
  success=false; await ctx.sauLuu({slug:'a'},'agent'); assert.equal(focused,1);
  ctx.S.chon.agent='b'; await ctx.sauLuu({slug:'a'},'agent'); assert.equal(opens,2);
 }

 // ---- Danh sách RỖNG (brain mới, tab Quy trình chưa có gì): ô nhập phải KHOÁ và nói vì sao.
 // Để nó sáng thì người dùng gõ xong bấm gửi mà canSend() trả false: không có gì xảy ra, và
 // cũng không có câu nào giải thích.
 {
  const phan = src.slice(src.indexOf('  function chonMacDinh('), src.indexOf('  // ---------- phiên ----------'))
             + src.slice(src.indexOf('  function veGiua('), src.indexOf('  function thuGonCaiDat('));
  let ds = [], opens = 0;
  const o = {disabled:false, placeholder:'cũ'}, iden = {innerHTML:''};
  const ctx = {
   danhSach:()=>ds, veDanhSach(){}, vePhai(){}, moPhien:async()=>{opens++;return true;},
   chatReady(v){ o.disabled = !v; }, esc:s=>String(s), t:k=>k, avatar:()=>'', ic:()=>'',
   S:{loai:'agent', chon:{agent:null}, el:{querySelector:sel=>sel==='#wsIdentity'?iden:null}},
   dangChon:()=>ds[0]||null, cacBuoc:()=>[],
   document:{getElementById:()=>o}};
  vm.createContext(ctx); vm.runInContext(phan, ctx);
  ctx.chonMacDinh();
  assert.equal(o.disabled, true, 'empty list must disable the chat box');
  assert.equal(opens, 0);
  assert.ok(iden.innerHTML.includes('ws.none_yet'), 'empty list explains itself');
  assert.equal(o.placeholder, 'ws.none_yet');
  ds = [{slug:'a', name:'X'}];
  await ctx.chonMacDinh();
  assert.equal(opens, 1, 'a non-empty list still opens the first session');
 }

 // ---- studio.js: lưu quy trình phải hành xử y như lưu trợ lý ----
 const studio = fs.readFileSync(path.join(root, 'dashboard/studio.js'), 'utf8');
 const saveWf = studio.slice(studio.indexOf('box.querySelector("#saveWf").onclick'),
                             studio.indexOf('    function captureSteps()'));
 assert.ok(/nutLuu\.disabled = true/.test(saveWf), 'saving must lock the button');
 assert.ok(/if \(!saved\.ok\)/.test(saveWf), 'a failed save must not look like a success');
 assert.ok(/alert\(loiLuu\(saved\.error\)\)/.test(saveWf), 'server codes go through the dictionary');
 assert.ok(/catch \(err\) \{ alert\(t\("ws\.save_failed"\)\)/.test(saveWf), 'a thrown save must be reported');
 assert.ok(/tuyChon\.onSaved\(saved\)/.test(saveWf), 'onSaved needs the response to select the new workflow');
 assert.ok(saveWf.indexOf('editor.classList.remove("open")') > saveWf.indexOf('if (!saved.ok)'),
   'the editor closes only after the save is confirmed');
 // Mã máy của server ("avatar_shape") KHÔNG được rơi thẳng vào alert.
 assert.ok(!/alert\(saved\.error \|\|/.test(studio), 'no raw server token in an alert');
 const bang = studio.slice(studio.indexOf('  const _MA_LOI_LUU'), studio.indexOf('  // Bỏ dấu để gõ'));
 const cd = {t:k=>k};
 vm.createContext(cd);
 // `const` trong vm là biến lexical, không thành thuộc tính của context - phải tự phơi ra.
 vm.runInContext(bang + '\nglobalThis.loiLuu = loiLuu;', cd);
 assert.equal(cd.loiLuu('avatar_shape'), 'ws.err_avatar_shape');
 assert.equal(cd.loiLuu('avatar_palette'), 'ws.err_avatar_palette');
 for (const la of ['', undefined, null, 'boom', '__proto__', 'toString'])
   assert.equal(cd.loiLuu(la), 'ws.save_failed', 'unknown codes fall back to the generic line');
 // Từ điển phải có đủ cả hai thứ tiếng, không thì người dùng đọc trơ tên key.
 for (const f of ['vi', 'en']) {
   const tu = JSON.parse(fs.readFileSync(path.join(root, 'dashboard/i18n/' + f + '.json'), 'utf8'));
   for (const k of ['ws.none_yet', 'ws.err_avatar_shape', 'ws.err_avatar_palette', 'qs.tts_can_mic'])
     assert.ok(tu[k], f + ' thiếu key ' + k);
 }
 console.log('OK save retries unavailable session, locks chat when empty, workflow save reports failures');
})().catch(e=>{console.error(e);process.exit(1);});
