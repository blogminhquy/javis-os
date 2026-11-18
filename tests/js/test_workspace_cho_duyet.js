/* Khung "Đang chờ bạn duyệt" của tab Quy trình: hiện đúng thẻ, Duyệt gửi "ok", Yêu cầu sửa gửi lời sửa,
   không vẽ lại khi đang gõ, và ẩn khi sang tab Cộng sự.

       node tests/js/test_workspace_cho_duyet.js */
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '../../dashboard/workspace.js'), 'utf8');
const code = src.slice(src.indexOf('  // ---------- mốc chờ duyệt'), src.indexOf('  async function taiDanhSach() {'));
assert.ok(code.length > 500, 'không bóc được đoạn chờ duyệt');

const host = { hidden: true, innerHTML: '' };
const sent = [];
let reply = { ok: true };
const ctx = {
  active: true, lanDung: 1, brain: () => 'b',
  S: { loai: 'workflow', choDuyet: [], duyetMo: {}, el: { querySelector: (q) => (q === '#wsApprovals' ? host : null) } },
  esc: (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]),
  t: (k) => k, ic: () => '', fd: (o) => o,
  api: async (url, opt) => { if (opt && opt.method === 'POST') { sent.push(opt.body); return reply; } return { items: ctx.items }; },
  currentBrainPath: () => '/brains/b', veDanhSach() {},
};
ctx.items = [{ id: 'T1', title: 'SKY tập 0', workflow: 'san-xuat-clip-sky', status: 'blocked', can_answer: true,
  question: 'DUYỆT CONTENT <b>', links: [{ path: 'marketing/a/story.md', kind: 'doc' }, { path: 'x/y.png', kind: 'image' }] },
  { id: 'T2', title: 'Việc khác', workflow: 'w2', status: 'review', can_answer: false, question: '', links: [] }];
vm.createContext(ctx); vm.runInContext(code, ctx);

