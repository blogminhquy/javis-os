/* Android dictation no longer writes every draft of a sentence (2026-11-05, rebuilt from the result list 2026-11-06).

       node tests/js/test_dictate_android_repeat.js

   Owner report 2026-11-05 (Android, screenshot): saying "tôi bị học chữ ở đây" filled the box with
   "tôi tôi tôi tôi bị tôi bị tôi bị học tôi bị học chữ ...". Chrome on Android, on some phones, sends each new result as
   the whole sentence so far, several of them final, and dictate.js appended every one. These cases replay that shape
   and pin that a computer still appends separate results unchanged. */
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const tick = () => new Promise(r => setTimeout(r, 0));

const ANDROID = { userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130 Mobile", platform: "Linux armv8l", maxTouchPoints: 5 };
const MAC = { userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130", platform: "MacIntel", maxTouchPoints: 0 };

let runs = [];
class FakeSR {
  constructor() { runs.push(this); this.list = []; }
  start() {}
  stop() { Promise.resolve().then(() => this.onend && this.onend()); }
  abort() { Promise.resolve().then(() => this.onend && this.onend()); }
  // Like a real session: the result list grows, resultIndex points at the first changed entry.
  push(text, final) {
    const at = this.list.length && !this.list[this.list.length - 1].isFinal ? this.list.length - 1 : this.list.length;
    this.list[at] = Object.assign([{ transcript: text }], { isFinal: !!final });
    this.onresult({ resultIndex: at, results: this.list.slice() });
  }
}
function setNav(nav) {
  Object.defineProperty(globalThis, "navigator", { value: Object.assign({}, nav), configurable: true, writable: true });
}
global.window = { SpeechRecognition: FakeSR };
global.fetch = () => Promise.resolve({ json: () => Promise.resolve({ kind: "" }) });
setNav(MAC);
function fresh() {
  delete require.cache[require.resolve(path.join(ROOT, "dashboard/dictate.js"))];
  return require(path.join(ROOT, "dashboard/dictate.js"));
}
const D = fresh();

// ───────── pure buildRun: the run's text from its whole result list (2026-11-06) ─────────
const L = items => items.map(([t, f]) => Object.assign([{ transcript: t }], { isFinal: f !== false }));
const run = (items, android) => D.buildRun(L(items.map(x => Array.isArray(x) ? x : [x, true])), android);
const SCREENSHOT = ["tôi", "tôi", "tôi", "tôi bị", "tôi bị", "tôi bị học", "tôi bị học chữ", "tôi bị học chữ ở",
  "tôi bị học chữ ở đây", "tôi bị học chữ ở đây"];
check("Android: the screenshot's drafts end as the one sentence", run(SCREENSHOT, true) === "tôi bị học chữ ở đây");
check("Android: a new sentence after the first one is still added",
  run(["tôi bị", "tôi bị học", "mai gửi nhé"], true) === "tôi bị học mai gửi nhé");
check("Android: a short sentence after a longer one is KEPT (2026-11-06: it used to vanish)",
  run(["tôi về rồi", "tôi"], true) === "tôi về rồi tôi");
check("Android: case and punctuation differences between drafts do not count",
  run(["tôi bị học", "Tôi bị học chữ."], true) === "Tôi bị học chữ.");
check("Android: a word that only starts like the last one is not mistaken for a draft",
  run(["tôi", "tôii"], true) === "tôi tôii");
check("Android: an interim draft that grows the last final takes its place",
  run([["tôi bị", true], ["tôi bị học chữ", false]], true) === "tôi bị học chữ");
check("computer: every entry is kept, even a repeat", run(["alo", "alo", "một", "một hai"], false) === "alo alo một một hai");
check("empty and blank entries are skipped", run(["", "  ", "xin chào"], true) === "xin chào" && D.buildRun(null) === "");
check("isAndroid: only Android", D.isAndroid(ANDROID) && !D.isAndroid(MAC));

(async () => {
  // A real Android run, replaying the screenshot through onresult.
  runs = []; setNav(ANDROID);
  let Dx = fresh(), texts = [];
  let d = Dx.create({ onText: t => texts.push(t) });
  d.start(); await tick();
  const r = runs[0];
  r.push("tôi", false); r.push("tôi", true);
  r.push("tôi", true); r.push("tôi bị", false); r.push("tôi bị", true);
  r.push("tôi bị học", true); r.push("tôi bị học chữ", false); r.push("tôi bị học chữ", true);
  check("Android run: a growing draft shows in place of the last sentence, no repeats on screen",
    texts.indexOf("tôi bị học chữ") !== -1 && !texts.some(t => /tôi tôi|bị tôi/.test(t)));
  r.push("tôi bị học chữ ở đây", true); r.push("tôi bị học chữ ở đây", true);
  check("Android run: the box ends with the sentence once", texts[texts.length - 1] === "tôi bị học chữ ở đây");
  // The browser ends the run on silence; the next run keeps the words and adds new ones.
  r.onend();
  runs[1].push("mai gửi nhé", true);
  check("Android: a restarted run keeps the sentence and adds the next one",
    texts[texts.length - 1] === "tôi bị học chữ ở đây mai gửi nhé");
  d.cancel(); await tick();

  // A computer sends separate results; they are all kept, even when one repeats the last.
  runs = []; setNav(MAC);
  Dx = fresh(); texts = [];
  d = Dx.create({ onText: t => texts.push(t) });
  d.start(); await tick();
  runs[0].push("alo", true); runs[0].push("alo", true); runs[0].push("nghe rõ không", false);
  check("computer run: separate results all land, interim after them", texts[texts.length - 1] === "alo alo nghe rõ không");
  d.cancel(); await tick();

  if (fails.length) { console.log("\nFAIL - test_dictate_android_repeat: " + fails.length); process.exit(1); }
  console.log("\nOK - test_dictate_android_repeat: all pass");
})();
