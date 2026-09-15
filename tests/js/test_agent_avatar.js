const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const root = path.join(__dirname,'../..');
const pet = fs.readFileSync(path.join(root,'dashboard/pet.js'),'utf8');
// Lấy catalog THẬT để phát hiện khi thư viện pet đổi hình hay màu.
const catalog = pet.slice(pet.indexOf('  var SHAPES ='), pet.indexOf('  // Cỡ pet.'));
const ctx={window:{addEventListener(){}},document:{addEventListener(){}}};
vm.createContext(ctx);vm.runInContext(catalog,ctx);
ctx.window.JavisPet={shapes:()=>ctx.SHAPES,palettes:()=>ctx.PALETTES,previewSvg:()=>'<svg><path/><ellipse/><ellipse/></svg>'};
vm.runInContext(fs.readFileSync(path.join(root,'dashboard/agent-avatar.js'),'utf8'),ctx);
const A=ctx.window.JavisAvatar;
const saved={shape:'pentagon',palette:'pink'};
assert.equal(JSON.stringify(A.of({avatar:saved})),JSON.stringify(saved));
assert.equal(JSON.stringify(A.of({slug:'legacy'})),JSON.stringify(A.of({slug:'legacy'})));
for(let i=0;i<40;i++){const a=A.random();assert(Object.hasOwn(ctx.SHAPES,a.shape));assert(Object.hasOwn(ctx.PALETTES,a.palette));}
const invalid=A.of({slug:'legacy',avatar:{shape:'__proto__',palette:'<script>'}});
assert(Object.hasOwn(ctx.SHAPES,invalid.shape));assert(Object.hasOwn(ctx.PALETTES,invalid.palette));
const html=A.html({avatar:saved},26,'thinking');
assert(html.includes('data-shape="pentagon"') && html.includes('data-state="thinking"'));
assert.equal((html.match(/<g\b/g)||[]).length,(html.match(/<\/g>/g)||[]).length);
assert(html.includes('aa-eyes') && html.includes('aa-gaze'));
console.log('OK - saved identity, stable legacy avatar, random library choices, safe SVG animation');
