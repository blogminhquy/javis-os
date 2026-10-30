/* Performance phase 2 (0.417.0): page code loads on demand, page CSS travels with it, reads retry while the server
   is unreachable.

       node tests/js/test_hieu_nang_gd2.js

   Measured 30/10/2026: 72% of the JS the dashboard loaded at boot never ran (other pages' code). The large modules that
   only one page uses now live in <script id="javis-lazy"> and load through nap-cham.js; renderPage waits for a page's
   group before drawing it, cross-page calls wait for the group they need, and the rest loads in the background once
   the page is idle. Separately, a page opened while the server was restarting got 502 pages for every read and broke
   (customer report): GET reads to the server now retry for ~10 s with a "Reconnecting" pill. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const read = rel => fs.readFileSync(path.join(ROOT, rel), "utf8");

const html = read("dashboard/index.html");
const lazy = JSON.parse((html.match(/<script id="javis-lazy" type="application\/json">([\s\S]*?)<\/script>/) || [])[1] || "{}");
const all = Object.values(lazy).flat();
check("the lazy groups exist", ["congviec", "teams", "packs", "hoithoai", "usage", "webhooks"].every(g => Array.isArray(lazy[g]) && lazy[g].length));
check("every lazy URL carries ?v= so the server keys it like any other file", all.every(u => /^\/static\/[\w./-]+\.(js|css)\?v=[\w.]+$/.test(u)));
check("every lazy file exists", all.every(u => fs.existsSync(path.join(ROOT, "dashboard", u.slice(8).split("?")[0]))));
check("no lazy file is also loaded eagerly", all.every(u => {
  const f = u.split("?")[0];
  return !new RegExp('<script src="' + f.replace(/[.]/g, "\\.") + '\\?').test(html) && !new RegExp('<link rel="stylesheet" href="' + f.replace(/[.]/g, "\\.") + '\\?').test(html);
}));
check("files that wire things at load stay eager (studio.js binds the Studio button, openStudio is used by app.js)",
  /<script src="\/static\/studio\.js\?v=/.test(html) && !all.some(u => /studio\.js/.test(u)));
check("the conversations CSS loads before its JS in the same group",
  lazy.hoithoai[0].indexOf("inbox-v5.css") > 0 && lazy.hoithoai[1].indexOf("inbox-compact.css") > 0);
check("the shared pulse parts load before teams.js (teams needs JavisAgentJudge)", lazy.congviec.some(u => /agent-judge-ui/.test(u)));
check("nap-cham.js loads early, before console.js", html.indexOf("/static/nap-cham.js") > 0 && html.indexOf("/static/nap-cham.js") < html.indexOf("/static/console.js"));

const con = read("dashboard/console.js");
const map = (con.match(/const NHOM_TRANG = \{([\s\S]*?)\};/) || [])[1] || "";
check("every page that needs lazy code is mapped in NHOM_TRANG",
  /workspace: \["congviec"\]/.test(map) && /teams: \["congviec", "teams"\]/.test(map) && /conversations: \["hoithoai"\]/.test(map)
  && /chatbots: \["hoithoai"\]/.test(map) && /packs: \["packs"\]/.test(map) && /plugins: \["packs"\]/.test(map) && /mcp: \["packs"\]/.test(map)
  && /usage: \["usage"\]/.test(map) && /webhooks: \["webhooks"\]/.test(map));
check("renderPage waits for the page's group, and stops if the user moved on meanwhile",
  /await window\.JavisNapCham\.cho\(nhomCan\);\n\s+if \(gen !== _renderGen\) return;/.test(con));
check("the Settings usage tab waits for usage.js itself", /if \(!window\.JavisUsage && window\.JavisNapCham\) await window\.JavisNapCham\.cho\("usage"\);/.test(con));
check("the zip plugin button is not deferred (the file picker only opens inside the click)",
  /zip\.onclick = \(\) => \{\n\s+if \(!window\.JavisPacks/.test(con));
check("a notice for a team chat loads teams.js and opens it, instead of falling back to the main chat",
  /window\.JavisNapCham\.goi\(\["congviec", "teams"\]/.test(read("dashboard/notifications.js")));
const ws = read("dashboard/workspace.js");
check("workspace opens a team and the Store through the loader", /openTeam: function \(teamId, taskId\) \{[\s\S]{0,200}nhom\(\["congviec", "teams"\]/.test(ws)
  && (ws.match(/nhom\("packs", function/g) || []).length === 2);

// ───────── nap-cham.js behaviour ─────────
async function loader() {
  const appended = [];
  const doc = {
    readyState: "complete",
    getElementById: () => ({ textContent: JSON.stringify({ a: ["/static/x.css?v=1", "/static/x.js?v=1", "/static/y.js?v=1"], b: ["/static/z.js?v=1"] }) }),
    createElement: tag => ({ tag }),
    head: { appendChild: el => { appended.push(el.href || el.src); setTimeout(() => el.onload && el.onload(), 1); } },
    body: { appendChild: el => { appended.push(el.href || el.src); setTimeout(() => el.onload && el.onload(), 1); } },
  };
  const win = { addEventListener() {}, requestIdleCallback: null };
  const ctx = vm.createContext({ window: win, document: doc, setTimeout, Promise, JSON, Array });
  vm.runInContext(read("dashboard/nap-cham.js"), ctx);
  const N = win.JavisNapCham;
  let ran = false;
  const sync = N.goi("nothing-to-load", () => { ran = true; });
  check("goi() on a group with nothing to load calls at once, inside the click", ran);
  await N.cho("a");
  check("a group loads its CSS first, then its JS, in order", appended.slice(0, 3).join(",") === "/static/x.css?v=1,/static/x.js?v=1,/static/y.js?v=1");
  check("a loaded group is marked done", N.daXong("a") && !N.daXong("b"));
  ran = false; N.goi("a", () => { ran = true; });
  check("goi() on a loaded group calls synchronously", ran);
  await N.cho("a");
  check("loading a group twice fetches nothing again", appended.length === 3);
  await N.cho(["a", "b"]);
  check("several groups at once", appended.length === 4 && N.daXong(["a", "b"]));
  await sync;
}

// ───────── retry (fetch-gop.js) ─────────
const G = require(path.join(ROOT, "dashboard/fetch-gop.js"));
const O = "http://127.0.0.1:7777";
check("502, 503, 504 and Cloudflare 520-530 mean 'server not reachable yet'", [502, 503, 504, 520, 530].every(G.maTam) && ![500, 404, 401, 200].some(G.maTam));
check("a GET to the server retries", G.thuLaiDuoc("/sessions?brain=a", undefined, O));
check("a write never retries", !G.thuLaiDuoc("/settings", { method: "POST", body: "x" }, O));
check("static files, streams, no-store and own-signal calls are left alone",
  !G.thuLaiDuoc("/static/app.js", undefined, O) && !G.thuLaiDuoc("/chat/stream", undefined, O)
  && !G.thuLaiDuoc("/update/status", { cache: "no-store" }, O) && !G.thuLaiDuoc("/x", { signal: {} }, O));
check("waits add up to about ten seconds", G.CHO_THU_LAI.reduce((a, b) => a + b, 0) === 10500);

async function retry() {
  let n = 0;
  const answers = [502, 530, 200];
  const win = { fetch: () => { const s = answers[Math.min(n++, answers.length - 1)]; return Promise.resolve(new Response("{}", { status: s })); } };
  win.window = win;
  const body = { children: [], appendChild(e) { e.isConnected = true; this.children.push(e); } };
  const doc = { body, createElement: () => ({ style: {}, setAttribute() {}, remove() { this.isConnected = false; } }) };
  // Waits run instantly here: the schedule itself is pinned above (CHO_THU_LAI), the behaviour is what is tested.
  const fast = (fn) => setTimeout(fn, 0);
  const ctx = vm.createContext({ window: win, document: doc, location: { origin: O }, URL, Response, Promise, Date, setTimeout: fast, String, JSON });
  vm.runInContext(read("dashboard/fetch-gop.js"), ctx);
  const r = await win.fetch("/sessions?brain=a");
  check("two 'not reachable' answers, then the real one: the caller only sees the real one", r.status === 200 && n === 3);
  check("the Reconnecting pill showed while retrying and is gone after", body.children.length === 1 && body.children[0].isConnected === false);
  n = 0; answers.splice(0, 3, 502, 502, 502, 502, 502, 502, 502);
  const p = await win.fetch("/brains?x=1");
  check("still failing after the last wait: the caller gets the 502 (its own error path runs)", p.status === 502 && n === 6);
  const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));
  check("net.reconnecting in vi and en", !!(vi["net.reconnecting"] && en["net.reconnecting"]));
}

loader().then(retry).then(() => {
  if (fails.length) { console.log("\nFAIL - test_hieu_nang_gd2: " + fails.length); process.exit(1); }
  console.log("\nOK - test_hieu_nang_gd2: all pass");
  process.exit(0);
});
