const assert = require('node:assert/strict');
const { Attention, SpeechLevel, IDLE_MS } = require('../../dashboard/voice-attention.js');
// 0.65.22: im 30 giây (chủ dự án 01/10: 20 giây hơi ít).
assert.equal(IDLE_MS, 30000);
let now = 0;
const gate = new Attention({ now: () => now });
gate.start();
assert.equal(gate.accept('đưa anh về trò chuyện'), true, 'explicit mic needs no wake word');
now += 29999;
assert.equal(gate.waiting(), false, 'still awake just before 30 seconds');
now += 2;
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
now += 29000;
assert.equal(gate.preview('anh muốn nói một câu dài'), true);
now += 5000;
assert.equal(gate.accept('anh muốn nói một câu dài và chưa xong ý'), true, 'started before idle deadline');
now += 29000;
gate.keepActive(); // assistant still processing/playing an accepted turn
now += 29000;
assert.equal(gate.accept('ừ'), true, 'window follows actual reply completion');
now += 30001;
gate.keepActive();
assert.equal(gate.waiting(), true, 'background output cannot wake sleeping gate');
gate.start(); gate.preview('câu cũ'); gate.stop();
assert.equal(gate.accept('câu cũ'), false, 'cancellation drops candidate');
gate.start(); gate.preview('câu chưa xong'); now += 120001;
assert.equal(gate.accept('kết quả quá muộn'), false, 'candidate lease is bounded');
gate.enabled = false; gate.start(); now += 900000;
assert.equal(gate.accept('nghe liên tục'), true);
assert.equal(gate.waiting(), false);

// 0.65.22: nối lại phiên Live đã ngắt bằng CÂU NÓI THẬT, không bắt buộc gọi tên.
const w = new Attention({ now: () => 0 });
for (const text of ['Javis', 'mở lịch', 'David ơi mở trang kết nối', 'Gia vít ơi', 'tiếng TV đang nói', 'ok Javis']) {
  assert.equal(w.wakes(text), true, text);
}
for (const text of ['', '  ', 'ừ', 'ok.', '!!', '123 456']) {
  assert.equal(w.wakes(text), false, JSON.stringify(text));
}

// 0.65.15: câu gần giống tên gọi chỉ được đưa cho tai nghe lại, KHÔNG mở rào.
const near = new Attention({ now: () => 0 });
assert.equal(near.wakeCandidate('David ơi mở trang kết nối'), false, 'stopped gate offers nothing');
near.start();
for (const text of ['David ơi mở trang kết nối', 'hey Davis', 'Gia vít ơi', 'Javix, mở Telegram']) {
  assert.equal(near.wakeCandidate(text), true, text);
}
for (const text of ['mua ngay hôm nay', 'anh vừa gặp David', 'Davidson', 'Javis ơi']) {
  assert.equal(near.wakeCandidate(text), false, text);
}

// Dự phòng đo âm lượng: tiếng to hơn nền đủ lâu mới tính là có người nói.
let t = 0;
const level = new SpeechLevel({ now: () => t });
for (let i = 0; i < 50; i++) { t += 100; assert.equal(level.feed(0.005), false, 'quiet room'); }
t += 100; assert.equal(level.feed(0.2), false, 'one loud frame (a knock) is not speech');
t += 100; assert.equal(level.feed(0.005), false);
let fired = false;
for (let i = 0; i < 5 && !fired; i++) { t += 100; fired = level.feed(0.08); }
assert.equal(fired, true, 'sustained voice-level sound fires within ~350 ms');
const loudStart = new SpeechLevel({ now: () => t });
fired = false;
for (let i = 0; i < 6 && !fired; i++) { t += 100; fired = loudStart.feed(0.1); }
assert.equal(fired, true, 'starting while someone talks must not paralyse the detector');
const hum = new SpeechLevel({ now: () => t });
for (let i = 0; i < 300; i++) { t += 100; hum.feed(0.012); }
fired = false;
for (let i = 0; i < 3 && !fired; i++) { t += 100; fired = hum.feed(0.03); }
assert.equal(fired, false, 'a steady fan hum raises the floor; slightly louder hum is still not speech');
console.log('voice attention: 30 s idle, wake, real-speech resume, interim revision, near-wake pass, level fallback');
