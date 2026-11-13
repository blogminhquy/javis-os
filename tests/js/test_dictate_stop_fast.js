/* Pressing stop answers at once, and the waits after it overlap instead of lining up (2026-11-13).

       node tests/js/test_dictate_stop_fast.js

   Owner, 2026-11-13: "khi ấn tạm dừng nó rất chậm", "phần đang viết lại câu cho đúng nó rất chậm". After stop, three
   waits ran one after the other: the browser closing its recognizer (up to 1.5 seconds, the bar still looking like a
   recording), the recorder stopping and its audio going to POST /stt, then the rewrite. Pins:
   - stop reports "transcribing" in the same tick, once, before the recognizer has closed;
   - on a computer with an ear the recorder is stopped and POST /stt is sent before the recognizer closes, and it is
     sent only once;
   - the ear's text still goes through the rewrite and lands as the final text, then idle;
   - X after stop drops everything;
   - the recording is made at a speech bitrate where the browser records Opus, never on iOS, and a browser that
     refuses the options still records. */
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const tick = () => new Promise(r => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 12; i++) await tick(); };

const PC = { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36" };
const IPHONE = { userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15", platform: "iPhone", maxTouchPoints: 5 };

let runs = [], recorders = [], calls = [], log = [], refuseOptions = false;
class SlowSR {   // the browser closes the run only when the test says so, like Chrome settling its last result
  constructor() { runs.push(this); }
  start() {}
  stop() { this.stopped = true; log.push("sr.stop"); }
  abort() { this.aborted = true; }
  end() { log.push("sr.onend"); this.onend && this.onend(); }
  say(text) { this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal: true })] }); }
}
class Rec {
  constructor(stream, options) {
    if (options && refuseOptions) throw new Error("NotSupportedError");
    this.options = options; this.state = "inactive"; this.mimeType = "audio/webm"; recorders.push(this);
  }
  start() { this.state = "recording"; this.ondataavailable({ data: new Blob([new Uint8Array(4000)]) }); }
  stop() { this.state = "inactive"; log.push("rec.stop"); setTimeout(() => this.onstop && this.onstop(), 0); }
}
Rec.isTypeSupported = t => t === "audio/webm;codecs=opus";
Object.defineProperty(globalThis, "navigator", {
  value: Object.assign({}, PC, { mediaDevices: { getUserMedia: () => Promise.resolve({ getTracks: () => [{ stop() {} }] }) } }),
  configurable: true, writable: true,
});
global.window = { SpeechRecognition: SlowSR };
global.MediaRecorder = Rec;
const json = v => Promise.resolve({ json: () => Promise.resolve(v) });
global.fetch = (url, init) => {
  url = String(url);
  if (url.indexOf("/voice/ear") !== -1) return json({ kind: "upload" });
  if (url.indexOf("/stt/fix") !== -1) { calls.push("fix"); log.push("fix"); return json({ ok: true, text: "Javis OS đã nghe được rồi." }); }
  if (url.indexOf("/stt") !== -1) { calls.push("stt"); log.push("stt"); return json({ ok: true, text: "javis os đã nghe được rồi" }); }
  return json({});
};
function fresh() {
  delete require.cache[require.resolve(path.join(ROOT, "dashboard/dictate.js"))];
  return require(path.join(ROOT, "dashboard/dictate.js"));
}

(async () => {
  // 1. A computer with an ear: Web Speech and the recorder side by side.
  let D = fresh(), states = [], texts = [];
  await D.warm();
  let d = D.create({ onText: (t, f) => texts.push([t, !!f]), onState: s => states.push(s) });
  d.start(); await settle();
  runs[0].say("ravist ô ét đã nghe được rồi");
  check("listening, one recorder", states[states.length - 1] === "listening" && recorders.length === 1);
  log = [];
  d.stop();
  check("stop reports transcribing in the same tick", states[states.length - 1] === "transcribing");
  check("stop stops the recorder at once, without waiting for the recognizer",
    log.indexOf("rec.stop") !== -1 && log.indexOf("sr.onend") === -1);
  await settle();
  check("the recording is on its way to the ear before the recognizer has closed",
    calls.indexOf("stt") !== -1 && log.indexOf("sr.onend") === -1);
  d.start();
  check("a press of the mic while the run is closing does not start a second recording",
    d.busy() === true && runs.length === 1 && recorders.length === 1);
  check("nothing lands before the recognizer has closed", !texts.some(t => t[1]) && states[states.length - 1] === "transcribing");
  runs[0].end(); await settle();
  check("the recording was sent once", calls.filter(c => c === "stt").length === 1);
  check("the ear's text went through the rewrite", calls.filter(c => c === "fix").length === 1 && log.indexOf("stt") < log.indexOf("fix"));
  check("the rewritten sentence is the final text", texts[texts.length - 1][0] === "Javis OS đã nghe được rồi." && texts[texts.length - 1][1]);
  check("transcribing was reported once, then idle",
    states.filter(s => s === "transcribing").length === 1 && states[states.length - 1] === "idle");

  // 2. X after stop: nothing lands.
  runs = []; recorders = []; calls = []; log = [];
  D = fresh(); states = []; texts = [];
  await D.warm();
  d = D.create({ onText: (t, f) => texts.push([t, !!f]), onState: s => states.push(s) });
  d.start(); await settle();
  runs[0].say("bỏ câu này");
  d.stop(); await tick();
  d.cancel(); await settle();
  check("X after stop: idle and no final text", states[states.length - 1] === "idle" && !texts.some(t => t[1]));
  check("X after stop: no rewrite is asked", calls.indexOf("fix") === -1);

  // 3. A new recording after that starts clean.
  runs = []; recorders = []; calls = []; log = [];
  states = []; texts = [];
  d.start(); await settle();
  runs[0].say("câu mới");
  d.stop(); runs[0].end(); await settle();
  check("the next recording runs the whole way again", calls.filter(c => c === "stt").length === 1
    && texts[texts.length - 1][1] && states[states.length - 1] === "idle");

  // 4. The recorder's options.
  const opus = D.recorderOptions(Rec, PC);
  check("Opus browser: recorded as Opus at 32 kbit/s", opus && opus.mimeType === "audio/webm;codecs=opus" && opus.audioBitsPerSecond === 32000);
  check("the recorder of this run was made with those options", recorders[0] && recorders[0].options && recorders[0].options.audioBitsPerSecond === 32000);
  check("iOS: the recorder is made exactly as before", D.recorderOptions(Rec, IPHONE) === undefined);
  check("a browser without Opus recording: as before", D.recorderOptions({ isTypeSupported: () => false }, PC) === undefined);
  check("a browser without isTypeSupported: as before", D.recorderOptions(function () {}, PC) === undefined);
  refuseOptions = true; runs = []; recorders = []; calls = [];
  D = fresh(); states = []; texts = [];
  await D.warm();
  d = D.create({ onText: (t, f) => texts.push([t, !!f]), onState: s => states.push(s) });
  d.start(); await settle();
  check("a browser that refuses the options still records", recorders.length === 1 && recorders[0].options === undefined
    && states[states.length - 1] === "listening");
  d.stop(); runs[0].end(); await settle();
  check("and its recording is still heard", calls.indexOf("stt") !== -1 && states[states.length - 1] === "idle");

  if (fails.length) { console.log("FAIL - test_dictate_stop_fast: " + fails.length); process.exit(1); }
  console.log("OK - test_dictate_stop_fast");
})();
