// Measure how long the dashboard takes to open, in a real browser (speed review 2026-11-23).
//
// Not a test: no pass/fail, never picked up by CI. Read-only against a running Javis.
//
//   node docs/dev/2026-11-ra-soat-toc-do/dashboard_load_bench.mjs                      # http://127.0.0.1:7777, 5 runs per case
//   JAVIS_URL=http://host:7777 RUNS=7 node docs/dev/2026-11-ra-soat-toc-do/dashboard_load_bench.mjs
//   JAVIS_BENCH_COOKIE=<value of the javis_session cookie> node docs/dev/2026-11-ra-soat-toc-do/dashboard_load_bench.mjs
//
// Without JAVIS_BENCH_COOKIE the page stops at the sign-in form, so "ready" means "the sign-in form can be typed in".
// The scripts and styles are the same either way (the page loads them before it knows who is looking); only the data
// requests after sign-in are missing. With the cookie, "ready" means "the chat box can be typed in".
//
// Playwright: `playwright-core` from node_modules, or point PLAYWRIGHT_CORE at its folder. CHROME_PATH picks the browser.
import { createRequire } from "node:module";
import fs from "node:fs";

const require = createRequire(import.meta.url);
const URL_ = process.env.JAVIS_URL || "http://127.0.0.1:7777";
const RUNS = Number(process.env.RUNS || 5);
const COOKIE = process.env.JAVIS_BENCH_COOKIE || "";
const OUT = process.env.OUT || "";

function loadPlaywright() {
  const tries = [process.env.PLAYWRIGHT_CORE, "playwright-core", "playwright"].filter(Boolean);
  for (const t of tries) { try { return require(t); } catch (e) { /* next */ } }
  throw new Error("playwright-core not found: npm i playwright-core, or set PLAYWRIGHT_CORE");
}

// Slow 4G as Lighthouse defines it: 1.6 Mbps down, 750 kbps up, 150 ms round trip.
const SLOW_4G = { offline: false, latency: 150, downloadThroughput: 1.6e6 / 8, uploadThroughput: 750e3 / 8 };
const CASES = [
  { name: "desktop, no throttle", viewport: { width: 1440, height: 900 }, net: null, cpu: 1 },
  { name: "desktop, slow 4G", viewport: { width: 1440, height: 900 }, net: SLOW_4G, cpu: 1 },
  { name: "phone 390px, slow 4G, CPU x4", viewport: { width: 390, height: 844 }, net: SLOW_4G, cpu: 4, mobile: true },
];

const med = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.floor((s.length - 1) / 2)] : NaN; };
const p95 = (a) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.min(s.length - 1, Math.ceil(0.95 * s.length) - 1)] : NaN; };

