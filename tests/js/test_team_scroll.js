// The Team chat scrolls like the main chat (one module, dashboard/chat-scroll.js): it follows the latest message only
// at the end, shows the jump button and its "New messages" pill, holds while the mouse is on a message's buttons, keeps
// the reader on the same message when older messages load, and keeps the end in view while pictures load.
//
//     node tests/js/test_team_scroll.js
"use strict";
const fs = require("fs");
const path = require("path");
const D = path.join(__dirname, "..", "..", "dashboard");
const CS = require(path.join(D, "chat-scroll.js"));
const teamsJs = fs.readFileSync(path.join(D, "teams.js"), "utf8");
const css = fs.readFileSync(path.join(D, "style.css"), "utf8");
const indexHtml = fs.readFileSync(path.join(D, "index.html"), "utf8");
let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || !extra ? "" : "  " + extra));
  if (!cond) fails++;
}

// A fake message list: messages are boxes stacked from y = 0 inside the area (area top at screen y 100).
function makeArea(heights) {
  const ls = {};
  const area = {
    msgs: [], clientHeight: 400, scrollTop: 0, top: 100,
    get scrollHeight() { return this.msgs.reduce((a, m) => a + m.h, 0); },
    addEventListener(n, f) { ls[n] = f; }, removeEventListener(n) { delete ls[n]; },
    fire(n, e) { if (ls[n]) ls[n](e || {}); },
    getBoundingClientRect() { return { top: this.top }; },
    querySelector: () => null,
    querySelectorAll() { return this.msgs.map((m) => m.el); },
    ownerDocument: { createElement: () => btnEl() },
  };
  area.set = function (list) {
    area.msgs = list.map((x) => ({ h: x.h, el: null, id: x.id }));
    let y = 0;
    area.msgs.forEach((m) => {
      const my = y;
      m.el = { getAttribute: (k) => (k === "data-mid" ? String(m.id) : null),
        getBoundingClientRect: () => ({ top: area.top + my - area.scrollTop, bottom: area.top + my + m.h - area.scrollTop }) };
      y += m.h;
    });
  };
  area.set(heights);
  return area;
}
function btnEl() {
  const set = new Set();
  return { parentNode: null, attrs: {}, classList: { add: (c) => set.add(c), remove: (c) => set.delete(c), contains: (c) => set.has(c),
    toggle: (c, on) => { if (on === undefined) on = !set.has(c); if (on) set.add(c); else set.delete(c); return on; } },
    setAttribute(k, v) { this.attrs[k] = v; }, addEventListener(n, f) { this["on" + n] = f; }, removeEventListener() {} };
}
const win = { matchMedia: () => ({ matches: false }), addEventListener() {}, removeEventListener() {} };

// keep(): older messages go in above; the reader stays on the same message, even when pictures below are still loading.
const ids = (from, to, h) => { const out = []; for (let i = from; i <= to; i++) out.push({ id: i, h: h }); return out; };
let area = makeArea(ids(41, 80, 100));
let ctl = CS.attach(area, { buttonClass: "jv-new-msg", msg: ".tm-msg", key: "data-mid", win });
area.scrollTop = 250;                      // message 43 is the first in view, 50 px of it hidden
ctl.keep(() => {
  // 40 older messages of 120 px added above; the redraw also left a picture below at 0 px (not loaded yet).
  const list = ids(1, 40, 120).concat(ids(41, 80, 100));
  list[list.length - 1].h = 0;
  area.set(list);
});
const m43 = area.msgs.find((m) => m.id === 43).el.getBoundingClientRect().top - area.top;
check("older messages above: the same message stays at the same height (anchor by data-mid)", m43 === -50, String(m43));
area = makeArea(ids(41, 80, 100));
ctl = CS.attach(area, { msg: ".tm-msg", win });
area.scrollTop = 250;
ctl.keep(() => area.set(ids(1, 40, 120).concat(ids(41, 80, 100))));
check("without a key: measured from the bottom", area.scrollTop === 250 + 40 * 120);

