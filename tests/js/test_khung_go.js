/* One-card composer (0.153.0): everything lives in #hudVoice and the old ids are kept.

       node tests/js/test_khung_go.js
*/
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const html = fs.readFileSync(path.join(ROOT, "dashboard/index.html"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard/style.css"), "utf8");
const consoleJs = fs.readFileSync(path.join(ROOT, "dashboard/console.js"), "utf8");
const mobile = fs.readFileSync(path.join(ROOT, "dashboard/mobile-chat.js"), "utf8");
const app = fs.readFileSync(path.join(ROOT, "dashboard/app.js"), "utf8");
const ws = fs.readFileSync(path.join(ROOT, "dashboard/workspace.js"), "utf8");
let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const card = (html.match(/<div class="hud-voice" id="hudVoice">[\s\S]*?<!-- \/hudVoice -->/) || [""])[0];
check("the #hudVoice card is found (ends with the <!-- /hudVoice --> marker)", !!card);
["voiceFocusResume", "attachBar", "fileInput", "chatInput", "cpRow", "plusBtn", "cpChips",
 "mbOpen", "effBtn", "effTxt", "fastBtn", "voiceBtn", "stopBtn", "sendBtn", "mbPop", "effPop", "plusMenu"].forEach(id => {
  check("the card contains #" + id, card.indexOf('id="' + id + '"') !== -1);
});
const order = ["attachBar", "chatInput", "cpRow"].map(id => card.indexOf('id="' + id + '"'));
check("attachments on top, text box in the middle, button row at the bottom", order[0] < order[1] && order[1] < order[2]);
const row = card.slice(card.indexOf('id="cpRow"'));
check("button row: + before the chips, mic and send at the end",
  row.indexOf('id="plusBtn"') < row.indexOf('id="cpChips"') && row.indexOf('id="cpChips"') < row.indexOf('id="voiceBtn"')
  && row.indexOf('id="voiceBtn"') < row.indexOf('id="sendBtn"'));
check("#attachBtn is gone from the page", html.indexOf('id="attachBtn"') === -1);
check("#modelBar stays, empty, right before the card", /<div class="model-bar" id="modelBar"><\/div>\s*(<!--[\s\S]*?-->\s*)*<div class="hud-voice" id="hudVoice">/.test(html));
check("no folder upload input (0.158.0: a folder is pinned, not uploaded)", card.indexOf('id="folderInput"') === -1);
check("the textarea keeps id first and rows=1", /<textarea id="chatInput"[^>]*rows="1"/.test(card));
check("no disabled attribute on #voiceBtn", !/id="voiceBtn"[^>]*disabled/.test(card));

check("CSS: the card stacks vertically, 24px corners before the --bg2 background",
  /\.hud-voice \{[^}]*flex-direction: column[^}]*align-items: flex-end[^}]*border-radius: 24px;[^}]*background: var\(--bg2\)/s.test(css));
check("CSS: an empty #modelBar is hidden", css.indexOf(".model-bar:empty { display: none; }") !== -1);
check("CSS: no old phone order rules left", css.indexOf(".hud-voice .attach-btn { order: 1;") === -1);

check("CHAT_NODE_IDS drops attachBar (it lives inside the card)",
  consoleJs.indexOf('const CHAT_NODE_IDS = ["callBar", "chatArea", "bgStrip", "modelBar", "hudVoice"];') !== -1);
check("Chat page cp-css uses 24px corners", consoleJs.indexOf(".chatpage-slot .hud-voice{ background:var(--bg2); border:1px solid var(--border); border-radius:24px; }") !== -1);

check("phone to desktop: the model chip goes back into #cpChips before #effBtn",
  mobile.indexOf('chipHost.insertBefore(mbOpen, document.getElementById("effBtn"))') !== -1
  && mobile.indexOf("mbPopHome.appendChild(mbPop)") !== -1);
check("app.js no longer calls #attachBtn directly", app.indexOf('document.getElementById("attachBtn").addEventListener') === -1);
check("Sources come from the first attachment that has sources (brain files have none)",
  app.indexOf("(atts.find(a => a.sources) || {}).sources") !== -1);
check("workspace locks + and send while the session is not ready", /\["plusBtn", "sendBtn"\]\.forEach/.test(ws));
const coding = fs.readFileSync(path.join(ROOT, "dashboard/coding.js"), "utf8");
check("the Coding page still inserts its chip row into #modelBar (shown because it is no longer empty)",
  coding.indexOf('getElementById("modelBar")') !== -1 && css.indexOf(".model-bar:empty { display: none; }") !== -1);

const slash = fs.readFileSync(path.join(ROOT, "dashboard/chat-slash.js"), "utf8");
check("the / menu anchors to the card (#hudVoice) and does not cover attachments",
  slash.indexOf('input.closest(".hud-voice") || input') !== -1);

// 0.160.0 follow-ups.
check("workspace locks send through a flag that app.js honours, so a turn update cannot re-enable it",
  /dataset\.wsLock/.test(ws) && // 0.206.0: during a turn the button unlocks for an add-on message (coTheGuiBoSung); the workspace flag still wins.
  /sendBtn\.disabled = \(isProcessing && !coTheGuiBoSung\(\)\) \|\| sendBtn\.dataset\.wsLock === "1"/.test(app)
  && /function setProcessing\(s\) \{[^}]*sendBtn\.dataset\.wsLock === "1"/.test(app));
check("leaving the page mid-turn does not re-enable send (workspace asks app.js to resync)", /JavisSyncActiveUI/.test(ws) && /window\.JavisSyncActiveUI = syncActiveUI/.test(app));
check("no CSS left for the old Effort row and separator", !/\.mb-eff-row|\.mb-eff-btn|\.mb-sep|\.mb-eff \{/.test(css));
check("mobile-chat.js has no unused modelBar variable", !/var modelBar = /.test(mobile));
if (fails.length) { console.log("\nFAIL - test_khung_go: " + fails.length); process.exit(1); }
console.log("\nOK - test_khung_go: all pass");
