// 0.196.0 (owner, 17/10/2026): "kéo đến 1 cỡ nhất định thì nó ẩn vào thụt luôn vào trong" on every page with columns
// (graph, chat, partners, team), the team list folds to team pictures with a hover card like the partners list.
//
//     node tests/js/test_col_fold_0196.js
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CR = require(path.join(ROOT, "dashboard", "col-resize.js"));
const css = read("console.css"), consoleJs = read("console.js"), ws = read("workspace.js"), teams = read("teams.js"), crSrc = read("col-resize.js");
const vi = JSON.parse(read("i18n/vi.json")), en = JSON.parse(read("i18n/en.json"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// ---- a fake column with a handle ----
function rig(extra) {
  const store = {};
  global.localStorage = { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; } };
  const L = {};
  const handle = { className: "", attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, addEventListener(n, f) { L[n] = f; },
    setPointerCapture() {}, parentNode: null };
  global.document = { createElement: () => handle, body: { classList: { add() {}, remove() {} } } };
  const cls = new Set();
  const col = { w: 300, querySelector: () => null, appendChild(h) { h.parentNode = this; },
    getBoundingClientRect() { return { width: this.w }; },
    classList: { toggle(c, on) { if (on) cls.add(c); else cls.delete(c); }, remove(c) { cls.delete(c); } } };
  const props = {};
  const host = { style: { setProperty: (k, v) => { props[k] = v; col.w = parseInt(v, 10); }, removeProperty: (k) => { delete props[k]; } } };
  const o = Object.assign({ host, varName: "--x-w", key: "x_w", min: 220, max: 560, edge: "right" }, extra);
  CR.attach(col, o);
  const drag = (from, to) => { L.pointerdown({ button: 0, clientX: from, preventDefault() {}, pointerId: 1 }); L.pointermove({ clientX: to }); };
  return { store, props, col, cls, L, o, drag };
}

check("fold point is 60px under the minimum, the gap of the partners list (220 -> 160)", CR.FOLD_AT(220) === 160);

// collapse
let folded = 0;
let r = rig({ collapse: { below: 160, run: () => folded++ } });
r.drag(500, 300);   // 300 - 200 = 100 < 160
check("dragging past the fold point dims the column (col-resize-folding)", r.cls.has("col-resize-folding"));
r.L.pointerup({});
check("letting go there folds the column with the page's own collapse", folded === 1);
check("... and keeps the width it had before the drag for when it reopens", r.props["--x-w"] === "300px" && r.store.x_w === "300",
  JSON.stringify([r.props, r.store]));
check("the dim goes away once let go", !r.cls.has("col-resize-folding"));
r = rig({ collapse: { below: 160, run: () => folded++ } });
r.drag(500, 440); r.L.pointerup({});
check("a drag that stays wide enough only resizes", folded === 1 && r.props["--x-w"] === "240px", JSON.stringify(r.props));

// snap
const snaps = [];
r = rig({ snap: { below: 160, to: 72, onSnap: (on) => snaps.push(on) } });
r.drag(500, 300);
check("snap: narrower than the point becomes the 72px strip and tells the page", r.props["--x-w"] === "72px" && snaps[snaps.length - 1] === true);
r.L.pointerup({});
check("snap: the strip width is remembered", r.store.x_w === "72");
r.drag(100, 400);
check("snap: dragging back out gives the list again", r.props["--x-w"] === "372px" && snaps[snaps.length - 1] === false, JSON.stringify(r.props));
check("fit(): snap below the point, clamp above it", CR.fit(r.o, 100) === 72 && CR.fit(r.o, 180) === 220 && CR.fit(r.o, 900) === 560);

// card
const card = CR.miniTip.html({ ava: "<i></i>", name: "A <b>", time: "10:00", sub: "Last line", stText: "Cần bạn", st: "need" });
check("card: name, time, last line, state with its colour key; text escaped",
  card.includes("<strong>A &lt;b&gt;</strong>") && card.includes('ws-mini-tip-time">10:00') && card.includes("Last line") &&
  card.includes('data-st="need">Cần bạn'));
check("one card for the app (moved out of workspace.js)", crSrc.includes('el.id = "wsMiniTip"') && !ws.includes('the.id = "wsMiniTip"') &&
  ws.includes("window.JavisColResize.miniTip.show(b,"));

// pages
check("graph: both columns fold with their own buttons", crSrc.includes('collapse: { below: FOLD_AT(200), run: press("#vtCollapse") }') &&
  crSrc.includes('collapse: { below: FOLD_AT(280), run: press("#chatColThu") }'));
check("chat: the conversations column folds like its collapse button",
  consoleJs.includes("collapse: { below: window.JavisColResize.FOLD_AT(220), run: () => datSideThu(true) }"));
check("partners: the right panel folds away when let go narrow, keeping its width",
  /if \(ben === "right" && tho && tho < NGUONG_AN_PHAI\) \{[\s\S]{0,400}luuBeRong\(ben, chanBeRong\(ben, w0, page\), page\);[\s\S]{0,80}datPhai\(false\);/.test(ws));
check("team: list handle snaps to the 72px strip of team pictures (tm-mini), side panel folds with closeSide",
  teams.includes("snap: { below: CR.FOLD_AT(220), to: LIST_MINI_W") && teams.includes('page.classList.toggle("tm-mini", !!on)') &&
  teams.includes("collapse: { below: CR.FOLD_AT(300), run: function () { closeSide(); } }") && teams.includes("var LIST_MINI_W = 72;"));
check("team: the side handle is put back after every side redraw", /attachSideResize\(side\);/.test(teams));
check("team: hovering a team picture in the strip shows the shared card", teams.includes("CR.miniTip.show(row, {"));
check("team CSS: widths from the handles, strip hides names and menus, handles only on wide screens",
  css.includes("grid-template-columns: var(--tm-list-w, 280px) minmax(0, 1fr) var(--tm-side-w, 360px)") &&
  /\.tm-page\.tm-mini \.tm-team-main/.test(css) && /\.tm-list > \.col-resize, \.tm-side > \.col-resize \{ display: block;/.test(css) &&
  css.includes(".col-resize-folding { opacity: .45;"));
["teams.resize_list", "teams.resize_side"].forEach((k) => check("i18n " + k, !!vi[k] && !!en[k]));
["col-resize.js", "teams.js", "workspace.js"].forEach((f) => check(f + " has no long dash", !/[–—]/.test(read(f))));

process.exit(fails ? 1 : 0);
