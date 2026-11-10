// 2026-11-10: a streaming answer renders its finished blocks once. Only the block still being written is redrawn.
//   node tests/js/test_stream_incremental.js
// Before, every flush parsed the whole answer and replaced the whole bubble, so the browser laid out the full text
// again each time (a 20,000 character answer on a throttled phone: 43 long tasks). This test runs the real helpers of
// app.js with the real splitter of chat-render.js against a small stand-in DOM, and pins three things: what is
// settled is rendered exactly once, what ends up in the bubble is the whole answer in order, and a bubble somebody
// else redrew starts over instead of mixing two states.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { streamCut, mdToHtml } = require('../../dashboard/chat-render.js');
const source = fs.readFileSync('dashboard/app.js', 'utf8');

const a = source.indexOf('const _VE_STREAM_MS');
const b = source.indexOf('function huyVeStream');
const helpers = source.slice(a, source.indexOf('\n', b) + 1);

// ---- a stand-in DOM: a parent with an ordered child list is all the helper touches ----
function node(kind, text) {
  return { kind, text, parentNode: null,
    get nextSibling() { const p = this.parentNode; if (!p) return null; return p.children[p.children.indexOf(this) + 1] || null; } };
}
function element() {
  const el = { children: [], _jvStream: undefined,
    appendChild(n) { for (const c of flat(n)) { c.parentNode = el; el.children.push(c); } return n; },
    insertBefore(n, ref) { const i = el.children.indexOf(ref); const add = flat(n); for (const c of add) c.parentNode = el; el.children.splice(i, 0, ...add); return n; },
    removeChild(n) { el.children.splice(el.children.indexOf(n), 1); n.parentNode = null; return n; },
    set textContent(v) { for (const c of el.children) c.parentNode = null; el.children = []; },
    get html() { return el.children.filter(c => c.kind === 'html').map(c => c.text).join(''); },
  };
  return el;
}
const flat = n => (n.kind === 'fragment' ? n.parts : [n]);

let now = 0, timers = [], rendered = [], scrolls = 0;
const ctx = {
  Date: { now: () => now },
  setTimeout: (fn, ms) => { timers.push({ fn, at: now + ms }); return timers.length; },
  clearTimeout: (id) => { if (timers[id - 1]) timers[id - 1].fn = null; },
  markdownToHtml: (s) => { rendered.push(s); return s; },          // identity: the bubble then holds the source text
  scrollBottom: () => { scrolls++; },
  window: { JavisStreamCut: streamCut },
  document: {
    body: {},
    createComment: (t) => node('comment', t),
    createRange: () => ({ selectNodeContents() {}, createContextualFragment: (html) => ({ kind: 'fragment', parts: [node('html', html)] }) }),
  },
};
vm.createContext(ctx);
vm.runInContext(helpers.replace(/^const /m, 'var ') + '\nthis.henVeStream=henVeStream;this.huyVeStream=huyVeStream;this._veStreamNgay=_veStreamNgay;', ctx);
function run(until) {
  for (const t of timers) if (t.fn && t.at <= until) { const f = t.fn; t.fn = null; now = t.at; f(); }
  now = until;
}
function bubble() { const inner = element(); return { isConnected: true, dataset: {}, querySelector: () => inner, inner }; }

let failures = 0;
function test(name, fn) {
  now = 1000; timers = []; rendered = []; scrolls = 0;
  try { fn(); console.log('ok', name); } catch (e) { failures++; console.error('FAIL', name, e.message); }
}

// a long answer: 60 sections of heading, paragraph, list, and every fourth one a code block
const section = i => `### Section ${i}\n\nRevenue this week reached ${120 + i} million, up ${i % 9 + 1}% on last week.\n\n- item one ${i}\n- item two\n\nClosing line ${i}.\n\n`
  + (i % 4 === 0 ? '```python\ndef f' + i + '(x):\n\n    return x + ' + i + '\n```\n\n' : '');
let FULL = ''; for (let i = 1; i <= 60; i++) FULL += section(i);