// followLoads: a picture loading while at the end keeps the end in view; reading higher up, nothing moves.
area = makeArea(ids(1, 20, 100));
ctl = CS.attach(area, { msg: ".tm-msg", key: "data-mid", followLoads: true, win });
area.scrollTop = area.scrollHeight - area.clientHeight;
area.fire("scroll");
area.msgs[19].h = 300;
area.fire("load", { target: { tagName: "IMG" } });
check("a picture loading at the end: still at the end", area.scrollTop === area.scrollHeight);
area.scrollTop = 200; area.fire("scroll");
area.msgs[19].h = 500;
area.fire("load", { target: { tagName: "IMG" } });
check("a picture loading while reading higher up: the view does not move", area.scrollTop === 200);
ctl.detach();
check("detach removes the listeners", area.fire("scroll") === undefined && ctl.stuck() === false);

// Team wiring.
check("Team attaches the shared scroll to its message list with its selectors, the anchor key and picture follow",
  /S\.scroll = CS && msgsBox \? CS\.attach\(msgsBox, \{ buttonClass: "jv-new-msg tm-new-msg", msg: "\.tm-msg",\s*hold: "\.tm-hacts:hover, \.tm-rx:hover", key: "data-mid", followLoads: true \}\) : null;/.test(teamsJs));
check("Team puts the jump button last in the list on every redraw", /if \(S\.scroll\) \{ if \(box\.lastChild !== S\.scroll\.button\) box\.appendChild\(S\.scroll\.button\); S\.scroll\.update\(\); \}/.test(teamsJs));
check("Team: open or own message jumps; other redraws follow only at the end",
  /if \(stick\) toLatest\(true\);\s*else if \(!S\.scroll \|\| S\.scroll\.stuck\(\)\) toLatest\(false\);/.test(teamsJs)
  && !/var atEnd = box\.scrollHeight - box\.scrollTop - box\.clientHeight < 80;/.test(teamsJs));
check("Team: a new message while reading higher up turns the button into New messages",
  /if \(i < 0 && S\.scroll && !S\.scroll\.stuck\(\)\) toLatest\(false\);/.test(teamsJs));
check("Team: loading older messages keeps the reading position",
  /if \(older && S\.scroll\) S\.scroll\.keep\(function \(\) \{ drawMsgs\(false\); \}\);/.test(teamsJs));
check("Team: a second render detaches the old scroll listeners", /if \(S && S\.scroll\) S\.scroll\.detach\(\);/.test(teamsJs));
check("CSS: the Team button looks like the main chat's", /#newMsgBtn, \.jv-new-msg \{ position: sticky;/.test(css)
  && /#newMsgBtn\.has-new, \.jv-new-msg\.has-new \{/.test(css));
check("chat-scroll.js loads before app.js and teams.js",
  indexHtml.indexOf("/static/chat-scroll.js?v=") > 0 && indexHtml.indexOf("/static/chat-scroll.js?v=") < indexHtml.indexOf("/static/app.js?v="));

// 0.358.0 (owner: "gửi xong không thấy hiện câu của mình"): the list getting shorter (phone keyboard, a taller composer)
// fires no scroll event; while following the end, the end stays in view. Reading higher up, nothing moves.
{
  let roCb = null, observed = null, disconnected = false;
  const rwin = Object.assign({}, win, { ResizeObserver: function (cb) { roCb = cb; this.observe = (el) => { observed = el; };
    this.disconnect = () => { disconnected = true; }; } });
  const ra = makeArea(ids(1, 20, 100));
  const rc = CS.attach(ra, { msg: ".tm-msg", win: rwin });
  ra.scrollTop = ra.scrollHeight - ra.clientHeight;
  ra.fire("scroll");
  ra.clientHeight = 339;                       // the composer grew by 61px
  roCb();
  check("resize while at the end: the newest message stays above the composer", observed === ra && rc.stuck()
    && ra.scrollTop === ra.scrollHeight, ra.scrollTop);
  ra.scrollTop = 200; ra.fire("scroll");
  ra.clientHeight = 300; roCb();
  check("resize while reading higher up: the view does not move", ra.scrollTop === 200 && !rc.stuck());
  rc.detach();
  check("detach stops watching the size", disconnected);
}

if (fails) { console.log("\nFAIL - test_team_scroll: " + fails); process.exit(1); }
console.log("\nOK - test_team_scroll");
