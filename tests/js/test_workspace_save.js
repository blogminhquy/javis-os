const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '../../dashboard/workspace.js'), 'utf8');
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
 console.log('OK save retries unavailable session, collapses settings responsively, preserves newer selection');
})().catch(e=>{console.error(e);process.exit(1);});
