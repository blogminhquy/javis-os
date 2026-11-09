// Markets page (markets.js): the pure chart helpers, the page wiring and its strings.
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const R = path.join(__dirname, "../..");
const read = (f) => fs.readFileSync(path.join(R, f), "utf8");
const src = read("dashboard/markets.js");
const cons = read("dashboard/console.js");
const uia = read("dashboard/ui-actions.js");
const tgt = read("server/ui_targets.py");
const html = read("dashboard/index.html");
const vi = JSON.parse(read("dashboard/i18n/vi.json"));
const en = JSON.parse(read("dashboard/i18n/en.json"));

let fails = 0;
function check(name, ok, detail) { console.log((ok ? "ok   " : "FAIL ") + name + (!ok && detail ? "  (" + detail + ")" : "")); if (!ok) fails++; }

const win = {};
const doc = { documentElement: { lang: "vi" }, addEventListener() {}, body: { contains() { return false; } } };
vm.runInNewContext(src, { window: win, document: doc, Intl, Math, JSON, String, Number, Array, Object, setTimeout, clearInterval, setInterval });
const M = win.JavisMarkets;
check("module exposes mount and unmount", M && typeof M.mount === "function" && typeof M.unmount === "function");
const H = M._test;

// squarify: tiles fill the box exactly, never overlap and keep the weight order.
const items = [9, 7, 5, 3, 2, 1, 1].map((w, i) => ({ w, r: { i } }));
const cells = H.squarify(items, 600, 300);
const area = cells.reduce((s, c) => s + c.w * c.h, 0);
check("treemap covers the whole box", Math.abs(area - 600 * 300) < 1e-6, area);
check("treemap keeps every item", cells.length === items.length);
check("treemap tiles stay inside the box", cells.every((c) => c.x >= -1e-9 && c.y >= -1e-9 && c.x + c.w <= 600 + 1e-6 && c.y + c.h <= 300 + 1e-6));
check("treemap area follows the weight", cells.every((c) => Math.abs(c.w * c.h / area - c.it.w / 28) < 1e-9));
let overlap = false;
for (let a = 0; a < cells.length; a++) for (let b = a + 1; b < cells.length; b++) {
  const p = cells[a], q = cells[b];
  if (p.x + 1e-6 < q.x + q.w && q.x + 1e-6 < p.x + p.w && p.y + 1e-6 < q.y + q.h && q.y + 1e-6 < p.y + p.h) overlap = true;
}
check("treemap tiles never overlap", !overlap);
check("empty treemap", H.squarify([], 100, 100).length === 0);

const ticks = H.niceTicks(1693, 1781, 5);
check("axis ticks are round and inside the range", ticks.length >= 3 && ticks.every((v) => v >= 1693 && v <= 1781 && v % 10 === 0), ticks.join(","));
check("signal bands", ["strong_pos", "pos", "neutral", "neg", "strong_neg"].join() === [60, 25, 0, -25, -60].map(H.sigOf).join());
check("fear and greed bands", [10, 30, 50, 70, 90].map(H.fngKey).join() === "xfear,fear,neutral,greed,xgreed");
check("percent keeps its sign", H.pct(1.5).indexOf("+") === 0 && H.pct(-2).indexOf("-") === 0);
check("direction", H.dir(1) === "up" && H.dir(-1) === "down" && H.dir(0) === "flat" && H.dir(null) === "flat");

// wiring
check("page in the Research group", /id: "nghien_cuu"[^\n]*ids: \["markets"/.test(cons));
check("page icon, meta, lazy group and renderer",
  /markets: "chart-candlestick"/.test(cons) && /"usage", "markets"/.test(cons) && /markets: \["markets"\]/.test(cons) &&
  /id === "markets"[\s\S]{0,600}JavisMarkets\.mount\(el\)/.test(cons));
check("voice commands know the page", /"markets"/.test(uia) && /"markets"/.test(tgt) && /"thi truong": "markets"/.test(tgt));
check("lazy block loads the page files", /"markets": \[\s*"\/static\/markets\.css\?v=\d+",\s*"\/static\/markets\.js\?v=\d+"/.test(html));

// strings: every static key the page uses exists in both languages, with no long dashes
const keys = new Set();
for (const m of src.matchAll(/T\("(mk\.[a-z0-9_.]+)"/g)) if (!/[._]$/.test(m[1])) keys.add(m[1]);
for (const m of src.matchAll(/"(mk\.col\.[a-z0-9_]+)"/g)) keys.add(m[1]);
for (const p of ["mk.tab.", "mk.sig.", "mk.regime.", "mk.fng_l.", "mk.vix.", "mk.voltrend.", "mk.volreg.", "mk.list.", "mk.range.",
  "mk.mode.", "mk.add_ph.", "mk.quad.", "mk.group.", "mk.region.", "mk.sector.", "mk.reason."]) {
  check("dynamic keys exist: " + p, Object.keys(vi).some((k) => k.indexOf(p) === 0));
}
["page.markets.label", "page.markets.sub", "nav.group.nghien_cuu"].forEach((k) => keys.add(k));
const missing = [...keys].filter((k) => !vi[k] || !en[k]);
check("every key in both languages", missing.length === 0, missing.join(", "));
const mk = Object.keys(vi).filter((k) => k.indexOf("mk.") === 0 || k.indexOf("page.markets") === 0);
check("no long dashes in the page strings", mk.every((k) => !/[\u2013\u2014]/.test(vi[k] + en[k])));
check("same placeholders in both languages", mk.every((k) => {
  const a = (vi[k].match(/\{[a-z0-9_]+\}/g) || []).sort().join(), b = (en[k].match(/\{[a-z0-9_]+\}/g) || []).sort().join();
  return a === b;
}));
check("no Vietnamese text in the code", !/[àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]/i.test(src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "")));

if (fails) { console.log("\n" + fails + " FAIL"); process.exit(1); }
console.log("\nall ok");
