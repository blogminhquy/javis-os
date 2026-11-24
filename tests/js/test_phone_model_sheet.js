/* Phone composer: model, Effort and the plan ring are three chips as on a computer (owner, 22/11/2026), and each opens
   the sheet from the bottom with ITS panel only. A computer keeps its three popovers.

       node tests/js/test_phone_model_sheet.js

Owner, 11/11/2026: "Ở điện thoại anh muốn sắp xếp lại mức suy luận và lựa chọn mô hình cũng như hiển thị mức dùng của gói
được gọn hơn", with the Claude app's "Fable 5.2 High" chip and its Select model sheet as the reference.
Owner, 22/11/2026: "ở điện thoại có đủ không gian để hiển thị để ấn thành 3 nút trên máy tính rồi, với cho text nhỏ hơn
một chút ở điện thoại để có thêm thông tin", and the Effort frame "đang bị lệch" (an empty "Recommended" row under it).
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
["cps.title", "cps.close", "cps.model"].forEach((k) => check("key " + k + " in vi and en", !!vi[k] && !!en[k]));

// ---- CSS ----
check("a computer: the wrappers have no box, so the popovers still place against the card",
  css.includes(".cp-sheet, .cp-sheet-card { display: contents; }") && css.includes(".cp-sheet-head { display: none; }"));
// The phone block of the composer: from its opening to the keyframes that follow it.
const phone = (css.match(/@media \(max-width: 860px\) \{\s*\.hud-voice \{[\s\S]*?\n\}\n@keyframes cps-fade/) || [""])[0];
check("the phone block of the composer is found", !!phone);
check("phone: the three chips stand apart (no joined pill any more)",
  !/#cpChips > \.cp-limit \{ order: -1;/.test(phone) && !/border-radius: 999px 0 0 999px/.test(phone)
  && !phone.includes("#cpChips > .mb-chip .mb-caret { display: none; }"));
check("phone: the chips are 34px tall with 13px text, so the whole model name fits",
  /#cpChips > \.mb-chip, #cpChips > \.cp-eff \{ height: 34px; padding: 0 8px; font-size: 13px; \}/.test(phone));
check("phone: the open sheet covers the screen above the other layers and dims it",
  /\.cp-sheet\.is-open \{[^}]*position: fixed; inset: 0;\s*z-index: 3400; background: var\(--scrim/.test(phone));
check("phone: the panels stop floating inside the sheet, and only the model list scrolls",
  /\.cp-sheet\.is-open \.mb-pop, \.cp-sheet\.is-open \.eff-pop \{ position: static; width: auto;/.test(phone)
  && /\.cp-sheet\.is-open \.mb-pop \{ flex: 1 1 auto;[^}]*overflow: auto;/.test(phone));
check("phone: no top padding over the sticky search, so no row shows through above it",
  /\.cp-sheet\.is-open \.mb-pop \{[^}]*padding: 0 8px 8px; \}/.test(phone)
  && /\.cp-sheet\.is-open \.mb-search \{ position: sticky; top: 0;/.test(phone));
check("phone: 16px in the search box (no iOS zoom), 15px rows still tall enough for a thumb",
  /\.cp-sheet\.is-open \.mb-search \{[^}]*font-size: 16px;/.test(phone) && /\.cp-sheet\.is-open \.mb-item \{ font-size: 15px; min-height: 44px;/.test(phone));
check("phone: the usage panel drops its own title (the sheet head says it)", phone.includes(".cp-sheet.is-open .lim-h { display: none; }"));
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
check("opening: the sheet moves to <body>, then draws only the panel asked for, under its own title",
  /document\.body\.appendChild\(s\);\s*s\.classList\.add\("is-open"\);/.test(blk)
  && /if \(part === "model"\) \{\s*pop\.hidden = false;/.test(blk)
  && /\} else if \(part === "eff"\) effMount\(\);/.test(blk) && /else \{ try \{ if \(window\.JavisPlanLimit[^}]*showInSheet\(\)/.test(blk)
  && blk.includes('const SHEET_TITLE = { model: "cps.model", eff: "eff.title", limit: "lim.title" };')
  && blk.includes("ttl.textContent = window.t(SHEET_TITLE[part]);"));
check("closing: every panel is hidden and the sheet goes back into the card",
  /s\.classList\.remove\("is-open"\);\s*if \(pop\) pop\.hidden = true;\s*effUnmount\(\);\s*closeLimit\(\);/.test(blk)
  && /sheetHome\.parent\.insertBefore\(s, next\);/.test(blk));
check("the card is a modal dialog only while it is a sheet",
  /card\.setAttribute\("role", "dialog"\);/.test(blk) && /\["role", "aria-modal", "aria-labelledby"\]\.forEach\(\(a\) => card\.removeAttribute\(a\)\)/.test(blk));
check("a window going wider than a phone closes the sheet", /if \(sheetIsOpen\(\) && !sheetMq\.matches\) sheetClose\(\);/.test(blk));
check("the head can be pulled down to close", /end\(dy > 70\)/.test(blk) && /#cpSheetHead/.test(blk));
check("each chip opens the sheet with its own panel; only the dim part or X closes it",
  /if \(chip\) \{ up \? sheetClose\(\) : sheetOpen\(chip\.id === "effBtn" \? "eff" : chip\.id === "limitBtn" \? "limit" : "model"\); return; \}/.test(mp)
  && /if \(e\.target\.closest\("#cpSheetClose"\) \|\| !e\.target\.closest\("#cpSheetCard"\)\) \{ sheetClose\(\); return; \}/.test(mp));
check("/model and the other callers reach the sheet through the same open() and close()",
  /function open\(\) \{[\s\S]{0,120}if \(sheetMode\(\)\) \{ sheetOpen\("model"\); return; \}/.test(mp)
  && /function effOpen\(\) \{[\s\S]{0,120}if \(sheetMode\(\)\) \{ sheetOpen\("eff"\); return; \}/.test(mp)
  && /function close\(\) \{\s*if \(sheetIsOpen\(\)\) \{ sheetClose\(\); return; \}/.test(mp)
  && /function effClose\(\) \{\s*if \(sheetIsOpen\(\)\) \{ sheetClose\(\); return; \}/.test(mp));
check("Escape closes the sheet and gives focus back to the chip that opened it",
  /if \(sheetIsOpen\(\)\) \{\s*const m = \$\(SHEET_CHIPS\[\["model", "eff", "limit"\]\.indexOf\(sheetPart\)\] \|\| "mbOpen"\);\s*sheetClose\(\); if \(m\) m\.focus\(\); return;/.test(mp));
check("a new model redraws an open Effort sheet (it may lock or unlock)", /if \(sheetIsOpen\(\) && sheetPart === "eff"\) effMount\(\);/.test(mp));

// ---- effort-slider.js: "Recommended" in the head, not a row that leaves a gap under the track ----
const es = fs.readFileSync(path.join(D, "effort-slider.js"), "utf8");
check("Recommended sits in the head beside the level", /<span class="eff-val"><\/span>' \+\s*(?:\/\/[^\n]*\n\s*)*\(opt\.locked \? "" : '<span class="eff-rec"><\/span>'\)/.test(es));
check("no Recommended row under the track any more", !es.includes('<div class="eff-rec">') && /rec\.hidden = value !== "medium";/.test(es)
  && css.includes(".eff-rec[hidden] { display: none; }"));

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
