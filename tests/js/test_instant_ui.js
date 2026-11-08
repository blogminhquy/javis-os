/* Instant UI (2026-11-08). Owner: "load các trang, load lịch sử chuyển từ hội thoại này sang hội thoại khác bị delay
   mấy giây". Measured over a 250 ms tunnel: a chat not in memory took ~330 ms to appear, pages 0.3-1.4 s, every visit.

   What is pinned here:
   - chat-cache.js keeps at most 50 chats, none older than 7 days, and degrades to "nothing kept" without IndexedDB;
   - app.js reads the kept chats at start, draws a kept chat at once even right after a reload, keeps a chat that grew
     while open (asking for its new copy instead of dropping it), refreshes a chat that answered in the background, and
     warms the first chats of the history list one at a time (none on a data-saving connection);
   - fetch-gop.js answers the reads of a console page's first drawing from the last visit's copy (also those with their
     own timeout) while it asks the server, tells console.js when the answer differs, sends later reads of the same
     visit to the server, and drops every copy on a write (except the bookkeeping posts) and at the end of a chat turn;
   - console.js draws such a page again unless the owner already clicked or typed on it; signing out clears the kept
     chats.

    node tests/js/test_instant_ui.js
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const fails = [];
const check = (name, cond, extra) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  if (!cond) fails.push(name);
};
const tick = () => new Promise((r) => setTimeout(r, 0));

// ───────── chat-cache.js ─────────
async function chatCacheStore() {
  const C = require(path.join(ROOT, "dashboard", "chat-cache.js"));
  const now = 1e12, day = 864e5;
  const recs = [];
  for (let i = 0; i < 60; i++) recs.push({ id: "c" + i, at: now - i * 1000 });
  recs.push({ id: "old", at: now - 8 * day });
  const drop = C.toDrop(recs, now, C.MAX, C.MAX_AGE);
  check("the store keeps at most 50 chats", C.MAX === 50 && drop.length === 11);
  check("the ones opened least recently go first", drop.includes("c59") && drop.includes("c50") && !drop.includes("c49"));
  check("a chat kept more than 7 days goes", drop.includes("old") && C.MAX_AGE === 7 * day);
  check("without IndexedDB nothing is kept and nothing throws",
    (await C.all()).length === 0 && (await C.put("x", { messages: [] })) === null && (await C.clear()) === null);
}

// ───────── app.js: kept chats ─────────
const APP = read("dashboard/app.js");
function fnSrc(name) {
  const start = APP.indexOf("function " + name + "(");
  if (start < 0) throw new Error("missing " + name);
  const head = APP.lastIndexOf("\n", start) + 1;
  return APP.slice(head, APP.indexOf("\n}", start) + 2);
}
function constLine(name) {
  const m = new RegExp("^const " + name + " = [^\\n]*$", "m").exec(APP);
  if (!m) throw new Error("missing const " + name);
  return m[0].replace(/^const /, "var ");
}
function appCtx(extra) {
  const answers = {};
  const st = { fetches: [], drawn: [], answers };
  const ctx = Object.assign({
    TIN_MOI_LUOT: 30, savedSessionId: null, convo: [], handsFree: false, sessionOpenSeq: 0, currentBrainPath: () => "b",
    tatRanhTay() {}, boViecPhienCu() {}, Date, Map, JSON, Promise, encodeURIComponent, setTimeout,
    navigator: {},
    fetch: (url) => {
      const id = decodeURIComponent(url.split("/")[2].split("?")[0]);
      st.fetches.push(id);
      return new Promise((r) => setTimeout(() => r({ json: () => Promise.resolve(JSON.parse(JSON.stringify(answers[id]))) }), 5));
    },
  }, extra || {});
  vm.createContext(ctx);
  ["_PHIEN_CACHE_MAX", "_PHIEN_CACHE_TTL", "_PREFETCH_TUOI", "_WARM_MAX", "_WARM_FRESH_MS", "_phienCache", "_phienDangTai"]
    .forEach((n) => vm.runInContext(constLine(n), ctx));
  vm.runInContext("var _phienMoLuc = null; var _keptChatsLoading = null; var _warming = false;", ctx);
  ["_urlPhien", "_ghiCachePhien", "_docCachePhien", "_vanTayPhien", "_taiPhien", "prefetchSession", "prefetchMany",
    "_quenPhienNeuDoi", "openStoredSession"].forEach((n) => vm.runInContext(fnSrc(n), ctx));
  ctx._veLaiPhien = (id, sess, ticket, capNhat) => {
    st.drawn.push({ id, n: sess.messages.length, capNhat });
    ctx.savedSessionId = id; ctx.convo = sess.messages.slice();
    vm.runInContext("_phienMoLuc = { id: savedSessionId, len: convo.length };", ctx);
  };
  return { ctx, st };
}
const msg = (id) => ({ id, role: "assistant", content: "x" + id, content_sha: "s" + id, ts: id });

async function keptChats() {
  check("50 chats, no 5-minute limit", /^const _PHIEN_CACHE_MAX = 50;$/m.test(APP) && /^const _PHIEN_CACHE_TTL = 7 \* 24 \* 3600 \* 1000;$/m.test(APP));
  check("every fresh copy is written to the kept store", /window\.JavisChatCache\.put\(id, sess, at\)/.test(APP));
  check("the kept chats are read once at start", /window\.JavisChatCache\.all\(\)\.then/.test(APP));

  // Right after a reload: the kept copy arrives from IndexedDB before the server, and is drawn at once.
  const { ctx, st } = appCtx();
  st.answers.A = { brain: "b", has_more: false, messages: [msg(1), msg(2)] };
  let release;
  ctx._keptChatsLoading = new Promise((r) => { release = r; });
  const opening = ctx.openStoredSession("A");
  check("the server is asked at once, before the kept copies are read", st.fetches.join() === "A");
  ctx._phienCache.set("A", { sess: { brain: "b", has_more: false, messages: [msg(1), msg(2)] }, at: Date.now() - 3600e3 });
  release();
  await tick(); await tick();
  check("a kept chat is drawn as soon as its copy is read, before the server answers", st.drawn.length === 1 && st.drawn[0].n === 2);
  await opening;
  check("the server's answer, equal to it, redraws nothing", st.drawn.length === 1);

  // An hour-old copy is still drawn first (it used to expire after 5 minutes), then corrected.
  st.answers.B = { brain: "b", has_more: false, messages: [msg(3), msg(4)] };
  ctx._phienCache.set("B", { sess: { brain: "b", has_more: false, messages: [msg(3)] }, at: Date.now() - 3600e3 });
  st.drawn.length = 0;
  await ctx.openStoredSession("B");
  check("an hour-old copy is drawn at once, then the newer answer once more",
    st.drawn.length === 2 && st.drawn[0].n === 1 && st.drawn[1].n === 2 && st.drawn[1].capNhat === true);

  // Background answer: app.js refreshes the kept copy of a chat that is not on screen.
  check("a chat that answered off screen has its copy refreshed",
    /data\.type === "turn_saved" && sid && sid !== savedSessionId && _phienCache\.has\(sid\)\) _taiPhien\(sid\)/.test(APP));
}

async function warming() {
  const { ctx, st } = appCtx({ requestIdleCallback: (fn) => setTimeout(fn, 0) });
  ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"].forEach((id) => { st.answers[id] = { brain: "b", has_more: false, messages: [msg(1)] }; });
  ctx.savedSessionId = "a";
  ctx._phienCache.set("b", { sess: st.answers.b, at: Date.now() });
  ctx.prefetchMany(["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]);
  await tick();
  check("warming starts with one chat, not all at once", st.fetches.length === 1);
  for (let i = 0; i < 40; i++) await new Promise((r) => setTimeout(r, 6));
  check("it skips the open chat and fresh copies, and stops at 8",
    st.fetches.join() === "c,d,e,f,g,h,i,j", st.fetches);
  const saver = appCtx({ navigator: { connection: { saveData: true } } });
  saver.ctx.prefetchMany(["x", "y"]);
  await tick();
  check("nothing is warmed on a data-saving connection", saver.st.fetches.length === 0);
  const ui = read("dashboard/sessions-ui.js");
  check("the history list warms its first 8 chats", /window\.JavisSessions\.prefetchMany\(items\.slice\(0, 8\)/.test(ui)
    && /prefetchMany: prefetchMany/.test(APP));
}

// ───────── fetch-gop.js: page reads from the last visit ─────────
async function pageCopies() {
  const G = require(path.join(ROOT, "dashboard", "fetch-gop.js"));
  const O = "https://j.example";
  check("console page reads may come from a copy", G.swrKey("/skills?brain=brain", undefined, O) === "/skills?brain=brain"
    && G.swrKey("/connect/catalog", undefined, O) !== "" && G.swrKey("/telegram/status", undefined, O) !== "");
  check("chat, live boards and explicit refreshes never do",
    G.swrKey("/sessions/abc?limit=30", undefined, O) === "" && G.swrKey("/kanban?brain=b", undefined, O) === ""
    && G.swrKey("/settings", { cache: "no-store" }, O) === "" && G.swrKey("/usage/insights?refresh=1", undefined, O) === "");
  check("marking a chat read keeps the copies, saving a setting does not",
    G.keepsCopies("/sessions/x/read", { method: "POST" }, O) && !G.keepsCopies("/settings", { method: "POST", body: "{}" }, O));

  // The real wrapper, on a fake window.
  const net = [];
  let body = { v: 1 };
  const events = [];
  const win = new EventTarget();
  Object.assign(win, {
    location: { origin: O },
    fetch: (url, init) => { net.push((init && init.method || "GET") + " " + url);
      return new Promise((r) => setTimeout(() => r(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } })), 5)); },
  });
  win.addEventListener("javis:page-data", (e) => events.push(e.detail));
  const ctx = vm.createContext({ window: win, location: win.location, Response, CustomEvent, URL, Promise, Date, setTimeout, document: {} });
  vm.runInContext(read("dashboard/fetch-gop.js"), ctx);
  const F = win.JavisFetchGop;
  const get = async (u) => (await win.fetch(u)).json();

  F.pageStart("skills");
  check("first visit: the read goes to the server", (await get("/skills?brain=b")).v === 1 && net.length === 1);
  check("reads while the page is first drawn share that answer", (await get("/skills?brain=b")).v === 1 && net.length === 1);
  await new Promise((r) => setTimeout(r, 1600));   // past the 1.5 s sharing window
  body = { v: 2 };
  F.pageStart("skills");
  const t0 = Date.now();
  const first = await get("/skills?brain=b");
  check("next visit: the page gets the last copy at once", first.v === 1 && Date.now() - t0 < 5);
  await new Promise((r) => setTimeout(r, 20));
  check("...while the server is asked again", net.length === 2);
  check("...and the page hears that the answer changed", events.length === 1 && events[0].page === "skills");
  check("the redraw that follows gets the new answer without another request", (await get("/skills?brain=b")).v === 2 && net.length === 2);
  await new Promise((r) => setTimeout(r, 2600));   // past the first drawing of the visit
  check("a later read on the same visit goes to the server (no step behind)", (await get("/skills?brain=b")).v === 2 && net.length === 3);
  // A read with its own timeout (the Settings, Channels and Models pages) is answered from the copy too.
  await new Promise((r) => setTimeout(r, 1600));
  F.pageStart("channels");
  const ac = new AbortController();
  const t1 = Date.now();
  const withSignal = await (await win.fetch("/skills?brain=b", { signal: ac.signal })).json();
  check("a read with its own timeout gets the copy at once too", withSignal.v === 2 && Date.now() - t1 < 5);
  await new Promise((r) => setTimeout(r, 20));

  await new Promise((r) => setTimeout(r, 1600));
  await win.fetch("/sessions/abc/read", { method: "POST" });
  body = { v: 3 };
  F.pageStart("skills");
  check("marking a chat read leaves the copy in place", (await get("/skills?brain=b")).v === 2);
  await new Promise((r) => setTimeout(r, 20));
  await new Promise((r) => setTimeout(r, 20));
  await win.fetch("/skills", { method: "POST", body: "x" });
  F.pageStart("skills");
  const before = net.length;
  await get("/skills?brain=b");
  check("any other write drops the copies (the next read waits for the server)", net.length === before + 1);
  F.forget();
  check("forget() is there for the end of a chat turn", typeof F.forget === "function"
    && /data\.type === "turn_done"\) \{[\s\S]{0,3000}window\.JavisFetchGop\.forget\(\);[\s\S]{0,40}notifySessions\(\);/.test(APP));
}

// ───────── console.js / index.html wiring ─────────
function wiring() {
  const con = read("dashboard/console.js");
  check("every page draw tells fetch-gop which page it is", /window\.JavisFetchGop\.pageStart\(id\);/.test(con));
  const pages = /const REDRAW_PAGES = new Set\(\[([^\]]+)\]\)/.exec(con);
  const list = pages ? pages[1] : "";
  check("list and card pages are drawn again when their data changed",
    ["skills", "mcp", "channels", "settings", "models", "learn", "usage", "webhooks"].every((p) => list.includes('"' + p + '"')));
  check("chat pages, the editor and the live Tasks board are not",
    ["chat", "workspace", "teams", "conversations", "files", "tasks"].every((p) => !list.includes('"' + p + '"')));
  check("a page the owner already clicked or typed on is left as it is",
    /if \(Alpine\.store\("nav"\)\.active !== id \|\| _pageTouched\) return;/.test(con)
    && /\["click", "keydown", "input", "change"\]/.test(con));
  check("signing out clears the kept chats", /await fetch\("\/auth\/logout"[\s\S]{0,200}window\.JavisChatCache\.clear\(\)/.test(con));
  const html = read("dashboard/index.html");
  const at = html.indexOf("/static/chat-cache.js?v=");
  check("chat-cache.js loads before app.js", at > 0 && at < html.indexOf("/static/app.js?v="));
  for (const f of ["dashboard/chat-cache.js", "dashboard/fetch-gop.js", "tests/js/test_instant_ui.js"]) {
    const s = read(f);
    check(f + " has no long dash", s.indexOf(String.fromCharCode(0x2014)) < 0 && s.indexOf(String.fromCharCode(0x2013)) < 0);
  }
}

chatCacheStore().then(keptChats).then(warming).then(pageCopies).then(wiring).then(() => {
  if (fails.length) { console.log("\nFAIL - test_instant_ui: " + fails.length); process.exit(1); }
  console.log("\nOK - test_instant_ui: all pass");
}, (e) => { console.log("FAIL crashed: " + (e && e.stack || e)); process.exit(1); });
