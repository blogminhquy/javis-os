/* The Partners page chat box never stays locked in silence, and a new version starts with fresh batch lists.

       node tests/js/test_partner_chat_open_guard.js

   Customer report 2026-11-08 (after updating to 0.507.2): on the Partners page "only clicking into the chat does not
   work", while the voice button and the effort picker did, and Ctrl+Shift+R changed nothing. The chat box is locked
   (disabled) until the partner's chat is open, and opening it waited on batched reads (fetch-gop.js) with no limit, so a
   read that never answered left the box locked for good with nothing on screen. The batch itself is pinned in
   tests/js/test_read_batch.js and tests/python/test_read_batch.py. Pinned here:
   - workspace.js: an open that hangs shows the error and its Retry after OPEN_WAIT_MS, and the box still unlocks (and
     the error goes) if the open finishes after all;
   - #1213 (the error showed on opens that were only slow): it waits while fetch-gop.js is retrying reads (its reconnect
     band is on screen), the Javis Core POST is cut after CORE_SESSION_WAIT_MS instead of hanging for good, and app.js
     does not hand a load stuck in flight to the Retry that follows;
   - freshness.js: the first page opened on a new version drops the batch lists ("javis.batch.*") the previous
     version recorded, which Ctrl+Shift+R does not clear, and nothing else. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond, extra) {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  if (!cond) fails.push(name);
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");

// ---- workspace.js: moPhien with a chat that never opens -------------------------------------------------------------
async function openGuard() {
  const src = read("dashboard/workspace.js");
  const m = /var OPEN_WAIT_MS = (\d+);/.exec(src);
  check("OPEN_WAIT_MS is a real wait, under 20 seconds", m && +m[1] >= 5000 && +m[1] <= 20000, m && m[1]);
  let piece = src.slice(src.indexOf("  async function moPhien("), src.indexOf("  async function chayQuyTrinh()"));
  piece = piece.replace(/var OPEN_WAIT_MS = \d+;/, "var OPEN_WAIT_MS = 60;")
    .replace(/var OPEN_RECHECK_MS = \d+;/, "var OPEN_RECHECK_MS = 20;")
    .replace(/var CORE_SESSION_WAIT_MS = \d+;/, "var CORE_SESSION_WAIT_MS = 40;");
  const wm = /var OPEN_WAIT_MS = (\d+);/.exec(src);
  check("#1213: OPEN_WAIT_MS covers the 4 s a batched read may wait plus a slow open", wm && +wm[1] >= 16000, wm && wm[1]);

  function run(openSession, extra) {
    const errEls = [];
    const ident = {
      innerHTML: "",
      querySelectorAll: () => errEls.splice(0).map((n) => ({ remove() { ident.innerHTML = ident.innerHTML.replace(n, ""); } })),
    };
    const ctx = {
      opening: 0, ready: false, active: true, setTimeout, clearTimeout, Promise,
      S: { loai: "agent", sessionCuaPhien: {}, el: { querySelector: (s) => (s === "#wsIdentity" ? ident : null) } },
      _phienGanNhat: {}, khoaGanNhat: () => "k", kenh: (x) => "agent:" + x.slug, brain: () => "b",
      conDangXem: () => true, phaiDaVeCho: () => true, vePhai() {}, veGiua() {}, luuViTri() {},
      coTinChuaDoc: () => false, daDoc() {}, ganCongHuong() {}, t: (k) => k, fd: (o) => o,
      api: async (u) => (u.indexOf("/sessions?") === 0 ? { sessions: [{ id: "s1" }] } : {}),
      veLoi(msg) { const tag = "<err:" + msg + ">"; ident.innerHTML += tag; errEls.push(tag); },
      window: { JavisSessions: { _cur: null, open: openSession, current() { return this._cur; }, new() {} } },
    };
    Object.assign(ctx, (extra && extra.ctx) || {});
    Object.assign(ctx.window, (extra && extra.window) || {});
    ctx.chatReady = (v) => { ctx.ready = v; };
    vm.createContext(ctx);
    vm.runInContext(piece, ctx);
    return { ctx, ident };
  }

  // A chat that never opens: the box stays locked, but the error and Retry show.
  let t = run(() => new Promise(() => {}));
  t.ctx.moPhien({ slug: "viet-email" }, false);
  await wait(150);
  check("an open that hangs shows the slow-open error instead of a silent locked box",
    t.ctx.ready === false && t.ident.innerHTML.includes("ws.err_session_slow"), t.ident.innerHTML);

  // A chat that opens late: the box unlocks and the error leaves.
  let finish;
  t = run(function (id) { const self = this; return new Promise((ok) => { finish = () => { self._cur = id; ok(); }; }); });
  const done = t.ctx.moPhien({ slug: "viet-email" }, false);
  await wait(150);
  const shown = t.ident.innerHTML.includes("ws.err_session_slow");
  finish(); await done;
  check("an open that finishes late unlocks the box and clears the error",
    shown && t.ctx.ready === true && !t.ident.innerHTML.includes("ws.err_session_slow"), t.ident.innerHTML);

  // A quick open: no error ever shows (the timer is cleared).
  t = run(function (id) { this._cur = id; return Promise.resolve(); });
  await t.ctx.moPhien({ slug: "viet-email" }, false);
  await wait(150);
  check("a quick open shows no error", t.ctx.ready === true && t.ident.innerHTML === "", t.ident.innerHTML);

  // #1213: no error while reads are being retried; it shows once the retries are over.
  let retrying = true;
  t = run(() => new Promise(() => {}), { window: { JavisFetchGop: { retrying: () => retrying } } });
  t.ctx.moPhien({ slug: "viet-email" }, false);
  await wait(150);
  check("#1213: while fetch-gop.js retries, the slow-open error waits", !t.ident.innerHTML.includes("ws.err_session_slow"),
    t.ident.innerHTML);
  retrying = false;
  await wait(100);
  check("#1213: once the retries end, the error and its Retry show", t.ident.innerHTML.includes("ws.err_session_slow"),
    t.ident.innerHTML);

  // #1213: the Javis Core POST that never answers is cut, and the open ends with the error instead of hanging.
  let sawSignal = false;
  t = run(() => new Promise(() => {}), { ctx: {
    AbortController,
    api: (u, opt) => {
      if (u !== "/javis-core/session") return Promise.resolve({});
      sawSignal = !!(opt && opt.signal);
      return new Promise((ok, no) => { if (opt && opt.signal) opt.signal.addEventListener("abort", () => no(new Error("aborted"))); });
    },
  } });
  const ended = t.ctx.moPhien({ slug: "javis-core", system: true }, false);
  const res = await Promise.race([ended, wait(400).then(() => "hung")]);
  check("#1213: the Javis Core POST carries a time limit", sawSignal);
  check("#1213: a Javis Core POST that hangs ends the open with the error", res === false
    && t.ident.innerHTML.includes("ws.err_session") && t.ctx.ready === false, { res, html: t.ident.innerHTML });

  for (const f of ["dashboard/i18n/vi.json", "dashboard/i18n/en.json"]) {
    check(f + " has ws.err_session_slow", !!JSON.parse(read(f))["ws.err_session_slow"]);
  }
}

// ---- app.js: Retry does not join a load stuck in flight (#1213) --------------------------------------------------------
function staleLoad() {
  const app = read("dashboard/app.js");
  const start = app.indexOf("function _taiPhien(");
  const fn = app.slice(app.lastIndexOf("\n", start) + 1, app.indexOf("\n}", start) + 2);
  let now = 1000000, fetches = 0;
  const ctx = {
    _phienDangTai: new Map(), _urlPhien: (id) => "/sessions/" + id, _ghiCachePhien() {},
    Date: { now: () => now }, fetch: () => { fetches++; return new Promise(() => {}); },
  };
  vm.createContext(ctx);
  vm.runInContext(fn, ctx);
  const a = ctx._taiPhien("s1");
  const b = ctx._taiPhien("s1");
  check("#1213: two loads of one chat at the same moment share one request", a === b && fetches === 1, fetches);
  now += 11 * 1000;
  const c = ctx._taiPhien("s1");
  check("#1213: a load stuck in flight for 10 s is not handed out again", c !== a && fetches === 2, fetches);
  check("#1213: the new load is the one kept in flight", ctx._phienDangTai.get("s1") === c);
}

// ---- freshness.js: a new version drops the old batch lists ------------------------------------------------------------
function freshPage(version, store) {
  const keys = () => Object.keys(store);
  const ls = {
    get length() { return keys().length; },
    key: (i) => keys()[i] || null,
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; },
  };
  const doc = {
    readyState: "loading", hidden: false,
    getElementById: (id) => (id === "javis-fresh" ? { textContent: JSON.stringify({ version, assets: {} }) } : null),
    addEventListener() {},
  };
  const win = {
    document: doc, localStorage: ls, sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    addEventListener() {}, setTimeout() {}, setInterval() {}, fetch: () => new Promise(() => {}),
    navigator: {}, isSecureContext: false, TextEncoder, t: (k) => k, Uint32Array, Uint8Array, Promise, JSON, Date,
    encodeURIComponent, Object, String, Number,
  };
  win.window = win;
  vm.createContext(win);
  vm.runInContext(read("dashboard/freshness.js"), win);
}

function versionCaches() {
  const store = { "javis.batch.chat": "[\"/x\"]", "javis.batch.boot": "[]", "javis_last_page": "workspace", "javis.theme": "dark" };
  freshPage("0.507.2", store);
  check("first ever page: nothing is dropped, the version is noted",
    store["javis.batch.chat"] && store["javis-fresh-version"] === "0.507.2", store);
  freshPage("0.507.2", store);
  check("same version again: the batch lists stay", !!store["javis.batch.chat"] && !!store["javis.batch.boot"]);
  freshPage("0.508.1", store);
  check("a new version drops every batch list of the old one",
    !("javis.batch.chat" in store) && !("javis.batch.boot" in store) && store["javis-fresh-version"] === "0.508.1", store);
  check("and nothing else: the owner's own choices stay",
    store["javis_last_page"] === "workspace" && store["javis.theme"] === "dark");

  const idx = read("dashboard/index.html");
  check("freshness.js runs before fetch-gop.js reads the lists",
    idx.indexOf('src="/static/freshness.js"') > 0 && idx.indexOf('src="/static/freshness.js"') < idx.indexOf('src="/static/fetch-gop.js'));
  for (const f of ["dashboard/freshness.js", "dashboard/workspace.js", "dashboard/fetch-gop.js", "dashboard/app.js",
    "tests/js/test_partner_chat_open_guard.js"]) {
    const s = read(f);
    check(f + " has no long dash", s.indexOf(String.fromCharCode(0x2014)) < 0 && s.indexOf(String.fromCharCode(0x2013)) < 0);
  }
}

openGuard().then(staleLoad).then(versionCaches).then(() => {
  if (fails.length) { console.log("\nFAIL - test_partner_chat_open_guard: " + fails.length); process.exit(1); }
  console.log("\nOK - test_partner_chat_open_guard: all pass");
}, (e) => { console.log("FAIL crashed: " + (e && e.stack || e)); process.exit(1); });
