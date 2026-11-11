/* Phone composer (2026-11-11): the plan ring, the model chip and the Effort chip read as ONE pill, and a tap on any of
   them opens ONE sheet from the bottom with plan usage, Effort and the model list. A computer keeps its three popovers.

       node tests/js/test_phone_model_sheet.js

Owner, 11/11/2026: "Ở điện thoại anh muốn sắp xếp lại mức suy luận và lựa chọn mô hình cũng như hiển thị mức dùng của gói
được gọn hơn", with the Claude app's "Fable 5.2 High" chip and its Select model sheet as the reference.
*/
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const html = fs.readFileSync(path.join(D, "index.html"), "utf8");
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
const mp = fs.readFileSync(path.join(D, "model-picker.js"), "utf8");
const pl = fs.readFileSync(path.join(D, "plan-limit.js"), "utf8");
const vi = require(path.join(D, "i18n", "vi.json")), en = require(path.join(D, "i18n", "en.json"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + extra));
  if (!cond) fails++;
}

// ---- markup ----
const card = (html.match(/<div class="hud-voice" id="hudVoice">[\s\S]*?<!-- \/hudVoice -->/) || [""])[0];
const sheet = (card.match(/<div class="cp-sheet" id="cpSheet">[\s\S]*?<div class="cp-menu" id="plusMenu"/) || [""])[0];
check("the sheet wrapper lives in the composer card, before the + menu", !!sheet);
check("it wraps the three panels a computer opens one by one",
  ["mbPop", "effPop", "limitPop"].every((id) => sheet.indexOf('id="' + id + '"') !== -1)
  && /<div class="cp-sheet-card" id="cpSheetCard">/.test(sheet));
check("the head has a close button and a title, both through i18n",
  /id="cpSheetClose"[^>]*data-i18n-title="cps\.close"[^>]*data-i18n-aria="cps\.close"/.test(sheet)
  && /id="cpSheetTitle" data-i18n="cps\.title"/.test(sheet));
check("the three chips are still three buttons in #cpChips (a computer shows them apart)",
  ["mbOpen", "effBtn", "limitBtn"].every((id) => card.indexOf('id="' + id + '"') !== -1));
["cps.title", "cps.close"].forEach((k) => check("key " + k + " in vi and en", !!vi[k] && !!en[k]));

// ---- CSS ----
check("a computer: the wrappers have no box, so the popovers still place against the card",
  css.includes(".cp-sheet, .cp-sheet-card { display: contents; }") && css.includes(".cp-sheet-head { display: none; }"));
