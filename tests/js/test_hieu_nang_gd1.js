/* Performance phase 1 (0.416.0): self-hosted fonts, coalesced boot reads, the client error black box.

       node tests/js/test_hieu_nang_gd1.js

   Measured 30/10/2026 on the boot of the dashboard: /settings was asked 9 times, /agents /skills /workflows twice each;
   the page reached fonts.googleapis.com and fonts.gstatic.com before it could draw text; and interface errors only
   lived in the browser of whoever hit them (a customer's screenshot was the only report). The minifier has its own
   test (test_tinh_gon.mjs). */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const read = rel => fs.readFileSync(path.join(ROOT, rel), "utf8");
const tick = () => new Promise(r => setTimeout(r, 0));

// ───────── fonts ─────────
const html = read("dashboard/index.html");
check("index.html no longer reaches Google Fonts", !/fonts\.googleapis\.com\/css|href="https:\/\/fonts\.g/.test(html));
check("index.html loads the self-hosted font sheet", /<link rel="stylesheet" href="\/static\/fonts\/fonts\.css\?v=\d+">/.test(html));
const fontsCss = read("dashboard/fonts/fonts.css");
const urls = [...fontsCss.matchAll(/url\(([^)]+)\)/g)].map(m => m[1].split("?")[0]);
check("every font file the sheet names exists", urls.length >= 12 && urls.every(u => fs.existsSync(path.join(ROOT, "dashboard/fonts", u))));
check("font URLs carry ?v= so they are cached for a year", /url\([^)]+\.woff2\?v=\d+\)/.test(fontsCss) && !/url\([^)?]+\.woff2\)/.test(fontsCss));
check("Be Vietnam Pro and Montserrat, Vietnamese subset included",
  /font-family: 'Be Vietnam Pro'/.test(fontsCss) && /font-family: 'Montserrat'/.test(fontsCss) && /vietnamese\.woff2/.test(fontsCss));
check("the OFL licence ships with the fonts", /SIL Open Font License/.test(read("dashboard/fonts/OFL.txt")));

// ───────── coalesced reads (fetch-gop.js) ─────────
const G = require(path.join(ROOT, "dashboard/fetch-gop.js"));
const O = "http://127.0.0.1:7777";
check("GET /settings is coalesced", G.gopDuoc("/settings", undefined, O) && G.gopDuoc("/agents?brain=b", { method: "GET" }, O));
check("a write is never coalesced", !G.gopDuoc("/settings", { method: "POST", body: "x" }, O));
check("a call with its own AbortController is not coalesced (one abort would kill the other)",
  !G.gopDuoc("/settings", { signal: {} }, O));
check("cache: no-store asks for the newest answer: not coalesced", !G.gopDuoc("/connect/health", { cache: "no-store" }, O));
check("paths outside the list are left alone (streams, files)", !G.gopDuoc("/chat/stream", undefined, O) && !G.gopDuoc("/files/raw?p=a", undefined, O));
check("another origin is left alone", !G.gopDuoc("https://example.com/settings", undefined, O));

async function wrapper() {
  let calls = 0;
  const win = {
    fetch: (u, init) => { calls++; const body = JSON.stringify({ u, n: calls }); return Promise.resolve(new Response(body, { status: u.indexOf("bad") >= 0 ? 500 : 200 })); },
  };
  win.window = win;
  const ctx = vm.createContext({ window: win, location: { origin: O }, URL, Response, Promise, Date, setTimeout, String, JSON, module: undefined });
  vm.runInContext(read("dashboard/fetch-gop.js"), ctx);
  const f = win.fetch;
  const a = f("/settings"), b = f("/settings");
  const [ra, rb] = await Promise.all([a, b]);
  const [ja, jb] = await Promise.all([ra.json(), rb.json()]);
  check("two reads of /settings at once: one request, both callers can read the body", calls === 1 && ja.n === 1 && jb.n === 1);
  await f("/settings");
  check("a third read inside 1.5 s still reuses it", calls === 1);
  await f("/settings", { method: "POST", body: "x" });
  const after = await (await f("/settings")).json();
  check("after a write, the next read asks the server again (never stale after saving)", calls === 3 && after.n === 3);
  await f("/agents?brain=bad"); await tick();
  await f("/agents?brain=bad");
  check("a failed answer is not reused", calls === 5);
}

// ───────── black box (loi-may-khach.js) ─────────
const L = require(path.join(ROOT, "dashboard/loi-may-khach.js"));
check("an error from a Javis file is reported", L.nenGui("x is not defined", O + "/static/app.js?v=1", O));
check("an error with no file (promise) is reported", L.nenGui("Load failed", "", O));
check("browser extensions and other sites are ignored",
  !L.nenGui("boom", "chrome-extension://abc/x.js", O) && !L.nenGui("boom", "https://ads.example.com/x.js", O));
check("well-known noise is ignored", !L.nenGui("Script error.", "", O) && !L.nenGui("ResizeObserver loop limit exceeded", "", O));
check("at most 20 errors per page load", L.TOI_DA === 20);
const lmk = read("dashboard/loi-may-khach.js");
check("it posts to /client-errors with keepalive", /fetch\("\/client-errors", \{[\s\S]{0,200}keepalive: true/.test(lmk));
check("a failed image or script load is not reported as a code error", /e\.target && e\.target !== window/.test(lmk));
check("the black box loads before the code it watches, the coalescer before any request",
  html.indexOf("/static/loi-may-khach.js") > 0 && html.indexOf("/static/loi-may-khach.js") < html.indexOf("/static/fetch-gop.js")
  && html.indexOf("/static/fetch-gop.js") < html.indexOf("/static/i18n/index.js"));

const HP = require(path.join(ROOT, "dashboard/health-panel.js"));
const row = HP.clientErrorHtml({ msg: "x <b>is</b> not defined", src: "/static/app.js", dong: 42, count: 3, last_at: 1, version: "0.416.0",
  ua: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile Safari/604.1" });
check("the Health page shows message, file:line, count, version and device, escaped",
  /x &lt;b&gt;is&lt;\/b&gt; not defined/.test(row) && /app\.js:42/.test(row) && /0\.416\.0/.test(row) && /iPhone Safari/.test(row));
const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));
["hp.cerr_head", "hp.cerr_none", "hp.cerr_clear", "hp.cerr_intro"].forEach(k => check("key " + k + " in vi and en", !!(vi[k] && en[k])));

wrapper().then(() => {
  if (fails.length) { console.log("\nFAIL - test_hieu_nang_gd1: " + fails.length); process.exit(1); }
  console.log("\nOK - test_hieu_nang_gd1: all pass");
});
