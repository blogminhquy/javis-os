// 0.206.0: send more while Javis is working. Typed text during a running turn goes to the server as action "steer"
// (no more silent return), the send button comes back next to Stop when there is text, and the message's status line
// follows steer_ack / steer_read / steer_turn.
const fs = require("fs");
const path = require("path");
const R = path.join(__dirname, "../..");
const app = fs.readFileSync(path.join(R, "dashboard/app.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(R, "dashboard/i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(R, "dashboard/i18n/en.json"), "utf8"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

check("typed text during a turn is sent as an add-on, not dropped",
  /if \(!\(_tuGiong \|\| handsFree\)\) \{ guiBoSung\(msg, atts\); return; \}/.test(app)
  && !/if \(!\(_tuGiong \|\| handsFree\)\) return;/.test(app));
const g = app.slice(app.indexOf("function guiBoSung(msg, atts) {"), app.indexOf("function trangThaiBoSung(data) {"));
check("guiBoSung sends action steer with the chat id", /action: "steer", session_id: sid, message: chu, client_id: cid/.test(g));
check("the message shows at once with a status line, input cleared", /appendUserMessage\(msg, tep\)/.test(g)
  && /steer-note/.test(g) && /chatInput\.value = "";/.test(g));
check("files attached go along as their paths", /"\\uD83D\\uDCCE " \+ a\.path/.test(g));
check("the send button comes back next to Stop when there is text",
  // 0.231.0: outside a turn send shows only with text (voice chat sits there otherwise); tested in test_composer_dictate.js.
  /sendBtn\.style\.display = \(active \? boSung : coNoiDung\) \? "flex" : "none";/.test(app) && /if \(isProcessing\) syncActiveUI\(\);/.test(app));
check("not in a voice call (that has its own queue)", /isProcessing && !handsFreeActive\(\)/.test(app));
check("status frames handled and never revive a turn",
  /data\.type === "steer_ack" \|\| data\.type === "steer_read" \|\| data\.type === "steer_turn"/.test(app)
  && !/KHUNG_LUOT = \[[^\]]*steer/.test(app));
const keys = ["app.steer_send", "app.steer_sent", "app.steer_live", "app.steer_after", "app.steer_read", "app.steer_turn"];
check("strings in both languages", keys.every((k) => vi[k] && en[k]));
check("no long dashes in the new strings", keys.every((k) => !/[–—]/.test(vi[k] + en[k])));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
