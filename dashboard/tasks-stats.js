/* Tasks page, list "Stats" on both tabs (0.428.0). Design approved by the owner on 2026-10-31.
 *
 * "My tasks": what the owner finished over the period, day by day, a 12-week map, the hours they finish most, habits,
 * projects and the tasks they keep moving. "Javis's tasks": how much of the work Javis carried next to the owner, the
 * time it gave back (minutes per kind of job, editable; no money, the owner asked for time only), what it did, which
 * assistant did it, when, how reliably, and what it could take over next.
 *
 * Data: GET /tasks/stats?brain&from&to (server/task_stats.py). The period comes from the shared date range picker
 * (date-range.js, same as the Chatbot stats), remembered in this browser. tasks.js calls `html(ctx)` on every render;
 * the answer is cached per tab, brain and period, so the 3-second redraws never refetch or flicker.
 * Pure helpers (`fmtHours`, `bestDay`, `goldWindow`, `deltaPct`) are exported for node tests. */
(function () {
  "use strict";

  var cache = {}, loading = {}, editing = false, LSKEY = "javis.nv.range";

  function tw(key, vars) {
    var s = (typeof window !== "undefined" && window.t) ? window.t(key, vars) : key;
    if (vars) s = String(s).replace(/\{(\w+)\}/g, function (m, k) { return Object.prototype.hasOwnProperty.call(vars, k) ? String(vars[k]) : m; });
    return s;
  }
  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function ic(name, cls) { return (typeof window !== "undefined" && window.ic) ? window.ic(name, cls ? { cls: cls } : undefined) : ""; }
  function num(n, digits) {
    try { return new Intl.NumberFormat(tw("nv.sta.locale"), { maximumFractionDigits: digits || 0 }).format(n); } catch (e) { return String(n); }
  }
  var WD = ["nv.wd.sun", "nv.wd.mon", "nv.wd.tue", "nv.wd.wed", "nv.wd.thu", "nv.wd.fri", "nv.wd.sat"];
  var LOGO = '<img class="ts-logo" src="/static/logo.svg" alt="" aria-hidden="true">';

  // ---------- pure helpers ----------
  function things(n) { return tw(Number(n) === 1 ? "nv.sta.one_thing" : "nv.sta.n_things", { n: n }); }
  function fmtHours(min) { return min >= 60 ? tw("nv.sta.hours", { n: num(min / 60, 1) }) : tw("nv.sta.minutes", { n: Math.round(min) }); }
  function deltaPct(cur, prev) { return prev ? Math.round((cur - prev) * 100 / prev) : null; }
  // The weekday with the most finished things in by_day {iso: {task, habit, appt}} -> {wd, n} or null.
  function bestDay(byDay) {
    var tot = [0, 0, 0, 0, 0, 0, 0];
    Object.keys(byDay || {}).forEach(function (iso) {
      var v = byDay[iso], d = new Date(iso + "T12:00:00");
      tot[d.getDay()] += (v.task || 0) + (v.habit || 0) + (v.appt || 0);
    });
    var best = -1, n = 0;
    tot.forEach(function (x, i) { if (x > n) { n = x; best = i; } });
    return best >= 0 && n >= 2 ? { wd: best, n: n } : null;
  }
  // The two consecutive hours with the most finished things -> start hour, or -1.
  function goldWindow(hours) {
    var best = -1, n = 0;
    for (var h = 0; h < 23; h++) { var s = (hours[h] || 0) + (hours[h + 1] || 0); if (s > n) { n = s; best = h; } }
    return n >= 3 ? best : -1;
  }

  // ---------- period ----------
  function range() {
    var r = null;
    try { r = JSON.parse(window.localStorage.getItem(LSKEY) || "null"); } catch (e) { r = null; }
    return r && (r.preset || (r.from && r.to)) ? r : { preset: "d7" };
  }
  function dates(r) {
    var DR = window.JavisDateRange;
    return DR ? DR.dates(r) : null;
  }
  function dmy(iso) { return iso ? iso.slice(8, 10) + "/" + iso.slice(5, 7) + "/" + iso.slice(0, 4) : ""; }
  function label(r) {
    var DR = window.JavisDateRange;
    return DR ? DR.label(r) : "";
  }

  // ---------- data ----------
  function key(ctx) { var d = dates(range()) || {}; return [ctx.brain, d.from, d.to].join("|"); }
  function fetchStats(ctx, force) {
    var k = key(ctx), d = dates(range());
    if (!d || loading[k] || (!force && cache[k] && Date.now() - cache[k].at < 60000)) return;
    loading[k] = true;
    fetch("/tasks/stats?brain=" + encodeURIComponent(ctx.brain) + "&from=" + d.from + "&to=" + d.to)
      .then(function (r) { return r.json(); })
      .then(function (j) { cache[k] = { at: Date.now(), data: j }; })
      .catch(function (e) { cache[k] = { at: Date.now(), data: { ok: false, error: String(e) } }; })
      .then(function () { loading[k] = false; if (ctx.redraw) ctx.redraw(); });
  }

  // ---------- pieces ----------
  function card(cls, inner) { return '<section class="ts-card' + (cls ? " " + cls : "") + '">' + inner + "</section>"; }
  function h3(text, extra) { return '<div class="ts-h"><h3>' + esc(text) + "</h3>" + (extra || "") + "</div>"; }
  function chip(cur, prev, unitKey, lowerBetter) {
    if (prev == null) return "";
    var diff = cur - prev;
    if (!diff) return '<span class="ts-chip">' + esc(tw("nv.sta.same_prev")) + "</span>";
    var good = lowerBetter ? diff < 0 : diff > 0;
    return '<span class="ts-chip ' + (good ? "good" : "bad") + '">' + esc(tw(diff > 0 ? "nv.sta.more_prev" : "nv.sta.less_prev", { n: tw(unitKey, { n: Math.abs(diff) }) })) + "</span>";
  }
  function tile(lbl, value, sub, cls) {
    return '<div class="ts-tile"><span class="ts-tl">' + esc(lbl) + '</span><b class="' + (cls || "") + '">' + esc(value) + '</b><span class="ts-ts">' + esc(sub || "") + "</span></div>";
  }
  function bars(list, max, cls) {
    return '<div class="ts-bars ' + (cls || "") + '">' + list.map(function (b) {
      return '<div class="ts-bar" title="' + esc(b.tip || "") + '">' + (b.top != null && b.top !== "" ? '<span class="ts-bv">' + esc(b.top) + "</span>" : "")
        + '<div class="ts-stack">' + b.parts.map(function (p) { return '<i class="' + p[0] + '" style="height:' + Math.round(p[1] * 150 / Math.max(1, max)) + 'px"></i>'; }).join("") + "</div></div>";
    }).join("") + '</div><div class="ts-xl">' + list.map(function (b) { return '<span class="' + (b.hot ? "hot" : "") + '">' + esc(b.x) + "</span>"; }).join("") + "</div>";
  }

  // ---------- My tasks ----------
  function mineHtml(d, ctx) {
    var me = d.me, lab = label(range());
    var spark = d.weeks.map(function (w) { return w.me; }), smax = Math.max.apply(null, spark.concat([1]));
    var pts = spark.map(function (v, i) { return (6 + i * 30) + "," + (60 - Math.round(v * 52 / smax)); }).join(" ");
    var h = '<div class="ts-grid2 wide">' + card("ts-hero",
      '<div class="ts-hero-l"><span class="ts-tl">' + esc(tw("nv.sta.me_done_in", { p: lab })) + '</span><div class="ts-big"><b>' + num(me.done) + "</b><span>" + esc(tw("nv.sta.things")) + "</span></div>"
      + chip(me.done, me.prev_done, "nv.sta.n_things") + "</div>"
      + '<div class="ts-spark"><span class="ts-tl">' + esc(tw("nv.sta.weeks8")) + '</span><svg viewBox="0 0 222 64" role="img" aria-label="' + esc(tw("nv.sta.weeks8")) + '"><polyline points="' + pts + '"/></svg></div>');
    var bd = bestDay(me.by_day);
    h += card("ts-talk", LOGO + '<div><span class="ts-kicker">' + esc(tw("nv.sta.javis_says")) + "</span><p>"
      + esc(bd ? tw("nv.sta.say_best", { day: tw(WD[bd.wd]), n: bd.n }) : me.done ? tw("nv.sta.say_keep") : tw("nv.sta.say_start")) + "</p></div>") + "</div>";
    var hab = me.habits.reduce(function (a, x) { return [a[0] + x.done, a[1] + x.sched]; }, [0, 0]);
    h += '<div class="ts-tiles">'
      + tile(tw("nv.sta.on_time"), me.on_time == null ? "-" : me.on_time + "%", me.prev_on_time == null || me.on_time == null ? "" : tw("nv.sta.pts_prev", { n: (me.on_time - me.prev_on_time >= 0 ? "+" : "") + (me.on_time - me.prev_on_time) }), me.on_time >= 80 ? "ok" : "")
      + tile(tw("nv.sta.overdue"), num(me.overdue), me.overdue ? tw("nv.sta.overdue_sub") : tw("nv.sta.overdue_none"), me.overdue ? "warn" : "ok")
      + tile(tw("nv.sta.habits30"), hab[1] ? hab[0] + "/" + hab[1] : "-", hab[1] ? tw("nv.sta.pct_sessions", { n: Math.round(hab[0] * 100 / hab[1]) }) : tw("nv.sta.no_habits"), "me")
      + tile(tw("nv.sta.appts"), num(me.appts), me.javis_ticks ? tw("nv.sta.javis_ticks", { n: me.javis_ticks }) : "", "blue") + "</div>";
    // Day by day (by week past 31 days).
    var D = d.range.days <= 31 ? daysOf(d.range.from, d.range.to).map(function (iso) {
      var v = me.by_day[iso] || {}, dt = new Date(iso + "T12:00:00");
      var n = (v.task || 0) + (v.habit || 0) + (v.appt || 0), long = d.range.days > 14;
      return { x: d.range.days <= 8 ? tw(WD[dt.getDay()]) : (!long || dt.getDate() % 5 === 1 ? String(dt.getDate()) : ""), parts: [["c-task", v.task || 0], ["c-hab", v.habit || 0], ["c-appt", v.appt || 0]],
        top: long && !n ? "" : n, tip: dmy(iso) + ": " + n, hot: bd && dt.getDay() === bd.wd && d.range.days <= 8 };
    }) : d.weeks.map(function (w) { return { x: w.from.slice(8, 10) + "/" + w.from.slice(5, 7), parts: [["c-task", w.me]], top: w.me, tip: dmy(w.from) + " - " + dmy(w.to) }; });
    var dmax = Math.max.apply(null, D.map(function (b) { return b.top; }).concat([1]));
    var legend = '<span class="ts-lg"><i class="c-task"></i>' + esc(tw("nv.sta.k_task")) + '</span><span class="ts-lg"><i class="c-hab"></i>' + esc(tw("nv.sta.k_habit")) + '</span><span class="ts-lg"><i class="c-appt"></i>' + esc(tw("nv.sta.k_appt")) + "</span>";
    h += '<div class="ts-grid2">' + card("", h3(tw(d.range.days <= 31 ? "nv.sta.per_day" : "nv.sta.per_week"), legend) + bars(D, dmax));
    // 12-week map, Monday first.
    var first = new Date(me.heat[0].d + "T12:00:00"), padN = (first.getDay() + 6) % 7, hmax = Math.max.apply(null, me.heat.map(function (c) { return c.n; }).concat([1]));
    var cells = "";
    for (var p = 0; p < padN; p++) cells += '<span class="ts-hc none"></span>';
    me.heat.forEach(function (c) { var lv = c.n ? Math.min(4, Math.ceil(c.n * 4 / hmax)) : 0; cells += '<span class="ts-hc l' + lv + '" title="' + esc(dmy(c.d) + ": " + c.n) + '"></span>'; });
    var active = me.heat.filter(function (c) { return c.n; }).length;
    h += card("", h3(tw("nv.sta.map")) + '<p class="ts-note">' + esc(tw("nv.sta.map_sub")) + '</p><div class="ts-heat">' + cells + "</div>"
      + '<div class="ts-heatl">' + esc(tw("nv.sta.less")) + '<i class="ts-hc l0"></i><i class="ts-hc l1"></i><i class="ts-hc l2"></i><i class="ts-hc l3"></i><i class="ts-hc l4"></i>' + esc(tw("nv.sta.more")) + '<span class="ts-grow"></span>' + esc(tw("nv.sta.active_days", { n: active })) + "</div>") + "</div>";
    // Golden hours and habits.
    var G = [], gmax = 1, gw = goldWindow(me.gold);
    for (var hh = 6; hh < 24; hh++) { G.push(hh); gmax = Math.max(gmax, me.gold[hh] || 0); }
    var gold = '<div class="ts-bars thin">' + G.map(function (x) { return '<div class="ts-bar" title="' + x + 'h: ' + (me.gold[x] || 0) + '"><div class="ts-stack"><i class="' + (gw >= 0 && (x === gw || x === gw + 1) ? "c-hot" : "c-soft") + '" style="height:' + Math.max(4, Math.round((me.gold[x] || 0) * 110 / gmax)) + 'px"></i></div></div>'; }).join("") + "</div>"
      + '<div class="ts-xl sparse"><span>6h</span><span>12h</span><span>18h</span><span>23h</span></div>';
    h += '<div class="ts-grid2">' + card("", h3(tw("nv.sta.gold")) + '<p class="ts-note">' + esc(tw("nv.sta.gold_sub")) + "</p>" + gold
      + (gw >= 0 ? '<div class="ts-tip">' + esc(tw("nv.sta.gold_tip", { a: gw, b: gw + 2 })) + "</div>" : ""));
    h += card("", h3(tw("nv.sta.habits"), '<span class="ts-note">' + esc(tw("nv.sta.habits_sub")) + "</span>") + (me.habits.length ? me.habits.map(function (x) {
      var r = x.rate == null ? 0 : x.rate, cls = x.frozen ? "ice" : r >= 80 ? "ok" : r >= 50 ? "mid" : "low";
      return '<div class="ts-row"><div class="ts-rh">' + ic("flame", x.frozen ? "c-ice" : "c-habit") + '<span class="ts-rt">' + esc(x.title) + '</span><span class="ts-note">'
        + esc(x.frozen ? tw("nv.sta.frozen") : tw("nv.sta.streak", { n: x.cur })) + '</span><b class="' + cls + '">' + (x.rate == null ? "-" : r + "%") + '</b></div><div class="ts-meter"><i class="' + cls + '" style="width:' + r + '%"></i></div></div>';
    }).join("") : '<p class="ts-note">' + esc(tw("nv.sta.no_habits")) + "</p>")) + "</div>";
    // Projects and tasks kept moving.
    h += '<div class="ts-grid2">' + card("", h3(tw("nv.sta.projects")) + (me.projects.length ? me.projects.map(function (x) {
      var pc = Math.round(x.done * 100 / Math.max(1, x.total));
      return '<div class="ts-row"><div class="ts-rh"><i class="ts-dot" style="background:' + esc(x.color || "#888") + '"></i><span class="ts-rt">' + esc(x.name) + '</span><span class="ts-note">' + esc(tw("nv.sta.of", { a: x.done, b: x.total })) + '</span></div><div class="ts-meter"><i style="width:' + pc + "%;background:" + esc(x.color || "#888") + '"></i></div></div>';
    }).join("") : '<p class="ts-note">' + esc(tw("nv.sta.no_projects")) + "</p>"));
    h += card("", h3(tw("nv.sta.moved")) + '<p class="ts-note">' + esc(tw("nv.sta.moved_sub")) + "</p>" + (me.delayed.length ? me.delayed.map(function (x) {
      return '<div class="ts-moved"><b>' + esc(tw("nv.sta.times", { n: x.moves })) + '</b><span class="ts-rt">' + esc(x.title) + '</span><button type="button" class="nv-btn sm ts-ai" data-act="st-give" data-id="m:' + esc(x.id) + '">' + esc(tw("nv.a.tojavis")) + "</button></div>";
    }).join("") : '<p class="ts-note">' + esc(tw("nv.sta.moved_none")) + "</p>")) + "</div>";
    return h;
  }
  function daysOf(a, b) {
    var out = [], d = new Date(a + "T12:00:00"), end = new Date(b + "T12:00:00");
    while (d <= end && out.length < 400) { out.push(d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0")); d.setDate(d.getDate() + 1); }
    return out;
  }

  // ---------- Javis's tasks ----------
  var KIND_KEYS = { reminder: "nv.sta.k_reminder", loop: "nv.sta.k_loop", kanban: "nv.sta.k_kanban", notify: "nv.sta.k_notify", watch: "nv.sta.k_watch" };
  var KIND_COLOR = { reminder: "#8b5cf6", loop: "#38bdf8", kanban: "#f0c020", notify: "#ff9bd2", watch: "#34d36b" };
  function aiHtml(d, ctx) {
    var ai = d.ai, me = d.me, lab = label(range()), tot = ai.done + me.done;
    var lever = me.done ? num(ai.done / me.done, 1) : null;
    var sp = tw("nv.sta.ai_share", { p: lab, pct: "\u0001" }).split("\u0001");
    var h = card("ts-hero ai", '<div class="ts-h"><h2>' + esc(sp[0]) + '<span class="ts-hl">' + ai.share + "%</span>" + esc(sp[1] || "") + "</h2>"
      + (d.ai.prev_done + d.me.prev_done ? '<span class="ts-chip ' + (ai.share >= ai.prev_share ? "good" : "") + '">' + esc(tw("nv.sta.share_prev", { n: ai.prev_share })) + "</span>" : "") + "</div>"
      // Each side keeps room for its label however lopsided the split; the night count lives in its own tile.
      + '<div class="ts-split">' + (me.done ? '<div class="me" style="flex:' + me.done + ' 1 0">' + ic("circle-user") + "<b>" + esc(tw("nv.sta.you_n", { n: me.done })) + "</b></div>" : "")
      + (ai.done ? '<div class="ai" style="flex:' + ai.done + ' 1 0">' + LOGO + "<b>" + esc(tw("nv.sta.javis_n", { n: ai.done })) + "</b></div>" : "")
      + (!tot ? '<div class="none">' + esc(tw("nv.sta.nothing_yet")) + "</div>" : "") + "</div>"
      + '<div class="ts-facts">' + fact(lever ? lever + "x" : "-", tw("nv.sta.lever")) + fact(num(tot), tw("nv.sta.total")) + fact(num(ai.handoffs), tw("nv.sta.handoffs")) + fact(num(me.javis_ticks), tw("nv.sta.ticks")) + "</div>");
    var answered = ai.rel.ok + ai.rel.fail + ai.rel.ask, okPct = answered ? Math.round(ai.rel.ok * 100 / answered) : null;
    h += '<div class="ts-tiles">'
      + tile(tw("nv.sta.saved"), fmtHours(ai.saved), tw("nv.sta.saved_sub", { n: (ai.saved - ai.prev_saved >= 0 ? "+" : "-") + fmtHours(Math.abs(ai.saved - ai.prev_saved)) }), "ai")
      + tile(tw("nv.sta.ai_done"), things(num(ai.done)), ai.prev_done == null ? "" : tw(ai.done >= ai.prev_done ? "nv.sta.more_prev" : "nv.sta.less_prev", { n: things(Math.abs(ai.done - ai.prev_done)) }), "")
      + tile(tw("nv.sta.night"), things(num(ai.night)), tw("nv.sta.night_sub"), "")
      + tile(tw("nv.sta.ok"), okPct == null ? "-" : okPct + "%", ai.rel.ask ? tw("nv.sta.ask_n", { n: ai.rel.ask }) : "", okPct != null && okPct >= 90 ? "ok" : "") + "</div>";
    // 8 weeks, you and Javis.
    var W = d.weeks.map(function (w, i) {
      var s = w.me + w.ai ? Math.round(w.ai * 100 / (w.me + w.ai)) : 0;
      return { x: i === 7 ? tw("nv.sta.this_week") : "T" + (i + 1), parts: [["c-me", w.me], ["c-ai", w.ai]], top: w.me + w.ai ? s + "%" : "", side: true, tip: dmy(w.from) + " - " + dmy(w.to) + ": " + w.me + " / " + w.ai };
    });
    var wmax = Math.max.apply(null, d.weeks.map(function (w) { return Math.max(w.me, w.ai); }).concat([1]));
    var share0 = d.weeks[0].me + d.weeks[0].ai ? Math.round(d.weeks[0].ai * 100 / (d.weeks[0].me + d.weeks[0].ai)) : 0, share7 = d.weeks[7].me + d.weeks[7].ai ? Math.round(d.weeks[7].ai * 100 / (d.weeks[7].me + d.weeks[7].ai)) : 0;
    h += '<div class="ts-grid2 wide">' + card("", h3(tw("nv.sta.weeks_vs"), '<span class="ts-lg"><i class="c-me"></i>' + esc(tw("nv.sta.you")) + '</span><span class="ts-lg"><i class="c-ai"></i>Javis</span>')
      + '<div class="ts-bars side">' + W.map(function (b) {
        return '<div class="ts-bar" title="' + esc(b.tip) + '"><span class="ts-bv">' + esc(b.top) + '</span><div class="ts-pair"><i class="c-me" style="height:' + Math.round(b.parts[0][1] * 150 / wmax) + 'px"></i><i class="c-ai" style="height:' + Math.round(b.parts[1][1] * 150 / wmax) + 'px"></i></div></div>';
      }).join("") + '</div><div class="ts-xl">' + W.map(function (b) { return "<span>" + esc(b.x) + "</span>"; }).join("") + "</div>"
      + '<p class="ts-note">' + esc(tw("nv.sta.weeks_note", { a: share0, b: share7 })) + "</p>");
    // Time given back.
    var smax = Math.max.apply(null, d.weeks.map(function (w) { return w.saved; }).concat([1]));
    h += card("ts-time", h3(tw("nv.sta.time_back"), '<button type="button" class="info-i" aria-expanded="false" aria-label="' + esc(tw("info.more")) + '" title="' + esc(tw("info.more")) + '">' + ic("info") + "</button>")
      + '<div class="info-body" hidden>' + esc(tw("nv.sta.time_how")) + "</div>"
      + '<div class="ts-big ai"><b>' + esc(fmtHours(ai.saved)) + "</b><span>" + esc(ai.saved >= 240 ? tw("nv.sta.workdays", { n: num(ai.saved / 480, 1) }) : "") + "</span></div>"
      + '<div class="ts-bars thin">' + d.weeks.map(function (w, i) { return '<div class="ts-bar" title="' + esc(dmy(w.from) + ": " + fmtHours(w.saved)) + '"><div class="ts-stack"><i class="' + (i === 7 ? "c-ai" : "c-ais") + '" style="height:' + Math.max(3, Math.round(w.saved * 70 / smax)) + 'px"></i></div></div>'; }).join("") + "</div>"
      + '<p class="ts-note">' + esc(tw("nv.sta.saved_weeks")) + "</p>"
      + '<div class="ts-kv"><span>' + esc(tw("nv.sta.saved_total")) + "</span><b>" + esc(fmtHours(ai.saved_total || 0)) + "</b></div>"
      + (editing ? minutesForm(d.minutes) : '<button type="button" class="nv-btn sm ts-ai" data-act="st-mins">' + esc(tw("nv.sta.edit_minutes")) + "</button>")) + "</div>";
    // What, who.
    var K = Object.keys(KIND_KEYS).filter(function (k) { return ai.by_kind[k] && ai.by_kind[k].n; }), kn = K.reduce(function (a, k) { return a + ai.by_kind[k].n; }, 0), off = 25, segs = "";
    K.forEach(function (k) { var len = ai.by_kind[k].n * 100 / Math.max(1, kn); segs += '<circle cx="21" cy="21" r="15.9" fill="none" stroke="' + KIND_COLOR[k] + '" stroke-width="6" stroke-dasharray="' + len.toFixed(2) + " " + (100 - len).toFixed(2) + '" stroke-dashoffset="' + off.toFixed(2) + '"/>'; off = (off - len + 100) % 100; });
    h += '<div class="ts-grid2">' + card("", h3(tw("nv.sta.what")) + (kn ? '<div class="ts-donut"><svg viewBox="0 0 42 42" role="img" aria-label="' + esc(things(kn)) + '"><circle cx="21" cy="21" r="15.9" fill="none" stroke="currentColor" stroke-opacity=".08" stroke-width="6"/>' + segs
      + '<text x="21" y="23.5" text-anchor="middle">' + kn + "</text></svg><div>" + K.map(function (k) {
        return '<div class="ts-kv"><span><i class="ts-dot" style="background:' + KIND_COLOR[k] + '"></i>' + esc(tw(KIND_KEYS[k])) + "</span><b>" + ai.by_kind[k].n + '</b><span class="ts-note">' + esc(fmtHours(ai.by_kind[k].minutes)) + "</span></div>";
      }).join("") + "</div></div>" : '<p class="ts-note">' + esc(tw("nv.sta.nothing_yet")) + "</p>"));
    h += card("", h3(tw("nv.sta.agents"), '<span class="ts-note">' + esc(tw("nv.sta.agents_sub")) + "</span>") + (ai.agents.length ? ai.agents.map(function (a) {
      var name = a.key === "core" ? "Javis Core" : (a.name || a.key), all = a.ok + a.fail;
      return '<div class="ts-agent">' + (a.key === "core" ? LOGO : ctx.avatar(a.key, 30)) + '<span class="ts-rt">' + esc(name) + "</span><b>" + a.n + '</b><span class="ok">' + (all ? Math.round(a.ok * 100 / all) + "%" : "-") + '</span><span class="ts-note">' + esc(fmtHours(a.minutes)) + "</span></div>";
    }).join("") : '<p class="ts-note">' + esc(tw("nv.sta.nothing_yet")) + "</p>")) + "</div>";
    // When, how reliably.
    var hmax = Math.max.apply(null, ai.hours.concat(me.hours).concat([1]));
    var strip = function (L, cls) { return L.map(function (v, i) { return '<i class="ts-hr ' + cls + '" style="opacity:' + (v ? (0.25 + 0.75 * v / hmax).toFixed(2) : 1) + (v ? "" : ";background:var(--ts-empty)") + '" title="' + i + "h: " + v + '"></i>'; }).join(""); };
    h += '<div class="ts-grid2 wide">' + card("", h3(tw("nv.sta.day24")) + '<p class="ts-note">' + esc(tw("nv.sta.day24_sub")) + "</p>"
      + '<div class="ts-24"><span class="me">' + esc(tw("nv.sta.you")) + "</span>" + strip(me.hours, "c-me") + '<span class="ai">Javis</span>' + strip(ai.hours, "c-ai")
      + "<span></span>" + ai.hours.map(function (_, i) { return "<small>" + (i % 3 === 0 ? i + "h" : "") + "</small>"; }).join("") + "</div>"
      + (ai.night ? '<div class="ts-tip ai">' + ic("moon") + esc(tw("nv.sta.night_tip", { n: ai.night })) + "</div>" : ""));
    var R = ai.rel, rt = Math.max(1, R.ok + R.retry + R.ask + R.fail);
    h += card("", h3(tw("nv.sta.rel")) + '<div class="ts-relbar"><i class="ok" style="width:' + (R.ok * 100 / rt) + '%"></i><i class="re" style="width:' + (R.retry * 100 / rt) + '%"></i><i class="ask" style="width:' + (R.ask * 100 / rt) + '%"></i><i class="fail" style="width:' + (R.fail * 100 / rt) + '%"></i></div>'
      + '<div class="ts-relk"><span><i class="ok"></i>' + esc(tw("nv.sta.r_ok")) + "<b>" + R.ok + "</b></span><span><i class=\"re\"></i>" + esc(tw("nv.sta.r_retry")) + "<b>" + R.retry + "</b></span><span><i class=\"ask\"></i>" + esc(tw("nv.sta.r_ask")) + "<b>" + R.ask + "</b></span><span><i class=\"fail\"></i>" + esc(tw("nv.sta.r_fail")) + "<b>" + R.fail + "</b></span></div>"
      + '<div class="ts-kv"><span>' + esc(tw("nv.sta.avg")) + "</span><b>" + esc(ai.avg_seconds ? (ai.avg_seconds >= 60 ? tw("nv.sta.minutes", { n: Math.round(ai.avg_seconds / 60) }) : tw("nv.sta.seconds", { n: ai.avg_seconds })) : "-") + "</b></div>") + "</div>";
    // Ideas.
    if (d.ideas && d.ideas.length) {
      h += card("ts-ideas", h3(tw("nv.sta.ideas"), '<span class="ts-note">' + esc(tw("nv.sta.ideas_sub")) + "</span>") + '<div class="ts-icards">' + d.ideas.map(function (x) {
        return '<div class="ts-idea"><span class="ts-kicker me">' + esc(x.kind === "moved" ? tw("nv.sta.idea_moved", { n: x.n }) : tw("nv.sta.idea_repeat", { n: x.n })) + "</span><b>" + esc(x.title) + "</b><p>"
          + esc(x.kind === "moved" ? tw("nv.sta.idea_moved_how") : tw("nv.sta.idea_repeat_how")) + '</p><div class="ts-ia"><span class="ok">' + esc(tw(x.kind === "moved" ? "nv.sta.idea_save_once" : "nv.sta.idea_save_week", { t: fmtHours(x.minutes) })) + '</span><button type="button" class="nv-btn sm pri ts-ai" data-act="st-give" data-id="m:' + esc(x.id) + '">' + esc(tw("nv.a.tojavis")) + "</button></div></div>";
      }).join("") + "</div>");
    }
    return h;
  }
  function fact(v, l) { return '<div class="ts-fact"><b>' + esc(v) + "</b><span>" + esc(l) + "</span></div>"; }
  function minutesForm(m) {
    return '<form class="ts-mins" data-stmins="1">' + Object.keys(KIND_KEYS).map(function (k) {
      return '<label><span>' + esc(tw(KIND_KEYS[k])) + '</span><input type="number" min="0" max="600" inputmode="numeric" name="' + k + '" value="' + esc(m[k]) + '"><small>' + esc(tw("nv.sta.min_unit")) + "</small></label>";
    }).join("") + '<div class="nv-acts end"><button type="button" class="nv-btn ghost sm" data-act="st-mins">' + esc(tw("nv.cancel")) + '</button><button type="submit" class="nv-btn pri sm">' + esc(tw("nv.save")) + "</button></div></form>";
  }

  // ---------- page part ----------
  // ctx: {tab: "me"|"ai", brain, redraw(), avatar(slug, size)}
  function html(ctx) {
    var r = range(), d = dates(r) || { from: "", to: "" };
    var head = '<div class="ts-top"><span class="ts-dates">' + esc(dmy(d.from) + (d.from !== d.to ? " - " + dmy(d.to) : "")) + "</span>"
      + '<button type="button" class="ts-range" data-act="st-range" aria-haspopup="dialog" aria-label="' + esc(tw("dr.title")) + '">' + ic("calendar") + "<span>" + esc(label(r)) + "</span>" + ic("chevron-down") + "</button></div>";
    var c = cache[key(ctx)];
    fetchStats(ctx, false);
    if (!c) return head + '<div class="nv-empty">' + esc(tw("common.loading")) + "</div>";
    if (!c.data || !c.data.ok) return head + '<div class="nv-empty">' + esc(tw("nv.sta.error")) + "</div>";
    return '<div class="ts ' + (ctx.tab === "me" ? "me" : "ai") + '">' + head + (ctx.tab === "me" ? mineHtml(c.data, ctx) : aiHtml(c.data, ctx)) + "</div>";
  }
  function openRange(anchor, ctx) {
    var DR = window.JavisDateRange;
    if (!DR) return;
    DR.open(anchor, range(), function (r) {
      try { window.localStorage.setItem(LSKEY, JSON.stringify(r || { preset: "d7" })); } catch (e) { /* no storage */ }
      if (ctx.redraw) ctx.redraw();
    });
  }
  function toggleMinutes(ctx) { editing = !editing; if (ctx.redraw) ctx.redraw(); }
  function saveMinutes(form, ctx) {
    var m = {};
    Array.prototype.forEach.call(form.querySelectorAll("input[name]"), function (i) { m[i.name] = Number(i.value); });
    return fetch("/tasks/stats/minutes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ brain: ctx.brain, minutes: m }) })
      .then(function () { editing = false; cache = {}; if (ctx.redraw) ctx.redraw(); });
  }
  function refresh() { cache = {}; }

  var api = { html: html, openRange: openRange, toggleMinutes: toggleMinutes, saveMinutes: saveMinutes, refresh: refresh, isEditing: function () { return editing; },
    fmtHours: fmtHours, bestDay: bestDay, goldWindow: goldWindow, deltaPct: deltaPct };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.JavisTaskStats = api;
})();
