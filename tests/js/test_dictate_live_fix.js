/* The faded live bubble shows the words as fixed by POST /stt/fix (2026-11-06).

       node tests/js/test_dictate_live_fix.js

   Drives composer-dictate.js with a fake DOM, a fake dictate engine and a fake /stt/fix that turns "Jarvis" into
   "Javis". Pins: on a computer the bubble first shows the words as heard, then the fixed text; new words keep the
   fixed part in front; one request at a time; the box gets the fixed text on stop; a failing server leaves the words
   as heard; a phone never calls the server while speaking but still gets its box fixed after stop; send while
   recording sends at once and the box is not swapped afterwards. */
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const tick = () => new Promise(r => setTimeout(r, 0));

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
let sentValues = [];
els.sendBtn.addEventListener("click", () => { sentValues.push(els.chatInput.value); });

let engine = null;
const D = require(path.join(ROOT, "dashboard/dictate.js"));
global.Event = function (type) { this.type = type; };
global.document = {
  readyState: "complete", hidden: false, activeElement: null,
  getElementById: id => els[id] || null,
  addEventListener() {},
};
const bubble = [];
global.window = {
  addEventListener() {},
  matchMedia: () => ({ matches: false }),
  nhapGiong: t => { bubble.push(t); },
  JavisDictate: {
    joinText: D.joinText, createLiveFix: D.createLiveFix, fixAfter: D.fixAfter, ear: () => "", isIOS: () => false,
    create(opts) {
      engine = { opts, stopped: 0, start() {}, stop() { this.stopped++; }, cancel() { opts.onState("idle"); } };
      return engine;
    },
  },
};
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
global.setInterval = () => 1;
global.clearInterval = () => {};
global.getComputedStyle = () => ({ color: "#fff" });
const setUA = ua => Object.defineProperty(global, "navigator", { value: { userAgent: ua }, configurable: true, writable: true });
const DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36";
const ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36";

// Fake /stt/fix. `hold` keeps answers waiting until release() is called.
let calls = [], mode = "ok", held = [];
global.fetch = (url, opts) => {
  const text = JSON.parse(opts.body).text;
  calls.push({ url, text });
  if (mode === "fail") return Promise.reject(new Error("down"));
  const answer = { ok: true, text: text.replace(/Jarvis/g, "Javis") };
  const res = { json: () => Promise.resolve(answer) };
  if (mode === "hold") return new Promise(r => held.push(() => r(res)));
  return Promise.resolve(res);
};
const release = async () => { const h = held; held = []; h.forEach(f => f()); await tick(); await tick(); };

require(path.join(ROOT, "dashboard/composer-dictate.js"));
const inp = els.chatInput;
const begin = () => { els.dictBtn.click(); engine.opts.onState("listening"); };
const end = async () => { els.dictStop.click(); engine.opts.onState("idle"); await tick(); await tick(); };

