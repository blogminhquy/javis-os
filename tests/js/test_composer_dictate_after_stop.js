/* The composer mic shows the words only after the recording ends (2026-11-05).

       node tests/js/test_composer_dictate_after_stop.js

   Owner, 2026-11-05: the mic icon should not copy the text onto the screen while speaking; it works like a voice
   recorder and the text comes out when the recording stops. These cases drive composer-dictate.js with a fake DOM and
   a fake dictate engine: nothing reaches the box while listening, the whole text lands once on idle, send-while-recording
   sends that text, and X leaves the box as it was. */
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
    joinText: D.joinText, ear: () => "", isIOS: () => false,
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

if (fails.length) { console.log("\nFAIL - test_composer_dictate_after_stop: " + fails.length); process.exit(1); }
console.log("\nOK - test_composer_dictate_after_stop: all pass");
