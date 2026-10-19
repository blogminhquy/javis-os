/* Dictate button in the main chat composer (0.230.0): record, the words land in the box, nothing is sent by itself.

       node tests/js/test_composer_dictate.js
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const html = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard/style.css"), "utf8");
const app = fs.readFileSync(path.join(ROOT, "dashboard/app.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/en.json"), "utf8"));
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// ───────────── markup ─────────────
const card = (html.match(/<div class="hud-voice" id="hudVoice">[\s\S]*?<!-- \/hudVoice -->/) || [""])[0];
const row = card.slice(card.indexOf('id="cpRow"'));
check("the row has the dictate mic right before the voice chat button, both before send",
  row.indexOf('id="dictBtn"') !== -1 && row.indexOf('id="dictBtn"') < row.indexOf('id="voiceBtn"')
  && row.indexOf('id="voiceBtn"') < row.indexOf('id="sendBtn"'));
check("the dictation bar has cancel, meter, timer and stop, and sits before send",
  ["dictBar", "dictCancel", "dictWave", "dictTime", "dictStop", "dictBusy"].every(id => row.indexOf('id="' + id + '"') !== -1)
  && row.indexOf('id="dictBar"') < row.indexOf('id="sendBtn"'));
const voiceTag = (row.match(/<button[^>]*id="voiceBtn"[\s\S]*?<\/button>/) || [""])[0];
check("the voice chat button now draws a sound wave, not a mic", /M2 10v3M6 6v11M10 3v18/.test(voiceTag) && !/a3 3 0 0 0-3 3v8/.test(voiceTag));
check("composer-dictate.js loads after dictate.js", html.indexOf("/static/dictate.js") !== -1
  && html.indexOf("/static/dictate.js") < html.indexOf("/static/composer-dictate.js"));
check("CSS: while dictating the bar shows and +, chips and both voice buttons hide",
  /\.hud-voice\.dictating \.dict-bar \{ display: flex; \}/.test(css)
  && /\.hud-voice\.dictating \.cp-plus, \.hud-voice\.dictating \.cp-chips[^{]*\.dict-btn, \.hud-voice\.dictating #voiceBtn \{ display: none; \}/.test(css));
check("app.js shares its passing note for mic errors", /window\.JavisNoteFlash = ghiChuThoang;/.test(app));
["bar.mic", "dict.btn", "dict.stop", "dict.cancel", "dict.busy", "dict.in_call", "dict.unsupported", "dict.denied", "dict.failed"]
  .forEach(k => check("key " + k + " in vi and en", !!(vi[k] && en[k])));
check("the voice chat tooltip says it is a live conversation", /Đàm thoại/.test(vi["bar.mic"]) && /Voice chat/.test(en["bar.mic"]));

// ───────────── 0.231.0: two buttons, voice chat turns into send ─────────────
function grab(name) {
  const i = app.indexOf("function " + name + "(");
  let depth = 0, j = app.indexOf("{", i);
  for (; j < app.length; j++) { if (app[j] === "{") depth++; else if (app[j] === "}" && --depth === 0) break; }
  return app.slice(i, j + 1);
}
function buttons(state) {
  const el = () => ({ style: {}, title: "" });
  const env = { sendBtn: el(), voiceBtn: el(), stopBtn: el(), dict: el() };
  const run = new Function("st", "env", `
    let isProcessing = st.processing, pendingAttachments = st.atts || [];
    const voice = { isSpeaking: () => !!st.speaking };
    const chatInput = { value: st.text || "" };
    const sendBtn = env.sendBtn, voiceBtn = env.voiceBtn, stopBtn = env.stopBtn;
    const document = { getElementById: () => env.dict };
    const window = { t: k => k };
    function handsFreeActive() { return !!st.call; }
    ${grab("updateStopBtn")} ${grab("coNoiDungGui")} ${grab("coTheGuiBoSung")}
    updateStopBtn();`);
  run(state, env);
  const shown = b => b.style.display !== "none";
  return ["dict", "voiceBtn", "stopBtn", "sendBtn"].filter(k => shown(env[k])).join(",");
}
check("empty box: mic and voice chat, no send", buttons({}) === "dict,voiceBtn");
check("typed text: voice chat turns into send", buttons({ text: "chào" }) === "dict,sendBtn");
check("an attachment alone also shows send", buttons({ atts: [{ path: "a.png" }] }) === "dict,sendBtn");
check("Javis answering, empty box: mic and stop", buttons({ processing: true }) === "dict,stopBtn");
check("Javis answering with typed text: stop and send (add-on)", buttons({ processing: true, text: "thêm" }) === "dict,stopBtn,sendBtn");
check("in a call: the red hang-up stays, the dictate mic steps aside", buttons({ call: true }) === "voiceBtn");
check("the box value is watched, so code that empties or fills it flips the button too",
  /Object\.defineProperty\(chatInput, "value"/.test(app) && /set\(v\) \{ d\.set\.call\(this, v\); try \{ updateStopBtn\(\); \}/.test(app));
check("attachments refresh the button", /function renderChips\(\) \{\n  try \{ updateStopBtn\(\); \}/.test(app));
check("CSS: send stays while dictating, voice chat wears the filled circle",
  /\.hud-voice\.dictating #sendBtn \{ display: flex !important; \}/.test(css) && /#voiceBtn:not\(\.in-call\):not\(\.handsfree\) \{ background: var\(--accent-solid\)/.test(css));

// ───────────── pure helpers ─────────────
const CD = require(path.join(ROOT, "dashboard/composer-dictate.js"));
check("timer reads m:ss", CD.fmtTime(0) === "0:00" && CD.fmtTime(9.7) === "0:09" && CD.fmtTime(75) === "1:15" && CD.fmtTime(-3) === "0:00");
const silence = new Uint8Array(512).fill(128);
const loud = new Uint8Array(512).map((_, i) => (i % 2 ? 228 : 28));
check("meter: silence is flat, loud speech fills the bar", CD.levelOf(silence) === 0 && CD.levelOf(loud) > 0.8 && CD.levelOf(loud) <= 1);
check("recording stops by itself after 5 minutes", CD.MAX_SECONDS === 300);

// ───────────── dictate.js engine with a fake Web Speech ─────────────
const runs = [];
class FakeSR {
  constructor() { runs.push(this); this.stopped = false; }
  start() {}
  stop() { this.stopped = true; Promise.resolve().then(() => this.onend && this.onend()); }
  abort() { this.aborted = true; Promise.resolve().then(() => this.onend && this.onend()); }
  say(text, final) {
    this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal: !!final })] });
  }
}
global.window = { SpeechRecognition: FakeSR };
global.fetch = () => Promise.resolve({ json: () => Promise.resolve({ kind: "" }) });
const D = require(path.join(ROOT, "dashboard/dictate.js"));
const tick = () => new Promise(r => setTimeout(r, 0));

(async () => {
  // A run the browser ends on its own restarts and keeps the words; stop then finishes.
  let texts = [], states = [];
  let d = D.create({ onText: t => texts.push(t), onState: s => states.push(s) });
  d.start(); await tick();
  check("start listens", states[states.length - 1] === "listening" && runs.length === 1);
  runs[0].say("xin chào", true);
  runs[0].onend();                       // Chrome stops after a silence, the owner has not pressed stop
  check("a run ended by the browser restarts while still recording", runs.length === 2 && d.active());
  runs[1].say("Javis", false);
  check("the new run keeps the words heard before", texts[texts.length - 1] === "xin chào Javis");
  d.stop(); await tick();
  check("stop ends with idle and no further run", states[states.length - 1] === "idle" && runs.length === 2 && !d.active());

  // Cancel drops the recording: idle at once, no text after it.
  texts = []; states = [];
  d = D.create({ onText: t => texts.push(t), onState: s => states.push(s) });
  d.start(); await tick();
  const r = runs[runs.length - 1];
  r.say("bỏ đi", false);
  d.cancel(); await tick();
  r.onresult && r.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: "muộn" }], { isFinal: true })] });
  check("cancel reports idle and aborts the run", states[states.length - 1] === "idle" && r.aborted === true);
  check("no text arrives after cancel", texts.join("|") === "bỏ đi");
  check("cancel does not start another run", runs[runs.length - 1] === r);

  // Cancel right after stop (last result still pending) still drops it.
  states = [];
  d = D.create({ onState: s => states.push(s) });
  d.start(); await tick();
  const r2 = runs[runs.length - 1];
  r2.stop = function () { this.stopped = true; };   // the browser has not sent onend yet
  d.stop();
  d.cancel(); await tick();
  check("cancel after stop, before the browser ends the run, still settles idle", states[states.length - 1] === "idle" && r2.aborted === true);

  // The teams composer API is unchanged.
  check("create still returns start, stop, active (teams composer)", ["start", "stop", "active", "cancel", "busy"].every(k => typeof d[k] === "function"));

  if (fails.length) { console.log("\nFAIL - test_composer_dictate: " + fails.length); process.exit(1); }
  console.log("\nOK - test_composer_dictate: all pass");
})();
