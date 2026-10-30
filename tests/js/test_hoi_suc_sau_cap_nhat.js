/* A page opened while the server is still restarting recovers by itself (0.415.0).

       node tests/js/test_hoi_suc_sau_cap_nhat.js

   Customer report 2026-10-30 (iPhone): pressing update reloaded the page while the server (or the Cloudflare tunnel
   in front of it) was still coming up. vi.json, /version and /settings all got an HTML error page, so the whole
   screen showed raw keys (`nav.group.bo_nao`), the version stuck at the fallback v0.4.3, Safari printed "The string
   did not match the expected pattern", and nothing ever retried. Pinned here:
   - i18n/index.js retries the base dictionary and, once it arrives, reloads a freshly opened page with an empty chat
     box, or only redraws the words when the owner is typing;
   - the update flow reloads only after the server answers JSON twice in a row (freshness.js);
   - the idle loops measured in the same audit stay light. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }
const wait = ms => new Promise(r => setTimeout(r, ms));
const read = rel => fs.readFileSync(path.join(ROOT, rel), "utf8");

// Runs dashboard/i18n/index.js in a fake page whose server is down for the first `downCalls` dictionary requests.
function page({ downCalls, typed }) {
  let calls = 0;
  const env = { reloads: 0, events: 0, session: {} };
  const win = {
    addEventListener() {}, dispatchEvent() { env.events++; },
    setTimeout, clearTimeout, Promise, Object, JSON, Math, Date, String, Number,
  };
  win.window = win;
  win.CustomEvent = function (n, o) { this.type = n; this.detail = o && o.detail; };
  win.fetch = (url) => {
    calls++;
    if (/\/i18n\/vi\.json$/.test(url) && calls <= downCalls) {
      // What the customer's phone got: a proxy error page, not JSON.
      return Promise.resolve({ ok: true, json: () => Promise.reject(new SyntaxError("The string did not match the expected pattern.")) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(/vi\.json$/.test(url) ? { "nav.group.bo_nao": "Bộ não" } : { "nav.group.bo_nao": "Brain" }) });
  };
  win.localStorage = { getItem: () => "vi", setItem() {} };
  win.sessionStorage = { getItem: k => env.session[k] || null, setItem: (k, v) => { env.session[k] = v; } };
  win.navigator = { languages: ["vi-VN"] };
  win.location = { reload() { env.reloads++; } };
  win.document = {
    documentElement: { setAttribute() {} },
    cookie: "",
    querySelectorAll: () => [],
    getElementById: id => (id === "chatInput" ? { value: typed || "" } : null),
  };
  vm.createContext(win);
  vm.runInContext(read("dashboard/i18n/index.js"), win);
  env.t = k => win.t(k);
  env.calls = () => calls;
  return env;
}

(async () => {
  // 1. Fresh page, server back after the first try: the page reloads once.
  let p = page({ downCalls: 1 });
  await wait(50);
  check("server down at boot: the screen shows raw keys at first", p.t("nav.group.bo_nao") === "nav.group.bo_nao");
  await wait(1300);
  check("the dictionary is fetched again after a second", p.calls() >= 2);
  check("a freshly opened page with an empty chat box reloads once the server is back", p.reloads === 1);

  // 2. Same, but the owner is typing: no reload, the words come back in place.
  p = page({ downCalls: 1, typed: "đang gõ dở" });
  await wait(1400);
  check("typing: the page is not reloaded under the owner's fingers", p.reloads === 0);
  check("typing: the words are redrawn from the recovered dictionary", p.t("nav.group.bo_nao") === "Bộ não");

  // 3. A reload just happened (sessionStorage mark): never a reload loop.
  p = page({ downCalls: 1 });
  p.session["javis.i18n_reload_at"] = String(Date.now());
  await wait(1400);
  check("a second automatic reload within 30 seconds is refused", p.reloads === 0 && p.t("nav.group.bo_nao") === "Bộ não");

  // 4. Healthy boot: no retry, no reload.
  p = page({ downCalls: 0 });
  await wait(1200);
  check("healthy boot: one request, no reload", p.calls() === 1 && p.reloads === 0 && p.t("nav.group.bo_nao") === "Bộ não");

  // ───────── the update flow waits for a ready server ─────────
  const fresh = read("dashboard/freshness.js");
  check("freshness.js offers JavisReloadWhenReady", /window\.JavisReloadWhenReady = choSanRoiTaiLai;/.test(fresh));
  check("it needs /app-version and vi.json as JSON twice in a row, 90 seconds at most",
    /json\("\/app-version"\), json\("\/static\/i18n\/vi\.json"\)/.test(fresh) && /dat >= 2 \|\| Date\.now\(\) - batDau > 90000/.test(fresh));
  check("a version change seen while updating goes through it", /if \(window\.__javisUpdating\) \{ choSanRoiTaiLai\(\); return; \}/.test(fresh));
  const consoleJs = read("dashboard/console.js");
  check("every update success in console.js reloads through it",
    (consoleJs.match(/setTimeout\(_taiLaiKhiSan, 1500\)/g) || []).length === 4 && !/setTimeout\(\(\) => location\.reload\(\), 1500\)/.test(consoleJs));
  check("the rail version falls back to the always fresh javis-fresh block, not v0.4.3",
    /JSON\.parse\(document\.getElementById\("javis-fresh"\)\.textContent\)\.version \|\| APP_VERSION/.test(consoleJs));

  // ───────── lighter idle loops ─────────
  check("freshness.js hashes each asset set once per device",
    /if \(daDo\(\)\) return;/.test(fresh) && /ghiDaDo\(!ds\.length\);/.test(fresh));
  const pet = read("dashboard/pet.js");
  check("pet draws 30 frames a second when idle, 15 asleep",
    /var khoang = nguGat \? 66 : \(state === "idle" && now - chuotLuc > 1600 && gatLuc <= now \? 33 : 0\);/.test(pet));
  const app = read("dashboard/app.js");
  check("the starfield skips frames behind a management page",
    /if \(document\.hidden\) return;\n[\s\S]{0,400}if \(document\.body\.classList\.contains\("in-console"\)\) return;/.test(app));
  check("the brain graph is paused right after it is built when the app opens on another page",
    /await reloadGraph\(\);\n[\s\S]{0,300}window\.JavisRecomputeGraph\(\)/.test(app) && /window\.JavisRecomputeGraph = recomputeGraph;/.test(consoleJs));

  if (fails.length) { console.log("\nFAIL - test_hoi_suc_sau_cap_nhat: " + fails.length); process.exit(1); }
  console.log("\nOK - test_hoi_suc_sau_cap_nhat: all pass");
  process.exit(0);
})();
