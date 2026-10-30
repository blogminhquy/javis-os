/* The dictation mic opens INSIDE the tap on an iPhone (0.419.0).

       node tests/js/test_dictate_inside_tap.js

   Owner report 2026-10-30, iPhone 15 Pro Max: press the dictation mic, the bar flashes and closes, no stop square.
   Safari only lets a page open the mic or start its speech recognizer during the brief moment after a tap, and
   dictate.js asked GET /voice/ear over the network first on nearly every press (the answer was cached for a minute
   only). These cases pin the fix: with any known answer the capture call happens synchronously in start(), the
   refresh runs in the background, and a failed refresh keeps the last known answer. */
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond, them) { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && them !== undefined ? "  [" + them + "]" : "")); if (!cond) fails.push(name); }
const tick = () => new Promise(r => setTimeout(r, 0));

const IPHONE = { userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15", platform: "iPhone", maxTouchPoints: 5 };

let runs = [], mics = 0, recorders = [], ear = "upload", fetches = 0, failFetch = false;
class FakeSR {
  constructor() { runs.push(this); }
  start() { this.started = true; }
  stop() { Promise.resolve().then(() => this.onend && this.onend()); }
  abort() { Promise.resolve().then(() => this.onend && this.onend()); }
}
class FakeRecorder {
  constructor() { this.state = "inactive"; this.mimeType = "audio/mp4"; recorders.push(this); }
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; Promise.resolve().then(() => this.onstop && this.onstop()); }
}
Object.defineProperty(globalThis, "navigator", {
  value: Object.assign({}, IPHONE, { mediaDevices: { getUserMedia: () => {
    mics++;
    return Promise.resolve({ getTracks: () => [{ stop() {} }] });
  } } }),
  configurable: true, writable: true,
});
global.window = { SpeechRecognition: FakeSR };
global.MediaRecorder = FakeRecorder;
global.fetch = (url) => {
  if (String(url).indexOf("/voice/ear") !== -1) fetches++;
  if (failFetch) return Promise.reject(new Error("offline"));
  return Promise.resolve({ json: () => Promise.resolve(String(url).indexOf("/voice/ear") !== -1 ? { kind: ear } : { ok: true, text: "" }) });
};
let now = Date.now();
const realNow = Date.now;
Date.now = () => now;

function fresh() {
  delete require.cache[require.resolve(path.join(ROOT, "dashboard/dictate.js"))];
  return require(path.join(ROOT, "dashboard/dictate.js"));
}

(async () => {
  // ── iPhone with an upload ear: the recorder path ──
  // Owner, 2026-10-30: ordinary users never set Groq up. A press made before ANY answer still starts at once, with the
  // browser's own recognizer, instead of waiting for the network.
  let D = fresh();
  let d = D.create({});
  d.start();
  check("very first press, no answer yet: the recognizer starts synchronously, inside the tap",
    runs.length === 1 && runs[0].started === true && mics === 0);
  for (let i = 0; i < 4; i++) await tick();
  d.cancel(); await tick();
  check("and that press asked the ear in the background", D.ear() === "upload", D.ear());

  now += 120000;   // well past the old one-minute cache: the press that used to go to the network first
  const before = fetches, micsBefore = mics;
  d = D.create({});
  d.start();       // no await: whatever happens here happens inside the tap
  check("a later press opens the mic synchronously, inside the tap", mics === micsBefore + 1, mics - micsBefore);
  check("and refreshes the ear in the background", fetches === before + 1, fetches - before);
  for (let i = 0; i < 4; i++) await tick();
  check("the recorder then runs", recorders[recorders.length - 1].state === "recording");
  d.cancel(); await tick();

  // ── a refresh that fails keeps the last known answer ──
  failFetch = true;
  now += 120000;
  d = D.create({});
  d.start();
  check("offline refresh: still opens the mic inside the tap", mics === micsBefore + 2);
  for (let i = 0; i < 4; i++) await tick();
  check("offline refresh: the ear is still 'upload', not dropped to none", D.ear() === "upload", D.ear());
  d.cancel(); await tick();
  failFetch = false;

  // ── iPhone without an ear: Web Speech starts inside the tap too ──
  ear = "";
  D = fresh();
  await D.warm();
  const runs0 = runs.length;
  d = D.create({});
  d.start(); for (let i = 0; i < 4; i++) await tick();
  check("no ear: Web Speech runs", runs.length === runs0 + 1 && runs[runs.length - 1].started === true);
  d.cancel(); await tick();
  now += 120000;
  const runsBefore = runs.length;
  d = D.create({});
  d.start();
  check("no ear, later press: the recognizer starts synchronously, inside the tap",
    runs.length === runsBefore + 1 && runs[runs.length - 1].started === true, runs.length - runsBefore);
  check("no ear: no getUserMedia next to it (one capture per phone)", mics === micsBefore + 2);
  d.cancel(); await tick();

  // ── the "mic blocked" note on an iPhone points at Safari's real switch (aA > Website Settings), not a padlock ──
  const fs = require("fs");
  const CD = fs.readFileSync(path.join(ROOT, "dashboard/composer-dictate.js"), "utf8");
  const VI = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/vi.json"), "utf8"));
  const EN = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/en.json"), "utf8"));
  check("iPhone gets its own mic-blocked note", /ios \? "dict\.denied_ios" : "dict\.denied"/.test(CD));
  check("that note names Safari's aA menu in both languages", /aA/.test(VI["dict.denied_ios"] || "") && /aA/.test(EN["dict.denied_ios"] || ""));

  // ── Dictation switched off on the iPhone (service-not-allowed) is its own note, pointing at Settings > Keyboard ──
  ear = "";
  D = fresh();
  await D.warm();
  const errs = [];
  d = D.create({ onError: (c) => errs.push(c) });
  d.start();
  runs[runs.length - 1].onerror({ error: "service-not-allowed" });
  runs[runs.length - 1].onend(); await tick();
  check("service-not-allowed is reported as 'service', not as a blocked mic", errs.join(",") === "service", errs.join(","));
  check("the composer and the team chat both map 'service' to the Dictation note",
    /code === "service" \? \(ios \? "dict\.service_ios"/.test(CD)
    && /code === "service" \? \(ios \? "dict\.service_ios"/.test(fs.readFileSync(path.join(ROOT, "dashboard/teams.js"), "utf8")));
  check("that note says where Dictation is turned on, in both languages",
    /Đọc chính tả/.test(VI["dict.service_ios"] || "") && /Dictation/.test(EN["dict.service_ios"] || ""));
  check("no dictation note sends an ordinary user to a Groq key any more",
    ["dict.nothing", "dict.unsupported", "teams.mic_unsupported"].every((k) => !/Groq/.test(VI[k] + EN[k])));

  Date.now = realNow;
  if (fails.length) { console.log("\nFAIL - test_dictate_inside_tap: " + fails.length); process.exit(1); }
  console.log("\nOK - test_dictate_inside_tap: all pass");
})();
