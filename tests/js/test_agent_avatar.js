/* Avatar trợ lý (dashboard/agent-avatar.js): nhân dạng ổn định, dựng SVG an toàn, và vẽ lại
   được khi đổi chủ đề dù dữ liệu trên DOM có lạ.

       node tests/js/test_agent_avatar.js */
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const root = path.join(__dirname,'../..');
const pet = fs.readFileSync(path.join(root,'dashboard/pet.js'),'utf8');
// Lấy catalog THẬT để phát hiện khi thư viện pet đổi hình hay màu.
const catalog = pet.slice(pet.indexOf('  var SHAPES ='), pet.indexOf('  // Cỡ pet.'));
const nghe = {};
const dom = {'.agent-avatar':[], '.aa-colors [data-palette]':[]};
const ctx={window:{addEventListener(n,f){nghe[n]=f;}},
  document:{addEventListener(){}, querySelectorAll:(sel)=>dom[sel]||[]}};
vm.createContext(ctx);vm.runInContext(catalog,ctx);
// toneOf trả NULL khi tên bảng màu lạ - đúng như dashboard/pet.js.
ctx.window.JavisPet={shapes:()=>ctx.SHAPES,palettes:()=>ctx.PALETTES,
  previewSvg:()=>'<svg><path/><ellipse/><ellipse/></svg>',
  toneOf:(p)=>ctx.PALETTES[p]?['#112233','#445566']:null};
const nguon = fs.readFileSync(path.join(root,'dashboard/agent-avatar.js'),'utf8');
vm.runInContext(nguon,ctx);
const A=ctx.window.JavisAvatar;
const saved={shape:'pentagon',palette:'pink'};
assert.equal(JSON.stringify(A.of({avatar:saved})),JSON.stringify(saved));
assert.equal(JSON.stringify(A.of({slug:'legacy'})),JSON.stringify(A.of({slug:'legacy'})));
const co=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
for(let i=0;i<40;i++){const a=A.random();assert(co(ctx.SHAPES,a.shape));assert(co(ctx.PALETTES,a.palette));}
const invalid=A.of({slug:'legacy',avatar:{shape:'__proto__',palette:'<script>'}});
assert(co(ctx.SHAPES,invalid.shape));assert(co(ctx.PALETTES,invalid.palette));
const html=A.html({avatar:saved},26,'thinking');
assert(html.includes('data-shape="pentagon"') && html.includes('data-state="thinking"'));
assert.equal((html.match(/<g\b/g)||[]).length,(html.match(/<\/g>/g)||[]).length);
assert(html.includes('aa-eyes') && html.includes('aa-gaze'));

// html() là hàm CÔNG KHAI: chỗ gọi khác có thể ném thẳng chuỗi lạ vào, nên hai thuộc tính
// data-* phải đi qua esc() chứ không nối trần.
assert(/data-shape="' \+ esc\(a\.shape\)/.test(nguon), 'data-shape phải escape');
assert(/data-palette="' \+ esc\(a\.palette\)/.test(nguon), 'data-palette phải escape');
// Object.hasOwn cần Safari 15.4+; repo này còn đỡ iPhone cũ nên không được dùng.
assert(!/Object\.hasOwn\b/.test(nguon), 'không dùng Object.hasOwn trong dashboard');

// Đổi chủ đề: một `data-palette` lạc (brain cũ, người dùng sửa DOM) không được giết cả vòng
// vẽ lại - toneOf trả null thì [0] là TypeError và các avatar còn lại đứng nguyên màu cũ.
const ve=[], swatch=[];
dom['.agent-avatar']=[{dataset:{shape:'circle',palette:'amber'},set innerHTML(v){ve.push(v);}},
                     {dataset:{shape:'la',palette:'khong-co'},set innerHTML(v){ve.push(v);}},
                     {dataset:{shape:'square',palette:'jade'},set innerHTML(v){ve.push(v);}}];
dom['.aa-colors [data-palette]']=[{dataset:{palette:'khong-co'},style:{setProperty:(k,v)=>swatch.push(v)}},
                                  {dataset:{palette:'jade'},style:{setProperty:(k,v)=>swatch.push(v)}}];
assert.doesNotThrow(()=>nghe['javis-theme-change']({}), 'bảng màu lạ không được ném');
assert.equal(ve.length,3,'mọi avatar đều được vẽ lại');
assert.equal(swatch.length,2);
assert.equal(swatch[0],'transparent','bảng màu lạ rơi về màu trong suốt');
assert.equal(swatch[1],'#112233');
console.log('OK - saved identity, stable legacy avatar, escaped markup, theme redraw survives a stray palette');
