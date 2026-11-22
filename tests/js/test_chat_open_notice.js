/* A chat that cannot be brought up to date says so (customer report, 2026-11-20).

   A customer saw an old last message on the computer for a week while the phone showed the new ones, and one chat of
   193 messages would not open. Two silent paths in dashboard/app.js could do that:
   - the server's answer for a chat hung or failed: the copy kept in this browser stayed on screen as if current, and a
     chat with no copy just did not open, with no sign either way;
   - one stored message the renderer choked on stopped the drawing there (one try/catch around the whole chat), so the
     screen ended on an older message, and the error was swallowed without a trace.

   Pinned here:
   - openStoredSession shows "slow" (no copy) or "stale" (a copy on screen) after _OPEN_SLOW_MS, "failed" or "stale"
     when the read fails or answers an error, removes the line when a late answer lands, and forgets a deleted chat;
   - the Retry button asks the server afresh instead of joining the read that hung;
   - _safeDraw draws a message that throws as plain text (no duplicate when the bubble already made it) and reports it;
   - restoreSession, the chat open and the older-messages load all draw through _safeDraw;
   - loi-may-khach.js has report() for errors caught on purpose; the new strings exist in vi and en.

    node tests/js/test_chat_open_notice.js
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

// ───────── openStoredSession: the slow / stale / failed line ─────────
function openCtx() {
  const st = { notices: [], hidden: 0, drawn: [], timers: [], fetches: 0, answer: null, deleted: [] };
  const ctx = {
    TIN_MOI_LUOT: 30, savedSessionId: null, convo: [], handsFree: false, sessionOpenSeq: 0, currentBrainPath: () => "b",
    tatRanhTay() {}, boViecPhienCu() {}, Date, Map, JSON, Promise, encodeURIComponent,
    window: { JavisChatCache: { del(id) { st.deleted.push(id); } } },
    // Timers run only when the test says so: setTimeout returns its id, fire() runs what is still armed.
    setTimeout(fn, ms) { st.timers.push({ fn, ms, on: true }); return st.timers.length; },
    clearTimeout(i) { if (st.timers[i - 1]) st.timers[i - 1].on = false; },
    fetch() { st.fetches++; return st.answer(); },
    _showOpenNotice(id, kind) { st.notices.push(id + ":" + kind); },
    _hideOpenNotice() { st.hidden++; },
  };
  vm.createContext(ctx);
  ["_PHIEN_CACHE_MAX", "_PHIEN_CACHE_TTL", "_PREFETCH_TUOI", "_OPEN_SLOW_MS", "_phienCache", "_phienDangTai"]
    .forEach((n) => vm.runInContext(constLine(n), ctx));
  vm.runInContext("var _phienMoLuc = null; var _keptChatsLoading = null;", ctx);
  ["_urlPhien", "_ghiCachePhien", "_docCachePhien", "_vanTayPhien", "_taiPhien", "_quenPhienNeuDoi", "openStoredSession"]
    .forEach((n) => vm.runInContext(fnSrc(n), ctx));
  ctx._veLaiPhien = (id, sess, ticket, capNhat) => {
    st.drawn.push({ id, n: sess.messages.length, capNhat });
    ctx.savedSessionId = id; ctx.convo = sess.messages.slice();
    vm.runInContext("_phienMoLuc = { id: savedSessionId, len: convo.length };", ctx);
  };
  st.fire = () => st.timers.forEach((t) => { if (t.on) { t.on = false; t.fn(); } });
  return { ctx, st };
}
const msg = (id) => ({ id, role: "assistant", content: "x" + id, content_sha: "s" + id, ts: id });
const json = (v) => Promise.resolve({ json: () => Promise.resolve(JSON.parse(JSON.stringify(v))) });

async function openNotice() {
  check("the wait before the line is a few seconds", /^const _OPEN_SLOW_MS = 8000;/m.test(APP));

  // No copy kept, the server never answers: "slow" once the wait is over.
  let { ctx, st } = openCtx();
  st.answer = () => new Promise(() => {});
  ctx.openStoredSession("A");
  await tick();
  check("no line before the wait is over", st.notices.length === 0 && st.timers.length === 1 && st.timers[0].ms === 8000);
  st.fire();
  check("a chat with no copy that hangs says it is slow", st.notices.join() === "A:slow");

  // A copy kept, the server never answers: "stale".
  ({ ctx, st } = openCtx());
  ctx._phienCache.set("B", { sess: { brain: "b", has_more: false, messages: [msg(1)] }, at: Date.now() });
  st.answer = () => new Promise(() => {});
  ctx.openStoredSession("B");
  await tick();
  st.fire();
  check("a kept copy on screen while the server hangs is called stale", st.drawn.length === 1 && st.notices.join() === "B:stale");

  // The answer comes late: the line goes, the chat is drawn again.
  ({ ctx, st } = openCtx());
  ctx._phienCache.set("C", { sess: { brain: "b", has_more: false, messages: [msg(1)] }, at: Date.now() });
  let late;
  st.answer = () => new Promise((r) => { late = r; });
  const opening = ctx.openStoredSession("C");
  await tick();
  st.fire();
  const hiddenBefore = st.hidden;
  late({ json: () => Promise.resolve({ brain: "b", has_more: false, messages: [msg(1), msg(2)] }) });
  await opening;
  check("a late answer removes the line and redraws the chat",
    st.hidden > hiddenBefore && st.drawn.length === 2 && st.drawn[1].n === 2 && st.drawn[1].capNhat === true);

  // A fast answer: no line, and the timer is cleared.
  ({ ctx, st } = openCtx());
  st.answer = () => json({ brain: "b", has_more: false, messages: [msg(1)] });
  await ctx.openStoredSession("D");
  st.fire();
  check("a fast answer leaves no line behind", st.notices.length === 0 && st.drawn.length === 1);

  // The read fails (network gone after the retries, or an HTML page instead of JSON).
  ({ ctx, st } = openCtx());
  st.answer = () => Promise.reject(new Error("Failed to fetch"));
  await ctx.openStoredSession("E");
  check("a failed read with nothing on screen says failed", st.notices.join() === "E:failed" && st.drawn.length === 0);
  ({ ctx, st } = openCtx());
  ctx._phienCache.set("F", { sess: { brain: "b", has_more: false, messages: [msg(1)] }, at: Date.now() });
  st.answer = () => Promise.resolve({ json: () => Promise.reject(new SyntaxError("Unexpected token <")) });
  await ctx.openStoredSession("F");
  check("a failed read with a copy on screen says stale", st.notices.join() === "F:stale");

  // A chat deleted elsewhere: its kept copies go.
  ({ ctx, st } = openCtx());
  ctx._phienCache.set("G", { sess: { brain: "b", has_more: false, messages: [msg(1)] }, at: Date.now() });
  st.answer = () => json({ error: "not found" });
  await ctx.openStoredSession("G");
  check("a chat the server no longer has is forgotten here", !ctx._phienCache.has("G") && st.deleted.join() === "G");

  // Switching to another chat before the wait is over: no line for the chat left behind.
  ({ ctx, st } = openCtx());
  st.answer = () => new Promise(() => {});
  ctx.openStoredSession("H");
  await tick();
  ctx.sessionOpenSeq++;
  st.fire();
  check("a chat left before the wait is over gets no line", st.notices.length === 0);
  check("opening a chat removes the line of the one before", /const ticket = \+\+sessionOpenSeq;\n  _hideOpenNotice\(\);/.test(APP));

  // Retry: a fresh read, not the one that hung.
  const show = fnSrc("_showOpenNotice");
  check("Retry drops the hung read, then opens the chat again",
    /_phienDangTai\.delete\(id\);[^\n]*\n\s*openStoredSession\(id\);/.test(show));
  check("the line speaks through i18n", /slow: "app\.open_slow", stale: "app\.open_stale", failed: "app\.open_failed"/.test(show) && /window\.t\("app\.open_retry"\)/.test(show));

  // Back on the tab after the phone or computer slept: giving up is no longer silent.
  const sync = fnSrc("_dongBoNeuLech");
  check("the resync that gives up says the chat is stale", /else if \(sid === savedSessionId[^\n]*_showOpenNotice\(sid, "stale"\)/.test(sync));
  check("the resync that finds the chat current removes the line", /else _hideOpenNotice\(\);/.test(sync));
}

// ───────── _safeDraw: one bad message does not cut the chat short ─────────
function el(tag) {
  const e = { tag, className: "", dataset: {}, children: [], textContent: "", attrs: {},
    appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; } };
  return e;
}
function drawCtx() {
  const area = [];
  const reported = [];
  const ctx = {
    document: { createElement: el },
    chatArea: { querySelectorAll: (sel) => (sel === ".msg" ? area.filter((x) => /\bmsg\b/.test(x.className)) : []) },
    chatAppend(x) { area.push(x); },
    chuNguoiGo: (s) => String(s).replace(/^\[FILE ĐANG MỞ[^\]]*\]\n\n/, ""),
    window: { JavisLoiMayKhach: { report(where, e) { reported.push(where + ":" + e.message); } } },
    console: { error() {} },
  };
  vm.createContext(ctx);
  ["_reportCaught", "_drawPlainMessage", "_safeDraw"].forEach((n) => vm.runInContext(fnSrc(n), ctx));
  return { ctx, area, reported };
}

function safeDraw() {
  let { ctx, area, reported } = drawCtx();
  const m = { id: 7, role: "assistant", content: "Bang ket qua <!-- JAVIS_VIEC: {} -->\nDong 2", content_sha: "h", ts: 2 };
  const entry = ctx._safeDraw(() => { throw new Error("render broke"); }, m, "brainX");
  check("a message the renderer throws on is still drawn, as plain text",
    area.length === 1 && /msg-javis/.test(area[0].className) && /msg-plain/.test(area[0].className)
    && area[0].children[0].textContent === "Bang ket qua \nDong 2");
  check("its convo entry keeps the id, so reactions and reloads still work",
    entry && entry.role === "javis" && entry.mid === 7 && entry.sha === "h" && entry.ts === 2000 && entry.brain === "brainX");
  check("the error reaches the Health page", reported.join() === "chat.message:render broke");

  ({ ctx, area, reported } = drawCtx());
  const ok = ctx._safeDraw(() => { area.push({ className: "msg msg-javis" }); return { role: "javis" }; }, m, "b");
  check("a message that draws fine is untouched", area.length === 1 && ok.role === "javis" && reported.length === 0);

  ({ ctx, area, reported } = drawCtx());
  const after = ctx._safeDraw(() => { area.push({ className: "msg msg-javis" }); throw new Error("pin failed"); }, m, "b");
  check("no second bubble when the bubble made it and only an extra after it failed",
    area.length === 1 && after === null && reported.length === 1);

  ({ ctx, area } = drawCtx());
  const u = ctx._safeDraw(() => { throw new Error("x"); },
    { id: 8, role: "user", content: "[FILE ĐANG MỞ trong trình sửa của Javis: a.md]\n\nSua giup anh", ts: 3 }, "b");
  check("a user message falls back without the context block the app added",
    /msg-user/.test(area[0].className) && area[0].children[0].textContent === "Sua giup anh" && u.text === "Sua giup anh");

  ({ ctx, area } = drawCtx());
  check("an unknown role draws nothing", ctx._safeDraw(() => { throw new Error("x"); }, { role: "tool" }, "b") === null && area.length === 0);

  check("opening a chat draws each message through _safeDraw",
    APP.includes("_safeDraw(() => veTinDaLuu(m, sess.brain, id), m, sess.brain)"));
  check("loading older messages draws each one through _safeDraw",
    APP.includes("_safeDraw(() => veTinDaLuu(m, st.brain, st.sid), m, st.brain)"));
  const restore = fnSrc("restoreSession");
  check("the copy restored after a reload draws each message through _safeDraw",
    /convo\.forEach\(\(t, i\) => _safeDraw\(\(\) => \{/.test(restore));
  const redraw = fnSrc("_veLaiPhien");
  check("an error while opening a chat is reported, not only swallowed", /_reportCaught\("chat\.open", e\)/.test(redraw));
}

// ───────── loi-may-khach.js, strings, style ─────────
function wiring() {
  const box = read("dashboard/loi-may-khach.js");
  check("the error box takes errors caught on purpose", /api\.report = function \(where, err\)/.test(box) && /them\("caught"/.test(box));
  const vi = JSON.parse(read("dashboard/i18n/vi.json"));
  const en = JSON.parse(read("dashboard/i18n/en.json"));
  const keys = ["app.open_slow", "app.open_stale", "app.open_failed", "app.open_retry"];
  check("the line's strings exist in Vietnamese and English", keys.every((k) => vi[k] && en[k]));
  check("the line is readable on a phone", /\.msg-ghichu\.msg-open-notice \{ font-size: 16px;/.test(read("dashboard/style.css")));
  const dash = String.fromCharCode(0x2014), endash = String.fromCharCode(0x2013);
  const touched = ["_reportCaught", "_drawPlainMessage", "_safeDraw", "_showOpenNotice", "_hideOpenNotice", "openStoredSession"]
    .map(fnSrc).join("\n") + keys.map((k) => vi[k] + en[k]).join("");
  check("no em or en dash in what changed", !touched.includes(dash) && !touched.includes(endash));
}

(async () => {
  try {
    await openNotice();
    safeDraw();
    wiring();
  } catch (e) {
    check("crashed: " + (e && e.stack || e), false);
  }
  if (fails.length) { console.log("\nFAIL - test_chat_open_notice: " + fails.length); process.exit(1); }
  console.log("\nOK - test_chat_open_notice: all pass");
})();
