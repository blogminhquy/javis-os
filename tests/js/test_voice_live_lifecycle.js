/* Exercise the real Live controller with deterministic browser boundaries. No microphone/network. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../../dashboard/voice-live.js'), 'utf8');
const tick = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };

function harness() {
  const requests = [], sockets = [], contexts = [], timers = new Map(), events = [];
  let timerId = 0;
  class AudioContext {
    constructor(options = {}) { this.sampleRate = options.sampleRate || 48000; this.destination = {}; this.currentTime = 0; contexts.push(this); }
    resume() { return Promise.resolve(); }
    close() { this.closed = true; this.state = 'closed'; return Promise.resolve(); }
    suspend() { this.suspended = true; return Promise.resolve(); }
    createMediaStreamSource() { return {connect() {}, disconnect() {}}; }
    createScriptProcessor() { return {connect() {}, disconnect() {}}; }
    createBuffer(_, length, rate) { return {duration: length / rate, getChannelData: () => new Float32Array(length)}; }
    createBufferSource() { return {connect() {}, start() {}, stop() {}}; }
  }
  class WebSocket {
    static OPEN = 1;
    constructor(url) { this.url = url; this.readyState = 0; this.sent = []; sockets.push(this); }
    send(data) { this.sent.push(data); }
    close() { this.readyState = 3; }
    open() { this.readyState = 1; if (this.onopen) this.onopen({}); }
    end() { this.readyState = 3; if (this.onclose) this.onclose({}); }
  }
  const box = {window: {AudioContext}, navigator: {mediaDevices: {getUserMedia: () => new Promise((resolve, reject) => requests.push({resolve, reject}))}},
    location: {protocol: 'http:', host: 'localhost'}, WebSocket, ArrayBuffer, Int16Array, Float32Array,
    setTimeout(fn, delay) { const id = ++timerId; timers.set(id, {fn, delay}); return id; },
    clearTimeout(id) { timers.delete(id); }, setInterval() { return 0; }, clearInterval() {}};
  vm.runInNewContext(source, box);
  function options(tag = '') { return Object.fromEntries(['onStarted', 'onStopped', 'onClosed', 'onError', 'onTranscript'].map(name => [name, (...args) => events.push([tag + name, ...args])])); }
  function microphone() { const track = {stopped: false, stop() { this.stopped = true; }}; return {track, getTracks: () => [track]}; }
  // The server sends `ready` once the provider is up; without it start() waits 25 s (a fake timer here), so the old
  // harness never got past its first case and node exited quietly with code 0 (fixed 0.339.0).
  async function connect(tag = '') { const promise = box.window.JavisVoiceLive.start(options(tag)); const mic = microphone(); requests.at(-1).resolve(mic); await tick(); sockets.at(-1).open(); await tick(); sockets.at(-1).onmessage({data: JSON.stringify({type: 'ready'})}); assert.equal(await promise, true); return mic; }
  return {api: box.window.JavisVoiceLive, options, microphone, requests, sockets, contexts, timers, events, connect};
}

const cases = [
  ['interruption after provider turn_done reports audio actually played', async () => {
    const h = harness(); await h.connect();
    const socket = h.sockets[0], output = h.contexts[1];
    socket.onmessage({data: new Int16Array(24000).buffer});
    output.currentTime = 0.42;
    socket.onmessage({data: JSON.stringify({type: 'turn_done'})});
    socket.onmessage({data: JSON.stringify({type: 'interrupted'})});
    assert.equal(JSON.parse(socket.sent.at(-1)).ms, 400); h.api.stop();
  }],
  ['played time is capped at available audio after playback ends', async () => {
    const h = harness(); await h.connect();
    h.sockets[0].onmessage({data: new Int16Array(24000).buffer});
    h.contexts[1].currentTime = 9;
    assert.equal(h.api.playedMs(), 1000); h.api.stop();
  }],
  ['playback marker advances to the next provider turn', async () => {
    const h = harness(); await h.connect();
    const socket = h.sockets[0], output = h.contexts[1];
    socket.onmessage({data: new Int16Array(24000).buffer});
    socket.onmessage({data: JSON.stringify({type: 'turn_done'})});
    output.currentTime = 2;
    socket.onmessage({data: new Int16Array(24000).buffer}); output.currentTime = 2.22;
    assert.equal(h.api.playedMs(), 200); h.api.stop();
  }],
  ['chosen recognition language reaches the Live websocket query', async () => {
    for (const [setting, want] of [[undefined, 'vi-VN'], ['en-US', 'en-US'], [() => 'auto', 'auto']]) {
      const h = harness(), promise = h.api.start({...h.options(), language: setting});
      h.requests[0].resolve(h.microphone()); await tick();
      assert.equal(new URL(h.sockets[0].url).searchParams.get('lang'), want);
      h.sockets[0].open(); await tick(); h.sockets[0].onmessage({data: JSON.stringify({type: 'ready'})}); await promise; h.api.stop();
    }
  }],
  ['stop during mic permission releases the eventual stream and never opens a socket', async () => {
    const h = harness(), promise = h.api.start(h.options()); h.api.stop();
    const mic = h.microphone(); h.requests[0].resolve(mic); await tick();
    // Let an incorrectly created socket finish so the test reports the behavioral failure.
    if (h.sockets[0]) h.sockets[0].open();
    assert.equal(await promise, false); assert.equal(mic.track.stopped, true); assert.equal(h.sockets.length, 0);
    // 0.339.0: stop() suspends the call's contexts (kept for the next session); release() closes them.
    assert.equal(h.contexts.every(c => c.suspended && !c.closed), true);
  }],
  ['a stale permission rejection cannot stop a restarted session', async () => {
    const h = harness(), old = h.api.start(h.options('old:')); h.api.stop();
    await h.connect('new:'); h.requests[0].reject({name: 'NotAllowedError'}); await old;
    assert.equal(h.api.isOn(), true); assert.equal(h.events.some(e => e[0] === 'new:onError'), false); h.api.stop();
  }],
  ['stop while websocket connects resolves start without waiting for timeout', async () => {
    const h = harness(); let result;
    h.api.start(h.options()).then(v => { result = v; }, e => { result = e; });
    const mic = h.microphone(); h.requests[0].resolve(mic); await tick(); h.api.stop(); await tick();
    // The 1 s cap on resume() is a harmless race timer; what must be gone is the 4 s open timeout.
    assert.equal(result, false); assert.equal(mic.track.stopped, true);
    assert.equal([...h.timers.values()].filter(t => t.delay !== 1000).length, 0);
  }],
  ['websocket close before open fails startup and releases audio', async () => {
    const h = harness(); let result;
    h.api.start(h.options()).then(v => { result = v; }, e => { result = e; });
    const mic = h.microphone(); h.requests[0].resolve(mic); await tick(); h.sockets[0].end(); await tick();
    assert.equal(result, false); assert.equal(mic.track.stopped, true); assert.equal(h.contexts.every(c => c.suspended), true);
    assert.equal(h.events.some(e => e[0] === 'onStarted'), false);
  }],
  ['websocket connection timeout fails rather than pretending capture started', async () => {
    const h = harness(), promise = h.api.start(h.options());
    const mic = h.microphone(); h.requests[0].resolve(mic); await tick();
    [...h.timers.values()].find(t => t.delay === 4000).fn();
    assert.equal(await promise, false); assert.equal(h.api.isOn(), false); assert.equal(mic.track.stopped, true);
  }],
  ['websocket error releases an active microphone and closes the session', async () => {
    const h = harness(), mic = await h.connect(); h.sockets[0].onerror({}); await tick();
    assert.equal(h.api.isOn(), false); assert.equal(mic.track.stopped, true);
    assert.equal(h.events.filter(e => e[0] === 'onClosed').length, 1);
  }],
  ['callbacks queued by the old websocket cannot affect the new session', async () => {
    const h = harness(); await h.connect('old:');
    const oldClose = h.sockets[0].onclose, oldMessage = h.sockets[0].onmessage;
    h.api.stop(); await h.connect('new:');
    oldMessage({data: JSON.stringify({type: 'transcript', role: 'user', text: 'synthetic', final: true})}); oldClose({});
    assert.equal(h.api.isOn(), true); assert.equal(h.events.some(e => e[0] === 'new:onTranscript'), false); h.api.stop();
  }],
  ['concurrent start calls share a single microphone request', async () => {
    const h = harness(), first = h.api.start(h.options()), second = h.api.start(h.options());
    assert.equal(h.requests.length, 1);
    h.requests[0].resolve(h.microphone()); await tick(); h.sockets[0].open(); await tick();
    h.sockets[0].onmessage({data: JSON.stringify({type: 'ready'})});
    assert.equal(await first, true); assert.equal(await second, true); h.api.stop();
  }],
  // 0.339.0, owner report 2026-10-26: after the call waited (provider closed after 30 quiet seconds) the reopened
  // session had no sound on an iPhone, because it made NEW audio contexts outside any press. One set per call now.
  ['the next session of the same call reuses the contexts a press unlocked', async () => {
    const h = harness();
    h.api.unlock();
    assert.equal(h.contexts.length, 2, 'unlock makes both contexts inside the press');
    await h.connect('first:'); h.api.stop();
    assert.equal(h.contexts.every(c => c.suspended && !c.closed), true, 'the wait suspends, never closes');
    await h.connect('second:');
    assert.equal(h.contexts.length, 2, 'reopening after the wait makes no new context');
    assert.equal(h.api.isOn(), true); h.api.stop();
  }],
  ['hang-up releases the contexts and the next call makes fresh ones', async () => {
    const h = harness(); await h.connect(); h.api.release();
    assert.equal(h.contexts.every(c => c.closed), true);
    assert.equal(h.events.filter(e => e[0] === 'onStopped').length, 1, 'release after stop does not stop twice');
    await h.connect(); assert.equal(h.contexts.length, 4); h.api.release();
  }],
  ['release after tatLive already stopped emits no second onStopped', async () => {
    const h = harness(); await h.connect(); h.api.stop(); h.api.release();
    assert.equal(h.events.filter(e => e[0] === 'onStopped').length, 1);
    assert.equal(h.contexts.every(c => c.closed), true);
  }],
];
let ran = 0;
// A case that awaits a promise nothing will settle empties the event loop and node exits with code 0, silently: that
// is how this file stayed green while running none of its cases. Count them, and fail when one never finished.
process.on('exit', () => {
  if (ran < cases.length) { console.error(`FAIL only ${ran} of ${cases.length} cases finished (one hung)`); process.exitCode = 1; }
});
(async () => {
  let failed = 0;
  for (const [name, test] of cases) { try { await test(); console.log('ok   ' + name); } catch (e) { failed++; console.error('FAIL ' + name + ': ' + e.message); } ran++; }
  if (failed) process.exitCode = 1;
})();
