/* The composer's popovers open just above the row of chips, not above the whole card (2026-11-14).

       node tests/js/test_composer_pop_anchor.js

Owner, 14/11/2026: "bị lỗi việc ấn vào model trong khung cộng sự popup bị nhảy lên trên khá xa với khung khiến cho việc lựa
chọn model bị khó khăn". The model list, Effort, plan usage and the + menu were placed against the top of the composer
card, so a tall card (a file attached, a few lines typed) left them about 220px above the chip, and a long model list ran
past the top of the chat column, which cut its first rows off. The Team chat's + menu and its folder and GitHub panels had
the same anchoring and follow the same rule (docs/quy-uoc-dev.md: a composer change is applied to every chat screen).
*/
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const html = fs.readFileSync(path.join(D, "index.html"), "utf8");
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
const mp = fs.readFileSync(path.join(D, "model-picker.js"), "utf8");
const tm = fs.readFileSync(path.join(D, "teams.js"), "utf8");
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + extra));
  if (!cond) fails++;
}

// ---- markup: the row is a direct child of the card, so its offsetTop is measured against the card ----
const card = (html.match(/<div class="hud-voice" id="hudVoice">[\s\S]*?<!-- \/hudVoice -->/) || [""])[0];
check("the composer card is found", !!card);
check("the four popovers live in the card", ["mbPop", "effPop", "limitPop", "plusMenu"].every((id) => card.includes('id="' + id + '"')));
const top = card.replace(/<!--[\s\S]*?-->/g, "");
check("#cpRow is a direct child of the card (opened right after the text box)",
  /<\/textarea>\s*<div class="cp-row" id="cpRow">/.test(top));

// ---- CSS ----
check("in the card the popovers take their bottom from --cp-pop-bottom (the old place is the fallback)",
  css.includes(".hud-voice .mb-pop, .hud-voice .eff-pop, .hud-voice .cp-menu { bottom: var(--cp-pop-bottom, calc(100% + 6px)); }"));
check("the model list and the + menu stop at the room above the row",
  css.includes(".hud-voice .mb-pop { max-height: min(62vh, var(--cp-pop-room, 62vh)); }")
  && css.includes(".hud-voice .cp-menu { max-height: min(60vh, 440px, var(--cp-pop-room, 60vh)); }"));
