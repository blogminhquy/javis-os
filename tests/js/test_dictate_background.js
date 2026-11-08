/* A recording keeps going when the owner switches tab or app (2026-11-08).

       node tests/js/test_dictate_background.js

   Owner report: dictating, then Alt Tab to another page stopped the recording. The owner wants it to run on in the
   background, on a computer and on a phone. These cases pin it:
   1. The main chat composer no longer stops the recording when the page is hidden.
   2. A recognizer run the browser cuts while the page is hidden is parked (no error, still listening) and starts
      again when the page is visible, keeping the words heard before.
   3. A normal end in the background (a computer keeps listening there) restarts at once, as before.
   4. A phone recorder the system stopped in the background keeps its audio; the mic reopens on return and both
      pieces are heard and joined on stop.
   5. A recorder that is already inactive when stop is pressed still hands over its audio (it used to be dropped). */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const tick = async (n) => { for (let i = 0; i < (n || 3); i++) await new Promise(r => setTimeout(r, 0)); };

const MAC = { userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130", platform: "MacIntel", maxTouchPoints: 0 };
const IPHONE = { userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15", platform: "iPhone", maxTouchPoints: 5 };

// ───────── fakes ─────────
const listeners = {};
global.document = {
  hidden: false,
  documentElement: { getAttribute: () => "vi" },
  addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
  removeEventListener(t, f) { listeners[t] = (listeners[t] || []).filter(x => x !== f); },
};
function setHidden(h) { document.hidden = h; (listeners.visibilitychange || []).slice().forEach(f => f()); }

let runs = [], recorders = [], mics = [], ear = "", uploads = 0;
class FakeSR {
  constructor() { runs.push(this); this.at = Date.now(); }
  start() {}
  stop() { Promise.resolve().then(() => this.onend && this.onend()); }
  abort() { Promise.resolve().then(() => this.onend && this.onend()); }
  say(text) { this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal: true })] }); }
}
class FakeRecorder {
  constructor() { this.state = "inactive"; this.mimeType = "audio/mp4"; recorders.push(this); }
  start() { this.state = "recording"; }
  // What the phone does in the background: the recorder stops by itself, its audio arrives, nobody listens to onstop.
  systemStop() {
    this.state = "inactive";
    this.ondataavailable && this.ondataavailable({ data: new Blob([new Uint8Array(4000)]) });
    this.onstop && this.onstop();
  }
  stop() { this.state = "inactive"; Promise.resolve().then(() => this.systemStop()); }
}
function setNav(nav) {
  Object.defineProperty(globalThis, "navigator", {
    value: Object.assign({}, nav, { mediaDevices: { getUserMedia: () => {
      const track = { readyState: "live", stop() { this.readyState = "ended"; } };
      const s = { getTracks: () => [track], track };
      mics.push(s);
      return Promise.resolve(s);
    } } }),
    configurable: true, writable: true,
  });
}
global.window = { SpeechRecognition: FakeSR };
global.MediaRecorder = FakeRecorder;
global.fetch = (url, init) => {
  const u = String(url);
  if (u.indexOf("/stt/fix") !== -1) return Promise.resolve({ json: () => Promise.resolve({ ok: true, text: JSON.parse(init.body).text }) });
  if (u.indexOf("/voice/ear") !== -1) return Promise.resolve({ json: () => Promise.resolve({ kind: ear }) });
  uploads++;
  const n = uploads;
  return Promise.resolve({ json: () => Promise.resolve({ ok: true, text: "phần " + n }) });
};
function fresh() {
  delete require.cache[require.resolve(path.join(ROOT, "dashboard/dictate.js"))];
  return require(path.join(ROOT, "dashboard/dictate.js"));
}

