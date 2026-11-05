/* Performance (2026-11-05): switching chats, the Tasks page and the Teams page draw at once from what was already seen.

   What is pinned here:
   - nap-cham.js asks for every file of a page group at once (order is kept by async=false), not one after another;
   - app.js keeps the last chats opened: opening one again draws from memory, a server answer that is the same
     redraws nothing, a hover prefetch is shared with the click that follows;
   - workspace.js opens a partner's remembered chat in parallel with asking which chat is newest;
   - the Tasks page draws its last state on return, the Teams page keeps opened teams and does not refetch the open
     team on a "read" event. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };
const tick = () => new Promise((r) => setTimeout(r, 0));

// ───────── nap-cham.js: one group's files are requested together ─────────
async function napCham() {
  const appended = [];
  const pending = [];
  const doc = {
    readyState: "loading",
    getElementById: () => ({ textContent: JSON.stringify({ a: ["/static/x.css?v=1", "/static/x.js?v=1", "/static/y.js?v=1"] }) }),
    createElement: (tag) => ({ tag }),
    head: { appendChild: (el) => { appended.push(el); pending.push(el); } },
    body: { appendChild: (el) => { appended.push(el); pending.push(el); } },
  };
  const win = { addEventListener() {}, requestIdleCallback: null };
  const ctx = vm.createContext({ window: win, document: doc, setTimeout, Promise, JSON, Array });
  vm.runInContext(read("dashboard/nap-cham.js"), ctx);
  const done = win.JavisNapCham.cho("a");
  await tick();
  check("every file of the group is requested before the first one has loaded", appended.length === 3);
  check("CSS first, then the scripts in the declared order",
    appended.map((e) => e.href || e.src).join(",") === "/static/x.css?v=1,/static/x.js?v=1,/static/y.js?v=1");
  check("scripts keep their run order (async = false)", appended.filter((e) => e.src).every((e) => e.async === false));
  let finished = false;
  done.then(() => { finished = true; });
  pending[0].onload(); pending[1].onload();
  await tick();
  check("the group is not done while one file is still loading", !finished && !win.JavisNapCham.daXong("a"));
  pending[2].onload();
  await done;
  check("the group is done once every file has loaded", win.JavisNapCham.daXong("a"));
  const src = read("dashboard/nap-cham.js");
  check("the Tasks page is among the first groups of the background load", /UU_TIEN = \["congviec", "teams", "nhiemvu"/.test(src));
  const con = read("dashboard/console.js");
  check("pointing at a rail item starts loading that page's code",
    /closest\("\.rail-item\[data-page\]"\)/.test(con) && /:data-page="it\.id"/.test(read("dashboard/index.html")));
}

// ───────── app.js: chat cache ─────────
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
async function chatCache() {
  let fetches = 0;
  const answers = {};
  const drawn = [];
  const ctx = {
    TIN_MOI_LUOT: 30, savedSessionId: null, convo: [], handsFree: false, sessionOpenSeq: 0,
    tatRanhTay() {}, boViecPhienCu() {}, Date, Map, JSON, Promise, encodeURIComponent,
    fetch: (url) => { fetches++; const id = decodeURIComponent(url.split("/")[2].split("?")[0]);
      return Promise.resolve({ json: () => Promise.resolve(JSON.parse(JSON.stringify(answers[id]))) }); },
  };
  vm.createContext(ctx);
  ["_PHIEN_CACHE_MAX", "_PHIEN_CACHE_TTL", "_PREFETCH_TUOI", "_phienCache", "_phienDangTai"].forEach((n) => vm.runInContext(constLine(n), ctx));
  vm.runInContext("var _phienMoLuc = null;", ctx);
  ["_urlPhien", "_ghiCachePhien", "_docCachePhien", "_vanTayPhien", "_taiPhien", "prefetchSession", "_quenPhienNeuDoi",
    "openStoredSession"].forEach((n) => vm.runInContext(fnSrc(n), ctx));
  // The real drawing is the DOM; here it records what was drawn and plays its bookkeeping.
  ctx._veLaiPhien = (id, sess, ticket, capNhat) => {
    drawn.push({ id, n: sess.messages.length, capNhat });
    ctx.savedSessionId = id; ctx.convo = sess.messages.slice();
    vm.runInContext("_phienMoLuc = { id: savedSessionId, len: convo.length };", ctx);
  };
  const msg = (id, sha) => ({ id, role: "assistant", content: "x", content_sha: sha, ts: id });
  answers.A = { brain: "b", has_more: false, messages: [msg(1, "a"), msg(2, "b")] };
  answers.B = { brain: "b", has_more: false, messages: [msg(3, "c")] };

  await ctx.openStoredSession("A");
  check("first open of a chat draws once, from the server", drawn.length === 1 && drawn[0].id === "A" && fetches === 1);
  await ctx.openStoredSession("B");
  drawn.length = 0;
  const p = ctx.openStoredSession("A");
  check("opening a chat seen before draws it at once, before the server answers", drawn.length === 1 && drawn[0].id === "A");
  await p;
  check("a server answer equal to what is on screen redraws nothing", drawn.length === 1);
  answers.B.messages.push(msg(4, "d"));
  drawn.length = 0;
  await ctx.openStoredSession("B");
  check("a newer server answer redraws the chat once more", drawn.length === 2 && drawn[1].n === 2 && drawn[1].capNhat === true);
  // Leaving a chat that grew (the owner sent a message) forgets it, so it is not drawn short next time.
  ctx.convo.push(msg(5, "e"));
  await ctx.openStoredSession("A");
  check("a chat that grew while open is dropped from the cache when left", !ctx._phienCache.has("B"));
  // Prefetch: one request, shared by the click that follows.
  answers.C = { brain: "b", has_more: false, messages: [msg(6, "f")] };
  fetches = 0;
  ctx.prefetchSession("C");
  ctx.prefetchSession("C");
  await ctx.openStoredSession("C");
  check("a hover prefetch and the click after it make one request", fetches === 1);
  check("JavisSessions exposes prefetch", /prefetch: prefetchSession/.test(APP));
}

// ───────── workspace.js: remembered chat opens in parallel ─────────
async function workspace() {
  const src = read("dashboard/workspace.js");
  const section = src.slice(src.indexOf("  async function moPhien("), src.indexOf("  function veLoi("));
  const order = [];
  let current = null;
  const reqs = [];
  const ctx = {
    opening: 0, ready: false, active: true, S: { loai: "agent", sessionCuaPhien: {} },
    _phienGanNhat: { "b|agent:a": "s-old" }, khoaGanNhat: (x) => "b|agent:" + x.slug,
    chatReady(v) { ctx.ready = v; }, veGiua() {}, vePhai() {}, veBuoc() {}, luuViTri() {}, daDoc() {}, ganCongHuong() {},
    brain: () => "b", kenh: (x) => "agent:" + x.slug, fd: (x) => x, t: (k) => k,
    conDangXem: () => true, dangChon: () => ({ slug: "a" }), tienDoHienTai: () => ({}), veLoi() {},
    api: (url) => { order.push("api"); return new Promise((r) => reqs.push(r)); },
    window: { JavisSessions: { current: () => current, open: async (id) => { order.push("open:" + id); current = id; }, new: () => { current = null; } } },
  };
  vm.createContext(ctx); vm.runInContext(section, ctx);
  const p = ctx.moPhien({ slug: "a" }, false);
  check("the remembered chat opens before the 'which chat is newest' answer", order[0] === "open:s-old" && order[1] === "api");
  reqs[0]({ sessions: [{ id: "s-old" }] });
  check("still the newest: it is not opened a second time", (await p) === true && order.filter((x) => x.indexOf("open:") === 0).length === 1);
  order.length = 0;
  const p2 = ctx.moPhien({ slug: "a" }, false);
  reqs[1]({ sessions: [{ id: "s-new" }] });
  await p2;
  check("a newer chat on the server wins", current === "s-new" && ctx._phienGanNhat["b|agent:a"] === "s-new");
}

// ───────── Tasks and Teams pages ─────────
function pages() {
  const tasks = read("dashboard/tasks.js");
  check("the Tasks page keeps what it showed when it closes", /function unmount\(\) \{\s*if \(!S\) return;\s*keepLast\(\);/.test(tasks));
  check("the Tasks page draws that at once on return, then refreshes", /if \(useLast\(\)\) \{[^\n]*render\(\);/.test(tasks) && /await load\(\);/.test(tasks));
  check("a load that lands after the page closed writes nothing", /if \(!S \|\| S !== st\) return;/.test(tasks));
  const teams = read("dashboard/teams.js");
  check("a team opened before draws from the cache", /useTeam\(id\);\s*\n\s*drawAll\(true\);/.test(teams));
  check("a 'read' event does not refetch the open team", /d\.type !== "team_read" && d\.team_id === S\.activeId/.test(teams));
}

napCham().then(chatCache).then(workspace).then(pages).then(() => {
  if (fails.length) { console.log("\nFAIL - test_hieu_nang_chuyen_trang: " + fails.length); process.exit(1); }
  console.log("\nOK - test_hieu_nang_chuyen_trang: all pass");
}, (e) => { console.log("FAIL crashed: " + (e && e.stack || e)); process.exit(1); });
