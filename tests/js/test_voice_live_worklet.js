// Live mic capture on an AudioWorklet (dashboard/voice-live-worklet.js, 0.220.0). No real audio.
//
//     node tests/js/test_voice_live_worklet.js
//
// Locks: the pure conversion gives PCM16 16 kHz with the same block size as before; voice-live.js
// captures through the worklet when the browser has one and the module loads, and falls back to
// ScriptProcessorNode when it does not (old Safari) or when addModule fails (a proxy blocking the file).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const W = require('../../dashboard/voice-live-worklet.js');
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const tick = (ms = 0) => new Promise(r => setTimeout(r, ms));

test('downsample 48 kHz -> 16 kHz keeps every third sample', () => {
  const src = new Float32Array([0, 1, 2, 3, 4, 5, 6, 7, 8]);
  assert.deepEqual(Array.from(W.downsample(src, 48000, 16000)), [0, 3, 6]);
  assert.equal(W.downsample(src, 16000, 16000), src);
});

test('toPcm16 clamps and scales', () => {
  assert.deepEqual(Array.from(W.toPcm16(new Float32Array([0, 1, -1, 2, -2, 0.5]))), [0, 32767, -32768, 32767, -32768, 16383]);
  assert.equal(W.BLOCK, 4096);
  assert.equal(W.RATE, 16000);
});

function setup({ worklet, addModuleFails = false }) {
  const log = { scriptProcessors: 0, workletNodes: [], modules: [], sent: [] };
  class FakeWS {
    constructor(url) { this.url = url; this.readyState = 0; FakeWS.last = this; setTimeout(() => { this.readyState = 1; this.onopen && this.onopen(); }, 0); }
    send(s) { log.sent.push(s); }
    close() { this.readyState = 3; }
    serverSend(obj) { this.onmessage && this.onmessage({ data: JSON.stringify(obj) }); }
  }
  FakeWS.OPEN = 1;
  const track = { enabled: true, stop() {} };
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
  class AC {
    constructor() {
      this.sampleRate = 16000; this.currentTime = 0; this.destination = {};
      if (worklet) this.audioWorklet = { addModule: async (url) => { log.modules.push(url); if (addModuleFails) throw new Error('blocked'); } };
    }
    resume() { return Promise.resolve(); }
    close() { return Promise.resolve(); }
    createMediaStreamSource() { return { connect(n) { this.to = n; }, disconnect() {} }; }
    createScriptProcessor() { log.scriptProcessors++; return { connect() {}, disconnect() {} }; }
    createBuffer() { return { getChannelData: () => ({ set() {} }), duration: 0 }; }
  }
  class FakeNode {
    constructor(ctx, name, opts) { this.name = name; this.opts = opts; this.posted = []; const self = this; this.port = { postMessage: (m) => self.posted.push(m), onmessage: null }; log.workletNodes.push(this); }
    disconnect() { this.disconnected = true; }
  }
  const window = { AudioContext: AC, location: { protocol: 'http:', host: 'x' } };
  if (worklet) window.AudioWorkletNode = FakeNode;
  const context = {
    window, WebSocket: FakeWS, navigator: { mediaDevices: { getUserMedia: async () => stream } },
    location: window.location, setTimeout, clearTimeout, setInterval, clearInterval,
    Float32Array, Int16Array, ArrayBuffer, Promise, JSON, Math, Date, Array, String, console,
  };
  vm.runInNewContext(fs.readFileSync('dashboard/voice-live.js', 'utf8'), context);
  return { live: window.JavisVoiceLive, FakeWS, log };
}

async function startPcm(h) {
  const p = h.live.start({});
  await tick(5);
  h.FakeWS.last.serverSend({ type: 'ready', provider: 'gemini', transport: 'pcm', session_id: 's1' });
  return p;
}

test('worklet available: capture runs on the worklet and its frames go to the socket', async () => {
  const h = setup({ worklet: true });
  assert.equal(await startPcm(h), true);
  assert.equal(h.log.scriptProcessors, 0);
  assert.equal(h.log.workletNodes.length, 1);
  const node = h.log.workletNodes[0];
  assert.equal(node.name, 'javis-mic');
  assert.ok(h.log.modules[0].startsWith('/static/voice-live-worklet.js'));
  const frame = new Int16Array([1, 2, 3]).buffer;
  node.port.onmessage({ data: frame });
  assert.ok(h.log.sent.includes(frame), 'the PCM frame is sent as is');
  h.live.stop();
  assert.ok(node.posted.includes('stop') && node.disconnected, 'stop tells the processor to end');
});

test('no AudioWorklet: falls back to ScriptProcessorNode', async () => {
  const h = setup({ worklet: false });
  assert.equal(await startPcm(h), true);
  assert.equal(h.log.scriptProcessors, 1);
  h.live.stop();
});

test('worklet module fails to load: falls back to ScriptProcessorNode', async () => {
  const h = setup({ worklet: true, addModuleFails: true });
  assert.equal(await startPcm(h), true);
  assert.equal(h.log.workletNodes.length, 0);
  assert.equal(h.log.scriptProcessors, 1);
  h.live.stop();
});

(async () => {
  let failed = 0;
  for (const [name, fn] of tests) {
    try { await fn(); console.log('ok   ' + name); } catch (e) { failed++; console.log('FAIL ' + name + '\n  ' + (e && e.stack || e)); }
  }
  if (failed) { console.log(`\nFAIL: ${failed}`); process.exit(1); }
  console.log('\nOK - voice-live worklet');
})();
