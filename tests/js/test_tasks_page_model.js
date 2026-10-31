// Tasks page (0.422.0): the pure model that merges Kanban jobs, reminders, loops, page watches and incidents.
// Run: node tests/js/test_tasks_page_model.js
"use strict";
const path = require("path");
const fs = require("fs");
const M = require(path.join(__dirname, "..", "..", "dashboard", "tasks.js"));

let fails = 0;
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails++; }

// A fixed "now": 2026-10-30 10:30 local time.
const now = Math.floor(new Date(2026, 9, 30, 10, 30).getTime() / 1000);
const at = (d, h, m) => Math.floor(new Date(2026, 9, d, h, m || 0).getTime() / 1000);

const src = {
  brain: "/b/main",
  kanban: {
    orchestration: "off",
    operations: {
      active: [{ id: "t1", title: "Write 3 posts", status: "running", metadata: { agent: { slug: "nd" } }, created_at: at(30, 9) }],
      attention: [
        { id: "t2", title: "Sync orders", status: "blocked", block_kind: "needs_input", block_reason: "Reconnect Pancake", created_at: at(29, 9) },
        { id: "t3", title: "Weekly sheet", status: "blocked", block_kind: "transient", block_reason: "Sheets slow", updated_at: at(30, 10) },
        { id: "t6", title: "Publish draft", status: "review", needs_approval: 1, created_at: at(30, 8) },
      ],
      queue: [
        { id: "t4", title: "Email wholesalers", status: "ready", created_at: at(30, 8) },
        { id: "t7", title: "Old queued job", status: "todo", not_before: at(28, 9), created_at: at(27, 9) },
        { id: "t8", title: "Later job", status: "todo", not_before: at(31, 15), created_at: at(30, 9), idempotency_key: "agent:kt:x" },
      ],
      handled: [],
      history: [{ id: "t5", title: "Stock count", status: "done", result: "1,240 bottles", updated_at: at(29, 16, 46), metadata: { run_seconds: 360 } }],
    },
  },
  viec: { brains: [
    { name: "Main", path: "/b/main", is_default: true,
      reminders: [
        { id: "r1", text: "POS report", label: "POS report", mode: "task", status: "pending", cron: "0 8 * * *", cron_human: "8:00 every day", due_at: at(31, 8) },
        { id: "r2", text: "Call supplier", mode: "notify", status: "pending", due_at: at(30, 14) },
        { id: "r3", text: "News digest", mode: "task", status: "paused", cron: "0 7 * * *", cron_human: "7:00 every day", due_at: at(31, 7) },
        { id: "r4", text: "Missed one", mode: "task", status: "pending", due_at: at(29, 9), running: false },
      ],
      loops: [{ slug: "ads", name: "Ad watch", enabled: true, interval_min: 120, next_run: at(30, 12), running: true, fail_streak: 0 }] },
    { name: "Other", path: "/b/other", reminders: [{ id: "rx", text: "Not mine", status: "pending", due_at: at(30, 9) }], loops: [] },
  ] },
  rems: { history: [
    { id: "h1", text: "Transfer reminder", mode: "notify", status: "done", fired_at: at(29, 11), result: "Sent" },
    { id: "h2", text: "Inventory sheet", mode: "task", status: "failed", fired_at: at(29, 16), error: "Sheets did not answer" },
  ] },
  watch: { watches: [{ id: "w1", title: "Competitor page", interval_min: 60, status: "active", next_at: at(30, 11), fail_streak: 2, last_error: "timeout" }] },
  incidents: { incidents: [{ id: "inc1", title: "Pancake expired", status: "needs_you", at: at(30, 9), brain: "/b/main" },
    { id: "inc2", title: "Other brain", status: "open", at: at(30, 9), brain: "/b/other" }] },
  loopLog: { entries: ["## [10:05] ads · loop (business/full) - schedule\nChecked 3 ads."] },
};

