/* Real-estate page (realestate.js + realestate/data.json): Da Nang, Ho Chi Minh City, Dong Nai.

       node tests/js/test_realestate_page.js

   Checks the growth maths, that the page draws every section from the data, that the data file keeps its shape
   (three regions, the five look-back spans, every text in Vietnamese and English, real source links, no long dashes),
   and that the page is wired like the other lazy pages. */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const RE = require(path.join(ROOT, "dashboard/realestate.js"));

// ---------- maths ----------
const pts = [[2006, null], [2010, 20], [2016, 40], [2021, 60], [2024, 55], [2026, 80]];
const c10 = RE._spanChange(pts, 10, 2026);
check("10-year change uses the first year with data inside the window", c10 && c10.fromYear === 2016 && c10.toYear === 2026);
check("total change and yearly growth are right", c10 && Math.abs(c10.total - 100) < 1e-9 && Math.abs(c10.cagr - (Math.pow(2, 1 / 10) - 1) * 100) < 1e-9);
const c20 = RE._spanChange(pts, 20, 2026);
check("a series that starts late is marked partial over 20 years", c20 && c20.fromYear === 2010 && c20.partial === true);
check("no change when only one point is inside the window", RE._spanChange([[2025, null], [2026, 10]], 2, 2026) === null);
check("pick falls back to English, then Vietnamese", RE._pick({ vi: "a", en: "b" }, "de") === "b" && RE._pick({ vi: "a" }, "en") === "a" && RE._pick("x") === "x");

// ---------- chart ----------
const ch = RE._chartSvg([{ key: "apartment", slot: 1, name: "A", points: [[2006, 10], [2007, null], [2008, 30], [2026, 50]] }], { width: 600, band: [2016, 2026] });
const d = (ch.svg.match(/class="re-line re-s1" d="([^"]+)"/) || [])[1] || "";
check("a gap in the data stays a gap (two path pieces)", (d.match(/M/g) || []).length === 2);
check("the chart shades the chosen span and carries a hover layer", /class="re-band"/.test(ch.svg) && /class="re-hit"/.test(ch.svg));
check("one y axis only", (ch.svg.match(/text-anchor="end"/g) || []).length === 5);

