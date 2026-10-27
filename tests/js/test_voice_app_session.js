const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('dashboard/app.js', 'utf8');
function load(context, names) {
  for (const name of names) {
    const start = source.indexOf('function ' + name + '(');
    assert.ok(start >= 0, name);
    vm.runInNewContext(source.slice(start, source.indexOf('\n}', start) + 2), context);
  }
}
let cancelled = 0;
const context = {
  adaptive: {cancel(){}, running:()=>false, input:()=>false, manual:()=>false, holding:()=>false, blocked:()=>false,start(){},save(){}},
  adaptiveOutbox:new Map(), adaptiveContinuation:'',

  _tinChoLuot: null, _tinChoTimer: null, _tinDutMang: [], _tinDutMangTimer: null,
  _choTaiLen: null, _sendEpoch: 0, _tuGiong: false,
  attention: { stop() {} }, liveWake: { cancelListening() {} }, updateVoiceFocus() {},
  clearTimeout() {}, setTimeout: fn => fn,
  handsFree: false, voice: { cancelListening() { cancelled++; }, stopSpeaking() {} },
  voiceBtn: { classList: { remove() {} } }, window: {}, tatLive() {}, nhapGiong() {},
  runActions() {}, turn: { micOff: () => [] },
  hideActivity() {}, goMoiTinCu() {}, chatArea: { innerHTML: '' },
  persistSession() {}, notifySessions() {}, syncActiveUI() {}, savedSessionId: 'old',
};
load(context, ['tatRanhTay', 'resetChatView', 'boViecPhienCu', 'capNhatTinNguoiDung', 'goTinNguoiDungCuoi', 'datTinCho', 'guiTinCho', 'guiTinDutMang']);
let failures = 0;
function test(name, fn) { try { fn(); console.log('ok', name); } catch (e) { failures++; console.error('FAIL', name, e.message); } }
test('leaving a conversation cancels capture even outside hands-free mode', () => {
  context.resetChatView(); assert.equal(cancelled, 1); assert.equal(context.savedSessionId, null);
});
// 0.347.0 (owner, 27/10/2026): leaving a conversation during a call (Partners page, history) keeps the call; only
// what was heading to the old conversation is dropped.
test('during a call, leaving a conversation keeps the call and drops queued sends', () => {
  let hungUp = 0;
  const tat = context.tatRanhTay;
  context.tatRanhTay = () => { hungUp++; };
  try {
    context.handsFree = true; context.voiceMode = 'basic'; context._sendEpoch = 0; context._tinDutMang = ['câu ở A'];
    cancelled = 0;
    context.resetChatView();
    assert.equal(hungUp, 0, 'the call is not hung up');
    assert.equal(context.handsFree, true);
    assert.equal(context._sendEpoch, 1, 'sends still in flight to the old conversation are invalidated');
    assert.equal(context._tinDutMang.length, 0, 'a reconnect resend cannot reach the new conversation');
    assert.equal(cancelled, 1, 'half-heard words are dropped, the hands-free loop listens again');
  } finally {
    context.tatRanhTay = tat; context.handsFree = false; context.savedSessionId = 'old';
  }
});
test('a delayed correction cannot overwrite a newer user message', () => {
  context.convo = [{ role: 'user', text: 'câu mới' }];
  const div = { dataset: { text: 'câu mới' }, querySelector: () => null };
  context.chatArea.querySelectorAll = () => [div];
  context.capNhatTinNguoiDung('Javis', 'câu cũ');
  assert.equal(div.dataset.text, 'câu mới'); assert.equal(context.convo[0].text, 'câu mới');
});
test('cancelling a session drops its queued barge-in before switching chats', () => {
  const sent = []; context.sendMessage = t => sent.push(t);
  context.savedSessionId = 'A'; context.datTinCho('câu ở A');
  context.tatRanhTay(); context.savedSessionId = 'B'; context.guiTinCho();
  assert.equal(sent.length, 0);
});
test('a reconnect send already scheduled cannot enter the next chat', () => {
  const scheduled = [], sent = [];
  context.setTimeout = fn => { scheduled.push(fn); };
  context.sendMessage = t => sent.push(t);
  context._tinDutMang = ['câu ở A']; context.guiTinDutMang();
  context.tatRanhTay(); context.savedSessionId = 'B';
  for (const fn of scheduled) fn();
  assert.equal(sent.length, 0);
});
test('noise removal matches the original user message and excludes live drafts', () => {
  context.convo = [{ role: 'user', text: 'câu mới' }];
  let removed = 0;
  context.chatArea.querySelectorAll = selector => {
    assert.equal(selector, '.msg-user:not(.msg-nhap-giong)');
    return [{ parentNode: { removeChild() { removed++; } } }];
  };
  assert.equal(context.goTinNguoiDungCuoi('câu cũ'), false);
  assert.equal(removed, 0); assert.equal(context.convo.length, 1);
  assert.equal(context.goTinNguoiDungCuoi('câu mới'), true);
  assert.equal(removed, 1); assert.equal(context.convo.length, 0);
});
if (failures) process.exitCode = 1;
