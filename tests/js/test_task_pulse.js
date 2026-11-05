// Tasks page, "Nhịp hôm nay" (2026-11-04): the pure parts of clean days, priorities and skipped times.
// Run: node tests/js/test_task_pulse.js
"use strict";
const path = require("path");
const M = require(path.join(__dirname, "..", "..", "dashboard", "tasks.js"));

let fails = 0;
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails++; }

const today = "2026-11-04";
const at = (d, h) => Math.floor(new Date(2026, 10, d, h || 12).getTime() / 1000);
const task = (o) => Object.assign({ id: "m_" + Math.random().toString(36).slice(2, 8), kind: "task", title: "t", date: null, time: "", repeat: null,
  tags: [], status: "open", done_at: 0, done_dates: {}, subs: [], habit: null, created_at: at(1) }, o);

// ---- skipped times of a repeat
const weekly = task({ title: "Weekly review", date: "2026-10-06", repeat: { unit: "week", n: 1, days: [2] } });   // Tuesdays
let m = M.mineModel({ tasks: [weekly] }, today, "10:00");
check("a missed Tuesday shows as overdue", m.items.some((i) => i.id.indexOf("mo:") === 0 && i.date === "2026-11-03"));
m = M.mineModel({ tasks: [Object.assign({}, weekly, { skip_dates: { "2026-11-03": at(3) } })] }, today, "10:00");
check("a skipped Tuesday is not overdue", !m.items.some((i) => i.over));
const daily = task({ title: "Reconcile orders", date: "2026-10-01", repeat: { unit: "day", n: 1 }, done_dates: { "2026-11-03": { at: at(3) } } });
m = M.mineModel({ tasks: [Object.assign({}, daily, { skip_dates: { "2026-11-04": at(4) } })] }, today, "10:00");
const occ = m.items.find((i) => i.id.indexOf("m") === 0 && !i.over && i.st === "todo");
check("skipping today's time moves the repeat to its next time", occ && occ.date === "2026-11-05");

// ---- pulse: clean day, frozen, priorities
const yd = "2026-11-03";
const store = (tasks, days) => ({ tasks: tasks, clean: { days: days || {} } });
const calc = (tasks, days) => { const s = store(tasks, days); return M.pulseCalc(M.mineModel(s, today, "10:00"), s, today); };

let p = calc([task({ date: today, status: "done", done_at: at(4) }), task({ date: today })], { "2026-11-02": "c", [yd]: "c" });
check("a task left open today: not clean yet", !p.clean && p.left === 1 && p.todayDone === 1);
check("the chain counts the clean days before today", p.cur === 2);
p = calc([task({ date: today, status: "done", done_at: at(4) })], { "2026-11-02": "c", [yd]: "c" });
check("all handled and one done: clean, the chain grows", p.clean && p.cur === 3);
p = calc([task({ date: yd })], { "2026-11-02": "c", [yd]: "i" });
check("an unclean yesterday with overdue left: frozen", p.frozen && p.over.length === 1);
p = calc([task({ date: today })], { "2026-11-01": "c", "2026-11-02": "x", [yd]: "c" });
check("a lost day resets the chain", p.cur === 1);
p = calc([task({ date: today, status: "done", done_at: at(4) })], { "2026-11-02": "c", [yd]: "e" });
check("an empty day neither adds nor breaks", p.cur === 2);
p = calc([], {});
check("nothing done today is never clean", !p.clean);

p = calc([task({ date: today, star: true }), task({ date: today, star: true, status: "done", done_at: at(4) }), task({ date: "2026-11-05", star: true })]);
check("only today's starred tasks are priorities", p.star.length === 2 && p.starDone === 1);
// A star belongs to its task's day (2026-11-05): tomorrow's stars have their own slots and never fill today's.
{
  const tm = "2026-11-05", ts = [task({ date: today, star: true }), task({ date: today, star: true }), task({ date: today, star: true }),
    task({ date: tm, star: true }), task({ date: tm }), task({ date: yd, star: true })];
  const me = M.mineModel(store(ts), today, "10:00");
  check("three stars today fill today only", M.starsOn(me, today).length === 3);
  check("tomorrow counts its own stars", M.starsOn(me, tm).length === 1);
  check("a past day's star is not today's", M.pulseCalc(me, store(ts), today).star.length === 3);
}
const hb = task({ title: "Read", date: "2026-10-01", repeat: { unit: "day", n: 1 }, habit: { start: "2026-10-01", remind: "auto" } });
p = calc([hb]);
check("habits are not tasks of the day, they have their own tile", p.today.length === 0 && p.hDue === 1 && p.hDone === 0);
check("a habit item is not a task item", !M.isTaskItem(M.mineModel({ tasks: [hb] }, today, "10:00").items[0]));

console.log(fails ? `\n${fails} failed` : "\nall passed");
process.exit(fails ? 1 : 0);
