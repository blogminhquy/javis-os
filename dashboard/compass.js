/* Investment compass page: when to tilt toward Vietnam real estate, Vietnam stocks, world stocks, crypto, gold,
 * savings or US dollars, read from the world and Vietnam macro picture, sentiment and commodities.
 *
 * Two layers:
 *  - a curated, sourced data file (dashboard/compass/data.json): the cycle position, one stance per asset class with
 *    its reasons, entry and exit signals, the factors that move each asset (a factor x asset impact grid), sentiment,
 *    commodities, allocations by risk profile, an event calendar, if-then rules and past cycles. Every text is {vi, en}.
 *  - live numbers from the Markets page (/market/overview): VN-Index, S&P 500, gold, oil, the dollar, the US 10-year
 *    yield, VIX, USD/VND, Bitcoin and the crypto Fear & Greed index. A signal in the data file may carry
 *    `live: {ref, op, value}`; the page checks it against those numbers, so "enter when" lists show what is true today.
 *
 * Owner rules kept here: no repeated page title, long explanations behind the (i) button, nothing under 16px except
 * chart ticks, no long dashes. Render helpers are pure (tested under node); `mount` loads data and wires the clicks.
 */
(function () {
  "use strict";

  // The server serves the approved monthly update when there is one, else the bundled file (compass_store.py).
  var DATA_URL = "/compass/data";
  var STATIC_URL = "/static/compass/data.json?v=1";
  // Monthly refresh: the 8th at 09:00, after Vietnam's statistics office (around the 6th) and US CPI week.
  var UPD_CRON = "0 9 8 * *";
  var UPD_MARK = "javis_compass_draft";
  var LIVE_URL = "/market/overview";
  var TABS = ["overview", "assets", "drivers", "alloc", "playbook"];
  var TAB_ICON = { overview: "compass", assets: "layers", drivers: "activity", alloc: "chart-pie", playbook: "calendar" };
  // Colour follows the asset, never its rank: the validated categorical order, one fixed slot per asset class.
  var ASSET_SLOT = { re_vn: 1, stocks_vn: 2, stocks_world: 3, gold: 4, crypto: 5, savings: 6, usd: 7 };
  var STALE_DAYS = 45;
  // Whole keys, never built from pieces, so the i18n check can find each one.
  var TAB_KEY = { overview: "cp.tab.overview", assets: "cp.tab.assets", drivers: "cp.tab.drivers", alloc: "cp.tab.alloc", playbook: "cp.tab.playbook" };
  var STANCE_KEY = { acc: "cp.stance.acc", hold: "cp.stance.hold", red: "cp.stance.red" };
  var REGIME_KEY = { risk_on: "cp.regime.risk_on", risk_off: "cp.regime.risk_off", neutral: "cp.regime.neutral", unknown: "cp.regime.unknown" };
  var SCOPE_KEY = { all: "cp.scope.all", world: "cp.scope.world", vn: "cp.scope.vn" };
  var ZONE_KEY = { fear: "cp.zone.fear", greed: "cp.zone.greed", neutral: "cp.zone.neutral" };

  function tw(key, vars) {
    var s = (typeof window !== "undefined" && window.t) ? window.t(key, vars) : key;
    if (vars) {
      s = String(s).replace(/\{(\w+)\}/g, function (m, name) {
        return Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : m;
      });
    }
    return s;
  }
  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var ic = function (n) { return (typeof window !== "undefined" && window.ic) ? window.ic(n) : ""; };
  function infoPair(html, label) {
    var J = typeof window !== "undefined" && window.JavisInfo;
    return J ? J.pair(html, label || tw("info.more")) : '<div class="info-body">' + html + "</div>";
  }
  function lang() {
    try { return (window.JavisI18n && window.JavisI18n.lang()) || "vi"; } catch (e) { return "vi"; }
  }
  function locale() {
    try { return (window.JavisI18n && window.JavisI18n.locale()) || "vi-VN"; } catch (e) { return "vi-VN"; }
  }
  // A text field is {vi, en}; Vietnamese is the source, so any other language falls back to English, then Vietnamese.
  function pick(v, lg) {
    if (v == null) return "";
    if (typeof v !== "object") return String(v);
    lg = lg || lang();
    return v[lg] || (lg !== "vi" ? v.en : "") || v.vi || v.en || "";
  }
  function fmtNum(n, digits) {
    if (n == null || !isFinite(n)) return "-";
    try { return Number(n).toLocaleString(locale(), { maximumFractionDigits: digits == null ? 1 : digits }); }
    catch (e) { return String(Math.round(n * 10) / 10); }
  }
  function fmtPct(p, digits) {
    if (p == null || !isFinite(p)) return "-";
    return (p > 0 ? "+" : "") + fmtNum(p, digits == null ? 1 : digits) + "%";
  }

  // ---------- live numbers ----------

  /** Reads one live value from the /market/overview payload.
   *  ref: "vn:idx:VNINDEX:chg_5d", "world:key:GC=F:price", "crypto:key:BTC:trend", "crypto:fng:value",
   *  "world:regime:vix", "vn:regime:label". Returns null when the number is missing. */
  function liveGet(ov, ref) {
    if (!ov || !ov.sections || !ref) return null;
    var p = String(ref).split(":");
    var sec = ov.sections[p[0]];
    if (!sec || sec.error) return null;
    var kind = p[1];
    if (kind === "regime" || kind === "fng" || kind === "global") {
      var o = sec[kind];
      if (!o) return null;
      return p[2] ? (o[p[2]] == null ? null : o[p[2]]) : o;
    }
    var list = kind === "idx" ? sec.indices : sec.key;
    if (!list) return null;
    var want = String(p[2] || "").toUpperCase();
    var row = list.filter(function (r) {
      return String(r.symbol || "").toUpperCase() === want || String(r.id || "").toUpperCase() === want;
    })[0];
    if (!row) return null;
    return p[3] ? (row[p[3]] == null ? null : row[p[3]]) : row;
  }
  /** true / false when the live number is there, null when it is not (the page then shows "no live data"). */
  function evalCond(ov, cond) {
    if (!cond || !cond.ref) return null;
    var v = liveGet(ov, cond.ref);
    if (v == null) return null;
    var w = cond.value;
    switch (cond.op) {
      case "<": return +v < +w;
      case "<=": return +v <= +w;
      case ">": return +v > +w;
      case ">=": return +v >= +w;
      case "==": return String(v) === String(w);
      case "!=": return String(v) !== String(w);
      case "in": return (w || []).map(String).indexOf(String(v)) >= 0;
      default: return null;
    }
  }
  function signalTally(ov, list) {
    var met = 0, known = 0;
    (list || []).forEach(function (s) {
      var r = evalCond(ov, s.live);
      if (r === null) return;
      known++;
      if (r) met++;
    });
    return { met: met, known: known, total: (list || []).length };
  }

  // ---------- small pieces ----------

  function card(title, inner, extraCls) {
    return '<section class="cp-card' + (extraCls ? " " + extraCls : "") + '"><h3 class="cp-h">' + title + "</h3>" + inner + "</section>";
  }
  function bullets(list, lg) {
    if (!list || !list.length) return "";
    return '<ul class="cp-ul">' + list.map(function (b) { return "<li>" + esc(pick(b, lg)) + "</li>"; }).join("") + "</ul>";
  }
  function trendIcon(tr) {
    if (tr === "up") return '<span class="cp-tr up">' + ic("trending-up") + "</span>";
    if (tr === "down") return '<span class="cp-tr down">' + ic("trending-down") + "</span>";
    return '<span class="cp-tr flat">' + ic("minus") + "</span>";
  }
  function sw(id) { return '<i class="cp-sw cp-a' + (ASSET_SLOT[id] || 1) + '"></i>'; }
  function stanceChip(st) {
    var k = st === "accumulate" ? "acc" : st === "reduce" ? "red" : "hold";
    var icn = k === "acc" ? "arrow-up" : k === "red" ? "arrow-down" : "minus";
    return '<span class="cp-stance cp-st-' + k + '">' + ic(icn) + esc(tw(STANCE_KEY[k])) + "</span>";
  }
  /** Score -2..+2 as five cells, the filled side and count carry the sign so it never rests on colour alone. */
  function scoreBar(n) {
    n = Math.max(-2, Math.min(2, Math.round(+n || 0)));
    var cells = "";
    for (var i = -2; i <= 2; i++) {
      var on = (n > 0 && i > 0 && i <= n) || (n < 0 && i < 0 && i >= n) || (i === 0);
      cells += '<i class="' + (i === 0 ? "mid" : on ? (i > 0 ? "pos" : "neg") : "") + '"></i>';
    }
    return '<span class="cp-score" title="' + (n > 0 ? "+" : "") + n + '" aria-label="' + (n > 0 ? "+" : "") + n + '">' + cells
      + '<b>' + (n > 0 ? "+" : "") + n + "</b></span>";
  }
  function assetById(data, id) { return (data.assets || []).filter(function (a) { return a.id === id; })[0]; }
  function assetName(data, id, lg) { var a = assetById(data, id); return a ? pick(a.short || a.name, lg) : id; }
  function daysSince(iso, now) {
    var t = Date.parse(iso || "");
    if (!isFinite(t)) return null;
    return Math.floor(((now || Date.now()) - t) / 86400000);
  }

  // ---------- live pulse ----------

  function pulseTile(p, ov, lg) {
    var name = esc(pick(p.name, lg));
    var val = "-", sub = "", tr = null;
    if (p.kind === "fng") {
      var f = liveGet(ov, p.ref);
      if (f && f.value != null) {
        val = fmtNum(f.value, 0);
        sub = esc(f.label || "") + (f.month_ago != null ? ' <span class="cp-muted">' + esc(tw("cp.pulse_month_ago", { v: f.month_ago })) + "</span>" : "");
      }
    } else if (p.kind === "regime") {
      var g = liveGet(ov, p.ref);
      if (g && g.label) {
        val = esc(tw(REGIME_KEY[g.label] || "cp.regime.unknown"));
        if (g.vix != null) sub = "VIX " + esc(fmtNum(g.vix, 1));
        else if (g.breadth50 != null) sub = esc(tw("cp.pulse_breadth", { v: fmtNum(g.breadth50, 0) }));
      }
    } else {
      var r = liveGet(ov, p.ref);
      if (r && r.price != null) {
        val = (p.prefix || "") + fmtNum(r.price, p.digits == null ? 2 : p.digits) + (p.suffix || "");
        tr = r.trend || null;
        var c5 = r.chg_5d, c1 = r.chg_1d;
        sub = (c1 != null ? '<span class="cp-chg ' + (c1 >= 0 ? "up" : "down") + '">' + esc(fmtPct(c1, 2)) + "</span> " : "")
          + (c5 != null ? '<span class="cp-muted">' + esc(tw("cp.pulse_5d", { v: fmtPct(c5, 1) })) + "</span>" : "");
      }
    }
    return '<div class="cp-pulse-t"><div class="cp-pulse-l">' + name + (tr ? trendIcon(tr) : "") + "</div>"
      + '<div class="cp-pulse-v">' + (val === "-" ? '<span class="cp-muted">-</span>' : val) + "</div>"
      + '<div class="cp-pulse-s">' + sub + "</div></div>";
  }
  function pulseHtml(data, st, lg) {
    var list = data.pulse || [];
    if (!list.length) return "";
    var state = st.live === null ? '<span class="cp-muted">' + esc(tw("common.loading")) + "</span>"
      : st.live === false ? '<span class="cp-chip cp-chip-warn">' + ic("triangle-alert") + esc(tw("cp.live_off")) + "</span>"
      : '<span class="cp-chip cp-chip-live"><i class="cp-dot"></i>' + esc(tw("cp.live_on")) + "</span>";
    var ov = st.live || null;
    return card(ic("activity") + esc(tw("cp.pulse_title")) + state + infoPair(esc(tw("cp.pulse_info"))),
      '<div class="cp-pulse">' + list.map(function (p) { return pulseTile(p, ov, lg); }).join("") + "</div>", "cp-card-pulse");
  }

  // ---------- investment clock (inline SVG) ----------

  // Quadrants: x = growth (left slowing, right picking up), y = inflation (down falling, up rising).
  var QUAD = { reflation: [-1, -1], recovery: [1, -1], overheat: [1, 1], stagflation: [-1, 1] };
  function clockSvg(clock, lg, size) {
    var S = size || 320, c = S / 2, r = S / 2 - 30;
    var X = function (v) { return c + Math.max(-1, Math.min(1, +v || 0)) * r; };
    var Y = function (v) { return c - Math.max(-1, Math.min(1, +v || 0)) * r; };
    var out = ['<svg class="cp-clock-svg" viewBox="0 0 ' + S + " " + S + '" width="' + S + '" height="' + S + '" role="img" aria-label="' + esc(tw("cp.clock_aria")) + '">'];
    var phases = clock.phases || [];
    var active = {};
    (clock.markers || []).forEach(function (m) { active[m.phase] = true; });
    phases.forEach(function (ph) {
      var q = QUAD[ph.key];
      if (!q) return;
      var x = q[0] > 0 ? c + 1 : c - r, y = q[1] > 0 ? c - r : c + 1;
      out.push('<rect class="cp-q' + (active[ph.key] ? " on" : "") + '" x="' + x + '" y="' + y + '" width="' + (r - 1) + '" height="' + (r - 1) + '" rx="10"/>');
      var tx = c + q[0] * r * 0.5, ty = c - q[1] * r * 0.5;
      out.push('<text class="cp-q-name" x="' + tx.toFixed(1) + '" y="' + (ty - 8).toFixed(1) + '" text-anchor="middle">' + esc(pick(ph.name, lg)) + "</text>");
      out.push('<text class="cp-q-lead" x="' + tx.toFixed(1) + '" y="' + (ty + 12).toFixed(1) + '" text-anchor="middle">' + esc(pick(ph.lead, lg)) + "</text>");
    });
    out.push('<line class="cp-axis" x1="' + (c - r) + '" x2="' + (c + r) + '" y1="' + c + '" y2="' + c + '"/>');
    out.push('<line class="cp-axis" x1="' + c + '" x2="' + c + '" y1="' + (c - r) + '" y2="' + (c + r) + '"/>');
    out.push('<text class="cp-tick" x="' + (c + r) + '" y="' + (c + r + 20) + '" text-anchor="end">' + esc(tw("cp.clock_growth_up")) + "</text>");
    out.push('<text class="cp-tick" x="' + (c - r) + '" y="' + (c + r + 20) + '" text-anchor="start">' + esc(tw("cp.clock_growth_down")) + "</text>");
    out.push('<text class="cp-tick" x="' + (c - r) + '" y="' + (c - r - 10) + '" text-anchor="start">' + esc(tw("cp.clock_infl_up")) + "</text>");
    (clock.markers || []).forEach(function (m, i) {
      var mx = X(m.x), my = Y(m.y);
      out.push('<g class="cp-mk cp-mk' + (i + 1) + '"><circle cx="' + mx.toFixed(1) + '" cy="' + my.toFixed(1) + '" r="9"/>'
        + '<text x="' + mx.toFixed(1) + '" y="' + (my + 5).toFixed(1) + '" text-anchor="middle">' + esc(m.badge || String(i + 1)) + "</text></g>");
    });
    out.push("</svg>");
    return out.join("");
  }
  function clockHtml(data, lg) {
    var cl = data.clock;
    if (!cl) return "";
    var legend = (cl.markers || []).map(function (m, i) {
      var ph = (cl.phases || []).filter(function (p) { return p.key === m.phase; })[0];
      return '<div class="cp-mk-row"><span class="cp-mk-b cp-mk' + (i + 1) + '">' + esc(m.badge || String(i + 1)) + "</span><div><b>" + esc(pick(m.name, lg)) + "</b>"
        + (ph ? ' <span class="cp-chip">' + esc(pick(ph.name, lg)) + "</span>" : "") + '<p class="cp-p">' + esc(pick(m.note, lg)) + "</p></div></div>";
    }).join("");
    return card(ic("compass") + esc(tw("cp.clock_title")) + infoPair(esc(pick(cl.info, lg)) || esc(tw("cp.clock_info"))),
      '<div class="cp-clock"><div class="cp-clock-fig">' + clockSvg(cl, lg) + '</div><div class="cp-clock-leg">' + legend + "</div></div>");
  }

  // ---------- overview ----------

  function assetCard(a, ov, lg) {
    var t = signalTally(ov, a.enter_when);
    var x = signalTally(ov, a.exit_when);
    var live = (t.known || x.known)
      ? '<div class="cp-ac-live">' + (t.known ? '<span class="cp-chip">' + ic("log-in") + esc(tw("cp.sig_enter_n", { m: t.met, k: t.known })) + "</span>" : "")
        + (x.known ? '<span class="cp-chip">' + ic("log-out") + esc(tw("cp.sig_exit_n", { m: x.met, k: x.known })) + "</span>" : "") + "</div>"
      : "";
    return '<button type="button" class="cp-ac" data-asset="' + esc(a.id) + '"><div class="cp-ac-h">' + sw(a.id) + "<b>" + esc(pick(a.name, lg)) + "</b>"
      + '<span class="cp-sp"></span>' + stanceChip(a.stance) + "</div>"
      + '<div class="cp-ac-m">' + scoreBar(a.score) + (a.horizon ? '<span class="cp-muted">' + esc(pick(a.horizon, lg)) + "</span>" : "") + "</div>"
      + '<p class="cp-p">' + esc(pick(a.one_liner, lg)) + "</p>" + live + "</button>";
  }
  function overviewHtml(data, st, lg) {
    var h = "";
    h += '<div class="cp-hero"><div class="cp-hero-t">' + esc(pick(data.verdict, lg)) + "</div>"
      + '<p class="cp-p">' + esc(pick(data.summary, lg)) + "</p>"
      + ((data.actions || []).length ? '<ol class="cp-actions">' + data.actions.map(function (x) { return "<li>" + esc(pick(x, lg)) + "</li>"; }).join("") + "</ol>" : "")
      + "</div>";
    h += pulseHtml(data, st, lg);
    var ov = st.live || null;
    h += card(ic("layers") + esc(tw("cp.scorecard_title", { n: (data.assets || []).length })),
      '<div class="cp-acs">' + (data.assets || []).map(function (a) { return assetCard(a, ov, lg); }).join("") + "</div>");
    h += clockHtml(data, lg);
    return h;
  }

  // ---------- one asset ----------

  function signalList(list, ov, lg) {
    if (!list || !list.length) return "";
    return '<ul class="cp-sigs">' + list.map(function (s) {
      var r = evalCond(ov, s.live);
      var badge = r === true ? '<span class="cp-sig on">' + ic("check") + esc(tw("cp.sig_on")) + "</span>"
        : r === false ? '<span class="cp-sig off">' + ic("x") + esc(tw("cp.sig_off")) + "</span>"
        : s.live ? '<span class="cp-sig na">' + esc(tw("cp.sig_na")) + "</span>"
        : '<span class="cp-sig manual">' + ic("eye") + esc(tw("cp.sig_watch")) + "</span>";
      return "<li>" + badge + '<span class="cp-sig-t">' + esc(pick(s.text, lg)) + "</span></li>";
    }).join("") + "</ul>";
  }
  function assetPicker(data, st, lg) {
    return '<div class="cp-row-tools">' + (data.assets || []).map(function (a) {
      return '<button type="button" class="cp-chipb' + (a.id === st.asset ? " on" : "") + '" data-asset="' + esc(a.id) + '">' + sw(a.id) + esc(pick(a.short || a.name, lg)) + "</button>";
    }).join("") + "</div>";
  }
  function assetHtml(data, st, lg) {
    var a = assetById(data, st.asset) || (data.assets || [])[0];
    if (!a) return "";
    var ov = st.live || null;
    var h = assetPicker(data, { asset: a.id }, lg);
    h += '<div class="cp-hero"><div class="cp-asset-h">' + sw(a.id) + '<span class="cp-hero-t">' + esc(pick(a.name, lg)) + "</span>" + stanceChip(a.stance) + scoreBar(a.score)
      + (a.horizon ? '<span class="cp-chip">' + ic("clock") + esc(pick(a.horizon, lg)) + "</span>" : "") + "</div>"
      + '<p class="cp-p">' + esc(pick(a.verdict || a.one_liner, lg)) + "</p></div>";
    if (a.live_ref) {
      var row = liveGet(ov, a.live_ref);
      if (row && row.price != null) {
        h += '<div class="cp-live-line">' + ic("activity") + "<span>" + esc(tw("cp.asset_live", { name: row.name || row.symbol || "", p: fmtNum(row.price, 2) })) + "</span>"
          + (row.chg_5d != null ? '<span class="cp-chg ' + (row.chg_5d >= 0 ? "up" : "down") + '">' + esc(tw("cp.pulse_5d", { v: fmtPct(row.chg_5d, 1) })) + "</span>" : "")
          + (row.trend ? trendIcon(row.trend) : "") + "</div>";
      }
    }
    h += '<div class="cp-2col">'
      + card(ic("log-in") + esc(tw("cp.enter_title")), signalList(a.enter_when, ov, lg))
      + card(ic("log-out") + esc(tw("cp.exit_title")), signalList(a.exit_when, ov, lg)) + "</div>";
    h += card(ic("lightbulb") + esc(tw("cp.thesis_title")), bullets(a.thesis, lg));
    h += '<div class="cp-2col">'
      + card(ic("trending-up") + esc(tw("cp.bull_title")), bullets(a.bull, lg))
      + card(ic("trending-down") + esc(tw("cp.bear_title")), bullets(a.bear, lg)) + "</div>";
    if ((a.how || []).length) h += card(ic("wallet") + esc(tw("cp.how_title")), bullets(a.how, lg));
    // Factors that move this asset the most, strongest first.
    var fs = (data.factors || []).filter(function (f) { return f.impact && f.impact[a.id]; })
      .sort(function (x, y) { return Math.abs(y.impact[a.id]) - Math.abs(x.impact[a.id]); }).slice(0, 6);
    if (fs.length) {
      h += card(ic("activity") + esc(tw("cp.asset_factors")), '<div class="cp-fl">' + fs.map(function (f) {
        return '<div class="cp-fl-r">' + scoreBar(f.impact[a.id]) + "<div><b>" + esc(pick(f.name, lg)) + "</b> " + trendIcon(f.trend)
          + '<span class="cp-muted"> ' + esc(pick(f.reading, lg)) + "</span></div></div>";
      }).join("") + "</div>");
    }
    return h;
  }

  // ---------- drivers ----------

  function impactCell(v, why) {
    v = Math.max(-2, Math.min(2, Math.round(+v || 0)));
    var cls = v === 0 ? "z" : (v > 0 ? "p" : "n") + Math.abs(v);
    var txt = v === 0 ? "0" : (v > 0 ? "+" : "-") + Math.abs(v);
    return '<td class="cp-im cp-im-' + cls + '"' + (why ? ' title="' + esc(why) + '"' : "") + ">" + txt + "</td>";
  }
  function factorGrid(data, st, lg) {
    var assets = data.assets || [];
    var scope = st.scope || "all";
    var list = (data.factors || []).filter(function (f) { return scope === "all" || f.scope === scope; });
    var head = "<tr><th>" + esc(tw("cp.col_factor")) + "</th><th>" + esc(tw("cp.col_now")) + "</th>" + assets.map(function (a) {
      return '<th class="cp-im-h" title="' + esc(pick(a.name, lg)) + '">' + sw(a.id) + "<span>" + esc(pick(a.short || a.name, lg)) + "</span></th>";
    }).join("") + "</tr>";
    var rows = list.map(function (f) {
      return '<tr><th class="cp-f-n"><b>' + esc(pick(f.name, lg)) + '</b><span class="cp-chip cp-chip-s">' + esc(tw(SCOPE_KEY[f.scope] || "cp.scope.all")) + "</span></th>"
        + '<td class="cp-f-r">' + trendIcon(f.trend) + "<span>" + esc(pick(f.reading, lg)) + "</span></td>"
        + assets.map(function (a) { return impactCell((f.impact || {})[a.id], pick(f.why, lg)); }).join("") + "</tr>";
    }).join("");
    var scopes = [["all", "cp.scope.all"], ["world", "cp.scope.world"], ["vn", "cp.scope.vn"]];
    var tools = '<div class="cp-row-tools">' + scopes.map(function (s) {
      return '<button type="button" class="cp-chipb' + (scope === s[0] ? " on" : "") + '" data-scope="' + s[0] + '">' + esc(tw(s[1])) + "</button>";
    }).join("") + '<span class="cp-sp"></span><span class="cp-im-key"><span class="cp-im cp-im-p2">+2</span>' + esc(tw("cp.im_good"))
      + '<span class="cp-im cp-im-z">0</span><span class="cp-im cp-im-n2">-2</span>' + esc(tw("cp.im_bad")) + "</span></div>";
    return card(ic("activity") + esc(tw("cp.grid_title", { n: list.length })) + infoPair(esc(tw("cp.grid_info"))),
      tools + '<div class="cp-tbl-wrap"><table class="cp-tbl cp-grid"><thead>' + head + "</thead><tbody>" + rows + "</tbody></table></div>");
  }
  function factorNotes(data, st, lg) {
    var scope = st.scope || "all";
    var list = (data.factors || []).filter(function (f) { return (scope === "all" || f.scope === scope) && f.why; });
    if (!list.length) return "";
    return card(ic("lightbulb") + esc(tw("cp.why_title")), '<div class="cp-notes">' + list.map(function (f) {
      return '<div class="cp-note"><div class="cp-note-h"><b>' + esc(pick(f.name, lg)) + "</b>" + (f.as_of ? '<span class="cp-chip">' + esc(f.as_of) + "</span>" : "") + "</div>"
        + '<p class="cp-p">' + esc(pick(f.why, lg)) + "</p>" + (f.source ? '<div class="cp-src">' + esc(f.source) + "</div>" : "") + "</div>";
    }).join("") + "</div>");
  }
  function zoneChip(z) {
    var k = z === "fear" ? "fear" : z === "greed" ? "greed" : "neutral";
    return '<span class="cp-zone cp-z-' + k + '">' + esc(tw(ZONE_KEY[k])) + "</span>";
  }
  function sentimentHtml(data, st, lg) {
    var list = data.sentiment || [];
    if (!list.length) return "";
    var ov = st.live || null;
    return card(ic("brain") + esc(tw("cp.sent_title")) + infoPair(esc(tw("cp.sent_info"))), '<div class="cp-notes">' + list.map(function (s) {
      var reading = pick(s.reading, lg);
      var zone = s.zone;
      if (s.live_ref) {
        var v = liveGet(ov, s.live_ref);
        if (v != null && typeof v !== "object") {
          reading = tw("cp.sent_live", { v: fmtNum(v, 1) });
          // `zones: [low, high]`; `invert` for gauges where a high reading means fear (VIX).
          if (s.zones) {
            var lo = v <= s.zones[0], hi = v >= s.zones[1];
            zone = lo ? (s.invert ? "greed" : "fear") : hi ? (s.invert ? "fear" : "greed") : "neutral";
          }
        }
      }
      return '<div class="cp-note"><div class="cp-note-h"><b>' + esc(pick(s.name, lg)) + "</b>" + zoneChip(zone) + "</div>"
        + '<div class="cp-note-v">' + esc(reading) + "</div><p class=\"cp-p\">" + esc(pick(s.text, lg)) + "</p></div>";
    }).join("") + "</div>");
  }
  function commodityHtml(data, st, lg) {
    var list = data.commodities || [];
    if (!list.length) return "";
    var ov = st.live || null;
    return card(ic("package") + esc(tw("cp.comm_title")), '<div class="cp-notes">' + list.map(function (c) {
      var row = c.live_ref ? liveGet(ov, c.live_ref) : null;
      var reading = row && row.price != null ? (c.prefix || "") + fmtNum(row.price, c.digits == null ? 2 : c.digits) + (c.suffix || "") : pick(c.reading, lg);
      var tr = row && row.trend ? row.trend : c.trend;
      return '<div class="cp-note"><div class="cp-note-h"><b>' + esc(pick(c.name, lg)) + "</b>" + trendIcon(tr)
        + (row && row.chg_5d != null ? '<span class="cp-chg ' + (row.chg_5d >= 0 ? "up" : "down") + '">' + esc(tw("cp.pulse_5d", { v: fmtPct(row.chg_5d, 1) })) + "</span>" : "") + "</div>"
        + '<div class="cp-note-v">' + esc(reading) + "</div><p class=\"cp-p\">" + esc(pick(c.impact, lg)) + "</p></div>";
    }).join("") + "</div>");
  }
  function driversHtml(data, st, lg) {
    return factorGrid(data, st, lg) + '<div class="cp-2col">' + sentimentHtml(data, st, lg) + commodityHtml(data, st, lg) + "</div>" + factorNotes(data, st, lg);
  }

  // ---------- allocation ----------

  /** Rounds a {asset: pct} map to whole percents that add up to exactly 100 (largest remainder). */
  function normAlloc(alloc, order) {
    var keys = (order || Object.keys(alloc || {})).filter(function (k) { return (alloc || {})[k] > 0; });
    var sum = keys.reduce(function (s, k) { return s + (+alloc[k] || 0); }, 0);
    if (!(sum > 0)) return [];
    var parts = keys.map(function (k) { var raw = alloc[k] / sum * 100; return { id: k, pct: Math.floor(raw), rem: raw - Math.floor(raw) }; });
    var left = 100 - parts.reduce(function (s, p) { return s + p.pct; }, 0);
    parts.slice().sort(function (a, b) { return b.rem - a.rem; }).slice(0, left).forEach(function (p) { p.pct++; });
    return parts.map(function (p) { return { id: p.id, pct: p.pct }; });
  }
  function allocBar(parts, data, lg) {
    return '<div class="cp-bar" role="img" aria-label="' + esc(parts.map(function (p) { return assetName(data, p.id, lg) + " " + p.pct + "%"; }).join(", ")) + '">'
      + parts.map(function (p) {
        return '<span class="cp-bar-s cp-a' + (ASSET_SLOT[p.id] || 1) + '" style="flex-grow:' + p.pct + '" title="' + esc(assetName(data, p.id, lg) + ": " + p.pct + "%") + '">'
          + (p.pct >= 8 ? "<b>" + p.pct + "%</b>" : "") + "</span>";
      }).join("") + "</div>";
  }
  function allocHtml(data, st, lg) {
    var profs = data.profiles || [];
    var pr = profs.filter(function (p) { return p.id === st.profile; })[0] || profs[0];
    if (!pr) return "";
    var order = (data.assets || []).map(function (a) { return a.id; });
    var now = normAlloc(pr.now, order), base = normAlloc(pr.neutral, order);
    var baseOf = {}; base.forEach(function (p) { baseOf[p.id] = p.pct; });
    var nowOf = {}; now.forEach(function (p) { nowOf[p.id] = p.pct; });
    var cap = +st.capital > 0 ? +st.capital : 0;
    var h = '<div class="cp-row-tools">' + profs.map(function (p) {
      return '<button type="button" class="cp-segb2' + (p.id === pr.id ? " on" : "") + '" data-profile="' + esc(p.id) + '">' + esc(pick(p.name, lg)) + "</button>";
    }).join("") + "</div>";
    h += '<div class="cp-hero"><p class="cp-p">' + esc(pick(pr.desc, lg)) + "</p></div>";
    var legend = '<div class="cp-legend">' + now.map(function (p) { return '<span class="cp-leg">' + sw(p.id) + esc(assetName(data, p.id, lg)) + "</span>"; }).join("") + "</div>";
    h += card(ic("chart-pie") + esc(tw("cp.alloc_now")), legend + allocBar(now, data, lg)
      + '<div class="cp-bar-l cp-muted">' + esc(tw("cp.alloc_neutral")) + "</div>" + allocBar(base, data, lg));
    var rows = order.filter(function (id) { return nowOf[id] || baseOf[id]; }).map(function (id) {
      var d = (nowOf[id] || 0) - (baseOf[id] || 0);
      return "<tr><th>" + sw(id) + esc(assetName(data, id, lg)) + "</th><td>" + (baseOf[id] || 0) + "%</td><td><b>" + (nowOf[id] || 0) + "%</b></td>"
        + '<td class="' + (d > 0 ? "cp-up" : d < 0 ? "cp-down" : "cp-muted") + '">' + (d > 0 ? "+" : d < 0 ? "-" : "") + Math.abs(d) + "</td>"
        + '<td data-amt="' + esc(id) + '">' + (cap ? esc(fmtNum(cap * (nowOf[id] || 0) / 100, 1)) : "-") + "</td></tr>";
    }).join("");
    h += card(ic("calculator") + esc(tw("cp.alloc_table")),
      '<label class="cp-cap"><span>' + esc(tw("cp.capital")) + '</span><input type="number" min="0" step="10" inputmode="decimal" data-capital value="' + (cap || "") + '" placeholder="500">'
      + '<span class="cp-muted">' + esc(tw("cp.capital_unit")) + "</span></label>"
      + '<div class="cp-tbl-wrap"><table class="cp-tbl cp-tbl-num"><thead><tr><th></th><th>' + esc(tw("cp.col_neutral")) + "</th><th>" + esc(tw("cp.col_now_pct"))
      + "</th><th>" + esc(tw("cp.col_tilt")) + "</th><th>" + esc(tw("cp.col_amount")) + "</th></tr></thead><tbody>" + rows + "</tbody></table></div>");
    if ((data.rules || []).length) h += card(ic("shield") + esc(tw("cp.rules_title")), bullets(data.rules, lg));
    return h;
  }
  function amountsFor(data, st) {
    var profs = data.profiles || [];
    var pr = profs.filter(function (p) { return p.id === st.profile; })[0] || profs[0];
    var out = {};
    if (!pr) return out;
    normAlloc(pr.now, (data.assets || []).map(function (a) { return a.id; })).forEach(function (p) { out[p.id] = (+st.capital || 0) * p.pct / 100; });
    return out;
  }

  // ---------- playbook ----------

  function playbookHtml(data, st, lg) {
    var h = "";
    var cal = (data.calendar || []).slice().sort(function (a, b) { return String(a.date).localeCompare(String(b.date)); });
    if (cal.length) {
      h += card(ic("calendar") + esc(tw("cp.cal_title", { n: cal.length })), '<ol class="cp-cal">' + cal.map(function (e) {
        return '<li><span class="cp-cal-d">' + esc(e.date_label ? pick(e.date_label, lg) : e.date) + "</span><div><b>" + esc(pick(e.title, lg)) + "</b>"
          + '<p class="cp-p">' + esc(pick(e.why, lg)) + "</p>"
          + ((e.assets || []).length ? '<div class="cp-tags">' + e.assets.map(function (id) { return '<span class="cp-tag">' + sw(id) + esc(assetName(data, id, lg)) + "</span>"; }).join("") + "</div>" : "")
          + "</div></li>";
      }).join("") + "</ol>");
    }
    if ((data.playbook || []).length) {
      h += card(ic("git-branch") + esc(tw("cp.pb_title")), '<div class="cp-pb">' + data.playbook.map(function (p) {
        return '<div class="cp-pb-r"><div class="cp-pb-if"><span class="cp-pb-k">' + esc(tw("cp.pb_if")) + "</span>" + esc(pick(p["if"], lg)) + "</div>"
          + '<div class="cp-pb-then"><span class="cp-pb-k">' + esc(tw("cp.pb_then")) + "</span>" + esc(pick(p.then, lg)) + "</div></div>";
      }).join("") + "</div>");
    }
    if ((data.history || []).length) {
      h += card(ic("history") + esc(tw("cp.hist_title")), '<ol class="cp-tl">' + data.history.map(function (x) {
        return '<li><span class="cp-tl-y">' + esc(x.period) + "</span><div><b>" + esc(pick(x.title, lg)) + "</b>"
          + '<p class="cp-p">' + esc(pick(x.text, lg)) + "</p>"
          + (x.lesson ? '<p class="cp-lesson">' + ic("lightbulb") + "<span>" + esc(pick(x.lesson, lg)) + "</span></p>" : "") + "</div></li>";
      }).join("") + "</ol>");
    }
    return h;
  }

  function sourcesBlock(data) {
    var s = data.sources || [];
    if (!s.length) return "";
    return '<details class="cp-sources"><summary>' + esc(tw("cp.sources_n", { n: s.length })) + "</summary><ol>" + s.map(function (x) {
      var u = String(x.url || "");
      var safe = /^https?:\/\//i.test(u) ? u : "";
      return "<li>" + (safe ? '<a href="' + esc(safe) + '" target="_blank" rel="noopener noreferrer">' + esc(x.name || safe) + "</a>" : esc(x.name || "")) + "</li>";
    }).join("") + "</ol></details>";
  }

  // ---------- page shell ----------

  function toolbarHtml(data, st, lg) {
    var tabs = TABS.map(function (k) {
      return '<button type="button" class="cp-segb' + (st.tab === k ? " on" : "") + '" data-tab="' + k + '" role="tab" aria-selected="' + (st.tab === k) + '">'
        + ic(TAB_ICON[k]) + esc(tw(TAB_KEY[k])) + "</button>";
    }).join("");
    var age = daysSince(data.updated, st.now);
    var stale = age != null && age > STALE_DAYS;
    return '<div class="cp-toolbar"><div class="cp-seg" role="tablist">' + tabs + '</div><span class="cp-sp"></span>'
      + (data.as_of ? '<span class="cp-chip' + (stale ? " cp-chip-warn" : "") + '">' + (stale ? ic("triangle-alert") : "") + esc(tw(stale ? "cp.as_of_stale" : "cp.as_of", { p: data.as_of })) + "</span>" : "")
      + infoPair(esc(tw("cp.disclaimer")))
      + '<button type="button" class="cp-btn" data-upd aria-expanded="' + (st.updOpen ? "true" : "false") + '">' + ic("refresh-cw") + esc(tw("cp.upd.btn")) + "</button>"
      + '<button type="button" class="cp-btn pri" data-ask>' + ic("message-circle") + esc(tw("cp.ask")) + "</button></div>";
  }
  function pageHtml(data, st) {
    var lg = lang();
    var main = st.tab === "assets" ? assetHtml(data, st, lg)
      : st.tab === "drivers" ? driversHtml(data, st, lg)
      : st.tab === "alloc" ? allocHtml(data, st, lg)
      : st.tab === "playbook" ? playbookHtml(data, st, lg)
      : overviewHtml(data, st, lg);
    return '<div class="cp-root">' + toolbarHtml(data, st, lg) + draftBanner(st.meta, st.preview) + (st.updOpen ? updPanel(st.meta, st.sched) : "")
      + '<div class="cp-main">' + main + sourcesBlock(data)
      + '<div class="cp-foot cp-muted">' + ic("shield") + "<span>" + esc(tw("cp.not_advice")) + "</span></div></div></div>";
  }

  // ---------- monthly update: draft banner and update panel ----------

  function fmtDate(ts) {
    if (!ts) return "";
    try { return new Date(ts * 1000).toLocaleDateString(locale(), { day: "2-digit", month: "2-digit", year: "numeric" }); } catch (e) { return ""; }
  }
  function draftBanner(meta, preview) {
    var d = meta && meta.draft;
    if (!d) return "";
    return '<div class="cp-draft' + (preview ? " on" : "") + '">' + ic("file-pen-line") + '<div class="cp-draft-t"><b>'
      + esc(tw(preview ? "cp.upd.previewing" : "cp.upd.draft", { n: (d.changed || []).length, d: fmtDate(d.at) })) + "</b>"
      + (d.note ? infoPair(esc(d.note), tw("cp.upd.note")) : "") + "</div>"
      + '<button type="button" class="cp-btn" data-upd-preview>' + ic(preview ? "eye-off" : "eye") + esc(tw(preview ? "cp.upd.back" : "cp.upd.preview")) + "</button>"
      + '<button type="button" class="cp-btn pri" data-upd-approve>' + ic("check") + esc(tw("cp.upd.approve")) + "</button>"
      + '<button type="button" class="cp-btn" data-upd-discard>' + ic("x") + esc(tw("cp.upd.discard")) + "</button></div>";
  }
  function updPanel(meta, sched) {
    var src = meta && meta.source === "updated" ? tw("cp.upd.src_updated", { d: fmtDate(meta.updated_at) }) : tw("cp.upd.src_bundled");
    var sc = sched === null || sched === undefined ? '<span class="cp-muted">' + esc(tw("common.loading")) + "</span>"
      : sched ? '<span class="cp-chip cp-chip-live">' + ic("calendar-check") + esc(tw("cp.upd.sched_on", { next: sched.next || "" })) + "</span>"
        + '<button type="button" class="cp-btn" data-upd-unsched="' + esc(sched.id) + '">' + esc(tw("cp.upd.sched_off")) + "</button>"
      : '<button type="button" class="cp-btn" data-upd-sched>' + ic("calendar-clock") + esc(tw("cp.upd.sched_btn")) + "</button>";
    return '<div class="cp-upd"><span class="cp-chip">' + esc(src) + "</span>" + sc
      + '<span class="cp-sp"></span><button type="button" class="cp-btn pri" data-upd-now>' + ic("sparkles") + esc(tw("cp.upd.now")) + "</button>"
      + infoPair(esc(tw("cp.upd.info")), tw("cp.upd.how")) + "</div>";
  }

  function liveBrief(ov, data, lg) {
    if (!ov) return "";
    return (data.pulse || []).map(function (p) {
      if (p.kind === "fng") { var f = liveGet(ov, p.ref); return f && f.value != null ? pick(p.name, lg) + " " + f.value : ""; }
      if (p.kind === "regime") { var g = liveGet(ov, p.ref); return g && g.label ? pick(p.name, lg) + " " + g.label : ""; }
      var r = liveGet(ov, p.ref);
      return r && r.price != null ? pick(p.name, lg) + " " + fmtNum(r.price, 2) + (r.chg_5d != null ? " (" + fmtPct(r.chg_5d, 1) + "/5d)" : "") : "";
    }).filter(Boolean).join("; ");
  }
  function askPrompt(data, st, lg) {
    var live = liveBrief(st.live || null, data, lg);
    var tail = live ? " " + tw("cp.ask_live", { live: live }) : "";
    if (st.tab === "assets") {
      var a = assetById(data, st.asset) || (data.assets || [])[0];
      return tw("cp.ask_prompt_asset", { asset: a ? pick(a.name, lg) : "", stance: a ? tw(STANCE_KEY[a.stance === "accumulate" ? "acc" : a.stance === "reduce" ? "red" : "hold"]) : "", period: data.as_of || "" }) + tail;
    }
    if (st.tab === "alloc") {
      var pr = (data.profiles || []).filter(function (p) { return p.id === st.profile; })[0];
      return tw("cp.ask_prompt_alloc", { profile: pr ? pick(pr.name, lg) : "", capital: st.capital ? fmtNum(st.capital, 0) : "?" }) + tail;
    }
    return tw("cp.ask_prompt", { period: data.as_of || "" }) + tail;
  }

  // ---------- mount ----------

  var _st = null, _el = null, _data = null;

  function readPref() {
    try { return JSON.parse(localStorage.getItem("javis.compass") || "{}") || {}; } catch (e) { return {}; }
  }
  function savePref() {
    try { localStorage.setItem("javis.compass", JSON.stringify({ tab: _st.tab, asset: _st.asset, profile: _st.profile, capital: _st.capital, scope: _st.scope })); } catch (e) {}
  }
  function render() {
    if (!_el || !_data) return;
    _el.innerHTML = pageHtml(_data, _st);
  }
  function onClick(e) {
    var t = e.target.closest ? e.target.closest("button") : null;
    if (!t || !_el || !_el.contains(t)) return;
    if (t.hasAttribute("data-tab")) { _st.tab = t.getAttribute("data-tab"); savePref(); render(); }
    else if (t.hasAttribute("data-asset")) {
      _st.asset = t.getAttribute("data-asset"); _st.tab = "assets"; savePref(); render();
      var top = _el.querySelector(".cp-root"); if (top && top.scrollIntoView) top.scrollIntoView({ block: "start" });
    }
    else if (t.hasAttribute("data-scope")) { _st.scope = t.getAttribute("data-scope"); savePref(); render(); }
    else if (t.hasAttribute("data-profile")) { _st.profile = t.getAttribute("data-profile"); savePref(); render(); }
    else if (t.hasAttribute("data-ask")) askJavis(askPrompt(_data, _st, lang()));
    else if (t.hasAttribute("data-upd")) { _st.updOpen = !_st.updOpen; render(); if (_st.updOpen) loadSched(); }
    else if (t.hasAttribute("data-upd-now")) askJavis(tw("cp.upd.prompt"));
    else if (t.hasAttribute("data-upd-sched")) makeSched(t);
    else if (t.hasAttribute("data-upd-unsched")) dropSched(t.getAttribute("data-upd-unsched"));
    else if (t.hasAttribute("data-upd-preview")) { _st.preview = !_st.preview; loadData(_el); }
    else if (t.hasAttribute("data-upd-approve")) {
      if (!confirm(tw("cp.upd.approve_confirm"))) return;
      post("/compass/approve").then(function () { _st.preview = false; loadData(_el); });
    } else if (t.hasAttribute("data-upd-discard")) {
      if (!confirm(tw("cp.upd.discard_confirm"))) return;
      post("/compass/discard").then(function () { _st.preview = false; loadData(_el); });
    }
  }
  function post(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json(); }).catch(function () { return { ok: false }; });
  }
  function brainPath() {
    try { if (window.currentBrainPath) return window.currentBrainPath(); } catch (e) {}
    try { if (window.JavisChatApi && window.JavisChatApi.brain) return window.JavisChatApi.brain(); } catch (e) {}
    return "brain";
  }
  // The monthly job is an ordinary reminder (Tasks page, Recurring list), found again by the tool name in its text.
  function loadSched() {
    _st.sched = null;
    return fetch("/reminders?brain=" + encodeURIComponent(brainPath())).then(function (r) { return r.json(); }).then(function (d) {
      var all = (d.pending || []).concat(d.paused || []);
      var hit = all.filter(function (x) { return String(x.text || "").indexOf(UPD_MARK) >= 0; })[0];
      _st.sched = hit ? { id: hit.id, next: hit.due_human || "" } : false;
      if (_st.updOpen) render();
    }).catch(function () { _st.sched = false; if (_st.updOpen) render(); });
  }
  function makeSched(btn) {
    btn.disabled = true;
    post("/reminders", { text: tw("cp.upd.prompt"), cron: UPD_CRON, mode: "task", label: tw("cp.upd.label"), brain: brainPath(),
      created_by: "user", allow_no_channel: true, muc_quyen: "auto" }).then(function (r) {
      if (!r || !r.ok) { btn.disabled = false; alert((r && r.error) || tw("cp.load_error")); return; }
      loadSched();
    });
  }
  function dropSched(id) {
    var f = new FormData();
    f.append("id", id);
    f.append("brain", brainPath());
    fetch("/reminders/cancel", { method: "POST", body: f }).then(function () { loadSched(); });
  }
  // Typing the capital updates the amounts in place, so the input keeps its focus and caret.
  function onInput(e) {
    var inp = e.target;
    if (!inp || !inp.hasAttribute || !inp.hasAttribute("data-capital")) return;
    _st.capital = Math.max(0, +inp.value || 0);
    savePref();
    var am = amountsFor(_data, _st);
    Array.prototype.forEach.call(_el.querySelectorAll("[data-amt]"), function (td) {
      var v = am[td.getAttribute("data-amt")];
      td.textContent = _st.capital && v != null ? fmtNum(v, 1) : "-";
    });
  }
  function loadLive(el) {
    return fetch(LIVE_URL).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(function (d) {
      if (_el !== el) return;
      _st.live = d && d.ok !== false && d.sections ? d : false;
      render();
    }).catch(function () { if (_el !== el) return; _st.live = false; render(); });
  }
  function loadData(el) {
    return fetch(DATA_URL + (_st.preview ? "?draft=1" : "")).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (res) {
      _st.meta = { source: res.source, updated_at: res.updated_at, draft: res.draft };
      if (!res.draft) _st.preview = false;
      return res.data;
    }).catch(function () {
      return fetch(STATIC_URL).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
    }).then(function (d) {
      if (_el !== el) return;
      _data = d || { assets: [] };
      var ids = (_data.assets || []).map(function (a) { return a.id; });
      if (ids.indexOf(_st.asset) < 0) _st.asset = ids[0] || "";
      var pids = (_data.profiles || []).map(function (p) { return p.id; });
      if (pids.indexOf(_st.profile) < 0) _st.profile = pids[1] || pids[0] || "";
      render();
    }).catch(function () {
      if (_el !== el) return;
      el.innerHTML = '<div class="cp-root"><div class="cp-err">' + ic("triangle-alert") + esc(tw("cp.load_error")) + "</div></div>";
    });
  }
  // Opens the chat with the prompt typed in, not sent: the owner may want to add a budget or a horizon first.
  function askJavis(text) {
    if (window.JavisNav && window.JavisNav.go) window.JavisNav.go("chat");
    var tries = 0;
    (function fill() {
      var inp = document.getElementById("chatInput");
      if (!inp && tries++ < 20) return setTimeout(fill, 100);
      if (!inp) return;
      inp.value = text;
      try { inp.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) {}
      inp.focus();
    })();
  }
  function mount(el) {
    _el = el;
    var pref = readPref();
    _st = { tab: TABS.indexOf(pref.tab) >= 0 ? pref.tab : "overview", asset: pref.asset || "", profile: pref.profile || "",
      capital: +pref.capital > 0 ? +pref.capital : 0, scope: pref.scope || "all", live: null, now: Date.now(),
      updOpen: false, preview: false, meta: null, sched: null };
    el.innerHTML = '<div class="cp-root"><div class="cp-muted">' + esc(tw("common.loading")) + "</div></div>";
    el.addEventListener("click", onClick);
    el.addEventListener("input", onInput);
    loadLive(el);
    return loadData(el);
  }
  function unmount() {
    if (_el) { _el.removeEventListener("click", onClick); _el.removeEventListener("input", onInput); }
    _el = null; _data = null;
  }

  var api = {
    mount: mount, unmount: unmount,
    // pure helpers, for tests
    _pick: pick, _liveGet: liveGet, _evalCond: evalCond, _signalTally: signalTally, _normAlloc: normAlloc,
    _clockSvg: clockSvg, _pageHtml: pageHtml, _askPrompt: askPrompt, TABS: TABS, ASSET_SLOT: ASSET_SLOT,
  };
  if (typeof window !== "undefined") window.JavisCompass = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
