/* Performance phase 3 (0.418.0): the service worker's fallback when the server cannot be reached.

       node tests/js/test_hieu_nang_gd3.js

   sw.js still caches NOTHING in the normal case (the reason is written at its top: a caching worker serves old code
   after every update). One narrow exception: opening "/" and the i18n dictionaries always ask the server first and
   take its answer; only when the server cannot be reached (network error, 502, 503, 504, 520-530) the last good copy
   is served, so the owner sees Javis with the "Reconnecting" pill instead of an error page. freshness.js then asks
   for the version right away and reloads a stale shell once the server is back. The pet's CSS rest has its own test
   (test_pet_nghi_yen.js). */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const read = rel => fs.readFileSync(path.join(ROOT, rel), "utf8");

const sw = read("dashboard/sw.js");
check("push and notification click are still there", /addEventListener\("push"/.test(sw) && /addEventListener\("notificationclick"/.test(sw));

// Run sw.js in a fake worker: a cache store, a network we control.
function worker(net) {
  const store = {};
  const handlers = {};
  const self = {
    location: { origin: "https://javis.example" },
    addEventListener: (n, fn) => { handlers[n] = fn; },
    skipWaiting() {}, clients: { claim: async () => {} },
    registration: {},
  };
  const caches = {
    open: async () => ({ put: async (k, r) => { store[k] = r; } }),
    match: async (k) => store[k],
    keys: async () => [], delete: async () => true,
  };
  const ctx = vm.createContext({ self, caches, fetch: net, URL, Promise, console });
  vm.runInContext(sw, ctx);
  async function go(url, mode) {
    let reply = "untouched";
    const req = { url, method: "GET", mode: mode || "cors" };
    handlers.fetch({ request: req, respondWith: (p) => { reply = p; } });
    return reply === "untouched" ? reply : await reply;
  }
  return { go, store };
}
const ok = (body) => ({ ok: true, status: 200, redirected: false, body, clone() { return this; } });
const bad = (status) => ({ ok: false, status, redirected: false, clone() { return this; } });

(async () => {
  let online = true, status = 200;
  const net = async (req) => { if (!online) throw new TypeError("Failed to fetch"); return status === 200 ? ok("fresh " + req.url) : bad(status); };
  const W = worker(net);
  const O = "https://javis.example";

  check("an API call is not touched by the worker", (await W.go(O + "/settings")) === "untouched");
  check("a static script is not touched either", (await W.go(O + "/static/app.js?v=1")) === "untouched");
  check("another site is not touched", (await W.go("https://cdn.example/x.js")) === "untouched");

  const r1 = await W.go(O + "/", "navigate");
  check("opening / with the server up: the server's page, and a copy is kept", r1.body === "fresh " + O + "/" && !!W.store[O + "/"]);
  await W.go(O + "/static/i18n/vi.json");
  check("the dictionary is kept too", !!W.store[O + "/static/i18n/vi.json"]);

  online = false;
  const r2 = await W.go(O + "/", "navigate");
  check("server unreachable (network error): the kept page", r2.body === "fresh " + O + "/");
  online = true; status = 502;
  const r3 = await W.go(O + "/static/i18n/vi.json");
  check("server answers 502: the kept dictionary", r3 && r3.body === "fresh " + O + "/static/i18n/vi.json");
  status = 500;
  const r4 = await W.go(O + "/", "navigate");
  check("a 500 is a real answer, passed through (not hidden behind an old copy)", r4.status === 500);
  status = 200;
  const r5 = await W.go(O + "/?x=1", "navigate");
  check("server back: fresh again", r5.body === "fresh " + O + "/?x=1");

  const fr = read("dashboard/freshness.js");
  check("freshness.js asks for the version soon after opening, retrying until the server answers",
    /function kiemSom\(lan\)/.test(fr) && /setTimeout\(function \(\) \{ kiemSom\(0\); \}, 2500\);/.test(fr) && /if \(lan < 24\)/.test(fr));
  check("a stale shell reloads by itself only on a fresh page with an empty chat box, at most once per 30 s",
    /Date\.now\(\) - batDau < 120000 && !\(o && o\.value\.trim\(\)\) && Date\.now\(\) - luc > 30000/.test(fr));
  check("the worker is registered for everyone in a secure context (it used to be only with push on)",
    /"serviceWorker" in navigator && window\.isSecureContext/.test(fr) && /register\("\/sw\.js", \{ scope: "\/" \}\)/.test(fr));

  if (fails.length) { console.log("\nFAIL - test_hieu_nang_gd3: " + fails.length); process.exit(1); }
  console.log("\nOK - test_hieu_nang_gd3: all pass");
})();
