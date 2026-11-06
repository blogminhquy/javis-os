/* The dictation mics show the words only after the recording ends (2026-11-05).

       node tests/js/test_composer_dictate_after_stop.js

   Owner, 2026-11-05: the mic icon should not copy the text onto the screen while speaking; it works like a voice
   recorder and the text comes out when the recording stops. These cases drive composer-dictate.js with a fake DOM and
   a fake dictate engine: nothing reaches the box while listening, the whole text lands once on idle, send-while-recording
   sends that text, and X leaves the box as it was. The team chat and Chatbot mics are checked on their source. */
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

function el(id) {
  const listeners = {};
  const cls = new Set();
  return {
    id, value: "", hidden: false, disabled: false, readOnly: false, scrollTop: 0, scrollHeight: 0, attrs: {},
    classList: { toggle(c, on) { if (on) cls.add(c); else cls.delete(c); }, contains: c => cls.has(c) },
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
    dispatchEvent(e) { (listeners[e.type] || []).forEach(f => f.call(this, e)); return true; },
    click() { this.dispatchEvent({ type: "click", target: this }); },
    focus() {}, blur() {}, setSelectionRange() {},
  };
}
const els = {};
["hudVoice", "dictBtn", "chatInput", "dictCancel", "dictStop", "dictBusy", "sendBtn", "voiceBtn", "dictTime", "dictWave"]
  .forEach(id => { els[id] = el(id); });
let sent = 0;
els.sendBtn.addEventListener("click", () => { sent++; });

let engine = null;
const D = require(path.join(ROOT, "dashboard/dictate.js"));
global.Event = function (type) { this.type = type; };
global.document = {
  readyState: "complete", hidden: false, activeElement: null,
  getElementById: id => els[id] || null,
  addEventListener() {},
};
global.window = {
  addEventListener() {},
  matchMedia: () => ({ matches: false }),
  JavisDictate: {
    joinText: D.joinText, createLiveFix: D.createLiveFix, fixAfter: D.fixAfter, ear: () => "", isIOS: () => false,
    create(opts) {
      engine = { opts, started: 0, stopped: 0, cancelled: 0,
        start() { this.started++; },
        stop() { this.stopped++; },
        cancel() { this.cancelled++; opts.onState("idle"); } };
      return engine;
    },
  },
};
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
global.setInterval = () => 1;
global.clearInterval = () => {};
global.getComputedStyle = () => ({ color: "#fff" });
require(path.join(ROOT, "dashboard/composer-dictate.js"));

const inp = els.chatInput;

// Record, words arrive, nothing on screen until stop.
inp.value = "Ghi chú:";
els.dictBtn.click();
check("pressing the mic starts the engine", engine && engine.started === 1);
engine.opts.onState("listening");
engine.opts.onText("tôi bị", false);
engine.opts.onText("tôi bị học chữ ở đây", false);
check("while recording, the box keeps only what was typed before", inp.value === "Ghi chú:");
els.dictStop.click();
check("stop asks the engine to stop", engine.stopped === 1);
check("still nothing on screen while the last words come in", inp.value === "Ghi chú:");
engine.opts.onState("idle");
check("when the recording ends the whole text lands once, after the typed text",
  inp.value === "Ghi chú: tôi bị học chữ ở đây");
check("the box can be edited again", inp.readOnly === false);

// The ear's text (Groq) replaces the browser draft, still only at the end.
inp.value = "";
els.dictBtn.click();
engine.opts.onState("listening");
engine.opts.onText("toi bi hoc", false);
engine.opts.onState("transcribing");
engine.opts.onText("Tôi bị học chữ ở đây.", true);
check("transcribing: the box is still empty", inp.value === "");
engine.opts.onState("idle");
check("the ear's text is what lands", inp.value === "Tôi bị học chữ ở đây.");

// X drops the recording: the box stays as it was.
inp.value = "giữ nguyên";
els.dictBtn.click();
engine.opts.onState("listening");
engine.opts.onText("bỏ câu này", false);
els.dictCancel.click();
check("X: nothing heard is written, the typed text stays", inp.value === "giữ nguyên" && engine.cancelled === 1);

