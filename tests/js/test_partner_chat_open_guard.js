/* The Partners page chat box never stays locked in silence, and a new version starts with fresh batch lists.

       node tests/js/test_partner_chat_open_guard.js

   Customer report 2026-11-08 (after updating to 0.507.2): on the Partners page "only clicking into the chat does not
   work", while the voice button and the effort picker did, and Ctrl+Shift+R changed nothing. The chat box is locked
   (disabled) until the partner's chat is open, and opening it waited on batched reads (fetch-gop.js) with no limit, so a
   read that never answered left the box locked for good with nothing on screen. The batch itself is pinned in
   tests/js/test_read_batch.js and tests/python/test_read_batch.py. Pinned here:
   - workspace.js: an open that hangs shows the error and its Retry after OPEN_WAIT_MS, and the box still unlocks (and
     the error goes) if the open finishes after all;
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
  piece = piece.replace(/var OPEN_WAIT_MS = \d+;/, "var OPEN_WAIT_MS = 60;");

  function run(openSession) {
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

  for (const f of ["dashboard/i18n/vi.json", "dashboard/i18n/en.json"]) {
    check(f + " has ws.err_session_slow", !!JSON.parse(read(f))["ws.err_session_slow"]);
  }
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
  for (const f of ["dashboard/freshness.js", "dashboard/workspace.js", "tests/js/test_partner_chat_open_guard.js"]) {
    const s = read(f);
    check(f + " has no long dash", s.indexOf(String.fromCharCode(0x2014)) < 0 && s.indexOf(String.fromCharCode(0x2013)) < 0);
  }
}

openGuard().then(versionCaches).then(() => {
  if (fails.length) { console.log("\nFAIL - test_partner_chat_open_guard: " + fails.length); process.exit(1); }
  console.log("\nOK - test_partner_chat_open_guard: all pass");
}, (e) => { console.log("FAIL crashed: " + (e && e.stack || e)); process.exit(1); });
