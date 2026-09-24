const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const tick = () => new Promise(resolve => setImmediate(resolve));
function setup(onTranscript = () => {}) {
  const timers = new Map(); let timerId = 0;
  class Recorder {
    static isTypeSupported() { return true; }
    constructor() { this.state = 'inactive'; this.mimeType = 'audio/webm'; this.finalChunk = 'tail'; }
    start() { this.state = 'recording'; }
    chunk(text) { this.ondataavailable({ data: new Blob([text]) }); }
    stop() { this.state = 'inactive'; queueMicrotask(() => { this.chunk(this.finalChunk); this.onstop(); }); }
  }
  class Recognition { start() {} stop() {} abort() {} }
  const context = {
    window: { SpeechRecognition: Recognition, speechSynthesis: { getVoices: () => [], cancel() {} } },
    navigator: { userAgent: 'Chrome desktop' }, localStorage: { getItem: () => null },
    MediaRecorder: Recorder, Blob, FormData, AbortController, console,
    setTimeout: fn => { timers.set(++timerId, fn); return timerId; },
    clearTimeout: id => timers.delete(id), setInterval: () => 0, clearInterval() {},
  };
  vm.runInNewContext(fs.readFileSync('dashboard/voice.js', 'utf8'), context);
  const voice = new context.window.JavisVoice({ onTranscript });
  voice.isSpeaking = () => false;
  return { voice, context, timers };
}
test('recorder keeps the final dataavailable chunk delivered by stop', async () => {
  const { voice } = setup();
  voice.sttUpload = true; voice.micStream = {}; voice.isListening = true;
  voice._startRecorder(); voice._rec.chunk('head');
  assert.equal(await (await voice._stopRecorder()).text(), 'headtail');
});
test('late recorder chunks cannot contaminate the next recording', async () => {
  const { voice } = setup();
  voice.sttUpload = true; voice.micStream = {}; voice.isListening = true;
  voice._startRecorder(); voice._rec.chunk('first'); voice._rec.finalChunk = 'tailA';
  const first = voice._stopRecorder();
  voice._startRecorder(); voice._rec.chunk('second'); voice._rec.finalChunk = 'tailB';
  await first;
  assert.equal(await (await voice._stopRecorder()).text(), 'secondtailB');
});
test('a complete recording may legitimately correct a long browser hypothesis to a short answer', async () => {
  const { voice, context } = setup();
  voice.sttUpload = true; voice._recComplete = true;
  voice._stopRecorder = async () => new Blob(['x'.repeat(3000)]);
  context.fetch = async () => ({ ok: true, json: async () => ({ ok: true, text: 'Không.' }) });
  let received;
  await voice._quaStt('không không không không không không', text => { received = text; });
  assert.equal(received, 'Không.');
});
test('late capture uses browser transcript without trusting the partial recording', async () => {
  const { voice, context } = setup();
  voice.sttUpload = true; voice._recComplete = false;
  voice._stopRecorder = async () => new Blob(['x'.repeat(3000)]);
  let uploads = 0, received;
  context.fetch = async () => { uploads++; return { ok: true, json: async () => ({ ok: true, text: 'Javis' }) }; };
  await voice._quaStt('Đưa anh về màn hình trò chuyện nhé.', text => { received = text; });
  assert.equal(received, 'Đưa anh về màn hình trò chuyện nhé.');
  assert.equal(uploads, 0);
});
test('STT results are delivered in spoken order even when the second request finishes first', async () => {
  const { voice, context } = setup();
  voice.sttUpload = true; voice._recComplete = true;
  voice._stopRecorder = async () => new Blob(['x'.repeat(3000)]);
  const a = deferred(), b = deferred(); let call = 0;
  context.fetch = () => (++call === 1 ? a.promise : b.promise);
  const received = [];
  const first = voice._quaStt('lượt một', t => received.push(t));
  const second = voice._quaStt('lượt hai', t => received.push(t));
  await tick();
  b.resolve({ ok: true, json: async () => ({ ok: true, text: 'hai' }) });
  await tick(); assert.deepEqual(received, []);
  a.resolve({ ok: true, json: async () => ({ ok: true, text: 'một' }) });
  await Promise.all([first, second]); assert.deepEqual(received, ['một', 'hai']);
});
test('STT posts the selected language snapshot, including explicit auto', async () => {
  for (const language of ['vi-VN', 'en-US', 'auto']) {
    const { voice, context } = setup();
    voice.setRecognitionLang(language); voice.sttUpload = true; voice._recComplete = true;
    const audio = deferred(); voice._stopRecorder = () => audio.promise;
    let sent;
    context.fetch = async (url, options) => {
      sent = options.body.get('lang');
      return { ok: true, json: async () => ({ ok: true, text: 'kết quả' }) };
    };
    const pending = voice._quaStt('câu gốc', () => {});
    voice.setRecognitionLang('fr-FR');
    audio.resolve(new Blob(['x'.repeat(3000)]));
    await pending; assert.equal(sent, language);
  }
});

