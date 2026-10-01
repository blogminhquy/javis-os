// voice-live.js, nhánh WebRTC của ChatGPT Live (0.65.17, docs/dev/2026-10-voice-call-spec.md mục 3.4).
// Khoá: chờ ready rồi mới chọn đường; transport webrtc thì KHÔNG đẩy PCM mà dựng peer connection có
// kênh oai-events, gửi offer, đặt answer; onReady chỉ báo SAU khi bắt tay xong (câu gọi Javis gửi
// trước lúc đó không có phiên nào nhận); lỗi lúc chờ answer báo đúng một lần; tắt mic tắt track;
// khung tool_result tới onToolResult; đường PCM cũ không đổi.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const tick = (ms = 0) => new Promise(r => setTimeout(r, ms));

function setup() {
  const log = { sent: [], peers: [], scriptProcessors: 0, channels: [] };
  class FakeWS {
    constructor(url) { this.url = url; this.readyState = 0; FakeWS.last = this; setTimeout(() => { this.readyState = 1; this.onopen && this.onopen(); }, 0); }
    send(s) { log.sent.push(JSON.parse(s)); }
    close() { this.readyState = 3; }
    serverSend(obj) { this.onmessage && this.onmessage({ data: JSON.stringify(obj) }); }
  }
  FakeWS.OPEN = 1;
  class FakePC {
    constructor() { this.connectionState = 'new'; this.iceGatheringState = 'complete'; this.closed = false; log.peers.push(this); this.track = null; }
    addTransceiver(kind, init) { this.kind = kind; this.direction = init.direction; const pc = this; return { sender: { replaceTrack: async (t) => { pc.track = t; } } }; }
    createDataChannel(name) { log.channels.push(name); return {}; }
    async createOffer() { return { type: 'offer', sdp: 'v=0 offer' }; }
    async setLocalDescription(d) { this.localDescription = d; }
    async setRemoteDescription(d) { this.remoteDescription = d; }
    close() { this.closed = true; }
  }
  const track = { enabled: true, stop() {} };
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
  class AC {
    constructor() { this.sampleRate = 16000; this.currentTime = 0; this.destination = {}; }
    resume() { return Promise.resolve(); }
    close() { return Promise.resolve(); }
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
    createScriptProcessor() { log.scriptProcessors++; return { connect() {}, disconnect() {} }; }
    createAnalyser() { return { fftSize: 512, getFloatTimeDomainData() {}, connect() {} }; }
    createBuffer() { return { getChannelData: () => ({ set() {} }), duration: 0 }; }
  }
  const window = {
    AudioContext: AC,
    location: { protocol: 'http:', host: 'x' },
  };
  const context = {
    window, WebSocket: FakeWS, RTCPeerConnection: FakePC, MediaStream: function () {},
    Audio: function () { this.play = () => Promise.resolve(); this.pause = () => {}; },
    navigator: { mediaDevices: { getUserMedia: async () => stream } },
    location: window.location, setTimeout, clearTimeout, setInterval, clearInterval,
    Float32Array, Int16Array, Promise, JSON, Math, Date, Array, String, console,
  };
  vm.runInNewContext(fs.readFileSync('dashboard/voice-live.js', 'utf8'), context);
  return { live: window.JavisVoiceLive, FakeWS, log, track };
}

function events() {
  const seen = [];
  const opts = {};
  ['onReady', 'onStarted', 'onError', 'onClosed', 'onToolResult', 'onStopped'].forEach(n => {
    opts[n] = (...a) => seen.push([n, ...a]);
  });
  return { opts, seen };
}

test('webrtc: waits for ready, sends offer with oai-events, reports ready only after the answer', async () => {
  const { live, FakeWS, log, track } = setup();
  const { opts, seen } = events();
  const started = live.start(opts);
  await tick(5);
  FakeWS.last.serverSend({ type: 'ready', provider: 'chatgpt', transport: 'webrtc', session_id: 's1' });
  await tick(5);
  const offer = log.sent.find(m => m.type === 'webrtc_offer');
  assert.ok(offer, 'offer sent');
  assert.equal(offer.sdp, 'v=0 offer');
  assert.deepEqual(log.channels, ['oai-events']);
  assert.equal(log.peers.length, 1);
  assert.equal(log.peers[0].track, track, 'mic track goes to the peer connection');
  assert.equal(log.scriptProcessors, 0, 'no PCM capture on the WebRTC path');
  assert.ok(!seen.some(e => e[0] === 'onReady'), 'ready withheld until the handshake finishes');
  FakeWS.last.serverSend({ type: 'webrtc_answer', sdp: 'v=0 answer' });
  assert.equal(await started, true);
  assert.equal(log.peers[0].remoteDescription.sdp, 'v=0 answer');
  const order = seen.map(e => e[0]);
  assert.ok(order.indexOf('onStarted') < order.indexOf('onReady'));
  assert.equal(live.transport(), 'webrtc');
  assert.equal(JSON.stringify(live.progress()), JSON.stringify({ played: 1, total: 1 }));

  live.setMuted(true);
  assert.equal(track.enabled, false, 'mute disables the mic track');
  live.setMuted(false);
  assert.equal(track.enabled, true);

  FakeWS.last.serverSend({ type: 'tool_result', name: 'ask_javis', text: '## Doanh thu\n12 triệu' });
  assert.deepEqual(seen.find(e => e[0] === 'onToolResult'), ['onToolResult', 'ask_javis', '## Doanh thu\n12 triệu']);

  live.stop();
  assert.equal(log.peers[0].closed, true, 'stop closes the peer connection');
  assert.equal(live.transport(), 'pcm');
});