(async () => {
  // 1. The composer itself no longer stops on a hidden page.
  const comp = fs.readFileSync(path.join(ROOT, "dashboard/composer-dictate.js"), "utf8");
  check("composer-dictate.js does not stop the recording when the page is hidden",
    !/document\.hidden\)\s*stop\(\)/.test(comp));

  // 2. Computer, Web Speech only: the browser cuts the run in the background, it comes back on return.
  setNav(MAC); ear = ""; runs = []; recorders = []; mics = [];
  let D = fresh();
  await D.warm();
  let states = [], texts = [], errors = [];
  let d = D.create({ onText: (t, f) => texts.push([t, f]), onState: s => states.push(s), onError: c => errors.push(c),
    polish: false });
  d.start(); await tick();
  runs[0].say("xin chào");
  setHidden(true);
  runs[0].onerror({ error: "network" });
  runs[0].onend();
  await tick();
  check("hidden: a run cut by the browser reports no error", errors.length === 0);
  check("hidden: the recording is still on and listening", d.active() && states[states.length - 1] === "listening");
  check("hidden: no tight restart loop while away", runs.length === 1);
  setHidden(false);
  await tick();
  check("visible again: a new run starts by itself", runs.length === 2);
  runs[1].say("Javis");
  check("visible again: the words heard before are kept", texts[texts.length - 1][0] === "xin chào Javis");
  d.stop(); await tick(5);
  check("stop after the round trip gives the whole sentence",
    states[states.length - 1] === "idle" && texts[texts.length - 1][0] === "xin chào Javis" && texts[texts.length - 1][1] === true);

  // 3. A normal end while hidden (the browser keeps listening there) restarts straight away.
  runs = []; states = []; texts = [];
  D = fresh(); await D.warm();
  d = D.create({ onText: t => texts.push(t), onState: s => states.push(s), polish: false });
  d.start(); await tick();
  runs[0].say("một");
  runs[0].at -= 5000;
  setHidden(true);
  // The run lived for a while, then ended on silence: not an interruption.
  const realNow = Date.now;
  Date.now = () => realNow() + 5000;
  runs[0].onend();
  Date.now = realNow;
  check("hidden: a normal end restarts at once", runs.length === 2 && d.active());
  runs[1].say("hai");
  setHidden(false);
  await tick();
  check("hidden: words keep coming in the background", texts[texts.length - 1] === "một hai" && runs.length === 2);
  d.stop(); await tick(5);

  // 4. iPhone with an upload ear: the system stops the recorder in the background, the mic reopens on return.
  setNav(IPHONE); ear = "upload"; runs = []; recorders = []; mics = []; uploads = 0;
  D = fresh(); await D.warm();
  states = []; texts = []; errors = [];
  d = D.create({ onText: (t, f) => texts.push([t, f]), onState: s => states.push(s), onError: c => errors.push(c),
    onStream: () => {}, polish: false });
  d.start(); await tick();
  check("iPhone with an ear records only", recorders.length === 1 && runs.length === 0);
  setHidden(true);
  recorders[0].systemStop();
  mics[0].track.readyState = "ended";
  await tick();
  setHidden(false);
  await tick(5);
  check("visible again: a second recorder is running", recorders.length === 2 && recorders[1].state === "recording");
  check("visible again: still listening, no error", states[states.length - 1] === "listening" && errors.length === 0);
  d.stop(); await tick(10);
  check("stop: both pieces are heard and joined", uploads === 2 && texts.length && texts[texts.length - 1][0] === "phần 1 phần 2");

  // 5. Recorder already inactive when stop is pressed, page never came back to visible in between.
  recorders = []; mics = []; uploads = 0; states = []; texts = [];
  D = fresh(); await D.warm();
  d = D.create({ onText: (t, f) => texts.push([t, f]), onState: s => states.push(s), polish: false });
  d.start(); await tick();
  recorders[0].systemStop();
  d.stop(); await tick(10);
  check("a recorder stopped by the system still hands over its audio", uploads === 1 && texts.length && texts[texts.length - 1][0] === "phần 1");

  if (fails.length) { console.log("\n" + fails.length + " failed"); process.exit(1); }
  console.log("\nall ok");
})();