// ---------- the data file ----------
let data = null;
try { data = JSON.parse(read("dashboard/realestate/data.json")); } catch (e) { data = null; }
check("data.json parses", !!data);
const regs = (data && data.regions) || [];
check("three regions: Da Nang, Ho Chi Minh City, Dong Nai", ["danang", "hcm", "dongnai"].every((id) => regs.some((r) => r.id === id)));
const bilingual = (v) => v && typeof v === "object" && typeof v.vi === "string" && v.vi.trim() && typeof v.en === "string" && v.en.trim();
let badText = [];
function walk(o, where) {
  if (Array.isArray(o)) return o.forEach((x, i) => walk(x, where + "[" + i + "]"));
  if (o && typeof o === "object") {
    if ("vi" in o || "en" in o) { if (!bilingual(o)) badText.push(where); return; }
    Object.keys(o).forEach((k) => walk(o[k], where + "." + k));
  }
}
regs.forEach((r) => {
  check(r.id + ": as_of, tagline, summary", !!r.as_of && bilingual(r.tagline) && bilingual(r.summary));
  check(r.id + ": at least 4 KPIs", (r.kpis || []).length >= 4);
  check(r.id + ": exactly the five spans 20/15/10/5/2", JSON.stringify((r.periods || []).map((p) => +p.span).sort((a, b) => b - a)) === "[20,15,10,5,2]");
  const series = ((r.price_series || {}).series) || [];
  check(r.id + ": a price series reaching 2025 or 2026", series.some((s) => (s.points || []).some((p) => p[0] >= 2025 && p[1] != null)));
  check(r.id + ": points are [year, number|null]", series.every((s) => (s.points || []).every((p) => Number.isInteger(p[0]) && (p[1] === null || typeof p[1] === "number"))));
  check(r.id + ": at most 3 series per chart (palette cap)", series.length <= 3);
  check(r.id + ": sub-areas scored 1-5", (r.subareas || []).length >= 5 && r.subareas.every((a) => a.potential >= 1 && a.potential <= 5 && a.risk >= 1 && a.risk <= 5));
  check(r.id + ": three forecast scenarios", ((r.forecast || {}).scenarios || []).length === 3);
  check(r.id + ": real source links", (r.sources || []).length >= 4 && r.sources.every((s) => /^https?:\/\//.test(s.url || "")));
  walk(r, r.id);
});
check("every text is in Vietnamese and English", badText.length === 0 || (console.log("   " + badText.slice(0, 8).join("\n   ")), false));
check("no long dashes in the data (owner rule)", !/[–—]/.test(read("dashboard/realestate/data.json")));

// ---------- the page draws from the data ----------
global.window = undefined;
if (data) {
  const hcm = RE._pageHtml(data, { region: "hcm", span: 10, sort: "potential", cmpKey: "" });
  check("region view: KPIs, chart, periods, forecast, areas, sources", ["re-kpis", 'data-chart="region"', 'data-span="20"', "re-scen", "re-areas", "re-sources"].every((s) => hcm.includes(s)));
  const cmp = RE._pageHtml(data, { region: "compare", span: 10, sort: "potential", cmpKey: "" });
  check("compare view: shared chart, growth table, three columns", cmp.includes('data-chart="compare"') && cmp.includes("re-tbl-num") && (cmp.match(/class="re-cmpcol"/g) || []).length === 3);
  check("compare prefers the apartment series", RE._compareKeys(regs)[0] === "apartment" || !regs.every((r) => r.price_series.series.some((s) => s.key === "apartment")));
}
check("page text is escaped", !RE._pageHtml({ regions: [{ id: "x", name: { vi: "<b>", en: "<b>" }, tagline: { vi: "<script>", en: "" } }] }, { region: "x", span: 10 }).includes("<script>"));

// ---------- wiring ----------
const con = read("dashboard/console.js");
const html = read("dashboard/index.html");
const lazy = JSON.parse((html.match(/<script id="javis-lazy" type="application\/json">([\s\S]*?)<\/script>/) || [])[1] || "{}");
check("lazy group batdongsan loads the CSS then the JS", JSON.stringify(lazy.batdongsan || []).indexOf("realestate.css") < JSON.stringify(lazy.batdongsan || []).indexOf("realestate.js"));
check("console.js maps the page to its group, icon and renderer",
  /realestate: \["batdongsan"\]/.test(con) && /realestate: "building-2"/.test(con) && /window\.JavisRealEstate\.mount\(el\)/.test(con));
check("the page sits in the Research group", /id: "nghien_cuu"[\s\S]{0,160}ids: \[[^\]]*"realestate"/.test(con));
check("voice commands know the page", /"realestate"/.test(read("dashboard/ui-actions.js")) && /"bat dong san": "realestate"/.test(read("server/ui_targets.py")));
const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));
const src = read("dashboard/realestate.js");
const keys = Array.from(new Set((src.match(/tw\("([a-z_.]+)"/g) || []).map((m) => m.slice(4, -1))));
check("every string the page uses is in both dictionaries", keys.every((k) => vi[k] && en[k]) || (console.log("   missing: " + keys.filter((k) => !vi[k] || !en[k]).join(", ")), false));
check("the page and the chart icons exist", ["building-2", "telescope", "trending-up", "trending-down", "minus", "map-pin", "sparkles", "lightbulb", "message-circle", "chart-column", "triangle-alert"].every((n) => read("dashboard/vendor/lucide-icons.js").includes('"' + n + '"')));

if (fails.length) { console.log(`\n${fails.length} FAILED`); process.exit(1); }
console.log("\nPASS");