const m = M.model(src, now);
const byId = id => m.items.find(i => i.id === id);
check("today is 2026-10-30", m.today === "2026-10-30");
check("a running Kanban job is 'run' and keeps its assistant", byId("k:t1").st === "run" && byId("k:t1").who === "nd");
check("a job waiting for input asks the owner", byId("k:t2").st === "ask" && byId("k:t2").reason === "Reconnect Pancake");
check("a transient block is handled by Javis (calm), not an ask", byId("k:t3").st === "calm" && !m.ask.some(a => a.id === "k:t3"));
check("a job in review asks for approval", byId("k:t6").st === "ask");
check("ready jobs wait their turn today", byId("k:t4").st === "queue" && byId("k:t4").date === "2026-10-30");
check("a job held to a future time is scheduled on that day", byId("k:t8").st === "sched" && byId("k:t8").date === "2026-10-31");
check("the agent prefix of the idempotency key names the assistant", byId("k:t8").who === "kt");
check("unassigned work belongs to Javis Core", byId("k:t4").who === "javis-core");
check("a done Kanban job is dated when it finished, with its run time", byId("k:t5").st === "done" && byId("k:t5").date === "2026-10-29" && byId("k:t5").took === 360);
check("a cron reminder is a recurring job", m.recurring.some(r => r.id === "r:r1" && r.on && r.sc === "8:00 every day"));
check("its next run is an item tomorrow at 08:00", byId("r:r1").date === "2026-10-31" && byId("r:r1").time === "08:00");
check("a notify reminder is 'remind only'", byId("r:r2").mode === "remind" && byId("r:r2").st === "sched");
check("a paused reminder is recurring and off, with no item", m.recurring.some(r => r.id === "r:r3" && !r.on) && !byId("r:r3"));
check("a pending reminder whose time passed is overdue", byId("r:r4").over === true);
check("an old queued job is overdue", byId("k:t7").over === true);
check("other brains are left out", !byId("r:rx"));
check("a running loop is recurring, running, and its next run is today", m.recurring.some(r => r.id === "l:ads" && r.running) && byId("l:ads").st === "run");
check("a page watch is a recurring job", m.recurring.some(r => r.id === "w:w1" && r.on));
check("a done one-time reminder from history is in done", byId("rh:h1").st === "done");
check("a failed reminder is in the error history, not open", m.fails.some(f => f.id === "rf:h2" && !f.open));
check("a failing watch is an open error Javis retries", m.fails.some(f => f.id === "wf:w1" && f.open && f.self));
check("an incident of this brain is an open error that needs the owner", m.fails.some(f => f.id === "i:inc1" && f.open && f.needYou));
check("an incident of another brain is left out", !m.fails.some(f => f.id === "i:inc2"));
check("the loop log becomes log entries", m.log.some(e => /ads/.test(e.title) && /Checked 3 ads/.test(e.text)));
check("orchestration off with queued jobs is reported", m.orch === "off" && m.waiting === 2);

// lists
const today = m.today;
const ids = list => m.items.filter(i => M.inList(i, list, today)).map(i => i.id).sort();
check("Today holds today's work", ids("today").includes("k:t1") && ids("today").includes("r:r2") && !ids("today").includes("r:r1"));
check("Upcoming holds tomorrow's runs", ids("week").includes("r:r1") && ids("week").includes("k:t8"));
check("Overdue holds the two late items", JSON.stringify(ids("over")) === JSON.stringify(["k:t7", "r:r4"]));
check("Done holds finished work", ids("done").includes("k:t5") && ids("done").includes("rh:h1"));
check("an assistant's list holds its open work", JSON.stringify(ids("who:nd")) === JSON.stringify(["k:t1"]));

// recurring timeline: on before off, then by next run
const tl = M.byTimeline(m.recurring).map(r => r.id);
check("recurring jobs run on the day's timeline, switched off last", tl[tl.length - 1] === "r:r3" && tl.indexOf("w:w1") < tl.indexOf("l:ads") && tl.indexOf("l:ads") < tl.indexOf("r:r1"));

// cron from the add form
check("daily cron", M.cronFor("daily", "2026-10-30", "07:30") === "30 7 * * *");
check("weekday cron", M.cronFor("weekdays", "2026-10-30", "08:00") === "0 8 * * 1-5");
check("weekly cron uses the weekday of the date", M.cronFor("weekly", "2026-10-30", "09:00") === "0 9 * * 5");
check("monthly cron uses the day of the month", M.cronFor("monthly", "2026-10-30", "09:00") === "0 9 30 * *");

