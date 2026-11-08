/* Performance (2026-11-05): switching chats, the Tasks page and the Teams page draw at once from what was already seen.

   What is pinned here:
   - nap-cham.js asks for every file of a page group at once (order is kept by async=false), not one after another;
   - app.js keeps the last chats opened: opening one again draws from memory, a server answer that is the same
     redraws nothing, a hover prefetch is shared with the click that follows;
   - workspace.js opens a partner's remembered chat in parallel with asking which chat is newest;
   - the Tasks page draws its last state on return, the Teams page keeps opened teams and does not refetch the open
     team on a "read" event.

   Second pass, same day (owner: "New conversation and switching history on the Partners page are slow"):
   - a chat just made by New conversation opens empty, with no request for its (zero) messages, and the old chat leaves
     the screen at the click;
   - the right column (settings form, history list) is not rebuilt for the same partner;
   - a plain switch (event reason "open") only re-lights the history row: no list, unread, job or inbox round trip;
   - the model bar and the project chip share one /sessions/<id>/meta request.

   Third pass (owner: "opening an old chat takes a few seconds", Chat, Workflow and Teams pages too), traced on a 4x
   slowed CPU: bubbles drawn from history no longer play the fade-in (each became its own compositor layer, ~660 ms
   of layer work per switch), Alpine no longer walks chat nodes, the chat view stops downloading stored tool calls
   it never shows, and the Teams page asks the server before it draws instead of after. */
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
    TIN_MOI_LUOT: 30, savedSessionId: null, convo: [], handsFree: false, sessionOpenSeq: 0, currentBrainPath: () => "b",
    tatRanhTay() {}, boViecPhienCu() {}, Date, Map, JSON, Promise, encodeURIComponent,
    fetch: (url) => { fetches++; const id = decodeURIComponent(url.split("/")[2].split("?")[0]);
      return Promise.resolve({ json: () => Promise.resolve(JSON.parse(JSON.stringify(answers[id]))) }); },
  };
  vm.createContext(ctx);
  ["_PHIEN_CACHE_MAX", "_PHIEN_CACHE_TTL", "_PREFETCH_TUOI", "_phienCache", "_phienDangTai"].forEach((n) => vm.runInContext(constLine(n), ctx));
  vm.runInContext("var _phienMoLuc = null; var _keptChatsLoading = null;", ctx);
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
  // Leaving a chat that grew (the owner sent a message) asks for its new copy at once (2026-11-08: it used to be
  // dropped, so going back to the chat being taught always waited for the server).
  ctx.convo.push(msg(5, "e"));
  answers.B.messages.push(msg(5, "e"));
  fetches = 0;
  await ctx.openStoredSession("A");
  await tick(); await tick();
  check("a chat that grew while open is fetched again when left, and its copy kept",
    fetches === 2 && ctx._phienCache.has("B") && ctx._phienCache.get("B").sess.messages.length === 3);
  // Prefetch: one request, shared by the click that follows.
  answers.C = { brain: "b", has_more: false, messages: [msg(6, "f")] };
  fetches = 0;
  ctx.prefetchSession("C");
  ctx.prefetchSession("C");
  await ctx.openStoredSession("C");
  check("a hover prefetch and the click after it make one request", fetches === 1);
  check("JavisSessions exposes prefetch", /prefetch: prefetchSession/.test(APP));
  // A chat made a moment ago: drawn empty at once, nothing asked.
  fetches = 0; drawn.length = 0;
  await ctx.openStoredSession("NEW", null, { empty: true });
  check("a just-created chat opens empty without a request", fetches === 0 && drawn.length === 1 && drawn[0].id === "NEW" && drawn[0].n === 0);
  check("JavisSessions exposes blank (clear the view at the click)", /blank: blankChat/.test(APP) && /function blankChat\(\)/.test(APP));
  check("a switch tells listeners its reason", /notifySessions\("open"\)/.test(APP) && /detail: \{ reason: reason \|\| "" \}/.test(APP));
}

