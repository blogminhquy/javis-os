/* The dictation mics write the words in the chat box, and the box ends with the REWRITTEN sentence (2026-11-06).

       node tests/js/test_composer_dictate_in_box.js

   Owner, 2026-11-06: in the old version the words appeared right in the chat box, not in a bubble above like an
   answer; and when the recording ends (stop, Enter, Send) a model rewrites what was heard into the sentence meant,
   and that is what is shown or sent. These cases drive composer-dictate.js with a fake DOM and a fake dictate engine
   (the rewrite itself is dictate.js, see test_dictate_polish.js): on a computer the box follows the words while
   speaking, the final text replaces them on idle, send-while-recording sends the final text, X restores the box, a
   phone sees nothing until the end, and no faded bubble is drawn. The team chat and Chatbot mics are checked on their
   source. */
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
    joinText: D.joinText, isPhoneUA: D.isPhoneUA, recentMessages: D.recentMessages, ear: () => "", isIOS: () => false,
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
const bubble = [];
global.window.nhapGiong = t => { bubble.push(t); };
const setUA = ua => Object.defineProperty(global, "navigator", { value: { userAgent: ua }, configurable: true, writable: true });
const PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36";
const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
const ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36";

// Computer: the words follow in the box, the rewritten sentence replaces them at the end.
setUA(PC);
inp.value = "Ghi chú:";
els.dictBtn.click();
check("pressing the mic starts the engine", engine && engine.started === 1);
check("the engine is given the chat context", typeof engine.opts.context === "function");
engine.opts.onState("listening");
engine.opts.onText("tôi bị", false);
check("computer: the box shows the words while speaking, after the typed text", inp.value === "Ghi chú: tôi bị");
engine.opts.onText("tôi bị học chữ ở đây", false);
check("computer: the box follows the growing sentence", inp.value === "Ghi chú: tôi bị học chữ ở đây");
els.dictStop.click();
check("stop asks the engine to stop", engine.stopped === 1);
engine.opts.onState("transcribing");
engine.opts.onText("Tôi bị lỗi chữ ở đây.", true);
check("transcribing: the final text waits for idle", inp.value === "Ghi chú: tôi bị học chữ ở đây");
engine.opts.onState("idle");
check("idle: the rewritten sentence replaces what was heard", inp.value === "Ghi chú: Tôi bị lỗi chữ ở đây.");
check("the box can be edited again", inp.readOnly === false);
check("no faded bubble is drawn", bubble.length === 0);

// X drops the recording: the box goes back to what was typed.
inp.value = "giữ nguyên";
els.dictBtn.click();
engine.opts.onState("listening");
engine.opts.onText("bỏ câu này", false);
check("computer: X starts from the words in the box", inp.value === "giữ nguyên bỏ câu này");
els.dictCancel.click();
check("X: the typed text stays, nothing heard is kept", inp.value === "giữ nguyên" && engine.cancelled === 1);

// Send while recording: stop, wait for the rewritten sentence, then send it.
inp.value = "";
sent = 0;
let sentValue = "";
els.sendBtn.addEventListener("click", () => { sentValue = inp.value; });
els.dictBtn.click();
engine.opts.onState("listening");
engine.opts.onText("gửi luôn nhé travis", false);
els.hudVoice.dispatchEvent({ type: "click", target: { closest: () => els.sendBtn },
  preventDefault() {}, stopPropagation() {} });
check("send while recording stops first, nothing sent yet", engine.stopped === 1 && sent === 0);
engine.opts.onState("transcribing");
engine.opts.onText("Gửi luôn nhé Javis.", true);
check("send: still not sent while the sentence is rewritten", sent === 0);
engine.opts.onState("idle");
check("send: the REWRITTEN sentence is what is sent", sent === 1 && sentValue === "Gửi luôn nhé Javis.");

// Phones keep the words for the end (owner, 2026-11-05).
[["iPhone", IPHONE], ["Android phone", ANDROID]].forEach(([name, ua]) => {
  setUA(ua);
  inp.value = "";
  els.dictBtn.click();
  engine.opts.onState("listening");
  engine.opts.onText("tôi bị học", false);
  check(name + ": nothing in the box while speaking", inp.value === "");
  els.dictStop.click();
  engine.opts.onState("transcribing");
  engine.opts.onText("Tôi bị học.", true);
  engine.opts.onState("idle");
  check(name + ": the rewritten sentence lands at the end", inp.value === "Tôi bị học.");
});
check("no faded bubble on any device", bubble.length === 0);

// The team chat and Chatbot mics follow the same rule.
const fs = require("fs");
const TEAMS = fs.readFileSync(path.join(ROOT, "dashboard/teams.js"), "utf8");
const CONV = fs.readFileSync(path.join(ROOT, "dashboard/conversations.js"), "utf8");
const COMP = fs.readFileSync(path.join(ROOT, "dashboard/composer-dictate.js"), "utf8");
[["team chat", TEAMS], ["Chatbot", CONV], ["main chat", COMP]].forEach(([name, src]) => {
  check(name + " mic: no faded bubble, no word-level live fix", !/createLiveFix|fixAfter|drawDictDraft|nhapGiong\(/.test(src));
  check(name + " mic: gives the chat's recent messages as context", /context: (dictContext|chatContext)/.test(src)
    && /recentMessages\(/.test(src));
  check(name + " mic: writes the box live only on a computer, never the final text early",
    /var live = !\(D\.isPhoneUA && D\.isPhoneUA\(\)\);/.test(src) && /!final && live|final \|\| !live/.test(src));
});
check("team chat mic: the final words land on idle, before Send-while-recording sends them",
  TEAMS.indexOf("inp0.value = D.joinText(S.dictBase, heard)") !== -1
  && TEAMS.indexOf("inp0.value = D.joinText(S.dictBase, heard)") < TEAMS.indexOf("if (sendNow) { send(); return; }"));
const convIdle = CONV.indexOf("if (box && heard) {");
check("Chatbot mic: the final words land on idle, before Send-while-recording sends them",
  convIdle !== -1 && convIdle < CONV.indexOf("if (send) { gui(_conv); return; }"));

if (fails.length) { console.log("\nFAIL - test_composer_dictate_in_box: " + fails.length); process.exit(1); }
console.log("\nOK - test_composer_dictate_in_box: all pass");
