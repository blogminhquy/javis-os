/* Stats tab of the Chatbot page (Chatbot v5, owner 2026-10-28; docs/dev/2026-10-chatbot-v5-spec.md section 9).
 *
 * Any period from the date range picker (date-range.js: today, last 7 / 30 / 90 days, last month, ... or days on the
 * calendar). Since 0.399.0 (owner, 2026-10-29: show what the chatbot gives the owner): a band with what the A.I. did for
 * you (answers, its share of all answers, the time it freed, answers while you rest), four tiles (customers served and
 * new ones, first-answer speed of the A.I. against yours, your own answers, chats waiting for you), customer messages
 * per hour, then two single-series bar lists: A.I. answers per channel and per bot (GET /conversations/insights).
 *
 * 0.401.0 (owner, 2026-10-29: "ở nick Javis Vũ anh không trả lời tý nào mà nó tính 45% câu do A.I. lo"): one account's
 * hand replies were lowering another account's A.I. share. An account picker keeps one account (remembered in this
 * browser), and the per-channel list became a per-account one: A.I. and hand replies side by side with the A.I. share.
 *
 * Pure builders (`tilesHtml`, `barsHtml`, `fmtWait`) are exported so node can test them. Keys `ib.st_*`. */
(function () {
  "use strict";

  var C = null, _body = null, _data = null, _err = "";
  // The period: a quick range ({preset}) or days picked on the calendar ({from, to}), date-range.js. Remembered in this
  // browser so the tab opens on the period the owner last looked at.
  var KEY = "javis.stats.range", _range = { preset: "d7" };
  try { var saved = JSON.parse(window.localStorage.getItem(KEY) || "null"); if (saved && (saved.preset || saved.from)) _range = saved; } catch (e) { /* no storage */ }
  // The account picked ("" = every account), an inbox account key "<channel>:<id>".
  var ACC_KEY = "javis.stats.account", _acc = "";
  try { _acc = window.localStorage.getItem(ACC_KEY) || ""; } catch (e) { /* no storage */ }

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
    if (before == null || now == null || !before) return { text: before === 0 && now ? t("ib.st_new") : "", good: null, fresh: before === 0 && !!now };
    var p = Math.round((now - before) / before * 100);
    if (!p) return { text: t("ib.st_same"), good: null };
    return { text: (p > 0 ? "+" : "") + p + "%", good: lowerBetter ? p < 0 : p > 0 };
  }

  // Minutes the owner did not spend typing: one minute for each answer the A.I. sent (owner, 2026-10-29). An estimate,
  // and the page says so in its note.
  var MIN_PER_ANSWER = 1;
  function savedText(ai) {
    var m = Math.max(0, Number(ai) || 0) * MIN_PER_ANSWER;
    return m < 60 ? t("ib.st_min", { n: m }) : t("ib.st_hour", { n: Math.round(m / 6) / 10 });
  }
  function fmtNum(n) { return Number(n || 0).toLocaleString("vi-VN"); }
  // "+12% vs the period before", or just "nothing the period before" (not "... vs the period before" twice).
  function vsText(dl) { return dl.fresh ? dl.text : t("ib.st_vs", { d: dl.text }); }
  // The A.I.'s share of the answers, in whole percent (0 when nobody answered).
  function shareOf(ai, human) { ai = Number(ai) || 0; human = Number(human) || 0; return ai + human ? Math.round(ai / (ai + human) * 100) : 0; }

  // The band at the top (0.399.0): what the chatbot did for the owner in the period, in three numbers.
  function heroHtml(d, icon) {
    var I = icon || noIcon, n = d.now || {}, b = d.before || {};
    var ai = Number(n.ai) || 0, human = Number(n.human) || 0;
    var share = shareOf(ai, human);
    var dl = delta(ai, Number(b.ai) || 0, false);
    var cls = dl.good === true ? " up" : dl.good === false ? " down" : "";
    return '<section class="st-hero">' +
      '<div class="st-hero-h"><span class="st-hero-ic">' + I("sparkles") + '</span><span class="st-hero-tt"><b>' +
        esc(ai ? t("ib.st_hero", { ai: fmtNum(ai) }) : t("ib.st_hero_none")) + '</b>' +
        (dl.text ? '<span class="st-d' + cls + '">' + esc(vsText(dl)) + '</span>' : "") + '</span></div>' +
      '<div class="st-hero-k">' +
        '<div><b>' + share + '%</b><span>' + esc(t("ib.st_share_l")) + '</span></div>' +
        '<div><b>' + esc(savedText(ai)) + '</b><span>' + esc(t("ib.st_saved_l")) + '</span></div>' +
        '<div><b>' + esc(fmtNum(n.ai_rest)) + '</b><span>' + esc(t("ib.st_rest_l")) + '</span></div>' +
      '</div></section>';
  }

  // Four tiles: customers served (and how many are new), how soon the first answer comes (A.I. against you), what you
  // answered yourself, and the chats waiting for you right now (opens the Needs you list).
  function tilesHtml(d, icon) {
    var I = icon || noIcon, n = d.now || {}, b = d.before || {};
    var tile = function (ic, key, value, sub, extra) {
      return '<div class="st-tile' + (extra || "") + '"><span class="st-k">' + I(ic) + ' ' + esc(t(key)) + '</span>' +
        '<span class="st-v">' + value + '</span>' + (sub || "") + '</div>';
    };
    var dYou = delta(Number(n.human) || 0, Number(b.human) || 0, false);
    var speed = '<span class="st-sp"><span class="st-sp-ai">' + esc(t("ib.st_speed_ai", { t: fmtWait(n.wait_ai) })) + '</span>' +
      '<span class="st-sp-you">' + esc(t("ib.st_speed_you", { t: fmtWait(n.wait_human) })) + '</span></span>';
    return tile("users", "ib.st_chats", esc(fmtNum(n.chats)),
        n.new_chats ? '<span class="st-d">' + esc(t("ib.st_new_chats", { n: fmtNum(n.new_chats) })) + '</span>' : "") +
      tile("zap", "ib.st_speed", speed, "", " st-speed") +
      tile("hand", "ib.st_you", esc(fmtNum(n.human)), dYou.text ? '<span class="st-d">' + esc(vsText(dYou)) + '</span>' : "") +
      '<div class="st-tile' + (d.needs_you ? " st-go" : "") + '" role="button" tabindex="0" data-go="you"><span class="st-k">' + I("inbox") + ' ' +
        esc(t("ib.st_needs")) + '</span><span class="st-v">' + esc(fmtNum(d.needs_you)) + '</span></div>';
  }

  // Customer messages per hour of the day: 24 columns, the owner's rest hours (21:00 to 07:00) in the A.I.'s colour, the
  // busiest hour named above the chart.
  function hoursHtml(hours) {
    var h = (hours && hours.length === 24) ? hours : [];
    var max = h.reduce(function (m, v) { return Math.max(m, v || 0); }, 0);
    if (!max) return '<section class="st-panel st-hours"><h3>' + esc(t("ib.st_hours")) + '</h3><p class="ib-hint">' + esc(t("ib.st_empty")) + '</p></section>';
    var peak = h.indexOf(max);
    return '<section class="st-panel st-hours"><h3>' + esc(t("ib.st_hours")) + '<small>' + esc(t("ib.st_peak", { a: peak, b: (peak + 1) % 24 })) +
      '</small></h3><div class="st-cols" role="img" aria-label="' + esc(t("ib.st_hours")) + '">' + h.map(function (v, i) {
        var rest = i >= 21 || i < 7;
        return '<span class="st-col' + (rest ? " rest" : "") + (i === peak ? " peak" : "") + '" title="' + esc(t("ib.st_hour_t", { h: i, n: v || 0 })) +
          '"><span style="height:' + (v ? Math.max(4, Math.round(v / max * 100)) : 0) + '%"></span></span>';
      }).join("") + '</div><div class="st-cols-x" aria-hidden="true"><span>0h</span><span>6h</span><span>12h</span><span>18h</span><span>23h</span></div>' +
      '<p class="st-legend"><span class="st-lg rest"></span>' + esc(t("ib.st_rest_lg")) + '</p></section>';
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

  // Per account: A.I. and hand replies as one bar in two colours, the A.I. share at the end. `rows`: [{label, logo, ai,
  // human, title}], most answers first.
  function accountsHtml(rows) {
    var max = rows.reduce(function (m, r) { return Math.max(m, (r.ai || 0) + (r.human || 0)); }, 0);
    return '<section class="st-panel st-accs"><h3>' + esc(t("ib.st_by_acc")) + '</h3>' + (rows.length ? rows.map(function (r) {
      var ai = r.ai || 0, hu = r.human || 0;
      var wa = max ? Math.round(ai / max * 100) : 0, wh = max ? Math.round(hu / max * 100) : 0;
      return '<div class="st-acc" title="' + esc(r.title || "") + '"><div class="st-acc-h"><span class="st-nm">' + (r.logo || "") + '<span>' + esc(r.label) +
        '</span></span><b>' + shareOf(ai, hu) + '%</b></div><span class="st-track st-split"><span class="st-fill" style="width:' + wa + '%"></span>' +
        '<span class="st-fill hu" style="width:' + wh + '%"></span></span><span class="st-acc-n">' +
        esc(t("ib.st_acc_n", { ai: fmtNum(ai), you: fmtNum(hu) })) + '</span></div>';
    }).join("") + '<p class="st-legend"><span class="st-lg"></span>' + esc(t("ib.st_lg_ai")) + '<span class="st-lg hu"></span>' + esc(t("ib.st_lg_hand")) + '</p>'
      : '<p class="ib-hint">' + esc(t("ib.st_empty")) + '</p>') + '</section>';
  }

  // The account picker: every account the inbox knows, "every account" first.
  function accountPickerHtml(accounts, cur) {
    if (!accounts || accounts.length < 2) return "";
    return '<option value="">' + esc(t("ib.st_acc_all")) + '</option>' + accounts.map(function (a) {
      return '<option value="' + esc(a.id) + '"' + (a.id === cur ? " selected" : "") + '>' + esc(a.name || a.id) + '</option>';
    }).join("");
  }

  function render(body, ctx) {
    C = ctx; _body = body;
    body.innerHTML = '<div class="ib-v5 st-wrap"><div class="st-bar"><button type="button" class="st-range" aria-haspopup="dialog" aria-label="' +
      esc(t("ib.st_period")) + '"></button><select class="st-accsel" aria-label="' + esc(t("ib.st_acc_pick")) + '" hidden></select>' +
      '<span class="st-dates"></span></div>' +
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
    var sel = body.querySelector(".st-accsel");
    sel.onchange = function () {
      _acc = sel.value || "";
      try { window.localStorage.setItem(ACC_KEY, _acc); } catch (e) { /* no storage */ }
      load();
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
    try {
      _data = await C.api("/conversations/insights?" + (d ? "from=" + d.from + "&to=" + d.to : "days=7") +
        (_acc ? "&account=" + encodeURIComponent(_acc) : ""));
      _err = "";
      // An account that is gone falls back to every account (the server already did).
      if (_acc && _data && _data.account !== _acc) { _acc = ""; try { window.localStorage.removeItem(ACC_KEY); } catch (e) { /* no storage */ } }
      var sel = _body.querySelector(".st-accsel");
      if (sel) { sel.innerHTML = accountPickerHtml(_data.accounts, _acc); sel.hidden = !sel.innerHTML; }
    }
    catch (e) { _err = e.message; }
    paint();
  }

  function paint() {
    var box = _body && _body.querySelector(".st-body");
    if (!box) return;
    if (_err) { box.innerHTML = '<div class="ht-empty">' + esc(t("ht.loi_tai")) + ' ' + esc(_err) + '</div>'; return; }
    var d = _data || {}, n = d.now || {}, b = d.before || {};
    var names = {};
    (d.accounts || []).forEach(function (a) { names[a.id] = a; });
    var accs = Object.keys(n.by_account || {}).map(function (k) {
      var x = n.by_account[k], a = names[k] || {}, ch = a.channel || k.split(":")[0];
      return { label: a.name || k, logo: C.logo(ch, "18px"), ai: x.ai || 0, human: x.human || 0,
               title: t("ib.st_ch_t", { ai: x.ai || 0, you: x.human || 0, kh: x.customer || 0 }) };
    }).filter(function (r) { return r.ai || r.human; }).sort(function (x, y) { return (y.ai + y.human) - (x.ai + x.human); });
    var bots = Object.keys(n.by_bot || {}).map(function (k) {
      return { label: (d.bot_names || {})[k] || k, value: n.by_bot[k], title: t("ib.st_bot_t", { n: n.by_bot[k], b: (b.by_bot || {})[k] || 0 }) };
    }).sort(function (x, y) { return y.value - x.value; });
    box.innerHTML = heroHtml(d, C.ic) + '<div class="st-tiles">' + tilesHtml(d, C.ic) + '</div>' + hoursHtml(n.hours) +
      '<div class="st-panels">' + accountsHtml(accs) + barsHtml(t("ib.st_by_bot"), bots, t("ib.st_empty")) + '</div>' +
      '<p class="ib-hint">' + esc(t("ib.st_note")) + ' ' + esc(t("ib.st_est")) + '</p>';
  }

  window.JavisInboxStats = { render: render, heroHtml: heroHtml, tilesHtml: tilesHtml, hoursHtml: hoursHtml, barsHtml: barsHtml, fmtWait: fmtWait,
    delta: delta, savedText: savedText, accountsHtml: accountsHtml, accountPickerHtml: accountPickerHtml, shareOf: shareOf, vsText: vsText };
})();