// ---- tab "Mine" (0.423.0) ----
check("weekly T3/T5/T7 falls on Thursday, not Friday", M.occursOn({ unit: "week", n: 1, days: [2, 4, 6] }, "2026-09-01", "2026-10-29") && !M.occursOn({ unit: "week", n: 1, days: [2, 4, 6] }, "2026-09-01", "2026-10-30"));
check("every 2 days counts from the start", M.occursOn({ unit: "day", n: 2 }, "2026-10-01", "2026-10-03") && !M.occursOn({ unit: "day", n: 2 }, "2026-10-01", "2026-10-02"));
check("every 2 weeks skips the week in between", M.occursOn({ unit: "week", n: 2, days: [1] }, "2026-10-05", "2026-10-19") && !M.occursOn({ unit: "week", n: 2, days: [1] }, "2026-10-05", "2026-10-12"));
check("a monthly 31st falls on the last day of a short month", M.occursOn({ unit: "month", n: 1 }, "2026-08-31", "2026-09-30") && !M.occursOn({ unit: "month", n: 1 }, "2026-08-31", "2026-09-29"));
check("nothing occurs before the start", !M.occursOn({ unit: "day", n: 1 }, "2026-11-01", "2026-10-30"));
check("next and previous occurrence", M.nextOcc({ unit: "week", n: 1, days: [2, 4, 6] }, "2026-09-01", "2026-10-30") === "2026-10-31"
  && M.prevOcc({ unit: "week", n: 1, days: [2, 4, 6] }, "2026-09-01", "2026-10-30") === "2026-10-29");
const store = { projects: [], tasks: [
  { id: "a", title: "Call Lan", date: "2026-10-30", time: "14:00", status: "open", project: "p1" },
  { id: "b", title: "Quote Hai Phong", date: "2026-10-29", status: "open" },
  { id: "c", title: "Find a printer", date: null, status: "open" },
  { id: "d", title: "Run PLR ads", date: "2026-10-29", status: "done", done_at: 1 },
  { id: "e", title: "Read 30 min", date: "2026-10-01", time: "21:00", repeat: { unit: "day", n: 1 }, status: "open", done_dates: { "2026-10-28": { at: 1, by: "me" } } },
  { id: "f", title: "Swim", date: "2026-09-01", repeat: { unit: "week", n: 1, days: [2, 4, 6] }, status: "open", done_dates: { "2026-10-29": { at: 1, by: "javis" } } },
] };
const mm = M.mineModel(store, "2026-10-30");
const mi = id => mm.items.find(i => i.id === id);
const mids = list => mm.items.filter(i => M.inList(i, list, "2026-10-30")).map(i => i.id).sort();
check("a dated one-off task is today's, with its project", mi("m:a").date === "2026-10-30" && mi("m:a").proj === "p1");
check("a one-off task dated yesterday is overdue", mi("m:b").over === true);
check("an undated task goes to No date", JSON.stringify(mids("nodate")) === JSON.stringify(["m:c"]));
check("a done task is done and not overdue", mi("m:d").st === "done" && !mi("m:d").over);
check("a daily task has today's occurrence under its own id", mi("m:e").date === "2026-10-30" && mi("m:e").st === "todo");
check("its missed yesterday is an overdue occurrence to tick", mi("mo:e:2026-10-29") && mi("mo:e:2026-10-29").over);
check("a done occurrence shows in Done on its day", mi("md:e:2026-10-28").st === "done");
check("a weekly task off today shows its next day with a dated id", mi("mn:f:2026-10-31") && mi("mn:f:2026-10-31").date === "2026-10-31");
check("a weekly task done at its last session has no overdue", !mm.items.some(i => i.id.indexOf("mo:f:") === 0));
check("repeating tasks are listed as recurring", mm.recurring.map(r => r.id).sort().join() === "m:e,m:f");
check("Overdue holds the one-off and the missed occurrence", JSON.stringify(mids("over")) === JSON.stringify(["m:b", "mo:e:2026-10-29"]));
check("a project list holds its open tasks", JSON.stringify(mids("proj:p1")) === JSON.stringify(["m:a"]));
check("repeat text", M.repHuman({ unit: "week", n: 1, days: [6, 2] }) .indexOf("nv.rep.weekly") === 0);
check("a weekly Javis schedule is a cron", M.javisSchedule({ unit: "week", n: 1, days: [4, 2] }, "2026-11-03", "06:30").cron === "30 6 * * 2,4");
check("every 3 days for Javis is a fixed step", M.javisSchedule({ unit: "day", n: 3 }, "2026-11-03", "06:30").repeat_min === 4320);

