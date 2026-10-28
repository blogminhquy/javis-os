/* Stats tab of the Chatbot page (Chatbot v5, owner 2026-10-28; docs/dev/2026-10-chatbot-v5-spec.md section 9).
 *
 * Any period from the date range picker (date-range.js: today, last 7 / 30 / 90 days, last month, ... or days on the
 * calendar). Four tiles: messages the A.I. answered, messages you answered, how long a customer waits
 * for a first answer, and chats that need you right now; each against the period before (GET
 * /conversations/insights). Then two single-series bar lists: A.I. answers per channel and per bot, values written at
 * the end of each bar, the period's numbers in each bar's hover text.
 *
 * Pure builders (`tilesHtml`, `barsHtml`, `fmtWait`) are exported so node can test them. Keys `ib.st_*`. */
(function () {
  "use strict";

  var C = null, _body = null, _data = null, _err = "";
  // The period: a quick range ({preset}) or days picked on the calendar ({from, to}), date-range.js. Remembered in this
  // browser so the tab opens on the period the owner last looked at.
  var KEY = "javis.stats.range", _range = { preset: "d7" };
  try { var saved = JSON.parse(window.localStorage.getItem(KEY) || "null"); if (saved && (saved.preset || saved.from)) _range = saved; } catch (e) { /* no storage */ }

  function t(k, v) { return window.t(k, v); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function noIcon() { return ""; }

  // Seconds to words: under a minute in seconds, under an hour in minutes, else hours with one decimal.
  function fmtWait(s) {
    if (s == null || isNaN(s)) return "-";
    if (s < 60) return t("ib.st_sec", { n: Math.round(s) });
    if (s < 3600) return t("ib.st_min", { n: Math.round(s / 60) });
    return t("ib.st_hour", { n: Math.round(s / 360) / 10 });
  }

  // Change against the period before. `lowerBetter`: a shorter wait is good news.
  function delta(now, before, lowerBetter) {
    if (before == null || now == null || !before) return { text: before === 0 && now ? t("ib.st_new") : "", good: null };
    var p = Math.round((now - before) / before * 100);
    if (!p) return { text: t("ib.st_same"), good: null };
    return { text: (p > 0 ? "+" : "") + p + "%", good: lowerBetter ? p < 0 : p > 0 };
  }

  function tilesHtml(d, icon) {
    var I = icon || noIcon, n = d.now || {}, b = d.before || {};
    var tiles = [
      ["sparkles", "ib.st_ai", String(n.ai || 0), delta(n.ai || 0, b.ai || 0, false)],
      ["hand", "ib.st_you", String(n.human || 0), delta(n.human || 0, b.human || 0, false)],
      ["alarm-clock", "ib.st_wait", fmtWait(n.wait_avg), delta(n.wait_avg, b.wait_avg, true)],
      ["inbox", "ib.st_needs", String(d.needs_you || 0), { text: "", good: null }],
    ];
    return tiles.map(function (x, i) {
      var cls = x[3].good === true ? " up" : x[3].good === false ? " down" : "";
      return '<div class="st-tile' + (i === 3 && d.needs_you ? " st-go" : "") + '"' + (i === 3 ? ' role="button" tabindex="0" data-go="you"' : "") + '>' +
        '<span class="st-k">' + I(x[0]) + ' ' + esc(t(x[1])) + '</span><span class="st-v">' + esc(x[2]) + '</span>' +
        (x[3].text ? '<span class="st-d' + cls + '">' + esc(t("ib.st_vs", { d: x[3].text })) + '</span>' : "") + '</div>';
    }).join("");
  }

  // `rows`: [{label, logo, value, title}] sorted by value. One series, one hue; the value is written at the bar's end.
  function barsHtml(title, rows, empty) {
    var max = rows.reduce(function (m, r) { return Math.max(m, r.value); }, 0);
    return '<section class="st-panel"><h3>' + esc(title) + '</h3>' + (rows.length ? rows.map(function (r) {
      var w = max ? Math.max(2, Math.round(r.value / max * 100)) : 0;
      return '<div class="st-row" title="' + esc(r.title || "") + '"><span class="st-nm">' + (r.logo || "") + '<span>' + esc(r.label) + '</span></span>' +
        '<span class="st-track"><span class="st-fill" style="width:' + w + '%"></span></span><span class="st-num">' + esc(r.value) + '</span></div>';
    }).join("") : '<p class="ib-hint">' + esc(empty) + '</p>') + '</section>';
  }

  function render(body, ctx) {
    C = ctx; _body = body;
    body.innerHTML = '<div class="ib-v5 st-wrap"><div class="st-bar"><button type="button" class="st-range" aria-haspopup="dialog" aria-label="' +
      esc(t("ib.st_period")) + '"></button><span class="st-dates"></span></div>' +
      '<div class="st-body"><div class="ht-empty">' + esc(t("common.loading")) + '</div></div></div>';
    var rb = body.querySelector(".st-range");
    rb.onclick = function () {
      if (!window.JavisDateRange) return;
      window.JavisDateRange.open(rb, _range, function (r) {
        _range = r || { preset: "d7" };
        try { window.localStorage.setItem(KEY, JSON.stringify(_range)); } catch (e) { /* no storage */ }
        load();
      });
    };
    body.addEventListener("click", function (e) { var g = e.target.closest && e.target.closest("[data-go]"); if (g) C.goWho(g.dataset.go); });
    body.addEventListener("keydown", function (e) {
      var g = e.target.closest && e.target.closest("[data-go]");
      if (g && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); C.goWho(g.dataset.go); }
    });
    load();
  }

  async function load() {
    if (!_body) return;
    var DR = window.JavisDateRange, d = DR ? DR.dates(_range) : null;
    var rb = _body.querySelector(".st-range"), sd = _body.querySelector(".st-dates");
    if (rb) rb.innerHTML = C.ic("calendar") + ' <span>' + esc(DR ? DR.label(_range) : t("ib.st_period")) + '</span> ' + C.ic("chevron-down");
    if (sd) sd.textContent = d && _range.preset ? DR.label({ from: d.from, to: d.to }) : "";
    try { _data = await C.api("/conversations/insights?" + (d ? "from=" + d.from + "&to=" + d.to : "days=7")); _err = ""; }
    catch (e) { _err = e.message; }
    paint();
  }

  function paint() {
    var box = _body && _body.querySelector(".st-body");
    if (!box) return;
    if (_err) { box.innerHTML = '<div class="ht-empty">' + esc(t("ht.loi_tai")) + ' ' + esc(_err) + '</div>'; return; }
    var d = _data || {}, n = d.now || {}, b = d.before || {};
    var ch = Object.keys(n.by_channel || {}).map(function (k) {
      var x = n.by_channel[k];
      return { label: C.channelName(k), logo: C.logo(k, "18px"), value: x.ai || 0,
               title: t("ib.st_ch_t", { ai: x.ai || 0, you: x.human || 0, kh: x.customer || 0 }) };
    }).sort(function (x, y) { return y.value - x.value; });
    var bots = Object.keys(n.by_bot || {}).map(function (k) {
      return { label: (d.bot_names || {})[k] || k, value: n.by_bot[k], title: t("ib.st_bot_t", { n: n.by_bot[k], b: (b.by_bot || {})[k] || 0 }) };
    }).sort(function (x, y) { return y.value - x.value; });
    box.innerHTML = '<div class="st-tiles">' + tilesHtml(d, C.ic) + '</div>' +
      '<div class="st-panels">' + barsHtml(t("ib.st_by_ch"), ch, t("ib.st_empty")) + barsHtml(t("ib.st_by_bot"), bots, t("ib.st_empty")) + '</div>' +
      '<p class="ib-hint">' + esc(t("ib.st_note")) + '</p>';
  }

  window.JavisInboxStats = { render: render, tilesHtml: tilesHtml, barsHtml: barsHtml, fmtWait: fmtWait, delta: delta };
})();
