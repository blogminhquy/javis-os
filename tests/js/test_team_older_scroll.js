// Team chat: only the newest page on open, older pages load by themselves near the top (owner, 18/11/2026: "phần tải
// tin nhắn trong nhóm ... tải rất lâu ... chỉ tải những tin gần nhất thôi lúc nào cuộn lên mới tải cả các tin bên trên").
//
//     python tests/run.py --js team_older_scroll -v
//
// The loaders of teams.js (loadOlder, fillOlder, onMsgsScroll) are cut out of the source and run under node against a
// fake state and a fake loadMsgs, so the real code is what is checked: one page at a time, the in-flight load is shared,
// the spinner class comes and goes, a short page loads more until the chat can scroll. Wiring is read from the source.
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "..", "..");
const src = fs.readFileSync(path.join(ROOT, "dashboard", "teams.js"), "utf8");
const css = fs.readFileSync(path.join(ROOT, "dashboard", "console.css"), "utf8");
const vi = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "vi.json"), "utf8"));
const en = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard", "i18n", "en.json"), "utf8"));

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (cond || extra === undefined ? "" : "  " + String(extra).slice(0, 500)));
  if (!cond) fails++;
}

// The source of one top-level function of teams.js (two-space indent), up to its closing brace.
function fnSrc(name) {
  const start = src.indexOf("\n  function " + name + "(");
  if (start < 0) return "";
  const end = src.indexOf("\n  }\n", start);
  return src.slice(start, end + 4);
}
const near = /var OLDER_NEAR_PX = (\d+);/.exec(src);
const code = (near ? near[0] : "") + fnSrc("loadOlder") + fnSrc("fillOlder") + fnSrc("onMsgsScroll") +
  "\nthis.api = { loadOlder: loadOlder, fillOlder: fillOlder, onMsgsScroll: onMsgsScroll };";

function classes() {
  const set = new Set();
  return { add: (c) => set.add(c), remove: (c) => set.delete(c), contains: (c) => set.has(c) };
}

// A fake page: S, the message box, and loadMsgs(true) answering one page of `page` older messages per call.
function makeWorld(opts) {
  opts = opts || {};
  const box = { classList: classes(), scrollTop: 0, clientHeight: opts.clientHeight == null ? 600 : opts.clientHeight,
    scrollHeight: opts.scrollHeight == null ? 3000 : opts.scrollHeight };
  const S = { activeId: "tm_a", team: { team_id: "tm_a" }, hasMore: true, filterTask: "", olderBusy: null,
    msgs: [{ id: 100 }, { id: 101 }], el: { querySelector: (sel) => (sel === ".tm-msgs" ? box : null) } };
  const loads = [];
  const ctx = {
    S: S, Promise: Promise,
    loadMsgs: function (older) {
      let release;
      const p = new Promise((res) => { release = res; });
      loads.push({ older: older, busyDuring: box.classList.contains("tm-older-busy"), release: () => {
        const first = S.msgs[0].id;
        const got = [];
        for (let i = (opts.page || 30); i >= 1; i--) got.push({ id: first - i });
        S.msgs = got.concat(S.msgs);
        if (opts.grow) box.scrollHeight += opts.grow;
        if (opts.lastPage && loads.length >= opts.lastPage) S.hasMore = false;
        release();
      }, fail: () => release() });
      return p;
    },
  };
  vm.createContext(ctx);
  vm.runInContext(code, ctx);
  return { S: S, box: box, loads: loads, api: ctx.api };
}
const tick = () => new Promise((r) => setImmediate(r));