// ---- habits (0.424.0) ----
const dn = (iso, n) => M.addDays(iso, n);
const T0 = "2026-10-30";
const dd = days => Object.fromEntries(days.map(x => [x, { at: 1, by: "me" }]));
const read = { id: "r", title: "Read 30 min", date: dn(T0, -10), repeat: { unit: "day", n: 1 }, habit: { start: dn(T0, -10), remind: "auto" },
  done_dates: dd([10, 9, 8, 7, 6, 5, 4, 3, 2].map(i => dn(T0, -i))) };
let hk = M.habitCalc(read, T0);
check("habit: yesterday missed freezes and keeps the streak", hk.frozen && hk.cur === 9 && !hk.doneToday);
hk = M.habitCalc(Object.assign({}, read, { done_dates: Object.assign({}, read.done_dates, dd([T0])) }), T0);
check("habit: done today thaws it", !hk.frozen && hk.doneToday && hk.cur === 10);
hk = M.habitCalc(Object.assign({}, read, { done_dates: dd([10, 9, 8].map(i => dn(T0, -i))) }), T0);
check("habit: two missed sessions in a row lose the streak", hk.cur === 0 && !hk.frozen && hk.best === 3);
const swim = { id: "s", title: "Swim", date: "2026-09-01", repeat: { unit: "week", n: 1, days: [2, 4, 6] }, habit: { start: "2026-09-01" },
  done_dates: dd(["2026-10-27", "2026-10-29"]) };
hk = M.habitCalc(swim, T0);
check("habit: a weekday habit rests on Friday (no freeze)", hk.rest && !hk.frozen && hk.days["2026-10-28"] === "r");
const st = M.habitStats([read, swim], T0);
check("habit stats: only habits with a session today count as due", st.due === 1 && st.done === 0 && st.ice === 1);
const moods = M.habitLines(st, T0).map(l => l.mood);
check("habit lines: a frozen habit makes Javis sulk first", moods[0] === "suspicious");
check("habit lines: a rest day gets the sleepy line", moods.indexOf("sleepy") >= 0);
check("usual time needs three ticks", M.usualTime({ done_dates: dd([T0]) }) === "");

// ---- appointments (0.425.0) ----
check("appointment states: past, live, upcoming", M.apptState("2026-10-29", "09:00", "10:00", T0, "08:00") === "past"
  && M.apptState(T0, "09:00", "10:00", T0, "09:30") === "live" && M.apptState(T0, "09:00", "10:00", T0, "10:00") === "past"
  && M.apptState(T0, "11:00", "12:00", T0, "10:30") === "todo");
const ap = M.mineModel({ tasks: [{ id: "a", kind: "appt", title: "Meet", date: T0, time: "09:00", end: "09:45" },
  { id: "w", kind: "appt", title: "Weekly", date: "2026-10-26", time: "08:30", end: "09:00", repeat: { unit: "week", n: 1, days: [1] } }] }, T0, "10:30");
check("a finished appointment is done on its own, never overdue", ap.items.find(i => i.id === "m:a").st === "done" && !ap.items.some(i => i.over));
check("a weekly appointment shows its next date and is listed as recurring", ap.items.some(i => i.id === "mn:w:2026-11-02") && ap.recurring.some(r => r.id === "m:w" && r.appt));

