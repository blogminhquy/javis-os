/* plan-limit.js - the composer's plan usage ring (0.329.0).
 * Takes the place of the old Fast mode bolt (which moved into the Effort popover). It shows only for brains
 * that run on a plan the user already pays for: Claude Code on its signed-in session, ChatGPT through Codex.
 * The ring fills with the larger of the two meters (5-hour session, weekly) and turns amber, then red, when
 * either gets close to its limit. Clicking it opens the two meters with their reset times, like Claude's
 * "Plan usage limits". Numbers come from GET /plan-limits (server/plan_limits.py).
 * Pure parts (which brain, level, reset text) are tested with node.
 */
(function () {
  "use strict";
  // Provider id on the model picker -> the brain key in /plan-limits.
  // Grok Build and Antigravity report no meter: their ring stays grey and only turns red once the CLI
  // refused a turn for plan quota (server: plan_limits.ghi_het).
  var BRAIN = { "anthropic-cli": "claude", "openai-oauth": "codex", "grok-cli": "grok", "antigravity-cli": "agy" };
  var BRAND = { claude: "Claude", codex: "ChatGPT", grok: "Grok", agy: "Antigravity" };
  // Full dictionary keys per brain (the i18n test scans literal keys, so no concatenation).
  var NONE_KEY = { claude: "lim.none_claude", codex: "lim.none_codex", grok: "lim.none_grok", agy: "lim.none_agy" };
  var WARN = 50, BAD = 80;   // same thresholds as plan_limits.CANH_BAO / SAT (the server sends its own too)

  function brainOf(provider, plan) {
    var b = BRAIN[provider];
    if (!b) return "";
    return plan && plan[provider] === false ? "" : b;
  }
  function level(pct, warn, bad) {
    var p = Number(pct) || 0;
    return p >= (bad || BAD) ? "bad" : p >= (warn || WARN) ? "warn" : "ok";
  }
  // Seconds until reset -> { key, vars } for the "resets in ..." line. Past a day, the weekday and time instead.
  function resetParts(resetsAt, now) {
    var s = Math.max(0, Math.round(Number(resetsAt) - now));
    if (!resetsAt || !s) return null;
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    if (h >= 24) return { key: "lim.reset_at", when: resetsAt };
    if (h >= 1) return { key: "lim.reset_hm", vars: { h: h, m: m } };
    return { key: "lim.reset_m", vars: { m: Math.max(1, m) } };
  }

  // Header next to "Plan usage limits": the brand, then the plan when the server could name it ("Claude · Max").
  function whoText(brain, plan) {
    var b = BRAND[brain] || "";
    return plan ? b + " · " + plan : b;
  }

  var api = { brainOf: brainOf, level: level, resetParts: resetParts, whoText: whoText, NONE_KEY: NONE_KEY };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document === "undefined") return;

  var $ = function (id) { return document.getElementById(id); };
  var tw = function (k, v) { return window.t ? window.t(k, v) : k; };
  var LOC = function () { return (window.JavisI18n && window.JavisI18n.locale()) || "vi-VN"; };
  var data = null, provider = "", busy = null, lastFetch = 0, names = {};

  function cur() {
    var b = brainOf(provider, data && data.plan);
    return { brain: b, d: b && data ? data[b] : null };
  }
  function resetText(w) {
    var r = resetParts(w && w.resets_at, Date.now() / 1000);
    if (!r) return w && w.moi ? tw("lim.fresh") : "";
    if (r.key === "lim.reset_at") {
      var d = new Date(r.when * 1000);
      return tw("lim.reset_at", { when: d.toLocaleDateString(LOC(), { weekday: "short" }) + " " +
        d.toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit" }) });
    }
    return tw(r.key, r.vars);
  }

  function paintRing() {
    var btn = $("limitBtn");
    if (!btn) return;
    var c = cur();
    btn.hidden = !c.brain;
    if (!c.brain) { closePop(); return; }
    var n = data && data.nguong, d = c.d;
    var pct = d ? d.max : 0;
    var lv = d ? (d.muc || level(pct, n && n.canh_bao, n && n.sat)) : "none";
    btn.dataset.muc = lv;
    var fg = btn.querySelector(".lim-fg");
    if (fg) fg.setAttribute("stroke-dasharray", Math.max(d ? 3 : 0, Math.min(100, pct)) + " 100");
    var lines = [tw("lim.title")];
    if (d && d.het) lines.push(tw("lim.het_short"));
    if (d && d.five_hour) lines.push(tw("lim.session") + ": " + d.five_hour.pct + "%");
    if (d && d.seven_day) lines.push(tw("lim.week") + ": " + d.seven_day.pct + "%");
    if (!d) lines.push(tw(c.brain === "grok" || c.brain === "agy" ? "lim.no_meter" : "lim.none_short"));
    btn.title = lines.join("\n");
    btn.setAttribute("aria-label", lines.join(", "));
    if (popOpen()) paintPop();
  }

  function row(w, n) {
    if (!w) return "";
    var lv = level(w.pct, n && n.canh_bao, n && n.sat);
    var rs = resetText(w);
    return '<div class="lim-row"><div class="lim-row-h"><span class="lim-name"></span>' +
      '<span class="lim-pct lim-' + lv + '"></span></div>' +
      '<div class="lim-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + w.pct + '">' +
      '<i class="lim-' + lv + '" style="width:' + Math.min(100, w.pct) + '%"></i></div>' +
      (rs ? '<div class="lim-reset"></div>' : "") + "</div>";
  }
  function paintPop() {
    var pop = $("limitPop");
    if (!pop) return;
    var c = cur(), d = c.d, n = data && data.nguong;
    var meter = d && (d.five_hour || d.seven_day);
    pop.innerHTML = '<div class="lim-head"><span class="lim-h"></span><span class="lim-who"></span></div>' +
      (d && d.het ? '<div class="lim-het"><p class="lim-het-h"></p><p class="lim-het-r"></p></div>' : "") +
      (meter ? row(d.five_hour, n) + row(d.seven_day, n) + '<p class="lim-at"></p>' : "") +
      (!meter ? '<p class="lim-none"></p>' : "");
    pop.querySelector(".lim-h").textContent = tw("lim.title");
    pop.querySelector(".lim-who").textContent = whoText(c.brain, names[c.brain] || "");
    if (d && d.het) {
      var hAt = new Date(d.het.at * 1000).toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit" });
      pop.querySelector(".lim-het-h").textContent = tw("lim.het", { time: hAt });
      pop.querySelector(".lim-het-r").textContent = d.het.reset ? resetText({ resets_at: d.het.reset })
        : tw("lim.het_no_reset", { brand: BRAND[c.brain] });
    }
    if (!meter) {
      // Claude or ChatGPT before the first turn, or Grok and Antigravity, which never send a meter.
      pop.querySelector(".lim-none").textContent = tw(NONE_KEY[c.brain]);
      return;
    }
    var rows = pop.querySelectorAll(".lim-row"), ws = [], labels = [];
    if (d.five_hour) { ws.push(d.five_hour); labels.push(tw("lim.session")); }
    if (d.seven_day) { ws.push(d.seven_day); labels.push(tw("lim.week")); }
    rows.forEach(function (r, i) {
      r.querySelector(".lim-name").textContent = labels[i];
      r.querySelector(".lim-pct").textContent = tw("lim.used", { n: ws[i].pct });
      var rs = r.querySelector(".lim-reset");
      if (rs) rs.textContent = resetText(ws[i]);
    });
    var at = new Date((d.at || 0) * 1000);
    pop.querySelector(".lim-at").textContent = tw("lim.at", { time: at.toLocaleTimeString(LOC(), { hour: "2-digit", minute: "2-digit" }) +
      (Date.now() - at.getTime() > 86400000 ? " " + at.toLocaleDateString(LOC()) : "") });
  }

  function popOpen() { var p = $("limitPop"); return !!(p && !p.hidden); }
  function closePop() {
    var p = $("limitPop"), b = $("limitBtn");
    if (p) p.hidden = true;
    if (b) b.setAttribute("aria-expanded", "false");
  }
  function openPop() {
    var p = $("limitPop"), b = $("limitBtn");
    if (!p || !b) return;
    try { if (window.JavisModelBar && window.JavisModelBar.closeAll) window.JavisModelBar.closeAll(); } catch (e) {}
    p.hidden = false;
    b.setAttribute("aria-expanded", "true");
    paintPop();
    var card = p.offsetParent;
    var maxLeft = card ? Math.max(8, card.clientWidth - p.offsetWidth - 8) : 8;
    p.style.left = Math.min(b.offsetLeft, maxLeft) + "px";
    refresh(true, true);
  }

  // withNames: the popover opening also asks the server to name each plan (it may run `claude auth status`).
  function refresh(force, withNames) {
    if (busy) return busy;
    if (!force && Date.now() - lastFetch < 15000) return Promise.resolve(data);
    busy = fetch("/plan-limits" + (withNames ? "?goi=1" : "")).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
      if (d) data = d;
      if (d && d.ten_goi) Object.keys(d.ten_goi).forEach(function (k) { if (d.ten_goi[k]) names[k] = d.ten_goi[k]; });
      lastFetch = Date.now();
      paintRing();
      return data;
    }).catch(function () { return data; }).then(function (d) { busy = null; return d; });
    return busy;
  }
  // model-picker.js calls this whenever the effective model changes.
  function setProvider(p) {
    provider = p || "";
    paintRing();
    if (BRAIN[provider] && !data) refresh(true);
  }

  document.addEventListener("click", function (e) {
    if (e.target.closest && e.target.closest("#limitBtn")) { popOpen() ? closePop() : openPop(); return; }
    if (popOpen() && !(e.target.closest && e.target.closest("#limitPop"))) closePop();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && popOpen()) { closePop(); var b = $("limitBtn"); if (b) b.focus(); }
  });

  window.addEventListener("javis:i18n", paintRing);

  api.setProvider = setProvider;
  api.refresh = function () { return refresh(true); };
  api.close = closePop;
  window.JavisPlanLimit = api;
})();
