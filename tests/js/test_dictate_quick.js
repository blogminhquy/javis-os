/* The phone records for a model from the first press, the wave moves, and stop is quick after an ear (2026-11-22).

       node tests/js/test_dictate_quick.js

   Owner, 2026-11-22: "ở điện thoại ấn vào thì nó không chép được lời và không nhìn thấy cái sóng âm", and "chức năng
   viết lại lời đang bị quá chậm", ChatGPT and Claude transcribe smoothly with their own model. Drives dictate.js with
   fakes. Pins:
   - the ear answer is remembered across page loads, so a phone's FIRST press records for the model (with the meter)
     instead of falling back to the browser's recognizer;
   - text an ear heard is polished with `quick` (the server then never waits on a subscription CLI) and a shorter wait;
     the browser's own words are not;
   - the recognizer's own events reach onHeard, and the composer turns them into a moving wave (waveLevel);
   - "nothing heard" on a phone with no ear names the fix (dict.nothing_phone), in both dictionaries. */
const path = require("path");
const fs = require("fs");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const tick = () => new Promise(r => setTimeout(r, 0));
const settle = async () => { for (let i = 0; i < 12; i++) await tick(); };

const IPHONE = { userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15", platform: "iPhone", maxTouchPoints: 5 };
const PC = { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36", platform: "Win32", maxTouchPoints: 0 };

let runs = [], mics = [], recorders = [], ear = "upload", earAsked = 0, fixes = [], sttText = "Mở trang Models giúp anh.";
class SR {
  constructor() { runs.push(this); }
  start() {}
  stop() { setTimeout(() => this.onend && this.onend(), 0); }
  abort() {}
  say(text) { this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal: true })] }); }
}
class Rec {
  constructor() { this.state = "inactive"; this.mimeType = "audio/mp4"; recorders.push(this); }
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    setTimeout(() => { this.ondataavailable && this.ondataavailable({ data: new Blob([new Uint8Array(4000)]) }); this.onstop && this.onstop(); }, 0);
  }
}
function setNav(nav) {
  Object.defineProperty(globalThis, "navigator", {
    value: Object.assign({}, nav, { mediaDevices: { getUserMedia: () => {
      const s = { getTracks: () => [{ stop() {} }] };
      mics.push(s);
      return Promise.resolve(s);
    } } }),
    configurable: true, writable: true,
  });
}
const store = {};
global.localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
global.window = { SpeechRecognition: SR };
global.MediaRecorder = Rec;
const json = v => Promise.resolve({ json: () => Promise.resolve(v) });
global.fetch = (url, init) => {
  url = String(url);
  if (url.indexOf("/voice/ear") !== -1) { earAsked++; return json({ kind: ear }); }
  if (url.indexOf("/stt/fix") !== -1) { fixes.push(JSON.parse(init.body)); return json({ ok: true, text: "Câu đã viết lại." }); }
  if (url.indexOf("/stt") !== -1) return json({ ok: true, text: sttText });
  return json({});
};
function fresh() {
  delete require.cache[require.resolve(path.join(ROOT, "dashboard/dictate.js"))];
  return require(path.join(ROOT, "dashboard/dictate.js"));
}
function reset(nav) { runs = []; mics = []; recorders = []; fixes = []; setNav(nav); }

