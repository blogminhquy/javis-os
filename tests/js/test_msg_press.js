// 0.179.0: long press a message on a touch screen (dashboard/msg-press.js), main chat and Teams.
//
//     node tests/js/test_msg_press.js
"use strict";
const fs = require("fs");
const { napTruoc, coNap } = require("./_thu_tu_nap");   // load order that understands lazy groups (0.417.0)
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const MP = require(path.join(D, "msg-press.js"));
const JR = require(path.join(D, "reactions.js"));
const src = fs.readFileSync(path.join(D, "msg-press.js"), "utf8");
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
const indexHtml = fs.readFileSync(path.join(D, "index.html"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(D, "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(D, "i18n", "en.json"), "utf8"));
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

let p = MP.place(200, 500, 300, 58, 390, 800, 120);
check("emoji row sits above the finger, centred", p.top === 500 - 58 - 28 && p.left === 50, JSON.stringify(p));
p = MP.place(10, 500, 300, 58, 390, 800, 0);
check("emoji row never leaves the screen on the left or right", p.left === 8 && MP.place(385, 500, 300, 58, 390, 800, 0).left === 82);
p = MP.place(200, 40, 300, 58, 390, 800, 0);
check("finger near the top: the row goes below the finger", p.top === 68, JSON.stringify(p));
p = MP.place(200, 760, 300, 58, 390, 800, 200);
check("finger near the bottom: the row stays above the action card", p.top <= 800 - 200 - 58 - 12, JSON.stringify(p));

const h = MP.layerHtml(JR.EMOJI, "love", [{ icon: "reply", label: "Trả lời <b>" }, { icon: "copy", label: "Sao chép" }]);
check("layer: dim area, six emoji with names, the current one marked, actions escaped",
  h.includes('class="mp-scrim" data-mp-close="1"') && (h.match(/class="mp-pick/g) || []).length === 6
  && /mp-pick is-on" data-mp-react="love"/.test(h) && h.includes('<span class="mp-tip">' + vi["teams.react.like"] + "</span>")
  && h.includes("Trả lời &lt;b&gt;") && (h.match(/class="mp-act"/g) || []).length === 2, h);
check("own message: no emoji row, only actions", !MP.layerHtml(null, "", [{ icon: "copy", label: "x" }]).includes("mp-bar"));

check("hold time is short (Zalo feel) and finger jitter cancels it", MP.HOLD_MS <= 400 && /var MOVE_TOL = 10;/.test(src));
check("touch events, not pointer events (iOS cancels the pointer stream when its own long press starts)",
  /addEventListener\("touchstart", onStart, \{ passive: true \}\)/.test(src) && /addEventListener\("touchmove", onMove, \{ passive: false \}\)/.test(src)
  && !/pointerdown/.test(src));
check("slide to pick: the emoji under the finger grows, lifting on it reacts, scrolling is held",
  /elementFromPoint\(p\.clientX, p\.clientY\)/.test(src) && /if \(hot\) return pick\(hot\.getAttribute\("data-mp-react"\)\)/.test(src)
  && /if \(e\.cancelable\) e\.preventDefault\(\);\s*var under/.test(src));
check("the click iOS fires after lifting does not close the card it just opened", /Date\.now\(\) - openedAt > 350/.test(src));
check("CSS: Teams messages and reaction buttons not selectable on touch screens (no iOS callout), hot emoji grows with its name",
  /@media \(hover: none\), \(pointer: coarse\) \{\s*\.mp-host \.tm-msg, \.mp-host \.jr-rx-btn, \.mp-host \.tm-rx-btn \{ -webkit-user-select: none; user-select: none; -webkit-touch-callout: none;/.test(css)
  && /\.mp-pick\.is-hot \{ transform: translateY\(-14px\) scale\(1\.55\);/.test(css) && css.includes(".mp-pick.is-hot .mp-tip { opacity: 1; }"));
check("the held message is drawn bright above the dim layer, with its own classes and a solid backing",
  /function lift\(el\)/.test(src) && /copy\.className = String\(el\.className\)/.test(src) && /lift\(el\);/.test(src)
  && /\.mp-layer \.mp-lift \{[^}]*background: var\(--bg\)/.test(css));
check("an action can say it is done (Copy shows a short note)", /toast\(a\.done\)/.test(src) && css.includes(".mp-toast {"));
const cr = fs.readFileSync(path.join(D, "chat-reactions.js"), "utf8");
const tm = fs.readFileSync(path.join(D, "teams.js"), "utf8");
check("main chat and Teams name their bubble for the lifted copy", /bubble: "\.bubble",/.test(cr) && /bubble: "\.tm-bubble",/.test(tm));
const ccss = fs.readFileSync(path.join(D, "console.css"), "utf8");
// 0.182.0
check("holding the reaction button opens the menu too (main chat and Teams), its tap is swallowed",
  /var onBtn = opts\.holdOn && t\.closest\(opts\.holdOn\);/.test(src) && /if \(!onBtn && t\.closest\("button, a,/.test(src)
  && /holdOn: "\.jr-rx-btn",/.test(cr) && /holdOn: "\.tm-rx-btn",/.test(tm));
check("the chat never scrolls sideways (phone: app felt loose)",
  /\.transcript \{\s*flex: 1 1 auto; overflow-y: auto; overflow-x: hidden; overscroll-behavior-x: none;/.test(css)
  && /\.tm-msgs \{[^}]*overflow-x: hidden; overscroll-behavior-x: none;/.test(ccss)
  && css.includes("@media (max-width: 860px) { .jr-rx { right: 4px; } }"));
check("no hover bridge over the like button, and the pill opens on keyboard focus only, not on a tap",
  !/\.jr-rx-bar::after/.test(css) && !/\.tm-rx-bar::after/.test(ccss)
  && css.includes(".jr-rx-bar::before { content: \"\"; position: absolute; inset: -18px -22px -4px; z-index: -1; }")
  && /\.jr-rx:has\(:focus-visible\) \.jr-rx-bar/.test(css) && !/\.jr-rx:focus-within/.test(css)
  && /\.tm-rx:has\(:focus-visible\) \.tm-rx-bar/.test(ccss) && !/\.tm-rx:focus-within/.test(ccss));
const pos = (f) => indexHtml.indexOf("/static/" + f);
// 0.184.0 (owner, iPhone): the hold ended in iOS's own text selection, its handle on "Trả lời" in the card.
check("iPhone: the card, the lifted copy and the whole message (time row too) are not selectable; fields still are",
  css.includes(".mp-layer, .mp-layer *, html.mp-holding, html.mp-holding * { -webkit-user-select: none; user-select: none; -webkit-touch-callout: none;")
  && /\.mp-host \.tm-msg :is\(input, textarea, \[contenteditable\]\)[^{]*\{ -webkit-user-select: text; user-select: text; \}/.test(css));
check("iPhone: a hold in progress or an open card refuses iOS's selection and clears one already made",
  /function onSelect\(e\) \{ if \(timer \|\| \(layer && !inLift\(e\.target\)\)\) e\.preventDefault\(\); \}/.test(src)
  && /document\.addEventListener\("selectstart", onSelect\)/.test(src) && /document\.removeEventListener\("selectstart", onSelect\)/.test(src)
  && /sliding = !!bar;\s*unselect\(\);/.test(src) && /removeAllRanges\(\)/.test(src));
check("Android: the browser menu is refused on the whole document (it lands on the card, not on root)",
  /document\.addEventListener\("contextmenu", onMenu\)/.test(src) && /document\.removeEventListener\("contextmenu", onMenu\)/.test(src)
  && !/root\.addEventListener\("contextmenu"/.test(src));
check("every browser: html.mp-holding while the card is open (not on every scroll start, no page-wide restyle)",
  /classList\.toggle\("mp-holding", !!layer\)/.test(src) && /sliding = !!bar;\s*unselect\(\);\s*holding\(\);/.test(src)
  && /document\.removeEventListener\("keydown", onEsc, true\);\s*holding\(\);/.test(src));
// 0.240.0 (owner, Zalo screenshot): Copy only took the whole message. Hold the lifted copy a second time to select part.
let f = MP.frame(300, 120, 560);
check("lifted copy: a short bubble stays where it sat", f.top === 300 && f.height === 120 && f.scroll === 0, JSON.stringify(f));
f = MP.frame(500, 120, 560);
check("lifted copy: a bubble under the card moves up above it", f.top === 440 && f.height === 120, JSON.stringify(f));
f = MP.frame(-400, 1500, 560);
check("lifted copy: a long message fills the space and scrolls to where it sat",
  f.top === 8 && f.height === 552 && f.scroll === 408, JSON.stringify(f));
check("lifted copy: never scrolled past its end", MP.frame(-3000, 1500, 560).scroll === 1500 - 552);
check("second hold: the lifted copy turns selectable only once the first finger is off",
  /if \(layer && \(!e\.touches \|\| !e\.touches\.length\)\) setFree\(\);/.test(src)
  && /document\.addEventListener\("touchstart", onAnyStart, \{ passive: true \}\)/.test(src)
  && /document\.removeEventListener\("touchstart", onAnyStart\)/.test(src) && /layer\.classList\.add\("is-free"\)/.test(src));
check("second hold: selection and the browser menu are allowed inside the lifted copy, still refused elsewhere",
  /function onSelect\(e\) \{ if \(timer \|\| \(layer && !inLift\(e\.target\)\)\) e\.preventDefault\(\); \}/.test(src)
  && /function onMenu\(e\) \{ if \(timer \|\| \(layer && !inLift\(e\.target\)\)\) e\.preventDefault\(\); \}/.test(src)
  && /free && node && node\.closest && node\.closest\("\.mp-lift"\)/.test(src));
check("second hold: a tap in the copy does not follow its links, closing clears the selection",
  /if \(inLift\(e\.target\)\) \{ e\.preventDefault\(\); e\.stopPropagation\(\); return; \}/.test(src)
  && /layer\.remove\(\); layer = null; unselect\(\);/.test(src));
check("CSS: the free copy is selectable with the phone's callout and scrolls when long",
  css.includes(".mp-layer.is-free .mp-lift { pointer-events: auto; }")
  && css.includes(".mp-layer.is-free .mp-lift, .mp-layer.is-free .mp-lift * { -webkit-user-select: text; user-select: text; -webkit-touch-callout: default; }")
  && /\.mp-layer \.mp-lift \{[^}]*overflow-y: auto;/.test(css));
check("iPhone: turning the phone sideways and back does not leave the text bigger (text-size-adjust)",
  /html \{[^}]*-webkit-text-size-adjust: 100%;\s*text-size-adjust: 100%;/.test(css));
check("index.html loads msg-press.js before chat-reactions.js and teams.js", pos("msg-press.js?v=") > 0
  && napTruoc("msg-press.js", ["chat-reactions.js", "teams.js"]));
// 0.266.0 (owner, iPhone): in the main chat the dimmed Reply / Copy card made copying harder. Holding the text is the
// phone's own selection and Copy again; only the reaction corner opens the emoji row there. Teams keeps the full menu.
check("main chat: only the reaction corner opens the menu, no action card, messages selectable with the phone's callout",
  /if \(opts\.holdOnly && !onBtn\) return;/.test(src) && /holdOn: "\.jr-rx-btn",\s*holdOnly: true,/.test(cr)
  && !/actions:/.test(cr) && !/pressActions|mpress\./.test(cr) && !/holdOnly/.test(tm) && /actions: function \(m\)/.test(tm)
  && !/\.mp-host \.msg\b/.test(css) && !/\.msg-javis\[data-mid\] \{ -webkit-touch-callout: none; \}/.test(css)
  && !Object.keys(vi).some((k) => k.startsWith("mpress.")) && !Object.keys(en).some((k) => k.startsWith("mpress.")));
check("no em or en dash", src.indexOf(String.fromCharCode(0x2014)) < 0 && src.indexOf(String.fromCharCode(0x2013)) < 0);
process.exit(fails ? 1 : 0);
