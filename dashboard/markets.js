/* Markets page: Vietnam stocks, world markets, crypto and a technical outlook.
 *
 * Data comes from the server (/market/*, server/market_data.py), which pulls public sources and computes the
 * indicators. This file only draws: tabs, sortable tables, a treemap heatmap, gauges, a scatter "opportunity map"
 * and a detail dialog with a candlestick chart (SMA, Bollinger, volume, RSI, MACD) and a crosshair tooltip.
 * Charts are hand-written SVG so the page needs no chart library. Every visible string goes through t().
 *
 * window.JavisMarkets = { mount(el), unmount() } - console.js calls these from renderPage("markets"). */
(function () {
  "use strict";

  var T = function (k, v) { return typeof window.t === "function" ? window.t(k, v) : k; };
  var IC = function (n) { return typeof window.ic === "function" ? window.ic(n) : ""; };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function infoBody(html) { return window.JavisInfo ? window.JavisInfo.body(html) : '<div class="mk-note">' + html + "</div>"; }
  function infoBtn(label) { return window.JavisInfo ? window.JavisInfo.btn(label) : ""; }

  var TABS = [
    { id: "overview", icon: "layout-dashboard" }, { id: "vn", icon: "flag" }, { id: "world", icon: "globe" },
    { id: "crypto", icon: "bitcoin" }, { id: "outlook", icon: "telescope" }, { id: "paper", icon: "target" },
  ];
  var MARKETS = ["vn", "world", "crypto"];
  var LIVE_MS = 5000;
  var LS_TAB = "javis.markets.tab";

  var S = {
    el: null, tab: "overview", data: {}, err: {}, busy: {}, timer: null, gen: 0,
    sort: { vn: ["value", -1], world: ["chg_1d", -1], crypto: ["rank", 1] },
    q: { vn: "", world: "", crypto: "" }, filter: { vn: "all", world: "all", crypto: "all" },
    watchOnly: { vn: false, world: false, crypto: false }, outlook: "vn", ro: null, tip: null, modal: null,
    liveBusy: false, liveOk: false, bg: null, acc: {},
    ppKind: "vn", pp: {}, ppSim: {}, ppOpen: {},
  };

  // ------------------------------------------------------------------ formatting
  function loc() { var l = (document.documentElement.lang || "vi").toLowerCase(); return l.indexOf("vi") === 0 ? "vi-VN" : "en-US"; }
  function fin(v) { return typeof v === "number" && isFinite(v); }
  function num(v, nd) {
    if (!fin(v)) return "-";
    return new Intl.NumberFormat(loc(), { minimumFractionDigits: nd, maximumFractionDigits: nd }).format(v);
  }
  function price(v) {
    if (!fin(v)) return "-";
    var a = Math.abs(v);
    if (a >= 100000) return num(v, 0);
    if (a >= 1) return num(v, 2);
    if (a >= 0.01) return num(v, 4);
    return new Intl.NumberFormat(loc(), { maximumSignificantDigits: 4 }).format(v);
  }
  function pct(v, nd) { if (!fin(v)) return "-"; return (v > 0 ? "+" : "") + num(v, nd == null ? 2 : nd) + "%"; }
  function compact(v) {
    if (!fin(v)) return "-";
    return new Intl.NumberFormat(loc(), { notation: "compact", maximumFractionDigits: 2 }).format(v);
  }
  function dir(v) { return !fin(v) || Math.abs(v) < 0.005 ? "flat" : (v > 0 ? "up" : "down"); }
  function arrow(v) { var d = dir(v); return d === "up" ? "▲" : (d === "down" ? "▼" : "■"); }
  function chg(v) { return '<span class="mk-' + dir(v) + ' mk-num">' + arrow(v) + " " + pct(v) + "</span>"; }
  // Cells the live poll updates in place: data-lp holds a price, data-lc a % change, both keyed "kind|id".
  function lp(key, v) { return '<span data-lp="' + esc(key) + '">' + price(v) + "</span>"; }
  function lc(key, v, extra) {
    return '<span data-lc="' + esc(key) + '" class="' + (extra || "") + " mk-num mk-" + dir(v) + '">' + arrow(v) + " " + pct(v) + "</span>";
  }
  function scorePill(s) {
    if (!fin(s)) return '<span class="mk-muted">-</span>';
    var d = s >= 20 ? "up" : (s <= -20 ? "down" : "flat");
    return '<span class="mk-pill ' + d + '" title="' + esc(T("mk.sig." + sigOf(s))) + '">' + (s > 0 ? "+" : "") + Math.round(s) + "</span>";
  }
  function sigOf(s) { return s >= 50 ? "strong_pos" : s >= 20 ? "pos" : s > -20 ? "neutral" : s > -50 ? "neg" : "strong_neg"; }
  function moveBar(m) {
    if (!fin(m)) return "-";
    return '<span class="mk-bar-mini" title="' + esc(T("mk.col.move")) + " " + m + '/100"><i style="width:' + Math.max(3, m) + '%"></i></span> <span class="mk-num">' + m + "</span>";
  }
  function ago(ts) {
    if (!ts) return "";
    var m = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
    return m < 1 ? T("mk.just_now") : T("mk.min_ago", { n: m });
  }
  function dateOf(ts) {
    try { return new Date(ts * 1000).toLocaleDateString(loc(), { day: "2-digit", month: "2-digit", year: "numeric" }); } catch (e) { return ""; }
  }
  function reasonChips(rs) {
    return (rs || []).map(function (r) {
      var good = ["above_sma200", "golden_cross", "macd_bull_cross", "volume_up", "near_52w_high", "rsi_oversold"].indexOf(r) >= 0;
      var bad = ["below_sma200", "death_cross", "macd_bear_cross", "volume_down", "near_52w_low", "rsi_overbought"].indexOf(r) >= 0;
      return '<span class="mk-chip ' + (good ? "up" : bad ? "down" : "") + '">' + esc(T("mk.reason." + r)) + "</span>";
    }).join("");
  }
  function nameOf(r) {
    if (r.sector) return T("mk.sector." + r.sector);
    return r.name && r.name !== r.symbol ? r.name : "";
  }
  function symLabel(kind, r) {
    if (kind === "crypto") return r.symbol || (r.id || "").toUpperCase();
    return r.symbol;
  }

  // ------------------------------------------------------------------ data
  function api(url, opts) {
    return fetch(url, opts).then(function (r) { return r.json().catch(function () { return { ok: false }; }); });
  }
  function load(name, force) {
    if (S.busy[name]) return S.busy[name];
    if (!force && S.data[name]) return Promise.resolve(S.data[name]);
    var url = name === "overview" ? "/market/overview" : "/market/section?name=" + name;
    var p = api(url).then(function (d) {
      delete S.busy[name];
      if (!d || d.ok === false) { S.err[name] = (d && d.error) || T("mk.err.load"); return null; }
      delete S.err[name];
      S.data[name] = d;
      return d;
    }).catch(function () { delete S.busy[name]; S.err[name] = T("mk.err.load"); return null; });
    S.busy[name] = p;
    return p;
  }
  function needs(tab) {
    if (tab === "paper") return [];
    if (tab === "overview") return ["overview"];
    if (tab === "outlook") return ["overview", S.outlook];
    return [tab];
  }
  function refresh(force) {
    var gen = S.gen;
    var names = needs(S.tab);
    setSpin(true);
    return Promise.all(names.map(function (n) { return load(n, force); })).then(function () {
      setSpin(false);
      if (gen === S.gen) drawBody();
    });
  }
  function hardRefresh() {
    setSpin(true);
    api("/market/refresh", { method: "POST" }).finally(function () { S.data = {}; refresh(true); });
  }

  // ------------------------------------------------------------------ shell
  function mount(el) {
    S.el = el;
    S.gen++;
    try { var t0 = localStorage.getItem(LS_TAB); if (t0 && TABS.some(function (x) { return x.id === t0; })) S.tab = t0; } catch (e) {}
    el.innerHTML = '<div class="mk-root">' + barHtml() + '<div id="mkBody"></div></div>';
    el.querySelector(".mk-bar").addEventListener("click", onBar);
    el.querySelector("#mkBody").addEventListener("click", onBody);
    el.querySelector("#mkBody").addEventListener("input", onInput);
    el.querySelector("#mkBody").addEventListener("change", onInput);
    drawBody();
    refresh(false);
    loadBg();
    clearInterval(S.timer);
    S.timer = setInterval(pollLive, LIVE_MS);
  }
  function unmount() {
    S.gen++;
    clearInterval(S.timer); S.timer = null;
    closeModal(); hideTip();
    if (S.ro) { try { S.ro.disconnect(); } catch (e) {} S.ro = null; }
    S.el = null;
  }
  function barHtml() {
    var tabs = TABS.map(function (x) {
      return '<button type="button" class="mk-segb' + (x.id === S.tab ? " on" : "") + '" data-tab="' + x.id + '">' + IC(x.icon) +
        "<span>" + esc(T("mk.tab." + x.id)) + "</span></button>";
    }).join("");
    return '<div class="mk-bar"><div class="mk-seg" role="tablist">' + tabs + '</div><span class="mk-sp"></span>' +
      '<span class="mk-live" id="mkLive" title="' + esc(T("mk.live_tip")) + '"><i></i>' + esc(T("mk.live")) + "</span>" +
      '<span class="mk-stamp" id="mkStamp"></span>' +
      '<button type="button" class="mk-btn ghost" data-act="bg" id="mkBg" aria-pressed="false" title="' + esc(T("mk.bg_tip")) + '">' + IC("activity") +
      '<span>' + esc(T("mk.bg")) + '</span><span class="mk-chip" id="mkBgState">-</span></button>' +
      '<button type="button" class="mk-btn ghost" data-act="refresh" title="' + esc(T("mk.refresh")) + '">' + IC("refresh-cw") +
      "<span>" + esc(T("mk.refresh")) + "</span></button>" + infoBtn(T("mk.about")) +
      infoBody(esc(T("mk.info.sources")) + "<br><br>" + esc(T("mk.info.bg")) + "<br><br>" + esc(T("mk.info.disclaimer"))) + "</div>";
  }
  function setSpin(on) {
    var b = S.el && S.el.querySelector('[data-act="refresh"]');
    if (b) b.classList.toggle("spin", !!on);
  }
  function setStamp(at, stale) {
    var s = S.el && S.el.querySelector("#mkStamp");
    if (!s) return;
    s.textContent = at ? T("mk.updated", { t: ago(at) }) + (stale ? " · " + T("mk.stale") : "") : "";
    s.classList.toggle("stale", !!stale);
  }
  function onBar(e) {
    var b = e.target.closest("[data-tab],[data-act]");
    if (!b) return;
    if (b.dataset.tab) {
      S.tab = b.dataset.tab;
      try { localStorage.setItem(LS_TAB, S.tab); } catch (err) {}
      S.el.querySelectorAll(".mk-bar [data-tab]").forEach(function (x) { x.classList.toggle("on", x.dataset.tab === S.tab); });
      S.gen++;
      drawBody();
      refresh(false);
    } else if (b.dataset.act === "bg") {
      toggleBg();
    } else if (b.dataset.act === "refresh") {
      hardRefresh();
    }
  }
  function body() { return S.el && S.el.querySelector("#mkBody"); }

  function drawBody() {
    var b = body();
    if (!b) return;
    hideTip();
    if (S.ro) { try { S.ro.disconnect(); } catch (e) {} S.ro = null; }
    var names = needs(S.tab);
    var missing = names.filter(function (n) { return !S.data[n]; });
    if (missing.length) {
      var err = missing.map(function (n) { return S.err[n]; }).filter(Boolean)[0];
      b.innerHTML = err ? '<div class="mk-err">' + IC("triangle-alert") + " " + esc(err) +
        ' <button type="button" class="mk-btn" data-act="retry">' + esc(T("mk.retry")) + "</button></div>"
        : '<div class="mk-grid mk-g3"><div class="mk-skel"></div><div class="mk-skel"></div><div class="mk-skel"></div></div>' +
          '<div class="mk-skel mk-sec" style="height:260px"></div><p class="mk-muted">' + esc(T("mk.loading")) + "</p>";
      return;
    }
    var html = "";
    if (S.tab === "overview") html = viewOverview(S.data.overview);
    else if (S.tab === "vn") html = viewVN(S.data.vn);
    else if (S.tab === "world") html = viewWorld(S.data.world);
    else if (S.tab === "crypto") html = viewCrypto(S.data.crypto);
    else if (S.tab === "paper") html = viewPaper();
    else html = viewOutlook(S.data.overview, S.data[S.outlook]);
    b.innerHTML = html;
    if (S.tab === "paper") { setStamp(0); drawPaper(); return; }
    var d = S.tab === "overview" || S.tab === "outlook" ? S.data.overview : S.data[S.tab];
    var stale = false;
    if (d && d.sections) MARKETS.forEach(function (m) { if (d.sections[m] && d.sections[m].stale) stale = true; });
    setStamp(d && d.at, stale || (d && d.stale));
    afterDraw(b);
  }

  // Charts that need the real width (treemaps, scatter) draw after the HTML is in the page, and again on resize.
  function afterDraw(b) {
    var heats = b.querySelectorAll("[data-heat]");
    var scat = b.querySelector("[data-scatter]");
    b.querySelectorAll("[data-acc]").forEach(drawAcc);
    function paint() {
      heats.forEach(function (h) { drawHeat(h); });
      if (scat) drawScatter(scat);
    }
    paint();
    if ((heats.length || scat) && typeof ResizeObserver === "function") {
      var w0 = b.clientWidth;
      S.ro = new ResizeObserver(function () { if (Math.abs(b.clientWidth - w0) > 8) { w0 = b.clientWidth; paint(); } });
      S.ro.observe(b);
    }
  }

  // ------------------------------------------------------------------ small charts
  function spark(vals, w, h) {
    var v = (vals || []).filter(fin);
    if (v.length < 2) return '<svg width="' + w + '" height="' + h + '"></svg>';
    var mn = Math.min.apply(null, v), mx = Math.max.apply(null, v), rg = mx - mn || 1;
    var pts = v.map(function (x, i) { return [(i / (v.length - 1)) * (w - 2) + 1, h - 2 - ((x - mn) / rg) * (h - 4)]; });
    var col = v[v.length - 1] >= v[0] ? "var(--mk-up)" : "var(--mk-down)";
    var line = pts.map(function (p) { return p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ");
    var area = "M" + pts[0][0].toFixed(1) + "," + h + " L" + line.replace(/ /g, " L") + " L" + pts[pts.length - 1][0].toFixed(1) + "," + h + " Z";
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" aria-hidden="true">' +
      '<path d="' + area + '" style="fill:' + col + ';opacity:.12"/>' +
      '<polyline points="' + line + '" vector-effect="non-scaling-stroke" style="fill:none;stroke:' + col + ';stroke-width:1.6;stroke-linejoin:round;stroke-linecap:round"/></svg>';
  }

  // Semicircle gauge for a -100..100 score, five zones with 2px gaps.
  function gauge(score, size) {
    size = size || 132;
    var cx = size / 2, cy = size * 0.56, r = size * 0.4, sw = size * 0.085;
    function pt(deg, rr) { var a = deg * Math.PI / 180; return [cx + rr * Math.cos(a), cy - rr * Math.sin(a)]; }
    function arc(a0, a1) {
      var p0 = pt(a0, r), p1 = pt(a1, r);
      return "M" + p0[0].toFixed(2) + "," + p0[1].toFixed(2) + " A" + r + "," + r + " 0 0 1 " + p1[0].toFixed(2) + "," + p1[1].toFixed(2);
    }
    function ang(s) { return 180 - ((s + 100) / 200) * 180; }
    var zones = [[-100, -50, "var(--mk-down)"], [-50, -20, "color-mix(in srgb, var(--mk-down) 45%, var(--mk-neutral))"],
      [-20, 20, "var(--mk-neutral)"], [20, 50, "color-mix(in srgb, var(--mk-up) 45%, var(--mk-neutral))"], [50, 100, "var(--mk-up)"]];
    var segs = zones.map(function (z) {
      return '<path d="' + arc(ang(z[0]) - 1.2, ang(z[1]) + 1.2) + '" style="fill:none;stroke:' + z[2] + ';stroke-width:' + sw + '"/>';
    }).join("");
    var s = fin(score) ? Math.max(-100, Math.min(100, score)) : 0;
    var tip = pt(ang(s), r - sw * 0.2);
    var needle = '<line x1="' + cx + '" y1="' + cy + '" x2="' + tip[0].toFixed(2) + '" y2="' + tip[1].toFixed(2) +
      '" style="stroke:var(--text);stroke-width:2.5;stroke-linecap:round"/><circle cx="' + cx + '" cy="' + cy + '" r="4" style="fill:var(--text)"/>';
    var txt = '<text x="' + cx + '" y="' + (cy + size * 0.2) + '" text-anchor="middle" style="font-size:' + (size * 0.15) +
      'px;font-weight:700;fill:var(--text)">' + (fin(score) ? (score > 0 ? "+" : "") + Math.round(score) : "-") + "</text>";
    return '<svg class="mk-gauge" width="' + size + '" height="' + (size * 0.82) + '" viewBox="0 0 ' + size + " " + (size * 0.82) +
      '" role="img" aria-label="' + esc(T("mk.score")) + " " + (fin(score) ? Math.round(score) : "") + '">' + segs + needle + txt + "</svg>";
  }

  function breadthBar(up, down) {
    var tot = (up || 0) + (down || 0);
    if (!tot) return "";
    var u = Math.round(up / tot * 100);
    return '<div class="mk-breadth" title="' + esc(T("mk.adv_dec", { up: up, down: down })) + '"><i style="width:' + u +
      '%;background:var(--mk-up)"></i><i style="width:' + (100 - u) + '%;background:var(--mk-down)"></i></div>' +
      '<div class="mk-breadth-l"><span>▲ ' + up + " " + esc(T("mk.advancers")) + "</span><span>" + esc(T("mk.decliners")) + " " + down + " ▼</span></div>";
  }

  // ------------------------------------------------------------------ regime card
  function regimeCard(mk, sec) {
    var r = (sec && sec.regime) || {};
    var lbl = r.label || "unknown";
    var col = lbl === "risk_on" ? "mk-up" : lbl === "risk_off" ? "mk-down" : "mk-flat";
    var kv = [
      [T("mk.breadth50"), fin(r.breadth50) ? r.breadth50 + "%" : "-"],
      [T("mk.breadth200"), fin(r.breadth200) ? r.breadth200 + "%" : "-"],
      [T("mk.hot"), fin(r.hot) ? String(r.hot) : "-"],
    ];
    if (fin(r.vix)) kv.push(["VIX · " + T("mk.vix." + r.vix_level), num(r.vix, 2)]);
    if (fin(r.fng)) kv.push([T("mk.fng") + " · " + T("mk.fng_l." + fngKey(r.fng)), String(r.fng)]);
    if (r.vol_trend) kv.push([T("mk.vol_trend"), T("mk.voltrend." + r.vol_trend)]);
    return '<div class="mk-card"><div class="mk-reg"><div class="mk-reg-name">' + IC(TABS.filter(function (x) { return x.id === mk; })[0].icon) +
      esc(T("mk.tab." + mk)) + '<span class="mk-sp"></span><button type="button" class="mk-btn ghost" data-go="' + mk + '">' + IC("chevron-right") +
      "</button></div><div>" + gauge(r.score) + '</div><div><div class="mk-reg-lbl ' + col + '">' + esc(T("mk.regime." + lbl)) +
      '</div><div class="mk-reg-kv">' + kv.map(function (p) { return "<span>" + esc(p[0]) + "</span><b>" + esc(p[1]) + "</b>"; }).join("") +
      "</div></div>" + breadthBar(r.advancers, r.decliners) + "</div></div>";
  }
  function fngKey(v) { return v <= 24 ? "xfear" : v <= 44 ? "fear" : v <= 55 ? "neutral" : v <= 75 ? "greed" : "xgreed"; }

  function tile(kind, r, sub) {
    var key = kind + "|" + (r.id || r.symbol);
    return '<button type="button" class="mk-tile" data-open="' + esc(key) + '"><span class="mk-tile-n">' +
      esc(sub || r.name || r.symbol) + '</span><span class="mk-tile-p">' + lp(key, r.price) + "</span>" + lc(key, r.chg_1d, "mk-tile-c") +
      spark(r.spark, 150, 28) + "</button>";
  }

  // ------------------------------------------------------------------ overview
  function viewOverview(d) {
    var s = d.sections || {};
    var html = '<div class="mk-grid mk-g3">' + MARKETS.map(function (m) {
      return s[m] && !s[m].error ? regimeCard(m, s[m]) : '<div class="mk-card mk-err">' + esc(T("mk.tab." + m)) + ": " + esc(T("mk.err.load")) + "</div>";
    }).join("") + "</div>";
    var tiles = [];
    (s.vn && s.vn.indices || []).slice(0, 4).forEach(function (i) { tiles.push(tile("vn", i, i.name)); });
    (s.world && s.world.key || []).forEach(function (r) { tiles.push(tile("world", r)); });
    (s.crypto && s.crypto.key || []).slice(0, 4).forEach(function (r) { tiles.push(tile("crypto", r, r.name)); });
    html += '<div class="mk-sec"><div class="mk-tiles">' + tiles.join("") + "</div></div>";

    html += '<div class="mk-grid mk-g3 mk-sec">' + MARKETS.map(function (m) {
      var x = s[m] || {};
      return '<div class="mk-card"><h3>' + esc(T("mk.movers_of", { m: T("mk.tab." + m) })) + "</h3>" +
        moversTable(m, x.top_up || [], x.top_down || []) + "</div>";
    }).join("") + "</div>";

    var pot = [];
    MARKETS.forEach(function (m) { ((s[m] && s[m].outlook && s[m].outlook.potential) || []).slice(0, 4).forEach(function (r) { pot.push([m, r]); }); });
    var mov = [];
    MARKETS.forEach(function (m) { ((s[m] && s[m].outlook && s[m].outlook.movers) || []).slice(0, 4).forEach(function (r) { mov.push([m, r]); }); });
    html += '<div class="mk-grid mk-g2 mk-sec"><div class="mk-card"><h3>' + IC("trending-up") + esc(T("mk.list.potential")) +
      '<span class="mk-sp"></span><button type="button" class="mk-btn ghost" data-go="outlook">' + esc(T("mk.see_all")) + "</button></h3>" +
      listItems(pot) + '</div><div class="mk-card"><h3>' + IC("zap") + esc(T("mk.list.movers")) +
      '<span class="mk-sp"></span><button type="button" class="mk-btn ghost" data-go="outlook">' + esc(T("mk.see_all")) + "</button></h3>" +
      listItems(mov) + "</div></div>";

    if (s.vn && s.vn.sectors) {
      html += '<div class="mk-card mk-sec"><h3>' + esc(T("mk.sectors_vn")) + '<span class="mk-sub">' + esc(T("mk.chg_1d_avg")) + "</span></h3>" +
        sectorBars(s.vn.sectors) + "</div>";
    }
    html += '<p class="mk-note">' + IC("info") + esc(T("mk.disclaimer_short")) + "</p>";
    return html;
  }
  function moversTable(kind, up, down) {
    function half(r) {
      if (!r) return '<td colspan="2"></td>';
      return '<td class="l" data-open="' + kind + "|" + esc(r.id || r.symbol) + '" title="' + esc(price(r.price)) + '"><b>' + esc(symLabel(kind, r)) +
        '</b></td><td data-open="' + kind + "|" + esc(r.id || r.symbol) + '">' + lc(kind + "|" + (r.id || r.symbol), r.chg_1d) + "</td>";
    }
    if (!up.length && !down.length) return '<div class="mk-empty">' + esc(T("mk.empty")) + "</div>";
    var out = [];
    for (var i = 0; i < 5; i++) out.push("<tr>" + half(up[i]) + half(down[i]) + "</tr>");
    return '<table class="mk-tbl mk-movers"><tbody>' + out.join("") + "</tbody></table>";
  }
  function sectorBars(secs) {
    var list = secs.filter(function (x) { return fin(x.chg_1d); }).slice().sort(function (a, b) { return b.chg_1d - a.chg_1d; });
    if (!list.length) return '<div class="mk-empty">' + esc(T("mk.empty")) + "</div>";
    var mx = Math.max(0.5, Math.max.apply(null, list.map(function (x) { return Math.abs(x.chg_1d); })));
    var rowH = 26, lw = 128, W = 640, rw = 70, mid = lw + (W - lw - rw) / 2, half = (W - lw - rw) / 2 - 4;
    var H = list.length * rowH + 4;
    var g = list.map(function (x, i) {
      var y = i * rowH + 4, w = Math.abs(x.chg_1d) / mx * half, up = x.chg_1d >= 0;
      var bx = up ? mid : mid - w;
      return '<g data-tipk="sector" data-i="' + i + '"><text x="' + (lw - 8) + '" y="' + (y + 15) + '" text-anchor="end" style="fill:var(--text2);font-size:12px">' +
        esc(T("mk.sector." + x.sector)) + '</text><rect x="' + bx.toFixed(1) + '" y="' + (y + 4) + '" width="' + Math.max(1, w).toFixed(1) + '" height="' + (rowH - 10) +
        '" rx="4" style="fill:' + (up ? "var(--mk-up)" : "var(--mk-down)") + '"/><text x="' + (W - 4) + '" y="' + (y + 15) + '" text-anchor="end" style="fill:var(--text);font-size:12px">' +
        pct(x.chg_1d) + "</text></g>";
    }).join("");
    return '<svg class="mk-chart" viewBox="0 0 ' + W + " " + H + '" style="max-height:' + (H + 10) + 'px"><line class="grid" x1="' + mid + '" x2="' + mid + '" y1="0" y2="' + H + '"/>' + g + "</svg>";
  }
  function listItems(items) {
    if (!items.length) return '<div class="mk-empty">' + esc(T("mk.list.none")) + "</div>";
    return '<div class="mk-list">' + items.map(function (p) {
      var m = p[0], r = p[1];
      var rng = r.range_5d && fin(r.range_5d[0]) ? price(r.range_5d[0]) + " - " + price(r.range_5d[1]) : "";
      return '<div class="mk-item" data-open="' + m + "|" + esc(r.id || r.symbol) + '"><div class="mk-item-h">' +
        (r.image ? '<img src="' + esc(r.image) + '" width="18" height="18" alt="" loading="lazy">' : "") + "<b>" + esc(symLabel(m, r)) + "</b><small>" +
        esc(T("mk.tab." + m)) + (nameOf(r) ? " · " + esc(nameOf(r)) : "") + '</small></div><div class="mk-item-r">' + price(r.price) + " " + chg(r.chg_1d) +
        '</div><div class="mk-item-h" style="gap:10px;flex-wrap:wrap"><span class="mk-kicker">' + esc(T("mk.score")) + "</span>" + scorePill(r.score) +
        '<span class="mk-kicker">' + esc(T("mk.col.move")) + "</span>" + moveBar(r.move_score) +
        '</div><div class="mk-item-r mk-kicker">' + (fin(r.exp_move_5d) ? esc(T("mk.exp5", { m: num(r.exp_move_5d, 1) })) : "") +
        (rng ? "<br>" + rng : "") + '</div><div class="mk-chips">' + reasonChips(r.reasons) + "</div></div>";
    }).join("") + "</div>";
  }

  // ------------------------------------------------------------------ tables
  var COLS = {
    vn: [
      ["watch", "", "c"], ["symbol", "mk.col.symbol", "l"], ["sector", "mk.col.sector", "l"], ["price", "mk.col.price_k"],
      ["chg_1d", "mk.col.d1"], ["chg_5d", "mk.col.w1"], ["chg_1m", "mk.col.m1"], ["chg_3m", "mk.col.m3"],
      ["value", "mk.col.value_bn"], ["vol_ratio", "mk.col.vol_ratio"], ["rsi", "RSI"], ["score", "mk.col.score"],
      ["move_score", "mk.col.move"], ["exp_move_5d", "mk.col.exp5"], ["spark", "mk.col.chart", "c"],
    ],
    world: [
      ["watch", "", "c"], ["symbol", "mk.col.symbol", "l"], ["group", "mk.col.group", "l"], ["price", "mk.col.price"],
      ["chg_1d", "mk.col.d1"], ["chg_5d", "mk.col.w1"], ["chg_1m", "mk.col.m1"], ["chg_3m", "mk.col.m3"], ["chg_1y", "mk.col.y1"],
      ["rsi", "RSI"], ["score", "mk.col.score"], ["move_score", "mk.col.move"], ["exp_move_5d", "mk.col.exp5"], ["spark", "mk.col.chart", "c"],
    ],
    crypto: [
      ["watch", "", "c"], ["rank", "#", "c"], ["symbol", "mk.col.coin", "l"], ["price", "mk.col.price_usd"], ["chg_1h", "1h"],
      ["chg_1d", "24h"], ["chg_5d", "7d"], ["chg_1m", "30d"], ["mcap", "mk.col.mcap"], ["volume_24h", "mk.col.vol24"],
      ["rsi", "RSI"], ["score", "mk.col.score"], ["move_score", "mk.col.move"], ["spark7d", "7d", "c"],
    ],
  };
  function cell(kind, key, r) {
    switch (key) {
      case "watch": return '<button type="button" class="mk-star' + (r.watch ? " on" : "") + '" data-star="' + kind + "|" + esc(r.id || r.symbol) +
        '" title="' + esc(T(r.watch ? "mk.unwatch" : "mk.watch")) + '">' + IC("star") + "</button>";
      case "symbol":
        return '<div class="mk-sym">' + (r.image ? '<img src="' + esc(r.image) + '" alt="" loading="lazy">' : "") + esc(symLabel(kind, r)) +
          (kind !== "vn" && r.name && r.name !== r.symbol ? "<small>" + esc(r.name) + "</small>" : "") + "</div>";
      case "sector": return '<span class="mk-muted">' + esc(T("mk.sector." + r.sector)) + "</span>";
      case "group": return '<span class="mk-muted">' + esc(T("mk.group." + r.group)) + " · " + esc(T("mk.region." + r.region)) + "</span>";
      case "price": return lp(kind + "|" + (r.id || r.symbol), r.price);
      case "chg_1d": return lc(kind + "|" + (r.id || r.symbol), r.chg_1d);
      case "chg_1h": case "chg_5d": case "chg_1m": case "chg_3m": case "chg_1y": return chg(r[key]);
      case "value": return fin(r.value) ? num(r.value / 1e6, 1) : "-";
      case "vol_ratio": return fin(r.vol_ratio) ? '<span class="' + (r.vol_ratio >= 1.5 ? "mk-flat" : "") + '">' + num(r.vol_ratio, 2) + "x</span>" : "-";
      case "rsi": return fin(r.rsi) ? '<span class="' + (r.rsi >= 70 ? "mk-down" : r.rsi <= 30 ? "mk-up" : "") + '">' + num(r.rsi, 0) + "</span>" : "-";
      case "score": return scorePill(r.score);
      case "move_score": return moveBar(r.move_score);
      case "exp_move_5d": return fin(r.exp_move_5d) ? "±" + num(r.exp_move_5d, 1) + "%" : "-";
      case "mcap": case "volume_24h": return compact(r[key]);
      case "rank": return r.rank || "";
      case "spark": return spark(r.spark, 90, 26);
      case "spark7d": return spark(r.spark7d || r.spark, 90, 26);
      default: return esc(r[key]);
    }
  }
  function sortRows(kind, rows) {
    var sk = S.sort[kind], key = sk[0], d = sk[1];
    return rows.slice().sort(function (a, b) {
      var x = a[key], y = b[key];
      if (key === "symbol" || key === "sector" || key === "group") return String(x || "").localeCompare(String(y || "")) * d;
      x = fin(x) ? x : -Infinity * d; y = fin(y) ? y : -Infinity * d;
      return (x - y) * d;
    });
  }
  function filterRows(kind, rows) {
    var q = (S.q[kind] || "").trim().toLowerCase();
    var f = S.filter[kind];
    return rows.filter(function (r) {
      if (S.watchOnly[kind] && !r.watch) return false;
      if (f !== "all") {
        if (kind === "vn" && r.sector !== f) return false;
        if (kind === "world" && r.group !== f) return false;
      }
      if (q) {
        var hay = [r.symbol, r.name, r.id, r.sector ? T("mk.sector." + r.sector) : ""].join(" ").toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
  }
  function tableHtml(kind, rows) {
    var cols = COLS[kind], sk = S.sort[kind];
    var head = cols.map(function (c) {
      var lab = c[1] ? (c[1].indexOf("mk.") === 0 ? T(c[1]) : c[1]) : "";
      var sorted = sk[0] === c[0];
      return '<th class="' + (c[2] || "") + (sorted ? " sorted" : "") + '" data-sort="' + kind + "|" + c[0] + '">' + esc(lab) +
        (sorted ? (sk[1] > 0 ? " ↑" : " ↓") : "") + "</th>";
    }).join("");
    var list = sortRows(kind, filterRows(kind, rows));
    var bodyRows = list.map(function (r) {
      return '<tr data-open="' + kind + "|" + esc(r.id || r.symbol) + '">' + cols.map(function (c) {
        return '<td class="' + (c[2] || "") + '">' + cell(kind, c[0], r) + "</td>";
      }).join("") + "</tr>";
    }).join("");
    return '<div class="mk-tblw"><table class="mk-tbl"><thead><tr>' + head + "</tr></thead><tbody>" +
      (bodyRows || '<tr><td colspan="' + cols.length + '" class="l mk-empty">' + esc(T("mk.empty")) + "</td></tr>") + "</tbody></table></div>" +
      '<p class="mk-note">' + esc(T("mk.rows_shown", { n: list.length, total: rows.length })) + "</p>";
  }
  function toolsHtml(kind, filters) {
    var seg = filters ? '<div class="mk-seg">' + filters.map(function (f) {
      return '<button type="button" class="mk-segb sm' + (S.filter[kind] === f[0] ? " on" : "") + '" data-filter="' + kind + "|" + f[0] + '">' + esc(f[1]) + "</button>";
    }).join("") + "</div>" : "";
    return '<div class="mk-tools"><input class="mk-input search" type="search" data-q="' + kind + '" value="' + esc(S.q[kind]) +
      '" placeholder="' + esc(T("mk.search")) + '">' + seg + '<label class="mk-chip" style="cursor:pointer"><input type="checkbox" data-watchonly="' + kind + '"' +
      (S.watchOnly[kind] ? " checked" : "") + "> " + esc(T("mk.watch_only")) + '</label><span class="mk-sp"></span>' +
      '<input class="mk-input" style="width:130px" data-addsym="' + kind + '" placeholder="' + esc(T("mk.add_ph." + kind)) + '">' +
      '<button type="button" class="mk-btn" data-add="' + kind + '">' + IC("plus") + "<span>" + esc(T("mk.add")) + "</span></button></div>";
  }

  // ------------------------------------------------------------------ Vietnam
  function viewVN(d) {
    var idx = (d.indices || []).map(function (i) { return tile("vn", i, i.name); }).join("");
    var secs = d.sectors || [];
    var filters = [["all", T("mk.all")]].concat(secs.map(function (s) { return [s.sector, T("mk.sector." + s.sector)]; }));
    return '<div class="mk-grid" style="grid-template-columns:minmax(0,1fr) minmax(0,2fr);align-items:start">' + regimeCard("vn", d) +
      '<div class="mk-tiles">' + idx + "</div></div>" +
      '<div class="mk-grid mk-g2 mk-sec"><div class="mk-card"><h3>' + esc(T("mk.heat_vn")) + '<span class="mk-sub">' + esc(T("mk.heat_vn_sub")) + "</span></h3>" +
      '<div class="mk-heat" data-heat="vn"></div>' + heatLegend(7) + '</div><div class="mk-card"><h3>' + esc(T("mk.sectors_vn")) +
      '<span class="mk-sub">' + esc(T("mk.chg_1d_avg")) + "</span></h3>" + sectorBars(secs) + "</div></div>" +
      '<div class="mk-sec">' + toolsHtml("vn", filters) + tableHtml("vn", d.rows || []) + "</div>";
  }
  function heatLegend(mx) {
    var steps = [-1, -0.6, -0.25, 0, 0.25, 0.6, 1];
    return '<div class="mk-legend"><span>' + pct(-mx, 0) + '</span><span class="mk-scale">' + steps.map(function (s) {
      return '<i style="background:' + heatColor(s * mx, mx) + '"></i>';
    }).join("") + "</span><span>" + pct(mx, 0) + "</span><span class=\"mk-muted\">" + esc(T("mk.heat_size")) + "</span></div>";
  }
  function heatColor(v, mx) {
    if (!fin(v)) return "var(--mk-neutral)";
    var k = Math.min(1, Math.abs(v) / mx);
    var p = Math.round(18 + k * 82);
    if (Math.abs(v) < 0.005) return "color-mix(in srgb, var(--mk-flat) 55%, var(--mk-neutral))";
    return "color-mix(in srgb, " + (v > 0 ? "var(--mk-up)" : "var(--mk-down)") + " " + p + "%, var(--mk-neutral))";
  }
  function squarify(items, W, H) {
    var total = items.reduce(function (s, i) { return s + i.w; }, 0);
    if (!total) return [];
    var scale = W * H / total;
    var nodes = items.map(function (i) { return { it: i, a: i.w * scale }; });
    var rect = { x: 0, y: 0, w: W, h: H }, out = [], row = [];
    function worst(r, side) {
      var s = 0, mx = 0, mn = Infinity;
      r.forEach(function (n) { s += n.a; mx = Math.max(mx, n.a); mn = Math.min(mn, n.a); });
      return Math.max(side * side * mx / (s * s), (s * s) / (side * side * mn));
    }
    function lay(r) {
      var s = r.reduce(function (a, n) { return a + n.a; }, 0);
      if (rect.w >= rect.h) {
        var cw = s / rect.h, cy = rect.y;
        r.forEach(function (n) { var ch = n.a / cw; out.push({ it: n.it, x: rect.x, y: cy, w: cw, h: ch }); cy += ch; });
        rect.x += cw; rect.w -= cw;
      } else {
        var rh = s / rect.w, cx = rect.x;
        r.forEach(function (n) { var w2 = n.a / rh; out.push({ it: n.it, x: cx, y: rect.y, w: w2, h: rh }); cx += w2; });
        rect.y += rh; rect.h -= rh;
      }
    }
    while (nodes.length) {
      var side = Math.min(rect.w, rect.h), n = nodes[0];
      if (!row.length || worst(row.concat([n]), side) <= worst(row, side)) { row.push(n); nodes.shift(); }
      else { lay(row); row = []; }
    }
    if (row.length) lay(row);
    return out;
  }
  function drawHeat(el) {
    var kind = el.dataset.heat, d = S.data[kind];
    if (!d) return;
    var rows = (d.rows || []).filter(function (r) { return fin(r.chg_1d); });
    var mx = kind === "vn" ? 7 : 10;
    var items = kind === "vn"
      ? rows.filter(function (r) { return fin(r.value) && r.value > 0; }).map(function (r) { return { w: Math.sqrt(r.value), r: r }; })
      : rows.filter(function (r) { return fin(r.mcap) && r.mcap > 0; }).slice(0, 60).map(function (r) { return { w: Math.sqrt(r.mcap), r: r }; });
    items.sort(function (a, b) { return b.w - a.w; });
    var W = el.clientWidth || 600, H = el.clientHeight || 360;
    var cells = squarify(items, W, H);
    el.innerHTML = cells.map(function (c, i) {
      var r = c.it.r, small = c.w < 46 || c.h < 30;
      var strong = Math.abs(r.chg_1d) / mx > 0.35;
      return '<div class="cell" data-open="' + kind + "|" + esc(r.id || r.symbol) + '" data-heati="' + i + '" style="left:' + c.x.toFixed(1) + "px;top:" + c.y.toFixed(1) +
        "px;width:" + c.w.toFixed(1) + "px;height:" + c.h.toFixed(1) + "px;background:" + heatColor(r.chg_1d, mx) + ";color:" + (strong ? "#fff" : "var(--text)") + '">' +
        (small ? "" : "<b>" + esc(symLabel(kind, r)) + "</b><span>" + pct(r.chg_1d) + "</span>") + "</div>";
    }).join("");
    el._cells = cells;
    if (!el._tipBound) {
      el._tipBound = true;
      el.addEventListener("mousemove", function (e) {
        var c = e.target.closest(".cell");
        if (!c || !el._cells) return hideTip();
        var r = el._cells[+c.dataset.heati].it.r;
        showTip(e, "<b>" + esc(symLabel(kind, r)) + "</b>" + (nameOf(r) ? " · " + esc(nameOf(r)) : "") + tipRows([
          [T("mk.col.price"), price(r.price)], [T("mk.col.d1"), pct(r.chg_1d)], [T("mk.col.w1"), pct(r.chg_5d)],
          [kind === "vn" ? T("mk.col.value_bn") : T("mk.col.mcap"), kind === "vn" ? num(r.value / 1e6, 1) : compact(r.mcap)],
          [T("mk.col.score"), fin(r.score) ? String(r.score) : "-"]]));
      });
      el.addEventListener("mouseleave", hideTip);
    }
  }

  // ------------------------------------------------------------------ world
  function viewWorld(d) {
    var rows = d.rows || [];
    function group(pred) { return rows.filter(pred).map(function (r) { return tile("world", r); }).join(""); }
    var regions = ["us", "eu", "asia"].map(function (rg) {
      return '<div class="mk-card"><h3>' + esc(T("mk.region." + rg)) + '</h3><div class="mk-tiles">' +
        group(function (r) { return r.group === "index" && r.region === rg; }) + "</div></div>";
    }).join("");
    var filters = [["all", T("mk.all")], ["index", T("mk.group.index")], ["stock", T("mk.group.stock")], ["commodity", T("mk.group.commodity")],
      ["fx", T("mk.group.fx")], ["rate", T("mk.group.rate")]];
    return '<div class="mk-grid" style="grid-template-columns:minmax(0,1fr) minmax(0,2fr);align-items:start">' + regimeCard("world", d) +
      '<div class="mk-card"><h3>' + esc(T("mk.macro")) + '</h3><div class="mk-tiles">' +
      group(function (r) { return r.group === "commodity" || r.group === "fx" || r.group === "rate"; }) + "</div></div></div>" +
      '<div class="mk-grid mk-g3 mk-sec">' + regions + "</div>" +
      '<div class="mk-sec">' + toolsHtml("world", filters) + tableHtml("world", rows) + "</div>";
  }

  // ------------------------------------------------------------------ crypto
  function viewCrypto(d) {
    var g = d.global || {}, f = d.fng || {};
    var dom = fin(g.btc_dom) ? '<div class="mk-breadth" style="height:12px"><i style="width:' + g.btc_dom + '%;background:var(--mk-s2)"></i><i style="width:' +
      (g.eth_dom || 0) + '%;background:var(--mk-s1)"></i><i style="flex:1;background:var(--mk-neutral)"></i></div>' +
      '<div class="mk-legend"><span><i class="sq" style="background:var(--mk-s2)"></i>BTC ' + num(g.btc_dom, 1) + '%</span><span><i class="sq" style="background:var(--mk-s1)"></i>ETH ' +
      num(g.eth_dom, 1) + '%</span><span><i class="sq" style="background:var(--mk-neutral)"></i>' + esc(T("mk.others")) + " " + num(100 - g.btc_dom - (g.eth_dom || 0), 1) + "%</span></div>" : "";
    var glob = '<div class="mk-card"><h3>' + esc(T("mk.crypto_global")) + '</h3><div class="mk-reg-kv" style="font-size:14px">' +
      "<span>" + esc(T("mk.total_mcap")) + "</span><b>$" + compact(g.mcap) + " " + chg(g.mcap_chg_24h) + "</b>" +
      "<span>" + esc(T("mk.vol24")) + "</span><b>$" + compact(g.volume) + "</b>" +
      "<span>" + esc(T("mk.coins_n")) + "</span><b>" + compact(g.coins) + "</b></div>" + '<div class="mk-sec mk-kicker">' + esc(T("mk.dominance")) + "</div>" + dom + "</div>";
    var fng = '<div class="mk-card"><h3>' + esc(T("mk.fng")) + '<span class="mk-sub">' + (fin(f.value) ? esc(T("mk.fng_l." + fngKey(f.value))) : "") + "</span>" +
      infoBtn(T("mk.fng")) + "</h3>" + infoBody(esc(T("mk.info.fng"))) +
      '<div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">' + gauge(fin(f.value) ? f.value * 2 - 100 : null, 120).replace(/>[+-]?\d+<\/text>/, ">" + (fin(f.value) ? f.value : "-") + "</text>") +
      '<div class="mk-reg-kv"><span>' + esc(T("mk.week_ago")) + "</span><b>" + (f.week_ago != null ? f.week_ago : "-") + "</b><span>" + esc(T("mk.month_ago")) +
      "</span><b>" + (f.month_ago != null ? f.month_ago : "-") + "</b></div></div>" + fngChart(f.history || []) + "</div>";
    var trend = '<div class="mk-card"><h3>' + IC("flame") + esc(T("mk.trending")) + '</h3><table class="mk-tbl"><tbody>' + (d.trending || []).slice(0, 8).map(function (c) {
      return '<tr data-open="crypto|' + esc(c.id) + '"><td class="l"><div class="mk-sym">' + (c.thumb ? '<img src="' + esc(c.thumb) + '" alt="" loading="lazy">' : "") +
        esc(c.symbol) + "<small>" + esc(c.name) + '</small></div></td><td class="mk-muted">#' + (c.rank || "-") + "</td><td>" + chg(c.chg_24h) + "</td></tr>";
    }).join("") + "</tbody></table></div>";
    return '<div class="mk-grid mk-g3" style="align-items:start">' + regimeCard("crypto", d) + glob + fng + "</div>" +
      '<div class="mk-grid mk-sec" style="grid-template-columns:minmax(0,2fr) minmax(0,1fr);align-items:start"><div class="mk-card"><h3>' + esc(T("mk.heat_crypto")) +
      '<span class="mk-sub">' + esc(T("mk.heat_crypto_sub")) + '</span></h3><div class="mk-heat" data-heat="crypto"></div>' + heatLegend(10) + "</div>" + trend + "</div>" +
      '<div class="mk-sec">' + toolsHtml("crypto", null) + tableHtml("crypto", d.rows || []) + "</div>";
  }
  function fngChart(hist) {
    if (hist.length < 2) return "";
    var W = 360, H = 90, pl = 4, pr = 24;
    var x = function (i) { return pl + i / (hist.length - 1) * (W - pl - pr); };
    var y = function (v) { return 4 + (100 - v) / 100 * (H - 8); };
    var bands = [[0, 25, "var(--mk-down)"], [75, 100, "var(--mk-up)"]].map(function (b) {
      return '<rect x="' + pl + '" y="' + y(b[1]) + '" width="' + (W - pl - pr) + '" height="' + (y(b[0]) - y(b[1])) + '" style="fill:' + b[2] + ';opacity:.08"/>';
    }).join("");
    var line = hist.map(function (p, i) { return x(i).toFixed(1) + "," + y(p.v).toFixed(1); }).join(" ");
    var ticks = [25, 50, 75].map(function (v) { return '<line class="grid" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text x="' + (W - pr + 4) + '" y="' + (y(v) + 4) + '">' + v + "</text>"; }).join("");
    return '<svg class="mk-chart mk-sec" viewBox="0 0 ' + W + " " + H + '" data-fng="1">' + bands + ticks + '<polyline points="' + line +
      '" style="fill:none;stroke:var(--mk-s1);stroke-width:2;stroke-linejoin:round"/><rect class="hit" x="0" y="0" width="' + W + '" height="' + H + '" style="fill:transparent"/></svg>';
  }

  // ------------------------------------------------------------------ outlook
  function narrative(mk, sec, bench) {
    var r = (sec && sec.regime) || {};
    var out = [];
    out.push(T("mk.nar.state", { label: T("mk.regime." + (r.label || "unknown")), score: fin(r.score) ? r.score : "-" }));
    if (fin(r.breadth50)) out.push(T("mk.nar.breadth", { b50: r.breadth50, b200: fin(r.breadth200) ? r.breadth200 : "-" }));
    if (fin(r.advancers)) out.push(T("mk.nar.adv", { up: r.advancers, down: r.decliners }));
    if (fin(r.vix)) out.push(T("mk.nar.vix", { v: num(r.vix, 1), level: T("mk.vix." + r.vix_level) }));
    if (fin(r.fng)) out.push(T("mk.nar.fng", { v: r.fng, label: T("mk.fng_l." + fngKey(r.fng)) }));
    if (r.vol_trend) out.push(T("mk.nar.vol_" + r.vol_trend));
    if (bench && fin(bench.exp_move_5d)) out.push(T("mk.nar.bench", { name: bench.name || bench.symbol, m: num(bench.exp_move_5d, 1) }));
    if (fin(r.hot)) out.push(T("mk.nar.hot", { n: r.hot }));
    return out;
  }
  function viewOutlook(ov, sec) {
    var s = (ov.sections || {})[S.outlook] || {};
    var ol = s.outlook || {};
    var bench = S.outlook === "vn" ? (s.indices || [])[0] : (s.key || [])[0];
    var seg = '<div class="mk-seg">' + MARKETS.map(function (m) {
      return '<button type="button" class="mk-segb' + (S.outlook === m ? " on" : "") + '" data-outlook="' + m + '">' + esc(T("mk.tab." + m)) + "</button>";
    }).join("") + "</div>";
    var nar = narrative(S.outlook, s, bench);
    var head = '<div class="mk-tools">' + seg + '<span class="mk-sp"></span><span class="mk-chip flat">' + IC("triangle-alert") + esc(T("mk.disclaimer_short")) +
      "</span>" + infoBtn(T("mk.how")) + infoBody(esc(T("mk.info.method")) + "<br><br>" + esc(T("mk.info.disclaimer"))) +
      '<button type="button" class="mk-btn pri" data-ask="' + S.outlook + '">' + IC("sparkles") + "<span>" + esc(T("mk.ask")) + "</span></button></div>";
    var summary = '<div class="mk-grid" style="grid-template-columns:minmax(0,1fr) minmax(0,2fr);align-items:start">' + regimeCard(S.outlook, s) +
      '<div class="mk-card"><h3>' + IC("telescope") + esc(T("mk.summary")) + '</h3><ul style="margin:0;padding-left:18px;line-height:1.7">' +
      nar.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></div></div>";
    var map = '<div class="mk-card mk-sec"><h3>' + esc(T("mk.map")) + '<span class="mk-sub">' + esc(T("mk.map_sub")) + "</span>" + infoBtn(T("mk.map")) + "</h3>" +
      infoBody(esc(T("mk.info.map"))) + '<div data-scatter="' + S.outlook + '" style="width:100%"></div></div>';
    function lst(key, icon) {
      return '<div class="mk-card"><h3>' + IC(icon) + esc(T("mk.list." + key)) + '<span class="mk-sub">' + (ol[key] || []).length + "</span></h3>" +
        listItems((ol[key] || []).map(function (r) { return [S.outlook, r]; })) + "</div>";
    }
    var acc = '<div class="mk-card mk-sec" data-acc="' + S.outlook + '"><div class="mk-skel" style="height:160px"></div></div>';
    return head + summary + map + acc + '<div class="mk-grid mk-g2 mk-sec" style="align-items:start">' + lst("potential", "trending-up") + lst("movers", "zap") +
      lst("risk", "trending-down") + lst("rebound", "rotate-ccw") + "</div>";
  }
  function drawScatter(el) {
    var kind = el.dataset.scatter, d = S.data[kind];
    if (!d) { el.innerHTML = '<div class="mk-skel" style="height:300px"></div>'; return; }
    var rows = (d.rows || []).filter(function (r) { return fin(r.score) && fin(r.move_score) && r.sma50; });
    var W = Math.max(300, el.clientWidth), H = Math.min(420, Math.max(280, W * 0.42)), pl = 34, pr = 10, pt = 10, pb = 28;
    var x = function (v) { return pl + (v + 100) / 200 * (W - pl - pr); };
    var y = function (v) { return pt + (100 - v) / 100 * (H - pt - pb); };
    var grid = [-100, -50, 0, 50, 100].map(function (v) {
      return '<line class="grid" x1="' + x(v) + '" x2="' + x(v) + '" y1="' + pt + '" y2="' + (H - pb) + '"/><text x="' + x(v) + '" y="' + (H - 10) + '" text-anchor="middle">' + v + "</text>";
    }).join("") + [0, 50, 100].map(function (v) {
      return '<line class="grid" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text x="' + (pl - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + v + "</text>";
    }).join("");
    var quad = [[x(55), y(92), "mk.quad.tr", "start"], [x(-95), y(92), "mk.quad.tl", "start"], [x(55), y(6), "mk.quad.br", "start"], [x(-95), y(6), "mk.quad.bl", "start"]]
      .map(function (q) { return '<text x="' + q[0] + '" y="' + q[1] + '" text-anchor="' + q[3] + '" style="font-weight:600">' + esc(T(q[2])) + "</text>"; }).join("");
    var top = rows.slice().sort(function (a, b) { return (Math.abs(b.score) + b.move_score) - (Math.abs(a.score) + a.move_score); }).slice(0, 14);
    var dots = rows.map(function (r, i) {
      var c = r.score >= 20 ? "var(--mk-up)" : r.score <= -20 ? "var(--mk-down)" : "var(--mk-flat)";
      return '<circle cx="' + x(r.score).toFixed(1) + '" cy="' + y(r.move_score).toFixed(1) + '" r="5" data-si="' + i + '" style="fill:' + c +
        ';stroke:var(--bg);stroke-width:2;cursor:pointer;opacity:.9"/>';
    }).join("");
    var placed = [];
    var labels = top.map(function (r) {
      var lx = x(r.score) + 7, ly = y(r.move_score) - 6, lw = String(symLabel(kind, r)).length * 7 + 4;
      if (placed.some(function (p) { return lx < p[0] + p[2] && p[0] < lx + lw && Math.abs(ly - p[1]) < 13; })) return "";
      placed.push([lx, ly, lw]);
      return '<text x="' + lx.toFixed(1) + '" y="' + ly.toFixed(1) + '" style="fill:var(--text2);font-weight:600">' + esc(symLabel(kind, r)) + "</text>";
    }).join("");
    el.innerHTML = '<svg class="mk-chart" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H + '">' + grid + quad + labels + dots +
      '<text x="' + (W - pr) + '" y="' + (H - pb - 6) + '" text-anchor="end">' + esc(T("mk.axis_score")) + '</text><text x="' + (pl + 6) + '" y="' + (pt + 12) + '">' +
      esc(T("mk.axis_move")) + "</text></svg>";
    var svg = el.querySelector("svg");
    svg.addEventListener("mousemove", function (e) {
      var c = e.target.closest("circle");
      if (!c) return hideTip();
      var r = rows[+c.dataset.si];
      showTip(e, "<b>" + esc(symLabel(kind, r)) + "</b>" + (nameOf(r) ? " · " + esc(nameOf(r)) : "") + tipRows([
        [T("mk.col.score"), String(r.score)], [T("mk.col.move"), r.move_score + "/100"], [T("mk.col.d1"), pct(r.chg_1d)],
        [T("mk.col.m1"), pct(r.chg_1m)], ["RSI", num(r.rsi, 0)]]));
    });
    svg.addEventListener("mouseleave", hideTip);
    svg.addEventListener("click", function (e) {
      var c = e.target.closest("circle");
      if (c) { var r = rows[+c.dataset.si]; openDetail(kind, r.id || r.symbol); }
    });
  }

  // ------------------------------------------------------------------ paper trading (virtual accounts)
  var PP_KINDS = ["vn", "crypto", "world"];
  function ppCcy(kind) { return kind === "vn" ? "VND" : "USD"; }
  function money(v, kind, nd) {
    if (!fin(v)) return "-";
    if (ppCcy(kind) === "VND") return T("mk.pp.vnd", { v: num(v, 0) });
    return "$" + num(v, nd == null ? 2 : nd);
  }
  function signedMoney(v, kind) { return fin(v) ? (v > 0 ? "+" : "") + money(v, kind) : "-"; }
  function qtyFmt(q, kind) { return fin(q) ? (kind === "crypto" ? new Intl.NumberFormat(loc(), { maximumFractionDigits: 6 }).format(q) : num(q, 0)) : "-"; }
  function dt(ts) {
    if (!ts) return "-";
    try { return new Date(ts * 1000).toLocaleString(loc(), { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }); } catch (e) { return ""; }
  }
  function viewPaper() {
    var seg = '<div class="mk-seg">' + PP_KINDS.map(function (k) {
      return '<button type="button" class="mk-segb' + (S.ppKind === k ? " on" : "") + '" data-ppk="' + k + '">' + esc(T("mk.pp.acc." + k)) + "</button>";
    }).join("") + "</div>";
    return '<div class="mk-tools">' + seg + '<span class="mk-sp"></span><span class="mk-chip flat">' + IC("triangle-alert") + esc(T("mk.pp.virtual")) +
      '</span><button type="button" class="mk-btn ghost" data-pptg id="mkPPTg" aria-pressed="false">' + IC("send") + "<span>" + esc(T("mk.pp.tg")) +
      '</span><span class="mk-chip" id="mkPPTgState">-</span></button>' + infoBtn(T("mk.pp.how")) + infoBody(esc(T("mk.pp.info"))) +
      '</div><div id="mkPP"><div class="mk-skel" style="height:300px"></div></div>';
  }
  function paintPPTg() {
    var btn = S.el && S.el.querySelector("#mkPPTg"), st = S.el && S.el.querySelector("#mkPPTgState");
    if (!btn || !S.bg) return;
    var on = !(S.bg.settings && S.bg.settings.paper_telegram === false), ready = !!S.bg.telegram_ready;
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    st.textContent = T(!on ? "mk.bg_off" : ready ? "mk.bg_on" : "mk.pp.tg_none");
    st.className = "mk-chip " + (on && ready ? "up" : "");
    btn.title = T(on && !ready ? "mk.pp.tg_need" : "mk.pp.tg_tip");
  }
  function togglePPTg() {
    if (!S.bg) return;
    var on = !(S.bg.settings && S.bg.settings.paper_telegram === false);
    api("/market/settings", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paper_telegram: !on }) }).then(function (d) { if (d && d.ok) { S.bg = Object.assign(S.bg, d); paintPPTg(); } });
  }
  function drawPaper(force) {
    var box = S.el && S.el.querySelector("#mkPP"), kind = S.ppKind, gen = S.gen;
    if (!box) return;
    paintPPTg();
    if (S.pp[kind] && !force) box.innerHTML = paperHtml(S.pp[kind]);
    api("/market/paper?kind=" + kind).then(function (d) {
      if (gen !== S.gen || S.ppKind !== kind) return;
      var b = S.el && S.el.querySelector("#mkPP");
      if (!b) return;
      if (!d || d.ok === false) { b.innerHTML = '<div class="mk-err">' + esc((d && d.error) || T("mk.err.load")) + "</div>"; return; }
      S.pp[kind] = d;
      var top = body() ? body().scrollTop : 0;
      b.innerHTML = paperHtml(d);
      if (body()) body().scrollTop = top;
      var svg = b.querySelector("svg[data-ppcurve]");
      if (svg) bindCurveHover(svg, svg._pts || ppCurvePoints(d.curve || [], d.stats && d.stats.start_cash));
      var sim = S.ppSim[kind];
      if (sim) paintSim(sim);
    });
  }
  function planHtml(plan) {
    var k = plan.kind, e = plan.entry || {}, ex = plan.exposure || {};
    var lines = [
      T("mk.pp.plan.capital", { v: money(plan.cash, k, 0) }),
      T("mk.pp.plan.style_" + (k === "world" ? "core" : "pullback")),
      T("mk.pp.plan.positions", { n: plan.max_pos, w: Math.round(plan.max_w * 100) }),
      T("mk.pp.plan.risk", { r: num(plan.risk * 100, 1) }),
      T("mk.pp.plan.stop", { a: num(plan.stop_atr, 1), lo: Math.round(plan.stop_min * 100), hi: Math.round(plan.stop_max * 100) }),
      T("mk.pp.plan.trail", { a: num(plan.trail_atr, 1), r: num(e.take_profit_r, 0) }),
      T("mk.pp.plan.exposure", { on: Math.round(ex.risk_on * 100), ne: Math.round(ex.neutral * 100) }),
      T("mk.pp.plan.timing"),
      T("mk.pp.plan.fees_" + k),
      T("mk.pp.plan.schedule_" + k),
    ];
    return '<ul class="mk-plan">' + lines.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>";
  }
  function simCard(kind) {
    return '<div class="mk-card mk-sec" id="mkSim"><h3>' + IC("history") + esc(T("mk.pp.sim.title")) + infoBtn(T("mk.pp.sim.title")) + "</h3>" +
      infoBody(esc(T("mk.pp.sim.info"))) + '<div class="mk-tools">' +
      [120, 250].map(function (n) { return '<button type="button" class="mk-btn" data-ppsim="' + n + '">' + esc(T("mk.pp.sim.run", { n: n })) + "</button>"; }).join("") +
      '</div><div id="mkSimOut"></div></div>';
  }
  function paperHtml(d) {
    var kind = d.kind;
    if (!d.started) {
      return '<div class="mk-card"><h3>' + IC("list-checks") + esc(T("mk.pp.plan.title", { a: T("mk.pp.acc." + kind) })) + "</h3>" + planHtml(d.plan) +
        '<div class="mk-tools mk-sec"><button type="button" class="mk-btn pri" data-pp="start">' + IC("play") + "<span>" + esc(T("mk.pp.start")) +
        "</span></button></div></div>" + simCard(kind);
    }
    var st = d.stats || {}, pos = d.positions || [], log = d.log || [];
    var head = '<div class="mk-tools"><span class="mk-chip ' + (d.running ? "up" : "") + '">' + IC(d.running ? "play" : "pause") +
      esc(T(d.running ? "mk.pp.running" : "mk.pp.paused")) + '</span><span class="mk-muted">' + esc(T("mk.pp.since", { d: dt(d.started_at), n: num(st.days, 0) })) +
      '</span><span class="mk-sp"></span><button type="button" class="mk-btn" data-pp="run">' + IC("zap") + "<span>" + esc(T("mk.pp.run")) + "</span></button>" +
      '<button type="button" class="mk-btn" data-pp="' + (d.running ? "pause" : "resume") + '">' + IC(d.running ? "pause" : "play") + "<span>" +
      esc(T(d.running ? "mk.pp.pause" : "mk.pp.resume")) + '</span></button><button type="button" class="mk-btn ghost" data-pp="reset">' + IC("rotate-ccw") +
      "<span>" + esc(T("mk.pp.reset")) + '</span></button><button type="button" class="mk-btn pri" data-pp="ask">' + IC("sparkles") + "<span>" +
      esc(T("mk.pp.ask")) + "</span></button></div>";
    function box(k, v, sub, good) {
      return '<div><div class="k">' + esc(k) + '</div><div class="v ' + (good == null ? "" : good ? "mk-up" : "mk-down") + '">' + esc(v) +
        '</div><div class="mk-kicker">' + esc(sub || "") + "</div></div>";
    }
    var kpi = '<div class="mk-sigbox g4 mk-sec">' +
      box(T("mk.pp.k.equity"), money(st.equity, kind, 0), T("mk.pp.k.start", { v: money(st.start_cash, kind, 0) })) +
      box(T("mk.pp.k.pnl"), signedMoney(st.pnl, kind), pct(st.pnl_pct), st.pnl >= 0) +
      box(T("mk.pp.k.bench"), pct(st.bench_return), fin(st.alpha) ? T("mk.pp.k.alpha", { a: pct(st.alpha) }) : "", fin(st.alpha) ? st.alpha >= 0 : null) +
      box(T("mk.pp.k.cash"), money(st.cash, kind, 0), T("mk.pp.k.exposure", { p: num(st.exposure, 0) })) +
      box(T("mk.pp.k.realized"), signedMoney(st.realized, kind), T("mk.pp.k.unrealized", { v: signedMoney(st.unrealized, kind) }), (st.realized || 0) >= 0) +
      box(T("mk.pp.k.trades"), String(st.trades || 0), T("mk.pp.k.closed", { n: st.closed || 0 })) +
      box(T("mk.pp.k.win"), fin(st.win_rate) ? num(st.win_rate, 0) + "%" : "-", fin(st.profit_factor) ? T("mk.pp.k.pf", { v: num(st.profit_factor, 2) }) : "", fin(st.profit_factor) ? st.profit_factor >= 1 : null) +
      box(T("mk.pp.k.mdd"), pct(st.max_drawdown), T("mk.pp.k.fees", { v: money(st.fees, kind) }), null) + "</div>";
    var curve = '<div class="mk-grid mk-sec" style="grid-template-columns:minmax(0,2fr) minmax(0,1fr);align-items:start"><div class="mk-card"><h3>' +
      esc(T("mk.pp.curve")) + '<span class="mk-sub">' + esc(T("mk.pp.curve_sub")) + "</span></h3>" + curveSvg(d) +
      '<div class="mk-legend"><span><i style="background:var(--mk-s1)"></i>' + esc(T("mk.pp.series.port")) + '</span><span><i style="background:var(--mk-s2)"></i>' +
      esc(T("mk.pp.series.bench", { b: T("mk.pp.bench." + kind) })) + '</span></div></div><div class="mk-card"><h3>' + esc(T("mk.pp.alloc")) + "</h3>" + allocHtml(d) + "</div></div>";
    var watch = (log[0] && log[0].watch) || [];
    return head + kpi + curve +
      '<div class="mk-card mk-sec"><h3>' + IC("shield") + esc(T("mk.pp.positions")) + '<span class="mk-sub">' + pos.length + "</span></h3>" + positionsHtml(d) + "</div>" +
      '<div class="mk-card mk-sec"><h3>' + IC("hourglass") + esc(T("mk.pp.watch")) + '<span class="mk-sub">' + esc(T("mk.pp.watch_sub")) + "</span></h3>" + watchHtml(kind, watch) + "</div>" +
      '<div class="mk-card mk-sec"><h3>' + IC("list") + esc(T("mk.pp.trades")) + '<span class="mk-sub">' + esc(T("mk.pp.trades_sub")) + "</span></h3>" + tradesHtml(d) + "</div>" +
      '<div class="mk-card mk-sec"><h3>' + IC("clock") + esc(T("mk.pp.log")) + "</h3>" + logHtml(d) + "</div>" +
      '<details class="mk-card mk-sec"><summary class="mk-sum">' + esc(T("mk.pp.plan.title", { a: T("mk.pp.acc." + kind) })) + "</summary>" + planHtml(d.plan) + "</details>" + simCard(kind);
  }
  function ppCurvePoints(curve, start) {
    var b0 = null;
    return curve.filter(function (c) { return fin(c.equity); }).map(function (c) {
      if (b0 == null && fin(c.bench)) b0 = c.bench;
      return { t: c.ts || c.d, p: c.equity / (start || curve[0].equity) * 100, b: fin(c.bench) && b0 ? c.bench / b0 * 100 : null, eq: c.equity };
    });
  }
  var CV_W = 640, CV_H = 220, CV_PL = 6, CV_PR = 48;
  function curveSvg(d, pts) {
    pts = pts || ppCurvePoints(d.curve || [], d.stats && d.stats.start_cash);
    if (pts.length < 2) return '<div class="mk-empty">' + esc(T("mk.pp.curve_wait")) + "</div>";
    var vals = [100];
    pts.forEach(function (x) { vals.push(x.p); if (fin(x.b)) vals.push(x.b); });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), pad = (hi - lo) * 0.1 || 1;
    lo -= pad; hi += pad;
    var x = function (i) { return CV_PL + i / (pts.length - 1) * (CV_W - CV_PL - CV_PR); };
    var y = function (v) { return 8 + (hi - v) / (hi - lo) * (CV_H - 30); };
    function line(key, col) {
      var a = [];
      pts.forEach(function (p, i) { if (fin(p[key])) a.push(x(i).toFixed(1) + "," + y(p[key]).toFixed(1)); });
      return a.length > 1 ? '<polyline points="' + a.join(" ") + '" style="fill:none;stroke:' + col + ';stroke-width:2;stroke-linejoin:round"/>' : "";
    }
    var ticks = niceTicks(lo, hi, 4).map(function (v) {
      return '<line class="grid" x1="' + CV_PL + '" x2="' + (CV_W - CV_PR) + '" y1="' + y(v).toFixed(1) + '" y2="' + y(v).toFixed(1) + '"' + (v === 100 ? ' style="stroke:var(--text3)"' : "") +
        '/><text x="' + (CV_W - CV_PR + 4) + '" y="' + (y(v) + 4).toFixed(1) + '">' + num(v, 0) + "</text>";
    }).join("");
    var lbl = function (t) { return typeof t === "number" ? dt(t) : t; };
    var dates = '<text x="' + CV_PL + '" y="' + (CV_H - 4) + '">' + esc(lbl(pts[0].t)) + '</text><text x="' + (CV_W - CV_PR) + '" y="' + (CV_H - 4) + '" text-anchor="end">' + esc(lbl(pts[pts.length - 1].t)) + "</text>";
    return '<svg class="mk-chart" data-ppcurve="1" viewBox="0 0 ' + CV_W + " " + CV_H + '" style="max-width:' + CV_W * 1.4 + 'px">'  + ticks + line("b", "var(--mk-s2)") + line("p", "var(--mk-s1)") + dates +
      '<line class="cross" x1="0" x2="0" y1="8" y2="' + (CV_H - 22) + '" style="display:none"/><rect x="0" y="0" width="' + CV_W + '" height="' + CV_H + '" style="fill:transparent"/></svg>';
  }
  function bindCurveHover(svg, pts) {
    if (!pts || pts.length < 2) return;
    var cross = svg.querySelector(".cross");
    svg.addEventListener("mousemove", function (e) {
      var r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * (CV_W / r.width);
      var i = Math.max(0, Math.min(pts.length - 1, Math.round((px - CV_PL) / (CV_W - CV_PL - CV_PR) * (pts.length - 1))));
      var xx = CV_PL + i / (pts.length - 1) * (CV_W - CV_PL - CV_PR);
      cross.setAttribute("x1", xx); cross.setAttribute("x2", xx); cross.style.display = "";
      var p = pts[i], kind = S.ppKind;
      showTip(e, "<b>" + esc(typeof p.t === "number" ? dt(p.t) : p.t) + "</b>" + tipRows([[T("mk.pp.series.port"), pct(p.p - 100)],
        [T("mk.pp.series.bench", { b: T("mk.pp.bench." + kind) }), fin(p.b) ? pct(p.b - 100) : "-"], [T("mk.pp.k.equity"), money(p.eq, kind, 0)]]));
    });
    svg.addEventListener("mouseleave", function () { cross.style.display = "none"; hideTip(); });
  }
  function allocHtml(d) {
    var st = d.stats || {}, pos = d.positions || [];
    if (!st.equity) return "";
    var cols = ["var(--mk-s1)", "var(--mk-s2)", "var(--mk-s3)", "#1baf7a", "#e87ba4", "#eda100", "#008300", "#e34948"];
    var seg = pos.map(function (x, i) { return '<i style="width:' + x.weight.toFixed(2) + "%;background:" + cols[i % cols.length] + '" title="' + esc(x.symbol_label) + " " + num(x.weight, 1) + '%"></i>'; }).join("");
    var cashW = Math.max(0, 100 - pos.reduce(function (a, x) { return a + x.weight; }, 0));
    seg += '<i style="width:' + cashW.toFixed(2) + '%;background:var(--mk-neutral)" title="' + esc(T("mk.pp.cash")) + '"></i>';
    var legend = pos.map(function (x, i) {
      return '<span><i class="sq" style="background:' + cols[i % cols.length] + '"></i>' + esc(x.symbol_label) + " " + num(x.weight, 1) + "%</span>";
    }).join("") + '<span><i class="sq" style="background:var(--mk-neutral)"></i>' + esc(T("mk.pp.cash")) + " " + num(cashW, 1) + "%</span>";
    return '<div class="mk-breadth" style="height:14px">' + seg + '</div><div class="mk-legend" style="flex-direction:column;align-items:flex-start;gap:4px">' + legend + "</div>";
  }
  function positionsHtml(d) {
    var kind = d.kind, pos = d.positions || [];
    if (!pos.length) return '<div class="mk-empty">' + esc(T("mk.pp.no_pos")) + "</div>";
    var now = Date.now() / 1000;
    return '<div class="mk-tblw"><table class="mk-tbl"><thead><tr><th class="l">' + esc(T("mk.col.symbol")) + "</th><th>" + esc(T("mk.pp.c.qty")) + "</th><th>" +
      esc(T("mk.pp.c.avg")) + "</th><th>" + esc(T("mk.pp.c.price")) + "</th><th>" + esc(T("mk.pp.c.value")) + "</th><th>" + esc(T("mk.pp.c.pnl")) + "</th><th>%</th><th>" +
      esc(T("mk.pp.c.weight")) + "</th><th>" + esc(T("mk.pp.c.stop")) + "</th><th>" + esc(T("mk.pp.c.opened")) + '</th><th class="c"></th></tr></thead><tbody>' +
      pos.map(function (x) {
        var locked = x.sellable && x.sellable > now;
        return '<tr data-open="' + kind + "|" + esc(x.symbol) + '"><td class="l"><div class="mk-sym">' + (x.image ? '<img src="' + esc(x.image) + '" alt="">' : "") + esc(x.symbol_label) +
          (x.partial ? '<span class="mk-chip up">' + esc(T("mk.pp.partial")) + "</span>" : "") + "</div></td><td>" + qtyFmt(x.qty, kind) + "</td><td>" + price(x.avg) + "</td><td>" +
          lp(kind + "|" + x.symbol, x.price) + "</td><td>" + money(x.value, kind, 0) + '</td><td class="mk-' + dir(x.pnl) + '">' + signedMoney(x.pnl, kind) + "</td><td>" + chg(x.pnl_pct) +
          "</td><td>" + num(x.weight, 1) + "%</td><td>" + price(x.stop) + "</td><td>" + esc(dt(x.opened)) + '</td><td class="c">' +
          (locked ? '<span class="mk-chip" title="' + esc(T("mk.pp.tplus_tip", { d: dt(x.sellable) })) + '">T+2</span>'
            : '<button type="button" class="mk-btn sm ghost" data-ppclose="' + esc(x.symbol) + '">' + esc(T("mk.pp.sell")) + "</button>") + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }
  function watchHtml(kind, watch) {
    if (!watch.length) return '<div class="mk-empty">' + esc(T("mk.pp.no_watch")) + "</div>";
    return '<div class="mk-tblw"><table class="mk-tbl"><thead><tr><th class="l">' + esc(T("mk.col.symbol")) + "</th><th>" + esc(T("mk.pp.c.price")) + "</th><th>" +
      esc(T("mk.pp.c.zone")) + '</th><th class="l">' + esc(T("mk.pp.c.why")) + "</th><th>" + esc(T("mk.col.score")) + "</th><th>RSI</th></tr></thead><tbody>" +
      watch.map(function (w) {
        return '<tr data-open="' + kind + "|" + esc(w.symbol) + '"><td class="l"><b>' + esc(w.name && kind !== "crypto" ? w.symbol : (w.name || w.symbol)) + "</b></td><td>" +
          lp(kind + "|" + w.symbol, w.price) + "</td><td>" + (w.zone ? price(w.zone[0]) + " - " + price(w.zone[1]) : "-") + '</td><td class="l">' + esc(T("mk.pp.why." + w.why)) +
          "</td><td>" + scorePill(w.score) + "</td><td>" + num(w.rsi, 0) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
  }
  function tradesHtml(d) {
    var kind = d.kind, tr = d.trades || [];
    if (!tr.length) return '<div class="mk-empty">' + esc(T("mk.pp.no_trades")) + "</div>";
    return '<div class="mk-tblw"><table class="mk-tbl"><thead><tr><th class="l">' + esc(T("mk.pp.c.time")) + '</th><th class="l">' + esc(T("mk.pp.c.side")) + '</th><th class="l">' +
      esc(T("mk.col.symbol")) + "</th><th>" + esc(T("mk.pp.c.qty")) + "</th><th>" + esc(T("mk.pp.c.price")) + "</th><th>" + esc(T("mk.pp.c.value")) + "</th><th>" + esc(T("mk.pp.c.fee")) +
      "</th><th>" + esc(T("mk.pp.c.pnl")) + '</th><th>%</th><th class="l">' + esc(T("mk.pp.c.reason")) + "</th></tr></thead><tbody>" +
      tr.map(function (t) {
        var open = S.ppOpen[t.id];
        var row = '<tr data-pptrade="' + t.id + '" class="' + (open ? "open" : "") + '"><td class="l">' + esc(dt(t.at)) + '</td><td class="l"><span class="mk-chip ' +
          (t.side === "buy" ? "up" : "down") + '">' + esc(T("mk.pp.side." + t.side)) + '</span></td><td class="l"><b>' + esc(t.symbol) + "</b></td><td>" + qtyFmt(t.qty, kind) +
          "</td><td>" + price(t.price) + "</td><td>" + money(t.value, kind, 0) + "</td><td>" + money(t.fee, kind) + '</td><td class="mk-' + dir(t.pnl) + '">' +
          (t.pnl == null ? "" : signedMoney(t.pnl, kind)) + "</td><td>" + (t.pnl_pct == null ? "" : chg(t.pnl_pct)) + '</td><td class="l">' + esc(T("mk.pp.reason." + t.reason)) +
          " " + IC(open ? "chevron-down" : "chevron-right") + "</td></tr>";
        if (open) row += '<tr class="mk-detail"><td colspan="10">' + analysisHtml(kind, t) + "</td></tr>";
        return row;
      }).join("") + "</tbody></table></div>";
  }
  function analysisHtml(kind, t) {
    var a = t.analysis || {};
    var kv = [
      [T("mk.pp.a.regime"), a.regime ? T("mk.regime." + a.regime) + (fin(a.regime_score) ? " (" + a.regime_score + ")" : "") : "-"],
      [T("mk.pp.a.bench"), a.bench_up == null ? "-" : T(a.bench_up ? "mk.pp.a.bench_up" : "mk.pp.a.bench_down")],
      [T("mk.score"), fin(a.score) ? String(a.score) + " · " + T("mk.sig." + (a.signal || sigOf(a.score))) : "-"],
      ["RSI", num(a.rsi, 1)], ["MA20 / MA50 / MA200", [a.sma20, a.sma50, a.sma200].map(price).join(" / ")],
      ["ATR", fin(a.atr_pct) ? num(a.atr_pct, 2) + "%" : "-"], [T("mk.col.exp5"), fin(a.exp_move_5d) ? "±" + num(a.exp_move_5d, 1) + "%" : "-"],
      [T("mk.pp.a.stop"), fin(a.stop) ? price(a.stop) + (fin(a.stop_pct) ? " (" + pct(a.stop_pct) + ")" : "") : "-"],
    ];
    if (fin(a.risk_amount)) kv.push([T("mk.pp.a.risk"), money(a.risk_amount, kind)]);
    if (fin(a.weight)) kv.push([T("mk.pp.c.weight"), num(a.weight, 1) + "%"]);
    if (fin(a.target_r3)) kv.push([T("mk.pp.a.target"), price(a.target_r3)]);
    if (fin(a.r_multiple)) kv.push([T("mk.pp.a.r"), num(a.r_multiple, 2) + "R"]);
    if (fin(a.held_days)) kv.push([T("mk.pp.a.held"), T("mk.pp.a.days", { n: num(a.held_days, 1) })]);
    if (fin(a.chg_1m)) kv.push([T("mk.col.m1"), pct(a.chg_1m)]);
    var why = T("mk.pp.explain." + t.reason, {
      s: t.symbol, score: fin(a.score) ? a.score : "-", rsi: num(a.rsi, 0), stop: price(a.stop),
    });
    return '<div class="mk-analysis"><p>' + esc(why) + '</p><div class="mk-stats">' + kv.map(function (p) { return "<div><span>" + esc(p[0]) + "</span><b>" + esc(p[1]) + "</b></div>"; }).join("") +
      '</div><div class="mk-chips mk-sec">' + reasonChips(a.reasons) + "</div></div>";
  }
  function logHtml(d) {
    var log = d.log || [];
    if (!log.length) return '<div class="mk-empty">' + esc(T("mk.pp.no_log")) + "</div>";
    return '<div class="mk-list">' + log.slice(0, 12).map(function (l) {
      var counts = {};
      (l.skipped || []).forEach(function (s) { counts[s.why] = (counts[s.why] || 0) + 1; });
      var sk = Object.keys(counts).map(function (k) { return T("mk.pp.why." + k) + " (" + counts[k] + ")"; }).join(", ");
      var acts = (l.actions || []).map(function (a) { return T("mk.pp.side." + a.side) + " " + a.symbol; }).join(", ");
      return '<details class="mk-item" style="display:block"><summary class="mk-sum"><b>' + esc(dt(l.at)) + "</b> · " + esc(T("mk.regime." + (l.regime || "unknown"))) +
        (l.bench_up === false ? " · " + esc(T("mk.pp.a.bench_down")) : "") + " · " + esc(T("mk.pp.invested", { p: num(l.invested_pct, 0) })) + " · " +
        esc(acts || T("mk.pp.no_action")) + (l.forced ? " · " + esc(T("mk.pp.forced")) : "") + "</summary>" +
        '<div class="mk-kicker" style="margin-top:6px">' + esc(T("mk.pp.considered", { n: (l.considered || []).length })) + " " +
        esc((l.considered || []).slice(0, 12).map(function (c) { return c.symbol + " (" + c.score + ", " + T("mk.pp.why." + c.why) + ")"; }).join("; ")) + "</div>" +
        (sk ? '<div class="mk-kicker">' + esc(T("mk.pp.skipped", { v: sk })) + "</div>" : "") + "</details>";
    }).join("") + "</div>";
  }
  function paintSim(r) {
    var out = S.el && S.el.querySelector("#mkSimOut");
    if (!out) return;
    if (!r || !r.ok) { out.innerHTML = '<div class="mk-empty">' + esc(T("mk.pp.sim.none")) + "</div>"; return; }
    var kind = r.kind;
    function box(k, v, good) { return '<div><div class="k">' + esc(k) + '</div><div class="v ' + (good == null ? "" : good ? "mk-up" : "mk-down") + '">' + esc(v) + "</div></div>"; }
    var pts = (r.curve || []).map(function (c, i, arr) {
      var b0 = arr.filter(function (x) { return fin(x.bench); })[0];
      return { t: c.d, p: c.equity / r.start_equity * 100, b: fin(c.bench) && b0 ? c.bench / b0.bench * 100 : null, eq: c.equity };
    });
    out.innerHTML = '<p class="mk-kicker">' + esc(T("mk.pp.sim.range", { a: r.from, b: r.to, n: r.days })) + "</p>" +
      '<div class="mk-sigbox g4">' + box(T("mk.pp.sim.ret"), pct(r.return_pct), r.return_pct >= 0) +
      box(T("mk.pp.series.bench", { b: T("mk.pp.bench." + kind) }), pct(r.bench_return), null) +
      box(T("mk.pp.k.mdd"), pct(r.max_drawdown), null) +
      box(T("mk.pp.k.win"), (fin(r.win_rate) ? num(r.win_rate, 0) + "%" : "-") + (fin(r.profit_factor) ? " · PF " + num(r.profit_factor, 2) : ""), fin(r.profit_factor) ? r.profit_factor >= 1 : null) +
      "</div>" + curveSvg(null, pts) + '<div class="mk-legend"><span><i style="background:var(--mk-s1)"></i>' + esc(T("mk.pp.series.port")) +
      '</span><span><i style="background:var(--mk-s2)"></i>' + esc(T("mk.pp.series.bench", { b: T("mk.pp.bench." + kind) })) + "</span><span>" +
      esc(T("mk.pp.sim.trades", { n: r.trades, c: r.closed })) + "</span></div>";
    var svg = out.querySelector("svg[data-ppcurve]");
    if (svg) bindCurveHover(svg, pts);
  }
  function runSim(n, btn) {
    var kind = S.ppKind;
    btn.disabled = true;
    btn.classList.add("spin");
    var out = S.el.querySelector("#mkSimOut");
    if (out) out.innerHTML = '<div class="mk-skel" style="height:140px"></div><p class="mk-muted">' + esc(T("mk.pp.sim.wait")) + "</p>";
    api("/market/paper/simulate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: kind, days: n }) }).then(function (r) {
      btn.disabled = false;
      btn.classList.remove("spin");
      S.ppSim[kind] = r;
      if (S.ppKind === kind) paintSim(r);
    });
  }
  function ppAction(act) {
    var kind = S.ppKind;
    if (act === "ask") { askJavis(T("mk.pp.ask_prompt", { a: T("mk.pp.acc." + kind), k: kind })); return; }
    if (act === "reset" && !confirm(T("mk.pp.reset_confirm"))) return;
    var url = { start: "/market/paper/start", run: "/market/paper/run", pause: "/market/paper/pause", resume: "/market/paper/pause", reset: "/market/paper/reset" }[act];
    var body = { kind: kind };
    if (act === "pause") body.running = false;
    if (act === "resume") body.running = true;
    api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(function (r) {
      if (r && r.ok === false && r.error) alert(r.error);
      drawPaper(true);
    });
  }
  function ppClose(sym) {
    if (!confirm(T("mk.pp.sell_confirm", { s: sym }))) return;
    api("/market/paper/close", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: S.ppKind, symbol: sym }) }).then(function (r) {
      if (r && r.ok === false && r.error) alert(r.error);
      drawPaper(true);
    });
  }

  // ------------------------------------------------------------------ live prices
  function liveKinds() { return S.tab === "overview" || S.tab === "outlook" ? MARKETS : S.tab === "paper" ? [S.ppKind] : [S.tab]; }
  function setLive(ok) {
    S.liveOk = ok;
    var el = S.el && S.el.querySelector("#mkLive");
    if (el) el.classList.toggle("on", !!ok);
  }
  function sectionTime(k) {
    if (S.tab === "overview" || S.tab === "outlook") {
      var sec = S.data.overview && S.data.overview.sections && S.data.overview.sections[k];
      return sec ? (sec.computed_at || 0) : 0;
    }
    var d = S.data[k];
    return d ? (d.computed_at || 0) : 0;
  }
  function pollLive() {
    if (!S.el || !document.body.contains(S.el) || document.visibilityState !== "visible" || S.liveBusy) return;
    S.liveBusy = true;
    var gen = S.gen;
    api("/market/live?kinds=" + liveKinds().join(",")).then(function (d) {
      S.liveBusy = false;
      if (gen !== S.gen) return;
      if (!d || d.ok === false) { setLive(false); return; }
      setLive(true);
      applyPrices(d.prices || {});
      if (S.tab === "paper") {
        // the account itself changes when the server runs a pass: refresh its report every minute
        if (!S.ppAt || Date.now() - S.ppAt > 60000) { S.ppAt = Date.now(); drawPaper(true); }
        return;
      }
      var newer = Object.keys(d.sections || {}).filter(function (k) { var t0 = sectionTime(k); return t0 && d.sections[k] > t0 + 1; });
      if (newer.length) quietReload();
    }).catch(function () { S.liveBusy = false; setLive(false); });
  }
  function applyPrices(prices) {
    var b = S.el;
    if (!b) return;
    Object.keys(prices).forEach(function (k) {
      var rows = S.data[k] ? (S.data[k].rows || []).concat(S.data[k].indices || []) : [];
      rows.forEach(function (r) {
        var v = prices[k][r.id || r.symbol];
        if (v && fin(v[0])) { r.price = v[0]; if (fin(v[1])) r.chg_1d = v[1]; }
      });
    });
    b.querySelectorAll("[data-lp]").forEach(function (el) {
      var p = el.dataset.lp.split("|"), v = prices[p[0]] && prices[p[0]][p.slice(1).join("|")];
      if (!v || !fin(v[0])) return;
      var old = el._v != null ? el._v : null, txt = price(v[0]);
      el._v = v[0];
      if (el.textContent === txt) return;
      el.textContent = txt;
      if (old != null && v[0] !== old) flash(el, v[0] > old ? "up" : "down");
    });
    b.querySelectorAll("[data-lc]").forEach(function (el) {
      var p = el.dataset.lc.split("|"), v = prices[p[0]] && prices[p[0]][p.slice(1).join("|")];
      if (!v || !fin(v[1])) return;
      var txt = arrow(v[1]) + " " + pct(v[1]);
      if (el.textContent === txt) return;
      el.textContent = txt;
      el.classList.remove("mk-up", "mk-down", "mk-flat");
      el.classList.add("mk-" + dir(v[1]));
    });
  }
  function flash(el, d) {
    el.classList.remove("mk-flash-up", "mk-flash-down");
    void el.offsetWidth;
    el.classList.add("mk-flash-" + d);
  }
  // A section the server recomputed (new session data, new scores): reload it without moving the reader.
  function quietReload() {
    var b = body();
    if (!b || b.contains(document.activeElement) && /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
    var names = needs(S.tab), gen = S.gen;
    Promise.all(names.map(function (n) { return load(n, true); })).then(function () {
      if (gen !== S.gen) return;
      var bb = body(), top = bb ? bb.scrollTop : 0;
      drawBody();
      bb = body();
      if (bb) bb.scrollTop = top;
    });
  }

  // ------------------------------------------------------------------ background refresh switch
  function paintBg() {
    var btn = S.el && S.el.querySelector("#mkBg"), st = S.el && S.el.querySelector("#mkBgState");
    if (!btn || !S.bg) return;
    var on = !!S.bg.enabled;
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.disabled = !!S.bg.env_off;
    st.textContent = T(on ? "mk.bg_on" : "mk.bg_off");
    st.className = "mk-chip " + (on ? "up" : "");
    if (S.bg.env_off) btn.title = T("mk.bg_env");
    paintPPTg();
  }
  function loadBg() {
    api("/market/settings").then(function (d) { if (d && d.ok) { S.bg = d; paintBg(); } });
  }
  function toggleBg() {
    if (!S.bg) return;
    api("/market/settings", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ background: !S.bg.enabled }) }).then(function (d) { if (d && d.ok) { S.bg = Object.assign(S.bg, d); paintBg(); } });
  }

  // ------------------------------------------------------------------ signal accuracy (Outlook tab)
  function loadAcc(kind) {
    var c = S.acc[kind];
    if (c && Date.now() - c.t < 10 * 60 * 1000) return Promise.resolve(c.d);
    return api("/market/accuracy?kind=" + kind).then(function (d) { if (d && d.ok) S.acc[kind] = { t: Date.now(), d: d }; return d; });
  }
  function drawAcc(el) {
    var kind = el.dataset.acc, gen = S.gen;
    loadAcc(kind).then(function (a) {
      if (gen !== S.gen || !document.body.contains(el)) return;
      el.innerHTML = accHtml(a || {});
      var svg = el.querySelector("svg[data-accchart]");
      if (svg) bindAccHover(svg, a.series || []);
    });
  }
  function accHtml(a) {
    var head = "<h3>" + IC("target") + esc(T("mk.acc.title")) + '<span class="mk-sub">' +
      (a.graded ? esc(T("mk.acc.sub", { d: a.days, live: a.live_days || 0 })) : "") + "</span>" + infoBtn(T("mk.acc.title")) + "</h3>" +
      infoBody(esc(T("mk.info.acc")));
    if (!a.graded) return head + '<div class="mk-empty">' + esc(T("mk.acc.wait")) + "</div>";
    var p = a.potential || {}, r = a.risk || {}, mv = a.movers || {};
    function box(k, v, sub, good) {
      return '<div><div class="k">' + esc(k) + '</div><div class="v ' + (good == null ? "" : good ? "mk-up" : "mk-down") + '">' + esc(v) +
        '</div><div class="mk-kicker">' + esc(sub) + "</div></div>";
    }
    var boxes = '<div class="mk-sigbox g4">' +
      box(T("mk.acc.pot"), p.n ? num(p.hit, 0) + "%" : "-", p.n ? T("mk.acc.pot_v", { avg: pct(p.avg), mkt: pct(a.market_avg), n: p.n }) : "", p.n ? p.excess >= 0 : null) +
      box(T("mk.acc.risk"), r.n ? num(r.hit, 0) + "%" : "-", r.n ? T("mk.acc.risk_v", { avg: pct(r.avg), n: r.n }) : "", r.n ? r.excess <= 0 : null) +
      box(T("mk.acc.move"), mv.ratio ? "\u00D7" + num(mv.ratio, 2) : "-", mv.n ? T("mk.acc.move_v", { a: num(mv.avg_abs, 1), m: num(mv.market_abs, 1) }) : "", mv.ratio ? mv.ratio >= 1 : null) +
      box(T("mk.acc.range"), fin(a.range_hit) ? num(a.range_hit, 0) + "%" : "-", T("mk.acc.range_v"), fin(a.range_hit) ? Math.abs(a.range_hit - 68) <= 10 : null) +
      "</div>";
    return head + boxes + '<div class="mk-grid mk-g2 mk-sec" style="align-items:start"><div><div class="mk-kicker">' + esc(T("mk.acc.chart")) + "</div>" +
      accChart(a.series || []) + '<div class="mk-legend"><span><i style="background:var(--mk-s1)"></i>' + esc(T("mk.acc.series_pot")) +
      '</span><span><i style="background:var(--mk-s2)"></i>' + esc(T("mk.acc.series_mkt")) + "</span></div></div><div>" +
      '<div class="mk-kicker">' + esc(T("mk.acc.buckets")) + "</div>" + bucketBars(a.buckets || []) + "</div></div>";
  }
  var ACC_W = 520, ACC_H = 170, ACC_PL = 6, ACC_PR = 44;
  function accChart(series) {
    var pts = series.filter(function (x) { return fin(x.market); });
    if (pts.length < 2) return '<div class="mk-empty">' + esc(T("mk.acc.wait")) + "</div>";
    var vals = [];
    pts.forEach(function (x) { vals.push(x.market); if (fin(x.potential)) vals.push(x.potential); });
    var mx = Math.max(1, Math.max.apply(null, vals.map(Math.abs)));
    var x = function (i) { return ACC_PL + i / (pts.length - 1) * (ACC_W - ACC_PL - ACC_PR); };
    var y = function (v) { return 8 + (mx - v) / (2 * mx) * (ACC_H - 26); };
    function line(key, col) {
      var segs = [], cur = [];
      pts.forEach(function (p, i) {
        if (fin(p[key])) cur.push(x(i).toFixed(1) + "," + y(p[key]).toFixed(1));
        else if (cur.length) { segs.push(cur); cur = []; }
      });
      if (cur.length) segs.push(cur);
      return segs.map(function (sg) { return '<polyline points="' + sg.join(" ") + '" style="fill:none;stroke:' + col + ';stroke-width:2;stroke-linejoin:round"/>'; }).join("");
    }
    var ticks = niceTicks(-mx, mx, 4).map(function (v) {
      return '<line class="grid" x1="' + ACC_PL + '" x2="' + (ACC_W - ACC_PR) + '" y1="' + y(v).toFixed(1) + '" y2="' + y(v).toFixed(1) + '"' +
        (v === 0 ? ' style="stroke:var(--text3)"' : "") + '/><text x="' + (ACC_W - ACC_PR + 4) + '" y="' + (y(v) + 4).toFixed(1) + '">' + pct(v, 0) + "</text>";
    }).join("");
    var live = pts.map(function (p, i) { return p.live ? '<circle cx="' + x(i).toFixed(1) + '" cy="' + (ACC_H - 12) + '" r="2.5" style="fill:var(--mk-s3)"/>' : ""; }).join("");
    var dates = [0, pts.length - 1].map(function (i) {
      return '<text x="' + x(i).toFixed(1) + '" y="' + (ACC_H - 2) + '" text-anchor="' + (i ? "end" : "start") + '">' + esc(pts[i].d) + "</text>";
    }).join("");
    return '<svg class="mk-chart" data-accchart="1" viewBox="0 0 ' + ACC_W + " " + ACC_H + '" style="max-width:' + ACC_W * 1.3 + 'px">'  + ticks + line("market", "var(--mk-s2)") +
      line("potential", "var(--mk-s1)") + live + dates + '<line class="cross" x1="0" x2="0" y1="8" y2="' + (ACC_H - 18) + '" style="display:none"/>' +
      '<rect x="0" y="0" width="' + ACC_W + '" height="' + ACC_H + '" style="fill:transparent"/></svg>';
  }
  function bindAccHover(svg, series) {
    var pts = series.filter(function (x) { return fin(x.market); });
    var cross = svg.querySelector(".cross");
    svg.addEventListener("mousemove", function (e) {
      var r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * (ACC_W / r.width);
      var i = Math.max(0, Math.min(pts.length - 1, Math.round((px - ACC_PL) / (ACC_W - ACC_PL - ACC_PR) * (pts.length - 1))));
      var xx = ACC_PL + i / (pts.length - 1) * (ACC_W - ACC_PL - ACC_PR);
      cross.setAttribute("x1", xx); cross.setAttribute("x2", xx); cross.style.display = "";
      var p = pts[i];
      showTip(e, "<b>" + esc(p.d) + "</b>" + tipRows([[T("mk.acc.series_pot"), fin(p.potential) ? pct(p.potential) : "-"],
        [T("mk.acc.series_mkt"), pct(p.market)], [T("mk.acc.kind"), T(p.live ? "mk.acc.kind_live" : "mk.acc.kind_bt")]]));
    });
    svg.addEventListener("mouseleave", function () { cross.style.display = "none"; hideTip(); });
  }
  function bucketBars(buckets) {
    var list = buckets.filter(function (b) { return b.n && fin(b.avg); });
    if (!list.length) return '<div class="mk-empty">' + esc(T("mk.acc.wait")) + "</div>";
    var mx = Math.max(0.5, Math.max.apply(null, list.map(function (b) { return Math.abs(b.avg); })));
    var W = 420, lw = 130, rw = 92, rowH = 28, mid = lw + (W - lw - rw) / 2, half = (W - lw - rw) / 2 - 4, H = list.length * rowH + 4;
    var g = list.map(function (b, i) {
      var y0 = i * rowH + 4, w = Math.abs(b.avg) / mx * half, up = b.avg >= 0;
      return '<text x="' + (lw - 8) + '" y="' + (y0 + 15) + '" text-anchor="end" style="fill:var(--text2);font-size:12px">' + esc(T("mk.sig." + b.band)) +
        '</text><rect x="' + (up ? mid : mid - w).toFixed(1) + '" y="' + (y0 + 5) + '" width="' + Math.max(1, w).toFixed(1) + '" height="' + (rowH - 12) +
        '" rx="4" style="fill:' + (up ? "var(--mk-up)" : "var(--mk-down)") + '"/><text x="' + (W - 4) + '" y="' + (y0 + 15) +
        '" text-anchor="end" style="fill:var(--text);font-size:12px">' + pct(b.avg) + " (" + b.n + ")</text>";
    }).join("");
    return '<svg class="mk-chart" viewBox="0 0 ' + W + " " + H + '" style="max-width:' + W + 'px"><line class="grid" x1="' + mid + '" x2="' + mid + '" y1="0" y2="' + H + '"/>' + g + "</svg>";
  }

  // ------------------------------------------------------------------ tooltip
  function tipRows(rows) {
    return rows.map(function (r) { return '<div class="row"><span>' + esc(r[0]) + "</span><span>" + esc(r[1]) + "</span></div>"; }).join("");
  }
  function showTip(e, html) {
    if (!S.tip) { S.tip = document.createElement("div"); S.tip.className = "mk-tip"; document.body.appendChild(S.tip); }
    S.tip.innerHTML = html;
    S.tip.style.display = "block";
    var w = S.tip.offsetWidth, h = S.tip.offsetHeight;
    var xx = e.clientX + 14, yy = e.clientY + 14;
    if (xx + w > window.innerWidth - 8) xx = e.clientX - w - 14;
    if (yy + h > window.innerHeight - 8) yy = e.clientY - h - 14;
    S.tip.style.left = Math.max(4, xx) + "px";
    S.tip.style.top = Math.max(4, yy) + "px";
  }
  function hideTip() { if (S.tip) S.tip.style.display = "none"; }

  // ------------------------------------------------------------------ events
  function onBody(e) {
    var t = e.target;
    var star = t.closest("[data-star]");
    if (star) { e.stopPropagation(); var p = star.dataset.star.split("|"); toggleWatch(p[0], p[1], star.classList.contains("on")); return; }
    var srt = t.closest("[data-sort]");
    if (srt) {
      var q = srt.dataset.sort.split("|"), cur = S.sort[q[0]];
      S.sort[q[0]] = [q[1], cur[0] === q[1] ? -cur[1] : (q[1] === "symbol" || q[1] === "rank" || q[1] === "sector" ? 1 : -1)];
      redrawTable(q[0]);
      return;
    }
    var flt = t.closest("[data-filter]");
    if (flt) { var f = flt.dataset.filter.split("|"); S.filter[f[0]] = f[1]; drawBody(); return; }
    var go = t.closest("[data-go]");
    if (go) { S.tab = go.dataset.go; if (S.tab === "outlook") S.outlook = S.outlook || "vn"; syncTabs(); drawBody(); refresh(false); return; }
    var ol = t.closest("[data-outlook]");
    if (ol) { S.outlook = ol.dataset.outlook; drawBody(); refresh(false); return; }
    var ppk = t.closest("[data-ppk]");
    if (ppk) { S.ppKind = ppk.dataset.ppk; S.ppAt = 0; drawBody(); return; }
    if (t.closest("[data-pptg]")) { togglePPTg(); return; }
    var ppa = t.closest("[data-pp]");
    if (ppa) { ppAction(ppa.dataset.pp); return; }
    var pps = t.closest("[data-ppsim]");
    if (pps) { runSim(+pps.dataset.ppsim, pps); return; }
    var ppc = t.closest("[data-ppclose]");
    if (ppc) { e.stopPropagation(); ppClose(ppc.dataset.ppclose); return; }
    var ppt = t.closest("[data-pptrade]");
    if (ppt) { S.ppOpen[ppt.dataset.pptrade] = !S.ppOpen[ppt.dataset.pptrade]; if (S.pp[S.ppKind]) { var bx = S.el.querySelector("#mkPP"); var top = body().scrollTop; bx.innerHTML = paperHtml(S.pp[S.ppKind]); body().scrollTop = top; var sv = bx.querySelector("svg[data-ppcurve]"); if (sv) bindCurveHover(sv, ppCurvePoints(S.pp[S.ppKind].curve || [], S.pp[S.ppKind].stats && S.pp[S.ppKind].stats.start_cash)); if (S.ppSim[S.ppKind]) paintSim(S.ppSim[S.ppKind]); } return; }
    if (t.closest("summary")) return;
    var ask = t.closest("[data-ask]");
    if (ask) { askJavis(T("mk.ask_prompt", { m: T("mk.tab." + ask.dataset.ask), k: ask.dataset.ask })); return; }
    var add = t.closest("[data-add]");
    if (add) { addSymbol(add.dataset.add); return; }
    if (t.closest('[data-act="retry"]')) { refresh(true); return; }
    var open = t.closest("[data-open]");
    if (open && !t.closest("input,label")) { var o = open.dataset.open.split("|"); openDetail(o[0], o.slice(1).join("|")); }
  }
  function onInput(e) {
    var t = e.target;
    if (t.dataset.q) { S.q[t.dataset.q] = t.value; redrawTable(t.dataset.q); }
    else if (t.dataset.watchonly) { S.watchOnly[t.dataset.watchonly] = t.checked; redrawTable(t.dataset.watchonly); }
    else if (t.dataset.addsym && e.type === "change" && t.value.trim()) { addSymbol(t.dataset.addsym); }
  }
  function syncTabs() {
    try { localStorage.setItem(LS_TAB, S.tab); } catch (e) {}
    if (S.el) S.el.querySelectorAll(".mk-bar [data-tab]").forEach(function (x) { x.classList.toggle("on", x.dataset.tab === S.tab); });
  }
  function redrawTable(kind) {
    var b = body(), d = S.data[kind];
    if (!b || !d || S.tab !== kind) return;
    var w = b.querySelector(".mk-tblw");
    if (!w) return;
    var tmp = document.createElement("div");
    tmp.innerHTML = tableHtml(kind, d.rows || []);
    var note = w.nextElementSibling;
    w.replaceWith(tmp.firstChild);
    if (note && note.classList.contains("mk-note")) note.replaceWith(tmp.lastChild);
  }
  function toggleWatch(kind, sym, on) {
    api("/market/watchlist", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: on ? "remove" : "add", kind: kind, symbol: sym }) }).then(function (r) {
      if (r && r.ok === false) { alert(r.message || T("mk.err.symbol")); return; }
      var d = S.data[kind];
      if (d) (d.rows || []).forEach(function (row) { if ((row.id || row.symbol) === sym) row.watch = !on; });
      if (S.tab === kind) redrawTable(kind);
      var st = S.modal && S.modal.querySelector("[data-mstar]");
      if (st) { st.classList.toggle("on", !on); st.dataset.on = on ? "" : "1"; }
    });
  }
  function addSymbol(kind) {
    var inp = S.el && S.el.querySelector('[data-addsym="' + kind + '"]');
    var v = inp && inp.value.trim();
    if (!v) { if (inp) inp.focus(); return; }
    var btn = S.el.querySelector('[data-add="' + kind + '"]');
    if (btn) btn.disabled = true;
    api("/market/watchlist", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ op: "add", kind: kind, symbol: v }) }).then(function (r) {
      if (btn) btn.disabled = false;
      if (!r || !r.ok) { alert((r && r.message) || T("mk.err.symbol")); return; }
      inp.value = "";
      S.watchOnly[kind] = false;
      load(kind, true).then(function () { if (S.tab === kind) drawBody(); openDetail(kind, r.symbol); });
    });
  }
  function askJavis(prompt) {
    closeModal();
    try { if (window.JavisNav) window.JavisNav.go("chat"); } catch (e) {}
    var tries = 0;
    (function send() {
      if (window.JavisChatApi && typeof window.JavisChatApi.send === "function" && document.getElementById("chatInput") !== null) {
        window.JavisChatApi.send(prompt);
      } else if (tries++ < 20) setTimeout(send, 150);
      else if (window.JavisChatApi && window.JavisChatApi.send) window.JavisChatApi.send(prompt);
    })();
  }

  // ------------------------------------------------------------------ detail dialog
  var RANGES = [["3m", 63], ["6m", 126], ["1y", 252], ["all", 0]];
  var DS = { range: "6m", mode: "candle", ov: { sma20: true, sma50: true, sma200: true, bb: false } };

  function closeModal() {
    if (S.modal) { S.modal.remove(); S.modal = null; document.removeEventListener("keydown", escClose); }
    hideTip();
  }
  function escClose(e) { if (e.key === "Escape") closeModal(); }
  function openDetail(kind, sym) {
    closeModal();
    var m = document.createElement("div");
    m.className = "mk-modal mk-root";
    m.innerHTML = '<div class="mk-dlg" role="dialog" aria-modal="true"><div class="mk-skel" style="height:420px"></div></div>';
    document.body.appendChild(m);
    S.modal = m;
    document.addEventListener("keydown", escClose);
    m.addEventListener("click", function (e) { if (e.target === m || e.target.closest("[data-close]")) closeModal(); });
    api("/market/history?kind=" + encodeURIComponent(kind) + "&symbol=" + encodeURIComponent(sym)).then(function (h) {
      if (S.modal !== m) return;
      if (!h || !h.ok) {
        m.querySelector(".mk-dlg").innerHTML = '<div class="mk-dlg-h"><h2>' + esc(sym) + '</h2><span class="mk-sp"></span><button type="button" class="mk-btn ghost" data-close="1">' +
          IC("x") + '</button></div><div class="mk-err">' + esc(T("mk.err.load")) + "</div>";
        return;
      }
      if (kind === "crypto" && !(h.bars.o || []).some(function (v, i) { return v !== h.bars.c[i]; })) DS.mode = "line";
      drawDetail(m, kind, sym, h);
    });
  }
  function rowFor(kind, sym) {
    var d = S.data[kind];
    var list = d ? (d.rows || []).concat(d.indices || []) : [];
    return list.filter(function (r) { return (r.id || r.symbol) === sym; })[0] || null;
  }
  function drawDetail(m, kind, sym, h) {
    var a = h.analysis || {}, row = rowFor(kind, sym) || {};
    var watching = !!row.watch;
    var last = a.price;
    var title = kind === "crypto" ? (row.symbol || h.symbol.toUpperCase()) : h.symbol;
    var sub = kind === "vn" ? (row.sector ? T("mk.sector." + row.sector) : h.name) : (h.name !== h.symbol ? h.name : "");
    var unit = kind === "vn" && !/INDEX|VN30|HNX|UPCOM|VN100/.test(h.symbol) ? " " + T("mk.unit_k") : (h.currency ? " " + h.currency : "");
    var ranges = RANGES.map(function (r) {
      return '<button type="button" class="mk-segb sm' + (DS.range === r[0] ? " on" : "") + '" data-range="' + r[0] + '">' + esc(T("mk.range." + r[0])) + "</button>";
    }).join("");
    var modes = ["candle", "line"].map(function (x) {
      return '<button type="button" class="mk-segb sm' + (DS.mode === x ? " on" : "") + '" data-mode="' + x + '">' + esc(T("mk.mode." + x)) + "</button>";
    }).join("");
    var ovs = [["sma20", "MA20", "var(--mk-s1)"], ["sma50", "MA50", "var(--mk-s2)"], ["sma200", "MA200", "var(--mk-s3)"], ["bb", "Bollinger", "var(--mk-band)"]].map(function (o) {
      return '<label class="mk-chip" style="cursor:pointer"><input type="checkbox" data-ov="' + o[0] + '"' + (DS.ov[o[0]] ? " checked" : "") +
        '><i style="display:inline-block;width:14px;height:' + (o[0] === "bb" ? "10px" : "3px") + ";border-radius:2px;background:" + (o[0] === "bb" ? "var(--mk-s3);opacity:.35" : o[2]) + '"></i>' + o[1] + "</label>";
    }).join("");
    var rng = a.range_5d || [];
    var stats = [
      [T("mk.st.open_prev"), price(a.prev)], [T("mk.col.w1"), pct(a.chg_5d)], [T("mk.col.m1"), pct(a.chg_1m)], [T("mk.col.m3"), pct(a.chg_3m)],
      [T("mk.col.y1"), pct(a.chg_1y)], [T("mk.st.high52"), price(a.high_52w)], [T("mk.st.low52"), price(a.low_52w)], [T("mk.st.from_high"), pct(a.from_high)],
      [T("mk.st.drawdown"), pct(a.drawdown_1y)], ["MA20", price(a.sma20)], ["MA50", price(a.sma50)], ["MA200", price(a.sma200)], ["RSI 14", num(a.rsi, 1)],
      ["MACD", num(a.macd, 3)], [T("mk.st.macd_hist"), num(a.macd_hist, 3)], ["ATR %", fin(a.atr_pct) ? num(a.atr_pct, 2) + "%" : "-"],
      [T("mk.st.hv20"), fin(a.hv20) ? num(a.hv20, 1) + "%" : "-"], [T("mk.st.hv120"), fin(a.hv120) ? num(a.hv120, 1) + "%" : "-"],
      [T("mk.st.bbw"), fin(a.bb_width) ? num(a.bb_width, 1) + "% (" + (fin(a.bb_rank) ? a.bb_rank : "-") + "/100)" : "-"],
      [T("mk.col.vol_ratio"), fin(a.vol_ratio) ? num(a.vol_ratio, 2) + "x" : "-"], [T("mk.st.volume"), compact(a.volume)],
    ];
    if (kind === "crypto") stats.push([T("mk.col.mcap"), compact(row.mcap)], [T("mk.col.vol24"), compact(row.volume_24h)], [T("mk.st.ath"), pct(row.ath_from)]);
    m.querySelector(".mk-dlg").innerHTML =
      '<div class="mk-dlg-h"><h2>' + esc(title) + '</h2><span class="mk-muted">' + esc(sub || "") + " · " + esc(T("mk.tab." + kind)) + "</span>" +
      '<span class="mk-dlg-p">' + price(last) + '</span><span class="mk-muted">' + esc(unit) + "</span>" + chg(a.chg_1d) +
      '<span class="mk-sp"></span><button type="button" class="mk-star' + (watching ? " on" : "") + '" data-mstar="' + kind + "|" + esc(sym) + '" data-on="' + (watching ? "1" : "") +
      '" title="' + esc(T("mk.watch")) + '">' + IC("star") + '</button><button type="button" class="mk-btn" data-dask="1">' + IC("sparkles") + "<span>" + esc(T("mk.ask_one")) +
      '</span></button><button type="button" class="mk-btn ghost" data-close="1" aria-label="' + esc(T("mk.close")) + '">' + IC("x") + "</button></div>" +
      '<div class="mk-sigbox"><div><div class="k">' + esc(T("mk.score")) + '</div><div class="v">' + scorePill(a.score) + " " + esc(T("mk.sig." + (a.signal || "neutral"))) +
      '</div></div><div><div class="k">' + esc(T("mk.col.move")) + '</div><div class="v">' + moveBar(a.move_score) + ' <span class="mk-kicker">' + esc(T("mk.volreg." + (a.vol_regime || "normal"))) +
      '</span></div></div><div><div class="k">' + esc(T("mk.range5")) + '</div><div class="v">' + (rng.length ? price(rng[0]) + " - " + price(rng[1]) : "-") +
      ' <span class="mk-kicker">±' + num(a.exp_move_5d, 1) + "%</span></div></div></div>" +
      '<div class="mk-chips mk-sec">' + reasonChips(a.reasons) + "</div>" +
      '<div class="mk-tools mk-sec"><div class="mk-seg">' + ranges + '</div><div class="mk-seg">' + modes + '</div><span class="mk-sp"></span>' + ovs + "</div>" +
      '<div id="mkChart"></div>' +
      '<div class="mk-stats">' + stats.map(function (p) { return "<div><span>" + esc(p[0]) + "</span><b>" + esc(p[1]) + "</b></div>"; }).join("") + "</div>" +
      '<p class="mk-note">' + IC("info") + esc(T("mk.disclaimer_short")) + " · " + esc(T("mk.updated", { t: ago(h.at) })) + "</p>";
    var dlg = m.querySelector(".mk-dlg");
    function paint() { drawPriceChart(dlg.querySelector("#mkChart"), h, kind); }
    dlg.onclick = function (e) {
      var r = e.target.closest("[data-range]"), md = e.target.closest("[data-mode]");
      if (r) { DS.range = r.dataset.range; dlg.querySelectorAll("[data-range]").forEach(function (b) { b.classList.toggle("on", b === r); }); paint(); }
      if (md) { DS.mode = md.dataset.mode; dlg.querySelectorAll("[data-mode]").forEach(function (b) { b.classList.toggle("on", b === md); }); paint(); }
      var st = e.target.closest("[data-mstar]");
      if (st) { var p = st.dataset.mstar.split("|"); toggleWatch(p[0], p.slice(1).join("|"), !!st.dataset.on); }
      if (e.target.closest("[data-dask]")) askJavis(T("mk.ask_one_prompt", { s: title, m: T("mk.tab." + kind), k: kind, sym: h.symbol }));
    };
    dlg.onchange = function (e) { var o = e.target.dataset.ov; if (o) { DS.ov[o] = e.target.checked; paint(); } };
    paint();
  }

  function niceTicks(mn, mx, n) {
    var span = mx - mn || Math.abs(mx) || 1, step = Math.pow(10, Math.floor(Math.log10(span / n)));
    var err = span / n / step;
    step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
    var out = [];
    for (var v = Math.ceil(mn / step) * step; v <= mx + step * 1e-9; v += step) out.push(v);
    return out;
  }
  function drawPriceChart(el, h, kind) {
    if (!el) return;
    var b = h.bars, L = h.lines, n = b.c.length;
    var take = RANGES.filter(function (r) { return r[0] === DS.range; })[0][1];
    var s0 = take ? Math.max(0, n - take) : 0;
    var idx = []; for (var i = s0; i < n; i++) idx.push(i);
    var W = Math.max(320, el.clientWidth || 800), pl = 6, pr = 62;
    var P = { top: 8, h: 260 }, V = { top: 278, h: 56 }, R = { top: 350, h: 70 }, M = { top: 436, h: 70 };
    var H = M.top + M.h + 22;
    var cw = (W - pl - pr) / idx.length;
    var x = function (k) { return pl + (k + 0.5) * cw; };
    var lo = Infinity, hi = -Infinity;
    idx.forEach(function (i) {
      lo = Math.min(lo, b.l[i]); hi = Math.max(hi, b.h[i]);
      if (DS.ov.bb && L.bb_up[i] != null) { hi = Math.max(hi, L.bb_up[i]); lo = Math.min(lo, L.bb_low[i]); }
      ["sma20", "sma50", "sma200"].forEach(function (k) { if (DS.ov[k] && L[k][i] != null) { hi = Math.max(hi, L[k][i]); lo = Math.min(lo, L[k][i]); } });
    });
    var pad = (hi - lo) * 0.05 || hi * 0.01 || 1; lo -= pad; hi += pad;
    var y = function (v) { return P.top + (hi - v) / (hi - lo) * P.h; };
    var vmax = Math.max.apply(null, idx.map(function (i) { return b.v[i] || 0; })) || 1;
    var yv = function (v) { return V.top + V.h - (v / vmax) * V.h; };
    var yr = function (v) { return R.top + (100 - v) / 100 * R.h; };
    var mvals = []; idx.forEach(function (i) { [L.macd[i], L.macd_signal[i], L.macd_hist[i]].forEach(function (v) { if (v != null) mvals.push(Math.abs(v)); }); });
    var mm = Math.max.apply(null, mvals.concat([1e-9]));
    var ym = function (v) { return M.top + M.h / 2 - (v / mm) * (M.h / 2); };
    var o = [];
    niceTicks(lo, hi, 5).forEach(function (v) {
      o.push('<line class="grid" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(v).toFixed(1) + '" y2="' + y(v).toFixed(1) + '"/><text x="' + (W - pr + 6) + '" y="' + (y(v) + 4).toFixed(1) + '">' + price(v) + "</text>");
    });
    [[V, T("mk.st.volume")], [R, "RSI 14"], [M, "MACD"]].forEach(function (p) {
      o.push('<text x="' + (pl + 2) + '" y="' + (p[0].top + 11) + '" style="font-weight:600">' + esc(p[1]) + "</text>");
    });
    [30, 70].forEach(function (v) {
      o.push('<line class="grid" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + yr(v) + '" y2="' + yr(v) + '" style="stroke-dasharray:3 3"/><text x="' + (W - pr + 6) + '" y="' + (yr(v) + 4) + '">' + v + "</text>");
    });
    o.push('<rect x="' + pl + '" y="' + yr(70) + '" width="' + (W - pl - pr) + '" height="' + (yr(30) - yr(70)) + '" style="fill:var(--mk-s3);opacity:.06"/>');
    o.push('<line class="grid" x1="' + pl + '" x2="' + (W - pr) + '" y1="' + ym(0) + '" y2="' + ym(0) + '"/>');
    // x-axis dates
    var step = Math.max(1, Math.round(idx.length / Math.max(2, Math.floor((W - pl - pr) / 110))));
    for (var k = 0; k < idx.length; k += step) {
      o.push('<text x="' + x(k).toFixed(1) + '" y="' + (H - 6) + '" text-anchor="middle">' + esc(dateOf(b.t[idx[k]])) + "</text>");
    }
    if (DS.ov.bb) {
      var up = [], dn = [];
      idx.forEach(function (i, k) { if (L.bb_up[i] != null) { up.push(x(k).toFixed(1) + "," + y(L.bb_up[i]).toFixed(1)); dn.unshift(x(k).toFixed(1) + "," + y(L.bb_low[i]).toFixed(1)); } });
      if (up.length) o.push('<polygon points="' + up.concat(dn).join(" ") + '" style="fill:var(--mk-band);stroke:var(--mk-s3);stroke-opacity:.35;stroke-width:1"/>');
    }
    var bw = Math.max(1, Math.min(10, cw * 0.66));
    if (DS.mode === "candle") {
      idx.forEach(function (i, k) {
        var upc = b.c[i] >= b.o[i], col = upc ? "var(--mk-up)" : "var(--mk-down)";
        var yt = y(Math.max(b.o[i], b.c[i])), yb = y(Math.min(b.o[i], b.c[i]));
        o.push('<line x1="' + x(k).toFixed(1) + '" x2="' + x(k).toFixed(1) + '" y1="' + y(b.h[i]).toFixed(1) + '" y2="' + y(b.l[i]).toFixed(1) + '" style="stroke:' + col + ';stroke-width:1"/>' +
          '<rect x="' + (x(k) - bw / 2).toFixed(1) + '" y="' + yt.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + Math.max(1, yb - yt).toFixed(1) + '" rx="' + (bw > 4 ? 1 : 0) + '" style="fill:' + col + '"/>');
      });
    } else {
      var pts = idx.map(function (i, k) { return x(k).toFixed(1) + "," + y(b.c[i]).toFixed(1); });
      var col0 = b.c[idx[idx.length - 1]] >= b.c[idx[0]] ? "var(--mk-up)" : "var(--mk-down)";
      o.push('<polygon points="' + x(0).toFixed(1) + "," + (P.top + P.h) + " " + pts.join(" ") + " " + x(idx.length - 1).toFixed(1) + "," + (P.top + P.h) + '" style="fill:' + col0 + ';opacity:.08"/>');
      o.push('<polyline points="' + pts.join(" ") + '" style="fill:none;stroke:' + col0 + ';stroke-width:2;stroke-linejoin:round"/>');
    }
    [["sma20", "var(--mk-s1)"], ["sma50", "var(--mk-s2)"], ["sma200", "var(--mk-s3)"]].forEach(function (s) {
      if (!DS.ov[s[0]]) return;
      var pts = []; idx.forEach(function (i, k) { if (L[s[0]][i] != null) pts.push(x(k).toFixed(1) + "," + y(L[s[0]][i]).toFixed(1)); });
      if (pts.length > 1) o.push('<polyline points="' + pts.join(" ") + '" style="fill:none;stroke:' + s[1] + ';stroke-width:1.6;stroke-linejoin:round"/>');
    });
    idx.forEach(function (i, k) {
      var col = b.c[i] >= b.o[i] ? "var(--mk-up)" : "var(--mk-down)";
      if (b.v[i]) o.push('<rect x="' + (x(k) - bw / 2).toFixed(1) + '" y="' + yv(b.v[i]).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + (V.top + V.h - yv(b.v[i])).toFixed(1) + '" style="fill:' + col + ';opacity:.45"/>');
    });
    var rp = []; idx.forEach(function (i, k) { if (L.rsi[i] != null) rp.push(x(k).toFixed(1) + "," + yr(L.rsi[i]).toFixed(1)); });
    if (rp.length > 1) o.push('<polyline points="' + rp.join(" ") + '" style="fill:none;stroke:var(--mk-s3);stroke-width:1.6"/>');
    idx.forEach(function (i, k) {
      var hv = L.macd_hist[i];
      if (hv == null) return;
      var y0 = ym(0), y1 = ym(hv);
      o.push('<rect x="' + (x(k) - bw / 2).toFixed(1) + '" y="' + Math.min(y0, y1).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + Math.max(0.5, Math.abs(y1 - y0)).toFixed(1) +
        '" style="fill:' + (hv >= 0 ? "var(--mk-up)" : "var(--mk-down)") + ';opacity:.5"/>');
    });
    [["macd", "var(--mk-s1)"], ["macd_signal", "var(--mk-s2)"]].forEach(function (s) {
      var pts = []; idx.forEach(function (i, k) { if (L[s[0]][i] != null) pts.push(x(k).toFixed(1) + "," + ym(L[s[0]][i]).toFixed(1)); });
      if (pts.length > 1) o.push('<polyline points="' + pts.join(" ") + '" style="fill:none;stroke:' + s[1] + ';stroke-width:1.4"/>');
    });
    // last price marker
    var lc = b.c[n - 1];
    o.push('<line x1="' + pl + '" x2="' + (W - pr) + '" y1="' + y(lc).toFixed(1) + '" y2="' + y(lc).toFixed(1) + '" style="stroke:var(--text3);stroke-dasharray:2 3"/>' +
      '<rect x="' + (W - pr + 2) + '" y="' + (y(lc) - 9).toFixed(1) + '" width="' + (pr - 4) + '" height="18" rx="4" style="fill:var(--text)"/><text x="' + (W - pr + 6) + '" y="' + (y(lc) + 4).toFixed(1) +
      '" style="fill:var(--bg);font-weight:700">' + price(lc) + "</text>");
    o.push('<line class="cross" id="mkCx" x1="0" x2="0" y1="' + P.top + '" y2="' + (M.top + M.h) + '" style="display:none"/>');
    o.push('<rect id="mkHit" x="' + pl + '" y="0" width="' + (W - pl - pr) + '" height="' + (M.top + M.h) + '" style="fill:transparent"/>');
    el.innerHTML = '<svg class="mk-chart" width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(T("mk.chart_aria")) + '">' + o.join("") + "</svg>";
    var hit = el.querySelector("#mkHit"), cx = el.querySelector("#mkCx"), svg = el.querySelector("svg");
    hit.addEventListener("mousemove", function (e) {
      var r = svg.getBoundingClientRect();
      var px = (e.clientX - r.left) * (W / r.width);
      var k = Math.max(0, Math.min(idx.length - 1, Math.floor((px - pl) / cw)));
      var i = idx[k];
      cx.setAttribute("x1", x(k)); cx.setAttribute("x2", x(k)); cx.style.display = "";
      var ch = i > 0 ? (b.c[i] / b.c[i - 1] - 1) * 100 : null;
      var rows = [[T("mk.st.close"), price(b.c[i]) + " (" + pct(ch) + ")"]];
      if (DS.mode === "candle") rows.push([T("mk.st.ohl"), price(b.o[i]) + " / " + price(b.h[i]) + " / " + price(b.l[i])]);
      if (b.v[i]) rows.push([T("mk.st.volume"), compact(b.v[i])]);
      if (L.sma20[i] != null) rows.push(["MA20", price(L.sma20[i])]);
      if (L.sma50[i] != null) rows.push(["MA50", price(L.sma50[i])]);
      if (L.sma200[i] != null) rows.push(["MA200", price(L.sma200[i])]);
      if (L.rsi[i] != null) rows.push(["RSI", num(L.rsi[i], 1)]);
      if (L.macd_hist[i] != null) rows.push([T("mk.st.macd_hist"), num(L.macd_hist[i], 3)]);
      showTip(e, "<b>" + esc(dateOf(b.t[i])) + "</b>" + tipRows(rows));
    });
    hit.addEventListener("mouseleave", function () { cx.style.display = "none"; hideTip(); });
  }

  // F&G chart hover (drawn as a static SVG inside the crypto tab).
  document.addEventListener("mousemove", function (e) {
    if (!S.el || S.tab !== "crypto") return;
    var svg = e.target && e.target.closest ? e.target.closest('svg[data-fng]') : null;
    if (!svg) return;
    var hist = (S.data.crypto && S.data.crypto.fng && S.data.crypto.fng.history) || [];
    if (hist.length < 2) return;
    var r = svg.getBoundingClientRect();
    var k = Math.round(((e.clientX - r.left) / r.width * 360 - 4) / (360 - 28) * (hist.length - 1));
    var p = hist[Math.max(0, Math.min(hist.length - 1, k))];
    showTip(e, "<b>" + esc(dateOf(p.t)) + "</b>" + tipRows([[T("mk.fng"), p.v + " · " + T("mk.fng_l." + fngKey(p.v))]]));
  }, { passive: true });
  document.addEventListener("mouseout", function (e) {
    if (e.target && e.target.closest && e.target.closest("svg[data-fng]") && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest("svg[data-fng]"))) hideTip();
  }, { passive: true });

  var api_ = { mount: mount, unmount: unmount };
  // Pure helpers for Node tests.
  api_._test = { squarify: squarify, niceTicks: niceTicks, sigOf: sigOf, fngKey: fngKey, pct: pct, dir: dir };
  window.JavisMarkets = api_;
})();
