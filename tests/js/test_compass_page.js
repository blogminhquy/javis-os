/* Investment compass page (compass.js + compass/data.json).

       node tests/js/test_compass_page.js

   Checks the live-number reader and signal checks, the allocation rounding, that the page draws every tab from the
   data, that the data file keeps its shape (seven asset classes with fixed colours, stances and scores in range,
   factor impacts for every asset, allocations adding to 100, every text in Vietnamese and English, real source links,
   no long dashes), and that the page is wired like the other lazy pages. */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const CP = require(path.join(ROOT, "dashboard/compass.js"));
const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));

// ---------- live numbers ----------
const ov = { sections: {
  vn: { regime: { label: "risk_off", score: -30 }, indices: [{ symbol: "VNINDEX", price: 1725, chg_5d: -1.2, trend: "down" }] },
  world: { regime: { label: "neutral", vix: 24.5 }, key: [{ symbol: "GC=F", price: 4100, trend: "up" }, { symbol: "DX-Y.NYB", price: 101.4, trend: "down" }, { symbol: "^TNX", price: 4.86 }] },
  crypto: { fng: { value: 34, label: "Fear" }, key: [{ symbol: "BTC", id: "bitcoin", price: 76000, trend: "down" }] },
} };
check("reads an index field", CP._liveGet(ov, "vn:idx:VNINDEX:price") === 1725);
check("reads a world key with a dot in the symbol", CP._liveGet(ov, "world:key:DX-Y.NYB:price") === 101.4);
check("reads a coin by id", CP._liveGet(ov, "crypto:key:bitcoin:trend") === "down");
check("reads regime and fear-greed fields", CP._liveGet(ov, "world:regime:vix") === 24.5 && CP._liveGet(ov, "crypto:fng:value") === 34);
check("missing data reads as null", CP._liveGet(ov, "world:key:NOPE:price") === null && CP._liveGet(null, "vn:regime:label") === null
  && CP._liveGet({ sections: { vn: { error: "x" } } }, "vn:regime:label") === null);
check("conditions: <, >, ==, !=", CP._evalCond(ov, { ref: "crypto:fng:value", op: "<", value: 40 }) === true
  && CP._evalCond(ov, { ref: "world:key:^TNX:price", op: ">", value: 5 }) === false
  && CP._evalCond(ov, { ref: "vn:idx:VNINDEX:trend", op: "==", value: "down" }) === true
  && CP._evalCond(ov, { ref: "vn:regime:label", op: "!=", value: "risk_off" }) === false);
check("a condition without data is null, not false", CP._evalCond(ov, { ref: "world:key:X:price", op: ">", value: 1 }) === null && CP._evalCond(ov, null) === null);
const tally = CP._signalTally(ov, [{ live: { ref: "crypto:fng:value", op: "<", value: 40 } }, { live: { ref: "world:key:GC=F:trend", op: "==", value: "down" } }, { text: "manual" }]);
check("signal tally counts met / known / total", tally.met === 1 && tally.known === 2 && tally.total === 3);

// ---------- allocation ----------
const n = CP._normAlloc({ a: 1, b: 1, c: 1 }, ["a", "b", "c"]);
check("thirds round to whole percents adding to 100", n.reduce((s, p) => s + p.pct, 0) === 100 && n.every((p) => p.pct === 33 || p.pct === 34));
check("zero weights drop out and order is kept", JSON.stringify(CP._normAlloc({ b: 0, a: 60, c: 40 }, ["a", "b", "c"]).map((p) => p.id)) === '["a","c"]');
check("empty allocation is empty", CP._normAlloc({}, []).length === 0);

