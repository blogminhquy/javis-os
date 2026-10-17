// 0.203.0: Javis calls you at a set time. A reminder push marked "call" rings the open chat as an incoming call;
// answering presses the mic and the call's first line asks Javis to read the reminder aloud.
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "../../dashboard");
const IC = require(path.join(D, "incoming-call.js"));
const app = fs.readFileSync(path.join(D, "app.js"), "utf8");
const html = fs.readFileSync(path.join(D, "index.html"), "utf8");
const cons = fs.readFileSync(path.join(D, "console.js"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(D, "i18n/vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(D, "i18n/en.json"), "utf8"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

const raw = '<!-- JAVIS_VIEC: {"kind": "reminder", "status": "done", "title": "Báo cáo sáng", "id": "r_1", "call": "1"} -->\n'
  + "Doanh thu hôm qua 12 triệu\n\n[🔊 Tin thoại](attachments/voice/a.mp3)";
const c = IC.parse(raw);
check("a call reminder is recognised", !!c && c.title === "Báo cáo sáng");
check("text to read drops hidden blocks and the voice link", c && c.text === "Doanh thu hôm qua 12 triệu");
check("a plain reminder does not ring", IC.parse(raw.replace(', "call": "1"', "")) === null);
check("a failed reminder does not ring", IC.parse(raw.replace('"done"', '"failed"')) === null);
check("a task result does not ring", IC.parse(raw.replace('"reminder"', '"task"')) === null);
check("broken block ignored", IC.parse('<!-- JAVIS_VIEC: {"kind": -->') === null && IC.parse("") === null);
check("long text capped", IC.parse(raw.replace("12 triệu", "x".repeat(5000))).text.length <= 1500);

const t = (k) => vi[k] || k;
const line = IC.script(c, t);
check("first line names the call and carries the text", line.includes("Báo cáo sáng") && line.includes("12 triệu"));
check("untitled call gets a default title", IC.script({ title: "", text: "a" }, t).includes(vi["call.in_title_none"]));

const keys = ["call.in_label", "call.in_title_none", "call.in_answer", "call.in_decline", "call.in_script",
  "cs.si_rem_call", "cs.si_rem_call_hint", "cs.si_rem_call_tag"];
check("strings in both languages", keys.every((k) => vi[k] && en[k]));
check("no long dashes in the new strings", keys.every((k) => !/[\u2013\u2014]/.test(vi[k] + en[k])));

check("script loaded before app.js", html.indexOf("incoming-call.js") > 0 && html.indexOf("incoming-call.js") < html.indexOf("/static/app.js"));
check("push branch rings a call before the plain voice-note autoplay",
  /if \(!daGoi\) ringReminder\(el, data\.content \|\| ""\);/.test(app));
// 0.204.0: it rings whichever chat is open, not only when the reminder's own chat is the open one.
const pushBranch = app.slice(app.indexOf('if (data.type === "push") {'), app.indexOf("if (isActive) {", app.indexOf('if (data.type === "push") {')));
check("call rings before the open-chat check", /const daGoi = goiDenTheoLich\(data\.content \|\| ""\);/.test(pushBranch));
const fn = app.match(/function goiDenTheoLich\(raw\) \{[\s\S]*?\n\}/);
check("goiDenTheoLich exists", !!fn);
check("already in a call: nothing rings", fn && /if \(!c \|\| handsFree\) return false;/.test(fn[0]));
check("answer presses the mic", fn && /voiceBtn\.click\(\)/.test(fn[0]));
check("Live call opens with the reminder line", /if \(handsFree\) batLive\(layMoDauGoiDen\(\)\);/.test(app)
  && /function layMoDauGoiDen\(\) \{ const s = _goiDenMoDau; _goiDenMoDau = ""; return s; \}/.test(app));
check("basic voice sends the line as the first message", fn && /if \(handsFree\) sendMessage\(moDau\)/.test(fn[0]));
check("Work page has the Call me box", cons.includes('id="lpRemCall"') && cons.includes("call: call") && cons.includes('f.append("call"'));

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nPASS");
