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

// ============================================================
// Chớp mắt LỆCH PHA giữa các trợ lý (0.59.4)
// ============================================================
// Trước đây mọi avatar dùng chung `animation: aa-blink 6s` nên cả danh sách chớp mắt đồng
// loạt - nhìn ra ngay là mấy bản sao của một cái máy (chủ dự án báo 15/09).
{
  const nhip = (slug) => {
    const h = A.html({slug}, 40);
    return [/--aa-blink-delay:(-?[\d.]+)s/.exec(h)[1], /--aa-blink-dur:([\d.]+)s/.exec(h)[1]].join("|");
  };
  const ds = ['viet-bai','ke-toan','chay-ads','tro-ly-zalo','bien-tap'].map(nhip);
  assert.equal(new Set(ds).size, ds.length, 'mỗi trợ lý phải có một nhịp chớp mắt riêng');
  // ...nhưng ỔN ĐỊNH: cùng một trợ lý vẽ ở hai chỗ (hàng danh sách + đầu khung chat) phải
  // chớp cùng nhịp, và vẽ lại danh sách không được đổi nhịp của ai.
  assert.equal(nhip('viet-bai'), nhip('viet-bai'), 'cùng slug thì cùng nhịp, không random mỗi lần vẽ');
  const tre = ds.map(x => +x.split("|")[0]), lau = ds.map(x => +x.split("|")[1]);
  assert(tre.every(v => v <= 0 && v > -7), 'trễ phải ÂM (bắt đầu giữa chu kỳ) và trong một vòng');
  assert(lau.every(v => v >= 5 && v <= 8.5), 'chu kỳ chớp mắt giữ trong khoảng người thật');
}

// ============================================================
// Hướng liếc của ô xem thử lớn trong cài đặt trợ lý (0.59.4)
// ============================================================
// Chủ dự án chốt: ô đó liếc sang TRÁI và hơi XUỐNG, khác dáng chữ ký chéo lên phải.
{
  const goi = [];
  ctx.window.JavisPet.previewSvg = (s, p, o) => { goi.push(o || {}); return '<svg><path/><ellipse/><ellipse/></svg>'; };
  A.html({slug:'x'}, 40);
  assert.deepEqual(goi.pop(), {}, 'avatar thường giữ nguyên dáng liếc mặc định');
  A.html({slug:'x'}, 100, 'idle', {liec:'trai_duoi'});
  const o = goi.pop();
  assert(o.liecX < 0, 'liếc sang TRÁI');
  assert(o.liecY > 0, 'và hơi XUỐNG dưới');
  assert(/html\(\{avatar:value\}, 100, "idle", \{liec:"trai_duoi"\}\)/.test(nguon),
    'ô xem thử trong picker phải truyền hướng liếc đó');
  // Tâm co của nhịp chớp mắt phải đi theo mắt, không thì mắt vừa nhắm vừa trượt đi.
  const h = A.html({slug:'x'}, 100, 'idle', {liec:'trai_duoi'});
  assert(/--aa-eye-x:144px/.test(h) && /--aa-eye-y:169px/.test(h), 'tâm chớp mắt đi theo mắt');
}
// ============================================================
// 0.64.39: avatar dùng CHUNG bộ chỉnh với linh vật
// ============================================================
{
  // Ngẫu nhiên: hình + bảng màu CÓ SẴN + mắt trắng hoặc đen (chủ dự án chốt 24/09).
  const cu = ctx.window.JavisPet.toneOf;
  ctx.window.JavisPet.toneOf = () => ['#c0703a'];   // thân tầm trung: trắng hay đen đều đọc được
  const mat = new Set();
  for (let i = 0; i < 80; i++) { const a = A.random(); mat.add(a.eye); assert(co(ctx.PALETTES, a.palette), 'không bốc màu tự chọn'); }
  assert.deepEqual([...mat].sort(), ['den', 'trang'], 'mắt ngẫu nhiên phải ra cả trắng lẫn đen, và chỉ hai màu đó');
  // Thân rất sáng thì không bao giờ bốc mắt trắng (mất mặt).
  ctx.window.JavisPet.toneOf = () => ['#fafafa'];
  for (let i = 0; i < 40; i++) assert.equal(A.random().eye, 'den', 'thân sáng thì mắt đen');
  ctx.window.JavisPet.toneOf = cu;
  // Màu tự chọn + mắt tự chọn + cỡ mắt đi qua of() và ra đúng trường form.
  const v = A.of({avatar:{shape:'star',palette:'custom',color:'#FA4F05',eye:'custom',eyeColor:'#2A62B0',eyeSize:1.3}});
  assert.equal(JSON.stringify(v), JSON.stringify({shape:'star',palette:'custom',color:'#fa4f05',eye:'custom',eyeColor:'#2a62b0',eyeSize:1.3}));
  assert.deepEqual(A.formFields(v), {avatar_shape:'star',avatar_palette:'custom',avatar_eye_size:'1.3',
    avatar_color:'#fa4f05',avatar_eye:'custom',avatar_eye_color:'#2a62b0'});
  // Mã rác trong frontmatter không lọt: "custom" mất mã thì về bảng màu theo slug.
  const hong = A.of({slug:'legacy',avatar:{palette:'custom',color:'"><script>',eye:'custom'}});
  assert(co(ctx.PALETTES, hong.palette) && !hong.color && !hong.eye);
  // html() mang theo màu mắt và mã màu để lúc đổi chủ đề vẽ lại đúng.
  const h = A.html({avatar:v}, 40);
  assert(/data-color="#fa4f05"/.test(h) && /data-eye="custom"/.test(h) && /data-eye-color="#2a62b0"/.test(h) && /data-eye-size="1.3"/.test(h));
  // Picker dùng đúng bộ chỉnh của linh vật, không dựng bản riêng.
  assert(/P\.editorHtml\(value, \{\}\)/.test(nguon) && /P\.editorBind\(host\.querySelector\('\.aa-editor'\)/.test(nguon),
    'cài đặt avatar phải dùng bộ chỉnh chung JavisPet.editorHtml/editorBind');
}
console.log('OK - saved identity, stable legacy avatar, escaped markup, theme redraw survives a stray palette, staggered blink, preview gaze');
