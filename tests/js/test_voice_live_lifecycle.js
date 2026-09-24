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
    close() { this.closed = true; return Promise.resolve(); }
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
    clearTimeout(id) { timers.delete(id); }};
  vm.runInNewContext(source, box);
  function options(tag = '') { return Object.fromEntries(['onStarted', 'onStopped', 'onClosed', 'onError', 'onTranscript'].map(name => [name, (...args) => events.push([tag + name, ...args])])); }
  function microphone() { const track = {stopped: false, stop() { this.stopped = true; }}; return {track, getTracks: () => [track]}; }
  async function connect(tag = '') { const promise = box.window.JavisVoiceLive.start(options(tag)); const mic = microphone(); requests.at(-1).resolve(mic); await tick(); sockets.at(-1).open(); assert.equal(await promise, true); return mic; }
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
      h.sockets[0].open(); await promise; h.api.stop();
    }
  }],
  ['stop during mic permission releases the eventual stream and never opens a socket', async () => {
    const h = harness(), promise = h.api.start(h.options()); h.api.stop();
    const mic = h.microphone(); h.requests[0].resolve(mic); await tick();
    // Let an incorrectly created socket finish so the test reports the behavioral failure.
    if (h.sockets[0]) h.sockets[0].open();
    assert.equal(await promise, false); assert.equal(mic.track.stopped, true); assert.equal(h.sockets.length, 0);
    assert.equal(h.contexts.every(c => c.closed), true);
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
    assert.equal(result, false); assert.equal(mic.track.stopped, true); assert.equal(h.timers.size, 0);
  }],
  ['websocket close before open fails startup and releases audio', async () => {
    const h = harness(); let result;
    h.api.start(h.options()).then(v => { result = v; }, e => { result = e; });
    const mic = h.microphone(); h.requests[0].resolve(mic); await tick(); h.sockets[0].end(); await tick();
    assert.equal(result, false); assert.equal(mic.track.stopped, true); assert.equal(h.contexts.every(c => c.closed), true);
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
    h.requests[0].resolve(h.microphone()); await tick(); h.sockets[0].open();
    assert.equal(await first, true); assert.equal(await second, true); h.api.stop();
  }],
];
(async () => {
  let failed = 0;
  for (const [name, test] of cases) { try { await test(); console.log('ok   ' + name); } catch (e) { failed++; console.error('FAIL ' + name + ': ' + e.message); } }
  if (failed) process.exitCode = 1;
})();