(async () => {
  await ctx.taiChoDuyet();
  assert.equal(host.hidden, false);
  assert.ok(host.innerHTML.includes('SKY tập 0') && host.innerHTML.includes('san-xuat-clip-sky'));
  assert.ok(host.innerHTML.includes('DUYỆT CONTENT &lt;b&gt;'), 'câu hỏi phải được escape');
  assert.ok(host.innerHTML.includes('/files/raw?brain=%2Fbrains%2Fb&amp;path=marketing%2Fa%2Fstory.md'));
  assert.equal((host.innerHTML.match(/data-ap="ok"/g) || []).length, 1, 'chỉ thẻ trả lời được mới có nút Duyệt');
  assert.ok(host.innerHTML.includes('ws.ap_tasks_page'));

  // Duyệt gửi đúng "ok" rồi thẻ rời danh sách.
  ctx.items = [ctx.items[1]];
  const btn = { dataset: { ap: 'ok', id: 'T1' }, disabled: false };
  ctx.xuLyChoDuyet({ target: { closest: () => btn } });
  await new Promise((r) => setImmediate(r));
  assert.equal(sent.length, 1); assert.equal(sent[0].id, 'T1'); assert.equal(sent[0].answer, 'ok'); assert.equal(sent[0].brain, 'b');
  assert.ok(!host.innerHTML.includes('SKY tập 0'));

  // Yêu cầu sửa: mở ô, trống thì không gửi, có chữ thì gửi nguyên văn.
  ctx.S.choDuyet = [{ id: 'T3', title: 'A', workflow: 'w', can_answer: true, question: 'q', links: [] }];
  ctx.veChoDuyet();
  ctx.xuLyChoDuyet({ target: { closest: () => ({ dataset: { ap: 'edit', id: 'T3' }, disabled: false }) } });
  assert.ok(host.innerHTML.includes('data-ap-text="T3"'));
  const box = { value: '  ', focus() {} };
  ctx.S.el.querySelector = (q) => (q === '#wsApprovals' ? host : q.includes('data-ap-text') ? box : { textContent: '' });
  ctx.xuLyChoDuyet({ target: { closest: () => ({ dataset: { ap: 'send', id: 'T3' }, disabled: false }) } });
  assert.equal(sent.length, 1, 'ô trống không được gửi');
  box.value = ' Đổi màu cyan ';
  ctx.xuLyChoDuyet({ target: { closest: () => ({ dataset: { ap: 'send', id: 'T3' }, disabled: false }) } });
  await new Promise((r) => setImmediate(r));
  assert.equal(sent.length, 2); assert.equal(sent[1].answer, 'Đổi màu cyan');

  // Gửi hỏng: thẻ còn đó.
  reply = { ok: false, error: 'lỗi' };
  ctx.S.choDuyet = [{ id: 'T4', title: 'B', workflow: 'w', can_answer: true, question: 'q', links: [] }];
  ctx.S.duyetMo = {};
  await ctx.guiDuyet('T4', 'ok');
  assert.equal(ctx.S.choDuyet.length, 1);

  // Đợt 2: ảnh và video nhúng thẳng trong thẻ.
  ctx.S.loai = 'workflow';
  ctx.S.choDuyet = [{ id: 'T5', title: 'M', workflow: 'w', can_answer: true, question: 'q', agents: [{ slug: 'hm', name: 'Hoàng Minh' }],
    links: [{ path: 'a/b.png', kind: 'image' }, { path: 'a/c.mp4', kind: 'video' }, { path: 'a/d.md', kind: 'doc' }] }];
  ctx.S.duyetMo = {}; ctx.veChoDuyet();
  assert.ok(host.innerHTML.includes('<img') && host.innerHTML.includes('<video'), 'ảnh và video phải nhúng');
  assert.equal((host.innerHTML.match(/<img/g) || []).length, 1); assert.equal((host.innerHTML.match(/<video/g) || []).length, 1);

  // Đợt 3: ô lưu bài học chỉ hiện khi mở ô sửa, và lời sửa đi vào kho bài học của agent đã chọn.
  assert.ok(!host.innerHTML.includes('data-ap-lesson'));
  ctx.S.duyetMo = { T5: true }; ctx.veChoDuyet();
  assert.ok(host.innerHTML.includes('data-ap-lesson="T5"') && host.innerHTML.includes('Hoàng Minh'));
  sent.length = 0; reply = { ok: true };
  const box2 = { value: 'Luôn dùng nền cyan', focus() {} }, cb = { checked: true }, sel = { value: 'hm' };
  ctx.S.el.querySelector = (q) => (q === '#wsApprovals' ? host : q.includes('data-ap-text') ? box2 : q.includes('data-ap-lesson') ? cb : q.includes('data-ap-agent') ? sel : { textContent: '' });
  ctx.xuLyChoDuyet({ target: { closest: () => ({ dataset: { ap: 'send', id: 'T5' }, disabled: false }) } });
  await new Promise((r) => setImmediate(r));
  assert.equal(sent.length, 2, 'một bài học và một lời duyệt');
  assert.equal(sent[0].text, 'Luôn dùng nền cyan'); assert.equal(sent[1].answer, 'Luôn dùng nền cyan');

  // Lượt cũ báo chờ duyệt: xoá khỏi lịch sử sau khi chủ đồng ý.
  ctx.S.choDuyet = []; ctx.S.lanCu = [{ id: 'R1', name: 'SKY', slug: 's', started_at: 1000 }]; ctx.veChoDuyet();
  assert.equal(host.hidden, false); assert.ok(host.innerHTML.includes('data-ap="del"'));
  ctx.window = { confirm: () => true }; ctx.confirm = ctx.window.confirm;
  sent.length = 0;
  await ctx.xoaLanCu('R1', { disabled: true });
  assert.equal(sent.length, 1); assert.equal(sent[0].brain, 'b'); assert.equal(ctx.S.lanCu.length, 0);

  // Sang tab Cộng sự thì ẩn.
  ctx.S.loai = 'agent'; ctx.veChoDuyet();
  assert.equal(host.hidden, true);
  console.log('ok   khung cho duyet');
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
