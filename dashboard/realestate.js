/* Real-estate page: Vietnam housing markets for brokers and investors (Da Nang, Ho Chi Minh City, Dong Nai).
 *
 * The content is a curated, sourced data file (dashboard/realestate/data.json): each region carries the current
 * snapshot, a yearly price series since 2006, what happened over the last 20/15/10/5/2 years, sub-areas scored for
 * potential and risk, infrastructure, policy, a three-scenario outlook and a broker playbook. Every text field in it
 * is {vi, en}. The numbers are the researchers' reading of published reports (CBRE, Savills, DKRA, press), so the page
 * always shows the "as of" period and the sources; "Ask Javis" opens the chat with a prompt to pull fresher numbers.
 *
 * Owner rules kept here: no repeated page title, long explanations behind the (i) button, nothing under 16px except
 * chart ticks.
 *
 * Render helpers are pure (tested under node); `mount` loads the data and wires the clicks.
 */
(function () {
  "use strict";

  // The server serves the approved quarterly update when there is one, else the bundled file (realestate_store.py).
  var DATA_URL = "/realestate/data";
  var STATIC_URL = "/static/realestate/data.json?v=1";
  // Quarterly refresh: the 20th of January, April, July and October at 09:00, after CBRE/DKRA/VARS publish.
  var UPD_CRON = "0 9 20 1,4,7,10 *";
  var UPD_MARK = "javis_realestate_draft";
  var NOW_YEAR = 2026;
  var SPANS = [20, 15, 10, 5, 2];
  // Colour follows the entity, never its rank: a series key or a region always gets the same slot.
  var SERIES_SLOT = { apartment: 1, land: 2, landed: 2, apartment_merged: 3 };
  var REGION_SLOT = { hcm: 1, danang: 2, dongnai: 3 };

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
  function fmtPct(p) {
    if (p == null || !isFinite(p)) return "-";
    return (p > 0 ? "+" : "") + fmtNum(p, Math.abs(p) >= 100 ? 0 : 1) + "%";
  }

  // ---------- numbers ----------

  // The value of a series at the first year >= `from` that has data, and at the last year <= `to` that has data.
  function windowEnds(points, from, to) {
    var start = null, end = null;
    (points || []).forEach(function (p) {
      var y = p[0], v = p[1];
      if (v == null || !isFinite(v)) return;
      if (y >= from && y <= to) {
        if (!start || y < start[0]) start = [y, v];
        if (!end || y > end[0]) end = [y, v];
      }
    });
    return start && end && end[0] > start[0] ? { from: start, to: end } : null;
  }
  // Total change and compound yearly growth of one series over the last `span` years.
  function spanChange(points, span, nowYear) {
    var now = nowYear || NOW_YEAR;
    var w = windowEnds(points, now - span, now);
    if (!w) return null;
    var a = w.from[1], b = w.to[1], years = w.to[0] - w.from[0];
    if (!(a > 0)) return null;
    return {
      fromYear: w.from[0], toYear: w.to[0], fromValue: a, toValue: b,
      total: (b / a - 1) * 100,
      cagr: (Math.pow(b / a, 1 / years) - 1) * 100,
      multiple: b / a,
      partial: w.from[0] > now - span,   // the series starts later than the span asks for
    };
  }

  // ---------- chart (inline SVG, one axis, gaps stay gaps) ----------

  // The top of the y axis: four equal steps, each a round number (5, 10, 15, 20, 25, 30, 40, 50...).
  function niceMax(v) {
    if (!(v > 0)) return 10;
    var raw = v / 4, p = Math.pow(10, Math.floor(Math.log10(raw)));
    var steps = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
    for (var i = 0; i < steps.length; i++) if (steps[i] * p >= raw) return 4 * steps[i] * p;
    return 40 * p;
  }
  /** lines: [{key, slot, name, points:[[year, value|null]]}]. band: [fromYear, toYear] to shade, or null. */
  function chartSvg(lines, opts) {
    opts = opts || {};
    var W = Math.max(300, opts.width || 720), H = opts.height || 280;
    var m = { l: 46, r: 14, t: 14, b: 30 };
    var x0 = opts.fromYear || 2006, x1 = opts.toYear || NOW_YEAR;
    var vmax = 0;
    lines.forEach(function (s) { (s.points || []).forEach(function (p) { if (p[1] != null && p[1] > vmax) vmax = p[1]; }); });
    var ymax = niceMax(vmax * 1.08);
    var X = function (y) { return m.l + (y - x0) / (x1 - x0) * (W - m.l - m.r); };
    var Y = function (v) { return H - m.b - v / ymax * (H - m.t - m.b); };
    var out = ['<svg class="re-chart-svg" viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" role="img" aria-label="' + esc(opts.label || "") + '">'];
    if (opts.band) {
      var bx = X(Math.max(x0, opts.band[0])), bw = X(opts.band[1]) - bx;
      out.push('<rect class="re-band" x="' + bx.toFixed(1) + '" y="' + m.t + '" width="' + bw.toFixed(1) + '" height="' + (H - m.t - m.b) + '"/>');
    }
    for (var i = 0; i <= 4; i++) {
      var v = ymax * i / 4, y = Y(v).toFixed(1);
      out.push('<line class="re-grid" x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + y + '" y2="' + y + '"/>');
      out.push('<text class="re-tick" x="' + (m.l - 6) + '" y="' + y + '" dy="4" text-anchor="end">' + esc(fmtNum(v, 0)) + "</text>");
    }
    var stepYear = W < 520 ? 5 : 2;
    for (var yr = x0; yr <= x1; yr++) {
      if ((yr - x0) % stepYear && yr !== x1) continue;
      if (yr !== x1 && x1 - yr < stepYear) continue;   // keep the last label from colliding
      out.push('<text class="re-tick" x="' + X(yr).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="middle">' + yr + "</text>");
    }
    lines.forEach(function (s) {
      var seg = [], d = "";
      (s.points || []).forEach(function (p) {
        if (p[1] == null || p[0] < x0 || p[0] > x1) { if (seg.length) { d += "M" + seg.join("L"); seg = []; } return; }
        seg.push(X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1));
      });
      if (seg.length) d += "M" + seg.join("L");
      if (d) out.push('<path class="re-line re-s' + s.slot + '" d="' + d + '"/>');
      // A small mark on every year with data: sparse series (a lone year between gaps) would otherwise be invisible.
      (s.points || []).forEach(function (p) {
        if (p[1] == null || p[0] < x0 || p[0] > x1) return;
        out.push('<circle class="re-pt re-s' + s.slot + '" cx="' + X(p[0]).toFixed(1) + '" cy="' + Y(p[1]).toFixed(1) + '" r="3"/>');
      });
    });
    out.push('<line class="re-cross" x1="0" x2="0" y1="' + m.t + '" y2="' + (H - m.b) + '" style="display:none"/>');
    out.push('<g class="re-dots"></g>');
    out.push('<rect class="re-hit" x="' + m.l + '" y="' + m.t + '" width="' + (W - m.l - m.r) + '" height="' + (H - m.t - m.b) + '"/>');
    out.push("</svg>");
    return { svg: out.join(""), X: X, Y: Y, x0: x0, x1: x1, m: m, W: W, H: H };
  }
  function legendHtml(lines) {
    return '<div class="re-legend">' + lines.map(function (s) {
      return '<span class="re-leg"><i class="re-sw re-s' + s.slot + '"></i>' + esc(s.name) + "</span>";
    }).join("") + "</div>";
  }

  // ---------- small pieces ----------

  function trendIcon(tr) {
    if (tr === "up") return '<span class="re-tr up">' + ic("trending-up") + "</span>";
    if (tr === "down") return '<span class="re-tr down">' + ic("trending-down") + "</span>";
    return '<span class="re-tr flat">' + ic("minus") + "</span>";
  }
  function meter(n, kind) {
    n = Math.max(0, Math.min(5, +n || 0));
    var s = "";
    for (var i = 1; i <= 5; i++) s += '<i class="' + (i <= n ? "on" : "") + '"></i>';
    return '<span class="re-meter re-m-' + kind + '" title="' + n + '/5" aria-label="' + n + '/5">' + s + "</span>";
  }
  function bullets(list, lg) {
    if (!list || !list.length) return "";
    return '<ul class="re-ul">' + list.map(function (b) { return "<li>" + esc(pick(b, lg)) + "</li>"; }).join("") + "</ul>";
  }
  function card(title, inner, extraCls) {
    return '<section class="re-card' + (extraCls ? " " + extraCls : "") + '"><h3 class="re-h">' + title + "</h3>" + inner + "</section>";
  }
  function seriesLines(region, lg) {
    var ps = region.price_series || {};
    return (ps.series || []).map(function (s) {
      return { key: s.key, slot: SERIES_SLOT[s.key] || 1, name: pick(s.name, lg), points: s.points || [] };
    });
  }

  // ---------- region view ----------

  function kpiGrid(region, lg) {
    var k = region.kpis || [];
    if (!k.length) return "";
    return '<div class="re-kpis">' + k.map(function (x) {
      return '<div class="re-kpi"><div class="re-kpi-l">' + esc(pick(x.label, lg)) + "</div>"
        + '<div class="re-kpi-v"><b>' + esc(pick(x.value, lg)) + "</b> <span>" + esc(pick(x.unit, lg)) + "</span></div>"
        + '<div class="re-kpi-c">' + trendIcon(x.trend) + (x.change ? "<span>" + esc(pick(x.change, lg)) + "</span>" : "")
        + (x.source ? '<span class="re-src">' + esc(x.source) + "</span>" : "") + "</div></div>";
    }).join("") + "</div>";
  }

  function periodBlock(region, span, lg) {
    var p = (region.periods || []).filter(function (x) { return +x.span === +span; })[0];
    var lines = seriesLines(region, lg);
    var rows = lines.map(function (s) {
      var c = spanChange(s.points, span);
      if (!c) return "";
      return '<div class="re-chg"><i class="re-sw re-s' + s.slot + '"></i><span class="re-chg-n">' + esc(s.name) + "</span>"
        + '<span class="re-chg-v">' + esc(fmtNum(c.fromValue)) + " → " + esc(fmtNum(c.toValue)) + " (" + c.fromYear + "-" + c.toYear + ")</span>"
        + '<b class="re-chg-p ' + (c.total >= 0 ? "up" : "down") + '">' + esc(fmtPct(c.total)) + "</b>"
        + '<span class="re-chg-y">' + esc(tw("re.cagr", { pct: fmtPct(c.cagr) })) + "</span></div>";
    }).join("");
    var seg = '<div class="re-seg" role="tablist">' + SPANS.map(function (s) {
      return '<button type="button" class="re-segb' + (s === +span ? " on" : "") + '" data-span="' + s + '" role="tab" aria-selected="' + (s === +span) + '">'
        + esc(tw("re.span_years", { n: s })) + "</button>";
    }).join("") + "</div>";
    var body = "";
    if (p) {
      body += '<div class="re-period-h"><b>' + esc(pick(p.title, lg)) + "</b>" + (p.range ? '<span class="re-chip">' + esc(p.range) + "</span>" : "")
        + (p.change ? '<span class="re-chip re-chip-acc">' + esc(pick(p.change, lg)) + "</span>" : "") + "</div>";
      body += '<p class="re-p">' + esc(pick(p.text, lg)) + "</p>";
      if (p.milestones && p.milestones.length) {
        body += '<ol class="re-tl">' + p.milestones.map(function (mi) {
          return '<li><span class="re-tl-y">' + esc(mi.year) + "</span><span>" + esc(pick(mi.text, lg)) + "</span></li>";
        }).join("") + "</ol>";
      }
    }
    return seg + (rows ? '<div class="re-chgs">' + rows + "</div>" : "") + body;
  }

  function subareaList(region, sortBy, lg) {
    var list = (region.subareas || []).slice();
    if (sortBy === "risk") list.sort(function (a, b) { return (a.risk || 0) - (b.risk || 0); });
    else if (sortBy === "name") list.sort(function (a, b) { return pick(a.name, lg).localeCompare(pick(b.name, lg), locale()); });
    else list.sort(function (a, b) { return (b.potential || 0) - (a.potential || 0) || (a.risk || 0) - (b.risk || 0); });
    var sorts = [["potential", "re.sort_potential"], ["risk", "re.sort_risk"], ["name", "re.sort_name"]];
    var head = '<div class="re-row-tools"><span class="re-muted">' + esc(tw("re.sort_by")) + "</span>" + sorts.map(function (s) {
      return '<button type="button" class="re-chipb' + (sortBy === s[0] ? " on" : "") + '" data-sort="' + s[0] + '">' + esc(tw(s[1])) + "</button>";
    }).join("") + "</div>";
    return head + '<div class="re-areas">' + list.map(function (a) {
      return '<article class="re-area"><div class="re-area-h"><b>' + esc(pick(a.name, lg)) + "</b>"
        + (a.type ? '<span class="re-chip">' + esc(pick(a.type, lg)) + "</span>" : "") + "</div>"
        + (a.price ? '<div class="re-area-price">' + esc(pick(a.price, lg)) + "</div>" : "")
        + '<p class="re-p">' + esc(pick(a.highlight, lg)) + "</p>"
        + '<div class="re-area-m"><span>' + esc(tw("re.potential")) + " " + meter(a.potential, "pot") + "</span>"
        + "<span>" + esc(tw("re.risk")) + " " + meter(a.risk, "risk") + "</span></div></article>";
    }).join("") + "</div>";
  }

  function segmentTable(region, lg) {
    var s = region.segments || [];
    if (!s.length) return "";
    return '<div class="re-tbl-wrap"><table class="re-tbl"><thead><tr><th>' + esc(tw("re.col_segment")) + "</th><th>" + esc(tw("re.col_price"))
      + "</th><th>" + esc(tw("re.col_trend")) + "</th><th>" + esc(tw("re.col_note")) + "</th></tr></thead><tbody>"
      + s.map(function (x) {
        return "<tr><td><b>" + esc(pick(x.name, lg)) + "</b></td><td>" + esc(pick(x.price, lg)) + "</td><td>" + trendIcon(x.trend)
          + "</td><td>" + esc(pick(x.note, lg)) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }

  function infraList(region, lg) {
    var s = region.infrastructure || [];
    if (!s.length) return "";
    return '<div class="re-infra">' + s.map(function (x) {
      return '<div class="re-inf"><div class="re-inf-h"><b>' + esc(pick(x.name, lg)) + "</b>"
        + (x.eta ? '<span class="re-chip re-chip-acc">' + esc(x.eta) + "</span>" : "") + "</div>"
        + (x.status ? '<div class="re-muted">' + esc(pick(x.status, lg)) + "</div>" : "")
        + '<p class="re-p">' + esc(pick(x.impact, lg)) + "</p></div>";
    }).join("") + "</div>";
  }

  function policyList(region, lg) {
    var s = region.policy || [];
    if (!s.length) return "";
    return '<div class="re-infra">' + s.map(function (x) {
      return '<div class="re-inf"><div class="re-inf-h"><b>' + esc(pick(x.title, lg)) + "</b></div><p class=\"re-p\">" + esc(pick(x.text, lg)) + "</p></div>";
    }).join("") + "</div>";
  }

  var SCEN_ORDER = { bear: 0, base: 1, bull: 2 };
  function forecastBlock(region, lg) {
    var f = region.forecast || {};
    var sc = (f.scenarios || []).slice().sort(function (a, b) { return (SCEN_ORDER[a.key] || 0) - (SCEN_ORDER[b.key] || 0); });
    var html = '<div class="re-scen">' + sc.map(function (s) {
      return '<div class="re-sc re-sc-' + esc(s.key) + '"><div class="re-sc-h">' + esc(pick(s.name, lg)) + "</div>"
        + '<div class="re-sc-v">' + esc(pick(s.price_change, lg)) + (s.estimate ? ' <span class="re-chip re-chip-warn">' + esc(tw("re.estimate")) + "</span>" : "") + "</div><p class=\"re-p\">" + esc(pick(s.text, lg)) + "</p></div>";
    }).join("") + "</div>";
    html += '<div class="re-2col"><div><h4 class="re-h4">' + ic("trending-up") + esc(tw("re.drivers")) + "</h4>" + bullets(f.drivers, lg)
      + '</div><div><h4 class="re-h4">' + ic("triangle-alert") + esc(tw("re.risks")) + "</h4>" + bullets(f.risks, lg) + "</div></div>";
    if (f.sources && f.sources.length) html += '<div class="re-muted re-small">' + esc(tw("re.forecast_by", { who: f.sources.join(", ") })) + "</div>";
    return html;
  }

  function sourcesBlock(region) {
    var s = region.sources || [];
    if (!s.length) return "";
    return '<details class="re-sources"><summary>' + esc(tw("re.sources_n", { n: s.length })) + "</summary><ol>" + s.map(function (x) {
      var u = String(x.url || "");
      var safe = /^https?:\/\//i.test(u) ? u : "";
      return "<li>" + (safe ? '<a href="' + esc(safe) + '" target="_blank" rel="noopener noreferrer">' + esc(x.name || safe) + "</a>" : esc(x.name || "")) + "</li>";
    }).join("") + "</ol></details>";
  }

  function regionHtml(region, st, lg) {
    var ps = region.price_series || {};
    var h = "";
    h += '<div class="re-hero"><div class="re-hero-t">' + esc(pick(region.tagline, lg)) + "</div>"
      + '<p class="re-p">' + esc(pick(region.summary, lg)) + "</p></div>";
    h += kpiGrid(region, lg);
    var lines = seriesLines(region, lg);
    if (lines.length) {
      var low = ps.confidence === "low"
        ? ' <span class="re-chip re-chip-warn">' + ic("triangle-alert") + esc(pick(ps.confidence_label, lg) || tw("re.low_conf")) + "</span>" : "";
      h += card(esc(tw("re.price_title", { unit: pick(ps.unit, lg) })) + low,
        legendHtml(lines) + '<div class="re-chart" data-chart="region"></div>'
        + (ps.note ? '<div class="re-note">' + infoPair(esc(pick(ps.note, lg))) + '<span class="re-muted">' + esc(tw("re.how_built")) + "</span></div>" : "")
        + '<div class="re-period">' + periodBlock(region, st.span, lg) + "</div>");
    }
    if (region.forecast) h += card(esc(tw("re.forecast_title", { h: (region.forecast.horizon || "") })), forecastBlock(region, lg));
    h += '<div class="re-2col">'
      + card(ic("sparkles") + esc(tw("re.potential_title")), bullets(region.potential, lg))
      + card(ic("lightbulb") + esc(tw("re.playbook_title")), bullets(region.playbook, lg)) + "</div>";
    if ((region.subareas || []).length) h += card(ic("map-pin") + esc(tw("re.areas_title", { n: region.subareas.length })), '<div data-areas>' + subareaList(region, st.sort, lg) + "</div>");
    if ((region.segments || []).length) h += card(esc(tw("re.segments_title")), segmentTable(region, lg));
    if ((region.infrastructure || []).length) h += card(esc(tw("re.infra_title", { n: region.infrastructure.length })), infraList(region, lg));
    if ((region.policy || []).length) h += card(esc(tw("re.policy_title")), policyList(region, lg));
    h += sourcesBlock(region);
    return h;
  }

  // ---------- compare view ----------

  // The series key the three regions share best, preferring apartments.
  function compareKeys(regions) {
    var count = {};
    regions.forEach(function (r) { ((r.price_series || {}).series || []).forEach(function (s) { count[s.key] = (count[s.key] || 0) + 1; }); });
    return Object.keys(count).sort(function (a, b) { return count[b] - count[a] || (a === "apartment" ? -1 : b === "apartment" ? 1 : 0); });
  }
  function compareLines(regions, key, lg) {
    var out = [];
    regions.forEach(function (r) {
      var s = ((r.price_series || {}).series || []).filter(function (x) { return x.key === key; })[0];
      if (s) out.push({ key: r.id, slot: REGION_SLOT[r.id] || 1, name: pick(r.name, lg), points: s.points || [] });
    });
    return out;
  }
  function avg(list, f) {
    var v = (list || []).map(f).filter(function (x) { return isFinite(x) && x > 0; });
    return v.length ? v.reduce(function (a, b) { return a + b; }, 0) / v.length : null;
  }
  function compareHtml(regions, st, lg) {
    var keys = compareKeys(regions);
    var key = keys.indexOf(st.cmpKey) >= 0 ? st.cmpKey : keys[0];
    var nameOf = {};
    regions.forEach(function (r) { ((r.price_series || {}).series || []).forEach(function (s) { if (!nameOf[s.key]) nameOf[s.key] = pick(s.name, lg); }); });
    var lines = compareLines(regions, key, lg);
    var h = "";
    h += '<div class="re-row-tools">' + keys.map(function (k) {
      return '<button type="button" class="re-chipb' + (k === key ? " on" : "") + '" data-cmpkey="' + esc(k) + '">' + esc(nameOf[k] || k) + "</button>";
    }).join("") + "</div>";
    if (lines.length) h += card(esc(tw("re.cmp_chart_title")), legendHtml(lines) + '<div class="re-chart" data-chart="compare"></div>');
    // Growth per span, one row per region.
    var rows = lines.map(function (l) {
      return "<tr><th><i class=\"re-sw re-s" + l.slot + "\"></i>" + esc(l.name) + "</th>" + SPANS.map(function (s) {
        var c = spanChange(l.points, s);
        // A series shorter than the span says which years it really covers, so "+60% over 20 years" never hides "since 2018".
        return "<td>" + (c ? "<b>" + esc(fmtPct(c.total)) + "</b><br><span class=\"re-muted\">" + esc(tw("re.cagr", { pct: fmtPct(c.cagr) })) + "</span>"
          + (c.partial ? '<br><span class="re-partial">' + c.fromYear + "-" + c.toYear + "</span>" : "") : "-") + "</td>";
      }).join("") + "</tr>";
    }).join("");
    if (rows) {
      h += card(esc(tw("re.cmp_growth_title")), '<div class="re-tbl-wrap"><table class="re-tbl re-tbl-num"><thead><tr><th></th>'
        // Columns read as year ranges (owner, 09/11/2026); the span in years stays as the hover hint.
        + SPANS.map(function (s) { return '<th title="' + esc(tw("re.span_years", { n: s })) + '">' + (NOW_YEAR - s) + "-" + NOW_YEAR + "</th>"; }).join("") + "</tr></thead><tbody>" + rows + "</tbody></table></div>");
    }
    // Side by side: character, outlook, scores.
    var cols = regions.map(function (r) {
      var base = ((r.forecast || {}).scenarios || []).filter(function (s) { return s.key === "base"; })[0];
      var pot = avg(r.subareas, function (a) { return +a.potential; });
      var risk = avg(r.subareas, function (a) { return +a.risk; });
      return '<div class="re-cmpcol"><div class="re-cmp-h"><i class="re-sw re-s' + (REGION_SLOT[r.id] || 1) + '"></i><b>' + esc(pick(r.name, lg)) + "</b>"
        + '<span class="re-chip">' + esc(r.as_of || "") + "</span></div>"
        + '<div class="re-hero-t">' + esc(pick(r.tagline, lg)) + "</div>"
        + '<dl class="re-dl">'
        + (base ? "<dt>" + esc(tw("re.cmp_base")) + "</dt><dd><b>" + esc(pick(base.price_change, lg)) + "</b></dd>" : "")
        + (pot ? "<dt>" + esc(tw("re.cmp_pot")) + "</dt><dd>" + meter(Math.round(pot), "pot") + " " + esc(fmtNum(pot, 1)) + "</dd>" : "")
        + (risk ? "<dt>" + esc(tw("re.cmp_risk")) + "</dt><dd>" + meter(Math.round(risk), "risk") + " " + esc(fmtNum(risk, 1)) + "</dd>" : "")
        + "</dl>" + bullets((r.potential || []).slice(0, 3), lg)
        + '<button type="button" class="re-btn sm" data-region="' + esc(r.id) + '">' + esc(tw("re.cmp_open")) + "</button></div>";
    }).join("");
    h += '<div class="re-cmpcols">' + cols + "</div>";
    return h;
  }

  // ---------- page shell ----------

  function toolbarHtml(data, st, lg) {
    var regs = data.regions || [];
    var tabs = regs.map(function (r) {
      return '<button type="button" class="re-segb' + (st.region === r.id ? " on" : "") + '" data-region="' + esc(r.id) + '">' + esc(pick(r.name, lg)) + "</button>";
    }).join("") + '<button type="button" class="re-segb' + (st.region === "compare" ? " on" : "") + '" data-region="compare">' + ic("chart-column") + esc(tw("re.compare")) + "</button>";
    var cur = regs.filter(function (r) { return r.id === st.region; })[0];
    var asOf = cur ? cur.as_of : data.updated;
    return '<div class="re-toolbar"><div class="re-seg">' + tabs + "</div><span class=\"re-sp\"></span>"
      + (asOf ? '<span class="re-chip">' + esc(tw("re.as_of", { p: asOf })) + "</span>" : "")
      + infoPair(esc(tw("re.disclaimer")))
      + '<button type="button" class="re-btn" data-upd aria-expanded="' + (st.updOpen ? "true" : "false") + '">' + ic("refresh-cw") + esc(tw("re.upd.btn")) + "</button>"
      + '<button type="button" class="re-btn pri" data-ask>' + ic("message-circle") + esc(tw("re.ask")) + "</button></div>";
  }

  function pageHtml(data, st) {
    var lg = lang();
    var regs = data.regions || [];
    var cur = regs.filter(function (r) { return r.id === st.region; })[0];
    var main = st.region === "compare" ? compareHtml(regs, st, lg) : (cur ? regionHtml(cur, st, lg) : "");
    return '<div class="re-root">' + toolbarHtml(data, st, lg) + draftBanner(st.meta, st.preview) + (st.updOpen ? updPanel(st.meta, st.sched) : "") +
      '<div class="re-main">' + main + "</div></div>";
  }

  function fmtDate(ts) {
    if (!ts) return "";
    try { return new Date(ts * 1000).toLocaleDateString(locale(), { day: "2-digit", month: "2-digit", year: "numeric" }); } catch (e) { return ""; }
  }
  function draftBanner(meta, preview) {
    var d = meta && meta.draft;
    if (!d) return "";
    return '<div class="re-draft' + (preview ? " on" : "") + '">' + ic("file-pen-line") + '<div class="re-draft-t"><b>' +
      esc(tw(preview ? "re.upd.previewing" : "re.upd.draft", { n: (d.changed || []).length, d: fmtDate(d.at) })) + "</b>" +
      (d.note ? infoPair(esc(d.note), tw("re.upd.note")) : "") + "</div>" +
      '<button type="button" class="re-btn" data-upd-preview>' + ic(preview ? "eye-off" : "eye") + esc(tw(preview ? "re.upd.back" : "re.upd.preview")) + "</button>" +
      '<button type="button" class="re-btn pri" data-upd-approve>' + ic("check") + esc(tw("re.upd.approve")) + "</button>" +
      '<button type="button" class="re-btn" data-upd-discard>' + ic("x") + esc(tw("re.upd.discard")) + "</button></div>";
  }
  function updPanel(meta, sched) {
    var src = meta && meta.source === "updated" ? tw("re.upd.src_updated", { d: fmtDate(meta.updated_at) }) : tw("re.upd.src_bundled");
    var sc = sched === null || sched === undefined ? '<span class="re-muted">' + esc(tw("common.loading")) + "</span>"
      : sched ? '<span class="re-chip ok">' + ic("calendar-check") + esc(tw("re.upd.sched_on", { next: sched.next || "" })) + "</span>" +
        '<button type="button" class="re-btn" data-upd-unsched="' + esc(sched.id) + '">' + esc(tw("re.upd.sched_off")) + "</button>"
      : '<button type="button" class="re-btn" data-upd-sched>' + ic("calendar-clock") + esc(tw("re.upd.sched_btn")) + "</button>";
    return '<div class="re-upd"><div class="re-upd-row"><span class="re-chip">' + esc(src) + "</span>" + sc +
      '<span class="re-sp"></span><button type="button" class="re-btn pri" data-upd-now>' + ic("sparkles") + esc(tw("re.upd.now")) + "</button>" +
      infoPair(esc(tw("re.upd.info")), tw("re.upd.how")) + "</div></div>";
  }

  function askPrompt(data, st, lg) {
    if (st.region === "compare") return tw("re.ask_prompt_compare");
    var r = (data.regions || []).filter(function (x) { return x.id === st.region; })[0];
    return tw("re.ask_prompt", { region: r ? pick(r.name, lg) : "", period: r ? r.as_of || "" : "" });
  }

  // ---------- mount ----------

  var _st = null, _el = null, _data = null, _onResize = null, _tip = null;

  function readPref() {
    try { return JSON.parse(localStorage.getItem("javis.realestate") || "{}") || {}; } catch (e) { return {}; }
  }
  function savePref() {
    try { localStorage.setItem("javis.realestate", JSON.stringify({ region: _st.region, span: _st.span })); } catch (e) {}
  }

  function drawCharts() {
    if (!_el || !_data) return;
    var lg = lang();
    Array.prototype.forEach.call(_el.querySelectorAll(".re-chart"), function (box) {
      var lines, band = null;
      if (box.getAttribute("data-chart") === "compare") {
        var keys = compareKeys(_data.regions || []);
        var key = keys.indexOf(_st.cmpKey) >= 0 ? _st.cmpKey : keys[0];
        lines = compareLines(_data.regions || [], key, lg);
      } else {
        var r = (_data.regions || []).filter(function (x) { return x.id === _st.region; })[0];
        lines = r ? seriesLines(r, lg) : [];
        band = [NOW_YEAR - _st.span, NOW_YEAR];
      }
      var w = Math.floor(box.clientWidth || 720);
      var c = chartSvg(lines, { width: w, height: w < 520 ? 230 : 280, band: band, label: tw("re.chart_aria") });
      box.innerHTML = c.svg;
      wireHover(box, c, lines);
    });
  }

  function wireHover(box, c, lines) {
    var svg = box.querySelector("svg");
    var hit = svg && svg.querySelector(".re-hit");
    if (!hit) return;
    var cross = svg.querySelector(".re-cross"), dots = svg.querySelector(".re-dots");
    function hide() { cross.style.display = "none"; dots.innerHTML = ""; if (_tip) _tip.style.display = "none"; }
    function show(ev) {
      var rect = svg.getBoundingClientRect();
      var px = (ev.clientX - rect.left) * (c.W / rect.width);
      var yr = Math.round(c.x0 + (px - c.m.l) / (c.W - c.m.l - c.m.r) * (c.x1 - c.x0));
      yr = Math.max(c.x0, Math.min(c.x1, yr));
      var x = c.X(yr);
      cross.setAttribute("x1", x); cross.setAttribute("x2", x); cross.style.display = "";
      var rows = [], dh = "";
      lines.forEach(function (s) {
        var p = (s.points || []).filter(function (q) { return q[0] === yr; })[0];
        var v = p ? p[1] : null;
        if (v != null) dh += '<circle class="re-dot re-s' + s.slot + '" cx="' + x.toFixed(1) + '" cy="' + c.Y(v).toFixed(1) + '" r="4.5"/>';
        rows.push('<div class="re-tip-r"><i class="re-sw re-s' + s.slot + '"></i><span>' + esc(s.name) + "</span><b>" + esc(v == null ? tw("re.no_data") : fmtNum(v)) + "</b></div>");
      });
      dots.innerHTML = dh;
      if (!_tip) { _tip = document.createElement("div"); _tip.className = "re-tip"; document.body.appendChild(_tip); }
      _tip.innerHTML = '<div class="re-tip-y">' + yr + "</div>" + rows.join("");
      _tip.style.display = "block";
      var tx = ev.clientX + 14, ty = ev.clientY + 14;
      var tr = _tip.getBoundingClientRect();
      if (tx + tr.width > window.innerWidth - 8) tx = ev.clientX - tr.width - 14;
      if (ty + tr.height > window.innerHeight - 8) ty = ev.clientY - tr.height - 14;
      _tip.style.left = Math.max(8, tx) + "px"; _tip.style.top = Math.max(8, ty) + "px";
    }
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerdown", show);
    hit.addEventListener("pointerleave", hide);
  }

  function render() {
    if (!_el || !_data) return;
    _el.innerHTML = pageHtml(_data, _st);
    drawCharts();
  }

  function onClick(e) {
    var t = e.target.closest ? e.target.closest("button") : null;
    if (!t || !_el.contains(t)) return;
    if (t.hasAttribute("data-region")) {
      _st.region = t.getAttribute("data-region"); savePref(); render();
      var top = _el.querySelector(".re-root"); if (top && top.scrollIntoView && t.closest(".re-cmpcol")) top.scrollIntoView({ block: "start" });
    } else if (t.hasAttribute("data-span")) {
      _st.span = +t.getAttribute("data-span"); savePref();
      var r = (_data.regions || []).filter(function (x) { return x.id === _st.region; })[0];
      var box = _el.querySelector(".re-period");
      if (r && box) box.innerHTML = periodBlock(r, _st.span, lang());
      drawCharts();
    } else if (t.hasAttribute("data-sort")) {
      _st.sort = t.getAttribute("data-sort");
      var rr = (_data.regions || []).filter(function (x) { return x.id === _st.region; })[0];
      var ab = _el.querySelector("[data-areas]");
      if (rr && ab) ab.innerHTML = subareaList(rr, _st.sort, lang());
    } else if (t.hasAttribute("data-cmpkey")) {
      _st.cmpKey = t.getAttribute("data-cmpkey"); render();
    } else if (t.hasAttribute("data-ask")) {
      askJavis(askPrompt(_data, _st, lang()));
    } else if (t.hasAttribute("data-upd")) {
      _st.updOpen = !_st.updOpen;
      render();
      if (_st.updOpen) loadSched();
    } else if (t.hasAttribute("data-upd-now")) {
      askJavis(tw("re.upd.prompt"));
    } else if (t.hasAttribute("data-upd-sched")) {
      makeSched(t);
    } else if (t.hasAttribute("data-upd-unsched")) {
      dropSched(t.getAttribute("data-upd-unsched"));
    } else if (t.hasAttribute("data-upd-preview")) {
      _st.preview = !_st.preview;
      loadData(_el);
    } else if (t.hasAttribute("data-upd-approve")) {
      if (!confirm(tw("re.upd.approve_confirm"))) return;
      post("/realestate/approve").then(function () { _st.preview = false; loadData(_el); });
    } else if (t.hasAttribute("data-upd-discard")) {
      if (!confirm(tw("re.upd.discard_confirm"))) return;
      post("/realestate/discard").then(function () { _st.preview = false; loadData(_el); });
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
  // The quarterly job is an ordinary reminder (Tasks page, Recurring list), found again by the tool name in its text.
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
    post("/reminders", { text: tw("re.upd.prompt"), cron: UPD_CRON, mode: "task", label: tw("re.upd.label"), brain: brainPath(),
      created_by: "user", allow_no_channel: true, muc_quyen: "auto" }).then(function (r) {
      if (!r || !r.ok) { btn.disabled = false; alert((r && r.error) || tw("re.load_error")); return; }
      loadSched();
    });
  }
  function dropSched(id) {
    var f = new FormData();
    f.append("id", id);
    f.append("brain", brainPath());
    fetch("/reminders/cancel", { method: "POST", body: f }).then(function () { loadSched(); });
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
      _data = d || { regions: [] };
      var ids = (_data.regions || []).map(function (x) { return x.id; });
      if (_st.region !== "compare" && ids.indexOf(_st.region) < 0) _st.region = ids[0] || "compare";
      render();
    }).catch(function () {
      if (_el !== el) return;
      el.innerHTML = '<div class="re-root"><div class="re-err">' + ic("triangle-alert") + esc(tw("re.load_error")) + "</div></div>";
    });
  }

  // Opens the chat with the prompt typed in, not sent: the owner may want to add a district or a budget first.
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
    _st = { region: pref.region || "", span: SPANS.indexOf(+pref.span) >= 0 ? +pref.span : 10, sort: "potential", cmpKey: "",
      updOpen: false, preview: false, meta: null, sched: null };
    el.innerHTML = '<div class="re-root"><div class="re-muted">' + esc(tw("common.loading")) + "</div></div>";
    el.addEventListener("click", onClick);
    var timer = null;
    _onResize = function () { clearTimeout(timer); timer = setTimeout(drawCharts, 120); };
    window.addEventListener("resize", _onResize);
    return loadData(el);
  }

  function unmount() {
    if (_el) _el.removeEventListener("click", onClick);
    if (_onResize) window.removeEventListener("resize", _onResize);
    if (_tip && _tip.parentNode) _tip.parentNode.removeChild(_tip);
    _el = null; _data = null; _tip = null; _onResize = null;
  }

  var api = {
    mount: mount, unmount: unmount,
    // pure helpers, for tests
    _pick: pick, _spanChange: spanChange, _windowEnds: windowEnds, _chartSvg: chartSvg, _pageHtml: pageHtml,
    _compareKeys: compareKeys, _askPrompt: askPrompt, SPANS: SPANS,
  };
  if (typeof window !== "undefined") window.JavisRealEstate = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
