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

  // Sang tab Cộng sự thì ẩn.
  ctx.S.loai = 'agent'; ctx.veChoDuyet();
  assert.equal(host.hidden, true);
  console.log('ok   khung cho duyet');
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
