/* Enter in the customer reply box (Chatbot page) and while dictating follows the main chat's rule (0.398.0; owner,
   2026-10-29: "ấn enter trên điện thoại nó gửi luôn mà không có cách xuống được dòng"): on a phone Enter is a new
   line and the Send button sends; on a computer Enter sends and Shift+Enter is a new line; an IME never sends.

       node tests/js/test_inbox_enter.js

   The rule itself runs for real (chat-acts.js); conversations.js and composer-dictate.js are guarded by their wiring.
*/
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const A = require(path.join(D, "chat-acts.js"));
const CV = fs.readFileSync(path.join(D, "conversations.js"), "utf8");
const DICT = fs.readFileSync(path.join(D, "composer-dictate.js"), "utf8");
const VI = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
const EN = JSON.parse(fs.readFileSync(path.join(D, "i18n", "en.json"), "utf8"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

const touch = { matchMedia: (q) => ({ matches: q === "(pointer: coarse)" }) };
const mouse = { matchMedia: () => ({ matches: false }) };
const key = (o) => Object.assign({ key: "Enter", shiftKey: false, keyCode: 13, isComposing: false }, o);

// ---- the shared rule ----
check("phone: Enter is a new line", A.enterSends(key(), false, touch) === false);
check("computer: Enter sends, Shift+Enter is a new line", A.enterSends(key(), false, mouse) === true &&
  A.enterSends(key({ shiftKey: true }), false, mouse) === false);
check("touchMain is shared so the placeholder can say the right thing", A.touchMain(touch) === true && A.touchMain(mouse) === false);

// ---- the reply box ----
const vt = CV.slice(CV.indexOf("  function veThread() {"), CV.indexOf("  // The phone's \"who replies\" sheet"));
check("the reply box asks the shared rule, with its own IME tracking", /var A = window\.JavisActs, soan = A \? A\.trackComposition\(ta\)/.test(vt) &&
  /var send = A \? A\.enterSends\(e, soan\(\)\)/.test(vt) && /if \(send\) \{ e\.preventDefault\(\); gui\(c\); \}/.test(vt));
check("CANARY: no Enter-sends-always handler left in the Chatbot page",
  !/if \(e\.key === "Enter" && !e\.shiftKey && !e\.isComposing\) \{ e\.preventDefault\(\); gui\(c\); \}/.test(CV));
const comp = CV.slice(CV.indexOf("  function veCompose(c) {"), CV.indexOf("  async function gui(c) {"));
check("a phone's placeholder does not say 'Enter to send'", /t\(laBot \? "ib\.cin_ph_ai" : cham \? "ib\.cin_ph_touch" : "ht\.gui_ph"\)/.test(comp) &&
  !/Enter/.test(VI["ib.cin_ph_touch"]) && !/Enter/.test(EN["ib.cin_ph_touch"]));
check("the box's spoken label names it, without key hints", /aria-label="' \+ esc\(t\("ib\.cin_aria"\)\)/.test(comp) &&
  !/Enter/.test(VI["ib.cin_aria"]) && !/Enter/.test(EN["ib.cin_aria"]));

// ---- dictation ----
check("dictating: Enter sends the recording only where Enter sends a message", /var sends = window\.JavisActs \? window\.JavisActs\.enterSends\(e, false\)/.test(DICT) &&
  /if \(sends && e\.target === \$\("chatInput"\)\)/.test(DICT));

const dashes = [String.fromCharCode(0x2014), String.fromCharCode(0x2013)];
check("no em or en dash in this test or the new strings", ![fs.readFileSync(__filename, "utf8"), VI["ib.cin_ph_touch"], EN["ib.cin_ph_touch"],
  VI["ib.cin_aria"], EN["ib.cin_aria"]].some((t) => dashes.some((d) => t.indexOf(d) >= 0)));

if (fails.length) { console.log("FAIL - test_inbox_enter: " + fails.length + " loi: " + fails.join("; ")); process.exit(1); }
console.log("OK - test_inbox_enter: tat ca pass");
