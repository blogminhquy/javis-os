/* Date range picker shared by the Chatbot page (owner, 2026-10-28: "về bộ lọc thì nên có đầy đủ 1 chút", with a
 * screenshot of the usual picker): quick ranges on the left (today, yesterday, last 7 / 30 / 90 days, last month, week
 * to date, month to date), two months on the right with the from and to dates on top, Close / Apply at the bottom.
 * Weeks start on Monday. One month on phones.
 *
 * A range is {preset} for a quick one (resolved again each time, so "last 7 days" moves with the calendar) or
 * {from, to} ("YYYY-MM-DD", both days included) for one picked on the calendar. Pure helpers (`resolve`, `label`,
 * `monthCells`, `iso`) are exported for node tests; `open` draws the popover. Keys `dr.*`. */
(function () {
  "use strict";

  var PRESETS = ["today", "yesterday", "d7", "d30", "d90", "last_month", "week", "month"];
  // Spelled out so the i18n check sees every key.
  var PKEY = { all: "dr.p_all", today: "dr.p_today", yesterday: "dr.p_yesterday", d7: "dr.p_d7", d30: "dr.p_d30", d90: "dr.p_d90",
               last_month: "dr.p_last_month", week: "dr.p_week", month: "dr.p_month" };

  function t(k, v) { return window.t(k, v); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function parse(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || ""));
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  }
  function addDays(d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); }
  function dmy(s) { var d = parse(s); return d ? pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + "/" + d.getFullYear() : ""; }

  // A quick range on a given day (`now`, a Date) -> {from, to}; an unknown preset gives null.
  function resolve(preset, now) {
    var d = now ? new Date(now.getFullYear(), now.getMonth(), now.getDate()) : new Date(new Date().setHours(0, 0, 0, 0));
    switch (preset) {
      case "today": return { from: iso(d), to: iso(d) };
      case "yesterday": return { from: iso(addDays(d, -1)), to: iso(addDays(d, -1)) };
      case "d7": return { from: iso(addDays(d, -6)), to: iso(d) };
      case "d30": return { from: iso(addDays(d, -29)), to: iso(d) };
      case "d90": return { from: iso(addDays(d, -89)), to: iso(d) };
      case "last_month": return { from: iso(new Date(d.getFullYear(), d.getMonth() - 1, 1)), to: iso(new Date(d.getFullYear(), d.getMonth(), 0)) };
      case "week": return { from: iso(addDays(d, -((d.getDay() + 6) % 7))), to: iso(d) };
      case "month": return { from: iso(new Date(d.getFullYear(), d.getMonth(), 1)), to: iso(d) };
      default: return null;
    }
  }

  // The dates a range stands for today: a preset is resolved, a picked range is kept as it is.
  function dates(r, now) {
    if (!r) return null;
    if (r.preset) return resolve(r.preset, now);
    return r.from && r.to ? { from: r.from, to: r.to } : null;
  }

  function label(r) {
    if (!r) return t("dr.all");
    if (r.preset && PRESETS.indexOf(r.preset) >= 0) return t(PKEY[r.preset]);
    if (r.from && r.to) return r.from === r.to ? dmy(r.from) : dmy(r.from) + " - " + dmy(r.to);
    return t("dr.all");
  }

  // The 42 cells (6 weeks, Monday first) of a month: {iso, day, out} where `out` marks days of the next or previous month.
  function monthCells(year, month) {
    var first = new Date(year, month, 1), start = addDays(first, -((first.getDay() + 6) % 7)), out = [];
    for (var i = 0; i < 42; i++) {
      var d = addDays(start, i);
      out.push({ iso: iso(d), day: d.getDate(), out: d.getMonth() !== month });
    }
    return out;
  }

  // ---- the popover ----
  var _pop = null;

  function close() {
    if (!_pop) return;
    if (_pop.el.parentNode) _pop.el.parentNode.removeChild(_pop.el);
    document.removeEventListener("mousedown", _pop.outside, true);
    document.removeEventListener("keydown", _pop.key, true);
    var a = _pop.anchor;
    _pop = null;
    if (a && a.focus) a.focus();
  }

  // `anchor`: the button it opens under. `cur`: the range now. `onApply(range)`. `opts.all`: offer "Any time" too.
  function open(anchor, cur, onApply, opts) {
    close();
    var o = opts || {};
    var now = new Date();
    var start = dates(cur, now) || resolve("d7", now);
    var view = parse(start.to) || now;
    var st = { preset: cur && cur.preset || (cur ? "" : (o.all ? "all" : "")), from: start.from, to: start.to,
               y: view.getFullYear(), m: view.getMonth() - 1 };
    if (cur === null && o.all) { st.from = ""; st.to = ""; }
    var el = document.createElement("div");
    el.className = "dr-pop";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", t("dr.title"));
    document.body.appendChild(el);
    var phone = window.matchMedia && window.matchMedia("(max-width: 640px)").matches;

    function month(y, m, nav) {
      var d = new Date(y, m, 1);
      var head = '<div class="dr-mh">' + (nav === "l" || nav === "lr" ? '<button type="button" class="dr-nav" data-n="-12" aria-label="' + esc(t("dr.prev_y")) + '">«</button>' +
        '<button type="button" class="dr-nav" data-n="-1" aria-label="' + esc(t("dr.prev_m")) + '">‹</button>' : '<span></span><span></span>') +
        '<b>' + esc(t("dr.month", { m: d.getMonth() + 1, y: d.getFullYear() })) + '</b>' +
        (nav === "r" || nav === "lr" ? '<button type="button" class="dr-nav" data-n="1" aria-label="' + esc(t("dr.next_m")) + '">›</button>' +
          '<button type="button" class="dr-nav" data-n="12" aria-label="' + esc(t("dr.next_y")) + '">»</button>' : '<span></span><span></span>') + '</div>';
      var wd = ["dr.w1", "dr.w2", "dr.w3", "dr.w4", "dr.w5", "dr.w6", "dr.w7"].map(function (k) { return '<span class="dr-wd">' + esc(t(k)) + '</span>'; }).join("");
      var today = iso(now);
      var cells = monthCells(d.getFullYear(), d.getMonth()).map(function (c) {
        var a = st.from, b = st.to || st.from;
        var on = a && c.iso >= a && c.iso <= b, edge = c.iso === a || c.iso === b;
        return '<button type="button" class="dr-d' + (c.out ? " out" : "") + (on ? " in" : "") + (edge && a ? " edge" : "") +
          (c.iso === today ? " now" : "") + '" data-d="' + c.iso + '" aria-pressed="' + !!(edge && a && !c.out) + '"' +
          (c.iso > today ? " disabled" : "") + '>' + c.day + '</button>';
      }).join("");
      return '<div class="dr-m">' + head + '<div class="dr-grid">' + wd + cells + '</div></div>';
    }

    function paint() {
      var pre = (o.all ? ["all"] : []).concat(PRESETS).map(function (p) {
        return '<button type="button" class="dr-p' + (st.preset === p ? " on" : "") + '" data-p="' + p + '">' + esc(t(PKEY[p])) + '</button>';
      }).join("");
      var months = phone ? month(st.y, st.m + 1, "lr") : month(st.y, st.m, "l") + month(st.y, st.m + 1, "r");
      el.innerHTML = '<div class="dr-body"><div class="dr-pre">' + pre + '</div><div class="dr-cal">' +
        '<div class="dr-top"><span class="dr-in">' + esc(st.from ? dmy(st.from) : t("dr.from")) + '</span><span aria-hidden="true">→</span>' +
        '<span class="dr-in">' + esc(st.to ? dmy(st.to) : t("dr.to")) + '</span></div><div class="dr-ms">' + months + '</div></div></div>' +
        '<div class="dr-ft"><span class="dr-hint">' + esc(st.from && !st.to ? t("dr.pick_end") : "") + '</span>' +
        '<button type="button" class="s-btn-ghost dr-close">' + esc(t("dr.close")) + '</button>' +
        '<button type="button" class="s-btn dr-apply"' + (st.preset || (st.from && st.to) ? "" : " disabled") + '>' + esc(t("dr.apply")) + '</button></div>';
      place();
    }

    function place() {
      var r = anchor.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight;
      var w = el.offsetWidth, h = el.offsetHeight;
      el.style.left = Math.max(8, Math.min(r.left, vw - w - 8)) + "px";
      var top = r.bottom + 6;
      if (top + h > vh - 8) top = Math.max(8, vh - h - 8);
      el.style.top = top + "px";
    }

    el.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("button");
      if (!b || b.disabled) return;
      if (b.dataset.p) {
        st.preset = b.dataset.p;
        var r = b.dataset.p === "all" ? null : resolve(b.dataset.p, now);
        st.from = r ? r.from : ""; st.to = r ? r.to : "";
        if (r) { var v = parse(r.to); st.y = v.getFullYear(); st.m = v.getMonth() - 1; }
        paint();
      } else if (b.dataset.n) {
        var n = +b.dataset.n, dd = new Date(st.y, st.m + n, 1);
        st.y = dd.getFullYear(); st.m = dd.getMonth();
        paint();
      } else if (b.dataset.d) {
        st.preset = "";
        if (!st.from || st.to) { st.from = b.dataset.d; st.to = ""; }
        else if (b.dataset.d < st.from) { st.to = st.from; st.from = b.dataset.d; }
        else st.to = b.dataset.d;
        paint();
        var again = el.querySelector('.dr-d:not(.out)[data-d="' + b.dataset.d + '"]');
        if (again) again.focus();
      } else if (b.classList.contains("dr-close")) close();
      else if (b.classList.contains("dr-apply")) {
        var out = st.preset === "all" ? null : st.preset ? { preset: st.preset } : { from: st.from, to: st.to };
        close();
        onApply(out);
      }
    });
    var outside = function (e) { if (!el.contains(e.target) && !anchor.contains(e.target)) close(); };
    var key = function (e) { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    document.addEventListener("mousedown", outside, true);
    document.addEventListener("keydown", key, true);
    _pop = { el: el, anchor: anchor, outside: outside, key: key };
    paint();
    var f = el.querySelector(".dr-p.on") || el.querySelector(".dr-p");
    if (f) f.focus();
  }

  window.JavisDateRange = { PRESETS: PRESETS, resolve: resolve, dates: dates, label: label, monthCells: monthCells, iso: iso,
                            open: open, close: close };
})();
