const assert = require('node:assert/strict');
const { Attention } = require('../../dashboard/voice-attention.js');
let now = 0;
const gate = new Attention({ now: () => now });
gate.start();
assert.equal(gate.accept('đưa anh về trò chuyện'), true, 'explicit mic needs no wake word');
now += 20001;
assert.equal(gate.waiting(), true);
for (const text of ['mua ngay hôm nay', 'ừ', 'Ich habe dich', 'anh vừa xem Javis trên TV', 'Javiscript']) {
  assert.equal(gate.preview(text), false);
  assert.equal(gate.accept(text), false);
}
assert.equal(gate.waiting(), true, 'noise must not extend the conversation');
assert.equal(gate.preview('Javis'), true);
assert.equal(gate.waiting(), true, 'interim wake is not permission to accept a revised final');
assert.equal(gate.accept('David'), false);
assert.equal(gate.accept('Javis ơi, đưa anh về trò chuyện'), true);
assert.equal(gate.accept('không'), true, 'short followup preserved');
now += 19000;
assert.equal(gate.preview('anh muốn nói một câu dài'), true);
now += 5000;
assert.equal(gate.accept('anh muốn nói một câu dài và chưa xong ý'), true, 'started before idle deadline');
now += 19000;
gate.keepActive(); // assistant still processing/playing an accepted turn
now += 19000;
assert.equal(gate.accept('ừ'), true, 'window follows actual reply completion');
now += 20001;
gate.keepActive();
assert.equal(gate.waiting(), true, 'background output cannot wake sleeping gate');
gate.start(); gate.preview('câu cũ'); gate.stop();
assert.equal(gate.accept('câu cũ'), false, 'cancellation drops candidate');
gate.start(); gate.preview('câu chưa xong'); now += 120001;
assert.equal(gate.accept('kết quả quá muộn'), false, 'candidate lease is bounded');
gate.enabled = false; gate.start(); now += 900000;
assert.equal(gate.accept('nghe liên tục'), true);
assert.equal(gate.waiting(), false);
console.log('voice attention: idle, wake, interim revision, short/long turns, cancellation pass');
