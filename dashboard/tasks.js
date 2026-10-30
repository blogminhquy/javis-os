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
    var kb = src.kanban || {}, ops = kb.operations || {};
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
          who: agentOf(c), st: st, date: ts.date || (FIN[st] ? null : today), time: ts.time, rep: "",
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
        var mode = r.mode === "notify" ? "remind" : "do";
        if (rep) {
          recurring.push({ id: "r:" + r.id, src: "reminder", ref: r.id, title: title, who: CORE, sc: rep, next: r.due_at || 0,
            on: !paused, running: !!r.running, mode: mode, raw: r });
        }
        if (paused) return;
        items.push({ id: "r:" + r.id, src: "reminder", ref: r.id, title: title, desc: r.text || "", who: CORE,
          st: r.running ? "run" : "sched", date: ts.date, time: ts.time, rep: rep, mode: mode,
          result: r.result || "", reason: r.error || "", at: r.due_at || 0, raw: r });
      });
      (b.loops || []).forEach(function (lp) {
        var paused = !!lp.auto_paused_reason;
        recurring.push({ id: "l:" + lp.slug, src: "loop", ref: lp.slug, title: lp.name || lp.slug, who: CORE,
          sc: everyMin(lp.interval_min), next: lp.next_run || 0, on: !!lp.enabled && !paused,
          running: !!lp.running, mode: "do", raw: lp });
        if (lp.enabled && lp.next_run && !paused) {
          var t2 = stamp(lp.next_run);
          items.push({ id: "l:" + lp.slug, src: "loop", ref: lp.slug, title: lp.name || lp.slug, desc: "", who: CORE,
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
      var title = r.label || r.text || "";
      if (r.status === "done") {
        items.push({ id: "rh:" + r.id, src: "reminder", ref: r.id, title: title, desc: r.text || "", who: CORE, st: "done",
          date: ts.date, time: ts.time, rep: "", mode: r.mode === "notify" ? "remind" : "do", result: r.result || "", reason: "",
          at: r.fired_at || 0, raw: r });
      }
      log.push({ at: r.fired_at || 0, title: title, text: r.result || r.error || "", who: CORE, ok: r.status === "done", ref: "rh:" + r.id });
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
      if (m) log.push({ at: 0, when: m[1], title: m[2], text: m[3].trim(), who: CORE, ok: !/l\u1ed7i|error/i.test(m[2]), ref: "" });
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

  var model_ = { model: model, inList: inList, byTime: byTime, byTimeline: byTimeline, cronFor: cronFor, kanbanState: kanbanState, addDays: addDays };
  if (typeof module !== "undefined" && module.exports) { module.exports = model_; return; }

  // ---------- page ----------
  var LISTS_AI = [["all", "list", "nv.l.all", "c-all"], ["today", "sun", "nv.l.today", "c-today"], ["week", "calendar", "nv.l.week", "c-week"],
    ["over", "clock-alert", "nv.l.over", "c-over"], ["rep", "repeat", "nv.l.rep", "c-rep"], ["err", "triangle-alert", "nv.l.err", "c-err"],
    ["done", "circle-check", "nv.l.done", "c-done"], ["log", "scroll-text", "nv.l.log", "c-log"]];
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

  async function load() {
    var b = brain(), enc = encodeURIComponent(b);
    var res = await Promise.all([
      getJSON("/kanban?brain=" + enc + "&history=40"), getJSON("/viec/all"), getJSON("/reminders?brain=" + enc),
      getJSON("/watch?brain=" + enc), getJSON("/incidents?limit=50"), getJSON("/loops/log?brain=" + enc + "&limit=60"),
      S.agents ? Promise.resolve(null) : getJSON("/agents?brain=" + enc + "&prompt=0&system=1")
    ]);
    if (res[6]) S.agents = (res[6].agents || res[6] || []).filter(function (a) { return a && a.slug; });
    S.brains = ((res[1] && res[1].brains) || []).map(function (x) { return { name: x.name, path: x.path, def: x.is_default }; });
    S.m = model({ kanban: res[0] || {}, viec: res[1] || {}, rems: res[2] || {}, watch: res[3] || {}, incidents: res[4] || {}, loopLog: res[5] || {}, brain: b });
    applyHidden();
    S.loaded = true;
  }
  // Items removed with "undo" still pending stay hidden until the server confirms.
  function applyHidden() {
    if (!S.m) return;
    var h = S.hidden;
    S.m.items = S.m.items.filter(function (i) { return !h[i.id]; });
    S.m.recurring = S.m.recurring.filter(function (r) { return !h[r.id]; });
  }

  function schedulePoll() {
    clearTimeout(S.poll);
    var busy = S.m && (S.m.items.some(function (i) { return i.st === "run"; }) || S.m.recurring.some(function (r) { return r.running; }));
    S.poll = setTimeout(async function tick() {
      if (!S || !document.body.contains(S.root)) return;
      if (document.hidden || S.sheet || S.layer) { schedulePoll(); return; }
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
  // Destructive actions wait 6 s so "Undo" can take them back before the server is told.
  function later(id, msg, commit) {
    S.hidden[id] = 1; applyHidden(); render();
    var done = false;
    var timer = setTimeout(async function () { done = true; var r = await commit(); delete S.hidden[id]; if (r && r.ok === false) toast(r.error || tw("nv.err.generic")); await load(); render(); }, 6000);
    toast(msg, function () { if (done) return; clearTimeout(timer); delete S.hidden[id]; load().then(render); });
  }
  async function act(promise, okMsg) {
    var r = await promise;
    if (r && r.ok === false) { toast(r.error || tw("nv.err.generic")); return r; }
    if (okMsg) toast(okMsg);
    await load(); render(); schedulePoll();
    return r;
  }

  // ---------- pieces ----------
  function agentName(slug) {
    if (slug === CORE) return "Javis Core";
    var a = (S.agents || []).find(function (x) { return x.slug === slug; });
    return a ? (a.name || slug) : slug;
  }
  function avatar(slug, size) {
    var a = (S.agents || []).find(function (x) { return x.slug === slug; }) || { slug: slug };
    if (window.JavisAvatar && window.JavisAvatar.html) {
      try { return window.JavisAvatar.html(a, size || 18, "idle", { still: true }); } catch (e) { /* fall through */ }
    }
    return '<span class="nv-av" style="width:' + (size || 18) + "px;height:" + (size || 18) + 'px"></span>';
  }
  function dayLabel(iso) {
    var t = S.m.today;
    if (iso === t) return tw("nv.d.today");
    if (iso === addDays(t, 1)) return tw("nv.d.tom");
    if (iso === addDays(t, -1)) return tw("nv.d.yday");
    var d = new Date(iso + "T12:00:00");
    return d.toLocaleDateString(LOC(), { weekday: "long", day: "numeric", month: "numeric" });
  }
  function shortDate(iso) { var d = new Date(iso + "T12:00:00"); return d.getDate() + "/" + (d.getMonth() + 1); }
  function stIcon(it) {
    if (it.st === "run") return ic("loader-circle", "nv-spin c-run");
    if (it.st === "ask") return ic("circle-alert", "c-ask");
    if (it.st === "calm") return ic("hourglass", "c-calm");
    if (it.st === "done") return ic("circle-check", "c-ok");
    if (it.st === "cancel") return ic("circle-x", "c-mute");
    return '<span class="nv-ring"></span>';
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
    parts.push(avatar(it.who, 14) + esc(agentName(it.who)));
    if (it.took) parts.push(esc(tw("nv.took", { n: Math.max(1, Math.round(it.took / 60)) })));
    return '<div class="nv-meta">' + parts.map(function (p) { return "<span>" + p + "</span>"; }).join("") + "</div>";
  }
  function runBtn(it, phone) {
    var cls = phone ? "nv-go" : "nv-rgo";
    if (it.st === "run") return '<button type="button" class="' + cls + ' busy" data-act="stop" data-id="' + esc(it.id) + '" aria-label="' + esc(tw("nv.a.stop")) + '" title="' + esc(tw("nv.a.stop_t")) + '">' + ic("square") + "</button>";
    if (FIN[it.st] || it.st === "ask") return "";
    return '<button type="button" class="' + cls + '" data-act="run" data-id="' + esc(it.id) + '" aria-label="' + esc(tw("nv.a.run")) + '" title="' + esc(tw("nv.a.run_t")) + '">' + ic("play") + "</button>";
  }
  function row(it) {
    var time = it.over ? '<span class="c-over">' + esc(shortDate(it.date)) + "</span>" + (it.time ? "<small>" + esc(it.time) + "</small>" : "") : esc(it.time || "");
    return '<div class="nv-rw"><button type="button" class="nv-row' + (FIN[it.st] ? " done" : "") + (S.sel === it.id ? " sel" : "") + '" data-open="' + esc(it.id) + '">'
      + '<span class="nv-tm">' + time + '</span><span class="nv-st">' + stIcon(it) + "</span>"
      + '<span class="nv-body"><span class="nv-ti">' + esc(it.title) + "</span>" + meta(it)
      + (it.st === "ask" && it.reason ? '<span class="nv-note c-ask">' + esc(it.reason) + "</span>" : "")
      + (it.st === "calm" && it.reason ? '<span class="nv-note">' + esc(it.reason) + "</span>" : "") + "</span>"
      + '<span class="nv-chipcol">' + chip(it) + "</span></button>"
      + runBtn(it) + '<button type="button" class="nv-dots" data-act="menu" data-id="' + esc(it.id) + '" aria-label="' + esc(tw("nv.a.more")) + '">' + ic("ellipsis") + "</button></div>";
  }
  function repRow(r, phone) {
    var lead = r.running
      ? '<button type="button" class="' + (phone ? "nv-go" : "nv-rgo") + ' busy" data-act="rstop" data-id="' + esc(r.id) + '" aria-label="' + esc(tw("nv.a.stop")) + '" title="' + esc(tw("nv.a.stop_t")) + '">' + ic("square") + "</button>"
      : '<button type="button" class="' + (phone ? "nv-go" : "nv-rgo") + '" data-act="rrun" data-id="' + esc(r.id) + '" aria-label="' + esc(tw("nv.a.run")) + '" title="' + esc(r.on ? tw("nv.a.run_t") : tw("nv.a.off")) + '"' + (r.on ? "" : " disabled") + ">" + ic("play") + "</button>";
    var nx = !r.on ? tw("nv.rep.off") : r.running ? tw("nv.st.run") : r.next ? tw("nv.rep.next", { t: whenText(r.next) }) : "";
    return '<div class="nv-rrow' + (r.on ? "" : " off") + '">' + lead + '<button type="button" class="nv-grow" data-open="' + esc(r.id) + '"><span class="nv-ti">' + esc(r.title) + '</span><span class="nv-sc">' + esc(r.sc) + '</span><span class="nv-nx">' + esc(nx) + "</span></button>"
      + '<button type="button" class="nv-sw" role="switch" aria-checked="' + r.on + '" aria-label="' + esc(r.on ? tw("nv.a.pause") : tw("nv.a.resume")) + '" data-act="rtog" data-id="' + esc(r.id) + '"><span></span></button>'
      + '<button type="button" class="nv-dots" data-act="menu" data-id="' + esc(r.id) + '" aria-label="' + esc(tw("nv.a.more")) + '">' + ic("ellipsis") + "</button></div>";
  }
  function whenText(sec) {
    var d = new Date(sec * 1000), iso = isoOf(d);
    return dayLabel(iso) + ", " + hmOf(d);
  }
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
  function items(list) { return S.m.items.filter(function (i) { return inList(i, list, S.m.today) && matchQ(i); }); }
  function overBlock() {
    var L = items("over");
    if (!L.length) return "";
    return '<div class="nv-day over-h">' + esc(tw("nv.l.over")) + " <span>" + L.length + "</span></div>" + L.sort(byTime).map(row).join("");
  }
  function viewTitle(v) {
    if (v.indexOf("who:") === 0) return agentName(v.slice(4));
    var L = LISTS_AI.find(function (x) { return x[0] === v; });
    return L ? tw(L[2]) : "";
  }
  function viewHtml(v) {
    var h = '<div class="nv-vh"><h2>' + esc(viewTitle(v)) + "</h2></div>";
    if (v === "rep") {
      var R = byTimeline(S.m.recurring.filter(function (r) { return !q() || r.title.toLowerCase().indexOf(q()) >= 0; }));
      return h + (R.length ? R.map(function (r) { return repRow(r); }).join("") : '<div class="nv-empty">' + esc(tw("nv.empty.rep")) + "</div>");
    }
    if (v === "err") return h + failsHtml();
    if (v === "log") return h + logHtml();
    if (v === "today") {
      var T = items("today"), open = T.filter(function (i) { return !FIN[i.st]; }), done = T.filter(function (i) { return FIN[i.st]; });
      h += overBlock();
      h += open.length ? open.sort(byTime).map(row).join("") : '<div class="nv-empty">' + esc(tw("nv.empty.today")) + "</div>";
      if (done.length) h += '<button type="button" class="nv-fold" data-act="fold" aria-expanded="' + !!S.showDone + '">' + ic("chevron-right") + esc(tw("nv.done_n", { n: done.length })) + "</button>" + (S.showDone ? done.sort(byTime).map(row).join("") : "");
      return h;
    }
    if (v === "done") {
      var D = items("done");
      if (!D.length) return h + '<div class="nv-empty">' + esc(tw("nv.empty.done")) + "</div>";
      return h + groupByDay(D, true).map(function (g) { return dayHead(g[0]) + g[1].map(row).join(""); }).join("");
    }
    var L = items(v);
    if (v === "all") { h += overBlock(); L = L.filter(function (i) { return !i.over; }); }
    if (!L.length && !(v === "all" && items("over").length)) return h + '<div class="nv-empty">' + esc(tw(v === "over" ? "nv.empty.over" : "nv.empty.list")) + "</div>";
    return h + groupByDay(L).map(function (g) { return dayHead(g[0]) + g[1].map(row).join(""); }).join("");
  }
  function failsHtml() {
    var open = S.m.fails.filter(function (f) { return f.open; }), past = S.m.fails.filter(function (f) { return !f.open && f.at > S.m.now - 7 * 86400; });
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
    var L = S.m.log.slice(0, 80).filter(function (e) { return !q() || (e.title + " " + e.text).toLowerCase().indexOf(q()) >= 0; });
    if (!L.length) return '<div class="nv-empty">' + esc(tw("nv.empty.log")) + "</div>";
    return L.map(function (e) {
      var when = e.at ? (function () { var d = new Date(e.at * 1000); return dayLabel(isoOf(d)) + " " + hmOf(d); })() : (e.when || "");
      return '<details class="nv-log"><summary>' + (e.ok ? ic("circle-check", "c-ok") : ic("circle-alert", "c-ask")) + '<span class="nv-ti">' + esc(e.title) + '</span><span class="nv-when">' + esc(when) + "</span></summary>"
        + '<div class="nv-logtx">' + esc(e.text || tw("nv.log.empty")) + "</div></details>";
    }).join("");
  }
  function askBar() {
    var A = S.m.ask, h = "";
    if (A.length) {
      var a = A[0];
      h += '<div class="nv-ask" role="status">' + ic("circle-alert", "c-ask") + '<button type="button" class="nv-ask-t" data-open="' + esc(a.id) + '"><b>' + esc(a.title) + ":</b> " + esc(a.reason || tw("nv.st.ask")) + "</button>"
        + (A.length > 1 ? '<span class="nv-ask-n">+' + (A.length - 1) + "</span>" : "") + "</div>";
    }
    if (S.m.orch === "off" && S.m.waiting) {
      h += '<div class="nv-ask" role="status">' + ic("pause", "c-ask") + '<span class="nv-ask-t">' + esc(tw("nv.orch.waiting", { n: S.m.waiting })) + '</span><button type="button" class="nv-btn sm pri" data-act="orch" data-v="auto">' + esc(tw("nv.orch.on")) + "</button></div>";
    }
    return h;
  }

  // ---------- desktop layout ----------
  function counts() {
    var c = {};
    LISTS_AI.forEach(function (L) {
      var v = L[0];
      c[v] = v === "rep" ? S.m.recurring.filter(function (r) { return r.on; }).length : v === "err" ? S.m.fails.filter(function (f) { return f.open; }).length
        : v === "log" ? "" : v === "done" ? items("done").length : items(v).filter(function (i) { return !FIN[i.st]; }).length;
    });
    return c;
  }
  function pins() { try { return JSON.parse(lsGet("pins", "[]")) || []; } catch (e) { return []; } }
  function agentsList() {
    var P = pins(), busy = {};
    S.m.items.forEach(function (i) { if (!FIN[i.st]) busy[i.who] = (busy[i.who] || 0) + 1; });
    var A = (S.agents || []).slice();
    if (!A.some(function (a) { return a.slug === CORE; })) A.unshift({ slug: CORE, name: "Javis Core" });
    A.sort(function (a, b) { return (P.indexOf(b.slug) >= 0) - (P.indexOf(a.slug) >= 0) || (busy[b.slug] || 0) - (busy[a.slug] || 0); });
    return { list: A, busy: busy, pins: P };
  }
  function sideHtml() {
    var c = counts();
    var h = '<div class="nv-title">' + esc(tw("nv.title")) + "</div>";
    h += LISTS_AI.map(function (L) {
      var n = c[L[0]];
      return '<button type="button" class="nv-li' + (S.view === L[0] ? " on" : "") + '" data-view="' + L[0] + '">' + ic(L[1], L[3]) + '<span class="nv-lbl">' + esc(tw(L[2])) + '</span><span class="nv-n' + (L[0] === "over" && n || L[0] === "err" && n ? " warn" : "") + '">' + (n || "") + "</span></button>";
    }).join("");
    var A = agentsList(), more = S.moreWho, shown = more ? A.list : A.list.slice(0, PAGE);
    h += '<div class="nv-sec">' + esc(tw("nv.agents")) + "</div>";
    h += shown.map(function (a) {
      var pin = A.pins.indexOf(a.slug) >= 0;
      return '<div class="nv-lirow"><button type="button" class="nv-li' + (S.view === "who:" + a.slug ? " on" : "") + '" data-view="who:' + esc(a.slug) + '">' + avatar(a.slug, 18) + '<span class="nv-lbl">' + esc(a.name || a.slug) + '</span><span class="nv-n">' + (A.busy[a.slug] || "") + "</span></button>"
        + '<button type="button" class="nv-pin' + (pin ? " on" : "") + '" data-act="pin" data-id="' + esc(a.slug) + '" aria-pressed="' + pin + '" aria-label="' + esc(pin ? tw("nv.a.unpin") : tw("nv.a.pin")) + '">' + ic("pin") + "</button></div>";
    }).join("");
    if (A.list.length > PAGE) h += '<button type="button" class="nv-more" data-act="morewho">' + ic(more ? "chevron-up" : "chevron-down") + "<span>" + esc(more ? tw("nv.less") : tw("nv.more_n", { n: A.list.length - PAGE })) + "</span></button>";
    h += '<div class="nv-orch"><span>' + ic("bot") + esc(tw("nv.orch.label")) + '</span><button type="button" class="nv-sw" role="switch" aria-checked="' + (S.m.orch !== "off") + '" aria-label="' + esc(tw("nv.orch.label")) + '" data-act="orch" data-v="' + (S.m.orch === "off" ? "auto" : "off") + '"><span></span></button></div>';
    return h;
  }
  function tabsHtml() {
    return '<div class="nv-tabs" role="tablist"><button type="button" role="tab" aria-selected="true" class="on">' + avatar(CORE, 18) + "<span>" + esc(tw("nv.tab.ai")) + '</span><span class="nv-n">' + S.m.items.filter(function (i) { return !FIN[i.st]; }).length + "</span></button></div>";
  }
  function renderDesk() {
    var D = S.root.querySelector(".nv-desk");
    D.querySelector(".nv-side").innerHTML = sideHtml();
    D.querySelector(".nv-top").innerHTML = tabsHtml();
    D.querySelector(".nv-askbox").innerHTML = askBar();
    D.querySelector(".nv-view").innerHTML = viewHtml(S.view);
    fitSide();
  }
  function fitSide() {
    var s = S.root.querySelector(".nv-side");
    if (!s || window.innerWidth <= 760) return;
    var top = s.getBoundingClientRect().top;
    s.style.maxHeight = (window.innerHeight - Math.max(12, top) - 12) + "px";
  }

  // ---------- phone layout ----------
  function phoneHtml() {
    var P = S.phone;
    var bar = function (title) { return '<div class="nv-pbar"><button type="button" class="nv-back" data-pback="1" aria-label="' + esc(tw("nv.back")) + '">' + ic("chevron-left") + '</button><span class="nv-ptitle">' + esc(title) + '</span><span></span></div>'; };
    if (P.screen === "detail") {
      var it = find(P.id);
      return bar(it ? agentName(it.who) : "") + '<div class="nv-ppad">' + (it ? detailHtml(it, true) : "") + "</div>";
    }
    if (P.screen === "list") {
      var body = viewHtml(P.list).replace(/^<div class="nv-vh">[\s\S]*?<\/div>/, "");
      return bar(viewTitle(P.list)) + '<div class="nv-ppad">' + body + "</div>";
    }
    var c = counts();
    var h = '<div class="nv-ppad">' + askBar() + '<div class="nv-pcards">';
    h += LISTS_AI.map(function (L) { return '<button type="button" class="nv-pl" data-pl="' + L[0] + '">' + ic(L[1], L[3]) + '<span class="nv-lbl">' + esc(tw(L[2])) + '</span><span class="nv-n">' + (c[L[0]] || "") + "</span>" + ic("chevron-right", "nv-chev") + "</button>"; }).join("");
    h += "</div>";
    var A = agentsList(), shown = S.moreWho ? A.list : A.list.slice(0, PAGE);
    h += '<div class="nv-sec">' + esc(tw("nv.agents")) + '</div><div class="nv-pcards">' + shown.map(function (a) { return '<button type="button" class="nv-pl" data-pl="who:' + esc(a.slug) + '">' + avatar(a.slug, 20) + '<span class="nv-lbl">' + esc(a.name || a.slug) + '</span><span class="nv-n">' + (A.busy[a.slug] || "") + "</span>" + ic("chevron-right", "nv-chev") + "</button>"; }).join("") + "</div>";
    if (A.list.length > PAGE) h += '<button type="button" class="nv-more" data-act="morewho">' + ic(S.moreWho ? "chevron-up" : "chevron-down") + "<span>" + esc(S.moreWho ? tw("nv.less") : tw("nv.more_n", { n: A.list.length - PAGE })) + "</span></button>";
    h += '<div class="nv-orch">' + "<span>" + ic("bot") + esc(tw("nv.orch.label")) + '</span><button type="button" class="nv-sw" role="switch" aria-checked="' + (S.m.orch !== "off") + '" aria-label="' + esc(tw("nv.orch.label")) + '" data-act="orch" data-v="' + (S.m.orch === "off" ? "auto" : "off") + '"><span></span></button></div>';
    return h + "</div>";
  }
  function renderPhone() {
    var el = S.root.querySelector(".nv-phone");
    el.querySelector(".nv-ptabs").innerHTML = tabsHtml();
    el.querySelector(".nv-pbody").innerHTML = phoneHtml();
  }

  // ---------- detail (drawer on desktop, a screen on phone) ----------
  function find(id) {
    // A repeating job has both a recurring entry and an item for its next run under the same id: the entry wins,
    // so its details and menu offer the schedule (switch, skip next run).
    return S.m.recurring.find(function (r) { return r.id === id; }) || S.m.items.find(function (i) { return i.id === id; }) || null;
  }
  function kv(label, value) { return '<div class="nv-kv"><span>' + esc(label) + "</span><span>" + value + "</span></div>"; }
  function detailHtml(it, phone) {
    var isRep = !!it.sc;
    var r = isRep ? it : S.m.recurring.find(function (x) { return x.id === it.id; });
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
    info += kv(tw("nv.k.kind"), esc(tw({ kanban: "nv.src.kanban", reminder: "nv.src.reminder", loop: "nv.src.loop", watch: "nv.src.watch" }[it.src] || "nv.src.kanban")));
    if (r) info += '<div class="nv-kv"><span>' + esc(tw("nv.k.on")) + '</span><button type="button" class="nv-sw" role="switch" aria-checked="' + r.on + '" aria-label="' + esc(tw("nv.k.on")) + '" data-act="rtog" data-id="' + esc(r.id) + '"><span></span></button></div>';
    h += '<div class="nv-sec2">' + info + "</div>";
    if (it.st === "done" && it.src === "kanban") {
      h += '<form class="nv-sec2 nv-answer" data-follow="' + esc(it.id) + '"><label class="nv-cap" for="nvFu">' + esc(tw("nv.follow")) + '</label><textarea id="nvFu" class="nv-ta" placeholder="' + esc(tw("nv.follow_ph")) + '" required></textarea><div class="nv-acts"><button type="submit" class="nv-btn pri">' + esc(tw("nv.send")) + "</button></div></form>";
    }
    h += '<div class="nv-sec2"><div class="nv-acts">' + menuButtons(it, true) + "</div></div>";
    return h;
  }
  function drawerHtml(it) {
    return '<div class="nv-scrim" data-act="close"></div><aside class="nv-drawer" role="dialog" aria-modal="true" aria-label="' + esc(tw("nv.detail")) + '">'
      + '<div class="nv-dh"><span>' + esc(tw("nv.detail")) + '</span><button type="button" class="nv-x" data-act="close" aria-label="' + esc(tw("nv.close")) + '">' + ic("x") + "</button></div>" + detailHtml(it) + "</aside>";
  }

  // ---------- menu ⋯ ----------
  function menuDefs(it) {
    var isRep = !!it.sc, src = it.src, out = [];
    if (src === "reminder" && (isRep || !FIN[it.st])) out.push(["edit", "pencil", "nv.a.edit"]);
    if (isRep && src === "reminder") out.push(["skip", "skip-forward", "nv.a.skip"]);
    if (isRep) out.push(["rtog", it.on ? "pause" : "play", it.on ? "nv.a.pause" : "nv.a.resume"]);
    if (!isRep && src === "kanban" && !FIN[it.st]) out.push(["cancel", "circle-x", "nv.a.cancel"]);
    if (!isRep && src === "reminder" && !FIN[it.st]) out.push(["cancel", "circle-x", "nv.a.cancel"]);
    if ((src === "reminder" || src === "loop") && !FIN[it.st] && (S.brains || []).length > 1) out.push(["move", "arrow-right-left", "nv.a.move"]);
    out.push(["del", "trash-2", "nv.a.del"]);
    return out;
  }
  function menuButtons(it, inline) {
    return menuDefs(it).map(function (m) { return '<button type="button" class="nv-btn sm' + (m[0] === "del" ? " ghost danger" : "") + '" data-act="m-' + m[0] + '" data-id="' + esc(it.id) + '">' + ic(m[1]) + esc(tw(m[2])) + "</button>"; }).join("");
  }
  function sheetHtml() {
    var sh = S.sheet;
    if (!sh) return "";
    var it = find(sh.id);
    if (!it) return "";
    var head = '<div class="nv-sheet-scrim" data-act="sheetclose"></div><div class="nv-sheet" role="dialog" aria-modal="true" aria-label="' + esc(it.title) + '"><div class="nv-sheet-h"><b>' + esc(it.title) + '</b><button type="button" class="nv-x" data-act="sheetclose" aria-label="' + esc(tw("nv.close")) + '">' + ic("x") + "</button></div>";
    if (sh.kind === "move") {
      var others = (S.brains || []).filter(function (b) { return b.path !== brain() && !(brain() === "brain" && b.def); });
      return head + '<div class="nv-sheet-b">' + others.map(function (b) { return '<button type="button" class="nv-mi" data-act="move-to" data-id="' + esc(it.id) + '" data-v="' + esc(b.path) + '">' + ic("brain") + esc(b.name) + "</button>"; }).join("") + "</div></div>";
    }
    return head + '<div class="nv-sheet-b">' + menuDefs(it).map(function (m) { return '<button type="button" class="nv-mi' + (m[0] === "del" ? " danger" : "") + '" data-act="m-' + m[0] + '" data-id="' + esc(it.id) + '">' + ic(m[1]) + esc(tw(m[2])) + "</button>"; }).join("") + "</div></div>";
  }

  // ---------- add / edit form ----------
  function timeOpts(sel) {
    var o = '<option value="">' + esc(tw("nv.f.no_time")) + "</option>";
    for (var i = 0; i < 48; i++) { var t = pad2(Math.floor(i / 2)) + ":" + (i % 2 ? "30" : "00"); o += '<option' + (t === sel ? " selected" : "") + ">" + t + "</option>"; }
    if (sel && !/:(00|30)$/.test(sel)) o += "<option selected>" + esc(sel) + "</option>";
    return o;
  }
  function formHtml() {
    var f = S.form;
    var reps = [["", "nv.f.rep_none"], ["daily", "nv.rep.daily"], ["weekdays", "nv.f.rep_weekdays"], ["weekly", "nv.f.rep_weekly"], ["monthly", "nv.f.rep_monthly"]];
    return '<div class="nv-scrim" data-act="close"></div><div class="nv-modal" role="dialog" aria-modal="true" aria-labelledby="nvFormT"><form data-form="1">'
      + '<div class="nv-mh"><h3 id="nvFormT">' + esc(f.edit ? tw("nv.f.edit") : tw("nv.f.new")) + '</h3><button type="button" class="nv-x" data-act="close" aria-label="' + esc(tw("nv.close")) + '">' + ic("x") + "</button></div>"
      + '<label class="nv-fld"><span>' + esc(tw("nv.f.what")) + '</span><textarea class="nv-ta" id="nvW" required placeholder="' + esc(tw("nv.f.what_ph")) + '">' + esc(f.text || "") + "</textarea></label>"
      + '<div class="nv-fld"><span>' + esc(tw("nv.k.how")) + '</span><div class="nv-seg" role="group">' + [["do", "nv.mode.do"], ["remind", "nv.mode.remind"]].map(function (m) { return '<button type="button" data-act="fmode" data-v="' + m[0] + '" aria-pressed="' + (f.mode === m[0]) + '">' + esc(tw(m[1])) + "</button>"; }).join("") + "</div></div>"
      + '<div class="nv-row2"><label class="nv-fld"><span>' + esc(tw("nv.f.date")) + '</span><input type="date" class="nv-inp" id="nvD" value="' + esc(f.date || "") + '"></label>'
      + '<label class="nv-fld"><span>' + esc(tw("nv.f.time")) + '</span><select class="nv-inp" id="nvT">' + timeOpts(f.time || "") + "</select></label></div>"
      + '<label class="nv-fld"><span>' + esc(tw("nv.k.repeat")) + '</span><select class="nv-inp" id="nvR"' + (f.edit && f.cronLocked ? " disabled" : "") + ">" + reps.map(function (r) { return '<option value="' + r[0] + '"' + (f.rep === r[0] ? " selected" : "") + ">" + esc(tw(r[1])) + "</option>"; }).join("") + "</select></label>"
      + (f.err ? '<div class="nv-ferr" role="alert">' + esc(f.err) + "</div>" : "")
      + '<div class="nv-acts end"><button type="button" class="nv-btn ghost" data-act="close">' + esc(tw("nv.cancel")) + '</button><button type="submit" class="nv-btn pri">' + esc(f.edit ? tw("nv.save") : tw("nv.f.give")) + "</button></div></form></div>";
  }
  function openForm(it) {
    if (it && it.src === "reminder") {
      var raw = it.raw || {}, ts = stamp(raw.due_at);
      S.form = { edit: it.ref, text: raw.text || it.title, mode: raw.mode === "notify" ? "remind" : "do", date: ts.date, time: ts.time, rep: "", cronLocked: !!(raw.cron || raw.repeat_min) };
    } else S.form = { text: "", mode: "do", date: "", time: "", rep: "" };
    S.layer = "form"; renderLayer();
    var w = S.root.querySelector("#nvW"); if (w) w.focus();
  }
  async function submitForm() {
    var f = S.form, txt = (S.root.querySelector("#nvW").value || "").trim();
    var date = S.root.querySelector("#nvD").value, time = S.root.querySelector("#nvT").value, rep = S.root.querySelector("#nvR").value;
    f.text = txt; f.date = date; f.time = time; f.rep = rep;
    if (!txt) return;
    var b = brain(), r;
    if (f.edit) {
      var fields = { id: f.edit, brain: b, text: txt, mode: f.mode === "remind" ? "notify" : "task" };
      if (!f.cronLocked && date) fields.at = date + "T" + (time || "08:00");
      r = await postForm("/reminders/update", fields);
    } else if (!date && !rep && f.mode === "do") {
      r = await postForm("/kanban/task", { brain: b, title: txt.slice(0, 120), intent: txt, priority: 2 });
    } else {
      var body = { brain: b, text: txt, label: txt.slice(0, 80), mode: f.mode === "remind" ? "notify" : "task", muc_quyen: "full", created_by: "dashboard" };
      if (rep) body.cron = cronFor(rep, date, time || "08:00");
      else body.at = (date || S.m.today) + "T" + (time || "08:00");
      r = await postJSON("/reminders", body);
      if (r && r.ok === false && r.can_force) {
        if (window.confirm(r.error + "\n\n" + tw("nv.f.force"))) { body.allow_no_channel = true; r = await postJSON("/reminders", body); }
        else return;
      }
    }
    if (r && r.ok === false) { f.err = r.error || tw("nv.err.generic"); renderLayer(); return; }
    S.layer = null; S.form = null; renderLayer();
    toast(f.edit ? tw("nv.saved") : tw("nv.f.given"));
    await load(); render(); schedulePoll();
  }

  // ---------- actions ----------
  function parts(id) { var i = id.indexOf(":"); return { k: id.slice(0, i), ref: id.slice(i + 1) }; }
  async function doAct(a, id, el) {
    var b = brain(), it = id ? find(id) : null, p = id ? parts(id) : null;
    switch (a) {
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
        var r = S.m.recurring.find(function (x) { return x.id === id; });
        if (!r) return;
        var undo = function () { return toggleRep(r, r.on); };
        var res = await toggleRep(r, !r.on);
        if (res && res.ok === false) { toast(res.error || tw("nv.err.generic")); return; }
        S.sheet = null; await load(); render();
        toast(r.on ? tw("nv.ok.paused") : tw("nv.ok.resumed"), function () { undo().then(function () { load().then(render); }); });
        return;
      }
      case "m-skip": S.sheet = null; return act(postForm("/reminders/skip", { brain: b, id: it.ref }), tw("nv.ok.skip"));
      case "m-edit": S.sheet = null; S.sel = null; renderLayer(); return openForm(it);
      case "m-cancel":
        S.sheet = null; S.sel = null;
        if (it.src === "kanban") return later(id, tw("nv.ok.cancelled"), function () { return postForm("/kanban/task/cancel", { brain: b, id: it.ref }); });
        return later(id, tw("nv.ok.cancelled"), function () { return postForm("/reminders/cancel", { brain: b, id: it.ref }); });
      case "m-del":
        S.sheet = null; S.sel = null;
        return later(id, tw("nv.ok.deleted"), function () {
          if (it.src === "kanban") return postForm("/kanban/task/delete", { brain: b, id: it.ref });
          if (it.src === "reminder") return postForm("/reminders/delete", { brain: b, id: it.ref });
          if (it.src === "loop") return postForm("/loops/delete", { brain: b, slug: it.ref });
          return postJSON("/watch/action", { id: it.ref, action: "delete", brain: b });
        });
      case "m-move": S.sheet = { kind: "move", id: id }; return renderLayer();
      case "move-to": {
        var to = el.dataset.v; S.sheet = null; S.sel = null;
        if (it.src === "reminder") return act(postForm("/reminders/move", { id: it.ref, from_brain: b, to_brain: to }), tw("nv.ok.moved"));
        if (it.src === "loop") return act(postForm("/loops/move", { slug: it.ref, from_brain: b, to_brain: to }), tw("nv.ok.moved"));
        return;
      }
      case "grant": return act(postForm("/kanban/task/grant", { brain: b, id: it.ref }), tw("nv.ok.granted"));
      case "approve": return act(postForm("/kanban/task/move", { brain: b, id: it.ref, status: "done" }), tw("nv.ok.approved"));
      case "resolve": return act(postJSON("/incidents/resolve", { id: id }), tw("nv.ok.resolved"));
      case "orch": return act(postForm("/kanban/orchestration", { brain: b, mode: el.dataset.v }), el.dataset.v === "off" ? tw("nv.orch.off_ok") : tw("nv.orch.on_ok"));
    }
  }
  function toggleRep(r, on) {
    var b = brain();
    if (r.src === "reminder") return postForm("/reminders/pause", { brain: b, id: r.ref, paused: on ? "0" : "1" });
    if (r.src === "loop") return postForm("/loops/toggle", { brain: b, slug: r.ref });
    return postJSON("/watch/action", { id: r.ref, action: on ? "resume" : "pause", brain: b });
  }

  // ---------- render + events ----------
  function renderLayer() {
    var L = S.root.querySelector(".nv-layer");
    var it = S.sel && window.innerWidth > 760 ? find(S.sel) : null;
    L.innerHTML = (S.layer === "form" ? formHtml() : it ? drawerHtml(it) : "") + sheetHtml();
  }
  function render() {
    if (!S || !S.m) return;
    renderDesk(); renderPhone(); renderLayer();
  }
  function setView(v) { S.view = v; S.sel = null; lsSet("view", v); render(); }

  function onClick(e) {
    var t = e.target;
    var a = t.closest("[data-act]");
    if (a && S.root.contains(a)) {
      var act_ = a.dataset.act, id = a.dataset.id;
      if (act_ === "close") { S.sel = null; S.layer = null; S.form = null; renderLayer(); return; }
      if (act_ === "sheetclose") { S.sheet = null; renderLayer(); return; }
      if (act_ === "menu") { S.sheet = { kind: "menu", id: id }; renderLayer(); return; }
      if (act_ === "fold") { S.showDone = !S.showDone; render(); return; }
      if (act_ === "morewho") { S.moreWho = !S.moreWho; lsSet("morewho", S.moreWho ? "1" : ""); render(); return; }
      if (act_ === "pin") { var P = pins(), i = P.indexOf(id); if (i >= 0) P.splice(i, 1); else P.push(id); lsSet("pins", JSON.stringify(P)); render(); return; }
      if (act_ === "fmode") { S.form.text = S.root.querySelector("#nvW").value; S.form.mode = a.dataset.v; renderLayer(); return; }
      if (act_ === "new") { openForm(null); return; }
      doAct(act_, id, a);
      return;
    }
    var v = t.closest("[data-view]"); if (v) { setView(v.dataset.view); return; }
    var pl = t.closest("[data-pl]"); if (pl) { S.phone = { screen: "list", list: pl.dataset.pl }; render(); window.scrollTo(0, 0); return; }
    var pb = t.closest("[data-pback]"); if (pb) { S.phone = S.phone.screen === "detail" && S.phone.from ? { screen: "list", list: S.phone.from } : { screen: "home" }; render(); return; }
    var o = t.closest("[data-open]");
    if (o) {
      var oid = o.dataset.open;
      if (!find(oid)) return;
      if (window.innerWidth <= 760) { S.phone = { screen: "detail", id: oid, from: S.phone.screen === "list" ? S.phone.list : "" }; render(); window.scrollTo(0, 0); }
      else { S.sel = oid; render(); }
    }
  }
  async function onSubmit(e) {
    var f = e.target;
    if (!S.root.contains(f)) return;
    e.preventDefault();
    var b = brain();
    if (f.dataset.form) return submitForm();
    if (f.dataset.answer) { var it = find(f.dataset.answer); return act(postForm("/kanban/task/answer", { brain: b, id: it.ref, answer: f.querySelector("textarea").value }), tw("nv.ok.sent")); }
    if (f.dataset.follow) { var it2 = find(f.dataset.follow); return act(postForm("/kanban/task/followup", { brain: b, id: it2.ref, text: f.querySelector("textarea").value }), tw("nv.ok.sent")); }
  }
  function onKey(e) {
    if (e.key === "Escape" && S && (S.sel || S.layer || S.sheet)) { S.sel = null; S.layer = null; S.sheet = null; renderLayer(); }
  }

  async function mount(el) {
    if (S) unmount();
    S = { root: el, view: lsGet("view", "today"), q: "", sel: null, layer: null, sheet: null, form: null, hidden: {}, showDone: false,
      moreWho: lsGet("morewho", "") === "1", phone: { screen: "home" }, agents: null, m: null };
    if (!LISTS_AI.some(function (L) { return L[0] === S.view; }) && S.view.indexOf("who:") !== 0) S.view = "today";
    el.classList.add("nv-root");
    el.innerHTML = '<div class="nv-desk"><nav class="nv-side" aria-label="' + esc(tw("nv.title")) + '"></nav><section class="nv-main"><div class="nv-top"></div>'
      + '<div class="nv-search">' + ic("search") + '<input type="search" id="nvQ" autocomplete="off" placeholder="' + esc(tw("nv.search_ph")) + '" aria-label="' + esc(tw("nv.search_ph")) + '"></div>'
      + '<div class="nv-askbox"></div><div class="nv-view"><div class="nv-empty">' + esc(tw("common.loading")) + "</div></div></section></div>"
      + '<div class="nv-phone"><div class="nv-ptabs"></div><div class="nv-pbody"></div></div>'
      + '<button type="button" class="nv-fab" data-act="new" aria-label="' + esc(tw("nv.f.new")) + '" title="' + esc(tw("nv.f.new")) + '">' + ic("plus") + "</button><div class=\"nv-layer\"></div>";
    el.addEventListener("click", onClick);
    el.addEventListener("submit", onSubmit);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", fitSide);
    document.addEventListener("scroll", fitSide, { passive: true, capture: true });   // the page scrolls inside #cviewBody
    el.querySelector("#nvQ").addEventListener("input", function (e) { S.q = e.target.value; S.root.querySelector(".nv-view").innerHTML = viewHtml(S.view); });
    await load();
    if (!S || S.root !== el) return;
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

  window.JavisTasks = { mount: mount, unmount: unmount, _model: model_ };
})();