async function oneLoad(context, c) {
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Performance.enable");
  if (c.net) await cdp.send("Network.emulateNetworkConditions", c.net);
  if (c.cpu > 1) await cdp.send("Emulation.setCPUThrottlingRate", { rate: c.cpu });
  const reqs = new Map();
  cdp.on("Network.requestWillBeSent", (e) => reqs.set(e.requestId, { url: e.request.url, type: e.type, bytes: 0, cached: false, status: 0 }));
  cdp.on("Network.responseReceived", (e) => { const r = reqs.get(e.requestId); if (r) { r.status = e.response.status; r.cached = !!e.response.fromDiskCache; } });
  cdp.on("Network.requestServedFromCache", (e) => { const r = reqs.get(e.requestId); if (r) r.cached = true; });
  cdp.on("Network.loadingFinished", (e) => { const r = reqs.get(e.requestId); if (r) r.bytes = e.encodedDataLength; });
  await page.addInitScript(() => {
    window.__long = [];
    try { new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__long.push(e.duration); }).observe({ type: "longtask", buffered: true }); } catch (e) {}
  });
  const t0 = Date.now();
  await page.goto(URL_ + "/", { waitUntil: "commit", timeout: 120000 });
  const readySel = COOKIE ? "#chatInput" : "#authUser";
  // Ready = the box is on screen, not covered by the start-up screen, and takes focus.
  await page.waitForFunction((sel) => {
    const el = document.querySelector(sel);
    if (!el || el.disabled) return false;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return top === el || el.contains(top);
  }, readySel, { timeout: 120000, polling: 25 });
  const ready = Date.now() - t0;
  await page.waitForLoadState("load", { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(1500);   // let the idle-time loads (nap-cham.js) and late requests land
  const nav = await page.evaluate(() => {
    const n = performance.getEntriesByType("navigation")[0] || {};
    const fcp = (performance.getEntriesByType("paint").find((p) => p.name === "first-contentful-paint") || {}).startTime;
    return { ttfb: n.responseStart, dcl: n.domContentLoadedEventEnd, load: n.loadEventEnd, fcp: fcp || 0,
             long: window.__long || [] };
  });
  const pm = Object.fromEntries((await cdp.send("Performance.getMetrics")).metrics.map((m) => [m.name, m.value]));
  const all = [...reqs.values()].filter((r) => r.url.startsWith("http"));
  const net = all.filter((r) => !r.cached);
  await page.close();
  return {
    ready, ttfb: nav.ttfb, fcp: nav.fcp, dcl: nav.dcl, load: nav.load,
    requests: all.length, fromNetwork: net.length, kb: net.reduce((s, r) => s + r.bytes, 0) / 1024,
    scriptMs: pm.ScriptDuration * 1000, taskMs: pm.TaskDuration * 1000, layoutMs: (pm.LayoutDuration + pm.RecalcStyleDuration) * 1000,
    heapMb: pm.JSHeapUsedSize / 1048576,
    longTasks: nav.long.length, blockedMs: nav.long.reduce((s, d) => s + Math.max(0, d - 50), 0),
    list: all.map((r) => ({ url: r.url.replace(URL_, ""), type: r.type, kb: +(r.bytes / 1024).toFixed(1), cached: r.cached, status: r.status })),
  };
}

const { chromium } = loadPlaywright();
const browser = await chromium.launch({
  headless: true, executablePath: process.env.CHROME_PATH || undefined,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const report = { url: URL_, runs: RUNS, signedIn: !!COOKIE, at: new Date().toISOString(), cases: [] };
for (const c of CASES) {
  const cold = [], warm = [];
  for (let i = 0; i < RUNS; i++) {
    const context = await browser.newContext({ viewport: c.viewport, isMobile: !!c.mobile, hasTouch: !!c.mobile,
                                               deviceScaleFactor: c.mobile ? 3 : 1, serviceWorkers: "allow" });
    if (COOKIE) await context.addCookies([{ name: "javis_session", value: COOKIE, url: URL_ }]);
    cold.push(await oneLoad(context, c));    // empty cache
    warm.push(await oneLoad(context, c));    // same profile again: what a returning visit costs
    await context.close();
  }
  const sum = (rows) => {
    const o = {};
    for (const k of ["ready", "ttfb", "fcp", "dcl", "load", "requests", "fromNetwork", "kb", "scriptMs", "taskMs", "layoutMs", "heapMb", "longTasks", "blockedMs"]) {
      const v = rows.map((r) => r[k]);
      o[k] = { median: +med(v).toFixed(1), p95: +p95(v).toFixed(1) };
    }
    return o;
  };
  const entry = { name: c.name, cold: sum(cold), warm: sum(warm), coldRequests: cold[0].list, warmRequests: warm[0].list };
  report.cases.push(entry);
  for (const [label, s] of [["cold", entry.cold], ["warm", entry.warm]]) {
    console.log(`${c.name} | ${label} | ready ${s.ready.median} ms (p95 ${s.ready.p95}) | FCP ${s.fcp.median} | DCL ${s.dcl.median} | load ${s.load.median}`
      + ` | ${s.requests.median} requests, ${s.fromNetwork.median} from network, ${s.kb.median} KB`
      + ` | script ${s.scriptMs.median} ms, long tasks ${s.longTasks.median} (${s.blockedMs.median} ms over 50)`
      + ` | heap ${s.heapMb.median} MB`);
  }
}
await browser.close();
if (OUT) fs.writeFileSync(OUT, JSON.stringify(report, null, 1));
