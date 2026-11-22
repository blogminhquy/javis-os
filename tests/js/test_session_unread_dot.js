/* Red unread dot in every chat history list (2026-11-06): the Chat page, the Partners history column (same module,
   sessions-ui.js) and the count pills of team and partner rows.

       node tests/js/test_session_unread_dot.js

   The helpers that decide "read" run for real here, on a tiny fake page: a chat is read only while it is on a
   visible screen, each chat is reported once per burst of events, and a read in another tab clears the dot. */
const fs = require("fs");
const path = require("path");
const R = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(R, f), "utf8");
const SRC = read("dashboard/sessions-ui.js");
const APP = read("dashboard/app.js");
const STYLE = read("dashboard/style.css");
const CONSOLE = read("dashboard/console.css");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

let fails = 0;
function check(name, ok) { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; }

// ---- the row ----
const rl = SRC.slice(SRC.indexOf("function renderList(items, hasMore)"), SRC.indexOf("async function doSearch(q)"));
check("unread row gets has-unread and a red dot", rl.includes('(chuaDoc ? " has-unread" : "")') && rl.includes('class="ci-unread"'));
check("the dot is labelled for screen readers", /ci-unread" role="img" title="' \+ esc\(window\.t\("sess\.unread"\)\) \+ '" aria-label=/.test(rl));
check("the chat on screen shows no dot and is reported read",
  /if \(chuaDoc && s\.id === cur && chatOnScreen\(\) && !isHeldUnread\(s\.id\)\) \{ chuaDoc = false; s\.unread = false; markRead\(s\.id\); \}/.test(rl));
check("a chat still running shows its spinner, not a dot (owner 2026-11-20)",
  rl.includes("var chuaDoc = !!s.unread && !isRun;") && rl.includes("!!s.unread && !isRunning(s.id)"));
const RAIL = fs.readFileSync(path.join(__dirname, "../../dashboard/rail-unread.js"), "utf8");
check("the rail skips running chats and counts again when a run ends",
  RAIL.includes("unreadSkipQuery()") && RAIL.includes('"javis:chat-turn"'));

// ---- the events ----
check("every chat change marks the chat on screen read",
  /window\.addEventListener\("javis:sessions-changed", function \(e\) \{[^}]*?markCurrentRead\(\);/.test(SRC));
check("coming back to the tab marks it read", SRC.includes('document.addEventListener("visibilitychange", markCurrentRead);'));
check("a read in another tab clears the dot here", /window\.addEventListener\("javis:session-read", function \(e\) \{[\s\S]{0,120}clearDot\(sid\)/.test(SRC));
check("app.js relays the session_read socket event", /data\.type === "session_read"[\s\S]{0,200}new CustomEvent\("javis:session-read", \{ detail: data \}\)/.test(APP));

// ---- the helpers, run for real ----
const start = SRC.indexOf("  function chatOnScreen() {");
const end = SRC.indexOf("\n  }\n", SRC.indexOf("  function clearDot(sid) {")) + 4;
const helpers = SRC.slice(start, end);
function makeRow(sid, unread) {
  const classes = new Set(["cside-item"].concat(unread ? ["has-unread"] : []));
  const dot = unread ? { parentNode: null } : null;
  const row = {
    getAttribute: (k) => (k === "data-sid" ? sid : null),
    classList: { remove: (c) => classes.delete(c), contains: (c) => classes.has(c) },
    querySelector: (q) => (q === ".ci-unread" ? row.dot : null),
    dot,
  };
  if (dot) dot.parentNode = { removeChild: () => { row.dot = null; } };
  return row;
}
function harness(opts) {
  const posts = [], timers = [];
  const rows = [makeRow("a", true), makeRow("b", true)];
  const env = {
    document: { visibilityState: opts.visible ? "visible" : "hidden",
      getElementById: (id) => (id === "chatArea" ? { getClientRects: () => (opts.chatShown ? [1] : []) } : null) },
    fetch: (url, o) => { posts.push([url, o && o.method]); return Promise.resolve(); },
    setTimeout: (fn) => { timers.push(fn); return timers.length; },
    current: opts.current,
    listEl: { querySelectorAll: () => rows },
    cached: { items: [{ id: "a", unread: true }, { id: "b", unread: true }] },
  };
  env.window = { JavisRunning: new Set(opts.running || []) };
  const api = new Function("document", "fetch", "setTimeout", "env", "window",
    "var listEl = env.listEl, cached = env.cached; function currentId() { return env.current; }\n" + helpers +
    "\nreturn { chatOnScreen: chatOnScreen, markRead: markRead, markCurrentRead: markCurrentRead, clearDot: clearDot," +
    " unreadSkipIds: unreadSkipIds, isHeldUnread: isHeldUnread, hold: function (sid) { heldUnread = sid; } };")(
    env.document, env.fetch, env.setTimeout, env, env.window);
  const flush = () => { while (timers.length) timers.shift()(); };
  return { api, posts, rows, env, flush };
}

let h = harness({ visible: true, chatShown: true, current: "a" });
h.api.markCurrentRead(); h.api.markCurrentRead(); h.api.markCurrentRead();
h.flush();
check("chat on screen: one POST for a burst of events", h.posts.length === 1 && h.posts[0][0] === "/sessions/a/read" && h.posts[0][1] === "POST");
check("its dot goes at once", !h.rows[0].classList.contains("has-unread") && h.rows[0].dot === null && h.env.cached.items[0].unread === false);
check("other rows keep their dot", h.rows[1].classList.contains("has-unread") && h.env.cached.items[1].unread === true);

h = harness({ visible: true, chatShown: true, current: "a" });
h.api.markRead("a"); h.api.markRead("b"); h.flush();
check("a quick switch reports both chats", h.posts.map((p) => p[0]).join() === "/sessions/a/read,/sessions/b/read");

h = harness({ visible: false, chatShown: true, current: "a" });
h.api.markCurrentRead(); h.flush();
check("tab in the background: nothing is read", h.posts.length === 0 && h.rows[0].classList.contains("has-unread"));

h = harness({ visible: true, chatShown: false, current: "a" });
h.api.markCurrentRead(); h.flush();
check("chat not on screen (another page): nothing is read", h.posts.length === 0);

h = harness({ visible: true, chatShown: true, current: null });
h.api.markCurrentRead(); h.flush();
check("no chat open: nothing is read", h.posts.length === 0);

h = harness({ visible: true, chatShown: true, current: "a" });
h.api.clearDot("b");
check("clearDot from another tab touches only that row", !h.rows[1].classList.contains("has-unread") && h.rows[0].classList.contains("has-unread") && h.posts.length === 0);

// ---- "Mark as unread" on the chat open on screen (owner 2026-11-20) ----
const menu = SRC.slice(SRC.indexOf("var h2 = smItem(\"pin\""), SRC.indexOf("function veMenuDong("));
check("the open chat's menu offers Mark as unread too", menu.includes('else if (!isRunning(s.id)) h2 += smItem("unread", "mail", "sess.mark_unread");')
  && !menu.includes("s.id !== currentId()"));
const act = SRC.slice(SRC.indexOf('if (act === "unread") {'), SRC.indexOf('if (act === "archive")'));
check("marking the open chat unread holds it and drops a pending read",
  act.includes("if (s.id === currentId()) heldUnread = s.id;") && act.includes("clearTimeout(readTimers[s.id])"));
check("the rail and project dots count again after marking unread",
  act.includes("refreshProjects();") && act.includes("window.JavisRailUnread.refresh()"));

h = harness({ visible: true, chatShown: true, current: "a" });
h.api.hold("a");
h.api.markCurrentRead(); h.flush();
check("held chat on screen: not read, dot stays", h.posts.length === 0 && h.rows[0].classList.contains("has-unread"));
check("held chat is counted unread (not skipped)", h.api.unreadSkipIds().indexOf("a") < 0);
h.env.current = "b";
h.api.markCurrentRead(); h.flush();
check("opening another chat releases the hold", h.api.isHeldUnread("a") === false && h.posts.map((p) => p[0]).join() === "/sessions/b/read");
h.env.current = "a";
h.api.markCurrentRead(); h.flush();
check("coming back to it reads it again", h.posts.map((p) => p[0]).join() === "/sessions/b/read,/sessions/a/read");

h = harness({ visible: true, chatShown: true, current: "a", running: ["a"] });
h.api.hold("a");
check("a new turn in the held chat releases the hold", h.api.isHeldUnread("a") === false);

// ---- the look ----
check("the dot is red", /\.ci-unread \{[^}]*background: var\(--red\)/.test(STYLE));
check("an unread title reads heavier", STYLE.includes(".cside-item.has-unread .ci-title { font-weight: 800; }"));
check("team and partner counts are red, muted stays grey",
  CONSOLE.includes(".tm-unread:not(.is-muted) { background: var(--red); color: #fff; }") &&
  CONSOLE.includes(".tm-unread.is-muted { background: var(--surface-2); color: var(--text2); }"));
check("label in both languages", vi["sess.unread"] === "Chưa đọc" && en["sess.unread"] === "Unread");

if (fails) { console.log(`\n${fails} FAILED`); process.exit(1); }
console.log("\nOK - session_unread_dot");
