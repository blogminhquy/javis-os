/* `#p=<page id>` opens a dashboard page (issue 1346, step 1).

       node tests/js/test_deep_link_page.js

   Before: only `#open=<vault path>` and `#cs=<spec>` were read, once, on load. Five modules set
   `location.hash = "#kanban"` (or "#mcp", "#" + id) when the Alpine nav store was not ready, which
   looked like a route but did nothing. Now `#p=<id>` is read on load next to the other two, a
   `hashchange` listener handles all three in an open tab, and those fallbacks write `#p=<id>`.

   Runs console.js's deepLinkPage and runDeepLink for real in a vm; the rest is read from source. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const D = (f) => fs.readFileSync(path.join(ROOT, "dashboard", f), "utf8");
const CONSOLE = D("console.js");

const fails = [];
const check = (name, cond, extra) => {
  console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  if (!cond) fails.push(name);
};

// ============================================================
// 1. deepLinkPage: which hash names which page
// ============================================================
const railSrc = (/const RAIL_ITEMS = \[([\s\S]*?)\]\.map\(/.exec(CONSOLE) || [])[1];
const gopSrc = (/const TRANG_GOP = (\{[^}]*\});/.exec(CONSOLE) || [])[1];
const fnStart = CONSOLE.indexOf("  function deepLinkPage(hash) {");
const fnSrc = fnStart < 0 ? "" : CONSOLE.slice(fnStart, CONSOLE.indexOf("\n  }\n", fnStart) + 4);
check("console.js has RAIL_ITEMS, TRANG_GOP and deepLinkPage", !!(railSrc && gopSrc && fnSrc));

const ids = vm.runInNewContext("[" + railSrc + "]");
const ctx = { RAIL_BY_ID: Object.fromEntries(ids.map((id) => [id, { id }])) };
vm.createContext(ctx);
vm.runInContext("const TRANG_GOP = " + gopSrc + ";\n" + fnSrc + "\nthis.deepLinkPage = deepLinkPage;", ctx);
const page = ctx.deepLinkPage;

check("CANARY: #p=tasks opens the Tasks page", page("#p=tasks") === "tasks", page("#p=tasks"));
check("every rail page id works", ids.every((id) => page("#p=" + id) === id));
check("a hidden page (coding) still works", page("#p=coding") === "coding");
check("old ids that moved still work (navigateTo sends them on)",
  page("#p=kanban") === "kanban" && page("#p=selfimprove") === "selfimprove" && page("#p=agents") === "agents");
check("ids are matched without regard to case", page("#p=Tasks") === "tasks");
check("an unknown page id is ignored quietly", page("#p=nope") === "" && page("#p=") === "");
check("CANARY: Object prototype keys are not pages",
  page("#p=constructor") === "" && page("#p=__proto__") === "" && page("#p=toString") === "");
check("not a #p= hash: nothing", page("#tasks") === "" && page("") === "" && page(null) === ""
  && page("#open=wiki%2Fa.md") === "" && page("#cs=agent:x") === "");
check("junk after the id is not a page", page("#p=tasks/x") === "" && page("#p=tasks?x=1") === "" && page("#p=tasks&b=1") === "");

// ============================================================
// 2. runDeepLink: one handler for load and hashchange
// ============================================================
const bootSrc = CONSOLE.slice(CONSOLE.indexOf("function boot()"));
const rdStart = bootSrc.indexOf("    let deepHashDone = null;");
const rdEnd = bootSrc.indexOf("\n    };\n", rdStart);
const rdSrc = rdStart < 0 || rdEnd < 0 ? "" : bootSrc.slice(rdStart, rdEnd + 7);
check("boot() defines runDeepLink", !!rdSrc);
check("CANARY: a hashchange listener runs it in an open tab",
  /window\.addEventListener\("hashchange", runDeepLink\);/.test(bootSrc));
check("the load read goes through the same handler, after settings",
  /freshSettings\(\)\.then\([\s\S]*?\n {6}runDeepLink\(\);\n {4}\}\);/.test(bootSrc));
check("the old one-off load read is gone (no second copy of the rules)",
  (bootSrc.match(/\/\^#open=\(\.\+\)\$\//g) || []).length === 1);

const calls = [];
const rctx = {
  location: { hash: "" },
  openVaultPath: (p) => calls.push("open:" + p),
  moCongSu: (s) => calls.push("cs:" + s),
  deepLinkPage: page,
  Alpine: { store: (n) => (n === "nav" ? { go: (id) => calls.push("go:" + id) } : null) },
};
vm.createContext(rctx);
vm.runInContext(rdSrc + "\nthis.runDeepLink = runDeepLink;", rctx);
const run = (hash) => { calls.length = 0; rctx.location.hash = hash; rctx.runDeepLink(); return calls.slice(); };

check("#p=tasks -> nav.go('tasks')", JSON.stringify(run("#p=tasks")) === '["go:tasks"]', calls);
check("#open= still opens through openVaultPath, decoded",
  JSON.stringify(run("#open=wiki%2Fa%20b.md")) === '["open:wiki/a b.md"]', calls);
check("#cs= still opens the partner chat, decoded",
  JSON.stringify(run("#cs=agent%3Aviet-bai")) === '["cs:agent:viet-bai"]', calls);
check("an unknown page does nothing", run("#p=nope").length === 0);
check("a plain heading anchor does nothing", run("#muc-2").length === 0);
check("a broken %-escape does nothing and does not throw", run("#open=%E0%A4%A").length === 0);
run("#p=mcp");
calls.length = 0; rctx.runDeepLink();
check("CANARY: the same hash is handled once (load read and a racing hashchange)", calls.length === 0, calls);
check("going back to an earlier hash handles it again",
  JSON.stringify(run("#p=tasks")) === '["go:tasks"]' && JSON.stringify(run("#p=mcp")) === '["go:mcp"]');
check("the handler never writes the hash itself (no loop with the #p= fallbacks)",
  !/location\.hash\s*=/.test(rdSrc) && !/history\.(push|replace)State/.test(rdSrc));

// ============================================================
// 3. The fallbacks of other modules now write a hash that works
// ============================================================
for (const [file, want] of [
  ["background-strip.js", 'location.hash = "#p=kanban"'],
  ["chat-viec.js", 'location.hash = "#p=" + trang'],
  ["composer-plus.js", 'location.hash = "#p=" + id'],
  ["teams.js", 'location.hash = "#p=mcp"'],
  ["github-connect.js", 'location.hash = "#p=mcp"'],
]) {
  const src = D(file);
  check(file + ": the nav-store fallback writes #p=", src.includes(want));
  check(file + ": no bare page hash left (#kanban, #mcp, \"#\" + id)",
    !/location\.hash = "#(?!p=)/.test(src));
}

console.log("");
if (fails.length) { console.log(fails.length + " FAILED: " + fails.join(", ")); process.exit(1); }
console.log("OK - test_deep_link_page: all pass");
