/* Date range picker (dashboard/date-range.js; owner, 2026-10-28: "về bộ lọc thì nên có đầy đủ 1 chút").

       node tests/js/test_date_range.js

   The pure helpers run for real under node; the popover and the CSS are guarded by their structure.
*/
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..", "..");
const src = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");
const DRS = src("dashboard/date-range.js");
const CSS = src("dashboard/inbox-v5.css");
const HTML = src("dashboard/index.html");
const CV = src("dashboard/conversations.js");
const VI = JSON.parse(src("dashboard/i18n/vi.json"));
const EN = JSON.parse(src("dashboard/i18n/en.json"));

const fails = [];
const check = (name, cond, extra) => { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && extra ? "  [" + extra + "]" : "")); if (!cond) fails.push(name); };

const win = { t: (k, v) => k + (v ? "#" + Object.keys(v).map((x) => v[x]).join(",") : "") };
const ctx = { window: win, document: {}, console, String, Object, Array, Number, JSON, Math, Date, isNaN };
vm.createContext(ctx);
vm.runInContext(DRS, ctx);
const D = win.JavisDateRange;
const R = (p, now) => JSON.stringify(D.resolve(p, now));

// ---- 1. quick ranges on Wednesday 2026-10-28 ----
const wed = new Date(2026, 9, 28, 15, 30);
check("today and yesterday", R("today", wed) === '{"from":"2026-10-28","to":"2026-10-28"}' && R("yesterday", wed) === '{"from":"2026-10-27","to":"2026-10-27"}');
check("last 7 / 30 / 90 days include today", R("d7", wed) === '{"from":"2026-10-22","to":"2026-10-28"}' &&
  R("d30", wed) === '{"from":"2026-09-29","to":"2026-10-28"}' && R("d90", wed) === '{"from":"2026-07-31","to":"2026-10-28"}');
check("last month is the whole month before", R("last_month", wed) === '{"from":"2026-09-01","to":"2026-09-30"}' &&
  R("last_month", new Date(2026, 0, 5)) === '{"from":"2025-12-01","to":"2025-12-31"}');
check("week to date starts on Monday (a Sunday counts in the week before)", R("week", wed) === '{"from":"2026-10-26","to":"2026-10-28"}' &&
  R("week", new Date(2026, 10, 1)) === '{"from":"2026-10-26","to":"2026-11-01"}' && R("week", new Date(2026, 9, 26)) === '{"from":"2026-10-26","to":"2026-10-26"}');
check("month to date", R("month", wed) === '{"from":"2026-10-01","to":"2026-10-28"}');
check("an unknown preset gives nothing", D.resolve("d999", wed) === null);
check("dates(): a preset is resolved again, picked days are kept, nothing is 'any time'",
  JSON.stringify(D.dates({ preset: "today" }, wed)) === '{"from":"2026-10-28","to":"2026-10-28"}' &&
  JSON.stringify(D.dates({ from: "2026-10-01", to: "2026-10-09" }, wed)) === '{"from":"2026-10-01","to":"2026-10-09"}' &&
  D.dates(null) === null && D.dates({ from: "2026-10-01" }) === null);

// ---- 2. words ----
check("label: the quick range's name, picked days as d/m/y, one day once, nothing = any time",
  D.label({ preset: "d30" }) === "dr.p_d30" && D.label({ from: "2026-10-01", to: "2026-10-09" }) === "01/10/2026 - 09/10/2026" &&
  D.label({ from: "2026-10-05", to: "2026-10-05" }) === "05/10/2026" && D.label(null) === "dr.all");

// ---- 3. the month grid ----
const oct = D.monthCells(2026, 9);
check("a month is 6 weeks of 7 days, Monday first", oct.length === 42 && oct[0].iso === "2026-09-28" && new Date(2026, 8, 28).getDay() === 1);
check("days of the months around are marked out", oct[0].out === true && oct[3].iso === "2026-10-01" && oct[3].out === false &&
  oct.filter((c) => !c.out).length === 31);
const jun = D.monthCells(2026, 5);
check("a month starting on Monday starts on its first day", jun[0].iso === "2026-06-01" && jun[0].day === 1);

// ---- 4. the popover ----
check("popover: quick ranges, two months (one on phones), from -> to, Close and Apply", /class="dr-pre"/.test(DRS) && /phone \? month\(st\.y, st\.m \+ 1, "lr"\)/.test(DRS) &&
  /dr-close/.test(DRS) && /dr-apply/.test(DRS) && /role", "dialog"/.test(DRS));
check("future days cannot be picked; a second click before the first swaps the ends", /c\.iso > today \? " disabled"/.test(DRS) &&
  /b\.dataset\.d < st\.from\) \{ st\.to = st\.from; st\.from = b\.dataset\.d; \}/.test(DRS));
check("Apply stays off until both ends are picked; Escape and a click outside close it", /\(st\.preset \|\| \(st\.from && st\.to\) \? "" : " disabled"\)/.test(DRS) &&
  /e\.key === "Escape"/.test(DRS) && /document\.addEventListener\("mousedown", outside, true\)/.test(DRS));
check("the inbox's own outside-click and Escape leave an open picker alone", /\.dr-pop/.test(CV));
check("index.html loads it before the inbox modules", HTML.indexOf("/static/date-range.js") > 0 &&
  HTML.indexOf("/static/date-range.js") < HTML.indexOf("/static/inbox-v5.js") && HTML.indexOf("/static/date-range.js") < HTML.indexOf("/static/conversations.js"));
check("phones: one month, quick ranges as a wrapping row", /@media \(max-width: 640px\)[\s\S]*\.dr-/.test(CSS));

// ---- 5. keys ----
const used = [...new Set([...DRS.matchAll(/"(dr\.[a-z0-9_]+)"/g)].map((m) => m[1]))];
const miss = used.filter((k) => !VI[k] || !EN[k]);
check(`every dr.* key used (${used.length}) is in vi and en`, used.length >= 20 && !miss.length, miss.join(","));
const dashes = [String.fromCharCode(0x2014), String.fromCharCode(0x2013)];
check("no em or en dash in the file or its strings", ![DRS, fs.readFileSync(__filename, "utf8"), ...used.map((k) => VI[k] + EN[k])]
  .some((t) => dashes.some((d) => t.indexOf(d) >= 0)));

if (fails.length) { console.log("\nĐỎ: " + fails.length + ": " + fails.join(" | ")); process.exit(1); }
console.log("\nOK - test_date_range: tất cả pass");
