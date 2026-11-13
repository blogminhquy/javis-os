/* The Tasks and Partners pages draw what changed, once (2026-11-13).

       node tests/js/test_tasks_partners_draw_once.js

   Owner: "Tối ưu tiếp trang Nhiệm vụ và Cộng sự". Measured in a real browser on a phone-speed CPU (4x slower), 170 tasks
   and 28 assistants, the bundle and minifier on:
   - Tasks drew its whole list (340 KB of HTML) twice on every opening, again on every poll (every 30 s, every 5 s
     while a task runs) and on every letter typed in the search box, and built the wide and the phone layout each time:
     0.45 s blocked per opening, a 0.37 s freeze per poll with nothing new;
   - Partners drew the list of assistants five times per opening (the list, the default choice, then the Auto state,
     the job counts and the unread marks) and measured every card's tags after each one: 260 layouts.
   After: 0.08 s blocked for Tasks on a wide screen and none on a phone, no freeze on a poll with nothing new, one draw
   and 66 layouts for Partners. The checks in a real browser (drawing, polling, ticking, search, resizing, choosing an
   assistant, the Auto switch) are listed in the pull request; here the rules that make it so are pinned. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(root, "dashboard", f), "utf8");

let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const fn = (src, name) => (src.match(new RegExp("  function " + name + "\\([^)]*\\) \\{[\\s\\S]*?\\n  \\}")) || [""])[0];

const tasks = D("tasks.js"), css = D("tasks.css"), ws = D("workspace.js");

// ───────── Tasks: put() writes only what changed, unless the page was touched ─────────
{
  const src = fn(tasks, "put");
  check("found put()", src.length > 80);
  const S = { touched: false };
  const held = [];
  const put = new Function("S", "holdRow", "backToRow", src + "\n  return put;")(S, (el) => { held.push("hold"); return { id: "k:1" }; }, (el, at) => { held.push("back:" + at.id); });
  let writes = 0;
  const el = {}; Object.defineProperty(el, "innerHTML", { set(v) { writes++; this._h = v; }, get() { return this._h; } });
  check("the first draw writes", put(el, "<p>a</p>") === true && writes === 1 && el.innerHTML === "<p>a</p>");
  check("the same HTML again writes nothing (a poll with nothing new)", put(el, "<p>a</p>") === false && writes === 1);
  check("different HTML writes", put(el, "<p>b</p>") === true && writes === 2);
  S.touched = true;
  check("after the user touched the page, even the same HTML is written again (a tick made by hand is put right)",
    put(el, "<p>b</p>") === true && writes === 3);
  S.touched = false;
  check("and the next passive draw skips again", put(el, "<p>b</p>") === false && writes === 3);
  check("a missing node is not an error", put(null, "x") === false);
  check("a plain region is written without looking for a row to hold", held.length === 0);
  put(el, "<p>c</p>", true);
  check("a list notes the task at the top of the screen before the write and puts it back after", held.join(",") === "hold,back:k:1");
  held.length = 0; put(el, "<p>c</p>", true);
  check("and does neither when nothing is written", held.length === 0);
}
{
  // holdRow / backToRow against a small fake list: 10 rows of 60 px, the scroller's top edge at y = 50.
  const mk = (tops, ids) => {
    const rows = tops.map((t, i) => ({ t, getAttribute: () => ids[i], getBoundingClientRect() { return { top: this.t, bottom: this.t + 60 }; } }));
    const sc = { scrollTop: 500, scrollHeight: 2000, clientHeight: 700, getBoundingClientRect: () => ({ top: 50 }), parentElement: null };
    const el = { parentElement: sc, getBoundingClientRect: () => ({ top: tops[0] }), querySelectorAll: () => rows };
    return { rows, sc, el };
  };
  const lib = new Function("getComputedStyle", "window", fn(tasks, "scrollerOf") + "\n" + fn(tasks, "holdRow") + "\n" + fn(tasks, "backToRow") + "\n  return { holdRow: holdRow, backToRow: backToRow };")(() => ({ overflowY: "auto" }), { scrollBy() {} });
  const ids = ["a", "b", "c", "d", "c", "e", "f", "g", "h", "i"];
  let L = mk(ids.map((_, i) => -250 + i * 60), ids);            // rows 0..4 end above y = 50, row 5 ("e") is the first below it
  const at = lib.holdRow(L.el);
  check("holdRow finds the first task that reaches below the top edge of the scrolling area", at && at.id === "e" && at.y === 50 && at.sc === L.sc);
  const sc = L.sc;                                               // the scrolling area is the same one after the write
  L = mk(ids.map((_, i) => -250 + i * 60 - 14), ids);           // every card above came back a little shorter: 14 px in all
  lib.backToRow(L.el, at);
  check("backToRow scrolls by exactly the shift, so the task stands where it stood", sc.scrollTop === 500 - 14);
  L = mk(ids.map((_, i) => -190 + i * 60), ids);                // the first row below the edge is the SECOND "c"
  const at2 = lib.holdRow(L.el);
  check("a task that stands twice in the list is told apart by its place", at2 && at2.id === "c" && at2.nth === 1);
  L = mk(ids.map((_, i) => 80 + i * 60), ids);                  // the start of the list is on screen
  check("with the start of the list on screen there is nothing to hold", lib.holdRow(L.el) === null);
  L = mk([0], ["zzz"]); const before = L.sc.scrollTop; lib.backToRow(L.el, at);
  check("a task that is gone after the write moves nothing", L.sc.scrollTop === before);
}
{
  const desk = fn(tasks, "renderDesk"), phone = fn(tasks, "renderPhone"), render = fn(tasks, "render");
  check("the wide layout is drawn through put() only", (desk.match(/put\(/g) || []).length === 4 && !/\.innerHTML\s*=/.test(desk));
  check("the phone layout is drawn through put() only", (phone.match(/put\(/g) || []).length === 2 && !/\.innerHTML\s*=/.test(phone));
  check("both lists hold the task at the top of the screen across a redraw",
    /put\(D\.querySelector\("\.nv-view"\), viewHtml\(S\.view\), true\);/.test(desk) && /put\(el\.querySelector\("\.nv-pbody"\), phoneHtml\(\), true\);/.test(phone));
  check("one draw builds only the layout that is on screen and empties the other",
    /var phone = isPhone\(\);\n\s*if \(phone\) \{ clearDesk\(\); renderPhone\(\); \} else \{ renderDesk\(\); clearPhone\(\); \}/.test(render));
  check("a draw ends the 'touched' state", /S\.touched = false;/.test(render) && /S\.phoneDrawn = phone;/.test(render));
  check("the width where the layouts switch is the one in the stylesheet",
    /function isPhone\(\) \{ return window\.innerWidth <= 760; \}/.test(tasks)
    && /@media \(max-width: 760px\) \{\n\s*\.nv-desk \{ display: none; \}\n\s*\.nv-phone \{ display: block; \}/.test(css));
  const resize = fn(tasks, "onResize");
  check("crossing that width draws the layout that just came on screen",
    /if \(S && S\.ai && S\.phoneDrawn !== undefined && S\.phoneDrawn !== isPhone\(\)\) render\(\);/.test(resize)
    && /window\.addEventListener\("resize", onResize\);/.test(tasks) && /window\.removeEventListener\("resize", onResize\);/.test(tasks));
  check("every click, key, edit, drop or paste inside the page marks it touched (capture phase, before the handlers)",
    /\["click", "change", "submit", "input", "keydown", "dragstart", "drop", "paste"\]\.forEach\(function \(k\) \{ el\.addEventListener\(k, markTouched, true\); \}\);/.test(tasks)
    && /function markTouched\(\) \{ if \(S\) S\.touched = true; \}/.test(tasks));
  check("the search box redraws the list a moment after the last key, through put()",
    /S\.qT = setTimeout\(function \(\) \{ if \(S && S\.root === el\) put\(S\.root\.querySelector\("\.nv-view"\), viewHtml\(S\.view\)\); \}, SEARCH_WAIT_MS\);/.test(tasks)
    && /var SEARCH_WAIT_MS = (\d+);/.test(tasks) && Number(/var SEARCH_WAIT_MS = (\d+);/.exec(tasks)[1]) <= 150);
  check("closing the page drops the pending search redraw", /clearTimeout\(S\.poll\);\n\s*clearTimeout\(S\.qT\);/.test(tasks));
  check("the poll and the fresh answer still call render() (it is put() that decides)",
    /await load\(\); render\(\); schedulePoll\(\);/.test(tasks) && /if \(!\(S\.sheet \|\| S\.layer \|\| S\.sel\)\) render\(\);/.test(tasks));
  check("the details layer is always written (forms and sheets live there)", /L\.innerHTML = \(S\.layer === "form"/.test(fn(tasks, "renderLayer")));
}
check("CSS: a task card outside the screen is skipped until it comes near (size remembered once seen)",
  /\.nv-item \{ content-visibility: auto; contain-intrinsic-size: auto \d+px; \}/.test(css));
check("CSS: the row's keyboard focus ring is drawn inside the card (paint is clipped to the card)",
  /\.nv-item \.nv-row:focus-visible \{ outline-offset: -2px; \}/.test(css));

// ───────── Partners: the same list is not drawn again ─────────
{
  const list = fn(ws, "veDanhSach");
  check("found veDanhSach()", list.length > 500);
  const iSame = list.indexOf("if (host.__wsHtml === html) return;"), iWrite = list.indexOf("host.innerHTML = html;");
  check("the list returns before writing when the HTML is what the rows already show", iSame > 0 && iWrite > iSame);
  check("it remembers what it wrote", /host\.innerHTML = html;\n\s*host\.__wsHtml = html;/.test(list));
  check("the 'Show more' button is part of the compared HTML", list.indexOf('id="wsMore"') > 0 && list.indexOf('id="wsMore"') < iSame);
  check("nothing is bound or measured again for a list that was kept",
    list.indexOf("noiDanhSach(host);") > iWrite && list.indexOf("watchCardTags(host);") > iWrite);
  check("the mini card is only hidden when the rows are really replaced",
    (list.match(/anTheMini\(\);/g) || []).length === 3 && list.indexOf("anTheMini();   // the rows are about to be replaced") > iSame);
  check("the loading and the empty line forget the remembered list (so a real list after them is drawn)",
    (list.match(/host\.__wsHtml = null;/g) || []).length === 2);
}
{
  const src = fn(ws, "listSoon");
  check("found listSoon()", src.length > 60);
  const timers = []; let draws = 0;
  const env = { active: true, S: { el: {} }, veDanhSach: () => { draws++; }, setTimeout: (f) => { timers.push(f); return timers.length; } };
  const listSoon = new Function("env", "var active = env.active, S = env.S, veDanhSach = env.veDanhSach, setTimeout = env.setTimeout, listTimer = 0;\n"
    + src + "\n  return listSoon;")(env);
  listSoon(); listSoon(); listSoon();
  check("three answers in one turn ask for one draw", timers.length === 1 && draws === 0);
  timers.shift()();
  check("which then happens once", draws === 1);
  listSoon();
  check("a later answer asks again", timers.length === 1);
  const load = (ws.match(/async function taiDanhSach\(\) \{[\s\S]*?\n  \}/) || [""])[0];
  check("the Auto state, the job counts and the unread marks share that one draw",
    (load.match(/listSoon\(\);/g) || []).length === 3 && !/\.then\(function \(ok\) \{ if \(ok && active && S\.loai === "agent"\) veDanhSach\(\); \}\)/.test(load));
}
check("the default choice is settled before the list is drawn (it used to be drawn, then drawn again with the row lit)",
  (ws.match(/chonSan\(\); veTrai\(\); chonMacDinh\(\);/g) || []).length === 8 && !/[^ ]veTrai\(\); chonMacDinh\(\);/.test(ws.replace(/chonSan\(\); veTrai\(\); chonMacDinh\(\);/g, "")));
{
  const src = fn(ws, "chonSan");
  const mk = (list, chosen) => { const S = { loai: "agent", chon: { agent: chosen } }; new Function("S", "danhSach", src + "\n  chonSan();")(S, () => list); return S.chon.agent; };
  check("chonSan: nothing chosen picks the first", mk([{ slug: "a" }, { slug: "b" }], null) === "a");
  check("chonSan: a choice that still exists stays", mk([{ slug: "a" }, { slug: "b" }], "b") === "b");
  check("chonSan: a choice that is gone falls back to the first", mk([{ slug: "a" }, { slug: "b" }], "zzz") === "a");
  check("chonSan: an empty list chooses nothing", mk([], null) === null);
}
check("the tag fitting is not run a second time by the observer's first report (same column width)",
  /S\.tagFitW = host\.clientWidth;/.test(fn(ws, "fitCardTags"))
  && /if \(typeof w === "number" && w > 0 && w === S\.tagFitW\) return;\n\s*fitCardTags\(host\);/.test(fn(ws, "watchCardTags")));

if (fails.length) { console.log("\nFAIL - test_tasks_partners_draw_once: " + fails.length); process.exit(1); }
console.log("\nOK - test_tasks_partners_draw_once: all pass");