// The phone block of the composer: from its opening to the keyframes that follow it.
const phone = (css.match(/@media \(max-width: 860px\) \{\s*\.hud-voice \{[\s\S]*?\n\}\n@keyframes cps-fade/) || [""])[0];
check("the phone block of the composer is found", !!phone);
check("phone: the ring leads the pill and each part drops the border it shares",
  /#cpChips > \.cp-limit \{ order: -1;[^}]*border-right: 0; border-radius: 999px 0 0 999px; \}/.test(phone)
  && /#cpChips > \.mb-chip \{[^}]*border-right: 0; border-radius: 999px 0 0 999px;/.test(phone)
  && /#cpChips\.has-ring > \.mb-chip \{[^}]*border-left: 0; border-radius: 0; \}/.test(phone)
  && /#cpChips > \.cp-eff \{[^}]*border-left: 0; border-radius: 0 999px 999px 0;/.test(phone));
check("phone: one caret for the pill, and the plain green dot gives way to the ring (the amber one stays)",
  phone.includes("#cpChips > .mb-chip .mb-caret { display: none; }")
  && phone.includes("#cpChips.has-ring > .mb-chip:not(.is-fallback):not(.is-pin-broken) .mb-dot { display: none; }"));
check("phone: the pill is 34px tall with 14px text", /#cpChips > \.cp-limit, #cpChips > \.mb-chip, #cpChips > \.cp-eff \{\s*height: 34px; font-size: 14px;/.test(phone));
check("phone: the open sheet covers the screen above the other layers and dims it",
  /\.cp-sheet\.is-open \{[^}]*position: fixed; inset: 0;\s*z-index: 3400; background: var\(--scrim/.test(phone));
check("phone: the panels stop floating and stack as usage, Effort, model list",
  /\.cp-sheet\.is-open \.mb-pop, \.cp-sheet\.is-open \.eff-pop \{ position: static; width: auto;/.test(phone)
  && /\.cp-sheet\.is-open \.lim-pop \{ order: 1;/.test(phone) && /\.cp-sheet\.is-open #effPop \{ order: 2;/.test(phone)
  && /\.cp-sheet\.is-open \.mb-pop \{ order: 3; flex: 1 1 auto;[^}]*overflow: auto;/.test(phone));
check("phone: 16px in the search box (no iOS zoom) and rows tall enough for a thumb",
  /\.cp-sheet\.is-open \.mb-search \{[^}]*font-size: 16px;/.test(phone) && /\.cp-sheet\.is-open \.mb-item \{ font-size: 16px; min-height: 46px;/.test(phone));
check("phone: a usage meter is one line over a thin bar",
  /\.cp-sheet\.is-open \.lim-row \{ display: grid; grid-template-columns: auto minmax\(0, 1fr\) auto;/.test(phone)
  && phone.includes(".cp-sheet.is-open .lim-row-h { display: contents; }")
  && /\.cp-sheet\.is-open \.lim-bar \{ grid-row: 2; grid-column: 1 \/ -1; height: 6px;/.test(phone));
check("phone, keyboard up: the sheet follows the visible part and the two fixed panels step aside",
  phone.includes("body.kb-open .cp-sheet.is-open { top: var(--vv-top, 0px); bottom: auto; height: var(--vv-h, 100dvh); }")
  && phone.includes("body.kb-open .cp-sheet.is-open .lim-pop, body.kb-open .cp-sheet.is-open #effPop { display: none; }"));
check("reduced motion: no slide", /@media \(prefers-reduced-motion: reduce\) \{\s*\.cp-sheet\.is-open, \.cp-sheet\.is-open \.cp-sheet-card \{ animation: none; transition: none; \}/.test(css));

// ---- model-picker.js ----
const blk = (mp.match(/\/\/ SHEET_BEGIN[\s\S]*?\/\/ SHEET_END/) || [""])[0];
check("the sheet block is found", !!blk);
check("the sheet is for the same width as the rest of the phone layout (860px)", blk.includes('window.matchMedia("(max-width: 860px)")'));
check("opening: the sheet moves to <body>, then all three panels are drawn",
  /document\.body\.appendChild\(s\);\s*s\.classList\.add\("is-open"\);/.test(blk) && /pop\.hidden = false;/.test(blk)
  && /effMount\(\);/.test(blk) && /JavisPlanLimit\.showInSheet\(\)/.test(blk));
check("closing: every panel is hidden and the sheet goes back into the card",
  /s\.classList\.remove\("is-open"\);\s*if \(pop\) pop\.hidden = true;\s*effUnmount\(\);\s*closeLimit\(\);/.test(blk)
  && /sheetHome\.parent\.insertBefore\(s, next\);/.test(blk));
check("the card is a modal dialog only while it is a sheet",
  /card\.setAttribute\("role", "dialog"\);/.test(blk) && /\["role", "aria-modal", "aria-labelledby"\]\.forEach\(\(a\) => card\.removeAttribute\(a\)\)/.test(blk));
check("a window going wider than a phone closes the sheet", /if \(sheetIsOpen\(\) && !sheetMq\.matches\) sheetClose\(\);/.test(blk));
check("the head can be pulled down to close", /end\(dy > 70\)/.test(blk) && /#cpSheetHead/.test(blk));
check("a tap on any of the three chips toggles the one sheet; only the dim part or X closes it",
  /if \(e\.target\.closest\("#mbOpen, #effBtn, #limitBtn"\)\) \{ up \? sheetClose\(\) : sheetOpen\(\); return; \}/.test(mp)
  && /if \(e\.target\.closest\("#cpSheetClose"\) \|\| !e\.target\.closest\("#cpSheetCard"\)\) \{ sheetClose\(\); return; \}/.test(mp));
check("/model and the other callers reach the sheet through the same open() and close()",
  /function open\(\) \{[\s\S]{0,120}if \(sheetMode\(\)\) \{ sheetOpen\(\); return; \}/.test(mp)
  && /function close\(\) \{\s*if \(sheetIsOpen\(\)\) \{ sheetClose\(\); return; \}/.test(mp)
  && /function effClose\(\) \{\s*if \(sheetIsOpen\(\)\) \{ sheetClose\(\); return; \}/.test(mp));
check("Escape closes the sheet", /if \(sheetIsOpen\(\)\) \{ sheetClose\(\); const m = \$\("mbOpen"\); if \(m\) m\.focus\(\); return; \}/.test(mp));
check("a model picked in the sheet redraws the slider (it may lock or unlock)", /if \(sheetIsOpen\(\)\) effMount\(\);/.test(mp));

// ---- plan-limit.js ----
check("the ring tells the row it is there (the pill rounds its left end on it)",
  pl.includes('btn.parentElement.classList.toggle("has-ring", !!c.brain)'));
check("the ring leaves its click and Escape to the sheet on a phone",
  /document\.addEventListener\("click", function \(e\) \{\s*if \(sheetOwns\(\)\) return;/.test(pl)
  && /e\.key === "Escape" && popOpen\(\) && !sheetOwns\(\)/.test(pl) && /sheetOwns: function \(\) \{ return sheetMode\(\) \|\| sheetIsOpen\(\); \}/.test(mp));
check("the usage panel can be shown inside the sheet without closing the others",
  /function showInSheet\(\) \{[\s\S]*?p\.hidden = false;[\s\S]*?paintPop\(\);\s*refresh\(true, true\);/.test(pl)
  && !/function showInSheet\(\) \{[^}]*closeAll/.test(pl) && pl.includes("api.showInSheet = showInSheet;"));
check("in the sheet the percent stands alone, with the full wording kept for a tooltip and screen readers",
  /pctEl\.textContent = inSheet \? ws\[i\]\.pct \+ "%" : used;/.test(pl) && /pctEl\.setAttribute\("aria-label", used\)/.test(pl));

const dash = String.fromCharCode(0x2014), nd = String.fromCharCode(0x2013);
check("no em or en dash in the new code", ![blk, phone, sheet].some((s) => s.includes(dash) || s.includes(nd)));
if (fails) { console.log("\nFAIL - test_phone_model_sheet: " + fails); process.exit(1); }
console.log("\nOK - test_phone_model_sheet: all pass");