(async () => {
  // 1. The answer is remembered: a fresh page's first press on an iPhone records for the model.
  reset(IPHONE); ear = "upload";
  let D = fresh();
  await D.warm();
  check("the ear answer is stored for the next page load", store["javis.dictate.ear"] === "upload");
  reset(IPHONE);
  D = fresh();   // a reload: nothing asked yet on this page
  check("a reloaded page knows the ear before asking", D.ear() === "upload");
  let streams = [], states = [], texts = [];
  let d = D.create({ onStream: s => streams.push(s), onState: s => states.push(s), onText: (t, f) => texts.push([t, f]) });
  d.start(); await settle();
  check("first press on the reloaded iPhone: records for the model, no browser recognizer",
    recorders.length === 1 && runs.length === 0);
  check("... and the meter gets the mic stream, so the wave moves", streams.length === 1 && streams[0] === mics[0]);

  // 2. The ear's text is polished with `quick` and lands.
  d.stop(); await settle();
  check("ear text: the rewrite is asked with quick", fixes.length === 1 && fixes[0].quick === true
    && fixes[0].text === sttText);
  check("ear text: the polished sentence lands as final", texts.length && texts[texts.length - 1][0] === "Câu đã viết lại."
    && texts[texts.length - 1][1] === true && states[states.length - 1] === "idle");

  // 3. The browser's own words (no ear, on a computer): the full rewrite, not quick.
  reset(PC); ear = ""; store["javis.dictate.ear"] = "";
  D = fresh();
  await D.warm();
  d = D.create({ onState: () => {}, onText: () => {} });
  d.start(); await settle();
  runs[0].say("câu trình duyệt nghe");
  d.stop(); await settle();
  check("browser words: the rewrite is asked without quick", fixes.length === 1 && fixes[0].quick === false);

  // 4. The recognizer's own events reach onHeard (a phone with no ear has no mic stream to measure).
  reset(IPHONE); ear = ""; store["javis.dictate.ear"] = "";
  D = fresh();
  await D.warm();
  const heard = [];
  streams = [];
  d = D.create({ onHeard: k => heard.push(k), onStream: s => streams.push(s), onState: () => {}, onText: () => {} });
  d.start(); await settle();
  check("iPhone, no ear: the browser's recognizer, no second mic capture", runs.length === 1 && mics.length === 0);
  runs[0].onsoundstart(); runs[0].say("một"); runs[0].onsoundend();
  check("recognizer events reach onHeard: sound, result, silence", heard.join(",") === "sound,result,silence");
  d.cancel(); await settle();

  // 5. The composer draws those events as a wave.
  const C = require(path.join(ROOT, "dashboard/composer-dictate.js"));
  check("wave: flat while the recognizer hears nothing", C.waveLevel(false, -1, 1234) === 0 && C.waveLevel(false, 5000, 1234) === 0);
  check("wave: up while it hears sound", C.waveLevel(true, -1, 1234) > 0.25);
  check("wave: up for a moment after words come back", C.waveLevel(false, 200, 1234) > 0.25);
  check("wave: the same moment draws the same bar (no randomness)", C.waveLevel(true, -1, 777) === C.waveLevel(true, -1, 777));
  const comp = fs.readFileSync(path.join(ROOT, "dashboard/composer-dictate.js"), "utf8");
  check("composer: passes onHeard to dictate.js and draws waveLevel without an analyser",
    /onHeard:\s*function/.test(comp) && /waveLevel\(S\.voice/.test(comp));

  // 6. The "nothing heard" note.
  check("phone with no ear: the note that names the fix", D.nothingKey(IPHONE, "") === "dict.nothing_phone");
  check("phone with an ear, or a computer: the usual note",
    D.nothingKey(IPHONE, "upload") === "dict.nothing" && D.nothingKey(PC, "") === "dict.nothing");
  for (const lang of ["vi", "en"]) {
    const dict = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/" + lang + ".json"), "utf8"));
    check(lang + ".json has dict.nothing_phone", typeof dict["dict.nothing_phone"] === "string" && dict["dict.nothing_phone"].length > 10);
  }
  for (const f of ["composer-dictate.js", "teams.js", "conversations.js", "editor-dictate.js"]) {
    const src = fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
    check(f + ": the nothing note goes through nothingKey", /nothingKey\(\)/.test(src));
  }

  if (fails.length) { console.log("\nFAIL - test_dictate_quick: " + fails.length); process.exit(1); }
  console.log("\nOK - test_dictate_quick: all pass");
  process.exit(0);
})();
