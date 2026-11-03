// 0.444.1: chữ stream từng mẩu không còn dựng lại cả câu trả lời mỗi mẩu (khách báo "đơ cả máy" 03/11/2026).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('dashboard/app.js', 'utf8');

const a = source.indexOf('const _VE_STREAM_MS');
const b = source.indexOf('function huyVeStream');
assert.ok(a > 0 && b > a, 'helpers present');
const helpers = source.slice(a, source.indexOf('\n', b) + 1);

let now = 0, timers = [], ve = 0, cuon = 0;
const ctx = {
  Date: { now: () => now },
  setTimeout: (fn, ms) => { timers.push({ fn, at: now + ms }); return timers.length; },
  clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].fn = null; },
  markdownToHtml: (s) => { ve++; return s; },
  scrollBottom: () => { cuon++; },
};
vm.createContext(ctx);
vm.runInContext(helpers.replace(/^const /m, 'var ') + '\nthis.henVeStream=henVeStream;this.huyVeStream=huyVeStream;', ctx);
function chay(den) {
  for (const t of timers) if (t.fn && t.at <= den) { const f = t.fn; t.fn = null; now = t.at; f(); }
  now = den;
}
function bong() { const inner = { innerHTML: '' }; return { isConnected: true, dataset: {}, querySelector: () => inner, inner }; }

let failures = 0;
function test(name, fn) {
  now = 1000; timers = []; ve = 0; cuon = 0;
  try { fn(); console.log('ok', name); } catch (e) { failures++; console.error('FAIL', name, e.message); }
}

test('2.700 mau trong 10 giay chi ve vai chuc lan, khong phai moi mau', () => {
  const t = { text: '', bubble: bong() };
  for (let i = 0; i < 2700; i++) { t.text += 'abc'; ctx.henVeStream(t); chay(now + 4); }
  chay(now + 1000);
  assert.ok(ve < 200, 'renders ' + ve);
  assert.equal(t.bubble.inner.innerHTML, t.text, 'last render holds the whole text');
  assert.equal(ve, cuon);
});

test('mau dau tien hien ngay, khong cho', () => {
  const t = { text: 'Chao', bubble: bong() };
  ctx.henVeStream(t);
  assert.equal(ve, 1);
  assert.equal(t.bubble.inner.innerHTML, 'Chao');
});

test('huy truoc khi chot luot thi nhip hen khong ve de len ban cuoi', () => {
  const t = { text: 'a', bubble: bong() };
  ctx.henVeStream(t);          // ve ngay
  t.text += 'b'; ctx.henVeStream(t);   // hen
  ctx.huyVeStream(t);
  t.bubble.inner.innerHTML = 'BAN CUOI';
  chay(now + 1000);
  assert.equal(t.bubble.inner.innerHTML, 'BAN CUOI');
  assert.equal(ve, 1);
});

test('bong bong da roi khung thi khong cuon', () => {
  const t = { text: 'x', bubble: bong() };
  t.bubble.isConnected = false;
  ctx.henVeStream(t);
  assert.equal(ve, 1);
  assert.equal(cuon, 0);
});

test('nhanh stream va chot luot goi dung ham gom', () => {
  const i = source.indexOf('data.type === "stream"');
  const j = source.indexOf('data.type === "response"', i);
  const nhanh = source.slice(i, j);
  assert.ok(nhanh.includes('henVeStream(t)'));
  assert.ok(!nhanh.includes('markdownToHtml(t.text'), 'stream branch must not rebuild the whole answer per piece');
  const k = source.indexOf('const finalText = askClean', j);
  assert.ok(source.slice(j, k).includes('huyVeStream(t)'));
});

if (failures) process.exit(1);