// Send while recording: stop, the text lands, then it is sent.
inp.value = "";
sent = 0;
els.dictBtn.click();
engine.opts.onState("listening");
engine.opts.onText("gửi luôn nhé", false);
els.hudVoice.dispatchEvent({ type: "click", target: { closest: () => els.sendBtn },
  preventDefault() {}, stopPropagation() {} });
check("send while recording stops first, nothing sent yet", engine.stopped === 1 && sent === 0);
engine.opts.onState("idle");
check("send: the heard text is in the box and sent", inp.value === "gửi luôn nhé" && sent === 1);

// The faded live bubble (2026-11-06): a computer shows the words in it while speaking; a phone shows none.
const bubble = [];
global.window.nhapGiong = t => { bubble.push(t); };
const setUA = ua => Object.defineProperty(global, "navigator", { value: { userAgent: ua }, configurable: true, writable: true });

setUA("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36");
inp.value = "";
els.dictBtn.click();
engine.opts.onState("listening");
engine.opts.onText("tôi bị", false);
engine.opts.onText("tôi bị học", false);
check("computer: the faded bubble shows the words while speaking", bubble[bubble.length - 1] === "tôi bị học");
check("computer: the box still does not move while speaking", inp.value === "");
els.dictStop.click();
engine.opts.onState("idle");
check("computer: the bubble is cleared when the recording ends", bubble[bubble.length - 1] === "");
check("computer: the text lands in the box once", inp.value === "tôi bị học");

setUA("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1");
inp.value = "";
let shown = bubble.length;
els.dictBtn.click();
engine.opts.onState("listening");
engine.opts.onText("ipad nói", false);
check("tablet (iPad) keeps the bubble", bubble[bubble.length - 1] === "ipad nói");
els.dictStop.click();
engine.opts.onState("idle");

setUA("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1");
inp.value = "";
shown = bubble.length;
els.dictBtn.click();
engine.opts.onState("listening");
engine.opts.onText("tôi bị", false);
engine.opts.onText("tôi bị học", false);
check("iPhone: no bubble text while speaking", bubble.slice(shown).every(t => t === ""));
check("iPhone: the box still gets the text once, at the end", inp.value === "");
els.dictStop.click();
engine.opts.onState("idle");
check("iPhone: the text lands in the box at the end", inp.value === "tôi bị học");

setUA("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36");
inp.value = "";
shown = bubble.length;
els.dictBtn.click();
engine.opts.onState("listening");
engine.opts.onText("tôi tôi bị", false);
check("Android phone: no bubble text while speaking", bubble.slice(shown).every(t => t === ""));
els.dictCancel.click();
check("Android phone: X leaves the box as it was", inp.value === "");

// The team chat and Chatbot mics follow the same rule: onText only holds the words, the box is written on idle.
const fs = require("fs");
const TEAMS = fs.readFileSync(path.join(ROOT, "dashboard/teams.js"), "utf8");
const CONV = fs.readFileSync(path.join(ROOT, "dashboard/conversations.js"), "utf8");
check("team chat mic: onText only holds the words (and feeds the faded bubble, never the box)",
  /onText: function \(text\) \{ heard = String\(text \|\| ""\); if \(live\) live\.heard\(heard\); \}/.test(TEAMS));
check("team chat mic: the words land when the recording is idle",
  /st === "idle" && heard \? S\.el\.querySelector\("\.tm-input"\)/.test(TEAMS) &&
  /D\.joinText\(S\.dictBase, \(res && res\.words\) \|\| heard\)/.test(TEAMS));
const convText = (CONV.match(/onText: function \(text\) \{[\s\S]*?\n      \},/) || [""])[0];
check("Chatbot mic: onText only holds the words, never writes the box",
  /_dictHeard = String\(text \|\| ""\)/.test(convText) && !/box\.value/.test(convText));
check("Chatbot mic: the words land on idle, before Send-while-recording sends them",
  CONV.indexOf("box.value = written = D.joinText(_dictBase, words)") !== -1
  && CONV.indexOf("box.value = written = D.joinText(_dictBase, words)") < CONV.indexOf("if (send) { gui(_conv); return; }"));

if (fails.length) { console.log("\nFAIL - test_composer_dictate_after_stop: " + fails.length); process.exit(1); }
console.log("\nOK - test_composer_dictate_after_stop: all pass");
