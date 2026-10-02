// Thanh gọi (call-bar.js) và dây nối của kiểu "bấm mic là gọi" (0.65.18, spec mục 4).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const { create, clock } = require('../../dashboard/call-bar.js');

class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; this.hidden = false; this.dataset = {}; this.attrs = {}; this.className = ''; }
  appendChild(c) { this.children.push(c); return c; }
  set innerHTML(v) { this.children = []; }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k]; }
}
const doc = { createElement: (t) => new Node(t) };
const t = (k, p) => (p && p.tool ? `${k}(${p.tool})` : k);

// 1. hiển thị, trạng thái, đồng hồ, nút
let now = 1000, ticks = [];
const calls = [];
const el = new Node('div'); el.hidden = true;
const bar = create({ el, document: doc, t, now: () => now,
  setInterval: (fn) => { ticks.push(fn); return ticks.length; }, clearInterval: () => {},
  onMute: (want) => calls.push(['mute', want]), onHangup: () => calls.push(['hangup']) });
const [dot, engine, state, clk, mute, hang] = el.children;
bar.show('ChatGPT Live');
assert.equal(el.hidden, false);
assert.equal(engine.textContent, 'ChatGPT Live');
assert.equal(el.dataset.state, 'connecting');
assert.equal(state.textContent, 'call.connecting');
assert.equal(hang.textContent, 'call.hangup');
assert.equal(clk.textContent, '00:00');
now += 65000; ticks[0]();
assert.equal(clk.textContent, '01:05', 'clock advances');
bar.setState('working', 'POS');
assert.equal(state.textContent, 'call.working(POS)');
bar.setState('working');
assert.equal(state.textContent, 'call.working_plain');
bar.setState('nonsense');
assert.equal(el.dataset.state, 'listening', 'unknown state falls back to listening');
mute.onclick();
assert.deepEqual(calls.at(-1), ['mute', true]);
bar.setMuted(true);
assert.equal(el.dataset.state, 'muted');
assert.equal(mute.textContent, 'call.unmute');
assert.equal(mute.getAttribute('aria-pressed'), 'true');
hang.onclick();
assert.deepEqual(calls.at(-1), ['hangup']);
bar.hide();
assert.equal(el.hidden, true);
assert.equal(bar.isVisible(), false);
assert.equal(clock(3725), '1:02:05');

// 2. dây nối trong app.js / index.html / console.js
const app = read('dashboard/app.js');
const html = read('dashboard/index.html');
const con = read('dashboard/console.js');
assert.match(html, /<div class="call-bar" id="callBar" hidden><\/div>\s*<div class="transcript" id="chatArea"[^>]*>/, 'call bar sits right above the chat');
assert.match(html, /call-bar\.js\?v=\d+"><\/script>\s*<script src="\/static\/app\.js/, 'call-bar.js loads before app.js');
assert.match(con, /CHAT_NODE_IDS = \["callBar", "chatArea"/, 'call bar follows the chat to the Chat page');
assert.ok(!/e\.code === "Space"/.test(app), 'Space no longer opens the mic');
assert.match(app, /if \(e\.code === "Escape"\) \{\s*\n[\s\S]{0,400}tatRanhTay\(\)/, 'Esc still hangs up');
assert.match(app, /fetch\("\/voice\/call"\)/, 'mode comes from the call engine');
// 0.65.25: only the FIRST connection of a call falls back to Basic; mid-call it retries and waits
// (test_voice_focus_app.js runs both cases).
assert.match(app, /if \(handsFree && !readySeen\) return _cuocGoiDaNoi \? noiLaiHong\(wakeText, lanThu\) : chuyenSangCoBan\(\);/,
  'Live that cannot start falls back to Basic only before the call has connected');
assert.match(app, /voice.muted = _callMuted/, "mute stops the basic path from reopening the mic");
assert.match(app, /capNhatThanhGoi\(\);\s*\n\}/, 'orb updates also update the call bar');
const vi = JSON.parse(read('dashboard/i18n/vi.json'));
const en = JSON.parse(read('dashboard/i18n/en.json'));
for (const k of ['call.connecting', 'call.listening', 'call.speaking', 'call.working', 'call.working_plain',
  'call.waiting_wake', 'call.reconnecting', 'call.muted', 'call.mute', 'call.unmute', 'call.hangup',
  'call.engine_basic', 'call.engine_api', 'call.fallback']) {
  assert.equal(typeof vi[k], 'string', 'vi ' + k);
  assert.equal(typeof en[k], 'string', 'en ' + k);
}
assert.ok(!/song công/i.test(JSON.stringify(vi)), 'no "song công" in user-facing strings');
assert.ok(!/Space/.test(vi['bar.mic']), 'mic tooltip no longer mentions Space');
console.log('OK - call bar');
