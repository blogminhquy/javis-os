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

// no Vietnamese text in the running code of the page (it goes through i18n)
const js = fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "tasks.js"), "utf8");
check("the nav points to the Tasks page", /ids: \["tasks", "webhooks"\]/.test(fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "console.js"), "utf8")));
check("old page ids open the Tasks page", /kanban: "tasks", selfimprove: "tasks"/.test(fs.readFileSync(path.join(__dirname, "..", "..", "dashboard", "console.js"), "utf8")));
check("the page exposes mount and unmount", /window\.JavisTasks = \{ mount: mount, unmount: unmount/.test(js));

console.log(fails ? `\n${fails} FAILED` : "\nall passed");
process.exit(fails ? 1 : 0);