// ---------- the data file ----------
let data = null;
try { data = JSON.parse(read("dashboard/compass/data.json")); } catch (e) { data = null; }
check("data.json parses", !!data);
const assets = (data && data.assets) || [];
const ids = assets.map((a) => a.id);
check("seven asset classes, each with its own colour slot", ids.length === 7 && ids.every((id) => CP.ASSET_SLOT[id]) && new Set(ids.map((id) => CP.ASSET_SLOT[id])).size === 7);
check("stances are accumulate / hold / reduce and scores -2..2", assets.every((a) => ["accumulate", "hold", "reduce"].includes(a.stance) && Number.isInteger(a.score) && a.score >= -2 && a.score <= 2));
check("every asset has reasons, upside, risks and both signal lists", assets.every((a) => (a.thesis || []).length && (a.bull || []).length && (a.bear || []).length && (a.enter_when || []).length && (a.exit_when || []).length));
const liveRefs = [];
assets.forEach((a) => (a.enter_when || []).concat(a.exit_when || []).forEach((s) => { if (s.live) liveRefs.push(s.live); }));
check("live signals use a known source and operator", liveRefs.length >= 8 && liveRefs.every((l) => /^(vn|world|crypto):(idx|key|regime|fng|global)(:|$)/.test(l.ref) && ["<", "<=", ">", ">=", "==", "!=", "in"].includes(l.op)));
check("live signals only read fields the overview serves", liveRefs.every((l) => { const f = l.ref.split(":"); const k = f[1]; const fld = k === "regime" || k === "fng" ? f[2] : f[3]; return ["price", "chg_1d", "chg_5d", "trend", "score", "rsi", "label", "vix", "value", "breadth50"].includes(fld); }));
const factors = (data && data.factors) || [];
check("at least 12 factors, world and Vietnam", factors.length >= 12 && factors.some((f) => f.scope === "world") && factors.some((f) => f.scope === "vn"));
check("each factor scores every asset from -2 to 2", factors.every((f) => ids.every((id) => Number.isInteger((f.impact || {})[id]) && Math.abs(f.impact[id]) <= 2)));
const profs = (data && data.profiles) || [];
check("three risk profiles whose weights add to 100", profs.length === 3 && profs.every((p) => ["now", "neutral"].every((k) => Object.values(p[k] || {}).reduce((s, v) => s + v, 0) === 100 && Object.keys(p[k]).every((id) => ids.includes(id)))));
check("clock markers sit in a known phase inside the square", ((data && data.clock && data.clock.markers) || []).length >= 2 && data.clock.markers.every((m) => data.clock.phases.some((p) => p.key === m.phase) && Math.abs(m.x) <= 1 && Math.abs(m.y) <= 1));
check("calendar dates are ISO and events name real assets", (data.calendar || []).length >= 5 && data.calendar.every((e) => /^\d{4}-\d{2}-\d{2}$/.test(e.date) && (e.assets || []).every((id) => ids.includes(id))));
check("real source links", (data.sources || []).length >= 10 && data.sources.every((s) => /^https?:\/\//.test(s.url || "")));
check("an update date and an as-of label", /^\d{4}-\d{2}-\d{2}$/.test(data.updated || "") && !!data.as_of);
const bilingual = (v) => v && typeof v === "object" && typeof v.vi === "string" && v.vi.trim() && typeof v.en === "string" && v.en.trim();
const badText = [];
(function walk(o, where) {
  if (Array.isArray(o)) return o.forEach((x, i) => walk(x, where + "[" + i + "]"));
  if (o && typeof o === "object") {
    if ("vi" in o || "en" in o) { if (!bilingual(o)) badText.push(where); return; }
    Object.keys(o).forEach((k) => walk(o[k], where + "." + k));
  }
})(data, "data");
check("every text is in Vietnamese and English", badText.length === 0 || (console.log("   " + badText.slice(0, 8).join("\n   ")), false));
check("no long dashes in the data or the page (owner rule)", !/[–—]/.test(read("dashboard/compass/data.json")) && !/[–—]/.test(read("dashboard/compass.js")));

// ---------- the page draws from the data ----------
global.window = undefined;
const base = { asset: "stocks_vn", profile: "balanced", capital: 500, scope: "all", live: ov, now: Date.parse("2026-11-10") };
const page = (tab, extra) => CP._pageHtml(data, Object.assign({}, base, { tab }, extra || {}));
const o = page("overview");
check("overview: verdict, live tiles, seven asset cards, cycle clock", o.includes("cp-hero") && o.includes("cp-pulse") && (o.match(/class="cp-ac"/g) || []).length === 7 && o.includes("cp-clock-svg"));
check("overview: live entry signals are counted on the cards", /cp\.sig_enter_n|Entry signals|Tín hiệu vào/.test(o));
const a = page("assets");
check("asset tab: picker, both signal lists, a live verdict on a signal", (a.match(/data-asset=/g) || []).length >= 7 && (a.match(/class="cp-sigs"/g) || []).length === 2 && a.includes('class="cp-sig off"'));
const d = page("drivers");
check("drivers tab: factor x asset grid with signed cells, sentiment, commodities", d.includes("cp-grid") && /cp-im-p[12]"/.test(d) && /cp-im-n[12]"/.test(d) && d.includes("cp-zone") && (d.match(/cp-note-v/g) || []).length >= 8);
check("drivers tab filters by scope", (page("drivers", { scope: "vn" }).match(/cp-f-n/g) || []).length === factors.filter((f) => f.scope === "vn").length);
const al = page("alloc");
check("allocation tab: two bars, an amount per asset from the capital", (al.match(/class="cp-bar"/g) || []).length === 2 && (al.match(/data-amt=/g) || []).length >= 6 && al.includes("data-capital"));
const pb = page("playbook");
check("playbook tab: calendar, if-then rules, past cycles", pb.includes("cp-cal") && pb.includes("cp-pb-r") && pb.includes("cp-tl"));
check("an old outlook is flagged as out of date", page("overview", { now: Date.parse("2027-03-01") }).includes("cp-chip-warn"));
check("no live data still draws the page", page("overview", { live: false }).includes("cp-ac"));
const withDraft = page("overview", { meta: { source: "bundled", draft: { changed: ["asset:gold", "verdict"], at: 1762650000, note: "<b>n</b>" } } });
check("a waiting draft shows preview, approve and discard", withDraft.includes("cp-draft") && withDraft.includes("data-upd-preview") && withDraft.includes("data-upd-approve") && withDraft.includes("data-upd-discard"));
check("the draft note is escaped", !withDraft.includes("<b>n</b>"));
check("no draft, no banner", !page("overview", { meta: { source: "bundled", draft: null } }).includes("cp-draft"));
const upd = page("overview", { updOpen: true, sched: false, meta: { source: "updated", updated_at: 1762650000 } });
check("the update panel offers update now and the monthly schedule", upd.includes("cp-upd") && upd.includes("data-upd-now") && upd.includes("data-upd-sched"));
check("a running schedule offers to turn it off", page("overview", { updOpen: true, sched: { id: "r1", next: "08/12" } }).includes('data-upd-unsched="r1"'));
check("the toolbar has the update button", page("overview").includes("data-upd "));
const frame = page("overview", { meta: { source: "bundled", draft: { changed: ["verdict"], at: 1 } }, updOpen: true, sched: false });
check("the tab bar sits above the scroller, banner and content scroll inside it",
  frame.indexOf("cp-toolbar") < frame.indexOf('class="cp-scroll"') && frame.indexOf('class="cp-scroll"') < frame.indexOf("cp-draft")
  && frame.indexOf('class="cp-scroll"') < frame.indexOf("cp-upd") && frame.indexOf('class="cp-scroll"') < frame.indexOf('class="cp-main"'));
const css = read("dashboard/compass.css");
check("the page hides the shared title row and only the content scrolls",
  /\.cview:has\(\.cview-body > \.cp-root\) \.cview-head \{ display: none; \}/.test(css) && /\.cview-body:has\(> \.cp-root\) \{ overflow: hidden;/.test(css) && /\.cp-scroll \{[^}]*overflow-y: auto/.test(css));
check("the page reads the approved outlook first, then the bundled file", /DATA_URL = "\/compass\/data"/.test(read("dashboard/compass.js")) && /UPD_MARK = "javis_compass_draft"/.test(read("dashboard/compass.js")));
check("page text is escaped", !CP._pageHtml({ assets: [{ id: "re_vn", name: { vi: "<script>", en: "<script>" }, stance: "hold", score: 0 }] }, { tab: "overview" }).includes("<script>"));
global.window = { t: (k) => en[k] || k };
check("the ask prompt carries the live numbers", /4[.,]?100/.test(CP._askPrompt(data, Object.assign({}, base, { tab: "overview" }), "en"))
  && /1[.,]?725/.test(CP._askPrompt(data, Object.assign({}, base, { tab: "assets" }), "en")));
global.window = undefined;

// ---------- wiring ----------
const con = read("dashboard/console.js");
const html = read("dashboard/index.html");
const lazy = JSON.parse((html.match(/<script id="javis-lazy" type="application\/json">([\s\S]*?)<\/script>/) || [])[1] || "{}");
const grp = JSON.stringify(lazy.labandautu || []);
check("lazy group labandautu loads the CSS then the JS", grp.indexOf("compass.css") >= 0 && grp.indexOf("compass.css") < grp.indexOf("compass.js"));
check("console.js maps the page to its group, icon and renderer",
  /compass: \["labandautu"\]/.test(con) && /compass: "compass"/.test(con) && /window\.JavisCompass\.mount\(el\)/.test(con));
check("the page sits in the Research group", /id: "nghien_cuu"[\s\S]{0,200}ids: \[[^\]]*"compass"/.test(con));
check("voice commands know the page", /"compass"/.test(read("dashboard/ui-actions.js")) && /"la ban dau tu": "compass"/.test(read("server/ui_targets.py")));
const src = read("dashboard/compass.js");
const keys = Array.from(new Set((src.match(/tw\("([a-z_.]+)"/g) || []).map((m) => m.slice(4, -1))));
const dyn = ["cp.stance.acc", "cp.stance.hold", "cp.stance.red", "cp.regime.risk_on", "cp.regime.risk_off", "cp.regime.neutral", "cp.regime.unknown",
  "cp.zone.fear", "cp.zone.greed", "cp.zone.neutral", "cp.scope.world", "cp.scope.vn", "page.compass.label", "page.compass.sub"].concat(CP.TABS.map((t) => "cp.tab." + t));
const all = keys.concat(dyn);
check("every string the page uses is in both dictionaries", all.every((k) => vi[k] && en[k]) || (console.log("   missing: " + all.filter((k) => !vi[k] || !en[k]).join(", ")), false));
const icons = read("dashboard/vendor/lucide-icons.js");
const used = Array.from(new Set((src.match(/ic\("([a-z0-9-]+)"\)/g) || []).map((m) => m.slice(4, -2)))).concat(["compass", "layers", "activity", "chart-pie", "calendar"]);
check("every icon the page uses exists", used.every((n) => icons.includes('"' + n + '"')) || (console.log("   missing: " + used.filter((n) => !icons.includes('"' + n + '"')).join(", ")), false));

if (fails.length) { console.log(`\n${fails.length} FAILED`); process.exit(1); }
console.log("\nPASS");
