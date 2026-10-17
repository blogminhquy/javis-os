// 0.202.1: a reminder pushed into the open chat with a voice note plays it at once (a "call"); other pushes do not.
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "../../dashboard/app.js"), "utf8");

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const m = src.match(/function ringReminder\(el, raw\) \{[\s\S]*?\n\}/);
check("ringReminder exists", !!m);
const ringReminder = new Function("return " + m[0])();
let played = 0;
const audio = { play() { played++; return { catch() {} }; } };
const el = { querySelector: (s) => (s === "audio.jv-audio" ? audio : null) };
ringReminder(el, '<!-- JAVIS_VIEC: {"kind": "reminder", "status": "done"} -->\nUống thuốc\n[🔊](attachments/voice/a.mp3)');
check("reminder with a voice note plays", played === 1);
ringReminder(el, '<!-- JAVIS_VIEC: {"kind": "task", "status": "done"} -->\nxong');
check("a task result does not ring", played === 1);
ringReminder({ querySelector: () => null }, '<!-- JAVIS_VIEC: {"kind": "reminder"} -->');
check("no player, no error", played === 1);
const blocked = { querySelector: () => ({ play() { throw new Error("NotAllowedError"); } }) };
let threw = false;
try { ringReminder(blocked, '<!-- JAVIS_VIEC: {"kind": "reminder"} -->'); } catch (e) { threw = true; }
check("autoplay blocked is swallowed", !threw);
// 0.203.0: a reminder marked "call" rings as an incoming call instead (test_incoming_call_0203.js).
check("called from the live push branch", /appendJavisMessage\(data\.content \|\| ""\);\s*recordTurn\("javis"[\s\S]{0,300}?ringReminder\(el, data\.content \|\| ""\);/.test(src));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
