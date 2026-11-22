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
["voiceFocusResume", "attachBar", "fileInput", "chatInput", "cpRow", "plusBtn", "cpRight", "cpUnder", "cpCtx", "cpChips",
 "mbOpen", "effBtn", "effTxt", "limitBtn", "voiceBtn", "stopBtn", "sendBtn", "mbPop", "effPop", "limitPop", "plusMenu"].forEach(id => {
  check("the card contains #" + id, card.indexOf('id="' + id + '"') !== -1);
});
const order = ["attachBar", "chatInput", "cpRow"].map(id => card.indexOf('id="' + id + '"'));
check("attachments on top, text box in the middle, button row at the bottom", order[0] < order[1] && order[1] < order[2]);
const row = card.slice(card.indexOf('id="cpRow"'));
// Owner, 21/11/2026 ("sắp xếp lại khung giống của Claude"): the card keeps +, mic and send; the chips sit under it.
const rowOnly = row.slice(0, row.indexOf('id="cpUnder"'));
check("button row: + first, then mic and send together on the right, no chip in the card's row",
  rowOnly.indexOf('id="plusBtn"') < rowOnly.indexOf('id="cpRight"') && rowOnly.indexOf('id="cpRight"') < rowOnly.indexOf('id="dictBtn"')
  && rowOnly.indexOf('id="dictBtn"') < rowOnly.indexOf('id="voiceBtn"') && rowOnly.indexOf('id="voiceBtn"') < rowOnly.indexOf('id="sendBtn"')
  && rowOnly.indexOf('id="cpChips"') === -1 && rowOnly.indexOf('id="cpCtx"') === -1);
// Owner, 22/11/2026 ("đưa folder và repo github lên khung trên ... dễ nhìn hơn trên điện thoại"): the pinned folder and
// the repos sit in a tray on top of the card, first in it; under the card only model, Effort and usage remain.
check("the tray of pinned folder and repos (#cpCtx) opens the card, hidden at first",
  /<div class="hud-voice" id="hudVoice">\s*(<!--[\s\S]*?-->\s*)*<div class="cp-ctx" id="cpCtx" hidden><\/div>/.test(card));
check("under the card: only model, Effort and usage (#cpChips), no folder or repo row",
  /<div class="cp-under" id="cpUnder">\s*<div class="cp-chips" id="cpChips">/.test(card));
check("#attachBtn is gone from the page", html.indexOf('id="attachBtn"') === -1);
check("#modelBar stays, empty, right before the card", /<div class="model-bar" id="modelBar"><\/div>\s*(<!--[\s\S]*?-->\s*)*<div class="hud-voice" id="hudVoice">/.test(html));
check("no folder upload input (0.158.0: a folder is pinned, not uploaded)", card.indexOf('id="folderInput"') === -1);
check("the textarea keeps id first and rows=1", /<textarea id="chatInput"[^>]*rows="1"/.test(card));
check("no disabled attribute on #voiceBtn", !/id="voiceBtn"[^>]*disabled/.test(card));

check("CSS: the card is ONE row (+, text, mic and send), 24px corners before the --bg2 background",
  /\.hud-voice \{[^}]*display: grid; grid-template-columns: auto minmax\(0, 1fr\) auto; align-items: end;[^}]*border-radius: 24px;[^}]*background: var\(--bg2\)/s.test(css)
  && css.includes(".hud-voice > .cp-row { display: contents; }")
  && css.includes(".hud-voice > .voice-input { grid-column: 2; grid-row: 2; min-height: 40px; padding: 8px 4px; line-height: 24px; }")
  && css.includes(".hud-voice .cp-plus { grid-column: 1; grid-row: 2; margin-bottom: 4px; }")
  && css.includes(".hud-voice .cp-right { grid-column: 3; grid-row: 2; display: flex; align-items: center; gap: 6px; min-height: 40px; }"));
