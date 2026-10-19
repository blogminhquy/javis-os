/* voice-live-worklet.js - microphone capture for Live calls over an API key (0.220.0).

   Runs on the audio rendering thread, not the page's main thread: a busy dashboard (a long chat
   render, a big table) used to stall ScriptProcessorNode and the provider heard gaps in the voice.
   Same output as before: PCM16 mono 16 kHz, one message per 4096 input frames.

   Loaded twice: by AudioWorklet.addModule (registers the processor) and by node tests through
   module.exports (the pure helpers). Neither environment has the other's globals. */
var JAVIS_MIC_BLOCK = 4096, JAVIS_MIC_RATE = 16000;

// Nearest-sample decimation, as voice-live.js did on the main thread.
function javisDownsample(f32, from, to) {
  if (from === to) return f32;
  var ratio = from / to, n = Math.floor(f32.length / ratio), out = new Float32Array(n);
  for (var i = 0; i < n; i++) out[i] = f32[Math.floor(i * ratio)];
  return out;
}

function javisToPcm16(f32) {
  var out = new Int16Array(f32.length);
  for (var i = 0; i < f32.length; i++) {
    var s = Math.max(-1, Math.min(1, f32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return out;
}

if (typeof registerProcessor === "function") {
  class JavisMicProcessor extends AudioWorkletProcessor {
    constructor() {
      super();
      this.buf = new Float32Array(JAVIS_MIC_BLOCK);
      this.n = 0;
      this.alive = true;
      this.port.onmessage = (e) => { if (e.data === "stop") this.alive = false; };
    }

    process(inputs) {
      var ch = inputs[0] && inputs[0][0];
      if (ch) {
        for (var i = 0; i < ch.length; i++) {
          this.buf[this.n++] = ch[i];
          if (this.n === JAVIS_MIC_BLOCK) {
            // `sampleRate` is the AudioWorkletGlobalScope's context rate.
            var pcm = javisToPcm16(javisDownsample(this.buf, sampleRate, JAVIS_MIC_RATE));
            this.port.postMessage(pcm.buffer, [pcm.buffer]);
            this.buf = new Float32Array(JAVIS_MIC_BLOCK);
            this.n = 0;
          }
        }
      }
      return this.alive;
    }
  }
  registerProcessor("javis-mic", JavisMicProcessor);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { downsample: javisDownsample, toPcm16: javisToPcm16, BLOCK: JAVIS_MIC_BLOCK, RATE: JAVIS_MIC_RATE };
}