test('webrtc: a server error while waiting for the answer is reported once and closes', async () => {
  const { live, FakeWS } = setup();
  const { opts, seen } = events();
  const started = live.start(opts);
  await tick(5);
  FakeWS.last.serverSend({ type: 'ready', transport: 'webrtc' });
  await tick(5);
  FakeWS.last.serverSend({ type: 'error', message: 'ChatGPT Live không mở được: thread does not support realtime' });
  assert.equal(await started, false);
  const errors = seen.filter(e => e[0] === 'onError');
  assert.equal(errors.length, 1, 'exactly one error');
  assert.match(errors[0][1], /ChatGPT Live/);
  assert.ok(seen.some(e => e[0] === 'onClosed'));
});

test('pcm providers keep the old path: ScriptProcessor, no peer connection, ready forwarded', async () => {
  const { live, FakeWS, log } = setup();
  const { opts, seen } = events();
  const started = live.start(opts);
  await tick(5);
  FakeWS.last.serverSend({ type: 'ready', provider: 'gemini', transport: 'pcm' });
  assert.equal(await started, true);
  assert.equal(log.scriptProcessors, 1);
  assert.equal(log.peers.length, 0);
  assert.ok(seen.some(e => e[0] === 'onReady'));
  assert.equal(live.transport(), 'pcm');
  live.stop();
});

// 0.65.24: nối sớm lúc người dùng còn đang nói câu đánh thức: bắt tay xong mà CHƯA giữ mic (bộ nghe
// của trình duyệt còn giữ mic, điện thoại chỉ cho một bên), mic gắn sau bằng attachMic.
test('webrtc deferMic: handshake without the mic, attachMic adds it to the same peer', async () => {
  const { live, FakeWS, log, track } = setup();
  let mics = 0;
  const { opts, seen } = events();
  const started = live.start(Object.assign(opts, { deferMic: true }));
  await tick(5);
  FakeWS.last.serverSend({ type: 'ready', provider: 'chatgpt', transport: 'webrtc' });
  await tick(5);
  assert.equal(log.peers.length, 1);
  assert.equal(log.peers[0].track, null, 'no mic track during the early handshake');
  assert.equal(live.hasMic(), false);
  FakeWS.last.serverSend({ type: 'webrtc_answer', sdp: 'v=0 answer' });
  assert.equal(await started, true);
  assert.ok(seen.some(e => e[0] === 'onReady'), 'the call is ready before the mic joins');
  assert.equal(await live.attachMic(), true);
  assert.equal(log.peers[0].track, track, 'mic joins the existing peer, no second handshake');
  assert.equal(log.peers.length, 1);
  assert.equal(live.hasMic(), true);
  assert.equal(await live.attachMic(), true, 'a second attach is a no-op');
  live.setMuted(true);
  assert.equal(track.enabled, false, 'mute still works after a late attach');
  live.stop();
});

test('pcm deferMic: ready without capture, attachMic starts the ScriptProcessor', async () => {
  const { live, FakeWS, log } = setup();
  const { opts } = events();
  const started = live.start(Object.assign(opts, { deferMic: true }));
  await tick(5);
  FakeWS.last.serverSend({ type: 'ready', provider: 'gemini', transport: 'pcm' });
  assert.equal(await started, true);
  assert.equal(log.scriptProcessors, 0, 'no capture before attachMic');
  assert.equal(await live.attachMic(), true);
  assert.equal(log.scriptProcessors, 1);
  live.stop();
});

(async () => {
  let failures = 0;
  for (const [name, fn] of tests) {
    try { await fn(); console.log('ok', name); }
    catch (error) { failures++; console.error('FAIL', name, error.message); }
  }
  if (failures) process.exitCode = 1;
  else console.log('OK - voice-live WebRTC');
})();
