/* Execute production app callbacks. Browser boundaries are simulated; no microphone/network. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { Attention } = require('../../dashboard/voice-attention.js');
const source = fs.readFileSync('dashboard/app.js', 'utf8');
let now = 0, liveOptions, wakeOptions, voiceOptions, stopCount = 0;
let captureEnd = Promise.resolve(true);
const sent = [], stored = [], drafts = [], events = [];
const button = {};
const noop = () => {};
const box = {
  window: { JavisVoiceAttention: { Attention: class extends Attention { constructor() { super({now: () => now}); } } },
    t: x => x, JavisVoiceLive: { start: async o => { liveOptions = o; events.push('live-start'); return true; },
      stop: () => { stopCount++; }, isSpeaking: () => false, sendText: t => sent.push(t) } },
  JavisVoice: class { constructor(o) { if (!voiceOptions) voiceOptions = o; else wakeOptions = o; this.lang = 'vi-VN'; }
    isSupported() { return true; } micHong() { return false; } isSpeaking() { return false; }
    waitForCaptureEnd() { return captureEnd; }
    setRecognitionLang(lang) { this.lang = lang; }
    cancelListening() { events.push('cancel-capture'); } startListening() { events.push('wake-listen'); } stopSpeaking() {} },
  Date: {now: () => now}, document: {getElementById: () => button},
  voiceBtn: {classList: {add: noop, remove: noop, toggle: noop}},
  handsFree: true, voiceMode: 'standard', isProcessing: false, savedSessionId: 'session-A',
  turn: {micOn: () => [], micOff: () => [], endpoint: () => [], delayFor: () => 1200,
    toolCall: () => [], turnDone: () => [], ttsEnd: () => []},
  _tinChoTimer: null, _tinChoLuot: null, _tinDutMangTimer: null, _tinDutMang: [], _choTaiLen: null,
  _sendEpoch: 0, _tuGiong: false,
  _theoLoi: null, _liveCtxTimer: null,
  runActions: noop, nhapGiong: t => drafts.push(t), veTinTuGiong: t => t, sendMessage: t => sent.push(t),
  capNhatOrb: noop, appendUserMessage: noop, recordTurn: (role, text) => stored.push([role, text]),
  currentBrainPath: () => 'brain', persistSession: noop, guiNguCanhLive: noop,
  setInterval: () => 1, clearInterval: noop, clearTimeout: noop,
};
vm.createContext(box);
vm.runInContext(source.slice(source.indexOf('const attention ='), source.indexOf('// ============================================\n// Voice V1 -')), box);
const start = source.indexOf('let _liveStartSeq');
const end = source.indexOf('// Ngữ cảnh giao diện vào phiên Live', start);
vm.runInContext(source.slice(start, end), box);
function load(name) {
  const p = source.indexOf('function ' + name + '(');
  vm.runInContext((source.slice(p - 6, p) === 'async ' ? 'async ' : '') + source.slice(p, source.indexOf('\n}', p) + 2), box);
}
['batLive', 'tatRanhTay'].forEach(load);
// tatLive is a one-line function, not suitable for the function extractor.
vm.runInContext(source.match(/^function tatLive\(\).*$/m)[0], box);
const run = s => vm.runInContext(s, box);
function final(text) { if (voiceOptions.acceptTranscript(text)) voiceOptions.onTranscript(text); }
(async () => {
  run('attention.start()'); final('đưa anh về trò chuyện');
  assert.deepEqual(sent, ['đưa anh về trò chuyện']); sent.length = 0;
  now = 20001; voiceOptions.onInterim('mua ngay trên TV'); final('mua ngay trên TV');
  assert.equal(sent.length, 0); assert.equal(stored.length, 0); assert.equal(drafts.at(-1), '');
  final('Javis ơi mở màn hình chat'); assert.equal(sent[0], 'Javis ơi mở màn hình chat'); sent.length = 0;
  final('không'); assert.equal(sent[0], 'không'); sent.length = 0;
  now += 20001;
  voiceOptions.onInterim('tiếng TV đang chép dở');
  box.resumeVoiceFocus();
  assert.deepEqual(events.slice(-2), ['cancel-capture', 'wake-listen'], 'click discards buffered noise before a fresh capture');

  box.voiceMode = 'live'; now += 20001; box.tickVoiceFocus();
  assert.equal(stopCount, 1, 'provider closed on idle');
  assert.equal(events.at(-1), 'wake-listen');
  wakeOptions.onTranscript('tiếng người khác'); assert.equal(liveOptions, undefined);
  wakeOptions.onTranscript('Javis mở trò chuyện');
  await new Promise(setImmediate);
  assert.deepEqual(events.slice(-2), ['cancel-capture', 'live-start']);
  assert.equal(sent.length, 0, 'handoff waits for ready');
  liveOptions.onReady({session_id:'session-A'}); liveOptions.onReady({});
  assert.deepEqual(sent, ['Javis mở trò chuyện']);
  assert.deepEqual(stored, [['user', 'Javis mở trò chuyện']]);
  run('_liveJavisText = "Latest answer"');
  liveOptions.onStopped(); liveOptions.onStopped();
  assert.deepEqual(stored.at(-1), ['javis', 'Latest answer']);
  assert.equal(stored.length, 2, 'reply without turn_done is saved exactly once on sleep');
  sent.length = 0; stored.length = 0;
  await box.batLive('Javis câu của phiên A');
  const stale = liveOptions;
  box.tatRanhTay(); box.savedSessionId = 'session-B';
  stale.onReady({session_id:'session-A'}); wakeOptions.onTranscript('Javis câu cũ');
  assert.equal(sent.length, 0); assert.equal(stored.length, 0);
  assert.equal(run('attention.running'), false); assert.equal(button.hidden, true);
  box.handsFree = true; run('attention.start()');
  await box.batLive(); liveOptions.onReady({});
  liveOptions.onTool('ask_javis', 'running'); liveOptions.onTool('ask_javis', 'running');
  liveOptions.onSpeakEnd(); liveOptions.onTurnDone();
  now += 19000; box.tickVoiceFocus();
  now += 2000; box.tickVoiceFocus();
  assert.equal(run('_liveWaitingWake'), false, 'a spoken acknowledgement must not cancel the running tool');
  liveOptions.onTool('ask_javis', 'done');
  for (let i = 0; i < 8; i++) { now += 19000; box.tickVoiceFocus(); }
  assert.equal(run('_liveWaitingWake'), false, 'a legitimate long-running tool is not cancelled by an idle timer');
  now += 19000; box.tickVoiceFocus();
  assert.equal(run('_liveWaitingWake'), false, 'one tool finishing must not clear another');
  liveOptions.onTool('ask_javis', 'done');
  now += 19000; box.tickVoiceFocus(); assert.equal(run('_liveWaitingWake'), false);
  now += 1001; box.tickVoiceFocus(); assert.equal(run('_liveWaitingWake'), true, 'new silent Live sleeps after 20s, not 40s');
  let release;
  captureEnd = new Promise(resolve => { release = resolve; });
  const starts = events.filter(e => e === 'live-start').length;
  const opening = box.batLive('Javis câu đang chờ nhả mic');
  box.tatRanhTay(); release(true); await opening;
  assert.equal(events.filter(e => e === 'live-start').length, starts, 'cancel while waiting for capture release never opens provider');
  console.log('voice focus app: rejects before send/store, Live sleep/wake, duplicate ready, stale handoff pass');
})().catch(e => { console.error(e); process.exitCode = 1; });