// ───────── workspace.js: remembered chat opens in parallel ─────────
async function workspace() {
  const src = read("dashboard/workspace.js");
  const section = src.slice(src.indexOf("  async function moPhien("), src.indexOf("  function veLoi("));
  const order = [];
  let current = null;
  const reqs = [];
  const ctx = {
    opening: 0, ready: false, active: true, setTimeout, clearTimeout, S: { loai: "agent", sessionCuaPhien: {} },
    _phienGanNhat: { "b|agent:a": "s-old" }, khoaGanNhat: (x) => "b|agent:" + x.slug,
    chatReady(v) { ctx.ready = v; }, veGiua() {}, vePhai() { order.push("vePhai"); }, phaiDaVeCho: () => ctx.drawnFor === "a",
    veBuoc() {}, luuViTri() {}, daDoc() {}, coTinChuaDoc: () => false, ganCongHuong() {},
    brain: () => "b", kenh: (x) => "agent:" + x.slug, fd: (x) => x, t: (k) => k,
    conDangXem: () => true, dangChon: () => ({ slug: "a" }), tienDoHienTai: () => ({}), veLoi() {},
    api: (url) => { order.push("api"); return new Promise((r) => reqs.push(r)); },
    window: { JavisSessions: { current: () => current, new: () => { current = null; }, blank: () => { order.push("blank"); },
      open: async (id, still, opts) => { order.push("open:" + id + (opts && opts.empty ? ":empty" : "")); current = id; } } },
  };
  vm.createContext(ctx); vm.runInContext(section, ctx);
  const p = ctx.moPhien({ slug: "a" }, false);
  const net = order.filter((x) => x !== "vePhai");
  check("the remembered chat opens before the 'which chat is newest' answer", net[0] === "open:s-old" && net[1] === "api");
  reqs[0]({ sessions: [{ id: "s-old" }] });
  check("still the newest: it is not opened a second time", (await p) === true && order.filter((x) => x.indexOf("open:") === 0).length === 1);
  order.length = 0;
  const p2 = ctx.moPhien({ slug: "a" }, false);
  reqs[1]({ sessions: [{ id: "s-new" }] });
  await p2;
  check("a newer chat on the server wins", current === "s-new" && ctx._phienGanNhat["b|agent:a"] === "s-new");
  // New conversation for the partner whose column is already drawn.
  ctx.drawnFor = "a"; order.length = 0;
  const p3 = ctx.moPhien({ slug: "a" }, true);
  check("New conversation clears the chat at the click and does not rebuild the right column",
    order[0] === "blank" && order.indexOf("vePhai") < 0);
  reqs[2]({ id: "s-made" });
  await p3;
  check("the chat it made opens empty, with no request for its messages", order.indexOf("open:s-made:empty") >= 0 && current === "s-made");
  ctx.drawnFor = ""; order.length = 0;
  const p4 = ctx.moPhien({ slug: "a" }, false);
  check("another partner still gets its right column drawn", order[0] === "vePhai");
  reqs[3]({ sessions: [{ id: "s-new" }] });
  await p4;
}

// ───────── a plain switch costs no extra round trips ─────────
function switchListeners() {
  const side = read("dashboard/sessions-ui.js");
  check("the history list only re-lights its row on a switch",
    /e\.detail\.reason === "open" && chiToDongDangMo\(\)\) return;/.test(side) && /function chiToDongDangMo\(\)/.test(side));
  const ws = read("dashboard/workspace.js");
  check("job and unread counts are not reread on a switch",
    /if \(!laDoiPhien\(e\)\) henDemViec\(\);/.test(ws) && /if \(!laDoiPhien\(e\)\) henUnread\(\);/.test(ws));
  check("the Jobs tab does not reload on a switch", /e\.detail\.reason === "open"\) return; schedule\(\);/.test(read("dashboard/agent-jobs.js")));
  // Inbox: no read POST and no reload when nothing of this chat is unread.
  const noti = read("dashboard/notifications.js");
  const fn = noti.slice(noti.indexOf("  function coThuChuaDocCua("), noti.indexOf("  async function docThu("));
  const ctx = vm.createContext({ state: { thuTai: false, thuChuaDoc: 0, thu: [] } });
  vm.runInContext(fn, ctx);
  const has = (sid) => vm.runInContext("coThuChuaDocCua(" + JSON.stringify(sid) + ")", ctx);
  check("inbox not loaded yet: mark read to be safe", has("x") === true);
  ctx.state.thuTai = true;
  check("nothing unread: no inbox round trip", has("x") === false);
  ctx.state.thuChuaDoc = 1; ctx.state.thu = [{ session_id: "y", read: false }];
  check("unread for another chat only: no round trip", has("x") === false);
  check("unread for this chat: marked read", has("y") === true);
  ctx.state.thuChuaDoc = 5;
  check("more unread than the list holds: marked read to be safe", has("x") === true);
  check("docPhien goes through that check", /if \(!coThuChuaDocCua\(sid\)\) return;/.test(noti));
  const gop = require(path.join(ROOT, "dashboard", "fetch-gop.js"));
  check("the model bar and the project chip share one meta request",
    gop.gopDuoc("/sessions/abc123/meta", undefined, "http://x") && !gop.gopDuoc("/sessions/abc123?limit=30", undefined, "http://x"));
}