test('a long answer: settled text is rendered once, the bubble holds the whole answer', () => {
  const t = { text: '', bubble: bubble() };
  for (let p = 0; p < FULL.length; p += 20) { t.text += FULL.slice(p, p + 20); ctx.henVeStream(t); run(now + 16); }
  run(now + 1000);
  assert.equal(t.bubble.inner.html, FULL, 'bubble content is the full answer, in order');
  const chars = rendered.reduce((n, s) => n + s.length, 0);
  // The old path rendered the whole text each time: about flushes * FULL.length / 2 characters. Now each character
  // is rendered once when it settles plus a few times while it is the growing block.
  const flushes = scrolls;
  assert.ok(flushes > 20, 'flushes ' + flushes);
  assert.ok(chars < FULL.length * 12, `rendered ${chars} chars for a ${FULL.length} char answer over ${flushes} flushes`);
  assert.ok(chars < flushes * FULL.length / 2 / 4, 'at least four times less than rendering everything on every flush');
  const kids = t.bubble.inner.children;
  assert.equal(kids.filter(c => c.kind === 'comment').length, 1, 'one tail marker');
  assert.ok(kids.indexOf(kids.find(c => c.kind === 'comment')) > 10, 'settled blocks sit before the marker');
});

test('nodes of settled blocks are the same objects flush after flush', () => {
  const t = { text: '', bubble: bubble() };
  const first = 'One.\n\nTwo.\n\nThree is still being ';
  t.text = first; ctx._veStreamNgay(t);
  const kept = t.bubble.inner.children.filter(c => c.kind === 'html' && t.bubble.inner.children.indexOf(c) < t.bubble.inner.children.findIndex(x => x.kind === 'comment'));
  assert.ok(kept.length >= 1, 'something settled');
  t.text += 'written.\n\nFour.\n\nFive'; ctx._veStreamNgay(t);
  for (const k of kept) assert.equal(k.parentNode, t.bubble.inner, 'a settled node was not replaced');
  assert.equal(t.bubble.inner.html, t.text);
});

test('one flush redraws only the growing block', () => {
  const t = { text: 'Alpha.\n\nBeta.\n\nGam', bubble: bubble() };
  ctx._veStreamNgay(t);
  rendered = [];
  t.text += 'ma'; ctx._veStreamNgay(t);
  // "Beta." is complete but stays in the tail: a block settles only once a complete plain line follows it, since
  // the line being written could still turn out to continue it.
  assert.deepEqual(rendered, ['Beta.\n\nGamma'], 'only the tail went through the renderer, "Alpha." did not');
});

test('a code block and a list stay in the growing part until plain text follows', () => {
  const t = { text: '', bubble: bubble() };
  t.text = 'Intro.\n\n```js\nlet a = 1;\n\nlet b = 2;\n'; ctx._veStreamNgay(t);
  const mark = () => t.bubble.inner.children.findIndex(c => c.kind === 'comment');
  assert.equal(t.bubble.inner.children.slice(0, mark()).map(c => c.text).join(''), '', 'nothing settles inside an open fence');
  t.text += '```\n\n1. one\n\n2. two\n\n'; ctx._veStreamNgay(t);
  assert.equal(t.bubble.inner.children.slice(0, mark()).map(c => c.text).join(''), '', 'nor inside a list');
  t.text += 'Plain again.\n\nAnd more.\n'; ctx._veStreamNgay(t);
  assert.ok(t.bubble.inner.children.slice(0, mark()).map(c => c.text).join('').endsWith('Plain again.\n\n'));
  assert.equal(t.bubble.inner.html, t.text);
});

test('a bubble somebody else redrew starts over', () => {
  const t = { text: 'A.\n\nB.\n\nC', bubble: bubble() };
  ctx._veStreamNgay(t);
  t.bubble.inner.textContent = '';                       // e.g. the final render, or a session redraw
  t.bubble.inner.appendChild(node('html', 'SOMETHING ELSE'));
  t.text += 'D'; ctx._veStreamNgay(t);
  assert.equal(t.bubble.inner.html, t.text, 'no leftover from the other draw, no lost block');
});