test('STT network errors and timeout retain the browser utterance', async () => {
  for (const timeout of [false, true]) {
    const { voice, context, timers } = setup();
    voice.sttUpload = true; voice._recComplete = true;
    voice._stopRecorder = async () => new Blob(['x'.repeat(3000)]);
    context.fetch = (url, options) => timeout
      ? new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('timeout'))))
      : Promise.reject(new Error('offline'));
    let received;
    const pending = voice._quaStt('Đưa anh về trò chuyện nhé.', t => { received = t; });
    await tick();
    if (timeout) for (const fn of timers.values()) fn();
    await pending;
    assert.equal(received, 'Đưa anh về trò chuyện nhé.');
    assert.equal(voice.isTranscribing, false);
  }
});

test('TTS abort drops committed words from earlier recognition segments', () => {
  const { voice } = setup(); let received = '';
  voice.onTranscript = t => { received = t; };
  voice.isListening = true; voice._committed = 'tiếng loa cũ';
  voice._muteRecognition(); voice.recognition.onend();
  assert.equal(received, '');
});
test('repeated start while recognition is opening does not open a second session', () => {
  const { voice } = setup(); let starts = 0;
  voice._startMicMeter = async () => {}; voice.stopSpeaking = () => {}; voice._moKhoaAudioIOS = () => {};
  voice.recognition.start = () => { starts++; };
  voice.startListening(true); voice.startListening(true);
  assert.equal(starts, 1);
});

test('a fresh start clears old stop debt, then cancellation during opening aborts onstart', () => {
  const { voice } = setup(); let aborted = 0, started = 0;
  voice._startMicMeter = async () => {}; voice.stopSpeaking = () => {}; voice._moKhoaAudioIOS = () => {};
  voice._stopPending = true;
  voice.recognition.abort = () => { aborted++; };
  voice.onStart = () => { started++; };
  voice.startListening(); assert.equal(voice._stopPending, false);
  voice._muteRecognition(); assert.equal(voice._resumeAfterTTS, true);
  voice.recognition.onstart();
  assert.equal(aborted, 2); assert.equal(started, 0); // immediate abort plus onstart repayment
});
test('late recognition result after TTS abort is discarded even when playback already ended', () => {
  const { voice } = setup(); let received = '';
  voice.onTranscript = t => { received = t; };
  voice.isListening = true; voice._muteRecognition();
  const row = Object.assign([{ transcript: 'tiếng loa' }], { isFinal: true });
  voice.recognition.onresult({ results: [row] }); voice.recognition.onend();
  assert.equal(received, '');
});
test('cancelling a voice session discards pending STT results', async () => {
  const { voice, context } = setup();
  voice.sttUpload = true; voice._recComplete = true;
  voice._stopRecorder = async () => new Blob(['x'.repeat(3000)]);
  const response = deferred(); let received = '';
  context.fetch = () => response.promise;
  const pending = voice._quaStt('lượt cũ', t => { received = t; });
  await tick();
  assert.equal(typeof voice.cancelListening, 'function');
  voice.cancelListening();
  response.resolve({ ok: true, json: async () => ({ ok: true, text: 'Javis' }) });
  await pending;
  assert.equal(received, ''); assert.equal(voice.isTranscribing, false);
});
test('a pending microphone permission cannot reopen capture after cancellation', async () => {
  const { voice, context } = setup(); const permission = deferred(); let stopped = 0;
  voice._ensureCtx = () => ({ createMediaStreamSource: () => ({ connect() {}, disconnect() {} }), createAnalyser: () => ({}) });
  context.navigator.mediaDevices = { getUserMedia: () => permission.promise };
  const opening = voice._startMicMeter();
  voice._nhaMicStream();
  permission.resolve({ getTracks: () => [{ stop() { stopped++; } }] });
  await opening;
  assert.equal(voice.micStream, null); assert.equal(stopped, 1);
});
test('finishing recognition cancels the endpoint timer from that turn', () => {
  const { voice, context, timers } = setup();
  voice._silenceTimer = context.setTimeout(() => voice.stopListening(), 100);
  voice.userStopped = true; voice.recognition.onend();
  assert.equal(timers.size, 0);
});
(async () => {
  let failures = 0;
  for (const [name, fn] of tests) {
    try { await fn(); console.log('ok', name); }
    catch (error) { failures++; console.error('FAIL', name, error.message); }
  }
  if (failures) process.exitCode = 1;
})();
