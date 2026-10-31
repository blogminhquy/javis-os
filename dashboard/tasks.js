/* tasks.js - the Tasks page ("Nhiệm vụ", 0.422.0). Spec: docs/dev/2026-10-nhiem-vu-spec.md.
 *
 * One page replaces the old Kanban and Recurring work pages. Phase 1 draws the "Javis does" tab from data
 * the server already keeps: Kanban jobs, reminders, loops and page watches, plus incidents for the
 * "Run errors" list. Everything is merged in the browser by pure functions (`model`, tested under node);
 * `mount(el)` fetches, draws and wires the actions.
 *
 * Desktop: a sticky left column (smart lists, assistants) and the list on the right, a drawer for details.
 * Phone: TickTick style drill-down (home with the lists, a list screen, a detail screen), only the tab row sticks.
 */
(function () {
  "use strict";

  // ---------- small helpers ----------
  function tw(key, vars) {
    var s = (typeof window !== "undefined" && window.t) ? window.t(key, vars) : key;
    if (vars) s = String(s).replace(/\{(\w+)\}/g, function (m, k) { return Object.prototype.hasOwnProperty.call(vars, k) ? String(vars[k]) : m; });
    return s;
  }
  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function ic(name, cls) { return (typeof window !== "undefined" && window.ic) ? window.ic(name, cls ? { cls: cls } : undefined) : ""; }
  var pad2 = function (n) { return String(n).padStart(2, "0"); };
  function isoOf(d) { return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()); }
  function hmOf(d) { return pad2(d.getHours()) + ":" + pad2(d.getMinutes()); }
  function addDays(iso, n) { var d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return isoOf(d); }
  function LOC() { return (typeof window !== "undefined" && window.JavisI18n && window.JavisI18n.locale && window.JavisI18n.locale()) || "vi-VN"; }

  // ---------- model: merge the sources into items, recurring jobs and failures (pure) ----------
  var CORE = "javis-core";   // Javis Core's slug in GET /agents (server/javis_core.py SLUG)
  var FIN = { done: 1, cancel: 1 };

  function agentOf(card) {
    var m = card && card.metadata, a = m && m.agent;
    if (a && a.slug) return a.slug;
    var k = String((card && card.idempotency_key) || "");
    var mm = k.match(/^agent:([^:]+):/);
    return mm ? mm[1] : CORE;
  }
  // 0.429.0: a job a chatbot made belongs to the bot's assistant, or to the bot itself when that assistant is not in
  // this brain. src.bots is GET /tasks/bots ({bots, jobs: {"r:<id>"|"l:<slug>"|"k:<id>": bot id}}).
  function botWho(src) {
    var B = src.bots || {}, bots = {}, known = {}, jobs = B.jobs || {};
    (B.bots || []).forEach(function (b) { bots[b.id] = b; });
    (src.agents || []).forEach(function (a) { known[a.slug] = 1; });
    return function (key, createdBy) {
      var cb = String(createdBy || ""), b = bots[jobs[key] || (cb.indexOf("bot:") === 0 ? cb.slice(4) : "")];
      if (!b) return CORE;
      return b.agent && known[b.agent] ? b.agent : "bot:" + b.id;
    };
  }
  function kanbanState(c, now) {
    var s = c.status;
    if (s === "running") return "run";
    if (s === "review") return "ask";
    if (s === "blocked") {
      var k = c.block_kind || "";
      if (k === "needs_input" || k === "capability") return "ask";
      if (k === "cancelled") return "cancel";
      return "calm";
    }
    if (s === "done") return "done";
    if (s === "cancelled" || s === "archived") return "cancel";
    if (c.not_before && c.not_before > now) return "sched";
    return "queue";
  }
  function stamp(sec) {
    if (!sec) return { date: null, time: "" };
    var d = new Date(sec * 1000);
    return { date: isoOf(d), time: hmOf(d) };
  }
  function everyMin(m) {
    m = Number(m || 0);
    if (!m) return "";
    if (m % 1440 === 0) return m === 1440 ? tw("nv.rep.daily") : tw("nv.rep.every_days", { n: m / 1440 });
    if (m % 60 === 0) return m === 60 ? tw("nv.rep.hourly") : tw("nv.rep.every_hours", { n: m / 60 });
    return tw("nv.rep.every_min", { n: m });
  }
  function repText(r) {
    if (r.cron_human) return r.cron_human;
    return everyMin(r.repeat_min);
  }

  // sources: {kanban, viec, rems, watch, incidents, loopLog}. Returns {items, recurring, fails, log, ask, orch, waiting}.
  function model(src, nowSec) {
    var now = nowSec || Math.floor(Date.now() / 1000);
    var today = isoOf(new Date(now * 1000));
    var items = [], recurring = [], fails = [], log = [];
    var kb = src.kanban || {}, ops = kb.operations || {}, whoOf = botWho(src);
    var seen = {};
    ["active", "attention", "queue", "handled", "history"].forEach(function (k) {
      (ops[k] || []).forEach(function (c) {
        if (!c || seen[c.id]) return;
        seen[c.id] = 1;
        var st = kanbanState(c, now);
        // Finished: the day it finished. Open with a start time (not_before): that time, so one held past its time is overdue.
        var when = st === "done" || st === "cancel" ? (c.updated_at || c.created_at) : (c.not_before || 0);
        var ts = stamp(when);
        var md = c.metadata || {};
        var it = {
          id: "k:" + c.id, src: "kanban", ref: c.id, title: c.title || c.intent || "", desc: c.intent || "",
          who: agentOf(c) === CORE ? whoOf("k:" + c.id, c.created_by) : agentOf(c), st: st, date: ts.date || (FIN[st] ? null : today), time: ts.time, rep: "",
          result: c.result || "", reason: c.block_reason || "", blockKind: c.block_kind || "", status: c.status,
          needsApproval: !!c.needs_approval, took: Number(md.run_seconds || 0), at: when || c.created_at || 0, raw: c
        };
        items.push(it);
        if (st === "done" || st === "cancel") log.push({ at: it.at, title: it.title, text: it.result, who: it.who, ok: st === "done", ref: it.id });
        if (st === "calm" && (c.block_kind === "transient" || c.block_kind === "limit")) {
          fails.push({ id: "kf:" + c.id, ref: it.id, title: it.title, at: c.updated_at || now, why: c.block_reason || "", open: true, self: true });
        }
      });
    });
    var brains = (src.viec && src.viec.brains) || [];
    var brainPath = src.brain || "";
    var mine = brains.filter(function (b) { return !brainPath || b.path === brainPath || b.name === brainPath || (brainPath === "brain" && b.is_default); });
    if (!mine.length && brains.length) mine = brains.filter(function (b) { return b.is_default; });
    mine.forEach(function (b) {
      (b.reminders || []).forEach(function (r) {
        var rep = repText(r), paused = r.status === "paused", ts = stamp(r.due_at);
        var title = r.label || r.text || "";
        var mode = r.mode === "notify" ? "remind" : "do", rwho = whoOf("r:" + r.id);
        if (rep) {
          recurring.push({ id: "r:" + r.id, src: "reminder", ref: r.id, title: title, who: rwho, sc: rep, next: r.due_at || 0,
            on: !paused, running: !!r.running, mode: mode, raw: r });
        }
        if (paused) return;
        items.push({ id: "r:" + r.id, src: "reminder", ref: r.id, title: title, desc: r.text || "", who: rwho,
          st: r.running ? "run" : "sched", date: ts.date, time: ts.time, rep: rep, mode: mode,
          result: r.result || "", reason: r.error || "", at: r.due_at || 0, raw: r });
      });
      (b.loops || []).forEach(function (lp) {
        var paused = !!lp.auto_paused_reason, lwho = whoOf("l:" + lp.slug);
        recurring.push({ id: "l:" + lp.slug, src: "loop", ref: lp.slug, title: lp.name || lp.slug, who: lwho,
          sc: everyMin(lp.interval_min), next: lp.next_run || 0, on: !!lp.enabled && !paused,
          running: !!lp.running, mode: "do", raw: lp });
        if (lp.enabled && lp.next_run && !paused) {
          var t2 = stamp(lp.next_run);
          items.push({ id: "l:" + lp.slug, src: "loop", ref: lp.slug, title: lp.name || lp.slug, desc: "", who: lwho,
            st: lp.running ? "run" : "sched", date: t2.date, time: t2.time, rep: everyMin(lp.interval_min),
            mode: "do", result: lp.last_summary || "", reason: "", at: lp.next_run, raw: lp });
        }
        if (paused || Number(lp.fail_streak || 0) >= 2) {
          fails.push({ id: "lf:" + lp.slug, ref: "l:" + lp.slug, title: lp.name || lp.slug, at: lp.last_run || now,
            why: lp.auto_paused_reason || lp.last_status || "", open: true, self: !paused });
        }
      });
    });
    var hist = (src.rems && src.rems.history) || [];
    hist.forEach(function (r) {
      if (r.status !== "done" && r.status !== "failed") return;
      var ts = stamp(r.fired_at);
      var title = r.label || r.text || "", hwho = whoOf("r:" + r.id);
      if (r.status === "done") {
        items.push({ id: "rh:" + r.id, src: "reminder", ref: r.id, title: title, desc: r.text || "", who: hwho, st: "done",
          date: ts.date, time: ts.time, rep: "", mode: r.mode === "notify" ? "remind" : "do", result: r.result || "", reason: "",
          at: r.fired_at || 0, raw: r });
      }
      log.push({ at: r.fired_at || 0, title: title, text: r.result || r.error || "", who: hwho, ok: r.status === "done", ref: "rh:" + r.id });
      if (r.status === "failed") fails.push({ id: "rf:" + r.id, ref: "rh:" + r.id, title: title, at: r.fired_at || now, why: r.error || "", open: false });
    });
    ((src.watch && src.watch.watches) || []).forEach(function (w) {
      var on = w.status !== "paused";
      recurring.push({ id: "w:" + w.id, src: "watch", ref: w.id, title: w.title || w.url || "", who: CORE,
        sc: everyMin(w.interval_min), next: w.next_at || 0, on: on, running: false, mode: "do", raw: w });
      if (Number(w.fail_streak || 0) > 0) fails.push({ id: "wf:" + w.id, ref: "w:" + w.id, title: w.title || w.url || "", at: w.last_at || now, why: w.last_error || "", open: true, self: true });
    });
    ((src.incidents && src.incidents.incidents) || []).forEach(function (inc) {
      if (brainPath && inc.brain && inc.brain !== brainPath && !String(brainPath).endsWith(String(inc.brain))) return;
      var open = inc.status !== "resolved";
      fails.push({ id: "i:" + inc.id, ref: "", inc: inc.id, title: inc.title || inc.source || "", at: inc.last_at || inc.at || now,
        why: inc.message || inc.error || "", open: open, needYou: inc.status === "needs_you" });
    });
    ((src.loopLog && src.loopLog.entries) || []).forEach(function (e) {
      var m = String(e).match(/^##\s*\[([^\]]+)\]\s*([^\n]*)\n?([\s\S]*)$/);
      if (m) log.push({ at: 0, when: m[1], title: m[2], text: m[3].trim(), who: whoOf("l:" + m[2].split(" \u00b7 ")[0].trim()), ok: !/l\u1ed7i|error/i.test(m[2]), ref: "" });
    });
    // Overdue: a job that should have started before today and has not.
    items.forEach(function (it) { it.over = !FIN[it.st] && it.st !== "run" && !!it.date && it.date < today; });
    fails.sort(function (a, b) { return b.at - a.at; });
    log.sort(function (a, b) { return (b.at || 0) - (a.at || 0); });
    var ask = items.filter(function (i) { return i.st === "ask"; });
    var orch = kb.orchestration || "off";
    var waiting = items.filter(function (i) { return i.src === "kanban" && i.st === "queue"; }).length;
    return { items: items, recurring: recurring, fails: fails, log: log, ask: ask, orch: orch, waiting: waiting, today: today, now: now };
  }

  // Which list an item belongs to, by list id (pure).
  function inList(it, list, today) {
    if (list === "all") return !FIN[it.st];
    if (list === "nodate") return !FIN[it.st] && !it.date;
    if (list.indexOf("proj:") === 0) return it.proj === list.slice(5) && !FIN[it.st];
    if (list === "today") return it.date === today;
    if (list === "week") return !FIN[it.st] && !!it.date && it.date > today && it.date <= addDays(today, 8);
    if (list === "over") return !!it.over;
    if (list === "done") return FIN[it.st] && it.st === "done";
    if (list.indexOf("who:") === 0) return it.who === list.slice(4) && !FIN[it.st];
    return false;
  }
  function byTime(a, b) {
    var ka = (a.date || "9999") + (a.time || "99"), kb = (b.date || "9999") + (b.time || "99");
    return ka < kb ? -1 : ka > kb ? 1 : 0;
  }
  // Recurring jobs on the user's day timeline: by next run, switched off last.
  function byTimeline(list) {
    return list.slice().sort(function (a, b) {
      var ka = (a.on ? "a" : "z") + String(a.next || 9e12).padStart(14, "0"), kb = (b.on ? "a" : "z") + String(b.next || 9e12).padStart(14, "0");
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
  }
  // How a Javis job is scheduled on the server from the repeat picker (pure): a cron where cron can say it,
  // otherwise a fixed step (repeat_min) from a start time. rule = {unit: min|hour|day|week|month|year, n, days}.
  function javisSchedule(rule, date, time) {
    var hm = String(time || "08:00").split(":"), h = Number(hm[0]) || 0, m = Number(hm[1]) || 0;
    var at = (date || isoOf(new Date())) + "T" + pad2(h) + ":" + pad2(m);
    if (!rule) return { at: at };
    var n = Math.max(1, rule.n || 1), d = new Date((date || isoOf(new Date())) + "T12:00:00");
    if (rule.unit === "min") return { repeat_min: n, at: at };
    if (rule.unit === "hour") return { repeat_min: n * 60, at: at };
    if (rule.unit === "day") return n === 1 ? { cron: m + " " + h + " * * *" } : { repeat_min: n * 1440, at: at };
    if (rule.unit === "week") {
      var days = rule.days && rule.days.length ? rule.days.slice().sort() : [d.getDay()];
      return n === 1 ? { cron: m + " " + h + " * * " + days.join(",") } : { repeat_min: n * 7 * 1440, at: at };
    }
    if (rule.unit === "month") return { cron: m + " " + h + " " + d.getDate() + " " + (n === 1 ? "*" : "*/" + n) + " *" };
    if (rule.unit === "year") return { cron: m + " " + h + " " + d.getDate() + " " + (d.getMonth() + 1) + " *" };
    return { at: at };
  }
  // A cron expression from the simple repeat choice of the add form (pure).
  function cronFor(rep, date, time) {
    var hm = String(time || "08:00").split(":"), h = Number(hm[0]) || 0, m = Number(hm[1]) || 0;
    var d = date ? new Date(date + "T12:00:00") : new Date();
    if (rep === "daily") return m + " " + h + " * * *";
    if (rep === "weekdays") return m + " " + h + " * * 1-5";
    if (rep === "weekly") return m + " " + h + " * * " + d.getDay();
    if (rep === "monthly") return m + " " + h + " " + d.getDate() + " * *";
    return "";
  }

  // ---------- the owner's own tasks (tab "Mine", 0.423.0) ----------
  function dayNum(iso) { return Math.round(new Date(iso + "T12:00:00Z").getTime() / 86400000); }
  function wdOf(iso) { return new Date(iso + "T12:00:00Z").getUTCDay(); }
  // Whether a repeat rule {unit, n, days} anchored on `start` falls on day `iso` (pure).
  function occursOn(rep, start, iso) {
    if (!rep || !start || iso < start) return false;
    var n = Math.max(1, rep.n || 1), d0 = dayNum(start), d = dayNum(iso);
    if (rep.unit === "day") return (d - d0) % n === 0;
    if (rep.unit === "week") {
      var days = rep.days && rep.days.length ? rep.days : [wdOf(start)];
      if (days.indexOf(wdOf(iso)) < 0) return false;
      var w0 = Math.floor((d0 + 3) / 7), w = Math.floor((d + 3) / 7);   // weeks start on Monday
      return (w - w0) % n === 0;
    }
    var s = start.split("-").map(Number), x = iso.split("-").map(Number);
    // A day that a month does not have (the 31st, Feb 29) falls on that month's last day.
    var last = new Date(Date.UTC(x[0], x[1], 0)).getUTCDate(), dayOk = s[2] === x[2] || (s[2] > last && x[2] === last);
    if (rep.unit === "month") return dayOk && ((x[0] - s[0]) * 12 + (x[1] - s[1])) % n === 0;
    if (rep.unit === "year") return s[1] === x[1] && dayOk && (x[0] - s[0]) % n === 0;
    return false;
  }
  function nextOcc(rep, start, from) {
    for (var i = 0, d = from < start ? start : from; i < 800; i++, d = addDays(d, 1)) if (occursOn(rep, start, d)) return d;
    return null;
  }
  // The latest occurrence before `today`, or null (pure).
  function prevOcc(rep, start, today) {
    for (var i = 0, d = addDays(today, -1); i < 800 && d >= start; i++, d = addDays(d, -1)) if (occursOn(rep, start, d)) return d;
    return null;
  }
  // Literal keys (the i18n test reads them from the source): weekday short names 0 = Sunday, and repeat units.
  var WD_KEYS = ["nv.wd.sun", "nv.wd.mon", "nv.wd.tue", "nv.wd.wed", "nv.wd.thu", "nv.wd.fri", "nv.wd.sat"];
  var RP_KEYS = { min: "nv.rp.u_min", hour: "nv.rp.u_hour", day: "nv.rp.u_day", week: "nv.rp.u_week", month: "nv.rp.u_month", year: "nv.rp.u_year" };
  function repHuman(rep, time) {
    if (!rep) return "";
    var n = rep.n || 1, at = time ? " " + tw("nv.rep.at", { t: time }) : "", s;
    if (rep.unit === "day") s = n === 1 ? tw("nv.rep.daily") : tw("nv.rep.every_days", { n: n });
    else if (rep.unit === "week") {
      var names = (rep.days || []).slice().sort(function (a, b) { return ((a + 6) % 7) - ((b + 6) % 7); }).map(function (d) { return tw(WD_KEYS[d]); });
      s = (n === 1 ? tw("nv.rep.weekly") : tw("nv.rep.every_weeks", { n: n })) + (names.length ? " (" + names.join(", ") + ")" : "");
    } else if (rep.unit === "month") s = n === 1 ? tw("nv.rep.monthly") : tw("nv.rep.every_months", { n: n });
    else s = n === 1 ? tw("nv.rep.yearly") : tw("nv.rep.every_years", { n: n });
    return s + at;
  }
  // Items for the "Mine" tab from GET /my-tasks (pure). A repeating task gives its next occurrence from today,
  // plus its latest missed occurrence (overdue, tickable) when that one was not done.
  // An appointment on `date` from `time` to `end`: "past" once it ended, "live" while it runs, else "todo" (pure).
  function apptState(date, time, end, today, nowHM) {
    if (!date || date < today) return date ? "past" : "todo";
    if (date > today) return "todo";
    if (end && nowHM >= end) return "past";
    if (time && nowHM >= time) return "live";
    return "todo";
  }
  function mineModel(store, today, nowHM) {
    var items = [], recurring = [], hm = nowHM || "00:00";
    var start = function (t) { return t.date || (t.created_at ? isoOf(new Date(t.created_at * 1000)) : today); };
    ((store && store.tasks) || []).forEach(function (t) {
      var base = { src: "mine", ref: t.id, title: t.title, desc: t.notes || "", who: "me", proj: t.project || "", time: t.time || "",
        kind: t.kind || "task", fromJavis: !!t.from_javis, raw: t, end: t.end || "" };
      if (t.kind === "appt") {
        // Appointments are not ticked: they turn "past" on their own once their time is over.
        var first = t.repeat ? nextOcc(t.repeat, start(t), today) : t.date;
        var occs = [first];
        if (t.repeat && first === today && apptState(today, t.time, t.end, today, hm) === "past") occs.push(nextOcc(t.repeat, start(t), addDays(today, 1)));
        occs.forEach(function (d, i) {
          if (!d) return;
          var as = apptState(d, t.time, t.end, today, hm);
          items.push(Object.assign({}, base, { id: i || !t.repeat ? (i ? "mn:" + t.id + ":" + d : "m:" + t.id) : (d === today ? "m:" + t.id : "mn:" + t.id + ":" + d),
            date: d, st: as === "past" ? "done" : "todo", live: as === "live", appt: true, rep: t.repeat ? repHuman(t.repeat) : "", occ: d, over: false }));
        });
        if (t.repeat) recurring.push(Object.assign({}, base, { id: "m:" + t.id, sc: repHuman(t.repeat, t.time), nextDate: first, on: true, appt: true, habit: false }));
        return;
      }
      if (!t.repeat) {
        var done = t.status === "done";
        items.push(Object.assign({}, base, { id: "m:" + t.id, date: t.date || null, st: done ? "done" : t.status === "cancelled" ? "cancel" : "todo",
          doneAt: t.done_at || 0, over: !done && !!t.date && t.date < today && t.kind !== "appt" }));
        return;
      }
      var st0 = start(t), dd = t.done_dates || {};
      var next = nextOcc(t.repeat, st0, today);
      recurring.push(Object.assign({}, base, { id: "m:" + t.id, sc: repHuman(t.repeat, t.time), nextDate: next, on: true,
        habit: !!(t.habit && !t.habit.off), doneToday: !!dd[today], sched: occursOn(t.repeat, st0, today) }));
      // Today's occurrence keeps the task's own id (its row ticks today); a later one gets its own id with its date.
      if (next) items.push(Object.assign({}, base, { id: next === today ? "m:" + t.id : "mn:" + t.id + ":" + next, date: next, st: next === today && dd[today] ? "done" : "todo",
        rep: repHuman(t.repeat), occ: next, over: false }));
      var miss = prevOcc(t.repeat, st0, today);
      if (miss && !dd[miss] && t.kind !== "appt") items.push(Object.assign({}, base, { id: "mo:" + t.id + ":" + miss, date: miss, st: "todo",
        rep: repHuman(t.repeat), occ: miss, over: true }));
      Object.keys(dd).forEach(function (d) {
        if (d !== today) items.push(Object.assign({}, base, { id: "md:" + t.id + ":" + d, date: d, st: "done", rep: repHuman(t.repeat), occ: d, doneAt: dd[d].at || 0, over: false }));
      });
    });
    // 0.427.0: read-only events from a connected Google Calendar sit next to the appointments.
    ((store && store.gcal) || []).forEach(function (e) {
      var c = calWhen(e);
      if (!c.date) return;
      var as = apptState(c.date, c.time, c.end, today, hm);
      items.push({ id: "g:" + e.id, src: "gcal", ref: e.id, title: e.title, desc: "", who: "me", proj: "", time: c.time, end: c.end, kind: "appt",
        raw: { location: e.location || "", link: e.link || "", source: e.source || "", all_day: !!e.all_day }, appt: true, gcal: true,
        date: c.date, st: as === "past" ? "done" : "todo", live: as === "live", rep: "", occ: c.date, over: false });
    });
    return { items: items, recurring: recurring };
  }
  // Local date and times of a calendar event: an all-day one has no time, a timed one is read in the browser's zone.
  function calWhen(e) {
    if (e.all_day || /^\d{4}-\d{2}-\d{2}$/.test(e.start || "")) return { date: String(e.start || "").slice(0, 10), time: "", end: "" };
    var a = new Date(e.start), b = e.end ? new Date(e.end) : null;
    if (isNaN(a)) return { date: "", time: "", end: "" };
    var endHm = b && !isNaN(b) ? (isoOf(b) === isoOf(a) ? hmOf(b) : "23:59") : "";
    return { date: isoOf(a), time: hmOf(a), end: endHm };
  }

  // ---------- habits (0.424.0) ----------
  // A habit is a repeating task of mine with `habit` set. Only SCHEDULED days count: a day the repeat does not fall
  // on is a rest day (no freeze, no break, no count). One missed session freezes the streak; a second missed
  // session in a row loses it; doing the next session thaws it. Weekly once is then counted by weeks, monthly by months.
  function habitOn(t) { return !!(t && t.repeat && t.habit && !t.habit.off); }
  function habitCalc(t, today) {
    if (!t || !t.repeat || !t.habit) return null;
    var anchor = t.date || t.habit.start || today, from = t.habit.start && t.habit.start > anchor ? t.habit.start : anchor;
    var dd = t.done_dates || {}, days = {}, cur = 0, best = 0, miss = 0, prev = null;
    for (var i = 0, d = from; i < 1500 && d <= today; i++, d = addDays(d, 1)) {
      if (!occursOn(t.repeat, anchor, d)) { days[d] = "r"; continue; }
      if (d === today && !dd[d]) { days[d] = "todo"; break; }
      if (dd[d]) { cur++; miss = 0; days[d] = "f"; }
      else if (++miss === 1) days[d] = "i";
      else { days[d] = "x"; if (prev && days[prev] === "i") days[prev] = "x"; cur = 0; }
      if (cur > best) best = cur;
      prev = d;
    }
    var rest = days[today] === "r", last = prev && prev !== today ? prev : null;
    return { cur: cur, best: best, days: days, rest: rest, last: last, next: nextOcc(t.repeat, anchor, addDays(today, 1)), anchor: anchor,
      frozen: !!(last && days[last] === "i" && (days[today] === "todo" || rest)), doneToday: days[today] === "f", by: dd };
  }
  // The time of day the owner usually ticks it (median of the last 30 ticks), "" when there are fewer than 3.
  function usualTime(t) {
    var ats = Object.keys(t.done_dates || {}).sort().slice(-30).map(function (k) { return Number((t.done_dates[k] || {}).at || 0); })
      .filter(function (x) { return x > 0; }).map(function (x) { var d = new Date(x * 1000); return d.getHours() * 60 + d.getMinutes(); }).sort(function (a, b) { return a - b; });
    if (ats.length < 3) return "";
    var m = ats[Math.floor(ats.length / 2)];
    return pad2(Math.floor(m / 60)) + ":" + pad2(m % 60);
  }
  var MILES = [7, 14, 30, 50, 100, 200, 365, 500, 1000];
  // The head of the Habits list: today x/y, frozen, longest streak, this week's rate, and the mascot's lines (pure).
  function habitStats(tasks, today) {
    var H = (tasks || []).filter(habitOn), wd = (new Date(today + "T12:00:00").getDay() + 6) % 7, mon = addDays(today, -wd);
    var due = 0, done = 0, ice = 0, wkDone = 0, wkAll = 0, top = null, rest = [];
    H.forEach(function (t) {
      var k = habitCalc(t, today);
      if (k.rest && !k.frozen) rest.push(t);
      if (!k.rest) due++;
      if (k.doneToday) done++;
      if (k.frozen) ice++;
      if (!top || k.cur > top.k.cur) top = { t: t, k: k };
      for (var d = mon; d <= today; d = addDays(d, 1)) { var st = k.days[d]; if (!st || st === "todo" || st === "r") continue; wkAll++; if (st === "f") wkDone++; }
    });
    return { H: H, due: due, done: done, ice: ice, top: top, rest: rest, wk: wkAll ? Math.round(wkDone * 100 / wkAll) : 0 };
  }
  // The mascot's lines. 0.427.0: today's lines written by Core (GET /my-tasks `coach`) win over the fixed ones; they
  // carry {placeholders} filled here with the live numbers, so a line stays true as ticks come in during the day.
  function fillLine(s, v) { return String(s).replace(/\{(\w+)\}/g, function (m, k) { return v[k] != null ? String(v[k]) : m; }); }
  function habitLines(st, today, coach) {
    var M = [], short = function (s) { return String(s).replace(/\s+\d+\s*\S+$/, "").toLowerCase(); };
    var C = coach && coach.date === today ? coach : null, H = (C && C.head) || {}, CH = (C && C.habits) || {};
    var say = function (key, k, v) { return H[key] ? fillLine(H[key], v) : tw(k, v); };
    st.H.forEach(function (t) {
      var k = habitCalc(t, today);
      if (!k.frozen) return;
      var v = { name: short(t.title), last: dayWord(k.last, today), next: k.rest ? dayWord(k.next, today) : tw("nv.d.today_low"), n: k.cur };
      M.push({ mood: "suspicious", tx: CH[t.id] && CH[t.id].frozen ? fillLine(CH[t.id].frozen, v) : tw("nv.h.say.frozen", v) });
    });
    if (st.due && st.done === st.due) M.push({ mood: "love", tx: say("all", "nv.h.say.all", { n: st.due }) });
    else if (st.done) M.push({ mood: "excited", tx: say("part", "nv.h.say.part", { done: st.done, due: st.due, left: st.due - st.done }) });
    if (st.top && st.top.k.cur) {
      var nx = MILES.find(function (m) { return m > st.top.k.cur; });
      if (nx) M.push({ mood: nx - st.top.k.cur <= 3 ? "gang" : "wink", tx: say("mile", "nv.h.say.mile", { left: nx - st.top.k.cur, name: short(st.top.t.title), n: nx }) });
    }
    if (st.rest.length) M.push({ mood: "sleepy", tx: say("rest", "nv.h.say.rest", { names: st.rest.map(function (t) { return short(t.title); }).join(", ") }) });
    if (st.wk >= 80) M.push({ mood: "happy", tx: say("week", "nv.h.say.week", { n: st.wk }) });
    if (!M.length) M.push({ mood: "curious", tx: say("start", "nv.h.say.start", {}) });
    return M;
  }
  function dayWord(iso, today) {
    if (!iso) return "";
    if (iso === today) return tw("nv.d.today_low");
    if (iso === addDays(today, -1)) return tw("nv.d.yday_low");
    if (iso === addDays(today, 1)) return tw("nv.d.tom_low");
    return tw(WD_KEYS[new Date(iso + "T12:00:00").getDay()]) + " " + Number(iso.slice(8)) + "/" + Number(iso.slice(5, 7));
  }

  var model_ = { apptState: apptState, habitCalc: habitCalc, habitStats: habitStats, habitLines: habitLines, usualTime: usualTime, model: model, mineModel: mineModel, occursOn: occursOn, nextOcc: nextOcc, prevOcc: prevOcc, repHuman: repHuman, inList: inList, byTime: byTime, byTimeline: byTimeline, cronFor: cronFor, javisSchedule: javisSchedule, kanbanState: kanbanState, addDays: addDays };
  if (typeof module !== "undefined" && module.exports) { module.exports = model_; return; }

  // ---------- page ----------
  var LISTS_AI = [["all", "list", "nv.l.all", "c-all"], ["today", "sun", "nv.l.today", "c-today"], ["week", "calendar", "nv.l.week", "c-week"],
    ["over", "clock-alert", "nv.l.over", "c-over"], ["rep", "repeat", "nv.l.rep", "c-rep"], ["err", "triangle-alert", "nv.l.err", "c-err"],
    ["done", "circle-check", "nv.l.done", "c-done"], ["log", "scroll-text", "nv.l.log", "c-log"]];
  var LISTS_ME = [["all", "list", "nv.l.all", "c-all"], ["today", "sun", "nv.l.today", "c-today"], ["week", "calendar", "nv.l.week", "c-week"],
    ["over", "clock-alert", "nv.l.over", "c-over"], ["nodate", "inbox", "nv.l.nodate", "c-nodate"], ["rep", "repeat", "nv.l.rep", "c-rep"],
    ["habit", "flame", "nv.l.habit", "c-habit"], ["done", "circle-check", "nv.l.done", "c-done"]];
  var COLORS = ["#ef4444", "#f97316", "#eab308", "#22c55e", "#14b8a6", "#3b82f6", "#8b5cf6", "#ec4899", "#64748b"];
  var PAGE = 6;
  var LS = "javis.nv.";
  function lsGet(k, d) { try { var v = localStorage.getItem(LS + k); return v == null ? d : v; } catch (e) { return d; } }
  function lsSet(k, v) { try { localStorage.setItem(LS + k, v); } catch (e) { /* private mode */ } }

  var S = null;   // page state, one mounted page at a time

  function brain() { return (typeof window !== "undefined" && window.currentBrainPath) ? window.currentBrainPath() : "brain"; }
  async function getJSON(url) {
    try { var r = await fetch(url, { cache: "no-store" }); return r.ok ? await r.json() : null; } catch (e) { return null; }
  }
  async function postForm(url, fields) {
    var fd = new FormData();
    Object.keys(fields || {}).forEach(function (k) { if (fields[k] != null) fd.append(k, fields[k]); });
    try { var r = await fetch(url, { method: "POST", body: fd }); return await r.json(); } catch (e) { return { ok: false, error: String(e) }; }
  }
  async function postJSON(url, body) {
    try { var r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); return await r.json(); }
    catch (e) { return { ok: false, error: String(e) }; }
  }
  function mine(body) { return postJSON(body.__url, Object.assign({ brain: brain() }, body, { __url: undefined })); }

  async function load() {
    var b = brain(), enc = encodeURIComponent(b);
    var res = await Promise.all([
      getJSON("/kanban?brain=" + enc + "&history=40"), getJSON("/viec/all"), getJSON("/reminders?brain=" + enc),
      getJSON("/watch?brain=" + enc), getJSON("/incidents?limit=50"), getJSON("/loops/log?brain=" + enc + "&limit=60"),
      S.agents ? Promise.resolve(null) : getJSON("/agents?brain=" + enc + "&prompt=0&system=1"),
      getJSON("/my-tasks?brain=" + enc), getJSON("/tasks/bots?brain=" + enc)
    ]);
    if (res[6]) S.agents = (res[6].agents || res[6] || []).filter(function (a) { return a && a.slug; });
    S.brains = ((res[1] && res[1].brains) || []).map(function (x) { return { name: x.label || x.name, path: x.path, def: x.is_default }; });
    S.notify = (res[2] && res[2].notify) || {};
    if (res[8]) S.bots = res[8];
    S.ai = model({ kanban: res[0] || {}, viec: res[1] || {}, rems: res[2] || {}, watch: res[3] || {}, incidents: res[4] || {}, loopLog: res[5] || {}, brain: b,
      bots: S.bots || {}, agents: S.agents || [] });
    S.my = res[7] && res[7].ok ? res[7] : (S.my || { tasks: [], projects: [] });
    S.me = mineModel(Object.assign({}, S.my, { gcal: S.gcal || [] }), S.ai.today, hmOf(new Date()));
    if (!S.calAt || Date.now() - S.calAt > 300000) { S.calAt = Date.now(); loadCal(); }
    applyHidden();
    S.loaded = true;
  }
  // 0.427.0: Google Calendar events (read-only) arrive after the page is up, then the Mine lists redraw.
  async function loadCal() {
    var r = await getJSON("/my-tasks/calendar?brain=" + encodeURIComponent(brain()) + "&days=14");
    if (!S || !r || !r.connected) return;
    S.gcal = r.events || [];
    S.me = mineModel(Object.assign({}, S.my, { gcal: S.gcal }), S.ai.today, hmOf(new Date()));
    applyHidden();
    render();
  }
  // The model of the open tab: the "Mine" lists or the "Javis does" lists.
  function M() { return S.tab === "me" ? S.me : S.ai; }
  function today() { return S.ai.today; }
  // Items removed with "undo" still pending stay hidden until the server confirms.
  function applyHidden() {
    var h = S.hidden;
    [S.ai, S.me].forEach(function (m) {
      if (!m) return;
      m.items = m.items.filter(function (i) { return !h[i.id] && !h[i.id.split(":").slice(0, 2).join(":")]; });
      m.recurring = m.recurring.filter(function (r) { return !h[r.id]; });
    });
  }

  function schedulePoll() {
    clearTimeout(S.poll);
    var busy = S.ai && (S.ai.items.some(function (i) { return i.st === "run"; }) || S.ai.recurring.some(function (r) { return r.running; }));
    S.poll = setTimeout(async function () {
      if (!S || !document.body.contains(S.root)) return;
      if (document.hidden || S.sheet || S.layer || S.sel || (window.JavisTaskStats && window.JavisTaskStats.isEditing())) { schedulePoll(); return; }
      await load(); render(); schedulePoll();
    }, busy ? 5000 : 30000);
  }

  // ---------- toast + undo ----------
  var toastT = null;
  function toast(msg, undo) {
    var t = document.querySelector(".nv-toast");
    if (!t) { t = document.createElement("div"); t.className = "nv-toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
    t.innerHTML = esc(msg) + (undo ? ' <button type="button" class="nv-undo">' + esc(tw("nv.undo")) + "</button>" : "");
    t.hidden = false;
    var b = t.querySelector(".nv-undo");
    if (b) b.onclick = function () { t.hidden = true; undo(); };
    clearTimeout(toastT);
    toastT = setTimeout(function () { t.hidden = true; }, undo ? 6000 : 3500);
  }
  // Actions the server cannot take back wait 6 s so "Undo" can cancel them before the server is told.
  function later(id, msg, commit) {
    S.hidden[id] = 1; applyHidden(); render();
    var done = false;
    var timer = setTimeout(async function () { done = true; var r = await commit(); delete S.hidden[id]; if (r && r.ok === false) toast(r.error || tw("nv.err.generic")); await load(); render(); }, 6000);
    toast(msg, function () { if (done) return; clearTimeout(timer); delete S.hidden[id]; load().then(render); });
  }
  async function act(promise, okMsg, undo) {
    var r = await promise;
    if (r && r.ok === false) { toast(r.error || tw("nv.err.generic")); return r; }
    await load(); render(); schedulePoll();
    if (okMsg) toast(okMsg, undo ? function () { Promise.resolve(undo(r)).then(function () { return load(); }).then(render); } : null);
    return r;
  }

  // ---------- pieces ----------
  function botOf(slug) {
    var id = String(slug || "").indexOf("bot:") === 0 ? slug.slice(4) : "";
    return id ? ((S.bots && S.bots.bots) || []).find(function (b) { return b.id === id; }) || { id: id, name: id } : null;
  }
  function agentName(slug) {
    if (slug === CORE) return "Javis Core";
    if (slug === "me") return tw("nv.me");
    if (botOf(slug)) return botOf(slug).name;
    var a = (S.agents || []).find(function (x) { return x.slug === slug; });
    return a ? (a.name || slug) : slug;
  }
  function avatar(slug, size) {
    var bt = botOf(slug), px = size || 18;
    if (bt) return '<span class="nv-av nv-botav" style="width:' + px + "px;height:" + px + 'px">' + ic(bt.icon || "headset") + "</span>";
    var a = (S.agents || []).find(function (x) { return x.slug === slug; }) || { slug: slug };
    if (window.JavisAvatar && window.JavisAvatar.html) {
      try { return window.JavisAvatar.html(a, size || 18, "idle"); } catch (e) { /* fall through */ }
    }
    return '<span class="nv-av" style="width:' + (size || 18) + "px;height:" + (size || 18) + 'px"></span>';
  }
  function proj(id) { return ((S.my && S.my.projects) || []).find(function (p) { return p.id === id; }) || null; }
  function projTag(id) { var p = proj(id); return p ? '<span><i class="nv-dot" style="background:' + esc(p.color) + '"></i>' + esc(p.name) + "</span>" : ""; }
  function dayLabel(iso) {
    var t = today();
    if (iso === t) return tw("nv.d.today");
    if (iso === addDays(t, 1)) return tw("nv.d.tom");
    if (iso === addDays(t, -1)) return tw("nv.d.yday");
    var d = new Date(iso + "T12:00:00");
    return d.toLocaleDateString(LOC(), { weekday: "long", day: "numeric", month: "numeric" });
  }
  function shortDate(iso) { var d = new Date(iso + "T12:00:00"); return d.getDate() + "/" + (d.getMonth() + 1); }
  function whenText(sec) { var d = new Date(sec * 1000); return dayLabel(isoOf(d)) + ", " + hmOf(d); }
  function whenIso(date, time) { return date ? dayLabel(date) + (time ? ", " + time : ", " + tw("nv.f.no_time_low")) : tw("nv.d.none"); }
  function stIcon(it) {
    if (it.st === "run") return ic("loader-circle", "nv-spin c-run");
    if (it.st === "ask") return ic("circle-alert", "c-ask");
    if (it.st === "calm") return ic("hourglass", "c-calm");
    if (it.st === "done") return ic("circle-check", "c-ok");
    if (it.st === "cancel") return ic("circle-x", "c-mute");
    return '<span class="nv-ring"></span>';
  }
  function ck(it) {
    if (it.st === "done") return '<span class="nv-ck on" data-act="uncheck" data-id="' + esc(it.id) + '" role="checkbox" aria-checked="true" tabindex="0" aria-label="' + esc(tw("nv.a.uncheck")) + '">' + ic("check") + "</span>";
    return '<span class="nv-ck" data-act="check" data-id="' + esc(it.id) + '" role="checkbox" aria-checked="false" tabindex="0" aria-label="' + esc(tw("nv.a.check", { t: it.title })) + '"></span>';
  }
  function chip(it) {
    if (it.over) return '<span class="nv-chip c-over">' + esc(tw("nv.st.over", { d: shortDate(it.date) })) + "</span>";
    var k = { run: "nv.st.run", ask: "nv.st.ask", calm: "nv.st.calm", queue: "nv.st.queue", cancel: "nv.st.cancel" }[it.st];
    return k ? '<span class="nv-chip s-' + it.st + '">' + esc(tw(k)) + "</span>" : "";
  }
  function meta(it) {
    var parts = [];
    if (it.rep) parts.push(ic("repeat") + esc(it.rep));
    else if (it.mode === "remind") parts.push(ic("bell") + esc(tw("nv.mode.remind")));
    if (it.src === "mine") {
      if (it.fromJavis) parts.push(avatar(CORE, 14) + esc(tw("nv.from_javis")));
      if (it.proj && S.view !== "proj:" + it.proj) { var pt = projTag(it.proj); if (pt) parts.push(pt.replace(/^<span>|<\/span>$/g, "")); }
    } else parts.push(avatar(it.who, 14) + esc(agentName(it.who)));
    if (it.took) parts.push(esc(tw("nv.took", { n: Math.max(1, Math.round(it.took / 60)) })));
    return parts.length ? '<div class="nv-meta">' + parts.map(function (p) { return "<span>" + p + "</span>"; }).join("") + "</div>" : "";
  }
  function runBtn(it, phone) {
    if (it.src === "mine" || it.src === "gcal") return "";
    var cls = phone ? "nv-go" : "nv-rgo";
    if (it.st === "run") return '<button type="button" class="' + cls + ' busy" data-act="stop" data-id="' + esc(it.id) + '" aria-label="' + esc(tw("nv.a.stop")) + '" title="' + esc(tw("nv.a.stop_t")) + '">' + ic("square") + "</button>";
    if (FIN[it.st] || it.st === "ask") return "";
    return '<button type="button" class="' + cls + '" data-act="run" data-id="' + esc(it.id) + '" aria-label="' + esc(tw("nv.a.run")) + '" title="' + esc(tw("nv.a.run_t")) + '">' + ic("play") + "</button>";
  }
  function apptColor(it) { if (it.gcal) return "#4285f4"; var p = proj(it.proj); return p ? p.color : "var(--accent)"; }
  function overlaps(it) {
    if (!it.appt || it.st === "done" || !it.time || !it.end) return false;
    return S.me.items.some(function (o) { return o !== it && o.appt && o.st !== "done" && o.date === it.date && o.time && o.end && o.time < it.end && it.time < o.end; });
  }
  function apptChip(it) {
    if (it.live) return '<span class="nv-chip s-run">' + esc(tw("nv.ap.live")) + "</span>";
    if (it.st === "done") return '<span class="nv-chip">' + esc(tw("nv.ap.past")) + "</span>";
    if (overlaps(it)) return '<span class="nv-chip s-ask">' + esc(tw("nv.ap.clash")) + "</span>";
    return "";
  }
  function row(it) {
    if (it.appt) {
      var t = it.raw;
      return '<div class="nv-rw"><button type="button" class="nv-row appt' + (it.st === "done" ? " done" : "") + (it.live ? " live" : "") + (S.sel === it.id ? " sel" : "") + '" data-open="' + esc(it.id) + '">'
        + '<span class="nv-tm">' + esc(it.time || (it.gcal ? tw("nv.g.allday") : "")) + (it.end ? "<small>" + esc(it.end) + "</small>" : "") + '</span><span class="nv-st"><i class="nv-abar" style="background:' + esc(apptColor(it)) + '"></i></span>'
        + '<span class="nv-body"><span class="nv-ti">' + esc(it.title) + '</span><div class="nv-meta">' + (it.gcal ? "<span>" + ic("calendar") + esc(tw("nv.g.src")) + "</span>" : "") + (t.location ? "<span>" + ic("map-pin") + esc(t.location) + "</span>" : "")
        + (it.rep ? "<span>" + ic("repeat") + esc(it.rep) + "</span>" : "") + (t.remind && t.remind !== "0" ? "<span>" + ic("bell") + esc(tw("nv.ap.before", { n: t.remind })) + "</span>" : "")
        + (t.prep ? "<span>" + avatar(CORE, 14) + esc(tw("nv.ap.prep_short")) + "</span>" : "") + (it.proj && S.view !== "proj:" + it.proj ? projTag(it.proj) : "") + "</div></span>"
        + '<span class="nv-chipcol">' + apptChip(it) + "</span></button>"
        + '<button type="button" class="nv-dots" data-act="menu" data-id="' + esc(it.id) + '" aria-label="' + esc(tw("nv.a.more")) + '">' + ic("ellipsis") + "</button></div>";
    }
    var time = it.over ? '<span class="c-over">' + esc(shortDate(it.date)) + "</span>" + (it.time ? "<small>" + esc(it.time) + "</small>" : "") : esc(it.time || "");
    var lead = it.src === "mine" ? (habitOn(it.raw) && it.id === "m:" + it.raw.id ? habitCk(it.raw) : ck(it)) : stIcon(it);
    return '<div class="nv-rw"><button type="button" class="nv-row' + (FIN[it.st] ? " done" : "") + (S.sel === it.id ? " sel" : "") + '" data-open="' + esc(it.id) + '">'
      + '<span class="nv-tm">' + time + '</span><span class="nv-st">' + lead + "</span>"
      + '<span class="nv-body"><span class="nv-ti">' + esc(it.title) + "</span>" + meta(it)
      + (it.st === "ask" && it.reason ? '<span class="nv-note c-ask">' + esc(it.reason) + "</span>" : "")
      + (it.st === "calm" && it.reason ? '<span class="nv-note">' + esc(it.reason) + "</span>" : "") + "</span>"
      + '<span class="nv-chipcol">' + chip(it) + "</span></button>"
      + runBtn(it) + '<button type="button" class="nv-dots" data-act="menu" data-id="' + esc(it.id) + '" aria-label="' + esc(tw("nv.a.more")) + '">' + ic("ellipsis") + "</button></div>";
  }
  function repRow(r, phone) {
    var lead, nx, sw = "";
    if (r.src === "mine" && r.appt) {
      lead = '<i class="nv-abar" style="background:' + esc(apptColor(r)) + '"></i>';
      nx = r.nextDate ? tw("nv.rep.next", { t: whenIso(r.nextDate, r.time) }) : "";
    } else if (r.src === "mine") {
      lead = r.doneToday ? '<span class="nv-ck on" data-act="uncheck" data-id="' + esc(r.id) + '" role="checkbox" aria-checked="true" tabindex="0" aria-label="' + esc(tw("nv.a.uncheck")) + '">' + ic("check") + "</span>"
        : '<span class="nv-ck" data-act="check" data-id="' + esc(r.id) + '" role="checkbox" aria-checked="false" tabindex="0" aria-label="' + esc(tw("nv.a.check", { t: r.title })) + '"></span>';
      nx = r.doneToday ? tw("nv.rep.done_today") + (r.nextDate ? " · " + tw("nv.rep.next", { t: whenIso(nextAfter(r), r.time) }) : "") : r.nextDate ? tw("nv.rep.next", { t: whenIso(r.nextDate, r.time) }) : "";
    } else {
      lead = r.running
        ? '<button type="button" class="' + (phone ? "nv-go" : "nv-rgo") + ' busy" data-act="rstop" data-id="' + esc(r.id) + '" aria-label="' + esc(tw("nv.a.stop")) + '" title="' + esc(tw("nv.a.stop_t")) + '">' + ic("square") + "</button>"
        : '<button type="button" class="' + (phone ? "nv-go" : "nv-rgo") + '" data-act="rrun" data-id="' + esc(r.id) + '" aria-label="' + esc(tw("nv.a.run")) + '" title="' + esc(r.on ? tw("nv.a.run_t") : tw("nv.a.off")) + '"' + (r.on ? "" : " disabled") + ">" + ic("play") + "</button>";
      nx = !r.on ? tw("nv.rep.off") : r.running ? tw("nv.st.run") : r.next ? tw("nv.rep.next", { t: whenText(r.next) }) : "";
      sw = '<button type="button" class="nv-sw" role="switch" aria-checked="' + r.on + '" aria-label="' + esc(r.on ? tw("nv.a.pause") : tw("nv.a.resume")) + '" data-act="rtog" data-id="' + esc(r.id) + '"><span></span></button>';
    }
    return '<div class="nv-rrow' + (r.on ? "" : " off") + '">' + lead + '<button type="button" class="nv-grow" data-open="' + esc(r.id) + '"><span class="nv-ti">' + esc(r.title) + '</span><span class="nv-sc">' + esc(r.sc) + '</span><span class="nv-nx">' + esc(nx) + "</span></button>"
      + sw + '<button type="button" class="nv-dots" data-act="menu" data-id="' + esc(r.id) + '" aria-label="' + esc(tw("nv.a.more")) + '">' + ic("ellipsis") + "</button></div>";
  }
  function nextAfter(r) { var t = r.raw; return nextOcc(t.repeat, t.date || today(), addDays(today(), 1)) || r.nextDate; }
  function groupByDay(list, desc) {
    var g = {}, keys = [];
    list.forEach(function (i) { var k = i.date || "~"; if (!g[k]) { g[k] = []; keys.push(k); } g[k].push(i); });
    keys.sort(); if (desc) keys.reverse();
    return keys.map(function (k) { return [k, g[k].sort(byTime)]; });
  }
  function dayHead(k, extra) { return '<div class="nv-day">' + (k === "~" ? esc(tw("nv.d.none")) : esc(dayLabel(k)) + " <span>" + esc(shortDate(k)) + "</span>") + (extra || "") + "</div>"; }

  // ---------- list views ----------
  function q() { return (S.q || "").trim().toLowerCase(); }
  function matchQ(it) { var s = q(); return !s || (it.title + " " + (it.desc || "") + " " + agentName(it.who)).toLowerCase().indexOf(s) >= 0; }
  function items(list) { return M().items.filter(function (i) { return inList(i, list, today()) && matchQ(i); }); }
  function lists() { return S.tab === "me" ? LISTS_ME : LISTS_AI; }
  function overBtn() { return S.tab === "me" && items("over").some(function (i) { return i.id.indexOf("m:") === 0; }) ? '<button type="button" class="nv-btn sm" data-act="overall">' + ic("redo") + esc(tw("nv.a.move_all")) + "</button>" : ""; }
  function overBlock() {
    var L = items("over");
    if (!L.length) return "";
    return '<div class="nv-day over-h">' + esc(tw("nv.l.over")) + " <span>" + L.length + "</span>" + (overBtn() ? '<span class="nv-grow1"></span>' + overBtn() : "") + "</div>" + L.sort(byTime).map(row).join("");
  }
  function viewTitle(v) {
    if (v === "stats") return tw(S.tab === "me" ? "nv.sta.title_me" : "nv.sta.title_ai");
    if (v.indexOf("who:") === 0) return agentName(v.slice(4));
    if (v.indexOf("proj:") === 0) { var p = proj(v.slice(5)); return p ? p.name : ""; }
    var L = lists().find(function (x) { return x[0] === v; });
    return L ? tw(L[2]) : "";
  }
  function emptyKey(v) {
    if (S.tab === "me") return { today: "nv.empty.me_today", over: "nv.empty.over", rep: "nv.empty.me_rep", done: "nv.empty.done", nodate: "nv.empty.nodate" }[v] || "nv.empty.list";
    return { today: "nv.empty.today", over: "nv.empty.over", rep: "nv.empty.rep", done: "nv.empty.done" }[v] || "nv.empty.list";
  }
  function statsCtx() { return { tab: S.tab, brain: brain(), redraw: function () { if (S) render(); }, avatar: avatar }; }
  function viewHtml(v) {
    var h = '<div class="nv-vh"><h2>' + esc(viewTitle(v)) + "</h2>" + (v === "over" ? overBtn() : "") + "</div>";
    var empty = '<div class="nv-empty">' + esc(tw(emptyKey(v))) + "</div>";
    if (v === "rep") {
      var R = byRepTimeline(M().recurring.filter(function (r) { return !r.habit && (!q() || r.title.toLowerCase().indexOf(q()) >= 0); }));
      return h + (R.length ? R.map(function (r) { return repRow(r); }).join("") : empty);
    }
    if (v === "habit") return h + habitView();
    if (v === "stats") return h + (window.JavisTaskStats ? window.JavisTaskStats.html(statsCtx()) : "");
    if (v === "err") return h + failsHtml();
    if (v === "log") return h + logHtml();
    if (v === "today") {
      var T = items("today"), open = T.filter(function (i) { return !FIN[i.st]; }), done = T.filter(function (i) { return FIN[i.st]; });
      h += overBlock();
      var plan = open.filter(function (i) { return !i.time; }), timed = open.filter(function (i) { return i.time; });
      if (plan.length && timed.length) h += '<div class="nv-day">' + esc(tw("nv.d.in_day")) + "</div>" + plan.map(row).join("") + '<div class="nv-day">' + esc(tw("nv.d.timed")) + "</div>" + timed.sort(byTime).map(row).join("");
      else h += open.length ? open.sort(byTime).map(row).join("") : empty;
      if (done.length) h += '<button type="button" class="nv-fold" data-act="fold" aria-expanded="' + !!S.showDone + '">' + ic("chevron-right") + esc(tw("nv.done_n", { n: done.length })) + "</button>" + (S.showDone ? done.sort(byTime).map(row).join("") : "");
      return h;
    }
    if (v === "done") {
      var D = items("done");
      return h + (D.length ? groupByDay(D, true).map(function (g) { return dayHead(g[0]) + g[1].map(row).join(""); }).join("") : empty);
    }
    if (v === "nodate") { var N = items("nodate"); return h + (N.length ? N.map(row).join("") : empty); }
    var L = items(v);
    if (v === "all") { h += overBlock(); L = L.filter(function (i) { return !i.over; }); }
    if (v === "over") return h + (L.length ? groupByDay(L).map(function (g) { return dayHead(g[0]) + g[1].map(row).join(""); }).join("") : empty);
    if (!L.length && !(v === "all" && items("over").length)) return h + empty;
    return h + groupByDay(L).map(function (g) { return dayHead(g[0]) + g[1].map(row).join(""); }).join("");
  }
  function byRepTimeline(list) {
    if (S.tab !== "me") return byTimeline(list);
    return list.slice().sort(function (a, b) {
      var ka = (a.nextDate || "9999") + (a.time || "99"), kb = (b.nextDate || "9999") + (b.time || "99");
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
  }
  function failsHtml() {
    var open = S.ai.fails.filter(function (f) { return f.open; }), past = S.ai.fails.filter(function (f) { return !f.open && f.at > S.ai.now - 7 * 86400; });
    var h = '<div class="nv-day">' + esc(tw("nv.err.open")) + " <span>" + open.length + "</span></div>";
    h += open.length ? open.map(failRow).join("") : '<div class="nv-empty">' + esc(tw("nv.err.none")) + "</div>";
    h += '<div class="nv-day">' + esc(tw("nv.err.past")) + "</div>";
    h += past.length ? past.map(failRow).join("") : '<div class="nv-empty">' + esc(tw("nv.err.none_past")) + "</div>";
    return h;
  }
  function failRow(f) {
    var when = new Date(f.at * 1000);
    return '<div class="nv-frow"' + (f.ref ? ' data-open="' + esc(f.ref) + '" role="button" tabindex="0"' : "") + ">" + (f.open ? ic("circle-alert", "c-ask") : ic("circle-check", "c-ok"))
      + '<span class="nv-body"><span class="nv-ti">' + esc(f.title) + '</span><span class="nv-note">' + esc(f.why) + "</span>"
      + (f.self ? '<span class="nv-note">' + esc(tw("nv.err.self")) + "</span>" : "") + "</span>"
      + '<span class="nv-when">' + esc(dayLabel(isoOf(when)) + " " + hmOf(when)) + "</span>"
      + (f.inc && f.open ? '<button type="button" class="nv-btn sm" data-act="resolve" data-id="' + esc(f.inc) + '">' + esc(tw("nv.a.resolve")) + "</button>" : "") + "</div>";
  }
  function logHtml() {
    var L = S.ai.log.slice(0, 80).filter(function (e) { return !q() || (e.title + " " + e.text).toLowerCase().indexOf(q()) >= 0; });
    if (!L.length) return '<div class="nv-empty">' + esc(tw("nv.empty.log")) + "</div>";
    return L.map(function (e) {
      var when = e.at ? (function () { var d = new Date(e.at * 1000); return dayLabel(isoOf(d)) + " " + hmOf(d); })() : (e.when || "");
      return '<details class="nv-log"><summary>' + (e.ok ? ic("circle-check", "c-ok") : ic("circle-alert", "c-ask")) + '<span class="nv-ti">' + esc(e.title) + '</span><span class="nv-when">' + esc(when) + "</span></summary>"
        + '<div class="nv-logtx">' + esc(e.text || tw("nv.log.empty")) + "</div></details>";
    }).join("");
  }
  function askBar() {
    if (S.tab === "me") return "";
    var A = S.ai.ask, h = "";
    if (A.length) {
      var a = A[0];
      h += '<div class="nv-ask" role="status">' + ic("circle-alert", "c-ask") + '<button type="button" class="nv-ask-t" data-open="' + esc(a.id) + '"><b>' + esc(a.title) + ":</b> " + esc(a.reason || tw("nv.st.ask")) + "</button>"
        + (A.length > 1 ? '<span class="nv-ask-n">+' + (A.length - 1) + "</span>" : "") + "</div>";
    }
    // 0.426.0: with no report channel, reminders and loops still run on time but their results reach no one. Say so.
    var nt = S.notify || {}, bad = nt.ok === false, warn = !bad && nt.warn;
    if ((bad || warn) && S.ai.recurring.length) {
      h += '<div class="nv-ask" role="alert">' + ic("triangle-alert", "c-ask") + '<span class="nv-ask-t"><b>' + esc(tw(bad ? "nv.nochan.head" : "nv.chanerr.head")) + ":</b> "
        + esc(bad ? (nt.error || tw("nv.nochan.body")) : nt.warn) + '</span><button type="button" class="nv-btn sm" data-act="gochan">' + esc(tw("nv.nochan.go")) + "</button></div>";
    }
    if (S.ai.orch === "off" && S.ai.waiting) {
      h += '<div class="nv-ask" role="status">' + ic("pause", "c-ask") + '<span class="nv-ask-t">' + esc(tw("nv.orch.waiting", { n: S.ai.waiting })) + '</span><button type="button" class="nv-btn sm pri" data-act="orch" data-v="auto">' + esc(tw("nv.orch.on")) + "</button></div>";
    }
    return h;
  }

  // ---------- side column ----------
  function counts() {
    var c = {};
    lists().forEach(function (L) {
      var v = L[0];
      c[v] = v === "habit" ? M().recurring.filter(function (r) { return r.habit; }).length
        : v === "rep" ? M().recurring.filter(function (r) { return r.on && !r.habit; }).length : v === "err" ? S.ai.fails.filter(function (f) { return f.open; }).length
        : v === "log" ? "" : v === "done" ? items("done").length : items(v).filter(function (i) { return !FIN[i.st]; }).length;
    });
    return c;
  }
  function pins(kind) { try { return JSON.parse(lsGet("pins." + kind, "[]")) || []; } catch (e) { return []; } }
  function agentsList() {
    var P = pins("who"), busy = {};
    S.ai.items.forEach(function (i) { if (!FIN[i.st]) busy[i.who] = (busy[i.who] || 0) + 1; });
    var A = (S.agents || []).slice();
    if (!A.some(function (a) { return a.slug === CORE; })) A.unshift({ slug: CORE, name: "Javis Core" });
    // A chatbot whose assistant is not in this brain gets its own row once it owns a job (0.429.0).
    var owned = {};
    S.ai.items.concat(S.ai.recurring).forEach(function (i) { owned[i.who] = 1; });
    ((S.bots && S.bots.bots) || []).forEach(function (b) { if (owned["bot:" + b.id]) A.push({ slug: "bot:" + b.id, name: b.name }); });
    A.sort(function (a, b) { return (P.indexOf(b.slug) >= 0) - (P.indexOf(a.slug) >= 0) || (busy[b.slug] || 0) - (busy[a.slug] || 0); });
    return { list: A.map(function (a) { return { id: a.slug, name: a.name || a.slug, n: busy[a.slug] || 0, pin: P.indexOf(a.slug) >= 0, view: "who:" + a.slug, mark: avatar(a.slug, 18) }; }) };
  }
  function projectsList() {
    var busy = {};
    S.me.items.forEach(function (i) { if (!FIN[i.st] && i.proj) busy[i.proj] = (busy[i.proj] || 0) + 1; });
    var P = ((S.my && S.my.projects) || []).filter(function (p) { return !S.hidden["p:" + p.id]; }).slice();
    P.sort(function (a, b) { return (!!b.pinned - !!a.pinned) || ((a.order || 0) - (b.order || 0)); });
    return { list: P.map(function (p) { return { id: p.id, name: p.name, n: busy[p.id] || 0, pin: !!p.pinned, view: "proj:" + p.id, mark: '<i class="nv-dot" style="background:' + esc(p.color) + '"></i>', proj: true }; }) };
  }
  function groupHtml(phone) {
    var me = S.tab === "me", G = me ? projectsList() : agentsList(), more = me ? S.moreProj : S.moreWho, shown = more ? G.list : G.list.slice(0, PAGE);
    var h = '<div class="nv-sec"><span>' + esc(me ? tw("nv.projects") : tw("nv.agents")) + "</span>" + (me ? '<button type="button" class="nv-secb" data-act="pnew" aria-label="' + esc(tw("nv.p.new")) + '" title="' + esc(tw("nv.p.new")) + '">' + ic("plus") + "</button>" : "") + "</div>";
    if (phone) h += '<div class="nv-pcards">';
    h += shown.map(function (x) {
      if (phone) return '<button type="button" class="nv-pl" data-pl="' + esc(x.view) + '">' + x.mark + '<span class="nv-lbl">' + esc(x.name) + '</span><span class="nv-n">' + (x.n || "") + "</span>" + ic("chevron-right", "nv-chev") + "</button>";
      return '<div class="nv-lirow"><button type="button" class="nv-li' + (S.view === x.view ? " on" : "") + '" data-view="' + esc(x.view) + '">' + x.mark + '<span class="nv-lbl">' + esc(x.name) + '</span><span class="nv-n">' + (x.n || "") + "</span></button>"
        + '<button type="button" class="nv-pin' + (x.pin ? " on" : "") + '" data-act="pin" data-id="' + esc(x.id) + '" data-v="' + (x.proj ? "proj" : "who") + '" aria-pressed="' + x.pin + '" aria-label="' + esc(x.pin ? tw("nv.a.unpin") : tw("nv.a.pin")) + '">' + ic("pin") + "</button>"
        + (x.proj ? '<button type="button" class="nv-pin" data-act="pmenu" data-id="' + esc(x.id) + '" aria-label="' + esc(tw("nv.a.more")) + '">' + ic("ellipsis") + "</button>" : "") + "</div>";
    }).join("");
    if (phone) h += "</div>";
    if (me && !G.list.length) h += '<button type="button" class="nv-more" data-act="pnew">' + ic("plus") + "<span>" + esc(tw("nv.p.new")) + "</span></button>";
    if (G.list.length > PAGE) h += '<button type="button" class="nv-more" data-act="' + (me ? "moreproj" : "morewho") + '">' + ic(more ? "chevron-up" : "chevron-down") + "<span>" + esc(more ? tw("nv.less") : tw("nv.more_n", { n: G.list.length - PAGE })) + "</span></button>";
    if (!me) h += '<div class="nv-orch"><span>' + ic("bot") + esc(tw("nv.orch.label")) + '</span><button type="button" class="nv-sw" role="switch" aria-checked="' + (S.ai.orch !== "off") + '" aria-label="' + esc(tw("nv.orch.label")) + '" data-act="orch" data-v="' + (S.ai.orch === "off" ? "auto" : "off") + '"><span></span></button></div>';
    return h;
  }
  function sideHtml() {
    var c = counts();
    var h = '<div class="nv-title">' + esc(tw("nv.title")) + "</div>";
    h += lists().map(function (L) {
      var n = c[L[0]];
      return '<button type="button" class="nv-li' + (S.view === L[0] ? " on" : "") + '" data-view="' + L[0] + '">' + ic(L[1], L[3]) + '<span class="nv-lbl">' + esc(tw(L[2])) + '</span><span class="nv-n' + ((L[0] === "over" || L[0] === "err") && n ? " warn" : "") + '">' + (n || "") + "</span></button>";
    }).join("");
    // 0.428.0: Stats closes the lists of both tabs.
    h += '<div class="nv-sep"></div><button type="button" class="nv-li' + (S.view === "stats" ? " on" : "") + '" data-view="stats">' + ic("chart-column", S.tab === "me" ? "c-stme" : "c-stai") + '<span class="nv-lbl">' + esc(tw("nv.sta.menu")) + "</span></button>";
    return h + groupHtml(false);
  }
  function tabsHtml() {
    var nMe = S.me.items.filter(function (i) { return !FIN[i.st] && !i.over && (i.date === today() || !i.date); }).length;
    var nAi = S.ai.items.filter(function (i) { return !FIN[i.st]; }).length;
    return '<div class="nv-tabs" role="tablist">'
      // 0.428.0: Javis's tasks first (owner: opening the page shows what Javis is doing), then mine.
      + '<button type="button" role="tab" data-act="tab" data-v="ai" aria-selected="' + (S.tab === "ai") + '" class="' + (S.tab === "ai" ? "on" : "") + '">' + avatar(CORE, 18) + "<span>" + esc(tw("nv.tab.ai")) + '</span><span class="nv-n">' + nAi + "</span></button>"
      + '<button type="button" role="tab" data-act="tab" data-v="me" aria-selected="' + (S.tab === "me") + '" class="' + (S.tab === "me" ? "on" : "") + '">' + ic("circle-user") + "<span>" + esc(tw("nv.tab.me")) + '</span><span class="nv-n">' + nMe + "</span></button></div>";
  }
  function renderDesk() {
    var D = S.root.querySelector(".nv-desk");
    D.querySelector(".nv-side").innerHTML = sideHtml();
    D.querySelector(".nv-top").innerHTML = tabsHtml();
    D.querySelector(".nv-askbox").innerHTML = askBar();
    D.querySelector(".nv-search").hidden = S.view === "stats";   // 0.429.0: nothing to search on Stats
    D.querySelector(".nv-view").innerHTML = viewHtml(S.view);
    fitSide();
  }
  function fitSide() {
    var s = S && S.root.querySelector(".nv-side");
    if (!s || window.innerWidth <= 760) return;
    var top = s.getBoundingClientRect().top;
    s.style.maxHeight = (window.innerHeight - Math.max(12, top) - 12) + "px";
  }

  // ---------- phone ----------
  function phoneHtml() {
    var P = S.phone;
    var bar = function (title, more) { return '<div class="nv-pbar"><button type="button" class="nv-back" data-pback="1" aria-label="' + esc(tw("nv.back")) + '">' + ic("chevron-left") + '</button><span class="nv-ptitle">' + esc(title) + "</span>" + (more || "<span></span>") + "</div>"; };
    if (P.screen === "detail") {
      var it = find(P.id);
      var more = it ? '<button type="button" class="nv-back" data-act="menu" data-id="' + esc(it.id) + '" aria-label="' + esc(tw("nv.a.more")) + '">' + ic("ellipsis") + "</button>" : "";
      return bar(it ? (it.src === "gcal" ? tw("nv.g.src") : it.src === "mine" ? (proj(it.proj) || {}).name || tw("nv.tab.me") : agentName(it.who)) : "", more) + '<div class="nv-ppad">' + (it ? detailHtml(it, true) : "") + "</div>";
    }
    if (P.screen === "list") {
      var body = viewHtml(P.list).replace(/^<div class="nv-vh">[\s\S]*?<\/div>/, "");
      return bar(viewTitle(P.list)) + '<div class="nv-ppad">' + (P.list === "over" ? overBtn() : "") + body + "</div>";
    }
    var c = counts();
    var h = '<div class="nv-ppad">' + askBar() + '<div class="nv-pcards">';
    h += lists().map(function (L) { return '<button type="button" class="nv-pl" data-pl="' + L[0] + '">' + ic(L[1], L[3]) + '<span class="nv-lbl">' + esc(tw(L[2])) + '</span><span class="nv-n">' + (c[L[0]] || "") + "</span>" + ic("chevron-right", "nv-chev") + "</button>"; }).join("")
      + '<button type="button" class="nv-pl" data-pl="stats">' + ic("chart-column", S.tab === "me" ? "c-stme" : "c-stai") + '<span class="nv-lbl">' + esc(tw("nv.sta.menu")) + '</span><span class="nv-n"></span>' + ic("chevron-right", "nv-chev") + "</button>";
    return h + "</div>" + groupHtml(true) + "</div>";
  }
  function renderPhone() {
    var el = S.root.querySelector(".nv-phone");
    el.querySelector(".nv-ptabs").innerHTML = tabsHtml();
    el.querySelector(".nv-pbody").innerHTML = phoneHtml();
    var te = el.querySelector(".nv-titleed"); if (te) fitTA(te);
  }

  // ---------- detail ----------
  function find(id) {
    if (!S.ai || !id) return null;
    var pools = id.indexOf("m") === 0 || id.indexOf("g:") === 0 ? [S.me] : [S.ai];
    for (var i = 0; i < pools.length; i++) {
      var m = pools[i];
      // A repeating job has both a recurring entry and an item under the same id: the entry wins (schedule, switch).
      var hit = m.recurring.find(function (r) { return r.id === id; }) || m.items.find(function (x) { return x.id === id; });
      if (hit) return hit;
    }
    return null;
  }
  function kv(label, value) { return '<div class="nv-kv"><span>' + esc(label) + "</span><span>" + value + "</span></div>"; }
  function projSelect(t, cls) {
    var P = (S.my && S.my.projects) || [];
    return '<select class="' + (cls || "nv-psel") + '" data-pproj="' + esc(t.id) + '" aria-label="' + esc(tw("nv.k.project")) + '"><option value="">' + esc(tw("nv.p.none")) + "</option>"
      + P.map(function (p) { return '<option value="' + esc(p.id) + '"' + (t.project === p.id ? " selected" : "") + ">" + esc(p.name) + "</option>"; }).join("") + "</select>";
  }
  var DURS = [15, 30, 45, 60, 90, 120, 180, 240];
  var REMS = ["0", "5", "15", "30", "60"];
  var LVL = { suggest: "nv.lp.m_suggest", auto: "nv.lp.m_auto", full: "nv.lp.m_full" };
  var LP_NOTE = { suggest: "cs.si_level_note_suggest", auto: "cs.si_level_note_auto", full: "cs.si_level_note_full" };
  function toMin(hm) { var p = String(hm || "0:0").split(":"); return Number(p[0]) * 60 + Number(p[1] || 0); }
  function fromMin(m) { m = Math.max(0, Math.min(23 * 60 + 59, m)); return pad2(Math.floor(m / 60)) + ":" + pad2(m % 60); }
  function durTxt(m) { return m >= 60 ? tw("nv.ap.h", { h: Math.floor(m / 60) }) + (m % 60 ? " " + tw("nv.ap.m", { m: m % 60 }) : "") : tw("nv.ap.m", { m: m }); }
  function durSelect(cur, attr) {
    var L = DURS.indexOf(cur) >= 0 ? DURS : DURS.concat([cur]).sort(function (a, b) { return a - b; });
    return '<select class="nv-psel" ' + attr + ' aria-label="' + esc(tw("nv.ap.dur")) + '">' + L.map(function (m) { return '<option value="' + m + '"' + (m === cur ? " selected" : "") + ">" + esc(durTxt(m)) + "</option>"; }).join("") + "</select>";
  }
  function remSelect(cur, attr) {
    return '<select class="nv-psel" ' + attr + ' aria-label="' + esc(tw("nv.ap.remind")) + '">' + REMS.map(function (v) { return '<option value="' + v + '"' + (String(cur || "15") === v ? " selected" : "") + ">" + esc(v === "0" ? tw("nv.ap.no_remind") : tw("nv.ap.before", { n: v })) + "</option>"; }).join("") + "</select>";
  }
  function apptDetail(it, phone) {
    var t = it.raw, dur = Math.max(5, toMin(t.end) - toMin(t.time));
    var h = '<div class="nv-dhead nv-mhead"><i class="nv-abar big" style="background:' + esc(apptColor(it)) + '"></i><textarea class="nv-titleed" data-mtitle="' + esc(t.id) + '" rows="1" aria-label="' + esc(tw("nv.ap.what")) + '">' + esc(t.title) + "</textarea></div>"
      + (apptChip(it) ? "<div>" + apptChip(it) + "</div>" : "");
    h += '<div class="nv-sec2">'
      + '<button type="button" class="nv-kv nv-kvb" data-act="pick-date" data-id="' + esc(it.id) + '"><span>' + ic("clock") + esc(tw("nv.ap.start")) + "</span><span>" + esc(whenIso(it.date, t.time)) + "</span></button>"
      + '<label class="nv-kv"><span>' + ic("hourglass") + esc(tw("nv.ap.dur")) + "</span>" + durSelect(dur, 'data-adur="' + esc(t.id) + '"') + "</label>"
      + kv(tw("nv.ap.end"), esc(t.end || ""))
      + '<label class="nv-kv"><span>' + ic("bell") + esc(tw("nv.ap.remind")) + "</span>" + remSelect(t.remind, 'data-arem="' + esc(t.id) + '"') + "</label>"
      + '<label class="nv-kv"><span>' + ic("map-pin") + esc(tw("nv.ap.where")) + '</span><input class="nv-psel" data-aloc="' + esc(t.id) + '" value="' + esc(t.location || "") + '" placeholder="' + esc(tw("nv.ap.where_ph")) + '"></label>'
      + '<button type="button" class="nv-kv nv-kvb" data-act="pick-rep" data-id="' + esc(it.id) + '"><span>' + ic("repeat") + esc(tw("nv.k.repeat")) + "</span><span>" + esc(t.repeat ? repHuman(t.repeat) : tw("nv.f.rep_none")) + "</span></button>"
      + '<label class="nv-kv"><span>' + ic("folder") + esc(tw("nv.k.project")) + "</span>" + projSelect(t) + "</label></div>";
    if (t.prep) h += '<div class="nv-sec2"><div class="nv-from">' + avatar(CORE, 16) + esc(tw("nv.ap.prep_set")) + '</div><div class="nv-res">' + esc(t.prep) + "</div></div>";
    h += '<div class="nv-sec2"><textarea class="nv-ta" data-mnotes="' + esc(t.id) + '" placeholder="' + esc(tw("nv.notes_ph")) + '" aria-label="' + esc(tw("nv.notes_ph")) + '">' + esc(t.notes || "") + "</textarea></div>";
    if (!phone) h += '<div class="nv-sec2"><div class="nv-acts">' + menuButtons(it) + "</div></div>";
    return h;
  }
  function mineDetail(it, phone) {
    if (it.appt) return apptDetail(it, phone);
    var t = it.raw, rep = !!t.repeat, occ = it.occ || null, done = it.sc ? it.doneToday : it.st === "done";
    var h = '<div class="nv-dhead nv-mhead">' + (habitOn(t) ? habitCk(t, "big") : it.sc ? (done ? '<span class="nv-ck on big" data-act="uncheck" data-id="' + esc(it.id) + '" role="checkbox" aria-checked="true" tabindex="0" aria-label="' + esc(tw("nv.a.uncheck")) + '">' + ic("check") + "</span>" : '<span class="nv-ck big" data-act="check" data-id="' + esc(it.id) + '" role="checkbox" aria-checked="false" tabindex="0" aria-label="' + esc(tw("nv.a.check", { t: it.title })) + '"></span>') : ck(it).replace('class="nv-ck', 'class="nv-ck big'))
      + '<textarea class="nv-titleed" data-mtitle="' + esc(t.id) + '" rows="1" aria-label="' + esc(tw("nv.f.what")) + '">' + esc(t.title) + "</textarea></div>";
    if (t.from_javis) h += '<div class="nv-from">' + avatar(CORE, 16) + esc(tw("nv.from_javis_long")) + "</div>";
    h += '<div class="nv-sec2">'
      + '<button type="button" class="nv-kv nv-kvb" data-act="pick-date" data-id="' + esc(it.id) + '"><span>' + ic("clock") + esc(tw("nv.k.when")) + "</span><span>" + esc(whenIso(occ && rep ? occ : t.date, t.time)) + "</span></button>"
      + '<button type="button" class="nv-kv nv-kvb" data-act="pick-rep" data-id="' + esc(it.id) + '"><span>' + ic("repeat") + esc(tw("nv.k.repeat")) + "</span><span>" + esc(rep ? repHuman(t.repeat) : tw("nv.f.rep_none")) + "</span></button>"
      + (rep && t.kind !== "appt" ? '<div class="nv-kv"><span>' + ic("flame", "c-habit") + esc(tw("nv.h.is_habit")) + '</span><button type="button" class="nv-sw" role="switch" aria-checked="' + habitOn(t) + '" aria-label="' + esc(tw("nv.h.is_habit")) + '" data-act="htog" data-id="m:' + esc(t.id) + '"><span></span></button></div>' : "")
      + '<label class="nv-kv"><span>' + ic("folder") + esc(tw("nv.k.project")) + "</span>" + projSelect(t) + "</label></div>";
    var acts = (done ? "" : '<button type="button" class="nv-btn pri" data-act="check" data-id="' + esc(it.id) + '">' + ic("check") + esc(tw("nv.a.done")) + "</button>")
      + '<button type="button" class="nv-btn" data-act="tojavis" data-id="' + esc(it.id) + '">' + avatar(CORE, 16) + esc(tw("nv.a.tojavis")) + "</button>";
    h += '<div class="nv-sec2"><div class="nv-acts">' + acts + "</div></div>";
    h += '<div class="nv-sec2">' + (t.subs || []).map(function (x, i) { return '<label class="nv-sub' + (x.done ? " done" : "") + '"><input type="checkbox" data-msub="' + esc(t.id) + '" data-v="' + i + '"' + (x.done ? " checked" : "") + "><span>" + esc(x.t) + "</span></label>"; }).join("")
      + '<form class="nv-subadd" data-msubadd="' + esc(t.id) + '">' + ic("plus") + '<input placeholder="' + esc(tw("nv.sub_ph")) + '" aria-label="' + esc(tw("nv.sub_ph")) + '" enterkeyhint="done"></form></div>';
    h += '<div class="nv-sec2"><textarea class="nv-ta" data-mnotes="' + esc(t.id) + '" placeholder="' + esc(tw("nv.notes_ph")) + '" aria-label="' + esc(tw("nv.notes_ph")) + '">' + esc(t.notes || "") + "</textarea></div>";
    if (habitOn(t)) h += '<div class="nv-sec2">' + streakCard(t) + "</div>";
    if (!phone) h += '<div class="nv-sec2"><div class="nv-acts">' + menuButtons(it) + "</div></div>";
    return h;
  }
  // A Google Calendar event: read-only here, edited in Google.
  function gcalDetail(it, phone) {
    var t = it.raw;
    var h = '<div class="nv-dhead nv-mhead"><i class="nv-abar big" style="background:' + esc(apptColor(it)) + '"></i><h3>' + esc(it.title) + "</h3></div>"
      + (apptChip(it) ? "<div>" + apptChip(it) + "</div>" : "")
      + '<div class="nv-sec2">' + kv(tw("nv.ap.start"), esc(t.all_day ? dayLabel(it.date) + ", " + tw("nv.g.allday") : whenIso(it.date, it.time)))
      + (it.end ? kv(tw("nv.ap.end"), esc(it.end)) : "") + (t.location ? kv(tw("nv.ap.where"), esc(t.location)) : "")
      + kv(tw("nv.g.from"), esc(t.source || tw("nv.g.src"))) + "</div>"
      + '<div class="nv-sec2"><div class="nv-from">' + ic("lock") + esc(tw("nv.g.readonly")) + "</div></div>";
    if (!phone && t.link) h += '<div class="nv-sec2"><div class="nv-acts">' + menuButtons(it) + "</div></div>";
    return h;
  }
  function detailHtml(it, phone) {
    if (it.src === "gcal") return gcalDetail(it, phone);
    if (it.src === "mine") return mineDetail(it, phone);
    var isRep = !!it.sc;
    var r = isRep ? it : S.ai.recurring.find(function (x) { return x.id === it.id; });
    var h = '<div class="nv-dhead">' + (isRep ? "" : chip(it)) + "<h3>" + esc(it.title) + "</h3>" + (it.desc && it.desc !== it.title ? '<div class="nv-desc">' + esc(it.desc) + "</div>" : "") + "</div>";
    var acts = "";
    if (isRep) {
      acts = it.running ? '<button type="button" class="nv-btn" data-act="rstop" data-id="' + esc(it.id) + '">' + ic("square") + esc(tw("nv.a.stop")) + "</button>"
        : '<button type="button" class="nv-btn pri" data-act="rrun" data-id="' + esc(it.id) + '"' + (it.on ? "" : " disabled") + ">" + ic("play") + esc(tw("nv.a.run")) + "</button>";
    } else if (it.st === "run") acts = '<button type="button" class="nv-btn" data-act="stop" data-id="' + esc(it.id) + '">' + ic("square") + esc(tw("nv.a.stop")) + "</button>";
    else if (it.src === "kanban" && it.st === "ask" && it.blockKind === "capability") acts = '<button type="button" class="nv-btn pri" data-act="grant" data-id="' + esc(it.id) + '">' + ic("key-round") + esc(tw("nv.a.grant")) + "</button>";
    else if (it.src === "kanban" && it.st === "ask" && it.status === "review") acts = '<button type="button" class="nv-btn pri" data-act="approve" data-id="' + esc(it.id) + '">' + ic("check") + esc(tw("nv.a.approve")) + "</button>";
    else if (!FIN[it.st] && it.st !== "ask") acts = '<button type="button" class="nv-btn pri" data-act="run" data-id="' + esc(it.id) + '">' + ic("play") + esc(it.st === "calm" ? tw("nv.a.retry") : tw("nv.a.run")) + "</button>";
    var prog = isRep ? (it.on ? tw("nv.rep.next", { t: it.next ? whenText(it.next) : "-" }) : tw("nv.rep.off"))
      : it.st === "done" ? (it.result || tw("nv.log.empty")) : it.st === "ask" ? (it.reason || tw("nv.st.ask")) : it.st === "calm" ? (it.reason || tw("nv.st.calm"))
      : it.st === "run" ? tw("nv.st.run") : it.st === "cancel" ? tw("nv.st.cancel") : it.st === "queue" ? tw("nv.prog.queue") : tw("nv.prog.sched");
    h += '<div class="nv-sec2"><div class="nv-cap">' + esc(it.st === "done" ? tw("nv.cap.result") : tw("nv.cap.progress")) + '</div><div class="nv-res">' + esc(prog) + "</div>" + (acts ? '<div class="nv-acts">' + acts + "</div>" : "") + "</div>";
    if (!isRep && it.src === "kanban" && it.st === "ask" && it.blockKind === "needs_input") {
      h += '<form class="nv-sec2 nv-answer" data-answer="' + esc(it.id) + '"><label class="nv-cap" for="nvAns">' + esc(tw("nv.answer")) + '</label><textarea id="nvAns" class="nv-ta" required></textarea><div class="nv-acts"><button type="submit" class="nv-btn pri">' + esc(tw("nv.send")) + "</button></div></form>";
    }
    var info = "";
    if (!isRep && it.date) info += kv(tw("nv.k.when"), esc(dayLabel(it.date) + (it.time ? ", " + it.time : "")));
    if (r) info += kv(tw("nv.k.repeat"), esc(r.sc));
    info += kv(tw("nv.k.who"), '<span class="nv-who">' + avatar(it.who, 16) + esc(agentName(it.who)) + "</span>");
    info += kv(tw("nv.k.how"), esc(it.mode === "remind" ? tw("nv.mode.remind") : tw("nv.mode.do")));
    // 0.426.0: the permission level a reminder or loop runs at, as the old Scheduled cards showed it.
    var lvl = it.src === "loop" ? (it.raw || {}).mode : it.src === "reminder" && it.mode !== "remind" ? ((it.raw || {}).muc_quyen || "full") : "";
    if (lvl) info += kv(tw("nv.lp.mode"), '<span class="nv-lvl' + (lvl === "full" ? " full" : "") + '">' + esc(tw(LVL[lvl] || LVL.full)) + "</span>");
    info += kv(tw("nv.k.kind"), esc(tw({ kanban: "nv.src.kanban", reminder: "nv.src.reminder", loop: "nv.src.loop", watch: "nv.src.watch" }[it.src] || "nv.src.kanban")));
    if (r) info += '<div class="nv-kv"><span>' + esc(tw("nv.k.on")) + '</span><button type="button" class="nv-sw" role="switch" aria-checked="' + r.on + '" aria-label="' + esc(tw("nv.k.on")) + '" data-act="rtog" data-id="' + esc(r.id) + '"><span></span></button></div>';
    h += '<div class="nv-sec2">' + info + "</div>";
    if (it.st === "done" && it.src === "kanban") {
      h += '<form class="nv-sec2 nv-answer" data-follow="' + esc(it.id) + '"><label class="nv-cap" for="nvFu">' + esc(tw("nv.follow")) + '</label><textarea id="nvFu" class="nv-ta" placeholder="' + esc(tw("nv.follow_ph")) + '" required></textarea><div class="nv-acts"><button type="submit" class="nv-btn pri">' + esc(tw("nv.send")) + "</button></div></form>";
    }
    if (!phone) h += '<div class="nv-sec2"><div class="nv-acts">' + menuButtons(it) + "</div></div>";
    return h;
  }
  function drawerHtml(it) {
    return '<div class="nv-scrim" data-act="close"></div><aside class="nv-drawer" role="dialog" aria-modal="true" aria-label="' + esc(tw("nv.detail")) + '">'
      + '<div class="nv-dh"><span>' + (it.src === "mine" || it.src === "gcal" ? ic("circle-user") + esc(tw("nv.tab.me")) : esc(tw("nv.detail"))) + '</span><button type="button" class="nv-x" data-act="close" aria-label="' + esc(tw("nv.close")) + '">' + ic("x") + "</button></div>" + detailHtml(it) + "</aside>";
  }

  // ---------- menu ⋯ ----------
  function menuDefs(it) {
    var isRep = !!it.sc, src = it.src, out = [];
    if (src === "gcal") return it.raw && it.raw.link ? [["gopen", "external-link", "nv.g.open"]] : [];
    if (src === "mine") {
      if (it.id.indexOf("mo:") === 0 || it.id.indexOf("md:") === 0) return [["open", "pencil", "nv.a.edit"]];
      out.push(["edit", "pencil", "nv.a.edit"]);
      if (!it.appt) out.push(["tojavis", "bot", "nv.a.tojavis"]);
      if ((S.brains || []).length > 1) { out.push(["move", "arrow-right-left", "nv.a.move"]); out.push(["copy", "copy", "nv.a.copy"]); }
      out.push(["del", "trash-2", "nv.a.del"]);
      return out;
    }
    if ((src === "reminder" && (isRep || !FIN[it.st])) || src === "loop") out.push(["edit", "pencil", "nv.a.edit"]);
    if (isRep && src === "reminder") out.push(["skip", "skip-forward", "nv.a.skip"]);
    if (isRep) out.push(["rtog", it.on ? "pause" : "play", it.on ? "nv.a.pause" : "nv.a.resume"]);
    if (!isRep && (src === "kanban" || src === "reminder") && !FIN[it.st]) out.push(["cancel", "circle-x", "nv.a.cancel"]);
    if ((src === "kanban" || src === "reminder") && !FIN[it.st] && it.st !== "run") out.push(["tome", "circle-user", "nv.a.tome"]);
    if ((src === "reminder" || src === "loop") && !FIN[it.st] && (S.brains || []).length > 1) out.push(["move", "arrow-right-left", "nv.a.move"]);
    out.push(["del", "trash-2", "nv.a.del"]);
    return out;
  }
  function menuButtons(it) {
    // The drawer of my task already has "Give to Javis" next to Done.
    return menuDefs(it).filter(function (m) { return !(it.src === "mine" && m[0] === "tojavis"); }).map(function (m) { return '<button type="button" class="nv-btn sm' + (m[0] === "del" ? " ghost danger" : "") + '" data-act="m-' + m[0] + '" data-id="' + esc(it.id) + '">' + ic(m[1]) + esc(tw(m[2])) + "</button>"; }).join("");
  }

  // ---------- sheets: menu, brains, project, date picker, repeat picker ----------
  function sheetFrame(title, body) {
    return '<div class="nv-sheet-scrim" data-act="sheetclose"></div><div class="nv-sheet" role="dialog" aria-modal="true" aria-label="' + esc(title) + '"><div class="nv-sheet-h"><b>' + esc(title) + '</b><button type="button" class="nv-x" data-act="sheetclose" aria-label="' + esc(tw("nv.close")) + '">' + ic("x") + "</button></div>" + body + "</div>";
  }
  function sheetHtml() {
    var sh = S.sheet;
    if (!sh) return "";
    if (sh.kind === "date") return sheetFrame(tw("nv.k.when"), datePickerHtml(sh));
    if (sh.kind === "rep") return sheetFrame(tw("nv.k.repeat"), repPickerHtml(sh));
    if (sh.kind === "project") return sheetFrame(sh.id ? tw("nv.p.edit") : tw("nv.p.new"), projectFormHtml(sh));
    if (sh.kind === "pmenu") {
      var p = proj(sh.id); if (!p) return "";
      return sheetFrame(p.name, '<div class="nv-sheet-b"><button type="button" class="nv-mi" data-act="pedit" data-id="' + esc(p.id) + '">' + ic("pencil") + esc(tw("nv.p.edit")) + '</button><button type="button" class="nv-mi danger" data-act="pdel" data-id="' + esc(p.id) + '">' + ic("trash-2") + esc(tw("nv.p.del")) + "</button></div>");
    }
    var it = find(sh.id);
    if (!it) return "";
    if (sh.kind === "move" || sh.kind === "copy") {
      var others = (S.brains || []).filter(function (b) { return b.path !== brain() && !(brain() === "brain" && b.def); });
      return sheetFrame(it.title, '<div class="nv-sheet-b">' + others.map(function (b) { return '<button type="button" class="nv-mi" data-act="' + sh.kind + '-to" data-id="' + esc(it.id) + '" data-v="' + esc(b.path) + '">' + ic("brain") + esc(b.name) + "</button>"; }).join("") + "</div>");
    }
    return sheetFrame(it.title, '<div class="nv-sheet-b">' + menuDefs(it).map(function (m) { return '<button type="button" class="nv-mi' + (m[0] === "del" ? " danger" : "") + '" data-act="m-' + m[0] + '" data-id="' + esc(it.id) + '">' + ic(m[1]) + esc(tw(m[2])) + "</button>"; }).join("") + "</div>");
  }
  function projectFormHtml(sh) {
    return '<form class="nv-pform" data-pform="1"><input class="nv-inp" id="nvPName" required placeholder="' + esc(tw("nv.p.name_ph")) + '" value="' + esc(sh.name || "") + '" aria-label="' + esc(tw("nv.p.name_ph")) + '">'
      + '<div class="nv-colors" role="radiogroup" aria-label="' + esc(tw("nv.p.color")) + '">' + COLORS.map(function (c) { return '<button type="button" role="radio" class="nv-color' + (sh.color === c ? " on" : "") + '" style="background:' + c + '" data-act="pcol" data-v="' + c + '" aria-checked="' + (sh.color === c) + '" aria-label="' + c + '"></button>'; }).join("") + "</div>"
      + '<div class="nv-acts end"><button type="button" class="nv-btn ghost" data-act="sheetclose">' + esc(tw("nv.cancel")) + '</button><button type="submit" class="nv-btn pri">' + esc(tw("nv.save")) + "</button></div></form>";
  }
  // Date picker: icon-only quick picks (no date first), a Monday-first month, a 30-minute time list plus "other time".
  function datePickerHtml(sh) {
    var d = sh.d, t = today(), mon = (function () { var x = new Date(t + "T12:00:00"); var k = (8 - x.getDay()) % 7 || 7; return addDays(t, k); })();
    var quick = [["", "inbox", "nv.dp.none"], [t, "sun", "nv.d.today"], [addDays(t, 1), "sunrise", "nv.d.tom"], [mon, "calendar", "nv.dp.monday"]];
    var h = '<div class="nv-dpq">' + quick.map(function (x) { return '<button type="button" class="nv-dpb' + ((d.date || "") === x[0] ? " on" : "") + '" data-act="dp-set" data-v="' + x[0] + '" aria-label="' + esc(tw(x[2])) + '" title="' + esc(tw(x[2])) + '">' + ic(x[1]) + "</button>"; }).join("") + "</div>";
    var vm = d.vm, first = new Date(vm + "-01T12:00:00"), lead = (first.getDay() + 6) % 7, nd = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
    h += '<div class="nv-dpm"><button type="button" class="nv-x" data-act="dp-mon" data-v="-1" aria-label="' + esc(tw("nv.dp.prev")) + '">' + ic("chevron-left") + "</button><b>" + esc(first.toLocaleDateString(LOC(), { month: "long", year: "numeric" })) + '</b><button type="button" class="nv-x" data-act="dp-mon" data-v="1" aria-label="' + esc(tw("nv.dp.next")) + '">' + ic("chevron-right") + "</button></div>";
    h += '<div class="nv-dpg">' + [1, 2, 3, 4, 5, 6, 0].map(function (k) { return '<span class="nv-dpw">' + esc(tw(WD_KEYS[k])) + "</span>"; }).join("");
    for (var i = 0; i < lead; i++) h += "<span></span>";
    for (var n = 1; n <= nd; n++) {
      var iso = vm + "-" + pad2(n);
      h += '<button type="button" class="nv-dpd' + (iso === d.date ? " on" : "") + (iso === t ? " tdy" : "") + (iso < t ? " past" : "") + '" data-act="dp-set" data-v="' + iso + '">' + n + "</button>";
    }
    h += "</div>";
    var times = '<option value="">' + esc(tw("nv.f.no_time")) + "</option>";
    for (var k = 0; k < 48; k++) { var tt = pad2(Math.floor(k / 2)) + ":" + (k % 2 ? "30" : "00"); times += '<option' + (tt === d.time ? " selected" : "") + ">" + tt + "</option>"; }
    if (d.time && !/:(00|30)$/.test(d.time)) times += "<option selected>" + esc(d.time) + "</option>";
    h += '<div class="nv-dpt"><label>' + ic("clock") + '<select class="nv-inp" data-dp="time"' + (d.date ? "" : " disabled") + ">" + times + '</select></label><input type="time" class="nv-inp" data-dp="other" aria-label="' + esc(tw("nv.dp.other")) + '" title="' + esc(tw("nv.dp.other")) + '"' + (d.date ? "" : " disabled") + "></div>";
    return h + '<div class="nv-acts two"><button type="button" class="nv-btn ghost" data-act="dp-clear">' + esc(tw("nv.dp.clear")) + '</button><button type="button" class="nv-btn pri" data-act="dp-ok">' + esc(tw("nv.dp.ok")) + "</button></div>";
  }
  // Repeat picker: "Every [n] [unit]", weekday circles for weeks. Minutes and hours only for Javis jobs.
  function repPickerHtml(sh) {
    var r = sh.r, units = sh.javis ? ["min", "hour", "day", "week", "month", "year"] : ["day", "week", "month", "year"];
    var h = '<div class="nv-rp"><span>' + esc(tw("nv.rp.every")) + '</span><input type="number" class="nv-inp nv-rpn" min="1" max="365" value="' + (r.n || 1) + '" data-rp="n" aria-label="' + esc(tw("nv.rp.n")) + '"><select class="nv-inp" data-rp="unit" aria-label="' + esc(tw("nv.rp.unit")) + '">'
      + units.map(function (u) { return '<option value="' + u + '"' + (r.unit === u ? " selected" : "") + ">" + esc(tw(RP_KEYS[u])) + "</option>"; }).join("") + "</select></div>";
    if (r.unit === "week") {
      h += '<div class="nv-wds">' + [1, 2, 3, 4, 5, 6, 0].map(function (d) { var on = (r.days || []).indexOf(d) >= 0; return '<button type="button" class="nv-wd' + (on ? " on" : "") + '" data-act="rp-day" data-v="' + d + '" aria-pressed="' + on + '">' + esc(tw(WD_KEYS[d])) + "</button>"; }).join("") + "</div>";
    }
    return h + '<div class="nv-acts two"><button type="button" class="nv-btn ghost" data-act="rp-clear">' + esc(tw("nv.rp.clear")) + '</button><button type="button" class="nv-btn pri" data-act="rp-ok">' + esc(tw("nv.dp.ok")) + "</button></div>";
  }

  // ---------- habits: list head, mascot, checkbox, streak card (0.424.0) ----------
  // The mascot is Javis's own star (dashboard/pet.js): all feeling sits in the eyes, no mouth.
  var PET_STAR = "M145 81 Q160 59.4 175 81 L177.9 85.1 Q195.8 110.7 225.8 119.9 L230.6 121.3 Q255.7 128.9 239.8 149.8 L236.8 153.8 Q217.9 178.8 218.5 210.1 L218.6 215.1 Q219.1 241.4 194.3 232.8 L189.6 231.1 Q160 220.8 130.4 231.1 L125.7 232.8 Q100.9 241.4 101.4 215.1 L101.5 210.1 Q102.1 178.8 83.2 153.8 L80.2 149.8 Q64.3 128.9 89.4 121.3 L94.2 119.9 Q124.2 110.7 142.1 85.1 Z";
  var PET_EYES = {
    neutral: '<ellipse rx="7.2" ry="17.5"/>', curious: '<ellipse cy="-2" rx="8.4" ry="21"/>', excited: '<ellipse cy="-1" rx="9.2" ry="22.5"/>',
    happy: '<path class="pl" d="M-9 6 Q0 -7 9 6"/>', sleepy: '<path class="pl" d="M-9 6 H9"/>',
    suspicious: ['<path class="pl" d="M-9 -3 H9"/>', '<path class="pl" d="M-9 2 H9"/>'],
    wink: ['<path class="pl" d="M-9 3 Q0 -7 9 3"/>', '<ellipse rx="7.2" ry="17.5"/>'],
    love: '<path d="M0 11 C-15 0 -13 -13 -5.5 -13 C-2 -13 0 -10 0 -7.5 C0 -10 2 -13 5.5 -13 C13 -13 15 0 0 11 Z"/>',
    gang: ['<path class="pl" d="M-8 -9 L6 0 L-8 9"/>', '<path class="pl" d="M8 -9 L-6 0 L8 9"/>']
  };
  function jstar(mood) {
    var e = PET_EYES[mood] || PET_EYES.neutral, L = typeof e === "string" ? e : e[0], R = typeof e === "string" ? e : e[1];
    var flat = /sleepy|love/.test(mood), dx = flat ? 0 : 7, dy = flat ? 6 : -4;
    return '<svg class="nv-star m-' + mood + '" viewBox="56 50 208 200" aria-hidden="true"><path d="' + PET_STAR + '" fill="#fd6100"/><g class="je"><g transform="translate(' + (145 + dx) + " " + (160 + dy) + ')">' + L + '</g><g transform="translate(' + (175 + dx) + " " + (160 + dy) + ')">' + R + "</g></g></svg>";
  }
  var FLAME = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5c.6 3.4 5.5 6 5.5 11.2A5.6 5.6 0 0 1 12 19.5a5.6 5.6 0 0 1-5.5-5.8c0-2.6 1.4-4.2 2.6-5.4.2 1.8 1 2.9 2.2 3.4C11 9 11 5.6 12 2.5z"/></svg>';
  // The tick of a habit: a ring; an icy dot while frozen; a dashed ring on a rest day; a flame when done.
  function habitCk(t, cls) {
    var k = habitCalc(t, today()), on = k.doneToday, ice = !on && k.frozen;
    if (k.rest && !on) return '<span class="nv-hck rest' + (cls ? " " + cls : "") + (ice ? " ice" : "") + '" data-act="hrest" data-id="m:' + esc(t.id) + '" role="img" aria-label="' + esc(tw("nv.h.rest_aria", { t: t.title })) + '" title="' + esc(tw("nv.h.rest_t")) + '"><i class="hx-ring' + (ice ? " icy" : "") + '"></i></span>';
    var lit = on && S.lit && S.lit.id === t.id ? S.lit : null;
    var fx = lit ? (lit.ice ? '<i class="hx-ring icy hx-melt"></i>' : "") + '<i class="hx-wave"></i>' : "";
    return '<span class="nv-hck' + (cls ? " " + cls : "") + (on ? " on" : ice ? " ice" : "") + (lit ? " lit" + (lit.ice ? " thaw" : "") : "") + '" data-act="' + (on ? "uncheck" : "check") + '" data-id="m:' + esc(t.id) + '" role="checkbox" aria-checked="' + on + '" tabindex="0" aria-label="' + esc(on ? tw("nv.a.uncheck") : tw("nv.h.tick", { t: t.title })) + '" title="' + esc(on ? tw("nv.h.lit_t") : ice ? tw("nv.h.ice_t") : tw("nv.h.tick_t")) + '">'
      + (on ? FLAME : '<i class="hx-ring' + (ice ? " icy" : "") + '"></i>') + fx + "</span>";
  }
  function stkBadge(t) {
    var k = habitCalc(t, today()); if (!k || !k.cur) return "";
    return '<span class="nv-stkb' + (k.frozen ? " ice" : k.doneToday || k.rest ? "" : " dim") + '">' + (k.frozen ? ic("snowflake") : FLAME) + k.cur + "</span>";
  }
  function habitHead() {
    var st = habitStats(S.my.tasks, today()); if (!st.H.length) return "";
    var M = habitLines(st, today(), S.my.coach), i = (S.hmsg || 0) % M.length;
    var wkc = st.wk >= 80 ? "ok" : st.wk >= 50 ? "mid" : st.wk > 0 ? "low" : "off";
    var tile = function (icon, cls, v, lb) { return '<div class="nv-hs-t ' + cls + '">' + icon + "<b>" + esc(v) + "</b><span>" + esc(lb) + "</span></div>"; };
    var h = '<div class="nv-hs">' + tile(FLAME, st.due && st.done === st.due ? "f" : "f off", st.due ? st.done + "/" + st.due : tw("nv.h.rest_short"), tw("nv.d.today"))
      + tile(ic("snowflake"), st.ice ? "i" : "i off", st.ice, tw("nv.h.frozen")) + tile(ic("trophy"), st.top && st.top.k.cur ? "tr" : "tr off", st.top ? st.top.k.cur : 0, tw("nv.h.longest"))
      + tile(ic("circle-check"), wkc, st.wk + "%", tw("nv.h.week")) + "</div>";
    if (!S.hmsgHide) {
      h += '<div class="nv-talk">' + jstar(M[i].mood) + '<div class="nv-bub" aria-live="polite"><span class="nv-bubs">' + M.map(function (m, n) { return '<span class="nv-bubt' + (n === i ? " on" : "") + '"' + (n === i ? "" : ' aria-hidden="true"') + ">" + esc(m.tx) + "</span>"; }).join("") + "</span>"
        + (M.length > 1 ? '<button type="button" class="nv-bubn" data-act="hmsg" aria-label="' + esc(tw("nv.h.next_line")) + '">' + M.map(function (_, n) { return "<i" + (n === i ? ' class="on"' : "") + "></i>"; }).join("") + ic("chevron-right") + "</button>" : "")
        + '</div><button type="button" class="nv-x nv-bubx" data-act="hmsgx" aria-label="' + esc(tw("nv.h.hide_line")) + '">' + ic("x") + "</button></div>";
    }
    return h;
  }
  function habitRow(r) {
    var t = r.raw, k = habitCalc(t, today());
    var nx = k.rest && !k.doneToday ? tw("nv.h.rest_today") + (k.next ? " · " + tw("nv.rep.next", { t: whenIso(k.next, t.time) }) : "")
      : k.doneToday ? tw("nv.rep.done_today") + (k.next ? " · " + tw("nv.rep.next", { t: whenIso(k.next, t.time) }) : "") : tw("nv.rep.next", { t: whenIso(today(), t.time) });
    return '<div class="nv-rrow habit">' + habitCk(t, "big") + '<button type="button" class="nv-grow" data-open="' + esc(r.id) + '"><span class="nv-ti">' + esc(r.title) + stkBadge(t) + '</span><span class="nv-sc">' + esc(r.sc) + '</span><span class="nv-nx">' + esc(nx) + "</span></button>"
      + '<button type="button" class="nv-dots" data-act="menu" data-id="' + esc(r.id) + '" aria-label="' + esc(tw("nv.a.more")) + '">' + ic("ellipsis") + "</button></div>";
  }
  function habitView() {
    var H = S.me.recurring.filter(function (r) { return r.habit && (!q() || r.title.toLowerCase().indexOf(q()) >= 0); });
    var key = function (r) { var t = r.raw, k = habitCalc(t, today()); return (k.rest && !k.doneToday ? "1" : "0") + (usualTime(t) || t.time || "99:99"); };
    H.sort(function (a, b) { return key(a) < key(b) ? -1 : key(a) > key(b) ? 1 : 0; });
    return habitHead() + (H.length ? H.map(habitRow).join("") : '<div class="nv-empty">' + esc(tw("nv.h.empty")) + "</div>");
  }
  // The streak card under a habit's details: big number, three tiles, a month calendar (rest days thread the chain),
  // the reminder choice, and what Javis has learned about it.
  function streakCard(t) {
    var k = habitCalc(t, today()); if (!k) return "";
    var td = today(), off = S.stkOff || 0, base = new Date(td + "T12:00:00"); base.setDate(1); base.setMonth(base.getMonth() + off);
    var Y = base.getFullYear(), Mo = base.getMonth(), first = isoOf(base), nDays = new Date(Y, Mo + 1, 0).getDate(), lead = (base.getDay() + 6) % 7;
    var startM = (t.habit.start || k.anchor).slice(0, 7), canPrev = first.slice(0, 7) > startM, canNext = off < 0;
    var near = function (d, dir) { for (var x = addDays(d, dir), n = 0; n < 40; x = addDays(x, dir), n++) { var st = k.days[x]; if (st === undefined) return dir > 0 ? "end" : null; if (st !== "r") return st; } return null; };
    var inChain = function (d) { var st = k.days[d]; if (st === "f" || st === "i") return true; if (st !== "r") return false; var a = near(d, -1), b2 = near(d, 1); return (a === "f" || a === "i") && (b2 === "f" || b2 === "i" || b2 === "todo" || b2 === "end"); };
    var cells = "", nDone = 0, nIce = 0, anyJ = false;
    for (var i = 0; i < lead; i++) cells += '<span class="sd e"></span>';
    for (var n = 1; n <= nDays; n++) {
      var d = first.slice(0, 8) + pad2(n), st = k.days[d], wd = (lead + n - 1) % 7, jv = k.by[d] && k.by[d].by === "javis";
      if (st === "f") { nDone++; if (jv) anyJ = true; }
      if (st === "i") nIce++;
      var cls = "sd";
      if (inChain(d)) {
        cls += " " + (st === "r" ? "rs" : st);
        if (!(wd > 0 && n > 1 && inChain(addDays(d, -1)))) cls += " l";
        if (!(wd < 6 && n < nDays && inChain(addDays(d, 1)))) cls += " rr";
      } else if (st === "x") cls += " x";
      else if (!st) cls += occursOn(t.repeat, k.anchor, d) ? " fu" : " fu off";
      else if (st === "r") cls += " off";
      if (d === td) cls += " tdy";
      var edit = (d === td && st !== "r") || (d === k.last);
      var lab = tw(st === "f" ? (jv ? "nv.h.c_done_j" : "nv.h.c_done") : st === "i" ? "nv.h.c_ice" : st === "x" ? "nv.h.c_lost" : st === "todo" ? "nv.h.c_todo" : st === "r" ? "nv.h.c_rest" : "nv.h.c_later", { d: n + "/" + (Mo + 1) });
      cells += (edit ? '<button type="button" class="' + cls + '" data-act="hday" data-id="m:' + esc(t.id) + '" data-v="' + d + '" aria-label="' + esc(lab) + '" title="' + esc(lab) + '">' : '<span class="' + cls + '" title="' + esc(lab) + '">') + n + (jv ? '<i class="jv"></i>' : "") + (edit ? "</button>" : "</span>");
    }
    var nx = k.rest ? k.next : td;
    var msg = k.frozen ? '<div class="nv-stk-msg">' + ic("snowflake") + "<span>" + esc(tw("nv.h.frozen_msg", { last: dayWord(k.last, td), next: dayWord(nx, td) })) + "</span></div>" : "";
    var hb = t.habit, ut = usualTime(t);
    var remind = '<label class="nv-kv"><span>' + ic("bell") + esc(tw("nv.h.remind")) + '</span><select class="nv-psel" data-hrem="' + esc(t.id) + '" aria-label="' + esc(tw("nv.h.remind")) + '">'
      + [["auto", "nv.h.r_auto"], ["time", "nv.h.r_time"], ["off", "nv.h.r_off"]].map(function (o) { return '<option value="' + o[0] + '"' + (hb.remind === o[0] ? " selected" : "") + ">" + esc(tw(o[1])) + "</option>"; }).join("") + "</select></label>";
    if (hb.remind === "time") {
      var opts = ""; for (var j = 0; j < 48; j++) { var tt = pad2(Math.floor(j / 2)) + ":" + (j % 2 ? "30" : "00"); opts += "<option" + (tt === hb.at ? " selected" : "") + ">" + tt + "</option>"; }
      remind += '<label class="nv-kv"><span>' + ic("clock") + esc(tw("nv.h.at")) + '</span><select class="nv-psel" data-hat="' + esc(t.id) + '" aria-label="' + esc(tw("nv.h.at")) + '">' + opts + "</select></label>";
    }
    if (hb.remind === "auto") {
      var plan = k.doneToday ? tw("nv.h.ai_done") : k.frozen ? tw("nv.h.ai_ice", { t: autoAt(t, k) }) : k.rest ? tw("nv.h.ai_rest") : tw("nv.h.ai_plan", { t: autoAt(t, k) });
      remind += '<div class="nv-ai">' + avatar(CORE, 20) + "<span>" + esc((ut ? tw("nv.h.ai_usual", { t: ut }) + " " : "") + plan) + "</span></div>";
    }
    return '<div class="nv-stk' + (k.frozen ? " frozen" : "") + (k.doneToday || (k.rest && !k.frozen) ? " lit" : "") + '">'
      + '<div class="nv-stk-top"><div><div class="nv-stk-n">' + k.cur + '</div><div class="nv-stk-l">' + esc(tw("nv.h.days_lit")) + '</div></div><span class="nv-stk-big">' + (k.frozen ? ic("snowflake") : FLAME) + "</span></div>"
      + msg + '<div class="nv-stk-tiles"><div><b>' + nDone + "</b><span>" + esc(tw("nv.h.t_done")) + "</span></div><div><b>" + nIce + "</b><span>" + esc(tw("nv.h.frozen")) + "</span></div><div><b>" + k.best + "</b><span>" + esc(tw("nv.h.longest")) + "</span></div></div>"
      + '<div class="nv-stk-mh"><b>' + esc(base.toLocaleDateString(LOC(), { month: "long", year: "numeric" })) + '</b><span><button type="button" class="nv-x" data-act="hmon" data-v="-1" aria-label="' + esc(tw("nv.dp.prev")) + '"' + (canPrev ? "" : " disabled") + ">" + ic("chevron-left") + '</button><button type="button" class="nv-x" data-act="hmon" data-v="1" aria-label="' + esc(tw("nv.dp.next")) + '"' + (canNext ? "" : " disabled") + ">" + ic("chevron-right") + "</button></span></div>"
      + '<div class="nv-stk-cal">' + [1, 2, 3, 4, 5, 6, 0].map(function (w) { return '<span class="wh">' + esc(tw(WD_KEYS[w])) + "</span>"; }).join("") + cells + "</div>"
      + (anyJ ? '<div class="nv-stk-leg"><i class="jv"></i>' + esc(tw("nv.h.by_javis")) + "</div>" : "")
      + '<div class="nv-stk-rem">' + remind + "</div></div>";
  }
  // When "Javis reminds on its own" nudges today: an hour after the usual time (or the set time), earlier while frozen.
  function autoAt(t, k) {
    var base = usualTime(t) || t.time || t.habit.at || "21:00", m = Number(base.slice(0, 2)) * 60 + Number(base.slice(3, 5));
    m = k && k.frozen ? Math.max(6 * 60, m - 30) : Math.min(23 * 60, m + 30);
    return pad2(Math.floor(m / 60)) + ":" + pad2(m % 60);
  }

  // 0.426.0: the reminder options the old Scheduled page had (level, call, read aloud, remember last), only when
  // the job will be a reminder: it has a time or a repeat, or only reminds, or is a reminder being edited.
  function remOpts(f) {
    if (f.script || (!f.edit && !f.date && !f.rule && f.mode !== "remind")) return "";   // a script job keeps its own type
    var box = function (k, label) { return '<label class="nv-prep"><input type="checkbox" data-act="fset" data-k="' + k + '" data-v="' + (f[k] ? "" : "1") + '"' + (f[k] ? " checked" : "") + "><span>" + esc(tw(label)) + "</span></label>"; };
    var lv = f.mq || "full";
    return (f.mode === "do" ? '<div class="nv-fld"><span>' + esc(tw("nv.lp.mode")) + "</span>" + '<div class="nv-seg" role="group">' + [["suggest", "nv.lp.m_suggest"], ["auto", "nv.lp.m_auto"], ["full", "nv.lp.m_full"]].map(function (o) { return '<button type="button" data-act="fset" data-k="mq" data-v="' + o[0] + '" aria-pressed="' + (lv === o[0]) + '">' + esc(tw(o[1])) + "</button>"; }).join("") + "</div>"
        + '<small class="nv-hint' + (lv === "full" ? " full" : "") + '" role="status">' + esc(tw(LP_NOTE[lv])) + "</small></div>" : "")
      + '<div class="nv-fld nv-opts">' + box("call", "nv.f.call") + box("speak", "nv.f.speak") + (f.mode === "do" ? box("last", "nv.f.last") : "") + "</div>";
  }

  // 0.426.0: a job queued right away keeps the old board's "review the result when done" box, its explanation behind (i).
  function jobOpts(f) {
    if (f.edit || f.date || f.rule || f.mode !== "do") return "";
    var J = window.JavisInfo, more = tw("info.more");
    return '<div class="nv-fld nv-opts"><div class="nv-apr"><label class="nv-prep"><input type="checkbox" data-act="fset" data-k="appr" data-v="' + (f.appr ? "" : "1") + '"' + (f.appr ? " checked" : "") + "><span>" + esc(tw("kanban.need_approve")) + "</span></label>"
      + (J ? J.btn(more) : "") + "</div>" + (J ? J.body(esc(tw("kanban.need_approve_info"))) : "") + "</div>";
  }

  // ---------- add form ----------
  function formHtml() {
    var f = S.form, me = f.who === "me";
    var seg = function (key, opts) { return '<div class="nv-seg" role="group">' + opts.map(function (o) { return '<button type="button" data-act="fset" data-k="' + key + '" data-v="' + o[0] + '" aria-pressed="' + (f[key] === o[0]) + '">' + (o[2] || "") + esc(tw(o[1])) + "</button>"; }).join("") + "</div>"; };
    var repTxt = f.rule ? (f.rule.unit === "min" || f.rule.unit === "hour" ? tw(f.rule.unit === "min" ? "nv.rep.every_min" : "nv.rep.every_hours", { n: f.rule.n || 1 }) : repHuman(f.rule)) : tw("nv.f.rep_none");
    var head = '<div class="nv-scrim" data-act="close"></div><div class="nv-modal" role="dialog" aria-modal="true" aria-labelledby="nvFormT"><form data-form="1">'
      + '<div class="nv-mh"><h3 id="nvFormT">' + esc(f.loop ? tw("nv.lp.edit") : f.edit ? tw("nv.f.edit") : f.kind === "appt" ? tw("nv.ap.new") : me ? tw("nv.f.new_me") : tw("nv.f.new")) + '</h3><button type="button" class="nv-x" data-act="close" aria-label="' + esc(tw("nv.close")) + '">' + ic("x") + "</button></div>"
      + (f.edit || f.loop ? "" : '<div class="nv-seg nv-kindseg" role="group">' + [["task", "circle-check", "nv.ap.k_task"], ["appt", "calendar", "nv.ap.k_appt"]].map(function (o) { return '<button type="button" data-act="fset" data-k="kind" data-v="' + o[0] + '" aria-pressed="' + ((f.kind || "task") === o[0]) + '">' + ic(o[1]) + esc(tw(o[2])) + "</button>"; }).join("") + "</div>");
    if (f.loop) {
      // 0.426.0: a loop's own fields, the ones the old Scheduled page let the owner edit by hand.
      return head + '<label class="nv-fld"><span>' + esc(tw("nv.lp.name")) + '</span><input class="nv-inp" id="nvLn" required value="' + esc(f.name || "") + '"></label>'
        + '<label class="nv-fld"><span>' + esc(tw("nv.lp.body")) + '</span><textarea class="nv-ta" id="nvW" required>' + esc(f.text || "") + "</textarea></label>"
        + '<div class="nv-fld"><span>' + esc(tw("nv.lp.mode")) + "</span>" + seg("lmode", [["suggest", "nv.lp.m_suggest"], ["auto", "nv.lp.m_auto"], ["full", "nv.lp.m_full"]])
        + '<small class="nv-hint' + ((f.lmode || "full") === "full" ? " full" : "") + '" role="status">' + esc(tw(LP_NOTE[f.lmode] || LP_NOTE.full)) + "</small></div>"
        + '<label class="nv-fld"><span>' + esc(tw("nv.lp.every")) + '</span><input class="nv-inp" id="nvIv" type="number" min="5" step="5" inputmode="numeric" value="' + esc(f.iv || "60") + '"></label>'
        + (f.err ? '<div class="nv-ferr" role="alert">' + esc(f.err) + "</div>" : "")
        + '<div class="nv-acts end"><button type="button" class="nv-btn ghost" data-act="close">' + esc(tw("nv.cancel")) + '</button><button type="submit" class="nv-btn pri">' + esc(tw("nv.save")) + "</button></div></form></div>";
    }
    if (f.kind === "appt") {
      var dur = Number(f.dur || 60);
      return head + '<label class="nv-fld"><span>' + esc(tw("nv.ap.what")) + '</span><input class="nv-inp" id="nvW" required placeholder="' + esc(tw("nv.ap.what_ph")) + '" value="' + esc(f.text || "") + '"></label>'
        + '<div class="nv-fld"><span>' + esc(tw("nv.ap.start")) + '</span><button type="button" class="nv-pick" data-act="pick-date" data-id="new">' + ic("clock") + '<span class="nv-lbl">' + esc(whenIso(f.date, f.time)) + "</span>" + ic("chevron-right") + "</button></div>"
        + '<div class="nv-row2"><label class="nv-fld"><span>' + esc(tw("nv.ap.dur")) + "</span>" + durSelect(dur, 'id="nvDur"').replace('class="nv-psel"', 'class="nv-inp"') + "</label>"
        + '<label class="nv-fld"><span>' + esc(tw("nv.ap.remind")) + "</span>" + remSelect(f.remind || "15", 'id="nvRem"').replace('class="nv-psel"', 'class="nv-inp"') + "</label></div>"
        + '<div class="nv-row2"><div class="nv-fld"><span>' + esc(tw("nv.k.repeat")) + '</span><button type="button" class="nv-pick" data-act="pick-rep" data-id="new">' + ic("repeat") + '<span class="nv-lbl">' + esc(repTxt) + "</span>" + ic("chevron-right") + "</button></div>"
        + '<label class="nv-fld"><span>' + esc(tw("nv.k.project")) + "</span>" + projSelect({ id: "new", project: f.project || "" }, "nv-inp") + "</label></div>"
        + '<details class="nv-more2"' + (f.loc ? " open" : "") + "><summary>" + ic("map-pin") + esc(tw("nv.ap.where")) + '</summary><input class="nv-inp" id="nvLoc" placeholder="' + esc(tw("nv.ap.where_ph")) + '" value="' + esc(f.loc || "") + '"></details>'
        + '<label class="nv-prep"><input type="checkbox" id="nvPrep"' + (f.prep ? " checked" : "") + ' data-act="fset" data-k="prep" data-v="' + (f.prep ? "" : "1") + '">' + avatar(CORE, 18) + "<span>" + esc(tw("nv.ap.prep")) + "</span></label>"
        + (f.prep ? '<input class="nv-inp" id="nvPrepT" placeholder="' + esc(tw("nv.ap.prep_ph")) + '" value="' + esc(f.prepT || "") + '">' : "")
        + (f.err ? '<div class="nv-ferr" role="alert">' + esc(f.err) + "</div>" : "")
        + '<div class="nv-acts end"><button type="button" class="nv-btn ghost" data-act="close">' + esc(tw("nv.cancel")) + '</button><button type="submit" class="nv-btn pri">' + esc(tw("nv.ap.add")) + "</button></div></form></div>";
    }
    return head
      + '<label class="nv-fld"><span>' + esc(tw("nv.f.what")) + '</span><textarea class="nv-ta" id="nvW" required placeholder="' + esc(me ? tw("nv.f.what_ph_me") : tw("nv.f.what_ph")) + '">' + esc(f.text || "") + "</textarea></label>"
      + (f.edit ? "" : '<div class="nv-fld"><span>' + esc(tw("nv.f.who")) + "</span>" + seg("who", [["me", "nv.me", ic("circle-user")], ["ai", "nv.javis", avatar(CORE, 16)]]) + "</div>")
      + (me || f.script ? "" : '<div class="nv-fld"><span>' + esc(tw("nv.k.how")) + "</span>" + seg("mode", [["do", "nv.mode.do"], ["remind", "nv.mode.remind"]]) + "</div>")
      + '<div class="nv-row2"><div class="nv-fld"><span>' + esc(tw("nv.k.when")) + '</span><button type="button" class="nv-pick" data-act="pick-date" data-id="new">' + ic("clock") + '<span class="nv-lbl">' + esc(f.date ? whenIso(f.date, f.time) : me ? tw("nv.d.none") : tw("nv.f.asap")) + "</span>" + ic("chevron-right") + "</button></div>"
      + '<div class="nv-fld"><span>' + esc(tw("nv.k.repeat")) + '</span><button type="button" class="nv-pick" data-act="pick-rep" data-id="new"' + (f.edit && f.cronLocked ? " disabled" : "") + ">" + ic("repeat") + '<span class="nv-lbl">' + esc(repTxt) + "</span>" + ic("chevron-right") + "</button></div></div>"
      + (me && f.rule && f.rule.unit !== "min" && f.rule.unit !== "hour" ? '<div class="nv-fld"><span>' + esc(tw("nv.h.kind")) + "</span>" + seg("habit", [["", "nv.l.rep", ic("repeat")], ["1", "nv.l.habit", ic("flame", "c-habit")]]) + "</div>" : "")
      + (me ? '<label class="nv-fld"><span>' + esc(tw("nv.k.project")) + "</span>" + projSelect({ id: "new", project: f.project || "" }, "nv-inp") + "</label>" : remOpts(f) + jobOpts(f))
      + (f.err ? '<div class="nv-ferr" role="alert">' + esc(f.err) + "</div>" : "")
      + '<div class="nv-acts end"><button type="button" class="nv-btn ghost" data-act="close">' + esc(tw("nv.cancel")) + '</button><button type="submit" class="nv-btn pri">' + esc(f.edit ? tw("nv.save") : me ? tw("nv.f.add") : tw("nv.f.give")) + "</button></div></form></div>";
  }
  function openForm(it) {
    if (it && it.src === "loop") {
      var lp = it.raw || {};
      S.form = { loop: it.ref, name: lp.name || it.ref, text: lp.body || "", lmode: lp.mode || "full", iv: String(lp.interval_min || 60) };
    } else if (it && it.src === "reminder") {
      var raw = it.raw || {}, ts = stamp(raw.due_at);
      S.form = { edit: it.ref, who: "ai", text: raw.text || it.title, mode: raw.mode === "notify" ? "remind" : "do", date: ts.date, time: ts.time, rule: null, cronLocked: !!(raw.cron || raw.repeat_min),
        mq: raw.muc_quyen || "full", call: raw.call ? "1" : "", speak: raw.speak ? "1" : "", last: raw.remember_last ? "1" : "", script: raw.mode === "script" };
    } else {
      var inHabit = S.tab === "me" && (S.view === "habit" || (S.phone.screen === "list" && S.phone.list === "habit"));
      S.form = { who: S.tab === "me" ? "me" : "ai", text: "", mode: "do", date: null, time: "", rule: inHabit ? { unit: "day", n: 1 } : null, habit: inHabit ? "1" : "",
        project: S.view.indexOf("proj:") === 0 ? S.view.slice(5) : (S.phone.screen === "list" && String(S.phone.list).indexOf("proj:") === 0 ? S.phone.list.slice(5) : "") };
    }
    S.layer = "form"; renderLayer();
    var w = S.root.querySelector("#nvW"); if (w) w.focus();
  }
  function keepFormText() {
    if (!S.form) return;
    var g = function (sel) { return S.root.querySelector(sel); };
    if (g("#nvW")) S.form.text = g("#nvW").value;
    if (g('[data-pproj="new"]')) S.form.project = g('[data-pproj="new"]').value;
    if (g("#nvDur")) S.form.dur = g("#nvDur").value;
    if (g("#nvRem")) S.form.remind = g("#nvRem").value;
    if (g("#nvLoc")) S.form.loc = g("#nvLoc").value;
    if (g("#nvPrepT")) S.form.prepT = g("#nvPrepT").value;
    if (g("#nvLn")) S.form.name = g("#nvLn").value;
    if (g("#nvIv")) S.form.iv = g("#nvIv").value;
  }
  async function submitForm() {
    keepFormText();
    var f = S.form, txt = (f.text || "").trim();
    if (!txt) return;
    var b = brain(), r;
    if (f.loop) {
      r = await postForm("/loops", { brain: b, slug: f.loop, name: (f.name || "").trim() || f.loop, body: txt, mode: f.lmode || "full",
        interval_min: String(Math.max(5, Number(f.iv) || 60)) });
    } else if (f.edit) {
      var fields = f.script ? { id: f.edit, brain: b, text: txt } : { id: f.edit, brain: b, text: txt, mode: f.mode === "remind" ? "notify" : "task", muc_quyen: f.mq || "full",
        call: f.call ? "true" : "false", speak: f.speak ? "true" : "false", remember_last: f.mode === "do" && f.last ? "true" : "false" };
      if (!f.cronLocked && f.date) fields.at = f.date + "T" + (f.time || "08:00");
      r = await postForm("/reminders/update", fields);
    } else if (f.kind === "appt") {
      if (!f.date || !f.time) { f.err = tw("nv.ap.need_time"); renderLayer(); return; }
      var end = fromMin(toMin(f.time) + Number(f.dur || 60));
      r = await postJSON("/my-tasks", { brain: b, kind: "appt", title: txt, date: f.date, time: f.time, end: end, remind: String(f.remind || "15"),
        location: f.loc || "", repeat: f.rule && f.rule.unit !== "min" && f.rule.unit !== "hour" ? f.rule : null, project: f.project || "",
        prep: f.prep ? (f.prepT || tw("nv.ap.prep_default")) : "" });
      if (r && r.ok !== false && f.prep) {
        // "Ask Javis to prepare": a reminder that does the job 30 minutes before the start.
        var at = fromMin(toMin(f.time) - 30);
        await createReminder((f.prepT || tw("nv.ap.prep_default")) + " (" + txt + ", " + f.date + " " + f.time + ")", "do", f.date, at, null);
      }
    } else if (f.who === "me") {
      var myRule = f.rule && f.rule.unit !== "min" && f.rule.unit !== "hour" ? f.rule : null;
      r = await postJSON("/my-tasks", { brain: b, title: txt, date: f.date || (myRule && f.habit ? today() : null), time: f.date ? f.time : "", repeat: myRule, project: f.project || "",
        habit: myRule && f.habit ? { start: today(), remind: "auto" } : null });
    } else if (!f.date && !f.rule && f.mode === "do") {
      r = await postForm("/kanban/task", { brain: b, title: txt.slice(0, 120), intent: txt, priority: 2, needs_approval: f.appr ? "1" : "0" });
    } else {
      r = await createReminder(txt, f.mode, f.date, f.time, f.rule, { muc_quyen: f.mq || "full", call: !!f.call, speak: !!f.speak, remember_last: f.mode === "do" && !!f.last });
      if (r === null) return;
    }
    if (r && r.ok === false) { f.err = r.error || tw("nv.err.generic"); renderLayer(); return; }
    S.layer = null; S.form = null; renderLayer();
    toast(f.edit || f.loop ? tw("nv.saved") : f.kind === "appt" ? tw("nv.ap.added") : f.who === "me" ? (f.habit && f.rule ? tw("nv.h.added") : tw("nv.f.added")) : tw("nv.f.given"));
    await load(); render(); schedulePoll();
  }
  async function createReminder(txt, mode, date, time, rule, opts) {
    var body = Object.assign({ brain: brain(), text: txt, label: txt.slice(0, 80), mode: mode === "remind" ? "notify" : "task", muc_quyen: "full", created_by: "dashboard" },
      opts || {}, javisSchedule(rule, date || today(), time || "08:00"));
    var r = await postJSON("/reminders", body);
    if (r && r.ok === false && r.can_force) {
      if (!window.confirm(r.error + "\n\n" + tw("nv.f.force"))) return null;
      body.allow_no_channel = true;
      r = await postJSON("/reminders", body);
    }
    return r;
  }

  // ---------- pickers state ----------
  function pickTarget(id) {
    if (id === "new") return { date: S.form.date, time: S.form.time, rule: S.form.rule, javis: S.form.who !== "me" };
    var it = find(id), t = it && it.raw;
    return { date: (it.occ && t.repeat ? it.occ : t.date) || null, time: t.time || "", rule: t.repeat || null, javis: false, task: t };
  }
  async function applyPick(id, patch) {
    if (id === "new") { Object.assign(S.form, patch); S.sheet = null; renderLayer(); return; }
    var it = find(id); if (!it) return;
    var t = it.raw, before = { date: t.date, time: t.time, repeat: t.repeat };
    var body = { __url: "/my-tasks/update", id: t.id };
    if ("date" in patch) { body.date = patch.date; body.time = patch.date ? patch.time || "" : ""; }
    if (t.kind === "appt" && "date" in patch) {
      // An appointment keeps its length when its start moves.
      if (!patch.date || !patch.time) { S.sheet = null; toast(tw("nv.ap.need_time")); renderLayer(); return; }
      body.end = fromMin(toMin(patch.time) + Math.max(5, toMin(t.end) - toMin(t.time)));
    }
    if ("rule" in patch) { body.repeat = patch.rule; if (patch.rule && !t.date && !body.date) body.date = today(); }
    S.sheet = null;
    await act(mine(body), tw("nv.saved"), function () { return mine({ __url: "/my-tasks/update", id: t.id, date: before.date, time: before.time, repeat: before.repeat }); });
  }

  // ---------- actions ----------
  function mineRef(id) { var p = id.split(":"); return { id: p[1], date: p[2] || "" }; }
  async function doAct(a, id, el) {
    var b = brain(), it = id ? find(id) : null;
    switch (a) {
      case "check": case "uncheck": {
        var m = mineRef(id), t = it && it.raw, date = m.date || (t && t.repeat ? (it.occ || today()) : "");
        if (t && t.repeat && it.sc) date = today();
        var on = a === "check";
        if (on && t && habitOn(t) && date === today()) {
          // A habit ticked today lights up: a short flat pop (thawing first when it was frozen) and one short buzz.
          var hk = habitCalc(t, today());
          if (hk.rest) return doAct("hrest", id);
          S.lit = { id: t.id, ice: hk.frozen }; S.hmsg = 0;
          try { if (navigator.vibrate) navigator.vibrate(12); } catch (e) { /* not on desktop */ }
          clearTimeout(S.litT); S.litT = setTimeout(function () { if (S) { S.lit = null; render(); } }, 700);
          var res = await act(mine({ __url: "/my-tasks/check", id: m.id, date: date }), "", null);
          if (res && res.ok !== false) { var k2 = habitCalc(res.task, today()); toast((hk.frozen ? tw("nv.h.thawed") + " " : "") + tw("nv.h.lit", { n: k2.cur }), function () { mine({ __url: "/my-tasks/uncheck", id: m.id, date: date }).then(load).then(render); }); }
          return;
        }
        return act(mine({ __url: on ? "/my-tasks/check" : "/my-tasks/uncheck", id: m.id, date: date }), on ? tw("nv.ok.done", { t: it ? it.title : "" }) : tw("nv.ok.undone"),
          function () { return mine({ __url: on ? "/my-tasks/uncheck" : "/my-tasks/check", id: m.id, date: date }); });
      }
      case "run":
        if (!it) return;
        if (it.src === "kanban") return act(postForm("/kanban/run", { brain: b, id: it.ref }), tw("nv.ok.run"));
        if (it.src === "reminder") return act(postForm("/reminders/run-now", { brain: b, id: it.ref }), tw("nv.ok.run"));
        if (it.src === "loop") return act(postForm("/loops/run-now", { brain: b, slug: it.ref }), tw("nv.ok.run"));
        return;
      case "stop":
        if (!it) return;
        if (it.src === "kanban") return act(postForm("/kanban/task/cancel", { brain: b, id: it.ref }), tw("nv.ok.stop"));
        if (it.src === "reminder") return act(postForm("/reminders/stop", { id: it.ref }), tw("nv.ok.stop"));
        if (it.src === "loop") return act(postForm("/loops/stop", { brain: b }), tw("nv.ok.stop"));
        return;
      case "rrun":
        if (!it) return;
        if (it.src === "reminder") return act(postForm("/reminders/run-now", { brain: b, id: it.ref }), tw("nv.ok.run"));
        if (it.src === "loop") return act(postForm("/loops/run-now", { brain: b, slug: it.ref }), tw("nv.ok.run"));
        if (it.src === "watch") return act(postJSON("/watch/action", { id: it.ref, action: "check_now", brain: b }), tw("nv.ok.run"));
        return;
      case "rstop": return doAct("stop", id);
      case "rtog": case "m-rtog": {
        var r = S.ai.recurring.find(function (x) { return x.id === id; });
        if (!r) return;
        S.sheet = null;
        var wasOn = r.on;
        return act(toggleRep(r, !wasOn), wasOn ? tw("nv.ok.paused") : tw("nv.ok.resumed"), function () { return toggleRep(r, wasOn); });
      }
      case "m-gopen": S.sheet = null; if (it && it.raw && /^https:\/\//.test(it.raw.link || "")) window.open(it.raw.link, "_blank", "noopener"); return renderLayer();
      case "m-skip": S.sheet = null; return act(postForm("/reminders/skip", { brain: b, id: it.ref }), tw("nv.ok.skip"));
      case "m-edit":
        S.sheet = null;
        if (it.src === "mine") { S.sel = window.innerWidth > 760 ? it.id.replace(/^m[odn]:([^:]+):.*$/, "m:$1") : S.sel; renderLayer(); if (window.innerWidth <= 760) openDetail(it.id); var te = S.root.querySelector(".nv-titleed"); if (te) te.focus(); return; }
        S.sel = null; renderLayer(); return openForm(it);
      case "m-open": S.sheet = null; return openDetail("m:" + mineRef(id).id);
      case "m-cancel":
        S.sheet = null; S.sel = null;
        if (it.src === "kanban") return later(id, tw("nv.ok.cancelled"), function () { return postForm("/kanban/task/cancel", { brain: b, id: it.ref }); });
        return later(id, tw("nv.ok.cancelled"), function () { return postForm("/reminders/cancel", { brain: b, id: it.ref }); });
      case "m-del":
        S.sheet = null; S.sel = null;
        if (it.src === "mine") {
          return act(mine({ __url: "/my-tasks/delete", id: it.raw.id }), tw("nv.ok.deleted"), function (res) { return mine({ __url: "/my-tasks/restore", task: res.task }); });
        }
        return later(id, tw("nv.ok.deleted"), function () {
          if (it.src === "kanban") return postForm("/kanban/task/delete", { brain: b, id: it.ref });
          if (it.src === "reminder") return postForm("/reminders/delete", { brain: b, id: it.ref });
          if (it.src === "loop") return postForm("/loops/delete", { brain: b, slug: it.ref });
          return postJSON("/watch/action", { id: it.ref, action: "delete", brain: b });
        });
      case "m-move": case "m-copy": S.sheet = { kind: a.slice(2), id: id }; return renderLayer();
      case "move-to": case "copy-to": {
        var to = el.dataset.v; S.sheet = null; S.sel = null;
        if (it.src === "mine") return act(mine({ __url: "/my-tasks/move", id: it.raw.id, from_brain: b, to_brain: to, copy: a === "copy-to" }), a === "copy-to" ? tw("nv.ok.copied") : tw("nv.ok.moved"));
        if (it.src === "reminder") return act(postForm("/reminders/move", { id: it.ref, from_brain: b, to_brain: to }), tw("nv.ok.moved"));
        if (it.src === "loop") return act(postForm("/loops/move", { slug: it.ref, from_brain: b, to_brain: to }), tw("nv.ok.moved"));
        return;
      }
      case "tojavis": case "m-tojavis": return giveToJavis(it);
      case "m-tome": return takeFromJavis(it);
      case "grant":
        if (!window.confirm(tw("kanban.confirm_grant"))) return;
        return act(postForm("/kanban/task/grant", { brain: b, id: it.ref }), tw("nv.ok.granted"));
      case "approve": return act(postForm("/kanban/task/move", { brain: b, id: it.ref, status: "done" }), tw("nv.ok.approved"));
      case "resolve": return act(postJSON("/incidents/resolve", { id: id }), tw("nv.ok.resolved"));
      case "gochan": if (window.JavisNav && window.JavisNav.go) window.JavisNav.go("channels"); return;
      case "orch": return act(postForm("/kanban/orchestration", { brain: b, mode: el.dataset.v }), el.dataset.v === "off" ? tw("nv.orch.off_ok") : tw("nv.orch.on_ok"));
      case "overall": {
        var L = S.me.items.filter(function (i) { return i.over && i.id.indexOf("m:") === 0; });
        var prev = L.map(function (i) { return { id: i.raw.id, date: i.raw.date }; });
        await Promise.all(prev.map(function (x) { return mine({ __url: "/my-tasks/update", id: x.id, date: today() }); }));
        return act(Promise.resolve({ ok: true }), tw("nv.ok.moved_all", { n: L.length }), function () { return Promise.all(prev.map(function (x) { return mine({ __url: "/my-tasks/update", id: x.id, date: x.date }); })); });
      }
      case "hrest": { var hk3 = habitCalc(it.raw, today()); toast(tw("nv.h.rest_toast") + (hk3 && hk3.next ? " " + tw("nv.h.next_session", { d: dayWord(hk3.next, today()) }) : "")); return; }
      case "hday": {
        var td = el.dataset.v, tt = it.raw, isOn = !!(tt.done_dates || {})[td];
        S.hmsg = 0;
        return act(mine({ __url: isOn ? "/my-tasks/uncheck" : "/my-tasks/check", id: tt.id, date: td }), isOn ? tw("nv.ok.undone") : tw("nv.h.filled", { d: dayWord(td, today()) }));
      }
      case "hmon": S.stkOff = Math.min(0, (S.stkOff || 0) + Number(el.dataset.v)); return renderLayer(), renderPhone();
      case "hmsg": S.hmsg = (S.hmsg || 0) + 1; return render();
      case "hmsgx": S.hmsgHide = true; lsSet("hmsgx", today()); toast(tw("nv.h.hidden_today")); return render();
      case "htog": {
        var th = it.raw, hb = th.habit;
        var next = habitOn(th) ? Object.assign({}, hb, { off: true }) : hb ? Object.assign({}, hb, { off: false }) : { start: today(), remind: "auto" };
        if (next.off === false) delete next.off;
        return act(mine({ __url: "/my-tasks/update", id: th.id, habit: next }), habitOn(th) ? tw("nv.h.to_rep") : hb ? tw("nv.h.back_habit") : tw("nv.h.to_habit"),
          function () { return mine({ __url: "/my-tasks/update", id: th.id, habit: hb || null }); });
      }
      case "pnew": S.sheet = { kind: "project", id: "", name: "", color: COLORS[5] }; renderLayer(); setTimeout(function () { var i = S.root.querySelector("#nvPName"); if (i) i.focus(); }, 0); return;
      case "pmenu": S.sheet = { kind: "pmenu", id: id }; return renderLayer();
      case "pedit": { var p = proj(id); S.sheet = { kind: "project", id: id, name: p.name, color: p.color }; return renderLayer(); }
      case "pcol": S.sheet.name = S.root.querySelector("#nvPName").value; S.sheet.color = el.dataset.v; return renderLayer();
      case "pdel": {
        S.sheet = null;
        if (S.view === "proj:" + id) S.view = "all";
        return later("p:" + id, tw("nv.p.deleted"), function () { return mine({ __url: "/my-tasks/project/delete", id: id }); });
      }
      case "pin": {
        if (el.dataset.v === "proj") { var pp = proj(id); return act(mine({ __url: "/my-tasks/project", id: id, pinned: !pp.pinned }), ""); }
        var P = pins("who"), i = P.indexOf(id); if (i >= 0) P.splice(i, 1); else P.push(id); lsSet("pins.who", JSON.stringify(P)); render(); return;
      }
      case "pick-date": {
        var tg = pickTarget(id), base = tg.date || today();
        S.sheet = { kind: "date", id: id, d: { date: tg.date, time: tg.time, vm: base.slice(0, 7) } }; return renderLayer();
      }
      case "pick-rep": {
        var tg2 = pickTarget(id), wd = new Date((tg2.date || today()) + "T12:00:00").getDay();
        S.sheet = { kind: "rep", id: id, javis: tg2.javis, r: tg2.rule ? JSON.parse(JSON.stringify(tg2.rule)) : { unit: "day", n: 1, days: [wd] } }; return renderLayer();
      }
      case "dp-set": S.sheet.d.date = el.dataset.v || null; if (!S.sheet.d.date) S.sheet.d.time = ""; if (S.sheet.d.date) S.sheet.d.vm = S.sheet.d.date.slice(0, 7); return renderLayer();
      case "dp-mon": { var x = new Date(S.sheet.d.vm + "-15T12:00:00"); x.setMonth(x.getMonth() + Number(el.dataset.v)); S.sheet.d.vm = isoOf(x).slice(0, 7); return renderLayer(); }
      case "dp-clear": return applyPick(S.sheet.id, { date: null, time: "" });
      case "dp-ok": return applyPick(S.sheet.id, { date: S.sheet.d.date, time: S.sheet.d.time });
      case "rp-day": { var dd = Number(el.dataset.v), rr = S.sheet.r; rr.days = rr.days || []; var k = rr.days.indexOf(dd); if (k >= 0) { if (rr.days.length > 1) rr.days.splice(k, 1); } else rr.days.push(dd); return renderLayer(); }
      case "rp-clear": return applyPick(S.sheet.id, { rule: null });
      case "rp-ok": { var rr2 = S.sheet.r; if (rr2.unit !== "week") delete rr2.days; return applyPick(S.sheet.id, { rule: rr2 }); }
    }
  }
  function toggleRep(r, on) {
    var b = brain();
    if (r.src === "reminder") return postForm("/reminders/pause", { brain: b, id: r.ref, paused: on ? "0" : "1" });
    if (r.src === "loop") return postForm("/loops/toggle", { brain: b, slug: r.ref });
    return postJSON("/watch/action", { id: r.ref, action: on ? "resume" : "pause", brain: b });
  }
  // "Give to Javis": a dated task becomes a reminder that does the job, an undated one a Kanban job; mine goes away.
  async function giveToJavis(it) {
    var t = it.raw; S.sheet = null; S.sel = null;
    var r = t.date || t.repeat ? await createReminder(t.title + (t.notes ? "\n" + t.notes : ""), "do", t.date, t.time, t.repeat)
      : await postForm("/kanban/task", { brain: brain(), title: t.title.slice(0, 120), intent: t.title + (t.notes ? "\n" + t.notes : ""), priority: 2 });
    if (!r || r.ok === false) { if (r) toast(r.error || tw("nv.err.generic")); return; }
    var del = await mine({ __url: "/my-tasks/delete", id: t.id, handoff: true });
    await load(); render();
    toast(tw("nv.ok.tojavis"), function () {
      var cancel = t.date || t.repeat ? postForm("/reminders/delete", { brain: brain(), id: r.id }) : postForm("/kanban/task/delete", { brain: brain(), id: r.id });
      Promise.all([cancel, mine({ __url: "/my-tasks/restore", task: del.task })]).then(load).then(render);
    });
  }
  // "Do it myself": the Javis job becomes my task (same title and date), the Javis job is cancelled after the undo window.
  async function takeFromJavis(it) {
    S.sheet = null; S.sel = null;
    var raw = it.raw || {}, ts = it.src === "reminder" ? stamp(raw.due_at) : { date: it.date, time: it.time };
    var r = await mine({ __url: "/my-tasks", title: it.desc && it.desc.length < 300 ? it.desc : it.title, date: ts.date || null, time: ts.time || "", from_javis: true });
    if (!r || r.ok === false) { toast((r && r.error) || tw("nv.err.generic")); return; }
    var b = brain();
    later(it.id, tw("nv.ok.tome"), function () {
      return it.src === "kanban" ? postForm("/kanban/task/cancel", { brain: b, id: it.ref }) : postForm("/reminders/cancel", { brain: b, id: it.ref });
    });
    var t = document.querySelector(".nv-toast .nv-undo");
    if (t) { var prevUndo = t.onclick; t.onclick = function () { prevUndo(); mine({ __url: "/my-tasks/delete", id: r.task.id }).then(load).then(render); }; }
  }

  // ---------- render + events ----------
  function renderLayer() {
    var L = S.root.querySelector(".nv-layer");
    var it = S.sel && window.innerWidth > 760 ? find(S.sel) : null;
    L.innerHTML = (S.layer === "form" ? formHtml() : it ? drawerHtml(it) : "") + sheetHtml();
    var te = L.querySelector(".nv-titleed"); if (te) fitTA(te);
  }
  function fitTA(el) { el.style.height = "auto"; el.style.height = el.scrollHeight + "px"; }
  function render() {
    if (!S || !S.ai) return;
    renderDesk(); renderPhone(); renderLayer();
  }
  function setView(v) { S.view = v; S.sel = null; lsSet("view." + S.tab, v); render(); }
  function setTab(tab) {
    S.tab = tab; lsSet("tab", tab);
    S.view = lsGet("view." + tab, "today");
    if (S.view !== "stats" && !lists().some(function (L) { return L[0] === S.view; }) && S.view.indexOf(tab === "me" ? "proj:" : "who:") !== 0) S.view = "today";
    S.sel = null; S.phone = { screen: "home" }; render();
  }
  function openDetail(oid) {
    if (window.innerWidth <= 760) { S.phone = { screen: "detail", id: oid, from: S.phone.screen === "list" ? S.phone.list : "" }; render(); window.scrollTo(0, 0); }
    else { S.sel = oid; render(); }
  }

  function onClick(e) {
    var t = e.target;
    var a = t.closest("[data-act]");
    if (a && S.root.contains(a)) {
      var act_ = a.dataset.act, id = a.dataset.id;
      if (act_ === "close") { S.sel = null; S.layer = null; S.form = null; renderLayer(); return; }
      if (act_ === "sheetclose") { S.sheet = null; renderLayer(); return; }
      if (act_ === "menu") { S.sheet = { kind: "menu", id: id }; renderLayer(); return; }
      if (act_ === "fold") { S.showDone = !S.showDone; render(); return; }
      if (act_ === "tab") { setTab(a.dataset.v); return; }
      if (act_ === "morewho" || act_ === "moreproj") { var k = act_ === "morewho" ? "moreWho" : "moreProj"; S[k] = !S[k]; lsSet(k, S[k] ? "1" : ""); render(); return; }
      if (act_ === "fset") { keepFormText(); S.form[a.dataset.k] = a.dataset.v;
        if (a.dataset.k === "kind" && a.dataset.v === "appt") { S.form.who = "me"; if (!S.form.date) S.form.date = today(); if (!S.form.time) S.form.time = fromMin(Math.ceil((toMin(hmOf(new Date())) + 30) / 30) * 30); } if (a.dataset.k === "who" && a.dataset.v === "me" && S.form.rule && (S.form.rule.unit === "min" || S.form.rule.unit === "hour")) S.form.rule = null; renderLayer(); return; }
      if (act_ === "new") { openForm(null); return; }
      if (act_ === "st-range") { if (window.JavisTaskStats) window.JavisTaskStats.openRange(a, statsCtx()); return; }
      if (act_ === "st-mins") { if (window.JavisTaskStats) window.JavisTaskStats.toggleMinutes(statsCtx()); return; }
      if (act_ === "st-give") { var gi = find(id); if (gi) { giveToJavis(gi).then(function () { if (window.JavisTaskStats) window.JavisTaskStats.refresh(); render(); }); } return; }
      if (act_ === "pick-date" || act_ === "pick-rep") { if (id === "new") keepFormText(); }
      doAct(act_, id, a);
      return;
    }
    var v = t.closest("[data-view]"); if (v) { setView(v.dataset.view); return; }
    var pl = t.closest("[data-pl]"); if (pl) { S.phone = { screen: "list", list: pl.dataset.pl }; S.view = pl.dataset.pl; render(); window.scrollTo(0, 0); return; }
    var pb = t.closest("[data-pback]"); if (pb) { S.phone = S.phone.screen === "detail" && S.phone.from ? { screen: "list", list: S.phone.from } : { screen: "home" }; render(); return; }
    var o = t.closest("[data-open]");
    if (o) { var oid = o.dataset.open; if (find(oid)) openDetail(oid); }
  }
  async function onChange(e) {
    var el = e.target;
    if (!S.root.contains(el)) return;
    if (el.dataset.pproj && el.dataset.pproj !== "new") {
      var it = find(el.dataset.pproj) || find("m:" + el.dataset.pproj); var id = it ? it.raw.id : el.dataset.pproj.replace(/^m:/, "");
      return act(mine({ __url: "/my-tasks/update", id: id, project: el.value }), tw("nv.saved"));
    }
    if (el.dataset.adur) { var at1 = S.my.tasks.find(function (x) { return x.id === el.dataset.adur; }); return act(mine({ __url: "/my-tasks/update", id: at1.id, end: fromMin(toMin(at1.time) + Number(el.value)) }), tw("nv.saved")); }
    if (el.dataset.arem) return act(mine({ __url: "/my-tasks/update", id: el.dataset.arem, remind: el.value }), tw("nv.saved"));
    if (el.dataset.aloc) return act(mine({ __url: "/my-tasks/update", id: el.dataset.aloc, location: el.value.trim() }), tw("nv.saved"));
    if (el.dataset.hrem || el.dataset.hat) {
      var ht = S.my.tasks.find(function (x) { return x.id === (el.dataset.hrem || el.dataset.hat); }); if (!ht) return;
      var nh = Object.assign({}, ht.habit, el.dataset.hrem ? { remind: el.value } : { at: el.value });
      return act(mine({ __url: "/my-tasks/update", id: ht.id, habit: nh }), nh.remind === "off" ? tw("nv.h.r_off_ok") : nh.remind === "auto" ? tw("nv.h.r_auto_ok") : tw("nv.h.r_time_ok", { t: nh.at || "21:00" }));
    }
    if (el.dataset.dp === "time") { S.sheet.d.time = el.value; return; }
    if (el.dataset.dp === "other") { if (el.value) { S.sheet.d.time = el.value; renderLayer(); } return; }
    if (el.dataset.rp === "unit") { S.sheet.r.unit = el.value; if (el.value === "week" && !(S.sheet.r.days || []).length) S.sheet.r.days = [new Date().getDay()]; renderLayer(); return; }
    if (el.dataset.rp === "n") { S.sheet.r.n = Math.max(1, Math.min(365, Number(el.value) || 1)); return; }
    if (el.dataset.msub) {
      var t = S.my.tasks.find(function (x) { return x.id === el.dataset.msub; }); if (!t) return;
      var subs = (t.subs || []).map(function (x, i) { return i === Number(el.dataset.v) ? { t: x.t, done: el.checked } : x; });
      return act(mine({ __url: "/my-tasks/update", id: t.id, subs: subs }), "");
    }
    if (el.dataset.mtitle) { var v = el.value.trim(); if (v) return act(mine({ __url: "/my-tasks/update", id: el.dataset.mtitle, title: v }), tw("nv.saved")); return; }
    if (el.dataset.mnotes) return act(mine({ __url: "/my-tasks/update", id: el.dataset.mnotes, notes: el.value }), tw("nv.saved"));
  }
  async function onSubmit(e) {
    var f = e.target;
    if (!S.root.contains(f)) return;
    e.preventDefault();
    var b = brain();
    if (f.dataset.form) return submitForm();
    if (f.dataset.stmins && window.JavisTaskStats) return window.JavisTaskStats.saveMinutes(f, statsCtx());
    if (f.dataset.pform) {
      var name = S.root.querySelector("#nvPName").value.trim(); if (!name) return;
      var sh = S.sheet; S.sheet = null;
      return act(mine({ __url: "/my-tasks/project", id: sh.id || undefined, name: name, color: sh.color }), sh.id ? tw("nv.saved") : tw("nv.p.created"));
    }
    if (f.dataset.msubadd) {
      var inp = f.querySelector("input"), txt = inp.value.trim(); if (!txt) return;
      var t = S.my.tasks.find(function (x) { return x.id === f.dataset.msubadd; }); if (!t) return;
      await act(mine({ __url: "/my-tasks/update", id: t.id, subs: (t.subs || []).concat([{ t: txt, done: false }]) }), "");
      var again = S.root.querySelector('[data-msubadd="' + t.id + '"] input'); if (again) again.focus();
      return;
    }
    if (f.dataset.answer) { var it = find(f.dataset.answer); return act(postForm("/kanban/task/answer", { brain: b, id: it.ref, answer: f.querySelector("textarea").value }), tw("nv.ok.sent")); }
    if (f.dataset.follow) { var it2 = find(f.dataset.follow); return act(postForm("/kanban/task/followup", { brain: b, id: it2.ref, text: f.querySelector("textarea").value }), tw("nv.ok.sent")); }
  }
  function onKey(e) {
    if (!S) return;
    if (e.key === "Escape" && (S.sel || S.layer || S.sheet)) { S.sel = null; S.layer = null; S.sheet = null; renderLayer(); return; }
    var c = e.target.closest && e.target.closest(".nv-root [role=checkbox]");
    if (c && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); c.click(); }
  }
  function onInput(e) { if (e.target.classList && e.target.classList.contains("nv-titleed")) fitTA(e.target); }

  async function mount(el) {
    if (S) unmount();
    var tab = "ai";   // 0.428.0: the page always opens on Javis's tasks; each tab still remembers its list
    S = { root: el, tab: tab, view: lsGet("view." + tab, "today"), q: "", sel: null, layer: null, sheet: null, form: null, hidden: {}, showDone: false,
      hmsgHide: lsGet("hmsgx", "") === isoOf(new Date()), moreWho: lsGet("moreWho", "") === "1", moreProj: lsGet("moreProj", "") === "1", phone: { screen: "home" }, agents: null, ai: null, me: null, my: null };
    var legacy = lsGet("view", "");   // the old Scheduled link sets "rep" for the Javis tab
    if (legacy) { try { localStorage.removeItem(LS + "view"); } catch (e2) { /* ignore */ } if (legacy === "rep") { S.tab = "ai"; S.view = "rep"; } }
    el.classList.add("nv-root");
    el.innerHTML = '<div class="nv-desk"><nav class="nv-side" aria-label="' + esc(tw("nv.title")) + '"></nav><section class="nv-main"><div class="nv-top"></div>'
      + '<div class="nv-search">' + ic("search") + '<input type="search" id="nvQ" autocomplete="off" placeholder="' + esc(tw("nv.search_ph")) + '" aria-label="' + esc(tw("nv.search_ph")) + '"></div>'
      + '<div class="nv-askbox"></div><div class="nv-view"><div class="nv-empty">' + esc(tw("common.loading")) + "</div></div></section></div>"
      + '<div class="nv-phone"><div class="nv-ptabs"></div><div class="nv-pbody"></div></div>'
      + '<button type="button" class="nv-fab" data-act="new" aria-label="' + esc(tw("nv.f.add_any")) + '" title="' + esc(tw("nv.f.add_any")) + '">' + ic("plus") + "</button><div class=\"nv-layer\"></div>";
    el.addEventListener("click", onClick);
    el.addEventListener("change", onChange);
    el.addEventListener("submit", onSubmit);
    el.addEventListener("input", onInput);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", fitSide);
    document.addEventListener("scroll", fitSide, { passive: true, capture: true });   // the page scrolls inside #cviewBody
    el.querySelector("#nvQ").addEventListener("input", function (e) { S.q = e.target.value; S.root.querySelector(".nv-view").innerHTML = viewHtml(S.view); });
    await load();
    if (!S || S.root !== el) return;
    if (S.view !== "stats" && !lists().some(function (L) { return L[0] === S.view; }) && S.view.indexOf(S.tab === "me" ? "proj:" : "who:") !== 0) S.view = "today";
    render(); schedulePoll();
  }
  function unmount() {
    if (!S) return;
    clearTimeout(S.poll);
    document.removeEventListener("keydown", onKey);
    window.removeEventListener("resize", fitSide);
    document.removeEventListener("scroll", fitSide, { capture: true });
    S = null;
  }

  // Javis opens a Kanban job on screen (ui-actions.js, action open_task): Javis tab, details of that job.
  async function show(ref) {
    if (!S || !S.ai) return false;
    var id = "k:" + String(ref || "").replace(/^k:/, "");
    if (S.tab !== "ai") setTab("ai");
    if (!find(id)) { await load(); if (!S) return false; }
    if (!find(id)) return false;
    openDetail(id);
    return true;
  }

  window.JavisTasks = { mount: mount, unmount: unmount, show: show, ready: function () { return !!(S && S.ai); }, _model: model_ };
})();
