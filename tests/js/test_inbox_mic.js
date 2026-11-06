/* The mic in the Chatbot reply box (owner, 2026-11-05: "thêm cho anh một nút chép lời nhé, để mà anh có thể nói bằng
   giọng nói, sau đó là chép lại để khỏi phải gõ"). It reuses dictate.js, the engine of the team chat mic: the words
   land in the box, nothing is sent by itself.

       node tests/js/test_inbox_mic.js
*/
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const CV = fs.readFileSync(path.join(D, "conversations.js"), "utf8");
const CSS = fs.readFileSync(path.join(D, "inbox-compact.css"), "utf8");
const HTML = fs.readFileSync(path.join(D, "index.html"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(D, "i18n", "en.json"), "utf8"));
const Dict = require(path.join(D, "dictate.js"));

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

const comp = CV.slice(CV.indexOf("  function veCompose(c) {"), CV.indexOf("  async function gui(c) {"));
check("the reply box draws the mic next to the A.I. and Send buttons", /micHtml\(c\) \+/.test(comp) &&
  comp.indexOf("micHtml(c)") < comp.indexOf("ib-ask") && comp.indexOf("micHtml(c)") < comp.indexOf("ht-send"));
check("the mic shows for every chat, with or without a bot (not inside the laBot branch)",
  /'"><\/textarea>' \+\s*\n\s*micHtml\(c\) \+/.test(comp));

const vt = CV.slice(CV.indexOf("  function veThread() {"), CV.indexOf("  // The phone's \"who replies\" sheet"));
check("the redraw wires the mic and keeps the box read only while listening",
  /mic\.onclick = function \(\) \{ toggleMic\(c\); \}/.test(vt) && /ta\.readOnly = dictOn\(c\)/.test(vt));

const tm = CV.slice(CV.indexOf("  function toggleMic(c) {"), CV.indexOf("  function dropMic() {"));
check("it uses the shared engine and joins the words after what was typed",
  /window\.JavisDictate/.test(tm) && /D\.create\(/.test(tm) && /D\.joinText\(_dictBase, words\)/.test(tm) && /words = res\.words \|\| heard/.test(tm));
check("words only land in the chat the recording started in", /_chon !== _dictConv/.test(tm));
check("a second press stops listening", /_dictState === "listening"\) \{ _dict\.stop\(\); return; \}/.test(tm));
check("nothing is sent unless Send was pressed", /if \(send\) \{ gui\(_conv\); return; \}/.test(tm) && !/gui\(/.test(tm.replace("if (send) { gui(_conv); return; }", "")));
check("errors use the shared dictation notes (iPhone gets its own)", /dict\.denied_ios/.test(tm) && /dict\.service_ios/.test(tm) && /dict\.nothing/.test(tm));

const g = CV.slice(CV.indexOf("  async function gui(c) {"), CV.indexOf("  async function gui(c) {") + 300);
check("Send while listening stops first, then sends the final text", /if \(dictOn\(c\)\) \{ _dictSend = true;/.test(g));
check("opening another chat, closing it or leaving the page drops the recording",
  /_msheet = false; dropMic\(\); \}/.test(CV) && /function dongThread\(\) \{\s*\n\s*dropMic\(\);/.test(CV) && /closeRowMenu\(false\); dropMic\(\); return;/.test(CV));

check("labels exist in both languages", ["ib.mic", "ib.mic_stop", "ib.mic_busy"].every((k) => VI[k] && EN[k] && VI[k] !== EN[k]));
check("the mic is styled and turns red while listening", /\.ib-v5 \.ib-cin \.ib-mic \{/.test(CSS) && /\.ib-mic\.is-rec \{[^}]*--red/.test(CSS));
check("dictate.js is on the page that hosts the Chatbot", /\/static\/dictate\.js/.test(HTML) && /\/static\/conversations\.js/.test(HTML));
check("joinText appends after a typed start", Dict.joinText("Dạ chị", "em gửi ạ") === "Dạ chị em gửi ạ" && Dict.joinText("", " xin chào ") === "xin chào");

const dashes = [String.fromCharCode(0x2014), String.fromCharCode(0x2013)];
check("no em or en dash in the new code, strings or this test", ![fs.readFileSync(__filename, "utf8"), tm,
  VI["ib.mic"], VI["ib.mic_stop"], VI["ib.mic_busy"], EN["ib.mic"], EN["ib.mic_stop"], EN["ib.mic_busy"]]
  .some((t) => dashes.some((d) => t.indexOf(d) >= 0)));

if (fails.length) { console.log("FAIL - test_inbox_mic: " + fails.length + " loi: " + fails.join("; ")); process.exit(1); }
console.log("OK - test_inbox_mic: tat ca pass");
