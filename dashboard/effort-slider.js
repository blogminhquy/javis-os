/* effort-slider.js - the composer's thinking-level slider (0.153.0).
 * Pure parts (stops, position, lock) are tested with node; drawing (orange particle canvas) runs only in the browser.
 */
(function () {
  "use strict";
  var LEVELS = ["off", "low", "medium", "high", "xhigh", "ultra"];
  var LOCKED_SUFFIX = /-(minimal|low|medium|high|xhigh|max)$/i;
  // Full dictionary keys (the i18n test scans literal keys, so no "eff." + value concatenation).
  var LABEL_KEY = { off: "eff.off", low: "eff.low", medium: "eff.medium", high: "eff.high", xhigh: "eff.xhigh", ultra: "eff.ultra" };

  function clamp(n, a, b) { return Math.max(a, Math.min(b, n)); }
  function levelFromRatio(r) { return LEVELS[clamp(Math.round(clamp(Number(r) || 0, 0, 1) * 5), 0, 5)]; }
  function ratioFromLevel(v) { var i = LEVELS.indexOf(v); return i < 0 ? 0 : i / 5; }
  // Antigravity models carry the level in their name (agy refuses an extra --effort): the slider is locked.
  function isLocked(provider, model) { return provider === "antigravity-cli" && LOCKED_SUFFIX.test(String(model || "")); }

  var api = { LEVELS: LEVELS, LABEL_KEY: LABEL_KEY, levelFromRatio: levelFromRatio, ratioFromLevel: ratioFromLevel, isLocked: isLocked };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document === "undefined") return;

  function tw(k) { return window.t ? window.t(k) : k; }
  function reduced() { try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) { return false; } }

  function mount(el, opt) {
    opt = opt || {};
    var value = LEVELS.indexOf(opt.value) < 0 ? "off" : opt.value;
    el.innerHTML =
      '<div class="eff-head"><span class="eff-lbl"></span><span class="eff-val"></span></div>' +
      (opt.locked ? '<p class="eff-locked"></p>' :
        '<div class="eff-ends"><span class="eff-faster"></span><span class="eff-smarter"></span></div>' +
        '<div class="eff-track" role="slider" tabindex="0" aria-valuemin="0" aria-valuemax="5">' +
        '<canvas class="eff-cv" aria-hidden="true"></canvas><div class="eff-ticks" aria-hidden="true">' +
        '<i></i><i></i><i></i><i></i><i></i><i></i></div><div class="eff-thumb" aria-hidden="true"></div></div>' +
        '<div class="eff-rec"></div>');
    el.querySelector(".eff-lbl").textContent = tw("eff.head");
    var valEl = el.querySelector(".eff-val");
    if (opt.locked) {
      el.querySelector(".eff-locked").textContent = tw("eff.locked");
      valEl.textContent = tw(LABEL_KEY[value]);
      return { set: function () {}, destroy: function () { el.innerHTML = ""; } };
    }
    el.querySelector(".eff-faster").textContent = tw("eff.faster");
    el.querySelector(".eff-smarter").textContent = tw("eff.smarter");
    var rec = el.querySelector(".eff-rec");
    rec.textContent = tw("eff.recommended");
    var track = el.querySelector(".eff-track"), thumb = el.querySelector(".eff-thumb");
    var cv = el.querySelector(".eff-cv"), ctx = cv.getContext && cv.getContext("2d");
    var parts = [], raf = 0, alive = true;
    for (var i = 0; i < 70; i++) parts.push({ x: Math.random(), y: Math.random(), s: Math.random() * 1.6 + 0.6, v: Math.random() * 0.0025 + 0.0008, p: Math.random() * 6 });

    function fillPx() { var w = track.clientWidth; return 13 + (w - 26) * ratioFromLevel(value); }
    function paint() {
      var i = LEVELS.indexOf(value);
      thumb.style.left = (fillPx() - 11) + "px";
      valEl.textContent = tw(LABEL_KEY[value]);
      track.setAttribute("aria-valuenow", String(i));
      track.setAttribute("aria-valuetext", tw(LABEL_KEY[value]));
      track.title = value === "ultra" ? tw("eff.ultra_hint") : "";
      rec.style.visibility = value === "medium" ? "visible" : "hidden";
    }
    function draw(t) {
      if (!alive || !ctx) return;
      var W = cv.width = track.clientWidth * 2, H = cv.height = track.clientHeight * 2;
      var fill = fillPx() * 2 + 20;
      var accent = getComputedStyle(el).getPropertyValue("--accent").trim() || "#ff7a3c";
      ctx.clearRect(0, 0, W, H);
      ctx.globalAlpha = 1;
      var g = ctx.createLinearGradient(0, 0, fill, 0);
      g.addColorStop(0, accent + "59");
      g.addColorStop(1, accent);
      ctx.fillStyle = g;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(0, 0, Math.max(fill, 0), H, H / 2); else ctx.rect(0, 0, Math.max(fill, 0), H);
      ctx.fill();
      parts.forEach(function (q) {
        if (!reduced()) { q.x += q.v; if (q.x > 1) q.x = 0; }
        var px = q.x * W;
        if (px > fill - 6) return;
        var d = px / Math.max(fill, 1);
        var a = (0.35 + 0.65 * Math.abs(Math.sin((reduced() ? 0 : t) / 500 + q.p))) * (0.3 + 0.7 * d);
        ctx.fillStyle = "rgba(255,255,255," + a.toFixed(2) + ")";
        ctx.beginPath(); ctx.arc(px, q.y * H, q.s * (1 + d), 0, 7); ctx.fill();
      });
      if (!reduced()) raf = requestAnimationFrame(draw);
    }
    function set(v, fire) {
      if (LEVELS.indexOf(v) < 0 || v === value) return;
      value = v; paint(); if (reduced()) draw(0);
      if (fire && opt.onChange) opt.onChange(v);
    }
    function fromEvent(e) {
      var r = track.getBoundingClientRect();
      set(levelFromRatio((e.clientX - r.left - 13) / Math.max(r.width - 26, 1)), true);
    }
    var dragging = false;
    track.addEventListener("pointerdown", function (e) { dragging = true; try { track.setPointerCapture(e.pointerId); } catch (x) {} fromEvent(e); });
    track.addEventListener("pointermove", function (e) { if (dragging) fromEvent(e); });
    track.addEventListener("pointerup", function () { dragging = false; });
    track.addEventListener("keydown", function (e) {
      var i = LEVELS.indexOf(value);
      if (e.key === "ArrowRight" || e.key === "ArrowUp") i++;
      else if (e.key === "ArrowLeft" || e.key === "ArrowDown") i--;
      else if (e.key === "Home") i = 0;
      else if (e.key === "End") i = 5;
      else return;
      e.preventDefault();
      set(LEVELS[clamp(i, 0, 5)], true);
    });
    paint();
    raf = requestAnimationFrame(draw);
    return {
      set: function (v) { set(v, false); },
      focus: function () { track.focus(); },
      destroy: function () { alive = false; cancelAnimationFrame(raf); el.innerHTML = ""; },
    };
  }
  api.mount = mount;
  window.JavisEffortSlider = api;
})();
