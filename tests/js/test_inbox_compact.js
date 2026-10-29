/* Chatbot page, compact layout (0.397.0; owner, 2026-10-29, approved on the design canvas): on a computer smaller type,
   a "who" dropdown instead of four wrapping chips, the three modes in the chat head, Info closed until asked; on a phone
   icon-only tabs, a full-screen chat, the mode as a chip opening a sheet, a one-row composer.

       node tests/js/test_inbox_compact.js

   inbox-v5.js runs for real under node; conversations.js and inbox-compact.css are guarded by their structure.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const V5SRC = src("dashboard/inbox-v5.js");
const CV = src("dashboard/conversations.js");
const CSS = src("dashboard/inbox-compact.css");
const HTML = src("dashboard/index.html");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

const win = { t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : "") };
const ctx = { window: win, console, String, Object, Array, Number, JSON };
vm.createContext(ctx);
vm.runInContext(V5SRC, ctx);
const V = win.JavisInboxV5;
const I = (n) => "[" + n + "]";
const fn = (head) => { const i = CV.indexOf(head); return i < 0 ? "" : CV.slice(i, CV.indexOf("\n  }\n", i) + 4); };

// ---- 1. the mode chip and its sheet (phones) ----
const chip = V.modeChipHtml({ mode: "human" }, I);
check("chip: the current mode's icon, short name and a chevron, saying what it does when tapped",
  /class="ib-mchip m-human" aria-haspopup="dialog" aria-label="ib\.mchip_aria#ib\.m_human_s">\[hand\]<span>ib\.m_human_s<\/span>\[chevron-down\]/.test(chip));
check("chip: an unknown mode counts as A.I. replies", /m-ai/.test(V.modeChipHtml({ mode: "?" }, I)));
const sheet = V.modeSheetHtml({ mode: "draft" }, I);
check("sheet: a modal dialog with its title, over a backdrop that closes it", /class="ib-msheet-bg" data-close="1"/.test(sheet) &&
  /role="dialog" aria-modal="true" aria-labelledby="ibMsheetH"/.test(sheet) && /<h3 id="ibMsheetH">ib\.msheet_h<\/h3>/.test(sheet));
check("sheet: the three modes in order, each with a line on what it does, the current one checked",
  /data-m="ai"[\s\S]*data-m="draft"[\s\S]*data-m="human"/.test(sheet) && ["ai", "draft", "human"].every((m) => sheet.indexOf("ib.m_" + m + "_d") > 0) &&
  /class="ib-mso m-draft on" role="menuitemradio" aria-checked="true" data-m="draft"/.test(sheet) && (sheet.match(/aria-checked="false"/g) || []).length === 2);
check("sheet: ends with Customer info (a phone has no other Info button)", /class="ib-mso-info">\[info\]<span>ib\.info_t<\/span>/.test(sheet));

// ---- 2. conversations.js: the list head ----
check("the who button opens its menu; a choice closes it, saves, reloads and gives the focus back",
  /\.ib-whobtn"\)\.onclick = function \(\) \{ setPop\(_wm \? "" : "who"\); \};/.test(CV) &&
  /_who = b\.dataset\.who \|\| "";\s*setPop\(""\);\s*onFilterChange\(\);\s*focusOpener\("\.ib-whobtn"\);/.test(CV));
check("one popover at a time; a click outside or Escape closes the who menu too", /_pick = which === "pick"; _fm = which === "fm"; _wm = which === "who";/.test(CV) &&
  /t\.closest\("\.ib-whobtn"\)/.test(CV) && /var from = _pick \? "\.ib-picker" : _wm \? "\.ib-whobtn" : "\.ib-fbtn";/.test(CV));
check("the menu is drawn on the owner's action only, never by the 5-second refresh", /wm\.innerHTML = _wm \? V\.whoMenuHtml\(_who, _whoCounts, ic\) : "";/.test(fn("function paintPops() {")) &&
  !/whoMenuHtml/.test(fn("async function tai(")));
check("the button follows the counts on every refresh, redrawn only when it changed", /var wh = V\.whoButtonHtml\(_who, _whoCounts, ic\);\s*if \(wb\.dataset\.sig !== wh\)/.test(CV));
check("the channel picker is one line; the names behind it are its tooltip", /pb\.title = sub \? sum\.title \+ ": " \+ sub : sum\.title;/.test(CV) &&
  !/'<small>' \+ esc\(sub\)/.test(CV));
check("Filter sits inside the search box, with a spoken label", /<input class="ht-search"[\s\S]{0,200}'<button type="button" class="ib-fbtn"[^']*aria-label="' \+ esc\(window\.t\("ib\.f_aria"\)\)/.test(CV));

// ---- 3. rows ----
check("rows keep the message count and the unread number (owner, 2026-10-28 and 2026-10-29)",
  /'<span class="ht-count" title="'/.test(CV) && /'<span class="ht-badge" title="'/.test(CV));
check("rows: tags on a third line only when there are some; the nick in the tooltip, no line of its own",
  /\(userTags \? '<span class="ht-item-utags">' \+ userTags \+ '<\/span>' : ""\)/.test(CV) && /title="' \+ esc\(accName \? accName \+ " · " \+ say : say\)/.test(CV) &&
  !/ib-acc/.test(CV));

// ---- 4. the chat head, the bar, the sheet ----
const vt = CV.slice(CV.indexOf("  function veThread() {"), CV.indexOf("  // The phone's \"who replies\" sheet"));
check("head: the name with its tags (three, then +N) and a Tag button that opens Info with the tag picker",
  /F\.tagChips\(c\.tags, 3\)/.test(vt) && /class="ib-htag-add"/.test(vt) &&
  /\.ib-htag-add"\)\.onclick = function \(\) \{ _tagPop = true; _tagEdit = 0; _tagErr = ""; setInfo\(true\); \};/.test(vt));
check("head: channel, nick, group and the chat's message count under the name", /window\.t\("sess\.msgs", \{ count: soTin \}\)/.test(vt) &&
  /c\.message_count \|\| item\.message_count/.test(vt));
check("head: the modes and the chip only when the A.I. may answer here; Info is an icon button with a spoken label",
  /\(threeModes \? '<span class="ib-hmode"/.test(vt) && /class="s-btn-ghost ib-info-btn" aria-expanded="' \+ infoOpen\(\) \+ '" aria-label="'/.test(vt));
check("the head's tags follow every tag change made in Info", /function veTagRow\(\) \{\s*paintHeadTags\(\);/.test(CV) &&
  /F\.tagChips\(_conv\.tags, 3\)/.test(fn("function paintHeadTags() {")));
check("sheet: the chip opens it; a mode goes through setWho, Customer info opens Info; Escape closes it",
  /chip\.onclick = function \(\) \{ setSheet\(true\); \};/.test(vt) && /if \(b\.classList\.contains\("ib-mso"\)\) setWho\(c, b\.dataset\.m\);/.test(vt) &&
  /else if \(b\.classList\.contains\("ib-mso-info"\)\) setInfo\(true\);/.test(vt) && /if \(_msheet\) \{ setSheet\(false\); return; \}/.test(CV));
check("sheet: survives the 5-second redraw, drawn again from _msheet", /'<div class="ib-msheet"' \+ \(_msheet && threeModes \? "" : " hidden"\)/.test(vt));
check("closing the chat on a phone also closes Info and the sheet", /_infoN = false; _msheet = false;/.test(fn("function dongThread() {")));

// ---- 5. messages and composer ----
const tin = fn("function veTin(t) {");
check("who and when go under the bubble; a private chat's customer is not named again", tin.indexOf('class="ht-bubble"') < tin.indexOf('class="ht-msg-h"') &&
  /if \(lop === "khach" && _conv && _conv\.chat_type !== "group"\) ai = "";/.test(tin));
const comp = fn("function veCompose(c) {");
check("composer: one card; the draft sits on top of the box inside it", /'<div class="ib-cbox">' \+\s*\(draft && V \? V\.draftHtml/.test(comp) && /has-draft/.test(comp));
check("composer buttons keep a spoken label when a phone shows only their icons", /class="s-btn ht-send" aria-label="'/.test(comp) &&
  /'" aria-label="' \+ esc\(t\("ib\.ai_reply"\)\)/.test(comp));
check("the box grows with what is typed", /ta\.style\.height = "auto"; ta\.style\.height = ta\.scrollHeight \+ "px";/.test(CV));

// ---- 6. tabs ----
check("tabs: the name is the tooltip and stays readable to screen readers when a phone shows the icon only",
  /' title="' \+ esc\(ten\) \+ '">' \+ ic\(NHAN\[t\]\[1\]\) \+ ' <span class="ht-tab-t">'/.test(CV) && /aria-current="page"/.test(CV));

// ---- 7. CSS ----
check("index.html loads the compact sheet right after inbox-v5.css", HTML.indexOf("/static/inbox-compact.css") > HTML.indexOf("/static/inbox-v5.css") &&
  HTML.indexOf("/static/inbox-compact.css") - HTML.indexOf("/static/inbox-v5.css") < 80);
check("computer: 14px lists, 15px messages", /\.ib-v5 \{ font-size: 14px; \}/.test(CSS) && /\.ib-v5 \.ht-bubble \{ font-size: 15px;/.test(CSS));
check("messages and composer in a centred column", (CSS.match(/max\(16px, calc\(\(100% - 760px\) \/ 2\)\)/g) || []).length === 2);
check("a narrow chat column swaps the modes for the chip, hides the Info button behind it and the head's tags",
  /@container \(max-width: 540px\) \{\s*\.ib-hmode \{ display: none; \}\s*\.ib-mchip \{ display: inline-flex; \}\s*\.ht-head:has\(\.ib-mchip\) \.ib-info-btn \{ display: none; \}\s*\.ib-htags \{ display: none; \}/.test(CSS));
check("phones: no page title, icon-only tabs with the name kept for screen readers", /\.ht-page \.ht-title \{ display: none; \}/.test(CSS) &&
  /\.ht-page \.ht-tab-t \{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect\(0 0 0 0\);/.test(CSS));
check("phones: an open chat takes the whole page", /\.ht-page:has\(\.ht-wrap\.thread-on\) \.ht-top \{ display: none; \}/.test(CSS) &&
  /\.cview\.cview-hoi-thoai:has\(\.ht-wrap\.thread-on\) \.cview-body \{ padding: 0; \}/.test(CSS));
check("phones: one-row composer with round icon buttons, 16px text in the box and the bubbles", /\.ib-v5 \.ib-cin \{ flex-wrap: nowrap; \}/.test(CSS) &&
  /\.ib-v5 \.ib-cin \.s-btn span, \.ib-v5 \.ib-cin \.s-btn-ghost span \{ display: none; \}/.test(CSS) && /\.ib-v5 \.ht-bubble \{ font-size: 16px; \}/.test(CSS));
const sizes = [...CSS.matchAll(/font-size:\s*(\d+(?:\.\d+)?)px/g)].map((m) => +m[1]);
check("no text under 11px", sizes.length > 20 && sizes.every((n) => n >= 11), sizes.filter((n) => n < 11).join(","));

// ---- 8. words ----
const keys = ["ib.wq_you", "ib.wq_ai", "ib.wq_owner", "ib.wq_all", "ib.wq_you_d", "ib.wq_ai_d", "ib.wq_owner_d", "ib.wq_all_d", "ib.f_aria",
  "ib.mchip_aria", "ib.msheet_h", "ib.m_ai_d", "ib.m_draft_d", "ib.m_human_d", "ib.cin_ph_as", "ib.cin_ph_as_ai"];
check("every new key is in vi and en, under 100 characters", keys.every((k) => VI[k] && EN[k] && VI[k].length <= 100 && EN[k].length <= 100),
  keys.filter((k) => !VI[k] || !EN[k]).join(","));
check("Vietnamese writes A.I. with dots, English plain AI", keys.every((k) => !/(^|[^.A-Za-z])AI([^.A-Za-z]|$)/.test(VI[k]) && EN[k].indexOf("A.I.") < 0));
check("the composer's A.I. button says what it does: it drafts, it does not send", VI["ib.ai_reply"] === "A.I. soạn" && EN["ib.ai_reply"] === "AI draft");
check("keys nothing uses any more are gone", ["ib.who_all", "ht.gui_ten_ban", "ib.f_btn"].every((k) => !(k in VI) && !(k in EN)));
const dashes = [String.fromCharCode(0x2014), String.fromCharCode(0x2013)];
check("no em or en dash in the new sheet, this test or the new strings", ![CSS, fs.readFileSync(__filename, "utf8"), ...keys.map((k) => VI[k] + EN[k])]
  .some((t) => dashes.some((d) => t.indexOf(d) >= 0)));

if (fails.length) { console.log("FAIL - test_inbox_compact: " + fails.length + " loi: " + fails.join("; ")); process.exit(1); }
console.log("OK - test_inbox_compact: tat ca pass");
