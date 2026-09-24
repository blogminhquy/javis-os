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
  _tinChoLuot: null, _tinChoTimer: null, _tinDutMang: [], _tinDutMangTimer: null,
  _choTaiLen: null, _sendEpoch: 0, _tuGiong: false,
  clearTimeout() {}, setTimeout: fn => fn,
  handsFree: false, voice: { cancelListening() { cancelled++; }, stopSpeaking() {} },
  voiceBtn: { classList: { remove() {} } }, window: {}, tatLive() {}, nhapGiong() {},
  runActions() {}, turn: { micOff: () => [] },
  hideActivity() {}, goMoiTinCu() {}, chatArea: { innerHTML: '' },
  persistSession() {}, notifySessions() {}, syncActiveUI() {}, savedSessionId: 'old',
};
load(context, ['tatRanhTay', 'resetChatView', 'capNhatTinNguoiDung', 'goTinNguoiDungCuoi', 'datTinCho', 'guiTinCho', 'guiTinDutMang']);
let failures = 0;
function test(name, fn) { try { fn(); console.log('ok', name); } catch (e) { failures++; console.error('FAIL', name, e.message); } }
test('leaving a conversation cancels capture even outside hands-free mode', () => {
  context.resetChatView(); assert.equal(cancelled, 1); assert.equal(context.savedSessionId, null);
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