check("the phone sheet still wins (static panels with no height cap)",
  /\.cp-sheet\.is-open \.mb-pop, \.cp-sheet\.is-open \.eff-pop \{ position: static; width: auto; max-height: none;/.test(css));

// ---- model-picker.js: static ----
const blk = (mp.match(/\/\/ POP_ANCHOR_BEGIN[\s\S]*?\/\/ POP_ANCHOR_END/) || [""])[0];
check("the anchor block is found", !!blk);
check("it covers the model list, Effort, plan usage and the + menu",
  blk.includes('const ANCHORED_POPS = ["mbPop", "effPop", "limitPop", "plusMenu"];'));
check("placed the moment one is shown, whoever shows it",
  /new MutationObserver\(/.test(blk) && blk.includes('attributeFilter: ["hidden"]'));
check("placed again when the card or the window changes size", /new ResizeObserver\(/.test(blk) && blk.includes('addEventListener("resize"'));

// ---- model-picker.js: run the block against a fake page ----
// The Partner page of the report: header 52px, the console view clips from 52px, a card 258px tall whose chip row starts
// 210px into it and sits at 884px on screen.
function fakePage(o) {
  const vars = {};
  const clip = { getBoundingClientRect: () => ({ top: o.clipTop }), parentElement: null, overflow: "hidden" };
  const plain = { getBoundingClientRect: () => ({ top: 0 }), parentElement: clip, overflow: "visible" };
  const body = {};
  clip.parentElement = body;
  const cardEl = { clientHeight: o.cardH, parentElement: plain, style: { setProperty: (k, v) => { vars[k] = v; } } };
  const row = { offsetTop: o.rowTop, offsetParent: cardEl, getBoundingClientRect: () => ({ top: o.rowScreenTop }) };
  const pops = { mbPop: { hidden: false }, effPop: { hidden: true }, limitPop: { hidden: true }, plusMenu: { hidden: true } };
  const els = Object.assign({ hudVoice: cardEl, cpRow: row }, pops);
  const document = {
    readyState: "complete", body,
    querySelector: (s) => (s === ".hud-top" ? { getBoundingClientRect: () => ({ height: 52, bottom: 52 }) } : null),
    addEventListener: () => {},
  };
  const getComputedStyle = (el) => ({ overflowX: el.overflow, overflowY: el.overflow });
  const window = { addEventListener: () => {} };
  function MutationObserver() { this.observe = () => {}; }
  function ResizeObserver() { this.observe = () => {}; }
  const api = new Function("$", "document", "getComputedStyle", "window", "MutationObserver", "ResizeObserver",
    blk + "\nreturn { placePops, anyPopOpen };")((id) => els[id] || null, document, getComputedStyle, window, MutationObserver, ResizeObserver);
  return { api, vars, pops };
}
let run = null;
try { run = fakePage({ clipTop: 52, cardH: 258, rowTop: 210, rowScreenTop: 884 }); } catch (e) { check("the block runs", false, String(e)); }
if (run) {
  run.api.placePops();
  check("bottom: 6px above the chip row, not above the card (258 - 210 + 6 = 54px)", run.vars["--cp-pop-bottom"] === "54px", run.vars["--cp-pop-bottom"]);
  check("room: from the row up to the visible top, less the gap and a margin (884 - 6 - 52 - 8 = 818px)",
    run.vars["--cp-pop-room"] === "818px", run.vars["--cp-pop-room"]);
  check("an open popover is seen as open", run.api.anyPopOpen() === true);
  run.pops.mbPop.hidden = true;
  check("all closed: nothing to place", run.api.anyPopOpen() === false);
}
// A box that clips lower than the header wins: the popover must stop inside it.
try {
  const r2 = fakePage({ clipTop: 300, cardH: 80, rowTop: 38, rowScreenTop: 500 });
  r2.api.placePops();
  check("the lowest clipping top wins (500 - 6 - 300 - 8 = 186px)", r2.vars["--cp-pop-room"] === "186px", r2.vars["--cp-pop-room"]);
  const r3 = fakePage({ clipTop: 52, cardH: 80, rowTop: 38, rowScreenTop: 120 });
  r3.api.placePops();
  check("never squeezed below a few rows (160px)", r3.vars["--cp-pop-room"] === "160px", r3.vars["--cp-pop-room"]);
} catch (e) { check("the block runs on other layouts", false, String(e)); }

// ---- Team chat: the same rule ----
const draw = (tm.match(/function drawComposer\(\) \{[\s\S]*?\n {2}\}\n/) || [""])[0];
check("Team chat: the open + menu is placed after the composer is drawn",
  /grow\(box\.querySelector\("\.tm-input"\)\);[\s\S]*?if \(S\.plusOpen\) placePlusMenu\(box\);/.test(draw));
check("Team chat: the + menu sits 6px above the + button",
  /function placePlusMenu\(box\) \{[\s\S]*?menu\.style\.bottom = Math\.max\(0, box\.clientHeight - pb\.offsetTop \+ 6\) \+ "px";/.test(tm));
check("Team chat: the folder and GitHub panels open above the + button too",
  (tm.match(/placeAbovePlus\(pop, comp\);/g) || []).length === 2 && !tm.includes("window.innerHeight - r.top"));

const dash = String.fromCharCode(0x2014), nd = String.fromCharCode(0x2013);
const cssBlk = (css.match(/\/\* In the composer card \(owner, 14\/11\/2026\)[\s\S]*?var\(--cp-pop-room, 60vh\)\); \}/) || [""])[0];
check("the CSS block is found", !!cssBlk);
check("no em or en dash in the new code", ![blk, cssBlk].some((s) => s.includes(dash) || s.includes(nd)));
if (fails) { console.log("\nFAIL - test_composer_pop_anchor: " + fails); process.exit(1); }
console.log("\nOK - test_composer_pop_anchor: all pass");
