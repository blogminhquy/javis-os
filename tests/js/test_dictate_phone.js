/* The composer mic on a PHONE uses one mic capture only (0.339.0).

       node tests/js/test_dictate_phone.js

   Owner report 2026-10-26 (iPhone, Javis installed as an app): press the mic, the timer runs, the meter stays flat
   and no word ever reaches the box. A phone lets only one thing capture the mic (voice.js learned that in 0.59.35),
   and dictate.js opened the recorder and the level meter next to Web Speech, so both went deaf. These cases pin the
   rule: with an upload ear a phone records only, without one it runs Web Speech only, and a run that hears nothing
   says so instead of closing in silence. A computer keeps running both. */
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const tick = () => new Promise(r => setTimeout(r, 0));

const IPHONE = { userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15", platform: "iPhone", maxTouchPoints: 5 };
const IPAD = { userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15", platform: "MacIntel", maxTouchPoints: 5 };
const ANDROID = { userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130 Mobile", platform: "Linux armv8l", maxTouchPoints: 5 };
const MAC = { userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130", platform: "MacIntel", maxTouchPoints: 0 };

// ───────── fakes ─────────
let runs = [], mics = [], recorders = [], ear = "upload", sttText = "chào Javis";
class FakeSR {
  constructor() { runs.push(this); }
  start() {}
  stop() { Promise.resolve().then(() => this.onend && this.onend()); }
  abort() { Promise.resolve().then(() => this.onend && this.onend()); }
  say(text, final) { this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal: !!final })] }); }
}
class FakeRecorder {
  constructor(stream) { this.stream = stream; this.state = "inactive"; this.mimeType = "audio/mp4"; recorders.push(this); }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    Promise.resolve().then(() => {
      this.ondataavailable && this.ondataavailable({ data: new Blob([new Uint8Array(4000)]) });
      this.onstop && this.onstop();
    });
  }
}
function setNav(nav) {
  Object.defineProperty(globalThis, "navigator", {
    value: Object.assign({}, nav, { mediaDevices: { getUserMedia: () => {
      const track = { stop() { this.stopped = true; } };
      const s = { getTracks: () => [track] };
      mics.push(s);
      return Promise.resolve(s);
    } } }),
    configurable: true, writable: true,
  });
}
global.window = { SpeechRecognition: FakeSR };
global.MediaRecorder = FakeRecorder;
global.fetch = (url) => Promise.resolve({ json: () => Promise.resolve(
  String(url).indexOf("/voice/ear") !== -1 ? { kind: ear } : { ok: true, text: sttText }) });
setNav(MAC);
const D = require(path.join(ROOT, "dashboard/dictate.js"));

// ───────── pure plan ─────────
const P = (o) => D.plan(Object.assign({ speech: true, mediaRecorder: true, wantMeter: true }, o));
let p = P({ phone: true, ear: "upload" });
check("phone with an upload ear: record only, meter on, no Web Speech", p.record && p.meter && !p.speech);
p = P({ phone: true, ear: "" });
check("phone without an ear: Web Speech only, no recorder, no meter", p.speech && !p.record && !p.meter);
p = P({ phone: true, ear: "upload", mediaRecorder: false });
check("phone with an ear but no MediaRecorder: Web Speech only", p.speech && !p.record && !p.meter);
p = P({ phone: false, ear: "upload" });
check("computer: Web Speech, recorder and meter side by side, as before", p.speech && p.record && p.meter);
p = P({ phone: true, ear: "", speech: false });
check("phone with neither: nothing runs (the caller reports unsupported)", !p.speech && !p.record);
check("iPhone, iPad (as a touch Mac) and Android are phones; a Mac is not",
  D.isPhone(IPHONE) && D.isPhone(IPAD) && D.isPhone(ANDROID) && !D.isPhone(MAC));
check("only Apple touch devices count as iOS", D.isIOS(IPHONE) && D.isIOS(IPAD) && !D.isIOS(ANDROID) && !D.isIOS(MAC));

function reset(nav, earKind) {
  runs = []; mics = []; recorders = []; ear = earKind;
  setNav(nav);
}
// dictate.js caches the ear answer for a minute; every case below asks again by waiting it out in a fresh module.
function fresh() {
  delete require.cache[require.resolve(path.join(ROOT, "dashboard/dictate.js"))];
  return require(path.join(ROOT, "dashboard/dictate.js"));
}

