/* Stop and X always close the dictation bar on a phone (0.409.0).

       node tests/js/test_dictate_dung_va_huy.js

   Owner report 2026-10-30 (iPhone, screenshot): the mic started fine, then neither the stop square nor X did anything
   and the timer ran on. Two causes, both pinned here:
   1. Waits with no end. A browser that never answers rec.stop() with onend, a MediaRecorder that never fires onstop
      or a /stt call that hangs left the run waiting forever, and stop only worked while the run was still `on`.
   2. The iOS keyboard trap. Stop focused the text box (keyboard up), the next recording made the focused box
      read-only, iOS dropped the keyboard but kept the page slid up, and on that page taps on X and stop landed on the
      box. On a touch screen the box now lets go of the focus while recording, and mobile-chat.js slides the page back
      when the keyboard goes down even with something still focused. */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const tick = () => new Promise(r => setTimeout(r, 0));
const wait = ms => new Promise(r => setTimeout(r, ms));

const IPHONE = { userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15", platform: "iPhone", maxTouchPoints: 5 };

// ───────── fakes: a browser that never answers ─────────
let runs = [], recorders = [], ear = "", sttHangs = false;
class DeafSR {   // stop() never leads to onend, like the iPhone in the report
  constructor() { runs.push(this); }
  start() {}
  stop() { this.stopped = true; }
  abort() { this.aborted = true; }
  say(text) { this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal: false })] }); }
}
class MuteRecorder {   // stop() never leads to onstop
  constructor() { this.state = "inactive"; this.mimeType = "audio/mp4"; recorders.push(this); }
  start() { this.state = "recording"; this.ondataavailable && this.ondataavailable({ data: new Blob([new Uint8Array(4000)]) }); }
  stop() { this.state = "inactive"; }
}
Object.defineProperty(globalThis, "navigator", {
  value: Object.assign({}, IPHONE, { mediaDevices: { getUserMedia: () => Promise.resolve({ getTracks: () => [{ stop() {} }] }) } }),
  configurable: true, writable: true,
});
global.window = { SpeechRecognition: DeafSR };
global.MediaRecorder = MuteRecorder;
global.fetch = (url) => String(url).indexOf("/voice/ear") !== -1
  ? Promise.resolve({ json: () => Promise.resolve({ kind: ear }) })
  : (sttHangs ? new Promise(() => {}) : Promise.resolve({ json: () => Promise.resolve({ ok: true, text: "chữ Groq" }) }));
function fresh() {
  delete require.cache[require.resolve(path.join(ROOT, "dashboard/dictate.js"))];
  return require(path.join(ROOT, "dashboard/dictate.js"));
}

(async () => {
  // 1. Web Speech only (phone without an ear), the browser never ends the run after stop.
  ear = ""; runs = [];
  let D = fresh(), states = [], texts = [];
  await D.warm();   // 0.419.0: a page asks the ear on load, before any press
  let d = D.create({ onText: t => texts.push(t), onState: s => states.push(s) });
  d.start(); await tick(); await tick();
  runs[0].say("xin chào");
  d.stop(); await tick();
  check("Web Speech: right after stop the run still waits for the browser", states[states.length - 1] === "listening");
  await wait(1700);
  check("Web Speech: with no onend the run ends by itself, idle, the words kept",
    states[states.length - 1] === "idle" && texts[texts.length - 1] === "xin chào" && runs[0].aborted === true);

  // 1b. A second press of stop does not wait for the watchdog.
  runs = []; states = [];
  D = fresh();
  await D.warm();
  d = D.create({ onState: s => states.push(s) });
  d.start(); await tick(); await tick();
  runs[0].say("một");
  d.stop(); d.stop(); await tick();
  check("a second stop while the browser still owes onend ends the run at once", states[states.length - 1] === "idle");

  // 2. Recorder (phone with an upload ear) that never fires onstop: stop still transcribes what was recorded.
  ear = "upload"; recorders = []; states = []; texts = [];
  D = fresh();
  await D.warm();
  d = D.create({ onText: t => texts.push(t), onState: s => states.push(s), onStream: () => {} });
  d.start(); for (let i = 0; i < 4; i++) await tick();
  check("recorder: listening with the recorder holding the mic", states[states.length - 1] === "listening" && recorders.length === 1);
  d.stop(); await tick();
  check("recorder: stop goes to transcribing", states[states.length - 1] === "transcribing");
  await wait(1700);
  check("recorder: with no onstop the recording is still sent and its text lands",
    states[states.length - 1] === "idle" && texts[texts.length - 1] === "chữ Groq");

  // 3. /stt hangs: X closes the bar at once and the late text never lands.
  sttHangs = true; recorders = []; states = []; texts = [];
  D = fresh();
  await D.warm();
  d = D.create({ onText: t => texts.push(t), onState: s => states.push(s), onStream: () => {} });
  d.start(); for (let i = 0; i < 4; i++) await tick();
  d.stop();
  await wait(1700);
  check("hanging /stt: still transcribing", states[states.length - 1] === "transcribing");
  d.cancel(); await tick();
  check("hanging /stt: X closes the bar right away", states[states.length - 1] === "idle" && texts.length === 0);

  const dictSrc = fs.readFileSync(path.join(ROOT, "dashboard/dictate.js"), "utf8");
  check("/stt has a time limit", /AbortController/.test(dictSrc) && /STT_WAIT_MS/.test(dictSrc));

  // ───────── the iOS keyboard trap (source checks: needs a real phone to run) ─────────
  const comp = fs.readFileSync(path.join(ROOT, "dashboard/composer-dictate.js"), "utf8");
  const startFn = comp.slice(comp.indexOf("function start()"), comp.indexOf("function stop()"));
  check("start lets go of the text box focus on a touch screen", /letGo\(inp\)/.test(startFn)
    && /function letGo\(inp\) \{\n    if \(inp && touch\(\) && document\.activeElement === inp\) \{ try \{ inp\.blur\(\); \}/.test(comp));
  check("the box cannot take focus back while recording", /addEventListener\("focus", function \(\) \{ if \(S\.state !== "idle"\) letGo\(inp\); \}\)/.test(comp));
  const finishedFn = comp.slice(comp.indexOf("function finished()"), comp.indexOf("function start()"));
  check("stop does not pop the keyboard on a touch screen", /if \(touch\(\)\) return;\n    try \{ inp\.focus\(\);/.test(finishedFn));
  const css = fs.readFileSync(path.join(ROOT, "dashboard/style.css"), "utf8");
  check("CSS: on a touch screen the box ignores taps while recording",
    /@media \(pointer: coarse\) \{\n  \.hud-voice\.dictating \.voice-input \{ pointer-events: none; \}/.test(css));
  const mc = fs.readFileSync(path.join(ROOT, "dashboard/mobile-chat.js"), "utf8");
  check("mobile-chat.js slides the page back when the keyboard goes down with focus kept",
    /if \(mq\.matches && vuaMo && !mo && \(window\.scrollY \|\| document\.documentElement\.scrollTop\)\) window\.scrollTo\(0, 0\);/.test(mc)
    && /vuaMo = mo;/.test(mc));

  if (fails.length) { console.log("\nFAIL - test_dictate_dung_va_huy: " + fails.length); process.exit(1); }
  console.log("\nOK - test_dictate_dung_va_huy: all pass");
  process.exit(0);   // the hanging /stt keeps its 45 second time limit armed; do not wait for it
})();