(async () => {
  // 1. Computer: heard words at once, then the fixed text.
  setUA(DESKTOP); calls = []; mode = "ok"; inp.value = "";
  begin();
  engine.opts.onText("tôi hỏi Jarvis OS", false);
  check("computer: the bubble shows the words as heard at once", bubble[bubble.length - 1] === "tôi hỏi Jarvis OS");
  await tick(); await tick();
  check("computer: /stt/fix is asked with the heard words",
    calls.length === 1 && calls[0].url === "/stt/fix" && calls[0].text === "tôi hỏi Jarvis OS");
  check("computer: then the bubble shows the fixed text", bubble[bubble.length - 1] === "tôi hỏi Javis OS");
  // New words: the fixed part stays in front while the next answer is on its way.
  mode = "hold";
  engine.opts.onText("tôi hỏi Jarvis OS hôm nay", false);
  check("computer: new words keep the fixed part in front", bubble[bubble.length - 1] === "tôi hỏi Javis OS hôm nay");
  engine.opts.onText("tôi hỏi Jarvis OS hôm nay thế nào", false);
  engine.opts.onText("tôi hỏi Jarvis OS hôm nay thế nào nhé", false);
  check("computer: one request at a time", calls.length === 2);
  await release();
  check("computer: words heard meanwhile ask once more, with the latest words",
    calls.length === 3 && calls[2].text === "tôi hỏi Jarvis OS hôm nay thế nào nhé");
  await release();
  check("computer: the bubble ends with the latest fixed text",
    bubble[bubble.length - 1] === "tôi hỏi Javis OS hôm nay thế nào nhé");
  mode = "ok";
  await end();
  check("computer: stop writes the fixed text into the box", inp.value === "tôi hỏi Javis OS hôm nay thế nào nhé");
  check("computer: the bubble is cleared", bubble[bubble.length - 1] === "");

  // 2. Stop before the answer came: the box gets the words as heard, then the fixed text.
  calls = []; mode = "hold"; inp.value = "";
  begin();
  engine.opts.onText("gọi Jarvis", false);
  els.dictStop.click(); engine.opts.onState("idle");
  check("stop before the answer: the box holds the words as heard", inp.value === "gọi Jarvis");
  await release(); await release();
  check("stop before the answer: the box is swapped for the fixed text", inp.value === "gọi Javis");
  check("stop before the answer: the late answer does not reopen the bubble", bubble[bubble.length - 1] === "");

  // 3. The owner edits the box before the fix arrives: the edit wins.
  calls = []; mode = "hold"; inp.value = "";
  begin();
  engine.opts.onText("gọi Jarvis", false);
  els.dictStop.click(); engine.opts.onState("idle");
  inp.value = "gọi Jarvis nhé";
  await release(); await release();
  check("an edit made before the fix arrives is never overwritten", inp.value === "gọi Jarvis nhé");

  // 4. Server down: the words as heard, no error.
  calls = []; mode = "fail"; inp.value = "";
  begin();
  engine.opts.onText("Jarvis ơi", false);
  await tick(); await tick();
  check("server down: the bubble keeps the words as heard", bubble[bubble.length - 1] === "Jarvis ơi");
  await end();
  check("server down: the box gets the words as heard", inp.value === "Jarvis ơi");

  // 5. Send while recording: sent at once, the box is not swapped afterwards.
  calls = []; mode = "ok"; inp.value = ""; sentValues = [];
  begin();
  engine.opts.onText("gửi Jarvis", false);
  await tick(); await tick();
  mode = "hold";
  engine.opts.onText("gửi Jarvis luôn", false);
  els.hudVoice.dispatchEvent({ type: "click", target: { closest: () => els.sendBtn }, preventDefault() {}, stopPropagation() {} });
  engine.opts.onState("idle");
  check("send while recording: sent at once with the fixed part in front", sentValues[0] === "gửi Javis luôn");
  const n = calls.length;
  await release(); await release();
  check("send while recording: no fix request after sending", calls.length === n);

  // 6. Android phone: no request while speaking (no bubble), the box is fixed after stop.
  setUA(ANDROID); calls = []; mode = "ok"; inp.value = "";
  begin();
  engine.opts.onText("Jarvis ơi", false);
  await tick(); await tick();
  check("phone: no /stt/fix call while speaking", calls.length === 0);
  await end();
  check("phone: the box gets the fixed text after stop", calls.length === 1 && inp.value === "Javis ơi");

  // 7. Teams and the Chatbot inbox use the same shared fix (docs/quy-uoc-dev.md: a chat composer change reaches
  // every chat screen). Checked on their source: the faded bubble, put back after a redraw, and the final fix.
  const fs = require("fs");
  const TEAMS = fs.readFileSync(path.join(ROOT, "dashboard/teams.js"), "utf8");
  const CONV = fs.readFileSync(path.join(ROOT, "dashboard/conversations.js"), "utf8");
  const CSS = fs.readFileSync(path.join(ROOT, "dashboard/console.css"), "utf8");
  check("Teams: the mic feeds dictate.js createLiveFix", /D\.createLiveFix\(function \(t\) \{ drawDictDraft\(/.test(TEAMS));
  check("Teams: the draft bubble only shows in the team the recording started in", /S\.activeId === forTeam \? t : ""/.test(TEAMS));
  check("Teams: a redraw puts the bubble back", /drawDictDraft\(S\.dictLive\.text\(\)\)/.test(TEAMS));
  check("Teams: the last words are fixed after stop when not sent", /D\.fixAfter\(res,/.test(TEAMS));
  check("Chatbot: the mic feeds dictate.js createLiveFix", /D\.createLiveFix\(function \(t\) \{ drawDictDraft\(/.test(CONV));
  check("Chatbot: the draft bubble only shows in the chat the recording started in", /_chon === forConv \? t : ""/.test(CONV));
  check("Chatbot: the 5-second redraw puts the bubble back", /drawDictDraft\(_dictLive\.text\(\)\)/.test(CONV));
  check("Chatbot: leaving the chat drops the bubble", /if \(_dictLive\) \{ _dictLive\.cancel\(\); _dictLive = null; \}/.test(CONV));
  check("Chatbot: the last words are fixed after stop when not sent", /D\.fixAfter\(res,/.test(CONV));
  check("both draft bubbles are faded and dashed",
    /\.tm-msg-draft \.tm-bubble \{ opacity: \.62; border-style: dashed; \}/.test(CSS) &&
    /\.ht-msg-draft \.ht-bubble \{ opacity: \.62; border-style: dashed; \}/.test(CSS));

  // 8. The shared helper on its own: a phone never draws, a cancel removes the bubble.
  setUA(DESKTOP); mode = "ok";
  const drawn = [];
  const lf = D.createLiveFix(t => drawn.push(t));
  lf.start(); lf.heard("Jarvis ơi"); await tick(); await tick();
  check("createLiveFix: heard words, then the fixed text", drawn.join("|") === "|Jarvis ơi|Javis ơi" && lf.text() === "Javis ơi");
  lf.cancel();
  check("createLiveFix: cancel removes the bubble and stops", drawn[drawn.length - 1] === "" && !lf.active() && lf.text() === "");
  setUA(ANDROID);
  const drawnPhone = [];
  const lp = D.createLiveFix(t => drawnPhone.push(t));
  lp.start(); lp.heard("Jarvis ơi"); await tick();
  const fin = lp.finish();
  check("createLiveFix on a phone: nothing drawn, the words need a fix after stop",
    drawnPhone.length === 0 && fin.words === "Jarvis ơi" && fin.needsFix === true);

  if (fails.length) { console.log("\nFAIL - test_dictate_live_fix: " + fails.length); process.exit(1); }
  console.log("\nOK - test_dictate_live_fix: all pass");
})();
