/* Enter while dictating stops and sends in one press (owner 2026-11-05), in the main chat, the customer inbox and the
   Team chat. Before, pressing the mic left the focus on the page (the main chat hides the mic while recording, the
   inbox redraws it), so Enter landed on <body> and did nothing: stop had to be pressed first.

       node tests/js/test_dictate_enter_sends.js
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const read = f => fs.readFileSync(path.join(ROOT, f), "utf8");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// ───────────── main chat: which focused element turns Enter into "stop and send" ─────────────
const CD = require(path.join(ROOT, "dashboard/composer-dictate.js"));
const ids = { input: "chatInput", cancel: "dictCancel", stop: "dictStop" };
const inCard = new Set();
const card = { contains: el => inCard.has(el) };
const el = (tagName, id, inside) => { const e = { tagName, id: id || "" }; if (inside) inCard.add(e); return e; };

check("Enter in the text box sends", CD.enterSendsFrom(el("TEXTAREA", "chatInput", true), ids, card) === true);
check("Enter with the focus on the page (mic hidden while recording) sends",
  CD.enterSendsFrom(el("BODY"), ids, card) === true && CD.enterSendsFrom(el("HTML"), ids, card) === true);
check("Enter with no target at all sends", CD.enterSendsFrom(null, ids, card) === true);
check("Enter on the mic or the send button of the composer sends",
  CD.enterSendsFrom(el("BUTTON", "dictBtn", true), ids, card) === true
  && CD.enterSendsFrom(el("BUTTON", "sendBtn", true), ids, card) === true);
check("X and stop reached with Tab keep their own meaning",
  CD.enterSendsFrom(el("BUTTON", "dictCancel", true), ids, card) === false
  && CD.enterSendsFrom(el("BUTTON", "dictStop", true), ids, card) === false);
check("another field elsewhere on the page keeps its Enter",
  CD.enterSendsFrom(el("INPUT", "searchBox"), ids, card) === false
  && CD.enterSendsFrom(el("BUTTON", "navLink"), ids, card) === false);

const cdSrc = read("dashboard/composer-dictate.js");
check("main chat: the keydown listener uses enterSendsFrom, not only the text box",
  /enterSendsFrom\(e\.target, \{ input: "chatInput", cancel: "dictCancel", stop: "dictStop" \}, card\)/.test(cdSrc)
  && !/sends && e\.target === \$\("chatInput"\)/.test(cdSrc));
check("main chat: Enter still follows the phone rule (JavisActs.enterSends)", /JavisActs\.enterSends\(e, false\)/.test(cdSrc));

// ───────────── customer inbox ─────────────
const conv = read("dashboard/conversations.js");
check("inbox: a document Enter listener is set up when the mic starts",
  /function watchDictEnter\(\)/.test(conv) && /watchDictEnter\(\);\n\s*paintMic\(\);\n\s*dict\.start\(\);/.test(conv));
check("inbox: it accepts the page, the reply box and the mic, then calls gui",
  /tag === "BODY" \|\| tag === "HTML" \|\| tg === replyBox\(\)/.test(conv) && /contains\("ib-mic"\)/.test(conv)
  && /e\.preventDefault\(\); e\.stopPropagation\(\);\n\s*gui\(_conv\);/.test(conv));
check("inbox: gui while recording still waits for the last words", /if \(dictOn\(c\)\) \{ _dictSend = true;/.test(conv));

// ───────────── Team chat ─────────────
const teams = read("dashboard/teams.js");
check("team: send while recording stops and waits instead of sending a half-heard sentence",
  /if \(S\.dict && S\.dictState !== "idle"\) \{\n\s*S\.dictSend = true;\n\s*if \(S\.dict\.active\(\)\) S\.dict\.stop\(\);\n\s*return;/.test(teams));
check("team: the end of the recording sends when it was asked to",
  /var sendNow = st === "idle" && was !== "idle" && S\.dictSend;/.test(teams) && /if \(sendNow\) \{ send\(\); return; \}/.test(teams));
check("team: Enter on the recording mic sends instead of only stopping",
  /var onMic = S\.dictState !== "idle" && e\.target\.classList && e\.target\.classList\.contains\("tm-mic"\);/.test(teams));

if (fails.length) { console.log("\n" + fails.length + " failed"); process.exit(1); }
console.log("\nall ok");
