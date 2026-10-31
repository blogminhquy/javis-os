// Tasks page stats (0.428.0): both tabs render from GET /tasks/stats, the shared date range picker sets the period,
// time only (no money), the Javis logo, Javis's tab first.
// Run: node tests/js/test_tasks_stats_0428.js
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..", "..");
const read = (f) => fs.readFileSync(path.join(ROOT, f), "utf8");

let fails = 0;
function check(name, cond, info) { console.log((cond ? "ok   " : "FAIL ") + name + (!cond && info ? "  [" + info + "]" : "")); if (!cond) fails++; }

const store = {};
global.window = {
  t: (k) => k,
  localStorage: { getItem: (k) => store[k] || null, setItem: (k, v) => { store[k] = v; } },
};
require(path.join(ROOT, "dashboard", "date-range.js"));
const S = require(path.join(ROOT, "dashboard", "tasks-stats.js"));

// ---- pure helpers
check("best day needs at least 2 things", S.bestDay({ "2026-10-27": { task: 1 } }) === null);
const bd = S.bestDay({ "2026-10-27": { task: 2, habit: 1 }, "2026-10-28": { task: 1 } });
check("best day is the weekday with the most done", bd && bd.wd === 2 && bd.n === 3);
const hrs = new Array(24).fill(0); hrs[20] = 2; hrs[21] = 3;
check("golden hours: the two hours with the most done", S.goldWindow(hrs) === 20);
check("golden hours need some data", S.goldWindow(new Array(24).fill(0)) === -1);
check("time is minutes under an hour, hours above", S.fmtHours(30) === "nv.sta.minutes" && S.fmtHours(90) === "nv.sta.hours");