// ---- habit lines written by Core, Google Calendar (0.427.0) ----
const coach = { date: T0, head: { rest: "Hôm nay {names} được nghỉ, mai làm tiếp nha" }, habits: { r: { frozen: "{name} đang đóng băng, chuỗi {n} ngày chờ bạn" } } };
const cl = M.habitLines(st, T0, coach);
check("Core's frozen line wins, filled with today's numbers", cl[0].mood === "suspicious" && cl[0].tx === "read đang đóng băng, chuỗi 9 ngày chờ bạn");
check("Core's head line wins too", cl.some(l => l.mood === "sleepy" && l.tx === "Hôm nay swim được nghỉ, mai làm tiếp nha"));
const stale = M.habitLines(st, T0, Object.assign({}, coach, { date: "2026-10-29" }));
check("yesterday's lines are not used today", stale[0].tx !== cl[0].tx);
const gm = M.mineModel({ tasks: [], gcal: [
  { id: "e1", title: "Supplier call", start: "2026-10-30T15:00:00", end: "2026-10-30T15:30:00", location: "Zoom", link: "https://calendar.google.com/x" },
  { id: "e2", title: "Holiday", start: "2026-11-02", end: "2026-11-03", all_day: true },
  { id: "e3", title: "Breakfast", start: "2026-10-30T08:00:00", end: "2026-10-30T09:00:00" }] }, T0, "10:30");
const g1 = gm.items.find(i => i.id === "g:e1"), g2 = gm.items.find(i => i.id === "g:e2"), g3 = gm.items.find(i => i.id === "g:e3");
check("a calendar event becomes a read-only appointment of the Mine tab", g1 && g1.src === "gcal" && g1.appt && g1.date === T0 && g1.time === "15:00" && g1.end === "15:30" && g1.raw.location === "Zoom");
check("an all-day event has no time", g2 && g2.date === "2026-11-02" && g2.time === "" && g2.raw.all_day);
check("a past event is done on its own, never overdue", g3 && g3.st === "done" && !g3.over);
check("Today lists today's events, Upcoming the later ones", M.inList(g1, "today", T0) && M.inList(g2, "week", T0) && !M.inList(g2, "today", T0));

// 0.429.0: jobs a chatbot made sit under the bot's assistant, or under the bot when that assistant is not in the brain
const bsrc = Object.assign({}, src, {
  agents: [{ slug: "vu", name: "Vu" }],
  bots: { bots: [{ id: "bot_vu", name: "Javis Vu", agent: "vu" }, { id: "bot_shop", name: "Shop", agent: "ghost" }],
    jobs: { "r:r1": "bot_vu", "l:ads": "bot_shop", "r:h1": "bot_vu" } },
});
bsrc.kanban = JSON.parse(JSON.stringify(src.kanban));
bsrc.kanban.operations.queue[0].created_by = "bot:bot_shop";
const bm = M.model(bsrc, now), bid = id => bm.items.find(i => i.id === id), brec = id => bm.recurring.find(i => i.id === id);
check("a bot's reminder belongs to the bot's assistant", bid("r:r1").who === "vu" && brec("r:r1").who === "vu");
check("a bot's loop whose assistant is not here belongs to the bot", brec("l:ads").who === "bot:bot_shop");
check("a Kanban job created by bot:<id> belongs to that bot", bid("k:t4").who === "bot:bot_shop");
check("a Kanban job with its own assistant keeps it", bid("k:t1").who === "nd");
check("the history and the log follow the bot too", bid("rh:h1").who === "vu" && bm.log.some(l => l.ref === "rh:h1" && l.who === "vu"));
check("the loop log line follows its loop", bm.log.some(l => /^ads/.test(l.title) && l.who === "bot:bot_shop"));
check("the rest stays with Javis Core", bid("r:r2").who === "javis-core" && brec("w:w1").who === "javis-core");

// no Vietnamese text in the running code of the page (it goes through i18n)
const js = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "tasks.js"), "utf8");
check("the nav points to the Tasks page", /ids: \["tasks", "webhooks"\]/.test(fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "console.js"), "utf8")));
check("old page ids open the Tasks page", /kanban: "tasks", selfimprove: "tasks"/.test(fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "console.js"), "utf8")));
check("the page asks which chatbot made which job", /getJSON\("\/tasks\/bots\?brain=" \+ enc\)/.test(js));
check("the page exposes mount and unmount", /window\.JavisTasks = \{ mount: mount, unmount: unmount/.test(js));

console.log(fails ? `\n${fails} FAILED` : "\nall passed");
process.exit(fails ? 1 : 0);