// ───────── Tasks and Teams pages ─────────
function pages() {
  const tasks = read("dashboard/tasks.js");
  check("the Tasks page keeps what it showed when it closes", /function unmount\(\) \{\s*if \(!S\) return;\s*keepLast\(\);/.test(tasks));
  check("the Tasks page draws that at once on return, then refreshes", /if \(useLast\(\)\) \{[^\n]*render\(\);/.test(tasks) && /await load\(\);/.test(tasks));
  check("a load that lands after the page closed writes nothing", /if \(!S \|\| S !== st\) return;/.test(tasks));
  const teams = read("dashboard/teams.js");
  check("a team opened before draws from the cache", /useTeam\(id\);[\s\S]{0,600}?drawAll\(true\);/.test(teams));
  check("a 'read' event does not refetch the open team", /d\.type !== "team_read" && d\.team_id === S\.activeId/.test(teams));
}

// ───────── third pass: drawing a chat from history is light (Chat, Partners, Workflow, Teams) ─────────
function historyDraw() {
  const css = read("dashboard/style.css");
  check("bubbles drawn from history skip the fade-in",
    /if \(\(_dangDungLoat \|\| _dangChenCu\) && el && el\.classList\) el\.classList\.add\("msg-tinh"\);/.test(APP)
    && /\.msg\.msg-tinh \{ animation: none; \}/.test(css));
  check("a message arriving live still fades in", /\.msg \{ animation: fadeIn 0\.2s ease; \}/.test(css));
  check("Alpine does not walk the chat area", /chatArea\._x_ignoreMutationObserver = true;/.test(APP));
  check("building a chat or a page of older messages runs outside Alpine's watcher",
    (APP.match(/ngoaiAlpine\(\(\) => ds\.forEach/g) || []).length === 2);
  // ngoaiAlpine falls back to a plain call when Alpine is missing, and uses mutateDom when it is there.
  const fn = APP.slice(APP.indexOf("function ngoaiAlpine("), APP.indexOf("\n}", APP.indexOf("function ngoaiAlpine(")) + 2);
  const seen = [];
  const ctx = vm.createContext({ window: {} });
  vm.runInContext(fn, ctx);
  check("without Alpine the build still runs", vm.runInContext("ngoaiAlpine(() => 7)", ctx) === 7);
  ctx.window.Alpine = { mutateDom: (f) => { seen.push("paused"); return f(); } };
  check("with Alpine the build runs inside mutateDom", vm.runInContext("ngoaiAlpine(() => 8)", ctx) === 8 && seen.length === 1);
  check("the chat view asks for messages without tool calls",
    /\?limit=\$\{TIN_MOI_LUOT\}&tools=0`/.test(APP) && /\/messages\?limit=\$\{TIN_MOI_LUOT\}&tools=0`/.test(APP));
  const teams = read("dashboard/teams.js");
  check("Teams: the three requests leave before the page is drawn",
    /var loads = Promise\.all\(\[loadTeam\(\), loadQueue\(\), loadMsgs\(false\)\]\);\s*\n\s*drawAll\(true\);\s*\n\s*loads\.then\(/.test(teams));
  check("Teams: the message list is kept out of Alpine's watcher",
    /box\._x_ignoreMutationObserver = true;/.test(teams) && /A\.mutateDom\(sync\)/.test(teams));
}

napCham().then(chatCache).then(workspace).then(switchListeners).then(historyDraw).then(pages).then(() => {
  if (fails.length) { console.log("\nFAIL - test_hieu_nang_chuyen_trang: " + fails.length); process.exit(1); }
  console.log("\nOK - test_hieu_nang_chuyen_trang: all pass");
}, (e) => { console.log("FAIL crashed: " + (e && e.stack || e)); process.exit(1); });