// ---- rendering from a fake answer
const days = []; for (let i = 0; i < 84; i++) days.push({ d: "2026-08-" + String((i % 28) + 1).padStart(2, "0"), n: i % 3 });
const data = {
  ok: true, range: { from: "2026-10-25", to: "2026-10-31", days: 7 }, prev: { from: "2026-10-18", to: "2026-10-24" },
  minutes: { kanban: 20, reminder: 10, notify: 2, loop: 5, watch: 3 },
  me: { done: 9, prev_done: 6, by_day: { "2026-10-27": { task: 3, habit: 1, appt: 0 } }, on_time: 87, prev_on_time: 80, overdue: 1,
    habit_done: 4, appts: 2, javis_ticks: 1, heat: days, gold: hrs, hours: hrs,
    habits: [{ id: "h", title: "Read", rate: 90, done: 9, sched: 10, cur: 4, frozen: false }],
    projects: [{ id: "p", name: "Wholesale", color: "#4285f4", done: 2, total: 3 }], delayed: [{ id: "x", title: "Call Lan", moves: 3 }] },
  ai: { done: 18, prev_done: 11, share: 67, prev_share: 58, saved: 390, prev_saved: 300, saved_total: 5040, night: 4, avg_seconds: 75, handoffs: 2,
    by_kind: { kanban: { n: 6, minutes: 120 }, reminder: { n: 8, minutes: 80 }, notify: { n: 0, minutes: 0 }, loop: { n: 3, minutes: 15 }, watch: { n: 1, minutes: 3 } },
    agents: [{ key: "core", name: "", n: 15, ok: 15, fail: 1, minutes: 300 }, { key: "kho", name: "Stock", n: 3, ok: 3, fail: 0, minutes: 60 }],
    hours: hrs, rel: { ok: 18, retry: 2, ask: 1, fail: 1 } },
  weeks: [0, 1, 2, 3, 4, 5, 6, 7].map((i) => ({ from: "2026-09-0" + (i + 1), to: "2026-09-0" + (i + 1), me: 5 + i, ai: 3 * i, saved: 30 * i })),
  ideas: [{ kind: "moved", id: "x", title: "Call Lan", n: 3, minutes: 20 }, { kind: "repeat", id: "y", title: "Close the till", n: 6, minutes: 14 }],
};
global.fetch = () => Promise.resolve({ json: () => Promise.resolve(data) });
let redraws = 0;
const ctx = (tab) => ({ tab, brain: "brain", redraw: () => { redraws++; }, avatar: () => "<i></i>" });
const first = S.html(ctx("ai"));
check("first render shows the picker and a loading line", /data-act="st-range"/.test(first) && /common\.loading/.test(first));
setTimeout(() => {
  check("the answer redraws the page", redraws >= 1);
  const ai = S.html(ctx("ai")), me = S.html(ctx("me"));
  check("Javis tab: share, split bar with the Javis logo, time given back", /nv\.sta\.ai_share/.test(ai) && /ts-split/.test(ai) && /src="\/static\/logo\.svg"/.test(ai) && /nv\.sta\.time_back/.test(ai));
  check("no money anywhere", !/(đ|\$|VND|money|tiền)/i.test(ai.replace(/nv\.sta\.time_how/g, "")));
  check("Javis tab: what, assistants (Javis Core with the logo), 24 hours, reliability, ideas",
    /nv\.sta\.what/.test(ai) && /Javis Core/.test(ai) && /ts-24/.test(ai) && /ts-relbar/.test(ai) && /data-act="st-give" data-id="m:y"/.test(ai));
  check("time card can edit the minutes", /data-act="st-mins"/.test(ai));
  check("My tab: done, Javis says with the logo, tiles, per day, map, golden hours, habits, projects, moved",
    /nv\.sta\.me_done_in/.test(me) && /nv\.sta\.javis_says/.test(me) && /src="\/static\/logo\.svg"/.test(me) && /ts-tiles/.test(me)
    && /nv\.sta\.per_day/.test(me) && /ts-heat/.test(me) && /nv\.sta\.gold/.test(me) && /Read/.test(me) && /Wholesale/.test(me) && /data-act="st-give" data-id="m:x"/.test(me));
  check("the map starts on Monday (padding cells before the first day)", /ts-hc none/.test(me) || new Date(days[0].d + "T12:00:00").getDay() === 1);
  S.toggleMinutes(ctx("ai"));
  check("minutes form shows one field per kind of job", (S.html(ctx("ai")).match(/<input type="number"/g) || []).length === 5);
  S.toggleMinutes(ctx("ai"));
  // ---- wiring in the page
  const js = read("dashboard/tasks.js"), html = read("dashboard/index.html"), css = read("dashboard/tasks.css");
  check("Stats closes the lists of both tabs, on desktop and phone", /data-view="stats"/.test(js) && /data-pl="stats"/.test(js));
  check("Javis's tab comes first and the page opens on it", js.indexOf('data-v="ai"') < js.indexOf('data-v="me"') && /var tab = "ai";/.test(js));
  check("the picker, the stats and their CSS load with the Tasks page",
    /"\/static\/date-range\.css\?v=\d+",\s*"\/static\/tasks\.css\?v=\d+",\s*"\/static\/date-range\.js\?v=\d+",\s*"\/static\/tasks-stats\.js\?v=\d+",\s*"\/static\/tasks\.js/.test(html));
  check("the Chatbot page loads the shared picker CSS too", /"hoithoai": \[[\s\S]*?"\/static\/date-range\.css/.test(html));
  check("stats classes do not clash with the Chatbot stats (ts-, not st-)", !/\.st-[a-z]/.test(css.slice(css.indexOf("Stats (0.428.0)"))));
  check("poll pauses while the minutes form is open", /JavisTaskStats\.isEditing\(\)/.test(js));
  const vi = JSON.parse(read("dashboard/i18n/vi.json")), en = JSON.parse(read("dashboard/i18n/en.json"));
  check("tab names", vi["nv.tab.ai"] === "Việc của Javis" && vi["nv.tab.me"] === "Việc của tôi" && en["nv.tab.ai"] && en["nv.tab.me"]);
  const keys = new Set([...(read("dashboard/tasks-stats.js") + js).matchAll(/"(nv\.sta\.[a-z0-9_]+)"/g)].map((m) => m[1]));
  check("every stats string in both languages", [...keys].every((k) => vi[k] && en[k]), [...keys].filter((k) => !vi[k] || !en[k]).join(","));
  check("no long dashes in them", [...keys].every((k) => !/[–—]/.test(vi[k] + en[k])));
  console.log(fails ? `\n${fails} FAILED` : "\nall passed");
  process.exit(fails ? 1 : 0);
}, 30);
