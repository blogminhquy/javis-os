/* pan-zoom.js - zoom and pan for a picture or a diagram inside a box (0.405.0).
 *
 * Owner, 2026-10-29: "a wide diagram shows tiny on the phone and cannot be zoomed". The page viewport turns pinch zoom
 * off (index.html, user-scalable=no), so every viewer that shows something bigger than its box needs its own zoom.
 *
 *   var pz = window.JavisPanZoom.attach(box, content, { w: 1200, h: 400 });
 *   pz.fit(); pz.zoomBy(1.25); pz.destroy();
 *
 * `box` is the visible frame, `content` the element moved and scaled inside it (an <svg> or <img>), `w`/`h` its natural
 * size. Mouse: wheel zooms around the pointer, drag pans. Touch: two fingers pinch, one finger pans. Double click or
 * double tap: zoom in 2x at that spot, or back to fit when already zoomed. A small bar with -, %, + and Fit sits in the
 * bottom corner. The math lives in pure functions (fitState, zoomAt, pinchStep, clampState) so node tests run it.
 */
(function () {
  "use strict";

  var MIN_FACTOR = 0.5;   // never smaller than half of "fit"
  var MAX_SCALE = 8;      // never bigger than 8x the natural size

  function tr(k) { return window.t ? window.t(k) : k; }
  function ic(n) { return window.ic ? window.ic(n) : ""; }

  // Content of size w x h centred in a viewport vw x vh, scaled down to fit but never blown up past its natural size.
  function fitState(size) {
    var w = size.w > 0 ? size.w : 1, h = size.h > 0 ? size.h : 1;
    var s = Math.min(size.vw / w, size.vh / h, 1);
    if (!(s > 0)) s = 1;
    return { scale: s, x: (size.vw - w * s) / 2, y: (size.vh - h * s) / 2 };
  }

  function limits(size) {
    var fit = fitState(size).scale;
    return { min: fit * MIN_FACTOR, max: Math.max(MAX_SCALE, fit) };
  }

  // Scale by `factor` keeping the point (px, py) of the viewport still.
  function zoomAt(state, factor, px, py, size) {
    var lim = limits(size);
    var s = Math.max(lim.min, Math.min(lim.max, state.scale * factor));
    var k = s / state.scale;
    return clampState({ scale: s, x: px - (px - state.x) * k, y: py - (py - state.y) * k }, size);
  }

  // Two fingers moved from `from` to `to` ({x, y, distance} of their midpoint and gap): scale and follow the midpoint.
  function pinchStep(state, from, to, size) {
    if (!(from.distance > 0)) return state;
    var z = zoomAt(state, to.distance / from.distance, from.x, from.y, size);
    return clampState({ scale: z.scale, x: z.x + (to.x - from.x), y: z.y + (to.y - from.y) }, size);
  }

  // Keep some of the content in view: it can be dragged off until only a quarter of the box (or of it) is left.
  function clampState(state, size) {
    var cw = size.w * state.scale, ch = size.h * state.scale;
    var keepX = Math.min(cw, size.vw) / 4, keepY = Math.min(ch, size.vh) / 4;
    return { scale: state.scale,
      x: Math.max(keepX - cw, Math.min(size.vw - keepX, state.x)),
      y: Math.max(keepY - ch, Math.min(size.vh - keepY, state.y)) };
  }

  // Natural size of an <svg>: its viewBox, else its width/height attributes, else what it draws now.
  function svgSize(svg) {
    var vb = svg.viewBox && svg.viewBox.baseVal;
    if (vb && vb.width > 0 && vb.height > 0) return { w: vb.width, h: vb.height };
    var w = parseFloat(svg.getAttribute("width")), h = parseFloat(svg.getAttribute("height"));
    if (w > 0 && h > 0) return { w: w, h: h };
    var r = svg.getBoundingClientRect();
    return { w: r.width || 800, h: r.height || 600 };
  }

  function attach(box, content, nat) {
    var state = { scale: 1, x: 0, y: 0 };
    var pointers = {}, lastPinch = null, lastDrag = null, lastTap = 0, moved = false;
    box.classList.add("jv-pz");
    content.classList.add("jv-pz-item");
    content.style.width = nat.w + "px";
    content.style.height = nat.h + "px";
    content.style.maxWidth = "none";
    content.style.maxHeight = "none";
    var bar = document.createElement("div");
    bar.className = "jv-pz-bar";
    bar.innerHTML =
      '<button type="button" data-pz="out" aria-label="' + tr("pz.out") + '" title="' + tr("pz.out") + '">' + ic("minus") + "</button>" +
      '<span class="jv-pz-pct" aria-live="polite"></span>' +
      '<button type="button" data-pz="in" aria-label="' + tr("pz.in") + '" title="' + tr("pz.in") + '">' + ic("plus") + "</button>" +
      '<button type="button" data-pz="fit" aria-label="' + tr("pz.fit") + '" title="' + tr("pz.fit") + '">' + ic("maximize") + "</button>";
    box.appendChild(bar);
    var pct = bar.querySelector(".jv-pz-pct");

    function size() { return { w: nat.w, h: nat.h, vw: box.clientWidth || 1, vh: box.clientHeight || 1 }; }
    function paint() {
      content.style.transform = "translate(" + state.x + "px," + state.y + "px) scale(" + state.scale + ")";
      pct.textContent = Math.round(state.scale * 100) + "%";
    }
    function fit() { state = fitState(size()); paint(); }
    function zoomBy(f, px, py) {
      var s = size();
      state = zoomAt(state, f, px == null ? s.vw / 2 : px, py == null ? s.vh / 2 : py, s);
      paint();
    }
    function local(e) { var r = box.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
    function two() {
      var ids = Object.keys(pointers);
      var a = pointers[ids[0]], b = pointers[ids[1]];
      return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, distance: Math.hypot(a.x - b.x, a.y - b.y) };
    }

    function onWheel(e) {
      e.preventDefault();
      var p = local(e);
      // A trackpad pinch arrives as a wheel with ctrlKey and small deltas; a mouse wheel as about 100 per notch.
      var f = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.002));
      zoomBy(f, p.x, p.y);
    }
    function onDown(e) {
      if (e.target.closest && e.target.closest(".jv-pz-bar")) return;
      if (e.pointerType === "mouse" && e.button !== 0) return;
      try { box.setPointerCapture(e.pointerId); } catch (x) {}
      pointers[e.pointerId] = local(e);
      moved = false;
      var n = Object.keys(pointers).length;
      if (n === 2) { lastPinch = two(); lastDrag = null; }
      else if (n === 1) lastDrag = pointers[e.pointerId];
      box.classList.add("jv-pz-grab");
    }
    function onMove(e) {
      if (!pointers[e.pointerId]) return;
      var p = local(e);
      pointers[e.pointerId] = p;
      var n = Object.keys(pointers).length;
      if (n >= 2 && lastPinch) {
        var now = two();
        state = pinchStep(state, lastPinch, now, size());
        lastPinch = now; moved = true; paint();
      } else if (n === 1 && lastDrag) {
        var dx = p.x - lastDrag.x, dy = p.y - lastDrag.y;
        if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
        state = clampState({ scale: state.scale, x: state.x + dx, y: state.y + dy }, size());
        lastDrag = p; paint();
      }
    }
    function onUp(e) {
      if (!pointers[e.pointerId]) return;
      var p = pointers[e.pointerId];
      delete pointers[e.pointerId];
      var n = Object.keys(pointers).length;
      if (n < 2) lastPinch = null;
      lastDrag = n === 1 ? pointers[Object.keys(pointers)[0]] : null;
      if (!n) box.classList.remove("jv-pz-grab");
      // Touch has no dblclick event: two quick taps in place make one.
      if (e.pointerType !== "mouse" && !moved && !n) {
        var t = Date.now();
        if (t - lastTap < 320) { lastTap = 0; toggle(p.x, p.y); } else lastTap = t;
      }
    }
    function toggle(px, py) {
      var f = fitState(size());
      if (state.scale > f.scale * 1.05) fit(); else zoomBy(2, px, py);
    }
    function onDbl(e) {
      if (e.target.closest && e.target.closest(".jv-pz-bar")) return;
      var p = local(e); toggle(p.x, p.y);
    }
    function onBar(e) {
      var b = e.target.closest && e.target.closest("[data-pz]");
      if (!b) return;
      e.stopPropagation();
      if (b.dataset.pz === "in") zoomBy(1.25);
      else if (b.dataset.pz === "out") zoomBy(0.8);
      else fit();
    }
    var ro = null;
    box.addEventListener("wheel", onWheel, { passive: false });
    box.addEventListener("pointerdown", onDown);
    box.addEventListener("pointermove", onMove);
    box.addEventListener("pointerup", onUp);
    box.addEventListener("pointercancel", onUp);
    box.addEventListener("dblclick", onDbl);
    bar.addEventListener("click", onBar);
    // Refit when the box changes size (rotating the phone, resizing the window) and the user has not zoomed yet.
    if (window.ResizeObserver) {
      var fitted = true;
      ro = new ResizeObserver(function () {
        var f = fitState(size());
        if (fitted || Math.abs(state.scale - f.scale) < 1e-6) { state = f; paint(); }
        fitted = false;
      });
      ro.observe(box);
    }
    fit();

    function destroy() {
      if (ro) ro.disconnect();
      box.removeEventListener("wheel", onWheel);
      box.removeEventListener("pointerdown", onDown);
      box.removeEventListener("pointermove", onMove);
      box.removeEventListener("pointerup", onUp);
      box.removeEventListener("pointercancel", onUp);
      box.removeEventListener("dblclick", onDbl);
      if (bar.parentNode) bar.parentNode.removeChild(bar);
      box.classList.remove("jv-pz", "jv-pz-grab");
    }
    return { fit: fit, zoomBy: zoomBy, destroy: destroy, state: function () { return state; } };
  }

  var api = { attach: attach, svgSize: svgSize, fitState: fitState, zoomAt: zoomAt, pinchStep: pinchStep, clampState: clampState };
  if (typeof window !== "undefined") window.JavisPanZoom = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