test('text that is no longer the settled text plus more starts over', () => {
  const t = { text: 'A.\n\nB.\n\nC.\n\nD', bubble: bubble() };
  ctx._veStreamNgay(t);
  t.text = 'Different answer.\n\nSecond.\n\nThird';     // a new turn reusing the bubble
  ctx._veStreamNgay(t);
  assert.equal(t.bubble.inner.html, t.text);
  t.text = 'Dif';                                        // shorter than what was settled
  ctx._veStreamNgay(t);
  assert.equal(t.bubble.inner.html, 'Dif');
});

test('without the splitter the whole bubble is rendered as before', () => {
  const keep = ctx.window.JavisStreamCut;
  ctx.window.JavisStreamCut = undefined;
  const inner = { innerHTML: '' };
  const t = { text: 'x\n\ny\n\nz', bubble: { isConnected: true, dataset: {}, querySelector: () => inner } };
  ctx._veStreamNgay(t);
  ctx.window.JavisStreamCut = keep;
  assert.equal(inner.innerHTML, 'x\n\ny\n\nz');
});

// ---- the splitter itself ----
test('streamCut: only complete plain blocks, never inside a fence, a list, a table, a comment or frontmatter', () => {
  const cutText = (s) => s.slice(0, streamCut(s, 0));
  assert.equal(cutText('a\n\nb\n\nc'), 'a\n\n', 'the last line is still being written');
  assert.equal(cutText('a\n\nb\n\nc\n'), 'a\n\nb\n\n');
  assert.equal(cutText('1. a\n\n2. b\n\n3. c\n'), '', 'a loose numbered list is one block');
  assert.equal(cutText('- a\n\n- b\n\ntext\n\nmore\n'), '- a\n\n- b\n\ntext\n\n');
  assert.equal(cutText('```js\na\n\nb\n```\n\nx\n\ny\n'), '```js\na\n\nb\n```\n\nx\n\n');
  assert.equal(cutText('a\n\n```\nopen\n\nstill open\n\nplain looking\n'), '', 'nothing is settled after an open fence');
  assert.equal(cutText('a\n\n| x |\n|---|\n| 1 |\n\nb\n\nc\n'), 'a\n\n| x |\n|---|\n| 1 |\n\nb\n\n');
  assert.equal(cutText('a\n\n<!-- JAVIS_ASK: {\n\n"q": 1} -->\n\nb\n\nc\n'), 'a\n\n<!-- JAVIS_ASK: {\n\n"q": 1} -->\n\nb\n\n');
  assert.equal(cutText('a\n\n<!-- open\n\nb\n\nc\n'), '', 'an open hidden block keeps everything after it');
  assert.equal(cutText('---\nt: 1\n'), '', 'open frontmatter');
  assert.equal(cutText('---\nt: 1\n---\n\na\n\nb\n\nc\n'), '---\nt: 1\n---\n\na\n\nb\n\n');
  assert.equal(cutText('a\n\n---\n\nb\n'), '', 'never right before or after a rule line, which could read as frontmatter');
  assert.equal(streamCut('a\n\nb\n\nc\n\nd\n', 3), 9, 'continues from an earlier cut');
  assert.equal(streamCut('', 0), 0);
  assert.equal(streamCut(null, 0), 0);
});

test('rendering the pieces gives the same HTML as rendering the whole answer', () => {
  const norm = h => h.replace(/\s+/g, ' ').replace(/> </g, '><').trim();
  for (const step of [1, 7, 20, 64]) {
    let len = 0, html = '';
    for (let p = step; ; p += step) {
      const text = FULL.slice(0, Math.min(p, FULL.length));
      const cut = streamCut(text, len);
      if (cut > len) { html += mdToHtml(text.slice(len, cut)); len = cut; }
      if (p >= FULL.length) { html += mdToHtml(text.slice(len)); break; }
    }
    assert.equal(norm(html), norm(mdToHtml(FULL)), 'step ' + step);
  }
});

test('app.js: the final render still replaces the whole bubble', () => {
  const j = source.indexOf('data.type === "response"');
  const k = source.indexOf('_renderCtxLine(msgEl, data)', j);
  assert.ok(source.slice(j, k).includes('.innerHTML = markdownToHtml(shownText'));
});

if (failures) process.exit(1);
console.log('\nOK - test_stream_incremental');