(async () => {
  // iPhone with an upload ear: no Web Speech at all, the recorder holds the mic, text arrives on stop.
  reset(IPHONE, "upload");
  let Dx = fresh(), texts = [], states = [], errors = [], streams = [];
  await Dx.warm();   // 0.419.0: a page asks the ear on load, before any press
  let d = Dx.create({ onText: (t, f) => texts.push([t, f]), onState: s => states.push(s), onError: c => errors.push(c),
    onStream: s => streams.push(s) });
  d.start(); await tick(); await tick();
  check("iPhone + ear: listening", states[states.length - 1] === "listening");
  check("iPhone + ear: Web Speech never starts (it would fight the recorder for the mic)", runs.length === 0);
  check("iPhone + ear: one mic capture, recording", mics.length === 1 && recorders.length === 1 && recorders[0].state === "recording");
  check("iPhone + ear: the meter gets that same stream", streams.length === 1 && streams[0] === mics[0]);
  d.stop(); for (let i = 0; i < 6; i++) await tick();
  check("iPhone + ear: stop transcribes, then the ear's text lands as final",
    states.indexOf("transcribing") !== -1 && texts.length === 1 && texts[0][0] === "chào Javis" && texts[0][1] === true);
  check("iPhone + ear: ends idle, mic released, no error", states[states.length - 1] === "idle"
    && mics[0].getTracks()[0].stopped === true && errors.length === 0);

  // iPhone without an ear: Web Speech alone, nothing else touches the mic, runs are not continuous.
  reset(IPHONE, "");
  Dx = fresh(); texts = []; states = []; streams = []; errors = [];
  await Dx.warm();
  d = Dx.create({ onText: t => texts.push(t), onState: s => states.push(s), onError: c => errors.push(c), onStream: s => streams.push(s) });
  d.start(); await tick(); await tick();
  check("iPhone, no ear: Web Speech runs", runs.length === 1 && states[states.length - 1] === "listening");
  check("iPhone, no ear: no getUserMedia, so the recognizer keeps the mic", mics.length === 0 && streams.length === 0);
  check("iPhone: one utterance per run (continuous runs never yield text on iOS)", runs[0].continuous === false);
  runs[0].say("một", true); runs[0].onend();
  check("iPhone: the next run starts by itself and keeps the words", runs.length === 2 && d.active());
  runs[1].say("hai", true);
  check("iPhone: words of both runs are joined", texts[texts.length - 1] === "một hai");
  d.stop(); await tick(); await tick();
  check("iPhone, no ear: stop ends idle with no error", states[states.length - 1] === "idle" && errors.length === 0);

  // iPhone, no ear, nothing heard: say so instead of closing the bar in silence.
  reset(IPHONE, "");
  Dx = fresh(); states = []; errors = [];
  await Dx.warm();
  d = Dx.create({ onState: s => states.push(s), onError: c => errors.push(c) });
  d.start(); await tick(); await tick();
  d.stop(); await tick(); await tick();
  check("nothing heard: the owner is told (error 'nothing')", errors.indexOf("nothing") !== -1 && states[states.length - 1] === "idle");

  // A real error (mic blocked) is not covered up by a second "nothing heard" note.
  reset(IPHONE, "");
  Dx = fresh(); errors = [];
  await Dx.warm();
  d = Dx.create({ onError: c => errors.push(c) });
  d.start(); await tick(); await tick();
  runs[0].onerror({ error: "not-allowed" }); runs[0].onend(); await tick();
  check("mic blocked: only 'denied' is reported", errors.join(",") === "denied");

  // iPhone + ear, the ear hears nothing either.
  reset(IPHONE, "upload"); sttText = "";
  Dx = fresh(); errors = []; texts = [];
  await Dx.warm();
  d = Dx.create({ onText: t => texts.push(t), onError: c => errors.push(c) });
  d.start(); await tick(); await tick();
  d.stop(); for (let i = 0; i < 6; i++) await tick();
  check("ear returned no words: error 'nothing', no empty text", errors.indexOf("nothing") !== -1 && texts.length === 0);
  sttText = "chào Javis";

  // Android behaves as a phone too.
  reset(ANDROID, "upload");
  Dx = fresh();
  await Dx.warm();
  d = Dx.create({});
  d.start(); await tick(); await tick();
  check("Android + ear: record only, no Web Speech", runs.length === 0 && recorders.length === 1);
  d.cancel(); await tick();

  // A computer is unchanged: Web Speech for live text plus the recorder for the ear.
  reset(MAC, "upload");
  Dx = fresh();
  await Dx.warm();
  d = Dx.create({ onStream: () => {} });
  d.start(); await tick(); await tick();
  check("computer + ear: Web Speech and recorder side by side (live text, then the ear)", runs.length === 1 && recorders.length === 1);
  check("computer: continuous runs as before", runs[0].continuous === true);
  d.cancel(); await tick();

  if (fails.length) { console.log("\nFAIL - test_dictate_phone: " + fails.length); process.exit(1); }
  console.log("\nOK - test_dictate_phone: all pass");
})();