// Owner, 22/11/2026 ("ở điện thoại đẩy lên dòng bên trên thì sẽ phù hợp hơn"): on a phone the text box takes the whole
// top line, so its placeholder stays on one line, and "+", mic and send sit on the line below. The rules above (one row)
// stay for a computer; the phone block overrides them.
const phoneCard = (css.match(/\n@media \(max-width: 860px\) \{\n  \.hud-voice \{[\s\S]*?\n\}/) || [""])[0];
check("CSS: a phone shows TWO rows, the box alone on top, + on the left and mic and send on the right below",
  phoneCard.includes(".hud-voice > .voice-input { grid-column: 1 / -1; grid-row: 2; padding: 8px 6px 4px; }")
  && phoneCard.includes(".hud-voice .cp-plus { grid-column: 1; grid-row: 3; align-self: center; margin-bottom: 0; }")
  && phoneCard.includes(".hud-voice .cp-right { grid-column: 3; grid-row: 3; }"));
check("CSS: dictating still wins on a phone (bar on the full second line), its rules outrank the phone ones",
  css.includes(".hud-voice.dictating .cp-right { grid-column: 1 / -1; grid-row: 3; }")
  && css.includes(".hud-voice.dictating > .voice-input { grid-column: 1 / -1; }"));
check("CSS: the row under the card hangs below its border and the card keeps room for it",
  /\.cp-under \{ position: absolute; top: calc\(100% \+ 2px\);/.test(css) && /margin: 4px 16px calc\(4px \+ var\(--cp-under-h\)\);/.test(css));
// 22/11/2026: the tray hangs on the card's top border (a grey tab, rounded top corners) and the card keeps its room
// above while the tray shows. With a row of its own, a phone keeps both names (no icons-only rule any more).
check("CSS: the tray sits on the card's top border and the card makes room for it",
  /\.hud-voice > \.cp-ctx \{ position: absolute; grid-column: auto; grid-row: auto; bottom: calc\(100% \+ 1px\);[^}]*border-bottom: 0;[^}]*border-radius: 16px 16px 0 0; background: var\(--bg3\)/.test(css)
  && css.includes(".hud-voice:has(> .cp-ctx:not([hidden])) { margin-top: calc(4px + var(--cp-ctx-h)); }")
  && /--cp-ctx-h: 40px;/.test(css));
check("CSS: a phone keeps the names of folder and repos when both are pinned",
  !css.includes(".cp-ctx.is-two .cp-pin-open > span, .cp-ctx.is-two .cp-pin > .gh-st { display: none; }")
  && !css.includes(".cp-ctx.is-two .cp-pin-open { width: 36px;"));
check("CSS: the X of a pin is always drawn, and reaches 44px tall on a touch screen",
  /\.cp-pin \.cp-pin-x \.cp-ic \{[^}]*background: var\(--bg3\)/.test(css) && !/\.cp-ctx\.is-two[^{]*\.cp-pin-x[^{]*\{[^}]*display: none/.test(css)
  && css.includes("@media (pointer: coarse) { .cp-pin-x { width: 34px; } .cp-pin-x::after { content: \"\"; position: absolute; inset: -5px 0; } }"));
check("CSS: an empty #modelBar is hidden", css.indexOf(".model-bar:empty { display: none; }") !== -1);
check("CSS: no old phone order rules left", css.indexOf(".hud-voice .attach-btn { order: 1;") === -1);

check("CHAT_NODE_IDS drops attachBar (it lives inside the card)",
  consoleJs.indexOf('const CHAT_NODE_IDS = ["callBar", "chatArea", "bgStrip", "goalBar", "modelBar", "hudVoice"];') !== -1);
check("Chat page cp-css uses 24px corners", consoleJs.indexOf(".chatpage-slot .hud-voice{ background:var(--bg2); border:1px solid var(--border); border-radius:24px; }") !== -1);

// 2026-11-09 (owner): the model chip stays in #cpChips right before #effBtn on every width; a phone no longer moves it.
check("the model chip sits in #cpChips right before #effBtn, and the phone script leaves it there",
  /<div class="cp-chips" id="cpChips">\s*<button type="button" class="mb-chip" id="mbOpen"[\s\S]*?<\/button>\s*<button type="button" class="cp-eff" id="effBtn"/.test(card)
  && !/getElementById\("mb(Open|Pop)"\)|insertBefore\(mb(Open|Pop)/.test(mobile));
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