(async function main() {
  check("the loaders are in teams.js", near && fnSrc("loadOlder") && fnSrc("fillOlder") && fnSrc("onMsgsScroll"));
  check("auto-load starts within 240 px of the top, like the main chat", near && near[1] === "240", near && near[1]);

  // ───── one page at a time ─────
  let w = makeWorld();
  const p1 = w.api.loadOlder();
  const p2 = w.api.loadOlder();
  check("two asks while a page is on its way start ONE load (the same messages were put in twice before)",
    w.loads.length === 1 && w.loads[0].older === true, w.loads.length);
  check("the second ask waits for the same load (the quote jump keeps going)", p1 === p2);
  check("while it loads, the list wears the spinner class", w.box.classList.contains("tm-older-busy"));
  w.loads[0].release();
  const more = await p1;
  check("done: older messages were added, the answer is true", more === true && w.S.msgs.length === 32, w.S.msgs.length);
  check("done: the spinner class is gone and another page may load", !w.box.classList.contains("tm-older-busy") && w.S.olderBusy === null);
  w.api.loadOlder();
  check("the next ask starts the next page", w.loads.length === 2);

  // ───── nothing to load ─────
  w = makeWorld();
  w.S.hasMore = false;
  check("no more pages: nothing is asked", (await w.api.loadOlder()) === false && w.loads.length === 0);
  w = makeWorld();
  w.S.filterTask = "t_1";
  check("a chat filtered on one job has no older pages", (await w.api.loadOlder()) === false && w.loads.length === 0);
  w = makeWorld();
  w.S.msgs = [];
  check("an empty chat (still loading) asks nothing", (await w.api.loadOlder()) === false && w.loads.length === 0);

  // ───── a failed page ─────
  w = makeWorld();
  const pf = w.api.loadOlder();
  w.loads[0].fail();
  check("a page that failed answers false and frees the loader", (await pf) === false && w.S.olderBusy === null
    && !w.box.classList.contains("tm-older-busy"));
  w = makeWorld();
  const ctx2 = w;
  // A network error: loadMsgs rejects.
  const vmCtx = vm.createContext({ S: ctx2.S, Promise: Promise, loadMsgs: () => Promise.reject(new Error("offline")) });
  vm.runInContext(code, vmCtx);
  check("a network error answers false and frees the loader", (await vmCtx.api.loadOlder()) === false && ctx2.S.olderBusy === null);

  // ───── switching team while a page is on its way ─────
  w = makeWorld();
  const ps = w.api.loadOlder();
  w.S.olderBusy = null;            // openTeam drops the last team's load
  w.S.activeId = "tm_b";
  w.loads[0].release();
  check("a page of the team left behind does not count as more for the new one", (await ps) === false);

  // ───── scrolling ─────
  w = makeWorld();
  w.box.scrollTop = 1500;
  w.api.onMsgsScroll({ currentTarget: w.box });
  check("reading far from the top: nothing loads", w.loads.length === 0);
  w.box.scrollTop = 120;
  w.api.onMsgsScroll({ currentTarget: w.box });
  w.api.onMsgsScroll({ currentTarget: w.box });
  check("near the top: the next older page loads, once for a burst of scroll events", w.loads.length === 1);
  w = makeWorld();
  w.S.team = null;
  w.box.scrollTop = 0;
  w.api.onMsgsScroll({ currentTarget: w.box });
  check("the team's record not here yet (chat shows Loading): a scroll to the top loads nothing", w.loads.length === 0);

  // ───── a short page fills the chat ─────
  w = makeWorld({ scrollHeight: 300, clientHeight: 600, page: 5, grow: 200 });
  w.api.fillOlder();
  check("a newest page too short to scroll loads the page before it", w.loads.length === 1);
  w.loads[0].release(); await tick(); await tick();
  check("still too short: one more page", w.loads.length === 2);
  w.loads[1].release(); await tick(); await tick();
  check("tall enough to scroll now: it stops", w.loads.length === 2 && w.box.scrollHeight === 700, w.box.scrollHeight);
  w = makeWorld({ scrollHeight: 300, clientHeight: 0 });
  w.api.fillOlder();
  check("a hidden chat (height 0) loads nothing", w.loads.length === 0);
  w = makeWorld({ scrollHeight: 300, clientHeight: 600, page: 1, grow: 10, lastPage: 2 });
  w.api.fillOlder();
  w.loads[0].release(); await tick(); await tick();
  w.loads[1].release(); await tick(); await tick();
  check("the first message of the team reached: it stops", w.loads.length === 2 && w.S.hasMore === false);

  // ───── wiring ─────
  check("page: the list listens to its own scroll (passive) to load older pages",
    src.includes('msgsBox.addEventListener("scroll", onMsgsScroll, { passive: true });'));
  check("page: the Older button and the quote jump go through the same loader",
    src.includes('if (t.classList.contains("tm-older")) return loadOlder();')
    && src.includes("loadOlder: function () { return loadOlder(); },") && !src.includes("return loadMsgs(true)"));
  check("page: opening a team forgets the last team's 'more above' and its load in flight, then fills a short chat",
    /S\.hasMore = false; S\.olderBusy = null;/.test(src)
    && /keepTeam\(\); loadFolder\(\); loadSkills\(\);\s*if \(S\.side && S\.tab === "info"\) loadInfo\(\);\s*fillOlder\(\);/.test(src));
  check("page: the button holds both labels, so a reused node never keeps 'Loading'",
    src.includes('<span class="tm-older-idle">\' + esc(tw("teams.older"))') && src.includes('<span class="tm-older-wait">\' + esc(tw("teams.older_loading"))'));
  check("CSS: the list's busy class swaps the label for a spinner line and blocks a second press",
    /\.tm-older-wait \{ display: none; \}/.test(css) && /\.tm-msgs\.tm-older-busy \.tm-older \{ pointer-events: none;/.test(css)
    && /\.tm-msgs\.tm-older-busy \.tm-older-idle \{ display: none; \}/.test(css)
    && /\.tm-msgs\.tm-older-busy \.tm-older-wait \{ display: inline; \}/.test(css) && /\.tm-older-wait::before \{[^}]*animation: tm-spin/.test(css));
  check("i18n: the loading label in vi and en, no long dash", vi["teams.older_loading"] && en["teams.older_loading"]
    && !/[\u2013\u2014]/.test(vi["teams.older_loading"] + en["teams.older_loading"]));

  console.log();
  if (fails) { console.log(fails + " FAILED"); process.exit(1); }
  console.log("ALL OK");
})();
