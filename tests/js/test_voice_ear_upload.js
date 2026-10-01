// Tai nghe lại dạng tải lên (0.65.15): ba chỗ khiến câu không tới được tai.
//   1. Lượt ĐẦU sau khi tải trang trên máy tính: bộ ghi bắt đầu sau Web Speech nên bị coi là
//      thiếu tiếng. Nay chờ luồng mic rồi mới mở nhận dạng; lệnh dừng trong lúc chờ vẫn có hiệu lực.
//   2. Rào chú ý chặn "David ơi..." trước khi tai kịp nghe lại "Javis ơi...".
//   3. Chế độ tự nhiên chốt câu bằng cách huỷ phiên, huỷ luôn bản ghi (commitWithEar).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const tick = () => new Promise(resolve => setImmediate(resolve));

function setup(onTranscript = () => {}, opts = {}, ua = 'Chrome desktop') {
  class Recorder {
    static isTypeSupported() { return true; }
    constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; }
    start() { this.state = 'recording'; }
    stop() { this.state = 'inactive'; queueMicrotask(() => { this.ondataavailable({ data: new Blob(['x'.repeat(3000)]) }); this.onstop(); }); }
  }
  const calls = { start: 0, abort: 0 };
  class Recognition { start() { calls.start++; } stop() {} abort() { calls.abort++; } }
  const context = {
    window: { SpeechRecognition: Recognition, speechSynthesis: { getVoices: () => [], cancel() {} } },
    navigator: { userAgent: ua }, localStorage: { getItem: () => null },
    MediaRecorder: Recorder, Blob, FormData, AbortController, console,
    setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  };
  vm.runInNewContext(fs.readFileSync('dashboard/voice.js', 'utf8'), context);
  const voice = new context.window.JavisVoice({ onTranscript, ...opts });
  voice.isSpeaking = () => false;
  voice.stopSpeaking = () => {};
  return { voice, context, calls };
}

test('first desktop turn with an upload ear waits for the mic before recognition', async () => {
  const { voice, calls } = setup();
  voice.sttUpload = true;
  const mic = deferred();
  voice._startMicMeter = () => mic.promise.then(() => { voice.micStream = {}; voice._startRecorder(); });
  voice.startListening();
  assert.equal(calls.start, 0, 'recognition must not start before the recorder');
  mic.resolve(); await tick();
  assert.equal(calls.start, 1);
  assert.equal(voice._recComplete, true, 'audio covers the whole first utterance');
});

test('a stop during the mic wait still closes the session at onstart', async () => {
  const started = [];
  const { voice, calls } = setup(() => {}, { onStart: () => started.push(1) });
  voice.sttUpload = true;
  const mic = deferred();
  voice._startMicMeter = () => mic.promise;
  voice.startListening();
  voice.stopListening();
  mic.resolve(); await tick();
  voice.recognition.onstart();
  assert.equal(calls.abort, 1, 'pending stop must survive the deferred start');
  assert.deepEqual(started, [], 'no listening session is announced');
});

test('without an ear or on a phone the start stays synchronous', () => {
  const desk = setup();
  desk.voice._startMicMeter = () => Promise.resolve();
  desk.voice.startListening();
  assert.equal(desk.calls.start, 1);
  const phone = setup(() => {}, {}, 'Mozilla/5.0 (Linux; Android 14) Chrome Mobile');
  phone.voice.sttUpload = true;
  phone.voice.startListening();
  assert.equal(phone.calls.start, 1);
});

test('a near-wake draft rejected by focus is re-checked on the ear text', async () => {
  const received = [];
  const accepted = [];
  const { voice, context } = setup(t => received.push(t), {
    acceptTranscript: t => { accepted.push(t); return /^javis/i.test(t); },
    wakeCandidate: t => /^david/i.test(t),
  });
  voice.sttUpload = true; voice._recComplete = true;
  voice._stopRecorder = async () => new Blob(['x'.repeat(3000)]);
  context.fetch = async () => ({ ok: true, json: async () => ({ ok: true, text: 'Javis ơi mở trang kết nối' }) });
  voice.onTranscript('David ơi mở trang kết nối');
  await voice._sttDelivery;
  assert.deepEqual(received, ['Javis ơi mở trang kết nối']);
  assert.deepEqual(accepted, ['David ơi mở trang kết nối', 'Javis ơi mở trang kết nối']);
});

test('ordinary noise rejected by focus is never uploaded', async () => {
  const received = [];
  let fetched = 0;
  const { voice, context } = setup(t => received.push(t), {
    acceptTranscript: () => false, wakeCandidate: t => /^david/i.test(t),
  });
  voice.sttUpload = true; voice._recComplete = true;
  context.fetch = async () => { fetched++; return { ok: true, json: async () => ({ ok: true, text: 'x' }) }; };
  voice.onTranscript('mua ngay hôm nay giảm giá');
  await tick();
  assert.equal(fetched, 0);
  assert.deepEqual(received, []);
});

test('the ear still rejects when it also hears no wake word', async () => {
  const received = [];
  const { voice, context } = setup(t => received.push(t), {
    acceptTranscript: t => /^javis/i.test(t), wakeCandidate: () => true,
  });
  voice.sttUpload = true; voice._recComplete = true;
  voice._stopRecorder = async () => new Blob(['x'.repeat(3000)]);
  context.fetch = async () => ({ ok: true, json: async () => ({ ok: true, text: 'David Beckham ghi bàn' }) });
  voice.onTranscript('David Beckham ghi bàn');
  await voice._sttDelivery;
  assert.deepEqual(received, []);
});

test('natural mode commit sends the recording to the ear before cancelling', async () => {
  const { voice, context } = setup();
  voice.sttUpload = true; voice._recComplete = true;
  voice.micStream = {}; voice.isListening = true; voice._startRecorder();
  let body;
  context.fetch = async (url, init) => { body = init.body; return { ok: true, json: async () => ({ ok: true, text: 'Mở dashboard Facebook Ads' }) }; };
  const pending = voice.commitWithEar('Mở double Facebook add');
  assert.equal(voice._discardRecognition, true, 'capture is cancelled right away');
  assert.equal(voice.isTranscribing, true, 'orb shows the ear is working');
  assert.equal(await pending, 'Mở dashboard Facebook Ads');
  assert.equal(body.get('draft'), 'Mở double Facebook add');
  assert.equal(voice.isTranscribing, false);
});

test('natural mode commit without an ear returns the draft and uploads nothing', async () => {
  let fetched = 0;
  const { voice, context } = setup();
  context.fetch = async () => { fetched++; return {}; };
  assert.equal(await voice.commitWithEar('Mở Telegram'), 'Mở Telegram');
  assert.equal(fetched, 0);
});

(async () => {
  let failures = 0;
  for (const [name, fn] of tests) {
    try { await fn(); console.log('ok', name); }
    catch (error) { failures++; console.error('FAIL', name, error.message); }
  }
  if (failures) process.exitCode = 1;
})();
